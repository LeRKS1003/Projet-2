# -*- coding: utf-8 -*-
"""
geometry.py — Construction de meshes statiques fusionnés.

Plutôt que de créer des milliers d'entités Ursina (une par cube), on
accumule directement les sommets, normales, couleurs et UV dans des listes
plates, puis on génère UN seul Mesh par salle / par bloc de couloir.
C'est la clé pour tenir 60 FPS : quelques dizaines de draw calls au lieu
de plusieurs milliers.

Les meshes sont construits directement en Panda3D (GeomVertexData) avec
normales, couleurs, UV, TANGENTES et BINORMALES calculées par numpy : c'est
indispensable pour que le shader automatique de Panda3D applique les
normal maps (reliefs, rivets, jointures) et les cartes de brillance.
"""
import math
import random

import numpy as np
from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData,
                          GeomVertexFormat, InternalName)
from ursina import Entity


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
    def poly(self, pts, normal, col, uv=None):
        """
        Polygone convexe quelconque. L'ordre des sommets est corrigé
        automatiquement pour que la face soit visible du côté de la normale.
        UV : projection planaire sur l'axe dominant si non fournies.
        """
        n = len(pts)
        if n < 3:
            return
        p0, p1, p2 = pts[0], pts[1], pts[2]
        e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        # repère main gauche : la face visible a un produit vectoriel opposé à la normale
        if cr[0] * normal[0] + cr[1] * normal[1] + cr[2] * normal[2] > 0:
            pts = list(reversed(pts))
            if uv is not None:
                uv = list(reversed(uv))
        if uv is None:
            ax = max(range(3), key=lambda k: abs(normal[k]))
            a, b = [(1, 2), (0, 2), (0, 1)][ax]
            us = self.uv_scale
            uv = [(p[a] / us, p[b] / us) for p in pts]
        cc = _c(col)
        b0 = self.count
        for p, u in zip(pts, uv):
            self.v.extend((p[0], p[1], p[2]))
            self.n.extend(normal)
            self.c.extend(cc)
            self.t.extend(u)
        for k in range(1, n - 1):
            self.i.extend((b0, b0 + k, b0 + k + 1))
        self.count += n

    def bevel_box(self, center, size, bevel, col, edge_col=None, rot=(0, 0, 0), faces_col=None):
        """
        Boîte chanfreinée (arêtes biseautées) : 6 faces, 12 biseaux, 8 coins.
        edge_col : couleur des biseaux (ex. métal plus clair = usure des arêtes).
        rot : (tangage, lacet, roulis) en degrés, autour du centre.
        faces_col : dict optionnel {'+x': couleur, ...} pour teinter une face.
        """
        cx, cy, cz = center
        h = (size[0] * .5, size[1] * .5, size[2] * .5)
        b = min(bevel, h[0] * .9, h[1] * .9, h[2] * .9)
        ec = edge_col if edge_col is not None else col
        R = _rot_matrix(*rot)

        def T(p):
            x, y, z = p
            return (cx + R[0][0] * x + R[0][1] * y + R[0][2] * z,
                    cy + R[1][0] * x + R[1][1] * y + R[1][2] * z,
                    cz + R[2][0] * x + R[2][1] * y + R[2][2] * z)

        def TN(nv):
            x, y, z = nv
            v = (R[0][0] * x + R[0][1] * y + R[0][2] * z, R[1][0] * x + R[1][1] * y + R[1][2] * z,
                 R[2][0] * x + R[2][1] * y + R[2][2] * z)
            l = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1
            return (v[0] / l, v[1] / l, v[2] / l)

        def pt(ax, s, u_ax, su, v_ax, sv, inset_u, inset_v):
            p = [0.0, 0.0, 0.0]
            p[ax] = s * h[ax]
            p[u_ax] = su * (h[u_ax] - inset_u)
            p[v_ax] = sv * (h[v_ax] - inset_v)
            return p

        names = {0: 'x', 1: 'y', 2: 'z'}
        # faces principales
        for ax in range(3):
            u_ax, v_ax = [a for a in range(3) if a != ax]
            for s in (-1, 1):
                pts = [pt(ax, s, u_ax, su, v_ax, sv, b, b) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                nv = [0, 0, 0]
                nv[ax] = s
                c = col
                if faces_col:
                    c = faces_col.get(('+' if s > 0 else '-') + names[ax], col)
                self.poly([T(p) for p in pts], TN(nv), c, self._uv_for(pts, ax))
        # biseaux des arêtes (entre deux faces)
        for a1 in range(3):
            for a2 in range(a1 + 1, 3):
                a3 = 3 - a1 - a2
                for s1 in (-1, 1):
                    for s2 in (-1, 1):
                        pts = []
                        for s3 in (-1, 1):
                            p = [0.0, 0.0, 0.0]
                            p[a1], p[a2], p[a3] = s1 * h[a1], s2 * (h[a2] - b), s3 * (h[a3] - b)
                            q = [0.0, 0.0, 0.0]
                            q[a1], q[a2], q[a3] = s1 * (h[a1] - b), s2 * h[a2], s3 * (h[a3] - b)
                            pts.append((p, q))
                        quad = [pts[0][0], pts[1][0], pts[1][1], pts[0][1]]
                        nv = [0, 0, 0]
                        nv[a1], nv[a2] = s1, s2
                        self.poly([T(p) for p in quad], TN(nv), ec, self._uv_for(quad, a3, True))
        # coins (triangles)
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    s = (sx, sy, sz)
                    tri = []
                    for ax in range(3):
                        p = [s[k] * (h[k] - b) for k in range(3)]
                        p[ax] = s[ax] * h[ax]
                        tri.append(p)
                    self.poly([T(p) for p in tri], TN(s), ec, [(0, 0), (.1, 0), (0, .1)])

    def _uv_for(self, pts, ax, edge=False):
        a, bb = [(1, 2), (0, 2), (0, 1)][ax] if not edge else [(1, 2), (0, 2), (0, 1)][ax]
        us = self.uv_scale
        return [(p[a] / us, p[bb] / us) for p in pts]

    def loft(self, sections, col, cap_start=True, cap_end=True, uv_len=None, perimeter_uv=True,
             colors=None):
        """
        Surface extrudée le long de l'axe Z à partir de sections octogonales
        (fuselages, nacelles). sections : liste de (z, cx, cy, largeur, hauteur,
        chanfrein). Normales plates par facette (aspect industriel usiné).
        UV : u = position le long de la longueur (0..1), v = tour de section (0..1),
        départ en bas au centre, puis côté +x, dessus, côté -x.
        colors : fonction optionnelle (i_section, i_facette) -> couleur.
        """
        rings = []
        for (z, cx, cy, w, hh, bv) in sections:
            hw, hh2 = w / 2, hh / 2
            bv = min(bv, hw * .95, hh2 * .95)
            # 8 points : bas-centre -> sens vers +x -> haut -> -x
            ring = [(cx, cy - hh2, z), (cx + hw - bv, cy - hh2, z), (cx + hw, cy - hh2 + bv, z),
                    (cx + hw, cy + hh2 - bv, z), (cx + hw - bv, cy + hh2, z), (cx - hw + bv, cy + hh2, z),
                    (cx - hw, cy + hh2 - bv, z), (cx - hw, cy - hh2 + bv, z), (cx - hw + bv, cy - hh2, z)]
            rings.append(ring)
        z0 = sections[0][0]
        z1 = sections[-1][0]
        L = (z1 - z0) or 1
        per = []
        r0 = rings[0]
        tot = 0.0
        acc = [0.0]
        for k in range(len(r0)):
            p, q = r0[k], r0[(k + 1) % len(r0)]
            tot += math.dist(p, q)
            acc.append(tot)
        per = [a / tot for a in acc]
        n = len(r0)
        for si in range(len(rings) - 1):
            ra, rb = rings[si], rings[si + 1]
            ua = (sections[si][0] - z0) / L
            ub = (sections[si + 1][0] - z0) / L
            for k in range(n):
                k2 = (k + 1) % n
                a0, a1, b1, b0 = ra[k], ra[k2], rb[k2], rb[k]
                # normale de facette (orientée vers l'extérieur de la section)
                e1 = np.subtract(b0, a0)
                e2 = np.subtract(a1, a0)
                nv = np.cross(e2, e1)
                mid = np.mean([a0, a1, b1, b0], axis=0)
                center = ((sections[si][1] + sections[si + 1][1]) / 2, (sections[si][2] + sections[si + 1][2]) / 2)
                out = (mid[0] - center[0], mid[1] - center[1], 0)
                if nv[0] * out[0] + nv[1] * out[1] < 0:
                    nv = -nv
                ln = np.linalg.norm(nv)
                if ln < 1e-9:
                    continue
                nv = tuple(nv / ln)
                va, vb = per[k], per[k + 1]
                c = colors(si, k) if colors else col
                self.poly([a0, a1, b1, b0], nv, c, [(ua, va), (ua, vb), (ub, vb), (ub, va)])
        if cap_start:
            self.poly(list(rings[0]), (0, 0, -1), col, [(0, .5)] * n)
        if cap_end:
            self.poly(list(rings[-1]), (0, 0, 1), col, [(1, .5)] * n)

    def cone(self, base_center, radius, length, col_base, col_tip, segments=14, axis_dir=(0, 0, -1)):
        """Cône (flammes de réacteur) : couleur dégradée base -> pointe (alpha compris)."""
        bx, by, bz = base_center
        dx, dy, dz = axis_dir
        tip = (bx + dx * length, by + dy * length, bz + dz * length)
        cb, ct = _c(col_base), _c(col_tip)
        for k in range(segments):
            a0 = 2 * math.pi * k / segments
            a1 = 2 * math.pi * (k + 1) / segments
            p0 = (bx + math.cos(a0) * radius, by + math.sin(a0) * radius, bz)
            p1 = (bx + math.cos(a1) * radius, by + math.sin(a1) * radius, bz)
            nm = (math.cos((a0 + a1) / 2), math.sin((a0 + a1) / 2), 0)
            b0 = self.count
            for p, c in ((p0, cb), (p1, cb), (tip, ct)):
                self.v.extend(p)
                self.n.extend(nm)
                self.c.extend(c)
                self.t.extend((0, 0))
            self.i.extend((b0, b0 + 1, b0 + 2))
            self.count += 3

    # ------------------------------------------------------------------
    def is_empty(self):
        return self.count == 0

    def make_geom_node(self, name='mesh', tangents=True):
        """GeomNode Panda3D (sommets entrelacés + tangentes/binormales)."""
        n = self.count
        V = np.asarray(self.v, np.float32).reshape(n, 3)
        N = np.asarray(self.n, np.float32).reshape(n, 3)
        Cc = np.asarray(self.c, np.float32).reshape(n, 4)
        U = np.asarray(self.t, np.float32).reshape(n, 2)
        I = np.asarray(self.i, np.uint32)
        arr = GeomVertexArrayFormat()
        arr.addColumn(InternalName.getVertex(), 3, Geom.NT_float32, Geom.C_point)
        arr.addColumn(InternalName.getNormal(), 3, Geom.NT_float32, Geom.C_normal)
        arr.addColumn(InternalName.getColor(), 4, Geom.NT_float32, Geom.C_color)
        arr.addColumn(InternalName.getTexcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
        cols = [V, N, Cc, U]
        if tangents:
            T, B = _tangents(V, N, U, I)
            arr.addColumn(InternalName.getTangent(), 3, Geom.NT_float32, Geom.C_vector)
            arr.addColumn(InternalName.getBinormal(), 3, Geom.NT_float32, Geom.C_vector)
            cols += [T, B]
        fmt = GeomVertexFormat.registerFormat(GeomVertexFormat(arr))
        vdata = GeomVertexData(name, fmt, Geom.UHStatic)
        vdata.uncleanSetNumRows(n)
        data = np.ascontiguousarray(np.hstack(cols).astype(np.float32))
        handle = vdata.modifyArray(0)
        stride = fmt.getArray(0).getStride()
        if stride != data.shape[1] * 4:   # sécurité (alignement éventuel)
            pad = np.zeros((n, stride // 4 - data.shape[1]), np.float32)
            data = np.ascontiguousarray(np.hstack([data, pad]))
        memoryview(handle).cast('B')[:] = data.tobytes()
        prim = GeomTriangles(Geom.UHStatic)
        prim.setIndexType(Geom.NT_uint32)
        prim.modifyVertices().uncleanSetNumRows(len(I))
        memoryview(prim.modifyVertices()).cast('B')[:] = I.tobytes()
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode(name)
        node.addGeom(geom)
        return node

    def build(self, parent=None, texture=None, name='mesh', unlit=False, material=None, tangents=True, **kwargs):
        """
        Crée l'entité Ursina contenant le mesh fusionné.
        texture : Texture Ursina (albédo) ; material : nom d'un matériau de
        textures.py (albédo + normal map + brillance + spéculaire).
        """
        e = Entity(parent=parent, name=name, **kwargs)
        if self.count == 0:
            return e
        np_ = e.attachNewNode(self.make_geom_node(name, tangents))
        e.geom_np = np_
        if material is not None:
            import textures
            textures.apply_material(np_, material, albedo=texture)
        elif texture is not None:
            np_.setTexture(texture._texture if hasattr(texture, '_texture') else texture)
        if unlit:
            e.setLightOff(1)
        return e


def _rot_matrix(pitch, yaw, roll):
    """Matrice de rotation (convention Ursina : tangage X, lacet Y, roulis Z, repère main gauche)."""
    p, y, r = math.radians(pitch), math.radians(yaw), math.radians(roll)
    cp, sp, cy, sy, cr, sr = math.cos(p), math.sin(p), math.cos(y), math.sin(y), math.cos(r), math.sin(r)
    # roulis autour de Z, puis tangage autour de X, puis lacet autour de Y
    Rz = ((cr, sr, 0), (-sr, cr, 0), (0, 0, 1))
    Rx = ((1, 0, 0), (0, cp, -sp), (0, sp, cp))
    Ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))

    def mul(A, B):
        return tuple(tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(Ry, mul(Rx, Rz))


def _tangents(V, N, U, I):
    """Tangentes / binormales par sommet à partir des gradients d'UV (numpy)."""
    n = len(V)
    T = np.zeros((n, 3), np.float64)
    B = np.zeros((n, 3), np.float64)
    tri = I.reshape(-1, 3)
    i0, i1, i2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1 = V[i1] - V[i0]
    e2 = V[i2] - V[i0]
    d1 = U[i1] - U[i0]
    d2 = U[i2] - U[i0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    r = (1.0 / det)[:, None]
    t = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r
    b = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r
    for idx in (i0, i1, i2):
        np.add.at(T, idx, t)
        np.add.at(B, idx, b)
    Nn = N.astype(np.float64)
    # Gram-Schmidt : tangente perpendiculaire à la normale
    T -= Nn * np.sum(Nn * T, axis=1, keepdims=True)
    lt = np.linalg.norm(T, axis=1, keepdims=True)
    fallback = np.cross(Nn, np.array([0, 1, 0.0001]))
    T = np.where(lt < 1e-8, fallback, T / np.maximum(lt, 1e-8))
    B -= Nn * np.sum(Nn * B, axis=1, keepdims=True) + T * np.sum(T * B, axis=1, keepdims=True)
    lb = np.linalg.norm(B, axis=1, keepdims=True)
    B = np.where(lb < 1e-8, np.cross(Nn, T), B / np.maximum(lb, 1e-8))
    return T.astype(np.float32), B.astype(np.float32)


def jitter_color(col, amount=.06, rng=random):
    """Petite variation aléatoire de teinte pour casser la monotonie."""
    c = _c(col)
    k = 1 + rng.uniform(-amount, amount)
    return (min(1, c[0] * k), min(1, c[1] * k), min(1, c[2] * k), c[3])
