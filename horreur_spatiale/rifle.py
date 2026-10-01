# -*- coding: utf-8 -*-
"""
rifle.py — Fusil d'assaut silencieux (trouvé dans le hangar).

Modèle (maillages générés, aucun cube brut) :
  * carcasse anguleuse en deux parties (haute / basse) biseautée, garde-main
    ajouré, rail supérieur cranté, viseur point rouge (boîtier, verre teinté,
    point rouge émissif), long silencieux cylindrique à rainures, lampe
    tactique sous le canon, crosse rétractable (deux tiges + plaque de couche),
    poignée pistolet texturée, pontet et détente, levier d'armement mobile,
    fenêtre d'éjection, LED d'état, numéro de série et logo Helios gravés ;
  * chargeur courbe TRANSPARENT : on voit les cartouches, leur niveau baisse
    à chaque tir ;
  * matériaux : métal noir mat (gunmetal), polymère gris foncé, arêtes usées
    plus claires.

Gameplay :
  * tir automatique (gâchette maintenue), précis en courtes rafales (la
    dispersion et le relèvement augmentent pendant une longue rafale) ;
  * silencieux : « pfft » sourds + cliquetis de culasse, petit flash presque
    invisible ; rayon de bruit très court (RIFLE_NOISE_RADIUS) : il ne
    déclenche pas l'alerte et n'alerte la grande créature que si elle est
    tout près ; les petites créatures proches peuvent réagir ;
  * munitions spécifiques et rares (« rifle_ammo ») ;
  * la grande créature reste impossible à tuer : le fusil la ralentit
    seulement, comme le pistolet.
"""
import math
import random

from panda3d.core import TransparencyAttrib, NodePath, Vec3 as PVec3
from ursina import camera, color, Vec3

import config as C
import textures
from geometry import MeshBuilder
from lighting import additive, mark_emissive

BLACK = (.12, .12, .13, 1)          # métal noir mat
EDGE = (.42, .42, .44, 1)           # usure claire sur les arêtes
POLY = (.2, .2, .21, 1)             # polymère gris foncé
POLY_EDGE = (.32, .32, .33, 1)
DARK = (.04, .04, .045, 1)
STEEL = (.5, .5, .52, 1)
BRASS = (.8, .6, .24, 1)
GLOVE = (.22, .2, .18, 1)
SUIT = (.52, .34, .15, 1)
CUFF = (.3, .3, .32, 1)

SIGHT_Y = .092                       # hauteur du point rouge (ligne de visée) dans le repère du fusil
N_ROUNDS = 12                        # cartouches visibles dans le chargeur transparent


def _mag_curve(k):
    """Point de l'axe du chargeur courbe (k = 0 en haut, 1 en bas)."""
    y = -.012 - .15 * k
    z = .05 + .05 * k * k
    return y, z


