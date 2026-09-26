# -*- coding: utf-8 -*-
"""
audio.py — Génération procédurale de tous les sons (numpy -> .wav) et
lecture avec spatialisation simple (volume selon la distance, balance
gauche/droite selon l'orientation de la caméra).

Les .wav sont créés au premier lancement dans generated/sounds/vN/ puis
réutilisés (N = SOUND_VERSION : l'incrémenter force leur régénération). Les boucles (moteurs, réacteur, alarme, musique) sont
synthétisées avec des fréquences entières sur la durée de la boucle et
du bruit périodique (FFT) : elles bouclent sans claquement.
"""
import math
import os
import wave

import numpy as np

import config as C

SR = C.SAMPLE_RATE
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUND_VERSION = 2
SOUND_DIR = os.path.join(BASE_DIR, C.SOUND_CACHE_DIR, f"v{SOUND_VERSION}")


# ============================================================================
# OUTILS DE SYNTHÈSE
# ============================================================================
def _t(dur):
    return np.arange(int(SR * dur)) / SR


def _noise(n, rng):
    return rng.uniform(-1, 1, n).astype(np.float64)


def _band(sig, lo, hi):
    """Filtre passe-bande idéal par FFT (rapide, et conserve la périodicité)."""
    spec = np.fft.rfft(sig)
    f = np.fft.rfftfreq(len(sig), 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, len(sig))


def _lowpass(sig, hi):
    return _band(sig, 0, hi)


def _norm(sig, peak=0.9):
    m = np.max(np.abs(sig)) or 1.0
    return sig / m * peak


def _fade(sig, fin=0.01, fout=0.05):
    n = len(sig)
    a = min(n, int(fin * SR))
    b = min(n, int(fout * SR))
    if a:
        sig[:a] *= np.linspace(0, 1, a)
    if b:
        sig[-b:] *= np.linspace(1, 0, b)
    return sig


def _reverb(sig, rng, length=1.2, mix=0.35, damp=3000):
    """Réverbération de salle métallique par convolution FFT avec du bruit décroissant."""
    n = int(length * SR)
    ir = _noise(n, rng) * np.exp(-np.arange(n) / SR * 4.5 / length)
    ir = _lowpass(ir, damp)
    ir[0] = 1.0
    size = len(sig) + n
    out = np.fft.irfft(np.fft.rfft(sig, size) * np.fft.rfft(ir, size), size)
    wet = _norm(out) * np.max(np.abs(sig))
    dry = np.concatenate([sig, np.zeros(n)])
    return dry * (1 - mix) + wet * mix


def _periodic_noise_band(n, lo, hi, rng):
    """Bruit filtré parfaitement bouclable (construit dans le domaine fréquentiel)."""
    f = np.fft.rfftfreq(n, 1 / SR)
    spec = (rng.normal(size=len(f)) + 1j * rng.normal(size=len(f)))
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, n)


def _loop_freq(f, dur):
    """Arrondit une fréquence pour qu'elle fasse un nombre entier de cycles sur la boucle."""
    return round(f * dur) / dur


def _write(name, sig):
    sig = np.clip(sig, -1, 1)
    data = (sig * 32767).astype(np.int16)
    path = os.path.join(SOUND_DIR, name + ".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


# ============================================================================
# ARMES ET ARAIGNÉES (v2 : plus secs, plus crus, plus angoissants)
# ============================================================================
def _metal_ring(t, freqs, decay, rng):
    """Résonances métalliques inharmoniques (tôles, couloirs)."""
    s = np.zeros(len(t))
    for k, f in enumerate(freqs):
        s += np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t * decay * (1 + k * .15)) / (1 + k * .4)
    return s


def _clicks(t, times, lo, hi, sharp, rng, ring=None):
    """Série de petits impacts (pattes, mandibules, mécanique)."""
    s = np.zeros(len(t))
    for t0, amp in times:
        tt = np.clip(t - t0, 0, None)
        on = t >= t0
        s += on * _band(_noise(len(t), rng), lo, hi) * np.exp(-tt * sharp) * amp
        if ring:
            s += on * np.sin(2 * np.pi * ring * rng.uniform(.9, 1.15) * tt) * np.exp(-tt * sharp * .6) * amp * .5
    return s


