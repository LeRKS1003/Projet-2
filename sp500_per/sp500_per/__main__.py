"""Point d'entrée : python -m sp500_per [--verif [AAAA-MM]] [--debut AAAA-MM] [--fin AAAA-MM-JJ]"""
import argparse
from datetime import date

import pandas as pd

from . import composition, prix, sec
from .bpa import bpa_12m, faits_depuis_json
from .config import DEBUT, SEUIL_PER, SORTIES, TICKERS_VERIF
from .resolution import Resolveur


def statut_ligne(cours, bpa):
    if cours is None or bpa is None:
        return "manquant"
    if bpa <= 0:
        return "PER négatif"
    return "PER > 40" if cours / bpa > SEUIL_PER else "PER <= 40"


class Calculateur:
    def __init__(self, actuels: pd.DataFrame, resolveur: Resolveur):
        self.resolveur = resolveur
        self.secteurs = {composition.ticker_sec(t): s for t, s in zip(actuels["ticker"], actuels["secteur"])}
        self._faits: dict[int, tuple[str | None, dict]] = {}

    def faits(self, cik: int):
        if cik not in self._faits:
            brut = sec.bpa(cik)
            self._faits[cik] = (brut.get("nom"), {c: faits_depuis_json(v) for c, v in brut["concepts"].items()})
        return self._faits[cik]

    def secteur(self, t: str) -> str:
        return self.secteurs.get(t) or prix.secteur_yahoo(t)

    def ligne(self, ticker: str, d: date) -> dict:
        t = composition.ticker_sec(ticker)
        res = self.resolveur.resoudre(ticker)
        ligne = {"date": d, "ticker": ticker, "nom": res.nom_historique, "secteur": None,
                 "cours": None, "bpa_12m": None, "per": None, "statut": None, "cik": res.cik,
                 "methode_bpa": None, "motif_manquant": None, "periodes": []}
        motifs = []

        # Un ticker réattribué depuis à une autre société : la série yfinance n'est pas la bonne.
        cik_actuel = sec.tickers_sec().get(t, (None,))[0]
        if res.ciks and cik_actuel is not None and cik_actuel not in res.ciks:
            motifs.append("ticker réattribué (cours yfinance d'une autre société)")
        else:
            ligne["cours"] = prix.cours_cote(t, d)
            if ligne["cours"] is None:
                motifs.append("pas de cours yfinance")

        if not res.ciks:
            motifs.append("pas de CIK")
        else:
            echec = "pas de BPA XBRL"
            # Premier CIK candidat ayant un BPA 12 mois connu à la date.
            for cik in res.ciks:
                nom_sec, concepts = self.faits(cik)
                ligne["nom"] = ligne["nom"] or nom_sec
                for concept, faits in concepts.items():  # Diluted, à défaut Basic, puis BasicAndDiluted
                    r = bpa_12m(faits, d, lambda depot: prix.facteur_splits_entre(t, depot, d))
                    if r.bpa is not None:
                        ligne.update(cik=cik, bpa_12m=r.bpa, periodes=r.periodes,
                                     methode_bpa=f"{concept.removeprefix('EarningsPerShare')} / {r.methode}")
                        break
                    echec = r.methode
                if ligne["bpa_12m"] is not None:
                    break
            else:
                motifs.append(echec)

        ligne["statut"] = statut_ligne(ligne["cours"], ligne["bpa_12m"])
        if ligne["statut"] != "manquant":
            ligne["per"] = ligne["cours"] / ligne["bpa_12m"]
        ligne["motif_manquant"] = "; ".join(motifs) or None
        ligne["secteur"] = self.secteur(t)
        return ligne


