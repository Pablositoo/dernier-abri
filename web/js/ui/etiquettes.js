// Étiquettes au-dessus des silhouettes (id, p(zombie), statut, cible en cours)
import * as THREE from "three";

const v = new THREE.Vector3();

export function majEtiquettes(partie, vues, camera, vis) {
  const vus = new Set(vis.map(o => o.id));
  for (const vue of vues.values()) {
    const e = vue.e, tag = vue.tag;
    v.set(e.x, 2.05, e.z).project(camera);
    const ok = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1 && (e.vivant ? vus.has(e.id) : e.mort < 2.5);
    tag.style.display = ok ? "" : "none";
    if (!ok) continue;
    tag.style.left = (v.x * .5 + .5) * innerWidth + "px"; tag.style.top = (-v.y * .5 + .5) * innerHeight + "px";
    if (!e.vivant) continue;
    tag.classList.toggle("target", e.id === partie.cibleId);
    if (partie.mode === "jev") {
      const p = partie.pistes.get(e.id);
      tag.classList.toggle("z", p.statut === "zombie"); tag.classList.toggle("h", p.statut === "humain");
      tag.classList.toggle("u", p.statut === "incertain" || p.statut === "analyse");
      const pz = partie.politique !== "v2" ? (p.statut === "analyse" ? null : p.pPost) : p.pZ;
      tag.textContent = e.id + (pz == null ? " …" : ` ${Math.round(pz * 100)}%`);
    }
  }
}
