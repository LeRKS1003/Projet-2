# -*- coding: utf-8 -*-
"""
controller.py — Manette PS5 DualSense (pygame.joystick / SDL2) + fusion
clavier/souris dans un gestionnaire d'entrées unique.

Le jeu ne lit jamais directement le clavier ou la manette : il interroge
InputManager (move, look, pressed('fire'), held('run')...). Le jeu reste
donc entièrement jouable au clavier/souris sans manette.
"""
import math
import os

import config as C

# Variables SDL à définir AVANT l'import de pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")   # la fenêtre appartient à Panda3D
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5", "1")
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5_RUMBLE", "1")          # vibrations aussi en Bluetooth
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS4_RUMBLE", "1")
if C.GAMEPAD_SDL_DUMMY_VIDEO:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")                 # pas de fenêtre pygame

try:
    import pygame
    PYGAME_OK = True
except Exception as exc:  # pragma: no cover
    print("[manette] pygame indisponible :", exc)
    PYGAME_OK = False

from ursina import held_keys, mouse, Text, Entity, camera, color


def _deadzone(v, dz):
    """Zone morte + remise à l'échelle pour garder une course complète."""
    if abs(v) < dz:
        return 0.0
    return math.copysign((abs(v) - dz) / (1 - dz), v)


def _curve(v, k):
    return math.copysign(abs(v) ** k, v)


class Gamepad:
    """Lecture brute de la manette + détection automatique / reconnexion."""

    def __init__(self):
        self.joy = None
        self.name = ""
        self.profile_name = "sdl"
        self.profile = C.GAMEPAD_PROFILES["sdl"]
        self.axes = []
        self.buttons = []
        self.hats = []
        self.prev_buttons = set()
        self.now_buttons = set()
        self.trigger_seen = {}
        self.ok = False
        self._recheck = 0.0
        self._rumble_until = 0.0
        if not (PYGAME_OK and C.GAMEPAD_ENABLED):
            return
        try:
            pygame.display.init()
            pygame.joystick.init()
            self.ok = True
            self._connect_first()
        except Exception as exc:
            print("[manette] initialisation impossible :", exc)
            self.ok = False

    # ------------------------------------------------------------------
    def _connect_first(self):
        if pygame.joystick.get_count() > 0:
            self._open(0)

    def _open(self, index):
        try:
            j = pygame.joystick.Joystick(index)
            j.init()
            self.joy = j
            self.name = j.get_name()
            self._choose_profile()
            self.trigger_seen = {}
            print(f"[manette] connectée : {self.name} ({j.get_numaxes()} axes, "
                  f"{j.get_numbuttons()} boutons, {j.get_numhats()} croix) -> profil {self.profile_name}")
        except Exception as exc:
            print("[manette] ouverture impossible :", exc)
            self.joy = None

    def _choose_profile(self):
        if C.GAMEPAD_PROFILE != "auto":
            self.profile_name = C.GAMEPAD_PROFILE
        else:
            nb = self.joy.get_numbuttons()
            nh = self.joy.get_numhats()
            # HIDAPI/SDL : 15+ boutons, croix directionnelle en boutons
            # DirectInput (Windows) : 14 boutons + 1 croix ; evdev (Linux) : 13 boutons + 1 croix
            if nh > 0 and nb <= 13:
                self.profile_name = "evdev"
            elif nh > 0 and nb <= 14:
                self.profile_name = "directinput"
            else:
                self.profile_name = "sdl"
        self.profile = C.GAMEPAD_PROFILES.get(self.profile_name, C.GAMEPAD_PROFILES["sdl"])

    @property
    def connected(self):
        return self.joy is not None

    # ------------------------------------------------------------------
    def poll(self, dt):
        """À appeler une fois par image : événements SDL + lecture des états."""
        self.prev_buttons = self.now_buttons
        self.now_buttons = set()
        if not self.ok:
            return
        try:
            for ev in pygame.event.get():
                if ev.type == pygame.JOYDEVICEADDED and self.joy is None:
                    self._open(ev.device_index)
                elif ev.type == pygame.JOYDEVICEREMOVED:
                    if self.joy is not None and getattr(ev, "instance_id", None) == self.joy.get_instance_id():
                        print("[manette] déconnectée")
                        self.joy = None
        except Exception:
            pass
        # vérification périodique (certains pilotes n'envoient pas d'événement)
        self._recheck -= dt
        if self.joy is None and self._recheck <= 0:
            self._recheck = 2.0
            try:
                pygame.joystick.quit()
                pygame.joystick.init()
                self._connect_first()
            except Exception:
                pass
        if self.joy is None:
            self.axes, self.buttons, self.hats = [], [], []
            return
        try:
            j = self.joy
            self.axes = [j.get_axis(i) for i in range(j.get_numaxes())]
            self.buttons = [j.get_button(i) for i in range(j.get_numbuttons())]
            self.hats = [j.get_hat(i) for i in range(j.get_numhats())]
        except Exception:
            self.joy = None
            return
        # boutons logiques actifs
        for name, idx in self.profile["buttons"].items():
            if idx < len(self.buttons) and self.buttons[idx]:
                self.now_buttons.add(name)
        if self.profile.get("use_hat") and self.hats:
            hx, hy = self.hats[0]
            if hy > 0: self.now_buttons.add("dpad_up")
            if hy < 0: self.now_buttons.add("dpad_down")
            if hx < 0: self.now_buttons.add("dpad_left")
            if hx > 0: self.now_buttons.add("dpad_right")
        # gâchettes utilisées comme boutons
        if self.trigger("l2") > C.GAMEPAD_TRIGGER_THRESHOLD:
            self.now_buttons.add("l2")
        if self.trigger("r2") > C.GAMEPAD_TRIGGER_THRESHOLD:
            self.now_buttons.add("r2")

    # ------------------------------------------------------------------
    def axis(self, name):
        idx = self.profile["axes"].get(name, -1)
        if 0 <= idx < len(self.axes):
            return self.axes[idx]
        return 0.0

    def stick(self, name):
        return _deadzone(self.axis(name), C.GAMEPAD_DEADZONE)

    def trigger(self, name):
        """Gâchette normalisée 0..1 (repos à -1 sous SDL, parfois 0 avant le 1er appui)."""
        v = self.axis(name)
        if v != 0.0:
            self.trigger_seen[name] = True
        if not self.trigger_seen.get(name):
            return 0.0
        return max(0.0, min(1.0, (v + 1.0) * 0.5))

    def held(self, button):
        return button in self.now_buttons

    def pressed(self, button):
        return button in self.now_buttons and button not in self.prev_buttons

    def rumble(self, low, high, ms):
        if not (C.GAMEPAD_RUMBLE and self.joy is not None):
            return
        try:
            self.joy.rumble(max(0, min(1, low)), max(0, min(1, high)), int(ms))
        except Exception:
            pass


