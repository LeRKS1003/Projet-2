"""Correspondance ticker S&P 500 -> CIK SEC.

Ordre de résolution :
1. correspondances_manuelles.csv (ticker,cik) si présent ;
2. CIK fourni pour les membres actuels (sp500.csv de fja05680) ;
3. company_tickers.json de la SEC, à condition que le nom de la société actuelle
   ressemble au nom historique connu (sinon le ticker a été réattribué) ;
4. recherche par nom (noms historiques Wikipédia) parmi tous les noms d'entités
   SEC, anciens compris (cik-lookup-data.txt) ;
5. sinon : non résolu (listé dans sorties/non_resolus.csv).
"""
import re
from dataclasses import dataclass
from io import StringIO

import pandas as pd
import requests
from rapidfuzz import fuzz, process

from . import sec
from .composition import ticker_sec
from .config import CACHE, CORRESPONDANCES_MANUELLES, URL_WIKI

SEUIL_NOM = 90  # score rapidfuzz minimal pour accepter une correspondance par nom

_SUFFIXES = r"\b(the|inc|incorporated|corp|corporation|co|company|companies|ltd|limited|plc|llc|lp|" \
            r"holdings?|group|n\.?v|s\.?a|ag|se|class [a-c]|cl [a-c]|new|de|del|/[a-z]{2}/?)\b"


def normaliser(nom: str) -> str:
    n = nom.lower().replace("&", " and ")
    n = re.sub(r"/[a-z]{2,3}/?", " ", n)  # suffixes d'état SEC : « /DE/ »
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(_SUFFIXES, " ", n)
    return re.sub(r"\s+", " ", n).strip()


@dataclass
class Resolution:
    ticker: str
    ciks: list[int]        # candidats par ordre de préférence
    methode: str
    nom_historique: str | None = None
    nom_sec: str | None = None
    score: float | None = None

    @property
    def cik(self) -> int | None:
        return self.ciks[0] if self.ciks else None


def noms_historiques_wikipedia() -> dict[str, str]:
    """Ticker -> nom de société, d'après les tables « membres » et « changements » de Wikipédia."""
    chemin = CACHE / "wikipedia" / "sp500.html"
    if not chemin.exists():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get(URL_WIKI, headers={"User-Agent": "Mozilla/5.0 sp500-per"}, timeout=60)
            r.raise_for_status()
            chemin.write_text(r.text)
        except requests.RequestException as e:
            print(f"  Wikipédia indisponible ({e}) : pas de recherche par nom pour les tickers disparus")
            return {}
    res: dict[str, str] = {}
    for table in pd.read_html(StringIO(chemin.read_text())):
        cols = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in table.columns]
        table.columns = cols
        if "Symbol" in cols and "Security" in cols:
            for t, n in zip(table["Symbol"], table["Security"]):
                res[ticker_sec(str(t))] = str(n)
        paires = [(c, c.replace("Ticker", "Security")) for c in cols if "Ticker" in c]
        for col_t, col_n in paires:
            if col_n not in cols:
                continue
            # Les tables sont triées du plus récent au plus ancien : on garde le nom le plus récent.
            for t, n in zip(table[col_t], table[col_n]):
                if isinstance(t, str) and isinstance(n, str) and t.strip():
                    res.setdefault(ticker_sec(t.strip()), n.strip())
    return res


def correspondances_manuelles() -> dict[str, int]:
    if not CORRESPONDANCES_MANUELLES.exists():
        return {}
    df = pd.read_csv(CORRESPONDANCES_MANUELLES, comment="#", dtype=str).dropna(subset=["ticker", "cik"])
    return {ticker_sec(t): int(c) for t, c in zip(df["ticker"], df["cik"])}


class Resolveur:
    def __init__(self, actuels: pd.DataFrame):
        self.manuelles = correspondances_manuelles()
        self.actuels = {ticker_sec(t): int(c) for t, c in zip(actuels["ticker"], actuels["cik"]) if pd.notna(c)}
        self.noms_actuels = {ticker_sec(t): n for t, n in zip(actuels["ticker"], actuels["nom"])}
        self.sec_tickers = sec.tickers_sec()
        self.noms_wiki = noms_historiques_wikipedia()
        self._index_noms = None
        self.cache: dict[str, Resolution] = {}

    def nom_historique(self, ticker: str) -> str | None:
        t = ticker_sec(ticker)
        return self.noms_actuels.get(t) or self.noms_wiki.get(t)

    def _recherche_par_nom(self, nom: str, limite: int = 5) -> list[tuple[int, float]]:
        """CIK distincts dont un nom (actuel ou ancien) ressemble à `nom`, meilleur score d'abord."""
        if self._index_noms is None:
            ciks, noms = [], []
            for cik, liste in sec.noms_entites().items():
                for n in liste:
                    ciks.append(cik)
                    noms.append(normaliser(n))
            self._index_noms = (ciks, noms)
        ciks, noms = self._index_noms
        cible = normaliser(nom)
        if not cible:
            return []
        res: dict[int, float] = {}
        for _, score, idx in process.extract(cible, noms, scorer=fuzz.token_sort_ratio, limit=limite * 4):
            res.setdefault(ciks[idx], score)
        return sorted(res.items(), key=lambda x: -x[1])[:limite]

    def resoudre(self, ticker: str) -> Resolution:
        t = ticker_sec(ticker)
        if t not in self.cache:
            self.cache[t] = self._resoudre(t, ticker, self.nom_historique(ticker))
        return self.cache[t]

    def _resoudre(self, t: str, ticker: str, nom_h: str | None) -> Resolution:
        ciks: list[int] = []
        methodes: list[str] = []
        nom_sec = score = None

        def ajouter(cik, methode):
            if cik not in ciks:
                ciks.append(cik)
                methodes.append(methode)

        if t in self.manuelles:
            ajouter(self.manuelles[t], "manuel")
        if t in self.actuels:
            ajouter(self.actuels[t], "membre actuel")
        if t in self.sec_tickers:
            cik, titre = self.sec_tickers[t]
            if nom_h is None:
                ajouter(cik, "ticker SEC (nom historique inconnu)")
                nom_sec = titre
            elif (s := fuzz.token_sort_ratio(normaliser(nom_h), normaliser(titre))) >= 80:
                ajouter(cik, "ticker SEC")
                nom_sec, score = titre, s
            # Sinon le ticker désigne aujourd'hui une autre société.
        if nom_h:
            # Toujours chercher aussi par nom : une société peut avoir changé de CIK
            # (nouvelle holding), l'ancien CIK porte alors l'historique XBRL.
            for cik, s in self._recherche_par_nom(nom_h):
                if s >= SEUIL_NOM:
                    ajouter(cik, "recherche par nom")
                    if nom_sec is None:
                        nom_sec, score = sec.noms_entites()[cik][0], s
                elif nom_sec is None:
                    nom_sec, score = sec.noms_entites()[cik][0], s  # meilleur candidat rejeté, pour info
        if not ciks:
            motif = "non résolu" if nom_h else "non résolu (nom historique inconnu)"
            return Resolution(ticker, [], motif, nom_h, nom_sec, score)
        return Resolution(ticker, ciks, " + ".join(dict.fromkeys(methodes)), nom_h, nom_sec, score)
