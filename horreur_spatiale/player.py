# -*- coding: utf-8 -*-
"""
player.py — Contrôleur FPS : clavier/souris (ZQSD) et manette PS5.

Le joueur ne peut pas se battre : il peut marcher, courir (endurance limitée),
s'accroupir (silencieux, obligatoire dans les conduits), utiliser sa lampe torche
(batterie) et se cacher dans les casiers. Chaque déplacement produit du bruit que
la créature peut entendre.
"""
import math
import random

from ursina import Entity, Vec3, camera, held_keys, lerp, mouse

import config as C
from generator import CONDUIT, GRILLE


def _touche(liste):
    return any(held_keys[k] for k in liste)


class Joueur(Entity):
    def __init__(self, monde, manette, audio, position, lacet=0.0):
        super().__init__(position=position, name="joueur")
        self.monde = monde
        self.manette = manette
        self.audio = audio
        self.tete = Entity(parent=self, y=C.YEUX_DEBOUT)
        camera.parent = self.tete
        camera.position = Vec3(0, 0, 0)
        camera.rotation = Vec3(0, 0, 0)
        self.lacet = lacet
        self.tangage = 0.0
        self.hauteur_yeux = C.YEUX_DEBOUT
        self.accroupi = False
        self.accroupi_bascule = False
        self.sprint_manette = False
        self.court = False
        self.endurance = C.ENDURANCE_MAX
        self.epuise = False
        self.batterie = 1.0
        self.lampe_allumee = True
        self.lampe_concentree = False
        self.niveau_bruit = 0.0         # 0..1 pour l'indicateur du HUD
        self.rayon_bruit = 0.0
        self._timer_bruit = 0.0
        self.distance_pas = 0.0
        self.balancement = 0.0
        self.vitesse = Vec3(0, 0, 0)
        self.cache = None               # casier dans lequel le joueur est caché
        self.secousse = 0.0
        self.cible = None               # interactif visé
        self.dans_conduit = False
        self._haletement = 0.0
        self.appui_interagir = False
        self.utilise_manette = False
        self.tete.rotation_y = 0
        self._appliquer_rotation()

    # --------------------------------------------------------------
    # Évènements clavier (appelés par le jeu)
    # --------------------------------------------------------------
    def touche(self, key):
        if key == C.TOUCHE_INTERAGIR:
            self.appui_interagir = True
            self.utilise_manette = False
        elif key == C.TOUCHE_LAMPE:
            self.basculer_lampe()
            self.utilise_manette = False
        elif not C.ACCROUPI_MAINTENU_CLAVIER and key in ("left control", "right control"):
            self.accroupi_bascule = not self.accroupi_bascule

    def basculer_lampe(self):
        self.lampe_allumee = not self.lampe_allumee
        self.audio.jouer("clic", volume=0.6)

    # --------------------------------------------------------------
    def _appliquer_rotation(self):
        self.rotation_y = self.lacet
        self.tete.rotation_x = self.tangage

    @property
    def hauteur(self):
        return C.HAUTEUR_ACCROUPI if self.accroupi else C.HAUTEUR_DEBOUT

    @property
    def pos_yeux(self):
        return self.tete.world_position

    def se_cacher(self, casier):
        self.cache = casier
        casier.entrouvrir()
        self.lacet = casier.lacet
        self.tangage = 0.0
        self.position = Vec3(casier.position_cachee.x, 0, casier.position_cachee.z)
        self.accroupi = False
        self.audio.jouer("grille", position=self.position, volume=0.35, pitch=1.4)
        self.monde.bruit(self.x, self.z, 4.0)

    def sortir(self):
        c = self.cache
        self.cache = None
        c.entrouvrir()
        self.position = Vec3(c.sortie.x, 0, c.sortie.z)
        self.audio.jouer("grille", position=self.position, volume=0.35, pitch=1.3)
        self.monde.bruit(self.x, self.z, 4.0)

    def secouer(self, force):
        self.secousse = max(self.secousse, force)

    # --------------------------------------------------------------
    def tick(self, dt):
        m = self.manette
        # ---- regard ----
        dyaw = dpitch = 0.0
        if mouse.locked:
            dyaw += mouse.velocity[0] * C.SENSIBILITE_SOURIS
            dpitch -= mouse.velocity[1] * C.SENSIBILITE_SOURIS * (-1 if C.INVERSER_Y else 1)
            if abs(mouse.velocity[0]) + abs(mouse.velocity[1]) > 0:
                self.utilise_manette = False
        rx, ry = m.regard()
        dyaw += rx * C.SENSIBILITE_MANETTE[0] * dt
        dpitch -= ry * C.SENSIBILITE_MANETTE[1] * dt
        if m.derniere_activite:
            self.utilise_manette = True
        self.lacet += dyaw
        self.tangage = max(-85, min(85, self.tangage + dpitch))
        if self.cache is not None:
            # dans un casier : on ne peut que regarder à travers les fentes
            d = (self.lacet - self.cache.lacet + 180) % 360 - 180
            self.lacet = self.cache.lacet + max(-35, min(35, d))
            self.tangage = max(-20, min(25, self.tangage))
            self.position = Vec3(self.cache.position_cachee.x, 0, self.cache.position_cachee.z)
            self.hauteur_yeux = lerp(self.hauteur_yeux, self.cache.position_cachee.y, min(1, dt * 8))
            self.niveau_bruit = 0.0
            self.court = False
            self._finir_tick(dt, 0.0)
            return

        # ---- déplacement ----
        ix = (1 if _touche(C.TOUCHES_DROITE) else 0) - (1 if _touche(C.TOUCHES_GAUCHE) else 0)
        iy = (1 if _touche(C.TOUCHES_AVANT) else 0) - (1 if _touche(C.TOUCHES_ARRIERE) else 0)
        clavier = ix != 0 or iy != 0
        if clavier:
            self.utilise_manette = False
        mx, my = m.deplacement()
        ix += mx
        iy += my
        mag = math.hypot(ix, iy)
        if mag > 1:
            ix, iy = ix / mag, iy / mag
            mag = 1.0

        # accroupi : Ctrl maintenu (ou bascule), R3 / Rond basculent à la manette
        if m.appui("r3") or m.appui("rond"):
            self.accroupi_bascule = not self.accroupi_bascule
            self.sprint_manette = False
        veut_accroupi = self.accroupi_bascule or (C.ACCROUPI_MAINTENU_CLAVIER and _touche(C.TOUCHES_ACCROUPIR))
        plafond = self.monde.hauteur_libre(self.x, self.z, C.RAYON_JOUEUR)
        if veut_accroupi:
            self.accroupi = True
        elif plafond >= C.HAUTEUR_DEBOUT + 0.02:
            self.accroupi = False
        else:
            self.accroupi = True   # plafond trop bas (conduit) : impossible de se relever

        # course : Shift maintenu, ou L3 (bascule tant qu'on avance)
        if m.appui("l3"):
            self.sprint_manette = not self.sprint_manette
            self.accroupi_bascule = False
        if mag < 0.3:
            self.sprint_manette = False
        veut_courir = (_touche(C.TOUCHES_COURIR) or self.sprint_manette) and iy > 0.2 and not self.accroupi
        if self.epuise and self.endurance > C.ENDURANCE_MAX * 0.35:
            self.epuise = False
        self.court = veut_courir and not self.epuise and mag > 0.1
        if self.court:
            self.endurance -= dt
            if self.endurance <= 0:
                self.endurance = 0
                self.epuise = True
                self.court = False
                self.audio.jouer("haletement", volume=0.5)
        else:
            self.endurance = min(C.ENDURANCE_MAX, self.endurance + dt * C.RECUP_ENDURANCE)

        if self.accroupi:
            v = C.VITESSE_ACCROUPI
        elif self.court:
            v = C.VITESSE_COURSE
        else:
            v = C.VITESSE_MARCHE
        rad = math.radians(self.lacet)
        fx, fz = math.sin(rad), math.cos(rad)
        dx = (fx * iy + fz * ix) * v
        dz = (fz * iy - fx * ix) * v
        # petite inertie
        k = min(1.0, dt * 12)
        self.vitesse = Vec3(lerp(self.vitesse.x, dx, k), 0, lerp(self.vitesse.z, dz, k))
        ax, az = self.x, self.z
        nx, nz = self.monde.deplacer(ax, az, self.vitesse.x * dt, self.vitesse.z * dt, C.RAYON_JOUEUR, self.hauteur)
        self.x, self.z = nx, nz
        parcouru = math.hypot(nx - ax, nz - az)
        self.dans_conduit = self.monde.type_case(nx, nz) in (CONDUIT, GRILLE)

        # ---- bruit ----
        vitesse_reelle = parcouru / max(dt, 1e-5)
        if vitesse_reelle < 0.3:
            rayon = 0.0
        elif self.accroupi:
            rayon = C.BRUIT_ACCROUPI
        elif self.court:
            rayon = C.BRUIT_COURSE
        else:
            rayon = C.BRUIT_MARCHE * (0.55 + 0.45 * min(1, mag))
        if self.dans_conduit and rayon > 0:
            rayon *= 1.3   # la tôle des conduits résonne
        self.rayon_bruit = rayon
        self.niveau_bruit = lerp(self.niveau_bruit, min(1.0, rayon / C.BRUIT_COURSE), min(1, dt * 6))
        self._timer_bruit -= dt
        if rayon > 0 and self._timer_bruit <= 0:
            self._timer_bruit = 0.3
            self.monde.bruit(self.x, self.z, rayon)

        # ---- pas ----
        self.distance_pas += parcouru
        foulee = 1.1 if self.accroupi else (2.3 if self.court else 1.8)
        if self.distance_pas > foulee:
            self.distance_pas = 0.0
            vol = 0.12 if self.accroupi else (0.75 if self.court else 0.4)
            nom = "pas_%d" % random.randint(1, 4)
            self.audio.jouer(nom, volume=vol * (1.3 if self.dans_conduit else 1.0),
                             pitch=random.uniform(0.85, 1.1) * (0.8 if self.dans_conduit else 1.0))
        self.balancement += parcouru * (1.0 if not self.court else 1.2)

        # ---- respiration après l'effort ----
        if self.epuise:
            self._haletement -= dt
            if self._haletement <= 0:
                self._haletement = 1.6
                self.audio.jouer("haletement", volume=0.35)

        cible_yeux = C.YEUX_ACCROUPI if self.accroupi else C.YEUX_DEBOUT
        self.hauteur_yeux = lerp(self.hauteur_yeux, cible_yeux, min(1, dt * 10))
        self._finir_tick(dt, vitesse_reelle)

    def _finir_tick(self, dt, vitesse):
        m = self.manette
        # ---- lampe torche ----
        if m.appui("carre"):
            self.basculer_lampe()
        concentree = bool(self.lampe_allumee and (
            m.gachette(self._nom_r2()) > C.SEUIL_GACHETTE or m.maintenu("r2b") or held_keys[C.BOUTON_LAMPE_CONCENTREE]))
        self.lampe_concentree = concentree
        if self.lampe_allumee and self.batterie > 0:
            conso = dt / C.LAMPE_DUREE_BATTERIE * (C.LAMPE_MULT_CONCENTREE if concentree else 1.0)
            self.batterie = max(0.0, self.batterie - conso)
        # ---- interaction ----
        if m.appui("croix"):
            self.appui_interagir = True

        # ---- caméra : balancement de tête et secousses ----
        by = 0.0
        roul = 0.0
        if C.BALANCEMENT_TETE and vitesse > 0.3:
            amp = 0.025 if self.accroupi else (0.07 if self.court else 0.04)
            freq = 3.3
            by = math.sin(self.balancement * freq) * amp
            roul = math.sin(self.balancement * freq * 0.5) * amp * 12
        self.secousse = max(0.0, self.secousse - dt * 1.5)
        s = self.secousse
        self.tete.y = self.hauteur_yeux + by + random.uniform(-s, s) * 0.05
        self._appliquer_rotation()
        self.tete.rotation_z = roul + random.uniform(-s, s) * 3
        self.tete.rotation_x = self.tangage + random.uniform(-s, s) * 2

    def _nom_r2(self):
        return "r2"

    def recharger(self, quantite):
        self.batterie = min(1.0, self.batterie + quantite)

    # --------------------------------------------------------------
    def chercher_interactif(self, interactifs):
        """Renvoie l'objet interactif visé (le plus en face, à portée, visible)."""
        cam = camera.world_position
        fwd = camera.forward
        meilleur, score = None, 0.0
        for obj in interactifs:
            if not obj.actif:
                continue
            d = obj.position - cam
            dist = d.length()
            if dist > obj.rayon or dist < 1e-3:
                continue
            dn = d / dist
            dot = dn.x * fwd.x + dn.y * fwd.y + dn.z * fwd.z
            seuil = 0.55 if dist < 1.2 else 0.8
            if dot < seuil:
                continue
            if not self.monde.ligne_de_vue(self.x, self.z, obj.position.x, obj.position.z):
                continue
            s = dot - dist * 0.05
            if s > score:
                meilleur, score = obj, s
        self.cible = meilleur
        return meilleur
