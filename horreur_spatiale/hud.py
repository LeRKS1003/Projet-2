# -*- coding: utf-8 -*-
"""
hud.py — Interface : HUD de pilotage (TPS), HUD d'exploration (FPS),
messages en fondu, invite d'interaction, surimpressions (vignette, sang,
vision nocturne, casier, fondu au noir) et écrans (menu, pause, game over,
victoire).
"""
import math
import random

from panda3d.core import TransparencyAttrib
from ursina import Entity, Text, camera, color, window, Vec3, destroy, scene

import config as C
import textures


def _tx(t, s):
    """Ne régénère le texte que s'il a changé (coûteux dans Ursina)."""
    if t.text != s:
        t.text = s


def _bar(parent, pos, width, col, height=.012):
    bg = Entity(parent=parent, model='quad', color=color.rgba(0, 0, 0, .55), origin=(-.5, 0), position=pos,
                scale=(width, height + .006))
    fg = Entity(parent=parent, model='quad', color=col, origin=(-.5, 0), position=(pos[0] + .003, pos[1]),
                scale=(width - .006, height), z=-.01)
    return bg, fg


def _overlay(tex=None, col=color.white, z=0):
    e = Entity(parent=camera.ui, model='quad', texture=tex, color=col, scale=(window.aspect_ratio * 1.02, 1.02), z=z)
    e.setTransparency(TransparencyAttrib.MAlpha)
    return e


