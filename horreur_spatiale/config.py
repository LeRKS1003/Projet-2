# -*- coding: utf-8 -*-
"""
config.py — Toutes les constantes réglables du jeu.

Modifie ce fichier pour ajuster la difficulté, les contrôles, la manette,
le volume, la seed de génération, etc.
"""

# ----------------------------------------------------------------------------
# GÉNÉRAL / FENÊTRE
# ----------------------------------------------------------------------------
TITLE = "ÉPAVE — Le silence du Mnémosyne"
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
MEDKIT_HEAL = 45
FOV = 80
ADS_FOV = 58
INTERACT_DISTANCE = 2.3
SEARCH_TIME = 1.8           # durée de fouille d'un cadavre
OBJECTIVE_COMPASS = True    # flèche discrète vers l'objectif (False = plus difficile)

# ----------------------------------------------------------------------------
# LAMPE / BATTERIE / VISION NOCTURNE
# ----------------------------------------------------------------------------
BATTERY_MAX = 100.0
FLASHLIGHT_DRAIN = 0.55     # % par seconde
NIGHTVISION_DRAIN = 1.2
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
QUALITY_PRESETS = {
    "basse": {
        "bloom": False, "ssao": False, "gamma": 1.15, "shadows": False, "shadow_size": 512,
        "normal_maps": False, "volumetric": False, "dust": 0, "point_lights": 4, "particles": .5,
        "cookie": False,
    },
    "moyenne": {
        "bloom": True, "ssao": False, "gamma": 1.18, "shadows": True, "shadow_size": 1024,
        "normal_maps": True, "volumetric": True, "dust": 36, "point_lights": 6, "particles": 1.0,
        "cookie": True,
    },
    "haute": {
        "bloom": True, "ssao": True, "gamma": 1.18, "shadows": True, "shadow_size": 2048,
        "normal_maps": True, "volumetric": True, "dust": 80, "point_lights": 8, "particles": 1.5,
        "cookie": True,
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
AMBIENT_FPS = (0.022, 0.025, 0.032)  # noirs profonds mais pas opaques
FOG_COLOR_FPS = (0.006, 0.007, 0.01)
FOG_DENSITY_FPS = 0.06
FOG_DENSITY_TPS = 0.0009
MAX_POINT_LIGHTS = QUALITY_PRESETS[QUALITY]["point_lights"]   # lumières dynamiques simultanées (pool)
LIGHT_RANGE = 9.0

# ----------------------------------------------------------------------------
# ARMES
# ----------------------------------------------------------------------------
PISTOL_MAG = 8
PISTOL_START_MAG = 6
PISTOL_START_RESERVE = 6
PISTOL_DAMAGE = 2
PISTOL_COOLDOWN = 0.3
PISTOL_RELOAD_TIME = 1.6
PISTOL_RANGE = 60.0
PISTOL_SPREAD_HIP = 2.6     # degrés
PISTOL_SPREAD_ADS = 0.35
PISTOL_RECOIL = 2.6         # degrés de relevé
AMMO_PICKUP = (3, 7)
KNIFE_DAMAGE = 1
KNIFE_STEALTH_MULT = 2      # dégâts x2 sur une cible qui ne t'a pas repéré
KNIFE_RANGE = 1.9
KNIFE_COOLDOWN = 0.55
KNIFE_DURABILITY = 10

# ----------------------------------------------------------------------------
# INVENTAIRE
# ----------------------------------------------------------------------------
INVENTORY_SLOTS = 8
STACK_SIZES = {"medkit": 3, "battery": 4, "ammo": 24, "knife": 1, "nv_helmet": 1, "hdd": 1}

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
CREATURE_KILL_DIST = 1.35
CREATURE_LOSE_TIME = 4.0
CREATURE_SEARCH_TIME = 14.0
CREATURE_STUN_TIME = 2.2
CREATURE_HITS_TO_FLEE = 3
CREATURE_HIDE_TIME = (20.0, 40.0)
DIRECTOR_CALM_TIME = 85.0   # secondes de calme avant que la directrice ne rapproche la créature

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
