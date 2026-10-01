# -*- coding: utf-8 -*-
"""
loot.py — Loot du vaisseau : casiers (qui servent aussi de cachettes),
corps de l'équipage du Kerguelen (fouillables, parfois « infestés »), sacs
abandonnés, objets posés, documents de l'histoire, disque dur. Tables de
loot pondérées selon le type de salle.
"""
import math
import random

from panda3d.core import TransparencyAttrib
from ursina import Entity, color, destroy

import config as C
import textures
from lighting import mark_emissive

# ----------------------------------------------------------------------------
# TABLES DE LOOT PONDÉRÉES (objet, poids)
# Les documents de l'histoire (story.py) sont placés à part, par rooms.py.
# ----------------------------------------------------------------------------
# (les casiers ont leurs propres tables, réglables dans config.LOCKER_TABLES)
LOOT_TABLES = {
    "crew":    [("battery", 32), ("ammo", 26), ("bandage", 14), ("knife", 10), (None, 18)],
    "medbay":  [("bandage", 50), ("battery", 16), ("ammo", 8), (None, 14)],
    "engine":  [("battery", 38), ("ammo", 24), ("knife", 12), ("bandage", 8), (None, 14)],
    "storage": [("battery", 25), ("ammo", 30), ("bandage", 12), ("knife", 12), (None, 15)],
    "command": [("ammo", 44), ("battery", 22), ("bandage", 16), (None, 12)],
    "mess":    [("battery", 24), ("bandage", 16), ("knife", 18), (None, 24)],
    "hangar":  [("battery", 35), ("ammo", 30), ("bandage", 10), (None, 20)],
    "corpse":  [("ammo", 34), ("battery", 26), ("bandage", 16), ("knife", 12), (None, 12)],
}

# objets sans utilité (casiers « vides ») : ils racontent un peu la vie à bord
JUNK_ITEMS = [
    "une tasse ébréchée au logo Helios Biotech", "une photo de famille pliée en quatre",
    "un gant de combinaison déchiré", "une brosse à dents", "un livre de poche gonflé par l'humidité",
    "des chaussettes roulées en boule", "un paquet de cartes à jouer", "une montre arrêtée à 03:17",
    "un badge d'accès sans puce", "un tube de dentifrice vide", "une peluche usée",
    "des écouteurs aux fils arrachés", "un carnet dont toutes les pages ont été déchirées",
]

ITEM_NAMES = {
    "ammo": "munitions", "rifle_ammo": "munitions de fusil", "battery": "pile", "bandage": "bandage", "knife": "couteau",
    "nv_helmet": "casque de vision nocturne", "hdd": "disque dur", "fuse": "fusible", "doc": "document",
}


def roll(table, rng):
    items = LOOT_TABLES[table]
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    for kind, w in items:
        r -= w
        if r <= 0:
            return kind
    return None


def roll_contents(table, rng, n_min=1, n_max=2):
    """Liste de (objet, quantité)."""
    out = []
    for _ in range(rng.randint(n_min, n_max)):
        k = roll(table, rng)
        if k is None:
            continue
        if k == "ammo":
            out.append(("ammo", rng.randint(*C.AMMO_PICKUP)))
        else:
            out.append((k, 1))
    return out


def roll_locker(table, rng, near_command=False):
    """
    Contenu d'un casier selon config : environ LOCKER_FILL_CHANCE des casiers
    contiennent de l'équipement utile (pondéré par type de salle), les autres
    sont vides ou ne contiennent qu'un objet sans utilité.
    Renvoie (liste de (objet, quantité), objet inutile ou None).
    """
    if rng.random() >= C.LOCKER_FILL_CHANCE:
        junk = rng.choice(JUNK_ITEMS) if rng.random() < C.LOCKER_EMPTY_JUNK else None
        return [], junk
    weights = dict(C.LOCKER_TABLES.get(table, C.LOCKER_TABLES["crew"]))
    if near_command:
        weights["ammo"] = weights.get("ammo", 0) + C.LOCKER_NEAR_COMMAND_AMMO_BONUS
    n = 2 if rng.random() < C.LOCKER_EXTRA_ITEM else 1
    out = []
    for _ in range(n):
        total = sum(weights.values())
        r = rng.uniform(0, total)
        for kind, w in weights.items():
            r -= w
            if r <= 0:
                break
        lo, hi = C.LOCKER_AMOUNTS.get(kind, (1, 1))
        amount = rng.randint(lo, hi)
        for k_, (kk, nn) in enumerate(out):
            if kk == kind:
                out[k_] = (kk, nn + amount)
                break
        else:
            out.append((kind, amount))
        weights.pop(kind, None)            # le 2e objet est d'un autre type
        if not weights:
            break
    return out, None


