/* 11 RESOLUTION + 12 END FRAME — strip everything back: the grid retracts into one
   hairline, the hairline shortens, and a single line of type closes the film. */
(function () {
  const L = FILM.layer('resolve'); L.style.background = C.paper;
  const rules = G.lines().filter(l => l.x != null).map(l => {
    const r = el('div', 'sw-rule-v', L); r.style.left = l.x + 'px'; r.style.top = G.my + 'px'; r.style.height = (H - 2 * G.my) + 'px'; return r;
  });
  const hair = el('div', 'sw-rule-h', L); hair.style.left = G.mx + 'px'; hair.style.top = G.row(5).y + 'px'; hair.style.width = (W - 2 * G.mx) + 'px';
  const l1 = label(L, '11 / 12', G.col(10).x, G.my);
  const T0 = B(20), END = B(21), T1 = MUSIC.dur;
  MG.hold(T0, END);                                                                   // resolution: deliberate stillness, back to negative space
  FILM.scene({
    id: '11 resolve', start: T0, end: END, el: L,
    render(lt) {
      rules.forEach((r, i) => { r.style.transform = `scaleY(${1 - MG.at(lt, 0.1 + i * 0.05, 0.7 + i * 0.05, E.in)})`; });
      hair.style.transform = `scaleX(${1 - 0.78 * MG.at(lt, 1.0, 2.2, E.inOut)})`;
      MG.clip(l1, 1 + MG.at(lt, 0.4, 0.7, E.snap), 'left');
    }
  });

  const F = FILM.layer('end'); F.style.background = C.paper;
  const hair2 = el('div', 'sw-rule-h', F); hair2.style.left = G.mx + 'px'; hair2.style.top = G.row(5).y + 'px'; hair2.style.width = (W - 2 * G.mx) * 0.22 + 'px';
  const line = el('div', 'sw-head abs', F, 'Made with code.'); line.style.fontSize = 112 * S + 'px'; line.style.left = G.mx + 'px'; line.style.top = (G.row(5).y + 26 * S) + 'px';
  const sig = label(F, 'MOTION-GRAPHIC-VIDEO-EDITOR · 2026', G.mx, G.row(7).y + G.rh - 24 * S);
  const dot = el('div', 'abs', F); dot.style.background = C.lime; dot.style.width = dot.style.height = 18 * S + 'px'; dot.style.borderRadius = '50%';
  let parts;
  MG.hold(END + 1.2, T1);
  FILM.scene({
    id: '12 end', start: END, end: T1, el: F,
    setup() { return document.fonts.ready.then(() => { parts = MG.split(line, 'words'); }); },
    render(lt) {
      MG.reveal(parts, lt, 0.05, { style: 'mask', each: 0.09, dur: 0.7, ease: E.out });
      MG.clip(sig, MG.at(lt, 0.6, 0.9, E.snap), 'left');
      const lw = line.offsetWidth;
      dot.style.left = (G.mx + lw + 22 * S) + 'px'; dot.style.top = (G.row(5).y + 26 * S + 112 * S * 0.62) + 'px';
      dot.style.transform = `scale(${MG.spring(lt - 0.9, { stiffness: 380, damping: 18 })})`;
    }
  });
})();
