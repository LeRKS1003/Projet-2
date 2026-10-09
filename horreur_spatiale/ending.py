# -*- coding: utf-8 -*-
"""
ending.py — Cinématique de fin (le joueur rejoint la navette avec le disque dur).

  1. fondu au noir court, vue du cockpit : mains sur les commandes, écrans
     qui s'allument, bruit des moteurs ;
  2. caméra externe : la navette décolle, se retourne lentement et sort du
     hangar ; les portes du hangar s'ouvrent en arrière-plan sous les
     lumières rouges ;
  3. plans cinématiques successifs (barres noires en haut et en bas, sans
     contrôle du joueur) : la navette qui s'éloigne, le Kerguelen immense et
     sombre qui dérive, quelques hublots qui clignotent encore, les planètes
     au loin ;
  4. message : « Cap sur la station Helios. Passagers à bord : 1. » ;
  5. retour au cockpit : dans le reflet de la verrière, une fraction de
     seconde, deux points blancs derrière le joueur. Bourdonnement à 7 Hz.
     Noir ;
  6. titre « DÉRIVE », crédits sobres qui défilent, documents retrouvés.

Musique générée par code (audio.gen_late) : nappes graves et lentes qui
montent jusqu'au moment du reflet. On peut passer la cinématique en
maintenant Croix / Espace.
"""
import math
import random

from panda3d.core import PointLight, Vec4
from panda3d.core import Vec3 as PVec3
from ursina import Entity, Text, camera, color, destroy, Vec3, application, window

import config as C
import story
from lighting import mark_emissive

# chronologie (secondes depuis le début de la cinématique)
T_COCKPIT = 0.0          # cockpit : démarrage
T_TAKEOFF = 7.0          # caméra dans le hangar : décollage, demi-tour, sortie
T_LIFT_END = 9.0
T_TURN_END = 15.0
T_OUT = 15.0             # la navette accélère vers l'ouverture
T_SHOT_EXIT = 18.0       # plan extérieur : la navette jaillit du hangar
T_SHOT_AWAY = 23.0       # la navette s'éloigne vers les planètes
T_SHOT_WIDE = 29.0       # le Kerguelen immense qui dérive
T_MESSAGE = 30.5
T_COCKPIT2 = 36.0        # retour au cockpit, reflet
T_EYES = 39.4            # les deux points blancs (une fraction de seconde)
T_BLACK = 39.8
T_TITLE = 41.5
T_CREDITS = 46.0


def _build_hands(parent):
    """Deux mains gantées posées sur les commandes (combinaison sombre, gants renforcés)."""
    root = Entity(parent=parent)
    suit = color.rgb(.17, .18, .2)
    glove = color.rgb(.1, .1, .11)
    pad = color.rgb(.55, .36, .12)
    for side in (-1, 1):
        h = Entity(parent=root, position=(side * .24, .86, 1.66), rotation=(12, side * -8, side * 6))
        # manche de la combinaison, qui remonte vers le pilote
        Entity(parent=h, model='sphere', color=suit, scale=(.12, .11, .42), position=(side * .03, .03, -.24))
        Entity(parent=h, model='sphere', color=pad, scale=(.13, .03, .07), position=(side * .02, .07, -.08))
        # paume
        Entity(parent=h, model='sphere', color=glove, scale=(.1, .05, .11))
        # quatre doigts repliés sur la manette + pouce
        for k in range(4):
            x = -.033 + k * .022
            Entity(parent=h, model='sphere', color=glove, scale=(.022, .03, .06), position=(x, -.01, .065),
                   rotation_x=35)
        Entity(parent=h, model='sphere', color=glove, scale=(.025, .03, .055), position=(-side * .055, .01, .03),
               rotation_y=side * 40)
        # manette des gaz / manche
        Entity(parent=root, model='cube', color=color.rgb(.12, .12, .13), scale=(.04, .12, .04),
               position=(side * .24, .78, 1.69))
    return root


