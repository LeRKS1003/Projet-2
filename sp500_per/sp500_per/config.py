import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("SP500_PER_CACHE", RACINE / "cache"))
SORTIES = Path(os.environ.get("SP500_PER_SORTIES", RACINE / "sorties"))

# La SEC exige un User-Agent identifiant l'appelant (nom + email).
SEC_EMAIL = os.environ.get("SEC_EMAIL", "aymericdrouin@orange.fr")
SEC_USER_AGENT = f"sp500-per-analyse {SEC_EMAIL}"

URL_FJA = "https://raw.githubusercontent.com/fja05680/sp500/master/"
FICHIER_HISTO = "S&P 500 Historical Components & Changes (Updated).csv"
FICHIER_ACTUEL = "sp500.csv"

URL_COMPANYFACTS = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
URL_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_CIK_NOMS = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
URL_WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Fichier optionnel de correspondances saisies à la main (ticker,cik).
CORRESPONDANCES_MANUELLES = RACINE / "correspondances_manuelles.csv"

DEBUT = "2009-07"
SEUIL_PER = 40.0
TICKERS_VERIF = ["AAPL", "MSFT", "AMZN", "TSLA", "NVDA", "JPM", "XOM"]
