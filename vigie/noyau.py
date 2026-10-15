"""
Contrat des sources et des répondeurs, et la règle non négociable du projet, appliquée dans le code :

    source du MONDE RÉEL ⇒ répondeurs INFORMATIFS uniquement (alerte, notification, enregistrement, journal).

Un répondeur qui agit (tirer dans le jeu, bloquer…) déclare informatif = False ; le brancher sur une source réelle
lève une erreur au démarrage, avant toute observation.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol

from .types import Decision, Piste


class Source(Protocol):
    nom: str
    reel: bool                   # True = capteurs du monde réel (caméra, logs, réseau…)


class Repondeur(Protocol):
    nom: str
    informatif: bool             # True = alerte / notification / enregistrement / journal, rien d'autre

    def repondre(self, source: str, t: float, decision: Decision, pistes: dict[str, Piste]) -> None: ...


class RegleViolee(Exception):
    pass


def verifier_repondeurs(source: Source, repondeurs: Iterable[Repondeur]) -> list[Repondeur]:
    repondeurs = list(repondeurs)
    if source.reel:
        actifs = [r.nom for r in repondeurs if not r.informatif]
        if actifs:
            raise RegleViolee(f"source réelle « {source.nom} » : répondeurs non informatifs interdits ({', '.join(actifs)}). "
                              "Réponses autorisées : alerte, notification, enregistrement, journal.")
    return repondeurs


class JournalRepondeur:
    """Journal JSONL des décisions (actions et changements de cible, horodatés). Informatif."""
    nom, informatif = "journal", True

    def __init__(self, chemin: Path):
        self.chemin, self._verrou, self._cible = chemin, threading.Lock(), {}

    def repondre(self, source: str, t: float, decision: Decision, pistes: dict[str, Piste]) -> None:
        # une ligne quand il se passe quelque chose : action, ou changement de cible (pas 60 lignes/s pour la même)
        actions = decision.sommer or decision.sommer_cibles or decision.recharger or decision.bloques
        if not actions and decision.cible == self._cible.get(source):
            return
        self._cible[source] = decision.cible
        ligne = {"date": datetime.now().isoformat(timespec="seconds"), "source": source, "t": round(t, 3),
                 "cible": decision.cible, "sommer": decision.sommer, "sommer_cibles": decision.sommer_cibles,
                 "recharger": decision.recharger, "bloques": decision.bloques, "raison": decision.raison}
        if decision.cible and decision.cible in pistes:
            p = pistes[decision.cible]
            ligne["preuves"] = {k: round(v, 3) for k, v in (p.preuves or {}).items()}
            ligne["L"] = round(p.L, 3) if p.L is not None else None
        with self._verrou, self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
