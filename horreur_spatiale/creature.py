# -*- coding: utf-8 -*-
"""
creature.py — La grande créature (« l'Ombre ») et la directrice d'IA.

Principe : on ne la voit JAMAIS longtemps ni en entier. On l'entend bien plus
souvent qu'on ne la voit. La peur vient de ce qu'on devine.

  * PRÉSENCE (invisible) : la plupart du temps, la créature n'est qu'une
    position qui rôde dans les conduits et les pièces voisines. On l'entend :
    pas lourds et irréguliers « au-dessus », grattements de métal, respiration
    lente et humide, petits claquements, chuchotements quand l'infection est
    avancée. Quand elle est tout près sans qu'on la voie : silence soudain,
    puis un seul bruit, très proche.
  * APPARITIONS (mises en scène par la directrice d'IA) : silhouette au loin,
    « elle est derrière toi », passage furtif, à travers un hublot, yeux dans
    un conduit, au plafond, au fond de l'image pendant une lecture... jamais
    deux fois de suite la même, toujours à distance, dans l'ombre.
  * RÈGLE D'OR : budget de visibilité (CREATURE_MAX_VISIBLE). Visible =
    dans le champ de la caméra + ligne de vue dégagée. Au-delà du budget, ou
    si l'on détourne les yeux, ou si l'on avance vers elle : elle disparaît
    (recule dans l'ombre, entre dans un conduit, tourne au coin, ou s'évanouit).
  * LA LUMIÈRE LA FAIT FUIR : faisceau de la lampe, flash d'un tir de pistolet,
    néons alimentés -> sursaut, cri bref, fuite très rapide vers l'obscurité ou
    un conduit. La vision nocturne ne la fait PAS fuir : elle te fixe,
    immobile... puis se cache quand même.
  * ATTAQUE rare et courte (< 1 s) : elle surgit du noir, frappe une fois
    (faibles dégâts, effets forts) et disparaît. Elle ne tue qu'un joueur déjà
    très affaibli. L'éclairer ou lui tirer dessus pendant qu'elle approche
    annule l'attaque.

États (attribut state) :
  ERRANCE    présence invisible qui rôde        ENQUETE    présence attirée par un bruit
  CACHEE     silencieuse, au fond des conduits  APPARITION mise en scène visible
  FUITE      la lumière l'a touchée             DISPARITION elle s'évanouit dans le noir
  ATTAQUE    elle surgit et frappe
"""
import math
import random
from collections import deque

from panda3d.core import Point2, Point3, TransparencyAttrib
from ursina import Entity, color, destroy, camera, scene, application

import numpy as np

import config as C
import textures
from geometry import MeshBuilder
from generator import VENT, CORR, ROOM, ekey, edge_geometry
from lighting import mark_emissive, additive

ROAM, INVESTIGATE, HIDDEN = "ERRANCE", "ENQUETE", "CACHEE"
STAGED, FLEE, VANISH, ATTACK = "APPARITION", "FUITE", "DISPARITION", "ATTAQUE"
WANDER, CHASE = ROAM, "TRAQUE"          # anciens noms (compatibilité)
VISIBLE_STATES = (STAGED, FLEE, VANISH, ATTACK)

KINDS = ("silhouette", "behind", "pass", "window", "vent", "ceiling", "background", "impossible")
KIND_LABELS = {
    "silhouette": "silhouette lointaine", "behind": "derrière toi", "pass": "passage furtif",
    "window": "derrière un hublot", "vent": "yeux dans un conduit", "ceiling": "au plafond",
    "background": "au fond de l'image", "impossible": "endroit impossible", "attack": "attaque",
}
# chuchotements (mêmes mots que audio.WHISPER_SPECS) : repris des documents
WHISPERS = ("Sinus...", "ça passe par l'air...", "il n'y a rien...", "tu l'as respiré...")

HEIGHT = 2.5          # la silhouette fait environ 2,5 m
EYE_Y = 2.33          # hauteur des yeux (debout)


def _creature_skin(rng):
    """Ancienne peau sombre et humide (encore utilisée par le screamer)."""
    s = 256
    n = textures.fractal_noise(s, s, rng, 6, base=4)
    folds = textures.fractal_noise(s, s, rng, 5, base=8)
    veins = np.clip(1 - np.abs(textures.fractal_noise(s, s, rng, 5, base=5) - .5) * 25, 0, 1)
    flesh = np.clip((textures.fractal_noise(s, s, rng, 4, base=3) - .62) * 5, 0, 1)
    alb = np.dstack([.07 + .04 * n, .06 + .03 * n, .07 + .035 * n])
    alb = alb * (1 - flesh[..., None]) + flesh[..., None] * np.array([.32, .22, .22]) * (.7 + .3 * n[..., None])
    alb = alb * (1 - veins[..., None] * .5)
    h = .5 + (folds - .5) * .7 + veins * .25
    rough = np.clip(.12 + .15 * n + flesh * .1, .04, 1)
    return np.clip(alb, 0, 1), h, rough, (1.5, 60, 2.6)


def _void_skin(rng):
    """Matière presque noire qui « boit » la lumière : albédo infime, mate, à peine de relief."""
    s = 128
    n = textures.fractal_noise(s, s, rng, 5, base=4)
    alb = np.dstack([.016 + .01 * n, .015 + .009 * n, .019 + .011 * n])
    h = .5 + (n - .5) * .3
    rough = np.full((s, s), .97, np.float32)
    return np.clip(alb, 0, 1), h, rough, (.05, 4, .8)


def _ang(a):
    return (a + 180) % 360 - 180


def _angle_between(fx, fz, dx, dz):
    """Angle (degrés) entre la direction de vue (fx, fz) et la direction (dx, dz)."""
    d = math.hypot(dx, dz)
    if d < 1e-5:
        return 0.0
    c = max(-1.0, min(1.0, (fx * dx + fz * dz) / d))
    return math.degrees(math.acos(c))


# ----------------------------------------------------------------------------
# poses : angles (rx, ry, rz) des articulations ; on « saute » d'une pose à
# l'autre sans interpolation (mouvements saccadés, pas de marche normale)
# ----------------------------------------------------------------------------
POSES = {
    # debout, parfaitement figée, tête penchée, bras trop longs qui pendent
    "stand": dict(hips=1.30, torso=(10, 0, 0), neck=(16, 0, 0), head=(4, 0, 22),
                  shL=(6, 0, 7), elL=(-14, 0, 0), shR=(2, 0, -5), elR=(-8, 0, 0),
                  hipL=(-26, 0, 2), knL=(52, 0, 0), anL=(-28, 0, 0),
                  hipR=(-22, 0, -2), knR=(46, 0, 0), anR=(-26, 0, 0)),
    # elle te fixe (vision nocturne) : penchée en avant, tête relevée vers toi
    "stare": dict(hips=1.24, torso=(26, 0, 0), neck=(-6, 0, 0), head=(-16, 0, 12),
                  shL=(14, 0, 9), elL=(-20, 0, 0), shR=(14, 0, -9), elR=(-24, 0, 0),
                  hipL=(-20, 0, 4), knL=(42, 0, 0), anL=(-24, 0, 0),
                  hipR=(-18, 0, -4), knR=(40, 0, 0), anR=(-24, 0, 0)),
    # course saccadée (deux images qui alternent, comme une image qui saute)
    "run_a": dict(hips=1.16, torso=(42, 0, 6), neck=(-18, 0, 0), head=(-8, 0, -10),
                  shL=(-35, 0, 10), elL=(-50, 0, 0), shR=(40, 0, -10), elR=(-15, 0, 0),
                  hipL=(-55, 0, 0), knL=(70, 0, 0), anL=(-30, 0, 0),
                  hipR=(25, 0, 0), knR=(20, 0, 0), anR=(-10, 0, 0)),
    "run_b": dict(hips=1.12, torso=(46, 0, -6), neck=(-20, 0, 0), head=(-6, 0, 14),
                  shL=(40, 0, 10), elL=(-15, 0, 0), shR=(-35, 0, -10), elR=(-50, 0, 0),
                  hipL=(25, 0, 0), knL=(20, 0, 0), anL=(-10, 0, 0),
                  hipR=(-55, 0, 0), knR=(70, 0, 0), anR=(-30, 0, 0)),
    # sursaut quand la lumière la touche : se recroqueville, bras devant la tête
    "flinch": dict(hips=1.18, torso=(-8, 25, 0), neck=(30, 0, 0), head=(20, -50, -30),
                   shL=(-120, 0, 30), elL=(-90, 0, 0), shR=(-110, 0, -25), elR=(-95, 0, 0),
                   hipL=(-30, 0, 6), knL=(55, 0, 0), anL=(-25, 0, 0),
                   hipR=(-10, 0, -6), knR=(30, 0, 0), anR=(-20, 0, 0)),
    # accroupie (conduits) : corps à l'horizontale, membres repliés
    "crouch": dict(hips=.62, torso=(78, 0, 0), neck=(-55, 0, 0), head=(-25, 0, 18),
                   shL=(-70, 0, 12), elL=(-30, 0, 0), shR=(-70, 0, -12), elR=(-30, 0, 0),
                   hipL=(-80, 0, 6), knL=(120, 0, 0), anL=(-40, 0, 0),
                   hipR=(-80, 0, -6), knR=(120, 0, 0), anR=(-40, 0, 0)),
    # au plafond (le modèle est retourné) : membres écartés, agrippés
    "ceiling": dict(hips=.55, torso=(85, 0, 0), neck=(-80, 0, 0), head=(-10, 0, 35),
                    shL=(-150, 0, 35), elL=(-40, 0, 0), shR=(-150, 0, -35), elR=(-40, 0, 0),
                    hipL=(-95, 0, 30), knL=(110, 0, 0), anL=(-30, 0, 0),
                    hipR=(-95, 0, -30), knR=(110, 0, 0), anR=(-30, 0, 0)),
    # frappe : un bras levé, le corps projeté en avant
    "strike": dict(hips=1.10, torso=(38, -20, 0), neck=(-20, 0, 0), head=(-10, 0, -8),
                   shL=(-160, 0, 20), elL=(-30, 0, 0), shR=(-60, 0, -10), elR=(-50, 0, 0),
                   hipL=(-50, 0, 0), knL=(60, 0, 0), anL=(-30, 0, 0),
                   hipR=(10, 0, 0), knR=(25, 0, 0), anR=(-15, 0, 0)),
}
JOINTS = ("torso", "neck", "head", "shL", "elL", "shR", "elR", "hipL", "knL", "anL", "hipR", "knR", "anR")


