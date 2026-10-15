"""
Tests du noyau vigie/ (phase 6). Aucun appel réel : les réponses JEV viennent de cache_jev.json.

    python3 -m unittest discover tests
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from server.app import creer_serveur
from server.cache_jev import CacheJEV
from server.websocket import FermetureWS, cle_acceptation, lire_trame
from vigie.fusion import P, Calibrateur
from vigie.jeu import R, RepondeurJeu, SessionJeu
from vigie.noyau import JournalRepondeur, RegleViolee, verifier_repondeurs
from vigie.types import Decision, Piste

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache_jev.json"


def node(code: str) -> object:
    sortie = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True, cwd=ROOT)
    return json.loads(sortie.stdout)


class TestMemesConstantesQueLeJeu(unittest.TestCase):
    """Le portage Python doit utiliser exactement les constantes de web/js/config.js."""

    def test_constantes_et_calibration(self):
        cfg = (ROOT / "web/js/config.js").as_uri()
        cal = (ROOT / "web/js/analysis/calibration.js").as_uri()
        js = node(f"""import * as C from {json.dumps(cfg)}; import {{ creerCalibrateur }} from {json.dumps(cal)};
            const c = creerCalibrateur();
            console.log(JSON.stringify({{ F: C.FUSION, O: C.ORDONNANCEMENT, INCOH_MAX: C.INCOH_MAX,
              PORTEE_SOMMATION: C.PORTEE_SOMMATION, COOLDOWN_SOMMATION: C.COOLDOWN_SOMMATION, BARRICADE_Z: C.BARRICADE_Z,
              MUNITIONS: C.MUNITIONS, MAX_SOMMATIONS: C.MAX_SOMMATIONS,
              touche: [5, 20, 30, 45, 59].map(C.chanceTouche), llr: [0.05, 0.5, 0.705, 0.835, 0.97].map(p => c.llr(p)) }}));""")
        F = js["F"]
        self.assertEqual((P.prior, P.p_clip, P.p_bouge_si_zombie, P.p_bouge_si_humain, P.p_bouge_encore_si_humain),
                         (F["prior"], F["pClip"], F["pBougeSiZombie"], F["pBougeSiHumain"], F["pBougeEncoreSiHumain"]))
        self.assertEqual((list(P.fenetre), P.seuil_arret, P.seuil_bouge, P.alpha, P.beta, P.incoh_max),
                         (F["fenetre"], F["seuilArret"], F["seuilBouge"], F["alpha"], F["beta"], js["INCOH_MAX"]))
        self.assertEqual((R.portee_sommation, R.cooldown_sommation, R.barricade_z, R.munitions, R.max_sommations,
                          R.portee_opportunite, R.recharge_tactique),
                         (js["PORTEE_SOMMATION"], js["COOLDOWN_SOMMATION"], js["BARRICADE_Z"], js["MUNITIONS"],
                          js["MAX_SOMMATIONS"], js["O"]["porteeOpportunite"], js["O"]["rechargeTactique"]))
        self.assertEqual([R.chance_touche(d) for d in (5, 20, 30, 45, 59)], js["touche"])
        cal_py = Calibrateur.depuis_js()
        for p, l in zip((0.05, 0.5, 0.705, 0.835, 0.97), js["llr"]):
            self.assertAlmostEqual(cal_py.llr(p), l, places=12)


class SourceReelle:
    nom, reel = "rtsp:portail", True


class TestRegleMondeReel(unittest.TestCase):
    def test_source_reelle_refuse_un_repondeur_qui_agit(self):
        with self.assertRaises(RegleViolee):
            verifier_repondeurs(SourceReelle(), [RepondeurJeu()])

    def test_source_reelle_accepte_les_repondeurs_informatifs(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(len(verifier_repondeurs(SourceReelle(), [JournalRepondeur(Path(d) / "j.jsonl")])), 1)

    def test_le_jeu_est_une_simulation(self):
        self.assertFalse(SessionJeu(client=lambda b: (200, {})).reel)


class TestJournal(unittest.TestCase):
    def test_une_ligne_par_action_ou_changement_de_cible(self):
        with tempfile.TemporaryDirectory() as d:
            j = JournalRepondeur(Path(d) / "j.jsonl")
            pistes = {"t1": Piste("t1", L=6.0, preuves={"prior": 0, "jev": 3, "cine": 3})}
            for dec in (Decision(), Decision(cible="t1"), Decision(cible="t1"), Decision(cible="t1", sommer=True), Decision()):
                j.repondre("jeu", 1.0, dec, pistes)
            lignes = [json.loads(l) for l in (Path(d) / "j.jsonl").read_text().splitlines()]
            self.assertEqual([(l["cible"], l["sommer"]) for l in lignes], [("t1", False), ("t1", True), (None, False)])
            self.assertEqual(lignes[0]["L"], 6.0)


# ---------- WebSocket /vigie ----------
def serveur_cache(dossier: Path):
    """Serveur réel, JEV « sans réseau » : réponses du cache seulement (toute question manquante ⇒ erreur)."""
    def pas_de_reseau(*_, **__):
        raise OSError("aucun appel réel pendant les tests")
    srv = creer_serveur(0, cle="test-sans-reseau", fake=False, dossier_donnees=dossier, ouvrir=pas_de_reseau,
                        cache=CacheJEV(CACHE) if CACHE.exists() else None)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def ws_brut(port: int, origine: str | None = None) -> tuple[socket.socket, bytes]:
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    cle = base64.b64encode(os.urandom(16)).decode()
    entetes = [f"GET /vigie HTTP/1.1", f"Host: localhost:{port}", "Upgrade: websocket", "Connection: Upgrade",
               f"Sec-WebSocket-Key: {cle}", "Sec-WebSocket-Version: 13"] + ([f"Origin: {origine}"] if origine else [])
    s.sendall(("\r\n".join(entetes) + "\r\n\r\n").encode())
    rep = b""
    while b"\r\n\r\n" not in rep:
        bloc = s.recv(4096)
        if not bloc:
            break
        rep += bloc
    return s, rep


def envoyer_masque(s: socket.socket, obj: dict):
    data, m = json.dumps(obj).encode(), os.urandom(4)
    s.sendall(bytes([0x81, 0x80 | len(data)]) + m + bytes(b ^ m[i % 4] for i, b in enumerate(data)))


class TestWebSocket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = serveur_cache(Path(cls.tmp.name))
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.tmp.cleanup()

    def test_vecteur_rfc6455(self):
        self.assertEqual(cle_acceptation("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_origine_etrangere_refusee(self):
        s, rep = ws_brut(self.port, origine="http://evil.example")
        self.assertIn(b" 403 ", rep.split(b"\r\n")[0]); s.close()

    def test_jeton_invalide_ferme_la_connexion(self):
        s, rep = ws_brut(self.port, origine=f"http://localhost:{self.port}")
        self.assertIn(b" 101 ", rep.split(b"\r\n")[0])
        envoyer_masque(s, {"type": "bonjour", "jeton": "faux"})
        b0, b1 = s.recv(2)
        self.assertEqual(b0 & 0x0F, 0x8)                              # trame de fermeture
        self.assertEqual(struct.unpack("!H", s.recv(b1 & 0x7F)[:2])[0], 1008)
        s.close()

    def test_trame_non_masquee_refusee(self):
        import io
        with self.assertRaises(FermetureWS):
            lire_trame(io.BytesIO(bytes([0x81, 0x02]) + b"{}"))

    @unittest.skipUnless(CACHE.exists(), "cache_jev.json absent")
    def test_parite_partie_par_partie_avec_la_v5_javascript(self):
        """Mêmes graines, mêmes réponses JEV : le noyau Python et la v5 JS donnent exactement les mêmes parties."""
        for langue, n in (("en", 3), ("fr", 2)):
            r = subprocess.run(["node", "tests/vigie_parite.mjs", "--port", str(self.port), "--parties", str(n),
                                "--langue", langue], capture_output=True, text=True, cwd=ROOT, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("0 écart(s) · 0 humain(s) abattu(s)", r.stdout)


if __name__ == "__main__":
    unittest.main()
