# -*- coding: utf-8 -*-
"""
startup.py — Préparation AVANT l'ouverture de la fenêtre : moteur audio et plein écran.

SON
  Panda3D choisit son moteur audio une seule fois, au démarrage. Sous Windows,
  la roue pip de Panda3D fournit DEUX moteurs : OpenAL (par défaut) et FMOD.
  * AUDIO_BACKEND = "auto" (config.py) : on teste OpenAL avant d'ouvrir la
    fenêtre. S'il n'ouvre aucun périphérique, le jeu se relance tout seul
    avec FMOD (une seule fois, sans boucle).
  * Maj+F8 en jeu bascule OpenAL <-> FMOD (choix mémorisé dans
    generated/audio_backend.txt) et relance le jeu.
  * Un rapport est écrit dans generated/rapport_son.txt (à m'envoyer si le
    son ne marche toujours pas).

PLEIN ÉCRAN
  « Plein écran fenêtré » : fenêtre sans bordure à la taille exacte de
  l'écran (pas de changement de résolution, Alt+Tab sans souci).
  FULLSCREEN = True dans config.py ; F11 ou Alt+Entrée bascule en jeu.
"""
import os
import subprocess
import sys

import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
GEN_DIR = os.path.join(HERE, "generated")
BACKEND_FILE = os.path.join(GEN_DIR, "audio_backend.txt")
REPORT_FILE = os.path.join(GEN_DIR, "rapport_son.txt")
LIBS = {"openal": "p3openal_audio", "fmod": "p3fmod_audio"}
NAMES = {"openal": "OpenAL", "fmod": "FMOD"}
ENV_KEY = "DERIVE_AUDIO_BACKEND"          # posé par la relance automatique (évite toute boucle)

# état lu par audio.py / main.py
STATE = {"backend": "openal", "auto_switched": False, "probe": {}}


