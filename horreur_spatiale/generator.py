# -*- coding: utf-8 -*-
"""
generator.py — Génération procédurale de l'intérieur du vaisseau.

Principe :
  * grille 2D de cases (config.CELL mètres) : SOLID (cloison / vide technique),
    ROOM (salle), CORR (couloir), VENT (conduit d'aération) ;
  * placement des salles sans chevauchement (1 case de cloison minimum) ;
  * graphe de connexion : arbre couvrant minimal + quelques boucles ;
  * couloirs creusés par A* (pénalité de virage -> couloirs droits avec coudes) ;
  * conduits d'aération creusés uniquement dans les cloisons (SOLID) ;
  * fenêtres sur les cases qui touchent la coque ;
  * les murs sont des ARÊTES entre cases : collisions, portes, grilles,
    ligne de vue et tirs sont calculés sur ces arêtes (rapide et exact).

L'architecture prévoit plusieurs ponts (ShipLayout.decks) ; un seul est
généré par défaut (config.DECK_COUNT).
"""
import heapq
import math
import random

import config as C

SOLID, ROOM, CORR, VENT = 0, 1, 2, 3
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

# type : (largeur, profondeur, hauteur, nom affiché)
ROOM_SPECS = {
    "hangar": (12, 8, C.HANGAR_HEIGHT, "Hangar"),
    "command": (8, 6, C.ROOM_HEIGHT + .6, "Salle de commandement"),
    "engine": (8, 7, C.ENGINE_HEIGHT, "Salle des machines"),
    "medbay": (6, 5, C.ROOM_HEIGHT, "Infirmerie"),
    "mess": (7, 5, C.ROOM_HEIGHT, "Salle à manger"),
    "crew": (5, 4, C.ROOM_HEIGHT, "Quartiers de l'équipage"),
    "storage": (4, 3, C.ROOM_HEIGHT, "Réserve"),
}


# ============================================================================
class Blocker:
    """Boîte de collision alignée sur les axes (avec plage verticale)."""
    __slots__ = ("x0", "x1", "y0", "y1", "z0", "z1", "active", "kind", "owner")

    def __init__(self, x0, x1, y0, y1, z0, z1, kind="wall", owner=None):
        self.x0, self.x1 = min(x0, x1), max(x0, x1)
        self.y0, self.y1 = min(y0, y1), max(y0, y1)
        self.z0, self.z1 = min(z0, z1), max(z0, z1)
        self.active = True
        self.kind = kind
        self.owner = owner


class Room:
    def __init__(self, rid, rtype, x, y, w, h):
        self.id = rid
        self.type = rtype
        self.x, self.y, self.w, self.h = x, y, w, h
        spec = ROOM_SPECS[rtype]
        self.height = spec[2]
        self.name = spec[3]
        self.doors = []
        self.grilles = []
        self.visited = False
        self.entity = None
        self.lights = []

    def contains(self, i, j):
        return self.x <= i < self.x + self.w and self.y <= j < self.y + self.h

    def cells(self):
        for i in range(self.x, self.x + self.w):
            for j in range(self.y, self.y + self.h):
                yield i, j

    @property
    def center_cell(self):
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def world_center(self):
        return ((self.x + self.w / 2.0) * C.CELL, (self.y + self.h / 2.0) * C.CELL)

    def world_bounds(self):
        return (self.x * C.CELL, (self.x + self.w) * C.CELL, self.y * C.CELL, (self.y + self.h) * C.CELL)


def ekey(i, j, ni, nj):
    """Clé canonique d'une arête entre deux cases voisines."""
    if ni != i:
        return ("x", min(i, ni), j)       # arête verticale en x = (min+1)*CELL
    return ("z", i, min(j, nj))           # arête horizontale en z = (min+1)*CELL


def edge_geometry(key):
    """Renvoie (axe, position de la ligne, début, fin) en coordonnées monde."""
    a, i, j = key
    Cc = C.CELL
    if a == "x":
        return "x", (i + 1) * Cc, j * Cc, (j + 1) * Cc
    return "z", (j + 1) * Cc, i * Cc, (i + 1) * Cc


