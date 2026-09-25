# -*- coding: utf-8 -*-
"""
geometry.py — Outils de géométrie et de textures procédurales.

* MeshBuilder : accumule des quads, boîtes, cylindres et sphères dans un seul
  tampon de sommets, puis crée UN nœud Panda3D (équivalent rapide de
  Entity.combine(), mais qui conserve les normales pour l'éclairage).
* Fonctions de bruit périodique (numpy) et génération des textures du jeu.
"""
import math

import numpy as np
from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat,
                          GeomVertexData, GeomVertexFormat, InternalName,
                          SamplerState, Texture as PandaTexture)

# ---------------------------------------------------------------------------
# Format de sommet : position, normale, couleur (float), coordonnées de texture
# ---------------------------------------------------------------------------
_fmt_tableau = GeomVertexArrayFormat()
_fmt_tableau.addColumn(InternalName.getVertex(), 3, Geom.NTFloat32, Geom.CPoint)
_fmt_tableau.addColumn(InternalName.getNormal(), 3, Geom.NTFloat32, Geom.CNormal)
_fmt_tableau.addColumn(InternalName.getColor(), 4, Geom.NTFloat32, Geom.CColor)
_fmt_tableau.addColumn(InternalName.getTexcoord(), 2, Geom.NTFloat32, Geom.CTexcoord)
FORMAT_SOMMETS = GeomVertexFormat.registerFormat(GeomVertexFormat(_fmt_tableau))

HAUT = (0.0, 1.0, 0.0)


