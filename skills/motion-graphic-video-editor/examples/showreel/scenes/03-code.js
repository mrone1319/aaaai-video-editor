/* 03 CREATIVE CODING — construction drawing: cube, axes, ground grid and a blue circle
   draw themselves on; a sine trace runs along the baseline; readouts change live.
   Ends with a hard inversion cut into the black particle study. */
(function () {
  const L = FILM.layer('code'); L.style.background = C.paper;
  const cv = canvasIn(L);
  const wire = GEN.wire(cv, {
    W, H, ink: C.ink, accent: C.blue, line: 1.3,
    items: [{ type: 'grid', size: 4, n: 12, pos: [0, -1.1, 0] }, { type: 'cube', size: 1.6 }, { type: 'axes', size: 1.8, pos: [-0.8, -0.8, -0.8], ticks: 6 },
      { type: 'circle', size: 1.45, pos: [0, -1.1, 0], accent: true }, { type: 'cloud', n: 260, size: 1.35, shell: true, seed: 4 }]
  });
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg'); svg.setAttribute('width', W); svg.setAttribute('height', H);
  svg.style.cssText = 'position:absolute;left:0;top:0;overflow:visible'; L.appendChild(svg);
  const path = document.createElementNS(svgNS, 'path'); path.setAttribute('fill', 'none'); path.setAttribute('stroke', C.ink);
  path.setAttribute('stroke-width', 1.5 * S); svg.appendChild(path);
  const y0 = G.row(7).y + G.rh * 0.5, x0 = G.mx, x1 = W - G.mx;
  let d = '';
  for (let i = 0; i <= 240; i++) { const u = i / 240, x = x0 + u * (x1 - x0), y = y0 - Math.sin(u * Math.PI * 6) * Math.exp(-u * 1.4) * 34 * S; d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); }
  path.setAttribute('d', d);
  const head = el('div', 'sw-head abs', L, 'Construction'); head.style.left = G.mx + 'px'; head.style.top = G.row(0).y + 'px'; head.style.fontSize = 72 * S + 'px';
  const ls = [label(L, 'STUDY 03 — PROCEDURAL GEOMETRY', G.mx, G.row(1).y + 10 * S), label(L, '', G.mx, G.row(1).y + 32 * S),
    label(L, '', G.mx, G.row(1).y + 54 * S), label(L, 'f(x) = sin(6πx) · e^(−1.4x)', x0, y0 - 64 * S), label(L, '03 / 12', G.col(10).x, G.my)];
  let hp;
  FILM.scene({
    id: '03 code', start: B(4), end: B(6), el: L,
    setup() { return document.fonts.ready.then(() => { hp = MG.split(head, 'chars'); }); },
    render(lt) {
      const ry = -0.6 + lt * 0.22, rx = 0.42 + 0.05 * Math.sin(lt * 0.7);
      wire.render(lt, { rx, ry, dist: 6.2, fov: 1.05, cx: 0.62, cy: 0.5, draw: MG.at(lt, 0.15, 2.6, E.smooth) });
      MG.draw(path, MG.at(lt, 0.8, 3.2, E.inOut));
      MG.reveal(hp, lt, 0.1, { style: 'mask', each: 0.025, dur: 0.5, ease: E.snap });
      ls[1].textContent = `RX ${rx.toFixed(3)}  RY ${ry.toFixed(3)}`;
      ls[2].textContent = `VERTICES ${pad(Math.min(1, MG.at(lt, 0.15, 2.6)) * 312, 3)} / 312`;
      ls.forEach((l, i) => MG.clip(l, MG.at(lt, 0.3 + i * 0.08, 0.6 + i * 0.08, E.snap), 'left'));
    }
  });
})();
