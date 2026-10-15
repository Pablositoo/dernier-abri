// Briques du simulateur headless : analyseurs sans réseau, liste des questions possibles, clé de cache.
import { createHash } from "node:crypto";
import { readFileSync, existsSync } from "node:fs";

import { PAS_SIM, SEUIL_DEFAUT } from "../web/js/config.js";
import { creerRng } from "../web/js/sim/rng.js";
import { creerPartie, pasPartie } from "../web/js/partie.js";
import { DESC_I18N, REACTION_DESOBEIT_I18N, REACTION_I18N } from "../web/js/perception/descriptions.js";
import { appliquerClassement, requeteClassement } from "../web/js/analysis/questions.js";

// ---------- Clé de cache : identique à server/cache_jev.py ----------
const canon = v => Array.isArray(v) ? `[${v.map(canon).join(",")}]`
  : v && typeof v === "object" ? `{${Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canon(v[k])).join(",")}}`
  : JSON.stringify(v);
export const cleCache = (modele, state, question) =>
  createHash("sha256").update(canon({ m: modele, q: question, s: state })).digest("hex");

// ---------- Toutes les requêtes que le protocole peut envoyer (100 questions) ----------
export function toutesLesRequetes(langues = ["fr", "en"], parLot = 5) {
  const requetes = [];
  for (const langue of langues) {
    const obs = [];
    for (const [nature, descs] of Object.entries(DESC_I18N[langue]))
      descs.forEach((desc, i) => {
        const reactions = { "0": null, r: REACTION_I18N[langue][nature], d: REACTION_DESOBEIT_I18N[langue][nature] };
        for (const [k, reaction] of Object.entries(reactions)) if (k === "0" || reaction) obs.push({ id: `${nature}_${i}_${k}`, desc, reaction });
      });
    for (let i = 0; i < obs.length; i += parLot) requetes.push(requeteClassement(obs.slice(i, i + parLot), langue));
  }
  return requetes;
}

// ---------- Analyseur différé : la réponse arrive après `latence` secondes de temps simulé ----------
export function analyseurDiffere(repondre, latence) {
  let attente = null, t = 0;
  return {
    appels: 0, questions: 0,
    get occupe() { return attente !== null; },
    tic(tc) {
      t = tc;
      if (attente && t >= attente.fin) { const a = attente; attente = null; appliquerClassement(a.cibles, a.pistes, a.answers); }
    },
    classer(cibles, pistes, langue) {
      cibles.forEach(c => pistes.get(c.id).besoinAnalyse = false);
      const req = requeteClassement(cibles, langue);
      this.appels++; this.questions += Object.keys(req.questions).length;
      attente = { fin: t + latence, cibles, pistes, answers: repondre(req) };
    },
    choisir() { throw new Error("le mode v1 (Choice) n'est pas simulé en headless"); },
  };
}

// ---------- Faux JEV : port de server/faux_jev.py (mots-clés + bruit ±0,05, RNG seedé) ----------
const ZOMBIE_MOTS = ["grogne", "gémissement", "mâchoire", "ne répond pas", "sans parler", "grunts", "groaning", "jaw", "doesn't respond", "without speaking"];
const HUMAIN_MOTS = ["aidez-moi", "ne tirez pas", "main ouverte", "prénom", "signes", "help me", "don't shoot", "open hand", "by name", "waves"];
const REAC_HUMAIN = ["lève", "vivant", "raises", "alive"];
const REAC_ZOMBIE = ["ne réagit pas", "sans s'arrêter", "does not react", "without stopping"];
const contient = (txt, mots) => mots.filter(m => txt.includes(m)).length;

export function repondreFaux(rng) {
  return req => {
    const answers = {};
    for (const [nom, q] of Object.entries(req.questions)) {
      const txt = q.instructions, fiche = txt.split(" Cette cible")[0].split(" This target")[0];
      const reaction = fiche.split("Réaction à la sommation :").at(-1).split("Reaction to the warning:").at(-1);
      let pz;
      if (contient(reaction, REAC_HUMAIN)) pz = 0.03;
      else if (contient(reaction, REAC_ZOMBIE)) pz = 0.96;
      else { const z = contient(fiche, ZOMBIE_MOTS), h = contient(fiche, HUMAIN_MOTS); pz = z === h ? 0.5 : z > h ? 0.85 : 0.15; }
      pz = Math.min(0.99, Math.max(0.01, pz + (rng.suivant() * 0.1 - 0.05)));
      answers[nom] = { type: "noul", noul: /est un zombie|is a zombie/.test(txt) ? pz : 1 - pz };
    }
    return answers;
  };
}

// ---------- Rejeu du cache des vraies réponses JEV (cache_jev.json) ----------
export function chargerCache(chemin) {
  if (!existsSync(chemin)) return {};
  return JSON.parse(readFileSync(chemin, "utf8")).entrees ?? {};
}

export function questionsManquantes(entrees, modele, langues) {
  const manquantes = [];
  for (const req of toutesLesRequetes(langues))
    for (const q of Object.values(req.questions))
      if (!entrees[cleCache(modele, req.state, q)]) manquantes.push(q.instructions);
  return manquantes;
}

export function repondreCache(entrees, modele) {
  const memo = new Map();
  return req => {
    const answers = {};
    for (const [nom, q] of Object.entries(req.questions)) {
      const k = q.instructions + "␟" + req.state.langue;
      if (!memo.has(k)) memo.set(k, entrees[cleCache(modele, req.state, q)]);
      const e = memo.get(k);
      if (!e) throw new Error(`question absente du cache : ${q.instructions}`);
      answers[nom] = e.reponse;
    }
    return answers;
  };
}

// ---------- Une partie headless complète ----------
const BLESSES = new Set(["blesse_zombie", "blesse_humain"]);

export function jouerPartie({ mode = "jev", graine, seuil = SEUIL_DEFAUT[mode] ?? .85, langue = "en", analyseur = null,
                              politique, desobeissance }) {
  const p = creerPartie(mode, graine, seuil, { politique, monde: desobeissance == null ? {} : { desobeissance } });
  const detail = { morsures_blesses: 0, morsures_valides: 0, humains_blesses_tues: 0, humains_desobeissants_tues: 0,
                   humains_desobeissants: 0, tirs_apres_2e_sommation: 0 };
  while (!p.monde.fini)
    for (const ev of pasPartie(p, PAS_SIM, { analyseur, langue })) {
      if (ev.type === "arrivee" && ev.issue === "morsure") detail[BLESSES.has(ev.e.nature) ? "morsures_blesses" : "morsures_valides"]++;
      if (ev.type === "apparition" && ev.e.desobeit) detail.humains_desobeissants++;
      if (ev.type === "tir" && ev.touche && ev.e.nature === "blesse_humain") detail.humains_blesses_tues++;
      if (ev.type === "tir" && ev.touche && ev.e.desobeit) detail.humains_desobeissants_tues++;
      if (ev.type === "tir" && ev.touche && ev.e.sommations >= 2) detail.tirs_apres_2e_sommation++;
    }
  return { graine, t: p.monde.t, ...p.monde.stats, ...detail };
}

export { creerRng };
