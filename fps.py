"""
Petit FPS avec Ursina — ennemis humanoïdes dotés d'une IA tactique qui progresse.

Lancement :  python fps.py            (vsync coupé : FPS non plafonnés)
             python fps.py --vsync    (vsync activé : FPS calés sur l'écran, pas de déchirure)

Au lancement : choix de l'arme (clic sur le menu, ou touches 1 / 2)
    1 : fusil d'assaut (tir automatique, viseur point rouge)
    2 : sniper (un tir par clic, gros dégâts, lunette zoom x2)

Commandes (clavier AZERTY) :
    E / flèche haut    : avancer
    S / flèche bas     : reculer
    Q / flèche gauche  : aller à gauche
    D / flèche droite  : aller à droite
    Z (ou Maj)         : courir
    Espace             : sauter
    Clic gauche ou P   : tirer (fusil : maintenir pour le tir automatique)
    Clic droit         : viser (point rouge / lunette du sniper)
    R                  : recharger
    G                  : qualité graphique (post-traitement + herbe) on/off
    Échap              : pause (X pour quitter pendant la pause)
    Entrée             : recommencer après la mort

IA des ennemis (de plus en plus redoutable à chaque vague) :
    - perception : champ de vision, ligne de vue (raycast), audition des tirs
    - mémoire de la dernière position connue du joueur, partage d'infos entre alliés
    - recherche de couverture (murs, voitures, arbres, sacs de sable, rochers),
      sortie de couverture pour tirer puis retour à l'abri, rechargement à couvert
    - tirs de couverture coordonnés quand un allié se déplace
    - contournement (flanc), prise en tenaille, repli quand ils sont blessés, esquive
    - grenades pour déloger le joueur caché, fuite devant les grenades
    - déplacement par A* sur une grille de navigation
    - corps articulé animé : marche, course, accroupi, visée, lancer, impacts, chute
"""

import heapq
import math
import random
import sys

from ursina import (
    Ursina, Entity, Text, Sky, DirectionalLight, Vec2, Vec3, Mesh, Shader, Quad, Button, Texture,
    camera, color, mouse, held_keys, time, window, application, raycast,
    destroy, invoke, clamp, lerp, scene,
)
from ursina.color import Color
from ursina.collider import Collider
from panda3d.core import CollisionBox


ARENA = 45          # l'arène va de -ARENA à +ARENA sur x et z
GRAVITY = 22
PLAYER_RADIUS = 0.5
ENEMY_RADIUS = 0.35
EYE_STAND = 1.6     # hauteur des yeux d'un ennemi debout
EYE_CROUCH = 1.0    # hauteur de la tête d'un ennemi accroupi
SHADOW_RES = 2048        # 4096 auparavant : aucune différence visible grâce au filtrage PCF
VSYNC = '--vsync' in sys.argv   # vsync coupé par défaut : lancer « python fps.py --vsync » pour le réactiver

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
    p3d_FragColor = vec4(col, base.a);
}
''', default_input={
    'texture_scale': Vec2(1, 1),
    'texture_offset': Vec2(0, 0),
    'sky_color': Color(0.50, 0.56, 0.66, 1),
    'ground_color': Color(0.30, 0.28, 0.22, 1),
    'fog_color': FOG_COLOR,
    'fog_density': 0.0085,
    'specular': 0.0,
    'shadow_texel': 1 / SHADOW_RES,
    'sun_strength': 0.95,
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
in vec2 uv;
out vec4 out_color;

void main() {
    vec2 px = 1.0 / vec2(textureSize(tex, 0));
    vec3 c = texture(tex, uv).rgb;

    // léger bloom sur les zones lumineuses
    vec3 b = vec3(0.0);
    // 8 échantillons en spirale (au lieu de 16) : même halo, moitié moins de lectures
    for (int i = 0; i < 8; i++) {
        float a = float(i) * 0.785398 + 0.3927;
        vec2 dir = vec2(cos(a), sin(a));
        b += max(texture(tex, uv + dir * px * (i % 2 == 0 ? 4.0 : 9.0)).rgb - 0.72, 0.0);
    }
    c += b * 0.12;

    // étalonnage : saturation, contraste, teinte chaude
    float l = dot(c, vec3(0.299, 0.587, 0.114));
    c = mix(vec3(l), c, 1.18);
    c = (c - 0.5) * 1.07 + 0.5;
    c *= vec3(1.03, 1.0, 0.96);

    // vignettage
    vec2 d = uv - 0.5;
    float v = smoothstep(0.95, 0.30, length(d * vec2(1.0, 0.8)) * 1.25);
    c *= mix(0.62, 1.0, v);
    out_color = vec4(clamp(c, 0.0, 1.0), 1.0);
}
''')


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

    def box(self, center, size, col, tile=None, jitter=0.0, top=True, bottom=False):
        cx, cy, cz = center
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

    def blob(self, center, radii, col, seg=7, rings=5, jitter=0.1, rough=0.12, rng=random):
        """Ellipsoïde à facettes irrégulières (feuillage, rochers, sacs de sable)."""
        cx, cy, cz = center
        rx, ry, rz = radii
        grid = []
        for j in range(rings + 1):
            phi = math.pi * j / rings
            row = []
            for i in range(seg):
                th = 2 * math.pi * i / seg
                k = 1 + (rng.uniform(-rough, rough) if 0 < j < rings else 0)
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