class HangarDoors:
    """Grandes portes du hangar (deux vantaux) : fermées après l'atterrissage, ouvertes pour le départ."""

    def __init__(self, game):
        self.game = game
        ex = game.exterior
        self.x0, self.x1 = ex.open_x0, ex.open_x1
        self.h = ex.open_h
        w = (self.x1 - self.x0) / 2 + .4
        self.w = w
        self.root = Entity(parent=game.world_root, name="hangar_doors")
        self.leaves = []
        for side in (-1, 1):
            leaf = Entity(parent=self.root)
            Entity(parent=leaf, model='cube', texture='white_cube', color=color.rgb(.26, .27, .29),
                   scale=(w, self.h + .6, .35))
            # bandes de danger au bord qui se rejoint + renforts
            Entity(parent=leaf, model='cube', color=color.rgb(.8, .62, .08),
                   scale=(.35, self.h + .6, .37), x=-side * (w / 2 - .18))
            for k in range(4):
                Entity(parent=leaf, model='cube', color=color.rgb(.2, .2, .22),
                       scale=(w * .9, .18, .4), y=-self.h / 2 + .8 + k * (self.h / 3.4))
            self.leaves.append((leaf, side))
        # feux rouges au-dessus de l'ouverture (sur batterie, ils brillent sans éclairer)
        self.beacons = []
        for x in (self.x0 + 1.0, (self.x0 + self.x1) / 2, self.x1 - 1.0):
            b = Entity(parent=self.root, model='sphere', color=color.rgb(.3, .02, .02), scale=.4,
                       position=(x, self.h + .7, .6))
            mark_emissive(b)
            self.beacons.append(b)
        self.light = None
        self.open_k = 0.0          # 0 fermé, 1 ouvert
        self.target = 0.0
        self.t = 0.0
        self._layout()

    def _layout(self):
        cx = (self.x0 + self.x1) / 2
        z = -.55
        y = self.h / 2 - .1
        for leaf, side in self.leaves:
            # fermé : les deux vantaux se rejoignent au centre ; ouvert : ils rentrent dans la coque
            x = cx + side * (self.w / 2) + side * self.open_k * (self.w + .3)
            leaf.position = (x, y, z)

    def close(self, instant=False):
        self.target = 0.0
        if instant:
            self.open_k = 0.0
            self._layout()

    def open(self):
        self.target = 1.0

    def set_alarm(self, on):
        """Gyrophares rouges pendant le départ (une vraie lumière rouge qui balaie le hangar)."""
        render = application.base.render
        if on and self.light is None:
            pl = PointLight("hangar_alarm")
            pl.setAttenuation(PVec3(1, 0, .004))
            pl.setColor(Vec4(0, 0, 0, 1))
            self.light = render.attachNewNode(pl)
            self.light.setPos((self.x0 + self.x1) / 2, self.h + .4, 3.0)     # au-dessus de l'ouverture, côté hangar
            render.setLight(self.light)
        elif not on and self.light is not None:
            render.clearLight(self.light)
            self.light.removeNode()
            self.light = None

    def update(self, dt):
        self.t += dt
        if abs(self.target - self.open_k) > 1e-3:
            step = dt / 5.0
            self.open_k += max(-step, min(step, self.target - self.open_k))
            self._layout()
        if self.light is not None:
            k = max(0.0, math.sin(self.t * 5.0)) ** 2
            self.light.node().setColor(Vec4(2.2 * k, .08 * k, .04 * k, 1))
            for i, b in enumerate(self.beacons):
                kk = max(0.0, math.sin(self.t * 5.0 + i * .9)) ** 2
                b.color = color.rgb(.3 + .7 * kk, .02, .02)

    def destroy(self):
        self.set_alarm(False)
        destroy(self.root)


