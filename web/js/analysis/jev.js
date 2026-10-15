// Analyseur JEV (via le proxy local). JEV ne renvoie que des probabilités : la décision reste dans policy/.
import { PAUSE_ERREUR_MS, chanceTouche } from "../config.js";
import { postJSON } from "../net.js";
import { TXT } from "../ui/i18n.js";

export const etatJEV = { appels: 0, tokens: 0, lat: [], busy: false, probas: {}, choix: "—", err: "", generation: 0 };

export function reinitialiserJEV() {
  Object.assign(etatJEV, { appels: 0, tokens: 0, lat: [], busy: false, probas: {}, choix: "—", err: "" });
  etatJEV.generation++;                      // les réponses d'une partie précédente sont ignorées
}

function compter(r) {
  etatJEV.appels++; etatJEV.tokens += r.usage?.input_tokens || 0; etatJEV.lat.push(r.latence_ms); etatJEV.err = "";
}
const pause = ms => new Promise(r => setTimeout(r, ms));   // rythme réseau (temps réel), pas logique de jeu

export const analyseurJEV = {
  get occupe() { return etatJEV.busy; },

  // ---- v2 : 2 questions Noul opposées par cible → p(zombie) et incohérence ----
  async classer(cibles, pistes, langue) {
    etatJEV.busy = true;
    const gen = etatJEV.generation, t = TXT[langue], questions = {};
    for (const c of cibles) {
      pistes.get(c.id).besoinAnalyse = false;
      const fiche = t.fiche(c, c.reaction);
      // deux questions formulées en sens inverse : si JEV est cohérent, p(zombie) ≈ 1 - p(humain)
      questions["z_" + c.id] = { type: "noul", instructions: `${fiche} ${t.qZ}` };
      questions["h_" + c.id] = { type: "noul", instructions: `${fiche} ${t.qH}` };
    }
    const payload = { questions,   // le modèle JEV est figé côté serveur
      state: { langue, contexte: t.contexte, cibles: cibles.map(c => ({ id: c.id, description: c.desc, distance_m: Math.round(c.distance), reaction_sommation: c.reaction })) } };
    try {
      const r = await postJSON("/jev", payload);
      if (gen !== etatJEV.generation) return;
      compter(r);
      for (const c of cibles) {
        const piste = pistes.get(c.id);
        if (!piste) continue;                                   // cible sortie du jeu entre-temps
        const z = r.answers["z_" + c.id]?.noul, h = r.answers["h_" + c.id]?.noul;
        if (z == null || h == null) { piste.besoinAnalyse = true; continue; }
        piste.pZ = (z + (1 - h)) / 2; piste.incoh = Math.abs(z - (1 - h)); piste.lectures++;
        if (c.reaction) piste.lueAvecReaction = true; else piste.pAvant = piste.pZ;   // ce que JEV a VRAIMENT lu
      }
    } catch (e) {
      if (gen !== etatJEV.generation) return;
      cibles.forEach(c => { const p = pistes.get(c.id); if (p) p.besoinAnalyse = true; });
      etatJEV.err = t.err + e.message; await pause(PAUSE_ERREUR_MS);
    } finally { if (gen === etatJEV.generation) etatJEV.busy = false; }
  },

  // ---- v1 : une seule question Choice « sur qui tirer ? » ----
  async choisir(partie, cibles, langue) {
    etatJEV.busy = true;
    const gen = etatJEV.generation, t = TXT[langue], m = partie.monde, criteria = {};
    for (const c of cibles) criteria[c.id] = t.v1Crit(c);
    criteria.attendre = t.v1Wait;
    const payload = {   // le modèle JEV est figé côté serveur
      state: { pv_abri: m.pv, munitions: m.mun, rechargement_en_cours: m.t < m.rechargeFin,
        cibles: cibles.map(c => ({ id: c.id, description: c.desc, distance_m: Math.round(c.distance), chance_de_toucher: +chanceTouche(c.distance).toFixed(2) })) },
      questions: { action: { type: "choice", criteria, instructions: t.v1Instr } } };
    try {
      const r = await postJSON("/jev", payload);
      if (gen !== etatJEV.generation) return;
      const a = r.answers.action;
      compter(r);
      etatJEV.probas = a.probabilities; etatJEV.choix = a.choice;
      // JEV peut changer d'avis à chaque réponse : on vise sa cible SEULEMENT si p >= seuil
      const p = a.probabilities[a.choice];
      const ok = a.choice !== "attendre" && p >= partie.seuil && m.vivante(a.choice);
      if (ok) partie.pistes.get(a.choice).pDecision = p;
      partie.cibleId = ok ? a.choice : null;
    } catch (e) {
      if (gen !== etatJEV.generation) return;
      etatJEV.err = t.err + e.message; await pause(PAUSE_ERREUR_MS);
    } finally { if (gen === etatJEV.generation) etatJEV.busy = false; }
  },
};
