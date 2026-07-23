# 🔥 Carte des habitats — Risque incendie

Application web (Next.js) qui affiche les **habitats/bâtiments** sur une carte Google Maps
et les colore en **bleu / orange / rouge** selon leur proximité avec des **zones à risque
incendie** que vous définissez sur la carte.

- 🟥 **Rouge** — habitat à l'intérieur d'une zone à risque (risque élevé)
- 🟧 **Orange** — habitat proche d'une zone à risque (risque modéré)
- 🟦 **Bleu** — habitat éloigné (risque faible)

## Comment ça marche

- La **carte** est fournie par Google Maps (vue satellite/hybride).
- Les **emprises des bâtiments** proviennent d'OpenStreetMap via l'API publique
  [Overpass](https://overpass-api.de/) — Google ne donne pas librement accès aux
  contours de bâtiments, OSM oui, et ça reste gratuit.
- Les **foyers de risque** sont de deux natures, traités de la même façon :
  - **Automatique** — les **forêts et zones boisées** (forêts, bois, garrigue, landes)
    chargées depuis OpenStreetMap : c'est le vrai facteur de « feu de forêt »
    (interface habitat‑forêt). La distance est calculée jusqu'au **bord** de la forêt.
  - **Manuel** — des **zones à risque** que vous posez à la main sur la carte
    (cercles déplaçables et redimensionnables).
- Chaque habitat est coloré selon sa distance au foyer de risque le plus proche,
  avec des **seuils rouge/orange réglables**.

## Utilisation

1. Déplacez/zoomez la carte sur le secteur voulu.
2. Cliquez sur **« Charger les habitats de cette zone »**.
3. Cliquez sur **« Charger les forêts (risque auto) »** : les habitats se colorent
   automatiquement selon leur distance aux zones boisées.
4. (Optionnel) Ajustez les **seuils rouge/orange** (en mètres) avec les curseurs.
5. (Optionnel) Cochez **« ajouter une zone à risque »** pour poser des cercles
   supplémentaires à la main. Clic droit sur une zone pour la supprimer.

## Démarrage local

```bash
npm install
cp .env.example .env.local   # puis renseignez votre clé Google Maps
npm run dev
```

Ouvrez http://localhost:3000

### Clé Google Maps

1. Sur [Google Cloud Console](https://console.cloud.google.com/google/maps-apis),
   créez une clé API et activez **« Maps JavaScript API »**.
2. Renseignez-la dans `.env.local` :

```
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=votre_cle_ici
```

> ⚠️ La clé étant exposée côté navigateur (préfixe `NEXT_PUBLIC_`), pensez à la
> restreindre par référent HTTP (votre domaine Vercel) dans la console Google Cloud.

## Déploiement sur Vercel

1. Poussez ce dépôt sur GitHub (déjà fait).
2. Sur [vercel.com](https://vercel.com), importez le dépôt (Vercel détecte Next.js
   automatiquement, aucune configuration de build nécessaire).
3. Dans **Settings → Environment Variables**, ajoutez :
   `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` = votre clé.
4. Déployez. 🎉

## Pile technique

- [Next.js 14](https://nextjs.org/) (App Router) — déploiement Vercel natif
- Google Maps JavaScript API — fond de carte et rendu des polygones/cercles
- OpenStreetMap / Overpass API — emprises des bâtiments et des zones boisées
- Géométrie maison (`lib/geo.ts`) : distance de Haversine, distance point→polygone,
  test d'appartenance, classification du risque (`lib/risk.ts`)

## Aller plus loin

- Le risque automatique s'appuie sur les zones boisées OSM (`fetchWildland` dans
  `lib/overpass.ts`). On peut y ajouter d'autres foyers (décharges, industries à risque…)
  ou brancher un jeu de données officiel (feux de forêt / DFCI) en le convertissant
  en polygones passés à `classifyBuilding`.
- Les seuils rouge/orange sont réglables dans l'interface, et par défaut dans
  `DEFAULT_THRESHOLDS` (`lib/risk.ts`).
