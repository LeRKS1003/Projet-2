# -*- coding: utf-8 -*-
"""
textures.py — Textures et matériaux générés par code (numpy -> PIL -> Texture).

Aucun fichier image externe : panneaux métalliques, caillebotis, sang,
grain de vision nocturne, étoiles, planètes... et des MATÉRIAUX complets
(albédo + normal map + carte de rugosité) : métal brossé, métal peint usé,
panneaux à jointures et rivets, polymère, acier bruni.

Cache : en mémoire, et sur disque dans generated/textures/ (PNG) pour que
les lancements suivants soient instantanés. Incrémente CACHE_VERSION pour
forcer la régénération après avoir modifié un générateur.

Rappel Panda3D : le shader automatique utilise des cartes de BRILLANCE
(gloss = 1 - rugosité) ; on génère la rugosité puis on la convertit.
"""
import os
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ursina import Texture

import config as C

CACHE_VERSION = 2
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(BASE_DIR, "generated", "textures")

_cache = {}
_last = {"arr": None, "filtering": "bilinear"}


def _to_tex(arr, filtering='bilinear'):
    """arr : tableau HxWx4 (float 0..1 ou uint8) -> Texture Ursina."""
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    if arr.ndim == 2:
        arr = np.dstack([arr, arr, arr, np.full_like(arr, 255)])
    elif arr.shape[2] == 3:
        arr = np.dstack([arr, np.full(arr.shape[:2], 255, np.uint8)])
    _last["arr"] = arr
    _last["filtering"] = filtering
    t = Texture(Image.fromarray(arr, 'RGBA'))
    t.filtering = filtering
    return t


def _disk_path(name, filtering):
    return os.path.join(TEX_DIR, f"{name}__{filtering}__v{CACHE_VERSION}.png")


def _load_disk(name):
    if not os.path.isdir(TEX_DIR):
        return None
    prefix = f"{name}__"
    suffix = f"__v{CACHE_VERSION}.png"
    for f in os.listdir(TEX_DIR):
        if f.startswith(prefix) and f.endswith(suffix):
            filtering = f[len(prefix):-len(suffix)]
            filtering = None if filtering == "None" else filtering
            try:
                img = Image.open(os.path.join(TEX_DIR, f)).convert('RGBA')
            except Exception:
                return None
            t = Texture(img)
            t.filtering = filtering
            return t
    return None


def _save_disk(name):
    arr = _last["arr"]
    if arr is None:
        return
    try:
        os.makedirs(TEX_DIR, exist_ok=True)
        Image.fromarray(arr, 'RGBA').save(_disk_path(name, _last["filtering"]), compress_level=1)
    except Exception as exc:  # pragma: no cover
        print("[textures] cache disque impossible :", exc)


def fractal_noise(h, w, rng, octaves=5, persistence=.55, base=4):
    """Bruit fractal périodique (tuilable) obtenu par interpolation de grilles."""
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh, gw = base * 2 ** o, base * 2 ** o * max(1, w // h)
        g = rng.random((gh, gw)).astype(np.float32)
        # interpolation bilinéaire périodique
        ys = np.linspace(0, gh, h, endpoint=False)
        xs = np.linspace(0, gw, w, endpoint=False)
        y0 = ys.astype(int) % gh
        x0 = xs.astype(int) % gw
        y1 = (y0 + 1) % gh
        x1 = (x0 + 1) % gw
        fy = (ys - ys.astype(int))[:, None]
        fx = (xs - xs.astype(int))[None, :]
        fy = fy * fy * (3 - 2 * fy)
        fx = fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0] * (1 - fx) + g[y0][:, x1] * fx
        b = g[y1][:, x0] * (1 - fx) + g[y1][:, x1] * fx
        out += (a * (1 - fy) + b * fy) * amp
        tot += amp
        amp *= persistence
    return out / tot


def get(name):
    """Renvoie (et génère au besoin, avec cache disque) la texture demandée."""
    if name in _cache:
        return _cache[name]
    t = _load_disk(name)
    if t is None:
        rng = np.random.default_rng(zlib.crc32(name.encode()))
        fn = globals().get('_gen_' + name)
        if fn is None:
            raise KeyError(name)
        _last["arr"] = None
        t = fn(rng)
        _save_disk(name)
    _cache[name] = t
    return t


def clear():
    _cache.clear()