class Creature:
    aware = True

    def __init__(self, game, level, cell):
        self.game = game
        self.level = level
        self.x, self.z = level.cell_center(*cell)
        self.yaw = 0.0
        self.state = ROAM
        self.kind = None             # type d'apparition en cours
        self.path = []
        self.goal = None
        self.pause = 2.0
        self.clock = 0.0
        self.events = []             # (instant, fonction) : petite file d'actions différées
        self.visible = False         # le corps est-il affiché ?
        self.can_see = False         # le JOUEUR la voit-il en ce moment ? (debug)
        self.lit_by = None           # "lampe" / "tir" / "néon" si la lumière la touche
        self.suspended = False       # révélation : l'hallucination est « tombée »
        self.hidden_timer = 0.0
        self.alert_t = 0.0           # attirée par un bruit : rôde plus vite, plus près
        self.stage_t = 0.0
        self.seen_time = 0.0         # temps passé à l'écran pendant cette apparition
        self.seen_ever = False
        self.unseen_t = 0.0
        self.react_t = -1.0          # compte à rebours de la réaction à la lumière
        self.stare = False           # vision nocturne : elle te fixe
        self.start_dist = 0.0
        self.max_time = C.CREATURE_APPARITION_MAX
        self.need_light = False      # au plafond : invisible tant qu'on ne l'éclaire pas
        self.los_pt = None           # point visé pour la ligne de vue (hublot, grille)
        self.y_off = 0.0
        self.upside_down = False
        self.eyes_only = False
        self.echo = False            # après le disque dur : réapparaît aussitôt ailleurs
        self.glimpse_t = -1.0
        self.fade = 1.0
        self.fade_speed = 4.0
        self.flee_t = 0.0
        self.attack_phase = None
        self.attack_t = 0.0
        self.pose = "stand"
        self.pose_t = 0.0
        self.head_t = 0.0
        self.head_off = (0.0, 0.0)
        self.skip_t = 0.0
        self.step_t = 1.0
        self.step_burst = 0
        self.scrape_t = random.uniform(8, 16)
        self.breath_t = random.uniform(10, 20)
        self.click_t = random.uniform(6, 14)
        self.next_silence = C.CREATURE_SILENCE_GAP * .6
        self.next_whisper = random.uniform(*C.CREATURE_WHISPER_GAP)
        self.dread = 0.0
        self.flicker_t = 0.0
        self.rumble_t = 0.0
        self.last_search_pos = None  # dernier cadavre / casier fouillé (endroits « impossibles »)
        self.hits = []
        self.cells = [(c, *level.cell_center(*c)) for c in level.links
                      if level.kind[c[0]][c[1]] in (ROOM, CORR)]
        self.vents = level.vent_cells()
        self._build_model()
        self.growl = game.audio.loop("creature_growl", "creature_growl", .7)
        self.hum = game.audio.loop("creature_hum", "sinus_chant", 1.0, ambient=True)

    # ==================================================================
    # MODÈLE : silhouette très grande, maigre, membres trop longs,
    # articulations à l'envers, tête allongée ; seuls les yeux brillent
    # ==================================================================
    def _build_model(self):
        mat = textures.material("creature_void", custom=_void_skin)
        K = (1, 1, 1, 1)

        def mesh(parent, mb, name):
            np_ = parent.attachNewNode(mb.make_geom_node(name))
            textures.apply_material(np_, mat)
            return np_

        def limb(parent, length, w0, w1, name, claws=0):
            mb = MeshBuilder(uv_scale=.4)
            # segment effilé : trois boîtes biseautées de plus en plus fines
            for k in range(3):
                f0 = k / 3
                w = w0 + (w1 - w0) * (f0 + 1 / 6)
                mb.bevel_box((0, -length * (f0 + 1 / 6), 0), (w, length / 3 + .02, w * .9), w * .35, K)
            mb.bevel_box((0, 0, 0), (w0 * 1.15, w0 * 1.15, w0 * 1.1), w0 * .4, K)        # articulation saillante
            for c in range(claws):                                                       # doigts trop longs
                a = (c - (claws - 1) / 2) * .035
                mb.cone((a, -length, 0), .012, .26, K, K, 5, (a * 2, -1, .1))
            return mesh(parent, mb, name)

        self.root = Entity(name='creature', enabled=False)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        J = {}
        J["hips"] = Entity(parent=self.root, y=POSES["stand"]["hips"])
        pb = MeshBuilder(uv_scale=.4)
        pb.bevel_box((0, 0, 0), (.3, .16, .17), .06, K)
        mesh(J["hips"], pb, "creature_pelvis")
        # torse étroit, cage thoracique creuse, épaules hautes
        J["torso"] = Entity(parent=J["hips"])
        tb = MeshBuilder(uv_scale=.5)
        tb.bevel_box((0, .14, 0), (.17, .26, .13), .06, K)                 # taille de guêpe
        tb.bevel_box((0, .42, .01), (.28, .34, .17), .08, K)               # thorax
        tb.bevel_box((0, .64, -.01), (.46, .1, .14), .05, K)               # épaules trop hautes
        for k in range(6):                                                  # vertèbres saillantes
            tb.bevel_box((0, .1 + k * .1, -.085), (.045, .05, .05), .015, K)
        mesh(J["torso"], tb, "creature_torso")
        J["neck"] = Entity(parent=J["torso"], y=.7)
        nb = MeshBuilder(uv_scale=.4)
        nb.bevel_box((0, .1, 0), (.07, .22, .07), .03, K)
        mesh(J["neck"], nb, "creature_neck")
        # tête allongée vers l'arrière, légèrement penchée
        J["head"] = Entity(parent=J["neck"], y=.2)
        hb = MeshBuilder(uv_scale=.4)
        hb.loft([(-.36, 0, .05, .05, .06, .02), (-.2, 0, .06, .12, .14, .05), (-.02, 0, .04, .17, .2, .07),
                 (.1, 0, .0, .14, .17, .06), (.16, 0, -.03, .08, .1, .03)], K)
        mesh(J["head"], hb, "creature_head")
        # les yeux : seuls éléments nets, blancs, visibles de loin dans le noir
        self.eye_nodes = []
        self.eye_glows = []
        for sd in (-1, 1):
            e = Entity(parent=J["head"], model='sphere', color=color.rgb(1, 1, 1), scale=(.03, .022, .02),
                       position=(sd * .045, .05, .135))
            mark_emissive(e)
            e.setFogOff()
            g_ = Entity(parent=J["head"], model='quad', texture=textures.get('glow'), billboard=True,
                        color=color.rgba(1, 1, 1, .8), scale=.26, position=(sd * .045, .05, .15))
            additive(g_, 7)
            g_.setFogOff()
            g_.setLightOff(1)
            self.eye_nodes.append(e)
            self.eye_glows.append(g_)
        # bras démesurés (les mains descendent sous les genoux)
        for sd, n in ((-1, "L"), (1, "R")):
            J["sh" + n] = Entity(parent=J["torso"], position=(sd * .23, .64, 0))
            limb(J["sh" + n], .78, .07, .05, "creature_upper_arm")
            J["el" + n] = Entity(parent=J["sh" + n], y=-.78)
            limb(J["el" + n], .86, .055, .035, "creature_forearm", claws=4)
        # jambes : genou qui plie dans le mauvais sens (vers l'avant), pieds en griffes
        for sd, n in ((-1, "L"), (1, "R")):
            J["hip" + n] = Entity(parent=J["hips"], position=(sd * .11, -.02, 0))
            limb(J["hip" + n], .62, .085, .06, "creature_thigh")
            J["kn" + n] = Entity(parent=J["hip" + n], y=-.62)
            limb(J["kn" + n], .58, .06, .04, "creature_shin")
            J["an" + n] = Entity(parent=J["kn" + n], y=-.58)
            fb = MeshBuilder(uv_scale=.3)
            fb.bevel_box((0, -.05, .06), (.06, .05, .2), .02, K)
            for c in (-1, 0, 1):
                fb.cone((c * .025, -.06, .16), .01, .12, K, K, 5, (c * .2, -.3, 1))
            mesh(J["an" + n], fb, "creature_foot")
        self.J = J
        # contours flous et mouvants : voiles sombres qui tremblent autour du corps
        self.shroud = []
        for parent, pos, sc in ((J["torso"], (0, .4, 0), .75), (J["torso"], (0, .7, 0), .55),
                                (J["head"], (0, .03, -.12), .45), (J["hips"], (0, 0, 0), .5),
                                (J["shL"], (0, -.45, 0), .32), (J["shR"], (0, -.45, 0), .32),
                                (J["elL"], (0, -.5, 0), .28), (J["elR"], (0, -.5, 0), .28),
                                (J["hipL"], (0, -.35, 0), .32), (J["hipR"], (0, -.35, 0), .32),
                                (J["knL"], (0, -.3, 0), .26), (J["knR"], (0, -.3, 0), .26)):
            q = Entity(parent=parent, model='quad', texture=textures.get('glow'), billboard=True,
                       color=color.rgba(0, 0, 0, .5), scale=sc, position=pos)
            q.setLightOff(1)
            q.setDepthWrite(False)
            q.setBin("transparent", 6)
            self.shroud.append((q, pos, sc))
        # yeux seuls (derrière une grille d'aération)
        self.vent_eyes = Entity(name='creature_vent_eyes', enabled=False)
        self.vent_eye_parts = []
        for sd in (-1, 1):
            e = Entity(parent=self.vent_eyes, model='sphere', color=color.rgb(1, 1, 1), scale=(.03, .02, .02),
                       position=(sd * .05, 0, 0))
            mark_emissive(e)
            e.setFogOff()
            g_ = Entity(parent=self.vent_eyes, model='quad', texture=textures.get('glow'), billboard=True,
                        color=color.rgba(1, 1, 1, .75), scale=.2, position=(sd * .05, 0, .02))
            additive(g_, 7)
            g_.setFogOff()
            g_.setLightOff(1)
            self.vent_eye_parts.append((e, g_))
        self._apply_pose("stand")

    def _apply_pose(self, name, jitter=0.0):
        P = POSES[name]
        self.pose = name
        self.J["hips"].y = P["hips"]
        for j in JOINTS:
            rx, ry, rz = P.get(j, (0, 0, 0))
            if jitter:
                rx += random.uniform(-jitter, jitter)
                rz += random.uniform(-jitter, jitter) * .5
            e = self.J[j]
            e.rotation_x, e.rotation_y, e.rotation_z = rx, ry, rz
        hx, hz = self.head_off
        h = self.J["head"]
        h.rotation_y += hx
        h.rotation_z += hz

    def _set_eyes(self, a):
        for e in self.eye_nodes:
            e.enabled = a > .05
        for g_ in self.eye_glows:
            g_.color = color.rgba(1, 1, 1, .8 * a)

    # ==================================================================
    # INTERFACE UTILISÉE PAR LE RESTE DU JEU
    # ==================================================================
    def hit_spheres(self):
        if not self.visible or self.state == VANISH or self.eyes_only:
            return []
        if self.upside_down:
            top = self.y_off
            return [((self.x, top - .9, self.z), .55), ((self.x, top - .4, self.z), .4)]
        y0 = self.y_off
        fx, fz = math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw))
        return [((self.x, 1.65 + y0, self.z), .42), ((self.x + fx * .1, 2.3 + y0, self.z + fz * .1), .25),
                ((self.x, .9 + y0, self.z), .35)]

    def center3(self):
        return (self.x, 1.6 + self.y_off, self.z)

    def on_hit(self, dmg, pos, gun, silent=False):
        """On ne la tue pas : touchée (balle ou lame), elle hurle et s'enfuit, l'attaque est annulée."""
        if self.state in (STAGED, ATTACK):
            self._react_to_light("tir", immediate=True)

    def sees_player_now(self):
        return False

    def hear(self, pos, radius, kind):
        """Bruit : la présence vient voir (invisible) ; un coup de feu avance la prochaine apparition."""
        if self.state == HIDDEN:
            if kind == "shot" and random.random() < .5:
                self.hidden_timer = min(self.hidden_timer, 4.0)
            return
        d = math.hypot(pos[0] - self.x, pos[2] - self.z)
        if d > radius:
            return
        if kind == "knife" and (d > C.KNIFE_ALERT_DIST or random.random() > C.KNIFE_ALERT_CHANCE):
            return
        if kind == "shot":
            self.alert_t = 25.0
            d_ = self.game.director
            if d_ is not None:
                d_.on_noise()
        if self.state in (ROAM, INVESTIGATE):
            self.state = INVESTIGATE
            self._go_to(pos[0], pos[2])

    def investigate(self, x, z):
        if self.state in (ROAM, INVESTIGATE):
            self.state = INVESTIGATE
            self._go_to(x, z)

    def appear_at(self, x, z):
        """Révélation : elle se tient là, entre le joueur et le hangar (silhouette forcée)."""
        self._hide_model(quiet=True)
        self.x, self.z = x, z
        self._begin("silhouette", forced=True)

    def start_retreat(self):
        """Retraite silencieuse au fond des conduits."""
        self._hide_model(quiet=True)
        self.state = HIDDEN
        self.hidden_timer = random.uniform(*C.CREATURE_HIDE_TIME)

    def staging(self):
        return self.state in VISIBLE_STATES

    def presence_distance(self):
        p = self.game.player
        if p is None or self.state == HIDDEN or self.suspended:
            return 99.0
        return math.hypot(self.x - p.x, self.z - p.z)

    def distant_call(self):
        """Événement d'ambiance : un bruit de la présence, quelque part."""
        if self.state == HIDDEN or self.suspended:
            return
        name = random.choice(("creature_scrape0", "creature_scrape1", "creature_click", "creature_heavy0"))
        self._presence_sound(name, .8)

    # ==================================================================
    # OUTILS : vue du joueur, écran, lumière, grille
    # ==================================================================
    def _view(self):
        cp = camera.world_position
        fw = camera.forward
        fx, fz = fw.x, fw.z
        n = math.hypot(fx, fz) or 1.0
        return (cp.x, cp.y, cp.z), (fx / n, fz / n), (fw.x, fw.y, fw.z)

    def _on_screen(self, pt, margin=.96):
        base = application.base
        try:
            p3 = base.cam.getRelativePoint(scene, Point3(pt[0], pt[1], pt[2]))
        except Exception:
            return False
        p2 = Point2()
        if not base.camLens.project(p3, p2):
            return False
        return abs(p2.x) < margin and abs(p2.y) < margin

    def _points(self):
        """Points du corps testés pour la visibilité (tête, poitrine, genoux / yeux seuls)."""
        if self.eyes_only:
            ep = self.vent_eyes.world_position
            return [(ep.x, ep.y, ep.z)]
        y0 = self.y_off
        if self.upside_down:
            return [(self.x, y0 - .5, self.z), (self.x, y0 - 1.1, self.z)]
        fx, fz = math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw))
        if self.pose == "crouch":
            return [(self.x + fx * .5, .9 + y0, self.z + fz * .5), (self.x, .7 + y0, self.z)]
        return [(self.x + fx * .12, EYE_Y + y0, self.z + fz * .12), (self.x, 1.6 + y0, self.z),
                (self.x, .9 + y0, self.z)]

    def _seen(self, pts, eye):
        L = self.level
        for pt in pts:
            if not self._on_screen(pt):
                continue
            tgt = self.los_pt or pt
            if L.line_of_sight(eye, tgt):
                return True
        return False

    def _light_on_me(self, pts, eye, fwd3):
        """La lumière la touche-t-elle ? Renvoie 'lampe', 'tir', 'néon' ou None."""
        g = self.game
        lt = g.lights
        L = self.level
        o = lt.flashlight_origin()
        for pt in pts[:2]:
            if lt.flashlight_hits(pt, C.CREATURE_LIGHT_RANGE, eye, fwd3):
                if L.line_of_sight(o, self.los_pt or pt):
                    return "lampe"
        m = lt.muzzle_recent()
        if m is not None and len(pts) > 1:
            b = pts[1]
            if math.dist(m, b) < C.CREATURE_MUZZLE_SCARE_DIST and L.line_of_sight(m, self.los_pt or b):
                return "tir"
        if not (self.eyes_only or self.upside_down or self.los_pt) and lt.lit_at(self.x, self.z):
            return "néon"
        return None

    def _bold(self):
        """Lampe éteinte, faible ou qui clignote : elle ose davantage."""
        lt = self.game.lights
        fl = lt.flashlight
        return (not lt.flashlight_on) or lt.battery < C.FLASHLIGHT_LOW or fl.flickering or fl.effective < .3

    def _dark_cell(self, c):
        x, z = self.level.cell_center(*c)
        return not self.game.lights.lit_at(x, z)

    def _go_to(self, x, z, agent="creature"):
        L = self.level
        start = L.cell_at(self.x, self.z)
        if start not in L.links:
            c = L.nearest_linked_cell(self.x, self.z, 4)
            if c is None:
                return False
            self.x, self.z = L.cell_center(*c)
            start = c
        goal = L.cell_at(x, z)
        if goal not in L.links:
            return False
        path = L.find_path(start, goal, agent, 3000)
        if not path:
            return False
        self.path = [L.cell_center(*c) for c in path[1:]]
        self.goal = (x, z)
        return True

    def _move(self, dt, speed, face=True):
        """Avance le long du chemin (cases praticables uniquement : jamais dans un mur)."""
        moved = 0.0
        L = self.level
        while self.path and speed * dt - moved > 1e-4:
            tx, tz = self.path[0]
            dx, dz = tx - self.x, tz - self.z
            d = math.hypot(dx, dz)
            if d < .05:
                self.path.pop(0)
                continue
            step = min(d, speed * dt - moved)
            a = L.cell_at(self.x, self.z)
            nx, nz = self.x + dx / d * step, self.z + dz / d * step
            b = L.cell_at(nx, nz)
            if a != b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
                gr = L.grilles.get(ekey(a[0], a[1], b[0], b[1]))
                if gr is not None and not gr.opened and not gr.locked:
                    gr.set_open(True)
                    self.game.audio.play_at("vent_bang", (gr.pos[0], .5, gr.pos[1]), .9, random.uniform(.8, 1))
            self.x, self.z = nx, nz
            moved += step
            if face:
                self.yaw = math.degrees(math.atan2(dx, dz))
            if step >= d - 1e-6:
                self.path.pop(0)
        return moved

    def _face_player(self):
        p = self.game.player
        if p is not None:
            self.yaw = math.degrees(math.atan2(p.x - self.x, p.z - self.z))

    def _in_vent(self):
        L = self.level
        i, j = L.cell_at(self.x, self.z)
        return L.inside(i, j) and L.kind[i][j] == VENT

    # ==================================================================
    # MISE EN SCÈNE DES APPARITIONS
    # ==================================================================
    def stage(self, kind):
        """Demande de la directrice : tente une apparition de ce type. Renvoie True si elle a lieu."""
        if self.suspended or self.state in VISIBLE_STATES:
            return False
        fn = getattr(self, "_place_" + kind, None)
        if fn is None or not fn():
            return False
        self._begin(kind)
        return True

    def _begin(self, kind, forced=False):
        g = self.game
        self.kind = kind
        self.state = STAGED
        self.stage_t = 0.0
        self.seen_time = 0.0
        self.seen_ever = False
        self.unseen_t = 0.0
        self.react_t = -1.0
        self.stare = False
        self.glimpse_t = -1.0
        self.fade = 1.0
        self.lit_by = None
        self.max_time = C.CREATURE_APPARITION_MAX
        if kind == "behind":
            self.max_time = C.CREATURE_BEHIND_WINDOW
        p = g.player
        self.start_dist = math.hypot(p.x - self.x, p.z - self.z) if p is not None else 10.0
        if kind not in ("pass", "background"):
            self._face_player()
        self.head_off = (0.0, 0.0)
        if self.eyes_only:
            self.root.enabled = False
            self.visible = False
            self.vent_eyes.enabled = True
            for e, g_ in self.vent_eye_parts:
                e.enabled = True
                g_.color = color.rgba(1, 1, 1, .75)
        else:
            self._show_model()
        if kind == "behind":
            # une respiration, ou un craquement, juste derrière
            self.events.append((self.clock + .35, lambda: g.audio.play_at(
                "creature_breath", (self.x, 2.1, self.z), .85, random.uniform(.9, 1.05), 12)))
        elif kind == "vent":
            self.events.append((self.clock + .2, lambda: g.audio.play_at(
                "creature_click", (self.x, .6, self.z), .5, random.uniform(.8, 1), 14)))

    def _show_model(self):
        self.visible = True
        self.root.enabled = True
        self.fade = 1.0
        self.root.setColorScale(1, 1, 1, 1)
        self._set_eyes(1.0)
        self._place_root()

    def _hide_model(self, quiet=False, retreat=True):
        """Fin d'une apparition : le corps disparaît, la présence continue (ou se terre)."""
        was = self.state in VISIBLE_STATES
        self.visible = False
        self.root.enabled = False
        self.vent_eyes.enabled = False
        self.can_see = False
        kind = self.kind
        self.kind = None
        self.eyes_only = False
        self.need_light = False
        self.upside_down = False
        self.los_pt = None
        self.y_off = 0.0
        self.attack_phase = None
        self.path = []
        if was:
            self.state = ROAM
            self.pause = random.uniform(3, 8)
            if retreat:
                self._retreat_from_player()
            d_ = self.game.director
            if d_ is not None:
                d_.on_end(kind)
            # après le disque dur : « à deux endroits presque en même temps »
            if self.echo and kind in ("silhouette", "impossible", "pass"):
                self.echo = False
                self.events.append((self.clock + .35, self._echo))

    def _echo(self):
        if self.state in VISIBLE_STATES or self.suspended:
            return
        if self._place_silhouette(echo=True):
            self._begin("silhouette")
            self.max_time = 1.2

    def _retreat_from_player(self):
        p = self.game.player
        if p is None:
            return
        L = self.level
        far = [c for c in (self.vents or []) if 12 < math.hypot(L.cell_center(*c)[0] - p.x, L.cell_center(*c)[1] - p.z) < 30]
        if far:
            c = random.choice(far)
            self._go_to(*L.cell_center(*c))
            self.alert_t = max(self.alert_t, 6.0)

    def _place_root(self):
        if self.upside_down:
            self.root.position = (self.x, self.y_off, self.z)
            self.root.rotation = (0, self.yaw, 180)
        else:
            self.root.position = (self.x, self.y_off, self.z)
            self.root.rotation = (0, self.yaw, 0)

    # --- choix des emplacements ----------------------------------------------
    def _cands(self, dmin, dmax, amin, amax, kinds=(ROOM, CORR)):
        """Cases à distance [dmin, dmax] et dans un secteur angulaire [amin, amax] autour de la vue."""
        p = self.game.player
        eye, (fx, fz), _ = self._view()
        out = []
        L = self.level
        for c, cx, cz in self.cells:
            dx, dz = cx - p.x, cz - p.z
            d = math.hypot(dx, dz)
            if d < dmin or d > dmax:
                continue
            a = _angle_between(fx, fz, dx, dz)
            if a < amin or a > amax:
                continue
            if L.kind[c[0]][c[1]] not in kinds:
                continue
            out.append((c, cx, cz, d, a))
        random.shuffle(out)
        return out, eye

    def _dist_mult(self):
        return C.CREATURE_BOLD_DIST_MULT if self._bold() else 1.0

    def _place_silhouette(self, echo=False):
        """Au bout d'un long couloir, à la limite du brouillard : une forme immobile."""
        g = self.game
        L = self.level
        k = self._dist_mult()
        d0, d1 = C.CREATURE_FAR_DIST
        d0 = max(C.CREATURE_MIN_DIST, d0 * k)
        lamp = g.lights.flashlight.effective > .25
        cands, eye = self._cands(d0, d1, 0, 38)
        best = None
        for c, cx, cz, d, a in cands[:40]:
            if lamp and a < 26 and d < C.CREATURE_LIGHT_RANGE:
                continue                       # pas en plein faisceau
            if not self._dark_cell(c):
                continue
            if echo and math.hypot(cx - self.x, cz - self.z) < 6:
                continue
            if not (L.line_of_sight(eye, (cx, EYE_Y, cz)) and L.line_of_sight(eye, (cx, 1.4, cz))):
                continue
            score = d * (1.4 if L.kind[c[0]][c[1]] == CORR else 1.0) + random.uniform(0, 6)
            if best is None or score > best[0]:
                best = (score, cx, cz)
        if best is None:
            return False
        self.x, self.z = best[1] + random.uniform(-.4, .4), best[2] + random.uniform(-.4, .4)
        self.pose = "stand"
        return True

    def _place_behind(self):
        """Juste derrière le joueur, hors de son champ de vision, à quelques mètres."""
        L = self.level
        k = self._dist_mult()
        d0, d1 = C.CREATURE_BEHIND_DIST
        cands, eye = self._cands(max(2.8, d0 * k), d1, 130, 180)
        for c, cx, cz, d, a in cands[:60]:
            x, z = cx + random.uniform(-.3, .3), cz + random.uniform(-.3, .3)
            pts = [(x, EYE_Y, z), (x, 1.6, z)]
            if any(self._on_screen(pt, 1.2) for pt in pts):
                continue
            if not L.line_of_sight(eye, pts[0]):
                continue
            if self.game.lights.lit_at(x, z):
                continue
            self.x, self.z = x, z
            self.pose = "stand"
            return True
        return False

    def _place_impossible(self):
        """Après le disque dur : debout à l'endroit même qu'on vient de fouiller."""
        if self.last_search_pos is None:
            return False
        p = self.game.player
        L = self.level
        x, z = self.last_search_pos
        d = math.hypot(x - p.x, z - p.z)
        if d < 6 or d > 22:
            return False
        c = L.nearest_linked_cell(x, z, 2)
        if c is None:
            return False
        cx, cz = L.cell_center(*c)
        eye, (fx, fz), _ = self._view()
        if _angle_between(fx, fz, cx - p.x, cz - p.z) < 100:
            return False                       # il faut qu'on se retourne pour la découvrir
        if not L.line_of_sight(eye, (cx, EYE_Y, cz)):
            return False
        self.x, self.z = cx, cz
        self.pose = "stand"
        return True

    def _perp_path(self, c, fx, fz, extra=1):
        """Chemin perpendiculaire à la vue passant par la case c (traversée d'une porte, d'un croisement)."""
        L = self.level
        ax = (0, 1) if abs(fx) > abs(fz) else (1, 0)
        links = {(n[0], n[1]): n[2] for n in L.links.get(c, [])}

        def side(cell, s):
            out = []
            cur = cell
            for _ in range(1 + extra):
                nxt = (cur[0] + ax[0] * s, cur[1] + ax[1] * s)
                lk = {(n[0], n[1]): n[2] for n in L.links.get(cur, [])}
                if lk.get(nxt) != "open":
                    break
                out.append(nxt)
                cur = nxt
            return out

        if not links:
            return None
        a = side(c, -1)
        b = side(c, 1)
        if not a or not b:
            return None
        if random.random() < .5:
            a, b = b, a
        cells = list(reversed(a)) + [c] + b
        if not all(self._dark_cell(x) for x in cells):
            return None
        return [L.cell_center(*x) for x in cells]

    def _place_pass(self, background=False):
        """Elle traverse une porte ou un croisement, au loin, très vite."""
        L = self.level
        k = self._dist_mult()
        if background:
            cands, eye = self._cands(7 * k + 2, 15, 18, 40)
        else:
            d0, d1 = C.CREATURE_PASS_DIST
            cands, eye = self._cands(max(C.CREATURE_MIN_DIST, d0 * k), d1, 0, 28)
        _, (fx, fz), _ = self._view()
        for c, cx, cz, d, a in cands[:40]:
            if not L.line_of_sight(eye, (cx, 1.6, cz)):
                continue
            path = self._perp_path(c, fx, fz, extra=1)
            if path is None:
                continue
            self.x, self.z = path[0]
            self.path = path[1:]
            self.pose = "run_a"
            return True
        return False

    def _place_background(self):
        """Pendant une lecture ou une fouille : elle passe au fond de l'image, au bord de l'écran."""
        return self._place_pass(background=True)

    def _place_window(self):
        """Derrière un hublot : une silhouette collée à la vitre, à l'extérieur. Impossible."""
        g = self.game
        p = g.player
        L = self.level
        eye, (fx, fz), _ = self._view()
        best = None
        for key, kind in L.windows.items():
            if kind != "porthole":
                continue
            axis, line, s0, s1 = edge_geometry(key)
            mid = (s0 + s1) / 2
            wx, wz = (line, mid) if axis == "x" else (mid, line)
            d = math.hypot(wx - p.x, wz - p.z)
            if d < 3.5 or d > 11:
                continue
            a = _angle_between(fx, fz, wx - p.x, wz - p.z)
            if a > 45:
                continue
            # côté intérieur : la case ouverte de part et d'autre de l'arête
            _, i, j = key
            if axis == "x":
                ins, out = ((i, j), (i + 1, j)) if L.inside(i, j) and L.is_open(i, j) else ((i + 1, j), (i, j))
            else:
                ins, out = ((i, j), (i, j + 1)) if L.inside(i, j) and L.is_open(i, j) else ((i, j + 1), (i, j))
            nx, nz = out[0] - ins[0], out[1] - ins[1]
            inside_pt = (wx - nx * .15, 1.58, wz - nz * .15)
            if not L.line_of_sight(eye, inside_pt):
                continue
            score = random.uniform(0, 1) - d * .05
            if best is None or score > best[0]:
                best = (score, wx + nx * .55, wz + nz * .55, inside_pt)
        if best is None:
            return False
        self.x, self.z = best[1], best[2]
        self.los_pt = best[3]
        self.y_off = -.62                      # la tête au niveau du hublot, le reste caché par le mur
        self.pose = "stand"
        return True

    def _place_vent(self):
        """Deux yeux blancs derrière une grille d'aération."""
        p = self.game.player
        L = self.level
        eye, (fx, fz), _ = self._view()
        d0, d1 = C.CREATURE_VENT_EYES_DIST
        best = None
        for gr in L.grilles.values():
            rx, rz = gr.room_side_point(.12)
            d = math.hypot(rx - p.x, rz - p.z)
            if d < d0 or d > d1:
                continue
            if _angle_between(fx, fz, rx - p.x, rz - p.z) > 70:
                continue
            tgt = (rx, C.VENT_HEIGHT * .5, rz)
            if not L.line_of_sight(eye, tgt):
                continue
            score = random.uniform(0, 1)
            if best is None or score > best[0]:
                best = (score, gr, tgt)
        if best is None:
            return False
        gr = best[1]
        vi, vj = gr.vent_cell
        ri, rj = gr.room_cell
        dx, dz = vi - ri, vj - rj
        ex, ez = gr.pos[0] + dx * .32, gr.pos[1] + dz * .32
        self.x, self.z = ex, ez
        self.eyes_only = True
        self.los_pt = best[2]
        self.vent_eyes.position = (ex, C.VENT_HEIGHT * .52, ez)
        self.vent_eyes.rotation_y = math.degrees(math.atan2(-dx, -dz))
        self._vent_dir = (dx, dz)
        return True

    def _place_ceiling(self):
        """Accrochée au plafond d'une grande salle : on ne la voit que si l'on lève la lampe."""
        g = self.game
        p = g.player
        L = self.level
        room = L.room_at(p.x, p.z)
        if room is None or room.height < 4.0:
            return False
        eye, (fx, fz), _ = self._view()
        cells = [c for c in room.cells() if c in L.links]
        random.shuffle(cells)
        for c in cells[:60]:
            cx, cz = L.cell_center(*c)
            d = math.hypot(cx - p.x, cz - p.z)
            if d < 4.5 or d > 11:
                continue
            if _angle_between(fx, fz, cx - p.x, cz - p.z) < 30:
                continue
            top = L.ceiling(*c) - .05
            if not L.line_of_sight(eye, (cx, top - .6, cz)):
                continue
            self.x, self.z = cx, cz
            self.upside_down = True
            self.y_off = top
            self.need_light = True
            self.pose = "ceiling"
            return True
        return False

    # ==================================================================
    # ATTAQUE
    # ==================================================================
    def start_attack(self):
        """Elle surgit de l'obscurité (hors champ), frappe une fois et disparaît."""
        if self.suspended or self.state in VISIBLE_STATES:
            return False
        g = self.game
        p = g.player
        L = self.level
        cands, eye = self._cands(5.5, 9.5, 75, 180)
        pc = L.cell_at(p.x, p.z)
        for c, cx, cz, d, a in cands[:60]:
            if not self._dark_cell(c):
                continue
            if self._on_screen((cx, EYE_Y, cz), 1.15) or self._on_screen((cx, 1.2, cz), 1.15):
                continue
            path = L.find_path(c, pc, "creature", 300)
            if not path or len(path) > 6:
                continue
            self.x, self.z = cx, cz
            self.path = [L.cell_center(*q) for q in path[1:]]
            self.kind = "attack"
            self.state = ATTACK
            self.attack_phase = "warn"
            self.attack_t = 0.0
            self.stage_t = 0.0
            self.seen_time = 0.0
            self.react_t = -1.0
            self.lit_by = None
            self._face_player()
            self._show_model()
            self._apply_pose("stare")
            # le souffle, tout près, avant qu'elle surgisse
            g.audio.play_at("creature_breath", (cx, 2.0, cz), 1.0, 1.1, 14)
            g.audio.play_at("creature_click", (cx, 2.0, cz), .7, .9, 14)
            return True
        return False

    def _update_attack(self, dt, seen, light):
        g = self.game
        p = g.player
        self.attack_t += dt
        if light == "lampe" or light == "tir":
            self._react_to_light(light, immediate=True)      # l'éclairer annule l'attaque
            return
        if self.attack_phase == "warn":
            if self.attack_t >= .45:
                self.attack_phase = "lunge"
                g.audio.play_at("creature_shriek", (self.x, 2.0, self.z), .8, .7, 16)
            return
        if self.attack_phase == "lunge":
            d = math.hypot(p.x - self.x, p.z - self.z)
            eye = (p.x, p.y + p.eye, p.z)
            if self.level.line_of_sight((self.x, 1.6, self.z), eye):
                self.path = [(p.x, p.z)]
            self._move(dt, C.CREATURE_ATTACK_SPEED)
            self._apply_pose("run_a" if int(self.clock * 9) % 2 else "run_b")
            if d < 1.35:
                self._strike()
                return
            if self.attack_t > 1.5:
                self._hide_model(quiet=True)                  # n'a pas atteint le joueur : elle s'évanouit
            return
        if self.attack_phase == "strike":
            if self.attack_t > .14:
                self._hide_model(quiet=True)

    def _strike(self):
        """Un seul coup : peu de dégâts, effets forts. Mortel seulement si le joueur est déjà très faible."""
        g = self.game
        p = g.player
        self.attack_phase = "strike"
        self.attack_t = 0.0
        self._face_player()
        self._apply_pose("strike")
        dmg = C.MAX_HEALTH * C.CREATURE_ATTACK_DAMAGE / 100.0
        pos3 = (self.x, 2.0, self.z)
        g.audio.play("creature_strike", 1.0, random.uniform(.95, 1.08), ignore_duck=True)
        g.audio.play("glitch_burst", .6, 1.3, ignore_duck=True)
        if p.health <= C.CREATURE_ATTACK_LETHAL_BELOW and p.health - dmg <= 0:
            p.health = 0
            p.alive = False
            g.game_over("creature")
            return
        p.damage(max(0.0, min(dmg, p.health - 1)), source=pos3)
        # caméra projetée de côté, joueur sonné, image brouillée, lampe qui tombe
        dx, dz = p.x - self.x, p.z - self.z
        n = math.hypot(dx, dz) or 1.0
        side = random.choice((-1, 1))
        p.push((dx / n * .8 + dz / n * side * .9), (dz / n * .8 - dx / n * side * .9))
        p.yaw += side * random.uniform(25, 40)
        p.trauma = 1.0
        p.daze = max(getattr(p, "daze", 0.0), C.CREATURE_ATTACK_DAZE)
        g.shake(1.0)
        g.inp.rumble(1, 1, 800)
        g.hud.dread_spike = 1.0
        fl = g.lights.flashlight
        fl.knocked = C.CREATURE_ATTACK_LAMP_OFF
        g.audio.play("flashlight_click", .9, .7)
        g.hud.message("La lampe t'échappe des mains...", color.rgb(.9, .6, .5))
        g.horror.scripted_scare(.8)

    # ==================================================================
    # LUMIÈRE : sursaut, cri, fuite
    # ==================================================================
    def _react_to_light(self, how, immediate=False):
        if self.state not in (STAGED, ATTACK):
            return
        if not immediate and self.react_t < 0:
            self.react_t = C.CREATURE_REACT_TIME
            self.lit_by = how
            return
        g = self.game
        self.lit_by = how
        if self.eyes_only:
            self._eyes_retreat()
            return
        if self.los_pt is not None and not self.eyes_only:
            # derrière un hublot : elle recule d'un coup dans le vide
            g.audio.play_at("creature_knock", (self.x, 1.4, self.z), .6, 1.3, 14)
            self._dissolve(7.0)
            return
        g.audio.play_at("creature_shriek", (self.x, 2.0 + (self.y_off if not self.upside_down else 0), self.z),
                        1.0, random.uniform(.95, 1.15), 30)
        g.inp.rumble(.5, .7, 220)
        if self.upside_down:
            # au plafond : elle détale le long du plafond et s'évanouit
            g.audio.play_at("creature_scrape1", (self.x, self.y_off, self.z), .9, 1.2, 20)
            self.state = VANISH
            self.fade_speed = 2.6
            self._skitter = (random.uniform(-1, 1), random.uniform(-1, 1))
            return
        self.state = FLEE
        self.flee_t = 0.0
        self._apply_pose("flinch")
        self.path = self._flee_path()
        if not self.path:
            self._dissolve(6.0)

    def _flee_path(self):
        """Chemin le plus court vers l'obscurité, hors de vue du joueur (ou un conduit)."""
        L = self.level
        p = self.game.player
        start = L.cell_at(self.x, self.z)
        if start not in L.links:
            return []
        eye, _, _ = self._view()
        d_now = math.hypot(self.x - p.x, self.z - p.z)
        par = {start: None}
        depth = {start: 0}
        q = deque([start])
        best = None
        while q:
            c = q.popleft()
            if c != start:
                cx, cz = L.cell_center(*c)
                ok = (self._dark_cell(c) and math.hypot(cx - p.x, cz - p.z) >= d_now - .5
                      and (L.kind[c[0]][c[1]] == VENT or not L.line_of_sight(eye, (cx, 1.6, cz))))
                if ok:
                    best = c
                    break
            if depth[c] >= 14:
                continue
            for ni, nj, st in L.links[c]:
                n = (ni, nj)
                if n in par:
                    continue
                k = ekey(c[0], c[1], ni, nj)
                if st == "door" and not L.doors[k].is_open:
                    continue
                if st == "grille" and L.grilles[k].locked:
                    continue
                cx, cz = L.cell_center(ni, nj)
                if math.hypot(cx - p.x, cz - p.z) < 1.6:
                    continue                    # jamais à travers le joueur
                par[n] = c
                depth[n] = depth[c] + 1
                q.append(n)
        if best is None:
            return []
        chain = []
        c = best
        while c is not None and c != start:
            chain.append(c)
            c = par[c]
        return [L.cell_center(*c) for c in reversed(chain)]

    def _eyes_retreat(self):
        """Les yeux se retirent dans le conduit en grattant le métal."""
        g = self.game
        g.audio.play_at(random.choice(("creature_scrape0", "creature_scrape1")), (self.x, .6, self.z), .9,
                        random.uniform(.9, 1.1), 18)
        self.state = VANISH
        self.fade_speed = 3.0

    def _dissolve(self, speed=4.0):
        """Elle s'évanouit dans le noir (fondu rapide en reculant d'un pas)."""
        self.state = VANISH
        self.fade_speed = speed
        self._skitter = None

    # ==================================================================
    # MISE À JOUR
    # ==================================================================
    def update(self, dt):
        g = self.game
        p = g.player
        if self.suspended or p is None:
            if self.visible or self.vent_eyes.enabled:
                self._hide_model(quiet=True, retreat=False)
            self.growl.set(0)
            self.hum.set(0)
            return
        self.clock += dt
        self.alert_t = max(0.0, self.alert_t - dt)
        due = [e for e in self.events if e[0] <= self.clock]
        if due:
            self.events = [e for e in self.events if e[0] > self.clock]
            for _, fn in due:
                try:
                    fn()
                except Exception as exc:
                    print("[créature] action différée :", exc)
        # cachée de l'extérieur (révélation, cinématique) : on termine proprement l'apparition
        if self.visible and not self.root.enabled:
            self._hide_model(quiet=True, retreat=False)
        st = p.search_target
        if st is not None:
            pos = getattr(st, "pos", None)
            if pos is not None:
                self.last_search_pos = (pos[0], pos[2]) if len(pos) == 3 else (pos[0], pos[1])
        if self.state in VISIBLE_STATES:
            self._update_visible(dt)
        else:
            self._update_presence(dt)
        self._dread_effects(dt)
        self._ambient(dt)

    # --- apparition visible ----------------------------------------------
    def _update_visible(self, dt):
        g = self.game
        p = g.player
        lt = g.lights
        self.stage_t += dt
        pts = self._points()
        eye, _, fwd3 = self._view()
        seen = self._seen(pts, eye)
        light = self._light_on_me(pts, eye, fwd3) if self.state in (STAGED, ATTACK) else None
        nv = lt.nightvision and light is None
        if self.need_light and self.state == STAGED:
            seen = seen and (nv or light is not None)
        self.can_see = seen
        if seen:
            self.seen_time += dt
            self.seen_ever = True
            self.unseen_t = 0.0
        else:
            self.unseen_t += dt
        dist = math.hypot(p.x - self.x, p.z - self.z)

        if self.state == ATTACK:
            self._update_attack(dt, seen, light)
            self._animate(dt)
            return

        if self.state == FLEE:
            self.flee_t += dt
            moved = self._move(dt, C.CREATURE_FLEE_SPEED)
            if self.flee_t > .12:
                self._apply_pose("crouch" if self._in_vent() else ("run_a" if int(self.clock * 10) % 2 else "run_b"))
            if not seen and self.flee_t > .15:
                self._hide_model()                         # hors de vue : elle n'est plus là
            elif self.flee_t > C.CREATURE_FLEE_MAX or (not self.path and moved == 0):
                self._dissolve(7.0)
            self._animate(dt)
            return

        if self.state == VANISH:
            self.fade = max(0.0, self.fade - dt * self.fade_speed)
            sk = getattr(self, "_skitter", None)
            if self.eyes_only:
                vx, vz = getattr(self, "_vent_dir", (0, 0))
                self.vent_eyes.x += vx * dt * 1.6
                self.vent_eyes.z += vz * dt * 1.6
                for e, g_ in self.vent_eye_parts:
                    g_.color = color.rgba(1, 1, 1, .75 * self.fade)
                    e.enabled = self.fade > .3
            elif sk is not None:
                self.x += sk[0] * dt * 6
                self.z += sk[1] * dt * 6
            else:
                # recule d'un pas dans l'ombre
                dx, dz = self.x - p.x, self.z - p.z
                n = math.hypot(dx, dz) or 1.0
                self.x += dx / n * dt * 1.4
                self.z += dz / n * dt * 1.4
            if not self.eyes_only:
                self.root.setColorScale(1, 1, 1, self.fade)
                self._set_eyes(self.fade * self.fade)
            if self.fade <= 0 or not seen:
                self._hide_model()
            self._animate(dt)
            return

        # --- STAGED : la mise en scène ------------------------------------
        kind = self.kind
        if light is not None and self.react_t < 0 and not nv:
            self._react_to_light(light)
        if self.react_t >= 0:
            self.react_t -= dt
            if self.react_t <= 0:
                self.react_t = -1.0
                self._react_to_light(self.lit_by or "lampe", immediate=True)
                self._animate(dt)
                return
        if dist < C.CREATURE_TOO_CLOSE:
            self._hide_model()                             # jamais juste devant le joueur
            return
        self.stare = nv and seen
        budget = C.CREATURE_NV_STARE if self.stare else C.CREATURE_MAX_VISIBLE
        if kind == "vent":
            budget *= 1.2                                  # deux yeux seulement : un peu plus longtemps
        if kind == "behind":
            if seen and self.glimpse_t < 0:
                # il s'est retourné : une fraction de seconde... et le choc
                self.glimpse_t = 0.0
                g.audio.play("creature_sting", 1.0, random.uniform(.95, 1.05), ignore_duck=True)
                g.inp.rumble(1, .9, 500)
                g.shake(.6)
                p.trauma = max(p.trauma, .8)
                g.horror.scripted_scare(.9)
                g.hud.dread_spike = max(g.hud.dread_spike, .7)
            if self.glimpse_t >= 0:
                self.glimpse_t += dt
                if self.glimpse_t >= C.CREATURE_GLIMPSE:
                    self._dissolve(9.0)
            elif self.stage_t >= self.max_time:
                # il ne s'est pas retourné : un craquement derrière lui, puis plus rien
                g.audio.play_at(random.choice(("creak0", "creak1", "creature_click")), (self.x, 1.5, self.z),
                                .6, random.uniform(.85, 1.0), 12)
                self._hide_model()
                return
        elif kind in ("pass", "background"):
            speed = C.CREATURE_DASH_SPEED * (.75 if kind == "background" else 1.0)
            # déplacement saccadé : figée, puis bond trop rapide
            burst = (self.stage_t * 3.1) % 1.0 < .62
            if burst:
                self._move(dt, speed)
            self._apply_pose("run_a" if int(self.clock * 9) % 2 else "run_b")
            if not self.path:
                if seen:
                    self._dissolve(6.0)
                else:
                    self._hide_model()
                return
        elif kind == "vent":
            if dist < C.CREATURE_EYES_RETREAT:
                self._eyes_retreat()
                return
        else:
            # silhouette, hublot, plafond, endroit impossible : immobiles
            if kind in ("silhouette", "impossible") and dist < self.start_dist - 2.5:
                self._dissolve(2.2)                        # on avance vers elle : elle recule dans l'ombre
                self._animate(dt)
                return
        fade_t = .4 if self.stare else .22
        if self.seen_time >= budget - fade_t:
            # règle d'or : jamais plus de quelques secondes (le fondu se termine pile à la limite)
            self._dissolve(1.0 / fade_t)
        elif self.seen_ever and self.unseen_t >= C.CREATURE_UNSEEN_VANISH:
            self._hide_model()                             # on a détourné les yeux : elle n'est plus là
            return
        elif self.stage_t >= self.max_time:
            if seen:
                self._dissolve(3.0)
            else:
                self._hide_model()
                return
        if kind not in ("pass", "background") and not self.eyes_only:
            if self.stare:
                self._face_player()
                self._apply_pose("stare")
            elif self.pose not in ("stand", "ceiling", "stare"):
                self._apply_pose("ceiling" if self.upside_down else "stand")
        self._animate(dt)

    def _animate(self, dt):
        """Immobilité parfaite, tête qui tourne par à-coups, contours qui tremblent."""
        if self.eyes_only or not self.visible:
            return
        self.head_t -= dt
        if self.head_t <= 0:
            self.head_t = random.uniform(.5, 1.6)
            if random.random() < .65:
                self.head_off = (random.uniform(-35, 35), random.uniform(-25, 25))
            else:
                self.head_off = (0.0, 0.0)
            h = self.J["head"]
            P = POSES[self.pose]["head"]
            h.rotation_y = P[1] + self.head_off[0]          # à-coup sec, sans transition
            h.rotation_z = P[2] + self.head_off[1]
        self._place_root()
        # « pas tout à fait là » : de temps en temps, l'image saute de quelques centimètres
        self.skip_t -= dt
        if self.skip_t <= 0:
            self.skip_t = random.uniform(.12, .5)
            if random.random() < .35:
                self.root.x += random.uniform(-.05, .05)
                self.root.z += random.uniform(-.05, .05)
        for q, pos, sc in self.shroud:
            q.position = (pos[0] + random.uniform(-.035, .035), pos[1] + random.uniform(-.035, .035),
                          pos[2] + random.uniform(-.03, .03))
            q.scale = sc * random.uniform(.9, 1.12)
            q.color = color.rgba(0, 0, 0, random.uniform(.32, .58) * self.fade)

    # --- présence invisible ----------------------------------------------
    def _update_presence(self, dt):
        g = self.game
        p = g.player
        L = self.level
        if self.state == HIDDEN:
            self.hidden_timer -= dt
            if self.hidden_timer <= 0:
                far = [c for c in self.vents
                       if math.hypot(L.cell_center(*c)[0] - p.x, L.cell_center(*c)[1] - p.z) > 20]
                c = random.choice(far or self.vents) if (far or self.vents) else L.random_cell(
                    near=(p.x, p.z), min_radius=20)
                if c is None:
                    self.hidden_timer = 5.0
                    return
                self.x, self.z = L.cell_center(*c)
                self.state = ROAM
                self.path = []
                self.pause = 2.0
            return
        speed = C.CREATURE_ROAM_SPEED_ALERT if (self.alert_t > 0 or g.horror.active) else C.CREATURE_ROAM_SPEED
        if self._in_vent():
            speed *= .7
        moved = self._move(dt, speed)
        if not self.path:
            if self.state == INVESTIGATE:
                self.state = ROAM
                self.pause = random.uniform(2, 5)
            self.pause -= dt
            if self.pause <= 0:
                self.pause = random.uniform(3, 9)
                self._pick_roam()
        # sons de la présence (plus souvent entendue que vue)
        d = math.hypot(self.x - p.x, self.z - p.z)
        if d > C.CREATURE_SOUND_DIST:
            return
        if moved > 0:
            self.step_t -= dt
            if self.step_t <= 0:
                # pas lourds et irréguliers : par grappes de 2-3, puis une pause
                if self.step_burst <= 0:
                    self.step_burst = random.randint(2, 3)
                    self.step_t = random.uniform(1.0, 2.6)
                else:
                    self.step_burst -= 1
                    self.step_t = random.uniform(.32, .7)
                    self._presence_sound(random.choice(("creature_heavy0", "creature_heavy1", "creature_step")),
                                         .9 if not self._in_vent() else .7)
        self.scrape_t -= dt
        if self.scrape_t <= 0:
            self.scrape_t = random.uniform(9, 20)
            self._presence_sound(random.choice(("creature_scrape0", "creature_scrape1")), .7)
        self.click_t -= dt
        if self.click_t <= 0:
            self.click_t = random.uniform(7, 16)
            if d < 13:
                self._presence_sound("creature_click", .55)
        self.breath_t -= dt
        if self.breath_t <= 0:
            self.breath_t = random.uniform(12, 24)
            if d < 10:
                self._presence_sound("creature_breath", .6)

    def _presence_sound(self, name, vol):
        """Son spatialisé de la présence : « au-dessus » dans les conduits, étouffé derrière une cloison."""
        g = self.game
        p = g.player
        vent = self._in_vent()
        y = 3.0 if vent else 1.6
        occluded = vent or not self.level.line_of_sight((self.x, 1.6, self.z), (p.x, p.y + p.eye, p.z))
        g.audio.play_at(name, (self.x, y, self.z), vol, random.uniform(.88, 1.06), C.CREATURE_SOUND_DIST, occluded)

    def _pick_roam(self):
        g = self.game
        p = g.player
        L = self.level
        d_ = g.director
        pressure = d_.pressure if d_ is not None else .3
        if self.alert_t > 0 or g.horror.active:
            pressure = max(pressure, .8)
        if random.random() < .35 + .55 * pressure:
            near_v = [c for c in self.vents if 5 < math.hypot(L.cell_center(*c)[0] - p.x,
                                                               L.cell_center(*c)[1] - p.z) < 18]
            if near_v and random.random() < .6:
                c = random.choice(near_v)
            else:
                c = L.random_cell(near=(p.x, p.z), radius=18, min_radius=7)
        else:
            c = L.random_cell(kinds=(ROOM, CORR, VENT))
        if c:
            self._go_to(*L.cell_center(*c))

    # --- effets de proximité ---------------------------------------------
    def _dread_effects(self, dt):
        """Proche : lumières qui grésillent, lampe qui clignote, image brouillée, 7 Hz, vibration lente."""
        g = self.game
        p = g.player
        lt = g.lights
        k = 0.0
        if self.visible and not self.upside_down:
            d = math.hypot(self.x - p.x, self.z - p.z)
            k = max(0.0, 1 - d / C.CREATURE_DREAD_DIST)
        if self.state not in (HIDDEN,) and not self.visible:
            d = math.hypot(self.x - p.x, self.z - p.z)
            k = max(k, .6 * max(0.0, 1 - d / (C.CREATURE_DREAD_DIST * .6)))
        self.dread += (k - self.dread) * min(1.0, dt * 3)
        k = self.dread
        lt.disturb = (self.x, 1.5, self.z, 7.5, k) if k > .05 else None
        fl = lt.flashlight
        if k > .2:
            self.flicker_t -= dt
            if self.flicker_t <= 0:
                if random.random() < k * .6:
                    fl.creature_mult = random.choice((.05, .2, .45))
                    self.flicker_t = random.uniform(.04, .16)
                else:
                    fl.creature_mult = 1.0
                    self.flicker_t = random.uniform(.15, .6)
        else:
            fl.creature_mult = 1.0
        g.hud.dread = k
        self.hum.set(k * .85, fade=2)
        self.growl.set(k * .5 if self.visible else 0, fade=2)
        if k > .25:
            self.rumble_t -= dt
            if self.rumble_t <= 0:
                self.rumble_t = 1.4
                g.inp.rumble(.18 * k, .05, 500)

    def _ambient(self, dt):
        """Silence soudain quand elle est tout près (hors de vue) ; chuchotements (infection avancée)."""
        g = self.game
        p = g.player
        d = self.presence_distance()
        busy = self.state in VISIBLE_STATES
        a = g.audio
        if (not busy and d < C.CREATURE_SILENCE_DIST and self.clock >= self.next_silence and not g.horror.active
                and a.duck >= 1.0):
            self.next_silence = self.clock + C.CREATURE_SILENCE_GAP
            a.silence(keep_loops=("creature_hum",))

            def one_noise():
                fx, fz = p.forward2()
                pos = (p.x - fx * 1.6, 1.8, p.z - fz * 1.6)
                a.play_at(random.choice(("creature_knock", "creature_breath", "creature_click")), pos, 1.0,
                          random.uniform(.85, 1.0), 10, ignore_duck=True)
                g.inp.rumble(.5, .2, 300)
            self.events.append((self.clock + 2.1, one_noise))
            self.events.append((self.clock + 2.9, lambda: a.restore(3.0)))
        hl = g.hallu
        if hl is not None and hl.infection >= C.CREATURE_WHISPER_INFECTION and d < 14 and not busy:
            if self.clock >= self.next_whisper:
                self.next_whisper = self.clock + random.uniform(*C.CREATURE_WHISPER_GAP)
                i = random.randrange(len(WHISPERS))
                a.play(f"shadow_whisper{i}", .3 + .2 * hl.infection, random.uniform(.94, 1.03),
                       balance=random.choice((-.75, .75)))
                g.hud.message(f"« ...{WHISPERS[i]} »", color.rgb(.5, .52, .55))

    # ==================================================================
    # DEBUG (F2)
    # ==================================================================
    def debug_text(self):
        g = self.game
        p = g.player
        d_ = g.director
        lines = [f"CRÉATURE  état : {self.state}"
                 + (f" ({KIND_LABELS.get(self.kind, self.kind)})" if self.kind else ""),
                 f"position ({self.x:.1f}, {self.z:.1f})  distance {self.presence_distance():.1f} m"
                 f"  corps visible : {'oui' if self.visible else 'non'}  vue par le joueur : "
                 f"{'OUI' if self.can_see else 'non'}",
                 f"temps à l'écran : {self.seen_time:.1f} / {C.CREATURE_MAX_VISIBLE:.1f} s"
                 f"  éclairée : {self.lit_by or 'non'}  audace : {'oui' if self._bold() else 'non'}"
                 f"  malaise : {self.dread:.2f}"]
        if d_ is not None:
            lines += d_.debug_lines()
        return "\n".join(lines)

    def destroy(self):
        g = self.game
        g.audio.stop_loop("creature_growl")
        g.audio.stop_loop("creature_hum")
        if g.lights is not None:
            g.lights.disturb = None
            g.lights.flashlight.creature_mult = 1.0
        destroy(self.vent_eyes)
        destroy(self.root)


