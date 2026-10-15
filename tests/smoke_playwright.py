"""
Fumée navigateur (Chromium headless, JEV simulé, vitesse ×8).

    python3 server.py --fake --no-browser --port 8765 &
    python3 tests/smoke_playwright.py [--port 8765] [--mode jev]   # une partie complète
    python3 tests/smoke_playwright.py --repro                      # ?seed=42 rejoué 2 fois à l'identique (bot)
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


def jouer(nav, port: int, mode: str, graine: int | None = None) -> tuple[dict, list[str]]:
    page = nav.new_page()
    erreurs: list[str] = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("console", lambda m: m.type == "error" and erreurs.append(m.text))
    page.goto(f"http://localhost:{port}/?speed=8&lite" + (f"&seed={graine}" if graine is not None else ""))
    page.wait_for_function("window.__debug !== undefined")
    page.evaluate(f"window.__debug.nouvellePartie({mode!r})")
    page.wait_for_function("window.__debug.etat().fini", timeout=60_000)
    res = page.evaluate("window.__debug.etat()")
    page.close()
    return res, erreurs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mode", default="jev", choices=["jev", "jev1", "regle"])
    ap.add_argument("--repro", action="store_true", help="vérifie que ?seed=42 donne deux fois la même partie")
    args = ap.parse_args()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        if args.repro:
            (a, ea), (b, eb) = jouer(nav, args.port, "regle", 42), jouer(nav, args.port, "regle", 42)
            print(a, b, sep="\n")
            ok = a == b and not ea and not eb
        else:
            res, erreurs = jouer(nav, args.port, args.mode)
            print(res)
            ok = not erreurs and (args.mode == "regle" or (res["appels"] > 0 and not res["err"]))
            if args.mode == "jev":
                ok = ok and res["stats"]["humains_tues"] == 0
            if erreurs:
                print(erreurs)
        nav.close()
    print("FUMÉE OK" if ok else "FUMÉE ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
