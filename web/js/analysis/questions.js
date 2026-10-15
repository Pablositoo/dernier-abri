// Protocole v2 (pur, sans réseau) : observations → requête JEV, réponses JEV → pistes.
// Partagé par le navigateur (analysis/jev.js) et le simulateur headless (tests/bench.mjs).
import { TXT } from "../ui/i18n.js";

// 2 questions Noul formulées en sens inverse par cible : si JEV est cohérent, p(zombie) ≈ 1 - p(humain).
// state ne contient que la langue et le contexte : même fiche ⇒ même requête ⇒ réponse cachable.
export function requeteClassement(cibles, langue) {
  const t = TXT[langue], questions = {};
  for (const c of cibles) {
    const fiche = t.fiche(c, c.reaction);
    questions["z_" + c.id] = { type: "noul", instructions: `${fiche} ${t.qZ}` };
    questions["h_" + c.id] = { type: "noul", instructions: `${fiche} ${t.qH}` };
  }
  return { questions, state: { langue, contexte: t.contexte } };
}

// → ids des cibles sans réponse exploitable (à reclasser)
export function appliquerClassement(cibles, pistes, answers) {
  const manquantes = [];
  for (const c of cibles) {
    const piste = pistes.get(c.id);
    if (!piste) continue;                                   // cible sortie du jeu entre-temps
    const z = answers["z_" + c.id]?.noul, h = answers["h_" + c.id]?.noul;
    if (z == null || h == null) { piste.besoinAnalyse = true; manquantes.push(c.id); continue; }
    piste.pZ = (z + (1 - h)) / 2; piste.incoh = Math.abs(z - (1 - h)); piste.lectures++;
    if (c.reaction) piste.lueAvecReaction = true; else piste.pAvant = piste.pZ;   // ce que JEV a VRAIMENT lu
  }
  return manquantes;
}
