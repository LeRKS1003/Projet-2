# -*- coding: utf-8 -*-
"""
shuttle.py — Navette pilotable (phase TPS) et caméra à la troisième personne.

Gameplay (inchangé) :
  * vol spatial 6 degrés de liberté simplifié, avec inertie : poussée
    avant/arrière, strafe, montée/descente, tangage/lacet/roulis, boost ;
  * assistance de vol (F / Triangle) : annule la dérive, freine quand on lâche
    la poussée, remet le roulis à plat ; sans assistance : inertie pure ;
  * régulateur : la poussée règle une vitesse cible ; frein d'urgence (X / Rond) ;
  * rotation avec courbe de réponse, vitesse max et amortissement réglables ;
  * aide à l'approche du hangar (pointillés lumineux + vitesse conseillée)
    et avertissement d'obstacle droit devant ;
  * caméra derrière et au-dessus de la navette, avec retard (lissage) ;
  * collisions sphère/boîte (orientée) contre la coque et les débris ->
    dégâts sur la barre d'intégrité ;
  * séquences scriptées : atterrissage automatique dans le hangar,
    décollage final (victoire).

Rendu (style industriel rétro-futuriste) :
  * coque en mesh personnalisé extrudé (sections octogonales biseautées) :
    fuselage profilé, nez effilé, cockpit en saillie, deux nacelles moteurs
    latérales sur pylônes, ailerons, dérive, train d'atterrissage replié
    (qui se déploie pendant l'atterrissage) ;
  * « greebles » asymétriques : antennes, tuyaux, trappes, radiateurs, boîtiers ;
  * livrée peinte générée par code : blanc cassé usé, bandes orange de
    sécurité, rayures, suie près des moteurs, immatriculation peinte ;
  * verrière sombre réfléchissante avec écrans de bord visibles ;
  * tuyères émissives bleu-blanc, flammes additives qui s'allongent, traînées
    de particules, lumière ponctuelle qui éclaire la coque et le grand vaisseau ;
  * propulseurs de manœuvre (RCS) qui crachent de brèves bouffées ;
  * feux de navigation (rouge / vert / blanc clignotant) avec halo additif ;
  * phare avant (spotlight) ; vibration au boost et inclinaison dans les virages.
"""
import math
import random

import numpy as np
from panda3d.core import (Spotlight as PSpot, PointLight as PPoint, PerspectiveLens, Vec4, Vec3 as PVec3,
                          TransparencyAttrib, NodePath, Material)
from ursina import Entity, Vec3, camera, color, destroy, application

import config as C
import textures
from geometry import MeshBuilder
from lighting import additive
import loot

REGISTRATION = "MSV-417  SELENE"

# couleurs de la livrée (multipliées par la texture)
WHITE = (.9, .88, .84, 1)
GREY = (.55, .55, .56, 1)
DARK = (.22, .22, .24, 1)
ORANGE = (.95, .45, .08, 1)
SOOT = (.28, .27, .26, 1)

# fuselage : (z, cx, cy, largeur, hauteur, chanfrein)
FUSELAGE = [(-3.3, 0, .1, 1.9, 1.25, .35), (-2.7, 0, .12, 2.45, 1.55, .45), (-1.0, 0, .12, 2.65, 1.7, .5),
            (.9, 0, .06, 2.5, 1.6, .5), (2.4, 0, -.04, 2.0, 1.25, .45), (3.4, 0, -.14, 1.25, .82, .32),
            (4.05, 0, -.2, .45, .32, .12)]
CANOPY = [(.7, 0, .86, 1.5, .08, .03), (1.4, 0, .98, 1.45, .46, .18), (2.45, 0, .76, 1.1, .38, .14),
          (3.05, 0, .52, .6, .1, .04)]


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lerp_angle(a, b, t):
    d = (b - a + 180) % 360 - 180
    return a + d * t


