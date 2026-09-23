"""
Petit FPS avec Ursina — ennemis humanoïdes dotés d'une IA tactique.

Lancement :  python fps.py

Commandes (clavier AZERTY) :
    Z Q S D / flèches  : se déplacer
    Maj                : courir
    Espace             : sauter
    Clic droit ou P    : tirer (maintenir pour le tir automatique)
    R                  : recharger
    Échap              : pause (X pour quitter pendant la pause)
    Entrée             : recommencer après la mort

IA des ennemis :
    - perception : champ de vision, ligne de vue (raycast), audition des tirs
    - mémoire de la dernière position connue du joueur, partage d'infos entre alliés
    - recherche de couverture (points cachés derrière les murs), sortie de
      couverture pour tirer puis retour à l'abri, rechargement à couvert
    - contournement (flanc) quand le joueur disparaît, repli quand ils sont blessés
    - déplacement par A* sur une grille de navigation
    - corps articulé (bassin, torse, tête, épaules, coudes, hanches, genoux)
      animé : marche, course, accroupi, visée, réaction aux impacts, chute
"""

import heapq
import math
import random

from ursina import (
    Ursina, Entity, Text, Sky, DirectionalLight, AmbientLight, Vec2, Vec3,
    camera, color, mouse, held_keys, time, window, application, raycast,
    destroy, invoke, clamp, lerp, scene,
)
from ursina.shaders import lit_with_shadows_shader


LIT = lit_with_shadows_shader
ARENA = 40          # l'arène va de -ARENA à +ARENA sur x et z
GRAVITY = 22
PLAYER_RADIUS = 0.5
ENEMY_RADIUS = 0.35
EYE_STAND = 1.6     # hauteur des yeux d'un ennemi debout
EYE_CROUCH = 1.0    # hauteur de la tête d'un ennemi accroupi


def flat(v):
    return Vec3(v.x, 0, v.z)


