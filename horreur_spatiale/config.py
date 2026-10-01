# -*- coding: utf-8 -*-
"""
config.py — Toutes les constantes réglables du jeu.

Modifie ce fichier pour ajuster la difficulté, les contrôles, la manette,
le volume, la seed de génération, etc.
"""

# ----------------------------------------------------------------------------
# GÉNÉRAL / FENÊTRE
# ----------------------------------------------------------------------------
TITLE = "DÉRIVE"
SEED = None                 # None = seed aléatoire à chaque partie, sinon un entier
WINDOW_SIZE = (1280, 720)
FULLSCREEN = False
VSYNC = True
SHOW_FPS = True
TARGET_FPS = 60

# ----------------------------------------------------------------------------
# AUDIO
# ----------------------------------------------------------------------------
MASTER_VOLUME = 0.85
SFX_VOLUME = 1.0
MUSIC_VOLUME = 0.55
AMBIENT_VOLUME = 0.7
SAMPLE_RATE = 22050         # fréquence des sons générés
ALARM_CYCLE = 2.4           # durée d'un « hurlement » de la sirène (s) : les gyrophares suivent ce rythme
ALARM_NEAR_RADIUS = 16.0    # au-delà, le haut-parleur de la salle n'est plus entendu « en direct »
ALARM_NEAR_VOLUME = 0.75    # sirène du haut-parleur le plus proche
ALARM_FAR_VOLUME = 0.45     # sirène lointaine (tout le vaisseau qui hurle, étouffée et réverbérée)
ALARM_HUM_VOLUME = 0.35     # bourdonnement électrique grave
ALARM_BEEP_VOLUME = 0.3     # bips d'alerte irréguliers
ALARM_VOICE_VOLUME = 0.85   # annonce automatique du vaisseau
ALARM_ANNOUNCE_FIRST = 2.5  # première annonce N s après le début de l'alerte
ALARM_ANNOUNCE_INTERVAL = (11.0, 18.0)
ALARM_FADE_OUT = 1.2        # vitesse d'extinction de l'alarme
ALARM_AFTER_SILENCE = 9.0   # durée du silence lourd après l'alerte (s)
SOUND_CACHE_DIR = "generated/sounds"
REGENERATE_SOUNDS = False   # True = regénère les .wav à chaque lancement
SOUND_MAX_DISTANCE = 40.0   # distance au-delà de laquelle un son 3D est muet

# ----------------------------------------------------------------------------
# CONTRÔLES CLAVIER / SOURIS
# ----------------------------------------------------------------------------
KEYBOARD_LAYOUT = "azerty"  # "azerty" ou "qwerty"
MOUSE_SENSITIVITY = 45.0    # degrés par unité de déplacement souris
INVERT_MOUSE_Y = False
CROUCH_TOGGLE = True        # Ctrl / Rond : bascule (True) ou maintien (False)

KEYS_AZERTY = {
    "forward": "z", "back": "s", "left": "q", "right": "d",
    "run": "shift", "crouch": "control",
    "knife": "a", "reload": "r", "flashlight": "l", "nightvision": "n",
    "interact": "e", "inventory": "tab", "heal": "h", "use_item": "f",
    "prev_item": "c", "next_item": "v", "drop": "delete",
    "pause": "escape", "debug": "f3",
    "debug_power": "f4", "debug_screamer": "f5",   # touches de test (voir DEBUG_KEYS)
    "debug_docs": "f6", "debug_reveal": "f7", "debug_sound": "f8",
    "journal": "j", "controls": "i",
    "melee": "b",               # mise à mort au corps à corps (R3 à la manette)
    "guide": "g",               # traits lumineux au sol vers l'objectif (flèche bas à la manette)
    "debug_hangar": "f9", "debug_ending": "f10", "debug_vertigo": "f11",
    "debug_rifle": "f12",       # F12 : fusil + munitions ; Maj+F12 : déclencher l'alarme
    "weapon_pistol": "1", "weapon_rifle": "2", "weapon_knife": "3",
    # navette
    "ship_up": "space", "ship_down": "control", "ship_boost": "shift",
    "ship_roll_left": "a", "ship_roll_right": "e",
    "ship_assist": "f", "ship_brake": "x", "ship_camera": "c",
}
KEYS_QWERTY = dict(KEYS_AZERTY, forward="w", left="a", knife="q", ship_roll_left="q")

# IMPORTANT : Ursina lit les lettres en "raw", c'est-à-dire par POSITION
# physique (nommée selon un clavier QWERTY US). On convertit donc les
# lettres AZERTY ci-dessus vers leur position physique : la touche Z d'un
# clavier AZERTY est à la place du W d'un QWERTY, etc.
_AZERTY_TO_PHYSICAL = {"a": "q", "z": "w", "q": "a", "w": "z"}


def _physical(key):
    if KEYBOARD_LAYOUT == "azerty":
        return _AZERTY_TO_PHYSICAL.get(key, key)
    return key


KEYS = {k: _physical(v) for k, v in (KEYS_AZERTY if KEYBOARD_LAYOUT == "azerty" else KEYS_QWERTY).items()}

