// Perception : entités du monde → observations. La nature réelle n'en sort jamais
// (l'analyse et la politique ne voient que ce qu'un capteur verrait).
import { PORTEE, MAX_CIBLES } from "../config.js";
import { DESC_I18N, REACTION_DESOBEIT_I18N, REACTION_I18N } from "./descriptions.js";

export const decrire = (e, langue) => DESC_I18N[langue][e.nature][e.descIdx];
export const reactionTexte = (e, langue) =>
  !e.reagi ? null : (e.desobeit ? REACTION_DESOBEIT_I18N : REACTION_I18N)[langue][e.nature];

export function observer(e, langue) {
  return { id: e.id, desc: decrire(e, langue), reaction: reactionTexte(e, langue), distance: e.distance,
           x: e.x, z: e.z, vitesse: e.vitesse, arrete: e.arrete, sommeAt: e.sommeAt };
}
export const observerTous = (monde, langue) => monde.entites.filter(e => e.vivant).map(e => observer(e, langue));
// les MAX_CIBLES silhouettes les plus proches à portée
export const visibles = tous => tous.filter(o => o.distance < PORTEE).sort((a, b) => a.distance - b.distance).slice(0, MAX_CIBLES);
