# -*- coding: utf-8 -*-
"""
lighting.py — Éclairage, ambiance visuelle et gestion du courant.

  * éclairage PAR PIXEL (shader automatique de Panda3D, activé dans main.py).
    IMPORTANT : Ursina 8 donne par défaut à chaque entité un shader NON
    éclairé (« unlit_with_fog_shader ») qui affiche tout en pleine lumière ;
    main.py le désactive (Entity.default_shader = None) et audit_unlit()
    vérifie au chargement qu'aucune entité du décor n'est restée non éclairée ;
  * lumière ambiante quasi nulle + brouillard noir exponentiel (réglé
    directement sur le nœud Fog de Panda3D : Ursina 8 ignore une densité
    numérique) ;
  * lampe torche réaliste (classe Flashlight) : vrai Spotlight fixé sous
    l'arme, orientation lissée, atténuation physique, masque « cookie »,
    ombres portées dynamiques, cône volumétrique + poussière, couleur en
    kelvins, comportement lié à la batterie ;
  * luminaires (Fixture) : tube émissif visible + vraie PointLight prise
    dans un pool limité (MAX_POINT_LIGHTS) ; seuls les luminaires des salles
    proches du joueur EN SUIVANT LES PASSAGES reçoivent une lumière (pas de
    fuite de lumière à travers les murs, et 60 FPS tenus) ;
  * PowerManager : enregistre toutes les lumières et tous les matériaux
    émissifs (écrans, consoles, réacteur) par salle, avec les états
    COUPÉ / REDÉMARRAGE / ALLUMÉ / CASSÉ / CLIGNOTANT, la propagation du
    courant depuis la salle des machines et les coupures temporaires ;
  * vision nocturne : éclairage vert amplifié, sources éblouissantes ;
  * soleil directionnel pour la phase TPS uniquement.
"""
import math
import random
from collections import deque

from panda3d.core import (AmbientLight as PAmbient, PointLight as PPoint, Spotlight as PSpot,
                          DirectionalLight as PDir, PerspectiveLens, Vec4, Vec3 as PVec3, BitMask32,
                          TextureStage, Texture as PTexture, TexGenAttrib, ColorBlendAttrib, Quat, Fog,
                          ShaderAttrib, LightAttrib)
from ursina import camera, color, scene, Entity, Mesh, destroy
from ursina import application

import config as C
import textures
from geometry import MeshBuilder

# bit du masque de caméra utilisé par les caméras d'ombre : les effets
# translucides (cône, poussière, halos) s'en cachent pour ne pas projeter d'ombre.
SHADOW_MASK = BitMask32.bit(3)

# états d'une lumière alimentée par le réseau du vaisseau
COUPE, REDEMARRAGE, ALLUME, CASSE, CLIGNOTANT = "COUPÉ", "REDÉMARRAGE", "ALLUMÉ", "CASSÉ", "CLIGNOTANT"


def additive(np_, bin_sort=5):
    """Mélange additif (lueurs, flammes, halos) sans écriture de profondeur."""
    np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                        ColorBlendAttrib.OOne))
    np_.setDepthWrite(False)
    np_.setBin('fixed', bin_sort)
    np_.setLightOff(2)
    np_.hide(SHADOW_MASK)
    np_.setPythonTag("emissive", True)


def mark_emissive(np_, lit_off=True):
    """
    Déclare un nœud comme volontairement émissif (néon, écran, voyant, œil...).
    Il ignore alors l'éclairage ; audit_unlit() ne le signale pas.
    """
    np_.setPythonTag("emissive", True)
    if lit_off:
        np_.setLightOff(1)
    return np_


def set_emissive_level(np_, v, off_scale=(.2, .2, .22)):
    """
    Allume (v > 0 : émissif, intensité v) ou éteint (v = 0 : surface ordinaire,
    éclairée par la lampe) un matériau émissif.
    """
    if v < .03:
        np_.clearLight()
        np_.setColorScale(off_scale[0], off_scale[1], off_scale[2], 1)
    else:
        np_.setLightOff(1)
        np_.setColorScale(v, v, v, 1)


def set_fog(col, density):
    """Brouillard exponentiel (nœud Fog de Panda3D posé par Ursina sur la scène)."""
    f = scene.fog
    f.setMode(Fog.MExponential)
    f.setColor(col[0], col[1], col[2])
    f.setExpDensity(density)


def audit_unlit(root, label="décor"):
    """
    Vérification au chargement : signale en console tout nœud du décor qui
    porte un shader non éclairé (shader explicite au lieu du shader
    automatique) ou qui ignore l'éclairage sans avoir été déclaré émissif.
    """
    shaders, unlit = [], []
    n = 0
    for np_ in root.findAllMatches("**"):
        if np_.hasNetPythonTag("audit_skip"):
            continue            # extérieur du vaisseau (phase de pilotage uniquement)
        n += 1
        st = np_.getState()
        sa = st.getAttrib(ShaderAttrib)
        if sa is not None and sa.getShader() is not None and not sa.autoShader():
            # seuls comptent les nœuds qui dessinent quelque chose (pas les entités techniques d'Ursina)
            if np_.node().isGeomNode() or not np_.findAllMatches("**/+GeomNode").isEmpty():
                shaders.append(np_.getName() or repr(np_))
        la = st.getAttrib(LightAttrib)
        if la is not None and la.hasAllOff() and not np_.hasNetPythonTag("emissive"):
            unlit.append(np_.getName())
    print(f"[éclairage] vérification du {label} : {n} nœuds, {len(shaders)} shader(s) non éclairé(s), "
          f"{len(unlit)} entité(s) non éclairée(s) non déclarée(s)")
    for name in shaders[:12]:
        print("   ! shader non éclairé :", name)
    for name in unlit[:12]:
        print("   ! entité restée en unlit :", name)
    return shaders, unlit