# ----------------------------------------------------------------------------
# TEXTURES DU VAISSEAU
# ----------------------------------------------------------------------------
def _gen_panel(rng):
    """Panneaux muraux : joints, rivets, crasse et rayures."""
    s = 256
    n = fractal_noise(s, s, rng, 6)
    img = 0.72 + 0.28 * n
    # joints de panneaux
    yy, xx = np.mgrid[0:s, 0:s]
    seams = ((xx % 128) < 3) | ((yy % 64) < 3)
    img[seams] *= 0.45
    light = ((xx % 128) == 3) | ((yy % 64) == 3)
    img[light] *= 1.15
    # rivets
    for cy in range(8, s, 64):
        for cx in range(10, s, 32):
            d = (xx - cx) ** 2 + (yy - cy) ** 2
            img[d < 5] *= 0.6
            img[(d >= 5) & (d < 8)] *= 1.12
    # rayures verticales et coulures de crasse
    for _ in range(40):
        x = rng.integers(0, s)
        y0 = rng.integers(0, s)
        ln = rng.integers(10, 120)
        img[y0:y0 + ln, x] *= rng.uniform(.75, .95)
    grime = fractal_noise(s, s, rng, 4, base=2)
    img *= 0.75 + 0.25 * grime
    return _to_tex(img[..., None].repeat(3, 2), 'mipmap')


def _gen_floor(rng):
    """Caillebotis métallique antidérapant."""
    s = 256
    yy, xx = np.mgrid[0:s, 0:s]
    n = fractal_noise(s, s, rng, 5)
    img = 0.55 + 0.25 * n
    # motif en losanges
    d = ((xx + yy) % 16 < 2) | ((xx - yy) % 16 < 2)
    img[d] *= 1.25
    border = ((xx % 128) < 4) | ((yy % 128) < 4)
    img[border] *= 0.5
    grime = fractal_noise(s, s, rng, 4, base=2)
    img *= 0.6 + 0.4 * grime
    return _to_tex(img[..., None].repeat(3, 2), 'mipmap')


def _gen_hull(rng):
    """Plaques de coque extérieure (grandes, usées)."""
    s = 512
    yy, xx = np.mgrid[0:s, 0:s]
    n = fractal_noise(s, s, rng, 6)
    img = 0.6 + 0.3 * n
    plates = rng.random((8, 8)) * 0.25 + 0.85
    img *= np.kron(plates, np.ones((64, 64)))
    seams = ((xx % 64) < 2) | ((yy % 64) < 2)
    img[seams] *= 0.4
    burn = fractal_noise(s, s, rng, 4, base=2)
    img *= 0.65 + 0.35 * burn
    rgb = np.dstack([img * 0.95, img * 0.93, img * 0.9])
    return _to_tex(rgb, 'mipmap')


def _gen_hazard(rng):
    """Bandes jaunes et noires (zones dangereuses, hangar)."""
    s = 128
    yy, xx = np.mgrid[0:s, 0:s]
    band = ((xx + yy) // 16) % 2 == 0
    n = fractal_noise(s, s, rng, 4)
    r = np.where(band, 0.85, 0.08) * (0.7 + 0.3 * n)
    g = np.where(band, 0.65, 0.08) * (0.7 + 0.3 * n)
    b = np.where(band, 0.08, 0.06) * (0.7 + 0.3 * n)
    return _to_tex(np.dstack([r, g, b]), 'mipmap')


def _gen_blood(rng):
    """Éclaboussure de sang (alpha)."""
    s = 128
    yy, xx = np.mgrid[0:s, 0:s] / s - .5
    r = np.sqrt(xx ** 2 + yy ** 2)
    n = fractal_noise(s, s, rng, 5, base=3)
    a = np.clip((0.33 - r + (n - .5) * .35) * 9, 0, 1)
    # gouttes autour
    for _ in range(18):
        cx, cy = rng.uniform(-.45, .45, 2)
        rr = rng.uniform(.01, .04)
        a = np.maximum(a, np.clip((rr - np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)) * 80, 0, 1))
    col = np.dstack([0.28 + 0.1 * n, 0.02 + 0.02 * n, 0.02 + 0.01 * n, a * 0.92])
    return _to_tex(col)


def _gen_smear(rng):
    """Traînée de sang / griffures sur un mur (alpha)."""
    s = 128
    yy, xx = np.mgrid[0:s, 0:s] / s
    a = np.zeros((s, s), np.float32)
    for k in range(4):
        x0 = 0.2 + k * 0.18 + rng.uniform(-.03, .03)
        w = rng.uniform(.02, .05)
        a = np.maximum(a, np.clip((w - np.abs(xx - x0 - (yy - .5) * 0.15)) * 40, 0, 1) * (1 - yy) ** 0.5)
    n = fractal_noise(s, s, rng, 4)
    a *= 0.6 + 0.4 * n
    col = np.dstack([0.25 + 0 * a, 0.02 + 0 * a, 0.02 + 0 * a, a * .85])
    return _to_tex(col)