# ============================================================================
class Door:
    """Porte coulissante sur une arête. open_amount : 0 fermée -> 1 ouverte."""

    def __init__(self, level, key, room_cell, out_cell):
        self.level = level
        self.key = key
        self.room_cell = room_cell
        self.out_cell = out_cell
        self.axis, self.line, s0, s1 = edge_geometry(key)
        self.mid = (s0 + s1) / 2
        if self.axis == "x":
            self.pos = (self.line, self.mid)
        else:
            self.pos = (self.mid, self.line)
        self.open_amount = 0.0
        self.target = 0.0
        self.timer = 0.0
        self.locked = False
        self.panels = []          # entités visuelles (créées par rooms.py)
        self.status_light = None
        self.blocker = None
        self.on_change = None

    def open(self, hold=7.0):
        if self.target < 1:
            self.target = 1.0
            if self.on_change:
                self.on_change(self, True)
        self.timer = max(self.timer, hold)

    def close(self):
        if self.target > 0:
            self.target = 0.0
            if self.on_change:
                self.on_change(self, False)

    @property
    def is_open(self):
        return self.open_amount > 0.5

    def update(self, dt, occupants):
        if self.target > 0:
            self.timer -= dt
            if self.timer <= 0:
                # ne se referme pas sur quelqu'un
                busy = any(abs(p[0] - self.pos[0]) < 1.3 and abs(p[1] - self.pos[1]) < 1.3 for p in occupants)
                if busy:
                    self.timer = 1.0
                else:
                    self.close()
        speed = 2.4
        if self.open_amount < self.target:
            self.open_amount = min(self.target, self.open_amount + dt * speed)
        elif self.open_amount > self.target:
            self.open_amount = max(self.target, self.open_amount - dt * speed)
        if self.blocker:
            self.blocker.active = self.open_amount < 0.85


class Grille:
    """Grille d'aération entre une salle et un conduit."""

    def __init__(self, level, key, room_cell, vent_cell):
        self.level = level
        self.key = key
        self.room_cell = room_cell
        self.vent_cell = vent_cell
        self.axis, self.line, s0, s1 = edge_geometry(key)
        self.mid = (s0 + s1) / 2
        self.pos = (self.line, self.mid) if self.axis == "x" else (self.mid, self.line)
        self.opened = False
        self.blocker = None
        self.entity = None
        self.angle = 0.0

    def set_open(self, v=True):
        self.opened = v
        if self.blocker:
            self.blocker.active = not v

    def room_side_point(self, dist=0.6):
        """Point dans la salle, juste devant la grille."""
        ri, rj = self.room_cell
        vi, vj = self.vent_cell
        dx, dz = ri - vi, rj - vj
        return (self.pos[0] + dx * dist, self.pos[1] + dz * dist)


