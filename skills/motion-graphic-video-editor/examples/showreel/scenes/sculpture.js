/* 05 SCULPTURE INTRODUCTION + 10 HERO SCULPTURE — one procedural sculpture, two scenes.
   05 is the slowest passage of the film: macro details first, then the whole object.
   10 is the most polished moment: chrome + pearl + lime in a white studio, slow orbit,
   minimal type. Each scene has its own WebGL canvas (only the live one renders). */
import { stage3d, studioEnv, studioLights, sculpture, softShadows, rig, orbit } from '../../../assets/mg-three.js';

function build(layer, opt) {
  const cv = canvasIn(layer);
  const st = stage3d(cv, W, H, { background: C.paper, distance: 9, fov: opt.fov || 30, exposure: 0.95 });
  studioEnv(st, { base: '#2E2E32', key: 10, rimA: '#ffffff', rimB: C.lime, rim: 3.5 });
  const L = studioLights(st.scene, { key: 2.4, fill: 0.5, rim: 0, ambient: 0.6 });
  L.key.position.set(-3, 9, 5);
  softShadows(st, L.key, { y: -2.9, opacity: 0.14, radius: 18 });
  const sc = sculpture(Object.assign({ strands: 5, seed: 7, size: 1.75, radius: [0.16, 0.38], breathe: 0.12 }, opt.sculpt || {}));
  st.scene.add(sc.group);
  return { st, sc };
}

/* ---- 05: macro → reveal ---- */
{
  const A = FILM.layer('sculpt-intro'); A.style.background = C.paper;
  const { st, sc } = build(A, { sculpt: { materials: ['chrome', 'pearl', 'glass', 'lime', 'chrome'] } });
  const T0 = B(9), T1 = B(11);
  const la = [label(A, 'STUDY 05 — CONTINUOUS FORM', G.mx, G.my), label(A, '05 / 12', G.col(10).x, G.my), label(A, '', G.mx, H - G.my - 22 * S)];
  FILM.scene({
    id: '05 sculpture', start: T0, end: T1, el: A,
    render(lt, ctx) {
      sc.update(ctx.t);
      sc.group.rotation.y = 0.4 + lt * 0.12; sc.group.rotation.x = 0.25;
      rig(st.camera, lt, [[0, [0.5, 0.4, 2.3], [0.8, 0.3, 0]], [1.6, [0.9, 0.7, 3.4], [0.6, 0.1, 0]], [5.0, [1.2, 1.6, 11.5], [-1.4, 0, 0]]], MG.ease.read);
      st.render();
      la[2].textContent = `FOCAL ${(30).toFixed(1)}MM EQ   DIST ${st.camera.position.length().toFixed(2)}`;
      la.forEach((l, i) => MG.clip(l, MG.at(lt, 1.0 + i * 0.1, 1.3 + i * 0.1, MG.ease.snap), 'left'));
    }
  });
}

/* ---- 10: hero ---- */
{
  const Hh = FILM.layer('hero'); Hh.style.background = C.paper;
  const { st, sc } = build(Hh, { fov: 26, sculpt: { materials: ['chrome', 'pearl', 'lime', 'chrome', 'iridescent'], seed: 7, breathe: 0.16 } });
  const T0 = B(17), T1 = B(20);
  const title = el('div', 'sw-head abs', Hh, 'Continuous form'); title.style.fontSize = 64 * S + 'px'; title.style.left = G.mx + 'px'; title.style.top = G.row(6).y + 'px';
  const la = [label(Hh, '10 / 12', G.col(10).x, G.my), label(Hh, 'CHROME · PEARL · LIME · IRIDESCENT', G.mx, G.row(7).y + 6 * S)];
  let tp;
  MG.blur(T0, T0 + 0.6);   // the fast settle at the cut gets real motion blur
  FILM.scene({
    id: '10 hero', start: T0, end: T1, el: Hh,
    setup() { return document.fonts.ready.then(() => { tp = MG.split(title, 'words'); }); },
    render(lt, ctx) {
      sc.update(ctx.t);
      // arrives with a fast settle (the only quick move), then slows to a near-still orbit
      const settle = MG.spring(lt, { stiffness: 60, damping: 13 });
      sc.group.rotation.y = MG.lerp(-1.6, 0, settle) + lt * 0.07;
      sc.group.rotation.x = 0.2 + 0.05 * Math.sin(lt * 0.4);
      orbit(st.camera, lt, { radius: 12.6, height: MG.lerp(3.2, 1.3, MG.at(lt, 0, 6, MG.ease.inOut)), speed: 0.06, phase: 0.25, target: [-1.5, 0.1, 0] });
      st.render();
      MG.reveal(tp, lt, 2.0, { style: 'mask', each: 0.08, dur: 0.8, ease: MG.ease.out });
      la.forEach((l, i) => MG.clip(l, MG.at(lt, 2.4 + i * 0.1, 2.7 + i * 0.1, MG.ease.snap), 'left'));
    }
  });
}