def _gen_screen(rng):
    """Écran de console : lignes de texte vertes pseudo-aléatoires."""
    w, h = 128, 96
    img = np.zeros((h, w, 3), np.float32)
    img[..., 1] = 0.05
    for y in range(6, h - 6, 6):
        x = 6
        while x < w - 10:
            ln = rng.integers(2, 14)
            if rng.random() < .8:
                img[y:y + 3, x:x + ln, 1] = rng.uniform(.5, 1)
                img[y:y + 3, x:x + ln, 0] = img[y:y + 3, x:x + ln, 1] * 0.3
            x += ln + rng.integers(2, 6)
    img[::2] *= 0.8   # lignes de balayage
    return _to_tex(img)


def _gen_screen_red(rng):
    w, h = 128, 96
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0] = 0.06
    for y in range(8, h - 8, 10):
        ln = rng.integers(20, 100)
        img[y:y + 5, 10:10 + ln, 0] = rng.uniform(.6, 1)
    img[::2] *= 0.75
    return _to_tex(img)


def _gen_glow(rng):
    """Halo radial blanc (balises, flash, reflets)."""
    s = 64
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    a = np.clip(1 - r, 0, 1) ** 2.2
    return _to_tex(np.dstack([np.ones_like(a), np.ones_like(a), np.ones_like(a), a]))


def _gen_vignette(rng):
    """Vignette noire sur les bords de l'écran."""
    s = 256
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 1.6
    a = np.clip(r - .35, 0, 1) ** 1.4
    z = np.zeros_like(a)
    return _to_tex(np.dstack([z, z, z, np.clip(a * 1.4, 0, 1)]))


def _gen_red_vignette(rng):
    """Bords rouges (santé basse / dégâts)."""
    s = 256
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 1.5
    n = fractal_noise(s, s, rng, 4)
    a = np.clip(r - .3 + (n - .5) * .25, 0, 1) ** 1.2
    return _to_tex(np.dstack([0.55 + 0 * a, 0 * a, 0 * a, np.clip(a * 1.5, 0, 1)]))


def _gen_grain(rng):
    """Grain animé (vision nocturne) : 4 images empilées verticalement."""
    s = 256
    frames = []
    for _ in range(4):
        g = rng.random((s, s)).astype(np.float32)
        frames.append(g)
    g = np.vstack(frames)
    return _to_tex(np.dstack([g * .6, g, g * .6, 0.35 + g * 0.3]))


def _gen_locker_slits(rng):
    """Vue depuis l'intérieur d'un casier : fentes horizontales."""
    w, h = 256, 256
    a = np.ones((h, w), np.float32)
    for y in range(100, 170, 16):
        a[y:y + 6, 60:196] = 0.0
    yy, xx = np.mgrid[0:h, 0:w]
    a = np.maximum(a, 0)
    z = np.zeros_like(a)
    return _to_tex(np.dstack([z + .01, z + .01, z + .01, a * .97]))


def _gen_forcefield(rng):
    """Champ de force bleuté de l'ouverture du hangar."""
    s = 128
    n = fractal_noise(s, s, rng, 4, base=4)
    yy = np.mgrid[0:s, 0:s][0] / s
    lines = (np.sin(yy * 60) * .5 + .5) ** 8
    a = 0.12 + 0.25 * n + 0.2 * lines
    return _to_tex(np.dstack([0.3 + 0 * a, 0.6 + 0 * a, 1.0 + 0 * a, np.clip(a, 0, 1)]))


def _gen_arrow(rng):
    """Flèche du HUD (pointe vers le haut)."""
    s = 64
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1)
    tri = (yy > 0.1) & (yy < 0.9) & (np.abs(xx - .5) < (yy - .1) * .55)
    tri = tri[::-1]
    a = tri.astype(np.float32)
    o = np.ones_like(a)
    return _to_tex(np.dstack([o, o, o, a]))


