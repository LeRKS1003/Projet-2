"""
Petit FPS avec Ursina — ennemis humanoïdes dotés d'une IA tactique qui progresse.

Lancement :  python fps.py                 (vsync activé, FPS limités à 60)
             python fps.py --sans-limite   (vsync coupé, FPS non plafonnés : pour mesurer)

Au lancement : choix de l'arme (clic sur le menu, ou touches 1 / 2), du moment (3 ou N : jour / nuit),
de la carte (4 : village ou désert) et du mode (5 : survie ou défense du village)
    1 : fusil d'assaut type M4 (tir automatique, viseur point rouge à tube rond grossissant x1,4 dans la lentille)
    2 : sniper (un tir par clic, gros dégâts, lunette zoom x2)
    Carte désert : dunes, tranchées en zigzag, char détruit au centre (il fume encore),
                   batterie anti-aérienne bitube utilisable (obus explosifs, surchauffe)

Commandes (clavier AZERTY) :
    E / flèche haut    : avancer
    S / flèche bas     : reculer
    Q / flèche gauche  : aller à gauche
    D / flèche droite  : aller à droite
    Z (ou Maj)         : courir
    C                  : s'accroupir / se relever
    Espace             : sauter
    Clic gauche ou P   : tirer (fusil : maintenir pour le tir automatique)
    Clic droit         : viser (viseur holographique / lunette du sniper / lunette x2,5 du RPG avec télémètre)
    A / F (en visant)  : se pencher à gauche / à droite
    R                  : recharger
    Tab                : changer d'arme (arme principale <-> pistolet)
    V                  : près d'un cadavre, prendre son arme (fusil d'assaut, fusil à pompe, pistolet ou RPG) ;
                         près de la batterie anti-aérienne (désert) : s'y installer / la quitter
    X                  : lancer une grenade (chaque ennemi tué en laisse une, ramassée en passant sur lui)
    U                  : ultime — drone Reaper (débloqué après 3 ennemis tués d'un tir à la tête)
    T                  : vue à la 1re / 3e personne
    N                  : lunettes de vision nocturne on/off (partie de nuit)
    M                  : afficher / masquer la carte (position des ennemis)
    G                  : qualité graphique (effets de post-traitement + herbe) on/off
    Échap              : pause (X pour quitter pendant la pause)
    Entrée             : recommencer après la mort

Manette PS5 (DualSense, USB ou Bluetooth) — lue avec pygame (Ursina reste le moteur du jeu).
Installer une fois :  pip install pygame      (sans pygame, le jeu se joue au clavier / à la souris)
    Stick gauche       : se déplacer (analogique, zone morte PAD_DEADZONE) ; L3 (clic du stick) : courir
    Stick droit        : regarder (légère aide à la visée sur les ennemis)
    R2 / L2            : tirer / viser ; en visant, L3 / R3 : se pencher à gauche / à droite
    Rond               : s'accroupir / se relever
    Croix              : sauter ; valider dans le menu ; recommencer après la mort
    Carré              : recharger ; près d'un cadavre : prendre son arme ; batterie AA : s'installer / quitter
    R1                 : lancer une grenade
    Flèche gauche      : ultime — drone Reaper (après 3 éliminations par tir à la tête)
    Triangle           : changer d'arme (arme principale <-> pistolet)
    Flèche bas         : vue à la 1re / 3e personne
    Flèche haut        : lunettes de vision nocturne on/off (partie de nuit)
    Options            : pause (Create pour quitter pendant la pause)
    Croix directionnelle ou stick gauche : choisir l'arme, le moment et la carte dans le menu
    Vibrations au tir, aux dégâts et aux explosions. La manette peut être branchée en cours de partie.

Mode DÉFENSE (grande carte désertique de 80 x 200 m : dunes, tranchées creusées, maison, épaves) :
    une colonne ennemie descend du nord vers la ligne rouge et blanche, devant votre base au sud.
    - tranchées creusées dans le sable : on y descend, on en sort par les rampes aux deux bouts ;
      debout on tire par-dessus le bord, accroupi on est entièrement à couvert
    - chars (canon + mitrailleuse, presque insensibles aux balles : RPG, grenades, missiles du drone)
    - blindés anti-aériens bitubes : tirent sur le drone (et sur vous quand il n'est pas en l'air)
    - fantassins en escouades, dont un porteur de MANPADS (missile sol-air contre le drone) par escouade
    - le RPG est l'arme secondaire (Triangle / Tab) ; roquettes illimitées à la caisse verte (Carré / V)
    - 3 percées de la ligne = la position tombe

Drone Reaper (ultime, pendant toute la manche ; vous réapparaissez au sol à la fin de la manche) :
    Clic gauche / R2 : canon à obus explosifs (paquets de 20 obus, 3 s pour engager le paquet suivant)
    Espace / R1 : missile à guidage infrarouge manuel (6 en tout) : pas de verrouillage, il suit jusqu'à
                  l'impact la tache infrarouge projetée au centre du réticule — gardez la cible dans le viseur
    Clic droit / L2 : zoom · N / Triangle : caméra normale ou thermique (corps chauds en blanc)
    F / L1 : leurres thermiques contre les missiles sol-air · le drone a 100 % de vie (DCA, MANPADS)
    Stick gauche / E,S,Q,D : piloter le drone (il vole dans la direction poussée, avec de l'inertie)
    Stick droit / souris : viser avec le canon et les missiles (accélère en butée, ralentit sur une cible) ;
    le point visé reste stabilisé au sol quand le drone se déplace

Batterie anti-aérienne (désert) : souris / stick droit pour pointer, clic gauche / R2 pour tirer,
    clic droit / L2 pour zoomer, V / Carré pour descendre.

IA des ennemis (de plus en plus redoutable à chaque vague) :
    - perception : champ de vision, ligne de vue (raycast), audition des tirs
    - mémoire de la dernière position connue du joueur, partage d'infos entre alliés
    - recherche de couverture (murs, voitures, arbres, sacs de sable, rochers),
      sortie de couverture pour tirer puis retour à l'abri, rechargement à couvert
    - tirs de couverture coordonnés quand un allié se déplace
    - contournement (flanc), prise en tenaille, repli quand ils sont blessés, esquive
    - grenades pour déloger le joueur caché, fuite devant les grenades
    - escouades : patrouille en formation, alerte partagée, progression par bonds
      (une moitié avance d'abri en abri pendant que l'autre la couvre)
    - armes : fusil d'assaut, fusil à pompe (combat rapproché) ou pistolet ; un soldat par vague
      porte un RPG dans le dos (2 roquettes, explosion de 3 m) à récupérer sur son cadavre
    - la nuit, ils portent des lunettes de vision nocturne et vous voient comme en plein jour
    - déplacement par A* sur une grille de navigation
    - corps articulé animé : marche, course, accroupi, visée, lancer, impacts, chute
"""

import heapq
import math
import random
import sys

from ursina import (
    Ursina, Entity, Text, Sky, DirectionalLight, Vec2, Vec3, Mesh, Shader, Quad, Button, Texture,
    Vec4, camera, color, mouse, held_keys, time, window, application, raycast,
    destroy, invoke, clamp, lerp, scene,
)
from ursina.color import Color
from panda3d.core import loadPrcFileData, Point3, Point2

# Panda3D balaie par défaut tout son cache d'états de rendu à chaque image (~2 ms) ;
# sans ce balayage, chaque état est libéré dès qu'il ne sert plus.
loadPrcFileData('', 'garbage-collect-states 0')
from ursina.collider import Collider, BoxCollider
from panda3d.core import CollisionBox


ARENA = 45          # l'arène va de -ARENA à +ARENA sur x et z
GRAVITY = 22
PLAYER_RADIUS = 0.5
ENEMY_RADIUS = 0.35
EYE_STAND = 1.6     # hauteur des yeux d'un ennemi debout
EYE_CROUCH = 1.0    # hauteur de la tête d'un ennemi accroupi
SHADOW_RES = 1024        # carte d'ombres allégée (4096 puis 2048 auparavant) : ombres un peu plus douces
VSYNC = '--sans-limite' not in sys.argv   # vsync + limite à 60 FPS ; « --sans-limite » pour tout couper
FPS_MAX = 60
# Ursina ignore son option vsync : on règle directement Panda3D, avant l'ouverture de la fenêtre
# (lu à l'ouverture de la fenêtre ; la limite de 60 images/s est posée sur l'horloge dans limit_fps()).
loadPrcFileData('', f"sync-video {'#t' if VSYNC else '#f'}")


def limit_fps():
    """Jamais plus de FPS_MAX images/s (en plus du vsync, utile sur un écran 144 Hz)."""
    if VSYNC:
        from panda3d.core import ClockObject
        clock = ClockObject.getGlobalClock()
        clock.setMode(ClockObject.MLimited)
        clock.setFrameRate(FPS_MAX)

FOG_COLOR = Color(0.72, 0.79, 0.86, 1)
SUN_COLOR = Color(1.0, 0.94, 0.82, 1)


# ---------------------------------------------------------------------------
# Shaders : éclairage (soleil + ciel), ombres douces, brouillard ; post-traitement
# ---------------------------------------------------------------------------

LIT = Shader(language=Shader.GLSL, name='fps_lit', vertex='''
#version 150
uniform struct {
    vec4 position;
    vec3 color;
    vec3 attenuation;
    vec3 spotDirection;
    float spotCosCutoff;
    float spotExponent;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat3 p3d_NormalMatrix;
uniform mat4 p3d_ModelMatrix;
uniform vec2 texture_scale;
uniform vec2 texture_offset;

in vec4 vertex;
in vec3 normal;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;

out vec2 texcoords;
out vec3 vpos;
out vec3 norm;
out vec3 wnorm;
out vec4 shad;
out vec4 vertex_color;

void main() {
    vec3 n = length(normal) > 0.01 ? normal : vec3(0.0, 1.0, 0.0);
    gl_Position = p3d_ModelViewProjectionMatrix * vertex;
    vpos = vec3(p3d_ModelViewMatrix * vertex);
    norm = normalize(p3d_NormalMatrix * n);
    wnorm = normalize(mat3(p3d_ModelMatrix) * n);
    shad = p3d_LightSource[0].shadowViewMatrix * vec4(vpos, 1.0);
    texcoords = p3d_MultiTexCoord0 * texture_scale + texture_offset;
    vertex_color = p3d_Color;
}
''', fragment='''
#version 150
uniform struct {
    vec4 position;
    vec3 color;
    vec3 attenuation;
    vec3 spotDirection;
    float spotCosCutoff;
    float spotExponent;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];

uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
uniform vec4 sky_color;
uniform vec4 ground_color;
uniform vec4 fog_color;
uniform float fog_density;
uniform float specular;
uniform float shadow_texel;
uniform float sun_strength;
uniform float flip_backface;
uniform float hot;          // caméra thermique du drone : 1 = corps chaud (blanc)

in vec2 texcoords;
in vec3 vpos;
in vec3 norm;
in vec3 wnorm;
in vec4 shad;
in vec4 vertex_color;
out vec4 p3d_FragColor;

void main() {
    vec4 base = texture(p3d_Texture0, texcoords) * p3d_ColorScale * vertex_color;
    vec3 N = normalize(norm);
    vec3 WN = normalize(wnorm);
    if (!gl_FrontFacing && flip_backface > 0.5) { N = -N; WN = -WN; }
    vec3 L = normalize(p3d_LightSource[0].position.xyz);
    float diff = clamp(dot(N, L), 0.0, 1.0);

    // ombres douces (PCF 3x3)
    float sh = 0.0;
    if (diff > 0.0) {
        vec4 sc = shad;
        sc.z -= (0.0004 + 0.0015 * (1.0 - diff)) * sc.w;
        // 4 échantillons décalés d'un demi-texel : chacun est déjà filtré (PCF matériel)
        for (int x = 0; x < 2; x++) {
            for (int y = 0; y < 2; y++) {
                sh += textureProj(p3d_LightSource[0].shadowMap,
                                  sc + vec4((vec2(x, y) - 0.5) * shadow_texel * sc.w, 0.0, 0.0));
            }
        }
        sh *= 0.25;
    }

    // lumière du ciel (hémisphérique) + soleil
    float h = clamp(WN.y * 0.5 + 0.5, 0.0, 1.0);
    vec3 amb = mix(ground_color.rgb, sky_color.rgb, h);
    vec3 sun = p3d_LightSource[0].color * diff * sh * sun_strength;
    vec3 col = base.rgb * (amb + sun);

    // reflet spéculaire (carrosseries, vitres)
    vec3 V = normalize(-vpos);
    vec3 H = normalize(L + V);
    col += specular * pow(max(dot(N, H), 0.0), 60.0) * sh * p3d_LightSource[0].color;

    // brouillard atmosphérique
    float d = length(vpos) * fog_density;
    float f = 1.0 - exp(-d * d);
    col = mix(col, fog_color.rgb, clamp(f, 0.0, 1.0));
    if (hot > 0.0) col = mix(col, vec3(1.0), hot);
    p3d_FragColor = vec4(col, base.a);
}
''', default_input={
    'texture_scale': Vec2(1, 1),
    'texture_offset': Vec2(0, 0),
    'specular': 0.0,
    'shadow_texel': 1 / SHADOW_RES,
    'flip_backface': 1.0,
})


POST = Shader(language=Shader.GLSL, name='fps_post', vertex='''
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uv = p3d_MultiTexCoord0;
}
''', fragment='''
#version 150
uniform sampler2D tex;
uniform float fx_on;        // 1 = bloom, étalonnage et vignettage ; 0 = image brute
uniform float nv_on;        // 1 = lunettes de vision nocturne
uniform float nv_time;      // fait bouger le grain de l'image
uniform float zoom;         // grossissement dans la vitre du viseur (1 = aucun)
uniform vec4 zoom_rect;     // vitre du viseur à l'écran : umin, vmin, umax, vmax
uniform vec2 zoom_center;   // point visé (centre du grossissement)
uniform float zoom_round;   // 1 = fenêtre ronde (ellipse inscrite dans zoom_rect)
uniform float ir_on;        // caméra infrarouge du drone (blanc = chaud)
uniform float ir_gain;      // amplification du décor (plus forte la nuit)
in vec2 uv;
out vec4 out_color;

void main() {
    // loupe : seule la vitre du viseur est grossie, la vision périphérique reste normale
    vec2 suv = uv;
    if (zoom > 1.001 && uv.x > zoom_rect.x && uv.x < zoom_rect.z && uv.y > zoom_rect.y && uv.y < zoom_rect.w) {
        vec2 e = (uv - (zoom_rect.xy + zoom_rect.zw) * 0.5) / ((zoom_rect.zw - zoom_rect.xy) * 0.5);
        if (zoom_round < 0.5 || dot(e, e) < 1.0)
            suv = zoom_center + (uv - zoom_center) / zoom;
    }
    vec3 c = texture(tex, suv).rgb;

    if (fx_on > 0.5) {
        // (le halo lumineux « bloom » a été retiré : quasi invisible, 8 lectures de texture par pixel)
        // étalonnage : saturation, contraste, teinte chaude
        float l = dot(c, vec3(0.299, 0.587, 0.114));
        c = mix(vec3(l), c, 1.18);
        c = (c - 0.5) * 1.07 + 0.5;
        c *= vec3(1.03, 1.0, 0.96);

        // vignettage
        vec2 d = uv - 0.5;
        float v = smoothstep(0.95, 0.30, length(d * vec2(1.0, 0.8)) * 1.25);
        c *= mix(0.62, 1.0, v);
    }
    if (nv_on > 0.5) {
        // vision nocturne : lumière amplifiée, image verte, grain, lignes de balayage, masque rond
        vec2 ts = vec2(textureSize(tex, 0));
        float l = dot(texture(tex, suv).rgb, vec3(0.3, 0.59, 0.11));
        l = pow(clamp(l * 6.0, 0.0, 1.0), 0.75);
        float n = fract(sin(dot(uv * ts + nv_time * 91.7, vec2(12.9898, 78.233))) * 43758.5453);
        l = l * 0.88 + (n - 0.5) * 0.14;
        l *= 0.92 + 0.08 * sin(uv.y * ts.y * 1.6);
        c = vec3(0.15, 1.0, 0.3) * l;
        vec2 q = (uv - 0.5) * vec2(ts.x / ts.y, 1.0);
        c *= smoothstep(0.62, 0.5, length(q));
    }
    if (ir_on > 0.5) {
        // caméra thermique : décor en gris sombre, corps chauds (hot = 1 dans l'éclairage) en blanc
        vec3 s = texture(tex, suv).rgb;
        float hotm = step(0.985, min(s.r, min(s.g, s.b)));
        float l = clamp(dot(s, vec3(0.3, 0.59, 0.11)) * ir_gain, 0.0, 1.0);
        vec2 ts = vec2(textureSize(tex, 0));
        float n = fract(sin(dot(uv * ts + nv_time * 53.1, vec2(12.9898, 78.233))) * 43758.5453);
        l = mix(0.08 + l * 0.5, 1.0, hotm) + (n - 0.5) * 0.05;
        c = vec3(l);
    }
    out_color = vec4(clamp(c, 0.0, 1.0), 1.0);
}
''', default_input={
    'nv_on': 0.0,
    'nv_time': 0.0,
    'fx_on': 1.0,
    'zoom': 1.0,
    'zoom_rect': Vec4(0, 0, 0, 0),
    'zoom_center': Vec2(0.5, 0.5),
    'zoom_round': 1.0,
    'ir_on': 0.0,
    'ir_gain': 1.0,
})


# ambiance appliquée à toute la scène (Game.apply_time_of_day)
DAY = dict(sky=Color(0.50, 0.56, 0.66, 1), ground=Color(0.30, 0.28, 0.22, 1), fog=FOG_COLOR, fog_density=0.0085,
           sun_strength=0.95, sun=SUN_COLOR, sky_tint=Color(0.95, 0.97, 1.0, 1), clear=FOG_COLOR)
DESERT_DAY = dict(sky=Color(0.62, 0.62, 0.62, 1), ground=Color(0.50, 0.42, 0.30, 1), fog=Color(0.86, 0.80, 0.70, 1),
                  fog_density=0.0075, sun_strength=1.05, sun=Color(1.0, 0.93, 0.80, 1),
                  sky_tint=Color(1.0, 0.95, 0.86, 1), clear=Color(0.86, 0.80, 0.70, 1))
NIGHT = dict(sky=Color(0.05, 0.06, 0.10, 1), ground=Color(0.02, 0.02, 0.03, 1), fog=Color(0.02, 0.03, 0.05, 1),
             fog_density=0.018, sun_strength=0.35, sun=Color(0.45, 0.55, 0.85, 1),
             sky_tint=Color(0.07, 0.09, 0.16, 1), clear=Color(0.02, 0.03, 0.05, 1))


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def flat(v):
    return Vec3(v.x, 0, v.z)


