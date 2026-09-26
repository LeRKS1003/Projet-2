# -*- coding: utf-8 -*-
"""
power.py — Le courant du vaisseau, côté gameplay.

Au début de la phase FPS, le Kerguelen est mort : plus aucune lumière, les
portes coulissantes ne fonctionnent plus (entrouvertes, à forcer ou
bloquées) et la salle de commandement est verrouillée électriquement.

Pour rétablir le courant, le joueur doit retrouver 2 ou 3 fusibles (salle
des machines et salles voisines), les insérer dans le tableau électrique
principal puis abaisser le gros levier. Séquence scriptée :
  1. silence, puis le réacteur démarre (grondement qui monte, vibrations,
     secousses de caméra) ;
  2. le réacteur central s'illumine progressivement ;
  3. la lumière revient salle par salle depuis la salle des machines (bruit
     de relais à chaque allumage) ;
  4. chaque néon clignote avant de rester allumé, écrans et consoles
     s'allument ; 20 à 30 % des lampes restent cassées ;
  5. pic de tension : le vacarme alerte la grande créature, de petites
     créatures sortent des conduits.
Ensuite, de rares coupures temporaires surviennent (surtout en mode
horreur ou quand la grande créature est proche).

L'état des lumières elles-mêmes est géré par lighting.PowerManager.
"""
import math
import random
from collections import deque

from ursina import color, Vec3

import config as C
import loot
from generator import ekey


class PowerPanel(loot.Interactable):
    """Tableau électrique principal de la salle des machines."""
    radius = 2.4

    def __init__(self, system, level, spec):
        self.system = system
        self.pos = spec["pos"]
        self._told = False
        level.add_interactable(self, self.pos[0], self.pos[2])

    def prompt(self, game):
        ps = self.system
        if ps.state != "off":
            return None
        missing = ps.fuses_needed - ps.fuses_inserted
        if missing > 0:
            if ps.fuses_held > 0:
                return f"Insérer les fusibles ({ps.fuses_inserted + min(ps.fuses_held, missing)}/{ps.fuses_needed})"
            return f"Tableau électrique : il manque {missing} fusible" + ("s" if missing > 1 else "")
        return "Abaisser le levier principal"

    def interact(self, game):
        ps = self.system
        if ps.state != "off":
            return
        missing = ps.fuses_needed - ps.fuses_inserted
        if missing > 0:
            if ps.fuses_held > 0:
                ps.insert_fuses()
            else:
                game.audio.play_at("beep", self.pos, .5, .8)
                game.hud.message(f"Il manque {missing} fusible{'s' if missing > 1 else ''}. Fouille la salle des "
                                 "machines et les salles voisines (ils brillent à la lampe).", color.orange)
            return
        ps.pull_lever()


