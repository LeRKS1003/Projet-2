# -*- coding: utf-8 -*-
"""
controller.py — Manette PS5 DualSense via pygame.joystick (SDL2), en USB ou Bluetooth.

* pygame n'ouvre aucune fenêtre : le pilote vidéo SDL « dummy » est utilisé et
  SDL est autorisé à lire la manette même quand la fenêtre du jeu (Panda3D) a le focus.
* Détection automatique au lancement et lors d'un branchement / d'une reconnexion.
* Les index des axes et boutons varient selon l'OS et le pilote : ils sont définis
  dans config.py (profils « sdl » et « linux ») et visibles en mode debug (F3).
* Zone morte radiale et courbe de sensibilité réglables.
* Vibrations : joystick.rumble(basse_fréquence, haute_fréquence, durée_ms).
"""
import math
import os
import sys

import config as C

# Ces variables doivent être définies AVANT l'import de pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5", "1")
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5_RUMBLE", "1")
if C.SDL_PILOTE_VIDEO:
    os.environ.setdefault("SDL_VIDEODRIVER", C.SDL_PILOTE_VIDEO)

try:
    import pygame
    PYGAME_OK = True
except ImportError:  # le jeu reste jouable au clavier/souris
    pygame = None
    PYGAME_OK = False


def _zone_morte(x, y):
    """Zone morte radiale + courbe de réponse (exposant) : renvoie (x, y) corrigés."""
    m = math.hypot(x, y)
    zm = C.ZONE_MORTE_STICK
    if m < zm:
        return 0.0, 0.0
    m2 = min(1.0, (m - zm) / (1 - zm))
    m2 = m2 ** C.EXPOSANT_COURBE_STICK
    return x / m * m2, y / m * m2


