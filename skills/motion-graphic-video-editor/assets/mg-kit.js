/* mg-kit.js — motion vocabulary for deterministic, code-authored motion graphics.
 *
 * Load it with a plain <script src="mg-kit.js"></script> (copy it next to the
 * scene). Everything is a pure function of time, so it obeys the renderer's
 * contract: same frame in, same pixels out, and fractional frames (motion-blur
 * sub-samples) interpolate smoothly.
 *
 *   MG.ease.*            named curves (AE-style bezier presets + the classics)
 *   MG.bezier(x1,y1,x2,y2)   any CSS/AE cubic-bezier as an easing function
 *   MG.spring(t, opt)    damped spring 0→1 with real overshoot and settle
 *   MG.tween(t, keys)    keyframes: [[time, value, ease?], ...] numbers/arrays/colours
 *   MG.stagger(i, n, opt) per-item delay (start/center/end/edges/seeded random)
 *   MG.split(el, by)     split text into masked chars/words/lines for reveals
 *   MG.reveal(parts, t, t0, opt)  animate the split parts in (mask/rise/blur/scale/pop)
 *   MG.draw(path, p)     SVG stroke draw-on 0→1
 *   MG.morph(a, b, p)    morph between two SVG paths with the same command layout
 *   MG.camera(layers, cam) parallax camera over depth layers
 *   MG.noise(x, seed)    smooth 1-D value noise (organic drift, camera breathing)
 *   MG.lottie(el, opt)   frame-exact Lottie playback (needs vendor/lottie.min.js)
 *   MG.blur(a, b)        declare a motion-blur window (render_frames.py --mblur scene)
 *   MG.ready(...)        flip window.__ready once fonts, images and Lottie are loaded
 */