def flat_dist(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def yaw_to(a, b):
    """Angle (degrés) pour qu'une entité en a regarde vers b sur le plan horizontal."""
    return math.degrees(math.atan2(b.x - a.x, b.z - a.z))


def angle_diff(a, b):
    return (b - a + 180) % 360 - 180


def approach_angle(cur, target, max_step):
    d = angle_diff(cur, target)
    return cur + clamp(d, -max_step, max_step)


# ---------------------------------------------------------------------------
# Monde : murs, collisions, navigation, points de couverture
# ---------------------------------------------------------------------------

class Box:
    def __init__(self, cx, cz, sx, sz, h):
        self.x0, self.x1 = cx - sx / 2, cx + sx / 2
        self.z0, self.z1 = cz - sz / 2, cz + sz / 2
        self.h = h
        self.cx, self.cz = cx, cz

    def circle_overlap(self, x, z, r):
        px = clamp(x, self.x0, self.x1)
        pz = clamp(z, self.z0, self.z1)
        return (x - px) ** 2 + (z - pz) ** 2 < r * r


class World:
    CELL = 1.0

    def __init__(self):
        self.boxes = []
        self.level = Entity()   # parent de tous les éléments qui bloquent la vue / les balles
        self.build()
        self.build_nav()
        self.build_cover()

    # -- construction ------------------------------------------------------
    def add_wall(self, cx, cz, sx, sz, h, texture='brick', col=color.white, tex_scale=None):
        self.boxes.append(Box(cx, cz, sx, sz, h))
        if tex_scale is None:
            tex_scale = (max(sx, sz) / 2, h / 2)
        Entity(parent=self.level, model='cube', texture=texture, color=col,
               position=(cx, h / 2, cz), scale=(sx, h, sz), collider='box',
               texture_scale=tex_scale, shader=LIT)

    def add_crate(self, cx, cz, size=1.3):
        self.boxes.append(Box(cx, cz, size, size, size))
        Entity(parent=self.level, model='cube', texture='white_cube',
               color=color.rgb32(150, 105, 60), position=(cx, size / 2, cz),
               scale=size, collider='box', shader=LIT)

    def build(self):
        ground = Entity(parent=self.level, model='plane', texture='grass',
                        scale=(ARENA * 2 + 20, 1, ARENA * 2 + 20),
                        texture_scale=(40, 40), collider='box', shader=LIT)
        ground.is_ground = True

        stone = color.rgb32(200, 190, 180)
        # enceinte
        L = ARENA * 2
        self.add_wall(0, ARENA, L + 1, 1, 4, col=stone)
        self.add_wall(0, -ARENA, L + 1, 1, 4, col=stone)
        self.add_wall(ARENA, 0, 1, L + 1, 4, col=stone)
        self.add_wall(-ARENA, 0, 1, L + 1, 4, col=stone)

        # grands murs (on ne voit pas par-dessus)
        self.add_wall(-12, 8, 10, 1, 3)
        self.add_wall(12, 8, 10, 1, 3)
        self.add_wall(0, 18, 1, 10, 3)
        self.add_wall(-22, -5, 1, 12, 3)
        self.add_wall(22, -5, 1, 12, 3)
        self.add_wall(-8, -14, 8, 1, 3)
        self.add_wall(8, -14, 8, 1, 3)
        self.add_wall(-28, 22, 12, 1, 3)
        self.add_wall(28, 22, 12, 1, 3)
        self.add_wall(-30, -24, 1, 10, 3)
        self.add_wall(30, -24, 1, 10, 3)
        # bâtiment ouvert au centre-nord
        self.add_wall(-6, 28, 1, 8, 3)
        self.add_wall(6, 28, 1, 8, 3)
        self.add_wall(-3.5, 32, 6, 1, 3)
        self.add_wall(3.5, 32, 6, 1, 3)

        # murets bas (on peut tirer par-dessus debout, se cacher accroupi)
        low = color.rgb32(170, 170, 170)
        self.add_wall(0, 0, 6, 0.8, 1.3, col=low)
        self.add_wall(-16, 20, 5, 0.8, 1.3, col=low)
        self.add_wall(16, 20, 5, 0.8, 1.3, col=low)
        self.add_wall(-14, -26, 0.8, 5, 1.3, col=low)
        self.add_wall(14, -26, 0.8, 5, 1.3, col=low)
        self.add_wall(-32, 6, 5, 0.8, 1.3, col=low)
        self.add_wall(32, 6, 5, 0.8, 1.3, col=low)
        self.add_wall(0, -24, 6, 0.8, 1.3, col=low)

        # caisses
        for x, z in [(-4, 10), (4, 10.2), (-18, 0), (18, 0), (-26, 14), (26, 14),
                     (-10, -22), (10, -22), (-24, -32), (24, -32), (0, 36), (-34, -10),
                     (34, -10), (-12, 30), (12, 30)]:
            self.add_crate(x, z)

    # -- collisions --------------------------------------------------------
    def floor_height(self, x, z, r, y):
        """Hauteur du sol sous une entité (sol ou dessus d'une caisse / d'un muret)."""
        h = 0
        for b in self.boxes:
            if b.h <= y + 0.35 and b.circle_overlap(x, z, r * 0.8):
                h = max(h, b.h)
        return h

    def resolve(self, pos, r, y=0.0):
        """Repousse un cercle (x,z) hors des murs dont le haut est au-dessus de ses pieds."""
        x, z = pos.x, pos.z
        for b in self.boxes:
            if b.h <= y + 0.35:
                continue
            px = clamp(x, b.x0, b.x1)
            pz = clamp(z, b.z0, b.z1)
            dx, dz = x - px, z - pz
            d2 = dx * dx + dz * dz
            if d2 >= r * r:
                continue
            if d2 > 1e-8:
                d = math.sqrt(d2)
                x += dx / d * (r - d)
                z += dz / d * (r - d)
            else:  # centre à l'intérieur de la boîte : sortie par le côté le plus proche
                opts = [(x - b.x0 + r, -1, 0), (b.x1 - x + r, 1, 0),
                        (z - b.z0 + r, 0, -1), (b.z1 - z + r, 0, 1)]
                pen, sx, sz = min(opts)
                x += sx * pen
                z += sz * pen
        return Vec3(x, pos.y, z)

    def los(self, a, b):
        """Ligne de vue entre deux points (rien du décor entre les deux)."""
        d = b - a
        dist = d.length()
        if dist < 0.01:
            return True
        hit = raycast(a, d / dist, dist, traverse_target=self.level)
        return not hit.hit

    # -- navigation (A* sur grille) -----------------------------------------
    def build_nav(self):
        self.n = int(ARENA * 2 / self.CELL)
        self.blocked = [[False] * self.n for _ in range(self.n)]
        for i in range(self.n):
            for j in range(self.n):
                x, z = self.cell_center(i, j)
                if abs(x) > ARENA - 1 or abs(z) > ARENA - 1:
                    self.blocked[i][j] = True
                    continue
                for b in self.boxes:
                    if b.circle_overlap(x, z, 0.55):
                        self.blocked[i][j] = True
                        break
        self.free_cells = [(i, j) for i in range(self.n) for j in range(self.n) if not self.blocked[i][j]]

    def cell_center(self, i, j):
        return -ARENA + (i + 0.5) * self.CELL, -ARENA + (j + 0.5) * self.CELL

    def cell_of(self, p):
        i = int((p.x + ARENA) / self.CELL)
        j = int((p.z + ARENA) / self.CELL)
        return clamp(i, 0, self.n - 1), clamp(j, 0, self.n - 1)

    def is_free(self, p):
        i, j = self.cell_of(p)
        return not self.blocked[i][j]

    def nearest_free(self, c):
        if not self.blocked[c[0]][c[1]]:
            return c
        for rad in range(1, 6):
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    i, j = c[0] + di, c[1] + dj
                    if 0 <= i < self.n and 0 <= j < self.n and not self.blocked[i][j]:
                        return (i, j)
        return None

    def line_free(self, a, b):
        d = flat_dist(a, b)
        steps = max(1, int(d / 0.3))
        for k in range(steps + 1):
            t = k / steps
            p = Vec3(lerp(a.x, b.x, t), 0, lerp(a.z, b.z, t))
            if not self.is_free(p):
                return False
        return True

    def find_path(self, start, goal, max_nodes=5000):
        s = self.nearest_free(self.cell_of(start))
        g = self.nearest_free(self.cell_of(goal))
        if s is None or g is None:
            return []
        if s == g:
            return [flat(goal)]
        SQ2 = 1.4142
        openq = [(0, 0, s)]
        came = {s: None}
        cost = {s: 0}
        expanded = 0
        found = False
        while openq:
            _, c, cur = heapq.heappop(openq)
            if cur == g:
                found = True
                break
            if c > cost[cur]:
                continue
            expanded += 1
            if expanded > max_nodes:
                break
            ci, cj = cur
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ni, nj = ci + di, cj + dj
                if not (0 <= ni < self.n and 0 <= nj < self.n) or self.blocked[ni][nj]:
                    continue
                if di and dj and (self.blocked[ci + di][cj] or self.blocked[ci][cj + dj]):
                    continue  # pas de coupe de coin
                nc = c + (SQ2 if di and dj else 1)
                if nc < cost.get((ni, nj), 1e9):
                    cost[(ni, nj)] = nc
                    came[(ni, nj)] = cur
                    dx, dz = abs(ni - g[0]), abs(nj - g[1])
                    h = (dx + dz) + (SQ2 - 2) * min(dx, dz)
                    heapq.heappush(openq, (nc + h, nc, (ni, nj)))
        if not found:
            return []
        cells = []
        cur = g
        while cur is not None:
            cells.append(cur)
            cur = came[cur]
        cells.reverse()
        pts = []
        for i, j in cells:
            x, z = self.cell_center(i, j)
            pts.append(Vec3(x, 0, z))
        if self.is_free(goal):
            pts[-1] = flat(goal)
        # lissage : on saute les points intermédiaires quand la ligne droite est libre
        smooth = []
        idx = 0
        cur_p = flat(start)
        while idx < len(pts):
            far = idx
            for k in range(len(pts) - 1, idx, -1):
                if self.line_free(cur_p, pts[k]):
                    far = k
                    break
            smooth.append(pts[far])
            cur_p = pts[far]
            idx = far + 1
        return smooth

    def random_free_point(self, near=None, radius=15):
        for _ in range(40):
            i, j = random.choice(self.free_cells)
            x, z = self.cell_center(i, j)
            p = Vec3(x, 0, z)
            if near is None or flat_dist(p, near) < radius:
                return p
        return near if near is not None else Vec3(0, 0, 0)

    # -- couvertures -------------------------------------------------------
    def build_cover(self):
        """Points au pied de chaque mur / caisse, avec leur normale et la direction du mur."""
        self.covers = []
        off = 0.85
        for b in self.boxes:
            if b.h < 1.2:
                continue
            sx, sz = b.x1 - b.x0, b.z1 - b.z0
            if sx > 70 or sz > 70:     # murs d'enceinte : on garde quand même quelques points
                step = 6
            else:
                step = 1.5
            sides = [
                ((b.x0, b.z0 - off), (b.x1, b.z0 - off), Vec3(0, 0, -1)),
                ((b.x0, b.z1 + off), (b.x1, b.z1 + off), Vec3(0, 0, 1)),
                ((b.x0 - off, b.z0), (b.x0 - off, b.z1), Vec3(-1, 0, 0)),
                ((b.x1 + off, b.z0), (b.x1 + off, b.z1), Vec3(1, 0, 0)),
            ]
            for (ax, az), (bx, bz), normal in sides:
                length = math.hypot(bx - ax, bz - az)
                n = max(1, int(length / step))
                for k in range(n + 1):
                    t = k / n
                    p = Vec3(lerp(ax, bx, t), 0, lerp(az, bz, t))
                    if abs(p.x) > ARENA - 1.2 or abs(p.z) > ARENA - 1.2:
                        continue
                    if self.is_free(p):
                        self.covers.append(CoverPoint(p, normal, b.h))


class CoverPoint:
    def __init__(self, pos, normal, height):
        self.pos = pos
        self.normal = normal
        self.tangent = Vec3(normal.z, 0, -normal.x)
        self.height = height
        self.owner = None


# ---------------------------------------------------------------------------
# Effets visuels
# ---------------------------------------------------------------------------

def tracer(start, end, col=color.yellow, thickness=0.025, life=0.06):
    d = end - start
    length = d.length()
    if length < 0.05:
        return
    e = Entity(model='cube', color=col, position=(start + end) / 2,
               scale=(thickness, thickness, length), unlit=True)
    e.look_at(end)
    destroy(e, life)


def muzzle_flash(parent, pos=(0, 0, 0), scale=0.25):
    f = Entity(parent=parent, model='quad', texture='circle', color=color.rgb32(255, 220, 120),
               position=pos, scale=scale, billboard=True, unlit=True)
    destroy(f, 0.05)


_impacts = []


def impact(point, normal=None, col=color.rgb32(60, 50, 40)):
    e = Entity(model='quad', texture='circle', color=col,
               position=point + (normal * 0.01 if normal is not None else Vec3(0, 0, 0)),
               scale=0.12, unlit=True)
    if normal is not None:
        e.look_at(point - normal)
    else:
        e.billboard = True
    _impacts.append(e)
    if len(_impacts) > 60:
        destroy(_impacts.pop(0))
    # petites particules
    for _ in range(4):
        p = Entity(model='cube', color=color.rgb32(140, 120, 90), position=point, scale=0.04, unlit=True)
        target = point + Vec3(random.uniform(-.3, .3), random.uniform(0, .4), random.uniform(-.3, .3))
        p.animate_position(target, duration=0.25)
        destroy(p, 0.25)


def blood(point):
    for _ in range(6):
        p = Entity(model='cube', color=color.rgb32(150, 0, 0), position=point, scale=0.05, unlit=True)
        target = point + Vec3(random.uniform(-.4, .4), random.uniform(-.3, .4), random.uniform(-.4, .4))
        p.animate_position(target, duration=0.3)
        destroy(p, 0.3)


# ---------------------------------------------------------------------------
# Cibles d'entraînement
# ---------------------------------------------------------------------------

class Target(Entity):
    def __init__(self, game, position, yaw=0):
        super().__init__(position=position, rotation_y=yaw)
        self.game = game
        Entity(parent=self, model='cube', color=color.rgb32(90, 60, 30), scale=(0.12, 1.2, 0.12),
               y=0.6, shader=LIT)
        self.board = Entity(parent=self, y=1.2)
        rings = [(0.9, color.white), (0.7, color.red), (0.5, color.white), (0.3, color.red), (0.12, color.white)]
        for k, (s, c) in enumerate(rings):
            Entity(parent=self.board, model='circle', color=c, scale=s, y=0.5, z=-0.02 - k * 0.004,
                   shader=LIT, double_sided=True)
        self.hitbox = Entity(parent=self.board, model='cube', scale=(0.9, 0.9, 0.05), y=0.5,
                             collider='box', visible=False)
        self.hitbox.target = self
        self.is_down = False

    def hit(self):
        if self.is_down:
            return
        self.is_down = True
        self.game.add_score(10, 'Cible +10')
        self.board.animate_rotation_x(-90, duration=0.2)
        invoke(self.reset, delay=3)

    def reset(self):
        self.board.animate_rotation_x(0, duration=0.3)
        self.is_down = False


# ---------------------------------------------------------------------------
# Ennemi humanoïde
# ---------------------------------------------------------------------------

class Enemy(Entity):
    SKIN = color.rgb32(224, 172, 130)
    UNIFORM = color.rgb32(85, 95, 60)
    UNIFORM_DARK = color.rgb32(60, 68, 42)
    BOOT = color.rgb32(40, 32, 25)
    HELMET = color.rgb32(70, 80, 50)
    GUN = color.rgb32(35, 35, 38)

    def __init__(self, game, position):
        super().__init__(position=position)
        self.game = game
        self.world = game.world
        self.hp = 100
        self.dead = False
        self.parts = []

        # IA
        self.state = 'patrol'        # patrol / investigate / combat
        self.sub = ''                # sous-état de combat
        self.timer = 0
        self.think_t = random.uniform(0, 0.2)
        self.path = []
        self.move_speed = 2.0
        self.sees = False
        self.suspicion = 0.0
        self.last_known = None
        self.last_seen = -99
        self.cover = None
        self.peek_pos = None
        self.mag = 8
        self.burst = 0
        self.shot_t = 0
        self.look_yaw = None         # angle que l'ennemi veut regarder (sinon direction du mouvement)
        self.retreated = False
        self.flinch = 0.0
        self.hit_recently = 0
        self.alerted_by = None

        # animation
        self.vel = Vec3(0, 0, 0)
        self.phase = random.uniform(0, 6.28)
        self.crouch = 0.0
        self.want_crouch = 0.0
        self.aim = 0.0
        self.want_aim = 0.0
        self.aim_pitch = 0.0
        self.death_t = 0

        self.build_body()
        self.icon = Text(parent=self, text='', y=2.25, scale=18, billboard=True,
                         origin=(0, 0), color=color.yellow)

    # -- corps articulé ----------------------------------------------------
    def part(self, parent, pos, scale, col, zone, model='cube'):
        p = Entity(parent=parent, model=model, color=col, position=pos, scale=scale,
                   collider='box', shader=LIT)
        p.owner = self
        p.zone = zone
        self.parts.append(p)
        return p

    def build_body(self):
        U, UD, S = self.UNIFORM, self.UNIFORM_DARK, self.SKIN
        # bassin : pivot principal (hauteur des hanches)
        self.hips = Entity(parent=self, y=0.95)
        self.part(self.hips, (0, 0.02, 0), (0.36, 0.2, 0.22), UD, 'body')
        # torse : pivote au bassin
        self.torso = Entity(parent=self.hips, y=0.08)
        self.part(self.torso, (0, 0.28, 0), (0.42, 0.5, 0.25), U, 'body')
        self.part(self.torso, (0, 0.3, 0.13), (0.34, 0.34, 0.06), UD, 'body')   # gilet
        self.part(self.torso, (0, 0.58, 0), (0.1, 0.08, 0.1), S, 'body')        # cou
        # tête
        self.neck = Entity(parent=self.torso, y=0.6)
        self.head = self.part(self.neck, (0, 0.14, 0), (0.22, 0.26, 0.24), S, 'head')
        self.part(self.neck, (0, 0.25, -0.01), (0.26, 0.1, 0.28), self.HELMET, 'head')   # casque
        self.part(self.neck, (-0.055, 0.17, 0.12), (0.04, 0.03, 0.01), color.black, 'head')  # yeux
        self.part(self.neck, (0.055, 0.17, 0.12), (0.04, 0.03, 0.01), color.black, 'head')

        # bras : épaule -> bras -> coude -> avant-bras -> main
        self.shoulders, self.elbows = [], []
        for side in (-1, 1):
            sh = Entity(parent=self.torso, position=(0.27 * side, 0.48, 0))
            self.part(sh, (0, -0.15, 0), (0.12, 0.32, 0.12), U, 'limb')
            el = Entity(parent=sh, y=-0.3)
            self.part(el, (0, -0.14, 0), (0.1, 0.28, 0.1), U, 'limb')
            self.part(el, (0, -0.31, 0), (0.09, 0.09, 0.09), S, 'limb')          # main
            self.shoulders.append(sh)
            self.elbows.append(el)
        # fusil tenu dans la main droite (orienté comme l'avant-bras)
        self.gun = Entity(parent=self.elbows[1], y=-0.31, rotation_x=90)
        g = self.part(self.gun, (0, 0.02, 0.2), (0.06, 0.1, 0.62), self.GUN, 'limb')
        g.zone = 'gun'
        self.part(self.gun, (0, -0.06, 0.1), (0.05, 0.14, 0.06), self.GUN, 'gun')
        self.muzzle = Entity(parent=self.gun, z=0.55, y=0.02)

        # jambes : hanche -> cuisse -> genou -> tibia -> pied
        self.hip_joints, self.knees = [], []
        for side in (-1, 1):
            hj = Entity(parent=self.hips, position=(0.1 * side, -0.05, 0))
            self.part(hj, (0, -0.22, 0), (0.15, 0.45, 0.16), UD, 'limb')
            kn = Entity(parent=hj, y=-0.44)
            self.part(kn, (0, -0.2, 0), (0.13, 0.42, 0.14), UD, 'limb')
            self.part(kn, (0, -0.43, 0.06), (0.14, 0.08, 0.26), self.BOOT, 'limb')
            self.hip_joints.append(hj)
            self.knees.append(kn)

    # -- utilitaires -------------------------------------------------------
    @property
    def eye(self):
        return self.position + Vec3(0, lerp(EYE_STAND, EYE_CROUCH, self.crouch), 0)

    def player_eye(self):
        return self.game.player.eye

    def set_path_to(self, target):
        self.path = self.world.find_path(self.position, target)

    def arrived(self):
        return not self.path

    def allies(self, radius):
        return [e for e in self.game.enemies if e is not self and not e.dead
                and flat_dist(e.position, self.position) < radius]

    # -- perception --------------------------------------------------------
    def perceive(self):
        pl = self.game.player
        if pl.dead:
            self.sees = False
            return
        to_p = pl.position - self.position
        dist = flat_dist(pl.position, self.position)
        facing = self.forward
        cosang = (to_p.x * facing.x + to_p.z * facing.z) / max(dist, 0.01)
        in_combat = self.state == 'combat'
        fov_ok = cosang > (math.cos(math.radians(70)) if not in_combat else -1)
        max_range = 45 if in_combat else 32
        self.sees = False
        if dist < max_range and (fov_ok or dist < 3):
            if self.world.los(self.eye, pl.eye):
                self.sees = True
        if self.sees:
            self.last_known = Vec3(pl.position)
            self.last_seen = self.game.t

    def hear_shot(self, pos):
        """Le joueur a tiré : on connaît approximativement sa position."""
        if self.dead or self.game.player.dead:
            return
        noisy = pos + Vec3(random.uniform(-3, 3), 0, random.uniform(-3, 3))
        self.last_known = noisy
        if self.state != 'combat':
            self.enter_combat(heard=True)

    def receive_alert(self, pos):
        if self.dead:
            return
        self.last_known = Vec3(pos)
        if self.state != 'combat':
            self.enter_combat(heard=True)

    def enter_combat(self, heard=False):
        self.state = 'combat'
        self.icon.text = '!'
        self.icon.color = color.red
        invoke(self.clear_icon, '!', delay=1.5)
        if not heard:
            self.last_seen = self.game.t
        # prévenir les alliés proches
        if self.last_known is not None:
            for a in self.allies(25):
                if a.state != 'combat':
                    invoke(a.receive_alert, self.last_known, delay=random.uniform(0.3, 0.9))
        self.go_to_cover()

    def clear_icon(self, which):
        if not self.dead and self.icon.text == which:
            self.icon.text = ''

    # -- choix tactiques ---------------------------------------------------
    def threat_eye(self):
        base = self.last_known if self.last_known is not None else self.game.player.position
        return base + Vec3(0, 1.6, 0)

    def cover_is_safe(self, cp, threat):
        head = cp.pos + Vec3(0, EYE_CROUCH, 0)
        return not self.world.los(head, threat)

    def choose_cover(self, far=False):
        threat = self.threat_eye()
        tpos = flat(threat)
        best, best_score = None, -1e9
        candidates = [c for c in self.world.covers
                      if (c.owner is None or c.owner is self)
                      and flat_dist(c.pos, self.position) < (30 if far else 20)]
        candidates.sort(key=lambda c: flat_dist(c.pos, self.position))
        others = [e.position for e in self.game.enemies if e is not self and not e.dead]
        for c in candidates[:45]:
            d_threat = flat_dist(c.pos, tpos)
            if d_threat < 5:
                continue
            # le mur doit être entre la couverture et la menace
            to_t = (tpos - c.pos)
            if (to_t.x * c.normal.x + to_t.z * c.normal.z) > 0:
                continue
            if not self.cover_is_safe(c, threat):
                continue
            score = -flat_dist(c.pos, self.position) * 1.0
            if far:
                score += d_threat * 1.5
            else:
                score -= abs(d_threat - 14) * 0.6
            for o in others:  # on s'écarte des alliés pour ne pas s'agglutiner
                if flat_dist(o, c.pos) < 4:
                    score -= 8
            # ne pas traverser la ligne de tir : pénalité si le chemin passe près du joueur
            mid = (c.pos + self.position) / 2
            if flat_dist(mid, tpos) < 6:
                score -= 15
            score += random.uniform(0, 2)
            if score > best_score:
                best, best_score = c, score
        return best

    def release_cover(self):
        if self.cover and self.cover.owner is self:
            self.cover.owner = None
        self.cover = None

    def go_to_cover(self, far=False):
        c = self.choose_cover(far)
        if c is None:
            self.release_cover()
            self.sub = 'skirmish'
            self.timer = random.uniform(1.0, 2.0)
            self.path = []
            return False
        self.release_cover()
        self.cover = c
        c.owner = self
        self.set_path_to(c.pos)
        self.sub = 'move_cover'
        self.timer = 8
        return True

    def find_peek_spot(self):
        """Position proche de la couverture d'où l'on voit la menace en étant debout."""
        threat = self.threat_eye()
        base = self.cover.pos
        cands = [Vec3(0, 0, 0)]
        for d in (1.0, 1.6, 2.3, 3.0):
            cands += [self.cover.tangent * d, self.cover.tangent * -d]
        cands.sort(key=lambda v: v.length())
        for off in cands:
            p = base + off
            if not self.world.is_free(p):
                continue
            if self.world.los(p + Vec3(0, EYE_STAND, 0), threat):
                return p
        return None

    def find_flank_spot(self):
        """Point à distance moyenne du joueur, avec vue sur lui, sous un angle différent des alliés."""
        target = self.last_known
        if target is None:
            return None
        ally_angles = [yaw_to(target, a.position) for a in self.allies(60)]
        best, best_score = None, -1e9
        for _ in range(25):
            ang = random.uniform(0, 360)
            dist = random.uniform(8, 16)
            p = target + Vec3(math.sin(math.radians(ang)) * dist, 0, math.cos(math.radians(ang)) * dist)
            if not self.world.is_free(p):
                continue
            if not self.world.los(p + Vec3(0, EYE_STAND, 0), target + Vec3(0, 1.6, 0)):
                continue
            score = -flat_dist(p, self.position) * 0.4
            for aa in ally_angles:
                score += min(abs(angle_diff(ang, aa)), 90) * 0.1
            if score > best_score:
                best, best_score = p, score
        return best

    # -- cerveau -----------------------------------------------------------
    def think(self):
        self.perceive()
        g = self.game
        if self.state == 'patrol':
            self.move_speed = 1.8
            self.want_aim = 0
            self.want_crouch = 0
            self.look_yaw = None
            if self.sees:
                d = flat_dist(self.position, g.player.position)
                self.suspicion += (0.25 if d > 15 else 0.6) * (1.6 if g.player.sprinting else 1)
                self.icon.text = '?'
                self.icon.color = color.yellow
                self.path = []
                self.look_yaw = yaw_to(self.position, g.player.position)
                if self.suspicion >= 1:
                    self.enter_combat()
            else:
                self.suspicion = max(0, self.suspicion - 0.05)
                if self.suspicion == 0 and self.icon.text == '?':
                    self.icon.text = ''
                if self.arrived():
                    self.timer -= 0.2
                    if self.timer <= 0:
                        self.set_path_to(self.world.random_free_point(self.position, 18))
                        self.timer = random.uniform(1, 4)
        elif self.state == 'investigate':
            self.move_speed = 2.6
            self.want_aim = 0.5
            self.want_crouch = 0
            if self.sees:
                self.enter_combat()
                return
            if self.arrived():
                self.timer -= 0.2
                self.look_yaw = (self.look_yaw or self.rotation_y) + random.choice((-60, 60))
                if self.timer <= 0:
                    self.state = 'patrol'
                    self.icon.text = ''
                    self.timer = 1
        elif self.state == 'combat':
            self.combat_think()

    def combat_think(self):
        g = self.game
        lost = g.t - self.last_seen
        if g.player.dead:
            self.state = 'patrol'
            self.sub = ''
            self.burst = 0
            self.release_cover()
            return
        if self.last_known is not None and self.sub not in ('flank', 'move_cover', 'retreat'):
            self.look_yaw = yaw_to(self.position, self.last_known)

        # blessé : on se replie loin
        if self.hp < 40 and not self.retreated:
            self.retreated = True
            if self.go_to_cover(far=True):
                self.sub = 'retreat'
                self.move_speed = 5.2
                return

        # joueur perdu depuis longtemps : on part le chercher
        if lost > 12 and self.sub not in ('flank',):
            self.state = 'investigate'
            self.sub = ''
            self.burst = 0
            self.release_cover()
            self.icon.text = '?'
            self.icon.color = color.orange
            if self.last_known is not None:
                self.set_path_to(self.last_known)
            self.timer = 4
            return

        sub = self.sub
        if sub in ('move_cover', 'retreat'):
            self.move_speed = 5.0
            self.want_crouch = 0.25
            self.want_aim = 0.3
            self.look_yaw = None
            # la couverture visée est-elle toujours sûre ?
            if self.cover and not self.cover_is_safe(self.cover, self.threat_eye()) and random.random() < 0.3:
                self.go_to_cover(far=(sub == 'retreat'))
                return
            if self.arrived() or self.timer <= 0:
                self.sub = 'hide'
                self.timer = random.uniform(0.8, 2.0) + (2 if sub == 'retreat' else 0)
        elif sub == 'hide':
            self.want_crouch = 1
            self.want_aim = 0
            self.move_speed = 2
            if self.cover and not self.cover_is_safe(self.cover, self.threat_eye()):
                # repéré : le joueur nous voit derrière ce mur
                if self.sees and self.mag > 0 and random.random() < 0.5:
                    self.start_aim()
                else:
                    self.go_to_cover()
                return
            if self.mag <= 0:
                self.sub = 'reload'
                self.timer = 2.2
                return
            if self.timer <= 0:
                if lost > 4:
                    spot = self.find_flank_spot()
                    if spot is not None and random.random() < 0.6:
                        self.release_cover()
                        self.set_path_to(spot)
                        self.sub = 'flank'
                        self.timer = 10
                        return
                spot = self.find_peek_spot() if self.cover else None
                if spot is not None:
                    self.peek_pos = spot
                    self.set_path_to(spot)
                    self.sub = 'peek_move'
                    self.timer = 3
                else:
                    self.timer = random.uniform(0.8, 1.5)
                    if random.random() < 0.35:
                        self.go_to_cover()
        elif sub == 'reload':
            self.want_crouch = 1
            self.want_aim = 0
            if self.timer <= 0:
                self.mag = 8
                self.sub = 'hide'
                self.timer = random.uniform(0.3, 1.0)
        elif sub == 'peek_move':
            self.want_crouch = 0
            self.want_aim = 0.6
            self.move_speed = 2.8
            if self.sees and self.mag > 0:
                self.path = []
                self.start_aim()
            elif self.arrived() or self.timer <= 0:
                self.start_aim()
        elif sub == 'aim':
            self.want_crouch = 0
            self.want_aim = 1
            if self.timer <= 0:
                if self.sees and self.mag > 0:
                    self.sub = 'shoot'
                    self.burst = min(self.mag, random.randint(3, 5))
                    self.shot_t = 0
                else:
                    self.back_to_cover()
        elif sub == 'shoot':
            self.want_aim = 1
            if self.burst <= 0:
                if self.sees and self.mag > 0 and random.random() < 0.3:
                    self.start_aim(short=True)
                else:
                    self.back_to_cover()
        elif sub == 'flank':
            self.want_crouch = 0.2
            self.want_aim = 0.6
            self.move_speed = 4.2
            self.look_yaw = None
            if self.sees:
                self.path = []
                self.start_aim()
            elif self.arrived() or self.timer <= 0:
                self.go_to_cover()
        elif sub == 'skirmish':
            # pas de couverture disponible : on se déplace latéralement en tirant
            self.want_aim = 1
            self.move_speed = 2.5
            self.want_crouch = 0.4 if random.random() < 0.3 else 0
            if self.sees and self.burst <= 0 and self.mag > 0 and random.random() < 0.5:
                self.burst = min(self.mag, random.randint(2, 4))
                self.shot_t = 0.3
            if self.mag <= 0:
                self.mag = 8     # recharge debout, en se déplaçant
                self.timer = 0
            if self.timer <= 0:
                side = self.right * random.choice((-1, 1)) * random.uniform(2, 4)
                p = self.position + side
                if self.world.is_free(p):
                    self.set_path_to(p)
                self.timer = random.uniform(1.0, 2.0)
                if random.random() < 0.4:
                    self.go_to_cover()
        else:
            self.go_to_cover()

    def start_aim(self, short=False):
        self.sub = 'aim'
        self.timer = random.uniform(0.15, 0.3) if short else random.uniform(0.35, 0.7)

    def back_to_cover(self):
        if self.cover:
            self.set_path_to(self.cover.pos)
            self.sub = 'move_cover'
            self.timer = 4
        else:
            self.go_to_cover()

    # -- tir ---------------------------------------------------------------
    def fire(self):
        pl = self.game.player
        self.mag -= 1
        muzzle = self.muzzle.world_position
        muzzle_flash(self.muzzle, scale=0.3)
        target = pl.eye - Vec3(0, 0.35, 0)
        dist = flat_dist(self.position, pl.position)
        chance = clamp(0.8 - dist / 45, 0.15, 0.75)
        if pl.speed_now > 5:
            chance *= 0.55
        elif pl.speed_now > 1:
            chance *= 0.8
        if self.sub == 'skirmish':
            chance *= 0.7
        if not self.world.los(muzzle, pl.eye) and not self.world.los(self.eye, pl.eye):
            chance = 0
        if random.random() < chance:
            tracer(muzzle, target, color.rgb32(255, 200, 80))
            pl.take_damage(random.randint(6, 10), self.position)
        else:
            miss = target + Vec3(random.uniform(-1.2, 1.2), random.uniform(-0.6, 1.0), random.uniform(-1.2, 1.2))
            d = (miss - muzzle).normalized()
            hit = raycast(muzzle, d, 80, traverse_target=self.world.level)
            end = hit.world_point if hit.hit else muzzle + d * 60
            tracer(muzzle, end, color.rgb32(255, 200, 80))
            if hit.hit:
                impact(hit.world_point, hit.world_normal)
            self.game.flyby(end)

    # -- dégâts ------------------------------------------------------------
    def take_hit(self, dmg, zone, point):
        if self.dead:
            return
        self.hp -= dmg
        blood(point)
        self.flinch = 1.0
        self.hit_recently = 1.0
        self.last_known = Vec3(self.game.player.position)
        self.last_seen = self.game.t
        if self.hp <= 0:
            self.die(zone)
            return
        if self.state != 'combat':
            self.enter_combat()
        elif self.sub in ('aim', 'shoot', 'peek_move', 'skirmish') and random.random() < 0.7:
            self.burst = 0
            self.back_to_cover() if (self.cover and self.cover_is_safe(self.cover, self.threat_eye())) \
                else self.go_to_cover()
        elif self.sub == 'hide':
            self.go_to_cover()

    def die(self, zone):
        self.dead = True
        self.release_cover()
        self.icon.text = ''
        self.path = []
        for p in self.parts:
            p.collider = None
        self.fall_dir = random.choice((-1, 1))
        self.fall_side = random.uniform(-25, 25)
        self.game.on_enemy_killed(self, zone == 'head')
        for a in self.allies(20):
            a.receive_alert(self.game.player.position)
            if a.state == 'combat' and a.sub in ('hide',):
                a.timer += 1.0  # les alliés restent prudents un instant
        destroy(self, 8)

    # -- mise à jour -------------------------------------------------------
    def update(self):
        if self.game.paused:
            return
        dt = time.dt
        if self.dead:
            self.animate_death(dt)
            return

        self.timer -= dt
        self.think_t -= dt
        if self.think_t <= 0:
            self.think_t = 0.2
            self.think()

        # tir en rafale
        if self.burst > 0 and self.sub in ('shoot', 'skirmish'):
            self.shot_t -= dt
            if self.shot_t <= 0:
                if self.sees and self.mag > 0:
                    self.fire()
                    self.burst -= 1
                    self.shot_t = random.uniform(0.12, 0.2)
                else:
                    self.burst = 0

        self.move(dt)
        self.animate(dt)

    def move(self, dt):
        desired = Vec3(0, 0, 0)
        speed = self.move_speed * (1 - 0.45 * self.crouch)
        if self.path:
            target = self.path[0]
            to = flat(target - self.position)
            d = to.length()
            if d < 0.35:
                self.path.pop(0)
            else:
                desired = to / d * speed
                if len(self.path) == 1 and d < 1.0:
                    desired *= max(0.3, d)
        # séparation entre ennemis
        for e in self.game.enemies:
            if e is self or e.dead:
                continue
            d = flat_dist(e.position, self.position)
            if 0.01 < d < 0.9:
                push = flat(self.position - e.position) / d
                desired += push * (0.9 - d) * 4
        self.vel = lerp(self.vel, desired, min(1, dt * 8))
        new = self.position + self.vel * dt
        new = self.world.resolve(new, ENEMY_RADIUS)
        new.y = 0
        real = (new - self.position) / max(dt, 1e-4)
        self.position = new
        self.real_speed = flat(real).length()

        # orientation
        if self.look_yaw is not None and self.state == 'combat' and self.sub in ('aim', 'shoot', 'hide', 'reload', 'peek_move', 'skirmish'):
            target_yaw = yaw_to(self.position, self.last_known) if self.last_known is not None else self.look_yaw
        elif self.look_yaw is not None and (self.real_speed < 0.3 or self.state == 'patrol'):
            target_yaw = self.look_yaw
        elif self.real_speed > 0.3:
            target_yaw = math.degrees(math.atan2(self.vel.x, self.vel.z))
        else:
            target_yaw = self.rotation_y
        self.rotation_y = approach_angle(self.rotation_y, target_yaw, 400 * dt)

    def animate(self, dt):
        self.crouch = lerp(self.crouch, self.want_crouch, min(1, dt * 6))
        self.aim = lerp(self.aim, self.want_aim, min(1, dt * 8))
        self.flinch = max(0, self.flinch - dt * 4)
        c, a = self.crouch, self.aim

        # inclinaison de visée vers le joueur
        pitch = 0
        if a > 0.5 and self.last_known is not None:
            pe = self.game.player.eye - Vec3(0, 0.3, 0)
            src = self.position + Vec3(0, lerp(1.45, 0.95, c), 0)
            horiz = max(flat_dist(pe, src), 0.1)
            pitch = -math.degrees(math.atan2(pe.y - src.y, horiz))
        self.aim_pitch = lerp(self.aim_pitch, pitch, min(1, dt * 8))

        # cycle de marche
        speed = self.real_speed
        running = clamp((speed - 2.5) / 2.5, 0, 1)
        self.phase += dt * speed * (2.2 - 0.5 * running)
        amp = clamp(speed / 2.0, 0, 1)
        stride = (28 + 20 * running) * amp
        s = math.sin(self.phase)
        bob = abs(math.cos(self.phase)) * 0.05 * amp

        self.hips.y = lerp(0.95, 0.56, c) + bob - 0.03 * running
        # jambes (rotation_x négative = jambe vers l'avant)
        base_hip = lerp(0, -72, c)
        base_knee = lerp(0, 112, c)
        for k, side in enumerate((1, -1)):
            ss = s * side
            self.hip_joints[k].rotation_x = base_hip - ss * stride
            lift = max(0, math.sin(self.phase * 1 + (0 if side > 0 else math.pi) + 1.2))
            self.knees[k].rotation_x = base_knee + lift * (25 + 45 * running) * amp
            self.hip_joints[k].rotation_z = side * lerp(2, 8, c)

        # torse : penché en courant / accroupi, rotation de visée, recul à l'impact
        lean = lerp(3, 28, c) + 12 * running
        self.torso.rotation_x = lerp(lean, self.aim_pitch + lerp(0, 10, c), a) - self.flinch * 20
        self.torso.rotation_y = s * 6 * amp * (1 - a) + a * -8
        self.torso.rotation_z = self.flinch * 8 * random.uniform(-1, 1)
        self.neck.rotation_x = -lean * 0.5 * (1 - a) + lerp(0, 5, a)
        self.neck.rotation_y = a * 8

        # bras : position « prêt » (arme basse) mélangée à la position de visée
        swing = s * 10 * amp * (1 - a)
        # bras droit (index 1) tient la crosse
        self.shoulders[1].rotation_x = lerp(-25 + swing, -80, a)
        self.shoulders[1].rotation_y = lerp(0, 10, a)
        self.shoulders[1].rotation_z = lerp(-10, -5, a)
        self.elbows[1].rotation_x = lerp(-65, -10, a)
        # bras gauche (index 0) soutient le canon
        self.shoulders[0].rotation_x = lerp(-45 - swing, -75, a)
        self.shoulders[0].rotation_y = lerp(35, 40, a)
        self.shoulders[0].rotation_z = lerp(10, 5, a)
        self.elbows[0].rotation_x = lerp(-70, -40, a)
        # l'arme reste parallèle au sol / pointée vers la cible
        self.gun.rotation_x = lerp(150, 100, a)

    def animate_death(self, dt):
        self.death_t += dt
        t = clamp(self.death_t / 0.7, 0, 1)
        e = t * t
        self.rotation_x = lerp(0, 86 * self.fall_dir, e)
        self.rotation_z = lerp(0, self.fall_side, e)
        for k in range(2):
            self.knees[k].rotation_x = lerp(self.knees[k].rotation_x, 20 + 25 * k, dt * 5)
            self.hip_joints[k].rotation_x = lerp(self.hip_joints[k].rotation_x, -10 * k, dt * 5)
            self.shoulders[k].rotation_x = lerp(self.shoulders[k].rotation_x, -150 * self.fall_dir + 60, dt * 3)
            self.elbows[k].rotation_x = lerp(self.elbows[k].rotation_x, -20, dt * 3)
        self.hips.y = lerp(self.hips.y, 0.95 - 0.3 * (1 - t), dt * 4)
        self.torso.rotation_x = lerp(self.torso.rotation_x, 0, dt * 4)
        if self.death_t > 6:
            self.scale = lerp(self.scale, Vec3(0.01, 0.01, 0.01), dt * 3)

    def on_destroy(self):
        self.release_cover()


# ---------------------------------------------------------------------------
# Joueur
# ---------------------------------------------------------------------------

class Player(Entity):
    def __init__(self, game):
        super().__init__(position=(0, 0, -34))
        self.game = game
        self.world = game.world
        self.pivot = Entity(parent=self, y=1.65)
        camera.parent = self.pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = 90
        camera.clip_plane_near = 0.03
        self.sensitivity = Vec2(40, 40)
        self.vel = Vec3(0, 0, 0)
        self.vy = 0
        self.grounded = True
        self.hp = 100
        self.dead = False
        self.mag = 30
        self.reload_t = 0
        self.cooldown = 0
        self.last_hurt = -99
        self.speed_now = 0
        self.sprinting = False
        self.recoil = 0
        self.recoil_pitch = 0   # recul de visée, récupéré progressivement
        self.build_gun()

    @property
    def eye(self):
        return self.position + Vec3(0, 1.65, 0)

    def build_gun(self):
        self.gun = Entity(parent=camera, position=(0.15, -0.14, 0.2), scale=0.42)
        dark = color.rgb32(40, 40, 45)
        Entity(parent=self.gun, model='cube', color=dark, scale=(0.08, 0.1, 0.6))
        Entity(parent=self.gun, model='cube', color=color.rgb32(110, 75, 45), scale=(0.07, 0.14, 0.2), position=(0, -0.08, -0.25))
        Entity(parent=self.gun, model='cube', color=dark, scale=(0.06, 0.15, 0.06), position=(0, -0.1, 0.02))
        Entity(parent=self.gun, model='cube', color=dark, scale=(0.03, 0.03, 0.3), position=(0, 0.02, 0.4))
        Entity(parent=self.gun, model='cube', color=color.rgb32(20, 20, 20), scale=(0.03, 0.05, 0.08), position=(0, 0.08, -0.05))
        self.muzzle = Entity(parent=self.gun, z=0.58, y=0.02)
        self.gun_base = Vec3(self.gun.position)

    def take_damage(self, dmg, from_pos):
        if self.dead or self.game.paused:
            return
        self.hp -= dmg
        self.last_hurt = self.game.t
        self.game.hud.flash_damage(from_pos)
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            self.game.game_over()

    def update(self):
        if self.game.paused or self.dead:
            return
        dt = time.dt
        # regard à la souris
        if mouse.locked:
            self.rotation_y += mouse.velocity[0] * self.sensitivity[1]
            self.pivot.rotation_x -= mouse.velocity[1] * self.sensitivity[0]
            self.pivot.rotation_x = clamp(self.pivot.rotation_x, -89, 89)

        # déplacement ZQSD (+ flèches)
        fwd = held_keys['z'] + held_keys['up arrow'] - held_keys['s'] - held_keys['down arrow']
        side = held_keys['d'] + held_keys['right arrow'] - held_keys['q'] - held_keys['left arrow']
        direction = flat(self.forward) * fwd + flat(self.right) * side
        if direction.length() > 0:
            direction = direction.normalized()
        self.sprinting = held_keys['shift'] and fwd > 0
        speed = 9 if self.sprinting else 5.5
        accel = 12 if self.grounded else 3
        self.vel = lerp(self.vel, direction * speed, min(1, dt * accel))
        new = self.position + self.vel * dt
        new = self.world.resolve(new, PLAYER_RADIUS, self.y)

        # gravité et saut
        floor_h = self.world.floor_height(new.x, new.z, PLAYER_RADIUS, self.y)
        self.vy -= GRAVITY * dt
        new.y = self.y + self.vy * dt
        if new.y <= floor_h:
            new.y = floor_h
            self.vy = 0
            self.grounded = True
        else:
            self.grounded = new.y - floor_h < 0.02
        self.speed_now = flat(new - self.position).length() / max(dt, 1e-4)
        self.position = new

        # régénération lente
        if self.game.t - self.last_hurt > 5 and self.hp < 100:
            self.hp = min(100, self.hp + 8 * dt)

        # arme : balancement, recul, tir auto
        self.recoil = max(0, self.recoil - dt * 6)
        if self.recoil_pitch > 0 and self.cooldown < -0.05:
            back = min(self.recoil_pitch, dt * 6)
            self.recoil_pitch -= back
            self.pivot.rotation_x += back
        bob_t = self.game.t * (12 if self.sprinting else 8)
        bob = min(1, self.speed_now / 5) if self.grounded else 0
        self.gun.position = self.gun_base + Vec3(math.sin(bob_t) * 0.012 * bob,
                                                 abs(math.cos(bob_t)) * 0.012 * bob - self.recoil * 0.03,
                                                 -self.recoil * 0.08)
        self.gun.rotation_x = -self.recoil * 6
        self.cooldown -= dt
        if self.reload_t > 0:
            self.reload_t -= dt
            self.gun.rotation_x = 30 * math.sin(clamp(self.reload_t / 1.6, 0, 1) * math.pi)
            if self.reload_t <= 0:
                self.mag = 30
        elif (held_keys['right mouse'] or held_keys['p']) and self.cooldown <= 0:
            self.shoot()

    def jump(self):
        if self.grounded and not self.dead:
            self.vy = 7.5
            self.grounded = False

    def reload(self):
        if self.reload_t <= 0 and self.mag < 30:
            self.reload_t = 1.6

    def shoot(self):
        if self.mag <= 0:
            self.reload()
            return
        self.mag -= 1
        self.cooldown = 0.1
        self.recoil = min(1.5, self.recoil + 0.5)
        muzzle_flash(self.muzzle, scale=0.35)
        spread = 0.004 + 0.02 * min(1, self.speed_now / 9) + (0.02 if not self.grounded else 0)
        d = camera.forward + camera.right * random.uniform(-spread, spread) + camera.up * random.uniform(-spread, spread)
        d = d.normalized()
        origin = camera.world_position
        hit = raycast(origin, d, 150, ignore=[self])
        end = hit.world_point if hit.hit else origin + d * 150
        tracer(self.muzzle.world_position, end, color.rgb32(255, 240, 160), thickness=0.015, life=0.04)
        # petit recul de visée
        self.pivot.rotation_x -= 0.35
        self.recoil_pitch = min(self.recoil_pitch + 0.35 * 0.8, 6)
        self.rotation_y += random.uniform(-0.15, 0.15)
        if hit.hit:
            ent = hit.entity
            owner = getattr(ent, 'owner', None)
            if isinstance(owner, Enemy):
                zone = ent.zone
                dmg = {'head': 100, 'body': 34, 'limb': 22, 'gun': 15}.get(zone, 25)
                owner.take_hit(dmg, zone, hit.world_point)
                self.game.hud.hitmarker(zone == 'head')
            elif hasattr(ent, 'target'):
                ent.target.hit()
                impact(hit.world_point, hit.world_normal, color.rgb32(40, 40, 40))
                self.game.hud.hitmarker(False)
            else:
                impact(hit.world_point, hit.world_normal)
        # les ennemis entendent le tir
        for e in self.game.enemies:
            if not e.dead and flat_dist(e.position, self.position) < 35:
                invoke(e.hear_shot, Vec3(self.position), delay=random.uniform(0.1, 0.5))


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class HUD:
    def __init__(self, game):
        self.game = game
        ui = camera.ui
        c = color.rgba(1, 1, 1, 0.9)
        for pos, sc in [((0.012, 0), (0.012, 0.002)), ((-0.012, 0), (0.012, 0.002)),
                        ((0, 0.012), (0.002, 0.012)), ((0, -0.012), (0.002, 0.012))]:
            Entity(parent=ui, model='quad', color=c, position=pos, scale=sc)
        self.hit = Entity(parent=ui, model='quad', texture='circle_outlined', color=color.clear, scale=0.03)
        self.hp_bg = Entity(parent=ui, model='quad', color=color.rgba(0, 0, 0, 0.5), origin=(-0.5, 0),
                            position=(-0.85, -0.44), scale=(0.4, 0.03))
        self.hp_bar = Entity(parent=ui, model='quad', color=color.rgb32(80, 220, 90), origin=(-0.5, 0),
                             position=(-0.85, -0.44, -0.01), scale=(0.4, 0.03))
        self.hp_text = Text(parent=ui, text='', position=(-0.85, -0.4), scale=1)
        self.ammo = Text(parent=ui, text='', position=(0.62, -0.42), scale=1.6)
        self.info = Text(parent=ui, text='', position=(-0.85, 0.47), scale=1)
        self.msg = Text(parent=ui, text='', origin=(0, 0), y=0.15, scale=2, color=color.white)
        self.feed = Text(parent=ui, text='', origin=(0.5, 0.5), position=(0.86, 0.47), scale=1)
        self.damage = Entity(parent=ui, model='quad', color=color.rgba(0.8, 0, 0, 0), scale=(3, 2), z=1)
        self.dir_ind = Entity(parent=ui, model='quad', color=color.rgba(1, 0.1, 0.1, 0), scale=(0.04, 0.012))
        self.feed_lines = []
        Text(parent=ui, text='ZQSD: bouger  Maj: courir  Espace: sauter  Clic droit / P: tirer  R: recharger  Échap: pause',
             position=(-0.85, -0.47), scale=0.75, color=color.rgba(1, 1, 1, 0.6))

    def update(self):
        g = self.game
        p = g.player
        self.hp_bar.scale_x = 0.4 * max(0, p.hp) / 100
        self.hp_bar.color = color.rgb32(80, 220, 90) if p.hp > 50 else (color.orange if p.hp > 25 else color.red)
        self.hp_text.text = f'Santé {int(p.hp)}'
        self.ammo.text = 'Rechargement...' if p.reload_t > 0 else f'{p.mag} / 30'
        alive = sum(1 for e in g.enemies if not e.dead)
        self.info.text = f'Vague {g.wave}    Ennemis restants {alive}    Score {g.score}    Éliminations {g.kills}'
        a = self.damage.color.a
        if a > 0:
            self.damage.color = color.rgba(0.8, 0, 0, max(0, a - time.dt * 0.8))
        da = self.dir_ind.color.a
        if da > 0:
            self.dir_ind.color = color.rgba(1, 0.1, 0.1, max(0, da - time.dt * 1.2))
        ha = self.hit.color.a
        if ha > 0:
            self.hit.color = color.rgba(self.hit.color.r, self.hit.color.g, self.hit.color.b, max(0, ha - time.dt * 5))

    def flash_damage(self, from_pos):
        self.damage.color = color.rgba(0.8, 0, 0, min(0.45, self.damage.color.a + 0.25))
        # indicateur de direction du tir
        p = self.game.player
        ang = angle_diff(p.rotation_y, yaw_to(p.position, from_pos))
        r = math.radians(ang)
        self.dir_ind.position = (math.sin(r) * 0.12, math.cos(r) * 0.12)
        self.dir_ind.rotation_z = ang
        self.dir_ind.color = color.rgba(1, 0.1, 0.1, 0.9)

    def hitmarker(self, head):
        self.hit.color = color.rgba(1, 0.2, 0.2, 1) if head else color.rgba(1, 1, 1, 1)

    def add_feed(self, line):
        self.feed_lines.append(line)
        self.feed_lines = self.feed_lines[-5:]
        self.feed.text = '\n'.join(self.feed_lines)
        invoke(self.pop_feed, line, delay=4)

    def pop_feed(self, line):
        if line in self.feed_lines:
            self.feed_lines.remove(line)
            self.feed.text = '\n'.join(self.feed_lines)

    def message(self, text, duration=2.5):
        self.msg.text = text
        if duration:
            invoke(self._clear_msg, text, delay=duration)

    def _clear_msg(self, text):
        if self.msg.text == text:
            self.msg.text = ''


# ---------------------------------------------------------------------------
# Jeu
# ---------------------------------------------------------------------------

SPAWNS = [Vec3(-30, 0, 32), Vec3(30, 0, 32), Vec3(0, 0, 25), Vec3(-20, 0, 12), Vec3(20, 0, 12),
          Vec3(-34, 0, -2), Vec3(34, 0, -2), Vec3(-10, 0, 36), Vec3(10, 0, 36), Vec3(0, 0, 14)]


class Game(Entity):
    def __init__(self):
        super().__init__(ignore_paused=True)
        self.t = 0
        self.paused = False
        self.over = False
        self.score = 0
        self.kills = 0
        self.wave = 0
        self.enemies = []

        Sky(texture='sky_default')
        self.world = World()
        self.sun = DirectionalLight(shadow_map_resolution=Vec2(4096, 4096))
        self.sun.look_at(Vec3(0.6, -1, 0.45))
        invoke(self.sun.update_bounds, self.world.level, delay=0.1)
        AmbientLight(color=color.rgba(0.55, 0.55, 0.6, 1))

        self.player = Player(self)
        self.hud = HUD(self)
        for pos, yaw in [(-6, -30), (-3, -30), (0, -30), (3, -30), (6, -30)]:
            Target(self, Vec3(pos, 0, yaw), yaw=0)
        self.targets_note = True
        mouse.locked = True
        self.hud.message('Éliminez les ennemis !\nLes cibles devant vous servent à s\'entraîner', 4)
        invoke(self.next_wave, delay=2)

    # -- vagues ------------------------------------------------------------
    def next_wave(self):
        if self.over:
            return
        self.wave += 1
        n = min(2 + self.wave, 9)
        spawns = sorted(SPAWNS, key=lambda s: -flat_dist(s, self.player.position))[:max(n + 2, 6)]
        random.shuffle(spawns)
        for s in spawns[:n]:
            e = Enemy(self, s + Vec3(random.uniform(-1, 1), 0, random.uniform(-1, 1)))
            e.rotation_y = random.uniform(0, 360)
            self.enemies.append(e)
        self.hud.message(f'Vague {self.wave}', 2)

    def on_enemy_killed(self, enemy, headshot):
        self.kills += 1
        self.add_score(150 if headshot else 100, 'Tir à la tête ! +150' if headshot else 'Ennemi éliminé +100')
        if all(e.dead for e in self.enemies):
            self.hud.message('Vague terminée !', 2.5)
            invoke(self.cleanup_and_next, delay=4)

    def cleanup_and_next(self):
        self.enemies = [e for e in self.enemies if not e.dead]
        self.next_wave()

    def add_score(self, pts, label):
        self.score += pts
        self.hud.add_feed(label)

    def flyby(self, point):
        if flat_dist(point, self.player.position) < 2.5:
            self.hud.damage.color = color.rgba(0.8, 0, 0, max(self.hud.damage.color.a, 0.06))

    # -- états -------------------------------------------------------------
    def game_over(self):
        self.over = True
        self.hud.message(f'Vous êtes mort !\nScore : {self.score}   Vague : {self.wave}\n\nEntrée pour recommencer', 0)
        self.player.pivot.animate_position((0, 0.3, 0), duration=0.6)
        self.player.pivot.animate_rotation_z(40, duration=0.6)

    def restart(self):
        for e in self.enemies:
            if not e.dead:
                e.dead = True
                e.release_cover()
                destroy(e)
        self.enemies = []
        for c in self.world.covers:
            c.owner = None
        p = self.player
        p.position = Vec3(0, 0, -34)
        p.rotation_y = 0
        p.pivot.position = (0, 1.65, 0)
        p.pivot.rotation = (0, 0, 0)
        p.hp, p.dead, p.mag, p.reload_t, p.vel, p.vy = 100, False, 30, 0, Vec3(0, 0, 0), 0
        self.over = False
        self.score = self.kills = self.wave = 0
        self.hud.msg.text = ''
        invoke(self.next_wave, delay=1.5)

    def toggle_pause(self):
        self.paused = not self.paused
        mouse.locked = not self.paused
        if self.paused:
            application.pause()
            self.hud.message('PAUSE\nÉchap : reprendre    X : quitter', 0)
        else:
            application.resume()
            self.hud.msg.text = ''

    def update(self):
        if not self.paused:
            self.t += time.dt
        self.hud.update()

    def input(self, key):
        if key == 'escape':
            if not self.over:
                self.toggle_pause()
        elif key == 'x' and self.paused:
            application.quit()
        elif self.paused:
            return
        elif key == 'space':
            self.player.jump()
        elif key == 'r':
            self.player.reload()
        elif key == 'enter' and self.over:
            self.restart()
        elif key == 'left mouse down' and not mouse.locked:
            mouse.locked = True


if __name__ == '__main__':
    app = Ursina(title='FPS Ursina', borderless=False, development_mode=False)
    window.color = color.rgb32(140, 180, 230)
    window.fps_counter.enabled = True
    window.exit_button.visible = False
    game = Game()
    app.run()
