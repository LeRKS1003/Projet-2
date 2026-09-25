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

from panda3d.core import Vec4
from ursina import Entity, Vec3, camera, held_keys, lerp, mouse

import config as C
from generator import CONDUIT, GRILLE
from geometry import MeshBuilder


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
        self.couteaux = 0               # couteaux ramassés (pour crocheter les serrures)
        self.bloque = False             # immobilisé (crochetage en cours)
        self.tete.rotation_y = 0
        self._appliquer_rotation()
        self._creer_lampe()

    def _creer_lampe(self):
        """Lampe torche visible en main droite (dessinée par-dessus le décor)."""
        # petite et proche de l'œil : elle reste à moins de 0,28 m de la caméra et ne traverse
        # donc jamais un mur (le joueur fait 0,3 m de rayon)
        self.lampe_modele = Entity(parent=self.tete, position=(0.1, -0.085, 0.15), scale=0.5)
        mb = MeshBuilder(1.0)
        mb.cylindre((0, 0, -0.14), (0, 0, 0.07), 0.021, (0.13, 0.13, 0.15), segments=10)
        mb.cylindre((0, 0, 0.07), (0, 0, 0.13), 0.026, (0.2, 0.2, 0.22), segments=10, rayon_b=0.036)
        for z in (-0.1, -0.06, -0.02):   # bagues antidérapantes
            mb.cylindre((0, 0, z), (0, 0, z + 0.012), 0.023, (0.07, 0.07, 0.08), segments=10)
        mb.boite((0, 0.022, 0.0), (0.012, 0.008, 0.025), (0.5, 0.1, 0.08))   # interrupteur
        np_ = self.lampe_modele.attachNewNode(mb.construire("lampe"))
        np_.setLightOff(1)
        self.lentille = Entity(parent=self.lampe_modele)
        mb2 = MeshBuilder(1.0)
        mb2.cylindre((0, 0, 0.13), (0, 0, 0.133), 0.032, (1, 1, 1), segments=12)
        self.lentille.attachNewNode(mb2.construire("lentille"))
        self.lentille.setLightOff(1)
        self.lampe_modele.setFogOff(1)

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

    def entrer_conduit(self, grille):
        """Se glisse dans le conduit derrière une grille ouverte (accroupi automatiquement)."""
        gi, gj = grille.grille.case
        dx, dz = grille.grille.vers_sol
        self.position = Vec3(gi + 0.5 - dx * 0.15, 0, gj + 0.5 - dz * 0.15)
        self.lacet = math.degrees(math.atan2(-dx, -dz))
        self.tangage = 0.0
        self.accroupi = True
        self.vitesse = Vec3(0, 0, 0)
        self.audio.jouer("grille", position=self.position, volume=0.3, pitch=0.8)
        self.monde.bruit(self.x, self.z, 3.0)

    def sortir_conduit(self, grille):
        """Ressort du conduit dans la pièce devant la grille, et se relève."""
        fi, fj = grille.grille.case_sol
        dx, dz = grille.grille.vers_sol
        self.position = Vec3(fi + 0.5 + dx * 0.1, 0, fj + 0.5 + dz * 0.1)
        self.lacet = math.degrees(math.atan2(dx, dz))
        self.accroupi_bascule = False
        self.vitesse = Vec3(0, 0, 0)
        self.audio.jouer("grille", position=self.position, volume=0.3, pitch=0.9)
        self.monde.bruit(self.x, self.z, 3.0)

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
        if self.bloque:
            ix = iy = 0.0   # crochetage en cours : on reste sur place
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
        if m.appui(C.MANETTE_LAMPE):
            self.basculer_lampe()
        concentree = bool(self.lampe_allumee and (
            m.gachette(self._nom_r2()) > C.SEUIL_GACHETTE or m.maintenu("r2b") or _touche(C.TOUCHES_LAMPE_POINTEE)))
        self.lampe_concentree = concentree
        if self.lampe_allumee and self.batterie > 0:
            conso = dt / C.LAMPE_DUREE_BATTERIE * (C.LAMPE_MULT_CONCENTREE if concentree else 1.0)
            self.batterie = max(0.0, self.batterie - conso)
        # ---- interaction ----
        if any(m.appui(b) for b in C.MANETTE_INTERAGIR):
            self.appui_interagir = True
        self._animer_lampe(dt, vitesse)

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

    def _animer_lampe(self, dt, vitesse):
        """Position de la lampe en main : baissée au repos, levée et braquée devant quand on la pointe."""
        self.lampe_modele.enabled = self.cache is None
        k = min(1.0, dt * 9)
        if self.lampe_concentree:
            cible, rot = Vec3(0.06, -0.055, 0.17), Vec3(-3, -8, 0)
        else:
            cible, rot = Vec3(0.1, -0.085, 0.15), Vec3(6, -14, 0)
        b = math.sin(self.balancement * 3.3) * (0.003 if vitesse > 0.3 else 0.0)
        self.lampe_modele.position = lerp(self.lampe_modele.position, cible + Vec3(b, abs(b), 0), k)
        self.lampe_modele.rotation = lerp(self.lampe_modele.rotation, rot, k)
        p = min(1.0, self.batterie * 4) if (self.lampe_allumee and self.batterie > 0) else 0.0
        self.lentille.setColorScale(Vec4(0.15 + p, 0.15 + p * 0.95, 0.15 + p * 0.8, 1))

    def recharger(self, quantite):
        self.batterie = min(1.0, self.batterie + quantite)

    # --------------------------------------------------------------
    def chercher_interactif(self, interactifs):
        """Renvoie l'objet interactif visé : à portée, visible, et à peu près devant le joueur.
        L'angle est mesuré à l'horizontale seulement : inutile de viser précisément une grille
        au ras du sol ou une porte, il suffit d'être tourné vers elle."""
        rad = math.radians(self.lacet)
        fx, fz = math.sin(rad), math.cos(rad)
        meilleur, score = None, -1.0
        for obj in interactifs:
            if not obj.actif:
                continue
            dx, dz = obj.position.x - self.x, obj.position.z - self.z
            dh = math.hypot(dx, dz)
            if dh > obj.rayon:
                continue
            dot = 1.0 if dh < 0.35 else (dx * fx + dz * fz) / dh
            if dot < (0.35 if dh < 1.0 else 0.65):
                continue
            if not self.monde.ligne_de_vue(self.x, self.z, obj.position.x, obj.position.z):
                continue
            s = dot - dh * 0.15
            if s > score:
                meilleur, score = obj, s
        self.cible = meilleur
        return meilleur
