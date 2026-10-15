"""
Analyseurs : JEV (texte → probabilités) et cinématique (mouvement après une sommation).
Portage de web/js/analysis/{questions,cinematique}.js et tests/bench_lib.mjs (analyseurDiffere).
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Callable

from .fusion import P, Parametres
from .types import Observation, Piste

# client(body) → (code HTTP, réponse) : en production ClientJEV.traiter (clé, cache, budget restent dans server/)
ClientJEV = Callable[[dict], tuple[int, dict]]
PAUSE_ERREUR_S = 0.8          # identique à PAUSE_ERREUR_MS : on ne martèle pas l'API après une erreur


@dataclass
class Hypotheses:
    """Les 2 questions opposées posées à JEV (si JEV est cohérent, p(oui) + p(non) ≈ 1). Fournies par la source."""
    langue: str
    contexte: str
    positive: str                # « Cette cible est un zombie… »
    negative: str                # « Cette cible est un survivant humain… »


def requete(cibles: list[Observation], h: Hypotheses) -> dict:
    """Mêmes questions que le navigateur, caractère pour caractère ⇒ mêmes clés de cache, même calibration."""
    qs = {}
    for o in cibles:
        qs["z_" + o.entite] = {"type": "noul", "instructions": f"{o.texte} {h.positive}"}
        qs["h_" + o.entite] = {"type": "noul", "instructions": f"{o.texte} {h.negative}"}
    return {"questions": qs, "state": {"langue": h.langue, "contexte": h.contexte}}


def appliquer(cibles: list[Observation], pistes: dict[str, Piste], answers: dict) -> list[str]:
    manquantes = []
    for o in cibles:
        piste = pistes.get(o.entite)
        if piste is None:
            continue
        z = (answers.get("z_" + o.entite) or {}).get("noul")
        hh = (answers.get("h_" + o.entite) or {}).get("noul")
        if z is None or hh is None:
            piste.besoin_analyse = True
            manquantes.append(o.entite)
            continue
        piste.pZ, piste.incoh = (z + (1 - hh)) / 2, abs(z - (1 - hh))
        piste.lectures += 1
        if o.a_reagi:
            piste.lue_avec_reaction = True
        else:
            piste.p_avant = piste.pZ
    return manquantes


@dataclass
class AnalyseurJEV:
    """Une requête à la fois. synchrone=True : réponse calculée tout de suite et livrée après `latence` secondes
    d'horloge de la source (simulation reproductible) ; sinon : appel dans un thread, livré dès qu'il revient."""
    client: ClientJEV
    latence: float = 0.0
    synchrone: bool = False
    modele_servi: str | None = None
    erreur: str = ""
    _attente: dict | None = None
    _pause_jusqu_a: float = -math.inf
    _verrou: threading.Lock = field(default_factory=threading.Lock)

    @property
    def occupe(self) -> bool:
        return self._attente is not None

    def classer(self, cibles: list[Observation], pistes: dict[str, Piste], h: Hypotheses, t: float):
        if self.occupe or t < self._pause_jusqu_a:
            return
        for o in cibles:
            pistes[o.entite].besoin_analyse = False
        attente = {"fin": t + self.latence, "cibles": cibles, "pistes": pistes, "reponse": None}
        self._attente = attente
        if self.synchrone:
            attente["reponse"] = self.client(requete(cibles, h))
        else:
            def appel():
                rep = self.client(requete(cibles, h))
                with self._verrou:
                    attente["reponse"] = rep
            threading.Thread(target=appel, daemon=True).start()

    def tic(self, t: float):
        """Livre la réponse si elle est arrivée et que la latence simulée est écoulée."""
        with self._verrou:
            a = self._attente
            if a is None or a["reponse"] is None or t < a["fin"]:
                return
            self._attente = None
        code, rep = a["reponse"]
        if code != 200 or "answers" not in rep:
            self.erreur = str(rep.get("error", f"HTTP {code}"))
            for o in a["cibles"]:
                if o.entite in a["pistes"]:
                    a["pistes"][o.entite].besoin_analyse = True
            self._pause_jusqu_a = t + PAUSE_ERREUR_S
            return
        self.erreur = ""
        if rep.get("model"):
            self.modele_servi = rep["model"]
        appliquer(a["cibles"], a["pistes"], rep["answers"])


def suivre_cinematique(piste: Piste, o: Observation, t: float, params: Parametres = P):
    """Fenêtre [sommation + 0,5 s ; + 2 s] : déplacement < 0,2 m = s'est arrêté, > 0,5 m = a continué."""
    somme_at = o.signaux.get("sommeAt")
    if somme_at is not None and somme_at != piste.derniere_somme_at:
        piste.derniere_somme_at = somme_at
        piste.fenetre = {"debut": somme_at + params.fenetre[0], "fin": somme_at + params.fenetre[1], "p0": None}
    f = piste.fenetre
    if not f:
        return
    x, z = o.signaux["x"], o.signaux["z"]
    if not f["p0"] and t >= f["debut"]:
        f["p0"] = (x, z)
    if f["p0"] and t >= f["fin"]:
        d = math.hypot(x - f["p0"][0], z - f["p0"][1])
        arret = True if d < params.seuil_arret else False if d > params.seuil_bouge else None
        piste.mesures.append({"t": t, "d": round(d, 2), "arret": arret})
        piste.fenetre = None
