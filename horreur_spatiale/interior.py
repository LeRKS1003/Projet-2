# -*- coding: utf-8 -*-
"""
interior.py — Habillage de l'intérieur du Kerguelen (après la construction des salles).

  * signalétique : noms des salles à côté des portes, numéros de section
    peints dans les couloirs, flèches d'évacuation (vers le hangar), logo
    Helios Biotech, danger biologique près de l'infirmerie, haute tension
    près de la salle des machines ;
  * portes plus détaillées : cadre épais, panneau de commande avec voyant,
    bandes de danger, plaques antidérapantes jaune et noir au sol ;
  * architecture : poutres au plafond, tuyaux avec colliers de fixation,
    câbles qui pendent (courbes), grilles de sol perforées ;
  * désordre lié à l'histoire : chaises renversées, papiers au sol,
    barricades de fortune près des portes, impacts de balles et douilles
    (fusillade de la salle à manger), messages écrits sur les murs ;
  * identité des salles : infirmerie blanche et froide, salle des machines
    industrielle et chaude, salle à manger « domestique », passerelle ;
  * vapeur qui s'échappe de tuyaux percés (particules, seulement quand la
    salle est affichée).

Toute la géométrie statique va dans les MeshBuilder du groupe (une salle ou
un bloc de couloirs) : elle est fusionnée en quelques meshes par groupe, ce
qui garde les performances (60 FPS visés).
"""
import math
import random
from collections import deque

from ursina import Entity, color, destroy

import config as C
import textures
from corpses import capsule
from generator import ROOM, CORR, VENT, SOLID, DIRS, ekey, edge_geometry
from lighting import additive


# ============================================================================
# OUTILS
# ============================================================================
def wall_quad(mb, cx, cy, cz, nx, nz, w, h, uv, col=(1, 1, 1, 1)):
    """Quad plaqué sur un mur (normale horizontale n), avec un rectangle UV (planche de signalétique)."""
    tx, tz = -nz, nx                      # tangente du mur (même convention que MeshBuilder.decal)
    hw, hh = w / 2, h / 2
    p0 = (cx - tx * hw, cy - hh, cz - tz * hw)
    p1 = (cx + tx * hw, cy - hh, cz + tz * hw)
    p2 = (cx + tx * hw, cy + hh, cz + tz * hw)
    p3 = (cx - tx * hw, cy + hh, cz - tz * hw)
    u0, v0, u1, v1 = uv
    mb.quad(p0, p1, p2, p3, (nx, 0, nz), col, uv=((u0, v0), (u1, v0), (u1, v1), (u0, v1)))


def wall_face(L, i, j, dx, dz):
    """Centre de la face intérieure du mur (i, j) -> (i+dx, j+dz) et normale vers la case."""
    Cc = C.CELL
    cx, cz = L.cell_center(i, j)
    off = Cc / 2 - C.WALL_T / 2 - .012
    return cx + dx * off, cz + dz * off, -dx, -dz


def sag_cable(mb, a, b, sag, r, col, n=6):
    """Câble qui pend entre deux points (chaîne de capsules en arc)."""
    pts = []
    for k in range(n + 1):
        t = k / n
        p = [a[q] + (b[q] - a[q]) * t for q in range(3)]
        p[1] -= sag * 4 * t * (1 - t)
        pts.append(p)
    for p, q in zip(pts, pts[1:]):
        capsule(mb, p, q, r, r, col, seg=5, cap=1)


class SteamVent:
    """Vapeur qui s'échappe d'un tuyau percé (quelques quads additifs, seulement si la salle est affichée)."""

    def __init__(self, parent, pos, direction, rng):
        self.parent = parent
        self.pos = pos
        self.dir = direction
        self.rng = rng
        self.root = Entity(parent=parent, name="steam")
        additive(self.root, 5)
        self.parts = []
        tex = textures.get('glow')
        for k in range(10):
            e = Entity(parent=self.root, model='quad', texture=tex, billboard=True,
                       color=color.rgba(.8, .82, .85, 0), scale=.3)
            self.parts.append([e, rng.uniform(0, 1.6)])
        self.t = 0.0

    def update(self, dt):
        if not self.parent.enabled:
            return
        self.t += dt
        x, y, z = self.pos
        dx, dy, dz = self.dir
        for p in self.parts:
            e, age = p
            age += dt
            if age > 1.6:
                age -= 1.6
            p[1] = age
            k = age / 1.6
            spread = .15 + k * .6
            e.position = (x + dx * k * 1.4 + math.sin(self.t * 3 + age * 5) * .05 * k,
                          y + dy * k * 1.4 + k * .5, z + dz * k * 1.4)
            e.scale = spread
            a = (1 - k) * min(1.0, k * 6) * .16
            e.color = color.rgba(.8, .82, .85, a)


