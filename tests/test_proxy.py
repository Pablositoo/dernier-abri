"""
Tests du proxy (phase 0). Aucun appel réel à JEV : mode --fake ou faux urlopen.
Les CSV et le journal sont écrits dans un dossier temporaire, jamais dans les vrais fichiers.

    python3 -m unittest discover tests
"""
from __future__ import annotations

import csv
import http.client
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path

from server.app import ENTETE_JETON, TAILLE_MAX, creer_serveur
from server.jev_client import MODELE_JEV, Budget, appeler
from server.storage import COLONNES, JournalCSV, nettoyer

ROOT = Path(__file__).resolve().parent.parent
FAUSSE_CLE = "CLE-SECRETE-DE-TEST-0123456789"
NOUL = {"questions": {"z_t1": {"type": "noul", "instructions": "Target t1. This target is a zombie (hostile infected)."}}}


class FausseReponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FausseAPI:
    """Remplace urllib.request.urlopen : enregistre les requêtes, rejoue des réponses."""

    def __init__(self, *reponses):
        self.reponses, self.requetes = list(reponses), []

    def __call__(self, req, timeout):
        self.requetes.append((req, timeout))
        r = self.reponses.pop(0)
        if isinstance(r, BaseException):
            raise r
        return FausseReponse(json.dumps(r).encode())


class HorlogeFictive:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


