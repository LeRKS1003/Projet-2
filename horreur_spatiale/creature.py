# -*- coding: utf-8 -*-
"""
creature.py — La grande créature (invulnérable) et la directrice d'IA.

États :
  ERRANCE    : se promène d'un point à l'autre (A* sur la grille)
  ENQUETE    : va vers le dernier bruit entendu
  TRAQUE     : voit le joueur (cône de vision + ligne de vue) et le poursuit
  RECHERCHE  : a perdu le joueur, fouille les environs
  RETRAITE   : blessée ou lassée, rejoint un conduit et disparaît un moment
  CACHEE     : invisible dans les conduits, réapparaît ailleurs

Contact = mort instantanée. Les balles la ralentissent / la font fuir.
"""
import math
import random

from ursina import Entity, color, destroy

import numpy as np

import config as C
import textures
from geometry import MeshBuilder
from generator import VENT, CORR, ROOM

WANDER, INVESTIGATE, CHASE, SEARCH, RETREAT, HIDDEN = "ERRANCE", "ENQUETE", "TRAQUE", "RECHERCHE", "RETRAITE", "CACHEE"


def _creature_skin(rng):
    """Peau sombre, humide et brillante, plis, veines, zones de chair plus claires."""
    s = 256
    n = textures.fractal_noise(s, s, rng, 6, base=4)
    folds = textures.fractal_noise(s, s, rng, 5, base=8)
    veins = np.clip(1 - np.abs(textures.fractal_noise(s, s, rng, 5, base=5) - .5) * 25, 0, 1)
    flesh = np.clip((textures.fractal_noise(s, s, rng, 4, base=3) - .62) * 5, 0, 1)
    alb = np.dstack([.07 + .04 * n, .06 + .03 * n, .07 + .035 * n])
    alb = alb * (1 - flesh[..., None]) + flesh[..., None] * np.array([.32, .22, .22]) * (.7 + .3 * n[..., None])
    alb = alb * (1 - veins[..., None] * .5)
    h = .5 + (folds - .5) * .7 + veins * .25
    rough = np.clip(.12 + .15 * n + flesh * .1, .04, 1)        # très brillante (humide)
    return np.clip(alb, 0, 1), h, rough, (1.5, 60, 2.6)


def _lerp_angle(a, b, t):
    d = (b - a + 180) % 360 - 180
    return a + d * t


