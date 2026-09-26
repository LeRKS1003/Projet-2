# ÉPAVE — Le silence du Mnémosyne

Jeu d'horreur spatial en Python (Ursina + pygame + numpy), ambiance *Alien* (1979), *Dead Space*, *SOMA*.
Aucun asset externe : toute la géométrie est faite de primitives, les textures et les sons sont générés par code.

1. **Phase 1 – Approche (TPS)** : tu pilotes une navette autour d'un immense vaisseau abandonné qui dérive
   (antennes, panneaux solaires arrachés, débris qui tournent). Trouve l'ouverture du hangar grâce aux balises
   rouges/vertes et à la flèche du HUD. Chaque collision abîme la coque. Une fois l'ouverture franchie, la navette
   se pose toute seule, l'écran s'assombrit, tu sors à pied.
2. **Phase 2 – Exploration (FPS)** : le vaisseau est **plongé dans le noir total** (plus de courant). Retrouve
   2 ou 3 fusibles, rétablis le courant dans la salle des machines, puis atteins la salle de commandement
   (verrouillée tant qu'il n'y a pas de courant), récupère le disque dur, reviens au hangar et repars. Une grande créature invulnérable rôde ; de petits parasites attaquent. **Chaque tir déclenche le
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
├── lighting.py     lumière ambiante, lampe torche, pool de lumières, néons, vision nocturne, PowerManager (courant)
├── power.py        courant du vaisseau : fusibles, tableau et levier, séquence de redémarrage, coupures, portes
├── screamer.py     casier piégé (jumpscare) : visage en primitives, cri, stinger, musique qui suit
├── space.py        skybox : milliers d'étoiles, nébuleuse, planètes (dont une à anneaux), soleil
├── audio.py        synthèse numpy -> .wav au premier lancement, lecture 2D/3D/boucles
├── hud.py          HUD TPS/FPS, messages en fondu, surimpressions, écrans de menu
├── postfx.py       post-traitement (bloom, SSAO, gamma) + couche séparée de l'arme (viewmodel)
├── geometry.py     meshes fusionnés avec tangentes (boîtes biseautées, extrusions, cônes, décalques)
├── textures.py     textures et matériaux procéduraux (albédo + normal map + rugosité), cache disque
├── requirements.txt
├── sounds/         tes propres sons (ex. screamer.wav / screamer.ogg remplace le cri généré)
└── generated/      créé au premier lancement (sons .wav, textures .png en cache)
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
| assistance de vol (on/off) | F | Triangle |
| frein d'urgence | X (maintenir) | Rond (maintenir) |
| caméra rapprochée / éloignée | C | R3 |
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
| test : basculer le courant / déclencher le screamer | F4 / F5 | — |

Dans l'inventaire : flèches/molette pour choisir, **E/Entrée** (Croix) pour utiliser, **Suppr** (Triangle) pour jeter.
`KEYBOARD_LAYOUT = "qwerty"` dans `config.py` pour un clavier QWERTY (WASD).
Ursina lit les lettres par position physique : la configuration AZERTY est convertie automatiquement.

## Conseils de survie

* Marcher fait du bruit, courir beaucoup, accroupi presque rien ; l'indicateur **BRUIT** du HUD te le montre.
* La lampe te fait repérer de plus loin. La vision nocturne voit dans le noir mais les néons éblouissent.
* Tirer sur la grande créature la ralentit ; trois balles la font fuir dans les conduits… un moment.
* Un casier vide sert de cachette — mais jamais sous ses yeux.
* Les araignées sont rares (3 au maximum, en groupes de 1 à 3). Au couteau, une araignée qui ne t'a
  pas repéré meurt instantanément et en silence (« Mise à mort silencieuse »). Un coup de couteau reste
  discret : la bête ne l'entend que tout près, et rarement ; en revanche une araignée blessée crie.
* Écoute : les grattements étouffés viennent de derrière les cloisons ou des conduits.

