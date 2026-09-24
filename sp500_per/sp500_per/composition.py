"""Composition historique du S&P 500 (dépôt GitHub fja05680/sp500)."""
from urllib.parse import quote

import pandas as pd

from .config import CACHE, FICHIER_ACTUEL, FICHIER_HISTO, URL_FJA
from .telechargement import telecharger


def charger_historique() -> pd.DataFrame:
    """Une ligne par date de changement : date, liste des tickers membres."""
    chemin = telecharger(URL_FJA + quote(FICHIER_HISTO), CACHE / "fja05680" / "historique.csv")
    df = pd.read_csv(chemin, parse_dates=["date"])
    df["tickers"] = df["tickers"].map(lambda s: sorted({t.strip() for t in s.split(",") if t.strip()}))
    return df.sort_values("date").reset_index(drop=True)


def charger_actuels() -> pd.DataFrame:
    """Membres actuels avec nom, secteur GICS et CIK."""
    chemin = telecharger(URL_FJA + FICHIER_ACTUEL, CACHE / "fja05680" / "sp500.csv")
    df = pd.read_csv(chemin)
    return df.rename(columns={"Symbol": "ticker", "Security": "nom", "GICS Sector": "secteur", "CIK": "cik"})


def membres_a(historique: pd.DataFrame, date: pd.Timestamp) -> list[str]:
    """Liste des membres à `date` : dernière ligne dont la date est <= `date`."""
    lignes = historique[historique["date"] <= date]
    if lignes.empty:
        raise ValueError(f"Pas de composition connue au {date:%Y-%m-%d}")
    return lignes.iloc[-1]["tickers"]


def ticker_sec(ticker: str) -> str:
    """BRK.B -> BRK-B (format SEC et Yahoo)."""
    return ticker.replace(".", "-").upper()