# ============================================================================
class InputManager:
    """Fusionne clavier/souris et manette en actions de jeu."""

    # action -> bouton manette (phase FPS)
    PAD_FPS = {
        "fire": "r2", "aim": "l2", "knife": "r1", "reload": "square",
        "flashlight": "triangle", "nightvision": "l1", "interact": "cross",
        "inventory": "touchpad", "heal": "dpad_up", "prev_item": "dpad_left",
        "next_item": "dpad_right", "use_item": "dpad_down", "pause": "options",
        "crouch": "circle", "run": "l3", "drop": "triangle",
        "confirm": "cross", "back": "circle",
        "menu_up": "dpad_up", "menu_down": "dpad_down",
        # navette
        "ship_assist": "triangle", "ship_brake": "circle", "ship_camera": "r3",
        "journal": "create",
    }
    # action -> touche clavier / souris
    KB = {
        "fire": "left mouse", "aim": "right mouse",
        "knife": C.KEYS["knife"], "reload": C.KEYS["reload"],
        "flashlight": C.KEYS["flashlight"], "nightvision": C.KEYS["nightvision"],
        "interact": C.KEYS["interact"], "inventory": C.KEYS["inventory"],
        "heal": C.KEYS["heal"], "prev_item": C.KEYS["prev_item"], "next_item": C.KEYS["next_item"],
        "use_item": C.KEYS["use_item"], "pause": C.KEYS["pause"], "crouch": C.KEYS["crouch"],
        "run": C.KEYS["run"], "drop": C.KEYS["drop"], "debug": C.KEYS["debug"],
        "confirm": "enter", "back": "escape", "menu_up": "up arrow", "menu_down": "down arrow",
        "ship_assist": C.KEYS["ship_assist"], "ship_brake": C.KEYS["ship_brake"],
        "ship_camera": C.KEYS["ship_camera"],
        "debug_power": C.KEYS["debug_power"], "debug_screamer": C.KEYS["debug_screamer"],
        "debug_docs": C.KEYS["debug_docs"], "debug_reveal": C.KEYS["debug_reveal"],
        "journal": C.KEYS["journal"], "controls": C.KEYS["controls"],
    }
    # alternatives clavier
    KB_ALT = {"confirm": ["space", C.KEYS["interact"]], "menu_up": [C.KEYS["forward"]],
              "menu_down": [C.KEYS["back"]], "prev_item": ["scroll up", "left arrow"],
              "next_item": ["scroll down", "right arrow"], "drop": ["backspace"]}

    def __init__(self):
        self.pad = Gamepad()
        self._kb_pressed = set()
        self.move_x = 0.0
        self.move_y = 0.0
        self.look_x = 0.0
        self.look_y = 0.0
        self.using_pad = False
        self.run_toggle = False
        self.debug_overlay = None

    # appelé depuis input() d'Ursina
    def on_key(self, key):
        self._kb_pressed.add(key)
        if key.endswith(" down") and "mouse" in key:
            self._kb_pressed.add(key.replace(" down", ""))
        if key == "f3":
            self.toggle_debug()

    def _kb_held(self, key):
        if key in ("left mouse", "right mouse"):
            return bool(held_keys[key])
        if key == "shift":
            return bool(held_keys["shift"] or held_keys["left shift"] or held_keys["right shift"])
        if key == "control":
            return bool(held_keys["control"] or held_keys["left control"] or held_keys["right control"])
        return bool(held_keys[key])

    # ------------------------------------------------------------------
    def update(self, dt, mouse_look=True):
        self.pad.poll(dt)
        p = self.pad
        # déplacement
        kx = self._kb_held(C.KEYS["right"]) - self._kb_held(C.KEYS["left"])
        ky = self._kb_held(C.KEYS["forward"]) - self._kb_held(C.KEYS["back"])
        px, py = p.stick("lx"), -p.stick("ly")
        if abs(px) + abs(py) > 0.05:
            self.using_pad = True
        elif kx or ky:
            self.using_pad = False
        mx, my = kx + px, ky + py
        mag = math.hypot(mx, my)
        if mag > 1:
            mx, my = mx / mag, my / mag
        self.move_x, self.move_y = mx, my
        # regard : souris (degrés par image) + stick droit (degrés / s)
        lx = ly = 0.0
        if mouse_look and mouse.locked:
            lx += mouse.velocity[0] * C.MOUSE_SENSITIVITY
            ly += mouse.velocity[1] * C.MOUSE_SENSITIVITY * (-1 if C.INVERT_MOUSE_Y else 1)
        rx, ry = p.stick("rx"), p.stick("ry")
        if rx or ry:
            lx += _curve(rx, C.GAMEPAD_LOOK_CURVE) * C.GAMEPAD_LOOK_SPEED * dt
            ly += -_curve(ry, C.GAMEPAD_LOOK_CURVE) * C.GAMEPAD_LOOK_SPEED * dt * (-1 if C.GAMEPAD_INVERT_Y else 1)
        self.look_x, self.look_y = lx, ly
        # L3 : course en bascule (s'arrête quand le stick revient au centre)
        if p.pressed("l3"):
            self.run_toggle = not self.run_toggle
        if abs(py) + abs(px) < 0.2:
            self.run_toggle = False
        if self.debug_overlay:
            self.debug_overlay.refresh(self.pad)

    def end_frame(self):
        self._kb_pressed.clear()

    # ------------------------------------------------------------------
    def pressed(self, action):
        k = self.KB.get(action)
        if k and k in self._kb_pressed:
            return True
        for alt in self.KB_ALT.get(action, []):
            if alt in self._kb_pressed:
                return True
        b = self.PAD_FPS.get(action)
        return bool(b and self.pad.pressed(b))

    def held(self, action):
        if action == "run" and self.run_toggle:
            return True
        k = self.KB.get(action)
        if k and self._kb_held(k):
            return True
        b = self.PAD_FPS.get(action)
        return bool(b and self.pad.held(b))

    # ------------------------------------------------------------------
    # Phase TPS : commandes de la navette
    def ship_axes(self, dt):
        """
        Commandes de la navette, normalisées :
        (poussée, strafe, vertical, tangage, lacet, roulis, boost), toutes dans [-1, 1]
        sauf boost (booléen). Tangage > 0 = nez vers le bas, lacet > 0 = vers la droite.
        La rotation passe par une courbe de réponse (zone morte + exposant) réglable,
        identique pour la souris et le stick.
        """
        p = self.pad
        thrust = self._kb_held(C.KEYS["forward"]) - self._kb_held(C.KEYS["back"]) - p.stick("ly")
        strafe = self._kb_held(C.KEYS["right"]) - self._kb_held(C.KEYS["left"]) + p.stick("lx")
        vert = (self._kb_held(C.KEYS["ship_up"]) - self._kb_held(C.KEYS["ship_down"])
                + p.trigger("r2") - p.trigger("l2"))
        roll = (self._kb_held(C.KEYS["ship_roll_left"]) - self._kb_held(C.KEYS["ship_roll_right"])
                + p.held("l1") - p.held("r1"))
        pitch = yaw = 0.0
        if mouse.locked:
            # vitesse de la souris (écrans / s) -> commande de rotation
            inv = 1.0 / max(dt, 1e-4)
            yaw += mouse.velocity[0] * inv * C.SHIP_MOUSE_SENS
            pitch += -mouse.velocity[1] * inv * C.SHIP_MOUSE_SENS * (-1 if C.INVERT_MOUSE_Y else 1)
        yaw += p.stick("rx")
        pitch += p.stick("ry") * (-1 if C.GAMEPAD_INVERT_Y else 1)
        clamp = lambda v: max(-1.0, min(1.0, v))

        def shape(v):
            v = clamp(v)
            dz = C.SHIP_LOOK_DEADZONE
            if abs(v) < dz:
                return 0.0
            v = math.copysign((abs(v) - dz) / (1 - dz), v)
            return math.copysign(abs(v) ** C.SHIP_LOOK_EXPONENT, v)

        boost = self._kb_held(C.KEYS["ship_boost"]) or p.held("cross")
        return clamp(thrust), clamp(strafe), clamp(vert), shape(pitch), shape(yaw), clamp(roll), boost

    def rumble(self, low, high, ms):
        self.pad.rumble(low, high, ms)

    # ------------------------------------------------------------------
    def toggle_debug(self):
        if self.debug_overlay:
            self.debug_overlay.destroy()
            self.debug_overlay = None
        else:
            self.debug_overlay = GamepadDebugOverlay()


