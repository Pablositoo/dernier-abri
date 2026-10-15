// Benchmark headless : N parties reproductibles, sans navigateur ni réseau.
//
//   node tests/bench.mjs --parties 500 --graine 1 --jev cache      # vraies réponses JEV (cache_jev.json)
//   node tests/bench.mjs --parties 500 --jev fake                  # faux JEV à mots-clés (gratuit, optimiste)
//   node tests/bench.mjs --mode regle                              # bot naïf (référence)
//   node tests/bench.mjs --lister-questions                        # requêtes possibles (utilisé par server/remplir_cache.py)
//
// Critère d'acceptation d'une politique (CLAUDE.md) : humains abattus = 0 sur 500 parties.
import { parseArgs } from "node:util";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { MODELE_PAR_DEFAUT } from "./bench_config.mjs";
import { analyseurDiffere, chargerCache, creerRng, jouerPartie, questionsManquantes, repondreCache, repondreFaux,
  toutesLesRequetes } from "./bench_lib.mjs";

const RACINE = join(dirname(fileURLToPath(import.meta.url)), "..");
const { values: o } = parseArgs({ options: {
  parties: { type: "string", default: "500" }, graine: { type: "string", default: "1" },
  mode: { type: "string", default: "jev" }, jev: { type: "string", default: "cache" },
  latence: { type: "string", default: "0.25" }, langue: { type: "string", default: "en" },
  seuil: { type: "string" }, modele: { type: "string", default: MODELE_PAR_DEFAUT },
  cache: { type: "string", default: join(RACINE, "cache_jev.json") }, json: { type: "string" },
  politique: { type: "string", default: "v4" }, desobeissance: { type: "string" },
  "lister-questions": { type: "boolean", default: false },
} });

if (o["lister-questions"]) {
  process.stdout.write(JSON.stringify(toutesLesRequetes()));
  process.exit(0);
}

const N = +o.parties, G0 = +o.graine, latence = +o.latence, langue = o.langue;
let fabrique = () => null;
if (o.mode === "jev") {
  if (o.jev === "cache") {
    const entrees = chargerCache(o.cache), manque = questionsManquantes(entrees, o.modele, [langue]);
    if (manque.length) {
      console.error(`❌ ${manque.length} question(s) absente(s) de ${o.cache} pour ${o.modele} (${langue}).`);
      console.error("   Remplis le cache (≈ 8 appels JEV, une seule fois) : python3 -m server.remplir_cache");
      process.exit(2);
    }
    const repondre = repondreCache(entrees, o.modele);
    fabrique = () => analyseurDiffere(repondre, latence);
  } else if (o.jev === "fake") {
    fabrique = g => analyseurDiffere(repondreFaux(creerRng(g ^ 0x9e3779b9)), latence);
  } else throw new Error(`--jev ${o.jev} inconnu (cache | fake)`);
}

// ---------- Parties ----------
const t0 = performance.now(), parties = [];
let appels = 0, questions = 0;
for (let g = G0; g < G0 + N; g++) {
  const analyseur = fabrique(g);
  parties.push(jouerPartie({ mode: o.mode, graine: g, langue, analyseur, politique: o.politique,
    ...(o.desobeissance != null ? { desobeissance: +o.desobeissance } : {}), ...(o.seuil ? { seuil: +o.seuil } : {}) }));
  appels += analyseur?.appels ?? 0; questions += analyseur?.questions ?? 0;
}
const duree = (performance.now() - t0) / 1000;

// ---------- Agrégats (moyenne ± IC 95 %) ----------
const resume = cle => {
  const v = parties.map(p => p[cle]), m = v.reduce((a, b) => a + b, 0) / v.length;
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, v.length - 1));
  return { moyenne: m, ic95: 1.96 * sd / Math.sqrt(v.length), total: v.reduce((a, b) => a + b, 0), max: Math.max(...v) };
};
const tirs = resume("tirs").total, rates = resume("rates").total;
const lignes = [
  ["humains_tues", "Humains abattus"], ["humains_blesses_tues", "  dont humains blessés"],
  ["humains_desobeissants_tues", "  dont désobéissants"], ["humains_desobeissants", "Humains désobéissants"], ["morsures", "Morsures"],
  ["morsures_blesses", "  dont zombies blessés"], ["morsures_valides", "  dont zombies valides"], ["zombies_tues", "Zombies tués"],
  ["humains_sauves", "Humains sauvés"], ["tirs", "Tirs"], ["tirs_bloques", "Tirs bloqués"], ["sommations", "Sommations"],
  ["sommations_ciblees", "2es sommations ciblées"], ["tirs_apres_2e_sommation", "Tués après 2e sommation"],
  ["recharges_tactiques", "Recharges tactiques"], ["tirs_annules", "Tirs annulés (verrou)"],
];
const stats = Object.fromEntries(lignes.map(([k]) => [k, resume(k)]));
const scores = parties.map(p => 10 * p.zombies_tues + 15 * p.humains_sauves - 50 * p.humains_tues - 20 * p.morsures);
const scoreMoy = scores.reduce((a, b) => a + b, 0) / N;

const monde = o.desobeissance != null ? `désobéissance ${o.desobeissance}` : "désobéissance par défaut";
console.log(`\n${N} parties · mode ${o.mode}${o.mode === "jev" ? ` · politique ${o.politique} · JEV ${o.jev} (${o.modele}, latence ${latence} s)` : ""} · ${monde} · langue ${langue} · graines ${G0}–${G0 + N - 1} · ${duree.toFixed(1)} s\n`);
console.log("Indicateur".padEnd(26) + "moy./partie".padStart(12) + "± IC95".padStart(9) + "total".padStart(8) + "max".padStart(6));
for (const [k, nom] of lignes) {
  const s = stats[k];
  console.log(nom.padEnd(26) + s.moyenne.toFixed(2).padStart(12) + s.ic95.toFixed(2).padStart(9) + String(s.total).padStart(8) + String(s.max).padStart(6));
}
console.log(`\nScore moyen ${scoreMoy.toFixed(1)} · précision ${tirs ? Math.round((1 - rates / tirs) * 100) : 0} % · parties avec ≥ 1 humain abattu : ${parties.filter(p => p.humains_tues > 0).length}`);
if (o.mode === "jev") console.log(`Requêtes JEV simulées : ${appels} (${(appels / N).toFixed(1)}/partie), ${questions} questions`);
const ok = stats.humains_tues.total === 0;
console.log(ok ? "✅ 0 humain abattu" : "❌ des humains ont été abattus");

if (o.json) writeFileSync(o.json, JSON.stringify({ options: o, duree, stats, score_moyen: scoreMoy, parties }, null, 1));
process.exit(ok || o.mode !== "jev" ? 0 : 1);
