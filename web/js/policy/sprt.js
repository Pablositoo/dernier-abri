// Politique v3 : test séquentiel de Wald (SPRT) sur les preuves fusionnées.
//   L ≥ A  → zombie confirmé (tir possible si toutes les règles passent)
//   L ≤ B  → humain confirmé
//   sinon  → incertain : on ESCALADE (2e sommation ciblée), et dans le doute on ne tire jamais.
// α = risque visé de tirer sur un humain, β = risque visé de laisser passer un zombie.
import { FUSION, INCOH_MAX, MAX_SOMMATIONS, PORTEE_SOMMATION, chanceTouche } from "../config.js";

export const SEUIL_A = Math.log((1 - FUSION.beta) / FUSION.alpha);    // ≈ 5,25
export const SEUIL_B = Math.log(FUSION.beta / (1 - FUSION.alpha));    // ≈ -2,99

export function statutSPRT(piste) {
  if (piste.L == null || (piste.pZ == null && !piste.mesures.length)) return "analyse";
  return piste.L >= SEUIL_A ? "zombie" : piste.L <= SEUIL_B ? "humain" : "incertain";
}

export const tirRaisonnable = c => chanceTouche(c.distance) >= .5 || c.distance < 15;   // R5

// Règles d'engagement v3 (TOUTES obligatoires) :
export const eligiblesV3 = (vis, pistes) => confirmesV3(vis, pistes).filter(tirRaisonnable);

// Cibles confirmées : toutes les règles sauf R5 (la distance de tir est décidée par l'ordonnancement en v4)
export function confirmesV3(vis, pistes) {
  return vis.filter(c => {
    const p = pistes.get(c.id);
    return p &&
      p.statut === "zombie" &&                              // S1 SPRT : L ≥ A
      p.preuves.jev > 0 && p.incoh <= INCOH_MAX &&          // S2 concordance : JEV (cohérent) penche zombie…
      p.preuves.cine > 0 &&                                 //    … ET le mouvement aussi (2 sources indépendantes)
      p.lueAvecReaction &&                                  // R3 JEV a lu la réaction à la sommation
      !c.arrete;                                            // R4 une silhouette arrêtée mains en l'air n'est jamais une cible
  });
}

// Escalade : 2e sommation ciblée sur les silhouettes encore incertaines dont la 1re mesure est terminée
export function aResommer(vis, pistes) {
  return vis.filter(c => {
    const p = pistes.get(c.id);
    return p && p.statut === "incertain" && p.lueAvecReaction && !p.fenetre &&
      p.mesures.length >= 1 && p.mesures.length < MAX_SOMMATIONS && c.distance < PORTEE_SOMMATION;
  }).map(c => c.id);
}