def give_contents(game, contents, source):
    """Transfère le contenu vers l'inventaire. Renvoie le reste (inventaire plein)."""
    got, left = [], []
    docs = []
    for kind, n in contents:
        if kind == "doc":
            docs.append(n)            # n = identifiant du document (story.py)
            got.append("un document")
            continue
        added = game.inventory.add(kind, n)
        if added > 0:
            got.append(f"{added} {ITEM_NAMES[kind]}" + ("s" if added > 1 and kind not in ("ammo", "rifle_ammo") else ""))
        if added < n:
            left.append((kind, n - added))
    if got:
        game.hud.message(f"{source} : " + ", ".join(got))
        game.audio.play("pickup", .7)
    elif not left:
        game.hud.message(f"{source} : vide")
    if left:
        game.hud.message("Inventaire plein !", color.orange)
    for d in docs:
        game.docs.collect(d)
    return left


# ============================================================================
class Interactable:
    hold_time = 0.0
    radius = 1.9
    pos = (0, 0, 0)

    def prompt(self, game):
        return None

    def interact(self, game):
        pass


class Locker(Interactable):
    """
    Casier : s'ouvre avec une animation, contient du loot (tiré par
    LootDirector.finalize selon la salle), sert de cachette. À l'ouverture,
    les objets trouvés luisent un court instant sur l'étagère.
    """
    W, D, H = 0.72, 0.55, 2.0

    def __init__(self, level, builders, parent, placer, table, rng, anim_list):
        self.level = level
        self.table = table
        self.room = None          # salle (renseignée par rooms.py)
        self.contents = []        # rempli par LootDirector.finalize (pondération par salle)
        self.junk = None          # objet sans utilité (casier « vide »)
        self.parent = parent
        self.placer = placer
        self.glow = []            # (entité, halo) des objets qui luisent à l'ouverture
        self.glow_t = 0.0
        self.opened = False
        self.searched = False
        self.anim_list = anim_list
        self.angle = 0.0
        self.target_angle = 0.0
        self.occupied = False
        pl = placer
        body = (.26, .29, .31) if table != "medbay" else (.62, .66, .68)
        mb = builders["struct"]
        W, D, H = self.W, self.D, self.H
        # caisson (ouvert à l'avant)
        pl.box(mb, (0, H / 2, -D / 2 + .03), (W, H, .05), body)                 # fond
        pl.box(mb, (-W / 2 + .03, H / 2, 0), (.05, H, D), body)                 # côté gauche
        pl.box(mb, (W / 2 - .03, H / 2, 0), (.05, H, D), body)                  # côté droit
        pl.box(mb, (0, H - .03, 0), (W, .06, D), body)                          # dessus
        pl.box(mb, (0, .05, 0), (W, .1, D), body)                               # socle
        pl.box(mb, (0, H * .7, -.05), (W - .1, .03, D - .12), (.2, .2, .2))     # étagère
        # porte sur charnière (entité séparée animée)
        hinge = pl.pt(-W / 2 + .02, 0, D / 2)
        self.base_yaw = pl.yaw
        self.pivot = Entity(parent=parent, position=(hinge[0], 0, hinge[2]), rotation_y=pl.yaw)
        self.door = Entity(parent=self.pivot, model='cube', texture=textures.get('panel'),
                           color=color.rgb(*[c * 1.1 for c in body]),
                           position=(W / 2 - .02, H / 2, 0), scale=(W - .04, H - .06, .04))
        # fentes d'aération sur la porte
        for k in range(4):
            Entity(parent=self.door, model='cube', color=color.rgb(.02, .02, .02),
                   position=(0, .25 - k * .04, -.6), scale=(.7, .012, .2))
        self.pos = pl.pt(0, 1.1, D / 2 + .1)
        self.hide_pos = pl.pt(0, 0, -.02)
        self.facing = pl.facing
        level.add_interactable(self, self.pos[0], self.pos[2])
        x0, x1, z0, z1 = pl.aabb((0, 0), (W, D))
        from generator import Blocker
        level.add_blocker(Blocker(x0, x1, 0, H, z0, z1, "prop", self))

    def prompt(self, game):
        if self.occupied:
            return "Sortir du casier"
        if not self.opened:
            return "Ouvrir le casier"
        if self.contents:
            return "Fouiller le casier"
        return "Se cacher dans le casier"

    def interact(self, game):
        if self.occupied:
            game.player.leave_hiding()
            return
        if not self.opened and game.screamer is not None and game.screamer.is_target(self):
            # casier piégé : aucun indice visuel, il s'ouvre normalement... puis le screamer
            self.open_door()
            self.searched = True
            game.audio.play_at("locker_open", self.pos, .9)
            game.screamer.trigger(self)
            return
        if not self.opened:
            self.open_door()
            game.audio.play_at("locker_open", self.pos, .9)
            game.noise(self.pos, C.NOISE_LOCKER, "locker")
            self.searched = True
            if self.contents:
                self._show_glow(self.contents)
                self.contents = give_contents(game, self.contents, "Trouvé")
            elif self.junk:
                game.hud.message(f"Trouvé : {self.junk}. Rien d'utile.", color.rgb(.65, .65, .6))
                game.audio.play("rustle", .4)
            else:
                game.hud.message("Casier vide.", color.rgb(.6, .6, .58))
            return
        if self.contents:
            self.contents = give_contents(game, self.contents, "Trouvé")
            return
        game.player.hide_in(self)

    # ------------------------------------------------------------------
    def _show_glow(self, contents):
        """Petits objets posés sur l'étagère, avec une lueur douce qui s'estompe."""
        from lighting import additive
        pl = self.placer
        spots = [(-.16, 1.43, -.08), (.14, 1.43, -.1), (0, .13, -.05)]
        for k, (kind, n) in enumerate(contents[:3]):
            x, y, z = pl.pt(*spots[k])
            root = Entity(parent=self.parent, position=(x, y, z), rotation_y=pl.yaw)
            item_model(root, kind)
            halo = Entity(parent=root, model='quad', texture=textures.get('glow'), billboard=True,
                          color=color.rgba(1, .9, .6, 0), scale=.42, y=.06)
            additive(halo, 6)
            self.glow.append((root, halo))
        self.glow_t = C.LOCKER_GLOW_TIME
        if self not in self.anim_list:
            self.anim_list.append(self)

    def open_door(self):
        self.opened = True
        self.target_angle = -105
        if self not in self.anim_list:
            self.anim_list.append(self)

    def close_door(self):
        self.target_angle = 0
        if self not in self.anim_list:
            self.anim_list.append(self)

    def update(self, dt):
        d = self.target_angle - self.angle
        done = abs(d) < 0.5
        if done:
            self.angle = self.target_angle
        else:
            self.angle += d * min(1, dt * 7)
        self.pivot.rotation_y = self.base_yaw + self.angle
        # lueur des objets trouvés : monte vite, puis s'éteint ; les objets disparaissent (ramassés)
        if self.glow:
            self.glow_t -= dt
            T = C.LOCKER_GLOW_TIME
            age = T - self.glow_t
            a = min(1.0, age / .35) * max(0.0, min(1.0, self.glow_t / 1.0))
            for root, halo in self.glow:
                halo.color = color.rgba(1, .9, .6, .55 * a)
                root.setColorScale(1 + .8 * a, 1 + .7 * a, 1 + .5 * a, 1)
            if self.glow_t <= 0:
                for root, _ in self.glow:
                    destroy(root)
                self.glow = []
        if done and not self.glow and self in self.anim_list:
            self.anim_list.remove(self)


