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

import config as C
from generator import VENT, CORR, ROOM

WANDER, INVESTIGATE, CHASE, SEARCH, RETREAT, HIDDEN = "ERRANCE", "ENQUETE", "TRAQUE", "RECHERCHE", "RETRAITE", "CACHEE"


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
        self._build_model()
        self.growl = game.audio.loop("creature_growl", "creature_growl", 1.0)

    # ------------------------------------------------------------------
    def _build_model(self):
        dark = color.rgb(.045, .04, .05)
        dark2 = color.rgb(.07, .06, .07)
        bone = color.rgb(.16, .14, .13)
        self.root = Entity(name='creature')
        self.body = Entity(parent=self.root, y=1.35)
        # torse allongé penché vers l'avant
        self.torso = Entity(parent=self.body, model='sphere', color=dark, scale=(.62, 1.35, .5), rotation_x=28, y=.35)
        Entity(parent=self.torso, model='sphere', color=dark2, scale=(.8, .5, .9), y=-.35)
        for k in range(5):   # côtes / vertèbres saillantes
            Entity(parent=self.torso, model='cube', color=bone, scale=(.15, .06, .25), position=(0, .35 - k * .15, -.42))
        # cou et tête allongée
        self.neck = Entity(parent=self.body, position=(0, 1.0, .45))
        self.head = Entity(parent=self.neck, model='sphere', color=dark, scale=(.34, .3, .7), z=.25)
        Entity(parent=self.head, model='sphere', color=dark2, scale=(.8, .5, .6), position=(0, -.35, .3))   # mâchoire
        self.eyes = []
        for s in (-1, 1):
            e = Entity(parent=self.head, model='sphere', color=color.rgb(1, .75, .2), scale=(.18, .14, .1),
                       position=(s * .28, .15, .38), unlit=True)
            self.eyes.append(e)
        # bras très longs et fins
        self.arms = []
        for s in (-1, 1):
            sh = Entity(parent=self.body, position=(s * .38, .85, .3))
            Entity(parent=sh, model='cube', color=dark, scale=(.1, .9, .1), y=-.45)
            elbow = Entity(parent=sh, y=-.9)
            Entity(parent=elbow, model='cube', color=dark, scale=(.08, 1.0, .08), y=-.5)
            for c in (-1, 0, 1):
                Entity(parent=elbow, model='cube', color=bone, scale=(.025, .35, .025), position=(c * .04, -1.12, .05),
                       rotation_x=-20)
            self.arms.append((sh, elbow))
        # jambes digitigrades
        self.legs = []
        for s in (-1, 1):
            hip = Entity(parent=self.body, position=(s * .22, 0, 0))
            Entity(parent=hip, model='cube', color=dark, scale=(.14, .75, .14), y=-.37)
            knee = Entity(parent=hip, y=-.72)
            Entity(parent=knee, model='cube', color=dark, scale=(.1, .72, .1), y=-.34)
            self.legs.append((hip, knee))

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
        if door and door.target < 1:
            door.open(hold=4)
            self.game.audio.play_at("metal_bang", (door.pos[0], 1.5, door.pos[1]), .8, .7)
            self.stun = max(self.stun, .35)
        gr = L.grilles.get(k)
        if gr and not gr.opened:
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
        self.walk_phase += moved * 2.2
        ph = self.walk_phase
        c = self.crawl_k
        t = self.game.time
        self.body.y = 1.35 * (1 - c * .6) + abs(math.sin(ph)) * .06
        self.body.rotation_x = c * 55 + (8 if self.state == CHASE else 0)
        for s, (hip, knee) in zip((1, -1), self.legs):
            hip.rotation_x = math.sin(ph + (0 if s > 0 else math.pi)) * 35 - 10 - c * 40
            knee.rotation_x = 25 + max(0, math.sin(ph + (0 if s > 0 else math.pi) + 1.2)) * 40 + c * 40
        for s, (sh, elbow) in zip((1, -1), self.arms):
            sw = math.sin(ph + (math.pi if s > 0 else 0)) * 25
            sh.rotation_x = -15 + sw - c * 70 - (35 if self.state == CHASE else 0)
            sh.rotation_z = s * (8 + 4 * math.sin(t * 1.3))
            elbow.rotation_x = -20 - abs(sw) * .4
        # tête : tics nerveux
        twitch = math.sin(t * 17) * math.sin(t * 3.1)
        self.neck.rotation_x = -10 + twitch * 6 - c * 30
        self.neck.rotation_y = math.sin(t * .7) * 20 + (twitch * 25 if abs(twitch) > .8 else 0)
        glow = .75 + .25 * math.sin(t * 2)
        eye_col = color.rgb(1, .15, .05) if self.state == CHASE else color.rgb(glow, .6 * glow, .15 * glow)
        for e in self.eyes:
            e.color = eye_col

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