# ============================================================================
class Level:
    """Un pont du vaisseau : grille, salles, arêtes, collisions, requêtes IA."""

    def __init__(self, seed, deck_index=0):
        self.seed = seed
        self.deck = deck_index
        self.base_y = deck_index * C.DECK_SPACING
        self.rng = random.Random(seed * 31 + deck_index)
        self.W, self.H = C.GRID_W, C.GRID_H
        self.kind = [[SOLID] * self.H for _ in range(self.W)]
        self.room_of = [[-1] * self.H for _ in range(self.W)]
        self.rooms = []
        self.doors = {}
        self.grilles = {}
        self.windows = {}         # clé d'arête -> 'bay' | 'porthole' | 'opening'
        self.connections = []
        self.vent_links = []
        self.blockers = {}        # (i, j) -> [Blocker]
        self.all_blockers = []
        self.interactables = {}   # (i, j) -> [objet]
        self.spawn_points = []    # (x, z, type)
        self.links = {}
        self.hangar_opening = None
        self.generate()

    # ------------------------------------------------------------------
    # utilitaires de grille
    def inside(self, i, j):
        return 0 <= i < self.W and 0 <= j < self.H

    def cell_at(self, x, z):
        return int(math.floor(x / C.CELL)), int(math.floor(z / C.CELL))

    def cell_center(self, i, j):
        return ((i + .5) * C.CELL, (j + .5) * C.CELL)

    def is_open(self, i, j):
        return self.inside(i, j) and self.kind[i][j] != SOLID

    def ceiling(self, i, j):
        if not self.inside(i, j):
            return 0.0
        k = self.kind[i][j]
        if k == ROOM:
            return self.rooms[self.room_of[i][j]].height
        if k == CORR:
            return C.CORRIDOR_HEIGHT
        if k == VENT:
            return C.VENT_HEIGHT
        return 0.0

    def ceiling_at(self, x, z):
        return self.ceiling(*self.cell_at(x, z))

    def room_at(self, x, z):
        i, j = self.cell_at(x, z)
        if self.inside(i, j) and self.room_of[i][j] >= 0:
            return self.rooms[self.room_of[i][j]]
        return None

    def rooms_of_type(self, t):
        return [r for r in self.rooms if r.type == t]

    def room(self, t):
        r = self.rooms_of_type(t)
        return r[0] if r else None

    # ------------------------------------------------------------------
    def edge_state(self, i, j, ni, nj):
        """'open', 'wall', 'door', 'grille', 'bay', 'porthole', 'opening', 'void'."""
        a_open = self.is_open(i, j)
        b_open = self.is_open(ni, nj)
        if not a_open and not b_open:
            return "void"
        key = ekey(i, j, ni, nj)
        if not self.inside(i, j) or not self.inside(ni, nj):
            return self.windows.get(key, "wall")
        if key in self.doors:
            return "door"
        if key in self.grilles:
            return "grille"
        if not (a_open and b_open):
            return "wall"
        ka, kb = self.kind[i][j], self.kind[ni][nj]
        if ka == ROOM and kb == ROOM:
            return "open" if self.room_of[i][j] == self.room_of[ni][nj] else "wall"
        if ka == kb and ka in (CORR, VENT):
            return "open"
        return "wall"

    # ==================================================================
    # GÉNÉRATION
    # ==================================================================
    def generate(self):
        rng = self.rng
        # 1) hangar au centre du flanc sud (touche la coque)
        hw, hh = ROOM_SPECS["hangar"][:2]
        hx = self.W // 2 - hw // 2
        self._add_room("hangar", hx, 0, hw, hh)
        # ouverture du hangar sur la coque (côté z = 0)
        ow = C.HANGAR_OPENING_CELLS
        ox = hx + (hw - ow) // 2
        self.hangar_opening = (ox, ow)
        for i in range(ox, ox + ow):
            self.windows[ekey(i, 0, i, -1)] = "opening"

        # 2) salle de commandement : le plus loin possible du hangar, contre la coque nord
        cw, ch = ROOM_SPECS["command"][:2]
        hcx = hx + hw / 2
        best = None
        for x in range(0, self.W - cw + 1):
            y = self.H - ch
            if not self._rect_free(x, y, cw, ch):
                continue
            d = math.hypot(x + cw / 2 - hcx, y + ch / 2) + rng.uniform(0, 4)
            if best is None or d > best[0]:
                best = (d, x, y)
        self._add_room("command", best[1], best[2], cw, ch)

        # 3) autres salles
        plan = ["engine", "medbay", "mess", "crew", "crew", "crew", "storage", "storage"]
        for t in plan:
            w, h = ROOM_SPECS[t][:2]
            placed = False
            for attempt in range(400):
                ww, hh2 = (w, h) if rng.random() < .5 or t in ("engine",) else (h, w)
                if attempt > 250:           # on réduit si ça ne rentre pas
                    ww, hh2 = max(3, ww - 1), max(3, hh2 - 1)
                x = rng.randint(0, self.W - ww)
                y = rng.randint(0, self.H - hh2)
                if self._rect_free(x, y, ww, hh2):
                    self._add_room(t, x, y, ww, hh2)
                    placed = True
                    break
            if not placed:
                print(f"[génération] impossible de placer : {t}")

        # 4) graphe de connexion : arbre couvrant minimal (Prim) + boucles
        n = len(self.rooms)
        centers = [r.center_cell for r in self.rooms]

        def dist(a, b):
            return math.hypot(centers[a][0] - centers[b][0], centers[a][1] - centers[b][1])

        in_tree = {0}
        edges = []
        while len(in_tree) < n:
            best = None
            for a in in_tree:
                for b in range(n):
                    if b in in_tree:
                        continue
                    d = dist(a, b)
                    if best is None or d < best[0]:
                        best = (d, a, b)
            edges.append((best[1], best[2]))
            in_tree.add(best[2])
        existing = {frozenset(e) for e in edges}
        for a in range(n):
            if rng.random() < C.EXTRA_LOOP_CHANCE:
                cands = sorted((dist(a, b), b) for b in range(n) if b != a and frozenset((a, b)) not in existing)
                if cands:
                    b = cands[min(len(cands) - 1, rng.randint(0, 1))][1]
                    edges.append((a, b))
                    existing.add(frozenset((a, b)))
        # le hangar a au moins deux sorties (pour pouvoir fuir)
        hdeg = sum(1 for e in edges if 0 in e)
        if hdeg < 2:
            cands = sorted((dist(0, b), b) for b in range(1, n) if frozenset((0, b)) not in existing)
            if cands:
                edges.append((0, cands[0][1]))
        self.connections = edges

        # 5) couloirs
        for a, b in edges:
            self._connect(self.rooms[a], self.rooms[b])

        # 6) conduits d'aération
        self._make_vents()

        # 7) fenêtres
        self._make_windows()

        # 8) collisions et liens de navigation
        self._build_collision()
        self._build_links()

        # 9) points d'apparition (grilles et plafonds)
        for g in self.grilles.values():
            x, z = g.room_side_point(0.5)
            self.spawn_points.append((x, z, "grille"))
        for i in range(self.W):
            for j in range(self.H):
                if self.kind[i][j] in (ROOM, CORR) and rng.random() < 0.06:
                    r = self.room_of[i][j]
                    if r >= 0 and self.rooms[r].type == "hangar":
                        continue
                    x, z = self.cell_center(i, j)
                    self.spawn_points.append((x, z, "ceiling"))

    # ------------------------------------------------------------------
    def _rect_free(self, x, y, w, h):
        if x < 0 or y < 0 or x + w > self.W or y + h > self.H:
            return False
        for i in range(x - 1, x + w + 1):
            for j in range(y - 1, y + h + 1):
                if self.inside(i, j) and self.kind[i][j] != SOLID:
                    return False
        return True

    def _add_room(self, t, x, y, w, h):
        r = Room(len(self.rooms), t, x, y, w, h)
        self.rooms.append(r)
        for i, j in r.cells():
            self.kind[i][j] = ROOM
            self.room_of[i][j] = r.id
        return r

    # ------------------------------------------------------------------
    def _door_candidates(self, room, target):
        """Paires (case salle, case extérieure) sur le périmètre, triées vers la cible."""
        out = []
        for i, j in room.cells():
            for dx, dz in DIRS:
                ni, nj = i + dx, j + dz
                if room.contains(ni, nj) or not self.inside(ni, nj):
                    continue
                if self.kind[ni][nj] not in (SOLID, CORR):
                    continue
                if ekey(i, j, ni, nj) in self.doors or ekey(i, j, ni, nj) in self.grilles:
                    continue
                # évite de coller une porte à une autre
                if any(abs(d.room_cell[0] - i) + abs(d.room_cell[1] - j) <= 1 for d in room.doors):
                    continue
                if room.type == "hangar" and dz == -1:
                    continue
                d = math.hypot(ni + .5 - target[0], nj + .5 - target[1])
                out.append((d, (i, j), (ni, nj)))
        out.sort()
        return out

    def _connect(self, ra, rb):
        rng = self.rng
        ca = self._door_candidates(ra, rb.center_cell)
        cb = self._door_candidates(rb, ra.center_cell)
        if not ca or not cb:
            return False
        for attempt in range(4):
            da = ca[min(len(ca) - 1, rng.randint(0, 2) + attempt)]
            db = cb[min(len(cb) - 1, rng.randint(0, 2) + attempt)]
            path = self._astar_carve(da[2], db[2])
            if path:
                for i, j in path:
                    self.kind[i][j] = CORR
                self._add_door(ra, da[1], da[2])
                self._add_door(rb, db[1], db[2])
                return True
        return False

    def _add_door(self, room, rc, oc):
        key = ekey(rc[0], rc[1], oc[0], oc[1])
        if key in self.doors:
            return self.doors[key]
        d = Door(self, key, rc, oc)
        self.doors[key] = d
        room.doors.append(d)
        return d

    def _astar_carve(self, start, goal, allowed=(SOLID, CORR), costs=None, turn_penalty=0.8, max_len=200):
        """A* avec pénalité de virage. L'état inclut la direction d'arrivée."""
        costs = costs or {CORR: 1.0, SOLID: 1.7, VENT: 1.0}
        sx, sz = start
        gx, gz = goal
        if self.kind[sx][sz] not in allowed or self.kind[gx][gz] not in allowed:
            return None
        openh = [(0, 0, sx, sz, -1)]
        gbest = {(sx, sz, -1): 0}
        parent = {}
        n = 0
        while openh:
            f, g, i, j, d = heapq.heappop(openh)
            if (i, j) == (gx, gz):
                path = [(i, j)]
                k = (i, j, d)
                while k in parent:
                    k = parent[k]
                    path.append((k[0], k[1]))
                return path[::-1] if len(path) <= max_len else None
            n += 1
            if n > 20000:
                return None
            for di, (dx, dz) in enumerate(DIRS):
                ni, nj = i + dx, j + dz
                if not self.inside(ni, nj):
                    continue
                k = self.kind[ni][nj]
                if k not in allowed:
                    continue
                c = costs.get(k, 1.0)
                if d != -1 and di != d:
                    c += turn_penalty
                ng = g + c
                key = (ni, nj, di)
                if ng < gbest.get(key, 1e18):
                    gbest[key] = ng
                    parent[key] = (i, j, d)
                    h = abs(ni - gx) + abs(nj - gz)
                    heapq.heappush(openh, (ng + h, ng, ni, nj, di))
        return None

    # ------------------------------------------------------------------
    def _make_vents(self):
        rng = self.rng
        rooms = [r for r in self.rooms]
        pairs = []
        hangar = self.room("hangar")
        command = self.room("command")

        def nearest(r, exclude=()):
            best = None
            for o in rooms:
                if o is r or o in exclude:
                    continue
                d = math.hypot(o.center_cell[0] - r.center_cell[0], o.center_cell[1] - r.center_cell[1])
                if best is None or d < best[0]:
                    best = (d, o)
            return best[1] if best else None

        if hangar:
            pairs.append((hangar, nearest(hangar)))
        if command:
            pairs.append((command, nearest(command)))
        tries = 0
        while len(pairs) < C.VENT_LINKS and tries < 60:
            tries += 1
            a = rng.choice(rooms)
            b = nearest(a, exclude=[p[1] for p in pairs if p[0] is a])
            if b and (a, b) not in pairs and (b, a) not in pairs:
                pairs.append((a, b))
        for a, b in pairs:
            if a is None or b is None:
                continue
            sa = self._grille_candidates(a, b.center_cell)
            sb = self._grille_candidates(b, a.center_cell)
            done = False
            for ia in range(min(3, len(sa))):
                for ib in range(min(3, len(sb))):
                    path = self._astar_carve(sa[ia][2], sb[ib][2], allowed=(SOLID, VENT),
                                             costs={SOLID: 1.0, VENT: 0.4}, turn_penalty=0.3, max_len=45)
                    if path:
                        for i, j in path:
                            self.kind[i][j] = VENT
                        for (rc, vc, room) in ((sa[ia][1], sa[ia][2], a), (sb[ib][1], sb[ib][2], b)):
                            key = ekey(rc[0], rc[1], vc[0], vc[1])
                            if key not in self.grilles:
                                g = Grille(self, key, rc, vc)
                                self.grilles[key] = g
                                room.grilles.append(g)
                        self.vent_links.append((a.id, b.id))
                        done = True
                        break
                if done:
                    break

    def _grille_candidates(self, room, target):
        out = []
        for i, j in room.cells():
            for dx, dz in DIRS:
                ni, nj = i + dx, j + dz
                if room.contains(ni, nj) or not self.inside(ni, nj):
                    continue
                if self.kind[ni][nj] not in (SOLID, VENT):
                    continue
                key = ekey(i, j, ni, nj)
                if key in self.doors or key in self.grilles:
                    continue
                # pas collée à une porte
                if any(abs(d.room_cell[0] - i) + abs(d.room_cell[1] - j) <= 1 for d in room.doors):
                    continue
                d = math.hypot(ni + .5 - target[0], nj + .5 - target[1]) + self.rng.uniform(0, 1.5)
                out.append((d, (i, j), (ni, nj)))
        out.sort()
        return out

    # ------------------------------------------------------------------
    def _make_windows(self):
        rng = self.rng
        for i in range(self.W):
            for j in range(self.H):
                k = self.kind[i][j]
                if k not in (ROOM, CORR):
                    continue
                for dx, dz in DIRS:
                    ni, nj = i + dx, j + dz
                    if self.inside(ni, nj):
                        continue
                    key = ekey(i, j, ni, nj)
                    if key in self.windows:
                        continue
                    if k == ROOM:
                        room = self.rooms[self.room_of[i][j]]
                        if room.type == "command" and dz == 1:
                            self.windows[key] = "bay"
                        elif room.type == "hangar":
                            if rng.random() < .25:
                                self.windows[key] = "porthole"
                        elif rng.random() < .5:
                            self.windows[key] = "porthole"
                    elif rng.random() < .3:
                        self.windows[key] = "porthole"

    # ==================================================================
    # COLLISIONS
    # ==================================================================
    def add_blocker(self, b):
        """Enregistre une boîte dans toutes les cases qu'elle recouvre."""
        Cc = C.CELL
        i0 = int(math.floor((b.x0 - .01) / Cc))
        i1 = int(math.floor((b.x1 + .01) / Cc))
        j0 = int(math.floor((b.z0 - .01) / Cc))
        j1 = int(math.floor((b.z1 + .01) / Cc))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                self.blockers.setdefault((i, j), []).append(b)
        self.all_blockers.append(b)
        return b

    def _build_collision(self):
        T = C.WALL_T / 2
        H = 30.0
        done = set()
        for i in range(self.W):
            for j in range(self.H):
                if self.kind[i][j] == SOLID:
                    continue
                for dx, dz in DIRS:
                    ni, nj = i + dx, j + dz
                    key = ekey(i, j, ni, nj)
                    if key in done:
                        continue
                    done.add(key)
                    st = self.edge_state(i, j, ni, nj)
                    if st == "open":
                        continue
                    axis, line, s0, s1 = edge_geometry(key)

                    def box(a0, a1, y0, y1, kind="wall", owner=None):
                        if axis == "x":
                            return self.add_blocker(Blocker(line - T, line + T, y0, y1, a0, a1, kind, owner))
                        return self.add_blocker(Blocker(a0, a1, y0, y1, line - T, line + T, kind, owner))

                    if st == "door":
                        d = self.doors[key]
                        m = (s0 + s1) / 2
                        hw = C.DOOR_WIDTH / 2
                        box(s0, m - hw, 0, H)
                        box(m + hw, s1, 0, H)
                        box(m - hw, m + hw, C.DOOR_HEIGHT, H)
                        d.blocker = box(m - hw, m + hw, 0, C.DOOR_HEIGHT, "door", d)
                    elif st == "grille":
                        g = self.grilles[key]
                        box(s0, s1, C.VENT_HEIGHT, H)
                        g.blocker = box(s0, s1, 0, C.VENT_HEIGHT, "grille", g)
                    else:
                        box(s0, s1, -1, H, st)

    def collide(self, x, z, r, y0, y1, extra=None, ignore=()):
        """Résout la collision d'un cercle (rayon r) contre les boîtes voisines."""
        i, j = self.cell_at(x, z)
        cand = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                lst = self.blockers.get((i + di, j + dj))
                if lst:
                    cand.extend(lst)
        if extra:
            cand.extend(extra)
        for _ in range(3):
            moved = False
            for b in cand:
                if not b.active or b.y0 >= y1 or b.y1 <= y0 or b.kind in ignore:
                    continue
                cx = min(max(x, b.x0), b.x1)
                cz = min(max(z, b.z0), b.z1)
                dx, dz = x - cx, z - cz
                d2 = dx * dx + dz * dz
                if d2 >= r * r:
                    continue
                if d2 > 1e-9:
                    d = math.sqrt(d2)
                    push = r - d
                    x += dx / d * push
                    z += dz / d * push
                else:
                    # centre à l'intérieur : sortie par le côté le plus proche
                    opts = ((x - b.x0 + r, -1, 0), (b.x1 - x + r, 1, 0), (z - b.z0 + r, 0, -1), (b.z1 - z + r, 0, 1))
                    m = min(opts)
                    x += m[1] * m[0]
                    z += m[2] * m[0]
                moved = True
            if not moved:
                break
        return x, z

    def blocked_point(self, x, y, z, margin=0.0):
        i, j = self.cell_at(x, z)
        if not self.inside(i, j) or self.kind[i][j] == SOLID:
            return True
        if y < 0 or y > self.ceiling(i, j):
            return True
        for b in self.blockers.get((i, j), ()):
            if (b.active and b.x0 - margin <= x <= b.x1 + margin and b.z0 - margin <= z <= b.z1 + margin
                    and b.y0 <= y <= b.y1):
                return True
        return False

    # ------------------------------------------------------------------
    def _edge_blocks_ray(self, i, j, ni, nj, y):
        """L'arête bloque-t-elle un rayon passant à la hauteur y ?"""
        st = self.edge_state(i, j, ni, nj)
        if st == "open":
            return False
        if st == "door":
            return not self.doors[ekey(i, j, ni, nj)].is_open or y > C.DOOR_HEIGHT
        if st == "grille":
            g = self.grilles[ekey(i, j, ni, nj)]
            return y > C.VENT_HEIGHT or not g.opened
        return True

    def raycast(self, ox, oy, oz, dx, dy, dz, max_dist=60.0):
        """
        Lancer de rayon par DDA sur la grille (murs = arêtes) + sol/plafond.
        Renvoie (distance, (x, y, z), normale).
        """
        Cc = C.CELL
        i, j = self.cell_at(ox, oz)
        if not self.is_open(i, j):
            return 0.0, (ox, oy, oz), (0, 1, 0)
        step_i = 1 if dx > 0 else -1
        step_j = 1 if dz > 0 else -1
        inf = 1e18
        t_dx = abs(Cc / dx) if abs(dx) > 1e-9 else inf
        t_dz = abs(Cc / dz) if abs(dz) > 1e-9 else inf
        if dx > 0:
            t_mx = ((i + 1) * Cc - ox) / dx
        elif dx < 0:
            t_mx = (i * Cc - ox) / dx
        else:
            t_mx = inf
        if dz > 0:
            t_mz = ((j + 1) * Cc - oz) / dz
        elif dz < 0:
            t_mz = (j * Cc - oz) / dz
        else:
            t_mz = inf
        t = 0.0
        while t < max_dist:
            # sol / plafond de la case courante
            ceil = self.ceiling(i, j)
            t_exit = min(t_mx, t_mz)
            if dy < -1e-6:
                tf = (0 - oy) / dy
                if t <= tf <= t_exit:
                    return tf, (ox + dx * tf, 0, oz + dz * tf), (0, 1, 0)
            elif dy > 1e-6:
                tc = (ceil - oy) / dy
                if t <= tc <= t_exit:
                    return tc, (ox + dx * tc, ceil, oz + dz * tc), (0, -1, 0)
            if t_mx < t_mz:
                t = t_mx
                ni, nj = i + step_i, j
                normal = (-step_i, 0, 0)
                t_mx += t_dx
            else:
                t = t_mz
                ni, nj = i, j + step_j
                normal = (0, 0, -step_j)
                t_mz += t_dz
            if t > max_dist:
                break
            y = oy + dy * t
            if self._edge_blocks_ray(i, j, ni, nj, y) or y > self.ceiling(ni, nj):
                return t, (ox + dx * t, y, oz + dz * t), normal
            i, j = ni, nj
        return max_dist, (ox + dx * max_dist, oy + dy * max_dist, oz + dz * max_dist), (0, 1, 0)

    def line_of_sight(self, a, b):
        """Visibilité entre deux points 3D (murs, portes fermées)."""
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 1e-4:
            return True
        dist, _, _ = self.raycast(a[0], a[1], a[2], dx / d, dy / d, dz / d, d)
        return dist >= d - 0.05

    # ==================================================================
    # NAVIGATION (IA)
    # ==================================================================
    def _build_links(self):
        self.links = {}
        for i in range(self.W):
            for j in range(self.H):
                if self.kind[i][j] == SOLID:
                    continue
                lst = []
                for dx, dz in DIRS:
                    ni, nj = i + dx, j + dz
                    if not self.inside(ni, nj) or self.kind[ni][nj] == SOLID:
                        continue
                    st = self.edge_state(i, j, ni, nj)
                    if st in ("open", "door", "grille"):
                        lst.append((ni, nj, st))
                self.links[(i, j)] = lst

    def find_path(self, start, goal, agent="creature", max_nodes=6000):
        """A* sur les cases. agent : 'creature' (évite les conduits) ou 'alien'."""
        if start == goal:
            return [goal]
        if start not in self.links or goal not in self.links:
            return None
        vent_cost = 2.6 if agent == "creature" else 1.0
        gx, gz = goal
        openh = [(0, 0, start)]
        g = {start: 0}
        parent = {}
        n = 0
        while openh:
            _, gc, cur = heapq.heappop(openh)
            if cur == goal:
                path = [cur]
                while cur in parent:
                    cur = parent[cur]
                    path.append(cur)
                return path[::-1]
            n += 1
            if n > max_nodes:
                return None
            for ni, nj, st in self.links[cur]:
                c = vent_cost if self.kind[ni][nj] == VENT else 1.0
                if st == "door":
                    c += 0.5
                ng = gc + c
                nxt = (ni, nj)
                if ng < g.get(nxt, 1e18):
                    g[nxt] = ng
                    parent[nxt] = cur
                    heapq.heappush(openh, (ng + abs(ni - gx) + abs(nj - gz), ng, nxt))
        return None

    def random_cell(self, kinds=(ROOM, CORR), near=None, radius=None, min_radius=0.0, exclude_rooms=()):
        cells = []
        for (i, j) in self.links:
            if self.kind[i][j] not in kinds:
                continue
            r = self.room_of[i][j]
            if r >= 0 and self.rooms[r].type in exclude_rooms:
                continue
            if near is not None:
                x, z = self.cell_center(i, j)
                d = math.hypot(x - near[0], z - near[1])
                if (radius is not None and d > radius) or d < min_radius:
                    continue
            cells.append((i, j))
        if not cells:
            return None
        return self.rng.choice(cells)

    def vent_cells(self):
        return [c for c in self.links if self.kind[c[0]][c[1]] == VENT]

    # ------------------------------------------------------------------
    def add_interactable(self, obj, x, z):
        self.interactables.setdefault(self.cell_at(x, z), []).append(obj)

    def remove_interactable(self, obj):
        for lst in self.interactables.values():
            if obj in lst:
                lst.remove(obj)

    def interactables_near(self, x, z):
        i, j = self.cell_at(x, z)
        out = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                out.extend(self.interactables.get((i + di, j + dj), ()))
        return out

    # ------------------------------------------------------------------
    def debug_ascii(self):
        """Carte texte du pont (utile pour vérifier la génération)."""
        ch = {SOLID: "#", ROOM: ".", CORR: ",", VENT: "~"}
        rows = []
        for j in range(self.H - 1, -1, -1):
            row = ""
            for i in range(self.W):
                c = ch[self.kind[i][j]]
                if self.room_of[i][j] >= 0:
                    c = self.rooms[self.room_of[i][j]].type[0].upper()
                row += c
            rows.append(row)
        return "\n".join(rows)


class ShipLayout:
    """Ensemble des ponts du vaisseau (un seul par défaut)."""

    def __init__(self, seed, deck_count=C.DECK_COUNT):
        self.seed = seed
        self.decks = [Level(seed, d) for d in range(max(1, deck_count))]

    @property
    def main(self):
        return self.decks[0]
