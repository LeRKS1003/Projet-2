# -*- coding: utf-8 -*-
"""
alarm.py — Alarme du Kerguelen pendant le mode horreur.

  * trois couches : sirène à deux tons dissonants qui montent et descendent
    lentement, bourdonnement électrique grave en continu, bips d'alerte
    courts et irréguliers ;
  * son spatialisé : chaque gyrophare est un haut-parleur. L'alarme est forte
    dans la salle où l'on se trouve, lointaine, étouffée et réverbérée depuis
    les autres salles : tout le vaisseau hurle ;
  * annonce automatique (voix synthétique métallique, sous-titrée) :
    « Alerte. Contamination détectée. Section... » — elle grésille, se
    répète, déraille parfois ;
  * les gyrophares et le clignotement des lumières suivent exactement la
    sirène (phase lue sur la position de lecture du son) ;
  * quand l'alerte retombe, l'alarme faiblit et se coupe, puis un silence
    lourd s'installe (il ne reste que le bourdonnement du vaisseau).
"""
import math
import random

from ursina import color

import config as C
import lighting


class ShipAlarm:
    def __init__(self, game):
        self.game = game
        a = game.audio
        self.siren = a.loop("alarm_siren", "alarm_siren", 1.0)
        self.siren_far = a.loop("alarm_siren_far", "alarm_siren_far", 1.0)
        self.hum = a.loop("alarm_hum", "alarm_hum", 1.0)
        self.beeps = a.loop("alarm_beeps", "alarm_beeps", 1.0)
        self.t = 0.0
        self.level = 0.0
        self.announce_t = C.ALARM_ANNOUNCE_FIRST
        self.speakers = None
        self.near = 0.0
        self._last_tm = -1.0
        self._stuck = 0

    # ------------------------------------------------------------------
    def _speakers(self):
        """Positions des haut-parleurs : les gyrophares d'alarme du vaisseau."""
        if self.speakers is None:
            g = self.game
            self.speakers = [fx.pos for fx in g.lights.fixtures if fx.mode == "alarm"] if g.lights else []
        return self.speakers

    def phase(self):
        """Phase (0..1) du hurlement en cours, lue sur la position de lecture de la sirène."""
        snd = self.siren.snd
        fallback = (self.t % C.ALARM_CYCLE) / C.ALARM_CYCLE
        if snd is None or not self.game.audio.ok:
            return fallback
        try:
            tm = snd.getTime()
        except Exception:
            return fallback
        # si la position de lecture n'avance pas (pilote audio particulier), on suit l'horloge du jeu
        if abs(tm - self._last_tm) < 1e-6:
            self._stuck += 1
        else:
            self._stuck = 0
        self._last_tm = tm
        if self._stuck > 10:
            return fallback
        return (tm % C.ALARM_CYCLE) / C.ALARM_CYCLE

    # ------------------------------------------------------------------
    def update(self, dt, level):
        """level : intensité du mode horreur (0..1)."""
        g = self.game
        p = g.player
        self.t += dt
        self.level = level
        if level <= .01 or p is None:
            lighting.ALARM_STATE["phase"] = None
            for lp in (self.siren, self.siren_far, self.hum, self.beeps):
                lp.set(0, fade=C.ALARM_FADE_OUT)
            self.announce_t = min(self.announce_t, C.ALARM_ANNOUNCE_FIRST)
            return
        lighting.ALARM_STATE["phase"] = self.phase()
        # haut-parleur le plus proche : fort s'il est dans la même salle (ou tout près), sinon lointain
        L = g.level
        room = L.room_at(p.x, p.z)
        best, bpos = 1e9, None
        for sp in self._speakers():
            d = math.hypot(sp[0] - p.x, sp[2] - p.z)
            same = (L.room_at(sp[0], sp[2]) is room and room is not None) or d < C.ALARM_NEAR_RADIUS * .4
            if same and d < best:
                best, bpos = d, sp
        near = 0.0
        bal = 0.0
        if bpos is not None:
            near = max(0.0, 1 - best / C.ALARM_NEAR_RADIUS) ** 1.2
            _, bal = g.audio.spatial(bpos, C.ALARM_NEAR_RADIUS * 2)
        self.near += (near - self.near) * min(1.0, dt * 3)
        k = level ** .7
        self.siren.set(k * self.near * C.ALARM_NEAR_VOLUME, balance=bal, fade=4)
        self.siren_far.set(k * C.ALARM_FAR_VOLUME * (1 - .55 * self.near), fade=3)
        self.hum.set(k * C.ALARM_HUM_VOLUME, fade=2)
        self.beeps.set(k * C.ALARM_BEEP_VOLUME * (.25 + .75 * self.near), balance=bal, fade=3)
        # annonce automatique du vaisseau
        if level > .5:
            self.announce_t -= dt
            if self.announce_t <= 0:
                self.announce_t = random.uniform(*C.ALARM_ANNOUNCE_INTERVAL)
                self._announce()

    def _announce(self):
        """« Alerte. Contamination détectée. Section... » — la voix grésille, se répète, déraille."""
        g = self.game
        a = g.audio
        vol = C.ALARM_VOICE_VOLUME * (.55 + .45 * self.near)
        col = color.rgb(1, .45, .35)
        a.play("voice_alert0", vol, random.uniform(.97, 1.02))
        g.hud.message("« Alerte. Contamination détectée... »", col)
        r = random.random()
        q = g.weapons.pending if g.weapons is not None else None
        t0 = g.weapons.t if g.weapons is not None else 0
        if q is None:
            return
        if r < .55:
            q.append((t0 + 3.4, lambda: (a.play("voice_alert1", vol), g.hud.message("« Section... »  *grésillement*", col))))
        elif r < .85:
            # la voix déraille
            q.append((t0 + 3.4, lambda: (a.play("voice_glitch", vol, .92), g.hud.message("« Sec... sec... sec— »", col))))
        else:
            # elle se répète, coupée
            q.append((t0 + 3.3, lambda: (a.play("voice_alert0", vol * .8, .95),
                                         g.hud.message("« Alerte. Alerte. Conta— »", col))))
            q.append((t0 + 5.0, lambda: a.play("static_burst", .5)))

    def stop(self):
        lighting.ALARM_STATE["phase"] = None
        for lp in (self.siren, self.siren_far, self.hum, self.beeps):
            lp.set(0, fade=8)
