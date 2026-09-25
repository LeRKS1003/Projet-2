# DÉRIVE — FPS d'horreur spatiale en Python

Vous vous réveillez seul à bord d'un vaisseau à la dérive. Quelque chose rôde dans les
couloirs et les conduits d'aération. Pas d'arme : il faut fuir, se cacher, et avancer
en silence.

**Objectif** : rétablir le courant dans la **salle des machines**, récupérer le code
d'accès dans la **salle de commandement**, puis fuir en **navette** depuis le **hangar**.

Ambiance : *Alien* (1979), *Dead Space*, *SOMA* — néons qui clignotent, alarmes rouges,
grincements métalliques, baies vitrées sur l'espace, silence oppressant.

---

## Arborescence

```
horreur_spatiale/
├── main.py          point d'entrée, boucle de jeu, états (menu, jeu, pause, game over, victoire), objectifs
├── config.py        toutes les constantes (sensibilité, vitesses, grille, seed, volume, mapping manette...)
├── generator.py     génération procédurale du vaisseau (salles, graphe, couloirs A*, portes, hublots, conduits)
├── rooms.py         construction et décoration de chaque type de salle + couloirs (props, casiers, piles, journaux)
├── world.py         géométrie 3D fusionnée par blocs, portes coulissantes, grilles, collisions, ligne de vue, culling
├── geometry.py      MeshBuilder (fusion de meshes avec normales) + bruit et textures procédurales (numpy)
├── player.py        contrôleur FPS clavier/souris + manette, bruit, endurance, lampe, casiers
├── controller.py    manette PS5 DualSense via pygame.joystick (SDL2), USB/Bluetooth, vibrations, debug F3
├── creature.py      IA de la créature (A*, machine à états) + directrice d'IA
├── lighting.py      ambiance, brouillard, lampe torche, néons, alarmes, pool de lumières dynamiques
├── space.py         skybox : milliers d'étoiles, planètes (dont une à anneaux), nébuleuse, dérive lente
├── audio.py         synthèse des sons (numpy -> .wav au 1er lancement) + spatialisation simple
├── hud.py           HUD minimaliste, messages en fondu, carte partielle, écrans de menu
├── requirements.txt
└── sons/            (créé automatiquement au premier lancement)
```

## Plan technique (résumé)

1. **Génération** (`generator.py`) — grille 2D (1 case = 1 m), seed aléatoire ou fixée.
   Salles obligatoires de tailles différentes placées sans chevauchement (compactes), graphe
   *arbre couvrant minimal + boucles*, couloirs de 2–3 cases creusés par A* avec pénalité de
   virage (coudes) et fusion des couloirs, portes de 2 cases, hublots/baies vitrées là où
   un mur donne directement sur le vide, puis réseau de conduits d'aération (grilles d'accès
   dans les murs). Une validation garantit que la progression est toujours possible.
   Le modèle (`Vaisseau` → liste de `Pont`) est prévu pour plusieurs ponts.
2. **Rendu** (`world.py`, `rooms.py`) — uniquement des primitives. Les murs ne sont émis
   qu'aux frontières sol/mur ; tout est fusionné en un mesh par matériau et par bloc de 16×16
   cases (et un mesh de décor par salle). Les blocs et salles éloignés sont désactivés.
3. **Éclairage** (`lighting.py`) — shaders automatiques de Panda3D (éclairage par pixel,
   brouillard). Des centaines de sources logiques, mais seules les 6 plus proches sont
   rendues via un pool de `PointLight` : coût constant.
4. **IA** (`creature.py`) — A* sur la grille (couloirs + conduits), états
   ERRANCE / ENQUÊTE / TRAQUE / RECHERCHE / RETRAITE, vision en cône + ligne de vue, ouïe.
   La directrice d'IA rapproche la créature si le joueur est tranquille trop longtemps et
   la fait battre en retraite après une longue traque.
5. **Audio** (`audio.py`) — tous les sons sont synthétisés (réacteur, pas métalliques,
   grincements, souffle, grattements, cri, alarme...) puis joués avec volume selon la
   distance, panoramique gauche/droite et atténuation derrière les murs.

---

## Installation

Python **3.11 ou plus récent** est requis.

