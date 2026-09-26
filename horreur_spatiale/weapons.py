# -*- coding: utf-8 -*-
"""
weapons.py — Pistolet (hitscan, visée, recul, flash, chargeur) et couteau
(silencieux, durabilité). Chaque tir déclenche le mode horreur.

Rendu (sans changer le gameplay) :
  * pistolet de sécurité industriel en dizaines de pièces biseautées
    (carcasse, culasse mobile striée, canon, pontet, détente, marteau,
    chargeur amovible, poignée en polymère antidérapant, organes de visée à
    points tritium, rail + lampe tactique, numéro de série gravé) ;
  * affichage diégétique des munitions : rangée de LED sur le flanc ;
  * mains gantées et avant-bras de combinaison spatiale ;
  * l'ensemble vit dans une couche séparée (postfx.vm_root) avec son
    propre FOV : l'arme ne rentre jamais dans les murs ;
  * animations procédurales : balancement de marche/course, inertie
    (sway), respiration, passage en visée, recul élastique, culasse qui
    recule (et reste bloquée à vide), rechargement complet (le chargeur
    vide tombe au sol), coup de couteau ;
  * effets : flash en étoile additif aléatoire, lumière très brève,
    fumée au canon après plusieurs tirs, douilles éjectées qui rebondissent,
    étincelles + trous qui restent sur les murs, giclées extraterrestres.
"""
import math
import random

from panda3d.core import TransparencyAttrib, NodePath, Vec3 as PVec3
from ursina import Entity, camera, color, Vec3, destroy

import config as C
import textures
from geometry import MeshBuilder
from lighting import additive

# couleurs des matériaux (teintes multipliées par les textures procédurales)
METAL = (.24, .24, .25, 1)
METAL_EDGE = (.55, .55, .57, 1)       # arêtes usées, plus claires
POLY = (.16, .16, .16, 1)
BRIGHT = (.62, .62, .64, 1)
SUIT = (.52, .34, .15, 1)             # combinaison orange sale
GLOVE = (.22, .2, .18, 1)
CUFF = (.3, .3, .32, 1)
BRASS = (.78, .58, .22, 1)

GRIP_TILT = 16.0                      # inclinaison de la poignée (degrés)


def _rotate(np_, pitch=0.0, yaw=0.0, roll=0.0):
    """Rotation Panda3D avec les conventions d'Ursina (tangage >0 = vers le bas)."""
    np_.setHpr(-yaw, -pitch, roll)


def _attach(parent, mb, name, material=None, albedo=None, shininess=None, specular=None, unlit=False):
    node = mb.make_geom_node(name, tangents=material is not None)
    np_ = parent.attachNewNode(node)
    if material is not None:
        textures.apply_material(np_, material, albedo=albedo, specular=specular, shininess=shininess)
    if unlit:
        np_.setLightOff(2)
    return np_


def _grip_frame():
    """Repère de la poignée inclinée : renvoie une fonction (u, v, w) -> point."""
    c = (0.0, -.058, -.068)
    t = math.radians(GRIP_TILT)
    up = (0, math.cos(t), math.sin(t))
    fw = (0, -math.sin(t), math.cos(t))

    def G(u, v, w):
        return (c[0] + u, c[1] + up[1] * v + fw[1] * w, c[2] + up[2] * v + fw[2] * w)
    return G


