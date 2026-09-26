# -*- coding: utf-8 -*-
"""
story.py — L'histoire de DÉRIVE : bible, équipage et documents.

Ce fichier ne contient QUE des données : tu peux modifier les textes
librement sans toucher au code. Les documents sont placés par le
générateur (rooms.py), affichés par document_ui.py et altérés par
hallucinations.py.

BIBLE (pour garder la cohérence)
--------------------------------
* Année 2187. Le KERGUELEN, vaisseau de recherche de la société Helios Biotech.
* Mission officielle : échantillons minéraux sur l'astéroïde 2187-KX, « Charon ».
* Mission réelle : ramener SINUS (Souche Isolée Neurotrope Ultra-Stable), un
  « cristal » gris découvert dans la glace de Charon, qui vibre à 7 Hz.
* La vérité : SINUS est un virus aéroporté. Il passe par la ventilation,
  attaque le cerveau et provoque des hallucinations construites à partir des
  peurs de chacun ; les infectés finissent tous par voir la même créature.
  Les créatures n'ont jamais existé : l'équipage s'est entretué, caché,
  blessé tout seul. Helios le savait et voulait en faire une arme.
* Le joueur est un agent de récupération d'Helios. Il respire l'air du
  vaisseau dès le hangar : il est contaminé dès le début. Les grandes et
  petites créatures sont des hallucinations (révélé à la fin).

Champs d'un document
--------------------
  id          identifiant (D01...)
  type        officiel / note / cahier / fiche / rapport / journal / audio / image / lettre / postit
  style       rendu à l'écran : helios (papier officiel), paper (papier jauni manuscrit),
              form (fiche typographiée), terminal (écran vert), audio (transcription),
              postit, photo (image granuleuse)
  title       titre affiché dans le journal
  author      auteur
  day         jour de la mission (ordre chronologique du journal)
  room        type de salle : hangar, crew, medbay, mess, engine, command, corridor
  place       emplacement : desk, console, workbench, bed, fridge, door, floor, panel,
              corpse:<membre d'équipage>, near_screamer
  guaranteed  True = toujours présent dans la partie
  image       image générée par code (drawing, brainscan, vents, waveform) ou None
  text        contenu
  variants    phrases modifiées par l'hallucination à la relecture : liste de (avant, après)
"""

GAME_TITLE = "DÉRIVE"
TITLE_SUBTITLE = "Kerguelen — dernier contact il y a 41 jours"
SHIP_NAME = "KERGUELEN"
COMPANY = "HELIOS BIOTECH"

# ----------------------------------------------------------------------------
# L'ÉQUIPAGE (7 personnes). Keating : son corps n'est jamais retrouvé.
# ----------------------------------------------------------------------------
CREW = {
    "vasseur": {"name": "Commandante Irène Vasseur", "room": "command", "uniform": (.16, .19, .32)},
    "keating": {"name": "Dr Mara Keating, cheffe scientifique", "room": None, "uniform": (.75, .75, .72)},
    "okafor": {"name": "Dr Samuel Okafor, médecin", "room": "mess", "uniform": (.62, .66, .68)},
    "lebrun": {"name": "Tomasz Lebrun, ingénieur en chef", "room": "engine", "uniform": (.45, .3, .15)},
    "fontaine": {"name": "Léa Fontaine, pilote", "room": "hangar", "uniform": (.2, .3, .22)},
    "andreiev": {"name": "Yuri Andreïev, technicien de laboratoire", "room": "medbay", "uniform": (.32, .34, .36)},
    "ricci": {"name": "Paolo Ricci, cuisinier et intendant", "room": "mess", "uniform": (.7, .68, .6)},
}

