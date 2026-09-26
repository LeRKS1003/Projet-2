# -*- coding: utf-8 -*-
"""
loot.py — Loot du vaisseau : casiers (qui servent aussi de cachettes),
cadavres fouillables (parfois infestés), objets posés, notes de
l'équipage, disque dur. Tables de loot pondérées selon le type de salle.
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
# ----------------------------------------------------------------------------
LOOT_TABLES = {
    "crew":    [("battery", 28), ("ammo", 22), ("medkit", 12), ("knife", 10), ("note", 18), (None, 14)],
    "medbay":  [("medkit", 46), ("battery", 14), ("ammo", 6), ("note", 12), (None, 10)],
    "engine":  [("battery", 34), ("ammo", 22), ("knife", 12), ("medkit", 8), ("note", 8), (None, 12)],
    "storage": [("battery", 25), ("ammo", 30), ("medkit", 12), ("knife", 12), (None, 15)],
    "command": [("ammo", 40), ("battery", 20), ("medkit", 15), ("note", 10), (None, 10)],
    "mess":    [("battery", 20), ("medkit", 14), ("knife", 16), ("note", 14), (None, 20)],
    "hangar":  [("battery", 35), ("ammo", 30), ("medkit", 10), (None, 20)],
    "corpse":  [("ammo", 28), ("battery", 20), ("medkit", 12), ("knife", 10), ("note", 22), (None, 10)],
}

# ----------------------------------------------------------------------------
# NOTES DE L'ÉQUIPAGE (ordre de lecture = ordre de découverte)
# ----------------------------------------------------------------------------
NOTES = [
    ("Journal du capitaine Varga — jour 112",
     "Nous avons arrimé le fragment de la comète K7-Hadès dans la soute.\n"
     "Le labo parle de matière organique fossile. L'équipage est euphorique :\n"
     "la prime paiera la retraite de tout le monde."),
    ("Dr Okonkwo, médecin de bord",
     "Hollis se plaint de démangeaisons depuis l'EVA de prélèvement. 39,8 °C.\n"
     "Sous sa peau, des filaments noirs qui BOUGENT quand j'approche la lampe.\n"
     "Quarantaine immédiate à l'infirmerie."),
    ("Note griffonnée",
     "Ils disent que Hollis est mort.\n"
     "Alors pourquoi j'entends gratter dans le conduit au-dessus de ma couchette ?"),
    ("Chef mécanicien Brandt",
     "Les filtres des conduits sont colmatés par une résine. Quelque chose y a pondu.\n"
     "J'ai scellé la grille 4. Puis la 6. Il y en a partout.\n"
     "Piles de rechange dans les casiers de la salle des machines."),
    ("Dr Okonkwo — rapport 3",
     "Le corps de Hollis a disparu de la morgue. Les petites créatures — j'en ai\n"
     "compté au moins vingt — sont attirées par le bruit et la chaleur.\n"
     "Une lame suffit si on les surprend. Elles se cachent dans les morts."),
    ("Journal du capitaine — jour 119",
     "Nous avons vu la grande. Elle ÉTAIT Hollis, je crois. Trois mètres.\n"
     "Elle ne nous court pas après : elle ÉCOUTE. Au premier coup de feu de Reyes,\n"
     "elle a traversé le pont en moins d'une minute. Ordre : AUCUNE arme à feu."),
    ("Reyes, sécurité",
     "Les balles ne font que la ralentir. Elle recule, secoue la tête, puis revient.\n"
     "Si vous devez vous cacher : les casiers. Ne respirez pas. Ne bougez pas.\n"
     "Et ne vous cachez jamais sous ses yeux."),
    ("Message enregistré — cuisine",
     "Si quelqu'un lit ça : marchez accroupi. Elle entend les pas.\n"
     "Mathis a couru. Mathis n'est pas revenu.\n"
     "On a laissé des kits de soin à l'infirmerie."),
    ("Brandt — dernière note",
     "J'ai coupé la propulsion. On dérive. Personne ne doit ramener ça sur Terre.\n"
     "Le disque dur de la passerelle contient tout : coordonnées de K7-Hadès,\n"
     "analyses, journaux. Une équipe de récupération devra l'emporter... ou le détruire."),
    ("Journal du capitaine — dernière entrée",
     "Il ne reste que moi sur la passerelle. Je garde le disque.\n"
     "Je l'entends dans les conduits : elle fredonne avec la voix de Hollis.\n"
     "Qui que vous soyez : prenez le disque et partez. Ne revenez jamais."),
    ("Dessin scotché dans un casier",
     "Un vaisseau, des étoiles, un bonhomme qui fait coucou.\n"
     "« Papa rentre bientôt. »"),
    ("Liste de maintenance",
     "- Grille du hangar desserrée, à revoir.\n- Néons du couloir C : remplacer les ballasts.\n"
     "- NE PAS OUVRIR LA SOUTE 2."),
]

ITEM_NAMES = {
    "ammo": "munitions", "battery": "pile", "medkit": "kit de soin", "knife": "couteau",
    "note": "note", "nv_helmet": "casque de vision nocturne", "hdd": "disque dur", "fuse": "fusible",
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


def give_contents(game, contents, source):
    """Transfère le contenu vers l'inventaire. Renvoie le reste (inventaire plein)."""
    got, left = [], []
    for kind, n in contents:
        if kind == "note":
            game.read_next_note()
            got.append("une note")
            continue
        added = game.inventory.add(kind, n)
        if added > 0:
            got.append(f"{added} {ITEM_NAMES[kind]}" + ("s" if added > 1 and kind not in ("ammo",) else ""))
        if added < n:
            left.append((kind, n - added))
    if got:
        game.hud.message(f"{source} : " + ", ".join(got))
        game.audio.play("pickup", .7)
    elif not left:
        game.hud.message(f"{source} : vide")
    if left:
        game.hud.message("Inventaire plein !", color.orange)
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
    """Casier : s'ouvre avec une animation, contient du loot, sert de cachette."""
    W, D, H = 0.72, 0.55, 2.0

    def __init__(self, level, builders, parent, placer, table, rng, anim_list):
        self.level = level
        self.table = table
        self.room = None          # salle (renseignée par rooms.py)
        self.contents = roll_contents(table, rng, 1, 2)
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
            left = give_contents(game, self.contents, "Casier fouillé")
            self.contents = left
            self.searched = True
            return
        if self.contents:
            self.contents = give_contents(game, self.contents, "Casier")
            return
        game.player.hide_in(self)

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
        if abs(d) < 0.5:
            self.angle = self.target_angle
            if self in self.anim_list:
                self.anim_list.remove(self)
        else:
            self.angle += d * min(1, dt * 7)
        self.pivot.rotation_y = self.base_yaw + self.angle