def _segment(mb, p0, p1, w, h, col, bevel=.01):
    """Boîte biseautée allant de p0 à p1 (avant-bras, doigts)."""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1e-4
    yaw = math.degrees(math.atan2(dx, dz))
    pitch = math.degrees(math.asin(max(-1, min(1, -dy / L))))
    c = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2)
    mb.bevel_box(c, (w, h, L), bevel, col, rot=(pitch, yaw, 0))


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
        self.casings = []
        self.dropped = []
        self.smoke = []
        self.splats = []
        # états d'animation
        self.rec_z = self.rec_zv = 0.0        # recul (translation)
        self.rec_p = self.rec_pv = 0.0        # recul (relèvement)
        self.sway_x = self.sway_y = 0.0
        self.slide_x = 0.0
        self.slide_t = 1.0
        self.slide_locked = False
        self.flash_t = 0.0
        self.heat = 0.0                        # chaleur du canon -> fumée
        self.smoke_timer = 0.0
        self.t = 0.0
        self.mag_ejected = False
        self.run_k = 0.0
        self._last_mag = -1
        self._pending_release = False
        pf = game.postfx
        self.vm_root = pf.vm_root
        self.rig = self.vm_root.attachNewNode("weapon_rig")
        self._build_pistol()
        self._build_knife()
        self.gun.hide()
        self.knife.hide()
        self._build_world_templates()

    # ==================================================================
    # CONSTRUCTION DES MODÈLES
    # ==================================================================
    def _build_pistol(self):
        self.gun = self.rig.attachNewNode("pistol")
        G = _grip_frame()
        # --- carcasse (fixe) ----------------------------------------------
        fr = MeshBuilder(uv_scale=.08)
        fr.bevel_box((0, -.008, .03), (.028, .022, .15), .004, METAL, METAL_EDGE)       # carcasse
        fr.bevel_box((0, -.021, .082), (.02, .006, .058), .0015, METAL, METAL_EDGE)     # rail inférieur
        for k in range(5):                                                                # crans du rail
            fr.box((0, -.0245, .06 + k * .01), (.021, .002, .004), (.05, .05, .05, 1))
        fr.bevel_box((0, -.043, .012), (.012, .006, .062), .002, METAL, METAL_EDGE)      # pontet (bas)
        fr.bevel_box((0, -.03, .043), (.012, .03, .006), .002, METAL, METAL_EDGE)        # pontet (avant)
        fr.bevel_box((0, -.027, -.006), (.006, .022, .006), .0015, BRIGHT, rot=(-18, 0, 0))   # détente
        fr.bevel_box((0, .026, -.108), (.01, .016, .012), .002, METAL, METAL_EDGE, rot=(-30, 0, 0))  # marteau
        fr.bevel_box((0, .035, -.114), (.012, .006, .01), .0015, METAL_EDGE, rot=(-30, 0, 0))       # crête
        fr.bevel_box((.0155, -.002, -.03), (.004, .006, .014), .001, BRIGHT)             # sûreté
        fr.bevel_box((-.0155, -.004, .01), (.004, .005, .02), .001, BRIGHT)              # arrêtoir de culasse
        fr.bevel_box((0, -.036, .092), (.024, .016, .05), .003, METAL, METAL_EDGE)       # corps de la lampe tactique
        fr.cylinder((0, -.038, .117), .0085, .006, BRIGHT, 14, 'z')                      # bague de la lampe
        # écran de munitions (cadre) côté gauche
        fr.bevel_box((-.0146, -.009, -.02), (.002, .009, .05), .0008, (.05, .05, .06, 1))
        self.frame_np = _attach(self.gun, fr, "pistol_frame", "gunmetal")
        # --- poignée en polymère antidérapant -----------------------------
        gp = MeshBuilder(uv_scale=.03)
        gp.bevel_box(G(0, 0, 0), (.031, .1, .046), .006, POLY, (.2, .2, .2, 1), rot=(GRIP_TILT, 0, 0))
        gp.bevel_box(G(0, .002, -.024), (.024, .08, .006), .002, POLY, rot=(GRIP_TILT, 0, 0))   # dos de poignée
        self.grip_np = _attach(self.gun, gp, "pistol_grip", "polymer")
        # --- lentille de la lampe tactique et points tritium (émissifs) ----
        em = MeshBuilder()
        em.cylinder((0, -.038, .1205), .007, .001, (.8, .85, 1, 1), 14, 'z')
        _attach(self.gun, em, "pistol_emissive", unlit=True)
        # --- culasse mobile -------------------------------------------------
        self.slide = self.gun.attachNewNode("slide")
        sl = MeshBuilder(uv_scale=.08)
        sl.bevel_box((0, .018, .03), (.03, .032, .19), .005, METAL, METAL_EDGE)
        # stries de préhension (arrière de la culasse, des deux côtés)
        for k in range(7):
            z = -.058 + k * .0055
            for s in (-1, 1):
                sl.box((s * .0151, .018, z), (.0012, .022, .0022), (.04, .04, .045, 1))
        # fenêtre d'éjection (côté droit) et canon visible
        sl.box((.0151, .026, .03), (.001, .01, .028), (.03, .03, .03, 1))
        sl.cylinder((.0, .02, .0305), .0065, .028, BRIGHT, 12, 'z')          # canon dans la fenêtre
        sl.bevel_box((0, .037, -.061), (.026, .012, .012), .002, METAL, METAL_EDGE)   # hausse
        sl.box((0, .041, -.055), (.006, .005, .001), (.02, .02, .02, 1))              # cran de mire
        sl.bevel_box((0, .038, .116), (.006, .01, .008), .0015, METAL, METAL_EDGE)    # guidon
        self.slide_np = _attach(self.slide, sl, "pistol_slide", "gunmetal")
        brl = MeshBuilder(uv_scale=.05)
        brl.cylinder((0, .02, .127), .0072, .008, BRIGHT, 14, 'z')                    # bouche du canon
        brl.cylinder((0, .02, .1315), .0045, .0012, (.02, .02, .02, 1), 12, 'z')     # âme (noire)
        _attach(self.slide, brl, "pistol_muzzle", "brushed", specular=1.2, shininess=80)
        trit = MeshBuilder()
        for x in (-.0075, .0075):
            trit.cylinder((x, .04, -.0675), .0016, .001, (.35, 1, .45, 1), 8, 'z')
        trit.cylinder((0, .0405, .1118), .0016, .001, (.35, 1, .45, 1), 8, 'z')
        _attach(self.slide, trit, "pistol_tritium", unlit=True)
        # --- numéro de série gravé (flanc gauche, visible) -------------------
        sn = MeshBuilder()
        sn.poly([(-.0143, -.017, .06), (-.0143, -.005, .06), (-.0143, -.005, .1), (-.0143, -.017, .1)],
                (-1, 0, 0), (1, 1, 1, 1), [(0, 0), (0, 1), (1, 1), (1, 0)])
        sn_np = _attach(self.gun, sn, "pistol_serial")
        sn_np.setTexture(textures.text_decal("SN 4471-KX  MNEMO", 256, 32, (170, 170, 165), mirror=True)._texture)
        sn_np.setTransparency(TransparencyAttrib.MAlpha)
        sn_np.setDepthOffset(2)
        # --- LED de munitions (affichage diégétique) ------------------------
        self.leds = []
        for k in range(C.PISTOL_MAG):
            lm = MeshBuilder()
            lm.box((-.0158, -.009, -.04 + k * .0055), (.001, .004, .0035), (1, 1, 1, 1))
            n = _attach(self.gun, lm, f"led_{k}", unlit=True)
            self.leds.append(n)
        # --- chargeur amovible -------------------------------------------
        self.mag_np = self.gun.attachNewNode("magazine")
        mg = MeshBuilder(uv_scale=.05)
        mg.bevel_box(G(0, -.004, -.002), (.022, .092, .032), .003, METAL, METAL_EDGE, rot=(GRIP_TILT, 0, 0))
        mg.bevel_box(G(0, -.055, 0), (.033, .01, .05), .003, (.1, .1, .1, 1), (.3, .3, .3, 1), rot=(GRIP_TILT, 0, 0))
        mg.box(G(0, .044, .004), (.01, .004, .02), BRASS)                             # cartouche visible
        _attach(self.mag_np, mg, "magazine_mesh", "gunmetal")
        self.mag_mb_template = mg
        # --- flash de bouche (étoile additive) -------------------------------
        fq = MeshBuilder()
        s = .07
        fq.poly([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], (0, 0, -1), (1, 1, 1, 1),
                [(0, 0), (1, 0), (1, 1), (0, 1)])
        self.flash = _attach(self.slide, fq, "muzzle_flash", unlit=True)
        self.flash.setPos(0, .02, .15)
        additive(self.flash, 9)
        self.flash.hide()
        fq2 = MeshBuilder()
        fq2.poly([(0, -s * .6, 0), (0, s * .6, 0), (0, s * .6, s * 2.2), (0, -s * .6, s * 2.2)], (1, 0, 0),
                 (1, 1, 1, 1), [(0, 0), (1, 0), (1, 1), (0, 1)])
        self.flash_side = _attach(self.slide, fq2, "muzzle_flash_side", unlit=True)
        self.flash_side.setPos(0, .02, .13)
        self.flash_side.setTwoSided(True)
        additive(self.flash_side, 9)
        self.flash_side.hide()
        # --- mains et avant-bras ------------------------------------------
        self._build_hands(G)

    def _build_hands(self, G):
        # main droite : paume contre la poignée, doigts qui l'enveloppent
        rh = MeshBuilder(uv_scale=.05)
        rh.bevel_box(G(.022, -.005, -.004), (.016, .09, .06), .008, GLOVE, rot=(GRIP_TILT, 0, 0))      # paume/dos
        for k in range(4):
            v = .022 - k * .021
            rh.bevel_box(G(.004, v, .033), (.044, .017, .02), .006, GLOVE, rot=(GRIP_TILT, 0, 0))   # doigts
            rh.bevel_box(G(-.02, v, .018), (.012, .016, .03), .005, GLOVE, rot=(GRIP_TILT, 0, 0))   # bouts
        rh.bevel_box((-.02, .002, -.045), (.013, .014, .055), .006, GLOVE, rot=(0, 8, 0))             # pouce
        rh.bevel_box(G(.012, -.07, -.03), (.05, .03, .055), .01, GLOVE, rot=(GRIP_TILT, 0, 0))        # poignet
        _segment(rh, G(.014, -.07, -.03), (.09, -.34, -.42), .075, .07, SUIT, .02)                     # avant-bras
        _segment(rh, G(.013, -.075, -.034), G(.016, -.1, -.055), .07, .065, CUFF, .01)                # manchette
        self.rhand = _attach(self.gun, rh, "right_hand", "suit")
        # main gauche : soutient la droite par-dessous (se retire pour le couteau)
        self.lhand = self.gun.attachNewNode("left_hand")
        lh = MeshBuilder(uv_scale=.05)
        lh.bevel_box(G(-.026, -.012, .0), (.016, .08, .058), .008, GLOVE, rot=(GRIP_TILT, 0, 0))
        for k in range(4):
            v = -.012 - k * .018
            lh.bevel_box(G(-.004, v, .05), (.052, .016, .02), .006, GLOVE, rot=(GRIP_TILT, 0, 0))
        lh.bevel_box((-.021, -.01, .03), (.012, .013, .05), .006, GLOVE, rot=(0, -6, 0))              # pouce gauche
        _segment(lh, G(-.03, -.06, -.02), (-.16, -.33, -.34), .072, .068, SUIT, .02)
        _segment(lh, G(-.03, -.062, -.022), G(-.05, -.09, -.05), .068, .064, CUFF, .01)
        _attach(self.lhand, lh, "left_hand_mesh", "suit")

    def _build_knife(self):
        self.knife = self.rig.attachNewNode("knife_arm")
        kb = MeshBuilder(uv_scale=.05)
        kb.bevel_box((0, 0, .075), (.004, .026, .13), .0015, (.7, .72, .76, 1), (.9, .9, .92, 1))   # lame
        kb.bevel_box((0, .006, .145), (.004, .014, .02), .0015, (.7, .72, .76, 1), rot=(-30, 0, 0))   # pointe
        kb.bevel_box((0, 0, .006), (.03, .01, .012), .002, (.2, .2, .2, 1))                          # garde
        _attach(self.knife, kb, "knife_blade", "brushed", specular=1.3, shininess=90)
        kh = MeshBuilder(uv_scale=.03)
        kh.bevel_box((0, 0, -.045), (.018, .024, .09), .005, (.1, .08, .06, 1))                     # manche
        kh.bevel_box((.004, -.004, -.045), (.04, .045, .07), .012, GLOVE)                           # main gauche
        _segment(kh, (.004, -.01, -.07), (-.05, -.18, -.35), .07, .066, SUIT, .02)
        _attach(self.knife, kh, "knife_hand", "polymer")

    def _build_world_templates(self):
        """Géométries partagées des objets éjectés dans le monde (douille, chargeur)."""
        cb = MeshBuilder(uv_scale=.02)
        cb.cylinder((0, 0, 0), .0045, .019, BRASS, 8, 'z')
        cb.cylinder((0, 0, -.0102), .005, .0014, (.6, .45, .18, 1), 8, 'z')
        self.casing_tpl = NodePath(cb.make_geom_node("casing", tangents=True))
        textures.apply_material(self.casing_tpl, "brushed", specular=1.4, shininess=70)
        self.mag_tpl = NodePath(self.mag_mb_template.make_geom_node("mag_drop", tangents=True))
        textures.apply_material(self.mag_tpl, "gunmetal")

    # ==================================================================
    def give_pistol(self):
        self.has_pistol = True
        self.mag = C.PISTOL_START_MAG
        self.game.inventory.add("ammo", C.PISTOL_START_RESERVE)
        self.gun.show()

    @property
    def reserve(self):
        return self.game.inventory.count("ammo")

    def show(self, on):
        self.game.postfx.show_viewmodel(on)

    # ==================================================================
    # MISE À JOUR
    # ==================================================================
    def update(self, dt, inp):
        g = self.game
        p = g.player
        self.t += dt
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
        self.recoil = max(0.0, self.recoil - dt * 6)
        self.kick = max(0.0, self.kick - dt * 9)
        self.spread_bonus = max(0.0, self.spread_bonus - dt * 2)
        self._animate(dt)
        self._update_effects(dt)

    # ------------------------------------------------------------------
    def _animate(self, dt):
        g = self.game
        p = g.player
        a = self.aim_k
        # ressort de recul (masse-ressort amorti : retour élastique)
        for attr, k, d in (("rec_z", 380, 26), ("rec_p", 320, 22)):
            x, v = getattr(self, attr), getattr(self, attr + "v")
            v += (-k * x - d * v) * dt
            x += v * dt
            setattr(self, attr, x)
            setattr(self, attr + "v", v)
        # inertie (sway) : l'arme traîne derrière les mouvements de la vue
        lx = g.inp.look_x / max(dt, 1e-4)
        ly = g.inp.look_y / max(dt, 1e-4)
        tx = max(-.025, min(.025, -lx * .00012)) * (1 - a * .7)
        ty = max(-.02, min(.02, -ly * .0001)) * (1 - a * .7)
        k = min(1.0, dt * 9)
        self.sway_x += (tx - self.sway_x) * k
        self.sway_y += (ty - self.sway_y) * k
        # balancement de marche / course + respiration à l'arrêt
        speed = math.hypot(p.vx, p.vz)
        moving = speed > .4
        self.run_k += ((1.0 if (p.running and moving and a < .1) else 0.0) - self.run_k) * min(1, dt * 7)
        amp = (.009 if not p.running else .018) * min(1, speed / 3) * (1 - a * .85)
        ph = p._bob
        bob_x = math.cos(ph * .5) * amp * 1.2
        bob_y = -abs(math.sin(ph * .5)) * amp * 1.4
        breath = math.sin(self.t * 1.7) * .0018 * (1 - min(1, speed)) * (1 - a * .6)
        # poses
        hip = PVec3(.125, -.1, .38)
        ads = PVec3(0, -.0405, .33)           # organes de visée alignés sur le centre de l'écran
        pos = hip + (ads - hip) * a
        pos += PVec3(self.sway_x + bob_x, self.sway_y + bob_y + breath, self.rec_z)
        pitch = -self.rec_p * (.55 if self.aiming else 1.0) + ly * .004 * (1 - a) + breath * 150
        yaw = self.sway_x * 90 + (1 - a) * -2.5
        roll = -self.sway_x * 160 + math.cos(ph * .5) * amp * 80
        # course : arme abaissée et tournée
        rk = self.run_k
        pos += PVec3(-.03 * rk, -.05 * rk, -.03 * rk)
        pitch += 22 * rk
        yaw += -28 * rk
        roll += 12 * rk
        # rechargement procédural
        mag_off = 0.0
        self.mag_np.show()
        if self.reloading > 0:
            rt = C.PISTOL_RELOAD_TIME - self.reloading
            tilt = _ease(min(1, rt / .25)) * (1 - _ease(max(0, (rt - 1.3) / .3)))
            pos += PVec3(-.02 * tilt, -.03 * tilt, -.02 * tilt)
            roll += 28 * tilt
            pitch += -12 * tilt
            if .25 <= rt < .45:
                mag_off = -((rt - .25) / .2) ** 2 * .2        # le chargeur vide glisse et tombe
                if not self.mag_ejected:
                    self.mag_ejected = True
                    self._drop_magazine()
            elif .45 <= rt < .95:
                mag_off = -.16 * (1 - _ease((rt - .45) / .5))  # nouveau chargeur inséré
            elif rt < .25:
                mag_off = 0.0
            if .95 <= rt < 1.05:
                pos += PVec3(0, .006 * math.sin((rt - .95) / .1 * math.pi), 0)   # claque le chargeur
            if rt >= 1.15 and self._pending_release:
                self._pending_release = False
                self.slide_locked = False
                self.slide_t = .03
            if .45 > rt >= .25 and mag_off < -.14:
                self.mag_np.hide()
        else:
            self.mag_ejected = False
        self.mag_np.setPos(0, mag_off * math.cos(math.radians(GRIP_TILT)),
                           mag_off * math.sin(math.radians(GRIP_TILT)))
        # culasse : recule au tir, revient, reste bloquée à vide
        if self.slide_locked:
            self.slide_x += (-.03 - self.slide_x) * min(1, dt * 40)
        else:
            self.slide_t += dt
            if self.slide_t < .03:
                self.slide_x = -.033 * (self.slide_t / .03)
            elif self.slide_t < .1:
                self.slide_x = -.033 * (1 - (self.slide_t - .03) / .07)
            else:
                self.slide_x = 0.0
        self.slide.setPos(0, 0, self.slide_x)
        # couteau : la main gauche quitte l'arme et frappe
        if self.knife_anim > 0:
            self.knife_anim -= dt
            t = 1 - max(0, self.knife_anim) / .35
            self.knife.show()
            self.lhand.hide()
            sw = _ease(t)
            self.knife.setPos(-.13 + .25 * sw, -.09 + .06 * math.sin(t * math.pi), .24 + .12 * math.sin(t * math.pi))
            _rotate(self.knife, pitch=10 - 25 * math.sin(t * math.pi), yaw=-55 + 115 * sw, roll=-35 + 70 * sw)
            pos += PVec3(.02, -.04, 0)
        else:
            self.knife.hide()
            self.lhand.show()
        self.rig.setPos(pos)
        _rotate(self.gun, pitch, yaw, roll)
        # LED de munitions
        if self.mag != self._last_mag:
            self._last_mag = self.mag
            for k, led in enumerate(self.leds):
                if k < self.mag:
                    c = (.1, 1, .35) if self.mag > 2 else (1, .55, .1)
                else:
                    c = (.05, .06, .05)
                led.setColorScale(c[0], c[1], c[2], 1)
        if self.mag == 0 and self.has_pistol:
            on = (self.t * 3) % 1 < .5
            self.leds[0].setColorScale(1 if on else .15, .05, .05, 1)
        # flash de bouche
        if self.flash_t > 0:
            self.flash_t -= dt
            self.flash.show()
            self.flash_side.show()
        else:
            self.flash.hide()
            self.flash_side.hide()

    # ------------------------------------------------------------------
    def vm_to_world(self, node, local):
        """Point de la couche de l'arme -> position approximative dans le monde."""
        p = self.vm_root.getRelativePoint(node, PVec3(*local))
        cam = camera
        s = .85    # la couche a un FOV différent : léger facteur d'échelle
        w = cam.world_position + cam.right * (p[0] * s) + cam.up * (p[1] * s) + cam.forward * (p[2] * s)
        return w

    def _update_effects(self, dt):
        g = self.game
        # étincelles
        for s in list(self.sparks):
            s[1] -= dt
            s[0].position += s[2] * dt
            s[2] += Vec3(0, -9, 0) * dt
            if s[1] <= 0:
                destroy(s[0])
                self.sparks.remove(s)
        # douilles et chargeurs : chute, rebonds, repos
        for lst, life_key in ((self.casings, 9.0), (self.dropped, 7.0)):
            for o in list(lst):
                o["age"] += dt
                if not o["rest"]:
                    o["v"] += Vec3(0, -9.8, 0) * dt
                    o["p"] += o["v"] * dt
                    o["rot"] += o["spin"] * dt
                    floor = o["floor"]
                    if o["p"].y <= floor:
                        o["p"].y = floor
                        if abs(o["v"].y) > .6:
                            o["v"].y = -o["v"].y * o["bounce"]
                            o["v"].x *= .6
                            o["v"].z *= .6
                            o["spin"] *= .5
                            if o["kind"] == "casing":
                                # la douille tinte et rebondit sur le métal
                                g.audio.play_var("casing", 3, .35 * min(1, abs(o["v"].y) / 2 + .3),
                                                 pos=(o["p"].x, o["p"].y, o["p"].z), pitch_range=(.9, 1.2),
                                                 max_dist=14)
                            else:
                                g.audio.play_at("mag_drop", (o["p"].x, o["p"].y, o["p"].z), .7,
                                                random.uniform(.9, 1.05), 16)
                        else:
                            o["rest"] = True
                            o["rot"] = Vec3(90 if o["kind"] == "casing" else 0, o["rot"].y, 0)
                    o["np"].setPos(o["p"].x, o["p"].y, o["p"].z)
                    _rotate(o["np"], o["rot"].x, o["rot"].y, o["rot"].z)
                if o["age"] > life_key:
                    o["np"].removeNode()
                    lst.remove(o)
        # fumée au canon après plusieurs tirs rapprochés
        self.heat = max(0.0, self.heat - dt * .6)
        if self.heat > 1.6 and self.flash_t <= 0:
            self.smoke_timer -= dt
            if self.smoke_timer <= 0:
                self.smoke_timer = .09
                self._spawn_smoke()
        for s in list(self.smoke):
            s[1] += dt
            e = s[0]
            e.position += Vec3(0, .25, 0) * dt + s[2] * dt
            k = s[1] / s[3]
            e.scale = .03 + k * .16
            e.color = color.rgba(.75, .75, .78, .22 * (1 - k))
            if k >= 1:
                destroy(e)
                self.smoke.remove(s)
        # giclées extraterrestres
        for s in list(self.splats):
            s[1] -= dt
            s[0].position += s[2] * dt
            s[2] += Vec3(0, -9, 0) * dt
            if s[0].y < .02 or s[1] <= 0:
                destroy(s[0])
                self.splats.remove(s)

    # ==================================================================
    # ACTIONS (gameplay inchangé)
    # ==================================================================
    def start_reload(self):
        g = self.game
        if not self.has_pistol or self.mag >= C.PISTOL_MAG:
            return
        if self.reserve <= 0:
            g.hud.message("Plus de munitions en réserve")
            return
        self.reloading = C.PISTOL_RELOAD_TIME
        self._pending_release = self.slide_locked
        g.audio.play("reload", .7)

    def fire(self):
        g = self.game
        if self.cooldown > 0:
            return
        if self.mag <= 0:
            self.cooldown = .25
            g.audio.play("dry_fire", .9, random.uniform(.95, 1.05))      # déclic sec, dans le silence
            if self.reserve > 0:
                self.start_reload()
            return
        self.mag -= 1
        self.shots_fired += 1
        self.cooldown = C.PISTOL_COOLDOWN
        self.kick = 1.0
        # animation : ressort de recul, culasse, flash en étoile aléatoire
        self.rec_zv -= .9 + random.uniform(0, .2)
        self.rec_pv += 260 + random.uniform(0, 60)
        self.slide_t = 0.0
        if self.mag == 0:
            self.slide_locked = True
        self.flash_t = .045
        self.flash.setTexture(textures.get(f"flash{random.randint(0, 3)}")._texture, 1)
        self.flash_side.setTexture(textures.get(f"flash{random.randint(0, 3)}")._texture, 1)
        self.flash.setR(random.uniform(0, 360))
        sc = random.uniform(.8, 1.35)
        self.flash.setScale(sc)
        self.flash_side.setScale(1, sc, random.uniform(.7, 1.2))
        self.heat += 1.0
        # recul : relève la visée
        g.player.pitch -= C.PISTOL_RECOIL * (.6 if self.aiming else 1.0)
        g.player.yaw += random.uniform(-.6, .6)
        g.player.trauma = min(1, g.player.trauma + .25)
        # détonation sèche + longue réverbération métallique (plus longue dans les grandes
        # salles) + acouphène qui s'estompe : chaque tir se regrette
        g.audio.play("gunshot", 1.0, random.uniform(.95, 1.05))
        room = g.level.room_at(g.player.x, g.player.z)
        big = room is not None and room.type in ("hangar", "engine", "command", "mess")
        g.audio.play("gun_tail_large" if big else "gun_tail_small", .9 if big else .75, random.uniform(.94, 1.04))
        g.audio.play("tinnitus", .8, random.uniform(.97, 1.03))
        g.audio.play("slide_click", .35, random.uniform(.95, 1.1))
        g.inp.rumble(1.0, .8, 140)
        cp = camera.world_position
        mw = self.vm_to_world(self.slide, (0, .02, .16))
        g.lights.muzzle_flash((mw.x, mw.y, mw.z))
        self._eject_casing()
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
            alien = hasattr(best, "mgr")
            self._spawn_splat(hp, d, alien)
            return best
        # impact sur le décor : étincelles + trou qui reste
        hp = Vec3(*hit_p)
        self._spawn_sparks(hp, color.rgb(1, .8, .4), int(6 * C.quality()["particles"]) + 2, Vec3(*normal))
        self._impact_decal(hp, normal)
        g.audio.play_at("spark", (hp.x, hp.y, hp.z), .4)
        return None

    # ------------------------------------------------------------------
    # EFFETS
    # ------------------------------------------------------------------
    def _spawn_sparks(self, pos, col, n, normal=None):
        nrm = normal or Vec3(0, 1, 0)
        for _ in range(n):
            e = Entity(model='cube', color=col, scale=(.012, .012, .04), position=pos, unlit=True)
            v = nrm * random.uniform(1, 3) + Vec3(random.uniform(-2, 2), random.uniform(0, 2.5), random.uniform(-2, 2))
            e.look_at(pos + v)
            self.sparks.append([e, random.uniform(.12, .3), v])

    def _spawn_splat(self, hp, d, alien):
        """Giclée de liquide (vert pour les parasites, noir pour la grande créature)."""
        col = color.rgb(.45, .75, .1) if alien else color.rgb(.06, .05, .04)
        n = int(8 * C.quality()["particles"]) + 3
        for _ in range(n):
            e = Entity(model='sphere', color=col, scale=random.uniform(.015, .035), position=hp,
                       unlit=alien)
            v = -d * random.uniform(.5, 2) + Vec3(random.uniform(-1.5, 1.5), random.uniform(.5, 2.5),
                                                 random.uniform(-1.5, 1.5))
            self.splats.append([e, .8, v])
        if alien:
            s = Entity(model='quad', texture=textures.get('splat_green'), scale=random.uniform(.5, .9),
                       position=(hp.x + d.x * .3, .014, hp.z + d.z * .3), rotation=(90, random.uniform(0, 360), 0),
                       double_sided=True)
            s.setTransparency(TransparencyAttrib.MAlpha)
            s.setDepthOffset(2)
            self.impacts.append(s)
            self._trim_impacts()

    def _impact_decal(self, pos, normal):
        n = Vec3(*normal)
        e = Entity(model='quad', texture=textures.get('bullet_hole'), color=color.white, scale=.07,
                   position=pos + n * .01, double_sided=True)
        e.look_at(pos + n * 2)
        e.rotation_z = random.uniform(0, 360)
        e.setTransparency(TransparencyAttrib.MAlpha)
        e.setDepthOffset(2)
        self.impacts.append(e)
        self._trim_impacts()

    def _trim_impacts(self):
        while len(self.impacts) > 40:
            destroy(self.impacts.pop(0))

    def _world_parent(self):
        wr = self.game.world_root
        return wr if wr is not None else camera

    def _eject_casing(self):
        """Douille éjectée sur la droite, avec rotation et rebonds."""
        start = self.vm_to_world(self.slide, (.016, .027, .03))
        cam = camera
        p = self.game.player
        v = (cam.right * random.uniform(1.6, 2.4) + cam.up * random.uniform(1.4, 2.0)
             + cam.forward * random.uniform(-.2, .4) + Vec3(p.vx, 0, p.vz))
        np_ = self._world_parent().attachNewNode("casing")
        self.casing_tpl.instanceTo(np_)
        np_.setPos(start.x, start.y, start.z)
        self.casings.append({"np": np_, "p": Vec3(start), "v": v, "rot": Vec3(0, random.uniform(0, 360), 0),
                             "spin": Vec3(random.uniform(600, 1100), random.uniform(-400, 400),
                                          random.uniform(-300, 300)),
                             "rest": False, "age": 0.0, "floor": .005, "bounce": .38, "kind": "casing"})
        while len(self.casings) > 24:
            self.casings.pop(0)["np"].removeNode()

    def _drop_magazine(self):
        """Le chargeur vide tombe au sol et y reste quelques secondes."""
        start = self.vm_to_world(self.mag_np, (0, -.06, -.07))
        p = self.game.player
        np_ = self._world_parent().attachNewNode("dropped_mag")
        self.mag_tpl.instanceTo(np_)
        self.dropped.append({"np": np_, "p": Vec3(start), "v": Vec3(p.vx * .8, -1.0, p.vz * .8),
                             "rot": Vec3(0, p.yaw, 0), "spin": Vec3(random.uniform(-200, 200), 0,
                                                                     random.uniform(-150, 150)),
                             "rest": False, "age": 0.0, "floor": .012, "bounce": .25, "kind": "mag"})
        while len(self.dropped) > 6:
            self.dropped.pop(0)["np"].removeNode()

    def _spawn_smoke(self):
        pos = self.vm_to_world(self.slide, (0, .02, .14))
        e = Entity(model='quad', texture=textures.get('smoke'), billboard=True, position=pos, scale=.03,
                   color=color.rgba(.75, .75, .78, .2))
        e.setTransparency(TransparencyAttrib.MAlpha)
        e.setDepthWrite(False)
        e.setLightOff(1)
        e.setBin('transparent', 20)
        drift = Vec3(random.uniform(-.05, .05), 0, random.uniform(-.05, .05))
        self.smoke.append([e, 0.0, drift, random.uniform(.9, 1.4)])
        while len(self.smoke) > int(14 * C.quality()["particles"]) + 2:
            destroy(self.smoke.pop(0)[0])

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
        g.audio.play_var("knife_swing", 2, .45)          # la lame fend l'air, à peine audible
        cp = camera.world_position
        fw = camera.forward
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
        spider = hit is not None and hasattr(hit, "mgr")
        if spider and not hit.aware:
            # attaque par surprise : mort instantanée et totalement silencieuse
            hit.on_hit(999, hit.center3(), False, silent=True)
            self._spawn_splat(Vec3(*hit.center3()), fw, True)
            g.audio.play("knife_flesh", .4, random.uniform(.9, 1.05))
            g.inp.rumble(.4, .2, 100)
            g.hud.message("Mise à mort silencieuse", color.rgb(.55, .7, .55))
            self._wear()
            return
        # un coup de couteau reste discret (petit rayon, rarement entendu par la bête)
        g.noise((cp.x, cp.y, cp.z), C.NOISE_KNIFE, "knife")
        if hit is not None:
            mult = C.KNIFE_STEALTH_MULT if not getattr(hit, "aware", True) else 1
            hit.on_hit(C.KNIFE_DAMAGE * mult, hit.center3(), False)
            c = hit.center3()
            self._spawn_splat(Vec3(*c), fw, spider)
            g.audio.play("knife_flesh", .5, random.uniform(.9, 1.1))          # impact humide
            if spider:
                g.audio.play("knife_crack", .4, random.uniform(.9, 1.15))     # craquement de carapace
            g.inp.rumble(.6, .3, 120)
            self._wear()

    def _wear(self):
        g = self.game
        broke = g.inventory.wear_knife()
        if broke:
            g.audio.play("knife_break", .7)
            g.hud.message("Ton couteau s'est brisé !", color.orange)

    def destroy(self):
        for s in self.sparks + self.splats:
            destroy(s[0])
        for s in self.smoke:
            destroy(s[0])
        for e in self.impacts:
            destroy(e)
        for o in self.casings + self.dropped:
            o["np"].removeNode()
        self.rig.removeNode()
        self.game.postfx.show_viewmodel(False)


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)
