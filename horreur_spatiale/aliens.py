# -*- coding: utf-8 -*-
"""
aliens.py — Petites créatures extraterrestres (« araignées »).

Comportement :
  * rares : jamais plus de 3 en même temps sur tout le vaisseau, en groupes
    de 1 à 3, avec un répit après la mort d'un groupe ;
  * rapides, mouvement saccadé (par à-coups) ;
  * apparaissent depuis les grilles d'aération, le plafond (où elles rampent
    à l'envers avant de se laisser tomber sur le joueur) ou les cadavres ;
  * bondissent sur le joueur ; meurent en un ou deux coups ;
  * tuées par surprise au couteau : mort instantanée et silencieuse ;
  * avec le disque dur : pas plus nombreuses, mais plus agressives.

Rendu (meshes personnalisés, aucun asset) :
  * céphalothorax chitineux luisant + abdomen gonflé, veiné, un peu translucide ;
  * 8 pattes articulées en 3 segments (fémur, tibia, tarse pointu) ;
  * grappe d'yeux rouges émissifs, mandibules qui s'ouvrent avant le bond ;
  * animation procédurale : marche en vague, tremblements, abdomen qui
    palpite, bond pattes repliées, mort pattes recroquevillées, flaque verte.
"""
import math
import random

import numpy as np
from panda3d.core import NodePath, TransparencyAttrib
from ursina import application, camera

import config as C
import textures
from geometry import MeshBuilder

EMERGE, IDLE, CHASE, WINDUP, LEAP, RECOVER, DEAD, CEILING, DROP = range(9)

# dimensions des pattes (m)
FEMUR, TIBIA, TARSUS = .2, .24, .19


# ============================================================================
# MATÉRIAUX
# ============================================================================
def _carapace(rng):
    """Chitine brun-noir luisante, plaques et arêtes."""
    s = 256
    n = textures.fractal_noise(s, s, rng, 6, base=4)
    yy, xx = np.mgrid[0:s, 0:s]
    plates = (np.abs(((yy / 32) % 1) - .5) > .46).astype(np.float32)
    h = .5 + (n - .5) * .5 - plates * .35
    alb = (.18 + .1 * n)[..., None] * np.array([1.0, .82, .62])
    alb[plates > 0] *= .5
    rough = np.clip(.18 + .15 * n, .05, 1)
    return alb, h, rough, (1.3, 70, 2.2)


def _abdomen(rng):
    """Chair gonflée, pâle et veinée (humide)."""
    s = 256
    n = textures.fractal_noise(s, s, rng, 6, base=3)
    v = textures.fractal_noise(s, s, rng, 5, base=5)
    veins = np.clip(1 - np.abs(v - .5) * 22, 0, 1)
    alb = np.dstack([.42 + .15 * n, .36 + .1 * n, .3 + .08 * n])
    alb = alb * (1 - veins[..., None] * .7) + veins[..., None] * np.array([.35, .05, .12])
    h = .5 + veins * .3 + (n - .5) * .2
    rough = np.clip(.3 - veins * .1, .05, 1)
    return np.clip(alb, 0, 1), h, rough, (1.1, 55, 1.6)


_TEMPLATES = {}


