# -*- coding: utf-8 -*-
"""
rooms.py — Construction visuelle de l'intérieur : sols, murs, plafonds,
portes coulissantes, grilles d'aération, hublots et baies vitrées, tuyaux
et câbles au plafond, luminaires, props de chaque type de salle, cadavres
et traces de sang.

Toute la géométrie statique d'une salle (ou d'un bloc de couloirs) est
fusionnée en quelques meshes (voir geometry.MeshBuilder). Les salles
éloignées sont désactivées (cull).
"""
import math
import random

from panda3d.core import TransparencyAttrib
from ursina import Entity, color, Vec3

import config as C
import textures
import loot
import story
from geometry import MeshBuilder, jitter_color
from generator import SOLID, ROOM, CORR, VENT, DIRS, Blocker
from lighting import Fixture, mark_emissive

# couleurs (murs, sol, plafond) par type de zone
PALETTE = {
    "hangar":  ((.46, .47, .49), (.36, .36, .37), (.25, .25, .27)),
    "engine":  ((.52, .44, .37), (.33, .31, .3), (.28, .25, .23)),
    "medbay":  ((.74, .79, .8), (.6, .65, .66), (.55, .6, .62)),
    "crew":    ((.6, .55, .48), (.42, .36, .3), (.45, .42, .38)),
    "command": ((.4, .46, .56), (.3, .33, .38), (.3, .34, .4)),
    "mess":    ((.6, .57, .5), (.45, .42, .38), (.45, .43, .4)),
    "storage": ((.46, .44, .4), (.36, .35, .33), (.3, .3, .3)),
    "corr":    ((.44, .45, .47), (.38, .38, .4), (.3, .3, .32)),
    "vent":    ((.3, .3, .32), (.26, .26, .27), (.24, .24, .25)),
}


class Placer:
    """Repère local d'un prop posé contre un mur : +z local = vers l'intérieur de la salle."""

    def __init__(self, x, z, fx, fz):
        self.x, self.z = x, z
        self.fx, self.fz = fx, fz
        self.rx, self.rz = fz, -fx
        self.yaw = math.degrees(math.atan2(fx, fz))
        self.facing = (fx, fz)
        self.along_x = abs(fx) > .5

    def pt(self, lx, ly, lz):
        return (self.x + self.rx * lx + self.fx * lz, ly, self.z + self.rz * lx + self.fz * lz)

    def size(self, s):
        return (s[2], s[1], s[0]) if self.along_x else s

    def box(self, mb, lc, ls, col, faces='all'):
        mb.box(self.pt(*lc), self.size(ls), col, faces)

    def cyl(self, mb, lc, r, h, col, axis='y', seg=10):
        if axis == 'x':
            axis = 'z' if self.along_x else 'x'
        elif axis == 'z':
            axis = 'x' if self.along_x else 'z'
        mb.cylinder(self.pt(*lc), r, h, col, seg, axis)

    def aabb(self, lc, ls):
        cx, _, cz = self.pt(lc[0], 0, lc[1])
        sx, _, sz = self.size((ls[0], 0, ls[1]))
        return cx - sx / 2, cx + sx / 2, cz - sz / 2, cz + sz / 2


class Group:
    """Un groupe de rendu (une salle ou un bloc de couloirs) et ses meshes."""
    # emissive : voyants / écrans rouges alimentés ; screen : écrans ; reactor : anneaux du réacteur ;
    # battery : voyants sur batterie de secours (clignotent même sans courant) ;
    # strip : bandes de secours au sol (option config.EMERGENCY_STRIPS)
    KINDS = ("struct", "floor", "hazard", "decal", "smear", "glass", "emissive", "screen", "reactor", "battery",
             "strip", "claw")
    POWERED = {"emissive": "emissive", "screen": "screen", "reactor": "reactor", "battery": "battery"}

    def __init__(self, name, parent, bounds, is_room=False):
        self.name = name
        self.root = Entity(parent=parent, name=name)
        self.b = {k: MeshBuilder(uv_scale=2.0 if k != "hazard" else 1.0) for k in self.KINDS}
        self.bounds = bounds       # (x0, x1, z0, z1)
        self.enabled = True
        self.is_room = is_room
        self.claw_node = None      # traces de griffes (cachées pendant la révélation)

    def build(self, power=None):
        tex = {"hazard": textures.get('hazard'), "decal": textures.get('blood'),
               "smear": textures.get('smear'), "screen": textures.get('screen'), "claw": textures.get('claws')}
        # matériaux complets (albédo + normal map + brillance) pour les surfaces éclairées
        mats = {"struct": ("panel", None), "floor": ("floor", None), "hazard": ("painted", tex["hazard"])}
        for k, mb in self.b.items():
            if mb.is_empty():
                continue
            if k in mats:
                mat, alb = mats[k]
                e = mb.build(parent=self.root, texture=alb, material=mat, name=f"{self.name}_{k}")
            else:
                e = mb.build(parent=self.root, texture=tex.get(k), name=f"{self.name}_{k}",
                             tangents=False)
            if k == "claw":
                self.claw_node = e
            if k in ("decal", "smear", "glass", "claw"):
                e.setTransparency(TransparencyAttrib.MAlpha)
                e.setDepthWrite(False)
                e.setBin('transparent', 10)
                if k != "glass":
                    e.setDepthOffset(2)
            if k in ("emissive", "screen", "glass", "reactor", "battery", "strip"):
                mark_emissive(e)          # émissif volontaire (ignoré par l'audit « unlit »)
            if k == "glass":
                e.double_sided = True
            # écrans, voyants et réacteur : allumés / éteints par le gestionnaire de courant
            if power is not None and k in self.POWERED:
                x0, x1, z0, z1 = self.bounds
                power.register_emissive(e, self.POWERED[k], (x0 + x1) / 2, (z0 + z1) / 2)
        self.b = None

    def distance_to(self, x, z):
        x0, x1, z0, z1 = self.bounds
        dx = max(x0 - x, 0, x - x1)
        dz = max(z0 - z, 0, z - z1)
        return math.hypot(dx, dz)


# ============================================================================
class DoorInteract(loot.Interactable):
    """
    Interaction avec une porte. Avec le courant : ouvrir / fermer. Sans
    courant : les portes entrouvertes se franchissent directement, les portes
    fermées se forcent (maintenir le bouton, très bruyant), certaines sont
    bloquées (passer par les conduits) et la salle de commandement est
    verrouillée électriquement.
    """
    radius = 2.2

    def __init__(self, level, door):
        self.door = door
        self.pos = (door.pos[0], 1.2, door.pos[1])
        self._grind = 0.0
        level.add_interactable(self, door.pos[0], door.pos[1])

    @property
    def hold_time(self):
        d = self.door
        return C.DOOR_FORCE_TIME if (d.unpowered and not d.locked and d.jam == "closed") else 0.0

    def prompt(self, game):
        d = self.door
        if d.locked:
            return "Porte verrouillée (pas de courant)"
        if d.unpowered:
            if d.jam == "ajar" or d.open_amount > .5:
                return None
            if d.jam == "stuck":
                return "Porte bloquée"
            return "Forcer la porte (maintenir)"
        return "Fermer la porte" if d.target > 0 else "Ouvrir la porte"

    def on_hold(self, game, dt):
        """Pendant qu'on force : grincements métalliques bruyants."""
        self._grind -= dt
        if self._grind <= 0:
            self._grind = .55
            game.audio.play_at("door_force", self.pos, .85, random.uniform(.85, 1.1))
            game.noise(self.pos, C.NOISE_DOOR_FORCE * .6, "door")
            game.inp.rumble(.35, .15, 200)
            game.shake(.08)

    def interact(self, game):
        d = self.door
        if d.locked:
            game.audio.play_at("beep", self.pos, .6, .7)
            game.hud.message("Verrouillage électrique. Rétablis le courant dans la salle des machines.",
                             color.orange)
            return
        if d.unpowered:
            if d.jam == "stuck":
                game.audio.play_at("metal_bang", self.pos, .5, 1.3)
                game.hud.message("Elle ne bouge pas d'un millimètre. Passe par les conduits d'aération.",
                                 color.orange)
                return
            if d.jam == "closed":
                # porte forcée : elle reste entrouverte
                d.force_ajar(C.DOOR_AJAR_OPENING)
                game.audio.play_at("door_force_open", self.pos, 1.0)
                game.noise(self.pos, C.NOISE_DOOR_FORCE, "door")
                game.inp.rumble(.8, .5, 350)
                game.hud.message("Porte forcée... tout le vaisseau a dû l'entendre.", color.rgb(.8, .6, .5))
            return
        if d.target > 0:
            d.close()
        else:
            d.open()
            game.noise((self.pos[0], 1, self.pos[2]), C.NOISE_DOOR, "door")


class GrilleInteract(loot.Interactable):
    radius = 1.8

    def __init__(self, level, grille):
        self.grille = grille
        x, z = grille.room_side_point(0.3)
        self.pos = (x, 0.5, z)
        level.add_interactable(self, x, z)

    def prompt(self, game):
        if self.grille.opened:
            return None
        if self.grille.locked:
            return "Grille scellée (verrou électrique)"
        return "Ouvrir la grille d'aération"

    def interact(self, game):
        if self.grille.locked:
            game.audio.play_at("beep", self.pos, .5, .7)
            game.hud.message("Scellée électriquement. Il faut rétablir le courant.", color.orange)
            return
        self.grille.set_open(True)
        game.audio.play_at("vent_bang", self.pos, .6)
        game.noise(self.pos, 4.0, "grille")
        game.hud.message("Grille ouverte : accroupis-toi pour entrer (Ctrl / Rond)")


