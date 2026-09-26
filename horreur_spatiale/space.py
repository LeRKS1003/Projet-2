# -*- coding: utf-8 -*-
"""
space.py — Skybox spatiale : milliers d'étoiles, nébuleuse discrète,
2 ou 3 planètes lointaines (dont une avec des anneaux), soleil lointain.

Le ciel suit la position de la caméra (pas sa rotation) : il paraît donc
infiniment loin. Il est dessiné dans le bin 'background' sans écriture de
profondeur : toute la géométrie du jeu passe devant, et on le voit à
travers les hublots en phase FPS.
"""
import math
import random

import numpy as np
from panda3d.core import (DirectionalLight as PDirLight, AmbientLight as PAmbLight,
                          TransparencyAttrib, Vec4)
from ursina import Entity, Vec3, camera, color, Mesh, destroy

import textures
from geometry import MeshBuilder


def _random_dir(rng, min_elev=-0.6, max_elev=0.6):
    az = rng.uniform(0, 2 * math.pi)
    el = rng.uniform(min_elev, max_elev)
    return Vec3(math.cos(el) * math.cos(az), math.sin(el), math.cos(el) * math.sin(az))


class Space:
    SKY_RADIUS = 180.0
    PLANET_DIST = 140.0

    def __init__(self, seed):
        rng = random.Random(seed * 7 + 3)
        nrng = np.random.default_rng(seed)
        self.root = Entity(name='space_root')
        self.root.setLightOff(1)
        self.root.setFogOff(1)
        self.root.setPythonTag("emissive", True)      # le ciel est lumineux par lui-même
        self.root.setBin('background', 0)
        self.root.setDepthWrite(False)
        self.root.setDepthTest(False)

        # --- dôme étoilé ---------------------------------------------------
        self.dome = Entity(parent=self.root, model='sky_dome', texture=textures.stars_texture(seed),
                           scale=self.SKY_RADIUS, rotation_y=rng.uniform(0, 360))
        self.dome.setBin('background', 1)

        # --- soleil lointain ---------------------------------------------
        self.sun_dir = _random_dir(rng, 0.15, 0.55).normalized()
        sun_pos = self.sun_dir * (self.SKY_RADIUS * .9)
        self.sun = Entity(parent=self.root, model='quad', texture=textures.get('glow'),
                          color=color.rgb(1, .92, .8), scale=26, position=sun_pos, billboard=True)
        self.sun_core = Entity(parent=self.root, model='quad', texture=textures.get('glow'),
                               color=color.rgb(1, 1, 1), scale=7, position=sun_pos * .99, billboard=True)
        for e in (self.sun, self.sun_core):
            e.setTransparency(TransparencyAttrib.MAlpha)
            e.setBin('background', 2)

        # lumière du soleil réservée aux planètes
        dl = PDirLight('planet_sun')
        dl.setColor(Vec4(1.3, 1.25, 1.15, 1))
        self.planet_light = self.root.attachNewNode(dl)
        self.planet_light.lookAt(-self.sun_dir)
        al = PAmbLight('planet_amb')
        al.setColor(Vec4(.04, .04, .06, 1))
        self.planet_amb = self.root.attachNewNode(al)

        # --- planètes -----------------------------------------------------
        self.planets = []
        count = rng.choice([2, 3, 3])
        kinds = ['gas', 'rock', 'ice']
        rng.shuffle(kinds)
        dirs = []
        ringed_index = 0
        sort = 3
        planet_specs = []
        for i in range(count):
            for _ in range(40):
                d = _random_dir(rng, -.45, .5).normalized()
                if all(d.dot(o) < .8 for o in dirs) and d.dot(self.sun_dir) < .85:
                    break
            dirs.append(d)
            size = rng.uniform(14, 26) if i == ringed_index else rng.uniform(5, 13)
            dist = self.PLANET_DIST * (1 + i * .08)
            planet_specs.append((dist, d, size, kinds[i], i == ringed_index))
        # les plus lointaines d'abord
        planet_specs.sort(key=lambda s: -s[0])
        for dist, d, size, kind, ringed in planet_specs:
            pos = d * dist
            tex = textures.planet_texture(nrng, kind)
            if ringed:
                tilt = (rng.uniform(-35, 35), rng.uniform(0, 180), rng.uniform(-25, 25))
                back, front = self._make_rings(nrng, pos, size, tilt)
                back.setBin('background', sort)
                sort += 1
            p = Entity(parent=self.root, model='sphere', texture=tex, position=pos, scale=size,
                       rotation=(rng.uniform(-20, 20), rng.uniform(0, 360), rng.uniform(-20, 20)))
            p.setLightOff(2)
            p.setLight(self.planet_light, 3)
            p.setLight(self.planet_amb, 3)
            p.setBin('background', sort)
            sort += 1
            # atmosphère : halo légèrement plus grand
            halo = Entity(parent=self.root, model='quad', texture=textures.get('glow'), billboard=True,
                          position=pos * 1.001, scale=size * 1.9,
                          color=color.rgba(.5, .7, 1, .18) if kind != 'rock' else color.rgba(1, .7, .5, .12))
            halo.setTransparency(TransparencyAttrib.MAlpha)
            halo.setBin('background', sort - 2 if ringed else sort - 1)
            if ringed:
                front.setBin('background', sort)
                sort += 1
            self.planets.append(p)

        # --- poussière spatiale (sensation de vitesse en TPS) ---------------
        self.dust_enabled = False
        self.dust_n = 180
        self.dust_box = 70.0
        self.dust_pts = [Vec3(rng.uniform(0, 1), rng.uniform(0, 1), rng.uniform(0, 1)) * self.dust_box
                         for _ in range(self.dust_n)]
        self.dust_mesh = Mesh(vertices=[Vec3(0, 0, 0)] * self.dust_n, mode='point', thickness=2,
                              colors=[color.rgba(.8, .8, .9, .7)] * self.dust_n, static=False)
        self.dust = Entity(model=self.dust_mesh, name='dust')
        self.dust.setLightOff(1)
        self.dust.enabled = False

    # ------------------------------------------------------------------
    def _make_rings(self, nrng, center, size, tilt):
        """Anneaux en deux moitiés (derrière / devant la planète) pour un tri correct."""
        tex = textures.ring_texture(nrng)
        pivot = Entity(parent=self.root, position=center, rotation=tilt)
        halves = []
        # on calcule quelle moitié est la plus éloignée de l'observateur (origine)
        mb_back, mb_front = MeshBuilder(), MeshBuilder()
        seg = 64
        r_out = size * 1.15
        for k in range(seg):
            a0 = 2 * math.pi * k / seg
            a1 = 2 * math.pi * (k + 1) / seg
            p0 = (math.cos(a0) * r_out, 0, math.sin(a0) * r_out)
            p1 = (math.cos(a1) * r_out, 0, math.sin(a1) * r_out)
            mid_local = Vec3((p0[0] + p1[0]) / 2, 0, (p0[2] + p1[2]) / 2)
            mid_world = self.root.getRelativePoint(pivot, mid_local)
            far = Vec3(mid_world).length() > Vec3(center).length()
            mb = mb_back if far else mb_front
            # triangle depuis le centre : UV = coordonnées planaires
            b = mb.count
            for p in ((0, 0, 0), p0, p1):
                mb.v.extend(p)
                mb.n.extend((0, 1, 0))
                mb.c.extend((1, 1, 1, 1))
                mb.t.extend((.5 + p[0] / (2 * r_out), .5 + p[2] / (2 * r_out)))
            mb.i.extend((b, b + 1, b + 2))
            mb.count += 3
        for mb in (mb_back, mb_front):
            e = mb.build(parent=pivot, texture=tex)
            e.double_sided = True
            e.setTransparency(TransparencyAttrib.MAlpha)
            e.setLightOff(2)
            halves.append(e)
        return halves

    # ------------------------------------------------------------------
    def set_dust(self, on):
        self.dust_enabled = on
        self.dust.enabled = on

    def update(self, dt):
        cp = camera.world_position
        self.root.position = cp
        if self.dust_enabled:
            b = self.dust_box
            h = b / 2
            verts = []
            for p in self.dust_pts:
                verts.append(Vec3(((p.x - cp.x) % b) - h + cp.x,
                                  ((p.y - cp.y) % b) - h + cp.y,
                                  ((p.z - cp.z) % b) - h + cp.z))
            self.dust_mesh.vertices = verts
            self.dust_mesh.generate()

    def destroy(self):
        destroy(self.dust)
        destroy(self.root)