class HUD:
    def __init__(self, game):
        self.game = game
        self.mode = "none"
        ar = window.aspect_ratio
        self.ar = ar
        # --- surimpressions plein écran (de l'arrière vers l'avant) --------
        self.nv_tint = _overlay(None, color.rgba(.1, 1, .25, .0), z=5)
        self.nv_grain = _overlay(textures.get('grain'), color.rgba(1, 1, 1, 0), z=4.9)
        self.nv_grain.texture_scale = (1, .25)
        self.glare = _overlay(textures.get('glow'), color.rgba(1, 1, 1, 0), z=4.8)
        self.glare.scale = 2.5
        self.horror_tint = _overlay(textures.get('red_vignette'), color.rgba(1, 0, 0, 0), z=4.7)
        self.vignette = _overlay(textures.get('vignette'), color.rgba(1, 1, 1, .85), z=4.6)
        self.blood = _overlay(textures.get('red_vignette'), color.rgba(1, 1, 1, 0), z=4.5)
        self.locker = _overlay(textures.get('locker_slits'), color.rgba(1, 1, 1, 0), z=4.4)
        self.fade = _overlay(None, color.rgba(0, 0, 0, 0), z=-20)
        # flash blanc d'une seule image (screamer ; désactivable : config.SCREAMER_FLASH)
        self.white = _overlay(None, color.rgba(1, 1, 1, 0), z=-19)
        self._white_frames = 0
        # histoire : glitch (signal perdu), « vérité » (couleurs éteintes), reflet de la verrière
        self.glitch = _overlay(textures.get('glitch'), color.rgba(1, 1, 1, 0), z=-18)
        self.truth = _overlay(None, color.rgba(.55, .58, .6, 0), z=4.2)
        self.reflection = _overlay(None, color.rgba(1, 1, 1, 0), z=-17)
        self.eyes = []
        for k in range(2):
            e = Entity(parent=camera.ui, model='quad', texture=textures.get('glow'), color=color.rgba(1, 1, 1, 0),
                       scale=.03, position=(-.215 + k * .05, .06), z=-17.5)
            e.setTransparency(TransparencyAttrib.MAlpha)
            self.eyes.append(e)
        self.glitch_level = 0.0
        self.truth_level = 0.0
        self.center_text = Text(parent=camera.ui, text='', position=(0, .08), origin=(0, 0), scale=1.5,
                                color=color.rgb(.8, .95, .85), z=-18.5)
        self.suit_box = Entity(parent=camera.ui, model='quad', color=color.rgba(0, .08, .04, 0), scale=(.9, .13),
                               position=(0, -.25), z=-1)
        self.suit_text = Text(parent=camera.ui, text='', position=(-.43, -.205), scale=.85,
                              color=color.rgb(.4, 1, .55), z=-1.1)
        self._suit_t = 0.0
        self.fade_target = 0.0
        self.fade_speed = 1.0
        self.fade_value = 0.0

        # --- commun ----------------------------------------------------------
        self.fps_text = Text(parent=camera.ui, text='', position=(ar / 2 - .12, .49), scale=.7,
                             color=color.rgba(1, 1, 1, .4))
        self.msg_texts = []
        self.messages = []           # [texte, couleur, temps restant]
        for k in range(5):
            t = Text(parent=camera.ui, text='', position=(-ar / 2 + .04, .12 - k * .04), scale=.9)
            self.msg_texts.append(t)

        # --- HUD TPS ---------------------------------------------------------
        self.tps = Entity(parent=camera.ui, enabled=False)
        Text(parent=self.tps, text='INTÉGRITÉ COQUE', position=(-ar / 2 + .04, -.38), scale=.75,
             color=color.rgb(.7, .8, .9))
        self.integrity_bar = _bar(self.tps, (-ar / 2 + .04, -.41), .35, color.rgb(.3, .8, 1))
        Text(parent=self.tps, text='BOOST', position=(-ar / 2 + .04, -.44), scale=.7, color=color.rgb(.7, .8, .9))
        self.boost_bar = _bar(self.tps, (-ar / 2 + .04, -.465), .25, color.rgb(1, .7, .2), .008)
        self.speed_text = Text(parent=self.tps, text='', position=(ar / 2 - .3, -.4), scale=1.1,
                               color=color.rgb(.7, .9, 1))
        self.cruise_text = Text(parent=self.tps, text='', position=(ar / 2 - .3, -.44), scale=.75,
                                color=color.rgb(.55, .75, .9))
        self.assist_text = Text(parent=self.tps, text='', position=(ar / 2 - .3, -.365), scale=.7,
                                color=color.rgb(.5, .9, .6))
        self.approach_text = Text(parent=self.tps, text='', position=(0, -.3), origin=(0, 0), scale=1.0,
                                  color=color.rgb(.4, 1, .55))
        self.arrow = Entity(parent=self.tps, model='quad', texture=textures.get('arrow'), color=color.rgb(.2, 1, .4),
                            scale=.05)
        self.marker = Entity(parent=self.tps, model='quad', texture=textures.get('glow'),
                             color=color.rgba(.2, 1, .4, .7), scale=.05)
        self.marker_text = Text(parent=self.tps, text='', scale=.75, color=color.rgb(.3, 1, .5), origin=(0, 0))
        self.warn_text = Text(parent=self.tps, text='', position=(0, .3), origin=(0, 0), scale=1.4, color=color.red)
        self.tps_hint = Text(parent=self.tps, text='', position=(0, -.47), origin=(0, 0), scale=.7,
                             color=color.rgba(1, 1, 1, .45))
        self.reticle = Entity(parent=self.tps, model='circle', color=color.rgba(.6, .9, 1, .5), scale=.012)

        # --- HUD FPS ---------------------------------------------------------
        self.fps = Entity(parent=camera.ui, enabled=False)
        self.objective = Text(parent=self.fps, text='', position=(0, .46), origin=(0, 0), scale=1.0,
                              color=color.rgb(.85, .9, .8))
        self.compass = Entity(parent=self.fps, model='quad', texture=textures.get('arrow'),
                              color=color.rgba(.8, .9, .6, .6), scale=.025, position=(0, .415))
        self.compass_text = Text(parent=self.fps, text='', position=(0, .385), origin=(0, 0), scale=.65,
                                 color=color.rgba(.8, .9, .7, .6))
        Text(parent=self.fps, text='SANTÉ', position=(-ar / 2 + .04, -.37), scale=.7, color=color.rgb(.8, .6, .6))
        self.health_bar = _bar(self.fps, (-ar / 2 + .04, -.395), .3, color.rgb(.8, .15, .12))
        self.stamina_bar = _bar(self.fps, (-ar / 2 + .04, -.415), .2, color.rgb(.7, .7, .6), .005)
        Text(parent=self.fps, text='BATTERIE', position=(-ar / 2 + .04, -.43), scale=.7, color=color.rgb(.8, .8, .5))
        self.battery_bar = _bar(self.fps, (-ar / 2 + .04, -.455), .22, color.rgb(.95, .85, .3), .008)
        self.battery_text = Text(parent=self.fps, text='', position=(-ar / 2 + .27, -.445), scale=.65,
                                 color=color.rgb(.8, .8, .5))
        self.ammo_text = Text(parent=self.fps, text='', position=(ar / 2 - .05, -.39), origin=(.5, 0), scale=1.6,
                              color=color.rgb(.9, .9, .85))
        self.knife_text = Text(parent=self.fps, text='', position=(ar / 2 - .05, -.43), origin=(.5, 0), scale=.75,
                               color=color.rgb(.75, .75, .75))
        self.item_text = Text(parent=self.fps, text='', position=(ar / 2 - .05, -.46), origin=(.5, 0), scale=.75,
                              color=color.rgb(.7, .85, .7))
        # indicateur de bruit : 6 segments
        Text(parent=self.fps, text='BRUIT', position=(-.09, -.44), scale=.6, color=color.rgba(1, 1, 1, .5))
        self.noise_segs = []
        for k in range(6):
            s = Entity(parent=self.fps, model='quad', color=color.rgba(1, 1, 1, .15), scale=(.02, .01 + k * .004),
                       position=(-.03 + k * .025, -.45 + k * .002))
            self.noise_segs.append(s)
        # réticule discret
        self.cross = []
        for k in range(4):
            c = Entity(parent=self.fps, model='quad', color=color.rgba(1, 1, 1, .55),
                       scale=(.012, .002) if k < 2 else (.002, .012))
            self.cross.append(c)
        self.dot = Entity(parent=self.fps, model='circle', color=color.rgba(1, 1, 1, .6), scale=.004)
        self.prompt = Text(parent=self.fps, text='', position=(0, -.08), origin=(0, 0), scale=.95,
                           color=color.rgb(.95, .95, .85))
        self.progress = _bar(self.fps, (-.1, -.12), .2, color.rgb(.9, .9, .6), .008)
        self.dmg_ind = Entity(parent=self.fps, model='quad', texture=textures.get('glow'), color=color.rgba(1, 0, 0, 0),
                              scale=(.18, .05))
        self.dmg_t = 0.0
        self.dmg_angle = 0.0
        self.alert_text = Text(parent=self.fps, text='', position=(0, .33), origin=(0, 0), scale=1.2,
                               color=color.red)

    # ------------------------------------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        self.tps.enabled = mode == "tps"
        self.fps.enabled = mode == "fps"
        if mode != "fps":
            for o in (self.nv_tint, self.nv_grain, self.glare, self.horror_tint, self.blood, self.locker):
                o.color = color.rgba(o.color.r, o.color.g, o.color.b, 0)
        self.vignette.enabled = mode in ("fps", "tps")

    def message(self, text, col=None):
        self.messages.insert(0, [text, col or color.rgb(.85, .85, .8), 4.5])
        self.messages = self.messages[:5]

    def damage_indicator(self, angle):
        self.dmg_angle = angle
        self.dmg_t = 1.0

    def fade_to(self, alpha, duration=1.0):
        self.fade_target = alpha
        self.fade_speed = 1.0 / max(.01, duration)

    def suit_log(self, text, duration=8.0):
        """Message du journal de la combinaison (encadré vert, en bas de l'écran)."""
        self.suit_text.text = text
        self._suit_t = duration

    def set_reflection(self, alpha, eyes=0.0):
        """Fin du jeu : reflet dans la verrière du cockpit (et deux points blancs derrière le joueur)."""
        if alpha > 0 and self.reflection.texture is None:
            from document_ui import reflection_image
            from ursina import Texture
            self.reflection.texture = Texture(reflection_image())
        self.reflection.color = color.rgba(1, 1, 1, alpha)
        for e in self.eyes:
            e.color = color.rgba(1, 1, 1, eyes)

    def flash_frame(self):
        """Flash blanc plein écran pendant une image."""
        self._white_frames = 1
        self.white.color = color.rgba(1, 1, 1, 1)

    def set_fade(self, alpha):
        self.fade_value = self.fade_target = alpha
        self.fade.color = color.rgba(0, 0, 0, alpha)

    # ------------------------------------------------------------------
    def update(self, dt):
        # flash blanc (une image)
        if self._white_frames > 0:
            self._white_frames -= 1
        elif self.white.color.a > 0:
            self.white.color = color.rgba(1, 1, 1, 0)
        # glitch : bandes de signal perdu qui sautent d'une image à l'autre
        gl = self.glitch_level
        if gl > .01:
            self.glitch.color = color.rgba(1, 1, 1, min(.85, gl * (.4 + .6 * random.random())))
            self.glitch.texture_offset = (random.random(), random.random())
            self.glitch.texture_scale = (1, random.uniform(.5, 2))
            self.glitch.x = random.uniform(-.03, .03) * gl
        elif self.glitch.color.a > 0:
            self.glitch.color = color.rgba(1, 1, 1, 0)
        self.truth.color = color.rgba(.55, .58, .6, .22 * self.truth_level)
        # journal de la combinaison
        if self._suit_t > 0:
            self._suit_t -= dt
            a = min(1.0, self._suit_t / 1.0)
            self.suit_box.color = color.rgba(0, .08, .04, .75 * a)
            self.suit_text.color = color.rgba(.4, 1, .55, a if (self._suit_t % .9) > .06 else .3)
        elif self.suit_text.text:
            self.suit_text.text = ''
            self.suit_box.color = color.rgba(0, .08, .04, 0)
        # fondu au noir
        if self.fade_value != self.fade_target:
            d = self.fade_target - self.fade_value
            step = self.fade_speed * dt
            self.fade_value = self.fade_target if abs(d) <= step else self.fade_value + math.copysign(step, d)
            self.fade.color = color.rgba(0, 0, 0, self.fade_value)
        # messages en fondu
        for m in self.messages:
            m[2] -= dt
        self.messages = [m for m in self.messages if m[2] > 0]
        for k, t in enumerate(self.msg_texts):
            if k < len(self.messages):
                txt, col, life = self.messages[k]
                a = min(1.0, life / 1.2)
                _tx(t, txt)
                t.color = color.rgba(col.r, col.g, col.b, a)
            else:
                _tx(t, '')
        if C.SHOW_FPS:
            # compteur lissé, rafraîchi deux fois par seconde
            self._fps_acc = getattr(self, "_fps_acc", 0.0) + dt
            self._fps_n = getattr(self, "_fps_n", 0) + 1
            if self._fps_acc >= .5:
                _tx(self.fps_text, f"{self._fps_n / self._fps_acc:.0f} FPS")
                self._fps_acc, self._fps_n = 0.0, 0
        if self.mode == "tps":
            self._update_tps(dt)
        elif self.mode == "fps":
            self._update_fps(dt)

    def _set_bar(self, bar, width, frac):
        bar[1].scale_x = max(0.0001, (width - .006) * max(0, min(1, frac)))

    def _update_tps(self, dt):
        g = self.game
        sh = g.shuttle
        self._set_bar(self.integrity_bar, .35, sh.integrity / C.SHIP_INTEGRITY)
        self.integrity_bar[1].color = color.rgb(1, .25, .15) if sh.integrity < 35 else color.rgb(.3, .8, 1)
        self._set_bar(self.boost_bar, .25, sh.boost / C.SHIP_BOOST_MAX)
        # le HUD vibre légèrement au boost et lors des impacts
        j = (.004 if sh.boosting else 0) + g.shake_amount * .01
        self.tps.position = (random.uniform(-j, j), random.uniform(-j, j))
        _tx(self.speed_text, f"{sh.speed:5.1f} m/s")
        if sh.assist and C.SHIP_CRUISE:
            _tx(self.cruise_text, f"cible {sh.target_speed:4.1f} m/s")
        else:
            _tx(self.cruise_text, "")
        state = "ASSIST. VOL" if sh.assist else "INERTIE PURE"
        _tx(self.assist_text, state + ("  |  FREIN" if sh.braking else ""))
        self.assist_text.color = color.rgb(.5, .9, .6) if sh.assist else color.rgb(1, .7, .3)
        blink = (g.time * 5) % 1 < .6
        if sh.warn > 0 and (g.time * 6) % 1 < .6:
            _tx(self.warn_text, "IMPACT !")
        elif sh.obstacle_warn > 0 and blink:
            _tx(self.warn_text, f"OBSTACLE DROIT DEVANT  ({sh.obstacle_warn:.1f} s)")
        elif sh.integrity < 25 and (g.time * 2) % 1 < .5:
            _tx(self.warn_text, "COQUE CRITIQUE")
        else:
            _tx(self.warn_text, "")
        if sh.approach is not None:
            d, v = sh.approach
            if sh.speed > v + 2:
                _tx(self.approach_text, f"Approche : réduis à {v:.0f} m/s   ({d:.0f} m)")
                self.approach_text.color = color.rgb(1, .75, .3)
            else:
                _tx(self.approach_text, f"Approche : vitesse correcte   ({d:.0f} m)")
                self.approach_text.color = color.rgb(.4, 1, .55)
        else:
            _tx(self.approach_text, "")
        pad = g.inp.using_pad
        _tx(self.tps_hint, ("Stick G: poussée/strafe  Stick D: orientation  R2/L2: monter/descendre  "
                              "L1/R1: roulis  Croix: boost  Triangle: assist.  Rond: frein  R3: caméra" if pad else
                              "ZQSD: poussée/strafe  Souris: orientation  Espace/Ctrl: monter/descendre  "
                              "A/E: roulis  Maj: boost  F: assist.  X: frein  C: caméra"))
        # flèche / marqueur vers l'entrée du hangar
        target = g.exterior.entrance if not g.exterior.in_hangar_entrance(sh.position) else None
        if sh.position.z > -5 and abs(sh.position.x - g.exterior.entrance.x) < 12 and sh.position.y < 10:
            target = Vec3(g.exterior.entrance.x, g.exterior.entrance.y, 6)
        if target is None:
            self.arrow.enabled = self.marker.enabled = False
            _tx(self.marker_text, '')
            return
        rel = camera.getRelativePoint(scene, target)
        dist = (target - sh.position).length()
        on_screen = False
        if rel[2] > 0:
            # projection perspective (camera.fov est le champ HORIZONTAL)
            k = (self.ar / 2) / (math.tan(math.radians(camera.fov / 2)) * rel[2])
            sx = rel[0] * k
            sy = rel[1] * k
            if abs(sx) < self.ar / 2 - .05 and abs(sy) < .45:
                on_screen = True
                self.marker.enabled = True
                self.arrow.enabled = False
                self.marker.position = (sx, sy)
                self.marker_text.position = (sx, sy - .045)
                _tx(self.marker_text, f"HANGAR  {dist:.0f} m")
        if not on_screen:
            self.marker.enabled = False
            ang = math.atan2(rel[0], rel[1] if rel[2] > 0 else -abs(rel[1]) - .001)
            if rel[2] <= 0 and abs(rel[0]) < 1e-3:
                ang = math.pi
            r = .32
            self.arrow.enabled = True
            self.arrow.position = (math.sin(ang) * r * 1.3, math.cos(ang) * r)
            self.arrow.rotation_z = math.degrees(ang)
            self.marker_text.position = (self.arrow.x, self.arrow.y - .05)
            _tx(self.marker_text, f"HANGAR {dist:.0f} m")

    def _update_fps(self, dt):
        g = self.game
        p = g.player
        w = g.weapons
        inv = g.inventory
        lt = g.lights
        pad = g.inp.using_pad
        # objectif + boussole
        _tx(self.objective, g.objective_text())
        tgt = g.objective_target()
        if C.OBJECTIVE_COMPASS and tgt is not None:
            a = math.degrees(math.atan2(tgt[0] - p.x, tgt[1] - p.z))
            rel = (a - p.yaw + 180) % 360 - 180
            self.compass.enabled = True
            self.compass.rotation_z = rel
            d = math.hypot(tgt[0] - p.x, tgt[1] - p.z)
            _tx(self.compass_text, f"{d:.0f} m")
        else:
            self.compass.enabled = False
            _tx(self.compass_text, '')
        # barres
        self._set_bar(self.health_bar, .3, p.health / C.MAX_HEALTH)
        self._set_bar(self.stamina_bar, .2, p.stamina / C.STAMINA_MAX)
        self.stamina_bar[1].color = color.rgb(.8, .4, .2) if p.exhausted else color.rgb(.7, .7, .6)
        self._set_bar(self.battery_bar, .22, lt.battery / C.BATTERY_MAX)
        self.battery_bar[1].color = color.rgb(1, .3, .2) if lt.battery < 15 else color.rgb(.95, .85, .3)
        mode = "VISION NOCT." if lt.nightvision else ("LAMPE" if lt.flashlight_on else "")
        _tx(self.battery_text, f"{lt.battery:.0f}%  {mode}")
        if w.has_pistol:
            _tx(self.ammo_text, f"{w.mag} | {w.reserve}" + ("  RECHARGE..." if w.reloading > 0 else ""))
        else:
            _tx(self.ammo_text, "")
        kd = inv.knife_durability()
        _tx(self.knife_text, f"Couteau {kd}/{C.KNIFE_DURABILITY}" if inv.has("knife") else "Pas de couteau")
        from loot import ITEM_NAMES
        eq = inv.equipped
        _tx(self.item_text, f"Équipé : {ITEM_NAMES[eq]} x{inv.count(eq)}   Kits : {inv.count('medkit')}")
        # bruit
        lvl = p.noise_level
        for k, s in enumerate(self.noise_segs):
            on = lvl * 6 > k + .1
            c = color.rgb(.3, .9, .3) if k < 2 else (color.rgb(.9, .8, .2) if k < 4 else color.rgb(1, .25, .2))
            s.color = color.rgba(c.r, c.g, c.b, .85) if on else color.rgba(1, 1, 1, .12)
        # réticule
        gap = .012 + (1 - w.aim_k) * .018 + w.spread_bonus * .006 + (.01 if p.running else 0)
        self.cross[0].position = (-gap - .006, 0)
        self.cross[1].position = (gap + .006, 0)
        self.cross[2].position = (0, gap + .006)
        self.cross[3].position = (0, -gap - .006)
        vis = not p.hidden and not g.inventory_ui.open
        for c in self.cross:
            c.enabled = vis and w.has_pistol
        self.dot.enabled = vis
        # invite d'interaction
        key = "Croix" if pad else "E"
        if p.focus is not None and not p.hidden and not g.inventory_ui.open:
            _tx(self.prompt, f"[{key}] {p.focus.prompt(g)}")
        elif p.hidden:
            _tx(self.prompt, f"[{key}] Sortir du casier")
        else:
            _tx(self.prompt, '')
        if p.search_target is not None:
            self.progress[0].enabled = self.progress[1].enabled = True
            self._set_bar(self.progress, .2, p.search_progress / p.search_target.hold_time)
        else:
            self.progress[0].enabled = self.progress[1].enabled = False
        # indicateur de dégâts directionnel
        self.dmg_t = max(0.0, self.dmg_t - dt * 1.5)
        a = math.radians(self.dmg_angle)
        self.dmg_ind.position = (math.sin(a) * .15, math.cos(a) * .15)
        self.dmg_ind.rotation_z = self.dmg_angle
        self.dmg_ind.color = color.rgba(1, .05, .05, self.dmg_t * .8)
        # alerte
        _tx(self.alert_text, ("ALERTE" if g.horror.active and (g.time * 2.5) % 1 < .55 else ""))
        # --- surimpressions ------------------------------------------------
        nv = lt.nightvision
        self.nv_tint.color = color.rgba(.05, 1, .2, .22 if nv else 0)
        self.nv_grain.color = color.rgba(.6, 1, .6, .5 if nv else 0)
        if nv:
            self.nv_grain.texture_offset = (random.random(), random.randint(0, 3) * .25)
            gl = lt.glare_amount(tuple(camera.world_position), tuple(camera.forward))
            self.glare.color = color.rgba(.9, 1, .9, gl * .9)
            self.glare.scale = 1.5 + gl * 2
        else:
            self.glare.color = color.rgba(1, 1, 1, 0)
        hl = g.horror.light_level
        pulse = .5 + .5 * math.sin(g.time * 9)
        self.horror_tint.color = color.rgba(1, .1, .05, hl * (.25 + .25 * pulse))
        low = max(0.0, 1 - p.health / C.LOW_HEALTH) if p.health < C.LOW_HEALTH else 0.0
        beat = .5 + .5 * math.sin(g.time * 7)
        self.blood.color = color.rgba(1, 1, 1, min(1, p.hurt_flash * .8 + low * (.45 + .3 * beat)))
        self.locker.color = color.rgba(1, 1, 1, .97 if p.hidden else 0)
        self.vignette.color = color.rgba(1, 1, 1, .7 + .3 * low)

    def destroy(self):
        pass