# ============================================================================
class LevelBuilder:
    def __init__(self, level, lights, parent, seed):
        self.level = level
        self.lights = lights
        self.parent = parent
        self.rng = random.Random(seed * 13 + 7)
        self.groups = {}           # clé -> Group
        self.cell_group = {}
        self.door_visuals = []
        self.grille_visuals = []
        self.animated = []         # objets animés (casiers)
        self.updatables = []       # objets avec update (disque dur...)
        self.forcefield = None
        self.loot_dir = loot.LootDirector(self.rng)
        self.spark_points = []     # câbles arrachés (étincelles)
        self.power_panel = None    # tableau électrique principal (salle des machines)
        self.fuses = []            # fusibles à retrouver
        self.seed = seed
        self.spots = {}            # salle -> {type d'emplacement : [(x, y, z, lacet, vertical)]} pour les documents
        self.crew_corpses = {}     # membre d'équipage -> corps (story.CREW)
        self.claw_nodes = []
        self.doc_present = set()
        self.doc_pickups = {}
        self.doc_deferred = []     # documents placés plus tard (près du casier du screamer)
        self.fridge_placer = None
        self.dock_placer = None
        self.hdd = None
        self.pad_center = None
        self.reactor_pos = None
        self.command_center = None
        self.time = 0.0
        self.cull_timer = 0.0

    # ------------------------------------------------------------------
    def group_for(self, i, j):
        L = self.level
        r = L.room_of[i][j]
        if r >= 0:
            key = ("room", r)
            if key not in self.groups:
                room = L.rooms[r]
                self.groups[key] = Group(f"room_{r}_{room.type}", self.parent, room.world_bounds(), True)
            return self.groups[key]
        ci, cj = i // C.CHUNK_SIZE, j // C.CHUNK_SIZE
        key = ("chunk", ci, cj)
        if key not in self.groups:
            s = C.CHUNK_SIZE * C.CELL
            self.groups[key] = Group(f"chunk_{ci}_{cj}", self.parent, (ci * s, (ci + 1) * s, cj * s, (cj + 1) * s))
        return self.groups[key]

    def zone_palette(self, i, j):
        L = self.level
        k = L.kind[i][j]
        if k == ROOM:
            return PALETTE[L.rooms[L.room_of[i][j]].type]
        return PALETTE["vent" if k == VENT else "corr"]

    # ------------------------------------------------------------------
    def build(self):
        L = self.level
        for i in range(L.W):
            for j in range(L.H):
                if L.kind[i][j] != SOLID:
                    self._build_cell(i, j)
        for door in L.doors.values():
            self._build_door(door)
        for g in L.grilles.values():
            self._build_grille(g)
        for i in range(L.W):
            for j in range(L.H):
                if L.kind[i][j] == CORR:
                    self._decorate_corridor(i, j)
        for room in L.rooms:
            getattr(self, "_room_" + room.type)(room)
            self._room_lights(room)
            self._room_clutter(room)
        self._place_caches()
        self._place_crew()
        self._place_fuses()
        self._place_documents()
        self.loot_dir.finalize()
        for g in self.groups.values():
            g.build(self.lights.power)
            if g.claw_node is not None:
                self.claw_nodes.append(g.claw_node)
        # retards d'allumage (propagation depuis la salle des machines) et lampes cassées
        self.lights.power.finalize(L, L.room("engine"), random.Random(self.rng.random()))

    # ------------------------------------------------------------------
    # CASES : sol, plafond, murs
    # ------------------------------------------------------------------
    def _build_cell(self, i, j):
        L = self.level
        g = self.group_for(i, j)
        Cc = C.CELL
        x0, z0 = i * Cc, j * Cc
        x1, z1 = x0 + Cc, z0 + Cc
        h = L.ceiling(i, j)
        wall_c, floor_c, ceil_c = self.zone_palette(i, j)
        rng = self.rng
        fc = jitter_color(floor_c, .08, rng)
        g.b["floor"].box(((x0 + x1) / 2, 0, (z0 + z1) / 2), (Cc, 0, Cc), fc, faces='t', shade=False)
        g.b["struct"].box(((x0 + x1) / 2, h, (z0 + z1) / 2), (Cc, 0, Cc), jitter_color(ceil_c, .05, rng), faces='b',
                          shade=False)
        # murs sur chaque arête non ouverte
        for dx, dz in DIRS:
            ni, nj = i + dx, j + dz
            st = L.edge_state(i, j, ni, nj)
            if st == "open":
                continue
            self._build_edge_face(g, i, j, dx, dz, st, h, wall_c)

    def _wall_quad(self, g, i, j, dx, dz, s0, s1, y0, y1, col, key="struct"):
        """Face de mur sur la ligne de l'arête, tournée vers la case (i, j)."""
        Cc = C.CELL
        if y1 <= y0 or s1 <= s0:
            return
        if dx != 0:
            line = (i + (1 if dx > 0 else 0)) * Cc
            face = 'w' if dx > 0 else 'e'
            g.b[key].box((line, (y0 + y1) / 2, (s0 + s1) / 2), (0, y1 - y0, s1 - s0), col, faces=face)
        else:
            line = (j + (1 if dz > 0 else 0)) * Cc
            face = 's' if dz > 0 else 'n'
            g.b[key].box(((s0 + s1) / 2, (y0 + y1) / 2, line), (s1 - s0, y1 - y0, 0), col, faces=face)

    def _trim(self, g, i, j, dx, dz, s0, s1, y0, y1, depth, col, key="struct"):
        """Petite boîte collée au mur côté case (plinthes, cadres, nervures)."""
        Cc = C.CELL
        # profondeur négative = vers l'extérieur de la case (joues de fenêtre)
        if dx != 0:
            line = (i + (1 if dx > 0 else 0)) * Cc
            cx = line - dx * depth / 2
            g.b[key].box((cx, (y0 + y1) / 2, (s0 + s1) / 2), (abs(depth), y1 - y0, s1 - s0), col)
        else:
            line = (j + (1 if dz > 0 else 0)) * Cc
            cz = line - dz * depth / 2
            g.b[key].box(((s0 + s1) / 2, (y0 + y1) / 2, cz), (s1 - s0, y1 - y0, abs(depth)), col)

    def _build_edge_face(self, g, i, j, dx, dz, st, h, wall_c):
        L = self.level
        Cc = C.CELL
        rng = self.rng
        s0 = (j if dx != 0 else i) * Cc
        s1 = s0 + Cc
        m = (s0 + s1) / 2
        wc = jitter_color(wall_c, .05, rng)
        dark = (wall_c[0] * .45, wall_c[1] * .45, wall_c[2] * .45)
        is_vent = L.kind[i][j] == VENT
        if st == "wall":
            self._wall_quad(g, i, j, dx, dz, s0, s1, 0, h, wc)
            if not is_vent:
                self._trim(g, i, j, dx, dz, s0, s1, 0, .16, .05, dark)                 # plinthe
                if h > 2.5:
                    self._trim(g, i, j, dx, dz, s0, s1, h - .22, h - .12, .06, dark)   # corniche
                if L.kind[i][j] == CORR or rng.random() < .3:
                    self._trim(g, i, j, dx, dz, s0, s0 + .22, 0, h, .1, dark)          # nervure
        elif st == "door":
            hw = C.DOOR_WIDTH / 2
            self._wall_quad(g, i, j, dx, dz, s0, m - hw, 0, h, wc)
            self._wall_quad(g, i, j, dx, dz, m + hw, s1, 0, h, wc)
            self._wall_quad(g, i, j, dx, dz, m - hw, m + hw, C.DOOR_HEIGHT, h, wc)
            # cadre de porte
            fc = (.18, .18, .2)
            self._trim(g, i, j, dx, dz, m - hw - .18, m - hw, 0, C.DOOR_HEIGHT + .18, .16, fc)
            self._trim(g, i, j, dx, dz, m + hw, m + hw + .18, 0, C.DOOR_HEIGHT + .18, .16, fc)
            self._trim(g, i, j, dx, dz, m - hw, m + hw, C.DOOR_HEIGHT, C.DOOR_HEIGHT + .18, .16, fc)
            # bandes de danger au sol
            self._floor_strip(g, i, j, dx, dz, m - hw, m + hw)
        elif st == "grille":
            self._wall_quad(g, i, j, dx, dz, s0, s1, C.VENT_HEIGHT, h, wc)
            if not is_vent:
                self._trim(g, i, j, dx, dz, s0 + .15, s1 - .15, C.VENT_HEIGHT, C.VENT_HEIGHT + .08, .08, dark)
        elif st == "porthole":
            self._window(g, i, j, dx, dz, s0, s1, h, wc, dark, big=False)
        elif st == "bay":
            self._window(g, i, j, dx, dz, s0, s1, h, wc, dark, big=True)
        elif st == "opening":
            oh = C.HANGAR_OPENING_HEIGHT
            self._wall_quad(g, i, j, dx, dz, s0, s1, oh, h, wc)
            self._trim(g, i, j, dx, dz, s0, s1, oh - .4, oh, .3, (.2, .2, .2), key="hazard")
            self._floor_strip(g, i, j, dx, dz, s0, s1, depth=.8)
        else:
            self._wall_quad(g, i, j, dx, dz, s0, s1, 0, h, wc)

    def _floor_strip(self, g, i, j, dx, dz, s0, s1, depth=.35):
        Cc = C.CELL
        if dx != 0:
            line = (i + (1 if dx > 0 else 0)) * Cc
            cx = line - dx * depth / 2
            g.b["hazard"].box((cx, .006, (s0 + s1) / 2), (depth, 0, s1 - s0), (1, 1, 1), faces='t', shade=False)
        else:
            line = (j + (1 if dz > 0 else 0)) * Cc
            cz = line - dz * depth / 2
            g.b["hazard"].box(((s0 + s1) / 2, .006, cz), (s1 - s0, 0, depth), (1, 1, 1), faces='t', shade=False)

    def _window(self, g, i, j, dx, dz, s0, s1, h, wc, dark, big):
        """Hublot (petit) ou baie vitrée (grande) donnant sur l'espace."""
        Cc = C.CELL
        m = (s0 + s1) / 2
        if big:
            wy0, wy1 = .55, h - .35
            hs0, hs1 = s0 + .08, s1 - .08
        else:
            wy0, wy1 = 1.1, 2.05
            hs0, hs1 = m - .5, m + .5
        self._wall_quad(g, i, j, dx, dz, s0, s1, 0, wy0, wc)
        self._wall_quad(g, i, j, dx, dz, s0, s1, wy1, h, wc)
        self._wall_quad(g, i, j, dx, dz, s0, hs0, wy0, wy1, wc)
        self._wall_quad(g, i, j, dx, dz, hs1, s1, wy0, wy1, wc)
        fc = (.15, .15, .17)
        d = .14
        self._trim(g, i, j, dx, dz, hs0 - .1, hs0, wy0, wy1, d, fc)
        self._trim(g, i, j, dx, dz, hs1, hs1 + .1, wy0, wy1, d, fc)
        self._trim(g, i, j, dx, dz, hs0 - .1, hs1 + .1, wy0 - .1, wy0, d + .1, fc)
        self._trim(g, i, j, dx, dz, hs0 - .1, hs1 + .1, wy1, wy1 + .1, d, fc)
        # vitre légèrement en retrait vers l'extérieur
        glass = (.35, .5, .6, .12)
        if dx != 0:
            line = (i + (1 if dx > 0 else 0)) * Cc + dx * .05
            g.b["glass"].box((line, (wy0 + wy1) / 2, (hs0 + hs1) / 2), (0, wy1 - wy0, hs1 - hs0), glass,
                             faces='w' if dx > 0 else 'e', shade=False)
        else:
            line = (j + (1 if dz > 0 else 0)) * Cc + dz * .05
            g.b["glass"].box(((hs0 + hs1) / 2, (wy0 + wy1) / 2, line), (hs1 - hs0, wy1 - wy0, 0), glass,
                             faces='s' if dz > 0 else 'n', shade=False)
        # le vide extérieur derrière la vitre doit être noir/étoilé : on ferme le
        # cadre avec des joues pour ne pas voir l'épaisseur du mur
        self._trim(g, i, j, dx, dz, hs0 - .02, hs0, wy0, wy1, -.25, dark)
        self._trim(g, i, j, dx, dz, hs1, hs1 + .02, wy0, wy1, -.25, dark)
        # très faible lueur froide des étoiles : n'éclaire que quelques mètres autour de la fenêtre
        cx, cz = self.level.cell_center(i, j)
        off = Cc / 2 - .5
        self.lights.add_fixture(Fixture((cx + dx * off, (wy0 + wy1) / 2, cz + dz * off), C.STARLIGHT_COLOR,
                                        C.STARLIGHT_RADIUS * (1.25 if big else 1.0), "star", None,
                                        C.STARLIGHT_INTENSITY * (1.0 if big else .5), powered=False, kind="star"))

    # ------------------------------------------------------------------
    # PORTES ET GRILLES
    # ------------------------------------------------------------------
    def _build_door(self, door):
        L = self.level
        g = self.group_for(*door.room_cell)
        hw = C.DOOR_WIDTH / 2
        panels = []
        for side in (-1, 1):
            if door.axis == "x":
                pos = (door.line, C.DOOR_HEIGHT / 2, door.mid + side * hw / 2)
                sc = (.1, C.DOOR_HEIGHT, hw)
            else:
                pos = (door.mid + side * hw / 2, C.DOOR_HEIGHT / 2, door.line)
                sc = (hw, C.DOOR_HEIGHT, .1)
            p = Entity(parent=g.root, model='cube', texture=textures.get('panel'), texture_scale=(.5, 1),
                       color=color.rgb(.42, .42, .4), position=pos, scale=sc)
            # bande jaune de sécurité
            Entity(parent=p, model='cube', color=color.rgb(.6, .48, .08), scale=(1.02, .035, 1.02), y=.12)
            panels.append((p, Vec3(*pos), side))
        door.panels = panels
        # voyants au-dessus de la porte (des deux côtés)
        lights = []
        for s in (-1, 1):
            if door.axis == "x":
                lp = (door.line + s * .2, C.DOOR_HEIGHT + .3, door.mid)
            else:
                lp = (door.mid, C.DOOR_HEIGHT + .3, door.line + s * .2)
            e = Entity(parent=g.root, model='cube', color=color.rgb(.3, .3, .32), scale=.1, position=lp)
            e.setPythonTag("emissive", True)     # voyant : émissif seulement quand il est allumé
            lights.append(e)
        door.status_light = lights
        door.light_state = None
        self.door_visuals.append(door)
        DoorInteract(L, door)

    def _build_grille(self, grille):
        L = self.level
        g = self.group_for(*grille.room_cell)
        Cc = C.CELL
        ri, rj = grille.room_cell
        vi, vj = grille.vent_cell
        dx, dz = vi - ri, vj - rj
        w = Cc - .3
        hgt = C.VENT_HEIGHT - .05
        # charnière en haut de la grille
        if grille.axis == "x":
            hp = (grille.line - dx * .03, C.VENT_HEIGHT, grille.mid)
        else:
            hp = (grille.mid, C.VENT_HEIGHT, grille.line - dz * .03)
        pivot = Entity(parent=g.root, position=hp)
        mb = MeshBuilder()
        bar_c = (.2, .21, .22)
        n = 9
        for k in range(n):
            t = -w / 2 + w * (k + .5) / n
            if grille.axis == "x":
                mb.box((0, -hgt / 2, t), (.04, hgt, .05), bar_c)
            else:
                mb.box((t, -hgt / 2, 0), (.05, hgt, .04), bar_c)
        for y in (-.04, -hgt + .04, -hgt / 2):
            if grille.axis == "x":
                mb.box((0, y, 0), (.06, .06, w), bar_c)
            else:
                mb.box((0, y, 0), (w, .06, .06), bar_c)
        grille.entity = mb.build(parent=pivot, material='gunmetal')
        grille.pivot = pivot
        grille.open_dir = (-dx, -dz)
        self.grille_visuals.append(grille)
        GrilleInteract(L, grille)
        if self.rng.random() < .5:
            self._wall_claw(g, *grille.room_cell)       # griffures autour des grilles
        # du noir derrière la grille pour suggérer la profondeur du conduit
        if self.rng.random() < .25:
            grille.set_open(True)   # certaines grilles ont été arrachées

    # ------------------------------------------------------------------
    # COULOIRS : tuyaux, câbles, lumières, désordre
    # ------------------------------------------------------------------
    def _decorate_corridor(self, i, j):
        L = self.level
        g = self.group_for(i, j)
        rng = self.rng
        Cc = C.CELL
        h = C.CORRIDOR_HEIGHT
        cx, cz = L.cell_center(i, j)
        ox = any(L.edge_state(i, j, i + d, j) in ("open", "door") for d in (-1, 1))
        oz = any(L.edge_state(i, j, i, j + d) in ("open", "door") for d in (-1, 1))
        mb = g.b["struct"]
        pipe_cols = [(.45, .3, .2), (.35, .36, .38), (.55, .5, .2), (.25, .3, .28)]
        if ox and not oz:
            axis = 'x'
        elif oz and not ox:
            axis = 'z'
        else:
            axis = None
        if axis:
            for k, off in enumerate((-.75, -.55, .6, .82)):
                if k == 3 and rng.random() < .5:
                    continue
                r = .06 + .03 * (k % 2)
                col = pipe_cols[(i * 3 + j + k) % len(pipe_cols)]
                if axis == 'x':
                    mb.cylinder((cx, h - .18 - .06 * (k % 2), cz + off), r, Cc, col, 8, 'x', caps=False)
                else:
                    mb.cylinder((cx + off, h - .18 - .06 * (k % 2), cz), r, Cc, col, 8, 'z', caps=False)
            # câbles noirs qui pendent un peu au milieu
            for off in (-.2, .1):
                sag = rng.uniform(.05, .18)
                for s in range(3):
                    t0 = -Cc / 2 + s * Cc / 3
                    y = h - .08 - sag * math.sin(math.pi * (s + .5) / 3)
                    if axis == 'x':
                        mb.box((cx + t0 + Cc / 6, y, cz + off), (Cc / 3 + .02, .035, .035), (.05, .05, .05))
                    else:
                        mb.box((cx + off, y, cz + t0 + Cc / 6), (.035, .035, Cc / 3 + .02), (.05, .05, .05))
            # support de tuyauterie
            if (i + j) % 2 == 0:
                if axis == 'x':
                    mb.box((cx - Cc / 2 + .1, h - .3, cz), (.08, .06, Cc - .1), (.2, .2, .22))
                else:
                    mb.box((cx, h - .3, cz - Cc / 2 + .1), (Cc - .1, .06, .08), (.2, .2, .22))
            # câble arraché qui pend
            if rng.random() < .06:
                ln = rng.uniform(.8, 1.6)
                px, pz = cx + rng.uniform(-.4, .4), cz + rng.uniform(-.4, .4)
                mb.box((px, h - ln / 2, pz), (.03, ln, .03), (.04, .04, .04))
                L.spawn_points.append((cx, cz, "spark"))
                self.spark_points.append((px, h - ln, pz))
        # lumières de couloir (néons froids ; lesquels resteront cassés est tiré par le gestionnaire de courant)
        roll = rng.random()
        if (i + 2 * j) % 3 == 0:
            mode = "red" if roll < .13 else "steady"
            col = (1, .12, .06) if mode == "red" else C.LIGHT_COLOR_COLD
            ln = 1.1
            if axis == 'z':
                sc = (.14, .05, ln)
            else:
                sc = (ln, .05, .14)
            e = Entity(parent=g.root, model='cube', color=color.rgb(.3, .3, .32), scale=sc,
                       position=(cx, h - .04, cz))
            mark_emissive(e, lit_off=False)
            self.lights.add_fixture(Fixture((cx, h - .35, cz), col, 7.5, mode, e,
                                            intensity=.9 if mode != "red" else .7))
        elif rng.random() < .12:
            # gyrophare d'alarme mural (alimenté ; ne s'allume qu'en mode horreur)
            e = Entity(parent=g.root, model='sphere', color=color.rgb(.2, .02, .02), scale=(.18, .12, .18),
                       position=(cx, h - .08, cz))
            mark_emissive(e, lit_off=False)
            self.lights.add_fixture(Fixture((cx, h - .3, cz), (1, .05, .02), 9, "alarm", e, 1.2, kind="alarm"))
        # bandes d'éclairage de secours au ras du sol (option, sur batterie)
        if C.EMERGENCY_STRIPS:
            ec = C.EMERGENCY_COLOR
            for ddx, ddz in DIRS:
                if L.edge_state(i, j, i + ddx, j + ddz) != "wall":
                    continue
                if ddx != 0:
                    g.b["strip"].box((cx + ddx * (Cc / 2 - .04), .06, cz), (.02, .025, Cc * .9),
                                     (ec[0] * .7, ec[1] * .7, ec[2] * .7))
                else:
                    g.b["strip"].box((cx, .06, cz + ddz * (Cc / 2 - .04)), (Cc * .9, .025, .02),
                                     (ec[0] * .7, ec[1] * .7, ec[2] * .7))
            if (i + j) % 3 == 1:
                self.lights.add_fixture(Fixture((cx, .3, cz), ec, 3.0, "emergency", None, C.EMERGENCY_INTENSITY,
                                                powered=False, kind="emergency"))
        # débris au sol
        if rng.random() < .18:
            s = rng.uniform(.2, .45)
            px, pz = cx + rng.uniform(-.6, .6), cz + rng.uniform(-.6, .6)
            mb.box_rot((px, s / 2, pz), (s, s, s * 1.3), rng.uniform(0, 90), jitter_color((.3, .3, .28), .2, rng))
        if rng.random() < .15:
            g.b["decal"].decal((cx + rng.uniform(-.8, .8), .011, cz + rng.uniform(-.8, .8)), rng.uniform(.5, 1.4),
                               rng.uniform(0, 360), (1, 1, 1, 1))
        if rng.random() < .12:
            self._wall_smear(g, i, j)
        if rng.random() < .07:
            self._wall_claw(g, i, j)

    def _wall_claw(self, g, i, j):
        """Traces de griffes sur un mur (elles n'existent que dans la tête de ceux qui les voient)."""
        L = self.level
        rng = self.rng
        walls = [(dx, dz) for dx, dz in DIRS if L.edge_state(i, j, i + dx, j + dz) == "wall"]
        if not walls:
            return
        dx, dz = rng.choice(walls)
        cx, cz = L.cell_center(i, j)
        Cc = C.CELL
        off = rng.uniform(-.6, .6)
        y = rng.uniform(.6, 1.9)
        if dx != 0:
            p = (cx + dx * (Cc / 2 - .012), y, cz + off)
        else:
            p = (cx + off, y, cz + dz * (Cc / 2 - .012))
        g.b["claw"].decal(p, rng.uniform(.5, .9), rng.uniform(-35, 35), (1, 1, 1, 1), normal=(-dx, 0, -dz))

    def _wall_smear(self, g, i, j, col=(1, 1, 1, 1)):
        L = self.level
        rng = self.rng
        walls = [(dx, dz) for dx, dz in DIRS if L.edge_state(i, j, i + dx, j + dz) == "wall"]
        if not walls:
            return
        dx, dz = rng.choice(walls)
        cx, cz = L.cell_center(i, j)
        Cc = C.CELL
        off = rng.uniform(-.6, .6)
        y = rng.uniform(.8, 1.6)
        if dx != 0:
            p = (cx + dx * (Cc / 2 - .015), y, cz + off)
        else:
            p = (cx + off, y, cz + dz * (Cc / 2 - .015))
        g.b["smear"].decal(p, rng.uniform(.8, 1.4), rng.uniform(-25, 25), col, normal=(-dx, 0, -dz))

    # ------------------------------------------------------------------
    # OUTILS DE PLACEMENT DANS LES SALLES
    # ------------------------------------------------------------------
    def wall_slots(self, room, exclude_sides=()):
        """Emplacements contre les murs pleins, loin des portes et des grilles."""
        L = self.level
        busy = set()
        for d in room.doors:
            busy.add(d.room_cell)
        for g in room.grilles:
            busy.add(g.room_cell)
        out = []
        for i, j in room.cells():
            if any(abs(i - bi) + abs(j - bj) <= 1 for bi, bj in busy):
                continue
            for dx, dz in DIRS:
                if (dx, dz) in exclude_sides:
                    continue
                if L.edge_state(i, j, i + dx, j + dz) == "wall":
                    out.append((i, j, dx, dz))
        self.rng.shuffle(out)
        return out

    def slot_placer(self, slot, depth):
        i, j, dx, dz = slot
        cx, cz = self.level.cell_center(i, j)
        off = C.CELL / 2 - depth / 2 - .03
        return Placer(cx + dx * off, cz + dz * off, -dx, -dz)

    def block(self, x0, x1, z0, z1, h, owner=None):
        self.level.add_blocker(Blocker(x0, x1, 0, h, z0, z1, "prop", owner))

    def block_placer(self, pl, lc, ls, h):
        x0, x1, z0, z1 = pl.aabb(lc, ls)
        self.block(x0, x1, z0, z1, h)

    def interior_cells(self, room, margin=1):
        return [(i, j) for i, j in room.cells()
                if room.x + margin <= i < room.x + room.w - margin and room.y + margin <= j < room.y + room.h - margin]

    def take_slots(self, slots, n):
        """Prend n emplacements en évitant deux objets dans la même case."""
        taken, used = [], set()
        while slots and len(taken) < n:
            s = slots.pop()
            if (s[0], s[1]) in used:
                continue
            used.add((s[0], s[1]))
            taken.append(s)
        return taken

    # --- props génériques ---------------------------------------------
    def prop_locker(self, room, slot, table):
        g = self.group_for(slot[0], slot[1])
        pl = self.slot_placer(slot, loot.Locker.D)
        lk = loot.Locker(self.level, g.b, g.root, pl, table, self.rng, self.animated)
        lk.room = room
        self.loot_dir.lockers.append(lk)
        return lk

    def prop_bed(self, room, slot, medical=False):
        g = self.group_for(slot[0], slot[1])
        pl = self.slot_placer(slot, 2.05)
        mb = g.b["struct"]
        frame = (.62, .64, .66) if medical else (.3, .3, .32)
        sheet = (.78, .8, .78) if medical else jitter_color((.35, .38, .45), .2, self.rng)
        lat = self.rng.uniform(-.4, .4)
        pl.box(mb, (lat, .3, 0), (.95, .1, 2.0), frame)
        for sx in (-.42, .42):
            for sz in (-.95, .95):
                pl.box(mb, (lat + sx, .15, sz), (.06, .3, .06), frame)
        pl.box(mb, (lat, .42, .05), (.88, .14, 1.85), sheet)
        pl.box(mb, (lat, .53, -.75), (.6, .1, .35), (.85, .85, .82))
        pl.box(mb, (lat, .55, -1.0), (.95, .6, .05), frame)
        if not medical and self.rng.random() < .5:
            # couchette superposée
            pl.box(mb, (lat, 1.45, 0), (.95, .08, 2.0), frame)
            pl.box(mb, (lat, 1.55, .05), (.88, .12, 1.85), jitter_color(sheet, .2, self.rng))
            for sx in (-.42, .42):
                pl.box(mb, (lat + sx, .95, .95), (.06, 1.9, .06), frame)
        self.block_placer(pl, (lat, 0), (.95, 2.0), .6)
        self._spot(room, "bed", pl.pt(lat + .15, .5, .35), pl.yaw + 15)
        if medical and self.rng.random() < .6:
            # potence à perfusion
            pl.cyl(mb, (lat + .65, .9, .7), .02, 1.8, (.7, .7, .72))
            pl.box(mb, (lat + .65, 1.75, .7), (.12, .2, .05), (.6, .75, .7))
        return pl

    def prop_console(self, room, slot, red=False, width=1.4):
        g = self.group_for(slot[0], slot[1])
        pl = self.slot_placer(slot, .8)
        mb = g.b["struct"]
        body = (.22, .24, .27)
        pl.box(mb, (0, .45, 0), (width, .9, .7), body)
        pl.box(mb, (0, .95, -.15), (width, .1, .45), (.15, .16, .18))
        pl.box(mb, (0, 1.35, -.3), (width - .1, .75, .08), body)
        sc = g.b["screen"] if not red else g.b["emissive"]
        col = (1, 1, 1) if not red else (.8, .1, .08)
        pl.box(sc, (0, 1.35, -.25), (width - .3, .55, .02), col, faces='all')
        for k in range(4):
            pl.box(g.b["emissive"], (-width / 2 + .25 + k * .25, .99, 0), (.05, .02, .05),
                   self.rng.choice([(.1, .9, .2), (.9, .6, .1), (.9, .1, .1)]))
        # voyant de batterie de secours : clignote même sans courant (brille sans éclairer)
        if self.rng.random() < C.BATTERY_LED_CHANCE:
            pl.box(g.b["battery"], (width / 2 - .12, .99, .12), (.04, .02, .04),
                   self.rng.choice([(1, .35, .05), (1, .08, .05)]))
        self.block_placer(pl, (0, 0), (width, .7), 1.0)
        self._spot(room, "console", pl.pt(-width / 4, 1.005, .05), pl.yaw + 5)
        x, _, z = pl.pt(0, 1.3, .2)
        self.lights.add_fixture(Fixture((x, 1.3, z), (.25, .9, .45) if not red else (1, .2, .1), 3.5, "pulse", None,
                                        .35, kind="console"))
        return pl

    def prop_crate(self, g, x, z, s=None, yaw=None, stack=True):
        rng = self.rng
        s = s or rng.uniform(.6, 1.1)
        yaw = rng.uniform(-15, 15) if yaw is None else yaw
        col = rng.choice([(.35, .32, .22), (.3, .33, .3), (.4, .25, .15), (.28, .28, .3)])
        g.b["struct"].box_rot((x, s / 2, z), (s, s, s), yaw, col)
        g.b["struct"].box_rot((x, s / 2, z), (s * 1.02, s * .12, s * 1.02), yaw, (.15, .15, .15))
        h = s
        if stack and rng.random() < .45:
            s2 = s * rng.uniform(.6, .9)
            g.b["struct"].box_rot((x, s + s2 / 2, z), (s2, s2, s2), yaw + rng.uniform(-20, 20),
                                  jitter_color(col, .15, rng))
            h += s2
        self.block(x - s / 2, x + s / 2, z - s / 2, z + s / 2, h)

    def prop_barrel(self, g, x, z):
        rng = self.rng
        col = rng.choice([(.5, .15, .1), (.2, .3, .45), (.55, .5, .15), (.3, .3, .3)])
        g.b["struct"].cylinder((x, .5, z), .32, 1.0, col, 12)
        g.b["struct"].cylinder((x, .78, z), .335, .06, (.15, .15, .15), 12)
        g.b["struct"].cylinder((x, .22, z), .335, .06, (.15, .15, .15), 12)
        self.block(x - .32, x + .32, z - .32, z + .32, 1.0)

    def prop_shelf(self, room, slot):
        g = self.group_for(slot[0], slot[1])
        pl = self.slot_placer(slot, .6)
        mb = g.b["struct"]
        c = (.3, .3, .32)
        for y in (.05, .7, 1.35, 2.0):
            pl.box(mb, (0, y, 0), (1.8, .05, .55), c)
            if y < 2 and self.rng.random() < .8:
                for k in range(self.rng.randint(1, 3)):
                    s = self.rng.uniform(.2, .45)
                    pl.box(mb, (self.rng.uniform(-.6, .6), y + s / 2 + .03, self.rng.uniform(-.1, .1)),
                           (s, s, s), jitter_color((.4, .35, .25), .25, self.rng))
        for sx in (-.88, .88):
            pl.box(mb, (sx, 1.05, 0), (.05, 2.1, .55), c)
        self.block_placer(pl, (0, 0), (1.8, .55), 2.1)

    def prop_table(self, g, x, z, w, d, col=(.35, .35, .37), benches=True):
        mb = g.b["struct"]
        mb.box((x, .75, z), (w, .06, d), col)
        for sx in (-1, 1):
            for sz in (-1, 1):
                mb.box((x + sx * (w / 2 - .1), .37, z + sz * (d / 2 - .1)), (.06, .74, .06), (.2, .2, .2))
        self.block(x - w / 2, x + w / 2, z - d / 2, z + d / 2, .8)
        if benches:
            for sz in (-1, 1):
                bz = z + sz * (d / 2 + .35)
                mb.box((x, .45, bz), (w, .06, .35), (.25, .25, .27))
                mb.box((x, .22, bz), (w - .2, .44, .06), (.2, .2, .2))
                self.block(x - w / 2, x + w / 2, bz - .18, bz + .18, .5)
        # vaisselle renversée
        for _ in range(self.rng.randint(0, 4)):
            mb.box_rot((x + self.rng.uniform(-w / 2 + .2, w / 2 - .2), .8, z + self.rng.uniform(-d / 3, d / 3)),
                       (.3, .02, .22), self.rng.uniform(0, 180), (.6, .6, .58))

    def add_room_fixture(self, room, x, z, y, col, mode, radius=8, intensity=1.0, size=(.9, .05, .18), kind="lamp"):
        g = self.groups[("room", room.id)]
        e = Entity(parent=g.root, model='cube', color=color.rgb(.3, .3, .32), scale=size, position=(x, y + .03, z))
        mark_emissive(e, lit_off=False)      # tube : émissif seulement quand il est alimenté
        return self.lights.add_fixture(Fixture((x, y - .3, z), col, radius, mode, e, intensity, room, kind=kind))

    # ------------------------------------------------------------------
    # SALLES
    # ------------------------------------------------------------------
    def _room_lights(self, room):
        """Grille de néons au plafond selon le type de salle."""
        rng = self.rng
        if room.type in ("hangar", "engine"):
            return   # éclairage spécifique
        nx = max(1, room.w // 3)
        nz = max(1, room.h // 3)
        x0, x1, z0, z1 = room.world_bounds()
        for a in range(nx):
            for b in range(nz):
                x = x0 + (x1 - x0) * (a + .5) / nx
                z = z0 + (z1 - z0) * (b + .5) / nz
                # couleur industrielle chaude ou froide selon la salle ; les lampes qui
                # resteront cassées sont tirées par le gestionnaire de courant
                r = rng.random()
                if room.type in ("medbay", "command"):
                    col = C.LIGHT_COLOR_COLD
                elif room.type in ("crew", "mess"):
                    col = C.LIGHT_COLOR_WARM
                else:
                    col = C.LIGHT_COLOR_WARM if r < .5 else C.LIGHT_COLOR_COLD
                mode = "pulse" if (room.type == "command" and r < .3) else "steady"
                self.add_room_fixture(room, x, z, room.height - .02, col, mode, 8, .9, size=(1.3, .05, .2))
        # gyrophare d'alarme
        cx, cz = room.world_center()
        g = self.groups[("room", room.id)]
        e = Entity(parent=g.root, model='sphere', color=color.rgb(.2, .02, .02), scale=(.25, .15, .25),
                   position=(cx + .5, room.height - .1, cz + .5))
        mark_emissive(e, lit_off=False)
        self.lights.add_fixture(Fixture((cx + .5, room.height - .4, cz + .5), (1, .05, .02), 11, "alarm", e, 1.4,
                                        room, kind="alarm"))

    def _room_clutter(self, room):
        """Désordre : sang, traces, débris."""
        rng = self.rng
        g = self.groups[("room", room.id)]
        cells = list(room.cells())
        for _ in range(rng.randint(1, 4)):
            i, j = rng.choice(cells)
            cx, cz = self.level.cell_center(i, j)
            g.b["decal"].decal((cx + rng.uniform(-.8, .8), .011, cz + rng.uniform(-.8, .8)), rng.uniform(.6, 1.8),
                               rng.uniform(0, 360), (1, 1, 1, 1))
        for _ in range(rng.randint(0, 3)):
            i, j = rng.choice(cells)
            self._wall_smear(g, i, j)
        for _ in range(rng.randint(0, 2)):
            i, j = rng.choice(cells)
            self._wall_claw(g, i, j)
        # traces de brûlure (décalque teinté noir)
        for _ in range(rng.randint(0, 2)):
            i, j = rng.choice(cells)
            cx, cz = self.level.cell_center(i, j)
            g.b["decal"].decal((cx, .012, cz), rng.uniform(1, 2), rng.uniform(0, 360), (.05, .05, .05, .8))

    def _room_hangar(self, room):
        L = self.level
        rng = self.rng
        g = self.groups[("room", room.id)]
        mb = g.b["struct"]
        x0, x1, z0, z1 = room.world_bounds()
        cx = (x0 + x1) / 2
        pad_z = z0 + (z1 - z0) * .5
        self.pad_center = (cx, pad_z)
        # aire d'atterrissage : cercle de bandes de danger
        for k in range(24):
            a = 2 * math.pi * k / 24
            px, pz = cx + math.cos(a) * 5.2, pad_z + math.sin(a) * 5.2
            g.b["hazard"].box_rot((px, .008, pz), (1.2, 0, .35), -math.degrees(a) + 90, (1, 1, 1))
        g.b["struct"].box((cx, .004, pad_z), (6, 0, 6), (.22, .22, .24), faces='t')
        # poutres au plafond
        for k in range(1, 5):
            z = z0 + (z1 - z0) * k / 5
            mb.box((cx, room.height - .4, z), (x1 - x0, .5, .4), (.25, .25, .27))
        for x in (x0 + 4, x1 - 4):
            mb.box((x, room.height - .8, (z0 + z1) / 2), (.35, .35, z1 - z0), (.28, .28, .3))
        # projecteurs muraux
        for x in (x0 + .4, x1 - .4):
            for z in (z0 + (z1 - z0) * .35, z0 + (z1 - z0) * .75):
                e = Entity(parent=g.root, model='cube', color=color.rgb(.3, .3, .32), scale=(.12, .5, 1.0),
                           position=(x, 7.5, z))
                mark_emissive(e, lit_off=False)
                self.lights.add_fixture(Fixture((x + (1.5 if x < cx else -1.5), 7, z), (1, .95, .82), 17, "steady",
                                                e, 1.6, room))
        # balises rouges de l'ouverture (sur batterie) : elles brillent sans éclairer
        ox, ow = L.hangar_opening
        for k in (0, 1):
            x = (ox + (0 if k == 0 else ow)) * C.CELL
            e = Entity(parent=g.root, model='cube', color=color.rgb(1, .1, .05), scale=(.3, .3, .3),
                       position=(x, C.HANGAR_OPENING_HEIGHT + .3, .3))
            mark_emissive(e)
        # lueur des étoiles par la grande ouverture
        for fx_ in (x0 + (x1 - x0) * .35, x0 + (x1 - x0) * .65):
            self.lights.add_fixture(Fixture((fx_, 3.5, 1.2), C.STARLIGHT_COLOR, C.STARLIGHT_RADIUS * 2.2, "star",
                                            None, C.STARLIGHT_INTENSITY * 1.4, room, powered=False, kind="star"))
        # gyrophare
        e = Entity(parent=g.root, model='sphere', color=color.rgb(.2, .02, .02), scale=.35,
                   position=(cx, room.height - .3, z1 - 1))
        mark_emissive(e, lit_off=False)
        self.lights.add_fixture(Fixture((cx, room.height - 1, z1 - 2), (1, .05, .02), 18, "alarm", e, 1.8, room,
                                        kind="alarm"))
        # caisses et fûts le long des murs (jamais devant l'ouverture)
        slots = self.wall_slots(room, exclude_sides=((0, -1),))
        for s in self.take_slots(slots, 9):
            i, j, dx, dz = s
            px, pz = L.cell_center(i, j)
            px += dx * .5
            pz += dz * .5
            if rng.random() < .6:
                self.prop_crate(g, px, pz, rng.uniform(.9, 1.4))
            else:
                self.prop_barrel(g, px + rng.uniform(-.3, .3), pz)
        # établi avec le couteau garanti
        if slots:
            s = slots.pop()
            gg = self.group_for(s[0], s[1])
            pl = self.slot_placer(s, .8)
            pl.box(gg.b["struct"], (0, .85, 0), (2.0, .08, .8), (.35, .3, .25))
            for sx in (-.9, .9):
                pl.box(gg.b["struct"], (sx, .42, 0), (.08, .84, .7), (.2, .2, .2))
            pl.box(gg.b["struct"], (0, 1.5, -.37), (2.0, 1.2, .05), (.3, .3, .32))   # panneau à outils
            self.block_placer(pl, (0, 0), (2.0, .8), .9)
            kx, ky, kz = pl.pt(.3, .9, .1)
            loot.Pickup(L, gg.root, "knife", 1, kx, ky, kz, pl.yaw + 70)
            bx, by, bz = pl.pt(-.4, .9, .05)
            loot.Pickup(L, gg.root, "battery", 1, bx, by, bz)
            self._spot(room, "workbench", pl.pt(-.05, .895, -.15), pl.yaw - 8)
            self.add_room_fixture(room, *pl.pt(0, 0, .2)[::2], 2.2, (1, .85, .6), "steady", 5, .8, (.6, .04, .1))
        # console d'amarrage
        if slots:
            s = slots.pop()
            self.prop_console(room, s, width=1.2)
            self.dock_placer = self.slot_placer(s, .8)
        # un casier de maintenance
        if slots:
            self.prop_locker(room, slots.pop(), "hangar")

    def _room_engine(self, room):
        L = self.level
        rng = self.rng
        g = self.groups[("room", room.id)]
        mb = g.b["struct"]
        cx, cz = room.world_center()
        self.reactor_pos = (cx, 2.5, cz)
        H = room.height
        # réacteur central
        mb.cylinder((cx, .3, cz), 2.4, .6, (.25, .25, .27), 20)
        mb.cylinder((cx, H - .3, cz), 1.9, .6, (.25, .25, .27), 20)
        rc = g.b["reactor"]
        for k in range(4):
            y = .8 + k * (H - 1.6) / 4
            rc.cylinder((cx, y + .3, cz), 1.25, .35, (.15, .8, 1.0), 20)
            mb.cylinder((cx, y + .7, cz), 1.4, .25, (.3, .3, .32), 20)
        mb.cylinder((cx, H / 2, cz), 1.05, H - .8, (.18, .2, .22), 16)
        for a in range(6):
            ang = a * math.pi / 3
            mb.cylinder((cx + math.cos(ang) * 1.6, H / 2, cz + math.sin(ang) * 1.6), .12, H - .6, (.35, .33, .3), 8)
        # garde-corps
        for a in range(16):
            ang = a * math.pi / 8
            mb.cylinder((cx + math.cos(ang) * 3.1, .55, cz + math.sin(ang) * 3.1), .04, 1.1, (.55, .5, .15), 6)
        for a in range(16):
            a0, a1 = a * math.pi / 8, (a + 1) * math.pi / 8
            mx, mz = cx + math.cos((a0 + a1) / 2) * 3.1, cz + math.sin((a0 + a1) / 2) * 3.1
            mb.box_rot((mx, 1.08, mz), (1.25, .05, .05), -math.degrees((a0 + a1) / 2) + 90, (.55, .5, .15))
        self.block(cx - 2.4, cx + 2.4, cz - 2.4, cz + 2.4, H)
        self.lights.add_fixture(Fixture((cx + 2.8, 2.5, cz), (.3, .8, 1.0), 14, "reactor", None, 1.5, room,
                                        kind="reactor"))
        self.lights.add_fixture(Fixture((cx - 2.8, 2.5, cz), (.3, .8, 1.0), 14, "reactor", None, 1.2, room,
                                        kind="reactor"))
        # câble arraché près du réacteur (étincelles)
        self.spark_points.append((cx + 2.9, H - 1.6, cz + 1.2))
        # tuyaux du réacteur vers les murs
        x0, x1, z0, z1 = room.world_bounds()
        for k, (tx, tz) in enumerate(((x0, cz), (x1, cz), (cx, z0), (cx, z1))):
            y = H - .9 - k * .2
            if tx != cx:
                mb.cylinder(((tx + cx) / 2, y, tz + .6), .18, abs(tx - cx) - 2, (.4, .3, .2), 10, 'x')
            else:
                mb.cylinder((tx + .6, y, (tz + cz) / 2), .18, abs(tz - cz) - 2, (.4, .3, .2), 10, 'z')
        # éclairage orangé de service
        for (x, z) in ((x0 + 1.5, z0 + 1.5), (x1 - 1.5, z1 - 1.5), (x0 + 1.5, z1 - 1.5), (x1 - 1.5, z0 + 1.5)):
            self.add_room_fixture(room, x, z, H - .02, (1, .6, .25), "steady", 9, .9, (.4, .05, .4))
        e = Entity(parent=g.root, model='sphere', color=color.rgb(.2, .02, .02), scale=.3,
                   position=(x0 + 1, H - .2, cz))
        mark_emissive(e, lit_off=False)
        self.lights.add_fixture(Fixture((x0 + 1.5, H - .8, cz), (1, .05, .02), 14, "alarm", e, 1.6, room,
                                        kind="alarm"))
        slots = self.wall_slots(room)
        # tableau électrique principal (fusibles + gros levier)
        if slots:
            self._power_panel(room, slots.pop())
        for s in self.take_slots(slots, 3):
            self.prop_locker(room, s, "engine")
        for s in self.take_slots(slots, 3):
            self.prop_console(room, s, red=rng.random() < .5)
        for s in self.take_slots(slots, 3):
            i, j, dx, dz = s
            px, pz = L.cell_center(i, j)
            self.prop_barrel(g, px + dx * .6, pz + dz * .6)

    def _room_medbay(self, room):
        rng = self.rng
        g = self.groups[("room", room.id)]
        slots = self.wall_slots(room)
        for s in self.take_slots(slots, rng.randint(3, 4)):
            self.prop_bed(room, s, medical=True)
        for s in self.take_slots(slots, 3):
            self.prop_locker(room, s, "medbay")
        for s in self.take_slots(slots, 1):
            self.prop_console(room, s)
        # scialytique au centre
        cx, cz = room.world_center()
        g.b["struct"].cylinder((cx, room.height - .5, cz), .5, .15, (.7, .72, .75), 16)
        g.b["struct"].cylinder((cx, room.height - .2, cz), .04, .5, (.5, .5, .5), 6)
        self.add_room_fixture(room, cx, cz, room.height - .5, (.9, .95, 1), "steady", 6, 1.1, (.7, .02, .7))
        # table d'opération
        g.b["struct"].box((cx, .85, cz), (.8, .1, 2.0), (.6, .62, .64))
        g.b["struct"].box((cx, .42, cz), (.3, .84, .3), (.4, .4, .42))
        g.b["decal"].decal((cx, .87, cz), 1.0, rng.uniform(0, 360), (1, 1, 1, 1))
        self.block(cx - .4, cx + .4, cz - 1, cz + 1, .9)
        # kit de soin posé
        loot.Pickup(self.level, g.root, "medkit", 1, cx + .22, .91, cz + .88, rng.uniform(0, 90))
        self.optable = (cx, cz)

    def _room_crew(self, room):
        rng = self.rng
        g = self.groups[("room", room.id)]
        slots = self.wall_slots(room)
        for s in self.take_slots(slots, 2):
            self.prop_bed(room, s)
        for s in self.take_slots(slots, rng.randint(2, 3)):
            self.prop_locker(room, s, "crew")
        for s in self.take_slots(slots, 1):
            gg = self.group_for(s[0], s[1])
            pl = self.slot_placer(s, .7)
            pl.box(gg.b["struct"], (0, .75, 0), (1.3, .05, .65), (.4, .32, .25))
            pl.box(gg.b["struct"], (-.55, .37, 0), (.05, .74, .6), (.3, .25, .2))
            pl.box(gg.b["struct"], (.55, .37, 0), (.05, .74, .6), (.3, .25, .2))
            pl.box(gg.b["screen"], (.2, 1.0, -.2), (.5, .35, .03), (1, 1, 1))
            pl.box(gg.b["struct"], (0, .45, .6), (.45, .06, .45), (.2, .2, .22))   # chaise
            self.block_placer(pl, (0, 0), (1.3, .65), .8)
            self._spot(room, "desk", pl.pt(-.3, .78, .05), pl.yaw + 10)
            if rng.random() < .4:
                x, y, z = pl.pt(.4, .78, .12)
                loot.Pickup(self.level, gg.root, "battery", 1, x, y, z, rng.uniform(0, 90))
            x, y, z = pl.pt(.2, 1.0, 0)
            self.lights.add_fixture(Fixture((x, y, z), (.3, .9, .5), 3, "pulse", None, .3, room, kind="console"))
        # affaires personnelles au sol
        for _ in range(rng.randint(2, 5)):
            i, j = rng.choice(list(room.cells()))
            cx, cz = self.level.cell_center(i, j)
            g.b["struct"].box_rot((cx + rng.uniform(-.8, .8), .06, cz + rng.uniform(-.8, .8)),
                                  (rng.uniform(.2, .5), .1, rng.uniform(.2, .4)), rng.uniform(0, 180),
                                  jitter_color((.4, .35, .3), .4, rng))

    def _room_command(self, room):
        L = self.level
        rng = self.rng
        g = self.groups[("room", room.id)]
        mb = g.b["struct"]
        x0, x1, z0, z1 = room.world_bounds()
        cx, cz = room.world_center()
        self.command_center = (cx, cz)
        # rangée de consoles face à la baie vitrée (nord)
        n = max(2, room.w // 2)
        for k in range(n):
            x = x0 + (x1 - x0) * (k + .5) / n
            pl = Placer(x, z1 - 1.6, 0, 1)
            pl.box(mb, (0, .45, 0), (1.6, .9, .7), (.2, .22, .26))
            pl.box(g.b["screen"], (0, 1.1, .1), (1.3, .5, .03), (1, 1, 1))
            pl.box(mb, (0, .95, -.1), (1.6, .08, .5), (.14, .15, .18))
            self.block_placer(pl, (0, 0), (1.6, .7), 1.0)
            pl.box(mb, (0, .45, -1.0), (.5, .08, .5), (.18, .18, .2))            # siège
            pl.box(mb, (0, .75, -1.25), (.5, .6, .08), (.18, .18, .2))
            pl.cyl(mb, (0, .22, -1.0), .05, .45, (.3, .3, .3))
            self.lights.add_fixture(Fixture((x, 1.2, z1 - 2.2), (.3, .6, 1.0), 4, "pulse", None, .45, room,
                                            kind="console"))
        # table holographique centrale
        mb.cylinder((cx, .45, cz - .5), .9, .9, (.18, .2, .24), 20)
        g.b["emissive"].cylinder((cx, .92, cz - .5), .8, .04, (.2, .6, 1.0), 20)
        holo = Entity(parent=g.root, model='sphere', color=color.rgba(.3, .7, 1, .25), scale=(1.2, .8, 1.2),
                      position=(cx, 1.7, cz - .5))
        mark_emissive(holo)
        holo.setTransparency(TransparencyAttrib.MAlpha)
        self.holo = holo
        self.lights.power.register_emissive(holo, "holo", cx, cz)     # s'allume avec le courant
        self.block(cx - .9, cx + .9, cz - 1.4, cz + .4, 1.0)
        self.lights.add_fixture(Fixture((cx, 1.8, cz - .5), (.3, .7, 1.0), 6, "pulse", None, .8, room,
                                        kind="console"))
        # console du disque dur (contre un mur latéral)
        slots = self.wall_slots(room, exclude_sides=((0, 1),))
        s = slots.pop() if slots else (room.x, room.y, -1, 0)
        gg = self.group_for(s[0], s[1])
        pl = self.slot_placer(s, .8)
        self.prop_console(room, s, red=True, width=1.2)
        hx, hy, hz = pl.pt(0, 1.02, .05)
        self.hdd = loot.HardDrive(L, gg.root, hx, hy, hz, pl.yaw)
        self.updatables.append(self.hdd)
        # lumière rouge d'urgence au-dessus
        self.add_room_fixture(room, hx, hz, room.height - .02, (1, .15, .1), "pulse", 7, 1.0, (.3, .05, .3),
                              kind="console")
        # le capitaine est mort à son poste
        cxp, _, czp = pl.pt(0, 0, 1.3)
        c = loot.Corpse(L, gg.b, cxp, czp, pl.yaw + 160, rng, story.CREW["vasseur"]["uniform"], crew="vasseur")
        c.infested = False
        self.crew_corpses["vasseur"] = c
        self.loot_dir.corpses.append(c)
        for s2 in self.take_slots(slots, 1):
            self.prop_locker(room, s2, "command")
        for s2 in self.take_slots(slots, 2):
            self.prop_console(room, s2)

    def _room_mess(self, room):
        rng = self.rng
        g = self.groups[("room", room.id)]
        x0, x1, z0, z1 = room.world_bounds()
        cx, cz = room.world_center()
        # tables et bancs au centre
        along_x = (x1 - x0) >= (z1 - z0)
        n = 2 if min(room.w, room.h) < 6 else 3
        for k in range(n):
            if along_x:
                z = z0 + (z1 - z0) * (k + .5) / n
                if abs(z - z0) < 2 or abs(z1 - z) < 2:
                    continue
                self.prop_table(g, cx, z, (x1 - x0) * .5, .9)
            else:
                x = x0 + (x1 - x0) * (k + .5) / n
                if abs(x - x0) < 2 or abs(x1 - x) < 2:
                    continue
                self.prop_table(g, x, cz, .9, (z1 - z0) * .5, benches=False)
        # cuisine : comptoirs et frigo contre les murs
        slots = self.wall_slots(room)
        for s in self.take_slots(slots, 3):
            gg = self.group_for(s[0], s[1])
            pl = self.slot_placer(s, .7)
            pl.box(gg.b["struct"], (0, .45, 0), (2.2, .9, .65), (.5, .5, .5))
            pl.box(gg.b["struct"], (0, .92, 0), (2.25, .05, .7), (.65, .65, .63))
            pl.box(gg.b["struct"], (0, 1.8, -.15), (2.2, .6, .35), (.45, .45, .45))
            self.block_placer(pl, (0, 0), (2.2, .65), 1.0)
        for s in self.take_slots(slots, 1):
            gg = self.group_for(s[0], s[1])
            pl = self.slot_placer(s, .8)
            pl.box(gg.b["struct"], (0, 1.0, 0), (1.0, 2.0, .8), (.7, .72, .72))       # frigo
            pl.box(gg.b["emissive"], (.3, 1.4, .41), (.08, .04, .01), (.2, .9, .3))
            self.block_placer(pl, (0, 0), (1.0, .8), 2.0)
            self.fridge_placer = pl
            self._spot(room, "fridge", pl.pt(-.12, 1.5, .415), pl.yaw, vertical=True)
        for s in self.take_slots(slots, 1):
            self.prop_locker(room, s, "mess")
        # plateaux au sol
        for _ in range(rng.randint(3, 7)):
            g.b["struct"].box_rot((cx + rng.uniform(-3, 3), .015, cz + rng.uniform(-2, 2)), (.4, .02, .3),
                                  rng.uniform(0, 180), (.55, .55, .5))

    def _room_storage(self, room):
        rng = self.rng
        g = self.groups[("room", room.id)]
        slots = self.wall_slots(room)
        for s in self.take_slots(slots, rng.randint(2, 3)):
            self.prop_shelf(room, s)
        for s in self.take_slots(slots, 1):
            self.prop_locker(room, s, "storage")
        for s in self.take_slots(slots, 3):
            i, j, dx, dz = s
            px, pz = self.level.cell_center(i, j)
            if rng.random() < .5:
                self.prop_crate(g, px + dx * .5, pz + dz * .5)
            else:
                self.prop_barrel(g, px + dx * .6, pz + dz * .6)

    # ------------------------------------------------------------------
    # COURANT : tableau électrique principal et fusibles
    # ------------------------------------------------------------------
    def _power_panel(self, room, slot):
        """Grand tableau électrique mural : 3 logements de fusibles, voyants sur batterie, gros levier."""
        g = self.group_for(slot[0], slot[1])
        pl = self.slot_placer(slot, .35)
        mb = g.b["struct"]
        body = (.28, .3, .26)
        pl.box(mb, (0, 1.35, 0), (1.5, 1.7, .3), body)                    # armoire
        pl.box(mb, (0, 1.35, .16), (1.36, 1.56, .02), (.2, .22, .19))     # façade
        pl.box(g.b["hazard"], (0, 2.28, .12), (1.5, .12, .08), (1, 1, 1))  # bande de danger
        pl.box(mb, (0, .25, .1), (1.2, .5, .5), (.22, .22, .24))          # socle / chemin de câbles
        for k in range(5):                                                  # gros câbles vers le plafond
            pl.cyl(mb, (-.5 + k * .25, 2.9, -.05), .05, 1.1, (.08, .08, .09))
        self.block_placer(pl, (0, 0), (1.5, .45), 2.2)
        slots_vis, leds = [], []
        for k in range(3):
            lx = -.45 + k * .3
            pl.box(mb, (lx, 1.55, .17), (.16, .36, .04), (.06, .06, .07))    # logement vide (noir)
            x, y, z = pl.pt(lx, 1.55, .2)
            fuse = Entity(parent=g.root, model='cube', color=color.rgb(.75, .62, .25), position=(x, y, z),
                          rotation_y=pl.yaw, scale=(.1, .28, .06), enabled=False)
            Entity(parent=fuse, model='cube', color=color.rgb(.7, .7, .72), scale=(1.1, .12, 1.1), y=.44)
            Entity(parent=fuse, model='cube', color=color.rgb(.7, .7, .72), scale=(1.1, .12, 1.1), y=-.44)
            slots_vis.append(fuse)
            x, y, z = pl.pt(lx, 1.83, .19)
            led = Entity(parent=g.root, model='cube', color=color.rgb(1, .08, .04), position=(x, y, z),
                         rotation_y=pl.yaw, scale=(.05, .05, .02))
            mark_emissive(led)       # voyant sur batterie de secours
            leds.append(led)
        # levier : pivot sur le côté droit de l'armoire
        x, y, z = pl.pt(.55, 1.3, .2)
        pivot = Entity(parent=g.root, position=(x, y, z), rotation_y=pl.yaw)
        pl.box(mb, (.55, 1.3, .18), (.18, .3, .06), (.12, .12, .13))         # socle du levier
        arm = Entity(parent=pivot, rotation_x=-40)
        Entity(parent=arm, model='cube', color=color.rgb(.35, .35, .37), scale=(.05, .5, .05), y=.25)
        Entity(parent=arm, model='cube', color=color.rgb(.6, .08, .05), scale=(.16, .07, .07), y=.5)
        x, y, z = pl.pt(0, 1.25, .45)
        self.power_panel = {"pos": (x, 1.25, z), "fuse_vis": slots_vis, "leds": leds, "arm": arm,
                            "room": room, "facing": pl.facing}

    def _place_fuses(self):
        """2 ou 3 fusibles garantis : dans la salle des machines et dans les salles voisines."""
        L = self.level
        rng = self.rng
        engine = L.room("engine")
        if engine is None or self.power_panel is None:
            return
        n = rng.randint(*C.POWER_FUSES)
        neigh = []
        for a, b in L.connections:
            ra, rb = L.rooms[a], L.rooms[b]
            other = rb if ra is engine else (ra if rb is engine else None)
            if other is not None and other.type not in ("command", "hangar") and other not in neigh:
                neigh.append(other)
        rng.shuffle(neigh)
        targets = [engine] + [neigh[k % len(neigh)] if neigh else engine for k in range(n - 1)]
        for room in targets:
            busy = {d.room_cell for d in room.doors} | {gr.room_cell for gr in room.grilles}
            cells = [c for c in room.cells() if c not in busy]
            for _ in range(80):
                i, j = rng.choice(cells)
                cx, cz = L.cell_center(i, j)
                # près d'un mur ou d'un meuble : caché, mais repérable à la lampe
                x, z = cx + rng.uniform(-.85, .85), cz + rng.uniform(-.85, .85)
                if L.blocked_point(x, .15, z, .35):
                    continue
                if any(math.hypot(x - f.pos[0], z - f.pos[2]) < 3 for f in self.fuses):
                    continue
                g = self.group_for(i, j)
                self.fuses.append(loot.FusePickup(L, g.root, x, .02, z, rng.uniform(0, 180)))
                break
        print(f"[courant] {len(self.fuses)} fusibles placés : " +
              ", ".join(L.room_at(f.pos[0], f.pos[2]).name for f in self.fuses))

    # ------------------------------------------------------------------
    def _place_caches(self):
        """Sacs de survie abandonnés (loot) là où l'équipage a fui ; traces de sang aux murs."""
        L = self.level
        rng = self.rng
        cands = [r for r in L.rooms if r.type not in ("hangar", "command")]
        for r in cands:
            if rng.random() < .75:
                cells = self.interior_cells(r, 1) or list(r.cells())
                i, j = rng.choice(cells)
                x, z = L.cell_center(i, j)
                x += rng.uniform(-.4, .4)
                z += rng.uniform(-.4, .4)
                if L.blocked_point(x, .3, z, .5):
                    continue
                g = self.group_for(i, j)
                loot.Cache(L, g.b, x, z, rng.uniform(0, 360), rng)
                self._wall_smear(g, i, j)
        corr = [c for c in L.links if L.kind[c[0]][c[1]] == CORR]
        rng.shuffle(corr)
        for (i, j) in corr[:4]:
            x, z = L.cell_center(i, j)
            g = self.group_for(i, j)
            loot.Cache(L, g.b, x + rng.uniform(-.3, .3), z + rng.uniform(-.3, .3), rng.uniform(0, 360), rng)
            for _ in range(2):
                self._wall_smear(g, i, j)

    # ------------------------------------------------------------------
    # HISTOIRE : corps de l'équipage et documents
    # ------------------------------------------------------------------
    def _spot(self, room, kind, pt, yaw, vertical=False):
        if room is None:
            return
        self.spots.setdefault(room.id, {}).setdefault(kind, []).append((pt[0], pt[1], pt[2], yaw, vertical))

    def _free_floor(self, room, rng, margin=.45, near=None, radius=None):
        """Point libre au sol dans une salle (optionnellement près d'un point)."""
        L = self.level
        cells = list(room.cells())
        for _ in range(60):
            if near is not None:
                x = near[0] + rng.uniform(-radius, radius)
                z = near[1] + rng.uniform(-radius, radius)
                if L.room_at(x, z) is not room:
                    continue
            else:
                i, j = rng.choice(cells)
                cx, cz = L.cell_center(i, j)
                x, z = cx + rng.uniform(-.8, .8), cz + rng.uniform(-.8, .8)
            if not L.blocked_point(x, .3, z, margin):
                return x, z
        return None

    def _crew_corpse(self, who, room, x, z, yaw, rng, y0=0.0):
        L = self.level
        g = self.group_for(*L.cell_at(x, z))
        c = loot.Corpse(L, g.b, x, z, yaw, rng, story.CREW[who]["uniform"], crew=who, y0=y0)
        self.crew_corpses[who] = c
        self.loot_dir.corpses.append(c)
        return c

    def _place_crew(self):
        """Corps de l'équipage du Kerguelen, chacun dans « sa » salle (Keating : jamais retrouvée)."""
        L = self.level
        rng = random.Random(self.seed * 5 + 29)
        # Lebrun, l'ingénieur, près du tableau électrique qu'il a lui-même coupé
        eng = L.room("engine")
        if eng is not None:
            near = None
            if self.power_panel is not None:
                px, _, pz = self.power_panel["pos"]
                fx, fz = self.power_panel["facing"]
                near = (px + fx * .9, pz + fz * .9)
            p = self._free_floor(eng, rng, near=near, radius=1.4) if near else None
            p = p or self._free_floor(eng, rng)
            if p:
                self._crew_corpse("lebrun", eng, p[0], p[1], rng.uniform(0, 360), rng)
        # Fontaine, la pilote, près de la console d'amarrage du hangar
        hg = L.room("hangar")
        if hg is not None:
            near = None
            if self.dock_placer is not None:
                near = self.dock_placer.pt(0, 0, 1.4)[::2]
            p = self._free_floor(hg, rng, near=near, radius=1.2) if near else None
            p = p or self._free_floor(hg, rng)
            if p:
                self._crew_corpse("fontaine", hg, p[0], p[1], rng.uniform(0, 360), rng)
        # Andreïev, autopsié : sur la table d'opération de l'infirmerie
        mb = L.room("medbay")
        if mb is not None and getattr(self, "optable", None):
            cx, cz = self.optable
            self._crew_corpse("andreiev", mb, cx, cz - .08, 0.0, rng, y0=.9)
        # Okafor et Ricci : la fusillade de la salle à manger
        ms = L.room("mess")
        if ms is not None:
            near = self.fridge_placer.pt(0, 0, 1.2)[::2] if self.fridge_placer else None
            p = self._free_floor(ms, rng, near=near, radius=1.0) if near else None
            p = p or self._free_floor(ms, rng)
            if p:
                self._crew_corpse("ricci", ms, p[0], p[1], rng.uniform(0, 360), rng)
            p = self._free_floor(ms, rng)
            if p:
                self._crew_corpse("okafor", ms, p[0], p[1], rng.uniform(0, 360), rng)
        for c in self.crew_corpses.values():
            i, j = L.cell_at(c.pos[0], c.pos[2])
            self._wall_smear(self.group_for(i, j), i, j)

    def _doc_room(self, d, crew_rooms):
        L = self.level
        if d["room"] == "crew":
            if not crew_rooms:
                return None
            if "Keating" in d["author"]:
                return crew_rooms[1 % len(crew_rooms)]
            return crew_rooms[0]
        if d["room"] == "corridor":
            return None
        return L.room(d["room"])

    def _door_spot(self, crew_rooms):
        """Post-it collé côté couloir, à côté de la porte d'une chambre."""
        for room in crew_rooms:
            for door in room.doors:
                ri, rj = door.room_cell
                oi, oj = door.out_cell
                dx, dz = oi - ri, oj - rj
                off = C.DOOR_WIDTH / 2 + .3
                if door.axis == "x":
                    x, z = door.pos[0] + dx * .08, door.pos[1] + off
                else:
                    x, z = door.pos[0] + off, door.pos[1] + dz * .08
                return (x, 1.55, z, math.degrees(math.atan2(dx, dz)), True)
        return None

    def _place_documents(self):
        """Place les documents de story.py (garantis + une sélection, au moins MIN_DOCUMENTS)."""
        L = self.level
        rng = random.Random(self.seed * 7 + 187)
        docs = story.DOCUMENTS
        optional = [d for d in docs if not d["guaranteed"]]
        rng.shuffle(optional)
        drop = rng.randint(0, max(0, len(docs) - story.MIN_DOCUMENTS))
        absent = {d["id"] for d in optional[:drop]}
        crew_rooms = sorted(L.rooms_of_type("crew"), key=lambda r: r.id)
        for d in docs:
            if d["id"] in absent:
                continue
            if self._place_doc(d, rng, crew_rooms):
                self.doc_present.add(d["id"])
        missing = sorted(set(x["id"] for x in docs) - self.doc_present)
        print(f"[histoire] {len(self.doc_present)} documents placés sur {len(docs)} (absents : {', '.join(missing)})")

    def _place_doc(self, d, rng, crew_rooms):
        L = self.level
        place = d["place"]
        if place.startswith("corpse:"):
            c = self.crew_corpses.get(place[7:])
            if c is not None:
                c.contents.insert(0, ("doc", d["id"]))
                c.infested = False          # un corps « important » ne cache pas de mauvaise surprise
                return True
            place = "floor"
        if place == "near_screamer":
            self.doc_deferred.append(d)     # placé par main.py une fois le casier piégé choisi
            return True
        spot = None
        room = self._doc_room(d, crew_rooms)
        if place == "door":
            spot = self._door_spot(crew_rooms)
        elif room is not None:
            lst = self.spots.get(room.id, {}).get(place)
            if lst:
                spot = lst.pop(rng.randrange(len(lst)))
        if spot is None and room is not None:
            p = self._free_floor(room, rng)
            if p:
                spot = (p[0], .012, p[1], rng.uniform(0, 360), False)
        if spot is None:
            return False
        x, y, z, yaw, vertical = spot
        g = self.group_for(*L.cell_at(x, z))
        self.doc_pickups[d["id"]] = loot.DocumentPickup(L, g.root, d, x, y, z, yaw, vertical)
        return True

    def place_near_locker(self, d, locker):
        """Le rapport d'autopsie de Yuri (enfermé dans un casier) posé au pied du casier piégé."""
        L = self.level
        fx, fz = locker.facing
        x, z = locker.pos[0] + fx * .3, locker.pos[2] + fz * .3
        pk = self.doc_pickups.get(d["id"])
        if pk is None:
            g = self.group_for(*L.cell_at(x, z))
            pk = loot.DocumentPickup(L, g.root, d, x, .012, z, locker.base_yaw + 20)
            self.doc_pickups[d["id"]] = pk
        elif not pk.taken:
            pk.move_to(x, .012, z, locker.base_yaw + 20)
        return pk

    def place_doc_floor(self, d, room_type):
        """Repli : document posé au sol dans une salle."""
        room = self.level.room(room_type)
        if room is None:
            return None
        rng = random.Random(self.seed + 3)
        p = self._free_floor(room, rng)
        if p is None:
            return None
        g = self.group_for(*self.level.cell_at(*p))
        pk = loot.DocumentPickup(self.level, g.root, d, p[0], .012, p[1], rng.uniform(0, 360))
        self.doc_pickups[d["id"]] = pk
        return pk

    def set_claws_visible(self, on):
        for n in self.claw_nodes:
            if on:
                n.show()
            else:
                n.hide()

    # ==================================================================
    # MISE À JOUR : portes, grilles, casiers, champ de force, culling
    # ==================================================================
    def update(self, dt, occupants, cam_pos, fps_mode=True):
        self.time += dt
        for door in self.door_visuals:
            prev = door.open_amount
            door.update(dt, occupants)
            if door.open_amount != prev or not hasattr(door, "_vis_init"):
                door._vis_init = True
                hw = C.DOOR_WIDTH / 2
                for ent, base, side in door.panels:
                    off = side * hw * .95 * door.open_amount
                    if door.axis == "x":
                        ent.position = (base.x, base.y, base.z + off)
                    else:
                        ent.position = (base.x + off, base.y, base.z)
            self._update_door_light(door)
        for gr in self.grille_visuals:
            target = 80 if gr.opened else 0
            if abs(gr.angle - target) > .5:
                gr.angle += (target - gr.angle) * min(1, dt * 6)
                ox, oz = gr.open_dir
                if gr.axis == "x":
                    gr.pivot.rotation_z = gr.angle * ox
                else:
                    gr.pivot.rotation_x = -gr.angle * oz
        for a in list(self.animated):
            a.update(dt)
        for u in self.updatables:
            u.update(dt)
        if getattr(self, "holo", None):
            self.holo.rotation_y += dt * 20
            self.holo.scale_y = .8 + .05 * math.sin(self.time * 3)
        # culling par distance
        self.cull_timer -= dt
        if self.cull_timer <= 0 and fps_mode:
            self.cull_timer = 0.3
            for g in self.groups.values():
                on = g.distance_to(cam_pos[0], cam_pos[2]) < C.CULL_DISTANCE
                if on != g.enabled:
                    g.enabled = on
                    g.root.enabled = on

    def _update_door_light(self, door):
        """Voyants de porte : éteints sans courant (sauf verrou sur batterie qui clignote)."""
        if door.unpowered:
            if door.locked:
                st = "lock_on" if (self.time * 1.2) % 1 < .5 else "off"
            else:
                st = "off"
        else:
            st = "green" if door.open_amount > .5 else "red"
        if st == door.light_state:
            return
        door.light_state = st
        for l in door.status_light:
            if st == "off":
                l.clearLight()
                l.color = color.rgb(.3, .3, .32)
            else:
                l.setLightOff(1)
                l.color = color.lime if st == "green" else color.rgb(1, .08, .04)

    def show_only(self, room_ids):
        """Phase TPS : seul le hangar est visible."""
        for key, g in self.groups.items():
            on = key[0] == "room" and key[1] in room_ids
            g.enabled = on
            g.root.enabled = on
