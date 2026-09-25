# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée de DÉRIVE, boucle de jeu et états (menu, jeu, pause,
game over, victoire).

Objectif : rétablir le courant dans la salle des machines, récupérer le code
d'accès dans la salle de commandement, puis fuir en navette depuis le hangar.
"""
import math
import os
import random
import sys
import time   # Ursina ajoute time.dt (durée de la dernière image) au module standard

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

import config as C
from controller import Manette          # importé avant Ursina : prépare SDL pour la manette

from panda3d.core import AntialiasAttrib, loadPrcFileData

if C.ANTICRENELAGE:
    loadPrcFileData("", f"framebuffer-multisample 1\nmultisamples {int(C.ANTICRENELAGE)}")
loadPrcFileData("", "audio-library-name p3openal_audio")

from ursina import (Entity, Text, Ursina, Vec3, application, camera, color, destroy, invoke, mouse,
                    window)

from audio import GestionnaireAudio
from creature import Creature, Directrice
from generator import generer_vaisseau
from hud import HUD
from lighting import Eclairage
from player import Joueur
from rooms import decorer
from space import Espace
from world import Monde

MENU, CHARGEMENT, JEU, PAUSE, MORT, VICTOIRE = "menu", "chargement", "jeu", "pause", "mort", "victoire"

OBJECTIFS = [
    "Rétablir le courant  —  salle des machines",
    "Récupérer le code d'accès  —  salle de commandement",
    "Fuir  —  rejoindre la navette dans le hangar",
]

AIDE_CONTROLES = ("Clavier : ZQSD déplacement · Maj courir · Ctrl s'accroupir · F lampe · clic droit lampe concentrée · "
                  "E interagir · Tab carte · Échap pause · F3 debug\n"
                  "Manette : stick G déplacement · stick D regard · L3 courir · R3/Rond s'accroupir · Croix interagir · "
                  "Carré lampe · R2 lampe concentrée · pavé tactile carte · Options pause")


class Jeu(Entity):
    def __init__(self):
        super().__init__(name="jeu", eternal=True)
        self.etat = MENU
        self.manette = Manette()
        self.audio = GestionnaireAudio(DOSSIER)
        self.hud = HUD()
        self.eclairage = Eclairage()
        self.espace = Espace(seed=random.randrange(10 ** 6))
        self.seed = C.SEED if C.SEED is not None else random.randrange(1, 10 ** 6)
        self.monde = None
        self.joueur = None
        self.creature = None
        self.directrice = None
        self.fps_txt = Text(parent=camera.ui, text="", position=(window.aspect_ratio / 2 - 0.12, 0.48), scale=0.8,
                            color=color.rgb(0.6, 0.9, 0.6), enabled=C.AFFICHER_FPS)
        self.debug = False
        self.t_evenement = 0.0
        self.coeur_timer = 0.0
        self.refus_timer = 0.0
        self.ambiance = None
        self.menu()

    # ------------------------------------------------------------------
    # Écrans
    # ------------------------------------------------------------------
    def menu(self):
        self.detruire_partie()
        self.etat = MENU
        mouse.locked = False
        mouse.visible = True
        camera.position = Vec3(0, 0, 0)
        camera.rotation = Vec3(0, 0, 0)
        self.hud.afficher_jeu(False)
        self.hud.ecran(
            "D É R I V E",
            "Vous vous réveillez seul à bord d'un vaisseau à la dérive. Quelque chose rôde dans les couloirs et les conduits.",
            f"ENTRÉE / Croix : nouvelle partie\nN : changer de vaisseau   (seed {self.seed})\nÉchap : quitter",
            AIDE_CONTROLES,
            noir=0.35,
        )

    def lancer(self, seed=None):
        if seed is not None:
            self.seed = seed
        self.detruire_partie()
        self.etat = CHARGEMENT
        self.hud.ecran("", "", "Génération du vaisseau...", "", noir=0.85)
        invoke(self._construire, delay=0.15)

    def _construire(self):
        t0 = time.time()
        random.seed(self.seed)
        vaisseau = generer_vaisseau(self.seed)
        self.monde = Monde(vaisseau, self.audio)
        infos = decorer(self.monde, self.eclairage, self.seed)
        self.infos = infos
        self.audio.occlusion = self.monde.ligne_de_vue
        # interactifs d'objectifs
        from world import Interactif
        self.console_courant = Interactif(infos["console_courant"], "console_courant", "Relancer le réacteur", rayon=2.2)
        self.terminal = Interactif(infos["terminal"], "terminal", "Consulter le terminal de commandement", rayon=2.2)
        self.navette = Interactif(infos["navette"], "navette", "Monter dans la navette", rayon=2.6)
        self.monde.interactifs += [self.console_courant, self.terminal, self.navette]
        # joueur
        p = infos["apparition"]
        s = infos["salle_depart"]
        porte = vaisseau.pont.portes[s.portes[0]]
        cx, cz = porte.centre
        lacet = math.degrees(math.atan2(cx - p.x, cz - p.z))
        self.joueur = Joueur(self.monde, self.manette, self.audio, Vec3(p.x, 0, p.z), lacet)
        # créature : dans un conduit loin du joueur
        cases = [c for c in self._cases_conduit(vaisseau)] or [(int(p.x), int(p.z))]
        cases.sort(key=lambda c: -((c[0] - p.x) ** 2 + (c[1] - p.z) ** 2))
        self.creature = Creature(self.monde, self.audio, cases[0])
        self.directrice = Directrice(self.creature, self.monde, self.audio)
        # sons d'ambiance
        self.ambiance = self.audio.boucle("ambiance", None, volume=0.55)
        m = vaisseau.pont.salle_de_type("machines")[0]
        self.pos_machines = Vec3(m.centre[0], 2.0, m.centre[1])
        self.reacteur = self.audio.boucle("reacteur", self.pos_machines, volume=0.25, portee=38)
        self.alarme = self.audio.boucle("alarme", self.pos_machines, volume=0.3, portee=30)
        self.bourdon = self.audio.boucle("neon", Vec3(0, -100, 0), volume=0.35, portee=8)
        self.bourdon_timer = 0.0
        # état de la partie
        self.etape = 0
        self.temps = 0.0
        self.hud.preparer_carte(vaisseau.pont)
        self.hud.carte_joueur.scale = (0.022 * vaisseau.pont.profondeur / vaisseau.pont.largeur, 0.022)
        self.hud.carte_obj.scale = (0.028 * vaisseau.pont.profondeur / vaisseau.pont.largeur, 0.028)
        self.hud.objectif.text = OBJECTIFS[0]
        self.hud.afficher_jeu(True)
        self.hud.ecran(noir=0.0)
        self.hud.alpha_noir = 1.0
        self.hud.vider_messages()
        self.hud.message("...Où suis-je ? Le vaisseau est silencieux. Trop silencieux.", 5)
        self.hud.message("Trouvez la salle des machines et rétablissez le courant.", 5)
        mouse.locked = True
        mouse.visible = False
        self.etat = JEU
        print(f"Vaisseau {self.seed} généré en {time.time() - t0:.2f} s "
              f"({len(vaisseau.pont.salles)} salles, {len(vaisseau.pont.portes)} portes, "
              f"{len(vaisseau.pont.grilles)} grilles, {len(self.eclairage.sources)} lumières)")

    @staticmethod
    def _cases_conduit(vaisseau):
        from generator import CONDUIT
        p = vaisseau.pont
        return [(i, j) for i in range(p.largeur) for j in range(p.profondeur) if p.type[i, j] == CONDUIT]

    def detruire_partie(self):
        self.audio.tout_arreter()
        self.manette.arreter_vibrations()
        if self.joueur is not None:
            camera.parent = self.espace.parent
            destroy(self.joueur)
            self.joueur = None
        if self.creature is not None:
            destroy(self.creature)
            self.creature = None
        if self.monde is not None:
            self.monde.detruire()
            self.monde = None
        self.eclairage.vider()
        self.hud.afficher_jeu(False)
        self.hud.vider_messages()

    def pause(self, active):
        if active and self.etat == JEU:
            self.etat = PAUSE
            mouse.locked = False
            mouse.visible = True
            self.manette.arreter_vibrations()
            self.hud.ecran("PAUSE", OBJECTIFS[self.etape],
                           "Échap / Options : reprendre\nM / Triangle : retour au menu", AIDE_CONTROLES, noir=0.6)
        elif not active and self.etat == PAUSE:
            self.etat = JEU
            mouse.locked = True
            mouse.visible = False
            self.hud.ecran(noir=0.0)

    def mourir(self):
        self.etat = MORT
        j, c = self.joueur, self.creature
        # la créature surgit face au joueur
        ang = math.atan2(c.x - j.x, c.z - j.z)
        j.lacet = math.degrees(ang)
        j.tangage = -12
        if j.cache is not None:
            j.cache.entrouvrir(2.0)
        c.position = Vec3(j.x + math.sin(ang) * 0.75, 0, j.z + math.cos(ang) * 0.75)
        c.rotation_y = j.lacet + 180
        c.visible = True
        j.secouer(1.0)
        j._finir_tick(0.016, 0)
        self.audio.tout_arreter()
        self.audio.jouer("cri", volume=1.0)
        self.manette.vibrer(1.0, 1.0, 900)
        self.hud.afficher_jeu(False)
        mouse.locked = False
        invoke(self._ecran_mort, delay=0.45)

    def _ecran_mort(self):
        if self.etat != MORT:
            return
        self.hud.alpha_noir = 1.0
        self.hud.ecran("VOUS ÊTES MORT", "Elle vous a trouvé.",
                       "ENTRÉE / Croix : recommencer (même vaisseau)\nN : nouveau vaisseau\nÉchap / Rond : menu",
                       "", noir=1.0)
        mouse.visible = True

    def victoire(self):
        self.etat = VICTOIRE
        self.audio.tout_arreter()
        self.audio.jouer("navette", volume=1.0)
        self.manette.vibrer(0.8, 0.3, 2500)
        self.hud.afficher_jeu(False)
        minutes, secondes = divmod(int(self.temps), 60)
        mouse.locked = False
        mouse.visible = True
        self.hud.ecran("VOUS AVEZ FUI", f"La navette se détache du vaisseau en perdition. Temps : {minutes} min {secondes:02d} s.",
                       "ENTRÉE / Croix : menu principal\nN : nouveau vaisseau", "", noir=0.92)

    # ------------------------------------------------------------------
    # Objectifs et interactions
    # ------------------------------------------------------------------
    def interagir(self, obj):
        j = self.joueur
        g = obj.genre
        if g == "grille":
            obj.donnees.ouvrir()
        elif g == "casier":
            j.se_cacher(obj.donnees)
            self.hud.message("Vous retenez votre souffle...", 2.5)
        elif g == "pile":
            j.recharger(C.BATTERIE_PILE)
            obj.actif = False
            destroy(obj.donnees)
            self.audio.jouer("ramasser", volume=0.7)
            self.hud.message(f"Pile récupérée  (batterie {int(j.batterie * 100)} %)", 2.5)
        elif g == "journal":
            self.audio.jouer("interface", volume=0.5)
            self.hud.message(obj.donnees[1], 9)
        elif g == "console_courant":
            if self.etape == 0:
                self.retablir_courant()
            else:
                self.hud.message("Le réacteur tourne. Il faut maintenant le code d'accès.", 3)
        elif g == "terminal":
            if self.etape == 0:
                self.audio.jouer("refus", volume=0.6)
                self.hud.message("Le terminal est éteint. Pas de courant.", 3)
            elif self.etape == 1:
                self.etape = 2
                self.audio.jouer("interface", volume=0.8)
                for porte in self.monde.portes:
                    if porte.porte.verrou == "code":
                        porte.deverrouiller()
                self.hud.objectif.text = OBJECTIFS[2]
                code = f"{random.randint(1000, 9999)}"
                self.hud.message(f"CODE D'ACCÈS NAVETTE : {code}. Les portes du hangar sont déverrouillées.", 6)
                self.hud.message("Quelque chose a entendu le terminal...", 3)
                self.monde.bruit(obj.position.x, obj.position.z, 30.0)
            else:
                self.hud.message("Le code est déjà transmis. Rejoignez le hangar !", 3)
        elif g == "navette":
            if self.etape < 2:
                self.audio.jouer("refus", volume=0.6)
                self.hud.message("Sas verrouillé. Code d'accès requis.", 3)
            else:
                self.victoire()

    def retablir_courant(self):
        self.etape = 1
        self.eclairage.retablir_courant()
        self.directrice.retablir_courant(self.pos_machines)
        for porte in self.monde.portes:
            if porte.porte.verrou == "courant":
                porte.deverrouiller()
        self.audio.jouer("courant", volume=1.0)
        self.reacteur.volume = 1.0
        self.alarme.volume = 0.0
        self.joueur.secouer(0.6)
        self.manette.vibrer(0.9, 0.4, 1200)
        self.monde.bruit(self.pos_machines.x, self.pos_machines.z, 70.0)
        self.hud.objectif.text = OBJECTIFS[1]
        self.hud.message("Le réacteur redémarre. Les lumières reviennent...", 4)
        self.hud.message("...et quelque chose s'est réveillé avec elles.", 4)

    def cible_objectif(self):
        return [self.console_courant, self.terminal, self.navette][min(self.etape, 2)].position

    # ------------------------------------------------------------------
    # Entrées
    # ------------------------------------------------------------------
    def input(self, key):
        if key == C.TOUCHE_DEBUG:
            self.debug = not self.debug
            self.hud.debug.enabled = self.debug
            return
        e = self.etat
        if e == MENU:
            if key == "enter":
                self.lancer()
            elif key == "n":
                self.seed = random.randrange(1, 10 ** 6)
                self.menu()
            elif key == "escape":
                self.quitter()
        elif e == JEU:
            if key == C.TOUCHE_PAUSE:
                self.pause(True)
            elif key in C.TOUCHE_CARTE:
                self.basculer_carte()
            elif self.joueur is not None:
                self.joueur.touche(key)
        elif e == PAUSE:
            if key == C.TOUCHE_PAUSE:
                self.pause(False)
            elif key in ("m", ";"):
                self.menu()
        elif e == MORT:
            if key == "enter":
                self.lancer(self.seed)
            elif key == "n":
                self.lancer(random.randrange(1, 10 ** 6))
            elif key == "escape":
                self.menu()
        elif e == VICTOIRE:
            if key == "enter":
                self.menu()
            elif key == "n":
                self.lancer(random.randrange(1, 10 ** 6))

    def basculer_carte(self):
        self.hud.carte.enabled = not self.hud.carte.enabled
        if self.hud.carte.enabled:
            self.hud.maj_carte(0, self.joueur, self.cible_objectif(), force=True)

    def _entrees_manette(self):
        m = self.manette
        e = self.etat
        if e == MENU:
            if m.appui("croix"):
                self.lancer()
        elif e == JEU:
            if m.appui("options"):
                self.pause(True)
            elif m.appui("pave"):
                self.basculer_carte()
        elif e == PAUSE:
            if m.appui("options"):
                self.pause(False)
            elif m.appui("triangle"):
                self.menu()
        elif e == MORT:
            if m.appui("croix"):
                self.lancer(self.seed)
            elif m.appui("rond"):
                self.menu()
        elif e == VICTOIRE:
            if m.appui("croix"):
                self.menu()

    def quitter(self):
        self.manette.quitter()
        application.quit()

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------
    def update(self):
        dt = min(time.dt, 0.05)
        self.manette.maj()
        if self.manette.message:
            if self.etat == JEU:
                self.hud.message(self.manette.message, 3)
            print(self.manette.message)
            self.manette.message = None
        self._entrees_manette()
        self.espace.tick(dt)
        self.hud.maj(dt, self.joueur if self.etat == JEU else None,
                     self.directrice.tension if self.directrice else 0.0)
        if self.fps_txt.enabled:
            self.fps_txt.text = f"{int(1 / max(time.dt, 1e-4))} FPS"
        if self.debug:
            self._maj_debug()
        if self.etat == MENU:
            camera.rotation_y += dt * 1.5
            return
        if self.etat != JEU:
            j = self.joueur
            if self.etat == MORT and j:
                j._finir_tick(dt, 0)
                # la lampe reste braquée sur la créature pendant la mort
                self.eclairage.maj(dt, j.position, j.lampe_allumee, False, max(j.batterie, 0.3))
            else:
                self.eclairage.maj(dt, j.position if j else Vec3(0, 0, 0), False, False, 0)
            return
        self._tick_jeu(dt)

    def _tick_jeu(self, dt):
        j, c, m = self.joueur, self.creature, self.monde
        self.temps += dt
        j.tick(dt)
        # interactions
        cible = None
        if j.cache is None:
            cible = j.chercher_interactif(m.interactifs)
        if j.appui_interagir:
            j.appui_interagir = False
            if j.cache is not None:
                j.sortir()
            elif cible is not None:
                self.interagir(cible)
                if self.etat != JEU:
                    return
        if j.cache is not None:
            self.hud.invite.text = ("[Croix]" if j.utilise_manette else "[E]") + "  Sortir du casier"
        elif cible is not None:
            self.hud.invite_texte(cible, j.utilise_manette)
        else:
            self.hud.invite.text = self._indice_porte()
        # monde, créature, directrice
        m.tick(dt, j.position, None if c.cachee else c.position)
        for casier in self.infos["casiers"]:
            casier.tick(dt)
        attrape = c.tick(dt, j)
        m.bruits.clear()
        self.directrice.tick(dt, j)
        if attrape:
            self.mourir()
            return
        # éclairage, son, carte
        self.eclairage.maj(dt, j.position, j.lampe_allumee, j.lampe_concentree, j.batterie)
        self._maj_bourdon(dt)
        self.audio.maj()
        self.hud.reveler(j.x, j.z)
        self.hud.maj_carte(dt, j, self.cible_objectif())
        self._coeur(dt)

    def _indice_porte(self):
        """Affiche pourquoi une porte proche reste fermée."""
        j = self.joueur
        self.refus_timer -= time.dt
        for porte in self.monde.portes:
            v = porte.porte.verrou
            if v is None:
                continue
            cx, cz = porte.porte.centre
            if (j.x - cx) ** 2 + (j.z - cz) ** 2 < 2.4 ** 2:
                if self.refus_timer <= 0:
                    self.refus_timer = 3.0
                    self.audio.jouer("refus", position=Vec3(cx, 1.5, cz), volume=0.5)
                return "Porte verrouillée : pas de courant" if v == "courant" else "Porte verrouillée : code d'accès requis"
        return ""

    def _maj_bourdon(self, dt):
        """Le bourdonnement électrique suit le néon défectueux le plus proche."""
        self.bourdon_timer -= dt
        if self.bourdon_timer > 0:
            return
        self.bourdon_timer = 0.5
        j = self.joueur
        meilleur, dmin = None, 81
        for s in self.eclairage.sources:
            if s.defectueuse and s.intensite > 0.05:
                d = (s.position.x - j.x) ** 2 + (s.position.z - j.z) ** 2
                if d < dmin:
                    meilleur, dmin = s, d
        self.bourdon.position = meilleur.position if meilleur else Vec3(0, -100, 0)

    def _coeur(self, dt):
        """Battements de cœur (son + vibrations) quand la créature est proche."""
        t = self.directrice.tension
        if t < 0.2:
            return
        self.coeur_timer -= dt
        if self.coeur_timer <= 0:
            self.coeur_timer = 1.15 - t * 0.7
            self.audio.jouer("coeur", volume=0.25 + t * 0.6)
            self.manette.vibrer(0.25 + t * 0.6, 0.05, 110)
            invoke(self.manette.vibrer, 0.15 + t * 0.4, 0.0, 90, delay=0.24)

    def _maj_debug(self):
        lignes = [f"seed {self.seed}  |  état {self.etat}  |  {int(1 / max(time.dt, 1e-4))} FPS"]
        if self.joueur and self.creature:
            j, c = self.joueur, self.creature
            d = math.hypot(j.x - c.x, j.z - c.z)
            lignes.append(f"joueur ({j.x:.1f}, {j.z:.1f})  bruit {j.rayon_bruit:.1f}  batterie {j.batterie * 100:.0f} %")
            lignes.append(f"créature : {c.etat}{' (cachée)' if c.cachee else ''}  distance {d:.1f}  voit {c.voit}  "
                          f"tension {self.directrice.tension:.2f}  calme {self.directrice.calme:.0f}s")
        lignes.append("")
        lignes.append(self.manette.texte_debug())
        self.hud.debug.text = "\n".join(lignes)


def principal():
    app = Ursina(title=C.TITRE_FENETRE, borderless=False, fullscreen=C.PLEIN_ECRAN, size=C.TAILLE_FENETRE,
                 vsync=C.VSYNC, development_mode=False)
    window.color = color.black
    # désactive le raccourci Maj+Q d'Ursina (il quitterait le jeu en courant vers la gauche)
    window.exit_button.input = lambda key: None
    window.exit_button.enabled = False
    camera.fov = C.FOV
    camera.clip_plane_near = 0.05
    camera.clip_plane_far = C.PLAN_LOINTAIN
    app.render.setShaderAuto()
    if C.ANTICRENELAGE:
        app.render.setAntialias(AntialiasAttrib.MMultisample)
    Jeu()
    app.run()


if __name__ == "__main__":
    principal()