class GamepadDebugOverlay:
    """Mode debug (F3) : affiche en temps réel les index des axes/boutons."""

    def __init__(self):
        self.bg = Entity(parent=camera.ui, model='quad', color=color.rgba(0, 0, 0, .7),
                         scale=(.62, .5), position=(-.55, .12), z=-5)
        self.text = Text(parent=camera.ui, text='', position=(-.85, .36), scale=.75, z=-6,
                         color=color.lime, font='VeraMono.ttf')
        self.extra = ""

    def refresh(self, pad):
        lines = ["DEBUG MANETTE (F3)"]
        if not pad.ok:
            lines.append("pygame joystick indisponible")
        elif not pad.connected:
            lines.append("Aucune manette détectée")
            lines.append("(branche-la ou appaire-la en Bluetooth)")
        else:
            lines.append(pad.name[:34])
            lines.append(f"profil : {pad.profile_name}")
            lines.append("AXES :")
            for i, a in enumerate(pad.axes):
                bar = "#" * int((a + 1) * 5)
                lines.append(f"  {i}: {a:+.2f} {bar}")
            on = [str(i) for i, b in enumerate(pad.buttons) if b]
            lines.append("BOUTONS : " + (" ".join(on) if on else "-"))
            lines.append("CROIX : " + " ".join(str(h) for h in pad.hats) if pad.hats else "CROIX : (boutons)")
            lines.append("logiques : " + " ".join(sorted(pad.now_buttons)))
        if self.extra:
            lines.append(self.extra)
        self.text.text = "\n".join(lines)

    def destroy(self):
        from ursina import destroy
        destroy(self.bg)
        destroy(self.text)
