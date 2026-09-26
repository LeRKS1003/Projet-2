# -*- coding: utf-8 -*-
"""
player.py — Contrôleur FPS : déplacement avec inertie, course (endurance),
accroupissement (obligatoire dans les conduits), collisions sur la grille,
bruit émis, bruits de pas, balancement de la tête, santé (aucune
régénération), interactions (portes, casiers, cadavres...), cachette dans
les casiers.
"""
import math
import random

from ursina import camera

import config as C


class Player:
    def __init__(self, game, level, x, z, yaw=0.0):
        self.game = game
        self.level = level
        self.x, self.z = x, z
        self.yaw = yaw
        self.pitch = 0.0
        self.vx = self.vz = 0.0
        self.crouched = False
        self.crouch_k = 0.0          # 0 debout -> 1 accroupi (lissé)
        self.health = C.MAX_HEALTH
        self.stamina = C.STAMINA_MAX
        self.exhausted = False
        self.alive = True
        self.running = False
        self.moving = False
        self.noise_radius = 0.0
        self.noise_level = 0.0
        self._noise_timer = 0.0
        self._step_dist = 0.0
        self._bob = 0.0
        self.trauma = 0.0            # secousses dues aux coups
        self.hidden_in = None
        self.search_target = None
        self.search_progress = 0.0
        self.focus = None            # objet interactif visé
        self.hurt_flash = 0.0
        self._heart_timer = 0.0
        self.fov_target = C.FOV
        self.frozen = False
        self.hide_yaw = 0.0
        self.last_damage_dir = 0.0
        self.saw_hide = False
        self.kills = 0

    # ------------------------------------------------------------------
    @property
    def height(self):
        return C.PLAYER_HEIGHT + (C.PLAYER_CROUCH_HEIGHT - C.PLAYER_HEIGHT) * self.crouch_k

    @property
    def eye(self):
        return C.EYE_HEIGHT + (C.CROUCH_EYE_HEIGHT - C.EYE_HEIGHT) * self.crouch_k

    @property
    def pos3(self):
        return (self.x, self.eye, self.z)

    def forward2(self):
        a = math.radians(self.yaw)
        return math.sin(a), math.cos(a)

    def in_vent(self):
        return self.level.ceiling_at(self.x, self.z) < C.PLAYER_HEIGHT

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        if not self.alive:
            return
        g = self.game
        # --- regard -------------------------------------------------------
        if not g.inventory_ui.open:
            self.yaw += inp.look_x
            self.pitch = max(-85, min(85, self.pitch - inp.look_y))
        if self.hidden_in is not None:
            # dans un casier : regard limité, aucun déplacement
            d = (self.yaw - self.hide_yaw + 180) % 360 - 180
            d = max(-40, min(40, d))
            self.yaw = self.hide_yaw + d
            self.pitch = max(-25, min(25, self.pitch))
            self.noise_radius = 0
            self.noise_level = 0
            if inp.pressed("interact") and not g.ui_consumed:
                self.leave_hiding()
            self._apply_camera(dt)
            return

        # --- accroupi -----------------------------------------------------
        want_toggle = inp.pressed("crouch") and not g.ui_consumed     # Rond ferme aussi les documents
        if C.CROUCH_TOGGLE:
            if want_toggle:
                self.crouched = not self.crouched
        else:
            self.crouched = inp.held("crouch")
        ceiling = self.level.ceiling_at(self.x, self.z)
        if not self.crouched and ceiling < C.PLAYER_HEIGHT + .05:
            self.crouched = True
            if want_toggle:
                g.hud.message("Trop bas pour te relever")
        # impossible de se relever sous une grille/un obstacle bas
        if not self.crouched and self.crouch_k > .5:
            _x, _z = self.level.collide(self.x, self.z, C.PLAYER_RADIUS * .9, 0.05, C.PLAYER_HEIGHT)
            if abs(_x - self.x) + abs(_z - self.z) > .05:
                self.crouched = True
        target_k = 1.0 if self.crouched else 0.0
        self.crouch_k += (target_k - self.crouch_k) * min(1, dt * 10)

        # --- fouille d'un cadavre (le joueur est vulnérable) -----------------
        if self.search_target is not None:
            if inp.held("interact") and self.search_target is self.focus:
                self.search_progress += dt
                hook = getattr(self.search_target, "on_hold", None)
                if hook is not None:
                    hook(g, dt)          # ex. grincements pendant qu'on force une porte
                if self.search_progress >= self.search_target.hold_time:
                    t = self.search_target
                    self.search_target = None
                    self.search_progress = 0
                    t.interact(g)
            else:
                self.search_target = None
                self.search_progress = 0

        # --- déplacement ----------------------------------------------------
        mx, my = inp.move_x, inp.move_y
        if self.search_target is not None or self.frozen or g.inventory_ui.reading:
            mx = my = 0
        self.moving = abs(mx) + abs(my) > 0.1
        want_run = inp.held("run") and my > 0.3 and not self.crouched
        if self.exhausted:
            want_run = False
        self.running = want_run and self.moving
        if self.running:
            self.stamina = max(0.0, self.stamina - C.STAMINA_DRAIN * dt)
            if self.stamina <= 0:
                self.exhausted = True
                g.audio.play("breath", .8)
        else:
            self.stamina = min(C.STAMINA_MAX, self.stamina + C.STAMINA_REGEN * dt * (1.5 if not self.moving else 1))
            if self.exhausted and self.stamina > 35:
                self.exhausted = False
        if self.crouched:
            speed = C.CROUCH_SPEED
        elif self.running:
            speed = C.RUN_SPEED
        else:
            speed = C.WALK_SPEED
        if g.weapons.aiming:
            speed *= .6
        if self.health < C.LOW_HEALTH:
            speed *= .88
        fx, fz = self.forward2()
        rx, rz = fz, -fx
        tvx = (fx * my + rx * mx) * speed
        tvz = (fz * my + rz * mx) * speed
        k = min(1.0, C.ACCELERATION * dt)
        self.vx += (tvx - self.vx) * k
        self.vz += (tvz - self.vz) * k
        # déplacement par sous-pas pour ne pas traverser les murs
        dist = math.hypot(self.vx, self.vz) * dt
        steps = max(1, int(dist / .15) + 1)
        ox, oz = self.x, self.z
        for _ in range(steps):
            nx = self.x + self.vx * dt / steps
            nz = self.z + self.vz * dt / steps
            self.x, self.z = self.level.collide(nx, nz, C.PLAYER_RADIUS, 0.05, self.height)
        moved = math.hypot(self.x - ox, self.z - oz)
        actual_speed = moved / max(dt, 1e-5)

        # --- bruit et pas -------------------------------------------------
        if actual_speed > .4:
            if self.crouched:
                self.noise_radius = C.NOISE_CROUCH
            elif self.running:
                self.noise_radius = C.NOISE_RUN
            else:
                self.noise_radius = C.NOISE_WALK
        else:
            self.noise_radius = 0.0
        self.noise_level = self.noise_radius / C.NOISE_RUN
        self._noise_timer -= dt
        if self._noise_timer <= 0 and self.noise_radius > 0:
            self._noise_timer = .5
            g.noise((self.x, 1.0, self.z), self.noise_radius, "step")
        self._step_dist += moved
        stride = 1.0 if self.crouched else (2.3 if self.running else 1.7)
        if self._step_dist >= stride:
            self._step_dist = 0
            if self.in_vent():
                g.audio.play("vent_crawl", .35, random.uniform(.9, 1.1))
            else:
                vol = .12 if self.crouched else (.55 if self.running else .3)
                g.audio.play(f"step{random.randint(0, 3)}", vol, random.uniform(.9, 1.1))
        if actual_speed > .3:
            self._bob += dt * (13 if self.running else (6 if self.crouched else 9))

        # --- interaction ----------------------------------------------------
        self._find_focus()
        if (inp.pressed("interact") and self.focus is not None and self.search_target is None
                and not g.ui_consumed):
            if self.focus.hold_time > 0:
                self.search_target = self.focus
                self.search_progress = 0
            else:
                self.focus.interact(g)

        # --- effets de santé ----------------------------------------------
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 1.8)
        self.trauma = max(0.0, self.trauma - dt * 1.5)
        if self.health < C.LOW_HEALTH:
            self._heart_timer -= dt
            if self._heart_timer <= 0:
                self._heart_timer = .75 + self.health / C.LOW_HEALTH * .5
                g.audio.play("heartbeat", .9)
                g.inp.rumble(.5, 0, 140)
        self._apply_camera(dt)

    # ------------------------------------------------------------------
    def _apply_camera(self, dt):
        g = self.game
        shake = self.trauma ** 2 + g.horror.shake_amount() + g.shake_amount * .6
        sx = (random.uniform(-1, 1)) * shake * 2.2
        sy = (random.uniform(-1, 1)) * shake * 2.2
        bob_y = math.sin(self._bob) * (.035 if not self.crouched else .02)
        bob_x = math.cos(self._bob * .5) * .02
        fx, fz = self.forward2()
        rx, rz = fz, -fx
        if self.hidden_in is not None:
            hp = self.hidden_in.hide_pos
            camera.position = (hp[0], 1.55, hp[2])
        else:
            camera.position = (self.x + rx * bob_x, self.eye + bob_y, self.z + rz * bob_x)
        tilt = 0.0
        if self.health < C.LOW_HEALTH:
            tilt = math.sin(g.time * 1.3) * (1 - self.health / C.LOW_HEALTH) * 2.5
        camera.rotation = (self.pitch + sy, self.yaw + sx, tilt + sx * .5)
        target = self.fov_target
        if self.health < C.LOW_HEALTH:
            target += math.sin(g.time * 2) * 2
        camera.fov += (target - camera.fov) * min(1, dt * 10)

    def _find_focus(self):
        best, best_s = None, -1e9
        cp = camera.world_position
        fw = camera.forward
        for obj in self.level.interactables_near(self.x, self.z):
            if obj.prompt(self.game) is None:
                continue
            dx, dy, dz = obj.pos[0] - cp.x, obj.pos[1] - cp.y, obj.pos[2] - cp.z
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d > max(C.INTERACT_DISTANCE, obj.radius) + .3:
                continue
            dot = (dx * fw.x + dy * fw.y + dz * fw.z) / max(d, 1e-4)
            if dot < .55 and d > .9:
                continue
            s = dot * 2 - d * .5
            if s > best_s:
                best, best_s = obj, s
        if best is not self.focus and self.search_target is not None:
            self.search_target = None
            self.search_progress = 0
        self.focus = best

    # ------------------------------------------------------------------
    def damage(self, amount, source=None):
        if not self.alive:
            return
        g = self.game
        self.health = max(0, self.health - amount)
        self.hurt_flash = min(1.0, self.hurt_flash + .6)
        self.trauma = min(1.0, self.trauma + .45)
        g.audio.play("hurt", .8, random.uniform(.9, 1.1))
        g.inp.rumble(.9, .7, 260)
        if source is not None:
            a = math.degrees(math.atan2(source[0] - self.x, source[2] - self.z))
            self.last_damage_dir = (a - self.yaw + 180) % 360 - 180
            g.hud.damage_indicator(self.last_damage_dir)
        # interrompt la fouille
        self.search_target = None
        if self.health <= 0:
            self.alive = False
            g.game_over("aliens")

    def heal(self, amount):
        self.health = min(C.MAX_HEALTH, self.health + amount)

    # ------------------------------------------------------------------
    def hide_in(self, locker):
        g = self.game
        self.hidden_in = locker
        locker.occupied = True
        locker.close_door()
        locker.door.enabled = False      # la vue passe par les fentes de la surimpression
        self.hide_yaw = math.degrees(math.atan2(locker.facing[0], locker.facing[1]))
        self.yaw = self.hide_yaw
        self.pitch = 0
        self.crouched = False
        # la créature t'a-t-elle vu te cacher ?
        self.saw_hide = g.creature is not None and g.creature.sees_player_now()
        g.audio.play_at("locker_open", locker.pos, .5, .8)
        g.hud.message("Caché. Ne bouge plus... (E / Croix pour sortir)")

    def leave_hiding(self):
        lk = self.hidden_in
        if lk is None:
            return
        lk.occupied = False
        lk.door.enabled = True
        lk.open_door()
        self.hidden_in = None
        self.x, self.z = lk.pos[0], lk.pos[2]
        self.x, self.z = self.level.collide(self.x, self.z, C.PLAYER_RADIUS, .05, self.height)
        self.game.audio.play_at("locker_open", lk.pos, .6)
        self.saw_hide = False

    @property
    def hidden(self):
        return self.hidden_in is not None
