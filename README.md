# Dernier Abri / Last Shelter

**Propulsé par [JEV](#le-rôle-de-jev), le modèle de décision de TypeSafe AI.**

**Une IA classe, le code décide.** Jeu 3D de défense où un modèle d'IA (JEV, TypeSafe AI) estime, à partir d'une simple description textuelle, si une silhouette dans la nuit est un zombie ou un survivant, et où un code déterministe, testé et auditable décide de tirer… ou pas.

> *Powered by JEV (TypeSafe AI). An AI classifies, deterministic code decides. A 3D browser game used as a test bench for decision-making under uncertainty: Bayesian evidence fusion, Wald's sequential test, calibration, drift detection, and a reusable "observe → analyse → decide → respond" core. Zero humans shot across thousands of simulated games.*

![Capture du jeu : sommation, cerveau JEV et décisions justifiées](docs/capture_jeu.png)

Projet du cours **Coding for AI** (L3 Data Science & IA, aivancity), construit autour de **JEV** : c'est JEV qui lit chaque silhouette et donne la probabilité sur laquelle tout le système de décision s'appuie.

---

## L'idée en une minute

| Principe | Concrètement |
|---|---|
| **Le modèle classe, le code décide** | JEV ne renvoie que des probabilités. Le tir passe par des règles explicites, versionnées et testées. |
| **Doute ⇒ pas d'action** | Un humain abattu coûte plus cher qu'une morsure. Dans le doute : nouvelle sommation, jamais de tir. |
| **Plusieurs preuves indépendantes** | Ce que dit JEV **et** ce que fait la silhouette après « Stop ! Levez les mains ! » (s'arrête-t-elle ?). |
| **Mesurer avant d'affirmer** | Simulateur sans rendu : des milliers de parties reproductibles, comparaisons appariées, intervalles de confiance. |

## Le rôle de JEV

**JEV** (TypeSafe AI) est un modèle de décision **non génératif** : il ne rédige pas de texte, il renvoie des réponses **typées** (une probabilité oui/non, un choix parmi des options, ou un score). Le jeu a été développé et évalué avec le **vrai JEV**, via son API (version figée `jev-1.13.0`).

Comment le jeu l'interroge :

1. **Ce que JEV reçoit** : uniquement du texte, jamais l'image ni la vraie nature de la silhouette. Par exemple : *« Une silhouette. Description : boite, ensanglanté, ne répond pas quand on l'appelle. Réaction à la sommation : tourne la tête vers le bruit puis continue d'avancer sans s'arrêter. »*
2. **Deux questions opposées** par silhouette : « Cette cible est un zombie » et « Cette cible est un survivant humain ». Si JEV est cohérent, les deux probabilités se complètent. Sinon, la lecture est jugée **incohérente** et ne compte pas comme preuve.
3. **Avant puis après la sommation** : JEV relit la fiche une fois la réaction connue (s'est arrêté, mains en l'air ? a continué ?).
4. **Ce que JEV ne fait jamais** : décider de tirer. Sa probabilité n'est qu'**une preuve parmi d'autres**, combinée au mouvement mesuré, puis soumise aux règles d'engagement.

Côté pratique :

- **La clé reste sur le serveur local** (`server/`), qui relaie les questions : le navigateur ne la voit jamais.
- **Cache des réponses** : une même fiche donne la même question, donc la même réponse. Après le premier remplissage, des milliers de parties se rejouent avec les vraies réponses de JEV, pour un coût nul. Une partie complète coûte moins d'un centime.
- **Dérive surveillée** : si l'API servait un autre modèle que `jev-1.13.0`, la calibration serait désactivée et une alerte affichée. Un contrôle par « canaris » repose des questions de référence pour vérifier que JEV répond toujours pareil.
- **Sans clé JEV**, `python3 server.py --fake` remplace JEV par un faux modèle à mots-clés : le jeu reste jouable, mais ce n'est pas le vrai JEV.

## Résultats (500 parties, réponses réelles de JEV rejouées depuis un cache)

| Version | Méthode | Morsures / partie (EN) | Humains abattus |
|---|---|---|---|
| v2.2 (départ) | Seuil fixe sur la probabilité de JEV | 4,31 | 0 |
| v3 | Fusion bayésienne (log-odds) + test séquentiel de Wald (SPRT) + mesure du mouvement | **1,25** | 0 |
| v4 | + ordonnancement des tirs (tir d'opportunité, rechargement tactique, verrou au tir) | 0,95 (gain réel ≈ −11 % sur graines jamais vues) | 0 |
| v5 (défaut) | + probabilités JEV calibrées (Platt) | 0,95 (identique), **marge de sécurité ×3,5** | 0 |

- **0 humain abattu** sur toutes les évaluations, y compris un stress test où 50 % des humains paniquent et n'obéissent pas.
- **Calibration** : l'isotonique avait les meilleures métriques… mais, hors échantillon, elle cassait la décision (4,2 morsures/partie). Leçon : *une meilleure calibration n'est pas une meilleure décision*. Détails : [`analyse/calibration.ipynb`](analyse/calibration.ipynb).
- **Bruit de JEV mesuré** (80 appels) : écart-type ≈ 0,01 par question. Les seuils de détection de dérive sont calés dessus.
- **Noyau générique `vigie/`** (Python) : piloté en WebSocket, il rejoue 130 parties **à l'identique** de la version JavaScript.

![Diagramme de fiabilité de JEV](analyse/fiabilite_jev.png)

## Architecture

```mermaid
flowchart LR
  M[Monde simulé<br/>vérité terrain cloisonnée] --> P[Perception<br/>description + réaction]
  P --> J[JEV<br/>2 questions opposées]
  P --> C[Cinématique<br/>s'arrête / continue]
  J --> F[Fusion log-odds<br/>+ calibration]
  C --> F
  F --> S[SPRT de Wald<br/>zombie / humain / incertain]
  S --> R[Règles d'engagement<br/>concordance, ligne de tir…]
  R --> A[Réponse<br/>tir, 2e sommation, attendre]
```

- **Navigateur** (`web/`) : Three.js, modules ES natifs, horloge simulée et graine aléatoire ⇒ parties reproductibles (`?seed=42`).
- **Serveur** (`server/`, Python stdlib) : proxy local qui garde la clé API, cache des réponses JEV, budget d'appels, protections CSRF / DNS rebinding.
- **Noyau** (`vigie/`, Python stdlib) : la même politique, réutilisable sur d'autres sources ; règle codée en dur : *source du monde réel ⇒ réponses informatives uniquement* (alerte, journal), jamais d'action.

## Lancer le jeu

Prérequis : Python ≥ 3.10 et un navigateur récent. Aucune dépendance obligatoire.

```bash
git clone <ce dépôt> && cd jev-zombies-3d
python3 server.py --fake        # JEV simulé : aucune clé, aucun coût
```

Puis ouvrir http://localhost:8000. Touches : `1` JEV, `3` bot naïf, `4` manuel, `L` FR/EN.

**Avec le vrai JEV** : copier `.env.example` en `.env` et y mettre **votre** clé TypeSafe (`TYPESAFE_API_KEY=...`). La clé reste côté serveur : jamais dans le navigateur, les journaux ni le dépôt.

## Tests et benchmark

```bash
python3 -m unittest discover tests        # proxy, cache, calibration, noyau, WebSocket…
node --test tests/js/                     # politique, fusion, sécurité pire cas, simulateur
node tests/bench.mjs --parties 500 --jev fake --langue en   # benchmark headless
```

Le benchmark avec les vraies réponses de JEV (`--jev cache`) nécessite un cache rempli une fois avec une clé (`python3 -m server.remplir_cache`).

## Structure

```
web/js/      sim/ perception/ analysis/ policy/ response/ render/ ui/   (le jeu)
server/      proxy sécurisé, client JEV, cache, détection de dérive, WebSocket
vigie/       noyau générique : fusion, SPRT/CUSUM, analyseurs, répondeurs
analyse/     calibration (notebook), étude du bruit de JEV
tests/       tests Python et JS, simulateur headless, benchmark
```

## Limites (honnêtement)

- Les résultats valent **dans le monde simulé** : 50 descriptions textuelles connues, des comportements modélisés. Un usage réel exigerait de tout re-mesurer sur de vraies données.
- La calibration repose sur 24 fiches cohérentes : peu d'observations indépendantes, d'où la validation croisée par description.
- C'est un jeu et un banc d'essai pédagogique sur la **décision sous incertitude**, pas un système d'armes.

## Crédits

- **JEV, TypeSafe AI** : le cœur du projet. Toute la classification des silhouettes repose sur ses réponses ; sans JEV, ni la fusion des preuves, ni la calibration, ni les résultats ci-dessus n'existeraient. Accès fourni dans le cadre du cours.
- Rendu 3D : [Three.js](https://threejs.org).
- Cours *Coding for AI*, aivancity.

## Licence

[MIT](LICENSE)
