# ÉPAVE — Le silence du Mnémosyne

Jeu d'horreur spatial en Python (Ursina + pygame + numpy), ambiance *Alien* (1979), *Dead Space*, *SOMA*.
Aucun asset externe : toute la géométrie est faite de primitives, les textures et les sons sont générés par code.

1. **Phase 1 – Approche (TPS)** : tu pilotes une navette autour d'un immense vaisseau abandonné qui dérive
   (antennes, panneaux solaires arrachés, débris qui tournent). Trouve l'ouverture du hangar grâce aux balises
   rouges/vertes et à la flèche du HUD. Chaque collision abîme la coque. Une fois l'ouverture franchie, la navette
   se pose toute seule, l'écran s'assombrit, tu sors à pied.
2. **Phase 2 – Exploration (FPS)** : atteins la salle de commandement, récupère le disque dur, reviens au hangar
   et repars. Une grande créature invulnérable rôde ; de petits parasites attaquent. **Chaque tir déclenche le
   mode horreur** (alarmes, lumières rouges, musique stridente, la créature fonce vers le bruit, des parasites
   sortent des conduits). Couteau et discrétion sont souvent de meilleures options.

---

## Arborescence

```
horreur_spatiale/
├── main.py         point d'entrée, gestionnaire d'états (menu, TPS, transition, FPS, pause, game over, victoire)
├── config.py       toutes les constantes (sensibilité, vitesses, seed, dégâts, volume, index manette...)
├── controller.py   manette PS5 via pygame.joystick + fusion clavier/souris (InputManager), debug F3
├── shuttle.py      navette pilotable (6DDL simplifié, inertie), caméra TPS lissée, atterrissage/décollage
├── exterior.py     extérieur du grand vaisseau : coque, superstructure, débris, balises, collisions OBB/AABB
├── generator.py    génération procédurale de l'intérieur (grille, salles, couloirs A*, conduits, collisions)
├── rooms.py        construction et décoration de chaque type de salle, portes, grilles, fenêtres, meshes fusionnés
├── player.py       contrôleur FPS (marche, course/endurance, accroupi, santé, bruit, interactions, cachette)
├── weapons.py      pistolet (hitscan, visée, recul, flash, chargeur) et couteau (durabilité)
├── inventory.py    inventaire limité, objet équipé, menu d'inventaire SANS pause, lecture des notes
├── loot.py         casiers, cadavres (parfois infestés), objets, notes de l'équipage, disque dur, tables pondérées
├── creature.py     IA de la grande créature (A*, états, perception) + directrice d'IA
├── aliens.py       IA des petites créatures (mouvement saccadé, bonds, apparitions)
├── horror.py       mode horreur, propagation du bruit, tension, battements de cœur, événements d'ambiance
├── lighting.py     lumière ambiante, lampe torche, pool de lumières dynamiques, néons, alarmes, vision nocturne
├── space.py        skybox : milliers d'étoiles, nébuleuse, planètes (dont une à anneaux), soleil
├── audio.py        synthèse numpy -> .wav au premier lancement, lecture 2D/3D/boucles
├── hud.py          HUD TPS/FPS, messages en fondu, surimpressions, écrans de menu
├── geometry.py     (utilitaire) construction de meshes fusionnés (boîtes, cylindres, décalques)
├── textures.py     (utilitaire) textures générées par code (panneaux, sang, grain, étoiles, planètes...)
├── requirements.txt
└── generated/      créé au premier lancement (sons .wav)
```

## Plan technique (résumé)

* **Monde cohérent** : l'intérieur est généré sur une grille 2D (seed). La coque extérieure enveloppe exactement
  l'empreinte de la grille : le hangar extérieur (flanc sud, `z = 0`) **est** le hangar intérieur, et les lumières
  des hublots vus de l'extérieur sont placées sur les fenêtres réelles de l'intérieur.
* **Génération** : hangar fixé contre la coque, salle de commandement placée le plus loin possible, autres salles
  sans chevauchement → arbre couvrant minimal (Prim) + boucles → couloirs creusés par A* avec pénalité de virage
  (couloirs droits avec coudes) → conduits d'aération creusés dans les cloisons → fenêtres sur la coque.
  L'architecture (`ShipLayout.decks`) est prête pour plusieurs ponts (`DECK_COUNT`).