def _livery(rng):
    """
    Livrée de la coque (u = longueur arrière -> avant, v = tour de section).
    Tour : v=0 en bas au centre, v~0.25 flanc droit, v~0.5 dessus, v~0.75 flanc gauche.
    La ligne 0 de l'image correspond à v = 1.
    """
    W, H = 1024, 512
    n = textures.fractal_noise(H, W, rng, 6, base=3)
    alb = np.full((H, W, 3), .86, np.float32) * (.93 + .07 * n)[..., None]
    h = np.full((H, W), .5, np.float32)
    rough = np.full((H, W), .55, np.float32)
    uu = np.linspace(0, 1, W)[None, :].repeat(H, 0)
    vv = (1 - np.linspace(0, 1, H))[:, None].repeat(W, 1)
    # lignes de panneaux (creux) + rivets
    seams = (np.abs(((uu * 14) % 1) - .5) > .493) | (np.abs(((vv * 16) % 1) - .5) > .49)
    h[seams] = .1
    alb[seams] *= .72
    yy, xx = np.mgrid[0:H, 0:W]
    riv = ((xx % 36) == 4) & ((yy % 32) == 4)
    h[riv] = .95
    # bandes orange de sécurité (autour du fuselage) + filet sombre
    band = ((uu > .6) & (uu < .66)) | ((uu > .675) & (uu < .69))
    alb[band] = np.array([.95, .45, .08]) * (.85 + .15 * n[band])[:, None]
    stripe = (np.abs(vv - .5) < .035) & (uu < .55)                  # bande dorsale
    alb[stripe] = np.array([.95, .45, .08]) * .9
    # zone « danger » jaune/noir près du sas (flanc droit)
    hz = (uu > .42) & (uu < .5) & (np.abs(vv - .2) < .04)
    chk = (((xx + yy) // 10) % 2 == 0)
    alb[hz & chk] = (.9, .75, .1)
    alb[hz & ~chk] = (.08, .08, .08)
    # usure : éclats de peinture révélant le métal
    chips = textures.fractal_noise(H, W, rng, 5, base=6)
    bare = chips > .7
    alb[bare] = (.45 + .1 * n[bare])[:, None].repeat(3, 1)
    rough[bare] = .25
    h[bare] -= .12
    # rayures
    from PIL import Image, ImageDraw
    img = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(img)
    for _ in range(160):
        x0, y0 = rng.integers(0, W), rng.integers(0, H)
        ln, a = rng.integers(8, 70), rng.uniform(-.4, .4)
        d.line((x0, y0, x0 + np.cos(a) * ln, y0 + np.sin(a) * ln), fill=int(rng.integers(90, 255)))
    scr = np.asarray(img, np.float32) / 255
    alb *= (1 - scr * .3)[..., None]
    h -= scr * .2
    # suie et brûlures près des moteurs (arrière)
    soot = np.clip((.2 - uu) / .2, 0, 1) ** 1.3 * (.6 + .4 * textures.fractal_noise(H, W, rng, 4, base=4))
    alb *= (1 - soot * .75)[..., None]
    rough = np.clip(rough + soot * .4, 0, 1)
    # immatriculation peinte sur les deux flancs (lisible de l'extérieur)
    textures.draw_text_on(alb, REGISTRATION, int(W * .36), int(H * (1 - .25)), 30, (.1, .1, .12))
    textures.draw_text_on(alb, REGISTRATION, int(W * .36), int(H * (1 - .75)), 30, (.1, .1, .12), rotate=180)
    textures.draw_text_on(alb, "NO STEP", int(W * .47), int(H * (1 - .43)), 14, (.3, .3, .3))
    return np.clip(alb, 0, 1), h, np.clip(rough, .08, 1), (.6, 38, 1.8)


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
        # entrées mémorisées pour les effets visuels (RCS, inclinaison)
        self.in_strafe = self.in_vert = self.in_thrust = 0.0
        # pilotage
        self.assist = C.SHIP_ASSIST_DEFAULT
        self.target_speed = 0.0
        self.braking = False
        self.cam_far = False
        self.obstacle_warn = 0.0       # secondes avant impact (0 = rien devant)
        self._warn_timer = 0.0
        self.approach = None           # (distance, vitesse conseillée) près du hangar
        self.bank = 0.0
        self.tilt = 0.0
        self.gear = 0.0          # 0 = replié, 1 = sorti
        self.q = C.quality()
        # particules (traînées et bouffées RCS), dans le monde
        self.fx_root = application.base.render.attachNewNode("shuttle_fx")
        additive(self.fx_root, 7)
        self.particles = []
        self._trail_acc = 0.0
        self._rcs_cd = {}
        self._build_model()
        # phare avant (éclaire la coque du grand vaisseau en approche)
        self.spot = PSpot("shuttle_headlight")
        lens = PerspectiveLens()
        lens.setFov(40)
        lens.setNearFar(.5, 160)
        self.spot.setLens(lens)
        self.spot.setExponent(10)
        self.spot.setAttenuation(PVec3(1, 0, 0.0005))
        self.spot.setColor(Vec4(1.7, 1.65, 1.5, 1))
        self.spot_np = self.model.attachNewNode(self.spot)
        self.spot_np.setPos(0, -.25, 4.1)
        application.base.render.setLight(self.spot_np)
        # lumière des réacteurs : éclaire la coque et les parois proches
        self.eng_light = PPoint("shuttle_engine_light")
        self.eng_light.setAttenuation(PVec3(1, 0, 0.012))
        self.eng_light.setColor(Vec4(0, 0, 0, 1))
        self.eng_np = self.model.attachNewNode(self.eng_light)
        self.eng_np.setPos(0, .1, -5.2)
        application.base.render.setLight(self.eng_np)
        a = game.audio
        self.engine_snd = a.loop("ship_engine", "ship_engine", .8)
        self.boost_snd = a.loop("ship_boost", "ship_boost", .6)

    # ==================================================================
    # MODÈLE
    # ==================================================================
    def _build_model(self):
        # le « modèle » est un enfant du nœud physique : on peut l'incliner et
        # le faire vibrer sans toucher à la trajectoire
        self.model = self.root.attachNewNode("shuttle_model")
        hull = MeshBuilder(uv_scale=1.0)
        hull.loft(FUSELAGE, WHITE)
        livery = textures.material("shuttle_livery", custom=_livery)
        hull_np = self.model.attachNewNode(hull.make_geom_node("shuttle_hull"))
        textures.apply_material(hull_np, livery)

        # --- verrière : verre sombre réfléchissant ---------------------------
        cn = MeshBuilder()
        cn.loft(CANOPY, (.03, .05, .07, .78), cap_start=False, cap_end=False)
        self.canopy = self.model.attachNewNode(cn.make_geom_node("canopy", tangents=False))
        m = Material()
        m.setSpecular((1.6, 1.6, 1.7, 1))
        m.setShininess(120)
        self.canopy.setMaterial(m, 1)
        self.canopy.setTransparency(TransparencyAttrib.MAlpha)
        self.canopy.setBin('transparent', 5)
        # tableau de bord visible à travers la vitre (émissif discret)
        dash = MeshBuilder()
        dash.box((0, .74, 1.7), (1.2, .06, .5), (.05, .05, .06, 1))
        dash.box((-.35, .8, 1.75), (.3, .02, .18), (.1, .55, .3, 1))
        dash.box((0, .8, 1.78), (.28, .02, .16), (.1, .35, .7, 1))
        dash.box((.36, .8, 1.74), (.26, .02, .15), (.7, .35, .08, 1))
        dash.box((0, .9, 1.25), (.5, .5, .08), (.08, .08, .09, 1))              # sièges
        self.dash = self.model.attachNewNode(dash.make_geom_node("dashboard", tangents=False))
        self.dash.setLightOff(2)
        self.dash.setColorScale(.8, .8, .8, 1)

        # --- nacelles moteurs, pylônes, ailerons, dérive ---------------------
        parts = MeshBuilder(uv_scale=1.2)
        self.nozzles = []
        for s in (-1, 1):
            nx = s * 2.0
            nac = [(-3.55, nx, .0, .95, .95, .3), (-3.2, nx, .0, 1.08, 1.08, .34), (-1.0, nx, .0, 1.1, 1.1, .35),
                   (-.1, nx, .0, .9, .9, .3), (.3, nx, 0, .55, .55, .18)]
            parts.loft(nac, WHITE, colors=lambda si, k: SOOT if si == 0 else (WHITE if si > 1 else GREY))
            parts.bevel_box((s * 1.45, .05, -1.6), (.9, .28, 1.5), .08, GREY, DARK)         # pylône
            parts.bevel_box((s * 2.0, .62, -1.8), (.5, .16, 1.2), .05, DARK)                  # capot d'accès
            # ailerons / ailes courtes en flèche
            parts.bevel_box((s * 2.85, -.18, -1.4), (1.3, .12, 1.6), .04, WHITE, GREY, rot=(0, s * -12, s * -6))
            parts.bevel_box((s * 3.45, -.12, -1.8), (.14, .5, .9), .04, ORANGE, rot=(0, s * -12, 0))  # saumon
            # tuyère
            parts.cylinder((nx, 0, -3.72), .44, .34, DARK, 16, 'z')
            parts.cylinder((nx, 0, -3.9), .5, .08, SOOT, 16, 'z')
            self.nozzles.append((nx, 0.0, -3.95))
        # dérive (aileron vertical) légèrement inclinée vers l'arrière
        parts.bevel_box((0, 1.25, -2.55), (.14, 1.35, 1.35), .05, WHITE, GREY, rot=(-24, 0, 0))
        parts.bevel_box((0, 1.78, -2.95), (.16, .22, .55), .04, ORANGE, rot=(-24, 0, 0))
        parts.bevel_box((.45, -.72, -2.6), (.08, .45, .8), .03, GREY, rot=(0, 0, 25))         # dérives ventrales
        parts.bevel_box((-.45, -.72, -2.6), (.08, .45, .8), .03, GREY, rot=(0, 0, -25))
        # trappes du train d'atterrissage (lignes sur le ventre)
        for (x, z) in ((0, 2.3), (-.8, -1.4), (.8, -1.4)):
            parts.box((x, -.745, z), (.55, .012, .9), DARK)
        self._greebles(parts)
        parts_np = self.model.attachNewNode(parts.make_geom_node("shuttle_parts"))
        textures.apply_material(parts_np, "painted")

        # --- émissifs : fond des tuyères, feux, hublots -------------------------
        self.nozzle_glow = []
        for (x, y, z) in self.nozzles:
            g = MeshBuilder()
            g.cylinder((0, 0, 0), .36, .02, (.55, .75, 1, 1), 16, 'z')
            n = self.model.attachNewNode(g.make_geom_node("nozzle_glow", tangents=False))
            n.setPos(x, y, z + .12)
            n.setLightOff(2)
            self.nozzle_glow.append(n)
        # flammes : cônes additifs, et halos
        self.flames = []
        for (x, y, z) in self.nozzles:
            fl = MeshBuilder()
            fl.cone((0, 0, 0), .36, 1.0, (.55, .78, 1, .85), (.2, .35, 1, 0), 16, (0, 0, -1))
            fl.cone((0, 0, 0), .2, 1.4, (.95, .97, 1, .9), (.4, .6, 1, 0), 12, (0, 0, -1))
            fnp = self.model.attachNewNode(fl.make_geom_node("flame", tangents=False))
            fnp.setPos(x, y, z)
            fnp.setTwoSided(True)
            additive(fnp, 6)
            halo = self._halo(self.model, (x, y, z - .2), 2.2, (.5, .7, 1))
            self.flames.append((fnp, halo))
        # feux de navigation avec halo
        self.nav_l = self._halo(self.model, (-3.5, .15, -1.9), 1.1, (1, .1, .08))
        self.nav_r = self._halo(self.model, (3.5, .15, -1.9), 1.1, (.1, 1, .25))
        self.nav_t = self._halo(self.model, (0, 1.95, -3.2), 1.0, (1, 1, 1))
        lights = MeshBuilder()
        for p, c in (((-3.5, .15, -1.9), (1, .1, .08, 1)), ((3.5, .15, -1.9), (.1, 1, .25, 1)),
                     ((0, 1.95, -3.2), (1, 1, 1, 1))):
            lights.bevel_box(p, (.12, .12, .12), .03, c)
        # hublots latéraux éclairés
        for s in (-1, 1):
            for k in range(3):
                lights.box((s * 1.33, .35, -.6 + k * .55), (.02, .16, .26), (.9, .7, .4, 1))
        lights.box((0, -.22, 4.02), (.2, .1, .02), (1, 1, .95, 1))                   # optique du phare
        lnp = self.model.attachNewNode(lights.make_geom_node("nav_lights", tangents=False))
        lnp.setLightOff(2)
        self.nav_meshes = lnp

        # --- train d'atterrissage (replié en vol, sorti à l'atterrissage) ------
        self.gear_nodes = []
        for (x, z) in ((0, 2.3), (-.8, -1.4), (.8, -1.4)):
            gnode = self.model.attachNewNode("gear")
            gm = MeshBuilder(uv_scale=.5)
            gm.bevel_box((0, -.3, 0), (.12, .6, .12), .03, GREY)
            gm.bevel_box((0, -.62, 0), (.3, .08, .5), .03, DARK)
            gm.cylinder((0, -.15, .12), .05, .35, (.6, .6, .62, 1), 8, 'y')
            gnp = gnode.attachNewNode(gm.make_geom_node("gear_leg"))
            textures.apply_material(gnp, "brushed")
            gnode.setPos(x, -.72, z)
            self.gear_nodes.append(gnode)
        # propulseurs RCS : (position locale, direction d'éjection)
        self.rcs = {
            "fl": ((-1.3, .2, 2.9), (-1, 0, 0)), "fr": ((1.3, .2, 2.9), (1, 0, 0)),
            "rl": ((-1.1, .3, -2.9), (-1, 0, 0)), "rr": ((1.1, .3, -2.9), (1, 0, 0)),
            "fu": ((0, .75, 3.0), (0, 1, 0)), "fd": ((0, -.65, 3.0), (0, -1, 0)),
            "ru": ((0, .8, -3.0), (0, 1, 0)), "rd": ((0, -.6, -3.0), (0, -1, 0)),
        }
        self._update_gear(0)

    def _greebles(self, mb):
        """Détails de surface asymétriques : antennes, tuyaux, trappes, radiateurs, boîtiers."""
        rng = random.Random(417)
        # mât d'antenne + fouet (arrière gauche) et antenne plate (avant droit)
        mb.bevel_box((-.55, 1.05, -1.9), (.06, .5, .06), .01, GREY)
        mb.bevel_box((-.55, 1.62, -1.9), (.018, .7, .018), .005, (.7, .7, .7, 1))
        mb.bevel_box((.5, .92, .2), (.35, .03, .22), .01, DARK, rot=(0, 20, 0))
        mb.bevel_box((.5, .87, .2), (.05, .1, .05), .01, GREY)
        # tuyaux le long du flanc gauche
        for k, y in enumerate((-.1, .12)):
            mb.cylinder((-1.36, y, -.6), .045, 3.6, (.5, .45, .35, 1) if k else GREY, 8, 'z')
        for z in (-2.2, -1.2, -.2, .8):
            mb.bevel_box((-1.35, .01, z), (.08, .34, .08), .015, DARK)            # colliers de fixation
        # radiateur à ailettes sur le flanc droit
        for k in range(9):
            mb.box((1.36, .05, -1.9 + k * .16), (.1, .5, .03), (.3, .3, .32, 1))
        mb.bevel_box((1.33, .05, -1.26), (.05, .6, 1.45), .02, DARK)
        # trappes et boîtiers techniques
        for (x, y, z, w, h, d) in ((.35, .9, -1.1, .5, .05, .6), (-.4, .92, .6, .35, .06, .4),
                                   (0, .95, -2.4, .7, .06, .5), (.7, -.8, .5, .4, .05, .5)):
            mb.bevel_box((x, y, z), (w, h, d), .015, DARK)
        for _ in range(7):
            x = rng.uniform(-.8, .8)
            z = rng.uniform(-2.6, 1.0)
            mb.bevel_box((x, .9 + rng.uniform(0, .06), z), (rng.uniform(.1, .25), rng.uniform(.05, .14),
                                                            rng.uniform(.1, .3)), .01, rng.choice([GREY, DARK]))
        # dôme de capteurs sous le nez, sas latéral (droite)
        mb.cylinder((0, -.52, 3.0), .16, .12, DARK, 12, 'y')
        mb.box((1.335, .1, -.1), (.02, .95, .75), GREY)
        mb.box((1.345, .1, -.1), (.01, .02, .75), DARK)
        # blocs RCS
        for (x, y, z) in ((-1.25, .2, 2.9), (1.25, .2, 2.9), (-1.05, .3, -2.9), (1.05, .3, -2.9)):
            mb.bevel_box((x, y, z), (.2, .18, .22), .03, DARK)

    def _halo(self, parent, pos, size, col):
        """Halo additif toujours face à la caméra (feux, tuyères)."""
        mb = MeshBuilder()
        s = size / 2
        mb.poly([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], (0, 0, -1), (1, 1, 1, 1),
                [(0, 0), (1, 0), (1, 1), (0, 1)])
        n = parent.attachNewNode(mb.make_geom_node("halo", tangents=False))
        n.setPos(*pos)
        n.setBillboardPointEye()
        n.setTexture(textures.get('glow')._texture)
        n.setColorScale(col[0], col[1], col[2], 1)
        additive(n, 8)
        n.setPythonTag('col', col)
        return n

    def _update_gear(self, k):
        self.gear = k
        for g in self.gear_nodes:
            # pivote depuis la soute : replié à plat, puis vertical
            g.setP(-90 * (1 - k))
            g.setScale(1, .2 + .8 * k, 1)

    # ==================================================================
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
        self.in_thrust, self.in_strafe, self.in_vert = thrust, strafe, vert
        if inp.pressed("ship_assist"):
            self.assist = not self.assist
            self.game.hud.message("Assistance de vol : " + ("ACTIVÉE" if self.assist else "DÉSACTIVÉE (inertie pure)"))
            self.game.audio.play("beep", .5)
        if inp.pressed("ship_camera"):
            self.cam_far = not self.cam_far
        self.braking = inp.held("ship_brake")
        # boost limité
        self.boosting = boost and self.boost > 0 and thrust > 0
        if self.boosting:
            self.boost = max(0.0, self.boost - C.SHIP_BOOST_DRAIN * dt)
        else:
            self.boost = min(C.SHIP_BOOST_MAX, self.boost + C.SHIP_BOOST_REGEN * dt)
        mult = C.SHIP_BOOST_MULT if self.boosting else 1.0
        vmax = C.SHIP_MAX_SPEED * mult
        self.throttle = max(abs(thrust), abs(strafe) * .6, abs(vert) * .6) * mult
        # --- rotation : taux visé (courbe de réponse) + amortissement --------
        tp = pitch * C.SHIP_MAX_TURN
        ty = yaw * C.SHIP_MAX_TURN
        tr = roll * C.SHIP_ROLL_RATE
        f, r, u = self.root.forward, self.root.right, self.root.up
        if self.assist and abs(roll) < .05:
            # remet doucement le roulis à plat (aile horizontale)
            bank = math.degrees(math.atan2(r.y, u.y))
            if abs(u.y) > .2:
                tr = max(-C.SHIP_ROLL_RATE, min(C.SHIP_ROLL_RATE, bank * C.SHIP_ASSIST_LEVEL))
        k = min(1.0, dt * C.SHIP_TURN_DAMP)
        self.rate_p += (tp - self.rate_p) * k
        self.rate_y += (ty - self.rate_y) * k
        self.rate_r += (tr - self.rate_r) * k
        if self.braking:
            damp = math.exp(-C.SHIP_BRAKE_RATE * dt)
            self.rate_p *= damp
            self.rate_y *= damp
            self.rate_r *= damp
        # rotation relative au repère de la navette (Panda : H=-lacet, P=-tangage)
        self.root.setHpr(self.root, -self.rate_y * dt, -self.rate_p * dt, self.rate_r * dt)
        f, r, u = self.root.forward, self.root.right, self.root.up
        # --- translation ---------------------------------------------------
        if self.assist:
            # vitesses dans le repère de la navette
            vf, vr, vu = self.vel.dot(f), self.vel.dot(r), self.vel.dot(u)
            if C.SHIP_CRUISE:
                # régulateur : la poussée fait varier la vitesse cible
                self.target_speed += thrust * C.SHIP_CRUISE_RATE * mult * dt
                self.target_speed = max(-vmax * .3, min(vmax, self.target_speed))
                if not self.boosting and self.target_speed > C.SHIP_MAX_SPEED:
                    self.target_speed += (C.SHIP_MAX_SPEED - self.target_speed) * min(1, dt * 1.5)
                acc = C.SHIP_THRUST * mult
                dv = self.target_speed - vf
                vf += max(-acc * dt, min(acc * dt, dv))
            elif abs(thrust) > .05:
                vf += thrust * C.SHIP_THRUST * mult * dt
            else:
                vf *= math.exp(-C.SHIP_ASSIST_BRAKE * dt)      # freine seule quand on lâche
            # dérive latérale / verticale annulée : la navette va là où pointe le nez
            if abs(strafe) > .05:
                vr += strafe * C.SHIP_STRAFE * dt
            else:
                vr *= math.exp(-C.SHIP_ASSIST_DRIFT * dt)
            if abs(vert) > .05:
                vu += vert * C.SHIP_VERTICAL * dt
            else:
                vu *= math.exp(-C.SHIP_ASSIST_DRIFT * dt)
            vr = max(-vmax * .6, min(vmax * .6, vr))
            vu = max(-vmax * .6, min(vmax * .6, vu))
            self.vel = f * vf + r * vr + u * vu
        else:
            # inertie pure (Newton), avec une très légère traînée
            acc = f * (thrust * C.SHIP_THRUST * mult) + r * (strafe * C.SHIP_STRAFE) + u * (vert * C.SHIP_VERTICAL)
            self.vel += acc * dt
            self.vel *= max(0.0, 1 - C.SHIP_DRAG * .25 * dt)
            self.target_speed = self.vel.dot(f)
        # frein / stabilisation d'urgence
        if self.braking:
            self.vel *= math.exp(-C.SHIP_BRAKE_RATE * dt)
            self.target_speed *= math.exp(-C.SHIP_BRAKE_RATE * dt)
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
                # un choc coupe le régulateur (sinon la navette repartirait dans la paroi)
                self.target_speed = min(self.target_speed, max(0.0, self.vel.dot(self.root.forward)))
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
        """
        Caméra TPS lissée : derrière et au-dessus de la navette. Un peu plus de
        retard au boost et en virage (sensation de poids), retour rapide quand on
        vole droit. Option caméra éloignée (C / R3).
        """
        f = self.root.forward
        u = self.root.up
        dist = C.TPS_CAM_FAR_DISTANCE if self.cam_far else C.TPS_CAM_DISTANCE
        height = C.TPS_CAM_FAR_HEIGHT if self.cam_far else C.TPS_CAM_HEIGHT
        target = self.root.world_position - f * dist + u * height
        turning = min(1.0, (abs(self.rate_y) + abs(self.rate_p)) / 90)
        smooth = C.TPS_CAM_SMOOTH * (1.5 - .75 * turning) * (.65 if self.boosting else 1.0)
        k = 1 - math.exp(-smooth * dt)
        self.cam_pos = self.cam_pos + (target - self.cam_pos) * k
        self.cam_up = (self.cam_up + (u - self.cam_up) * min(1, dt * 3)).normalized()
        camera.position = self.cam_pos
        look = self.root.world_position + f * 8 + u * 1.2
        # lookAt de Panda3D (compatible avec toutes les versions d'Ursina)
        camera.lookAt(PVec3(look.x, look.y, look.z), PVec3(self.cam_up.x, self.cam_up.y, self.cam_up.z))
        shake = self.game.shake_amount
        if self.boosting:
            shake = max(shake, .12)               # vibration au boost
        if shake > 0:
            camera.rotation_z += random.uniform(-1, 1) * shake * 3
            camera.rotation_x += random.uniform(-1, 1) * shake * 2
        base_fov = C.FOV - 10
        camera.fov += (base_fov + min(12, self.speed * .35) - camera.fov) * min(1, dt * 3)

    # ------------------------------------------------------------------
    def update_pilot_aids(self, dt, colliders, exterior):
        """Avertissement d'obstacle (droit devant, < N s) et aide à l'approche du hangar."""
        p = self.root.world_position
        self._warn_timer -= dt
        if self._warn_timer <= 0:
            self._warn_timer = .15
            self.obstacle_warn = 0.0
            sp = self.speed
            if sp > 3 and not exterior.in_hangar_entrance(p):
                d = self.vel / sp
                horizon = sp * C.SHIP_COLLISION_WARN
                R = C.SHIP_RADIUS + .6
                best = None
                for col in colliders:
                    c, rad = col.bound()
                    oc = Vec3(c[0] - p.x, c[1] - p.y, c[2] - p.z)
                    tproj = oc.dot(d)
                    if tproj < 0 or tproj - rad > horizon:
                        continue
                    if oc.length_squared() - tproj * tproj > (rad + R) ** 2:
                        continue
                    # affinage : on échantillonne finement la trajectoire sur la zone utile
                    t0 = max(0.0, tproj - rad)
                    t1 = min(horizon, tproj + rad)
                    step = max(1.2, (t1 - t0) / 40)
                    tt = t0
                    while tt <= t1:
                        q = p + d * tt
                        cl = col.closest(q)
                        if (q - cl).length() < R:
                            if best is None or tt < best:
                                best = tt
                            break
                        tt += step
                if best is not None:
                    self.obstacle_warn = best / sp
        # aide à l'approche
        e = exterior.entrance
        mouth = Vec3(e.x, e.y, 0)
        dm = (p - mouth).length()
        if dm < C.SHIP_APPROACH_DIST and p.z < 4:
            self.approach = (dm, C.SHIP_APPROACH_SPEED)
        else:
            self.approach = None
        self._update_guide(dt, exterior)

    def _update_guide(self, dt, exterior):
        """Pointillés lumineux sur la trajectoire idéale (axe de l'ouverture du hangar)."""
        if not hasattr(self, "guide"):
            self.guide = []
            e = exterior.entrance
            for k in range(22):
                z = -58 + k * 3.0
                n = self._halo(application.base.render, (e.x, e.y - .8, z), .7, (.3, 1, .5))
                n.hide()
                self.guide.append(n)
            self._guide_t = 0.0
        self._guide_t += dt
        show = self.approach is not None
        for k, n in enumerate(self.guide):
            if show:
                n.show()
                # vague lumineuse qui court vers l'ouverture
                w = .35 + .65 * max(0.0, math.sin(self._guide_t * 5 - k * .45)) ** 4
                n.setColorScale(.25 * w, .9 * w, .45 * w, 1)
            else:
                n.hide()

    def cinematic_camera(self, dt, cam_point):
        k = 1 - math.exp(-2.0 * dt)
        self.cam_pos = self.cam_pos + (Vec3(*cam_point) - self.cam_pos) * k
        camera.position = self.cam_pos
        p = self.root.world_position
        camera.lookAt(PVec3(p.x, p.y, p.z), PVec3(0, 1, 0))

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
        application.base.render.setLight(self.eng_np)

    def _update_auto(self, dt):
        self.auto_t += dt
        t = self.auto_t
        self.in_strafe = self.in_vert = 0.0
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
            self.in_vert = -.6 * (1 - k)            # bouffées RCS pendant la descente
            self._update_gear(_smooth(t / 1.4))     # le train sort
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
                application.base.render.clearLight(self.eng_np)
                self.on_done()
        elif self.auto == "lift":
            k = _smooth(t / 1.8)
            self.root.y = 1.35 + (4.0 - 1.35) * k
            self.throttle = .6
            self.in_vert = .6
            self._update_gear(1 - _smooth(t / 1.6))   # le train rentre
            if t >= 1.8:
                self.auto, self.auto_t = "exit", 0.0
                self.vel = Vec3(0, 0, 0)
        elif self.auto == "exit":
            self.throttle = 1.6
            self.boosting = t > 2.0
            self.vel += self.root.forward * 16 * dt
            self.root.position += self.vel * dt
            self.root.rotation_x = max(-8, -t * 2)
            if t >= 7.5:
                self.auto = None
                self.on_done()

    # ==================================================================
    # EFFETS VISUELS
    # ==================================================================
    def _visuals(self, dt):
        t = self.blink_t
        th = self.throttle if not self.landed else 0.0
        # feux : rouge / vert fixes, blanc à éclats sur la dérive
        on = (t % 1.2) < .12
        self.nav_t.setColorScale((1, 1, 1, 1) if on else (0, 0, 0, 1))
        for h in (self.nav_l, self.nav_r):
            c = h.getPythonTag('col')
            p = .75 + .25 * math.sin(t * 3)
            h.setColorScale(c[0] * p, c[1] * p, c[2] * p, 1)
        # tuyères et flammes (bleu-blanc, s'intensifient avec la poussée)
        boost = 1.0 if self.boosting else 0.0
        glow = .25 + .75 * min(1.5, th)
        for n in self.nozzle_glow:
            n.setColorScale(.5 * glow + .3 * boost, .7 * glow + .2 * boost, glow, 1)
        spd = min(1.0, self.speed / C.SHIP_MAX_SPEED)
        ln = (.15 + th * .8 + spd * .45 + boost * .6) * (1 + random.uniform(-.06, .06))
        wid = .8 + th * .2 + boost * .1
        for fl, halo in self.flames:
            fl.setScale(wid, wid, ln)
            fi = min(1.0, .15 + th * .7)
            fl.setColorScale(fi * (.8 + .2 * boost), fi * (.85 + .15 * boost), min(1.0, fi * 1.1), 1)
            hs = .4 + th * .9 + boost * .5
            halo.setScale(hs)
            halo.setColorScale(.4 * glow, .6 * glow, glow, 1)
            if th < .03:
                fl.hide()
            else:
                fl.show()
        k = (th * 2.2 + boost * 1.5)
        self.eng_light.setColor(Vec4(.5 * k, .7 * k, 1.1 * k, 1))
        # inclinaison visuelle dans les virages + vibration au boost
        target_bank = max(-28, min(28, -self.rate_y * .35 - self.in_strafe * 10))
        target_tilt = max(-10, min(10, -self.in_vert * 5 + self.rate_p * .06))
        kk = min(1, dt * 4)
        self.bank += (target_bank - self.bank) * kk
        self.tilt += (target_tilt - self.tilt) * kk
        jit = (.012 + .02 * boost) * th if not self.landed else 0
        self.model.setPos(random.uniform(-1, 1) * jit, random.uniform(-1, 1) * jit, 0)
        self.model.setHpr(0, -self.tilt, self.bank)
        # particules
        if not self.landed:
            self._emit_trails(dt, th, boost)
            self._emit_rcs(dt)
        self._update_particles(dt)
        # sons
        self.engine_snd.set(0 if self.landed else .5 + .5 * min(1, th), pitch=.8 + .35 * min(1.5, th), fade=4)
        self.boost_snd.set(.9 if self.boosting else 0, fade=5)

    def _local_to_world(self, p):
        w = application.base.render.getRelativePoint(self.model, PVec3(*p))
        return Vec3(w[0], w[1], w[2])

    def _local_dir(self, d):
        w = application.base.render.getRelativeVector(self.model, PVec3(*d))
        return Vec3(w[0], w[1], w[2])

    def _spawn_particle(self, pos, vel, life, size0, size1, col):
        if len(self.particles) > int(90 * self.q["particles"]) + 10:
            old = self.particles.pop(0)
            old["np"].removeNode()
        if not hasattr(self, "_quad_tpl"):
            mb = MeshBuilder()
            s = .5
            mb.poly([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], (0, 0, -1), (1, 1, 1, 1),
                    [(0, 0), (1, 0), (1, 1), (0, 1)])
            self._quad_tpl = NodePath(mb.make_geom_node("fxquad", tangents=False))
            self._quad_tpl.setTexture(textures.get('glow')._texture)
        n = self.fx_root.attachNewNode("p")
        self._quad_tpl.instanceTo(n)
        n.setBillboardPointEye()
        n.setPos(pos.x, pos.y, pos.z)
        self.particles.append({"np": n, "p": Vec3(pos), "v": Vec3(vel), "age": 0.0, "life": life,
                               "s0": size0, "s1": size1, "c": col})

    def _emit_trails(self, dt, th, boost):
        """Traînées de particules derrière les tuyères."""
        rate = (th * 26 + boost * 30) * self.q["particles"]
        self._trail_acc += rate * dt
        back = self._local_dir((0, 0, -1))
        while self._trail_acc >= 1:
            self._trail_acc -= 1
            for (x, y, z) in self.nozzles:
                p = self._local_to_world((x + random.uniform(-.15, .15), y + random.uniform(-.15, .15),
                                          z - .6 - random.uniform(0, .5)))
                v = self.vel * .6 + back * random.uniform(3, 6)
                col = (.45, .65, 1.0) if boost else (.35, .5, .9)
                self._spawn_particle(p, v, random.uniform(.35, .7), .5 + th * .3, 1.6, col)

    def _emit_rcs(self, dt):
        """Bouffées des propulseurs de manœuvre quand on tourne ou qu'on strafe."""
        fire = []
        if self.in_strafe > .3:
            fire += ["fl", "rl"]
        elif self.in_strafe < -.3:
            fire += ["fr", "rr"]
        if self.in_vert > .3:
            fire += ["fd", "rd"]
        elif self.in_vert < -.3:
            fire += ["fu", "ru"]
        if self.rate_y > 12:
            fire += ["fl", "rr"]
        elif self.rate_y < -12:
            fire += ["fr", "rl"]
        if self.rate_p > 12:
            fire += ["fu", "rd"]
        elif self.rate_p < -12:
            fire += ["fd", "ru"]
        for key in set(fire):
            cd = self._rcs_cd.get(key, 0) - dt
            if cd <= 0:
                cd = .07
                pos, d = self.rcs[key]
                wp = self._local_to_world(pos)
                wd = self._local_dir(d)
                for _ in range(2):
                    v = self.vel + wd * random.uniform(4, 7) + Vec3(random.uniform(-.5, .5), random.uniform(-.5, .5),
                                                                   random.uniform(-.5, .5))
                    self._spawn_particle(wp, v, random.uniform(.18, .3), .25, 1.1, (.9, .92, 1.0))
            self._rcs_cd[key] = cd

    def _update_particles(self, dt):
        for pt in list(self.particles):
            pt["age"] += dt
            k = pt["age"] / pt["life"]
            if k >= 1:
                pt["np"].removeNode()
                self.particles.remove(pt)
                continue
            pt["p"] += pt["v"] * dt
            pt["v"] *= max(0.0, 1 - dt * 1.5)
            n = pt["np"]
            n.setPos(pt["p"].x, pt["p"].y, pt["p"].z)
            n.setScale(pt["s0"] + (pt["s1"] - pt["s0"]) * k)
            a = (1 - k) ** 1.5
            c = pt["c"]
            n.setColorScale(c[0] * a, c[1] * a, c[2] * a, 1)

    def silence_aids(self):
        """Cache l'aide à l'approche et l'alerte d'obstacle (atterrissage, FPS)."""
        for n in getattr(self, "guide", []):
            n.hide()
        self.approach = None
        self.obstacle_warn = 0.0

    def silence(self):
        self.silence_aids()
        self.engine_snd.set(0, fade=2)
        self.boost_snd.set(0, fade=5)
        for pt in self.particles:
            pt["np"].removeNode()
        self.particles = []

    def destroy(self):
        r = application.base.render
        r.clearLight(self.spot_np)
        r.clearLight(self.eng_np)
        self.game.audio.stop_loop("ship_engine")
        self.game.audio.stop_loop("ship_boost")
        self.fx_root.removeNode()
        for n in getattr(self, "guide", []):
            n.removeNode()
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
