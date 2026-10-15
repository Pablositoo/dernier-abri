// Son synthétisé (aucun fichier externe)
let actx;

export function audio() { actx ??= new (window.AudioContext || window.webkitAudioContext)(); actx.resume?.(); }

// rng : hasard visuel/sonore (n'influence pas la partie)
export function bang(rng) {
  if (!actx) return;
  const len = actx.sampleRate * .25, buf = actx.createBuffer(1, len, actx.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (rng.suivant() * 2 - 1) * Math.pow(1 - i / len, 3);
  const src = actx.createBufferSource(), f = actx.createBiquadFilter(), g = actx.createGain();
  src.buffer = buf; f.type = "lowpass"; f.frequency.value = 1400; g.gain.value = .5;
  src.connect(f).connect(g).connect(actx.destination); src.start();
}

export function bip() {
  if (!actx) return;
  [0, .18].forEach((d, i) => { const o = actx.createOscillator(), g = actx.createGain();
    o.type = "square"; o.frequency.value = i ? 660 : 880; g.gain.setValueAtTime(.08, actx.currentTime + d); g.gain.exponentialRampToValueAtTime(.001, actx.currentTime + d + .16);
    o.connect(g).connect(actx.destination); o.start(actx.currentTime + d); o.stop(actx.currentTime + d + .17); });
}
