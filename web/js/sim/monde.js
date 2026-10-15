// Monde simulé : vérité terrain (nature), déplacements, sommation, tir, fin de partie.
// Aucune dépendance à Three.js ni au DOM : tourne aussi en Node (simulateur headless, phase 2).
// Le temps est uniquement partie.t (horloge simulée) : pas de setTimeout pour la logique.
import { DUREE, PV_MAX, MUNITIONS, RECHARGE, CADENCE, SPAWN_Z, BARRICADE_Z, PORTEE_SOMMATION, DELAI_REACTION,
  VITESSES, BAREME, P_DESOBEISSANCE, P_OBEIT_2E, MAX_SOMMATIONS, chanceTouche } from "../config.js";
import { NB_DESC } from "../perception/descriptions.js";

export const estZombie = n => n === "zombie" || n === "blesse_zombie";
export const score = s => BAREME.zombie * s.zombies_tues + BAREME.sauve * s.humains_sauves
  + BAREME.humain_abattu * s.humains_tues + BAREME.morsure * s.morsures;

export class Entite {
  constructor(id, nature, rng, t, pDesobeissance = P_DESOBEISSANCE) {
    this.id = id; this.nature = nature; this.descIdx = rng.entier(NB_DESC[nature]);
    this.vivant = true; this.mort = 0; this.phase = rng.suivant() * 6;
    this.sommeAt = null; this.reactionAt = null; this.reagi = false; this.arrete = false;
    this.vitesse = VITESSES[nature] * (0.85 + rng.suivant() * 0.35) * (1 + t / DUREE * 0.6);
    this.x = (rng.suivant() - .5) * 14; this.z = SPAWN_Z; this.rotY = 0;
    this.cibleX = (rng.suivant() - .5) * 10;
    this.zig = nature === "humain" && this.descIdx === 2;
    // tirages toujours faits (même suite aléatoire quelle que soit la nature)
    const d = rng.suivant(), d2 = rng.suivant();
    this.desobeit = !estZombie(nature) && d < pDesobeissance;   // ne s'arrête pas à la 1re sommation
    this.obeitSecond = d2 < P_OBEIT_2E;                          // … mais à la 2e (si désobéissant)
    this.sommations = 0;
  }
  // un humain s'arrête à la sommation, sauf s'il panique ; un zombie jamais
  get obeit() { return !estZombie(this.nature) && (!this.desobeit || (this.sommations >= 2 && this.obeitSecond)); }
  get distance() { return Math.hypot(this.x, this.z); }
}

function avancer(e, dt, t) {
  // humain qui obéit à la sommation : s'arrête, mains en l'air
  e.arrete = e.sommeAt !== null && e.obeit && t > e.sommeAt + .3 && t < e.sommeAt + 2.6;
  if (e.arrete) return;
  const dx = e.cibleX - e.x + (e.zig ? Math.sin(t * 3 + e.phase) * 3 : 0), dz = BARRICADE_Z - e.z;
  const L = Math.hypot(dx, dz) || 1;
  e.x += dx / L * e.vitesse * dt; e.z += dz / L * e.vitesse * dt;
  e.rotY = Math.atan2(dx, dz);
  e.phase += dt * e.vitesse * (e.nature === "humain" ? 2.2 : 3.2);
}

export class Monde {
  constructor(rng, { desobeissance = P_DESOBEISSANCE } = {}) {
    this.rng = rng; this.t = 0; this.fini = false; this.desobeissance = desobeissance;
    this.pv = PV_MAX; this.mun = MUNITIONS; this.rechargeFin = 0; this.dernierTir = -9;
    this.prochainSpawn = 0; this.n = 0; this.derniereSommation = -9;
    this.entites = []; this.parId = new Map(); this.evenements = [];
    this.stats = { zombies_tues: 0, humains_tues: 0, humains_sauves: 0, morsures: 0, tirs: 0, rates: 0, sommations: 0, tirs_bloques: 0, sommations_ciblees: 0 };
  }
  emettre(type, data = {}) { this.evenements.push({ type, ...data }); }
  vider() { const ev = this.evenements; this.evenements = []; return ev; }
  entite(id) { return this.parId.get(id); }
  vivante(id) { return !!this.parId.get(id)?.vivant; }