def _hash01(a, b):
    """Pseudo-aléatoire déterministe dans [0, 1[ (clignotements reproductibles)."""
    h = math.sin(a * 12.9898 + b * 78.233) * 43758.5453
    return h - math.floor(h)


class Fixture:
    """Un luminaire du vaisseau (ou une source de lumière ponctuelle indépendante)."""
    __slots__ = ("pos", "col", "radius", "mode", "entity", "base_col", "phase", "brightness",
                 "intensity", "rate", "room", "dead_until", "active", "powered", "kind", "cell", "delay",
                 "pstate", "start_dur", "tube_on", "tube_q", "power")

    def __init__(self, pos, col, radius=C.LIGHT_RANGE, mode="steady", entity=None, intensity=1.0, room=None,
                 powered=True, kind="lamp"):
        self.pos = pos                  # (x, y, z) monde
        self.col = col                  # (r, g, b)
        self.radius = radius
        self.mode = mode                # steady / flicker / broken / pulse / alarm / red / reactor / star / nav
        self.entity = entity            # tube émissif (Entity) ou None
        self.base_col = col
        self.phase = random.uniform(0, 100)
        self.rate = random.uniform(.6, 1.6)
        self.brightness = 1.0
        self.intensity = intensity
        self.room = room
        self.dead_until = 0.0
        self.active = True
        self.powered = powered          # dépend du réseau électrique du vaisseau ?
        self.kind = kind                # lamp / console / alarm / reactor / star / nav / emergency
        self.cell = None                # case de la grille (calculée par PowerManager.finalize)
        self.delay = 0.0                # retard d'allumage depuis la salle des machines
        self.pstate = ALLUME            # ALLUMÉ, CASSÉ ou CLIGNOTANT une fois le courant rétabli
        self.start_dur = 1.0            # durée du clignotement de démarrage
        self.tube_on = None             # état courant du tube (None = jamais réglé)
        self.tube_q = -1
        self.power = 1.0                # facteur d'alimentation courant (0..1)

    def compute(self, t, horror, power=1.0):
        """Luminosité courante (0..~1.5) selon le mode, le courant et le mode horreur."""
        m = self.mode
        self.power = power
        if not self.active or power <= 0:
            self.brightness = 0.0
            return 0.0
        if m in ("steady", "red", "star", "emergency"):
            b = 1.0
        elif m == "reactor":
            b = 0.85 + 0.15 * math.sin(t * 2.1 + self.phase)
        elif m == "pulse":
            b = 0.55 + 0.45 * math.sin(t * 1.4 * self.rate + self.phase)
        elif m == "nav":
            # feu blanc à éclats de la navette
            b = 1.0 if ((t + self.phase) % 1.2) < .12 else 0.0
        elif m == "flicker":
            # néon fatigué : allumé la plupart du temps, coupures brèves irrégulières
            x = math.sin(t * 13.0 * self.rate + self.phase) + math.sin(t * 31.7 + self.phase * 2.3)
            b = 0.08 if x > 1.55 else (0.6 if x > 1.3 else 1.0)
        elif m == "broken":
            # néon cassé : éteint, avec des sursauts
            x = math.sin(t * 7.3 * self.rate + self.phase) * math.sin(t * 2.9 + self.phase)
            b = 1.0 if x > 0.82 else 0.0
        elif m == "alarm":
            b = 0.0
        else:
            b = 1.0
        if horror > 0.01 and self.powered:
            if m == "alarm":
                # gyrophare : pulsation rouge rapide
                b = horror * (0.5 + 0.5 * math.sin(t * 9.0 + self.phase)) ** 2 * 1.6
            elif self.kind != "reactor":
                # toutes les lumières clignotent fortement
                strobe = 1.0 if math.sin(t * 17.0 + self.phase * 3) > -0.2 else 0.15
                b *= (1 - horror) + horror * strobe * 0.8
        b *= power
        self.brightness = b
        return b

    def current_color(self, horror):
        r, g, b = self.base_col
        if self.mode == "alarm":
            return (1.0, 0.05, 0.02)
        if horror > 0.01 and self.powered and self.kind not in ("reactor", "nav"):
            # glisse vers le rouge
            k = min(1.0, horror * 1.2)
            r = r * (1 - k) + 1.0 * k
            g = g * (1 - k) + 0.08 * k
            b = b * (1 - k) + 0.05 * k
        return (r, g, b)


