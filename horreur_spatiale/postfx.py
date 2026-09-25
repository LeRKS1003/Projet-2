# -*- coding: utf-8 -*-
"""
postfx.py — Post-traitement et couche « viewmodel ».

  * CommonFilters de Panda3D : bloom (néons, réacteurs, flash de tir),
    occlusion ambiante (SSAO, qualité Haute), correction gamma ;
    chaque effet est activé selon config.QUALITY.
  * Couche séparée pour l'arme tenue en main : un second graphe de scène
    (vm_root) rendu par sa propre caméra, avec son propre FOV, APRÈS le
    décor et avec le tampon de profondeur vidé : l'arme ne rentre jamais
    dans les murs et garde toujours la même échelle. Si les filtres sont
    actifs, cette couche est dessinée dans le même tampon que la scène, elle
    profite donc aussi du bloom (flash de tir, points tritium).

Note : dans Panda3D 1.10, combiner SSAO + bloom + gamma dans CommonFilters
donne une image délavée. En qualité Haute (SSAO + bloom), la correction
gamma est donc remplacée par un léger réglage de l'éclairage ambiant.
"""
from panda3d.core import Camera, NodePath, PerspectiveLens, AmbientLight, DirectionalLight, PointLight, Vec4
from panda3d.core import Vec3 as PVec3
from ursina import application, window

import config as C


class PostFX:
    def __init__(self):
        base = application.base
        self.q = C.quality()
        self.filters = None
        self.gamma_active = False
        self.ssao_active = False
        self.bloom_active = False
        wants = self.q["bloom"] or self.q["ssao"] or self.q["gamma"] != 1.0
        if wants:
            try:
                from direct.filter.CommonFilters import CommonFilters
                self.filters = CommonFilters(base.win, base.cam)
                if self.q["bloom"]:
                    self.bloom_active = bool(self.filters.setBloom(
                        blend=(.3, .4, .3, 0), mintrigger=C.BLOOM_THRESHOLD, maxtrigger=1.0, desat=.35,
                        intensity=C.BLOOM_INTENSITY, size="medium"))
                if self.q["ssao"]:
                    self.ssao_active = bool(self.filters.setAmbientOcclusion(
                        numsamples=16, radius=0.05, amount=1.6, strength=0.01, falloff=0.000002))
                # voir la note en tête de fichier
                if self.q["gamma"] != 1.0 and not (self.ssao_active and self.bloom_active):
                    self.gamma_active = bool(self.filters.setGammaAdjust(self.q["gamma"]))
            except Exception as exc:  # carte graphique trop ancienne, pilote...
                print("[postfx] filtres indisponibles :", exc)
                self.filters = None
        print(f"[postfx] qualité {C.QUALITY} : bloom={self.bloom_active} ssao={self.ssao_active} "
              f"gamma={self.gamma_active}")
        self._make_viewmodel_layer()

    # ------------------------------------------------------------------
    def _make_viewmodel_layer(self):
        base = application.base
        self.vm_root = NodePath("viewmodel_render")
        self.vm_root.setShaderAuto()
        cam = Camera("viewmodel_cam")
        self.vm_lens = PerspectiveLens()
        self.vm_lens.setFov(C.VIEWMODEL_FOV)
        self.vm_lens.setNearFar(0.01, 20)
        self.vm_lens.setAspectRatio(window.aspect_ratio)
        cam.setLens(self.vm_lens)
        self.vm_cam = self.vm_root.attachNewNode(cam)
        target = base.win
        if self.filters is not None and self.filters.manager.buffers:
            target = self.filters.manager.buffers[0]   # même tampon que la scène -> bloom sur l'arme
        self.vm_region = target.makeDisplayRegion()
        self.vm_region.setSort(10)                     # après le décor (0), avant l'interface (20)
        self.vm_region.setClearDepthActive(True)
        self.vm_region.setCamera(self.vm_cam)
        # éclairage propre à la couche de l'arme (piloté par lighting.py)
        self.vm_amb = AmbientLight("vm_ambient")
        self.vm_amb.setColor(Vec4(.08, .08, .09, 1))
        self.vm_amb_np = self.vm_root.attachNewNode(self.vm_amb)
        self.vm_key = DirectionalLight("vm_key")            # lumière du décor la plus proche
        self.vm_key.setColor(Vec4(0, 0, 0, 1))
        self.vm_key_np = self.vm_root.attachNewNode(self.vm_key)
        self.vm_lamp = PointLight("vm_lamp")                # reflet de la lampe torche
        self.vm_lamp.setAttenuation(PVec3(1, 0, 2))
        self.vm_lamp.setColor(Vec4(0, 0, 0, 1))
        self.vm_lamp_np = self.vm_root.attachNewNode(self.vm_lamp)
        self.vm_lamp_np.setPos(-.05, .12, .1)
        self.vm_flash = PointLight("vm_flash")              # flash de bouche
        self.vm_flash.setAttenuation(PVec3(1, 0, 6))
        self.vm_flash.setColor(Vec4(0, 0, 0, 1))
        self.vm_flash_np = self.vm_root.attachNewNode(self.vm_flash)
        self.vm_flash_np.setPos(.1, -.05, .7)
        for n in (self.vm_amb_np, self.vm_key_np, self.vm_lamp_np, self.vm_flash_np):
            self.vm_root.setLight(n)
        self.vm_root.hide()

    def show_viewmodel(self, on):
        if on:
            self.vm_root.show()
        else:
            self.vm_root.hide()

    def update(self):
        # suit le rapport largeur/hauteur de la fenêtre (redimensionnement)
        ar = window.aspect_ratio
        if abs(self.vm_lens.getAspectRatio() - ar) > 1e-3:
            self.vm_lens.setAspectRatio(ar)
