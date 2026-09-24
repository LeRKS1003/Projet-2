"""Données SEC : correspondance ticker -> CIK, noms d'entités et BPA XBRL (companyfacts.zip)."""
import json
import re
import zipfile
from functools import lru_cache

from .config import CACHE, URL_CIK_NOMS, URL_COMPANYFACTS, URL_TICKERS
from .telechargement import telecharger

DOSSIER = CACHE / "sec"
ZIP = DOSSIER / "companyfacts.zip"
DOSSIER_BPA = DOSSIER / "bpa"

# Ordre de préférence des concepts us-gaap pour le BPA.
CONCEPTS_BPA = ["EarningsPerShareDiluted", "EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"]


def telecharger_companyfacts(forcer: bool = False) -> None:
    telecharger(URL_COMPANYFACTS, ZIP, sec=True, forcer=forcer)
    if forcer:
        for f in DOSSIER_BPA.glob("*.json"):
            f.unlink()
        (DOSSIER / "ciks_companyfacts.txt").unlink(missing_ok=True)


@lru_cache(maxsize=1)
def tickers_sec() -> dict[str, tuple[int, str]]:
    """ticker (format BRK-B) -> (cik, nom) pour les sociétés cotées actuellement."""
    chemin = telecharger(URL_TICKERS, DOSSIER / "company_tickers.json", sec=True)
    donnees = json.loads(chemin.read_text())
    res = {}
    for d in donnees.values():
        res.setdefault(d["ticker"].upper(), (int(d["cik_str"]), d["title"]))
    return res


@lru_cache(maxsize=1)
def ciks_companyfacts() -> frozenset[int]:
    """CIK présents dans l'archive companyfacts (liste mise en cache)."""
    liste = DOSSIER / "ciks_companyfacts.txt"
    if not liste.exists():
        telecharger_companyfacts()
        with zipfile.ZipFile(ZIP) as z:
            ciks = sorted(int(m.group(1)) for n in z.namelist() if (m := re.fullmatch(r"CIK(\d+)\.json", n)))
        liste.write_text("\n".join(map(str, ciks)))
    return frozenset(int(x) for x in liste.read_text().split())


@lru_cache(maxsize=1)
def noms_entites() -> dict[int, list[str]]:
    """CIK -> noms connus (actuels et anciens) d'après cik-lookup-data.txt,
    restreint aux CIK présents dans companyfacts."""
    chemin = telecharger(URL_CIK_NOMS, DOSSIER / "cik-lookup-data.txt", sec=True)
    utiles = ciks_companyfacts()
    res: dict[int, list[str]] = {}
    with open(chemin, encoding="latin-1") as f:
        for ligne in f:
            # Format « NOM:0000123456: » ; le nom peut lui-même contenir « : ».
            m = re.match(r"^(.*):(\d{10}):\s*$", ligne)
            if m and (cik := int(m.group(2))) in utiles:
                res.setdefault(cik, []).append(m.group(1).strip())
    for ticker, (cik, nom) in tickers_sec().items():
        if cik in utiles and nom not in res.get(cik, []):
            res.setdefault(cik, []).append(nom)
    return res


def extraire_bpa(ciks: set[int]) -> None:
    """Extrait de companyfacts.zip les faits BPA des CIK demandés vers cache/sec/bpa/<cik>.json."""
    manquants = [c for c in ciks if not (DOSSIER_BPA / f"{c}.json").exists()]
    if not manquants:
        return
    telecharger_companyfacts()
    DOSSIER_BPA.mkdir(parents=True, exist_ok=True)
    print(f"  extraction des BPA de {len(manquants)} sociétés depuis companyfacts.zip")
    with zipfile.ZipFile(ZIP) as z:
        noms = set(z.namelist())
        for cik in manquants:
            membre = f"CIK{cik:010d}.json"
            sortie = {"cik": cik, "nom": None, "concepts": {}}
            if membre in noms:
                faits = json.loads(z.read(membre))
                sortie["nom"] = faits.get("entityName")
                gaap = faits.get("facts", {}).get("us-gaap", {})
                for concept in CONCEPTS_BPA:
                    valeurs = gaap.get(concept, {}).get("units", {}).get("USD/shares")
                    if valeurs:
                        sortie["concepts"][concept] = [
                            {k: v[k] for k in ("start", "end", "val", "filed", "form", "accn") if k in v}
                            for v in valeurs
                            if "start" in v
                        ]
            (DOSSIER_BPA / f"{cik}.json").write_text(json.dumps(sortie))


@lru_cache(maxsize=None)
def bpa(cik: int) -> dict:
    """Faits BPA d'un CIK (après extract_bpa)."""
    chemin = DOSSIER_BPA / f"{cik}.json"
    if not chemin.exists():
        extraire_bpa({cik})
    return json.loads(chemin.read_text())
