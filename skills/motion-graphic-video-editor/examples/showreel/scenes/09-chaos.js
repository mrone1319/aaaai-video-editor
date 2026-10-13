/* 09 TYPOGRAPHIC CHAOS — controlled overload: a fast type grid of digits, two marquee
   bands running opposite ways, ink/paper swapping on every beat, blinds cropping on
   the off-beats. Short and loud, then a hard cut to the hero. */
(function () {
  const T0 = B(16), T1 = B(17);
  const L = FILM.layer('chaos');
  const cv = canvasIn(L);
  const gridA = GEN.typeGrid(cv, { W, H, cols: 24, rows: 12, glyphs: (i, j, t) => String((i * 7 + j * 3 + Math.floor(t * 12)) % 10),
    mode: 'mixed', wave: { kind: 'diag', freq: 0.5, speed: 3.2 }, ink: C.ink, paper: C.paper, weight: 700 });
  const gridB = GEN.typeGrid(cv, { W, H, cols: 24, rows: 12, glyphs: (i, j, t) => String((i * 7 + j * 3 + Math.floor(t * 12)) % 10),
    mode: 'mixed', wave: { kind: 'diag', freq: 0.5, speed: 3.2 }, ink: C.paper, paper: C.ink, weight: 700 });
  const band = (y, txt) => { const b = el('div', 'sw-display abs', L, (txt + ' ').repeat(8)); b.dataset.bleed = ''; b.style.fontSize = 210 * S + 'px'; b.style.top = y + 'px'; b.style.left = '0px'; return b; };
  const b1 = band(H * 0.12, 'SYSTEM'), b2 = band(H * 0.56, 'RHYTHM');
  const crop = el('div', 'abs', L); crop.style.inset = '0'; crop.style.background = C.blue;
  const big = el('div', 'sw-display abs', L, '09'); big.dataset.bleed = ''; big.style.fontSize = 560 * S + 'px'; big.style.right = (-40 * S) + 'px'; big.style.bottom = (-120 * S) + 'px';
  const flips = [0, 1, 2, 3].map(n => beat(16, n));
  flips.forEach(f => { MG.cut(f); MG.cut(f + MUSIC.beat * 0.5); });               // every beat and off-beat is a hard change here
  FILM.scene({
    id: '09 chaos', start: T0, end: T1, el: L,
    render(lt, ctx) {
      const t = ctx.t, inv = MG.invert(t, flips);
      (inv ? gridB : gridA).render(lt);
      const ink = inv ? C.paper : C.ink;
      const w1 = b1.offsetWidth / 8, w2 = b2.offsetWidth / 8;
      b1.style.transform = `translateX(${MG.marquee(lt, 2400 * S, w1, -1)}px)`;
      b2.style.transform = `translateX(${MG.marquee(lt, 1900 * S, w2, 1)}px)`;
      b1.style.color = b2.style.color = ink; big.style.color = C.lime;
      // blue blinds crop on the off-beats: in and out inside half a beat
      const ob = flips.map(f => f + MUSIC.beat * 0.5), k = ob.reduce((a, f) => Math.max(a, MG.at(t, f, f + MUSIC.beat * 0.45, E.linear)), 0);
      const active = ob.some(f => t >= f && t < f + MUSIC.beat * 0.45);
      MG.clip(crop, active ? 1 + k : 0, 'blinds:8');
      big.style.transform = `scale(${MG.hit(t, flips[2], 1.8)})`;
    }
  });
})();