# ----------------------------------------------------------------------------
# MANETTE PS5 DUALSENSE (pygame.joystick)
# ----------------------------------------------------------------------------
GAMEPAD_ENABLED = True
GAMEPAD_DEADZONE = 0.14         # zone morte des sticks
GAMEPAD_TRIGGER_THRESHOLD = 0.45  # seuil d'appui des gâchettes L2/R2
GAMEPAD_LOOK_SPEED = 200.0      # degrés / seconde à fond de stick
GAMEPAD_LOOK_CURVE = 2.0        # 1 = linéaire, 2 = quadratique (plus précis)
GAMEPAD_INVERT_Y = False
GAMEPAD_RUMBLE = True
GAMEPAD_PROFILE = "auto"        # "auto", "sdl" (HIDAPI, cas le plus courant), "directinput", "evdev"
GAMEPAD_SDL_DUMMY_VIDEO = True  # pygame sans fenêtre (pilote vidéo SDL "dummy"). Mettre False si la
                                # manette n'est pas détectée sur ta machine (voir README, Dépannage)

# Profil SDL2/HIDAPI : DualSense reconnu comme "PS5 Controller"
# (pygame 2 sous Windows/macOS/Linux, USB ou Bluetooth la plupart du temps)
GAMEPAD_PROFILES = {
    "sdl": {
        "axes": {"lx": 0, "ly": 1, "rx": 2, "ry": 3, "l2": 4, "r2": 5},
        "buttons": {
            "cross": 0, "circle": 1, "square": 2, "triangle": 3,
            "create": 4, "ps": 5, "options": 6, "l3": 7, "r3": 8,
            "l1": 9, "r1": 10,
            "dpad_up": 11, "dpad_down": 12, "dpad_left": 13, "dpad_right": 14,
            "touchpad": 15,
        },
        "use_hat": False,
    },
    # Profil DirectInput / ancien pilote générique
    "directinput": {
        "axes": {"lx": 0, "ly": 1, "rx": 2, "ry": 5, "l2": 3, "r2": 4},
        "buttons": {
            "square": 0, "cross": 1, "circle": 2, "triangle": 3,
            "l1": 4, "r1": 5, "l2b": 6, "r2b": 7, "create": 8, "options": 9,
            "l3": 10, "r3": 11, "ps": 12, "touchpad": 13,
        },
        "use_hat": True,
    },
    # Linux sans accès hidraw (pilote noyau hid-playstation via evdev)
    # Le clic du pavé tactile n'y est pas exposé : "Create" le remplace.
    "evdev": {
        "axes": {"lx": 0, "ly": 1, "l2": 2, "rx": 3, "ry": 4, "r2": 5},
        "buttons": {
            "cross": 0, "circle": 1, "triangle": 2, "square": 3,
            "l1": 4, "r1": 5, "l2b": 6, "r2b": 7, "touchpad": 8, "options": 9,
            "ps": 10, "l3": 11, "r3": 12,
        },
        "use_hat": True,
    },
}

# ----------------------------------------------------------------------------
# GÉNÉRATION DU VAISSEAU
# ----------------------------------------------------------------------------
CELL = 2.5                  # taille d'une case de la grille (mètres)
GRID_W = 44                 # cases en X (longueur du vaisseau)
GRID_H = 30                 # cases en Z (largeur)
DECK_COUNT = 1              # architecture prête pour plusieurs ponts
DECK_SPACING = 14.0         # écart vertical entre deux ponts
ROOM_HEIGHT = 3.2
CORRIDOR_HEIGHT = 2.7
HANGAR_HEIGHT = 10.0
ENGINE_HEIGHT = 6.0
VENT_HEIGHT = 1.1
WALL_T = 0.3                # épaisseur des murs
DOOR_WIDTH = 1.5
DOOR_HEIGHT = 2.3
EXTRA_LOOP_CHANCE = 0.35    # probabilité d'ajouter une boucle par salle
VENT_LINKS = 6              # nombre de conduits d'aération
CHUNK_SIZE = 8              # taille des blocs de couloirs (fusion des meshes)
CULL_DISTANCE = 42.0        # distance d'activation des salles
HANGAR_OPENING_CELLS = 6    # largeur de l'ouverture du hangar (en cases)
HANGAR_OPENING_HEIGHT = 7.0

# ----------------------------------------------------------------------------
# JOUEUR (FPS)
# ----------------------------------------------------------------------------
PLAYER_RADIUS = 0.35
PLAYER_HEIGHT = 1.8
PLAYER_CROUCH_HEIGHT = 1.0
EYE_HEIGHT = 1.65
CROUCH_EYE_HEIGHT = 0.82
WALK_SPEED = 3.0
RUN_SPEED = 5.4
CROUCH_SPEED = 1.5
ACCELERATION = 12.0
STAMINA_MAX = 100.0
STAMINA_DRAIN = 16.0        # par seconde de course
STAMINA_REGEN = 11.0
MAX_HEALTH = 100
LOW_HEALTH = 35
BANDAGE_HEAL = 35          # santé rendue par un bandage
BANDAGE_TIME = 2.0         # durée d'application (le joueur est vulnérable : lent, arme baissée)
BANDAGE_SLOW = 0.35        # vitesse de déplacement pendant l'application
FOV = 80
ADS_FOV = 58
INTERACT_DISTANCE = 2.3
SEARCH_TIME = 1.8           # durée de fouille d'un cadavre
OBJECTIVE_COMPASS = True    # guidage vers l'objectif (False = plus difficile, aucune flèche)

