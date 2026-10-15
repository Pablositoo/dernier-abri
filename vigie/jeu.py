"""
Domaine « jeu » : la politique v5 (v4 + JEV calibré) portée depuis web/js/{partie,policy/*}.js.
Le jeu envoie ses observations (sans la nature réelle) ; le noyau renvoie une décision ; le jeu vise, et revérifie
la ligne de tir au moment du tir (verrou local). Mêmes résultats que la v5 JavaScript : tests/test_vigie.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .analyseurs import AnalyseurJEV, ClientJEV, Hypotheses, suivre_cinematique
from .fusion import P, Calibrateur, fusionner, statut_sprt
from .noyau import JournalRepondeur, verifier_repondeurs
from .types import Decision, Observation, Piste


@dataclass(frozen=True)
class RegleJeu:
    """Identiques à web/js/config.js (vérifié par tests/test_vigie.py)."""
    portee_sommation: float = 45
    cooldown_sommation: float = 2.5
    barricade_z: float = -4.4
    munitions: int = 6
    max_sommations: int = 2
    portee_opportunite: float = 45
    recharge_tactique: int = 2

    @staticmethod
    def chance_touche(d: float) -> float:
        return max(0.15, min(0.95, 1 - d / 60))


R = RegleJeu()


# ---------- Règles (fonctions pures : observations + pistes) ----------
def doit_sommer(t: float, derniere: float, tous: list[Observation], pistes: dict[str, Piste]) -> bool:
    return t - derniere > R.cooldown_sommation and any(
        o.signaux["sommeAt"] is None and o.signaux["distance"] < R.portee_sommation
        and (pistes.get(o.entite) is None or pistes[o.entite].statut != "humain") for o in tous)


def ligne_degagee(c: Observation, tous: list[Observation], pistes: dict[str, Piste]) -> bool:
    """Refuse si un non-zombie est près de la trajectoire (devant, ou jusqu'à 4 m derrière la cible)."""
    L = math.hypot(c.signaux["x"], c.signaux["z"])
    ux, uz = c.signaux["x"] / L, c.signaux["z"] / L
    for o in tous:
        if o.entite == c.entite or (o.entite in pistes and pistes[o.entite].statut == "zombie"):
            continue
        proj = o.signaux["x"] * ux + o.signaux["z"] * uz
        lat = abs(o.signaux["x"] * uz - o.signaux["z"] * ux)
        if lat < 1.0 and 0 < proj < L + 4:
            return False
    return True


def temps_avant_impact(c: Observation) -> float:
    return (c.signaux["distance"] - abs(R.barricade_z)) / c.signaux["vitesse"]


def tir_raisonnable(c: Observation) -> bool:                       # R5
    return R.chance_touche(c.signaux["distance"]) >= 0.5 or c.signaux["distance"] < 15


def confirmes(vis: list[Observation], pistes: dict[str, Piste]) -> list[Observation]:
    """S1 SPRT · S2 concordance JEV ET mouvement · R3 réaction lue · R4 pas arrêté mains en l'air."""
    out = []
    for c in vis:
        p = pistes.get(c.entite)
        if (p and p.statut == "zombie" and p.preuves["jev"] > 0 and p.incoh <= P.incoh_max and p.preuves["cine"] > 0
                and p.lue_avec_reaction and not c.signaux["arrete"]):
            out.append(c)
    return out


def eligibles_v4(vis, pistes, tous) -> list[Observation]:
    """R5, ou tir d'opportunité jusqu'à 45 m si la ligne est libre maintenant."""
    return [c for c in confirmes(vis, pistes)
            if tir_raisonnable(c) or (c.signaux["distance"] < R.portee_opportunite and ligne_degagee(c, tous, pistes))]


def choisir_cible(vis, tous, pistes) -> tuple[Observation | None, list[str]]:
    bloques = []
    for c in sorted(eligibles_v4(vis, pistes, tous), key=temps_avant_impact):
        if ligne_degagee(c, tous, pistes):
            return c, bloques
        if not pistes[c.entite].bloque:
            bloques.append(c.entite)
    return None, bloques


def a_resommer(vis, pistes) -> list[str]:
    return [c.entite for c in vis
            if (p := pistes.get(c.entite)) and p.statut == "incertain" and p.lue_avec_reaction and not p.fenetre
            and 1 <= len(p.mesures) < R.max_sommations and c.signaux["distance"] < R.portee_sommation]


def doit_recharger(monde: dict, vis, pistes) -> bool:
    return (monde["mun"] <= R.recharge_tactique and monde["mun"] < R.munitions and monde["t"] >= monde["rechargeFin"]
            and not any(c.signaux["distance"] < R.portee_opportunite for c in confirmes(vis, pistes)))


# ---------- Session : une partie pilotée par le noyau ----------
class RepondeurJeu:
    """Renvoie la décision au jeu, qui l'exécute (dont le tir). NON informatif : interdit sur une source réelle."""
    nom, informatif = "jeu", False

    def repondre(self, *_):
        pass                                   # la décision part dans la réponse WebSocket (voir SessionJeu.traiter)


@dataclass
class SessionJeu:
    client: ClientJEV
    journal: JournalRepondeur | None = None
    latence: float = 0.0
    synchrone: bool = False
    calibrateur: Calibrateur | None = field(default_factory=Calibrateur.depuis_js)
    nom: str = "jeu"
    reel: bool = False                         # le jeu est une simulation
    pistes: dict[str, Piste] = field(default_factory=dict)
    derive: dict | None = None

    def __post_init__(self):
        self.jev = AnalyseurJEV(self.client, latence=self.latence, synchrone=self.synchrone)
        self.repondeurs = verifier_repondeurs(self, [RepondeurJeu()] + ([self.journal] if self.journal else []))

    def observations(self, msg: dict) -> list[Observation]:
        return [Observation(source=self.nom, entite=o["id"], t=msg["t"], texte=o["texte"], a_reagi=bool(o["reaction"]),
                            signaux={k: o[k] for k in ("distance", "x", "z", "vitesse", "arrete", "sommeAt")})
                for o in msg["observations"]]

    def traiter(self, msg: dict) -> dict:
        """Message « etat » du jeu → message « decision ». Même ordre d'opérations que pasPartie (web/js/partie.js)."""
        t, monde = msg["t"], {**msg["monde"], "t": msg["t"]}
        tous = self.observations(msg)
        par_id = {o.entite: o for o in tous}
        vis = [par_id[i] for i in msg["visibles"]]
        # pistes : apparition = 1re observation ; réaction à la sommation (nouveau texte) = à relire
        for o in tous:
            p = self.pistes.get(o.entite)
            if p is None:
                self.pistes[o.entite] = p = Piste(o.entite)
            if o.a_reagi and not p.a_reagi:
                p.besoin_analyse = True
            p.a_reagi = o.a_reagi
        for i in [i for i in self.pistes if i not in par_id]:
            del self.pistes[i]                 # entité morte ou partie : plus jamais observée
        self.jev.tic(t)
        self._verifier_derive()

        d = Decision()
        for o in tous:
            p = self.pistes[o.entite]
            suivre_cinematique(p, o, t)
            fusionner(p, self.calibrateur)
            p.statut = statut_sprt(p)
        a_analyser = [c for c in vis if self.pistes[c.entite].besoin_analyse]
        if a_analyser and not self.jev.occupe:
            j = msg["jev"]
            self.jev.classer(a_analyser, self.pistes, Hypotheses(msg["langue"], j["contexte"], j["qZ"], j["qH"]), t)
        if doit_sommer(t, monde["derniereSommation"], tous, self.pistes):
            d.sommer = True
        d.sommer_cibles = a_resommer(vis, self.pistes)
        cible, d.bloques = choisir_cible(vis, tous, self.pistes)
        for i in d.bloques:
            self.pistes[i].bloque = True
        d.cible = cible.entite if cible else None
        d.recharger = d.cible is None and doit_recharger(monde, vis, self.pistes)
        if d.cible:
            p = self.pistes[d.cible]
            d.raison = f"SPRT L={p.L:.2f} ≥ {P.seuil_a:.2f}, JEV {p.preuves['jev']:+.2f} et mouvement {p.preuves['cine']:+.2f} concordants, ligne libre"
        for r in self.repondeurs:
            r.repondre(self.nom, t, d, self.pistes)
        return {"type": "decision", "tick": msg.get("tick"), "cible": d.cible, "sommer": d.sommer,
                "sommerCibles": d.sommer_cibles, "recharger": d.recharger, "bloques": d.bloques,
                "derive": self.derive, "erreur": self.jev.erreur,
                "pistes": {i: p.resume() for i, p in self.pistes.items()}}

    def _verifier_derive(self):
        """Calibration apprise sur UN modèle : un autre modèle servi ⇒ probabilités brutes + alerte."""
        servi = self.jev.modele_servi
        if self.calibrateur and servi and servi != self.calibrateur.modele:
            self.derive = {"attendu": self.calibrateur.modele, "servi": servi}
            self.calibrateur = None