def gen_weapons_spiders(rng):
    """Renvoie {nom: signal} pour les armes et les araignées."""
    out = {}

    # --- pistolet : détonation sèche et violente -------------------------
    t = _t(0.45)
    crack = _band(_noise(len(t), rng), 1800, 10000) * np.exp(-t * 90)
    click = np.exp(-t * 900) * 2.5
    boom = np.sin(2 * np.pi * np.cumsum(120 * np.exp(-t * 9) + 42) / SR) * np.exp(-t * 11) * 1.6
    body = _lowpass(_noise(len(t), rng), 2200) * np.exp(-t * 22)
    early = np.zeros(len(t))
    for d, a in ((.011, .5), (.019, .35), (.031, .25)):          # premières réflexions sur les parois
        k = int(d * SR)
        early[k:] += crack[:len(t) - k] * a
    s = np.tanh((crack * 1.3 + click + boom + body + early) * 1.6)
    out["gunshot"] = _norm(_fade(s, .0002, .05), .99)
    # queue de réverbération métallique (petite pièce / grande salle)
    for name, L, freqs, echo in (("gun_tail_small", 2.2, (180, 263, 397, 588, 881, 1310), ()),
                                  ("gun_tail_large", 4.5, (96, 141, 212, 318, 477, 715, 1073), (.42, .86, 1.31))):
        t = _t(L)
        ir = _lowpass(_noise(len(t), rng), 3800) * np.exp(-t * 3.2 / L * 1.6)
        ring = _metal_ring(t, freqs, 2.4 / L * 2.2, rng) * .35
        s = (ir + ring) * np.clip(t / .03, 0, 1)
        for e in echo:                                              # échos discrets des couloirs
            k = int(e * SR)
            s[k:] += _lowpass(_noise(len(t) - k, rng), 1800) * np.exp(-(t[:len(t) - k]) * 18) * .5 * (1 - e / L)
        out[name] = _norm(_fade(s, .01, .6), .55)
    # acouphène : sifflement aigu qui s'éteint en ~2,5 s
    t = _t(3.0)
    tt = np.clip(t - .12, 0, None)
    s = (np.sin(2 * np.pi * 4150 * t) + .5 * np.sin(2 * np.pi * 4212 * t)) * np.exp(-tt * 1.4) * (t > .12)
    s *= np.clip(tt / .25, 0, 1)
    out["tinnitus"] = _norm(s, .22)
    # mécanique
    t = _t(0.14)
    out["slide_click"] = _norm(_clicks(t, ((0, 1), (.045, .8)), 2500, 9000, 260, rng, 3200), .5)
    t = _t(0.3)
    s = np.exp(-t * 700) * 1.5 + _clicks(t, ((0, 1),), 3000, 9000, 400, rng) + \
        np.sin(2 * np.pi * 1850 * t) * np.exp(-t * 55) * .35                       # ressort qui vibre
    out["dry_fire"] = _norm(s, .6)
    for k in range(3):                                                             # douilles qui tintent
        t = _t(0.55)
        s = np.zeros(len(t))
        for t0, a in ((0, 1), (.13 + k * .02, .45), (.22 + k * .03, .2)):
            tt = np.clip(t - t0, 0, None)
            s += (t >= t0) * _metal_ring(tt, (3900 + k * 400, 5600 + k * 350, 7900), 30, rng) * a
        out[f"casing{k}"] = _norm(s, .5)
    t = _t(0.6)
    s = _lowpass(_noise(len(t), rng), 500) * np.exp(-t * 20) * 1.4 + np.sin(2 * np.pi * 170 * t) * np.exp(-t * 16)
    s += _clicks(t, ((.05, .4), (.11, .25), (.18, .15)), 1500, 5000, 90, rng, 2300)
    out["mag_drop"] = _norm(s, .6)
    # rechargement synchronisé sur l'animation (éjection .25 s, insertion .9 s, culasse 1.15 s)
    t = _t(1.6)
    s = _clicks(t, ((.08, .8),), 2500, 8000, 220, rng, 2600)                       # bouton de chargeur
    tt = np.clip(t - .22, 0, .25)
    s += (t > .22) * (t < .47) * _band(_noise(len(t), rng), 900, 4000) * np.sin(np.pi * tt / .25) * .35
    s += _clicks(t, ((.62, .3),), 800, 3000, 60, rng)                               # prise du chargeur
    s += _clicks(t, ((.93, 1.2),), 400, 3000, 70, rng, 700)                         # insertion : clac sourd
    s += _clicks(t, ((1.15, 1.0), (1.2, .7)), 2000, 9000, 180, rng, 1900)           # culasse relâchée
    out["reload"] = _norm(s, .65)
    # --- couteau : intime, cru, retenu -----------------------------------
    for k in range(2):
        t = _t(0.28)
        f0 = 600 + k * 300
        n = _noise(len(t), rng)
        s = _band(n, f0, f0 * 5) * np.sin(np.pi * t / .28) ** 3
        out[f"knife_swing{k}"] = _norm(s, .32)
    out["knife_swing"] = out["knife_swing0"]
    t = _t(0.45)
    sq = _lowpass(_noise(len(t), rng), 700) * np.exp(-t * 9)
    sq *= 1 + .8 * np.sin(2 * np.pi * (30 + 60 * t) * t)                          # bouillonnement humide
    s = sq + np.sin(2 * np.pi * np.cumsum(220 * np.exp(-t * 6) + 60) / SR) * np.exp(-t * 14) * .5
    out["knife_flesh"] = _norm(_fade(s), .55)
    out["knife_hit"] = out["knife_flesh"]
    t = _t(0.4)
    s = _clicks(t, [(rng.uniform(0, .06), rng.uniform(.5, 1)) for _ in range(7)], 1200, 7000, 160, rng)
    s += _lowpass(_noise(len(t), rng), 1500) * np.exp(-t * 25) * .6
    out["knife_crack"] = _norm(s, .55)
    t = _t(0.5)
    out["knife_break"] = _norm(_metal_ring(t, (1800, 2700, 4100, 5900), 12, rng), .45)

    # --- araignées -------------------------------------------------------
    for k in range(4):                          # grattements irréguliers de pattes sur le métal
        dur = rng.uniform(.45, .8)
        t = _t(dur)
        times, x = [], 0.0
        while x < dur - .05:
            times.append((x, rng.uniform(.3, 1)))
            x += rng.uniform(.012, .07) if rng.random() < .7 else rng.uniform(.08, .16)
        s = _clicks(t, times, 2200, 9000, rng.uniform(140, 260), rng, ring=rng.uniform(3000, 5200))
        s = _fade(s, .002, .04)
        out[f"alien_skitter{k}"] = _norm(s, .5)
        out[f"alien_skitter{k}_m"] = _norm(_lowpass(s, 1100), .3)       # étouffé (derrière une cloison)
    out["alien_skitter"] = out["alien_skitter0"]
    for k in range(2):                          # cliquetis de mandibules
        t = _t(.35)
        s = _clicks(t, [(j * rng.uniform(.035, .06), rng.uniform(.6, 1)) for j in range(5 + k)], 600, 3500, 300, rng,
                    ring=900 + 300 * k)
        out[f"alien_click{k}"] = _norm(s, .42)
    for k in range(2):                          # sifflement de mise en garde
        t = _t(.9 + .3 * k)
        s = _band(_noise(len(t), rng), 2500 + 800 * k, 9000) * np.sin(np.pi * t / t[-1]) ** 2
        s *= 1 + .6 * np.sin(2 * np.pi * (14 + 6 * k) * t)
        out[f"alien_hiss{k}"] = _norm(s, .35)
    t = _t(1.4)                                 # respiration humide et gargouillis
    br = _band(_noise(len(t), rng), 250, 1600) * (np.sin(np.pi * t / 1.4) ** 2)
    bubbles = _clicks(t, [(rng.uniform(.1, 1.2), rng.uniform(.2, .6)) for _ in range(9)], 150, 900, 60, rng, 260)
    out["alien_breath"] = _norm(br + bubbles, .35)
    for k in range(3):                          # cri déchiré qui monte avant le bond
        dur = .55 + .1 * k
        t = _t(dur)
        f = 500 + 3200 * (t / dur) ** 1.6 + 250 * np.sin(2 * np.pi * (23 + 7 * k) * t)
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = np.sin(ph) + .6 * np.sin(ph * 1.51) + .4 * np.sin(ph * 2.03)
        s += _band(_noise(len(t), rng), 1800, 9000) * (.6 + .8 * t / dur)
        s = np.tanh(s * 2.2) * np.clip(t / .04, 0, 1) * np.clip((dur - t) / .08, 0, 1)
        out[f"alien_shriek{k}"] = _norm(_reverb(s, rng, .8, .25), .8)
    out["alien_screech0"] = out["alien_shriek0"]
    out["alien_screech1"] = out["alien_shriek1"]
    for k in range(2):                          # mort : craquement, gargouillis, pattes qui grattent encore
        t = _t(1.8)
        crack = _clicks(t, [(rng.uniform(0, .07), 1.0) for _ in range(6)], 900, 6000, 130, rng)
        f = 700 * np.exp(-t * 2.5) + 90
        garg = np.sin(2 * np.pi * np.cumsum(f) / SR) * (1 + .7 * np.sin(2 * np.pi * 21 * t)) * np.exp(-t * 2.3)
        garg += _lowpass(_noise(len(t), rng), 600) * np.exp(-t * 3) * .6
        legs = _clicks(t, [(rng.uniform(.6, 1.6), rng.uniform(.1, .35)) for _ in range(10)], 2500, 8000, 200, rng)
        out[f"alien_die{k}"] = _norm(_fade(crack * 1.2 + garg * .8 + legs), .75)
    out["alien_die"] = out["alien_die0"]
    # présence invisible : boucle de grattements lointains (bouclable)
    d = 4.0
    t = _t(d)
    s = np.zeros(len(t))
    x = 0.0
    while x < d - .3:
        n = rng.integers(3, 9)
        for j in range(n):
            t0 = x + j * rng.uniform(.02, .06)
            tt = np.clip(t - t0, 0, None)
            s += (t >= t0) * np.exp(-tt * 220) * rng.uniform(.3, 1)
        x += rng.uniform(.35, 1.1)
    s = _lowpass(_band(s * _noise(len(t), rng), 1500, 7000), 3500)
    out["alien_scratch_loop"] = _norm(_fade(s, .05, .05), .4)
    return out


# ============================================================================
# SONS
# ============================================================================
# ============================================================================
# COURANT DU VAISSEAU ET SCREAMER
# ============================================================================
def _after(t, t0):
    """Temps local (0 avant t0) et masque « a commencé » pour composer des événements."""
    return np.clip(t - t0, 0, None), (t >= t0).astype(np.float64)


def _sweep(f_of_t):
    """Phase d'une fréquence qui varie dans le temps (glissando)."""
    return 2 * np.pi * np.cumsum(f_of_t) / SR


