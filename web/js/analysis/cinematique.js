// Analyseur cinématique : après une sommation, un humain s'arrête, un zombie continue.
// Gratuit, instantané, indépendant du texte : il ne lit que les positions observées (x, z).
import { FUSION } from "../config.js";

// À appeler à chaque pas pour chaque silhouette observée. Ajoute une mesure à piste.mesures à la fin de chaque fenêtre.
export function suivreCinematique(piste, o, t) {
  if (o.sommeAt !== null && o.sommeAt !== piste.derniereSommeAt) {   // nouvelle sommation → nouvelle fenêtre
    piste.derniereSommeAt = o.sommeAt;
    piste.fenetre = { debut: o.sommeAt + FUSION.fenetre[0], fin: o.sommeAt + FUSION.fenetre[1], p0: null };
  }
  const f = piste.fenetre;
  if (!f) return;
  if (!f.p0 && t >= f.debut) f.p0 = { x: o.x, z: o.z };
  if (f.p0 && t >= f.fin) {
    const d = Math.hypot(o.x - f.p0.x, o.z - f.p0.z);
    // true = s'est arrêté, false = a continué, null = ambigu (aucune preuve)
    const arret = d < FUSION.seuilArret ? true : d > FUSION.seuilBouge ? false : null;
    piste.mesures.push({ t, d: +d.toFixed(2), arret });
    piste.fenetre = null;
  }
}

