"""
Phase 5 — Calibration de JEV : quand JEV dit p = 0,8, la cible est-elle un zombie 80 % du temps ?

    node tests/bench.mjs --parties 500 --langue en --lectures bench_resultats/lectures_en.json
    node tests/bench.mjs --parties 500 --langue fr --lectures bench_resultats/lectures_fr.json
    python3 -m analyse.calibration            # métriques + diagramme + web/js/analysis/calibration_jev.js

Points de méthode :
- La vérité vient du catalogue du jeu (nature de la fiche), jamais de JEV.
- 100 000 lectures, mais seulement 50 fiches distinctes : une même fiche donne toujours la même réponse.
  La taille d'échantillon effective est le nombre de FICHES. Les poids (fréquence en jeu) sont donc
  normalisés pour sommer au nombre de fiches.
- Validation croisée « une description à la fois » (les variantes 0 / r / d d'une même description restent
  ensemble) : c'est la seule estimation honnête de ce que la calibration donnerait sur une fiche jamais vue.
- Seules les lectures cohérentes (incohérence ≤ 0,15) servent de preuve dans la fusion : on calibre celles-là.
- Règle de choix : meilleure log-loss en validation croisée parmi les calibrateurs qui, HORS échantillon,
  (1) gardent une marge de sécurité pire cas au moins égale à celle de JEV brut (humains) et
  (2) ne demandent jamais plus de sommations que JEV brut pour confirmer une fiche zombie.
  Le critère (2) a été ajouté après coup : la 1re règle (log-loss + marge) choisissait l'isotonique, et le
  benchmark hors échantillon (--calibration-cv) a montré 4,2 morsures/partie en EN (contre 0,95) : une fiche
  zombie inconnue tombe dans la marche de l'escalier et n'est plus jamais confirmée.
- La preuve envoyée à la fusion est un rapport de vraisemblance : logit(p calibrée) − logit(taux de zombies
  des données), car la fusion a son propre a priori neutre (0,5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parent.parent
P_CLIP = 0.01            # identique à FUSION.pClip (web/js/config.js)
INCOH_MAX = 0.15         # identique à INCOH_MAX
ZOMBIES = {"zombie", "blesse_zombie"}
# SPRT et pire cas cinématique, identiques à FUSION (web/js/config.js) ; le test JS v5 revérifie la marge
SEUIL_A = np.log(0.95 / 0.005)
PREUVE_BOUGE = (np.log(0.98 / 0.05), np.log(0.98 / 0.3))         # 1re et 2e sommation ignorées
PIRE_CINEMATIQUE = sum(PREUVE_BOUGE)                              # l'humain continue aux 2 sommations


# ================= Données =================
@dataclass
class Lectures:
    langue: np.ndarray
    item: np.ndarray
    groupe: np.ndarray       # langue + nature + n° de description (les variantes 0/r/d restent ensemble)
    y: np.ndarray            # 1 = zombie (vérité du catalogue)
    p: np.ndarray            # pZ = (z + 1 - h) / 2, comme web/js/analysis/questions.js
    incoh: np.ndarray
    n: np.ndarray            # nombre de lectures en jeu (fréquence)
    modele: str

    def filtre(self, masque) -> "Lectures":
        return Lectures(*(getattr(self, c)[masque] for c in ("langue", "item", "groupe", "y", "p", "incoh", "n")),
                        modele=self.modele)

    @property
    def w(self) -> np.ndarray:
        """Poids normalisés : somme = nombre de fiches (taille d'échantillon effective)."""
        return self.n / self.n.sum() * len(self.n)


def charger(fichiers: list[Path]) -> Lectures:
    lignes, modeles = [], set()
    for f in fichiers:
        d = json.loads(f.read_text())
        modeles.add(d["modele"])
        lignes += d["lectures"]
    if len(modeles) != 1:
        raise ValueError(f"lectures de plusieurs modèles mélangées : {modeles}")
    col = lambda f: np.array([f(l) for l in lignes])
    return Lectures(
        langue=col(lambda l: l["langue"]), item=col(lambda l: l["item"]),
        groupe=col(lambda l: l["langue"] + " " + l["item"].rsplit("_", 1)[0]),
        y=col(lambda l: float(l["nature"] in ZOMBIES)),
        p=col(lambda l: (l["z"] + 1 - l["h"]) / 2), incoh=col(lambda l: abs(l["z"] - (1 - l["h"]))),
        n=col(lambda l: float(l["n"])), modele=modeles.pop())


# ================= Métriques =================
def clip(p):
    return np.clip(p, P_CLIP, 1 - P_CLIP)


def logit(p):
    p = clip(p)
    return np.log(p / (1 - p))


def brier(p, y, w):
    return float(np.average((p - y) ** 2, weights=w))


def log_loss(p, y, w):
    p = clip(p)
    return float(np.average(-(y * np.log(p) + (1 - y) * np.log(1 - p)), weights=w))


def fiabilite(p, y, w, bins=5):
    """Diagramme de fiabilité : par tranche de p prédite → (p moyenne prédite, fréquence observée, poids)."""
    bords = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, bords) - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if w[m].sum() > 0:
            out.append((float(np.average(p[m], weights=w[m])), float(np.average(y[m], weights=w[m])), float(w[m].sum())))
    return out


