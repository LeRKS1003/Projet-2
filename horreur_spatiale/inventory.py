# -*- coding: utf-8 -*-
"""
inventory.py — Inventaire limité en place, objets empilables, objet
équipé (utilisation rapide), casque de vision nocturne, couteaux avec
durabilité. Les documents de l'histoire sont dans le journal (document_ui.py).

Le menu d'inventaire NE met PAS le jeu en pause : la créature continue
de rôder pendant que tu fouilles ton sac.
"""
import textwrap

from ursina import Entity, Text, camera, color

import config as C
from loot import ITEM_NAMES

DESCRIPTIONS = {
    "ammo": "Balles de 9 mm pour le pistolet.",
    "battery": "Recharge la lampe torche / le casque (+{:.0f} %).".format(C.BATTERY_PICKUP),
    "medkit": "Soigne {} points de santé.".format(C.MEDKIT_HEAL),
    "knife": "Silencieux. S'use à chaque coup porté.",
    "nv_helmet": "Vision nocturne (N / L1). Consomme la batterie. Les lumières éblouissent.",
    "hdd": "Les données du projet SINUS, extraites du Kerguelen.",
}
USABLE = ("medkit", "battery")


class Slot:
    __slots__ = ("kind", "count", "durability")

    def __init__(self, kind, count=1, durability=None):
        self.kind = kind
        self.count = count
        self.durability = durability


class Inventory:
    def __init__(self, game):
        self.game = game
        self.slots = []
        self.equipped = "medkit"        # objet d'utilisation rapide
        self.nv_equipped = False

    # ------------------------------------------------------------------
    def count(self, kind):
        return sum(s.count for s in self.slots if s.kind == kind)

    def has(self, kind):
        return any(s.kind == kind and s.count > 0 for s in self.slots)

    def free_slots(self):
        return C.INVENTORY_SLOTS - len(self.slots)

    def add(self, kind, n=1):
        """Ajoute n objets. Renvoie le nombre réellement ajouté."""
        stack = C.STACK_SIZES.get(kind, 1)
        added = 0
        # compléter les piles existantes
        for s in self.slots:
            if s.kind == kind and s.count < stack and kind != "knife":
                take = min(stack - s.count, n - added)
                s.count += take
                added += take
                if added >= n:
                    break
        while added < n:
            # le disque dur a toujours sa place (objet de quête)
            if len(self.slots) >= C.INVENTORY_SLOTS and kind != "hdd":
                break
            take = min(stack, n - added)
            self.slots.append(Slot(kind, take, C.KNIFE_DURABILITY if kind == "knife" else None))
            added += take
        if kind == "nv_helmet" and added:
            self.nv_equipped = True
            self.game.hud.message("Casque de vision nocturne équipé : N / L1", color.lime)
        return added

    def remove(self, kind, n=1):
        removed = 0
        for s in list(self.slots):
            if s.kind != kind:
                continue
            take = min(s.count, n - removed)
            s.count -= take
            removed += take
            if s.count <= 0:
                self.slots.remove(s)
            if removed >= n:
                break
        if kind == "nv_helmet" and not self.has("nv_helmet"):
            self.nv_equipped = False
        return removed

    def wear_knife(self):
        """Use le premier couteau. Renvoie True s'il se brise."""
        for s in self.slots:
            if s.kind == "knife":
                s.durability -= 1
                if s.durability <= 0:
                    self.slots.remove(s)
                    return True
                return False
        return False

    def knife_durability(self):
        for s in self.slots:
            if s.kind == "knife":
                return s.durability
        return 0

    # ------------------------------------------------------------------
    def cycle_equipped(self, step):
        kinds = [k for k in USABLE if self.has(k)] or list(USABLE)
        if self.equipped not in kinds:
            self.equipped = kinds[0]
            return
        i = kinds.index(self.equipped)
        self.equipped = kinds[(i + step) % len(kinds)]
        self.game.audio.play("ui_select", .5)

    def use(self, kind):
        g = self.game
        if not self.has(kind):
            g.hud.message(f"Aucun(e) {ITEM_NAMES.get(kind, kind)}")
            return False
        if kind == "medkit":
            if g.player.health >= C.MAX_HEALTH:
                g.hud.message("Santé déjà au maximum")
                return False
            self.remove("medkit")
            g.player.heal(C.MEDKIT_HEAL)
            g.audio.play("rustle", .6)
            g.hud.message(f"Kit de soin utilisé (+{C.MEDKIT_HEAL})", color.lime)
            return True
        if kind == "battery":
            if g.lights.battery >= C.BATTERY_MAX - 1:
                g.hud.message("Batterie déjà pleine")
                return False
            self.remove("battery")
            g.lights.battery = min(C.BATTERY_MAX, g.lights.battery + C.BATTERY_PICKUP)
            g.audio.play("pickup", .6)
            g.hud.message("Pile insérée", color.lime)
            return True
        if kind == "nv_helmet":
            g.toggle_nightvision()
            return True
        if kind == "knife":
            g.hud.message(f"Couteau : {self.knife_durability()} coups restants")
            return False
        if kind == "hdd":
            g.hud.message("Le disque dur. Retourne au hangar !")
            return False
        return False

    def drop(self, index):
        if 0 <= index < len(self.slots):
            s = self.slots[index]
            if s.kind == "hdd":
                self.game.hud.message("Tu ne peux pas abandonner le disque dur")
                return
            self.slots.pop(index)
            if s.kind == "nv_helmet":
                self.nv_equipped = False
                if self.game.lights.nightvision:
                    self.game.toggle_nightvision()
            self.game.hud.message(f"Jeté : {ITEM_NAMES.get(s.kind, s.kind)}")


