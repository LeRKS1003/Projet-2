# -*- coding: utf-8 -*-
"""
aliens.py — Petites créatures extraterrestres (parasites-araignées).

  * petites, rapides, mouvement saccadé (par à-coups) ;
  * apparaissent depuis les grilles d'aération, le plafond ou les cadavres ;
  * attaquent en groupe de 1 à 4, bondissent sur le joueur ;
  * meurent en un ou deux coups (couteau ou pistolet) ;
  * plus nombreuses en mode horreur et quand le joueur porte le disque dur.
"""
import math
import random

from ursina import Entity, color, destroy

import config as C

EMERGE, IDLE, CHASE, WINDUP, LEAP, RECOVER, DEAD = range(7)


class Alien:
    RADIUS = .45

    def __init__(self, mgr, x, z, mode="grille", aware=True, from_dir=(0, 0)):
        self.mgr = mgr
        self.game = mgr.game
        self.level = mgr.game.level
        self.x, self.z = x, z
        self.y = 0.0
        self.yaw = random.uniform(0, 360)
        self.hp = C.ALIEN_HP
        self.aware = aware
        self.state = EMERGE
        self.t = 0.0
        self.mode = mode
        self.path = []
        self.repath = 0.0
        self.burst = 0.0
        self.bursting = True
        self.bite_cd = 0.0
        self.leap_from = None
        self.leap_to = None
        self.leap_t = 0.0
        self.leap_hit = False
        self.phase = random.uniform(0, 10)
        self.dead_t = 0.0
        self.from_dir = from_dir
        self.scream_cd = random.uniform(1, 3)
        # position de départ selon le mode d'apparition
        if mode == "ceiling":
            self.y = self.level.ceiling_at(x, z) - .2
        elif mode == "grille":
            self.x -= from_dir[0] * .6
            self.z -= from_dir[1] * .6
        self._build()

    def _build(self):
        skin = color.rgb(.2, .17, .12)
        dark = color.rgb(.1, .08, .06)
        self.root = Entity(name='alien')
        self.body = Entity(parent=self.root, y=.25)
        Entity(parent=self.body, model='sphere', color=skin, scale=(.36, .2, .42))
        Entity(parent=self.body, model='sphere', color=dark, scale=(.3, .24, .38), z=-.3, y=.04)   # abdomen
        head = Entity(parent=self.body, model='sphere', color=skin, scale=(.2, .14, .2), z=.25)
        for s in (-1, 1):
            Entity(parent=head, model='sphere', color=color.rgb(1, .15, .05), scale=.28, position=(s * .3, .25, .35),
                   unlit=True)
            Entity(parent=head, model='cube', color=dark, scale=(.08, .08, .6), position=(s * .25, -.3, .6),
                   rotation_y=-s * 25)   # mandibules
        self.legs = []
        for k in range(4):
            for s in (-1, 1):
                hip = Entity(parent=self.body, position=(s * .15, 0, .15 - k * .12), rotation_y=s * (60 - k * 30))
                up = Entity(parent=hip, rotation_z=-s * 35)
                Entity(parent=up, model='cube', color=dark, scale=(.3, .03, .03), x=s * .15)
                knee = Entity(parent=up, x=s * .3, rotation_z=s * 75)
                Entity(parent=knee, model='cube', color=dark, scale=(.32, .025, .025), x=s * .16)
                self.legs.append((up, knee, s, k))
        self.root.position = (self.x, self.y, self.z)

    # ------------------------------------------------------------------
    def center3(self):
        return (self.x, self.y + .25, self.z)

    def on_hit(self, dmg, pos, gun):
        if self.state == DEAD:
            return
        self.hp -= dmg
        self.aware = True
        g = self.game
        if self.hp <= 0:
            self.state = DEAD
            self.dead_t = 0
            g.audio.play_at("alien_die", self.center3(), 1.0, random.uniform(.9, 1.2))
            g.player.kills += 1
            g.stats["kills"] += 1
            # tache verdâtre
            self.splat = Entity(model='quad', color=color.rgba(.25, .4, .08, .8), scale=random.uniform(.6, 1),
                                position=(self.x, .015, self.z), rotation_x=90, rotation_y=random.uniform(0, 360),
                                double_sided=True)
            self.mgr.decals.append(self.splat)
            if len(self.mgr.decals) > 25:
                destroy(self.mgr.decals.pop(0))
        else:
            # recule sous l'impact
            if self.state == LEAP:
                self.state = RECOVER
                self.t = 0
            p = g.player
            dx, dz = self.x - p.x, self.z - p.z
            d = math.hypot(dx, dz) or 1
            self.x, self.z = self.level.collide(self.x + dx / d * .6, self.z + dz / d * .6, .25, .02, .4,
                                                ignore=("grille",))
            g.audio.play_at(f"alien_screech{random.randint(0, 1)}", self.center3(), .9, 1.3)

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        p = g.player
        self.t += dt
        self.bite_cd = max(0, self.bite_cd - dt)
        if self.state == DEAD:
            self.dead_t += dt
            self.body.rotation_z = min(180, self.dead_t * 900)
            self.body.y = max(.05, .25 - self.dead_t * .5)
            return self.dead_t < 1.2
        dx, dz = p.x - self.x, p.z - self.z
        dist = math.hypot(dx, dz)
        moved = 0.0
        if self.state == EMERGE:
            dur = .7 if self.mode != "ceiling" else .55
            if self.mode == "ceiling":
                # tombe du plafond
                self.y = max(0.0, self.y - dt * 7)
                if self.y <= 0:
                    self.state = CHASE if self.aware else IDLE
                    g.audio.play_at("alien_skitter", self.center3(), .7)
            else:
                # sort de la grille / du cadavre en rampant
                fx, fz = self.from_dir
                self.x += fx * dt * 1.2
                self.z += fz * dt * 1.2
                self.yaw = math.degrees(math.atan2(fx, fz)) if (fx or fz) else self.yaw
                moved = 1.2 * dt
                if self.t > dur:
                    self.state = CHASE if self.aware else IDLE
            if self.t > 1.5:
                self.state = CHASE if self.aware else IDLE
        elif self.state == IDLE:
            # tapie : repère le joueur s'il est proche et visible (ou bruyant)
            if self.t > .5:
                self.t = 0
                if dist < 11 and not p.hidden and self.level.line_of_sight(self.center3(), p.pos3):
                    if dist < 5 or not p.crouched:
                        self.alert()
            if random.random() < dt * .5:
                self.yaw += random.uniform(-60, 60)
        elif self.state == CHASE:
            if p.hidden:
                # le joueur caché : elles rôdent autour
                if random.random() < dt * .3:
                    self.state = IDLE
            los = dist < 12 and self.level.line_of_sight(self.center3(), p.pos3)
            speed = C.ALIEN_SPEED * (1.6 if self.bursting else 0.0)
            # mouvement saccadé : à-coups rapides entrecoupés d'arrêts
            self.burst -= dt
            if self.burst <= 0:
                self.bursting = not self.bursting
                self.burst = random.uniform(.18, .38) if self.bursting else random.uniform(.06, .16)
                if not self.bursting:
                    self.yaw += random.uniform(-25, 25)
            target = None
            if los and dist < 7:
                target = (p.x, p.z)
                self.path = []
            else:
                self.repath -= dt
                if self.repath <= 0 or not self.path:
                    self.repath = .7
                    L = self.level
                    path = L.find_path(L.cell_at(self.x, self.z), L.cell_at(p.x, p.z), "alien", 2500)
                    self.path = [L.cell_center(*c) for c in path[1:]] if path else []
                if self.path:
                    target = self.path[0]
                    if math.hypot(target[0] - self.x, target[1] - self.z) < .4:
                        self.path.pop(0)
                        target = self.path[0] if self.path else None
            if target and speed > 0:
                tx, tz = target[0] - self.x, target[1] - self.z
                d = math.hypot(tx, tz)
                if d > .05:
                    step = min(d, speed * dt)
                    nx, nz = self.x + tx / d * step, self.z + tz / d * step
                    self.x, self.z = self.level.collide(nx, nz, .22, .02, .4, ignore=("grille",))
                    moved = step
                    self.yaw = math.degrees(math.atan2(tx, tz))
                    self._open_door_ahead(tx / d, tz / d)
            self.scream_cd -= dt
            if self.scream_cd <= 0:
                self.scream_cd = random.uniform(2.5, 5)
                g.audio.play_at(f"alien_screech{random.randint(0, 1)}", self.center3(), .55, random.uniform(.9, 1.3))
            if los and dist < C.ALIEN_LEAP_DIST and dist > 1.3 and not p.hidden:
                self.state = WINDUP
                self.t = 0
                g.audio.play_at("alien_screech0", self.center3(), 1.0, 1.4)
            elif dist < 1.1 and not p.hidden and self.bite_cd <= 0:
                self.bite_cd = 1.1
                p.damage(C.ALIEN_BITE_DAMAGE, self.center3())
        elif self.state == WINDUP:
            # se ramasse avant de bondir (fenêtre pour réagir)
            self.yaw = math.degrees(math.atan2(dx, dz))
            self.body.y = .15
            if self.t > .35:
                self.state = LEAP
                self.t = 0
                self.leap_from = (self.x, self.z)
                lead = .35
                self.leap_to = (p.x + p.vx * lead, p.z + p.vz * lead)
                self.leap_hit = False
        elif self.state == LEAP:
            dur = .45
            k = min(1.0, self.t / dur)
            nx = self.leap_from[0] + (self.leap_to[0] - self.leap_from[0]) * k
            nz = self.leap_from[1] + (self.leap_to[1] - self.leap_from[1]) * k
            self.x, self.z = self.level.collide(nx, nz, .22, .3, 1.2, ignore=("grille",))
            self.y = math.sin(k * math.pi) * 1.1
            if not self.leap_hit and math.hypot(p.x - self.x, p.z - self.z) < .8 and not p.hidden:
                self.leap_hit = True
                p.damage(C.ALIEN_DAMAGE, self.center3())
                g.audio.play_at("alien_screech1", self.center3(), 1.0, 1.1)
            if k >= 1:
                self.y = 0
                self.state = RECOVER
                self.t = 0
        elif self.state == RECOVER:
            if self.t > .8:
                self.state = CHASE
                self.t = 0
        self._animate(dt, moved)
        return True

    def alert(self):
        if not self.aware:
            self.aware = True
            self.state = CHASE
            self.game.audio.play_at("alien_screech1", self.center3(), .9)

    def _open_door_ahead(self, dx, dz):
        L = self.level
        a = L.cell_at(self.x, self.z)
        b = L.cell_at(self.x + dx * .8, self.z + dz * .8)
        if a != b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
            from generator import ekey
            door = L.doors.get(ekey(a[0], a[1], b[0], b[1]))
            if door and door.target < 1:
                door.open(hold=3)

    def _animate(self, dt, moved):
        self.phase += moved * 14 + dt * (2 if self.state == IDLE else 0)
        self.root.position = (self.x, self.y, self.z)
        self.root.rotation_y = self.yaw
        if self.state not in (WINDUP,):
            self.body.y = .25 + abs(math.sin(self.phase * .5)) * .03
        for up, knee, s, k in self.legs:
            a = math.sin(self.phase + k * 1.3 + (0 if s > 0 else math.pi))
            up.rotation_y = a * 18
            up.rotation_z = -s * (35 + max(0, a) * 15)
        if self.state == LEAP:
            self.body.rotation_x = -30
        else:
            self.body.rotation_x = 0

    def destroy(self):
        destroy(self.root)