def gen_power_screamer(rng):
    """Renvoie {nom: signal} : levier, réacteur, relais, coupures, portes forcées, fusibles, screamer."""
    out = {}

    # --- levier principal : cliquetis du cran puis gros claquement métallique ----
    t = _t(1.6)
    ratchet = _clicks(t, [(k * .032, .7 - k * .09) for k in range(6)], 1500, 7000, 300, rng)
    tt, on = _after(t, .21)
    clunk = on * (_metal_ring(tt, [142, 318, 507, 866, 1370], 7, rng) * 1.2 + np.sin(2 * np.pi * 52 * tt) *
                  np.exp(-tt * 12) * 2.0 + _lowpass(_noise(len(t), rng), 2500) * np.exp(-tt * 30) * 1.6)
    spring = on * np.sin(_sweep(700 - 350 * np.clip(tt, 0, 1))) * np.exp(-tt * 5) * .15
    out["lever_pull"] = _norm(_reverb(_fade(ratchet + clunk + spring, .001, .2), rng, 1.8, .4), .95)

    # --- réacteur : grondement qui monte en puissance (7 s) ----------------------
    d = 7.5
    t = _t(d)
    k = np.clip(t / (d - .8), 0, 1)
    f0 = 16 + 40 * k ** 1.4
    rumble = sum(np.sin(_sweep(f0 * (h + 1)) + rng.uniform(0, 6)) / (1 + h * .8) for h in range(6))
    whine = np.sin(_sweep(140 + 1500 * k ** 2)) * .16 * k + np.sin(_sweep(210 + 2300 * k ** 2.2)) * .07 * k
    roar = _lowpass(_noise(len(t), rng), 500) * (.3 + 1.2 * k)
    groans = np.zeros(len(t))
    for t0 in (1.2, 2.9, 4.4, 5.6):
        g_t, g_on = _after(t, t0 + rng.uniform(-.2, .2))
        groans += g_on * _metal_ring(g_t, [rng.uniform(70, 110), rng.uniform(170, 240), rng.uniform(330, 420)],
                                     2.2, rng) * .45
    env = np.clip(t / .6, 0, 1) * (.25 + .75 * k ** .8)
    s = (rumble * .9 + roar + whine + groans) * env
    out["reactor_spinup"] = _norm(_reverb(_fade(np.tanh(s * 1.4), .05, .6), rng, 2.6, .45, 1800), .95)

    # --- mise sous tension : énorme choc sourd + crépitement ----------------------
    t = _t(2.6)
    s = np.sin(2 * np.pi * 38 * t) * np.exp(-t * 3.5) * 2.2 + np.sin(2 * np.pi * 76 * t) * np.exp(-t * 5)
    s += _band(_noise(len(t), rng), 2000, 9000) * np.exp(-t * 14) * .8
    s += _metal_ring(t, [97, 211, 383, 612], 3, rng) * .6
    out["power_thump"] = _norm(_reverb(_fade(np.tanh(s)), rng, 2.4, .45, 2000), .95)

    # --- relais électriques (claquement sec + bourdonnement du transformateur) ----
    for i in range(3):
        t = _t(1.1)
        c1 = _band(_noise(len(t), rng), 2200, 9500) * np.exp(-t * 420) * 1.6
        tt, on = _after(t, .012 + .006 * i)
        c2 = on * _band(_noise(len(t), rng), 1500, 7000) * np.exp(-tt * 380) * 1.0
        hum_f = 50 * (1 + i * .02)
        hum = (np.sin(2 * np.pi * hum_f * t) + .6 * np.sin(2 * np.pi * hum_f * 2 * t) +
               .3 * np.sign(np.sin(2 * np.pi * hum_f * 3 * t))) * np.exp(-t * 2.8) * np.clip(t / .05, 0, 1) * .35
        buzz = _band(_noise(len(t), rng), 90, 400) * np.exp(-t * 4) * .25
        ring = _metal_ring(t, [1830 + 140 * i, 2960 + 90 * i], 30, rng) * .3
        out[f"relay{i}"] = _norm(_reverb(_fade(c1 + c2 + hum + buzz + ring, .0005, .2), rng, .9, .3), .85)

    # --- coupure de courant : sifflement qui s'effondre + claquement --------------
    t = _t(2.2)
    k = np.clip(t / 1.7, 0, 1)
    whine = np.sin(_sweep(900 * (1 - k) ** 2 + 45)) * (1 - k) * .5
    hum = np.sin(_sweep(100 - 60 * k)) * (1 - k) ** .5 * .6
    tt, on = _after(t, 1.65)
    clack = on * (_band(_noise(len(t), rng), 1500, 7000) * np.exp(-tt * 200) + np.sin(2 * np.pi * 60 * tt) *
                  np.exp(-tt * 15))
    out["power_down"] = _norm(_reverb(_fade(whine + hum + clack, .01, .1), rng, 1.4, .35), .85)

    # --- porte forcée : grincement métallique (stick-slip) -----------------------
    t = _t(.7)
    stick = np.zeros(len(t))
    tp = 0.0
    while tp < .65:
        a = rng.uniform(.4, 1.0)
        tt, on = _after(t, tp)
        stick += on * np.exp(-tt * rng.uniform(25, 60)) * a
        tp += rng.uniform(.018, .05)
    scrape = _band(_noise(len(t), rng), 350, 3200) * stick
    squeal = np.sin(_sweep(rng.uniform(520, 700) + 90 * np.sin(2 * np.pi * 3 * t))) * stick * .5
    groan = _metal_ring(t, [83, 197, 309], 3, rng) * .5
    out["door_force"] = _norm(_reverb(_fade(scrape + squeal + groan, .01, .1), rng, 1.2, .35), .9)
    t = _t(2.0)
    s = _metal_ring(t, [61, 149, 287, 452, 761, 1203], 2.2, rng) * 1.3
    s += _lowpass(_noise(len(t), rng), 2200) * np.exp(-t * 16) * 2.2
    tt, on = _after(t, .05)
    s += on * _band(_noise(len(t), rng), 600, 4000) * np.exp(-tt * 6) * np.clip(1 - tt / .6, 0, 1) * .8
    out["door_force_open"] = _norm(_reverb(_fade(np.tanh(s * 1.3)), rng, 2.2, .5), .95)

    # --- fusible inséré : glissement + déclic -------------------------------------
    t = _t(.45)
    slide = _band(_noise(len(t), rng), 2000, 6000) * np.clip(1 - t / .12, 0, 1) * .3
    tt, on = _after(t, .13)
    snap = on * (_band(_noise(len(t), rng), 2500, 9000) * np.exp(-tt * 500) * 1.5 +
                 np.sin(2 * np.pi * 2300 * tt) * np.exp(-tt * 60) * .4)
    out["fuse_insert"] = _norm(_reverb(_fade(slide + snap, .002, .05), rng, .4, .2), .75)

    # --- SCREAMER : cri strident (fréquences aiguës dissonantes + bruit + distorsion) --
    d = 1.8
    t = _t(d)
    env = np.exp(-t * 1.6) * np.clip(1 - (t - 1.3) / .5, 0, 1)      # attaque instantanée
    s = np.zeros(len(t))
    for f in (1840, 1955, 2230, 2610, 3120, 3305, 4410):
        bend = 1 + .06 * np.sin(2 * np.pi * rng.uniform(5, 9) * t) + .12 * t
        s += np.sin(_sweep(f * bend)) * rng.uniform(.5, 1)
    glottal = np.sign(np.sin(_sweep(410 * (1 + .1 * np.sin(2 * np.pi * 11 * t))))) * .8        # voix déchirée
    hiss = _band(_noise(len(t), rng), 2000, 10000) * 2.2
    s = np.tanh((s * .5 + glottal + hiss) * 2.8) * env
    out["screamer"] = _norm(_fade(s, .0005, .15), .99)

    # --- stinger « orchestral » : clusters de cordes dissonants puis chute grave ---
    d = 4.2
    t = _t(d)
    strings = np.zeros(len(t))
    for f in (587.3, 622.3, 659.3, 698.5, 740.0, 784.0, 155.6, 164.8, 174.6, 185.0):
        vib = 1 + .006 * np.sin(2 * np.pi * rng.uniform(5, 6.5) * t + rng.uniform(0, 6))
        ph = _sweep(f * vib)
        strings += sum(np.sin(ph * h) / h for h in range(1, 7)) * rng.uniform(.6, 1)   # « scie » : cordes
    strings += _band(_noise(len(t), rng), 3000, 9000) * .6                              # archet frotté
    senv = np.clip(t / .004, 0, 1) * (np.exp(-t * 2.2) * .8 + .2 * np.exp(-t * .8))
    tt, on = _after(t, .75)
    fall = on * np.sin(_sweep(np.where(t > .75, 110 * np.exp(-(t - .75) * 1.1) + 24, 110))) * np.exp(-tt * .9) * 2.2
    boom = on * _lowpass(_noise(len(t), rng), 160) * np.exp(-tt * 1.5) * 1.5
    s = np.tanh((strings * senv * .35 + fall + boom) * 1.2)
    out["screamer_stinger"] = _norm(_reverb(_fade(s, .001, .8), rng, 2.8, .45, 3500), .97)

    # --- musique angoissante (25 s) : drone grave, cordes grinçantes, battements -
    d = C.SCREAMER_MUSIC_TIME
    t = _t(d)
    fade_all = np.clip(1 - t / d, 0, 1) ** 1.6
    drone = (np.sin(2 * np.pi * 41 * t) + np.sin(2 * np.pi * 43.7 * t) * .8 + np.sin(2 * np.pi * 61.5 * t) * .4)
    drone *= .6 + .4 * np.sin(2 * np.pi * .07 * t)
    creak = np.zeros(len(t))
    for _ in range(9):
        t0 = rng.uniform(0, d - 4)
        ln = rng.uniform(2.0, 4.5)
        f0 = rng.uniform(900, 2400)
        tt, on = _after(t, t0)
        e = on * np.clip(tt / .4, 0, 1) * np.clip(1 - (tt - ln + .8) / .8, 0, 1) * (tt < ln)
        creak += np.sin(_sweep(f0 * (1 + .05 * np.sin(2 * np.pi * rng.uniform(.3, 1.2) * t)) +
                               rng.uniform(-60, 60) * t / d)) * e * .35
        creak += _band(_noise(len(t), rng), f0 * .8, f0 * 1.6) * e * .5                 # sul ponticello
    beats = np.zeros(len(t))
    tb = .6
    while tb < d - 1:
        tt, on = _after(t, tb)
        beats += on * np.sin(2 * np.pi * 52 * tt) * np.exp(-tt * 9) * rng.uniform(.6, 1.1)
        tb += rng.uniform(.45, 2.4) * (1 + tb / d)          # battements irréguliers qui s'espacent
    air = _band(_noise(len(t), rng), 150, 900) * .25
    s = (drone * .5 + creak + beats * 1.2 + air) * fade_all
    out["screamer_music"] = _norm(_reverb(_fade(s, .3, 3.0), rng, 3.0, .4, 2500), .75)

    # --- fuite dans le conduit : griffes sur le métal qui s'éloignent -------------
    d = 2.6
    t = _t(d)
    far = np.clip(1 - t / d, 0, 1)
    claws = _clicks(t, [(x, rng.uniform(.5, 1.0) * (1 - x / d)) for x in np.cumsum(rng.uniform(.03, .09, 45))
                        if x < d - .1], 1800, 8000, 160, rng, ring=2600)
    scrape = _band(_noise(len(t), rng), 1400, 6000) * (np.sin(2 * np.pi * 7 * t) > .2) * far ** 2 * .6
    boom = _metal_ring(t, [130, 290, 470], 4, rng) * .5
    s = (claws + scrape + boom) * (.3 + .7 * far)
    out["screamer_flee"] = _norm(_reverb(_fade(_lowpass(s, 9000), .002, .3), rng, 1.6, .45, 2500), .9)
    return out


