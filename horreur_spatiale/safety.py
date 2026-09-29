# -*- coding: utf-8 -*-
"""
safety.py — Apparition sûre du joueur dans le hangar et filet de sécurité.

Séquence d'apparition (après l'atterrissage) :
  1. l'intérieur est déjà généré ; on attend que le sol du hangar soit
     réellement présent dans le graphe de scène (groupe activé, géométrie
     construite) ;
  2. on place le joueur au point d'apparition calculé UNE fois par le
     générateur (LevelBuilder.landing), à côté de la porte latérale de la
     navette, face à l'intérieur du hangar ;
  3. on lance un rayon vers le bas (collision Panda3D contre la vraie
     géométrie du sol) pour le poser exactement dessus ;
  4. seulement ensuite on rend les contrôles (et la « gravité » : hauteur
     des pieds suivie en continu).

Vérifications :
  * juste après le placement : le joueur doit être dans les limites du
    hangar, sinon il est remis au point d'apparition (message terminal) ;
  * en continu pendant la partie : s'il sort du vaisseau (case pleine, hors
    de la grille, chute sous le sol...), il est replacé au dernier point sûr.
"""
import math

from panda3d.core import (CollisionTraverser, CollisionHandlerQueue, CollisionNode, CollisionRay,
                          GeomNode, BitMask32)
from ursina import application

import config as C
from generator import SOLID


def floor_raycast(root, x, z, y0=None):
    """
    Lance un rayon vertical vers le bas à la position (x, z) contre toute la
    géométrie visible sous 'root'. Renvoie la hauteur du sol touché, ou None
    si rien n'est touché (sol pas encore chargé / masqué).
    Les coordonnées Ursina et Panda3D sont identiques (y vers le haut dans le jeu).
    """
    if root is None or root.isEmpty():
        return None
    y0 = C.SPAWN_RAY_HEIGHT if y0 is None else y0
    render = application.base.render
    trav = CollisionTraverser("rayon_sol")
    queue = CollisionHandlerQueue()
    node = CollisionNode("rayon_sol")
    node.addSolid(CollisionRay(x, y0, z, 0, -1, 0))         # vers le bas
    node.setFromCollideMask(GeomNode.getDefaultCollideMask())
    node.setIntoCollideMask(BitMask32.allOff())
    ray_np = render.attachNewNode(node)
    try:
        trav.addCollider(ray_np, queue)
        trav.traverse(root)
        best = None
        for k in range(queue.getNumEntries()):
            e = queue.getEntry(k)
            h = e.getSurfacePoint(render).y
            # on garde la surface la plus haute sous l'origine du rayon, dans une plage « sol »
            if -1.0 <= h <= 1.2 and (best is None or h > best):
                best = h
        return best
    finally:
        ray_np.removeNode()


class SpawnGuard:
    """Place le joueur de façon fiable puis le surveille pendant toute la partie."""

    def __init__(self, game):
        self.game = game
        self.state = "idle"          # idle -> pending (attente du sol) -> ok
        self.frames = 0
        self.landing = None
        self.last_safe = None
        self._save_t = 0.0
        self.rescues = 0

    # ------------------------------------------------------------------
    def _hangar_root(self):
        g = self.game
        hangar = g.level.room("hangar")
        grp = g.builder.groups.get(("room", hangar.id))
        return grp.root if grp is not None else None

    def begin(self, player, landing):
        """Étape 2 : position et orientation fixes, contrôles bloqués jusqu'à la pose au sol."""
        self.landing = landing
        sx, sz = landing["spawn"]
        player.x, player.z = sx, sz
        player.yaw = landing["spawn_yaw"]
        player.pitch = 0.0
        player.vx = player.vz = 0.0
        player.y = 0.0
        player.spawn_lock = True
        self.state = "pending"
        self.frames = 0
        self.last_safe = (sx, sz)
        print(f"[apparition] joueur placé au point prévu ({sx:.2f}, {sz:.2f}), cap {player.yaw:.0f}°, "
              "attente du sol du hangar...")

    def respawn(self, reason):
        """Remet le joueur au point d'apparition (utilisé aussi par la touche F9)."""
        p = self.game.player
        if p is None or self.landing is None:
            return
        print(f"[apparition] {reason} -> retour au point d'apparition du hangar")
        self.begin(p, self.landing)

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        p = g.player
        if p is None or self.state == "idle":
            return
        if self.state == "pending":
            self._try_ground(p)
            return
        if C.SAFETY_CHECK:
            self._watch(p, dt)

    def _try_ground(self, p):
        """Étapes 3 et 4 : rayon vers le bas, pose exacte, puis contrôles rendus."""
        self.frames += 1
        root = self._hangar_root()
        loaded = root is not None and not root.isStashed() and not root.isHidden()
        h = floor_raycast(root, p.x, p.z) if loaded else None
        if h is None and self.frames < C.SPAWN_MAX_WAIT_FRAMES:
            return                                  # sol pas encore prêt : on attend l'image suivante
        if h is None:
            h = 0.0
            print("[apparition] ATTENTION : sol du hangar introuvable par rayon, repli à y = 0")
        p.y = h
        # vérification immédiate : dans les limites du hangar ?
        x0, x1, z0, z1 = self.landing["hangar_bounds"]
        if not (x0 < p.x < x1 and z0 < p.z < z1) or p.y < C.SAFETY_MIN_Y:
            sx, sz = self.landing["spawn"]
            print(f"[apparition] joueur hors du hangar ({p.x:.2f}, {p.z:.2f}) -> replacé en ({sx:.2f}, {sz:.2f})")
            p.x, p.z = sx, sz
            p.y = 0.0
        p.spawn_lock = False
        self.state = "ok"
        self.last_safe = (p.x, p.z)
        self._save_t = 0.0
        print(f"[apparition] joueur posé sur le sol du hangar (y = {p.y:.3f}) après {self.frames} image(s)")

    def position_ok(self, p):
        """Le joueur est-il à un endroit valide du vaisseau ?"""
        L = self.game.level
        if not (math.isfinite(p.x) and math.isfinite(p.z)):
            return False
        i, j = L.cell_at(p.x, p.z)
        if not L.inside(i, j) or L.kind[i][j] == SOLID:
            return False
        return p.y >= C.SAFETY_MIN_Y

    def _watch(self, p, dt):
        """Filet de sécurité continu : dernier point sûr mémorisé, replacement si besoin."""
        if p.hidden_in is not None:
            return
        if self.position_ok(p):
            self._save_t -= dt
            if self._save_t <= 0:
                self._save_t = C.SAFETY_SAVE_INTERVAL
                self.last_safe = (p.x, p.z)
            return
        self.rescues += 1
        bad = (p.x, p.z)
        lx, lz = self.last_safe if self.last_safe else self.landing["spawn"]
        p.x, p.z = lx, lz
        p.y = 0.0
        p.vx = p.vz = 0.0
        print(f"[sécurité] joueur sorti du vaisseau en ({bad[0]:.2f}, {bad[1]:.2f}) -> replacé au dernier point "
              f"sûr ({lx:.2f}, {lz:.2f})")
