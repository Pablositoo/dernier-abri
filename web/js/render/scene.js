// Décor Three.js : rendu, caméra, lumières, rue, immeubles, voitures, barricade, poussière.
// rng = hasard purement visuel (n'influence jamais la partie).
import * as THREE from "three";
import { BARRICADE_Z, HAUTEUR_OEIL } from "../config.js";

export function creerScene(rng, lite) {
  const R = () => rng.suivant();
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(lite ? 0.75 : Math.min(devicePixelRatio, 1.5));   // M1 / GTX 1060 : on plafonne
  renderer.setSize(innerWidth, innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.shadowMap.enabled = !lite;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  document.body.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0e18);
  scene.fog = new THREE.FogExp2(0x0a0e18, 0.024);
  const camera = new THREE.PerspectiveCamera(72, innerWidth / innerHeight, 0.05, 200);
  camera.rotation.order = "YXZ";
  camera.position.set(0, HAUTEUR_OEIL, 0);
  scene.add(camera);

  scene.add(new THREE.HemisphereLight(0x51618a, 0x120c08, 0.55));
  const lune = new THREE.DirectionalLight(0xa9bcff, 0.9);
  lune.position.set(-18, 32, -30);
  lune.target.position.set(0, 0, -30);
  lune.castShadow = true;
  lune.shadow.mapSize.set(1024, 1024);
  Object.assign(lune.shadow.camera, { left: -16, right: 16, top: 45, bottom: -45, near: 1, far: 90 });
  scene.add(lune, lune.target);

  const lampe = new THREE.SpotLight(0xfff0d0, 38, 70, 0.32, 0.5, 1.4);   // lampe torche fixée à l'arme
  lampe.position.set(0.2, -0.1, -0.9);
  camera.add(lampe, lampe.target);
  lampe.target.position.set(0, 0, -10);

  // ---------- Textures procédurales (aucun fichier externe) ----------
  function canvasTex(w, h, draw, rx = 1, ry = 1) {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    draw(c.getContext("2d"), w, h);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rx, ry);
    t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return t;
  }
  const asphalte = canvasTex(512, 512, (g, w, h) => {
    g.fillStyle = "#1b1c20"; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 9000; i++) { const v = 20 + R() * 30; g.fillStyle = `rgb(${v},${v},${v + 3})`; g.fillRect(R() * w, R() * h, 2, 2); }
    g.strokeStyle = "rgba(0,0,0,.6)"; g.lineWidth = 2;
    for (let i = 0; i < 6; i++) { g.beginPath(); let x = R() * w, y = R() * h; g.moveTo(x, y); for (let k = 0; k < 6; k++) { x += (R() - .5) * 80; y += (R() - .5) * 80; g.lineTo(x, y); } g.stroke(); }
    g.fillStyle = "rgba(220,200,120,.55)"; g.fillRect(w / 2 - 5, 0, 10, h * 0.55);
  }, 1, 10);
  const fenetres = canvasTex(256, 512, (g, w, h) => {
    g.fillStyle = "#15161b"; g.fillRect(0, 0, w, h);
    for (let y = 16; y < h - 16; y += 40) for (let x = 14; x < w - 14; x += 38) {
      const on = R() < 0.12;
      g.fillStyle = on ? (R() < .7 ? "#ffcf7a" : "#9fc3ff") : "#0b0c10";
      g.fillRect(x, y, 22, 26);
    }
  });

  // ---------- Décor ----------
  const sol = new THREE.Mesh(new THREE.PlaneGeometry(18, 160), new THREE.MeshStandardMaterial({ map: asphalte, roughness: 0.92 }));
  sol.rotation.x = -Math.PI / 2; sol.position.z = -60; sol.receiveShadow = true; scene.add(sol);
  const trottoirMat = new THREE.MeshStandardMaterial({ color: 0x2a2b31, roughness: 1 });
  for (const s of [-1, 1]) {
    const t = new THREE.Mesh(new THREE.BoxGeometry(4, 0.2, 160), trottoirMat);
    t.position.set(s * 11, 0.1, -60); t.receiveShadow = true; scene.add(t);
  }
  const immeubleGeo = new THREE.BoxGeometry(1, 1, 1);
  for (const s of [-1, 1]) for (let z = 4; z > -150; z -= 9 + R() * 5) {
    const h = 8 + R() * 22, w = 6 + R() * 3, d = 7 + R() * 3;
    const tex = fenetres.clone(); tex.needsUpdate = true; tex.repeat.set(Math.max(1, Math.round(d / 4)), Math.max(1, Math.round(h / 8)));
    const m = new THREE.Mesh(immeubleGeo, new THREE.MeshStandardMaterial({ map: tex, emissive: 0xffffff, emissiveMap: tex, emissiveIntensity: 0.4, roughness: 0.9 }));
    m.scale.set(w, h, d); m.position.set(s * (13 + w / 2), h / 2, z - d / 2); scene.add(m);
  }
  // lampadaires (3 vraies lumières max pour la perf)
  const poteauMat = new THREE.MeshStandardMaterial({ color: 0x24262c, metalness: .6, roughness: .5 });
  const ampouleMat = new THREE.MeshBasicMaterial({ color: 0xffd28a });
  const lampadaires = [];
  for (const [x, z] of [[-8.5, -12], [8.5, -30], [-8.5, -48]]) {
    const p = new THREE.Mesh(new THREE.CylinderGeometry(.08, .1, 6.5, 8), poteauMat); p.position.set(x, 3.25, z); scene.add(p);
    const a = new THREE.Mesh(new THREE.BoxGeometry(.9, .12, .3), ampouleMat); a.position.set(x - Math.sign(x) * .4, 6.4, z); scene.add(a);
    const l = new THREE.PointLight(0xffb866, 22, 20, 1.6); l.position.set(x - Math.sign(x) * .4, 6.1, z); scene.add(l);
    lampadaires.push(l);
  }
  // voitures abandonnées
  const carMats = [0x5a1f1f, 0x1f2f4a, 0x2e3a2a].map(c => new THREE.MeshStandardMaterial({ color: c, roughness: .55, metalness: .4 }));
  const vitreMat = new THREE.MeshStandardMaterial({ color: 0x0c1118, roughness: .1, metalness: .9 });
  for (const [x, z, r] of [[-6.2, -20, .3], [5.8, -38, -.5], [-5.5, -58, .1], [6.5, -8, .9]]) {
    const c = new THREE.Group();
    const b = new THREE.Mesh(new THREE.BoxGeometry(1.9, .75, 4.2), rng.choisir(carMats)); b.position.y = .6;
    const h = new THREE.Mesh(new THREE.BoxGeometry(1.7, .6, 2.2), vitreMat); h.position.set(0, 1.25, -.2);
    b.castShadow = h.castShadow = true; c.add(b, h); c.position.set(x, 0, z); c.rotation.y = r; scene.add(c);
  }
  // barricade de sacs de sable
  const sacMat = new THREE.MeshStandardMaterial({ color: 0x6b5c3e, roughness: 1 });
  const sacGeo = new THREE.CapsuleGeometry(.22, .55, 4, 8); sacGeo.rotateZ(Math.PI / 2);
  for (let row = 0; row < 2; row++) for (let i = -9; i <= 9; i++) {
    const s = new THREE.Mesh(sacGeo, sacMat);
    s.position.set(i * .9 + (row % 2) * .45, .22 + row * .36, BARRICADE_Z + .25); s.rotation.y = (R() - .5) * .2; s.castShadow = true; scene.add(s);
  }
  // poussière en suspension
  const dustGeo = new THREE.BufferGeometry(), N = 700, dp = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) { dp[i * 3] = (R() - .5) * 26; dp[i * 3 + 1] = R() * 10; dp[i * 3 + 2] = -R() * 90; }
  dustGeo.setAttribute("position", new THREE.BufferAttribute(dp, 3));
  const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ color: 0x9aa3b5, size: .05, transparent: true, opacity: .5, depthWrite: false }));
  scene.add(dust);

  addEventListener("resize", () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
  return { renderer, scene, camera, lampadaires, dust };
}
