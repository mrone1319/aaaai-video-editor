/* 01 INTRO — off-white, tiny technical type, the grid draws itself, a block steps
   cell to cell on the beat, then oversized type enters from a mask. Hard cut. */
(function () {
  const L = FILM.layer('intro');
  L.style.background = C.paper;
  const rules = G.lines().filter(l => l.x != null).map((l, i) => {
    const r = el('div', 'sw-rule-v', L); r.style.left = l.x + 'px'; r.style.top = G.my + 'px'; r.style.height = (H - 2 * G.my) + 'px'; r.dataset.i = i; return r;
  });
  const top = el('div', 'sw-rule-h', L); top.style.left = G.mx + 'px'; top.style.top = G.my + 'px'; top.style.width = (W - 2 * G.mx) + 'px';
  const crosses = [[2, 2], [5, 5], [9, 3], [11, 6]].map(([i, j]) => {
    const c = el('div', 'sw-cross', L); const r = G.cell(i, j); c.style.left = (r.x - 7 * S) + 'px'; c.style.top = (r.y - 7 * S) + 'px'; return c;
  });
  const l1 = label(L, 'MG — SYSTEMS', G.mx + 10 * S, G.my + 10 * S);
  const l2 = label(L, '01 / 12', G.col(10).x + 10 * S, G.my + 10 * S);
  const l3 = label(L, 'X 0.000  Y 0.000', G.col(5).x + 10 * S, G.my + 10 * S);
  const l4 = label(L, '00:00:00', G.mx + 10 * S, H - G.my - 28 * S);
  const block = el('div', 'abs', L); block.style.background = C.ink;
  const steps = [[1, 1], [4, 1], [4, 3], [7, 2], [10, 4], [8, 5]];
  steps.forEach((_, k) => MG.cut(beat(0, 2) + k * MUSIC.beat));        // the block ticks cell to cell: intended jumps
  const big = el('div', 'sw-display abs', L, 'Motion');
  big.dataset.bleed = '';
  big.style.fontSize = 400 * S + 'px'; big.style.left = (G.mx - 14 * S) + 'px'; big.style.top = (H * 0.40) + 'px';
  let parts;
  FILM.scene({
    id: '01 intro', start: B(0), end: B(2), el: L,
    setup() { return document.fonts.ready.then(() => { parts = MG.split(big, 'chars'); }); },
    render(t) {
      rules.forEach((r, i) => { r.style.transform = `scaleY(${MG.at(t, 0.15 + i * 0.045, 0.75 + i * 0.045, E.out)})`; });
      top.style.transform = `scaleX(${MG.at(t, 0.1, 0.9, E.out)})`;
      crosses.forEach((c, i) => { c.style.transform = `scale(${MG.spring(t - 0.9 - i * 0.12, { stiffness: 400, damping: 20 })})`; });
      [l1, l2, l3, l4].forEach((l, i) => MG.clip(l, MG.at(t, 0.25 + i * 0.1, 0.55 + i * 0.1, E.snap), 'left'));
      const x = MG.at(t, 0.4, 2.6, E.inOut), y = MG.at(t, 0.4, 2.6, E.read);
      l3.textContent = `X ${x.toFixed(3)}  Y ${y.toFixed(3)}`;
      l4.textContent = tc(t);
      // rhythmic block: jumps cell to cell exactly on beats (no tween: it's a tick)
      const k = Math.floor((t - beat(0, 2)) / MUSIC.beat);
      if (k >= 0 && t < B(1) + MUSIC.beat * 2) {
        const [ci, cj] = steps[Math.min(k, steps.length - 1)], r = G.cell(ci, cj);
        MG.place(block, r); block.style.display = '';
      } else block.style.display = 'none';
      MG.reveal(parts, t, beat(1, 1), { style: 'mask', each: 0.035, dur: 0.6, ease: E.snap });
    }
  });
})();
