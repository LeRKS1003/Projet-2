# -*- coding: utf-8 -*-
"""
startup.py — Préparation AVANT l'ouverture de la fenêtre : moteur audio et plein écran.

SON
  Trois moteurs audio possibles :
  * « pygame » (SDL2) : PAR DÉFAUT. pygame est déjà installé pour la manette ;
    SDL ouvre la sortie son par défaut de Windows (WASAPI, sinon DirectSound,
    sinon WinMM). C'est le plus fiable.
  * « openal » et « fmod » : les moteurs de Panda3D (secours).
  * AUDIO_BACKEND = "auto" (config.py) : pygame si la sortie son s'ouvre, sinon
    OpenAL testé avant d'ouvrir la fenêtre, sinon relance automatique avec FMOD.
  * Maj+F8 en jeu passe au moteur suivant (pygame -> OpenAL -> FMOD), le
    mémorise (generated/audio_moteur.txt) et relance le jeu.
  * Un rapport est écrit dans generated/rapport_son.txt.

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
BACKEND_FILE = os.path.join(GEN_DIR, "audio_moteur.txt")    # (ancien fichier audio_backend.txt ignoré)
REPORT_FILE = os.path.join(GEN_DIR, "rapport_son.txt")
DEVICE_FILE = os.path.join(GEN_DIR, "audio_sortie.txt")      # sortie son choisie dans le menu
# une manette PS5 branchée en USB est aussi une « carte son » (petit haut-parleur + prise casque) :
# Windows la choisit souvent comme sortie par défaut... et on n'entend plus rien dans les enceintes
CONTROLLER_WORDS = ("wireless controller", "dualsense", "dualshock", "manette", "controller", "gamepad")
LIBS = {"openal": "p3openal_audio", "fmod": "p3fmod_audio"}
NAMES = {"pygame": "SDL / pygame", "openal": "OpenAL", "fmod": "FMOD"}
ORDER = ("pygame", "openal", "fmod")
ENV_KEY = "DERIVE_AUDIO_BACKEND"          # posé par la relance automatique (évite toute boucle)

# état lu par audio.py / main.py
STATE = {"backend": "openal", "auto_switched": False, "probe": {}, "sdl_driver": None,
         "devices": [], "device": None, "device_why": ""}


def _saved_choice():
    try:
        with open(BACKEND_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip().lower()
        return v if v in NAMES else None
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


def _is_controller(name):
    n = (name or "").lower()
    return any(w in n for w in CONTROLLER_WORDS)


def _saved_device():
    try:
        with open(DEVICE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _list_devices():
    try:
        from pygame._sdl2 import audio as sdl2_audio
        return [str(d) for d in sdl2_audio.get_audio_device_names(False)]
    except Exception:
        return []


def _pick_device(devices):
    """Choix de la sortie son : choix du menu, sinon config, sinon on évite la manette."""
    saved = _saved_device()
    if saved and saved in devices:
        return saved, "choisie dans le menu"
    want = (C.AUDIO_DEVICE or "").lower()
    if want:
        for d in devices:
            if want in d.lower():
                return d, "config.AUDIO_DEVICE"
    if any(_is_controller(d) for d in devices):
        others = [d for d in devices if not _is_controller(d)]
        if others:
            # enceintes / casque de l'ordinateur plutôt que le haut-parleur de la manette
            pref = ("haut-parleur", "speaker", "casque", "headphone", "headset", "realtek", "écouteurs")
            others.sort(key=lambda d: 0 if any(w in d.lower() for w in pref) else 1)
            return others[0], "manette évitée"
    return None, "sortie par défaut de Windows"


def init_pygame_mixer():
    """
    Ouvre la sortie son avec SDL (pygame.mixer). Essaie le pilote par défaut,
    puis les autres pilotes Windows. Renvoie (ok, info).
    """
    try:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
    except Exception as exc:
        return False, f"pygame absent : {exc}"
    drivers = [None]
    if sys.platform.startswith("win"):
        drivers += ["wasapi", "directsound", "winmm"]
    last = ""
    for drv in drivers:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.quit()
            if drv is None:
                os.environ.pop("SDL_AUDIODRIVER", None)
            else:
                os.environ["SDL_AUDIODRIVER"] = drv
            pygame.mixer.pre_init(44100, -16, 2, 1024)
            pygame.mixer.init(44100, -16, 2, 1024)
            if pygame.mixer.get_init():
                # sortie son : liste des périphériques, et on évite la manette PS5
                devices = _list_devices()
                STATE["devices"] = devices
                dev, why = _pick_device(devices)
                if dev is not None:
                    try:
                        pygame.mixer.quit()
                        pygame.mixer.init(44100, -16, 2, 1024, devicename=dev)
                    except Exception as exc:
                        print(f"[audio] sortie « {dev} » impossible ({exc}) : sortie par défaut")
                        dev, why = None, "sortie par défaut (l'autre a échoué)"
                        pygame.mixer.init(44100, -16, 2, 1024)
                STATE["device"] = dev
                STATE["device_why"] = why
                print(f"[audio] sorties son trouvées : {devices or '(liste indisponible)'}")
                print(f"[audio] sortie utilisée : {dev or 'par défaut'} ({why})")
                pygame.mixer.set_num_channels(C.AUDIO_CHANNELS)
                pygame.mixer.set_reserved(C.AUDIO_LOOP_CHANNELS)
                try:
                    name = pygame.mixer.get_driver() if hasattr(pygame.mixer, "get_driver") else (drv or "défaut")
                except Exception:
                    name = drv or "défaut"
                STATE["sdl_driver"] = name
                return True, f"pilote {name}, {pygame.mixer.get_init()}"
        except Exception as exc:
            last = str(exc)
    return False, f"aucune sortie son SDL ({last})"


def choose_audio_backend():
    """
    À appeler AVANT Ursina() : choisit le moteur audio et le configure.
    pygame (SDL) d'abord ; sinon OpenAL (testé), sinon relance avec FMOD.
    """
    from panda3d.core import loadPrcFileData
    forced = os.environ.get(ENV_KEY)
    pref = (C.AUDIO_BACKEND or "auto").lower()
    saved = _saved_choice()
    if forced in NAMES:
        backend = forced                              # processus relancé automatiquement
        STATE["auto_switched"] = True
    elif pref in NAMES:
        backend = pref                                # choix imposé dans config.py
    elif saved:
        backend = saved                               # choix mémorisé (Maj+F8)
    else:
        backend = "pygame"
    if backend == "pygame":
        ok, info = init_pygame_mixer()
        STATE["probe"]["pygame"] = (ok, info)
        print(f"[audio] sortie son SDL / pygame : {'OK' if ok else 'ÉCHEC'} ({info})")
        if ok:
            STATE["backend"] = "pygame"
            # Panda3D n'ouvre pas de second périphérique son
            loadPrcFileData("", "audio-library-name null")
            return "pygame"
        backend = "openal"                            # repli sur les moteurs de Panda3D
    if backend == "openal" and forced is None and pref == "auto":
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


def device_label():
    d = STATE.get("device")
    if not d:
        return "par défaut"
    return d if len(d) <= 34 else d[:32] + "…"


def cycle_output_device():
    """Menu « Sortie son » : passe à la sortie suivante (Auto, puis chaque périphérique) et relance le jeu."""
    opts = [None] + list(STATE.get("devices") or [])
    cur = STATE.get("device") if _saved_device() else None
    i = opts.index(cur) if cur in opts else 0
    nxt = opts[(i + 1) % len(opts)]
    try:
        os.makedirs(GEN_DIR, exist_ok=True)
        with open(DEVICE_FILE, "w", encoding="utf-8") as f:
            f.write(nxt or "")
    except OSError as exc:
        print("[audio] impossible d'enregistrer la sortie son :", exc)
    return restart_game()


def restart_game():
    env = dict(os.environ)
    env.pop(ENV_KEY, None)
    try:
        subprocess.Popen(_command(), env=env, cwd=HERE)
        return True
    except Exception as exc:
        print("[audio] relance impossible :", exc)
        return False


def switch_backend_and_restart():
    """Maj+F8 : passe au moteur audio suivant (pygame -> OpenAL -> FMOD), le mémorise et relance le jeu."""
    i = ORDER.index(STATE["backend"]) if STATE["backend"] in ORDER else 0
    other = ORDER[(i + 1) % len(ORDER)]
    if other == "fmod" and not fmod_available():
        other = ORDER[(i + 2) % len(ORDER)]
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
