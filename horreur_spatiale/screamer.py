# -*- coding: utf-8 -*-
"""
screamer.py — Le casier piégé (jumpscare), une seule fois par partie.

Placement : au lancement, un casier est tiré avec la seed parmi tous les
casiers du vaisseau, sauf ceux du hangar. S'il se trouve dans la première
salle que le joueur visite, il est déplacé vers un autre casier (le joueur
ne doit pas tomber dessus trop tôt). Rien ne le distingue des autres.

Déroulement (à l'ouverture du casier) :
  0,0 s  le casier s'ouvre normalement ; silence total, tout se coupe ;
  0,5 s  une créature jaillit vers la caméra (visage déformé : bouche
         béante pleine de dents, yeux blancs lumineux, peau grise) et
         remplit l'écran en 0,2 s : cri strident + stinger de cordes,
         flash blanc d'une image, tremblement violent, vibration maximale,
         la lampe clignote puis s'éteint une seconde ;
  0,8 s  la créature disparaît dans un conduit en griffant le métal ;
  2 s    la lampe se rallume, le cœur bat fort (son + vibrations pulsées),
         musique angoissante 20-30 s qui retombe vers l'ambiance normale.
Le casier contient ensuite un bon loot. Aucun dégât : c'est seulement pour
faire peur.
"""
import math
import random

from panda3d.core import PointLight, AmbientLight, Vec4, Vec3 as PVec3, NodePath, TransparencyAttrib
from ursina import color

import config as C
import textures
from geometry import MeshBuilder
from lighting import mark_emissive, additive

JUMP_T = 0.5        # instant où la créature jaillit
GROW = 0.2          # durée pour remplir l'écran
HOLD = 0.13
LAMP_OFF = (0.95, 1.95)
END_T = 9.0


def _skin(rng):
    """Peau grise, cireuse, veinée (albédo, relief, rugosité)."""
    import numpy as np
    from creature import _creature_skin
    alb, h, rough, spec = _creature_skin(rng)
    grey = alb.mean(axis=2, keepdims=True)
    alb = np.clip(grey * np.array([1.0, 1.0, 1.04]) * 1.15 + alb * .15, 0, 1)
    return alb, h, rough, spec