# ============================================================================
# HISTOIRE : LE « CHANT » DE SINUS, CHUCHOTEMENTS, VOIX, GRÉSILLEMENTS
# ============================================================================
def _formant_voice(t, f0, vowels, rng, breath=.3):
    """Voix synthétique : train d'impulsions glottiques filtré par des formants (voyelles)."""
    ph = _sweep(f0)
    glott = (np.mod(ph / (2 * np.pi), 1.0) < .08).astype(np.float64)        # impulsions
    glott = glott - glott.mean()
    out = np.zeros(len(t))
    for f1, f2, f3, w in vowels:
        v = _band(glott, f1 * .8, f1 * 1.2) + .6 * _band(glott, f2 * .85, f2 * 1.15) + .3 * _band(glott, f3 * .9,
                                                                                                   f3 * 1.1)
        out += v * w
    out += _band(_noise(len(t), rng), 800, 5000) * breath
    return out


def gen_story(rng):
    """Renvoie {nom: signal} pour l'histoire (titre, hallucinations, révélation)."""
    out = {}
    # --- bourdonnement grave pulsé à 7 Hz (boucle parfaite de 4 s) ------------
    d = 4.0
    t = _t(d)
    puls = .55 + .45 * np.sin(2 * np.pi * _loop_freq(7, d) * t) ** 2
    s = (np.sin(2 * np.pi * _loop_freq(49, d) * t) + .55 * np.sin(2 * np.pi * _loop_freq(98, d) * t) +
         .25 * np.sin(2 * np.pi * _loop_freq(147, d) * t) + .12 * np.sin(2 * np.pi * _loop_freq(203, d) * t))
    s = s * puls + _periodic_noise_band(len(t), 30, 120, rng) / 25 * puls
    out["sinus_hum"] = _norm(s, .7)
    # --- montée du bourdonnement (fin du jeu) ---------------------------------
    d = 3.5
    t = _t(d)
    k = np.clip(t / 3.0, 0, 1)
    puls = .5 + .5 * np.sin(2 * np.pi * (7 + 5 * k) * t) ** 2
    s = sum(np.sin(_sweep(np.full(len(t), f) * (1 + .15 * k))) / (h + 1) for h, f in enumerate((49, 98, 147, 196, 294)))
    s = np.tanh(s * puls * (.3 + 2.5 * k ** 2))
    s += _band(_noise(len(t), rng), 2000, 8000) * k ** 3 * .6
    out["sinus_swell"] = _norm(_fade(s, .3, .02), .95)
    # --- chuchotements (syllabes de souffle filtré, sans source) --------------
    for i in range(3):
        d = 1.6 + i * .3
        t = _t(d)
        env = np.zeros(len(t))
        tp = .1
        while tp < d - .25:
            ln = rng.uniform(.08, .22)
            env += np.exp(-((t - tp - ln / 2) / (ln / 2.5)) ** 2) * rng.uniform(.5, 1)
            tp += ln + rng.uniform(.03, .12)
        s = 0
        for lo, hi, a in ((600, 1400, 1.0), (1800, 3200, .7), (3500, 7000, .5)):
            s = s + _band(_noise(len(t), rng), lo * rng.uniform(.9, 1.1), hi) * a
        out[f"whisper{i}"] = _norm(_reverb(_fade(s * env, .02, .1), rng, 1.2, .35), .6)
    # --- voix qui appelle depuis un conduit (« hé... ») -----------------------
    d = 2.6
    t = _t(d)
    f0 = np.where(t < 1.0, 190 - 25 * t, 175 - 30 * (t - 1.2))
    vowels = [(530, 1840, 2480, 1.0), (730, 1090, 2440, .6)]
    env = (np.exp(-((t - .45) / .28) ** 2) + .8 * np.exp(-((t - 1.55) / .45) ** 2))
    s = _formant_voice(t, f0, vowels, rng, .35) * env
    s = _band(s, 250, 3200)                                     # passé par le métal du conduit
    out["voice_call"] = _norm(_reverb(_fade(s, .05, .3), rng, 2.2, .55, 2200), .7)
    # --- grésillement d'enregistrement / de terminal ---------------------------
    t = _t(.7)
    crackle = (rng.random(len(t)) > .985) * rng.uniform(-1, 1, len(t)) * 3
    hiss = _band(_noise(len(t), rng), 1500, 9000) * .5
    beep = np.sin(2 * np.pi * 1320 * t) * (t < .06) * .6
    out["static_burst"] = _norm(_fade((crackle + hiss) * np.exp(-t * 3) + beep, .002, .08), .7)
    # --- glitch numérique (déchirure, bits qui sautent) ------------------------
    t = _t(1.2)
    s = np.zeros(len(t))
    tp = 0.0
    while tp < 1.1:
        ln = rng.uniform(.02, .09)
        m = (t >= tp) & (t < tp + ln)
        f = rng.uniform(80, 2400)
        s += m * np.sign(np.sin(2 * np.pi * f * t)) * rng.uniform(.3, 1)
        tp += ln + rng.uniform(0, .05)
    s += _band(_noise(len(t), rng), 300, 9000) * .4 * (np.sin(2 * np.pi * 7 * t) > 0)
    s += np.sin(2 * np.pi * 49 * t) * .8
    out["glitch_burst"] = _norm(_fade(np.tanh(s * 1.5), .001, .1), .85)
    return out


