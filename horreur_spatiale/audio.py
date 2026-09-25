# -*- coding: utf-8 -*-
"""
audio.py — Sons générés par code (numpy -> .wav au premier lancement) et lecture
avec une spatialisation simple : volume selon la distance, panoramique selon
l'angle par rapport à la caméra, atténuation si un mur sépare la source du joueur.
"""
import math
import os
import wave

import numpy as np
from panda3d.core import Filename
from ursina import application, camera

import config as C

SR = C.FREQ_ECHANTILLONNAGE
VERSION_SONS = "3"


# ---------------------------------------------------------------------------
# Outils de synthèse
# ---------------------------------------------------------------------------
def _t(duree):
    return np.arange(int(duree * SR)) / SR


def _bruit(n, rng):
    return rng.uniform(-1, 1, n)


def _passe_bas_rapide(x, taille):
    """Moyenne glissante (passe-bas bon marché)."""
    k = np.ones(int(taille)) / int(taille)
    return np.convolve(x, k, mode="same")


def _resonance(x, freq, q=30.0):
    """Filtre résonant (passe-bande à 2 pôles) pour les timbres métalliques."""
    w = 2 * math.pi * freq / SR
    r = 1 - w / q
    a1, a2 = -2 * r * math.cos(w), r * r
    y = np.zeros_like(x)
    y1 = y2 = 0.0
    g = (1 - r)
    for i in range(len(x)):
        v = g * x[i] - a1 * y1 - a2 * y2
        y2, y1 = y1, v
        y[i] = v
    return y


def _enveloppe(n, attaque, relache):
    e = np.ones(n)
    a = int(attaque * SR)
    r = int(relache * SR)
    if a > 0:
        e[:a] = np.linspace(0, 1, a)
    if r > 0:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _boucle(x, fondu=0.25):
    """Rend un son bouclable en fondant la fin dans le début."""
    n = int(fondu * SR)
    debut = x[:n].copy()
    x = x[n:]
    x[-n:] = x[-n:] * np.linspace(1, 0, n) + debut * np.linspace(0, 1, n)
    return x


def _normaliser(x, niveau=0.9):
    m = np.max(np.abs(x)) or 1
    return x / m * niveau


def _ecrire(chemin, x):
    x = np.clip(x, -1, 1)
    data = (x * 32767).astype(np.int16)
    with wave.open(chemin, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.tobytes())


# ---------------------------------------------------------------------------
# Recettes des sons
# ---------------------------------------------------------------------------
def s_reacteur(rng):
    t = _t(6.0)
    x = (np.sin(2 * np.pi * 45 * t) * 0.5 + np.sin(2 * np.pi * 90 * t) * 0.3 + np.sin(2 * np.pi * 135 * t) * 0.15
         + np.sin(2 * np.pi * 180.5 * t) * 0.05)
    x *= 0.8 + 0.2 * np.sin(2 * np.pi * (1 / 3) * t)
    x += _passe_bas_rapide(_bruit(len(t), rng), 30) * 0.6
    return _normaliser(_boucle(x), 0.7)


def s_ambiance(rng):
    t = _t(10.0)
    brun = np.cumsum(_bruit(len(t), rng))
    brun -= _passe_bas_rapide(brun, 4000)
    brun = _normaliser(brun, 1.0)
    x = brun * 0.7 + np.sin(2 * np.pi * 31 * t) * 0.25 * (0.6 + 0.4 * np.sin(2 * np.pi * 0.1 * t))
    x += np.sin(2 * np.pi * 62.3 * t) * 0.08
    return _normaliser(_boucle(x, 0.5), 0.6)


def s_pas(rng, graine):
    r = np.random.default_rng(graine)
    t = _t(0.35)
    n = len(t)
    choc = _bruit(n, r) * np.exp(-t * 90)
    x = choc * 0.5
    for f in r.uniform(160, 420, 3):
        x += _resonance(_bruit(n, r) * np.exp(-t * 60), f, 60) * 3
    x += np.sin(2 * np.pi * r.uniform(70, 95) * t) * np.exp(-t * 30) * 0.5
    return _normaliser(x, 0.8)