# ============================================================================
# HABILLAGE
# ============================================================================
class InteriorDresser:
    def __init__(self, builder):
        self.b = builder
        self.L = builder.level
        self.rng = random.Random(builder.seed * 13 + 7)
        self.sign_uv = textures.sign_uv
        self.evac_dist = self._hangar_distances()

    # ------------------------------------------------------------------
    def dress(self):
        L = self.L
        for door in L.doors.values():
            self._door(door)
        for i in range(L.W):
            for j in range(L.H):
                if L.kind[i][j] == CORR:
                    self._corridor(i, j)
        for room in L.rooms:
            self._room_common(room)
            fn = getattr(self, "_room_" + room.type, None)
            if fn is not None:
                fn(room)
        self._wall_messages()

    # ------------------------------------------------------------------
    def _hangar_distances(self):
        """Distance (en cases) jusqu'au hangar, pour orienter les flèches d'évacuation."""
        L = self.L
        hangar = L.room("hangar")
        dist = {}
        q = deque()
        for c in hangar.cells():
            if c in L.links:
                dist[c] = 0
                q.append(c)
        while q:
            c = q.popleft()
            for ni, nj, st in L.links.get(c, ()):
                n = (ni, nj)
                if n not in dist and L.kind[ni][nj] != VENT:
                    dist[n] = dist[c] + 1
                    q.append(n)
        return dist

    # ------------------------------------------------------------------
    # PORTES : cadre épais, panneau de commande, plaque du nom, bandes de danger
    # ------------------------------------------------------------------
    def _door(self, door):
        L = self.L
        b = self.b
        ri, rj = door.room_cell
        oi, oj = door.out_cell
        room = L.rooms[L.room_of[ri][rj]] if L.room_of[ri][rj] >= 0 else None
        hw = C.DOOR_WIDTH / 2
        frame_col = (.2, .21, .23)
        for (ci, cj), (ni, nj), inside in (((ri, rj), (oi, oj), True), ((oi, oj), (ri, rj), False)):
            if not L.inside(ci, cj) or L.kind[ci][cj] == SOLID:
                continue
            g = b.group_for(ci, cj)
            nx, nz = ci - ni, cj - nj                 # normale du mur, vers la case (ci, cj)
            if door.axis == "x":
                wx, wz = door.line + nx * (C.WALL_T / 2 + .06), door.mid
                along = (0, 1)
            else:
                wx, wz = door.mid, door.line + nz * (C.WALL_T / 2 + .06)
                along = (1, 0)
            mb = g.b["painted"]
            # cadre épais : montants + linteau
            for s in (-1, 1):
                px, pz = wx + along[0] * s * (hw + .09), wz + along[1] * s * (hw + .09)
                size = (.12 if along[0] == 0 else .18, C.DOOR_HEIGHT + .1, .18 if along[0] == 0 else .12)
                mb.box((px, C.DOOR_HEIGHT / 2, pz), size, frame_col)
                # bande de danger sur le montant
                hz = g.b["hazard"]
                hs = (.13 if along[0] == 0 else .08, C.DOOR_HEIGHT * .9, .08 if along[0] == 0 else .13)
                hz.box((px + nx * .03, C.DOOR_HEIGHT * .47, pz + nz * .03), hs, (1, 1, 1))
            lsize = (.12 if along[0] == 0 else C.DOOR_WIDTH + .5, .16, C.DOOR_WIDTH + .5 if along[0] == 0 else .12)
            mb.box((wx, C.DOOR_HEIGHT + .08, wz), lsize, frame_col)
            # plaque antidérapante jaune et noir au sol, devant la porte
            fx, fz = wx + nx * .45, wz + nz * .45
            psize = (.7 if along[0] == 0 else C.DOOR_WIDTH + .3, .012, C.DOOR_WIDTH + .3 if along[0] == 0 else .7)
            g.b["hazard"].box((fx, .007, fz), psize, (.95, .95, .9), faces='t')
            # panneau de commande avec voyant (alimenté : éteint sans courant)
            s = 1 if (ci + cj) % 2 == 0 else -1
            px, pz = wx + along[0] * s * (hw + .45), wz + along[1] * s * (hw + .45)
            g.b["struct"].box((px + nx * .02, 1.3, pz + nz * .02),
                              (.06 if along[0] == 0 else .26, .36, .26 if along[0] == 0 else .06), (.15, .16, .17))
            g.b["emissive"].box((px + nx * .06, 1.4, pz + nz * .06), (.03, .05, .03), (.1, 1, .3))
            g.b["emissive"].box((px + nx * .06, 1.3, pz + nz * .06), (.03, .03, .03), (1, .5, .1))
            # plaque du nom de la salle au-dessus de la porte (des deux côtés), à côté du voyant
            if room is not None and room.type in textures.SIGN_TEXT:
                wall_quad(g.b["sign"], wx - along[0] * .22 + nx * .07, C.DOOR_HEIGHT + .26,
                          wz - along[1] * .22 + nz * .07, nx, nz, .9, .2, self.sign_uv(room.type))
            # panneau d'avertissement côté couloir : sur le mur qui fait face à la porte
            if not inside and room is not None:
                warn = {"medbay": "biohazard", "engine": "voltage", "command": "noentry",
                        "storage": "oxygen"}.get(room.type)
                if warn and L.edge_state(ci, cj, ci + nx, cj + nz) == "wall":
                    fx_, fz_, fnx, fnz = wall_face(L, ci, cj, nx, nz)
                    wall_quad(g.b["sign"], fx_, 1.7, fz_, fnx, fnz, 1.1, .27, self.sign_uv(warn))

    # ------------------------------------------------------------------
    # COULOIRS : grilles, numéros de section, évacuation, câbles, papiers
    # ------------------------------------------------------------------
    def _corridor(self, i, j):
        L = self.L
        b = self.b
        g = b.group_for(i, j)
        rng = self.rng
        Cc = C.CELL
        cx, cz = L.cell_center(i, j)
        walls = [(dx, dz) for dx, dz in DIRS if L.edge_state(i, j, i + dx, j + dz) == "wall"]
        ox = any(L.edge_state(i, j, i + d, j) in ("open", "door") for d in (-1, 1))
        oz = any(L.edge_state(i, j, i, j + d) in ("open", "door") for d in (-1, 1))
        axis = 'x' if (ox and not oz) else ('z' if (oz and not ox) else None)
        # grille de sol perforée au centre du couloir
        if axis and (i * 7 + j * 3) % 4 == 0:
            size = (Cc, .02, 1.1) if axis == 'x' else (1.1, .02, Cc)
            g.b["grate"].box((cx, .012, cz), size, (.85, .85, .85), faces='t')
            # colliers de fixation des tuyaux du plafond
            for k in (-.5, .5):
                if axis == 'x':
                    g.b["pipe"].box((cx + k, C.CORRIDOR_HEIGHT - .2, cz - .65), (.05, .2, .22), (.4, .4, .42))
                else:
                    g.b["pipe"].box((cx - .65, C.CORRIDOR_HEIGHT - .2, cz + k), (.22, .2, .05), (.4, .4, .42))
        # gaine de ventilation rectangulaire au plafond, avec ses nervures
        if axis and (i + j * 2) % 9 == 0:
            y = C.CORRIDOR_HEIGHT - .32
            off = .35 if (i + j) % 2 else -.35
            if axis == 'x':
                g.b["painted"].box((cx, y, cz + off), (Cc, .34, .5), (.42, .44, .46))
                for k in (-.8, 0, .8):
                    g.b["painted"].box((cx + k, y, cz + off), (.05, .38, .54), (.3, .31, .33))
            else:
                g.b["painted"].box((cx + off, y, cz), (.5, .34, Cc), (.42, .44, .46))
                for k in (-.8, 0, .8):
                    g.b["painted"].box((cx + off, y, cz + k), (.54, .38, .05), (.3, .31, .33))
        if not walls:
            return
        dx, dz = walls[(i + j) % len(walls)]
        wx, wz, nx, nz = wall_face(L, i, j, dx, dz)
        # numéro de section peint au pochoir
        if (i * 3 + j * 5) % 11 == 0:
            sec = 1 + ((i // 7) * 3 + (j // 7)) % 8
            wall_quad(g.b["sign"], wx, 1.95, wz, nx, nz, 1.2, .3, self.sign_uv(f"sec{sec}"))
        # flèche d'évacuation vers le hangar
        elif (i * 5 + j * 2) % 7 == 0 and (i, j) in self.evac_dist:
            d0 = self.evac_dist[(i, j)]
            best = None
            for ni, nj, st in L.links.get((i, j), ()):
                d1 = self.evac_dist.get((ni, nj))
                if d1 is not None and d1 < d0:
                    best = (ni - i, nj - j)
            if best is not None:
                tx, tz = -nz, nx
                right = best[0] * tx + best[1] * tz > 0
                wall_quad(g.b["sign"], wx, 1.35, wz, nx, nz, 1.0, .25,
                          self.sign_uv("evac_right" if right else "evac_left"))
        # câble qui pend en arc entre deux fixations
        if axis and rng.random() < .07:
            y = C.CORRIDOR_HEIGHT - .1
            if axis == 'x':
                a, c = (cx - Cc / 2, y, cz + rng.uniform(-.5, .5)), (cx + Cc / 2, y, cz + rng.uniform(-.5, .5))
            else:
                a, c = (cx + rng.uniform(-.5, .5), y, cz - Cc / 2), (cx + rng.uniform(-.5, .5), y, cz + Cc / 2)
            sag_cable(g.b["struct"], a, c, rng.uniform(.35, .9), .018, (.05, .05, .05))
        # papiers au sol
        if rng.random() < .1:
            self._papers(g, cx, cz, rng.randint(1, 3), .8)

    def _papers(self, g, cx, cz, n, spread):
        rng = self.rng
        for _ in range(n):
            x, z = cx + rng.uniform(-spread, spread), cz + rng.uniform(-spread, spread)
            shade = rng.uniform(.7, .88)
            g.b["struct"].box_rot((x, .004 + rng.uniform(0, .004), z), (.21, .003, .29), rng.uniform(0, 360),
                                  (shade, shade, shade * .96))

    # ------------------------------------------------------------------
    # SALLES
    # ------------------------------------------------------------------
    def _room_walls(self, room):
        """Faces de mur intérieures d'une salle : (i, j, dx, dz)."""
        L = self.L
        out = []
        for i, j in room.cells():
            for dx, dz in DIRS:
                if L.edge_state(i, j, i + dx, j + dz) == "wall":
                    out.append((i, j, dx, dz))
        return out

    def _room_common(self, room):
        """Poutres apparentes au plafond (sauf hangar et machines, qui ont les leurs)."""
        if room.type in ("hangar", "engine"):
            return
        g = self.b.groups[("room", room.id)]
        x0, x1, z0, z1 = room.world_bounds()
        h = room.height
        if room.w >= room.h:
            n = max(1, room.w // 2)
            for k in range(1, n):
                x = x0 + (x1 - x0) * k / n
                g.b["painted"].box((x, h - .12, (z0 + z1) / 2), (.22, .24, z1 - z0), (.3, .31, .33))
        else:
            n = max(1, room.h // 2)
            for k in range(1, n):
                z = z0 + (z1 - z0) * k / n
                g.b["painted"].box(((x0 + x1) / 2, h - .12, z), (x1 - x0, .24, .22), (.3, .31, .33))

    def _logo(self, room, y, w, h, prefer=None):
        """Logo Helios Biotech sur un mur de la salle."""
        L = self.L
        walls = self._room_walls(room)
        if not walls:
            return
        rng = self.rng
        i, j, dx, dz = prefer if prefer in walls else rng.choice(walls)
        g = self.b.group_for(i, j)
        wx, wz, nx, nz = wall_face(L, i, j, dx, dz)
        wall_quad(g.b["sign"], wx, y, wz, nx, nz, w, h, self.sign_uv("helios"))

    def _room_hangar(self, room):
        # grand logo Helios au fond du hangar
        walls = [w for w in self._room_walls(room) if w[3] == 1]
        if walls:
            w = sorted(walls, key=lambda s: abs(s[0] - (room.x + room.w / 2)))[0]
            self._logo(room, 5.2, 6.0, 1.5, prefer=w)

    def _room_medbay(self, room):
        """Infirmerie blanche et froide : habillage mural clair, carrelage au sol."""
        L = self.L
        for i, j, dx, dz in self._room_walls(room):
            g = self.b.group_for(i, j)
            wx, wz, nx, nz = wall_face(L, i, j, dx, dz)
            Cc = C.CELL
            size = (.03, 2.3, Cc - .02) if dx != 0 else (Cc - .02, 2.3, .03)
            g.b["struct"].box((wx + nx * .02, 1.15, wz + nz * .02), size, (.92, .95, .97))   # panneaux blancs
            # plinthe grise
            size = (.05, .12, Cc - .02) if dx != 0 else (Cc - .02, .12, .05)
            g.b["painted"].box((wx + nx * .04, .06, wz + nz * .04), size, (.45, .47, .5))
        g = self.b.groups[("room", room.id)]
        x0, x1, z0, z1 = room.world_bounds()
        # carrelage blanc (grandes dalles) avec joints
        tile = 1.25
        x = x0 + tile / 2
        while x < x1:
            z = z0 + tile / 2
            while z < z1:
                v = .74 + .06 * ((int(x / tile) + int(z / tile)) % 2)
                g.b["painted"].box((x, .006, z), (tile - .03, .01, tile - .03), (v, v + .02, v + .03), faces='t')
                z += tile
            x += tile
        # quelques compresses et papiers au sol
        cx, cz = room.world_center()
        self._papers(g, cx, cz, 4, 1.6)

    def _room_engine(self, room):
        """Salle des machines industrielle et chaude : gros tuyaux, colliers, vapeur, haute tension."""
        L = self.L
        rng = self.rng
        walls = self._room_walls(room)
        for n, (i, j, dx, dz) in enumerate(walls):
            g = self.b.group_for(i, j)
            wx, wz, nx, nz = wall_face(L, i, j, dx, dz)
            Cc = C.CELL
            ax = 'z' if dx != 0 else 'x'
            for k, (y, r, col) in enumerate(((3.6, .16, (.55, .32, .15)), (4.1, .11, (.42, .43, .45)))):
                px, pz = wx + nx * (r + .08), wz + nz * (r + .08)
                g.b["pipe"].cylinder((px, y, pz), r, Cc, col, 10, ax, caps=False)
                # collier de fixation
                cs = (.1, r * 2.6, r * 2.6) if ax == 'x' else (r * 2.6, r * 2.6, .1)
                g.b["struct"].box((px, y, pz), cs, (.25, .25, .27))
            if n % 5 == 0:
                wall_quad(g.b["sign"], wx, 2.2, wz, nx, nz, 1.0, .25, self.sign_uv("voltage"))
            if n % 7 == 3:
                # tuyau percé : de la vapeur s'échappe
                g_ = self.b.groups[("room", room.id)]
                sv = SteamVent(g_.root, (wx + nx * .3, 3.6, wz + nz * .3), (nx * .6, -.2, nz * .6), rng)
                self.b.updatables.append(sv)

    def _room_mess(self, room):
        """Salle à manger : lieu de la fusillade (impacts, douilles), chaises renversées, barricade."""
        L = self.L
        rng = self.rng
        g = self.b.groups[("room", room.id)]
        walls = self._room_walls(room)
        # impacts de balles sur les murs
        for _ in range(14):
            if not walls:
                break
            i, j, dx, dz = rng.choice(walls)
            gg = self.b.group_for(i, j)
            wx, wz, nx, nz = wall_face(L, i, j, dx, dz)
            tx, tz = -nz, nx
            u = rng.uniform(-1.0, 1.0)
            gg.b["decal"].decal((wx + tx * u + nx * .01, rng.uniform(.6, 2.0), wz + tz * u + nz * .01),
                                rng.uniform(.08, .14), rng.uniform(0, 360), (.08, .07, .07, .95), normal=(nx, 0, nz))
        # douilles au sol
        cx, cz = room.world_center()
        for _ in range(12):
            x, z = cx + rng.uniform(-2, 2), cz + rng.uniform(-1.5, 1.5)
            g.b["pipe"].cylinder((x, .012, z), .006, .025, (.75, .6, .25), 6, 'x' if rng.random() < .5 else 'z')
        # chaises renversées
        for _ in range(3):
            x, z = cx + rng.uniform(-2.2, 2.2), cz + rng.uniform(-1.6, 1.6)
            if L.blocked_point(x, .3, z, .3):
                continue
            yaw = rng.uniform(0, 360)
            g.b["struct"].box_rot((x, .22, z), (.42, .06, .42), yaw, (.32, .22, .15), pitch=80)
            g.b["struct"].box_rot((x, .05, z + .1), (.42, .08, .4), yaw, (.3, .2, .14), pitch=10)
        self._barricade(room)
        self._papers(g, cx, cz, 5, 2.0)
        self._logo(room, 2.3, 1.6, .4)

    def _room_crew(self, room):
        g = self.b.groups[("room", room.id)]
        cx, cz = room.world_center()
        self._papers(g, cx, cz, 3, 1.2)
        if self.rng.random() < .5:
            self._barricade(room)

    def _room_command(self, room):
        g = self.b.groups[("room", room.id)]
        cx, cz = room.world_center()
        self._papers(g, cx, cz, 6, 1.8)
        self._logo(room, 2.6, 1.8, .45)

    def _barricade(self, room):
        """Barricade de fortune (table renversée + caisse) à côté d'une porte, sans bloquer le passage."""
        L = self.L
        b = self.b
        rng = self.rng
        if not room.doors:
            return
        door = rng.choice(room.doors)
        ri, rj = door.room_cell
        oi, oj = door.out_cell
        nx, nz = ri - oi, rj - oj
        along = (0, 1) if door.axis == "x" else (1, 0)
        s = rng.choice((-1, 1))
        dxw, dzw = door.pos
        x = dxw + nx * .7 + along[0] * s * (C.DOOR_WIDTH / 2 + .75)
        z = dzw + nz * .7 + along[1] * s * (C.DOOR_WIDTH / 2 + .75)
        if L.room_at(x, z) is not room or L.blocked_point(x, .4, z, .35):
            return
        g = b.group_for(*L.cell_at(x, z))
        yaw = math.degrees(math.atan2(nx, nz))
        # table sur la tranche, plateau face à la porte
        g.b["struct"].box_rot((x, .45, z), (1.2, .9, .06), yaw + 90 * along[0], (.35, .33, .3))
        g.b["struct"].box_rot((x + nx * .3, .25, z + nz * .3), (.06, .06, .5), yaw, (.25, .25, .27), pitch=90)
        # caisse contre la table
        g.b["struct"].box_rot((x + nx * .45, .3, z + nz * .45), (.55, .6, .5), yaw + rng.uniform(-15, 15),
                              (.3, .31, .26))
        b.block(x - .6, x + .6, z - .6, z + .6, 1.0)

    # ------------------------------------------------------------------
    def _wall_messages(self):
        """Quelques messages écrits sur les murs (salles et couloirs) — horreur suggestive."""
        L = self.L
        rng = self.rng
        cands = []
        for room in L.rooms:
            if room.type in ("mess", "crew", "storage", "medbay"):
                cands += [(w, room) for w in self._room_walls(room)]
        rng.shuffle(cands)
        used = set()
        n = 0
        for (i, j, dx, dz), room in cands:
            if room.id in used:
                continue
            used.add(room.id)
            g = self.b.group_for(i, j)
            wx, wz, nx, nz = wall_face(L, i, j, dx, dz)
            wall_quad(g.b["sign"], wx + nx * .005, 1.55, wz + nz * .005, nx, nz, 2.2, .55,
                      self.sign_uv(f"msg{n % len(textures.WALL_MESSAGES)}"))
            n += 1
            if n >= 4:
                break
