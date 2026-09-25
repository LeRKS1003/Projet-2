# -*- coding: utf-8 -*-
"""
config.py — Toutes les constantes réglables du jeu DÉRIVE.

Modifie ce fichier pour ajuster la difficulté, les contrôles, la manette,
les performances ou la génération procédurale.
"""

# ---------------------------------------------------------------------------
# Fenêtre / rendu
# ---------------------------------------------------------------------------
TITRE_FENETRE = "DÉRIVE"
PLEIN_ECRAN = False
TAILLE_FENETRE = (1600, 900)
VSYNC = True
AFFICHER_FPS = False            # compteur d'images par seconde d'Ursina
FOV = 78                        # champ de vision horizontal de la caméra
PLAN_LOINTAIN = 3000            # distance de rendu maximale (pour le ciel étoilé)
ANTICRENELAGE = 4               # échantillons MSAA (0 = désactivé, plus rapide)

# ---------------------------------------------------------------------------
# Génération procédurale
# ---------------------------------------------------------------------------
SEED = None                     # None = seed aléatoire à chaque partie, sinon un entier
GRILLE_LARGEUR = 104            # taille de la grille (1 case = 1 unité = ~1 mètre)
GRILLE_PROFONDEUR = 84
MARGE_SALLES = 5                # espace minimal entre deux salles (couloirs + murs)
RATIO_BOUCLES = 0.35            # proportion d'arêtes supplémentaires (boucles) après l'arbre couvrant
LARGEURS_COULOIR = (2, 3)       # largeur possible d'un couloir
HAUTEUR_COULOIR = 3.0
HAUTEUR_PORTE = 2.4
HAUTEUR_CONDUIT = 1.0           # hauteur intérieure des conduits d'aération
NB_GRILLES_COULOIR = 3          # grilles d'aération supplémentaires dans les couloirs
TAILLE_CHUNK = 16               # taille (en cases) d'un bloc de géométrie statique fusionnée
DISTANCE_CULLING = 48           # au-delà, les salles/chunks sont désactivés
INTERVALLE_CULLING = 0.35       # secondes entre deux mises à jour du culling

# Salles : (largeur min, max), (profondeur min, max), hauteur sous plafond, nombre
SALLES = {
    "machines":       dict(nom="Salle des machines", l=(16, 19), p=(14, 17), h=7.0, n=1),
    "hangar":         dict(nom="Hangar", l=(24, 28), p=(18, 21), h=11.0, n=1),
    "commandement":   dict(nom="Salle de commandement", l=(12, 14), p=(9, 11), h=4.5, n=1),
    "infirmerie":     dict(nom="Infirmerie", l=(10, 12), p=(8, 10), h=3.5, n=1),
    "salle_a_manger": dict(nom="Salle à manger", l=(12, 14), p=(9, 11), h=3.5, n=1),
    "chambre":        dict(nom="Quartiers de l'équipage", l=(6, 7), p=(5, 6), h=3.0, n=4),
    "stockage":       dict(nom="Réserve", l=(7, 9), p=(6, 8), h=3.5, n=2),
}

# ---------------------------------------------------------------------------
# Joueur
# ---------------------------------------------------------------------------
RAYON_JOUEUR = 0.3
HAUTEUR_DEBOUT = 1.8
HAUTEUR_ACCROUPI = 0.9
YEUX_DEBOUT = 1.62
YEUX_ACCROUPI = 0.7
VITESSE_MARCHE = 3.0
VITESSE_COURSE = 5.4
VITESSE_ACCROUPI = 1.5
ENDURANCE_MAX = 6.0             # secondes de course
RECUP_ENDURANCE = 0.75          # secondes récupérées par seconde de repos
SENSIBILITE_SOURIS = 40.0
INVERSER_Y = False
BALANCEMENT_TETE = True
DISTANCE_INTERACTION = 2.3
ACCROUPI_MAINTENU_CLAVIER = True  # True : maintenir Ctrl ; False : Ctrl bascule

# Bruit produit par le joueur (rayon en unités où la créature peut l'entendre)
BRUIT_COURSE = 17.0
BRUIT_MARCHE = 7.0
BRUIT_ACCROUPI = 1.5

# ---------------------------------------------------------------------------
# Clavier (disposition AZERTY ; WASD fonctionne aussi pour les claviers QWERTY)
# ---------------------------------------------------------------------------
TOUCHES_AVANT = ("z", "w", "up arrow")
TOUCHES_ARRIERE = ("s", "down arrow")
TOUCHES_GAUCHE = ("q", "a", "left arrow")
TOUCHES_DROITE = ("d", "right arrow")
TOUCHES_COURIR = ("left shift", "right shift", "shift")
TOUCHES_ACCROUPIR = ("left control", "right control", "control")
TOUCHE_LAMPE = "f"
TOUCHE_INTERAGIR = "e"
TOUCHE_CARTE = ("tab", "m", ";")   # ";" = touche M d'un clavier AZERTY en mode brut
TOUCHE_PAUSE = "escape"
TOUCHE_DEBUG = "f3"
BOUTON_LAMPE_CONCENTREE = "right mouse"

