"""Faux JEV pour tester sans API ni coût (python3 server.py --fake) : lit les mots-clés des descriptions."""
from __future__ import annotations

import random
import re
import time

# mots-clés FR + EN (le jeu est bilingue)
ZOMBIE_MOTS = ("grogne", "gémissement", "mâchoire", "ne répond pas", "sans parler",
               "grunts", "groaning", "jaw", "doesn't respond", "without speaking")
HUMAIN_MOTS = ("aidez-moi", "ne tirez pas", "main ouverte", "prénom", "signes",
               "help me", "don't shoot", "open hand", "by name", "waves")
REAC_HUMAIN = ("lève", "vivant", "raises", "alive")
REAC_ZOMBIE = ("ne réagit pas", "sans s'arrêter", "does not react", "without stopping")


def noul_simule(txt: str) -> float:
    fiche = txt.split(" Cette cible")[0].split(" This target")[0]   # on ignore la question elle-même
    reaction = fiche.split("Réaction à la sommation :")[-1].split("Reaction to the warning:")[-1]
    if any(w in reaction for w in REAC_HUMAIN):
        pz = 0.03
    elif any(w in reaction for w in REAC_ZOMBIE):
        pz = 0.96
    else:
        z = sum(w in fiche for w in ZOMBIE_MOTS); h = sum(w in fiche for w in HUMAIN_MOTS)
        pz = 0.5 if z == h else (0.85 if z > h else 0.15)
    pz = min(0.99, max(0.01, pz + random.uniform(-0.05, 0.05)))
    return pz if ("est un zombie" in txt or "is a zombie" in txt) else 1 - pz


def jev_simule(payload: dict, attente: bool = True) -> dict:
    qs = payload["questions"]
    if attente:
        time.sleep(random.uniform(0.15, 0.35))
    if all(q.get("type") == "noul" for q in qs.values()):
        return {"model": "jev-simule", "usage": {"input_tokens": 0},
                "answers": {k: {"type": "noul", "noul": noul_simule(q.get("instructions", ""))} for k, q in qs.items()}}
    crit = next(q for q in qs.values() if q.get("type") == "choice").get("criteria", {})
    scores = {}
    for k, desc in crit.items():
        if k == "attendre":
            scores[k] = 0.3
            continue
        s = 0.2
        if any(w in desc for w in ZOMBIE_MOTS):
            s = 0.9
        if any(w in desc for w in HUMAIN_MOTS):
            s = 0.02
        m = re.search(r"(\d+) %", desc)   # FR « chance 70 % », EN « 70 % chance to hit »
        if m:  # on tire plus volontiers quand la cible est proche
            s *= 0.4 + 0.6 * int(m.group(1)) / 100
        scores[k] = s
    tot = sum(scores.values()) or 1
    probas = {k: v / tot for k, v in scores.items()}
    choix = max(probas, key=probas.get)
    return {"model": "jev-simule", "answers": {"action": {"type": "choice", "choice": choix,
            "confidence": probas[choix], "probabilities": probas}}, "usage": {"input_tokens": 0}}
