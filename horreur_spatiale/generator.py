# -*- coding: utf-8 -*-
"""
generator.py — Génération procédurale du vaisseau sur une grille 2D.

Étapes :
  1. placement des salles sans chevauchement (salles obligatoires de tailles différentes) ;
  2. graphe de connexion : arbre couvrant minimal + quelques boucles ;
  3. couloirs étroits creusés par A* (coudes, fusion avec les couloirs existants) ;
  4. murs, portes, hublots / baies vitrées sur la coque extérieure ;
  5. réseau secondaire de conduits d'aération avec grilles d'accès ;
  6. validation : la progression (machines -> commandement -> hangar) doit être possible.

L'architecture est prévue pour plusieurs ponts (classe Pont avec une altitude),
mais un seul pont est généré pour l'instant.
"""
import heapq
import math
import random

import numpy as np

import config as C

# Types de cases
VIDE, MUR, SOL, PORTE, CONDUIT, GRILLE = range(6)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIRS8 = DIRS + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def connectes(a, b):
    """Deux types de cases voisines communiquent-ils (pas de mur entre eux) ?"""
    sol = (SOL, PORTE)
    if a in sol and b in sol:
        return True
    if (a == SOL and b == GRILLE) or (a == GRILLE and b == SOL):
        return True
    reseau = (CONDUIT, GRILLE)
    return a in reseau and b in reseau


class Salle:
    def __init__(self, id_, type_, x, z, l, p, h):
        self.id = id_
        self.type = type_
        self.nom = C.SALLES[type_]["nom"]
        self.x, self.z, self.l, self.p, self.h = x, z, l, p, h
        self.portes = []
        self.grilles = []

    @property
    def centre(self):
        return (self.x + self.l / 2.0, self.z + self.p / 2.0)

    def contient(self, i, j):
        return self.x <= i < self.x + self.l and self.z <= j < self.z + self.p

    def distance(self, x, z):
        """Distance d'un point au rectangle de la salle (0 si à l'intérieur)."""
        dx = max(self.x - x, 0, x - (self.x + self.l))
        dz = max(self.z - z, 0, z - (self.z + self.p))
        return math.hypot(dx, dz)


class Porte:
    def __init__(self, id_, cases, normale, salle_id):
        self.id = id_
        self.cases = cases              # deux cases (i, j)
        self.normale = normale          # direction vers l'extérieur de la salle
        self.salle_id = salle_id
        self.verrou = None              # None, "courant" ou "code"

    @property
    def centre(self):
        xs = [c[0] + 0.5 for c in self.cases]
        zs = [c[1] + 0.5 for c in self.cases]
        return (sum(xs) / len(xs), sum(zs) / len(zs))

    @property
    def axe(self):
        """'x' si les deux cases sont alignées selon x (la porte coulisse en x)."""
        return "x" if self.cases[0][0] != self.cases[1][0] else "z"


class Grille:
    def __init__(self, id_, case, vers_sol, salle_id):
        self.id = id_
        self.case = case
        self.vers_sol = vers_sol        # direction de la grille vers la case de sol qu'elle dessert
        self.salle_id = salle_id

    @property
    def case_sol(self):
        return (self.case[0] + self.vers_sol[0], self.case[1] + self.vers_sol[1])


class Pont:
    """Un pont (étage) du vaisseau."""

    def __init__(self, largeur, profondeur, altitude=0.0):
        self.largeur, self.profondeur = largeur, profondeur
        self.altitude = altitude
        self.type = np.zeros((largeur, profondeur), dtype=np.int8)
        self.hauteur = np.zeros((largeur, profondeur), dtype=np.float32)
        self.salle = np.full((largeur, profondeur), -1, dtype=np.int16)
        self.porte_id = np.full((largeur, profondeur), -1, dtype=np.int16)
        self.grille_id = np.full((largeur, profondeur), -1, dtype=np.int16)
        self.salles = []
        self.portes = []
        self.grilles = []
        self.fenetres = {}              # (i, j, dx, dz) -> (allège, linteau, marge)

    def dans(self, i, j):
        return 0 <= i < self.largeur and 0 <= j < self.profondeur

    def t(self, i, j):
        return int(self.type[i, j]) if self.dans(i, j) else VIDE

    def salle_de_type(self, type_):
        return [s for s in self.salles if s.type == type_]