class Screamer:
    def __init__(self, game, lockers, rng):
        self.game = game
        self.rng = rng
        self.cands = [lk for lk in lockers if lk.table != "hangar"]
        self.target = rng.choice(self.cands) if (C.SCREAMER_ENABLED and self.cands) else None
        self.done = False
        self.active = False
        self.t = 0.0
        self.locker = None
        self.face = None
        self._first_room_done = False
        self._heart_t = 0.0
        self._flee_done = False
        self._started = False
        self._restored = False
        self._music = False
        self._told = False
        self._jitter = 0.0
        if self.target is not None and self.target.room is not None:
            print(f"[screamer] casier piégé : {self.target.room.name}")

    # ------------------------------------------------------------------
    def is_target(self, locker):
        return C.SCREAMER_ENABLED and not self.done and locker is self.target

    def on_room_visited(self, room):
        """Première salle visitée (hors hangar) : si le casier piégé s'y trouve, on le déplace."""
        if self._first_room_done or room is None or room.type == "hangar":
            return
        self._first_room_done = True
        if self.target is not None and self.target.room is room and not self.done:
            others = [lk for lk in self.cands if lk.room is not room and not lk.opened]
            if others:
                self.target = self.rng.choice(others)
                print(f"[screamer] déplacé vers : {self.target.room.name if self.target.room else '?'}")
                self.game.place_autopsy()       # le rapport d'autopsie suit le casier

    # ------------------------------------------------------------------
    def trigger(self, locker=None):
        """Déclenche le screamer (ouverture du casier piégé, ou F5 pour tester)."""
        g = self.game
        if self.active or g.player is None:
            return
        self.done = True
        self.active = True
        self.t = 0.0
        self.locker = locker
        self._started = self._flee_done = self._restored = self._music = self._told = False
        self._heart_t = 0.0
        # 1. silence total : la musique d'ambiance et les sons se coupent d'un coup
        g.audio.silence(keep=("locker_open",))
        # récompense : un bon loot au fond du casier
        if locker is not None:
            locker.contents = [("ammo", self.rng.randint(8, 11)), ("medkit", 1)]
            if self.rng.random() < .5:
                locker.contents.append(("battery", 1))

    # ------------------------------------------------------------------
    def _build_face(self):
        """Visage déformé fait de primitives, dans la couche de l'arme (toujours au premier plan)."""
        g = self.game
        rng = random.Random(self.rng.random())
        root = g.postfx.vm_root.attachNewNode("screamer_face")
        skin = textures.material("screamer_skin", custom=_skin)
        mb = MeshBuilder(uv_scale=.12)
        grey = (.62, .62, .64, 1)
        # crâne allongé, asymétrique (face avant tournée vers la caméra : -z)
        secs = []
        for z, w, h, b in ((-.12, .30, .46, .12), (-.07, .36, .54, .15), (.04, .39, .57, .16),
                           (.17, .33, .5, .14), (.29, .19, .3, .08)):
            secs.append((z, rng.uniform(-.02, .02), rng.uniform(-.015, .025), w * rng.uniform(.93, 1.07),
                         h * rng.uniform(.95, 1.06), b))
        mb.loft(secs, grey, cap_start=False)
        # face avant : plaque aux UV planaires (le bouchon du loft n'aurait qu'une couleur de texture)
        z0, cx0, cy0, w0, h0, _b = secs[0]
        front = []
        for k in range(24):
            a = 2 * math.pi * k / 24
            front.append((cx0 + math.cos(a) * w0 * .56, cy0 + math.sin(a) * h0 * .54, z0 - .002))
        mb.poly(front[::-1], (0, 0, -1), grey, [(.5 + p_[0] * 2.2, .5 + p_[1] * 2.2) for p_ in front[::-1]])
        # arcades sourcilières au-dessus des yeux, pommettes saillantes, bosses sous la peau
        for s_ in (-1, 1):
            mb.bevel_box((s_ * .09, .225, -.125), (.11, .03, .05), .012, grey, rot=(0, 0, s_ * -14))
            mb.bevel_box((s_ * .125, .02, -.12), (.05, .07, .05), .016, grey, rot=(0, 0, s_ * 22))
        for _ in range(7):
            mb.bevel_box((rng.uniform(-.15, .15), rng.uniform(-.22, .26), rng.uniform(-.12, .1)),
                         (rng.uniform(.03, .06),) * 3, .012, grey)
        head = NodePath(mb.make_geom_node("screamer_head", tangents=True))
        textures.apply_material(head, skin)
        head.reparentTo(root)
        dark = MeshBuilder()
        # orbites creuses (les yeux y sont enfoncés) et fentes nasales
        for s_, r, dy in ((-1, .05, .0), (1, .042, .015)):
            dark.cylinder((s_ * .09, .16 + dy, -.122), r * 1.35, .006, (.05, .03, .03, 1), 18, 'z')
        # rides de peau tendue autour de la bouche
        for k in range(10):
            a = math.radians(200 + k * 14)
            dark.bevel_box((math.cos(a) * .15, -.08 + math.sin(a) * .17, -.121), (.006, .05, .006), .002,
                           (.22, .2, .2, 1), rot=(0, 0, math.degrees(a) + 90))
        dnp = NodePath(dark.make_geom_node("screamer_sockets", tangents=False))
        dnp.reparentTo(root)
        # bouche béante : trou noir, lèvres continues, anneau de dents irrégulières
        mo = MeshBuilder()
        mcx, mcy, rx, ry = 0.0, -.085, .1, .135
        ring = []
        n = 28
        for k in range(n):
            a = 2 * math.pi * k / n
            ring.append((mcx + math.cos(a) * rx * (1 + .08 * math.sin(3 * a)), mcy + math.sin(a) * ry, -.126))
        mo.poly(ring[::-1], (0, 0, -1), (.015, 0, 0, 1))
        lip = (.24, .07, .075, 1)
        for k in range(n):
            p0, p1 = ring[k], ring[(k + 1) % n]
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            mo.bevel_box((mx, my, -.128), (ln * 1.3, .016, .016), .006, lip, rot=(0, 0, ang))
        for k in range(26):
            a = 2 * math.pi * (k + rng.uniform(-.3, .3)) / 26
            bx = mcx + math.cos(a) * rx * .92
            by = mcy + math.sin(a) * ry * .92
            dx, dy = mcx - bx, mcy - by
            ln = math.hypot(dx, dy)
            d = (dx / ln * .8, dy / ln * .8, -.4)
            dl = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
            mo.cone((bx, by, -.13), rng.uniform(.007, .012), rng.uniform(.03, .075),
                    (.72, .66, .5, 1), (.93, .9, .8, 1), 6, (d[0] / dl, d[1] / dl, d[2] / dl))
        mouth = NodePath(mo.make_geom_node("screamer_mouth", tangents=False))
        mouth.reparentTo(root)
        # yeux blancs lumineux (tailles et hauteurs inégales), enfoncés dans les orbites
        ey = MeshBuilder()
        for s_, r, dy in ((-1, .036, .0), (1, .029, .015)):
            ey.cylinder((s_ * .09, .16 + dy, -.128), r, .008, (1, 1, 1, 1), 16, 'z')
        eyes = NodePath(ey.make_geom_node("screamer_eyes", tangents=False))
        eyes.reparentTo(root)
        mark_emissive(eyes)
        for s_, r, dy in ((-1, .036, .0), (1, .029, .015)):
            h = MeshBuilder()
            q = r * 3.2
            h.poly([(-q, -q, 0), (q, -q, 0), (q, q, 0), (-q, q, 0)], (0, 0, -1), (1, 1, 1, .6),
                   [(0, 0), (1, 0), (1, 1), (0, 1)])
            halo = NodePath(h.make_geom_node("screamer_halo", tangents=False))
            halo.reparentTo(root)
            halo.setPos(s_ * .09, .16 + dy, -.14)
            halo.setTexture(textures.get('glow')._texture)
            halo.setTransparency(TransparencyAttrib.MAlpha)
            additive(halo, 60)
        # éclairage propre au visage (la lampe du joueur clignote) : lumière crue par en dessous
        root.setLightOff(1)
        pl = PointLight("screamer_light")
        pl.setColor(Vec4(2.6, 2.5, 2.4, 1))
        pl.setAttenuation(PVec3(1, 0, 1.5))
        pln = root.attachNewNode(pl)
        pln.setPos(.08, -.3, -.5)
        am = AmbientLight("screamer_amb")
        am.setColor(Vec4(.14, .14, .15, 1))
        amn = root.attachNewNode(am)
        root.setLight(pln, 2)
        root.setLight(amn, 2)
        root.hide()
        return root

    # ------------------------------------------------------------------
    def update(self, dt):
        if not self.active:
            return
        g = self.game
        self.t += dt
        t = self.t
        fl = g.lights.flashlight
        # --- 2. la créature jaillit -----------------------------------------
        if t >= JUMP_T and not self._started:
            self._started = True
            if self.face is None:
                self.face = self._build_face()
            self.face.show()
            if g.weapons is not None:
                g.weapons.rig.hide()
            vol = C.SCREAMER_VOLUME
            g.audio.play("screamer", 1.0 * vol, ignore_duck=True)
            g.audio.play("screamer_stinger", .95 * vol, ignore_duck=True)
            if C.SCREAMER_FLASH:
                g.hud.flash_frame()
            g.inp.rumble(1, 1, 1000)
            g.player.trauma = 1.0
            g.shake(1.0)
            # point de départ : l'intérieur du casier (ou 1,8 m devant pour le test F5)
            from ursina import camera
            from panda3d.core import Point3
            if self.locker is not None:
                lp = self.locker.pos
                fx, fz = self.locker.facing
                wp = Point3(lp[0] - fx * .35, 1.45, lp[2] - fz * .35)
                rel = camera.getRelativePoint(_render(), wp)
                self.start = (rel[0], rel[1], max(.8, rel[2]))
            else:
                self.start = (0.0, -.05, 1.8)
        if self._started and self.face is not None and not self._flee_done:
            u = min(1.0, (t - JUMP_T) / GROW)
            e = u * u * (3 - 2 * u) if u < 1 else 1.0
            e = e ** .7
            sx, sy, sz = self.start
            ex, ey, ez = 0.0, -.09, .8           # le visage remplit l'écran
            j = .012 * (1 + 2 * e)
            self.face.setPos(sx + (ex - sx) * e + random.uniform(-j, j), sy + (ey - sy) * e + random.uniform(-j, j),
                             sz + (ez - sz) * e)
            self.face.setScale(.5 + .55 * e)
            self.face.setHpr(random.uniform(-6, 6) * e, random.uniform(-5, 5) * e, random.uniform(-9, 9) * e)
        # --- 3. la lampe clignote puis s'éteint une seconde -------------------
        if JUMP_T <= t < LAMP_OFF[0]:
            fl.scare_mult = 1.0 if random.random() < .45 else 0.0
        elif LAMP_OFF[0] <= t < LAMP_OFF[1]:
            fl.scare_mult = 0.0
        elif t >= LAMP_OFF[1]:
            fl.scare_mult = 1.0
        # --- 4. elle s'enfuit dans un conduit en griffant le métal ------------
        if t >= JUMP_T + GROW + HOLD and not self._flee_done:
            self._flee_done = True
            if self.face is not None:
                self.face.hide()
            pos = self._vent_near()
            g.audio.play_at("screamer_flee", pos, 1.0 * C.SCREAMER_VOLUME, max_dist=30, ignore_duck=True)
            g.audio.play_at("vent_bang", pos, .9, .8, ignore_duck=True)
        if t >= LAMP_OFF[1] and g.weapons is not None and g.weapons.rig.isHidden():
            g.weapons.rig.show()
        # --- musique angoissante qui retombe vers l'ambiance ------------------
        if t >= 1.2 and not self._music:
            self._music = True
            g.audio.play("screamer_music", .9, music=True, ignore_duck=True)
        if t >= 2.0 and not self._restored:
            self._restored = True
            g.audio.restore(12.0)
        # --- cœur qui bat fort (son + vibration pulsée) -----------------------
        if 1.9 <= t < 8.5:
            self._heart_t -= dt
            if self._heart_t <= 0:
                k = (t - 1.9) / 6.6
                self._heart_t = .48 + .4 * k
                g.audio.play("heartbeat", 1.0 - .5 * k, ignore_duck=True)
                g.inp.rumble(.95 - .5 * k, .2, 130)
        if t >= 2.6 and not self._told:
            self._told = True
            if self.locker is not None:
                g.hud.message("... Il reste quelque chose au fond du casier.", color.rgb(.8, .75, .6))
        if t >= END_T:
            self.active = False
            fl.scare_mult = 1.0

    def _vent_near(self):
        """Grille d'aération la plus proche (sinon le casier) : c'est par là qu'elle s'enfuit."""
        g = self.game
        p = g.player
        best = None
        for gr in g.level.grilles.values():
            d = math.hypot(gr.pos[0] - p.x, gr.pos[1] - p.z)
            if best is None or d < best[0]:
                best = (d, (gr.pos[0], .5, gr.pos[1]))
        if best is not None and best[0] < 20:
            return best[1]
        if self.locker is not None:
            return self.locker.pos
        return (p.x, 1.0, p.z)

    def destroy(self):
        if self.face is not None:
            self.face.removeNode()
            self.face = None
        fl = self.game.lights.flashlight if self.game.lights else None
        if fl is not None:
            fl.scare_mult = 1.0


def _render():
    from ursina import application
    return application.base.render
