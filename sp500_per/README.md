# S&P 500 — nombre de membres avec un PER > 40 (juillet 2009 → aujourd'hui)

Pour chaque fin de mois (dernier jour de bourse), le script reconstitue la composition du
S&P 500 à cette date, calcule le PER de chaque membre avec les seules informations connues
à cette date, et compte les PER > 40, les PER négatifs et les données manquantes.

## Installation

```bash
cd sp500_per
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

L'email envoyé à la SEC dans le User-Agent est dans `sp500_per/config.py`
(modifiable aussi via la variable d'environnement `SEC_EMAIL`).

## Utilisation

1. **Vérification sur juillet 2021 d'abord** :

   ```bash
   python -m sp500_per --verif            # ou --verif 2023-12 pour un autre mois
   ```

   Affiche pour AAPL, MSFT, AMZN, TSLA, NVDA, JPM, XOM : cours coté, BPA 12 mois, PER,
   CIK utilisé et le détail des 4 trimestres retenus. Écrit aussi
   `sorties/detail_verif_2021-07.csv` et la liste des tickers non résolus.
   Le premier lancement télécharge `companyfacts.zip` (plus d’1 Go, une seule fois).

2. **Calcul complet** :

   ```bash
   python -m sp500_per                     # juillet 2009 -> dernier jour de bourse disponible
   python -m sp500_per --debut 2015-01 --fin 2020-12-31
   ```

Options : `--maj-prix` (retélécharge les cours), `--maj-sec` (retélécharge companyfacts.zip).

## Sorties (`sorties/`)

| Fichier | Contenu |
|---|---|
| `mensuel.csv` | date, nb membres, nb PER > 40, nb PER négatifs, nb manquants, nb PER positifs, % PER > 40 parmi les positifs |
| `detail.csv` | date, ticker, nom, secteur, cours, BPA 12m, PER (+ statut, CIK, méthode, motif si manquant) |
| `per_sup_40.png` | part des PER > 40 (parmi les PER positifs) et des PER négatifs (parmi les membres avec données) |
| `correspondances.csv` | ticker → CIK candidats et méthode de résolution |
| `non_resolus.csv` | tickers sans CIK (à compléter dans `correspondances_manuelles.csv`) |

## Sources et cache (`cache/`)

- Composition : `S&P 500 Historical Components & Changes (Updated).csv` et `sp500.csv` du dépôt
  [fja05680/sp500](https://github.com/fja05680/sp500).
- BPA : `companyfacts.zip` de la SEC, concept us-gaap `EarningsPerShareDiluted`, à défaut
  `EarningsPerShareBasic` (puis `EarningsPerShareBasicAndDiluted`), unité USD/action.
  Seuls les faits BPA des sociétés utiles sont extraits dans `cache/sec/bpa/` : le zip peut
  ensuite être supprimé.
- Ticker → CIK : `company_tickers.json` de la SEC ; pour les tickers disparus ou réattribués,
  recherche par nom (noms historiques de Wikipédia, comparés à tous les noms, anciens compris,
  de `cik-lookup-data.txt` de la SEC).
- Cours : yfinance, historique complet par ticker (clôture + splits), un CSV par ticker.

Tout est mis en cache ; une relance ne retélécharge rien (sauf les cours des titres encore cotés
quand un nouveau mois est demandé).

## Règles de calcul

- **Date étudiée D** = dernier jour de bourse du mois (calendrier de ^GSPC).
- **BPA 12 mois** = somme des 4 derniers trimestres parmi les faits déposés (`filed`) strictement
  avant D. T4 = annuel − T1 − T2 − T3 (à défaut annuel − cumul 9 mois).
  Si une même période a été déposée plusieurs fois, on garde la dernière valeur déposée **avant D** :
  un retraitement publié après D est ignoré.
  Replis mathématiquement équivalents quand les 4 trimestres ne sont pas tous disponibles
  (surtout 2009-2010, début de l'XBRL) : dernier exercice complet si c'est la période la plus
  récente, sinon annuel N-1 + cumul N − cumul N-1. La méthode utilisée figure dans `detail.csv`.
  Un BPA dont la dernière période est close depuis plus de 230 jours est considéré manquant.
- **Splits** : le cours yfinance (ajusté des splits) est multiplié par les ratios des splits
  postérieurs à D pour retrouver le cours coté. Symétriquement, un BPA déposé avant un split
  intervenu entre son dépôt et D est divisé par le ratio (sinon le PER d'Apple fin août 2020
  serait faux d'un facteur 4).
- **Statuts** : BPA ≤ 0 → « PER négatif » ; PER > 40 → « PER > 40 » ; tout manque (CIK, cours,
  BPA) → « manquant ». Le % de PER > 40 est calculé sur les membres à PER positif.
- **Changement de CIK** : une société peut avoir plusieurs CIK candidats (ex. nouvelle holding) ;
  le premier qui a un BPA connu à D est retenu.

## Limites connues

- **2009-2010** : l'XBRL n'est obligatoire que pour les périodes closes après le 15 juin 2009
  (grandes sociétés), puis 2010-2011 pour les autres. Les premiers mois comptent donc beaucoup
  de « manquants » : regarder `nb_manquants` avant d'interpréter le début de la série.
- **Titres radiés** : Yahoo ne fournit généralement plus les cours des sociétés rachetées ou
  disparues ; elles tombent en « manquant ». Un ticker réattribué depuis à une autre société
  est aussi mis en « manquant » (le cours yfinance serait celui de l'autre société).
- Le BPA publié est le BPA GAAP (pas un BPA « ajusté »), ce qui gonfle les PER des sociétés
  avec des charges exceptionnelles.
- Les sociétés étrangères déposant en IFRS (20-F) n'ont pas de concept us-gaap → manquant.
- Le secteur est le secteur GICS actuel (fja05680) ; pour les sociétés sorties, le secteur
  Yahoo quand il existe encore.

## Tests

```bash
pip install pytest && python -m pytest -q tests
```
