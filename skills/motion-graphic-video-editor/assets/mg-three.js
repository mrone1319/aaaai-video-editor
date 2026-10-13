/* mg-three.js — real 3D for code-authored motion graphics (three.js r170).
 *
 *   import * as THREE from './vendor/three.module.min.js';
 *   import { stage3d, extrudeLogo, studioLights, particles } from './mg-three.js';
 *
 * Deterministic: nothing animates by itself — position the camera and objects
 * from `t` inside window.__render, then call `S.render()`. The renderer keeps
 * its drawing buffer so the frame grabber always captures the finished frame.
 * Rendered on the GPU by render_frames.py (ANGLE/Metal on a Mac); with --cpu
 * it falls back to SwiftShader and is much slower.
 */
import * as THREE from './vendor/three.module.min.js';

export { THREE };

/* A canvas-filling renderer + scene + perspective camera.
   transparent: true keeps the page background visible (alpha renders). */
export function stage3d(canvas, W, H, opt = {}) {
  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: true, alpha: !!opt.transparent, preserveDrawingBuffer: true,
    powerPreference: 'high-performance'
  });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = opt.exposure || 1.0;
  if (opt.transparent) renderer.setClearColor(0x000000, 0);
  else renderer.setClearColor(new THREE.Color(opt.background || '#0B0B0F'), 1);
  const scene = new THREE.Scene();
  if (opt.fog) scene.fog = new THREE.Fog(new THREE.Color(opt.fog.color || opt.background || '#0B0B0F'), opt.fog.near, opt.fog.far);
  const camera = new THREE.PerspectiveCamera(opt.fov || 32, W / H, 0.1, 2000);
  camera.position.set(0, 0, opt.distance || 10);
  return { renderer, scene, camera, THREE, render: () => renderer.render(scene, camera) };
}

/* Extrude a logo traced by `logo_tools.py outline` into a solid.
   outline: the JSON; texture: THREE.Texture of the same PNG for the front face
   (keeps the brand's exact colours/gradients); width: world units across.
   Returns a Group centred on the origin, front face toward +Z. */
export function extrudeLogo(outline, opt = {}) {
  const width = opt.width || 6, depth = opt.depth == null ? 0.6 : opt.depth;
  const k = width / outline.w;
  const toV = ([x, y]) => new THREE.Vector2((x - outline.w / 2) * k, (outline.h / 2 - y) * k);
  const shapes = outline.shapes.map(s => {
    const sh = new THREE.Shape(s.outer.map(toV));
    s.holes.forEach(h => sh.holes.push(new THREE.Path(h.map(toV))));
    return sh;
  });
  const bevel = opt.bevel == null ? depth * 0.12 : opt.bevel;
  const geo = new THREE.ExtrudeGeometry(shapes, {
    depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel * 0.8,
    bevelSegments: opt.bevelSegments || 4, curveSegments: 1, steps: 1
  });
  geo.translate(0, 0, -depth / 2);
  // front/back caps: UVs from the shape coordinates → map the original PNG 1:1
  const uv = geo.attributes.uv, pos = geo.attributes.position;
  const hw = outline.w * k / 2, hh = outline.h * k / 2;
  for (let i = 0; i < uv.count; i++) {
    uv.setXY(i, (pos.getX(i) + hw) / (2 * hw), (pos.getY(i) + hh) / (2 * hh));
  }
  uv.needsUpdate = true;
  geo.computeVertexNormals();
  const face = new THREE.MeshStandardMaterial({
    map: opt.texture || null, color: opt.texture ? 0xffffff : (opt.color || '#E9E7E1'),
    roughness: opt.faceRoughness == null ? 0.35 : opt.faceRoughness, metalness: opt.faceMetal || 0.0
  });
  const side = new THREE.MeshStandardMaterial({
    color: opt.sideColor || '#2A2A33', roughness: opt.sideRoughness == null ? 0.28 : opt.sideRoughness,
    metalness: opt.sideMetal == null ? 0.85 : opt.sideMetal
  });
  if (opt.texture) { opt.texture.colorSpace = THREE.SRGBColorSpace; opt.texture.anisotropy = 8; }
  const mesh = new THREE.Mesh(geo, [face, side]);   // ExtrudeGeometry groups: 0 = caps, 1 = sides
  const g = new THREE.Group();
  g.add(mesh);
  g.userData = { mesh, face, side };
  return g;
}

