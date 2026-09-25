# -*- coding: utf-8 -*-
"""
creature.py — La créature et sa directrice d'IA.

* Silhouette sombre faite de primitives (corps allongé, membres fins) avec des yeux lumineux.
* Pathfinding A* sur la grille (couloirs + conduits d'aération).
* Machine à états : ERRANCE, ENQUÊTE, TRAQUE, RECHERCHE, RETRAITE.
* Elle voit (cône de vision + ligne de vue) et entend (bruits émis par le joueur).
* Une directrice d'IA ajuste la pression : si le joueur reste tranquille trop longtemps,
  la créature se rapproche ; si la traque dure trop, elle bat en retraite dans un conduit.
"""
import heapq
import math
import random

from ursina import Entity, Vec3, color, lerp

import config as C
from generator import SOL, PORTE, CONDUIT, GRILLE, DIRS, connectes

ERRANCE, ENQUETE, TRAQUE, RECHERCHE, RETRAITE = "ERRANCE", "ENQUÊTE", "TRAQUE", "RECHERCHE", "RETRAITE"
NOIR = color.rgb(0.035, 0.035, 0.045)


class Creature(Entity):
    def __init__(self, monde, audio, case_depart):
        super().__init__(name="creature")
        self.monde = monde
        self.pont = monde.pont
        self.audio = audio
        self.rng = random.Random(monde.vaisseau.seed + 99)
        self._construire_corps()
        self._graphe()
        self.position = Vec3(case_depart[0] + 0.5, 0, case_depart[1] + 0.5)
        self.etat = ERRANCE
        self.chemin = []
        self.pause = 0.0
        self.dernier_vu = None
        self.sans_voir = 0.0
        self.repath = 0.0
        self.points_recherche = []
        self.cachee = False
        self.temps_cachee = 0.0
        self.casier_cible = None
        self.agressivite = 1.0
        self.phase_marche = 0.0
        self.vitesse_actuelle = 0.0
        self.cri_cooldown = 0.0
        self.son_timer = 0.0
        self.tic_tete = 0.0
        self.bloque_timer = 0.0
        self.derniere_pos = Vec3(self.position)
        self.voit = False
        self.vu_recemment = 0.0
        self.renifle = 0.0
        self.souffle = audio.boucle("souffle", position=self.position + Vec3(0, 1.8, 0), volume=0.0, portee=14)
        self.cacher(1.0)

    # ------------------------------------------------------------------
    # Corps
    # ------------------------------------------------------------------
    def _membre(self, parent, pos, longueur, epaisseur):
        pivot = Entity(parent=parent, position=pos)
        Entity(parent=pivot, model="cube", scale=(epaisseur, longueur, epaisseur), y=-longueur / 2, color=NOIR)
        return pivot

    def _construire_corps(self):
        self.corps = Entity(parent=self)
        self.bassin = Entity(parent=self.corps, y=1.05)
        Entity(parent=self.bassin, model="sphere", scale=(0.34, 0.25, 0.28), color=NOIR)
        self.torse = Entity(parent=self.bassin, rotation_x=18)
        Entity(parent=self.torse, model="cube", scale=(0.34, 0.85, 0.22), y=0.45, color=NOIR)
        for k in range(6):   # vertèbres saillantes
            Entity(parent=self.torse, model="sphere", scale=0.1, position=(0, 0.1 + k * 0.15, 0.13), color=NOIR)
        for k in range(4):   # côtes
            Entity(parent=self.torse, model="cube", scale=(0.4, 0.03, 0.25), position=(0, 0.35 + k * 0.1, -0.02),
                   color=NOIR)
        self.cou = Entity(parent=self.torse, y=0.92, rotation_x=10)
        Entity(parent=self.cou, model="cube", scale=(0.08, 0.2, 0.08), y=0.08, color=NOIR)
        self.tete = Entity(parent=self.cou, y=0.2)
        Entity(parent=self.tete, model="sphere", scale=(0.24, 0.26, 0.55), position=(0, 0.05, 0.12), color=NOIR)
        Entity(parent=self.tete, model="cube", scale=(0.16, 0.06, 0.3), position=(0, -0.1, -0.1), rotation_x=12,
               color=NOIR)
        # yeux lumineux (quatre, légèrement asymétriques)
        self.yeux = []
        for x, y, s in ((-0.07, 0.07, 0.05), (0.07, 0.07, 0.05), (-0.05, 0.0, 0.03), (0.055, 0.005, 0.03)):
            o = Entity(parent=self.tete, model="sphere", scale=s, position=(x, y, -0.13), unlit=True,
                       color=color.rgb(1.0, 0.85, 0.55))
            self.yeux.append(o)
        # bras très longs
        self.epaules = []
        self.coudes = []
        for sx in (-1, 1):
            e = self._membre(self.torse, (0.22 * sx, 0.82, 0), 0.7, 0.06)
            e.rotation_z = 12 * sx
            c = self._membre(e, (0, -0.7, 0), 0.75, 0.05)
            c.rotation_x = -25
            for k in (-1, 0, 1):
                d = self._membre(c, (0.02 * k, -0.75, 0), 0.28, 0.02)
                d.rotation_z = 10 * k
                d.rotation_x = -20
            self.epaules.append(e)
            self.coudes.append(c)
        # jambes digitigrades
        self.hanches = []
        self.genoux = []
        for sx in (-1, 1):
            h = self._membre(self.bassin, (0.14 * sx, 0, 0), 0.55, 0.08)
            g = self._membre(h, (0, -0.55, 0), 0.55, 0.06)
            g.rotation_x = 35
            p = self._membre(g, (0, -0.55, 0), 0.2, 0.05)
            p.rotation_x = -60
            self.hanches.append(h)
            self.genoux.append(g)

    # ------------------------------------------------------------------
    # Graphe de navigation
    # ------------------------------------------------------------------
    def _graphe(self):
        p = self.pont
        self.voisins = {}
        praticables = (SOL, PORTE, CONDUIT, GRILLE)
        for i in range(p.largeur):
            for j in range(p.profondeur):
                t = int(p.type[i, j])
                if t not in praticables or (t == SOL and self.monde.nav_bloque[i, j]):
                    continue
                vs = []
                for dx, dz in DIRS:
                    n = (i + dx, j + dz)
                    nt = p.t(*n)
                    if nt in praticables and connectes(t, nt) and not (nt == SOL and self.monde.nav_bloque[n]):
                        vs.append(n)
                self.voisins[(i, j)] = vs
        self.cases_conduit = [c for c in self.voisins if p.type[c] == CONDUIT]
        self.cases_sol = [c for c in self.voisins if p.type[c] == SOL]

    def case_proche(self, x, z, rayon=3):
        """Case navigable la plus proche d'un point."""
        ci, cj = int(math.floor(x)), int(math.floor(z))
        if (ci, cj) in self.voisins:
            return (ci, cj)
        meilleur, dmin = None, 1e9
        for i in range(ci - rayon, ci + rayon + 1):
            for j in range(cj - rayon, cj + rayon + 1):
                if (i, j) in self.voisins:
                    d = (i + 0.5 - x) ** 2 + (j + 0.5 - z) ** 2
                    if d < dmin:
                        meilleur, dmin = (i, j), d
        return meilleur

    def astar(self, depart, arrivee, max_iter=9000):
        if depart is None or arrivee is None:
            return []
        p = self.pont
        ouvert = [(0, 0.0, depart)]
        g = {depart: 0.0}
        parent = {}
        it = 0
        ai, aj = arrivee
        while ouvert and it < max_iter:
            it += 1
            _, gc, c = heapq.heappop(ouvert)
            if c == arrivee:
                chemin = [c]
                while c in parent:
                    c = parent[c]
                    chemin.append(c)
                chemin.reverse()
                return chemin[1:]
            if gc > g.get(c, 1e18):
                continue
            for n in self.voisins.get(c, ()):
                t = p.type[n]
                if t == PORTE and p.portes[p.porte_id[n]].verrou is not None:
                    continue
                ng = gc + (1.15 if t == CONDUIT else 1.0)
                if ng < g.get(n, 1e18):
                    g[n] = ng
                    parent[n] = c
                    heapq.heappush(ouvert, (ng + abs(n[0] - ai) + abs(n[1] - aj), ng, n))
        return []

    def aller_vers(self, x, z):
        dep = self.case_proche(self.x, self.z)
        arr = self.case_proche(x, z)
        self.chemin = self.astar(dep, arr)
        return bool(self.chemin)

    # ------------------------------------------------------------------
    # États
    # ------------------------------------------------------------------
    def changer_etat(self, etat):
        if etat == self.etat:
            return
        self.etat = etat
        self.pause = 0.0
        if etat == TRAQUE and self.cri_cooldown <= 0:
            self.audio.jouer("cri", position=self.position + Vec3(0, 2, 0), volume=0.7, portee=40)
            self.cri_cooldown = 25.0

    def cacher(self, duree):
        """La créature disparaît dans les conduits pendant `duree` secondes."""
        self.cachee = True
        self.temps_cachee = duree
        self.visible = False
        self.chemin = []

    def reapparaitre(self, case):
        self.cachee = False
        self.visible = True
        self.position = Vec3(case[0] + 0.5, 0, case[1] + 0.5)
        self.changer_etat(ERRANCE)
        self.chemin = []
        self.audio.jouer("coup_conduit", position=self.position + Vec3(0, 0.5, 0), volume=0.8)

    def enqueter(self, x, z):
        if self.cachee or self.etat in (TRAQUE, RETRAITE):
            return
        if self.aller_vers(x, z):
            self.changer_etat(ENQUETE)
            self.cible_enquete = Vec3(x, 0, z)

    def _vitesse(self):
        v = {ERRANCE: C.CREATURE_VITESSE_ERRANCE, ENQUETE: C.CREATURE_VITESSE_ENQUETE,
             TRAQUE: C.CREATURE_VITESSE_TRAQUE, RECHERCHE: C.CREATURE_VITESSE_ENQUETE * 0.85,
             RETRAITE: C.CREATURE_VITESSE_ENQUETE}[self.etat]
        if self.pont.t(int(math.floor(self.x)), int(math.floor(self.z))) in (CONDUIT, GRILLE):
            v *= C.CREATURE_MULT_CONDUIT
        return v * self.agressivite

    def dans_conduit(self):
        return self.pont.t(int(math.floor(self.x)), int(math.floor(self.z))) in (CONDUIT, GRILLE)

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------
    def peut_voir(self, joueur):
        if joueur.cache is not None or self.cachee:
            return False
        dx, dz = joueur.x - self.x, joueur.z - self.z
        d = math.hypot(dx, dz)
        portee = C.CREATURE_PORTEE_VUE if (joueur.lampe_allumee and joueur.batterie > 0) else C.CREATURE_PORTEE_VUE_NUIT
        if joueur.accroupi:
            portee *= 0.7
        portee *= 1.0 + (self.agressivite - 1.0) * 1.2
        if d > portee:
            return False
        if d > 2.2:
            a = math.radians(self.rotation_y)
            fx, fz = math.sin(a), math.cos(a)
            if (dx * fx + dz * fz) / d < math.cos(math.radians(C.CREATURE_ANGLE_VISION / 2)):
                return False
        return self.monde.ligne_de_vue(self.x, self.z, joueur.x, joueur.z)

    def entendre(self):
        """Choisit le bruit le plus fort parmi ceux émis cette image."""
        meilleur, force = None, 0.0
        for (x, z, r) in self.monde.bruits:
            d = math.hypot(x - self.x, z - self.z)
            r2 = r * (1.0 + (self.agressivite - 1.0) * 1.5)
            if d < r2 and (r2 - d) > force:
                meilleur, force = (x, z), r2 - d
        return meilleur

    # ------------------------------------------------------------------
    # Mise à jour
    # ------------------------------------------------------------------
    def tick(self, dt, joueur):
        """Renvoie True si la créature a attrapé le joueur."""
        self.cri_cooldown -= dt
        if self.cachee:
            self.temps_cachee -= dt
            self.souffle.volume = 0.0
            return False

        self.voit = self.peut_voir(joueur)
        if self.voit:
            self.dernier_vu = Vec3(joueur.x, 0, joueur.z)
            self.sans_voir = 0.0
            self.vu_recemment = 1.2
            if self.etat != RETRAITE:
                self.changer_etat(TRAQUE)
        else:
            self.sans_voir += dt
            self.vu_recemment -= dt
            # le joueur s'est caché sous ses yeux : elle sait dans quel casier
            if joueur.cache is not None and self.vu_recemment > 0 and self.etat == TRAQUE and self.casier_cible is None:
                self.casier_cible = joueur.cache

        if self.etat in (ERRANCE, RECHERCHE, ENQUETE):
            bruit = self.entendre()
            if bruit is not None:
                self.enqueter(*bruit)

        e = self.etat
        if e == TRAQUE:
            self._traquer(dt, joueur)
        elif e == ENQUETE:
            if not self.chemin:
                self._commencer_recherche(self.x, self.z)
        elif e == RECHERCHE:
            self._rechercher(dt, joueur)
        elif e == ERRANCE:
            self._errer(dt)
        elif e == RETRAITE:
            if not self.chemin:
                if self.dans_conduit():
                    self.cacher(self.rng.uniform(*C.DIRECTEUR_RETRAITE))
                    return False
                self._fuir_vers_conduit()

        self._avancer(dt, joueur)
        self._animer(dt)
        self._sons(dt, joueur)

        # attrape le joueur
        if joueur.cache is None:
            d = math.hypot(joueur.x - self.x, joueur.z - self.z)
            if d < C.CREATURE_DISTANCE_MORT:
                return True
        elif self.casier_cible is not None and self.casier_cible is joueur.cache:
            s = joueur.cache.sortie
            if math.hypot(s.x - self.x, s.z - self.z) < 0.9:
                return True
        return False

    def _traquer(self, dt, joueur):
        if self.casier_cible is not None:
            s = self.casier_cible.sortie
            if not self.chemin or self.repath <= 0:
                self.repath = 1.0
                self.aller_vers(s.x, s.z)
            self.repath -= dt
            if joueur.cache is None:
                self.casier_cible = None
            return
        if self.sans_voir > C.CREATURE_OUBLI:
            if self.dernier_vu is not None:
                self._commencer_recherche(self.dernier_vu.x, self.dernier_vu.z)
            else:
                self.changer_etat(ERRANCE)
            return
        self.repath -= dt
        if self.voit and math.hypot(joueur.x - self.x, joueur.z - self.z) < 5.0 and \
                self.dans_conduit() == (joueur.dans_conduit):
            self.chemin = []   # poursuite directe
            return
        if self.repath <= 0 or not self.chemin:
            self.repath = 0.45
            cible = self.dernier_vu or Vec3(joueur.x, 0, joueur.z)
            self.aller_vers(cible.x, cible.z)

    def _commencer_recherche(self, x, z):
        self.changer_etat(RECHERCHE)
        centre = self.case_proche(x, z) or self.case_proche(self.x, self.z)
        pts = []
        if centre:
            cands = [c for c in self.voisins if abs(c[0] - centre[0]) + abs(c[1] - centre[1]) < 8]
            self.rng.shuffle(cands)
            pts = cands[:self.rng.randint(3, 5)]
        self.points_recherche = pts
        self.chemin = []
        self.pause = self.rng.uniform(1.0, 2.5)

    def _rechercher(self, dt, joueur):
        if self.chemin:
            return
        if self.pause > 0:
            self.pause -= dt
            return
        # renifle un casier proche où le joueur se cache (sans l'avoir vu y entrer)
        if joueur.cache is not None and self.renifle <= 0:
            s = joueur.cache.sortie
            if math.hypot(s.x - self.x, s.z - self.z) < 5 and self.rng.random() < 0.5:
                self.aller_vers(s.x, s.z)
                self.renifle = 4.0
                self.pause = 3.5
                return
        self.renifle -= dt
        if not self.points_recherche:
            self.changer_etat(ERRANCE)
            return
        c = self.points_recherche.pop()
        self.aller_vers(c[0] + 0.5, c[1] + 0.5)
        self.pause = self.rng.uniform(0.8, 2.5)

    def _errer(self, dt):
        if self.chemin:
            return
        if self.pause > 0:
            self.pause -= dt
            return
        if self.rng.random() < 0.45 and self.cases_conduit:
            c = self.rng.choice(self.cases_conduit)
        else:
            s = self.rng.choice(self.pont.salles)
            c = self.case_proche(s.x + self.rng.randint(0, s.l - 1) + 0.5, s.z + self.rng.randint(0, s.p - 1) + 0.5)
            if c is None:
                c = self.rng.choice(self.cases_sol)
        self.aller_vers(c[0] + 0.5, c[1] + 0.5)
        self.pause = self.rng.uniform(1.5, 4.5)

    def _fuir_vers_conduit(self):
        """Parcours en largeur jusqu'au conduit le plus proche (en distance de marche)."""
        p = self.pont
        dep = self.case_proche(self.x, self.z)
        if dep is None or not self.cases_conduit:
            self.cacher(10)
            return
        parent = {dep: None}
        file = [dep]
        k = 0
        while k < len(file):
            c = file[k]
            k += 1
            if p.type[c] == CONDUIT:
                chemin = []
                while c != dep:
                    chemin.append(c)
                    c = parent[c]
                self.chemin = chemin[::-1]
                return
            for n in self.voisins.get(c, ()):
                if n in parent:
                    continue
                if p.type[n] == PORTE and p.portes[p.porte_id[n]].verrou is not None:
                    continue
                parent[n] = c
                file.append(n)
        self.cacher(10)

    # ------------------------------------------------------------------
    def _avancer(self, dt, joueur):
        v = self._vitesse()
        cible = None
        if self.chemin:
            c = self.chemin[0]
            p = self.pont
            # ouvre les grilles sur son passage, attend l'ouverture des portes
            if p.type[c] == GRILLE:
                g = self.monde.grilles.get(int(p.grille_id[c]))
                if g and not g.ouverte:
                    g.ouvrir(par_creature=True)
            if p.type[c] == PORTE:
                porte = self.monde.portes[p.porte_id[c]]
                if porte.porte.verrou is not None:
                    self.chemin = []
                    return
                if porte.ouverture < 0.6:
                    v *= 0.15
            cible = Vec3(c[0] + 0.5, 0, c[1] + 0.5)
        elif self.etat == TRAQUE and self.voit:
            cible = Vec3(joueur.x, 0, joueur.z)
        if cible is None:
            self.vitesse_actuelle = lerp(self.vitesse_actuelle, 0, min(1, dt * 6))
            return
        d = cible - self.position
        d.y = 0
        dist = d.length()
        if dist < 0.12 and self.chemin:
            self.chemin.pop(0)
            return
        pas = min(dist, v * dt)
        if dist > 1e-4:
            self.position += d / dist * pas
            ang = math.degrees(math.atan2(d.x, d.z))
            diff = (ang - self.rotation_y + 180) % 360 - 180
            self.rotation_y += diff * min(1, dt * 8)
        self.vitesse_actuelle = pas / max(dt, 1e-5)
        # anti-blocage
        self.bloque_timer += dt
        if self.bloque_timer > 2.5:
            if (self.position - self.derniere_pos).length() < 0.4:
                self.chemin = []
                self.pause = 0
                if self.etat == ENQUETE:
                    self.changer_etat(ERRANCE)
            self.derniere_pos = Vec3(self.position)
            self.bloque_timer = 0.0

    def _animer(self, dt):
        conduit = self.dans_conduit()
        # posture rampante dans les conduits
        cible_rx = 78 if conduit else (12 if self.etat == TRAQUE else 0)
        self.corps.rotation_x = lerp(self.corps.rotation_x, cible_rx, min(1, dt * 5))
        self.corps.y = lerp(self.corps.y, 0.12 if conduit else 0.0, min(1, dt * 5))
        v = self.vitesse_actuelle
        self.phase_marche += dt * (2.5 + v * 1.6) * (1 if v > 0.1 else 0.15)
        amp = min(1.0, v / 3.0)
        s = math.sin(self.phase_marche)
        for k, (h, g) in enumerate(zip(self.hanches, self.genoux)):
            sg = s if k == 0 else -s
            h.rotation_x = sg * 32 * amp + (-70 if conduit else 0)
            g.rotation_x = 35 + max(0, sg) * 30 * amp
        for k, (e, c) in enumerate(zip(self.epaules, self.coudes)):
            sg = -s if k == 0 else s
            e.rotation_x = sg * 25 * amp + (-80 if conduit else (-35 if self.etat == TRAQUE else 0))
            c.rotation_x = -25 - abs(sg) * 20 * amp
        # tics nerveux de la tête
        self.tic_tete -= dt
        if self.tic_tete <= 0:
            self.tic_tete = self.rng.uniform(0.15, 2.5)
            self.tete.rotation_z = self.rng.uniform(-35, 35)
            self.tete.rotation_y = self.rng.uniform(-30, 30)
        else:
            self.tete.rotation_z = lerp(self.tete.rotation_z, 0, min(1, dt * 1.5))
        self.cou.rotation_x = -60 if conduit else 10

    def _sons(self, dt, joueur):
        conduit = self.dans_conduit()
        self.souffle.position = self.position + Vec3(0, 1.0 if conduit else 1.9, 0)
        d = math.hypot(joueur.x - self.x, joueur.z - self.z)
        self.souffle.volume = 0.9 if d < 14 else 0.0
        self.son_timer -= dt
        if self.son_timer <= 0:
            if conduit:
                self.son_timer = self.rng.uniform(0.8, 2.2)
                self.audio.jouer("grattement", position=self.position + Vec3(0, 0.5, 0), volume=0.9, portee=26)
                if self.rng.random() < 0.25:
                    self.audio.jouer("coup_conduit", position=self.position, volume=0.6, portee=30)
            elif self.vitesse_actuelle > 0.5:
                self.son_timer = 1.6 / max(1.0, self.vitesse_actuelle)
                self.audio.jouer("pas_%d" % self.rng.randint(1, 4), position=self.position, volume=0.9,
                                 pitch=0.55, portee=22)
            else:
                self.son_timer = 0.5


