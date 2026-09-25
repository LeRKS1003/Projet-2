# -*- coding: utf-8 -*-
"""
world.py — Construction 3D du vaisseau à partir de la grille, portes coulissantes,
grilles d'aération, collisions, ligne de vue et culling par distance.

La géométrie statique est fusionnée par blocs (chunks) de TAILLE_CHUNK cases :
un seul nœud par matériau et par bloc, ce qui garde un nombre d'appels de rendu faible.
Les collisions n'utilisent pas le moteur physique : elles sont calculées sur la grille
(beaucoup plus rapide et parfaitement fiable pour des couloirs étroits).
"""
import math
import random

import numpy as np
from panda3d.core import TransparencyAttrib, DirectionalLight as PandaDirectionalLight, Vec4
from ursina import Entity, Vec3, color, destroy

import config as C
from generator import VIDE, MUR, SOL, PORTE, CONDUIT, GRILLE, DIRS, DIRS8, connectes
from geometry import MeshBuilder, Textures

TEINTES = {
    "machines": (0.78, 0.68, 0.58),
    "hangar": (0.72, 0.72, 0.68),
    "commandement": (0.6, 0.67, 0.8),
    "infirmerie": (0.92, 0.94, 0.94),
    "salle_a_manger": (0.82, 0.76, 0.64),
    "chambre": (0.74, 0.7, 0.64),
    "stockage": (0.6, 0.6, 0.56),
    "couloir": (0.6, 0.63, 0.66),
}

# Types de case praticables selon la case où se trouve le centre de l'entité
PRATICABLE = {
    SOL: (SOL, PORTE, GRILLE),
    PORTE: (SOL, PORTE, GRILLE),
    CONDUIT: (CONDUIT, GRILLE),
    GRILLE: (SOL, CONDUIT, GRILLE),
}

_textures = None


def textures():
    """Textures procédurales partagées (générées au premier appel)."""
    global _textures
    if _textures is None:
        _textures = Textures()
    return _textures


class Interactif:
    """Objet avec lequel le joueur peut interagir (E / Croix)."""

    def __init__(self, position, genre, texte, rayon=None, donnees=None, actif=True):
        self.position = Vec3(*position)
        self.genre = genre
        self.texte = texte
        self.rayon = rayon or C.DISTANCE_INTERACTION
        self.donnees = donnees
        self.actif = actif


class PorteCoulissante(Entity):
    """Porte à deux battants qui s'ouvre automatiquement à l'approche."""

    def __init__(self, monde, porte, **kw):
        super().__init__(parent=monde.racine, **kw)
        self.monde = monde
        self.porte = porte
        cx, cz = porte.centre
        self.position = Vec3(cx, 0, cz)
        self.ouverture = 0.0
        self.etait_ouverte = False
        self.axe = Vec3(1, 0, 0) if porte.axe == "x" else Vec3(0, 0, 1)
        h = C.HAUTEUR_PORTE
        tex = textures().get("mur")
        taille = Vec3(1.0, h, 0.16) if porte.axe == "x" else Vec3(0.16, h, 1.0)
        self.battants = []
        for s in (-1, 1):
            b = Entity(parent=self, model="cube", scale=taille, color=color.rgb(0.42, 0.44, 0.47))
            b.setTexture(tex, 1)
            # bande jaune et noire au milieu du battant
            Entity(parent=b, model="cube", scale=(1.02, 0.07, 1.1), y=-0.1,
                           color=color.rgb(0.55, 0.45, 0.08))
            b.cote = s
            self.battants.append(b)
        # voyants au-dessus de la porte, des deux côtés
        n = porte.normale
        self.voyants = []
        for s in (-1, 1):
            v = Entity(parent=self, model="cube", scale=(0.25, 0.1, 0.05) if porte.axe == "x" else (0.05, 0.1, 0.25),
                       position=(n[0] * 0.55 * s, h + 0.18, n[1] * 0.55 * s), unlit=True)
            self.voyants.append(v)
        self._placer()
        self._maj_voyants()

    def _placer(self):
        # battants : fermés au centre, ouverts ils glissent dans le mur voisin
        for b in self.battants:
            decal = (0.5 + self.ouverture * 0.95) * b.cote
            b.position = self.axe * decal + Vec3(0, C.HAUTEUR_PORTE / 2, 0)

    def _maj_voyants(self):
        v = self.porte.verrou
        if v is None:
            c = color.rgb(0.1, 0.9, 0.3)
        elif v == "courant":
            c = color.rgb(0.9, 0.5, 0.05)
        elif v == "crochet":
            c = color.rgb(0.95, 0.85, 0.1)
        else:
            c = color.rgb(0.95, 0.08, 0.05)
        for voy in self.voyants:
            voy.color = c

    def deverrouiller(self):
        self.porte.verrou = None
        self._maj_voyants()
        for obj in getattr(self, "interactifs", ()):
            obj.actif = False

    @property
    def ouverte(self):
        return self.ouverture > 0.8

    def tick(self, dt, positions):
        cx, cz = self.porte.centre
        proche = any((p[0] - cx) ** 2 + (p[1] - cz) ** 2 < 2.6 ** 2 for p in positions)
        cible = 1.0 if (proche and self.porte.verrou is None) else 0.0
        if cible != self.ouverture:
            if cible > 0 and not self.etait_ouverte:
                self.monde.son("porte", Vec3(cx, 1.2, cz))
                self.monde.bruit(cx, cz, 6.0)
            self.etait_ouverte = cible > 0
            vitesse = 2.4 * dt
            self.ouverture = min(cible, self.ouverture + vitesse) if cible > self.ouverture else max(cible, self.ouverture - vitesse)
            self._placer()


