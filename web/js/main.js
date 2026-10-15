// Orchestration : boucle à pas fixe (horloge simulée), rendu, contrôles, journal.
import * as THREE from "three";
import { DT_REEL_MAX, PAS_SIM, POLITIQUE_DEFAUT, SEUIL_DEFAUT } from "./config.js";
import { creerRng, graineAleatoire } from "./sim/rng.js";
import { estZombie } from "./sim/monde.js";
import { AUTEURS, creerPartie, pasPartie } from "./partie.js";
import { decrire, observerTous, visibles } from "./perception/observer.js";
import { analyseurJEV, etatJEV, reinitialiserJEV } from "./analysis/jev.js";
import { journalDecision, journalPartie } from "./response/journal.js";
import { creerScene } from "./render/scene.js";
import { animerArme, creerArme, tirArme } from "./render/arme.js";
import { creerEffets } from "./render/effets.js";
import { VuePerso } from "./render/persos.js";
import { appliquerLangue, langue, tr } from "./ui/i18n.js";
import { $, ecranFin, feed, hud } from "./ui/hud.js";
import { majEtiquettes } from "./ui/etiquettes.js";
import { audio, bang, bip } from "./ui/audio.js";

const PARAMS = new URLSearchParams(location.search);
const LITE = PARAMS.has("lite");                                     // ?lite = PC lent
const SPEED = +PARAMS.get("speed") || 1;                             // ?speed=8 : accéléré (tests)
const GRAINE = PARAMS.has("seed") ? (+PARAMS.get("seed") >>> 0) : null;   // ?seed=42 : partie reproductible
const POLITIQUE = PARAMS.get("politique") === "v2" ? "v2" : POLITIQUE_DEFAUT;  // ?politique=v2 : ancienne politique (comparaison)
const rngRendu = creerRng(graineAleatoire());                       // hasard visuel : n'influence jamais la partie

const { renderer, scene, camera, lampadaires, dust } = creerScene(rngRendu, LITE);
const arme = creerArme(camera);
const effets = creerEffets(scene);
const vues = new Map();                                             // id → VuePerso
let partie = null, seuil = SEUIL_DEFAUT.jev, cfg = { jev: false }, accu = 0, recul = 0, shake = 0;

// ================= Partie =================
function nouvellePartie(mode) {
  vues.forEach(v => v.detruire()); vues.clear();
  if (mode === "jev1" && seuil > .6) seuil = SEUIL_DEFAUT.jev1;
  if (mode === "jev" && seuil < .6) seuil = SEUIL_DEFAUT.jev;
  const graine = GRAINE ?? graineAleatoire();
  partie = creerPartie(mode, graine, seuil, { politique: POLITIQUE }); accu = 0;
  console.info(`Partie ${mode} · politique ${POLITIQUE} · graine ${graine} (la rejouer : ?seed=${graine})`);
  reinitialiserJEV(); $("feed").innerHTML = "";
  $("start").classList.add("hidden"); $("end").classList.add("hidden");
  afficherMode();
  $("brain").style.display = mode.startsWith("jev") ? "" : "none";
  $("rules").style.display = mode === "jev" ? "" : "none";
  if (mode === "manuel") renderer.domElement.requestPointerLock?.();
  audio();
}

function changerSeuil(delta) {
  seuil = Math.min(.95, Math.max(.05, +(seuil + delta).toFixed(2)));
  if (partie) partie.seuil = seuil;
}

// ================= Événements de la simulation → rendu, HUD, journal =================
function effetTir(ev) {
  recul = 1; tirArme(arme); bang(rngRendu);
  const from = new THREE.Vector3(); arme.canon.getWorldPosition(from);
  const to = ev.e ? new THREE.Vector3(ev.e.x, 1.25, ev.e.z) : new THREE.Vector3(0, 0, -40).applyQuaternion(camera.quaternion).add(camera.position);
  if (ev.e && !ev.touche) to.add(new THREE.Vector3((rngRendu.suivant() - .5) * 2.5, rngRendu.suivant() * 1.2, 0));
  effets.tracer(from, to);
}

function surEvenements(evs) {
  const L = langue();
  for (const ev of evs) {
    const e = ev.e, nom = e && tr().noms[e.nature];
    switch (ev.type) {
      case "apparition": vues.set(e.id, new VuePerso(e, rngRendu, scene, $("tags"))); break;
      case "sommation":
        $("shout").style.opacity = 1; setTimeout(() => $("shout").style.opacity = 0, 900);
        effets.onde(); bip(); feed(ev.cibles ? tr().sommationCiblee(ev.cibles) : tr().sommation); break;
      case "bloque": feed(tr().bloque(ev.id)); break;
      case "tir":
        effetTir(ev);
        if (ev.touche) {
          const z = estZombie(e.nature), p = ev.piste;
          vues.get(e.id)?.tuer(nom, z); journalDecision(partie, e, p, "abattu", L);
          const pr = ev.auteur.startsWith("JEV") ? (p?.pPost ?? p?.pZ ?? p?.pDecision) : null;   // v3 : p fusionné
          feed(`${ev.auteur} → ${e.id} · ${nom.toLowerCase()} ${z ? "✓" : "✗ " + tr().erreur}${pr ? " · p=" + pr.toFixed(2) : ""}  « ${decrire(e, L)} »`, z ? "good" : "bad");
        } else if (e) feed(`${ev.auteur} → ${e.id} · ${tr().rate} (${Math.round(e.distance)} m)`);
        break;
      case "arrivee":
        journalDecision(partie, e, ev.piste, ev.issue, L);
        if (ev.issue === "morsure") { shake = .5; $("damage").style.opacity = 1; setTimeout(() => $("damage").style.opacity = 0, 250); feed(tr().morsure(e.id), "bad"); }
        else feed(tr().sauve(e.id), "good");
        break;
      case "retrait": vues.get(e.id)?.detruire(); vues.delete(e.id); break;
      case "fin": document.exitPointerLock?.(); ecranFin(partie, etatJEV); journalPartie(partie, etatJEV, L); break;
    }
  }
}