class World:
    CELL = 1.0

    def __init__(self):
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

    def area_free(self, cx, cz, sx, sz, margin=1.2):
        probe = Box(cx, cz, sx + 2 * margin, sz + 2 * margin, 1)
        for b in self.boxes:
            if not (probe.x1 < b.x0 or probe.x0 > b.x1 or probe.z1 < b.z0 or probe.z0 > b.z1):
                return False
        return abs(cx) + sx / 2 < ARENA - 1.5 and abs(cz) + sz / 2 < ARENA - 1.5

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
        b.box((0, size / 2, 0), (size, size, size), rgb(160, 115, 65), jitter=0.06)
        dark = rgb(115, 80, 45)
        e = size / 2 + 0.01
        for sgn in (-1, 1):   # renforts
            b.box((0, size / 2, sgn * e), (size, 0.12, 0.03), dark)
            b.box((sgn * e, size / 2, 0), (0.03, 0.12, size), dark)
            b.box((0, size - 0.06, sgn * e), (size, 0.12, 0.03), dark)
            b.box((0, 0.06, sgn * e), (size, 0.12, 0.03), dark)
        b.xf()

    def tree(self, x, z, collide=True, scale=1.0, y=0.0):
        rng = self.rng
        pine = rng.random() < 0.45
        h = rng.uniform(2.4, 3.3) * scale
        r = 0.27 * scale
        self.plain.xf()
        self.plain.cylinder((x, y - 0.2, z), r, h + 1.2, rgb(95, 68, 45), seg=8, caps=False)
        f = self.foliage
        f.xf()
        if pine:
            greens = [rgb(40, 85, 50), rgb(50, 100, 55), rgb(35, 75, 45)]
            base = y + h * 0.45
            for k in range(4):
                f.cone((x, base + k * 1.05 * scale, z), (2.0 - k * 0.42) * scale, 1.9 * scale,
                       rng.choice(greens), seg=9, jitter=0.12)
        else:
            greens = [rgb(70, 125, 50), rgb(85, 140, 55), rgb(60, 110, 45), rgb(95, 145, 60)]
            top = y + h + 0.5 * scale
            f.blob((x, top, z), (1.5 * scale, 1.25 * scale, 1.5 * scale), rng.choice(greens), rng=rng)
            for _ in range(rng.randint(3, 5)):
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
        s, p = self.shiny, self.plain
        s.xf((x, 0, z), yaw)
        p.xf((x, 0, z), yaw)
        s.box((0, 0.68, 0), (1.86, 0.62, 4.3), paint)
        s.box((0, 1.02, 1.35), (1.8, 0.08, 1.5), shade(paint, 0.95))         # capot
        s.box((0, 1.22, -0.25), (1.62, 0.55, 2.15), shade(paint, 0.97))      # habitacle
        s.box((0, 1.24, -0.25), (1.66, 0.4, 2.2), rgb(40, 55, 70))           # vitres
        dark = rgb(30, 30, 32)
        p.box((0, 0.45, 2.17), (1.9, 0.24, 0.1), dark)                       # pare-chocs
        p.box((0, 0.45, -2.17), (1.9, 0.24, 0.1), dark)
        p.box((0, 0.72, 2.16), (1.2, 0.16, 0.04), rgb(60, 60, 64))            # calandre
        for sgn in (-1, 1):
            p.box((sgn * 0.68, 0.78, 2.16), (0.34, 0.14, 0.05), rgb(255, 250, 225))
            p.box((sgn * 0.7, 0.78, -2.16), (0.3, 0.12, 0.05), rgb(200, 30, 30))
            for wz in (1.35, -1.35):
                p.cylinder((sgn * 0.84 - 0.13, 0.38, wz), 0.38, 0.26, dark, seg=12, axis='x',
                           col_cap=rgb(150, 150, 155))
        p.xf()
        s.xf()

    def sandbags(self, cx, cz, length, along_x=True):
        sx, sz = (length, 0.8) if along_x else (0.8, length)
        self.add_box(cx, cz, sx, sz, 1.12)
        n = int(length / 0.62)
        khaki = rgb(160, 145, 105)
        self.plain.xf()
        for layer in range(3):
            off = 0.31 if layer % 2 else 0
            for i in range(n - (1 if layer % 2 else 0)):
                t = -length / 2 + 0.31 + i * 0.62 + off
                px, pz = (cx + t, cz) if along_x else (cx, cz + t)
                rx, rz = (0.33, 0.24) if along_x else (0.24, 0.33)
                self.plain.blob((px, 0.19 + layer * 0.35, pz), (rx, 0.19, rz), khaki, seg=7, rings=4,
                                jitter=0.08, rough=0.05, rng=self.rng)

    def barrels(self, cx, cz):
        cols = [rgb(170, 45, 35), rgb(40, 80, 150), rgb(120, 90, 50), rgb(60, 110, 70)]
        offs = [(0, 0), (0.65, 0.1), (0.3, 0.6)][:self.rng.randint(2, 3)]
        self.plain.xf()
        for ox, oz in offs:
            c = self.rng.choice(cols)
            self.plain.cylinder((cx + ox, 0, cz + oz), 0.3, 0.95, c, seg=12, col_cap=shade(c, 0.8))
            for ry in (0.3, 0.65):
                self.plain.cylinder((cx + ox, ry, cz + oz), 0.315, 0.04, shade(c, 0.7), seg=12, caps=False)
        self.add_box(cx + 0.3, cz + 0.3, 1.3, 1.3, 0.95)

    def rock(self, cx, cz, size=1.0):
        self.plain.xf()
        self.plain.blob((cx, 0.35 * size, cz), (1.2 * size, 0.95 * size, 1.0 * size), rgb(125, 122, 115),
                        seg=7, rings=5, jitter=0.12, rough=0.18, rng=self.rng)
        self.add_box(cx, cz, 2.0 * size, 1.7 * size, 1.25 * size)

    # -- terrain -------------------------------------------------------------
    def build_ground(self):
        """Sol limité à l'arène (rien n'est construit hors des murs)."""
        half = ARENA + 2
        n = 32
        step = 2 * half / n
        b = MeshBuilder()
        up = Vec3(0, 1, 0)
        cache = {}

        def vert(i, j):
            if (i, j) not in cache:
                x, z = -half + i * step, -half + j * step
                nz = value_noise(x, z, 1) * 0.5 + 0.5
                dry = value_noise(x * 1.7, z * 1.7, 5) * 0.5 + 0.5
                col = Color(lerp(0.42, 0.6, nz) + dry * 0.14, lerp(0.7, 0.85, nz), lerp(0.42, 0.55, nz), 1)
                cache[(i, j)] = (Vec3(x, 0, z), col, (x / 3, z / 3))
            return cache[(i, j)]

        for i in range(n):
            for j in range(n):
                q = [vert(i, j), vert(i + 1, j), vert(i + 1, j + 1), vert(i, j + 1)]
                for a, bb, c in ((0, 1, 2), (0, 2, 3)):
                    b.tri(q[a][0], q[bb][0], q[c][0], [q[a][1], q[bb][1], q[c][1]], up,
                          (q[a][2], q[bb][2], q[c][2]), local=False)
        # le sol ne projette aucune ombre : on l'exclut de la passe d'ombres
        b.build(self.level, texture='grass', cast_shadows=False)
        # collisionneur plat pour les impacts de balles
        self.add_collider(0, -0.05, 0, 2 * half, 0.1, 2 * half)

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
        self.build_ground()
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
            self.wall(cx, cz, sx, sz, 3)
        # toit de la maison du nord (au-dessus des têtes)
        self.plain.xf()
        self.plain.box((0, 3.2, 32), (15.2, 0.25, 10), rgb(140, 70, 55), jitter=0.02, bottom=True)

        # murets bas
        for cx, cz, sx, sz in [(0, 0, 7, 0.8), (-18, 22, 5, 0.8), (18, 22, 5, 0.8), (-16, -29, 0.8, 5),
                               (16, -29, 0.8, 5), (-37, 7, 5, 0.8), (37, 7, 5, 0.8), (0, -27, 6, 0.8)]:
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
            if abs(x) < 9 and z < -30:       # zone de départ et cibles dégagées
                continue
            if not self.area_free(x, z, 0.7, 0.7, margin=1.8):
                continue
            self.tree(x, z, scale=self.rng.uniform(0.9, 1.25))
            placed += 1

    def build_grass(self):
        """Touffes d'herbe et fleurs, sans ombre portée.

        Découpées en tuiles de 15 m : Panda3D ne dessine que les tuiles dans le champ de vision."""
        b = MeshBuilder(tile=15)
        rng = random.Random(99)
        flowers = [rgb(250, 230, 80), rgb(245, 245, 245), rgb(190, 120, 220), rgb(240, 120, 60)]
        up = Vec3(0, 1, 0)
        count = 0
        while count < 14000:
            x = rng.uniform(-ARENA + 1, ARENA - 1)
            z = rng.uniform(-ARENA + 1, ARENA - 1)
            if 12.2 < z < 16.8 or not self.is_free(Vec3(x, 0, z)):
                continue
            count += 1
            nz = value_noise(x, z, 1) * 0.5 + 0.5
            base = Color(0.26 + 0.06 * nz, 0.38 + 0.06 * nz, 0.14, 1)
            tip = Color(0.44 + 0.14 * nz, 0.60 + 0.08 * nz, 0.24, 1)
            flower = rng.random() < 0.05
            for _ in range(4):
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

    def floor_height(self, x, z, r, y):
        """Hauteur du sol sous une entité (sol ou dessus d'une caisse / d'un muret)."""
        h = 0
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
        self.n = int(ARENA * 2 / self.CELL)
        self.blocked = [[False] * self.n for _ in range(self.n)]
        for i in range(self.n):
            for j in range(self.n):
                x, z = self.cell_center(i, j)
                if abs(x) > ARENA - 1 or abs(z) > ARENA - 1:
                    self.blocked[i][j] = True
        for b in self.boxes:
            i0, j0 = self.cell_of(Vec3(b.x0 - 1, 0, b.z0 - 1))
            i1, j1 = self.cell_of(Vec3(b.x1 + 1, 0, b.z1 + 1))
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    x, z = self.cell_center(i, j)
                    if b.circle_overlap(x, z, 0.55):
                        self.blocked[i][j] = True
        self.free_cells = [(i, j) for i in range(self.n) for j in range(self.n) if not self.blocked[i][j]]

    def cell_center(self, i, j):
        return -ARENA + (i + 0.5) * self.CELL, -ARENA + (j + 0.5) * self.CELL

    def cell_of(self, p):
        i = int((p.x + ARENA) / self.CELL)
        j = int((p.z + ARENA) / self.CELL)
        return clamp(i, 0, self.n - 1), clamp(j, 0, self.n - 1)

    def is_free(self, p):
        return self.free_xz(p.x, p.z)

    def free_xz(self, x, z):
        i = int((x + ARENA) / self.CELL)
        j = int((z + ARENA) / self.CELL)
        if i < 0 or j < 0 or i >= self.n or j >= self.n:
            return False
        return not self.blocked[i][j]

    def nearest_free(self, c):
        if not self.blocked[c[0]][c[1]]:
            return c
        for rad in range(1, 6):
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    i, j = c[0] + di, c[1] + dj
                    if 0 <= i < self.n and 0 <= j < self.n and not self.blocked[i][j]:
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
                if not (0 <= ni < self.n and 0 <= nj < self.n) or self.blocked[ni][nj]:
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
                    if abs(p.x) > ARENA - 1.2 or abs(p.z) > ARENA - 1.2:
                        continue
                    if self.is_free(p):
                        self.covers.append(CoverPoint(p, normal, b.h))


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
            if fx[4] is not None:
                e.position = lerp(fx[3], fx[4], k)
            if fx[6] is not None:
                e.scale = lerp(fx[5], fx[6], k)
            if fx[8] is not None:
                e.color = lerp(fx[7], fx[8], k)
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
# Cibles d'entraînement
# ---------------------------------------------------------------------------

