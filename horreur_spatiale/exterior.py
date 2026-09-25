# -*- coding: utf-8 -*-
"""
exterior.py — Extérieur du grand vaisseau abandonné (phase TPS).

La coque enveloppe EXACTEMENT l'empreinte de l'intérieur généré : le
hangar extérieur est donc à la même position que le hangar intérieur
(flanc sud, z = 0). Autour : proue, bloc moteur, superstructure, antennes,
panneaux solaires arrachés, débris flottants qui tournent sur eux-mêmes,
balises clignotantes guidant vers l'ouverture du hangar.
"""
import math
import random

from panda3d.core import TransparencyAttrib
from ursina import Entity, Vec3, color, destroy, scene

import config as C
import textures
from geometry import MeshBuilder
from lighting import Fixture


# ----------------------------------------------------------------------------
# COLLISIONS
# ----------------------------------------------------------------------------
class AABBCollider:
    def __init__(self, x0, x1, y0, y1, z0, z1):
        self.b = (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1))
        self.c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        self.r = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) / 2

    def bound(self):
        return self.c, self.r

    def closest(self, p):
        b = self.b
        return Vec3(min(max(p.x, b[0]), b[1]), min(max(p.y, b[2]), b[3]), min(max(p.z, b[4]), b[5]))


class OBBCollider:
    """Boîte orientée : un nœud (cube unité mis à l'échelle), éventuellement mobile."""

    def __init__(self, node):
        self.node = node
        s = node.getScale(scene)
        self.r = math.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2) / 2

    def bound(self):
        p = self.node.getPos(scene)
        return (p[0], p[1], p[2]), self.r

    def closest(self, p):
        lp = self.node.getRelativePoint(scene, p)
        cl = Vec3(min(max(lp[0], -.5), .5), min(max(lp[1], -.5), .5), min(max(lp[2], -.5), .5))
        w = scene.getRelativePoint(self.node, cl)
        return Vec3(w[0], w[1], w[2])