# ----------------------------------------------------------------------------
# GUIDAGE (flèche qui suit le vrai chemin A*, marqueur en bord d'écran, traits au sol)
# ----------------------------------------------------------------------------
GUIDE_COLOR = (0.35, 1.0, 0.55)       # couleur de la flèche / du marqueur (r, g, b entre 0 et 1)
GUIDE_ARROW_SIZE = 0.055              # taille de la flèche en haut de l'écran
GUIDE_PULSE = 0.12                    # amplitude de la pulsation (0 = fixe)
GUIDE_EDGE_MARKER = True              # marqueur de destination (bord d'écran si hors champ)
GUIDE_REPATH_TIME = 0.35              # recalcul du chemin (secondes)
GUIDE_LOOKAHEAD = 14                  # nombre max de cases du trajet testées pour « couper » les virages
GUIDE_TRAIL = True                    # traits lumineux au sol (touche G / flèche bas)
GUIDE_TRAIL_TIME = 6.0                # durée d'affichage des traits (secondes)
GUIDE_TRAIL_LENGTH = 70.0             # longueur max du tracé au sol (mètres)
GUIDE_TRAIL_SPACING = 1.1             # espacement des traits (mètres)
GUIDE_TRAIL_COLOR = (0.3, 0.95, 0.6)
GUIDE_TRAIL_COOLDOWN = 1.0

# ----------------------------------------------------------------------------
# APPARITION ET FILET DE SÉCURITÉ
# ----------------------------------------------------------------------------
SPAWN_SIDE_DISTANCE = 4.2             # distance entre le centre de la navette posée et le joueur (porte latérale)
SPAWN_RAY_HEIGHT = 4.0                # hauteur de départ du rayon lancé vers le sol
SPAWN_MAX_WAIT_FRAMES = 90            # images max d'attente du sol avant repli (y = 0)
SAFETY_CHECK = True                   # replace le joueur s'il sort du vaisseau (bug de collision...)
SAFETY_SAVE_INTERVAL = 0.4            # mémorisation du dernier point sûr (secondes)
SAFETY_MIN_Y = -0.6                   # sous cette hauteur, on considère que le joueur « tombe »

# ----------------------------------------------------------------------------
# LAMPE / BATTERIE / VISION NOCTURNE
# ----------------------------------------------------------------------------
BATTERY_MAX = 100.0
FLASHLIGHT_DRAIN = 0.55     # % par seconde
NIGHTVISION_DRAIN = 1.2     # (ancien réglage, inutilisé : le casque a sa propre batterie)
NVG_BATTERY_SECONDS = 420.0 # autonomie du casque de vision nocturne en usage continu (7 min)
NVG_LOW_PERCENT = 20        # avertissement (bip, image qui grésille)
NVG_FADE_PERCENT = 6.0      # sous ce seuil, l'image faiblit progressivement jusqu'à l'extinction
NVG_BATTERY_RECHARGE = 40.0 # une pile recharge le casque de N % (recharge partielle)
BATTERY_PICKUP = 45.0
FLASHLIGHT_FOV = 46                 # ouverture du cône (degrés)
FLASHLIGHT_TEMPERATURE = 7200       # température de couleur (K) : 6500 neutre, >7000 bleuté
FLASHLIGHT_INTENSITY = 2.4
FLASHLIGHT_ATTENUATION = (1.0, 0.07, 0.011)   # constante, linéaire, quadratique (portée utile ~18 m)
FLASHLIGHT_EXPONENT = 14            # concentration du point chaud central
FLASHLIGHT_OFFSET = (0.22, -0.2, 0.05)        # lampe fixée sur l'arme : à droite et en dessous de l'œil
FLASHLIGHT_LAG = 11.0               # lissage de l'orientation (plus petit = plus de retard)
FLASHLIGHT_RANGE = 22.0             # distance de la caméra d'ombre / du cône volumétrique
FLASHLIGHT_LOW = 25.0               # sous ce % l'intensité baisse
FLASHLIGHT_FLICKER = 10.0           # sous ce % la lampe scintille (Recharger = taper dessus)
FLASHLIGHT_TAP_TIME = 3.0           # durée du répit après une tape sur la lampe

