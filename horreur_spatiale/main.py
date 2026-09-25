# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée et gestionnaire d'états du jeu.

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
if hasattr(window, "editor_ui"):
    window.editor_ui.enabled = False     # cache le bouton X et les compteurs d'Ursina
application.base.render.setShaderAuto()     # éclairage par pixel (lampe torche, néons)
camera.clip_plane_near = 0.05

from controller import InputManager  # noqa: E402
from audio import AudioSystem  # noqa: E402
from hud import HUD, MenuScreen  # noqa: E402
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
from loot import NOTES  # noqa: E402


class _NoInput:
    """Entrée neutre (quand l'inventaire est ouvert, l'arme ne réagit pas)."""

    def pressed(self, a):
        return False

    def held(self, a):
        return False


ROOM_EVENTS = {
    "engine": (.7, "Le réacteur gronde. Quelque chose a griffé les parois."),
    "medbay": (.5, "L'infirmerie... Les néons grésillent."),
    "command": (.4, "La passerelle. Le disque dur doit être sur une console."),
    "mess": (.3, None),
}


class Game(Entity):
    def __init__(self):
        super().__init__(ignore_paused=True)
        self.inp = InputManager()
        self.audio = AudioSystem()
        self.hud = HUD(self)
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
        self.stats = {"kills": 0, "start": 0.0, "notes": 0}
        self.current_room = None
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
        self.menu_drone = self.audio.loop("menu", "ambience", 1.0, ambient=True)
        self.menu_drone.set(1.0, fade=.5)
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = C.FOV
        self._set_screen(MenuScreen("ÉPAVE", "Le silence du Mnémosyne",
                                    ["Nouvelle partie", "Quitter"], self._menu_select))
        self.hud.message("Astuce : F3 affiche le debug de la manette", color.rgb(.5, .6, .6))

    def _set_screen(self, s):
        if self.screen:
            self.screen.destroy()
        self.screen = s

    def _menu_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt == "Nouvelle partie":
            self.new_game()
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
        self.loading_text.text = f"Génération de l'épave...\nseed {seed}"
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
        self.lights = LightManager(self.world_root)
        self.space = Space(seed)
        self.builder = LevelBuilder(self.level, self.lights, self.world_root, seed)
        self.builder.build()
        self.exterior = ExteriorShip(self, self.level, self.lights, self.world_root, seed)
        rng = random.Random(seed)
        W = self.level.W * C.CELL
        D = self.level.H * C.CELL
        start = (W * .5 + rng.uniform(-25, 25), rng.uniform(15, 28), D + C.SHIP_START_DISTANCE * .6)
        self.shuttle = Shuttle(self, start, 180)
        self.inventory = Inventory(self)
        self.inventory_ui = InventoryUI(self)
        self.weapons = Weapons(self)
        self.weapons.show(False)
        self.horror = HorrorManager(self)
        self.player = self.creature = self.aliens = self.director = None
        self.stats = {"kills": 0, "start": self.time, "notes": 0}
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
        self.hud.message("Épave du MNÉMOSYNE en vue. Silence radio depuis 212 jours.", color.rgb(.7, .85, 1))
        self.hud.message("Contourne l'épave et entre dans le hangar (balises rouges / vertes).",
                         color.rgb(.7, .85, 1))

    def _update_tps(self, dt):
        sh = self.shuttle
        sh.update(dt, self.inp, self.exterior.colliders)
        if self.state == "tps" and sh.auto is None and self.exterior.in_hangar_entrance(sh.position):
            self.state = "landing"
            self.hud.message("Hangar atteint — atterrissage automatique", color.lime)
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
        self.audio.play("door_open", .8)

    def _update_fps(self, dt):
        inp = self.inp
        p = self.player
        lt = self.lights
        ui = self.inventory_ui
        # --- inventaire (sans pause) ------------------------------------
        if inp.pressed("inventory") and not ui.reading and not p.hidden:
            ui.toggle()
        ui.update(dt, inp)
        self.ui_consumed = ui.open or ui.reading
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
        self.weapons.update(dt, inp if not self.ui_consumed else self._null)
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
        lt.update(dt, (cp.x, cp.y, cp.z), self.horror.light_level)
        self.space.update(dt)
        self._room_events()
        if inp.debug_overlay:
            cr = self.creature
            inp.debug_overlay.extra = (f"\nCréature : {cr.state}  vue={cr.can_see}\n"
                                       f"Aliens : {len(self.aliens.alive)}  horreur={self.horror.level:.2f}\n"
                                       f"Directrice : pression={self.director.pressure:.2f}")

    def _room_events(self):
        p = self.player
        room = self.level.room_at(p.x, p.z)
        if room is not self.current_room:
            self.current_room = room
            if room is not None and not room.visited:
                room.visited = True
                self.hud.message(room.name.upper(), color.rgb(.6, .75, .8))
                ev = ROOM_EVENTS.get(room.type)
                if ev:
                    strength, text = ev
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
        if not self.has_hdd():
            return "OBJECTIF : récupère le disque dur dans la salle de commandement"
        return "OBJECTIF : retourne au hangar et repars avec la navette"

    def objective_target(self):
        if not self.has_hdd():
            h = self.builder.hdd
            return (h.pos[0], h.pos[2]) if h and not h.taken else None
        p = self.shuttle.root.world_position
        return (p.x, p.z)

    def read_next_note(self):
        inv = self.inventory
        idx = len(inv.notes_read)
        if idx >= len(NOTES):
            self.hud.message("Une note déchirée, illisible.")
            return
        inv.notes_read.append(idx)
        self.stats["notes"] += 1
        title, body = NOTES[idx]
        self.inventory_ui.show_note(title, body)
        self.audio.play("rustle", .7)
        self.hud.message(f"Note ajoutée au journal : {title}", color.rgb(.9, .8, .55))

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
        self.audio.play("hdd_pickup", 1.0)
        self.hud.message("Disque dur récupéré — retourne au hangar !", color.lime)
        # événement scripté : alerte générale, tout le vaisseau se réveille
        invoke(self._hdd_alarm, delay=1.5)

    def _hdd_alarm(self):
        if self.state != "fps":
            return
        self.horror.trigger(None, scripted=True, duration=25)
        cr = self.creature
        if cr.state == "CACHEE":
            cr.hidden_timer = min(cr.hidden_timer, 3)
        else:
            cr.investigate(self.player.x, self.player.z)
        self.aliens.spawn_near_player(2, aware=True)

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
            a.root.enabled = False
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
        sh.start_takeoff(self._victory)
        self.hud.fade_to(0, 1.2)

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

    def _victory(self):
        self.state = "victory"
        mouse.locked = False
        t = self.time - self.stats["start"]
        sub = (f"Tu as quitté l'épave avec le disque dur.\n"
               f"Temps : {int(t // 60)} min {int(t % 60)} s   —   Créatures tuées : {self.stats['kills']}   —   "
               f"Notes : {self.stats['notes']}/{len(NOTES)}")
        self._set_screen(MenuScreen("ÉCHAPPÉ", sub, ["Nouvelle partie", "Menu principal", "Quitter"],
                                    self._end_select, title_color=color.rgb(.6, 1, .7), bg_alpha=.5))

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
            sub = "La navette s'est disloquée contre l'épave."
        else:
            self.audio.play("death_sting", .7, .8)
            self.hud.fade_to(1, 1.2)
            sub = "Les parasites t'ont submergé."
        self.audio.stop_all_loops()
        invoke(self._show_gameover, sub, delay=1.6)

    def _show_gameover(self, sub):
        if self.inventory_ui:
            self.inventory_ui.hide_all()
        mouse.locked = False
        self.hud.set_mode("none")
        self._set_screen(MenuScreen("TU ES MORT", sub, ["Réessayer (même épave)", "Nouvelle épave",
                                                         "Menu principal"], self._end_select,
                                    title_color=color.rgb(.9, .15, .1), bg_alpha=.2))

    def _end_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt.startswith("Réessayer"):
            self.new_game(self.seed)
        elif opt in ("Nouvelle épave", "Nouvelle partie"):
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
            self._set_screen(MenuScreen("PAUSE", f"seed {self.seed}", ["Reprendre", "Recommencer", "Menu principal",
                                                                      "Quitter"], self._pause_select, bg_alpha=.6))
        else:
            self._set_screen(None)
            mouse.locked = True

    def _pause_select(self, opt):
        self.audio.play("ui_select", .6)
        if opt == "Reprendre":
            self.toggle_pause()
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
        self.inp.update(dt, mouse_look=playing and not self.paused)
        if playing and self.inp.pressed("pause"):
            if self.inventory_ui and (self.inventory_ui.open or self.inventory_ui.reading) and not self.paused:
                self.inventory_ui.hide_all()
            else:
                self.toggle_pause()
        if self.screen:
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
        self.hud.update(dt)
        self.inp.end_frame()


def run():
    global game
    game = Game()
    app.run()


if __name__ == "__main__":
    run()