class Creature:
    aware = True

    def __init__(self, game, level, cell):
        self.game = game
        self.level = level
        self.x, self.z = level.cell_center(*cell)
        self.yaw = 0.0
        self.state = WANDER
        self.path = []
        self.goal = None
        self.repath = 0.0
        self.state_timer = 0.0
        self.perceive_timer = 0.0
        self.can_see = False
        self.last_seen = None
        self.lost_timer = 0.0
        self.search_center = None
        self.stun = 0.0
        self.slow = 0.0
        self.hits = []
        self.hidden_timer = 0.0
        self.visible = True
        self.walk_phase = 0.0
        self.crawl_k = 0.0
        self.step_timer = 0.0
        self.pause = 0.0
        self.chase_time = 0.0
        self.roar_cd = 0.0
        self.speed_now = 0.0
        self.alert_flash = 0.0
        self.suspended = False       # révélation : l'hallucination est « tombée »
        self._build_model()
        self.growl = game.audio.loop("creature_growl", "creature_growl", 1.0)

    # ------------------------------------------------------------------
    def _build_model(self):
        """
        Silhouette longue et voûtée en meshes personnalisés : torse extrudé,
        colonne vertébrale saillante, cage thoracique, bras démesurés à griffes,
        jambes digitigrades, tête allongée SANS visage dont la mâchoire s'ouvre
        verticalement (en deux moitiés). Peau sombre, humide et brillante.
        """
        skin = textures.material("creature_skin", custom=_creature_skin)
        SK = (1, 1, 1, 1)
        BONE = (1.9, 1.75, 1.6, 1)      # plus clair (os / chair sous la peau)

        def mesh(parent, mb, name):
            np_ = parent.attachNewNode(mb.make_geom_node(name))
            textures.apply_material(np_, skin)
            return np_

        self.root = Entity(name='creature')
        self.body = Entity(parent=self.root, y=1.3)                # bassin
        # --- torse voûté (extrudé le long de +z, puis redressé) -------------
        self.torso = Entity(parent=self.body, rotation_x=-62)
        tb = MeshBuilder(uv_scale=.6)
        tb.loft([(0, 0, 0, .42, .3, .1), (.3, 0, .02, .5, .36, .14), (.7, 0, .05, .62, .42, .17),
                 (1.05, 0, .04, .66, .44, .18), (1.3, 0, .0, .5, .34, .14), (1.45, 0, -.02, .26, .2, .08)], SK)
        # colonne vertébrale saillante (côté dos = +y local)
        for k in range(12):
            z = .05 + k * .12
            tb.bevel_box((0, .22 + .03 * math.sin(k * .7), z), (.07, .1, .07), .02, BONE, rot=(-25, 0, 0))
        # cage thoracique : côtes qui entourent le ventre (côté -y)
        for k in range(6):
            z = .55 + k * .12
            for sd in (-1, 1):
                tb.bevel_box((sd * .3, -.08, z), (.05, .06, .05), .015, BONE, rot=(0, 0, sd * 20))
                tb.bevel_box((sd * .2, -.22, z - .02), (.2, .035, .04), .012, BONE, rot=(0, sd * 10, sd * -35))
        mesh(self.torso, tb, "creature_torso")
        # bassin
        pb = MeshBuilder(uv_scale=.5)
        pb.bevel_box((0, 0, 0), (.46, .24, .3), .09, SK)
        pb.bevel_box((0, .12, -.1), (.12, .1, .12), .03, BONE)
        mesh(self.body, pb, "creature_pelvis")
        # --- cou et tête allongée sans visage ---------------------------------
        self.neck = Entity(parent=self.torso, z=1.45, y=-.02)
        nb = MeshBuilder(uv_scale=.4)
        nb.loft([(0, 0, 0, .2, .18, .06), (.25, 0, .02, .16, .15, .05)], SK)
        for k in range(3):
            nb.bevel_box((0, .1, .04 + k * .08), (.05, .06, .05), .015, BONE)
        mesh(self.neck, nb, "creature_neck")
        self.head = Entity(parent=self.neck, z=.25, rotation_x=62)      # la tête regarde vers l'avant
        hb = MeshBuilder(uv_scale=.4)
        hb.loft([(-.12, 0, .05, .26, .26, .09), (0, 0, .06, .32, .3, .11), (.22, 0, .05, .27, .24, .09),
                 (.45, 0, .02, .2, .17, .06), (.62, 0, 0, .12, .1, .04)], SK)      # crâne allongé, lisse
        hb.bevel_box((0, .16, 0), (.08, .06, .38), .02, BONE)                      # crête
        mesh(self.head, hb, "creature_head")
        # mâchoire verticale : deux moitiés gauche / droite qui s'écartent
        self.jaws = []
        for sd in (-1, 1):
            j = Entity(parent=self.head, position=(sd * .03, -.08, .08))
            jb = MeshBuilder(uv_scale=.3)
            jb.bevel_box((sd * .06, 0, .22), (.1, .14, .46), .04, SK)
            for k in range(7):                                                     # dents (cônes)
                jb.cone((-sd * .005, -.04 + (k % 2) * .03, .06 + k * .06), .012, .07, (2.2, 2.1, 1.9, 1),
                        (1.6, 1.4, 1.2, 1), 6, (0, 0, 1))
            np_ = mesh(j, jb, "creature_jaw")
            np_.setR(sd * 90)          # dents orientées vers l'intérieur de la gueule
            self.jaws.append((j, sd))
        # --- bras démesurés terminés par des griffes -------------------------
        self.arms = []
        for sd in (-1, 1):
            sh = Entity(parent=self.torso, position=(sd * .36, 0, 1.25))
            ab = MeshBuilder(uv_scale=.4)
            ab.bevel_box((0, 0, 0), (.16, .16, .16), .05, SK)                       # épaule
            ab.bevel_box((0, -.5, 0), (.1, 1.0, .1), .035, SK)                      # bras
            ab.bevel_box((0, -.35, .03), (.06, .2, .06), .02, BONE)                 # tendon
            mesh(sh, ab, "creature_upper_arm")
            elbow = Entity(parent=sh, y=-1.0)
            fb = MeshBuilder(uv_scale=.4)
            fb.bevel_box((0, -.55, 0), (.085, 1.1, .085), .03, SK)
            fb.bevel_box((0, -1.12, 0), (.13, .12, .1), .04, SK)                    # main
            mesh(elbow, fb, "creature_forearm")
            claws = []
            for c in (-1, 0, 1):
                cl = Entity(parent=elbow, position=(c * .045, -1.16, .02), rotation_x=95 + abs(c) * 8,
                            rotation_z=c * 12)
                cb = MeshBuilder(uv_scale=.1)
                cb.cone((0, 0, 0), .02, .42, BONE, (1.2, 1.1, 1.0, 1), 6, (0, 0, 1))
                mesh(cl, cb, "creature_claw")
                claws.append(cl)
            self.arms.append((sh, elbow, claws))
        # --- jambes digitigrades --------------------------------------------
        self.legs = []
        for sd in (-1, 1):
            hip = Entity(parent=self.body, position=(sd * .2, -.02, 0))
            lb = MeshBuilder(uv_scale=.4)
            lb.bevel_box((0, -.36, .05), (.15, .74, .15), .05, SK)
            mesh(hip, lb, "creature_thigh")
            knee = Entity(parent=hip, y=-.72, z=.08)
            kb = MeshBuilder(uv_scale=.4)
            kb.bevel_box((0, -.33, 0), (.1, .68, .1), .035, SK)
            kb.bevel_box((0, 0, .04), (.1, .1, .08), .03, BONE)                     # rotule
            mesh(knee, kb, "creature_shin")
            ankle = Entity(parent=knee, y=-.66)
            fb2 = MeshBuilder(uv_scale=.3)
            fb2.bevel_box((0, -.15, 0), (.08, .32, .08), .03, SK)
            for c in (-1, 0, 1):
                fb2.cone((c * .04, -.3, .0), .018, .22, BONE, (1.2, 1.1, 1, 1), 6, (0, 0, 1))
            mesh(ankle, fb2, "creature_foot")
            self.legs.append((hip, knee, ankle))
        self.eyes = []              # sans visage : aucun œil
        self.jaw_open = 0.0
        self.twist = 0.0
        self.twist_target = 0.0
        self.twist_timer = random.uniform(2, 5)
        self.hitch = 0.0

    # ------------------------------------------------------------------
    def hit_spheres(self):
        if not self.visible:
            return []
        fx, fz = math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw))
        h = 1 - .5 * self.crawl_k
        return [((self.x, 1.6 * h, self.z), .6), ((self.x + fx * .5, 2.35 * h, self.z + fz * .5), .38),
                ((self.x, .8 * h, self.z), .45)]

    def center3(self):
        return (self.x, 1.5, self.z)

    def on_hit(self, dmg, pos, gun):
        """Les balles ne la tuent pas : elle est sonnée, ralentie ou fuit."""
        g = self.game
        if not gun:
            return
        now = g.time
        self.hits = [t for t in self.hits if now - t < 20] + [now]
        self.stun = C.CREATURE_STUN_TIME
        self.slow = 4.0
        g.audio.play_at("creature_roar", (self.x, 2, self.z), 1.0, random.uniform(1.05, 1.2))
        if len(self.hits) >= C.CREATURE_HITS_TO_FLEE:
            self.hits = []
            self.start_retreat()
            g.hud.message("La créature bat en retraite dans les conduits...", color.rgb(.8, .7, .6))

    # ------------------------------------------------------------------
    def sees_player_now(self):
        return self.can_see

    def hear(self, pos, radius, kind):
        if self.state in (HIDDEN, RETREAT):
            if kind == "shot" and self.state == HIDDEN and random.random() < .5:
                # un tir peut la faire sortir plus tôt de sa cachette
                self.hidden_timer = min(self.hidden_timer, 4.0)
            return
        d = math.hypot(pos[0] - self.x, pos[2] - self.z)
        if d > radius:
            return
        # le couteau est discret : la bête ne l'entend que tout près, et rarement
        if kind == "knife" and (d > C.KNIFE_ALERT_DIST or random.random() > C.KNIFE_ALERT_CHANCE):
            return
        if self.state == CHASE and self.can_see:
            return
        self.last_seen = (pos[0], pos[2])
        if self.state != INVESTIGATE or kind == "shot":
            self.game.audio.play_at("creature_hiss", (self.x, 2, self.z), .8)
        self.set_state(INVESTIGATE)
        self._go_to(pos[0], pos[2])

    def investigate(self, x, z):
        if self.state in (HIDDEN, RETREAT, CHASE):
            return
        self.set_state(INVESTIGATE)
        self._go_to(x, z)

    def set_state(self, s):
        if s != self.state:
            self.state = s
            self.state_timer = 0.0
            if s == CHASE:
                self.chase_time = 0.0

    def start_retreat(self):
        vents = self.level.vent_cells()
        self.set_state(RETREAT)
        if vents:
            here = self.level.cell_at(self.x, self.z)
            vents.sort(key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1]))
            for c in vents[:6]:
                x, z = self.level.cell_center(*c)
                if self._go_to(x, z):
                    return
        self.hidden_timer = random.uniform(*C.CREATURE_HIDE_TIME)

    # ------------------------------------------------------------------
    def _go_to(self, x, z):
        L = self.level
        start = L.cell_at(self.x, self.z)
        goal = L.cell_at(x, z)
        if start not in L.links:
            # sortie d'un mur : on se replace
            c = L.random_cell(near=(self.x, self.z), radius=6)
            if c:
                self.x, self.z = L.cell_center(*c)
                start = c
        if goal not in L.links:
            return False
        path = L.find_path(start, goal, "creature")
        if not path:
            return False
        self.path = [L.cell_center(*c) for c in path[1:]]
        if self.path:
            self.path[-1] = (x, z)
        self.goal = (x, z)
        return True

    def _perceive(self):
        g = self.game
        p = g.player
        self.can_see = False
        if p is None or not p.alive or not self.visible:
            return
        dx, dz = p.x - self.x, p.z - self.z
        d = math.hypot(dx, dz)
        if p.hidden:
            # cachée sous ses yeux -> elle sait
            if p.saw_hide and d < 5 and self.state == CHASE:
                self.can_see = True
            return
        view = C.CREATURE_VIEW_DIST
        if g.lights.flashlight_on and g.lights.battery > 0:
            view *= 1.7
        if p.crouched:
            view *= .55
        if p.running:
            view *= 1.2
        if self.state == CHASE:
            view *= 1.5
        if d > view:
            return
        fx, fz = math.sin(math.radians(self.yaw)), math.cos(math.radians(self.yaw))
        cos_half = math.cos(math.radians(C.CREATURE_VIEW_ANGLE / 2))
        in_cone = (dx * fx + dz * fz) / max(d, 1e-4) > cos_half
        if not in_cone and d > 2.5 and self.state != CHASE:
            return
        eye = (self.x, 2.2 - self.crawl_k, self.z)
        if self.level.line_of_sight(eye, (p.x, p.eye, p.z)):
            self.can_see = True

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        p = g.player
        L = self.level
        if self.suspended:
            self.growl.set(0)
            return
        self.state_timer += dt
        self.roar_cd = max(0.0, self.roar_cd - dt)
        self.alert_flash = max(0.0, self.alert_flash - dt)
        if self.state == HIDDEN:
            self.hidden_timer -= dt
            self.growl.set(0)
            if self.hidden_timer <= 0:
                self._reappear()
            return
        self.perceive_timer -= dt
        if self.perceive_timer <= 0:
            self.perceive_timer = .15
            self._perceive()
            if self.can_see:
                self.last_seen = (p.x, p.z)
                self.lost_timer = 0
                if self.state not in (CHASE, RETREAT):
                    self.set_state(CHASE)
                    self.alert_flash = 1.0
                    if self.roar_cd <= 0:
                        self.roar_cd = 8
                        g.audio.play_at("creature_roar", (self.x, 2, self.z), 1.0)
                        g.inp.rumble(1, .6, 600)
        # --- machine à états ----------------------------------------------
        speed = C.CREATURE_SPEED_WANDER
        target = None
        if self.state == WANDER:
            if not self.path:
                if self.pause <= 0:
                    self.pause = random.uniform(1.5, 4.0)
                else:
                    self.pause -= dt
                    if self.pause <= 0:
                        self._pick_wander()
        elif self.state == INVESTIGATE:
            speed = C.CREATURE_SPEED_INVESTIGATE
            if not self.path:
                self.set_state(SEARCH)
                self.search_center = (self.x, self.z)
        elif self.state == CHASE:
            speed = C.CREATURE_SPEED_CHASE
            self.chase_time += dt
            if self.can_see:
                d = math.hypot(p.x - self.x, p.z - self.z)
                if d < 9:
                    target = (p.x, p.z)
                    self.path = []
                else:
                    self.repath -= dt
                    if self.repath <= 0 or not self.path:
                        self.repath = .6
                        self._go_to(p.x, p.z)
            else:
                self.lost_timer += dt
                if not self.path and self.last_seen:
                    self._go_to(*self.last_seen)
                if self.lost_timer > C.CREATURE_LOSE_TIME:
                    self.set_state(SEARCH)
                    self.search_center = self.last_seen or (self.x, self.z)
                    self.path = []
            # la directrice lui laisse une chance si la traque dure trop
            if self.chase_time > 40:
                self.start_retreat()
        elif self.state == SEARCH:
            speed = C.CREATURE_SPEED_WANDER * 1.3
            if not self.path:
                if self.pause <= 0:
                    self.pause = random.uniform(.8, 2.2)
                else:
                    self.pause -= dt
                    if self.pause <= 0:
                        c = L.random_cell(near=self.search_center, radius=9)
                        if c:
                            self._go_to(*L.cell_center(*c))
            if self.state_timer > C.CREATURE_SEARCH_TIME:
                self.set_state(WANDER)
        elif self.state == RETREAT:
            speed = C.CREATURE_SPEED_INVESTIGATE
            if not self.path:
                self._hide()
                return

        if self.slow > 0:
            self.slow -= dt
            speed *= .5
        if self.stun > 0:
            self.stun -= dt
            speed = 0.0
        ci, cj = L.cell_at(self.x, self.z)
        in_vent = L.inside(ci, cj) and L.kind[ci][cj] == VENT
        if in_vent:
            speed *= C.CREATURE_VENT_SPEED_MULT
        self.crawl_k += ((1.0 if in_vent else 0.0) - self.crawl_k) * min(1, dt * 5)

        # --- déplacement --------------------------------------------------
        moved = 0.0
        if target is None and self.path:
            target = self.path[0]
            if math.hypot(target[0] - self.x, target[1] - self.z) < .45:
                self.path.pop(0)
                target = self.path[0] if self.path else None
        if target is not None and speed > 0:
            dx, dz = target[0] - self.x, target[1] - self.z
            d = math.hypot(dx, dz)
            if d > .05:
                step = min(d, speed * dt)
                nx, nz = self.x + dx / d * step, self.z + dz / d * step
                self._open_doors_between(self.x, self.z, nx, nz)
                self.x, self.z = nx, nz
                moved = step
                want = math.degrees(math.atan2(dx, dz))
                self.yaw = _lerp_angle(self.yaw, want, min(1, dt * 6))
        self.speed_now = moved / max(dt, 1e-5)

        # --- mise à mort --------------------------------------------------
        if p is not None and p.alive:
            d = math.hypot(p.x - self.x, p.z - self.z)
            if d < C.CREATURE_KILL_DIST and self.stun <= 0:
                if not p.hidden or (p.saw_hide and self.state == CHASE):
                    g.game_over("creature")
                    return

        self._animate(dt, moved)
        self._sounds(dt, moved)

    def _open_doors_between(self, x0, z0, x1, z1):
        L = self.level
        dx, dz = x1 - x0, z1 - z0
        d = math.hypot(dx, dz) or 1.0
        a = L.cell_at(x0, z0)
        b = L.cell_at(x0 + dx / d * 1.1, z0 + dz / d * 1.1)   # regarde 1,1 m devant
        if a == b:
            return
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            return
        from generator import ekey
        k = ekey(a[0], a[1], b[0], b[1])
        door = L.doors.get(k)
        if door and door.target < 1 and not door.locked:
            # sans courant, elle arrache littéralement la porte (qui reste ouverte)
            forced = door.unpowered
            door.open(hold=4, force=True)
            self.game.audio.play_at("metal_bang", (door.pos[0], 1.5, door.pos[1]), 1.0 if forced else .8, .7)
            if forced:
                self.game.audio.play_at("door_force_open", (door.pos[0], 1.2, door.pos[1]), 1.0, .8)
            self.stun = max(self.stun, .8 if forced else .35)
        gr = L.grilles.get(k)
        if gr and not gr.opened and not gr.locked:
            gr.set_open(True)
            self.game.audio.play_at("vent_bang", (gr.pos[0], .5, gr.pos[1]), 1.0)

    def _pick_wander(self):
        g = self.game
        L = self.level
        p = g.player
        near = None
        if p is not None and random.random() < g.director.pressure:
            near = (p.x, p.z)
        if near:
            c = L.random_cell(near=near, radius=16, min_radius=6)
        else:
            c = L.random_cell(kinds=(ROOM, CORR))
        if c:
            self._go_to(*L.cell_center(*c))

    def _hide(self):
        self.set_state(HIDDEN)
        self.hidden_timer = random.uniform(*C.CREATURE_HIDE_TIME)
        self.visible = False
        self.root.enabled = False
        self.path = []

    def appear_at(self, x, z):
        """Réapparaît à un endroit précis (révélation : entre le joueur et le hangar)."""
        self.x, self.z = x, z
        self.visible = True
        self.root.enabled = True
        self.stun = 0.0
        self.hidden_timer = 0.0
        self.set_state(WANDER)
        self.path = []
        self.pause = .3
        self._animate(0.0, 0.0)

    def _reappear(self):
        L = self.level
        p = self.game.player
        vents = L.vent_cells()
        far = [c for c in vents if p is None or math.hypot(L.cell_center(*c)[0] - p.x, L.cell_center(*c)[1] - p.z) > 22]
        c = random.choice(far or vents) if (far or vents) else L.random_cell(near=(p.x, p.z), min_radius=25)
        if c is None:
            self.hidden_timer = 5
            return
        self.x, self.z = L.cell_center(*c)
        self.visible = True
        self.root.enabled = True
        self.set_state(WANDER)
        self.path = []
        self.pause = .5

    # ------------------------------------------------------------------
    def _animate(self, dt, moved):
        self.root.position = (self.x, 0, self.z)
        self.root.rotation_y = self.yaw
        t = self.game.time
        c = self.crawl_k
        hunt = 1.0 if self.state == CHASE else 0.0
        # démarche irrégulière : boiterie et petits à-coups
        self.hitch -= dt
        if self.hitch <= 0 and moved > 0 and random.random() < dt * .8:
            self.hitch = random.uniform(.15, .35)
        stutter = .25 if self.hitch > 0 else 1.0
        self.walk_phase += moved * 2.2 * stutter
        ph = self.walk_phase
        # posture : plus basse et penchée quand elle traque, à quatre pattes dans les conduits
        self.body.y = 1.3 * (1 - c * .62) - .18 * hunt + abs(math.sin(ph)) * .05
        self.body.rotation_x = c * 40 + 6 * hunt
        self.torso.rotation_x = -62 + 18 * hunt + c * 45 + math.sin(t * 1.1) * 2     # respiration
        for sd, (hip, knee, ankle) in zip((1, -1), self.legs):
            limp = 1.0 if sd > 0 else .7                                            # boiterie
            a = math.sin(ph + (0 if sd > 0 else math.pi))
            hip.rotation_x = a * 32 * limp - 18 - c * 55 - 10 * hunt
            knee.rotation_x = 38 + max(0, math.sin(ph + (0 if sd > 0 else math.pi) + 1.2)) * 35 + c * 40
            ankle.rotation_x = -40 - max(0, a) * 15
        for sd, (sh, elbow, claws) in zip((1, -1), self.arms):
            sw = math.sin(ph + (math.pi if sd > 0 else 0)) * 22
            # bras qui pendent, balancent ; tendus vers l'avant en chasse / dans les conduits
            sh.rotation_x = 62 - 15 + sw - c * 65 - 45 * hunt
            sh.rotation_z = sd * (10 + 4 * math.sin(t * 1.3 + sd))
            elbow.rotation_x = -25 - abs(sw) * .4 - 25 * hunt
            flex = (math.sin(t * 7 + sd) * .5 + .5) * (8 + 20 * hunt)               # griffes qui se crispent
            for k, cl in enumerate(claws):
                cl.rotation_x = 95 + (k - 1) ** 2 * 8 - flex
        # tête : se tord brusquement pour écouter
        self.twist_timer -= dt
        listening = self.state in (INVESTIGATE, SEARCH, WANDER)
        if self.twist_timer <= 0:
            self.twist_timer = random.uniform(.6, 1.4) if listening else random.uniform(2.5, 5)
            self.twist_target = random.choice((-1, 1)) * random.uniform(35, 70) if random.random() < .7 else 0.0
        self.twist += (self.twist_target - self.twist) * min(1, dt * 14)            # mouvement sec
        tic = math.sin(t * 17) * math.sin(t * 3.1)
        self.neck.rotation_x = -8 + tic * 5 - c * 25 - 10 * hunt
        self.neck.rotation_y = math.sin(t * .7) * 12 + (tic * 18 if abs(tic) > .85 else 0)
        self.head.rotation_z = self.twist
        # mâchoire verticale : s'entrouvre en traque, grande ouverte près du joueur
        p = self.game.player
        near = p is not None and math.hypot(p.x - self.x, p.z - self.z) < 4
        target = 1.0 if (hunt and near) else (.45 + .15 * math.sin(t * 4)) * hunt + .05
        self.jaw_open += (target - self.jaw_open) * min(1, dt * 6)
        for j, sd in self.jaws:
            j.rotation_y = sd * 32 * self.jaw_open

    def _sounds(self, dt, moved):
        g = self.game
        att, bal = g.audio.spatial((self.x, 2, self.z), 26)
        vol = att * (1.0 if self.state == CHASE else .7)
        self.growl.set(vol, pitch=1.15 if self.state == CHASE else 1.0, balance=bal, fade=3)
        if moved > 0:
            self.step_timer -= moved
            if self.step_timer <= 0:
                self.step_timer = 1.4 if self.crawl_k < .5 else .9
                g.audio.play_at("creature_step", (self.x, .2, self.z), 1.0 if self.crawl_k < .5 else .5,
                                random.uniform(.85, 1.05), 30)
                if att > .3:
                    g.inp.rumble(.3 * att, 0, 90)

    def destroy(self):
        self.game.audio.stop_loop("creature_growl")
        destroy(self.root)