# ----------------------------------------------------------------------------
# LES DOCUMENTS (D01 à D15 à trouver à bord ; D16 = contenu du disque dur)
# ----------------------------------------------------------------------------
DOCUMENTS = [
    {
        "id": "D01", "type": "officiel", "style": "helios",
        "title": "Ordre de mission", "author": "Helios Biotech", "day": 0,
        "room": "hangar", "place": "workbench", "guaranteed": True, "image": None,
        "text": "CONFIDENTIEL — NIVEAU 4.\n\n"
                "Kerguelen, objectif principal : récupération de l'échantillon Charon-01 (projet SINUS).\n\n"
                "L'équipage n'est informé que de la mission minéralogique. Toute anomalie biologique doit être "
                "signalée uniquement à la Dr Keating. Aucune communication externe concernant SINUS n'est autorisée.",
        "variants": [],
    },
    {
        "id": "D02", "type": "note", "style": "paper",
        "title": "Note sur la console d'amarrage", "author": "Léa Fontaine", "day": 1,
        "room": "hangar", "place": "console", "guaranteed": False, "image": None,
        "text": "Amarrage sur Charon OK. Le conteneur scellé est monté directement au labo, Keating n'a laissé "
                "personne le toucher. Elle a dit « minéral ». Un minéral dans un conteneur de niveau 4 ? Bon. "
                "Moi je pilote, je pose pas de questions.",
        "variants": [],
    },
    {
        "id": "D03", "type": "cahier", "style": "paper",
        "title": "Cahier personnel — jour 3", "author": "Yuri Andreïev", "day": 3,
        "room": "crew", "place": "desk", "guaranteed": False, "image": None,
        "text": "Le cristal est magnifique. Gris, presque liquide sous la lumière. Et il vibre : 7 hertz, "
                "parfaitement réguliers, une sinusoïde pure. On l'appelle SINUS maintenant, Keating trouve ça "
                "drôle.\n\nLa nuit j'ai l'impression de l'entendre à travers les murs. C'est impossible, le labo "
                "est à l'autre bout du vaisseau.",
        "variants": [("à travers les murs", "à travers mon oreiller")],
    },
    {
        "id": "D04", "type": "fiche", "style": "form",
        "title": "Fiche médicale — Y. Andreïev", "author": "Dr Samuel Okafor", "day": 9,
        "room": "medbay", "place": "corpse:andreiev", "guaranteed": False, "image": None,
        "text": "PATIENT : Yuri ANDREÏEV — JOUR 9\n\n"
                "Motif : céphalées persistantes, pression dans les sinus, acouphène grave constant. Troubles du "
                "sommeil. Le patient affirme « entendre le cristal ».\n\n"
                "Diagnostic : stress et fatigue liés à l'isolement.\n"
                "Traitement : repos, anxiolytiques.\n\n"
                "Note : deuxième patient cette semaine avec les mêmes symptômes (voir Ricci).\n\n"
                "Signé : Dr S. Okafor",
        "variants": [],
    },
    {
        "id": "D05", "type": "note", "style": "paper",
        "title": "Mot affiché sur le frigo", "author": "Paolo Ricci", "day": 8,
        "room": "mess", "place": "fridge", "guaranteed": False, "image": None,
        "text": "À celui qui descend manger dans la chambre froide la nuit : j'ai trouvé des traces de griffes "
                "sur la porte. Très drôle. Si c'est une blague, arrêtez. Si c'est pas une blague, dites-le-moi.\n\n"
                "Menu de jeudi : ragoût. Encore.",
        "variants": [("des traces de griffes", "des traces d'ongles")],
    },
    {
        "id": "D06", "type": "cahier", "style": "paper",
        "title": "Cahier de laboratoire — jour 11", "author": "Dr Mara Keating", "day": 11,
        "room": "crew", "place": "desk", "guaranteed": True, "image": None,
        "text": "Incident au labo : micro-fissure dans l'enceinte de confinement pendant le test de résonance. "
                "Durée d'exposition estimée : 40 secondes. Les filtres de ventilation ont été changés.\n\n"
                "Je n'ai rien déclaré. Helios arrêterait le projet, et nous sommes si proches.\n\n"
                "Yuri tousse depuis ce matin. Coïncidence.",
        "variants": [],
    },
    {
        "id": "D07", "type": "image", "style": "photo",
        "title": "Dessin sur une page arrachée", "author": "Yuri Andreïev", "day": 13,
        "room": "crew", "place": "bed", "guaranteed": False, "image": "drawing",
        "text": "IL ÉTAIT DANS LA GRILLE. IL M'A REGARDÉ DORMIR.",
        "variants": [],
    },
    {
        "id": "D08", "type": "rapport", "style": "form",
        "title": "Rapport d'autopsie — Y. Andreïev", "author": "Dr Samuel Okafor", "day": 15,
        "room": "medbay", "place": "near_screamer", "guaranteed": True, "image": "brainscan",
        "text": "RAPPORT D'AUTOPSIE — Yuri ANDREÏEV — JOUR 15\n\n"
                "Retrouvé mort dans un casier des quartiers de l'équipage, où il s'était enfermé. Plaies multiples "
                "sur les avant-bras et le visage. Les plaies ne correspondent à aucun animal : elles correspondent "
                "à ses propres ongles.\n\n"
                "Scanner cérébral : lésions étendues dans le cortex visuel et l'amygdale. Je n'ai jamais vu ça.\n\n"
                "Je demande la quarantaine de tout l'équipage.",
        "variants": [],
    },
    {
        "id": "D09", "type": "journal", "style": "paper",
        "title": "Journal de l'ingénieur — jour 17", "author": "Tomasz Lebrun", "day": 17,
        "room": "engine", "place": "corpse:lebrun", "guaranteed": True, "image": None,
        "text": "La chose vit dans les conduits, je l'ai vue deux fois. Elle chasse à la lumière et au bruit. "
                "Alors je coupe tout. Le courant, les portes, les néons. Dans le noir elle ne nous trouvera pas.\n\n"
                "Vasseur dit que je suis fou. J'ai caché les fusibles : {fuses}. Personne ne rallumera sans moi.",
        "variants": [],
    },
    {
        "id": "D10", "type": "postit", "style": "postit",
        "title": "Post-it collé sur une porte", "author": "Inconnu", "day": 18,
        "room": "corridor", "place": "door", "guaranteed": False, "image": None,
        "text": "NE LEUR FAITES PAS CONFIANCE.\nILS NE SONT PLUS EUX.",
        "variants": [("ILS NE SONT PLUS EUX.", "VOUS N'ÊTES PLUS VOUS.")],
    },
    {
        "id": "D11", "type": "audio", "style": "audio",
        "title": "Transcription audio — jour 18", "author": "Léa Fontaine", "day": 18,
        "room": "hangar", "place": "corpse:fontaine", "guaranteed": False, "image": "waveform",
        "text": "[bruit de respiration]\n\n... Elle m'appelle. C'est la voix de ma mère, dans la ventilation. "
                "Elle est morte il y a six ans. Elle dit que c'est froid là-dedans.\n\n[silence]\n\n"
                "... Je vais préparer la navette. Je pars, avec ou sans eux.\n\n[fin de l'enregistrement]",
        "variants": [],
    },
    {
        "id": "D12", "type": "image", "style": "photo",
        "title": "Schéma du réseau de ventilation", "author": "Tomasz Lebrun", "day": 19,
        "room": "engine", "place": "console", "guaranteed": False, "image": "vents",
        "text": "ça passe par l'air",
        "variants": [],
    },
    {
        "id": "D13", "type": "note", "style": "paper",
        "title": "Note du médecin — jour 20", "author": "Dr Samuel Okafor", "day": 20,
        "room": "medbay", "place": "console", "guaranteed": True, "image": None,
        "text": "Tout le monde décrit la même créature. Grande, maigre, les yeux blancs. Mais chacun ajoute un "
                "détail que lui seul craint : Paolo parle de dents, Léa de la voix de sa mère, Tomasz de bruits de "
                "métal.\n\nUne créature ne s'adapte pas à celui qui la regarde. Un cerveau, si.",
        "variants": [],
    },
    {
        "id": "D14", "type": "lettre", "style": "paper",
        "title": "Lettre inachevée", "author": "Dr Samuel Okafor", "day": 21,
        "room": "mess", "place": "corpse:okafor", "guaranteed": False, "image": None,
        "text": "Ma chérie,\n\nsi ce message t'arrive, sache que papa a essayé de soigner tout le monde. "
                "Il y a quelque chose ici qui",
        "variants": [],
    },
    {
        "id": "D15", "type": "journal", "style": "terminal",
        "title": "Journal de bord — jour 22", "author": "Commandante Irène Vasseur", "day": 22,
        "room": "command", "place": "corpse:vasseur", "guaranteed": True, "image": None,
        "text": "JOURNAL DE BORD — KERGUELEN — JOUR 22\n\n"
                "Lebrun et Ricci se sont tiré dessus dans la salle à manger. Chacun jurait avoir tiré sur la "
                "créature. Okafor affirme avoir tué une des petites bêtes près de l'infirmerie. Je suis allée voir : "
                "il n'y avait qu'un tas de câbles arrachés.\n\n"
                "J'ai désactivé la balise de détresse. Personne ne doit venir ici. Personne ne doit repartir avec "
                "ce qu'il y a à bord.",
        "variants": [],
    },
]

