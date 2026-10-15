"""
Cache des réponses JEV (questions Noul) : même modèle + même state + même question ⇒ même réponse.

La clé est un sha256 de la forme canonique JSON ; tests/bench.mjs calcule exactement la même
pour rejouer le cache sans réseau (benchmark headless).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path

TYPES_CACHES = ("noul",)


def canonique(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def cle(modele: str, state: dict, question: dict) -> str:
    return hashlib.sha256(canonique({"m": modele, "q": question, "s": state}).encode()).hexdigest()


def reponse_valide(question: dict, reponse) -> bool:
    if not isinstance(reponse, dict) or question.get("type") not in TYPES_CACHES:
        return False
    p = reponse.get("noul")
    return isinstance(p, (int, float)) and not isinstance(p, bool) and 0 <= p <= 1


class CacheJEV:
    def __init__(self, chemin: Path):
        self.chemin, self._verrou = chemin, threading.Lock()
        self.entrees: dict[str, dict] = {}
        if chemin.exists():
            self.entrees = json.loads(chemin.read_text(encoding="utf-8")).get("entrees", {})

    def chercher(self, payload: dict) -> tuple[dict, dict, str | None]:
        """→ (réponses trouvées, questions manquantes, modèle servi des réponses trouvées)."""
        trouvees, manquantes, servi = {}, {}, None
        with self._verrou:
            for nom, q in payload["questions"].items():
                e = self.entrees.get(cle(payload["model"], payload["state"], q))
                if e is None:
                    manquantes[nom] = q
                else:
                    trouvees[nom], servi = e["reponse"], e["modele_servi"]
        return trouvees, manquantes, servi

    def ranger(self, payload: dict, rep: dict) -> int:
        """Enregistre les réponses valides d'un appel réussi. → nombre d'entrées ajoutées."""
        ajout = 0
        with self._verrou:
            for nom, q in payload["questions"].items():
                r = (rep.get("answers") or {}).get(nom)
                if reponse_valide(q, r):
                    self.entrees[cle(payload["model"], payload["state"], q)] = {
                        "reponse": r, "modele_servi": rep.get("model"), "date": datetime.now().isoformat(timespec="seconds"),
                        "langue": payload["state"].get("langue"), "question": q.get("instructions", "")[:300]}
                    ajout += 1
            if ajout:
                self._sauver()
        return ajout

    def _sauver(self):  # écriture atomique : jamais de fichier à moitié écrit
        tmp = self.chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "entrees": self.entrees}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.chemin)
