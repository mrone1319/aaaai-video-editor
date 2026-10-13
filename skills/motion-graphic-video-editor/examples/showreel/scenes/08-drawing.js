/* 08 DRAWING / HUMAN MOTION — the hand-drawn walker continues full screen (same
   timing as the panel, so the cut is invisible), then a hard inverted cut to a
   motion-analysis skeleton: joints, bones, trails, live angle readouts. */
(function () {
  const T0 = B(14), CUT = B(15), T1 = B(16);
  const L = FILM.layer('drawing'); L.style.background = C.paper;
  const cf = canvasIn(L);
  const fig = GEN.figure(cf, { W, H, ink: C.ink, line: 3 });
  const la = [label(L, 'STUDY 08 — LINE / GAIT', G.mx, G.my), label(L, '08 / 12', G.col(10).x, G.my), label(L, '', G.mx, H - G.my - 22 * S)];
  const M = FILM.layer('motion'); M.style.background = C.ink;
  const cm = canvasIn(M);
  const mo = GEN.motion(cm, { W, H, ink: C.paper, accent: C.lime });
  const lm = [label(M, 'STUDY 08B — MOTION ANALYSIS', G.mx, G.my, C.paper), label(M, '15 JOINTS · 11 SEGMENTS · 60 HZ', G.mx, G.my + 22 * S, C.paper),
    label(M, '08 / 12', G.col(10).x, G.my, C.paper)];
  const ground = el('div', 'sw-rule-h', M); ground.style.background = C.paper; ground.style.left = G.mx + 'px'; ground.style.width = (W - 2 * G.mx) + 'px'; ground.style.top = (H * 0.86) + 'px';
  FILM.scene({
    id: '08 drawing', start: T0, end: CUT, el: L,
    render(lt, ctx) {
      fig.render(ctx.t, { x: W * 0.5, y: H * 0.8, h: H * 0.42, kind: 'walk', draw: 1, ground: true });
      la[2].textContent = `BOIL 8 FPS   STROKE 3.0   T ${ctx.t.toFixed(2)}`;
    }
  });
  FILM.scene({
    id: '08b motion', start: CUT, end: T1, el: M,
    render(lt, ctx) {
      mo.render(ctx.t, { x: W * 0.55, y: H * 0.86, h: H * 0.62, kind: 'run', freq: 1.25, trail: 0.7, draw: MG.at(lt, 0, 0.5, E.snap) });
      ground.style.transform = `scaleX(${MG.at(lt, 0, 0.6, E.out)})`;
      lm.forEach((l, i) => MG.clip(l, MG.at(lt, 0.1 + i * 0.08, 0.4 + i * 0.08, E.snap), 'left'));
    }
  });
})();
