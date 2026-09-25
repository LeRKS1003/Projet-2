# -*- coding: utf-8 -*-
"""
lighting.py — Éclairage et ambiance visuelle.

  * lumière ambiante très faible + brouillard sombre (FPS) ;
  * lampe torche = Spotlight attaché à la caméra, batterie qui se vide ;
  * luminaires (néons, lampes rouges, gyrophares d'alarme) : chaque
    luminaire a un tube émissif visible, mais seules les MAX_POINT_LIGHTS
    lumières les plus proches reçoivent une vraie PointLight (pool) :
    c'est ce qui permet de garder 60 FPS avec un éclairage par pixel ;
  * vision nocturne : éclairage vert amplifié, sources éblouissantes ;
  * soleil directionnel pour la phase TPS.
"""
import math
import random

from panda3d.core import (AmbientLight as PAmbient, PointLight as PPoint, Spotlight as PSpot,
                          DirectionalLight as PDir, PerspectiveLens, Vec4, Vec3 as PVec3)
from ursina import camera, color, scene
from ursina import application

import config as C


class Fixture:
    """Un luminaire du vaisseau."""
    __slots__ = ("pos", "col", "radius", "mode", "entity", "base_col", "phase", "brightness",
                 "intensity", "rate", "room", "dead_until", "active")

    def __init__(self, pos, col, radius=C.LIGHT_RANGE, mode="steady", entity=None, intensity=1.0, room=None):
        self.pos = pos                  # (x, y, z) monde
        self.col = col                  # (r, g, b)
        self.radius = radius
        self.mode = mode                # steady / flicker / broken / pulse / alarm / red / reactor
        self.entity = entity            # tube émissif (Entity) ou None
        self.base_col = col
        self.phase = random.uniform(0, 100)
        self.rate = random.uniform(.6, 1.6)
        self.brightness = 1.0
        self.intensity = intensity
        self.room = room
        self.dead_until = 0.0
        self.active = True

    def compute(self, t, horror):
        """Luminosité courante (0..~1.5) selon le mode et le mode horreur."""
        m = self.mode
        if not self.active:
            return 0.0
        if m == "steady" or m == "red":
            b = 1.0
        elif m == "reactor":
            b = 0.85 + 0.15 * math.sin(t * 2.1 + self.phase)
        elif m == "pulse":
            b = 0.55 + 0.45 * math.sin(t * 1.4 * self.rate + self.phase)
        elif m == "flicker":
            # néon fatigué : allumé la plupart du temps, coupures brèves irrégulières
            x = math.sin(t * 13.0 * self.rate + self.phase) + math.sin(t * 31.7 + self.phase * 2.3)
            b = 0.08 if x > 1.55 else (0.6 if x > 1.3 else 1.0)
        elif m == "broken":
            # néon cassé : éteint, avec des sursauts
            x = math.sin(t * 7.3 * self.rate + self.phase) * math.sin(t * 2.9 + self.phase)
            b = 1.0 if x > 0.82 else 0.0
        elif m == "alarm":
            b = 0.0
        else:
            b = 1.0
        if horror > 0.01:
            if m == "alarm":
                # gyrophare : pulsation rouge rapide
                b = horror * (0.5 + 0.5 * math.sin(t * 9.0 + self.phase)) ** 2 * 1.6
            else:
                # toutes les lumières clignotent fortement
                strobe = 1.0 if math.sin(t * 17.0 + self.phase * 3) > -0.2 else 0.15
                b *= (1 - horror) + horror * strobe * 0.8
        self.brightness = b
        return b

    def current_color(self, horror):
        r, g, b = self.base_col
        if self.mode == "alarm":
            return (1.0, 0.05, 0.02)
        if horror > 0.01:
            # glisse vers le rouge
            k = min(1.0, horror * 1.2)
            r = r * (1 - k) + 1.0 * k
            g = g * (1 - k) + 0.08 * k
            b = b * (1 - k) + 0.05 * k
        return (r, g, b)


