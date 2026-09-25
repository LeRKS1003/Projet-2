# -*- coding: utf-8 -*-
"""
textures.py — Textures générées par code (numpy -> PIL -> Texture Ursina).

Aucun fichier image externe n'est nécessaire : panneaux métalliques,
caillebotis, sang, grain de vision nocturne, vignettes, étoiles, planètes...
Toutes les textures sont mises en cache en mémoire.
"""
import zlib

import numpy as np
from PIL import Image
from ursina import Texture

_cache = {}


def _to_tex(arr, filtering='bilinear'):
    """arr : tableau HxWx4 (float 0..1 ou uint8) -> Texture Ursina."""
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    if arr.ndim == 2:
        arr = np.dstack([arr, arr, arr, np.full_like(arr, 255)])
    elif arr.shape[2] == 3:
        arr = np.dstack([arr, np.full(arr.shape[:2], 255, np.uint8)])
    t = Texture(Image.fromarray(arr, 'RGBA'))
    t.filtering = filtering
    return t


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
    """Renvoie (et génère au besoin) la texture demandée."""
    if name in _cache:
        return _cache[name]
    rng = np.random.default_rng(zlib.crc32(name.encode()))
    fn = globals().get('_gen_' + name)
    if fn is None:
        raise KeyError(name)
    _cache[name] = fn(rng)
    return _cache[name]


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
