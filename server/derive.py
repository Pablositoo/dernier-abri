"""
Détection de dérive de JEV par « canaris » : on repose à JEV des questions dont on connaît déjà la réponse
(cache, modèle figé) et on compare question par question. Comparaison appariée : bien plus sensible qu'une
comparaison de distributions, et sans besoin de vérité terrain (réutilisable sur des sources réelles).

    python3 -m server.derive --dry-run          # quelles questions, combien d'appels (rien n'est envoyé)
    python3 -m server.derive                    # 12 canaris = 1 appel réel ; code de sortie 1 si dérive

Contrôle passif, gratuit, à chaque appel (jev_client) : modèle servi ≠ modèle demandé ⇒ alerte, et la réponse
n'entre pas dans le cache (elle empoisonnerait la référence). Côté navigateur, la v5 désactive alors sa calibration.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field

from .cache_jev import CacheJEV, cle
from .jev_client import MAX_QUESTIONS, MODELE_JEV, Budget, JournalAppels, appeler, preparer_payload

# Seuils calés sur l'étude du bruit (analyse/bruit_jev.py, 80 appels, 15/10/2026) : sans dérive, une même question
# varie avec un écart-type de 0,010 en moyenne (0,038 au pire) et une étendue max de 0,11 sur 8 tirages ;
# le regroupement des fiches dans la requête n'ajoute pas de bruit.
TOLERANCE = 0.15        # |Δp| maximal sur une question (> étendue max observée ; ≈ 3σ de la question la plus bruitée)
DECALAGE_MAX = 0.05     # |Δp moyen| sur 12 canaris : bruit attendu ≈ 0,004 → 0,05 = biais systématique réel


@dataclass
class Verdict:
    modele_attendu: str
    modele_servi: str | None
    n: int = 0
    decalage: float = 0.0          # moyenne signée de (nouvelle − référence)
    ecart_max: float = 0.0
    pire: str = ""
    raisons: list[str] = field(default_factory=list)

    @property
    def derive(self) -> bool:
        return bool(self.raisons)


def comparer(reference: dict[str, float], nouvelles: dict[str, float], *, modele_attendu: str,
             modele_servi: str | None, tolerance: float = TOLERANCE, decalage_max: float = DECALAGE_MAX) -> Verdict:
    """reference / nouvelles : {nom de question: p}. Une question sans nouvelle réponse est une dérive."""
    v = Verdict(modele_attendu, modele_servi)
    if modele_servi != modele_attendu:
        v.raisons.append(f"modèle servi {modele_servi} ≠ {modele_attendu}")
    manquantes = sorted(set(reference) - set(nouvelles))
    if manquantes:
        v.raisons.append(f"{len(manquantes)} réponse(s) manquante(s)")
    ecarts = {k: nouvelles[k] - reference[k] for k in reference if k in nouvelles}
    v.n = len(ecarts)
    if ecarts:
        v.decalage = sum(ecarts.values()) / len(ecarts)
        v.pire, d = max(ecarts.items(), key=lambda kv: abs(kv[1]))
        v.ecart_max = abs(d)
        if v.ecart_max > tolerance:
            v.raisons.append(f"|Δp| = {v.ecart_max:.2f} > {tolerance} ({v.pire})")
        if abs(v.decalage) > decalage_max:
            v.raisons.append(f"décalage moyen {v.decalage:+.3f} (> {decalage_max})")
    return v


def choisir_canaris(requetes: list[dict], cache: CacheJEV, modele: str, n: int) -> tuple[list[dict], dict[str, float]]:
    """n questions déjà en cache, choisies de façon déterministe (tri par hash) et regroupées par state.
    → (payloads à envoyer, {nom: p de référence})."""
    candidates = []
    for r in requetes:
        for q in r["questions"].values():
            k = cle(modele, r["state"], q)
            if k in cache.entrees:
                candidates.append((hashlib.sha256(k.encode()).hexdigest(), k, r["state"], q))
    candidates.sort()
    choisies = candidates[:: max(1, len(candidates) // n)][:n] if candidates else []
    payloads, reference = {}, {}
    for _, k, state, q in choisies:
        nom = f"c{len(reference)}"
        reference[nom] = cache.entrees[k]["reponse"]["noul"]
        cle_state = repr(sorted(state.items()))
        lot = payloads.setdefault(cle_state, [])
        if not lot or len(lot[-1]["questions"]) >= MAX_QUESTIONS:
            lot.append({"state": state, "questions": {}})
        lot[-1]["questions"][nom] = q
    return [p for lots in payloads.values() for p in lots], reference


def interroger(payloads: list[dict], cle_api: str, modele: str, budget: Budget, journal: JournalAppels,
               appel=appeler) -> tuple[dict[str, float], str | None]:
    """Envoie les canaris SANS passer par le cache. → ({nom: p}, modèle servi)."""
    nouvelles, servi = {}, None
    for body in payloads:
        if (raison := budget.reserver()) is not None:
            raise SystemExit(f"budget : {raison}")
        rep = appel(preparer_payload(body, modele), cle_api)
        tokens = (rep.get("usage") or {}).get("input_tokens") or 0
        budget.compter_tokens(int(tokens))
        journal.ecrire(modele_demande=modele, modele_servi=rep.get("model"), questions=len(body["questions"]),
                       cache=0, tokens=tokens, statut="canari " + rep.get("error", "ok"), appels_session=budget.appels)
        if "error" in rep:
            continue
        servi = rep.get("model")
        for nom, r in (rep.get("answers") or {}).items():
            if isinstance(r, dict) and isinstance(r.get("noul"), (int, float)):
                nouvelles[nom] = float(r["noul"])
    return nouvelles, servi


def main(argv: list[str] | None = None) -> int:
    from .app import ROOT, charger_cle
    from .remplir_cache import requetes_possibles

    ap = argparse.ArgumentParser(description="Détection de dérive de JEV par canaris")
    ap.add_argument("--canaris", type=int, default=MAX_QUESTIONS, help="nombre de questions reposées (défaut 12 = 1 appel)")
    ap.add_argument("--modele", default=MODELE_JEV)
    ap.add_argument("--max-appels", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    cache = CacheJEV(ROOT / "cache_jev.json")
    payloads, reference = choisir_canaris(requetes_possibles(), cache, args.modele, args.canaris)
    if not reference:
        raise SystemExit(f"Aucune réponse de référence en cache pour {args.modele} : python3 -m server.remplir_cache")
    print(f"{len(reference)} canaris · {len(payloads)} appel(s) · modèle {args.modele} · "
          f"tolérance |Δp| ≤ {TOLERANCE}, décalage moyen ≤ {DECALAGE_MAX}")
    if args.dry_run:
        for p in payloads:
            for nom, q in p["questions"].items():
                print(f"  {nom} [{p['state'].get('langue')}] réf. {reference[nom]:.2f} · {q['instructions'][:90]}…")
        return 0
    cle_api = charger_cle()
    if not cle_api:
        raise SystemExit("Pas de clé TYPESAFE_API_KEY dans .env")
    nouvelles, servi = interroger(payloads, cle_api, args.modele, Budget(max_appels=args.max_appels),
                                  JournalAppels(ROOT / "jev_appels.jsonl"))
    v = comparer(reference, nouvelles, modele_attendu=args.modele, modele_servi=servi)
    textes = {nom: (pl["state"].get("langue"), q["instructions"]) for pl in payloads for nom, q in pl["questions"].items()}
    for nom in sorted(reference, key=lambda k: -abs(nouvelles.get(k, reference[k]) - reference[k])):
        lg, txt = textes[nom]
        nv = f"{nouvelles[nom]:.2f}  Δ {nouvelles[nom] - reference[nom]:+.2f}" if nom in nouvelles else "absente"
        print(f"  {nom:>3} [{lg}] réf. {reference[nom]:.2f} → {nv} · {txt[:80]}…")
    print(f"servi par {v.modele_servi} · {v.n} réponses · décalage moyen {v.decalage:+.3f} · |Δp| max {v.ecart_max:.3f}")
    print("⚠ DÉRIVE : " + " ; ".join(v.raisons) + "\n  → recalibrer : bench --lectures puis python3 -m analyse.calibration"
          if v.derive else "✅ pas de dérive : JEV répond comme lors de la calibration")
    return 1 if v.derive else 0


if __name__ == "__main__":
    sys.exit(main())