def ece(p, y, w, bins=5):
    """Expected Calibration Error : écart moyen |prédit − observé|, pondéré par tranche."""
    t = fiabilite(p, y, w, bins)
    return float(sum(pw * abs(pp - fo) for pp, fo, pw in t) / sum(pw for _, _, pw in t))


def metriques(p, y, w) -> dict:
    return {"brier": brier(p, y, w), "log_loss": log_loss(p, y, w), "ece": ece(p, y, w)}


# ================= Calibrateurs =================
class Brut:
    nom = "brut (JEV tel quel)"

    def fit(self, p, y, w):
        return self

    def predict(self, p):
        return clip(p)


class Platt:
    """Régression logistique sur logit(p) : 2 paramètres, régularisée (C=1) car les classes sont séparables."""
    nom = "Platt (logistique, 2 paramètres)"

    def fit(self, p, y, w):
        self.m = LogisticRegression(C=1.0).fit(logit(p).reshape(-1, 1), y, sample_weight=w)
        self.a, self.b = float(self.m.coef_[0, 0]), float(self.m.intercept_[0])
        return self

    def predict(self, p):
        return clip(1 / (1 + np.exp(-(self.a * logit(p) + self.b))))


class Isotonique:
    """Régression isotonique (fonction croissante en escalier) : flexible, donc risque de sur-apprentissage."""
    nom = "isotonique"

    def fit(self, p, y, w):
        self.m = IsotonicRegression(y_min=P_CLIP, y_max=1 - P_CLIP, out_of_bounds="clip").fit(p, y, sample_weight=w)
        return self

    def predict(self, p):
        return clip(self.m.predict(p))


CALIBRATEURS = (Brut, Platt, Isotonique)


def validation_croisee(d: Lectures, fabrique) -> np.ndarray:
    """Prédictions hors échantillon : chaque description est prédite par un calibrateur appris SANS elle."""
    pred = np.empty_like(d.p)
    for g in np.unique(d.groupe):
        test = d.groupe == g
        pred[test] = fabrique().fit(d.p[~test], d.y[~test], d.w[~test]).predict(d.p[test])
    return pred


def taux_zombies(d: Lectures) -> float:
    return float(np.average(d.y, weights=d.w))


def marge_securite(d: Lectures, p_cal: np.ndarray, brut: bool) -> tuple[float, str]:
    """Pire cas : fiche humaine après réaction, l'humain continue aux 2 sommations. Marge = A − L (> 0 = sûr)."""
    humains = (d.y == 0) & ~np.char.endswith(d.item.astype(str), "_0")
    preuve = logit(p_cal[humains]) - (0 if brut else logit(taux_zombies(d)))
    marges = SEUIL_A - (preuve + PIRE_CINEMATIQUE)
    j = int(np.argmin(marges))
    return float(marges[j]), f"{d.langue[humains][j]} {d.item[humains][j]}"


def sommations_pour_confirmer(d: Lectures, p_cal: np.ndarray, brut: bool) -> np.ndarray:
    """Fiches zombies après réaction : nombre de sommations ignorées nécessaires pour atteindre A (99 = jamais)."""
    zombies = (d.y == 1) & ~np.char.endswith(d.item.astype(str), "_0")
    L = logit(p_cal[zombies]) - (0 if brut else logit(taux_zombies(d)))
    return np.where(L + PREUVE_BOUGE[0] >= SEUIL_A, 1, np.where(L + PIRE_CINEMATIQUE >= SEUIL_A, 2, 99))


