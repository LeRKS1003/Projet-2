# -*- coding: utf-8 -*-
"""
space.py — L'espace autour du vaisseau : skybox noire, milliers d'étoiles de tailles
et de luminosités variées, 2 ou 3 planètes lointaines (dont une avec des anneaux),
une nébuleuse discrète. L'ensemble suit la caméra (il est « à l'infini ») et tourne
très lentement pour donner l'impression que le vaisseau dérive.
"""
import math

import numpy as np
from panda3d.core import (ColorBlendAttrib, DirectionalLight as PandaDirectionalLight,
                          TransparencyAttrib, Vec4)
from ursina import Entity, camera

import config as C
from geometry import MeshBuilder, bruit_fractal, texture_depuis_tableau, Textures


def _direction_aleatoire(rng):
    z = rng.uniform(-1, 1)
    t = rng.uniform(0, 2 * math.pi)
    r = math.sqrt(1 - z * z)
    return (r * math.cos(t), z, r * math.sin(t))


class Espace(Entity):
    def __init__(self, seed=1):
        super().__init__(name="espace", eternal=True)
        self.rng = np.random.default_rng(seed)
        # tout l'espace est hors éclairage et hors brouillard, dessiné en arrière-plan
        self.setLightOff(10)
        self.setFogOff(10)
        self.setDepthWrite(False)
        self.setBin("background", 0)
        self.pivot = Entity(parent=self)
        self._nebuleuse()
        self._etoiles()
        self._planetes()

    # --------------------------------------------------------------
    def _nebuleuse(self):
        l, h = 1024, 512
        b1 = bruit_fractal(l, h, self.rng, base=3, octaves=6, ratio=2)
        b2 = bruit_fractal(l, h, self.rng, base=2, octaves=5, ratio=2)
        lat = np.linspace(-1, 1, h)[:, None]
        # bande diagonale douce (comme une voie lactée)
        bande = np.exp(-((lat - 0.25 * np.sin(np.linspace(0, 2 * np.pi, l))[None, :]) ** 2) / 0.12)
        a = np.clip((b1 - 0.45) * 2.2, 0, 1) ** 2 * (0.25 + bande * 0.75)
        img = np.zeros((h, l, 4))
        c1 = np.array([0.35, 0.12, 0.55])
        c2 = np.array([0.05, 0.35, 0.45])
        img[..., :3] = c1 * b2[..., None] + c2 * (1 - b2[..., None])
        img[..., 3] = a * 0.55
        tex = texture_depuis_tableau(img, "nebuleuse")
        mb = MeshBuilder()
        mb.sphere((0, 0, 0), 1500, (1, 1, 1, 1), anneaux=16, segments=32, interieur=True)
        e = Entity(parent=self.pivot)
        np_ = e.attachNewNode(mb.construire("nebuleuse"))
        np_.setTexture(tex, 1)
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
        np_.setBin("background", 1)
        np_.setDepthWrite(False)

    def _etoiles(self):
        mb = MeshBuilder()
        R = 1400.0
        rng = self.rng
        for _ in range(C.NB_ETOILES):
            d = _direction_aleatoire(rng)
            # taille : beaucoup de petites étoiles, quelques grosses
            t = 1.2 + rng.pareto(3.0) * 1.6
            t = min(t, 9.0)
            lum = min(1.0, 0.25 + rng.random() * 0.6 + t / 12)
            teinte = rng.choice([(1, 1, 1), (0.75, 0.85, 1.0), (1.0, 0.9, 0.75), (1.0, 0.75, 0.7)], p=[0.55, 0.2, 0.15, 0.1])
            col = (teinte[0] * lum, teinte[1] * lum, teinte[2] * lum, 1.0)
            n = (-d[0], -d[1], -d[2])
            haut = (0, 1, 0) if abs(d[1]) < 0.95 else (1, 0, 0)
            # vecteur haut orthogonal à la normale
            dot = sum(a * b for a, b in zip(haut, n))
            haut = tuple(h - dot * c for h, c in zip(haut, n))
            lh = math.sqrt(sum(c * c for c in haut))
            haut = tuple(c / lh for c in haut)
            mb.rect((d[0] * R, d[1] * R, d[2] * R), n, haut, t * 2.2, t * 2.2, col,
                    uvs=((0, 0), (1, 0), (1, 1), (0, 1)))
        e = Entity(parent=self.pivot)
        np_ = e.attachNewNode(mb.construire("etoiles"))
        np_.setTexture(Textures().get("halo"), 1)
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
        np_.setBin("background", 2)
        np_.setDepthWrite(False)

    def _texture_planete(self, genre):
        l, h = 512, 256
        rng = self.rng
        lat = np.linspace(0, 1, h)[:, None] * np.ones((1, l))
        b = bruit_fractal(l, h, rng, base=3, octaves=6, ratio=2)
        if genre == "gazeuse":
            bandes = np.sin((lat + (b - 0.5) * 0.12) * rng.uniform(18, 34))
            c1 = rng.uniform(0.4, 0.9, 3)
            c2 = c1 * rng.uniform(0.4, 0.8, 3)
            v = (bandes * 0.5 + 0.5)[..., None]
            img = c1 * v + c2 * (1 - v)
        elif genre == "glace":
            v = (b ** 1.5)[..., None]
            img = np.array([0.75, 0.85, 0.95]) * (0.6 + 0.4 * v)
        else:  # rocheuse / désertique
            v = b[..., None]
            c1 = np.array([0.5, 0.3, 0.2]) * rng.uniform(0.7, 1.2)
            c2 = np.array([0.2, 0.18, 0.16])
            img = np.where(v > 0.5, c1 * (0.7 + v * 0.5), c2 * (0.6 + v))
        return texture_depuis_tableau(np.clip(img, 0, 1), "planete")

    def _planetes(self):
        rng = self.rng
        # « soleil » lointain qui éclaire uniquement les planètes
        soleil = PandaDirectionalLight("soleil")
        soleil.setColor(Vec4(1.3, 1.2, 1.1, 1))
        snp = self.pivot.attachNewNode(soleil)
        snp.setHpr(rng.uniform(0, 360), rng.uniform(-30, 30), 0)
        genres = ["gazeuse", "rocheuse", "glace"]
        rng.shuffle(genres)
        anneaux = int(rng.integers(0, C.NB_PLANETES))
        for k in range(C.NB_PLANETES):
            d = _direction_aleatoire(rng)
            d = (d[0], d[1] * 0.5, d[2])
            nd = math.sqrt(sum(c * c for c in d))
            d = tuple(c / nd for c in d)
            dist = 1100.0
            rayon = float(rng.uniform(40, 160) if k == 0 else rng.uniform(15, 60))
            mb = MeshBuilder()
            mb.sphere((0, 0, 0), rayon, (1, 1, 1, 1), anneaux=24, segments=40)
            e = Entity(parent=self.pivot, position=(d[0] * dist, d[1] * dist, d[2] * dist),
                       rotation=(float(rng.uniform(-25, 25)), float(rng.uniform(0, 360)), float(rng.uniform(-20, 20))))
            np_ = e.attachNewNode(mb.construire("planete"))
            np_.setTexture(self._texture_planete(genres[k % 3]), 1)
            np_.setLightOff(20)
            np_.setLight(snp, 21)
            np_.setBin("background", 3)
            np_.setDepthWrite(True)
            if k == anneaux:
                self._anneaux(e, rayon)

    def _anneaux(self, parent, rayon):
        l = 512
        r = np.linspace(0, 1, l)
        b = np.sin(r * 90) * 0.3 + np.sin(r * 37) * 0.3 + 0.4
        a = np.clip(b, 0, 1) * np.clip((r - 0.05) * 8, 0, 1) * np.clip((1 - r) * 8, 0, 1)
        img = np.zeros((4, l, 4))
        img[..., 0] = 0.8
        img[..., 1] = 0.72
        img[..., 2] = 0.6
        img[..., 3] = a[None, :] * 0.8
        tex = texture_depuis_tableau(img, "anneaux", repeter=False)
        mb = MeshBuilder()
        r0, r1 = rayon * 1.3, rayon * 2.3
        seg = 64
        for i in range(seg):
            t0, t1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            p = [(math.cos(t0) * r0, 0, math.sin(t0) * r0), (math.cos(t0) * r1, 0, math.sin(t0) * r1),
                 (math.cos(t1) * r1, 0, math.sin(t1) * r1), (math.cos(t1) * r0, 0, math.sin(t1) * r0)]
            uvs = ((0, 0.5), (1, 0.5), (1, 0.5), (0, 0.5))
            mb.quad_auto(*p, (0, 1, 0), (1, 1, 1, 1), uvs)
        e = Entity(parent=parent)
        np_ = e.attachNewNode(mb.construire("anneaux"))
        np_.setTexture(tex, 1)
        np_.setTwoSided(True)
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setBin("background", 4)
        np_.setDepthWrite(False)

    # --------------------------------------------------------------
    def tick(self, dt):
        # l'espace suit la caméra : il paraît infiniment loin
        self.position = camera.world_position
        self.pivot.rotation_y += C.VITESSE_DERIVE * dt
        self.pivot.rotation_x = math.sin(self.pivot.rotation_y * 0.013) * 4
