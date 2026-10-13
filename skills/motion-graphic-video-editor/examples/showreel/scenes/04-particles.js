/* 04 PARTICLE STUDY — black field, 7 000 points in curl noise. They organise into a
   word, lime appears in a few of them, a repulsor dissolves the word, then they settle
   into a circle as the scene hands over to the slow sculpture. */
(function () {
  const L = FILM.layer('particles'); L.style.background = C.ink;
  const cv = canvasIn(L);
  const N = 7000;
  const T0 = B(6);
  const word = GEN.textPoints('FIELD', N, W, H, { size: H * 0.46, seed: 3 });
  const ring = GEN.shapePoints('circle', N, W, H, { r: 0.3, seed: 8 });
  // target switches from word → ring: blend both target sets into one moving target
  const target = new Float32Array(N * 2);
  const ps = GEN.particles(cv, {
    W, H, count: N, seed: 11, scale: 380, speed: 70, drift: 0.18, size: 2.1, ink: C.paper, accent: C.lime, accentShare: 0.07,
    target,
    attractors: [{ x: 0.5, y: 0.5, strength: -2.2, radius: 0.32, t0: 4.95, t1: 5.6 }],          // repulsor burst (scene time)
    form: t => MG.at(t, 1.3, 2.6, E.inOut) - MG.at(t, 4.9, 5.4, E.out) + MG.at(t, 6.0, 7.4, E.inOut),
    accentOn: t => MG.at(t, 3.0, 3.4) - MG.at(t, 6.6, 7.2)
  });
  const ls = [label(L, 'STUDY 04 — CURL FIELD', G.mx, G.my, C.paper), label(L, 'N = 7 000   σ = 380   SEED 11', G.mx, G.my + 22 * S, C.paper),
    label(L, '', G.mx, H - G.my - 22 * S, C.paper), label(L, '04 / 12', G.col(10).x, G.my, C.paper)];
  FILM.scene({
    id: '04 particles', start: T0, end: B(9), el: L,
    render(lt) {
      const toRing = MG.at(lt, 5.6, 6.2);
      for (let i = 0; i < N * 2; i++) target[i] = word[i] + (ring[i] - word[i]) * toRing;
      ps.render(lt);
      ls[2].textContent = `FRAME ${pad(lt * FPS, 5)}   FORM ${(MG.clamp(MG.at(lt, 1.3, 2.6, E.inOut) - MG.at(lt, 4.9, 5.4, E.out) + MG.at(lt, 6.0, 7.4, E.inOut))).toFixed(2)}`;
      ls.forEach((l, i) => MG.clip(l, MG.at(lt, 0.2 + i * 0.08, 0.5 + i * 0.08, E.snap), 'left'));
    }
  });
})();