# ----------------------------------------------------------------------------
# ESPACE
# ----------------------------------------------------------------------------
def stars_texture(seed, w=4096, h=2048):
    """Carte équirectangulaire : milliers d'étoiles + nébuleuse discrète."""
    key = ('stars', seed)
    if key in _cache:
        return _cache[key]
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.float32)
    # nébuleuse : bruit basse fréquence coloré, concentré sur une bande
    nh, nw = h // 8, w // 8
    n1 = fractal_noise(nh, nw, rng, 6, base=3)
    n2 = fractal_noise(nh, nw, rng, 6, base=3)
    yy = np.linspace(-1, 1, nh)[:, None]
    band_y = rng.uniform(-.4, .4)
    band = np.exp(-((yy - band_y - 0.25 * np.sin(np.linspace(0, 6.28, nw))[None, :]) ** 2) / 0.08)
    neb = np.clip((n1 - .45) * 2.2, 0, 1) * band
    c1 = np.array(rng.choice([[.35, .12, .45], [.12, .25, .5], [.45, .18, .1]]))
    c2 = np.array([.1, .3, .4])
    nebula = neb[..., None] * c1 * 0.35 + (neb * n2)[..., None] * c2 * 0.2
    nebula = np.kron(nebula, np.ones((8, 8, 1)))[:h, :w]
    img += nebula
    # étoiles : densité plus forte dans la bande galactique
    count = 9000
    ys = rng.integers(0, h, count)
    xs = rng.integers(0, w, count)
    # correction de densité aux pôles (projection équirectangulaire)
    lat = (ys / h - .5) * np.pi
    keep = rng.random(count) < np.cos(lat)
    ys, xs = ys[keep], xs[keep]
    mag = rng.power(6, len(ys)) ** 6
    tint = rng.random(len(ys))
    col = np.where(tint[:, None] < .15, [1, .75, .6], np.where(tint[:, None] > .85, [.7, .8, 1], [1, 1, 1]))
    br = (0.25 + 0.75 * mag)[:, None] * col
    img[ys, xs] = np.maximum(img[ys, xs], br)
    # étoiles brillantes : croix de 3 pixels
    big = mag > 0.55
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        yy2 = np.clip(ys[big] + dy, 0, h - 1)
        xx2 = (xs[big] + dx) % w
        img[yy2, xx2] = np.maximum(img[yy2, xx2], br[big] * 0.45)
    tex = _to_tex(img, 'bilinear')
    _cache[key] = tex
    return tex


def planet_texture(rng, kind):
    """Texture de planète : 'gas' (bandes), 'rock' (cratères/continents), 'ice'."""
    w, h = 512, 256
    n = fractal_noise(h, w, rng, 6, base=3)
    yy = np.linspace(0, 1, h)[:, None]
    if kind == 'gas':
        bands = np.sin(yy * rng.uniform(18, 30) + n * 4) * .5 + .5
        base = np.array(rng.choice([[.8, .6, .4], [.6, .5, .7], [.5, .7, .8]]))
        img = (0.55 + 0.45 * bands)[..., None] * base
        img = img * (0.8 + 0.2 * n[..., None])
    elif kind == 'ice':
        base = np.array([.75, .85, .95])
        img = (0.7 + 0.3 * n)[..., None] * base
        cracks = np.abs(n - .5) < .015
        img[cracks] *= .6
    else:
        base1 = np.array(rng.choice([[.45, .3, .22], [.35, .35, .32], [.5, .2, .15]]))
        base2 = base1 * 0.55
        m = (n > .5)[..., None]
        img = np.where(m, base1, base2) * (0.75 + 0.35 * n[..., None])
    return _to_tex(np.clip(img, 0, 1), 'mipmap')


def ring_texture(rng):
    """Texture des anneaux (dégradé radial, sera plaquée sur un disque)."""
    s = 256
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    bands = rng.random(64)
    idx = np.clip(((r - .55) / .45 * 63).astype(int), 0, 63)
    a = np.where((r > .55) & (r < 1.0), bands[idx] * 0.8, 0)
    a *= np.clip((r - .55) * 20, 0, 1) * np.clip((1 - r) * 20, 0, 1)
    return _to_tex(np.dstack([.85 + 0 * a, .78 + 0 * a, .65 + 0 * a, a]), 'mipmap')


# ============================================================================
# EFFETS : lampe, tir, fumée, impacts
# ============================================================================
def _gen_cookie(rng):
    """
    Masque projeté de la lampe torche (« cookie ») : 1 = neutre (lumière du
    spot telle quelle), <1 = assombri. Anneaux concentriques d'une optique LED,
    légers défauts, bord doux. Le point chaud central vient du spot lui-même.
    """
    s = 256
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    ang = np.arctan2(yy, xx)
    rings = 1 - .12 * (np.sin(r * 38) * .5 + .5) ** 3 * np.clip(r * 1.4, 0, 1)
    halo = np.where(r < .32, 1.0, .82 + .18 * np.clip((.55 - r) / .23, 0, 1))
    halo = np.where(r > .55, .82 - .5 * np.clip((r - .55) / .4, 0, 1), halo)
    dirt = 1 - .07 * fractal_noise(s, s, rng, 4, base=3)
    wobble = 1 - .04 * (np.sin(ang * 7 + r * 5) * .5 + .5) * (r > .25)
    v = np.clip(rings * halo * dirt * wobble, 0, 1)
    v = np.where(r > .98, 0.3, v)
    return _to_tex(np.dstack([v, v, v, np.ones_like(v)]), 'bilinear')


