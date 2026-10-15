// Un pas de partie : monde → perception → analyse → politique → réponse.
// Sans Three.js ni DOM : le même code tourne dans le navigateur et dans le simulateur headless (Node).
import { creerRng } from "./sim/rng.js";
import { Monde } from "./sim/monde.js";
import { observerTous, visibles } from "./perception/observer.js";
import { nouvellePiste, majStatuts, doitSommer, choisirCible } from "./policy/regles.js";
import { botNaif } from "./policy/bot.js";
import { pointVise, orienter, relacher } from "./response/visee.js";

export const AUTEURS = { jev: "JEV v2", jev1: "JEV v1", regle: "BOT", manuel: "TOI" };

export function creerPartie(mode, graine, seuil) {
  return { mode, graine, seuil, monde: new Monde(creerRng(graine)), pistes: new Map(), cibleId: null,
           tourelle: { yaw: 0, pitch: 0 } };
}

// Événements du monde → pistes d'analyse ; la piste est jointe aux événements que le journal doit enregistrer
function recolter(p, sortie) {
  for (const ev of p.monde.vider()) {
    const id = ev.e?.id;
    if (ev.type === "apparition") p.pistes.set(id, nouvellePiste());
    if (ev.type === "reaction") p.pistes.get(id).besoinAnalyse = true;   // nouvelle observation → reclasser
    if (id) ev.piste = p.pistes.get(id);
    if (ev.type === "retrait") p.pistes.delete(id);
    sortie.push(ev);
  }
}

// ---- v2 : JEV CLASSE, le CODE décide (règles explicites) ----
function protocole(p, tous, vis, analyseur, langue) {
  const m = p.monde;
  majStatuts(p.pistes, p.seuil);                          // le seuil peut changer en direct (↑/↓)
  const aAnalyser = vis.filter(c => p.pistes.get(c.id).besoinAnalyse);
  if (aAnalyser.length && !analyseur.occupe) analyseur.classer(aAnalyser, p.pistes, langue);
  if (doitSommer(m.t, m.derniereSommation, tous, p.pistes)) m.sommer();
  const { cible, bloques } = choisirCible(vis, tous, p.pistes);
  for (const id of bloques) { p.pistes.get(id).bloque = true; m.stats.tirs_bloques++; m.emettre("bloque", { id }); }
  p.cibleId = cible?.id ?? null;
}

/**
 * Avance la partie d'un pas de temps simulé.
 * analyseur : null (pas de JEV) ou { occupe, classer(liste, pistes, langue), choisir(partie, liste, langue), tic?(t) }
 * → liste des événements du pas (pour le rendu, le HUD et le journal)
 */
export function pasPartie(p, dt, { analyseur = null, langue = "fr" } = {}) {
  const m = p.monde, sortie = [];
  m.pas(dt);
  recolter(p, sortie);
  analyseur?.tic?.(m.t);                                  // headless : livre les réponses dont la latence simulée est écoulée
  if (p.cibleId && !m.vivante(p.cibleId)) p.cibleId = null;

  const tous = observerTous(m, langue), vis = visibles(tous);
  if (p.mode === "jev" && analyseur) protocole(p, tous, vis, analyseur, langue);
  if (p.mode === "jev1" && analyseur && !analyseur.occupe && vis.length) analyseur.choisir(p, vis, langue);
  if (p.mode === "regle" && !p.cibleId) p.cibleId = botNaif(vis)?.id ?? null;

  // visée automatique (JEV / bot) : la tourelle tourne vers la cible puis tire
  if (p.mode !== "manuel") {
    const e = p.cibleId && m.entite(p.cibleId);
    if (e) {
      if (orienter(p.tourelle, pointVise(e, p.mode === "jev"), dt) && m.peutTirer()) {
        m.tirer(e, m.rouleauTouche(e), AUTEURS[p.mode]);
        if (!e.vivant || p.mode === "regle") p.cibleId = null;
      }
    } else relacher(p.tourelle, dt);
  }
  m.verifierFin();
  recolter(p, sortie);
  return sortie;
}
