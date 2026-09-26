# -*- coding: utf-8 -*-
"""
document_ui.py — Documents de l'histoire : rendu, lecture, journal, commandes.

  * rendu de chaque document dans une texture (PIL), selon son type :
      helios   papier officiel avec en-tête et logo Helios Biotech ;
      paper    papier jauni, lignes, écriture manuscrite ;
      form     fiche / rapport tapé à la machine (+ image jointe) ;
      terminal écran vert de terminal (journal de bord) ;
      audio    transcription d'enregistrement (+ forme d'onde) ;
      postit   petit carré jaune écrit au feutre ;
      photo    image granuleuse (dessin, schéma) ;
      video    image de caméra granuleuse + transcription ;
  * images générées par code : dessin de la créature dans la grille,
    scanner cérébral, plan de ventilation tiré du VRAI plan de la partie,
    visage de la Dr Keating (vidéo), forme d'onde audio ;
  * DocumentLog : documents présents dans la partie, trouvés, lus ;
  * DocumentReader : affichage en grand, SANS mettre le jeu en pause ;
  * JournalUI : journal chronologique (J / bouton Create), emplacements vides ;
  * ControlsOverlay : écran des commandes (I).

Les textes eux-mêmes sont dans story.py.
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from ursina import Entity, Text, Texture, camera, color, window, destroy

import config as C
import story

# ============================================================================
# POLICES (Windows / macOS / Linux, avec repli sur la police intégrée)
# ============================================================================
_URSINA_FONTS = os.path.join(os.path.dirname(__import__('ursina').__file__), 'fonts')
FONT_CANDIDATES = {
    # écriture manuscrite : Ink Free et Segoe Print existent sous Windows 10/11
    "hand": ["Inkfree.ttf", "segoepr.ttf", "segoesc.ttf", "comic.ttf", "Comic Sans MS.ttf",
             "FreeSansOblique.ttf", "DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf"],
    "marker": ["Inkfree.ttf", "comicbd.ttf", "segoeprb.ttf", "FreeSansBold.ttf", "DejaVuSans-Bold.ttf"],
    "serif": ["georgia.ttf", "times.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "FreeSerif.ttf"],
    "serif_bold": ["georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf",
                   "FreeSerifBold.ttf"],
    "mono": ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf",
             os.path.join(_URSINA_FONTS, "VeraMono.ttf")],
    "sans": ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
             os.path.join(_URSINA_FONTS, "OpenSans-Regular.ttf")],
    "sans_bold": ["arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
                  os.path.join(_URSINA_FONTS, "OpenSans-Regular.ttf")],
}
_font_cache = {}


def font(kind, size):
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    for name in FONT_CANDIDATES[kind]:
        try:
            f = ImageFont.truetype(name, size)
            break
        except Exception:
            continue
    if f is None:
        try:
            f = ImageFont.load_default(size=size)
        except TypeError:
            f = ImageFont.load_default()
    _font_cache[key] = f
    return f


def _wrap(text, fnt, width):
    """Découpe le texte en lignes (mesure réelle de la police)."""
    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for word in para.split(" "):
            test = (cur + " " + word).strip()
            if fnt.getlength(test) <= width or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _grain(img, amount=18, seed=0):
    """Grain photographique."""
    rng = np.random.default_rng(seed)
    a = np.asarray(img.convert("RGB"), np.int16)
    n = rng.normal(0, amount, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a + n, 0, 255).astype(np.uint8), "RGB")


def _paper(w, h, base, seed, fibers=True):
    """Fond de papier : couleur de base, taches et fibres."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    low = rng.normal(0, 1, (h // 40 + 2, w // 40 + 2))
    low = np.array(Image.fromarray(((low - low.min()) / (np.ptp(low) + 1e-6) * 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC), np.float32) / 255
    a = np.zeros((h, w, 3), np.float32)
    for i in range(3):
        a[..., i] = base[i] * (0.93 + 0.1 * low)
    # bords plus sombres (vieilli)
    edge = np.minimum(np.minimum(x, w - 1 - x), np.minimum(y, h - 1 - y)) / (0.08 * min(w, h))
    a *= (0.8 + 0.2 * np.clip(edge, 0, 1))[..., None]
    if fibers:
        a += rng.normal(0, 4, (h, w))[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


# ============================================================================
# IMAGES GÉNÉRÉES PAR CODE
# ============================================================================
def image_drawing(w=760, h=620, seed=7):
    """Dessin au crayon : longue silhouette recroquevillée dans une grille d'aération, yeux blancs."""
    rng = random.Random(seed)
    img = _paper(w, h, (226, 219, 196), seed)
    d = ImageDraw.Draw(img)
    pencil = (58, 56, 60)

    def scribble(p0, p1, n=3, wid=3):
        for _ in range(n):
            j = lambda: rng.uniform(-4, 4)    # noqa: E731
            d.line([(p0[0] + j(), p0[1] + j()), (p1[0] + j(), p1[1] + j())], fill=pencil, width=wid)

    # grille d'aération (cadre + barreaux)
    gx0, gy0, gx1, gy1 = 110, 70, w - 110, h - 140
    for _ in range(2):
        d.rectangle((gx0 + rng.uniform(-3, 3), gy0, gx1, gy1 + rng.uniform(-3, 3)), outline=pencil, width=4)
    for k in range(1, 9):
        x = gx0 + (gx1 - gx0) * k / 9
        scribble((x, gy0), (x + rng.uniform(-6, 6), gy1), 2, 3)
    # silhouette : trop longue, trop fine, pliée derrière les barreaux
    cx, cy = w * .52, gy0 + 90
    head = (cx - 26, cy - 36, cx + 26, cy + 30)
    for _ in range(3):
        d.ellipse((head[0] + rng.uniform(-3, 3), head[1], head[2], head[3] + rng.uniform(-3, 3)), outline=pencil,
                  width=3)
    d.ellipse(head, fill=(40, 38, 42))
    # deux points blancs pour les yeux
    for ex in (cx - 11, cx + 10):
        d.ellipse((ex - 6, cy - 8, ex + 6, cy + 4), fill=(246, 244, 236))
    # cou, torse maigre replié, membres interminables
    pts = [(cx, cy + 30), (cx - 8, cy + 120), (cx + 4, cy + 210), (cx - 30, cy + 260)]
    for a, b in zip(pts, pts[1:]):
        scribble(a, b, 4, 4)
    for s in (-1, 1):
        sh = (cx + s * 8, cy + 55)
        el = (cx + s * 150, cy + 20)
        hand = (cx + s * 190, cy + 190)
        scribble(sh, el, 3, 3)
        scribble(el, hand, 3, 3)
        for f in range(4):
            scribble(hand, (hand[0] + s * rng.uniform(5, 30), hand[1] + rng.uniform(15, 45)), 1, 2)
        kn = (cx + s * 120, cy + 300)
        scribble((cx - 30, cy + 260), kn, 3, 3)
        scribble(kn, (cx + s * 40, gy1 - 20), 3, 3)
    # hachures d'ombre
    for k in range(60):
        x = rng.uniform(gx0 + 10, gx1 - 10)
        y = rng.uniform(gy0 + 10, gy1 - 10)
        if abs(x - cx) < 60 and y < cy + 60:
            continue
        d.line([(x, y), (x + 22, y - 22)], fill=(110, 106, 104), width=1)
    # texte tremblé
    fnt = font("marker", 34)
    txt = "IL ÉTAIT DANS LA GRILLE. IL M'A REGARDÉ DORMIR."
    lines = _wrap(txt, fnt, w - 80)
    y = gy1 + 22
    for line in lines:
        x = 40
        for ch in line:
            d.text((x, y + rng.uniform(-4, 4)), ch, fill=(40, 30, 34), font=fnt)
            x += fnt.getlength(ch) + rng.uniform(-1, 2)
        y += 46
    # page arrachée : bord déchiré en haut
    torn = Image.new("L", (w, h), 255)
    td = ImageDraw.Draw(torn)
    edge = [(0, 0)] + [(x, rng.uniform(4, 22)) for x in range(0, w + 20, 18)] + [(w, 0)]
    td.polygon(edge, fill=0)
    bg = Image.new("RGB", (w, h), (18, 18, 20))
    return Image.composite(img, bg, torn)


def image_brainscan(size=520, seed=11):
    """Scanner cérébral (coupe axiale) en niveaux de gris, avec lésions sombres anormales."""
    rng = np.random.default_rng(seed)
    s = size
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    cx, cy = s / 2, s / 2
    nx, ny = (x - cx) / (s * .36), (y - cy) / (s * .44)
    r = np.sqrt(nx ** 2 + ny ** 2)
    img = np.zeros((s, s), np.float32)
    # crâne (anneau clair) et cerveau
    img += np.exp(-((r - 1.04) / .035) ** 2) * .95
    brain = r < 1.0
    ang = np.arctan2(ny, nx)
    gyri = .55 + .12 * np.sin(r * 38 + np.sin(ang * 9) * 2.2) + .06 * np.sin(ang * 23 + r * 11)
    img += brain * gyri
    # scissure centrale, ventricules
    img -= brain * np.exp(-(nx / .02) ** 2) * (np.abs(ny) > .15) * .45
    for sx in (-1, 1):
        img -= np.exp(-(((nx - sx * .13) / .07) ** 2 + (ny / .28) ** 2)) * .5
    # lésions : cortex visuel (arrière) et amygdales (tempes)
    les = [(0, .78, .22, .13), (-.18, .72, .12, .09), (.2, .7, .1, .08), (-.52, .12, .12, .1), (.5, .1, .13, .1),
           (.05, .55, .07, .06)]
    for lx, ly, rx, ry in les:
        blob = np.exp(-(((nx - lx) / rx) ** 2 + ((ny - ly) / ry) ** 2) ** 1.4)
        img -= blob * .55 * (1 + .3 * rng.normal(0, 1, (s, s)) * .2)
    img = np.clip(img, 0, 1)
    img += rng.normal(0, .045, (s, s))
    img = np.clip(img, 0, 1) * 235
    im = Image.fromarray(img.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(1.1)).convert("RGB")
    d = ImageDraw.Draw(im)
    f = font("mono", 18)
    d.text((12, 10), "IRM AXIALE  S-42", fill=(200, 200, 200), font=f)
    d.text((12, s - 30), "ANDREÏEV Y.  J15", fill=(200, 200, 200), font=f)
    d.text((s - 30, s // 2 - 10), "D", fill=(200, 200, 200), font=f)
    d.text((14, s // 2 - 10), "G", fill=(200, 200, 200), font=f)
    return im


def image_vents(level, w=820, h=560, seed=3):
    """Plan technique du VRAI vaisseau de la partie, ventilation surlignée au feutre rouge."""
    from generator import SOLID, ROOM, CORR, VENT
    rng = random.Random(seed)
    img = _paper(w, h, (214, 222, 230), seed, fibers=False)
    d = ImageDraw.Draw(img)
    if level is None:
        return img
    cs = min((w - 40) / level.W, (h - 70) / level.H)
    ox, oy = (w - cs * level.W) / 2, 50

    def P(i, j):          # la case j = 0 (côté hangar) en bas du plan
        return ox + i * cs, oy + (level.H - 1 - j) * cs

    # grille de plan
    for i in range(0, level.W + 1, 2):
        d.line([P(i, -1 + 1), (P(i, 0)[0], oy)], fill=(190, 202, 214), width=1)
    for i in range(level.W):
        for j in range(level.H):
            k = level.kind[i][j]
            if k == SOLID:
                continue
            x, y = P(i, j)
            col = {ROOM: (40, 60, 90), CORR: (70, 88, 110), VENT: (120, 130, 140)}[k]
            d.rectangle((x, y, x + cs, y + cs), outline=col, width=1)
    for r in level.rooms:
        x0, y0 = P(r.x, r.y + r.h - 1)
        x1, y1 = x0 + r.w * cs, y0 + r.h * cs
        d.rectangle((x0, y0, x1, y1), outline=(30, 45, 80), width=3)
        d.text((x0 + 4, y0 + 3), r.name.upper()[:14], fill=(30, 45, 80), font=font("mono", 11))
    # conduits d'aération au feutre rouge (trait épais, un peu tremblé)
    red = (200, 30, 30)
    for i in range(level.W):
        for j in range(level.H):
            if level.kind[i][j] == VENT:
                x, y = P(i, j)
                for _ in range(2):
                    d.ellipse((x + cs * .2 + rng.uniform(-2, 2), y + cs * .2 + rng.uniform(-2, 2),
                               x + cs * .8, y + cs * .8), fill=red)
    # flèches depuis le laboratoire (infirmerie) vers toutes les salles
    lab = level.room("medbay")
    if lab is not None:
        lx, ly = P(lab.x + lab.w / 2, lab.y + lab.h / 2)
        for r in level.rooms:
            if r is lab:
                continue
            tx, ty = P(r.x + r.w / 2, r.y + r.h / 2)
            dx, dy = tx - lx, ty - ly
            L = math.hypot(dx, dy) or 1
            ex, ey = tx - dx / L * 18, ty - dy / L * 18
            mx, my = (lx + ex) / 2 + rng.uniform(-20, 20), (ly + ey) / 2 + rng.uniform(-20, 20)
            d.line([(lx, ly), (mx, my), (ex, ey)], fill=red, width=3)
            a = math.atan2(ey - my, ex - mx)
            for s in (-1, 1):
                d.line([(ex, ey), (ex - math.cos(a + s * .5) * 14, ey - math.sin(a + s * .5) * 14)], fill=red,
                       width=3)
        d.ellipse((lx - 16, ly - 16, lx + 16, ly + 16), outline=red, width=4)
        d.text((lx + 18, ly - 30), "LABO", fill=red, font=font("marker", 22))
    d.text((24, 12), "KERGUELEN — RÉSEAU D'AÉRATION — PONT 1", fill=(30, 45, 80), font=font("mono", 18))
    f = font("marker", 40)
    d.text((w - 360, h - 62), "ça passe par l'air", fill=red, font=f)
    return img.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, fillcolor=(20, 20, 22))


def image_waveform(w=820, h=180, seed=5):
    """Forme d'onde de l'enregistrement (respiration, voix, silence)."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (w, h), (18, 14, 8))
    d = ImageDraw.Draw(img)
    n = 360
    t = np.linspace(0, 1, n)
    env = .15 + .25 * (np.sin(t * 40) > .3) * (t < .25) + .6 * ((t > .3) & (t < .55)) + .5 * ((t > .72) & (t < .9))
    amp = env * (0.5 + 0.5 * rng.random(n))
    for k in range(n):
        x = 10 + k * (w - 20) / n
        a = amp[k] * h * .42
        d.line([(x, h / 2 - a), (x, h / 2 + a)], fill=(255, 176, 60), width=2)
    d.line([(10, h / 2), (w - 10, h / 2)], fill=(90, 60, 20), width=1)
    return img


def image_keating(w=820, h=560, seed=23):
    """Image de caméra granuleuse du visage de la Dr Keating (générée par code)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w * .5, h * .5
    img = np.full((h, w), .08, np.float32)
    # cheveux / ombre de la tête
    img += np.exp(-(((x - cx) / 170) ** 2 + ((y - cy + 30) / 210) ** 2) ** 2) * .12
    # visage (ovale éclairé d'un côté)
    face = np.exp(-(((x - cx) / 118) ** 2 + ((y - cy + 10) / 160) ** 2) ** 3)
    light = np.clip(.55 + (cx - x) / 300, .2, 1.0)
    img += face * .7 * light
    # orbites, nez, bouche
    for sx in (-1, 1):
        img -= np.exp(-(((x - cx - sx * 45) / 30) ** 2 + ((y - cy + 25) / 16) ** 2)) * .35
        img += np.exp(-(((x - cx - sx * 45) / 7) ** 2 + ((y - cy + 25) / 4) ** 2)) * .15      # reflet des yeux
    img -= np.exp(-(((x - cx + 6) / 10) ** 2 + ((y - cy + 25 - 45) / 26) ** 2)) * .12
    img -= np.exp(-(((x - cx) / 40) ** 2 + ((y - cy + 25 - 95) / 6) ** 2)) * .25
    img += np.exp(-(((x - cx) / 60) ** 2 + ((y - cy + 25 - 108) / 14) ** 2)) * .05
    # cou et épaules
    img += np.exp(-(((x - cx) / 60) ** 2)) * (y > cy + 150) * .18 * light
    img += np.exp(-(((y - h) / 120) ** 2)) * np.exp(-(((x - cx) / 320) ** 2)) * .15
    # flou, lignes de balayage, déchirures horizontales, bruit
    im = Image.fromarray(np.clip(img * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(3))
    a = np.asarray(im, np.float32) / 255
    a *= (0.82 + 0.18 * (np.arange(h) % 4 < 2))[:, None]
    for _ in range(9):
        y0 = int(rng.integers(0, h - 10))
        hh = int(rng.integers(2, 14))
        a[y0:y0 + hh] = np.roll(a[y0:y0 + hh], int(rng.integers(-40, 40)), axis=1)
    a += rng.normal(0, .07, (h, w))
    a = np.clip(a, 0, 1)
    rgb = np.dstack([a * 205, a * 225, a * 215]).astype(np.uint8)
    im = Image.fromarray(rgb, "RGB")
    d = ImageDraw.Draw(im)
    f = font("mono", 22)
    d.ellipse((24, 24, 40, 40), fill=(220, 30, 30))
    d.text((50, 18), "REC   LABO-2   J23  03:17:44", fill=(230, 230, 230), font=f)
    d.text((24, h - 44), "SIGNAL DÉGRADÉ", fill=(200, 200, 200), font=f)
    return im


def reflection_image(w=1024, h=576):
    """Reflet dans la verrière du cockpit : silhouette du casque du joueur, très faible."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # reflet diagonal de la vitre
    for k in range(40):
        a = int(10 * (1 - k / 40))
        d.line([(w * .15 + k * 3, 0), (w * .45 + k * 3, h)], fill=(160, 190, 220, a), width=3)
    # casque et épaules (vus de dos dans le reflet)
    cx, cy = w * .5, h * .72
    d.ellipse((cx - 120, cy - 150, cx + 120, cy + 90), fill=(90, 110, 130, 38), outline=(170, 200, 230, 60),
              width=3)
    d.rectangle((cx - 260, cy + 60, cx + 260, h), fill=(80, 100, 120, 30))
    return img.filter(ImageFilter.GaussianBlur(6))


# ============================================================================
# RENDU D'UN DOCUMENT (texture)
# ============================================================================
def _logo(d, x, y, s):
    """Logo Helios Biotech : soleil stylisé."""
    orange = (226, 118, 28)
    d.ellipse((x - s * .38, y - s * .38, x + s * .38, y + s * .38), fill=orange)
    for k in range(12):
        a = k * math.pi / 6
        d.line([(x + math.cos(a) * s * .5, y + math.sin(a) * s * .5),
                (x + math.cos(a) * s * .75, y + math.sin(a) * s * .75)], fill=orange, width=max(2, int(s * .06)))
    d.ellipse((x - s * .16, y - s * .16, x + s * .16, y + s * .16), fill=(250, 244, 230))


def _stamp(img, text, xy, col=(190, 30, 30), size=46, angle=-12):
    lay = Image.new("RGBA", (int(size * len(text) * .72) + 40, size + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f = font("sans_bold", size)
    tw = f.getlength(text)
    d.rectangle((8, 8, tw + 28, size + 28), outline=col + (200,), width=5)
    d.text((18, 14), text, fill=col + (200,), font=f)
    lay = lay.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.paste(lay, xy, lay)


def _handwrite(img, lines, x, y, fnt, ink, line_h, rng, jitter=True):
    """Écrit des lignes « à la main » : légère inclinaison et tremblement par ligne."""
    for line in lines:
        if line:
            lay = Image.new("RGBA", (img.width, int(line_h * 1.6)), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            cx = x
            for word in line.split(" "):
                d.text((cx, line_h * .2 + (rng.uniform(-2, 2) if jitter else 0)), word, fill=ink, font=fnt)
                cx += fnt.getlength(word + " ") + (rng.uniform(-1, 3) if jitter else 0)
            if jitter:
                lay = lay.rotate(rng.uniform(-.7, .7), resample=Image.BICUBIC)
            img.paste(lay, (0, int(y - line_h * .2)), lay)
        y += line_h
    return y


def render_document(doc, text, level=None, seed=0):
    """Renvoie une image PIL du document (rendu adapté à son style)."""
    style = doc["style"]
    rng = random.Random(hash(doc["id"]) & 0xffff)
    if style == "helios":
        W, H = 900, 1200
        img = _paper(W, H, (240, 238, 230), seed + 1)
        d = ImageDraw.Draw(img)
        _logo(d, 110, 110, 110)
        d.text((190, 62), "HELIOS BIOTECH", fill=(30, 30, 40), font=font("serif_bold", 50))
        d.text((192, 124), "Division des programmes spéciaux", fill=(90, 90, 100), font=font("serif", 24))
        d.line([(60, 180), (W - 60, 180)], fill=(226, 118, 28), width=4)
        d.text((60, 200), doc["title"].upper(), fill=(30, 30, 40), font=font("serif_bold", 30))
        fnt = font("serif", 30)
        y = 270
        for line in _wrap(text, fnt, W - 130):
            d.text((65, y), line, fill=(25, 25, 30), font=fnt)
            y += 42
        d.line([(60, H - 90), (W - 60, H - 90)], fill=(180, 180, 180), width=2)
        d.text((60, H - 76), "Document interne — reproduction et diffusion strictement interdites",
               fill=(120, 120, 120), font=font("serif", 20))
        _stamp(img, "CONFIDENTIEL", (W - 420, H - 330), size=44, angle=14)
        return img
    if style == "paper":
        W, H = 900, 1200
        img = _paper(W, H, (228, 212, 168), seed + 2)
        d = ImageDraw.Draw(img)
        line_h = 62
        for k in range(3, H // line_h):
            d.line([(0, k * line_h + 10), (W, k * line_h + 10)], fill=(150, 170, 200), width=1)
        d.line([(110, 0), (110, H)], fill=(210, 110, 110), width=2)
        fnt = font("hand", 42)
        ink = (32, 42, 96, 255)
        head = f"Jour {doc['day']}" if doc["type"] in ("cahier", "journal") else ""
        y = 3 * line_h - 30
        if head:
            y = _handwrite(img, [head], 130, y, font("hand", 44), ink, line_h, rng)
        y = _handwrite(img, _wrap(text, fnt, W - 180), 130, y, fnt, ink, line_h, rng)
        if doc["type"] != "lettre":
            _handwrite(img, ["— " + doc["author"].split(",")[0]], W - 420, y + 20, font("hand", 34), ink, line_h,
                       rng)
        return img
    if style == "form":
        W, H = 900, 1200
        img = _paper(W, H, (236, 236, 232), seed + 3)
        d = ImageDraw.Draw(img)
        d.rectangle((40, 40, W - 40, 130), outline=(40, 40, 50), width=3)
        d.text((60, 55), "KERGUELEN — SERVICE MÉDICAL", fill=(30, 30, 40), font=font("sans_bold", 26))
        d.text((60, 97), doc["title"], fill=(60, 60, 70), font=font("sans", 22))
        fnt = font("mono", 25)
        y = 160
        width = W - 110
        img_attach = None
        if doc.get("image") == "brainscan":
            img_attach = image_brainscan(430, seed + 4)
        for line in _wrap(text, fnt, width):
            d.text((60, y), line, fill=(20, 20, 26), font=fnt)
            y += 35
        if img_attach is not None:
            iy = min(y + 20, H - 470)
            img.paste(img_attach, (W // 2 - 215, iy))
            d.rectangle((W // 2 - 217, iy - 2, W // 2 + 217, iy + 432), outline=(30, 30, 30), width=2)
            d.text((60, iy + 440), "Pièce jointe : scanner cérébral (J15)", fill=(80, 80, 90), font=font("sans", 20))
        _stamp(img, "QUARANTAINE" if doc["type"] == "rapport" else "MÉDICAL", (W - 300, 44), (150, 30, 30), 24, 6)
        return img
    if style == "terminal":
        W, H = 1000, 1000
        img = Image.new("RGB", (W, H), (6, 18, 10))
        d = ImageDraw.Draw(img)
        g = (95, 255, 130)
        d.rectangle((20, 20, W - 20, H - 20), outline=(40, 120, 60), width=3)
        d.text((50, 45), "KERGUELEN // JOURNAL DE BORD // ACCÈS COMMANDANT", fill=g, font=font("mono", 26))
        d.line([(50, 90), (W - 50, 90)], fill=(40, 140, 70), width=2)
        fnt = font("mono", 29)
        y = 120
        for line in _wrap(text, fnt, W - 110):
            d.text((55, y), line, fill=g, font=fnt)
            y += 41
        d.text((55, y + 10), "> _", fill=g, font=fnt)
        a = np.asarray(img, np.float32)
        a *= (0.78 + 0.22 * (np.arange(H) % 3 == 0))[:, None, None]
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
        glow = img.filter(ImageFilter.GaussianBlur(3))
        return Image.blend(img, glow, .35)
    if style == "audio":
        W, H = 1000, 1000
        img = Image.new("RGB", (W, H), (20, 16, 10))
        d = ImageDraw.Draw(img)
        amber = (255, 186, 80)
        d.text((50, 40), "TRANSCRIPTION AUDIO — ENREGISTREUR PERSONNEL", fill=amber, font=font("mono", 26))
        d.text((50, 80), f"{doc['author'].upper()} — JOUR {doc['day']}", fill=(200, 150, 70), font=font("mono", 22))
        img.paste(image_waveform(W - 100, 170, seed + 5), (50, 125))
        fnt = font("mono", 28)
        y = 330
        for line in _wrap(text, fnt, W - 110):
            d.text((55, y), line, fill=amber, font=fnt)
            y += 40
        return img
    if style == "postit":
        W, H = 800, 800
        img = Image.new("RGB", (W, H), (16, 16, 18))
        note = _paper(640, 640, (246, 230, 104), seed + 6)
        d = ImageDraw.Draw(note)
        fnt = font("marker", 58)
        y = 110
        for line in _wrap(text, fnt, 560):
            x = 40
            for ch in line:
                d.text((x, y + rng.uniform(-5, 5)), ch, fill=(20, 20, 24), font=fnt)
                x += fnt.getlength(ch) + rng.uniform(-1, 3)
            y += 90
        note = note.rotate(rng.uniform(-4, 4), expand=True, resample=Image.BICUBIC, fillcolor=(16, 16, 18))
        img.paste(note, ((W - note.width) // 2, (H - note.height) // 2))
        return img
    if style == "photo":
        if doc.get("image") == "drawing":
            pic = image_drawing(seed=seed + 7)
        elif doc.get("image") == "vents":
            pic = image_vents(level, seed=seed + 8)
        else:
            pic = Image.new("RGB", (800, 600), (40, 40, 40))
        W, H = pic.width + 80, pic.height + 80
        img = Image.new("RGB", (W, H), (14, 14, 16))
        img.paste(pic, (40, 40))
        return _grain(img, 14, seed + 9)
    if style == "video":
        pic = image_keating(seed=seed + 10)
        W, H = 1000, 1250
        img = Image.new("RGB", (W, H), (8, 8, 10))
        img.paste(pic, ((W - pic.width) // 2, 40))
        d = ImageDraw.Draw(img)
        fnt = font("mono", 27)
        y = pic.height + 80
        d.text((60, y - 30), "TRANSCRIPTION — DERNIER ENREGISTREMENT (DR M. KEATING)", fill=(170, 200, 190),
               font=font("mono", 22))
        y += 10
        for line in _wrap(text, fnt, W - 120):
            d.text((60, y), line, fill=(215, 230, 222), font=fnt)
            y += 39
        return _grain(img, 10, seed + 11)
    img = Image.new("RGB", (900, 1200), (230, 230, 230))
    ImageDraw.Draw(img).text((40, 40), text, fill=(0, 0, 0), font=font("sans", 28))
    return img


# ============================================================================
# DOCUMENTS DE LA PARTIE
# ============================================================================
class DocumentLog:
    """Documents présents dans la partie, trouvés et lus."""

    def __init__(self, game):
        self.game = game
        self.docs = {d["id"]: d for d in story.DOCUMENTS}
        self.order = sorted(story.DOCUMENTS, key=lambda d: (d["day"], d["id"]))
        self.present = set(self.docs)      # renseigné par rooms.py
        self.found = []                    # ids dans l'ordre de découverte
        self.read_count = {}
        self.variant_seen = set()          # documents dont la phrase a « changé »
        self.hdd_found = False
        self.pickups = {}                  # id -> objet ramassable (pour le déplacer)
        self._tex_cache = {}

    @property
    def total(self):
        return len(self.docs)

    def text_for(self, doc):
        """Texte à afficher (avec les indications de fusibles et, plus tard, les phrases altérées)."""
        text = doc["text"]
        if "{fuses}" in text:
            b = self.game.builder
            rooms = []
            if b is not None:
                for f in b.fuses:
                    r = self.game.level.room_at(f.pos[0], f.pos[2])
                    if r is not None and r.name not in rooms:
                        rooms.append(r.name.lower())
            where = ("un ici, dans la salle des machines, les autres dans : " + ", ".join(
                n for n in rooms if n != "salle des machines")) if len(rooms) > 1 else "tous ici, dans la salle"
            text = text.replace("{fuses}", where)
        h = self.game.hallu
        if doc["id"] in self.variant_seen or (h is not None and h.variant_active(doc, self.read_count.get(doc["id"], 0))):
            if doc.get("variants"):
                self.variant_seen.add(doc["id"])
                for a, b in doc["variants"]:
                    text = text.replace(a, b)
        return text

    def texture_for(self, doc):
        text = self.text_for(doc)
        key = (doc["id"], text)
        if key not in self._tex_cache:
            img = render_document(doc, text, self.game.level, seed=(self.game.seed or 0) % 1000)
            t = Texture(img)
            t.filtering = 'mipmap'
            self._tex_cache[key] = (t, img.width / img.height)
        return self._tex_cache[key]

    def collect(self, doc_id, open_reader=True):
        """Le joueur ramasse un document : son court, message, ouverture en lecture."""
        g = self.game
        doc = self.docs.get(doc_id)
        if doc is None:
            return
        if doc_id not in self.found:
            self.found.append(doc_id)
            g.stats["docs"] = len(self.found)
            g.hud.message(f"Document ajouté au journal : {doc['title']}  (J / Create)", color.rgb(.9, .8, .55))
        if doc["style"] in ("audio", "terminal", "video"):
            g.audio.play("static_burst", .7)
        else:
            g.audio.play("rustle", .7)
        if open_reader:
            g.reader.open([doc])

    def debug_all(self):
        for d in self.order:
            if d["id"] not in self.found:
                self.found.append(d["id"])
        self.game.stats["docs"] = len(self.found)
        self.game.hud.message("[debug] tous les documents ajoutés au journal", color.yellow)


# ============================================================================
# LECTEUR DE DOCUMENTS (le jeu continue)
# ============================================================================
class DocumentReader:
    def __init__(self, game):
        self.game = game
        self.open_ = False
        self.pages = []
        self.index = 0
        self.on_close = None
        self._timer = 0.0
        ar = window.aspect_ratio
        self.root = Entity(parent=camera.ui, enabled=False, z=-4)
        Entity(parent=self.root, model='quad', color=color.rgba(0, 0, 0, .74), scale=(ar * 1.05, 1.05), z=.1)
        self.page = Entity(parent=self.root, model='quad', scale=(.6, .8), y=.02)
        self.header = Text(parent=self.root, text="", position=(0, .465), origin=(0, 0), scale=.9,
                           color=color.rgb(.85, .85, .8))
        self.hint = Text(parent=self.root, text="", position=(0, -.46), origin=(0, 0), scale=.75,
                         color=color.rgba(1, 1, 1, .55))

    @property
    def is_open(self):
        return self.open_

    def open(self, docs, on_close=None):
        self.pages = list(docs)
        self.index = 0
        self.on_close = on_close
        self.open_ = True
        self.root.enabled = True
        self._timer = .3
        self._show()

    def _show(self):
        g = self.game
        doc = self.pages[self.index]
        tex, ratio = g.docs.texture_for(doc)
        h = .84
        w = min(h * ratio, window.aspect_ratio * .9)
        self.page.texture = tex
        self.page.scale = (w, w / ratio)
        g.docs.read_count[doc["id"]] = g.docs.read_count.get(doc["id"], 0) + 1
        day = f"jour {doc['day']}" if doc["day"] else "avant le départ"
        self.header.text = f"{doc['id'][:3]} — {doc['title']} — {doc['author']} — {day}"
        pad = g.inp.using_pad
        more = self.index < len(self.pages) - 1
        if pad:
            self.hint.text = "Croix : page suivante" if more else "Rond : fermer"
        else:
            self.hint.text = "E : page suivante" if more else "E / Échap : fermer"
        if len(self.pages) > 1:
            self.hint.text += f"    ({self.index + 1}/{len(self.pages)})"

    def close(self):
        if not self.open_:
            return
        self.open_ = False
        self.root.enabled = False
        cb = self.on_close
        self.on_close = None
        if cb:
            cb()

    def update(self, dt, inp):
        if not self.open_:
            return False
        self._timer -= dt
        if self._timer > 0:
            return True
        nxt = inp.pressed("interact") or inp.pressed("confirm") or inp.pressed("next_item")
        back = inp.pressed("back") or inp.pad.pressed("circle")
        if nxt and self.index < len(self.pages) - 1:
            self.index += 1
            self._timer = .2
            self.game.audio.play("rustle", .5, 1.2)
            self._show()
        elif nxt or back:
            self.close()
        return True

    def destroy(self):
        destroy(self.root)


# ============================================================================
# JOURNAL DU JOUEUR (ordre chronologique, emplacements vides)
# ============================================================================
class JournalUI:
    def __init__(self, game):
        self.game = game
        self.open = False
        self.sel = 0
        self.root = Entity(parent=camera.ui, enabled=False, z=-3)
        Entity(parent=self.root, model='quad', color=color.rgba(.02, .02, .03, .9), scale=(1.15, .92))
        Text(parent=self.root, text="JOURNAL", position=(-.54, .42), scale=1.4, color=color.rgb(.85, .8, .65))
        self.count = Text(parent=self.root, text="", position=(.54, .42), origin=(.5, 0), scale=.9,
                          color=color.rgb(.7, .7, .65))
        self.rows = []
        for k in range(18):
            bg = Entity(parent=self.root, model='quad', color=color.rgba(1, 1, 1, .03), scale=(1.08, .038),
                        position=(0, .345 - k * .042))
            t = Text(parent=self.root, text="", position=(-.53, .355 - k * .042), scale=.78)
            self.rows.append((bg, t))
        self.hint = Text(parent=self.root, text="", position=(0, -.43), origin=(0, 0), scale=.72,
                         color=color.rgba(1, 1, 1, .5))

    def entries(self):
        """(document, trouvé ?) dans l'ordre chronologique, + contenu du disque dur si lu."""
        docs = self.game.docs
        out = [(d, d["id"] in docs.found) for d in docs.order]
        if docs.hdd_found:
            out += [(story.HDD_CLASSIFIED, True), (story.HDD_KEATING, True)]
        return out

    def toggle(self):
        self.open = not self.open
        self.root.enabled = self.open
        self.game.audio.play("ui_select", .5)

    def close(self):
        self.open = False
        self.root.enabled = False

    def update(self, dt, inp):
        if not self.open:
            return False
        ents = self.entries()
        n = len(ents)
        if inp.pressed("menu_up") or inp.pressed("prev_item"):
            self.sel = (self.sel - 1) % n
            self.game.audio.play("ui_select", .35)
        if inp.pressed("menu_down") or inp.pressed("next_item"):
            self.sel = (self.sel + 1) % n
            self.game.audio.play("ui_select", .35)
        if inp.pressed("back") or inp.pad.pressed("circle"):
            self.close()
            return True
        doc, ok = ents[self.sel]
        if (inp.pressed("interact") or inp.pressed("confirm")) and ok:
            self.close()
            self.game.reader.open([doc])
            return True
        docs = self.game.docs
        self.count.text = f"{len(docs.found)}/{docs.total} documents"
        first = max(0, min(self.sel - 8, n - len(self.rows)))
        for k, (bg, t) in enumerate(self.rows):
            i = first + k
            if i >= n:
                t.text = ""
                bg.color = color.rgba(1, 1, 1, 0)
                continue
            d, found = ents[i]
            day = f"Jour {d['day']:>2}" if d["day"] else "Avant  "
            if found:
                t.text = f"{day}   {d['id'][:3]}   {d['title']}  —  {d['author']}"
                t.color = color.rgb(1, .9, .6) if i == self.sel else color.rgb(.8, .8, .75)
            else:
                t.text = f"{day}   {d['id'][:3]}   Document manquant"
                t.color = color.rgb(.55, .4, .35) if i == self.sel else color.rgb(.35, .33, .32)
            bg.color = color.rgba(1, .9, .6, .12) if i == self.sel else color.rgba(1, 1, 1, .03)
        pad = self.game.inp.using_pad
        self.hint.text = ("Haut/Bas : choisir   Croix : lire   Rond / Create : fermer" if pad else
                          "Flèches / molette : choisir   E : lire   J / Échap : fermer")
        return True

    def destroy(self):
        destroy(self.root)


# ============================================================================
# ÉCRAN DES COMMANDES (touche I)
# ============================================================================
CONTROL_ROWS = [
    ("À PIED", None, None),
    ("Se déplacer", "forward/left/back/right", "Stick gauche"),
    ("Regarder", "Souris", "Stick droit"),
    ("Courir / s'accroupir", "run/crouch", "L3 / Rond"),
    ("Tirer / viser", "Clic gauche / clic droit", "R2 / L2"),
    ("Couteau / recharger", "knife/reload", "R1 / Carré"),
    ("Tuer une araignée au corps à corps", "melee", "R3"),
    ("Lampe / vision nocturne", "flashlight/nightvision", "Triangle / L1"),
    ("Interagir, lire, forcer (maintenir)", "interact", "Croix"),
    ("Fermer un document", "Échap / E", "Rond"),
    ("Journal des documents", "journal", "Create"),
    ("Inventaire (le jeu continue)", "inventory", "Pavé tactile"),
    ("Soin / objet équipé", "heal/use_item", "Haut / Bas (croix directionnelle)"),
    ("Changer d'objet", "prev_item/next_item", "Gauche / Droite"),
    ("NAVETTE", None, None),
    ("Poussée / strafe", "forward/left/back/right", "Stick gauche"),
    ("Monter / descendre", "ship_up/ship_down", "R2 / L2"),
    ("Roulis / boost", "ship_roll_left/ship_roll_right/ship_boost", "L1 R1 / Croix"),
    ("Assistance / frein / caméra", "ship_assist/ship_brake/ship_camera", "Triangle / Rond / R3"),
    ("DIVERS", None, None),
    ("Pause", "pause", "Options"),
    ("Commandes (cet écran)", "controls", "—"),
    ("Debug : manette / courant / screamer", "debug/debug_power/debug_screamer", "—"),
    ("Debug : tous les documents / révélation", "debug_docs/debug_reveal", "—"),
    ("Debug : son de test", "debug_sound", "—"),
]


def key_label(action_keys):
    """Nom lisible des touches (lettres AZERTY affichées telles qu'imprimées sur le clavier)."""
    raw = C.KEYS_AZERTY if C.KEYBOARD_LAYOUT == "azerty" else C.KEYS_QWERTY
    names = {"space": "Espace", "control": "Ctrl", "shift": "Maj", "escape": "Échap", "tab": "Tab",
             "delete": "Suppr"}
    out = []
    for a in action_keys.split("/"):
        k = raw.get(a)
        if k is None:
            return action_keys
        out.append(names.get(k, k.upper()))
    return " / ".join(out)


class ControlsOverlay:
    def __init__(self, game):
        self.game = game
        self.open = False
        self.root = Entity(parent=camera.ui, enabled=False, z=-27)
        Entity(parent=self.root, model='quad', color=color.rgba(0, 0, 0, 1),
               scale=(window.aspect_ratio * 1.05, 1.05), z=.5)
        Text(parent=self.root, text="COMMANDES", position=(0, .46), origin=(0, 0), scale=1.6,
             color=color.rgb(.85, .9, .95))
        Text(parent=self.root, text="ACTION", position=(-.62, .4), scale=.8, color=color.rgb(.6, .6, .6))
        Text(parent=self.root, text="CLAVIER / SOURIS", position=(-.05, .4), scale=.8, color=color.rgb(.6, .6, .6))
        Text(parent=self.root, text="MANETTE PS5", position=(.37, .4), scale=.8, color=color.rgb(.6, .6, .6))
        y = .36
        for label, kb, pad in CONTROL_ROWS:
            if kb is None:
                Text(parent=self.root, text=label, position=(-.62, y), scale=.8, color=color.rgb(1, .8, .45))
            else:
                Text(parent=self.root, text=label, position=(-.62, y), scale=.72, color=color.rgb(.85, .85, .82))
                lab = kb if kb[0].isupper() else key_label(kb)
                Text(parent=self.root, text=lab, position=(-.05, y), scale=.72, color=color.rgb(.75, .85, .95))
                Text(parent=self.root, text=pad, position=(.37, y), scale=.72, color=color.rgb(.75, .95, .8))
            y -= .032
        lay = "AZERTY" if C.KEYBOARD_LAYOUT == "azerty" else "QWERTY"
        Text(parent=self.root, text=f"Clavier {lay} (config.KEYBOARD_LAYOUT).   I / Échap : fermer",
             position=(0, -.46), origin=(0, 0), scale=.72, color=color.rgba(1, 1, 1, .5))

    def toggle(self):
        self.open = not self.open
        self.root.enabled = self.open
        self.game.audio.play("ui_select", .5)

    def close(self):
        self.open = False
        self.root.enabled = False

    def destroy(self):
        destroy(self.root)