# ----------------------------------------------------------------------------
# QUALITÉ GRAPHIQUE : "basse", "moyenne" ou "haute"
# ----------------------------------------------------------------------------
QUALITY = __import__("os").environ.get("EPAVE_QUALITE", "moyenne")   # ou variable d'environnement EPAVE_QUALITE
# gamma : 1.0 = aucune correction. Une valeur > 1 éclaircit les noirs : on la laisse
# à 1.0 pour que le vaisseau sans courant reste réellement plongé dans le noir.
# point_shadows : nombre de lumières du décor (en plus de la lampe torche) qui
# projettent des ombres (0 à 2, coûteux : 6 rendus de profondeur par lumière).
QUALITY_PRESETS = {
    "basse": {
        "bloom": False, "ssao": False, "gamma": 1.0, "shadows": False, "shadow_size": 512,
        "normal_maps": False, "volumetric": False, "dust": 0, "point_lights": 4, "particles": .5,
        "cookie": False, "point_shadows": 0,
    },
    "moyenne": {
        "bloom": True, "ssao": False, "gamma": 1.0, "shadows": True, "shadow_size": 1024,
        "normal_maps": True, "volumetric": True, "dust": 36, "point_lights": 6, "particles": 1.0,
        "cookie": True, "point_shadows": 0,
    },
    "haute": {
        "bloom": True, "ssao": True, "gamma": 1.0, "shadows": True, "shadow_size": 2048,
        "normal_maps": True, "volumetric": True, "dust": 80, "point_lights": 8, "particles": 1.5,
        "cookie": True, "point_shadows": 1,
    },
}
BLOOM_INTENSITY = 1.1
BLOOM_THRESHOLD = 0.62              # luminosité à partir de laquelle un pixel « bave »
VIEWMODEL_FOV = 62                  # FOV propre de l'arme (couche séparée)


def quality():
    """Préréglage de qualité actif."""
    return QUALITY_PRESETS.get(QUALITY, QUALITY_PRESETS["moyenne"])


def kelvin_to_rgb(k):
    """Approximation de la couleur d'un corps noir (Tanner Helland), normalisée."""
    import math
    t = k / 100.0
    r = 255 if t <= 66 else 329.7 * ((t - 60) ** -0.1332)
    g = 99.47 * math.log(t) - 161.12 if t <= 66 else 288.12 * ((t - 60) ** -0.0755)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.52 * math.log(t - 10) - 305.04)
    r, g, b = (max(0, min(255, x)) / 255 for x in (r, g, b))
    m = max(r, g, b)
    return (r / m, g / m, b / m)


FLASHLIGHT_COLOR = kelvin_to_rgb(FLASHLIGHT_TEMPERATURE)

# ----------------------------------------------------------------------------
# ÉCLAIRAGE / AMBIANCE
# ----------------------------------------------------------------------------
# Lumière ambiante (r, g, b) : quasi nulle. Sans lampe, on ne voit presque rien.
AMBIENT_POWER_OFF = (0.010, 0.011, 0.014)     # courant coupé
AMBIENT_POWER_ON = (0.021, 0.022, 0.027)      # courant rétabli (reste sombre et contrasté)
AMBIENT_NIGHTVISION = (0.55, 0.9, 0.55)       # vision nocturne (amplification)
FOG_COLOR_FPS = (0.0, 0.0, 0.0)               # brouillard noir pur
FOG_DENSITY_POWER_OFF = 0.085                 # le fond des couloirs se perd dans le noir
FOG_DENSITY_POWER_ON = 0.055
FOG_DENSITY_TPS = 0.0009
MAX_POINT_LIGHTS = QUALITY_PRESETS[QUALITY]["point_lights"]   # lumières dynamiques simultanées (pool)
LIGHT_RANGE = 9.0
LIGHT_REACH_CELLS = 9       # seules les lumières à moins de N cases (en suivant les passages) sont rendues
LIGHT_INTENSITY = 1.25      # multiplicateur global des luminaires du vaisseau (courant rétabli)
LIGHT_COLOR_WARM = (1.0, 0.78, 0.55)   # sodium / tungstène (quartiers, machines)
LIGHT_COLOR_COLD = (0.72, 0.84, 1.0)   # néons froids (couloirs, passerelle)
LIGHT_COLOR_MEDBAY = (0.86, 0.94, 1.0)  # infirmerie : blanc clinique
LIGHT_COLOR_MESS = (1.0, 0.72, 0.46)    # salle à manger : lumière chaude, « domestique »
# flash de bouche du pistolet (éclaire brièvement la pièce)
MUZZLE_LIGHT_INTENSITY = 5.0
MUZZLE_LIGHT_ATTENUATION = (1.0, 0.12, 0.05)
# lueur des étoiles à travers hublots et baies vitrées (très faible, bleutée)
STARLIGHT_COLOR = (0.42, 0.52, 0.85)
STARLIGHT_INTENSITY = 0.32  # baie vitrée ; un hublot en reçoit la moitié
STARLIGHT_RADIUS = 4.0      # n'éclaire que quelques mètres autour de la fenêtre
# navette posée dans le hangar
SHUTTLE_PARKED_HEADLIGHT = 0.9   # intensité du phare avant une fois posée
SHUTTLE_NAV_LIGHT = 0.55         # feux de navigation (rouge / vert / blanc à éclats)
# bandes d'éclairage de secours rouges au ras du sol (aide pour les joueurs en difficulté)
EMERGENCY_STRIPS = False
EMERGENCY_COLOR = (1.0, 0.08, 0.04)
EMERGENCY_INTENSITY = 0.22
# petits détails lumineux (sans éclairer autour d'eux)
BATTERY_LED_CHANCE = 0.45        # voyants de batterie de secours sur les consoles
SPARK_INTERVAL = (5.0, 14.0)     # étincelles des câbles arrachés (secondes entre deux gerbes)
SPARK_FLASH = 2.4                # intensité du flash lumineux d'une étincelle

