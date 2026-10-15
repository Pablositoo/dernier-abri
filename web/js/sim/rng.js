// Seule source de hasard du jeu (règle : pas de Math.random() ailleurs).
// mulberry32 : rapide, 32 bits, suffisant pour une simulation reproductible (pas pour de la crypto).

export const graineAleatoire = () => crypto.getRandomValues(new Uint32Array(1))[0];

export function creerRng(graine) {
  let a = graine >>> 0;
  const suivant = () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return {
    graine: graine >>> 0,
    suivant,                                            // [0, 1)
    entier: n => Math.floor(suivant() * n),             // [0, n)
    choisir: tab => tab[Math.floor(suivant() * tab.length)],
  };
}