# ============================================================================
class AIDirector:
    """
    Directrice d'IA : si le joueur est tranquille trop longtemps, elle
    rapproche la créature (pression). Si la traque dure, elle la rappelle.
    """

    def __init__(self, game):
        self.game = game
        self.calm = 0.0
        self.pressure = .2
        self.grace = 50.0            # début de partie : un peu de répit

    def update(self, dt):
        g = self.game
        cr = g.creature
        p = g.player
        if cr is None or p is None:
            return
        if self.grace > 0:
            self.grace -= dt
            self.pressure = .05
            return
        d = math.hypot(cr.x - p.x, cr.z - p.z) if cr.visible else 99
        if d < 16 or cr.state == CHASE or g.horror.active:
            self.calm = 0.0
        else:
            self.calm += dt
        threshold = C.DIRECTOR_CALM_TIME * (.5 if g.has_hdd() else 1.0)
        self.pressure = min(.8, .2 + self.calm / threshold * .5 + (.25 if g.has_hdd() else 0))
        if self.calm > threshold:
            self.calm = 0.0
            if cr.state == WANDER or cr.state == SEARCH:
                c = g.level.random_cell(near=(p.x, p.z), radius=12, min_radius=5)
                if c:
                    x, z = g.level.cell_center(*c)
                    cr.investigate(x, z)
                    g.audio.play("creature_roar", .25, .85)
            elif cr.state == HIDDEN:
                cr.hidden_timer = min(cr.hidden_timer, 2.0)
