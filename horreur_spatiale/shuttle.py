# -*- coding: utf-8 -*-
"""
shuttle.py — Navette pilotable (phase TPS) et caméra à la troisième personne.

  * vol spatial 6 degrés de liberté simplifié, avec inertie : poussée
    avant/arrière, strafe, montée/descente, tangage/lacet/roulis, boost ;
  * caméra derrière et au-dessus de la navette, avec retard (lissage) ;
  * collisions sphère/boîte (orientée) contre la coque et les débris ->
    dégâts sur la barre d'intégrité ;
  * séquences scriptées : atterrissage automatique dans le hangar,
    décollage final (victoire).
"""
import math
import random

from panda3d.core import Spotlight as PSpot, PerspectiveLens, Vec4, Vec3 as PVec3, TransparencyAttrib
from ursina import Entity, Vec3, camera, color, destroy, application

import config as C
import textures
from geometry import MeshBuilder
import loot


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lerp_angle(a, b, t):
    d = (b - a + 180) % 360 - 180
    return a + d * t


class Shuttle:
    def __init__(self, game, pos, yaw):
        self.game = game
        self.root = Entity(name='shuttle', position=pos, rotation=(0, yaw, 0))
        self.vel = Vec3(0, 0, 0)
        self.rate_p = self.rate_y = self.rate_r = 0.0
        self.integrity = C.SHIP_INTEGRITY
        self.boost = C.SHIP_BOOST_MAX
        self.boosting = False
        self.throttle = 0.0
        self.hit_cd = 0.0
        self.warn = 0.0
        self.auto = None
        self.auto_t = 0.0
        self.landed = False
        self.cam_pos = Vec3(*pos) - self.root.forward * C.TPS_CAM_DISTANCE + Vec3(0, C.TPS_CAM_HEIGHT, 0)
        self.cam_up = Vec3(0, 1, 0)
        self.blink_t = 0.0
        self._build_model()
        # phare avant (éclaire la coque en approche)
        self.spot = PSpot("shuttle_headlight")
        lens = PerspectiveLens()
        lens.setFov(38)
        lens.setNearFar(.5, 150)
        self.spot.setLens(lens)
        self.spot.setExponent(8)
        self.spot.setAttenuation(PVec3(1, 0, 0.0006))
        self.spot.setColor(Vec4(1.6, 1.55, 1.4, 1))
        self.spot_np = self.root.attachNewNode(self.spot)
        self.spot_np.setPos(0, 0, 3.8)
        application.base.render.setLight(self.spot_np)
        a = game.audio
        self.engine_snd = a.loop("ship_engine", "ship_engine", .8)
        self.boost_snd = a.loop("ship_boost", "ship_boost", .6)

    # ------------------------------------------------------------------
    def _build_model(self):
        mb = MeshBuilder(uv_scale=1.5)
        em = MeshBuilder()
        hull = (.62, .6, .55)
        dark = (.25, .25, .27)
        mb.box((0, 0, 0), (2.4, 1.5, 5.2), hull)
        mb.box((0, -.1, 3.1), (1.9, 1.15, 1.4), hull)
        mb.box((0, -.2, 4.0), (1.2, .7, .7), hull)
        mb.box((0, .78, -.5), (1.6, .12, 3.8), dark)            # dos
        mb.box((0, -.8, 0), (2.0, .12, 4.6), dark)              # ventre
        # cockpit vitré
        em.box((0, .45, 3.35), (1.5, .45, .9), (.08, .18, .28))
        # ailes
        for s in (-1, 1):
            mb.box((s * 2.0, -.25, -.6), (1.8, .14, 2.6), hull)
            mb.box((s * 2.95, -.05, -1.2), (.12, .6, 1.2), dark)
            mb.cylinder((s * 1.05, .15, -3.1), .5, 1.8, dark, 12, 'z')
            mb.cylinder((s * 1.05, .15, -4.05), .56, .2, (.15, .15, .15), 12, 'z')
            em.cylinder((s * 1.05, .15, -4.16), .4, .02, (1, .55, .25), 12, 'z')
            # patins d'atterrissage
            mb.box((s * .9, -1.05, 1.0), (.12, .5, .12), dark)
            mb.box((s * .9, -1.05, -1.6), (.12, .5, .12), dark)
            mb.box((s * .9, -1.3, -.3), (.2, .08, 3.4), dark)
        # bandes de marquage
        mb.box((0, .02, 1.6), (2.42, .3, .5), (.7, .45, .1))
        self.body = mb.build(parent=self.root, texture=textures.get('panel'))
        self.glow_mesh = em.build(parent=self.root, unlit=True)
        # lumières de navigation
        self.nav_l = Entity(parent=self.root, model='sphere', color=color.red, scale=.18, position=(-2.95, .3, -1.2),
                            unlit=True)
        self.nav_r = Entity(parent=self.root, model='sphere', color=color.lime, scale=.18, position=(2.95, .3, -1.2),
                            unlit=True)
        self.nav_t = Entity(parent=self.root, model='sphere', color=color.white, scale=.15, position=(0, .9, -2.4),
                            unlit=True)
        # flammes / halos des réacteurs
        self.flames = []
        for s in (-1, 1):
            f = Entity(parent=self.root, model='quad', texture=textures.get('glow'), color=color.rgb(1, .6, .3),
                       position=(s * 1.05, .15, -4.4), scale=1.4, billboard=True, unlit=True)
            f.setTransparency(TransparencyAttrib.MAlpha)
            f.setDepthWrite(False)
            cone = Entity(parent=self.root, model='cube', color=color.rgb(.6, .8, 1), position=(s * 1.05, .15, -4.8),
                          scale=(.35, .35, .8), unlit=True)
            self.flames.append((f, cone))

    # ------------------------------------------------------------------
    @property
    def position(self):
        return self.root.world_position

    @property
    def speed(self):
        return self.vel.length()

    def update(self, dt, inp, colliders):
        self.blink_t += dt
        self.hit_cd = max(0.0, self.hit_cd - dt)
        self.warn = max(0.0, self.warn - dt)
        if self.auto:
            self._update_auto(dt)
        else:
            self._fly(dt, inp)
            self._collide(colliders, dt)
        self._visuals(dt)

    def _fly(self, dt, inp):
        thrust, strafe, vert, pitch, yaw, roll, boost = inp.ship_axes(dt)
        # boost limité
        self.boosting = boost and self.boost > 0 and thrust > 0
        if self.boosting:
            self.boost = max(0.0, self.boost - C.SHIP_BOOST_DRAIN * dt)
        else:
            self.boost = min(C.SHIP_BOOST_MAX, self.boost + C.SHIP_BOOST_REGEN * dt)
        mult = C.SHIP_BOOST_MULT if self.boosting else 1.0
        self.throttle = max(abs(thrust), abs(strafe) * .6, abs(vert) * .6) * mult
        # rotation : le taux visé suit l'entrée avec un léger retard (inertie)
        inv = 1.0 / max(dt, 1e-4)
        tp = max(-C.SHIP_TURN_RATE * 1.4, min(C.SHIP_TURN_RATE * 1.4, pitch * inv))
        ty = max(-C.SHIP_TURN_RATE * 1.4, min(C.SHIP_TURN_RATE * 1.4, yaw * inv))
        tr = roll * C.SHIP_ROLL_RATE
        k = min(1.0, dt * C.SHIP_ANGULAR_DAMP)
        self.rate_p += (tp - self.rate_p) * k
        self.rate_y += (ty - self.rate_y) * k
        self.rate_r += (tr - self.rate_r) * k
        # rotation relative au repère de la navette (Panda : H=-lacet, P=-tangage)
        self.root.setHpr(self.root, -self.rate_y * dt, -self.rate_p * dt, self.rate_r * dt)
        # poussée dans le repère local
        f, r, u = self.root.forward, self.root.right, self.root.up
        acc = f * (thrust * C.SHIP_THRUST * mult) + r * (strafe * C.SHIP_STRAFE) + u * (vert * C.SHIP_VERTICAL)
        self.vel += acc * dt
        self.vel *= max(0.0, 1 - C.SHIP_DRAG * dt)
        vmax = C.SHIP_MAX_SPEED * mult
        sp = self.vel.length()
        if sp > vmax:
            self.vel = self.vel * (1 - min(1, dt * 2)) + self.vel.normalized() * vmax * min(1, dt * 2)
        self.root.position += self.vel * dt

    def _collide(self, colliders, dt):
        p = self.root.world_position
        R = C.SHIP_RADIUS
        for col in colliders:
            c, rad = col.bound()
            dx, dy, dz = p.x - c[0], p.y - c[1], p.z - c[2]
            if dx * dx + dy * dy + dz * dz > (rad + R) ** 2:
                continue
            q = col.closest(p)
            n = p - q
            d = n.length()
            if d >= R:
                continue
            n = n / d if d > 1e-4 else Vec3(0, 1, 0)
            p = p + n * (R - d)
            vn = self.vel.dot(n)
            if vn < 0:
                impact = -vn
                self.vel -= n * vn * 1.35
                self.vel *= .85
                if impact > C.SHIP_DAMAGE_MIN_SPEED:
                    dmg = (impact - C.SHIP_DAMAGE_MIN_SPEED) * C.SHIP_DAMAGE_FACTOR
                    self.integrity = max(0.0, self.integrity - dmg)
                    if self.hit_cd <= 0:
                        self.hit_cd = .35
                        self.game.audio.play("ship_hit", min(1, .4 + impact / 20), random.uniform(.9, 1.1))
                        self.game.inp.rumble(min(1, .4 + impact / 15), min(1, impact / 20), 300)
                        self.warn = 1.5
                        self.game.shake(min(1, impact / 12))
                    if self.integrity <= 0:
                        self.game.game_over("shuttle")
        self.root.position = p

    # ------------------------------------------------------------------
    def camera_follow(self, dt):
        """Caméra TPS lissée : derrière et au-dessus de la navette."""
        f = self.root.forward
        u = self.root.up
        target = self.root.world_position - f * C.TPS_CAM_DISTANCE + u * C.TPS_CAM_HEIGHT
        k = 1 - math.exp(-C.TPS_CAM_SMOOTH * dt)
        self.cam_pos = self.cam_pos + (target - self.cam_pos) * k
        self.cam_up = (self.cam_up + (u - self.cam_up) * min(1, dt * 3)).normalized()
        camera.position = self.cam_pos
        look = self.root.world_position + f * 8 + u * 1.2
        camera.look_at(look, up=self.cam_up)
        shake = self.game.shake_amount
        if shake > 0:
            camera.rotation_z += random.uniform(-1, 1) * shake * 3
            camera.rotation_x += random.uniform(-1, 1) * shake * 2
        base_fov = C.FOV - 10
        camera.fov += (base_fov + min(12, self.speed * .35) - camera.fov) * min(1, dt * 3)

    def cinematic_camera(self, dt, cam_point):
        k = 1 - math.exp(-2.0 * dt)
        self.cam_pos = self.cam_pos + (Vec3(*cam_point) - self.cam_pos) * k
        camera.position = self.cam_pos
        camera.look_at(self.root.world_position, up=Vec3(0, 1, 0))

    # ------------------------------------------------------------------
    def start_landing(self, pad, on_done):
        """Atterrissage automatique sur l'aire du hangar."""
        self.auto = "align"
        self.auto_t = 0.0
        self.auto_from = Vec3(self.root.position)
        self.auto_rot = Vec3(self.root.rotation)
        self.pad = pad
        self.on_done = on_done
        self.vel = Vec3(0, 0, 0)

    def start_takeoff(self, on_done):
        self.auto = "lift"
        self.auto_t = 0.0
        self.auto_from = Vec3(self.root.position)
        self.on_done = on_done
        self.landed = False
        application.base.render.setLight(self.spot_np)

    def _update_auto(self, dt):
        self.auto_t += dt
        t = self.auto_t
        if self.auto == "align":
            k = _smooth(t / 3.2)
            hover = Vec3(self.pad[0], 3.6, self.pad[1])
            self.root.position = self.auto_from + (hover - self.auto_from) * k
            r = self.auto_rot
            self.root.rotation = (r.x + (0 - r.x) * k, _lerp_angle(r.y, 180, k), r.z + (0 - r.z) * k)
            self.throttle = .5
            if t >= 3.2:
                self.auto, self.auto_t = "descend", 0.0
        elif self.auto == "descend":
            k = _smooth(t / 2.2)
            self.root.y = 3.6 + (1.35 - 3.6) * k
            self.throttle = .35 * (1 - k)
            if t >= 2.2:
                self.auto, self.auto_t = "settle", 0.0
                self.game.audio.play("landing", 1.0)
                self.game.inp.rumble(.9, .5, 700)
                self.game.shake(.5)
        elif self.auto == "settle":
            self.throttle = 0
            self.root.y = 1.35 - .08 * math.sin(min(1, t / .4) * math.pi)
            if t >= 1.4:
                self.auto = None
                self.landed = True
                application.base.render.clearLight(self.spot_np)
                self.on_done()
        elif self.auto == "lift":
            k = _smooth(t / 1.8)
            self.root.y = 1.35 + (4.0 - 1.35) * k
            self.throttle = .6
            if t >= 1.8:
                self.auto, self.auto_t = "exit", 0.0
                self.vel = Vec3(0, 0, 0)
        elif self.auto == "exit":
            self.throttle = 1.6
            self.vel += self.root.forward * 16 * dt
            self.root.position += self.vel * dt
            self.root.rotation_x = max(-8, -t * 2)
            if t >= 7.5:
                self.auto = None
                self.on_done()

    def _visuals(self, dt):
        on = (self.blink_t % 1.2) < .15
        self.nav_t.color = color.white if on else color.rgb(.1, .1, .1)
        th = self.throttle if not self.landed else 0
        for f, cone in self.flames:
            f.scale = .6 + th * 1.2 + random.uniform(0, .15) * th
            f.color = color.rgb(.6, .75, 1) if self.boosting else color.rgb(1, .6, .3)
            cone.scale_z = .1 + th * 1.4
            cone.z = -4.4 - cone.scale_z / 2
            cone.enabled = th > .05
        self.engine_snd.set(0 if self.landed else .5 + .5 * min(1, th), pitch=.8 + .35 * min(1.5, th), fade=4)
        self.boost_snd.set(.9 if self.boosting else 0, fade=5)

    def silence(self):
        self.engine_snd.set(0, fade=2)
        self.boost_snd.set(0, fade=5)

    def destroy(self):
        application.base.render.clearLight(self.spot_np)
        self.game.audio.stop_loop("ship_engine")
        self.game.audio.stop_loop("ship_boost")
        destroy(self.root)


class ShuttleInteract(loot.Interactable):
    """Sas de la navette posée dans le hangar."""
    radius = 3.0

    def __init__(self, game, level, shuttle):
        self.game = game
        self.shuttle = shuttle
        p = shuttle.root.world_position
        r = shuttle.root.right
        self.pos = (p.x + r.x * 1.6, 1.2, p.z + r.z * 1.6)
        level.add_interactable(self, self.pos[0], self.pos[2])

    def prompt(self, game):
        if game.state != "fps":
            return None
        return "Repartir avec la navette" if game.has_hdd() else "Navette (récupère d'abord le disque dur)"

    def interact(self, game):
        if game.has_hdd():
            game.start_escape()
        else:
            game.hud.message("Pas sans le disque dur. Salle de commandement.", color.orange)