# ============================================================================
class AlienManager:
    def __init__(self, game):
        self.game = game
        self.aliens = []
        self.decals = []
        self.spawn_timer = random.uniform(*C.ALIEN_SPAWN_INTERVAL)
        self.grace = 35.0

    @property
    def alive(self):
        return [a for a in self.aliens if a.state != DEAD]

    def max_count(self):
        return C.ALIEN_MAX_HORROR if self.game.horror.active else C.ALIEN_MAX

    def hit_spheres(self):
        return [(a, a.center3(), Alien.RADIUS) for a in self.aliens if a.state != DEAD]

    def hear(self, pos, radius, kind):
        for a in self.aliens:
            if a.state == IDLE and math.hypot(pos[0] - a.x, pos[2] - a.z) < radius * .8:
                a.alert()

    # ------------------------------------------------------------------
    def spawn_near_player(self, n, aware=True):
        g = self.game
        p = g.player
        L = g.level
        if p is None:
            return 0
        cands = []
        for (x, z, kind) in L.spawn_points:
            if kind == "spark":
                continue
            d = math.hypot(x - p.x, z - p.z)
            if 6 < d < 45:
                r = L.room_at(x, z)
                # le hangar reste calme tant que le disque dur n'est pas pris
                if r is not None and r.type == "hangar" and not g.has_hdd():
                    continue
                # on évite d'apparaître sous les yeux du joueur
                seen = d < 14 and L.line_of_sight((x, 1.0, z), p.pos3)
                cands.append((d + random.uniform(0, 6) + (15 if seen else 0), x, z, kind))
        cands.sort()
        spawned = 0
        for _, x, z, kind in cands[:max(3, n)]:
            if spawned >= n or len(self.alive) >= self.max_count():
                break
            self.spawn(x, z, kind, aware)
            spawned += 1
        return spawned

    def spawn(self, x, z, kind, aware=True):
        g = self.game
        L = g.level
        from_dir = (0, 0)
        if kind == "grille":
            # trouve la grille correspondante pour sortir dans le bon sens
            best = None
            for gr in L.grilles.values():
                gx, gz = gr.room_side_point(.5)
                d = math.hypot(gx - x, gz - z)
                if best is None or d < best[0]:
                    best = (d, gr)
            if best and best[0] < .8:
                gr = best[1]
                ri, rj = gr.room_cell
                vi, vj = gr.vent_cell
                from_dir = (ri - vi, rj - vj)
                if not gr.opened:
                    gr.set_open(True)
                g.audio.play_at("vent_bang", (gr.pos[0], .5, gr.pos[1]), 1.0)
        else:
            g.audio.play_at("alien_skitter", (x, 2.5, z), 1.0)
        a = Alien(self, x, z, kind, aware, from_dir)
        self.aliens.append(a)
        return a

    def burst_from_corpse(self, pos, n):
        for k in range(n):
            a = random.uniform(0, 2 * math.pi)
            al = Alien(self, pos[0], pos[2], "corpse", True, (math.cos(a), math.sin(a)))
            self.aliens.append(al)
        self.game.audio.play_at("alien_screech1", pos, 1.0, .9)

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        for a in list(self.aliens):
            if not a.update(dt):
                a.destroy()
                self.aliens.remove(a)
        if self.grace > 0:
            self.grace -= dt
            return
        # apparitions régulières (embuscades)
        mult = C.ALIEN_HDD_MULT if g.has_hdd() else 1.0
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = random.uniform(*C.ALIEN_SPAWN_INTERVAL) * mult
            if len(self.alive) < self.max_count():
                n = random.randint(1, 2) if not g.has_hdd() else random.randint(2, 3)
                self.spawn_near_player(n, aware=random.random() < .6 or g.has_hdd())

    def destroy(self):
        for a in self.aliens:
            a.destroy()
        for d in self.decals:
            destroy(d)
        self.aliens = []