* **Murs = arêtes de la grille** : collisions (boîtes avec plage verticale : on passe sous le mur d'une grille
  seulement accroupi), portes, lignes de vue et tirs (DDA exact sur la grille) sont rapides et fiables.
* **Rendu 60 FPS** : chaque salle / bloc de couloirs est fusionné en quelques meshes ; les salles éloignées sont
  désactivées ; seules les `MAX_POINT_LIGHTS` lumières les plus proches sont de vraies lumières (pool),
  les autres néons sont émissifs ; éclairage par pixel (shader automatique de Panda3D) + brouillard.
* **Étapes de la spécification** : les 5 étapes (intérieur + FPS + manette + fenêtres ; TPS + extérieur +
  transition ; armes + lampe + vision nocturne + loot ; créatures + mode horreur ; audio + HUD + objectif + fins)
  sont toutes implémentées dans cette version.

---

## Installation et lancement

Prérequis : **Python 3.11+** et une carte graphique compatible OpenGL 3.2+.

```bash
cd horreur_spatiale
python -m venv .venv
# Windows : .venv\Scripts\activate      macOS / Linux : source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Au premier lancement, les sons sont synthétisés dans `generated/sounds/` (environ une seconde).
La génération du vaisseau prend 2 à 4 secondes à chaque nouvelle partie.
La seed est affichée dans le menu pause ; fixe `SEED` dans `config.py` pour rejouer la même épave.

## Contrôles

| Action | Clavier / souris (AZERTY) | Manette PS5 |
|---|---|---|
| **Navette** : poussée / strafe | Z Q S D | stick gauche |
| orientation (tangage / lacet) | souris | stick droit |
| monter / descendre | Espace / Ctrl | R2 / L2 |
| roulis | A / E | L1 / R1 |
| boost | Maj | Croix |
| **À pied** : se déplacer / regarder | Z Q S D + souris | stick gauche / stick droit |
| courir | Maj | L3 |
| s'accroupir (bascule) | Ctrl | Rond |
| viser / tirer | clic droit / clic gauche | L2 / R2 |
| couteau | A | R1 |
| recharger | R | Carré |
| lampe torche | L | Triangle |
| vision nocturne (casque requis) | N | L1 |
| interagir / fouiller (maintenir) | E | Croix |
| kit de soin | H | Flèche haut |
| changer d'objet équipé / l'utiliser | C, V ou molette / F | Flèches gauche-droite / Flèche bas |
| inventaire (le jeu continue !) | Tab | Pavé tactile |
| pause | Échap | Options |
| debug manette | F3 | — |

Dans l'inventaire : flèches/molette pour choisir, **E/Entrée** (Croix) pour utiliser, **Suppr** (Triangle) pour jeter.
`KEYBOARD_LAYOUT = "qwerty"` dans `config.py` pour un clavier QWERTY (WASD).
Ursina lit les lettres par position physique : la configuration AZERTY est convertie automatiquement.

## Conseils de survie

* Marcher fait du bruit, courir beaucoup, accroupi presque rien ; l'indicateur **BRUIT** du HUD te le montre.
* La lampe te fait repérer de plus loin. La vision nocturne voit dans le noir mais les néons éblouissent.
* Tirer sur la grande créature la ralentit ; trois balles la font fuir dans les conduits… un moment.
* Un casier vide sert de cachette — mais jamais sous ses yeux.
* Les cadavres se fouillent (maintenir E) : tu es vulnérable pendant la fouille, et certains sont infestés.
* Avec le disque dur, le vaisseau se réveille : plus de parasites, la créature te cherche.

## Réglages utiles (`config.py`)

* Difficulté : `CREATURE_SPEED_CHASE`, `CREATURE_VIEW_DIST`, `ALIEN_MAX`, `ALIEN_DAMAGE`, `PISTOL_START_*`,
  `OBJECTIVE_COMPASS = False` (plus de flèche d'objectif).
* Performances : `MAX_POINT_LIGHTS` (4 sur un petit GPU), `CULL_DISTANCE`, `WINDOW_SIZE`, `VSYNC`, `FOG_DENSITY_FPS`.
* Manette : `GAMEPAD_DEADZONE`, `GAMEPAD_LOOK_SPEED`, `GAMEPAD_LOOK_CURVE`, `GAMEPAD_INVERT_Y`, `GAMEPAD_RUMBLE`,
  `GAMEPAD_PROFILE` et tous les index d'axes/boutons dans `GAMEPAD_PROFILES`.

---

## Dépannage manette

Commence toujours par **F3** en jeu : le panneau affiche le nom de la manette, le profil choisi, la valeur de
chaque axe et l'index de chaque bouton appuyé. Si un bouton ne correspond pas, corrige son index dans
`GAMEPAD_PROFILES` (`config.py`) ou force un profil avec `GAMEPAD_PROFILE` (`"sdl"`, `"directinput"`, `"evdev"`).
La manette peut être branchée ou rebranchée à tout moment (détection automatique).

**Généralités**
* En USB, utilise un câble USB-C **de données** (certains câbles ne font que charger).
* Appairage Bluetooth : maintiens **Create + PS** jusqu'au clignotement rapide de la barre lumineuse.
* Gâchettes L2/R2 bloquées à moitié ? Appuie une fois à fond sur chacune : certains pilotes renvoient 0 au lieu
  de -1 avant le premier appui (le jeu l'ignore jusqu'à ce qu'il voie une vraie valeur).
* Aucune détection alors qu'elle apparaît dans le système : mets `GAMEPAD_SDL_DUMMY_VIDEO = False`.

**Windows**
* **Steam** intercepte souvent la DualSense (Steam Input) : ferme Steam, ou désactive
  « Prise en charge de la configuration PlayStation » dans Paramètres Steam → Manette.
* **DS4Windows / DSX** : désactive-les ou coupe le mode « masquer la manette », sinon le jeu voit une manette
  Xbox virtuelle avec d'autres index (vérifie avec F3).
* Si le panneau F3 indique 14 boutons + 1 croix, c'est le profil `directinput` (choisi automatiquement).
* Vibrations absentes en Bluetooth : mets pygame à jour (`pip install -U pygame`) ; le jeu active déjà
  `SDL_JOYSTICK_HIDAPI_PS5_RUMBLE`.

**macOS**
* Appaire la manette dans Réglages Système → Bluetooth (ou branche-la en USB).
* Autorise le terminal (ou ton IDE) dans Réglages Système → Confidentialité et sécurité → **Surveillance de
  l'entrée**, puis relance le terminal.
* Ferme Steam s'il est ouvert (même remarque que sous Windows).

**Linux**
* Noyau 5.12+ recommandé (pilote `hid-playstation`).
* Pour que SDL utilise HIDAPI (index du profil `sdl`, pavé tactile et vibrations), donne l'accès aux périphériques
  hidraw avec une règle udev, par exemple `/etc/udev/rules.d/70-dualsense.rules` :
  ```
  KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", MODE="0660", TAG+="uaccess"
  KERNEL=="hidraw*", KERNELS=="*054C:0CE6*", MODE="0660", TAG+="uaccess"
  KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0df2", MODE="0660", TAG+="uaccess"
  ```
  puis `sudo udevadm control --reload-rules && sudo udevadm trigger` et rebranche la manette
  (`0ce6` = DualSense, `0df2` = DualSense Edge ; la 2e ligne couvre le Bluetooth).
* Sans cet accès, SDL passe par evdev : 13 boutons + 1 croix → profil `evdev` automatique ; le clic du pavé
  tactile n'existe pas dans ce mode, le bouton **Create** ouvre alors l'inventaire.
* Bluetooth : `bluetoothctl` → `scan on`, `pair <adresse>`, `trust <adresse>`, `connect <adresse>`.
* Sous Wayland/X11, rien à régler côté vidéo (pygame n'ouvre aucune fenêtre).

## Limitations connues

* Un seul pont est généré (l'architecture multi-ponts est prête mais sans escaliers/ascenseurs).
* Pas de sauvegarde en cours de partie.
* Le son 3D est une spatialisation simple (volume + balance), sans occlusion par les murs.
