"""
Fusion bayésienne en log-odds + test séquentiel de Wald (portage exact de web/js/analysis/fusion.js et policy/sprt.js).
L = logit(a priori) + preuve JEV (dernière lecture cohérente) + preuves cinématiques.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .types import Piste

RACINE = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Parametres:
    """Identiques à FUSION / INCOH_MAX de web/js/config.js (vérifié par tests/test_vigie.py)."""
    prior: float = 0.5
    p_clip: float = 0.01
    p_bouge_si_zombie: float = 0.98
    p_bouge_si_humain: float = 0.05
    p_bouge_encore_si_humain: float = 0.3
    fenetre: tuple[float, float] = (0.5, 2.0)
    seuil_arret: float = 0.2
    seuil_bouge: float = 0.5
    alpha: float = 0.005
    beta: float = 0.05
    incoh_max: float = 0.15

    @property
    def seuil_a(self) -> float:
        return math.log((1 - self.beta) / self.alpha)

    @property
    def seuil_b(self) -> float:
        return math.log(self.beta / (1 - self.alpha))


P = Parametres()


def logit(p: float, params: Parametres = P) -> float:
    q = min(1 - params.p_clip, max(params.p_clip, p))
    return math.log(q / (1 - q))


def sigmoide(L: float) -> float:
    return 1 / (1 + math.exp(-L))


# ---------- Calibration (phase 5) : même fichier que le navigateur ----------
@dataclass(frozen=True)
class Calibrateur:
    modele: str
    methode: str
    conf: dict

    @classmethod
    def depuis_js(cls, chemin: Path = RACINE / "web" / "js" / "analysis" / "calibration_jev.js") -> "Calibrateur":
        conf = json.loads(re.search(r"=\s*(\{.*\});", chemin.read_text(encoding="utf-8"), re.S).group(1))
        return cls(conf["modele"], conf["methode"], conf)

    def p_calibree(self, p: float) -> float:
        c = self.conf
        if self.methode == "platt":
            return sigmoide(c["a"] * logit(p) + c["b"])
        if self.methode == "isotonique":
            x, y = c["x"], c["y"]
            if p <= x[0]:
                return y[0]
            if p >= x[-1]:
                return y[-1]
            i = 1
            while p > x[i]:
                i += 1
            return y[i] if x[i] == x[i - 1] else y[i - 1] + (y[i] - y[i - 1]) * (p - x[i - 1]) / (x[i] - x[i - 1])
        raise ValueError(f"méthode de calibration inconnue : {self.methode}")

    def llr(self, p: float) -> float:
        return logit(self.p_calibree(p)) - logit(self.conf["tauxZombies"])


# ---------- Preuves ----------
def preuve_jev(piste: Piste, cal: Calibrateur | None = None, params: Parametres = P) -> float:
    """Dernière lecture cohérente seulement ; lecture incohérente = aucune preuve."""
    if piste.pZ is None or piste.incoh > params.incoh_max:
        return 0.0
    return cal.llr(piste.pZ) if cal else logit(piste.pZ, params)


def preuve_cinematique(mesures: list[dict], params: Parametres = P) -> float:
    """Désobéissance persistante possible : une 2e désobéissance prouve moins que la 1re."""
    pz, L, deja_bouge = params.p_bouge_si_zombie, 0.0, False
    for m in mesures:
        if m["arret"] is None:
            continue
        ph = params.p_bouge_encore_si_humain if deja_bouge else params.p_bouge_si_humain
        L += math.log((1 - pz) / (1 - ph)) if m["arret"] else math.log(pz / ph)
        if not m["arret"]:
            deja_bouge = True
    return L


def fusionner(piste: Piste, cal: Calibrateur | None = None, params: Parametres = P) -> float:
    jev, cine = preuve_jev(piste, cal, params), preuve_cinematique(piste.mesures, params)
    piste.preuves = {"prior": logit(params.prior, params), "jev": jev, "cine": cine}
    piste.L = piste.preuves["prior"] + jev + cine
    piste.p_post = sigmoide(piste.L)
    return piste.L


def statut_sprt(piste: Piste, params: Parametres = P) -> str:
    if piste.L is None or (piste.pZ is None and not piste.mesures):
        return "analyse"
    return "zombie" if piste.L >= params.seuil_a else "humain" if piste.L <= params.seuil_b else "incertain"
