# -*- coding: utf-8 -*-
"""
audio.py — Génération procédurale de tous les sons (numpy -> .wav) et
lecture avec spatialisation simple (volume selon la distance, balance
gauche/droite selon l'orientation de la caméra).

Les .wav sont créés au premier lancement dans generated/sounds/ puis
réutilisés. Les boucles (moteurs, réacteur, alarme, musique) sont
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
SOUND_DIR = os.path.join(BASE_DIR, C.SOUND_CACHE_DIR)


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
# SONS
# ============================================================================
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
    for name, fn in table.items():
        path = os.path.join(SOUND_DIR, name + ".wav")
        if force or not os.path.exists(path):
            _write(name, fn())
        sounds[name] = path
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

    POLY = {"step0": 2, "step1": 2, "step2": 2, "step3": 2, "gunshot": 3, "alien_screech0": 3,
            "alien_screech1": 3, "alien_die": 3, "knife_swing": 2, "knife_hit": 2, "alien_skitter": 3,
            "creature_step": 3, "pickup": 2, "beep": 2, "ui_select": 2, "spark": 2}

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

    def play(self, name, volume=1.0, pitch=1.0, balance=0.0, music=False):
        s = self._get(name)
        if s is None:
            return None
        vol = volume * self.master * (C.MUSIC_VOLUME if music else C.SFX_VOLUME)
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

    def play_at(self, name, pos, volume=1.0, pitch=1.0, max_dist=None):
        att, bal = self.spatial(pos, max_dist)
        if att <= 0.01:
            return None
        return self.play(name, volume * att, pitch, bal)

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
        for lp in self.loops.values():
            lp.update(dt, self.master)