# ============================================================================
class MenuScreen:
    """Écran générique (menu, pause, game over, victoire) navigable clavier/souris/manette."""

    def __init__(self, title, subtitle, options, on_select, title_color=color.rgb(.85, .9, .95), bg_alpha=.75):
        self.options = options
        self.on_select = on_select
        self.sel = 0
        self.root = Entity(parent=camera.ui, z=-25)     # devant le fondu au noir (z=-20)
        self.bg = Entity(parent=self.root, model='quad', color=color.rgba(0, 0, 0, bg_alpha),
                         scale=(window.aspect_ratio * 1.05, 1.05))
        self.title = Text(parent=self.root, text=title, position=(0, .28), origin=(0, 0), scale=3.2,
                          color=title_color)
        self.subtitle = Text(parent=self.root, text=subtitle, position=(0, .16), origin=(0, 0), scale=1.0,
                             color=color.rgb(.7, .7, .7))
        self.items = []
        for k, label in enumerate(options):
            t = Text(parent=self.root, text=label, position=(0, .0 - k * .07), origin=(0, 0), scale=1.4)
            hit = Entity(parent=self.root, model='quad', color=color.rgba(1, 1, 1, 0), scale=(.5, .06),
                         position=(0, -k * .07), collider='box')
            hit.on_click = (lambda i=k: self._click(i))
            hit.on_mouse_enter = (lambda i=k: self._hover(i))
            self.items.append((t, hit))
        self.hint = Text(parent=self.root, text="Haut/Bas + Entrée  —  Croix pour valider", position=(0, -.42),
                         origin=(0, 0), scale=.75, color=color.rgba(1, 1, 1, .4))
        self.t = 0.0
        self._refresh()

    def _hover(self, i):
        self.sel = i
        self._refresh()

    def _click(self, i):
        self.sel = i
        self.on_select(self.options[i])

    def _refresh(self):
        for k, (t, hit) in enumerate(self.items):
            t.color = color.rgb(1, .85, .4) if k == self.sel else color.rgb(.75, .75, .75)
            t.text = ("> " + self.options[k] + " <") if k == self.sel else self.options[k]

    def update(self, dt, inp):
        self.t += dt
        if self.t < .25:
            return
        n = len(self.options)
        up = inp.pressed("menu_up") or inp.pad.pressed("dpad_up")
        down = inp.pressed("menu_down") or inp.pad.pressed("dpad_down")
        ly = inp.pad.stick("ly")
        if not hasattr(self, "_stick_lock"):
            self._stick_lock = False
        if abs(ly) > .6 and not self._stick_lock:
            self._stick_lock = True
            up = up or ly < 0
            down = down or ly > 0
        elif abs(ly) < .3:
            self._stick_lock = False
        if up:
            self.sel = (self.sel - 1) % n
            self._refresh()
        if down:
            self.sel = (self.sel + 1) % n
            self._refresh()
        if inp.pressed("confirm") or inp.pad.pressed("cross"):
            self.on_select(self.options[self.sel])

    def destroy(self):
        destroy(self.root)