class Directrice:
    """Directrice d'IA : dose la pression exercée sur le joueur."""

    def __init__(self, creature, monde, audio):
        self.creature = creature
        self.monde = monde
        self.audio = audio
        self.rng = random.Random(monde.vaisseau.seed + 7)
        self.calme = 0.0
        self.traque = 0.0
        self.debut = C.CREATURE_DELAI_DEPART
        self.courant = False
        self.frayeur = self.rng.uniform(10, 25)
        self.tension = 0.0              # 0..1 (utilisé pour le rythme cardiaque / vibrations)

    def retablir_courant(self, pos_machines):
        """Le vacarme du réacteur attire la créature, qui devient plus agressive."""
        self.courant = True
        c = self.creature
        c.agressivite = C.CREATURE_MULT_COURANT
        if c.cachee:
            self._reapparaitre_pres(pos_machines, 12, 26)
        c.enqueter(pos_machines.x, pos_machines.z)

    def _reapparaitre_pres(self, pos, dmin, dmax):
        c = self.creature
        cands = [k for k in c.cases_conduit if dmin < math.hypot(k[0] - pos.x, k[1] - pos.z) < dmax]
        if not cands:
            cands = c.cases_conduit or c.cases_sol
        c.reapparaitre(self.rng.choice(cands))

    def tick(self, dt, joueur):
        c = self.creature
        d = math.hypot(joueur.x - c.x, joueur.z - c.z)
        # tension (pour le cœur et les vibrations)
        cible = 0.0
        if not c.cachee:
            cible = max(0.0, 1 - d / 16) if d < 16 else 0.0
            if c.etat == TRAQUE:
                cible = max(cible, 0.6)
        self.tension = lerp(self.tension, cible, min(1, dt * 2))

        # frayeurs d'ambiance : grincements du vaisseau autour du joueur
        self.frayeur -= dt
        if self.frayeur <= 0:
            self.frayeur = self.rng.uniform(12, 35)
            ang = self.rng.uniform(0, 2 * math.pi)
            pos = Vec3(joueur.x + math.cos(ang) * 8, 2.5, joueur.z + math.sin(ang) * 8)
            self.audio.jouer("grincement_%d" % self.rng.randint(1, 3), position=pos, volume=0.8)

        # début de partie : la créature est encore dans les conduits
        if self.debut > 0:
            self.debut -= dt
            if self.debut <= 0:
                self._reapparaitre_pres(joueur.position, 25, 60)
            return

        if c.cachee:
            if c.temps_cachee <= 0:
                # sortie : plus près du joueur si la pression est faible
                if self.calme > C.DIRECTEUR_CALME_MAX * 0.5:
                    self._reapparaitre_pres(joueur.position, 10, 22)
                else:
                    self._reapparaitre_pres(joueur.position, 20, 45)
            return

        if c.etat == TRAQUE:
            self.traque += dt
            self.calme = 0.0
            if self.traque > C.DIRECTEUR_TRAQUE_MAX and not c.voit:
                c.changer_etat(RETRAITE)
                c.chemin = []
                self.traque = 0.0
        else:
            self.traque = max(0.0, self.traque - dt * 0.5)
            if d > 18 and c.etat != ENQUETE:
                self.calme += dt
            else:
                self.calme = max(0.0, self.calme - dt * 2)
        limite = C.DIRECTEUR_CALME_MAX * (0.6 if self.courant else 1.0)
        if self.calme > limite:
            # le joueur est tranquille depuis trop longtemps : la créature se rapproche
            self.calme = limite * 0.3
            ang = self.rng.uniform(0, 2 * math.pi)
            r = self.rng.uniform(3, 8)
            c.enqueter(joueur.x + math.cos(ang) * r, joueur.z + math.sin(ang) * r)
