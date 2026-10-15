// Généré par `python3 -m analyse.calibration` (phase 5) — ne pas modifier à la main.
// Calibration des lectures JEV cohérentes, valable pour CE modèle uniquement (sinon : désactivée).
// isotonique : p calibrée = interpolation linéaire de (x → y), bornée aux extrémités (comme sklearn).
// tauxZombies : proportion de zombies dans ces données, retirée pour obtenir un rapport de vraisemblance.
export const CALIBRATION_JEV = {
  "modele": "jev-1.13.0",
  "methode": "platt",
  "a": 1.4543,
  "b": -0.5584,
  "tauxZombies": 0.607,
  "fiches": 24,
  "incohMax": 0.15,
  "validationCroisee": {
    "brier": 0.0071,
    "log_loss": 0.0453,
    "ece": 0.0402,
    "marge": 0.7798,
    "fiche_pire": "en blesse_humain_1_d"
  }
};