def gen_all(force=False):
    """Génère tous les sons manquants. Renvoie la liste des noms."""
    os.makedirs(SOUND_DIR, exist_ok=True)
    rng = np.random.default_rng(1979)
    sounds = {}

    # --- boucles de moteur de la navette ---------------------------------
    def ship_engine():
        d = 2.0
        t = _t(d)
        s = sum(math.pow(.6, k) * np.sin(2 * np.pi * _loop_freq(55 * (k + 1), d) * t) for k in range(5))
        s += 0.8 * _periodic_noise_band(len(t), 60, 400, rng) / 40
        s *= 1 + 0.15 * np.sin(2 * np.pi * _loop_freq(6, d) * t)
        return _norm(s, .6)

    def ship_boost():
        d = 2.0
        t = _t(d)
        s = _periodic_noise_band(len(t), 300, 2500, rng)
        s = _norm(s) * (1 + 0.2 * np.sin(2 * np.pi * _loop_freq(11, d) * t))
        s += 0.3 * np.sin(2 * np.pi * _loop_freq(110, d) * t)
        return _norm(s, .55)

    def ship_hit():
        t = _t(1.4)
        s = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (3 + k)) for k, f in enumerate([97, 233, 411, 587, 1033]))
        s += _lowpass(_noise(len(t), rng), 2500) * np.exp(-t * 10) * 3
        return _norm(_reverb(_fade(s), rng, 1.0, .3), .9)

    def landing():
        t = _t(2.4)
        thud = np.sin(2 * np.pi * 45 * t) * np.exp(-t * 5)
        hiss = _band(_noise(len(t), rng), 2000, 8000) * np.clip(t - .4, 0, 1) * np.exp(-(t - .4).clip(0) * 1.5)
        clank = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 6) for f in (180, 460, 950))
        return _norm(_fade(thud * 2 + hiss * .5 + clank * .5), .85)

    # --- ambiance intérieure --------------------------------------------
    def reactor_hum():
        d = 4.0
        t = _t(d)
        s = sum(np.sin(2 * np.pi * _loop_freq(f, d) * t) * a
                for f, a in ((50, 1), (100, .6), (150, .3), (200.25, .25), (49.75, .5)))
        s += _periodic_noise_band(len(t), 40, 300, rng) / 60
        return _norm(s, .6)

    def ambience():
        d = 8.0
        t = _t(d)
        s = _periodic_noise_band(len(t), 20, 180, rng)
        s = _norm(s) * .6
        for f in (36, 36.5, 54.25, 72.125):
            s += 0.18 * np.sin(2 * np.pi * _loop_freq(f, d) * t)
        s *= 1 + 0.25 * np.sin(2 * np.pi * _loop_freq(0.25, d) * t)
        return _norm(s, .5)

    def creak(i):
        dur = 1.6 + i * .4
        t = _t(dur)
        f0 = 70 + 40 * i
        fm = f0 * (1 + 0.4 * np.sin(2 * np.pi * (0.7 + .3 * i) * t) + 0.2 * t)
        phase = 2 * np.pi * np.cumsum(fm) / SR
        s = np.sign(np.sin(phase)) * 0.4 + np.sin(phase * 2.01) * 0.4
        s = _band(s, 80, 1800)
        env = np.sin(np.pi * t / dur) ** 2
        s *= env * (1 + 0.5 * _lowpass(_noise(len(t), rng), 30) * 8)
        return _norm(_reverb(_fade(s), rng, 1.5, .45), .7)

    def metal_bang():
        t = _t(1.8)
        s = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (2 + k * .7)) / (1 + k * .3)
                for k, f in enumerate([63, 157, 298, 441, 733, 1187]))
        s += _lowpass(_noise(len(t), rng), 1800) * np.exp(-t * 18) * 2
        return _norm(_reverb(_fade(s), rng, 2.0, .5), .8)

    def vent_bang():
        t = _t(0.9)
        s = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 8) for f in (210, 540, 1320, 2210))
        s += _band(_noise(len(t), rng), 800, 5000) * np.exp(-t * 25)
        return _norm(_reverb(_fade(s), rng, .8, .3), .7)

    # --- joueur -----------------------------------------------------------
    def footstep(i):
        t = _t(0.22)
        s = _lowpass(_noise(len(t), rng), 900 + 150 * i) * np.exp(-t * 35)
        s += 0.35 * np.sin(2 * np.pi * (380 + 90 * i) * t) * np.exp(-t * 40)
        s += 0.2 * np.sin(2 * np.pi * (1250 + 160 * i) * t) * np.exp(-t * 55)
        return _norm(_fade(s, .001, .02), .6)

    def vent_crawl():
        t = _t(0.35)
        s = _band(_noise(len(t), rng), 300, 3000) * np.exp(-t * 12)
        s += 0.4 * np.sin(2 * np.pi * 640 * t) * np.exp(-t * 20)
        return _norm(_fade(s), .5)

    def hurt():
        t = _t(0.45)
        f = 190 - 70 * t
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)
        s += _band(_noise(len(t), rng), 200, 1500) * np.exp(-t * 7) * .6
        return _norm(_fade(s), .8)

    def heartbeat():
        t = _t(0.9)
        def thump(t0, a):
            tt = np.clip(t - t0, 0, None)
            return a * np.sin(2 * np.pi * 52 * tt) * np.exp(-tt * 16) * (t >= t0)
        s = thump(0.0, 1.0) + thump(0.22, 0.7)
        return _norm(_lowpass(s, 200), .9)

    def breath():
        t = _t(1.6)
        s = _band(_noise(len(t), rng), 400, 2200) * (np.sin(np.pi * t / 1.6) ** 2)
        return _norm(s, .35)

    # --- armes ------------------------------------------------------------
    def gunshot():
        t = _t(0.6)
        crack = _band(_noise(len(t), rng), 900, 9000) * np.exp(-t * 45)
        boom = np.sin(2 * np.pi * (70 - 30 * t) * t) * np.exp(-t * 9)
        body = _lowpass(_noise(len(t), rng), 1500) * np.exp(-t * 14)
        s = crack * 1.4 + boom * 1.2 + body
        return _norm(_reverb(_fade(s, .0005, .05), rng, 2.2, .45), .98)

    def dry_fire():
        t = _t(0.12)
        s = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 90) + _band(_noise(len(t), rng), 2000, 7000) * np.exp(-t * 120)
        return _norm(s, .5)

    def reload():
        t = _t(1.3)
        s = np.zeros(len(t))
        for t0, f in ((0.1, 1600), (0.45, 900), (0.95, 2100), (1.05, 1200)):
            tt = np.clip(t - t0, 0, None)
            s += (t >= t0) * (np.sin(2 * np.pi * f * tt) * np.exp(-tt * 60) +
                              _band(_noise(len(t), rng), 1500, 6000) * np.exp(-tt * 90) * .6)
        return _norm(s, .55)

    def knife_swing():
        t = _t(0.3)
        n = _noise(len(t), rng)
        s = _band(n, 700, 4200) * np.sin(np.pi * t / .3) ** 2
        return _norm(s, .45)

    def knife_hit():
        t = _t(0.35)
        s = _lowpass(_noise(len(t), rng), 900) * np.exp(-t * 14)
        s += np.sin(2 * np.pi * (140 - 80 * t) * t) * np.exp(-t * 12)
        return _norm(_fade(s), .7)

    def knife_break():
        t = _t(0.5)
        s = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 14) for f in (1800, 2700, 4100))
        return _norm(s, .5)

    # --- créatures --------------------------------------------------------
    def alien_screech(i):
        dur = 0.7 + .15 * i
        t = _t(dur)
        f = 1400 + 700 * i + 500 * np.sin(2 * np.pi * (9 + 4 * i) * t) + 800 * t
        s = np.sin(2 * np.pi * np.cumsum(f) / SR)
        s *= 0.6 + 0.4 * np.sin(2 * np.pi * 37 * t)
        s += _band(_noise(len(t), rng), 2000, 7000) * .4
        s *= np.sin(np.pi * t / dur) ** .5
        return _norm(_reverb(_fade(s), rng, .9, .3), .6)

    def alien_die():
        t = _t(0.9)
        f = 1800 * np.exp(-t * 2.2) + 150
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3)
        s += _lowpass(_noise(len(t), rng), 800) * np.exp(-t * 6) * .8
        return _norm(_fade(s), .7)

    def alien_skitter():
        t = _t(0.5)
        s = np.zeros(len(t))
        for k in range(9):
            t0 = k * .05 + rng.uniform(0, .02)
            tt = np.clip(t - t0, 0, None)
            s += (t >= t0) * _band(_noise(len(t), rng), 2500, 8000) * np.exp(-tt * 150)
        return _norm(s, .45)

    def creature_roar():
        t = _t(2.8)
        f = 85 + 25 * np.sin(2 * np.pi * 0.8 * t) + 8 * np.sin(2 * np.pi * 7 * t)
        ph = 2 * np.pi * np.cumsum(f) / SR
        saw = sum(np.sin(ph * k) / k for k in range(1, 18))
        s = _band(saw, 60, 3000)
        s += _band(_noise(len(t), rng), 300, 2500) * .9
        # formants grossiers
        s = s + _band(s, 500, 900) * 1.5 + _band(s, 1500, 2600) * 1.0
        env = np.clip(t / .25, 0, 1) * np.clip((2.8 - t) / 1.0, 0, 1)
        return _norm(_reverb(_fade(s * env), rng, 2.4, .5), .95)

    def creature_growl():
        d = 3.0
        t = _t(d)
        f = _loop_freq(62, d)
        ph = 2 * np.pi * f * t + 3 * np.sin(2 * np.pi * _loop_freq(2, d) * t)
        s = sum(np.sin(ph * k) / k for k in range(1, 10))
        s = _norm(s) + 0.6 * _norm(_periodic_noise_band(len(t), 150, 900, rng))
        s *= 0.6 + 0.4 * np.sin(2 * np.pi * _loop_freq(1 / 3 * 2, d) * t) ** 2
        return _norm(s, .6)

    def creature_step():
        t = _t(0.5)
        s = np.sin(2 * np.pi * 38 * t) * np.exp(-t * 9) + _lowpass(_noise(len(t), rng), 500) * np.exp(-t * 20)
        s += 0.3 * np.sin(2 * np.pi * 330 * t) * np.exp(-t * 30)
        return _norm(_reverb(_fade(s), rng, 1.2, .35), .85)

    def creature_hiss():
        t = _t(1.2)
        s = _band(_noise(len(t), rng), 1500, 7000) * np.sin(np.pi * t / 1.2)
        s *= 1 + 0.5 * np.sin(2 * np.pi * 23 * t)
        return _norm(_reverb(s, rng, 1.0, .35), .6)

    def death_sting():
        t = _t(2.5)
        s = np.zeros(len(t))
        for f in (1310, 1390, 1466, 2012, 2130, 620, 655):
            s += np.sin(2 * np.pi * f * t + rng.uniform(0, 6))
        s += _band(_noise(len(t), rng), 1000, 9000) * 1.5
        s *= np.exp(-t * 0.9)
        return _norm(_reverb(s, rng, 2.0, .4), .98)

    # --- ambiance d'alerte -----------------------------------------------
    def alarm():
        d = 1.6
        t = _t(d)
        f = np.where((t % 0.8) < 0.4, 880, 660)
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = np.sign(np.sin(ph)) * .5 + np.sin(ph) * .5
        s = _lowpass(s, 3000)
        return _norm(_fade(s, .005, .005), .45)

    def horror_music():
        d = 8.0
        t = _t(d)
        s = np.zeros(len(t))
        # grappes dissonantes aiguës (cordes stridentes)
        for f in (1480, 1568, 1661, 2217, 2349, 740, 784, 830):
            ff = _loop_freq(f, d)
            vib = 1 + 0.004 * np.sin(2 * np.pi * _loop_freq(5.5, d) * t + rng.uniform(0, 6))
            s += np.sin(2 * np.pi * ff * t * vib) * rng.uniform(.4, 1)
        s *= 0.55 + 0.45 * np.sin(2 * np.pi * _loop_freq(8, d) * t)  # trémolo
        # pulsation grave
        s += 1.5 * np.sin(2 * np.pi * _loop_freq(41, d) * t) * (np.sin(2 * np.pi * _loop_freq(1, d) * t) > .6)
        s += 0.8 * _periodic_noise_band(len(t), 3000, 8000, rng) / 30
        return _norm(s, .6)

    def tension_drone():
        d = 8.0
        t = _t(d)
        s = np.zeros(len(t))
        for f in (110, 116.5, 164.8, 233):
            s += np.sin(2 * np.pi * _loop_freq(f, d) * t) * (0.5 + 0.5 * np.sin(2 * np.pi * _loop_freq(.125, d) * t + f))
        s += _periodic_noise_band(len(t), 60, 600, rng) / 30
        return _norm(s, .45)

    # --- interactions -----------------------------------------------------
    def door_open():
        t = _t(1.0)
        hiss = _band(_noise(len(t), rng), 1500, 7000) * np.exp(-t * 4) * .7
        servo = np.sin(2 * np.pi * (220 + 180 * t) * t) * (t < .6) * .4
        clunk = np.sin(2 * np.pi * 90 * t) * np.exp(-np.clip(t - .6, 0, None) * 25) * (t > .6)
        return _norm(_fade(hiss + servo + clunk), .6)

    def locker_open():
        t = _t(0.8)
        f = 300 + 250 * np.sin(np.pi * t / .8)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * .3 * np.sin(np.pi * t / .8)
        s += sum(np.sin(2 * np.pi * fr * t) * np.exp(-t * 10) for fr in (410, 870)) * .5
        return _norm(_reverb(_fade(s), rng, .7, .3), .55)

    def pickup():
        t = _t(0.25)
        s = np.sin(2 * np.pi * np.where(t < .1, 880, 1320) * t) * np.exp(-t * 10)
        return _norm(_fade(s), .4)

    def rustle():
        t = _t(0.7)
        s = np.zeros(len(t))
        for k in range(14):
            t0 = rng.uniform(0, .6)
            tt = np.clip(t - t0, 0, None)
            s += (t >= t0) * _band(_noise(len(t), rng), 1500, 8000) * np.exp(-tt * 40) * rng.uniform(.3, 1)
        return _norm(s, .45)

    def hdd_pickup():
        t = _t(0.9)
        s = np.zeros(len(t))
        for k, f in enumerate((660, 990, 1320, 1760)):
            t0 = k * .15
            tt = np.clip(t - t0, 0, None)
            s += (t >= t0) * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 8)
        return _norm(s, .5)

    def beep():
        t = _t(0.15)
        return _norm(np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 15), .35)

    def flashlight_click():
        t = _t(0.06)
        return _norm(_band(_noise(len(t), rng), 2000, 8000) * np.exp(-t * 150), .4)

    def nv_on():
        t = _t(0.6)
        f = 400 + 3000 * t
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3) * .5
        return _norm(s, .35)

    def spark():
        t = _t(0.4)
        s = _band(_noise(len(t), rng), 3000, 9000) * np.exp(-t * 12) * (rng.random(len(t)) > .6)
        return _norm(s, .45)

    def ui_select():
        t = _t(0.08)
        return _norm(np.sin(2 * np.pi * 700 * t) * np.exp(-t * 40), .3)

    def victory():
        d = 12.0
        t = _t(d)
        s = np.zeros(len(t))
        chords = [(220, 277.2, 329.6, 440), (196, 246.9, 293.7, 392), (174.6, 220, 261.6, 349.2),
                  (196, 246.9, 329.6, 392)]
        seg = d / len(chords)
        for i, ch in enumerate(chords):
            m = (t >= i * seg) & (t < (i + 1) * seg + 1.5)
            tt = t - i * seg
            env = np.clip(tt / 1.2, 0, 1) * np.clip((seg + 1.5 - tt) / 1.5, 0, 1)
            for f in ch:
                s += m * env * (np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * f * 2 * t))
        s += _periodic_noise_band(len(t), 100, 400, rng) / 60
        return _norm(_reverb(_fade(s, .5, 2.0), rng, 2.5, .5), .6)

    table = {
        "ship_engine": ship_engine, "ship_boost": ship_boost, "ship_hit": ship_hit, "landing": landing,
        "reactor_hum": reactor_hum, "ambience": ambience,
        "creak0": lambda: creak(0), "creak1": lambda: creak(1), "creak2": lambda: creak(2),
        "metal_bang": metal_bang, "vent_bang": vent_bang,
        "step0": lambda: footstep(0), "step1": lambda: footstep(1), "step2": lambda: footstep(2),
        "step3": lambda: footstep(3), "vent_crawl": vent_crawl, "hurt": hurt, "heartbeat": heartbeat,
        "breath": breath, "gunshot": gunshot, "dry_fire": dry_fire, "reload": reload,
        "knife_swing": knife_swing, "knife_hit": knife_hit, "knife_break": knife_break,
        "alien_screech0": lambda: alien_screech(0), "alien_screech1": lambda: alien_screech(1),
        "alien_die": alien_die, "alien_skitter": alien_skitter,
        "creature_roar": creature_roar, "creature_growl": creature_growl, "creature_step": creature_step,
        "creature_hiss": creature_hiss, "death_sting": death_sting,
        "alarm": alarm, "horror_music": horror_music, "tension_drone": tension_drone,
        "door_open": door_open, "locker_open": locker_open, "pickup": pickup, "rustle": rustle,
        "hdd_pickup": hdd_pickup, "beep": beep, "flashlight_click": flashlight_click, "nv_on": nv_on,
        "spark": spark, "ui_select": ui_select, "victory": victory,
    }
    # armes et araignées v2 (remplacent les anciennes versions de même nom)
    pending = [n for n in table if force or not os.path.exists(os.path.join(SOUND_DIR, n + ".wav"))]
    ws_names = ("gunshot", "gun_tail_small", "tinnitus", "alien_skitter0", "alien_scratch_loop")
    need_ws = force or any(not os.path.exists(os.path.join(SOUND_DIR, n + ".wav")) for n in ws_names)
    ws = gen_weapons_spiders(np.random.default_rng(417)) if need_ws else {}
    for name, sig in ws.items():
        _write(name, sig)
    # courant du vaisseau et screamer
    ps_names = ("lever_pull", "reactor_spinup", "relay2", "power_down", "door_force", "screamer",
                "screamer_stinger", "screamer_music", "screamer_flee", "fuse_insert", "power_thump",
                "door_force_open")
    need_ps = force or any(not os.path.exists(os.path.join(SOUND_DIR, n + ".wav")) for n in ps_names)
    ps = gen_power_screamer(np.random.default_rng(666)) if need_ps else {}
    for name, sig in ps.items():
        _write(name, sig)
    # histoire (titre, hallucinations, révélation)
    st_names = ("sinus_hum", "sinus_swell", "whisper2", "voice_call", "static_burst", "glitch_burst")
    need_st = force or any(not os.path.exists(os.path.join(SOUND_DIR, n + ".wav")) for n in st_names)
    st = gen_story(np.random.default_rng(2187)) if need_st else {}
    for name, sig in st.items():
        _write(name, sig)
    ps.update(st)
    for name in pending:
        if name in ws:
            continue
        _write(name, table[name]())
    for name in list(table) + list(ws) + list(ps):
        sounds[name] = os.path.join(SOUND_DIR, name + ".wav")
    # cache déjà présent : on retrouve aussi les autres sons sur le disque
    for f in os.listdir(SOUND_DIR):
        if f.endswith(".wav"):
            sounds.setdefault(f[:-4], os.path.join(SOUND_DIR, f))
    # sons personnels : un fichier placé dans sounds/ (ex. screamer.wav ou screamer.ogg) remplace le son généré
    custom = os.path.join(BASE_DIR, C.CUSTOM_SOUND_DIR)
    if os.path.isdir(custom):
        for f in sorted(os.listdir(custom)):
            name, ext = os.path.splitext(f)
            if ext.lower() in (".wav", ".ogg") and name in sounds:
                sounds[name] = os.path.join(custom, f)
                print(f"[audio] son personnel utilisé : {f}")
    return sounds


