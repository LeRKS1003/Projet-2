# -*- coding: utf-8 -*-
"""
lighting.py — Éclairage : lumière ambiante, brouillard, lampe torche, néons qui
clignotent, alarmes rouges, et changement d'ambiance quand le courant revient.

Optimisation : le vaisseau contient des centaines de sources « logiques », mais seules
les NB_LUMIERES_ACTIVES plus proches du joueur sont réellement rendues par un
petit pool de PointLight Panda3D réaffectées en continu (pas de recompilation de shader).
"""
import math
import random

from panda3d.core import (AmbientLight, PointLight, Spotlight, PerspectiveLens, Vec3 as PVec3, Vec4)
from ursina import Entity, Vec3, application, camera, color, lerp, scene

import config as C


class SourceLumiere:
    """Source lumineuse logique (néon, lampe de secours, alarme, réacteur, console...)."""

    def __init__(self, position, couleur, rayon=8.0, genre="neon", couleur_courant=None,
                 defectueuse=False, fixtures=None):
        self.position = Vec3(*position)
        self.couleur = couleur
        self.couleur_courant = couleur_courant or couleur
        self.rayon = rayon
        self.genre = genre
        self.defectueuse = defectueuse
        self.fixtures = fixtures or []
        self.intensite = 0.0
        self.couleur_actuelle = couleur
        self._affichee = -1.0
        self._etat = 1.0
        self._prochain = random.uniform(0, 4)
        self._rafale = 0
        self.phase = random.uniform(0, 6.28)

    def _clignoter(self, t, rng, frequent):
        """Clignotement irrégulier : longues pauses puis rafales de micro-coupures."""
        if t >= self._prochain:
            if self._rafale > 0:
                self._rafale -= 1
                self._etat = rng.choice((0.0, 0.05, 0.4, 1.0, 0.0))
                self._prochain = t + rng.uniform(0.03, 0.14)
            else:
                self._etat = 1.0
                self._rafale = rng.randint(3, 12)
                self._prochain = t + (rng.uniform(0.6, 3.0) if frequent else rng.uniform(2.5, 9.0))
        return self._etat

    def calculer(self, t, courant, rng):
        g = self.genre
        self.couleur_actuelle = self.couleur_courant if courant else self.couleur
        if g == "neon":
            if courant:
                v = self._clignoter(t, rng, True) if self.defectueuse else 1.0
            else:
                # sans courant : seuls quelques néons défectueux crachent des étincelles
                v = self._clignoter(t, rng, False) * 0.45 if self.defectueuse else 0.0
                if v > 0.2 and self._etat == 1.0:
                    v = 0.0 if (t * 7 + self.phase) % 3 > 0.4 else v
        elif g == "secours":
            v = (0.3 if courant else 0.6) * (0.85 + 0.15 * math.sin(t * 1.3 + self.phase))
        elif g == "alarme":
            v = 0.0 if courant else max(0.0, math.sin(t * 3.2 + self.phase)) ** 3
        elif g == "reacteur":
            v = (1.0 + 0.15 * math.sin(t * 2.2)) if courant else 0.22 + 0.05 * math.sin(t * 0.7)
        elif g == "console":
            v = 0.75 if courant else 0.14
            if self.defectueuse:
                v *= self._clignoter(t, rng, True)
        else:  # "navette" et autres : alimentation autonome
            v = 0.6 + 0.05 * math.sin(t * 1.7 + self.phase)
        self.intensite = v
        return v

    def maj_fixtures(self):
        """Met à jour la couleur émissive des tubes/écrans associés."""
        if abs(self.intensite - self._affichee) < 0.03:
            return
        self._affichee = self.intensite
        k = 0.12 + self.intensite * 1.1
        r, g, b = self.couleur_actuelle
        c = Vec4(min(1, r * k), min(1, g * k), min(1, b * k), 1)
        for f in self.fixtures:
            # colorScale sur le nœud lui-même : fonctionne aussi pour les meshes fusionnés sans « model »
            f.setColorScale(c)


class LampeTorche:
    """Projecteur attaché à la caméra, avec un léger retard pour un effet de balancement."""

    def __init__(self):
        self.noeud = Spotlight("lampe_torche")
        self.lentille = PerspectiveLens()
        self.lentille.setFov(C.LAMPE_FOV)
        self.lentille.setNearFar(0.1, 40)
        self.noeud.setLens(self.lentille)
        self.noeud.setExponent(C.LAMPE_EXPOSANT)
        self.noeud.setAttenuation(PVec3(1.0, 0.04, 0.012))
        self.pivot = Entity(parent=scene, name="pivot_lampe")
        self.np = self.pivot.attachNewNode(self.noeud)
        self.np.setPos(0.18, -0.2, 0.0)
        self.allumee = True
        self.concentree = False
        self.fov = C.LAMPE_FOV
        self.puissance = 0.0
        self._scintille = 0.0
        _rendu().setLight(self.np)

    def maj(self, dt, allumee, concentree, batterie):
        self.allumee = allumee and batterie > 0
        self.concentree = concentree
        # suit la caméra avec un léger retard
        self.pivot.world_position = camera.world_position
        cible = camera.world_rotation
        cur = self.pivot.world_rotation
        k = min(1.0, dt * 14)
        self.pivot.world_rotation = Vec3(
            cur.x + _angle(cible.x - cur.x) * k,
            cur.y + _angle(cible.y - cur.y) * k,
            cible.z,
        )
        fov_cible = C.LAMPE_FOV_CONCENTREE if concentree else C.LAMPE_FOV
        self.fov = lerp(self.fov, fov_cible, min(1, dt * 8))
        self.lentille.setFov(self.fov)
        # l'exposant adoucit le bord du faisceau (plus il est grand, plus le cône est resserré)
        self.noeud.setExponent(C.LAMPE_EXPOSANT_CONCENTREE if concentree else C.LAMPE_EXPOSANT)
        p = 0.0
        if self.allumee:
            p = C.LAMPE_PUISSANCE_CONCENTREE if concentree else C.LAMPE_PUISSANCE
            if batterie < 0.2:
                p *= 0.4 + batterie * 3
            if batterie < 0.15:
                # batterie faible : la lampe vacille
                self._scintille -= dt
                if self._scintille <= 0:
                    self._scintille = random.uniform(0.05, 0.9)
                if self._scintille < 0.08:
                    p *= random.uniform(0.0, 0.4)
        self.puissance = lerp(self.puissance, p, min(1, dt * 20))
        v = self.puissance
        self.noeud.setColor(Vec4(v * 1.0, v * 0.95, v * 0.85, 1))

    def detruire(self):
        _rendu().clearLight(self.np)
        self.np.removeNode()


