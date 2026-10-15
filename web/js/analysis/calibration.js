// Calibration des lectures JEV (phase 5) : pZ brute → rapport de vraisemblance calibré pour la fusion.
// Les paramètres viennent de `python3 -m analyse.calibration` (calibration_jev.js) et ne valent que pour leur modèle :
// si JEV sert un autre modèle, la partie désactive la calibration (dérive, voir partie.js).
import { CALIBRATION_JEV } from "./calibration_jev.js";
import { logit, sigmoide } from "./fusion.js";

// interpolation linéaire bornée aux extrémités (comme sklearn IsotonicRegression, out_of_bounds="clip")
export function interpoler(p, x, y) {
  if (p <= x[0]) return y[0];
  if (p >= x.at(-1)) return y.at(-1);
  let i = 1;
  while (p > x[i]) i++;
  return x[i] === x[i - 1] ? y[i] : y[i - 1] + (y[i] - y[i - 1]) * (p - x[i - 1]) / (x[i] - x[i - 1]);
}

const cleTable = (pZ, incoh) => `${pZ.toFixed(4)}|${incoh.toFixed(4)}`;

// conf.methode : "isotonique" (x, y) | "platt" (a, b) | "table" (pCal par lecture, pour le benchmark hors échantillon)
export function creerCalibrateur(conf = CALIBRATION_JEV) {
  let pCal;
  if (conf.methode === "isotonique") pCal = p => interpoler(p, conf.x, conf.y);
  else if (conf.methode === "platt") pCal = p => sigmoide(conf.a * logit(p) + conf.b);
  else if (conf.methode === "table") {
    const t = new Map(conf.table.map(l => [cleTable(l.pZ, l.incoh), l.pCal]));
    pCal = (p, incoh) => {
      const v = t.get(cleTable(p, incoh));
      if (v == null) throw new Error(`lecture absente de la table de calibration : p=${p} incoh=${incoh}`);
      return v;
    };
  } else throw new Error(`méthode de calibration inconnue : ${conf.methode}`);
  // la fusion a son propre a priori (0,5) : on retire le taux de zombies des données de calibration
  const lpi = logit(conf.tauxZombies);
  return { modele: conf.modele, methode: conf.methode, llr: (pZ, incoh) => logit(pCal(pZ, incoh)) - lpi };
}