class Target(Entity):
    def __init__(self, game, position, yaw=0):
        super().__init__(position=position, rotation_y=yaw)
        self.game = game
        Entity(parent=self, model='cube', color=rgb(100, 70, 40), scale=(0.1, 1.2, 0.1), y=0.6, shader=LIT)
        Entity(parent=self, model='cube', color=rgb(90, 90, 95), scale=(0.6, 0.08, 0.6), y=0.04, shader=LIT)
        self.board = Entity(parent=self, y=1.2)
        Entity(parent=self.board, model='cube', color=rgb(120, 85, 50), scale=(0.95, 0.95, 0.04), y=0.5, z=0.03,
               shader=LIT)
        rings = [(0.9, color.white), (0.7, rgb(210, 30, 30)), (0.5, color.white), (0.3, rgb(210, 30, 30)),
                 (0.12, color.white)]
        for k, (s, c) in enumerate(rings):
            Entity(parent=self.board, model='circle', color=c, scale=s, y=0.5, z=-0.03 - k * 0.012,
                   unlit=True, double_sided=True)
        self.hitbox = Entity(parent=self.board, model='cube', scale=(0.9, 0.9, 0.05), y=0.5,
                             collider='box', visible=False)
        self.hitbox.target = self
        self.is_down = False

    def hit(self):
        if self.is_down:
            return
        self.is_down = True
        self.game.add_score(10, 'Cible +10')
        self.board.animate_rotation_x(-90, duration=0.2)
        invoke(self.reset, delay=3)

    def reset(self):
        self.board.animate_rotation_x(0, duration=0.3)
        self.is_down = False


# ---------------------------------------------------------------------------
# Grenades
# ---------------------------------------------------------------------------

