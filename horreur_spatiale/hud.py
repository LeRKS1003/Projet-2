# -*- coding: utf-8 -*-
"""
hud.py — Interface minimale et discrète : objectif en haut, batterie de la lampe,
indicateur de bruit, endurance, messages en fondu, invite d'interaction, carte partielle,
écran de debug manette (F3) et écrans de menu, pause, game over et victoire.
"""
import textwrap

import numpy as np
from panda3d.core import SamplerState, Texture as PandaTexture
from ursina import Entity, Text, Texture, camera, color, window

import config as C
from generator import MUR, SOL, CONDUIT, GRILLE
from geometry import Textures

GRIS = color.rgb(0.75, 0.78, 0.8)


def _texture_ursina(tex_panda):
    """Enveloppe une texture Panda3D dans une Texture Ursina (pour les entités d'interface)."""
    t = Texture(tex_panda)
    t._cached_image = None
    return t


class Message:
    def __init__(self, texte, duree):
        self.texte = texte
        self.texte_affiche = textwrap.fill(texte, 70)
        self.duree = duree
        self.t = 0.0


class HUD:
    def __init__(self):
        ui = camera.ui
        self.racine = Entity(parent=ui, name="hud")
        tex = Textures()
        # voiles plein écran
        self.vignette = Entity(parent=ui, model="quad", texture="vignette", scale=(window.aspect_ratio * 1.02, 1.02),
                               color=color.rgba(0, 0, 0, 0.9), z=1)
        self.danger = Entity(parent=ui, model="quad", texture="vignette", scale=(window.aspect_ratio * 1.02, 1.02),
                             color=color.rgba(0.6, 0, 0, 0), z=0.9)
        self.fentes = Entity(parent=ui, model="quad", scale=(window.aspect_ratio * 1.02, 1.02), z=0.8,
                             color=color.rgba(0.02, 0.02, 0.02, 1), enabled=False)
        self.fentes.texture = _texture_ursina(tex.get("fentes"))
        # réticule
        self.reticule = Entity(parent=self.racine, model="circle", scale=0.006, color=color.rgba(1, 1, 1, 0.35))
        # objectif (en haut)
        self.objectif = Text(parent=self.racine, text="", origin=(0, 0), position=(0, 0.45), scale=1.05,
                             color=color.rgba(0.8, 0.85, 0.9, 0.85))
        # invite d'interaction
        self.invite = Text(parent=self.racine, text="", origin=(0, 0), position=(0, -0.08), scale=0.95,
                           color=color.rgba(1, 1, 1, 0.85))
        # messages en fondu
        self.message_txt = Text(parent=self.racine, text="", origin=(0, 0), position=(0, -0.25), scale=1.0,
                                color=color.rgba(0.9, 0.9, 0.85, 0))
        self.messages = []
        # batterie (en bas à gauche)
        ar = window.aspect_ratio
        self.bat_label = Text(parent=self.racine, text="LAMPE", position=(-ar / 2 + 0.04, -0.4), scale=0.7,
                              color=color.rgba(0.8, 0.8, 0.8, 0.6))
        self.bat_segments = []
        for k in range(10):
            e = Entity(parent=self.racine, model="quad", scale=(0.012, 0.022),
                       position=(-ar / 2 + 0.05 + k * 0.016, -0.44), color=GRIS)
            self.bat_segments.append(e)
        # bruit (en bas à droite)
        self.bruit_label = Text(parent=self.racine, text="BRUIT", position=(ar / 2 - 0.13, -0.4), scale=0.7,
                                color=color.rgba(0.8, 0.8, 0.8, 0.6))
        self.bruit_barres = []
        for k in range(6):
            e = Entity(parent=self.racine, model="quad", origin=(0, -0.5), scale=(0.012, 0.01 + k * 0.006),
                       position=(ar / 2 - 0.125 + k * 0.017, -0.455), color=GRIS)
            self.bruit_barres.append(e)
        # endurance (fine barre centrale)
        self.endu_fond = Entity(parent=self.racine, model="quad", scale=(0.2, 0.004), position=(0, -0.46),
                                color=color.rgba(1, 1, 1, 0.1))
        self.endu = Entity(parent=self.racine, model="quad", origin=(-0.5, 0), scale=(0.2, 0.004),
                           position=(-0.1, -0.46), color=color.rgba(0.8, 0.85, 0.9, 0.5))
        # carte
        self.carte = Entity(parent=ui, model="quad", enabled=False, z=0.5)
        self.carte_cadre = Entity(parent=self.carte, model="quad", scale=1.04, z=0.01, color=color.rgba(0, 0, 0, 0.85))
        self.carte_joueur = Entity(parent=self.carte, model="circle", scale=0.02, z=-0.01, color=color.rgb(0.2, 1, 0.4))
        self.carte_obj = Entity(parent=self.carte, model="circle", scale=0.025, z=-0.01, color=color.rgb(1, 0.6, 0.1))
        self.carte_titre = Text(parent=self.carte, text="CARTE (partielle)", origin=(0, 0), y=-0.56, scale=(1.2, 1.2),
                                color=GRIS)
        self.carte_tex = None
        self.vus = None
        # debug
        self.debug = Text(parent=ui, text="", position=(-ar / 2 + 0.02, 0.48), scale=0.75,
                          color=color.rgb(0.5, 1.0, 0.6), enabled=False)
        # écrans
        self.noir = Entity(parent=ui, model="quad", scale=(ar * 1.1, 1.1), color=color.rgba(0, 0, 0, 0), z=-0.5)
        self.titre = Text(parent=ui, text="", origin=(0, 0), y=0.18, scale=4, z=-0.6, color=color.rgb(0.85, 0.85, 0.85))
        self.sous_titre = Text(parent=ui, text="", origin=(0, 0), y=0.06, scale=1.1, z=-0.6,
                               color=color.rgb(0.6, 0.62, 0.65))
        self.options = Text(parent=ui, text="", origin=(0, 0), y=-0.12, scale=1.05, z=-0.6, color=color.rgb(0.8, 0.8, 0.8))
        self.aide = Text(parent=ui, text="", origin=(0, 0), y=-0.38, scale=0.75, z=-0.6,
                         color=color.rgb(0.45, 0.47, 0.5))
        self.alpha_noir = 0.0
        self.cible_noir = 0.0
        self.afficher_jeu(False)

    # --------------------------------------------------------------
    def afficher_jeu(self, visible):
        self.racine.enabled = visible
        self.vignette.enabled = visible
        self.danger.enabled = visible
        if not visible:
            self.fentes.enabled = False
            self.carte.enabled = False

    def ecran(self, titre="", sous_titre="", options="", aide="", noir=0.0):
        self.titre.text = titre
        self.sous_titre.text = textwrap.fill(sous_titre, 80) if sous_titre else ""
        self.options.text = options
        self.aide.text = aide
        self.cible_noir = noir

    def message(self, texte, duree=4.0):
        self.messages = [m for m in self.messages if m.texte != texte]
        self.messages.append(Message(texte, duree))

    def vider_messages(self):
        self.messages = []
        self.message_txt.text = ""

    # --------------------------------------------------------------
    def maj(self, dt, joueur=None, tension=0.0):
        # fondu de l'écran noir
        k = min(1, dt * 2.5)
        self.alpha_noir += (self.cible_noir - self.alpha_noir) * k
        self.noir.color = color.rgba(0, 0, 0, self.alpha_noir)
        # messages
        if self.messages:
            m = self.messages[0]
            m.t += dt
            a = min(1, m.t / 0.4, max(0, (m.duree - m.t) / 0.8))
            if self.message_txt.text != m.texte_affiche:
                self.message_txt.text = m.texte_affiche
            self.message_txt.color = color.rgba(0.9, 0.9, 0.85, a)
            if m.t >= m.duree:
                self.messages.pop(0)
        else:
            self.message_txt.text = ""
        if joueur is None:
            return
        # batterie
        n = int(round(joueur.batterie * 10 + 0.49)) if joueur.batterie > 0 else 0
        for i, s in enumerate(self.bat_segments):
            if i < n:
                c = color.rgb(0.9, 0.25, 0.2) if joueur.batterie < 0.2 else GRIS
                s.color = c if joueur.lampe_allumee else color.rgba(c.r, c.g, c.b, 0.35)
            else:
                s.color = color.rgba(1, 1, 1, 0.08)
        # bruit
        nb = joueur.niveau_bruit * len(self.bruit_barres)
        for i, b in enumerate(self.bruit_barres):
            actif = i < nb - 0.05
            if actif:
                b.color = color.rgb(0.95, 0.3, 0.2) if i >= 4 else (color.rgb(0.95, 0.75, 0.3) if i >= 2 else GRIS)
            else:
                b.color = color.rgba(1, 1, 1, 0.08)
        # endurance
        r = joueur.endurance / C.ENDURANCE_MAX
        self.endu.scale_x = 0.2 * r
        vis = r < 0.999
        self.endu.enabled = vis
        self.endu_fond.enabled = vis
        self.endu.color = color.rgba(0.9, 0.3, 0.2, 0.6) if joueur.epuise else color.rgba(0.8, 0.85, 0.9, 0.5)
        # danger (la créature est proche)
        self.danger.color = color.rgba(0.45, 0, 0, min(0.45, tension * 0.5))
        self.fentes.enabled = joueur.cache is not None

    def invite_texte(self, obj, manette):
        if obj is None:
            self.invite.text = ""
            return
        touche = "[Croix]" if manette else "[E]"
        self.invite.text = f"{touche}  {obj.texte}"

    # --------------------------------------------------------------
    # Carte partielle
    # --------------------------------------------------------------
    def preparer_carte(self, pont):
        self.pont = pont
        W, H = pont.largeur, pont.profondeur
        self.vus = np.zeros((W, H), dtype=bool)
        self.carte_tex = PandaTexture("carte")
        self.carte_tex.setup2dTexture(W, H, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
        self.carte_tex.setMagfilter(SamplerState.FTNearest)
        self.carte_tex.setMinfilter(SamplerState.FTNearest)
        self.carte.texture = _texture_ursina(self.carte_tex)
        self.carte.texture.filtering = None
        h = 0.8
        self.carte.scale = (h * W / H, h)
        self._maj_carte_timer = 0.0

    def reveler(self, x, z, rayon=6):
        if self.vus is None:
            return
        W, H = self.vus.shape
        i, j = int(x), int(z)
        self.vus[max(0, i - rayon):min(W, i + rayon + 1), max(0, j - rayon):min(H, j + rayon + 1)] = True
        sid = self.pont.salle[min(max(i, 0), W - 1), min(max(j, 0), H - 1)]
        if sid >= 0:
            s = self.pont.salles[sid]
            self.vus[s.x - 1:s.x + s.l + 1, s.z - 1:s.z + s.p + 1] = True

    def maj_carte(self, dt, joueur, cible_objectif, force=False):
        if not self.carte.enabled or self.vus is None:
            return
        self._maj_carte_timer -= dt
        p = self.pont
        W, H = p.largeur, p.profondeur
        if self._maj_carte_timer <= 0 or force:
            self._maj_carte_timer = 0.5
            img = np.zeros((W, H, 4), dtype=np.float32)
            t = p.type
            img[t == SOL] = (0.28, 0.31, 0.34, 1)
            img[t == MUR] = (0.65, 0.68, 0.72, 1)
            img[t == CONDUIT] = (0.3, 0.22, 0.12, 1)
            img[t == GRILLE] = (0.6, 0.4, 0.15, 1)
            for porte in p.portes:
                c = (0.2, 0.8, 0.3, 1) if porte.verrou is None else ((0.9, 0.5, 0.1, 1) if porte.verrou == "courant" else (0.9, 0.1, 0.1, 1))
                for (i, j) in porte.cases:
                    img[i, j] = c
            img[~self.vus] = (0, 0, 0, 0)
            # (i, j) -> image : lignes = z inversé
            rgba = np.transpose(img, (1, 0, 2))[::-1]
            octets = (np.flipud(rgba) * 255).astype(np.uint8)
            self.carte_tex.setRamImageAs(octets.tobytes(), "RGBA")
        self.carte_joueur.position = (joueur.x / W - 0.5, joueur.z / H - 0.5, -0.01)
        if cible_objectif is not None and self.vus[int(cible_objectif.x) % W, int(cible_objectif.z) % H]:
            self.carte_obj.enabled = True
            self.carte_obj.position = (cible_objectif.x / W - 0.5, cible_objectif.z / H - 0.5, -0.01)
        else:
            self.carte_obj.enabled = False
