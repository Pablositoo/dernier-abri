// Politique v4 : ordonnancement des tirs par coût. Ne relâche aucune règle de sécurité :
// mêmes cibles confirmées (SPRT + concordance + R3 + R4), même ligne de tir, même verrou au moment du tir.
//
// Constat (benchmark v3, EN) : 56 % des morsures restantes = zombie confirmé dont la ligne de tir n'est JAMAIS libre
// (le prix de « ne jamais risquer un humain ») ; 30 % = ligne libre seulement entre 30 et 45 m, où R5 interdisait de tirer.
// Coût d'un raté : du temps et une balle ; coût d'une morsure : -20 et 1 PV. Une occasion libre ne revient souvent pas
// (d'autres humains arrivent dans la ligne) : on tire dès qu'elle se présente.
import { MUNITIONS, ORDONNANCEMENT as O } from "../config.js";
import { ligneDegagee } from "./regles.js";
import { confirmesV3, tirRaisonnable } from "./sprt.js";

// Cibles v4 : zone normale (R5), ou tir d'opportunité jusqu'à 45 m quand la ligne de tir est libre maintenant
export function eligiblesV4(vis, pistes, tous) {
  return confirmesV3(vis, pistes).filter(c => tirRaisonnable(c) || (c.distance < O.porteeOpportunite && ligneDegagee(c, tous, pistes)));
}

// Rechargement tactique : chargeur presque vide et aucune cible confirmée à portée → recharger maintenant plutôt qu'en plein assaut
export function doitRecharger(m, vis, pistes) {
  return m.mun <= O.rechargeTactique && m.mun < MUNITIONS && m.t >= m.rechargeFin &&
    !confirmesV3(vis, pistes).some(c => c.distance < O.porteeOpportunite);
}