class Manette:
    def __init__(self):
        self.joy = None
        self.nom = ""
        self.profil_nom = ""
        self.axes_idx = {}
        self.boutons_idx = {}
        self.etat = {}
        self.precedent = {}
        self.axes_bruts = []
        self.boutons_bruts = []
        self.chapeaux = []
        self.message = None             # message à afficher par le HUD (connexion...)
        self.derniere_activite = False  # vrai si la manette a été utilisée récemment
        self.ok = False
        if not (PYGAME_OK and C.MANETTE_ACTIVE):
            return
        try:
            pygame.display.init()
            pygame.joystick.init()
            self.ok = True
        except Exception as e:
            print("Manette : initialisation SDL impossible :", e)
            try:
                pygame.joystick.init()
                self.ok = True
            except Exception:
                self.ok = False
        if self.ok and pygame.joystick.get_count() > 0:
            self._ouvrir(0)

    # --------------------------------------------------------------
    @property
    def connectee(self):
        return self.joy is not None

    def _ouvrir(self, index):
        try:
            j = pygame.joystick.Joystick(index)
            j.init()
        except Exception as e:
            print("Manette : ouverture impossible :", e)
            return
        self.joy = j
        self.nom = j.get_name()
        nb = j.get_numbuttons()
        profil = C.MANETTE_PROFIL
        if profil == "auto":
            # SDL HIDAPI expose ~16 boutons ; le pilote noyau Linux en expose 13 + un chapeau
            profil = "sdl" if (nb >= 15 or sys.platform != "linux") else "linux"
        self.profil_nom = profil
        p = C.MANETTE_PROFILS[profil]
        self.axes_idx = p["axes"]
        self.boutons_idx = p["boutons"]
        self.message = f"Manette connectée : {self.nom} (profil {profil})"
        print(self.message, f"- {j.get_numaxes()} axes, {nb} boutons, {j.get_numhats()} chapeaux")

    def _fermer(self):
        if self.joy is not None:
            try:
                self.joy.quit()
            except Exception:
                pass
        self.joy = None
        self.message = "Manette déconnectée"

    # --------------------------------------------------------------
    def maj(self):
        """À appeler une fois par image : lit les évènements et l'état de la manette."""
        if not self.ok:
            return
        try:
            for ev in pygame.event.get():
                if ev.type == pygame.JOYDEVICEADDED and self.joy is None:
                    self._ouvrir(ev.device_index)
                elif ev.type == pygame.JOYDEVICEREMOVED:
                    if self.joy is not None and getattr(ev, "instance_id", None) == self.joy.get_instance_id():
                        self._fermer()
        except Exception:
            pygame.event.pump()
        self.precedent = dict(self.etat)
        if self.joy is None:
            self.etat = {}
            return
        try:
            self.axes_bruts = [self.joy.get_axis(i) for i in range(self.joy.get_numaxes())]
            self.boutons_bruts = [self.joy.get_button(i) for i in range(self.joy.get_numbuttons())]
            self.chapeaux = [self.joy.get_hat(i) for i in range(self.joy.get_numhats())]
        except Exception:
            self._fermer()
            return
        self.etat = {nom: (self.boutons_bruts[i] if i < len(self.boutons_bruts) else 0)
                     for nom, i in self.boutons_idx.items()}
        # croix directionnelle exposée comme chapeau par certains pilotes
        if self.chapeaux:
            hx, hy = self.chapeaux[0]
            self.etat["haut"] = self.etat.get("haut", 0) or hy > 0
            self.etat["bas"] = self.etat.get("bas", 0) or hy < 0
            self.etat["gauche"] = self.etat.get("gauche", 0) or hx < 0
            self.etat["droite"] = self.etat.get("droite", 0) or hx > 0
        mx, my = self.deplacement()
        lx, ly = self.regard()
        self.derniere_activite = (any(self.etat.values()) or abs(mx) + abs(my) + abs(lx) + abs(ly) > 0
                                  or self.gachette("r2") > C.SEUIL_GACHETTE)

    def _axe(self, nom):
        i = self.axes_idx.get(nom)
        if i is None or i >= len(self.axes_bruts):
            return 0.0
        return self.axes_bruts[i]

    def deplacement(self):
        """Stick gauche : (x, y) avec y positif vers l'avant."""
        x, y = _zone_morte(self._axe("lx"), self._axe("ly"))
        return x, -y

    def regard(self):
        """Stick droit : (x, y) avec y positif vers le haut."""
        x, y = _zone_morte(self._axe("rx"), self._axe("ry"))
        return x, (y if C.MANETTE_INVERSER_Y else -y)

    def gachette(self, nom):
        """Gâchette analogique ramenée entre 0 et 1 (au repos : -1 sous SDL)."""
        v = self._axe(nom)
        return max(0.0, min(1.0, (v + 1) / 2))

    def maintenu(self, nom):
        return bool(self.etat.get(nom, 0))

    def appui(self, nom):
        """Vrai uniquement à l'image où le bouton est enfoncé."""
        return bool(self.etat.get(nom, 0)) and not self.precedent.get(nom, 0)

    def vibrer(self, basse, haute, duree_ms):
        if self.joy is None or not C.VIBRATIONS:
            return
        try:
            self.joy.rumble(max(0.0, min(1.0, basse)), max(0.0, min(1.0, haute)), int(duree_ms))
        except Exception:
            pass

    def arreter_vibrations(self):
        if self.joy is not None:
            try:
                self.joy.stop_rumble()
            except Exception:
                pass

    def texte_debug(self):
        """Mapping brut des axes et boutons pour le mode debug (F3)."""
        if not self.ok:
            return "pygame indisponible : manette désactivée"
        if self.joy is None:
            return "Aucune manette détectée (branchez-la : détection automatique)"
        lignes = [f"{self.nom}  |  profil : {self.profil_nom}  |  guid : {self.joy.get_guid()}"]
        lignes.append("Axes : " + "  ".join(f"[{i}] {v:+.2f}" for i, v in enumerate(self.axes_bruts)))
        lignes.append("Boutons : " + " ".join(f"[{i}]{'#' if v else '.'}" for i, v in enumerate(self.boutons_bruts)))
        if self.chapeaux:
            lignes.append("Chapeaux : " + " ".join(str(h) for h in self.chapeaux))
        inv_b = {i: n for n, i in self.boutons_idx.items()}
        inv_a = {i: n for n, i in self.axes_idx.items()}
        actifs = [inv_b.get(i, f"?{i}") for i, v in enumerate(self.boutons_bruts) if v]
        lignes.append("Boutons appuyés (selon le profil) : " + (", ".join(actifs) or "aucun"))
        lignes.append("Axes du profil : " + ", ".join(f"{inv_a[i]}={v:+.2f}" for i, v in enumerate(self.axes_bruts) if i in inv_a))
        lignes.append("Modifiez MANETTE_PROFILS dans config.py si un bouton ne correspond pas.")
        return "\n".join(lignes)

    def quitter(self):
        self.arreter_vibrations()
        if self.ok:
            try:
                pygame.joystick.quit()
                pygame.display.quit()
            except Exception:
                pass