def item_model(parent, kind):
    """Petit modèle d'un objet (posé dans le décor ou luisant dans un casier ouvert)."""
    if kind == "knife":
        Entity(parent=parent, model='cube', color=color.rgb(.75, .77, .8), scale=(.035, .01, .22), z=.08)
        Entity(parent=parent, model='cube', color=color.rgb(.1, .08, .06), scale=(.04, .03, .12), z=-.08)
    elif kind == "battery":
        Entity(parent=parent, model='cube', color=color.rgb(.8, .6, .1), scale=(.06, .12, .06), y=.06)
        Entity(parent=parent, model='cube', color=color.rgb(.2, .2, .2), scale=(.062, .03, .062), y=.1)
    elif kind == "bandage":
        # rouleau de bande + petite boîte blanche à croix rouge
        Entity(parent=parent, model='sphere', color=color.rgb(.9, .88, .84), scale=(.09, .07, .09), y=.035, x=-.06)
        Entity(parent=parent, model='cube', color=color.rgb(.88, .88, .86), scale=(.14, .06, .1), y=.03, x=.05)
        Entity(parent=parent, model='cube', color=color.rgb(.8, .08, .06), scale=(.05, .062, .015), y=.03, x=.05)
        Entity(parent=parent, model='cube', color=color.rgb(.8, .08, .06), scale=(.015, .062, .05), y=.03, x=.05)
    elif kind == "ammo":
        Entity(parent=parent, model='cube', color=color.rgb(.25, .3, .2), scale=(.16, .08, .1), y=.04)
        Entity(parent=parent, model='cube', color=color.rgb(.75, .62, .25), scale=(.12, .012, .06), y=.082)
    elif kind == "rifle_ammo":
        # chargeur courbe de fusil (polymère sombre, bande rouge « subsonique »)
        Entity(parent=parent, model='cube', color=color.rgb(.13, .13, .14), scale=(.04, .16, .06), y=.08,
               rotation_x=12)
        Entity(parent=parent, model='cube', color=color.rgb(.6, .1, .08), scale=(.042, .02, .062), y=.13,
               rotation_x=12)
    elif kind == "nv_helmet":
        Entity(parent=parent, model='sphere', color=color.rgb(.2, .22, .2), scale=(.28, .24, .3), y=.12)
        mark_emissive(Entity(parent=parent, model='cube', color=color.rgb(.1, .6, .1), scale=(.18, .06, .08),
                             y=.14, z=.15))       # voyant du casque (sur pile)
    else:
        Entity(parent=parent, model='cube', color=color.rgb(.5, .5, .5), scale=.08, y=.04)


