"""
Serveur HTTP local : fichiers statiques de web/ + POST /jev, /log, /decision.

Pourquoi un serveur ? La clé API ne doit JAMAIS être dans le code du navigateur.
Le navigateur parle à ce serveur, qui ajoute la clé.

Protections (phase 0) :
  - Host = localhost/127.0.0.1 sur toutes les requêtes (DNS rebinding)
  - POST : Origin locale + Content-Type JSON + jeton de session injecté dans la page (CSRF)
  - taille max des requêtes, JSON validé, budget d'appels JEV, CSV en liste blanche
  - WebSocket /vigie (phase 6, le jeu piloté par le noyau) : Host local, Origin locale si présente,
    jeton de session dans le 1er message ; JEV est appelé côté serveur (la clé ne sort jamais d'ici)
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import webbrowser
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .cache_jev import CacheJEV
from .jev_client import MODELE_JEV, Budget, ClientJEV, JournalAppels
from .storage import COLONNES, JournalCSV
from .websocket import ConnexionWS, FermetureWS, cle_acceptation

ROOT = Path(__file__).resolve().parent.parent
TAILLE_MAX = 64 * 1024
ENTETE_JETON = "X-Jeton-Session"
MARQUEUR_JETON = "__JETON_SESSION__"


def charger_cle(dossier: Path = ROOT) -> str | None:
    env = dossier / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.getenv("TYPESAFE_API_KEY")


@dataclass
class Contexte:
    jev: ClientJEV
    csv: JournalCSV
    jeton: str
    web: Path
    donnees: Path = ROOT
    hotes: frozenset[str] = frozenset()
    origines: frozenset[str] = frozenset()

    def autoriser_port(self, port: int):
        self.hotes = frozenset({f"localhost:{port}", f"127.0.0.1:{port}"})
        self.origines = frozenset(f"http://{h}" for h in self.hotes)


class Handler(SimpleHTTPRequestHandler):
    server: ThreadingHTTPServer

    def __init__(self, requete, adresse, serveur):
        super().__init__(requete, adresse, serveur, directory=str(serveur.ctx.web))

    @property
    def ctx(self) -> Contexte:
        return self.server.ctx

    def log_message(self, *_):  # terminal silencieux
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):  # onglet fermé pendant la réponse
            pass

    def _refuser(self, code: int, raison: str):
        print(f"⛔ {self.command} {urlsplit(self.path).path} refusé ({code}) : {raison}")
        self._json(code, {"error": raison})

    def _hote_ok(self) -> bool:
        return self.headers.get("Host", "") in self.ctx.hotes

    # ---------- GET ----------
    def do_GET(self):
        if not self._hote_ok():
            return self._refuser(403, "hôte non autorisé")
        chemin = urlsplit(self.path).path
        if chemin == "/config":
            return self._json(200, {"jev": bool(self.ctx.jev.cle) or self.ctx.jev.fake, "fake": self.ctx.jev.fake})
        if chemin in ("/", "/index.html"):
            return self._page()
        if chemin == "/vigie":
            return self._vigie()
        return super().do_GET()

    def do_HEAD(self):
        if not self._hote_ok():
            return self._refuser(403, "hôte non autorisé")
        return super().do_HEAD()

    def _page(self):
        """index.html avec le jeton de session injecté (un autre site ne peut pas lire cette page)."""
        html = (self.ctx.web / "index.html").read_text(encoding="utf-8").replace(MARQUEUR_JETON, self.ctx.jeton, 1)
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------- WebSocket /vigie : le noyau Python décide, le jeu exécute ----------
    def _vigie(self):
        from vigie.jeu import SessionJeu
        from vigie.noyau import JournalRepondeur

        origine = self.headers.get("Origin")
        if origine is not None and origine not in self.ctx.origines:
            return self._refuser(403, "origine non autorisée")
        cle_ws = self.headers.get("Sec-WebSocket-Key")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not cle_ws or self.headers.get("Sec-WebSocket-Version") != "13":
            return self._refuser(400, "WebSocket attendu")
        self.protocol_version = "HTTP/1.1"
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", cle_acceptation(cle_ws))
        self.end_headers()
        self.close_connection = True
        ws = ConnexionWS(self.rfile, self.wfile)
        try:
            self.connection.settimeout(5)
            bonjour = ws.recevoir()
            if bonjour.get("type") != "bonjour" or not hmac.compare_digest(str(bonjour.get("jeton", "")).encode(),
                                                                          self.ctx.jeton.encode()):
                print("⛔ /vigie refusé : jeton de session invalide")
                return ws.fermer(1008, "jeton invalide")
            # simulation (benchmark, tests) : réponses JEV livrées après une latence fixe d'horloge simulée
            sim = bonjour.get("simulation")
            latence = min(5.0, max(0.0, float(sim.get("latence", 0)))) if isinstance(sim, dict) else 0.0
            session = SessionJeu(client=self.ctx.jev.traiter, synchrone=isinstance(sim, dict), latence=latence,
                                 journal=JournalRepondeur(self.ctx.donnees / "vigie_decisions.jsonl"))
            ws.envoyer({"type": "pret", "calibration": session.calibrateur.modele if session.calibrateur else None})
            self.connection.settimeout(120)
            while True:
                msg = ws.recevoir()
                if msg.get("type") == "etat":
                    if len(msg.get("observations", [])) > 100:
                        return ws.fermer(1009, "trop d'observations")
                    ws.envoyer(session.traiter(msg))
        except FermetureWS:
            pass
        except (OSError, ValueError, KeyError, TypeError) as e:   # message mal formé, délai dépassé, onglet fermé
            print(f"⛔ /vigie fermé : {type(e).__name__}")
            ws.fermer(1003, "message invalide")

    # ---------- POST ----------
    def do_POST(self):
        chemin = urlsplit(self.path).path
        if not self._hote_ok():
            return self._refuser(403, "hôte non autorisé")
        if chemin != "/jev" and chemin not in COLONNES:
            return self._refuser(404, "inconnu")
        if self.headers.get("Origin", "") not in self.ctx.origines:
            return self._refuser(403, "origine non autorisée")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self._refuser(415, "Content-Type application/json attendu")
        if not hmac.compare_digest(self.headers.get(ENTETE_JETON, "").encode(), self.ctx.jeton.encode()):
            return self._refuser(403, "jeton de session invalide")
        longueur = self.headers.get("Content-Length")
        if longueur is None:
            return self._refuser(411, "Content-Length requis")
        try:
            n = int(longueur)
        except ValueError:
            return self._refuser(400, "Content-Length invalide")
        if n < 0:
            return self._refuser(400, "Content-Length invalide")
        if n > TAILLE_MAX:
            self.close_connection = True   # on ne lit pas le corps
            return self._refuser(413, f"requête > {TAILLE_MAX // 1024} Ko")
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return self._refuser(400, "JSON invalide")
        if not isinstance(body, dict):
            return self._refuser(400, "objet JSON attendu")

        if chemin == "/jev":
            code, rep = self.ctx.jev.traiter(body)
            return self._json(code, rep)
        # /log : une ligne par partie, /decision : une ligne par cible
        self.ctx.csv.ecrire(chemin, body)
        if chemin == "/log":
            print("Partie enregistrée :", {k: body.get(k) for k in ("mode", "score", "humains_tues", "morsures")})
        return self._json(200, {"ok": True})


def creer_serveur(port: int = 8000, *, cle: str | None, fake: bool, budget: Budget | None = None,
                  modele: str = MODELE_JEV, dossier_donnees: Path = ROOT, web: Path = ROOT / "web",
                  ouvrir=None, cache: CacheJEV | None = None) -> ThreadingHTTPServer:
    """Serveur prêt à servir (port=0 : port libre, pour les tests)."""
    jev = ClientJEV(cle=cle, fake=fake, budget=budget or Budget(), modele=modele, cache=cache,
                    journal=JournalAppels(dossier_donnees / "jev_appels.jsonl"))
    if ouvrir is not None:
        jev.ouvrir = ouvrir
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.ctx = Contexte(jev=jev, csv=JournalCSV(dossier_donnees), jeton=secrets.token_urlsafe(32), web=web,
                       donnees=dossier_donnees)
    srv.ctx.autoriser_port(srv.server_address[1])
    return srv


def main():
    ap = argparse.ArgumentParser(description="Dernier Abri : proxy local JEV")
    ap.add_argument("--fake", action="store_true", help="JEV simulé, sans API ni coût")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--modele", default=MODELE_JEV, help=f"version JEV figée (défaut {MODELE_JEV})")
    ap.add_argument("--par-minute", type=float, default=300, help="débit max d'appels JEV par minute")
    ap.add_argument("--max-appels", type=int, default=1000, help="plafond d'appels JEV par lancement")
    ap.add_argument("--max-tokens", type=int, default=None, help="plafond de tokens par lancement (aucun par défaut)")
    ap.add_argument("--sans-cache", action="store_true", help="interroge JEV à chaque fois (pas de cache_jev.json)")
    ap.add_argument("--donnees", type=Path, default=None,
                    help="dossier des CSV et du journal (défaut : le projet ; donnees_fake/ en --fake)")
    args = ap.parse_args()
    # les parties simulées ne doivent pas se mélanger aux vraies données (calibration)
    donnees = args.donnees or (ROOT / "donnees_fake" if args.fake else ROOT)
    donnees.mkdir(parents=True, exist_ok=True)
    cle = charger_cle()
    if not cle and not args.fake:
        print("⚠️  Pas de clé dans .env : seuls les modes Bot et Manuel marcheront (ou lance avec --fake).")
    budget = Budget(par_minute=args.par_minute, max_appels=args.max_appels, max_tokens=args.max_tokens)
    # cache seulement pour le vrai JEV (le faux JEV est gratuit et volontairement bruité)
    cache = None if args.fake or args.sans_cache else CacheJEV(ROOT / "cache_jev.json")
    srv = creer_serveur(args.port, cle=cle, fake=args.fake, budget=budget, modele=args.modele, dossier_donnees=donnees, cache=cache)
    url = f"http://localhost:{args.port}"
    print(f"🧟 Jeu prêt sur {url}   (Ctrl+C pour arrêter)")
    print(f"   JEV : {'simulé' if args.fake else args.modele} · budget {args.par_minute:g}/min, "
          f"{args.max_appels} appels" + (f", {args.max_tokens} tokens" if args.max_tokens else ""))
    print(f"   Journaux : {donnees}" + (f" · cache JEV : {len(cache.entrees)} réponses" if cache else ""))
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print(f"\nArrêt. Appels JEV : {budget.appels}, tokens : {budget.tokens}")
