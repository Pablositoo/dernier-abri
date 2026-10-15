// Effets éphémères : traçantes des balles et onde de la sommation
import * as THREE from "three";

export function creerEffets(scene) {
  const tracers = [], ondes = [];
  const tracerMat = new THREE.LineBasicMaterial({ color: 0xffe2a0, transparent: true });
  const ondeMat = new THREE.MeshBasicMaterial({ color: 0xffcf6b, transparent: true, side: THREE.DoubleSide, depthWrite: false });
  return {
    tracer(from, to) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([from, to]), tracerMat.clone());
      scene.add(line); tracers.push({ line, t: 0.09 });
    },
    onde() {
      const m = new THREE.Mesh(new THREE.RingGeometry(.9, 1, 64), ondeMat.clone());
      m.rotation.x = -Math.PI / 2; m.position.y = .05; scene.add(m); ondes.push({ m, t: 0 });
    },
    maj(dt) {
      for (let i = ondes.length - 1; i >= 0; i--) { const o = ondes[i]; o.t += dt; o.m.scale.setScalar(1 + o.t * 30); o.m.material.opacity = Math.max(0, 1 - o.t / 1.4); if (o.t > 1.4) { scene.remove(o.m); ondes.splice(i, 1); } }
      for (let i = tracers.length - 1; i >= 0; i--) { const tr = tracers[i]; tr.t -= dt; tr.line.material.opacity = tr.t / .09; if (tr.t <= 0) { scene.remove(tr.line); tr.line.geometry.dispose(); tracers.splice(i, 1); } }
    },
  };
}
