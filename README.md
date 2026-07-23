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
- Les **zones à risque** sont placées à la main : vous cliquez sur la carte pour poser
  un cercle (déplaçable et redimensionnable). Chaque bâtiment est ensuite coloré selon
  sa distance à la zone la plus proche.

## Utilisation

1. Déplacez/zoomez la carte sur le secteur voulu.
2. Cliquez sur **« Charger les habitats de cette zone »**.
3. Cochez **« ajouter une zone à risque »**, réglez le rayon, puis cliquez sur la carte
   pour placer une ou plusieurs zones.
4. Les habitats se recolorent automatiquement. Clic droit sur une zone pour la supprimer.

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
- OpenStreetMap / Overpass API — emprises des bâtiments
- Calcul de distance par formule de Haversine (`lib/geo.ts`, `lib/risk.ts`)

## Aller plus loin

- Brancher un **vrai jeu de données de zones à risque** (ex. données feux de forêt / DFCI)
  en remplaçant la saisie manuelle par un chargement automatique dans `lib/risk.ts`.
- Affiner les seuils rouge/orange dans `classifyBuilding` (paramètre `orangeFactor`).
