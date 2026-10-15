"""
Tests de l'analyse de calibration (phase 5). Nécessite numpy + scikit-learn (sinon : ignorés).

    python3 -m unittest discover tests
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    from analyse import calibration as cal
except ImportError:          # le serveur reste en stdlib ; seule l'analyse a besoin de numpy / sklearn
    cal = None

ROOT = Path(__file__).resolve().parent.parent


def lectures(p, y, groupes, items=None, n=None):
    k = len(p)
    return cal.Lectures(langue=np.array(["en"] * k), item=np.array(items or [f"x_{i}_r" for i in range(k)]),
                        groupe=np.array(groupes), y=np.array(y, float), p=np.array(p, float),
                        incoh=np.zeros(k), n=np.array(n or [1.0] * k), modele="m")


@unittest.skipIf(cal is None, "numpy / scikit-learn absents")
class TestMetriques(unittest.TestCase):
    def test_ece_nulle_si_parfaitement_calibre(self):
        # p = 0,25 : 1 zombie sur 4 ; p = 0,75 : 3 sur 4
        p = np.array([.25] * 4 + [.75] * 4); y = np.array([1, 0, 0, 0, 1, 1, 1, 0.]); w = np.ones(8)
        self.assertAlmostEqual(cal.ece(p, y, w), 0)
        self.assertAlmostEqual(cal.brier(p, y, w), 0.1875)

    def test_ece_detecte_la_sous_confiance(self):
        # JEV dit 0,65 / 0,35 alors que la réalité est 1 / 0 : écart de 0,35 dans chaque tranche
        p = np.array([.65] * 5 + [.35] * 5); y = np.array([1] * 5 + [0] * 5, float)
        self.assertAlmostEqual(cal.ece(p, y, np.ones(10)), 0.35)

    def test_poids_normalises_au_nombre_de_fiches(self):
        d = lectures([.2, .8], [0, 1], ["a", "b"], n=[1000., 3000.])
        self.assertAlmostEqual(d.w.sum(), 2)


@unittest.skipIf(cal is None, "numpy / scikit-learn absents")
class TestValidationCroisee(unittest.TestCase):
    def test_aucune_fuite_la_description_testee_est_absente_de_l_apprentissage(self):
        vus = []

        class Espion(cal.Brut):
            def fit(self, p, y, w):
                vus.append(set(np.round(p, 3)))
                return self

        d = lectures([.1, .15, .8, .85], [0, 0, 1, 1], ["a", "a", "b", "b"])
        cal.validation_croisee(d, Espion)
        self.assertEqual(vus, [{.8, .85}, {.1, .15}])

    def test_regle_de_choix_refuse_un_calibrateur_qui_ralentit_les_confirmations(self):
        base = {"brier": 0, "ece": 0, "fiche_pire": ""}
        res = {cal.Brut.nom: {"validation croisée": {**base, "log_loss": .09, "marge": .2, "sommations": np.array([1, 2])}},
               cal.Platt.nom: {"validation croisée": {**base, "log_loss": .05, "marge": .8, "sommations": np.array([1, 2])}},
               cal.Isotonique.nom: {"validation croisée": {**base, "log_loss": .02, "marge": 1.6, "sommations": np.array([1, 99])}}}
        self.assertIs(cal.choisir(res), cal.Platt)
        res[cal.Isotonique.nom]["validation croisée"]["sommations"] = np.array([1, 2])
        self.assertIs(cal.choisir(res), cal.Isotonique)


@unittest.skipIf(cal is None, "numpy / scikit-learn absents")
class TestExport(unittest.TestCase):
    def test_module_js_lisible_par_node_et_meme_preuve_qu_en_python(self):
        d = lectures([.05, .1, .3, .7, .9, .95], [0, 0, 0, 1, 1, 1], list("abcdef"))
        platt = cal.Platt().fit(d.p, d.y, d.w)
        with tempfile.TemporaryDirectory() as t:
            js = Path(t) / "calibration_jev.mjs"
            cal.exporter_js(d, platt, js, {"log_loss": .1, "sommations": np.array([1])})
            calib = (ROOT / "web" / "js" / "analysis" / "calibration.js").as_uri()
            code = (f"import {{ CALIBRATION_JEV as C }} from {json.dumps(js.as_uri())};"
                    f"import {{ creerCalibrateur }} from {json.dumps(calib)};"
                    "console.log(JSON.stringify([C.methode, creerCalibrateur(C).llr(0.8)]));")
            sortie = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
        methode, llr_js = json.loads(sortie.stdout)
        pi = cal.taux_zombies(d)
        llr_py = float(cal.logit(platt.predict(np.array([0.8])))[0] - np.log(pi / (1 - pi)))
        self.assertEqual(methode, "platt")
        self.assertAlmostEqual(llr_js, llr_py, places=3)


if __name__ == "__main__":
    unittest.main()