def flat_dist(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def yaw_to(a, b):
    """Angle (degrés) pour qu'une entité en a regarde vers b sur le plan horizontal."""
    return math.degrees(math.atan2(b.x - a.x, b.z - a.z))


def angle_diff(a, b):
    return (b - a + 180) % 360 - 180


def approach_angle(cur, target, max_step):
    return cur + clamp(angle_diff(cur, target), -max_step, max_step)


def smoothstep(t):
    t = clamp(t, 0, 1)
    return t * t * (3 - 2 * t)


def rgb(r, g, b, a=255):
    return Color(r / 255, g / 255, b / 255, a / 255)


def shade(c, k):
    return Color(clamp(c[0] * k, 0, 1), clamp(c[1] * k, 0, 1), clamp(c[2] * k, 0, 1), c[3])


def value_noise(x, z, seed=0):
    """Bruit doux (somme de sinus) pour varier les couleurs et le relief."""
    return (math.sin(x * 0.11 + seed) * math.cos(z * 0.13 + seed * 1.7)
            + 0.5 * math.sin(x * 0.27 + z * 0.21 + seed * 2.3)
            + 0.25 * math.cos(x * 0.53 - z * 0.47 + seed * 0.7)) / 1.75


def mark_static(root, include_root=False):
    """Ursina parcourt toutes les entités à chaque image pour appeler leur update().
    Celles qui n'en ont pas (décor, os des ennemis, effets...) sont marquées « ignore » :
    la boucle les saute immédiatement."""
    stack = [root] if include_root else list(root.children)
    while stack:
        e = stack.pop()
        if not hasattr(e, 'update') and not hasattr(e, 'input') and not hasattr(e, 'on_click'):
            e.ignore = True
        stack.extend(e.children)


# ---------------------------------------------------------------------------
# Construction de maillages statiques (un seul maillage par matériau = rapide)
# ---------------------------------------------------------------------------

class MeshBuilder:
    MAX_VERTS = 60000

    def __init__(self, tile=None):
        """tile : taille (m) des tuiles spatiales ; chaque tuile devient un maillage séparé
        que Panda3D peut ignorer lorsqu'il est hors du champ de vision."""
        self.tile = tile
        self.chunks = []
        self.current = {}
        self.origin = Vec3(0, 0, 0)
        self.cos, self.sin = 1.0, 0.0

    def _chunk(self, key):
        ch = self.current.get(key)
        if ch is None or len(ch[0]) > self.MAX_VERTS:
            ch = ([], [], [], [])
            self.chunks.append(ch)
            self.current[key] = ch
        return ch

    def xf(self, origin=(0, 0, 0), yaw=0):
        """Transformation locale -> monde (translation + rotation autour de y)."""
        self.origin = Vec3(*origin)
        r = math.radians(yaw)
        self.cos, self.sin = math.cos(r), math.sin(r)

    def _p(self, p):
        x, y, z = p
        c, s = self.cos, self.sin
        return Vec3(self.origin.x + x * c + z * s, self.origin.y + y, self.origin.z - x * s + z * c)

    def _dir(self, d):
        x, y, z = d
        c, s = self.cos, self.sin
        return Vec3(x * c + z * s, y, -x * s + z * c)

    def tri(self, a, b, c, col, n=None, uvs=((0, 0), (0, 0), (0, 0)), normals=None, local=True):
        if local:
            a, b, c = self._p(a), self._p(b), self._p(c)
            if n is not None:
                n = self._dir(n)
            if normals is not None:
                normals = [self._dir(k) for k in normals]
        face = (b - a).cross(c - a)
        if face.length() < 1e-9:
            return
        face = face.normalized()
        if n is None:
            n = face
        cols = list(col) if isinstance(col, (list, tuple)) else [col, col, col]
        normals = list(normals) if normals is not None else [n, n, n]
        uvs = list(uvs)
        if face.dot(n) > 0:        # ordre des sommets attendu par Panda3D (repère y-up-left)
            b, c = c, b
            for lst in (cols, normals, uvs):
                lst[1], lst[2] = lst[2], lst[1]
        if self.tile:
            t = self.tile
            key = (int((a.x + b.x + c.x) / 3 // t), int((a.z + b.z + c.z) / 3 // t))
        else:
            key = 0
        v, cc, u, nn = self._chunk(key)
        v.extend((a, b, c))
        nn.extend(normals)
        cc.extend(cols)
        u.extend(uvs)

    def quad(self, a, b, c, d, col, n=None, uvs=((0, 0), (1, 0), (1, 1), (0, 1)), local=True):
        self.tri(a, b, c, col, n, (uvs[0], uvs[1], uvs[2]), local=local)
        self.tri(a, c, d, col, n, (uvs[0], uvs[2], uvs[3]), local=local)

    def box(self, center, size, col, tile=None, jitter=0.0, top=True, bottom=False, rx=0.0):
        """Pavé ; rx : inclinaison (degrés) autour de l'axe x passant par son centre."""
        cx, cy, cz = center
        cr, sr = math.cos(math.radians(rx)), math.sin(math.radians(rx))

        def rot(y, z):
            return (y * cr - z * sr, y * sr + z * cr) if rx else (y, z)
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        faces = [
            (Vec3(1, 0, 0), [(hx, -hy, -hz), (hx, -hy, hz), (hx, hy, hz), (hx, hy, -hz)], (2, 1)),
            (Vec3(-1, 0, 0), [(-hx, -hy, hz), (-hx, -hy, -hz), (-hx, hy, -hz), (-hx, hy, hz)], (2, 1)),
            (Vec3(0, 0, 1), [(hx, -hy, hz), (-hx, -hy, hz), (-hx, hy, hz), (hx, hy, hz)], (0, 1)),
            (Vec3(0, 0, -1), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz)], (0, 1)),
        ]
        if top:
            faces.append((Vec3(0, 1, 0), [(-hx, hy, -hz), (hx, hy, -hz), (hx, hy, hz), (-hx, hy, hz)], (0, 2)))
        if bottom:
            faces.append((Vec3(0, -1, 0), [(-hx, -hy, hz), (hx, -hy, hz), (hx, -hy, -hz), (-hx, -hy, -hz)], (0, 2)))
        for n, corners, axes in faces:
            if rx:
                n = Vec3(n.x, *rot(n.y, n.z))
                corners = [(x, *rot(y, z)) for x, y, z in corners]
            pts = [Vec3(cx + x, cy + y, cz + z) for x, y, z in corners]
            fc = shade(col, 1 + random.uniform(-jitter, jitter)) if jitter else col
            if tile:   # coordonnées de texture en mètres (briques continues d'un mur à l'autre)
                wp = [self._p(p) for p in pts]
                uvs = [(p[axes[0]] / tile, p[axes[1]] / tile) for p in wp]
                self.quad(*pts, fc, n, uvs)
            else:
                self.quad(*pts, fc, n)

    def cylinder(self, base, r, h, col, seg=10, axis='y', caps=True, col_cap=None):
        bx, by, bz = base

        def pt(ang, t, rr=r):
            ca, sa = math.cos(ang) * rr, math.sin(ang) * rr
            if axis == 'y':
                return Vec3(bx + ca, by + t, bz + sa), Vec3(math.cos(ang), 0, math.sin(ang))
            if axis == 'x':
                return Vec3(bx + t, by + ca, bz + sa), Vec3(0, math.cos(ang), math.sin(ang))
            return Vec3(bx + ca, by + sa, bz + t), Vec3(math.cos(ang), math.sin(ang), 0)

        axis_v = {'y': Vec3(0, 1, 0), 'x': Vec3(1, 0, 0), 'z': Vec3(0, 0, 1)}[axis]
        c0 = pt(0, 0, 0)[0]
        c1 = pt(0, h, 0)[0]
        for i in range(seg):
            a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            p00, n0 = pt(a0, 0)
            p01, _ = pt(a0, h)
            p10, n1 = pt(a1, 0)
            p11, _ = pt(a1, h)
            mid = (n0 + n1).normalized()
            self.tri(p00, p10, p11, col, mid, normals=[n0, n1, n1])
            self.tri(p00, p11, p01, col, mid, normals=[n0, n1, n0])
            if caps:
                self.tri(c1, p01, p11, col_cap or col, axis_v)
                self.tri(c0, p00, p10, col_cap or col, -axis_v)

    def tube(self, center, r_in, r_out, length, col, seg=20, col_in=None):
        """Tube creux le long de z (corps de viseur rond) : parois extérieure et intérieure + deux bagues."""
        cx, cy, cz = center
        z0, z1 = cz - length / 2, cz + length / 2
        for i in range(seg):
            a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            n0, n1 = Vec3(c0, s0, 0), Vec3(c1, s1, 0)
            nm = (n0 + n1).normalized()

            def p(r, c, s_, z):
                return Vec3(cx + c * r, cy + s_ * r, z)
            self.quad(p(r_out, c0, s0, z0), p(r_out, c1, s1, z0), p(r_out, c1, s1, z1), p(r_out, c0, s0, z1), col, nm)
            self.quad(p(r_in, c0, s0, z0), p(r_in, c1, s1, z0), p(r_in, c1, s1, z1), p(r_in, c0, s0, z1),
                      col_in or shade(col, 0.6), -nm)
            for z, n in ((z1, Vec3(0, 0, 1)), (z0, Vec3(0, 0, -1))):
                self.quad(p(r_in, c0, s0, z), p(r_out, c0, s0, z), p(r_out, c1, s1, z), p(r_in, c1, s1, z), col, n)

    def cone(self, base, r, h, col, seg=8, jitter=0.0):
        bx, by, bz = base
        apex = Vec3(bx, by + h, bz)
        for i in range(seg):
            a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            p0 = Vec3(bx + math.cos(a0) * r, by, bz + math.sin(a0) * r)
            p1 = Vec3(bx + math.cos(a1) * r, by, bz + math.sin(a1) * r)
            am = (a0 + a1) / 2
            n = Vec3(math.cos(am) * h, r, math.sin(am) * h).normalized()
            fc = shade(col, 1 + random.uniform(-jitter, jitter)) if jitter else col
            self.tri(p0, p1, apex, fc, n)
            self.tri(p0, Vec3(bx, by, bz), p1, shade(col, 0.6), Vec3(0, -1, 0))

    def blob(self, center, radii, col, seg=7, rings=5, jitter=0.1, rough=0.12, rng=random, dome=False):
        """Ellipsoïde à facettes irrégulières (feuillage, rochers, sacs de sable).
        dome : seulement la moitié supérieure (dunes posées sur le sol : rien de caché à dessiner)."""
        cx, cy, cz = center
        rx, ry, rz = radii
        grid = []
        for j in range(rings + 1):
            phi = (math.pi * 0.56 if dome else math.pi) * j / rings
            row = []
            for i in range(seg):
                th = 2 * math.pi * i / seg
                k = 1 + (rng.uniform(-rough, rough) if 0 < j < rings or (dome and j == rings) else 0)
                row.append(Vec3(cx + math.sin(phi) * math.cos(th) * rx * k,
                                cy + math.cos(phi) * ry * k,
                                cz + math.sin(phi) * math.sin(th) * rz * k))
            grid.append(row)
        cen = Vec3(cx, cy, cz)
        for j in range(rings):
            for i in range(seg):
                a, b = grid[j][i], grid[j][(i + 1) % seg]
                c, d = grid[j + 1][(i + 1) % seg], grid[j + 1][i]
                for t in ((a, b, c), (a, c, d)):
                    out = (t[0] + t[1] + t[2]) / 3 - cen
                    if out.length() < 1e-6:
                        continue
                    self.tri(t[0], t[1], t[2], shade(col, 1 + rng.uniform(-jitter, jitter)), out.normalized())

    def mesh(self):
        v, c, u, n = self.chunks[0]
        return Mesh(vertices=v, triangles=list(range(len(v))), colors=c, uvs=u, normals=n, mode='triangle')

    def build(self, parent=None, texture=None, specular=0.0, double_sided=False, cast_shadows=True):
        ents = []
        for v, c, u, n in self.chunks:
            if not v:
                continue
            m = Mesh(vertices=v, triangles=list(range(len(v))), colors=c, uvs=u, normals=n, mode='triangle')
            e = Entity(parent=parent, model=m, texture=texture, shader=LIT, double_sided=double_sided)
            e.ignore = True
            e.center = sum(v, Vec3(0, 0, 0)) / len(v)       # sert à masquer l'herbe lointaine
            e.set_shader_input('specular', specular)
            if double_sided and not cast_shadows:
                e.set_shader_input('flip_backface', 0.0)   # herbe : même éclairage des deux côtés
            if not cast_shadows:
                e.hide(0b0001)
            ents.append(e)
        return ents


# ---------------------------------------------------------------------------
# Monde : décor, collisions, navigation, points de couverture
# ---------------------------------------------------------------------------

class Box:
    def __init__(self, cx, cz, sx, sz, h):
        self.x0, self.x1 = cx - sx / 2, cx + sx / 2
        self.z0, self.z1 = cz - sz / 2, cz + sz / 2
        self.h = h
        self.cx, self.cz = cx, cz

    def circle_overlap(self, x, z, r):
        px = clamp(x, self.x0, self.x1)
        pz = clamp(z, self.z0, self.z1)
        return (x - px) ** 2 + (z - pz) ** 2 < r * r


TRENCH_DEPTH = 1.35    # profondeur des tranchées creusées (debout on voit par-dessus, accroupi on est caché)
TRENCH_WIDTH = 2.0
TRENCH_RAMP = 3.0      # longueur des rampes aux deux bouts


class Pit:
    """Tranchée creusée : rectangle (x0..x1, z0..z1) orienté le long de x ou de z."""
    def __init__(self, x0, x1, z0, z1, along_x):
        self.x0, self.x1, self.z0, self.z1 = x0, x1, z0, z1
        self.along_x = along_x


class World:
    CELL = 1.0

    def __init__(self, map_name='village', mode='survie'):
        self.mode = mode
        if mode == 'defense':
            map_name = 'defense'   # la défense se joue sur sa propre grande carte désertique
        self.map = map_name
        self.desert = map_name in ('desert', 'defense')
        # demi-dimensions de la zone jouable (x, z) : carrée en survie, longue (80 x 200 m) en défense
        self.hx, self.hz = (40.0, 100.0) if map_name == 'defense' else (float(ARENA), float(ARENA))
        self.spawn = Vec3(0, 0, -self.hz + 6) if map_name == 'defense' else Vec3(0, 0, -40)
        self.defense_z = -self.hz + 22          # ligne à tenir (défense)
        # défense : deux axes dégagés pour les blindés (rien n'y est construit)
        self.lanes = [Box(x, 0, 5.2, self.hz * 2, 1) for x in LANES] if mode == 'defense' else []
        self.pits = []             # tranchées creusées dans le sable (défense)
        self.ammo_point = None     # caisse de roquettes (défense)
        self.aa = None             # batterie anti-aérienne (carte désert)
        self.smoke_points = []     # épaves qui fument
        self.boxes = []
        self._col_boxes = []
        self.level = Entity()   # parent de tout ce qui bloque la vue / les balles
        self.rng = random.Random(1234)
        # décor fusionné : un maillage par matériau (le découper en tuiles s'est révélé plus lent)
        self.brick = MeshBuilder()
        self.plain = MeshBuilder()
        self.shiny = MeshBuilder()
        self.foliage = MeshBuilder()
        self.build()
        self.build_colliders()
        self.brick.build(self.level, texture='brick')
        self.plain.build(self.level)
        self.shiny.build(self.level, specular=0.7)
        self.foliage.build(self.level)
        self.build_box_grid()
        self.build_nav()
        self.build_cover()
        self.grass = self.build_grass()
        mark_static(self.level)

    # -- collisions pour le décor --------------------------------------------
    def add_box(self, cx, cz, sx, sz, h, collider=True):
        self.boxes.append(Box(cx, cz, sx, sz, h))
        if collider:
            self.add_collider(cx, h / 2, cz, sx, h, sz)

    def add_collider(self, cx, cy, cz, sx, sy, sz):
        self._col_boxes.append((cx, cy, cz, sx, sy, sz))

    def build_colliders(self):
        """Toutes les boîtes de collision du décor dans UNE seule entité (au lieu d'une entité par obstacle)."""
        self.collision = Entity(parent=self.level, name='collisions_decor')
        solids = [CollisionBox(Vec3(cx, cy, cz), max(sx / 2, 0.001), max(sy / 2, 0.001), max(sz / 2, 0.001))
                  for cx, cy, cz, sx, sy, sz in self._col_boxes]
        self.collision.collider = Collider(self.collision, solids)

    def in_lane(self, cx, cz, sx, sz):
        return any(not (cx + sx / 2 < l.x0 or cx - sx / 2 > l.x1) for l in self.lanes)

    def area_free(self, cx, cz, sx, sz, margin=1.2):
        probe = Box(cx, cz, sx + 2 * margin, sz + 2 * margin, 1)
        if self.lanes and self.in_lane(cx, cz, sx + 2 * margin, sz + 2 * margin):
            return False
        for b in self.boxes:
            if not (probe.x1 < b.x0 or probe.x0 > b.x1 or probe.z1 < b.z0 or probe.z0 > b.z1):
                return False
        for pt in self.pits:
            if not (probe.x1 < pt.x0 - 1 or probe.x0 > pt.x1 + 1 or probe.z1 < pt.z0 - 1 or probe.z0 > pt.z1 + 1):
                return False
        return abs(cx) + sx / 2 < self.hx - 1.5 and abs(cz) + sz / 2 < self.hz - 1.5

    # -- éléments --------------------------------------------------------------
    def wall(self, cx, cz, sx, sz, h, tint=None, low=False):
        tint = tint or (rgb(205, 190, 175) if not low else rgb(175, 172, 168))
        self.add_box(cx, cz, sx, sz, h)
        self.brick.xf()
        self.brick.box((cx, h / 2, cz), (sx, h, sz), tint, tile=2.0, top=False)
        self.plain.xf()
        cap = rgb(200, 198, 192) if not low else rgb(185, 183, 178)
        self.plain.box((cx, h + 0.06, cz), (sx + 0.14, 0.12, sz + 0.14), cap, jitter=0.03)
        self.plain.box((cx, 0.1, cz), (sx + 0.08, 0.2, sz + 0.08), rgb(120, 118, 112))

    def crate(self, cx, cz, size=1.3):
        self.add_box(cx, cz, size, size, size)
        b = self.plain
        b.xf((cx, 0, cz), 0)
        b.box((0, size / 2, 0), (size, size, size), rgb(160, 115, 65), jitter=0.06)   # simple cube de bois
        b.xf()

    def tree(self, x, z, collide=True, scale=1.0, y=0.0):
        rng = self.rng
        pine = rng.random() < 0.45
        h = rng.uniform(2.4, 3.3) * scale
        r = 0.27 * scale
        self.plain.xf()
        self.plain.cylinder((x, y - 0.2, z), r, h + 1.2, rgb(95, 68, 45), seg=6, caps=False)
        f = self.foliage
        f.xf()
        if pine:
            greens = [rgb(40, 85, 50), rgb(50, 100, 55), rgb(35, 75, 45)]
            base = y + h * 0.45
            for k in range(3):
                f.cone((x, base + k * 1.35 * scale, z), (2.0 - k * 0.5) * scale, 2.1 * scale,
                       rng.choice(greens), seg=7, jitter=0.12)
        else:
            greens = [rgb(70, 125, 50), rgb(85, 140, 55), rgb(60, 110, 45), rgb(95, 145, 60)]
            top = y + h + 0.5 * scale
            f.blob((x, top, z), (1.5 * scale, 1.25 * scale, 1.5 * scale), rng.choice(greens), seg=6, rings=4, rng=rng)
            for _ in range(2):
                a = rng.uniform(0, 6.28)
                d = rng.uniform(0.7, 1.2) * scale
                rad = rng.uniform(0.9, 1.25) * scale
                f.blob((x + math.cos(a) * d, top + rng.uniform(-0.5, 0.7) * scale, z + math.sin(a) * d),
                       (rad, rad * 0.85, rad), rng.choice(greens), seg=6, rings=4, rng=rng)
        if collide:
            self.add_box(x, z, 0.7 * scale, 0.7 * scale, 6)

    def car(self, x, z, yaw, paint):
        sx, sz = (2.0, 4.4) if yaw % 180 == 0 else (4.4, 2.0)
        self.add_box(x, z, sx, sz, 1.5)
        # voiture simplifiée : caisse, habitacle vitré, toit et 4 roues carrées
        s, p = self.shiny, self.plain
        s.xf((x, 0, z), yaw)
        p.xf((x, 0, z), yaw)
        s.box((0, 0.68, 0), (1.86, 0.62, 4.3), paint)                       # caisse
        s.box((0, 1.2, -0.25), (1.66, 0.5, 2.2), rgb(40, 55, 70))           # habitacle vitré
        s.box((0, 1.47, -0.25), (1.62, 0.06, 2.1), shade(paint, 0.97))      # toit
        dark = rgb(30, 30, 32)
        for sgn in (-1, 1):
            for wz in (1.35, -1.35):
                p.box((sgn * 0.84, 0.36, wz), (0.26, 0.7, 0.7), dark, top=False)
        p.xf()
        s.xf()

    def sandbags(self, cx, cz, length, along_x=True):
        sx, sz = (length, 0.8) if along_x else (0.8, length)
        self.add_box(cx, cz, sx, sz, 1.12)
        khaki = rgb(160, 145, 105)
        self.plain.xf()
        for layer in range(3):       # trois rangées de sacs (une boîte chacune, légèrement en retrait)
            inset = 0.06 * layer
            bx, bz = (sx - inset, sz - 0.1 - inset) if along_x else (sx - 0.1 - inset, sz - inset)
            self.plain.box((cx, 0.19 + layer * 0.36, cz), (bx, 0.36, bz), shade(khaki, 1 - 0.05 * layer), jitter=0.05)

    def barrels(self, cx, cz):
        cols = [rgb(170, 45, 35), rgb(40, 80, 150), rgb(120, 90, 50), rgb(60, 110, 70)]
        offs = [(0, 0), (0.65, 0.1), (0.3, 0.6)][:self.rng.randint(2, 3)]
        self.plain.xf()
        for ox, oz in offs:
            c = self.rng.choice(cols)
            self.plain.cylinder((cx + ox, 0, cz + oz), 0.3, 0.95, c, seg=8, col_cap=shade(c, 0.8))
        self.add_box(cx + 0.3, cz + 0.3, 1.3, 1.3, 0.95)

    def rock(self, cx, cz, size=1.0):
        self.plain.xf()
        self.plain.blob((cx, 0.35 * size, cz), (1.2 * size, 0.95 * size, 1.0 * size), rgb(125, 122, 115),
                        seg=6, rings=4, jitter=0.12, rough=0.18, rng=self.rng)
        self.add_box(cx, cz, 2.0 * size, 1.7 * size, 1.25 * size)

    def build_defense_line(self):
        """Ligne à tenir (poteaux rouges et blancs), caisse de roquettes et traces de chenilles sur les axes."""
        p = self.plain
        p.xf()
        n = int(2 * self.hx / 2.9)
        for k in range(n + 1):
            x = -self.hx + 1.5 + k * 2.9
            if x > self.hx - 1:
                break
            p.box((x, 0.5, self.defense_z), (0.12, 1.0, 0.12), rgb(200, 40, 35) if k % 2 else rgb(235, 235, 230))
        up = Vec3(0, 1, 0)
        for lx in LANES:
            for sx in (-1.3, 1.3):         # ornières laissées par les chenilles
                x = lx + sx
                z0, z1 = -self.hz + 1, self.hz - 1
                p.quad(Vec3(x - 0.35, 0.015, z0), Vec3(x + 0.35, 0.015, z0),
                       Vec3(x + 0.35, 0.015, z1), Vec3(x - 0.35, 0.015, z1), rgb(150, 125, 90), up)
        cx, cz = -4.0, self.spawn.z + 3        # caisse de roquettes près du point de départ
        self.add_box(cx, cz, 1.6, 1.0, 0.9)
        p.box((cx, 0.45, cz), (1.6, 0.9, 1.0), rgb(80, 90, 55), jitter=0.05)
        p.box((cx, 0.92, cz), (1.64, 0.06, 1.04), rgb(65, 72, 45))
        p.box((cx, 0.6, cz + 0.51), (0.9, 0.25, 0.02), rgb(220, 200, 60))    # marquage jaune
        self.ammo_point = Vec3(cx, 0, cz)

    # -- terrain -------------------------------------------------------------
    def build_ground(self):
        """Sol limité à l'arène (rien n'est construit hors des murs)."""
        pad = 16 if self.desert else 2          # désert : le sable continue sous les dunes
        hx, hz = self.hx + pad, self.hz + pad
        n = 32
        b = MeshBuilder()
        up = Vec3(0, 1, 0)
        cache = {}

        desert = self.desert
        if desert:
            n = 48

        def ripple(x, z):
            # ondulations du sable : ne servent qu'à l'éclairage (le sol reste plat pour le jeu)
            return value_noise(x * 0.09, z * 0.09, 3) * 1.4 + math.sin(x * 0.55 + z * 0.3
                                                                        + value_noise(x * 0.2, z * 0.2, 4) * 3) * 0.12

        step = 2 * max(hx, hz) / n
        # lignes de la grille : pas régulier + bords des tranchées (chaque case est dedans ou dehors)
        xs = sorted(set([-hx + k * step for k in range(int(2 * hx / step) + 1)] + [hx]
                        + [v for p in self.pits for v in (p.x0, p.x1)]))
        zs = sorted(set([-hz + k * step for k in range(int(2 * hz / step) + 1)] + [hz]
                        + [v for p in self.pits for v in (p.z0, p.z1)]))

        def vert(i, j):
            if (i, j) not in cache:
                x, z = xs[i], zs[j]
                nz = value_noise(x, z, 1) * 0.5 + 0.5
                dry = value_noise(x * 1.7, z * 1.7, 5) * 0.5 + 0.5
                if desert:
                    col = Color(lerp(0.80, 0.93, nz) - dry * 0.05, lerp(0.66, 0.78, nz) - dry * 0.05,
                                lerp(0.45, 0.55, nz) - dry * 0.04, 1)
                    e = 0.5
                    nrm = Vec3(ripple(x - e, z) - ripple(x + e, z), 2 * e, ripple(x, z - e) - ripple(x, z + e))
                    cache[(i, j)] = (Vec3(x, 0, z), col, (x / 4, z / 4), nrm.normalized())
                else:
                    col = Color(lerp(0.42, 0.6, nz) + dry * 0.14, lerp(0.7, 0.85, nz), lerp(0.42, 0.55, nz), 1)
                    cache[(i, j)] = (Vec3(x, 0, z), col, (x / 3, z / 3), up)
            return cache[(i, j)]

        for i in range(len(xs) - 1):
            for j in range(len(zs) - 1):
                if self.pit_at((xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2):
                    continue                   # trou de la tranchée (dessinée à part)
                q = [vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)]
                for a, bb, c in ((0, 1, 2), (0, 2, 3)):
                    b.tri(q[a][0], q[bb][0], q[c][0], [q[a][1], q[bb][1], q[c][1]], up,
                          (q[a][2], q[bb][2], q[c][2]), normals=[q[a][3], q[bb][3], q[c][3]], local=False)
        # le sol ne projette aucune ombre : on l'exclut de la passe d'ombres
        b.build(self.level, texture=sand_texture() if desert else 'grass', cast_shadows=False)
        # collisionneur du sol pour les impacts de balles (percé au droit des tranchées)
        if not self.pits:
            self.add_collider(0, -0.05, 0, 2 * hx, 0.1, 2 * hz)
        else:
            bx = sorted(set([-hx, hx] + [v for p in self.pits for v in (p.x0, p.x1)]))
            bz = sorted(set([-hz, hz] + [v for p in self.pits for v in (p.z0, p.z1)]))
            th = TRENCH_DEPTH + 0.3
            for j in range(len(bz) - 1):
                z0, z1 = bz[j], bz[j + 1]
                run = None
                for i in range(len(bx) - 1):
                    solid = not self.pit_at((bx[i] + bx[i + 1]) / 2, (z0 + z1) / 2)
                    if solid and run is None:
                        run = bx[i]
                    if (not solid or i == len(bx) - 2) and run is not None:
                        end = bx[i + 1] if solid else bx[i]
                        self.add_collider((run + end) / 2, -th / 2, (z0 + z1) / 2, end - run, th, z1 - z0)
                        run = None
            for p in self.pits:          # fond des tranchées
                self.add_collider((p.x0 + p.x1) / 2, -TRENCH_DEPTH - 0.1, (p.z0 + p.z1) / 2,
                                  p.x1 - p.x0, 0.2, p.z1 - p.z0)

    def road(self, z0, z1):
        b = self.plain
        b.xf()
        up = Vec3(0, 1, 0)
        x0, x1 = -ARENA + 0.6, ARENA - 0.6
        k = 0
        x = x0
        while x < x1:
            nx = min(x + 3, x1)
            c = shade(rgb(62, 62, 66), 1 + 0.06 * value_noise(x, z0, 2))
            b.quad(Vec3(x, 0.02, z0), Vec3(nx, 0.02, z0), Vec3(nx, 0.02, z1), Vec3(x, 0.02, z1), c, up)
            if k % 2 == 0:
                zc = (z0 + z1) / 2
                b.quad(Vec3(x + 0.3, 0.03, zc - 0.08), Vec3(nx - 0.3, 0.03, zc - 0.08),
                       Vec3(nx - 0.3, 0.03, zc + 0.08), Vec3(x + 0.3, 0.03, zc + 0.08), rgb(230, 225, 200), up)
            k += 1
            x = nx
        for zz in (z0 - 0.12, z1 + 0.12):   # bordures
            b.box(((x0 + x1) / 2, 0.06, zz), (x1 - x0, 0.12, 0.24), rgb(170, 168, 160))

    def build(self):
        if self.map == 'defense':
            self.define_pits()
        self.build_ground()
        if self.map == 'defense':
            self.build_defense_map()
        elif self.desert:
            self.build_desert()
        else:
            self.build_village()

    def build_village(self):
        # enceinte avec piliers
        L = ARENA * 2
        for cx, cz, sx, sz in [(0, ARENA, L + 1, 1), (0, -ARENA, L + 1, 1), (ARENA, 0, 1, L + 1), (-ARENA, 0, 1, L + 1)]:
            self.wall(cx, cz, sx, sz, 4, tint=rgb(190, 180, 168))
        self.plain.xf()
        for k in range(-5, 6):
            t = k * 9
            for px, pz in [(t, ARENA), (t, -ARENA), (ARENA, t), (-ARENA, t)]:
                self.plain.box((px, 2.2, pz), (1.3, 4.4, 1.3), rgb(165, 160, 150), jitter=0.04)

        self.road(12.5, 16.5)

        # grands murs
        for cx, cz, sx, sz in [(-13, 9, 11, 1), (13, 9, 11, 1), (0, 22, 1, 7), (-25, -6, 1, 13), (25, -6, 1, 13),
                               (-9, -16, 9, 1), (9, -16, 9, 1), (-31, 25, 13, 1), (31, 25, 13, 1),
                               (-34, -27, 1, 11), (34, -27, 1, 11),
                               (-7, 32, 1, 9), (7, 32, 1, 9), (-4.75, 36.5, 5.5, 1), (4.75, 36.5, 5.5, 1)]:
            if not self.in_lane(cx, cz, sx, sz):
                self.wall(cx, cz, sx, sz, 3)
        # toit de la maison du nord (au-dessus des têtes)
        self.plain.xf()
        self.plain.box((0, 3.2, 32), (15.2, 0.25, 10), rgb(140, 70, 55), jitter=0.02, bottom=True)

        # murets bas
        for cx, cz, sx, sz in [(0, 0, 7, 0.8), (-18, 22, 5, 0.8), (18, 22, 5, 0.8), (-16, -29, 0.8, 5),
                               (16, -29, 0.8, 5), (-37, 7, 5, 0.8), (37, 7, 5, 0.8), (0, -27, 6, 0.8)]:
            if not self.in_lane(cx, cz, sx, sz):
                self.wall(cx, cz, sx, sz, 1.3, low=True)

        # voitures
        paints = [rgb(180, 30, 35), rgb(30, 70, 150), rgb(220, 220, 215), rgb(40, 40, 45),
                  rgb(200, 150, 30), rgb(60, 120, 80), rgb(120, 125, 135)]
        for x, z, yaw in [(-30, 14.3, 90), (-12, 15, 90), (6, 13.8, 90), (22, 15.5, 90), (38, 14.5, 90),
                          (28, -39, 0), (31.5, -38.5, 0), (-28, -38, 0), (-22, -8, 0), (18, -7, 0),
                          (-39, 33, 90), (40, 38, 0)]:
            if self.area_free(x, z, 4.4, 4.4, margin=0.3):
                self.car(x, z, yaw, self.rng.choice(paints))

        # caisses
        for x, z in [(-4, 10.3), (4, 10.3), (-18, 0), (18, 0), (-26, 18), (26, 18), (-10, -22), (10, -22),
                     (-24, -34), (24, -34), (0, 40), (-38, -10), (38, -10), (-13, 30), (13, 30), (-1.2, 10.3)]:
            if self.area_free(x, z, 1.3, 1.3, margin=0.2):
                self.crate(x, z)

        # sacs de sable
        for x, z, l, ax in [(-6, -8, 4, True), (7, -7.5, 4, True), (-39, -15, 4, False), (39, -18, 4, False),
                            (-20, 34, 4, True), (20, 34, 4, True), (0, -35, 3, True)]:
            if self.area_free(x, z, 4.2, 4.2, margin=0.2):
                self.sandbags(x, z, l, ax)

        # rochers, tonneaux
        for x, z, s in [(-15, -38, 1.0), (14, 3, 0.9), (-30, 3, 1.1), (35, 30, 1.0), (-8, 20, 0.8)]:
            if self.area_free(x, z, 2.5 * s, 2.5 * s, margin=0.4):
                self.rock(x, z, s)
        for x, z in [(-20, -20), (20, -21), (-36, 38), (5, 26), (-3, -20), (30, 5)]:
            if self.area_free(x, z, 1.4, 1.4, margin=0.4):
                self.barrels(x, z)

        # arbres dans l'arène (couverture fine)
        placed = tries = 0
        while placed < 26 and tries < 800:
            tries += 1
            x = self.rng.uniform(-ARENA + 3, ARENA - 3)
            z = self.rng.uniform(-ARENA + 3, ARENA - 3)
            if 11.5 < z < 17.5:              # pas sur la route
                continue
            if abs(x) < 9 and z < -30:       # zone de départ dégagée
                continue
            if not self.area_free(x, z, 0.7, 0.7, margin=1.8):
                continue
            self.tree(x, z, scale=self.rng.uniform(0.9, 1.25))
            placed += 1

    # -- carte désert ----------------------------------------------------------
    SAND = rgb(200, 172, 128)
    AA_POS = Vec3(14, 0, -31)        # batterie anti-aérienne (près du point de départ)

    def berm(self, b, L, zc, w, tw, h, col):
        """Talus de sable à section trapézoïdale, le long de l'axe x local (centre z = zc)."""
        hl, e = L / 2, (w / 2 - tw)
        z0, z1, t0, t1 = zc - w / 2, zc + w / 2, zc - tw, zc + tw
        faces = [
            ([(-hl, 0, z1), (hl, 0, z1), (hl - e, h, t1), (-hl + e, h, t1)], (0, tw * 2, 1)),
            ([(hl, 0, z0), (-hl, 0, z0), (-hl + e, h, t0), (hl - e, h, t0)], (0, tw * 2, -1)),
            ([(-hl + e, h, t0), (-hl + e, h, t1), (hl - e, h, t1), (hl - e, h, t0)], (0, 1, 0)),
            ([(hl, 0, z1), (hl, 0, z0), (hl - e, h, t0), (hl - e, h, t1)], (1, tw * 2, 0)),
            ([(-hl, 0, z0), (-hl, 0, z1), (-hl + e, h, t1), (-hl + e, h, t0)], (-1, tw * 2, 0)),
        ]
        for pts, n in faces:
            b.quad(*[Vec3(*p) for p in pts], shade(col, 1 + self.rng.uniform(-0.04, 0.04)), Vec3(*n).normalized())

    def trench(self, x0, z0, x1, z1):
        """Tranchée : couloir de 1,7 m bordé de parois en planches, de talus de sable et de sacs de sable.
        À l'intérieur, accroupi, on est à couvert ; debout, on voit (et on tire) par-dessus."""
        along_x = abs(x1 - x0) >= abs(z1 - z0)
        L = abs(x1 - x0) if along_x else abs(z1 - z0)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        b = self.plain
        b.xf((cx, 0, cz), 0 if along_x else 90)
        wood, post = rgb(120, 92, 60), rgb(85, 65, 45)
        khaki = rgb(170, 150, 108)
        for side in (-1, 1):
            b.box((0, 0.5, side * 0.91), (L, 1.0, 0.1), wood, jitter=0.05)                 # parois en planches
            for k in range(int(L // 2) + 1):
                b.box((-L / 2 + 0.2 + k * (L - 0.4) / max(1, int(L // 2)), 0.55, side * 0.84),
                      (0.1, 1.1, 0.08), post)                                              # poteaux
            self.berm(b, L, side * 1.75, 2.1, 0.45, 1.02, self.SAND)                        # talus
            for layer in range(2):                                                        # sacs de sable
                b.box((0, 1.14 + layer * 0.24, side * (1.12 + layer * 0.06)), (L - 0.2 * layer, 0.24, 0.55),
                      shade(khaki, 1 - 0.06 * layer), jitter=0.05)
            if along_x:
                self.add_box(cx, cz + side * 1.35, L, 1.0, 1.38)
            else:
                self.add_box(cx + side * 1.35, cz, 1.0, L, 1.38)
        # fond de la tranchée : sable piétiné et caillebotis
        up = Vec3(0, 1, 0)
        dark = rgb(160, 128, 88)
        b.quad(Vec3(-L / 2, 0.012, -0.86), Vec3(L / 2, 0.012, -0.86), Vec3(L / 2, 0.012, 0.86),
               Vec3(-L / 2, 0.012, 0.86), dark, up)
        for k in range(int(L / 0.45)):
            b.box((-L / 2 + 0.25 + k * 0.45, 0.035, 0), (0.14, 0.04, 1.1), rgb(110, 85, 58))
        b.xf()

    def dune(self, cx, cz, rx, rz, h, collide=True):
        """Dune de sable (dôme lisse). Assez haute pour s'y abriter ; on ne peut pas l'escalader."""
        col = shade(self.SAND, self.rng.uniform(0.95, 1.05))
        self.plain.xf()
        self.plain.blob((cx, -h * 0.12, cz), (rx, h * 1.12, rz), col, seg=12 if collide else 10,
                        rings=4, jitter=0.03, rough=0.04, rng=self.rng, dome=True)
        if collide:
            self.add_box(cx, cz, rx * 1.25, rz * 1.25, h * 0.85)

    def tank_wreck(self, x, z):
        """Char d'assaut détruit, tourelle arrachée, calciné (il fume encore)."""
        b = self.plain
        b.xf((x, 0, z), 0)
        burnt, char, rust = rgb(78, 70, 58), rgb(38, 35, 32), rgb(118, 66, 38)
        paint = rgb(160, 140, 100)
        b.box((0, 0.8, 0), (3.2, 0.9, 6.6), burnt, jitter=0.08)                            # caisse
        b.box((0, 1.35, 0.1), (3.5, 0.25, 6.0), char, jitter=0.08)                          # plage avant/arrière
        b.box((0, 1.0, 3.45), (3.1, 0.7, 0.9), burnt, rx=-38)                              # glacis incliné
        b.box((0.9, 1.05, -1.2), (1.3, 0.1, 2.0), paint, jitter=0.06)                      # restes de peinture
        b.box((-0.8, 1.05, 1.5), (1.0, 0.12, 1.4), rust)
        for side in (-1, 1):
            b.box((side * 1.85, 0.5, 0 if side > 0 else 0.9), (0.62, 1.0, 7.0 if side > 0 else 5.2), char)  # chenilles
            for k in range(6):
                if side < 0 and k == 0:
                    continue
                b.cylinder((side * 2.17 - 0.08, 0.45, -2.6 + k * 1.05), 0.4, 0.16, rgb(55, 52, 48), seg=8,
                           axis='x')                                                          # galets
            b.box((side * 1.95, 1.1, 0.8), (0.1, 0.35, 4.0 if side > 0 else 2.2), burnt, jitter=0.1)  # jupes
        b.box((-1.9, 0.06, -4.6), (0.62, 0.1, 3.4), char)                                 # chenille déroulée
        # tourelle arrachée, posée de travers à côté de la caisse, canon piqué dans le sable
        b.xf((x + 1.9, 0, z - 2.4), 38)
        b.box((0, 0.5, 0), (2.6, 0.95, 3.0), burnt, jitter=0.08, rx=-8)
        b.box((0, 0.95, -0.2), (2.2, 0.3, 2.3), char, rx=-8)
        b.box((0, 0.55, 1.75), (1.2, 0.7, 0.5), char, rx=-8)                               # masque
        b.box((0, 0.3, 3.4), (0.22, 0.22, 3.2), rgb(50, 48, 45), rx=10)                    # canon
        b.box((0.55, 1.2, -0.6), (0.7, 0.12, 0.7), rust, rx=35)                            # trappe ouverte
        b.xf()
        for _ in range(9):                                                                 # débris
            a = self.rng.uniform(0, 6.28)
            d = self.rng.uniform(4.2, 6.5)
            b.box((x + math.cos(a) * d, 0.08, z + math.sin(a) * d),
                  (self.rng.uniform(0.2, 0.6), 0.15, self.rng.uniform(0.2, 0.7)), self.rng.choice((char, burnt, rust)))
        self.add_box(x, z, 4.4, 7.0, 2.1)
        self.add_box(x + 1.9, z - 2.4, 3.2, 3.2, 1.3)
        self.smoke_points.append(Vec3(x + 0.3, 1.6, z + 0.2))

    def truck_wreck(self, x, z, yaw):
        """Pick-up calciné."""
        sx, sz = (2.2, 5.0) if yaw % 180 == 0 else (5.0, 2.2)
        self.add_box(x, z, sx, sz, 1.6)
        p = self.plain
        p.xf((x, 0, z), yaw)
        c, dk = rgb(70, 60, 52), rgb(35, 33, 30)
        p.box((0, 0.7, 0), (1.9, 0.6, 4.8), c, jitter=0.1)
        p.box((0, 1.3, 0.8), (1.8, 0.65, 1.7), dk)
        p.box((0, 1.05, -1.2), (1.9, 0.12, 2.2), rgb(110, 62, 36))
        for sgn in (-1, 1):
            for wz in (1.6, -1.6):
                p.box((sgn * 0.9, 0.3, wz), (0.2, 0.55, 0.6), dk, top=False)
        p.xf()

    def ammo_crate(self, cx, cz):
        self.add_box(cx, cz, 1.4, 0.9, 0.8)
        b = self.plain
        b.xf()
        b.box((cx, 0.4, cz), (1.4, 0.8, 0.9), rgb(85, 95, 60), jitter=0.05)
        b.box((cx, 0.82, cz), (1.44, 0.06, 0.94), rgb(70, 80, 50))

    def build_desert(self):
        rng = self.rng
        L = ARENA * 2
        # limites de la zone : murs invisibles, grandes dunes tout autour (hors de l'arène)
        for cx, cz, sx, sz in [(0, ARENA, L + 1, 1), (0, -ARENA, L + 1, 1), (ARENA, 0, 1, L + 1), (-ARENA, 0, 1, L + 1)]:
            self.add_box(cx, cz, sx, sz, 6)
        for k in range(-5, 6):
            t = k * 9 + rng.uniform(-2, 2)
            for px, pz in [(t, ARENA + 5.5), (t, -ARENA - 5.5), (ARENA + 5.5, t), (-ARENA - 5.5, t)]:
                self.dune(px, pz, rng.uniform(7, 9), rng.uniform(6, 8), rng.uniform(3.0, 5.0), collide=False)

        self.tank_wreck(0, 0)                               # char détruit au centre

        # tranchées en zigzag (avec des passages)
        for x0, z0, x1, z1 in [(-30, 20, -13, 20), (-9, 17, 9, 17), (13, 20, 30, 20),
                               (-28, -18, -7, -18), (7, -15, 28, -15),
                               (-24, 27, -24, 36), (24, 27, 24, 36), (-36, -2, -36, 9), (36, -6, 36, 5)]:
            self.trench(x0, z0, x1, z1)

        # dunes dans l'arène : grandes (à couvert debout) et basses (à couvert accroupi)
        for x, z, rx, rz, h in [(-30, -6, 5.5, 4.5, 2.6), (30, -30, 5, 6, 2.5), (-20, 38, 6, 4, 2.4),
                                (22, 38, 5.5, 4, 2.6), (-36, -32, 5, 5, 2.4), (31, 8, 4.5, 4, 2.2),
                                (-14, 4, 3.5, 2.8, 1.25), (15, 5, 3.2, 3, 1.2), (-6, 30, 3, 2.5, 1.2),
                                (8, 31, 3.2, 2.6, 1.25), (-18, -28, 3.2, 2.4, 1.2), (0, -26, 3, 2.2, 1.15),
                                (38, -18, 3, 3.5, 1.3), (-38, 20, 3, 3.5, 1.3), (-24, 8, 2.6, 2.2, 1.1)]:
            if self.area_free(x, z, rx * 1.3, rz * 1.3, margin=0.3):
                self.dune(x, z, rx, rz, h)

        # épaves, caisses de munitions, sacs de sable, rochers
        for x, z, yaw in [(-22, -8, 0), (20, -5, 90), (-8, 40, 90), (34, 28, 0)]:
            if self.area_free(x, z, 5, 5, margin=0.3):
                self.truck_wreck(x, z, yaw)
        for x, z in [(-5, 8), (6, -7), (-26, 14), (26, 14), (-12, -34), (-33, 33), (40, -38), (-3, -10)]:
            if self.area_free(x, z, 1.4, 1.4, margin=0.3):
                self.ammo_crate(x, z)
        for x, z, l, ax in [(-10, -6, 4, True), (10, 8, 4, True), (-40, -12, 4, False), (40, 18, 4, False),
                            (0, 38, 5, True), (-28, 0, 3, False)]:
            if self.area_free(x, z, 4.2, 4.2, margin=0.2):
                self.sandbags(x, z, l, ax)
        for x, z, s in [(-15, -40, 0.9), (18, 26, 1.0), (-32, 26, 1.1), (27, -40, 0.9), (-40, 2, 1.0)]:
            if self.area_free(x, z, 2.5 * s, 2.5 * s, margin=0.4):
                self.rock(x, z, s)
        for x, z in [(-20, -22), (22, -24), (5, 24), (-38, 38)]:
            if self.area_free(x, z, 1.4, 1.4, margin=0.4):
                self.barrels(x, z)

        # batterie anti-aérienne derrière un fer à cheval de sacs de sable (ouvert vers le sud)
        ax, az = self.AA_POS.x, self.AA_POS.z
        self.sandbags(ax, az + 3.2, 5, True)
        self.sandbags(ax - 2.9, az + 0.6, 4, False)
        self.sandbags(ax + 2.9, az + 0.6, 4, False)
        self.aa = AAGun(self, self.AA_POS)

    # -- carte de défense (désert long) ------------------------------------------
    def define_pits(self):
        """Tranchées creusées (avant de construire le sol, qui est percé à leur emplacement).
        Chaque tranchée a une rampe à chaque bout ; accroupi au fond, on est à couvert."""
        w = TRENCH_WIDTH
        dz = self.defense_z
        segs = [
            # ligne principale, juste devant la ligne à tenir (en zigzag, avec des passages)
            (-37, -26.5, dz + 8, True), (-17, -3, dz + 8, True), (3, 17, dz + 6, True), (26.5, 37, dz + 8, True),
            (0, dz + 10, dz + 26, False),                            # boyau de communication vers l'avant
            # tranchées avancées
            (-15, -2, dz + 42, True), (4, 16, dz + 40, True),
            (-36, -27, dz + 60, True), (27, 36, dz + 62, True),
            # anciennes positions ennemies, au nord
            (-14, 14, dz + 108, True), (-35, -26, dz + 126, True), (26, 35, dz + 124, True),
            (-10, 10, dz + 150, True),
        ]
        for a, b, c, along_x in segs:
            if along_x:
                self.pits.append(Pit(a, b, c - w / 2, c + w / 2, True))
            else:
                self.pits.append(Pit(a - w / 2, a + w / 2, b, c, False))

    def draw_pit(self, p):
        """Tranchée creusée : parois coffrées de planches et de poteaux, rampes de sable aux bouts,
        caillebotis au fond, sacs de sable posés au bord."""
        b = self.plain
        b.xf()
        d = TRENCH_DEPTH
        R = TRENCH_RAMP
        wood, post, sand = rgb(125, 95, 62), rgb(88, 66, 45), shade(self.SAND, 0.82)
        floor = rgb(150, 120, 84)
        # repère local : u le long de la tranchée, v en travers
        if p.along_x:
            u0, u1, v0, v1 = p.x0, p.x1, p.z0, p.z1

            def P(u, y, v):
                return Vec3(u, y, v)
        else:
            u0, u1, v0, v1 = p.z0, p.z1, p.x0, p.x1

            def P(u, y, v):
                return Vec3(v, y, u)
        up = Vec3(0, 1, 0)
        a, c = u0 + R, u1 - R
        # fond et rampes
        b.quad(P(a, -d, v0), P(c, -d, v0), P(c, -d, v1), P(a, -d, v1), floor, up, local=False)
        for s0, s1 in ((u0, a), (u1, c)):
            n = (P(s1, -d, v0) - P(s0, 0, v0)).cross(P(s0, 0, v1) - P(s0, 0, v0)).normalized()
            if n.y < 0:
                n = -n
            b.quad(P(s0, 0, v0), P(s1, -d, v0), P(s1, -d, v1), P(s0, 0, v1), sand, n, local=False)
        # parois : coffrage en planches sur la partie profonde, sable au-dessus des rampes
        for v, inward in ((v0, 1), (v1, -1)):
            n = P(0, 0, inward) - P(0, 0, 0)
            b.quad(P(a, -d, v), P(c, -d, v), P(c, 0, v), P(a, 0, v), wood, n, local=False)
            b.tri(P(u0, 0, v), P(a, -d, v), P(a, 0, v), sand, n, local=False)
            b.tri(P(c, -d, v), P(u1, 0, v), P(c, 0, v), sand, n, local=False)
            for k in range(int((c - a) / 1.8) + 1):                 # poteaux
                u = a + 0.2 + k * 1.8
                if u > c - 0.1:
                    break
                ctr = P(u, -d / 2, v + inward * 0.05)
                b.box((ctr.x, ctr.y, ctr.z), (0.1, d, 0.1), post)
            # sacs de sable au bord (décor)
            ctr = P((u0 + u1) / 2, 0.14, v - inward * 0.35)
            size = P(u1 - u0 - 0.6, 0.28, 0.55) - P(0, 0, 0)
            b.box((ctr.x, ctr.y, ctr.z), (abs(size.x), 0.28, abs(size.z)), rgb(170, 150, 108), jitter=0.05)
        for k in range(int((c - a) / 0.5)):                          # caillebotis
            u = a + 0.25 + k * 0.5
            ctr = P(u, -d + 0.03, (v0 + v1) / 2)
            size = P(0.14, 0.04, (v1 - v0) - 0.5) - P(0, 0, 0)
            b.box((ctr.x, ctr.y, ctr.z), (abs(size.x), 0.04, abs(size.z)), rgb(105, 80, 55))

    def house(self, cx, cz, w=9.0, dpt=7.0, h=3.0):
        """Maison en terre crue : porte au sud, fenêtres, toit plat en terrasse (on peut y entrer)."""
        t = 0.4
        mud, dark, wood = rgb(196, 164, 122), rgb(150, 122, 90), rgb(95, 70, 45)
        p = self.plain
        p.xf()

        def solid(x, z, sx, sz, hh):
            self.add_box(x, z, sx, sz, hh)
            p.box((x, hh / 2, z), (sx, hh, sz), mud, jitter=0.03)

        def lintel(x, z, sx, sz, y0):
            self.add_collider(x, (y0 + h) / 2, z, sx, h - y0, sz)
            p.box((x, (y0 + h) / 2, z), (sx, h - y0, sz), mud, jitter=0.03)
        x0, x1, z0, z1 = cx - w / 2, cx + w / 2, cz - dpt / 2, cz + dpt / 2
        # mur sud : porte de 1,4 m au milieu
        door = 2.2                               # assez large pour que les soldats passent aussi
        solid((x0 + cx - door / 2) / 2, z0, cx - door / 2 - x0, t, h)
        solid((cx + door / 2 + x1) / 2, z0, x1 - cx - door / 2, t, h)
        lintel(cx, z0, door, t, 2.2)
        p.box((cx, 2.15, z0 - 0.05), (door + 0.2, 0.12, t + 0.1), wood)
        # murs nord, est, ouest : une fenêtre de 1,2 m chacun
        win = 1.2
        for side in ('n', 'e', 'o'):
            if side == 'n':
                solid((x0 + cx - win / 2) / 2, z1, cx - win / 2 - x0, t, h)
                solid((cx + win / 2 + x1) / 2, z1, x1 - cx - win / 2, t, h)
                solid(cx, z1, win, t, 1.1)
                lintel(cx, z1, win, t, 2.0)
            else:
                x = x1 if side == 'e' else x0
                solid(x, (z0 + cz - win / 2) / 2, t, cz - win / 2 - z0, h)
                solid(x, (cz + win / 2 + z1) / 2, t, z1 - cz - win / 2, h)
                solid(x, cz, t, win, 1.1)
                lintel(x, cz, t, win, 2.0)
        # toit en terrasse avec un petit parapet et des poutres qui dépassent
        p.box((cx, h + 0.12, cz), (w + 0.2, 0.24, dpt + 0.2), dark, bottom=True)
        self.add_collider(cx, h + 0.12, cz, w + 0.2, 0.24, dpt + 0.2)
        for sx_, sz_, bx, bz in ((w + 0.2, 0.15, cx, z0 - 0.02), (w + 0.2, 0.15, cx, z1 + 0.02),
                                 (0.15, dpt + 0.2, x0 - 0.02, cz), (0.15, dpt + 0.2, x1 + 0.02, cz)):
            p.box((bx, h + 0.42, bz), (sx_, 0.36, sz_), mud)
        for k in range(5):
            p.cylinder((x0 - 0.3, h - 0.25, z0 + 0.8 + k * (dpt - 1.6) / 4), 0.08, w + 0.6, wood, seg=5, axis='x')
        p.cylinder((cx + 2.5, h + 0.24, cz + 1.5), 0.45, 0.9, rgb(60, 80, 110), seg=10)   # réservoir d'eau

    def build_defense_map(self):
        rng = self.rng
        hx, hz, dz = self.hx, self.hz, self.defense_z
        # limites : murs invisibles et grandes dunes tout autour
        for cx, cz, sx, sz in [(0, hz, 2 * hx + 1, 1), (0, -hz, 2 * hx + 1, 1), (hx, 0, 1, 2 * hz + 1),
                               (-hx, 0, 1, 2 * hz + 1)]:
            self.add_box(cx, cz, sx, sz, 6)
        for k in range(int(2 * hx / 9) + 2):
            t = -hx + k * 9 + rng.uniform(-2, 2)
            for pz in (hz + 5.5, -hz - 5.5):
                self.dune(t, pz, rng.uniform(7, 9), rng.uniform(6, 8), rng.uniform(3.0, 5.0), collide=False)
        for k in range(int(2 * hz / 9) + 2):
            t = -hz + k * 9 + rng.uniform(-2, 2)
            for px in (hx + 5.5, -hx - 5.5):
                self.dune(px, t, rng.uniform(6, 8), rng.uniform(7, 9), rng.uniform(3.0, 5.0), collide=False)
        for p in self.pits:
            self.draw_pit(p)
        self.house(-10, dz + 30)                              # maison, avant-poste au milieu des tranchées
        self.tank_wreck(8, dz + 92)                           # char détruit à mi-chemin
        for x, z, yaw in [(-32, dz + 20, 0), (32, dz + 80, 90), (-6, dz + 132, 90), (34, dz + 140, 0)]:
            if self.area_free(x, z, 5, 5, margin=0.3):
                self.truck_wreck(x, z, yaw)
        # dunes : grandes (à couvert debout) et basses (à couvert accroupi), réparties sur toute la longueur
        placed = tries = 0
        while placed < 26 and tries < 600:
            tries += 1
            x, z = rng.uniform(-hx + 5, hx - 5), rng.uniform(dz + 14, hz - 16)
            big = rng.random() < 0.45
            rx, rz = (rng.uniform(4, 6), rng.uniform(3.5, 5)) if big else (rng.uniform(2.6, 3.4), rng.uniform(2.2, 3))
            if self.area_free(x, z, rx * 1.4, rz * 1.4, margin=1.0):
                self.dune(x, z, rx, rz, rng.uniform(2.2, 2.7) if big else rng.uniform(1.1, 1.3))
                placed += 1
        for x, z, l, ax in [(-8, dz + 3, 6, True), (8, dz + 3, 6, True), (-32, dz + 3, 6, True), (32, dz + 3, 6, True),
                            (-2, dz + 36, 4, True), (-16, dz + 28, 4, False)]:
            if self.area_free(x, z, l + 0.4, l + 0.4, margin=0.2):
                self.sandbags(x, z, l, ax)
        for x, z in [(-26, dz + 44, ), (28, dz + 46), (-4, dz + 70), (12, dz + 118), (-30, dz + 100)]:
            if self.area_free(x, z, 1.4, 1.4, margin=0.3):
                self.ammo_crate(x, z)
        for x, z, s_ in [(-15, dz + 76, 1.0), (16, dz + 24, 0.9), (-34, dz + 150, 1.1), (30, dz + 104, 1.0)]:
            if self.area_free(x, z, 2.5 * s_, 2.5 * s_, margin=0.4):
                self.rock(x, z, s_)
        # batterie anti-aérienne près de la base
        ax, az = 13.0, dz - 9
        self.sandbags(ax, az + 3.2, 5, True)
        self.sandbags(ax - 2.9, az + 0.6, 4, False)
        self.sandbags(ax + 2.9, az + 0.6, 4, False)
        self.aa = AAGun(self, Vec3(ax, 0, az))
        self.build_defense_line()

    def build_shrubs(self):
        """Désert : quelques touffes sèches (bien moins que l'herbe)."""
        b = MeshBuilder(tile=15)
        rng = random.Random(77)
        count = 0
        up = Vec3(0, 1, 0)
        target = int(900 * self.hx * self.hz / (ARENA * ARENA))
        while count < target:
            x = rng.uniform(-self.hx + 1, self.hx - 1)
            z = rng.uniform(-self.hz + 1, self.hz - 1)
            if not self.is_free(Vec3(x, 0, z)) or (self.pits and self.pit_at(x, z)):
                continue
            count += 1
            base = rgb(120, 100, 60)
            tip = rng.choice((rgb(165, 140, 85), rgb(150, 150, 90), rgb(185, 160, 105)))
            for _ in range(3):
                a = rng.uniform(0, 3.1416)
                w = rng.uniform(0.02, 0.035)
                hgt = rng.uniform(0.2, 0.45)
                dx, dz = math.cos(a) * w, math.sin(a) * w
                p0 = Vec3(x - dx, 0, z - dz)
                p1 = Vec3(x + dx, 0, z + dz)
                p2 = Vec3(x + rng.uniform(-0.25, 0.25), hgt, z + rng.uniform(-0.25, 0.25))
                side = (p1 - p0).cross(p2 - p0).normalized()
                b.tri(p0, p1, p2, [base, base, tip], side, normals=[up, up, up], local=False)
        return b.build(self.level, double_sided=True, cast_shadows=False)

    def build_grass(self):
        """Touffes d'herbe et fleurs, sans ombre portée.

        Découpées en tuiles de 15 m : Panda3D ne dessine que les tuiles dans le champ de vision."""
        if self.desert:
            return self.build_shrubs()
        b = MeshBuilder(tile=15)
        rng = random.Random(99)
        flowers = [rgb(250, 230, 80), rgb(245, 245, 245), rgb(190, 120, 220), rgb(240, 120, 60)]
        up = Vec3(0, 1, 0)
        count = 0
        while count < 7000:          # herbe simplifiée : 2 fois moins de touffes
            x = rng.uniform(-ARENA + 1, ARENA - 1)
            z = rng.uniform(-ARENA + 1, ARENA - 1)
            if 12.2 < z < 16.8 or not self.is_free(Vec3(x, 0, z)):
                continue
            count += 1
            nz = value_noise(x, z, 1) * 0.5 + 0.5
            base = Color(0.26 + 0.06 * nz, 0.38 + 0.06 * nz, 0.14, 1)
            tip = Color(0.44 + 0.14 * nz, 0.60 + 0.08 * nz, 0.24, 1)
            flower = rng.random() < 0.05
            for _ in range(2):          # 2 brins par touffe (au lieu de 4)
                a = rng.uniform(0, 3.1416)
                w = rng.uniform(0.025, 0.045)
                hgt = rng.uniform(0.15, 0.38) * (0.7 + 0.6 * nz)
                dx, dz = math.cos(a) * w, math.sin(a) * w
                ox, oz = x + rng.uniform(-0.2, 0.2), z + rng.uniform(-0.2, 0.2)
                p0 = Vec3(ox - dx, 0, oz - dz)
                p1 = Vec3(ox + dx, 0, oz + dz)
                p2 = Vec3(ox + rng.uniform(-0.12, 0.12), hgt, oz + rng.uniform(-0.12, 0.12))
                top = rng.choice(flowers) if flower else tip
                side = (p1 - p0).cross(p2 - p0).normalized()
                b.tri(p0, p1, p2, [base, base, top], side, normals=[up, up, up], local=False)
        return b.build(self.level, double_sided=True, cast_shadows=False)

    # -- collisions --------------------------------------------------------
    GRID = 6.0

    def build_box_grid(self):
        """Grille spatiale : chaque case (6 m) connaît les obstacles qui la touchent."""
        self.box_grid = {}
        g = self.GRID
        for b in self.boxes:
            for i in range(int(math.floor((b.x0 - 1) / g)), int(math.floor((b.x1 + 1) / g)) + 1):
                for j in range(int(math.floor((b.z0 - 1) / g)), int(math.floor((b.z1 + 1) / g)) + 1):
                    self.box_grid.setdefault((i, j), []).append(b)

    def boxes_near(self, x, z):
        return self.box_grid.get((int(math.floor(x / self.GRID)), int(math.floor(z / self.GRID))), ())

    # -- tranchées creusées ---------------------------------------------------
    def pit_at(self, x, z):
        for p in self.pits:
            if p.x0 <= x <= p.x1 and p.z0 <= z <= p.z1:
                return p
        return None

    def ground_y(self, x, z):
        """Hauteur du terrain : 0, ou fond de tranchée (avec une rampe à chaque bout)."""
        p = self.pit_at(x, z) if self.pits else None
        if p is None:
            return 0.0
        u, u0, u1 = (x, p.x0, p.x1) if p.along_x else (z, p.z0, p.z1)
        return -TRENCH_DEPTH * min(1.0, min(u - u0, u1 - u) / TRENCH_RAMP)

    def pit_resolve(self, old, new, r, y):
        """Au fond d'une tranchée on ne sort que par les rampes : les parois retiennent le joueur
        (on le recadre entre les deux parois ; aux bouts, la rampe le fait remonter)."""
        if not self.pits or y > -0.4:
            return new
        p = self.pit_at(old.x, old.z) or self.pit_at(new.x, new.z)
        if p is None:
            return new
        x, z = clamp(new.x, p.x0, p.x1), clamp(new.z, p.z0, p.z1)
        if p.along_x:
            z = clamp(z, p.z0 + r, p.z1 - r)
        else:
            x = clamp(x, p.x0 + r, p.x1 - r)
        return Vec3(x, new.y, z)

    def floor_height(self, x, z, r, y):
        """Hauteur du sol sous une entité (sol, fond de tranchée ou dessus d'une caisse / d'un muret)."""
        h = self.ground_y(x, z) if self.pits else 0
        for b in self.boxes_near(x, z):
            if b.h <= y + 0.35 and b.circle_overlap(x, z, r * 0.8):
                h = max(h, b.h)
        return h

    def resolve(self, pos, r, y=0.0):
        """Repousse un cercle (x,z) hors des obstacles dont le haut est au-dessus de ses pieds."""
        x, z = pos.x, pos.z
        for b in self.boxes_near(x, z):
            if b.h <= y + 0.35:
                continue
            px = clamp(x, b.x0, b.x1)
            pz = clamp(z, b.z0, b.z1)
            dx, dz = x - px, z - pz
            d2 = dx * dx + dz * dz
            if d2 >= r * r:
                continue
            if d2 > 1e-8:
                d = math.sqrt(d2)
                x += dx / d * (r - d)
                z += dz / d * (r - d)
            else:  # centre à l'intérieur de la boîte : sortie par le côté le plus proche
                opts = [(x - b.x0 + r, -1, 0), (b.x1 - x + r, 1, 0),
                        (z - b.z0 + r, 0, -1), (b.z1 - z + r, 0, 1)]
                pen, sx, sz = min(opts)
                x += sx * pen
                z += sz * pen
        return Vec3(x, pos.y, z)

    def los(self, a, b):
        """Ligne de vue entre deux points (rien du décor entre les deux)."""
        d = b - a
        dist = d.length()
        if dist < 0.01:
            return True
        return not raycast(a, d / dist, dist, traverse_target=self.level).hit

    # -- navigation (A* sur grille) -----------------------------------------
    def build_nav(self):
        self.nx = int(self.hx * 2 / self.CELL)
        self.nz = int(self.hz * 2 / self.CELL)
        self.blocked = [[False] * self.nz for _ in range(self.nx)]
        for i in range(self.nx):
            for j in range(self.nz):
                x, z = self.cell_center(i, j)
                if abs(x) > self.hx - 1 or abs(z) > self.hz - 1:
                    self.blocked[i][j] = True
        for b in self.boxes:
            i0, j0 = self.cell_of(Vec3(b.x0 - 1, 0, b.z0 - 1))
            i1, j1 = self.cell_of(Vec3(b.x1 + 1, 0, b.z1 + 1))
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    x, z = self.cell_center(i, j)
                    if b.circle_overlap(x, z, 0.55):
                        self.blocked[i][j] = True
        self.free_cells = [(i, j) for i in range(self.nx) for j in range(self.nz) if not self.blocked[i][j]]

    def cell_center(self, i, j):
        return -self.hx + (i + 0.5) * self.CELL, -self.hz + (j + 0.5) * self.CELL

    def cell_of(self, p):
        i = int((p.x + self.hx) / self.CELL)
        j = int((p.z + self.hz) / self.CELL)
        return clamp(i, 0, self.nx - 1), clamp(j, 0, self.nz - 1)

    def is_free(self, p):
        return self.free_xz(p.x, p.z)

    def free_xz(self, x, z):
        i = int((x + self.hx) / self.CELL)
        j = int((z + self.hz) / self.CELL)
        if i < 0 or j < 0 or i >= self.nx or j >= self.nz:
            return False
        return not self.blocked[i][j]

    def nearest_free(self, c):
        if not self.blocked[c[0]][c[1]]:
            return c
        for rad in range(1, 6):
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    i, j = c[0] + di, c[1] + dj
                    if 0 <= i < self.nx and 0 <= j < self.nz and not self.blocked[i][j]:
                        return (i, j)
        return None

    def line_free(self, a, b):
        ax, az = a.x, a.z
        dx, dz = b.x - ax, b.z - az
        steps = max(1, int(math.hypot(dx, dz) / 0.3))
        inv = 1 / steps
        free = self.free_xz
        for k in range(steps + 1):
            if not free(ax + dx * k * inv, az + dz * k * inv):
                return False
        return True

    def find_path(self, start, goal, max_nodes=6000):
        s = self.nearest_free(self.cell_of(start))
        g = self.nearest_free(self.cell_of(goal))
        if s is None or g is None:
            return []
        if s == g:
            return [flat(goal)]
        SQ2 = 1.4142
        openq = [(0, 0, s)]
        came = {s: None}
        cost = {s: 0}
        expanded = 0
        found = False
        while openq:
            _, c, cur = heapq.heappop(openq)
            if cur == g:
                found = True
                break
            if c > cost[cur]:
                continue
            expanded += 1
            if expanded > max_nodes:
                break
            ci, cj = cur
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ni, nj = ci + di, cj + dj
                if not (0 <= ni < self.nx and 0 <= nj < self.nz) or self.blocked[ni][nj]:
                    continue
                if di and dj and (self.blocked[ci + di][cj] or self.blocked[ci][cj + dj]):
                    continue  # pas de coupe de coin
                nc = c + (SQ2 if di and dj else 1)
                if nc < cost.get((ni, nj), 1e9):
                    cost[(ni, nj)] = nc
                    came[(ni, nj)] = cur
                    dx, dz = abs(ni - g[0]), abs(nj - g[1])
                    heapq.heappush(openq, (nc + (dx + dz) + (SQ2 - 2) * min(dx, dz), nc, (ni, nj)))
        if not found:
            return []
        cells = []
        cur = g
        while cur is not None:
            cells.append(cur)
            cur = came[cur]
        cells.reverse()
        pts = []
        for i, j in cells:
            x, z = self.cell_center(i, j)
            pts.append(Vec3(x, 0, z))
        if self.is_free(goal):
            pts[-1] = flat(goal)
        # lissage : on saute les points intermédiaires quand la ligne droite est libre
        smooth = []
        idx = 0
        cur_p = flat(start)
        while idx < len(pts):
            far = idx
            for k in range(len(pts) - 1, idx, -1):
                if self.line_free(cur_p, pts[k]):
                    far = k
                    break
            smooth.append(pts[far])
            cur_p = pts[far]
            idx = far + 1
        return smooth

    def free_point_near(self, p):
        """Position libre la plus proche de p (centre de case de navigation)."""
        c = self.nearest_free(self.cell_of(p))
        x, z = self.cell_center(*c)
        return Vec3(x, 0, z)

    def random_free_point(self, near=None, radius=15):
        for _ in range(40):
            i, j = random.choice(self.free_cells)
            x, z = self.cell_center(i, j)
            p = Vec3(x, 0, z)
            if near is None or flat_dist(p, near) < radius:
                return p
        return near if near is not None else Vec3(0, 0, 0)

    # -- couvertures -------------------------------------------------------
    def build_cover(self):
        """Points au pied de chaque obstacle assez haut, avec leur normale."""
        self.covers = []
        off = 0.85
        for b in self.boxes:
            if b.h < 1.1:
                continue
            sx, sz = b.x1 - b.x0, b.z1 - b.z0
            step = 6 if (sx > 70 or sz > 70) else 1.5
            sides = [
                ((b.x0, b.z0 - off), (b.x1, b.z0 - off), Vec3(0, 0, -1)),
                ((b.x0, b.z1 + off), (b.x1, b.z1 + off), Vec3(0, 0, 1)),
                ((b.x0 - off, b.z0), (b.x0 - off, b.z1), Vec3(-1, 0, 0)),
                ((b.x1 + off, b.z0), (b.x1 + off, b.z1), Vec3(1, 0, 0)),
            ]
            for (ax, az), (bx, bz), normal in sides:
                length = math.hypot(bx - ax, bz - az)
                n = max(1, int(length / step))
                for k in range(n + 1):
                    t = k / n
                    p = Vec3(lerp(ax, bx, t), 0, lerp(az, bz, t))
                    if abs(p.x) > self.hx - 1.2 or abs(p.z) > self.hz - 1.2:
                        continue
                    if self.is_free(p):
                        self.covers.append(CoverPoint(p, normal, b.h))


_SAND = None


def sand_texture(size=256):
    """Texture de sable (grain fin + petites rides), générée une fois."""
    global _SAND
    if _SAND is None:
        from PIL import Image
        rnd = random.Random(5)
        img = Image.new('RGBA', (size, size))
        px = img.load()
        for y in range(size):
            for x in range(size):
                r = 0.5 + 0.5 * math.sin((x * 0.9 + y * 0.35) * 2 * math.pi / size * 6
                                         + math.sin(y * 2 * math.pi / size * 3) * 1.5)
                v = int(215 + 25 * r + rnd.uniform(-22, 22))
                v = max(0, min(255, v))
                px[x, y] = (v, v, v, 255)
        _SAND = Texture(img)
    return _SAND


class AAGun:
    """Canon anti-aérien bitube (type ZU-23-2) : tourelle orientable que le joueur peut occuper
    (Carré / V). Obus explosifs, tir très rapide, surchauffe si l'on tire trop longtemps."""
    COOLDOWN = 0.075
    BLAST = 2.2           # rayon de l'explosion d'un obus (m)

    def __init__(self, world, pos):
        self.pos = Vec3(pos)
        self.heat = 0.0
        self.overheat = False
        self.side = 0
        dark, olive, mid = rgb(40, 44, 36), rgb(88, 96, 70), rgb(62, 66, 60)
        # affût fixe (fusionné avec le décor) : pied central et 4 bras d'appui
        b = world.plain
        b.xf((pos.x, 0, pos.z), 0)
        b.cylinder((0, 0, 0), 0.45, 0.7, olive, seg=10)
        for yaw in (45, 135, 225, 315):
            r = math.radians(yaw)
            b.xf((pos.x + math.cos(r) * 1.1, 0, pos.z + math.sin(r) * 1.1), -yaw)
            b.box((0, 0.12, 0), (2.0, 0.16, 0.22), olive)
            b.box((0.95, 0.05, 0), (0.4, 0.1, 0.4), dark)                        # vérins au sol
        b.xf()
        # partie tournante
        self.yaw = Entity(parent=world.level, position=(pos.x, 0.7, pos.z))
        t = MeshBuilder()
        t.box((0, 0.08, 0), (1.2, 0.16, 1.3), olive)                             # plateau tournant
        for sx in (-1, 1):
            t.box((sx * 0.5, 0.42, 0.1), (0.1, 0.6, 0.7), olive)                 # flasques
        t.box((0, 0.3, -1.0), (0.45, 0.08, 0.4), dark)                           # siège du tireur
        t.box((0, 0.6, -1.2), (0.45, 0.5, 0.08), dark)                           # dossier
        t.box((0, 0.25, -0.65), (0.1, 0.35, 0.6), mid)                           # support du siège
        for sx in (-1, 1):
            t.box((sx * 0.3, 0.3, -0.55), (0.1, 0.1, 0.25), dark)                # pédales de tir
        t.build(self.yaw)
        # berceau qui s'incline, avec les deux tubes
        self.cradle = Entity(parent=self.yaw, position=(0, 0.55, 0.1))
        c = MeshBuilder()
        self.muzzles = []
        for sx in (-1, 1):
            x = sx * 0.2
            c.box((x, 0, 0.1), (0.16, 0.24, 1.0), olive)                         # boîtes de culasse
            c.box((sx * 0.42, 0.02, 0.05), (0.2, 0.3, 0.55), rgb(70, 78, 55))    # caisses de munitions
            c.cylinder((x, 0, 0.55), 0.045, 2.1, dark, seg=8, axis='z')          # tubes
            c.cylinder((x, 0, 1.3), 0.07, 0.35, mid, seg=8, axis='z')            # manchons
            c.cylinder((x, 0, 2.6), 0.06, 0.22, rgb(25, 25, 25), seg=8, axis='z')  # cache-flammes
            self.muzzles.append(Entity(parent=self.cradle, position=(x, 0, 2.85)))
        c.box((0, 0.2, -0.2), (0.07, 0.12, 0.2), dark)                           # support du viseur
        c.build(self.cradle)
        # viseur annulaire devant l'œil du tireur
        self.ring = Entity(parent=self.cradle, model=Quad(mode='line', thickness=2, radius=0.5, segments=16),
                           color=rgb(30, 30, 30), position=(0, 0.42, 0.25), scale=0.22)
        self.eye = Entity(parent=self.yaw, position=(0, 1.0, -1.05))              # tête du tireur

    def aim(self, yaw, pitch):
        self.yaw.rotation_y = yaw
        self.cradle.rotation_x = pitch

    def cool(self, dt):
        self.heat = max(0.0, self.heat - dt * 0.3)
        if self.overheat and self.heat < 0.35:
            self.overheat = False

    def fire(self, game):
        """Un obus : traçante depuis le tube, explosion au point visé (petit délai de vol)."""
        if self.overheat:
            return False
        self.side ^= 1
        muzzle = self.muzzles[self.side]
        muzzle_flash(muzzle, scale=0.5, intensity=0.7, life=0.04)
        self.heat += 0.05
        if self.heat >= 1:
            self.overheat = True
            game.hud.add_feed('Batterie AA : surchauffe !')
        origin = camera.world_position
        d = (camera.forward + camera.right * random.uniform(-.006, .006)
             + camera.up * random.uniform(-.006, .006)).normalized()
        hit = raycast(origin, d, 300, ignore=[game.player])
        end = hit.world_point if hit.hit else origin + d * 300
        tracer(muzzle.world_position, end, rgb(255, 170, 70), thickness=0.05, life=0.05)
        if hit.hit or end.y < 0.5:
            FXM.later((end - origin).length() / 900, blast, game, Vec3(end), self.BLAST, 140, 35, 0.35, False,
                      VDMG_AA_SHELL)
        for e in game.enemies:                  # vacarme : tous les ennemis proches accourent
            if not e.dead and flat_dist(e.position, self.pos) < 60 and random.random() < 0.05:
                FXM.later(random.uniform(0.2, 0.8), e.hear_shot, Vec3(game.player.position))
        return True


def blast(game, pos, radius, dmax, dmin, size=1.0, hurt_player=False, vdmg=None):
    """Explosion (obus, missile) : dégâts dégressifs aux ennemis à découvert dans le rayon
    (et aux blindés si vdmg = (dégâts au char, dégâts au camion))."""
    explosion_fx(pos, size)
    if vdmg:
        damage_vehicles(game, pos, radius + 0.5, vdmg)
    center = pos + Vec3(0, 0.2, 0)
    w = game.world
    for e in list(game.enemies):
        if e.dead:
            continue
        de = (e.position + Vec3(0, 0.9, 0) - center).length()
        if de < radius + 0.4 and (w.los(center, e.eye) or w.los(center, e.position + Vec3(0, 0.4, 0))):
            e.take_hit(int(lerp(dmax, dmin, clamp(de / radius, 0, 1))), 'body', e.position + Vec3(0, 1, 0),
                       explosive=True)
            if e.dead:
                game.hud.hitmarker(True)
        elif de < 25 and game.player.drone is None:
            e.receive_alert(game.player.position)
    pl = game.player
    d = (pl.position + Vec3(0, 0.9, 0) - center).length()
    if hurt_player and d < radius + 0.4 and w.los(center, pl.eye):
        pl.take_damage(int(lerp(60, 15, clamp(d / radius, 0, 1))), pos)
    if d < 15 and pl.drone is None:
        pl.shake = max(pl.shake, 0.4 * (1 - d / 15))


class CoverPoint:
    def __init__(self, pos, normal, height):
        self.pos = pos
        self.normal = normal
        self.tangent = Vec3(normal.z, 0, -normal.x)
        self.height = height
        self.owner = None


# ---------------------------------------------------------------------------
# Effets visuels
# ---------------------------------------------------------------------------

class FX(Entity):
    """Effets visuels et minuteries sans Sequence Ursina.

    Les entités d'effets (étincelles, sang, traceurs...) sont réutilisées (réserve) et animées
    dans une seule boucle ; les appels différés passent par une liste de minuteries.
    """
    def __init__(self):
        super().__init__()
        self.live = []
        self.pools = {}
        self.timers = []

    def get(self, model, texture=None, parent=None):
        pool = self.pools.setdefault((model, texture), [])
        while pool and pool[-1].is_empty():
            pool.pop()
        if pool:
            e = pool.pop()
            e.enabled = True
        else:
            e = Entity(model=model, texture=texture, unlit=True)
            e.ignore = True
            e.pool_key = (model, texture)
        e.parent = parent if parent is not None else scene
        e.rotation = (0, 0, 0)
        return e

    def play(self, e, life, pos=None, scale=None, col=None, rot=None):
        self.live.append([e, 0.0, life,
                          Vec3(e.position), pos, Vec3(e.scale), scale,
                          e.color, col, Vec3(e.rotation), rot])

    def later(self, delay, fn, *args):
        self.timers.append([delay, fn, args])

    def release(self, e):
        if e.is_empty():             # détruit avec son parent (ex. arme d'un ennemi disparu)
            return
        e.parent = scene             # ne jamais laisser un effet en réserve attaché à un autre objet
        e.enabled = False
        e.billboard = False
        pool = self.pools[e.pool_key]
        if len(pool) < 150:
            pool.append(e)
        else:
            destroy(e)

    def update(self):
        dt = time.dt
        if self.timers:
            due = []
            for t in self.timers:
                t[0] -= dt
                if t[0] <= 0:
                    due.append(t)
            if due:
                self.timers = [t for t in self.timers if t[0] > 0]
                for _, fn, args in due:
                    fn(*args)
        keep = []
        for fx in self.live:
            e = fx[0]
            if e.is_empty():
                continue
            fx[1] += dt
            k = fx[1] / fx[2]
            if k >= 1:
                self.release(e)
                continue
            # setters Panda3D directs : bien plus rapides que les propriétés Ursina
            if fx[4] is not None:
                e.setPos(fx[3] + (fx[4] - fx[3]) * k)
            if fx[6] is not None:
                e.setScale(fx[5] + (fx[6] - fx[5]) * k)
            if fx[8] is not None:
                e.setColorScale(fx[7] + (fx[8] - fx[7]) * k)
            if fx[10] is not None:
                e.rotation = lerp(fx[9], fx[10], k)
            keep.append(fx)
        self.live = keep

    def clear(self):
        for fx in self.live:
            self.release(fx[0])
        self.live = []
        self.timers = []


FXM = None      # instance unique, créée par Game


def tracer(start, end, col=color.yellow, thickness=0.025, life=0.06):
    d = end - start
    length = d.length()
    if length < 0.05:
        return
    e = FXM.get('cube')
    e.color = col
    e.position = (start + end) / 2
    e.scale = (thickness, thickness, length)
    e.look_at(end)
    FXM.play(e, life)


def muzzle_flash(parent, pos=(0, 0, 0), scale=0.25, intensity=1.0, life=0.05):
    """intensity : opacité du flash (1 = plein éclat) ; life : durée en secondes."""
    a = int(255 * clamp(intensity, 0, 1))
    for k in range(2):
        f = FXM.get('quad', 'circle', parent)
        f.color = rgb(255, 215, 120, a) if k else rgb(255, 250, 220, a)
        f.position = pos
        f.scale = scale * (1 if k else 0.5)
        f.billboard = True
        f.rotation_z = random.uniform(0, 90)
        FXM.play(f, life)


_impacts = []


def impact(point, normal=None, col=rgb(40, 35, 30)):
    e = Entity(model='quad', texture='circle', color=col,
               position=point + (normal * 0.01 if normal is not None else Vec3(0, 0, 0)),
               scale=0.1, unlit=True)
    if normal is not None:
        e.look_at(point - normal)
    else:
        e.billboard = True
    e.ignore = True
    _impacts.append(e)
    if len(_impacts) > 80:
        destroy(_impacts.pop(0))
    out = normal if normal is not None else Vec3(0, 1, 0)
    for _ in range(5):
        p = FXM.get('cube')
        p.color = rgb(150, 130, 100)
        p.position = point
        p.scale = 0.04
        FXM.play(p, 0.25, pos=point + out * 0.2 + Vec3(random.uniform(-.3, .3), random.uniform(0, .4), random.uniform(-.3, .3)))
    dust = FXM.get('sphere')
    dust.color = rgb(170, 160, 140, 140)
    dust.position = point
    dust.scale = 0.1
    FXM.play(dust, 0.4, scale=Vec3(0.6, 0.6, 0.6), col=rgb(170, 160, 140, 0))


def blood(point):
    for _ in range(7):
        p = FXM.get('cube')
        p.color = rgb(140, 0, 0)
        p.position = point
        p.scale = 0.05
        FXM.play(p, 0.3, pos=point + Vec3(random.uniform(-.4, .4), random.uniform(-.3, .4), random.uniform(-.4, .4)))
    mist = FXM.get('sphere')
    mist.color = rgb(150, 10, 10, 150)
    mist.position = point
    mist.scale = 0.15
    FXM.play(mist, 0.25, scale=Vec3(0.5, 0.5, 0.5), col=rgb(150, 10, 10, 0))


def shell_casing(origin, right):
    c = FXM.get('cube')
    c.color = rgb(200, 160, 60)
    c.position = origin
    c.scale = (0.012, 0.012, 0.03)
    FXM.play(c, 0.3, pos=origin + right * random.uniform(0.25, 0.4) + Vec3(0, random.uniform(-0.2, 0.05), 0),
             rot=Vec3(random.uniform(0, 720), random.uniform(0, 720), 0))


# ---------------------------------------------------------------------------
# Grenades
# ---------------------------------------------------------------------------

class Grenade(Entity):
    def __init__(self, game, start, target, vel=None, by_player=False):
        """Grenade lancée vers target (ennemis) ou avec une vitesse initiale vel (joueur)."""
        super().__init__(model='sphere', color=rgb(55, 70, 40), scale=0.16, position=start, shader=LIT)
        self.game = game
        self.world = game.world
        self.by_player = by_player
        if vel is not None:
            self.vel = Vec3(vel)
        else:
            T = clamp(flat_dist(start, target) / 13, 0.6, 1.6)
            self.vel = Vec3((target.x - start.x) / T, 0, (target.z - start.z) / T)
            self.vel.y = (target.y + 0.1 - start.y + 0.5 * GRAVITY * T * T) / T
        self.fuse = 2.8
        self.landed = False
        self.blink = Entity(parent=self, model='sphere', color=color.red, scale=0.5, y=0.5, unlit=True)
        game.grenades.append(self)

    def update(self):
        if self.game.paused:
            return
        dt = time.dt
        self.fuse -= dt
        self.blink.visible = int(self.fuse * (8 if self.fuse < 1 else 4)) % 2 == 0
        self.vel.y -= GRAVITY * dt
        new = self.position + self.vel * dt
        res = self.world.resolve(new, 0.12, new.y)
        if abs(res.x - new.x) > 1e-4:
            self.vel.x *= -0.4
        if abs(res.z - new.z) > 1e-4:
            self.vel.z *= -0.4
        new = res
        floor = self.world.floor_height(new.x, new.z, 0.1, self.y) + 0.08
        if new.y <= floor:
            new.y = floor
            self.vel.y = -self.vel.y * 0.3 if abs(self.vel.y) > 1.5 else 0
            self.vel.x *= 0.55
            self.vel.z *= 0.55
            if not self.landed:
                self.landed = True
                for e in self.game.enemies:        # les ennemis proches s'écartent
                    if not e.dead and flat_dist(e.position, new) < 7:
                        FXM.later(random.uniform(0.15, 0.5) * (1.3 - e.skill), e.evade_grenade, Vec3(new))
        self.position = new
        self.rotation_x += 400 * dt
        if self.fuse <= 0:
            self.explode()

    def explode(self):
        g = self.game
        pos = Vec3(self.position)
        if self in g.grenades:
            g.grenades.remove(self)
        destroy(self)
        explosion_fx(pos)
        radius = 6.0
        damage_vehicles(g, pos, 3.5, VDMG_GRENADE)
        pl = g.player
        center = pos + Vec3(0, 0.3, 0)
        d = (pl.position + Vec3(0, 0.9, 0) - center).length()
        if not pl.dead and d < radius and (self.world.los(center, pl.eye)
                                           or self.world.los(center, pl.position + Vec3(0, 0.5, 0))):
            pl.take_damage(int(105 * (1 - d / radius) ** 1.1) + 5, pos)
        if d < 16:
            pl.shake = max(pl.shake, 0.6 * (1 - d / 16))
            PAD.rumble(1.0 * (1 - d / 16), 0.8 * (1 - d / 16), 350)
        for e in list(g.enemies):
            if e.dead:
                continue
            de = (e.position + Vec3(0, 0.9, 0) - center).length()
            if de < radius and self.world.los(center, e.eye):
                e.take_hit(int((150 if self.by_player else 100) * (1 - de / radius)), 'body',
                           e.position + Vec3(0, 1, 0), explosive=True)
            elif self.by_player and de < 25:
                e.receive_alert(pl.position)


def explosion_fx(pos, size=1.0):
    """Boule de feu, fumée, trace au sol et débris (grenades et roquettes)."""
    flash = FXM.get('sphere')
    flash.color = rgb(255, 200, 90)
    flash.position = pos
    flash.scale = 0.5
    FXM.play(flash, 0.3, scale=Vec3(5, 5, 5) * size, col=rgb(255, 120, 30, 0))
    for _ in range(9):
        sm = FXM.get('sphere')
        sm.color = rgb(90, 85, 80, 200)
        sm.position = pos + Vec3(random.uniform(-.8, .8), random.uniform(0, .5), random.uniform(-.8, .8)) * size
        sm.scale = random.uniform(0.6, 1.2) * size
        FXM.play(sm, 1.8, pos=sm.position + Vec3(random.uniform(-1, 1), random.uniform(1.5, 3), random.uniform(-1, 1)),
                 scale=sm.scale * 2.5, col=rgb(120, 115, 110, 0))
    scorch = FXM.get('circle')
    scorch.color = rgb(25, 22, 20, 200)
    scorch.position = (pos.x, 0.035, pos.z)
    scorch.rotation_x = 90
    scorch.scale = 2.4 * size
    scorch.double_sided = True
    FXM.play(scorch, 20)
    for _ in range(12):
        p = FXM.get('cube')
        p.color = rgb(70, 60, 50)
        p.position = pos
        p.scale = 0.06
        FXM.play(p, 0.4, pos=pos + Vec3(random.uniform(-3, 3), random.uniform(0.2, 2.5), random.uniform(-3, 3)) * size)


class Rocket(Entity):
    """Roquette de RPG : vole en ligne droite, explose au premier contact (ou au bout de 3 s)."""

    def __init__(self, game, start, direction):
        super().__init__(model='cube', color=rgb(70, 80, 50), scale=(0.09, 0.09, 0.45), position=start, shader=LIT)
        self.game = game
        self.dir = direction.normalized()
        self.look_at(start + self.dir)
        self.life = 3.0
        self.smoke_t = 0.0
        Entity(parent=self, model='quad', texture='circle', color=rgb(255, 190, 90), z=-0.6, scale=(3, 3),
               billboard=True, unlit=True)       # flamme du propulseur

    def update(self):
        if self.game.paused:
            return
        dt = time.dt
        self.life -= dt
        step = ROCKET_SPEED * dt
        hit = raycast(self.world_position, self.dir, step + 0.1, ignore=[self, self.game.player])
        if hit.hit:
            self.explode(hit.world_point - self.dir * 0.2)
            return
        self.position += self.dir * step
        self.smoke_t -= dt
        if self.smoke_t <= 0:          # traînée de fumée
            self.smoke_t = 0.03
            sm = FXM.get('sphere')
            sm.color = rgb(200, 200, 195, 160)
            sm.position = self.position - self.dir * 0.3
            sm.scale = 0.15
            FXM.play(sm, 1.2, scale=Vec3(0.9, 0.9, 0.9), col=rgb(160, 160, 155, 0),
                     pos=sm.position + Vec3(0, 0.4, 0))
        if self.life <= 0 or self.y < -1:
            self.explode(Vec3(self.position))

    def explode(self, pos):
        g = self.game
        destroy(self)
        explosion_fx(pos, 0.8)
        damage_vehicles(g, pos, ROCKET_RADIUS, VDMG_ROCKET)       # charge creuse : efficace contre les blindés
        center = pos + Vec3(0, 0.1, 0)
        w = g.world
        for e in list(g.enemies):              # tue ou blesse dans un rayon de 3 m
            if e.dead:
                continue
            de = (e.position + Vec3(0, 0.9, 0) - center).length()
            if de < ROCKET_RADIUS + 0.4 and (w.los(center, e.eye) or w.los(center, e.position + Vec3(0, 0.4, 0))):
                e.take_hit(int(lerp(240, 60, clamp(de / ROCKET_RADIUS, 0, 1))), 'body',
                           e.position + Vec3(0, 1, 0), explosive=True)
            elif de < 30:
                e.receive_alert(g.player.position)
        pl = g.player
        d = (pl.position + Vec3(0, 0.9, 0) - center).length()
        if not pl.dead and d < ROCKET_RADIUS + 0.4 and w.los(center, pl.eye):
            pl.take_damage(int(lerp(70, 20, clamp(d / ROCKET_RADIUS, 0, 1))), pos)
        if d < 20:
            pl.shake = max(pl.shake, 0.7 * (1 - d / 20))
            PAD.rumble(1.0 * (1 - d / 20), 0.9 * (1 - d / 20), 400)


# ---------------------------------------------------------------------------
# Ennemi humanoïde
# ---------------------------------------------------------------------------

TIERS = [dict(name='Recrues'), dict(name='Soldats'), dict(name='Commandos'), dict(name='Élite')]

# tous les ennemis : tenue entièrement noire, seule la tête porte un casque vert
ENEMY_LOOK = dict(uniform=rgb(26, 26, 28), dark=rgb(16, 16, 18), skin=rgb(20, 20, 22), helmet=rgb(55, 125, 45),
                  boot=rgb(12, 12, 12), glove=rgb(14, 14, 14), belt=rgb(10, 10, 10), hair=rgb(18, 18, 20))
# silhouette du joueur en vue à la 3e personne
PLAYER_LOOK = dict(uniform=rgb(120, 110, 82), dark=rgb(88, 80, 60), skin=rgb(224, 172, 130), helmet=rgb(70, 85, 110),
                   boot=rgb(40, 32, 25), glove=rgb(35, 32, 30), belt=rgb(45, 40, 32), hair=rgb(60, 42, 28))

# armes des ennemis : comportement de tir, distance de combat préférée, arme ramassable
ENEMY_WEAPONS = {
    'rifle':   dict(name="fusil d'assaut", loot='rifle', burst=(3, 5), interval=(0.12, 0.2), dmg=(6, 10),
                    ideal=14, mag=10, reach=45, acc=1.0, weight=0.5),
    'shotgun': dict(name='fusil à pompe', loot='shotgun', burst=(1, 1), interval=(0.9, 1.1), dmg=(22, 36),
                    ideal=8, mag=6, reach=18, acc=1.15, weight=0.25),
    'pistol':  dict(name='pistolet', loot='pistol', burst=(1, 3), interval=(0.35, 0.5), dmg=(7, 11),
                    ideal=11, mag=10, reach=30, acc=0.9, weight=0.25),
}

GUN_DARK, GUN_WOOD = rgb(35, 35, 38), rgb(90, 65, 40)
# modèles d'armes tenues par les soldats (repère de la main) : (position, taille, couleur, collision)
GUN_PARTS = {
    'rifle': [((0, 0.02, 0.2), (0.06, 0.1, 0.62), GUN_DARK, True), ((0, -0.06, 0.1), (0.05, 0.14, 0.06), GUN_DARK, False),
              ((0, -0.07, 0.3), (0.05, 0.16, 0.07), GUN_DARK, False), ((0, 0.0, -0.13), (0.06, 0.12, 0.2), GUN_WOOD, False)],
    'shotgun': [((0, 0.03, 0.3), (0.05, 0.05, 0.8), GUN_DARK, True), ((0, -0.02, 0.38), (0.065, 0.055, 0.22), GUN_WOOD, False),
                ((0, 0.0, 0.02), (0.06, 0.09, 0.22), GUN_DARK, False), ((0, -0.01, -0.16), (0.06, 0.12, 0.24), GUN_WOOD, False)],
    'pistol': [((0, 0.02, 0.07), (0.045, 0.05, 0.2), GUN_DARK, True), ((0, -0.06, 0.0), (0.04, 0.1, 0.06), GUN_DARK, False)],
    'sniper': [((0, 0.02, 0.35), (0.05, 0.07, 0.95), GUN_DARK, True), ((0, 0.1, 0.1), (0.05, 0.05, 0.3), GUN_DARK, False),
               ((0, 0.0, -0.18), (0.06, 0.12, 0.26), GUN_WOOD, False)],
}
GUN_PARTS['rpg'] = [((0, 0.03, 0.2), (0.1, 0.1, 1.0), rgb(70, 80, 50), True),
                    ((0, 0.03, 0.78), (0.14, 0.14, 0.18), rgb(60, 60, 55), False),
                    ((0, -0.07, 0.1), (0.04, 0.12, 0.05), GUN_DARK, False)]
GUN_MUZZLE = {'rifle': 0.55, 'shotgun': 0.72, 'pistol': 0.18, 'sniper': 0.85, 'rpg': 0.9}
ROCKET_SPEED = 38.0      # m/s
ROCKET_RADIUS = 3.0      # rayon de l'explosion (m)
CORPSE_TIME = 45        # secondes pendant lesquelles un cadavre reste au sol (et peut être fouillé)
PICKUP_RANGE = 2.5      # distance pour ramasser l'arme d'un cadavre
MAX_NADES = 6           # grenades transportées au maximum


def random_enemy_weapon():
    r = random.random()
    for k, w in ENEMY_WEAPONS.items():
        r -= w['weight']
        if r <= 0:
            return k
    return 'rifle'


class Squad:
    """Groupe de 2 à 4 soldats : ils patrouillent en formation, partagent l'alerte et avancent
    par bonds — une moitié se déplace d'abri en abri vers le joueur pendant que l'autre la couvre."""
    FORMATION = [(-2.2, -2.0), (2.2, -2.0), (0.0, -4.0)]

    def __init__(self, members):
        self.members = members
        self.phase = 0
        self.bound_t = random.uniform(3, 5)
        for i, m in enumerate(members):
            m.squad = self
            m.squad_index = i
            m.squad_group = i % 2

    def alive(self):
        return [m for m in self.members if not m.dead]

    def leader(self):
        a = self.alive()
        return a[0] if a else None

    def centroid(self):
        a = self.alive()
        if not a:
            return None
        return Vec3(sum(m.x for m in a) / len(a), 0, sum(m.z for m in a) / len(a))

    def alert(self, pos, source):
        for m in self.alive():
            if m is not source and m.state != 'combat':
                FXM.later(random.uniform(0.1, 0.4), m.receive_alert, Vec3(pos))

    def update(self, dt):
        alive = self.alive()
        fighting = [m for m in alive if m.state == 'combat' and m.last_known is not None]
        if len(fighting) < 2:
            return
        self.bound_t -= dt
        if self.bound_t > 0:
            return
        self.bound_t = random.uniform(3.5, 5.5) - 1.5 * fighting[0].skill
        movers = [m for m in fighting if m.squad_group == self.phase and m.sub == 'hide' and m.mag > 0]
        if movers:
            for c in fighting:            # l'autre moitié couvre la progression
                if c.squad_group != self.phase and c.sub == 'hide' and c.mag > 0:
                    c.cover_fire = True
                    c.timer = min(c.timer, 0.1)
            for m in movers:
                m.advance()
        self.phase ^= 1


class Enemy(Entity):
    def __init__(self, game, position, skill=0.0, tier=0, weapon='rifle', look=None, rpg=False, night=False,
                 manpads=False):
        super().__init__(position=position)
        self.game = game
        self.world = game.world
        self.skill = skill
        self.tier = TIERS[tier]
        self.look = look or ENEMY_LOOK
        self.wkind = weapon
        self.wp = ENEMY_WEAPONS.get(weapon, ENEMY_WEAPONS['rifle'])
        self.carries_rpg = rpg                          # RPG dans le dos : c'est lui qu'on récupère
        self.manpads = manpads                          # lance-missiles sol-air (tire sur le drone)
        self.sam_t = random.uniform(4, 9)
        self.night = night                              # lunettes de vision nocturne sur le casque
        self.loot = 'rpg' if rpg else self.wp['loot']   # arme récupérable sur le cadavre
        self.loot_mag = None
        self.squad = None
        self.squad_index = 0
        self.squad_group = 0
        self.aim_target = None                          # avatar du joueur : point visé imposé
        self.max_hp = 100 + int(70 * skill)
        self.hp = self.max_hp
        self.dead = False
        self.parts = []

        # IA
        self.state = 'patrol'        # patrol / investigate / combat
        self.sub = ''                # sous-état de combat
        self.timer = 0
        self.think_t = random.uniform(0, 0.2)     # décalage : tous ne réfléchissent pas à la même image
        self.path = []
        self.move_speed = 2.0
        self.sees = False
        self.suspicion = 0.0
        self.last_known = None
        self.last_seen = -99
        self.cover = None
        self.peek_pos = None
        self.last_peek_off = None
        self.mag = self.wp['mag']
        self.burst = 0
        self.shot_t = 0
        self.look_yaw = None
        self.retreated = False
        self.flinch = 0.0
        self.cover_fire = False
        self.grenades = 1 + int(skill * 2)
        self.last_grenade = -99
        self.thrown = False
        self.real_speed = 0.0

        # paramètres qui dépendent du niveau d'IA
        self.fov = 65 + 20 * skill            # demi-angle du champ de vision
        self.view_range = 32 + 15 * skill
        self.hear_radius = 32 + 20 * skill
        self.accuracy = 0.55 + 0.35 * skill
        self.reaction = 1.0 - 0.55 * skill    # multiplie les temps de réaction

        # animation
        self.vel = Vec3(0, 0, 0)
        self.phase = random.uniform(0, 6.28)
        self.crouch = 0.0
        self.want_crouch = 0.0
        self.aim = 0.0
        self.want_aim = 0.0
        self.aim_pitch = 0.0
        self.death_t = 0
        self.anim_acc = 0.0

        self.build_body()
        self.icon = Text(parent=self, text='', y=2.3, scale=18, billboard=True,
                         origin=(0, 0), color=color.yellow)
        mark_static(self)        # os, arme, icône : rien à mettre à jour image par image

    # -- corps articulé ----------------------------------------------------
    def part(self, bone, pos, scale, col, zone, collide=True, lit=True):
        """Enregistre un morceau de corps ; les morceaux d'un même os sont fusionnés dans merge_bones()."""
        if not lit:          # visière lumineuse : seule pièce non éclairée, gardée à part
            v = Entity(parent=bone, model='cube', color=col, position=pos, scale=scale, unlit=True)
            return v
        if bone not in self._bone_parts:
            self._bone_parts[bone] = (zone, [])
        self._bone_parts[bone][1].append((pos, scale, col, collide))

    def merge_bones(self):
        """Un maillage + des collisions en boîtes par os (au lieu d'une entité par morceau)."""
        for bone, (zone, parts) in self._bone_parts.items():
            b = MeshBuilder()
            solids = []
            for pos, scale, col, collide in parts:
                b.box(pos, scale, col, bottom=True)
                if collide:
                    solids.append(CollisionBox(Vec3(*pos), scale[0] / 2, scale[1] / 2, scale[2] / 2))
            bone.model = b.mesh()
            bone.shader = LIT
            if solids:
                bone.collider = Collider(bone, solids)
            bone.owner = self
            bone.zone = zone
            self.parts.append(bone)
        self._bone_parts = {}

    def set_gun(self, kind):
        """Change le modèle d'arme tenu (utilisé par l'avatar du joueur)."""
        b = MeshBuilder()
        for pos, sc, col, _ in GUN_PARTS[kind]:
            b.box(pos, sc, col, bottom=True)
        self.gun.model = b.mesh()
        self.muzzle.z = GUN_MUZZLE[kind]

    def build_body(self):
        t = self.look
        U, UD, S = t['uniform'], t['dark'], t['skin']
        glove = t['glove']
        # ennemis (tout en noir) : silhouette simplifiée, les petits détails seraient invisibles ;
        # l'avatar du joueur (3e personne) garde ses détails
        detail = self.look is not ENEMY_LOOK
        self._bone_parts = {}
        # bassin : pivot principal (hauteur des hanches)
        self.hips = Entity(parent=self, y=0.95)
        self.part(self.hips, (0, 0.02, 0), (0.36, 0.2, 0.22), UD, 'body')
        if detail:
            self.part(self.hips, (0, 0.1, 0), (0.39, 0.06, 0.25), t['belt'], 'body', collide=False)   # ceinture
        # torse : pivote au bassin
        self.torso = Entity(parent=self.hips, y=0.08)
        self.part(self.torso, (0, 0.28, 0), (0.42, 0.5, 0.25), U, 'body')
        if detail:
            self.part(self.torso, (0, 0.3, 0.12), (0.36, 0.36, 0.06), UD, 'body', collide=False)    # gilet
        for px in ((-0.1, 0.02, 0.14) if detail else ()):                                       # poches
            self.part(self.torso, (px, 0.2, 0.16), (0.09, 0.11, 0.05), shade(UD, 0.85), 'body', collide=False)
        self.part(self.torso, (0, 0.3, -0.19), (0.3, 0.38, 0.14), shade(UD, 0.9), 'body')       # sac à dos
        if detail:
            self.part(self.torso, (0, 0.52, -0.19), (0.26, 0.08, 0.13), shade(UD, 0.75), 'body', collide=False)
        if self.manpads:         # lance-missiles sol-air (tube vert sable) en bandoulière
            self.part(self.torso, (-0.14, 0.3, -0.3), (0.11, 1.1, 0.11), rgb(150, 140, 95), 'body', collide=False)
            self.part(self.torso, (-0.14, 0.9, -0.3), (0.16, 0.12, 0.16), rgb(60, 60, 55), 'body', collide=False)
            self.part(self.torso, (-0.14, 0.4, -0.22), (0.08, 0.14, 0.12), rgb(40, 40, 40), 'body', collide=False)
        if self.carries_rpg:     # lance-roquettes porté en travers du dos
            self.part(self.torso, (0.12, 0.35, -0.3), (0.1, 0.95, 0.1), rgb(70, 80, 50), 'body', collide=False)
            self.part(self.torso, (0.12, 0.88, -0.3), (0.14, 0.18, 0.14), rgb(60, 60, 55), 'body', collide=False)
        if detail:
            self.part(self.torso, (0, 0.58, 0), (0.11, 0.08, 0.11), S, 'body', collide=False)        # cou
        # tête
        self.neck = Entity(parent=self.torso, y=0.6)
        self.part(self.neck, (0, 0.14, 0), (0.22, 0.26, 0.24), S, 'head')
        if detail:
            self.part(self.neck, (0, 0.15, -0.1), (0.228, 0.2, 0.06), t['hair'], 'head', collide=False)   # arrière du crâne
        self.part(self.neck, (0, 0.26, -0.01), (0.27, 0.1, 0.29), t['helmet'], 'head')              # casque
        if detail:
            self.part(self.neck, (0, 0.22, 0), (0.28, 0.04, 0.3), shade(t['helmet'], 0.8), 'head', collide=False)
        if detail:
            self.part(self.neck, (0, 0.07, 0.12), (0.06, 0.05, 0.02), shade(S, 0.9), 'head', collide=False)  # nez
        for ex in (-0.055, 0.055):
            if detail:
                self.part(self.neck, (ex, 0.17, 0.12), (0.045, 0.03, 0.01), color.black, 'head', collide=False)
            if self.night:       # vision nocturne : deux oculaires verts lumineux
                self.part(self.neck, (ex, 0.19, 0.16), (0.05, 0.05, 0.07), rgb(20, 20, 22), 'head', collide=False)
                self.part(self.neck, (ex, 0.19, 0.196), (0.035, 0.035, 0.01), rgb(90, 255, 110), 'head',
                          collide=False, lit=False)
        if detail:
            self.part(self.neck, (0, 0.23, 0.13), (0.2, 0.025, 0.02), shade(t['helmet'], 0.7), 'head', collide=False)

        # bras : épaule -> bras -> coude -> avant-bras -> main
        self.shoulders, self.elbows = [], []
        for side in (-1, 1):
            sh = Entity(parent=self.torso, position=(0.27 * side, 0.48, 0))
            if detail:
                self.part(sh, (0, 0, 0), (0.15, 0.12, 0.15), UD, 'limb', collide=False)        # épaulière
            self.part(sh, (0, -0.15, 0), (0.12, 0.32, 0.12), U, 'limb')
            el = Entity(parent=sh, y=-0.3)
            self.part(el, (0, -0.14, 0), (0.1, 0.28, 0.1), U, 'limb')
            self.part(el, (0, -0.31, 0), (0.09, 0.1, 0.09), glove, 'limb')                   # main
            self.shoulders.append(sh)
            self.elbows.append(el)
        # arme tenue dans la main droite (orientée comme l'avant-bras) : fusil, fusil à pompe ou pistolet
        self.gun = Entity(parent=self.elbows[1], y=-0.31, rotation_x=90)
        for pos, sc, col, collide in GUN_PARTS[self.wkind]:
            self.part(self.gun, pos, sc, col, 'gun', collide=collide)
        self.muzzle = Entity(parent=self.gun, z=GUN_MUZZLE[self.wkind], y=0.02)

        # jambes : hanche -> cuisse -> genou -> tibia -> pied
        self.hip_joints, self.knees = [], []
        for side in (-1, 1):
            hj = Entity(parent=self.hips, position=(0.1 * side, -0.05, 0))
            self.part(hj, (0, -0.22, 0), (0.15, 0.45, 0.16), UD, 'limb')
            if detail:
                self.part(hj, (0.08 * side, -0.25, 0.02), (0.05, 0.12, 0.1), shade(UD, 0.85), 'limb', collide=False)
            kn = Entity(parent=hj, y=-0.44)
            self.part(kn, (0, -0.2, 0), (0.13, 0.42, 0.14), UD, 'limb')
            if detail:
                self.part(kn, (0, -0.03, 0.07), (0.12, 0.1, 0.04), shade(UD, 1.4), 'limb', collide=False)
            self.part(kn, (0, -0.43, 0.05), (0.14, 0.09, 0.27), t['boot'], 'limb')
            self.hip_joints.append(hj)
            self.knees.append(kn)
        self.merge_bones()

    # -- utilitaires -------------------------------------------------------
    @property
    def eye(self):
        return self.position + Vec3(0, lerp(EYE_STAND, EYE_CROUCH, self.crouch), 0)

    def set_path_to(self, target):
        self.path = self.world.find_path(self.position, target)

    def arrived(self):
        return not self.path

    def allies(self, radius):
        return [e for e in self.game.enemies if e is not self and not e.dead
                and flat_dist(e.position, self.position) < radius]

    # -- perception --------------------------------------------------------
    def perceive(self):
        pl = self.game.player
        if pl.dead or pl.drone is not None:       # aux commandes du drone, le joueur est hors de portée
            self.sees = False
            return
        to_p = pl.position - self.position
        dist = flat_dist(pl.position, self.position)
        facing = self.forward
        cosang = (to_p.x * facing.x + to_p.z * facing.z) / max(dist, 0.01)
        in_combat = self.state == 'combat'
        fov_ok = in_combat or cosang > math.cos(math.radians(self.fov))
        max_range = self.view_range + (12 if in_combat else 0)
        self.sees = False
        if dist < max_range and (fov_ok or dist < 3):
            if self.world.los(self.eye, pl.eye):
                self.sees = True
        if self.sees:
            self.last_known = Vec3(pl.position)
            self.last_seen = self.game.t

    def hear_shot(self, pos):
        """Le joueur a tiré : on connaît approximativement sa position."""
        if self.dead or self.game.player.dead:
            return
        err = 3.5 - 2.5 * self.skill
        self.last_known = pos + Vec3(random.uniform(-err, err), 0, random.uniform(-err, err))
        if self.state != 'combat':
            self.enter_combat(heard=True)

    def receive_alert(self, pos):
        if self.dead:
            return
        self.last_known = Vec3(pos)
        if self.state != 'combat':
            self.enter_combat(heard=True)

    def enter_combat(self, heard=False):
        self.state = 'combat'
        self.icon.text = '!'
        self.icon.color = color.red
        FXM.later(1.5, self.clear_icon, '!')
        if not heard:
            self.last_seen = self.game.t
        if self.last_known is not None and self.squad is not None:
            self.squad.alert(self.last_known, self)
        if self.last_known is not None:
            for a in self.allies(25 + 15 * self.skill):
                if a.state != 'combat':
                    FXM.later(random.uniform(0.3, 0.9), a.receive_alert, Vec3(self.last_known))
        self.go_to_cover()

    def clear_icon(self, which):
        if not self.dead and self.icon.text == which:
            self.icon.text = ''

    # -- choix tactiques ---------------------------------------------------
    def threat_eye(self):
        base = self.last_known if self.last_known is not None else self.game.player.position
        return base + Vec3(0, 1.6, 0)

    def cover_is_safe(self, cp, threat):
        return not self.world.los(cp.pos + Vec3(0, EYE_CROUCH, 0), threat)

    def choose_cover(self, far=False, avoid=None, ideal=None, center=None, closer_than=None):
        threat = self.threat_eye()
        tpos = flat(threat)
        best, best_score = None, -1e9
        sx, sz = self.x, self.z
        r2 = (30 if far else 22) ** 2
        near = []
        for c in self.world.covers:      # distances au carré, sans créer d'objets
            if c.owner is not None and c.owner is not self:
                continue
            dx, dz = c.pos.x - sx, c.pos.z - sz
            d2 = dx * dx + dz * dz
            if d2 < r2:
                near.append((d2, c))
        near.sort(key=lambda t: t[0])
        candidates = [c for _, c in near]
        others = [e.position for e in self.game.enemies if e is not self and not e.dead]
        if ideal is None:
            ideal = self.wp['ideal'] - 2 * self.skill      # fusil à pompe : de près ; fusil : à distance
        if center is None and self.squad is not None:
            center = self.squad.centroid()                  # rester groupés
        for c in candidates[:50]:
            d_threat = flat_dist(c.pos, tpos)
            if d_threat < 5:
                continue
            if closer_than is not None and d_threat > closer_than:
                continue
            if avoid is not None and flat_dist(c.pos, avoid) < 7:
                continue
            to_t = tpos - c.pos
            if (to_t.x * c.normal.x + to_t.z * c.normal.z) > 0:   # l'obstacle doit être entre nous et la menace
                continue
            if not self.cover_is_safe(c, threat):
                continue
            score = -flat_dist(c.pos, self.position)
            score += d_threat * 1.5 if far else -abs(d_threat - ideal) * 0.6
            for o in others:
                if flat_dist(o, c.pos) < 4:
                    score -= 8
            if self.skill > 0.3:      # les plus malins cherchent à prendre le joueur en tenaille
                my_ang = yaw_to(tpos, c.pos)
                for o in others:
                    if flat_dist(o, tpos) < 30:
                        score += min(abs(angle_diff(my_ang, yaw_to(tpos, o))), 90) * 0.05 * self.skill
            if flat_dist((c.pos + self.position) / 2, tpos) < 6:
                score -= 15           # ne pas traverser la ligne de tir du joueur
            if center is not None and not far:
                score -= max(0.0, flat_dist(c.pos, center) - 10) * 1.0     # cohésion de l'escouade
            score += random.uniform(0, 2)
            if score > best_score:
                best, best_score = c, score
        return best

    def release_cover(self):
        if self.cover and self.cover.owner is self:
            self.cover.owner = None
        self.cover = None

    def advance(self):
        """Bond vers le joueur : abri plus proche, sans quitter le groupe (ordonné par l'escouade)."""
        if self.last_known is None:
            return
        d = flat_dist(self.position, self.last_known)
        if d <= self.wp['ideal'] + 1:
            return
        c = self.choose_cover(ideal=max(self.wp['ideal'], d - 7), closer_than=d - 2)
        if c is not None:
            self.take_cover(c)

    def take_cover(self, c):
        self.release_cover()
        self.cover = c
        c.owner = self
        self.set_path_to(c.pos)
        self.sub = 'move_cover'
        self.timer = 8

    def go_to_cover(self, far=False, avoid=None):
        c = self.choose_cover(far, avoid)
        if c is None:
            self.release_cover()
            self.sub = 'skirmish'
            self.timer = random.uniform(1.0, 2.0)
            self.path = []
            return False
        self.release_cover()
        self.cover = c
        c.owner = self
        self.set_path_to(c.pos)
        self.sub = 'move_cover'
        self.timer = 8
        if self.state == 'combat' and flat_dist(c.pos, self.position) > 3:
            self.request_cover_fire()
        return True

    def request_cover_fire(self):
        """Demande à un allié à couvert de tirer pendant qu'on se déplace."""
        if self.skill < 0.2:
            return
        for a in sorted(self.allies(24), key=lambda a: flat_dist(a.position, self.position)):
            if a.state == 'combat' and a.sub == 'hide' and a.mag > 0 and random.random() < a.skill + 0.2:
                a.cover_fire = True
                a.timer = min(a.timer, 0.05)
                break

    def find_peek_spot(self):
        """Position proche de la couverture d'où l'on voit la menace en étant debout."""
        threat = self.threat_eye()
        base = self.cover.pos
        cands = [Vec3(0, 0, 0)]
        for d in (1.0, 1.6, 2.3, 3.0):
            cands += [self.cover.tangent * d, self.cover.tangent * -d]

        def key(v):
            k = v.length()
            if self.skill > 0.3 and self.last_peek_off is not None and (v - self.last_peek_off).length() < 0.5:
                k += 3       # ne pas ressortir toujours au même endroit
            return k
        cands.sort(key=key)
        for off in cands:
            p = base + off
            if not self.world.is_free(p):
                continue
            if self.world.los(p + Vec3(0, EYE_STAND, 0), threat):
                self.last_peek_off = off
                return p
        return None

    def find_flank_spot(self):
        """Point avec vue sur le joueur, sous un angle différent de celui des alliés."""
        target = self.last_known
        if target is None:
            return None
        ally_angles = [yaw_to(target, a.position) for a in self.allies(60)]
        best, best_score = None, -1e9
        for _ in range(25):
            ang = random.uniform(0, 360)
            dist = random.uniform(8, 16)
            p = target + Vec3(math.sin(math.radians(ang)) * dist, 0, math.cos(math.radians(ang)) * dist)
            if not self.world.is_free(p):
                continue
            if not self.world.los(p + Vec3(0, EYE_STAND, 0), target + Vec3(0, 1.6, 0)):
                continue
            score = -flat_dist(p, self.position) * 0.4
            for aa in ally_angles:
                score += min(abs(angle_diff(ang, aa)), 90) * 0.1
            if score > best_score:
                best, best_score = p, score
        return best

    def can_grenade(self, lost):
        g = self.game
        if g.wave < 3 or self.grenades <= 0 or self.last_known is None:
            return False
        if g.t - self.last_grenade < 12 or g.t - g.last_grenade < 6 - 2 * self.skill:
            return False
        if not 7 < flat_dist(self.position, self.last_known) < 24:
            return False
        if any(flat_dist(a.position, self.last_known) < 5 for a in self.allies(80)):
            return False      # pas de grenade sur un allié
        want = 0.25 + 0.45 * self.skill
        return (lost > 1.5 and random.random() < want) or random.random() < want * 0.25

    def start_throw(self):
        self.sub = 'throw'
        self.timer = 0.75
        self.thrown = False
        self.path = []
        self.want_crouch = 0
        self.want_aim = 0
        self.grenades -= 1
        self.last_grenade = self.game.t
        self.game.last_grenade = self.game.t

    def throw_grenade(self):
        err = 2.8 - 2.2 * self.skill
        target = self.last_known + Vec3(random.uniform(-err, err), 0, random.uniform(-err, err))
        Grenade(self.game, self.elbows[0].world_position + Vec3(0, 0.1, 0), target)

    def evade_grenade(self, gpos):
        if self.dead or flat_dist(self.position, gpos) > 7.5:
            return
        away = flat(self.position - gpos)
        if away.length() < 0.1:
            away = Vec3(random.uniform(-1, 1), 0, random.uniform(-1, 1))
        best = None
        for k in range(8):
            ang = math.atan2(away.x, away.z) + math.radians((k // 2) * 35 * (1 if k % 2 else -1))
            p = self.position + Vec3(math.sin(ang), 0, math.cos(ang)) * 8
            if self.world.is_free(p):
                best = p
                break
        if best is None:
            return
        self.release_cover()
        self.set_path_to(best)
        self.state = 'combat'
        self.sub = 'evade'
        self.timer = 2.5
        self.burst = 0
        self.icon.text = '!!'
        self.icon.color = color.orange
        FXM.later(1.5, self.clear_icon, '!!')

    # -- cerveau -----------------------------------------------------------
    def think(self):
        self.perceive()
        g = self.game
        if self.state == 'patrol':
            self.move_speed = 1.8
            self.want_aim = 0
            self.want_crouch = 0
            self.look_yaw = None
            if self.sees:
                d = flat_dist(self.position, g.player.position)
                rate = (0.25 if d > 15 else 0.6) * (1.6 if g.player.sprinting else 1) * (1 + 1.5 * self.skill)
                self.suspicion += rate
                self.icon.text = '?'
                self.icon.color = color.yellow
                self.path = []
                self.look_yaw = yaw_to(self.position, g.player.position)
                if self.suspicion >= 1:
                    self.enter_combat()
            else:
                self.suspicion = max(0, self.suspicion - 0.05)
                if self.suspicion == 0 and self.icon.text == '?':
                    self.icon.text = ''
                lead = self.squad.leader() if self.squad is not None else None
                if lead is not None and lead is not self and lead.state == 'patrol':
                    # suiveur : garde sa place dans la formation derrière le chef
                    ox, oz = Squad.FORMATION[(self.squad_index - 1) % len(Squad.FORMATION)]
                    spot = lead.position + lead.right * ox + lead.forward * oz
                    self.move_speed = 2.3
                    if flat_dist(spot, self.position) > 2.5 and (self.arrived() or self.timer <= 0):
                        self.set_path_to(spot)
                        self.timer = 1.0
                elif g.mode == 'defense' and (self.arrived() or self.timer <= 0):
                    self.move_speed = 2.5            # défense : ils progressent vers la ligne à tenir
                    self.set_path_to(g.advance_point(self))
                    self.timer = random.uniform(4, 7)
                elif self.arrived() and self.timer <= 0:
                    self.move_speed = 1.6
                    self.set_path_to(self.world.random_free_point(self.position, 18))
                    self.timer = random.uniform(2, 5)
        elif self.state == 'investigate':
            self.move_speed = 2.6
            self.want_aim = 0.6
            self.want_crouch = 0.15 * self.skill
            if self.sees:
                self.enter_combat()
                return
            if self.arrived():
                self.look_yaw = (self.look_yaw or self.rotation_y) + random.choice((-60, 60))
                if self.timer <= 0:
                    self.state = 'patrol'
                    self.icon.text = ''
                    self.timer = 1
        elif self.state == 'combat':
            self.combat_think()

    def combat_think(self):
        g = self.game
        lost = g.t - self.last_seen
        if g.player.dead or (g.mode == 'defense' and lost > 9 and self.sub not in ('evade', 'dodge')):
            # défense : sans nouvelles du joueur, ils reprennent leur progression
            self.state = 'patrol'
            self.sub = ''
            self.burst = 0
            self.icon.text = ''
            self.release_cover()
            return
        if self.last_known is not None and self.sub not in ('flank', 'move_cover', 'retreat', 'evade', 'dodge'):
            self.look_yaw = yaw_to(self.position, self.last_known)

        if self.sub in ('evade', 'dodge'):
            self.move_speed = 5.8
            self.want_crouch = 0.1
            self.want_aim = 0.2
            if self.arrived() or self.timer <= 0:
                if self.sub == 'evade':
                    self.go_to_cover()
                else:
                    self.back_to_cover()
            return

        if self.sub == 'throw':
            return    # géré dans update()

        # blessé : on se replie loin
        if self.hp < self.max_hp * 0.4 and not self.retreated:
            self.retreated = True
            if self.go_to_cover(far=True):
                self.sub = 'retreat'
                return

        # joueur perdu depuis longtemps : on part le chercher
        if lost > 12 - 4 * self.skill and self.sub != 'flank':
            self.state = 'investigate'
            self.sub = ''
            self.burst = 0
            self.release_cover()
            self.icon.text = '?'
            self.icon.color = color.orange
            if self.last_known is not None:
                self.set_path_to(self.last_known)
            self.timer = 4
            return

        sub = self.sub
        if sub in ('move_cover', 'retreat'):
            self.move_speed = 5.0
            self.want_crouch = 0.25
            self.want_aim = 0.3 + 0.4 * self.skill
            self.look_yaw = None
            if self.cover and not self.cover_is_safe(self.cover, self.threat_eye()) and random.random() < 0.3:
                self.go_to_cover(far=(sub == 'retreat'))
                return
            # les plus aguerris tirent en courant vers l'abri
            if self.sees and self.skill > 0.5 and self.mag > 2 and self.burst <= 0 and random.random() < 0.15 * self.skill:
                self.burst = 2
                self.shot_t = 0.1
            if self.arrived() or self.timer <= 0:
                self.sub = 'hide'
                self.timer = random.uniform(0.8, 2.0) * self.reaction + (2 if sub == 'retreat' else 0)
        elif sub == 'hide':
            self.want_crouch = 1
            self.want_aim = 0
            self.move_speed = 2
            if self.cover and not self.cover_is_safe(self.cover, self.threat_eye()):
                if self.sees and self.mag > 0 and random.random() < 0.5:
                    self.start_aim()
                else:
                    self.go_to_cover()
                return
            if self.mag <= 0:
                self.sub = 'reload'
                self.timer = 2.2 - 0.6 * self.skill
                return
            if self.timer <= 0:
                cover_fire, self.cover_fire = self.cover_fire, False
                if not cover_fire:
                    if self.can_grenade(lost):
                        self.start_throw()
                        return
                    if lost > 5 - 2.5 * self.skill:
                        spot = self.find_flank_spot()
                        if spot is not None and random.random() < 0.35 + 0.5 * self.skill:
                            self.release_cover()
                            self.set_path_to(spot)
                            self.sub = 'flank'
                            self.timer = 10
                            self.request_cover_fire()
                            return
                spot = self.find_peek_spot() if self.cover else None
                if spot is not None:
                    self.peek_pos = spot
                    self.set_path_to(spot)
                    self.sub = 'peek_move'
                    self.timer = 3
                else:
                    self.timer = random.uniform(0.8, 1.5)
                    if random.random() < 0.35:
                        self.go_to_cover()
        elif sub == 'reload':
            self.want_crouch = 1
            self.want_aim = 0
            if self.timer <= 0:
                self.mag = self.wp['mag']
                self.sub = 'hide'
                self.timer = random.uniform(0.3, 1.0) * self.reaction
        elif sub == 'peek_move':
            self.want_crouch = 0
            self.want_aim = 0.6 + 0.4 * self.skill
            self.move_speed = 2.8
            if self.sees and self.mag > 0:
                self.path = []
                self.start_aim()
            elif self.arrived() or self.timer <= 0:
                self.start_aim()
        elif sub == 'aim':
            self.want_crouch = 0
            self.want_aim = 1
            if self.timer <= 0:
                if self.sees and self.mag > 0:
                    self.sub = 'shoot'
                    self.burst = min(self.mag, random.randint(*self.wp['burst']))
                    self.shot_t = 0
                else:
                    self.back_to_cover()
        elif sub == 'shoot':
            self.want_aim = 1
            if self.burst <= 0:
                if self.sees and self.mag > 0 and random.random() < 0.3:
                    self.start_aim(short=True)
                else:
                    self.back_to_cover()
        elif sub == 'flank':
            self.want_crouch = 0.2
            self.want_aim = 0.6
            self.move_speed = 4.2
            self.look_yaw = None
            if self.sees:
                self.path = []
                self.start_aim()
            elif self.arrived() or self.timer <= 0:
                self.go_to_cover()
        elif sub == 'skirmish':
            self.want_aim = 1
            self.move_speed = 2.5
            self.want_crouch = 0.4 if random.random() < 0.3 else 0
            if self.sees and self.burst <= 0 and self.mag > 0 and random.random() < 0.5:
                self.burst = min(self.mag, random.randint(*self.wp['burst']))
                self.shot_t = 0.3 * self.reaction
            if self.mag <= 0:
                self.mag = self.wp['mag']
                self.timer = 0
            if self.timer <= 0:
                p = self.position + self.right * random.choice((-1, 1)) * random.uniform(2, 4)
                if self.world.is_free(p):
                    self.set_path_to(p)
                self.timer = random.uniform(1.0, 2.0)
                if random.random() < 0.4:
                    self.go_to_cover()
        else:
            self.go_to_cover()

    def start_aim(self, short=False):
        self.sub = 'aim'
        base = random.uniform(0.15, 0.3) if short else random.uniform(0.35, 0.7)
        self.timer = base * self.reaction

    def back_to_cover(self):
        if self.cover:
            self.set_path_to(self.cover.pos)
            self.sub = 'move_cover'
            self.timer = 4
        else:
            self.go_to_cover()

    # -- tir ---------------------------------------------------------------
    def fire(self):
        pl = self.game.player
        self.mag -= 1
        muzzle = self.muzzle.world_position
        w = self.wp
        muzzle_flash(self.muzzle, scale=0.45 if self.wkind == 'shotgun' else 0.3)
        target = pl.eye - Vec3(0, 0.35, 0)
        dist = flat_dist(self.position, pl.position)
        chance = clamp(self.accuracy * w['acc'] - dist / (45 + 25 * self.skill), 0.1, 0.9)
        if dist > w['reach']:
            chance *= 0.3                 # hors de portée efficace
        if self.wkind == 'shotgun':
            chance *= clamp(1.3 - dist / 15, 0.15, 1.2)
        if pl.speed_now > 5:        # les meilleurs anticipent vos déplacements
            chance *= lerp(0.55, 0.85, self.skill)
        elif pl.speed_now > 1:
            chance *= lerp(0.8, 0.95, self.skill)
        if pl.ads > 0.5 and pl.speed_now < 1:
            chance *= 1.1           # immobile en train de viser : cible facile
        if pl.crouch_t > 0.5:
            chance *= 0.8           # accroupi : cible plus petite
        if self.sub in ('skirmish', 'move_cover'):
            chance *= 0.6
        if not self.world.los(muzzle, pl.eye) and not self.world.los(self.eye, pl.eye):
            chance = 0
        if self.wkind == 'shotgun':        # gerbe de plombs
            for _ in range(3):
                tracer(muzzle, target + Vec3(random.uniform(-.8, .8), random.uniform(-.5, .5), random.uniform(-.8, .8)),
                       rgb(255, 200, 80), thickness=0.012)
        if random.random() < chance:
            tracer(muzzle, target, rgb(255, 200, 80))
            dmg = random.randint(*w['dmg'])
            if self.wkind == 'shotgun':
                dmg = int(dmg * clamp(1.2 - dist / 20, 0.25, 1.0))     # dégâts qui chutent avec la distance
            pl.take_damage(dmg, self.position)
        else:
            miss = target + Vec3(random.uniform(-1.2, 1.2), random.uniform(-0.6, 1.0), random.uniform(-1.2, 1.2))
            d = (miss - muzzle).normalized()
            hit = raycast(muzzle, d, 80, traverse_target=self.world.level)
            end = hit.world_point if hit.hit else muzzle + d * 60
            tracer(muzzle, end, rgb(255, 200, 80))
            if hit.hit:
                impact(hit.world_point, hit.world_normal)
            self.game.flyby(end)

    # -- dégâts ------------------------------------------------------------
    def take_hit(self, dmg, zone, point, explosive=False):
        if self.dead:
            return
        self.hp -= dmg
        blood(point)
        self.flinch = 1.0
        if not explosive:
            self.last_known = Vec3(self.game.player.position)
            self.last_seen = self.game.t
        if self.hp <= 0:
            self.die(zone)
            return
        if self.state != 'combat':
            self.enter_combat()
        elif self.sub in ('aim', 'shoot', 'peek_move', 'skirmish'):
            if self.skill > 0.35 and random.random() < self.skill:
                self.dodge()
            elif random.random() < 0.7:
                self.burst = 0
                if self.cover and self.cover_is_safe(self.cover, self.threat_eye()):
                    self.back_to_cover()
                else:
                    self.go_to_cover()
        elif self.sub == 'hide':
            self.go_to_cover()

    def dodge(self):
        """Esquive latérale rapide (ennemis expérimentés)."""
        for sgn in random.sample((-1, 1), 2):
            p = self.position + self.right * sgn * 2.5
            if self.world.is_free(p) and self.world.line_free(self.position, p):
                self.path = [p]
                self.sub = 'dodge'
                self.timer = 0.7
                self.burst = 0
                return
        self.go_to_cover()

    def die(self, zone):
        self.dead = True
        self.release_cover()
        self.icon.text = ''
        self.path = []
        for p in self.parts:
            p.collider = None
        self.fall_dir = random.choice((-1, 1))
        self.fall_side = random.uniform(-25, 25)
        full = WEAPONS[self.loot]['mag']
        self.loot_mag = full if self.carries_rpg else random.randint(full // 2, full)
        self.nade_loot = 1                # chaque ennemi tué laisse une grenade (ramassée automatiquement)
        if self.game.player.drone is not None and self.game.player.drone.thermal:
            set_hot(self, 0.45)           # vu du drone en thermique : le corps refroidit
        self.game.corpses.append(self)
        self.game.on_enemy_killed(self, zone == 'head')
        for a in self.allies(20):
            a.receive_alert(self.game.player.position)
            if a.state == 'combat' and a.sub == 'hide':
                a.timer += 1.0 * a.reaction
        destroy(self, CORPSE_TIME)

    # -- mise à jour -------------------------------------------------------
    def update(self):
        if self.game.paused:
            return
        dt = time.dt
        if self.dead:
            self.animate_death(dt)
            return

        self.timer -= dt
        self.think_t -= dt
        drone = self.game.player.drone
        if self.manpads and drone is not None and not self.dead:
            self.sam_t -= dt
            # tir d'un missile sol-air : drone à portée (70 m au sol) et pas plus de 2 missiles en l'air
            if self.sam_t <= 0 and flat_dist(self.position, drone.position) < 70 and len(self.game.sams) < 2:
                self.sam_t = random.uniform(18, 26) - 5 * self.skill
                SAMissile(self.game, self.eye + Vec3(0, 0.4, 0))
                self.game.hud.add_feed('MANPADS : missile sol-air lancé sur le drone !')
        if self.think_t <= 0:
            self.think_t += 0.2          # l'IA réfléchit 5 fois par seconde (décalée entre ennemis)
            self.think()
            self.update_shadow()

        if self.sub == 'throw':
            if self.last_known is not None:
                self.look_yaw = yaw_to(self.position, self.last_known)
            if not self.thrown and self.timer <= 0.3:
                self.thrown = True
                self.throw_grenade()
            if self.timer <= 0:
                self.back_to_cover()

        # tir en rafale
        if self.burst > 0 and self.sub in ('shoot', 'skirmish', 'move_cover'):
            self.shot_t -= dt
            if self.shot_t <= 0:
                if self.sees and self.mag > 0:
                    self.fire()
                    self.burst -= 1
                    self.shot_t = random.uniform(*self.wp['interval'])
                else:
                    self.burst = 0

        self.move(dt)
        # animation complète de près ; à mi-fréquence au loin ou hors du champ de vision
        self.anim_acc += dt
        pl = self.game.player
        to = self.position - pl.position
        d2 = to.x * to.x + to.z * to.z
        visible = (to.x * camera.forward.x + to.z * camera.forward.z) > 0 or d2 < 64
        step = 0 if (d2 < 625 and visible) else (1 / 30 if visible else 1 / 15)
        if self.anim_acc >= step:
            self.animate(self.anim_acc)
            self.anim_acc = 0.0

    def move(self, dt):
        desired = Vec3(0, 0, 0)
        speed = self.move_speed * (1 - 0.45 * self.crouch) * (1 + 0.15 * self.skill)
        if self.path:
            target = self.path[0]
            to = flat(target - self.position)
            d = to.length()
            if d < 0.35:
                self.path.pop(0)
            else:
                desired = to / d * speed
                if len(self.path) == 1 and d < 1.0:
                    desired *= max(0.3, d)
        for e in self.game.enemies:        # séparation entre ennemis
            if e is self or e.dead:
                continue
            d = flat_dist(e.position, self.position)
            if 0.01 < d < 0.9:
                desired += flat(self.position - e.position) / d * (0.9 - d) * 4
        self.vel = lerp(self.vel, desired, min(1, dt * 8))
        new = self.world.resolve(self.position + self.vel * dt, ENEMY_RADIUS)
        new.y = lerp(self.y, self.world.ground_y(new.x, new.z), min(1, dt * 7)) if self.world.pits else 0
        self.real_speed = flat(new - self.position).length() / max(dt, 1e-4)
        self.position = new

        # orientation
        facing_subs = ('aim', 'shoot', 'hide', 'reload', 'peek_move', 'skirmish', 'throw')
        if self.look_yaw is not None and self.state == 'combat' and self.sub in facing_subs:
            target_yaw = yaw_to(self.position, self.last_known) if self.last_known is not None else self.look_yaw
        elif self.look_yaw is not None and (self.real_speed < 0.3 or self.state == 'patrol'):
            target_yaw = self.look_yaw
        elif self.real_speed > 0.3:
            target_yaw = math.degrees(math.atan2(self.vel.x, self.vel.z))
        else:
            target_yaw = self.rotation_y
        self.rotation_y = approach_angle(self.rotation_y, target_yaw, (400 + 300 * self.skill) * dt)

    def animate(self, dt):
        self.crouch = lerp(self.crouch, self.want_crouch, min(1, dt * 6))
        self.aim = lerp(self.aim, self.want_aim, min(1, dt * 8))
        self.flinch = max(0, self.flinch - dt * 4)
        c, a = self.crouch, self.aim

        # inclinaison de visée vers le joueur
        pitch = 0
        if a > 0.5 and (self.last_known is not None or self.aim_target is not None):
            pe = self.aim_target if self.aim_target is not None else self.game.player.eye - Vec3(0, 0.3, 0)
            src = self.position + Vec3(0, lerp(1.45, 0.95, c), 0)
            pitch = -math.degrees(math.atan2(pe.y - src.y, max(flat_dist(pe, src), 0.1)))
        self.aim_pitch = lerp(self.aim_pitch, pitch, min(1, dt * 8))

        # cycle de marche
        speed = self.real_speed
        running = clamp((speed - 2.5) / 2.5, 0, 1)
        self.phase += dt * speed * (2.2 - 0.5 * running)
        amp = clamp(speed / 2.0, 0, 1)
        stride = (28 + 20 * running) * amp
        s = math.sin(self.phase)
        bob = abs(math.cos(self.phase)) * 0.05 * amp

        self.hips.y = lerp(0.95, 0.56, c) + bob - 0.03 * running
        base_hip = lerp(0, -72, c)
        base_knee = lerp(0, 112, c)
        for k, side in enumerate((1, -1)):
            self.hip_joints[k].rotation_x = base_hip - s * side * stride
            lift = max(0, math.sin(self.phase + (0 if side > 0 else math.pi) + 1.2))
            self.knees[k].rotation_x = base_knee + lift * (25 + 45 * running) * amp
            self.hip_joints[k].rotation_z = side * lerp(2, 8, c)

        lean = lerp(3, 28, c) + 12 * running
        self.torso.rotation_x = lerp(lean, self.aim_pitch + lerp(0, 10, c), a) - self.flinch * 20
        self.torso.rotation_y = s * 6 * amp * (1 - a) + a * -8
        self.torso.rotation_z = self.flinch * 8 * random.uniform(-1, 1)
        self.neck.rotation_x = -lean * 0.5 * (1 - a) + lerp(0, 5, a)
        self.neck.rotation_y = a * 8

        swing = s * 10 * amp * (1 - a)
        self.shoulders[1].rotation_x = lerp(-25 + swing, -80, a)
        self.shoulders[1].rotation_y = lerp(0, 10, a)
        self.shoulders[1].rotation_z = lerp(-10, -5, a)
        self.elbows[1].rotation_x = lerp(-65, -10, a)
        self.shoulders[0].rotation_x = lerp(-45 - swing, -75, a)
        self.shoulders[0].rotation_y = lerp(35, 40, a)
        self.shoulders[0].rotation_z = lerp(10, 5, a)
        self.elbows[0].rotation_x = lerp(-70, -40, a)
        self.gun.rotation_x = lerp(150, 100, a)

        if self.sub == 'throw':      # lancer de grenade : bras gauche armé derrière la tête puis projeté
            p = clamp(1 - self.timer / 0.75, 0, 1)
            if p < 0.55:
                w = smoothstep(p / 0.55)
                self.shoulders[0].rotation_x = lerp(-45, -200, w)
                self.elbows[0].rotation_x = lerp(-70, -60, w)
            else:
                w = smoothstep((p - 0.55) / 0.45)
                self.shoulders[0].rotation_x = lerp(-200, -50, w)
                self.elbows[0].rotation_x = lerp(-60, -5, w)
            self.shoulders[0].rotation_y = 0
            self.torso.rotation_y = lerp(20, -25, p)
            self.torso.rotation_x = lerp(-5, 15, p)

    def animate_death(self, dt):
        self.death_t += dt
        t = clamp(self.death_t / 0.7, 0, 1)
        e = t * t
        self.rotation_x = lerp(0, 86 * self.fall_dir, e)
        self.rotation_z = lerp(0, self.fall_side, e)
        for k in range(2):
            self.knees[k].rotation_x = lerp(self.knees[k].rotation_x, 20 + 25 * k, dt * 5)
            self.hip_joints[k].rotation_x = lerp(self.hip_joints[k].rotation_x, -10 * k, dt * 5)
            self.shoulders[k].rotation_x = lerp(self.shoulders[k].rotation_x, -150 * self.fall_dir + 60, dt * 3)
            self.elbows[k].rotation_x = lerp(self.elbows[k].rotation_x, -20, dt * 3)
        self.hips.y = lerp(self.hips.y, 0.95 - 0.3 * (1 - t), dt * 4)
        self.torso.rotation_x = lerp(self.torso.rotation_x, 0, dt * 4)
        if self.death_t > CORPSE_TIME - 2:
            self.scale = lerp(self.scale, Vec3(0.01, 0.01, 0.01), dt * 3)

    SHADOW_DIST = 35.0

    def update_shadow(self):
        """Au-delà de 35 m, l'ombre d'un soldat est à peine visible : on ne la calcule plus."""
        near = flat_dist(self.position, self.game.player.position) < self.SHADOW_DIST
        if near != getattr(self, '_casts', True):
            self._casts = near
            if near:
                self.show(0b0001)
            else:
                self.hide(0b0001)

    def on_destroy(self):
        self.release_cover()
        if self in self.game.corpses:
            self.game.corpses.remove(self)


# ---------------------------------------------------------------------------
# Armes du joueur
# ---------------------------------------------------------------------------

SNIPER_ZOOM = 2.0
PAD_LOOK_SPEED = (200, 140)   # vitesse de rotation au stick droit (degrés/s, horizontal / vertical)
LEAN_DIST = 0.55              # décalage de la tête quand on se penche (m)
LEAN_ROLL = 12                # inclinaison de la vue quand on se penche (degrés)
EYE_STAND, EYE_CROUCHED = 1.65, 1.05   # hauteur des yeux du joueur debout / accroupi

WEAPONS = {
    'rifle': dict(
        name="Fusil d'assaut", short='FUSIL', auto=True, cooldown=0.1, mag=30, reload=1.6,
        dmg={'head': 250, 'body': 34, 'limb': 22, 'gun': 15},
        spread=0.004, move_spread=0.02, ads_spread=0.25, kick=0.35,
        ads_fov=90, ads_sens=0.8, scope=False,
        sight_zoom=1.4,        # grossissement uniquement dans la vitre du viseur point rouge
        flash=0.45 * 0.5, flash_intensity=0.5, flash_life=0.05 * 0.5,      # flash réduit de 50 %
        tracer=(0.015, 0.04), model='rifle',
        hip=Vec3(0.15, -0.14, 0.2), ads=Vec3(0, -0.1675 * 0.42, 0.09),      # le point rouge au centre
    ),
    'sniper': dict(
        name='Sniper', short='SNIPER', auto=False, cooldown=1.25, mag=5, reload=2.6,
        dmg={'head': 500, 'body': 160, 'limb': 95, 'gun': 40},
        spread=0.035, move_spread=0.04, ads_spread=0.02, kick=2.6,
        ads_fov=math.degrees(2 * math.atan(math.tan(math.radians(45)) / SNIPER_ZOOM)),   # zoom x2
        ads_sens=0.45, scope=True, sight_zoom=1.0,
        flash=0.7 * 0.5, flash_intensity=0.5, flash_life=0.06 * 0.5,
        tracer=(0.03, 0.09), model='sniper',
        hip=Vec3(0.15, -0.15, 0.2), ads=Vec3(0, -0.1, 0.12),
    ),
    # ramassé sur les ennemis : 8 plombs par cartouche, dévastateur de près
    'shotgun': dict(
        name='Fusil à pompe', short='POMPE', auto=False, cooldown=0.85, mag=6, reload=2.4, pellets=8,
        dmg={'head': 45, 'body': 22, 'limb': 14, 'gun': 8},
        spread=0.045, move_spread=0.02, ads_spread=0.75, kick=2.2,
        ads_fov=80, ads_sens=0.8, scope=False, sight_zoom=1.0,
        flash=0.6 * 0.5, flash_intensity=0.5, flash_life=0.05 * 0.5,
        tracer=(0.01, 0.03), model='shotgun',
        hip=Vec3(0.15, -0.15, 0.22), ads=Vec3(0, -0.075 * 0.42, 0.22),
    ),
    # trouvé sur un ennemi : 2 roquettes en tout (pas de rechargement), explosion de 3 m de rayon
    'rpg': dict(
        name='RPG', short='RPG', auto=False, cooldown=1.6, mag=2, reload=0, no_reload=True, rocket=True,
        dmg={}, spread=0.003, move_spread=0.01, ads_spread=0.15, kick=3.0,
        ads_fov=math.degrees(2 * math.atan(math.tan(math.radians(45)) / 2.5)),    # lunette PGO-7 x2,5
        ads_sens=0.5, scope='rpg', sight_zoom=1.0,
        flash=1.0 * 0.5, flash_intensity=0.5, flash_life=0.08 * 0.5,
        tracer=(0.0, 0.0), model='rpg',
        hip=Vec3(0.2, -0.12, 0.12), ads=Vec3(0, -0.105 * 0.42, 0.16),
    ),
    # arme secondaire (Triangle / Tab) : semi-automatique, 8 balles, visée aux organes de visée
    'pistol': dict(
        name='Pistolet', short='PISTOLET', auto=False, cooldown=0.16, mag=8, reload=1.2,
        dmg={'head': 220, 'body': 45, 'limb': 28, 'gun': 15},
        spread=0.012, move_spread=0.02, ads_spread=0.3, kick=1.0,
        ads_fov=75, ads_sens=0.75, scope=False, sight_zoom=1.0,
        flash=0.35 * 0.5, flash_intensity=0.5, flash_life=0.04 * 0.5,
        tracer=(0.012, 0.035), model='pistol',
        hip=Vec3(0.13, -0.13, 0.25), ads=Vec3(0, -0.1 * 0.42, 0.32),      # guidon et hausse au centre
    ),
}


_HOLO = None


def holo_texture(size=256):
    """Réticule du viseur holographique : cercle rouge, 4 repères et point central."""
    global _HOLO
    if _HOLO is None:
        from PIL import Image, ImageDraw, ImageFilter
        img = Image.new('RGBA', (size, size), (255, 40, 30, 0))
        d = ImageDraw.Draw(img)
        c, r, w = size // 2, int(size * 0.36), max(2, size // 110)     # traits fins
        red = (255, 45, 35, 255)
        d.ellipse((c - r, c - r, c + r, c + r), outline=red, width=w)
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):       # repères à 3, 6, 9 et 12 h
            x0, y0 = c + dx * (r - w * 3), c + dy * (r - w * 3)
            x1, y1 = c + dx * (r + w * 2), c + dy * (r + w * 2)
            d.line((x0, y0, x1, y1), fill=red, width=w)
        pr = max(2, size // 75)
        d.ellipse((c - pr, c - pr, c + pr, c + pr), fill=red)
        glow = img.filter(ImageFilter.GaussianBlur(size / 120))  # léger halo lumineux
        _HOLO = Texture(Image.alpha_composite(glow, img))
    return _HOLO


# ---------------------------------------------------------------------------
# Joueur
# ---------------------------------------------------------------------------

class Player(Entity):
    GUN_SCALE = 0.42
    DOT = Vec3(0, 0.1675, 0.08)                  # centre du réticule (repère local de l'arme), centre de la vitre
    SIGHT = ((-0.044, 0.1235), (0.044, 0.2115))  # carré qui encadre la lentille ronde (repère local)

    def __init__(self, game):
        super().__init__(position=game.world.spawn)
        self.game = game
        self.world = game.world
        self.pivot = Entity(parent=self, y=1.65)
        camera.parent = self.pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = 90
        camera.clip_plane_near = 0.05
        camera.clip_plane_far = 220
        self.sensitivity = Vec2(40, 40)
        self.vel = Vec3(0, 0, 0)
        self.vy = 0
        self.grounded = True
        self.hp = 100
        self.dead = False
        self.weapon_key = 'rifle'
        self.slots = ['rifle', 'pistol']   # 2 emplacements : arme principale et arme secondaire
        self.slot = 0                      # Triangle / Tab alterne ; Carré près d'un cadavre échange l'arme tenue
        self.start_weapon = 'rifle'        # arme choisie au menu
        self.avatar = None                 # corps du joueur, visible en vue à la 3e personne
        self.tps = False
        self.weapon = WEAPONS['rifle']
        self.mag = self.weapon['mag']
        self.mags = {}              # munitions gardées pour l'arme rangée
        self.switch_t = 0.0         # animation de changement d'arme
        self.crouching = False
        self.crouch_t = 0.0
        self.lean_pad = 0           # penché choisi à la manette (-1 gauche, 0, 1 droite)
        self.lean_t = 0.0
        self.armed = False          # il faut relâcher la détente avant le premier tir (clic du menu)
        self.trigger_ready = False  # sniper : un tir par pression
        self.reload_t = 0
        self.cooldown = 0
        self.last_hurt = -99
        self.speed_now = 0
        self.sprinting = False
        self.recoil = 0
        self.recoil_pitch = 0   # recul de visée, récupéré progressivement
        self.ads = 0.0          # 0 = arme à la hanche, 1 = visée
        self.shake = 0.0
        self.bob_t = 0.0
        self.land_dip = 0.0
        self.pad_sprint = False
        self._zoom_on = False
        self.nades = 1              # grenades (X / R1) ; +1 en passant sur le cadavre d'un ennemi
        self.nade_t = 0.0
        self.drone = None           # drone Reaper piloté (ultime)
        self.mount = None           # batterie anti-aérienne occupée
        self.build_gun()

    @property
    def eye(self):
        # position réelle de la tête : tient compte de l'accroupissement et du penché
        return self.pivot.world_position

    def set_weapon(self, key):
        self.mags[self.weapon_key] = self.mag
        self.weapon_key = key
        self.weapon = WEAPONS[key]
        destroy(self.gun)
        self.build_gun()
        self.mag = self.mags.get(key, self.weapon['mag'])
        self.mags.pop(key, None)
        self.reload_t = 0
        self.cooldown = 0.3
        self.armed = False
        self.trigger_ready = False

    def switch_weapon(self):
        """Triangle / Tab : passe à l'autre emplacement (chaque arme garde son chargeur)."""
        if self.dead or self.switch_t > 0:
            return
        self.slot ^= 1
        self.set_weapon(self.slots[self.slot])
        self.switch_t = 0.35
        self.game.hud.add_feed(f"Arme : {self.weapon['name']}")

    def reset_weapons(self, start):
        self.start_weapon = start
        self.slots = [start, 'pistol']
        self.slot = 0
        self.mags = {}
        self.set_weapon(start)
        self.mags = {}
        self.mag = self.weapon['mag']

    def take_weapon(self, corpse):
        """Carré / V près d'un cadavre : échange l'arme tenue contre la sienne (qui garde ses balles)."""
        new = corpse.loot
        if new is None or self.dead:
            return
        if new == self.weapon_key:                   # même arme : on récupère juste ses munitions
            self.mag = self.weapon['mag']
            self.reload_t = 0
            corpse.loot = None
            self.game.hud.add_feed(f"Munitions récupérées : {self.weapon['name']}")
        else:
            old, old_mag = self.weapon_key, self.mag
            self.slots[self.slot] = new
            self.mags[new] = corpse.loot_mag
            self.set_weapon(new)
            self.switch_t = 0.35
            corpse.loot, corpse.loot_mag = old, old_mag      # on laisse la sienne sur le cadavre
            if self.slots[self.slot ^ 1] != old:
                self.mags.pop(old, None)
            self.game.hud.add_feed(f"Arme ramassée : {self.weapon['name']}")
        PAD.rumble(0.3, 0.3, 90)

    def toggle_view(self):
        """Flèche bas / T : vue à la première ou à la troisième personne."""
        self.tps = not self.tps
        if self.tps and self.avatar is None:
            self.avatar = Enemy(self.game, Vec3(self.position), look=PLAYER_LOOK, weapon='rifle')
            self.avatar.set_gun(self.weapon['model'])
            self.avatar.update = lambda: None            # pas d'IA : piloté par le joueur
            for part in self.avatar.parts:
                part.collider = None                     # ne bloque ni les balles ni la vue
        if self.avatar is not None:
            self.avatar.enabled = self.tps
        self.game.hud.add_feed('Vue : 3e personne' if self.tps else 'Vue : 1re personne')

    def drive_avatar(self, dt):
        a = self.avatar
        a.position = self.position
        a.rotation_y = self.rotation_y
        a.want_crouch = a.crouch = self.crouch_t
        a.want_aim = 1.0 if self.ads > 0.3 else 0.55
        a.real_speed = self.speed_now
        a.aim_target = self.eye + camera.forward * 30
        a.animate(dt)

    def throw_grenade(self):
        """X / R1 : lance une grenade dans la direction du regard (explose au bout de 2,8 s)."""
        if self.dead or self.drone is not None or self.mount is not None or self.game.t < self.nade_t:
            return
        if self.nades <= 0:
            self.game.hud.add_feed('Plus de grenades (ramassez-en sur les ennemis tués)')
            return
        self.nades -= 1
        self.nade_t = self.game.t + 0.8
        fwd = camera.forward
        start = self.eye + fwd * 0.6 + camera.right * 0.2
        start = self.world.resolve(start, 0.15, start.y)
        Grenade(self.game, start, None, vel=fwd * 15 + Vec3(0, 3.5, 0) + flat(self.vel) * 0.8, by_player=True)
        self.switch_t = max(self.switch_t, 0.3)      # l'arme s'abaisse pendant le lancer
        PAD.rumble(0.2, 0.2, 60)

    def toggle_crouch(self):
        if not self.dead:
            self.crouching = not self.crouching

    def build_gun(self):
        {'sniper': self.build_sniper, 'pistol': self.build_pistol, 'shotgun': self.build_shotgun,
         'rpg': self.build_rpg}.get(self.weapon['model'], self.build_rifle)()
        if self.avatar is not None:
            self.avatar.set_gun(self.weapon['model'])

    def build_rpg(self):
        self.gun = Entity(parent=camera, position=self.weapon['hip'], scale=self.GUN_SCALE)
        olive = rgb(70, 80, 50)
        dark = rgb(34, 35, 38)

        def p(pos, sc, col):
            return Entity(parent=self.gun, model='cube', color=col, position=pos, scale=sc, shader=LIT)
        p((0, 0, 0.1), (0.13, 0.13, 1.3), olive)                 # tube
        p((0, 0, 0.82), (0.2, 0.2, 0.22), rgb(60, 62, 55))       # ogive de la roquette
        p((0, 0, 0.98), (0.1, 0.1, 0.12), rgb(60, 62, 55))
        p((0, 0, -0.58), (0.16, 0.16, 0.08), dark)               # tuyère arrière
        p((0, -0.12, 0.08), (0.05, 0.14, 0.07), dark)            # poignée
        p((0, -0.12, 0.3), (0.05, 0.12, 0.06), dark)
        p((-0.03, 0.09, 0.1), (0.02, 0.05, 0.06), dark)          # hausse
        p((0.03, 0.09, 0.1), (0.02, 0.05, 0.06), dark)
        p((0, 0.095, 0.45), (0.015, 0.03, 0.02), rgb(220, 220, 200))   # guidon
        # lunette optique PGO-7 sur le flanc gauche
        p((-0.085, 0.06, 0.05), (0.05, 0.03, 0.14), dark)        # monture
        p((-0.12, 0.1, 0.03), (0.055, 0.055, 0.3), dark)          # corps de la lunette
        p((-0.12, 0.1, 0.2), (0.07, 0.07, 0.05), dark)            # objectif
        p((-0.12, 0.1, -0.15), (0.075, 0.075, 0.07), rgb(20, 20, 20))   # œilleton caoutchouc
        p((-0.155, 0.1, 0.02), (0.02, 0.025, 0.03), rgb(60, 62, 55))    # molette d'éclairage
        self.dot = None
        self.sight_corners = []
        self.muzzle = Entity(parent=self.gun, z=1.05)
        self.eject = Entity(parent=self.gun, z=-0.6)

    def build_shotgun(self):
        self.gun = Entity(parent=camera, position=self.weapon['hip'], scale=self.GUN_SCALE)
        dark = rgb(34, 35, 38)
        wood = rgb(110, 75, 45)

        def p(pos, sc, col):
            return Entity(parent=self.gun, model='cube', color=col, position=pos, scale=sc, shader=LIT)
        p((0, 0.0, 0.0), (0.08, 0.11, 0.34), dark)               # boîte de culasse
        p((0, 0.03, 0.5), (0.045, 0.045, 0.75), dark)            # canon
        p((0, -0.025, 0.46), (0.04, 0.035, 0.62), dark)          # magasin tubulaire
        p((0, -0.03, 0.42), (0.075, 0.06, 0.22), wood)           # pompe
        p((0, -0.03, -0.35), (0.07, 0.13, 0.36), wood)           # crosse
        p((0, -0.1, -0.1), (0.055, 0.13, 0.06), wood)            # poignée
        p((0, 0.065, 0.85), (0.012, 0.02, 0.012), rgb(230, 220, 180))   # guidon (bille)
        self.dot = None
        self.sight_corners = []
        self.muzzle = Entity(parent=self.gun, z=0.88, y=0.03)
        self.eject = Entity(parent=self.gun, x=0.05, y=0.03, z=0.05)

    def build_pistol(self):
        self.gun = Entity(parent=camera, position=self.weapon['hip'], scale=self.GUN_SCALE)
        dark = rgb(32, 33, 36)
        mid = rgb(70, 72, 76)

        def p(pos, sc, col):
            return Entity(parent=self.gun, model='cube', color=col, position=pos, scale=sc, shader=LIT)
        p((0, 0.04, 0.1), (0.07, 0.07, 0.36), mid)               # culasse
        p((0, -0.01, 0.08), (0.065, 0.04, 0.3), dark)            # carcasse
        p((0, -0.12, -0.02), (0.06, 0.2, 0.09), dark)            # poignée
        p((0, -0.06, 0.08), (0.02, 0.05, 0.08), dark)            # pontet
        p((0, 0.04, 0.29), (0.03, 0.03, 0.03), dark)             # bouche du canon
        # organes de visée : hausse à cran et guidon, alignés à y = 0.1
        p((0.024, 0.09, -0.06), (0.014, 0.02, 0.02), dark)
        p((-0.024, 0.09, -0.06), (0.014, 0.02, 0.02), dark)
        p((0, 0.087, 0.26), (0.01, 0.026, 0.02), rgb(230, 230, 230))
        self.dot = None
        self.sight_corners = []
        self.muzzle = Entity(parent=self.gun, z=0.31, y=0.04)
        self.eject = Entity(parent=self.gun, x=0.04, y=0.06, z=0.1)

    def build_sniper(self):
        self.gun = Entity(parent=camera, position=self.weapon['hip'], scale=self.GUN_SCALE)
        dark = rgb(34, 36, 38)
        mid = rgb(58, 60, 64)
        wood = rgb(95, 70, 45)

        def p(pos, sc, col):
            return Entity(parent=self.gun, model='cube', color=col, position=pos, scale=sc, shader=LIT)
        p((0, 0, 0), (0.08, 0.1, 0.5), dark)                    # boîtier
        p((0, -0.01, -0.45), (0.075, 0.16, 0.42), wood)         # crosse
        p((0, 0.0, 0.42), (0.07, 0.08, 0.4), wood)              # fût
        p((0, 0.02, 0.95), (0.03, 0.03, 0.75), dark)            # long canon
        p((0, 0.02, 1.34), (0.045, 0.045, 0.08), mid)           # frein de bouche
        p((0, -0.1, 0.05), (0.06, 0.1, 0.09), mid)              # petit chargeur
        p((0, -0.1, -0.13), (0.055, 0.14, 0.07), dark)          # poignée
        p((0.06, 0.03, -0.05), (0.06, 0.02, 0.02), mid)         # levier de culasse
        # lunette
        p((0, 0.09, 0.02), (0.04, 0.04, 0.12), dark)            # montage
        p((0, 0.14, 0.05), (0.07, 0.07, 0.42), dark)            # tube
        p((0, 0.14, 0.28), (0.09, 0.09, 0.07), mid)             # objectif
        p((0, 0.14, -0.18), (0.085, 0.085, 0.06), mid)          # oculaire
        self.dot = None
        self.sight_corners = []
        self.muzzle = Entity(parent=self.gun, z=1.4, y=0.02)
        self.eject = Entity(parent=self.gun, x=0.05, y=0.03, z=0.02)

    def build_rifle(self):
        """Fusil d'assaut type M4 (un seul maillage fusionné) avec viseur holographique."""
        self.gun = Entity(parent=camera, position=self.weapon['hip'], scale=self.GUN_SCALE)
        blk = rgb(30, 31, 34)          # anodisé noir
        dark = rgb(44, 45, 49)
        mid = rgb(70, 72, 76)
        fde = rgb(150, 128, 95)        # garde-main et crosse couleur terre (FDE)
        b = MeshBuilder()
        # carcasse supérieure / inférieure
        b.box((0, 0.02, 0.02), (0.075, 0.075, 0.42), dark)
        b.box((0, -0.045, -0.03), (0.068, 0.06, 0.32), blk)
        b.box((0, -0.085, 0.1), (0.075, 0.07, 0.11), blk)                    # puits de chargeur
        b.box((0.039, 0.022, 0.03), (0.004, 0.032, 0.1), mid)                # fenêtre d'éjection
        b.box((0.045, 0.03, -0.07), (0.022, 0.022, 0.035), mid)              # assistance de fermeture
        b.box((0, 0.052, -0.2), (0.07, 0.014, 0.035), mid)                   # levier d'armement
        b.box((-0.038, -0.03, 0.02), (0.006, 0.02, 0.03), mid)               # arrêtoir de culasse
        # chargeur courbe (deux segments inclinés vers l'avant)
        b.box((0, -0.18, 0.115), (0.055, 0.15, 0.095), mid, rx=-7)
        b.box((0, -0.31, 0.15), (0.053, 0.13, 0.09), mid, rx=-17)
        b.box((0, -0.38, 0.175), (0.06, 0.02, 0.1), blk, rx=-17)             # talon du chargeur
        # détente, pontet, poignée inclinée
        b.box((0, -0.105, -0.02), (0.022, 0.012, 0.11), blk)
        b.box((0, -0.085, -0.03), (0.012, 0.035, 0.012), mid)
        b.box((0, -0.15, -0.11), (0.056, 0.15, 0.066), fde, rx=18)
        # tube de crosse et crosse rétractable
        b.cylinder((0, 0.005, -0.4), 0.022, 0.22, blk, seg=8, axis='z')
        b.box((0, -0.02, -0.5), (0.062, 0.1, 0.2), fde)
        b.box((0, 0.03, -0.49), (0.05, 0.03, 0.17), fde)
        b.box((0, -0.035, -0.605), (0.07, 0.14, 0.03), blk)                  # plaque de couche
        # garde-main à rails (M-LOK) et ses fentes
        b.box((0, 0.018, 0.4), (0.082, 0.082, 0.36), fde)
        for k in range(4):
            for sx in (-1, 1):
                b.box((sx * 0.042, 0.012, 0.28 + k * 0.075), (0.004, 0.022, 0.04), blk)
            b.box((0, -0.024, 0.28 + k * 0.075), (0.022, 0.004, 0.04), blk)
        b.box((0, -0.05, 0.47), (0.034, 0.06, 0.05), blk, rx=-12)            # poignée d'appui
        # rail Picatinny sur toute la longueur, avec ses crans
        b.box((0, 0.064, 0.19), (0.03, 0.012, 0.76), blk)
        for k in range(22):
            b.box((0, 0.073, -0.17 + k * 0.034), (0.034, 0.007, 0.014), blk)
        # canon, bloc d'emprunt de gaz, cache-flamme
        b.cylinder((0, 0.02, 0.57), 0.014, 0.24, dark, seg=8, axis='z')
        b.box((0, 0.02, 0.62), (0.032, 0.036, 0.03), blk)
        b.box((0, 0.08, 0.55), (0.022, 0.012, 0.05), blk)                   # guidon repliable (couché)
        b.cylinder((0, 0.02, 0.8), 0.021, 0.085, blk, seg=8, axis='z')
        for sx, sy in ((0, 1), (1, 0), (-1, 0)):                            # fentes du cache-flamme
            b.box((sx * 0.02, 0.02 + sy * 0.02, 0.85), (0.006, 0.006, 0.05), rgb(10, 10, 10))
        # viseur point rouge à tube rond (type Aimpoint) : corps cylindrique, bagues de fixation, molettes
        cy = self.DOT.y
        b.box((0, 0.082, 0.085), (0.045, 0.018, 0.1), blk)                   # embase sur le rail
        for z in (0.1, 0.13):
            b.box((0, 0.1, z), (0.03, 0.03, 0.016), blk)                     # colonnes des bagues
            b.tube((0, cy, z), 0.049, 0.054, 0.016, blk, seg=20)             # bagues
        b.tube((0, cy, 0.115), 0.045, 0.049, 0.05, dark, seg=24, col_in=rgb(40, 40, 44))   # corps court et fin
        b.tube((0, cy, 0.143), 0.045, 0.051, 0.008, blk, seg=24)             # bague avant
        b.cylinder((0.049, cy, 0.115), 0.01, 0.014, mid, seg=8, axis='x')     # molette de dérive
        b.cylinder((0, cy + 0.049, 0.115), 0.01, 0.014, mid, seg=8)           # molette de hausse
        b.build(self.gun, cast_shadows=False)
        # lentille à peine teintée (ronde)
        Entity(parent=self.gun, model='circle', color=rgb(150, 200, 235, 16), position=(0, cy, 0.14),
               scale=0.088, unlit=True)
        (x0, y0), (x1, y1) = self.SIGHT
        self.sight_corners = [Entity(parent=self.gun, position=(x, y, 0.14))
                              for x in (x0, x1) for y in (y0, y1)]
        # réticule : cercle fin et point central (le point visé)
        self.dot = Entity(parent=self.gun, model='quad', texture=holo_texture(), position=self.DOT,
                          scale=0.03, unlit=True, visible=False)
        self.muzzle = Entity(parent=self.gun, z=0.9, y=0.02)
        self.eject = Entity(parent=self.gun, x=0.05, y=0.03, z=0.03)

    def take_damage(self, dmg, from_pos):
        if self.dead or self.game.paused or self.drone is not None:
            return
        self.hp -= dmg
        self.last_hurt = self.game.t
        self.shake = max(self.shake, 0.15)
        self.game.hud.flash_damage(from_pos)
        PAD.rumble(0.7, 0.3, 160)
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            self.game.game_over()

    # -- batterie anti-aérienne ----------------------------------------------------
    def mount_aa(self, aa):
        """Carré / V près de la batterie : on s'installe au poste de tir."""
        if self.dead or self.drone is not None:
            return
        if self.tps:
            self.toggle_view()
        self.mount = aa
        self.crouching = False
        self.reload_t = 0
        self.armed = False
        self.rotation_y = aa.yaw.rotation_y
        self.pivot.rotation_x = 0
        self.gun.visible = False
        self.game.hud.add_feed('Batterie anti-aérienne : Clic G / R2 tirer · Clic D / L2 zoom · V / Carré quitter')
        PAD.rumble(0.3, 0.2, 100)

    def dismount(self):
        aa = self.mount
        if aa is None:
            return
        self.mount = None
        back = aa.pos - flat(aa.yaw.forward) * 2.0          # on descend derrière le siège
        self.position = self.world.resolve(Vec3(back.x, 0, back.z), PLAYER_RADIUS)
        self.vel = Vec3(0, 0, 0)
        self.vy = 0
        camera.fov = 90
        self.armed = False
        self.game.hud.add_feed('Vous quittez la batterie')

    def update_mounted(self, dt):
        aa = self.mount
        pad = PAD
        zoom = held_keys['right mouse'] or pad.l2 > 0.4
        sens = 0.5 if zoom else 1.0
        if mouse.locked:
            self.rotation_y += mouse.velocity[0] * self.sensitivity[1] * sens
            self.pivot.rotation_x -= mouse.velocity[1] * self.sensitivity[0] * sens
        if pad.rx or pad.ry:
            k = sens * dt
            self.rotation_y += pad.rx * abs(pad.rx) * PAD_LOOK_SPEED[0] * k
            self.pivot.rotation_x -= pad.ry * abs(pad.ry) * PAD_LOOK_SPEED[1] * k
        self.pivot.rotation_x = clamp(self.pivot.rotation_x, -80, 10)     # de -10° à +80° en site
        aa.aim(self.rotation_y, self.pivot.rotation_x)
        eye = aa.eye.world_position
        self.position = Vec3(eye.x, 0, eye.z)
        self.pivot.position = (0, eye.y, 0)
        self.pivot.rotation_z = 0
        self.speed_now = 0
        self.ads = 0
        camera.fov = lerp(camera.fov, 40 if zoom else 75, min(1, dt * 10))
        self.shake = max(0, self.shake - dt * 1.2)
        head = Vec3(0, 0, 0)
        if self.shake > 0:
            head += Vec3(random.uniform(-1, 1), random.uniform(-1, 1), 0) * self.shake * 0.08
        camera.position = head
        self.gun.visible = False
        if self.game.t - self.last_hurt > 5 and self.hp < 100:
            self.hp = min(100, self.hp + 8 * dt)
        aa.cool(dt)
        pad_fire = pad.r2 > 0.35
        trigger = held_keys['left mouse'] or held_keys['p'] or pad_fire
        if not trigger:
            self.armed = True
        self.cooldown -= dt
        if trigger and self.armed and self.cooldown <= 0 and (mouse.locked or pad_fire):
            if aa.fire(self.game):
                self.cooldown = aa.COOLDOWN
                self.shake = max(self.shake, 0.06)
                self.pivot.rotation_x -= 0.15
                PAD.rumble(0.5, 0.4, 70)
        self.game.hud.scope_visible(False)
        self.game.hud.crosshair_visible(True)
        self.update_sight_zoom()

    def update(self):
        if self.game.paused or self.dead or self.game.choosing:
            return
        if self.drone is not None:
            return                      # c'est le drone qui est piloté
        dt = time.dt
        if self.mount is not None:
            self.update_mounted(dt)
            return
        w = self.weapon
        pad = PAD
        aiming = (held_keys['right mouse'] or pad.l2 > 0.4) and self.reload_t <= 0 and not self.sprinting
        self.ads = lerp(self.ads, 1.0 if aiming else 0.0, min(1, dt * 14))
        self.switch_t = max(0.0, self.switch_t - dt)

        # se pencher (en visant) : L3 gauche / R3 droite à la manette (appui = bascule), A / F au clavier
        if aiming:
            if pad.pressed['l3']:
                self.lean_pad = 0 if self.lean_pad == -1 else -1
            if pad.pressed['r3']:
                self.lean_pad = 0 if self.lean_pad == 1 else 1
        else:
            self.lean_pad = 0
        kb_lean = (held_keys['f'] - held_keys['a']) if aiming else 0
        self.lean_t = lerp(self.lean_t, kb_lean or self.lean_pad, min(1, dt * 10))

        # regard à la souris (plus précis en visée)
        sens = lerp(1.0, w['ads_sens'], self.ads)
        if mouse.locked:
            self.rotation_y += mouse.velocity[0] * self.sensitivity[1] * sens
            self.pivot.rotation_x -= mouse.velocity[1] * self.sensitivity[0] * sens
        # regard au stick droit : courbe progressive (précis au centre, rapide au bout)
        if pad.rx or pad.ry:
            assist = 0.55 if self.enemy_under_crosshair() else 1.0     # légère aide à la visée
            k = sens * assist * dt
            self.rotation_y += pad.rx * abs(pad.rx) * PAD_LOOK_SPEED[0] * k
            self.pivot.rotation_x -= pad.ry * abs(pad.ry) * PAD_LOOK_SPEED[1] * k
        self.pivot.rotation_x = clamp(self.pivot.rotation_x, -89, 89)

        # déplacement : E avancer, S reculer, Q gauche, D droite (+ flèches) ; Z pour courir
        # stick gauche : déplacement analogique (on marche doucement en poussant peu le stick)
        fwd = clamp(held_keys['e'] + held_keys['up arrow'], 0, 1) - clamp(held_keys['s'] + held_keys['down arrow'], 0, 1)
        side = clamp(held_keys['d'] + held_keys['right arrow'], 0, 1) - clamp(held_keys['q'] + held_keys['left arrow'], 0, 1)
        fwd = clamp(fwd + pad.ly, -1, 1)
        side = clamp(side + pad.lx, -1, 1)
        direction = flat(self.forward) * fwd + flat(self.right) * side
        if direction.length() > 1:
            direction = direction.normalized()
        # L3 : course maintenue tant qu'on pousse le stick vers l'avant (sauf en visée : L3 = se pencher)
        if pad.pressed['l3'] and not aiming:
            self.pad_sprint = True
        if fwd < 0.5:
            self.pad_sprint = False
        self.sprinting = bool(held_keys['z'] or held_keys['shift'] or self.pad_sprint) and fwd > 0 and self.ads < 0.3
        if self.sprinting:
            self.crouching = False           # courir relève le joueur
        self.crouch_t = lerp(self.crouch_t, 1.0 if self.crouching else 0.0, min(1, dt * 10))
        speed = (9 if self.sprinting else 5.5) * lerp(1, 0.6, self.ads) * lerp(1, 0.5, self.crouch_t)
        accel = 12 if self.grounded else 3
        self.vel = lerp(self.vel, direction * speed, min(1, dt * accel))
        new = self.world.resolve(self.position + self.vel * dt, PLAYER_RADIUS, self.y)
        for v in self.game.vehicles:
            new = v.push_out(new, PLAYER_RADIUS)
        new = self.world.pit_resolve(self.position, new, PLAYER_RADIUS, self.y)

        # gravité et saut
        floor_h = self.world.floor_height(new.x, new.z, PLAYER_RADIUS, self.y)
        self.vy -= GRAVITY * dt
        new.y = self.y + self.vy * dt
        was_air = not self.grounded
        if new.y <= floor_h:
            if was_air and self.vy < -5:
                self.land_dip = min(0.12, -self.vy * 0.012)
            new.y = floor_h
            self.vy = 0
            self.grounded = True
        else:
            self.grounded = new.y - floor_h < 0.02
        self.speed_now = flat(new - self.position).length() / max(dt, 1e-4)
        self.position = new

        if self.game.t - self.last_hurt > 5 and self.hp < 100:
            self.hp = min(100, self.hp + 8 * dt)

        # tête : hauteur (accroupi) et penché ; on ne passe jamais la tête à travers un mur
        lean = 0.0
        if abs(self.lean_t) > 0.01:
            side_dir = self.right * math.copysign(1, self.lean_t)
            base_eye = self.position + Vec3(0, lerp(EYE_STAND, EYE_CROUCHED, self.crouch_t), 0)
            want = abs(self.lean_t) * LEAN_DIST
            hit = raycast(base_eye, side_dir, want + 0.25, traverse_target=self.world.level)
            lean = math.copysign(min(want, max(0.0, hit.distance - 0.25)) if hit.hit else want, self.lean_t)
        self.pivot.position = (lean, lerp(EYE_STAND, EYE_CROUCHED, self.crouch_t), 0)
        self.pivot.rotation_z = self.lean_t * LEAN_ROLL

        # caméra : zoom, balancement de tête, secousses
        camera.fov = lerp(90, w['ads_fov'], self.ads)
        move = min(1, self.speed_now / 5) if self.grounded else 0
        self.bob_t += dt * (13 if self.sprinting else 9) * move
        self.land_dip = max(0, self.land_dip - dt * 0.5)
        self.shake = max(0, self.shake - dt * 1.2)
        head = Vec3(math.sin(self.bob_t * 0.5) * 0.03, abs(math.cos(self.bob_t * 0.5)) * 0.04, 0) \
            * move * (1 - self.ads * 0.8)
        head.y -= self.land_dip
        if self.shake > 0:
            head += Vec3(random.uniform(-1, 1), random.uniform(-1, 1), 0) * self.shake * 0.12
        scoped_now = w['scope'] and self.ads > 0.85
        if self.tps and not scoped_now:
            # caméra au-dessus de l'épaule droite, rapprochée en visée ; jamais derrière un mur
            want = Vec3(lerp(0.7, 0.5, self.ads), lerp(0.3, 0.12, self.ads), lerp(-3.2, -1.5, self.ads))
            world_off = self.pivot.right * want.x + self.pivot.up * want.y + self.pivot.forward * want.z
            dist = world_off.length()
            hit = raycast(self.pivot.world_position, world_off / dist, dist + 0.3, traverse_target=self.world.level)
            if hit.hit:
                want *= max(0.1, (hit.distance - 0.3) / dist)
            head += want
        camera.position = head
        if self.avatar is not None and self.tps:
            self.drive_avatar(dt)

        # arme : visée, balancement, recul
        self.recoil = max(0, self.recoil - dt * 6)
        if self.recoil_pitch > 0 and self.cooldown < -0.05:
            back = min(self.recoil_pitch, dt * 6)
            self.recoil_pitch -= back
            self.pivot.rotation_x += back
        sway = Vec3(math.sin(self.bob_t) * 0.012, abs(math.cos(self.bob_t)) * 0.01, 0) * move * (1 - self.ads * 0.85)
        base = lerp(w['hip'], w['ads'], self.ads)
        if self.sprinting:
            base += Vec3(0.02, -0.03, -0.03)
        base += Vec3(0, -self.switch_t * 0.6, 0)       # l'arme remonte après un changement
        self.gun.position = base + sway + Vec3(0, -self.recoil * 0.012, -self.recoil * 0.05)
        self.gun.rotation = Vec3(-self.recoil * 5 * (1 - 0.6 * self.ads), 18 if self.sprinting else 0, 0)
        if self.dot is not None:
            self.dot.visible = self.ads > 0.6
        self.update_sight_zoom()
        scoped = w['scope'] and self.ads > 0.85
        self.gun.visible = not scoped and not self.tps   # dans la lunette ou en 3e personne : pas d'arme à l'écran
        self.game.hud.scope_visible(scoped, w['scope'])
        if scoped and w['scope'] == 'rpg':                     # télémètre de la lunette du RPG
            hit = raycast(camera.world_position, camera.forward, 200, ignore=[self])
            self.game.hud.set_text(self.game.hud.range_txt, f'DISTANCE  {hit.distance:.0f} m' if hit.hit
                                   else 'DISTANCE  > 200 m')
        self.game.hud.crosshair_visible((self.ads < 0.5 or self.tps) and not scoped)

        pad_fire = pad.r2 > 0.35
        trigger = held_keys['left mouse'] or held_keys['p'] or pad_fire
        if not trigger:
            self.armed = True
            self.trigger_ready = True
        self.cooldown -= dt
        if self.reload_t > 0:
            self.reload_t -= dt
            k = math.sin(clamp(self.reload_t / w['reload'], 0, 1) * math.pi)
            self.gun.rotation_x = 30 * k
            self.gun.rotation_z = 20 * k
            if self.reload_t <= 0:
                self.mag = w['mag']
        elif trigger and self.armed and (w['auto'] or self.trigger_ready) and self.cooldown <= 0 \
                and self.switch_t <= 0 and (mouse.locked or pad_fire):
            self.trigger_ready = False               # sniper : relâcher pour tirer à nouveau
            self.shoot()

    def update_sight_zoom(self):
        """Grossissement limité à la vitre du viseur : on projette ses coins à l'écran
        et le shader de caméra agrandit l'image seulement dans ce rectangle."""
        z = self.weapon['sight_zoom']
        k = smoothstep((self.ads - 0.75) / 0.2) if z > 1 and self.reload_t <= 0 and not self.tps \
            and self.mount is None and self.drone is None else 0
        if k <= 0:
            if self._zoom_on:
                camera.set_shader_input('zoom', 1.0)
                self._zoom_on = False
            return
        cam = application.base.cam
        lens = camera.lens
        us, vs = [], []
        for c in self.sight_corners:
            p2 = Point2()
            lens.project(cam.getRelativePoint(c, Point3(0, 0, 0)), p2)
            us.append((p2.x + 1) / 2)
            vs.append((p2.y + 1) / 2)
        p2 = Point2()
        lens.project(cam.getRelativePoint(self.dot, Point3(0, 0, 0)), p2)
        camera.set_shader_input('zoom_rect', Vec4(min(us), min(vs), max(us), max(vs)))
        camera.set_shader_input('zoom_center', Vec2((p2.x + 1) / 2, (p2.y + 1) / 2))
        camera.set_shader_input('zoom', lerp(1.0, z, k))
        self._zoom_on = True

    def fire_rocket(self):
        w = self.weapon
        self.mag -= 1
        self.cooldown = w['cooldown']
        self.recoil = 1.5
        muzzle = self.avatar.muzzle if (self.tps and self.avatar is not None) else self.muzzle
        muzzle_flash(muzzle, scale=w['flash'], intensity=w['flash_intensity'], life=w['flash_life'])
        PAD.rumble(1.0, 0.8, 300)
        origin = camera.world_position
        if self.tps:
            origin = origin + camera.forward * max(0.0, (self.eye - origin).dot(camera.forward))
        spread = w['spread'] * lerp(1, w['ads_spread'], self.ads)
        d = (camera.forward + camera.right * random.uniform(-spread, spread)
             + camera.up * random.uniform(-spread, spread)).normalized()
        # la roquette part du tube mais vise le centre de l'écran
        target_hit = raycast(origin, d, 200, ignore=[self])
        target = target_hit.world_point if target_hit.hit else origin + d * 200
        start = muzzle.world_position + d * 0.3
        Rocket(self.game, start, target - start)
        self.pivot.rotation_x -= w['kick']
        self.recoil_pitch = min(self.recoil_pitch + w['kick'] * 0.8, 6)
        self.shake = max(self.shake, 0.2)
        for e in self.game.enemies:
            if not e.dead and flat_dist(e.position, self.position) < e.hear_radius:
                FXM.later(random.uniform(0.1, 0.4) * e.reaction, e.hear_shot, Vec3(self.position))
        if self.mag <= 0:
            self.game.hud.add_feed('Dernière roquette tirée')

    def enemy_under_crosshair(self):
        """Aide à la visée manette : le regard ralentit quand un ennemi est sous le réticule."""
        hit = raycast(camera.world_position, camera.forward, 80, ignore=[self])
        return hit.hit and isinstance(getattr(hit.entity, 'owner', None), Enemy)

    def jump(self):
        if self.crouching:                    # accroupi : Croix / Espace relève d'abord
            self.crouching = False
            return
        if self.grounded and not self.dead:
            self.vy = 7.5
            self.grounded = False

    def reload(self):
        if self.weapon.get('no_reload'):
            if self.mag <= 0:
                self.game.hud.add_feed('Plus de roquettes')
            return
        if self.reload_t <= 0 and self.mag < self.weapon['mag']:
            self.reload_t = self.weapon['reload']

    def shoot(self):
        if self.mag <= 0:
            self.reload()
            return
        w = self.weapon
        if w.get('rocket'):
            self.fire_rocket()
            return
        self.mag -= 1
        self.cooldown = w['cooldown']
        self.recoil = min(1.5, self.recoil + (1.2 if w['scope'] or w.get('pellets') else 0.5))
        muzzle = self.avatar.muzzle if (self.tps and self.avatar is not None) else self.muzzle
        muzzle_flash(muzzle, scale=w['flash'], intensity=w['flash_intensity'], life=w['flash_life'])
        if w['scope'] or w.get('pellets'):
            PAD.rumble(0.9, 0.6, 180)
        else:
            PAD.rumble(0.15, 0.35, 60)
        if not self.tps:
            shell_casing(self.eject.world_position, camera.right)
        spread = (w['spread'] + w['move_spread'] * min(1, self.speed_now / 9) + (0.02 if not self.grounded else 0)) \
            * lerp(1, w['ads_spread'], self.ads)
        origin = camera.world_position
        if self.tps:     # la balle part du joueur, pas de la caméra placée derrière lui
            origin = origin + camera.forward * max(0.0, (self.eye - origin).dot(camera.forward))
        start = muzzle.world_position
        hits = {}        # dégâts cumulés par ennemi (plusieurs plombs)
        for i in range(w.get('pellets', 1)):
            d = camera.forward + camera.right * random.uniform(-spread, spread) + camera.up * random.uniform(-spread, spread)
            d = d.normalized()
            hit = raycast(origin, d, 200, ignore=[self])
            end = hit.world_point if hit.hit else origin + d * 200
            if i < 3:
                tracer(start, end, rgb(255, 240, 160), thickness=w['tracer'][0], life=w['tracer'][1])
            if hit.hit:
                ent = hit.entity
                owner = getattr(ent, 'owner', None)
                if isinstance(owner, Enemy):
                    h = hits.setdefault(owner, [0, ent.zone, hit.world_point])
                    h[0] += w['dmg'].get(ent.zone, 25)
                    if ent.zone == 'head':
                        h[1] = 'head'
                elif isinstance(owner, Vehicle):
                    owner.bullet_hit(w['dmg'].get('body', 30), hit.world_point)
                else:
                    impact(hit.world_point, hit.world_normal)
        for owner, (dmg, zone, point) in hits.items():
            owner.take_hit(dmg, zone, point)
            self.game.hud.hitmarker(zone == 'head' or owner.dead)
        kick = w['kick'] * lerp(1, 0.6, self.ads)
        self.pivot.rotation_x -= kick
        self.recoil_pitch = min(self.recoil_pitch + kick * 0.8, 6)
        self.rotation_y += random.uniform(-0.15, 0.15)
        for e in self.game.enemies:        # les ennemis entendent le tir
            if not e.dead and flat_dist(e.position, self.position) < e.hear_radius:
                FXM.later(random.uniform(0.1, 0.5) * e.reaction, e.hear_shot, Vec3(self.position))


# ---------------------------------------------------------------------------
# Ultime : drone Reaper (3 tirs à la tête pour le débloquer, flèche gauche / U)
# ---------------------------------------------------------------------------

ULT_HEADSHOTS = 3                 # tirs à la tête qui débloquent le drone


class IRMissile(Entity):
    """Missile à guidage infrarouge MANUEL (pas de verrouillage) : jusqu'à l'impact, il suit
    la tache infrarouge que le drone projette au centre de sa caméra. Le pilote garde le réticule
    sur la cible ; s'il le déplace, le missile corrige sa trajectoire."""

    def __init__(self, game, drone, start, direction):
        super().__init__(model='cube', color=rgb(200, 200, 195), scale=(0.18, 0.18, 0.9), position=start, shader=LIT)
        self.game = game
        self.drone = drone
        self.dir = direction.normalized()
        self.point = drone.laser
        self.speed = 30.0
        self.life = 8.0
        self.smoke_t = 0.0
        self.look_at(start + self.dir)
        Entity(parent=self, model='quad', texture='circle', color=rgb(255, 230, 170), z=-0.7, scale=(2.2, 2.2),
               billboard=True, unlit=True)
        drone.in_flight.append(self)

    def update(self):
        if self.game.paused:
            return
        dt = time.dt
        self.life -= dt
        self.speed = min(80.0, self.speed + 55 * dt)
        d = self.drone
        if d is not None and d.enabled:
            self.point = d.laser                   # suit le point désigné par le drone
        want = self.point - self.position
        dist = want.length()
        if dist < 1.0:
            self.explode(Vec3(self.point))
            return
        want /= max(dist, 1e-4)
        k = min(1.0, dt * 7.0)                     # guidage : virage progressif vers la tache infrarouge
        self.dir = (self.dir * (1 - k) + want * k).normalized()
        step = self.speed * dt
        hit = raycast(self.world_position, self.dir, step + 0.2, ignore=[self, self.game.player])
        if hit.hit:
            self.explode(hit.world_point - self.dir * 0.2)
            return
        self.position += self.dir * step
        self.look_at(self.position + self.dir)
        self.smoke_t -= dt
        if self.smoke_t <= 0:
            self.smoke_t = 0.03
            sm = FXM.get('sphere')
            sm.color = rgb(220, 220, 215, 150)
            sm.position = self.position - self.dir * 0.5
            sm.scale = 0.25
            FXM.play(sm, 1.0, scale=Vec3(1.2, 1.2, 1.2), col=rgb(180, 180, 175, 0))
        if self.life <= 0 or self.y < -0.5:
            self.explode(Vec3(self.position))

    def explode(self, pos):
        game = self.game
        d = self.drone
        if d is not None and self in d.in_flight:
            d.in_flight.remove(self)
        destroy(self)
        blast(game, pos, 5.0, 400, 100, size=1.4, vdmg=VDMG_MISSILE)
        if game.player.drone is not None:
            game.player.drone.shake = 0.5


class ReaperDrone(Entity):
    """Drone MQ-9 Reaper piloté pendant toute une manche : il tourne au-dessus de la zone visée.
    Caméra normale ou thermique (N / Triangle), canon à obus explosifs par paquets de 20,
    6 missiles à guidage infrarouge manuel."""
    ALT = 48
    FLY_SPEED = 20.0     # m/s, stick gauche poussé à fond
    MISSILES = 6
    PACK = 20            # obus par paquet
    PACK_RELOAD = 3.0    # secondes pour engager un nouveau paquet

    def __init__(self, game):
        super().__init__()
        self.game = game
        p = game.player
        self.center = Vec3(p.x, 0, p.z) - flat(p.forward) * 10     # le drone arrive derrière le joueur
        self.aim = Vec3(p.x, 0, p.z) + flat(p.forward) * 25
        self.fly_vel = Vec3(0, 0, 0)
        self.bob = 0.0
        self.missiles = self.MISSILES
        self.shells = self.PACK
        self.pack_t = 0.0
        self.cannon_t = 0.0
        self.missile_t = 0.0
        self.in_flight = []
        self.laser = Vec3(self.aim)
        self.aim_vel = Vec3(0, 0, 0)
        self.edge_t = 0.0
        self.hp = 100
        self.flares = 8
        self.flare_t = 0.0
        self.shake = 0.0
        self.fov = 50.0
        self.saved_nv = game.nv
        game.set_nv(False)
        camera.parent = self
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = self.fov
        camera.set_shader_input('ir_gain', 6.0 if game.night else 1.0)
        camera.set_shader_input('zoom', 1.0)
        scene.set_shader_input('fog_density', 0.003)
        # tache du désignateur infrarouge (visible quand un missile est en vol)
        self.spot = Entity(model='sphere', color=rgb(255, 40, 40), scale=0.5, unlit=True, enabled=False)
        self.build_overlay()
        self.set_vision(game.night)          # de jour : caméra normale ; de nuit : thermique
        self.update_position(0)

    def set_vision(self, thermal):
        self.thermal = thermal
        g = self.game
        camera.set_shader_input('ir_on', 1.0 if thermal else 0.0)
        for e in g.enemies + g.corpses:
            set_hot(e, (0.45 if e.dead else 1.0) if thermal else 0.0)
        for v in g.vehicles:
            set_hot(v, (0.8 if v.alive else 0.6) if thermal else 0.0)
        HUD.set_text(self.title, 'MQ-9 REAPER  ·  ' + ('CAMÉRA THERMIQUE (blanc = chaud)' if thermal
                                                        else 'CAMÉRA NORMALE'))

    def toggle_vision(self):
        self.set_vision(not self.thermal)
        PAD.rumble(0.1, 0.2, 60)

    # -- interface -----------------------------------------------------------
    def build_overlay(self):
        ui = camera.ui
        ar = camera.aspect_ratio / 2
        white = color.rgba(1, 1, 1, 0.9)
        self.ui = Entity(parent=ui, z=0.5)
        for pos, sc in [((0.03, 0), (0.035, 0.003)), ((-0.03, 0), (0.035, 0.003)),
                        ((0, 0.03), (0.003, 0.035)), ((0, -0.03), (0.003, 0.035))]:
            Entity(parent=self.ui, model='quad', color=white, position=pos, scale=sc)
        for sx in (-1, 1):                                          # crochets du cadre de visée
            for sy in (-1, 1):
                Entity(parent=self.ui, model='quad', color=white, position=(sx * 0.2, sy * 0.185), scale=(0.04, 0.004))
                Entity(parent=self.ui, model='quad', color=white, position=(sx * 0.218, sy * 0.165), scale=(0.004, 0.04))
        self.guide_txt = Text(parent=self.ui, text='', origin=(0, 0), y=-0.23, scale=1.1, color=rgb(255, 80, 70))
        self.threat_txt = Text(parent=self.ui, text='', origin=(0, 0), y=0.24, scale=1.5, color=rgb(255, 60, 50))
        self.title = Text(parent=self.ui, text='', origin=(0, 0), y=0.42, scale=1.1, color=white)
        self.info = Text(parent=self.ui, text='', origin=(-0.5, 0.5), position=(-ar + 0.04, -0.28), scale=1.0,
                         color=white)
        self.alt = Text(parent=self.ui, text='', origin=(0.5, 0.5), position=(ar - 0.04, 0.12), scale=1.0, color=white)
        Text(parent=self.ui, text='Retour au sol à la fin de la manche', origin=(0, 0), y=0.38, scale=0.8,
             color=color.rgba(1, 1, 1, 0.6))

    def update_overlay(self):
        g = self.game
        alive = sum(1 for e in g.enemies if not e.dead)
        shells = f'RECHARGEMENT {self.pack_t:.1f} s' if self.pack_t > 0 else f'{self.shells}/{self.PACK}'
        HUD.set_text(self.info, f'DRONE  {max(0, int(self.hp))} %   ·   LEURRES  {self.flares}   [F / L1]\n'
                                f'CANON 30 mm EXPLOSIF  {shells}   [Clic G / R2]\n'
                                f'MISSILES IR  {self.missiles}/{self.MISSILES}   [Espace / R1]\n'
                                f'VISION  {"THERMIQUE" if self.thermal else "NORMALE"}   [N / Triangle]\n'
                                f'PILOTER : stick gauche / E,S,Q,D   ·   VISER : stick droit / souris   ·   ZOOM : L2 / clic D')
        HUD.set_text(self.alt, f'ALT {self.ALT} m\nCAP {int(self.rotation_y) % 360:03d}°\nCIBLES {alive}')
        HUD.set_text(self.guide_txt, 'GUIDAGE IR : gardez le réticule sur la cible' if self.in_flight else '')
        threat = any(m.decoy is None for m in g.sams)
        HUD.set_text(self.threat_txt, ('!  MISSILE SOL-AIR EN APPROCHE — LEURRES : F / L1  !'
                                       if threat and int(g.t * 4) % 2 == 0 else ('' if not threat else ' ')))

    # -- vol -----------------------------------------------------------------
    def update_position(self, dt):
        self.bob += dt
        self.position = self.center + Vec3(0, self.ALT + math.sin(self.bob * 0.8) * 0.4, 0)
        self.look_at(Vec3(self.aim.x, 0, self.aim.z))
        self.shake = max(0.0, self.shake - dt)
        camera.position = Vec3(random.uniform(-1, 1), random.uniform(-1, 1), 0) * self.shake * 0.3

    def update(self):
        g = self.game
        if g.paused:
            return
        dt = time.dt
        pad = PAD
        zoom = held_keys['right mouse'] or pad.l2 > 0.4
        self.fov = lerp(self.fov, 20.0 if zoom else 50.0, min(1, dt * 6))
        camera.fov = self.fov
        z = self.fov / 50
        right = flat(self.right).normalized()
        fwd = flat(self.forward).normalized()
        dist = (self.aim - self.position).length()
        if mouse.locked:
            k = dist * 2 * math.tan(math.radians(self.fov / 2))
            self.aim += right * mouse.velocity[0] * k + fwd * mouse.velocity[1] * k * 1.3
        # VISÉE (canon et missiles) : stick droit ou souris. Courbe progressive (précis au centre),
        # accélération quand le stick reste en butée, ralentissement quand le réticule passe sur une cible.
        # La visée est stabilisée : le point visé au sol ne bouge pas quand le drone se déplace.
        want = Vec3(0, 0, 0)
        rm = math.hypot(pad.rx, pad.ry)
        if rm > 0:
            self.edge_t = self.edge_t + dt if rm > 0.9 else 0.0
            boost = 1 + min(1.5, self.edge_t * 2.5)
            want += (right * pad.rx + fwd * pad.ry) * (rm ** 1.8 / rm * 16 * boost)
        else:
            self.edge_t = 0.0
        near = any(not e.dead and flat_dist(e.position, self.laser) < 4 for e in g.enemies) or \
            any(v.alive and flat_dist(v.position, self.laser) < 5 for v in g.vehicles)
        want *= z * (0.45 if near else 1.0)                   # aide à la visée
        self.aim_vel = lerp(self.aim_vel, want, min(1, dt * 9))
        self.aim += self.aim_vel * dt

        # PILOTAGE du drone : stick gauche ou E/S/Q/D (et flèches). Il vole dans la direction poussée
        # (haut = vers l'avant de l'image), avec l'inertie d'un avion.
        mv = clamp(held_keys['e'] + held_keys['up arrow'], 0, 1) - clamp(held_keys['s'] + held_keys['down arrow'], 0, 1)
        sd = clamp(held_keys['d'] + held_keys['right arrow'], 0, 1) - clamp(held_keys['q'] + held_keys['left arrow'], 0, 1)
        lm = math.hypot(pad.lx, pad.ly)
        if lm > 0:
            k = lm ** 1.5 / lm
            mv += pad.ly * k
            sd += pad.lx * k
        fly = (fwd * clamp(mv, -1, 1) + right * clamp(sd, -1, 1)) * self.FLY_SPEED
        self.fly_vel = lerp(self.fly_vel, fly, min(1, dt * 2.2))
        self.center += self.fly_vel * dt
        w = g.world
        self.center = Vec3(clamp(self.center.x, -w.hx - 10, w.hx + 10), 0, clamp(self.center.z, -w.hz - 10, w.hz + 10))
        self.aim = Vec3(clamp(self.aim.x, -w.hx - 5, w.hx + 5), 0, clamp(self.aim.z, -w.hz - 5, w.hz + 5))
        # la caméra ne vise ni à la verticale exacte ni trop loin (12 à 75 m devant le drone)
        off = flat(self.aim - self.center)
        d = off.length()
        if d < 12:
            self.aim = self.center + (off / d if d > 0.01 else fwd) * 12
        elif d > 75:
            self.aim = self.center + off / d * 75
        self.update_position(dt)
        camera.set_shader_input('nv_time', g.t % 100)

        # désignateur infrarouge : la tache suit le centre de l'image, les missiles la suivent
        self.laser = self.aim_point()
        self.spot.enabled = bool(self.in_flight) and int(g.t * 8) % 2 == 0
        self.spot.position = self.laser

        # armes
        self.cannon_t -= dt
        self.missile_t -= dt
        if self.pack_t > 0:
            self.pack_t -= dt
            if self.pack_t <= 0:
                self.shells = self.PACK
        pad_fire = pad.r2 > 0.35
        if (held_keys['left mouse'] or held_keys['p'] or pad_fire) and self.cannon_t <= 0 and (mouse.locked or pad_fire):
            self.fire_cannon()
        if pad.pressed['r1']:
            self.fire_missile()
        if pad.pressed['triangle']:
            self.toggle_vision()
        if pad.pressed['l1']:
            self.drop_flares()
        self.flare_t -= dt
        self.update_overlay()

    def aim_point(self):
        hit = raycast(camera.world_position, self.forward, 250, ignore=[self.game.player, self.spot])
        return hit.world_point if hit.hit else Vec3(self.aim)

    def fire_cannon(self):
        if self.pack_t > 0:
            return
        self.cannon_t = 0.2
        self.shells -= 1
        if self.shells <= 0:
            self.pack_t = self.PACK_RELOAD
            self.game.hud.add_feed('Canon : nouveau paquet de 20 obus en cours')
        target = self.laser + Vec3(random.uniform(-0.8, 0.8), 0, random.uniform(-0.8, 0.8))
        start = self.position + Vec3(0, -1.5, 0)
        seen = start + (target - start).normalized() * 18       # traçante visible loin de la caméra
        tracer(seen, target, rgb(255, 245, 200), thickness=0.05, life=0.06)
        self.shake = max(self.shake, 0.12)
        PAD.rumble(0.4, 0.5, 90)
        FXM.later((target - start).length() / 500, blast, self.game, Vec3(target), 3.0, 200, 50, 0.7, False,
                  VDMG_DRONE_SHELL)

    def drop_flares(self):
        """F / L1 : leurres thermiques ; les missiles sol-air en vol ont de grandes chances de les suivre."""
        if self.flare_t > 0:
            return
        if self.flares <= 0:
            self.game.hud.add_feed('Plus de leurres')
            return
        self.flares -= 1
        self.flare_t = 1.0
        spots = []
        for _ in range(6):
            f = FXM.get('sphere')
            f.color = rgb(255, 240, 200)
            f.position = self.position + Vec3(random.uniform(-2, 2), -2, random.uniform(-2, 2))
            f.scale = 0.5
            end = f.position + Vec3(random.uniform(-8, 8), -18, random.uniform(-8, 8))
            FXM.play(f, 2.5, pos=end, scale=Vec3(0.2, 0.2, 0.2), col=rgb(255, 150, 60, 0))
            spots.append((f.position + end) / 2)
        for m in self.game.sams:
            if m.decoy is None and random.random() < 0.85:
                m.decoy = random.choice(spots)
        PAD.rumble(0.3, 0.3, 120)

    def take_damage(self, dmg, why=''):
        g = self.game
        self.hp -= dmg
        self.shake = max(self.shake, 0.6 if dmg > 20 else 0.2)
        PAD.rumble(0.8, 0.6, 250)
        if why:
            g.hud.add_feed(f'{why}  Drone : {max(0, int(self.hp))} %')
        if self.hp <= 0 and not getattr(self, 'is_shot_down', False):
            self.is_shot_down = True
            air_burst(Vec3(self.position), 2.0)
            self.finish(shot_down=True)

    def fire_missile(self):
        if self.missile_t > 0:
            return
        if self.missiles <= 0:
            self.game.hud.add_feed('Plus de missiles')
            return
        self.missiles -= 1
        self.missile_t = 1.0
        start = self.position + self.right * random.choice((-3, 3)) + Vec3(0, -1.2, 0)
        IRMissile(self.game, self, start, (self.laser - start) * 0.6 + Vec3(0, -8, 0) + self.forward * 5)
        PAD.rumble(0.6, 0.6, 200)
        self.game.hud.add_feed(f'Missile IR tiré ({self.missiles} restants) — guidez-le avec le réticule')

    def finish(self, shot_down=False):
        """Fin de la manche (ou drone abattu) : on rend l'antenne, le joueur réapparaît au sol."""
        g = self.game
        for m in list(g.sams):
            m.explode()
        p = g.player
        destroy(self.ui)
        destroy(self.spot)
        for m in list(self.in_flight):
            m.drone = None                     # les missiles encore en vol finissent tout droit
        camera.set_shader_input('ir_on', 0.0)
        for e in g.enemies + g.corpses:
            set_hot(e, 0.0)
        g.apply_time_of_day(g.night)          # rétablit le brouillard
        camera.parent = p.pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = 90
        p.drone = None
        p.position = Vec3(g.world.spawn)
        p.rotation_y = 0
        p.pivot.rotation_x = 0
        p.vel, p.vy = Vec3(0, 0, 0), 0
        p.hp = 100
        p.armed = False
        g.set_nv(self.saved_nv)
        if shot_down:
            g.hud.message('Drone abattu !', 3, 'Vous reprenez le combat au sol')
        else:
            g.hud.message('Retour au sol', 3, 'Le drone rentre à la base — vous réapparaissez au point de départ')
        destroy(self)


# ---------------------------------------------------------------------------
# Mode « Défense du village » : chars, blindés anti-aériens, missiles sol-air
# ---------------------------------------------------------------------------

MAX_BREACHES = 3              # percées tolérées avant la chute du village
LANES = (-21.5, 21.5)         # axes de progression des blindés (x), dégagés dans le village
# dégâts contre les blindés : (char, camion anti-aérien) au point d'impact
VDMG_ROCKET = (340, 450)
VDMG_MISSILE = (520, 600)
VDMG_DRONE_SHELL = (45, 140)
VDMG_AA_SHELL = (18, 60)
VDMG_GRENADE = (60, 160)


def damage_vehicles(game, center, radius, vdmg):
    """Explosion : les blindés proches encaissent (plus au contact, moins au bord du rayon)."""
    for v in list(game.vehicles):
        if not v.alive:
            continue
        d = v.box_dist(center)
        if d < radius:
            v.take_hit(int((vdmg[0] if v.kind == 'tank' else vdmg[1]) * (1 - 0.7 * d / radius)))


def air_burst(pos, size=1.0):
    """Explosion en l'air (missile sol-air, obus de DCA) : boule de feu et fumée, sans trace au sol."""
    f = FXM.get('sphere')
    f.color = rgb(255, 200, 90)
    f.position = pos
    f.scale = 0.4 * size
    FXM.play(f, 0.25, scale=Vec3(3, 3, 3) * size, col=rgb(255, 120, 30, 0))
    for _ in range(4):
        sm = FXM.get('sphere')
        sm.color = rgb(70, 68, 66, 200)
        sm.position = pos + Vec3(random.uniform(-.5, .5), random.uniform(-.5, .5), random.uniform(-.5, .5)) * size
        sm.scale = 0.8 * size
        FXM.play(sm, 1.6, scale=Vec3(2.5, 2.5, 2.5) * size, col=rgb(110, 108, 105, 0))


class TankShell(Entity):
    """Obus explosif tiré par un char : vole très vite, explose au premier contact."""

    def __init__(self, game, start, target, shooter):
        super().__init__(model='sphere', color=rgb(255, 220, 150), scale=0.2, position=start, unlit=True)
        self.game = game
        self.shooter = shooter
        self.dir = (target - start).normalized()
        self.life = 2.0

    def update(self):
        if self.game.paused:
            return
        dt = time.dt
        self.life -= dt
        step = 140 * dt
        hit = raycast(self.world_position, self.dir, step + 0.2, ignore=[self, self.shooter])
        end = hit.world_point if hit.hit else self.position + self.dir * step
        if (self.position - camera.world_position).length() > 6:     # pas de traînée collée à la caméra
            tracer(self.position, end, rgb(255, 200, 120), thickness=0.03, life=0.04)
        if hit.hit or self.life <= 0 or end.y < 0:
            self.explode(Vec3(end))
            return
        self.position = end

    def explode(self, pos):
        g = self.game
        destroy(self)
        explosion_fx(pos, 1.0)
        pl = g.player
        d = (pl.position + Vec3(0, 0.9, 0) - pos).length()
        if not pl.dead and d < 4.5 and (g.world.los(pos + Vec3(0, 0.3, 0), pl.eye)
                                          or g.world.los(pos + Vec3(0, 0.3, 0), pl.position + Vec3(0, 0.5, 0))):
            pl.take_damage(int(lerp(85, 20, clamp(d / 4.5, 0, 1))), pos)
        if d < 20 and pl.drone is None:
            pl.shake = max(pl.shake, 0.6 * (1 - d / 20))
            PAD.rumble(0.9 * (1 - d / 20), 0.7 * (1 - d / 20), 300)


class SAMissile(Entity):
    """Missile sol-air (MANPADS) : poursuit le drone ; les leurres thermiques peuvent le dévier."""

    def __init__(self, game, start):
        super().__init__(model='cube', color=rgb(95, 100, 85), scale=(0.1, 0.1, 0.6), position=start, shader=LIT)
        self.game = game
        d = game.player.drone
        self.dir = ((d.position - start).normalized() + Vec3(0, 0.6, 0)).normalized()
        self.speed = 30.0
        self.life = 9.0
        self.decoy = None
        self.smoke_t = 0.0
        Entity(parent=self, model='quad', texture='circle', color=rgb(255, 230, 170), z=-0.5, scale=(2, 2),
               billboard=True, unlit=True)
        game.sams.append(self)

    def update(self):
        g = self.game
        if g.paused:
            return
        dt = time.dt
        d = g.player.drone
        self.life -= dt
        if d is None:
            self.explode()
            return
        self.speed = min(95.0, self.speed + 45 * dt)
        target = self.decoy if self.decoy is not None else d.position
        want = target - self.position
        dist = want.length()
        if self.decoy is not None:
            self.decoy_t = getattr(self, 'decoy_t', 0.0) + dt
            if dist < 6.0 or self.decoy_t > 2.0:      # leurré : il explose sur les leurres
                self.explode()
                return
        if dist < 3.0:
            self.explode()
            if self.decoy is None:
                d.take_damage(34, 'Missile sol-air !')
            return
        k = min(1.0, dt * 2.8)
        self.dir = (self.dir * (1 - k) + want / max(dist, 1e-4) * k).normalized()
        self.position += self.dir * self.speed * dt
        self.look_at(self.position + self.dir)
        self.smoke_t -= dt
        if self.smoke_t <= 0:
            self.smoke_t = 0.04
            sm = FXM.get('sphere')
            sm.color = rgb(230, 230, 225, 150)
            sm.position = self.position - self.dir * 0.4
            sm.scale = 0.3
            FXM.play(sm, 1.5, scale=Vec3(1.4, 1.4, 1.4), col=rgb(190, 190, 185, 0))
        if self.life <= 0:
            self.explode()

    def explode(self):
        g = self.game
        if self in g.sams:
            g.sams.remove(self)
        air_burst(Vec3(self.position), 0.8)
        destroy(self)


class Vehicle(Entity):
    """Blindé ennemi qui descend un axe du village vers la ligne à tenir.
    kind 'tank' : char (canon de 125 mm + mitrailleuse), très résistant aux balles.
    kind 'aa'   : camion anti-aérien bitube : tire sur le drone, sinon sur le joueur."""
    HALF = {'tank': (1.9, 3.6), 'aa': (1.3, 3.3)}
    HEIGHT = {'tank': 2.6, 'aa': 2.8}

    def __init__(self, game, kind, lane_x, z, skill=0.0):
        super().__init__(position=(lane_x, 0, z), rotation_y=180)
        self.game = game
        self.kind = kind
        self.lane = lane_x
        self.skill = skill
        self.max_hp = 900 if kind == 'tank' else 420
        self.hp = self.max_hp
        self.alive = True
        self.gone = False
        self.speed = 2.0 if kind == 'tank' else 2.4        # ~1 min 30 pour descendre jusqu'à la ligne
        self.fire_t = random.uniform(3, 6)
        self.mg_t = random.uniform(1, 3)
        self.burn_t = 0.0
        self.smoke_t = 0.0
        self.owner = self
        self.zone = 'hull'
        hw, hl = self.HALF[kind]
        self.collider = BoxCollider(self, center=Vec3(0, self.HEIGHT[kind] / 2, 0),
                                    size=Vec3(hw * 2, self.HEIGHT[kind], hl * 2))
        (self.build_tank if kind == 'tank' else self.build_aa)()
        game.vehicles.append(self)
        if game.player.drone is not None and game.player.drone.thermal:
            set_hot(self, 0.8)

    # -- modèles -------------------------------------------------------------
    def build_tank(self):
        paint, dark, track = rgb(88, 96, 66), rgb(58, 63, 46), rgb(36, 36, 34)
        b = MeshBuilder()
        b.box((0, 0.85, 0), (3.2, 0.8, 6.4), paint, jitter=0.03)                  # caisse
        b.box((0, 0.95, 3.35), (3.0, 0.6, 0.8), paint, rx=-35)                    # glacis
        b.box((0, 1.28, -0.2), (3.6, 0.1, 6.2), dark)                              # garde-boue
        b.box((0, 1.0, -3.3), (2.6, 0.5, 0.3), dark)                               # arrière / échappement
        for s in (-1, 1):
            b.box((s * 1.85, 0.5, 0), (0.62, 1.0, 6.9), track)                    # chenilles
            for k in range(6):
                b.cylinder((s * 2.17 - 0.08, 0.45, -2.6 + k * 1.05), 0.38, 0.16, rgb(55, 56, 50), seg=8, axis='x')
            b.box((s * 1.95, 1.05, 0.2), (0.08, 0.42, 5.8), paint)                # jupes
            for k in range(4):
                b.box((s * 0.9, 1.4, 2.2 - k * 0.5), (0.9, 0.12, 0.4), rgb(80, 86, 60))   # briques réactives
        b.build(self)
        self.turret = Entity(parent=self, y=1.33, z=-0.3)
        t = MeshBuilder()
        t.box((0, 0.35, 0), (2.4, 0.7, 2.8), paint, jitter=0.03)
        t.box((0, 0.73, -0.3), (1.7, 0.1, 1.9), dark)
        t.cylinder((0.6, 0.75, -0.4), 0.3, 0.25, dark, seg=8)                      # tourelleau
        t.box((0, 0.35, 1.55), (1.0, 0.55, 0.4), dark)                             # masque
        t.cylinder((0, 0.38, 1.7), 0.09, 4.1, dark, seg=8, axis='z')               # canon
        t.cylinder((0, 0.38, 3.3), 0.13, 0.6, dark, seg=8, axis='z')               # évacuateur de fumée
        t.cylinder((0.6, 1.0, -0.4), 0.03, 0.8, rgb(30, 30, 30), seg=5, axis='z')  # mitrailleuse de tourelle
        t.build(self.turret)
        self.muzzle = Entity(parent=self.turret, position=(0, 0.38, 5.9))
        self.mg = Entity(parent=self.turret, position=(0.6, 1.0, 0.5))

    def build_aa(self):
        paint, dark, tyre = rgb(150, 138, 100), rgb(70, 72, 60), rgb(30, 30, 30)
        b = MeshBuilder()
        b.box((0, 0.95, 0), (2.4, 0.5, 6.4), dark)                                 # châssis
        b.box((0, 1.75, 2.35), (2.4, 1.3, 1.7), paint, jitter=0.03)                # cabine
        b.box((0, 1.95, 3.21), (2.0, 0.5, 0.05), rgb(40, 55, 70))                  # pare-brise
        b.box((0, 1.4, -1.0), (2.4, 0.5, 4.0), paint)                              # plateau
        for s in (-1, 1):
            for wz in (-2.3, -0.9, 0.9, 2.4):
                b.cylinder((s * 1.3 - (0.3 if s > 0 else 0), 0.5, wz), 0.5, 0.3, tyre, seg=10, axis='x')
        b.build(self)
        self.turret = Entity(parent=self, y=1.65, z=-1.2)
        t = MeshBuilder()
        t.box((0, 0.45, 0), (1.9, 0.9, 1.9), paint, jitter=0.03)
        t.box((0, 1.1, -0.6), (0.12, 0.8, 0.12), dark)                             # mât radar
        t.box((0, 1.55, -0.6), (1.3, 0.55, 0.08), dark)                            # antenne radar
        for sx in (-1, 1):
            t.box((sx * 0.7, 0.9, 1.0), (0.14, 0.14, 2.4), dark, rx=-35)          # tubes pointés vers le ciel
            t.box((sx * 0.7, 0.62, 0.3), (0.35, 0.4, 0.8), paint)                 # boîtes de culasse
        t.build(self.turret)
        self.muzzles = [Entity(parent=self.turret, position=(sx * 0.7, 1.6, 2.0)) for sx in (-1, 1)]

    # -- géométrie -----------------------------------------------------------
    def box_dist(self, p):
        hw, hl = self.HALF[self.kind]
        dx = max(0.0, abs(p.x - self.x) - hw)
        dz = max(0.0, abs(p.z - self.z) - hl)
        dy = max(0.0, p.y - self.HEIGHT[self.kind])
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def push_out(self, pos, r):
        """Empêche le joueur de traverser le blindé (ou son épave)."""
        hw, hl = self.HALF[self.kind]
        x0, x1, z0, z1 = self.x - hw, self.x + hw, self.z - hl, self.z + hl
        px, pz = clamp(pos.x, x0, x1), clamp(pos.z, z0, z1)
        dx, dz = pos.x - px, pos.z - pz
        d2 = dx * dx + dz * dz
        if d2 >= r * r or pos.y > self.HEIGHT[self.kind] - 0.3:
            return pos
        if d2 > 1e-8:
            d = math.sqrt(d2)
            return Vec3(pos.x + dx / d * (r - d), pos.y, pos.z + dz / d * (r - d))
        opts = [(pos.x - x0 + r, -1, 0), (x1 - pos.x + r, 1, 0), (pos.z - z0 + r, 0, -1), (z1 - pos.z + r, 0, 1)]
        pen, sx, sz = min(opts)
        return Vec3(pos.x + sx * pen, pos.y, pos.z + sz * pen)

    # -- dégâts --------------------------------------------------------------
    def bullet_hit(self, dmg, point):
        """Balles : ricochent presque sans effet sur le char, entament le camion."""
        impact(point, None, rgb(255, 220, 140))
        self.take_hit(dmg * (0.03 if self.kind == 'tank' else 0.3))

    def take_hit(self, dmg):
        if not self.alive:
            return
        self.hp -= dmg
        if self.hp <= 0:
            self.destroyed()

    def destroyed(self):
        g = self.game
        self.alive = False
        explosion_fx(self.position + Vec3(0, 1.5, 0), 2.0)
        for part in list(self.children) + list(self.turret.children):
            if part.model is not None:
                part.color = rgb(70, 60, 50)          # calciné
        self.turret.rotation_y += random.uniform(-40, 40)
        self.turret.rotation_z = random.uniform(-8, 8)
        self.burn_t = 10.0
        set_hot(self, 0.6 if g.player.drone is not None and g.player.drone.thermal else 0.0)
        pts = 500 if self.kind == 'tank' else 350
        g.add_score(pts + g.wave * 20, ('Char détruit' if self.kind == 'tank' else 'Blindé anti-aérien détruit')
                    + f' +{pts + g.wave * 20}')
        g.hud.hitmarker(True)
        PAD.rumble(0.8, 0.8, 350)
        g.check_wave_end()

    # -- comportement --------------------------------------------------------
    def update(self):
        g = self.game
        if g.paused or self.gone:
            return
        dt = time.dt
        if not self.alive:                        # épave qui brûle puis disparaît
            self.burn_t -= dt
            self.smoke_t -= dt
            if self.smoke_t <= 0:
                self.smoke_t = 0.3
                sm = FXM.get('sphere')
                sm.color = rgb(35, 33, 31, 190)
                sm.position = self.position + Vec3(random.uniform(-.8, .8), 2.0, random.uniform(-.8, .8))
                sm.scale = 1.0
                FXM.play(sm, 3.0, pos=sm.position + Vec3(random.uniform(1, 3), 8, 0), scale=Vec3(3, 3, 3),
                         col=rgb(90, 88, 85, 0))
            if self.burn_t <= 0:
                self.y -= dt * 0.6                # l'épave « s'enfonce » : elle libère l'axe
                if self.y < -3:
                    self.remove()
            return
        # progression : on attend si un blindé nous précède de trop près
        blocked = any(o is not self and not o.gone and o.lane == self.lane and 0 < self.z - o.z < 9.5
                      for o in g.vehicles)
        if not blocked:
            self.z -= self.speed * dt
            self.y = abs(math.sin(g.t * 9)) * 0.02
        if self.z <= g.world.defense_z:
            g.breach(self)
            self.remove()
            return
        pl = g.player
        drone = pl.drone
        self.fire_t -= dt
        self.mg_t -= dt
        if self.kind == 'aa' and drone is not None:
            self.aim_turret(drone.position, dt, 60)
            if self.fire_t <= 0:
                self.fire_t = random.uniform(1.0, 1.6)
                self.burst_at(drone.position, 3.5, stop=12)
                dist = (drone.position - self.position).length()
                if random.random() < 0.35 * clamp(1.4 - dist / 110, 0.2, 1):
                    drone.take_damage(5, 'Tirs de DCA !')
            return
        if pl.dead or drone is not None:
            return
        eye = self.position + Vec3(0, 2.3, 0)
        dist = flat_dist(self.position, pl.position)
        if dist > 85 or not g.world.los(eye, pl.eye):
            self.aim_turret(self.position + Vec3(0, 0, -10), dt, 20)
            return
        aligned = self.aim_turret(pl.position, dt, 32 + 20 * self.skill)
        if self.kind == 'tank':
            if aligned and self.fire_t <= 0:
                self.fire_t = random.uniform(6.5, 8.5) - 2.5 * self.skill
                err = lerp(3.2, 1.2, self.skill) * clamp(dist / 35, 0.4, 1.5)
                target = pl.position + Vec3(random.uniform(-err, err), random.uniform(0.2, 1.4), random.uniform(-err, err))
                start = self.muzzle.world_position
                muzzle_flash(self.muzzle, scale=1.6, intensity=0.8, life=0.08)
                TankShell(g, start, target, self)
                g.hud.add_feed('Le char fait feu !')
            if self.mg_t <= 0:
                self.mg_t = random.uniform(2.5, 4)
                self.mg_burst(pl, dist)
        elif self.fire_t <= 0 and aligned and dist < 60:
            self.fire_t = random.uniform(1.8, 2.6)
            self.burst_at(pl.eye - Vec3(0, 0.4, 0), 1.5)
            if random.random() < 0.3 * clamp(1.3 - dist / 60, 0.3, 1):
                pl.take_damage(9, self.position)
            else:
                g.flyby(pl.position)

    def aim_turret(self, target, dt, rate):
        want = angle_diff(self.rotation_y, yaw_to(self.position, target))
        self.turret.rotation_y = approach_angle(self.turret.rotation_y, want, rate * dt)
        return abs(angle_diff(self.turret.rotation_y, want)) < 5

    def burst_at(self, target, scatter, stop=0.0):
        """Rafale de traçantes ; stop : elles s'arrêtent avant la cible (tirs vers le drone = la caméra)."""
        for m in self.muzzles:
            muzzle_flash(m, scale=0.5, intensity=0.6, life=0.04)
            start = m.world_position
            for _ in range(2):
                end = target + Vec3(random.uniform(-scatter, scatter), random.uniform(-scatter, scatter),
                                    random.uniform(-scatter, scatter))
                if stop:
                    d = end - start
                    end = start + d * max(0.1, 1 - stop / max(d.length(), 1e-3))
                tracer(start, end, rgb(255, 170, 80), thickness=0.04, life=0.07)

    def mg_burst(self, pl, dist):
        start = self.mg.world_position
        for _ in range(3):
            end = pl.eye + Vec3(random.uniform(-1.5, 1.5), random.uniform(-1, 0.5), random.uniform(-1.5, 1.5))
            tracer(start, end, rgb(255, 200, 80), thickness=0.02)
        if random.random() < 0.3 * clamp(1.2 - dist / 70, 0.2, 1) and \
                (pl.crouch_t < 0.5 or random.random() < 0.4):
            pl.take_damage(6, self.position)
        else:
            self.game.flyby(pl.position)

    def remove(self):
        if self.gone:
            return
        self.gone = True
        self.alive = False
        g = self.game
        if self in g.vehicles:
            g.vehicles.remove(self)
        destroy(self)
        g.check_wave_end()


def render_root():
    return application.base.render


def set_hot(e, value):
    """Température d'un corps pour la caméra thermique (ignore les entités déjà détruites)."""
    if not e.isEmpty():
        e.set_shader_input('hot', value)


# ---------------------------------------------------------------------------
# Manette (PS5 DualSense, et la plupart des manettes)
# ---------------------------------------------------------------------------

PAD_DEADZONE = 0.15           # zone morte des sticks (rayon, 0..1) : augmenter si le personnage dérive
PAD_TRIGGER_DEADZONE = 0.05   # gâchettes L2 / R2 : ignore les pressions infimes

PAD_BUTTONS = ('cross', 'circle', 'square', 'triangle', 'share', 'ps', 'options',
               'l3', 'r3', 'l1', 'r1', 'up', 'down', 'left', 'right')


class Gamepad:
    """Lecture de la manette avec pygame, et uniquement pour ça : pygame n'ouvre aucune fenêtre
    et ne dessine rien, Ursina reste le moteur du jeu. Installation : pip install pygame

    Valeurs lues à chaque image : lx, ly (stick gauche, ly > 0 = vers l'avant), rx, ry (stick droit,
    ry > 0 = vers le haut), l2, r2 (gâchettes 0..1), down[nom] (bouton maintenu),
    pressed[nom] (appui de cette image). Zone morte circulaire appliquée à chaque stick.
    """

    def __init__(self):
        self.dev = None
        self.name = ''
        self.lx = self.ly = self.rx = self.ry = self.l2 = self.r2 = 0.0
        self.down = {b: False for b in PAD_BUTTONS}
        self.pressed = {b: False for b in PAD_BUTTONS}
        self.last_used = -99.0
        self._scan_t = 0.0
        self._pg = None
        self._sdlc = None
        self.available = self._init_pygame()

    # -- initialisation --------------------------------------------------------
    def _init_pygame(self):
        import os
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        os.environ.setdefault('SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS', '1')   # la fenêtre active est celle d'Ursina
        os.environ.setdefault('SDL_JOYSTICK_HIDAPI_PS5', '1')                # pilote DualSense de SDL
        os.environ.setdefault('SDL_JOYSTICK_HIDAPI_PS5_RUMBLE', '1')          # vibrations en Bluetooth aussi
        try:
            import pygame
            pygame.display.init()      # requis par SDL pour recevoir les événements manette ; aucune fenêtre créée
            pygame.joystick.init()
        except Exception as ex:
            print('Manette désactivée : pygame est introuvable (pip install pygame).', ex)
            return False
        self._pg = pygame
        try:
            from pygame._sdl2 import controller as sdlc    # boutons normalisés (croix, carré...)
            sdlc.init()
            self._sdlc = sdlc
        except Exception:
            self._sdlc = None                              # repli : lecture brute du joystick
        return True

    def _connect(self):
        """Cherche une manette (au démarrage puis toutes les 2 s tant qu'aucune n'est branchée)."""
        self.dev = None
        pg = self._pg
        pg.event.pump()
        for i in range(pg.joystick.get_count()):
            try:
                if self._sdlc is not None and self._sdlc.is_controller(i):
                    self.dev = ('controller', self._sdlc.Controller(i))
                    self.name = self.dev[1].name
                else:
                    j = pg.joystick.Joystick(i)
                    j.init()
                    self.dev = ('joystick', j)
                    self.name = j.get_name()
                return
            except Exception:
                continue

    @property
    def connected(self):
        if self.dev is None:
            return False
        kind, d = self.dev
        try:
            return d.attached() if kind == 'controller' else d.get_init()
        except Exception:
            return False

    # -- lecture ---------------------------------------------------------------
    @staticmethod
    def deadzone(x, y, dz=None):
        """Zone morte circulaire : en dessous de dz (rayon), le stick est considéré au repos ;
        au-delà, la course restante est ramenée sur 0..1 (pas de saut de vitesse au bord)."""
        dz = PAD_DEADZONE if dz is None else dz
        m = math.hypot(x, y)
        if m <= dz:
            return 0.0, 0.0
        k = min(1.0, (m - dz) / (1 - dz)) / m
        return x * k, y * k

    def _read(self):
        """Renvoie (lx, ly_haut, rx, ry_haut, l2, r2, {bouton: bool})."""
        kind, d = self.dev
        if kind == 'controller':
            pg = self._pg
            ax = lambda a: d.get_axis(a) / 32767.0
            b = lambda k: bool(d.get_button(k))
            btn = {
                'cross': b(pg.CONTROLLER_BUTTON_A), 'circle': b(pg.CONTROLLER_BUTTON_B),
                'square': b(pg.CONTROLLER_BUTTON_X), 'triangle': b(pg.CONTROLLER_BUTTON_Y),
                'share': b(pg.CONTROLLER_BUTTON_BACK), 'ps': b(pg.CONTROLLER_BUTTON_GUIDE),
                'options': b(pg.CONTROLLER_BUTTON_START),
                'l3': b(pg.CONTROLLER_BUTTON_LEFTSTICK), 'r3': b(pg.CONTROLLER_BUTTON_RIGHTSTICK),
                'l1': b(pg.CONTROLLER_BUTTON_LEFTSHOULDER), 'r1': b(pg.CONTROLLER_BUTTON_RIGHTSHOULDER),
                'up': b(pg.CONTROLLER_BUTTON_DPAD_UP), 'down': b(pg.CONTROLLER_BUTTON_DPAD_DOWN),
                'left': b(pg.CONTROLLER_BUTTON_DPAD_LEFT), 'right': b(pg.CONTROLLER_BUTTON_DPAD_RIGHT),
            }
            return (ax(pg.CONTROLLER_AXIS_LEFTX), -ax(pg.CONTROLLER_AXIS_LEFTY),
                    ax(pg.CONTROLLER_AXIS_RIGHTX), -ax(pg.CONTROLLER_AXIS_RIGHTY),
                    max(0.0, ax(pg.CONTROLLER_AXIS_TRIGGERLEFT)), max(0.0, ax(pg.CONTROLLER_AXIS_TRIGGERRIGHT)), btn)
        # repli joystick brut, disposition SDL de la DualSense : 0 croix, 1 rond, 2 carré, 3 triangle...
        na, nb = d.get_numaxes(), d.get_numbuttons()
        ax = lambda i: d.get_axis(i) if i < na else 0.0
        b = lambda i: bool(d.get_button(i)) if i < nb else False
        hat = d.get_hat(0) if d.get_numhats() else (0, 0)
        btn = {'cross': b(0), 'circle': b(1), 'square': b(2), 'triangle': b(3), 'share': b(4),
               'ps': b(5), 'options': b(6), 'l3': b(7), 'r3': b(8), 'l1': b(9), 'r1': b(10),
               'up': b(11) or hat[1] > 0, 'down': b(12) or hat[1] < 0,
               'left': b(13) or hat[0] < 0, 'right': b(14) or hat[0] > 0}
        trig = lambda i: (ax(i) + 1) / 2 if i < na else 0.0     # gâchettes de -1 (relâchée) à 1
        return ax(0), -ax(1), ax(2), -ax(3), trig(4), trig(5), btn

    def _reset(self):
        self.lx = self.ly = self.rx = self.ry = self.l2 = self.r2 = 0.0
        for k in PAD_BUTTONS:
            self.down[k] = self.pressed[k] = False

    def update(self, now):
        if not self.available:
            return
        try:
            for _ in self._pg.event.get():       # vide la file d'événements SDL
                pass
        except Exception:
            pass
        if not self.connected:
            self._scan_t -= time.dt
            if self._scan_t <= 0:
                self._scan_t = 2.0
                self._connect()
            if not self.connected:
                self._reset()
                return
        try:
            lx, ly, rx, ry, l2, r2, btn = self._read()
        except Exception:
            self.dev = None
            self._reset()
            return
        self.lx, self.ly = self.deadzone(lx, ly)
        self.rx, self.ry = self.deadzone(rx, ry)
        self.l2 = l2 if l2 > PAD_TRIGGER_DEADZONE else 0.0
        self.r2 = r2 if r2 > PAD_TRIGGER_DEADZONE else 0.0
        for k in PAD_BUTTONS:
            v = btn.get(k, False)
            self.pressed[k] = v and not self.down[k]
            self.down[k] = v
        if (abs(self.lx) + abs(self.ly) + abs(self.rx) + abs(self.ry) + self.l2 + self.r2 > 0) \
                or any(self.down.values()):
            self.last_used = now

    def rumble(self, low, high, ms):
        """Vibrations (manettes reconnues par SDL comme « game controller », dont la DualSense)."""
        if self.dev is None or self.dev[0] != 'controller':
            return
        try:
            self.dev[1].rumble(clamp(low, 0, 1), clamp(high, 0, 1), int(ms))
        except Exception:
            pass


PAD = None       # instance unique, créée par Game


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

CONTROLS_LINE = ('E/S/Q/D bouger · Z courir · C accroupi · Espace sauter · Clic G/P tirer · Clic D viser (+A/F pencher)'
                 ' · R recharger · V ramasser/utiliser · X grenade · U drone · Tab arme · T vue 3e pers. · N vision nuit'
                 ' · M carte · Échap pause')
CONTROLS_PAD_LINE = ('Manette : stick G bouger · L3 courir · Rond accroupi · R2 tirer · L2 viser (+L3/R3 pencher)'
                     ' · Croix sauter · Carré recharger/ramasser/utiliser · R1 grenade · flèche G drone · Triangle arme'
                     ' · flèche bas vue 3e pers. · flèche haut vision nuit · Options pause')
CONTROLS_PAUSE = ('E avancer   ·   S reculer   ·   Q gauche   ·   D droite   ·   flèches : se déplacer\n'
                  'Z courir   ·   C accroupi   ·   Espace sauter   ·   Clic gauche ou P tirer   ·   Clic droit viser\n'
                  'En visant : A / F se pencher   ·   R recharger   ·   V ramasser une arme / utiliser la batterie AA\n'
                  'X grenade   ·   U drone Reaper (après 3 tirs à la tête)   ·   Tab changer d\'arme\n'
                  'T vue 3e personne   ·   N vision nocturne (la nuit)   ·   M carte   ·   G graphismes\n'
                  'Manette PS5 : stick gauche bouger (L3 courir) · stick droit regarder · R2 tirer · L2 viser\n'
                  'Rond accroupi · en visant L3 / R3 se pencher · Croix sauter · Carré recharger / ramasser / utiliser\n'
                  'R1 grenade · flèche gauche : drone · drone : stick G piloter, stick D viser, R2 canon, R1 missile,\n'
                  'L1 leurres, L2 zoom, Triangle vision\n'
                  'Triangle changer d\'arme · flèche bas : vue 3e personne · flèche haut : vision nocturne\n\n'
                  'Échap / Options : reprendre    ·    X / Create : quitter')

class MiniMap:
    """Carte de l'arène (en haut à gauche) : seulement la position des ennemis (points rouges)
    et la vôtre (flèche bleue), nord en haut."""
    SIZE = 0.3

    def __init__(self, game, parent, position):
        self.game = game
        self.root = Entity(parent=parent, position=position, scale=self.SIZE)
        Entity(parent=self.root, model=Quad(radius=0.04), color=color.rgba(0, 0, 0, 0.55), scale=1.06, z=0.02)
        Entity(parent=self.root, model=Quad(radius=0.03, mode='line', thickness=2), color=color.rgba(1, 1, 1, 0.35),
               scale=1.0, z=0.01)
        arrow = Mesh(vertices=[Vec3(0, 0.6, 0), Vec3(-0.4, -0.45, 0), Vec3(0.4, -0.45, 0)],
                     triangles=[0, 1, 2], mode='triangle')
        self.player_icon = Entity(parent=self.root, model=arrow, color=rgb(90, 220, 255), scale=0.045,
                                  double_sided=True, z=-0.02)
        self.dots = []
        self.vdots = []             # blindés : rectangles orange
        self.line = Entity(parent=self.root, model='quad', color=rgb(255, 80, 70), scale=(1.0, 0.006), z=-0.005,
                           enabled=False)   # ligne à tenir

    def update(self):
        if not self.root.enabled:
            return
        k = 1 / (2 * max(self.game.world.hx, self.game.world.hz))
        p = self.game.player
        self.player_icon.position = (p.x * k, p.z * k, -0.02)
        self.player_icon.rotation_z = p.rotation_y
        alive = [e for e in self.game.enemies if not e.dead]
        while len(self.dots) < len(alive):
            self.dots.append(Entity(parent=self.root, model='circle', color=rgb(255, 60, 50), scale=0.03, z=-0.01))
        for d, e in zip(self.dots, alive):
            d.enabled = True
            d.position = (e.x * k, e.z * k, -0.01)
        for d in self.dots[len(alive):]:
            d.enabled = False
        vs = [v for v in self.game.vehicles if v.alive]
        while len(self.vdots) < len(vs):
            self.vdots.append(Entity(parent=self.root, model='quad', color=rgb(255, 150, 40), scale=0.05, z=-0.012))
        for d, v in zip(self.vdots, vs):
            d.enabled = True
            d.position = (v.x * k, v.z * k, -0.012)
            d.scale = (0.05, 0.07) if v.kind == 'tank' else (0.04, 0.06)
        for d in self.vdots[len(vs):]:
            d.enabled = False
        self.line.enabled = self.game.mode == 'defense'
        self.line.y = self.game.world.defense_z * k
        self.line.scale_x = self.game.world.hx * 2 * k


class HUD:
    def __init__(self, game):
        self.game = game
        ui = camera.ui
        ar = camera.aspect_ratio / 2
        panel = color.rgba(0, 0, 0, 0.42)
        self.cross = []
        for pos, sc in [((0.014, 0), (0.012, 0.0025)), ((-0.014, 0), (0.012, 0.0025)),
                        ((0, 0.014), (0.0025, 0.012)), ((0, -0.014), (0.0025, 0.012))]:
            self.cross.append(Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, 0.9), position=pos, scale=sc))
        self.cross.append(Entity(parent=ui, model='quad', texture='circle', color=color.rgba(1, 1, 1, 0.9), scale=0.004))
        self.hits = []
        for ang in (45, 135, 225, 315):
            r = math.radians(ang)
            self.hits.append(Entity(parent=ui, model='quad', color=color.clear, rotation_z=-ang,
                                    position=(math.cos(r) * 0.022, math.sin(r) * 0.022), scale=(0.016, 0.003)))

        # panneaux
        Entity(parent=ui, model=Quad(radius=0.2), color=panel, origin=(-0.5, -0.5),
               position=(-ar + 0.02, -0.49), scale=(0.46, 0.11))
        Entity(parent=ui, model=Quad(radius=0.2), color=panel, origin=(0.5, -0.5),
               position=(ar - 0.02, -0.49), scale=(0.3, 0.11))
        Entity(parent=ui, model=Quad(radius=0.2), color=panel, origin=(-0.5, 0.5),
               position=(-ar + 0.02, 0.49), scale=(1.15, 0.055))
        Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, 0.15), origin=(-0.5, 0),
               position=(-ar + 0.05, -0.455), scale=(0.4, 0.022))
        self.hp_bar = Entity(parent=ui, model='quad', color=rgb(80, 220, 90), origin=(-0.5, 0),
                             position=(-ar + 0.05, -0.455, -0.01), scale=(0.4, 0.022))
        self.hp_text = Text(parent=ui, text='', position=(-ar + 0.05, -0.415), scale=1)
        self.ammo = Text(parent=ui, text='', origin=(0.5, 0), position=(ar - 0.05, -0.445), scale=1.8)
        self.ammo_lbl = Text(parent=ui, text='MUNITIONS', origin=(0.5, 0), position=(ar - 0.05, -0.4), scale=0.75,
                             color=color.rgba(1, 1, 1, 0.6))
        # grenades et progression de l'ultime (drone), au-dessus du panneau des munitions
        self.gear = Text(parent=ui, text='', origin=(0.5, 0), position=(ar - 0.05, -0.36), scale=0.95,
                         color=rgb(235, 225, 190))
        # lunette du sniper : cache noir avec un trou rond et un réticule
        self.scope = Entity(parent=ui, z=0.8, enabled=False)
        Entity(parent=self.scope, model='quad', texture=self.scope_texture(), scale=1)
        side = ar - 0.5 + 0.05
        for sgn in (-1, 1):
            Entity(parent=self.scope, model='quad', color=color.black, scale=(side, 1.02), x=sgn * (0.5 + side / 2 - 0.001))
        # lunette du RPG : réticule PGO-7 (chevrons de distance) + télémètre
        self.scope_rpg = Entity(parent=ui, z=0.8, enabled=False)
        Entity(parent=self.scope_rpg, model='quad', texture=self.rpg_scope_texture(), scale=1)
        for sgn in (-1, 1):
            Entity(parent=self.scope_rpg, model='quad', color=color.black, scale=(side, 1.02),
                   x=sgn * (0.5 + side / 2 - 0.001))
        self.range_txt = Text(parent=self.scope_rpg, text='', origin=(0, 0), y=-0.3, scale=1.2, z=-0.01,
                              color=rgb(255, 150, 60))
        self.info = Text(parent=ui, text='', position=(-ar + 0.04, 0.477), scale=1)
        self.msg = Text(parent=ui, text='', origin=(0, 0), y=0.17, scale=2, color=color.white)
        self.sub_msg = Text(parent=ui, text='', origin=(0, 0), y=0.1, scale=1.1, color=color.rgba(1, 1, 1, 0.85))
        self.warn = Text(parent=ui, text='', origin=(0, 0), y=-0.12, scale=1.4, color=rgb(255, 90, 60))
        self.prompt = Text(parent=ui, text='', origin=(0, 0), y=-0.22, scale=1.2, color=rgb(255, 225, 120))
        self.nv_label = Text(parent=ui, text='', origin=(0, 0), y=0.43, scale=1.0, color=rgb(120, 255, 140))
        self.feed = Text(parent=ui, text='', origin=(0.5, 0.5), position=(ar - 0.03, 0.4), scale=1)
        # compteur de FPS à droite de l'écran
        Entity(parent=ui, model=Quad(radius=0.25), color=panel, origin=(0.5, 0.5),
               position=(ar - 0.02, 0.49), scale=(0.14, 0.045))
        self.fps = Text(parent=ui, text='FPS --', origin=(0.5, 0), position=(ar - 0.035, 0.4675), scale=1.1,
                        color=rgb(120, 255, 120))
        self.damage = Entity(parent=ui, model='quad', texture='vignette', color=color.rgba(0.8, 0, 0, 0),
                             scale=(ar * 2, 1), z=1)
        self.dir_ind = Entity(parent=ui, model='quad', color=color.rgba(1, 0.1, 0.1, 0), scale=(0.05, 0.012))
        self.feed_lines = []
        self._fps_frames = 0
        self._fps_time = 0.0
        self.minimap = MiniMap(game, ui, (-ar + 0.02 + MiniMap.SIZE * 0.53, 0.415 - MiniMap.SIZE * 0.53))
        self.help = Text(parent=ui, text=CONTROLS_LINE,
                         origin=(0, 0), position=(0, -0.475), scale=0.7, color=color.rgba(1, 1, 1, 0.55))

    @staticmethod
    def scope_texture(size=1024):
        """Réticule de lunette dessiné une fois (noir autour, transparent dans le cercle)."""
        from PIL import Image, ImageDraw
        img = Image.new('RGBA', (size, size), (0, 0, 0, 255))
        d = ImageDraw.Draw(img)
        c, r = size // 2, int(size * 0.48)
        d.ellipse((c - r, c - r, c + r, c + r), fill=(0, 0, 0, 0))
        d.ellipse((c - r, c - r, c + r, c + r), outline=(0, 0, 0, 255), width=int(size * 0.012))
        t = 2                                                    # fil fin au centre
        d.rectangle((c - r, c - t // 2, c + r, c + t // 2), fill=(0, 0, 0, 255))
        d.rectangle((c - t // 2, c - r, c + t // 2, c + r), fill=(0, 0, 0, 255))
        g, T = int(size * 0.12), int(size * 0.012)               # montants épais vers le bord
        d.rectangle((c - r, c - T, c - g, c + T), fill=(0, 0, 0, 255))
        d.rectangle((c + g, c - T, c + r, c + T), fill=(0, 0, 0, 255))
        d.rectangle((c - T, c + g, c + T, c + r), fill=(0, 0, 0, 255))
        for k in range(1, 5):                                    # graduations
            o = int(size * 0.022 * k)
            for x, y in ((c + o, c), (c - o, c), (c, c + o)):
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(0, 0, 0, 255))
        d.ellipse((c - 3, c - 3, c + 3, c + 3), fill=(230, 30, 30, 255))   # point central rouge
        return Texture(img)

    @staticmethod
    def rpg_scope_texture(size=1024):
        """Réticule de la lunette PGO-7 du RPG : chevron de visée, chevrons de distance,
        échelle de correction latérale et télémètre, éclairés en orange."""
        from PIL import Image, ImageDraw
        img = Image.new('RGBA', (size, size), (0, 0, 0, 255))
        d = ImageDraw.Draw(img)
        c, r = size // 2, int(size * 0.48)
        d.ellipse((c - r, c - r, c + r, c + r), fill=(0, 0, 0, 0))
        d.ellipse((c - r, c - r, c + r, c + r), outline=(0, 0, 0, 255), width=int(size * 0.012))
        o = (15, 12, 10, 255)                 # traits noirs, comme la vraie lunette
        w = max(3, size // 220)

        def chevron(y, k):
            d.line((c - k, y + k, c, y, c + k, y + k), fill=o, width=w, joint='curve')
        chevron(c, int(size * 0.02))                          # point visé : pointe du chevron
        for i in range(1, 4):                                   # chevrons de distance (hausse)
            chevron(c + int(size * 0.06 * i), int(size * 0.014))
        tick = int(size * 0.035)                                # échelle latérale (correction du vent / mobile)
        for i in range(-5, 6):
            if i == 0:
                continue
            x = c + i * tick
            h = int(size * (0.018 if i % 2 == 0 else 0.01))
            d.line((x, c + int(size * 0.02) - h, x, c + int(size * 0.02)), fill=o, width=w)
        d.line((c - 5 * tick, c + int(size * 0.02), c - int(size * 0.035), c + int(size * 0.02)), fill=o, width=w)
        d.line((c + int(size * 0.035), c + int(size * 0.02), c + 5 * tick, c + int(size * 0.02)), fill=o, width=w)
        # télémètre (en bas à gauche) : on encadre un véhicule de 2,7 m de haut
        x0, y0 = c - int(size * 0.3), c + int(size * 0.28)
        pts = [(x0 + i * size * 0.035, y0 - size * 0.11 / (1 + i * 0.6)) for i in range(6)]
        d.line([(x0, y0)] + [(x0 + i * size * 0.035, y0) for i in range(1, 6)], fill=o, width=w)
        d.line(pts, fill=o, width=w)
        return Texture(img)

    def scope_visible(self, v, kind=True):
        sniper, rpg = v and kind != 'rpg', v and kind == 'rpg'
        if self.scope.enabled != sniper:
            self.scope.enabled = sniper
        if self.scope_rpg.enabled != rpg:
            self.scope_rpg.enabled = rpg

    def crosshair_visible(self, v):
        if getattr(self, '_cross_on', None) is v:
            return
        self._cross_on = v
        for c in self.cross:
            c.visible = v

    @staticmethod
    def set_text(t, value):
        """Ursina reconstruit le texte à chaque affectation : on ne le fait que s'il change."""
        if t.text != value:
            t.text = value

    def update(self):
        g = self.game
        p = g.player
        self.hp_bar.scale_x = 0.4 * max(0, p.hp) / 100
        self.hp_bar.color = rgb(80, 220, 90) if p.hp > 50 else (color.orange if p.hp > 25 else color.red)
        self.set_text(self.hp_text, f'SANTÉ  {int(p.hp)}')
        if p.drone is not None:
            self.set_text(self.ammo, f'{p.drone.missiles} / {ReaperDrone.MISSILES}')
            self.set_text(self.ammo_lbl, 'DRONE REAPER · MISSILES IR')
        elif p.mount is not None:
            aa = p.mount
            self.set_text(self.ammo, 'SURCHAUFFE' if aa.overheat else f'{int(aa.heat * 100)} %')
            self.set_text(self.ammo_lbl, 'BATTERIE AA · CHALEUR DES TUBES')
        else:
            self.set_text(self.ammo, '...' if p.reload_t > 0 else f"{p.mag} / {p.weapon['mag']}")
            self.set_text(self.ammo_lbl, f"MUNITIONS · {p.weapon['short']}")
        ult = ('ULTI PRÊTE : flèche G / U' if g.ult_ready else
               ('DRONE EN VOL' if p.drone is not None else f'Ulti {g.headshot_streak}/{ULT_HEADSHOTS} têtes'))
        self.set_text(self.gear, f'Grenades {p.nades} (X / R1)   ·   {ult}')
        self.gear.color = rgb(255, 210, 80) if g.ult_ready else rgb(235, 225, 190)
        alive = sum(1 for e in g.enemies if not e.dead)
        tier = TIERS[g.tier_index()]['name']
        if g.mode == 'defense':
            tanks = sum(1 for v in g.vehicles if v.alive and v.kind == 'tank')
            aas = sum(1 for v in g.vehicles if v.alive and v.kind == 'aa')
            self.set_text(self.info, f'DÉFENSE · Vague {g.wave}   ·   Chars {tanks}   ·   DCA {aas}   ·   Fantassins {alive}'
                          f'   ·   Percées {g.breaches}/{MAX_BREACHES}   ·   Score {g.score}')
        else:
            self.set_text(self.info, f'Vague {g.wave}   ·   {tier} (IA niv. {max(g.wave, 1)})   ·   Ennemis {alive}'
                          f'   ·   Score {g.score}   ·   Éliminations {g.kills}')

        # aide : commandes de la manette si elle a servi récemment
        self.set_text(self.help, CONTROLS_PAD_LINE if PAD is not None and g.t - PAD.last_used < 10 and PAD.connected
                      else CONTROLS_LINE)

        self.minimap.update()

        # images par seconde, moyenne sur une demi-seconde
        self._fps_frames += 1
        self._fps_time += time.dt
        if self._fps_time >= 0.5:
            fps = self._fps_frames / self._fps_time
            self.fps.text = f'FPS {fps:.0f}'
            self.fps.color = rgb(120, 255, 120) if fps >= 50 else (rgb(255, 200, 80) if fps >= 30 else rgb(255, 90, 80))
            self._fps_frames = 0
            self._fps_time = 0.0

        # alerte grenade
        near = [gr for gr in g.grenades if flat_dist(gr.position, p.position) < 9]
        if near and not p.dead:
            d = min(flat_dist(gr.position, p.position) for gr in near)
            self.set_text(self.warn, f'!  GRENADE  ({d:.0f} m)  !')
        else:
            self.set_text(self.warn, '')

        a = self.damage.color.a
        if a > 0:
            self.damage.color = color.rgba(0.8, 0, 0, max(0, a - time.dt * 0.8))
        da = self.dir_ind.color.a
        if da > 0:
            self.dir_ind.color = color.rgba(1, 0.1, 0.1, max(0, da - time.dt * 1.2))
        for h in self.hits:
            ha = h.color.a
            if ha > 0:
                h.color = color.rgba(h.color.r, h.color.g, h.color.b, max(0, ha - time.dt * 5))

    def flash_damage(self, from_pos):
        self.damage.color = color.rgba(0.8, 0, 0, min(0.7, self.damage.color.a + 0.3))
        p = self.game.player
        ang = angle_diff(p.rotation_y, yaw_to(p.position, from_pos))
        r = math.radians(ang)
        self.dir_ind.position = (math.sin(r) * 0.13, math.cos(r) * 0.13)
        self.dir_ind.rotation_z = ang
        self.dir_ind.color = color.rgba(1, 0.1, 0.1, 0.9)

    def hitmarker(self, strong):
        for h in self.hits:
            h.color = color.rgba(1, 0.2, 0.2, 1) if strong else color.rgba(1, 1, 1, 1)

    def add_feed(self, line):
        self.feed_lines.append(line)
        self.feed_lines = self.feed_lines[-5:]
        self.feed.text = '\n'.join(self.feed_lines)
        invoke(self.pop_feed, line, delay=4)

    def pop_feed(self, line):
        if line in self.feed_lines:
            self.feed_lines.remove(line)
            self.feed.text = '\n'.join(self.feed_lines)

    def message(self, text, duration=2.5, sub=''):
        self.msg.text = text
        self.sub_msg.text = sub
        if duration:
            invoke(self._clear_msg, text, delay=duration)

    def _clear_msg(self, text):
        if self.msg.text == text:
            self.msg.text = ''
            self.sub_msg.text = ''


# ---------------------------------------------------------------------------
# Jeu
# ---------------------------------------------------------------------------

class Game(Entity):
    def __init__(self):
        super().__init__(ignore_paused=True)
        self.t = 0
        self.paused = False
        self.over = False
        self.score = 0
        self.kills = 0
        self.wave = 0
        self.enemies = []
        self.squads = []
        self.corpses = []          # ennemis morts encore au sol (arme récupérable)
        self.pickup = None         # cadavre à portée pour Carré / V
        self.grenades = []
        self.last_grenade = -99
        self.high_quality = True
        self.choosing = True        # menu de choix d'arme affiché
        self.night = False          # choisi dans le menu de départ
        self.nv = False             # lunettes de vision nocturne (nuit seulement)
        self.map_name = 'village'   # carte choisie dans le menu : 'village' ou 'desert'
        self.mode = 'survie'        # 'survie' (vagues) ou 'defense' (défense du village)
        self.vehicles = []          # blindés ennemis (défense)
        self.sams = []              # missiles sol-air en vol
        self.breaches = 0           # percées de la ligne (défense)
        self.pending = 0            # blindés encore à faire entrer dans la vague
        self.wave_over = False
        self.headshot_streak = 0    # tirs à la tête comptés pour l'ultime (drone)
        self.ult_ready = False
        self.smoke_t = 0.0

        global FXM, PAD
        FXM = FX()
        PAD = Gamepad()
        self.menu_sel = 0
        self._pad_was = False
        self.sky = Sky(texture='sky_default', color=Color(0.95, 0.97, 1.0, 1))
        self.sun = DirectionalLight(shadow_map_resolution=Vec2(SHADOW_RES, SHADOW_RES), color=SUN_COLOR)
        self.apply_time_of_day(False)       # avant de créer le décor : les objets héritent de l'ambiance
        self.world = World(self.map_name, self.mode)
        self.sun.look_at(Vec3(0.55, -0.75, 0.4))
        self.shadow_bounds = Entity(model='cube', scale=(ARENA * 2 + 4, 9, ARENA * 2 + 4), y=4, visible=False)
        invoke(self.fit_shadows, delay=0.1)

        self.player = Player(self)
        self.hud = HUD(self)
        self.set_quality(True)
        self.show_weapon_menu()

    # -- menu de choix d'arme ------------------------------------------------
    def show_weapon_menu(self):
        mouse.locked = False
        ui = camera.ui
        self.menu = Entity(parent=ui, z=-0.5)
        Entity(parent=self.menu, model=Quad(radius=0.03), color=color.rgba(0, 0, 0, 0.72), scale=(1.1, 0.98), z=0.01,
               y=-0.07)
        Text(parent=self.menu, text='CHOISISSEZ VOTRE ARME', origin=(0, 0), y=0.33, scale=2)
        choices = [
            ('rifle', "1  —  Fusil d'assaut",
             'Tir automatique · 30 balles · viseur point rouge rond x1,4'),
            ('sniper', '2  —  Sniper',
             'Un tir par clic · gros dégâts · 5 balles · lunette zoom x2'),
        ]
        self.menu_buttons = []
        for k, (key, title, desc) in enumerate(choices):
            y = 0.18 - k * 0.18
            b = Button(parent=self.menu, text='', scale=(0.9, 0.15), y=y, radius=0.08,
                       color=color.rgba(0.2, 0.25, 0.3, 0.95), highlight_color=color.rgba(0.3, 0.45, 0.55, 1))
            b.on_click = (lambda k=key: self.choose_weapon(k))
            b.action = key
            self.menu_buttons.append(b)
            Text(parent=self.menu, text=title, origin=(0, 0), y=y + 0.025, scale=1.5, z=-0.02)
            Text(parent=self.menu, text=desc, origin=(0, 0), y=y - 0.035, scale=0.95, z=-0.02,
                 color=color.rgba(1, 1, 1, 0.75))
        # 3e et 4e lignes : jour / nuit et carte (bascules, ne lancent pas la partie)
        b = Button(parent=self.menu, text='', scale=(0.9, 0.09), y=-0.16, radius=0.08,
                   color=color.rgba(0.15, 0.18, 0.3, 0.95), highlight_color=color.rgba(0.25, 0.3, 0.5, 1))
        b.on_click = self.toggle_night_choice
        b.action = 'time'
        self.menu_buttons.append(b)
        self.menu_time_text = Text(parent=self.menu, text=self.time_label(), origin=(0, 0), y=-0.16, scale=1.2, z=-0.02)
        b = Button(parent=self.menu, text='', scale=(0.9, 0.09), y=-0.265, radius=0.08,
                   color=color.rgba(0.3, 0.24, 0.12, 0.95), highlight_color=color.rgba(0.45, 0.36, 0.2, 1))
        b.on_click = self.toggle_map_choice
        b.action = 'map'
        self.menu_buttons.append(b)
        self.menu_map_text = Text(parent=self.menu, text=self.map_label(), origin=(0, 0), y=-0.265, scale=1.2, z=-0.02)
        b = Button(parent=self.menu, text='', scale=(0.9, 0.09), y=-0.37, radius=0.08,
                   color=color.rgba(0.32, 0.14, 0.12, 0.95), highlight_color=color.rgba(0.48, 0.22, 0.18, 1))
        b.on_click = self.toggle_mode_choice
        b.action = 'mode'
        self.menu_buttons.append(b)
        self.menu_mode_text = Text(parent=self.menu, text=self.mode_label(), origin=(0, 0), y=-0.37, scale=1.2,
                                   z=-0.02)
        # cadre de sélection pour la manette
        self.menu_cursor = Entity(parent=self.menu, model=Quad(radius=0.08, thickness=3, mode='line'),
                                  color=rgb(255, 210, 90), scale=(0.93, 0.18), y=0.18, z=-0.03, visible=False)
        Text(parent=self.menu, text='Cliquez sur une arme ou appuyez sur 1 / 2  ·  3 ou N : jour / nuit  ·  4 : carte'
                                    '  ·  5 : mode\n'
                                    'Manette : croix directionnelle ou stick gauche, puis Croix pour valider',
             origin=(0, 0), y=-0.46, scale=0.85, color=color.rgba(1, 1, 1, 0.6))

    def choose_weapon(self, key):
        if not self.choosing:
            return
        self.choosing = False
        destroy(self.menu)
        self.player.reset_weapons(key)
        if self.mode == 'defense':               # défense : RPG en arme secondaire (Triangle / Tab)
            self.player.slots[1] = 'rpg'
        mouse.locked = True
        self.hud.message('Éliminez les ennemis !', 4,
                         f"Arme : {WEAPONS[key]['name']}" + (' · Nuit : les ennemis ont la vision nocturne'
                                                             if self.night else '')
                         + ('\nDésert : Carré / V près de la batterie anti-aérienne pour l\'utiliser'
                            if self.world.aa is not None else '')
                         + ('\nDÉFENSE : arrêtez chars, DCA et fantassins avant la ligne rouge et blanche au sud'
                            f' ({MAX_BREACHES} percées = défaite)\nRPG : Triangle / Tab · roquettes à la caisse verte'
                            if self.mode == 'defense' else ''))
        self.set_nv(self.night)             # la nuit, on commence lunettes allumées
        invoke(self.next_wave, delay=2)

    def apply_time_of_day(self, night):
        """Jour ou nuit : ambiance posée une fois sur toute la scène (tous les objets en héritent)."""
        self.night = night
        a = NIGHT if night else (DESERT_DAY if self.map_name == 'desert' or self.mode == 'defense' else DAY)
        scene.set_shader_input('sky_color', a['sky'])
        scene.set_shader_input('ground_color', a['ground'])
        scene.set_shader_input('fog_color', a['fog'])
        scene.set_shader_input('fog_density', a['fog_density'])
        scene.set_shader_input('sun_strength', a['sun_strength'])
        scene.set_shader_input('hot', 0.0)       # vue thermique du drone : les ennemis passent à 1
        self.sun.color = a['sun']
        self.sky.color = a['sky_tint']
        window.color = a['clear']
        if not night:
            self.set_nv(False)

    def set_nv(self, on):
        """Lunettes de vision nocturne (flèche haut / N), seulement la nuit."""
        self.nv = bool(on) and self.night
        camera.set_shader_input('nv_on', 1.0 if self.nv else 0.0)
        if hasattr(self, 'hud'):
            self.hud.set_text(self.hud.nv_label, 'VISION NOCTURNE' if self.nv else
                              ('Flèche haut / N : vision nocturne' if self.night and not self.choosing else ''))

    def toggle_nv(self):
        if not self.night:
            self.hud.add_feed('Vision nocturne : seulement la nuit')
            return
        self.set_nv(not self.nv)
        PAD.rumble(0.1, 0.2, 60)

    def toggle_night_choice(self):
        self.apply_time_of_day(not self.night)
        self.menu_time_text.text = self.time_label()

    def map_label(self):
        if self.mode == 'defense':
            return '4  —  Carte : DÉSERT DE DÉFENSE (200 m de long)'
        return '4  —  Carte : ' + ('DÉSERT (dunes, tranchées, char détruit, batterie AA)' if self.map_name == 'desert'
                                   else 'VILLAGE (murs, voitures, arbres)')

    def toggle_map_choice(self):
        """Change de carte dans le menu : le décor est reconstruit."""
        if self.mode == 'defense':          # la défense a sa propre carte : on revient à la survie
            self.mode = 'survie'
        else:
            self.map_name = 'desert' if self.map_name == 'village' else 'village'
        self.rebuild_world()

    def mode_label(self):
        return '5  —  Mode : ' + ('DÉFENSE (chars, DCA, MANPADS) — carte désert' if self.mode == 'defense'
                                  else 'SURVIE (vagues d\'infanterie)')

    def toggle_mode_choice(self):
        self.mode = 'defense' if self.mode == 'survie' else 'survie'
        self.rebuild_world()

    def rebuild_world(self):
        destroy(self.world.level)
        self.world = World(self.map_name, self.mode)
        self.player.world = self.world
        self.player.position = Vec3(self.world.spawn)
        self.fit_shadows()
        self.apply_time_of_day(self.night)
        self.update_grass(force=True)
        self.menu_map_text.text = self.map_label()
        self.menu_mode_text.text = self.mode_label()

    def time_label(self):
        return '3  —  Moment : ' + ('NUIT (vision nocturne)' if self.night else 'JOUR')

    def fit_shadows(self):
        """La carte d'ombres couvre uniquement l'arène (ombres plus nettes)."""
        w = self.world
        self.shadow_bounds.scale = (w.hx * 2 + 4, 9, w.hz * 2 + 4)
        self.shadow_bounds.visible = True
        self.sun.update_bounds(self.shadow_bounds)
        self.shadow_bounds.visible = False

    def set_quality(self, high):
        """G : effets de post-traitement et herbe. Le shader de caméra reste actif car il
        porte aussi la loupe du viseur du fusil (il ne coûte presque rien sans les effets)."""
        self.high_quality = high
        if camera.shader is None:
            try:
                camera.shader = POST
            except Exception as ex:      # carte graphique incompatible
                print('Post-traitement indisponible :', ex)
            camera.clip_plane_near = 0.05    # Ursina le remet à 1 quand on pose un shader de caméra
        camera.set_shader_input('fx_on', 1.0 if high else 0.0)
        self.update_grass(force=True)

    # -- vagues ------------------------------------------------------------
    def skill(self):
        return clamp((self.wave - 1) / 7, 0, 1)

    def tier_index(self):
        return min(3, max(0, (self.wave - 1) // 2))

    def spawn_points(self, n):
        pl = self.player.position
        pts = []
        tries = 0
        while len(pts) < n and tries < 600:
            tries += 1
            p = self.world.random_free_point()
            if flat_dist(p, pl) < 30 - min(tries / 60, 8):
                continue
            if any(flat_dist(p, q) < 3 for q in pts):
                continue
            if tries < 300 and self.world.los(p + Vec3(0, 1.6, 0), self.player.eye):
                continue      # on préfère des apparitions hors de vue
            pts.append(p)
        return pts

    def next_wave(self):
        if self.over:
            return
        self.wave_over = False
        if self.mode == 'defense':
            self.next_wave_defense()
            return
        self.wave += 1
        sk = self.skill()
        n = min(3 + self.wave, 14)
        tier = self.tier_index()
        # escouades de 2 à 4 soldats qui apparaissent groupés
        sizes = []
        left = n
        while left > 0:
            k = min(left, random.choice((3, 3, 4)) if left > 4 else left)
            sizes.append(k)
            left -= k
        self.squads = []
        rpg_index = random.randrange(n)          # un soldat par vague porte un RPG (à récupérer sur lui)
        count = 0
        for anchor, size in zip(self.spawn_points(len(sizes)), sizes):
            members = []
            yaw = random.uniform(0, 360)
            for i in range(size):
                pos = anchor
                for _ in range(30):
                    cand = anchor + Vec3(random.uniform(-3.5, 3.5), 0, random.uniform(-3.5, 3.5))
                    if i == 0 or (self.world.is_free(cand) and all(flat_dist(cand, m.position) > 1.2 for m in members)):
                        pos = cand if i else anchor
                        break
                e = Enemy(self, pos, skill=sk, tier=tier, weapon=random_enemy_weapon(),
                          rpg=(count == rpg_index), night=self.night)
                count += 1
                e.rotation_y = yaw
                members.append(e)
                self.enemies.append(e)
            self.squads.append(Squad(members))
        extra = ['', 'Ils se couvrent mutuellement', 'Ils lancent des grenades',
                 'Ils vous prennent en tenaille', 'Ils esquivent et visent plus vite']
        detail = extra[min(self.wave - 1, len(extra) - 1)]
        self.hud.message(f'Vague {self.wave}', 3,
                         f'{n} ennemis en {len(self.squads)} escouades · {TIERS[tier]["name"]} · IA niveau {self.wave}'
                         + (f' — {detail}' if detail else ''))

    # -- mode défense du village ---------------------------------------------
    def next_wave_defense(self):
        """Colonne ennemie : chars et DCA sur les deux axes, escouades à pied (une arme sol-air par escouade)."""
        self.wave += 1
        w = self.wave
        sk = self.skill()
        tier = self.tier_index()
        tanks = min(1 + w // 2, 4)
        aa = (1 if w >= 2 else 0) + (1 if w >= 4 else 0)
        kinds = ['tank'] * tanks + ['aa'] * aa
        random.shuffle(kinds)
        self.pending = len(kinds)
        for i, kind in enumerate(kinds):          # les blindés entrent l'un après l'autre
            invoke(self.spawn_vehicle, kind, LANES[i % 2], sk, delay=1 + (i // 2) * 9)
        n = min(4 + 2 * w, 14)
        sizes = []
        left = n
        while left > 0:
            k = min(left, 3 if left > 4 else left)
            sizes.append(k)
            left -= k
        self.squads = []
        rpg_index = random.randrange(n)
        count = 0
        for size in sizes:
            hx, hz = self.world.hx, self.world.hz
            anchor = self.world.free_point_near(Vec3(random.uniform(-hx + 6, hx - 6), 0, random.uniform(hz - 16, hz - 4)))
            members = []
            for i in range(size):
                pos = anchor
                for _ in range(30):
                    cand = anchor + Vec3(random.uniform(-3.5, 3.5), 0, random.uniform(-3, 3))
                    if i == 0 or (self.world.is_free(cand) and all(flat_dist(cand, m.position) > 1.2 for m in members)):
                        pos = cand if i else anchor
                        break
                e = Enemy(self, pos, skill=sk, tier=tier, weapon=random_enemy_weapon(), rpg=(count == rpg_index),
                          night=self.night, manpads=(i == size - 1 and count != rpg_index))
                count += 1
                e.rotation_y = 180
                members.append(e)
                self.enemies.append(e)
            self.squads.append(Squad(members))
        manpads = sum(1 for e in self.enemies if not e.dead and e.manpads)
        self.hud.message(f'Vague {w} — la colonne arrive', 4,
                         f'{tanks} char(s) · {aa} blindé(s) anti-aérien(s) · {n} fantassins dont {manpads} MANPADS\n'
                         f'Tenez la ligne rouge et blanche ! Percées : {self.breaches}/{MAX_BREACHES}')

    def spawn_vehicle(self, kind, lane, skill):
        if self.over or self.mode != 'defense':
            return
        self.pending = max(0, self.pending - 1)
        Vehicle(self, kind, lane, self.world.hz - 6, skill)
        self.hud.add_feed('Char en approche !' if kind == 'tank' else 'Blindé anti-aérien en approche !')

    def advance_point(self, e):
        """Étape suivante de la progression d'un fantassin vers la ligne à tenir."""
        w = self.world
        z = max(e.z - random.uniform(10, 16), w.defense_z - 6)
        x = clamp(e.x + random.uniform(-6, 6), -w.hx + 3, w.hx - 3)
        return self.world.free_point_near(Vec3(x, 0, z))

    def breach(self, who):
        """Un ennemi a franchi la ligne."""
        if self.over:
            return
        self.breaches += 1
        what = {'tank': 'Un char', 'aa': 'Un blindé anti-aérien'}.get(getattr(who, 'kind', ''), 'Un fantassin')
        self.hud.message('PERCÉE !', 2.5, f'{what} a franchi la ligne — {self.breaches}/{MAX_BREACHES}')
        PAD.rumble(0.6, 0.6, 400)
        if self.breaches >= MAX_BREACHES:
            if self.player.drone is not None:
                self.player.drone.finish()
            self.over = True
            self.player.dead = True
            self.hud.message('La position est tombée !', 0,
                             f'Score : {self.score}   ·   Vague : {self.wave}\n\nEntrée (ou Croix) pour recommencer')

    def check_breaches(self):
        for e in self.enemies:
            if not e.dead and e.z < self.world.defense_z:
                e.dead = True
                e.release_cover()
                destroy(e)
                self.breach(e)
        self.check_wave_end()

    def wave_cleared(self):
        return (not any(not e.dead for e in self.enemies) and self.pending == 0
                and not any(v.alive for v in self.vehicles))

    def check_wave_end(self):
        if self.wave_over or self.over or self.wave == 0 or not self.wave_cleared():
            return
        self.wave_over = True
        self.hud.message('Vague terminée !', 3, 'Santé restaurée — la prochaine sera plus coriace')
        self.player.hp = min(100, self.player.hp + 50)
        if self.player.drone is not None:
            invoke(self.end_drone, delay=2.5)
        invoke(self.cleanup_and_next, delay=4.5)

    def on_enemy_killed(self, enemy, headshot):
        self.kills += 1
        bonus = self.wave * 10
        if headshot:
            self.add_score(150 + bonus, f'Tir à la tête ! +{150 + bonus}')
            if not self.ult_ready and self.player.drone is None:
                self.headshot_streak += 1
                if self.headshot_streak >= ULT_HEADSHOTS:
                    self.ult_ready = True
                    self.hud.message('ULTIME DISPONIBLE', 3, 'Flèche gauche (manette) ou U : drone Reaper '
                                                             'pour toute la manche')
                    PAD.rumble(0.5, 0.8, 300)
        else:
            self.add_score(100 + bonus, f'Ennemi éliminé +{100 + bonus}')
        self.check_wave_end()

    def activate_ult(self):
        """Flèche gauche / U : pilote le drone Reaper jusqu'à la fin de la manche."""
        p = self.player
        if p.drone is not None or p.dead or self.over or self.paused:
            return
        if not self.ult_ready:
            self.hud.add_feed(f'Ultime : {self.headshot_streak}/{ULT_HEADSHOTS} tirs à la tête')
            return
        if self.wave_cleared() or self.wave_over:
            self.hud.add_feed('Ultime : attendez le début de la manche')
            return
        if p.mount is not None:
            p.dismount()
        if p.tps:
            p.toggle_view()
        self.ult_ready = False
        self.headshot_streak = 0
        p.gun.visible = False
        self.hud.scope_visible(False)
        self.hud.crosshair_visible(False)
        camera.set_shader_input('zoom', 1.0)
        p._zoom_on = False
        p.drone = ReaperDrone(self)
        self.hud.set_text(self.hud.nv_label, '')
        self.hud.message('DRONE REAPER', 2.5, 'Canon : clic gauche / R2 · missiles IR guidés au réticule : Espace / R1'
                                              ' · vision : N / Triangle')
        PAD.rumble(0.4, 0.4, 250)

    def end_drone(self):
        if self.player.drone is not None:
            self.player.drone.finish()

    def cleanup_and_next(self):
        self.enemies = [e for e in self.enemies if not e.dead]
        self.next_wave()

    def add_score(self, pts, label):
        self.score += pts
        self.hud.add_feed(label)

    def flyby(self, point):
        if flat_dist(point, self.player.position) < 2.5:
            self.hud.damage.color = color.rgba(0.8, 0, 0, max(self.hud.damage.color.a, 0.08))

    # -- états -------------------------------------------------------------
    def game_over(self):
        self.over = True
        self.hud.message('Vous êtes mort !', 0,
                         f'Score : {self.score}   ·   Vague : {self.wave}\n\nEntrée (ou Croix) pour recommencer')
        self.player.pivot.animate_position((0, 0.3, 0), duration=0.6)
        self.player.pivot.animate_rotation_z(40, duration=0.6)

    def restart(self):
        for e in self.enemies:
            if not e.dead:
                e.dead = True
                e.release_cover()
                destroy(e)
        self.enemies = []
        self.squads = []
        for v in list(self.vehicles):
            v.remove()
        self.vehicles = []
        for m in list(self.sams):
            m.explode()
        self.breaches = 0
        self.pending = 0
        self.wave_over = False
        for c in list(self.corpses):
            destroy(c)
        self.corpses = []
        self.pickup = None
        FXM.clear()
        for gr in list(self.grenades):
            destroy(gr)
        self.grenades = []
        for c in self.world.covers:
            c.owner = None
        p = self.player
        if p.drone is not None:
            p.drone.finish()
        p.mount = None
        p.nades = 1
        self.headshot_streak = 0
        self.ult_ready = False
        p.position = Vec3(self.world.spawn)
        p.rotation_y = 0
        p.pivot.position = (0, 1.65, 0)
        p.pivot.rotation = (0, 0, 0)
        p.reset_weapons(p.start_weapon)
        if self.mode == 'defense':
            p.slots[1] = 'rpg'
        p.hp, p.dead, p.mag, p.reload_t, p.vel, p.vy = 100, False, p.weapon['mag'], 0, Vec3(0, 0, 0), 0
        p.armed = False
        p.crouching, p.crouch_t, p.lean_pad, p.lean_t = False, 0.0, 0, 0.0
        self.over = False
        self.score = self.kills = self.wave = 0
        self.hud.msg.text = ''
        self.hud.sub_msg.text = ''
        invoke(self.next_wave, delay=1.5)

    def toggle_pause(self):
        self.paused = not self.paused
        mouse.locked = not self.paused
        if self.paused:
            application.pause()
            self.hud.message('PAUSE', 0, CONTROLS_PAUSE)
        else:
            application.resume()
            self.hud.msg.text = ''
            self.hud.sub_msg.text = ''

    def find_pickup(self):
        """Cadavre le plus proche avec une arme, à portée de main."""
        p = self.player
        best, bd = None, PICKUP_RANGE
        if not p.dead and p.drone is None:
            for c in self.corpses:
                if getattr(c, 'nade_loot', 0) and p.nades < MAX_NADES and flat_dist(c.position, p.position) < 1.8:
                    c.nade_loot = 0                       # grenade ramassée automatiquement
                    p.nades += 1
                    self.hud.add_feed(f'+1 grenade  ({p.nades})')
                    PAD.rumble(0.1, 0.2, 50)
            for c in self.corpses:
                if c.loot is not None:
                    d = flat_dist(c.position, p.position)
                    if d < bd:
                        best, bd = c, d
        self.pickup = best
        aa = self.world.aa
        self.aa_near = None
        self.crate_near = False
        if p.mount is not None:
            self.hud.set_text(self.hud.prompt, 'Carré / V : quitter la batterie anti-aérienne'
                              + ('   ·   SURCHAUFFE' if p.mount.overheat else ''))
        elif p.drone is not None:
            self.hud.set_text(self.hud.prompt, '')
        elif best is None:
            ap = self.world.ammo_point
            self.crate_near = ap is not None and not p.dead and flat_dist(p.position, ap) < 2.4
            if self.crate_near:
                self.hud.set_text(self.hud.prompt, 'Carré / V : prendre des roquettes de RPG')
            elif aa is not None and not p.dead and flat_dist(p.position, aa.pos) < 2.8:
                self.aa_near = aa
                self.hud.set_text(self.hud.prompt, 'Carré / V : utiliser la batterie anti-aérienne')
            else:
                self.hud.set_text(self.hud.prompt, '')
        else:
            same = best.loot == p.weapon_key
            what = 'munitions' if same else WEAPONS[best.loot]['name'].lower()
            self.hud.set_text(self.hud.prompt, f'Carré / V : prendre {what}'
                              + ('' if same else f"  (remplace : {p.weapon['name'].lower()})"))

    GRASS_DIST = 38.0

    def update_grass(self, force=False):
        """L'herbe n'est dessinée qu'autour du joueur (au-delà, le brouillard la rend invisible)."""
        if not force:
            self.grass_t = getattr(self, 'grass_t', 0) - time.dt
            if self.grass_t > 0:
                return
        self.grass_t = 0.25
        p = self.player.drone.aim if self.player.drone is not None else self.player.position
        r2 = self.GRASS_DIST ** 2
        for g in self.world.grass:
            c = g.center
            on = self.high_quality and (c.x - p.x) ** 2 + (c.z - p.z) ** 2 < r2
            if g.enabled != on:
                g.enabled = on

    def update(self):
        if not self.paused:
            self.t += time.dt
        PAD.update(self.t)
        if self.nv:
            camera.set_shader_input('nv_time', self.t % 100)
        if not self.paused and not self.choosing:
            for sq in self.squads:
                sq.update(time.dt)
            self.find_pickup()
            self.emit_smoke()
            if self.mode == 'defense' and not self.over:
                self.breach_t = getattr(self, 'breach_t', 0) - time.dt
                if self.breach_t <= 0:
                    self.breach_t = 0.5
                    self.check_breaches()
        self.pad_actions()
        self.update_grass()
        self.hud.update()

    def emit_smoke(self):
        """Fumée noire qui s'échappe du char détruit (désert)."""
        pts = self.world.smoke_points
        if not pts:
            return
        self.smoke_t -= time.dt
        if self.smoke_t > 0:
            return
        self.smoke_t = 0.35         # peu de bouffées : la transparence superposée coûte cher au rendu
        for p in pts:
            sm = FXM.get('sphere')
            sm.color = rgb(40, 38, 36, 190)
            sm.position = p + Vec3(random.uniform(-.4, .4), 0, random.uniform(-.4, .4))
            sm.scale = random.uniform(0.7, 1.1)
            FXM.play(sm, 3.2, pos=sm.position + Vec3(random.uniform(1.5, 3.0), random.uniform(7, 9),
                                                     random.uniform(-1, 1)),
                     scale=Vec3(3, 3, 3), col=rgb(90, 88, 85, 0))

    def use_action(self):
        """Carré / V : quitter ou prendre la batterie AA, ramasser une arme. Renvoie False si rien à faire."""
        p = self.player
        if p.mount is not None:
            p.dismount()
        elif self.pickup is not None:
            p.take_weapon(self.pickup)
        elif getattr(self, 'aa_near', None) is not None:
            p.mount_aa(self.aa_near)
        elif getattr(self, 'crate_near', False):
            full = WEAPONS['rpg']['mag']
            if 'rpg' not in p.slots:
                p.slots[p.slot ^ 1] = 'rpg'
                p.mags['rpg'] = full
            elif p.weapon_key == 'rpg':
                p.mag = full
            else:
                p.mags['rpg'] = full
            self.hud.add_feed(f'RPG rechargé : {full} roquettes (Triangle / Tab pour le prendre)')
            PAD.rumble(0.3, 0.3, 90)
        else:
            return False
        return True

    def pad_actions(self):
        """Boutons de la manette qui correspondent à des touches (menu, pause, saut, rechargement...)."""
        pad = PAD
        if not pad.available and not getattr(self, '_pad_warned', False) and self.t > 1:
            self._pad_warned = True
            self.hud.add_feed('Manette : installez pygame (pip install pygame)')
        if pad.connected != self._pad_was:
            self._pad_was = pad.connected
            if pad.connected:
                self.hud.add_feed(f'Manette connectée : {pad.name[:28]}')
            else:
                self.hud.add_feed('Manette déconnectée')
        if not pad.connected:
            return
        pr = pad.pressed
        if self.choosing:
            move = (pr['down'] or pr['up'] or pr['left'] or pr['right'])
            n = len(self.menu_buttons)
            if pr['down']:
                self.menu_sel = min(n - 1, self.menu_sel + 1)
            elif pr['up']:
                self.menu_sel = max(0, self.menu_sel - 1)
            if abs(pad.ly) > 0.6 and self.t - getattr(self, '_menu_stick_t', -9) > 0.25:
                self._menu_stick_t = self.t
                self.menu_sel = clamp(self.menu_sel + (-1 if pad.ly > 0 else 1), 0, n - 1)
                move = True
            if pr['left'] or pr['right']:
                act = self.menu_buttons[self.menu_sel].action
                if act == 'time':
                    self.toggle_night_choice()
                elif act == 'map':
                    self.toggle_map_choice()
                elif act == 'mode':
                    self.toggle_mode_choice()
            if move or pad.last_used == self.t:
                self.menu_cursor.visible = True
                sel = self.menu_buttons[self.menu_sel]
                self.menu_cursor.y = sel.y
                self.menu_cursor.scale_y = sel.scale_y + 0.03
            if pr['cross']:
                b = self.menu_buttons[self.menu_sel]
                if b.action == 'time':
                    self.toggle_night_choice()
                elif b.action == 'map':
                    self.toggle_map_choice()
                elif b.action == 'mode':
                    self.toggle_mode_choice()
                else:
                    self.choose_weapon(b.action)
            return
        if pr['options'] and not self.over:
            self.toggle_pause()
        elif self.paused:
            if pr['share']:
                application.quit()
        elif self.over:
            if pr['cross']:
                self.restart()
        elif self.player.drone is not None:
            pass                                    # R1 (missiles) est lu par le drone
        else:
            if pr['cross'] and self.player.mount is None:
                self.player.jump()
            if pr['square']:
                if not self.use_action():
                    self.player.reload()
            if pr['r1']:
                self.player.throw_grenade()
            if pr['left']:
                self.activate_ult()
            if pr['down']:
                self.player.toggle_view()
            if pr['up']:
                self.toggle_nv()
            if pr['circle']:
                self.player.toggle_crouch()
            if pr['triangle']:
                self.player.switch_weapon()

    def input(self, key):
        if self.choosing:
            if key in ('1', '2'):
                self.choose_weapon('rifle' if key == '1' else 'sniper')
            elif key in ('3', 'n'):
                self.toggle_night_choice()
            elif key == '4':
                self.toggle_map_choice()
            elif key == '5':
                self.toggle_mode_choice()
            elif key == 'g':
                self.set_quality(not self.high_quality)
            return
        if key == 'escape':
            if not self.over:
                self.toggle_pause()
        elif key == 'x' and self.paused:
            application.quit()
        elif key == 'g':
            self.set_quality(not self.high_quality)
            self.hud.add_feed('Graphismes : ' + ('élevés' if self.high_quality else 'rapides'))
        elif self.paused:
            return
        elif self.player.drone is not None:
            if key == 'space':
                self.player.drone.fire_missile()
            elif key == 'n':
                self.player.drone.toggle_vision()
            elif key == 'f':
                self.player.drone.drop_flares()
            elif key == 'm':
                self.hud.minimap.root.enabled = not self.hud.minimap.root.enabled
            elif key == 'left mouse down' and not mouse.locked:
                mouse.locked = True
            return
        elif key == 'v' and self.use_action():
            pass
        elif self.player.mount is not None and key not in ('m', 'left mouse down'):
            return
        elif key == 'x':
            self.player.throw_grenade()
        elif key == 'u':
            self.activate_ult()
        elif key == 'space':
            self.player.jump()
        elif key == 'r':
            self.player.reload()
        elif key == 'c':
            self.player.toggle_crouch()
        elif key == 't':
            self.player.toggle_view()
        elif key == 'n':
            self.toggle_nv()
        elif key == 'tab':
            self.player.switch_weapon()
        elif key == 'm':
            self.hud.minimap.root.enabled = not self.hud.minimap.root.enabled
        elif key == 'enter' and self.over:
            self.restart()
        elif key == 'left mouse down' and not mouse.locked:
            mouse.locked = True


if __name__ == '__main__':
    app = Ursina(title='FPS Ursina', borderless=False, development_mode=False)
    limit_fps()
    window.color = FOG_COLOR
    window.fps_counter.enabled = False
    window.exit_button.visible = False
    game = Game()
    app.run()