class WeaponCrate(Interactable):
    """
    Caisse d'armes de sécurité verrouillée (hangar) : on la force en maintenant
    le bouton d'interaction, puis on y prend le fusil d'assaut silencieux et
    des munitions. Rangée parmi les caisses du hangar, pas en évidence.
    """
    radius = 1.8

    def __init__(self, level, builders, parent, placer):
        self.level = level
        self.opened = False
        self.taken = False
        self.parent = parent
        pl = placer
        mb = builders["struct"]
        body = (.18, .2, .17)
        # caisse longue, renforts, poignées, bandes « SÉCURITÉ »
        pl.box(mb, (0, .25, 0), (1.25, .46, .5), body)
        for x in (-.5, 0, .5):
            pl.box(mb, (x, .25, 0), (.06, .48, .52), (.12, .13, .12))
        for sx in (-.66, .66):
            pl.box(mb, (sx, .32, 0), (.04, .05, .2), (.08, .08, .08))
        builders["hazard"].box(pl.pt(0, .2, .252), pl.size((1.0, .06, .005)), (1, 1, 1))
        self.pos = pl.pt(0, .6, .45)
        self.placer = pl
        # couvercle (entité animée) + boîtier de verrouillage avec voyant
        self.lid_pivot = Entity(parent=parent, position=pl.pt(0, .48, -.25), rotation_y=pl.yaw)
        self.lid = Entity(parent=self.lid_pivot, model='cube', texture=textures.get('panel'),
                          color=color.rgb(.2, .22, .19), position=(0, .02, .25), scale=(1.27, .05, .52))
        lock = Entity(parent=self.lid_pivot, model='cube', color=color.rgb(.1, .1, .11), position=(0, -.03, .51),
                      scale=(.14, .1, .03))
        self.led = Entity(parent=lock, model='cube', color=color.rgb(1, .05, .03), position=(.25, .2, -.6),
                          scale=(.2, .2, .3))
        mark_emissive(self.led)
        self.angle = 0.0
        # le fusil et ses chargeurs, à l'intérieur (visibles une fois ouvert)
        self.content = Entity(parent=parent, position=pl.pt(0, .32, 0), rotation_y=pl.yaw + 90)
        Entity(parent=self.content, model='cube', color=color.rgb(.1, .1, .11), scale=(.05, .06, .62))       # carcasse
        Entity(parent=self.content, model='cube', color=color.rgb(.08, .08, .09), scale=(.045, .045, .26),
               z=.43)                                                                                      # silencieux
        Entity(parent=self.content, model='cube', color=color.rgb(.17, .17, .18), scale=(.04, .1, .05),
               position=(0, -.06, -.05))                                                                   # poignée
        Entity(parent=self.content, model='cube', color=color.rgb(.17, .17, .18), scale=(.04, .11, .03),
               position=(0, -.02, -.36))                                                                   # crosse
        mark_emissive(Entity(parent=self.content, model='cube', color=color.rgb(1, .1, .05), scale=(.006, .006, .006),
                             position=(0, .06, .05)))                                                      # point rouge
        for k in range(2):
            item_model(Entity(parent=self.content, position=(.16, -.03, -.15 + k * .12), rotation_z=90), "rifle_ammo")
        self.content.enabled = False
        level.add_interactable(self, self.pos[0], self.pos[2])

    @property
    def hold_time(self):
        return C.RIFLE_CRATE_HOLD if not self.opened else 0.0

    def prompt(self, game):
        if not self.opened:
            return "Forcer la caisse d'armes verrouillée (maintenir)"
        if not self.taken:
            return "Prendre le fusil d'assaut silencieux"
        return None

    def on_hold(self, game, dt):
        """Pied-de-biche sur la serrure : grincements métalliques pendant l'effort."""
        self._snd_t = getattr(self, "_snd_t", 0.0) - dt
        if self._snd_t <= 0:
            self._snd_t = random.uniform(.5, .8)
            game.audio.play_at("door_force", self.pos, .45, random.uniform(1.1, 1.3))
            game.inp.rumble(.25, .1, 120)

    def interact(self, game):
        if not self.opened:
            self.opened = True
            self.led.color = color.rgb(.1, 1, .3)
            self.content.enabled = True
            game.audio.play_at("locker_open", self.pos, .8, .8)
            game.noise(self.pos, 4.0, "locker")
            game.hud.message("La serrure cède. Un fusil d'assaut, sous film plastique.", color.rgb(.8, .85, .8))
            if self not in game.builder.animated:
                game.builder.animated.append(self)
            return
        if not self.taken:
            self.taken = True
            self.content.enabled = False
            game.weapons.give_rifle(C.RIFLE_START_AMMO)
            game.audio.play("pickup", .8)
            game.hud.message(f"Fusil d'assaut silencieux récupéré (+{C.RIFLE_START_AMMO} munitions). "
                             "Touche 2 / flèche droite pour le prendre en main.", color.lime)
            self.level.remove_interactable(self)

    def update(self, dt):
        target = -100.0 if self.opened else 0.0
        self.angle += (target - self.angle) * min(1, dt * 4)
        self.lid_pivot.rotation_x = self.angle


