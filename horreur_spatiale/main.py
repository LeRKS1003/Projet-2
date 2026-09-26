# -*- coding: utf-8 -*-
"""
main.py — DÉRIVE : point d'entrée et gestionnaire d'états du jeu.

États : menu -> chargement -> tps (pilotage) -> landing (atterrissage
scripté) -> fps (exploration / survie) -> escape (décollage) -> victoire.
Plus : pause (superposée), game over. L'inventaire est un sous-état de la
phase FPS qui NE met PAS le jeu en pause.

Lancement :  python main.py
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C  # noqa: E402

from panda3d.core import loadPrcFileData  # noqa: E402

loadPrcFileData("", "sync-video %d" % (1 if C.VSYNC else 0))
loadPrcFileData("", "texture-anisotropic-degree 4")

from ursina import (Ursina, Entity, Text, camera, color, mouse, window, application, invoke,  # noqa: E402
                    destroy, time as utime, Vec3)

app = Ursina(title=C.TITLE, development_mode=True, editor_ui_enabled=False, borderless=False,
             fullscreen=C.FULLSCREEN, size=C.WINDOW_SIZE, vsync=C.VSYNC)
window.color = color.black
# IMPORTANT : Ursina 8 donne par défaut à chaque entité un shader NON ÉCLAIRÉ
# (unlit_with_fog_shader) qui affiche tout en pleine lumière, quel que soit
# l'éclairage. Sans shader propre, les entités héritent du shader automatique
# de Panda3D (éclairage par pixel, ci-dessous). Sans effet sous Ursina 7.
Entity.default_shader = None
if hasattr(window, "editor_ui"):
    window.editor_ui.enabled = False     # cache le bouton X et les compteurs d'Ursina
application.base.render.setShaderAuto()     # éclairage par pixel (lampe torche, néons)
camera.clip_plane_near = 0.05

from controller import InputManager  # noqa: E402
from audio import AudioSystem  # noqa: E402
from hud import HUD, MenuScreen, TitleScreen  # noqa: E402
from generator import ShipLayout, Blocker, ROOM, CORR  # noqa: E402
from rooms import LevelBuilder  # noqa: E402
from lighting import LightManager  # noqa: E402
from space import Space  # noqa: E402
from exterior import ExteriorShip  # noqa: E402
from shuttle import Shuttle, ShuttleInteract  # noqa: E402
from player import Player  # noqa: E402
from weapons import Weapons  # noqa: E402
from inventory import Inventory, InventoryUI  # noqa: E402
from creature import Creature, AIDirector  # noqa: E402
from aliens import AlienManager  # noqa: E402
from horror import HorrorManager  # noqa: E402
from postfx import PostFX  # noqa: E402
import story  # noqa: E402
from document_ui import DocumentLog, DocumentReader, JournalUI, ControlsOverlay  # noqa: E402
from hallucinations import Hallucinations, Revelation  # noqa: E402
from power import PowerSystem  # noqa: E402
from screamer import Screamer  # noqa: E402
from lighting import audit_unlit  # noqa: E402


class _NoInput:
    """Entrée neutre (quand l'inventaire est ouvert, l'arme ne réagit pas)."""

    def pressed(self, a):
        return False

    def held(self, a):
        return False


class _MaskedInput:
    """Relais d'entrée qui masque certaines actions (ex. « recharger » utilisé pour taper la lampe)."""

    def __init__(self, inp, masked):
        self.inp = inp
        self.masked = masked

    def pressed(self, a):
        return a not in self.masked and self.inp.pressed(a)

    def held(self, a):
        return a not in self.masked and self.inp.held(a)

    def __getattr__(self, name):
        return getattr(self.inp, name)


# (intensité du sursaut, texte avec courant, texte sans courant)
ROOM_EVENTS = {
    "engine": (.7, "Le réacteur gronde. Quelque chose a griffé les parois.",
               "Le réacteur est à l'arrêt. Le tableau électrique principal doit être ici."),
    "medbay": (.5, "L'infirmerie... Les néons grésillent.", "L'infirmerie. Des tables d'opération dans le noir..."),
    "command": (.4, "La passerelle. Le disque dur doit être sur une console.",
                "La passerelle. Le disque dur doit être sur une console."),
    "mess": (.3, None, None),
}