class Corpse(Interactable):
    """Cadavre d'un membre d'équipage, fouillable (fouille = vulnérable)."""
    hold_time = C.SEARCH_TIME

    def __init__(self, level, builders, x, z, yaw, rng, uniform_col=None):
        self.level = level
        self.pos = (x, 0.4, z)
        self.searched = False
        self.infested = rng.random() < C.INFESTED_CORPSE_CHANCE
        self.contents = roll_contents("corpse", rng, 1, 2)
        mb = builders["struct"]
        dec = builders["decal"]
        uni = uniform_col or rng.choice([(.35, .3, .2), (.2, .25, .32), (.4, .38, .35), (.45, .2, .12)])
        skin = rng.choice([(.55, .42, .36), (.35, .25, .2), (.62, .5, .45)])
        a = math.radians(yaw)
        ca, sa = math.cos(a), math.sin(a)

        def L(lx, lz):  # local -> monde
            return (x + lx * ca + lz * sa, z - lx * sa + lz * ca)

        # flaque de sang
        dec.decal((x, .012, z), rng.uniform(1.6, 2.4), rng.uniform(0, 360), (1, 1, 1, 1))
        # corps allongé (le long de l'axe local z)
        px, pz = L(0, 0)
        mb.box_rot((px, .14, pz), (.42, .22, .72), yaw, uni)                # torse
        px, pz = L(0, .5)
        mb.box_rot((px, .13, pz), (.22, .2, .24), yaw + rng.uniform(-30, 30), skin)   # tête
        for side in (-1, 1):
            px, pz = L(side * .3, .1 + rng.uniform(-.1, .2))
            mb.box_rot((px, .08, pz), (.12, .12, .6), yaw + side * rng.uniform(10, 60), uni)   # bras
            px, pz = L(side * .12, -.7)
            mb.box_rot((px, .1, pz), (.16, .16, .8), yaw + side * rng.uniform(0, 20), (.12, .12, .14))  # jambes
        if self.infested:
            # bosses suspectes sur le torse
            for _ in range(3):
                px, pz = L(rng.uniform(-.15, .15), rng.uniform(-.2, .2))
                mb.box_rot((px, .27, pz), (.1, .08, .1), rng.uniform(0, 90), (.12, .05, .08))
        level.add_interactable(self, x, z)

    def prompt(self, game):
        if self.searched:
            return None
        return "Fouiller le cadavre (maintenir)"

    def interact(self, game):
        if self.searched:
            return
        self.searched = True
        game.audio.play_at("rustle", self.pos, .8)
        if self.infested:
            game.hud.message("Quelque chose bouge sous les vêtements !", color.red)
            game.aliens.burst_from_corpse(self.pos, 1 + (1 if random.random() < .4 else 0))
            game.horror.scripted_scare(.5)
        left = give_contents(game, self.contents, "Cadavre fouillé")
        self.contents = left
        if left:
            self.searched = False


