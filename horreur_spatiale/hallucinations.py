# -*- coding: utf-8 -*-
"""
hallucinations.py — SINUS dans la tête du joueur.

Le joueur respire l'air du Kerguelen dès le hangar : une jauge d'infection
invisible monte avec le temps passé à bord. Des indices rares, subtils et
jamais expliqués apparaissent (de plus en plus au fil de l'infection) :
  * bruits de pas derrière soi, chuchotements sans source ;
  * silhouette au bout d'un couloir, qui disparaît dès qu'on l'éclaire ;
  * un document déjà lu dont une phrase a changé à la relecture ;
  * porte qu'on vient de passer qui se retrouve refermée ;
  * plus tard : une voix qui appelle depuis un conduit.

Revelation : la séquence du disque dur (fichier Helios + vidéo de Keating),
puis « l'hallucination tombe » quelques secondes (les créatures tuées
redeviennent des câbles, des objets et des combinaisons vides, les traces
de griffes disparaissent, les impacts de balles restent)... avant de revenir
en pire.
"""
import math
import random

from ursina import Entity, color, destroy

import config as C
import story
from generator import ekey, ROOM, CORR
from geometry import MeshBuilder
from lighting import mark_emissive


# ============================================================================
class Hallucinations:
    def __init__(self, game):
        self.game = game
        self.infection = C.INFECTION_START
        self.timer = random.uniform(*C.HALLU_FIRST_DELAY)
        self.queue = []                 # [(instant, fonction)] : petites séquences (pas successifs)
        self.t = 0.0
        self.door_log = []              # [(porte, instant)] portes franchies récemment
        self._last_cell = None
        self.silhouette = None
        self.sil_timer = 0.0
        self.paused = False             # pendant la révélation / le screamer
        self.hum = game.audio.loop("sinus_low", "sinus_chant", 1.0, ambient=True)

    # ------------------------------------------------------------------
    def variant_active(self, doc, read_count):
        """Une phrase change à la RELECTURE, une fois l'infection assez avancée."""
        return bool(doc.get("variants")) and read_count >= 1 and self.infection >= C.HALLU_VARIANT_AT

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        p = g.player
        if p is None:
            return
        self.t += dt
        self.infection = min(1.0, self.infection + dt / C.INFECTION_TIME)
        # bourdonnement à 7 Hz, à peine perceptible, qui s'installe avec l'infection
        if g.revelation is None or not g.revelation.active:
            self.hum.set(C.HALLU_HUM * self.infection, fade=.3)
        # séquences en cours
        for item in list(self.queue):
            if self.t >= item[0]:
                self.queue.remove(item)
                try:
                    item[1]()
                except Exception as exc:          # un effet raté ne doit jamais casser la partie
                    print("[hallucination]", exc)
        self._track_doors()
        self._update_silhouette(dt)
        if self.paused or (g.screamer is not None and g.screamer.active) or g.horror.active:
            return
        self.timer -= dt
        if self.timer > 0:
            return
        self.timer = random.uniform(*C.HALLU_INTERVAL) * (1.3 - .6 * self.infection)
        self._event()

    def _event(self):
        """Tire un indice parmi ceux que l'infection permet."""
        inf = self.infection
        opts = []
        for name, level, w in (("steps", .08, 3), ("whisper", .18, 2), ("silhouette", .3, 2), ("door", .35, 2),
                               ("voice", .6, 1)):
            if inf >= level:
                opts.append((name, w))
        if not opts:
            return
        total = sum(w for _, w in opts)
        r = random.uniform(0, total)
        for name, w in opts:
            r -= w
            if r <= 0:
                getattr(self, "_do_" + name)()
                return

    # ------------------------------------------------------------------
    # INDICES
    # ------------------------------------------------------------------
    def _behind(self, dist):
        p = self.game.player
        fx, fz = p.forward2()
        a = math.atan2(-fx, -fz) + random.uniform(-.7, .7)
        return (p.x + math.sin(a) * dist, 1.0, p.z + math.cos(a) * dist)

    def _do_steps(self):
        """Quelques pas derrière le joueur, puis plus rien."""
        pos = self._behind(random.uniform(4, 6.5))
        for k in range(random.randint(3, 5)):
            self.queue.append((self.t + k * .52, lambda: self.game.audio.play_at(
                f"step{random.randint(0, 3)}", pos, .45, random.uniform(.85, .95))))

    def _do_whisper(self):
        pos = self._behind(random.uniform(2.5, 5))
        self.game.audio.play_var("whisper", 3, .5, pos=pos, pitch_range=(.9, 1.05))

    def _do_voice(self):
        """Une voix qui appelle depuis la grille d'aération la plus proche."""
        g = self.game
        p = g.player
        best = None
        for gr in g.level.grilles.values():
            d = math.hypot(gr.pos[0] - p.x, gr.pos[1] - p.z)
            if 3 < d < 18 and (best is None or d < best[0]):
                best = (d, gr)
        if best is None:
            self._do_whisper()
            return
        gr = best[1]
        g.audio.play_at("voice_call", (gr.pos[0], .6, gr.pos[1]), .75, random.uniform(.92, 1.02), occluded=True)

    def _do_door(self):
        """Une porte qu'on vient de passer se retrouve refermée (sans bruit, hors de la vue)."""
        g = self.game
        p = g.player
        fx, fz = p.forward2()
        for door, t0 in list(self.door_log):
            if not (3 < self.t - t0 < 25):
                continue
            dx, dz = door.pos[0] - p.x, door.pos[1] - p.z
            d = math.hypot(dx, dz)
            if d < 4 or d > 20 or door.locked or door.open_amount < .5:
                continue
            if (dx * fx + dz * fz) / d > .2:          # le joueur la regarde : pas maintenant
                continue
            cr = g.creature
            if cr is not None and cr.visible and math.hypot(cr.x - door.pos[0], cr.z - door.pos[1]) < 6:
                continue
            door.target = 0.0
            door.open_amount = 0.0
            door.timer = 0.0
            if door.unpowered:
                door.jam = "closed"
            self.door_log.remove((door, t0))
            return
        self._do_steps()

    def _do_silhouette(self):
        """Silhouette au bout d'un couloir : elle disparaît quand on l'éclaire ou qu'on approche."""
        g = self.game
        p = g.player
        L = g.level
        lamp = g.lights.flashlight_on
        # hors du faisceau si la lampe est allumée (vue du coin de l'œil)
        off = random.choice((-1, 1)) * (random.uniform(30, 40) if lamp else random.uniform(0, 12))
        a = math.radians(p.yaw + off)
        dx, dz = math.sin(a), math.cos(a)
        dist, _, _ = L.raycast(p.x, 1.2, p.z, dx, 0, dz, 24)
        if dist < 9:
            self._do_whisper()
            return
        d = min(dist - .7, random.uniform(10, 14))
        x, z = p.x + dx * d, p.z + dz * d
        i, j = L.cell_at(x, z)
        if not L.inside(i, j) or L.kind[i][j] not in (ROOM, CORR) or L.ceiling(i, j) < 2.6:
            self._do_whisper()
            return
        if self.silhouette is None:
            self.silhouette = _build_silhouette()
        s = self.silhouette
        s.position = (x, 0, z)
        s.rotation_y = math.degrees(math.atan2(p.x - x, p.z - z))
        s.enabled = True
        self.sil_timer = random.uniform(3.5, 6.0)

    def _update_silhouette(self, dt):
        s = self.silhouette
        if s is None or not s.enabled:
            return
        g = self.game
        p = g.player
        self.sil_timer -= dt
        dx, dz = s.x - p.x, s.z - p.z
        d = math.hypot(dx, dz) or 1
        fx, fz = p.forward2()
        ang = math.degrees(math.acos(max(-1, min(1, (dx * fx + dz * fz) / d))))
        lit = g.lights.flashlight_on and g.lights.flashlight_level > .2 and ang < C.FLASHLIGHT_FOV / 2 + 4 and d < 19
        if lit or d < 6.5 or self.sil_timer <= 0:
            s.enabled = False

    def _track_doors(self):
        """Mémorise les portes que le joueur vient de franchir."""
        g = self.game
        p = g.player
        c = g.level.cell_at(p.x, p.z)
        prev = self._last_cell
        self._last_cell = c
        if prev is None or prev == c or abs(prev[0] - c[0]) + abs(prev[1] - c[1]) != 1:
            return
        door = g.level.doors.get(ekey(prev[0], prev[1], c[0], c[1]))
        if door is not None:
            self.door_log.append((door, self.t))
            self.door_log = self.door_log[-4:]

    def hide_all(self):
        if self.silhouette is not None:
            self.silhouette.enabled = False

    def destroy(self):
        if self.silhouette is not None:
            destroy(self.silhouette)
            self.silhouette = None
        self.game.audio.stop_loop("sinus_low")