# ----------------------------------------------------------------------------
# COURANT DU VAISSEAU
# ----------------------------------------------------------------------------
POWER_START_OFF = True       # False = le courant est déjà rétabli au début (ancien comportement)
POWER_FUSES = (2, 3)         # nombre de fusibles à retrouver (tiré avec la seed)
POWER_BROKEN_RATIO = 0.25    # part des lumières qui restent cassées après le redémarrage (20 à 30 %)
POWER_BROKEN_FLICKER = 0.5   # parmi elles, part qui clignote en permanence (le reste reste éteint)
POWER_SILENCE_TIME = 1.4     # silence après l'actionnement du levier
POWER_SPINUP_TIME = 5.5      # montée en puissance du réacteur
POWER_SPREAD_STEP = 0.16     # secondes par case parcourue depuis la salle des machines
POWER_STARTUP_TIME = (0.5, 1.4)   # durée du clignotement de démarrage d'un néon
POWER_ALIENS_ON_RESTART = (2, 3)  # petites créatures qui sortent des conduits au redémarrage
# coupures temporaires (courant rétabli)
POWER_OUTAGE_CHECK = 12.0    # un tirage toutes les N secondes...
POWER_OUTAGE_BASE = 0.015    # ... probabilité de base (rare)
POWER_OUTAGE_HORROR = 0.22   # ... ajoutée en mode horreur
POWER_OUTAGE_CREATURE = 0.25 # ... ajoutée quand la grande créature est proche
POWER_OUTAGE_CREATURE_DIST = 12.0
POWER_OUTAGE_DURATION = (2.0, 5.0)
POWER_OUTAGE_MIN_GAP = 35.0  # délai minimal entre deux coupures
# portes sans courant
DOOR_AJAR_CHANCE = 0.35      # portes restées entrouvertes
DOOR_STUCK_CHANCE = 0.25     # portes bloquées (il faut passer par les conduits)
DOOR_AJAR_OPENING = 0.62     # ouverture d'une porte entrouverte ou forcée (0..1)
DOOR_FORCE_TIME = 2.6        # durée d'appui pour forcer une porte
NOISE_DOOR_FORCE = 12.0      # forcer une porte fait beaucoup de bruit

# ----------------------------------------------------------------------------
# SCREAMER (casier piégé)
# ----------------------------------------------------------------------------
SCREAMER_ENABLED = True
SCREAMER_VOLUME = 1.0        # volume du cri et du stinger
SCREAMER_FLASH = True        # flash blanc d'une image (False pour les personnes sensibles aux flashs)
SCREAMER_MUSIC_TIME = 25.0   # durée de la musique angoissante qui suit
CUSTOM_SOUND_DIR = "sounds"  # un fichier screamer.wav ou screamer.ogg placé ici remplace le cri généré
DEBUG_KEYS = True            # F4 courant, F5 screamer, F6 documents, F7 révélation, F8 son de test

# ----------------------------------------------------------------------------
# HISTOIRE : INFECTION PAR SINUS ET HALLUCINATIONS
# ----------------------------------------------------------------------------
INFECTION_START = 0.05       # le joueur respire l'air du bord dès le hangar
INFECTION_TIME = 1500.0      # secondes à bord pour atteindre une infection complète
HALLU_FIRST_DELAY = (90.0, 150.0)   # premier indice
HALLU_INTERVAL = (70.0, 140.0)      # intervalle entre deux indices (se raccourcit avec l'infection)
HALLU_VARIANT_AT = 0.4       # à partir de là, une phrase d'un document déjà lu change à la relecture
HALLU_HUM = 0.12             # volume du bourdonnement à 7 Hz à infection maximale (très discret)
REVEAL_TRUTH_TIME = 6.5      # durée pendant laquelle « l'hallucination tombe »
REVEAL_EXTRA_ALIENS = 2      # petites créatures en plus du plafond après la révélation
REVEAL_CREATURE_DIST = 14.0  # la grande créature réapparaît à cette distance, entre toi et le hangar