# ============================================================================
class AIDirector:
    """
    Directrice d'IA : décide QUAND et COMMENT la créature se montre.
      * récupération de plusieurs dizaines de secondes entre deux apparitions ;
      * jamais deux types identiques à la suite ;
      * choix selon la situation (lecture / fouille, grande salle, grille ou
        hublot proche, long couloir...) ;
      * attaque rare quand le joueur reste longtemps dans le noir ;
      * après le disque dur : apparitions plus fréquentes et plus étranges.
    """

    def __init__(self, game):
        self.game = game
        self.grace = 0.0             # répit imposé (tests) : rien ne se passe tant qu'il dure
        self.pressure = .2           # 0..1 : envie de la présence de se rapprocher
        self.cooldown = C.CREATURE_FIRST_DELAY
        self.last_kind = None
        self.history = []
        self.dark_time = 0.0
        self.since_attack = C.CREATURE_ATTACK_MIN_GAP * .5
        self.attack_check = 5.0
        self.preview = None
        self.preview_t = 0.0
        self.trying = []             # types restant à essayer pour l'apparition en cours de préparation
        self.calm = 0.0

    def on_noise(self):
        """Un coup de feu : elle arrive. La prochaine apparition sera bien plus tôt."""
        self.cooldown = min(self.cooldown, random.uniform(*C.CREATURE_ALERT_COOLDOWN))
        self.pressure = max(self.pressure, .8)

    def on_end(self, kind):
        pass

    def _mult(self):
        g = self.game
        m = 1.0
        if g.has_hdd():
            m *= C.CREATURE_HDD_COOLDOWN_MULT
        cr = g.creature
        if cr is not None and cr._bold():
            m *= C.CREATURE_BOLD_COOLDOWN_MULT
        return m

    def _busy_player(self):
        g = self.game
        p = g.player
        reader = getattr(g, "reader", None)
        return ((reader is not None and reader.is_open) or p.search_target is not None
                or (g.inventory_ui is not None and g.inventory_ui.reading))

    def weights(self):
        """Poids de chaque type d'apparition selon la situation (le précédent est exclu)."""
        g = self.game
        p = g.player
        L = g.level
        w = {"silhouette": 3.0, "behind": 2.4, "pass": 2.2, "window": 1.2, "vent": 1.4,
             "ceiling": C.CREATURE_CEILING_CHANCE * 3}
        room = L.room_at(p.x, p.z)
        if room is not None and room.height >= 4.0:
            w["ceiling"] *= 2.2
        else:
            w["ceiling"] = 0.0
        if room is not None and room.grilles:
            w["vent"] *= 2.0
        if room is None:
            w["silhouette"] *= 1.5             # couloir : la silhouette au bout
            w["pass"] *= 1.3
        if self._busy_player():
            w = {"background": 6.0, "behind": 1.5}
        if g.has_hdd():
            w["impossible"] = 2.5
        if self.last_kind in w:
            w[self.last_kind] = 0.0            # jamais deux fois de suite le même type
        return {k: v for k, v in w.items() if v > 0}

    def choose(self):
        w = self.weights()
        order = []
        while w:
            tot = sum(w.values())
            r = random.uniform(0, tot)
            for k, v in w.items():
                r -= v
                if r <= 0:
                    order.append(k)
                    del w[k]
                    break
            else:
                break
        return order

    def force(self, kind):
        """Maj+F2 : apparition immédiate (test)."""
        cr = self.game.creature
        if cr is None:
            return False
        if cr.staging():
            cr._hide_model(quiet=True, retreat=False)
        ok = cr.stage(kind)
        if ok:
            self._record(kind)
        return ok

    def _record(self, kind):
        self.last_kind = kind
        self.history = (self.history + [kind])[-5:]
        self.cooldown = random.uniform(*C.CREATURE_COOLDOWN) * self._mult()
        cr = self.game.creature
        cr.echo = self.game.has_hdd() and kind in ("silhouette", "impossible", "pass") and \
            random.random() < C.CREATURE_DOUBLE_CHANCE

    def update(self, dt):
        g = self.game
        cr = g.creature
        p = g.player
        if cr is None or p is None:
            return
        lt = g.lights
        # obscurité : la vision nocturne n'est pas de la lumière pour elle
        dark = lt.flashlight.effective < .2 and not lt.lit_at(p.x, p.z)
        self.dark_time = self.dark_time + dt if dark else 0.0
        self.since_attack += dt
        if self.grace > 0:
            self.grace -= dt
            self.pressure = .05
            return
        if cr.suspended or cr.staging():
            return
        # rythme : plus rapide pendant une alerte, après le disque dur, lampe faible
        rate = 1.0 / self._mult()
        if g.horror.active:
            rate *= 2.0
        if self._busy_player():
            rate *= 1.6                         # pendant une lecture : moment idéal
        self.cooldown -= dt * rate
        self.pressure = max(.15, min(.9, 1 - self.cooldown / max(1.0, C.CREATURE_COOLDOWN[1])))
        # attaque rare : le joueur est dans le noir depuis longtemps
        if (self.dark_time >= C.CREATURE_ATTACK_DARK_TIME and self.since_attack >= C.CREATURE_ATTACK_MIN_GAP
                and not self._busy_player() and p.alive):
            self.attack_check -= dt
            if self.attack_check <= 0:
                self.attack_check = 5.0
                chance = C.CREATURE_ATTACK_CHANCE * (1.8 if cr._bold() else 1.0)
                if random.random() < chance and cr.start_attack():
                    self.since_attack = 0.0
                    self.dark_time = 0.0
                    self.last_kind = "attack"
                    self.history = (self.history + ["attack"])[-5:]
                    self.cooldown = max(self.cooldown, 25.0)
                    return
        # aperçu du prochain type (debug)
        self.preview_t -= dt
        if self.preview_t <= 0:
            self.preview_t = 1.0
            order = self.choose()
            self.preview = order[0] if order else None
        if self.cooldown <= 0:
            # un seul essai par image (la recherche d'un emplacement coûte quelques millisecondes)
            if not self.trying:
                self.trying = self.choose()
            kind = self.trying.pop(0) if self.trying else None
            if kind is not None and cr.stage(kind):
                self.trying = []
                self._record(kind)
                return
            if not self.trying:
                self.cooldown = 4.0             # aucun endroit crédible : on réessaie bientôt

    def debug_lines(self):
        nxt = KIND_LABELS.get(self.preview, self.preview or "—")
        att = max(0.0, C.CREATURE_ATTACK_MIN_GAP - self.since_attack)
        return [f"DIRECTRICE  prochaine apparition dans {max(0.0, self.cooldown):.0f} s (prévue : {nxt})"
                + (f"  répit {self.grace:.0f} s" if self.grace > 0 else ""),
                f"historique : {', '.join(KIND_LABELS.get(k, k) for k in self.history) or '—'}",
                f"dans le noir depuis {self.dark_time:.0f} s  attaque possible dans {att:.0f} s"
                f"  pression {self.pressure:.2f}"]