def _flash_star(rng):
    """Flash de bouche en étoile : branches irrégulières + cœur brillant."""
    s = 128
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    ang = np.arctan2(yy, xx)
    n = rng.integers(5, 9)
    rays = np.zeros_like(r)
    for k in range(n):
        a0 = rng.uniform(0, 2 * np.pi)
        ln = rng.uniform(.5, 1.0)
        w = rng.uniform(.06, .14)
        d = np.abs(((ang - a0 + np.pi) % (2 * np.pi)) - np.pi)
        rays = np.maximum(rays, np.clip(1 - d / w, 0, 1) * np.clip(1 - r / ln, 0, 1))
    core = np.clip(1 - r / .35, 0, 1) ** 1.5
    a = np.clip(rays ** 1.3 + core, 0, 1)
    return np.dstack([np.ones_like(a), .85 * np.ones_like(a) + .15 * core, .55 + .45 * core, a])


def _gen_flash0(rng):
    return _to_tex(_flash_star(rng))


def _gen_flash1(rng):
    return _to_tex(_flash_star(rng))


def _gen_flash2(rng):
    return _to_tex(_flash_star(rng))


def _gen_flash3(rng):
    return _to_tex(_flash_star(rng))


def _gen_smoke(rng):
    """Bouffée de fumée douce (alpha)."""
    s = 64
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    n = fractal_noise(s, s, rng, 4, base=3)
    a = np.clip(1 - r, 0, 1) ** 1.5 * (.5 + .5 * n)
    o = np.ones_like(a)
    return _to_tex(np.dstack([o * .8, o * .8, o * .82, a]))


def _gen_bullet_hole(rng):
    """Impact de balle : trou sombre, anneau déchiré, éclats (alpha)."""
    s = 64
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    ang = np.arctan2(yy, xx)
    crack = (np.sin(ang * 9 + rng.uniform(0, 6)) * .5 + .5) ** 6 * np.clip(1 - r, 0, 1)
    a = np.clip((.3 - r) * 12, 0, 1) + np.clip((.55 - r) * 4, 0, .6) + crack * .7
    a = np.clip(a, 0, 1)
    c = np.where(r < .3, .02, .12)
    return _to_tex(np.dstack([c, c, c, a]))


def _gen_splat_green(rng):
    """Giclée de liquide extraterrestre (alpha)."""
    s = 64
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2)
    n = fractal_noise(s, s, rng, 4, base=3)
    a = np.clip((.32 - r + (n - .5) * .3) * 10, 0, 1)
    return _to_tex(np.dstack([.35 + .2 * n, .55 + .2 * n, .08 + 0 * n, a * .95]))


def _gen_dust(rng):
    """Particule de poussière dans le faisceau (petit point flou)."""
    s = 16
    yy, xx = np.mgrid[0:s, 0:s] / (s - 1) - .5
    r = np.sqrt(xx ** 2 + yy ** 2) * 2
    a = np.clip(1 - r, 0, 1) ** 2
    o = np.ones_like(a)
    return _to_tex(np.dstack([o, o, o, a]))


def _gen_beam(rng):
    """Dégradé du cône volumétrique : intense au centre, s'efface sur les bords et au loin."""
    w, h = 64, 128
    u = np.linspace(-1, 1, w)[None, :]
    v = np.linspace(0, 1, h)[:, None]       # v = 0 : loin, 1 : près de la lampe
    a = (1 - np.abs(u)) ** 2 * v ** 1.6
    n = fractal_noise(h, w, rng, 3, base=4)
    a = a * (.75 + .25 * n)
    o = np.ones((h, w))
    return _to_tex(np.dstack([o, o, o, a]))


