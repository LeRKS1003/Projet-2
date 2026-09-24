"""BPA 12 mois glissants « point-in-time » à partir des faits XBRL.

À une date D, on ne regarde que les faits dont la date de dépôt (« filed ») est
strictement antérieure à D. Pour une même période (début, fin) déposée plusieurs
fois (comparatifs, retraitements), on garde la dernière valeur déposée avant D :
c'est la valeur connue à D, pas une correction publiée plus tard.

BPA 12 mois = somme des 4 derniers trimestres, T4 = annuel - T1 - T2 - T3.
Deux identités équivalentes servent de repli quand les 4 trimestres ne sont pas
disponibles (début de l'XBRL en 2009-2010, trimestre manquant) :
  - la dernière période publiée est un exercice complet : BPA 12m = BPA annuel ;
  - BPA 12m = annuel N-1 + cumul N en cours - cumul N-1 équivalent.

Chaque valeur est ramenée à la base d'actions en vigueur à D : si une division
d'actions (split) a eu lieu entre la date de dépôt et D, la valeur est divisée
par le ratio.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

TRIMESTRE = (70, 105)
SEMESTRE = (170, 200)
NEUF_MOIS = (250, 290)
ANNUEL = (340, 390)
FRAICHEUR_MAX = 230  # jours max entre la fin de la dernière période et D


@dataclass(frozen=True)
class Fait:
    debut: date
    fin: date
    val: float
    depot: date

    @property
    def duree(self) -> int:
        return (self.fin - self.debut).days + 1


@dataclass
class Composante:
    """Valeur d'une période, éventuellement recomposée (T4 = annuel - 3T)."""
    debut: date
    fin: date
    termes: list = field(default_factory=list)  # [(signe, Fait)]
    origine: str = "publié"

    def valeur(self, facteur_split) -> float:
        return sum(s * f.val / facteur_split(f.depot) for s, f in self.termes)


@dataclass
class ResultatBPA:
    bpa: float | None
    methode: str
    periodes: list = field(default_factory=list)  # [(debut, fin, valeur ajustée, origine)]


def _dans(duree: int, bornes: tuple[int, int]) -> bool:
    return bornes[0] <= duree <= bornes[1]


def _proche(a: date, b: date, jours: int = 10) -> bool:
    return abs((a - b).days) <= jours


def faits_depuis_json(valeurs: list[dict]) -> list[Fait]:
    res = []
    for v in valeurs:
        try:
            res.append(Fait(date.fromisoformat(v["start"]), date.fromisoformat(v["end"]),
                            float(v["val"]), date.fromisoformat(v["filed"])))
        except (KeyError, ValueError, TypeError):
            continue
    return res


def connus_a(faits: list[Fait], d: date) -> list[Fait]:
    """Dernière valeur déposée avant d pour chaque période (début, fin)."""
    par_periode: dict[tuple[date, date], Fait] = {}
    for f in faits:
        if f.depot < d:
            cle = (f.debut, f.fin)
            if cle not in par_periode or f.depot >= par_periode[cle].depot:
                par_periode[cle] = f
    return list(par_periode.values())