def _templates():
    """Géométries partagées par toutes les araignées (construites une seule fois)."""
    if _TEMPLATES:
        return _TEMPLATES
    carapace = textures.material("spider_carapace", custom=_carapace)
    belly = textures.material("spider_abdomen", custom=_abdomen)

    def node(mb, name, mat=None, unlit=False, alpha=False):
        np_ = NodePath(mb.make_geom_node(name, tangents=mat is not None))
        if mat is not None:
            textures.apply_material(np_, mat)
        if unlit:
            np_.setLightOff(2)
        if alpha:
            np_.setTransparency(TransparencyAttrib.MAlpha)
        return np_

    # céphalothorax (extrusion octogonale) + crête dorsale + épines
    ceph = MeshBuilder(uv_scale=.15)
    ceph.loft([(-.1, 0, 0, .16, .08, .03), (-.04, 0, .01, .23, .12, .05), (.06, 0, .01, .21, .11, .05),
               (.14, 0, -.005, .13, .08, .035), (.18, 0, -.01, .07, .05, .02)], (1, 1, 1, 1))
    for k in range(4):
        ceph.bevel_box((0, .065, -.06 + k * .05), (.02, .025, .035), .006, (.8, .75, .7, 1), rot=(-20, 0, 0))
    for s in (-1, 1):
        ceph.bevel_box((s * .07, .05, .02), (.012, .04, .012), .004, (.9, .85, .8, 1), rot=(-15, 0, s * 25))
    _TEMPLATES["ceph"] = node(ceph, "spider_ceph", carapace)
    # abdomen gonflé, légèrement translucide
    ab = MeshBuilder(uv_scale=.2)
    ab.loft([(-.02, 0, .03, .1, .08, .03), (-.1, 0, .06, .26, .2, .08), (-.22, 0, .08, .32, .26, .1),
             (-.34, 0, .07, .26, .22, .09), (-.42, 0, .05, .1, .09, .035)], (1, 1, 1, .93))
    _TEMPLATES["abdomen"] = node(ab, "spider_abdomen", belly, alpha=True)
    # segments de patte (le long de +z, pivot à l'origine)
    fe = MeshBuilder(uv_scale=.1)
    fe.bevel_box((0, 0, FEMUR / 2), (.032, .03, FEMUR), .009, (1, 1, 1, 1))
    fe.bevel_box((0, .015, FEMUR * .55), (.01, .03, .012), .003, (1, 1, 1, 1))      # petite épine
    _TEMPLATES["femur"] = node(fe, "spider_femur", carapace)
    ti = MeshBuilder(uv_scale=.1)
    ti.bevel_box((0, 0, TIBIA / 2), (.022, .021, TIBIA), .006, (1, 1, 1, 1))
    _TEMPLATES["tibia"] = node(ti, "spider_tibia", carapace)
    ta = MeshBuilder(uv_scale=.1)
    ta.cone((0, 0, 0), .011, TARSUS, (1, 1, 1, 1), (.6, .55, .5, 1), 6, (0, 0, 1))
    _TEMPLATES["tarsus"] = node(ta, "spider_tarsus", carapace)
    # mandibule (crochet)
    md = MeshBuilder(uv_scale=.05)
    md.bevel_box((0, 0, .035), (.02, .025, .07), .007, (.9, .85, .8, 1))
    md.cone((0, -.005, .07), .008, .05, (.9, .85, .8, 1), (.5, .45, .4, 1), 6, (0, 0, 1))
    _TEMPLATES["mandible"] = node(md, "spider_mandible", carapace)
    # grappe d'yeux (émissifs)
    ey = MeshBuilder()
    for (x, y, r) in ((-.022, .02, .011), (.022, .02, .011), (-.045, .008, .008), (.045, .008, .008),
                      (-.012, .038, .006), (.012, .038, .006), (-.034, .032, .005), (.034, .032, .005)):
        ey.cylinder((x, y, 0), r, .004, (1, .12, .05, 1), 8, 'z')
    _TEMPLATES["eyes"] = node(ey, "spider_eyes", unlit=True)
    # flaque verte (décalque)
    pd = MeshBuilder()
    pd.poly([(-.5, 0, -.5), (.5, 0, -.5), (.5, 0, .5), (-.5, 0, .5)], (0, 1, 0), (1, 1, 1, 1),
            [(0, 0), (1, 0), (1, 1), (0, 1)])
    t = node(pd, "spider_puddle")
    t.setTexture(textures.get('splat_green')._texture)
    t.setTransparency(TransparencyAttrib.MAlpha)
    t.setDepthOffset(2)
    t.setDepthWrite(False)
    _TEMPLATES["puddle"] = t
    return _TEMPLATES


def _rot(np_, pitch=0.0, yaw=0.0, roll=0.0):
    """Rotation avec les conventions d'Ursina (tangage > 0 = vers le bas)."""
    np_.setHpr(-yaw, -pitch, roll)