# ---------------------------------------------------------------------------
# Manette PS5 DualSense (via pygame.joystick / SDL2)
# ---------------------------------------------------------------------------
MANETTE_ACTIVE = True
# "auto" choisit le profil selon le nombre de boutons détectés,
# sinon "sdl" (pilote HIDAPI de SDL2 : Windows, macOS, Linux récent)
# ou "linux" (pilote noyau hid-playstation sans HIDAPI).
MANETTE_PROFIL = "auto"
MANETTE_PROFILS = {
    "sdl": {
        "axes": {"lx": 0, "ly": 1, "rx": 2, "ry": 3, "l2": 4, "r2": 5},
        "boutons": {"croix": 0, "rond": 1, "carre": 2, "triangle": 3,
                    "create": 4, "ps": 5, "options": 6, "l3": 7, "r3": 8,
                    "l1": 9, "r1": 10, "haut": 11, "bas": 12, "gauche": 13,
                    "droite": 14, "pave": 15},
    },
    "linux": {
        "axes": {"lx": 0, "ly": 1, "l2": 2, "rx": 3, "ry": 4, "r2": 5},
        "boutons": {"croix": 0, "rond": 1, "triangle": 2, "carre": 3,
                    "l1": 4, "r1": 5, "l2b": 6, "r2b": 7, "create": 8,
                    "options": 9, "ps": 10, "l3": 11, "r3": 12, "pave": 13},
    },
}
ZONE_MORTE_STICK = 0.14         # zone morte radiale des sticks
EXPOSANT_COURBE_STICK = 1.8     # 1 = linéaire, >1 = plus précis au centre
SENSIBILITE_MANETTE = (170.0, 120.0)   # degrés/seconde (horizontal, vertical) à fond
SEUIL_GACHETTE = 0.35
MANETTE_INVERSER_Y = False
VIBRATIONS = True
SDL_PILOTE_VIDEO = "dummy"      # pygame n'ouvre aucune fenêtre : seul le joystick est utilisé

# ---------------------------------------------------------------------------
# Lampe torche
# ---------------------------------------------------------------------------
LAMPE_FOV = 75                  # angle de coupure du cône (le bord est adouci par l'exposant)
LAMPE_FOV_CONCENTREE = 40
LAMPE_EXPOSANT = 26
LAMPE_EXPOSANT_CONCENTREE = 90
LAMPE_PUISSANCE = 1.6
LAMPE_PUISSANCE_CONCENTREE = 3.2
LAMPE_DUREE_BATTERIE = 240.0    # secondes d'autonomie avec une batterie pleine
LAMPE_MULT_CONCENTREE = 3.0     # la lampe concentrée vide la batterie x fois plus vite
BATTERIE_PILE = 0.45            # une pile recharge 45 %
NB_PILES = 8

# ---------------------------------------------------------------------------
# Éclairage / ambiance
# ---------------------------------------------------------------------------
NB_LUMIERES_ACTIVES = 6         # lumières ponctuelles simultanées (les plus proches)
AMBIANTE_SANS_COURANT = (0.03, 0.03, 0.038)
AMBIANTE_AVEC_COURANT = (0.06, 0.06, 0.07)
BROUILLARD_SANS_COURANT = 0.075
BROUILLARD_AVEC_COURANT = 0.045
COULEUR_BROUILLARD = (0.008, 0.008, 0.012)

# ---------------------------------------------------------------------------
# Espace
# ---------------------------------------------------------------------------
NB_ETOILES = 4500
NB_PLANETES = 3
VITESSE_DERIVE = 0.35           # degrés par seconde de rotation du ciel

# ---------------------------------------------------------------------------
# Créature
# ---------------------------------------------------------------------------
CREATURE_VITESSE_ERRANCE = 2.0
CREATURE_VITESSE_ENQUETE = 3.0
CREATURE_VITESSE_TRAQUE = 5.0
CREATURE_MULT_CONDUIT = 0.8
CREATURE_MULT_COURANT = 1.2     # bonus quand le courant est rétabli
CREATURE_ANGLE_VISION = 120     # cône de vision total (degrés)
CREATURE_PORTEE_VUE = 22.0      # portée si la lampe est allumée
CREATURE_PORTEE_VUE_NUIT = 11.0 # portée si la lampe est éteinte
CREATURE_DISTANCE_MORT = 1.05
CREATURE_DELAI_DEPART = 35.0    # secondes de répit au début de la partie
CREATURE_OUBLI = 3.0            # secondes sans voir le joueur avant de passer en RECHERCHE
DIRECTEUR_CALME_MAX = 75.0      # si le joueur est tranquille trop longtemps, la créature se rapproche
DIRECTEUR_TRAQUE_MAX = 28.0     # traque trop longue : la créature bat en retraite
DIRECTEUR_RETRAITE = (15.0, 35.0)

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
VOLUME_GENERAL = 0.85
DOSSIER_SONS = "sons"           # les .wav sont générés ici au premier lancement
FREQ_ECHANTILLONNAGE = 22050
DISTANCE_AUDIO_MAX = 30.0
