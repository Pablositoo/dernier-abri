// Toutes les constantes réglables du jeu (seuils, portées, cadences, barème)

// ---------- Partie ----------
export const DUREE = 120, PV_MAX = 10, MUNITIONS = 6, RECHARGE = 1.4, CADENCE = 0.3;
export const MAX_CIBLES = 5, PORTEE = 60, SPAWN_Z = -72, BARRICADE_Z = -4.4;
export const PORTEE_SOMMATION = 45, DELAI_REACTION = 1.0, COOLDOWN_SOMMATION = 2.5;
export const VITESSES = { zombie: 1.5, humain: 4.6, blesse_zombie: 1.2, blesse_humain: 1.2 };
export const BAREME = { zombie: 10, sauve: 15, humain_abattu: -50, morsure: -20 };
export const chanceTouche = d => Math.max(0.15, Math.min(0.95, 1 - d / 60));

// ---------- Horloge simulée ----------
// La logique avance par pas fixes : même graine + mêmes décisions ⇒ même partie, quel que soit le nombre d'images/s
export const PAS_SIM = 1 / 60;
export const DT_REEL_MAX = 0.05;          // au-delà (onglet ralenti), la simulation ralentit au lieu de sauter

// ---------- Politique (règles d'engagement) ----------
export const SEUIL_DEFAUT = { jev: 0.85, jev1: 0.5 };
export const INCOH_MAX = 0.15, SEUIL_HUMAIN = 0.25;

// ---------- Tir / visée ----------
export const HAUTEUR_OEIL = 1.65;

// ---------- Réseau ----------
export const DELAI_JEV_MS = 12000, DELAI_LOG_MS = 5000, PAUSE_ERREUR_MS = 800;
