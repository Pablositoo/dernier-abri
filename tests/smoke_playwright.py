"""
Fumée navigateur : une partie complète en mode JEV v2, JEV simulé, vitesse ×8.

    python3 server.py --fake --no-browser --port 8765 &
    python3 tests/smoke_playwright.py [--port 8765] [--mode jev]
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mode", default="jev", choices=["jev", "jev1", "regle"])
    args = ap.parse_args()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        page = nav.new_page()
        erreurs: list[str] = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.goto(f"http://localhost:{args.port}/?speed=8&lite")
        page.wait_for_function("window.__debug !== undefined")
        page.evaluate(f"window.__debug.nouvellePartie({args.mode!r})")
        page.wait_for_function("window.__debug.partie.fini", timeout=60_000)
        res = page.evaluate("""() => { const d = window.__debug;
            return { appels: d.jevStats.appels, err: d.jevStats.err, stats: d.partie.stats }; }""")
        nav.close()
    print(res)
    ok = not erreurs and (args.mode == "regle" or (res["appels"] > 0 and not res["err"]))
    if args.mode == "jev":
        ok = ok and res["stats"]["humains_tues"] == 0
    print("FUMÉE OK" if ok else f"FUMÉE ÉCHEC {erreurs}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