# ----------------------------------------------------------------------------
# VERTIGES (après la révélation du disque dur)
# ACCESSIBILITÉ : ces effets peuvent donner le mal des transports. Réglable aussi
# dans le menu pause. Valeurs : "desactive", "faible", "normal", "fort".
# ----------------------------------------------------------------------------
VERTIGO_INTENSITY = "normal"
VERTIGO_LEVELS = {"desactive": 0.0, "faible": 0.45, "normal": 1.0, "fort": 1.5}
VERTIGO_FIRST_DELAY = 25.0          # première crise N secondes après la révélation
VERTIGO_INTERVAL = (30.0, 90.0)     # temps entre deux crises (secondes)
VERTIGO_DURATION = (3.0, 8.0)       # durée d'une crise (secondes)
VERTIGO_NEAR_DIST = 14.0            # créature plus proche que ça : crises plus fréquentes...
VERTIGO_NEAR_FACTOR = 2.2           # ... le compte à rebours va N fois plus vite (idem pendant l'alerte)
VERTIGO_STUMBLE_CHANCE = 0.45       # chance de trébucher pendant une crise
VERTIGO_STUMBLE_TIME = 1.6          # durée du trébuchement (chute à moitié puis relevé)
VERTIGO_SCREEN_FX = True            # flou des bords / dédoublement / désaturation (rendu secondaire)
VERTIGO_BUFFER_SCALE = 0.5          # résolution du rendu secondaire (0.5 = moitié : rapide et flou)

# ----------------------------------------------------------------------------
# CINÉMATIQUE DE FIN
# ----------------------------------------------------------------------------
ENDING_SKIP_HOLD = 1.5              # maintenir Croix / Espace N secondes pour passer la cinématique
ENDING_CREDITS_SPEED = 0.055        # vitesse de défilement des crédits (hauteur d'écran par seconde)


# ----------------------------------------------------------------------------
# ARMES
# ----------------------------------------------------------------------------
PISTOL_MAG = 8
# fusil d'assaut silencieux (trouvé dans une caisse verrouillée du hangar)
RIFLE_MAG = 24
RIFLE_FIRE_RATE = 9.0           # coups par seconde en automatique
RIFLE_DAMAGE = 55
RIFLE_RANGE = 70.0
RIFLE_SPREAD_HIP = 2.2
RIFLE_SPREAD_ADS = .35          # très précis au point rouge, en courtes rafales
RIFLE_SPREAD_BURST = .18        # dispersion ajoutée à chaque tir d'une rafale
RIFLE_RECOIL = .55              # relèvement par tir (degrés)...
RIFLE_RECOIL_CLIMB = .12        # ... qui augmente pendant la rafale
RIFLE_RELOAD_TIME = 2.3
RIFLE_ADS_FOV = 50
RIFLE_VOLUME = .55
RIFLE_MUZZLE_LIGHT = .25        # flash presque invisible au bout du silencieux
RIFLE_NOISE_RADIUS = 3.0        # la grande créature ne l'entend que dans ce rayon (pas d'alerte générale)
RIFLE_ALIEN_HEAR_RADIUS = 7.0   # les petites créatures proches peuvent réagir
RIFLE_START_AMMO = 30           # munitions trouvées avec le fusil
RIFLE_DEBUG_AMMO = 72           # F12
RIFLE_CRATE_HOLD = 2.5          # forcer la caisse verrouillée (maintenir)
WEAPON_SWITCH_TIME = .55        # durée de l'animation de changement d'arme
# son du pistolet (volumes 0..1)
GUN_VOLUME_RANGE = (0.88, 1.0)        # variation de volume à chaque tir
GUN_PITCH_RANGE = (0.93, 1.07)        # variation de hauteur à chaque tir
GUN_HALL_ROOMS = ("hangar", "engine") # grandes salles : écho long et métallique
GUN_REVERB_HALL = 0.95
GUN_REVERB_ROOM = 0.75
GUN_REVERB_CORRIDOR = 0.7             # couloirs : court et sec
GUN_REVERB_VENT = 0.8                 # conduits : étouffé
GUN_TINNITUS_WINDOW = 2.5             # deux tirs (ou plus) en moins de N s dans un endroit exigu -> acouphène
GUN_TINNITUS_VOLUME = 0.8
GUN_ECHO_VOLUME = 0.5                 # écho qui se propage dans le vaisseau
GUN_AFTERMATH_DELAY = (2.6, 4.2)      # silence pesant avant un bruit lointain (secondes)
GUN_AFTERMATH_COOLDOWN = 5.0
PISTOL_START_MAG = 6
PISTOL_START_RESERVE = 6
PISTOL_DAMAGE = 2
PISTOL_COOLDOWN = 0.3
PISTOL_RELOAD_TIME = 1.6
PISTOL_RANGE = 60.0
PISTOL_SPREAD_HIP = 2.6     # degrés
PISTOL_SPREAD_ADS = 0.35
PISTOL_RECOIL = 2.6         # degrés de relevé
AMMO_PICKUP = (3, 7)        # munitions trouvées sur un cadavre / dans un sac

