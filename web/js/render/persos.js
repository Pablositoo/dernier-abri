// Personnages 3D (géométries/matériaux partagés). La vue lit l'état de l'entité simulée, elle ne la modifie jamais.
import * as THREE from "three";
import { estZombie } from "../sim/monde.js";

const G = {
  jambe: new THREE.BoxGeometry(.19, .88, .21).translate(0, -.44, 0),
  bras: new THREE.BoxGeometry(.13, .62, .14).translate(0, -.31, 0),
  torse: new THREE.BoxGeometry(.52, .66, .28),
  tete: new THREE.BoxGeometry(.3, .32, .3),
  oeil: new THREE.BoxGeometry(.06, .035, .02),
  sac: new THREE.BoxGeometry(.38, .44, .18),
  sang: new THREE.BoxGeometry(.2, .16, .02),
};
const M = c => new THREE.MeshStandardMaterial({ color: c, roughness: .85 });
const MAT = {
  peauZ: M(0x6f855c), habitZ: M(0x34322c), pantZ: M(0x23242a), oeilZ: new THREE.MeshBasicMaterial({ color: 0xd8ff6a }),
  oeilBZ: new THREE.MeshBasicMaterial({ color: 0x9fd14a, transparent: true, opacity: .55 }), mainBZ: M(0x8a9a78),
  peaux: [0xe3b48f, 0xc68642, 0x8d5524, 0xf1c9a5].map(M), chemises: [0x2f7de1, 0xe1a12f, 0xd94a4a, 0x2fbf8f, 0xf2f2f2].map(M),
  jean: M(0x2f3f58), sac: M(0x7a4a22), peauB: M(0xc9a58b), habitB: M(0x6a5a50), sang: M(0x5e0d0d),
};

export class VuePerso {
  constructor(e, rng, scene, conteneurTags) {
    this.e = e; this.scene = scene;
    const nature = e.nature, z = estZombie(nature), blesse = nature.startsWith("blesse");
    const peau = z && !blesse ? MAT.peauZ : blesse ? MAT.peauB : rng.choisir(MAT.peaux);
    const habit = z && !blesse ? MAT.habitZ : blesse ? MAT.habitB : rng.choisir(MAT.chemises);
    const pant = z && !blesse ? MAT.pantZ : MAT.jean;
    this.root = new THREE.Group(); this.corps = new THREE.Group(); this.root.add(this.corps);
    const mesh = (geo, mat, x, y, zz, parent = this.corps) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, zz); m.castShadow = true; m.userData.id = e.id; parent.add(m); return m; };
    const pivot = (x, y) => { const p = new THREE.Group(); p.position.set(x, y, 0); this.corps.add(p); return p; };
    this.jg = pivot(-.12, .9); this.jd = pivot(.12, .9); mesh(G.jambe, pant, 0, 0, 0, this.jg); mesh(G.jambe, pant, 0, 0, 0, this.jd);
    mesh(G.torse, habit, 0, 1.23, 0);
    this.cou = pivot(0, 1.56); mesh(G.tete, peau, 0, .17, 0, this.cou);
    this.bg = pivot(-.33, 1.52); this.bd = pivot(.33, 1.52); mesh(G.bras, peau, 0, 0, 0, this.bg); mesh(G.bras, peau, 0, 0, 0, this.bd);
    if (z && !blesse) { mesh(G.oeil, MAT.oeilZ, -.07, .2, .151, this.cou); mesh(G.oeil, MAT.oeilZ, .07, .2, .151, this.cou); }
    if (blesse) { mesh(G.sang, MAT.sang, -.1, 1.3, .145); mesh(G.sang, MAT.sang, .12, 1.08, .145); }
    if (nature === "blesse_zombie") {            // indice visuel discret, invisible pour JEV (il ne lit que la description)
      this.yeux = [mesh(G.oeil, MAT.oeilBZ, -.07, .2, .151, this.cou), mesh(G.oeil, MAT.oeilBZ, .07, .2, .151, this.cou)];
      this.bg.children[0].material = this.bd.children[0].material = MAT.mainBZ;
    }
    if (!z && !blesse && rng.suivant() < .5) mesh(G.sac, MAT.sac, 0, 1.25, -.23);
    this.root.position.set(e.x, 0, e.z);
    scene.add(this.root);
    this.tag = document.createElement("div"); this.tag.className = "tag"; this.tag.textContent = e.id;
    conteneurTags.append(this.tag);
  }

  maj() {
    const e = this.e, n = e.nature;
    if (!e.vivant) {                           // chute puis enfoncement dans le sol
      this.corps.rotation.x = -Math.min(Math.PI / 2, e.mort * 4);
      this.root.position.y = -Math.max(0, e.mort - 3) * .3;
      return;
    }
    this.root.position.set(e.x, 0, e.z); this.root.rotation.y = e.rotY;
    if (e.arrete) {                            // humain qui obéit : s'arrête, mains en l'air
      this.jg.rotation.x = this.jd.rotation.x = 0; this.corps.position.y = 0; this.corps.rotation.set(0, 0, 0);
      this.bd.rotation.x = -2.9; this.bg.rotation.x = n === "humain" ? -2.9 : -.5; this.cou.rotation.x = 0;
      return;
    }
    const s = Math.sin(e.phase);
    if (n === "zombie") {
      this.jg.rotation.x = s * .45; this.jd.rotation.x = -s * .45;
      this.bg.rotation.x = -1.45 + s * .1; this.bd.rotation.x = -1.35 - s * .1;
      this.cou.rotation.z = Math.sin(e.phase * .5) * .25; this.corps.rotation.z = s * .06;
    } else if (n === "humain") {
      this.jg.rotation.x = s * .9; this.jd.rotation.x = -s * .9;
      this.bg.rotation.x = -s * .9; this.bd.rotation.x = s * .9;
      if (e.descIdx === 1) this.bd.rotation.x = -2.6 + s * .4;
      this.corps.position.y = Math.abs(s) * .08; this.corps.rotation.x = .15;
    } else {                                   // blessés : même apparence, seule la description diffère
      this.jg.rotation.x = s * .35; this.jd.rotation.x = -s * .2;
      this.bg.rotation.x = -.5; this.bd.rotation.x = n === "blesse_humain" && e.descIdx === 1 ? -2.5 : s * .2;
      this.corps.rotation.z = Math.max(0, s) * .12; this.cou.rotation.x = .35;
    }
  }

  revelerYeux() {                              // l'infecté se trahit une fois classé avec sa réaction
    if (this.yeux) { this.yeux.forEach(m => m.material = MAT.oeilZ); this.yeux = null; }
  }

  tuer(nom, zombie) {
    this.tag.className = "tag reveal"; this.tag.textContent = nom + (zombie ? " ✓" : " ✗");
    this.tag.style.color = zombie ? "var(--green)" : "var(--red)";
  }

  detruire() { this.scene.remove(this.root); this.tag.remove(); }
}