class Grenade(Entity):
    def __init__(self, game, start, target):
        super().__init__(model='sphere', color=rgb(55, 70, 40), scale=0.16, position=start, shader=LIT)
        self.game = game
        self.world = game.world
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
        flash = FXM.get('sphere')
        flash.color = rgb(255, 200, 90)
        flash.position = pos
        flash.scale = 0.5
        FXM.play(flash, 0.3, scale=Vec3(5, 5, 5), col=rgb(255, 120, 30, 0))
        for _ in range(9):
            sm = FXM.get('sphere')
            sm.color = rgb(90, 85, 80, 200)
            sm.position = pos + Vec3(random.uniform(-.8, .8), random.uniform(0, .5), random.uniform(-.8, .8))
            sm.scale = random.uniform(0.6, 1.2)
            FXM.play(sm, 1.8, pos=sm.position + Vec3(random.uniform(-1, 1), random.uniform(1.5, 3), random.uniform(-1, 1)),
                     scale=sm.scale * 2.5, col=rgb(120, 115, 110, 0))
        scorch = FXM.get('circle')
        scorch.color = rgb(25, 22, 20, 200)
        scorch.position = (pos.x, 0.035, pos.z)
        scorch.rotation_x = 90
        scorch.scale = 2.4
        scorch.double_sided = True
        FXM.play(scorch, 20)
        for _ in range(12):
            p = FXM.get('cube')
            p.color = rgb(70, 60, 50)
            p.position = pos
            p.scale = 0.06
            FXM.play(p, 0.4, pos=pos + Vec3(random.uniform(-3, 3), random.uniform(0.2, 2.5), random.uniform(-3, 3)))
        radius = 6.0
        pl = g.player
        center = pos + Vec3(0, 0.3, 0)
        d = (pl.position + Vec3(0, 0.9, 0) - center).length()
        if not pl.dead and d < radius and (self.world.los(center, pl.eye)
                                           or self.world.los(center, pl.position + Vec3(0, 0.5, 0))):
            pl.take_damage(int(105 * (1 - d / radius) ** 1.1) + 5, pos)
        if d < 16:
            pl.shake = max(pl.shake, 0.6 * (1 - d / 16))
        for e in list(g.enemies):
            if e.dead:
                continue
            de = (e.position + Vec3(0, 0.9, 0) - center).length()
            if de < radius and self.world.los(center, e.eye):
                e.take_hit(int(100 * (1 - de / radius)), 'body', e.position + Vec3(0, 1, 0), explosive=True)


# ---------------------------------------------------------------------------
# Ennemi humanoïde
# ---------------------------------------------------------------------------

TIERS = [
    dict(name='Recrues', uniform=rgb(85, 100, 60), dark=rgb(60, 70, 42), helmet=rgb(70, 82, 50), visor=None),
    dict(name='Soldats', uniform=rgb(175, 155, 115), dark=rgb(135, 115, 82), helmet=rgb(150, 130, 95), visor=None),
    dict(name='Commandos', uniform=rgb(80, 92, 108), dark=rgb(55, 62, 76), helmet=rgb(60, 66, 80),
         visor=rgb(40, 180, 220)),
    dict(name='Élite', uniform=rgb(38, 38, 44), dark=rgb(24, 24, 28), helmet=rgb(30, 30, 34), visor=rgb(230, 40, 40)),
]


