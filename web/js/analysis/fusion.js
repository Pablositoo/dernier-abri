// Fusion bayésienne des preuves en log-odds : L = logit(prior) + preuve JEV + preuves cinématiques.
// L > 0 penche « zombie », L < 0 penche « humain ». Chaque preuve est un log du rapport de vraisemblance.
import { FUSION, INCOH_MAX } from "../config.js";

export const logit = p => { const q = Math.min(1 - FUSION.pClip, Math.max(FUSION.pClip, p)); return Math.log(q / (1 - q)); };
export const sigmoide = L => 1 / (1 + Math.exp(-L));

// JEV : seule la DERNIÈRE lecture cohérente compte (les lectures successives d'une même fiche ne sont pas
// indépendantes : les additionner compterait deux fois la description). Lecture incohérente = pas de preuve.
export function preuveJEV(piste) {
  return piste.pZ != null && piste.incoh <= INCOH_MAX ? logit(piste.pZ) : 0;
}

// Cinématique : chaque sommation donne une mesure. Une désobéissance humaine peut être persistante (panique),
// donc une 2e désobéissance prouve moins que la 1re : P(bouge encore | humain) > P(bouge | humain).
export function preuveCinematique(mesures) {
  const { pBougeSiZombie: pz, pBougeSiHumain, pBougeEncoreSiHumain } = FUSION;
  let L = 0, dejaBouge = false;
  for (const m of mesures) {
    if (m.arret === null) continue;
    const ph = dejaBouge ? pBougeEncoreSiHumain : pBougeSiHumain;
    L += m.arret ? Math.log((1 - pz) / (1 - ph)) : Math.log(pz / ph);
    if (!m.arret) dejaBouge = true;
  }
  return L;
}

export function fusionner(piste) {
  const jev = preuveJEV(piste), cine = preuveCinematique(piste.mesures);
  piste.preuves = { prior: logit(FUSION.prior), jev, cine };
  piste.L = piste.preuves.prior + jev + cine;
  piste.pPost = sigmoide(piste.L);
  return piste.L;
}
