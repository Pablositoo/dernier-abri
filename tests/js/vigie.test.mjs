// Tests du pilote distant (phase 6) : node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";

import { PAS_SIM } from "../../web/js/config.js";
import { appliquerDecision, avancerPartie, creerPartie, executerPartie } from "../../web/js/partie.js";
import { etatPourVigie } from "../../web/js/analysis/vigie.js";

test("message au noyau : observations seulement, jamais la nature réelle (vérité terrain cloisonnée)", () => {
  const p = creerPartie("jev", 3, .85);
  let ctx;
  for (let i = 0; i < 300; i++) ctx = avancerPartie(p, PAS_SIM, { langue: "fr" });
  const msg = etatPourVigie(p, ctx.tous, ctx.vis, "fr", 1), txt = JSON.stringify(msg);
  assert.ok(msg.observations.length > 0);
  assert.ok(!/nature|descIdx|desobeit|blesse_|"zombie"|"humain"/.test(txt), txt.slice(0, 200));
  assert.deepEqual(Object.keys(msg.observations[0]).sort(),
    ["arrete", "distance", "id", "reaction", "sommeAt", "texte", "vitesse", "x", "z"]);
});

test("un ordre de tir du noyau ne contourne jamais le verrou local : humain dans la ligne ⇒ tir annulé", () => {
  const p = creerPartie("jev", 1, .85), m = p.monde;
  m.prochainSpawn = 1e9; m.apparition(); m.apparition();
  const [z, h] = m.entites;
  Object.assign(z, { nature: "zombie", x: 0, z: -20, vitesse: 0 });
  Object.assign(h, { nature: "humain", x: 0, z: -10, vitesse: 0 });
  for (let i = 0; i < 120 && !m.stats.tirs_annules; i++) {
    const ctx = avancerPartie(p, PAS_SIM);
    appliquerDecision(p, { cible: z.id, pistes: { [z.id]: { statut: "zombie" } } });   // le noyau insiste
    executerPartie(p, PAS_SIM, ctx);
  }
  assert.ok(m.stats.tirs_annules > 0);
  assert.equal(m.stats.tirs, 0);
  assert.equal(h.vivant, true);
});

test("décision appliquée dans l'ordre du protocole ; cible morte ignorée ; pas de recharge avec une cible", () => {
  const p = creerPartie("jev", 1, .85), m = p.monde;
  avancerPartie(p, PAS_SIM);
  const id = m.entites[0].id;
  m.mun = 2;
  appliquerDecision(p, { cible: id, recharger: true, sommer: true, bloques: [id] });
  assert.equal(p.cibleId, id); assert.equal(m.mun, 2, "pas de recharge pendant qu'on vise");
  assert.equal(m.stats.sommations, 1); assert.equal(m.stats.tirs_bloques, 1); assert.equal(p.pistes.get(id).bloque, true);
  m.entites[0].vivant = false;
  appliquerDecision(p, { cible: id });
  assert.equal(p.cibleId, null);
});