class LightManager:
    def __init__(self, root):
        self.root = root
        self.fixtures = []
        self.time = 0.0
        self.horror = 0.0
        self.nightvision = False
        self.flashlight_on = False
        self.battery = C.BATTERY_MAX
        self.mode = "tps"
        self._assign_timer = 0.0
        self.extra_flash = 0.0      # flash de bouche du pistolet
        self.flash_pos = None

        # lumière ambiante
        self.amb_node = PAmbient("ambient")
        self.amb_node.setColor(Vec4(.05, .05, .06, 1))
        self.amb = render_np().attachNewNode(self.amb_node)
        render_np().setLight(self.amb)

        # pool de lumières ponctuelles
        self.pool = []
        for k in range(C.MAX_POINT_LIGHTS):
            pl = PPoint(f"pool_{k}")
            pl.setColor(Vec4(0, 0, 0, 1))
            q = 9.0 / (C.LIGHT_RANGE ** 2)
            pl.setAttenuation(PVec3(1, 0.05, q))
            np_ = render_np().attachNewNode(pl)
            render_np().setLight(np_)
            self.pool.append([np_, pl, None])

        # lumière du flash de bouche
        self.flash_node = PPoint("muzzle")
        self.flash_node.setColor(Vec4(0, 0, 0, 1))
        self.flash_node.setAttenuation(PVec3(1, 0.1, 0.25))
        self.flash_np = render_np().attachNewNode(self.flash_node)
        render_np().setLight(self.flash_np)

        # lampe torche
        self.spot = PSpot("flashlight")
        lens = PerspectiveLens()
        lens.setFov(C.FLASHLIGHT_FOV)
        lens.setNearFar(0.1, 40)
        self.spot.setLens(lens)
        self.spot.setExponent(18)
        self.spot.setAttenuation(PVec3(1, 0.02, 0.012))
        self.spot.setColor(Vec4(0, 0, 0, 1))
        self.spot_np = camera.attachNewNode(self.spot)
        self.spot_np.setPos(0.18, -0.12, 0)
        render_np().setLight(self.spot_np)

        # soleil (phase TPS)
        self.sun_node = PDir("sun")
        self.sun_node.setColor(Vec4(1.1, 1.05, 0.95, 1))
        self.sun_np = render_np().attachNewNode(self.sun_node)
        self.sun_on = False

    # ------------------------------------------------------------------
    def add_fixture(self, fx):
        self.fixtures.append(fx)
        return fx

    def set_sun(self, direction, on=True):
        self.sun_np.lookAt(PVec3(direction[0], direction[1], direction[2]))
        if on and not self.sun_on:
            render_np().setLight(self.sun_np)
        elif not on and self.sun_on:
            render_np().clearLight(self.sun_np)
        self.sun_on = on

    def set_mode(self, mode):
        """'tps' : espace (soleil, peu de brouillard) ; 'fps' : intérieur sombre."""
        self.mode = mode
        if mode == "tps":
            self.amb_node.setColor(Vec4(.06, .065, .08, 1))
            scene.fog_color = color.rgb(0, 0, 0)
            scene.fog_density = C.FOG_DENSITY_TPS
            camera.clip_plane_far = 3000
        elif mode == "fps":
            self.set_sun((0, -1, 0), False)
            self._apply_ambient()
            scene.fog_color = color.rgb(*C.FOG_COLOR_FPS)
            scene.fog_density = C.FOG_DENSITY_FPS
            camera.clip_plane_far = 260
        elif mode == "menu":
            self.amb_node.setColor(Vec4(.05, .05, .07, 1))
            scene.fog_density = C.FOG_DENSITY_TPS
            camera.clip_plane_far = 3000

    def _apply_ambient(self):
        if self.nightvision:
            self.amb_node.setColor(Vec4(.55, .9, .55, 1))
        else:
            a = C.AMBIENT_FPS
            h = self.horror
            self.amb_node.setColor(Vec4(a[0] + .05 * h, a[1], a[2], 1))

    def set_nightvision(self, on):
        self.nightvision = on
        if self.mode == "fps":
            self._apply_ambient()
            scene.fog_density = C.FOG_DENSITY_FPS * (0.45 if on else 1.0)
            scene.fog_color = color.rgb(.02, .06, .02) if on else color.rgb(*C.FOG_COLOR_FPS)

    def muzzle_flash(self, pos):
        self.extra_flash = 1.0
        self.flash_np.setPos(pos[0], pos[1], pos[2])

    # ------------------------------------------------------------------
    def update(self, dt, cam_pos, horror=0.0):
        self.time += dt
        self.horror = horror
        t = self.time
        # flash de bouche
        if self.extra_flash > 0:
            self.extra_flash = max(0.0, self.extra_flash - dt * 14)
            f = self.extra_flash * 4.0
            self.flash_node.setColor(Vec4(f, f * .8, f * .5, 1))
        # lampe torche
        if self.flashlight_on and self.battery > 0 and self.mode == "fps":
            k = C.FLASHLIGHT_INTENSITY
            if self.battery < 15:  # batterie faible : clignotements
                if math.sin(t * 23) * math.sin(t * 7.1) > 0.6:
                    k *= 0.2
                k *= 0.5 + self.battery / 30
            c = C.FLASHLIGHT_COLOR
            if self.nightvision:
                k *= 0.4
            self.spot.setColor(Vec4(c[0] * k, c[1] * k, c[2] * k, 1))
        else:
            self.spot.setColor(Vec4(0, 0, 0, 1))
        if self.mode == "fps":
            self._apply_ambient()

        # choix des luminaires qui reçoivent une vraie lumière
        self._assign_timer -= dt
        cx, cy, cz = cam_pos
        if self._assign_timer <= 0:
            self._assign_timer = 0.2
            cands = []
            for fx in self.fixtures:
                dx, dy, dz = fx.pos[0] - cx, fx.pos[1] - cy, fx.pos[2] - cz
                d2 = dx * dx + dy * dy + dz * dz
                if d2 < (fx.radius + 22) ** 2:
                    cands.append((d2 / (fx.intensity + .01), fx))
            cands.sort(key=lambda c: c[0])
            chosen = [c[1] for c in cands[:len(self.pool)]]
            # garde les assignations existantes pour éviter les sauts
            current = {id(p[2]): p for p in self.pool if p[2] is not None}
            free = [p for p in self.pool if p[2] is None or p[2] not in chosen]
            for fx in chosen:
                if id(fx) in current and current[id(fx)][2] is fx:
                    continue
                if not free:
                    break
                slot = free.pop()
                slot[2] = fx
                slot[0].setPos(fx.pos[0], fx.pos[1], fx.pos[2])
                q = 9.0 / (fx.radius ** 2)
                slot[1].setAttenuation(PVec3(1, 0.05, q))
            for slot in free:
                slot[2] = None
                slot[1].setColor(Vec4(0, 0, 0, 1))
            self._visible = [fx for d, fx in cands[:40]]

        nv_boost = 2.6 if self.nightvision else 1.0
        # mise à jour des tubes émissifs proches + intensité des lumières du pool
        for fx in getattr(self, "_visible", ()):
            b = fx.compute(t, horror)
            r, g, bb = fx.current_color(horror)
            if fx.entity is not None:
                k = 0.15 + 0.85 * min(1.0, b)
                fx.entity.color = color.rgb(min(1, r * k * 1.1), min(1, g * k * 1.1), min(1, bb * k * 1.1))
        for slot in self.pool:
            fx = slot[2]
            if fx is None:
                continue
            b = fx.brightness * fx.intensity * nv_boost
            r, g, bb = fx.current_color(horror)
            slot[1].setColor(Vec4(r * b, g * b, bb * b, 1))

    def glare_amount(self, cam_pos, cam_forward):
        """Éblouissement en vision nocturne : luminaire allumé proche dans l'axe du regard."""
        best = 0.0
        cx, cy, cz = cam_pos
        fx_, fy_, fz_ = cam_forward
        for fx in getattr(self, "_visible", ()):
            if fx.brightness < 0.3:
                continue
            dx, dy, dz = fx.pos[0] - cx, fx.pos[1] - cy, fx.pos[2] - cz
            d = math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-4
            if d > 14:
                continue
            dot = (dx * fx_ + dy * fy_ + dz * fz_) / d
            if dot > 0.8:
                v = (dot - 0.8) / 0.2 * (1 - d / 14) * fx.brightness * fx.intensity
                best = max(best, v)
        return min(1.0, best)

    def destroy(self):
        r = render_np()
        for p in self.pool:
            r.clearLight(p[0])
            p[0].removeNode()
        for n in (self.amb, self.flash_np, self.spot_np, self.sun_np):
            r.clearLight(n)
            n.removeNode()
        self.fixtures.clear()


def render_np():
    """NodePath 'render' de Panda3D (scène 3D)."""
    return application.base.render
