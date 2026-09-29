# -*- coding: utf-8 -*-
"""
corpses.py — Corps de l'équipage du Kerguelen, construits par code.

  * silhouette organique : capsules et ellipsoïdes lisses (aucun cube), tête,
    cou, torse, bassin, bras et jambes en plusieurs segments, mains avec
    doigts, bottes ;
  * combinaison épaisse (matériau légèrement brillant) : plis, coutures le
    long des membres, renforts aux genoux et aux coudes, ceinture, col ou
    casque fêlé, bande de couleur selon le poste, badge nominatif (texture
    générée : nom et fonction) ; peau mate ;
  * poses crédibles : affalé contre un mur, recroquevillé, face contre
    terre, assis à une console la tête sur le bureau, tentant de ramper vers
    une porte, allongé (table d'opération) ;
  * visages peu visibles : tête tournée, penchée dans l'ombre ou casque ;
  * décalques : sang séché sombre, traînée, traces de mains, ongles sur les
    murs (horreur suggestive, sans gore excessif).
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw
from ursina import Entity, Texture

import config as C
import textures
from geometry import MeshBuilder

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

SKIN_TONES = [(.52, .4, .34), (.36, .26, .21), (.63, .5, .44), (.45, .33, .27)]


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


def capsule(mb, a, b, r0, r1, col, seg=10, cap=4):
    """Capsule effilée de a (rayon r0) à b (rayon r1), normales lisses, UV continues."""
    a, b = _v(a), _v(b)
    d = b - a
    L = np.linalg.norm(d)
    if L < 1e-5:
        return ellipsoid(mb, a, (r0, r0, r0), col)
    d /= L
    u, w = _frame(d)
    rings = []
    # hémisphère de départ, tube, hémisphère d'arrivée
    for k in range(cap, 0, -1):
        t = (k / cap) * math.pi / 2
        rings.append((a - d * r0 * math.sin(t), r0 * math.cos(t), -math.sin(t)))
    for k in range(3):
        f = k / 2
        rings.append((a + d * L * f, r0 + (r1 - r0) * f, 0.0))
    for k in range(1, cap + 1):
        t = (k / cap) * math.pi / 2
        rings.append((b + d * r1 * math.sin(t), r1 * math.cos(t), math.sin(t)))
    cc = (col[0], col[1], col[2], 1.0)
    base = mb.count
    total = L + r0 + r1
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
            mb.t.extend((s / seg * math.pi * (r0 + r1) / .45, along / .45))   # tissu : ~45 cm par motif
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
    cc = (col[0], col[1], col[2], 1.0)
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


# ============================================================================
# POSES (coordonnées locales : x à droite, y en haut, z vers l'avant du corps)
# Points : pelvis, chest, neck, head, sh (épaules), el (coudes), wr (poignets),
# hip, kn (genoux), an (chevilles), toe ; suffixes L / R.
# « face » : direction du visage (pour la cacher : vers le sol, le mur, le bureau).
# ============================================================================
def _pose(kind, rng):
    j = lambda s=.03: rng.uniform(-s, s)            # petites variations
    P = {}
    if kind == "slumped":           # affalé, assis contre un mur (mur derrière : z négatif)
        P.update(pelvis=(0, .14, 0), chest=(j(), .52, -.13), neck=(.03, .72, -.1), head=(.13 + j(), .78, .0),
                 face=(.5, -.8, .35),
                 shL=(-.19, .62, -.12), shR=(.19, .62, -.12), elL=(-.3, .38, .0), elR=(.29, .36, .02),
                 wrL=(-.26, .16, .22 + j()), wrR=(.34, .07, .15 + j()), hipL=(-.1, .12, .02), hipR=(.1, .12, .02),
                 knL=(-.18, .36, .4), knR=(.2, .14, .52), anL=(-.2, .07, .7), anR=(.26, .07, .95),
                 toeL=(-.21, .1, .82), toeR=(.28, .12, 1.06), front=(0, .15, 1))
    elif kind == "curled":          # recroquevillé sur le côté, face vers les genoux
        P.update(pelvis=(0, .17, 0), chest=(.08, .19, .44), neck=(.14, .18, .64), head=(.2, .17, .76),
                 face=(.6, -.4, -.3),
                 shL=(.02, .31, .44), shR=(.02, .07, .44), elL=(.28, .27, .3), elR=(.25, .07, .28),
                 wrL=(.33, .22, .58), wrR=(.32, .07, .6), hipL=(0, .27, 0), hipR=(0, .08, 0),
                 knL=(.42, .26, .08), knR=(.4, .09, .02), anL=(.3, .23, -.33), anR=(.3, .08, -.38),
                 toeL=(.4, .22, -.4), toeR=(.4, .06, -.45), front=(1, 0, 0))
    elif kind == "facedown":        # face contre terre, un bras tendu
        P.update(pelvis=(0, .13, 0), chest=(j(), .14, .5), neck=(0, .13, .67), head=(.06, .12, .8),
                 face=(.3, -1, .1),
                 shL=(-.21, .14, .45), shR=(.21, .14, .45), elL=(-.36, .08, .7), elR=(.34, .07, .3),
                 wrL=(-.3, .06, .98), wrR=(.3, .06, .06), hipL=(-.1, .12, -.05), hipR=(.1, .12, -.05),
                 knL=(-.13, .09, -.5), knR=(.16, .09, -.48), anL=(-.14, .08, -.92), anR=(.24, .08, -.9),
                 toeL=(-.14, .02, -.98), toeR=(.25, .02, -.97), front=(0, -1, 0))
    elif kind == "desk":            # assis, la tête sur le bureau (bureau devant : z positif)
        P.update(pelvis=(0, .5, 0), chest=(j(.02), .83, .22), neck=(0, .96, .36), head=(.05, .99, .48),
                 face=(.2, -1, .4),
                 shL=(-.2, .93, .26), shR=(.2, .93, .26), elL=(-.32, .92, .5), elR=(.3, .93, .52),
                 wrL=(-.13, .95, .6), wrR=(.16, .95, .6), hipL=(-.1, .49, .0), hipR=(.1, .49, .0),
                 knL=(-.13, .5, .44), knR=(.14, .5, .44), anL=(-.15, .08, .48), anR=(.17, .08, .5),
                 toeL=(-.15, .06, .6), toeR=(.17, .06, .62), front=(0, -.3, 1))
    elif kind == "crawl":           # tentait de ramper vers une porte (vers +z)
        P.update(pelvis=(0, .14, 0), chest=(.02, .19, .5), neck=(.03, .2, .68), head=(.04, .16, .8),
                 face=(0, -1, .5),
                 shL=(-.2, .2, .46), shR=(.2, .2, .46), elL=(-.36, .09, .45), elR=(.26, .1, .78),
                 wrL=(-.3, .07, .72), wrR=(.18, .06, 1.05), hipL=(-.1, .13, -.04), hipR=(.1, .13, -.04),
                 knL=(-.38, .1, -.3), knR=(.14, .09, -.5), anL=(-.3, .08, -.72), anR=(.17, .08, -.92),
                 toeL=(-.3, .02, -.78), toeR=(.17, .02, -.98), front=(0, -1, 0))
    else:                           # "supine" : allongé sur le dos (table d'opération), tête tournée
        P.update(pelvis=(0, .12, 0), chest=(0, .14, .5), neck=(0, .14, .68), head=(-.05, .15, .8),
                 face=(-1, .2, .1),
                 shL=(-.21, .13, .46), shR=(.21, .13, .46), elL=(-.27, .09, .2), elR=(.27, .09, .2),
                 wrL=(-.25, .08, -.06), wrR=(.26, .08, -.05), hipL=(-.1, .12, -.05), hipR=(.1, .12, -.05),
                 knL=(-.11, .12, -.5), knR=(.12, .12, -.5), anL=(-.12, .1, -.92), anR=(.13, .1, -.92),
                 toeL=(-.14, .2, -.97), toeR=(.15, .2, -.97), front=(0, 1, 0))
    return {k: _v(v) for k, v in P.items()}


# ============================================================================
# BADGE (texture générée : nom + fonction)
# ============================================================================
_badges = {}


def badge_texture(who):
    if who in _badges:
        return _badges[who]
    name, role, stripe = ROLES.get(who, ("INCONNU", "Équipage", (.5, .5, .5)))
    w, h = 256, 96
    img = Image.new("RGBA", (w, h), (205, 205, 196, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(60, 60, 60, 255), width=3)
    d.rectangle((0, 0, 22, h), fill=tuple(int(c * 255) for c in stripe) + (255,))
    try:
        f1 = textures._font(34)
        f2 = textures._font(20)
    except Exception:
        f1 = f2 = None
    d.text((32, 10), name, fill=(25, 25, 25, 255), font=f1)
    d.text((32, 56), role, fill=(55, 55, 55, 255), font=f2)
    # usure : taches sombres
    arr = np.asarray(img).astype(np.float32)
    rng = np.random.default_rng(abs(hash(who)) % 9999)
    for _ in range(6):
        cx, cy = rng.integers(0, w), rng.integers(0, h)
        yy, xx = np.mgrid[0:h, 0:w]
        m = np.exp(-(((xx - cx) / rng.uniform(6, 20)) ** 2 + ((yy - cy) / rng.uniform(4, 12)) ** 2))
        arr[..., :3] *= (1 - .45 * m[..., None])
    t = Texture(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA"))
    _badges[who] = t
    return t


# ============================================================================
# CORPS COMPLET
# ============================================================================
def build_body(parent, x, y0, z, yaw, pose, suit_col, rng, who=None, helmet=None):
    """
    Construit un corps (entité sous 'parent') et renvoie (racine, info).
    info : points utiles en coordonnées monde (torse, tête) pour les décalques.
    """
    P = _pose(pose, rng)
    a = math.radians(yaw)
    ca, sa = math.cos(a), math.sin(a)

    def W(p):                        # local -> monde (repère Ursina : rotation autour de y)
        return np.array([x + p[0] * ca + p[2] * sa, y0 + p[1], z - p[0] * sa + p[2] * ca])

    def Wd(d):
        return np.array([d[0] * ca + d[2] * sa, d[1], -d[0] * sa + d[2] * ca])

    Q = {k: W(v) for k, v in P.items() if k not in ("face", "front")}
    suit = MeshBuilder()
    skin = MeshBuilder()
    dark = tuple(c * .55 for c in suit_col)
    pad = tuple(min(1, c * .7 + .05) for c in suit_col)
    stripe = ROLES.get(who, (None, None, (.45, .45, .45)))[2]
    skin_col = rng.choice(SKIN_TONES)
    # --- torse, bassin, ceinture ------------------------------------------------
    capsule(suit, Q["pelvis"], Q["chest"], .15, .18, suit_col, seg=12)
    mid = (Q["pelvis"] + Q["chest"]) / 2
    spine = Q["chest"] - Q["pelvis"]
    spine /= np.linalg.norm(spine)
    ellipsoid(suit, Q["pelvis"] + spine * .02, (.17, .055, .15), dark, rot=_look_rot(spine, Wd(P["front"])))
    # plis horizontaux du tissu sur le ventre
    for k in range(2):
        ellipsoid(suit, mid + spine * (k * .08 - .05), (.172, .018, .162), tuple(c * .88 for c in suit_col),
                  rot=_look_rot(spine, Wd(P["front"])), seg=10, rings=5)
    # épaules et bande de couleur du poste
    capsule(suit, Q["shL"], Q["shR"], .07, .07, suit_col, seg=10)
    for s in ("shL", "shR"):
        # écusson de couleur du poste, sur le haut du bras
        el = Q["el" + s[-1]]
        d_ = (el - Q[s]) / (np.linalg.norm(el - Q[s]) + 1e-9)
        ellipsoid(suit, Q[s] + d_ * .07, (.062, .02, .062), stripe, rot=_look_rot(np.cross(d_, spine) + 1e-6),
                  seg=10, rings=5)
    # col de la combinaison (anneau épais) ou casque
    capsule(suit, Q["chest"] + spine * .06, Q["neck"], .1, .075, dark, seg=12)
    capsule(skin, Q["neck"], Q["head"] - (Q["head"] - Q["neck"]) * .35, .045, .05, skin_col, seg=8)
    face = Wd(P["face"])
    face /= np.linalg.norm(face) + 1e-9
    head_rot = _look_rot(face)
    if helmet:
        # casque : coque + visière sombre fêlée (le visage reste invisible)
        ellipsoid(suit, Q["head"], (.155, .165, .16), (.78, .79, .8), rot=head_rot, seg=14, rings=10)
        ellipsoid(suit, Q["head"] + face * .07, (.12, .1, .1), (.03, .035, .04), rot=head_rot, seg=12, rings=8)
        # visière fêlée : un impact et des fissures en étoile
        u_, w_ = _frame(face)
        hit = Q["head"] + face * .168 + u_ * .03
        for k in range(6):
            a_ = k * math.pi / 3 + rng.uniform(-.3, .3)
            end = hit + (u_ * math.cos(a_) + w_ * math.sin(a_)) * rng.uniform(.04, .08) - face * .012
            capsule(suit, hit, end, .0035, .002, (.75, .78, .8), seg=4, cap=1)
    else:
        ellipsoid(skin, Q["head"], (.1, .12, .115), skin_col, rot=head_rot, seg=14, rings=10)
        # cheveux (calotte sombre) : le visage est tourné vers le sol / le mur / le bureau
        hair = rng.choice([(.08, .06, .05), (.18, .12, .07), (.05, .05, .05), (.35, .33, .3)])
        ellipsoid(skin, Q["head"] - face * .025 + np.array([0, .02, 0]), (.106, .11, .11), hair, rot=head_rot,
                  seg=12, rings=8)
    # --- bras ---------------------------------------------------------------------
    for side in ("L", "R"):
        sh, el, wr = Q["sh" + side], Q["el" + side], Q["wr" + side]
        capsule(suit, sh, el, .058, .05, suit_col)
        capsule(suit, el, wr, .05, .042, suit_col)
        ellipsoid(suit, el, (.06, .06, .06), pad, seg=10, rings=6)                    # renfort de coude
        # couture le long du bras
        capsule(suit, sh + np.array([0, .05, 0]), el + np.array([0, .045, 0]), .012, .012, dark, seg=5, cap=1)
        capsule(suit, wr - (wr - el) * .12, wr, .048, .048, dark, seg=8, cap=2)          # poignet renforcé
        # main : paume + doigts (gants pour certains)
        hand = wr + (wr - el) / (np.linalg.norm(wr - el) + 1e-9) * .07
        glove = rng.random() < .5
        hc = (.1, .1, .11) if glove else skin_col
        tgt = skin if not glove else suit
        dirh = (wr - el) / (np.linalg.norm(wr - el) + 1e-9)
        ellipsoid(tgt, hand, (.045, .02, .055), hc, rot=_look_rot(dirh), seg=8, rings=6)
        u, w_ = _frame(dirh)
        for k in range(4):
            base_ = hand + dirh * .045 + u * (-.03 + k * .02)
            tip = base_ + dirh * (.05 + .01 * (k in (1, 2))) + np.array([0, -.02, 0]) * rng.random()
            capsule(tgt, base_, tip, .01, .008, hc, seg=5, cap=2)
        capsule(tgt, hand - u * .04, hand - u * .06 + dirh * .04, .011, .009, hc, seg=5, cap=2)   # pouce
    # --- jambes -------------------------------------------------------------------
    for side in ("L", "R"):
        hp, kn, an, toe = Q["hip" + side], Q["kn" + side], Q["an" + side], Q["toe" + side]
        capsule(suit, hp, kn, .085, .065, suit_col)
        capsule(suit, kn, an, .062, .048, suit_col)
        ellipsoid(suit, kn, (.075, .075, .075), pad, seg=10, rings=6)                   # genouillère
        capsule(suit, hp + np.array([0, .07, 0]), kn + np.array([0, .06, 0]), .012, .012, dark, seg=5, cap=1)
        # botte
        capsule(suit, an, toe, .058, .05, (.09, .09, .1), seg=10)
        capsule(suit, an - (an - kn) * .18, an, .06, .058, (.12, .12, .13), seg=10, cap=2)
    # --- construction (combinaison légèrement brillante, peau mate) --------------------
    root = Entity(parent=parent, name=f"corpse_{who or 'anon'}")
    s_e = suit.build(parent=root, material="suitcloth", name="suit")
    k_e = skin.build(parent=root, material="skin", name="skin")
    for e in (s_e, k_e):
        e.setTwoSided(True)
    # badge nominatif sur la poitrine (petit quad texturé, plaqué sur le torse)
    if who is not None:
        fr = Wd(P["front"])
        fr = fr - spine * np.dot(fr, spine)
        fr /= np.linalg.norm(fr) + 1e-9
        side = np.cross(spine, fr)
        side /= np.linalg.norm(side) + 1e-9
        c0 = Q["chest"] - spine * .12 + fr * .185 + side * .07
        hw, hh = .055, .021
        bm = MeshBuilder()
        pts = [c0 - side * hw - spine * hh, c0 + side * hw - spine * hh, c0 + side * hw + spine * hh,
               c0 - side * hw + spine * hh]
        bm.quad(*[tuple(p.tolist()) for p in pts], tuple(fr.tolist()), (1, 1, 1, 1))
        be = bm.build(parent=root, texture=badge_texture(who), name="badge", tangents=False)
        be.setTwoSided(True)
    info = {"torso": (mid + Q["chest"]) / 2, "head": Q["head"], "hands": (Q["wrL"], Q["wrR"]),
            "feet": (Q["anL"], Q["anR"]), "front": Wd(P["front"])}
    return root, info