# ============================================================================
class TitleScreen(MenuScreen):
    """
    Écran titre de DÉRIVE : le mot en grandes lettres blanches fines sur fond
    d'espace, qui tremble et se dédouble de temps en temps (image qui perd le
    signal), sous-titre « Kerguelen — dernier contact il y a 41 jours ».
    """

    def __init__(self, title, subtitle, options, on_select):
        super().__init__(title, subtitle, options, on_select, title_color=color.rgb(.95, .96, .97), bg_alpha=.25)
        self.title.scale = 7
        self.title.y = .24
        self.subtitle.y = .1
        self.subtitle.scale = .95
        self.subtitle.color = color.rgb(.62, .66, .7)
        # copies décalées rouge / cyan pour le dédoublement
        self.ghosts = []
        for c in (color.rgba(1, .2, .2, 0), color.rgba(.2, 1, 1, 0)):
            g = Text(parent=self.root, text=title, position=self.title.position, origin=(0, 0), scale=7, color=c)
            self.ghosts.append(g)
        self.scan = Entity(parent=self.root, model='quad', texture=textures.get('glitch'), color=color.rgba(1, 1, 1, 0),
                           scale=(1.2, .16), position=(0, .24), z=-.1)
        self._glitch = 0.0
        self._next = random.uniform(1.5, 4)
        self.hint.text = "Haut/Bas + Entrée  —  Croix pour valider  —  I : commandes"

    def update(self, dt, inp):
        super().update(dt, inp)
        self._next -= dt
        if self._next <= 0:
            self._next = random.uniform(1.2, 5.0)
            self._glitch = random.uniform(.12, .45)
        if self._glitch > 0:
            self._glitch -= dt
            j = .02
            self.title.x = random.uniform(-j, j)
            for k, g in enumerate(self.ghosts):
                g.x = self.title.x + (-.02 if k == 0 else .02) * random.uniform(.4, 1.6)
                g.y = self.title.y + random.uniform(-.006, .006)
                c = g.color
                g.color = color.rgba(c.r, c.g, c.b, random.uniform(.3, .7))
            self.scan.color = color.rgba(1, 1, 1, random.uniform(.2, .6))
            self.scan.texture_offset = (random.random(), random.random())
            self.scan.y = self.title.y + random.uniform(-.06, .06)
        else:
            self.title.x = 0
            for g in self.ghosts:
                c = g.color
                if c.a > 0:
                    g.color = color.rgba(c.r, c.g, c.b, 0)
            if self.scan.color.a > 0:
                self.scan.color = color.rgba(1, 1, 1, 0)
