// Parité phase 6 : la même partie jouée (1) par la v5 JavaScript locale et (2) pilotée par le noyau Python « vigie »
// via WebSocket doit donner EXACTEMENT les mêmes résultats (même graine, mêmes réponses JEV du cache).
//
//   python3 server.py --no-browser --port 8766 &        (puis)
//   node tests/vigie_parite.mjs --port 8766 --parties 10 --langue en
//
// Le serveur répond depuis cache_jev.json (aucun appel réel si le cache est complet).
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";

import { PAS_SIM } from "../web/js/config.js";
import { appliquerDecision, avancerPartie, creerPartie, executerPartie } from "../web/js/partie.js";
import { etatPourVigie } from "../web/js/analysis/vigie.js";
import { MODELE_PAR_DEFAUT } from "./bench_config.mjs";
import { analyseurDiffere, chargerCache, jouerPartie, repondreCache } from "./bench_lib.mjs";

const { values: o } = parseArgs({ options: {
  port: { type: "string", default: "8766" }, parties: { type: "string", default: "5" }, graine: { type: "string", default: "1" },
  langue: { type: "string", default: "en" }, latence: { type: "string", default: "0.25" }, desobeissance: { type: "string" },
} });
const base = `localhost:${o.port}`, latence = +o.latence, langue = o.langue;
const monde = o.desobeissance == null ? {} : { desobeissance: +o.desobeissance };

async function jeton() {
  const html = await (await fetch(`http://${base}/`)).text();
  return html.match(/name="jeton-session" content="([^"]+)"/)[1];
}

// une connexion = une partie ; requête/réponse strictement alternées (pas à pas, reproductible)
async function connecter(j) {
  const ws = new WebSocket(`ws://${base}/vigie`), file = [];
  let attente = null;
  ws.onmessage = ev => { const m = JSON.parse(ev.data); attente ? (attente(m), attente = null) : file.push(m); };
  const suivant = () => file.length ? Promise.resolve(file.shift()) : new Promise(r => attente = r);
  await new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = ko; });
  ws.send(JSON.stringify({ type: "bonjour", jeton: j, simulation: { latence } }));
  const pret = await suivant();
  if (pret.type !== "pret") throw new Error("pas de « pret » : " + JSON.stringify(pret));
  return { rpc: msg => { ws.send(JSON.stringify(msg)); return suivant(); }, fermer: () => ws.close(), calibration: pret.calibration };
}

export async function jouerVigie(graine, j) {
  const p = creerPartie("jev", graine, .85, { politique: "v5", monde }), c = await connecter(j);
  let tick = 0, derive = null, erreur = "";
  while (!p.monde.fini) {
    const ctx = avancerPartie(p, PAS_SIM, { langue });
    const d = await c.rpc(etatPourVigie(p, ctx.tous, ctx.vis, langue, ++tick));
    if (d.type !== "decision") throw new Error(JSON.stringify(d));
    if (d.erreur) erreur = d.erreur;
    derive ??= d.derive;
    appliquerDecision(p, d);
    executerPartie(p, PAS_SIM, ctx, { langue });
  }
  c.fermer();
  return { t: p.monde.t, ...p.monde.stats, derive, erreur, calibration: c.calibration };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const j = await jeton(), repondre = repondreCache(chargerCache(fileURLToPath(new URL("../cache_jev.json", import.meta.url))), MODELE_PAR_DEFAUT);
  const CLES = ["zombies_tues", "humains_tues", "humains_sauves", "morsures", "tirs", "rates", "sommations", "tirs_bloques",
                "sommations_ciblees", "recharges_tactiques", "tirs_annules"];
  let ecarts = 0, total = 0;
  const t0 = performance.now();
  for (let g = +o.graine; g < +o.graine + +o.parties; g++) {
    const local = jouerPartie({ graine: g, langue, politique: "v5", analyseur: analyseurDiffere(repondre, latence), ...monde });
    const vigie = await jouerVigie(g, j);
    const diff = CLES.filter(k => local[k] !== vigie[k]);
    if (Math.abs(local.t - vigie.t) > 1e-9) diff.push("t");
    total += vigie.humains_tues;
    console.log(`graine ${g} : ${diff.length ? "❌ " + diff.map(k => `${k} ${local[k]}≠${vigie[k]}`).join(", ") : "✅ identique"}`
      + ` · zombies ${vigie.zombies_tues} · morsures ${vigie.morsures} · humains abattus ${vigie.humains_tues}`
      + (vigie.derive ? ` · dérive ${JSON.stringify(vigie.derive)}` : "") + (vigie.erreur ? ` · erreur ${vigie.erreur}` : ""));
    if (diff.length || vigie.derive || vigie.erreur || vigie.calibration !== MODELE_PAR_DEFAUT) ecarts++;
  }
  console.log(`\n${o.parties} parties (${langue}) en ${((performance.now() - t0) / 1000).toFixed(1)} s · ${ecarts} écart(s) · ${total} humain(s) abattu(s)`);
  process.exit(ecarts || total ? 1 : 0);
}