def _croix(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def matrice_rotation(rx=0.0, ry=0.0, rz=0.0):
    """Matrice 3x3 (liste de lignes) pour des angles d'Euler en degrés (ordre Y, X, Z)."""
    cx, sx = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    cy, sy = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz, sz = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return my @ mx @ mz


class MeshBuilder:
    """Accumule de la géométrie statique puis la fusionne en un seul Geom."""

    def __init__(self, echelle_uv=0.5):
        self.sommets = []       # liste plate de flottants (12 par sommet)
        self.indices = []
        self.n = 0
        self.echelle_uv = echelle_uv

    def vide(self):
        return self.n == 0

    # -- primitive de base ---------------------------------------------------
    def quad(self, p0, p1, p2, p3, normale, couleur, uvs=None):
        """Quad dont les sommets sont donnés dans le sens anti-horaire vus depuis la normale."""
        if uvs is None:
            uvs = self._uv_monde((p0, p1, p2, p3), normale)
        r, g, b, a = couleur if len(couleur) == 4 else (*couleur, 1.0)
        nx, ny, nz = normale
        for p, uv in zip((p0, p1, p2, p3), uvs):
            self.sommets.extend((p[0], p[1], p[2], nx, ny, nz, r, g, b, a, uv[0], uv[1]))
        n = self.n
        self.indices.extend((n, n + 1, n + 2, n + 2, n + 3, n))
        self.n += 4

    def quad_auto(self, p0, p1, p2, p3, normale, couleur, uvs=None):
        """Comme quad(), mais corrige automatiquement l'ordre des sommets selon la normale."""
        if _sens_ok(p0, p1, p2, normale):
            self.quad(p0, p1, p2, p3, normale, couleur, uvs)
        else:
            self.quad(p0, p3, p2, p1, normale, couleur, None if uvs is None else (uvs[0], uvs[3], uvs[2], uvs[1]))

    def _uv_monde(self, pts, normale):
        """Coordonnées de texture calculées depuis la position dans le monde (textures continues)."""
        e = self.echelle_uv
        if abs(normale[1]) > 0.7:
            return [(p[0] * e, p[2] * e) for p in pts]
        droite = _croix(normale, HAUT)
        return [((p[0] * droite[0] + p[2] * droite[2]) * e, p[1] * e) for p in pts]

    def rect(self, centre, normale, haut, largeur, hauteur, couleur, uvs=None):
        """Rectangle centré, orienté par sa normale et son vecteur « haut »."""
        d = _croix(normale, haut)
        hw, hh = largeur * 0.5, hauteur * 0.5
        c = centre
        p0 = (c[0] - d[0] * hw - haut[0] * hh, c[1] - d[1] * hw - haut[1] * hh, c[2] - d[2] * hw - haut[2] * hh)
        p1 = (c[0] + d[0] * hw - haut[0] * hh, c[1] + d[1] * hw - haut[1] * hh, c[2] + d[2] * hw - haut[2] * hh)
        p2 = (c[0] + d[0] * hw + haut[0] * hh, c[1] + d[1] * hw + haut[1] * hh, c[2] + d[2] * hw + haut[2] * hh)
        p3 = (c[0] - d[0] * hw + haut[0] * hh, c[1] - d[1] * hw + haut[1] * hh, c[2] - d[2] * hw + haut[2] * hh)
        self.quad(p0, p1, p2, p3, normale, couleur, uvs)

    # -- faces de la grille -------------------------------------------------
    def sol(self, x0, z0, x1, z1, y, couleur, plafond=False):
        """Rectangle horizontal : sol (normale vers le haut) ou plafond (normale vers le bas)."""
        if not plafond:
            self.quad((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1), (0, 1, 0), couleur)
        else:
            self.quad((x1, y, z0), (x0, y, z0), (x0, y, z1), (x1, y, z1), (0, -1, 0), couleur)

    def mur(self, ax, az, bx, bz, y0, y1, couleur):
        """Mur vertical du point A au point B (vu de face, A à gauche, B à droite)."""
        if y1 - y0 <= 1e-4:
            return
        self.quad((ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az), _normale_mur(ax, az, bx, bz), couleur)

    # -- volumes --------------------------------------------------------------
    def boite(self, centre, taille, couleur, rot=None, uv_local=True):
        """Pavé centré en `centre`, de dimensions `taille`, avec rotation optionnelle (rx, ry, rz)."""
        sx, sy, sz = taille[0] * 0.5, taille[1] * 0.5, taille[2] * 0.5
        m = matrice_rotation(*rot) if rot else None
        faces = (
            ((1, 0, 0), (0, 1, 0), sz * 2, sy * 2, sx),
            ((-1, 0, 0), (0, 1, 0), sz * 2, sy * 2, sx),
            ((0, 0, 1), (0, 1, 0), sx * 2, sy * 2, sz),
            ((0, 0, -1), (0, 1, 0), sx * 2, sy * 2, sz),
            ((0, 1, 0), (0, 0, 1), sx * 2, sz * 2, sy),
            ((0, -1, 0), (0, 0, 1), sx * 2, sz * 2, sy),
        )
        for n, h, lw, lh, dist in faces:
            d = _croix(n, h)
            hw, hh = lw * 0.5, lh * 0.5
            pts = []
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = (n[0] * dist + d[0] * hw * su + h[0] * hh * sv,
                     n[1] * dist + d[1] * hw * su + h[1] * hh * sv,
                     n[2] * dist + d[2] * hw * su + h[2] * hh * sv)
                pts.append(p)
            nn = n
            if m is not None:
                pts = [tuple(m @ np.array(p)) for p in pts]
                nn = tuple(m @ np.array(n))
            pts = [(p[0] + centre[0], p[1] + centre[1], p[2] + centre[2]) for p in pts]
            uvs = ((0, 0), (lw * 0.5, 0), (lw * 0.5, lh * 0.5), (0, lh * 0.5)) if uv_local else None
            self.quad(*pts, nn, couleur, uvs)

    def cylindre(self, a, b, rayon, couleur, segments=8, bouchons=True, rayon_b=None):
        """Cylindre (ou cône tronqué) de l'axe A vers B."""
        rayon_b = rayon if rayon_b is None else rayon_b
        axe = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        longueur = math.sqrt(sum(c * c for c in axe)) or 1.0
        ax = _norm(axe)
        ref = (0, 1, 0) if abs(ax[1]) < 0.9 else (1, 0, 0)
        u = _norm(_croix(ax, ref))
        v = _croix(u, ax)
        anneau = []
        for i in range(segments + 1):
            t = 2 * math.pi * i / segments
            c, s = math.cos(t), math.sin(t)
            anneau.append((u[0] * c + v[0] * s, u[1] * c + v[1] * s, u[2] * c + v[2] * s))
        for i in range(segments):
            d0, d1 = anneau[i], anneau[i + 1]
            p0 = (a[0] + d0[0] * rayon, a[1] + d0[1] * rayon, a[2] + d0[2] * rayon)
            p1 = (a[0] + d1[0] * rayon, a[1] + d1[1] * rayon, a[2] + d1[2] * rayon)
            p2 = (b[0] + d1[0] * rayon_b, b[1] + d1[1] * rayon_b, b[2] + d1[2] * rayon_b)
            p3 = (b[0] + d0[0] * rayon_b, b[1] + d0[1] * rayon_b, b[2] + d0[2] * rayon_b)
            nm = _norm((d0[0] + d1[0], d0[1] + d1[1], d0[2] + d1[2]))
            uvs = ((i / segments * 2, 0), ((i + 1) / segments * 2, 0),
                   ((i + 1) / segments * 2, longueur * 0.5), (i / segments * 2, longueur * 0.5))
            # l'ordre p0,p3,p2,p1 ou p0,p1,p2,p3 dépend du sens : on vérifie avec la normale
            if _sens_ok(p0, p1, p2, nm):
                self.quad(p0, p1, p2, p3, nm, couleur, uvs)
            else:
                self.quad(p1, p0, p3, p2, nm, couleur, uvs)
        if bouchons:
            for centre, r, n in ((a, rayon, (-ax[0], -ax[1], -ax[2])), (b, rayon_b, ax)):
                for i in range(segments):
                    d0, d1 = anneau[i], anneau[i + 1]
                    p0 = centre
                    p1 = (centre[0] + d0[0] * r, centre[1] + d0[1] * r, centre[2] + d0[2] * r)
                    p2 = (centre[0] + d1[0] * r, centre[1] + d1[1] * r, centre[2] + d1[2] * r)
                    if _sens_ok(p0, p1, p2, n):
                        self.quad(p0, p1, p2, p0, n, couleur, ((0.5, 0.5), (0, 0), (1, 0), (0.5, 0.5)))
                    else:
                        self.quad(p0, p2, p1, p0, n, couleur, ((0.5, 0.5), (0, 0), (1, 0), (0.5, 0.5)))

    def sphere(self, centre, rayon, couleur, anneaux=10, segments=14, interieur=False, echelle=(1, 1, 1)):
        """Sphère UV (optionnellement vue de l'intérieur, pour le ciel)."""
        pts = []
        for j in range(anneaux + 1):
            phi = math.pi * j / anneaux
            ligne = []
            for i in range(segments + 1):
                th = 2 * math.pi * i / segments
                n = (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th))
                ligne.append((n, (i / segments, 1 - j / anneaux)))
            pts.append(ligne)
        for j in range(anneaux):
            for i in range(segments):
                coins = (pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i])
                pos = [(centre[0] + n[0] * rayon * echelle[0], centre[1] + n[1] * rayon * echelle[1],
                        centre[2] + n[2] * rayon * echelle[2]) for n, _ in coins]
                uvs = [uv for _, uv in coins]
                nm = _norm(tuple(sum(c[0][k] for c in coins) for k in range(3)))
                if interieur:
                    nm = (-nm[0], -nm[1], -nm[2])
                if _sens_ok(pos[0], pos[1], pos[2], nm) or _sens_ok(pos[0], pos[2], pos[3], nm):
                    self.quad(pos[0], pos[1], pos[2], pos[3], nm, couleur, uvs)
                else:
                    self.quad(pos[1], pos[0], pos[3], pos[2], nm, couleur, [uvs[1], uvs[0], uvs[3], uvs[2]])

    # -- construction du nœud Panda3D -----------------------------------------
    def construire(self, nom="mesh"):
        """Crée un GeomNode Panda3D à partir des données accumulées (rapide, via numpy)."""
        noeud = GeomNode(nom)
        if self.n == 0:
            return noeud
        donnees = np.asarray(self.sommets, dtype=np.float32)
        vdata = GeomVertexData(nom, FORMAT_SOMMETS, Geom.UHStatic)
        vdata.uncleanSetNumRows(self.n)
        memoryview(vdata.modifyArray(0)).cast("B")[:] = donnees.tobytes()
        prim = GeomTriangles(Geom.UHStatic)
        prim.setIndexType(Geom.NTUint32)
        idx = np.asarray(self.indices, dtype=np.uint32)
        tableau = prim.modifyVertices()
        tableau.uncleanSetNumRows(len(idx))
        memoryview(tableau).cast("B")[:] = idx.tobytes()
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        noeud.addGeom(geom)
        return noeud


