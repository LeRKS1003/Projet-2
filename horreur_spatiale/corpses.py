# -*- coding: utf-8 -*-
"""
corpses.py — Corps de l'équipage du Kerguelen (tout le code des cadavres).

Anatomie et poses :
  * squelette articulé (bassin, deux segments de colonne, cou, tête,
    épaules, bras, avant-bras, mains à doigts en deux phalanges, hanches,
    cuisses, jambes, pieds) aux proportions humaines ;
  * poses calculées par cinématique directe à partir d'ANGLES D'ARTICULATION
    LIMITÉS (comme un vrai corps : un coude ne se plie pas à l'envers) ;
  * effet de poids : le corps s'affaisse sur son support (sol, chaise,
    bureau, mur), les membres qui touchent le sol s'y posent, la tête
    retombe ;
  * maillages lisses (capsules et ellipsoïdes à normales lissées), sans cube.

Combinaisons et peau :
  * tissu épais (normal map de plis et coutures), poches, fermeture éclair,
    sangles, ceinture, renforts usés aux coudes et genoux, bande de couleur du
    poste, badge nominatif (nom + fonction), saleté et taches (couleur des
    sommets modulée par un bruit 3D) ;
  * peau visible (mains, cou, un peu du visage) pâle, grisâtre, légèrement
    bleutée, aux veines sombres (SINUS) — matériau « deadskin » ;
  * le vaisseau est glacé : fine couche de givre sur les parties tournées vers
    le haut (combinaison, cheveux), petits cristaux qui scintillent sous la
    lampe, visières embuées et gelées, fêlées ;
  * cheveux en mèches (plans fins), casques posés à côté de certains corps.

Autour des corps (histoire) : tablette fissurée, photo de famille floue
(générée), lampe torche éteinte, arme vide, carnet ouvert, seringue à
l'infirmerie, clé à molette en salle des machines ; décalques de sang séché,
traces de mains, traînées (horreur suggestive, sans gore excessif).

Hallucination : quand l'infection est avancée, très rarement, un corps a
changé de position quand on revient dans la pièce — sa tête est tournée vers
le joueur.
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from panda3d.core import TransparencyAttrib, Material
from ursina import Entity, Texture, color, destroy

import config as C
import textures
from geometry import MeshBuilder
import loot

# poste de chaque membre d'équipage : (nom sur le badge, fonction, couleur de la bande d'épaule)
ROLES = {
    "vasseur": ("VASSEUR", "Commandante", (.75, .6, .15)),
    "keating": ("KEATING", "Cheffe scientifique", (.2, .55, .6)),
    "okafor": ("OKAFOR", "Médecin", (.75, .12, .12)),
    "lebrun": ("LEBRUN", "Ingénieur en chef", (.85, .45, .08)),
    "fontaine": ("FONTAINE", "Pilote", (.15, .4, .8)),
    "andreiev": ("ANDREÏEV", "Technicien labo", (.35, .6, .25)),
    "ricci": ("RICCI", "Intendant", (.6, .5, .35)),
}

# objets personnels posés près de chaque corps (liés à l'histoire)
PERSONAL = {
    "vasseur": ("tablet", "notebook"),
    "okafor": ("syringe", "photo"),
    "lebrun": ("wrench", "flashlight"),
    "fontaine": ("flashlight", "notebook"),
    "andreiev": ("syringe", "tablet"),
    "ricci": ("pistol", "photo"),
    None: ("flashlight",),
}

# peau d'un corps mort dans le froid : pâle, grisâtre, légèrement bleutée
DEAD_SKIN = [(.66, .66, .7), (.56, .55, .6), (.7, .69, .72), (.5, .5, .56)]
HAIR = [(.07, .055, .05), (.17, .12, .08), (.05, .05, .05), (.32, .3, .28), (.25, .17, .1)]


# ============================================================================
# PRIMITIVES LISSES
# ============================================================================
def _v(a):
    return np.asarray(a, np.float64)


def _frame(d):
    """Deux vecteurs perpendiculaires à d (unitaire)."""
    up = np.array([0, 1, 0]) if abs(d[1]) < .9 else np.array([1, 0, 0])
    u = np.cross(d, up)
    u /= np.linalg.norm(u)
    w = np.cross(d, u)
    return u, w


def capsule(mb, a, b, r0, r1, col, seg=10, cap=3):
    """Capsule effilée de a (rayon r0) à b (rayon r1), normales lisses, UV continues."""
    a, b = _v(a), _v(b)
    d = b - a
    L = np.linalg.norm(d)
    if L < 1e-5:
        return ellipsoid(mb, a, (r0, r0, r0), col)
    d /= L
    u, w = _frame(d)
    rings = []
    for k in range(cap, 0, -1):
        t = (k / cap) * math.pi / 2
        rings.append((a - d * r0 * math.sin(t), r0 * math.cos(t), -math.sin(t)))
    for k in range(3):
        f = k / 2
        rings.append((a + d * L * f, r0 + (r1 - r0) * f, 0.0))
    for k in range(1, cap + 1):
        t = (k / cap) * math.pi / 2
        rings.append((b + d * r1 * math.sin(t), r1 * math.cos(t), math.sin(t)))
    cc = (col[0], col[1], col[2], col[3] if len(col) > 3 else 1.0)
    base = mb.count
    for ri, (c, r, nz) in enumerate(rings):
        along = np.dot(c - a, d) + r0
        for s in range(seg + 1):
            ang = 2 * math.pi * s / seg
            radial = u * math.cos(ang) + w * math.sin(ang)
            p = c + radial * max(r, 1e-4)
            n = radial * math.sqrt(max(0.0, 1 - nz * nz)) + d * nz
            mb.v.extend(p.tolist())
            mb.n.extend(n.tolist())
            mb.c.extend(cc)
            mb.t.extend((s / seg * math.pi * (r0 + r1) / .7, along / .7))   # tissu : ~70 cm par motif
    nr = len(rings)
    for ri in range(nr - 1):
        for s in range(seg):
            i0 = base + ri * (seg + 1) + s
            i1 = i0 + seg + 1
            mb.i.extend((i0, i1, i0 + 1, i0 + 1, i1, i1 + 1))
    mb.count += nr * (seg + 1)


def ellipsoid(mb, c, radii, col, rot=None, seg=12, rings=8):
    """Ellipsoïde (tête, paume, renforts...), rot : matrice 3x3 (colonnes = axes locaux)."""
    c = _v(c)
    rx, ry, rz = radii
    R = np.eye(3) if rot is None else rot
    cc = (col[0], col[1], col[2], col[3] if len(col) > 3 else 1.0)
    base = mb.count
    for i in range(rings + 1):
        th = math.pi * i / rings
        for j in range(seg + 1):
            ph = 2 * math.pi * j / seg
            lx, ly, lz = math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)
            p = c + R @ np.array([lx * rx, ly * ry, lz * rz])
            n = R @ np.array([lx / rx, ly / ry, lz / rz])
            n /= np.linalg.norm(n) + 1e-9
            mb.v.extend(p.tolist())
            mb.n.extend(n.tolist())
            mb.c.extend(cc)
            mb.t.extend((j / seg * 2, i / rings))
    for i in range(rings):
        for j in range(seg):
            a0 = base + i * (seg + 1) + j
            a1 = a0 + seg + 1
            mb.i.extend((a0, a0 + 1, a1, a0 + 1, a1 + 1, a1))
    mb.count += (rings + 1) * (seg + 1)


def _look_rot(fwd, up_hint=(0, 1, 0)):
    """Matrice de rotation dont l'axe z local suit 'fwd'."""
    f = _v(fwd)
    f /= np.linalg.norm(f) + 1e-9
    up = _v(up_hint)
    if abs(np.dot(f, up)) > .95:
        up = np.array([1.0, 0, 0])
    x = np.cross(up, f)
    x /= np.linalg.norm(x)
    y = np.cross(f, x)
    return np.column_stack([x, y, f])


