// Tests de la politique v3 (fusion bayésienne + SPRT + cinématique + 2e sommation) : node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { FUSION } from "../../web/js/config.js";
import { creerRng } from "../../web/js/sim/rng.js";
import { Monde } from "../../web/js/sim/monde.js";
import { nouvellePiste } from "../../web/js/policy/regles.js";
import { suivreCinematique } from "../../web/js/analysis/cinematique.js";
import { fusionner, logit, preuveCinematique } from "../../web/js/analysis/fusion.js";
import { SEUIL_A, SEUIL_B, aResommer, eligiblesV3, statutSPRT } from "../../web/js/policy/sprt.js";
import { chargerCache, cleCache, toutesLesRequetes } from "../bench_lib.mjs";

const BOUGE = { arret: false }, ARRET = { arret: true }, FLOU = { arret: null };
const piste = o => Object.assign(nouvellePiste(), o);

test("seuils de Wald : A = ln((1-β)/α), B = ln(β/(1-α))", () => {
  assert.ok(Math.abs(SEUIL_A - Math.log(0.95 / 0.005)) < 1e-12);
  assert.ok(Math.abs(SEUIL_B - Math.log(0.05 / 0.995)) < 1e-12);
});

test("cinématique : continuer = preuve zombie, s'arrêter = preuve humain, ambigu = rien", () => {
  assert.ok(preuveCinematique([BOUGE]) > 2.9);
  assert.ok(preuveCinematique([ARRET]) < -3.5);
  assert.equal(preuveCinematique([FLOU]), 0);
  // désobéissance persistante : la 2e prouve moins que la 1re
  const premiere = preuveCinematique([BOUGE]), seconde = preuveCinematique([BOUGE, BOUGE]) - premiere;
  assert.ok(seconde > 0 && seconde < premiere);
});

test("mesure : fenêtre [sommation + 0,5 s ; + 2,0 s], arrêté si < 0,2 m, continue si > 0,5 m", () => {
  const p = nouvellePiste(), o = { sommeAt: 10, x: 0, z: -30 };
  for (let t = 10; t <= 12.1; t += 0.05) suivreCinematique(p, { ...o, z: -30 + (t - 10) * 1.2 }, t);   // zombie lent
  assert.equal(p.mesures.length, 1); assert.equal(p.mesures[0].arret, false);
  const h = nouvellePiste();
  for (let t = 10; t <= 12.1; t += 0.05) suivreCinematique(h, o, t);                                  // humain arrêté
  assert.equal(h.mesures[0].arret, true);
});

test("SPRT : JEV seul ne suffit jamais à tirer (il faut une 2e source)", () => {
  const p = piste({ pZ: 0.99, incoh: 0, lueAvecReaction: true });
  fusionner(p);
  assert.equal(statutSPRT(p), "incertain");
});

test("le zombie blessé EN (p = 0,835) : incertain après 1 mesure → 2e sommation → zombie", () => {
  const p = piste({ pZ: 0.835, incoh: 0.07, lueAvecReaction: true, mesures: [{ ...BOUGE }] });
  fusionner(p); p.statut = statutSPRT(p);
  assert.equal(p.statut, "incertain");
  const c = { id: "t1", distance: 30, arrete: false };
  assert.deepEqual(aResommer([c], new Map([["t1", p]])), ["t1"]);
  p.mesures.push({ ...BOUGE }); fusionner(p); p.statut = statutSPRT(p);
  assert.equal(p.statut, "zombie");
  assert.equal(eligiblesV3([{ ...c, distance: 25 }], new Map([["t1", p]])).length, 1);
});

test("règles v3 : concordance obligatoire (JEV ET mouvement), R4 mains en l'air", () => {
  const ok = { pZ: 0.97, incoh: 0, lueAvecReaction: true, mesures: [{ ...BOUGE }, { ...BOUGE }] };
  const elig = (o, c = {}) => { const p = piste(o); fusionner(p); p.statut = statutSPRT(p);
    return eligiblesV3([{ id: "t1", distance: 20, arrete: false, ...c }], new Map([["t1", p]])).length; };
  assert.equal(elig(ok), 1);
  assert.equal(elig({ ...ok, incoh: 0.3 }), 0, "JEV incohérent");
  assert.equal(elig({ ...ok, lueAvecReaction: false }), 0, "R3");
  assert.equal(elig(ok, { arrete: true }), 0, "R4");
});

test("monde : un humain désobéissant ne s'arrête pas à la 1re sommation ; la 2e sommation est ciblée", () => {
  const m = new Monde(creerRng(1), { desobeissance: 1 });
  m.apparition();
  const e = m.entites[0];
  Object.assign(e, { nature: "humain", desobeit: true, obeitSecond: true, z: -30 });
  m.sommer(); assert.equal(e.sommations, 1);
  for (let i = 0; i < 60; i++) m.pas(1 / 60);
  assert.equal(e.arrete, false);
  m.sommerCibles([e.id]); assert.equal(e.sommations, 2); assert.equal(m.stats.sommations_ciblees, 1);
  for (let i = 0; i < 60; i++) m.pas(1 / 60);
  assert.equal(e.arrete, true);
  m.sommerCibles([e.id]); assert.equal(e.sommations, 2, "pas de 3e sommation");
});

// Preuve de sécurité sur les VRAIES réponses JEV : pour chaque fiche humaine (réaction normale ou désobéissante),
// même dans le pire cas cinématique (l'humain continue aux 2 sommations), L reste sous le seuil de tir.
const CACHE = fileURLToPath(new URL("../../cache_jev.json", import.meta.url));   // chemin avec espaces
test("sécurité (pire cas, vraies réponses JEV) : aucun humain ne peut atteindre le seuil de tir", { skip: !existsSync(CACHE) && "cache_jev.json absent" }, () => {
  const E = chargerCache(CACHE), pire = preuveCinematique([BOUGE, BOUGE]);
  let marge = Infinity, fichePire = "";
  for (const req of toutesLesRequetes())
    for (const nz of Object.keys(req.questions).filter(n => n.startsWith("z_") && /humain_\d+_[rd]$/.test(n) && !n.includes("zombie"))) {
      const id = nz.slice(2), z = E[cleCache("jev-1.13.0", req.state, req.questions[nz])].reponse.noul;
      const h = E[cleCache("jev-1.13.0", req.state, req.questions["h_" + id])].reponse.noul;
      const L = logit(FUSION.prior) + logit((z + 1 - h) / 2) + pire;
      if (SEUIL_A - L < marge) { marge = SEUIL_A - L; fichePire = `${req.state.langue} ${id}`; }
    }
  console.log(`   marge de sécurité minimale : ${marge.toFixed(2)} (fiche ${fichePire})`);
  assert.ok(marge > 0, `un humain pourrait être abattu : ${fichePire}`);
});
