/* 02 TYPOGRAPHIC EXPERIMENT — huge grotesk letters move independently and bleed off
   frame; ink and paper swap on the beat; then a push-through into the counter of the O
   lands on the paper of scene 03. */
(function () {
  const L = FILM.layer('type');
  const grp = el('div', 'abs', L); grp.style.left = '0px'; grp.style.top = '0px'; grp.style.width = W + 'px'; grp.style.height = H + 'px';
  const WORD = 'FORMS';
  const letters = WORD.split('').map(ch => {
    const s = el('div', 'sw-display abs', grp, ch); s.dataset.bleed = ''; s.style.fontSize = 760 * S + 'px'; return s;
  });
  const lab = label(L, 'STUDY 02 — LETTERS AS OBJECTS', G.mx, G.my);
  const lab2 = label(L, '', G.col(10).x, G.my);
  lab.dataset.bleed = ''; lab2.dataset.bleed = '';
  let xs = [], ws = [];
  const flips = [beat(2, 2), beat(3, 0), beat(3, 1), beat(3, 2), beat(3, 3)];
  const jumps = [0, 1, 2, 3, 4, 5, 6, 7].map(n => beat(2, 1 + n));                 // a letter jumps on each beat
  flips.concat(jumps, jumps.map(j => j + MUSIC.beat * 1.5)).forEach(MG.cut);   // jump up on the beat, back on the half-beat                                             // inversions and beat jumps are hard by design
  const ZIN = B(3) + MUSIC.beat * 3;                                               // push-through: the last beat of the bar
  FILM.scene({
    id: '02 type', start: B(2), end: B(4), el: L,
    setup() {
      return document.fonts.ready.then(() => {
        let x = 0;
        letters.forEach((s, i) => { ws[i] = s.offsetWidth; xs[i] = x; x += ws[i] * 0.94; });
      });
    },
    render(lt, ctx) {
      const t = ctx.t;
      const inv = MG.invert(t, flips) && t < ZIN;
      L.style.background = inv ? C.ink : C.paper;
      const ink = inv ? C.paper : C.ink;
      const slide = -MG.at(t, B(2), ZIN, E.linear) * W * 0.22;                     // slow drift left (controlled)
      letters.forEach((s, i) => {
        // each letter: jumps up/down on its beat, settles with a snap; never a fade
        let dy = 0;
        jumps.forEach((jt, n) => { if (n % WORD.length === i) dy += (n % 2 ? -1 : 1) * 0.22 * H * (MG.at(t, jt, jt + 0.18, E.snap) - MG.at(t, jt + MUSIC.beat * 1.5, jt + MUSIC.beat * 1.5 + 0.18, E.snap)); });
        const enter = MG.at(t, B(2) + i * 0.06, B(2) + 0.32 + i * 0.06, E.snap);
        s.style.left = (W * 0.06 + xs[i] + slide) + 'px';
        s.style.top = (H * 0.5 - 0.42 * 760 * S + dy + (1 - enter) * H * 0.9) + 'px';
        s.style.color = ink;
      });
      // push-through: zoom into the counter of the O (paper inside) → scene 03 starts on paper
      const zp = MG.at(t, ZIN, B(4), E.in);
      if (zp > 0) {
        const o = letters[1], r = o.getBoundingClientRect(), sr = stage.getBoundingClientRect();
        grp.style.transform = 'none';
        const k = sr.width / W;
        const fx = (r.left - sr.left) / k + r.width / (2 * k), fy = (r.top - sr.top) / k + r.height * 0.56 / k;
        grp.style.transform = MG.zoomTo(zp, fx, fy, W, H, 70);
      } else grp.style.transform = 'none';
      lab.style.color = lab2.style.color = ink;
      lab2.textContent = `SCALE ${(1 + zp * 69).toFixed(2)}×`;
    }
  });
})();
