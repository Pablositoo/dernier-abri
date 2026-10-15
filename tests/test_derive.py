"""
Tests de la détection de dérive (phase 5). Aucun appel réel : fausse API.

    python3 -m unittest discover tests
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.cache_jev import CacheJEV, cle
from server.derive import choisir_canaris, comparer, interroger
from server.jev_client import MAX_QUESTIONS, MODELE_JEV, Budget, ClientJEV, JournalAppels
from tests.test_cache import Q_H, Q_Z, STATE, rep_api
from tests.test_proxy import FAUSSE_CLE, FausseAPI

REF = {"c0": 0.9, "c1": 0.1, "c2": 0.5}


class TestComparer(unittest.TestCase):
    def test_memes_reponses_pas_de_derive(self):
        v = comparer(REF, dict(REF), modele_attendu="m", modele_servi="m")
        self.assertFalse(v.derive)
        self.assertEqual((v.n, v.ecart_max), (3, 0))

    def test_petit_bruit_tolere(self):
        v = comparer(REF, {"c0": 0.93, "c1": 0.08, "c2": 0.5}, modele_attendu="m", modele_servi="m")
        self.assertFalse(v.derive, v.raisons)

    def test_une_question_qui_bouge_beaucoup(self):
        v = comparer(REF, {**REF, "c2": 0.75}, modele_attendu="m", modele_servi="m")
        self.assertTrue(v.derive)
        self.assertEqual(v.pire, "c2")

    def test_biais_systematique(self):
        v = comparer(REF, {k: p + 0.07 for k, p in REF.items()}, modele_attendu="m", modele_servi="m")
        self.assertTrue(v.derive)
        self.assertTrue(any("décalage" in r for r in v.raisons))

    def test_autre_modele_ou_reponses_manquantes(self):
        self.assertTrue(comparer(REF, dict(REF), modele_attendu="m", modele_servi="m2").derive)
        self.assertTrue(comparer(REF, {"c0": 0.9}, modele_attendu="m", modele_servi="m").derive)


class TestCanaris(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)
        self.cache = CacheJEV(self.dossier / "cache.json")
        self.qs = [{"type": "noul", "instructions": f"question {i}"} for i in range(30)]
        for i, q in enumerate(self.qs):
            self.cache.entrees[cle(MODELE_JEV, STATE, q)] = {"reponse": {"type": "noul", "noul": i / 30}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_choix_deterministe_et_regroupe(self):
        requetes = [{"state": STATE, "questions": {f"q{i}": q for i, q in enumerate(self.qs)}},
                    {"state": STATE, "questions": {"absente": {"type": "noul", "instructions": "pas en cache"}}}]
        p1, r1 = choisir_canaris(requetes, self.cache, MODELE_JEV, 15)
        p2, r2 = choisir_canaris(requetes, self.cache, MODELE_JEV, 15)
        self.assertEqual(r1, r2)
        self.assertEqual(len(r1), 15)
        self.assertEqual(len(p1), 2)                                 # 15 questions → lots de 12 max
        self.assertTrue(all(len(p["questions"]) <= MAX_QUESTIONS for p in p1))
        self.assertNotIn("pas en cache", str(p1))

    def test_interroger_sans_cache_et_journalise(self):
        api = FausseAPI(rep_api("c0", "c1", p=0.42))
        journal = JournalAppels(self.dossier / "j.jsonl")
        appel = lambda payload, cle_api: __import__("server.jev_client", fromlist=["appeler"]).appeler(
            payload, cle_api, ouvrir=api)
        nouvelles, servi = interroger([{"state": STATE, "questions": {"c0": Q_Z, "c1": Q_H}}], FAUSSE_CLE, MODELE_JEV,
                                      Budget(max_appels=1), journal, appel=appel)
        self.assertEqual(nouvelles, {"c0": 0.42, "c1": 0.42})
        self.assertEqual(servi, "jev-1.13.0")
        ligne = (self.dossier / "j.jsonl").read_text()
        self.assertIn("canari ok", ligne)
        self.assertNotIn(FAUSSE_CLE, ligne)


class TestDerivePassive(unittest.TestCase):
    def test_autre_modele_servi_jamais_mis_en_cache(self):
        with tempfile.TemporaryDirectory() as d:
            api = FausseAPI({**rep_api("z_t1"), "model": "jev-1.14.0"})
            c = ClientJEV(cle=FAUSSE_CLE, fake=False, budget=Budget(), journal=JournalAppels(Path(d) / "j.jsonl"),
                          ouvrir=api, cache=CacheJEV(Path(d) / "cache.json"))
            code, r = c.traiter({"questions": {"z_t1": Q_Z}, "state": STATE})
            self.assertEqual(code, 200)                          # la réponse est servie (le navigateur décidera)…
            self.assertEqual(r["model"], "jev-1.14.0")
            self.assertEqual(c.cache.entrees, {})                # … mais n'empoisonne pas la référence
            self.assertIn('"statut": "derive"', (Path(d) / "j.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
