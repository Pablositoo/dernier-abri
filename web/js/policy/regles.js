// Politique v2 : règles d'engagement explicites. Le modèle classe, le code décide. Doute ⇒ pas de tir.
// Fonctions pures (observations + pistes), testables en Node.
import { INCOH_MAX, SEUIL_HUMAIN, COOLDOWN_SOMMATION, PORTEE_SOMMATION, BARRICADE_Z, chanceTouche } from "../config.js";

// État d'analyse d'une cible (rempli par analysis/, lu par la politique et le HUD)
export const nouvellePiste = () => ({ besoinAnalyse: true, pZ: null, incoh: null, pAvant: null, pDecision: null,
  statut: "analyse", lectures: 0, lueAvecReaction: false, bloque: false,
  // v3 : mesures cinématiques et fusion des preuves
  mesures: [], fenetre: null, derniereSommeAt: null, L: null, pPost: null, preuves: null });

export function statut(piste, seuil) {
  if (piste.pZ == null) return piste.statut;
  return piste.incoh > INCOH_MAX ? "incertain" : piste.pZ >= seuil ? "zombie" : piste.pZ <= SEUIL_HUMAIN ? "humain" : "incertain";
}
export function majStatuts(pistes, seuil) { for (const p of pistes.values()) p.statut = statut(p, seuil); }

// sommation dès qu'une silhouette non confirmée humaine entre dans la zone
export function doitSommer(t, derniereSommation, tous, pistes) {
  return t - derniereSommation > COOLDOWN_SOMMATION &&
    tous.some(o => o.sommeAt === null && o.distance < PORTEE_SOMMATION && pistes.get(o.id)?.statut !== "humain");
}

// Ligne de tir : refuse si un non-zombie est près de la trajectoire (devant ou juste derrière la cible)
export function ligneDegagee(cible, tous, pistes) {
  const L = Math.hypot(cible.x, cible.z), ux = cible.x / L, uz = cible.z / L;
  return !tous.some(o => {
    if (o.id === cible.id || pistes.get(o.id)?.statut === "zombie") return false;
    const proj = o.x * ux + o.z * uz, lat = Math.abs(o.x * uz - o.z * ux);
    return lat < 1.0 && proj > 0 && proj < L + 4;
  });
}

const tempsAvantImpact = c => (c.distance - Math.abs(BARRICADE_Z)) / c.vitesse;

// règles d'engagement (TOUTES obligatoires, aucune exception), puis la plus urgente d'abord
export function eligibles(vis, pistes) {
  return vis.filter(c => {
    const p = pistes.get(c.id);
    return p &&
      p.statut === "zombie" &&            // R1 p(zombie) >= seuil
      p.incoh <= INCOH_MAX &&             // R2 les 2 questions opposées sont d'accord
      p.lueAvecReaction &&                // R3 JEV a lu la réaction à la sommation
      !c.arrete &&                        // R4 une silhouette arrêtée mains en l'air n'est jamais une cible
      (chanceTouche(c.distance) >= .5 || c.distance < 15);   // R5 tir raisonnable (pas de balle gâchée)
  }).sort((a, b) => tempsAvantImpact(a) - tempsAvantImpact(b));
}

// → { cible, bloques } : bloques = cibles éligibles refusées pour la 1re fois (survivant dans la ligne de tir)
// regles : eligibles (v2) ou eligiblesV3 ; la plus urgente d'abord
export function choisirCible(vis, tous, pistes, regles = eligibles) {
  const bloques = [];
  for (const c of regles(vis, pistes, tous).sort((a, b) => tempsAvantImpact(a) - tempsAvantImpact(b))) {
    if (ligneDegagee(c, tous, pistes)) return { cible: c, bloques };
    if (!pistes.get(c.id).bloque) bloques.push(c.id);
  }
  return { cible: null, bloques };
}