class Pickup(Interactable):
    """Objet posé dans le décor (couteau sur l'établi, pile sur une table...)."""

    def __init__(self, level, parent, kind, amount, x, y, z, yaw=0):
        self.level = level
        self.kind = kind
        self.amount = amount
        self.pos = (x, y, z)
        self.taken = False
        self.entity = Entity(parent=parent, position=(x, y, z), rotation_y=yaw)
        item_model(self.entity, kind)
        level.add_interactable(self, x, z)

    def prompt(self, game):
        if self.taken:
            return None
        return f"Ramasser : {ITEM_NAMES[self.kind]}"

    def interact(self, game):
        if self.taken:
            return
        left = give_contents(game, [(self.kind, self.amount)], "Ramassé")
        if not left:
            self.taken = True
            destroy(self.entity)
            self.level.remove_interactable(self)


class Cache(Interactable):
    """Sac de survie abandonné par l'équipage, à fouiller (maintenir)."""
    hold_time = C.SEARCH_TIME * .6

    def __init__(self, level, builders, x, z, yaw, rng):
        self.level = level
        self.pos = (x, 0.25, z)
        self.searched = False
        self.contents = roll_contents("corpse", rng, 1, 2)
        mb = builders["struct"]
        col = rng.choice([(.3, .33, .22), (.45, .2, .12), (.2, .24, .3), (.42, .4, .36)])
        mb.box_rot((x, .14, z), (.36, .28, .62), yaw, col)                               # sac
        mb.box_rot((x, .29, z), (.05, .04, .5), yaw + 90, (.08, .08, .08))              # sangle
        mb.box_rot((x, .15, z), (.37, .03, .2), yaw, (.1, .1, .1))
        level.add_interactable(self, x, z)

    def prompt(self, game):
        return None if self.searched else "Fouiller le sac abandonné (maintenir)"

    def interact(self, game):
        if self.searched:
            return
        self.searched = True
        game.audio.play_at("rustle", self.pos, .8, 1.2)
        self.contents = give_contents(game, self.contents, "Sac fouillé")
        if self.contents:
            self.searched = False


