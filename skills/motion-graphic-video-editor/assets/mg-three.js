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
