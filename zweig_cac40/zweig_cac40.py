"""
Zweig Breadth Thrust (ZBT) sur les composantes historiques du CAC 40.

Étape 1 (ce fichier, pour l'instant) :
  - reconstitue la composition du CAC 40 révision par révision, en remontant
    le temps à partir de la composition actuelle (sans biais de survivance) ;
  - teste le téléchargement de chaque ticker (Yahoo, puis Stooq en secours)
    et écrit la plage de dates disponible dans tickers_cac40.csv.

Les étapes 2 à 4 (matrice d'appartenance, calcul du ZBT, résultats) seront
ajoutées une fois la table de correspondance validée.

Usage :  python zweig_cac40.py etape1
"""

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# PARAMÈTRES
# ---------------------------------------------------------------------------
DATE_DEBUT = "2016-01-01"
DATE_FIN = None                 # None = aujourd'hui
EMA_PERIODE = 10                # période de l'EMA du ratio (étape 3)
SEUIL_BAS = 0.40
SEUIL_HAUT = 0.615
FENETRE_SIGNAL = 10             # séances max. pour passer de SEUIL_BAS à SEUIL_HAUT

DOSSIER = Path(__file__).resolve().parent
FICHIER_MOUVEMENTS = DOSSIER / "mouvements_cac40.csv"
FICHIER_TICKERS = DOSSIER / "tickers_cac40.csv"

# Composition après la révision du 22/12/2025 (aucun changement en mars,
# juin et septembre 2026). Noms identiques à la colonne `societe` de
# tickers_cac40.csv.
COMPOSITION_ACTUELLE = [
    "Accor", "Air Liquide", "Airbus", "ArcelorMittal", "AXA", "BNP Paribas",
    "Bouygues", "Bureau Veritas", "Capgemini", "Carrefour", "Crédit Agricole",
    "Danone", "Dassault Systèmes", "Eiffage", "Engie", "EssilorLuxottica",
    "Eurofins Scientific", "Euronext", "Hermès", "Kering", "Legrand",
    "L'Oréal", "LVMH", "Michelin", "Orange", "Pernod Ricard", "Publicis",
    "Renault", "Safran", "Saint-Gobain", "Sanofi", "Schneider Electric",
    "Société Générale", "Stellantis (ex-PSA)", "STMicroelectronics", "Thales",
    "TotalEnergies", "Unibail-Rodamco-Westfield", "Veolia", "Vinci",
]

# Noms du fichier Wikipédia -> nom de société unique (changements de nom :
# une société renommée reste membre sans interruption).
ALIAS = {
    "PSA Peugeot Citroën": "Stellantis (ex-PSA)",
    "TechnipFMC": "Technip / TechnipFMC",
}

# Corrections des anomalies du fichier de mouvements.
#  - Eurofins remplace Atos « le 17/09/2021 après la clôture » (communiqué
#    Euronext) : premier jour de cotation dans l'indice = lundi 20/09/2021.
#  - Ligne Sanofi du 20/06/2022 : à ignorer (Sanofi est resté membre). Elle
#    n'apparaît pas dans la version actuelle du fichier ; le filtre reste
#    en place par sécurité.
CORRECTIONS_DATES = {("2021-09-17", "Eurofins Scientific", "Atos"): "2021-09-20"}
LIGNES_IGNOREES = [("2022-06-20", "Sanofi")]


# ---------------------------------------------------------------------------
# COMPOSITION
# ---------------------------------------------------------------------------
def charger_mouvements():
    """Lit le fichier de mouvements, normalise les noms et applique les corrections."""
    mv = pd.read_csv(FICHIER_MOUVEMENTS, dtype=str).fillna("")
    for col in ("entrante", "sortante"):
        mv[col] = mv[col].str.strip().replace(ALIAS)
    mv["date"] = mv["date"].str.strip()
    for (d, e, s), nouvelle in CORRECTIONS_DATES.items():
        masque = (mv.date == d) & (mv.entrante == e) & (mv.sortante == s)
        mv.loc[masque, "date"] = nouvelle
    for d, nom in LIGNES_IGNOREES:
        mv = mv[~((mv.date == d) & ((mv.entrante == nom) | (mv.sortante == nom)))]
    mv["date"] = pd.to_datetime(mv["date"])
    return mv.sort_values("date", ascending=False).reset_index(drop=True)