# ============================================================================
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
        self.leap_hit = False
        self.phase = random.uniform(0, 10)
        self.dead_t = 0.0
        self.from_dir = from_dir
        self.scream_cd = random.uniform(1, 3)
        self.skitter_cd = random.uniform(.2, .6)
        self.idle_sound_cd = random.uniform(2, 6)
        self.jaw = 0.0
        self.roll = 0.0
        self.vy = 0.0
        self.silent_death = False
        self.aggro = C.ALIEN_HDD_AGGRO if self.game.has_hdd() else 1.0
        # position de départ selon le mode d'apparition
        if mode == "ceiling":
            self.y = self.level.ceiling_at(x, z) - .12
            self.roll = 180.0
            self.crawl_ceiling = random.random() < C.ALIEN_CEILING_CHANCE
        elif mode == "grille":
            self.x -= from_dir[0] * .6
            self.z -= from_dir[1] * .6
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        T = _templates()
        parent = self.game.world_root if self.game.world_root is not None else application.base.render
        self.root = parent.attachNewNode("spider")
        self.body = self.root.attachNewNode("body")
        s = random.uniform(.9, 1.1)                                  # individus de tailles variées
        self.body.setScale(s)
        T["ceph"].instanceTo(self.body)
        self.abdomen = self.body.attachNewNode("abdomen_pivot")
        self.abdomen.setPos(0, 0, -.06)
        T["abdomen"].instanceTo(self.abdomen)
        eyes = self.body.attachNewNode("eyes")
        eyes.setPos(0, 0, .181)
        T["eyes"].instanceTo(eyes)
        self.mandibles = []
        for sd in (-1, 1):
            m = self.body.attachNewNode("mandible")
            m.setPos(sd * .025, -.025, .17)
            T["mandible"].instanceTo(m)
            self.mandibles.append((m, sd))
        # 8 pattes : hanche (lacet + tangage) -> genou -> cheville
        self.legs = []
        for k in range(4):
            for sd in (-1, 1):
                hip = self.body.attachNewNode("hip")
                hip.setPos(sd * .075, .0, .09 - k * .055)
                T["femur"].instanceTo(hip)
                knee = hip.attachNewNode("knee")
                knee.setPos(0, 0, FEMUR)
                T["tibia"].instanceTo(knee)
                ankle = knee.attachNewNode("ankle")
                ankle.setPos(0, 0, TIBIA)
                T["tarsus"].instanceTo(ankle)
                base_yaw = sd * (40 + k * 32)
                group = (k % 2 == 0) == (sd > 0)                       # marche en tétrapode (vague)
                self.legs.append({"hip": hip, "knee": knee, "ankle": ankle, "yaw": base_yaw, "s": sd, "k": k,
                                  "grp": group, "jit": random.uniform(-.4, .4)})
        self.puddle = None
        self._place()

    def _place(self):
        self.root.setPos(self.x, self.y, self.z)
        _rot(self.root, 0, self.yaw, self.roll)

    # ------------------------------------------------------------------
    def center3(self):
        if self.roll > 90:
            return (self.x, self.y - .2, self.z)
        return (self.x, self.y + .22, self.z)

    def _occluded(self):
        """Source cachée par une cloison ou dans un conduit (son étouffé)."""
        cp = camera.world_position
        return not self.level.line_of_sight(self.center3(), (cp.x, cp.y, cp.z))

    def _skitter(self, vol=.6):
        self.game.audio.play_var("alien_skitter", 4, vol, pos=self.center3(), occluded=self._occluded())

    def on_hit(self, dmg, pos, gun, silent=False):
        if self.state == DEAD:
            return
        g = self.game
        self.hp -= dmg
        self.aware = True
        if self.hp <= 0:
            self.state = DEAD
            self.dead_t = 0
            self.silent_death = silent or not gun
            vol = .25 if silent else (.5 if not gun else 1.0)
            if silent:
                g.audio.play_at("knife_crack", self.center3(), .5, random.uniform(.9, 1.1))
            else:
                g.audio.play_var("alien_die", 2, vol, pos=self.center3())
            g.player.kills += 1
            g.stats["kills"] += 1
            self.mgr.on_death(self)
            # flaque de liquide vert qui s'étend
            self.puddle = self.root.getParent().attachNewNode("puddle")
            _templates()["puddle"].instanceTo(self.puddle)
            self.puddle.setPos(self.x, .012, self.z)
            self.puddle.setH(random.uniform(0, 360))
            self.puddle.setScale(.1)
            if self.roll > 90:            # tuée au plafond : elle tombe
                self.vy = 0.0
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
            g.audio.play_var("alien_shriek", 3, .9, pos=self.center3(), pitch_range=(1.15, 1.4))
            if not gun:
                # le cri d'une araignée blessée au couteau peut attirer la bête
                g.noise(self.center3(), C.NOISE_ALIEN_SCREAM, "scream")

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        p = g.player
        self.t += dt
        self.bite_cd = max(0, self.bite_cd - dt)
        if self.state == DEAD:
            return self._update_dead(dt)
        dx, dz = p.x - self.x, p.z - self.z
        dist = math.hypot(dx, dz)
        moved = 0.0
        speed_mult = self.aggro
        if self.state == EMERGE:
            dur = .7
            if self.mode == "ceiling":
                if getattr(self, "crawl_ceiling", False):
                    self.state = CEILING           # rampe à l'envers au plafond
                    self.t = 0
                    self._skitter(.7)
                else:
                    self.state = DROP
                    self.vy = 0.0
            else:
                # sort de la grille / du cadavre en rampant
                fx, fz = self.from_dir
                self.x += fx * dt * 1.2
                self.z += fz * dt * 1.2
                self.yaw = math.degrees(math.atan2(fx, fz)) if (fx or fz) else self.yaw
                moved = 1.2 * dt
                if self.t > dur:
                    self.state = CHASE if self.aware else IDLE
            if self.t > 1.5 and self.state == EMERGE:
                self.state = CHASE if self.aware else IDLE
        elif self.state == CEILING:
            # à l'envers au plafond, elle se rapproche puis se laisse tomber
            ceil = self.level.ceiling_at(self.x, self.z)
            self.y = ceil - .12
            if dist > .1:
                step = min(dist, C.ALIEN_SPEED * .8 * speed_mult * dt * (1.6 if self.bursting else .15))
                nx, nz = self.x + dx / dist * step, self.z + dz / dist * step
                if self.level.ceiling_at(nx, nz) > 0:
                    self.x, self.z = self.level.collide(nx, nz, .22, ceil - .5, ceil, ignore=("grille",))
                moved = step
                self.yaw = math.degrees(math.atan2(dx, dz))
            self._burst_tick(dt)
            self.skitter_cd -= dt
            if self.skitter_cd <= 0:
                self.skitter_cd = random.uniform(.35, .9)
                self._skitter(.55)
            if dist < 2.1 or self.t > 12 or p.hidden:
                self.state = DROP
                self.vy = 0.0
                g.audio.play_var("alien_shriek", 3, .9, pos=self.center3(), pitch_range=(1.0, 1.25))
        elif self.state == DROP:
            # chute (se retourne en tombant) ; frappe le joueur s'il est dessous
            self.vy -= 14 * dt
            self.y = max(0.0, self.y + self.vy * dt)
            self.roll = max(0.0, self.roll - dt * 520)
            if self.y <= 0:
                self.roll = 0.0
                if dist < 1.0 and not p.hidden:
                    p.damage(C.ALIEN_DAMAGE, self.center3())
                self.state = RECOVER if self.aware else IDLE
                self.aware = True
                self.t = 0
                self._skitter(.8)
        elif self.state == IDLE:
            # tapie : repère le joueur s'il est proche et visible (ou bruyant)
            if self.t > .5:
                self.t = 0
                if dist < 11 and not p.hidden and self.level.line_of_sight(self.center3(), p.pos3):
                    if dist < 5 or not p.crouched:
                        self.alert()
            if random.random() < dt * .5:
                self.yaw += random.uniform(-60, 60)
            self._idle_sounds(dt)
        elif self.state == CHASE:
            if p.hidden:
                # le joueur caché : elles rôdent autour
                if random.random() < dt * .3:
                    self.state = IDLE
            los = dist < 12 and self.level.line_of_sight(self.center3(), p.pos3)
            speed = C.ALIEN_SPEED * speed_mult * (1.6 if self.bursting else 0.0)
            self._burst_tick(dt)
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
            # grattements de pattes : on les entend avant de les voir
            if moved > 0:
                self.skitter_cd -= dt
                if self.skitter_cd <= 0:
                    self.skitter_cd = random.uniform(.3, .75)
                    self._skitter(.6)
            self.scream_cd -= dt
            if self.scream_cd <= 0:
                self.scream_cd = random.uniform(4, 8)
                g.audio.play_var("alien_hiss", 2, .5, pos=self.center3(), occluded=not los)
            if los and dist < C.ALIEN_LEAP_DIST * (1.2 if self.aggro > 1 else 1) and dist > 1.3 and not p.hidden:
                self.state = WINDUP
                self.t = 0
                g.audio.play_var("alien_shriek", 3, 1.0, pos=self.center3(), pitch_range=(.95, 1.15))
            elif dist < 1.1 and not p.hidden and self.bite_cd <= 0:
                self.bite_cd = 1.1
                p.damage(C.ALIEN_BITE_DAMAGE, self.center3())
                g.audio.play_var("alien_click", 2, .8, pos=self.center3())
        elif self.state == WINDUP:
            # se ramasse, mandibules ouvertes, avant de bondir (fenêtre pour réagir)
            self.yaw = math.degrees(math.atan2(dx, dz))
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
                g.audio.play_var("alien_click", 2, 1.0, pos=self.center3())
            if k >= 1:
                self.y = 0
                self.state = RECOVER
                self.t = 0
                self._skitter(.7)
        elif self.state == RECOVER:
            if self.t > .8:
                self.state = CHASE
                self.t = 0
        self._animate(dt, moved)
        return True

    def _burst_tick(self, dt):
        """Mouvement saccadé : à-coups rapides entrecoupés d'arrêts."""
        self.burst -= dt
        if self.burst <= 0:
            self.bursting = not self.bursting
            self.burst = random.uniform(.18, .38) if self.bursting else random.uniform(.06, .16)
            if not self.bursting:
                self.yaw += random.uniform(-25, 25)

    def _idle_sounds(self, dt):
        """Tapie : cliquetis de mandibules, sifflements, respiration humide."""
        self.idle_sound_cd -= dt
        if self.idle_sound_cd <= 0:
            self.idle_sound_cd = random.uniform(3, 8)
            r = random.random()
            occ = self._occluded()
            if r < .45:
                self.game.audio.play_var("alien_click", 2, .45, pos=self.center3(), occluded=occ)
            elif r < .75:
                self.game.audio.play_at("alien_breath", self.center3(), .5, random.uniform(.85, 1.1), occluded=occ)
            else:
                self.game.audio.play_var("alien_hiss", 2, .35, pos=self.center3(), occluded=occ)

    def _update_dead(self, dt):
        self.dead_t += dt
        # tombe si elle est morte au plafond
        if self.y > 0:
            self.vy -= 14 * dt
            self.y = max(0.0, self.y + self.vy * dt)
            self.roll = max(0.0, self.roll - dt * 400)
        k = min(1.0, self.dead_t / .6)
        # pattes qui se recroquevillent, spasmes au début
        spasm = math.sin(self.dead_t * 40) * max(0, 1 - self.dead_t / .8) * 12
        for leg in self.legs:
            _rot(leg["hip"], -35 + 85 * k + spasm, leg["yaw"] * (1 - .35 * k), 0)
            _rot(leg["knee"], 70 + 60 * k, 0, 0)
            _rot(leg["ankle"], 30 + 50 * k, 0, 0)
        self.body.setPos(0, .2 - .14 * k, 0)
        self.abdomen.setScale(1, 1 - .15 * k, 1)
        self._place()
        if self.puddle is not None:
            ps = min(1.0, self.dead_t / 2.5) * .9 + .1
            self.puddle.setScale(ps)
        if self.dead_t > C.ALIEN_CORPSE_TIME:
            return False
        return True

    def alert(self):
        if not self.aware:
            self.aware = True
            self.state = CHASE
            self.game.audio.play_var("alien_hiss", 2, .8, pos=self.center3())

    def _open_door_ahead(self, dx, dz):
        L = self.level
        a = L.cell_at(self.x, self.z)
        b = L.cell_at(self.x + dx * .8, self.z + dz * .8)
        if a != b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
            from generator import ekey
            door = L.doors.get(ekey(a[0], a[1], b[0], b[1]))
            if door and door.target < 1:
                door.open(hold=3)

    # ------------------------------------------------------------------
    def _animate(self, dt, moved):
        t = self.game.time
        self.phase += moved * 16 + dt * (1.5 if self.state == IDLE else 0)
        ph = self.phase
        st = self.state
        crouch = 1.0 if st == WINDUP else 0.0
        # hauteur du corps : tremblements à l'arrêt, ramassé avant le bond
        tremble = math.sin(t * 47 + self.phase) * .004 * (1 if st in (IDLE, WINDUP) else .3)
        self.body.setPos(tremble, .2 - .08 * crouch + abs(math.sin(ph * .5)) * .015, 0)
        _rot(self.body, -8 * crouch + (18 if st == LEAP else 0), 0, tremble * 300)
        # abdomen qui palpite
        pulse = 1 + math.sin(t * (6 if st in (CHASE, WINDUP) else 2.5) + self.phase) * .05
        self.abdomen.setScale(pulse, pulse * .97, pulse)
        _rot(self.abdomen, -6 * crouch + math.sin(t * 1.3) * 3, math.sin(t * .9 + ph) * 4, 0)
        # mandibules
        target_jaw = 1.0 if st in (WINDUP, LEAP) else (.35 + .2 * math.sin(t * 9) if st == CHASE else .1)
        self.jaw += (target_jaw - self.jaw) * min(1, dt * 12)
        for m, sd in self.mandibles:
            _rot(m, 20 * self.jaw, sd * 28 * self.jaw, 0)
        # pattes : tétrapode en vague, saccadé, asymétrique
        for leg in self.legs:
            off = 0.0 if leg["grp"] else math.pi
            a = math.sin(ph + off + leg["k"] * .35 + leg["jit"])
            lift = max(0.0, a) if moved > 0 or st == CEILING else 0.0
            swing = a * 16 if moved > 0 or st == CEILING else math.sin(t * 3 + leg["jit"] * 5) * 2
            if st == LEAP:                     # pattes repliées pendant le bond
                hp, kp, ap = -10, 115, 60
                swing = 0
            elif st == WINDUP:
                hp, kp, ap = -48, 95, 45
            else:
                hp, kp, ap = -38 - lift * 22, 72 + lift * 10, 32
            _rot(leg["hip"], hp, leg["yaw"] + swing * (1 if leg["s"] > 0 else -1), 0)
            _rot(leg["knee"], kp, 0, 0)
            _rot(leg["ankle"], ap, 0, 0)
        self._place()

    def destroy(self):
        self.root.removeNode()
        if self.puddle is not None:
            self.puddle.removeNode()


