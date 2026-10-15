// Journal : avec sim/, la seule couche qui lit la vérité terrain (pour mesurer les erreurs a posteriori).
import { DELAI_LOG_MS } from "../config.js";
import { postJSON } from "../net.js";
import { estZombie, score } from "../sim/monde.js";
import { decrire, reactionTexte } from "../perception/observer.js";

// une ligne par cible (decisions_jev.csv), modes JEV seulement
export function journalDecision(partie, e, piste, issue, langue) {
  if (!partie.mode.startsWith("jev")) return;
  postJSON("/decision", {
    mode: partie.mode, langue, seuil: partie.seuil, id: e.id, verite: estZombie(e.nature) ? "zombie" : "humain", nature: e.nature,
    description: decrire(e, langue), reaction: reactionTexte(e, langue) ?? "",
    p_zombie_avant_sommation: piste?.pAvant?.toFixed(3) ?? "", p_zombie_final: piste?.pZ?.toFixed(3) ?? "",
    incoherence: piste?.incoh?.toFixed(3) ?? "", statut_jev: piste?.statut ?? "", issue, distance_m: Math.round(e.distance),
  }, DELAI_LOG_MS).catch(() => {});
}

// une ligne par partie (resultats_parties.csv)
export function journalPartie(partie, jev, langue) {
  const m = partie.monde, s = m.stats, l = jev.lat, avecJEV = partie.mode.startsWith("jev");
  postJSON("/log", {
    mode: partie.mode, langue, seuil: avecJEV ? partie.seuil : "", score: score(s), ...s, survie_s: Math.round(m.t),
    appels_jev: jev.appels, latence_moy_ms: l.length ? Math.round(l.reduce((a, b) => a + b, 0) / l.length) : "",
  }, DELAI_LOG_MS).catch(() => {});
}