class GrilleAeration(Entity):
    """Grille d'accès à un conduit : le joueur l'ouvre (E), la créature l'arrache."""

    def __init__(self, monde, grille, **kw):
        super().__init__(parent=monde.racine, **kw)
        self.monde = monde
        self.grille = grille
        gi, gj = grille.case
        dx, dz = grille.vers_sol
        # position : sur la frontière entre la grille et la pièce, charnière en haut
        self.position = Vec3(gi + 0.5 + dx * 0.5, C.HAUTEUR_CONDUIT, gj + 0.5 + dz * 0.5)
        self.ouverte = False
        self.angle = 0.0
        self.rotation_y = {(1, 0): -90, (-1, 0): 90, (0, 1): 180, (0, -1): 0}[(dx, dz)]
        self.panneau = Entity(parent=self)
        b = MeshBuilder(echelle_uv=1.0)
        col = (0.5, 0.52, 0.55)
        # cadre
        b.boite((0, -0.05, 0.0), (0.98, 0.08, 0.06), col)
        b.boite((0, -0.95, 0.0), (0.98, 0.08, 0.06), col)
        b.boite((-0.47, -0.5, 0.0), (0.06, 0.9, 0.06), col)
        b.boite((0.47, -0.5, 0.0), (0.06, 0.9, 0.06), col)
        # lamelles
        for k in range(7):
            b.boite((0, -0.15 - k * 0.11, 0.0), (0.9, 0.035, 0.05), (0.38, 0.4, 0.42), rot=(35, 0, 0))
        np_ = self.panneau.attachNewNode(b.construire("grille"))
        np_.setTexture(textures().get("objet"), 1)

    def ouvrir(self, par_creature=False):
        if self.ouverte:
            return
        self.ouverte = True
        if hasattr(self, "interactif"):
            self.interactif.texte = "Entrer dans le conduit"
        self.monde.son("grille", self.world_position)
        self.monde.bruit(self.x, self.z, 9.0 if not par_creature else 4.0)

    def tick(self, dt):
        cible = 80.0 if self.ouverte else 0.0
        if self.angle != cible:
            self.angle = min(cible, self.angle + 220 * dt)
            self.panneau.rotation_x = -self.angle