# ================= Serveur HTTP réel sur un port libre =================
class BaseServeur(unittest.TestCase):
    fake = True
    budget_kw: dict = {}
    api = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)
        self.srv = creer_serveur(0, cle=None if self.fake else FAUSSE_CLE, fake=self.fake,
                                 budget=Budget(**self.budget_kw), dossier_donnees=self.dossier, ouvrir=self.api)
        self.port = self.srv.server_address[1]
        self.jeton = self.srv.ctx.jeton
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def entetes(self, **sauf):
        h = {"Host": f"localhost:{self.port}", "Origin": f"http://localhost:{self.port}",
             "Content-Type": "application/json", ENTETE_JETON: self.jeton}
        for k, v in sauf.items():
            k = {"jeton": ENTETE_JETON, "type": "Content-Type"}.get(k, k)
            if v is None:
                h.pop(k)
            else:
                h[k] = v
        return h

    def requete(self, methode, chemin, corps=None, entetes=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = corps if isinstance(corps, (bytes, type(None))) else json.dumps(corps).encode()
        c.request(methode, chemin, body=data, headers=entetes or {"Host": f"localhost:{self.port}"})
        r = c.getresponse()
        res = r.status, dict(r.getheaders()), r.read()
        c.close()
        return res

    def post(self, chemin, corps, **sauf):
        return self.requete("POST", chemin, corps, self.entetes(**sauf))


class TestS1Csrf(BaseServeur):
    def test_requete_legitime_acceptee(self):
        code, _, body = self.post("/jev", NOUL)
        self.assertEqual(code, 200)
        self.assertIn("z_t1", json.loads(body)["answers"])

    def test_127_0_0_1_accepte(self):
        code, _, _ = self.post("/jev", NOUL, Host=f"127.0.0.1:{self.port}", Origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(code, 200)

    def test_sans_jeton(self):
        self.assertEqual(self.post("/jev", NOUL, jeton=None)[0], 403)

    def test_mauvais_jeton(self):
        self.assertEqual(self.post("/jev", NOUL, jeton="x" * 43)[0], 403)

    def test_autre_origine(self):
        self.assertEqual(self.post("/jev", NOUL, Origin="https://evil.example")[0], 403)

    def test_sans_origine(self):
        self.assertEqual(self.post("/jev", NOUL, Origin=None)[0], 403)

    def test_text_plain_refuse(self):   # requête « simple » cross-site, sans pré-vol CORS
        self.assertEqual(self.post("/jev", NOUL, type="text/plain")[0], 415)

    def test_dns_rebinding_post(self):
        self.assertEqual(self.post("/jev", NOUL, Host=f"evil.example:{self.port}")[0], 403)

    def test_dns_rebinding_get_ne_livre_pas_le_jeton(self):
        code, _, body = self.requete("GET", "/", entetes={"Host": f"evil.example:{self.port}"})
        self.assertEqual(code, 403)
        self.assertNotIn(self.jeton.encode(), body)

    def test_page_contient_jeton_non_cache(self):
        code, h, body = self.requete("GET", "/?speed=8")
        self.assertEqual(code, 200)
        self.assertIn(self.jeton.encode(), body)
        self.assertNotIn(b"__JETON_SESSION__", body)
        self.assertEqual(h.get("Cache-Control"), "no-store")

    def test_protege_aussi_les_journaux(self):
        for chemin in ("/log", "/decision"):
            self.assertEqual(self.post(chemin, {"mode": "jev"}, jeton=None)[0], 403)
        self.assertFalse(any(self.dossier.glob("*.csv")))

    def test_preflight_cors_refuse(self):
        code, h, _ = self.requete("OPTIONS", "/jev", entetes={"Host": f"localhost:{self.port}", "Origin": "https://evil.example"})
        self.assertNotEqual(code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", h)


class TestS4Taille(BaseServeur):
    def test_trop_gros(self):
        corps = json.dumps({"questions": {"a": {"type": "noul", "instructions": "x" * TAILLE_MAX}}}).encode()
        self.assertEqual(self.post("/jev", corps)[0], 413)

    def test_json_invalide(self):
        self.assertEqual(self.post("/jev", b"{pas du json")[0], 400)

    def test_pas_un_objet(self):
        self.assertEqual(self.post("/jev", b"[1, 2]")[0], 400)

    def test_sans_content_length(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.putrequest("POST", "/jev", skip_host=True)
        for k, v in self.entetes().items():
            c.putheader(k, v)
        c.endheaders()
        self.assertEqual(c.getresponse().status, 411)
        c.close()

    def test_payload_jev_invalide(self):
        self.assertEqual(self.post("/jev", {"questions": {}})[0], 400)
        self.assertEqual(self.post("/jev", {"questions": {"a": {"type": "autre"}}})[0], 400)
        trop = {"questions": {f"q{i}": {"type": "noul", "instructions": "x"} for i in range(13)}}
        self.assertEqual(self.post("/jev", trop)[0], 400)

    def test_route_inconnue(self):
        self.assertEqual(self.post("/autre", {})[0], 404)


class TestS2BudgetHTTP(BaseServeur):
    budget_kw = {"max_appels": 2}

    def test_plafond_session(self):
        self.assertEqual(self.post("/jev", NOUL)[0], 200)
        self.assertEqual(self.post("/jev", NOUL)[0], 200)
        code, _, body = self.post("/jev", NOUL)
        self.assertEqual(code, 429)
        self.assertEqual(json.loads(body)["error"], "budget")


class TestS2Budget(unittest.TestCase):
    def test_debit_et_recharge(self):
        h = HorlogeFictive()
        b = Budget(par_minute=60, rafale=3, horloge=h)
        self.assertEqual([b.reserver() for _ in range(3)], [None] * 3)
        self.assertEqual(b.reserver(), "débit trop élevé")
        h.t += 1.0                                  # 60/min = 1 jeton par seconde
        self.assertIsNone(b.reserver())
        self.assertIsNotNone(b.reserver())

    def test_plafond_tokens(self):
        b = Budget(max_tokens=100)
        self.assertIsNone(b.reserver())
        b.compter_tokens(100)
        self.assertIn("tokens", b.reserver())


class TestS3Csv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def lire(self, nom):
        with (self.dossier / nom).open(newline="") as f:
            return list(csv.reader(f))

    def test_formules_echappees_et_colonnes_libres_ignorees(self):
        JournalCSV(self.dossier).ecrire("/decision", {
            "id": "t1", "description": '=HYPERLINK("http://evil","x")', "reaction": "+1", "nature": "@SUM(A1)",
            "statut_jev": "-2", "colonne_pirate": "=1+1", "seuil": 0.85})
        entete, ligne = self.lire("decisions_jev.csv")
        self.assertEqual(entete, ["date", *COLONNES["/decision"]])
        d = dict(zip(entete, ligne))
        self.assertEqual(d["description"], "'=HYPERLINK(\"http://evil\",\"x\")")
        self.assertEqual(d["reaction"], "'+1")
        self.assertEqual(d["nature"], "'@SUM(A1)")
        self.assertEqual(d["statut_jev"], "'-2")
        self.assertEqual(d["seuil"], "0.85")
        self.assertNotIn("colonne_pirate", entete)

    def test_nettoyer(self):
        self.assertEqual(nettoyer(-3), -3)                 # vrai nombre : pas une formule
        self.assertEqual(nettoyer({"a": 1}), "")
        self.assertEqual(len(nettoyer("a" * 1000)), 300)

    def test_entetes_identiques_aux_vrais_csv(self):
        """Les CSV existants ne doivent pas être archivés par la nouvelle version (lecture seule)."""
        for route, nom in (("/decision", "decisions_jev.csv"), ("/log", "resultats_parties.csv")):
            vrai = ROOT / nom
            if not vrai.exists():
                continue
            with vrai.open(newline="") as f:
                self.assertEqual(next(csv.reader(f)), ["date", *COLONNES[route]], nom)


class TestL2TimeoutsEtRetries(unittest.TestCase):
    def test_429_puis_succes(self):
        h = HorlogeFictive()
        api = FausseAPI(urllib.error.HTTPError("u", 429, "rate", {}, io.BytesIO(b"")), {"answers": {}})
        rep = appeler({"q": 1}, FAUSSE_CLE, ouvrir=api, horloge=h, dormir=h.dormir)
        self.assertEqual(rep, {"answers": {}})
        self.assertEqual(len(api.requetes), 2)

    def test_jev_qui_pend_respecte_le_delai_global(self):
        h = HorlogeFictive()

        def pend(req, timeout):                       # simule une API qui ne répond jamais
            h.t += timeout
            raise TimeoutError()
        rep = appeler({"q": 1}, FAUSSE_CLE, ouvrir=pend, horloge=h, dormir=h.dormir)
        self.assertEqual(rep, {"error": "TimeoutError"})
        self.assertLessEqual(h.t, 10.0)

    def test_erreur_400_sans_retry_ni_detail(self):
        err = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(f"cle {FAUSSE_CLE} invalide".encode()))
        api = FausseAPI(err)
        rep = appeler({"q": 1}, FAUSSE_CLE, ouvrir=api)
        self.assertEqual(rep, {"error": "HTTP 400"})
        self.assertEqual(len(api.requetes), 1)


class TestVersionEtCle(BaseServeur):
    """Vraie route /jev avec une fausse API : modèle imposé, version journalisée, clé jamais exposée."""
    fake = False

    def setUp(self):
        self.api = FausseAPI({"model": "jev-1.13.0", "usage": {"input_tokens": 42}, "answers": {"z_t1": {"noul": 0.9}}},
                             urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(FAUSSE_CLE.encode())))
        super().setUp()

    def test_modele_impose_journalise_et_cle_cachee(self):
        code, _, body = self.post("/jev", {**NOUL, "model": "jev-le-plus-cher"})
        self.assertEqual(code, 200)
        req, _ = self.api.requetes[0]
        self.assertEqual(json.loads(req.data)["model"], MODELE_JEV)
        self.assertEqual(req.get_header("Authorization"), f"Bearer {FAUSSE_CLE}")   # la clé ne part que vers l'API
        code2, _, body2 = self.post("/jev", NOUL)                                     # erreur API contenant la clé
        self.assertEqual(code2, 502)
        journal = (self.dossier / "jev_appels.jsonl").read_text()
        for texte in (body, body2, journal.encode()):
            self.assertNotIn(FAUSSE_CLE.encode(), texte)
        lignes = [json.loads(l) for l in journal.splitlines()]
        self.assertEqual(lignes[0]["modele_demande"], MODELE_JEV)
        self.assertEqual(lignes[0]["modele_servi"], "jev-1.13.0")
        self.assertEqual(lignes[0]["tokens"], 42)
        self.assertEqual(lignes[1]["statut"], "HTTP 401")


if __name__ == "__main__":
    unittest.main()
