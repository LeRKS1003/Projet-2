# -*- coding: utf-8 -*-
"""
rooms.py — Construction et décoration de chaque type de salle et des couloirs.

Chaque salle est meublée procéduralement (avec de la variété : objets renversés,
chaises au sol, traces de sang et griffures sur les murs). Toute la géométrie
statique d'une salle est fusionnée en un seul mesh (MeshBuilder), les éléments
lumineux (néons, écrans, réacteur) restent des entités séparées pour pouvoir
clignoter. Les objets interactifs (casiers, consoles, piles, journaux, navette)
sont déclarés auprès du Monde.
"""
import math
import random

from ursina import Entity, Vec3, color

import config as C
from generator import SOL, PORTE, MUR, DIRS
from geometry import MeshBuilder
from lighting import SourceLumiere
from world import Interactif, textures

# angle (degrés) d'un objet dont la face avant regarde dans la direction « normale intérieure »
ANGLE_NORMALE = {(1, 0): -90, (-1, 0): 90, (0, 1): 180, (0, -1): 0}

BLANC_NEON = (0.78, 0.88, 1.0)
ORANGE_SECOURS = (1.0, 0.32, 0.08)
ROUGE_ALARME = (1.0, 0.05, 0.03)

JOURNAUX = [
    "JOURNAL — Dr Okafor : « Trois membres d'équipage présentent des lésions "
    "que je ne sais pas expliquer. Quelque chose bouge dans les gaines de ventilation. »",
    "JOURNAL — Chef mécanicien Varga : « Le réacteur s'est coupé tout seul. "
    "Pour le relancer, il faut la console principale au pied du cœur. »",
    "JOURNAL — Cuisine : « Plus personne ne vient manger. On entend gratter "
    "derrière les grilles. N'ouvrez pas les conduits. »",
    "JOURNAL — Capitaine Moreau : « J'ai verrouillé le hangar. Le code de la "
    "navette est dans le terminal de commandement. Que Dieu nous pardonne. »",
    "JOURNAL — Inconnu : « Elle ne voit pas bien dans le noir. Mais elle entend. "
    "Tout. Marchez lentement. Cachez-vous dans les casiers. »",
]


# Contenu possible des casiers : quelques clins d'œil cachés (« easter eggs »)
OEUFS_DE_PAQUES = [
    ("Un chat roux dans une caisse de transport. Sur l'étiquette : « JONES ». "
     "Il vous fixe avec mépris, puis se rendort.", False),
    ("Une casquette délavée : « NOSTROMO — Weyland-Yutani Corp. » "
     "Quelqu'un à bord avait de bonnes références.", False),
    ("Un canard en plastique jaune. Vous appuyez dessus. Il COUINE. Très fort. Beaucoup trop fort.", True),
    ("Un badge d'employé : « Isaac C. — ingénieur système ». Au dos, griffonné : « Viser les membres. »", False),
    ("Un disque étiqueté « PATHOS-II — copie de conscience n°3 ». Vous préférez ne pas y penser.", False),
    ("Une photo de l'équipage souriant devant le vaisseau. Ils étaient onze. Vous en comptez douze.", False),
    ("Un post-it : « Le code de la navette n'est PAS 0000. Signé : la sécurité. »", False),
    ("Une cassette : « Relaxation spatiale, vol. 3 — bruits de vagues ». L'ironie vous échappe.", False),
    ("Un tamagotchi. Mort. Évidemment.", False),
    ("Une boîte de céréales « Choco-Xéno ». La mascotte a beaucoup trop de dents.", False),
    ("Un mot d'enfant : « Papa, reviens vite de l'espace. » Vous rangez le mot avec soin.", False),
    ("Une console portable. Record : 999 999 points. Pseudo du joueur : « CLAUDE ».", False),
]

BRIC_A_BRAC = [
    "Des vêtements sales et une odeur de sueur froide.",
    "Une trousse de toilette renversée. Rien d'utile.",
    "Des bottes magnétiques dépareillées.",
    "Un casier vide, à l'exception de trois longues griffures à l'intérieur de la porte.",
    "Une combinaison déchirée, raide de sang séché.",
    "Des rations périmées depuis quatre ans.",
]


class Cadre:
    """Repère local d'un objet : origine au sol, face avant vers -z local."""

    def __init__(self, cx, cz, angle):
        self.cx, self.cz, self.angle = cx, cz, angle
        self.c = math.cos(math.radians(angle))
        self.s = math.sin(math.radians(angle))

    def p(self, lx, ly, lz):
        return (self.cx + self.c * lx + self.s * lz, ly, self.cz - self.s * lx + self.c * lz)

    def avant(self):
        return (-self.s, -self.c)


class Casier(Entity):
    """Casier métallique dans lequel le joueur peut se cacher."""

    def __init__(self, parent, cadre, rng):
        super().__init__(parent=parent, position=(cadre.cx, 0, cadre.cz), rotation_y=cadre.angle)
        self.cadre = cadre
        teinte = rng.choice(((0.45, 0.5, 0.55), (0.5, 0.45, 0.38), (0.38, 0.45, 0.42)))
        b = MeshBuilder(1.0)
        l, p, h = 0.72, 0.55, 2.0
        b.boite((0, h / 2, 0.02), (l, h, p - 0.04), teinte)
        b.boite((0, h + 0.02, 0), (l + 0.04, 0.04, p), (teinte[0] * 0.7, teinte[1] * 0.7, teinte[2] * 0.7))
        np_ = self.attachNewNode(b.construire("casier"))
        np_.setTexture(textures().get("objet"), 1)
        # porte articulée (charnière à gauche)
        self.charniere = Entity(parent=self, position=(-l / 2, 0, -p / 2))
        bp = MeshBuilder(1.0)
        bp.boite((l / 2, h / 2, -0.015), (l - 0.02, h - 0.04, 0.03), (teinte[0] * 1.1, teinte[1] * 1.1, teinte[2] * 1.1))
        for k in range(6):
            bp.boite((l / 2, 1.35 + k * 0.06, -0.035), (0.4, 0.025, 0.01), (0.05, 0.05, 0.05))
        bp.boite((l - 0.1, 1.0, -0.045), (0.03, 0.18, 0.03), (0.7, 0.7, 0.7))
        npp = self.charniere.attachNewNode(bp.construire("porte_casier"))
        npp.setTexture(textures().get("objet"), 1)
        self.ouverture = 0.0
        self.cible = 0.0
        ax, az = cadre.avant()
        self.position_cachee = Vec3(cadre.cx - ax * 0.02, C.YEUX_DEBOUT - 0.1, cadre.cz - az * 0.02)
        self.sortie = Vec3(cadre.cx + ax * 0.85, 0, cadre.cz + az * 0.85)
        self.lacet = math.degrees(math.atan2(ax, az))
        self.contenu = ("rien", "")    # rempli par decorer()
        self.fouille = False
        self.salle = None
        self.interactif = None

    def entrouvrir(self, duree=0.6):
        self.cible = 1.0
        self._fermer_dans = duree

    def tick(self, dt):
        if self.cible > 0:
            self._fermer_dans -= dt
            if self._fermer_dans <= 0:
                self.cible = 0.0
        if self.ouverture != self.cible:
            v = dt * 4
            self.ouverture = min(self.cible, self.ouverture + v) if self.cible > self.ouverture else max(self.cible, self.ouverture - v)
            self.charniere.rotation_y = 100 * self.ouverture