(function (root) {
  'use strict';
  const MG = {};

  /* ------------------------------------------------------------ basics */
  const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
  const lerp = (a, b, k) => a + (b - a) * k;
  // b < a is always a timing bug (an event scheduled past its own end): say so instead of running backwards
  const prog = (t, a, b) => {
    if (b < a) { if (!prog.warned) { prog.warned = 1; console.error(`MG.prog: window ends before it starts (${a.toFixed(3)} → ${b.toFixed(3)})`); } return t >= a ? 1 : 0; }
    return b === a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a));
  };
  MG.clamp = clamp; MG.lerp = lerp; MG.prog = prog;
  /* one-shot impulse: 0 before t0, 1 at t0, decays to 0 by t0+w. Never write flashes as 1-progress. */
  MG.imp = (t, t0, w, k = 2.4) => (t < t0 || t >= t0 + w ? 0 : Math.pow(1 - (t - t0) / w, k));
  /* map t through [a,b] with an easing; the workhorse: MG.at(t, 1.2, 1.8, MG.ease.out) */
  MG.at = (t, a, b, ease = MG.ease.smooth) => ease(prog(t, a, b));

  /* ------------------------------------------------------------ bezier */
  MG.bezier = function (x1, y1, x2, y2) {
    // Newton + bisection solve of x(s) = p, as browsers do for cubic-bezier()
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = s => ((ax * s + bx) * s + cx) * s;
    const sy = s => ((ay * s + by) * s + cy) * s;
    const dx = s => (3 * ax * s + 2 * bx) * s + cx;
    return function (p) {
      if (p <= 0) return 0;
      if (p >= 1) return 1;
      let s = p;
      for (let i = 0; i < 8; i++) {
        const e = sx(s) - p;
        if (Math.abs(e) < 1e-6) return sy(s);
        const d = dx(s);
        if (Math.abs(d) < 1e-6) break;
        s -= e / d;
      }
      let lo = 0, hi = 1; s = p;
      for (let i = 0; i < 30; i++) {
        const v = sx(s);
        if (Math.abs(v - p) < 1e-6) break;
        if (v < p) lo = s; else hi = s;
        s = (lo + hi) / 2;
      }
      return sy(s);
    };
  };

  /* ------------------------------------------------------------ easing vocabulary
     Pick by role, not by taste:
       smooth   — AE "Easy Ease": things that travel and land (default)
       out      — enters and settles (UI, cards); snappy start, long tail
       in       — leaves the frame; accelerates away
       snap     — confident arrival: 70% of the move in the first 25% of time
       expo     — hard "arrive and lock" (scale/opacity of impacts)
       read     — slow reveal meant to be read (~2s); gentle both ends
       whip     — whip pans / fast transitions: tiny ease in, violent middle
       anticipate / overshoot — wind-up before, or pass-and-return after
  */
  const E = {};
  E.linear = p => p;
  E.smooth = MG.bezier(0.33, 0, 0.67, 1);
  E.out = MG.bezier(0.16, 1, 0.3, 1);
  E.in = MG.bezier(0.7, 0, 0.84, 0);
  E.inOut = MG.bezier(0.65, 0, 0.35, 1);
  E.snap = MG.bezier(0.2, 0.9, 0.1, 1);
  E.read = MG.bezier(0.45, 0.05, 0.25, 1);
  E.whip = MG.bezier(0.85, 0, 0.15, 1);
  E.expo = p => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p));
  E.cubic = p => 1 - Math.pow(1 - p, 3);
  E.quint = p => 1 - Math.pow(1 - p, 5);
  E.sine = p => -(Math.cos(Math.PI * p) - 1) / 2;
  E.circ = p => Math.sqrt(1 - Math.pow(p - 1, 2));
  E.anticipate = (p, k = 1.6) => p * p * ((k + 1) * p - k);                  // dips back, then goes
  E.overshoot = (p, k = 1.7) => { const q = p - 1; return 1 + q * q * ((k + 1) * q + k); };
  E.anticipateOvershoot = (p, k = 1.4) => p < 0.5
    ? 0.5 * E.anticipate(p * 2, k * 1.5)
    : 0.5 * E.overshoot(p * 2 - 1, k * 1.5) + 0.5;
  E.steps = n => p => Math.min(1, Math.floor(p * n) / (n - 1 || 1));         // stop-motion / ticker
  MG.ease = E;

  /* ------------------------------------------------------------ spring
     Closed-form damped harmonic oscillator from 0 to 1 — no simulation, so any
     t (including fractional sub-frames) gives the same answer.
       stiffness 170 / damping 26  ≈ gentle "settle"     (default)
       stiffness 300 / damping 18  ≈ punchy pop with a visible overshoot
       stiffness 120 / damping 8   ≈ wobbly / playful (use sparingly)
     Returns the value; MG.spring.duration(opt) gives the time to settle within 0.1%. */
  MG.spring = function (t, opt = {}) {
    if (t <= 0) return 0;
    const m = opt.mass || 1, k = opt.stiffness || 170, c = opt.damping == null ? 26 : opt.damping;
    const v0 = -(opt.velocity || 0);
    const w0 = Math.sqrt(k / m), zeta = c / (2 * Math.sqrt(k * m));
    if (zeta < 1) {
      const wd = w0 * Math.sqrt(1 - zeta * zeta);
      const B = (zeta * w0 * 1 + v0) / wd;
      return 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + B * Math.sin(wd * t));
    }
    const B = v0 + w0;
    return 1 - Math.exp(-w0 * t) * (1 + B * t);
  };
  MG.spring.duration = function (opt = {}) {
    let last = 0;
    for (let t = 0; t < 10; t += 1 / 240) {
      if (Math.abs(MG.spring(t, opt) - 1) > 0.001) last = t;
    }
    return last;
  };
  /* spring between two values starting at t0 */
  MG.springTo = (t, t0, from, to, opt) => lerp(from, to, MG.spring(t - t0, opt));

  /* ------------------------------------------------------------ colour */
  const hex = c => {
    if (Array.isArray(c)) return c;
    c = c.replace('#', '');
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
  };
  MG.rgb = hex;
  MG.mix = (a, b, p) => {
    const x = hex(a), y = hex(b);
    return 'rgb(' + x.map((v, i) => Math.round(lerp(v, y[i], p))).join(',') + ')';
  };

  /* ------------------------------------------------------------ keyframes
     keys: [[time, value, ease?], ...]; ease applies to the segment ARRIVING at that key.
     value can be a number, an array of numbers, or a '#rrggbb' colour. */
  MG.tween = function (t, keys, defEase = E.smooth) {
    if (t <= keys[0][0]) return keys[0][1];
    const last = keys[keys.length - 1];
    if (t >= last[0]) return last[1];
    let i = 1;
    while (keys[i][0] < t) i++;
    const [ta, va] = keys[i - 1], [tb, vb, ez] = keys[i];
    const p = (ez || defEase)((t - ta) / (tb - ta));
    if (typeof va === 'number') return lerp(va, vb, p);
    if (typeof va === 'string') return MG.mix(va, vb, p);
    return va.map((v, j) => lerp(v, vb[j], p));
  };

  /* ------------------------------------------------------------ seeded random + noise */
  MG.rand = function (seed) {
    let s = seed | 0;
    return function () {
      s = (s + 0x6D2B79F5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  const hash = (i, seed) => {
    let h = Math.imul((i | 0) ^ 0x9E3779B9, 0x85EBCA6B) ^ Math.imul(seed | 0, 0xC2B2AE35);
    h ^= h >>> 13; h = Math.imul(h, 0x27D4EB2F); h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
  /* smooth value noise in [-1,1]; continuous in x, so it drifts organically and
     sub-frame samples stay consistent. MG.noise(t*0.4, 7) for a slow camera breath. */
  MG.noise = function (x, seed = 0) {
    const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
    return lerp(hash(i, seed), hash(i + 1, seed), u) * 2 - 1;
  };

  /* ------------------------------------------------------------ stagger
     Delay for item i of n. from: 'start' | 'end' | 'center' | 'edges' | 'random' | index.
     each: seconds between neighbours. For long lists prefer total: spread over a fixed span. */
  MG.stagger = function (i, n, opt = {}) {
    const each = opt.total != null ? opt.total / Math.max(1, n - 1) : (opt.each == null ? 0.05 : opt.each);
    const from = opt.from == null ? 'start' : opt.from;
    let k;
    if (from === 'start') k = i;
    else if (from === 'end') k = n - 1 - i;
    else if (from === 'center') k = Math.abs(i - (n - 1) / 2);
    else if (from === 'edges') k = (n - 1) / 2 - Math.abs(i - (n - 1) / 2);
    else if (from === 'random') {
      const order = MG.rand(opt.seed || 1);
      const idx = [...Array(n).keys()].map(j => [order(), j]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
      k = idx.indexOf(i);
    } else k = Math.abs(i - from);
    return k * each;
  };

  /* ------------------------------------------------------------ text split + reveal
     MG.split(el, 'chars' | 'words' | 'lines') wraps each part in a mask (overflow
     hidden) so 'mask' reveals slide up from behind a clean edge — the single most
     "designed" text move. Call once at setup, after fonts are ready (line breaks
     depend on the font). Returns [{el, mask, i}] in reading order. */
  MG.split = function (el, by = 'words') {
    const text = el.textContent;
    el.textContent = '';
    el.style.whiteSpace = by === 'lines' ? el.style.whiteSpace : 'pre-wrap';
    const parts = [];
    const make = (str) => {
      const mask = document.createElement('span');
      mask.style.cssText = 'display:inline-block;overflow:hidden;vertical-align:top;' +
        'padding:0.08em 0.02em 0.12em;margin:-0.08em -0.02em -0.12em';
      const inner = document.createElement('span');
      inner.style.cssText = 'display:inline-block;will-change:transform,opacity,filter';
      inner.textContent = str;
      mask.appendChild(inner);
      return { mask, el: inner };
    };
    if (by === 'chars') {
      // keep words together so a line never breaks mid-word
      text.split(/(\s+)/).forEach(tok => {
        if (/^\s+$/.test(tok)) { el.appendChild(document.createTextNode(tok)); return; }
        const w = document.createElement('span');
        w.style.cssText = 'display:inline-block;white-space:nowrap';
        Array.from(tok).forEach(ch => { const p = make(ch); w.appendChild(p.mask); parts.push(p); });
        el.appendChild(w);
      });
    } else if (by === 'words') {
      // CJK has no spaces: treat each Han character as a word so it can still wrap and stagger
      const toks = text.match(/[㐀-鿿豈-﫿]|[^\s㐀-鿿豈-﫿]+|\s+/g) || [];
      toks.forEach(tok => {
        if (/^\s+$/.test(tok)) { el.appendChild(document.createTextNode(tok)); return; }
        const p = make(tok); el.appendChild(p.mask); parts.push(p);
      });
    } else {
      // lines: lay the words out first, then group them by their rendered top
      const words = (text.match(/[㐀-鿿豈-﫿]|[^\s㐀-鿿豈-﫿]+|\s+/g) || []);
      const spans = words.map(w => { const s = document.createElement('span'); s.textContent = w; el.appendChild(s); return s; });
      const lines = [];
      let top = null;
      spans.forEach(s => {
        const y = s.offsetTop;
        if (top === null || Math.abs(y - top) > 2) { lines.push([]); top = y; }
        lines[lines.length - 1].push(s.textContent);
      });
      el.textContent = '';
      lines.forEach((ws, j) => {
        const p = make(ws.join('').trim());
        p.mask.style.display = 'block';
        el.appendChild(p.mask);
        parts.push(p);
      });
    }
    parts.forEach((p, i) => (p.i = i));
    return parts;
  };

  /* style: 'mask' (slide up from behind the mask edge) | 'rise' (fade + lift) |
     'blur' (focus pull in) | 'scale' (grow from small) | 'pop' (spring scale) |
     'type' (typewriter, no motion). out: optional exit time, same style reversed. */
  MG.reveal = function (parts, t, t0, opt = {}) {
    const style = opt.style || 'mask', dur = opt.dur || 0.7, n = parts.length;
    const ease = opt.ease || (style === 'mask' ? E.out : E.smooth);
    const each = opt.each == null ? (style === 'type' ? 0.045 : 0.06) : opt.each;
    parts.forEach((p, i) => {
      const d = t0 + MG.stagger(i, n, { each, from: opt.from || 'start', seed: opt.seed });
      let k = style === 'pop' ? MG.spring(t - d, opt.spring || { stiffness: 300, damping: 18 }) : ease(prog(t, d, d + dur));
      if (opt.out != null) {
        const od = opt.out + MG.stagger(i, n, { each: each * 0.6, from: opt.from || 'start' });
        k *= 1 - E.in(prog(t, od, od + dur * 0.6));
      }
      const s = p.el.style;
      if (style === 'mask') {
        s.transform = `translateY(${(1 - k) * 110}%)`;
        s.opacity = 1;
      } else if (style === 'rise') {
        s.transform = `translateY(${(1 - k) * 0.45}em)`;
        s.opacity = clamp(k * 1.4);
      } else if (style === 'blur') {
        s.filter = k >= 1 ? 'none' : `blur(${(1 - k) * 0.35}em)`;
        s.opacity = clamp(k * 1.2);
        s.transform = `scale(${lerp(1.08, 1, k)})`;
      } else if (style === 'scale' || style === 'pop') {
        s.transform = `scale(${Math.max(0, k)})`;
        s.opacity = clamp(k * 3);
      } else if (style === 'type') {
        s.opacity = t >= d ? 1 : 0;
      }
    });
  };

  /* ------------------------------------------------------------ SVG draw + morph */
  const lenCache = new WeakMap();
  MG.draw = function (path, p, opt = {}) {
    let L = lenCache.get(path);
    if (!L) { L = path.getTotalLength(); lenCache.set(path, L); }
    const from = opt.from || 0;            // 0 = draw from the path start; 0.5 = grow from the middle
    const vis = L * clamp(p);
    path.style.strokeDasharray = `${vis} ${L}`;
    path.style.strokeDashoffset = `${-(L - vis) * from}`;
    path.style.visibility = p <= 0 ? 'hidden' : 'visible';
  };
  /* Morph two path strings that share the same commands (same count and order of
     numbers) — export both shapes from the same template. Throws if they don't match. */
  MG.morph = function (a, b, p) {
    const num = /-?\d*\.?\d+(?:e-?\d+)?/gi;
    const na = a.match(num), nb = b.match(num);
    if (!na || !nb || na.length !== nb.length) throw new Error('MG.morph: paths need the same number of points');
    let i = 0;
    return a.replace(num, () => { const v = lerp(+na[i], +nb[i], p); i++; return v.toFixed(2); });
  };

  /* ------------------------------------------------------------ camera / parallax
     layers: [{el, z}] where z is depth (0 = on the focal plane, + = further away,
     - = closer). cam: {x, y, zoom, rot} in px / scale / degrees. Far layers move
     less and scale less, near layers more — instant depth from flat artwork. */
  MG.camera = function (layers, cam) {
    const zoom = cam.zoom || 1, x = cam.x || 0, y = cam.y || 0, rot = cam.rot || 0;
    layers.forEach(L => {
      const z = L.z || 0, f = 1 / (1 + z);                 // parallax factor
      const zs = 1 + (zoom - 1) * f;
      const s = L.el.style;
      s.transform = `translate(${-x * f}px, ${-y * f}px) scale(${zs}) rotate(${rot * f}deg)`;
      if (L.focus != null) {                                // depth of field: blur away from the focal z
        const b = Math.abs(z - L.focus) * (cam.dof || 0);
        s.filter = b > 0.05 ? `blur(${b}px)` : 'none';
      }
    });
  };

  /* ------------------------------------------------------------ Lottie
     Frame-exact Lottie: MG.lottie(el, {path | data, start, speed, loop}) → controller;
     call ctl.at(t) from __render. Requires vendor/lottie.min.js on the page.
     The animation's own frame rate is respected (a 24 fps Lottie in a 60 fps film
     holds frames like the original, which is how it was designed). */
  const pending = [];
  MG.lottie = function (el, opt = {}) {
    if (!root.lottie) throw new Error('MG.lottie: load vendor/lottie.min.js first');
    const anim = root.lottie.loadAnimation({
      container: el, renderer: opt.renderer || 'svg', loop: false, autoplay: false,
      path: opt.path, animationData: opt.data,
      rendererSettings: { preserveAspectRatio: opt.fit || 'xMidYMid meet' }
    });
    const ready = new Promise(res => anim.addEventListener('DOMLoaded', res));
    pending.push(ready);
    const start = opt.start || 0, speed = opt.speed || 1;
    return {
      anim, ready,
      at(t) {
        const total = anim.totalFrames, fr = anim.frameRate || 30;
        let f = (t - start) * speed * fr;
        if (opt.loop) f = ((f % total) + total) % total;
        f = clamp(f, 0, total - 1);
        anim.goToAndStop(f, true);
        el.style.visibility = t < start ? 'hidden' : 'visible';
      }
    };
  };

  /* ------------------------------------------------------------ declarations for the tools
     MG.blur(a,b)  motion-blur window (render_frames.py --mblur scene)
     MG.hold(a,b)  an intended still (poster frame, end board) — check_motion won't flag it
     MG.cut(t)     an intended hard cut — check_motion won't flag the jump */
  root.__mblur = root.__mblur || [];
  root.__holds = root.__holds || [];
  root.__cuts = root.__cuts || [];
  MG.blur = (a, b) => { root.__mblur.push([a, b]); };
  MG.hold = (a, b) => { root.__holds.push([a, b]); };
  MG.cut = t => { root.__cuts.push(t); };

  /* ------------------------------------------------------------ readiness
     MG.ready(extraPromise...) waits for fonts, every <img>, every Lottie, and
     anything else you pass, renders frame 0, then sets window.__ready. */
  MG.ready = function (...extra) {
    const imgs = [...document.images].map(im => im.complete ? Promise.resolve() :
      new Promise(r => { im.onload = im.onerror = r; }));
    return Promise.all([document.fonts.ready, ...imgs, ...pending, ...extra]).then(() => {
      if (root.__render) root.__render(0);
      root.__ready = true;
    });
  };

  /* ------------------------------------------------------------ audits (renderer helpers)
     window.__audit() → smallest visible text size as a share of frame height, and
     any visible text outside the safe area. render_frames/check_motion use it. */
  root.__audit = function (safe = 0.05) {
    // safe margin = share of the SHORT side on every edge (the same rule MG.grid uses), minus 2px slack
    const W = innerWidth, H = innerHeight, out = { minText: null, minTextSample: '', outside: [] };
    const m = safe * Math.min(W, H) - 2;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const txt = n.textContent.trim();
      if (!txt) continue;
      const el = n.parentElement, cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      // data-deco: texture text not meant to be read (tiny technical labels, type grids);
      // data-bleed: type that deliberately runs off the frame
      const deco = el.closest('[data-deco]'), bleed = el.closest('[data-bleed]');
      if (deco && bleed) continue;
      let op = 1, e = el;
      while (e && e !== document.body) { op *= +getComputedStyle(e).opacity; e = e.parentElement; }
      if (op < 0.5) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.right < 0 || r.left > W || r.bottom < 0 || r.top > H) continue;
      // rendered size = font size × every ancestor's scale (bounding box vs layout box)
      const px = parseFloat(cs.fontSize) * (el.offsetHeight ? r.height / el.offsetHeight : 1);
      const share = px / H;
      if (!deco && (out.minText === null || share < out.minText)) { out.minText = share; out.minTextSample = txt.slice(0, 24); }
      if (!bleed && (r.left < m || r.right > W - m || r.top < m || r.bottom > H - m))
        out.outside.push(txt.slice(0, 24));
    }
    return out;
  };

  /* ============================================================ layout & graphic transitions
     Editorial (Swiss) composition: a modular grid instead of "centre everything". */

  /* MG.grid({cols, rows, W, H, margin, gutter}) → g
       g.col(i, span) → {x, w}      g.row(j, span) → {y, h}
       g.cell(i, j, cs, rs) → {x, y, w, h}  (column i, row j, spanning cs × rs)
       g.lines() → [{x}|{y}] edges for drawing the grid itself
     margin/gutter in px (default: margin 5% of the short side, gutter 1.6%). */
  MG.grid = function (o = {}) {
    const W = o.W || innerWidth, H = o.H || innerHeight, M = Math.min(W, H);
    const cols = o.cols || 12, rows = o.rows || 8;
    const mx = o.margin == null ? M * 0.05 : (o.margin.x == null ? o.margin : o.margin.x);
    const my = o.margin == null ? M * 0.05 : (o.margin.y == null ? o.margin : o.margin.y);
    const gx = o.gutter == null ? M * 0.016 : o.gutter, gy = o.gutterY == null ? gx : o.gutterY;
    const cw = (W - 2 * mx - gx * (cols - 1)) / cols, rh = (H - 2 * my - gy * (rows - 1)) / rows;
    const g = { W, H, cols, rows, mx, my, gx, gy, cw, rh };
    g.col = (i, span = 1) => ({ x: mx + i * (cw + gx), w: span * cw + (span - 1) * gx });
    g.row = (j, span = 1) => ({ y: my + j * (rh + gy), h: span * rh + (span - 1) * gy });
    g.cell = (i, j, cs = 1, rs = 1) => Object.assign({}, g.col(i, cs), g.row(j, rs));
    g.lines = () => {
      const out = [];
      for (let i = 0; i <= cols; i++) out.push({ x: i === cols ? W - mx : mx + i * (cw + gx) - (i ? gx / 2 : 0) });
      for (let j = 0; j <= rows; j++) out.push({ y: j === rows ? H - my : my + j * (rh + gy) - (j ? gy / 2 : 0) });
      return out;
    };
    return g;
  };
  /* absolutely position an element on a rect {x, y, w, h} (any field optional) */
  MG.place = function (el, r) {
    const s = el.style;
    s.position = 'absolute';
    if (r.x != null) s.left = r.x + 'px';
    if (r.y != null) s.top = r.y + 'px';
    if (r.w != null) s.width = r.w + 'px';
    if (r.h != null) s.height = r.h + 'px';
  };
  /* layout morph: a panel in a grid becoming full screen (rect A → rect B) */
  MG.rect = (a, b, p) => ({ x: lerp(a.x, b.x, p), y: lerp(a.y, b.y, p), w: lerp(a.w, b.w, p), h: lerp(a.h, b.h, p) });

  /* MG.clip(el, p, style) — graphic wipe (p 0 = hidden, 1 = fully shown; 1→2 wipes it
     off again in the same direction, so one call covers in and out).
     style: 'left' | 'right' | 'up' | 'down' (direction of travel) | 'center' (opens from a
     horizontal line) | 'circle' | 'diag' | 'blinds:N' (N horizontal strips) | 'cols:N'
     (N vertical strips, staggered left→right). */
  MG.clip = function (el, p, style = 'left') {
    const off = p > 1, k = clamp(off ? p - 1 : p);
    const a = (off ? k : 0) * 100, b = (off ? 1 : k) * 100;          // visible band [a, b] in %
    const [kind, nStr] = style.split(':'), n = +nStr || 6;
    let cp, shown = off ? 1 - k : k;
    if (kind === 'left') cp = `inset(0 ${100 - b}% 0 ${a}%)`;
    else if (kind === 'right') cp = `inset(0 ${a}% 0 ${100 - b}%)`;
    else if (kind === 'up') cp = `inset(${100 - b}% 0 ${a}% 0)`;
    else if (kind === 'down') cp = `inset(${a}% 0 ${100 - b}% 0)`;
    else if (kind === 'center') { const h = shown * 50; cp = `inset(${50 - h}% 0 ${50 - h}% 0)`; }
    else if (kind === 'circle') cp = `circle(${shown * 75}% at 50% 50%)`;
    else if (kind === 'diag') { const q = shown * 200; cp = `polygon(0 0, ${q}% 0, ${q - 100}% 100%, 0 100%)`; }
    else if (kind === 'blinds' || kind === 'cols') {
      // one polygon tracing every strip, joined along the outer edge so no slivers leak
      const pts = [];
      for (let i = 0; i < n; i++) {
        const lag = kind === 'cols' ? (i / n) * 0.5 : 0;
        const kk = clamp((k - lag) / (kind === 'cols' ? 0.5 : 1));
        const v = off ? 1 - kk : kk, s0 = (i / n) * 100, s1 = ((i + v) / n) * 100;
        if (kind === 'blinds') pts.push(`0% ${s0}%`, `100% ${s0}%`, `100% ${s1}%`, `0% ${s1}%`, `0% ${s0}%`);
        else pts.push(`${s0}% 0%`, `${s1}% 0%`, `${s1}% 100%`, `${s0}% 100%`, `${s0}% 0%`);
      }
      cp = `polygon(${pts.join(',')})`;
    }
    el.style.clipPath = cp;
    el.style.visibility = shown <= 0.0005 ? 'hidden' : 'visible';
  };

  /* Background inversion on a rhythm: MG.invert(t, [t1, t2, ...]) → true after an odd
     number of flips. Feed it to MG.swap so every layer trades ink and paper on the same
     frame (a hard, graphic punctuation — never cross-fade it). */
  MG.invert = (t, flips) => flips.reduce((n, f) => n + (t >= f ? 1 : 0), 0) % 2 === 1;
  MG.swap = function (el, inverted, ink, paper) {
    el.style.setProperty('--ink', inverted ? paper : ink);
    el.style.setProperty('--paper', inverted ? ink : paper);
  };

  /* Push-through zoom: scale so the point (fx, fy) — in the element's own px — rushes
     to fill the frame; cut to the next scene "inside" it at the end. p = eased 0→1. */
  MG.zoomTo = function (p, fx, fy, W, H, maxScale = 40) {
    const s = Math.exp(Math.log(maxScale) * p);             // exponential = constant perceived speed
    const tx = (W / 2 - fx) * clamp(p * 1.4), ty = (H / 2 - fy) * clamp(p * 1.4);
    return `translate(${tx}px,${ty}px) translate(${fx}px,${fy}px) scale(${s}) translate(${-fx}px,${-fy}px)`;
  };

  /* Marquee offset (px) for a strip of width w at speed px/s, wrapping seamlessly —
     put the text in the strip twice. dir -1 = leftward. */
  MG.marquee = (t, speed, w, dir = -1) => {
    const x = ((t * speed) % w + w) % w;
    return dir < 0 ? -x : x - w;
  };

  /* Scale hit: a word slams in oversized and locks (rapid text scaling). Scale for t. */
  MG.hit = (t, t0, from = 2.4, opt = { stiffness: 520, damping: 30 }) =>
    t < t0 ? 0 : lerp(from, 1, MG.spring(t - t0, opt));

  /* Deterministic per-cell field for type grids / rhythmic repetition → 0..1
     kind: 'diag' | 'rows' | 'cols' | 'radial' (cx, cy) | 'noise' | 'random' (seeded flicker at `rate` Hz) */
  MG.wave = function (i, j, t, o = {}) {
    const f = o.freq || 0.35, sp = o.speed || 1.2, kind = o.kind || 'diag';
    if (kind === 'diag') return 0.5 + 0.5 * Math.sin((i + j) * f - t * sp * Math.PI);
    if (kind === 'rows') return 0.5 + 0.5 * Math.sin(j * f - t * sp * Math.PI);
    if (kind === 'cols') return 0.5 + 0.5 * Math.sin(i * f - t * sp * Math.PI);
    if (kind === 'radial') return 0.5 + 0.5 * Math.sin(Math.hypot(i - (o.cx || 0), j - (o.cy || 0)) * f - t * sp * Math.PI);
    if (kind === 'noise') return 0.5 + 0.5 * MG.noise(t * sp + i * 3.1 + j * 7.7, o.seed || 1);
    return hash(i * 131 + j * 977 + Math.floor(t * (o.rate || 8)) * 7919, o.seed || 1);
  };

  root.MG = MG;
})(window);
