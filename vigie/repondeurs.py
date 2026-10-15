"""
Répondeurs INFORMATIFS (phase 7) : journal, enregistrement des preuves, notification macOS, webhook (Discord…).
Aucun n'agit sur le monde. Le texte des journaux peut être écrit par un attaquant : il n'est jamais interprété
(pas de mentions Discord, pas de code AppleScript construit avec lui, pas de chemin de fichier tiré de lui).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .surveillance import Alerte


class JournalAlertes:
    """Une ligne JSON par alerte."""
    nom, informatif = "journal", True

    def __init__(self, chemin: Path):
        self.chemin, self._verrou = chemin, threading.Lock()

    def alerter(self, a: Alerte):
        with self._verrou, self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": datetime.now().isoformat(timespec="seconds"), **asdict(a)}, ensure_ascii=False) + "\n")


class Enregistrement:
    """Conserve les preuves de chaque alerte (lignes brutes, calculs) dans un fichier à part : utile pour enquêter."""
    nom, informatif = "enregistrement", True

    def __init__(self, dossier: Path):
        self.dossier = dossier

    def alerter(self, a: Alerte):
        self.dossier.mkdir(parents=True, exist_ok=True)
        nom = re.sub(r"[^A-Za-z0-9_.-]", "_", a.entite)[:60]           # jamais de chemin tiré du texte observé
        f = self.dossier / f"{datetime.now():%Y%m%d-%H%M%S}_{nom}.json"
        f.write_text(json.dumps(asdict(a), ensure_ascii=False, indent=1), encoding="utf-8")


def texte_alerte(a: Alerte) -> str:
    icone = "🛑" if a.niveau == "critique" else "🚨"
    lignes = [f"{icone} Vigie : {a.niveau.upper()} ({a.source})", a.resume, *(f"• {d}" for d in a.details)]
    if a.avis_jev:
        lignes.append(f"• avis JEV (indicatif, non calibré) : {a.avis_jev}")
    lignes.append("Aucune action automatique : à vérifier par un humain.")
    return "\n".join(lignes)


class NotificationMac:
    """Notification du centre de notifications macOS. Le texte passe en ARGUMENT d'un script fixe (pas d'injection)."""
    nom, informatif = "notification macOS", True
    SCRIPT = "on run argv\ndisplay notification (item 1 of argv) with title (item 2 of argv)\nend run"

    def __init__(self, executer=subprocess.run):
        self.executer = executer

    def alerter(self, a: Alerte):
        if sys.platform != "darwin":
            return
        self.executer(["osascript", "-e", self.SCRIPT, "--", a.resume[:200], f"Vigie : {a.niveau}"],
                      capture_output=True, timeout=5)


def neutraliser(texte: str) -> str:
    """Texte observé → texte Discord inoffensif : pas de @mention, pas de bloc de code détourné."""
    return texte.replace("@", "@​").replace("```", "ʼʼʼ")


class Webhook:
    """POST JSON vers un webhook (Discord). L'URL est un secret : lue dans .env, jamais affichée ni journalisée."""
    nom, informatif = "webhook", True

    def __init__(self, url: str, ouvrir=urllib.request.urlopen, intervalle_min: float = 5.0, horloge=time.monotonic):
        if not url.startswith("https://"):
            raise ValueError("webhook : URL https:// attendue")
        self._url, self.ouvrir, self.intervalle_min, self.horloge = url, ouvrir, intervalle_min, horloge
        self._dernier = -1e9

    def __repr__(self):                       # même un print(repondeur) ne montre pas l'URL
        return "Webhook(<secret>)"

    def charge(self, a: Alerte) -> dict:
        corps = neutraliser(texte_alerte(a))
        if a.extraits:
            corps += "\n```\n" + neutraliser("\n".join(a.extraits[-6:]))[:900] + "\n```"
        return {"username": "Vigie", "content": corps[:1900], "allowed_mentions": {"parse": []}}

    def alerter(self, a: Alerte):
        if self.horloge() - self._dernier < self.intervalle_min and a.niveau != "critique":
            print("⚠ webhook : alerte non envoyée (anti-rafale), elle reste dans le journal")
            return
        self._dernier = self.horloge()
        req = urllib.request.Request(self._url, data=json.dumps(self.charge(a)).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "vigie/1.0"})
        try:
            with self.ouvrir(req, timeout=5):
                pass
        except urllib.error.HTTPError as e:   # jamais l'URL dans le message
            print(f"⚠ webhook : HTTP {e.code}")
        except OSError as e:
            print(f"⚠ webhook : {type(e).__name__}")


def url_webhook(dossier: Path) -> str | None:
    env = dossier / ".env"
    if env.exists():
        for l in env.read_text().splitlines():
            if l.startswith("VIGIE_WEBHOOK_URL="):
                return l.split("=", 1)[1].strip() or None
    return None


class Console:
    """Affichage terminal (pour la démo)."""
    nom, informatif = "console", True

    def alerter(self, a: Alerte):
        print("\n" + texte_alerte(a) + "\n")