# ============================================================================
class PowerManager:
    """
    Réseau électrique du vaisseau, côté rendu : toutes les lumières et tous
    les matériaux émissifs y sont enregistrés par salle.

    État global : "off" (courant coupé), "on" (rétabli, éventuellement en
    cours de propagation), "outage" (coupure temporaire). Chaque lumière a
    son état : COUPÉ, REDÉMARRAGE (clignotement de démarrage), ALLUMÉ,
    CASSÉ (reste éteinte) ou CLIGNOTANT (grésille en permanence).
    La logique de jeu (fusibles, levier, séquence, coupures) est dans power.py.
    """

    def __init__(self, lights):
        self.lights = lights
        self.level = None
        self.state = "off" if C.POWER_START_OFF else "on"
        self.t_on = -1e6                # instant où la propagation a démarré
        self.delay_scale = 1.0          # 1 = redémarrage complet, < 1 = retour après une coupure
        self.reactor_level = 0.0 if C.POWER_START_OFF else 1.0
        self.outage_t0 = 0.0
        self.global_level = 0.0 if C.POWER_START_OFF else 1.0
        self.max_delay = 0.0
        self.emissives = []             # [nœud, retard, phase, type, dernière valeur, case]
        self.relay_events = []          # (retard, position) : bruits de relais pendant la propagation
        self.reach = None               # case -> distance (en cases) depuis le joueur
        self._reach_cell = None
        self._reach_timer = 0.0
        self._settle = True             # une passe complète sur tous les tubes à faire
        self.now = 0.0

    # ------------------------------------------------------------------
    def register_emissive(self, np_, kind, x, z):
        """kind : screen / emissive / holo / reactor / battery (voyant qui clignote sur batterie)."""
        self.emissives.append([np_, 0.0, random.uniform(0, 10), kind, None, (x, z)])

    def finalize(self, level, engine_room, rng):
        """
        Calcule le retard d'allumage de chaque lumière (distance en suivant
        les passages depuis la salle des machines, salle par salle) et tire,
        avec la seed, les lumières qui resteront cassées ou clignotantes.
        """
        self.level = level
        L = level
        dist = {}
        q = deque()
        if engine_room is not None:
            for c in engine_room.cells():
                dist[c] = 0
                q.append(c)
        while q:
            c = q.popleft()
            for ni, nj, st in L.links.get(c, ()):
                n = (ni, nj)
                if n not in dist:
                    dist[n] = dist[c] + 1
                    q.append(n)
        maxd = max(dist.values()) if dist else 1
        room_min = {}
        for (i, j), d in dist.items():
            r = L.room_of[i][j]
            if r >= 0:
                room_min[r] = min(room_min.get(r, 1e9), d)

        cell_of = self.cell_of

        def delay_of(c):
            i, j = c
            r = L.room_of[i][j] if L.inside(i, j) else -1
            d = room_min.get(r) if r >= 0 else dist.get(c, maxd)
            if d is None:
                d = maxd
            return d * C.POWER_SPREAD_STEP

        relays = {}
        for fx in self.lights.fixtures:
            fx.cell = cell_of(fx.pos[0], fx.pos[2])
            fx.delay = delay_of(fx.cell)
            fx.start_dur = rng.uniform(*C.POWER_STARTUP_TIME)
            if fx.powered and fx.kind in ("lamp", "alarm"):
                i, j = fx.cell
                r = L.room_of[i][j] if L.inside(i, j) else -1
                key = ("room", r) if r >= 0 else ("cell", i // 3, j // 3)
                if key not in relays:
                    relays[key] = (fx.delay, fx.pos)
        self.relay_events = sorted(relays.values(), key=lambda e: e[0])
        for e in self.emissives:
            e[5] = cell_of(*e[5])
            e[1] = delay_of(e[5])
        self.max_delay = maxd * C.POWER_SPREAD_STEP
        # 20 à 30 % des lampes restent cassées (éteintes ou clignotantes)
        lamps = [fx for fx in self.lights.fixtures if fx.powered and fx.kind == "lamp"]
        rng.shuffle(lamps)
        n_broken = int(round(len(lamps) * C.POWER_BROKEN_RATIO))
        for k, fx in enumerate(lamps):
            if k < n_broken:
                if rng.random() < C.POWER_BROKEN_FLICKER:
                    fx.pstate = CLIGNOTANT
                    fx.mode = rng.choice(["flicker", "flicker", "broken"])
                else:
                    fx.pstate = CASSE
            else:
                fx.pstate = ALLUME
        self._settle = True
        print(f"[courant] {len(self.lights.fixtures)} lumières, {len(self.emissives)} matériaux émissifs, "
              f"{n_broken} lampes cassées, propagation {self.max_delay:.1f} s")

    def cell_of(self, x, z):
        """Case ouverte la plus proche d'un point (un luminaire mural peut déborder sur la cloison)."""
        L = self.level
        i, j = L.cell_at(x, z)
        if (i, j) in L.links:
            return (i, j)
        best = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                c = (i + di, j + dj)
                if c in L.links:
                    cx, cz = L.cell_center(*c)
                    d = (cx - x) ** 2 + (cz - z) ** 2
                    if best is None or d < best[0]:
                        best = (d, c)
        return best[1] if best else (i, j)

    # ------------------------------------------------------------------
    # changements d'état
    # ------------------------------------------------------------------
    def switch_on(self, now, instant=False, delay_scale=1.0):
        self.state = "on"
        self.t_on = now - (1e5 if instant else 0.0)
        self.delay_scale = delay_scale
        if instant:
            self.reactor_level = 1.0
            self.global_level = 1.0
        self._settle = True

    def switch_off(self):
        self.state = "off"
        self.reactor_level = 0.0
        self._settle = True

    def start_outage(self, now):
        self.state = "outage"
        self.outage_t0 = now
        self._settle = True

    def end_outage(self, now):
        self.switch_on(now, delay_scale=.3)

    # ------------------------------------------------------------------
    @staticmethod
    def _startup(u, phase):
        """Démarrage d'un néon : plusieurs flashs de plus en plus longs avant de rester allumé."""
        if u > .88:
            return 1.0
        r = _hash01(int(u * 16), phase)
        if r < .18 + u * .6:
            return 1.0
        if r < .3 + u * .5:
            return .35
        return 0.0

    def _zone(self, now, delay, phase, start_dur, pstate=ALLUME):
        st = self.state
        if st == "off" or pstate == CASSE:
            return 0.0
        if st == "outage":
            u = now - self.outage_t0
            if u < .35:     # sursaut juste avant le noir
                return 1.0 if _hash01(int(u * 30), phase) > .45 else .12
            return 0.0
        t0 = self.t_on + delay * self.delay_scale
        if now < t0:
            return 0.0
        u = (now - t0) / start_dur
        if u >= 1:
            return 1.0
        return self._startup(u, phase)

    def factor(self, fx, now):
        """Alimentation d'une lumière (0..1)."""
        if not fx.powered:
            return 1.0
        if fx.kind == "reactor":
            return self.reactor_level
        return self._zone(now, fx.delay, fx.phase, fx.start_dur, fx.pstate)

    def fixture_state(self, fx, now):
        """État lisible d'une lumière : COUPÉ / REDÉMARRAGE / ALLUMÉ / CASSÉ / CLIGNOTANT."""
        if not fx.powered:
            return ALLUME
        if self.state != "on":
            return COUPE
        if fx.pstate == CASSE:
            return CASSE
        t0 = self.t_on + fx.delay * self.delay_scale
        if now < t0:
            return COUPE
        if now < t0 + fx.start_dur:
            return REDEMARRAGE
        return fx.pstate

    def transitioning(self, now):
        """Vrai tant que des lumières changent d'état (propagation, coupure)."""
        if self.state == "outage":
            return True
        if self.state == "on" and now < self.t_on + self.max_delay * self.delay_scale + 2.0:
            return True
        return 0.0 < self.reactor_level < 1.0

    # ------------------------------------------------------------------
    def update(self, now, dt, cam_pos, fps_mode):
        self.now = now
        # niveau global (ambiante, brouillard) : suit la propagation
        if self.state == "on":
            span = self.max_delay * self.delay_scale + 1.0
            target = max(0.0, min(1.0, (now - self.t_on) / span))
        else:
            target = 0.0
        self.global_level += (target - self.global_level) * min(1.0, dt * 3.0)
        # salles atteignables par la lumière depuis le joueur
        if fps_mode and self.level is not None:
            cell = self.level.cell_at(cam_pos[0], cam_pos[2])
            self._reach_timer -= dt
            if cell != self._reach_cell or self._reach_timer <= 0:
                self._reach_timer = .3
                self._reach_cell = cell
                self.reach = self._bfs_reach(cell)
        else:
            self.reach = None
        self._update_emissives(now)

    def _bfs_reach(self, start):
        """Cases à moins de LIGHT_REACH_CELLS du joueur en passant par les ouvertures (portes ouvertes...)."""
        from generator import ekey
        L = self.level
        if start not in L.links:
            return None
        R = C.LIGHT_REACH_CELLS
        out = {start: 0}
        q = deque([start])
        while q:
            c = q.popleft()
            d = out[c]
            if d >= R:
                continue
            for ni, nj, st in L.links[c]:
                if st == "door":
                    if L.doors[ekey(c[0], c[1], ni, nj)].open_amount < .08:
                        continue
                elif st == "grille":
                    if not L.grilles[ekey(c[0], c[1], ni, nj)].opened:
                        continue
                n = (ni, nj)
                if n not in out:
                    out[n] = d + 1
                    q.append(n)
        return out

    def _update_emissives(self, now):
        """Écrans, consoles, hologramme, réacteur, voyants de batterie."""
        for e in self.emissives:
            np_, delay, phase, kind, last, _cell = e
            if kind == "battery":
                v = 1.0 if ((now * .7 + phase) % 1.0) < .5 else .3
            elif kind == "reactor":
                v = self.reactor_level * (.8 + .2 * math.sin(now * 2.3 + phase)) if self.reactor_level > 0 else 0.0
            else:
                v = self._zone(now, delay, phase, .9)
            q = round(v * 20) / 20
            if q != last:
                e[4] = q
                if kind == "holo":
                    if q < .03:
                        np_.hide()
                    else:
                        np_.show()
                        np_.setColorScale(1, 1, 1, q)
                else:
                    set_emissive_level(np_, q, (.16, .16, .18) if kind == "screen" else (.3, .3, .32))


# ============================================================================
class Flashlight:
    """Lampe torche : spot + cookie + ombres + cône volumétrique + poussière."""

    def __init__(self, world_root):
        q = C.quality()
        self.q = q
        r = render_np()
        # le « rig » suit la caméra ; son orientation est lissée (retard naturel)
        self.rig = r.attachNewNode("flashlight_rig")
        self.spot = PSpot("flashlight")
        lens = PerspectiveLens()
        lens.setFov(C.FLASHLIGHT_FOV)
        lens.setNearFar(0.15, C.FLASHLIGHT_RANGE)
        self.spot.setLens(lens)
        self.spot.setExponent(C.FLASHLIGHT_EXPONENT)
        self.spot.setAttenuation(PVec3(*C.FLASHLIGHT_ATTENUATION))
        self.spot.setColor(Vec4(0, 0, 0, 1))
        self.spot.setCameraMask(SHADOW_MASK)
        if q["shadows"]:
            # ombres portées : la lampe rend une carte de profondeur à chaque image
            self.spot.setShadowCaster(True, q["shadow_size"], q["shadow_size"])
        self.np = self.rig.attachNewNode(self.spot)
        r.setLight(self.np)
        # masque projeté (« cookie ») : anneaux LED et bords doux
        self.cookie_root = None
        if q["cookie"] and world_root is not None:
            tex = textures.get('flash_cookie')._texture
            tex.setWrapU(PTexture.WM_border_color)
            tex.setWrapV(PTexture.WM_border_color)
            tex.setBorderColor(Vec4(1, 1, 1, 1))
            self.cookie_stage = TextureStage("flash_cookie")
            self.cookie_stage.setMode(TextureStage.MModulate)
            self.cookie_stage.setSort(40)
            world_root.projectTexture(self.cookie_stage, tex, self.np)
            # décalage des coordonnées projetées : (0, 0) = actif ; hors de [0, 1] = bord blanc = neutre
            world_root.setTexOffset(self.cookie_stage, .0001, 0)
            self.cookie_root = world_root
            self._cookie_on = True
        # cône volumétrique : trois coques emboîtées, plus denses au centre
        self.cone = None
        if q["volumetric"]:
            L = 9.0
            mb = MeshBuilder()
            half = math.radians(C.FLASHLIGHT_FOV / 2)
            for k, (rk, a) in enumerate(((1.0, .006), (.62, .01), (.32, .016))):
                R = math.tan(half) * L * rk
                seg = 18
                for s in range(seg):
                    a0 = 2 * math.pi * s / seg
                    a1 = 2 * math.pi * (s + 1) / seg
                    p0 = (math.cos(a0) * R, math.sin(a0) * R, L)
                    p1 = (math.cos(a1) * R, math.sin(a1) * R, L)
                    b0 = mb.count
                    for p, al in (((0, 0, .05), a), (p0, 0.0), (p1, 0.0)):
                        mb.v.extend(p)
                        mb.n.extend((0, 0, 1))
                        mb.c.extend((1, 1, 1, al))
                        mb.t.extend((0, 0))
                    mb.i.extend((b0, b0 + 1, b0 + 2))
                    mb.count += 3
            self.cone = mb.build(name="flash_cone", tangents=False)
            self.cone.reparentTo(self.rig)
            self.cone.setTwoSided(True)
            additive(self.cone, 4)
        # poussière qui flotte dans le faisceau (sprites ponctuels)
        self.dust = None
        self.dust_n = q["dust"]
        if self.dust_n:
            rnd = random.Random(7)
            self.dust_pts = [[rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(.6, 7.5), rnd.uniform(0, 6.28)]
                             for _ in range(self.dust_n)]
            self.dust_mesh = Mesh(vertices=[(0, 0, 0)] * self.dust_n, colors=[color.clear] * self.dust_n,
                                  mode='point', thickness=.018, render_points_in_3d=True, static=False)
            self.dust = Entity(model=self.dust_mesh, name="flash_dust")
            self.dust.reparentTo(self.rig)
            self.dust.setTexture(textures.get('dust')._texture)
            self.dust.setTexGen(TextureStage.getDefault(), TexGenAttrib.MPointSprite)
            additive(self.dust, 6)
            self._dust_tick = 0
        self.cur_quat = None
        self.level = 0.0            # intensité effective 0..1 (lissée)
        self.flick = 1.0
        self.flick_timer = 0.0
        self.tap_timer = 0.0
        self.scare_mult = 1.0       # imposé par le screamer (clignote puis s'éteint)

    # ------------------------------------------------------------------
    def tap(self):
        """Taper sur la lampe : répit de quelques secondes quand elle faiblit."""
        self.tap_timer = C.FLASHLIGHT_TAP_TIME

    def battery_factor(self, battery, dt):
        """Intensité relative selon la batterie (baisse, puis scintillement irrégulier)."""
        if self.tap_timer > 0:
            return max(.6, min(1.0, battery / C.FLASHLIGHT_LOW)) if battery > 0 else .55
        if battery <= 0:
            return 0.0
        if battery > C.FLASHLIGHT_LOW:
            return 1.0
        if battery > C.FLASHLIGHT_FLICKER:
            return .45 + .55 * (battery - C.FLASHLIGHT_FLICKER) / (C.FLASHLIGHT_LOW - C.FLASHLIGHT_FLICKER)
        # sous le seuil : coupures et sursauts aléatoires
        self.flick_timer -= dt
        if self.flick_timer <= 0:
            r = random.random()
            if r < .25:
                self.flick, self.flick_timer = .03, random.uniform(.04, .25)
            elif r < .45:
                self.flick, self.flick_timer = .2, random.uniform(.03, .12)
            else:
                self.flick, self.flick_timer = random.uniform(.35, .5), random.uniform(.1, .6)
        return self.flick

    @property
    def flickering(self):
        return self.tap_timer <= 0 and 0 < self.level < .55

    def update(self, dt, on, battery, nightvision, fog_density):
        self.tap_timer = max(0.0, self.tap_timer - dt)
        # position : sous et à droite de l'œil (lampe fixée sur l'arme)
        cam = camera
        ox, oy, oz = C.FLASHLIGHT_OFFSET
        p = cam.world_position + cam.right * ox + cam.up * oy + cam.forward * oz
        self.rig.setPos(p.x, p.y, p.z)
        # orientation : suit la vue avec un léger retard
        target = cam.getQuat(render_np())
        if self.cur_quat is None:
            self.cur_quat = Quat(target)
        k = 1 - math.exp(-C.FLASHLIGHT_LAG * dt)
        a, b = self.cur_quat, target
        if a.dot(b) < 0:
            b = Quat(-b[0], -b[1], -b[2], -b[3])
        qn = Quat(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k,
                  a[3] + (b[3] - a[3]) * k)
        qn.normalize()
        self.cur_quat = qn
        self.rig.setQuat(qn)
        # intensité
        lit = (on or self.tap_timer > 0)
        target_level = self.battery_factor(battery, dt) if lit else 0.0
        # montée / descente douce (sauf coupures du scintillement)
        self.level += (target_level - self.level) * min(1, dt * 25)
        lv = self.level * self.scare_mult
        # lampe éteinte : le cookie ne doit plus rien modifier dans le décor
        if self.cookie_root is not None and (lv > .02) != self._cookie_on:
            self._cookie_on = lv > .02
            self.cookie_root.setTexOffset(self.cookie_stage, .0001 if self._cookie_on else 5.0, 0)
        kk = C.FLASHLIGHT_INTENSITY * lv * (.4 if nightvision else 1.0)
        c = C.FLASHLIGHT_COLOR
        self.spot.setColor(Vec4(c[0] * kk, c[1] * kk, c[2] * kk, 1))
        vol = lv * (1.0 + fog_density * 8)
        if self.cone is not None:
            self.cone.enabled = lv > .02
            self.cone.setColorScale(c[0] * vol, c[1] * vol, c[2] * vol, 1)
        if self.dust is not None:
            self.dust.enabled = lv > .02
            self._dust_tick += 1
            if self.dust.enabled and self._dust_tick % 2 == 0:
                self._update_dust(dt * 2, vol)

    def _update_dust(self, dt, vol):
        tan = math.tan(math.radians(C.FLASHLIGHT_FOV / 2))
        verts, cols = [], []
        t = time_now()
        for pnt in self.dust_pts:
            pnt[0] += math.sin(t * .3 + pnt[3]) * dt * .05
            pnt[1] += (math.cos(t * .23 + pnt[3] * 1.7) * .04 - .01) * dt
            pnt[2] += math.sin(t * .17 + pnt[3] * .5) * dt * .08
            if abs(pnt[0]) > 1 or abs(pnt[1]) > 1:
                pnt[0], pnt[1] = random.uniform(-.8, .8), random.uniform(-.8, .8)
            z = pnt[2]
            R = tan * z
            verts.append((pnt[0] * R, pnt[1] * R, z))
            rr = math.sqrt(pnt[0] ** 2 + pnt[1] ** 2)
            a = max(0.0, 1 - rr) ** 1.5 * max(0.0, 1 - z / 8) * min(1, z) * .55 * vol
            cols.append(color.rgba(1, 1, 1, min(1, a)))
        self.dust_mesh.vertices = verts
        self.dust_mesh.colors = cols
        self.dust_mesh.generate()

    def destroy(self):
        r = render_np()
        if self.cookie_root is not None:
            try:
                self.cookie_root.clearProjectTexture(self.cookie_stage)
            except Exception:
                pass
        r.clearLight(self.np)
        if self.dust is not None:
            destroy(self.dust)
        self.rig.removeNode()


_CLOCK = [0.0]      # horloge partagée (animée par LightManager.update)


def time_now():
    return _CLOCK[0]


class LightManager:
    def __init__(self, root, postfx=None):
        self.root = root
        self.postfx = postfx
        self.fixtures = []
        self.time = 0.0
        self.horror = 0.0
        self.nightvision = False
        self.flashlight_on = False
        self.battery = C.BATTERY_MAX
        self.mode = "tps"
        self._assign_timer = 0.0
        self.extra_flash = 0.0      # flash bref (tir, étincelle) 0..1
        self.flash_col = (1, .8, .5)
        self.flash_strength = C.MUZZLE_LIGHT_INTENSITY
        self.flash_decay = 14.0
        self.flash_is_muzzle = False
        self.flash_pos = None
        self._visible = []
        self.fog_density = 0.0
        self._fog_applied = None
        self.glitch = 0.0           # révélation : les lumières sautent au rythme du glitch
        self.power = PowerManager(self)

        # lumière ambiante (quasi nulle en FPS)
        self.amb_node = PAmbient("ambient")
        self.amb_node.setColor(Vec4(.05, .05, .06, 1))
        self.amb = render_np().attachNewNode(self.amb_node)
        render_np().setLight(self.amb)

        # pool de lumières ponctuelles ; les premières projettent des ombres (qualité Haute)
        self.pool = []
        n_shadow = min(2, C.quality().get("point_shadows", 0)) if C.quality()["shadows"] else 0
        self.n_shadow = n_shadow
        for k in range(C.MAX_POINT_LIGHTS):
            pl = PPoint(f"pool_{k}")
            pl.setColor(Vec4(0, 0, 0, 1))
            q = 9.0 / (C.LIGHT_RANGE ** 2)
            pl.setAttenuation(PVec3(1, 0.05, q))
            if k < n_shadow:
                pl.setShadowCaster(True, 256, 256)
                pl.setCameraMask(SHADOW_MASK)
            np_ = render_np().attachNewNode(pl)
            render_np().setLight(np_)
            self.pool.append([np_, pl, None])

        # lumière des flashs brefs (bouche du pistolet, étincelles)
        self.flash_node = PPoint("muzzle")
        self.flash_node.setColor(Vec4(0, 0, 0, 1))
        self.flash_node.setAttenuation(PVec3(*C.MUZZLE_LIGHT_ATTENUATION))
        self.flash_np = render_np().attachNewNode(self.flash_node)
        render_np().setLight(self.flash_np)

        # lampe torche
        self.flashlight = Flashlight(root)

        # soleil (phase TPS uniquement : jamais à l'intérieur du vaisseau)
        self.sun_node = PDir("sun")
        self.sun_node.setColor(Vec4(1.1, 1.05, 0.95, 1))
        self.sun_np = render_np().attachNewNode(self.sun_node)
        self.sun_on = False

    # ------------------------------------------------------------------
    def add_fixture(self, fx):
        self.fixtures.append(fx)
        if self.power.level is not None:
            # lumière ajoutée après la construction (ex. feux de la navette posée)
            fx.cell = self.power.cell_of(fx.pos[0], fx.pos[2])
            self.power._settle = True
        return fx

    def set_sun(self, direction, on=True):
        self.sun_np.lookAt(PVec3(direction[0], direction[1], direction[2]))
        if on and not self.sun_on:
            render_np().setLight(self.sun_np)
        elif not on and self.sun_on:
            render_np().clearLight(self.sun_np)
        self.sun_on = on

    def _set_fog(self, col, density):
        key = (tuple(round(c, 3) for c in col), round(density, 5))
        if key != self._fog_applied:
            self._fog_applied = key
            set_fog(col, density)
        self.fog_density = density

    def set_mode(self, mode):
        """'tps' : espace (soleil, peu de brouillard) ; 'fps' : intérieur plongé dans le noir."""
        self.mode = mode
        if mode == "tps":
            self.amb_node.setColor(Vec4(.06, .065, .08, 1))
            self._set_fog((0, 0, 0), C.FOG_DENSITY_TPS)
            camera.clip_plane_far = 3000
        elif mode == "fps":
            self.set_sun((0, -1, 0), False)      # aucun soleil à l'intérieur
            self._apply_ambient()
            camera.clip_plane_far = 260
        elif mode == "menu":
            self.amb_node.setColor(Vec4(.05, .05, .07, 1))
            self._set_fog((0, 0, 0), C.FOG_DENSITY_TPS)
            camera.clip_plane_far = 3000

    def _apply_ambient(self):
        k = self.power.global_level
        if self.nightvision:
            a = C.AMBIENT_NIGHTVISION
            self.amb_node.setColor(Vec4(a[0], a[1], a[2], 1))
            dens = (C.FOG_DENSITY_POWER_OFF + (C.FOG_DENSITY_POWER_ON - C.FOG_DENSITY_POWER_OFF) * k) * .45
            self._set_fog((.02, .06, .02), dens)
            return
        a0, a1 = C.AMBIENT_POWER_OFF, C.AMBIENT_POWER_ON
        a = [a0[i] + (a1[i] - a0[i]) * k for i in range(3)]
        # teinte rouge du mode horreur seulement si les lumières du vaisseau sont alimentées
        a[0] += .03 * self.horror * k
        self.amb_node.setColor(Vec4(a[0], a[1], a[2], 1))
        dens = C.FOG_DENSITY_POWER_OFF + (C.FOG_DENSITY_POWER_ON - C.FOG_DENSITY_POWER_OFF) * k
        self._set_fog(C.FOG_COLOR_FPS, dens)

    def set_nightvision(self, on):
        self.nightvision = on
        if self.mode == "fps":
            self._apply_ambient()

    def muzzle_flash(self, pos):
        self.flash(pos, (1, .8, .5), C.MUZZLE_LIGHT_INTENSITY, 14.0)
        self.flash_is_muzzle = True

    def flash(self, pos, col, strength, decay=14.0):
        """Flash lumineux bref (étincelle, tir) : réutilise une seule PointLight."""
        if self.extra_flash * self.flash_strength > strength:
            return          # un flash plus fort est déjà en cours
        self.extra_flash = 1.0
        self.flash_col = col
        self.flash_strength = strength
        self.flash_decay = decay
        self.flash_is_muzzle = False
        self.flash_np.setPos(pos[0], pos[1], pos[2])

    def tap_flashlight(self):
        self.flashlight.tap()

    @property
    def flashlight_level(self):
        return self.flashlight.level

    # ------------------------------------------------------------------
    def update(self, dt, cam_pos, horror=0.0):
        self.time += dt
        self.horror = horror
        t = self.time
        _CLOCK[0] = t
        fps = self.mode == "fps"
        pm = self.power
        pm.update(t, dt, cam_pos, fps)
        # flash bref (tir, étincelle)
        if self.extra_flash > 0:
            self.extra_flash = max(0.0, self.extra_flash - dt * self.flash_decay)
            f = self.extra_flash * self.flash_strength
            c = self.flash_col
            self.flash_node.setColor(Vec4(f * c[0], f * c[1], f * c[2], 1))
        # lampe torche
        self.flashlight.update(dt, self.flashlight_on and fps, self.battery, self.nightvision,
                               self.fog_density if fps else 0)
        if fps:
            self._apply_ambient()

        # choix des luminaires qui reçoivent une vraie lumière : proches, alimentés
        # et atteignables depuis le joueur en passant par les ouvertures
        reach = pm.reach
        self._assign_timer -= dt
        cx, cy, cz = cam_pos
        if self._assign_timer <= 0:
            self._assign_timer = 0.2
            cands = []
            for fx in self.fixtures:
                if reach is not None and fx.cell not in reach:
                    continue
                if fx.mode == "alarm" and horror < .01:
                    continue
                if pm.factor(fx, t) <= 0:
                    continue
                dx, dy, dz = fx.pos[0] - cx, fx.pos[1] - cy, fx.pos[2] - cz
                d2 = dx * dx + dy * dy + dz * dz
                if d2 < (fx.radius + 22) ** 2:
                    cands.append((d2 / (fx.intensity + .01), fx))
            cands.sort(key=lambda c: c[0])
            chosen = [c[1] for c in cands[:len(self.pool)]]
            # les meilleures lumières vont dans les emplacements qui projettent des ombres
            for k in range(self.n_shadow):
                slot = self.pool[k]
                fx = chosen[k] if k < len(chosen) else None
                if slot[2] is not fx:
                    self._assign(slot, fx)
            rest = chosen[self.n_shadow:]
            regular = self.pool[self.n_shadow:]
            # garde les assignations existantes pour éviter les sauts
            current = {id(p[2]) for p in regular if p[2] is not None and p[2] in rest}
            free = [p for p in regular if p[2] is None or p[2] not in rest]
            for fx in rest:
                if id(fx) in current:
                    continue
                if not free:
                    break
                self._assign(free.pop(), fx)
            for slot in free:
                self._assign(slot, None)
            self._visible = [fx for d, fx in cands[:40]]

        nv_boost = 2.6 if self.nightvision else 1.0
        # luminosité + tubes émissifs : tous les luminaires pendant une transition
        # (propagation, coupure), sinon seulement les plus proches
        full = pm.transitioning(t) or pm._settle
        pm._settle = pm.transitioning(t)
        lst = self.fixtures if full else self._visible
        for fx in lst:
            b = fx.compute(t, horror, pm.factor(fx, t))
            if fx.entity is not None:
                self._update_tube(fx, b, horror)
        if not full:
            for slot in self.pool:
                fx = slot[2]
                if fx is not None and fx not in self._visible:
                    fx.compute(t, horror, pm.factor(fx, t))
        for slot in self.pool:
            fx = slot[2]
            if fx is None:
                continue
            b = fx.brightness * fx.intensity * nv_boost * (C.LIGHT_INTENSITY if fx.powered else 1.0)
            if self.glitch > 0 and random.random() < self.glitch * .5:
                b *= random.uniform(0, .25)
            r, g, bb = fx.current_color(horror)
            slot[1].setColor(Vec4(r * b, g * b, bb * b, 1))
        if self.postfx is not None:
            self._update_viewmodel_lights(cam_pos)

    def _assign(self, slot, fx):
        slot[2] = fx
        if fx is None:
            slot[1].setColor(Vec4(0, 0, 0, 1))
            return
        slot[0].setPos(fx.pos[0], fx.pos[1], fx.pos[2])
        q = 9.0 / (fx.radius ** 2)
        slot[1].setAttenuation(PVec3(1, 0.05, q))

    def _update_tube(self, fx, b, horror):
        """Tube émissif : lumineux quand alimenté, simple plastique sombre (éclairé par la lampe) sinon."""
        e = fx.entity
        k = min(1.0, b)
        if k < .03:
            if fx.tube_on is not False:
                fx.tube_on = False
                fx.tube_q = -1
                e.clearLight()
                # éteint : simple plastique (verre rouge pour un gyrophare), éclairé par la lampe
                e.color = color.rgb(.3, .05, .05) if fx.mode == "alarm" else color.rgb(.3, .3, .32)
            return
        if fx.tube_on is not True:
            fx.tube_on = True
            e.setLightOff(1)
        r, g, bb = fx.current_color(horror)
        q = (int(k * 20), int(r * 10), int(g * 10), int(bb * 10))
        if q != fx.tube_q:
            fx.tube_q = q
            e.color = color.rgb(min(1, r * k * 1.1), min(1, g * k * 1.1), min(1, bb * k * 1.1))

    def _update_viewmodel_lights(self, cam_pos):
        """
        L'arme vit dans sa propre couche (postfx.vm_root) : on y reproduit
        l'éclairage du décor autour du joueur (ambiante, luminaire le plus
        influent, lampe torche, flash de bouche).
        """
        pf = self.postfx
        a = self.amb_node.getColor()
        # l'arme reste à peine lisible dans le noir : ambiante faible + reflet de l'ambiante du décor
        pf.vm_amb.setColor(Vec4(a[0] * 1.8 + .025, a[1] * 1.8 + .025, a[2] * 1.8 + .03, 1))
        # luminaire le plus influent -> lumière directionnelle clé
        best, best_c, best_dir = 0.0, None, None
        cx, cy, cz = cam_pos
        for np_, pl, fx in self.pool:
            if fx is None:
                continue
            col = pl.getColor()
            dx, dy, dz = fx.pos[0] - cx, fx.pos[1] - cy, fx.pos[2] - cz
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            q = 9.0 / (fx.radius ** 2)
            att = 1.0 / (1 + .05 * d + q * d * d)
            lum = (col[0] + col[1] + col[2]) * att
            if lum > best:
                best, best_c, best_dir = lum, (col[0] * att, col[1] * att, col[2] * att), (dx, dy, dz)
        if best_c is not None:
            pf.vm_key.setColor(Vec4(min(2, best_c[0]), min(2, best_c[1]), min(2, best_c[2]), 1))
            rel = camera.getRelativeVector(render_np(), PVec3(*best_dir))
            pf.vm_key_np.lookAt(-rel)
        else:
            pf.vm_key.setColor(Vec4(0, 0, 0, 1))
        k = self.flashlight.level * self.flashlight.scare_mult * (1.3 if not self.nightvision else .5)
        c = C.FLASHLIGHT_COLOR
        pf.vm_lamp.setColor(Vec4(c[0] * k, c[1] * k, c[2] * k, 1))
        f = self.extra_flash * 3.0 if self.flash_is_muzzle else 0.0
        pf.vm_flash.setColor(Vec4(f, f * .8, f * .5, 1))

    def glare_amount(self, cam_pos, cam_forward):
        """Éblouissement en vision nocturne : luminaire allumé proche dans l'axe du regard."""
        best = 0.0
        cx, cy, cz = cam_pos
        fx_, fy_, fz_ = cam_forward
        for fx in self._visible:
            if fx.brightness < 0.3:
                continue
            dx, dy, dz = fx.pos[0] - cx, fx.pos[1] - cy, fx.pos[2] - cz
            d = math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-4
            if d > 14:
                continue
            dot = (dx * fx_ + dy * fy_ + dz * fz_) / d
            if dot > 0.8:
                v = (dot - 0.8) / 0.2 * (1 - d / 14) * fx.brightness * fx.intensity
                best = max(best, v)
        return min(1.0, best)

    def destroy(self):
        r = render_np()
        for p in self.pool:
            r.clearLight(p[0])
            p[0].removeNode()
        for n in (self.amb, self.flash_np, self.sun_np):
            r.clearLight(n)
            n.removeNode()
        self.flashlight.destroy()
        self.fixtures.clear()
        self.power.emissives.clear()
        if self.postfx is not None:
            self.postfx.vm_key.setColor(Vec4(0, 0, 0, 1))
            self.postfx.vm_lamp.setColor(Vec4(0, 0, 0, 1))
            self.postfx.vm_flash.setColor(Vec4(0, 0, 0, 1))


def render_np():
    """NodePath 'render' de Panda3D (scène 3D)."""
    return application.base.render