def s_grincement(rng, graine):
    r = np.random.default_rng(graine)
    duree = r.uniform(1.6, 2.6)
    t = _t(duree)
    f0 = r.uniform(55, 90)
    freq = f0 * (1 + 0.3 * np.sin(2 * np.pi * r.uniform(0.2, 0.6) * t)) + r.normal(0, 3, len(t)).cumsum() * 0.002
    phase = np.cumsum(freq) / SR * 2 * np.pi
    scie = (phase / (2 * np.pi)) % 1 * 2 - 1
    # frottement saccadé (stick-slip)
    saccade = (np.sin(phase * 0.5) > r.uniform(-0.2, 0.4)).astype(float)
    x = scie * saccade
    x = _resonance(x, r.uniform(300, 700), 25) * 2 + _resonance(x, r.uniform(900, 1600), 40)
    x *= _enveloppe(len(t), 0.3, 0.6)
    return _normaliser(x, 0.75)


def s_souffle(rng):
    t = _t(3.2)
    n = len(t)
    b = _bruit(n, rng)
    b = b - _passe_bas_rapide(b, 3)
    b = _passe_bas_rapide(b, 4)
    env = np.clip(np.sin(2 * np.pi * t / 3.2 * 2 - 0.3), 0, 1) ** 1.5
    grogne = np.sin(2 * np.pi * 68 * t + np.sin(2 * np.pi * 7 * t) * 2) * 0.35
    x = (b * 1.4 + grogne * (0.5 + 0.5 * np.sin(2 * np.pi * 13 * t))) * env
    return _normaliser(x, 0.8)


def s_grattement(rng):
    t = _t(1.8)
    n = len(t)
    x = np.zeros(n)
    pos = 0
    while pos < n - 3000:
        l = int(rng.uniform(0.02, 0.12) * SR)
        g = _bruit(l, rng)
        g = g - _passe_bas_rapide(g, 6)
        x[pos:pos + l] += g * np.hanning(l) * rng.uniform(0.4, 1.0)
        pos += int(rng.uniform(0.03, 0.2) * SR)
    x = _resonance(x, 1200, 8) * 0.6 + x * 0.6
    return _normaliser(x, 0.8)


def s_coup_conduit(rng):
    t = _t(0.9)
    n = len(t)
    x = _bruit(n, rng) * np.exp(-t * 40) * 0.4
    for f in (110, 173, 260, 410):
        x += _resonance(_bruit(n, rng) * np.exp(-t * 20), f, 90) * 4
    return _normaliser(x * np.exp(-t * 3), 0.9)


def s_cri(rng):
    t = _t(2.2)
    x = np.zeros(len(t))
    for k in range(5):
        f = 700 + k * 173 + 300 * t / 2.2
        vib = np.sin(2 * np.pi * (6 + k) * t) * 40
        phase = np.cumsum(f + vib) / SR * 2 * np.pi
        x += ((phase / (2 * np.pi)) % 1 * 2 - 1) * 0.3
    x += _bruit(len(t), rng) * 0.4
    x = np.tanh(x * 3)
    x *= _enveloppe(len(t), 0.02, 0.8)
    return _normaliser(x, 0.95)


def s_porte(rng):
    t = _t(1.1)
    n = len(t)
    f = 260 + 220 * np.clip(t / 0.7, 0, 1)
    phase = np.cumsum(f) / SR * 2 * np.pi
    moteur = (np.sin(phase) * 0.4 + np.sin(phase * 2) * 0.2) * _enveloppe(n, 0.05, 0.3) * (t < 0.85)
    souffle = _passe_bas_rapide(_bruit(n, rng), 5) * np.exp(-((t - 0.3) ** 2) / 0.05) * 1.2
    clac = np.zeros(n)
    i0 = int(0.85 * SR)
    clac[i0:] = _bruit(n - i0, rng) * np.exp(-np.arange(n - i0) / SR * 60)
    clac[i0:] += np.sin(2 * np.pi * 90 * np.arange(n - i0) / SR) * np.exp(-np.arange(n - i0) / SR * 25)
    return _normaliser(moteur + souffle + clac, 0.7)


def s_refus(rng):
    t = _t(0.35)
    x = np.sign(np.sin(2 * np.pi * 110 * t)) * 0.5 * _enveloppe(len(t), 0.005, 0.05)
    return _normaliser(_passe_bas_rapide(x, 4), 0.6)


def s_coeur(rng):
    t = _t(0.9)
    x = np.zeros(len(t))
    for debut, amp in ((0.0, 1.0), (0.24, 0.7)):
        tt = np.clip(t - debut, 0, None)
        x += np.sin(2 * np.pi * 48 * tt) * np.exp(-tt * 18) * amp * (t >= debut)
    return _normaliser(x, 0.95)


