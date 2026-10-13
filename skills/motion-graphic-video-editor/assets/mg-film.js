/* mg-film.js — one master timeline for long, multi-scene films (showreels, 45–90 s).
 *
 * Load after mg-kit.js. Each scene lives in its own file (scenes/03-particles.js) and
 * registers itself; index.html lists the files in order and calls FILM.start().
 *
 *   FILM.config({ W, H, fps, dur, root: document.getElementById('stage') });
 *   FILM.scene({
 *     id: 'particles', start: 14.0, end: 19.5,      // seconds on the master timeline
 *     in: 'cut' | 'over',                           // 'cut' = hard cut at start (default);
 *                                                   // 'over' = overlaps the previous scene (transition drawn by either)
 *     pre: 0, post: 0,                              // keep the scene alive this long before/after (for transitions)
 *     setup(ctx) { ... build DOM/canvas/3D once ... return optional Promise },
 *     render(lt, ctx) { ... lt = local seconds since start; ctx.p = 0..1 through the scene ... }
 *   });
 *   FILM.start();   // after all scene files are loaded
 *
 * Contract kept: window.__render(frame) is pure, frames may be fractional, window.__ready
 * flips only after every scene's setup resolved. Only scenes alive at t are rendered and
 * the rest are display:none (DOM) / skipped (canvas, WebGL) — a 12-scene film costs what
 * one scene costs. window.__scenes exposes the table to the dev player and check tools;
 * every 'cut' boundary is declared with MG.cut so check_motion does not flag it.
 */
(function (root) {
  'use strict';
  const FILM = { scenes: [], cfg: { fps: 60 } };

  FILM.config = function (c) { Object.assign(FILM.cfg, c); return FILM.cfg; };

  FILM.scene = function (s) {
    if (s.start == null || s.end == null) throw new Error('FILM.scene needs start and end: ' + s.id);
    s.in = s.in || 'cut'; s.pre = s.pre || 0; s.post = s.post || 0;
    FILM.scenes.push(s);
    return s;
  };

  /* make a full-frame layer for a scene (DOM scenes draw into it) */
  FILM.layer = function (id, cls) {
    const el = document.createElement('div');
    el.id = 'scene-' + id;
    el.className = 'film-layer' + (cls ? ' ' + cls : '');
    el.style.cssText = 'position:absolute;inset:0;overflow:hidden;display:none';
    (FILM.cfg.root || document.body).appendChild(el);
    return el;
  };

  FILM.check = function () {
    const sc = FILM.scenes.slice().sort((a, b) => a.start - b.start), out = [];
    for (let i = 1; i < sc.length; i++) {
      const gap = sc[i].start - sc[i - 1].end;
      if (gap > 1e-6) out.push(`gap ${gap.toFixed(3)}s between ${sc[i - 1].id} and ${sc[i].id}`);
      if (gap < -1e-6 && sc[i].in !== 'over') out.push(`${sc[i].id} overlaps ${sc[i - 1].id} but in:'cut'`);
    }
    const dur = FILM.cfg.dur;
    if (dur && sc.length && Math.abs(sc[sc.length - 1].end - dur) > 1e-6) out.push(`last scene ends at ${sc[sc.length - 1].end}, film is ${dur}`);
    return out;
  };

  FILM.start = function () {
    const cfg = FILM.cfg, fps = cfg.fps;
    FILM.scenes.sort((a, b) => a.start - b.start);
    const problems = FILM.check();
    if (problems.length) console.warn('[FILM] ' + problems.join(' | '));
    root.__scenes = FILM.scenes.map(s => ({ id: s.id, start: s.start, end: s.end, in: s.in }));
    FILM.scenes.forEach(s => { if (s.in === 'cut' && s.start > 0 && root.MG) MG.cut(s.start); });

    const ctxOf = s => ({ W: cfg.W, H: cfg.H, S: Math.sqrt(cfg.W * cfg.H / (1920 * 1080)), fps, scene: s, film: FILM });
    // during setup every layer takes part in layout but stays invisible: a display:none
    // layer measures 0 wide, and every offsetWidth-based layout would silently collapse
    FILM.scenes.forEach(s => { if (s.el) { s.el.style.display = ''; s.el.style.visibility = 'hidden'; } });
    const setups = FILM.scenes.map(s => {
      s.ctx = ctxOf(s);
      return Promise.resolve(s.setup ? s.setup(s.ctx) : null);
    });
    const shown = Promise.all(setups).then(() => {
      FILM.scenes.forEach(s => { if (s.el) { s.el.style.visibility = ''; s.el.style.display = 'none'; } });
    });
    setups.push(shown);

    root.__render = function (frame) {
      const t = frame / fps;
      for (const s of FILM.scenes) {
        const alive = t >= s.start - s.pre && t < s.end + s.post;
        if (s.el) s.el.style.display = alive ? '' : 'none';
        if (s.onVisible) s.onVisible(alive);
        if (!alive) continue;
        const lt = t - s.start;
        s.ctx.t = t; s.ctx.lt = lt; s.ctx.dur = s.end - s.start;
        s.ctx.p = Math.max(0, Math.min(1, lt / (s.end - s.start)));
        s.render(lt, s.ctx);
      }
      if (cfg.onFrame) cfg.onFrame(t);
    };
    return (root.MG ? MG.ready(...setups) : Promise.all(setups).then(() => { root.__render(0); root.__ready = true; }));
  };

  root.FILM = FILM;
})(window);
