// Tests de la politique v4 (ordonnancement par coût) : node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";

import { PAS_SIM } from "../../web/js/config.js";
import { creerRng } from "../../web/js/sim/rng.js";
import { Monde } from "../../web/js/sim/monde.js";
import { creerPartie, pasPartie } from "../../web/js/partie.js";
import { nouvellePiste } from "../../web/js/policy/regles.js";
import { fusionner } from "../../web/js/analysis/fusion.js";
import { eligiblesV3, statutSPRT } from "../../web/js/policy/sprt.js";
import { doitRecharger, eligiblesV4 } from "../../web/js/policy/ordonnancement.js";

// zombie confirmé (SPRT + concordance + réaction lue) à `d` m, droit devant
function scene(d, autres = []) {
  const p = Object.assign(nouvellePiste(), { pZ: .97, incoh: 0, lueAvecReaction: true, mesures: [{ arret: false }] });
  fusionner(p); p.statut = statutSPRT(p);
  const z = { id: "z", x: 0, z: -d, distance: d, arrete: false };
  const pistes = new Map([["z", p], ...autres.map(o => [o.id, Object.assign(nouvellePiste(), { statut: o.statut })])]);
  return { vis: [z], tous: [z, ...autres], pistes };
}

test("v4 : tir d'opportunité à 40 m si la ligne est libre (v3 attendait 30 m)", () => {
  const { vis, tous, pistes } = scene(40);
  assert.equal(pistes.get("z").statut, "zombie");
  assert.equal(eligiblesV3(vis, pistes).length, 0);
  assert.equal(eligiblesV4(vis, pistes, tous).length, 1);
});

test("v4 : pas d'opportunité si un humain est dans la ligne, ni au-delà de 45 m", () => {
  const h = { id: "h", x: .2, z: -20, distance: 20, statut: "humain" };
  const elig = ({ vis, tous, pistes }) => eligiblesV4(vis, pistes, tous).length;
  assert.equal(elig(scene(40, [h])), 0);
  assert.equal(elig(scene(46)), 0);
});

test("v4 : une cible non confirmée n'est jamais tirée, même ligne libre", () => {
  const { vis, tous, pistes } = scene(40);
  pistes.get("z").statut = "incertain";
  assert.equal(eligiblesV4(vis, pistes, tous).length, 0);
});

test("rechargement tactique : seulement chargeur presque vide et aucune cible confirmée à portée", () => {
  const m = new Monde(creerRng(1)), vide = new Map();
  m.mun = 2; assert.equal(doitRecharger(m, [], vide), true);
  m.mun = 3; assert.equal(doitRecharger(m, [], vide), false);
  m.mun = 2; const { vis, pistes } = scene(40); assert.equal(doitRecharger(m, vis, pistes), false);
  m.recharger(); assert.equal(m.mun, 6); assert.ok(m.rechargeFin > m.t); assert.equal(m.peutTirer(), false);
  assert.equal(m.stats.recharges_tactiques, 1);
});

test("verrou au moment du tir : cible choisie mais humain dans la ligne ⇒ tir annulé", () => {
  // sans analyseur, la politique ne tourne pas : on force une cible pour tester le verrou seul
  const p = creerPartie("jev", 1, .85, { politique: "v4" }), m = p.monde;
  m.prochainSpawn = 1e9;
  m.apparition(); m.apparition();
  const [z, h] = m.entites;
  Object.assign(z, { nature: "zombie", x: 0, z: -20, vitesse: 0 });
  Object.assign(h, { nature: "humain", x: 0, z: -10, vitesse: 0, desobeit: false });
  p.cibleId = z.id;
  for (let i = 0; i < 120 && !m.stats.tirs_annules; i++) { pasPartie(p, PAS_SIM, { analyseur: null }); p.cibleId = z.id; }
  assert.ok(m.stats.tirs_annules > 0);
  assert.equal(m.stats.tirs, 0);
  assert.equal(h.vivant, true);
});
