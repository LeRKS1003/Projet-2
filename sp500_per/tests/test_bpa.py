from datetime import date

from sp500_per.bpa import Fait, bpa_12m


def f(debut, fin, val, depot):
    return Fait(date.fromisoformat(debut), date.fromisoformat(fin), val, date.fromisoformat(depot))


# Exercice calendaire : T1..T3 publiés en 10-Q, annuel en 10-K.
FAITS = [
    f("2019-01-01", "2019-03-31", 1.0, "2019-05-01"),
    f("2019-04-01", "2019-06-30", 1.1, "2019-08-01"),
    f("2019-01-01", "2019-06-30", 2.1, "2019-08-01"),   # cumul 6 mois
    f("2019-07-01", "2019-09-30", 1.2, "2019-11-01"),
    f("2019-01-01", "2019-09-30", 3.3, "2019-11-01"),   # cumul 9 mois
    f("2019-01-01", "2019-12-31", 4.6, "2020-02-15"),   # annuel -> T4 = 1.3
    f("2020-01-01", "2020-03-31", 1.5, "2020-05-01"),
    f("2019-01-01", "2019-03-31", 1.0, "2020-05-01"),   # comparatif
]


def test_quatre_trimestres_avec_t4_recompose():
    r = bpa_12m(FAITS, date(2020, 5, 29))
    assert r.methode == "4 trimestres"
    # T2..T4 2019 + T1 2020 = 1.1 + 1.2 + 1.3 + 1.5
    assert abs(r.bpa - 5.1) < 1e-9
    assert r.periodes[2][3].startswith("T4")


def test_date_de_depot_stricte():
    # Le 10-K est déposé le 15/02 : au 14/02 il est inconnu, on reste sur T4 2018..T3 2019 -> incomplet,
    # donc repli sur annuel + cumul impossible (pas d'annuel 2018) -> manquant.
    assert bpa_12m(FAITS, date(2020, 2, 14)).bpa is None
    r = bpa_12m(FAITS, date(2020, 2, 28))
    assert abs(r.bpa - 4.6) < 1e-9  # T4 connu : 4 trimestres 2019 = annuel


def test_retraitement_ulterieur_ignore():
    faits = FAITS + [f("2020-01-01", "2020-03-31", 0.5, "2020-08-01")]  # T1 2020 retraité en août 2020
    assert abs(bpa_12m(faits, date(2020, 5, 29)).bpa - 5.1) < 1e-9
    # Après le dépôt du retraitement, la valeur connue change.
    assert abs(bpa_12m(faits, date(2020, 8, 31)).bpa - 4.1) < 1e-9


def test_split_entre_depot_et_date():
    # Split 4:1 le 2020-05-15 : les BPA déposés avant sont divisés par 4.
    def facteur(depot, d=date(2020, 5, 29)):
        return 4.0 if depot < date(2020, 5, 15) <= d else 1.0
    r = bpa_12m(FAITS, date(2020, 5, 29), facteur)
    assert abs(r.bpa - 5.1 / 4) < 1e-9


def test_repli_annuel_plus_cumul():
    faits = [
        f("2019-01-01", "2019-12-31", 4.0, "2020-02-15"),
        f("2020-01-01", "2020-06-30", 2.5, "2020-08-01"),
        f("2019-01-01", "2019-06-30", 2.0, "2020-08-01"),
    ]
    r = bpa_12m(faits, date(2020, 8, 31))
    assert r.methode == "annuel + cumul"
    assert abs(r.bpa - 4.5) < 1e-9


def test_donnees_trop_anciennes():
    assert bpa_12m(FAITS, date(2021, 6, 30)).bpa is None
