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

import startup  # noqa: E402

loadPrcFileData("", "sync-video %d" % (1 if C.VSYNC else 0))
loadPrcFileData("", "texture-anisotropic-degree 4")
# audio : OpenAL testé AVANT d'ouvrir la fenêtre, repli automatique sur FMOD (voir startup.py)
startup.choose_audio_backend()
_WIN_SIZE, _BORDERLESS = startup.initial_window()     # plein écran fenêtré à la taille de l'écran

from ursina import (Ursina, Entity, Text, camera, color, mouse, window, application, invoke,  # noqa: E402
                    destroy, time as utime, Vec3)

app = Ursina(title=C.TITLE, development_mode=True, editor_ui_enabled=False, borderless=_BORDERLESS,
             fullscreen=False, size=_WIN_SIZE, vsync=C.VSYNC)
window.color = color.black
# IMPORTANT : Ursina 8 donne par défaut à chaque entité un shader NON ÉCLAIRÉ
# (unlit_with_fog_shader) qui affiche tout en pleine lumière, quel que soit
# l'éclairage. Sans shader propre, les entités héritent du shader automatique
# de Panda3D (éclairage par pixel, ci-dessous). Sans effet sous Ursina 7.
Entity.default_shader = None
if hasattr(window, "editor_ui"):
    window.editor_ui.enabled = False     # cache le bouton X et les compteurs d'Ursina
# les raccourcis du mode développeur d'Ursina (F10 = rendu fil de fer, F11 = plein écran avec barre
# de titre, F12 = éditeur) entrent en conflit avec les touches du jeu : on les désactive
if hasattr(window, "input_entity"):
    window.input_entity.input = None
    window.input_entity.enabled = False