def text_decal(text, w=256, h=64, color=(230, 230, 220), bg=(0, 0, 0, 0), size=None, mirror=False, rotate=0):
    """Texte rendu dans une texture (numéros de série, immatriculation)."""
    key = ("text", text, w, h, color, bg, mirror, rotate)
    if key in _cache:
        return _cache[key]
    img = Image.new('RGBA', (w, h), bg)
    d = ImageDraw.Draw(img)
    font = _font(size or int(h * .7))
    tw = d.textlength(text, font=font) if hasattr(d, "textlength") else len(text) * h * .5
    d.text(((w - tw) / 2, h * .12), text, fill=color + (255,), font=font)
    if mirror:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if rotate:
        img = img.rotate(rotate)
    t = Texture(img)
    t.filtering = 'mipmap'
    _cache[key] = t
    return t


def _font(size):
    """Police : DejaVu/Vera si disponible (Ursina fournit VeraMono), sinon police bitmap."""
    cands = [os.path.join(os.path.dirname(__import__('ursina').__file__), 'fonts', 'VeraMono.ttf'),
             "DejaVuSans-Bold.ttf"]
    for c in cands:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_text_on(arr, text, x, y, size, color, rotate=0, mirror=False):
    """Écrit du texte dans un tableau numpy HxWx3 (float 0..1), avec rotation/miroir."""
    h, w = arr.shape[:2]
    font = _font(size)
    tmp = Image.new('L', (int(size * len(text) * .75) + 8, int(size * 1.4)), 0)
    d = ImageDraw.Draw(tmp)
    d.text((4, 0), text, fill=255, font=font)
    if mirror:
        tmp = tmp.transpose(Image.FLIP_LEFT_RIGHT)
    if rotate:
        tmp = tmp.rotate(rotate, expand=True)
    m = np.asarray(tmp, np.float32) / 255
    th, tw = m.shape
    x0, y0 = int(x - tw / 2), int(y - th / 2)
    xs0, ys0 = max(0, x0), max(0, y0)
    xs1, ys1 = min(w, x0 + tw), min(h, y0 + th)
    if xs1 <= xs0 or ys1 <= ys0:
        return arr
    mm = m[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0][..., None]
    arr[ys0:ys1, xs0:xs1] = arr[ys0:ys1, xs0:xs1] * (1 - mm) + np.array(color) * mm
    return arr


