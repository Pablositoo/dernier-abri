"""
Sources du monde réel (phase 7) : elles OBSERVENT seulement (lecture de journaux, compteurs réseau).
Toutes déclarent reel = True ⇒ le noyau n'accepte que des répondeurs informatifs.
"""
from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .types import Observation


# ================= Lignes de journal → observations =================
@dataclass(frozen=True)
class Motif:
    regex: re.Pattern
    genre: str                  # "echec" | "succes"
    entite: str                 # gabarit, ex. "ip:{ip}" ou "sudo:{user}"
    k: str | None = None        # groupe donnant un nombre d'échecs (sudo : « 3 incorrect password attempts »)


MOTIFS_DEFAUT = (
    Motif(re.compile(r"Failed (?:password|publickey|keyboard-interactive/pam) for (?:invalid user )?(?P<user>\S+) from (?P<ip>[0-9a-fA-F.:]+)"),
          "echec", "ip:{ip}"),
    Motif(re.compile(r"Invalid user (?P<user>\S+) from (?P<ip>[0-9a-fA-F.:]+)"), "echec", "ip:{ip}"),
    Motif(re.compile(r"Accepted \S+ for (?P<user>\S+) from (?P<ip>[0-9a-fA-F.:]+)"), "succes", "ip:{ip}"),
    Motif(re.compile(r"sudo(?:\[\d+\])?:\s+(?P<user>[\w.-]+) : (?P<k>\d+) incorrect password attempts?"), "echec", "sudo:{user}", "k"),
    Motif(re.compile(r"sudo(?:\[\d+\])?:\s+(?P<user>[\w.-]+) : .*COMMAND="), "succes", "sudo:{user}"),
)


def analyser_ligne(ligne: str, source: str, t: float, motifs=MOTIFS_DEFAUT) -> Observation | None:
    """Une ligne de journal (écrite potentiellement par un attaquant) → observation, par expressions régulières seulement."""
    for m in motifs:
        r = m.regex.search(ligne)
        if r:
            g = {k: v for k, v in r.groupdict().items() if v is not None}
            k = int(g[m.k]) if m.k and m.k in g else 1
            return Observation(source=source, entite=m.entite.format(**g)[:80], t=t, texte=ligne[:300],
                               signaux={"type": m.genre, "k": min(k, 100), "utilisateur": g.get("user", "")[:40]})
    return None


@dataclass
class SourceFichier:
    """Suit un fichier comme `tail -F` (gère la rotation). Au démarrage, ne relit pas l'historique sauf depuis_debut."""
    chemin: Path
    nom: str = ""
    depuis_debut: bool = False
    reel: bool = True
    _pos: int = 0
    _inode: int | None = None
    _reste: str = ""

    def __post_init__(self):
        self.nom = self.nom or f"journal:{Path(self.chemin).name}"
        if self.chemin.exists() and not self.depuis_debut:
            st = self.chemin.stat()
            self._pos, self._inode = st.st_size, st.st_ino

    def lignes(self) -> list[str]:
        if not self.chemin.exists():
            return []
        st = self.chemin.stat()
        if st.st_ino != self._inode or st.st_size < self._pos:      # rotation ou troncature : on repart du début
            self._pos, self._inode, self._reste = 0, st.st_ino, ""
        with self.chemin.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self._pos)
            bloc = f.read(1_000_000)
            self._pos = f.tell()
        texte = self._reste + bloc
        lignes = texte.split("\n")
        self._reste = lignes.pop()                                   # ligne incomplète : au prochain tour
        return lignes

    def observations(self, t: float) -> list[Observation]:
        return [o for l in self.lignes() if (o := analyser_ligne(l, self.nom, t))]


@dataclass
class SourceCommande:
    """Lit la sortie d'une commande en continu, ex. le journal unifié de macOS :
    log stream --style syslog --predicate 'process == "sudo" OR process == "sshd"'"""
    commande: list[str]
    nom: str = "commande"
    reel: bool = True
    _file: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=10_000))

    def demarrer(self):
        self._proc = subprocess.Popen(self.commande, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                      errors="replace")
        def lire():
            for l in self._proc.stdout:
                try:
                    self._file.put_nowait(l)
                except queue.Full:                                   # inondation : on perd des lignes plutôt que la mémoire
                    pass
        threading.Thread(target=lire, daemon=True).start()
        return self

    def observations(self, t: float) -> list[Observation]:
        out = []
        while True:
            try:
                l = self._file.get_nowait()
            except queue.Empty:
                return out
            if (o := analyser_ligne(l, self.nom, t)):
                out.append(o)

    def arreter(self):
        if getattr(self, "_proc", None):
            self._proc.terminate()


def commande_journal_mac() -> list[str]:
    return ["log", "stream", "--style", "syslog", "--predicate", 'process == "sudo" OR process == "sshd"']


# ================= Compteurs réseau → débits =================
def compteurs_reseau() -> dict[str, tuple[int, int]]:
    """{interface: (octets reçus, octets envoyés)} via psutil s'il est là, sinon `netstat -ib` (macOS)."""
    try:
        import psutil
        return {n: (c.bytes_recv, c.bytes_sent) for n, c in psutil.net_io_counters(pernic=True).items()}
    except ImportError:
        pass
    if not shutil.which("netstat"):
        return {}
    out, vus = {}, set()
    for l in subprocess.run(["netstat", "-ib"], capture_output=True, text=True).stdout.splitlines()[1:]:
        c = l.split()
        if len(c) >= 10 and c[0] not in vus and c[2].startswith("<Link"):
            vus.add(c[0])
            try:
                out[c[0]] = (int(c[6]), int(c[9]))
            except ValueError:
                pass
    return out


@dataclass
class SourceReseau:
    """Débit entrant / sortant par interface (octets/s). Une piste par interface et par sens."""
    nom: str = "reseau"
    reel: bool = True
    ignorer: tuple[str, ...] = ("lo", "lo0", "gif0", "stf0", "anpi", "ap1", "awdl0", "llw0", "utun", "bridge")
    lire_compteurs: object = compteurs_reseau
    _avant: dict | None = None
    _t: float | None = None

    def observations(self, t: float) -> list[Observation]:
        c, out = self.lire_compteurs(), []
        if self._avant is not None and t > self._t:
            dt = t - self._t
            for nom, (rx, tx) in c.items():
                if nom.startswith(self.ignorer) or nom not in self._avant:
                    continue
                for sens, v, v0 in (("entrant", rx, self._avant[nom][0]), ("sortant", tx, self._avant[nom][1])):
                    if v >= v0:
                        debit = (v - v0) / dt
                        out.append(Observation(self.nom, f"{nom}:{sens}", t, f"{nom} {sens} {debit:,.0f} octets/s",
                                               signaux={"type": "metrique", "valeur": debit}))
        self._avant, self._t = c, t
        return out
