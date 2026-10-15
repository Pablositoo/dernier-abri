"""
Pont local entre le jeu 3D (navigateur) et l'API JEV.

Pourquoi un serveur ? La clé API ne doit JAMAIS être dans le code du navigateur
(n'importe qui pourrait la lire). Le navigateur parle à ce serveur, qui ajoute la clé.

    python server.py          -> ouvre http://localhost:8000
    python server.py --fake   -> sans API (JEV simulé), pour tester
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
API = "https://api.typesafe.ai/v1/systemone"
LOGS = {"/log": ROOT / "resultats_parties.csv", "/decision": ROOT / "decisions_jev.csv"}


def charger_cle() -> str | None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.getenv("TYPESAFE_API_KEY")


def jev(payload: dict, cle: str, essais: int = 3) -> dict:
    """Appel JEV avec retries sur rate limit / erreurs serveur."""
    data = json.dumps(payload).encode()
    for i in range(essais):
        req = urllib.request.Request(API, data=data, method="POST", headers={
            "Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < essais - 1:
                time.sleep(0.5 * 2 ** i)
                continue
            return {"error": f"HTTP {e.code}", "detail": e.read().decode()[:300]}
        except Exception as e:  # timeout, réseau
            if i < essais - 1:
                time.sleep(0.5 * 2 ** i)
                continue
            return {"error": type(e).__name__}
    return {"error": "inconnu"}


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


def jev_simule(payload: dict) -> dict:
    """Faux JEV pour tester sans API : lit les mots-clés des descriptions."""
    qs = payload["questions"]
    if all(q.get("type") == "noul" for q in qs.values()):
        time.sleep(random.uniform(0.15, 0.35))
        return {"model": "jev-simule", "usage": {"input_tokens": 0},
                "answers": {k: {"type": "noul", "noul": noul_simule(q["instructions"])} for k, q in qs.items()}}
    crit = payload["questions"]["action"]["criteria"]
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
        if "chance " in desc:  # on tire plus volontiers quand la cible est proche
            s *= 0.4 + 0.6 * float(desc.split("chance ")[-1].split(" %")[0]) / 100
        scores[k] = s
    tot = sum(scores.values())
    probas = {k: v / tot for k, v in scores.items()}
    time.sleep(random.uniform(0.15, 0.35))
    choix = max(probas, key=probas.get)
    return {"model": "jev-simule", "answers": {"action": {"type": "choice", "choice": choix,
            "confidence": probas[choix], "probabilities": probas}}, "usage": {"input_tokens": 0}}


class Handler(SimpleHTTPRequestHandler):
    cle: str | None = None
    fake: bool = False

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def log_message(self, *_):  # terminal silencieux
        pass

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):  # onglet fermé pendant la réponse
            pass

    def do_GET(self):
        if self.path == "/config":
            return self._json(200, {"jev": bool(self.cle) or self.fake, "fake": self.fake})
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/jev":
            t0 = time.perf_counter()
            rep = jev_simule(body) if self.fake else jev(body, self.cle) if self.cle else {"error": "pas de clé"}
            rep["latence_ms"] = round((time.perf_counter() - t0) * 1000)
            return self._json(200, rep)
        if self.path in LOGS:  # /log : une ligne par partie, /decision : une ligne par cible
            fichier = LOGS[self.path]
            champs = ["date", *body.keys()]
            if fichier.exists():  # colonnes changées (nouvelle version) -> on archive l'ancien fichier
                with fichier.open() as f:
                    if next(csv.reader(f), []) != champs:
                        fichier.rename(fichier.with_name(fichier.stem + f"_ancien_{int(time.time())}.csv"))
            neuf = not fichier.exists()
            with fichier.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["date", *body.keys()])
                if neuf:
                    w.writeheader()
                w.writerow({"date": datetime.now().isoformat(timespec="seconds"), **body})
            if self.path == "/log":
                print("Partie enregistrée :", body)
            return self._json(200, {"ok": True})
        self._json(404, {"error": "inconnu"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    Handler.cle, Handler.fake = charger_cle(), args.fake
    if not Handler.cle and not args.fake:
        print("⚠️  Pas de clé dans .env : seuls les modes Bot et Manuel marcheront (ou lance avec --fake).")
    url = f"http://localhost:{args.port}"
    print(f"🧟 Jeu prêt sur {url}   (Ctrl+C pour arrêter)")
    if not args.no_browser:
        webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