class Game(Entity):
    def __init__(self):
        super().__init__(ignore_paused=True)
        self.inp = InputManager()
        self.audio = AudioSystem()
        self.hud = HUD(self)
        self.postfx = PostFX()          # bloom / SSAO / gamma + couche de l'arme
        self.state = "menu"
        self.paused = False
        self.time = 0.0
        self.shake_amount = 0.0
        self.screen = None
        self.seed = None
        self.ui_consumed = False
        self._null = _NoInput()
        # objets de la partie
        self.world_root = None
        self.level = self.builder = self.lights = self.space = self.exterior = None
        self.shuttle = self.player = self.weapons = self.inventory = self.inventory_ui = None
        self.creature = self.aliens = self.director = self.horror = None
        self.power = self.screamer = None
        self.docs = self.hallu = self.revelation = None
        self.stats = {"kills": 0, "start": 0.0, "docs": 0}
        self.current_room = None
        # interfaces persistantes : lecture des documents, journal, commandes (I)
        self.reader = DocumentReader(self)
        self.journal = JournalUI(self)
        self.controls = ControlsOverlay(self)
        self.ending_t = 0.0
        self.loading_text = Text(parent=camera.ui, text="", origin=(0, 0), scale=1.4, color=color.rgb(.7, .8, .8),
                                 z=-30)
        self.menu_space = None
        self.show_menu()

    # ==================================================================
    # MENUS
    # ==================================================================
    def show_menu(self):
        self._cleanup_world()
        self.state = "menu"
        self.hud.set_mode("none")
        self.hud.set_fade(0)
        mouse.locked = False
        mouse.visible = True
        if self.menu_space is None:
            self.menu_space = Space(random.randint(0, 99999))
        self.audio.stop_all_loops()
        # le « chant » de SINUS : bourdonnement grave pulsé à 7 Hz
        self.menu_drone = self.audio.loop("menu", "sinus_hum", 1.0, ambient=True)
        self.menu_drone.set(.8, fade=.5)
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = C.FOV
        self._set_screen(TitleScreen(story.GAME_TITLE, story.TITLE_SUBTITLE,
                                     ["Nouvelle partie", "Commandes", "Quitter"], self._menu_select))

    def _set_screen(self, s):
        if self.screen:
            self.screen.destroy()
        self.screen = s

    def _menu_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt == "Nouvelle partie":
            self.new_game()
        elif opt == "Commandes":
            self.controls.toggle()
        elif opt == "Quitter":
            application.quit()

    # ==================================================================
    # CONSTRUCTION D'UNE PARTIE
    # ==================================================================
    def new_game(self, seed=None):
        if seed is None:
            seed = C.SEED if C.SEED is not None else random.randint(0, 999999)
        self.seed = seed
        self._set_screen(None)
        self.state = "loading"
        self.loading_text.text = f"Approche du Kerguelen...\nseed {seed}"
        self.hud.set_fade(1)
        invoke(self._build_world, seed, delay=.15)

    def _build_world(self, seed):
        self._cleanup_world()
        if self.menu_space:
            self.menu_space.destroy()
            self.menu_space = None
        self.audio.stop_all_loops()
        random.seed(seed)
        self.world_root = Entity(name="world")
        layout = ShipLayout(seed)
        self.layout = layout
        self.level = layout.main
        self.lights = LightManager(self.world_root, self.postfx)
        self.space = Space(seed)
        self.builder = LevelBuilder(self.level, self.lights, self.world_root, seed)
        self.builder.build()
        self.exterior = ExteriorShip(self, self.level, self.lights, self.world_root, seed)
        rng = random.Random(seed)
        W = self.level.W * C.CELL
        D = self.level.H * C.CELL
        start = (W * .5 + rng.uniform(-25, 25), rng.uniform(15, 28), D + C.SHIP_START_DISTANCE * .6)
        self.shuttle = Shuttle(self, start, 180)
        self.docs = DocumentLog(self)
        self.docs.present = set(self.builder.doc_present)
        self.docs.pickups = self.builder.doc_pickups
        self.inventory = Inventory(self)
        self.inventory_ui = InventoryUI(self)
        self.weapons = Weapons(self)
        self.weapons.show(False)
        # courant du vaisseau (coupé au départ) et casier piégé
        self.power = PowerSystem(self, self.level, self.builder, random.Random(seed * 5 + 1))
        self.screamer = Screamer(self, self.builder.loot_dir.lockers, random.Random(seed * 11 + 3))
        self.place_autopsy()
        self.horror = HorrorManager(self)
        self.hallu = Hallucinations(self)
        self.revelation = Revelation(self)
        self.player = self.creature = self.aliens = self.director = None
        self.stats = {"kills": 0, "start": self.time, "docs": 0}
        self.current_room = None
        self.loading_text.text = ""
        print(self.level.debug_ascii())
        self.enter_tps()
        self._optimize_entities()

    def _optimize_entities(self):
        """
        Ursina parcourt TOUTES les entités à chaque image. Les entités purement
        visuelles (sans update/input/collider) sont marquées 'ignore' : la boucle
        les saute immédiatement (gain de plusieurs ms par image).
        """
        from ursina import scene as uscene
        for e in uscene.entities:
            if e.ignore or e is self:
                continue
            if hasattr(e, "update") or hasattr(e, "input") or e.collider is not None or hasattr(e, "on_click"):
                continue
            e.ignore = True

    def _cleanup_world(self):
        if self.world_root is None:
            return
        if self.screamer is not None:
            self.screamer.destroy()
        for obj in (self.hallu, self.revelation):
            if obj is not None:
                obj.destroy()
        self.reader.close()
        self.journal.close()
        h = self.hud
        h.glitch_level = h.truth_level = 0.0
        h.set_reflection(0.0)
        h.center_text.text = ""
        self.audio.duck = self.audio.duck_target = 1.0
        for obj in (self.creature, self.aliens, self.shuttle, self.weapons, self.inventory_ui, self.exterior,
                    self.space):
            if obj is not None:
                try:
                    obj.destroy()
                except Exception as exc:  # pragma: no cover
                    print("nettoyage :", exc)
        if self.lights:
            self.lights.destroy()
        destroy(self.world_root)
        self.world_root = None
        self.level = self.builder = self.lights = self.space = self.exterior = None
        self.shuttle = self.player = self.weapons = self.inventory = self.inventory_ui = None
        self.creature = self.aliens = self.director = self.horror = None
        self.power = self.screamer = None
        self.docs = self.hallu = self.revelation = None
        self.audio.stop_all_loops()
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)

    # ==================================================================
    # PHASE 1 : PILOTAGE
    # ==================================================================
    def enter_tps(self):
        self.state = "tps"
        hangar = self.level.room("hangar")
        self.builder.show_only({hangar.id})
        self.lights.set_mode("tps")
        self.lights.set_sun(-self.space.sun_dir, True)
        self.space.set_dust(True)
        self.exterior.set_enabled(True)
        self.hud.set_mode("tps")
        self.hud.fade_to(0, 2.0)
        mouse.locked = True
        camera.fov = C.FOV - 10
        self.horror.amb.set(.6)
        for m in story.ARRIVAL_MESSAGES:
            self.hud.message(m, color.rgb(.7, .85, 1))

    def _update_tps(self, dt):
        sh = self.shuttle
        sh.update(dt, self.inp, self.exterior.colliders)
        if self.state == "tps":
            sh.update_pilot_aids(dt, self.exterior.colliders, self.exterior)
        if self.state == "tps" and sh.auto is None and self.exterior.in_hangar_entrance(sh.position):
            self.state = "landing"
            self.hud.message("Hangar atteint — atterrissage automatique", color.lime)
            sh.silence_aids()
            pad = self.builder.pad_center
            sh.start_landing(pad, self._on_landed)
        if self.state == "landing":
            pad = self.builder.pad_center
            hx0, hx1, hz0, hz1 = self.level.room("hangar").world_bounds()
            sh.cinematic_camera(dt, (hx0 + 5, 7.5, hz1 - 4))
        elif self.state == "tps":
            sh.camera_follow(dt)
        self.exterior.update(dt)
        self.space.update(dt)
        cp = camera.world_position
        self.lights.update(dt, (cp.x, cp.y, cp.z), 0)
        self.builder.update(dt, [], (cp.x, cp.y, cp.z), fps_mode=False)

    def _on_landed(self):
        self.hud.fade_to(1, 1.3)
        invoke(self.enter_fps, delay=1.6)

    # ==================================================================
    # PHASE 2 : EXPLORATION
    # ==================================================================
    def enter_fps(self):
        if self.state != "landing":
            return
        self.state = "fps"
        L = self.level
        sh = self.shuttle
        sh.silence()
        self.exterior.set_enabled(False)
        self.space.set_dust(False)
        self.lights.set_mode("fps")
        for g in self.builder.groups.values():
            g.enabled = True
            g.root.enabled = True
        # la navette posée bloque le passage
        p = sh.root.world_position
        L.add_blocker(Blocker(p.x - 3.1, p.x + 3.1, 0, 3.0, p.z - 4.6, p.z + 4.6, "prop"))
        self.shuttle_interact = ShuttleInteract(self, L, sh)
        # le phare et les feux de la navette posée éclairent un peu le hangar
        hangar_group = self.builder.groups.get(("room", L.room("hangar").id))
        if hangar_group is not None:
            sh.park_lights(self.lights, hangar_group.root)
        # le joueur sort par le sas latéral
        r = sh.root.right
        px, pz = p.x + r.x * 4.2, p.z + r.z * 4.2
        self.player = Player(self, L, px, pz, yaw=0)
        self.weapons.give_pistol()
        self.weapons.show(True)
        self.lights.flashlight_on = True
        # la grande créature démarre loin du hangar
        hx, hz = L.room("hangar").world_center()
        far = [c for c in L.links if L.kind[c[0]][c[1]] in (ROOM, CORR)
               and math.hypot(L.cell_center(*c)[0] - hx, L.cell_center(*c)[1] - hz) > 40]
        cell = random.choice(far) if far else L.random_cell()
        self.creature = Creature(self, L, cell)
        self.director = AIDirector(self)
        self.aliens = AlienManager(self)
        self.hud.set_mode("fps")
        self.hud.fade_to(0, 1.8)
        mouse.locked = True
        camera.fov = C.FOV
        self.horror.amb.set(1.0)
        self.hud.message("Pistolet récupéré dans la navette (%d + %d balles)." % (C.PISTOL_START_MAG,
                                                                                C.PISTOL_START_RESERVE))
        self.hud.message("Chaque tir fera du bruit. Beaucoup de bruit.", color.rgb(.8, .6, .5))
        if not self.power.on:
            self.hud.message("Le vaisseau est mort : plus une seule lumière. Rétablis le courant "
                             "dans la salle des machines.", color.rgb(.7, .8, .9))
        self.hud.message(story.HANGAR_MESSAGE, color.rgb(.6, .7, .7))
        self.audio.play("door_open", .8)
        # vérification : aucune entité du décor ne doit être restée « non éclairée »
        audit_unlit(application.base.render, "vaisseau")

    def _update_fps(self, dt):
        inp = self.inp
        p = self.player
        lt = self.lights
        ui = self.inventory_ui
        rd, jr = self.reader, self.journal
        # --- documents, journal (J / Create), inventaire : le jeu continue ---
        if self.controls.open:
            pass
        elif rd.is_open:
            rd.update(dt, inp)
        elif jr.open:
            if inp.pressed("journal"):
                jr.toggle()
            else:
                jr.update(dt, inp)
        else:
            if inp.pressed("journal") and not p.hidden:
                ui.close()
                jr.toggle()
            elif inp.pressed("inventory") and not p.hidden:
                ui.toggle()
            ui.update(dt, inp)
        self.ui_consumed = ui.open or rd.is_open or jr.open or self.controls.open
        if not self.ui_consumed:
            if inp.pressed("flashlight"):
                if lt.battery <= 0:
                    self.hud.message("Batterie vide — trouve des piles")
                else:
                    lt.flashlight_on = not lt.flashlight_on
                self.audio.play("flashlight_click", .7)
            if inp.pressed("nightvision"):
                self.toggle_nightvision()
            if inp.pressed("heal"):
                self.inventory.use("medkit")
            if inp.pressed("prev_item"):
                self.inventory.cycle_equipped(-1)
            if inp.pressed("next_item"):
                self.inventory.cycle_equipped(1)
            if inp.pressed("use_item"):
                self.inventory.use(self.inventory.equipped)
        # --- joueur et armes ---------------------------------------------
        p.update(dt, inp)
        if self.state != "fps":
            return
        # taper sur la lampe quand elle faiblit (bouton Recharger) : répit de quelques secondes
        wpn_inp = inp if not self.ui_consumed else self._null
        if (not self.ui_consumed and inp.pressed("reload") and lt.battery < C.FLASHLIGHT_FLICKER
                and (lt.flashlight_on or lt.battery <= 0) and not lt.nightvision):
            lt.tap_flashlight()
            self.audio.play("flashlight_click", .8, .8)
            self.audio.play("knife_hit", .25, 1.8)
            self.hud.message("*tape sur la lampe*", color.rgb(.7, .7, .6))
            wpn_inp = _MaskedInput(inp, {"reload"})
        self.weapons.update(dt, wpn_inp)
        # --- batterie -------------------------------------------------------
        before = lt.battery
        if lt.flashlight_on:
            lt.battery -= C.FLASHLIGHT_DRAIN * dt
        if lt.nightvision:
            lt.battery -= C.NIGHTVISION_DRAIN * dt
        if lt.battery <= 0 and (lt.flashlight_on or lt.nightvision):
            lt.battery = 0
            lt.flashlight_on = False
            if lt.nightvision:
                lt.set_nightvision(False)
            self.audio.play("flashlight_click", 1.0, .7)
            self.audio.play("spark", .5)
            self.hud.message("Batterie vide !", color.orange)
        if before >= 15 > lt.battery:
            self.audio.play("beep", .8)
            self.hud.message("Batterie faible", color.orange)
        lt.battery = max(0.0, lt.battery)
        # --- monde ----------------------------------------------------------
        occ = [(p.x, p.z)]
        if self.creature and self.creature.visible:
            occ.append((self.creature.x, self.creature.z))
        occ += [(a.x, a.z) for a in self.aliens.aliens]
        cp = camera.world_position
        self.builder.update(dt, occ, (cp.x, cp.y, cp.z))
        self.creature.update(dt)
        if self.state != "fps":
            return
        self.aliens.update(dt)
        self.director.update(dt)
        self.horror.update(dt)
        self.power.update(dt)
        self.screamer.update(dt)
        self.hallu.update(dt)
        self.revelation.update(dt)
        lt.update(dt, (cp.x, cp.y, cp.z), self.horror.light_level)
        self.shuttle.update_parked(lt.time)
        self.space.update(dt)
        self._room_events()
        # touches de test : F4 bascule le courant, F5 déclenche le screamer
        if C.DEBUG_KEYS and not self.ui_consumed:
            if inp.pressed("debug_power"):
                self.power.debug_toggle()
            if inp.pressed("debug_screamer"):
                self.screamer.trigger(None)
            if inp.pressed("debug_docs"):
                self.docs.debug_all()
            if inp.pressed("debug_reveal"):
                self.revelation.debug_start()
        if inp.debug_overlay:
            cr = self.creature
            pm = lt.power
            states = {}
            for fx in lt.fixtures:
                s_ = pm.fixture_state(fx, lt.time)
                states[s_] = states.get(s_, 0) + 1
            inp.debug_overlay.extra = (f"\nCréature : {cr.state}  vue={cr.can_see}\n"
                                       f"Aliens : {len(self.aliens.alive)}  horreur={self.horror.level:.2f}\n"
                                       f"Directrice : pression={self.director.pressure:.2f}\n"
                                       f"Courant : {self.power.state} / {pm.state}  "
                                       + "  ".join(f"{k} {v}" for k, v in sorted(states.items()))
                                       + f"\nInfection : {self.hallu.infection:.2f}  documents {len(self.docs.found)}")

    def _room_events(self):
        p = self.player
        room = self.level.room_at(p.x, p.z)
        if room is not self.current_room:
            self.current_room = room
            if room is not None and not room.visited:
                room.visited = True
                self.screamer.on_room_visited(room)
                self.hud.message(room.name.upper(), color.rgb(.6, .75, .8))
                ev = ROOM_EVENTS.get(room.type)
                if ev:
                    strength, text_on, text_off = ev
                    text = text_on if self.power.on else text_off
                    if random.random() < .8:
                        self.horror.scripted_scare(strength)
                    if text:
                        self.hud.message(text, color.rgb(.7, .7, .65))

    # ------------------------------------------------------------------
    # services utilisés par les autres modules
    # ------------------------------------------------------------------
    def hit_targets(self, melee=False):
        out = []
        if self.aliens:
            out += self.aliens.hit_spheres()
        if self.creature and self.creature.visible:
            out += [(self.creature, c, r) for c, r in self.creature.hit_spheres()]
        return out

    def noise(self, pos, radius, kind):
        if self.horror:
            self.horror.emit_noise(pos, radius, kind)

    def shake(self, amount):
        self.shake_amount = max(self.shake_amount, amount)

    def has_hdd(self):
        return self.inventory is not None and self.inventory.has("hdd")

    def objective_text(self):
        pw = self.power
        if pw is not None and not pw.on and not self.has_hdd():
            if pw.state == "restarting":
                return "OBJECTIF : le courant revient..."
            txt = "OBJECTIF : rétablis le courant dans la salle des machines"
            if pw.fuses_needed and pw.fuses_inserted < pw.fuses_needed:
                txt += f"  (fusibles {pw.fuses_inserted + pw.fuses_held}/{pw.fuses_needed})"
            return txt
        if not self.has_hdd():
            return "OBJECTIF : récupère le disque dur dans la salle de commandement"
        return "OBJECTIF : " + story.FINAL_OBJECTIVE

    def objective_target(self):
        pw = self.power
        if pw is not None and not pw.on and not self.has_hdd() and pw.spec is not None:
            p = pw.spec["pos"]
            return (p[0], p[2])
        if not self.has_hdd():
            h = self.builder.hdd
            return (h.pos[0], h.pos[2]) if h and not h.taken else None
        p = self.shuttle.root.world_position
        return (p.x, p.z)

    def place_autopsy(self):
        """Le rapport d'autopsie de Yuri (D08) est posé au pied du casier piégé (le screamer prend son sens)."""
        b = self.builder
        for d in b.doc_deferred:
            target = self.screamer.target if self.screamer is not None else None
            if target is not None:
                b.place_near_locker(d, target)
            else:
                b.place_doc_floor(d, "medbay")

    def toggle_nightvision(self):
        lt = self.lights
        if not self.inventory.nv_equipped:
            self.hud.message("Il te faut un casque de vision nocturne")
            return
        if lt.battery <= 0 and not lt.nightvision:
            self.hud.message("Batterie vide")
            return
        lt.set_nightvision(not lt.nightvision)
        self.audio.play("nv_on" if lt.nightvision else "flashlight_click", .7)

    def on_hdd_taken(self):
        """Le disque dur est branché sur la console : la vérité, puis l'hallucination revient en pire."""
        self.audio.play("hdd_pickup", 1.0)
        self.revelation.begin()

    # ==================================================================
    # FIN DE PARTIE
    # ==================================================================
    def start_escape(self):
        if self.state != "fps":
            return
        self.state = "escape"
        self.inventory_ui.close()
        self.hud.fade_to(1, .8)
        invoke(self._escape_cinematic, delay=.9)

    def _escape_cinematic(self):
        self.inventory_ui.hide_all()
        self.weapons.show(False)
        self.lights.flashlight_on = False
        self.lights.set_nightvision(False)
        self.creature.root.enabled = False
        for a in self.aliens.aliens:
            a.root.hide()          # les araignées sont des nœuds Panda3D
        self.exterior.set_enabled(True)
        self.builder.show_only({self.level.room("hangar").id})
        self.lights.set_mode("tps")
        self.lights.set_sun(-self.space.sun_dir, True)
        self.space.set_dust(True)
        self.hud.set_mode("none")
        self.horror.level = 0
        self.horror.timer = 0
        self.horror.update(0.01)
        self.audio.play("victory", 1.0, music=True)
        sh = self.shuttle
        hx0, hx1, hz0, hz1 = self.level.room("hangar").world_bounds()
        sh.cam_pos = Vec3(hx0 + 5, 7.5, hz1 - 4)
        sh.start_takeoff(self._ending_start)
        self.hud.fade_to(0, 1.2)
        self.hallu.hide_all()
        self.revelation.finish()
        self.reader.close()
        self.journal.close()

    def _update_escape(self, dt):
        sh = self.shuttle
        if sh.auto is None:
            return
        sh.update(dt, self.inp, [])
        cx = (self.exterior.open_x0 + self.exterior.open_x1) / 2
        if sh.auto == "exit" and sh.auto_t > 1.2:
            sh.cinematic_camera(dt, (cx + 16, 9, -40))
        else:
            hx0, hx1, hz0, hz1 = self.level.room("hangar").world_bounds()
            sh.cinematic_camera(dt, (hx0 + 5, 7.5, hz1 - 4))
        self.exterior.update(dt)
        self.space.update(dt)
        cp = camera.world_position
        self.lights.update(dt, (cp.x, cp.y, cp.z), 0)
        self.builder.update(dt, [], (cp.x, cp.y, cp.z), fps_mode=False)

    # ------------------------------------------------------------------
    # FIN : la navette s'éloigne du Kerguelen... et elle n'est pas seule
    # ------------------------------------------------------------------
    def _ending_start(self):
        self.state = "ending"
        self.ending_t = 0.0
        self._ending_flags = set()
        self.ending_cam = Vec3(camera.world_position)

    def _update_ending(self, dt):
        sh = self.shuttle
        self.ending_t += dt
        t = self.ending_t
        f = self._ending_flags
        sh.root.position += sh.root.forward * 30 * dt
        self.space.update(dt)
        self.exterior.update(dt)
        if t < 5.5:
            # plan extérieur : la navette s'éloigne du Kerguelen qui dérive (derrière elle), planètes au loin
            from panda3d.core import Vec3 as PVec3
            p = sh.root.world_position
            cam = p + sh.root.forward * (30 - t * 3) + sh.root.right * 14 + Vec3(0, 5, 0)
            ship = Vec3(self.level.W * C.CELL / 2, 0, self.level.H * C.CELL / 2)
            look = p + (ship - p) * .45          # la navette au premier plan, le Kerguelen derrière elle
            camera.position = cam
            camera.lookAt(PVec3(look.x, look.y, look.z), PVec3(0, 1, 0))
            if t > .6 and "msg" not in f:
                f.add("msg")
                self.audio.play("static_burst", .6)
                self.hud.center_text.text = story.ENDING_SHUTTLE_MESSAGE
            if t > 4.6:
                self.hud.center_text.text = ""
        else:
            # plan du cockpit : dans le reflet de la verrière, derrière le joueur...
            if "cockpit" not in f:
                f.add("cockpit")
                self.hud.set_fade(0)
                # on est dans le cockpit : on ne garde que le tableau de bord (la vitre est le reflet du HUD)
                for c in sh.model.getChildren():
                    if c != sh.dash:
                        c.hide()
                sh.fx_root.hide()
                self.audio.stop_loop("sinus_low")
                self.hum_end = self.audio.loop("sinus_end", "sinus_hum", 1.0, ambient=True)
                self.hum_end.set(.25, fade=.5)
            cam_p = sh._local_to_world((0, 1.28, 1.42))      # tête du pilote, au-dessus du siège
            ahead = sh._local_to_world((0, -3.0, 40))                # regard un peu baissé : tableau de bord
            camera.position = cam_p
            camera.lookAt(ahead)
            refl = min(.22, (t - 5.5) * .12)
            eyes = 1.0 if 8.4 <= t < 8.6 else 0.0
            self.hud.set_reflection(refl, eyes)
            if t > 7.9 and "swell" not in f:
                f.add("swell")
                self.audio.play("sinus_swell", 1.0)
                self.hum_end.set(1.0, fade=2.5)
            if t >= 8.75 and "black" not in f:
                f.add("black")
                self.hud.set_fade(1)
                self.hud.set_reflection(0.0)
                self.audio.stop_all_loops()
            if t >= 10.8 and "screen" not in f:
                f.add("screen")
                self._final_screen()

    def _final_screen(self):
        self.state = "victory"
        mouse.locked = False
        t = self.time - self.stats["start"]
        n = len(self.docs.found) if self.docs else 0
        total = self.docs.total if self.docs else len(story.DOCUMENTS)
        sub = (f"{story.ENDING_CAPTION}\n\nDocuments retrouvés : {n}/{total}\n"
               f"Temps à bord : {int(t // 60)} min {int(t % 60)} s   —   Créatures « abattues » : {self.stats['kills']}")
        self._set_screen(MenuScreen(story.GAME_TITLE, sub, ["Nouvelle partie", "Menu principal", "Quitter"],
                                    self._end_select, title_color=color.rgb(.92, .93, .95), bg_alpha=.9))

    def game_over(self, cause):
        if self.state not in ("fps", "tps", "landing"):
            return
        self.state = "gameover"
        self.inp.rumble(1, 1, 900)
        if cause == "creature":
            self.hud.set_fade(1)            # écran noir immédiat
            self.audio.play("death_sting", 1.0)
            self.audio.play("creature_roar", 1.0, .9)
            sub = "Elle t'a trouvé."
        elif cause == "shuttle":
            self.audio.play("ship_hit", 1.0, .7)
            self.hud.fade_to(1, .6)
            sub = "La navette s'est disloquée contre la coque du Kerguelen."
        else:
            self.audio.play("death_sting", .7, .8)
            self.hud.fade_to(1, 1.2)
            sub = "Les petites créatures t'ont submergé."
        self.audio.stop_all_loops()
        invoke(self._show_gameover, sub, delay=1.6)

    def _show_gameover(self, sub):
        if self.inventory_ui:
            self.inventory_ui.hide_all()
        mouse.locked = False
        self.hud.set_mode("none")
        self._set_screen(MenuScreen("TU ES MORT", sub, ["Réessayer (même partie)", "Nouvelle partie",
                                                         "Menu principal"], self._end_select,
                                    title_color=color.rgb(.9, .15, .1), bg_alpha=.2))

    def _end_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt.startswith("Réessayer"):
            self.new_game(self.seed)
        elif opt == "Nouvelle partie":
            self.new_game(None)
        elif opt == "Menu principal":
            self.show_menu()
        elif opt == "Quitter":
            application.quit()

    # ==================================================================
    # PAUSE
    # ==================================================================
    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            mouse.locked = False
            self._set_screen(MenuScreen("PAUSE", f"{story.GAME_TITLE} — seed {self.seed}",
                                        ["Reprendre", "Commandes", "Recommencer", "Menu principal", "Quitter"],
                                        self._pause_select, bg_alpha=.6))
        else:
            self._set_screen(None)
            mouse.locked = True

    def _pause_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt == "Reprendre":
            self.toggle_pause()
        elif opt == "Commandes":
            self.controls.toggle()
        elif opt == "Recommencer":
            self.paused = False
            self.new_game(self.seed)
        elif opt == "Menu principal":
            self.paused = False
            self.show_menu()
        elif opt == "Quitter":
            application.quit()

    # ==================================================================
    # BOUCLE
    # ==================================================================
    def input(self, key):
        self.inp.on_key(key)

    def update(self):
        dt = min(utime.dt, 1 / 20)
        self.time += dt
        playing = self.state in ("tps", "landing", "fps")
        self.inp.update(dt, mouse_look=playing and not self.paused and not self.controls.open)
        # écran des commandes (I) : accessible partout
        closed_overlay = False
        if self.controls.open:
            if self.inp.pressed("controls") or self.inp.pressed("pause") or self.inp.pressed("back"):
                self.controls.close()
                closed_overlay = True
        elif self.inp.pressed("controls") and self.state in ("menu", "tps", "landing", "fps", "victory", "gameover"):
            self.controls.toggle()
        if playing and self.inp.pressed("pause") and not closed_overlay and not self.controls.open:
            if self.reader.is_open and not self.paused:
                self.reader.close()
            elif self.journal.open and not self.paused:
                self.journal.close()
            elif self.inventory_ui and self.inventory_ui.open and not self.paused:
                self.inventory_ui.hide_all()
            else:
                self.toggle_pause()
        if self.screen and not self.controls.open:
            self.screen.update(dt, self.inp)
        if not self.paused:
            if self.state == "menu":
                camera.rotation_y += dt * 2
                camera.rotation_x = math.sin(self.time * .1) * 5
                if self.menu_space:
                    self.menu_space.update(dt)
            elif self.state in ("tps", "landing"):
                self._update_tps(dt)
            elif self.state == "fps":
                self._update_fps(dt)
            elif self.state == "escape":
                self._update_escape(dt)
            elif self.state == "ending":
                self._update_ending(dt)
            elif self.state in ("victory",):
                if self.shuttle:
                    self.shuttle.root.position += self.shuttle.root.forward * 30 * dt
                    self.shuttle.cinematic_camera(dt, camera.world_position)
                if self.space:
                    self.space.update(dt)
        self.shake_amount = max(0.0, self.shake_amount - dt * 2)
        self._opt_timer = getattr(self, "_opt_timer", 0) - dt
        if self._opt_timer <= 0:
            self._opt_timer = 1.5
            self._optimize_entities()
        self.audio.set_listener(camera.world_position, camera.right)
        self.audio.update(dt)
        self.postfx.update()
        self.hud.update(dt)
        self.inp.end_frame()


def run():
    global game
    game = Game()
    app.run()


if __name__ == "__main__":
    run()