# ----------------------------------------------------------------------------
# CASIERS : LOOT (toutes les quantités et probabilités sont ici)
# ----------------------------------------------------------------------------
LOCKER_FILL_CHANCE = 0.70   # proportion de casiers qui contiennent de l'équipement utile
LOCKER_EMPTY_JUNK = 0.55    # parmi les autres : chance d'y trouver un objet sans utilité (sinon vide)
LOCKER_EXTRA_ITEM = 0.30    # chance d'un 2e objet utile dans un casier rempli
LOCKER_AMOUNTS = {          # quantité (min, max) par type d'objet trouvé dans un casier
    "ammo": (6, 12), "bandage": (1, 2), "battery": (1, 1), "rifle_ammo": (8, 14),
}
# poids par type de salle : plus de bandages à l'infirmerie, de piles à la salle des machines,
# de munitions près de la salle de commandement
LOCKER_TABLES = {
    "medbay":  {"bandage": 60, "battery": 20, "ammo": 20},
    "engine":  {"battery": 50, "ammo": 22, "bandage": 18, "rifle_ammo": 10},
    "command": {"ammo": 50, "battery": 18, "bandage": 18, "rifle_ammo": 14},
    "crew":    {"ammo": 34, "battery": 33, "bandage": 33},
    "mess":    {"bandage": 35, "battery": 35, "ammo": 30},
    "storage": {"battery": 40, "ammo": 35, "bandage": 25},
    "hangar":  {"battery": 45, "ammo": 35, "bandage": 20},
}
LOCKER_NEAR_COMMAND_DIST = 22.0     # un casier à moins de N m de la passerelle compte comme « près »
LOCKER_NEAR_COMMAND_AMMO_BONUS = 30  # poids ajouté aux munitions dans ce cas
NV_HELMET_ROOMS = ("crew", "medbay")  # le casque de vision nocturne (unique) est dans un casier de ces salles
LOCKER_GLOW_TIME = 2.6      # durée de la lueur sur les objets à l'ouverture
KNIFE_DAMAGE = 1
KNIFE_STEALTH_MULT = 2      # dégâts x2 sur une cible qui ne t'a pas repéré
KNIFE_RANGE = 1.9
KNIFE_COOLDOWN = 0.55
KNIFE_DURABILITY = 10

# ----------------------------------------------------------------------------
# INVENTAIRE
# ----------------------------------------------------------------------------
INVENTORY_SLOTS = 8
STACK_SIZES = {"rifle_ammo": 45, "bandage": 4, "battery": 4, "ammo": 24, "knife": 1, "nv_helmet": 1, "hdd": 1}

# ----------------------------------------------------------------------------
# BRUIT (rayon en mètres)
# ----------------------------------------------------------------------------
NOISE_RUN = 13.0
NOISE_WALK = 6.0
NOISE_CROUCH = 1.2
NOISE_SHOT = 70.0
NOISE_KNIFE = 3.0           # coup de couteau dans le vide
NOISE_ALIEN_SCREAM = 8.0    # cri d'une araignée blessée (sans mourir) au couteau
KNIFE_ALERT_DIST = 4.0      # le couteau n'alerte la grande créature qu'en deçà de cette distance...
KNIFE_ALERT_CHANCE = 0.15   # ... et seulement avec cette probabilité
NOISE_DOOR = 8.0
NOISE_LOCKER = 5.0

# ----------------------------------------------------------------------------
# MODE HORREUR
# ----------------------------------------------------------------------------
HORROR_DURATION = 20.0      # secondes à pleine intensité après un tir
HORROR_FADE = 10.0          # temps de redescente si le joueur est discret
HORROR_ALIEN_WAVE = (1, 3)
HORROR_WAVE_INTERVAL = 18.0
HORROR_MAX_TIME = 60.0      # une alerte ne dure jamais plus d'une minute (même en continuant à tirer)
CAMERA_SHAKE = 0.35

# ----------------------------------------------------------------------------
# GRANDE CRÉATURE
# ----------------------------------------------------------------------------
CREATURE_SPEED_WANDER = 1.9
CREATURE_SPEED_INVESTIGATE = 3.4
CREATURE_SPEED_CHASE = 5.5
CREATURE_VENT_SPEED_MULT = 0.55
CREATURE_VIEW_DIST = 15.0
CREATURE_VIEW_ANGLE = 110.0
CREATURE_KILL_DIST = 1.35      # distance de contact
CREATURE_HITS_TO_KILL = 5       # de face, elle frappe : le 5e coup est mortel
CREATURE_HIT_DAMAGE = 16        # dégâts d'un coup (sans jamais tuer avant le 5e)
CREATURE_ATTACK_COOLDOWN = 1.6  # secondes entre deux coups
CREATURE_BEHIND_SCARE = True    # si elle arrive dans ton dos : elle hurle, te fait peur... et repart
CREATURE_HITS_DECAY = 25.0      # un coup encaissé est « oublié » après N secondes sans être touché
CREATURE_LOSE_TIME = 4.0
CREATURE_SEARCH_TIME = 14.0
CREATURE_STUN_TIME = 2.2
CREATURE_HITS_TO_FLEE = 3
CREATURE_HIDE_TIME = (20.0, 40.0)
DIRECTOR_CALM_TIME = 85.0   # secondes de calme avant que la directrice ne rapproche la créature
CREATURE_CALM_UNTIL_POWER = True   # courant coupé : la créature n'attaque pas si l'on reste discret
CREATURE_PROVOKE_NOISE = 20.0      # ... sauf un bruit au moins aussi fort (coup de feu) qui déclenche l'alerte

