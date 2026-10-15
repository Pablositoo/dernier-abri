"""
Étude du bruit de JEV : la même question donne-t-elle toujours la même réponse ?

Deux sources possibles de variation, séparées par 2 conditions :
  - « mêmes lots »  : exactement les requêtes du cache (mêmes fiches regroupées ensemble), répétées → hasard pur ;
  - « lots mélangés » : mêmes questions, fiches regroupées au hasard par 5 (comme en jeu) → hasard + contexte.

    python3 -m analyse.bruit_jev --dry-run                  # nombre d'appels, rien n'est envoyé
    python3 -m analyse.bruit_jev --memes 5 --melanges 3     # ≈ 80 appels réels (≈ 0,004 €), reprend où il s'est arrêté
    python3 -m analyse.bruit_jev --analyser                 # sans appel : statistiques + conséquences pour la sécurité

Les réponses ne vont PAS dans le cache (la référence de calibration reste intacte) ; brut dans bench_resultats/.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

from analyse.calibration import PIRE_CINEMATIQUE, SEUIL_A, logit

ROOT = Path(__file__).resolve().parent.parent
SORTIE = ROOT / "bench_resultats" / "bruit_jev.json"
PAR_LOT = 5          # cibles par requête, comme en jeu (MAX_CIBLES)


def fiches(requetes: list[dict]) -> list[tuple[dict, str, dict, dict]]:
    """→ [(state, id de fiche, question z, question h)] : z et h d'une fiche restent toujours ensemble."""
    out = []
    for r in requetes:
        for nom, q in r["questions"].items():
            if nom.startswith("z_"):
                out.append((r["state"], nom[2:], q, r["questions"]["h_" + nom[2:]]))
    return out


def lots_melanges(requetes: list[dict], graine: int) -> list[dict]:
    rng, lots = random.Random(graine), []
    par_langue: dict[str, list] = {}
    for f in fiches(requetes):
        par_langue.setdefault(f[0]["langue"], []).append(f)
    for fs in par_langue.values():
        rng.shuffle(fs)
        for i in range(0, len(fs), PAR_LOT):
            lot = fs[i:i + PAR_LOT]
            lots.append({"state": lot[0][0], "questions": {k: v for _, id_, z, h in lot for k, v in (("z_" + id_, z), ("h_" + id_, h))}})
    return lots


def plan(requetes: list[dict], memes: int, melanges: int) -> list[tuple[str, int, int, dict]]:
    """→ [(condition, répétition, n° de requête, requête)] dans un ordre fixe (permet de reprendre)."""
    p = [("memes_lots", r, i, req) for r in range(memes) for i, req in enumerate(requetes)]
    p += [("lots_melanges", r, i, req) for r in range(melanges) for i, req in enumerate(lots_melanges(requetes, 1000 + r))]
    return p


def collecter(args):
    from server.app import charger_cle
    from server.jev_client import Budget, JournalAppels, appeler, preparer_payload
    from server.remplir_cache import requetes_possibles

    taches = plan(requetes_possibles(), args.memes, args.melanges)
    donnees = json.loads(SORTIE.read_text()) if SORTIE.exists() else {"modele": args.modele, "reponses": []}
    faites = {(r["condition"], r["repetition"], r["requete"]) for r in donnees["reponses"]}
    reste = [t for t in taches if t[:3] not in faites]
    print(f"{len(taches)} requêtes prévues · {len(taches) - len(reste)} déjà faites · {len(reste)} à envoyer (modèle {args.modele})")
    if args.dry_run or not reste:
        return
    cle = charger_cle()
    if not cle:
        raise SystemExit("Pas de clé TYPESAFE_API_KEY dans .env")
    budget, journal = Budget(max_appels=args.max_appels), JournalAppels(ROOT / "jev_appels.jsonl")
    for n, (cond, rep, i, req) in enumerate(reste, 1):
        if (raison := budget.reserver()) is not None:
            print(f"arrêt : {raison} (relancer pour reprendre)")
            break
        r = appeler(preparer_payload(req, args.modele), cle)
        tokens = (r.get("usage") or {}).get("input_tokens") or 0
        budget.compter_tokens(int(tokens))
        journal.ecrire(modele_demande=args.modele, modele_servi=r.get("model"), questions=len(req["questions"]), cache=0,
                       tokens=tokens, statut="bruit " + r.get("error", "ok"), appels_session=budget.appels)
        if "error" in r:
            print(f"  {n}/{len(reste)} erreur {r['error']} (relancer pour reprendre)")
            continue
        donnees["reponses"].append({"condition": cond, "repetition": rep, "requete": i, "langue": req["state"]["langue"],
                                    "modele_servi": r.get("model"),
                                    "answers": {k: v.get("noul") for k, v in (r.get("answers") or {}).items()}})
        SORTIE.write_text(json.dumps(donnees, ensure_ascii=False))
        if n % 10 == 0 or n == len(reste):
            print(f"  {n}/{len(reste)} · {budget.appels} appels · {budget.tokens} tokens")


