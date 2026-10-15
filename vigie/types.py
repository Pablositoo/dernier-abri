"""Vocabulaire commun : ce qu'une source observe, ce que le noyau sait d'une entité, ce qu'il décide."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Observation:
    """Unité normalisée, quelle que soit la source. Ne contient JAMAIS la vérité terrain."""
    source: str                  # "jeu", "log:auth", "rtsp:portail"…
    entite: str                  # identifiant stable de l'entité suivie (piste)
    t: float                     # horloge de la source (s)
    texte: str                   # ce qu'un analyseur textuel (JEV) lit
    a_reagi: bool = False        # l'entité a répondu à une sommation (le texte la décrit)
    signaux: dict = field(default_factory=dict)   # mesures numériques : distance, x, z, vitesse, arrete, sommeAt…


@dataclass
class Piste:
    """Ce que le noyau sait d'une entité : lectures JEV, mesures cinématiques, preuves fusionnées, statut."""
    entite: str
    besoin_analyse: bool = True
    pZ: float | None = None
    incoh: float | None = None
    p_avant: float | None = None          # lecture avant toute réaction (journal)
    lectures: int = 0
    lue_avec_reaction: bool = False       # JEV a lu le texte APRÈS la réaction (règle R3)
    bloque: bool = False
    statut: str = "analyse"               # analyse | incertain | zombie | humain (classe positive / négative)
    mesures: list = field(default_factory=list)   # [{"t", "d", "arret": True | False | None}]
    fenetre: dict | None = None
    derniere_somme_at: float | None = None
    L: float | None = None
    p_post: float | None = None
    preuves: dict | None = None
    a_reagi: bool = False                 # dernière observation : réaction déjà décrite

    def resume(self) -> dict:
        """Ce que la source affiche (HUD) et journalise ; noms identiques aux pistes JS."""
        return {"statut": self.statut, "pZ": self.pZ, "incoh": self.incoh, "pAvant": self.p_avant, "lectures": self.lectures,
                "lueAvecReaction": self.lue_avec_reaction, "L": self.L, "pPost": self.p_post, "preuves": self.preuves,
                "mesures": [{"arret": m["arret"]} for m in self.mesures]}


@dataclass
class Decision:
    """Sortie de la politique : des intentions explicites, avec les règles qui les justifient."""
    cible: str | None = None
    sommer: bool = False
    sommer_cibles: list[str] = field(default_factory=list)
    recharger: bool = False
    bloques: list[str] = field(default_factory=list)
    raison: str = ""

    @property
    def vide(self) -> bool:
        return not (self.cible or self.sommer or self.sommer_cibles or self.recharger or self.bloques)
