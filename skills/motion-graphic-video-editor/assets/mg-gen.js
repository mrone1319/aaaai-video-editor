/* mg-gen.js — generative design studies on <canvas>, all seekable and deterministic.
 * Load after mg-kit.js.  Each study: const s = GEN.xxx(canvas, opt); then s.render(t) per frame.
 *
 *   GEN.particles   thousands of points in a curl-noise field with attractors/repulsors;
 *                   can organise into a target shape (text, circle, grid) and dissolve again
 *   GEN.typeGrid    one glyph repeated over a strict grid, each cell driven by MG.wave
 *   GEN.wire        wireframe studies: cube, grid plane, axes with ticks, point cloud,
 *                   construction circles — projected in 3D, drawn on progressively
 *   GEN.figure      hand-drawn line character (boiling line, draw-on, walk / jump / wave)
 *   GEN.motion      motion-analysis skeleton: joints, bones, trails, angle readouts
 *   GEN.textPoints / GEN.shapePoints   target point sets for particles
 *
 * Determinism: particles integrate with a fixed step (1/120 s) from cached checkpoints,
 * so seeking to any t (forwards, backwards, fractional) gives the same picture.
 */
(function (root) {
  'use strict';
  const GEN = {};
  const MG = root.MG;
  const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
  const lerp = (a, b, k) => a + (b - a) * k;

  /* ---------------------------------------------------------------- 3-D value noise + curl */
  function h3(x, y, z, s) {
    let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(z | 0, 2147483647) ^ Math.imul(s | 0, 1274126177);
    h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  }
  const sm = f => f * f * (3 - 2 * f);
  function noise3(x, y, z, s = 0) {
    const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
    const u = sm(x - xi), v = sm(y - yi), w = sm(z - zi);
    const c = (a, b, d) => h3(xi + a, yi + b, zi + d, s);
    const x00 = lerp(c(0, 0, 0), c(1, 0, 0), u), x10 = lerp(c(0, 1, 0), c(1, 1, 0), u);
    const x01 = lerp(c(0, 0, 1), c(1, 0, 1), u), x11 = lerp(c(0, 1, 1), c(1, 1, 1), u);
    return lerp(lerp(x00, x10, v), lerp(x01, x11, v), w) * 2 - 1;
  }
  GEN.noise3 = noise3;
  /* divergence-free 2-D flow from a scalar potential: swirls, never sinks */
  function curl(x, y, z, s) {
    const e = 0.01;
    const dx = (noise3(x + e, y, z, s) - noise3(x - e, y, z, s)) / (2 * e);
    const dy = (noise3(x, y + e, z, s) - noise3(x, y - e, z, s)) / (2 * e);
    return [dy, -dx];
  }

  function rand(seed) { return MG ? MG.rand(seed) : (() => { let s = seed; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })(); }
  function sizeCanvas(cv, W, H) { cv.width = W; cv.height = H; cv.style.width = W + 'px'; cv.style.height = H + 'px'; return cv.getContext('2d'); }

  /* ---------------------------------------------------------------- target point sets */
  GEN.textPoints = function (text, n, W, H, o = {}) {
    const c = document.createElement('canvas'), k = 0.5, w = Math.round(W * k), h = Math.round(H * k);
    c.width = w; c.height = h;
    const x = c.getContext('2d');
    x.fillStyle = '#000'; x.textAlign = 'center'; x.textBaseline = 'middle';
    x.font = `${o.weight || 800} ${(o.size || H * 0.42) * k}px ${o.font || '"Helvetica Neue", Arial, sans-serif'}`;
    x.fillText(text, w * (o.cx == null ? 0.5 : o.cx), h * (o.cy == null ? 0.5 : o.cy));
    const d = x.getImageData(0, 0, w, h).data, on = [];
    for (let j = 0; j < h; j += 2) for (let i = 0; i < w; i += 2) if (d[(j * w + i) * 4 + 3] > 128) on.push([i / k, j / k]);
    const r = rand(o.seed || 9), out = new Float32Array(n * 2);
    for (let p = 0; p < n; p++) {
      const q = on.length ? on[Math.floor(r() * on.length)] : [W / 2, H / 2];
      out[p * 2] = q[0] + (r() - 0.5) * 2; out[p * 2 + 1] = q[1] + (r() - 0.5) * 2;
    }
    return out;
  };
  GEN.shapePoints = function (kind, n, W, H, o = {}) {
    const out = new Float32Array(n * 2), r = rand(o.seed || 5), cx = W * (o.cx || 0.5), cy = H * (o.cy || 0.5), R = Math.min(W, H) * (o.r || 0.32);
    for (let p = 0; p < n; p++) {
      let x, y;
      if (kind === 'circle') { const a = (p / n) * Math.PI * 2, rr = R * (1 + (r() - 0.5) * 0.02); x = cx + Math.cos(a) * rr; y = cy + Math.sin(a) * rr; }
      else if (kind === 'disc') { const a = r() * Math.PI * 2, rr = R * Math.sqrt(r()); x = cx + Math.cos(a) * rr; y = cy + Math.sin(a) * rr; }
      else if (kind === 'grid') { const c = Math.ceil(Math.sqrt(n * W / H)), rows = Math.ceil(n / c); x = W * 0.1 + (p % c) / (c - 1) * W * 0.8; y = H * 0.12 + Math.floor(p / c) / Math.max(1, rows - 1) * H * 0.76; }
      else if (kind === 'line') { x = W * 0.08 + (p / n) * W * 0.84; y = cy + (r() - 0.5) * 2; }
      else { const a = r() * Math.PI * 2, b = Math.acos(2 * r() - 1), z = Math.cos(b); x = cx + R * Math.sin(b) * Math.cos(a) * (1 + 0.15 * z); y = cy + R * Math.sin(b) * Math.sin(a) * (1 + 0.15 * z); }
      out[p * 2] = x; out[p * 2 + 1] = y;
    }
    return out;
  };

  /* ---------------------------------------------------------------- particles
     opt: { W, H, count: 6000, seed, scale (field size px), speed (px/s), drift (field evolution),
            attractors: [{x, y, strength, radius, t0, t1}] (strength < 0 = repulsor),
            target: Float32Array of n*2 points, form: t => 0..1 (how organised),
            size: px, ink: '#F2EFE8', accent: '#D4FF3A', accentShare: 0.06, accentOn: t => 0..1,
            background: '#0D0D0E' | null (transparent) }  */
  GEN.particles = function (cv, o = {}) {
    const W = o.W, H = o.H, n = o.count || 6000, ctx = sizeCanvas(cv, W, H), S = Math.sqrt(W * H / (1920 * 1080));
    const DT = 1 / 120, CK = 120, seed = o.seed || 3;
    const r = rand(seed), init = new Float32Array(n * 2), vel = new Float32Array(n);
    for (let p = 0; p < n; p++) { init[p * 2] = r() * W; init[p * 2 + 1] = r() * H; vel[p] = 0.6 + 0.8 * r(); }
    const scale = (o.scale || 420) * S, speed = (o.speed || 90) * S, drift = o.drift == null ? 0.12 : o.drift;
    const atts = o.attractors || [];
    const cache = new Map([[0, init.slice()]]);
    function step(pos, k) {                                   // advance one fixed step from step k
      const t = k * DT;
      for (let p = 0; p < n; p++) {
        let x = pos[p * 2], y = pos[p * 2 + 1];
        const [vx, vy] = curl(x / scale, y / scale, t * drift, seed);
        let ax = vx * speed * vel[p], ay = vy * speed * vel[p];
        for (const a of atts) {
          if (a.t0 != null && (t < a.t0 || t > a.t1)) continue;
          const dx = a.x * W - x, dy = a.y * H - y, d2 = dx * dx + dy * dy + 1, R = (a.radius || 0.3) * Math.min(W, H);
          const f = a.strength * speed * Math.exp(-d2 / (R * R)) / Math.sqrt(d2);
          ax += dx * f; ay += dy * f;
        }
        x += ax * DT; y += ay * DT;
        if (x < -20) x += W + 40; else if (x > W + 20) x -= W + 40;      // wrap: density never drains
        if (y < -20) y += H + 40; else if (y > H + 20) y -= H + 40;
        pos[p * 2] = x; pos[p * 2 + 1] = y;
      }
    }
    function at(k) {                                          // positions at step k (cached checkpoints)
      const c0 = Math.floor(k / CK) * CK;
      let base = -1;
      for (let c = c0; c >= 0; c -= CK) if (cache.has(c)) { base = c; break; }
      const pos = cache.get(base).slice();
      for (let s = base; s < k; s++) { step(pos, s); if ((s + 1) % CK === 0 && !cache.has(s + 1)) cache.set(s + 1, pos.slice()); }
      return pos;
    }
    let lastK = -1, lastPos = null;
    function positions(t) {
      const kf = t / DT, k = Math.floor(kf), f = kf - k;
      const a = k === lastK ? lastPos : at(k);
      lastK = k; lastPos = a;
      if (f < 1e-6) return a;
      const b = a.slice(); step(b, k);
      const out = new Float32Array(n * 2);
      for (let i = 0; i < n * 2; i++) out[i] = lerp(a[i], b[i], f);
      return out;
    }
    const sz = (o.size || 2) * S, ink = o.ink || '#F2EFE8', acc = o.accent || '#D4FF3A', share = o.accentShare || 0.06;
    return {
      render(t) {
        const pos = positions(Math.max(0, t));
        const form = o.form ? clamp(o.form(t)) : 0, tg = o.target, accOn = o.accentOn ? clamp(o.accentOn(t)) : 0;
        if (o.background) { ctx.fillStyle = o.background; ctx.fillRect(0, 0, W, H); } else ctx.clearRect(0, 0, W, H);
        const draw = (sel, color) => {
          ctx.fillStyle = color;
          for (let p = 0; p < n; p++) {
            if (!sel(p)) continue;
            let x = pos[p * 2], y = pos[p * 2 + 1];
            if (tg && form > 0) {
              const e = MG ? MG.ease.inOut(clamp(form * (1.25 - 0.25 * vel[p] / 1.4))) : form;   // stagger by particle
              x = lerp(x, tg[p * 2], e); y = lerp(y, tg[p * 2 + 1], e);
            }
            ctx.fillRect(x - sz / 2, y - sz / 2, sz, sz);
          }
        };
        const isAcc = p => (p * 2654435761 >>> 0) % 1000 < share * 1000;
        draw(p => !(accOn > 0 && isAcc(p)), ink);
        if (accOn > 0) { ctx.globalAlpha = accOn; draw(isAcc, acc); ctx.globalAlpha = 1; }
      }
    };
  };

  /* ---------------------------------------------------------------- typography grid
     opt: { W, H, cols, rows, glyphs: 'A' | 'TYPE' | ['0','1'] | (i,j,t)=>string, font, weight,
            ink, paper, mode: 'scale' | 'invert' | 'weight' | 'cycle' | 'mixed', wave: {kind, freq, speed, seed},
            margin, appear: t => 0..1 (cells switch on in a diagonal sweep) } */
  GEN.typeGrid = function (cv, o = {}) {
    const W = o.W, H = o.H, ctx = sizeCanvas(cv, W, H);
    const cols = o.cols || 16, rows = o.rows || 9, m = o.margin == null ? Math.min(W, H) * 0.05 : o.margin;
    const cw = (W - 2 * m) / cols, ch = (H - 2 * m) / rows, ink = o.ink || '#0D0D0E', paper = o.paper || '#F2EFE8';
    const font = o.font || '"Helvetica Neue", Arial, sans-serif', mode = o.mode || 'mixed';
    const glyph = (i, j, t) => typeof o.glyphs === 'function' ? o.glyphs(i, j, t)
      : Array.isArray(o.glyphs) ? o.glyphs[(i + j * cols) % o.glyphs.length]
      : (o.glyphs || 'A')[(i + j * cols) % (o.glyphs || 'A').length];
    return {
      render(t) {
        ctx.fillStyle = paper; ctx.fillRect(0, 0, W, H);
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const ap = o.appear ? clamp(o.appear(t)) : 1;
        for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
          if ((i + j) / (cols + rows - 2) > ap * 1.0001) continue;
          const v = MG.wave(i, j, t, o.wave || { kind: 'diag' });
          const x = m + i * cw, y = m + j * ch;
          let inv = false, s = 1, wgt = o.weight || 700, g = glyph(i, j, t);
          if (mode === 'scale' || mode === 'mixed') s = 0.25 + 0.95 * v;
          if (mode === 'invert' || mode === 'mixed') inv = v > 0.82;
          if (mode === 'weight') wgt = 100 + Math.round(v * 8) * 100;
          if (mode === 'cycle') g = String.fromCharCode(65 + Math.floor(v * 25.99));
          if (inv) { ctx.fillStyle = ink; ctx.fillRect(x, y, cw + 0.5, ch + 0.5); }
          ctx.fillStyle = inv ? paper : ink;
          ctx.font = `${wgt} ${ch * 0.86 * s}px ${font}`;
          ctx.fillText(g, x + cw / 2, y + ch / 2 + ch * 0.04);
        }
      }
    };
  };

  /* ---------------------------------------------------------------- wireframe studies
     opt: { W, H, items: [{type:'cube'|'grid'|'axes'|'cloud'|'circle', size, pos:[x,y,z], n, seed, ticks}],
            ink, accent, line: px, labels: true }
     render(t, {rx, ry, rz, dist, draw (0..1 progressive draw-on), cx, cy, fov}) */
  GEN.wire = function (cv, o = {}) {
    const W = o.W, H = o.H, ctx = sizeCanvas(cv, W, H), S = Math.sqrt(W * H / (1920 * 1080));
    const segs = [], pts = [], labs = [];
    const add = (a, b, c) => segs.push([a, b, c || null]);
    (o.items || []).forEach(it => {
      const s = it.size || 1, [px, py, pz] = it.pos || [0, 0, 0], col = it.accent ? 'accent' : null;
      if (it.type === 'cube') {
        const v = [];
        for (let i = 0; i < 8; i++) v.push([px + (i & 1 ? s : -s) / 2, py + (i & 2 ? s : -s) / 2, pz + (i & 4 ? s : -s) / 2]);
        [[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]].forEach(([a, b]) => add(v[a], v[b], col));
      } else if (it.type === 'grid') {
        const n = it.n || 10;
        for (let i = 0; i <= n; i++) {
          const u = -s / 2 + (i / n) * s;
          add([px + u, py, pz - s / 2], [px + u, py, pz + s / 2], col); add([px - s / 2, py, pz + u], [px + s / 2, py, pz + u], col);
        }
      } else if (it.type === 'axes') {
        add([px, py, pz], [px + s, py, pz], col); add([px, py, pz], [px, py + s, pz], col); add([px, py, pz], [px, py, pz + s], col);
        const tk = it.ticks || 5;
        for (let i = 1; i <= tk; i++) {
          const u = (i / tk) * s, d = s * 0.025;
          add([px + u, py - d, pz], [px + u, py + d, pz]); add([px - d, py + u, pz], [px + d, py + u, pz]); add([px, py - d, pz + u], [px, py + d, pz + u]);
        }
        labs.push([[px + s * 1.06, py, pz], 'X'], [[px, py + s * 1.06, pz], 'Y'], [[px, py, pz + s * 1.06], 'Z']);
      } else if (it.type === 'cloud') {
        const r = rand(it.seed || 2);
        for (let i = 0; i < (it.n || 400); i++) {
          const a = r() * Math.PI * 2, b = Math.acos(2 * r() - 1), rr = s * (it.shell ? 1 : Math.cbrt(r()));
          pts.push([px + rr * Math.sin(b) * Math.cos(a), py + rr * Math.cos(b), pz + rr * Math.sin(b) * Math.sin(a), col]);
        }
      } else if (it.type === 'circle') {
        const n = 96;
        for (let i = 0; i < n; i++) {
          const a0 = (i / n) * Math.PI * 2, a1 = ((i + 1) / n) * Math.PI * 2;
          add([px + Math.cos(a0) * s, py, pz + Math.sin(a0) * s], [px + Math.cos(a1) * s, py, pz + Math.sin(a1) * s], col);
        }
        add([px, py, pz], [px + s, py, pz], col);
      }
    });
    const ink = o.ink || '#0D0D0E', acc = o.accent || '#2340FF', lw = (o.line || 1.4) * S;
    return {
      render(t, v = {}) {
        const rx = v.rx || 0, ry = v.ry || 0, rz = v.rz || 0, dist = v.dist || 6, fov = v.fov || 1.1;
        const cx = W * (v.cx == null ? 0.5 : v.cx), cy = H * (v.cy == null ? 0.5 : v.cy), f = Math.min(W, H) * fov;
        const [sx, cxr, sy, cyr, sz, czr] = [Math.sin(rx), Math.cos(rx), Math.sin(ry), Math.cos(ry), Math.sin(rz), Math.cos(rz)];
        const P = ([x, y, z]) => {
          let x1 = x * cyr + z * sy, z1 = -x * sy + z * cyr;
          let y1 = y * cxr - z1 * sx, z2 = y * sx + z1 * cxr;
          const x2 = x1 * czr - y1 * sz, y2 = x1 * sz + y1 * czr, d = dist + z2;
          return [cx + (x2 * f) / d, cy - (y2 * f) / d, d];
        };
        if (v.clear !== false) ctx.clearRect(0, 0, W, H);
        ctx.lineWidth = lw; ctx.lineCap = 'round';
        const dr = v.draw == null ? 1 : clamp(v.draw), N = segs.length;
        segs.forEach((sg, i) => {
          const local = clamp((dr - (i / N) * 0.85) / 0.15);   // segments draw on in order
          if (local <= 0) return;
          const a = P(sg[0]), b = P(sg[1]);
          ctx.strokeStyle = sg[2] === 'accent' ? acc : ink;
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(lerp(a[0], b[0], local), lerp(a[1], b[1], local)); ctx.stroke();
        });
        const pr = clamp((dr - 0.3) / 0.7);
        pts.forEach((p, i) => {
          if (i / pts.length > pr) return;
          const q = P(p), r0 = Math.max(0.8, 2.2 * S * 6 / q[2]);
          ctx.fillStyle = p[3] === 'accent' ? acc : ink;
          ctx.fillRect(q[0] - r0 / 2, q[1] - r0 / 2, r0, r0);
        });
        if (o.labels !== false && dr > 0.9) {
          ctx.fillStyle = ink; ctx.font = `500 ${12 * S}px "IBM Plex Mono", Menlo, monospace`;
          labs.forEach(([p, s]) => { const q = P(p); ctx.fillText(s, q[0] + 4 * S, q[1] - 4 * S); });
        }
      }
    };
  };

  /* ---------------------------------------------------------------- gait model (shared)
     Returns 2-D joints for a side-view figure of height 1 at phase φ (radians).
     kind: 'walk' | 'run' | 'jump' | 'wave' | 'stand'. Pure function → seekable. */
  GEN.pose = function (phi, kind = 'walk') {
    const s = Math.sin, c = Math.cos;
    const amp = kind === 'run' ? 0.62 : kind === 'walk' ? 0.42 : 0.05;
    const bob = kind === 'run' ? 0.035 * Math.abs(s(phi)) : kind === 'walk' ? 0.015 * c(2 * phi) : 0;
    let lift = 0, crouch = 0;
    if (kind === 'jump') { const q = (phi / (Math.PI * 2)) % 1; lift = Math.max(0, s(q * Math.PI * 2 - 0.6)) * 0.28; crouch = Math.max(0, -s(q * Math.PI * 2 - 0.6)) * 0.12; }
    const hip = [0, 0.53 + bob + lift - crouch];
    const leg = (ph) => {
      const th = amp * s(ph) - crouch * 1.2, kn = (kind === 'run' ? 1.1 : 0.7) * Math.max(0, s(ph + 1.4)) + crouch * 2.4;
      const knee = [hip[0] + 0.26 * s(th), hip[1] - 0.26 * c(th)];
      const sh = th - kn, ankle = [knee[0] + 0.25 * s(sh), knee[1] - 0.25 * c(sh)];
      const toe = [ankle[0] + 0.07, ankle[1] - 0.01];
      return { knee, ankle, toe };
    };
    const L = leg(phi), R = leg(phi + Math.PI);
    const lean = kind === 'run' ? 0.12 : 0.03;
    const neck = [hip[0] + 0.3 * s(lean), hip[1] + 0.3 * c(lean)], head = [neck[0] + 0.03, neck[1] + 0.1];
    const arm = (ph, waving) => {
      if (waving) { const a = 2.6 + 0.35 * s(phi * 2); const el = [neck[0] + 0.12 * s(a - 0.6), neck[1] - 0.02 + 0.12 * -c(a - 0.6)]; return { elbow: el, wrist: [el[0] + 0.13 * s(a), el[1] - 0.13 * c(a)] }; }
      const a = -amp * 0.9 * s(ph), el = [neck[0] + 0.15 * s(a), neck[1] - 0.04 - 0.15 * c(a)];
      const fa = a + (kind === 'run' ? 1.4 : 0.5);
      return { elbow: el, wrist: [el[0] + 0.14 * s(fa), el[1] - 0.14 * c(fa)] };
    };
    const AL = arm(phi + Math.PI, kind === 'wave'), AR = arm(phi, false);
    return {
      hip, neck, head,
      kneeL: L.knee, ankleL: L.ankle, toeL: L.toe, kneeR: R.knee, ankleR: R.ankle, toeR: R.toe,
      elbowL: AL.elbow, wristL: AL.wrist, elbowR: AR.elbow, wristR: AR.wrist
    };
  };
  const BONES = [['hip', 'neck'], ['hip', 'kneeL'], ['kneeL', 'ankleL'], ['ankleL', 'toeL'], ['hip', 'kneeR'], ['kneeR', 'ankleR'],
    ['ankleR', 'toeR'], ['neck', 'elbowL'], ['elbowL', 'wristL'], ['neck', 'elbowR'], ['elbowR', 'wristR']];

  /* ---------------------------------------------------------------- hand-drawn line figure
     opt: { W, H, ink, line, boil: 8 (Hz the line "redraws" at, like hand animation) }
     render(t, {x, y, h (px height), kind, phase, draw (0..1), travel (px/s), clear}) */
  GEN.figure = function (cv, o = {}) {
    const W = o.W, H = o.H, ctx = sizeCanvas(cv, W, H), S = Math.sqrt(W * H / (1920 * 1080));
    const ink = o.ink || '#0D0D0E', lw = (o.line || 3) * S, boil = o.boil || 8;
    const wob = (x, y, k, t) => {                              // hand jitter that changes in steps
      const st = Math.floor(t * boil);
      return [x + (h3(k, st, 1, 7) - 0.5) * 2.4 * S, y + (h3(k, st, 2, 7) - 0.5) * 2.4 * S];
    };
    return {
      render(t, v = {}) {
        if (v.clear !== false) ctx.clearRect(0, 0, W, H);
        const hpx = v.h || H * 0.42, kind = v.kind || 'walk', freq = v.freq || (kind === 'run' ? 1.6 : 1.0);
        const J = GEN.pose((v.phase || 0) + t * freq * Math.PI * 2, kind);
        const ox = (v.x == null ? W * 0.5 : v.x) + (v.travel || 0) * t, oy = v.y == null ? H * 0.82 : v.y;
        const P = (p) => [ox + p[0] * hpx, oy - p[1] * hpx];
        const dr = v.draw == null ? 1 : clamp(v.draw);
        ctx.strokeStyle = ink; ctx.lineWidth = lw; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        BONES.forEach(([a, b], i) => {
          const k = clamp((dr - i / BONES.length * 0.8) / 0.2);
          if (k <= 0) return;
          const A = wob(...P(J[a]), i * 2, t), B = wob(...P(J[b]), i * 2 + 1, t);
          // a slight bow in each stroke reads as a pen line, not a vector
          const mx = (A[0] + B[0]) / 2 + (h3(i, Math.floor(t * boil), 3, 7) - 0.5) * 4 * S, my = (A[1] + B[1]) / 2;
          ctx.beginPath(); ctx.moveTo(A[0], A[1]);
          const ex = lerp(A[0], B[0], k), ey = lerp(A[1], B[1], k);
          ctx.quadraticCurveTo(lerp(A[0], mx, k), lerp(A[1], my, k), ex, ey); ctx.stroke();
        });
        if (dr > 0.85) {
          const hd = wob(...P(J.head), 99, t), r = hpx * 0.075, k = clamp((dr - 0.85) / 0.15);
          ctx.beginPath(); ctx.arc(hd[0], hd[1], r, -Math.PI / 2, -Math.PI / 2 + k * Math.PI * 2); ctx.stroke();
        }
        if (v.ground) { ctx.lineWidth = lw * 0.6; ctx.beginPath(); ctx.moveTo(0, oy + 2 * S); ctx.lineTo(W * dr, oy + 2 * S); ctx.stroke(); }
      }
    };
  };

  /* ---------------------------------------------------------------- motion-analysis skeleton
     opt: { W, H, ink, accent, labels: true }
     render(t, {x, y, h, kind, freq, trail (s), trailJoints: ['ankleL','wristR'], draw}) */
  GEN.motion = function (cv, o = {}) {
    const W = o.W, H = o.H, ctx = sizeCanvas(cv, W, H), S = Math.sqrt(W * H / (1920 * 1080));
    const ink = o.ink || '#F2EFE8', acc = o.accent || '#D4FF3A';
    const mono = `500 ${12 * S}px "IBM Plex Mono", Menlo, monospace`;
    return {
      render(t, v = {}) {
        if (v.clear !== false) ctx.clearRect(0, 0, W, H);
        const hpx = v.h || H * 0.6, kind = v.kind || 'run', freq = v.freq || 1.3;
        const ox = v.x == null ? W * 0.5 : v.x, oy = v.y == null ? H * 0.86 : v.y;
        const at = (tt) => GEN.pose(tt * freq * Math.PI * 2, kind);
        const P = (p) => [ox + p[0] * hpx, oy - p[1] * hpx];
        const dr = v.draw == null ? 1 : clamp(v.draw);
        // trails: the joint's path over the last `trail` seconds (evaluated, not stored)
        const trail = v.trail == null ? 0.8 : v.trail, tj = v.trailJoints || ['ankleL', 'ankleR', 'wristR'];
        tj.forEach((j, n) => {
          ctx.strokeStyle = n === 0 ? acc : ink; ctx.lineWidth = 1.2 * S; ctx.globalAlpha = 0.55 * dr;
          ctx.beginPath();
          for (let k = 0; k <= 48; k++) {
            const q = P(at(t - trail + (k / 48) * trail)[j]);
            k ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]);
          }
          ctx.stroke();
        });
        ctx.globalAlpha = 1;
        const J = at(t);
        ctx.strokeStyle = ink; ctx.lineWidth = 1.6 * S;
        BONES.forEach(([a, b], i) => {
          if (i / BONES.length > dr) return;
          const A = P(J[a]), B = P(J[b]);
          ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.stroke();
        });
        Object.keys(J).forEach((k, i) => {
          if (i / 15 > dr) return;
          const q = P(J[k]), r = (k === 'head' ? 7 : 4) * S;
          ctx.fillStyle = k === 'kneeL' || k === 'ankleL' ? acc : ink;
          ctx.beginPath(); ctx.arc(q[0], q[1], r, 0, Math.PI * 2); ctx.fill();
        });
        if (o.labels !== false && dr > 0.6) {
          ctx.font = mono; ctx.fillStyle = ink;
          const ang = (a, b, c) => {
            const v1 = [a[0] - b[0], a[1] - b[1]], v2 = [c[0] - b[0], c[1] - b[1]];
            return Math.round(Math.acos(clamp((v1[0] * v2[0] + v1[1] * v2[1]) / (Math.hypot(...v1) * Math.hypot(...v2)), -1, 1)) * 180 / Math.PI);
          };
          [['kneeL', ['hip', 'kneeL', 'ankleL']], ['kneeR', ['hip', 'kneeR', 'ankleR']], ['elbowR', ['neck', 'elbowR', 'wristR']]].forEach(([k, tri]) => {
            const q = P(J[k]), a = ang(J[tri[0]], J[tri[1]], J[tri[2]]);
            ctx.fillText(`${k.toUpperCase()} ${String(a).padStart(3, '0')}°`, q[0] + 12 * S, q[1] + 4 * S);
          });
          ctx.fillText(`CYCLE ${((t * freq) % 1).toFixed(3)}   F ${String(Math.floor(t * 60)).padStart(5, '0')}`, ox - hpx * 0.6, oy + 30 * S);
        }
      }
    };
  };

  root.GEN = GEN;
})(window);