def evaluer(d: Lectures) -> dict:
    """{calibrateur: {« dans l'échantillon » | « validation croisée »: métriques + marge + sommations}}"""
    res = {}
    for C in CALIBRATEURS:
        for cas, p in (("dans l'échantillon", C().fit(d.p, d.y, d.w).predict(d.p)),
                       ("validation croisée", validation_croisee(d, C))):
            marge, fiche = marge_securite(d, p, C is Brut)
            res.setdefault(C.nom, {})[cas] = {**metriques(p, d.y, d.w), "marge": marge, "fiche_pire": fiche,
                                              "sommations": sommations_pour_confirmer(d, p, C is Brut)}
    return res


def choisir(res: dict):
    """Meilleure log-loss CV parmi les calibrateurs au moins aussi sûrs que JEV brut ET jamais plus lents à confirmer."""
    cv = {C: res[C.nom]["validation croisée"] for C in CALIBRATEURS}
    admis = [C for C in CALIBRATEURS if cv[C]["marge"] >= cv[Brut]["marge"]
             and (cv[C]["sommations"] <= cv[Brut]["sommations"]).all()]
    return min(admis, key=lambda C: cv[C]["log_loss"])


# ================= Export pour le jeu =================
def parametres(cal) -> dict:
    if isinstance(cal, Isotonique):
        return {"methode": "isotonique", "x": [round(float(v), 4) for v in cal.m.X_thresholds_],
                "y": [round(float(v), 4) for v in cal.m.y_thresholds_]}
    if isinstance(cal, Platt):
        return {"methode": "platt", "a": round(cal.a, 4), "b": round(cal.b, 4)}
    return {"methode": "brut"}


def exporter_js(d: Lectures, cal, chemin: Path, cv: dict):
    """Écrit le module JS lu par la politique v5 (pas de bundler : un module ES plutôt qu'un .json)."""
    cv = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cv.items() if k != "sommations"}
    conf = {"modele": d.modele, **parametres(cal), "tauxZombies": round(taux_zombies(d), 4), "fiches": int(len(d.y)),
            "incohMax": INCOH_MAX, "validationCroisee": cv}
    chemin.write_text(
        "// Généré par `python3 -m analyse.calibration` (phase 5) — ne pas modifier à la main.\n"
        "// Calibration des lectures JEV cohérentes, valable pour CE modèle uniquement (sinon : désactivée).\n"
        "// isotonique : p calibrée = interpolation linéaire de (x → y), bornée aux extrémités (comme sklearn).\n"
        "// tauxZombies : proportion de zombies dans ces données, retirée pour obtenir un rapport de vraisemblance.\n"
        f"export const CALIBRATION_JEV = {json.dumps(conf, ensure_ascii=False, indent=2)};\n")
    return conf


def exporter_table_cv(d: Lectures, C, chemin: Path):
    """Prédictions hors échantillon par fiche : le benchmark peut ainsi mesurer l'effet SANS sur-apprentissage."""
    pred = validation_croisee(d, C)
    lignes = [{"langue": str(l), "item": str(i), "pZ": round(float(p), 4), "incoh": round(float(q), 4),
               "pCal": round(float(c), 4)} for l, i, p, q, c in zip(d.langue, d.item, d.p, d.incoh, pred)]
    chemin.write_text(json.dumps({"modele": d.modele, "methode": C.nom, "tauxZombies": taux_zombies(d),
                                  "table": lignes}, ensure_ascii=False, indent=1))


