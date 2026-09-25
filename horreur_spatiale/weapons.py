# -*- coding: utf-8 -*-
"""
weapons.py — Pistolet (hitscan, visée, recul, flash, chargeur) et couteau
(silencieux, durabilité). Chaque tir déclenche le mode horreur.
"""
import math
import random

from panda3d.core import TransparencyAttrib
from ursina import Entity, camera, color, Vec3, destroy

import config as C
import textures


class Weapons:
    def __init__(self, game):
        self.game = game
        self.has_pistol = False
        self.mag = 0
        self.aiming = False
        self.aim_k = 0.0
        self.cooldown = 0.0
        self.reloading = 0.0
        self.knife_cd = 0.0
        self.knife_anim = 0.0
        self.recoil = 0.0
        self.kick = 0.0
        self.spread_bonus = 0.0
        self.shots_fired = 0
        self.impacts = []
        self.sparks = []

        # --- modèle du pistolet (vue à la première personne) ---------------
        self.vm = Entity(parent=camera, name='viewmodel')
        self.gun = Entity(parent=self.vm, scale=.8)
        metal = color.rgb(.13, .13, .14)
        Entity(parent=self.gun, model='cube', color=metal, scale=(.045, .05, .24), position=(0, .02, .05))      # culasse
        Entity(parent=self.gun, model='cube', color=color.rgb(.08, .08, .08), scale=(.04, .12, .06),
               position=(0, -.06, -.03), rotation_x=12)                                                     # crosse
        Entity(parent=self.gun, model='cube', color=metal, scale=(.03, .015, .03), position=(0, .052, .15))    # guidon
        Entity(parent=self.gun, model='cube', color=color.rgb(.2, .2, .22), scale=(.035, .03, .08),
               position=(0, -.015, .09))
        self.gun_led = Entity(parent=self.gun, model='cube', color=color.rgb(.1, 1, .3), scale=(.008, .008, .008),
                              position=(.024, .03, 0), unlit=True)
        self.flash = Entity(parent=self.gun, model='quad', texture=textures.get('glow'), color=color.rgb(1, .8, .4),
                            scale=.28, position=(0, .02, .25), unlit=True, billboard=True)
        self.flash.setTransparency(TransparencyAttrib.MAlpha)
        self.flash.enabled = False
        self.flash_t = 0.0
        self.gun.enabled = False

        # --- modèle du couteau -------------------------------------------
        self.knife = Entity(parent=self.vm, position=(-.14, -.14, .34))
        Entity(parent=self.knife, model='cube', color=color.rgb(.72, .74, .78), scale=(.012, .035, .2), z=.12)
        Entity(parent=self.knife, model='cube', color=color.rgb(.08, .06, .05), scale=(.03, .04, .11), z=-.03)
        self.knife.enabled = False

    # ------------------------------------------------------------------
    def give_pistol(self):
        self.has_pistol = True
        self.mag = C.PISTOL_START_MAG
        self.game.inventory.add("ammo", C.PISTOL_START_RESERVE)
        self.gun.enabled = True

    @property
    def reserve(self):
        return self.game.inventory.count("ammo")

    def show(self, on):
        self.vm.enabled = on

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        g = self.game
        p = g.player
        busy = p.hidden or p.search_target is not None or g.inventory_ui.reading
        self.cooldown = max(0.0, self.cooldown - dt)
        self.knife_cd = max(0.0, self.knife_cd - dt)
        # visée
        self.aiming = (self.has_pistol and inp.held("aim") and not busy and self.reloading <= 0
                       and self.knife_anim <= 0)
        self.aim_k += ((1.0 if self.aiming else 0.0) - self.aim_k) * min(1, dt * 12)
        p.fov_target = C.FOV + (C.ADS_FOV - C.FOV) * self.aim_k
        # rechargement
        if self.reloading > 0:
            self.reloading -= dt
            if self.reloading <= 0:
                need = C.PISTOL_MAG - self.mag
                got = g.inventory.remove("ammo", need)
                self.mag += got
        elif not busy:
            if inp.pressed("reload"):
                self.start_reload()
            elif inp.pressed("fire") and self.has_pistol:
                self.fire()
            elif inp.pressed("knife"):
                self.knife_attack()
        # animation du modèle
        self.recoil = max(0.0, self.recoil - dt * 6)
        self.kick = max(0.0, self.kick - dt * 9)
        self.spread_bonus = max(0.0, self.spread_bonus - dt * 2)
        hip = Vec3(.16, -.15, .36)
        ads = Vec3(0, -.105, .32)
        pos = hip + (ads - hip) * self.aim_k
        bob = math.sin(p._bob) * .012 * (1 - self.aim_k * .8)
        pos += Vec3(math.cos(p._bob * .5) * .008, bob, -self.kick * .06)
        if self.reloading > 0:
            k = math.sin(min(1, (C.PISTOL_RELOAD_TIME - self.reloading) / C.PISTOL_RELOAD_TIME) * math.pi)
            pos += Vec3(0, -.12 * k, 0)
            self.gun.rotation = (25 * k, 0, 30 * k)
        else:
            self.gun.rotation = (-self.kick * 18, 0, 0)
        if p.running and self.aim_k < .1:
            pos += Vec3(-.05, -.04, 0)
            self.gun.rotation_y = -25
        self.gun.position = pos
        # couteau
        if self.knife_anim > 0:
            self.knife_anim -= dt
            t = 1 - self.knife_anim / .35
            self.knife.enabled = True
            self.knife.position = (-.14 + .26 * t, -.14 + .04 * math.sin(t * math.pi), .34 + .1 * math.sin(t * math.pi))
            self.knife.rotation = (10, -60 + 120 * t, -30 + 60 * t)
            self.gun.y -= .1
        else:
            self.knife.enabled = False
        # flash de bouche
        if self.flash_t > 0:
            self.flash_t -= dt
            self.flash.enabled = True
            self.flash.scale = .2 + random.uniform(0, .15)
            self.flash.rotation_z = random.uniform(0, 360)
        else:
            self.flash.enabled = False
        self.gun_led.color = color.rgb(.1, 1, .3) if self.mag > 2 else (color.rgb(1, .6, .1) if self.mag else color.red)
        # impacts / étincelles
        for s in list(self.sparks):
            s[1] -= dt
            s[0].position += s[2] * dt
            s[2] += Vec3(0, -9, 0) * dt
            if s[1] <= 0:
                destroy(s[0])
                self.sparks.remove(s)

    # ------------------------------------------------------------------
    def start_reload(self):
        g = self.game
        if not self.has_pistol or self.mag >= C.PISTOL_MAG:
            return
        if self.reserve <= 0:
            g.hud.message("Plus de munitions en réserve")
            return
        self.reloading = C.PISTOL_RELOAD_TIME
        g.audio.play("reload", .7)

    def fire(self):
        g = self.game
        if self.cooldown > 0:
            return
        if self.mag <= 0:
            self.cooldown = .25
            g.audio.play("dry_fire", .8)
            if self.reserve > 0:
                self.start_reload()
            return
        self.mag -= 1
        self.shots_fired += 1
        self.cooldown = C.PISTOL_COOLDOWN
        self.kick = 1.0
        self.flash_t = .05
        # recul : relève la visée
        g.player.pitch -= C.PISTOL_RECOIL * (.6 if self.aiming else 1.0)
        g.player.yaw += random.uniform(-.6, .6)
        g.player.trauma = min(1, g.player.trauma + .25)
        g.audio.play("gunshot", 1.0, random.uniform(.95, 1.05))
        g.inp.rumble(1.0, .8, 140)
        cp = camera.world_position
        g.lights.muzzle_flash((cp.x, cp.y, cp.z))
        # bruit très fort + mode horreur
        g.noise((cp.x, cp.y, cp.z), C.NOISE_SHOT, "shot")
        g.horror.trigger((cp.x, cp.y, cp.z))
        # tir hitscan
        spread = (C.PISTOL_SPREAD_ADS if self.aiming else C.PISTOL_SPREAD_HIP) + self.spread_bonus
        self.spread_bonus = min(3, self.spread_bonus + 1.2)
        d = self._spread_dir(spread)
        self._hitscan(cp, d, C.PISTOL_DAMAGE, C.PISTOL_RANGE, gun=True)

    def _spread_dir(self, deg):
        f = camera.forward
        r = camera.right
        u = camera.up
        a = random.uniform(0, 2 * math.pi)
        m = math.tan(math.radians(deg)) * math.sqrt(random.random())
        d = f + r * math.cos(a) * m + u * math.sin(a) * m
        return d.normalized()

    def _hitscan(self, origin, d, damage, max_dist, gun):
        g = self.game
        L = g.level
        wall_t, hit_p, normal = L.raycast(origin.x, origin.y, origin.z, d.x, d.y, d.z, max_dist)
        best_t, best = wall_t, None
        for target, center, radius in g.hit_targets():
            oc = Vec3(center[0] - origin.x, center[1] - origin.y, center[2] - origin.z)
            t = oc.dot(d)
            if t < 0 or t > best_t:
                continue
            closest2 = oc.length_squared() - t * t
            if closest2 <= radius * radius:
                best_t, best = t, target
        if best is not None:
            hp = origin + d * best_t
            best.on_hit(damage, (hp.x, hp.y, hp.z), gun)
            self._spawn_sparks(hp, color.rgb(.3, .9, .2), 6)
            return best
        # impact sur le décor
        hp = Vec3(*hit_p)
        self._spawn_sparks(hp, color.rgb(1, .8, .4), 5)
        self._impact_decal(hp, normal)
        g.audio.play_at("spark", (hp.x, hp.y, hp.z), .4)
        return None

    def _spawn_sparks(self, pos, col, n):
        for _ in range(n):
            e = Entity(model='cube', color=col, scale=.025, position=pos, unlit=True)
            v = Vec3(random.uniform(-2, 2), random.uniform(0, 3), random.uniform(-2, 2))
            self.sparks.append([e, random.uniform(.15, .35), v])

    def _impact_decal(self, pos, normal):
        n = Vec3(*normal)
        e = Entity(model='quad', texture=textures.get('glow'), color=color.rgba(0, 0, 0, .8), scale=.09,
                   position=pos + n * .012)
        e.look_at(pos + n * 2)
        e.rotation_y += 180
        e.setTransparency(TransparencyAttrib.MAlpha)
        e.setDepthOffset(1)
        self.impacts.append(e)
        if len(self.impacts) > 30:
            destroy(self.impacts.pop(0))

    # ------------------------------------------------------------------
    def knife_attack(self):
        g = self.game
        if self.knife_cd > 0:
            return
        if not g.inventory.has("knife"):
            g.hud.message("Tu n'as pas de couteau")
            self.knife_cd = .5
            return
        self.knife_cd = C.KNIFE_COOLDOWN
        self.knife_anim = .35
        g.audio.play("knife_swing", .6, random.uniform(.9, 1.1))
        cp = camera.world_position
        fw = camera.forward
        g.noise((cp.x, cp.y, cp.z), C.NOISE_KNIFE, "knife")
        hit = None
        best = 1e9
        for target, center, radius in g.hit_targets(melee=True):
            dx, dy, dz = center[0] - cp.x, center[1] - cp.y, center[2] - cp.z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist - radius > C.KNIFE_RANGE:
                continue
            dot = (dx * fw.x + dy * fw.y * .3 + dz * fw.z) / max(dist, 1e-4)
            if dot < .55 and dist > .8:
                continue
            if dist < best:
                best, hit = dist, target
        if hit is not None:
            mult = C.KNIFE_STEALTH_MULT if not getattr(hit, "aware", True) else 1
            hit.on_hit(C.KNIFE_DAMAGE * mult, hit.center3(), False)
            g.audio.play("knife_hit", .8)
            g.inp.rumble(.6, .3, 120)
            broke = g.inventory.wear_knife()
            if broke:
                g.audio.play("knife_break", .8)
                g.hud.message("Ton couteau s'est brisé !", color.orange)

    def destroy(self):
        for s in self.sparks:
            destroy(s[0])
        for e in self.impacts:
            destroy(e)
        destroy(self.vm)
