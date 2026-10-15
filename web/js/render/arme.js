// Arme en vue à la première personne + flash du tir
import * as THREE from "three";

export function creerArme(camera) {
  const arme = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0x3a3e46, metalness: .35, roughness: .45, emissive: 0x0c0d10 });
  const bois = new THREE.MeshStandardMaterial({ color: 0x4a3322, roughness: .8 });
  const corps = new THREE.Mesh(new THREE.BoxGeometry(.09, .12, .36), metal);
  const canon = new THREE.Mesh(new THREE.CylinderGeometry(.022, .022, .42, 10), metal); canon.rotation.x = Math.PI / 2; canon.position.set(0, .02, -.36);
  const crosse = new THREE.Mesh(new THREE.BoxGeometry(.08, .13, .12), bois); crosse.position.set(0, -.03, .22);
  const poignee = new THREE.Mesh(new THREE.BoxGeometry(.07, .16, .08), bois); poignee.position.set(0, -.12, .08); poignee.rotation.x = .3;
  arme.add(corps, canon, crosse, poignee);
  const BASE = new THREE.Vector3(.26, -.25, -.7);
  arme.scale.setScalar(.85);
  arme.position.copy(BASE); camera.add(arme);
  const flashMat = new THREE.SpriteMaterial({ color: 0xffd27a, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  const flash = new THREE.Sprite(flashMat); flash.scale.set(.35, .35, 1); flash.position.set(0, .02, -.7); arme.add(flash);
  const flashLight = new THREE.PointLight(0xffb45a, 0, 9); flashLight.position.set(0, 0, -.8); arme.add(flashLight);
  return { arme, canon, flashMat, flashLight, BASE };
}

export function tirArme(A) { A.flashMat.opacity = 1; A.flashLight.intensity = 30; }

export function animerArme(A, t, dt, recharge, recul) {
  A.arme.position.set(A.BASE.x, A.BASE.y - (recharge ? .18 : 0) + Math.sin(t * 1.6) * .004, A.BASE.z + recul * .08);
  A.arme.rotation.x = recharge ? -.6 : recul * .15;
  A.flashMat.opacity = Math.max(0, A.flashMat.opacity - dt * 18); A.flashLight.intensity = Math.max(0, A.flashLight.intensity - dt * 400);
}