def preparer(dates: list[date], forcer_prix: bool):
    historique = composition.charger_historique()
    actuels = composition.charger_actuels()
    membres = {d: composition.membres_a(historique, pd.Timestamp(d)) for d in dates}
    tous = sorted({t for m in membres.values() for t in m})

    print(f"Résolution ticker -> CIK pour {len(tous)} tickers")
    resolveur = Resolveur(actuels)
    for t in tous:
        resolveur.resoudre(t)
    sec.extraire_bpa({c for r in resolveur.cache.values() for c in r.ciks})

    yahoo = [composition.ticker_sec(t) for t in tous]
    prix.precharger(yahoo, forcer=False)
    perimes = [t for t in yahoo if prix.cache_perime(t, dates[-1])]
    if forcer_prix or perimes:
        prix.precharger(yahoo if forcer_prix else perimes, forcer=True)
    return membres, Calculateur(actuels, resolveur), resolveur


def ecrire_resolutions(resolveur: Resolveur):
    df = pd.DataFrame([vars(r) for r in resolveur.cache.values()])
    non = df[df["ciks"].map(len) == 0]
    df["ciks"] = df["ciks"].map(lambda c: ";".join(map(str, c)))
    SORTIES.mkdir(parents=True, exist_ok=True)
    df.sort_values(["methode", "ticker"]).to_csv(SORTIES / "correspondances.csv", index=False)
    df.loc[non.index].sort_values("ticker").to_csv(SORTIES / "non_resolus.csv", index=False)
    print(f"Tickers non résolus : {len(non)} (voir sorties/non_resolus.csv)")
    if len(non):
        print("  " + ", ".join(non["ticker"].head(60)) + (" ..." if len(non) > 60 else ""))


def verification(mois: str, forcer_prix: bool):
    fin = (pd.Period(mois, "M").end_time).date()
    dates = prix.fins_de_mois(mois, fin)
    if not dates:
        raise SystemExit(f"Aucun jour de bourse trouvé pour {mois}")
    d = dates[-1]
    membres, calc, resolveur = preparer([d], forcer_prix)
    print(f"\n=== Vérification au {d} ===\n")
    lignes = []
    for t in TICKERS_VERIF:
        l = calc.ligne(t, d)
        lignes.append(l)
        per = f"{l['per']:.1f}" if l["per"] is not None else "-"
        cours = f"{l['cours']:.2f}" if l["cours"] is not None else "-"
        bpa = f"{l['bpa_12m']:.2f}" if l["bpa_12m"] is not None else "-"
        print(f"{t:5}  cours {cours:>9}  BPA 12m {bpa:>7}  PER {per:>7}  [{l['statut']}]  "
              f"CIK {l['cik']}  {l['methode_bpa'] or l['motif_manquant']}")
        for debut, fin_p, val, origine in l["periodes"]:
            print(f"         {debut} -> {fin_p}  {val:8.3f}  ({origine})")
    detail = [calc.ligne(t, d) for t in membres[d]]
    mensuel = synthese(pd.DataFrame(detail))
    print("\nSynthèse du mois :")
    print(mensuel.to_string(index=False))
    SORTIES.mkdir(parents=True, exist_ok=True)
    colonnes_detail(pd.DataFrame(detail)).to_csv(SORTIES / f"detail_verif_{mois}.csv", index=False)
    ecrire_resolutions(resolveur)