class Amenageur:
    """Aide à la décoration d'une salle : placement sans chevauchement + mesh fusionné."""

    def __init__(self, monde, eclairage, salle, rng, racine):
        self.monde = monde
        self.pont = monde.pont
        self.eclairage = eclairage
        self.salle = salle
        self.rng = rng
        self.racine = racine
        self.b = MeshBuilder(1.0)
        self.dec = MeshBuilder(1.0)
        self.occupe = set()
        self.reserve = set()
        self.casiers = []
        if salle is not None:
            self._reserver()

    # -- réservations : on garde libres les accès aux portes et aux grilles --
    def _reserver(self):
        s = self.salle
        points = []
        for pid in s.portes:
            p = self.pont.portes[pid]
            for (i, j) in p.cases:
                points.append((i - p.normale[0], j - p.normale[1], 2))
        for gid in s.grilles:
            g = next(g for g in self.pont.grilles if g.id == gid)
            points.append((*g.case_sol, 1))
        for (ci, cj, r) in points:
            for i in range(ci - r, ci + r + 1):
                for j in range(cj - r, cj + r + 1):
                    if s.contient(i, j):
                        self.reserve.add((i, j))

    # -- primitives dans un repère local --
    def boite(self, f, lx, ly, lz, sx, sy, sz, col, rot=(0, 0, 0)):
        self.b.boite(f.p(lx, ly, lz), (sx, sy, sz), col, rot=(rot[0], f.angle + rot[1], rot[2]))

    def cyl(self, f, a, b, r, col, seg=8, rb=None):
        self.b.cylindre(f.p(*a), f.p(*b), r, col, segments=seg, rayon_b=rb)

    def collision(self, f, larg, prof, cx=0.0, cz=0.0, nav=True):
        coins = [f.p(cx + sx * larg / 2, 0, cz + sz * prof / 2) for sx in (-1, 1) for sz in (-1, 1)]
        xs = [c[0] for c in coins]
        zs = [c[2] for c in coins]
        self.monde.ajouter_boite(min(xs), min(zs), max(xs), max(zs), bloque_nav=nav)

    def emissif(self, f, lx, ly, lz, sx, sy, sz, rot_x=0.0, modele="cube"):
        """Élément lumineux (écran, tube) : entité non éclairée dont la couleur varie."""
        pivot = Entity(parent=self.racine, position=f.p(lx, ly, lz), rotation_y=f.angle)
        e = Entity(parent=pivot, model=modele, scale=(sx, sy, sz), rotation_x=rot_x, unlit=True)
        e.setColorScale(0.1, 0.1, 0.1, 1)
        return e

    def lumiere(self, pos, couleur, rayon, genre, fixtures=(), defectueuse=False, couleur_courant=None):
        s = SourceLumiere(pos, couleur, rayon, genre, couleur_courant=couleur_courant,
                          defectueuse=defectueuse, fixtures=list(fixtures))
        self.eclairage.ajouter(s)
        return s

    # -- placement --
    def _cases_rect(self, x0, z0, x1, z1):
        return [(i, j) for i in range(int(math.floor(x0 + 0.05)), int(math.floor(x1 - 0.05)) + 1)
                for j in range(int(math.floor(z0 + 0.05)), int(math.floor(z1 - 0.05)) + 1)]

    def _libre(self, cases):
        s = self.salle
        return all(s.contient(i, j) and (i, j) not in self.occupe and (i, j) not in self.reserve for i, j in cases)

    def placer_mur(self, larg, prof, haut=False, cotes=None, marquer=True):
        """Place un objet contre un mur (face vers la pièce). Renvoie un Cadre ou None."""
        s = self.salle
        cands = []
        for n in (cotes or ((1, 0), (-1, 0), (0, 1), (0, -1))):
            if n[0] != 0:
                x_mur = s.x if n[0] > 0 else s.x + s.l
                cx = x_mur + n[0] * prof / 2
                pos = [s.z + larg / 2 + k * 0.5 for k in range(int((s.p - larg) / 0.5) + 1)]
                for cz in pos:
                    x0, x1 = sorted((x_mur, x_mur + n[0] * prof))
                    cases = self._cases_rect(x0, cz - larg / 2, x1, cz + larg / 2)
                    cands.append((cx, cz, n, cases))
            else:
                z_mur = s.z if n[1] > 0 else s.z + s.p
                cz = z_mur + n[1] * prof / 2
                pos = [s.x + larg / 2 + k * 0.5 for k in range(int((s.l - larg) / 0.5) + 1)]
                for cx in pos:
                    z0, z1 = sorted((z_mur, z_mur + n[1] * prof))
                    cases = self._cases_rect(cx - larg / 2, z0, cx + larg / 2, z1)
                    cands.append((cx, cz, n, cases))
        self.rng.shuffle(cands)
        for cx, cz, n, cases in cands:
            if not self._libre(cases):
                continue
            if haut and self._devant_fenetre(cases, n):
                continue
            if marquer:
                self.occupe.update(cases)
            return Cadre(cx, cz, ANGLE_NORMALE[n])
        return None

    def _devant_fenetre(self, cases, n):
        for (i, j) in cases:
            wi, wj = i - n[0], j - n[1]
            if (wi, wj, -n[0], -n[1]) in self.pont.fenetres:
                return True
        return False

    def placer_libre(self, larg, prof, marge=1, angles=(0, 90, 180, -90)):
        """Place un objet loin des murs, avec une marge de cases libres autour."""
        s = self.salle
        for _ in range(80):
            a = self.rng.choice(angles)
            l, p = (larg, prof) if a in (0, 180) else (prof, larg)
            if s.l - 2 * marge < l or s.p - 2 * marge < p:
                continue
            cx = self.rng.uniform(s.x + marge + l / 2, s.x + s.l - marge - l / 2)
            cz = self.rng.uniform(s.z + marge + p / 2, s.z + s.p - marge - p / 2)
            cx, cz = round(cx * 2) / 2, round(cz * 2) / 2
            cases = self._cases_rect(cx - l / 2 - marge, cz - p / 2 - marge, cx + l / 2 + marge, cz + p / 2 + marge)
            coeur = self._cases_rect(cx - l / 2, cz - p / 2, cx + l / 2, cz + p / 2)
            if not self._libre(coeur) or any((c in self.occupe) for c in cases):
                continue
            self.occupe.update(coeur)
            return Cadre(cx, cz, a)
        return None

    def cases_libres(self):
        s = self.salle
        return [(i, j) for i in range(s.x, s.x + s.l) for j in range(s.z, s.z + s.p)
                if (i, j) not in self.occupe and (i, j) not in self.reserve]

    # -- décalques (sang, griffures) --
    def decalque(self, pos, normale, taille, index, haut=(0, 1, 0)):
        u0, v0 = (index % 2) * 0.5, (index // 2) * 0.5
        uvs = ((u0, v0), (u0 + 0.5, v0), (u0 + 0.5, v0 + 0.5), (u0, v0 + 0.5))
        self.dec.rect(pos, normale, haut, taille, taille, (1, 1, 1, 1), uvs)

    def traces_murales(self, nb):
        s = self.salle
        for _ in range(nb):
            n = self.rng.choice(DIRS)
            if n[0] != 0:
                x = s.x if n[0] > 0 else s.x + s.l
                z = self.rng.uniform(s.z + 0.8, s.z + s.p - 0.8)
            else:
                z = s.z if n[1] > 0 else s.z + s.p
                x = self.rng.uniform(s.x + 0.8, s.x + s.l - 0.8)
            i, j = int(math.floor(x + n[0] * 0.5)), int(math.floor(z + n[1] * 0.5))
            if self.pont.t(i - n[0], j - n[1]) != MUR:
                continue
            y = self.rng.uniform(0.6, 1.9)
            idx = self.rng.choice((0, 1, 2, 2))
            self.decalque((x + n[0] * 0.015, y, z + n[1] * 0.015), (n[0], 0, n[1]), self.rng.uniform(0.6, 1.3), idx)

    def traces_sol(self, nb):
        libres = self.cases_libres()
        for _ in range(min(nb, len(libres))):
            i, j = self.rng.choice(libres)
            idx = self.rng.choice((0, 3, 3, 1))
            a = self.rng.uniform(0, 360)
            haut = (math.cos(math.radians(a)), 0, math.sin(math.radians(a)))
            self.decalque((i + 0.5, 0.012, j + 0.5), (0, 1, 0), self.rng.uniform(0.8, 1.6), idx, haut=haut)

    # -- finalisation --
    def terminer(self):
        tex = textures()
        if not self.b.vide():
            np_ = self.racine.attachNewNode(self.b.construire("decor"))
            np_.setTexture(tex.get("objet"), 1)
        if not self.dec.vide():
            from panda3d.core import TransparencyAttrib
            np_ = self.racine.attachNewNode(self.dec.construire("decalques"))
            np_.setTexture(tex.get("decalques"), 1)
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setDepthWrite(False)
            np_.setDepthOffset(2)
            np_.setBin("transparent", 5)


# ---------------------------------------------------------------------------
# Objets (repère local : x le long du mur, z vers le mur, y vers le haut)
# ---------------------------------------------------------------------------
def neon_plafond(a, x, z, h, defect_proba=0.3, couleur=BLANC_NEON, rayon=None, long=1.3):
    f = Cadre(x, z, a.rng.choice((0, 90)))
    a.boite(f, 0, h - 0.06, 0, long + 0.1, 0.1, 0.3, (0.25, 0.25, 0.27))
    tube = a.emissif(f, 0, h - 0.13, 0, long, 0.05, 0.12)
    a.lumiere((x, h - 0.4, z), couleur, rayon or max(6.5, h * 1.7), "neon", (tube,),
              defectueuse=a.rng.random() < defect_proba)


def lampe_secours(a, f, h=2.3):
    a.boite(f, 0, h, 0.05, 0.3, 0.14, 0.1, (0.2, 0.2, 0.2))
    v = a.emissif(f, 0, h, -0.0, 0.24, 0.09, 0.06)
    pos = f.p(0, h, -0.4)
    a.lumiere(pos, ORANGE_SECOURS, 6.0, "secours", (v,))


def gyrophare(a, f, h=2.5):
    a.boite(f, 0, h + 0.08, 0.1, 0.25, 0.08, 0.2, (0.2, 0.2, 0.2))
    v = a.emissif(f, 0, h, -0.02, 0.18, 0.16, 0.18)
    a.lumiere(f.p(0, h, -0.6), ROUGE_ALARME, 9.0, "alarme", (v,), couleur_courant=ROUGE_ALARME)


def chaise(a, f, lx, lz, renversee=False, col=(0.3, 0.32, 0.36)):
    if renversee:
        rot = a.rng.choice(((90, 0, 0), (0, 0, 90), (-90, 0, 0)))
        a.boite(f, lx, 0.24, lz, 0.45, 0.45, 0.05, col, rot=(rot[0], a.rng.uniform(0, 360), rot[2]))
        a.boite(f, lx + 0.25, 0.23, lz, 0.45, 0.05, 0.45, col, rot=(0, a.rng.uniform(0, 360), 90))
        return
    a.boite(f, lx, 0.45, lz, 0.45, 0.05, 0.45, col)
    a.boite(f, lx, 0.75, lz + 0.2, 0.45, 0.55, 0.04, col)
    for sx in (-0.19, 0.19):
        for sz in (-0.19, 0.19):
            a.boite(f, lx + sx, 0.22, lz + sz, 0.04, 0.44, 0.04, (0.2, 0.2, 0.2))


def lit_superpose(a, f):
    col_cadre = (0.35, 0.37, 0.4)
    for sx in (-1.0, 1.0):
        for sz in (-0.45, 0.45):
            a.boite(f, sx, 1.0, sz, 0.06, 2.0, 0.06, col_cadre)
    for y in (0.35, 1.45):
        a.boite(f, 0, y, 0, 2.0, 0.1, 0.9, col_cadre)
        a.boite(f, 0, y + 0.12, 0, 1.9, 0.14, 0.85, (0.35, 0.4, 0.48))
        a.boite(f, -0.72, y + 0.23, 0, 0.35, 0.09, 0.6, (0.8, 0.8, 0.78))
        couv = a.rng.choice(((0.25, 0.3, 0.45), (0.45, 0.2, 0.2), (0.3, 0.35, 0.25)))
        if a.rng.random() < 0.3:   # couverture tombée au sol
            a.boite(f, a.rng.uniform(-0.6, 0.6), 0.02, -0.8, 1.2, 0.03, 0.7, couv, rot=(0, a.rng.uniform(-30, 30), 0))
        else:
            a.boite(f, 0.25, y + 0.2, 0, 1.3, 0.04, 0.88, couv)
    for k in range(4):   # échelle
        a.boite(f, 0.85, 0.5 + k * 0.3, -0.47, 0.25, 0.03, 0.03, col_cadre)
    a.collision(f, 2.1, 1.0)


def bureau(a, f):
    col = (0.4, 0.38, 0.35)
    a.boite(f, 0, 0.74, 0, 1.2, 0.04, 0.6, col)
    a.boite(f, 0.38, 0.36, 0, 0.4, 0.72, 0.55, (0.32, 0.31, 0.3))
    for sx in (-0.56,):
        for sz in (-0.26, 0.26):
            a.boite(f, sx, 0.36, sz, 0.04, 0.72, 0.04, (0.2, 0.2, 0.2))
    a.boite(f, -0.1, 0.97, 0.15, 0.55, 0.34, 0.04, (0.12, 0.12, 0.13))
    a.boite(f, -0.1, 0.8, 0.18, 0.08, 0.1, 0.08, (0.12, 0.12, 0.13))
    for _ in range(a.rng.randint(1, 4)):   # feuilles éparpillées
        a.boite(f, a.rng.uniform(-0.5, 0.5), 0.765, a.rng.uniform(-0.25, 0.1), 0.21, 0.003, 0.29,
                (0.8, 0.8, 0.75), rot=(0, a.rng.uniform(0, 360), 0))
    a.collision(f, 1.2, 0.6)


def armoire(a, f, col=(0.55, 0.57, 0.6), vitree=False):
    a.boite(f, 0, 0.95, 0, 1.0, 1.9, 0.45, col)
    a.boite(f, 0, 0.95, -0.228, 0.02, 1.8, 0.01, (0.1, 0.1, 0.1))
    for sx in (-0.08, 0.08):
        a.boite(f, sx, 1.0, -0.235, 0.03, 0.2, 0.02, (0.8, 0.8, 0.8))
    if vitree:
        for y in (0.6, 1.1, 1.6):
            for k in range(a.rng.randint(1, 4)):
                a.boite(f, a.rng.uniform(-0.4, 0.4), y + 0.08, 0.0, 0.08, 0.16, 0.08,
                        a.rng.choice(((0.8, 0.8, 0.8), (0.5, 0.2, 0.2), (0.3, 0.5, 0.7))))
    a.collision(f, 1.0, 0.45)


def lit_medical(a, f):
    a.boite(f, 0, 0.55, 0, 0.9, 0.1, 2.0, (0.6, 0.62, 0.64))
    for sx in (-0.4, 0.4):
        for sz in (-0.9, 0.9):
            a.boite(f, sx, 0.27, sz, 0.05, 0.54, 0.05, (0.3, 0.3, 0.3))
    a.boite(f, 0, 0.66, 0, 0.85, 0.12, 1.9, (0.62, 0.72, 0.68))
    a.boite(f, 0, 0.76, 0.75, 0.6, 0.1, 0.35, (0.85, 0.85, 0.85))
    if a.rng.random() < 0.5:   # drap taché
        a.boite(f, 0, 0.73, -0.3, 0.87, 0.03, 1.1, (0.55, 0.25, 0.22))
    for sx in (-0.47, 0.47):
        a.boite(f, sx, 0.8, 0, 0.03, 0.03, 1.4, (0.7, 0.7, 0.7))
    # perfusion
    a.cyl(f, (0.7, 0, 0.7), (0.7, 1.9, 0.7), 0.02, (0.6, 0.6, 0.6), seg=5)
    a.boite(f, 0.7, 1.75, 0.7, 0.15, 0.22, 0.06, (0.7, 0.8, 0.75))
    a.collision(f, 1.0, 2.0)


def scanner(a, f):
    a.boite(f, 0, 0.4, 0.3, 0.8, 0.8, 1.8, (0.8, 0.82, 0.84))
    a.cyl(f, (0, 1.0, -0.5), (0, 1.0, -0.1), 0.95, (0.85, 0.86, 0.88), seg=16)
    a.cyl(f, (0, 1.0, -0.52), (0, 1.0, -0.08), 0.62, (0.05, 0.05, 0.06), seg=16)
    ecran = a.emissif(f, 0, 1.75, -0.3, 0.6, 0.35, 0.03)
    a.lumiere(f.p(0, 1.6, -1.0), (0.3, 0.8, 0.7), 3.5, "console", (ecran,), defectueuse=True)
    a.collision(f, 2.0, 2.0)


def chariot(a, f):
    a.boite(f, 0, 0.8, 0, 0.9, 0.04, 0.5, (0.7, 0.7, 0.72))
    a.boite(f, 0, 0.3, 0, 0.9, 0.04, 0.5, (0.7, 0.7, 0.72))
    for sx in (-0.42, 0.42):
        for sz in (-0.22, 0.22):
            a.boite(f, sx, 0.4, sz, 0.03, 0.8, 0.03, (0.5, 0.5, 0.5))
    a.collision(f, 0.9, 0.5)


def table_longue(a, f, longueur):
    col = (0.5, 0.5, 0.48)
    a.boite(f, 0, 0.75, 0, longueur, 0.06, 1.0, col)
    for sx in (-longueur / 2 + 0.3, longueur / 2 - 0.3):
        a.boite(f, sx, 0.37, 0, 0.1, 0.72, 0.8, (0.3, 0.3, 0.3))
    for sz in (-0.8, 0.8):
        a.boite(f, 0, 0.45, sz, longueur - 0.2, 0.06, 0.35, (0.4, 0.4, 0.42))
        for sx in (-longueur / 2 + 0.4, longueur / 2 - 0.4):
            a.boite(f, sx, 0.22, sz, 0.08, 0.44, 0.3, (0.3, 0.3, 0.3))
    for _ in range(a.rng.randint(2, 7)):   # plateaux, gobelets renversés
        x = a.rng.uniform(-longueur / 2 + 0.3, longueur / 2 - 0.3)
        z = a.rng.uniform(-0.35, 0.35)
        if a.rng.random() < 0.6:
            a.boite(f, x, 0.79, z, 0.4, 0.02, 0.3, (0.55, 0.6, 0.62), rot=(0, a.rng.uniform(-20, 20), 0))
        else:
            if a.rng.random() < 0.5:
                a.cyl(f, (x, 0.78, z), (x, 0.9, z), 0.04, (0.8, 0.8, 0.8), seg=6)
            else:
                a.cyl(f, (x, 0.82, z), (x + 0.12, 0.82, z), 0.04, (0.8, 0.8, 0.8), seg=6)
    a.collision(f, longueur, 2.0)


def comptoir(a, f):
    a.boite(f, 0, 0.45, 0, 1.0, 0.9, 0.65, (0.45, 0.47, 0.5))
    a.boite(f, 0, 0.92, 0, 1.02, 0.04, 0.68, (0.7, 0.72, 0.74))
    a.boite(f, 0, 1.85, 0.12, 1.0, 0.6, 0.4, (0.5, 0.5, 0.52))
    if a.rng.random() < 0.5:
        a.cyl(f, (0.1, 0.94, 0), (0.1, 1.14, 0), 0.15, (0.6, 0.6, 0.62), seg=10)
    a.collision(f, 1.0, 0.65)


def frigo(a, f):
    a.boite(f, 0, 1.0, 0, 0.9, 2.0, 0.75, (0.8, 0.8, 0.8))
    a.boite(f, 0, 1.3, -0.38, 0.88, 0.02, 0.01, (0.2, 0.2, 0.2))
    a.boite(f, 0.35, 1.0, -0.4, 0.03, 0.4, 0.03, (0.5, 0.5, 0.5))
    a.collision(f, 0.9, 0.75)


def console(a, f, genre="console", couleur=(0.25, 0.6, 1.0), defect=False):
    col = (0.3, 0.32, 0.36)
    a.boite(f, 0, 0.42, 0.05, 1.4, 0.84, 0.7, col)
    a.boite(f, 0, 0.9, -0.05, 1.4, 0.06, 0.75, (0.22, 0.23, 0.26), rot=(-18, 0, 0))
    a.boite(f, 0, 1.25, 0.32, 1.25, 0.65, 0.06, (0.15, 0.15, 0.17))
    for k in range(8):   # boutons
        a.boite(f, -0.55 + k * 0.15, 0.95, -0.2, 0.07, 0.03, 0.05,
                a.rng.choice(((0.7, 0.1, 0.1), (0.1, 0.6, 0.2), (0.8, 0.7, 0.1))), rot=(-18, 0, 0))
    ecran = a.emissif(f, 0, 1.25, 0.285, 1.12, 0.52, 0.02)
    a.collision(f, 1.4, 0.8)
    src = a.lumiere(f.p(0, 1.2, -0.6), couleur, 3.5, genre, (ecran,), defectueuse=defect)
    return ecran, src


def fauteuil(a, f, lx=0.0, lz=0.0):
    a.boite(f, lx, 0.5, lz, 0.7, 0.12, 0.7, (0.25, 0.22, 0.2))
    a.boite(f, lx, 0.95, lz + 0.32, 0.7, 0.9, 0.1, (0.25, 0.22, 0.2))
    a.cyl(f, (lx, 0, lz), (lx, 0.45, lz), 0.08, (0.3, 0.3, 0.3), seg=6)
    for sx in (-0.38, 0.38):
        a.boite(f, lx + sx, 0.7, lz, 0.08, 0.06, 0.6, (0.3, 0.3, 0.3))
    a.collision(f, 0.8, 0.8, lx, lz)


def etagere(a, f):
    col = (0.4, 0.42, 0.45)
    for sx in (-0.97, 0.97):
        for sz in (-0.22, 0.22):
            a.boite(f, sx, 1.1, sz, 0.05, 2.2, 0.05, col)
    for y in (0.1, 0.7, 1.3, 1.9):
        a.boite(f, 0, y, 0, 2.0, 0.04, 0.5, col)
        x = -0.85
        while x < 0.8:
            if a.rng.random() < 0.7:
                w = a.rng.uniform(0.25, 0.5)
                hh = a.rng.uniform(0.2, 0.45)
                a.boite(f, x + w / 2, y + 0.02 + hh / 2, a.rng.uniform(-0.05, 0.05), w * 0.95, hh, 0.4,
                        a.rng.choice(((0.55, 0.45, 0.3), (0.4, 0.45, 0.5), (0.6, 0.6, 0.55))))
                x += w
            else:
                x += 0.3
    a.collision(f, 2.0, 0.5)


def caisse(a, f, lx, lz, taille, ly=0.0, rot=0.0):
    col = a.rng.choice(((0.45, 0.4, 0.3), (0.35, 0.4, 0.35), (0.5, 0.45, 0.25)))
    a.boite(f, lx, ly + taille / 2, lz, taille, taille, taille, col, rot=(0, rot, 0))
    a.boite(f, lx, ly + taille / 2, lz, taille + 0.02, taille * 0.12, taille + 0.02,
            (col[0] * 0.6, col[1] * 0.6, col[2] * 0.6), rot=(0, rot, 0))


def baril(a, f, lx, lz, couche=False):
    col = a.rng.choice(((0.5, 0.15, 0.1), (0.2, 0.3, 0.5), (0.6, 0.5, 0.1)))
    if couche:
        ang = a.rng.uniform(0, 3.14)
        dx, dz = math.cos(ang) * 0.45, math.sin(ang) * 0.45
        a.cyl(f, (lx - dx, 0.3, lz - dz), (lx + dx, 0.3, lz + dz), 0.3, col, seg=10)
    else:
        a.cyl(f, (lx, 0, lz), (lx, 0.9, lz), 0.3, col, seg=10)
        a.cyl(f, (lx, 0.3, lz), (lx, 0.34, lz), 0.31, (col[0] * 0.6, col[1] * 0.6, col[2] * 0.6), seg=10)


def generateur(a, f):
    a.boite(f, 0, 1.0, 0, 1.6, 2.0, 1.2, (0.4, 0.42, 0.38))
    for k in range(5):
        a.boite(f, -0.5 + k * 0.25, 1.2, -0.61, 0.15, 1.0, 0.02, (0.1, 0.1, 0.1))
    a.cyl(f, (-0.4, 2.0, 0), (-0.4, 2.6, 0), 0.2, (0.3, 0.3, 0.3), seg=8)
    a.cyl(f, (0.4, 2.0, 0.2), (0.4, 3.5, 0.2), 0.12, (0.45, 0.35, 0.25), seg=8)
    v = a.emissif(f, 0.55, 1.75, -0.61, 0.12, 0.12, 0.02)
    a.lumiere(f.p(0.5, 1.7, -0.8), (0.2, 1.0, 0.3), 2.0, "console", (v,))
    a.collision(f, 1.6, 1.2)


def reservoir(a, f):
    a.cyl(f, (0, 0, 0), (0, 3.2, 0), 0.75, (0.5, 0.52, 0.5), seg=14)
    for y in (0.6, 1.6, 2.6):
        a.cyl(f, (0, y, 0), (0, y + 0.08, 0), 0.78, (0.6, 0.5, 0.1), seg=14)
    a.cyl(f, (0, 2.8, 0.5), (0, 2.8, 0.95), 0.1, (0.35, 0.35, 0.35), seg=6)
    a.collision(f, 1.6, 1.6)


# ---------------------------------------------------------------------------
# Salles
# ---------------------------------------------------------------------------
def _neons_grille(a, espacement, defect=0.3, rayon=None, long=1.3, marge=1.5):
    s = a.salle
    nx = max(1, int((s.l - 2 * marge) // espacement) + 1)
    nz = max(1, int((s.p - 2 * marge) // espacement) + 1)
    for ix in range(nx):
        for iz in range(nz):
            x = s.x + s.l / 2 + (ix - (nx - 1) / 2) * espacement
            z = s.z + s.p / 2 + (iz - (nz - 1) / 2) * espacement
            neon_plafond(a, x, z, s.h, defect, rayon=rayon, long=long)


def _secours_pres_porte(a, h=2.3):
    """Lampe de secours orange fixée au mur, juste à côté d'une porte."""
    s = a.salle
    if not s.portes:
        return
    p = a.pont.portes[a.rng.choice(s.portes)]
    n = (-p.normale[0], -p.normale[1])      # normale intérieure du mur
    (i, j) = p.cases[0]
    if p.normale[0] != 0:
        xb = i + 0.5 - p.normale[0] * 0.5
        zs = [c[1] for c in p.cases]
        for z in (min(zs) - 0.6, max(zs) + 1.6):
            if s.z + 0.3 < z < s.z + s.p - 0.3:
                lampe_secours(a, Cadre(xb + n[0] * 0.07, z, ANGLE_NORMALE[n]), min(h, s.h - 0.4))
                return
    else:
        zb = j + 0.5 - p.normale[1] * 0.5
        xs = [c[0] for c in p.cases]
        for x in (min(xs) - 0.6, max(xs) + 1.6):
            if s.x + 0.3 < x < s.x + s.l - 0.3:
                lampe_secours(a, Cadre(x, zb + n[1] * 0.07, ANGLE_NORMALE[n]), min(h, s.h - 0.4))
                return


def amenager_chambre(a, infos):
    for _ in range(a.rng.randint(1, 2)):
        f = a.placer_mur(2.1, 1.0, haut=True)
        if f:
            lit_superpose(a, f)
    for _ in range(a.rng.randint(2, 3)):
        f = a.placer_mur(0.75, 0.6, haut=True)
        if f:
            a.casiers.append(Casier(a.racine, f, a.rng))
            a.collision(f, 0.72, 0.55)
    f = a.placer_mur(1.2, 1.3)
    if f:
        bureau(a, Cadre(*f.p(0, 0, 0.35)[::2], f.angle))
        chaise(a, f, 0.0, -0.35, renversee=a.rng.random() < 0.5)
    for _ in range(a.rng.randint(1, 3)):
        c = a.placer_libre(0.5, 0.5, marge=0)
        if c:
            caisse(a, c, 0, 0, a.rng.uniform(0.25, 0.45), rot=a.rng.uniform(0, 90))
    neon_plafond(a, a.salle.x + a.salle.l / 2, a.salle.z + a.salle.p / 2, a.salle.h, 0.45)
    _secours_pres_porte(a)
    a.traces_murales(a.rng.randint(0, 2))
    a.traces_sol(a.rng.randint(0, 2))


def amenager_infirmerie(a, infos):
    cote = a.rng.choice(DIRS)
    for _ in range(4):
        f = a.placer_mur(1.2, 2.2, cotes=(cote,)) or a.placer_mur(1.2, 2.2)
        if f:
            lit_medical(a, f)
    for _ in range(a.rng.randint(2, 3)):
        f = a.placer_mur(1.0, 0.45, haut=True)
        if f:
            armoire(a, f, (0.85, 0.87, 0.88), vitree=True)
    f = a.placer_libre(2.0, 2.2, marge=1)
    if f:
        scanner(a, f)
    for _ in range(2):
        f = a.placer_libre(0.9, 0.5, marge=0)
        if f:
            chariot(a, f)
    f = a.placer_mur(0.75, 0.6, haut=True)
    if f:
        a.casiers.append(Casier(a.racine, f, a.rng))
        a.collision(f, 0.72, 0.55)
    _neons_grille(a, 3.5, defect=0.55)
    _secours_pres_porte(a)
    a.traces_murales(a.rng.randint(2, 4))
    a.traces_sol(a.rng.randint(2, 4))


def amenager_salle_a_manger(a, infos):
    s = a.salle
    long_axe_x = s.l >= s.p
    longueur = max(3.0, min(6.0, (s.l if long_axe_x else s.p) - 5))
    for _ in range(2):
        f = a.placer_libre(longueur, 2.0, marge=1, angles=(0, 180) if long_axe_x else (90, -90))
        if f:
            table_longue(a, f, longueur)
    cote = a.rng.choice(DIRS)
    for _ in range(4):
        f = a.placer_mur(1.0, 0.7, haut=True, cotes=(cote,))
        if f:
            comptoir(a, f)
    f = a.placer_mur(0.9, 0.75, haut=True)
    if f:
        frigo(a, f)
    for _ in range(a.rng.randint(3, 6)):
        c = a.placer_libre(0.6, 0.6, marge=0)
        if c:
            chaise(a, c, 0, 0, renversee=a.rng.random() < 0.65)
    _neons_grille(a, 4.0, defect=0.35)
    _secours_pres_porte(a)
    a.traces_murales(a.rng.randint(1, 3))
    a.traces_sol(a.rng.randint(1, 3))


def amenager_commandement(a, infos):
    s = a.salle
    # côté ayant le plus de fenêtres = baie vitrée
    def nb_fen(n):
        return sum(1 for (wi, wj, dx, dz) in a.pont.fenetres if (dx, dz) == (-n[0], -n[1]) and s.contient(wi - dx, wj - dz))
    cote = max(DIRS, key=nb_fen)
    terminal = None
    for k in range(5):
        f = a.placer_mur(1.5, 1.4, cotes=(cote,))
        if not f:
            f = a.placer_mur(1.5, 1.4)
        if not f:
            continue
        fc = Cadre(*f.p(0, 0, 0.3)[::2], f.angle)
        e, src = console(a, fc, couleur=(0.2, 0.55, 1.0), defect=a.rng.random() < 0.3)
        chaise(a, f, 0.0, -0.45, renversee=a.rng.random() < 0.3)
        if terminal is None:
            terminal = fc
            src.couleur = (0.1, 0.9, 0.4)
            src.couleur_courant = (0.1, 1.0, 0.45)
    f = a.placer_libre(1.8, 1.8, marge=1)
    if f:
        a.cyl(f, (0, 0, 0), (0, 0.8, 0), 0.5, (0.3, 0.32, 0.36), seg=12)
        a.cyl(f, (0, 0.8, 0), (0, 0.9, 0), 0.85, (0.25, 0.27, 0.3), seg=16)
        holo = a.emissif(f, 0, 1.45, 0, 0.9, 0.45, 0.9, modele="sphere")
        holo.alpha = 0.6
        a.lumiere(f.p(0, 1.4, 0), (0.2, 0.6, 1.0), 5.0, "console", (holo,))
        a.collision(f, 1.8, 1.8)
    f = a.placer_libre(0.9, 0.9, marge=1)
    if f:
        fauteuil(a, f)
    _neons_grille(a, 4.5, defect=0.2)
    _secours_pres_porte(a)
    a.traces_murales(a.rng.randint(1, 3))
    a.traces_sol(a.rng.randint(0, 2))
    if terminal is None:
        c = a.cases_libres()[0]
        terminal = Cadre(c[0] + 0.5, c[1] + 0.5, 0)
    ax, az = terminal.avant()
    infos["terminal"] = Vec3(terminal.cx + ax * 0.6, 1.0, terminal.cz + az * 0.6)


def amenager_machines(a, infos):
    s = a.salle
    cx, cz = s.x + s.l / 2, s.z + s.p / 2
    f = Cadre(cx, cz, 0)
    h = s.h
    # --- réacteur central ---
    a.cyl(f, (0, 0, 0), (0, 0.5, 0), 2.3, (0.3, 0.3, 0.32), seg=20)
    a.cyl(f, (0, h - 1.4, 0), (0, h - 0.7, 0), 1.7, (0.3, 0.3, 0.32), seg=20)
    for k in range(6):
        ang = k * math.pi / 3
        a.boite(f, math.cos(ang) * 1.15, (h - 0.9) / 2 + 0.25, math.sin(ang) * 1.15, 0.2, h - 1.9, 0.2,
                (0.2, 0.2, 0.22), rot=(0, -math.degrees(ang), 0))
        a.cyl(f, (math.cos(ang) * 1.3, h - 0.7, math.sin(ang) * 1.3), (math.cos(ang) * 1.3, h, math.sin(ang) * 1.3),
              0.15, (0.35, 0.3, 0.25), seg=6)
    coeur_mb = MeshBuilder(1.0)
    coeur_mb.cylindre((cx, 0.5, cz), (cx, h - 1.4, cz), 1.0, (1, 1, 1), segments=20)
    fixtures = []
    coeur = Entity(parent=a.racine, unlit=True)
    coeur.attachNewNode(coeur_mb.construire("coeur"))
    fixtures.append(coeur)
    for y in (1.2, 2.6, 4.0):
        if y < h - 1.6:
            mb = MeshBuilder(1.0)
            mb.cylindre((cx, y, cz), (cx, y + 0.15, cz), 1.35, (1, 1, 1), segments=20)
            anneau = Entity(parent=a.racine, unlit=True)
            anneau.attachNewNode(mb.construire("anneau"))
            fixtures.append(anneau)
    a.lumiere((cx, 2.5, cz), (0.9, 0.15, 0.08), 14.0, "reacteur", fixtures, couleur_courant=(0.3, 0.8, 1.0))
    # garde-corps
    postes = 14
    for k in range(postes):
        a0, a1 = 2 * math.pi * k / postes, 2 * math.pi * (k + 1) / postes
        p0 = (math.cos(a0) * 3.0, 0, math.sin(a0) * 3.0)
        p1 = (math.cos(a1) * 3.0, 0, math.sin(a1) * 3.0)
        a.cyl(f, p0, (p0[0], 1.05, p0[2]), 0.035, (0.55, 0.5, 0.2), seg=5)
        a.cyl(f, (p0[0], 1.05, p0[2]), (p1[0], 1.05, p1[2]), 0.03, (0.55, 0.5, 0.2), seg=5)
        a.cyl(f, (p0[0], 0.55, p0[2]), (p1[0], 0.55, p1[2]), 0.025, (0.55, 0.5, 0.2), seg=5)
    # bandes de danger au sol autour du réacteur
    for k in range(24):
        a0 = 2 * math.pi * k / 24
        col = (0.6, 0.5, 0.05) if k % 2 == 0 else (0.05, 0.05, 0.05)
        a.boite(f, math.cos(a0) * 3.35, 0.006, math.sin(a0) * 3.35, 0.8, 0.012, 0.35, col, rot=(0, -math.degrees(a0) + 90, 0))
    a.monde.ajouter_boite(cx - 3.1, cz - 3.1, cx + 3.1, cz + 3.1)
    for i in range(int(cx - 3.1), int(cx + 3.1) + 1):
        for j in range(int(cz - 3.1), int(cz + 3.1) + 1):
            a.occupe.add((i, j))
    # --- console de rétablissement du courant ---
    options = [(0, -4.0, 0), (0, 4.0, 180), (-4.0, 0, 90), (4.0, 0, -90)]
    a.rng.shuffle(options)
    for dx, dz, ang in options:
        fc = Cadre(cx + dx, cz + dz, ang)
        cases = a._cases_rect(cx + dx - 0.8, cz + dz - 0.8, cx + dx + 0.8, cz + dz + 0.8)
        if a._libre(cases):
            a.occupe.update(cases)
            # l'écran regarde vers l'extérieur : le joueur l'utilise face au réacteur
            console(a, fc, couleur=(1.0, 0.4, 0.1), defect=True)
            av = fc.avant()
            infos["console_courant"] = Vec3(fc.cx + av[0] * 0.6, 1.0, fc.cz + av[1] * 0.6)
            break
    else:
        infos["console_courant"] = Vec3(cx + 3.6, 1.0, cz)
    # --- machines le long des murs ---
    for _ in range(4):
        f2 = a.placer_mur(1.6, 1.2, haut=True)
        if f2:
            generateur(a, f2)
    for _ in range(2):
        f2 = a.placer_mur(1.6, 1.6, haut=True)
        if f2:
            reservoir(a, Cadre(*f2.p(0, 0, 0)[::2], f2.angle))
    for _ in range(a.rng.randint(2, 4)):
        c = a.placer_libre(0.7, 0.7, marge=0)
        if c:
            baril(a, c, 0, 0, couche=a.rng.random() < 0.4)
    # alarmes et éclairage
    for _ in range(2):
        f2 = a.placer_mur(0.4, 0.2, marquer=False)
        if f2:
            gyrophare(a, f2, h=min(4.5, h - 0.8))
    _neons_grille(a, 6.0, defect=0.5, rayon=12.0, long=1.8)
    _secours_pres_porte(a)
    a.traces_murales(a.rng.randint(2, 4))
    a.traces_sol(a.rng.randint(2, 5))


def amenager_hangar(a, infos):
    s = a.salle
    cx, cz = s.x + s.l / 2, s.z + s.p / 2
    ang = 0 if s.p >= s.l else 90
    f = Cadre(cx, cz, ang)
    coque = (0.62, 0.64, 0.66)
    sombre = (0.25, 0.27, 0.3)
    # --- navette de fuite ---
    a.boite(f, 0, 2.2, 0, 3.2, 2.4, 8.0, coque)
    a.boite(f, 0, 2.0, -4.6, 2.6, 1.8, 1.8, coque, rot=(-14, 0, 0))
    a.boite(f, 0, 2.55, -4.9, 2.2, 0.7, 1.0, (0.08, 0.12, 0.18), rot=(-35, 0, 0))
    a.boite(f, 0, 1.6, 1.2, 8.5, 0.25, 3.0, coque)
    a.boite(f, 0, 1.6, 2.4, 9.0, 0.3, 0.6, sombre)
    a.boite(f, 0, 4.0, 3.2, 0.25, 1.8, 1.8, coque)
    a.boite(f, 0, 3.45, 0, 3.3, 0.1, 8.1, (0.55, 0.12, 0.08))
    for sx in (-1.0, 1.0):
        a.cyl(f, (sx, 2.2, 4.0), (sx, 2.2, 4.9), 0.6, sombre, seg=12)
    for sx in (-1.2, 1.2):
        for sz in (-2.8, 2.5):
            a.cyl(f, (sx, 0, sz), (sx, 1.0, sz), 0.1, (0.3, 0.3, 0.3), seg=6)
            a.boite(f, sx, 0.05, sz, 0.5, 0.1, 0.5, (0.3, 0.3, 0.3))
    # sas latéral
    a.boite(f, 1.61, 1.9, 0.0, 0.02, 1.9, 1.2, (0.15, 0.15, 0.16))
    a.boite(f, 1.8, 0.45, 0.0, 0.4, 0.06, 1.0, sombre, rot=(0, 0, 25))
    fix = []
    for sx in (-1.0, 1.0):
        e = a.emissif(f, sx, 2.2, 4.92, 0.9, 0.9, 0.05, modele="sphere")
        fix.append(e)
    e = a.emissif(f, 1.625, 2.95, 0, 0.02, 0.08, 1.2)
    fix.append(e)
    a.lumiere(f.p(0, 2.5, 5.8), (0.3, 0.7, 1.0), 7.0, "navette", fix)
    a.collision(f, 3.4, 10.0)
    a.collision(f, 8.6, 3.0, 0, 1.2)
    for i in range(s.x, s.x + s.l):
        for j in range(s.z, s.z + s.p):
            x, z = i + 0.5 - cx, j + 0.5 - cz
            lxx, lzz = (x, z) if ang == 0 else (z, x)
            if abs(lxx) < 5.2 and abs(lzz) < 6.0:
                a.occupe.add((i, j))
    sas = f.p(2.3, 1.0, 0)
    infos["navette"] = Vec3(*sas)
    # marquage au sol de l'aire d'atterrissage
    for sx, sz, w, d in ((0, -6.0, 10.0, 0.15), (0, 6.0, 10.0, 0.15), (-5.0, 0, 0.15, 12.0), (5.0, 0, 0.15, 12.0)):
        a.boite(f, sx, 0.006, sz, w, 0.012, d, (0.7, 0.6, 0.1))
    # caisses empilées et fûts
    for _ in range(a.rng.randint(4, 7)):
        f2 = a.placer_mur(1.4, 1.4)
        if f2:
            t = a.rng.uniform(0.9, 1.3)
            caisse(a, f2, 0, 0, t, rot=a.rng.uniform(-8, 8))
            if a.rng.random() < 0.6:
                caisse(a, f2, a.rng.uniform(-0.1, 0.1), 0, t * 0.8, ly=t, rot=a.rng.uniform(-20, 20))
            a.collision(f2, 1.4, 1.4)
    for _ in range(a.rng.randint(3, 6)):
        c = a.placer_libre(0.7, 0.7, marge=0)
        if c:
            baril(a, c, 0, 0, couche=a.rng.random() < 0.3)
    for _ in range(2):
        f2 = a.placer_mur(1.6, 1.6, haut=True)
        if f2:
            reservoir(a, f2)
    for _ in range(2):
        f2 = a.placer_mur(0.4, 0.2, marquer=False)
        if f2:
            gyrophare(a, f2, h=4.0)
    _neons_grille(a, 7.0, defect=0.35, rayon=15.0, long=2.2, marge=3)
    _secours_pres_porte(a)
    a.traces_murales(a.rng.randint(2, 4))
    a.traces_sol(a.rng.randint(2, 4))


def amenager_stockage(a, infos):
    for _ in range(a.rng.randint(2, 4)):
        f = a.placer_mur(2.0, 0.5, haut=True)
        if f:
            etagere(a, f)
    for _ in range(a.rng.randint(3, 6)):
        c = a.placer_libre(1.1, 1.1, marge=0)
        if c:
            caisse(a, c, 0, 0, a.rng.uniform(0.6, 1.0), rot=a.rng.uniform(0, 90))
            a.collision(c, 0.9, 0.9)
    for _ in range(a.rng.randint(1, 3)):
        c = a.placer_libre(0.7, 0.7, marge=0)
        if c:
            baril(a, c, 0, 0, couche=a.rng.random() < 0.5)
    f = a.placer_mur(0.75, 0.6, haut=True)
    if f:
        a.casiers.append(Casier(a.racine, f, a.rng))
        a.collision(f, 0.72, 0.55)
    _neons_grille(a, 4.0, defect=0.6)
    a.traces_murales(a.rng.randint(0, 2))
    a.traces_sol(a.rng.randint(0, 2))


AMENAGEMENTS = {
    "chambre": amenager_chambre,
    "infirmerie": amenager_infirmerie,
    "salle_a_manger": amenager_salle_a_manger,
    "commandement": amenager_commandement,
    "machines": amenager_machines,
    "hangar": amenager_hangar,
    "stockage": amenager_stockage,
}


# ---------------------------------------------------------------------------
# Couloirs : tuyaux et câbles au plafond, appliques, débris
# ---------------------------------------------------------------------------
def decorer_couloirs(monde, eclairage, rng):
    p = monde.pont
    a = Amenageur(monde, eclairage, None, rng, Entity(parent=monde.racine, name="couloirs"))
    lampes = []
    cellules = [(i, j) for i in range(p.largeur) for j in range(p.profondeur)
                if p.type[i, j] == SOL and p.salle[i, j] == -1]
    col_tuyau = (0.42, 0.36, 0.3)
    col_tuyau2 = (0.3, 0.35, 0.38)
    for (i, j) in cellules:
        h = float(p.hauteur[i, j])
        for n in DIRS:
            wi, wj = i + n[0], j + n[1]
            if p.t(wi, wj) == SOL or p.t(wi, wj) == PORTE:
                continue
            # tuyaux le long du mur (perpendiculaire à n)
            (ax, az), r = monde._arete(i, j, n)
            o1, o2 = 0.22, 0.14
            a1 = (ax - n[0] * o1, h - 0.22, az - n[1] * o1)
            b1 = (ax + r[0] - n[0] * o1, h - 0.22, az + r[1] - n[1] * o1)
            a.b.cylindre(a1, b1, 0.09, col_tuyau, segments=6, bouchons=False)
            a2 = (ax - n[0] * o2, h - 0.5, az - n[1] * o2)
            b2 = (ax + r[0] - n[0] * o2, h - 0.5, az + r[1] - n[1] * o2)
            a.b.cylindre(a2, b2, 0.05, col_tuyau2, segments=5, bouchons=False)
            a3 = (ax - n[0] * 0.06, h - 0.08, az - n[1] * 0.06)
            b3 = (ax + r[0] - n[0] * 0.06, h - 0.08, az + r[1] - n[1] * 0.06)
            a.b.cylindre(a3, b3, 0.03, (0.08, 0.08, 0.08), segments=4, bouchons=False)
            if (i + j) % 2 == 0:
                m = ((ax + r[0] * 0.5) - n[0] * 0.15, (az + r[1] * 0.5) - n[1] * 0.15)
                a.b.boite((m[0], h - 0.36, m[1]), (0.06 if n[0] else 0.3, 0.6, 0.3 if n[0] else 0.06), (0.25, 0.25, 0.25))
            # applique murale tous les ~6 mètres
            if not any((lx - i) ** 2 + (lz - j) ** 2 < 36 for lx, lz in lampes) and rng.random() < 0.5:
                if (wi, wj, n[0], n[1]) in p.fenetres:
                    continue
                lampes.append((i, j))
                cx = i + 0.5 + n[0] * 0.45
                cz = j + 0.5 + n[1] * 0.45
                f = Cadre(cx, cz, ANGLE_NORMALE[(-n[0], -n[1])])
                genre = rng.random()
                if genre < 0.2:
                    lampe_secours(a, f, 2.3)
                elif genre < 0.3 and rng.random() < 0.6:
                    gyrophare(a, f, 2.35)
                else:
                    a.boite(f, 0, 2.3, 0.05, 0.9, 0.12, 0.1, (0.22, 0.22, 0.24))
                    tube = a.emissif(f, 0, 2.3, -0.01, 0.8, 0.06, 0.05)
                    a.lumiere(f.p(0, 2.2, -0.5), BLANC_NEON, 7.5, "neon", (tube,),
                              defectueuse=rng.random() < 0.4)
        # câbles qui pendent et débris
        if rng.random() < 0.035:
            x, z = i + rng.uniform(0.2, 0.8), j + rng.uniform(0.2, 0.8)
            bas = rng.uniform(1.9, 2.3)
            pts = [(x, h, z), (x + 0.2, bas + 0.3, z + 0.1), (x + 0.3, bas, z + 0.35), (x + 0.35, bas - 0.25, z + 0.4)]
            for q0, q1 in zip(pts, pts[1:]):
                a.b.cylindre(q0, q1, 0.02, (0.05, 0.05, 0.05), segments=4, bouchons=False)
        if rng.random() < 0.05:
            x, z = i + rng.uniform(0.2, 0.8), j + rng.uniform(0.2, 0.8)
            a.b.boite((x, 0.01, z), (0.25, 0.005, 0.32), (0.75, 0.75, 0.7), rot=(0, rng.uniform(0, 360), 0))
        if rng.random() < 0.02:
            a.decalque((i + 0.5, 0.012, j + 0.5), (0, 1, 0), rng.uniform(0.8, 1.5), rng.choice((0, 1, 3)))
        if rng.random() < 0.025:
            for n in DIRS:
                if p.t(i + n[0], j + n[1]) == MUR:
                    x = i + 0.5 + n[0] * 0.485
                    z = j + 0.5 + n[1] * 0.485
                    a.decalque((x, rng.uniform(0.8, 1.8), z), (-n[0], 0, -n[1]), rng.uniform(0.6, 1.1), rng.choice((0, 1, 2)))
                    break
    a.terminer()
    return a.racine


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def decorer(monde, eclairage, seed):
    """Décore tout le vaisseau. Renvoie un dictionnaire d'informations de jeu."""
    rng = random.Random(seed * 31 + 7)
    p = monde.pont
    infos = {"casiers": [], "piles": [], "journaux": []}
    libres = []
    for s in p.salles:
        racine = Entity(parent=monde.racine, name=f"salle_{s.id}_{s.type}")
        a = Amenageur(monde, eclairage, s, rng, racine)
        AMENAGEMENTS[s.type](a, infos)
        a.terminer()
        monde.ajouter_decor_salle(s.id, racine)
        for c in a.casiers:
            c.salle = s
        infos["casiers"] += a.casiers
        libres += [(c, s) for c in a.cases_libres()]
        if s.id == monde.vaisseau.salle_depart:
            cands = a.cases_libres()
            cx, cz = s.centre
            cands.sort(key=lambda c: (c[0] + 0.5 - cx) ** 2 + (c[1] + 0.5 - cz) ** 2)
            infos["apparition"] = Vec3(cands[0][0] + 0.5, 0, cands[0][1] + 0.5) if cands else Vec3(cx, 0, cz)
            infos["salle_depart"] = s
    decorer_couloirs(monde, eclairage, rng)
    for c in infos["casiers"]:
        c.interactif = Interactif(c.sortie + Vec3(0, 1.0, 0), "casier", "Fouiller le casier", rayon=1.7, donnees=c)
        monde.interactifs.append(c.interactif)
    remplir_casiers(p, infos["casiers"], rng)

    # piles pour la lampe : une dans la chambre de départ, les autres au hasard
    rng.shuffle(libres)
    couloirs = [(i, j) for i in range(p.largeur) for j in range(p.profondeur)
                if p.type[i, j] == SOL and p.salle[i, j] == -1]
    rng.shuffle(couloirs)
    emplacements = []
    depart = infos.get("salle_depart")
    for (c, s) in libres:
        if s is depart and c != (int(infos["apparition"].x), int(infos["apparition"].z)):
            emplacements.append(c)
            break
    salles_vues = set()
    for (c, s) in libres:
        if len(emplacements) >= C.NB_PILES - 2:
            break
        if s.id not in salles_vues and s is not depart:
            salles_vues.add(s.id)
            emplacements.append(c)
    emplacements += couloirs[:C.NB_PILES - len(emplacements)]
    # récompense : deux piles de plus dans chaque salle fermée par une serrure
    for s in p.salles:
        if salle_crochetee(p, s):
            cands = [c for (c, s2) in libres if s2 is s and c not in emplacements]
            emplacements += cands[:2]
    for (i, j) in emplacements:
        infos["piles"].append(creer_pile(monde, Vec3(i + rng.uniform(0.3, 0.7), 0, j + rng.uniform(0.3, 0.7))))

    # journaux de bord (datapads) dans quelques salles
    salles_journal = [s for s in p.salles if s.type in ("infirmerie", "machines", "salle_a_manger", "commandement", "chambre")]
    rng.shuffle(salles_journal)
    for texte, s in zip(JOURNAUX, salles_journal):
        cands = [c for (c, s2) in libres if s2 is s]
        if not cands:
            continue
        i, j = rng.choice(cands)
        infos["journaux"].append(creer_journal(monde, Vec3(i + 0.5, 0, j + 0.5), texte))
    return infos


def salle_crochetee(pont, salle):
    return bool(salle.portes) and all(pont.portes[pid].verrou == "crochet" for pid in salle.portes)


def remplir_casiers(pont, casiers, rng):
    """Répartit couteaux, piles, easter eggs et bric-à-brac dans les casiers."""
    dehors = [c for c in casiers if c.salle is None or not salle_crochetee(pont, c.salle)]
    dedans = [c for c in casiers if c not in dehors]
    rng.shuffle(dehors)
    oeufs = list(OEUFS_DE_PAQUES)
    rng.shuffle(oeufs)
    # les couteaux sont toujours accessibles sans couteau
    for c in dehors[:C.NB_COUTEAUX]:
        c.contenu = ("couteau", "")
    reste = dehors[C.NB_COUTEAUX:] + dedans
    rng.shuffle(reste)
    for c in reste:
        r = rng.random()
        recompense = c in dedans
        if oeufs and (r < 0.45 or recompense and r < 0.7):
            texte, bruyant = oeufs.pop()
            c.contenu = ("oeuf_bruyant" if bruyant else "oeuf", texte)
        elif r < 0.75 or recompense:
            c.contenu = ("pile", "")
        else:
            c.contenu = ("rien", rng.choice(BRIC_A_BRAC))


def creer_pile(monde, pos):
    e = Entity(parent=monde.racine, position=pos + Vec3(0, 0.12, 0))
    mb = MeshBuilder(1.0)
    mb.cylindre((0, -0.1, 0), (0, 0.1, 0), 0.06, (0.2, 0.2, 0.22), segments=8)
    mb.cylindre((0, 0.1, 0), (0, 0.13, 0), 0.025, (0.7, 0.7, 0.7), segments=6)
    np_ = e.attachNewNode(mb.construire("pile"))
    np_.setTexture(textures().get("objet"), 1)
    Entity(parent=e, model="cube", scale=(0.125, 0.05, 0.125), unlit=True, color=color.rgb(0.2, 1.0, 0.35))
    e.rotation_z = 90 if random.random() < 0.5 else 0
    obj = Interactif(pos + Vec3(0, 0.3, 0), "pile", "Ramasser une pile", rayon=1.8, donnees=e)
    monde.interactifs.append(obj)
    return obj


def creer_journal(monde, pos, texte):
    e = Entity(parent=monde.racine, position=pos + Vec3(0, 0.02, 0), rotation_y=random.uniform(0, 360))
    mb = MeshBuilder(1.0)
    mb.boite((0, 0.0, 0), (0.28, 0.025, 0.4), (0.15, 0.15, 0.17))
    np_ = e.attachNewNode(mb.construire("journal"))
    np_.setTexture(textures().get("objet"), 1)
    Entity(parent=e, model="cube", position=(0, 0.014, 0.01), scale=(0.23, 0.005, 0.3), unlit=True,
           color=color.rgb(0.25, 0.55, 0.9))
    obj = Interactif(pos + Vec3(0, 0.3, 0), "journal", "Lire le journal de bord", rayon=1.8, donnees=(e, texte))
    monde.interactifs.append(obj)
    return obj
