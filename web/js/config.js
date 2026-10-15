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

// ---------- Monde : obéissance à la sommation ----------
// Cas piège pour la sécurité : un humain qui panique ou n'entend pas ne s'arrête pas (0 = monde v2.2)
export const P_DESOBEISSANCE = 0.05;      // humain qui ne s'arrête pas à la 1re sommation
export const P_OBEIT_2E = 0.7;            // … mais s'arrête à la 2e sommation
export const MAX_SOMMATIONS = 2;          // 1 sommation générale + 1 sommation ciblée par silhouette

// ---------- Politique (règles d'engagement) ----------
export const POLITIQUE_DEFAUT = "v4";     // v2 = seuil fixe (v2.2), v3 = fusion bayésienne + SPRT, v4 = v3 + ordonnancement
export const SEUIL_DEFAUT = { jev: 0.85, jev1: 0.5 };
export const INCOH_MAX = 0.15, SEUIL_HUMAIN = 0.25;

// ---------- v3 : fusion des preuves (log-odds) + test séquentiel de Wald ----------
export const FUSION = {
  prior: 0.5,                             // neutre : on n'ajoute pas la proportion de zombies du jeu
  pClip: 0.01,                            // p JEV bornée à [0,01 ; 0,99] (pas de certitude absolue)
  // analyseur cinématique : vraisemblances supposées (le simulateur, lui, a ses propres taux ci-dessus)
  pBougeSiZombie: 0.98,                   // un zombie ignore la sommation
  pBougeSiHumain: 0.05,                   // un humain qui ne s'arrête pas (1re sommation)
  pBougeEncoreSiHumain: 0.3,              // … et qui ne s'arrête toujours pas à la 2e (désobéissance persistante)
  fenetre: [0.5, 2.0],                    // mesure du déplacement entre sommation + 0,5 s et + 2,0 s
  seuilArret: 0.2, seuilBouge: 0.5,       // m : < 0,2 = arrêté, > 0,5 = continue, entre les deux = pas de preuve
  alpha: 0.005,                           // risque visé de tirer sur un humain
  beta: 0.05,                             // risque visé de laisser passer un zombie
};

// ---------- v4 : ordonnancement des tirs par coût (ne touche ni au SPRT ni à la ligne de tir) ----------
// Benchmark : 56 % des morsures restantes en v3 = ligne de tir jamais libre (prix de la sécurité, non évitable),
// 30 % = ligne libre seulement entre 30 et 45 m. Prédire les positions pour « attendre une meilleure occasion »
// n'apporte rien (de nouveaux humains bloquent la ligne) : la règle simple « tirer dès que c'est libre » gagne.
export const ORDONNANCEMENT = {
  porteeOpportunite: 45,                  // m : au-delà de R5 (30 m), tir d'opportunité si la ligne est libre maintenant
  rechargeTactique: 2,                    // recharge si ≤ 2 balles et aucune cible confirmée à portée
};

// ---------- Tir / visée ----------
export const HAUTEUR_OEIL = 1.65;

// ---------- Réseau ----------
export const DELAI_JEV_MS = 12000, DELAI_LOG_MS = 5000, PAUSE_ERREUR_MS = 800;
