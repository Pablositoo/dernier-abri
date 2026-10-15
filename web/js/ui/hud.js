// HUD : chrono, abri, score, munitions, cerveau JEV, fil d'événements, écran de fin
import { DUREE, PV_MAX, MUNITIONS, INCOH_MAX } from "../config.js";
import { score } from "../sim/monde.js";
import { tr } from "./i18n.js";

export const $ = id => document.getElementById(id);

export function feed(txt, cls = "") {
  const d = document.createElement("div"); d.className = cls; d.textContent = txt; $("feed").prepend(d);
  while ($("feed").children.length > 6) $("feed").lastChild.remove();
}

const ICONES = { zombie: "🧟", humain: "🛡️", incertain: "❓", analyse: "…" };

export function hud(partie, jev, vis) {
  const m = partie.monde, s = m.stats;
  $("timer").textContent = Math.max(0, Math.ceil(DUREE - m.t));
  $("score").textContent = score(s);
  $("pv").innerHTML = Array.from({ length: PV_MAX }, (_, i) => `<i class="${i < m.pv ? "" : "off"}"></i>`).join("");
  const recharge = m.t < m.rechargeFin;
  $("ammoLbl").textContent = recharge ? tr().recharge : tr().munitions;
  $("bullets").innerHTML = Array.from({ length: MUNITIONS }, (_, i) => `<i class="${!recharge && i < m.mun ? "" : "off"}"></i>`).join("");
  if (!partie.mode.startsWith("jev")) return;
  $("seuil").textContent = partie.seuil.toFixed(2);
  const l = jev.lat; $("lat").textContent = l.length ? Math.round(l.slice(-10).reduce((a, b) => a + b, 0) / Math.min(10, l.length)) + " ms" : "—";
  $("calls").textContent = `${jev.appels} / ${jev.tokens}`;
  $("errRow").textContent = jev.err;
  if (partie.mode === "jev") {
    $("dec").textContent = partie.cibleId ? tr().tirerSur + partie.cibleId : tr().attendre;
    $("bars").innerHTML = vis.map(c => {
      const p = partie.pistes.get(c.id), pz = p.pZ ?? 0, cls = p.statut === "zombie" ? "fire" : "";
      const col = p.statut === "humain" ? "background:var(--green)" : "";
      return `<div class="bar"><i class="fill ${cls}" style="width:${pz * 100}%;${col}"></i><em><span>${ICONES[p.statut]} ${c.id} ${p.lueAvecReaction ? "📢✓" : c.sommeAt !== null ? "📢…" : ""}</span><span>${p.pZ == null ? "—" : "p(z)=" + pz.toFixed(2)}${p.incoh > INCOH_MAX ? " ⚠" : ""}</span></em></div>`;
    }).join("");
    return;
  }
  $("dec").textContent = jev.choix;
  $("bars").innerHTML = Object.entries(jev.probas).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, p]) =>
    `<div class="bar"><i class="fill ${k !== "attendre" && p >= partie.seuil ? "fire" : ""}" style="width:${p * 100}%"></i><em><span>${k}</span><span>${p.toFixed(2)}</span></em></div>`).join("");
}

export function ecranFin(partie, jev) {
  const m = partie.monde, s = m.stats;
  $("endSub").textContent = (m.pv <= 0 ? tr().tombe : tr().tenu) + ` · mode ${$("mode").textContent}`;
  const vals = [score(s), s.zombies_tues, s.humains_sauves, s.humains_tues, s.morsures, s.tirs ? Math.round((1 - s.rates / s.tirs) * 100) + " %" : "—",
    partie.mode.startsWith("jev") ? jev.appels : "—", partie.mode === "jev" ? s.sommations : "—"];
  $("endStats").innerHTML = tr().stats.map((k, i) => `<div><span class="label">${k}</span><b>${vals[i]}</b></div>`).join("");
  $("end").classList.remove("hidden");
}
