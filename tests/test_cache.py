"""
Tests du cache JEV (phase 2). Aucun appel réel : fausse API. Fichiers dans un dossier temporaire.

    python3 -m unittest discover tests
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from server.cache_jev import CacheJEV, cle
from server.jev_client import MODELE_JEV, Budget, ClientJEV, JournalAppels
from tests.test_proxy import FAUSSE_CLE, FausseAPI

ROOT = Path(__file__).resolve().parent.parent
STATE = {"langue": "fr", "contexte": "Contexte : « Stop ! Levez les mains ! » — l'abri"}
Q_Z = {"type": "noul", "instructions": "Une silhouette. Description : grogne, « aidez-moi ! ». Cette cible est un zombie."}
Q_H = {"type": "noul", "instructions": "Une silhouette. Description : grogne, « aidez-moi ! ». Cette cible est un humain."}


def rep_api(*noms, p=0.9):
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 50}, "answers": {n: {"type": "noul", "noul": p} for n in noms}}


class TestCacheClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, api):
        self.budget = Budget()
        return ClientJEV(cle=FAUSSE_CLE, fake=False, budget=self.budget, journal=JournalAppels(self.dossier / "j.jsonl"),
                         ouvrir=api, cache=CacheJEV(self.dossier / "cache.json"))

    def test_deuxieme_appel_identique_sans_api(self):
        api = FausseAPI(rep_api("z_t1", "h_t1"))
        c = self.client(api)
        code, r1 = c.traiter({"questions": {"z_t1": Q_Z, "h_t1": Q_H}, "state": STATE})
        self.assertEqual(code, 200)
        code, r2 = c.traiter({"questions": {"z_t9": Q_Z, "h_t9": Q_H}, "state": STATE})   # autre cible, même fiche
        self.assertEqual(code, 200)
        self.assertEqual(len(api.requetes), 1)                     # aucun 2e appel
        self.assertEqual(self.budget.appels, 1)
        self.assertEqual(r2["answers"]["z_t9"], r1["answers"]["z_t1"])
        self.assertEqual(r2["cache"], 2)

    def test_seules_les_questions_manquantes_partent(self):
        api = FausseAPI(rep_api("z_t1"), rep_api("h_t2", p=0.2))
        c = self.client(api)
        c.traiter({"questions": {"z_t1": Q_Z}, "state": STATE})
        code, r = c.traiter({"questions": {"z_t2": Q_Z, "h_t2": Q_H}, "state": STATE})
        self.assertEqual(code, 200)
        envoye = json.loads(api.requetes[1][0].data)
        self.assertEqual(list(envoye["questions"]), ["h_t2"])
        self.assertEqual(set(r["answers"]), {"z_t2", "h_t2"})

    def test_erreurs_et_reponses_invalides_jamais_cachees(self):
        import io, urllib.error
        api = FausseAPI(urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"")),
                        {"model": "m", "answers": {"z_t1": {"noul": 1.7}}}, rep_api("z_t1"))
        c = self.client(api)
        self.assertEqual(c.traiter({"questions": {"z_t1": Q_Z}, "state": STATE})[0], 502)
        c.traiter({"questions": {"z_t1": Q_Z}, "state": STATE})        # p = 1,7 : invalide
        self.assertEqual(c.cache.entrees, {})
        c.traiter({"questions": {"z_t1": Q_Z}, "state": STATE})
        self.assertEqual(len(c.cache.entrees), 1)

    def test_cle_depend_du_modele_et_du_contexte(self):
        self.assertNotEqual(cle("jev-1.13.0", STATE, Q_Z), cle("jev-1.14.0", STATE, Q_Z))
        self.assertNotEqual(cle(MODELE_JEV, STATE, Q_Z), cle(MODELE_JEV, {**STATE, "langue": "en"}, Q_Z))

    def test_persistance(self):
        c = self.client(FausseAPI(rep_api("z_t1")))
        c.traiter({"questions": {"z_t1": Q_Z}, "state": STATE})
        relu = CacheJEV(self.dossier / "cache.json")
        trouvees, manquantes, servi = relu.chercher({"model": MODELE_JEV, "state": STATE, "questions": {"x": Q_Z}})
        self.assertEqual((len(trouvees), manquantes, servi), (1, {}, "jev-1.13.0"))


@unittest.skipUnless(shutil.which("node"), "node absent")
class TestCompatibiliteJS(unittest.TestCase):
    """Le benchmark (Node) doit retrouver exactement les clés écrites par le serveur (Python)."""

    def test_meme_cle_en_python_et_en_js(self):
        script = ("import { cleCache } from './tests/bench_lib.mjs';"
                  f"console.log(cleCache({json.dumps(MODELE_JEV)}, {json.dumps(STATE)}, {json.dumps(Q_Z)}))")
        cle_js = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(cle_js, cle(MODELE_JEV, STATE, Q_Z))

    def test_meme_modele_par_defaut(self):
        js = (ROOT / "tests" / "bench_config.mjs").read_text()
        self.assertEqual(re.search(r'"(jev-[^"]+)"', js).group(1), MODELE_JEV)


if __name__ == "__main__":
    unittest.main()