def _build_silhouette():
    """Longue silhouette maigre (membres trop fins), sombre, avec deux points blancs pour les yeux."""
    mb = MeshBuilder()
    dark = (.03, .03, .035)
    mb.box((0, 1.25, 0), (.34, 1.1, .2), dark)             # torse étroit
    mb.box((0, 2.05, .02), (.22, .32, .22), dark)          # tête
    for s in (-1, 1):
        mb.box((s * .12, .45, 0), (.09, .9, .09), dark)    # jambes
        mb.box((s * .24, 1.1, 0), (.06, 1.5, .06), dark)   # bras interminables
    root = Entity(name="silhouette", enabled=False)
    mb.build(parent=root, name="silhouette_body")
    ey = MeshBuilder()
    for s in (-1, 1):
        ey.box((s * .06, 2.08, .135), (.06, .04, .01), (1, 1, 1))
    eyes = ey.build(parent=root, name="silhouette_eyes")
    mark_emissive(eyes)
    eyes.setFogOff(1)            # deux points blancs qui percent le noir
    return root


# ============================================================================
class Revelation:
    """La vérité (disque dur), l'hallucination qui tombe... et qui revient, en pire."""

    def __init__(self, game):
        self.game = game
        self.active = False
        self.done = False
        self.t = 0.0
        self.phase = None
        self.props = []
        self._glitch_t = 0.0

    def begin(self):
        """Le joueur branche le disque dur sur la console : lecture des deux fichiers."""
        g = self.game
        if self.active or self.done:
            return
        g.docs.hdd_found = True
        g.audio.play("static_burst", .8)
        g.hud.message("Disque dur branché sur la console de la passerelle...", color.rgb(.7, .9, .8))
        g.hallu.paused = True
        # les créatures se tiennent tranquilles pendant la lecture
        if g.aliens is not None:
            g.aliens.suspended = True
        if g.creature is not None:
            g.creature.suspended = True
        g.reader.open([story.HDD_CLASSIFIED, story.HDD_KEATING], on_close=self.start)

    def start(self):
        g = self.game
        self.active = True
        self.t = 0.0
        self.phase = "glitch"
        g.hud.suit_log(story.SUIT_LOG, 10.0)
        g.audio.play("glitch_burst", 1.0)
        g.hallu.hum.set(1.0, fade=1.2)
        g.inp.rumble(.6, .6, 500)

    def update(self, dt):
        if not self.active:
            return
        g = self.game
        self.t += dt
        t = self.t
        fl = g.lights.flashlight
        if self.phase == "glitch":
            # l'écran glitche, le bourdonnement monte, les lumières clignotent
            k = min(1.0, t / 2.5)
            g.hud.glitch_level = .25 + .75 * k
            fl.scare_mult = 1.0 if random.random() > .35 * k else .1
            g.lights.glitch = k
            g.shake(.1 * k)
            if t > 1.3 and self._glitch_t == 0:
                self._glitch_t = 1
                g.audio.play("glitch_burst", .9, 1.2)
            if t >= 2.5:
                self._truth()
        elif self.phase == "truth":
            g.hud.glitch_level = .1 + .05 * math.sin(t * 7)
            fl.scare_mult = 1.0
            g.lights.glitch = 0.0
            if t >= 2.5 + C.REVEAL_TRUTH_TIME:
                self._return()
        elif self.phase == "return":
            k = max(0.0, 1 - (t - self.t_return) / 1.5)
            g.hud.glitch_level = k
            fl.scare_mult = 1.0 if random.random() > .5 * k else .1
            g.lights.glitch = k
            if k <= 0:
                self.finish()
                g.hallu.paused = False
                g.hallu.hum.set(.3, fade=.5)

    # ------------------------------------------------------------------
    def _truth(self):
        """L'hallucination tombe : il n'y a jamais eu de créatures."""
        g = self.game
        self.phase = "truth"
        g.audio.play("glitch_burst", 1.0, .8)
        g.hud.glitch_level = 1.0
        g.hud.truth_level = 1.0
        cr = g.creature
        if cr is not None:
            cr.root.enabled = False
            cr.visible = False
            cr.growl.set(0)
        al = g.aliens
        positions = []
        if al is not None:
            positions += list(al.kill_positions)
            for a in al.aliens:
                positions.append((a.x, a.z))
            al.set_visible(False)
        g.horror.timer = 0
        g.horror.level = 0
        g.hallu.hide_all()
        g.builder.set_claws_visible(False)
        rng = random.Random(len(positions) + 17)
        for (x, z) in positions:
            self.props.append(_truth_prop(x, z, rng))
        if not positions:
            # même sans victime : des câbles arrachés là où « elles » sortaient
            p = g.player
            for k in range(3):
                a = rng.uniform(0, 6.28)
                self.props.append(_truth_prop(p.x + math.cos(a) * 4, p.z + math.sin(a) * 4, rng))

    def _return(self):
        """Tout revient, en pire."""
        g = self.game
        self.phase = "return"
        self.t_return = self.t
        for pr in self.props:
            destroy(pr)
        self.props = []
        g.hud.truth_level = 0.0
        g.builder.set_claws_visible(True)
        g.audio.play("glitch_burst", 1.0, .7)
        g.audio.play("creature_roar", 1.0, .75)
        g.inp.rumble(1, 1, 900)
        g.shake(.8)
        al = g.aliens
        if al is not None:
            al.set_visible(True)
            al.suspended = False
            al.bonus_cap = C.REVEAL_EXTRA_ALIENS
            al.rest = 0.0
            al.grace = 0.0
        cr = g.creature
        if cr is not None:
            cr.suspended = False
            self._creature_between()
        g.horror.trigger(None, scripted=True, duration=35)
        if al is not None:
            al.spawn_near_player(3, aware=True)
            g.hallu.queue.append((g.hallu.t + 6.0, lambda: al.spawn_near_player(3, aware=True)))
        g.hud.message("OBJECTIF : " + story.FINAL_OBJECTIVE, color.rgb(1, .85, .4))

    def _creature_between(self):
        """La grande créature apparaît entre le joueur et le hangar."""
        g = self.game
        L = g.level
        p = g.player
        cr = g.creature
        hangar = L.room("hangar")
        goal = (hangar.x + hangar.w // 2, hangar.y + hangar.h - 1)
        path = L.find_path(L.cell_at(p.x, p.z), goal, "creature", 9000)
        cell = None
        if path:
            acc = 0.0
            for a, b in zip(path, path[1:]):
                acc += C.CELL
                if acc >= C.REVEAL_CREATURE_DIST:
                    cell = b
                    break
            cell = cell or path[len(path) // 2]
        if cell is None:
            cell = L.random_cell(near=(p.x, p.z), radius=20, min_radius=10)
        if cell is None:
            return
        cr.appear_at(*L.cell_center(*cell))
        cr.investigate(p.x, p.z)

    def finish(self):
        """Termine proprement la séquence (décollage, fin de partie)."""
        g = self.game
        for pr in self.props:
            destroy(pr)
        self.props = []
        if self.active or self.phase is not None:
            self.done = True
        self.active = False
        self.phase = None
        g.hud.glitch_level = 0.0
        g.hud.truth_level = 0.0
        if g.lights is not None:
            g.lights.glitch = 0.0
            g.lights.flashlight.scare_mult = 1.0
        if g.builder is not None:
            g.builder.set_claws_visible(True)
        if g.aliens is not None:
            g.aliens.suspended = False
        if g.creature is not None:
            g.creature.suspended = False

    def debug_start(self):
        """F7 : révélation immédiate (donne le disque dur si besoin)."""
        g = self.game
        if not g.has_hdd():
            g.inventory.add("hdd", 1)
            if g.builder.hdd is not None and not g.builder.hdd.taken:
                g.builder.hdd.taken = True
                destroy(g.builder.hdd.entity)
                g.level.remove_interactable(g.builder.hdd)
        self.done = False
        self.begin()

    def destroy(self):
        for pr in self.props:
            destroy(pr)
        self.props = []


def _truth_prop(x, z, rng):
    """Ce qu'il y avait VRAIMENT : câbles arrachés, objets, combinaison vide."""
    mb = MeshBuilder()
    kind = rng.choice(("cables", "cables", "suit", "objects"))
    if kind in ("cables", "objects"):
        for _ in range(rng.randint(5, 9)):
            ln = rng.uniform(.5, 1.3)
            yaw = rng.uniform(0, 180)
            mb.box_rot((x + rng.uniform(-.35, .35), .03 + rng.uniform(0, .05), z + rng.uniform(-.35, .35)),
                       (.035, .035, ln), yaw, rng.choice([(.05, .05, .05), (.5, .1, .08), (.1, .2, .45)]))
        if kind == "objects":
            mb.box_rot((x + .3, .12, z - .2), (.35, .24, .25), rng.uniform(0, 90), (.55, .45, .12))    # boîte à outils
            mb.cylinder((x - .3, .08, z + .2), .09, .16, (.6, .6, .62), 10)                            # gourde
    else:
        # combinaison vide, affaissée au sol
        suit = (.55, .5, .42)
        yaw = rng.uniform(0, 180)
        mb.box_rot((x, .09, z), (.46, .16, .7), yaw, suit)
        a = math.radians(yaw)
        for s in (-1, 1):
            mb.box_rot((x + math.cos(a) * s * .3, .06, z - math.sin(a) * s * .3), (.13, .11, .6), yaw + s * 25, suit)
            mb.box_rot((x + math.sin(a) * .7 + math.cos(a) * s * .12, .07, z + math.cos(a) * .7 - math.sin(a) * s * .12),
                       (.15, .12, .75), yaw, suit)
        mb.cylinder((x - math.sin(a) * .5, .15, z - math.cos(a) * .5), .16, .28, (.2, .22, .25), 12)   # casque
    root = Entity(name="truth_prop")
    mb.build(parent=root, name="truth_mesh")
    return root
