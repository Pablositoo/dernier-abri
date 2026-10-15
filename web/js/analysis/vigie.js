// Pilote distant (phase 6) : le jeu envoie ses observations au noyau Python (WebSocket /vigie) et applique sa décision.
// Le jeu reste maître de l'exécution : la visée et le verrou de ligne de tir au moment du tir restent locaux (partie.js).
// La nature réelle des silhouettes ne part jamais : seulement ce qu'observe perception/observer.js.
import { TXT } from "../ui/i18n.js";

// Message « etat » : mêmes textes que les questions JEV du navigateur (questions.js) ⇒ mêmes clés de cache
export function etatPourVigie(p, tous, vis, langue, tick) {
  const t = TXT[langue], m = p.monde;
  return {
    type: "etat", tick, t: m.t, langue,
    jev: { contexte: t.contexte, qZ: t.qZ, qH: t.qH },
    monde: { mun: m.mun, rechargeFin: m.rechargeFin, derniereSommation: m.derniereSommation },
    observations: tous.map(o => ({ id: o.id, texte: t.fiche(o, o.reaction), reaction: !!o.reaction, distance: o.distance,
                                   x: o.x, z: o.z, vitesse: o.vitesse, arrete: o.arrete, sommeAt: o.sommeAt })),
    visibles: vis.map(o => o.id),
  };
}

// Navigateur : une décision en vol au plus ; la dernière reçue est appliquée au pas suivant (non bloquant)
export function creerPiloteVigie({ jeton, surEtat = () => {} }) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/vigie`);
  const pilote = { pret: false, enAttente: false, decision: null, erreur: "", calibration: null, tick: 0,
    envoyer(msg) { if (pilote.pret && !pilote.enAttente) { pilote.enAttente = true; ws.send(JSON.stringify({ ...msg, tick: ++pilote.tick })); } },
    prendre() { const d = pilote.decision; pilote.decision = null; return d; },
    fermer() { ws.close(); } };
  ws.onopen = () => ws.send(JSON.stringify({ type: "bonjour", jeton }));
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "pret") { pilote.pret = true; pilote.calibration = msg.calibration; }
    if (msg.type === "decision") { pilote.decision = msg; pilote.enAttente = false; pilote.erreur = msg.erreur || ""; }
    surEtat(pilote);
  };
  ws.onclose = ev => { pilote.pret = false; pilote.erreur = `vigie déconnecté (${ev.code})`; surEtat(pilote); };
  return pilote;
}