/* Three-point studio light: soft key, cool fill, two coloured rims (pass the
   brand's end colours) that carve the silhouette out of a dark background. */
export function studioLights(scene, opt = {}) {
  const L = {};
  L.amb = new THREE.HemisphereLight('#ffffff', '#202028', opt.ambient == null ? 0.35 : opt.ambient);
  L.key = new THREE.DirectionalLight('#ffffff', opt.key == null ? 2.2 : opt.key);
  L.key.position.set(-4, 5, 8);
  L.fill = new THREE.DirectionalLight('#BFD3FF', opt.fill == null ? 0.6 : opt.fill);
  L.fill.position.set(6, -2, 6);
  L.rimA = new THREE.PointLight(opt.rimA || '#FF6A3D', opt.rim == null ? 60 : opt.rim, 30, 2);
  L.rimA.position.set(-6, 2, -4);
  L.rimB = new THREE.PointLight(opt.rimB || '#5B7CFF', opt.rim == null ? 60 : opt.rim, 30, 2);
  L.rimB.position.set(6, -1, -4);
  Object.values(L).forEach(l => scene.add(l));
  return L;
}

/* Procedural studio environment for reflections: metal with no environment
   renders black. Builds a small room of emissive softboxes (two in the brand
   colours) and prefilters it — no HDR file needed. Call once after stage3d. */
export function studioEnv(st, opt = {}) {
  const env = new THREE.Scene();
  env.background = new THREE.Color(opt.base || '#121216');
  const box = (color, intensity, pos, size) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(intensity), side: THREE.DoubleSide }));
    m.position.set(...pos); m.lookAt(0, 0, 0); env.add(m);
  };
  box('#ffffff', opt.key == null ? 6 : opt.key, [-3, 4, 5], [4, 3]);        // key softbox
  box('#ffffff', 2.5, [0, 6, 0], [6, 6]);                                     // top
  box(opt.rimA || '#FF6A3D', opt.rim == null ? 5 : opt.rim, [-6, 0, -3], [2, 6]);
  box(opt.rimB || '#5B7CFF', opt.rim == null ? 5 : opt.rim, [6, 0, -3], [2, 6]);
  box('#ffffff', 1.2, [0, -5, 3], [8, 2]);                                    // floor bounce
  const pm = new THREE.PMREMGenerator(st.renderer);
  const tex = pm.fromScene(env, opt.blur == null ? 0.03 : opt.blur).texture;
  st.scene.environment = tex;
  st.scene.environmentIntensity = opt.intensity == null ? 1.0 : opt.intensity;
  pm.dispose();
  return tex;
}

/* Seeded particle field (points) in a box — a cheap depth cue as the camera moves.
   Size attenuates with distance; fog fades the far ones. */
export function particles(scene, opt = {}) {
  const n = opt.count || 600, seed = opt.seed || 1;
  let s = seed | 0;
  const r = () => { s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const box = opt.box || [30, 18, 40];
  const p = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    p[i * 3] = (r() - 0.5) * box[0]; p[i * 3 + 1] = (r() - 0.5) * box[1]; p[i * 3 + 2] = -r() * box[2] + 4;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(p, 3));
  const mat = new THREE.PointsMaterial({ color: opt.color || '#F5B83D', size: opt.size || 0.06,
    sizeAttenuation: true, transparent: true, opacity: opt.opacity == null ? 0.8 : opt.opacity, depthWrite: false });
  const pts = new THREE.Points(geo, mat);
  scene.add(pts);
  return pts;
}

/* Load a texture and resolve once it is decoded (pass to MG.ready()). */
export function loadTexture(url) {
  return new Promise((res, rej) => new THREE.TextureLoader().load(url, res, undefined, rej));
}

/* =====================================================================
   Studio sculpture kit: procedural tube sculptures, material presets,
   soft shadows, camera rigs. Everything is a function of t (seekable).
   ===================================================================== */