class Pickup(Interactable):
    """Objet posé dans le décor (couteau sur l'établi, pile sur une table...)."""

    def __init__(self, level, parent, kind, amount, x, y, z, yaw=0):
        self.level = level
        self.kind = kind
        self.amount = amount
        self.pos = (x, y, z)
        self.taken = False
        self.entity = Entity(parent=parent, position=(x, y, z), rotation_y=yaw)
        if kind == "knife":
            Entity(parent=self.entity, model='cube', color=color.rgb(.75, .77, .8), scale=(.035, .01, .22), z=.08)
            Entity(parent=self.entity, model='cube', color=color.rgb(.1, .08, .06), scale=(.04, .03, .12), z=-.08)
        elif kind == "battery":
            Entity(parent=self.entity, model='cube', color=color.rgb(.8, .6, .1), scale=(.06, .12, .06), y=.06)
        elif kind == "medkit":
            Entity(parent=self.entity, model='cube', color=color.rgb(.85, .85, .85), scale=(.3, .1, .2), y=.05)
            Entity(parent=self.entity, model='cube', color=color.red, scale=(.08, .102, .04), y=.05)   # croix peinte
        elif kind == "ammo":
            Entity(parent=self.entity, model='cube', color=color.rgb(.25, .3, .2), scale=(.16, .08, .1), y=.04)
        elif kind == "note":
            Entity(parent=self.entity, model='cube', color=color.rgb(.85, .82, .7), scale=(.2, .005, .28), y=.003)
        elif kind == "nv_helmet":
            Entity(parent=self.entity, model='sphere', color=color.rgb(.2, .22, .2), scale=(.28, .24, .3), y=.12)
            mark_emissive(Entity(parent=self.entity, model='cube', color=color.rgb(.1, .6, .1), scale=(.18, .06, .08),
                                 y=.14, z=.15))       # voyant du casque (sur pile)
        level.add_interactable(self, x, z)

    def prompt(self, game):
        if self.taken:
            return None
        return f"Ramasser : {ITEM_NAMES[self.kind]}"

    def interact(self, game):
        if self.taken:
            return
        if self.kind == "note":
            game.read_next_note()
            left = []
        else:
            left = give_contents(game, [(self.kind, self.amount)], "Ramassé")
        if not left:
            self.taken = True
            destroy(self.entity)
            self.level.remove_interactable(self)


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
    """Répartit le loot garanti (casque de vision nocturne unique, notes)."""

    def __init__(self, rng):
        self.rng = rng
        self.lockers = []
        self.corpses = []

    def finalize(self):
        # un seul casque de vision nocturne, jamais dans le hangar
        cands = [l for l in self.lockers if l.table != "hangar"]
        if cands:
            self.rng.choice(cands).contents.append(("nv_helmet", 1))
        # au moins 5 notes réparties
        holders = self.lockers + self.corpses
        n_notes = sum(1 for h in holders for k, _ in h.contents if k == "note")
        self.rng.shuffle(holders)
        for h in holders:
            if n_notes >= 5:
                break
            if not any(k == "note" for k, _ in h.contents):
                h.contents.append(("note", 1))
                n_notes += 1