# ============================================================================
class InventoryUI:
    """Menu d'inventaire (Tab / pavé tactile). Le jeu continue en arrière-plan."""

    def __init__(self, game):
        self.game = game
        self.open = False
        self.sel = 0
        self.root = Entity(parent=camera.ui, enabled=False, z=-2)
        Entity(parent=self.root, model='quad', color=color.rgba(0, 0, 0, .78), scale=(.9, .66), position=(0, 0))
        Text(parent=self.root, text="INVENTAIRE", position=(-.42, .3), scale=1.3, color=color.rgb(.8, .9, .8))
        self.hint = Text(parent=self.root, text="", position=(-.42, -.27), scale=.72, color=color.rgb(.6, .6, .6))
        self.rows = []
        for k in range(C.INVENTORY_SLOTS):
            bg = Entity(parent=self.root, model='quad', color=color.rgba(1, 1, 1, .05), scale=(.5, .05),
                        position=(-.17, .22 - k * .058))
            t = Text(parent=self.root, text="", position=(-.41, .232 - k * .058), scale=.85)
            self.rows.append((bg, t))
        self.desc = Text(parent=self.root, text="", position=(.12, .2), scale=.75, color=color.rgb(.8, .8, .75))
        self.journal = Text(parent=self.root, text="", position=(.12, -.05), scale=.7, color=color.rgb(.6, .7, .6))

    @property
    def reading(self):
        """Un document est-il ouvert en lecture ? (le joueur ne se déplace pas pendant la lecture)"""
        r = getattr(self.game, "reader", None)
        return r is not None and r.is_open

    def toggle(self):
        self.open = not self.open
        self.root.enabled = self.open
        self.game.audio.play("ui_select", .5)
        self.sel = min(self.sel, max(0, len(self.game.inventory.slots) - 1))

    def close(self):
        self.open = False
        self.root.enabled = False

    def hide_all(self):
        self.close()

    def update(self, dt, inp):
        inv = self.game.inventory
        if not self.open:
            return False
        n = len(inv.slots)
        if inp.pressed("menu_up") or inp.pressed("prev_item"):
            self.sel = (self.sel - 1) % max(1, n)
            self.game.audio.play("ui_select", .4)
        if inp.pressed("menu_down") or inp.pressed("next_item"):
            self.sel = (self.sel + 1) % max(1, n)
            self.game.audio.play("ui_select", .4)
        if n and (inp.pressed("interact") or inp.pressed("confirm")):
            inv.use(inv.slots[self.sel].kind)
        if n and inp.pressed("drop"):
            inv.drop(self.sel)
        self.sel = min(self.sel, max(0, len(inv.slots) - 1))
        # affichage
        for k, (bg, t) in enumerate(self.rows):
            if k < len(inv.slots):
                s = inv.slots[k]
                name = ITEM_NAMES.get(s.kind, s.kind).capitalize()
                extra = f" x{s.count}" if s.count > 1 else ""
                if s.kind == "knife":
                    extra = f"  ({s.durability}/{C.KNIFE_DURABILITY})"
                if s.kind == "nv_helmet":
                    extra = "  [équipé]"
                t.text = name + extra
                t.color = color.rgb(1, 1, .7) if k == self.sel else color.rgb(.75, .75, .75)
                bg.color = color.rgba(1, 1, .6, .15) if k == self.sel else color.rgba(1, 1, 1, .04)
            else:
                t.text = "-"
                t.color = color.rgb(.3, .3, .3)
                bg.color = color.rgba(1, 1, 1, .02)
        if inv.slots:
            self.desc.text = textwrap.fill(DESCRIPTIONS.get(inv.slots[self.sel].kind, ""), 30)
        else:
            self.desc.text = "Vide."
        docs = self.game.docs
        self.journal.text = (f"Documents : {len(docs.found)}/{docs.total}  (journal : J / Create)\n"
                             f"Places libres : {inv.free_slots()}")
        pad = self.game.inp.using_pad
        self.hint.text = ("Croix: utiliser   Triangle: jeter   Pavé: fermer" if pad
                          else "Flèches/molette: choisir   E/Entrée: utiliser   Suppr: jeter   Tab: fermer")
        return True

    def destroy(self):
        from ursina import destroy
        destroy(self.root)