/* smooth deterministic 1-D noise in [-1, 1] (same family as MG.noise) */
function hash(i, seed) {
  let h = Math.imul((i | 0) ^ 0x9E3779B9, 0x85EBCA6B) ^ Math.imul(seed | 0, 0xC2B2AE35);
  h ^= h >>> 13; h = Math.imul(h, 0x27D4EB2F); h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
export function noise1(x, seed = 0) {
  const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
  return (hash(i, seed) * (1 - u) + hash(i + 1, seed) * u) * 2 - 1;
}

/* Material presets for "photographed in a studio" objects. All need an environment
   (studioEnv) — physical materials reflect the room, they don't glow on their own.
     chrome · pearl · glass · lime · iridescent · ceramic (matte off-white) */
export function material(name, o = {}) {
  const P = (x) => new THREE.MeshPhysicalMaterial(Object.assign(x, o));
  switch (name) {
    case 'chrome': return P({ color: '#E9E9EC', metalness: 1, roughness: 0.07, envMapIntensity: 1.25 });
    case 'pearl': return P({ color: '#F2EEE6', metalness: 0, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.08,
      sheen: 1, sheenColor: new THREE.Color('#ffffff'), sheenRoughness: 0.45,
      iridescence: 0.35, iridescenceIOR: 1.3, iridescenceThicknessRange: [180, 520] });
    case 'glass': return P({ color: '#ffffff', metalness: 0, roughness: 0.04, transmission: 1, thickness: 1.4, ior: 1.46,
      attenuationColor: new THREE.Color('#EAF2FF'), attenuationDistance: 2.5, specularIntensity: 1, envMapIntensity: 1.2 });
    case 'lime': return P({ color: '#D4FF3A', metalness: 0, roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.15 });
    case 'iridescent': return P({ color: '#DCE2EA', metalness: 0.85, roughness: 0.14, iridescence: 1,
      iridescenceIOR: 1.6, iridescenceThicknessRange: [120, 820] });
    case 'ceramic': return P({ color: '#EDEAE3', metalness: 0, roughness: 0.75, clearcoat: 0.2 });
    default: throw new Error('mg-three material: unknown preset ' + name);
  }
}

/* Procedural tube sculpture: intertwined closed spline strands (inflated loops).
   opt: { strands: 5, seed: 7, size: 2.2, materials: ['chrome','pearl','glass','lime','chrome'],
          radius: [0.18, 0.42], knots: 18, breathe: 0.18, segments: 260, radial: 32 }
   Returns { group, strands, update(t) } — call update(t) every frame: knots drift with
   continuous noise and the tube is rebuilt (deterministic, so seeking and motion-blur
   sub-samples agree). Strands follow (p,q) torus-knot paths with seeded offsets, so
   they interlock like a sculpture instead of a random scribble. */
export function sculpture(opt = {}) {
  const n = opt.strands || 5, seed = opt.seed || 7, size = opt.size || 2.2, K = opt.knots || 18;
  const mats = (opt.materials || ['chrome', 'pearl', 'glass', 'lime', 'chrome']).map(m => typeof m === 'string' ? material(m) : m);
  const rr = opt.radius || [0.18, 0.42], seg = opt.segments || 260, rad = opt.radial || 32;
  const PQ = opt.pq || [[2, 3], [3, 2], [2, 5], [3, 4], [1, 3], [2, 3]];
  const group = new THREE.Group();
  const strands = [];
  for (let s = 0; s < n; s++) {
    const [p, q] = PQ[s % PQ.length];
    const R = size * (0.62 + 0.3 * hash(s, seed)), r = size * (0.22 + 0.18 * hash(s + 50, seed));
    const ph = hash(s + 100, seed) * Math.PI * 2;
    const tilt = new THREE.Euler(hash(s + 200, seed) * 1.6 - 0.8, hash(s + 300, seed) * Math.PI, hash(s + 400, seed) * 1.2 - 0.6);
    const base = [];
    for (let k = 0; k < K; k++) {
      const u = (k / K) * Math.PI * 2;
      const v = new THREE.Vector3((R + r * Math.cos(q * u + ph)) * Math.cos(p * u), (R + r * Math.cos(q * u + ph)) * Math.sin(p * u), r * Math.sin(q * u + ph) * 1.4);
      v.applyEuler(tilt);
      base.push(v);
    }
    const radius = rr[0] + (rr[1] - rr[0]) * hash(s + 500, seed);
    const mesh = new THREE.Mesh(new THREE.BufferGeometry(), mats[s % mats.length]);
    mesh.castShadow = true; mesh.receiveShadow = true;
    group.add(mesh);
    strands.push({ base, radius, mesh, s });
  }
  const breathe = opt.breathe == null ? 0.18 : opt.breathe;
  function update(t) {
    for (const st of strands) {
      const pts = st.base.map((v, k) => new THREE.Vector3(
        v.x + breathe * size * noise1(t * 0.35 + k * 0.7, seed + st.s * 3 + 1),
        v.y + breathe * size * noise1(t * 0.31 + k * 0.9, seed + st.s * 3 + 2),
        v.z + breathe * size * noise1(t * 0.27 + k * 1.1, seed + st.s * 3 + 3)));
      const curve = new THREE.CatmullRomCurve3(pts, true, 'centripetal');
      const geo = new THREE.TubeGeometry(curve, seg, st.radius * (1 + 0.08 * Math.sin(t * 0.8 + st.s)), rad, true);
      st.mesh.geometry.dispose();
      st.mesh.geometry = geo;
    }
  }
  update(0);
  return { group, strands, update, dispose() { strands.forEach(s => s.mesh.geometry.dispose()); mats.forEach(m => m.dispose()); } };
}

/* Soft shadows onto an invisible floor (ShadowMaterial): the object sits on something.
   light: a DirectionalLight (e.g. studioLights().key). Returns the floor mesh. */
export function softShadows(st, light, o = {}) {
  st.renderer.shadowMap.enabled = true;
  st.renderer.shadowMap.type = THREE.VSMShadowMap;
  light.castShadow = true;
  light.shadow.mapSize.set(o.mapSize || 2048, o.mapSize || 2048);
  light.shadow.radius = o.radius == null ? 14 : o.radius;
  light.shadow.blurSamples = 24;
  light.shadow.bias = -0.0004;
  const b = o.bounds || 8;
  Object.assign(light.shadow.camera, { left: -b, right: b, top: b, bottom: -b, near: 0.5, far: 40 });
  light.shadow.camera.updateProjectionMatrix();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), new THREE.ShadowMaterial({ opacity: o.opacity == null ? 0.16 : o.opacity }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = o.y == null ? -2.6 : o.y;
  floor.receiveShadow = true;
  st.scene.add(floor);
  return floor;
}

/* Camera rigs (pure functions of t).
   orbit(cam, t, {radius, height, speed (rad/s), phase, target})
   rig(cam, t, keys, ease) — keys: [[time, [x,y,z], [tx,ty,tz]], ...] e.g. macro → wide reveal */
export function orbit(cam, t, o = {}) {
  const a = (o.phase || 0) + t * (o.speed == null ? 0.12 : o.speed), r = o.radius || 9;
  const tg = o.target || [0, 0, 0];
  cam.position.set(tg[0] + Math.sin(a) * r, tg[1] + (o.height == null ? 1.2 : o.height), tg[2] + Math.cos(a) * r);
  cam.lookAt(tg[0], tg[1], tg[2]);
}
export function rig(cam, t, keys, ease) {
  const E = ease || (p => p * p * (3 - 2 * p));
  let i = 1;
  if (t <= keys[0][0]) i = 1; else { while (i < keys.length - 1 && keys[i][0] < t) i++; }
  const [ta, pa, la] = keys[i - 1], [tb, pb, lb] = keys[i];
  const k = E(Math.max(0, Math.min(1, (t - ta) / (tb - ta || 1))));
  cam.position.set(...pa.map((v, j) => v + (pb[j] - v) * k));
  cam.lookAt(...la.map((v, j) => v + (lb[j] - v) * k));
}