```bash
cd horreur_spatiale
python -m venv .venv
# Windows : .venv\Scripts\activate      macOS / Linux : source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

Au premier lancement, les sons sont générés dans `sons/` (moins d'une seconde).
La génération d'un vaisseau prend environ une seconde.

Pour rejouer toujours le même vaisseau, fixez `SEED = 12345` dans `config.py`.
Dans le menu, **N** change de vaisseau.

## Contrôles

| Action | Clavier / souris (AZERTY) | Manette PS5 |
|---|---|---|
| Se déplacer | Z Q S D (WASD et flèches aussi) | Stick gauche |
| Regarder | Souris | Stick droit |
| Courir | Maj (maintenir) | L3 (bascule, tant qu'on avance) |
| S'accroupir | Ctrl (maintenir) | R3 ou Rond (bascule) |
| Interagir (portes, grilles, casiers, objets) | E | Croix |
| Lampe torche | F | Carré |
| Lampe concentrée (plus puissante, vide la batterie) | Clic droit | R2 |
| Carte partielle | Tab (ou M) | Pavé tactile |
| Pause | Échap | Options |
| Debug (FPS, IA, mapping manette) | F3 | — |

Conseils : courir fait beaucoup de bruit, marcher un peu, s'accroupir presque pas.
Les conduits d'aération (grilles au ras du sol) ne sont accessibles qu'accroupi — la
créature les emprunte aussi. Les casiers des chambres permettent de se cacher... si elle
ne vous a pas vu y entrer. Les piles rechargent la lampe ; les journaux de bord donnent
des indices.

## Réglages utiles (`config.py`)

* `SENSIBILITE_SOURIS`, `SENSIBILITE_MANETTE`, `ZONE_MORTE_STICK`, `EXPOSANT_COURBE_STICK`
* `PLEIN_ECRAN`, `TAILLE_FENETRE`, `FOV`, `AFFICHER_FPS`
* Performances : `ANTICRENELAGE` (0 pour désactiver), `NB_LUMIERES_ACTIVES`,
  `DISTANCE_CULLING`, `NB_ETOILES`
* Difficulté : vitesses et portées de vue de la créature, `CREATURE_DELAI_DEPART`,
  `DIRECTEUR_CALME_MAX`, `LAMPE_DUREE_BATTERIE`, `NB_PILES`

Le jeu vise 60 FPS sur un PC de milieu de gamme : la logique Python coûte environ
1,5 ms par image, le reste est du rendu GPU (quelques centaines d'appels de dessin grâce
à la fusion des meshes et au culling). Si besoin, baissez `ANTICRENELAGE` puis
`NB_LUMIERES_ACTIVES`.

---

## Dépannage manette

La manette est détectée automatiquement au lancement **et** à la (re)connexion. Le jeu
reste entièrement jouable au clavier/souris sans manette.

Appuyez sur **F3** en jeu : l'écran de debug affiche le nom de la manette, le profil
utilisé, la valeur brute de chaque axe et l'état de chaque bouton. Si un bouton ne
correspond pas, corrigez son index dans `MANETTE_PROFILS` (`config.py`). Deux profils sont
fournis :

* `"sdl"` : pilote HIDAPI de SDL2 (Windows, macOS, Linux avec accès hidraw) ;
* `"linux"` : pilote noyau `hid-playstation` (13 boutons + croix directionnelle en « chapeau »).

`MANETTE_PROFIL = "auto"` choisit selon le nombre de boutons détectés ; vous pouvez forcer
l'un ou l'autre.

### Windows

* **USB** : utilisez un câble USB‑C qui transporte les données (certains câbles ne font
  que la charge).
* **Bluetooth** : Paramètres → Bluetooth → Ajouter un appareil, en maintenant **PS + Create**
  jusqu'à ce que la barre lumineuse clignote.
* **Steam** ouvert avec « Prise en charge des manettes PlayStation » peut s'approprier la
  manette : fermez Steam ou désactivez cette option pour ce jeu.
* **DS4Windows / DSX** créent une manette Xbox virtuelle : le jeu verrait deux manettes ou
  un mapping Xbox. Fermez-les.
* Pas de vibrations en Bluetooth : mettez pygame à jour (`pip install -U pygame`, SDL ≥ 2.26).

### macOS

* Appairage : Réglages Système → Bluetooth (maintenir **PS + Create**).
* Si la manette n'est pas détectée : Réglages Système → Confidentialité et sécurité →
  **Surveillance de l'entrée** → autorisez votre Terminal (ou l'IDE) puis relancez-le.
* Le jeu utilise le pilote vidéo SDL « dummy » pour ne pas ouvrir de seconde fenêtre. En
  cas de souci, essayez `SDL_PILOTE_VIDEO = None` dans `config.py`.
* Les vibrations en Bluetooth peuvent être indisponibles selon la version de macOS ; en USB
  elles fonctionnent.

### Linux

* Noyau ≥ 5.12 recommandé (pilote `hid-playstation`). Vérifiez la détection avec
  `evtest` ou `jstest-gtk`.
* Pour le pilote HIDAPI de SDL (mapping « sdl », vibrations, Bluetooth), donnez l'accès
  à `hidraw` avec une règle udev, par exemple `/etc/udev/rules.d/70-dualsense.rules` :

  ```
  KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", MODE="0660", TAG+="uaccess"
  KERNEL=="hidraw*", KERNELS=="*054C:0CE6*", MODE="0660", TAG+="uaccess"
  ```

  puis `sudo udevadm control --reload-rules && sudo udevadm trigger` et rebranchez la
  manette (`0df2` pour la DualSense Edge).
* Bluetooth : `bluetoothctl` → `scan on`, `pair <MAC>`, `trust <MAC>`, `connect <MAC>`
  (manette en mode appairage : **PS + Create**).
* Si les boutons sont décalés, forcez `MANETTE_PROFIL = "linux"` ou `"sdl"` et vérifiez
  avec **F3**.
* Steam Input peut aussi capturer la manette : fermez Steam pendant le jeu.