# ============================================================================
# MATÉRIAUX (albédo + normal map + rugosité)
# ============================================================================
def height_to_normal(hmap, strength=2.0):
    """
    Carte de hauteur -> normal map en espace tangent (R = +u, G = +v, B = normale).
    La ligne 0 de l'image correspond au haut de la texture (v = 1).
    """
    dx = (np.roll(hmap, -1, 1) - np.roll(hmap, 1, 1)) * .5
    dy = (np.roll(hmap, 1, 0) - np.roll(hmap, -1, 0)) * .5
    n = np.dstack([-dx * strength, -dy * strength, np.ones_like(hmap)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * .5 + .5


def _mat_panel(rng):
    """Panneaux muraux : jointures en creux, rivets en relief, crasse."""
    s = 512
    yy, xx = np.mgrid[0:s, 0:s]
    n = fractal_noise(s, s, rng, 6)
    h = np.full((s, s), .5, np.float32)
    seam = ((xx % 256) < 4) | ((yy % 128) < 4)
    h[seam] = 0.0
    bevel = ((xx % 256) < 8) | ((yy % 128) < 8)
    h[bevel & ~seam] = .3
    # plaque intérieure légèrement emboutie
    inner = ((xx % 256) > 40) & ((xx % 256) < 216) & ((yy % 128) > 30) & ((yy % 128) < 98)
    h[inner] -= .08
    for cy in range(16, s, 128):
        for cx in range(20, s, 64):
            d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            h = np.maximum(h, np.clip(1 - d / 6, 0, 1) ** .6 * .95)
    h += (n - .5) * .08
    alb = .72 + .28 * n
    alb[seam] *= .4
    alb[inner] *= .95
    grime = fractal_noise(s, s, rng, 4, base=2)
    alb *= .7 + .3 * grime
    # coulures verticales
    for _ in range(60):
        x = rng.integers(0, s)
        y0 = rng.integers(0, s)
        ln = rng.integers(20, 200)
        alb[y0:y0 + ln, x:x + 2] *= rng.uniform(.7, .9)
    rough = np.clip(.55 + .3 * grime - .15 * (h > .7), .15, 1)
    return alb[..., None].repeat(3, 2), h, rough, (.55, 40, 3.0)


def _mat_floor(rng):
    """Caillebotis antidérapant : losanges en relief."""
    s = 512
    yy, xx = np.mgrid[0:s, 0:s]
    n = fractal_noise(s, s, rng, 5)
    d1 = np.abs(((xx + yy) % 32) - 16) / 16
    d2 = np.abs(((xx - yy) % 32) - 16) / 16
    h = np.clip(1 - np.minimum(d1, d2) * 3, 0, 1) * .7
    border = ((xx % 256) < 6) | ((yy % 256) < 6)
    h[border] = 0
    alb = .55 + .25 * n
    alb[h > .3] *= 1.2
    alb[border] *= .45
    grime = fractal_noise(s, s, rng, 4, base=2)
    alb *= .6 + .4 * grime
    rough = np.clip(.45 + .4 * grime - .25 * h, .1, 1)
    return alb[..., None].repeat(3, 2), h, rough, (.6, 30, 2.5)


def _mat_brushed(rng):
    """Métal brossé : fines stries horizontales, très brillant."""
    s = 256
    streak = rng.random((s, 1)).astype(np.float32).repeat(s, 1)
    streak = (streak + np.roll(streak, 1, 0) + np.roll(streak, -1, 0)) / 3
    fine = rng.random((s, s)).astype(np.float32)
    fine = (fine + np.roll(fine, 1, 1) + np.roll(fine, 2, 1) + np.roll(fine, 3, 1)) / 4
    n = fractal_noise(s, s, rng, 3, base=2)
    alb = .62 + .18 * streak + .06 * fine + .08 * n
    h = streak * .3 + fine * .1
    rough = np.clip(.2 + .15 * n + .1 * fine, .05, 1)
    return alb[..., None].repeat(3, 2), h, rough, (1.0, 70, 1.2)


def _mat_painted(rng):
    """Métal peint usé : peinture claire, rayures et éclats révélant le métal."""
    s = 512
    n = fractal_noise(s, s, rng, 6)
    chips = fractal_noise(s, s, rng, 5, base=3)
    bare = chips > .66
    alb = np.full((s, s), .82, np.float32) * (.92 + .08 * n)
    h = np.full((s, s), .5, np.float32)
    # rayures fines aléatoires
    img = Image.new('L', (s, s), 0)
    d = ImageDraw.Draw(img)
    for _ in range(90):
        x0, y0 = rng.integers(0, s, 2)
        ln = rng.integers(10, 90)
        a = rng.uniform(0, np.pi)
        d.line((x0, y0, x0 + np.cos(a) * ln, y0 + np.sin(a) * ln), fill=int(rng.integers(120, 255)), width=1)
    scr = np.asarray(img, np.float32) / 255
    alb = np.where(bare, .45 + .1 * n, alb)
    alb = alb * (1 - scr * .35)
    h = np.where(bare, .3, h) - scr * .25
    dirt = fractal_noise(s, s, rng, 4, base=2)
    alb *= .8 + .2 * dirt
    rough = np.where(bare, .25, .6) + .2 * dirt + scr * -.2
    return alb[..., None].repeat(3, 2), h, np.clip(rough, .08, 1), (.5, 35, 2.0)


def _mat_hullplates(rng):
    """Grandes plaques de coque avec jointures et rivets (extérieur)."""
    s = 512
    yy, xx = np.mgrid[0:s, 0:s]
    n = fractal_noise(s, s, rng, 6)
    plates = np.kron(rng.random((8, 8)) * .2 + .85, np.ones((64, 64)))
    seam = ((xx % 64) < 2) | ((yy % 64) < 2)
    h = np.full((s, s), .5, np.float32)
    h[seam] = 0
    for cy in range(6, s, 64):
        for cx in range(6, s, 16):
            d = (xx - cx) ** 2 + (yy - cy) ** 2
            h[d < 5] = .9
    alb = (.6 + .3 * n) * plates
    alb[seam] *= .4
    burn = fractal_noise(s, s, rng, 4, base=2)
    alb *= .65 + .35 * burn
    rgb = np.dstack([alb * .95, alb * .93, alb * .9])
    rough = np.clip(.5 + .3 * burn, .1, 1)
    return rgb, h, rough, (.45, 25, 2.0)


def _mat_gunmetal(rng):
    """Acier bruni mat, micro-grain (arme)."""
    s = 256
    n = fractal_noise(s, s, rng, 6, base=4)
    fine = rng.random((s, s)).astype(np.float32)
    alb = .5 + .15 * n + .05 * fine
    h = fine * .15 + n * .1
    rough = np.clip(.5 + .2 * n, .1, 1)
    return alb[..., None].repeat(3, 2), h, rough, (.7, 45, 1.5)


def _mat_polymer(rng):
    """Polymère texturé antidérapant (poignée) : picots réguliers."""
    s = 256
    yy, xx = np.mgrid[0:s, 0:s]
    d = np.sqrt(((xx % 12) - 6) ** 2 + ((yy % 12) - 6) ** 2)
    h = np.clip(1 - d / 4, 0, 1)
    n = fractal_noise(s, s, rng, 4)
    alb = .45 + .1 * n - .08 * h
    rough = np.clip(.8 - .1 * h, .3, 1)
    return alb[..., None].repeat(3, 2), h, rough, (.2, 12, 3.0)


def _mat_suit(rng):
    """Tissu de combinaison spatiale : trame croisée."""
    s = 256
    yy, xx = np.mgrid[0:s, 0:s]
    weave = (np.sin(xx * .8) * np.sin(yy * .8)) * .5 + .5
    n = fractal_noise(s, s, rng, 5)
    alb = .7 + .15 * n - .1 * weave
    h = weave * .6
    rough = np.full((s, s), .9, np.float32)
    return alb[..., None].repeat(3, 2), h, rough, (.1, 8, 2.0)


MATERIALS = {
    "panel": _mat_panel, "floor": _mat_floor, "brushed": _mat_brushed, "painted": _mat_painted,
    "hullplates": _mat_hullplates, "gunmetal": _mat_gunmetal, "polymer": _mat_polymer, "suit": _mat_suit,
}


def material(name, custom=None):
    """
    Renvoie un dict {'albedo', 'normal', 'gloss', 'specular', 'shininess'}.
    custom : fonction générant (albédo, hauteur, rugosité, (spéc, brillance, relief))
    pour un matériau spécifique (ex. livrée de la navette).
    """
    key = ("mat", name)
    if key in _cache:
        return _cache[key]
    textures = {}
    params = None
    for kind in ("albedo", "normal", "gloss"):
        t = _load_disk(f"mat_{name}_{kind}")
        if t is None:
            break
        textures[kind] = t
    meta_path = os.path.join(TEX_DIR, f"mat_{name}__meta__v{CACHE_VERSION}.txt")
    if len(textures) == 3 and os.path.exists(meta_path):
        with open(meta_path) as f:
            params = tuple(float(x) for x in f.read().split())
    else:
        rng = np.random.default_rng(zlib.crc32(name.encode()))
        alb, h, rough, params = (custom or MATERIALS[name])(rng)
        nrm = height_to_normal(h.astype(np.float32), params[2] * 6)
        gloss = 1 - rough
        for kind, arr in (("albedo", alb), ("normal", nrm), ("gloss", np.dstack([gloss, gloss, gloss, gloss]))):
            textures[kind] = _to_tex(arr, 'mipmap')
            _save_disk(f"mat_{name}_{kind}")
        try:
            os.makedirs(TEX_DIR, exist_ok=True)
            with open(meta_path, "w") as f:
                f.write(" ".join(str(p) for p in params))
        except Exception:
            pass
    m = {"albedo": textures["albedo"], "normal": textures["normal"], "gloss": textures["gloss"],
         "specular": params[0], "shininess": params[1]}
    _cache[key] = m
    return m


_stages = {}


def _stage(kind):
    from panda3d.core import TextureStage
    if kind not in _stages:
        ts = TextureStage(kind)
        if kind == "normal":
            ts.setMode(TextureStage.MNormal)
        elif kind == "gloss":
            ts.setMode(TextureStage.MGloss)
        ts.setSort({"normal": 10, "gloss": 20}.get(kind, 0))
        _stages[kind] = ts
    return _stages[kind]


def apply_material(np_, mat, albedo=None, specular=None, shininess=None):
    """
    Applique un matériau à un NodePath : texture d'albédo (étage par défaut),
    normal map, carte de brillance et Material Panda3D (reflets spéculaires).
    Le niveau de qualité (config.QUALITY) peut désactiver normal/brillance.
    """
    from panda3d.core import Material, TextureStage
    m = material(mat) if isinstance(mat, str) else mat
    alb = albedo if albedo is not None else m["albedo"]
    np_.setTexture(TextureStage.getDefault(), alb._texture if hasattr(alb, "_texture") else alb)
    q = C.quality()
    if q["normal_maps"]:
        np_.setTexture(_stage("normal"), m["normal"]._texture)
        np_.setTexture(_stage("gloss"), m["gloss"]._texture)
    mt = Material()
    sp = m["specular"] if specular is None else specular
    mt.setSpecular((sp, sp, sp, 1))
    mt.setShininess(m["shininess"] if shininess is None else shininess)
    np_.setMaterial(mt, 1)