def figure(d_tout: Lectures, d: Lectures, preds: dict, chemin: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for ax in axes[:2]:
        ax.plot([0, 1], [0, 1], ":", color="grey", label="calibration parfaite")
        ax.set_xlabel("p(zombie) annoncée"); ax.set_ylabel("fréquence réelle de zombies")
        ax.set_xlim(0, 1); ax.set_ylim(-.03, 1.03)
    ax = axes[0]
    for lg, coul in (("en", "tab:blue"), ("fr", "tab:orange")):
        s = d_tout.filtre(d_tout.langue == lg)
        coh = s.incoh <= INCOH_MAX
        ax.scatter(s.p[coh], s.y[coh], s=20 + 300 * s.w[coh] / s.w.max(), color=coul, alpha=.7, label=f"{lg} cohérente")
        ax.scatter(s.p[~coh], s.y[~coh], s=20 + 300 * s.w[~coh] / s.w.max(), facecolors="none", edgecolors=coul,
                   label=f"{lg} incohérente (ignorée)")
    ax.set_title("JEV brut : chaque point = une fiche (taille = fréquence)")
    ax.legend(fontsize=7, loc="center right")
    ax = axes[1]
    for nom, p in preds.items():
        t = fiabilite(p, d.y, d.w)
        ax.plot([a for a, _, _ in t], [b for _, b, _ in t], "o-", label=f"{nom} (ECE {ece(p, d.y, d.w):.3f})")
    ax.set_title("Lectures cohérentes : fiabilité en validation croisée")
    ax.legend(fontsize=7, loc="upper left")

    # Ce qui compte pour la DÉCISION : la preuve JEV de chaque fiche (après réaction) face aux seuils du SPRT.
    # Ligne pleine : un humain qui désobéit 2 fois reste sous le seuil de tir ssi preuve < A − pire cinématique ;
    # c'est aussi la preuve minimale pour confirmer un zombie en 2 sommations (même valeur).
    ax = axes[2]
    apres = ~np.char.endswith(d.item.astype(str), "_0")
    pi = logit(taux_zombies(d))
    for (nom, p), m in zip(preds.items(), ("o", "s", "^")):
        preuve = logit(p) - (0 if nom == Brut.nom else pi)
        for cls, coul in ((1, "tab:green"), (0, "tab:red")):
            k = apres & (d.y == cls)
            ax.scatter(d.p[k], preuve[k], marker=m, color=coul, alpha=.6, s=35,
                       label=f"{nom.split(' (')[0]} · {'zombies' if cls else 'humains'}")
    ax.axhline(SEUIL_A - PIRE_CINEMATIQUE, color="black", lw=1.2)
    ax.axhline(SEUIL_A - PREUVE_BOUGE[0], color="black", lw=.8, ls="--")
    ax.text(0.02, SEUIL_A - PIRE_CINEMATIQUE + .15, f"{SEUIL_A - PIRE_CINEMATIQUE:.2f} : humain sûr dessous · zombie en 2 sommations dessus",
            fontsize=7)
    ax.text(0.02, SEUIL_A - PREUVE_BOUGE[0] + .15, "zombie confirmé dès la 1re sommation", fontsize=7)
    ax.set_xlabel("p(zombie) brute de JEV"); ax.set_ylabel("preuve JEV (log-rapport de vraisemblance)")
    ax.set_title("Décision : preuve par fiche, hors échantillon")
    ax.legend(fontsize=6, loc="lower right", ncol=2)
    fig.suptitle(f"Diagramme de fiabilité JEV ({d.modele}) — {len(d_tout.y)} fiches, dont {len(d.y)} cohérentes")
    fig.tight_layout()
    fig.savefig(chemin, dpi=110)
    plt.close(fig)


def main():
    fichiers = sorted((ROOT / "bench_resultats").glob("lectures_*.json"))
    if not fichiers:
        raise SystemExit("Aucune lecture : node tests/bench.mjs --langue en --lectures bench_resultats/lectures_en.json")
    tout = charger(fichiers)
    d = tout.filtre(tout.incoh <= INCOH_MAX)
    print(f"{len(tout.y)} fiches ({int(tout.n.sum())} lectures en jeu), dont {len(d.y)} cohérentes · modèle {tout.modele}\n")

    res = evaluer(d)
    print(f"{'Calibrateur':34}{'':>4}{'Brier':>8}{'LogLoss':>9}{'ECE':>7}{'Marge':>7}{'Jamais':>8}"
          "  fiche humaine la plus proche du tir")
    for nom, r in res.items():
        for cas, m in r.items():
            print(f"{nom:34}{'in ' if cas.startswith('dans') else 'CV '}{m['brier']:9.4f}{m['log_loss']:9.4f}"
                  f"{m['ece']:7.3f}{m['marge']:7.2f}{int((m['sommations'] == 99).sum()):8d}  {m['fiche_pire']}")
    print("(Marge = A − L pire cas humain, > 0 = sûr · Jamais = fiches zombies jamais confirmées, même après 2 sommations)")

    preds = {C.nom: validation_croisee(d, C) for C in CALIBRATEURS}
    figure(tout, d, preds, ROOT / "analyse" / "fiabilite_jev.png")
    C = choisir(res)
    conf = exporter_js(d, C().fit(d.p, d.y, d.w), ROOT / "web" / "js" / "analysis" / "calibration_jev.js",
                       res[C.nom]["validation croisée"])
    exporter_table_cv(d, C, ROOT / "bench_resultats" / "calibration_cv.json")
    print(f"\nChoix (règle ci-dessus) : {C.nom} · taux de zombies = {conf['tauxZombies']}")
    print("→ analyse/fiabilite_jev.png · web/js/analysis/calibration_jev.js · bench_resultats/calibration_cv.json")
    return res


if __name__ == "__main__":
    main()
