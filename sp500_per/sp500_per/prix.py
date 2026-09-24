"""Cours Yahoo Finance (yfinance) avec cache local et reconstitution du cours coté à l'époque.

yfinance renvoie des clôtures ajustées des splits (même avec auto_adjust=False,
qui ne neutralise que l'ajustement des dividendes). Le cours réellement coté à
une date D s'obtient en multipliant par le produit des ratios des splits
postérieurs à D.
"""
import json
import warnings
from datetime import date
from functools import lru_cache

import pandas as pd

from .config import CACHE

DOSSIER = CACHE / "yfinance"
DOSSIER_PRIX = DOSSIER / "prix"
DOSSIER_INFO = DOSSIER / "info"

SECTEURS_YAHOO_VERS_GICS = {
    "Technology": "Information Technology",
    "Financial Services": "Financials",
    "Healthcare": "Health Care",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
}


def _chemin(ticker: str):
    return DOSSIER_PRIX / f"{ticker}.csv"


def precharger(tickers: list[str], forcer: bool = False, taille_lot: int = 50) -> None:
    """Télécharge en lots l'historique complet (clôture + splits) des tickers absents du cache."""
    import yfinance as yf

    DOSSIER_PRIX.mkdir(parents=True, exist_ok=True)
    a_faire = [t for t in dict.fromkeys(tickers) if forcer or not _chemin(t).exists()]
    if not a_faire:
        return
    print(f"  yfinance : {len(a_faire)} tickers à télécharger")
    for i in range(0, len(a_faire), taille_lot):
        lot = a_faire[i:i + taille_lot]
        print(f"    lot {i // taille_lot + 1}/{(len(a_faire) - 1) // taille_lot + 1}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(lot, period="max", interval="1d", auto_adjust=False, actions=True,
                             group_by="ticker", threads=True, progress=False)
        for t in lot:
            try:
                sous = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                sous = sous[["Close", "Stock Splits"]].dropna(subset=["Close"])
            except (KeyError, TypeError):
                sous = pd.DataFrame(columns=["Close", "Stock Splits"])
            sous.index = pd.to_datetime(sous.index).tz_localize(None) if len(sous) else sous.index
            sous.index.name = "Date"
            # Un fichier vide mémorise l'absence de données pour ne pas redemander.
            sous.to_csv(_chemin(t))
    historique.cache_clear()
    splits.cache_clear()


@lru_cache(maxsize=None)
def historique(ticker: str) -> pd.DataFrame:
    chemin = _chemin(ticker)
    if not chemin.exists():
        precharger([ticker])
    df = pd.read_csv(chemin, index_col="Date", parse_dates=["Date"])
    return df.sort_index()


@lru_cache(maxsize=None)
def splits(ticker: str) -> pd.Series:
    h = historique(ticker)
    s = h["Stock Splits"].fillna(0) if "Stock Splits" in h else pd.Series(dtype=float)
    return s[s > 0]


def facteur_splits_apres(ticker: str, d: date) -> float:
    """Produit des ratios des splits strictement postérieurs à d."""
    s = splits(ticker)
    return float(s[s.index > pd.Timestamp(d)].prod()) if len(s) else 1.0


def facteur_splits_entre(ticker: str, depot: date, d: date) -> float:
    """Produit des ratios des splits intervenus après le dépôt et au plus tard à d."""
    s = splits(ticker)
    if not len(s):
        return 1.0
    return float(s[(s.index > pd.Timestamp(depot)) & (s.index <= pd.Timestamp(d))].prod())


def cours_cote(ticker: str, d: date, tolerance_jours: int = 5) -> float | None:
    """Clôture réellement cotée au dernier jour de bourse <= d (dans la tolérance)."""
    h = historique(ticker)
    if h.empty:
        return None
    avant = h.loc[: pd.Timestamp(d), "Close"]
    if avant.empty or (pd.Timestamp(d) - avant.index[-1]).days > tolerance_jours:
        return None
    return float(avant.iloc[-1]) * facteur_splits_apres(ticker, avant.index[-1].date())


def fins_de_mois(debut: str, fin: date | None = None) -> list[date]:
    """Dernier jour de bourse de chaque mois, d'après le calendrier de cotation du S&P 500 (^GSPC)."""
    precharger(["^GSPC"], forcer=_calendrier_perime())
    idx = historique("^GSPC").index
    idx = idx[idx >= pd.Timestamp(debut + "-01")]
    if fin is not None:
        idx = idx[idx <= pd.Timestamp(fin)]
    return [d.date() for d in pd.Series(idx, index=idx).groupby(idx.to_period("M")).max()]


def _calendrier_perime() -> bool:
    chemin = _chemin("^GSPC")
    if not chemin.exists():
        return True
    age = pd.Timestamp.now() - pd.Timestamp(chemin.stat().st_mtime, unit="s")
    return age > pd.Timedelta(days=1)


@lru_cache(maxsize=None)
def secteur_yahoo(ticker: str) -> str:
    """Secteur Yahoo (converti en libellé GICS) pour les sociétés absentes de la liste actuelle."""
    DOSSIER_INFO.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_INFO / f"{ticker}.json"
    if not chemin.exists():
        import yfinance as yf

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:  # yfinance lève des erreurs variées pour les titres radiés
            info = {}
        chemin.write_text(json.dumps({k: info.get(k) for k in ("sector", "longName")}))
    secteur = json.loads(chemin.read_text()).get("sector") or ""
    return SECTEURS_YAHOO_VERS_GICS.get(secteur, secteur)


def cache_perime(ticker: str, jusqua: date) -> bool:
    """Vrai si le cache s'arrête avant `jusqua`, date d'un fichier de plus d'un jour
    (on ne redemande pas en boucle les titres radiés)."""
    chemin = _chemin(ticker)
    if not chemin.exists():
        return True
    h = historique(ticker)
    if h.empty or h.index[-1] >= pd.Timestamp(jusqua) - pd.Timedelta(days=5):
        return False
    age = pd.Timestamp.now() - pd.Timestamp(chemin.stat().st_mtime, unit="s")
    recent = h.index[-1] >= pd.Timestamp(chemin.stat().st_mtime, unit="s") - pd.Timedelta(days=10)
    return recent and age > pd.Timedelta(days=1)