## Le courant du vaisseau

* **Au début, tout est éteint.** Sans lampe, on ne voit presque rien. Seules sources de lumière : ta lampe
  torche (et la vision nocturne), la très faible lueur bleutée des étoiles près des hublots et baies vitrées,
  le phare et les feux de la navette posée dans le hangar, quelques voyants de batterie de secours, les
  étincelles des câbles arrachés, les yeux des créatures… et le **flash de chaque tir**, qui éclaire la pièce.
* **Portes sans courant** : certaines sont entrouvertes (on passe), d'autres se **forcent** (maintenir E /
  Croix, très bruyant : la créature entend), d'autres sont **bloquées** : il faut passer par les conduits.
  La salle de commandement est **verrouillée électriquement** (portes et grilles).
* **Rétablir le courant** : trouve les 2 ou 3 fusibles (salle des machines et salles voisines ; leur bande
  réfléchissante et un petit voyant ambré les trahissent à la lampe), insère-les dans le tableau électrique
  de la salle des machines, puis abaisse le gros levier. Silence… le réacteur démarre, la lumière revient
  salle par salle depuis la salle des machines, chaque néon clignote avant de s'allumer, et 20 à 30 % des
  lampes restent cassées. **Ce vacarme réveille tout le vaisseau** (mode horreur, créature, parasites).
* Ensuite l'éclairage reste sombre et contrasté, et de rares **coupures** surviennent, surtout en mode horreur
  ou quand la grande créature est proche.
* **Trop difficile ?** `EMERGENCY_STRIPS = True` ajoute de faibles bandes de secours rouges au ras du sol.
* Réglages : `AMBIENT_POWER_OFF` / `AMBIENT_POWER_ON` (≈ 0,01), `FOG_DENSITY_POWER_*`, `LIGHT_INTENSITY`,
  `LIGHT_COLOR_WARM` / `COLD`, `STARLIGHT_*`, `POWER_*` (fusibles, part de lampes cassées, vitesse de
  propagation, coupures), `DOOR_*` (portes entrouvertes / bloquées, durée pour forcer), `POWER_START_OFF`.

## Le casier piégé

Un casier (hors hangar, et jamais dans la première salle que tu visites) cache une mauvaise surprise, une
seule fois par partie. Aucun indice visuel. Réglages : `SCREAMER_ENABLED`, `SCREAMER_VOLUME`,
`SCREAMER_FLASH` (mets `False` si tu es sensible aux flashs lumineux). Pour utiliser ton propre cri, place
`screamer.wav` ou `screamer.ogg` dans le dossier `sounds/`. **F5** le déclenche pour le tester
(`DEBUG_KEYS = False` désactive F4/F5).

## Pilotage de la navette

* **Assistance de vol** (par défaut) : la navette va là où pointe le nez, annule sa dérive, freine quand
  tu lâches la poussée et remet ses ailes à plat. Avec le **régulateur** (`SHIP_CRUISE`), la poussée
  règle une vitesse cible affichée sous la vitesse. Sans assistance : inertie pure.
* Près du hangar, des pointillés lumineux montrent l'axe d'approche et le HUD conseille la vitesse
  (8 m/s). « OBSTACLE DROIT DEVANT » s'affiche quand un obstacle est à moins de 3 s de vol.
* Les frottements à basse vitesse n'abîment plus la coque ; seuls les vrais impacts comptent.
* Réglages : `SHIP_ASSIST_*`, `SHIP_CRUISE*`, `SHIP_BRAKE_RATE`, `SHIP_LOOK_DEADZONE`,
  `SHIP_LOOK_EXPONENT`, `SHIP_MAX_TURN`, `SHIP_TURN_DAMP`, `SHIP_MOUSE_SENS`, `TPS_CAM_FAR_*`.
* Les cadavres se fouillent (maintenir E) : tu es vulnérable pendant la fouille, et certains sont infestés.
* Avec le disque dur, le vaisseau se réveille : plus de parasites, la créature te cherche.