  apparition() {
    const r = this.rng.suivant();
    const nature = r < .55 ? "zombie" : r < .8 ? "humain" : this.rng.choisir(["blesse_zombie", "blesse_humain"]);
    const e = new Entite("t" + (++this.n), nature, this.rng, this.t, this.desobeissance);
    this.entites.push(e); this.parId.set(e.id, e);
    this.emettre("apparition", { e });
  }

  pas(dt) {
    this.t += dt;
    if (this.t >= this.prochainSpawn) { this.apparition(); this.prochainSpawn = this.t + Math.max(.65, 2.3 - this.t / 55); }
    for (const e of this.entites) {
      if (!e.vivant) { e.mort += dt; continue; }
      if (e.reactionAt !== null && !e.reagi && this.t >= e.reactionAt) { e.reagi = true; this.emettre("reaction", { e }); }
      avancer(e, dt, this.t);
    }
    this.entites = this.entites.filter(e => {
      if (e.vivant && e.z >= BARRICADE_Z - .2) {          // arrivée à la barricade
        e.vivant = false; e.mort = 9;
        const z = estZombie(e.nature);
        if (z) { this.pv--; this.stats.morsures++; } else this.stats.humains_sauves++;
        this.emettre("arrivee", { e, issue: z ? "morsure" : "sauve" });
      } else if (e.vivant || e.mort < 6) return true;     // les morts restent 6 s (animation)
      this.parId.delete(e.id); this.emettre("retrait", { e });
      return false;
    });
  }

  // 📢 « Stop ! Levez les mains ! » : chaque silhouette à portée réagit après DELAI_REACTION (temps simulé)
  sommer() {
    this.derniereSommation = this.t; this.stats.sommations++;
    for (const e of this.entites)
      if (e.vivant && e.sommeAt === null && e.distance < PORTEE_SOMMATION) { e.sommeAt = this.t; e.reactionAt = this.t + DELAI_REACTION; e.sommations = 1; }
    this.emettre("sommation");
  }

  // 2e sommation, ciblée sur des silhouettes déjà sommées (la réaction verbale ne change pas : seul le mouvement apporte une preuve nouvelle)
  sommerCibles(ids) {
    const visees = ids.map(id => this.parId.get(id))
      .filter(e => e?.vivant && e.sommeAt !== null && e.sommations < MAX_SOMMATIONS && e.distance < PORTEE_SOMMATION);
    if (!visees.length) return;
    for (const e of visees) { e.sommeAt = this.t; e.sommations++; }
    this.stats.sommations_ciblees++;
    this.emettre("sommation", { cibles: visees.map(e => e.id) });
  }

  peutTirer() { return this.mun > 0 && this.t >= this.rechargeFin && this.t - this.dernierTir >= CADENCE; }
  rouleauTouche(e) { return this.rng.suivant() < chanceTouche(e.distance); }
  tirer(e, touche, auteur) {
    this.dernierTir = this.t; this.mun--; this.stats.tirs++;
    const tue = !!(e && touche && e.vivant);
    if (tue) { e.vivant = false; this.stats[estZombie(e.nature) ? "zombies_tues" : "humains_tues"]++; }
    else this.stats.rates++;
    this.emettre("tir", { e, touche: tue, auteur });
    if (this.mun === 0) { this.rechargeFin = this.t + RECHARGE; this.mun = MUNITIONS; }
  }

  verifierFin() {
    if (!this.fini && (this.pv <= 0 || this.t >= DUREE)) { this.fini = true; this.emettre("fin"); }
  }
}