class Vaisseau:
    def __init__(self, seed):
        self.seed = seed
        self.ponts = []
        self.apparition = (0, 0)        # case de départ du joueur
        self.salle_depart = None

    @property
    def pont(self):
        return self.ponts[0]


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------
def generer_vaisseau(seed=None):
    """Génère un vaisseau jouable. Si une tentative échoue, on dérive la seed et on recommence."""
    if seed is None:
        seed = random.randrange(1, 10 ** 6)
    for essai in range(40):
        s = seed + essai * 7919
        v = _essayer(s)
        if v is not None:
            v.seed = seed
            return v
    raise RuntimeError("Impossible de générer un vaisseau valide")


def _essayer(seed):
    rng = random.Random(seed)
    W, H = C.GRILLE_LARGEUR, C.GRILLE_PROFONDEUR
    pont = Pont(W, H)
    if not _placer_salles(pont, rng):
        return None
    for s in pont.salles:
        pont.type[s.x:s.x + s.l, s.z:s.z + s.p] = SOL
        pont.salle[s.x:s.x + s.l, s.z:s.z + s.p] = s.id
        pont.hauteur[s.x:s.x + s.l, s.z:s.z + s.p] = s.h

    aretes = _graphe(pont.salles, rng)
    bruit = np.array([[rng.random() for _ in range(H)] for _ in range(W)], dtype=np.float32)
    for a, b in aretes:
        _creuser_couloir(pont, pont.salles[a], pont.salles[b], rng, bruit)
    _nettoyer_portes(pont)

    _poser_murs(pont)
    _verrous(pont)
    if not _valider(pont):
        return None
    _serrures(pont, rng)
    _fenetres(pont, rng)
    _conduits(pont, rng)

    v = Vaisseau(seed)
    v.ponts.append(pont)
    # Le joueur se réveille dans la chambre la plus éloignée du hangar
    hangar = pont.salle_de_type("hangar")[0]
    chambres = pont.salle_de_type("chambre")
    depart = max(chambres, key=lambda s: math.dist(s.centre, hangar.centre))
    v.salle_depart = depart.id
    v.apparition = (depart.x + depart.l // 2, depart.z + depart.p // 2)
    return v


def _placer_salles(pont, rng):
    """Place les salles une à une (les plus grandes d'abord) en restant compact."""
    liste = []
    for type_, spec in C.SALLES.items():
        for _ in range(spec["n"]):
            liste.append((type_, spec))
    liste.sort(key=lambda e: -(e[1]["l"][1] * e[1]["p"][1]))
    m = C.MARGE_SALLES
    W, H = pont.largeur, pont.profondeur
    for type_, spec in liste:
        candidats = []
        for _ in range(500):
            l = rng.randint(*spec["l"])
            p = rng.randint(*spec["p"])
            if type_ not in ("hangar", "machines") and rng.random() < 0.5:
                l, p = p, l
            x = rng.randint(4, W - l - 4)
            z = rng.randint(4, H - p - 4)
            libre = all(not (x < s.x + s.l + m and s.x < x + l + m and
                             z < s.z + s.p + m and s.z < z + p + m) for s in pont.salles)
            if libre:
                candidats.append((x, z, l, p))
            if len(candidats) >= 40:
                break
        if not candidats:
            return False
        if pont.salles:
            cx = sum(s.centre[0] for s in pont.salles) / len(pont.salles)
            cz = sum(s.centre[1] for s in pont.salles) / len(pont.salles)
            candidats.sort(key=lambda c: math.hypot(c[0] + c[2] / 2 - cx, c[1] + c[3] / 2 - cz))
            x, z, l, p = candidats[rng.randint(0, min(3, len(candidats) - 1))]
        else:
            x, z, l, p = candidats[0]
            x, z = W // 2 - l // 2 + rng.randint(-6, 6), H // 2 - p // 2 + rng.randint(-6, 6)
        pont.salles.append(Salle(len(pont.salles), type_, x, z, l, p, spec["h"]))
    return True


def _graphe(salles, rng):
    """Arbre couvrant minimal (Prim) + quelques arêtes courtes supplémentaires (boucles)."""
    n = len(salles)
    dist = [[math.dist(a.centre, b.centre) for b in salles] for a in salles]
    dans_arbre = {0}
    aretes = []
    while len(dans_arbre) < n:
        meilleur = None
        for a in dans_arbre:
            for b in range(n):
                if b not in dans_arbre and (meilleur is None or dist[a][b] < meilleur[0]):
                    meilleur = (dist[a][b], a, b)
        _, a, b = meilleur
        aretes.append((a, b))
        dans_arbre.add(b)
    maxi = max(dist[a][b] for a, b in aretes)
    restantes = sorted((dist[a][b], a, b) for a in range(n) for b in range(a + 1, n)
                       if (a, b) not in aretes and (b, a) not in aretes and dist[a][b] < maxi * 1.4)
    nb = max(2, int(round(n * C.RATIO_BOUCLES)))
    for d, a, b in restantes[:nb * 2]:
        if nb <= 0:
            break
        if rng.random() < 0.7:
            aretes.append((a, b))
            nb -= 1
    return aretes


def _choisir_porte(pont, salle, cible):
    """Choisit (ou réutilise) une porte de `salle` sur le côté qui fait face à `cible`."""
    cx, cz = salle.centre
    dx, dz = cible[0] - cx, cible[1] - cz
    # côté principal selon la direction dominante (normalisée par la taille de la salle)
    if abs(dx) / salle.l > abs(dz) / salle.p:
        normale = (1, 0) if dx > 0 else (-1, 0)
    else:
        normale = (0, 1) if dz > 0 else (0, -1)
    # réutilise une porte existante du même côté
    for pid in salle.portes:
        p = pont.portes[pid]
        if p.normale == normale:
            return p
    if normale[0] != 0:
        x = salle.x + salle.l if normale[0] > 0 else salle.x - 1
        zc = int(min(max(cible[1] - 1, salle.z + 1), salle.z + salle.p - 3))
        cases = [(x, zc), (x, zc + 1)]
    else:
        z = salle.z + salle.p if normale[1] > 0 else salle.z - 1
        xc = int(min(max(cible[0] - 1, salle.x + 1), salle.x + salle.l - 3))
        cases = [(xc, z), (xc + 1, z)]
    porte = Porte(len(pont.portes), cases, normale, salle.id)
    pont.portes.append(porte)
    salle.portes.append(porte.id)
    return porte


def _depart_couloir(porte, w):
    """Case d'ancrage du pinceau de couloir juste devant la porte."""
    (i0, j0) = min(porte.cases)
    nx, nz = porte.normale
    if nx > 0:
        return (i0 + 1, j0)
    if nx < 0:
        return (i0 - w, j0)
    if nz > 0:
        return (i0, j0 + 1)
    return (i0, j0 - w)


def _creuser_couloir(pont, sa, sb, rng, bruit):
    w = rng.choice(C.LARGEURS_COULOIR)
    pa = _choisir_porte(pont, sa, sb.centre)
    pb = _choisir_porte(pont, sb, sa.centre)
    depart, arrivee = _depart_couloir(pa, w), _depart_couloir(pb, w)
    W, H = pont.largeur, pont.profondeur
    # zones interdites : le pinceau ne doit jamais toucher l'anneau de mur d'une salle
    interdit = np.zeros((W, H), dtype=bool)
    for s in pont.salles:
        interdit[max(0, s.x - w):s.x + s.l + 1, max(0, s.z - w):s.z + s.p + 1] = True
    interdit[:1, :] = interdit[W - w - 1:, :] = True
    interdit[:, :1] = interdit[:, H - w - 1:] = True
    chemin = _astar_couloir(pont, depart, arrivee, interdit, bruit)
    if chemin is None:
        return False
    for (i, j) in chemin:
        for di in range(w):
            for dj in range(w):
                x, z = i + di, j + dj
                if pont.type[x, z] != SOL:
                    pont.type[x, z] = SOL
                    pont.salle[x, z] = -1
                    pont.hauteur[x, z] = C.HAUTEUR_COULOIR
    for p in (pa, pb):
        for (x, z) in p.cases:
            pont.type[x, z] = PORTE
            pont.porte_id[x, z] = p.id
            pont.hauteur[x, z] = C.HAUTEUR_PORTE
    return True


def _astar_couloir(pont, depart, arrivee, interdit, bruit):
    """A* avec pénalité de virage : produit des couloirs droits avec quelques coudes."""
    W, H = pont.largeur, pont.profondeur
    ouvert = [(0.0, 0.0, depart, -1)]
    meilleur = {(depart, -1): 0.0}
    parent = {}
    fin_etat = None
    while ouvert:
        f, g, case, d = heapq.heappop(ouvert)
        if case == arrivee:
            fin_etat = (case, d)
            break
        if g > meilleur.get((case, d), 1e18):
            continue
        for k, (dx, dz) in enumerate(DIRS):
            n = (case[0] + dx, case[1] + dz)
            if not (0 <= n[0] < W and 0 <= n[1] < H):
                continue
            if interdit[n] and n != arrivee:
                continue
            existant = pont.type[n] == SOL and pont.salle[n] == -1
            cout = (0.35 if existant else 1.0) + float(bruit[n]) * 0.6
            if d != -1 and d != k:
                cout += 3.0
            ng = g + cout
            if ng < meilleur.get((n, k), 1e18):
                meilleur[(n, k)] = ng
                parent[(n, k)] = (case, d)
                h = (abs(n[0] - arrivee[0]) + abs(n[1] - arrivee[1])) * 0.35
                heapq.heappush(ouvert, (ng + h, ng, n, k))
    if fin_etat is None:
        return None
    chemin = []
    etat = fin_etat
    while etat in parent or etat[0] == depart:
        chemin.append(etat[0])
        if etat[0] == depart:
            break
        etat = parent[etat]
    return chemin[::-1]


def _nettoyer_portes(pont):
    """Supprime les portes dont le couloir n'a pas pu être creusé, puis renumérote."""
    gardees = [p for p in pont.portes if pont.type[p.cases[0]] == PORTE]
    pont.porte_id[:] = -1
    for s in pont.salles:
        s.portes = []
    for nouvel_id, p in enumerate(gardees):
        p.id = nouvel_id
        for c in p.cases:
            pont.porte_id[c] = nouvel_id
        pont.salles[p.salle_id].portes.append(nouvel_id)
    pont.portes = gardees


def _poser_murs(pont):
    """Toute case vide voisine (8 directions) d'un sol ou d'une porte devient un mur."""
    sol = np.isin(pont.type, (SOL, PORTE))
    voisin = np.zeros_like(sol)
    W, H = sol.shape
    for dx, dz in DIRS8:
        decal = np.zeros_like(sol)
        xs0, xs1 = max(0, dx), W + min(0, dx)
        zs0, zs1 = max(0, dz), H + min(0, dz)
        decal[xs0 - dx:xs1 - dx, zs0 - dz:zs1 - dz] = sol[xs0:xs1, zs0:zs1]
        voisin |= decal
    pont.type[(pont.type == VIDE) & voisin] = MUR


def _verrous(pont):
    """Commandement : verrouillé sans courant. Hangar : code d'accès requis."""
    for p in pont.portes:
        t = pont.salles[p.salle_id].type
        if t == "commandement":
            p.verrou = "courant"
        elif t == "hangar":
            p.verrou = "code"


def _serrures(pont, rng):
    """Réserves (et parfois l'infirmerie) : serrure mécanique à crocheter avec un couteau.
    Une salle n'est verrouillée que si cela ne bloque jamais la progression."""
    candidates = [s for s in pont.salles if s.type == "stockage"]
    candidates += [s for s in pont.salles if s.type in ("infirmerie", "salle_a_manger") and rng.random() < 0.4]
    rng.shuffle(candidates)
    for s in candidates:
        for pid in s.portes:
            pont.portes[pid].verrou = "crochet"
        if not _valider(pont):
            for pid in s.portes:
                pont.portes[pid].verrou = None


def _atteignables(pont, depart, verrous_ouverts):
    """Parcours en largeur des cases accessibles à pied (sans les conduits)."""
    vus = np.zeros(pont.type.shape, dtype=bool)
    pile = [depart]
    vus[depart] = True
    while pile:
        i, j = pile.pop()
        for dx, dz in DIRS:
            n = (i + dx, j + dz)
            if not pont.dans(*n) or vus[n]:
                continue
            t = pont.type[n]
            if t == PORTE:
                v = pont.portes[pont.porte_id[n]].verrou
                if v is not None and v not in verrous_ouverts:
                    continue
            elif t != SOL:
                continue
            vus[n] = True
            pile.append(n)
    return vus


def _valider(pont):
    """Vérifie que toutes les salles sont reliées et que la progression est possible."""
    chambres = pont.salle_de_type("chambre")
    if not chambres:
        return False
    s0 = chambres[0]
    depart = (s0.x + 1, s0.z + 1)
    tout = _atteignables(pont, depart, ("courant", "code", "crochet"))
    for s in pont.salles:
        if not tout[s.x + 1, s.z + 1] or not s.portes:
            return False
    # sans aucun verrou ouvert : machines atteignable depuis toutes les chambres
    libre = _atteignables(pont, depart, ())
    m = pont.salle_de_type("machines")[0]
    if not libre[m.x + 1, m.z + 1]:
        return False
    for c in chambres:
        if not libre[c.x + 1, c.z + 1]:
            return False
    # les serrures à crocheter restent optionnelles : jamais nécessaires pour finir
    avec_courant = _atteignables(pont, depart, ("courant",))
    cmd = pont.salle_de_type("commandement")[0]
    if not avec_courant[cmd.x + 1, cmd.z + 1]:
        return False
    avec_code = _atteignables(pont, depart, ("courant", "code"))
    h = pont.salle_de_type("hangar")[0]
    return bool(avec_code[h.x + 1, h.z + 1])


def _fenetres(pont, rng):
    """Hublots et baies vitrées sur les murs de la coque (mur d'une case avec le vide derrière)."""
    W, H = pont.largeur, pont.profondeur
    for i in range(W):
        for j in range(H):
            if pont.type[i, j] != SOL:
                continue
            sid = int(pont.salle[i, j])
            type_ = pont.salles[sid].type if sid >= 0 else "couloir"
            h = float(pont.hauteur[i, j])
            for dx, dz in DIRS:
                wi, wj = i + dx, j + dz
                if pont.t(wi, wj) != MUR or pont.t(i + 2 * dx, j + 2 * dz) != VIDE:
                    continue
                # un mur de coque ne doit pas border une porte (montants)
                if any(pont.t(wi + a, wj + b) == PORTE for a, b in DIRS):
                    continue
                le_long = j if dx != 0 else i
                style = None
                if type_ == "commandement":
                    style = (0.55, h - 0.55, 0.035)
                elif type_ == "hangar":
                    style = (1.3, 7.5, 0.06)
                elif type_ == "salle_a_manger":
                    style = (0.9, 2.5, 0.07)
                elif type_ == "machines":
                    style = (1.2, 1.9, 0.28) if le_long % 5 == 0 else None
                elif type_ == "couloir":
                    style = (1.05, 2.05, 0.22) if le_long % 4 == 0 else None
                else:
                    style = (1.1, 1.9, 0.25) if le_long % 3 == 0 else None
                if style:
                    pont.fenetres[(wi, wj, dx, dz)] = style


def _conduits(pont, rng):
    """Réseau secondaire de conduits d'aération reliant des grilles d'accès."""
    W, H = pont.largeur, pont.profondeur
    murs_fenetre = {(k[0], k[1]) for k in pont.fenetres}

    def candidates(filtre):
        res = []
        for i in range(1, W - 1):
            for j in range(1, H - 1):
                if pont.type[i, j] != MUR or (i, j) in murs_fenetre:
                    continue
                voisins_sol = [(dx, dz) for dx, dz in DIRS if pont.t(i + dx, j + dz) in (SOL, PORTE)]
                if len(voisins_sol) != 1:
                    continue
                dx, dz = voisins_sol[0]
                if pont.t(i + dx, j + dz) != SOL:
                    continue
                if any(pont.t(i + a, j + b) == PORTE for a, b in DIRS8):
                    continue
                if pont.t(i - dx, j - dz) not in (MUR, VIDE):
                    continue
                # les deux voisins latéraux doivent être des murs (pas un coin)
                if pont.t(i + dz, j + dx) != MUR or pont.t(i - dz, j - dx) != MUR:
                    continue
                sid = int(pont.salle[i + dx, j + dz])
                if filtre(sid):
                    res.append(((i, j), (dx, dz), sid))
        return res

    grilles = []
    for s in pont.salles:
        cands = candidates(lambda sid, s=s: sid == s.id)
        rng.shuffle(cands)
        nb = 2 if s.type in ("hangar", "machines") else 1
        pris = []
        for c in cands:
            if all(abs(c[0][0] - p[0][0]) + abs(c[0][1] - p[0][1]) > 6 for p in pris):
                pris.append(c)
            if len(pris) >= nb:
                break
        grilles += pris
    cands = candidates(lambda sid: sid == -1)
    rng.shuffle(cands)
    grilles += cands[:C.NB_GRILLES_COULOIR]

    for (case, vers, sid) in grilles:
        g = Grille(len(pont.grilles), case, vers, sid)
        pont.grilles.append(g)
        pont.type[case] = GRILLE
        pont.grille_id[case] = g.id
        pont.hauteur[case] = C.HAUTEUR_CONDUIT
        if sid >= 0:
            pont.salles[sid].grilles.append(g.id)

    # arbre couvrant sur les grilles + 2 liaisons supplémentaires
    n = len(pont.grilles)
    if n < 2:
        return
    pos = [g.case for g in pont.grilles]
    d = lambda a, b: abs(pos[a][0] - pos[b][0]) + abs(pos[a][1] - pos[b][1])
    arbre, liens = {0}, []
    while len(arbre) < n:
        a, b = min(((a, b) for a in arbre for b in range(n) if b not in arbre), key=lambda e: d(*e))
        liens.append((a, b))
        arbre.add(b)
    autres = sorted(((a, b) for a in range(n) for b in range(a + 1, n) if (a, b) not in liens and (b, a) not in liens),
                    key=lambda e: d(*e))
    liens += autres[:2]
    for a, b in liens:
        _creuser_conduit(pont, pont.grilles[a], pont.grilles[b], murs_fenetre)
    # une grille non reliée redevient un mur
    for g in pont.grilles:
        if not any(pont.t(g.case[0] + dx, g.case[1] + dz) in (CONDUIT, GRILLE) for dx, dz in DIRS):
            pont.type[g.case] = MUR
            pont.hauteur[g.case] = 0
            g.case_morte = True
    pont.grilles = [g for g in pont.grilles if not getattr(g, "case_morte", False)]
    for s in pont.salles:
        s.grilles = [gid for gid in s.grilles if any(g.id == gid for g in pont.grilles)]


def _creuser_conduit(pont, ga, gb, murs_fenetre):
    W, H = pont.largeur, pont.profondeur
    depart = (ga.case[0] - ga.vers_sol[0], ga.case[1] - ga.vers_sol[1])
    arrivee = (gb.case[0] - gb.vers_sol[0], gb.case[1] - gb.vers_sol[1])

    def praticable(c):
        if not (1 <= c[0] < W - 1 and 1 <= c[1] < H - 1) or c in murs_fenetre:
            return False
        if any(pont.t(c[0] + a, c[1] + b) == PORTE for a, b in DIRS8):
            return False   # jamais à côté d'une porte (les battants coulissent dans le mur)
        return pont.type[c] in (MUR, VIDE, CONDUIT)

    if not praticable(depart) or not praticable(arrivee):
        return
    ouvert = [(0.0, 0.0, depart)]
    meilleur = {depart: 0.0}
    parent = {}
    while ouvert:
        f, g, c = heapq.heappop(ouvert)
        if c == arrivee:
            break
        if g > meilleur.get(c, 1e18):
            continue
        for dx, dz in DIRS:
            n = (c[0] + dx, c[1] + dz)
            if not praticable(n):
                continue
            t = pont.type[n]
            cout = 0.3 if t == CONDUIT else (1.0 if t == MUR else 1.4)
            ng = g + cout
            if ng < meilleur.get(n, 1e18):
                meilleur[n] = ng
                parent[n] = c
                heapq.heappush(ouvert, (ng + (abs(n[0] - arrivee[0]) + abs(n[1] - arrivee[1])) * 0.3, ng, n))
    if arrivee not in meilleur:
        return
    c = arrivee
    while True:
        pont.type[c] = CONDUIT
        pont.hauteur[c] = C.HAUTEUR_CONDUIT
        if c == depart:
            break
        c = parent[c]
