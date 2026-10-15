"""
WebSocket minimal (RFC 6455), stdlib uniquement : poignée de main + trames texte, ping/pong, fermeture.
Utilisé par /vigie (le jeu piloté par le noyau). Trames client masquées obligatoires, taille bornée.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TAILLE_MAX = 1024 * 1024
TEXTE, FERMER, PING, PONG = 0x1, 0x8, 0x9, 0xA


class FermetureWS(Exception):
    pass


def cle_acceptation(cle_client: str) -> str:
    return base64.b64encode(hashlib.sha1((cle_client + GUID).encode()).digest()).decode()


def _lire(f, n: int) -> bytes:
    data = f.read(n)
    if len(data) < n:
        raise FermetureWS("connexion fermée")
    return data


def lire_trame(f) -> tuple[int, bytes]:
    b0, b1 = _lire(f, 2)
    op, masque, n = b0 & 0x0F, b1 & 0x80, b1 & 0x7F
    if not b0 & 0x80:
        raise FermetureWS("trames fragmentées non prises en charge")
    if not masque:
        raise FermetureWS("trame client non masquée")
    if n == 126:
        n = struct.unpack("!H", _lire(f, 2))[0]
    elif n == 127:
        n = struct.unpack("!Q", _lire(f, 8))[0]
    if n > TAILLE_MAX:
        raise FermetureWS("trame trop grande")
    m = _lire(f, 4)
    data = bytes(b ^ m[i % 4] for i, b in enumerate(_lire(f, n))) if n < 4096 else _demasquer(_lire(f, n), m)
    return op, data


def _demasquer(data: bytes, m: bytes) -> bytes:
    cle = (m * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(cle, "big")).to_bytes(len(data), "big")


def ecrire_trame(f, op: int, data: bytes):
    n = len(data)
    entete = bytes([0x80 | op]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack("!H", n) if n < 65536
                                   else bytes([127]) + struct.pack("!Q", n))
    f.write(entete + data)
    f.flush()


class ConnexionWS:
    def __init__(self, rfile, wfile):
        self.rfile, self.wfile = rfile, wfile

    def recevoir(self) -> dict:
        """→ prochain message JSON (objet). Répond aux ping ; lève FermetureWS à la fermeture."""
        while True:
            op, data = lire_trame(self.rfile)
            if op == PING:
                ecrire_trame(self.wfile, PONG, data)
            elif op == FERMER:
                try:
                    ecrire_trame(self.wfile, FERMER, data[:2])
                finally:
                    raise FermetureWS("fermée par le client")
            elif op == TEXTE:
                msg = json.loads(data.decode("utf-8"))
                if not isinstance(msg, dict):
                    raise ValueError("objet JSON attendu")
                return msg

    def envoyer(self, msg: dict):
        ecrire_trame(self.wfile, TEXTE, json.dumps(msg, ensure_ascii=False).encode("utf-8"))

    def fermer(self, code: int = 1000, raison: str = ""):
        try:
            ecrire_trame(self.wfile, FERMER, struct.pack("!H", code) + raison.encode()[:100])
        except OSError:
            pass