# ================= Analyse =================
def tableau(donnees: dict) -> dict:
    """→ {(langue, fiche): {condition: [pZ, …]}} avec pZ = (z + 1 − h) / 2 et la même cohérence que le jeu."""
    t: dict = {}
    for r in donnees["reponses"]:
        a = r["answers"]
        for nom, z in a.items():
            if nom.startswith("z_") and z is not None and a.get("h_" + nom[2:]) is not None:
                h = a["h_" + nom[2:]]
                t.setdefault((r["langue"], nom[2:]), {}).setdefault(r["condition"], []).append(
                    ((z + 1 - h) / 2, abs(z - (1 - h)), z, h))
    return t


def main():
    ap = argparse.ArgumentParser(description="Étude du bruit de JEV")
    ap.add_argument("--memes", type=int, default=5)
    ap.add_argument("--melanges", type=int, default=3)
    ap.add_argument("--modele", default="jev-1.13.0")
    ap.add_argument("--max-appels", type=int, default=90)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--analyser", action="store_true")
    args = ap.parse_args()
    if not args.analyser:
        collecter(args)
    if SORTIE.exists() and not args.dry_run:
        rapport(json.loads(SORTIE.read_text()))


def rapport(donnees: dict):
    import re
    conf = json.loads(re.search(r"=\s*(\{.*\});", (ROOT / "web/js/analysis/calibration_jev.js").read_text(), re.S).group(1))
    a, b, lpi = conf["a"], conf["b"], float(logit(np.array(conf["tauxZombies"])))
    preuve = {"brut": lambda p: logit(p), "v5": lambda p: a * logit(p) + b - lpi}

    t = tableau(donnees)
    servis = {r["modele_servi"] for r in donnees["reponses"]}
    print(f"\n{len(donnees['reponses'])} requêtes · modèle(s) servi(s) {servis} · {len(t)} fiches")
    for cond in ("memes_lots", "lots_melanges"):
        sd_q = [np.std([x[k] for x in v[cond]]) for v in t.values() if len(v.get(cond, [])) > 1 for k in (2, 3)]
        sd_p = [np.std([x[0] for x in v[cond]]) for v in t.values() if len(v.get(cond, [])) > 1]
        et_q = [max(x[k] for x in v[cond]) - min(x[k] for x in v[cond]) for v in t.values() if len(v.get(cond, [])) > 1 for k in (2, 3)]
        if sd_q:
            print(f"  {cond:14} écart-type par question : moyen {np.mean(sd_q):.3f}, max {np.max(sd_q):.3f} · "
                  f"étendue max {np.max(et_q):.2f} · écart-type de pZ : moyen {np.mean(sd_p):.3f}, max {np.max(sd_p):.3f}")

    # Sécurité : pire tirage observé de chaque fiche (humains : pZ max ; zombies : pZ min), lectures cohérentes seulement
    print("\nPire tirage observé par fiche après réaction (toutes conditions) :")
    print(f"  {'fiche':28}{'pZ min–max':>13}{'incoh max':>10}{'marge brut':>12}{'marge v5':>10}")
    pires = {"brut": (np.inf, ""), "v5": (np.inf, "")}
    zombies_lents = {"brut": 0, "v5": 0}
    for (lg, id_), conds in sorted(t.items()):
        if id_.endswith("_0"):
            continue
        tirages = [x for v in conds.values() for x in v]
        coherents = [x for x in tirages if x[1] <= conf["incohMax"]]
        humain = "humain" in id_ and "zombie" not in id_
        ligne = f"  {lg + ' ' + id_:28}{min(x[0] for x in tirages):7.3f}–{max(x[0] for x in tirages):.3f}{max(x[1] for x in tirages):10.2f}"
        if humain and coherents:
            pmax = max(x[0] for x in coherents)
            for k, f in preuve.items():
                m = float(SEUIL_A - (f(np.array(pmax)) + PIRE_CINEMATIQUE))
                ligne += f"{m:{12 if k == 'brut' else 10}.2f}"
                if m < pires[k][0]:
                    pires[k] = (m, f"{lg} {id_} (p = {pmax:.3f})")
            print(ligne)
        elif not humain:
            for k, f in preuve.items():   # zombie cohérent le plus bas : encore confirmé en ≤ 2 sommations ?
                if any(float(f(np.array(x[0]))) + PIRE_CINEMATIQUE < SEUIL_A for x in coherents):
                    zombies_lents[k] += 1
    for k, (m, fiche) in pires.items():
        print(f"\n{k:5}: marge pire cas sur le pire tirage = {m:.2f} ({fiche}) → {'SÛR' if m > 0 else '⚠ UN HUMAIN POURRAIT ÊTRE ABATTU'}"
              f" · fiches zombies parfois non confirmées en 2 sommations : {zombies_lents[k]}")


if __name__ == "__main__":
    main()