## Qualité graphique

`QUALITY` dans `config.py` (ou la variable d'environnement `EPAVE_QUALITE=basse|moyenne|haute`) :

| Effet | Basse | Moyenne (défaut) | Haute |
|---|---|---|---|
| Éclairage par pixel | oui | oui | oui |
| Normal maps + reflets spéculaires | non | oui | oui |
| Bloom (néons, réacteurs, flash) | non | oui | oui |
| Correction gamma | non (*) | non (*) | non (*) |
| Occlusion ambiante (SSAO) | non | non | oui |
| Ombres de la lampe torche | non | 1024 px | 2048 px |
| Masque « cookie » de la lampe | non | oui | oui |
| Cône volumétrique + poussière | non | oui (36) | oui (80) |
| Lumières dynamiques simultanées | 4 | 6 | 8 |
| Particules (traînées, fumée…) | ×0,5 | ×1 | ×1,5 |

| Lumières du décor projetant des ombres (en plus de la lampe) | 0 | 0 | 1 |

(*) La correction gamma éclaircit les noirs : elle est désormais à 1,0 (désactivée) pour que le vaisseau sans
courant soit vraiment noir. Tu peux la remettre (`"gamma": 1.15`) si ton écran est très sombre.
Seules les lumières des salles proches **en suivant les passages** sont rendues (`LIGHT_REACH_CELLS`) :
pas de lumière qui traverse les murs, et un coût constant.

**Si le jeu n'atteint pas 60 FPS en Moyenne**, baisse dans cet ordre : ombres de la lampe
(`"shadows": False` ou `"shadow_size": 512`), nombre de lumières (`"point_lights": 4`), bloom,
puis `WINDOW_SIZE`. `CULL_DISTANCE` (salles actives autour du joueur) aide aussi sur les petits GPU.

## Réglages utiles (`config.py`)

* Difficulté : `CREATURE_SPEED_CHASE`, `CREATURE_VIEW_DIST`, `ALIEN_MAX`, `ALIEN_DAMAGE`, `PISTOL_START_*`,
  `OBJECTIVE_COMPASS = False` (plus de flèche d'objectif).
* Performances : `QUALITY`, `CULL_DISTANCE`, `WINDOW_SIZE`, `VSYNC`, `LIGHT_REACH_CELLS`.
* Lampe torche : `FLASHLIGHT_TEMPERATURE` (kelvins), `FLASHLIGHT_INTENSITY`, `FLASHLIGHT_ATTENUATION`
  (constante, linéaire, quadratique), `FLASHLIGHT_FOV`, `FLASHLIGHT_OFFSET`, `FLASHLIGHT_LAG`.
  Quand elle scintille (batterie < 10 %), **Recharger** (R / Carré) tape dessus et la rallume quelques secondes.
* Arme : `VIEWMODEL_FOV` (champ de vision propre de l'arme). Rendu : `BLOOM_INTENSITY`, `BLOOM_THRESHOLD`.
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

## Dépannage affichage

* **Tout est éclairé à fond, même sans lampe** : c'est le shader « unlit » par défaut d'Ursina 8. `main.py` le
  désactive (`Entity.default_shader = None`). Au chargement, la console affiche une vérification
  `[éclairage] vérification du vaisseau : … 0 entité(s) non éclairée(s)` : si un nombre non nul apparaît,
  les noms fautifs sont listés juste en dessous.
* **Trop sombre sur ton écran** : augmente un peu `AMBIENT_POWER_OFF` (ex. 0.02) ou `FLASHLIGHT_INTENSITY`.

## Limitations connues

* Un seul pont est généré (l'architecture multi-ponts est prête mais sans escaliers/ascenseurs).
* Pas de sauvegarde en cours de partie.
* Le son 3D est une spatialisation simple (volume + balance), sans occlusion par les murs.
