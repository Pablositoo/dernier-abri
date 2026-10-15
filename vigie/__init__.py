"""
Vigie — noyau générique « observer → analyser → décider → répondre » (phase 6).

    Source ──Observation──▶ Piste ──Analyseurs (JEV, cinématique…)──▶ Fusion log-odds + SPRT ──▶ Politique ──▶ Répondeurs

- types.py      Observation, Piste, Decision : le vocabulaire commun à toutes les sources
- fusion.py     preuves en log-rapport de vraisemblance, calibration, test séquentiel de Wald
- analyseurs.py JEV (questions opposées, latence, dérive) et cinématique (s'arrête / continue après une sommation)
- noyau.py      contrat des répondeurs + règle non négociable : source réelle ⇒ réponses informatives uniquement
- jeu.py        domaine « jeu » : la politique v5 portée depuis web/js (mêmes résultats, testé partie par partie)

Python stdlib uniquement. Le jeu (navigateur ou Node) se connecte en WebSocket sur /vigie (server/app.py).
"""