def colonnes_detail(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["date", "ticker", "nom", "secteur", "cours", "bpa_12m", "per", "statut", "cik",
            "methode_bpa", "motif_manquant"]
    out = df[cols].copy()
    for c in ("cours", "bpa_12m", "per"):
        out[c] = pd.to_numeric(out[c]).round(4)
    out["cik"] = out["cik"].astype("Int64")
    return out


def synthese(detail: pd.DataFrame) -> pd.DataFrame:
    g = detail.groupby("date")["statut"]
    m = pd.DataFrame({
        "nb_membres": g.size(),
        "nb_per_sup_40": g.apply(lambda s: (s == "PER > 40").sum()),
        "nb_per_negatifs": g.apply(lambda s: (s == "PER négatif").sum()),
        "nb_manquants": g.apply(lambda s: (s == "manquant").sum()),
    })
    m["nb_per_positifs"] = m["nb_membres"] - m["nb_per_negatifs"] - m["nb_manquants"]
    m["pct_per_sup_40_parmi_positifs"] = (100 * m["nb_per_sup_40"] / m["nb_per_positifs"]).round(2)
    return m.reset_index()


def graphique(mensuel: pd.DataFrame, chemin):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    x = pd.to_datetime(mensuel["date"])
    connus = mensuel["nb_membres"] - mensuel["nb_manquants"]
    part40 = mensuel["pct_per_sup_40_parmi_positifs"]
    partneg = 100 * mensuel["nb_per_negatifs"] / connus

    encre, encre2, grille = "#0b0b0b", "#52514e", "#e4e3df"
    bleu, orange = "#2a78d6", "#eb6834"
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ax.plot(x, part40, color=bleu, lw=2, label="PER > 40 (en % des PER positifs)")
    ax.plot(x, partneg, color=orange, lw=2, label="PER négatif (en % des membres avec données)")
    for serie, couleur in ((part40, bleu), (partneg, orange)):
        if serie.notna().any():
            ax.annotate(f"{serie.dropna().iloc[-1]:.1f} %", (x[serie.notna()].iloc[-1], serie.dropna().iloc[-1]),
                        xytext=(6, 0), textcoords="offset points", va="center", color=encre, fontsize=9)
    ax.set_title("S&P 500 : part des PER > 40 et des PER négatifs, fin de mois", loc="left",
                 color=encre, fontsize=13, pad=30)
    ax.set_ylabel("%", color=encre2)
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", color=grille, lw=0.8)
    ax.set_axisbelow(True)
    for cote in ("top", "right", "left"):
        ax.spines[cote].set_visible(False)
    ax.spines["bottom"].set_color(encre2)
    ax.tick_params(colors=encre2, length=0)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, labelcolor=encre, fontsize=9)
    fig.text(0.01, 0.01, "Sources : fja05680/sp500, SEC XBRL (BPA dilué 12 mois point-in-time), Yahoo Finance.",
             color=encre2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(chemin, facecolor=fig.get_facecolor())
    plt.close(fig)


def complet(debut: str, fin: date | None, forcer_prix: bool):
    dates = prix.fins_de_mois(debut, fin)
    print(f"{len(dates)} fins de mois : {dates[0]} -> {dates[-1]}")
    membres, calc, resolveur = preparer(dates, forcer_prix)
    ecrire_resolutions(resolveur)
    lignes = []
    for i, d in enumerate(dates, 1):
        lignes.extend(calc.ligne(t, d) for t in membres[d])
        if i % 12 == 0 or i == len(dates):
            print(f"  {i}/{len(dates)} mois calculés ({d})")
    detail = pd.DataFrame(lignes)
    mensuel = synthese(detail)
    SORTIES.mkdir(parents=True, exist_ok=True)
    mensuel.to_csv(SORTIES / "mensuel.csv", index=False)
    colonnes_detail(detail).to_csv(SORTIES / "detail.csv", index=False)
    graphique(mensuel, SORTIES / "per_sup_40.png")
    print(f"\nÉcrit : {SORTIES / 'mensuel.csv'}, {SORTIES / 'detail.csv'}, {SORTIES / 'per_sup_40.png'}")
    print(mensuel.tail(12).to_string(index=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verif", nargs="?", const="2021-07", metavar="AAAA-MM",
                   help="calcule un seul mois (défaut 2021-07) et affiche le détail de 7 grandes valeurs")
    p.add_argument("--debut", default=DEBUT, help="premier mois (AAAA-MM), défaut %(default)s")
    p.add_argument("--fin", type=date.fromisoformat, default=None, help="dernière date (AAAA-MM-JJ)")
    p.add_argument("--maj-prix", action="store_true", help="retélécharge tous les cours yfinance")
    p.add_argument("--maj-sec", action="store_true", help="retélécharge companyfacts.zip et réextrait les BPA")
    args = p.parse_args()

    if args.maj_sec:
        sec.telecharger_companyfacts(forcer=True)
    if args.verif:
        verification(args.verif, args.maj_prix)
    else:
        complet(args.debut, args.fin, args.maj_prix)


if __name__ == "__main__":
    main()