class Enemy(Entity):
    SKIN = rgb(224, 172, 130)
    BOOT = rgb(40, 32, 25)
    GUN = rgb(35, 35, 38)

    def __init__(self, game, position, skill=0.0, tier=0):
        super().__init__(position=position)
        self.game = game
        self.world = game.world
        self.skill = skill
        self.tier = TIERS[tier]
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
        self.mag = 8
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

    def build_body(self):
        t = self.tier
        U, UD, S = t['uniform'], t['dark'], self.SKIN
        glove = rgb(35, 32, 30)
        self._bone_parts = {}
        # bassin : pivot principal (hauteur des hanches)
        self.hips = Entity(parent=self, y=0.95)
        self.part(self.hips, (0, 0.02, 0), (0.36, 0.2, 0.22), UD, 'body')
        self.part(self.hips, (0, 0.1, 0), (0.39, 0.06, 0.25), rgb(45, 40, 32), 'body', collide=False)   # ceinture
        # torse : pivote au bassin
        self.torso = Entity(parent=self.hips, y=0.08)
        self.part(self.torso, (0, 0.28, 0), (0.42, 0.5, 0.25), U, 'body')
        self.part(self.torso, (0, 0.3, 0.12), (0.36, 0.36, 0.06), UD, 'body', collide=False)    # gilet
        for px in (-0.1, 0.02, 0.14):                                                          # poches
            self.part(self.torso, (px, 0.2, 0.16), (0.09, 0.11, 0.05), shade(UD, 0.85), 'body', collide=False)
        self.part(self.torso, (0, 0.3, -0.19), (0.3, 0.38, 0.14), shade(UD, 0.9), 'body')       # sac à dos
        self.part(self.torso, (0, 0.52, -0.19), (0.26, 0.08, 0.13), shade(UD, 0.75), 'body', collide=False)
        self.part(self.torso, (0, 0.58, 0), (0.11, 0.08, 0.11), S, 'body', collide=False)        # cou
        # tête
        self.neck = Entity(parent=self.torso, y=0.6)
        self.part(self.neck, (0, 0.14, 0), (0.22, 0.26, 0.24), S, 'head')
        self.part(self.neck, (0, 0.26, -0.01), (0.27, 0.1, 0.29), t['helmet'], 'head')              # casque
        self.part(self.neck, (0, 0.22, 0), (0.28, 0.04, 0.3), shade(t['helmet'], 0.8), 'head', collide=False)
        self.part(self.neck, (0, 0.07, 0.12), (0.06, 0.05, 0.02), shade(S, 0.9), 'head', collide=False)  # nez
        if t['visor'] is not None:
            self.part(self.neck, (0, 0.17, 0.125), (0.2, 0.06, 0.02), t['visor'], 'head', collide=False, lit=False)
        else:
            for ex in (-0.055, 0.055):
                self.part(self.neck, (ex, 0.17, 0.12), (0.045, 0.03, 0.01), color.black, 'head', collide=False)
            self.part(self.neck, (0, 0.23, 0.13), (0.2, 0.025, 0.02), shade(S, 0.7), 'head', collide=False)

        # bras : épaule -> bras -> coude -> avant-bras -> main
        self.shoulders, self.elbows = [], []
        for side in (-1, 1):
            sh = Entity(parent=self.torso, position=(0.27 * side, 0.48, 0))
            self.part(sh, (0, 0, 0), (0.15, 0.12, 0.15), UD, 'limb', collide=False)            # épaulière
            self.part(sh, (0, -0.15, 0), (0.12, 0.32, 0.12), U, 'limb')
            el = Entity(parent=sh, y=-0.3)
            self.part(el, (0, -0.14, 0), (0.1, 0.28, 0.1), U, 'limb')
            self.part(el, (0, -0.31, 0), (0.09, 0.1, 0.09), glove, 'limb')                   # main
            self.shoulders.append(sh)
            self.elbows.append(el)
        # fusil tenu dans la main droite (orienté comme l'avant-bras)
        self.gun = Entity(parent=self.elbows[1], y=-0.31, rotation_x=90)
        self.part(self.gun, (0, 0.02, 0.2), (0.06, 0.1, 0.62), self.GUN, 'gun')
        self.part(self.gun, (0, -0.06, 0.1), (0.05, 0.14, 0.06), self.GUN, 'gun', collide=False)
        self.part(self.gun, (0, -0.07, 0.3), (0.05, 0.16, 0.07), self.GUN, 'gun', collide=False)    # chargeur
        self.part(self.gun, (0, 0.0, -0.13), (0.06, 0.12, 0.2), rgb(90, 65, 40), 'gun', collide=False)
        self.muzzle = Entity(parent=self.gun, z=0.55, y=0.02)

        # jambes : hanche -> cuisse -> genou -> tibia -> pied
        self.hip_joints, self.knees = [], []
        for side in (-1, 1):
            hj = Entity(parent=self.hips, position=(0.1 * side, -0.05, 0))
            self.part(hj, (0, -0.22, 0), (0.15, 0.45, 0.16), UD, 'limb')
            self.part(hj, (0.08 * side, -0.25, 0.02), (0.05, 0.12, 0.1), shade(UD, 0.85), 'limb', collide=False)
            kn = Entity(parent=hj, y=-0.44)
            self.part(kn, (0, -0.2, 0), (0.13, 0.42, 0.14), UD, 'limb')
            self.part(kn, (0, -0.03, 0.07), (0.12, 0.1, 0.04), rgb(40, 40, 40), 'limb', collide=False)  # genouillère
            self.part(kn, (0, -0.43, 0.05), (0.14, 0.09, 0.27), self.BOOT, 'limb')
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
        if pl.dead:
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

    def choose_cover(self, far=False, avoid=None):
        threat = self.threat_eye()
        tpos = flat(threat)
        best, best_score = None, -1e9
        candidates = [c for c in self.world.covers
                      if (c.owner is None or c.owner is self)
                      and flat_dist(c.pos, self.position) < (30 if far else 22)]
        candidates.sort(key=lambda c: flat_dist(c.pos, self.position))
        others = [e.position for e in self.game.enemies if e is not self and not e.dead]
        ideal = 14 - 3 * self.skill
        for c in candidates[:50]:
            d_threat = flat_dist(c.pos, tpos)
            if d_threat < 5:
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
            score += random.uniform(0, 2)
            if score > best_score:
                best, best_score = c, score
        return best

    def release_cover(self):
        if self.cover and self.cover.owner is self:
            self.cover.owner = None
        self.cover = None

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
                if self.arrived() and self.timer <= 0:
                    self.set_path_to(self.world.random_free_point(self.position, 18))
                    self.timer = random.uniform(1, 4)
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
        if g.player.dead:
            self.state = 'patrol'
            self.sub = ''
            self.burst = 0
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
                self.mag = 8
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
                    self.burst = min(self.mag, random.randint(3, 5))
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
                self.burst = min(self.mag, random.randint(2, 4))
                self.shot_t = 0.3 * self.reaction
            if self.mag <= 0:
                self.mag = 8
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
        muzzle_flash(self.muzzle, scale=0.3)
        target = pl.eye - Vec3(0, 0.35, 0)
        dist = flat_dist(self.position, pl.position)
        chance = clamp(self.accuracy - dist / (45 + 25 * self.skill), 0.12, 0.85)
        if pl.speed_now > 5:        # les meilleurs anticipent vos déplacements
            chance *= lerp(0.55, 0.85, self.skill)
        elif pl.speed_now > 1:
            chance *= lerp(0.8, 0.95, self.skill)
        if pl.ads > 0.5 and pl.speed_now < 1:
            chance *= 1.1           # immobile en train de viser : cible facile
        if self.sub in ('skirmish', 'move_cover'):
            chance *= 0.6
        if not self.world.los(muzzle, pl.eye) and not self.world.los(self.eye, pl.eye):
            chance = 0
        if random.random() < chance:
            tracer(muzzle, target, rgb(255, 200, 80))
            pl.take_damage(random.randint(6, 10), self.position)
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
        self.game.on_enemy_killed(self, zone == 'head')
        for a in self.allies(20):
            a.receive_alert(self.game.player.position)
            if a.state == 'combat' and a.sub == 'hide':
                a.timer += 1.0 * a.reaction
        destroy(self, 8)

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
        if self.think_t <= 0:
            self.think_t += 0.2          # l'IA réfléchit 5 fois par seconde (décalée entre ennemis)
            self.think()

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
                    self.shot_t = random.uniform(0.12, 0.2)
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
        new.y = 0
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
        if a > 0.5 and self.last_known is not None:
            pe = self.game.player.eye - Vec3(0, 0.3, 0)
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
        if self.death_t > 6:
            self.scale = lerp(self.scale, Vec3(0.01, 0.01, 0.01), dt * 3)

    def on_destroy(self):
        self.release_cover()


# ---------------------------------------------------------------------------
# Armes du joueur
# ---------------------------------------------------------------------------

SNIPER_ZOOM = 2.0     # grossissement de la lunette par rapport à la vue normale (90°)

