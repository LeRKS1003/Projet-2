# -*- coding: utf-8 -*-
"""
geometry.py — Construction de meshes statiques fusionnés.

Plutôt que de créer des milliers d'entités Ursina (une par cube), on
accumule directement les sommets, normales, couleurs et UV dans des listes
plates, puis on génère UN seul Mesh par salle / par bloc de couloir.
C'est la clé pour tenir 60 FPS : quelques dizaines de draw calls au lieu
de plusieurs milliers.
"""
import math
import random

from ursina import Entity, Mesh


def _c(col):
    """Convertit une couleur Ursina (ou un tuple) en tuple RGBA flottant."""
    if hasattr(col, 'r') and hasattr(col, 'a'):
        return (col.r, col.g, col.b, col.a)
    if len(col) == 3:
        return (col[0], col[1], col[2], 1.0)
    return tuple(col)


class MeshBuilder:
    """Accumulateur de géométrie. uv_scale = mètres par répétition de texture."""

    def __init__(self, uv_scale=2.0):
        self.v = []      # positions (x, y, z) à plat
        self.n = []      # normales à plat
        self.c = []      # couleurs RGBA à plat
        self.t = []      # UV à plat
        self.i = []      # indices de triangles
        self.count = 0
        self.uv_scale = uv_scale

    # ------------------------------------------------------------------
    def quad(self, p0, p1, p2, p3, normal, col, uv=None):
        """Ajoute un quadrilatère (p0..p3 dans le sens anti-horaire vu de face)."""
        cc = _c(col)
        for p in (p0, p1, p2, p3):
            self.v.extend((p[0], p[1], p[2]))
            self.n.extend(normal)
            self.c.extend(cc)
        if uv is None:
            uv = ((0, 0), (1, 0), (1, 1), (0, 1))
        for u in uv:
            self.t.extend(u)
        b = self.count
        # Ursina est en repère main gauche (y-up-left) : avec cet ordre, la
        # face est visible du côté où pointe la normale fournie.
        self.i.extend((b, b + 1, b + 2, b, b + 2, b + 3))
        self.count += 4

    # ------------------------------------------------------------------
    def box(self, center, size, col, faces='all', shade=True):
        """
        Ajoute une boîte alignée sur les axes.
        faces : 'all' ou chaîne contenant les lettres des faces voulues
        (t=top, b=bottom, n=nord +z, s=sud -z, e=est +x, w=ouest -x).
        shade : légère variation de teinte par face (donne du relief même
        sans lumière).
        """
        cx, cy, cz = center
        sx, sy, sz = size[0] * .5, size[1] * .5, size[2] * .5
        x0, x1 = cx - sx, cx + sx
        y0, y1 = cy - sy, cy + sy
        z0, z1 = cz - sz, cz + sz
        cc = _c(col)
        us = self.uv_scale

        def tint(k):
            if not shade:
                return cc
            return (cc[0] * k, cc[1] * k, cc[2] * k, cc[3])

        if faces == 'all':
            faces = 'tbnsew'
        # UV projetées en coordonnées monde : les textures ne s'étirent pas
        if 't' in faces:
            self.quad((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), (0, 1, 0), tint(1.0),
                      ((x0 / us, z0 / us), (x1 / us, z0 / us), (x1 / us, z1 / us), (x0 / us, z1 / us)))
        if 'b' in faces:
            self.quad((x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0), (0, -1, 0), tint(.7),
                      ((x0 / us, z1 / us), (x1 / us, z1 / us), (x1 / us, z0 / us), (x0 / us, z0 / us)))
        if 's' in faces:  # face -z
            self.quad((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (0, 0, -1), tint(.9),
                      ((x0 / us, y0 / us), (x1 / us, y0 / us), (x1 / us, y1 / us), (x0 / us, y1 / us)))
        if 'n' in faces:  # face +z
            self.quad((x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (0, 0, 1), tint(.85),
                      ((x1 / us, y0 / us), (x0 / us, y0 / us), (x0 / us, y1 / us), (x1 / us, y1 / us)))
        if 'e' in faces:  # face +x
            self.quad((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0), (1, 0, 0), tint(.8),
                      ((z0 / us, y0 / us), (z1 / us, y0 / us), (z1 / us, y1 / us), (z0 / us, y1 / us)))
        if 'w' in faces:  # face -x
            self.quad((x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (-1, 0, 0), tint(.75),
                      ((z1 / us, y0 / us), (z0 / us, y0 / us), (z0 / us, y1 / us), (z1 / us, y1 / us)))

    # ------------------------------------------------------------------
    def box_rot(self, center, size, yaw, col, pitch=0.0):
        """Boîte orientée (lacet 'yaw' en degrés autour de Y, tangage optionnel autour de X local)."""
        cx, cy, cz = center
        sx, sy, sz = size[0] * .5, size[1] * .5, size[2] * .5
        a = math.radians(yaw)
        ca, sa = math.cos(a), math.sin(a)
        p = math.radians(pitch)
        cp, sp = math.cos(p), math.sin(p)
        cc = _c(col)

        def T(x, y, z):
            # tangage autour de X local puis lacet autour de Y (repère main gauche)
            y2 = y * cp - z * sp
            z2 = y * sp + z * cp
            return (cx + x * ca + z2 * sa, cy + y2, cz - x * sa + z2 * ca)

        def N(x, y, z):
            y2 = y * cp - z * sp
            z2 = y * sp + z * cp
            return (x * ca + z2 * sa, y2, -x * sa + z2 * ca)

        faces = (
            (((-sx, sy, -sz), (sx, sy, -sz), (sx, sy, sz), (-sx, sy, sz)), (0, 1, 0), 1.0),
            (((-sx, -sy, sz), (sx, -sy, sz), (sx, -sy, -sz), (-sx, -sy, -sz)), (0, -1, 0), .7),
            (((-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz)), (0, 0, -1), .9),
            (((sx, -sy, sz), (-sx, -sy, sz), (-sx, sy, sz), (sx, sy, sz)), (0, 0, 1), .85),
            (((sx, -sy, -sz), (sx, -sy, sz), (sx, sy, sz), (sx, sy, -sz)), (1, 0, 0), .8),
            (((-sx, -sy, sz), (-sx, -sy, -sz), (-sx, sy, -sz), (-sx, sy, sz)), (-1, 0, 0), .75),
        )
        for pts, n, k in faces:
            q = [T(*pt) for pt in pts]
            self.quad(q[0], q[1], q[2], q[3], N(*n), (cc[0] * k, cc[1] * k, cc[2] * k, cc[3]))

    def decal(self, center, size, yaw, col, normal=(0, 1, 0)):
        """Quad plaqué (sang, traces) : au sol si normal=(0,1,0), sinon sur un mur."""
        cx, cy, cz = center
        h = size * .5
        a = math.radians(yaw)
        ca, sa = math.cos(a), math.sin(a)
        if normal == (0, 1, 0):
            pts = [(-h, -h), (h, -h), (h, h), (-h, h)]
            q = [(cx + x * ca + z * sa, cy, cz - x * sa + z * ca) for x, z in pts]
        else:
            nx, _, nz = normal
            # tangente horizontale du mur (repère main gauche)
            tx, tz = -nz, nx
            q = []
            for u, v in [(-h, -h), (h, -h), (h, h), (-h, h)]:
                uu = u * ca - v * sa
                vv = u * sa + v * ca
                q.append((cx + tx * uu, cy + vv, cz + tz * uu))
        self.quad(q[0], q[1], q[2], q[3], normal, col)

    # ------------------------------------------------------------------
    def cylinder(self, center, radius, height, col, segments=10, axis='y', caps=True):
        """Cylindre (tuyaux, réacteur, bouteilles...). axis = 'x', 'y' ou 'z'."""
        cx, cy, cz = center
        cc = _c(col)
        h = height * .5

        def P(a, d):
            # a = angle, d = position le long de l'axe
            ca, sa = math.cos(a) * radius, math.sin(a) * radius
            if axis == 'y':
                return (cx + ca, cy + d, cz + sa), (math.cos(a), 0, math.sin(a))
            if axis == 'x':
                return (cx + d, cy + ca, cz + sa), (0, math.cos(a), math.sin(a))
            return (cx + ca, cy + sa, cz + d), (math.cos(a), math.sin(a), 0)

        for k in range(segments):
            a0 = 2 * math.pi * k / segments
            a1 = 2 * math.pi * (k + 1) / segments
            p00, n0 = P(a0, -h)
            p10, n1 = P(a1, -h)
            p11, _ = P(a1, h)
            p01, _ = P(a0, h)
            b = self.count
            for p, nn in ((p00, n0), (p10, n1), (p11, n1), (p01, n0)):
                self.v.extend(p)
                self.n.extend(nn)
                self.c.extend(cc)
            self.t.extend((k / segments, 0, (k + 1) / segments, 0, (k + 1) / segments, 1, k / segments, 1))
            # orientation dépendante de l'axe (repère main gauche)
            if axis != 'y':
                self.i.extend((b, b + 2, b + 1, b, b + 3, b + 2))
            else:
                self.i.extend((b, b + 1, b + 2, b, b + 2, b + 3))
            self.count += 4
        if caps:
            for d, sgn in ((h, 1), (-h, -1)):
                pc, _ = P(0, d)
                if axis == 'y':
                    pc = (cx, cy + d, cz)
                    nn = (0, sgn, 0)
                elif axis == 'x':
                    pc = (cx + d, cy, cz)
                    nn = (sgn, 0, 0)
                else:
                    pc = (cx, cy, cz + d)
                    nn = (0, 0, sgn)
                base = self.count
                self.v.extend(pc)
                self.n.extend(nn)
                self.c.extend(cc)
                self.t.extend((.5, .5))
                self.count += 1
                for k in range(segments):
                    a = 2 * math.pi * k / segments
                    p, _ = P(a, d)
                    self.v.extend(p)
                    self.n.extend(nn)
                    self.c.extend(cc)
                    self.t.extend((.5 + .5 * math.cos(a), .5 + .5 * math.sin(a)))
                    self.count += 1
                for k in range(segments):
                    i0 = base + 1 + k
                    i1 = base + 1 + (k + 1) % segments
                    if (axis == 'y') == (sgn > 0):
                        self.i.extend((base, i0, i1))
                    else:
                        self.i.extend((base, i1, i0))

    # ------------------------------------------------------------------
    def is_empty(self):
        return self.count == 0

    def build(self, parent=None, texture=None, name='mesh', unlit=False, **kwargs):
        """Crée l'entité Ursina contenant le mesh fusionné."""
        if self.count == 0:
            return Entity(parent=parent, name=name)
        m = Mesh(vertices=self.v, triangles=self.i, normals=self.n,
                 colors=self.c, uvs=self.t, static=True, mode='triangle')
        e = Entity(parent=parent, model=m, texture=texture, name=name, **kwargs)
        if unlit:
            e.setLightOff()
        return e


def jitter_color(col, amount=.06, rng=random):
    """Petite variation aléatoire de teinte pour casser la monotonie."""
    c = _c(col)
    k = 1 + rng.uniform(-amount, amount)
    return (min(1, c[0] * k), min(1, c[1] * k), min(1, c[2] * k), c[3])