def _rendu():
    """Nœud racine de rendu de Panda3D (parent de la scène Ursina)."""
    return application.base.render


def _angle(a):
    return (a + 180) % 360 - 180


class Eclairage:
    """Gestionnaire global de l'éclairage."""

    def __init__(self):
        self.rng = random.Random(3)
        self.sources = []
        self.courant = False
        self.t = 0.0
        self._selection_timer = 0.0
        self._assignations = [None] * C.NB_LUMIERES_ACTIVES
        # pool de lumières ponctuelles
        self.pool = []
        for k in range(C.NB_LUMIERES_ACTIVES):
            pl = PointLight(f"lumiere_{k}")
            pl.setColor(Vec4(0, 0, 0, 1))
            np_ = _rendu().attachNewNode(pl)
            np_.setPos(0, -1000, 0)
            _rendu().setLight(np_)
            self.pool.append((pl, np_))
        # lumière ambiante
        self.ambiante = AmbientLight("ambiante")
        self.ambiante_np = _rendu().attachNewNode(self.ambiante)
        _rendu().setLight(self.ambiante_np)
        self.ambiante_val = list(C.AMBIANTE_SANS_COURANT)
        self.brouillard = C.BROUILLARD_SANS_COURANT
        self.lampe = LampeTorche()
        self.flash = 0.0
        self._appliquer_ambiance()
        scene.fog_color = color.rgb(*C.COULEUR_BROUILLARD)

    def ajouter(self, source):
        self.sources.append(source)
        return source

    def vider(self):
        self.sources = []
        self._assignations = [None] * C.NB_LUMIERES_ACTIVES
        for pl, np_ in self.pool:
            pl.setColor(Vec4(0, 0, 0, 1))
        self.courant = False
        self.ambiante_val = list(C.AMBIANTE_SANS_COURANT)
        self.brouillard = C.BROUILLARD_SANS_COURANT
        self._appliquer_ambiance()

    def retablir_courant(self):
        self.courant = True
        self.flash = 1.0

    def _appliquer_ambiance(self):
        a = self.ambiante_val
        f = self.flash
        self.ambiante.setColor(Vec4(a[0] + f * 0.5, a[1] + f * 0.5, a[2] + f * 0.55, 1))
        scene.fog_density = self.brouillard

    def maj(self, dt, pos_joueur, lampe_allumee, lampe_concentree, batterie):
        self.t += dt
        # transition douce de l'ambiance
        cible_a = C.AMBIANTE_AVEC_COURANT if self.courant else C.AMBIANTE_SANS_COURANT
        cible_b = C.BROUILLARD_AVEC_COURANT if self.courant else C.BROUILLARD_SANS_COURANT
        k = min(1, dt * 0.6)
        self.ambiante_val = [lerp(a, b, k) for a, b in zip(self.ambiante_val, cible_a)]
        self.brouillard = lerp(self.brouillard, cible_b, k)
        self.flash = max(0.0, self.flash - dt * 1.5)
        self._appliquer_ambiance()
        self.lampe.maj(dt, lampe_allumee, lampe_concentree, batterie)

        # calcule l'intensité des sources proches (les lointaines sont ignorées)
        proches = []
        px, pz = pos_joueur.x, pos_joueur.z
        for s in self.sources:
            d2 = (s.position.x - px) ** 2 + (s.position.z - pz) ** 2
            if d2 < 45 * 45:
                s.calculer(self.t, self.courant, self.rng)
                s.maj_fixtures()
                if s.intensite > 0.02 or s.defectueuse:
                    proches.append((d2 / max(0.3, s.rayon / 8.0), s))

        # sélection des sources rendues (toutes les 0.15 s)
        self._selection_timer -= dt
        if self._selection_timer <= 0:
            self._selection_timer = 0.15
            proches.sort(key=lambda e: e[0])
            choisies = [s for _, s in proches[:C.NB_LUMIERES_ACTIVES]]
            nouvelles = [s if s in choisies else None for s in self._assignations]
            for s in choisies:
                if s not in nouvelles:
                    nouvelles[nouvelles.index(None)] = s
            self._assignations = nouvelles

        for (pl, np_), s in zip(self.pool, self._assignations):
            if s is None:
                pl.setColor(Vec4(0, 0, 0, 1))
                continue
            np_.setPos(s.position)
            v = s.intensite
            r, g, b = s.couleur_actuelle
            pl.setColor(Vec4(r * v, g * v, b * v, 1))
            q = 9.0 / (s.rayon * s.rayon)
            pl.setAttenuation(PVec3(1.0, 0.0, q))

    def detruire(self):
        for pl, np_ in self.pool:
            _rendu().clearLight(np_)
            np_.removeNode()
        _rendu().clearLight(self.ambiante_np)
        self.lampe.detruire()