WEAPONS = {
    'rifle': dict(
        name="Fusil d'assaut", short='FUSIL', auto=True, cooldown=0.1, mag=30, reload=1.6,
        dmg={'head': 250, 'body': 34, 'limb': 22, 'gun': 15},
        spread=0.004, move_spread=0.02, ads_spread=0.25, kick=0.35,
        ads_fov=52, ads_sens=0.55, scope=False,
        flash=0.45 * 0.5, flash_intensity=0.5, flash_life=0.05 * 0.5,      # flash réduit de 50 %
        tracer=(0.015, 0.04),
        hip=Vec3(0.15, -0.14, 0.2), ads=Vec3(0, -0.16 * 0.42, 0.17),        # le point rouge au centre
    ),
    'sniper': dict(
        name='Sniper', short='SNIPER', auto=False, cooldown=1.25, mag=5, reload=2.6,
        dmg={'head': 500, 'body': 160, 'limb': 95, 'gun': 40},
        spread=0.035, move_spread=0.04, ads_spread=0.02, kick=2.6,
        ads_fov=math.degrees(2 * math.atan(math.tan(math.radians(45)) / SNIPER_ZOOM)),   # zoom x2
        ads_sens=0.45, scope=True,
        flash=0.7 * 0.5, flash_intensity=0.5, flash_life=0.06 * 0.5,
        tracer=(0.03, 0.09),
        hip=Vec3(0.15, -0.15, 0.2), ads=Vec3(0, -0.1, 0.12),
    ),
}


# ---------------------------------------------------------------------------
# Joueur
# ---------------------------------------------------------------------------

class Player(Entity):
    GUN_SCALE = 0.42
    DOT = Vec3(0, 0.16, 0.1)                     # point rouge (repère local de l'arme)

    def __init__(self, game):
        super().__init__(position=(0, 0, -40))
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
        self.weapon = WEAPONS['rifle']
        self.mag = self.weapon['mag']
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
        self.build_gun()

    @property
    def eye(self):
        return self.position + Vec3(0, 1.65, 0)

    def set_weapon(self, key):
        self.weapon = WEAPONS[key]
        destroy(self.gun)
        self.build_gun()
        self.mag = self.weapon['mag']
        self.reload_t = 0
        self.cooldown = 0.3
        self.armed = False
        self.trigger_ready = False

    def build_gun(self):
        if self.weapon['scope']:
            self.build_sniper()
        else:
            self.build_rifle()

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
        self.muzzle = Entity(parent=self.gun, z=1.4, y=0.02)
        self.eject = Entity(parent=self.gun, x=0.05, y=0.03, z=0.02)

    def build_rifle(self):
        self.gun = Entity(parent=camera, position=self.weapon['hip'], scale=self.GUN_SCALE)
        dark = rgb(38, 38, 42)
        mid = rgb(60, 62, 66)
        tan = rgb(150, 125, 90)

        def p(pos, sc, col):
            return Entity(parent=self.gun, model='cube', color=col, position=pos, scale=sc, shader=LIT)
        p((0, 0, 0), (0.09, 0.12, 0.55), dark)                 # boîtier
        p((0, 0.02, 0.42), (0.075, 0.09, 0.32), tan)             # garde-main
        p((0, 0.03, 0.66), (0.035, 0.035, 0.22), dark)           # canon
        p((0, 0.03, 0.78), (0.05, 0.05, 0.05), mid)              # cache-flamme
        p((0, -0.13, 0.12), (0.07, 0.2, 0.1), mid)               # chargeur
        p((0, -0.1, -0.1), (0.06, 0.15, 0.07), dark)             # poignée
        p((0, -0.02, -0.38), (0.07, 0.13, 0.25), tan)            # crosse
        p((0, 0.075, 0.05), (0.03, 0.03, 0.4), mid)              # rail
        # viseur point rouge
        p((0, 0.1, 0.08), (0.07, 0.02, 0.1), dark)
        p((0.035, 0.16, 0.08), (0.01, 0.1, 0.05), dark)
        p((-0.035, 0.16, 0.08), (0.01, 0.1, 0.05), dark)
        p((0, 0.215, 0.08), (0.08, 0.012, 0.05), dark)
        self.dot = Entity(parent=self.gun, model='quad', texture='circle', color=rgb(255, 40, 40),
                          position=self.DOT, scale=0.006, unlit=True)      # point rouge réduit de 50 %
        self.muzzle = Entity(parent=self.gun, z=0.82, y=0.03)
        self.eject = Entity(parent=self.gun, x=0.05, y=0.03, z=0.05)

    def take_damage(self, dmg, from_pos):
        if self.dead or self.game.paused:
            return
        self.hp -= dmg
        self.last_hurt = self.game.t
        self.shake = max(self.shake, 0.15)
        self.game.hud.flash_damage(from_pos)
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            self.game.game_over()

    def update(self):
        if self.game.paused or self.dead or self.game.choosing:
            return
        dt = time.dt
        w = self.weapon
        aiming = held_keys['right mouse'] and self.reload_t <= 0 and not self.sprinting
        self.ads = lerp(self.ads, 1.0 if aiming else 0.0, min(1, dt * 14))

        # regard à la souris (plus précis en visée)
        if mouse.locked:
            sens = lerp(1.0, w['ads_sens'], self.ads)
            self.rotation_y += mouse.velocity[0] * self.sensitivity[1] * sens
            self.pivot.rotation_x -= mouse.velocity[1] * self.sensitivity[0] * sens
            self.pivot.rotation_x = clamp(self.pivot.rotation_x, -89, 89)

        # déplacement : E avancer, S reculer, Q gauche, D droite (+ flèches) ; Z pour courir
        fwd = clamp(held_keys['e'] + held_keys['up arrow'], 0, 1) - clamp(held_keys['s'] + held_keys['down arrow'], 0, 1)
        side = clamp(held_keys['d'] + held_keys['right arrow'], 0, 1) - clamp(held_keys['q'] + held_keys['left arrow'], 0, 1)
        direction = flat(self.forward) * fwd + flat(self.right) * side
        if direction.length() > 0:
            direction = direction.normalized()
        self.sprinting = bool(held_keys['z'] or held_keys['shift']) and fwd > 0 and self.ads < 0.3
        speed = (9 if self.sprinting else 5.5) * lerp(1, 0.6, self.ads)
        accel = 12 if self.grounded else 3
        self.vel = lerp(self.vel, direction * speed, min(1, dt * accel))
        new = self.world.resolve(self.position + self.vel * dt, PLAYER_RADIUS, self.y)

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
        camera.position = head

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
        self.gun.position = base + sway + Vec3(0, -self.recoil * 0.012, -self.recoil * 0.05)
        self.gun.rotation = Vec3(-self.recoil * 5 * (1 - 0.6 * self.ads), 18 if self.sprinting else 0, 0)
        if self.dot is not None:
            self.dot.visible = self.ads > 0.6
        scoped = w['scope'] and self.ads > 0.85
        self.gun.visible = not scoped                 # dans la lunette, on ne voit plus l'arme
        self.game.hud.scope_visible(scoped)
        self.game.hud.crosshair_visible(self.ads < 0.5)

        trigger = held_keys['left mouse'] or held_keys['p']
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
        elif trigger and self.armed and (w['auto'] or self.trigger_ready) and self.cooldown <= 0 and mouse.locked:
            self.trigger_ready = False               # sniper : relâcher pour tirer à nouveau
            self.shoot()

    def jump(self):
        if self.grounded and not self.dead:
            self.vy = 7.5
            self.grounded = False

    def reload(self):
        if self.reload_t <= 0 and self.mag < self.weapon['mag']:
            self.reload_t = self.weapon['reload']

    def shoot(self):
        if self.mag <= 0:
            self.reload()
            return
        w = self.weapon
        self.mag -= 1
        self.cooldown = w['cooldown']
        self.recoil = min(1.5, self.recoil + (1.2 if w['scope'] else 0.5))
        muzzle_flash(self.muzzle, scale=w['flash'], intensity=w['flash_intensity'], life=w['flash_life'])
        shell_casing(self.eject.world_position, camera.right)
        spread = (w['spread'] + w['move_spread'] * min(1, self.speed_now / 9) + (0.02 if not self.grounded else 0)) \
            * lerp(1, w['ads_spread'], self.ads)
        d = camera.forward + camera.right * random.uniform(-spread, spread) + camera.up * random.uniform(-spread, spread)
        d = d.normalized()
        origin = camera.world_position
        hit = raycast(origin, d, 200, ignore=[self])
        end = hit.world_point if hit.hit else origin + d * 200
        tracer(self.muzzle.world_position, end, rgb(255, 240, 160), thickness=w['tracer'][0], life=w['tracer'][1])
        kick = w['kick'] * lerp(1, 0.6, self.ads)
        self.pivot.rotation_x -= kick
        self.recoil_pitch = min(self.recoil_pitch + kick * 0.8, 6)
        self.rotation_y += random.uniform(-0.15, 0.15)
        if hit.hit:
            ent = hit.entity
            owner = getattr(ent, 'owner', None)
            if isinstance(owner, Enemy):
                zone = ent.zone
                dmg = w['dmg'].get(zone, 25)
                owner.take_hit(dmg, zone, hit.world_point)
                self.game.hud.hitmarker(zone == 'head' or owner.dead)
            elif hasattr(ent, 'target'):
                ent.target.hit()
                impact(hit.world_point, hit.world_normal, rgb(40, 40, 40))
                self.game.hud.hitmarker(False)
            else:
                impact(hit.world_point, hit.world_normal)
        for e in self.game.enemies:        # les ennemis entendent le tir
            if not e.dead and flat_dist(e.position, self.position) < e.hear_radius:
                FXM.later(random.uniform(0.1, 0.5) * e.reaction, e.hear_shot, Vec3(self.position))


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

