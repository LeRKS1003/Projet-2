# -*- coding: utf-8 -*-
"""
guidance.py — Guidage vers l'objectif en cours.

  * la flèche du haut de l'écran ne pointe plus en ligne droite à travers
    les murs : elle suit le VRAI chemin calculé par A* (couloirs, portes) et
    vise le prochain virage visible du trajet ;
  * marqueur de destination : posé sur l'objectif quand il est à l'écran,
    collé au bord de l'écran quand il est hors champ, avec le nom de la pièce
    et la distance (en mètres, le long du chemin) ;
  * flèche plus lisible : plus grande, contour sombre (lisible sur fond clair
    comme sombre), légère pulsation, couleur réglable (config.GUIDE_COLOR) ;
  * traits lumineux discrets au sol le long du chemin, pendant quelques
    secondes, à la demande (touche G / flèche bas de la manette) ;
  * pendant une crise de vertige (game.vertigo.level), le guidage tremble et
    clignote sans jamais disparaître complètement.
"""
import math
import random

from panda3d.core import Point3, Point2
from ursina import Entity, Text, camera, color, application, window

import config as C
import textures
from generator import VENT
from lighting import additive


def _rgb(c, a=1.0):
    return color.rgba(c[0], c[1], c[2], a)


class Guidance:
    def __init__(self, game):
        self.game = game
        self.level = game.level
        self.t = 0.0
        self.path = None             # liste de cases (i, j) du joueur jusqu'à l'objectif
        self.path_len = 0.0          # longueur du trajet (mètres)
        self.goal = None             # (x, z, libellé)
        self._goal_cell = None
        self._repath = 0.0
        self._last_cell = None
        self.waypoint = None         # prochain point visé (x, z)
        self.trail_t = 0.0           # temps restant d'affichage des traits au sol
        self._trail_cd = 0.0
        self.trail = []
        col = C.GUIDE_COLOR
        ui = game.hud.fps
        s = C.GUIDE_ARROW_SIZE
        # --- flèche du haut : contour sombre + remplissage coloré -------------
        self.arrow_root = Entity(parent=ui, position=(0, .405))
        self.arrow_shadow = Entity(parent=self.arrow_root, model='quad', texture=textures.get('guide_arrow'),
                                   color=color.rgba(0, 0, 0, .75), scale=s * 1.28, z=.01)
        self.arrow = Entity(parent=self.arrow_root, model='quad', texture=textures.get('guide_arrow'),
                            color=_rgb(col), scale=s)
        self.label = Text(parent=ui, text='', position=(0, .36), origin=(0, 0), scale=.75,
                          color=_rgb(col, .9))
        self.label_bg = Text(parent=ui, text='', position=(.0015, .3585), origin=(0, 0), scale=.75,
                             color=color.rgba(0, 0, 0, .8), z=.01)
        # --- marqueur de destination (dans le champ ou en bord d'écran) -------
        self.marker = Entity(parent=ui, model='quad', texture=textures.get('guide_marker'),
                             color=_rgb(col, .9), scale=.034)
        self.marker_edge = Entity(parent=self.marker, model='quad', texture=textures.get('guide_arrow'),
                                  color=_rgb(col, .9), scale=.7, y=.9)
        self.marker_text = Text(parent=ui, text='', scale=.62, origin=(0, 0), color=_rgb(col, .95))
        self.marker_text_bg = Text(parent=ui, text='', scale=.62, origin=(0, 0), color=color.rgba(0, 0, 0, .85),
                                   z=.01)
        # --- traits au sol ----------------------------------------------------
        self.trail_root = Entity(parent=game.world_root, name="guide_trail")
        additive(self.trail_root, 6)
        self.trail_root.setTwoSided(True)
        self.set_visible(False)

    # ------------------------------------------------------------------
    def set_visible(self, on):
        for e in (self.arrow_root, self.label, self.label_bg, self.marker, self.marker_text, self.marker_text_bg):
            e.enabled = on

    def destroy(self):
        from ursina import destroy
        for e in (self.arrow_root, self.label, self.label_bg, self.marker, self.marker_text, self.marker_text_bg):
            destroy(e)
        self.clear_trail()
        destroy(self.trail_root)

    # ------------------------------------------------------------------
    # CHEMIN
    # ------------------------------------------------------------------
    def _compute_path(self, p):
        L = self.level
        start = L.nearest_linked_cell(p.x, p.z, 2)
        goal = self._goal_cell
        if start is None or goal is None:
            self.path = None
            return
        path = L.find_path(start, goal, agent="player", max_nodes=9000)
        if path is None:
            # porte verrouillée sur le trajet : on guide quand même jusqu'à elle
            path = L.find_path(start, goal, agent="creature", max_nodes=9000)
        self.path = path
        self.path_len = 0.0
        if path:
            prev = (p.x, p.z)
            for c in path[1:]:
                cx, cz = L.cell_center(*c)
                self.path_len += math.hypot(cx - prev[0], cz - prev[1])
                prev = (cx, cz)
            self.path_len += math.hypot(self.goal[0] - prev[0], self.goal[1] - prev[1])

    def _visible(self, x0, z0, x1, z1):
        """Ligne de vue au niveau du torse entre deux points (murs et portes fermées bloquent)."""
        dx, dz = x1 - x0, z1 - z0
        d = math.hypot(dx, dz)
        if d < .05:
            return True
        hit, _, _ = self.level.raycast(x0, 1.1, z0, dx / d, 0, dz / d, d)
        return hit >= d - .2

    def _next_waypoint(self, p):
        """Le prochain virage : le point le plus lointain du trajet encore visible depuis le joueur."""
        L = self.level
        if not self.path:
            return (self.goal[0], self.goal[1])
        pts = [L.cell_center(*c) for c in self.path[1:C.GUIDE_LOOKAHEAD + 1]]
        if len(self.path) <= C.GUIDE_LOOKAHEAD + 1:
            pts.append((self.goal[0], self.goal[1]))
        best = pts[0] if pts else (self.goal[0], self.goal[1])
        for q in pts:
            # un peu de marge latérale : on teste aussi deux rayons décalés (épaisseur du joueur)
            if self._visible(p.x, p.z, q[0], q[1]):
                best = q
            else:
                break
        return best

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        g = self.game
        p = g.player
        self.t += dt
        goal = g.objective_goal() if C.OBJECTIVE_COMPASS else None
        if p is None or goal is None or g.state != "fps":
            self.set_visible(False)
            self._fade_trail(dt)
            return
        self.set_visible(True)
        L = self.level
        # nouvel objectif ou objectif déplacé : on recalcule tout de suite
        if self.goal is None or goal[2] != self.goal[2] or math.hypot(goal[0] - self.goal[0],
                                                                     goal[1] - self.goal[1]) > .5:
            self.goal = goal
            self._goal_cell = L.nearest_linked_cell(goal[0], goal[1])
            self._repath = 0.0
        cell = L.cell_at(p.x, p.z)
        self._repath -= dt
        if self._repath <= 0 or cell != self._last_cell:
            self._repath = C.GUIDE_REPATH_TIME
            self._last_cell = cell
            self._compute_path(p)
        self.waypoint = self._next_waypoint(p)
        dist = self.path_len if self.path else math.hypot(goal[0] - p.x, goal[1] - p.z)
        # --- instabilité pendant les vertiges -------------------------------
        vl = 0.0
        vg = getattr(g, "vertigo", None)
        if vg is not None:
            vl = vg.guide_instability()
        jitter = (math.sin(self.t * 23) * 14 + random.uniform(-10, 10)) * vl
        blink = 1.0
        if vl > 0:
            blink = .35 + .65 * (1.0 if (self.t * (3 + 5 * vl)) % 1 > .35 * vl else .25)
        # --- flèche vers le prochain virage ---------------------------------
        wx, wz = self.waypoint
        a = math.degrees(math.atan2(wx - p.x, wz - p.z))
        rel = (a - p.yaw + 180) % 360 - 180
        pulse = 1 + C.GUIDE_PULSE * math.sin(self.t * 4.2)
        self.arrow_root.rotation_z = rel + jitter
        self.arrow_root.scale = pulse
        self.arrow_root.x = random.uniform(-.006, .006) * vl
        col = C.GUIDE_COLOR
        self.arrow.color = _rgb(col, blink)
        self.arrow_shadow.color = color.rgba(0, 0, 0, .75 * blink)
        txt = f"{goal[2]}  ·  {dist:.0f} m"
        if self.label.text != txt:
            self.label.text = txt
            self.label_bg.text = txt
        self.label.color = _rgb(col, .9 * blink)
        self.label_bg.color = color.rgba(0, 0, 0, .8 * blink)
        # --- marqueur de destination ----------------------------------------
        self._update_marker(goal, dist, vl, blink)
        # --- traits au sol ---------------------------------------------------
        self._trail_cd = max(0.0, self._trail_cd - dt)
        if C.GUIDE_TRAIL and inp.pressed("guide") and not g.ui_consumed and self._trail_cd <= 0:
            self._trail_cd = C.GUIDE_TRAIL_COOLDOWN
            self.show_trail(p)
        self._fade_trail(dt)

    # ------------------------------------------------------------------
    def _project(self, x, y, z):
        """Projette un point du monde à l'écran. Renvoie (ux, uy, devant) en coordonnées camera.ui."""
        base = application.base
        rel = base.cam.getRelativePoint(base.render, Point3(x, y, z))
        ar = window.aspect_ratio
        if rel.y > .05:
            p2 = Point2()
            if base.camLens.project(rel, p2):
                return p2.x * ar / 2, p2.y * .5, True
            return p2.x * ar / 2, p2.y * .5, rel.y > 0
        # derrière la caméra : on renvoie la direction « écran » inversée
        return rel.x * 10, (rel.z if abs(rel.z) > 1e-3 else -1) * 10, False

    def _update_marker(self, goal, dist, vl, blink):
        if not C.GUIDE_EDGE_MARKER:
            self.marker.enabled = self.marker_text.enabled = self.marker_text_bg.enabled = False
            return
        ux, uy, front = self._project(goal[0], 1.2, goal[1])
        ar = window.aspect_ratio
        mx, my = ar / 2 - .05, .5 - .07
        inside = front and abs(ux) < mx and abs(uy) < my
        if inside:
            x, y = ux, uy
            self.marker_edge.enabled = False
            self.marker.rotation_z = 0
        else:
            # collé au bord de l'écran, dans la direction de l'objectif
            if not front and abs(ux) < 1e-3 and abs(uy) < 1e-3:
                ux, uy = 0, -1
            k = min(mx / max(abs(ux), 1e-5), my / max(abs(uy), 1e-5))
            x, y = ux * k, uy * k
            self.marker_edge.enabled = True
            self.marker.rotation_z = math.degrees(math.atan2(ux, uy))
        x += random.uniform(-.01, .01) * vl
        y += random.uniform(-.01, .01) * vl
        self.marker.position = (x, y)
        self.marker.color = _rgb(C.GUIDE_COLOR, .9 * blink)
        self.marker_edge.color = _rgb(C.GUIDE_COLOR, .9 * blink)
        txt = f"{goal[2]}\n{dist:.0f} m"
        if self.marker_text.text != txt:
            self.marker_text.text = txt
            self.marker_text_bg.text = txt
        # texte à l'intérieur de l'écran par rapport au marqueur
        tx = max(-ar / 2 + .12, min(ar / 2 - .12, x))
        ty = y - .055 if y > -.3 else y + .06
        self.marker_text.position = (tx, ty)
        self.marker_text_bg.position = (tx + .0015, ty - .0015)
        self.marker_text.color = _rgb(C.GUIDE_COLOR, .95 * blink)
        self.marker_text_bg.color = color.rgba(0, 0, 0, .85 * blink)

    # ------------------------------------------------------------------
    # TRAITS LUMINEUX AU SOL
    # ------------------------------------------------------------------
    def clear_trail(self):
        from ursina import destroy
        for e, _ in self.trail:
            destroy(e)
        self.trail = []

    def show_trail(self, p):
        """Dépose des traits lumineux au sol le long du chemin (du joueur jusqu'à l'objectif)."""
        L = self.level
        self.clear_trail()
        if not self.path:
            self._compute_path(p)
        if not self.path:
            return
        pts = [(p.x, p.z)] + [L.cell_center(*c) for c in self.path[1:]] + [(self.goal[0], self.goal[1])]
        # lissage léger des angles (moyenne avec les voisins)
        sm = [pts[0]]
        for k in range(1, len(pts) - 1):
            sm.append(((pts[k - 1][0] + 2 * pts[k][0] + pts[k + 1][0]) / 4,
                       (pts[k - 1][1] + 2 * pts[k][1] + pts[k + 1][1]) / 4))
        sm.append(pts[-1])
        tex = textures.get('guide_dash')
        col = C.GUIDE_TRAIL_COLOR
        acc, total = C.GUIDE_TRAIL_SPACING * .6, 0.0
        for k in range(len(sm) - 1):
            ax, az = sm[k]
            bx, bz = sm[k + 1]
            seg = math.hypot(bx - ax, bz - az)
            if seg < 1e-3:
                continue
            ux, uz = (bx - ax) / seg, (bz - az) / seg
            yaw = math.degrees(math.atan2(ux, uz))
            s = acc
            while s < seg:
                x, z = ax + ux * s, az + uz * s
                i, j = L.cell_at(x, z)
                floor_y = .05 if L.inside(i, j) and L.kind[i][j] == VENT else .025
                e = Entity(parent=self.trail_root, model='quad', texture=tex, color=_rgb(col, 0),
                           position=(x, floor_y, z), rotation=(90, yaw, 0), scale=(.2, .62))
                self.trail.append((e, total + s))
                s += C.GUIDE_TRAIL_SPACING
            acc = s - seg
            total += seg
            if total > C.GUIDE_TRAIL_LENGTH:
                break
        self.trail_t = C.GUIDE_TRAIL_TIME
        self.game.audio.play("beep", .25, 1.4)

    def _fade_trail(self, dt):
        if not self.trail:
            return
        self.trail_t -= dt
        if self.trail_t <= 0:
            self.clear_trail()
            return
        T = C.GUIDE_TRAIL_TIME
        age = T - self.trail_t
        env = min(1.0, age / .5) * min(1.0, self.trail_t / 1.2)
        col = C.GUIDE_TRAIL_COLOR
        vl = 0.0
        vg = getattr(self.game, "vertigo", None)
        if vg is not None:
            vl = vg.guide_instability()
        for e, d in self.trail:
            # une onde lumineuse parcourt le tracé vers l'objectif
            wave = .55 + .45 * max(0.0, math.cos((d - age * 9.0) * .35)) ** 6
            flick = 1.0 if vl <= 0 else (.4 + .6 * random.random() ** vl)
            e.color = _rgb(col, .9 * env * wave * flick)