# nombre minimal de documents (D01 à D15) présents dans chaque partie
MIN_DOCUMENTS = 12

# ----------------------------------------------------------------------------
# D16 — LE DISQUE DUR (révélation finale)
# ----------------------------------------------------------------------------
HDD_CLASSIFIED = {
    "id": "D16a", "type": "officiel", "style": "helios",
    "title": "Fichier classifié — Projet SINUS", "author": "Helios Biotech", "day": 23,
    "image": None, "variants": [],
    "text": "PROJET SINUS — Souche Isolée Neurotrope Ultra-Stable.\n\n"
            "Agent viral transmissible par voie aérienne. Colonise le système nerveux central en 48 à 72 heures. "
            "Provoque des hallucinations sensorielles complètes, construites à partir des peurs du sujet, et "
            "synchronisées entre sujets infectés.\n\n"
            "Aucune créature n'est présente à bord.\n\n"
            "Applications envisagées : défense, contrôle des populations.\n\n"
            "Priorité : récupérer les données. L'équipage est considéré comme perdu.",
}
HDD_KEATING = {
    "id": "D16b", "type": "video", "style": "video",
    "title": "Dernier enregistrement — Dr Keating", "author": "Dr Mara Keating", "day": 23,
    "image": "keating", "variants": [],
    "text": "C'est ma faute. Il n'y a jamais eu de monstre. Juste nous, dans le noir, qui avions peur. "
            "SINUS ne tue personne. Il nous montre ce qui nous tue.\n\n"
            "Si vous lisez ceci, vous êtes venus de l'extérieur, et vous respirez déjà notre air. Tout ce que vous "
            "avez vu à bord... vous l'avez imaginé.\n\n"
            "Ne ramenez pas ce disque. Ne vous ramenez pas vous-même.",
}
SUIT_LOG = ("JOURNAL DE LA COMBINAISON\n"
            "Analyse de l'air ambiant : contaminant biologique inconnu détecté.\n"
            "Première exposition : hangar, à l'arrivée.")

# ----------------------------------------------------------------------------
# TEXTES DU JEU
# ----------------------------------------------------------------------------
ARRIVAL_MESSAGES = [
    "Le KERGUELEN en vue. Helios Biotech. Dernier contact il y a 41 jours.",
    "Mission : récupérer le disque dur des données du projet. Entre par le hangar (balises rouges / vertes).",
]
HANGAR_MESSAGE = "Joints du casque : ouverts. L'air du bord est respirable. Il sent le métal froid."
FINAL_OBJECTIVE = "Retourner à la navette."
ENDING_SHUTTLE_MESSAGE = "Cap sur la station Helios. Passagers à bord : 1."
ENDING_CAPTION = "Le Kerguelen continue de dériver."