# ----------------------------------------------------------------------------
class ExteriorShip:
    def __init__(self, game, level, lights, parent, seed):
        self.game = game
        self.level = level
        self.lights = lights
        self.rng = random.Random(seed * 17 + 5)
        self.root = Entity(parent=parent, name='exterior')
        self.colliders = []
        self.debris = []
        self.beacons = []
        self.blinkers = []
        self.fixtures = []
        self.t = 0.0
        Cc = C.CELL
        self.W = level.W * Cc
        self.D = level.H * Cc
        self.T = 1.4                       # épaisseur de coque
        self.top = 12.5
        self.bottom = -2.5
        ox, ow = level.hangar_opening
        self.open_x0 = ox * Cc
        self.open_x1 = (ox + ow) * Cc
        self.open_h = C.HANGAR_OPENING_HEIGHT
        hangar = level.room("hangar")
        hx0, hx1, hz0, hz1 = hangar.world_bounds()
        self.hangar_bounds = (hx0, hx1, hz0, hz1)
        self.entrance = Vec3((self.open_x0 + self.open_x1) / 2, self.open_h / 2, -30)
        self.mb = MeshBuilder(uv_scale=12)      # coque
        self.gm = MeshBuilder(uv_scale=3)       # détails (texture panneaux)
        self.em = MeshBuilder()                 # émissifs
        self._hull()
        self._greebles()
        self._superstructure()
        self._engines_and_bow()
        self._antennas()
        self._solar_panels()
        self._window_lights()
        self._hangar_frame()
        self.mb.build(parent=self.root, material='hullplates', name='hull')
        self.gm.build(parent=self.root, material='panel', name='greebles')
        self.em.build(parent=self.root, unlit=True, name='hull_lights')
        self._debris()
        self._beacons()
        self._hangar_colliders()

    # ------------------------------------------------------------------
    def _solid(self, x0, x1, y0, y1, z0, z1, col=(.55, .55, .55), mb=None, collide=True, faces='all'):
        (mb or self.mb).box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), col,
                            faces=faces)
        if collide:
            self.colliders.append(AABBCollider(x0, x1, y0, y1, z0, z1))

    def _hull(self):
        W, D, T = self.W, self.D, self.T
        top, bot = self.top, self.bottom
        c = (.5, .5, .52)
        # dessus / dessous
        self._solid(-T, W + T, top, top + T, -T, D + T, c)
        self._solid(-T, W + T, bot - T, bot, -T, D + T, c)
        # flancs est / ouest / nord
        self._solid(-T, 0, bot, top, -T, D + T, c)
        self._solid(W, W + T, bot, top, -T, D + T, c)
        self._solid(0, W, bot, top, D, D + T, c)
        # flanc sud avec l'ouverture du hangar
        x0, x1, oh = self.open_x0, self.open_x1, self.open_h
        self._solid(0, x0, bot, top, -T, 0, c)
        self._solid(x1, W, bot, top, -T, 0, c)
        self._solid(x0, x1, oh, top, -T, 0, c)
        self._solid(x0, x1, bot, 0, -T, 0, c)

    def _greebles(self):
        """Détails de coque : panneaux, conduites, radiateurs, réservoirs."""
        rng = self.rng
        W, D, T = self.W, self.D, self.T
        top = self.top + T
        for _ in range(140):
            w, d, h = rng.uniform(2, 9), rng.uniform(2, 9), rng.uniform(.3, 2.2)
            x, z = rng.uniform(2, W - 2), rng.uniform(2, D - 2)
            col = rng.choice([(.45, .45, .47), (.38, .37, .36), (.55, .53, .5), (.3, .32, .33)])
            self._solid(x - w / 2, x + w / 2, top, top + h, z - d / 2, z + d / 2, col, self.gm, collide=h > 1)
        # conduites le long des flancs
        for side_z in (-T, D + T):
            s = -1 if side_z < 0 else 1
            for k in range(4):
                y = self.bottom + 2 + k * 3.3
                if s < 0 and y < self.open_h + 1 and y > -1:
                    # pas devant l'ouverture : deux tronçons
                    self.gm.cylinder((self.open_x0 / 2, y, side_z + s * .5), .4, self.open_x0 - 2, (.4, .35, .3), 8,
                                     'x')
                    ln = self.W - self.open_x1
                    self.gm.cylinder((self.open_x1 + ln / 2, y, side_z + s * .5), .4, ln - 2, (.4, .35, .3), 8, 'x')
                else:
                    self.gm.cylinder((W / 2, y, side_z + s * .5), .4, W - 4, (.4, .35, .3), 8, 'x')
        # réservoirs sphériques-ish sur le dessous
        for k in range(5):
            x = W * (k + .5) / 5
            self.gm.cylinder((x, self.bottom - T - 2, D / 2), 3, 8, (.45, .44, .42), 14, 'z')
            self.colliders.append(AABBCollider(x - 3, x + 3, self.bottom - T - 5, self.bottom - T + 1, D / 2 - 4,
                                               D / 2 + 4))

    def _superstructure(self):
        """Tour de commandement au-dessus de la salle de commandement + épine dorsale."""
        rng = self.rng
        cmd = self.level.room("command")
        top = self.top + self.T
        x0, x1, z0, z1 = cmd.world_bounds()
        self._solid(x0 + 1, x1 - 1, top, top + 9, z0 + 2, z1 - 1, (.5, .5, .52))
        self._solid(x0 + 3, x1 - 3, top + 9, top + 13, z0 + 4, z1 - 3, (.46, .46, .48))
        # bandeau de vitres éclairées de la tour
        for k in range(8):
            x = x0 + 2 + (x1 - x0 - 4) * (k + .5) / 8
            if rng.random() < .6:
                self.em.box((x, top + 6.5, z0 + 1.95), (1.2, .8, .05), (.35, .5, .6) if rng.random() < .7 else
                            (.8, .6, .3))
        # épine dorsale
        self._solid(4, self.W - 4, top + 1, top + 4, self.D / 2 - 3, self.D / 2 + 3, (.42, .42, .44))
        # ailettes de radiateurs (sombres)
        for k in range(10):
            x = 8 + k * (self.W - 16) / 9
            self._solid(x - .3, x + .3, top + 4, top + 10, self.D / 2 - 5, self.D / 2 + 5, (.2, .2, .22), self.gm)

    def _engines_and_bow(self):
        W, D, T = self.W, self.D, self.T
        bot, top = self.bottom - T, self.top + T
        # bloc moteur à l'est
        self._solid(W + T, W + 30, bot + 2, top - 2, 6, D - 6, (.4, .4, .42))
        for k in range(3):
            z = D * (k + 1) / 4
            y = (bot + top) / 2
            self.mb.cylinder((W + 38, y, z), 6.5, 16, (.3, .3, .32), 18, 'x')
            self.em.cylinder((W + 46.2, y, z), 5, .1, (.25, .08, .04), 18, 'x')    # tuyère éteinte (lueur)
            self.colliders.append(AABBCollider(W + 30, W + 46, y - 6.5, y + 6.5, z - 6.5, z + 6.5))
        # proue à l'ouest : étages de plus en plus étroits
        for k in range(4):
            w = 22 - k * 5
            x1 = -T - k * 8
            x0 = x1 - 8
            m = D / 2
            hh = (top - bot) / 2 - k * 2
            yc = (top + bot) / 2
            self._solid(x0, x1, yc - hh, yc + hh, m - w - k * 0, m + w, (.5, .5, .52))

    def _antennas(self):
        rng = self.rng
        top = self.top + self.T
        for _ in range(9):
            x = rng.uniform(5, self.W - 5)
            z = rng.uniform(5, self.D - 5)
            h = rng.uniform(12, 32)
            self._solid(x - .25, x + .25, top, top + h, z - .25, z + .25, (.6, .6, .6), self.gm)
            for k in range(rng.randint(1, 3)):
                y = top + h * rng.uniform(.4, .9)
                ln = rng.uniform(3, 8)
                self._solid(x - ln / 2, x + ln / 2, y - .1, y + .1, z - .1, z + .1, (.55, .55, .55), self.gm)
            e = Entity(parent=self.root, model='sphere', color=color.red, scale=.6, position=(x, top + h + .3, z),
                       unlit=True)
            self.blinkers.append((e, rng.uniform(0, 3), color.red))
        # grandes antennes latérales qui dépassent au sud et au nord
        for side in (-1, 1):
            for k in range(2):
                x = self.W * (.2 + .6 * k) + rng.uniform(-6, 6)
                if side < 0 and self.open_x0 - 8 < x < self.open_x1 + 8:
                    x += 25
                z0 = -self.T if side < 0 else self.D + self.T
                ln = rng.uniform(18, 30)
                y = rng.uniform(2, 9)
                zc = z0 + side * ln / 2
                self._solid(x - .3, x + .3, y - .3, y + .3, zc - ln / 2, zc + ln / 2, (.6, .6, .6), self.gm)
                e = Entity(parent=self.root, model='sphere', color=color.red, scale=.5,
                           position=(x, y, z0 + side * ln), unlit=True)
                self.blinkers.append((e, rng.uniform(0, 3), color.red))
        # parabole de communication
        x, z = self.W * .3, self.D * .7
        dish = Entity(parent=self.root, model='sphere', texture=textures.get('panel'), color=color.rgb(.6, .6, .62),
                      scale=(9, 2, 9), position=(x, top + 10, z), rotation=(30, 40, 0))
        self._solid(x - .4, x + .4, top, top + 10, z - .4, z + .4, (.5, .5, .5), self.gm)
        self.colliders.append(OBBCollider(dish))

    def _solar_panels(self):
        """Panneaux solaires sur bras, certains arrachés et de travers."""
        rng = self.rng
        for side in (-1, 1):
            for k in range(3):
                x = self.W * (k + .5) / 3
                if side < 0 and self.open_x0 - 12 < x < self.open_x1 + 12:
                    continue
                z_base = -self.T if side < 0 else self.D + self.T
                y = self.top - 3
                arm = 10
                zc = z_base + side * arm / 2
                self._solid(x - .5, x + .5, y - .5, y + .5, zc - arm / 2, zc + arm / 2, (.4, .4, .42), self.gm)
                broken = rng.random() < .55
                pz = z_base + side * (arm + 7)
                yaw = rng.uniform(-35, 35) if broken else 0
                pitch = rng.uniform(-50, 50) if broken else 0
                roll = rng.uniform(-30, 30) if broken else 0
                panel = Entity(parent=self.root, model='cube', texture=textures.get('panel'),
                               color=color.rgb(.12, .16, .3), position=(x + (rng.uniform(-4, 4) if broken else 0),
                                                                        y + (rng.uniform(-5, 3) if broken else 0), pz),
                               scale=(16, .25, 12), rotation=(pitch, yaw, roll))
                self.colliders.append(OBBCollider(panel))

    def _window_lights(self):
        """Lumières des hublots sur la coque, aux positions des fenêtres intérieures."""
        rng = self.rng
        Cc = C.CELL
        for key, kind in self.level.windows.items():
            if kind == "opening":
                continue
            a, i, j = key
            lit = rng.random() < .55
            col = rng.choice([(.5, .6, .7), (.7, .55, .3), (.6, .1, .08)]) if lit else (.04, .05, .06)
            if kind == "bay":
                y0, y1 = .55, C.ROOM_HEIGHT + .25
                w = Cc - .2
            else:
                y0, y1 = 1.1, 2.05
                w = 1.0
            yc = (y0 + y1) / 2
            if a == "x":
                x = (i + 1) * Cc
                x = -self.T - .02 if x <= 0 else self.W + self.T + .02
                z = (j + .5) * Cc
                self.em.box((x, yc, z), (.05, y1 - y0, w), col)
            else:
                z = (j + 1) * Cc
                z = -self.T - .02 if z <= 0 else self.D + self.T + .02
                x = (i + .5) * Cc
                self.em.box((x, yc, z), (w, y1 - y0, .05), col)

    def _hangar_frame(self):
        """Cadre de l'ouverture du hangar : bandes de danger + projecteurs."""
        x0, x1, oh = self.open_x0, self.open_x1, self.open_h
        T = self.T
        hz = MeshBuilder(uv_scale=1)
        for (a0, a1, b0, b1) in ((x0 - 1, x0, 0, oh + 1), (x1, x1 + 1, 0, oh + 1), (x0 - 1, x1 + 1, oh, oh + 1)):
            hz.box(((a0 + a1) / 2, (b0 + b1) / 2, -T - .15), (a1 - a0, b1 - b0, .3), (1, 1, 1))
        hz.build(parent=self.root, texture=textures.get('hazard'), material='painted', name='hangar_frame')
        # parois intérieures du tunnel d'entrée
        self.gm.box((x0 + .05, oh / 2, -T / 2), (.1, oh, T), (.35, .35, .37), faces='e')
        self.gm.box((x1 - .05, oh / 2, -T / 2), (.1, oh, T), (.35, .35, .37), faces='w')
        self.gm.box(((x0 + x1) / 2, oh - .05, -T / 2), (x1 - x0, .1, T), (.35, .35, .37), faces='b')
        self.gm.box(((x0 + x1) / 2, .0, -T / 2), (x1 - x0, 0, T), (.3, .3, .32), faces='t')
        # champ de force lumineux (visuel) dans l'ouverture
        ff = Entity(parent=self.root, model='quad', texture=textures.get('forcefield'),
                    position=((x0 + x1) / 2, oh / 2, -.05), scale=(x1 - x0, oh), double_sided=True, unlit=True)
        ff.setTransparency(TransparencyAttrib.MAlpha)
        ff.setDepthWrite(False)
        self.forcefield = ff
        # projecteurs extérieurs au-dessus de l'ouverture (vraies lumières)
        for x in (x0 + 2, (x0 + x1) / 2, x1 - 2):
            e = Entity(parent=self.root, model='cube', color=color.rgb(1, .9, .7), scale=(1, .3, .3),
                       position=(x, oh + 1.5, -T - .4), unlit=True)
            fx = self.lights.add_fixture(Fixture((x, oh + 1, -T - 3), (1, .9, .75), 22, "steady", e, 1.6))
            self.fixtures.append(fx)

    def _beacons(self):
        """Balises lumineuses clignotantes qui guident vers l'ouverture."""
        x0, x1, oh = self.open_x0, self.open_x1, self.open_h
        cx = (x0 + x1) / 2
        pts = []
        for y in (0.5, oh - .5):
            for x in (x0 - .5, x1 + .5):
                pts.append(((x, y, -self.T - .6), 0))
        # bouées flottantes formant un couloir d'approche
        for k in range(1, 6):
            z = -self.T - k * 12
            for s in (-1, 1):
                pts.append(((cx + s * (x1 - x0) / 2 + s * k * .8, oh / 2 + math.sin(k) * 1.5, z), k))
        for (pos, order) in pts:
            col = color.rgb(1, .15, .1) if pos[0] < cx else color.rgb(.1, 1, .3)
            core = Entity(parent=self.root, model='sphere', color=col, scale=.7, position=pos, unlit=True)
            halo = Entity(parent=self.root, model='quad', texture=textures.get('glow'), color=col, scale=5,
                          position=pos, billboard=True, unlit=True)
            halo.setTransparency(TransparencyAttrib.MAlpha)
            halo.setDepthWrite(False)
            self.beacons.append((core, halo, order, col))
            if order <= 1:
                fx = self.lights.add_fixture(Fixture(pos, (col.r, col.g, col.b), 16, "steady", None, 1.3))
                self.fixtures.append(fx)
        # lumière d'ambiance à l'intérieur du hangar, visible de loin
        self.hangar_glow = self.lights.add_fixture(Fixture((cx, 5, 8), (.6, .75, 1.0), 25, "steady", None, 1.2))
        self.fixtures.append(self.hangar_glow)

    def _debris(self):
        """Débris flottants (plaques, poutres, conteneurs) qui tournent lentement."""
        rng = self.rng
        W, D = self.W, self.D
        cx = (self.open_x0 + self.open_x1) / 2
        for k in range(C.DEBRIS_COUNT):
            r = rng.random()
            if r < .45:
                # concentrés sur l'approche du hangar (sud)
                pos = Vec3(cx + rng.uniform(-45, 45), rng.uniform(-8, 22), rng.uniform(-90, -10))
            elif r < .75:
                # autour du vaisseau
                a = rng.uniform(0, 2 * math.pi)
                d = rng.uniform(15, 70)
                pos = Vec3(W / 2 + math.cos(a) * (W / 2 + d), rng.uniform(-20, 35), D / 2 + math.sin(a) * (D / 2 + d))
            else:
                # sur le chemin depuis le point de départ (nord)
                pos = Vec3(rng.uniform(-20, W + 20), rng.uniform(-10, 30), D + rng.uniform(15, 110))
            # ne pas boucher l'ouverture
            if abs(pos.x - cx) < 10 and -18 < pos.z < 2 and -2 < pos.y < 12:
                pos.z -= 20
            kind = rng.random()
            if kind < .4:
                sc = Vec3(rng.uniform(2, 6), rng.uniform(.2, .5), rng.uniform(2, 5))       # plaque de coque
                col = color.rgb(.5, .5, .5)
            elif kind < .7:
                sc = Vec3(rng.uniform(.4, .8), rng.uniform(.4, .8), rng.uniform(5, 12))    # poutre
                col = color.rgb(.35, .33, .3)
            else:
                s = rng.uniform(1.5, 3.5)
                sc = Vec3(s * 1.6, s, s)                                                  # conteneur
                col = rng.choice([color.rgb(.5, .25, .1), color.rgb(.2, .3, .45), color.rgb(.45, .42, .15)])
            e = Entity(parent=self.root, model='cube', texture=textures.get('hull'), color=col, position=pos,
                       scale=sc, rotation=(rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360)))
            spin = Vec3(rng.uniform(-12, 12), rng.uniform(-12, 12), rng.uniform(-12, 12))
            drift = Vec3(rng.uniform(-.3, .3), rng.uniform(-.15, .15), rng.uniform(-.3, .3))
            self.debris.append([e, spin, drift, Vec3(pos), rng.uniform(0, 6.28)])
            self.colliders.append(OBBCollider(e))

    def _hangar_colliders(self):
        """Parois intérieures du hangar (pour la navette en phase TPS)."""
        hx0, hx1, hz0, hz1 = self.hangar_bounds
        H = C.HANGAR_HEIGHT
        self.colliders.append(AABBCollider(hx0, hx1, -2, 0, hz0, hz1))
        self.colliders.append(AABBCollider(hx0, hx1, H, H + 2, hz0, hz1))
        self.colliders.append(AABBCollider(hx0 - 2, hx0, 0, H, hz0, hz1))
        self.colliders.append(AABBCollider(hx1, hx1 + 2, 0, H, hz0, hz1))
        self.colliders.append(AABBCollider(hx0, hx1, 0, H, hz1, hz1 + 2))

    # ------------------------------------------------------------------
    def in_hangar_entrance(self, p):
        """La navette a-t-elle franchi l'ouverture du hangar ?"""
        return (self.open_x0 + 1 < p.x < self.open_x1 - 1 and .5 < p.y < self.open_h + 1.5
                and 1.5 < p.z < self.hangar_bounds[3] - 3)

    def update(self, dt):
        self.t += dt
        t = self.t
        for d in self.debris:
            e, spin, drift, home, ph = d
            e.rotation += spin * dt
            e.position = home + drift * math.sin(t * .1 + ph) * 8
        for e, ph, col in self.blinkers:
            on = ((t + ph) % 1.6) < .25
            e.color = col if on else color.rgb(.15, .02, .02)
        # balises : séquence "piste" qui court vers l'ouverture
        for core, halo, order, col in self.beacons:
            phase = (t * 2.2 - order * .35) % 2.0
            on = phase < .5 or order == 0
            k = 1.0 if on else .12
            core.color = color.rgb(col.r * k, col.g * k, col.b * k)
            halo.color = color.rgba(col.r, col.g, col.b, .8 * k)
        self.forcefield.texture_offset = (0, (t * .1) % 1)

    def set_enabled(self, on):
        self.root.enabled = on
        for fx in self.fixtures:
            fx.active = on

    def destroy(self):
        destroy(self.root)