CONTROLS_LINE = ('E/S/Q/D ou flèches bouger · Z courir · Espace sauter · Clic gauche/P tirer'
                 ' · Clic droit viser · R recharger · G graphismes · Échap pause')
CONTROLS_PAUSE = ('E avancer   ·   S reculer   ·   Q gauche   ·   D droite   ·   flèches : se déplacer\n'
                  'Z courir   ·   Espace sauter   ·   Clic gauche ou P tirer   ·   Clic droit viser\n'
                  'R recharger   ·   G graphismes\n\n'
                  'Échap : reprendre    ·    X : quitter')

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
               position=(-ar + 0.02, 0.49), scale=(1.0, 0.055))
        Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, 0.15), origin=(-0.5, 0),
               position=(-ar + 0.05, -0.455), scale=(0.4, 0.022))
        self.hp_bar = Entity(parent=ui, model='quad', color=rgb(80, 220, 90), origin=(-0.5, 0),
                             position=(-ar + 0.05, -0.455, -0.01), scale=(0.4, 0.022))
        self.hp_text = Text(parent=ui, text='', position=(-ar + 0.05, -0.415), scale=1)
        self.ammo = Text(parent=ui, text='', origin=(0.5, 0), position=(ar - 0.05, -0.445), scale=1.8)
        self.ammo_lbl = Text(parent=ui, text='MUNITIONS', origin=(0.5, 0), position=(ar - 0.05, -0.4), scale=0.75,
                             color=color.rgba(1, 1, 1, 0.6))
        # lunette du sniper : cache noir avec un trou rond et un réticule
        self.scope = Entity(parent=ui, z=0.8, enabled=False)
        Entity(parent=self.scope, model='quad', texture=self.scope_texture(), scale=1)
        side = ar - 0.5 + 0.05
        for sgn in (-1, 1):
            Entity(parent=self.scope, model='quad', color=color.black, scale=(side, 1.02), x=sgn * (0.5 + side / 2 - 0.001))
        self.info = Text(parent=ui, text='', position=(-ar + 0.04, 0.477), scale=1)
        self.msg = Text(parent=ui, text='', origin=(0, 0), y=0.17, scale=2, color=color.white)
        self.sub_msg = Text(parent=ui, text='', origin=(0, 0), y=0.1, scale=1.1, color=color.rgba(1, 1, 1, 0.85))
        self.warn = Text(parent=ui, text='', origin=(0, 0), y=-0.12, scale=1.4, color=rgb(255, 90, 60))
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
        Text(parent=ui, text=CONTROLS_LINE,
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

    def scope_visible(self, v):
        if self.scope.enabled != v:
            self.scope.enabled = v

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
        self.set_text(self.ammo, '...' if p.reload_t > 0 else f"{p.mag} / {p.weapon['mag']}")
        self.set_text(self.ammo_lbl, f"MUNITIONS · {p.weapon['short']}")
        alive = sum(1 for e in g.enemies if not e.dead)
        tier = TIERS[g.tier_index()]['name']
        self.set_text(self.info, f'Vague {g.wave}   ·   {tier} (IA niv. {max(g.wave, 1)})   ·   Ennemis {alive}'
                      f'   ·   Score {g.score}   ·   Éliminations {g.kills}')

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
        self.grenades = []
        self.last_grenade = -99
        self.high_quality = True
        self.choosing = True        # menu de choix d'arme affiché

        global FXM
        FXM = FX()
        Sky(texture='sky_default', color=Color(0.95, 0.97, 1.0, 1))
        self.world = World()
        self.sun = DirectionalLight(shadow_map_resolution=Vec2(SHADOW_RES, SHADOW_RES), color=SUN_COLOR)
        self.sun.look_at(Vec3(0.55, -0.75, 0.4))
        self.shadow_bounds = Entity(model='cube', scale=(ARENA * 2 + 4, 9, ARENA * 2 + 4), y=4, visible=False)
        invoke(self.fit_shadows, delay=0.1)

        self.player = Player(self)
        self.hud = HUD(self)
        for x in (-6, -3, 0, 3, 6):
            Target(self, Vec3(x, 0, -35))
        self.set_quality(True)
        self.show_weapon_menu()

    # -- menu de choix d'arme ------------------------------------------------
    def show_weapon_menu(self):
        mouse.locked = False
        ui = camera.ui
        self.menu = Entity(parent=ui, z=-0.5)
        Entity(parent=self.menu, model=Quad(radius=0.03), color=color.rgba(0, 0, 0, 0.72), scale=(1.1, 0.62), z=0.01)
        Text(parent=self.menu, text='CHOISISSEZ VOTRE ARME', origin=(0, 0), y=0.24, scale=2)
        choices = [
            ('rifle', "1  —  Fusil d'assaut",
             'Tir automatique · 30 balles · viseur point rouge'),
            ('sniper', '2  —  Sniper',
             'Un tir par clic · gros dégâts · 5 balles · lunette zoom x2'),
        ]
        for k, (key, title, desc) in enumerate(choices):
            y = 0.07 - k * 0.19
            b = Button(parent=self.menu, text='', scale=(0.9, 0.15), y=y, radius=0.08,
                       color=color.rgba(0.2, 0.25, 0.3, 0.95), highlight_color=color.rgba(0.3, 0.45, 0.55, 1))
            b.on_click = (lambda k=key: self.choose_weapon(k))
            Text(parent=self.menu, text=title, origin=(0, 0), y=y + 0.025, scale=1.5, z=-0.02)
            Text(parent=self.menu, text=desc, origin=(0, 0), y=y - 0.035, scale=0.95, z=-0.02,
                 color=color.rgba(1, 1, 1, 0.75))
        Text(parent=self.menu, text='Cliquez sur une arme ou appuyez sur 1 / 2', origin=(0, 0), y=-0.26,
             scale=0.9, color=color.rgba(1, 1, 1, 0.6))

    def choose_weapon(self, key):
        if not self.choosing:
            return
        self.choosing = False
        destroy(self.menu)
        self.player.set_weapon(key)
        mouse.locked = True
        self.hud.message('Éliminez les ennemis !', 4,
                         f"Arme : {WEAPONS[key]['name']} — les cibles devant vous servent à s'entraîner")
        invoke(self.next_wave, delay=2)

    def fit_shadows(self):
        """La carte d'ombres couvre uniquement l'arène (ombres plus nettes)."""
        self.shadow_bounds.visible = True
        self.sun.update_bounds(self.shadow_bounds)
        self.shadow_bounds.visible = False

    def set_quality(self, high):
        self.high_quality = high
        try:
            if high:
                camera.shader = POST
            elif camera.shader is not None:
                camera.shader = None
                camera.filter_quad = None    # sinon Ursina plante au redimensionnement de la fenêtre
        except Exception as ex:      # carte graphique incompatible : on reste sans post-traitement
            print('Post-traitement indisponible :', ex)
        camera.clip_plane_near = 0.05    # Ursina le remet à 1 quand on change le shader de caméra
        for g in self.world.grass:
            g.enabled = high

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
        self.wave += 1
        sk = self.skill()
        n = min(3 + self.wave, 14)
        tier = self.tier_index()
        for s in self.spawn_points(n):
            e = Enemy(self, s, skill=sk, tier=tier)
            e.rotation_y = random.uniform(0, 360)
            self.enemies.append(e)
        extra = ['', 'Ils se couvrent mutuellement', 'Ils lancent des grenades',
                 'Ils vous prennent en tenaille', 'Ils esquivent et visent plus vite']
        detail = extra[min(self.wave - 1, len(extra) - 1)]
        self.hud.message(f'Vague {self.wave}', 3,
                         f'{n} ennemis · {TIERS[tier]["name"]} · IA niveau {self.wave}'
                         + (f' — {detail}' if detail else ''))

    def on_enemy_killed(self, enemy, headshot):
        self.kills += 1
        bonus = self.wave * 10
        if headshot:
            self.add_score(150 + bonus, f'Tir à la tête ! +{150 + bonus}')
        else:
            self.add_score(100 + bonus, f'Ennemi éliminé +{100 + bonus}')
        if all(e.dead for e in self.enemies):
            self.hud.message('Vague terminée !', 3, 'Santé restaurée — la prochaine sera plus coriace')
            self.player.hp = min(100, self.player.hp + 50)
            invoke(self.cleanup_and_next, delay=4.5)

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
                         f'Score : {self.score}   ·   Vague : {self.wave}\n\nEntrée pour recommencer')
        self.player.pivot.animate_position((0, 0.3, 0), duration=0.6)
        self.player.pivot.animate_rotation_z(40, duration=0.6)

    def restart(self):
        for e in self.enemies:
            if not e.dead:
                e.dead = True
                e.release_cover()
                destroy(e)
        self.enemies = []
        FXM.clear()
        for gr in list(self.grenades):
            destroy(gr)
        self.grenades = []
        for c in self.world.covers:
            c.owner = None
        p = self.player
        p.position = Vec3(0, 0, -40)
        p.rotation_y = 0
        p.pivot.position = (0, 1.65, 0)
        p.pivot.rotation = (0, 0, 0)
        p.hp, p.dead, p.mag, p.reload_t, p.vel, p.vy = 100, False, p.weapon['mag'], 0, Vec3(0, 0, 0), 0
        p.armed = False
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

    def update(self):
        if not self.paused:
            self.t += time.dt
        self.hud.update()

    def input(self, key):
        if self.choosing:
            if key in ('1', '2'):
                self.choose_weapon('rifle' if key == '1' else 'sniper')
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
        elif key == 'space':
            self.player.jump()
        elif key == 'r':
            self.player.reload()
        elif key == 'enter' and self.over:
            self.restart()
        elif key == 'left mouse down' and not mouse.locked:
            mouse.locked = True


if __name__ == '__main__':
    app = Ursina(title='FPS Ursina', borderless=False, development_mode=False, vsync=VSYNC)
    window.color = FOG_COLOR
    window.fps_counter.enabled = False
    window.exit_button.visible = False
    game = Game()
    app.run()