def compositions_par_periode(mv, debut=DATE_DEBUT):
    """
    Remonte le temps révision par révision depuis la composition actuelle.
    Renvoie une liste de (date_debut_periode, ensemble_des_membres), la
    composition étant valable de date_debut_periode (incluse) jusqu'à la
    révision suivante (exclue). Un titre entre à la date de révision indiquée.
    """
    membres = set(COMPOSITION_ACTUELLE)
    periodes = []
    for date, groupe in mv.groupby("date", sort=False):   # dates décroissantes
        periodes.append((date, frozenset(membres)))
        # Composition AVANT la révision = après - entrantes + sortantes
        for _, ligne in groupe.iterrows():
            if ligne.entrante:
                if ligne.entrante not in membres:
                    raise ValueError(f"{date:%Y-%m-%d} : {ligne.entrante} n'était pas membre")
                membres.discard(ligne.entrante)
            if ligne.sortante:
                membres.add(ligne.sortante)
        if date <= pd.Timestamp(debut):
            break
    periodes.append((pd.Timestamp("1900-01-01"), frozenset(membres)))
    return sorted(periodes, key=lambda p: p[0])


# ---------------------------------------------------------------------------
# TÉLÉCHARGEMENT
# ---------------------------------------------------------------------------
def telecharger(ticker, debut=DATE_DEBUT, fin=DATE_FIN):
    """Clôtures ajustées : Yahoo d'abord, Stooq en secours. Renvoie (série, source)."""
    try:
        import yfinance as yf
        df = yf.download(ticker, start=debut, end=fin, auto_adjust=True,
                         progress=False, threads=False)
        if df is not None and not df.empty:
            s = df["Close"]
            s = s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
            return s.dropna(), "yahoo"
    except Exception:
        pass
    try:
        from pandas_datareader import data as pdr
        # Stooq : suffixe de place différent de Yahoo, on tente les variantes usuelles.
        base = ticker.split(".")[0]
        for sym in (ticker, base, f"{base}.FR", f"{base}.US"):
            df = pdr.DataReader(sym, "stooq", start=debut, end=fin)
            if not df.empty:
                return df["Close"].sort_index().dropna(), "stooq"
    except Exception:
        pass
    return pd.Series(dtype=float), None


def reseau_disponible():
    """Vrai si Yahoo ou Stooq répond (évite de confondre « bloqué » et « radié »)."""
    import urllib.request
    for url in ("https://query1.finance.yahoo.com", "https://stooq.com"):
        try:
            urllib.request.urlopen(url, timeout=10)
            return True
        except urllib.error.HTTPError:
            return True          # le serveur répond, même avec un code d'erreur
        except Exception:
            continue
    return False


def etape1():
    mv = charger_mouvements()
    tickers = pd.read_csv(FICHIER_TICKERS, dtype=str).fillna("")

    # 1. Contrôle de la composition actuelle
    print(f"Composition actuelle : {len(COMPOSITION_ACTUELLE)} valeurs")
    assert len(set(COMPOSITION_ACTUELLE)) == 40
    inconnues = set(COMPOSITION_ACTUELLE) - set(tickers.societe)
    assert not inconnues, f"Sans ticker : {inconnues}"

    # 2. Reconstitution des compositions depuis DATE_DEBUT
    periodes = compositions_par_periode(mv)
    print("\nNombre de membres par période :")
    for (d, m), suivant in zip(periodes, periodes[1:] + [(None, None)]):
        if suivant[0] is not None and suivant[0] <= pd.Timestamp(DATE_DEBUT):
            continue
        print(f"  à partir du {max(d, pd.Timestamp(DATE_DEBUT)):%Y-%m-%d} : {len(m)}")
    tous = set().union(*(m for d, m in periodes[1:])) | set(periodes[0][1])
    sans_ticker = tous - set(tickers.societe)
    print("\nSociétés membres depuis 2016 sans ticker :", sans_ticker or "aucune")

    # 3. Test de téléchargement de chaque ticker
    if not reseau_disponible():
        print("\nYahoo et Stooq injoignables : test des tickers non effectué.")
        return
    plages = []
    for _, t in tickers.iterrows():
        s, source = telecharger(t.ticker_yahoo)
        if s.empty:
            plages.append("aucune donnée")
        else:
            plages.append(f"{s.index.min():%Y-%m-%d} → {s.index.max():%Y-%m-%d} ({source})")
        print(f"  {t.ticker_yahoo:10s} {plages[-1]}")
    tickers["plage_dates_disponibles"] = plages
    tickers.to_csv(FICHIER_TICKERS, index=False)
    print(f"\n{FICHIER_TICKERS.name} mis à jour.")


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "etape1"
    {"etape1": etape1}[etape]()