def _trimestres(connus: list[Fait]) -> list[Composante]:
    """Trimestres publiés + T4 recomposés, un par date de fin, triés."""
    trims = {f.fin: Composante(f.debut, f.fin, [(1, f)]) for f in connus if _dans(f.duree, TRIMESTRE)}
    cumuls9 = [f for f in connus if _dans(f.duree, NEUF_MOIS)]
    for a in (f for f in connus if _dans(f.duree, ANNUEL)):
        if any(_proche(fin, a.fin) for fin in trims):
            continue
        dedans = sorted((q for q in trims.values()
                         if q.debut >= a.debut - timedelta(days=10) and q.fin <= a.fin - timedelta(days=60)
                         and q.origine == "publié"),
                        key=lambda q: q.fin)
        # T4 = annuel - T1 - T2 - T3 (les 3 trimestres doivent être contigus depuis le début d'exercice)
        if (len(dedans) == 3 and _proche(dedans[0].debut, a.debut)
                and all(_proche(dedans[i].fin + timedelta(days=1), dedans[i + 1].debut) for i in range(2))):
            termes = [(1, a)] + [(-1, f) for q in dedans for _, f in q.termes]
            trims[a.fin] = Composante(dedans[-1].fin + timedelta(days=1), a.fin, termes, "T4 = annuel - T1..T3")
            continue
        # Repli : T4 = annuel - cumul 9 mois
        c9 = [c for c in cumuls9 if _proche(c.debut, a.debut)
              and _dans((a.fin - c.fin).days, TRIMESTRE)]
        if c9:
            c = max(c9, key=lambda c: c.depot)
            trims[a.fin] = Composante(c.fin + timedelta(days=1), a.fin, [(1, a), (-1, c)], "T4 = annuel - 9 mois")
    return sorted(trims.values(), key=lambda q: q.fin)


def _quatre_trimestres(trims: list[Composante]) -> list[Composante] | None:
    if len(trims) < 4:
        return None
    q = trims[-4:]
    contigus = all(_proche(q[i].fin + timedelta(days=1), q[i + 1].debut) for i in range(3))
    duree = (q[-1].fin - q[0].debut).days + 1
    return q if contigus and _dans(duree, ANNUEL) else None


def _ytd(connus: list[Fait]) -> tuple[Fait, Fait, Fait] | None:
    """(annuel N-1, cumul N, cumul N-1) pour l'identité annuel + cumul - cumul."""
    annuels = sorted((f for f in connus if _dans(f.duree, ANNUEL)), key=lambda f: f.fin)
    if not annuels:
        return None
    a = annuels[-1]
    cumuls = [f for f in connus
              if f.fin > a.fin and _proche(f.debut, a.fin + timedelta(days=1))
              and any(_dans(f.duree, b) for b in (TRIMESTRE, SEMESTRE, NEUF_MOIS))]
    for cur in sorted(cumuls, key=lambda f: f.fin, reverse=True):
        for prec in connus:
            if (_proche(prec.debut, a.debut) and abs(prec.duree - cur.duree) <= 10
                    and _proche(prec.fin + timedelta(days=365), cur.fin, 10)):
                return a, cur, prec
    return None


def bpa_12m(faits: list[Fait], d: date, facteur_split=lambda depot: 1.0) -> ResultatBPA:
    """BPA 12 mois connu à la date d, ramené à la base d'actions de d."""
    connus = connus_a(faits, d)
    if not connus:
        return ResultatBPA(None, "aucun BPA déposé avant la date")

    candidats = []  # (fin de la période la plus récente, priorité, composantes, méthode)
    q = _quatre_trimestres(_trimestres(connus))
    if q:
        candidats.append((q[-1].fin, 0, q, "4 trimestres"))
    annuels = [f for f in connus if _dans(f.duree, ANNUEL)]
    if annuels:
        a = max(annuels, key=lambda f: f.fin)
        candidats.append((a.fin, 1, [Composante(a.debut, a.fin, [(1, a)], "annuel")], "dernier exercice"))
    y = _ytd(connus)
    if y:
        a, cur, prec = y
        candidats.append((cur.fin, 2, [Composante(a.debut, cur.fin, [(1, a), (1, cur), (-1, prec)],
                                                  "annuel + cumul N - cumul N-1")],
                          "annuel + cumul"))
    if not candidats:
        return ResultatBPA(None, "pas assez de périodes pour 12 mois")

    fin, _, comps, methode = max(candidats, key=lambda c: (c[0], -c[1]))
    if (d - fin).days > FRAICHEUR_MAX:
        return ResultatBPA(None, f"dernier BPA trop ancien (période close le {fin})")
    periodes = [(c.debut, c.fin, c.valeur(facteur_split), c.origine) for c in comps]
    return ResultatBPA(sum(p[2] for p in periodes), methode, periodes)
