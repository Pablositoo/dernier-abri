// Tous les textes de l'interface ET des questions envoyées à JEV (FR + EN obligatoires)
import { chanceTouche } from "../config.js";

export const TXT = {
  fr: {
    mode: "Mode", temps: "Temps", abri: "Abri", cerveau: "Cerveau JEV", seuilLbl: "Seuil de tir (↑/↓)", latence: "Latence", appels: "Appels / tokens",
    decision: "Décision :", regles: "Règles de tir : p(zombie) ≥ seuil · 2 questions cohérentes · réaction à la sommation lue · pas les mains en l'air · ligne de tir dégagée",
    reglesV3: "Règles v3 : preuve cumulée ≥ seuil de Wald (risque humain 0,5 %) · JEV ET mouvement d'accord · réaction lue · pas les mains en l'air · ligne de tir dégagée · dans le doute : 2e sommation, jamais de tir", reglesV4: " · v4 : tir d'opportunité jusqu'à 45 m dès que la ligne est libre · rechargement tactique",
    reglesV5: " · v5 : probabilités JEV calibrées (Platt, jev-1.13.0) ; autre modèle servi ⇒ calibration désactivée",
    cri: "📢 STOP ! LEVEZ LES MAINS !", titre: "DERNIER ABRI<small>Une IA décide qui vit · v5.0</small>",
    intro: "Les zombies marchent vers ta barricade. Des survivants courent aussi vers toi, et certains blessés ressemblent à s'y méprendre à des infectés. <b>JEV ne voit pas l'image</b> : il lit seulement la description de chaque silhouette et décide <b>sur qui tirer, et quand</b>.",
    b1: "<strong>1 · JEV v5</strong>Classe, somme, mesure<br>le mouvement, puis tire.", b2: "<strong>2 · JEV v1</strong>Ancienne méthode :<br>1 question « sur qui tirer ».",
    b3: "<strong>3 · Bot</strong>Règle naïve : tire sur<br>le plus proche.", b4: "<strong>4 · Toi</strong>Souris pour viser,<br>clic pour tirer.",
    legende: "<span>1–4 changer de mode</span><span>↑/↓ seuil JEV</span><span>L langue</span><span>R rejouer</span><span>Échap menu</span>",
    fin: "FIN DE PARTIE", rejouer: "Rejouer", toi: "Toi", enregistre: "Partie enregistrée dans <b>resultats_parties.csv</b>",
    modes: { jev: "JEV", jev1: "JEV v1", regle: "BOT NAÏF", manuel: "TOI" },
    noms: { zombie: "ZOMBIE", blesse_zombie: "ZOMBIE BLESSÉ", humain: "HUMAIN", blesse_humain: "HUMAIN BLESSÉ" },
    erreur: "ERREUR", rate: "raté", recharge: "Rechargement…", munitions: "Munitions", tirerSur: "tirer sur ", attendre: "attendre",
    sommation: "📢 SOMMATION : « Stop ! Levez les mains ! »", sommationCiblee: ids => `📢 2e SOMMATION → ${ids.join(", ")} : « Toi ! Arrête-toi ! »`, bloque: id => `⛔ ${id} : tir bloqué, un survivant est dans la ligne de tir`,
    derive: (servi, attendu) => `⚠ DÉRIVE JEV : modèle servi ${servi} ≠ ${attendu} → calibration désactivée (probabilités brutes)`,
    morsure: id => `MORSURE ! ${id} a atteint la barricade`, sauve: id => `${id} est à l'abri · +15`,
    tombe: "L'abri est tombé", tenu: "Tu as tenu jusqu'au bout", pasCle: "Pas de clé API", err: "Erreur : ",
    stats: ["Score", "Zombies tués", "Humains sauvés", "Humains abattus", "Morsures", "Précision", "Appels JEV", "Sommations"],
    contexte: "Contexte : un défenseur protège un abri. Une sommation « Stop ! Levez les mains ! » est criée aux silhouettes qui approchent : un survivant humain obéit, un zombie l'ignore.",
    // sans id ni distance : la réponse ne dépend que de ce qui est observé (cache JEV possible)
    fiche: (c, r) => `Une silhouette. Description : ${c.desc}. Réaction à la sommation : ${r ?? "sommation pas encore faite"}.`,
    qZ: "Cette cible est un zombie (infecté hostile).", qH: "Cette cible est un survivant humain vivant.",
    v1Crit: c => `Tirer sur ${c.id} : ${c.desc} (${Math.round(c.distance)} m, chance ${Math.round(chanceTouche(c.distance) * 100)} % de toucher)`,
    v1Wait: "Ne pas tirer maintenant (cible humaine, trop loin ou trop incertaine)",
    v1Instr: "Tu défends un abri contre des zombies. Des survivants humains courent aussi vers l'abri : ne JAMAIS tirer sur un humain. Les munitions sont limitées : un tir de loin rate souvent. Choisis la meilleure action maintenant.",
  },
  en: {
    mode: "Mode", temps: "Time", abri: "Shelter", cerveau: "JEV Brain", seuilLbl: "Fire threshold (↑/↓)", latence: "Latency", appels: "Calls / tokens",
    decision: "Decision:", regles: "Rules of engagement: p(zombie) ≥ threshold · 2 consistent questions · reaction to the warning read · hands not raised · clear line of fire",
    reglesV3: "v3 rules: accumulated evidence ≥ Wald threshold (human risk 0.5 %) · JEV AND movement agree · reaction read · hands not raised · clear line of fire · when in doubt: 2nd warning, never fire", reglesV4: " · v4: opportunity shot up to 45 m as soon as the line is clear · tactical reload",
    reglesV5: " · v5: calibrated JEV probabilities (Platt, jev-1.13.0); different model served ⇒ calibration disabled",
    cri: "📢 STOP! HANDS UP!", titre: "LAST SHELTER<small>An AI decides who lives · v5.0</small>",
    intro: "Zombies are walking toward your barricade. Survivors are running toward you too, and some wounded people look just like the infected. <b>JEV can't see the image</b>: it only reads each figure's description and decides <b>who to shoot, and when</b>.",
    b1: "<strong>1 · JEV v5</strong>Classify, warn, measure<br>movement, then fire.", b2: "<strong>2 · JEV v1</strong>Old method:<br>1 question \"who to shoot\".",
    b3: "<strong>3 · Bot</strong>Naive rule: shoots<br>the closest one.", b4: "<strong>4 · You</strong>Mouse to aim,<br>click to shoot.",
    legende: "<span>1–4 switch mode</span><span>↑/↓ JEV threshold</span><span>L language</span><span>R replay</span><span>Esc menu</span>",
    fin: "GAME OVER", rejouer: "Play again", toi: "You", enregistre: "Game saved to <b>resultats_parties.csv</b>",
    modes: { jev: "JEV", jev1: "JEV v1", regle: "NAIVE BOT", manuel: "YOU" },
    noms: { zombie: "ZOMBIE", blesse_zombie: "WOUNDED ZOMBIE", humain: "HUMAN", blesse_humain: "WOUNDED HUMAN" },
    erreur: "ERROR", rate: "missed", recharge: "Reloading…", munitions: "Ammo", tirerSur: "shoot ", attendre: "wait",
    sommation: "📢 WARNING: \"Stop! Hands up!\"", sommationCiblee: ids => `📢 2nd WARNING → ${ids.join(", ")}: "You! Stop right there!"`, bloque: id => `⛔ ${id}: shot blocked, a survivor is in the line of fire`,
    derive: (servi, attendu) => `⚠ JEV DRIFT: served model ${servi} ≠ ${attendu} → calibration disabled (raw probabilities)`,
    morsure: id => `BITE! ${id} reached the barricade`, sauve: id => `${id} is safe · +15`,
    tombe: "The shelter has fallen", tenu: "You held out to the end", pasCle: "No API key", err: "Error: ",
    stats: ["Score", "Zombies killed", "Humans saved", "Humans shot", "Bites", "Accuracy", "JEV calls", "Warnings"],
    contexte: "Context: a defender protects a shelter. A warning \"Stop! Hands up!\" is shouted at approaching figures: a human survivor obeys, a zombie ignores it.",
    fiche: (c, r) => `A figure. Description: ${c.desc}. Reaction to the warning: ${r ?? "no warning given yet"}.`,
    qZ: "This target is a zombie (hostile infected).", qH: "This target is a living human survivor.",
    v1Crit: c => `Shoot ${c.id}: ${c.desc} (${Math.round(c.distance)} m, ${Math.round(chanceTouche(c.distance) * 100)} % chance to hit)`,
    v1Wait: "Don't shoot now (human target, too far or too uncertain)",
    v1Instr: "You defend a shelter against zombies. Human survivors are also running toward the shelter: NEVER shoot a human. Ammo is limited: long shots often miss. Choose the best action now.",
  },
};

let LANG = "fr";
if (typeof window !== "undefined")   // navigateur seulement (le module est aussi chargé en Node pour le benchmark)
  try { LANG = localStorage.getItem("lang") || (navigator.language?.startsWith("fr") ? "fr" : "en"); } catch {}
export const langue = () => LANG;
export const tr = () => TXT[LANG];

export function appliquerLangue(l) {
  LANG = l; try { localStorage.setItem("lang", l); } catch {}
  document.documentElement.lang = l;
  document.querySelectorAll("[data-i18n]").forEach(e => e.innerHTML = tr()[e.dataset.i18n]);
  document.querySelectorAll("[data-lang]").forEach(b => b.classList.toggle("on", b.dataset.lang === l));
}
