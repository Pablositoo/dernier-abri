// Tests des modules JS purs (sans Three.js ni DOM) : node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";

import { creerRng } from "../../web/js/sim/rng.js";
import { PAS_SIM, SEUIL_DEFAUT } from "../../web/js/config.js";
import { creerPartie, pasPartie } from "../../web/js/partie.js";
import { nouvellePiste, statut, eligibles, ligneDegagee, choisirCible } from "../../web/js/policy/regles.js";
import { botNaif } from "../../web/js/policy/bot.js";

// ---------- RNG ----------
test("RNG : même graine ⇒ même suite, graines différentes ⇒ suites différentes", () => {
  const a = creerRng(42), b = creerRng(42), c = creerRng(43);
  const sa = Array.from({ length: 100 }, a.suivant), sb = Array.from({ length: 100 }, b.suivant);
  assert.deepEqual(sa, sb);
  assert.notDeepEqual(sa, Array.from({ length: 100 }, c.suivant));
  assert.ok(sa.every(x => x >= 0 && x < 1));
});

// ---------- Politique ----------
const piste = o => ({ ...nouvellePiste(), ...o });
const obs = o => ({ id: "t1", desc: "", reaction: null, distance: 20, x: 0, z: -20, vitesse: 1.5, arrete: false, sommeAt: 0, ...o });
const sure = { pZ: .97, incoh: 0, lueAvecReaction: true, statut: "zombie" };

test("statut : seuil, incohérence, zone grise", () => {
  assert.equal(statut(piste({ pZ: .9, incoh: 0 }), .85), "zombie");
  assert.equal(statut(piste({ pZ: .84, incoh: 0 }), .85), "incertain");   // cas réel des morsures de blessés
  assert.equal(statut(piste({ pZ: .05, incoh: 0 }), .85), "humain");
  assert.equal(statut(piste({ pZ: .97, incoh: .3 }), .85), "incertain");  // les 2 questions se contredisent
  assert.equal(statut(piste({}), .85), "analyse");
});

test("R1–R5 : chaque règle seule bloque le tir", () => {
  const ok = [obs()], pistes = m => new Map([["t1", piste({ ...sure, ...m })]]);
  assert.equal(eligibles(ok, pistes({})).length, 1);
  assert.equal(eligibles(ok, pistes({ statut: "incertain" })).length, 0, "R1");
  assert.equal(eligibles(ok, pistes({ incoh: .2 })).length, 0, "R2");
  assert.equal(eligibles(ok, pistes({ lueAvecReaction: false })).length, 0, "R3");
  assert.equal(eligibles([obs({ arrete: true })], pistes({})).length, 0, "R4");
  assert.equal(eligibles([obs({ distance: 40, z: -40 })], pistes({})).length, 0, "R5");
});

test("ligne de tir : un survivant devant la cible bloque, un zombie confirmé non", () => {
  const cible = obs({ id: "z", z: -30, distance: 30 }), devant = obs({ id: "h", x: .3, z: -15, distance: 15 });
  const p = statutH => new Map([["z", piste(sure)], ["h", piste({ statut: statutH })]]);
  assert.equal(ligneDegagee(cible, [cible, devant], p("humain")), false);
  assert.equal(ligneDegagee(cible, [cible, devant], p("incertain")), false);
  assert.equal(ligneDegagee(cible, [cible, devant], p("zombie")), true);
  assert.equal(ligneDegagee(cible, [cible, obs({ id: "h", x: 5, z: -15 })], p("humain")), true);   // à côté
  const { cible: c, bloques } = choisirCible([cible], [cible, devant], p("humain"));
  assert.equal(c, null); assert.deepEqual(bloques, ["z"]);
});

test("bot naïf : épargne celui qui appelle à l'aide", () => {
  assert.equal(botNaif([obs({ desc: "court vers l'abri en criant « aidez-moi ! »" })]), null);
  assert.equal(botNaif([obs({ desc: "runs toward the shelter shouting \"help me!\"" })]), null);
  assert.equal(botNaif([obs({ desc: "grunts" })]).id, "t1");
});

// ---------- Simulation headless ----------
function jouer(mode, graine, analyseur = null) {
  const p = creerPartie(mode, graine, SEUIL_DEFAUT[mode] ?? .85);
  while (!p.monde.fini) pasPartie(p, PAS_SIM, { analyseur, langue: "fr" });
  return { t: p.monde.t, ...p.monde.stats };
}

test("?seed=42 : la même partie (bot) se rejoue à l'identique", () => {
  const a = jouer("regle", 42), b = jouer("regle", 42);
  assert.deepEqual(a, b);
  assert.notDeepEqual(a, jouer("regle", 43));
  assert.ok(a.tirs > 0 && a.zombies_tues > 0);
});

// Analyseur synchrone à mots-clés (comme server/faux_jev.py) : lit seulement les observations
const analyseurMotsCles = {
  occupe: false,
  classer(cibles, pistes) {
    for (const c of cibles) {
      const p = pistes.get(c.id), r = c.reaction ?? "";
      p.besoinAnalyse = false;
      p.pZ = /lève|vivant/.test(r) ? .03 : /ne réagit pas|sans s'arrêter/.test(r) ? .96 : .5;
      p.incoh = 0; p.lectures++;
      if (c.reaction) p.lueAvecReaction = true; else p.pAvant = p.pZ;
    }
  },
};

test("protocole v2 headless : reproductible et 0 humain abattu sur 20 graines", () => {
  assert.deepEqual(jouer("jev", 7, analyseurMotsCles), jouer("jev", 7, analyseurMotsCles));
  for (let g = 1; g <= 20; g++) {
    const s = jouer("jev", g, analyseurMotsCles);
    assert.equal(s.humains_tues, 0, `graine ${g}`);
    assert.ok(s.zombies_tues > 0 && s.sommations > 0, `graine ${g}`);
  }
});