# ----------------------------------------------------------------------------
# PETITES CRÉATURES
# ----------------------------------------------------------------------------
ALIEN_HP = 2
ALIEN_SPEED = 4.3
ALIEN_LEAP_DIST = 4.2
ALIEN_DAMAGE = 11
ALIEN_BITE_DAMAGE = 5
ALIEN_MAX = 3               # jamais plus de 3 en même temps sur tout le vaisseau
ALIEN_MAX_HORROR = 3
ALIEN_GROUP = (1, 3)        # taille des groupes
ALIEN_SPAWN_INTERVAL = (90.0, 150.0)
ALIEN_REST_AFTER_GROUP = 60.0   # répit après la mort de tout un groupe
ALIEN_HDD_MULT = 0.6        # intervalle multiplié quand le disque dur est transporté
ALIEN_HDD_AGGRO = 1.25      # avec le disque dur : plus rapides et bondissent de plus loin
ALIEN_CEILING_CHANCE = 0.5  # probabilité qu'une araignée tombée du plafond y rampe d'abord
ALIEN_CORPSE_TIME = 7.0     # durée pendant laquelle le cadavre reste au sol
INFESTED_CORPSE_CHANCE = 0.22
# --- cadavres de l'équipage (corpses.py) ---
CORPSE_FROST = 0.55              # givre sur les combinaisons, cheveux, visières (0 = aucun, 1 = maximum)
CORPSE_HAIR_STRANDS = 14         # mèches de cheveux simplifiées par tête nue
CORPSE_HELMET_BESIDE = 0.5       # probabilité qu'un casque soit posé à côté d'un corps tête nue
CORPSE_HALLU_INFECTION = 0.6     # infection minimale pour l'hallucination « le corps a bougé »
CORPSE_HALLU_CHANCE = 0.12       # chance, en quittant une salle avec un corps, qu'il ait bougé au retour

# ----------------------------------------------------------------------------
# NAVETTE (TPS)
# ----------------------------------------------------------------------------
SHIP_THRUST = 13.0
SHIP_STRAFE = 9.0
SHIP_VERTICAL = 9.0
SHIP_MAX_SPEED = 22.0
SHIP_BOOST_MULT = 2.1
SHIP_BOOST_MAX = 100.0
SHIP_BOOST_DRAIN = 32.0
SHIP_BOOST_REGEN = 11.0
SHIP_DRAG = 0.45
SHIP_TURN_RATE = 70.0       # degrés / s
SHIP_ROLL_RATE = 80.0
SHIP_ANGULAR_DAMP = 5.0
SHIP_RADIUS = 2.1
SHIP_INTEGRITY = 100.0
SHIP_DAMAGE_FACTOR = 3.2    # dégâts par m/s d'impact
SHIP_DAMAGE_MIN_SPEED = 4.5 # les frottements en dessous de cette vitesse d'impact ne font aucun dégât
# --- assistance de vol / régulateur / freinage ---
SHIP_ASSIST_DEFAULT = True  # assistance de vol activée au départ (touche F / Triangle)
SHIP_ASSIST_DRIFT = 2.6     # vitesse d'annulation de la dérive latérale/verticale (assistance)
SHIP_ASSIST_BRAKE = 1.6     # freinage automatique quand on lâche la poussée (assistance)
SHIP_ASSIST_LEVEL = 1.2     # retour du roulis à plat quand on ne touche plus au roulis
SHIP_CRUISE = True          # régulateur : la poussée règle une vitesse cible
SHIP_CRUISE_RATE = 14.0     # m/s de vitesse cible gagnés par seconde de poussée
SHIP_BRAKE_RATE = 2.5       # frein d'urgence (touche X / Rond)
SHIP_LOOK_DEADZONE = 0.02   # zone morte de la commande de rotation (souris et stick)
SHIP_MOUSE_SENS = 0.9       # sensibilité de la souris en vol
SHIP_LOOK_EXPONENT = 1.6    # courbe de réponse (1 = linéaire)
SHIP_MAX_TURN = 85.0        # vitesse de rotation max (degrés / s)
SHIP_TURN_DAMP = 7.0        # amortissement (évite les dépassements)
SHIP_APPROACH_DIST = 60.0   # distance d'affichage de l'aide à l'approche du hangar
SHIP_APPROACH_SPEED = 8.0   # vitesse conseillée pour entrer dans le hangar
SHIP_COLLISION_WARN = 3.0   # avertissement si un obstacle est à moins de N secondes de vol
TPS_CAM_DISTANCE = 16.0
TPS_CAM_HEIGHT = 4.6
TPS_CAM_FAR_DISTANCE = 26.0 # caméra éloignée (touche C / R3)
TPS_CAM_FAR_HEIGHT = 7.5
TPS_CAM_SMOOTH = 4.5        # plus grand = caméra plus réactive
SHIP_START_DISTANCE = 150.0
DEBRIS_COUNT = 70