# ============================================================================
class AlienManager:
    def __init__(self, game):
        self.game = game
        self.aliens = []
        self.decals = []
        self.spawn_timer = random.uniform(*C.ALIEN_SPAWN_INTERVAL) * .6
        self.grace = 35.0
        self.rest = 0.0              # répit après la mort d'un groupe
        self._had_group = False
        self.kill_positions = []     # là où le joueur a « tué » des créatures (révélation)
        self.suspended = False       # révélation : elles n'existent plus pendant quelques secondes
        self.bonus_cap = 0           # après la révélation : plus nombreuses

    @property
    def alive(self):
        return [a for a in self.aliens if a.state != DEAD]

    def max_count(self):
        # jamais plus de 3 en même temps, même en mode horreur ou avec le disque dur
        return (C.ALIEN_MAX_HORROR if self.game.horror.active else C.ALIEN_MAX) + self.bonus_cap

    def hit_spheres(self):
        if self.suspended:
            return []
        return [(a, a.center3(), Alien.RADIUS) for a in self.aliens if a.state != DEAD]

    def hear(self, pos, radius, kind):
        for a in self.aliens:
            if a.state == IDLE and math.hypot(pos[0] - a.x, pos[2] - a.z) < radius * .8:
                a.alert()

    def set_visible(self, on):
        """Révélation : les araignées (et leurs cadavres) disparaissent / réapparaissent."""
        for a in self.aliens:
            if on:
                a.root.show()
                if a.puddle is not None:
                    a.puddle.show()
            else:
                a.root.hide()
                if a.puddle is not None:
                    a.puddle.hide()

    def on_death(self, alien):
        self.kill_positions.append((alien.x, alien.z))
        if not self.alive:
            self.rest = C.ALIEN_REST_AFTER_GROUP
            self._had_group = False

    def can_spawn(self):
        return self.rest <= 0 and len(self.alive) < self.max_count()

    # ------------------------------------------------------------------
    def spawn_near_player(self, n, aware=True):
        g = self.game
        p = g.player
        L = g.level
        if p is None or not self.can_spawn():
            return 0
        n = min(n, C.ALIEN_GROUP[1] + self.bonus_cap, self.max_count() - len(self.alive))
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
                # la passerelle verrouillée (sans courant) : elles y resteraient enfermées
                if r is not None and r.type == "command" and g.power is not None and not g.power.on:
                    continue
                # on évite d'apparaître sous les yeux du joueur
                seen = d < 14 and L.line_of_sight((x, 1.0, z), p.pos3)
                cands.append((d + random.uniform(0, 6) + (15 if seen else 0), x, z, kind))
        cands.sort()
        spawned = 0
        # un groupe vient d'un même endroit (ou de deux points proches)
        for _, x, z, kind in cands[:max(2, n)]:
            if spawned >= n or len(self.alive) >= self.max_count():
                break
            self.spawn(x, z, kind, aware)
            spawned += 1
        if spawned:
            self._had_group = True
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
        a = Alien(self, x, z, kind, aware or g.has_hdd(), from_dir)
        self.aliens.append(a)
        a._skitter(.8)
        return a

    def burst_from_corpse(self, pos, n):
        n = min(n, max(0, C.ALIEN_MAX - len(self.alive)))
        for k in range(max(1, n) if len(self.alive) < C.ALIEN_MAX else 0):
            a = random.uniform(0, 2 * math.pi)
            al = Alien(self, pos[0], pos[2], "corpse", True, (math.cos(a), math.sin(a)))
            self.aliens.append(al)
        self.game.audio.play_var("alien_shriek", 3, 1.0, pos=pos, pitch_range=(.85, 1.0))

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        if self.suspended:
            return
        for a in list(self.aliens):
            if not a.update(dt):
                a.destroy()
                self.aliens.remove(a)
        self.rest = max(0.0, self.rest - dt)
        if self.grace > 0:
            self.grace -= dt
            return
        # apparitions régulières (embuscades), rares
        mult = C.ALIEN_HDD_MULT if g.has_hdd() else 1.0
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = random.uniform(*C.ALIEN_SPAWN_INTERVAL) * mult
            if self.can_spawn():
                n = random.randint(*C.ALIEN_GROUP)
                self.spawn_near_player(n, aware=random.random() < .6 or g.has_hdd())

    def nearest_hidden(self):
        """(distance, alien) de l'araignée vivante la plus proche que le joueur ne voit pas."""
        p = self.game.player
        best = None
        for a in self.alive:
            d = math.hypot(a.x - p.x, a.z - p.z)
            if d < 13 and (best is None or d < best[0]):
                if not self.game.level.line_of_sight(a.center3(), p.pos3):
                    best = (d, a)
        return best

    def destroy(self):
        for a in self.aliens:
            a.destroy()
        self.aliens = []
