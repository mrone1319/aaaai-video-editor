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
  const prog = (t, a, b) => (b === a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));
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
    const W = innerWidth, H = innerHeight, out = { minText: null, minTextSample: '', outside: [] };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const txt = n.textContent.trim();
      if (!txt) continue;
      const el = n.parentElement, cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      let op = 1, e = el;
      while (e && e !== document.body) { op *= +getComputedStyle(e).opacity; e = e.parentElement; }
      if (op < 0.5) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.right < 0 || r.left > W || r.bottom < 0 || r.top > H) continue;
      // rendered size = font size × every ancestor's scale (bounding box vs layout box)
      const px = parseFloat(cs.fontSize) * (el.offsetHeight ? r.height / el.offsetHeight : 1);
      const share = px / H;
      if (out.minText === null || share < out.minText) { out.minText = share; out.minTextSample = txt.slice(0, 24); }
      if (r.left < W * safe || r.right > W * (1 - safe) || r.top < H * safe || r.bottom > H * (1 - safe))
        out.outside.push(txt.slice(0, 24));
    }
    return out;
  };

  root.MG = MG;
})(window);
