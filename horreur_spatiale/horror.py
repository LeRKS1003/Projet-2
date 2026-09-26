# -*- coding: utf-8 -*-
"""
horror.py — Mode horreur et gestion de la tension.

Un tir (ou un événement scripté) déclenche le MODE HORREUR :
  alarmes, lumières rouges qui clignotent, musique stridente, secousses
  de caméra, vibrations de la manette, la grande créature est alertée et
  des petites créatures sortent des conduits. Le mode dure un moment puis
  retombe progressivement si le joueur se fait discret.

Ce module gère aussi le bruit (propagation vers les créatures), les
battements de cœur quand la grande créature est proche et les événements
d'ambiance aléatoires (grincements, coups dans les conduits...).
"""
import math
import random

from ursina import color

import config as C


class HorrorManager:
    def __init__(self, game):
        self.game = game
        self.level = 0.0          # intensité 0..1
        self.timer = 0.0          # temps restant à pleine intensité
        self.scare = 0.0          # sursaut scripté court
        self.active = False
        self.wave_timer = 0.0
        self.rumble_timer = 0.0
        self.event_timer = random.uniform(12, 25)
        self.heart_timer = 0.0
        self.tension = 0.0        # 0..1 (proximité de la grande créature)
        self.times_triggered = 0
        self.active_time = 0.0    # durée de l'alerte en cours (plafonnée à HORROR_MAX_TIME)
        a = game.audio
        self.alarm = a.loop("alarm", "alarm", .5)
        self.music = a.loop("horror_music", "horror_music", .9, music=True)
        self.drone = a.loop("drone", "tension_drone", .8, music=True)
        self.amb = a.loop("ambience", "ambience", .9, ambient=True)
        self.reactor = a.loop("reactor", "reactor_hum", 1.0, ambient=True)
        self.amb.set(1.0, fade=.5)
        self.scratch = a.loop("alien_presence", "alien_scratch_loop", .7)
        self.presence = 0.0
        self.presence_timer = 0.0
        self.presence_heart = 0.0

    # ------------------------------------------------------------------
    def trigger(self, pos=None, scripted=False, duration=None):
        """Déclenche (ou prolonge) le mode horreur."""
        g = self.game
        was = self.active
        self.timer = max(self.timer, duration or C.HORROR_DURATION)
        self.active = True
        self.times_triggered += 1
        if not was:
            self.active_time = 0.0
            self.wave_timer = 1.2 if not scripted else 3.0
            g.hud.message("!! ALERTE — ÇA T'A ENTENDU !!" if not scripted else "!! ALERTE GÉNÉRALE !!", color.red)
            g.inp.rumble(1, 1, 500)
        if pos is not None and g.creature is not None:
            g.creature.hear(pos, 999.0, "shot")

    def scripted_scare(self, strength=1.0):
        """Sursaut : les lumières sautent, sting sonore, secousse."""
        self.scare = max(self.scare, strength)
        self.game.audio.play("metal_bang", .6 * strength, random.uniform(.8, 1.1))
        self.game.inp.rumble(.7 * strength, .4, 300)

    def shake_amount(self):
        pulse = .5 + .5 * math.sin(self.game.time * 11)
        return C.CAMERA_SHAKE * self.level * (.25 + .5 * pulse) * .5 + self.scare * .25

    @property
    def light_level(self):
        return max(self.level, self.scare * .6)

    # ------------------------------------------------------------------
    def emit_noise(self, pos, radius, kind):
        g = self.game
        if g.creature is not None:
            g.creature.hear(pos, radius, kind)
        if g.aliens is not None:
            g.aliens.hear(pos, radius, kind)

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        p = g.player
        # une alerte ne dure jamais plus d'une minute : redescente forcée sur les 4 dernières secondes
        if self.active:
            self.active_time += dt
            if self.active_time >= C.HORROR_MAX_TIME - 4:
                self.timer = 0.0
                self.level = max(0.0, self.level - dt / 4 - (1.0 if self.active_time >= C.HORROR_MAX_TIME else 0))
        # intensité
        if self.timer > 0:
            self.timer -= dt
            self.level = min(1.0, self.level + dt * 2.5)
        else:
            # redescend seulement si le joueur reste discret
            quiet = p is None or p.noise_radius <= C.NOISE_WALK
            rate = 1.0 / C.HORROR_FADE * (1.0 if quiet else .25)
            self.level = max(0.0, self.level - dt * rate)
            if self.level <= 0 and self.active:
                self.active = False
                g.hud.message("Le silence retombe...", color.rgb(.6, .6, .7))
        self.scare = max(0.0, self.scare - dt * 1.2)
        L = self.level
        # sons
        self.alarm.set(L ** .7, fade=3)
        self.music.set(L, fade=1.5 if self.timer > 0 else .6)
        self.amb.set(1.0 - .5 * L)
        # réacteur spatialisé
        # (silencieux tant que le courant n'est pas rétabli)
        if g.builder and g.builder.reactor_pos:
            att, bal = g.audio.spatial(g.builder.reactor_pos, 45)
            lvl = g.lights.power.reactor_level if g.lights else 1.0
            self.reactor.set(att * 1.2 * lvl, pitch=.6 + .4 * lvl, balance=bal, fade=4)
        # vibrations
        if L > .3:
            self.rumble_timer -= dt
            if self.rumble_timer <= 0:
                self.rumble_timer = .6
                g.inp.rumble(.35 * L, .2 * L, 250)
        # vagues de petites créatures pendant l'alerte
        if L > .5 and g.aliens is not None:
            self.wave_timer -= dt
            if self.wave_timer <= 0:
                self.wave_timer = C.HORROR_WAVE_INTERVAL * random.uniform(.8, 1.3)
                n = random.randint(*C.HORROR_ALIEN_WAVE)       # 1 à 3, plafonné à 3 au total
                g.aliens.spawn_near_player(n, aware=True)
        # présence invisible : une araignée proche que l'on ne voit pas -> grattements
        # lointains et battement de cœur discret
        self.presence_timer -= dt
        if self.presence_timer <= 0 and g.aliens is not None and p is not None:
            self.presence_timer = .5
            near = g.aliens.nearest_hidden()
            self.presence = 0.0 if near is None else max(0.0, 1 - near[0] / 13)
            if near is not None:
                att, bal = g.audio.spatial(near[1].center3(), 16)
                self.scratch.set(self.presence * .9, balance=bal, fade=1.5)
            else:
                self.scratch.set(0, fade=1.0)
        if self.presence > .25 and self.tension < .1:
            self.presence_heart -= dt
            if self.presence_heart <= 0:
                self.presence_heart = 1.3 - self.presence * .5
                g.audio.play("heartbeat", .18 + .25 * self.presence)
        # tension : proximité de la grande créature
        cr = g.creature
        self.tension = 0.0
        if cr is not None and cr.visible and p is not None:
            d = math.hypot(cr.x - p.x, cr.z - p.z)
            if d < 16:
                self.tension = 1 - d / 16
                self.heart_timer -= dt
                if self.heart_timer <= 0:
                    self.heart_timer = .45 + d / 16 * .9
                    g.audio.play("heartbeat", .4 + .6 * self.tension)
                    g.inp.rumble(.25 + .6 * self.tension, 0, 110)
        self.drone.set(max(self.tension * .9, .15 if not self.active else 0), fade=1)
        # événements d'ambiance
        self.event_timer -= dt
        if self.event_timer <= 0 and p is not None:
            self.event_timer = random.uniform(14, 32)
            self._ambient_event()

    def _ambient_event(self):
        g = self.game
        p = g.player
        r = random.random()
        a = random.uniform(0, 2 * math.pi)
        d = random.uniform(5, 14)
        pos = (p.x + math.cos(a) * d, 2.0, p.z + math.sin(a) * d)
        if r < .45:
            g.audio.play_at(f"creak{random.randint(0, 2)}", pos, .9, random.uniform(.8, 1.1))
        elif r < .7:
            g.audio.play_at("vent_bang", pos, .8, random.uniform(.7, 1.0))
        elif r < .85:
            g.audio.play_var("alien_skitter", 4, .55, pos=pos, occluded=True)   # derrière une cloison
        elif g.creature is not None and g.creature.visible:
            # rugissement lointain
            g.audio.play("creature_roar", .15, .8)
        else:
            self.scripted_scare(.35)