DISPLAY = startup.DisplayMode(application.base)
if _BORDERLESS:
    DISPLAY.set(True)                    # collée en haut à gauche de l'écran, sans bordure
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
from safety import SpawnGuard  # noqa: E402
from guidance import Guidance  # noqa: E402
from vertigo import Vertigo, LABELS as VERTIGO_LABELS  # noqa: E402
from ending import EndingCinematic, HangarDoors  # noqa: E402
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
        self.spawn_guard = SpawnGuard(self)
        self.guidance = None
        self.vertigo = None
        self.ending = None
        self.hangar_doors = None
        self.vertigo_setting = C.VERTIGO_INTENSITY      # réglage d'accessibilité (menu pause)
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
        self.audio.reset()          # aucun « silence » (screamer, levier) ne doit rester bloqué
        # le « chant » de SINUS : bourdonnement grave pulsé à 7 Hz
        self.menu_drone = self.audio.loop("menu", "sinus_chant", 1.0, ambient=True)
        self.menu_drone.set(.8, fade=.5)
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = C.FOV
        self._title_menu()

    def _fullscreen_label(self):
        return "Plein écran : " + ("Oui" if DISPLAY.full else "Non")

    def _title_menu(self, sel=0):
        scr = TitleScreen(story.GAME_TITLE, story.TITLE_SUBTITLE,
                          ["Nouvelle partie", "Commandes", self._fullscreen_label(), "Quitter"], self._menu_select)
        # état du son, bien visible (vert = OK, rouge = aucune sortie audio)
        txt, ok = self.audio.status_line()
        Text(parent=scr.root, text=txt, origin=(0, 0), y=-.33, scale=.9,
             color=color.rgb(.45, .85, .5) if ok else color.rgb(1, .35, .3))
        scr.sel = sel
        scr._refresh()
        self._set_screen(scr)

    def toggle_fullscreen(self):
        DISPLAY.toggle()
        self.hud.message("Plein écran" if DISPLAY.full else "Fenêtre", color.rgb(.7, .75, .8))
        if self.state == "menu" and isinstance(self.screen, TitleScreen):
            self._title_menu(self.screen.sel)
        elif self.paused:
            self._pause_menu(self.screen.sel if self.screen else 0)

    def switch_audio_backend(self):
        """Maj+F8 : relance le jeu avec l'autre moteur audio (OpenAL <-> FMOD)."""
        other = startup.switch_backend_and_restart()
        if other is None:
            self.hud.message("Impossible de relancer le jeu", color.red)
            return
        print(f"[audio] relance du jeu avec {startup.NAMES[other]}...")
        application.quit()

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
        elif opt.startswith("Plein écran"):
            self.toggle_fullscreen()
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
        self.audio.reset()
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
        self.vertigo = Vertigo(self)
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
        for obj in (self.hallu, self.revelation, self.guidance, self.vertigo):
            if obj is not None:
                obj.destroy()
        self.guidance = None
        self.vertigo = None
        if self.ending is not None:
            self.ending.cleanup()
            self.ending = None
        if self.hangar_doors is not None:
            self.hangar_doors.destroy()
            self.hangar_doors = None
        self.spawn_guard = SpawnGuard(self)
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
        if C.DEBUG_KEYS and self.inp.pressed("debug_hangar"):
            self.debug_skip_to_hangar()
            return
        sh = self.shuttle
        sh.update(dt, self.inp, self.exterior.colliders)
        if self.state == "tps":
            sh.update_pilot_aids(dt, self.exterior.colliders, self.exterior)
        if self.state == "tps" and sh.auto is None and self.exterior.in_hangar_entrance(sh.position):
            self.state = "landing"
            self.hud.message("Hangar atteint — atterrissage automatique", color.lime)
            sh.silence_aids()
            sh.start_landing(self.builder.landing, self._on_landed)
        if self.state == "landing":
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
        seed = self.seed
        # l'appel différé ne doit concerner QUE cette partie (pas une partie relancée entre-temps)
        invoke(lambda: self.enter_fps() if self.seed == seed and self.state == "landing" else None, delay=1.6)

    def debug_skip_to_hangar(self):
        """F9 : saute le pilotage et l'atterrissage, le joueur apparaît directement dans le hangar."""
        if self.state in ("tps", "landing"):
            self.shuttle.snap_to_pad(self.builder.landing)
            self.state = "landing"
            self.hud.message("[debug] atterrissage immédiat", color.yellow)
            self.enter_fps()
        elif self.state == "fps":
            self.spawn_guard.respawn("[debug] F9")
            self.hud.message("[debug] retour au hangar", color.yellow)

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
        # la navette est posée EXACTEMENT sur l'aire prévue par le générateur (source unique)
        landing = self.builder.landing
        sh.snap_to_pad(landing)
        px_, pz_ = landing["pad"]
        # la navette posée bloque le passage
        L.add_blocker(Blocker(px_ - 3.1, px_ + 3.1, 0, 3.0, pz_ - 4.6, pz_ + 4.6, "prop"))
        self.shuttle_interact = ShuttleInteract(self, L, sh)
        # le phare et les feux de la navette posée éclairent un peu le hangar
        hangar_group = self.builder.groups.get(("room", L.room("hangar").id))
        if hangar_group is not None:
            sh.park_lights(self.lights, hangar_group.root)
        # le joueur sort par le sas latéral : point fixe calculé à la génération, vérifié,
        # puis posé sur le sol par un rayon (voir safety.py) avant de rendre les contrôles
        sx, sz = landing["spawn"]
        self.player = Player(self, L, sx, sz, yaw=landing["spawn_yaw"])
        self.spawn_guard = SpawnGuard(self)
        self.spawn_guard.begin(self.player, landing)
        self.guidance = Guidance(self)
        # les grandes portes du hangar se referment derrière la navette
        self.hangar_doors = HangarDoors(self)
        self.hangar_doors.open_k = 1.0
        self.hangar_doors.close()
        invoke(lambda: self.audio.play("hangar_doors", .7) if self.state == "fps" else None, delay=.4)
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
                self.inventory.use("bandage")
            # clavier : F utilise l'objet équipé, C / V en changent ; manette : Gauche utilise l'objet
            # équipé (Droite change d'arme : voir weapons.py)
            if inp.pressed("use_item"):
                self.inventory.use(self.inventory.equipped)
            elif inp.pressed("prev_item"):
                self.inventory.cycle_equipped(-1)
            elif inp.pressed("next_item") and not inp.pad.pressed("dpad_right"):
                self.inventory.cycle_equipped(1)
        # --- joueur et armes ---------------------------------------------
        self.spawn_guard.update(dt)        # apparition sûre puis filet de sécurité continu
        p.update(dt, inp)
        if self.state != "fps":
            return
        # taper sur la lampe quand elle faiblit (bouton Recharger) : répit de quelques secondes
        # pendant l'application d'un bandage : arme baissée, impossible de tirer (vulnérable)
        wpn_inp = inp if not (self.ui_consumed or p.bandaging > 0) else self._null
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
        if lt.battery <= 0 and lt.flashlight_on:
            lt.battery = 0
            lt.flashlight_on = False
            self.audio.play("flashlight_click", 1.0, .7)
            self.audio.play("spark", .5)
            self.hud.message("Batterie vide !", color.orange)
        self._update_nvg(dt)
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
        self.vertigo.update(dt)
        lt.update(dt, (cp.x, cp.y, cp.z), self.horror.light_level)
        self.shuttle.update_parked(lt.time)
        self.hangar_doors.update(dt)
        self.space.update(dt)
        self._room_events()
        self.guidance.update(dt, inp)
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
            if inp.pressed("debug_hangar"):
                self.debug_skip_to_hangar()
            if inp.pressed("debug_rifle"):
                if inp._kb_held("shift"):
                    self.horror.trigger(None, scripted=True)          # Maj+F12 : alarme générale
                    self.hud.message("[debug] alarme déclenchée", color.yellow)
                else:
                    self.weapons.debug_give_rifle()                     # F12 : fusil + munitions
            if inp.pressed("debug_ending"):
                self.debug_ending()
                return
            if inp.pressed("debug_vertigo") and inp._kb_held("shift"):
                self.vertigo.start_crisis(forced=True)
                self.hud.message("[debug] crise de vertige", color.yellow)
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
            left = self.current_room
            self.current_room = room
            # hallucination (infection avancée) : un corps de la salle quittée aura « bougé »
            # et tournera la tête vers la porte par laquelle on reviendra
            if (left is not None and self.hallu is not None
                    and self.hallu.infection >= C.CORPSE_HALLU_INFECTION
                    and random.random() < C.CORPSE_HALLU_CHANCE):
                cands = [c for c in self.builder.loot_dir.corpses
                         if getattr(c, "room", None) is left and not getattr(c, "hallucinated", True)]
                if cands:
                    random.choice(cands).hallucinate((p.x, p.z))
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

    def objective_goal(self):
        """
        Destination du guidage : (x, z, libellé). Suit l'objectif en cours :
        fusibles manquants -> tableau de la salle des machines -> disque dur ->
        navette.
        """
        pw = self.power
        L = self.level
        if pw is not None and not pw.on and not self.has_hdd() and pw.spec is not None:
            if pw.state == "off" and pw.fuses_needed and pw.fuses_inserted + pw.fuses_held < pw.fuses_needed:
                p = self.player
                left = [f for f in self.builder.fuses if not f.taken]
                if left and p is not None:
                    f = min(left, key=lambda f_: math.hypot(f_.pos[0] - p.x, f_.pos[2] - p.z))
                    room = L.room_at(f.pos[0], f.pos[2])
                    where = room.name if room is not None else "couloir"
                    return (f.pos[0], f.pos[2], f"Fusible ({where})")
            sp = pw.spec["pos"]
            return (sp[0], sp[2], "Salle des machines")
        if not self.has_hdd():
            h = self.builder.hdd
            if h and not h.taken:
                return (h.pos[0], h.pos[2], "Salle de commandement")
            return None
        px_, pz_ = self.builder.landing["pad"]
        sx_, sz_ = self.builder.landing["spawn"]
        return (px_ + (sx_ - px_) * .8, pz_ + (sz_ - pz_) * .8, "Navette (hangar)")

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
        if lt.nv_battery <= 0 and not lt.nightvision:
            self.hud.message("Batterie du casque vide — une pile peut la recharger en partie")
            return
        lt.set_nightvision(not lt.nightvision)
        lt.nv_strength = 1.0
        self.audio.play("nv_on" if lt.nightvision else "flashlight_click", .7)

    def _update_nvg(self, dt):
        """
        Batterie propre au casque de vision nocturne (séparée de la lampe) :
        NVG_BATTERY_SECONDS d'autonomie, avertissement à NVG_LOW_PERCENT %,
        puis extinction progressive (l'image s'assombrit et grésille) à 0 %.
        """
        lt = self.lights
        if not lt.nightvision:
            lt.nv_strength = 1.0
            return
        before = lt.nv_battery
        lt.nv_battery = max(0.0, lt.nv_battery - dt * 100.0 / C.NVG_BATTERY_SECONDS)
        if before > C.NVG_LOW_PERCENT >= lt.nv_battery:
            self.audio.play("nvg_warn", .5)
            self.hud.message(f"Casque de vision nocturne : batterie faible ({C.NVG_LOW_PERCENT} %)", color.orange)
        # en dessous du seuil d'extinction, l'image faiblit progressivement
        lt.nv_strength = min(1.0, lt.nv_battery / C.NVG_FADE_PERCENT) if C.NVG_FADE_PERCENT > 0 else 1.0
        if lt.nv_battery <= 0:
            lt.set_nightvision(False)
            lt.nv_strength = 1.0
            self.audio.play("nvg_off", .6)
            self.hud.message("Le casque s'éteint : batterie épuisée.", color.orange)

    def on_hdd_taken(self):
        """Le disque dur est branché sur la console : la vérité, puis l'hallucination revient en pire."""
        self.audio.play("hdd_pickup", 1.0)
        self.revelation.begin()

    # ==================================================================
    # FIN DE PARTIE
    # ==================================================================
    def start_escape(self):
        """Le joueur rejoint la navette avec le disque dur : cinématique de fin (ending.py)."""
        if self.state != "fps":
            return
        self.state = "ending"
        if self.vertigo is not None:
            self.vertigo.stop()
        self.inventory_ui.close()
        self.hud.fade_to(1, .7)
        self.ending = EndingCinematic(self)
        invoke(self._ending_begin, delay=.8)

    def _ending_begin(self):
        if self.state == "ending" and self.ending is not None:
            self.ending.start()

    def debug_ending(self):
        """F10 : lance directement la cinématique de fin (donne le disque dur si besoin)."""
        if self.state != "fps":
            return
        if not self.has_hdd():
            self.inventory.add("hdd", 1)
        self.hud.message("[debug] cinématique de fin", color.yellow)
        self.start_escape()

    def _update_ending(self, dt):
        if self.ending is not None and self.ending.started and not self.ending.done:
            self.ending.update(dt)

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
        if self.vertigo is not None:
            self.vertigo.stop()
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
            self._pause_menu()
        else:
            self._set_screen(None)
            mouse.locked = True

    def _vertigo_label(self):
        return "Vertiges : " + VERTIGO_LABELS.get(self.vertigo_setting, "Normal")

    def _pause_menu(self, sel=0):
        scr = MenuScreen("PAUSE", f"{story.GAME_TITLE} — seed {self.seed}",
                         ["Reprendre", "Commandes", self._vertigo_label(), self._fullscreen_label(), "Recommencer",
                          "Menu principal", "Quitter"], self._pause_select, bg_alpha=.6)
        scr.sel = sel
        scr._refresh()
        self._set_screen(scr)

    def _pause_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt.startswith("Vertiges"):
            # accessibilité : Désactivé / Faible / Normal / Fort (le mal des transports est possible)
            if self.vertigo is not None:
                self.vertigo.cycle_setting()
            else:
                from vertigo import ORDER
                i = ORDER.index(self.vertigo_setting) if self.vertigo_setting in ORDER else 2
                self.vertigo_setting = ORDER[(i + 1) % len(ORDER)]
            self._pause_menu(sel=2)
            return
        if opt.startswith("Plein écran"):
            self.toggle_fullscreen()
            return
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
        # F11 / Alt+Entrée : plein écran <-> fenêtre (partout)
        inp = self.inp
        alt = inp._kb_held("alt") or inp._kb_held("left alt") or inp._kb_held("right alt")
        if (inp.pressed("fullscreen") and not inp._kb_held("shift")) or (alt and "enter" in inp._kb_pressed):
            inp._kb_pressed.discard("enter")              # Alt+Entrée ne valide pas le menu
            self.toggle_fullscreen()
        # F8 : son de test (partout, même dans les menus) ; Maj+F8 : essayer l'autre moteur audio
        if self.inp.pressed("debug_sound"):
            if self.inp._kb_held("shift"):
                self.switch_audio_backend()
                return
            self.hud.message(self.audio.test_sound(), color.yellow)
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