class Monde:
    """Le vaisseau en 3D : géométrie, entités dynamiques et requêtes spatiales."""

    def __init__(self, vaisseau, audio=None):
        self.vaisseau = vaisseau
        self.pont = vaisseau.pont
        self.audio = audio
        self.rng = random.Random(vaisseau.seed)
        self.racine = Entity(name="vaisseau")
        self.chunks = {}                # (ci, cj) -> Entity
        self.salles_entites = {}        # id salle -> Entity (décor fusionné)
        self.boites = {}                # (i, j) -> liste de boîtes de collision (x0, z0, x1, z1)
        self.nav_bloque = np.zeros(self.pont.type.shape, dtype=bool)
        self.interactifs = []
        self.bruits = []                # (x, z, rayon) émis cette image
        self.culling_timer = 0.0
        self._calculer_toits()
        self._construire_structure()
        self.portes = [PorteCoulissante(self, p) for p in self.pont.portes]
        # serrures mécaniques : un point d'interaction de chaque côté de la porte
        for pe in self.portes:
            pe.interactifs = []
            if pe.porte.verrou == "crochet":
                cx, cz = pe.porte.centre
                nx, nz = pe.porte.normale
                for s in (-1, 1):
                    obj = Interactif((cx + nx * 0.75 * s, 1.1, cz + nz * 0.75 * s), "serrure",
                                     "Crocheter la serrure (couteau)", rayon=2.0, donnees=pe)
                    pe.interactifs.append(obj)
                    self.interactifs.append(obj)
        self.grilles = {g.id: GrilleAeration(self, g) for g in self.pont.grilles}
        for g in self.grilles.values():
            dx, dz = g.grille.vers_sol
            g.interactif = Interactif(g.world_position + Vec3(dx * 0.15, -0.5, dz * 0.15), "grille",
                                      "Ouvrir la grille et entrer dans le conduit", rayon=2.0, donnees=g)
            self.interactifs.append(g.interactif)

    # ------------------------------------------------------------------
    # Construction de la géométrie
    # ------------------------------------------------------------------
    def _calculer_toits(self):
        """Hauteur du toit extérieur de chaque case (murs = hauteur max des sols voisins)."""
        p = self.pont
        W, H = p.largeur, p.profondeur
        sol = np.isin(p.type, (SOL,))
        hs = np.where(sol, p.hauteur, 0.0)
        maxi = hs.copy()
        for dx, dz in DIRS8:
            dec = np.zeros_like(hs)
            xs0, xs1 = max(0, dx), W + min(0, dx)
            zs0, zs1 = max(0, dz), H + min(0, dz)
            dec[xs0 - dx:xs1 - dx, zs0 - dz:zs1 - dz] = hs[xs0:xs1, zs0:zs1]
            maxi = np.maximum(maxi, dec)
        toit = np.where(sol, p.hauteur, np.maximum(maxi, p.hauteur))
        toit = np.where(p.type == VIDE, 0.0, toit)
        self.toit = toit + 0.35

    def _teinte(self, i, j):
        sid = int(self.pont.salle[i, j])
        t = self.pont.salles[sid].type if sid >= 0 else "couloir"
        base = TEINTES[t]
        v = 0.9 + ((i * 73856093 ^ j * 19349663) % 1000) / 1000 * 0.2
        return (base[0] * v, base[1] * v, base[2] * v, 1.0)

    def _builders(self, cle):
        if cle not in self._b:
            self._b[cle] = {
                "sol": MeshBuilder(0.5), "mur": MeshBuilder(0.5), "plafond": MeshBuilder(0.5),
                "conduit": MeshBuilder(1.0), "vitre": MeshBuilder(1.0),
            }
        return self._b[cle]

    @staticmethod
    def _arete(i, j, d):
        """Frontière de la case (i, j) dans la direction d : point A, vecteur r (vue de l'intérieur)."""
        dx, dz = d
        r = (dz, -dx)
        mx, mz = i + 0.5 + dx * 0.5, j + 0.5 + dz * 0.5
        return (mx - r[0] * 0.5, mz - r[1] * 0.5), r

    def _mur_seg(self, b, i, j, d, u0, u1, y0, y1, col):
        if y1 - y0 < 1e-4 or u1 - u0 < 1e-4:
            return
        (ax, az), r = self._arete(i, j, d)
        b.mur(ax + r[0] * u0, az + r[1] * u0, ax + r[0] * u1, az + r[1] * u1, y0, y1, col)

    def _mur_fenetre(self, b, bv, i, j, d, h, style, col, bas=0.0, revers=True):
        """Mur percé d'une fenêtre (hublot ou baie vitrée) avec embrasure et vitre."""
        allege, linteau, marge = style
        linteau = min(linteau, h - 0.05)
        self._mur_seg(b, i, j, d, 0, 1, bas, allege, col)
        self._mur_seg(b, i, j, d, 0, 1, linteau, h, col)
        self._mur_seg(b, i, j, d, 0, marge, allege, linteau, col)
        self._mur_seg(b, i, j, d, 1 - marge, 1, allege, linteau, col)
        if not revers:
            return
        (ax, az), r = self._arete(i, j, d)
        dx, dz = d
        cadre = (col[0] * 0.55, col[1] * 0.55, col[2] * 0.6, 1.0)

        def P(u, prof, y):
            return (ax + r[0] * u + dx * prof, y, az + r[1] * u + dz * prof)

        u0, u1 = marge, 1 - marge
        b.quad_auto(P(u0, 0, allege), P(u1, 0, allege), P(u1, 1, allege), P(u0, 1, allege), (0, 1, 0), cadre)
        b.quad_auto(P(u0, 0, linteau), P(u1, 0, linteau), P(u1, 1, linteau), P(u0, 1, linteau), (0, -1, 0), cadre)
        b.quad_auto(P(u0, 0, allege), P(u0, 1, allege), P(u0, 1, linteau), P(u0, 0, linteau), (r[0], 0, r[1]), cadre)
        b.quad_auto(P(u1, 0, allege), P(u1, 1, allege), P(u1, 1, linteau), P(u1, 0, linteau), (-r[0], 0, -r[1]), cadre)
        # vitre (double face) au milieu de l'épaisseur du mur
        verre = (0.55, 0.75, 0.9, 0.1)
        pts = (P(u0, 0.5, allege), P(u1, 0.5, allege), P(u1, 0.5, linteau), P(u0, 0.5, linteau))
        bv.quad_auto(*pts, (-dx, 0, -dz), verre)
        bv.quad_auto(*pts, (dx, 0, dz), verre)

    def _construire_structure(self):
        p = self.pont
        W, H = p.largeur, p.profondeur
        CH = C.TAILLE_CHUNK
        self._b = {}
        coque = MeshBuilder(0.25)
        coque_vitre = MeshBuilder(1.0)
        col_coque = (0.42, 0.43, 0.46, 1.0)
        for i in range(W):
            for j in range(H):
                t = int(p.type[i, j])
                if t == VIDE:
                    continue
                # --- extérieur : coque, toits et marches de toit (jamais désactivés) ---
                toit = float(self.toit[i, j])
                coque.sol(i, j, i + 1, j + 1, toit, col_coque)
                for d in DIRS:
                    ni, nj = i + d[0], j + d[1]
                    nt = p.t(ni, nj)
                    if nt == VIDE:
                        # face extérieure vue depuis la case vide voisine
                        cle = (i, j, d[0], d[1])
                        style = p.fenetres.get(cle)
                        od = (-d[0], -d[1])
                        if style is not None:
                            self._mur_fenetre(coque, coque_vitre, ni, nj, od, toit, style, col_coque, bas=-0.8, revers=False)
                        else:
                            self._mur_seg(coque, ni, nj, od, 0, 1, -0.8, toit, col_coque)
                    elif p.dans(ni, nj) and self.toit[ni, nj] < toit:
                        self._mur_seg(coque, ni, nj, (-d[0], -d[1]), 0, 1, float(self.toit[ni, nj]), toit, col_coque)
                if t == MUR:
                    continue
                # --- intérieur : sol, plafond, murs ---
                b = self._builders((i // CH, j // CH))
                h = float(p.hauteur[i, j])
                col = self._teinte(i, j)
                reseau = t in (CONDUIT, GRILLE)
                bs = b["conduit"] if reseau else b["sol"]
                bp = b["conduit"] if reseau else b["plafond"]
                bm = b["conduit"] if reseau else b["mur"]
                colc = (0.5, 0.5, 0.52, 1.0) if reseau else col
                bs.sol(i, j, i + 1, j + 1, 0.0, colc)
                bp.sol(i, j, i + 1, j + 1, h, colc if reseau else (col[0] * 0.8, col[1] * 0.8, col[2] * 0.8, 1), plafond=True)
                for d in DIRS:
                    ni, nj = i + d[0], j + d[1]
                    nt = p.t(ni, nj)
                    if connectes(t, nt):
                        hn = float(p.hauteur[ni, nj])
                        if hn < h:
                            # marche de plafond (linteau de porte, entrée de conduit...)
                            self._mur_seg(bm, i, j, d, 0, 1, hn, h, colc)
                        continue
                    style = p.fenetres.get((ni, nj, d[0], d[1])) if t == SOL else None
                    if style is not None:
                        self._mur_fenetre(bm, b["vitre"], i, j, d, h, style, col)
                    else:
                        self._mur_seg(bm, i, j, d, 0, 1, 0.0, h, colc)
                    # plinthe sombre en bas des murs des pièces
                    if not reseau and t == SOL:
                        self._mur_plinthe(bm, i, j, d, col)

        tex = textures()
        for (ci, cj), builders in self._b.items():
            e = Entity(parent=self.racine, name=f"chunk_{ci}_{cj}")
            e.centre = Vec3((ci + 0.5) * CH, 0, (cj + 0.5) * CH)
            for nom, bld in builders.items():
                if bld.vide():
                    continue
                np_ = e.attachNewNode(bld.construire(nom))
                if nom == "vitre":
                    self._style_vitre(np_)
                else:
                    np_.setTexture(tex.get(nom), 1)
            self.chunks[(ci, cj)] = e
        self.exterieur = Entity(parent=self.racine, name="coque")
        np_ = self.exterieur.attachNewNode(coque.construire("coque"))
        np_.setTexture(tex.get("coque"), 1)
        if not coque_vitre.vide():
            self._style_vitre(self.exterieur.attachNewNode(coque_vitre.construire("vitre_ext")))
        # lumière stellaire très faible uniquement sur la coque extérieure
        soleil = PandaDirectionalLight("etoile")
        soleil.setColor(Vec4(0.16, 0.17, 0.22, 1))
        snp = self.exterieur.attachNewNode(soleil)
        snp.setHpr(35, -40, 0)
        self.exterieur.setLight(snp)
        del self._b

    def _mur_plinthe(self, b, i, j, d, col):
        """Petite bande sombre au pied du mur (légèrement décollée pour éviter le z-fighting)."""
        (ax, az), r = self._arete(i, j, d)
        dx, dz = d
        o = 0.012
        sombre = (col[0] * 0.35, col[1] * 0.35, col[2] * 0.35, 1)
        b.mur(ax - dx * o, az - dz * o, ax + r[0] - dx * o, az + r[1] - dz * o, 0.0, 0.14, sombre)

    @staticmethod
    def _style_vitre(np_):
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setDepthWrite(False)
        np_.setTwoSided(True)
        np_.setLightOff(1)
        np_.setBin("transparent", 10)

    def ajouter_decor_salle(self, sid, entite):
        self.salles_entites[sid] = entite

    # ------------------------------------------------------------------
    # Collisions
    # ------------------------------------------------------------------
    def ajouter_boite(self, x0, z0, x1, z1, bloque_nav=True):
        """Boîte de collision d'un objet du décor (axe-alignée, vue de dessus)."""
        for i in range(int(math.floor(x0)), int(math.floor(x1)) + 1):
            for j in range(int(math.floor(z0)), int(math.floor(z1)) + 1):
                self.boites.setdefault((i, j), []).append((x0, z0, x1, z1))
                if bloque_nav and x0 <= i + 0.5 <= x1 and z0 <= j + 0.5 <= z1:
                    self.nav_bloque[i, j] = True

    def type_case(self, x, z):
        return self.pont.t(int(math.floor(x)), int(math.floor(z)))

    def case_bloquee(self, i, j, type_centre, hauteur):
        p = self.pont
        t = p.t(i, j)
        if t not in PRATICABLE.get(type_centre, (SOL, PORTE, GRILLE)):
            return True
        if t == PORTE and not self.portes[p.porte_id[i, j]].ouverte:
            return True
        if t == GRILLE and not self.grilles[int(p.grille_id[i, j])].ouverte:
            return True
        return p.hauteur[i, j] < hauteur

    def _collision(self, x, z, r, type_centre, hauteur, avec_boites):
        for i in range(int(math.floor(x - r)), int(math.floor(x + r)) + 1):
            for j in range(int(math.floor(z - r)), int(math.floor(z + r)) + 1):
                if self.case_bloquee(i, j, type_centre, hauteur):
                    return (i, j, i + 1, j + 1)
                if avec_boites:
                    for bx in self.boites.get((i, j), ()):
                        if x + r > bx[0] and x - r < bx[2] and z + r > bx[1] and z - r < bx[3]:
                            return bx
        return None

    def deplacer(self, x, z, dx, dz, r, hauteur, avec_boites=True):
        """Déplace une boîte de demi-taille r en glissant le long des murs (axes séparés)."""
        tc = self.type_case(x, z)
        if tc in (VIDE, MUR):
            tc = SOL
        # sous-pas pour ne jamais traverser un mur à grande vitesse
        pas = max(1, int(max(abs(dx), abs(dz)) / (r * 0.9)) + 1)
        sx, sz = dx / pas, dz / pas
        for _ in range(pas):
            if sx:
                nx = x + sx
                for _k in range(4):
                    b = self._collision(nx, z, r, tc, hauteur, avec_boites)
                    if b is None:
                        break
                    nx = (b[0] - r - 1e-4) if sx > 0 else (b[2] + r + 1e-4)
                    if (sx > 0 and nx < x) or (sx < 0 and nx > x):
                        nx = x
                        break
                x = nx
            if sz:
                nz = z + sz
                for _k in range(4):
                    b = self._collision(x, nz, r, tc, hauteur, avec_boites)
                    if b is None:
                        break
                    nz = (b[1] - r - 1e-4) if sz > 0 else (b[3] + r + 1e-4)
                    if (sz > 0 and nz < z) or (sz < 0 and nz > z):
                        nz = z
                        break
                z = nz
        return x, z

    def hauteur_libre(self, x, z, r):
        """Hauteur sous plafond minimale autour d'un point (pour savoir si on peut se relever)."""
        h = 99.0
        for i in range(int(math.floor(x - r)), int(math.floor(x + r)) + 1):
            for j in range(int(math.floor(z - r)), int(math.floor(z + r)) + 1):
                t = self.pont.t(i, j)
                if t in (SOL, PORTE, CONDUIT, GRILLE):
                    h = min(h, float(self.pont.hauteur[i, j]))
        return h

    # ------------------------------------------------------------------
    # Ligne de vue (parcours de grille Amanatides & Woo)
    # ------------------------------------------------------------------
    def ligne_de_vue(self, x0, z0, x1, z1):
        p = self.pont
        i, j = int(math.floor(x0)), int(math.floor(z0))
        ti, tj = int(math.floor(x1)), int(math.floor(z1))
        dx, dz = x1 - x0, z1 - z0
        si = 1 if dx > 0 else -1
        sj = 1 if dz > 0 else -1
        tdx = abs(1.0 / dx) if dx else 1e9
        tdz = abs(1.0 / dz) if dz else 1e9
        tmx = ((i + (si > 0)) - x0) / dx if dx else 1e9
        tmz = ((j + (sj > 0)) - z0) / dz if dz else 1e9
        t_prec = p.t(i, j)
        for _ in range(200):
            if i == ti and j == tj:
                return True
            if tmx < tmz:
                i += si
                tmx += tdx
            else:
                j += sj
                tmz += tdz
            t = p.t(i, j)
            if not connectes(t_prec, t):
                return False
            if t == PORTE and not self.portes[p.porte_id[i, j]].ouverte:
                return False
            if t == GRILLE and not self.grilles[int(p.grille_id[i, j])].ouverte:
                return False
            t_prec = t
        return False

    # ------------------------------------------------------------------
    # Évènements sonores
    # ------------------------------------------------------------------
    def bruit(self, x, z, rayon):
        self.bruits.append((x, z, rayon))

    def son(self, nom, position, volume=1.0):
        if self.audio:
            self.audio.jouer(nom, position=position, volume=volume)

    # ------------------------------------------------------------------
    # Mise à jour
    # ------------------------------------------------------------------
    def tick(self, dt, pos_joueur, pos_creature=None):
        positions = [(pos_joueur.x, pos_joueur.z)]
        if pos_creature is not None:
            positions.append((pos_creature.x, pos_creature.z))
        for porte in self.portes:
            porte.tick(dt, positions)
        for g in self.grilles.values():
            g.tick(dt)
        self.culling_timer -= dt
        if self.culling_timer <= 0:
            self.culling_timer = C.INTERVALLE_CULLING
            self._culling(pos_joueur)

    def _culling(self, pos):
        """Désactive les blocs et salles trop éloignés (le brouillard les masque de toute façon)."""
        dmax = C.DISTANCE_CULLING
        demi = C.TAILLE_CHUNK * 0.5
        for e in self.chunks.values():
            dx = max(abs(pos.x - e.centre.x) - demi, 0)
            dz = max(abs(pos.z - e.centre.z) - demi, 0)
            e.enabled = dx * dx + dz * dz < dmax * dmax
        for sid, e in self.salles_entites.items():
            e.enabled = self.pont.salles[sid].distance(pos.x, pos.z) < dmax
        for porte in self.portes:
            cx, cz = porte.porte.centre
            porte.enabled = (pos.x - cx) ** 2 + (pos.z - cz) ** 2 < dmax * dmax

    def detruire(self):
        destroy(self.racine)
