// Visée automatique (calcul pur, sans Three.js) : la tourelle tourne vers la cible, tir quand elle est alignée.
import { HAUTEUR_OEIL } from "../config.js";

// tête + anticipation du mouvement (la balle et la latence ne sont pas instantanées) ; sinon centre du torse
export function pointVise(e, tete) {
  if (!tete) return { x: e.x, y: 1.25, z: e.z };
  const lead = e.arrete ? 0 : e.vitesse * .12;
  return { x: e.x + Math.sin(e.rotY) * lead, y: 1.72, z: e.z + Math.cos(e.rotY) * lead };
}

// → true si la tourelle (caméra en 0, HAUTEUR_OEIL, 0) est alignée sur le point
export function orienter(tourelle, c, dt) {
  const ty = Math.atan2(-c.x, -c.z), tp = Math.atan2(c.y - HAUTEUR_OEIL, Math.hypot(c.x, c.z)), k = Math.min(1, dt * 9);
  tourelle.yaw += (ty - tourelle.yaw) * k; tourelle.pitch += (tp - tourelle.pitch) * k;
  return Math.abs(ty - tourelle.yaw) < .03 && Math.abs(tp - tourelle.pitch) < .03;
}

export function relacher(tourelle, dt) { tourelle.yaw *= 1 - dt; tourelle.pitch *= 1 - dt; }
