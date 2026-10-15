// Tests de la politique v5 (lectures JEV calibrées, phase 5) : node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { FUSION, INCOH_MAX, PAS_SIM } from "../../web/js/config.js";
import { creerPartie, pasPartie } from "../../web/js/partie.js";
import { logit, preuveCinematique } from "../../web/js/analysis/fusion.js";
import { CALIBRATION_JEV } from "../../web/js/analysis/calibration_jev.js";
import { creerCalibrateur, interpoler } from "../../web/js/analysis/calibration.js";
import { SEUIL_A } from "../../web/js/policy/sprt.js";
import { MODELE_PAR_DEFAUT } from "../bench_config.mjs";
import { chargerCache, cleCache, toutesLesRequetes } from "../bench_lib.mjs";

const BOUGE = { arret: false };

test("interpolation isotonique : linéaire entre les points, bornée aux extrémités (comme sklearn)", () => {
  const x = [0.1, 0.5, 0.9], y = [0.02, 0.2, 0.98];
  assert.equal(interpoler(0, x, y), 0.02);
  assert.equal(interpoler(1, x, y), 0.98);
  assert.ok(Math.abs(interpoler(0.3, x, y) - 0.11) < 1e-12);
  assert.equal(interpoler(0.5, x, y), 0.2);
});

test("calibrateur Platt : preuve = a·logit(p) + b − logit(taux de zombies), bornée comme le brut", () => {
  const c = creerCalibrateur({ modele: "m", methode: "platt", a: 1.5, b: -0.5, tauxZombies: 0.6 });
  const p = 0.8, attendu = 1.5 * Math.log(4) - 0.5 - Math.log(1.5);
  assert.ok(Math.abs(c.llr(p) - attendu) < 1e-9);
  assert.ok(c.llr(0.999999) <= logit(1) - logit(0.6) + 1e-12, "jamais plus que p = 0,99");
});

test("calibrateur table (benchmark hors échantillon) : lecture inconnue ⇒ erreur, jamais de valeur inventée", () => {
  const c = creerCalibrateur({ modele: "m", methode: "table", tauxZombies: .5, table: [{ pZ: .9, incoh: .02, pCal: .95 }] });
  assert.ok(Math.abs(c.llr(.9, .02) - logit(.95)) < 1e-12);
  assert.throws(() => c.llr(.91, .02), /absente/);
});

test("la calibration exportée vise le modèle figé du projet", () => {
  assert.equal(CALIBRATION_JEV.modele, MODELE_PAR_DEFAUT);
  assert.ok(["platt", "isotonique"].includes(CALIBRATION_JEV.methode));
});

// ---------- Sur les VRAIES réponses JEV (cache) ----------
const CACHE = fileURLToPath(new URL("../../cache_jev.json", import.meta.url));
function fichesApresReaction() {
  const E = chargerCache(CACHE), fiches = [];
  for (const req of toutesLesRequetes())
    for (const nz of Object.keys(req.questions).filter(n => n.startsWith("z_") && /_[rd]$/.test(n))) {
      const id = nz.slice(2), lire = n => E[cleCache(MODELE_PAR_DEFAUT, req.state, req.questions[n])].reponse.noul;
      const z = lire(nz), h = lire("h_" + id), pZ = (z + 1 - h) / 2, incoh = Math.abs(z - (1 - h));
      fiches.push({ nom: `${req.state.langue} ${id}`, zombie: /^(blesse_)?zombie/.test(id), pZ, incoh });
    }
  return fiches;
}

test("v5 sécurité (pire cas, vraies réponses JEV) : marge ≥ celle de JEV brut", { skip: !existsSync(CACHE) && "cache_jev.json absent" }, () => {
  const cal = creerCalibrateur(), pire = preuveCinematique([BOUGE, BOUGE]);
  let brute = Infinity, calibree = Infinity, fiche = "";
  for (const f of fichesApresReaction().filter(f => !f.zombie)) {
    brute = Math.min(brute, SEUIL_A - (logit(FUSION.prior) + logit(f.pZ) + pire));
    const m = SEUIL_A - (logit(FUSION.prior) + cal.llr(f.pZ, f.incoh) + pire);
    if (m < calibree) { calibree = m; fiche = f.nom; }
  }
  console.log(`   marge pire cas : brute ${brute.toFixed(2)} → calibrée ${calibree.toFixed(2)} (fiche ${fiche})`);
  assert.ok(calibree > 0, `un humain pourrait être abattu : ${fiche}`);
  assert.ok(calibree >= brute);
});

test("v5 : chaque fiche zombie est confirmée en ≤ 2 sommations, jamais plus lentement qu'en brut", { skip: !existsSync(CACHE) && "cache_jev.json absent" }, () => {
  const cal = creerCalibrateur(), un = preuveCinematique([BOUGE]), deux = preuveCinematique([BOUGE, BOUGE]);
  const besoin = L => L + un >= SEUIL_A ? 1 : L + deux >= SEUIL_A ? 2 : Infinity;
  for (const f of fichesApresReaction().filter(f => f.zombie && f.incoh <= INCOH_MAX)) {
    const brut = besoin(logit(f.pZ)), calib = besoin(cal.llr(f.pZ, f.incoh));
    assert.ok(calib <= 2, `${f.nom} jamais confirmé`);
    assert.ok(calib <= brut, `${f.nom} : ${calib} sommations au lieu de ${brut}`);
  }
});

// ---------- Dérive : la calibration ne s'applique qu'à son modèle ----------
const analyseurFictif = modeleServi => ({ occupe: true, modeleServi, classer() {}, tic() {} });

test("dérive : modèle servi ≠ modèle de la calibration ⇒ calibration désactivée + événement, une seule fois", () => {
  const p = creerPartie("jev", 1, .85, { politique: "v5" });
  assert.ok(p.calibrateur);
  const evs = [];
  for (let i = 0; i < 5; i++) evs.push(...pasPartie(p, PAS_SIM, { analyseur: analyseurFictif("jev-9.9.9") }));
  assert.equal(p.calibrateur, null);
  assert.deepEqual(p.derive, { attendu: MODELE_PAR_DEFAUT, servi: "jev-9.9.9" });
  assert.equal(evs.filter(e => e.type === "derive").length, 1);
});

test("pas de dérive : même modèle ou modèle encore inconnu ⇒ calibration conservée ; v4 n'a pas de calibration", () => {
  for (const servi of [MODELE_PAR_DEFAUT, null]) {
    const p = creerPartie("jev", 1, .85, { politique: "v5" });
    for (let i = 0; i < 5; i++) pasPartie(p, PAS_SIM, { analyseur: analyseurFictif(servi) });
    assert.ok(p.calibrateur); assert.equal(p.derive, null);
  }
  assert.equal(creerPartie("jev", 1, .85, { politique: "v4" }).calibrateur, null);
});
