"""
Écriture CSV sûre : colonnes en liste blanche + échappement des formules (=, +, -, @).

Toute nouvelle colonne envoyée par le jeu doit être ajoutée ici, sinon elle est ignorée.
"""
from __future__ import annotations

import csv
import threading
import time
from datetime import datetime
from pathlib import Path

# ordre identique aux CSV existants (sinon l'ancien fichier serait archivé)
COLONNES = {
    "/log": ["mode", "langue", "seuil", "score", "zombies_tues", "humains_tues", "humains_sauves", "morsures",
             "tirs", "rates", "sommations", "tirs_bloques", "survie_s", "appels_jev", "latence_moy_ms"],
    "/decision": ["mode", "langue", "seuil", "id", "verite", "nature", "description", "reaction",
                  "p_zombie_avant_sommation", "p_zombie_final", "incoherence", "statut_jev", "issue", "distance_m"],
}
FICHIERS = {"/log": "resultats_parties.csv", "/decision": "decisions_jev.csv"}
DEBUTS_DANGEREUX = ("=", "+", "-", "@", "\t", "\r")   # interprétés comme formule par Excel / LibreOffice
LONGUEUR_MAX = 300


def nettoyer(valeur) -> str | int | float:
    if valeur is None or isinstance(valeur, (dict, list)):
        return ""
    if isinstance(valeur, bool):
        return str(valeur).lower()
    if isinstance(valeur, (int, float)):
        return valeur
    texte = str(valeur)[:LONGUEUR_MAX]
    return "'" + texte if texte.startswith(DEBUTS_DANGEREUX) else texte


class JournalCSV:
    def __init__(self, dossier: Path):
        self.dossier, self._verrou = dossier, threading.Lock()

    def ecrire(self, route: str, body: dict):
        colonnes = COLONNES[route]
        champs = ["date", *colonnes]
        fichier = self.dossier / FICHIERS[route]
        ligne = {"date": datetime.now().isoformat(timespec="seconds"),
                 **{k: nettoyer(body.get(k)) for k in colonnes}}
        with self._verrou:
            if fichier.exists():  # colonnes changées (nouvelle version) -> on archive l'ancien fichier
                with fichier.open(newline="") as f:
                    if next(csv.reader(f), []) != champs:
                        fichier.rename(fichier.with_name(fichier.stem + f"_ancien_{int(time.time())}.csv"))
            neuf = not fichier.exists()
            with fichier.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=champs)
                if neuf:
                    w.writeheader()
                w.writerow(ligne)