def _saved_choice():
    try:
        with open(BACKEND_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip().lower()
        return v if v in LIBS else None
    except OSError:
        return None


def save_choice(backend):
    try:
        os.makedirs(GEN_DIR, exist_ok=True)
        with open(BACKEND_FILE, "w", encoding="utf-8") as f:
            f.write(backend)
    except OSError as exc:
        print("[audio] impossible d'enregistrer le choix du moteur audio :", exc)


def fmod_available():
    """FMOD est fourni avec Panda3D sous Windows (libp3fmod_audio.dll), pas sous Linux."""
    try:
        import panda3d
        d = os.path.dirname(panda3d.__file__)
        return any(f.startswith("libp3fmod_audio") for f in os.listdir(d))
    except Exception:
        return False


def probe(backend):
    """
    Essaie d'ouvrir le périphérique son avec ce moteur (sans fenêtre).
    ATTENTION : Panda3D garde en mémoire la PREMIÈRE bibliothèque chargée :
    on ne peut sonder qu'un seul moteur par processus.
    """
    from panda3d.core import loadPrcFileData, AudioManager
    loadPrcFileData("", f"audio-library-name {LIBS[backend]}")
    try:
        m = AudioManager.createAudioManager()
    except Exception as exc:
        return False, f"exception : {exc}"
    ok = bool(m is not None and m.isValid() and type(m).__name__ != "NullAudioManager")
    info = type(m).__name__ if m is not None else "aucun"
    try:
        m.shutdown()
    except Exception:
        pass
    return ok, info


def _command():
    """Commande pour relancer le jeu (chemin absolu : marche même si le dossier courant a changé)."""
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if not os.path.isfile(script):
        script = os.path.join(HERE, "main.py")
    return [sys.executable, script] + list(sys.argv[1:])


def _relaunch(backend):
    """Relance le jeu avec un autre moteur audio (même console, même arguments) et attend sa fin."""
    env = dict(os.environ)
    env[ENV_KEY] = backend
    print(f"[audio] OpenAL n'a ouvert aucune sortie son -> relance automatique avec {NAMES[backend]}...")
    try:
        code = subprocess.call(_command(), env=env, cwd=HERE)
    except Exception as exc:
        print("[audio] relance impossible :", exc)
        return False
    sys.exit(code)


def choose_audio_backend():
    """
    À appeler AVANT Ursina() : choisit le moteur audio, le configure (prc) et,
    en mode auto, se relance avec FMOD si OpenAL ne fonctionne pas.
    """
    from panda3d.core import loadPrcFileData
    forced = os.environ.get(ENV_KEY)
    pref = (C.AUDIO_BACKEND or "auto").lower()
    saved = _saved_choice()
    if forced in LIBS:
        backend = forced                              # processus relancé automatiquement
        STATE["auto_switched"] = True
    elif pref in LIBS:
        backend = pref                                # choix imposé dans config.py
    elif saved:
        backend = saved                               # choix mémorisé (Maj+F8)
    else:
        backend = "openal"
    if pref == "auto" and forced is None and backend == "openal":
        ok, info = probe("openal")
        STATE["probe"]["openal"] = (ok, info)
        print(f"[audio] test OpenAL avant ouverture de la fenêtre : {'OK' if ok else 'ÉCHEC'} ({info})")
        if not ok and fmod_available():
            _relaunch("fmod")                         # ne revient que si la relance a échoué
    STATE["backend"] = backend
    loadPrcFileData("", f"audio-library-name {LIBS[backend]}")
    loadPrcFileData("", "audio-active #t")
    loadPrcFileData("", "audio-sfx-active #t")
    loadPrcFileData("", "audio-music-active #t")
    return backend


def switch_backend_and_restart():
    """Maj+F8 : passe à l'autre moteur audio, le mémorise et relance le jeu."""
    other = "fmod" if STATE["backend"] == "openal" else "openal"
    save_choice(other)
    env = dict(os.environ)
    env.pop(ENV_KEY, None)
    try:
        subprocess.Popen(_command(), env=env, cwd=HERE)
    except Exception as exc:
        print("[audio] relance impossible :", exc)
        return None
    return other


def write_report(lines):
    """Rapport son lisible (generated/rapport_son.txt)."""
    try:
        os.makedirs(GEN_DIR, exist_ok=True)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("DÉRIVE — rapport son\n")
            f.write(f"Python {sys.version.split()[0]} — {sys.platform}\n")
            for ln in lines:
                f.write(ln + "\n")
    except OSError:
        pass


# ============================================================================
# PLEIN ÉCRAN
# ============================================================================
def monitor_rect():
    """(x, y, largeur, hauteur) de l'écran principal, ou None si inconnu."""
    try:
        from screeninfo import get_monitors
        mons = get_monitors()
        if mons:
            m = next((e for e in mons if getattr(e, "is_primary", False)), mons[0])
            return int(m.x), int(m.y), int(m.width), int(m.height)
    except Exception:
        pass
    return None


def initial_window():
    """Arguments de fenêtre pour Ursina() : (taille, sans bordure)."""
    if C.FULLSCREEN:
        r = monitor_rect()
        if r is not None:
            return (r[2], r[3]), True
    return tuple(C.WINDOW_SIZE), False


class DisplayMode:
    """Bascule plein écran fenêtré <-> fenêtre (F11 / Alt+Entrée)."""

    def __init__(self, base):
        self.base = base
        self.full = False
        size, borderless = initial_window()
        self.full = borderless

    def set(self, full):
        from panda3d.core import WindowProperties
        wp = WindowProperties()
        r = monitor_rect()
        if full:
            if r is None:
                try:
                    pipe = self.base.pipe
                    r = (0, 0, pipe.getDisplayWidth(), pipe.getDisplayHeight())
                except Exception:
                    return
            wp.setUndecorated(True)
            wp.setOrigin(r[0], r[1])
            wp.setSize(r[2], r[3])
        else:
            w, h = C.WINDOW_SIZE
            wp.setUndecorated(False)
            wp.setSize(int(w), int(h))
            if r is not None:
                wp.setOrigin(int(r[0] + (r[2] - w) / 2), int(r[1] + (r[3] - h) / 2))
        try:
            self.base.win.requestProperties(wp)
        except Exception as exc:
            print("[affichage] changement de mode impossible :", exc)
            return
        self.full = full
        print(f"[affichage] {'plein écran' if full else 'fenêtre'}"
              + (f" {r[2]}x{r[3]}" if full and r else ""))

    def toggle(self):
        self.set(not self.full)
        return self.full