# ============================================================================
# LECTURE
# ============================================================================
class LoopSound:
    """Son en boucle dont on règle volume / hauteur / balance en continu."""

    def __init__(self, snd, base_volume, channel):
        self.snd = snd
        self.base = base_volume
        self.channel = channel
        self.target = 0.0
        self.current = 0.0
        self.pitch = 1.0
        self.fade_speed = 2.0
        if snd:
            snd.setLoop(True)
            snd.setVolume(0)
            snd.play()

    def set(self, volume, pitch=None, balance=None, fade=None):
        self.target = volume
        if pitch is not None:
            self.pitch = pitch
        if fade is not None:
            self.fade_speed = fade
        if self.snd and balance is not None:
            self.snd.setBalance(balance)

    def update(self, dt, master):
        if not self.snd:
            return
        k = min(1.0, dt * self.fade_speed)
        self.current += (self.target - self.current) * k
        self.snd.setVolume(max(0.0, self.current * self.base * master))
        self.snd.setPlayRate(self.pitch)

    def stop(self):
        if self.snd:
            self.snd.stop()


class AudioSystem:
    """Chargement des .wav et lecture (2D / 3D / boucles)."""

    POLY = {"step0": 2, "step1": 2, "step2": 2, "step3": 2, "gunshot": 3, "gun_tail_small": 2,
            "gun_tail_large": 2, "alien_screech0": 2, "alien_screech1": 2, "alien_die": 2, "knife_swing": 2,
            "knife_hit": 2, "alien_skitter": 2, "creature_step": 3, "pickup": 2, "beep": 2, "ui_select": 2,
            "spark": 2, "casing0": 2, "casing1": 2, "casing2": 2, "alien_skitter0": 2, "alien_skitter1": 2,
            "alien_skitter2": 2, "alien_skitter3": 2, "alien_click0": 2, "alien_click1": 2, "relay0": 2,
            "relay1": 2, "relay2": 2, "heartbeat": 2, "door_force": 2, "fuse_insert": 2}

    def __init__(self):
        from ursina import application
        from panda3d.core import Filename
        self.base = application.base
        self.paths = gen_all(C.REGENERATE_SOUNDS)
        self.pool = {}
        self.cursor = {}
        self.loops = {}
        self.master = C.MASTER_VOLUME
        self.listener_pos = (0, 0, 0)
        self.listener_right = (1, 0, 0)
        # « ducking » : 0 = silence total (screamer, levier), remonte ensuite progressivement
        self.duck = 1.0
        self.duck_target = 1.0
        self.duck_rate = 1.0
        self.duck_exempt = set()
        for name, path in self.paths.items():
            n = self.POLY.get(name, 1)
            lst = []
            for _ in range(n):
                try:
                    s = self.base.loader.loadSfx(Filename.fromOsSpecific(path))
                except Exception:
                    s = None
                lst.append(s)
            self.pool[name] = lst
            self.cursor[name] = 0

    def _get(self, name):
        lst = self.pool.get(name)
        if not lst:
            return None
        i = self.cursor[name]
        self.cursor[name] = (i + 1) % len(lst)
        return lst[i]

    def set_listener(self, pos, right):
        self.listener_pos = (pos[0], pos[1], pos[2])
        self.listener_right = (right[0], right[1], right[2])

    def silence(self, keep=(), keep_loops=()):
        """Coupe tout d'un coup : boucles d'ambiance, musique et sons en cours (sauf ceux de keep)."""
        from panda3d.core import AudioSound
        self.duck = self.duck_target = 0.0
        self.duck_exempt = set(keep_loops)
        for name, lst in self.pool.items():
            if name in keep:
                continue
            for snd in lst:
                if snd is not None and snd.status() == AudioSound.PLAYING:
                    snd.stop()
        for key, lp in self.loops.items():
            if key not in self.duck_exempt:
                lp.current = 0.0
                if lp.snd:
                    lp.snd.setVolume(0)

    def restore(self, fade=2.0):
        """Fait revenir progressivement l'ambiance après un silence."""
        self.duck_target = 1.0
        self.duck_rate = 1.0 / max(.05, fade)

    def play(self, name, volume=1.0, pitch=1.0, balance=0.0, music=False, ignore_duck=False):
        s = self._get(name)
        if s is None:
            return None
        vol = volume * self.master * (C.MUSIC_VOLUME if music else C.SFX_VOLUME)
        if not ignore_duck:
            vol *= self.duck
        s.setVolume(max(0.0, min(1.0, vol)))
        s.setPlayRate(pitch)
        s.setBalance(max(-1, min(1, balance)))
        s.setLoop(False)
        s.play()
        return s

    def spatial(self, pos, max_dist=None):
        """Renvoie (atténuation 0..1, balance -1..1) d'une source 3D."""
        max_dist = max_dist or C.SOUND_MAX_DISTANCE
        lx, ly, lz = self.listener_pos
        dx, dy, dz = pos[0] - lx, pos[1] - ly, pos[2] - lz
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d >= max_dist:
            return 0.0, 0.0
        att = (1 - d / max_dist) ** 2
        if d > 0.01:
            rx, ry, rz = self.listener_right
            bal = (dx * rx + dy * ry + dz * rz) / d * 0.85
        else:
            bal = 0.0
        return att, bal

    def play_at(self, name, pos, volume=1.0, pitch=1.0, max_dist=None, occluded=False, ignore_duck=False):
        """
        Son 3D. occluded=True : la source est derrière une cloison ou dans un
        conduit -> version étouffée (suffixe _m) si elle existe, volume réduit.
        """
        att, bal = self.spatial(pos, max_dist)
        if att <= 0.01:
            return None
        if occluded:
            volume *= .45
            if name + "_m" in self.pool:
                name = name + "_m"
        return self.play(name, volume * att, pitch, bal, ignore_duck=ignore_duck)

    def play_var(self, prefix, count, volume=1.0, pos=None, pitch_range=(.9, 1.12), max_dist=None,
                 occluded=False):
        """Joue une variante au hasard (prefix0..prefixN-1) avec une hauteur aléatoire."""
        import random
        name = f"{prefix}{random.randrange(count)}"
        pitch = random.uniform(*pitch_range)
        if pos is None:
            return self.play(name, volume, pitch)
        return self.play_at(name, pos, volume, pitch, max_dist, occluded)

    def loop(self, key, name, base_volume=1.0, music=False, ambient=False):
        """Crée (ou récupère) une boucle nommée 'key'."""
        if key in self.loops:
            return self.loops[key]
        from panda3d.core import Filename
        snd = None
        path = self.paths.get(name)
        if path:
            try:
                snd = self.base.loader.loadSfx(Filename.fromOsSpecific(path))
            except Exception:
                snd = None
        mult = C.MUSIC_VOLUME if music else (C.AMBIENT_VOLUME if ambient else C.SFX_VOLUME)
        lp = LoopSound(snd, base_volume * mult, key)
        self.loops[key] = lp
        return lp

    def stop_loop(self, key):
        lp = self.loops.pop(key, None)
        if lp:
            lp.stop()

    def stop_all_loops(self):
        for k in list(self.loops):
            self.stop_loop(k)

    def update(self, dt):
        if self.duck != self.duck_target:
            step = self.duck_rate * dt
            d = self.duck_target - self.duck
            self.duck = self.duck_target if abs(d) <= step else self.duck + math.copysign(step, d)
            if self.duck >= 1.0:
                self.duck_exempt = set()
        for key, lp in self.loops.items():
            lp.update(dt, self.master * (1.0 if key in self.duck_exempt else self.duck))