class DocumentPickup(Interactable):
    """
    Document de l'histoire posé dans le décor : feuille, carnet, tablette
    (journal de bord), enregistreur audio, photo, post-it (vertical sur une
    porte ou sur le frigo). Ramassé -> ajouté au journal et ouvert en lecture.
    """
    radius = 1.7

    def __init__(self, level, parent, doc, x, y, z, yaw=0, vertical=False):
        self.level = level
        self.doc = doc
        self.pos = (x, y + .05, z)
        self.taken = False
        self.parent = parent
        self.entity = Entity(parent=parent, position=(x, y, z), rotation_y=yaw)
        if vertical:
            self.entity.rotation_x = -90          # collé sur une surface verticale
        self._build(doc)
        level.add_interactable(self, x, z)

    def _build(self, doc):
        e = self.entity
        st = doc["style"]
        if st in ("terminal",):
            Entity(parent=e, model='cube', color=color.rgb(.08, .08, .09), scale=(.2, .015, .28), y=.008)
            mark_emissive(Entity(parent=e, model='cube', color=color.rgb(.15, .6, .3), scale=(.17, .002, .22),
                                 y=.017))
        elif st == "audio":
            Entity(parent=e, model='cube', color=color.rgb(.12, .12, .13), scale=(.07, .03, .12), y=.015)
            mark_emissive(Entity(parent=e, model='cube', color=color.rgb(1, .1, .05), scale=(.012, .005, .012),
                                 position=(.02, .032, .04)))
        elif st == "postit":
            Entity(parent=e, model='cube', color=color.rgb(.95, .88, .35), scale=(.09, .002, .09), y=.001)
        elif st == "photo":
            Entity(parent=e, model='cube', color=color.rgb(.9, .88, .82), scale=(.2, .003, .16), y=.002)
            Entity(parent=e, model='cube', color=color.rgb(.2, .2, .22), scale=(.17, .004, .12), y=.003)
        elif doc["type"] in ("cahier", "journal"):
            Entity(parent=e, model='cube', color=color.rgb(.25, .12, .1), scale=(.17, .02, .23), y=.01)
            Entity(parent=e, model='cube', color=color.rgb(.9, .87, .78), scale=(.16, .012, .22), y=.022)
        else:
            # feuille (légèrement claire : elle accroche la lampe)
            Entity(parent=e, model='cube', color=color.rgb(.9, .87, .76), scale=(.21, .003, .29), y=.002)
            if st == "helios":
                Entity(parent=e, model='cube', color=color.rgb(.85, .45, .1), scale=(.05, .004, .05),
                       position=(-.07, .003, .11))

    def move_to(self, x, y, z, yaw=0):
        """Déplace le document (le casier du screamer a été déplacé)."""
        self.level.remove_interactable(self)
        self.pos = (x, y + .05, z)
        self.entity.position = (x, y, z)
        self.entity.rotation_y = yaw
        self.level.add_interactable(self, x, z)

    def prompt(self, game):
        if self.taken:
            return None
        verb = "Écouter" if self.doc["style"] == "audio" else "Lire"
        return f"{verb} : {self.doc['title']}"

    def interact(self, game):
        if self.taken:
            return
        self.taken = True
        destroy(self.entity)
        self.level.remove_interactable(self)
        game.docs.collect(self.doc["id"])