class EndingCinematic:
    def __init__(self, game):
        self.game = game
        self.t = 0.0
        self.flags = set()
        self.done = False
        self.started = False
        self.skip_hold = 0.0
        sh = game.shuttle
        self.sh = sh
        ld = game.builder.landing
        self.pad = ld["pad"]
        self.rest_y = ld["rest_y"]
        self.yaw0 = ld["yaw"]
        self.exit_pos = None
        self.hidden = []
        # interface : barres noires, titre, crédits, indication pour passer
        ui = camera.ui
        ar = window.aspect_ratio
        self.bar_top = Entity(parent=ui, model='quad', color=color.black, scale=(ar * 1.1, .13),
                              position=(0, .5 + .065), z=-16)
        self.bar_bot = Entity(parent=ui, model='quad', color=color.black, scale=(ar * 1.1, .13),
                              position=(0, -.5 - .065), z=-16)
        self.bars = 0.0
        self.title = Text(parent=ui, text=story.GAME_TITLE, origin=(0, 0), scale=5.5, position=(0, .05),
                          color=color.rgba(.9, .92, .95, 0), z=-21)
        self.credits = Text(parent=ui, text=self._credits_text(), origin=(0, .5), scale=1.0,
                            position=(0, -.6), color=color.rgba(.8, .83, .86, 0), z=-21)
        n_lines = self.credits.text.count("\n") + 1
        self.credits_time = (n_lines * .032 + .75) / C.ENDING_CREDITS_SPEED
        self.skip_text = Text(parent=ui, text="Maintenir Espace / Croix pour passer", origin=(.5, 0), scale=.7,
                              position=(ar / 2 - .03, -.47), color=color.rgba(1, 1, 1, 0), z=-21)
        self.hands = None
        self.cockpit_light = None
        self.music = None

    # ------------------------------------------------------------------
    def _credits_text(self):
        g = self.game
        n = len(g.docs.found) if g.docs else 0
        total = g.docs.total if g.docs else len(story.DOCUMENTS)
        crew = "\n".join(c["name"] for c in story.CREW.values())
        return (f"{story.GAME_TITLE}\n\n"
                "Une histoire d'horreur spatiale\n\n\n"
                "ÉQUIPAGE DU KERGUELEN\n\n"
                f"{crew}\n\n\n"
                "Tout est généré par le code :\n"
                "le vaisseau, les textures, les sons, la musique.\n\n"
                "Moteur : Ursina / Panda3D\n\n\n"
                f"Documents retrouvés : {n}/{total}\n\n\n"
                f"{story.ENDING_CAPTION}\n\n\n"
                "Merci d'avoir joué.")

    # ------------------------------------------------------------------
    def start(self):
        """Appelé une fois le fondu au noir terminé."""
        g = self.game
        self.started = True
        sh = self.sh
        g.inventory_ui.hide_all()
        g.weapons.show(False)
        g.lights.flashlight_on = False
        g.lights.set_nightvision(False)
        if g.creature is not None:
            g.creature.root.enabled = False
        for a in g.aliens.aliens:
            a.root.hide()
        g.hallu.hide_all()
        g.revelation.finish()
        g.reader.close()
        g.journal.close()
        g.hud.set_mode("none")
        g.hud.messages = []                 # aucun message du HUD pendant la cinématique
        g.horror.level = 0
        g.horror.timer = 0
        g.horror.update(0.01)
        g.audio.reset()
        g.audio.stop_all_loops()
        # navette à sa place exacte, prête à décoller
        sh.snap_to_pad(g.builder.landing)
        sh.throttle = 0.0
        # boucles des moteurs (coupées avec le reste) : muettes tant que la navette est « posée »
        sh.engine_snd = g.audio.loop("ship_engine", "ship_engine", .8)
        sh.boost_snd = g.audio.loop("ship_boost", "ship_boost", .6)
        self.hands = _build_hands(sh.model)
        # lueur des écrans dans le cockpit
        pl = PointLight("cockpit_glow")
        pl.setAttenuation(PVec3(1, 0, 6))
        pl.setColor(Vec4(0, 0, 0, 1))
        self.cockpit_light = sh.model.attachNewNode(pl)
        self.cockpit_light.setPos(0, 1.1, 1.95)            # juste au-dessus du tableau de bord
        application.base.render.setLight(self.cockpit_light)
        sh.dash.setColorScale(.08, .08, .09, 1)
        self._cockpit_view(True)
        self.music = g.audio.play("ending_music", .95, music=True, ignore_duck=True)
        # direction d'une planète du ciel (la navette mettra le cap dessus)
        self.planet_dir = (0.0, 0.0, -1.0)
        try:
            pl_ = g.space.planets[-1]
            v = pl_.getPos(g.space.root)
            n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
            if v[2] / n < .3:                 # une planète vers l'avant (pas derrière le Kerguelen)
                self.planet_dir = (v[0] / n, v[1] / n, v[2] / n)
            else:
                for pl_ in g.space.planets:
                    v = pl_.getPos(g.space.root)
                    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
                    if v[2] / n < .3:
                        self.planet_dir = (v[0] / n, v[1] / n, v[2] / n)
                        break
        except Exception:
            pass
        g.hud.fade_to(0, .8)

    def _cockpit_view(self, on):
        """Dans le cockpit : on masque la coque (la caméra est dedans), on garde tableau de bord et mains."""
        sh = self.sh
        if on:
            self.hidden = []
            for c in sh.model.getChildren():
                if c != sh.dash and c != self.hands and not c.isHidden() and c != self.cockpit_light:
                    c.hide()
                    self.hidden.append(c)
            sh.fx_root.hide()
        else:
            for c in self.hidden:
                c.show()
            self.hidden = []
            sh.fx_root.show()

    # ------------------------------------------------------------------
    def _shuttle_motion(self, t, dt):
        """Trajectoire de la navette : décollage, demi-tour lent, sortie du hangar, départ vers les planètes."""
        sh = self.sh
        px, pz = self.pad
        if t < T_TAKEOFF:
            sh.throttle = .12 if t > 2.2 else 0.0
            sh._visuals(dt)
            return
        if t < T_LIFT_END:
            k = (t - T_TAKEOFF) / (T_LIFT_END - T_TAKEOFF)
            k = k * k * (3 - 2 * k)
            sh.root.position = (px, self.rest_y + (4.2 - self.rest_y) * k, pz)
            sh._update_gear(1 - k)
            sh.throttle = .5
            sh.in_vert = .6
        elif t < T_TURN_END:
            # demi-tour lent (le nez vers l'ouverture du hangar), léger roulis
            k = (t - T_LIFT_END) / (T_TURN_END - T_LIFT_END)
            e = k * k * (3 - 2 * k)
            sh.root.position = (px, 4.2 + math.sin(t * 1.3) * .08, pz)
            sh.root.rotation = (0, self.yaw0 + 180 * e, math.sin(k * math.pi) * 6)
            sh.throttle = .4
            sh.in_vert = 0.0
            sh.in_strafe = .4 * math.sin(k * math.pi)
        else:
            if self.exit_pos is None:
                self.exit_pos = Vec3(px, 4.2, pz)
                self.exit_speed = 0.0
            # accélération vers -z (l'ouverture), puis cap légèrement vers les planètes
            self.exit_speed = min(46.0, self.exit_speed + dt * (4.0 if t < T_SHOT_AWAY else 12.0))
            fwd = sh.root.forward
            sh.root.position = sh.root.position + fwd * self.exit_speed * dt
            if t > T_SHOT_EXIT + 1.5:
                # cap progressif vers une planète lointaine (elle apparaît derrière la navette à l'image)
                d = self.planet_dir
                ty = math.degrees(math.atan2(d[0], d[2]))
                tp = -math.degrees(math.asin(max(-.6, min(.6, d[1]))))
                k = min(1.0, dt * .35)
                dy = (ty - sh.root.rotation_y + 180) % 360 - 180
                sh.root.rotation_y += dy * k
                sh.root.rotation_x += (tp - sh.root.rotation_x) * k
            sh.throttle = 1.2 if t < T_SHOT_EXIT + 2 else 1.6
            sh.boosting = t > T_SHOT_EXIT + 2
            sh.in_strafe = 0.0
        sh._visuals(dt)

    def _look(self, cam, target):
        camera.position = cam
        camera.lookAt(PVec3(target[0], target[1], target[2]), PVec3(0, 1, 0))

    # ------------------------------------------------------------------
    def update(self, dt):
        g = self.game
        sh = self.sh
        self.t += dt
        t = self.t
        f = self.flags
        inp = g.inp
        # --- passer la cinématique (maintenir Croix / Espace) -----------------
        holding = inp.held("confirm") or inp._kb_held("space") or inp.pad.held("cross")
        self.skip_hold = self.skip_hold + dt if holding else max(0.0, self.skip_hold - dt * 2)
        a = min(1.0, .35 + self.skip_hold / C.ENDING_SKIP_HOLD) if (t > 1.0 and t < T_CREDITS + 30) else 0.0
        self.skip_text.color = color.rgba(1, 1, 1, .35 * a if self.skip_hold <= 0 else .9)
        self.skip_text.text = ("Maintenir Espace / Croix pour passer" if self.skip_hold <= 0
                               else f"Passer... {int(min(1, self.skip_hold / C.ENDING_SKIP_HOLD) * 100)} %")
        if self.skip_hold >= C.ENDING_SKIP_HOLD:
            self.finish()
            return
        # --- décor vivant ----------------------------------------------------------
        g.space.update(dt)
        g.exterior.update(dt)
        if g.hangar_doors is not None:
            g.hangar_doors.update(dt)
        self._shuttle_motion(t, dt)
        cp = camera.world_position
        g.lights.update(dt, (cp.x, cp.y, cp.z), 0)
        g.builder.update(dt, [], (cp.x, cp.y, cp.z), fps_mode=False)
        # --- barres noires (plans cinématiques) ------------------------------
        want_bars = 1.0 if T_TAKEOFF <= t < T_BLACK else 0.0
        self.bars += (want_bars - self.bars) * min(1.0, dt * 2.5)
        self.bar_top.y = .5 + .065 - .13 * self.bars
        self.bar_bot.y = -.5 - .065 + .13 * self.bars
        # --- 1. COCKPIT : mains sur les commandes, écrans qui s'allument ---------
        if t < T_TAKEOFF:
            # tête du pilote : on regarde vers le bas le tableau de bord et les mains, la verrière au-dessus
            cam = sh._local_to_world((0, 1.22, 1.42))
            ahead = sh._local_to_world((0, .3, 3.4))
            camera.position = cam
            camera.lookAt(ahead)
            camera.fov = 80
            if t > .3 and "start_snd" not in f:
                f.add("start_snd")
                g.audio.play("cockpit_start", 1.0, ignore_duck=True)
                g.inp.rumble(.3, .2, 400)
            if t > 1.3 and "screens" not in f:
                f.add("screens")
                g.audio.play("screens_on", .9, ignore_duck=True)
            if t > 1.3:
                k = min(1.0, (t - 1.3) / .8)
                fl = 1.0 if k >= 1 or random.random() > .35 else .3
                v = .08 + .92 * k * fl
                sh.dash.setColorScale(v, v, v * 1.05, 1)
                self.cockpit_light.node().setColor(Vec4(.25 * v, .45 * v, .55 * v, 1))
            if t > 2.2 and "engine" not in f:
                f.add("engine")
                sh.landed = False                  # les moteurs démarrent (son géré par la navette)
                g.inp.rumble(.5, .3, 900)
            if t > 2.2:
                g.shake(.05)
        # --- 2. DÉCOLLAGE : caméra dans le hangar ---------------------------------
        elif t < T_SHOT_EXIT:
            if "takeoff" not in f:
                f.add("takeoff")
                self._cockpit_view(False)
                self.hands.enabled = False
                application.base.render.setLight(sh.spot_np)
                application.base.render.setLight(sh.eng_np)
                g.hangar_doors.set_alarm(True)
                g.audio.play("alarm", .5)
                g.lights.set_mode("tps")
                g.lights.set_sun(-g.space.sun_dir, True)
                g.space.set_dust(True)
                g.exterior.set_enabled(True)
                g.builder.show_only({g.level.room("hangar").id})
                camera.fov = 62
            if t > T_TAKEOFF + 1.2 and "doors" not in f:
                f.add("doors")
                g.hangar_doors.open()
                g.audio.play("hangar_doors", 1.0, ignore_duck=True)
                g.inp.rumble(.6, .4, 1200)
            hx0, hx1, hz0, hz1 = g.level.room("hangar").world_bounds()
            # caméra au fond du hangar, en hauteur, qui suit la navette (les portes derrière elle)
            cam = Vec3(self.pad[0] + 7.5, 7.0, hz1 - 2.5)
            p = sh.root.world_position
            look = Vec3(p.x, p.y + .5, p.z - 2.0)
            self._look(cam, look)
        # --- 3a. SORTIE DU HANGAR (plan extérieur) --------------------------------
        elif t < T_SHOT_AWAY:
            if "exit" not in f:
                f.add("exit")
                g.audio.play("ship_boost", .8)
                ex = g.exterior
                cx = (ex.open_x0 + ex.open_x1) / 2
                # loin devant l'ouverture : la navette jaillit du hangar, la coque immense derrière elle
                self.cam_exit = Vec3(cx - 24, ex.open_h + 7, -80)
            p = sh.root.world_position
            self._look(self.cam_exit, (p.x, p.y, p.z))
            camera.fov = 55
        # --- 3b. LA NAVETTE S'ÉLOIGNE (vers les planètes) --------------------------
        elif t < T_SHOT_WIDE:
            if "away" not in f:
                f.add("away")
                p = sh.root.world_position
                d = self.planet_dir
                # derrière la navette, un peu sur le côté : la planète est devant elle, à l'image
                self.cam_away = Vec3(p.x - d[0] * 30 + 10, p.y - d[1] * 30 + 6, p.z - d[2] * 30)
                g.hangar_doors.set_alarm(False)
            p = sh.root.world_position
            k = (t - T_SHOT_AWAY)
            cam = self.cam_away + Vec3(0, k * .3, 0)
            self._look(cam, (p.x, p.y, p.z))
            camera.fov = 50
        # --- 3c. LE KERGUELEN, IMMENSE ET SOMBRE, QUI DÉRIVE ----------------------
        elif t < T_COCKPIT2:
            if "wide" not in f:
                f.add("wide")
                g.audio.stop_loop("ship_engine")
                g.audio.stop_loop("ship_boost")
                g.audio.play("static_burst", .4)
                # le vaisseau mort, sombre : seuls ses hublots et balises brillent encore
                g.exterior.root.setColorScale(.45, .46, .52, 1)
            W = g.level.W * C.CELL
            D = g.level.H * C.CELL
            ship = Vec3(W / 2, 4, D / 2)
            k = (t - T_SHOT_WIDE) / (T_COCKPIT2 - T_SHOT_WIDE)
            ang = math.radians(200 + 25 * k)
            dist = 150 + 30 * k
            cam = ship + Vec3(math.sin(ang) * dist, 38 - 10 * k, math.cos(ang) * dist)
            self._look(cam, (ship.x, ship.y - 6 * k, ship.z))
            camera.fov = 48
            # quelques hublots clignotent encore
            if random.random() < dt * 3:
                g.audio.play("beep", .05, .6)
            if t > T_MESSAGE and "msg" not in f:
                f.add("msg")
                g.audio.play("static_burst", .6)
                g.hud.center_text.text = story.ENDING_SHUTTLE_MESSAGE
            if t > T_MESSAGE + 4.6:
                g.hud.center_text.text = ""
        # --- 5. RETOUR AU COCKPIT : le reflet -----------------------------------
        elif t < T_TITLE:
            if "cockpit2" not in f:
                f.add("cockpit2")
                g.hud.center_text.text = ""
                self._cockpit_view(True)
                self.hands.enabled = True
                self.hum = g.audio.loop("sinus_end", "sinus_chant", 1.0, ambient=True)
                self.hum.set(.3, fade=.5)
                camera.fov = 72
            if t < T_BLACK:
                cam_p = sh._local_to_world((0, 1.28, 1.36))
                ahead = sh._local_to_world((0, -3.0, 40))
                camera.position = cam_p
                camera.lookAt(ahead)
                refl = min(.24, (t - T_COCKPIT2) * .1)
                # ses yeux, dans le reflet : un instant, puis un second éclat plus faible
                eyes = 1.0 if T_EYES <= t < T_EYES + .3 else (.45 if T_EYES + .55 <= t < T_EYES + .65 else 0.0)
                if t >= T_EYES and "sting" not in f:
                    f.add("sting")
                    g.audio.play("creature_sting", .7, .9, ignore_duck=True)
                g.hud.set_reflection(refl, eyes)
                if t > T_EYES - .6 and "swell" not in f:
                    f.add("swell")
                    g.audio.play("sinus_swell", 1.0, ignore_duck=True)
                    self.hum.set(1.0, fade=2.0)
                    g.inp.rumble(.4, .8, 1200)
            elif "black" not in f:
                f.add("black")
                g.hud.set_fade(1)
                g.hud.set_reflection(0.0)
                g.audio.stop_all_loops()
                if self.music is not None:
                    self.music.stop()
        # --- 6. TITRE PUIS CRÉDITS ------------------------------------------------
        else:
            if "title" not in f:
                f.add("title")
                g.audio.play("credits_music", .8, music=True, ignore_duck=True)
            ta = t - T_TITLE
            a = min(1.0, ta / 1.5) * (1.0 if t < T_CREDITS - .5 else max(0.0, 1 - (t - T_CREDITS + .5) / 1.2))
            self.title.color = color.rgba(.9, .92, .95, a)
            if t >= T_CREDITS:
                tc = t - T_CREDITS
                self.credits.color = color.rgba(.8, .83, .86, min(1.0, tc / 1.5))
                self.credits.y = -.6 + tc * C.ENDING_CREDITS_SPEED
                # fin du défilement : la dernière ligne est passée au-dessus du centre
                if tc > self.credits_time:
                    self.finish()

    # ------------------------------------------------------------------
    def finish(self):
        """Fin (ou cinématique passée) : écran final avec le nombre de documents."""
        if self.done:
            return
        self.done = True
        g = self.game
        g.hud.set_reflection(0.0)
        g.hud.center_text.text = ""
        g.hud.set_fade(1)
        g.audio.stop_all_loops()
        if self.music is not None:
            self.music.stop()
        self.cleanup()
        g._final_screen()

    def cleanup(self):
        for e in (self.bar_top, self.bar_bot, self.title, self.credits, self.skip_text):
            destroy(e)
        if self.hands is not None:
            destroy(self.hands)
            self.hands = None
        if self.cockpit_light is not None:
            application.base.render.clearLight(self.cockpit_light)
            self.cockpit_light.removeNode()
            self.cockpit_light = None
        self._cockpit_view(False)
