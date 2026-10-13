/* shared constants for the showreel: size, palette, music grid, small helpers */
const Q = new URLSearchParams(location.search);
const W = +(Q.get('w') || 1920), H = +(Q.get('h') || 1080), FPS = +(Q.get('fps') || 60);
const S = Math.sqrt(W * H / (1920 * 1080));
const E = MG.ease;
const C = { ink: '#0D0D0E', paper: '#F2EFE8', blue: '#2340FF', lime: '#D4FF3A' };

/* music_grid.py fit upbeat-energetic.m4a --dur 56 → bars of the real song */
const MUSIC = {"dur": 55.0084, "bpm": 95.753, "beat": 0.62661, "bar": 2.50645, "bars": [0.0, 2.4962, 5.0039, 7.5001, 9.9962, 12.4924, 15.0001, 17.4963, 20.004, 22.5002, 24.9963, 27.5041, 30.0002, 32.4963, 35.0041, 37.5002, 39.9964, 42.4925, 45.0003, 47.4964, 50.0042, 52.5003, 55.0081], "drops": [], "sections": [50.0042]};
const B = i => MUSIC.bars[i];                      // bar line i (seconds)
const beat = (bar, n) => B(bar) + n * MUSIC.beat;  // n-th beat after bar line

const stage = document.getElementById('stage');
stage.style.width = W + 'px'; stage.style.height = H + 'px';
stage.style.setProperty('--u', S);
FILM.config({ W, H, fps: FPS, dur: MUSIC.dur, root: stage });
const G = MG.grid({ W, H, cols: 12, rows: 8 });

/* helpers */
function el(tag, cls, parent, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  (parent || stage).appendChild(e);
  return e;
}
function label(parent, text, x, y, color) {          // tiny technical label (decorative texture)
  const e = el('div', 'sw-label abs', parent, text);
  e.dataset.deco = '';
  e.style.left = x + 'px'; e.style.top = y + 'px';
  if (color) e.style.color = color;
  return e;
}
function canvasIn(layer) { const c = el('canvas', '', layer); return c; }
const pad = (n, k) => String(Math.max(0, Math.floor(n))).padStart(k, '0');
const tc = t => `${pad(t / 60, 2)}:${pad(t % 60, 2)}:${pad((t % 1) * FPS, 2)}`;