class FusePickup(Interactable):
    """
    Fusible de rechange pour le tableau électrique principal. Posé au sol,
    caché dans un coin : sa bande réfléchissante et son petit voyant ambre
    le rendent repérable à la lampe.
    """
    radius = 1.6

    def __init__(self, level, parent, x, y, z, yaw=0):
        self.level = level
        self.pos = (x, y + .1, z)
        self.taken = False
        self.entity = Entity(parent=parent, position=(x, y, z), rotation_y=yaw)
        # cartouche en céramique + culots métalliques, couché sur le sol
        body = Entity(parent=self.entity, model='cube', color=color.rgb(.8, .66, .28), scale=(.07, .07, .24),
                      y=.035)
        for zz in (-.14, .14):
            Entity(parent=self.entity, model='cube', color=color.rgb(.75, .75, .78), scale=(.08, .08, .05),
                   position=(0, .035, zz))
        # bande réfléchissante : accroche la lampe torche
        Entity(parent=body, model='cube', color=color.rgb(1, .95, .75), scale=(1.03, .25, .35), y=.3)
        # minuscule voyant de charge (brille sans éclairer)
        mark_emissive(Entity(parent=self.entity, model='cube', color=color.rgb(1, .55, .1),
                             scale=(.02, .012, .02), position=(0, .075, .06)))
        level.add_interactable(self, x, z)

    def prompt(self, game):
        return None if self.taken else "Ramasser : fusible"

    def interact(self, game):
        if self.taken:
            return
        self.taken = True
        destroy(self.entity)
        self.level.remove_interactable(self)
        game.audio.play("pickup", .7, .9)
        if game.power is not None:
            game.power.pick_fuse()


class HardDrive(Interactable):
    """Le disque dur des données du vaisseau, sur une console de la passerelle."""

    def __init__(self, level, parent, x, y, z, yaw):
        self.level = level
        self.pos = (x, y, z)
        self.taken = False
        self.entity = Entity(parent=parent, position=(x, y, z), rotation_y=yaw)
        Entity(parent=self.entity, model='cube', color=color.rgb(.15, .16, .18), scale=(.22, .05, .15))
        self.led = mark_emissive(Entity(parent=self.entity, model='cube', color=color.rgb(.1, 1, .3),
                                        scale=(.03, .02, .02), position=(.08, .03, .07)))
        self.halo = mark_emissive(Entity(parent=self.entity, model='quad', texture=textures.get('glow'),
                                         billboard=True, color=color.rgba(.2, 1, .4, .35), scale=.6, y=.05))
        self.halo.setTransparency(TransparencyAttrib.MAlpha)
        self.t = 0
        level.add_interactable(self, x, z)

    def update(self, dt):
        self.t += dt
        if not self.taken:
            on = math.sin(self.t * 6) > 0
            self.led.color = color.rgb(.1, 1, .3) if on else color.rgb(.02, .2, .05)

    def prompt(self, game):
        return None if self.taken else "Récupérer le disque dur"

    def interact(self, game):
        if self.taken:
            return
        if game.inventory.add("hdd", 1) <= 0:
            game.hud.message("Inventaire plein : libère une place (Tab)", color.orange)
            return
        self.taken = True
        destroy(self.entity)
        self.level.remove_interactable(self)
        game.on_hdd_taken()


class LootDirector:
    """Répartit le loot garanti (casque de vision nocturne unique)."""

    def __init__(self, rng):
        self.rng = rng
        self.lockers = []
        self.corpses = []
        self.nv_locker = None

    def finalize(self, command_center=None):
        """
        Remplit tous les casiers (config.LOCKER_*), puis place LE casque de
        vision nocturne : un seul par partie, garanti, dans un casier des
        chambres ou de l'infirmerie (jamais dans le hangar).
        """
        rng = self.rng
        for lk in self.lockers:
            near = False
            if command_center is not None:
                near = math.hypot(lk.pos[0] - command_center[0], lk.pos[2] - command_center[1]) \
                    < C.LOCKER_NEAR_COMMAND_DIST
            lk.contents, lk.junk = roll_locker(lk.table, rng, near)
        cands = [l for l in self.lockers if l.table in C.NV_HELMET_ROOMS]
        if not cands:
            cands = [l for l in self.lockers if l.table != "hangar"]
        if cands:
            lk = rng.choice(cands)
            lk.contents.append(("nv_helmet", 1))
            lk.junk = None
            self.nv_locker = lk
        filled = sum(1 for l in self.lockers if l.contents)
        print(f"[loot] {len(self.lockers)} casiers : {filled} avec de l'équipement, casque de vision nocturne : "
              f"{self.nv_locker.table if self.nv_locker else 'aucun casier candidat'}")