class PowerSystem:
    def __init__(self, game, level, builder, rng):
        self.game = game
        self.level = level
        self.builder = builder
        self.pm = game.lights.power
        self.rng = rng
        self.fuses_needed = len(builder.fuses)
        self.fuses_held = 0
        self.fuses_inserted = 0
        self.state = "off" if C.POWER_START_OFF else "on"
        self.seq_t = 0.0
        self._spin_started = False
        self._relay_idx = 0
        self.prop_t0 = 0.0
        self.outage_end = None
        self.outage_timer = C.POWER_OUTAGE_CHECK
        self.last_outage = -1e9
        self._rumble_t = 0.0
        self._led_state = None
        spec = builder.power_panel
        self.spec = spec
        self.panel = PowerPanel(self, level, spec) if spec else None
        self.arm_angle = -40.0
        self.sparks = [[p, rng.uniform(1.0, C.SPARK_INTERVAL[1])] for p in builder.spark_points]
        self._setup_doors()
        if spec is None and self.state == "off":
            # filet de sécurité : aucun emplacement pour le tableau électrique -> courant déjà présent
            print("[courant] tableau électrique introuvable : courant rétabli d'office")
            self.state = "on"
        if self.state == "on":
            self.fuses_inserted = self.fuses_needed
            self.pm.switch_on(0.0, instant=True)
            self._power_doors(True)
        self._update_panel_visuals()

    @property
    def on(self):
        return self.state == "on"

    # ------------------------------------------------------------------
    # PORTES SANS COURANT
    # ------------------------------------------------------------------
    def _setup_doors(self):
        """Tire l'état de chaque porte sans courant, sans jamais rendre le parcours impossible."""
        L = self.level
        rng = self.rng
        for d in L.doors.values():
            d.set_powered(False)
            d.jam = "closed"
        self._lock_command(True)
        doors = [d for d in L.doors.values() if not d.locked]
        rng.shuffle(doors)
        n_stuck = 0
        for d in doors:
            r = rng.random()
            if r < C.DOOR_AJAR_CHANCE:
                d.force_ajar(C.DOOR_AJAR_OPENING)
                d.open_amount = d.target
            elif r < C.DOOR_AJAR_CHANCE + C.DOOR_STUCK_CHANCE:
                d.jam = "stuck"
                # une porte bloquée ne doit jamais couper l'accès à une salle
                # (il reste toujours un détour, souvent par les conduits)
                if not self._all_reachable():
                    d.jam = "closed"
                else:
                    n_stuck += 1
        print(f"[courant] portes : {sum(1 for d in doors if d.jam == 'ajar')} entrouvertes, {n_stuck} bloquées, "
              f"{sum(1 for d in doors if d.jam == 'closed')} à forcer")

    def _lock_command(self, lock):
        room = self.level.room("command")
        if room is None:
            return
        for d in room.doors:
            d.locked = lock
        for gr in room.grilles:
            gr.locked = lock
            if lock and gr.opened:
                gr.set_open(False)

    def _all_reachable(self):
        """Toutes les salles (sauf la passerelle verrouillée) sont-elles accessibles depuis le hangar ?"""
        L = self.level
        hangar = L.room("hangar")
        if hangar is None:
            return True
        start = (hangar.x + hangar.w // 2, hangar.y + hangar.h // 2)
        seen = {start}
        q = deque([start])
        while q:
            c = q.popleft()
            for ni, nj, st in L.links.get(c, ()):
                n = (ni, nj)
                if n in seen:
                    continue
                if st == "door":
                    d = L.doors[ekey(c[0], c[1], ni, nj)]
                    if d.locked or d.jam == "stuck":
                        continue
                elif st == "grille" and L.grilles[ekey(c[0], c[1], ni, nj)].locked:
                    continue
                seen.add(n)
                q.append(n)
        for r in L.rooms:
            if r.type == "command":
                continue
            if not any(c in seen for c in r.cells()):
                return False
        return True

    def _power_doors(self, on):
        for d in self.level.doors.values():
            was_open = d.open_amount > .5
            d.set_powered(on)
            if not on and was_open:
                d.force_ajar(max(d.open_amount, C.DOOR_AJAR_OPENING))
        self._lock_command(not on and not self.game.has_hdd())

    # ------------------------------------------------------------------
    # FUSIBLES ET LEVIER
    # ------------------------------------------------------------------
    def pick_fuse(self):
        self.fuses_held += 1
        got = self.fuses_inserted + self.fuses_held
        self.game.hud.message(f"Fusible récupéré ({got}/{self.fuses_needed})", color.rgb(1, .8, .4))
        if got >= self.fuses_needed:
            self.game.hud.message("Tous les fusibles : direction le tableau électrique de la salle des machines.",
                                  color.rgb(1, .8, .4))

    def insert_fuses(self):
        g = self.game
        n = min(self.fuses_held, self.fuses_needed - self.fuses_inserted)
        self.fuses_held -= n
        self.fuses_inserted += n
        for k in range(n):
            g.audio.play_at("fuse_insert", self.spec["pos"], .9, random.uniform(.95, 1.05))
        g.inp.rumble(.3, .1, 150)
        missing = self.fuses_needed - self.fuses_inserted
        if missing > 0:
            g.hud.message(f"Fusible inséré. Il en manque encore {missing}.", color.rgb(1, .8, .4))
        else:
            g.hud.message("Tous les fusibles sont en place. Abaisse le levier principal.", color.rgb(1, .8, .4))
        self._update_panel_visuals()

    def pull_lever(self):
        """Démarre la séquence scriptée de redémarrage."""
        g = self.game
        if self.state != "off":
            return
        self.state = "restarting"
        self.seq_t = 0.0
        self._spin_started = False
        g.audio.play_at("lever_pull", self.spec["pos"] if self.spec else g.player.pos3, 1.0)
        g.inp.rumble(.6, .3, 250)
        g.hud.message("Le levier s'abaisse avec un claquement sec...", color.rgb(.8, .8, .7))
        # 1. silence : l'ambiance se coupe d'un coup
        g.audio.silence(keep_loops=("reactor",))

    # ------------------------------------------------------------------
    # MISE À JOUR
    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        now = g.lights.time
        # levier animé
        target = 45.0 if self.state != "off" else -40.0
        if abs(self.arm_angle - target) > .3 and self.spec:
            self.arm_angle += (target - self.arm_angle) * min(1.0, dt * 14)
            self.spec["arm"].rotation_x = self.arm_angle
        if self.state == "restarting":
            self._update_restart(dt, now)
        elif self.state == "on":
            self._update_outages(dt, now)
        self._update_sparks(dt)
        self._update_panel_visuals(now)

    def _update_restart(self, dt, now):
        g = self.game
        self.seq_t += dt
        t = self.seq_t
        S, U = C.POWER_SILENCE_TIME, C.POWER_SPINUP_TIME
        rpos = g.builder.reactor_pos or self.spec["pos"]
        if t >= S and not self._spin_started:
            # 2. le réacteur démarre : grondement qui monte en puissance
            self._spin_started = True
            g.audio.play_at("reactor_spinup", rpos, 1.0, max_dist=80, ignore_duck=True)
            g.audio.restore(U * .9)
            g.hud.message("Le réacteur se réveille dans un grondement assourdissant.", color.rgb(.6, .85, 1))
            self._alert_ship(rpos)
        if S <= t < S + U:
            k = (t - S) / U
            self.pm.reactor_level = k ** 1.6
            g.shake(.12 + .4 * k)
            self._rumble_t -= dt
            if self._rumble_t <= 0:
                self._rumble_t = .25
                g.inp.rumble(.3 + .7 * k, .15 + .5 * k, 260)
        if t >= S + U and self.pm.state == "off":
            # 3. la lumière revient, salle par salle, depuis la salle des machines
            self.pm.reactor_level = 1.0
            self.pm.switch_on(now)
            self.prop_t0 = now
            self._relay_idx = 0
            g.audio.play_at("power_thump", rpos, 1.0, max_dist=80, ignore_duck=True)
            g.shake(.7)
            g.inp.rumble(1, .8, 600)
            self._power_doors(True)
        if self.pm.state == "on":
            ev = self.pm.relay_events
            while self._relay_idx < len(ev) and now >= self.prop_t0 + ev[self._relay_idx][0]:
                pos = ev[self._relay_idx][1]
                g.audio.play_at(f"relay{self._relay_idx % 3}", pos, .9, random.uniform(.9, 1.1), max_dist=50)
                self._relay_idx += 1
            if now > self.prop_t0 + self.pm.max_delay + 2.5:
                self.state = "on"
                g.hud.message("Courant rétabli. La passerelle est déverrouillée.", color.lime)

    def _alert_ship(self, rpos):
        """Pic de tension : le vacarme du réacteur réveille tout le vaisseau."""
        g = self.game
        g.horror.trigger(None, scripted=True, duration=25)
        cr = g.creature
        if cr is not None:
            if cr.state == "CACHEE":
                cr.hidden_timer = min(cr.hidden_timer, 3)
            cr.hear(rpos, 999.0, "shot")
        if g.aliens is not None:
            g.aliens.rest = 0.0
            g.aliens.spawn_near_player(self.rng.randint(*C.POWER_ALIENS_ON_RESTART), aware=True)

    def _update_outages(self, dt, now):
        g = self.game
        if self.outage_end is not None:
            if now >= self.outage_end:
                self.outage_end = None
                self.pm.end_outage(now)
                self.last_outage = now
                g.audio.play_var("relay", 3, .8)
                g.audio.play("power_thump", .5, 1.2)
                g.hud.message("Le courant revient.", color.rgb(.7, .8, .8))
            return
        self.outage_timer -= dt
        if self.outage_timer > 0:
            return
        self.outage_timer = C.POWER_OUTAGE_CHECK
        if now - self.last_outage < C.POWER_OUTAGE_MIN_GAP:
            return
        p = C.POWER_OUTAGE_BASE + C.POWER_OUTAGE_HORROR * g.horror.level
        cr, pl = g.creature, g.player
        if cr is not None and cr.visible and pl is not None:
            if math.hypot(cr.x - pl.x, cr.z - pl.z) < C.POWER_OUTAGE_CREATURE_DIST:
                p += C.POWER_OUTAGE_CREATURE
        if random.random() < p:
            self.start_outage(now)

    def start_outage(self, now=None):
        g = self.game
        if self.state != "on" or self.outage_end is not None:
            return          # jamais pendant le redémarrage
        now = g.lights.time if now is None else now
        self.pm.start_outage(now)
        self.outage_end = now + random.uniform(*C.POWER_OUTAGE_DURATION)
        self.last_outage = now
        g.audio.play("power_down", .9)
        g.inp.rumble(.4, .2, 300)

    def _update_sparks(self, dt):
        """Câbles arrachés : gerbes d'étincelles occasionnelles avec un bref flash lumineux."""
        g = self.game
        p = g.player
        if p is None:
            return
        for sp in self.sparks:
            sp[1] -= dt
            if sp[1] > 0:
                continue
            sp[1] = random.uniform(*C.SPARK_INTERVAL)
            pos = sp[0]
            if math.hypot(pos[0] - p.x, pos[2] - p.z) > 18:
                continue
            g.lights.flash(pos, (1, .85, .55), C.SPARK_FLASH * random.uniform(.6, 1.0), 16.0)
            g.audio.play_at("spark", pos, .7, random.uniform(.9, 1.2))
            if g.weapons is not None:
                g.weapons._spawn_sparks(Vec3(*pos), color.rgb(1, .8, .45), random.randint(5, 10), Vec3(0, -1, 0))
            break           # une seule gerbe par image

    def _update_panel_visuals(self, now=0.0):
        """Fusibles visibles dans leurs logements, voyants rouges (manquant, clignotant) ou verts."""
        if not self.spec:
            return
        filled = [k < self.fuses_inserted or k >= self.fuses_needed for k in range(3)]
        blink = (now * 1.5) % 1 < .5
        st = (tuple(filled), blink)
        if st == self._led_state:
            return
        self._led_state = st
        for k in range(3):
            self.spec["fuse_vis"][k].enabled = filled[k]
            led = self.spec["leds"][k]
            if filled[k]:
                led.color = color.rgb(.1, 1, .25)
            else:
                led.color = color.rgb(1, .08, .04) if blink else color.rgb(.25, .02, .01)

    # ------------------------------------------------------------------
    # DEBUG (F4)
    # ------------------------------------------------------------------
    def debug_toggle(self):
        g = self.game
        now = g.lights.time
        if self.state in ("off", "restarting"):
            self.fuses_inserted = self.fuses_needed
            self.fuses_held = 0
            self.state = "on"
            self.pm.switch_on(now, instant=True)
            self.outage_end = None
            self._power_doors(True)
            g.audio.restore(.5)
            g.hud.message("[debug] courant rétabli", color.yellow)
        else:
            # les fusibles restent en place : le levier peut être actionné à nouveau
            self.state = "off"
            self.pm.switch_off()
            self.outage_end = None
            self._power_doors(False)
            g.hud.message("[debug] courant coupé", color.yellow)
        self._update_panel_visuals(now)