class Rifle:
    def __init__(self, weapons):
        self.w = weapons
        self.game = weapons.game
        self.mag = C.RIFLE_MAG
        self.cooldown = 0.0
        self.reloading = 0.0
        self.burst = 0                 # tirs consécutifs (rafale en cours)
        self.bolt_t = 1.0
        self.flash_t = 0.0
        self.mag_dropped = False
        self.inserted = False
        self._last_rounds = -1
        self.root = weapons.rig.attachNewNode("rifle")
        self._build()
        self.root.hide()

    # ==================================================================
    # MODÈLE
    # ==================================================================
    def _build(self):
        from weapons import _attach, _segment
        R = self.root
        # --- carcasse haute et basse, garde-main --------------------------------
        mb = MeshBuilder(uv_scale=.08)
        mb.bevel_box((0, .032, .06), (.05, .05, .3), .008, BLACK, EDGE)             # carcasse haute
        mb.bevel_box((0, -.002, .0), (.044, .036, .19), .007, BLACK, EDGE)          # carcasse basse
        mb.bevel_box((0, .03, .3), (.054, .052, .19), .01, BLACK, EDGE)            # garde-main
        for k in range(5):                                                          # ouïes du garde-main
            for s in (-1, 1):
                mb.box((s * .0272, .028, .23 + k * .03), (.002, .022, .016), DARK)
        mb.bevel_box((0, -.012, .1), (.03, .014, .05), .004, BLACK, EDGE)           # puits du chargeur
        mb.bevel_box((0, .0, -.105), (.04, .044, .03), .006, BLACK, EDGE)          # bloc arrière
        # rail supérieur cranté
        mb.bevel_box((0, .062, .12), (.022, .008, .38), .002, BLACK, EDGE)
        for k in range(18):
            mb.box((0, .0665, -.05 + k * .021), (.023, .003, .006), DARK)
        # fenêtre d'éjection (côté droit) et levier d'armement fixe
        mb.box((.0255, .036, .05), (.002, .016, .045), DARK)
        # pontet et détente
        mb.bevel_box((0, -.035, -.012), (.012, .005, .065), .0015, BLACK, EDGE)
        mb.bevel_box((0, -.026, .02), (.012, .02, .005), .0015, BLACK)
        mb.bevel_box((0, -.022, -.005), (.006, .02, .006), .0015, STEEL, rot=(-15, 0, 0))
        # canon visible entre garde-main et silencieux
        mb.cylinder((0, .03, .405), .009, .03, STEEL, 14, 'z')
        # crosse rétractable : deux tiges + plaque de couche
        for s in (-1, 1):
            mb.cylinder((s * .012, .014, -.19), .006, .2, STEEL, 10, 'z')
        mb.bevel_box((0, .0, -.295), (.042, .115, .028), .008, POLY, POLY_EDGE)
        mb.bevel_box((0, -.002, -.31), (.04, .11, .008), .003, DARK)                 # caoutchouc de la plaque
        self.body = _attach(R, mb, "rifle_body", "gunmetal")
        # --- silencieux à rainures -----------------------------------------------
        sp = MeshBuilder(uv_scale=.05)
        sp.cylinder((0, .03, .54), .024, .25, BLACK, 20, 'z')
        for k in range(8):                                                          # rainures
            sp.cylinder((0, .03, .45 + k * .024), .0245, .006, DARK, 20, 'z')
        sp.cylinder((0, .03, .667), .02, .006, STEEL, 20, 'z')                        # bouche (usée)
        sp.cylinder((0, .03, .671), .007, .003, DARK, 12, 'z')                        # âme
        _attach(R, sp, "rifle_suppressor", "gunmetal", specular=.6, shininess=30)
        # --- poignée pistolet texturée ----------------------------------------------
        gp = MeshBuilder(uv_scale=.03)
        gp.bevel_box((0, -.07, -.045), (.032, .095, .045), .008, POLY, POLY_EDGE, rot=(18, 0, 0))
        _attach(R, gp, "rifle_grip", "polymer")
        # --- viseur point rouge ------------------------------------------------------
        vs = MeshBuilder(uv_scale=.05)
        vs.bevel_box((0, .07, .07), (.026, .012, .05), .003, BLACK, EDGE)            # embase
        vs.cylinder((0, SIGHT_Y, .045), .019, .012, BLACK, 18, 'z')                    # bague arrière
        vs.cylinder((0, SIGHT_Y, .095), .021, .012, BLACK, 18, 'z')                    # bague avant
        for s in (-1, 1):
            vs.bevel_box((s * .02, SIGHT_Y, .07), (.004, .03, .05), .0015, BLACK, EDGE)  # flancs
        vs.bevel_box((0, SIGHT_Y + .021, .07), (.03, .004, .05), .0015, BLACK, EDGE)    # toit
        vs.bevel_box((.024, SIGHT_Y, .06), (.006, .01, .014), .002, POLY)               # molette
        _attach(R, vs, "rifle_sight", "gunmetal")
        lens = MeshBuilder()
        lens.cylinder((0, SIGHT_Y, .095), .0185, .001, (.55, .7, .62, .22), 18, 'z')
        self.lens = _attach(R, lens, "rifle_lens")
        self.lens.setTransparency(TransparencyAttrib.MAlpha)
        self.lens.setDepthWrite(False)
        self.lens.setBin('transparent', 30)
        dot = MeshBuilder()
        dot.cylinder((0, 0, 0), .0012, .0005, (1, .05, .03, 1), 10, 'z')
        self.red_dot = _attach(R, dot, "rifle_red_dot", unlit=True)
        self.red_dot.setPos(0, SIGHT_Y, .0965)     # géométrie centrée : le grossissement reste sur la lentille
        mark_emissive(self.red_dot)
        self.red_dot.setBin('fixed', 31)
        # --- lampe tactique sous le canon ------------------------------------------
        lt = MeshBuilder(uv_scale=.04)
        lt.bevel_box((0, -.008, .3), (.02, .012, .05), .003, BLACK, EDGE)
        lt.cylinder((0, -.02, .31), .011, .065, BLACK, 16, 'z')
        lt.cylinder((0, -.02, .345), .0125, .006, STEEL, 16, 'z')
        _attach(R, lt, "rifle_light", "gunmetal")
        ll = MeshBuilder()
        ll.cylinder((0, -.02, .3485), .0095, .001, (.8, .85, 1, 1), 14, 'z')
        mark_emissive(_attach(R, ll, "rifle_light_lens", unlit=True))
        # --- LED d'état (flanc gauche) ---------------------------------------------
        self.leds = []
        for k in range(3):
            lm = MeshBuilder()
            lm.box((-.0255, .045, .0 + k * .012), (.001, .005, .006), (1, 1, 1, 1))
            n = _attach(R, lm, f"rifle_led{k}", unlit=True)
            mark_emissive(n)
            self.leds.append(n)
        # --- marquages gravés : numéro de série + logo Helios ------------------------
        for z0, z1, txt in ((-.07, .05, "HB-SR7  SN 0912-AK"), (.08, .18, "HELIOS BIOTECH")):
            sn = MeshBuilder()
            sn.poly([(-.0225, -.012, z0), (-.0225, .006, z0), (-.0225, .006, z1), (-.0225, -.012, z1)],
                    (-1, 0, 0), (1, 1, 1, 1), [(0, 0), (0, 1), (1, 1), (1, 0)])
            n = _attach(R, sn, "rifle_mark")
            n.setTexture(textures.text_decal(txt, 256, 32, (165, 165, 160), mirror=True)._texture)
            n.setTransparency(TransparencyAttrib.MAlpha)
            n.setDepthOffset(2)
        # --- levier d'armement / culasse mobile -------------------------------------
        self.bolt = R.attachNewNode("rifle_bolt")
        bm = MeshBuilder(uv_scale=.04)
        bm.bevel_box((.026, .036, .05), (.004, .012, .03), .0015, STEEL)               # culasse dans la fenêtre
        bm.bevel_box((.03, .05, -.07), (.012, .008, .02), .002, BLACK, EDGE)          # levier d'armement
        _attach(self.bolt, bm, "rifle_bolt_mesh", "gunmetal")
        # --- chargeur courbe transparent + cartouches visibles ------------------------
        self.mag_np = R.attachNewNode("rifle_mag")
        shell = MeshBuilder()
        segs = 10
        for i in range(segs):
            k0, k1 = i / segs, (i + 1) / segs
            y0, z0 = _mag_curve(k0)
            y1, z1 = _mag_curve(k1)
            yc, zc = (y0 + y1) / 2, (z0 + z1) / 2
            ang = math.degrees(math.atan2(z1 - z0, -(y1 - y0)))
            shell.bevel_box((0, yc, zc), (.026, abs(y1 - y0) + .004, .034), .004, (.6, .62, .6, .3),
                            rot=(-ang, 0, 0))
        self.mag_shell = _attach(self.mag_np, shell, "rifle_mag_shell")
        self.mag_shell.setTransparency(TransparencyAttrib.MAlpha)
        self.mag_shell.setDepthWrite(False)
        self.mag_shell.setBin('transparent', 25)
        base = MeshBuilder(uv_scale=.04)
        y1, z1 = _mag_curve(1.0)
        base.bevel_box((0, y1 - .006, z1), (.03, .01, .04), .003, POLY, POLY_EDGE)      # semelle
        _attach(self.mag_np, base, "rifle_mag_base", "polymer")
        self.rounds = []
        for i in range(N_ROUNDS):
            k = (i + .5) / N_ROUNDS
            y, z = _mag_curve(k)
            rm = MeshBuilder(uv_scale=.02)
            rm.cylinder((0, y, z), .0065, .026, BRASS, 8, 'z')
            rm.cylinder((0, y, z + .016), .0045, .008, STEEL, 8, 'z')                 # ogive
            n = _attach(self.mag_np, rm, f"round{i}", "brushed", specular=1.2, shininess=60)
            self.rounds.append(n)
        self.mag_tpl_mb = shell
        # --- flash très atténué au bout du silencieux ---------------------------------
        fq = MeshBuilder()
        s = .025
        fq.poly([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], (0, 0, -1), (1, .8, .55, 1),
                [(0, 0), (1, 0), (1, 1), (0, 1)])
        self.flash = _attach(R, fq, "rifle_flash", unlit=True)
        self.flash.setPos(0, .03, .68)
        additive(self.flash, 9)
        self.flash.hide()
        # --- mains : droite sur la poignée, gauche sur le garde-main -----------------
        hm = MeshBuilder(uv_scale=.05)
        hm.bevel_box((.008, -.07, -.04), (.05, .09, .06), .01, GLOVE, rot=(18, 0, 0))   # main droite
        for k in range(4):
            hm.bevel_box((-.006, -.04 - k * .019, -.01), (.05, .016, .02), .006, GLOVE, rot=(18, 0, 0))
        hm.bevel_box((-.02, .005, -.05), (.013, .014, .05), .006, GLOVE)                  # pouce
        _segment(hm, (.012, -.11, -.07), (.1, -.33, -.4), .075, .07, SUIT, .02)
        _segment(hm, (.012, -.112, -.072), (.03, -.14, -.1), .07, .065, CUFF, .01)
        hm.bevel_box((-.006, .0, .3), (.06, .05, .08), .012, GLOVE)                       # main gauche
        for k in range(4):
            hm.bevel_box((.02, -.006, .27 + k * .02), (.03, .045, .016), .006, GLOVE)
        _segment(hm, (-.02, -.02, .29), (-.18, -.32, -.22), .072, .068, SUIT, .02)
        _attach(R, hm, "rifle_hands", "suit")

    def make_mag_template(self):
        """Gabarit du chargeur vide qui tombe au sol (rechargement)."""
        np_ = NodePath(self.mag_tpl_mb.make_geom_node("rifle_mag_drop", tangents=False))
        np_.setTransparency(TransparencyAttrib.MAlpha)
        return np_

    # ==================================================================
    # ACTIONS
    # ==================================================================
    @property
    def reserve(self):
        return self.game.inventory.count("rifle_ammo")

    def start_reload(self):
        g = self.game
        if self.reloading > 0 or self.mag >= C.RIFLE_MAG:
            return
        if self.reserve <= 0:
            g.hud.message("Plus de munitions de fusil")
            return
        self.reloading = C.RIFLE_RELOAD_TIME
        self.mag_dropped = self.inserted = False
        g.audio.play("rifle_reload", .65)

    def update_input(self, dt, inp, busy):
        """Tir automatique (maintenir), rechargement. Appelé quand le fusil est l'arme active."""
        g = self.game
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.reloading > 0:
            self.reloading -= dt
            if self.reloading <= 0:
                got = g.inventory.remove("rifle_ammo", C.RIFLE_MAG - self.mag)
                self.mag += got
            return
        if busy:
            self.burst = 0
            return
        if inp.pressed("reload"):
            self.start_reload()
            return
        if inp.held("fire"):
            if self.cooldown <= 0:
                self.fire()
        else:
            self.burst = max(0, self.burst - 1) if self.cooldown <= 0 else self.burst
            if not inp.held("fire"):
                self.burst = 0

    def fire(self):
        g = self.game
        w = self.w
        if self.mag <= 0:
            self.cooldown = .3
            g.audio.play("rifle_dry", .7, random.uniform(.95, 1.05))
            if self.reserve > 0:
                self.start_reload()
            return
        self.mag -= 1
        self.burst += 1
        self.cooldown = 1.0 / C.RIFLE_FIRE_RATE
        # animation : petit recul élastique, culasse, flash presque invisible
        w.rec_zv -= .32 + random.uniform(0, .08)
        w.rec_pv += 70 + random.uniform(0, 25) + min(60, self.burst * 6)
        self.bolt_t = 0.0
        self.flash_t = .03
        self.flash.setR(random.uniform(0, 360))
        # le canon monte pendant la rafale (relèvement qui s'accumule)
        climb = C.RIFLE_RECOIL * (1 + min(self.burst, 12) * C.RIFLE_RECOIL_CLIMB)
        g.player.pitch -= climb * (.6 if w.aiming else 1.0)
        g.player.yaw += random.uniform(-.25, .25) * (1 + self.burst * .05)
        g.player.trauma = min(1, g.player.trauma + .04)
        g.inp.rumble(.45, .3, 60)
        # son silencieux : « pfft » sourd + cliquetis de culasse
        g.audio.play(f"rifle_shot{random.randint(0, 2)}", C.RIFLE_VOLUME * random.uniform(.85, 1.0),
                     random.uniform(.94, 1.08))
        if random.random() < .35:
            g.audio.play("rifle_tail", .5, random.uniform(.9, 1.1))
        cp = camera.world_position
        mw = w.vm_to_world(self.root, (0, .03, .68))
        g.lights.flash((mw.x, mw.y, mw.z), (1, .8, .5), C.RIFLE_MUZZLE_LIGHT, 22.0)
        w.eject_casing_from(self.root, (.03, .04, .05))
        # bruit très court : pas d'alerte générale ; la grande créature n'entend que tout près,
        # les petites créatures un peu plus loin
        pos = (cp.x, cp.y, cp.z)
        if g.creature is not None:
            g.creature.hear(pos, C.RIFLE_NOISE_RADIUS, "silenced")
        if g.aliens is not None:
            g.aliens.hear(pos, C.RIFLE_ALIEN_HEAR_RADIUS, "silenced")
        # tir précis en courtes rafales : la dispersion grimpe pendant une longue rafale
        spread = (C.RIFLE_SPREAD_ADS if w.aiming else C.RIFLE_SPREAD_HIP) + min(self.burst, 15) * C.RIFLE_SPREAD_BURST
        d = w._spread_dir(spread)
        w._hitscan(cp, d, C.RIFLE_DAMAGE, C.RIFLE_RANGE, gun=True)

    # ==================================================================
    # ANIMATION (appelée par Weapons._animate quand le fusil est actif)
    # ==================================================================
    def animate(self, dt, pos, pitch, yaw, roll):
        w = self.w
        from weapons import _rotate, _ease
        # rechargement procédural : le fusil s'incline, le chargeur tombe, le nouveau arrive, on arme
        mag_off = 0.0
        if self.reloading > 0:
            rt = C.RIFLE_RELOAD_TIME - self.reloading
            tilt = _ease(min(1, rt / .3)) * (1 - _ease(max(0, (rt - 1.9) / .35)))
            pos += PVec3(-.03 * tilt, -.035 * tilt, -.02 * tilt)
            roll += 32 * tilt
            pitch += -10 * tilt
            if .3 <= rt < .55:
                mag_off = -((rt - .3) / .25) ** 2 * .22
                if not self.mag_dropped:
                    self.mag_dropped = True
                    w.drop_object(self.mag_np, (0, -.12, .08), self.make_mag_template(), .015)
            elif .55 <= rt < 1.05:
                mag_off = -.2 * (1 - _ease((rt - .55) / .5))
            if .55 > rt >= .3 and mag_off < -.18:
                self.mag_np.hide()
            else:
                self.mag_np.show()
            if 1.05 <= rt < 1.15:
                pos += PVec3(0, .007 * math.sin((rt - 1.05) / .1 * math.pi), 0)
            if 1.55 <= rt < 1.8:
                # levier d'armement tiré puis relâché
                k = math.sin((rt - 1.55) / .25 * math.pi)
                self.bolt.setPos(0, 0, -.045 * k)
        else:
            self.mag_np.show()
            # culasse : recule au tir et revient
            self.bolt_t += dt
            if self.bolt_t < .025:
                self.bolt.setPos(0, 0, -.03 * self.bolt_t / .025)
            elif self.bolt_t < .07:
                self.bolt.setPos(0, 0, -.03 * (1 - (self.bolt_t - .025) / .045))
            else:
                self.bolt.setPos(0, 0, 0)
        self.mag_np.setPos(0, mag_off, mag_off * -.25)
        # cartouches visibles : le niveau baisse à chaque tir
        shown = int(math.ceil(self.mag / C.RIFLE_MAG * N_ROUNDS)) if self.mag > 0 else 0
        if shown != self._last_rounds:
            self._last_rounds = shown
            for i, n in enumerate(self.rounds):
                if i < shown:
                    n.show()
                else:
                    n.hide()
            # LED d'état : vert, ambre (peu de munitions), rouge (vide)
            frac = self.mag / C.RIFLE_MAG
            c = (.1, 1, .35) if frac > .3 else ((1, .55, .1) if frac > 0 else (1, .06, .04))
            for k, led in enumerate(self.leds):
                on = k < max(1, int(round(frac * 3)))
                led.setColorScale(*(c if on else (.05, .06, .05)), 1)
        # point rouge plus présent en visée
        a = w.aim_k
        self.red_dot.setColorScale(1, 1, 1, 1)
        self.red_dot.setScale(1 + .6 * (1 - a))
        # flash presque invisible
        if self.flash_t > 0:
            self.flash_t -= dt
            self.flash.show()
            self.flash.setScale(random.uniform(.7, 1.1))
        else:
            self.flash.hide()
        # à la hanche, le long fusil est tourné un peu vers l'extérieur (sinon sa bouche croise l'écran)
        yaw += 4.5 * (1 - a)
        self.w.rig.setPos(pos)
        _rotate(self.root, pitch, yaw, roll)

    def hud_text(self):
        return f"{self.mag} | {self.reserve}" + ("  RECHARGE..." if self.reloading > 0 else "") + "   FUSIL"