def _normale_mur(ax, az, bx, bz):
    """Normale d'un mur allant de A vers B : n = direction x haut (repère main gauche)."""
    dx, dz = bx - ax, bz - az
    l = math.hypot(dx, dz) or 1.0
    d = (dx / l, 0.0, dz / l)
    # n tel que croix(n, haut) == d  =>  n = croix(haut, d)
    return _croix(HAUT, d)


def _sens_ok(p0, p1, p2, n):
    """Vrai si le triangle p0,p1,p2 est anti-horaire vu depuis la normale n (convention quad())."""
    e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    c = _croix(e2, e1)   # convention main gauche : croix(e2, e1) pointe vers la face avant
    return c[0] * n[0] + c[1] * n[1] + c[2] * n[2] >= 0


# ---------------------------------------------------------------------------
# Bruit périodique et textures
# ---------------------------------------------------------------------------
def bruit_valeur(largeur, hauteur, grille, rng, periodique=True):
    """Bruit de valeur interpolé (lisse), périodique en x et y."""
    gx, gy = grille
    g = rng.random((gy, gx))
    u = np.linspace(0, gx, largeur, endpoint=False)
    v = np.linspace(0, gy, hauteur, endpoint=False)
    x0 = np.floor(u).astype(int)
    y0 = np.floor(v).astype(int)
    fx = u - x0
    fy = v - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    x1 = (x0 + 1) % gx
    y1 = (y0 + 1) % gy
    x0 %= gx
    y0 %= gy
    a = g[np.ix_(y0, x0)]
    b = g[np.ix_(y0, x1)]
    c = g[np.ix_(y1, x0)]
    d = g[np.ix_(y1, x1)]
    fx = fx[None, :]
    fy = fy[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def bruit_fractal(largeur, hauteur, rng, base=4, octaves=5, persistance=0.5, ratio=1):
    """Somme de plusieurs octaves de bruit de valeur (fBm), normalisée entre 0 et 1."""
    total = np.zeros((hauteur, largeur))
    amp, somme = 1.0, 0.0
    for o in range(octaves):
        f = base * (2 ** o)
        total += bruit_valeur(largeur, hauteur, (f * ratio, f), rng) * amp
        somme += amp
        amp *= persistance
    total /= somme
    total -= total.min()
    total /= (total.max() or 1)
    return total


def texture_depuis_tableau(tab, nom="tex", mipmap=True, repeter=True):
    """Convertit un tableau numpy (h, l, 3 ou 4) en texture Panda3D."""
    tab = np.clip(tab, 0, 1)
    if tab.shape[2] == 3:
        tab = np.concatenate([tab, np.ones(tab.shape[:2] + (1,))], axis=2)
    h, l = tab.shape[:2]
    octets = (np.flipud(tab) * 255).astype(np.uint8)
    tex = PandaTexture(nom)
    tex.setup2dTexture(l, h, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
    tex.setRamImageAs(octets.tobytes(), "RGBA")
    if mipmap:
        tex.setMinfilter(SamplerState.FTLinearMipmapLinear)
        tex.setAnisotropicDegree(4)
    else:
        tex.setMinfilter(SamplerState.FTLinear)
    tex.setMagfilter(SamplerState.FTLinear)
    mode = SamplerState.WMRepeat if repeter else SamplerState.WMClamp
    tex.setWrapU(mode)
    tex.setWrapV(mode)
    return tex


def _gris(v):
    return np.stack([v, v, v], axis=2)


class Textures:
    """Génère (une seule fois) toutes les textures procédurales du vaisseau."""

    def __init__(self, seed=7):
        self.rng = np.random.default_rng(seed)
        self.cache = {}

    def get(self, nom):
        if nom not in self.cache:
            self.cache[nom] = getattr(self, "_" + nom)()
        return self.cache[nom]

    # plaques de sol en métal avec relief antidérapant
    def _sol(self):
        n = 256
        crasse = bruit_fractal(n, n, self.rng, base=4, octaves=5)
        y, x = np.mgrid[0:n, 0:n]
        motif = ((x + y) % 16 < 2) | ((x - y) % 16 < 2)
        v = 0.42 + crasse * 0.25 - motif * 0.05
        joints = (x % 128 < 3) | (y % 128 < 3)
        v = np.where(joints, 0.16, v)
        for cx in (10, 118, 138, 246):
            for cy in (10, 118, 138, 246):
                v = np.where((x - cx) ** 2 + (y - cy) ** 2 < 10, 0.62, v)
        return texture_depuis_tableau(_gris(v), "sol")

    # panneaux muraux verticaux avec coulures de rouille
    def _mur(self):
        n = 256
        crasse = bruit_fractal(n, n, self.rng, base=3, octaves=5)
        y, x = np.mgrid[0:n, 0:n]
        v = 0.5 + crasse * 0.22
        v = np.where(x % 64 < 2, 0.2, v)
        v = np.where((y % 128 > 60) & (y % 128 < 66), 0.3, v)
        v = np.where((y % 128 > 66) & (y % 128 < 70), 0.62, v)
        coulures = bruit_valeur(n, n, (48, 3), self.rng) ** 6 * 1.2
        img = _gris(v)
        img[..., 0] -= coulures * 0.10
        img[..., 1] -= coulures * 0.22
        img[..., 2] -= coulures * 0.30
        return texture_depuis_tableau(img, "mur")

    # plafond : dalles et grilles de ventilation
    def _plafond(self):
        n = 128
        crasse = bruit_fractal(n, n, self.rng, base=4, octaves=4)
        y, x = np.mgrid[0:n, 0:n]
        v = 0.35 + crasse * 0.2
        v = np.where((x % 64 < 2) | (y % 64 < 2), 0.1, v)
        fentes = (x % 64 > 16) & (x % 64 < 48) & (y % 64 > 20) & (y % 64 < 44) & (y % 4 < 2)
        v = np.where(fentes, 0.08, v)
        return texture_depuis_tableau(_gris(v), "plafond")

    # coque extérieure sombre
    def _coque(self):
        n = 256
        crasse = bruit_fractal(n, n, self.rng, base=2, octaves=6)
        y, x = np.mgrid[0:n, 0:n]
        v = 0.3 + crasse * 0.3
        v = np.where((x % 128 < 2) | (y % 64 < 2), 0.12, v)
        return texture_depuis_tableau(_gris(v), "coque")

    # tôle ondulée des conduits d'aération
    def _conduit(self):
        n = 128
        crasse = bruit_fractal(n, n, self.rng, base=4, octaves=4)
        y, x = np.mgrid[0:n, 0:n]
        v = 0.4 + 0.12 * np.sin(x / n * 2 * np.pi * 16) + crasse * 0.2
        return texture_depuis_tableau(_gris(v), "conduit")

    # texture neutre de crasse pour les objets (multipliée par la couleur des sommets)
    def _objet(self):
        n = 128
        crasse = bruit_fractal(n, n, self.rng, base=4, octaves=5)
        y, x = np.mgrid[0:n, 0:n]
        v = 0.75 + crasse * 0.3
        v = np.where((x % 128 < 2) | (y % 128 < 2), 0.5, v)
        return texture_depuis_tableau(_gris(v), "objet")

    # atlas 2x2 de décalques : éclaboussure, traînée, griffures, flaque
    def _decalques(self):
        n = 256
        h = n // 2
        img = np.zeros((n, n, 4))
        y, x = np.mgrid[0:h, 0:h] / h - 0.5
        r = np.sqrt(x * x + y * y)
        b = bruit_fractal(h, h, self.rng, base=6, octaves=4)
        # 1. éclaboussure
        a1 = np.clip((0.33 - r + (b - 0.5) * 0.35) * 8, 0, 1)
        gouttes = (bruit_valeur(h, h, (24, 24), self.rng) > 0.86) & (r < 0.48)
        a1 = np.maximum(a1, gouttes * 0.9)
        # 2. traînée verticale
        a2 = np.clip((0.18 - np.abs(x + (b - 0.5) * 0.2)) * 8, 0, 1) * np.clip((0.45 - np.abs(y)) * 6, 0, 1)
        # 3. griffures (trois entailles)
        a3 = np.zeros_like(r)
        for k in (-0.15, 0.0, 0.15):
            ligne = np.abs((x - k) - y * 0.25)
            a3 = np.maximum(a3, np.clip((0.018 - ligne) * 70, 0, 1) * np.clip((0.42 - np.abs(y)) * 8, 0, 1))
        # 4. flaque
        a4 = np.clip((0.4 - r + (b - 0.5) * 0.25) * 10, 0, 1)
        sang = np.array([0.22, 0.02, 0.02])
        suie = np.array([0.03, 0.03, 0.03])
        for (oy, ox), a, c in (((h, 0), a1, sang), ((h, h), a2, sang), ((0, 0), a3, suie), ((0, h), a4, sang)):
            img[oy:oy + h, ox:ox + h, :3] = c * (0.7 + b[..., None] * 0.6)
            img[oy:oy + h, ox:ox + h, 3] = a * 0.92
        return texture_depuis_tableau(img, "decalques", repeter=False)

    # point lumineux doux (étoiles, halos)
    def _halo(self):
        n = 64
        y, x = np.mgrid[0:n, 0:n] / (n - 1) - 0.5
        r = np.sqrt(x * x + y * y) * 2
        a = np.clip(1 - r, 0, 1) ** 2.5
        img = np.ones((n, n, 4))
        img[..., 3] = a
        return texture_depuis_tableau(img, "halo", repeter=False)

    # fentes de casier (vue depuis l'intérieur quand le joueur se cache)
    def _fentes(self):
        l, h = 512, 256
        img = np.zeros((h, l, 4))
        img[..., 3] = 1.0
        y, x = np.mgrid[0:h, 0:l]
        fentes = (np.abs(x - l / 2) < 150) & (y % 32 > 20) & (y > 60) & (y < 200)
        img[..., 3] = np.where(fentes, 0.0, 0.97)
        return texture_depuis_tableau(img, "fentes", mipmap=False, repeter=False)
