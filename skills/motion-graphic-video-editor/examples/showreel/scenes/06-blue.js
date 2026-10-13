/* 06 BLUE HIT — full cobalt, massive type slams on the bar, a second word on the
   half-bar, then the whole frame scales out through the type. Rhythmic punctuation. */
(function () {
  const L = FILM.layer('blue', 'sw-blue');
  const w1 = el('div', 'sw-display abs', L, 'Scale'); w1.dataset.bleed = '';
  const w2 = el('div', 'sw-display abs', L, '× 40'); w2.dataset.bleed = '';
  [w1, w2].forEach(w => { w.style.color = C.paper; w.style.transformOrigin = '50% 55%'; });
  w1.style.fontSize = 520 * S + 'px'; w2.style.fontSize = 300 * S + 'px';
  const ls = [label(L, '06 / 12', G.col(10).x, G.my, C.paper), label(L, 'RHYTHM — 95.75 BPM', G.mx, G.my, C.paper), label(L, '', G.mx, H - G.my - 22 * S, C.paper)];
  const T0 = B(11), half = T0 + MUSIC.bar / 2;
  MG.cut(half);                                                                    // the second slam
  FILM.scene({
    id: '06 blue', start: T0, end: B(12), el: L,
    setup() {
      return document.fonts.ready.then(() => {
        w1.style.left = (W - w1.offsetWidth) / 2 + 'px'; w1.style.top = (H * 0.5 - 520 * S * 0.5) + 'px';
        w2.style.left = (G.col(7).x) + 'px'; w2.style.top = (H * 0.62) + 'px';
      });
    },
    render(lt, ctx) {
      const t = ctx.t;
      const out = MG.at(t, B(12) - 0.45, B(12), E.in);                             // exit: everything rushes at the camera
      const s1 = MG.hit(t, T0, 3.2) * (1 + out * 30);
      w1.style.transform = `scale(${s1})`;
      w1.style.visibility = t >= T0 ? 'visible' : 'hidden';
      const s2 = MG.hit(t, half, 2.0);
      w2.style.transform = `scale(${s2 * (1 + out * 8)}) translateX(${-out * W * 0.4}px)`;
      w2.style.visibility = t >= half ? 'visible' : 'hidden';
      ls[2].textContent = `SCALE ${s1.toFixed(3)}`;
      ls.forEach(l => { l.style.visibility = out > 0.3 ? 'hidden' : 'visible'; });
    }
  });
})();
