"""
Appels à l'API JEV : modèle figé, délai global, retries, budget d'appels, journal des appels.

La clé API n'est utilisée que dans l'en-tête Authorization vers l'API.
Elle n'est jamais renvoyée au navigateur ni écrite dans un journal.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .faux_jev import jev_simule

API = "https://api.typesafe.ai/v1/systemone"
MODELE_JEV = "jev-1.13.0"          # version figée : seuils calibrés sur elle (option --modele pour changer)
DELAI_TOTAL_S = 10.0               # délai global, retries compris
ESSAIS = 2
CODES_REESSAI = (429, 500, 502, 503, 504)
TYPES_QUESTION = ("noul", "choice", "score")
MAX_QUESTIONS = 12                 # v2 : 5 cibles × 2 questions ; v1 : 1 question


# ================= Budget =================
@dataclass
class Budget:
    """Seau à jetons (débit par minute + rafale) + plafonds par lancement du serveur."""
    par_minute: float = 300
    rafale: int = 20
    max_appels: int = 1000
    max_tokens: int | None = None
    horloge: Callable[[], float] = time.monotonic
    appels: int = 0
    tokens: int = 0
    _jetons: float = field(init=False)
    _t: float = field(init=False)
    _verrou: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        self._jetons, self._t = float(self.rafale), self.horloge()

    def reserver(self) -> str | None:
        """Réserve un appel. Renvoie None si accepté, sinon la raison du refus."""
        with self._verrou:
            now = self.horloge()
            self._jetons = min(self.rafale, self._jetons + (now - self._t) * self.par_minute / 60)
            self._t = now
            if self.appels >= self.max_appels:
                return f"plafond de {self.max_appels} appels atteint"
            if self.max_tokens is not None and self.tokens >= self.max_tokens:
                return f"plafond de {self.max_tokens} tokens atteint"
            if self._jetons < 1:
                return "débit trop élevé"
            self._jetons -= 1
            self.appels += 1
            return None

    def compter_tokens(self, n: int):
        with self._verrou:
            self.tokens += n


# ================= Validation =================
def preparer_payload(body: dict, modele: str) -> dict:
    """Ne garde que questions + state, et impose le modèle (le client ne le choisit pas)."""
    qs = body.get("questions")
    if not isinstance(qs, dict) or not 1 <= len(qs) <= MAX_QUESTIONS:
        raise ValueError(f"questions : 1 à {MAX_QUESTIONS} attendues")
    for k, q in qs.items():
        if not isinstance(q, dict) or q.get("type") not in TYPES_QUESTION:
            raise ValueError(f"question {k!r} invalide")
    state = body.get("state", {})
    if not isinstance(state, dict):
        raise ValueError("state doit être un objet")
    return {"model": modele, "questions": qs, "state": state}


# ================= Appel réel =================
def appeler(payload: dict, cle: str, *, ouvrir=urllib.request.urlopen, horloge=time.monotonic,
            dormir=time.sleep, delai_total: float = DELAI_TOTAL_S, essais: int = ESSAIS) -> dict:
    """Appel JEV avec retries 429/5xx, sans jamais dépasser delai_total au total."""
    data = json.dumps(payload).encode()
    fin = horloge() + delai_total
    erreur = "délai dépassé"
    for i in range(essais):
        reste = fin - horloge()
        if reste <= 0.5:
            break
        req = urllib.request.Request(API, data=data, method="POST", headers={
            "Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
        try:
            with ouvrir(req, timeout=reste) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:   # le détail brut de l'API n'est jamais renvoyé
            erreur = f"HTTP {e.code}"
            if e.code not in CODES_REESSAI:
                break
        except (OSError, ValueError) as e:     # timeout, réseau, réponse non JSON
            erreur = type(e).__name__
        attente = 0.5 * 2 ** i
        if i == essais - 1 or fin - horloge() < attente + 1:
            break
        dormir(attente)
    return {"error": erreur}


# ================= Journal des appels =================
class JournalAppels:
    """Une ligne JSON par appel : version servie, tokens, latence. Jamais la clé ni les questions."""

    def __init__(self, chemin: Path):
        self.chemin, self._verrou = chemin, threading.Lock()

    def ecrire(self, **ligne):
        ligne = {"date": datetime.now().isoformat(timespec="seconds"), **ligne}
        with self._verrou, self.chemin.open("a") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


# ================= Client =================
@dataclass
class ClientJEV:
    cle: str | None
    fake: bool
    budget: Budget
    journal: JournalAppels
    modele: str = MODELE_JEV
    ouvrir: Callable = urllib.request.urlopen

    def traiter(self, body: dict) -> tuple[int, dict]:
        """Requête du navigateur → (code HTTP, réponse JSON)."""
        try:
            payload = preparer_payload(body, self.modele)
        except ValueError as e:
            return 400, {"error": "requête invalide", "detail": str(e)}
        if not self.fake and not self.cle:
            return 503, {"error": "pas de clé"}
        if (raison := self.budget.reserver()) is not None:
            print(f"⛔ budget JEV : {raison}")
            return 429, {"error": "budget", "detail": raison}
        t0 = time.perf_counter()
        rep = jev_simule(payload) if self.fake else appeler(payload, self.cle, ouvrir=self.ouvrir)
        latence = round((time.perf_counter() - t0) * 1000)
        tokens = (rep.get("usage") or {}).get("input_tokens") or 0
        self.budget.compter_tokens(int(tokens))
        self.journal.ecrire(modele_demande=payload["model"], modele_servi=rep.get("model"),
                            questions=len(payload["questions"]), tokens=tokens, latence_ms=latence,
                            statut=rep.get("error", "ok"), appels_session=self.budget.appels)
        rep["latence_ms"] = latence
        return (502 if "error" in rep else 200), rep