def s_ramasser(rng):
    t = _t(0.3)
    x = np.sin(2 * np.pi * 880 * t) * (t < 0.1) + np.sin(2 * np.pi * 1320 * t) * (t >= 0.12)
    return _normaliser(x * _enveloppe(len(t), 0.005, 0.05), 0.5)


def s_clic(rng):
    t = _t(0.06)
    x = _bruit(len(t), rng) * np.exp(-t * 200) + np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 150)
    return _normaliser(x, 0.6)


def s_alarme(rng):
    t = _t(2.0)
    f = np.where((t % 1.0) < 0.5, 660, 880)
    phase = np.cumsum(f) / SR * 2 * np.pi
    x = np.tanh(np.sin(phase) * 2) * 0.6
    return _normaliser(x, 0.5)


def s_courant(rng):
    t = _t(3.5)
    n = len(t)
    f = 30 + 170 * (t / 3.5) ** 1.5
    phase = np.cumsum(f) / SR * 2 * np.pi
    x = (np.sin(phase) + 0.5 * np.sin(phase * 2) + 0.25 * np.sin(phase * 3)) * _enveloppe(n, 0.5, 0.8)
    clac = np.zeros(n)
    clac[:int(0.4 * SR)] = _bruit(int(0.4 * SR), rng) * np.exp(-np.arange(int(0.4 * SR)) / SR * 12)
    return _normaliser(x * 0.8 + clac, 0.9)


def s_neon(rng):
    t = _t(2.0)
    x = np.sign(np.sin(2 * np.pi * 100 * t)) * 0.2 + np.sin(2 * np.pi * 200 * t) * 0.3
    x = _passe_bas_rapide(x, 8) * (0.8 + 0.2 * _passe_bas_rapide(_bruit(len(t), rng), 800) * 10)
    return _normaliser(_boucle(x, 0.2), 0.4)


def s_interface(rng):
    t = _t(0.5)
    x = sum(np.sin(2 * np.pi * f * t) * ((t > d) & (t < d + 0.09)) for f, d in ((523, 0), (659, 0.1), (784, 0.2), (1046, 0.3)))
    return _normaliser(x * _enveloppe(len(t), 0.005, 0.1), 0.5)


def s_grille(rng):
    t = _t(0.6)
    n = len(t)
    x = _bruit(n, rng) * np.exp(-t * 30) * 0.5
    for f in (340, 520, 780, 1150):
        x += _resonance(_bruit(n, rng) * np.exp(-t * 25), f, 120) * 3
    return _normaliser(x, 0.85)


def s_navette(rng):
    t = _t(5.0)
    n = len(t)
    b = _passe_bas_rapide(_bruit(n, rng), 12)
    montee = np.clip(t / 3.5, 0, 1) ** 2
    x = b * (0.2 + montee) + np.sin(2 * np.pi * (40 + 60 * montee) * t) * 0.4 * montee
    return _normaliser(x * _enveloppe(n, 0.3, 0.8), 0.9)


def s_haletement(rng):
    t = _t(1.6)
    b = _passe_bas_rapide(_bruit(len(t), rng), 3)
    env = np.clip(np.sin(2 * np.pi * t * 1.25), 0, 1) ** 2
    return _normaliser(b * env, 0.6)


RECETTES = {
    "reacteur": s_reacteur,
    "ambiance": s_ambiance,
    "pas_1": lambda r: s_pas(r, 11), "pas_2": lambda r: s_pas(r, 12),
    "pas_3": lambda r: s_pas(r, 13), "pas_4": lambda r: s_pas(r, 14),
    "grincement_1": lambda r: s_grincement(r, 21), "grincement_2": lambda r: s_grincement(r, 22),
    "grincement_3": lambda r: s_grincement(r, 23),
    "souffle": s_souffle,
    "grattement": s_grattement,
    "coup_conduit": s_coup_conduit,
    "cri": s_cri,
    "porte": s_porte,
    "refus": s_refus,
    "coeur": s_coeur,
    "ramasser": s_ramasser,
    "clic": s_clic,
    "alarme": s_alarme,
    "courant": s_courant,
    "neon": s_neon,
    "interface": s_interface,
    "grille": s_grille,
    "navette": s_navette,
    "haletement": s_haletement,
}


