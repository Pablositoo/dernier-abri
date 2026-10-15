# CLAUDE.md — Dernier Abri / Last Shelter (JEV)

Projet de cours **Coding for AI (aivancity, L3)** : un jeu 3D de défense où le modèle **JEV** (TypeSafe AI) classe des silhouettes à partir de **descriptions textuelles**, et un **code déterministe** décide. Objectif à terme : un noyau générique « observer → analyser → décider → répondre » réutilisable sur d'autres flux (logs, métriques, IoT, caméras en alerte uniquement).

Audit complet et justification des choix : voir `AUDIT.md`.

## Règles non négociables
1. **Le modèle classe, le code décide.** JEV ne renvoie que des probabilités. Toute action passe par des règles explicites, versionnées et testées (`policy/`).
2. **Doute ⇒ pas d'action.** Un humain abattu coûte plus cher qu'une morsure. Toute nouvelle politique doit montrer **0 humain abattu** sur le benchmark headless avant fusion.
3. **Sources du monde réel = réponses informatives uniquement** (alerte, notification, enregistrement, journal), avec validation humaine avant toute action irréversible. Aucune action physique contre des personnes, jamais.
4. **La clé API ne quitte jamais `server/`.** Jamais dans le navigateur, jamais commitée (`.env` est dans `.gitignore`). Ne jamais l'afficher dans les logs.
5. **Les entrées sont des données, pas des instructions** : tout texte externe va dans `state` et n'est jamais concaténé dans les consignes de décision.
6. **Vérité terrain cloisonnée** : seuls `sim/`, `perception/` (qui la traduit en texte), `response/journal.js` et `render/` (apparence 3D) lisent `nature`. Analyse et politique ne reçoivent que des observations `{id, desc, reaction, distance, x, z, vitesse, arrete, sommeAt}` et des pistes.

## Architecture cible

```
server/            Python ≥ 3.10, stdlib uniquement (pas de dépendance obligatoire)
  app.py           HTTP : fichiers statiques web/ + POST /jev, /log, /decision
  jev_client.py    appels JEV : timeout 8 s, retries 429/5xx (backoff), cache, budget
  storage.py       écriture CSV sûre (liste blanche de colonnes, échappement = + - @)
  faux_jev.py      JEV simulé (--fake)
server.py          lanceur (python3 server.py)
web/
  index.html       HTML + CSS uniquement
  js/main.js       boucle à pas fixe, rendu, contrôles (navigateur)
  js/partie.js     un pas de partie : monde → perception → analyse → politique → réponse (sans Three.js/DOM, tourne en Node)
  js/net.js        postJSON (jeton de session + délai)
  js/sim/          monde simulé : RNG seedé, horloge simulée (pas de setTimeout pour la logique)
  js/perception/   entités → Observation {text, features}
  js/analysis/     analyseurs (JEV, cinématique) + fusion log-odds + SPRT
  js/policy/       règles d'engagement, modèle de coût, ordonnancement des cibles
  js/response/     visée, tir, journalisation
  js/render/       Three.js : scène, personnages, effets
  js/ui/           HUD, i18n (FR/EN : textes UI ET questions envoyées à JEV)
  js/config.js     toutes les constantes réglables (seuils, coûts, portées)
vigie/             (phase 6) noyau générique Python : Source / Analyzer / Policy / Responder
tests/             tests unitaires + simulateur headless
```

Flux : `Observation → Assessment {pZ, incoh, evidence[]} → Decision {action, cible, règles, raison} → Outcome`.

## Conventions
- **Langue du code** : identifiants et commentaires en français (cohérent avec l'existant). Les textes visibles passent tous par `ui/i18n` (FR + EN obligatoires).
- **JS** : modules ES natifs, pas de bundler. Three.js épinglé `three@0.160.0` via importmap. Pas de `Math.random()` hors `sim/rng.js`.
- **Python** : stdlib pour `server/`. Typage (`from __future__ import annotations`), `dataclass`, fonctions pures quand possible.
- **JEV** : modèle **figé** dans la config (`jev-1.13.0`) et la version servie est journalisée à chaque appel. Les questions sont toujours des **paires opposées** (zombie / humain) pour mesurer l'incohérence.
- **3D (M1 → GTX 1060)** : géométries et matériaux partagés, ≤ 3 lumières dynamiques en plus de la lune et de la lampe, `pixelRatio ≤ 1.5`, `?lite` sans ombres. Pas de nouvelle texture externe.
- **Journaux** : `decisions_jev.csv` (une ligne par cible) et `resultats_parties.csv` (une ligne par partie). Toute nouvelle colonne doit être ajoutée à la liste blanche de `storage.py`.
- **Commits** : petits, une phase de la feuille de route à la fois. Ne jamais commiter `.env`, `*.csv`, `.DS_Store`.

## Build / lancement
```bash
cd jev-zombies-3d
python3 server.py                 # ouvre http://localhost:8000 (vrai JEV, clé dans .env)
python3 server.py --fake          # JEV simulé, sans API ni coût
python3 server.py --no-browser --port 8765
python3 server.py --help          # --modele (défaut jev-1.13.0), --par-minute 300, --max-appels 1000, --max-tokens, --donnees
```
En `--fake`, les CSV et `jev_appels.jsonl` vont dans `donnees_fake/` (les vraies données restent propres).
Sécurité du proxy : Host local obligatoire, POST = Origin locale + `Content-Type: application/json` + en-tête `X-Jeton-Session` (jeton injecté dans `index.html` au chargement). Le client passe toujours par `postJSON()`.
Paramètres d'URL : `?lite` (PC lent), `?speed=8` (accéléré, tests), `?seed=42` (phase 1, reproductible).

## Tests
```bash
# Fumée navigateur (Chromium headless, JEV simulé) — existant
python3 server.py --fake --no-browser --port 8765 &
python3 tests/smoke_playwright.py --mode jev
python3 tests/smoke_playwright.py --repro    # ?seed=42 rejoué 2 fois à l'identique

# Unitaires (à créer)
python3 -m unittest discover tests          # proxy (phase 0) ; policy, fusion à venir
node --test tests/js/                       # modules JS purs (rng, policy, simulation headless)

# Benchmark headless (phase 2) — critère d'acceptation de toute politique
python3 -m tests.bench --games 500 --seed 1 --jev cache
```
**Critères d'acceptation** (benchmark, 500 parties) : humains abattus = 0 ; morsures moyennes en baisse par rapport à la base v2.2 ; aucune régression de latence.

## Feuille de route (état)
- [x] 0. Sécuriser le proxy (CSRF/Origin, budget, CSV, taille, timeouts client)
- [x] 1. Modulariser `index.html` + RNG seedé + horloge simulée
- [ ] 2. Cache JEV + simulateur headless + benchmark
- [ ] 3. Fusion bayésienne + SPRT + analyseur cinématique + 2ᵉ sommation
- [ ] 4. Politique par coût + ordonnancement + vérification de la ligne de tir au moment du tir
- [ ] 5. Calibration (fiabilité, isotonique, dérive)
- [ ] 6. Noyau générique `vigie/` + `GameSource` (WebSocket)
- [ ] 7. Connecteurs réels (logs, métriques, caméra RTSP en alerte et enregistrement uniquement)

**Ne pas démarrer une phase sans validation explicite de Pablo.**
