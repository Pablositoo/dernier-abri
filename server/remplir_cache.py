"""
Remplit cache_jev.json avec les vraies réponses JEV de toutes les fiches possibles (≈ 80 questions, ≈ 8 appels).
Une seule fois par version du modèle ; ensuite le jeu et le benchmark n'appellent plus JEV pour ces questions.

    python3 -m server.remplir_cache --dry-run     # combien d'appels, sans rien envoyer
    python3 -m server.remplir_cache               # vrais appels (plafonnés par --max-appels)
"""
from __future__ import annotations

import argparse
import json
import subprocess

from .app import ROOT, charger_cle
from .cache_jev import CacheJEV, cle
from .jev_client import MODELE_JEV, Budget, ClientJEV, JournalAppels


def requetes_possibles() -> list[dict]:
    """La liste vient du code du jeu lui-même (mêmes textes que le navigateur)."""
    sortie = subprocess.run(["node", str(ROOT / "tests" / "bench.mjs"), "--lister-questions"],
                            capture_output=True, text=True, check=True).stdout
    return json.loads(sortie)


def main():
    ap = argparse.ArgumentParser(description="Remplit le cache des réponses JEV")
    ap.add_argument("--dry-run", action="store_true", help="affiche ce qui serait envoyé, sans appel")
    ap.add_argument("--modele", default=MODELE_JEV)
    ap.add_argument("--max-appels", type=int, default=20)
    args = ap.parse_args()

    cache = CacheJEV(ROOT / "cache_jev.json")
    requetes = requetes_possibles()
    manque = lambda r: [q for q in r["questions"].values() if cle(args.modele, r["state"], q) not in cache.entrees]
    a_faire = [r for r in requetes if manque(r)]
    n_q = sum(len(manque(r)) for r in a_faire)
    car = sum(len(json.dumps(r, ensure_ascii=False)) for r in a_faire)
    print(f"{len(requetes)} requêtes possibles · {len(a_faire)} à envoyer · {n_q} questions manquantes · "
          f"≈ {car // 4} tokens estimés (modèle {args.modele})")
    if args.dry_run or not a_faire:
        return

    cle_api = charger_cle()
    if not cle_api:
        raise SystemExit("Pas de clé TYPESAFE_API_KEY dans .env")
    budget = Budget(max_appels=args.max_appels)
    client = ClientJEV(cle=cle_api, fake=False, budget=budget, modele=args.modele, cache=cache,
                       journal=JournalAppels(ROOT / "jev_appels.jsonl"))
    for i, r in enumerate(a_faire, 1):
        code, rep = client.traiter(r)
        tokens = (rep.get("usage") or {}).get("input_tokens")
        print(f"  {i}/{len(a_faire)} · HTTP {code} · servi par {rep.get('model')} · {tokens} tokens · "
              f"{rep.get('latence_ms')} ms {rep.get('error', '')}")
        if code != 200:
            raise SystemExit("Arrêt : réponse en erreur (voir jev_appels.jsonl). Rien d'invalide n'a été mis en cache.")
    print(f"✅ cache : {len(cache.entrees)} réponses · {budget.appels} appels · {budget.tokens} tokens consommés")


if __name__ == "__main__":
    main()
