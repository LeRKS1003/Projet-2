# -*- coding: utf-8 -*-
"""
lighting.py — Éclairage et ambiance visuelle.

  * éclairage PAR PIXEL (shader automatique de Panda3D, activé dans main.py) ;
  * lumière ambiante très faible + brouillard sombre (FPS) : la lampe est
    indispensable, mais les noirs ne sont jamais totalement opaques ;
  * lampe torche réaliste (classe Flashlight) : vrai Spotlight fixé sous
    l'arme, orientation lissée (léger retard), atténuation physique réglable,
    masque projeté « cookie » (anneaux d'une optique LED), ombres portées
    dynamiques, cône volumétrique additif + poussière dans le faisceau,
    couleur réglable en kelvins, comportement lié à la batterie (baisse,
    scintillement, extinction, « tape » pour la rallumer brièvement) ;
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
                          DirectionalLight as PDir, PerspectiveLens, Vec4, Vec3 as PVec3, BitMask32,
                          TextureStage, Texture as PTexture, TexGenAttrib, ColorBlendAttrib, Quat)
from ursina import camera, color, scene, Entity, Mesh, destroy
from ursina import application

import config as C
import textures
from geometry import MeshBuilder

# bit du masque de caméra utilisé par la caméra d'ombre de la lampe : les
# effets translucides (cône, poussière, halos) s'en cachent pour ne pas
# projeter d'ombre.
SHADOW_MASK = BitMask32.bit(3)


def additive(np_, bin_sort=5):
    """Mélange additif (lueurs, flammes, halos) sans écriture de profondeur."""
    np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                        ColorBlendAttrib.OOne))
    np_.setDepthWrite(False)
    np_.setBin('fixed', bin_sort)
    np_.setLightOff(2)
    np_.hide(SHADOW_MASK)


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


class Flashlight:
    """Lampe torche : spot + cookie + ombres + cône volumétrique + poussière."""

    def __init__(self, world_root):
        q = C.quality()
        self.q = q
        r = render_np()
        # le « rig » suit la caméra ; son orientation est lissée (retard naturel)
        self.rig = r.attachNewNode("flashlight_rig")
        self.spot = PSpot("flashlight")
        lens = PerspectiveLens()
        lens.setFov(C.FLASHLIGHT_FOV)
        lens.setNearFar(0.15, C.FLASHLIGHT_RANGE)
        self.spot.setLens(lens)
        self.spot.setExponent(C.FLASHLIGHT_EXPONENT)
        self.spot.setAttenuation(PVec3(*C.FLASHLIGHT_ATTENUATION))
        self.spot.setColor(Vec4(0, 0, 0, 1))
        self.spot.setCameraMask(SHADOW_MASK)
        if q["shadows"]:
            # ombres portées : la lampe rend une carte de profondeur à chaque image
            self.spot.setShadowCaster(True, q["shadow_size"], q["shadow_size"])
        self.np = self.rig.attachNewNode(self.spot)
        r.setLight(self.np)
        # masque projeté (« cookie ») : anneaux LED et bords doux
        self.cookie_root = None
        if q["cookie"] and world_root is not None:
            tex = textures.get('cookie')._texture
            tex.setWrapU(PTexture.WM_border_color)
            tex.setWrapV(PTexture.WM_border_color)
            tex.setBorderColor(Vec4(1, 1, 1, 1))
            self.cookie_stage = TextureStage("flash_cookie")
            self.cookie_stage.setMode(TextureStage.MModulate)
            self.cookie_stage.setSort(40)
            world_root.projectTexture(self.cookie_stage, tex, self.np)
            self.cookie_root = world_root
        # cône volumétrique : trois coques emboîtées, plus denses au centre
        self.cone = None
        if q["volumetric"]:
            L = 9.0
            mb = MeshBuilder()
            half = math.radians(C.FLASHLIGHT_FOV / 2)
            for k, (rk, a) in enumerate(((1.0, .006), (.62, .01), (.32, .016))):
                R = math.tan(half) * L * rk
                seg = 18
                for s in range(seg):
                    a0 = 2 * math.pi * s / seg
                    a1 = 2 * math.pi * (s + 1) / seg
                    p0 = (math.cos(a0) * R, math.sin(a0) * R, L)
                    p1 = (math.cos(a1) * R, math.sin(a1) * R, L)
                    b0 = mb.count
                    for p, al in (((0, 0, .05), a), (p0, 0.0), (p1, 0.0)):
                        mb.v.extend(p)
                        mb.n.extend((0, 0, 1))
                        mb.c.extend((1, 1, 1, al))
                        mb.t.extend((0, 0))
                    mb.i.extend((b0, b0 + 1, b0 + 2))
                    mb.count += 3
            self.cone = mb.build(name="flash_cone", tangents=False)
            self.cone.reparentTo(self.rig)
            self.cone.setTwoSided(True)
            additive(self.cone, 4)
        # poussière qui flotte dans le faisceau (sprites ponctuels)
        self.dust = None
        self.dust_n = q["dust"]
        if self.dust_n:
            rnd = random.Random(7)
            self.dust_pts = [[rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(.6, 7.5), rnd.uniform(0, 6.28)]
                             for _ in range(self.dust_n)]
            self.dust_mesh = Mesh(vertices=[(0, 0, 0)] * self.dust_n, colors=[color.clear] * self.dust_n,
                                  mode='point', thickness=.018, render_points_in_3d=True, static=False)
            self.dust = Entity(model=self.dust_mesh, name="flash_dust")
            self.dust.reparentTo(self.rig)
            self.dust.setTexture(textures.get('dust')._texture)
            self.dust.setTexGen(TextureStage.getDefault(), TexGenAttrib.MPointSprite)
            additive(self.dust, 6)
            self._dust_tick = 0
        self.cur_quat = None
        self.level = 0.0            # intensité effective 0..1 (lissée)
        self.flick = 1.0
        self.flick_timer = 0.0
        self.tap_timer = 0.0

    # ------------------------------------------------------------------
    def tap(self):
        """Taper sur la lampe : répit de quelques secondes quand elle faiblit."""
        self.tap_timer = C.FLASHLIGHT_TAP_TIME

    def battery_factor(self, battery, dt):
        """Intensité relative selon la batterie (baisse, puis scintillement irrégulier)."""
        if self.tap_timer > 0:
            return max(.6, min(1.0, battery / C.FLASHLIGHT_LOW)) if battery > 0 else .55
        if battery <= 0:
            return 0.0
        if battery > C.FLASHLIGHT_LOW:
            return 1.0
        if battery > C.FLASHLIGHT_FLICKER:
            return .45 + .55 * (battery - C.FLASHLIGHT_FLICKER) / (C.FLASHLIGHT_LOW - C.FLASHLIGHT_FLICKER)
        # sous le seuil : coupures et sursauts aléatoires
        self.flick_timer -= dt
        if self.flick_timer <= 0:
            r = random.random()
            if r < .25:
                self.flick, self.flick_timer = .03, random.uniform(.04, .25)
            elif r < .45:
                self.flick, self.flick_timer = .2, random.uniform(.03, .12)
            else:
                self.flick, self.flick_timer = random.uniform(.35, .5), random.uniform(.1, .6)
        return self.flick

    @property
    def flickering(self):
        return self.tap_timer <= 0 and 0 < self.level < .55

    def update(self, dt, on, battery, nightvision, fog_density):
        self.tap_timer = max(0.0, self.tap_timer - dt)
        # position : sous et à droite de l'œil (lampe fixée sur l'arme)
        cam = camera
        ox, oy, oz = C.FLASHLIGHT_OFFSET
        p = cam.world_position + cam.right * ox + cam.up * oy + cam.forward * oz
        self.rig.setPos(p.x, p.y, p.z)
        # orientation : suit la vue avec un léger retard
        target = cam.getQuat(render_np())
        if self.cur_quat is None:
            self.cur_quat = Quat(target)
        k = 1 - math.exp(-C.FLASHLIGHT_LAG * dt)
        a, b = self.cur_quat, target
        if a.dot(b) < 0:
            b = Quat(-b[0], -b[1], -b[2], -b[3])
        qn = Quat(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k,
                  a[3] + (b[3] - a[3]) * k)
        qn.normalize()
        self.cur_quat = qn
        self.rig.setQuat(qn)
        # intensité
        lit = (on or self.tap_timer > 0)
        target_level = self.battery_factor(battery, dt) if lit else 0.0
        # montée / descente douce (sauf coupures du scintillement)
        self.level += (target_level - self.level) * min(1, dt * 25)
        kk = C.FLASHLIGHT_INTENSITY * self.level * (.4 if nightvision else 1.0)
        c = C.FLASHLIGHT_COLOR
        self.spot.setColor(Vec4(c[0] * kk, c[1] * kk, c[2] * kk, 1))
        vol = self.level * (1.0 + fog_density * 8)
        if self.cone is not None:
            self.cone.enabled = self.level > .02
            self.cone.setColorScale(c[0] * vol, c[1] * vol, c[2] * vol, 1)
        if self.dust is not None:
            self.dust.enabled = self.level > .02
            self._dust_tick += 1
            if self.dust.enabled and self._dust_tick % 2 == 0:
                self._update_dust(dt * 2, vol)

    def _update_dust(self, dt, vol):
        tan = math.tan(math.radians(C.FLASHLIGHT_FOV / 2))
        verts, cols = [], []
        t = time_now()
        for pnt in self.dust_pts:
            pnt[0] += math.sin(t * .3 + pnt[3]) * dt * .05
            pnt[1] += (math.cos(t * .23 + pnt[3] * 1.7) * .04 - .01) * dt
            pnt[2] += math.sin(t * .17 + pnt[3] * .5) * dt * .08
            if abs(pnt[0]) > 1 or abs(pnt[1]) > 1:
                pnt[0], pnt[1] = random.uniform(-.8, .8), random.uniform(-.8, .8)
            z = pnt[2]
            R = tan * z
            verts.append((pnt[0] * R, pnt[1] * R, z))
            rr = math.sqrt(pnt[0] ** 2 + pnt[1] ** 2)
            a = max(0.0, 1 - rr) ** 1.5 * max(0.0, 1 - z / 8) * min(1, z) * .55 * vol
            cols.append(color.rgba(1, 1, 1, min(1, a)))
        self.dust_mesh.vertices = verts
        self.dust_mesh.colors = cols
        self.dust_mesh.generate()

    def destroy(self):
        r = render_np()
        if self.cookie_root is not None:
            try:
                self.cookie_root.clearProjectTexture(self.cookie_stage)
            except Exception:
                pass
        r.clearLight(self.np)
        if self.dust is not None:
            destroy(self.dust)
        self.rig.removeNode()


_CLOCK = [0.0]      # horloge partagée (animée par LightManager.update)


def time_now():
    return _CLOCK[0]


class LightManager:
    def __init__(self, root, postfx=None):
        self.root = root
        self.postfx = postfx
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
        self._visible = []

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

        # lumière du flash de bouche (très brève)
        self.flash_node = PPoint("muzzle")
        self.flash_node.setColor(Vec4(0, 0, 0, 1))
        self.flash_node.setAttenuation(PVec3(1, 0.1, 0.22))
        self.flash_np = render_np().attachNewNode(self.flash_node)
        render_np().setLight(self.flash_np)

        # lampe torche
        self.flashlight = Flashlight(root)

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
            # sans correction gamma (qualité Haute), un peu plus d'ambiante
            g = 1.0 if (self.postfx is None or self.postfx.gamma_active or not self.postfx.filters) else 1.35
            self.amb_node.setColor(Vec4((a[0] + .05 * h) * g, a[1] * g, a[2] * g, 1))

    def set_nightvision(self, on):
        self.nightvision = on
        if self.mode == "fps":
            self._apply_ambient()
            scene.fog_density = C.FOG_DENSITY_FPS * (0.45 if on else 1.0)
            scene.fog_color = color.rgb(.02, .06, .02) if on else color.rgb(*C.FOG_COLOR_FPS)

    def muzzle_flash(self, pos):
        self.extra_flash = 1.0
        self.flash_np.setPos(pos[0], pos[1], pos[2])

    def tap_flashlight(self):
        self.flashlight.tap()

    @property
    def flashlight_level(self):
        return self.flashlight.level

    # ------------------------------------------------------------------
    def update(self, dt, cam_pos, horror=0.0):
        self.time += dt
        self.horror = horror
        t = self.time
        _CLOCK[0] = t
        # flash de bouche
        if self.extra_flash > 0:
            self.extra_flash = max(0.0, self.extra_flash - dt * 14)
            f = self.extra_flash * 4.0
            self.flash_node.setColor(Vec4(f, f * .8, f * .5, 1))
        # lampe torche
        fps = self.mode == "fps"
        self.flashlight.update(dt, self.flashlight_on and fps, self.battery, self.nightvision,
                               scene.fog_density if fps else 0)
        if fps:
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
        for fx in self._visible:
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
        if self.postfx is not None:
            self._update_viewmodel_lights(cam_pos)

    def _update_viewmodel_lights(self, cam_pos):
        """
        L'arme vit dans sa propre couche (postfx.vm_root) : on y reproduit
        l'éclairage du décor autour du joueur (ambiante, luminaire le plus
        influent, lampe torche, flash de bouche).
        """
        pf = self.postfx
        a = self.amb_node.getColor()
        # l'arme doit rester lisible : ambiante de base + reflet de l'ambiante du décor
        pf.vm_amb.setColor(Vec4(a[0] * 1.8 + .07, a[1] * 1.8 + .07, a[2] * 1.8 + .08, 1))
        # luminaire le plus influent -> lumière directionnelle clé
        best, best_c, best_dir = 0.0, None, None
        cx, cy, cz = cam_pos
        for np_, pl, fx in self.pool:
            if fx is None:
                continue
            col = pl.getColor()
            dx, dy, dz = fx.pos[0] - cx, fx.pos[1] - cy, fx.pos[2] - cz
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            q = 9.0 / (fx.radius ** 2)
            att = 1.0 / (1 + .05 * d + q * d * d)
            lum = (col[0] + col[1] + col[2]) * att
            if lum > best:
                best, best_c, best_dir = lum, (col[0] * att, col[1] * att, col[2] * att), (dx, dy, dz)
        if best_c is not None:
            pf.vm_key.setColor(Vec4(min(2, best_c[0]), min(2, best_c[1]), min(2, best_c[2]), 1))
            rel = camera.getRelativeVector(render_np(), PVec3(*best_dir))
            pf.vm_key_np.lookAt(-rel)
        else:
            pf.vm_key.setColor(Vec4(0, 0, 0, 1))
        k = self.flashlight.level * (1.3 if not self.nightvision else .5)
        c = C.FLASHLIGHT_COLOR
        pf.vm_lamp.setColor(Vec4(c[0] * k, c[1] * k, c[2] * k, 1))
        f = self.extra_flash * 3.0
        pf.vm_flash.setColor(Vec4(f, f * .8, f * .5, 1))

    def glare_amount(self, cam_pos, cam_forward):
        """Éblouissement en vision nocturne : luminaire allumé proche dans l'axe du regard."""
        best = 0.0
        cx, cy, cz = cam_pos
        fx_, fy_, fz_ = cam_forward
        for fx in self._visible:
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
        for n in (self.amb, self.flash_np, self.sun_np):
            r.clearLight(n)
            n.removeNode()
        self.flashlight.destroy()
        self.fixtures.clear()
        if self.postfx is not None:
            self.postfx.vm_key.setColor(Vec4(0, 0, 0, 1))
            self.postfx.vm_lamp.setColor(Vec4(0, 0, 0, 1))
            self.postfx.vm_flash.setColor(Vec4(0, 0, 0, 1))


def render_np():
    """NodePath 'render' de Panda3D (scène 3D)."""
    return application.base.render
