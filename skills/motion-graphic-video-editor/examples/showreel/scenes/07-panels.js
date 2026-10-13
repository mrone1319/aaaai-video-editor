/* 07 GENERATIVE GRID — editorial panels, each a live study (type grid, wireframe,
   line figure, counter). The figure panel grows to full screen and hands over to 08. */
(function () {
  const L = FILM.layer('panels'); L.style.background = C.paper;
  const T0 = B(12), GROW = B(13) + MUSIC.beat * 1.5, T1 = B(14);
  const rects = { a: G.cell(0, 1, 5, 4), b: G.cell(6, 1, 3, 3), c: G.cell(9, 1, 3, 5), d: G.cell(6, 5, 3, 2) };
  const panel = (r) => { const p = el('div', 'abs', L); MG.place(p, r); p.style.overflow = 'hidden'; p.style.outline = `${Math.max(1, 1.5 * S)}px solid ${C.ink}`; p.style.background = C.paper; return p; };
  const pa = panel(rects.a), pb = panel(rects.b), pd = panel(rects.d), pc = panel(rects.c);
  const ca = el('canvas', '', pa), cb = el('canvas', '', pb), cc = el('canvas', '', pc);
  const tg = GEN.typeGrid(ca, { W: Math.round(rects.a.w), H: Math.round(rects.a.h), cols: 10, rows: 7, glyphs: 'FORM', mode: 'mixed', ink: C.ink, paper: C.paper,
    wave: { kind: 'radial', cx: 4.5, cy: 3, freq: 0.9, speed: 1.4 }, margin: 0 });
  const wr = GEN.wire(cb, { W: Math.round(rects.b.w), H: Math.round(rects.b.h), ink: C.ink, accent: C.blue, labels: false,
    items: [{ type: 'cube', size: 1.5 }, { type: 'cube', size: 0.9, accent: true }, { type: 'cloud', n: 120, size: 1.1, seed: 9 }] });
  const fig = GEN.figure(cc, { W, H, ink: C.ink, line: 3 });
  cc.style.position = 'absolute'; cc.style.transformOrigin = '50% 50%';
  const num = el('div', 'sw-display abs', pd, '0'); num.style.fontSize = 120 * S + 'px'; num.style.left = 18 * S + 'px'; num.style.bottom = 10 * S + 'px';
  const tags = [['A — TYPE FIELD', rects.a], ['B — SOLIDS', rects.b], ['C — LINE / GAIT', rects.c], ['D — COUNT', rects.d]]
    .map(([s, r]) => label(L, s, r.x, r.y - 22 * S));
  const head = label(L, 'STUDY 07 — FOUR EXPERIMENTS, ONE GRID', G.mx, G.my); const idx = label(L, '07 / 12', G.col(10).x, G.my);
  const full = { x: 0, y: 0, w: W, h: H };
  FILM.scene({
    id: '07 panels', start: T0, end: T1, el: L,
    render(lt, ctx) {
      const t = ctx.t;
      [pa, pb, pc, pd].forEach((p, i) => MG.clip(p, MG.at(lt, 0.05 + i * 0.12, 0.45 + i * 0.12, E.snap), 'cols:5'));
      tags.concat([head, idx]).forEach((l, i) => MG.clip(l, MG.at(lt, 0.4 + i * 0.05, 0.7 + i * 0.05, E.snap), 'left'));
      tg.render(lt);
      wr.render(lt, { rx: 0.5 + lt * 0.3, ry: lt * 0.6, dist: 5, fov: 1.2, draw: MG.at(lt, 0.3, 1.6) });
      num.textContent = Math.round(MG.tween(lt, [[0.4, 0], [2.4, 2048, E.out]])).toLocaleString('en-US').replace(',', ' ');
      // the figure panel grows to full frame; everything else is wiped away under it
      const g = MG.at(t, GROW, T1, E.inOut), r = MG.rect(rects.c, full, g);
      MG.place(pc, r); pc.style.outlineColor = g > 0.98 ? 'transparent' : C.ink;
      const k = r.h / H;
      cc.style.left = (r.w / 2 - W / 2) + 'px'; cc.style.top = (r.h / 2 - H / 2) + 'px'; cc.style.transform = `scale(${MG.lerp(1.15, 1, g) * Math.max(k, 0.0001)})`;
      fig.render(t, { x: W * 0.5, y: H * 0.8, h: H * 0.42, kind: 'walk', draw: MG.at(lt, 0.5, 2.0), ground: g > 0.5 });
      pc.style.zIndex = g > 0 ? 5 : '';
    }
  });
})();