def _rx(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# ============================================================================
# SQUELETTE : angles d'articulation limités (degrés)
# ============================================================================
LIMITS = {
    "spine1": (-25, 60), "spine2": (-20, 55), "side": (-30, 30),
    "neck": (-40, 70), "turn": (-80, 80), "tilt": (-40, 40),
    "sh_flex": (-50, 175), "sh_abd": (-10, 160), "elbow": (0, 145),
    "hip_flex": (-25, 125), "hip_abd": (-25, 55), "knee": (0, 150), "wrist": (-60, 70),
}

# dimensions du corps (repère du corps : x droite, y le long de la colonne, z devant)
SEG = {"waist": .2, "chest": .25, "neck": .07, "head": .13, "upper": .29, "fore": .26, "thigh": .44,
       "shin": .42, "sh_w": .19, "hip_w": .095}


def _lim(name, v):
    lo, hi = LIMITS[name]
    return max(lo, min(hi, v))


def _orient(kind):
    """Orientation du corps entier : colonnes = axes x, y (colonne), z (face) du corps dans le repère local."""
    if kind in ("facedown", "crawl"):
        return np.column_stack([(1, 0, 0), (0, 0, 1), (0, -1, 0)])
    if kind == "supine":
        return np.column_stack([(-1, 0, 0), (0, 0, 1), (0, 1, 0)])
    if kind == "curled":
        return np.column_stack([(0, 1, 0), (0, 0, 1), (1, 0, 0)])
    if kind == "slumped":
        return _rx(-22)                          # adossé : la colonne s'appuie en arrière contre le mur
    return np.eye(3)                             # assis à une console


def _pose_angles(kind, rng):
    """Angles d'articulation (avant limitation) et réglages de support pour chaque pose."""
    j = lambda a=8: rng.uniform(-a, a)
    A = {}
    if kind == "slumped":          # affalé contre un mur, tête retombée sur le côté, une jambe repliée
        A = dict(spine1=18 + j(), spine2=22 + j(), side=12 + j(5), neck=55 + j(), turn=35 + j(15), tilt=28,
                 R=dict(sh_flex=12 + j(), sh_abd=18 + j(), elbow=25 + j(10)),
                 L=dict(sh_flex=30 + j(), sh_abd=12, elbow=70 + j(15)),
                 RL=dict(hip_flex=78, hip_abd=12, knee=28 + j(10)), LL=dict(hip_flex=95, hip_abd=22, knee=95 + j(15)))
    elif kind == "curled":         # recroquevillé sur le côté, bras serrés, tête rentrée
        A = dict(spine1=38 + j(), spine2=34 + j(), side=j(6), neck=50 + j(), turn=j(10), tilt=j(10),
                 R=dict(sh_flex=95 + j(), sh_abd=10, elbow=125 + j(10)),
                 L=dict(sh_flex=80 + j(), sh_abd=5, elbow=115 + j(10)),
                 RL=dict(hip_flex=105 + j(), hip_abd=5, knee=120 + j(10)), LL=dict(hip_flex=95 + j(), hip_abd=0, knee=125))
    elif kind == "facedown":       # face contre terre, un bras tendu devant, tête tournée
        A = dict(spine1=j(5), spine2=j(5), side=j(8), neck=-5, turn=70 + j(10), tilt=j(10),
                 R=dict(sh_flex=165 + j(5), sh_abd=20 + j(), elbow=15 + j(10)),
                 L=dict(sh_flex=-10, sh_abd=12, elbow=20 + j(10)),
                 RL=dict(hip_flex=j(4), hip_abd=10 + j(5), knee=8 + j(5)), LL=dict(hip_flex=15 + j(5), hip_abd=18, knee=40 + j(10)))
    elif kind == "crawl":          # a rampé vers la porte : un bras qui s'agrippe, une jambe qui pousse
        A = dict(spine1=5 + j(4), spine2=8 + j(4), side=8 + j(5), neck=-10, turn=15 + j(10), tilt=j(8),
                 R=dict(sh_flex=170, sh_abd=12 + j(5), elbow=20 + j(10)),
                 L=dict(sh_flex=70 + j(), sh_abd=55 + j(), elbow=110 + j(10)),
                 RL=dict(hip_flex=j(4), hip_abd=6, knee=10 + j(5)), LL=dict(hip_flex=55 + j(), hip_abd=40, knee=75 + j(10)))
    elif kind == "supine":         # allongé sur le dos (table d'opération), tête tournée
        A = dict(spine1=j(3), spine2=j(3), side=j(3), neck=5, turn=-65 + j(10), tilt=j(8),
                 R=dict(sh_flex=-5, sh_abd=14, elbow=10 + j(8)), L=dict(sh_flex=-5, sh_abd=12, elbow=30 + j(8)),
                 RL=dict(hip_flex=j(3), hip_abd=6, knee=5), LL=dict(hip_flex=j(3), hip_abd=6, knee=8))
    else:                          # "desk" : assis, effondré sur la console, la tête sur les bras
        A = dict(spine1=30 + j(4), spine2=45 + j(4), side=6 + j(4), neck=40 + j(5), turn=50 + j(10), tilt=20,
                 R=dict(sh_flex=95 + j(5), sh_abd=35 + j(5), elbow=120 + j(8)),
                 L=dict(sh_flex=60 + j(5), sh_abd=8, elbow=10 + j(8)),            # l'autre bras pend
                 RL=dict(hip_flex=88, hip_abd=8, knee=85 + j(5)), LL=dict(hip_flex=82, hip_abd=14, knee=70 + j(8)))
    return A


def _skeleton(kind, rng, look_world=None, to_body=None):
    """
    Cinématique directe : renvoie {nom: point (repère local, avant support)}, les
    repères des segments utiles et la direction du visage.
    """
    A = _pose_angles(kind, rng)
    O = _orient(kind)
    P = {"pelvis": np.zeros(3)}
    F_pel = np.eye(3)
    F_w = F_pel @ _rx(_lim("spine1", A["spine1"])) @ _rz(_lim("side", A["side"]) * .5)
    P["waist"] = F_w @ np.array([0, SEG["waist"], 0])
    F_c = F_w @ _rx(_lim("spine2", A["spine2"])) @ _rz(_lim("side", A["side"]) * .5)
    P["chest"] = P["waist"] + F_c @ np.array([0, SEG["chest"], 0])
    P["neck"] = P["chest"] + F_c @ np.array([0, SEG["neck"], .0])
    F_h = F_c @ _rx(_lim("neck", A["neck"])) @ _ry(_lim("turn", A["turn"])) @ _rz(_lim("tilt", A["tilt"]))
    P["head"] = P["neck"] + F_h @ np.array([0, SEG["head"], .02])
    face = F_h @ np.array([0, 0, 1.0])
    frames = {"pelvis": F_pel, "waist": F_w, "chest": F_c, "head": F_h}
    for side, key in ((1, "R"), (-1, "L")):
        a = A[key]
        sh = P["waist"] + F_c @ np.array([side * SEG["sh_w"], SEG["chest"] - .04, -.01])
        F_u = F_c @ _rx(-_lim("sh_flex", a["sh_flex"])) @ _rz(side * _lim("sh_abd", a["sh_abd"]))
        el = sh + F_u @ np.array([0, -SEG["upper"], 0])
        F_f = F_u @ _rx(-_lim("elbow", a["elbow"]))
        wr = el + F_f @ np.array([0, -SEG["fore"], 0])
        P["sh" + key], P["el" + key], P["wr" + key] = sh, el, wr
        frames["fore" + key] = F_f
        b = A[key + "L"]
        hp = np.array([side * SEG["hip_w"], -.04, 0])
        F_t = F_pel @ _rx(-_lim("hip_flex", b["hip_flex"])) @ _rz(side * _lim("hip_abd", b["hip_abd"]))
        kn = hp + F_t @ np.array([0, -SEG["thigh"], 0])
        F_s = F_t @ _rx(_lim("knee", b["knee"]))
        an = kn + F_s @ np.array([0, -SEG["shin"], 0])
        toe = an + F_s @ np.array([0, -.04, .19])
        P["hip" + key], P["kn" + key], P["an" + key], P["toe" + key] = hp, kn, an, toe
        frames["shin" + key] = F_s
    # orientation du corps entier
    for k in P:
        P[k] = O @ P[k]
    for k in frames:
        frames[k] = O @ frames[k]
    face = O @ face
    return P, frames, face


# rayon (épaisseur) approximatif autour de chaque point, pour le poser sur son support
RADII = {"pelvis": .14, "waist": .15, "chest": .17, "neck": .06, "head": .12, "sh": .07, "el": .055, "wr": .045,
         "hip": .09, "kn": .07, "an": .055, "toe": .05}


def _radius(name):
    for k in sorted(RADII, key=len, reverse=True):
        if name.startswith(k):
            return RADII[k]
    return .05


def _settle(P, kind, y0):
    """
    Effet de poids : le corps s'affaisse sur son support. Le point le plus bas
    touche le sol (ou la table), les membres qui passeraient dessous s'y posent
    à plat ; assis à une console, le haut du corps repose sur le bureau.
    """
    if kind == "desk":
        # assis sur la chaise (bassin à hauteur d'assise), le bureau devant (z > .3) à 0,93 m
        lift = .5 - P["pelvis"][1]
        for k in P:
            P[k] = P[k] + np.array([0, lift, 0])
        for k in P:
            r = _radius(k)
            if P[k][2] > .28 and k not in ("pelvis",) and not k.startswith(("hip", "kn", "an", "toe")):
                P[k][1] = max(P[k][1], .93 + r)
            P[k][1] = max(P[k][1], r)
        return P
    low = min(P[k][1] - _radius(k) for k in P)
    for k in P:
        P[k] = P[k] + np.array([0, y0 - low, 0])
    for k in P:
        r = _radius(k)
        P[k][1] = max(P[k][1], y0 + r * .9)
        # la tête, les bras et les jambes retombent vers le support (gravité)
        if k.startswith(("wr", "el", "head", "an", "toe", "kn")) and kind not in ("slumped",):
            P[k][1] = y0 + r + (P[k][1] - y0 - r) * .55
    if kind == "slumped":
        # adossé au mur (derrière : z négatif)
        for k in P:
            P[k][2] = max(P[k][2], -.28 + _radius(k))
        for k in ("wrR", "wrL", "anR", "anL", "toeR", "toeL"):
            P[k][1] = y0 + _radius(k)                 # mains et pieds posés au sol
    return P


# ============================================================================
# TEXTURES GÉNÉRÉES : badge, photo de famille, givre
# ============================================================================
_tex = {}


def badge_texture(who):
    key = ("badge", who)
    if key in _tex:
        return _tex[key]
    name, role, stripe = ROLES.get(who, ("INCONNU", "Équipage", (.5, .5, .5)))
    w, h = 256, 96
    img = Image.new("RGBA", (w, h), (205, 205, 196, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(60, 60, 60, 255), width=3)
    d.rectangle((0, 0, 22, h), fill=tuple(int(c * 255) for c in stripe) + (255,))
    try:
        from document_ui import font as dfont
        f1, f2 = dfont("sans_bold", 34), dfont("sans", 20)
    except Exception:
        f1 = f2 = None
    d.text((32, 10), name, fill=(25, 25, 25, 255), font=f1)
    d.text((32, 56), role, fill=(55, 55, 55, 255), font=f2)
    arr = np.asarray(img).astype(np.float32)
    rng = np.random.default_rng(abs(hash(who)) % 9999)
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(6):                               # usure, taches de givre et de crasse
        cx, cy = rng.integers(0, w), rng.integers(0, h)
        m = np.exp(-(((xx - cx) / rng.uniform(6, 20)) ** 2 + ((yy - cy) / rng.uniform(4, 12)) ** 2))
        arr[..., :3] *= (1 - .45 * m[..., None])
    t = Texture(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA"))
    _tex[key] = t
    return t


def photo_texture(seed):
    """Photo de famille floue (générée) : silhouettes devant un fond chaud, bord blanc, pli."""
    key = ("photo", seed)
    if key in _tex:
        return _tex[key]
    rng = random.Random(seed)
    w, h = 192, 144
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    top = (rng.randint(150, 220), rng.randint(120, 170), rng.randint(80, 130))
    bot = (rng.randint(60, 110), rng.randint(70, 110), rng.randint(70, 120))
    for y in range(h):
        k = y / h
        d.line((0, y, w, y), fill=tuple(int(top[i] * (1 - k) + bot[i] * k) for i in range(3)))
    n = rng.randint(2, 4)
    for i in range(n):
        x = int(w * (i + .7) / (n + .4))
        hh = rng.randint(55, 90) if i != n - 1 or n < 3 else rng.randint(35, 50)
        col = tuple(rng.randint(30, 120) for _ in range(3))
        d.ellipse((x - 22, h - hh, x + 22, h + 30), fill=col)                    # corps
        d.ellipse((x - 11, h - hh - 24, x + 11, h - hh), fill=(190, 150, 125))   # tête
    img = img.filter(ImageFilter.GaussianBlur(3.2))
    arr = np.asarray(img).astype(np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w]
    vig = 1 - .5 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    arr *= np.clip(vig, .3, 1)[..., None]
    arr = arr * .8 + .12                                                          # photo délavée
    out = np.ones((h + 16, w + 16, 4), np.float32)
    out[8:-8, 8:-8, :3] = arr
    out[:, w // 2 + 8:w // 2 + 10, :3] *= .75                                    # pli
    t = Texture(Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA"))
    _tex[key] = t
    return t


def frost_texture():
    """Givre : voile blanc irrégulier parsemé de petits cristaux qui accrochent la lumière."""
    key = ("frost",)
    if key in _tex:
        return _tex[key]
    rng = np.random.default_rng(271)
    s = 256
    n = textures.fractal_noise(s, s, rng, 5, base=4)
    a = np.clip((n - .35) * 1.6, 0, 1) * .55
    sparkle = (rng.random((s, s)) > .985).astype(np.float32)
    a = np.clip(a + sparkle * .9, 0, 1)
    v = np.clip(.85 + .15 * n + sparkle * .3, 0, 1)
    rgb = np.dstack([v * .93, v * .97, v])
    t = textures._to_tex(np.dstack([rgb, a]), 'mipmap')
    _tex[key] = t
    return t


# ============================================================================
# CORPS COMPLET
# ============================================================================
def _stains(mb, rng, strength=.35):
    """Saleté et taches : la couleur des sommets est assombrie par plaques (bruit 3D)."""
    if mb.count == 0:
        return
    V = np.asarray(mb.v, np.float64).reshape(-1, 3)
    Cc = np.asarray(mb.c, np.float64).reshape(-1, 4)
    ph = [rng.uniform(0, 6.28) for _ in range(6)]
    noise = (np.sin(V[:, 0] * 9 + ph[0]) * np.sin(V[:, 1] * 7 + ph[1]) * np.sin(V[:, 2] * 8 + ph[2])
             + .5 * np.sin(V[:, 0] * 23 + ph[3]) * np.sin(V[:, 2] * 19 + ph[4]))
    k = np.clip(noise, 0, 1) * strength
    Cc[:, :3] *= (1 - k)[:, None]
    # quelques taches brunes (sang séché, crasse)
    brown = np.clip(np.sin(V[:, 1] * 11 + ph[5]) * np.sin(V[:, 0] * 13 + ph[1]) - .6, 0, 1) * 2
    Cc[:, 0] = Cc[:, 0] * (1 - brown * .3) + .25 * brown * .3
    Cc[:, 1] *= (1 - brown * .45)
    Cc[:, 2] *= (1 - brown * .5)
    mb.c = Cc.reshape(-1).tolist()


def _frost_layer(src_list, rng):
    """Couche de givre : copie des faces tournées vers le haut, légèrement gonflée, semi-transparente."""
    fm = MeshBuilder()
    for mb in src_list:
        if mb.count == 0:
            continue
        V = np.asarray(mb.v, np.float64).reshape(-1, 3)
        N = np.asarray(mb.n, np.float64).reshape(-1, 3)
        T = np.asarray(mb.t, np.float64).reshape(-1, 2)
        up = np.clip((N[:, 1] - .15) * 1.6, 0, 1)
        base = fm.count
        Vf = V + N * .0035
        fm.v.extend(Vf.reshape(-1).tolist())
        fm.n.extend(N.reshape(-1).tolist())
        alpha = up * C.CORPSE_FROST
        cols = np.column_stack([np.full(len(V), .92), np.full(len(V), .96), np.ones(len(V)), alpha])
        fm.c.extend(cols.reshape(-1).tolist())
        fm.t.extend((T * 1.7).reshape(-1).tolist())
        fm.i.extend([base + i for i in mb.i])
        fm.count += len(V)
    return fm


def _hair(mb, head, F_h, face, rng, col):
    """Cheveux simplifiés : mèches en plans fins (deux faces), qui retombent selon la gravité."""
    for k in range(C.CORPSE_HAIR_STRANDS):
        a = rng.uniform(-2.2, 2.2)
        b = rng.uniform(.15, 1.2)
        local = np.array([math.sin(a) * math.sin(b), math.cos(b), -math.cos(a) * math.sin(b) * .9])
        root = head + F_h @ (local * np.array([.1, .115, .11]))
        side = F_h @ np.array([math.cos(a), 0, math.sin(a)])
        side /= np.linalg.norm(side) + 1e-9
        out = (root - head)
        out /= np.linalg.norm(out) + 1e-9
        pts = [root]
        d = out * .02 - face * .015 + np.array([0, -.02, 0])
        for s in range(3):
            d = d + np.array([0, -.018, 0]) + out * .008                # la gravité tire les mèches vers le bas
            pts.append(pts[-1] + d * rng.uniform(.8, 1.2))
        wdt = rng.uniform(.012, .022)
        for p, q in zip(pts, pts[1:]):
            n = np.cross(q - p, side)
            n /= np.linalg.norm(n) + 1e-9
            if np.dot(n, out) < 0:
                n = -n
            c0 = (col[0], col[1], col[2], 1)
            mb.quad(tuple((p - side * wdt).tolist()), tuple((p + side * wdt).tolist()),
                    tuple((q + side * wdt * .7).tolist()), tuple((q - side * wdt * .7).tolist()),
                    tuple(n.tolist()), c0)


def build_body(parent, x, y0, z, yaw, pose, suit_col, rng, who=None, helmet=None, look_at=None):
    """
    Construit un corps sous 'parent' et renvoie (racine, info). look_at : point
    du monde (x, z) vers lequel la tête est tournée (hallucination).
    """
    P, Fr, face = _skeleton(pose, rng)
    P = _settle(P, pose, 0.0)
    a = math.radians(yaw)
    ca, sa = math.cos(a), math.sin(a)

    def W(p):                        # local -> monde (repère Ursina : rotation autour de y)
        return np.array([x + p[0] * ca + p[2] * sa, y0 + p[1], z - p[0] * sa + p[2] * ca])

    def Wd(d):
        return np.array([d[0] * ca + d[2] * sa, d[1], -d[0] * sa + d[2] * ca])

    Q = {k: W(v) for k, v in P.items()}
    F = {k: np.column_stack([Wd(v[:, i]) for i in range(3)]) for k, v in Fr.items()}
    face = Wd(face)
    if look_at is not None:
        # hallucination : la tête s'est tournée vers le joueur
        tgt = np.array([look_at[0], Q["head"][1] + .1, look_at[1]])
        face = tgt - Q["head"]
        face /= np.linalg.norm(face) + 1e-9
    face /= np.linalg.norm(face) + 1e-9
    suit = MeshBuilder()
    skin = MeshBuilder()
    gear = MeshBuilder()                      # métal / plastique : boucles, zip, visière, casque, objets
    dark = tuple(c * .5 for c in suit_col)
    pad = tuple(min(1, c * .68 + .04) for c in suit_col)
    worn = tuple(min(1, c * 1.25 + .08) for c in suit_col)                # renforts usés (plus clairs)
    stripe = ROLES.get(who, (None, None, (.45, .45, .45)))[2]
    skin_col = rng.choice(DEAD_SKIN)
    F_c = F["chest"]
    spine = Q["chest"] - Q["pelvis"]
    spine /= np.linalg.norm(spine)
    front = F_c[:, 2]
    right = F_c[:, 0]
    # --- bassin, abdomen, cage thoracique -------------------------------------------
    ellipsoid(suit, Q["pelvis"] + spine * .02, (.17, .11, .13), suit_col, rot=F["pelvis"], seg=14, rings=9)
    capsule(suit, Q["pelvis"], Q["waist"], .15, .155, suit_col, seg=14)
    ellipsoid(suit, Q["waist"] + F_c[:, 1] * .13, (.19, .17, .13), suit_col, rot=F_c, seg=16, rings=10)
    # plis horizontaux du tissu sur le ventre
    for k in range(2):
        ellipsoid(suit, Q["waist"] + spine * (k * .07 - .06), (.158, .016, .143), tuple(c * .86 for c in suit_col),
                  rot=F["waist"], seg=12, rings=5)
    # ceinture + boucle, sangle en bandoulière, poches de poitrine, fermeture éclair
    ellipsoid(suit, Q["pelvis"] + spine * .09, (.172, .03, .148), dark, rot=F["pelvis"], seg=14, rings=6)
    ellipsoid(gear, Q["pelvis"] + spine * .09 + F["pelvis"][:, 2] * .148, (.035, .025, .012), (.55, .55, .58),
              rot=F["pelvis"], seg=8, rings=5)
    capsule(suit, Q["shR"] + front * .07, Q["pelvis"] + spine * .12 - right * .1 + front * .14, .014, .014, dark,
            seg=6, cap=1)
    for s in (-1, 1):
        ellipsoid(suit, Q["waist"] + F_c[:, 1] * .17 + right * s * .085 + front * .128, (.055, .045, .022), pad,
                  rot=F_c, seg=10, rings=6)
    zip_a = Q["waist"] - spine * .12 + front * .148
    zip_b = Q["neck"] - spine * .03 + front * .11
    capsule(gear, zip_a, zip_b, .005, .005, (.6, .6, .62), seg=5, cap=1)
    # épaules (deltoïdes), écusson de couleur du poste
    for s_, key in ((1, "R"), (-1, "L")):
        ellipsoid(suit, Q["sh" + key], (.075, .07, .075), suit_col, seg=10, rings=7)
        d_ = Q["el" + key] - Q["sh" + key]
        d_ /= np.linalg.norm(d_) + 1e-9
        ellipsoid(suit, Q["sh" + key] + d_ * .08, (.062, .018, .062), stripe,
                  rot=_look_rot(np.cross(d_, spine) + 1e-6), seg=10, rings=5)
    # cou (peau), col épais de la combinaison
    capsule(skin, Q["neck"] - spine * .04, Q["neck"] + (Q["head"] - Q["neck"]) * .55, .046, .05, skin_col, seg=10)
    capsule(suit, Q["chest"], Q["neck"] - spine * .01, .1, .08, dark, seg=12)
    # --- tête : peau pâle (visage tourné), cheveux en mèches, ou casque à visière gelée ----
    head_rot = _look_rot(face)
    if helmet:
        ellipsoid(gear, Q["head"], (.155, .165, .16), (.78, .79, .8), rot=head_rot, seg=16, rings=11)
        visor = MeshBuilder()
        ellipsoid(visor, Q["head"] + face * .07, (.122, .102, .102), (.62, .68, .74, .82), rot=head_rot, seg=14,
                  rings=9)
        u_, w_ = _frame(face)
        hit = Q["head"] + face * .17 + u_ * .03
        for k in range(6):                          # visière fêlée : impact et fissures en étoile
            a_ = k * math.pi / 3 + rng.uniform(-.3, .3)
            end = hit + (u_ * math.cos(a_) + w_ * math.sin(a_)) * rng.uniform(.04, .08) - face * .012
            capsule(gear, hit, end, .0032, .0018, (.88, .9, .92), seg=4, cap=1)
    else:
        visor = None
        ellipsoid(skin, Q["head"], (.098, .118, .112), skin_col, rot=head_rot, seg=16, rings=11)
        ellipsoid(skin, Q["head"] + face * .07 - head_rot[:, 1] * .055, (.06, .04, .05), skin_col, rot=head_rot,
                  seg=10, rings=6)                                                  # mâchoire
        hair = rng.choice(HAIR)
        ellipsoid(skin, Q["head"] - face * .02 + head_rot[:, 1] * .02, (.104, .108, .108), hair, rot=head_rot,
                  seg=12, rings=8)                                                   # calotte
        _hair(skin, Q["head"], head_rot, face, rng, hair)
    # --- bras : bras, avant-bras, renforts usés, manchettes, mains à doigts articulés ---------
    for key in ("R", "L"):
        sh, el, wr = Q["sh" + key], Q["el" + key], Q["wr" + key]
        capsule(suit, sh, el, .058, .05, suit_col)
        capsule(suit, el, wr, .05, .041, suit_col)
        ellipsoid(suit, el, (.06, .06, .06), worn, seg=10, rings=6)                       # coude renforcé, usé
        capsule(suit, sh + spine * .05, el + spine * .045, .011, .011, dark, seg=5, cap=1)  # couture
        capsule(suit, wr - (wr - el) * .14, wr, .047, .047, dark, seg=8, cap=2)            # manchette
        dirh = wr - el
        dirh /= np.linalg.norm(dirh) + 1e-9
        hand = wr + dirh * .06
        glove = rng.random() < .45
        hc = (.1, .1, .11) if glove else skin_col
        tgt = gear if glove else skin
        ellipsoid(tgt, hand, (.044, .019, .054), hc, rot=_look_rot(dirh), seg=10, rings=6)
        u, w_ = _frame(dirh)
        for k in range(4):                                                               # doigts : 2 phalanges
            base_ = hand + dirh * .045 + u * (-.03 + k * .02)
            curl = rng.uniform(.2, .9)
            mid = base_ + dirh * .03 + w_ * (-.012 * curl)
            tip = mid + dirh * .022 * (1 - curl * .5) + w_ * (-.02 * curl)
            capsule(tgt, base_, mid, .0095, .0085, hc, seg=6, cap=2)
            capsule(tgt, mid, tip, .0085, .0075, hc, seg=6, cap=2)
        capsule(tgt, hand - u * .038, hand - u * .058 + dirh * .04, .011, .009, hc, seg=6, cap=2)  # pouce
    # --- jambes : cuisses, genoux renforcés, jambes, bottes -----------------------------------
    for key in ("R", "L"):
        hp, kn, an, toe = Q["hip" + key], Q["kn" + key], Q["an" + key], Q["toe" + key]
        capsule(suit, hp, kn, .086, .066, suit_col)
        capsule(suit, kn, an, .062, .049, suit_col)
        ellipsoid(suit, kn, (.074, .074, .074), worn, seg=10, rings=6)
        capsule(suit, hp + spine * .07, kn + spine * .06, .011, .011, dark, seg=5, cap=1)
        ellipsoid(suit, hp + (kn - hp) * .45 + F["shin" + key][:, 0] * .07, (.05, .06, .025), pad,
                  rot=F["shin" + key], seg=10, rings=6)                                    # poche de cuisse
        capsule(gear, an - (an - kn) * .2, an, .062, .058, (.12, .12, .13), seg=10, cap=2)  # tige de botte
        capsule(gear, an, toe, .056, .05, (.09, .09, .1), seg=10)                            # pied
        ellipsoid(gear, (an + toe) / 2 - F["shin" + key][:, 1] * -.01, (.065, .03, .13), (.05, .05, .055),
                  rot=_look_rot(toe - an), seg=10, rings=5)                                  # semelle
    # --- saleté, taches ----------------------------------------------------------------------
    _stains(suit, rng, .4)
    _stains(gear, rng, .25)
    # --- construction (combinaison légèrement brillante, peau morte, équipement) -------------------
    root = Entity(parent=parent, name=f"corpse_{who or 'anon'}")
    parts = []
    for mb, mat, nm in ((suit, "suitcloth", "suit"), (skin, "deadskin", "skin"), (gear, "gunmetal", "gear")):
        if mb.count:
            e = mb.build(parent=root, material=mat, name=nm)
            e.setTwoSided(True)
            parts.append(e)
    if visor is not None:
        ve = visor.build(parent=root, name="visor", tangents=False)
        ve.setTransparency(TransparencyAttrib.MAlpha)
        m = Material()
        m.setSpecular((1.2, 1.2, 1.2, 1))
        m.setShininess(90)
        ve.setMaterial(m, 1)
        ve.setTexture(frost_texture()._texture, 1)                  # visière embuée et gelée
        ve.setBin('transparent', 12)
    # couche de givre (scintille sous la lampe)
    if C.CORPSE_FROST > 0:
        fm = _frost_layer([suit, skin], rng)
        fe = fm.build(parent=root, name="frost", tangents=False)
        fe.setTexture(frost_texture()._texture, 1)
        fe.setTransparency(TransparencyAttrib.MAlpha)
        fe.setDepthWrite(False)
        fe.setBin('transparent', 11)
        m = Material()
        m.setSpecular((1.4, 1.45, 1.5, 1))
        m.setShininess(110)
        fe.setMaterial(m, 1)
    # badge nominatif sur la poitrine
    if who is not None:
        side = np.cross(spine, front)
        side /= np.linalg.norm(side) + 1e-9
        c0 = Q["waist"] + F_c[:, 1] * .2 + front * .136 - side * .075
        hw, hh = .055, .021
        bm = MeshBuilder()
        pts = [c0 - side * hw - spine * hh, c0 + side * hw - spine * hh, c0 + side * hw + spine * hh,
               c0 - side * hw + spine * hh]
        bm.quad(*[tuple(p.tolist()) for p in pts], tuple(front.tolist()), (1, 1, 1, 1))
        be = bm.build(parent=root, texture=badge_texture(who), name="badge", tangents=False)
        be.setTwoSided(True)
    info = {"torso": (Q["waist"] + Q["chest"]) / 2, "head": Q["head"], "hands": (Q["wrR"], Q["wrL"]),
            "feet": (Q["anR"], Q["anL"]), "front": front, "support": y0, "helmet": bool(helmet)}
    return root, info


# ============================================================================
# OBJETS PERSONNELS ET CASQUE POSÉ À CÔTÉ
# ============================================================================
def build_props(parent, who, info, x, z, yaw, rng, y_floor=0.0):
    """Objets liés à l'histoire, posés près des mains du corps (ou sur la console)."""
    root = Entity(parent=parent, name=f"props_{who or 'anon'}")
    hands = [np.asarray(h) for h in info["hands"]]
    kinds = PERSONAL.get(who, PERSONAL[None])
    mb = MeshBuilder(uv_scale=.2)
    glow = MeshBuilder()
    photos = []
    for k, kind in enumerate(kinds):
        h = hands[k % 2]
        ang = rng.uniform(0, 360)
        off = np.array([math.cos(math.radians(ang)) * .2, 0, math.sin(math.radians(ang)) * .2])
        px, pz = h[0] + off[0], h[2] + off[2]
        py = max(y_floor, h[1] - .04) if info["support"] > 0 or who == "vasseur" else y_floor
        py = max(py, y_floor)
        if kind == "tablet":
            mb.box_rot((px, py + .006, pz), (.2, .012, .28), ang, (.07, .07, .08))
            glow.box_rot((px, py + .0125, pz), (.18, .001, .25), ang, (.03, .06, .07))       # écran mort
            for _ in range(5):                                                          # fissures
                a2 = math.radians(rng.uniform(0, 360))
                L = rng.uniform(.05, .12)
                mb.box_rot((px + math.cos(a2) * L / 2, py + .0135, pz + math.sin(a2) * L / 2), (L, .001, .003),
                           -math.degrees(a2), (.6, .65, .7))
        elif kind == "photo":
            photos.append((px, py + .003, pz, ang))
        elif kind == "flashlight":
            mb.cylinder((px, py + .022, pz), .02, .2, (.15, .15, .16), 10, 'x' if k % 2 else 'z')
            mb.cylinder((px + (.1 if k % 2 else 0), py + .022, pz + (0 if k % 2 else .1)), .026, .04,
                        (.2, .2, .22), 10, 'x' if k % 2 else 'z')                         # tête de lampe, éteinte
        elif kind == "pistol":                                                          # arme vide, culasse ouverte
            mb.box_rot((px, py + .02, pz), (.04, .035, .2), ang, (.16, .16, .17))
            mb.box_rot((px, py + .035, pz), (.03, .02, .14), ang, (.12, .12, .13))
        elif kind == "notebook":
            mb.box_rot((px - .07, py + .008, pz), (.14, .012, .2), ang + 4, (.25, .12, .1))   # couverture
            mb.box_rot((px - .07, py + .016, pz), (.13, .004, .19), ang + 4, (.85, .83, .76))  # page gauche
            mb.box_rot((px + .07, py + .016, pz), (.13, .004, .19), ang - 4, (.83, .81, .74))  # page droite
        elif kind == "syringe":
            mb.cylinder((px, py + .01, pz), .008, .09, (.85, .88, .9), 8, 'x')
            mb.cylinder((px - .055, py + .01, pz), .003, .03, (.7, .7, .72), 6, 'x')
            mb.cylinder((px + .055, py + .01, pz), .0012, .03, (.8, .8, .82), 4, 'x')     # aiguille
        elif kind == "wrench":
            mb.box_rot((px, py + .01, pz), (.04, .015, .3), ang, (.5, .5, .52))
            mb.box_rot((px, py + .012, pz + .15), (.09, .02, .05), ang, (.5, .5, .52))
    # casque posé à côté (pour ceux qui ne le portent pas)
    if not info["helmet"] and rng.random() < C.CORPSE_HELMET_BESIDE:
        ang = rng.uniform(0, 6.28)
        hx, hz = info["torso"][0] + math.cos(ang) * .6, info["torso"][2] + math.sin(ang) * .6
        ellipsoid(mb, (hx, y_floor + .14, hz), (.155, .14, .16), (.76, .77, .78), seg=14, rings=9)
        ellipsoid(mb, (hx + .07, y_floor + .15, hz), (.04, .09, .1), (.08, .09, .1), seg=10, rings=6)   # visière
    if mb.count:
        e = mb.build(parent=root, material="painted", name="props")
        e.setTwoSided(True)
    if glow.count:
        ge = glow.build(parent=root, name="props_screens", tangents=False)
        m = Material()
        m.setSpecular((1.5, 1.5, 1.5, 1))
        m.setShininess(80)
        ge.setMaterial(m, 1)
    for (px, py, pz, ang) in photos:
        pm = MeshBuilder()
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        hw, hd = .065, .05
        pts = [(px + (-hw) * ca + (-hd) * sa, py, pz - (-hw) * sa + (-hd) * ca),
               (px + hw * ca + (-hd) * sa, py, pz - hw * sa + (-hd) * ca),
               (px + hw * ca + hd * sa, py, pz - hw * sa + hd * ca),
               (px + (-hw) * ca + hd * sa, py, pz - (-hw) * sa + hd * ca)]
        pm.quad(*pts, (0, 1, 0), (1, 1, 1, 1))
        pe = pm.build(parent=root, texture=photo_texture(rng.randint(0, 9999)), name="photo", tangents=False)
        pe.setTwoSided(True)
    return root


# ============================================================================
# CADAVRE FOUILLABLE
# ============================================================================
class Corpse(loot.Interactable):
    """
    Corps d'un membre d'équipage (story.CREW), fouillable (fouille = vulnérable).
    y0 : hauteur du support (0 = sol, ~0,9 = table d'opération).
    """
    hold_time = C.SEARCH_TIME

    def __init__(self, level, builders, x, z, yaw, rng, uniform_col=None, crew=None, y0=0.0, parent=None,
                 pose=None, helmet=None):
        self.level = level
        self.searched = False
        self.crew = crew
        self.infested = rng.random() < C.INFESTED_CORPSE_CHANCE and y0 == 0.0
        self.contents = loot.roll_contents("corpse", rng, 1, 2)
        dec = builders["decal"]
        uni = uniform_col or rng.choice([(.35, .3, .2), (.2, .25, .32), (.4, .38, .35), (.45, .2, .12)])
        pose = pose or rng.choice(["slumped", "curled", "facedown"])
        if helmet is None:
            helmet = rng.random() < .3
        self.pose = pose
        self.args = (parent, x, y0, z, yaw, pose, uni, crew, helmet)
        self.seed = rng.randint(0, 999999)
        self.hallucinated = False
        self.room = level.room_at(x, z)
        self._build()
        tx, ty, tz = self.info["torso"]
        self.pos = (float(tx), float(ty) + .25, float(tz))
        a = math.radians(yaw)
        ca, sa = math.cos(a), math.sin(a)

        def Lw(lx, lz):  # local -> monde
            return (x + lx * ca + lz * sa, z - lx * sa + lz * ca)

        # --- décalques : sang séché sombre, traînées, traces de mains -----------------
        dried = (.38, .14, .12, .95)
        if y0 == 0.0:
            px, pz = float(tx), float(tz)
            dec.decal((px, .012, pz), rng.uniform(1.3, 2.0), rng.uniform(0, 360), dried)
            dec.decal((px + rng.uniform(-.5, .5), .013, pz + rng.uniform(-.5, .5)), rng.uniform(.5, .9),
                      rng.uniform(0, 360), (.28, .09, .08, .9))
        else:
            dec.decal((x, .012, z), rng.uniform(1.0, 1.5), rng.uniform(0, 360), dried)
        if pose == "crawl" and "smear" in builders:
            for k in range(1, 5):                     # il s'est traîné jusqu'ici
                sx, sz = Lw(rng.uniform(-.1, .1), -.35 - k * .55)
                builders["smear"].decal((sx, .014, sz), rng.uniform(.7, .9), yaw + rng.uniform(-15, 15),
                                        (.48, .19, .16, .85))
        if "hand" in builders:
            for _ in range(rng.randint(1, 3)):
                hx, hz = Lw(rng.uniform(-.8, .8), rng.uniform(-.3, 1.2))
                builders["hand"].decal((hx, .015, hz), rng.uniform(.22, .3), rng.uniform(0, 360), (.42, .14, .11, .9))
        if self.infested:
            mb = builders["struct"]
            for _ in range(3):                        # bosses suspectes sous la combinaison
                bx = float(tx) + rng.uniform(-.12, .12)
                bz = float(tz) + rng.uniform(-.15, .15)
                mb.box_rot((bx, float(ty) + .16, bz), (.09, .07, .09), rng.uniform(0, 90), (.12, .05, .08))
        level.add_interactable(self, self.pos[0], self.pos[2])

    def _build(self, look_at=None, jitter=0):
        parent, x, y0, z, yaw, pose, uni, crew, helmet = self.args
        rng = random.Random(self.seed + jitter)
        self.body, self.info = build_body(parent, x, y0, z, yaw, pose, uni, rng, who=crew, helmet=helmet,
                                          look_at=look_at)
        self.entity = self.body
        self.props = build_props(parent, crew, self.info, x, z, yaw, random.Random(self.seed + 1), 0.0)

    # ------------------------------------------------------------------
    def hallucinate(self, look_from):
        """
        Hallucination (infection avancée) : pendant que le joueur n'est pas là, le
        corps a « bougé » — légère nouvelle pose, tête tournée vers lui.
        """
        if self.hallucinated:
            return
        self.hallucinated = True
        destroy(self.body)
        destroy(self.props)
        self._build(look_at=look_from, jitter=7)

    def prompt(self, game):
        if self.searched:
            return None
        if self.crew is not None:
            import story
            name = story.CREW[self.crew]["name"].split(",")[0]
            return f"Fouiller le corps (badge : {name}) — maintenir"
        return "Fouiller le cadavre (maintenir)"

    def on_hold(self, game, dt):
        """Pendant la fouille (maintenir) : bruits de tissu réguliers, petite vibration."""
        self._rustle_t = getattr(self, "_rustle_t", 0.0) - dt
        if self._rustle_t <= 0:
            self._rustle_t = random.uniform(.35, .6)
            game.audio.play_at("rustle", self.pos, .55, random.uniform(.85, 1.15))
            game.inp.rumble(.12, .05, 90)

    def interact(self, game):
        if self.searched:
            return
        self.searched = True
        game.audio.play_at("rustle", self.pos, .8)
        if self.infested:
            game.hud.message("Quelque chose bouge sous les vêtements !", color.red)
            game.aliens.burst_from_corpse(self.pos, 1 + (1 if random.random() < .4 else 0))
            game.horror.scripted_scare(.5)
        left = loot.give_contents(game, self.contents, "Cadavre fouillé")
        self.contents = left
        if left:
            self.searched = False