// ================= Contrôles =================
addEventListener("mousemove", e => {
  if (partie?.mode !== "manuel" || document.pointerLockElement !== renderer.domElement) return;
  const t = partie.tourelle;
  t.yaw = THREE.MathUtils.clamp(t.yaw - e.movementX * .0022, -1.3, 1.3);
  t.pitch = THREE.MathUtils.clamp(t.pitch - e.movementY * .0022, -.5, .45);
});
const ray = new THREE.Raycaster();
function viseSous() {
  ray.setFromCamera({ x: 0, y: 0 }, camera);
  const vivants = [...vues.values()].filter(v => v.e.vivant).map(v => v.root);
  const hit = ray.intersectObjects(vivants, true)[0];
  return hit ? partie.monde.entite(hit.object.userData.id) : null;
}
addEventListener("mousedown", () => {
  if (!partie || partie.monde.fini || partie.mode !== "manuel") return;
  if (document.pointerLockElement !== renderer.domElement) return renderer.domElement.requestPointerLock?.();
  if (partie.monde.peutTirer()) { const e = viseSous(); partie.monde.tirer(e, !!e, AUTEURS.manuel); }
});
// libellé du mode et règles affichées selon la politique (v2 seuil fixe / v3 SPRT)
function afficherMode() {
  if (partie) $("mode").textContent = partie.mode === "jev" ? `${tr().modes.jev} ${partie.politique}` : tr().modes[partie.mode];
  $("rules").innerHTML = POLITIQUE === "v3" ? tr().reglesV3 : tr().regles;
}
function changerLangue(l) { appliquerLangue(l); afficherMode(); }
addEventListener("keydown", e => {
  if (e.key === "l" || e.key === "L") changerLangue(langue() === "fr" ? "en" : "fr");
  if (e.key === "ArrowUp") changerSeuil(+.05);
  if (e.key === "ArrowDown") changerSeuil(-.05);
  if (e.key === "1" && cfg.jev) nouvellePartie("jev");
  if (e.key === "2" && cfg.jev) nouvellePartie("jev1");
  if (e.key === "3") nouvellePartie("regle");
  if (e.key === "4") nouvellePartie("manuel");
  if ((e.key === "r" || e.key === "R") && partie) nouvellePartie(partie.mode);
  if (e.key === "Escape" && partie) { partie.monde.fini = true; $("start").classList.remove("hidden"); }
});
document.querySelectorAll("[data-lang]").forEach(b => b.addEventListener("click", () => changerLangue(b.dataset.lang)));
document.querySelectorAll("button[data-mode]").forEach(b => b.addEventListener("click", () => nouvellePartie(b.dataset.mode)));

// ================= Boucle =================
// La simulation avance par pas fixes de PAS_SIM (temps simulé), le rendu suit à chaque image.
const clock = new THREE.Clock();
function frame() {
  requestAnimationFrame(frame);
  const dt = Math.min(clock.getDelta(), DT_REEL_MAX) * SPEED, t = clock.elapsedTime;
  lampadaires[1].intensity = rngRendu.suivant() < .03 ? 2 : 22;     // lampadaire qui grésille
  dust.rotation.y = Math.sin(t * .05) * .05; dust.position.y = Math.sin(t * .3) * .2;

  if (partie && !partie.monde.fini) {
    const opts = { analyseur: cfg.jev ? analyseurJEV : null, langue: langue() };
    accu += dt;
    while (accu >= PAS_SIM && !partie.monde.fini) { surEvenements(pasPartie(partie, PAS_SIM, opts)); accu -= PAS_SIM; }
    const vis = visibles(observerTous(partie.monde, opts.langue));
    const p = partie.mode === "manuel" && viseSous();
    $("tip").style.display = p ? "block" : "none";
    if (p) $("tip").textContent = `${p.id} · ${Math.round(p.distance)} m · « ${decrire(p, opts.langue)} »`;
    hud(partie, etatJEV, vis); majEtiquettes(partie, vues, camera, vis);
  }
  for (const v of vues.values()) { v.maj(); if (partie?.pistes.get(v.e.id)?.lueAvecReaction) v.revelerYeux(); }

  // caméra, recul, tremblement, arme, effets
  shake = Math.max(0, shake - dt); recul = Math.max(0, recul - dt * 7);
  const tour = partie?.tourelle ?? { yaw: 0, pitch: 0 }, alea = () => (rngRendu.suivant() - .5) * shake * .05;
  camera.rotation.set(tour.pitch + recul * .04 + alea(), tour.yaw + alea(), 0);
  animerArme(arme, t, dt, partie && partie.monde.t < partie.monde.rechargeFin, recul);
  effets.maj(dt);
  renderer.render(scene, camera);
}

fetch("/config").then(r => r.json()).then(c => { cfg = c; if (!c.jev) document.querySelectorAll(".needJev").forEach(b => { b.disabled = true; b.title = tr().pasCle; }); }).catch(() => {});
changerLangue(langue());
// débogage et tests (fumée Playwright)
window.__debug = {
  get partie() { return partie; }, etatJEV, nouvellePartie,
  etat: () => partie && { mode: partie.mode, graine: partie.graine, t: +partie.monde.t.toFixed(3), fini: partie.monde.fini,
    stats: { ...partie.monde.stats }, appels: etatJEV.appels, err: etatJEV.err },
};
frame();