def generer_sons(dossier, forcer=False):
    """Crée les fichiers .wav manquants (quelques secondes au premier lancement)."""
    os.makedirs(dossier, exist_ok=True)
    marqueur = os.path.join(dossier, "version.txt")
    if not forcer and os.path.exists(marqueur) and open(marqueur).read().strip() == VERSION_SONS:
        if all(os.path.exists(os.path.join(dossier, n + ".wav")) for n in RECETTES):
            return
    rng = np.random.default_rng(1979)
    for nom, recette in RECETTES.items():
        chemin = os.path.join(dossier, nom + ".wav")
        if forcer or not os.path.exists(chemin) or not os.path.exists(marqueur):
            _ecrire(chemin, recette(rng))
    with open(marqueur, "w") as f:
        f.write(VERSION_SONS)


# ---------------------------------------------------------------------------
# Lecture et spatialisation
# ---------------------------------------------------------------------------
class Emetteur:
    """Son en boucle attaché à une position (réacteur, souffle de la créature...)."""

    def __init__(self, gestionnaire, nom, position=None, volume=1.0, portee=None):
        self.g = gestionnaire
        self.son = gestionnaire._charger(nom, unique=True)
        self.position = position
        self.volume = volume
        self.portee = portee or C.DISTANCE_AUDIO_MAX
        self.actif = True
        if self.son:
            self.son.setLoop(True)
            self.son.setVolume(0)
            self.son.play()

    def stop(self):
        self.actif = False
        if self.son:
            self.son.stop()


class GestionnaireAudio:
    def __init__(self, base_dir):
        self.dossier = os.path.join(base_dir, C.DOSSIER_SONS)
        try:
            generer_sons(self.dossier)
        except OSError as e:
            print("Audio : impossible d'écrire les sons :", e)
        self.cache = {}
        self.pool_index = {}
        self.emetteurs = []
        self.occlusion = None       # fonction (x0, z0, x1, z1) -> bool (ligne de vue)
        self.volume_general = C.VOLUME_GENERAL

    def _chemin(self, nom):
        return Filename.fromOsSpecific(os.path.join(self.dossier, nom + ".wav"))

    def _charger(self, nom, unique=False):
        """Charge un son. Plusieurs instances par son permettent de les superposer."""
        try:
            if unique:
                return application.base.loader.loadSfx(self._chemin(nom))
            if nom not in self.cache:
                self.cache[nom] = [application.base.loader.loadSfx(self._chemin(nom)) for _ in range(3)]
                self.pool_index[nom] = 0
            k = self.pool_index[nom]
            self.pool_index[nom] = (k + 1) % 3
            return self.cache[nom][k]
        except Exception as e:  # pas de périphérique audio : on continue en silence
            print("Audio indisponible pour", nom, e)
            return None

    def _spatial(self, position, portee):
        """Calcule (volume, balance) d'une source par rapport à la caméra."""
        if position is None:
            return 1.0, 0.0
        cam = camera.world_position
        dx, dz = position.x - cam.x, position.z - cam.z
        dy = position.y - cam.y
        d = math.sqrt(dx * dx + dz * dz + dy * dy * 0.5)
        if d >= portee:
            return 0.0, 0.0
        v = (1 - d / portee) ** 2
        if self.occlusion and d > 2.5 and not self.occlusion(cam.x, cam.z, position.x, position.z):
            v *= 0.45
        droite = camera.right
        bal = (dx * droite.x + dz * droite.z) / (d + 0.001)
        return v, max(-0.85, min(0.85, bal))

    def jouer(self, nom, position=None, volume=1.0, pitch=1.0, portee=None):
        son = self._charger(nom)
        if son is None:
            return None
        v, bal = self._spatial(position, portee or C.DISTANCE_AUDIO_MAX)
        if v <= 0.001:
            return None
        son.setVolume(min(1.0, v * volume * self.volume_general))
        son.setBalance(bal)
        son.setPlayRate(pitch)
        son.play()
        return son

    def boucle(self, nom, position=None, volume=1.0, portee=None):
        e = Emetteur(self, nom, position, volume, portee)
        self.emetteurs.append(e)
        return e

    def maj(self):
        for e in self.emetteurs:
            if not e.actif or not e.son:
                continue
            v, bal = self._spatial(e.position, e.portee)
            e.son.setVolume(min(1.0, v * e.volume * self.volume_general))
            e.son.setBalance(bal)

    def tout_arreter(self):
        for e in self.emetteurs:
            e.stop()
        self.emetteurs = []
        for liste in self.cache.values():
            for s in liste:
                s.stop()
