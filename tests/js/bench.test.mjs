// Tests du simulateur headless : node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";

import { requeteClassement } from "../../web/js/analysis/questions.js";
import { nouvellePiste } from "../../web/js/policy/regles.js";
import { analyseurDiffere, cleCache, jouerPartie, repondreCache, repondreFaux, toutesLesRequetes, creerRng }
  from "../bench_lib.mjs";

test("questions JEV : ni id ni distance (même fiche ⇒ même question ⇒ cachable)", () => {
  const a = requeteClassement([{ id: "t1", desc: "grunts", reaction: null, distance: 12 }], "en");
  const b = requeteClassement([{ id: "t77", desc: "grunts", reaction: null, distance: 40 }], "en");
  assert.equal(a.questions.z_t1.instructions, b.questions.z_t77.instructions);
  assert.deepEqual(a.state, b.state);
  assert.ok(!a.questions.z_t1.instructions.includes("t1"));
});

test("toutes les requêtes possibles : 100 questions (10 descriptions × 2 états + 5 humains désobéissants, × 2 questions × 2 langues)", () => {
  const n = toutesLesRequetes().reduce((s, r) => s + Object.keys(r.questions).length, 0);
  assert.equal(n, 100);
});

test("analyseur différé : la réponse n'arrive qu'après la latence simulée", () => {
  const a = analyseurDiffere(() => ({ z_t1: { noul: .9 }, h_t1: { noul: .1 } }), 0.25);
  const pistes = new Map([["t1", nouvellePiste()]]);
  a.tic(10);
  a.classer([{ id: "t1", desc: "x", reaction: "y" }], pistes, "en");
  assert.equal(a.occupe, true); assert.equal(pistes.get("t1").besoinAnalyse, false);
  a.tic(10.2); assert.equal(pistes.get("t1").pZ, null);
  a.tic(10.25); assert.equal(a.occupe, false); assert.equal(pistes.get("t1").pZ, .9); assert.equal(pistes.get("t1").lueAvecReaction, true);
});

test("rejeu du cache : mêmes réponses que celles enregistrées, erreur claire si absente", () => {
  const req = toutesLesRequetes(["en"])[0], entrees = {};
  for (const q of Object.values(req.questions)) entrees[cleCache("m", req.state, q)] = { reponse: { type: "noul", noul: .42 } };
  const r = repondreCache(entrees, "m")(req);
  assert.ok(Object.values(r).every(x => x.noul === .42));
  assert.throws(() => repondreCache({}, "m")(req), /absente du cache/);
});

test("benchmark : une partie faux JEV est reproductible", () => {
  const jouer = () => jouerPartie({ graine: 5, analyseur: analyseurDiffere(repondreFaux(creerRng(5)), .25) });
  assert.deepEqual(jouer(), jouer());
});
