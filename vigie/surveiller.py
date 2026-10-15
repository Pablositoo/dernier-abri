"""
Surveillance en continu de sources réelles — réponses informatives uniquement (phase 7).

    python3 -m vigie.surveiller --demo                 # faux journal sshd : bruit normal puis force brute (rien de réel)
    python3 -m vigie.surveiller --mac                  # vrai journal macOS (sudo, sshd) : 3 mauvais mots de passe sudo = alerte
    python3 -m vigie.surveiller --fichier /chemin/auth.log
    python3 -m vigie.surveiller --reseau               # pics de débit par interface
    options : --notif-mac  --webhook (URL dans .env : VIGIE_WEBHOOK_URL)  --jev (avis indicatif, coûte des appels)
              --duree 60 (s, 0 = sans fin)  --donnees DOSSIER

Les alertes vont dans <donnees>/vigie_alertes.jsonl et les preuves dans <donnees>/alertes/.
"""
from __future__ import annotations

import argparse
import random
import threading
import time
from pathlib import Path

from .repondeurs import Console, Enregistrement, JournalAlertes, NotificationMac, Webhook, url_webhook
from .sources import SourceCommande, SourceFichier, SourceReseau, commande_journal_mac
from .surveillance import Surveillance

RACINE = Path(__file__).resolve().parent.parent


# ================= Démo : un faux journal sshd (adresses IP réservées à la documentation) =================
def scenario_demo(graine: int = 7) -> list[tuple[float, str]]:
    """→ [(t, ligne)] : 40 s de bruit normal (échecs isolés d'IP différentes, connexions réussies),
    puis 203.0.113.7 tente 7 mots de passe en 14 s et finit par entrer."""
    rng, lignes = random.Random(graine), []
    for i in range(10):
        t = 2 + i * 4 + rng.random()
        if i % 3 == 0:
            lignes.append((t, f"sshd[{1000 + i}]: Accepted publickey for pablo from 192.0.2.{10 + i} port 52{i:03d} ssh2"))
        else:
            lignes.append((t, f"sshd[{1000 + i}]: Failed password for pablo from 198.51.100.{rng.randint(2, 250)} port 4{i:04d} ssh2"))
    for i, user in enumerate(["admin", "root", "root", "oracle", "pi", "admin", "root"]):
        lignes.append((44 + 2 * i, f"sshd[2{i:03d}]: Failed password for invalid user {user} from 203.0.113.7 port 6{i:04d} ssh2"))
    lignes.append((60, "sshd[2999]: Accepted password for root from 203.0.113.7 port 60999 ssh2"))
    return sorted(lignes)


def ecrire_demo(chemin: Path, vitesse: float, depart: float):
    chemin.write_text("")
    for t, l in scenario_demo():
        attente = depart + t / vitesse - time.monotonic()
        if attente > 0:
            time.sleep(attente)
        with chemin.open("a", encoding="utf-8") as f:
            f.write(l + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vigie : surveillance de sources réelles, alertes uniquement")
    g = ap.add_argument_group("sources")
    g.add_argument("--demo", action="store_true")
    g.add_argument("--mac", action="store_true", help="journal unifié macOS (sudo, sshd) via `log stream`")
    g.add_argument("--fichier", type=Path)
    g.add_argument("--reseau", action="store_true")
    r = ap.add_argument_group("réponses (toutes informatives)")
    r.add_argument("--notif-mac", action="store_true")
    r.add_argument("--webhook", action="store_true", help="envoie aussi les alertes au webhook de .env")
    r.add_argument("--jev", action="store_true", help="ajoute l'avis de JEV à chaque alerte (1 appel par alerte)")
    ap.add_argument("--duree", type=float, default=0)
    ap.add_argument("--intervalle", type=float, default=1.0)
    ap.add_argument("--vitesse", type=float, default=4.0, help="démo : accélération du temps")
    ap.add_argument("--donnees", type=Path, default=RACINE / "donnees_vigie")
    a = ap.parse_args(argv)

    a.donnees.mkdir(parents=True, exist_ok=True)
    repondeurs = [Console(), JournalAlertes(a.donnees / "vigie_alertes.jsonl"), Enregistrement(a.donnees / "alertes")]
    if a.notif_mac:
        repondeurs.append(NotificationMac())
    if a.webhook:
        url = url_webhook(RACINE)
        if not url:
            raise SystemExit("--webhook : ajoute VIGIE_WEBHOOK_URL=... dans .env")
        repondeurs.append(Webhook(url))
    client_jev = None
    if a.jev:
        from server.app import charger_cle
        from server.jev_client import Budget, ClientJEV, JournalAppels
        client_jev = ClientJEV(cle=charger_cle(), fake=False, budget=Budget(max_appels=50),
                               journal=JournalAppels(a.donnees / "jev_appels.jsonl")).traiter

    sources, vitesse, depart = [], 1.0, time.monotonic()
    if a.demo:
        vitesse, journal = a.vitesse, a.donnees / "auth_demo.log"
        journal.write_text("")
        sources.append(SourceFichier(journal, nom="demo:sshd"))
        threading.Thread(target=ecrire_demo, args=(journal, vitesse, depart), daemon=True).start()
        a.duree = a.duree or 70 / vitesse
    if a.mac:
        sources.append(SourceCommande(commande_journal_mac(), nom="mac:auth").demarrer())
    if a.fichier:
        sources.append(SourceFichier(a.fichier))
    if a.reseau:
        sources.append(SourceReseau())
    if not sources:
        ap.error("au moins une source : --demo, --mac, --fichier ou --reseau")

    noyaux = [(s, Surveillance(s, repondeurs, client_jev=client_jev)) for s in sources]
    print(f"👁  Vigie : {', '.join(s.nom for s in sources)} → {', '.join(r.nom for r in repondeurs)} "
          f"(seuil L ≥ {noyaux[0][1].params.seuil:.2f}) · Ctrl-C pour arrêter")
    try:
        while not a.duree or time.monotonic() - depart < a.duree:
            time.sleep(a.intervalle / (vitesse if a.demo else 1))
            t = (time.monotonic() - depart) * vitesse
            for s, n in noyaux:
                n.traiter(s.observations(t), t)
    except KeyboardInterrupt:
        pass
    finally:
        for s in sources:
            getattr(s, "arreter", lambda: None)()
    total = sum(len(n.alertes) for _, n in noyaux)
    print(f"Fin : {total} alerte(s) · journal {a.donnees / 'vigie_alertes.jsonl'}")


if __name__ == "__main__":
    main()
