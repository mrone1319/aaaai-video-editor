// aaaai-editor Studio 界面。
// 原则：界面只改剪辑表（storyboard.json）与字幕轨（work/captions.json），存档一律经过服务端的存取口（带版本检查）；
// 画面上的字卡只是「近似样子」，停下来换成引擎排的真样子 PNG；动态与成片一律由同一个引擎渲染。
// 时间：字卡、配方、推近用成片时间；字幕用原片时间（剪辑点改了也不会错位）。
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
const plain = (s) => String(s ?? "").replace(/\*\*/g, "").replace(/\n/g, " ");
const r2 = (x) => Math.round(x * 100) / 100;
const r3 = (x) => Math.round(x * 1000) / 1000;
const clone = (o) => JSON.parse(JSON.stringify(o));
function fmt(t) { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = t - m * 60; return String(m).padStart(2, "0") + ":" + s.toFixed(2).padStart(5, "0"); }
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} },
  del(k) { try { localStorage.removeItem(k); } catch (_) {} },
};

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  let j = {};
  try { j = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}

// ------------------------------------------------------------------ 状态
let SCHEMA = null;
let P = null;           // 项目：id name fps W H styles source_ok proxy …
let S = null;           // 正在编辑的内容：{ sb, cap }；cap 为 null 时显示自动字幕（第一次改字时才建字幕轨）
let AUTO = [];          // 自动切好的字幕片段（还没有字幕轨时）
let V = { sb: "", cap: "" };          // 服务端版本
let SAVED = { sb: "", cap: "" };      // 上次存档的内容（JSON 字串）
let RO = false;         // 只读（原片不见了）
let sel = null;         // { k: "ov"|"rc"|"cap"|"cut", i }
let undoStack = [], redoStack = [];
let pps = 18, tOut = 0, playing = false;
let PEAKS = null, ISSUES = [], CHECKED = false, CONFLICT = false;
const PNG = new Map();  // 字卡真样子缓存：key → { url, box:[x,y,w,h]（相对画面） }
let OPT = null, FACES = null, FACES_BUSY = false;
const SHOW = { safe: false, face: false, plat: "" };   // 画面叠层：安全区、脸、平台遮挡
const TOOLS = { tidy: null, hooks: null, busy: "" };    // 逐字稿页的口误清理／开头钩子结果
let pngBusy = false, idleTimer = null;

// ------------------------------------------------------------------ 时间轴换算（与引擎 timeline.py 相同）
function TL() {
  const cuts = (S.sb.cuts || []).map((c) => [+c[0], +c[1]]);
  const off = []; let acc = 0;
  for (const [a, b] of cuts) { off.push(acc); acc += b - a; }
  return {
    cuts, off, dur: acc,
    toSrc(t) {
      for (let i = 0; i < cuts.length; i++) { const L = cuts[i][1] - cuts[i][0]; if (t < off[i] + L || i === cuts.length - 1) return { src: cuts[i][0] + Math.min(L, Math.max(0, t - off[i])), i }; }
      return { src: 0, i: 0 };
    },
    clip(a, b) {
      const out = [];
      cuts.forEach(([ca, cb], i) => { const lo = Math.max(a, ca), hi = Math.min(b, cb); if (hi > lo) out.push([off[i] + lo - ca, off[i] + hi - ca]); });
      return out;
    },
    toOut(s) { for (let i = 0; i < cuts.length; i++) if (s >= cuts[i][0] - 1e-6 && s <= cuts[i][1] + 1e-6) return off[i] + s - cuts[i][0]; return null; },
  };
}
let T = null;
const pieces = () => (S.cap ? S.cap.pieces : AUTO);
// 一句字幕在成片里的位置（同一段原片可能出现两次，例如开头预告：取第一次、相连的段落合在一起）
function capSegs(pc) { return T.clip(+pc.s[0], +pc.s[1]).filter((x) => x[1] - x[0] >= 0.15); }
function capOut(pc) {
  const h = capSegs(pc); if (!h.length) return null;
  const r = [h[0][0], h[0][1]];
  for (const x of h.slice(1)) { if (x[0] - r[1] < 0.02) r[1] = x[1]; else break; }
  return r;
}

// ------------------------------------------------------------------ 首页
async function showHome() {
  stopAll();
  $("app").hidden = true; $("home").hidden = false;
  document.title = "aaaai-editor Studio";
  const j = await api("api/projects");
  $("homeSub").textContent = j.projects.length ? "项目文件夹：" + (j.projects_dir || "（未设定）") + "　·　共 " + j.projects.length + " 个项目" : "还没有项目。先在对话里让 Claude 剪一支片，这里就会出现。";
  $("grid").innerHTML = j.projects.map((p) => {
    const d = new Date(p.mtime * 1000);
    const day = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    return '<button class="pcard" data-id="' + p.id + '"><div class="th"' + (p.thumb ? ' style="background-image:url(\'' + esc(p.thumb) + '\')"' : "") + ">" + (p.thumb ? "" : "没有封面") + "</div>" +
      '<div class="meta"><div class="nm">' + esc(p.name) + '</div><div class="row">' + day + "</div>" +
      '<div class="row">' + (p.source_ok ? "" : '<span class="chip bad">原片不见了·只读</span>') + (p.final ? '<span class="chip ok">已出片</span>' : "") + '<span class="chip">' + p.overlays + " 张字卡</span></div></div></button>";
  }).join("");
}
$("grid").addEventListener("click", (e) => { const b = e.target.closest(".pcard"); if (b) location.hash = "p=" + b.dataset.id; });
$("back").onclick = () => { flushSave().finally(() => { location.hash = ""; }); };

// ------------------------------------------------------------------ 打开项目
async function openProject(id) {
  stopAll();
  $("home").hidden = true; $("app").hidden = false;
  if (!SCHEMA) SCHEMA = await api("api/schema");
  let j;
  try { j = await api("api/open?p=" + encodeURIComponent(id)); } catch (e) { toast("打不开这个项目：" + e.message, true); location.hash = ""; return; }
  load(j, true);
  const draft = store.get("aaaai-studio-draft-" + id);
  if (draft && draft.sbv === V.sb && draft.capv === V.cap && (JSON.stringify(draft.sb) !== SAVED.sb || JSON.stringify(draft.cap) !== (SAVED.cap || "null"))) {
    toast("上次有修改还没存进剪辑表（可能是界面被关掉了）。", false, [["恢复", () => { const before = snap(); S.sb = draft.sb; S.cap = draft.cap; commit(before); }], ["不要", () => store.del("aaaai-studio-draft-" + id)]], 15000);
  } else if (draft) store.del("aaaai-studio-draft-" + id);
  if (P.source_ok) {
    api("api/peaks?p=" + encodeURIComponent(id)).then((pk) => { PEAKS = pk; renderTimeline(); }).catch(() => {});
    if (!P.proxy) prepareProxy(); else setVideo(P.proxy);
  }
  pollTimer = setInterval(pollVersion, 2000);
  api("api/options?p=" + encodeURIComponent(id)).then((o) => { OPT = o; renderSettings(); }).catch(() => {});
  if (!store.get("aaaai-studio-tour-1")) tour(0);
}

function load(j, first) {
  const keepSel = sel, keepT = tOut;
  P = { id: j.id, name: j.name, fps: j.fps, W: j.W, H: j.H, styles: j.styles, source_ok: j.source_ok, proxy: j.proxy, final: j.final };
  S = { sb: j.storyboard, cap: j.captions };
  AUTO = j.captions_auto || [];
  V = { sb: j.sb_version, cap: j.cap_version };
  SAVED = { sb: JSON.stringify(S.sb), cap: S.cap ? JSON.stringify(S.cap) : "" };
  RO = !j.source_ok;
  CONFLICT = false;
  T = TL();
  if (first) { FACES = null; TOOLS.tidy = null; TOOLS.hooks = null; OPT = null; }
  if (first) { undoStack = []; redoStack = []; sel = null; tOut = 0; ISSUES = []; CHECKED = false; $("chkN").hidden = true; PNG.clear(); }
  else { sel = keepSel && findSel(keepSel) ? keepSel : null; tOut = Math.min(keepT, Math.max(0, T.dur - 0.01)); }
  document.title = P.name + " · Studio";
  $("projName").textContent = "　" + P.name;
  $("styleSel").innerHTML = Object.keys(P.styles).map((k) => '<option value="' + esc(k) + '">' + esc(k) + "</option>").join("");
  $("styleSel").value = S.sb.style || "";
  $("app").classList.toggle("ro-mode", RO);
  $("roNote").hidden = !RO;
  $("roNote").innerHTML = RO ? '<span class="ro">原片不见了：只能看、不能改（把原片放回 storyboard.json 的 source 指向的位置后重新打开）</span>' : "";
  ["undo", "redo", "renderRange", "export", "styleSel", "addCardBtn", "addFxBtn", "delBtn"].forEach((x) => { $(x).disabled = RO; });
  updUndo(); setSave(); fitStage(); renderAll();
}

function stopAll() {
  clearInterval(pollTimer); pollTimer = null;
  playing = false; $("video").pause();
  $("play").textContent = "▶ 播放";
}

// ------------------------------------------------------------------ 代理影片（只做一次）
function setVideo(url) { const v = $("video"); v.src = url; v.addEventListener("loadeddata", () => { seek(tOut); $("wait").hidden = true; }, { once: true }); }
async function prepareProxy() {
  const w = $("wait"); w.hidden = false;
  w.innerHTML = "<div>第一次打开：在准备播放用的影片（低清、只做一次）…</div><div class=\"bar\"><i></i></div><div class=\"hint\">长片要一两分钟；可以先在右边改文字。</div>";
  try {
    const r = await api("api/render", { p: P.id, kind: "proxy" });
    if (r.busy) { w.innerHTML = "<div>" + esc(r.msg) + "</div>"; return; }
    const pid = P.id;
    const done = await waitJob(r.job, false);
    if (P.id !== pid) return;
    if (done.status === "done") { P.proxy = done.result; setVideo(done.result); } else w.innerHTML = "<div>准备影片失败：" + esc(done.stage) + "（⋯ → 诊断报告）</div>";
  } catch (e) { w.innerHTML = "<div>准备影片失败：" + esc(e.message) + "</div>"; }
}

// ------------------------------------------------------------------ 复原／存档／同步
const snap = () => JSON.stringify({ sb: S.sb, cap: S.cap });
function commit(before) {
  if (RO) return;
  if (before === snap()) return;
  undoStack.push(before); if (undoStack.length > 200) undoStack.shift();
  redoStack = [];
  changed();
}
function changed() {
  T = TL(); updUndo(); renderAll();
  store.set("aaaai-studio-draft-" + P.id, { sbv: V.sb, capv: V.cap, sb: S.sb, cap: S.cap, ts: Date.now() });
  setSave("dirty"); clearTimeout(saveTimer); saveTimer = setTimeout(save, 700);
}
function restore(json) { const o = JSON.parse(json); S.sb = o.sb; S.cap = o.cap; if (sel && !findSel(sel)) sel = null; changed(); }
function undo() { if (RO || !undoStack.length) return; redoStack.push(snap()); restore(undoStack.pop()); }
function redo() { if (RO || !redoStack.length) return; undoStack.push(snap()); restore(redoStack.pop()); }
$("undo").onclick = undo; $("redo").onclick = redo;
function updUndo() { $("undo").disabled = RO || !undoStack.length; $("redo").disabled = RO || !redoStack.length; }

let saveTimer = null, saving = null, pollTimer = null;
const dirty = () => S && (JSON.stringify(S.sb) !== SAVED.sb || (S.cap ? JSON.stringify(S.cap) : "") !== SAVED.cap);
function setSave(st) {
  const el = $("save");
  if (RO) { el.textContent = "只读"; el.className = "save bad"; return; }
  if (CONFLICT) { el.textContent = "没存：剪辑表在别处被改过"; el.className = "save bad"; return; }
  if (st === "dirty" || dirty()) { el.textContent = "存档中…"; el.className = "save"; return; }
  if (st === "err") { el.textContent = "存档失败，稍后重试"; el.className = "save bad"; return; }
  el.textContent = "已存进剪辑表"; el.className = "save ok";
}
async function save() {
  if (RO || CONFLICT || !dirty()) { setSave(); return; }
  if (saving) { await saving; return save(); }
  const sbj = JSON.stringify(S.sb), capj = S.cap ? JSON.stringify(S.cap) : "";
  const body = { p: P.id };
  if (sbj !== SAVED.sb) { body.storyboard = S.sb; body.sb_expect = V.sb; }
  if (capj !== SAVED.cap && S.cap) { body.captions = S.cap; body.cap_expect = V.cap; }
  saving = (async () => {
    try {
      const r = await api("api/save", body);
      if (r.sb_version) { V.sb = r.sb_version; SAVED.sb = sbj; }
      if (r.cap_version) { V.cap = r.cap_version; SAVED.cap = capj; }
      if (r.conflict) { conflict(r.fresh); return; }
      if (!dirty()) store.del("aaaai-studio-draft-" + P.id);
      setSave();
    } catch (e) { setSave("err"); clearTimeout(saveTimer); saveTimer = setTimeout(save, 3000); }
  })();
  await saving; saving = null;
}
async function flushSave() { clearTimeout(saveTimer); if (dirty()) await save(); if (saving) await saving; }

async function pollVersion() {
  if (!P || document.hidden || saving || CONFLICT) return;
  let v;
  try { v = await api("api/version?p=" + encodeURIComponent(P.id)); } catch (_) { return; }
  if (v.sb_version === V.sb && v.cap_version === V.cap) return;
  if (saving) return;
  const fresh = await api("api/open?p=" + encodeURIComponent(P.id));
  if (dirty()) { conflict(fresh); return; }
  const before = snap();
  load(fresh, false);
  if (before !== snap()) { undoStack.push(before); updUndo(); }
  PNG.clear();
  toast("剪辑表在别处（多半是对话里的 Claude）改过了，界面已同步。要退回按「复原」。");
}
function conflict(fresh) {
  CONFLICT = true; setSave();
  const mine = snap();
  modal('<h2>剪辑表在别处被改过了</h2><p class="hint">你在这里的修改还没存进去，而剪辑表或字幕轨刚被别的地方（多半是对话里的 Claude）改过。为了不互相覆盖，你的修改先<b>没有</b>写进去。</p>' +
    '<p class="hint">选「载入最新版本」后，你刚才的修改仍在复原纪录里：按一次「复原」就能拿回来，再存档时会以它为准。</p>' +
    '<div class="acts"><button class="btn" data-a="later">先不处理</button><button class="btn primary" data-a="load">载入最新版本</button></div>', (a) => {
    if (a === "load") { load(fresh, false); undoStack.push(mine); updUndo(); PNG.clear(); toast("已载入最新版本；按「复原」可拿回你刚才的修改。"); }
  });
}
window.addEventListener("beforeunload", (e) => { if (dirty()) { save(); e.preventDefault(); e.returnValue = ""; } });

// ------------------------------------------------------------------ 预览画面
const video = $("video"), stage = $("stage"), layer = $("layer");
function fitStage() {
  if (!P) return;
  const wrap = $("stageWrap").getBoundingClientRect();
  const aw = wrap.width - 20, ah = wrap.height - 20;
  const k = Math.min(aw / P.W, ah / P.H);
  stage.style.width = Math.max(60, Math.floor(P.W * k)) + "px";
  stage.style.height = Math.max(100, Math.floor(P.H * k)) + "px";
}
window.addEventListener("resize", () => { fitStage(); renderTimeline(); });
function accent() { const st = P.styles[S.sb.style] || P.styles.mrone || {}; return st.accent || "#FFC933"; }

function visibleCards() {
  const out = [];
  (S.sb.overlays || []).forEach((o, i) => { if (Array.isArray(o.t) && tOut >= o.t[0] && tOut < o.t[1]) out.push({ k: "ov", i, o }); });
  (S.sb.recipes || []).forEach((o, i) => { if (Array.isArray(o.t) && tOut >= o.t[0] && tOut < o.t[1]) out.push({ k: "rc", i, o }); });
  return out;
}
function boxCss(b) { return "left:" + b[0] * 100 + "%;top:" + b[1] * 100 + "%;width:" + b[2] * 100 + "%;height:" + b[3] * 100 + "%"; }
function renderStage() {
  if (!S) return;
  stage.style.setProperty("--style-accent", accent());
  const vis = visibleCards();
  const showTrue = !playing && !tdrag;
  let h = "", t = "", hits = "", top = false, anyTrue = false, anyApprox = false;
  for (const v of vis) {
    const o = v.o, isSel = sel && sel.k === v.k && sel.i === v.i;
    const pg = showTrue && v.k === "ov" ? PNG.get(pngKey(o)) : null;
    if (pg) {
      t += '<img alt="" data-i="' + v.i + '" src="' + esc(pg.url) + '">'; anyTrue = true;
      if (pg.box) hits += '<div class="hit" data-k="ov" data-i="' + v.i + '" style="' + boxCss(pg.box) + '"></div>';
    } else anyApprox = true;
    const xy = o.xy && v.k === "ov" ? ' style="left:' + o.xy[0] * 100 + "%;top:" + o.xy[1] * 100 + '%;right:auto;bottom:auto;transform:translateX(-50%);max-width:88%"' : "";
    h += '<div class="' + cardClass(v) + (isSel ? " sel" : "") + (pg ? " hid" : "") + '" data-k="' + v.k + '" data-i="' + v.i + '"' + xy + ">" + cardHTML(v) + "</div>";
    if (v.k === "ov" && !["lower_third", "avatar", "stamp", "image", "clip", "broll", "cutout", "confetti", "glow"].includes(o.type) && !(o.pos || "").startsWith("bottom") && !o.xy) top = true;
  }
  // 字幕（原片时间）
  const src = T.toSrc(tOut).src;
  const pcs = pieces();
  const ci = pcs.findIndex((pc) => src >= pc.s[0] && src < pc.s[1]);
  if (ci >= 0 && (S.sb.captions || {}).enabled !== false) {
    const pc = pcs[ci], mv = (S.sb.captions || {}).margin_v ?? 0.30;
    h += '<div class="cap' + (sel && sel.k === "cap" && sel.i === ci ? " sel" : "") + '" data-k="cap" data-i="' + ci + '" style="bottom:' + (mv * 100) + '%"><div class="zh">' + md(hl(pc)) + "</div>" + (pc.en ? '<div class="en">' + md(pc.en) + "</div>" : "") + "</div>";
  }
  layer.innerHTML = h + hits;
  $("truelook").innerHTML = t;
  $("scrim").classList.toggle("on", top);
  // 推近（近似）：画面放大
  const z = (S.sb.zooms || []).find((x) => Array.isArray(x.t) && tOut >= x.t[0] && tOut < x.t[1]);
  const an = (z && z.anchor) || [0.5, 0.42];
  video.style.transformOrigin = an[0] * 100 + "% " + an[1] * 100 + "%";
  video.style.transform = z ? "scale(" + (+z.to || 1.12) + ")" : "";
  const pending = vis.some((v) => v.k === "ov" && SCHEMA.true_look.includes(v.o.type) && !PNG.has(pngKey(v.o)));
  const b = $("badge");
  b.textContent = anyTrue && !anyApprox ? "引擎真样子（字卡）" : !vis.length ? "近似预览" : playing ? "近似预览 · 停下来换成真样子" : pending ? "近似预览 · 正在换成真样子…" : "近似预览（这种卡要「渲染这一段」）";
  b.classList.toggle("true", anyTrue && !anyApprox);
  renderSelBox(); renderGuides();
  scheduleTrueLook();
}
// 选中的字卡：画选取框（拖框＝移动，拉右下角＝放大缩小）
function renderSelBox() {
  const el = $("selLayer");
  if (!sel || sel.k !== "ov" || playing || cdrag) { if (!cdrag) el.innerHTML = ""; return; }
  const o = findSel(), pg = o && PNG.get(pngKey(o));
  if (!o || !pg || !pg.box || !(tOut >= o.t[0] && tOut < o.t[1])) { el.innerHTML = ""; return; }
  el.innerHTML = '<div class="selbox" id="selbox" style="' + boxCss(pg.box) + '"><span class="lbl">' + (RO ? "只读" : "拖动＝移位置 · 拉角＝大小") + "</span>" + (RO ? "" : '<i class="hd" title="拉动放大缩小"></i>') + "</div>";
}
// 画面叠层：安全区、脸的位置、平台按钮遮挡（大概位置）
const PLAT = {
  douyin: [["顶栏", 0, 0, 1, 0.07], ["点赞、评论、分享", 0.84, 0.42, 0.98, 0.84], ["账号与文案", 0.03, 0.80, 0.78, 0.95]],
  reels: [["顶栏", 0, 0, 1, 0.06], ["点赞、评论、分享", 0.86, 0.50, 0.98, 0.88], ["账号与文案", 0.03, 0.82, 0.80, 0.95]],
  shorts: [["顶栏", 0, 0, 1, 0.07], ["点赞、评论、分享", 0.85, 0.45, 0.98, 0.85], ["频道与标题", 0.03, 0.80, 0.80, 0.93]],
  xhs: [["顶栏", 0, 0, 1, 0.08], ["点赞、收藏、评论", 0.86, 0.55, 0.98, 0.85], ["账号与标题", 0.03, 0.82, 0.82, 0.96]],
};
function renderGuides() {
  let h = "";
  if (SHOW.safe && OPT) {
    const sf = OPT.safe, mv = (S.sb.captions || {}).margin_v ?? 0.30;
    h += '<div class="safe" style="left:' + sf.side * 100 + "%;right:" + sf.side * 100 + "%;top:" + sf.top * 100 + "%;bottom:" + sf.bottom * 100 + '%"></div>';
    h += '<span class="tag" style="left:' + sf.side * 100 + "%;top:" + sf.top * 100 + '%">字卡安全区</span>';
    h += '<div class="capline" style="top:' + (1 - mv) * 100 + '%"></div><span class="tag" style="right:4px;top:' + (1 - mv) * 100 + '%">字幕底边</span>';
  }
  if (SHOW.face && FACES) {
    const f = FACES.faces.reduce((best, x) => (Math.abs(x[0] - tOut) < Math.abs(best[0] - tOut) ? x : best), FACES.faces[0] || [0, null]);
    if (f && f[1] && Math.abs(f[0] - tOut) <= FACES.step) {
      const [y0, y1] = f[1];
      h += '<div class="face" style="top:' + y0 * 100 + "%;height:" + (y1 - y0) * 100 + '%"></div><div class="eye" style="top:' + (y0 + 0.3 * (y1 - y0)) * 100 + '%"></div><span class="tag" style="left:4px;top:' + y0 * 100 + '%">脸（虚线＝眼睛，字卡别压到）</span>';
    } else if (FACES) h += '<span class="tag" style="left:4px;top:50%">这里没有侦测到脸</span>';
  }
  if (SHOW.plat && PLAT[SHOW.plat]) {
    for (const [lb, x0, y0, x1, y1] of PLAT[SHOW.plat]) h += '<div class="plat" style="left:' + x0 * 100 + "%;top:" + y0 * 100 + "%;width:" + (x1 - x0) * 100 + "%;height:" + (y1 - y0) * 100 + '%"></div><span class="tag" style="left:' + (x0 * 100 + 1) + "%;top:" + (y0 * 100 + 0.5) + '%">' + lb + "</span>";
    h += '<span class="tag" style="left:4px;bottom:28px">平台遮挡是大概位置，各版本会变</span>';
  }
  $("guides").innerHTML = h;
}
function hl(pc) { let t = pc.text || ""; for (const w of pc.hl || []) if (w && !t.includes("**" + w)) t = t.split(w).join("**" + w + "**"); return t; }
function cardClass(v) {
  const o = v.o;
  if (v.k === "rc") return "card recipe pos-top";
  const pos = o.pos || { lower_third: "bottom_left", avatar: "bottom_left", stamp: "top_left" }[o.type] || "top";
  return "card pos-" + pos + (o.type === "lower_third" || o.type === "avatar" ? " lower" : "") + (SCHEMA.true_look.includes(o.type) ? "" : " other");
}
function cardHTML(v) {
  const o = v.o;
  if (v.k === "rc") {
    const main = o.text || o.title || o.value || o.question || "";
    return '<span class="tag">配方：' + esc(o.use) + "</span>" + (o.kicker ? '<div class="kicker">' + md(o.kicker) + "</div>" : "") + (main !== "" ? '<div class="title">' + md(main) + "</div>" : "");
  }
  if (o.type === "lower_third" || o.type === "avatar") return '<div class="vbar"></div><div><div class="name">' + md(o.name) + '</div><div class="role">' + md(o.role) + "</div></div>";
  let h = "";
  if (!SCHEMA.true_look.includes(o.type)) h += '<span class="tag">' + esc((SCHEMA.cards[o.type] || {}).name || o.type) + "</span>";
  else h += '<div class="bar"></div>';
  if (o.kicker) h += '<div class="kicker">' + md(o.kicker) + "</div>";
  const unit = (x) => (x ? "<span>" + md(x) + "</span>" : "");
  if (o.type === "stat") h += '<div class="num">' + md((o.prefix || "") + (o.value ?? "")) + unit((o.unit || "") + (o.suffix || "")) + "</div>";
  else if (o.type === "gauge") h += '<div class="num">' + Math.round((o.of ? o.value / o.of : o.value || 0) * 100) + unit("%") + "</div>";
  else if (o.type === "rating") h += '<div class="num">' + md(o.value) + unit("/ " + (o.of || 5)) + "</div>";
  else if (o.type === "cta") h += '<div class="title">' + md(o.question) + "</div>" + (o.keyword ? '<div class="sub">「' + md(o.keyword) + "」</div>" : "");
  else if (o.text || o.title) h += '<div class="title"' + (o.title && !o.text ? ' style="font-size:6.4cqw"' : "") + ">" + md(o.text || o.title) + "</div>";
  if (o.name && o.type !== "lower_third") h += '<div class="sub">' + md(o.name) + "</div>";
  const items = Array.isArray(o.items) ? o.items : Array.isArray(o.steps) ? o.steps : null;
  if (items) h += '<div class="items">' + items.slice(0, 6).map((x, k) => "<div>" + String(k + 1).padStart(2, "0") + "　" + md(typeof x === "string" ? x : x.label || x.text || x.big || x.top || "") + "</div>").join("") + "</div>";
  if (o.sub) h += '<div class="sub">' + md(o.sub) + "</div>";
  if (o.label) h += '<div class="label">' + md(o.label) + "</div>";
  if (o.by) h += '<div class="label">— ' + md(o.by) + "</div>";
  return h;
}
stage.addEventListener("click", (e) => {
  if (e.target.closest("#selLayer") || cdragJustEnded) return;
  const el = e.target.closest("[data-k]");
  if (!el) { select(null); return; }
  select({ k: el.dataset.k, i: +el.dataset.i });
  if (el.dataset.k === "cap") showPane("insp");
});

// 字卡真样子：停下来 0.5 秒、已存档后，一张张向引擎要透明 PNG（有缓存）
function pngKey(o) { return JSON.stringify([o, S.sb.style || "", S.sb.brand || null]); }
function scheduleTrueLook() {
  clearTimeout(idleTimer);
  if (playing || cdrag || tdrag || !P || !P.source_ok) return;
  idleTimer = setTimeout(fetchTrueLook, 500);
}
async function fetchTrueLook() {
  if (pngBusy || playing || dirty()) { if (dirty()) scheduleTrueLook(); return; }
  const need = visibleCards().find((v) => v.k === "ov" && SCHEMA.true_look.includes(v.o.type) && !PNG.has(pngKey(v.o)));
  if (!need) return;
  pngBusy = true;
  const key = pngKey(need.o), pid = P.id;
  try {
    const r = await api("api/card", { p: P.id, overlay: need.o, height: Math.min(1280, Math.max(640, Math.round(stage.clientHeight * (window.devicePixelRatio || 1)))) });
    if (P && P.id === pid) PNG.set(key, { url: r.url, box: r.box });
  } catch (e) { if (P && P.id === pid) PNG.set(key, null); }
  pngBusy = false;
  renderStage();
}

// ------------------------------------------------------------------ 播放
function seek(t) {
  tOut = Math.max(0, Math.min(Math.max(0, T.dur - 0.01), t));
  const m = T.toSrc(tOut);
  if (video.src) { try { video.currentTime = m.src; } catch (_) {} }
  tick();
}
function tick() {
  $("tc").innerHTML = fmt(tOut) + " <em>/ " + fmt(T.dur) + "</em>";
  const ph = $("ph"); if (ph) ph.style.left = tOut * pps + "px";
  renderStage(); markTranscript();
}
function togglePlay() {
  if (!video.src) { toast(P && P.source_ok ? "播放用的影片还在准备中。" : "原片不见了，没办法播放。"); return; }
  playing = !playing; $("play").textContent = playing ? "❚❚ 暂停" : "▶ 播放";
  if (playing) { if (tOut >= T.dur - 0.05) seek(0); video.play().catch(() => {}); requestAnimationFrame(loop); }
  else { video.pause(); renderStage(); }
}
function loop() {
  if (!playing) return;
  // 按「现在播到第几刀」换算时间：同一段原片出现两次（开头预告）也不会跳回去
  const i = T.toSrc(tOut).i, c = T.cuts[i];
  if (c && video.currentTime >= c[1] - 0.02) {   // 一刀播完跳到下一刀
    if (i + 1 < T.cuts.length) { video.currentTime = T.cuts[i + 1][0]; tOut = T.off[i + 1] + 0.001; }
    else { togglePlay(); return; }
  } else if (c && video.currentTime >= c[0] - 0.1) tOut = T.off[i] + Math.max(0, video.currentTime - c[0]);
  tick();
  const sc = $("tlScroll"), x = tOut * pps;
  if (x > sc.scrollLeft + sc.clientWidth - 40 || x < sc.scrollLeft) sc.scrollLeft = x - 80;
  requestAnimationFrame(loop);
}
$("play").onclick = togglePlay;
video.addEventListener("pause", () => { if (playing && !video.ended && document.hidden) togglePlay(); });   // 切到别的分页时浏览器会自己暂停
$("mute").onclick = () => { video.muted = !video.muted; $("mute").textContent = video.muted ? "🔇" : "🔊"; };

// ------------------------------------------------------------------ 时间轴
const TRACKS = [{ key: "card", label: "字卡", h: 34 }, { key: "fx", label: "特效", h: 34 }, { key: "cap", label: "字幕", h: 34 }, { key: "cut", label: "画面", h: 34 }, { key: "voice", label: "人声", h: 34 }, { key: "music", label: "配乐", h: 30 }];
function cardItems() {
  const it = [];
  (S.sb.overlays || []).forEach((o, i) => { if (Array.isArray(o.t)) it.push({ k: "ov", i, t0: +o.t[0], t1: +o.t[1], o }); });
  (S.sb.recipes || []).forEach((o, i) => { if (Array.isArray(o.t)) it.push({ k: "rc", i, t0: +o.t[0], t1: +o.t[1], o }); });
  return it;
}
function lanes(items) {
  const ends = [], map = new Map();
  [...items].sort((a, b) => a.t0 - b.t0).forEach((it) => {
    let k = ends.findIndex((e) => e <= it.t0 + 1e-6); if (k < 0) { k = ends.length; ends.push(0); }
    ends[k] = it.t1; map.set(it.k + it.i, k);
  });
  return { map, n: Math.max(1, ends.length) };
}
function cardName(it) {
  const o = it.o;
  if (it.k === "rc") return "配方 " + o.use + "　" + plain(o.text || o.title || o.kicker || "");
  return ((SCHEMA.cards[o.type] || {}).name || o.type) + "　" + plain(o.kicker || o.text || o.name || o.title || o.question || o.value || "");
}
function renderTimeline() {
  if (!S) return;
  const D = T.dur, W = Math.max(D * pps + 80, $("tlScroll").clientWidth);
  const items = cardItems(), ln = lanes(items);
  TRACKS[0].h = 8 + 30 * ln.n;
  $("labels").innerHTML = "<div></div>" + TRACKS.map((t) => '<div style="--h:' + t.h + 'px">' + t.label + "</div>").join("");
  const inner = $("tlInner"); inner.style.width = W + "px";
  let h = '<div class="ruler" id="ruler">';
  const step = pps >= 60 ? 1 : pps >= 24 ? 2 : pps >= 12 ? 5 : 10;
  for (let s = 0; s <= D; s += step) h += '<span style="left:' + s * pps + 'px">' + fmt(s).slice(0, 5) + "</span>";
  for (const x of ISSUES) if (x.t != null && x.level !== "ok") h += '<i class="mark' + (x.level === "note" ? " note" : "") + '" data-t="' + x.t + '" title="' + esc(x.msg) + '" style="left:' + x.t * pps + 'px"></i>';
  h += "</div>";
  const badT = ISSUES.filter((x) => x.level === "problem" && x.t != null).map((x) => x.t);
  const isBad = (a, b) => badT.some((t) => t >= a - 0.05 && t <= b + 0.05);
  for (const t of TRACKS) {
    h += '<div class="track" data-track="' + t.key + '" style="--h:' + t.h + 'px">';
    if (t.key === "card") for (const it of items) h += block(it.k, it.i, it.t0, it.t1, cardName(it), 4 + 30 * ln.map.get(it.k + it.i), isBad(it.t0, it.t1));
    if (t.key === "fx") {
      (S.sb.zooms || []).forEach((z, i) => { if (Array.isArray(z.t)) h += block("zm", i, +z.t[0], +z.t[1], (z.style === "punch" ? "瞬切推近 ×" : "推近 ×") + (z.to || 1.12)); });
      (S.sb.sfx || []).forEach((x, i) => { h += block("sx", i, +x.t, +x.t + 0.01, "音效 " + (x.sound || "pop")); });
    }
    if (t.key === "cap") pieces().forEach((pc, i) => { for (const o of capSegs(pc)) h += block("cap", i, o[0], o[1], plain(hl(pc)), undefined, isBad(o[0], o[1])); });
    if (t.key === "cut") T.cuts.forEach((c, i) => { h += block("cut", i, T.off[i], T.off[i] + c[1] - c[0], "原片 " + fmt(c[0]).slice(0, 5) + "–" + fmt(c[1]).slice(0, 5)); });
    if (t.key === "voice") h += '<div class="tl-block aud" style="left:0;width:' + D * pps + 'px"><canvas class="wave" id="wave" width="' + Math.max(1, Math.round(D * pps)) + '" height="26"></canvas></div>';
    if (t.key === "music") { const mu = S.sb.music; h += mu ? '<div class="tl-block aud music" style="left:0;width:' + D * pps + 'px;height:22px;line-height:22px">配乐 ' + esc(String(mu.file || "").replace(/^bgm:/, "")) + "　" + (mu.db ?? -18) + " dB" + (mu.duck ? " · 人声出现时自动闪避" : "") + "</div>" : ""; }
    h += "</div>";
  }
  const rg = rangeOf();
  if (rg) h += '<div class="rangebox" style="left:' + rg[0] * pps + "px;width:" + (rg[1] - rg[0]) * pps + 'px"></div>';
  h += '<div class="playhead" id="ph" style="left:' + tOut * pps + 'px"></div>';
  inner.innerHTML = h;
  drawWave();
}
function block(k, i, a, b, text, top, bad) {
  const isSel = sel && sel.k === k && sel.i === i;
  return '<div class="tl-block ' + k + (isSel ? " sel" : "") + (bad ? " bad" : "") + '" tabindex="0" data-k="' + k + '" data-i="' + i + '" style="left:' + a * pps + "px;width:" + Math.max(6, (b - a) * pps) + "px" + (top !== undefined ? ";top:" + top + "px" : "") + '" title="' + esc(plain(text)) + '">' + esc(plain(text)) + "</div>";
}
function drawWave() {
  const cv = $("wave"); if (!cv) return;
  const g = cv.getContext("2d"); g.clearRect(0, 0, cv.width, cv.height); g.fillStyle = "rgba(255,255,255,.8)";
  if (!PEAKS) return;
  for (let x = 0; x < cv.width; x += 2) {
    const src = T.toSrc(x / pps).src, k = Math.floor(src / PEAKS.hop);
    const v = PEAKS.v[k] || 0, amp = Math.max(1, v * 24);
    g.fillRect(x, 13 - amp / 2, 1.5, amp);
  }
}
function findSel(s) {
  s = s || sel; if (!s) return null;
  if (s.k === "ov") return (S.sb.overlays || [])[s.i];
  if (s.k === "rc") return (S.sb.recipes || [])[s.i];
  if (s.k === "cap") return pieces()[s.i];
  if (s.k === "cut") return T.cuts[s.i];
  if (s.k === "zm") return (S.sb.zooms || [])[s.i];
  if (s.k === "sx") return (S.sb.sfx || [])[s.i];
  return null;
}
function rangeOf() {
  const o = findSel(); if (!o) return null;
  if (sel.k === "ov" || sel.k === "rc" || sel.k === "zm") return [+o.t[0], +o.t[1]];
  if (sel.k === "sx") return [Math.max(0, +o.t - 0.5), Math.min(T.dur, +o.t + 1)];
  if (sel.k === "cap") return capOut(o);
  if (sel.k === "cut") return [T.off[sel.i], T.off[sel.i] + o[1] - o[0]];
  return null;
}

// 拖拽：拖中间＝移动，拖两端＝改长短；靠近播放头或其他块的边会吸附
let tdrag = null;
$("tlInner").addEventListener("pointerdown", (e) => {
  const mk = e.target.closest(".mark"); if (mk) { seek(+mk.dataset.t); return; }
  const b = e.target.closest(".tl-block:not(.aud)");
  const rect = $("tlInner").getBoundingClientRect();
  if (!b) { seek((e.clientX - rect.left) / pps); tdrag = { mode: "scrub" }; $("tlInner").setPointerCapture(e.pointerId); return; }
  const k = b.dataset.k, i = +b.dataset.i;
  const br = b.getBoundingClientRect(), off = e.clientX - br.left;   // 先量：选取会重画时间轴
  const mode = k === "sx" ? "move" : off < 7 ? "l" : off > br.width - 7 ? "r" : "move";
  select({ k, i });
  if (RO || k === "cut") { seek((e.clientX - rect.left) / pps); return; }
  if (k === "cap" && !ensureCapTrack()) return;
  const o = findSel();
  const a0 = k === "cap" ? +o.s[0] : k === "sx" ? +o.t : +o.t[0], b0 = k === "cap" ? +o.s[1] : k === "sx" ? +o.t : +o.t[1];
  tdrag = { k, o, mode, sx: e.clientX, before: tdragBefore || snap(), a0, b0, moved: false };
  tdragBefore = null;
  $("tlInner").setPointerCapture(e.pointerId);
  e.preventDefault();
});
let tdragBefore = null;
$("tlInner").addEventListener("pointermove", (e) => {
  if (!tdrag) return;
  const rect = $("tlInner").getBoundingClientRect();
  if (tdrag.mode === "scrub") { seek((e.clientX - rect.left) / pps); return; }
  const d = (e.clientX - tdrag.sx) / pps, o = tdrag.o;
  if (Math.abs(e.clientX - tdrag.sx) < 3 && !tdrag.moved) return;
  tdrag.moved = true;
  if (tdrag.k === "cap") {
    // 字幕在原片时间里移动／改长短；不能和前后句重叠
    const pcs = pieces(), idx = pcs.indexOf(o);
    const lo = idx > 0 ? +pcs[idx - 1].s[1] : 0, hi = idx + 1 < pcs.length ? +pcs[idx + 1].s[0] : 1e9;
    let a = tdrag.a0, b = tdrag.b0;
    if (tdrag.mode === "l") a = Math.min(b - 0.2, Math.max(lo, a + d));
    else if (tdrag.mode === "r") b = Math.max(a + 0.2, Math.min(hi, b + d));
    else { const L = b - a; a = Math.min(hi - L, Math.max(lo, a + d)); b = a + L; }
    o.s = [r2(a), r2(b)];
  } else if (tdrag.k === "sx") {
    o.t = r2(Math.max(0, Math.min(T.dur - 0.05, tdrag.a0 + d)));
  } else {
    const pts = [tOut, ...cardItems().filter((x) => x.o !== o).flatMap((x) => [x.t0, x.t1]), ...T.off];
    const snapv = (v) => { for (const p of pts) if (Math.abs(p - v) * pps < 6) return p; return v; };
    const L = tdrag.b0 - tdrag.a0;
    let a = +o.t[0], b = +o.t[1];
    if (tdrag.mode === "move") { a = Math.min(Math.max(0, T.dur - L), Math.max(0, snapv(tdrag.a0 + d))); b = a + L; }
    if (tdrag.mode === "l") a = Math.min(b - 0.3, Math.max(0, snapv(tdrag.a0 + d)));
    if (tdrag.mode === "r") b = Math.max(a + 0.3, Math.min(T.dur, snapv(tdrag.b0 + d)));
    o.t = [r2(a), r2(b)];
  }
  renderTimeline(); renderStage(); renderInspector();
});
$("tlInner").addEventListener("pointerup", () => {
  if (tdrag && tdrag.before && tdrag.moved) commit(tdrag.before);
  tdrag = null; scheduleTrueLook();
});
$("tlInner").addEventListener("dblclick", (e) => { const b = e.target.closest(".tl-block:not(.aud)"); if (b) { const r = rangeOf(); if (r) seek(r[0] + 0.01); } });
$("zoom").oninput = (e) => { const keep = tOut * pps - $("tlScroll").scrollLeft; pps = +e.target.value; renderTimeline(); $("tlScroll").scrollLeft = tOut * pps - keep; };
let cdrag = null;  // 画面上的拖拽（移位置／放大缩小）

// 第一次改字幕：从自动字幕建一份字幕轨（之后都改它）
function ensureCapTrack() {
  if (RO) return false;
  if (S.cap) return true;
  tdragBefore = snap();
  S.cap = { version: 1, note: "s 是原片时间（改剪辑点不会错位）。可改 text 修错字、填 en 出双语、hl 列出要高亮的词，或在 text 里写 **关键词**。删掉本文件即回到自动字幕。", pieces: clone(AUTO).map((p) => ({ s: [r3(p.s[0]), r3(p.s[1])], text: p.text, en: p.en || "", hl: p.hl || [] })), aligned: false };
  return true;
}

// ------------------------------------------------------------------ 右栏：属性／逐字稿／体检
function showPane(name) {
  for (const b of document.querySelectorAll(".tabs button")) b.setAttribute("aria-selected", String(b.dataset.pane === name));
  for (const n of ["insp", "tr", "chk", "ast", "set"]) $("pane-" + n).hidden = n !== name;
  if (name === "tr") renderTranscript();
  if (name === "ast") renderAssets();
  if (name === "set") renderSettings();
  if (name === "chk") renderChecks(false);
}
document.querySelector(".tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) showPane(b.dataset.pane); });

function select(s) { sel = s; renderInspector(); renderTimeline(); renderStage(); }

function inp(id, label, kind, val, opts) {
  const dis = RO ? " disabled" : "";
  let h = '<div class="field"><label for="' + id + '">' + esc(label) + "</label>";
  if (kind === "textarea" || kind === "lines" || kind === "json") {
    const v = kind === "lines" ? (Array.isArray(val) ? val.join("\n") : val ?? "") : kind === "json" ? (val === undefined ? "" : JSON.stringify(val, null, 1)) : val ?? "";
    h += '<textarea id="' + id + '" data-kind="' + kind + '"' + (kind === "json" ? ' class="code" spellcheck="false"' : "") + dis + ">" + esc(v) + "</textarea>";
  } else if (kind === "select" || kind === "bool") {
    const o = kind === "bool" ? [["", "默认"], ["true", "是"], ["false", "否"]] : opts;
    const cur = val === undefined || val === null ? "" : String(val);
    if (kind === "select" && cur && !o.some((x) => x[0] === cur)) o.push([cur, cur]);
    h += '<select id="' + id + '" data-kind="' + kind + '"' + dis + ">" + o.map((x) => '<option value="' + esc(x[0]) + '"' + (x[0] === cur ? " selected" : "") + ">" + esc(x[1]) + "</option>").join("") + "</select>";
  } else {
    h += '<input id="' + id + '" data-kind="' + kind + '" ' + (kind === "num" ? 'type="number" step="any"' : 'type="text"') + ' value="' + esc(val ?? "") + '"' + dis + ">";
  }
  return h + "</div>";
}
function readVal(el) {
  const k = el.dataset.kind, v = el.value;
  if (k === "num") return v.trim() === "" ? undefined : (isNaN(parseFloat(v)) ? null : parseFloat(v));
  if (k === "bool") return v === "" ? undefined : v === "true";
  if (k === "lines") { const a = v.split("\n").map((x) => x.trim()).filter(Boolean); return a.length ? a : undefined; }
  if (k === "json") { if (!v.trim()) return undefined; try { return JSON.parse(v); } catch (_) { return null; } }
  if (k === "select") return v === "" ? undefined : v;
  return v === "" ? undefined : v;
}

function renderInspector() {
  const el = $("pane-insp"); if (!S) return;
  const o = findSel();
  if (!o) {
    el.innerHTML = '<h3>还没选东西</h3><p class="empty">点画面上的<b>字卡</b>或<b>字幕</b>，或点下面时间轴上的任何一块，就能在这里改。</p>' +
      '<div class="hint"><b>操作</b><br>时间轴：拖中间＝移动，拖两端＝改长短（会吸附到播放头和其他块的边）<br>「逐字稿」：删一句＝把那句从片子里剪掉，后面的字卡自动跟着往前<br>「体检」：对时、字幕太长、字卡压到脸、响度，红点可点<br>改完自动存进剪辑表；对话里的 Claude 改了，这里会自动同步</div>' +
      '<p class="hint">按 <span class="kbd">?</span> 看全部快捷键。</p>';
    return;
  }
  let h = "";
  const fields = [];
  if (sel.k === "ov") {
    const sc = SCHEMA.cards[o.type] || { name: o.type, fields: [] };
    h += '<h3><span class="tag" style="background:var(--card-t);color:#1a1406">' + esc(sc.name) + '</span>字卡 #' + (sel.i + 1) + "</h3>";
    h += '<div class="row2">' + inp("f_t0", "出现（成片秒）", "num", o.t[0]) + inp("f_t1", "消失（成片秒）", "num", o.t[1]) + "</div>";
    for (const f of sc.fields) { h += inp("f_" + f.key, f.label, f.kind, o[f.key], f.options); fields.push(f.key); }
    h += "<fieldset><legend>出场</legend>";
    for (const f of SCHEMA.common) { h += inp("f_" + f.key, f.label, f.kind, o[f.key], f.options); fields.push(f.key); }
    h += "</fieldset>";
    h += '<div class="field"><label>位置</label><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="hint">' +
      (o.xy ? "水平中心 " + Math.round(o.xy[0] * 100) + "%、上缘 " + Math.round(o.xy[1] * 100) + "%（手动放的，不会自动避脸）" : "风格默认位置（会自动避脸）") + "</span>" +
      (o.xy && !RO ? '<button class="btn sm" id="resetXY">还原默认位置</button>' : "") + "</div></div>";
    h += otherFields(o, fields.concat(["type", "t", "xy"]));
    h += '<p class="hint">' + (SCHEMA.true_look.includes(o.type) ? "停下来后，画面上的这张卡会换成引擎排的<b>真样子</b>；要看动态按「渲染这一段」。" : "这种卡只有「渲染这一段」才看得到真样子。") + "</p>";
  } else if (sel.k === "rc") {
    const rc = SCHEMA.recipes[o.use] || { desc: "", required: [], optional: [] };
    h += '<h3><span class="tag" style="background:var(--rc-t)">配方</span>' + esc(o.use) + "</h3><p class=\"hint\">" + esc(rc.desc) + "（一个配方会展开成几张卡＋推近，真样子要「渲染这一段」）</p>";
    h += '<div class="row2">' + inp("f_t0", "开始（成片秒）", "num", o.t[0]) + inp("f_t1", "结束（成片秒）", "num", o.t[1]) + "</div>";
    for (const k of rc.required.concat(rc.optional)) {
      if (k === "t") continue;
      const v = o[k], kind = v !== undefined && typeof v === "object" ? "json" : typeof v === "number" ? "num" : (k === "text" || k === "title" ? "textarea" : "text");
      h += inp("f_" + k, k + (rc.required.includes(k) ? "（必填）" : ""), kind, v); fields.push(k);
    }
    h += otherFields(o, fields.concat(["use", "t"]));
  } else if (sel.k === "zm") {
    h += '<h3><span class="tag" style="background:#7A55C9">特效</span>推近</h3>';
    h += '<div class="row2">' + inp("f_t0", "开始（成片秒）", "num", o.t[0]) + inp("f_t1", "结束（成片秒）", "num", o.t[1]) + "</div>";
    h += '<div class="row2">' + inp("f_to", "放大到（1.05–1.4）", "num", o.to ?? 1.12) + inp("f_style", "方式", "select", o.style, [["", "平滑推近"], ["punch", "瞬切推近（冲击）"]]) + "</div>";
    h += inp("f_anchor", "放大中心 [水平, 垂直]（0–1，默认 [0.5, 0.42]）", "json", o.anchor);
    h += '<p class="hint">画面上是近似效果；看真正的推近按「渲染这一段」。</p>';
  } else if (sel.k === "sx") {
    h += '<h3><span class="tag" style="background:#D9773A">特效</span>音效</h3>';
    h += '<div class="row2">' + inp("f_tpt", "在成片第几秒", "num", o.t) + inp("f_sound", "声音", "select", o.sound || "pop", (OPT ? OPT.sounds : ["pop"]).map((x) => [x, (SCHEMA.common.find((c) => c.key === "sfx") || { options: [] }).options.find((y) => y[0] === x)?.[1] || x])) + "</div>";
    h += inp("f_db", "音量（dB，0＝默认，负数＝小声）", "num", o.db);
  } else if (sel.k === "cap") {
    const out = capOut(o);
    h += '<h3><span class="tag" style="background:var(--cap-t)">字幕</span>第 ' + (sel.i + 1) + " 句" + (out ? '　<span class="hint">成片 ' + fmt(out[0]) + "</span>" : '　<span class="chip bad">这句已剪掉</span>') + "</h3>";
    h += inp("f_text", "中文（**关键词**＝高亮）", "textarea", o.text) + inp("f_en", "英文（填了就是双语）", "textarea", o.en);
    h += inp("f_hl", "要高亮的词（一行一个）", "lines", o.hl);
    h += '<div class="row2">' + inp("f_s0", "开始（原片秒）", "num", o.s[0]) + inp("f_s1", "结束（原片秒）", "num", o.s[1]) + "</div>";
    h += '<p class="hint">字幕跟着<b>原片时间</b>走：剪辑点改了也不会错位。' + (S.cap ? "" : "目前是自动字幕，第一次修改时会建一份字幕轨（work/captions.json）。") + "</p>";
    if (!RO) h += '<button class="btn danger sm" id="capCut">把这句从片子里剪掉</button>';
  } else if (sel.k === "cut") {
    h += '<h3><span class="tag" style="background:var(--cut-t)">画面</span>第 ' + (sel.i + 1) + " 段</h3>";
    h += '<p class="hint">原片 ' + fmt(o[0]) + " – " + fmt(o[1]) + "（" + (o[1] - o[0]).toFixed(2) + " 秒），成片从 " + fmt(T.off[sel.i]) + " 开始。</p>";
    h += '<p class="hint">要剪掉讲错、重讲的句子，到<b>逐字稿</b>里删那一句；字卡会自动跟着往前。拖剪辑点留到之后的版本。</p>';
  }
  if (!RO && ["ov", "rc", "zm", "sx"].includes(sel.k)) h += '<button class="btn danger sm" id="delSel">删除' + ({ ov: "这张字卡", rc: "这个配方", zm: "这个推近", sx: "这个音效" }[sel.k]) + "</button>";
  el.innerHTML = h;
  bindInspector(o);
  const ds = $("delSel"); if (ds) ds.onclick = deleteSel;
  const rx = $("resetXY"); if (rx) rx.onclick = () => { const before = snap(); delete o.xy; commit(before); };
}
function otherFields(o, known) {
  const rest = {};
  for (const k of Object.keys(o)) if (!known.includes(k)) rest[k] = o[k];
  return Object.keys(rest).length ? inp("f__rest", "其他栏位（JSON，照样能改）", "json", rest) : "";
}
function bindInspector(o) {
  const el = $("pane-insp");
  const cc = $("capCut"); if (cc) cc.onclick = () => cutPiece(sel.i);
  el.querySelectorAll("[data-kind]").forEach((x) => {
    let before = null;
    x.addEventListener("focus", () => { before = snap(); });
    const apply = (final) => {
      const key = x.id.slice(2);
      let v = readVal(x);
      const bad = v === null || (x.dataset.kind === "json" && v === null);
      x.classList.toggle("err", bad);
      if (bad) return;
      if (sel.k === "cap" && !S.cap) { const b = before; ensureCapTrack(); tdragBefore = null; before = b; o = pieces()[sel.i]; }
      if (key === "t0" || key === "t1") {
        if (v === undefined) return;
        const t = [...o.t]; t[key === "t0" ? 0 : 1] = r3(Math.max(0, Math.min(T.dur, v)));
        if (t[1] - t[0] < 0.1) { if (final) x.classList.add("err"); return; }
        o.t = t;
      } else if (key === "tpt") {
        if (v === undefined) return;
        o.t = r3(Math.max(0, Math.min(T.dur, v)));
      } else if (key === "s0" || key === "s1") {
        if (v === undefined) return;
        const s = [...o.s]; s[key === "s0" ? 0 : 1] = r3(Math.max(0, v));
        if (s[1] - s[0] < 0.1) return;
        o.s = s;
      } else if (key === "_rest") {
        if (x.dataset.kind === "json" && (v === undefined || typeof v !== "object" || Array.isArray(v))) { x.classList.add("err"); return; }
        if (!final) return;
        const keep = new Set(Array.from(el.querySelectorAll("[data-kind]")).map((y) => y.id.slice(2)).concat(sel.k === "rc" ? ["use", "t"] : ["type", "t"]));
        for (const k of Object.keys(o)) if (!keep.has(k)) delete o[k];
        Object.assign(o, v);
      } else {
        if (x.dataset.kind === "json" && !final) return;
        if (v === undefined) delete o[key]; else o[key] = v;
      }
      if (final) { T = TL(); commit(before); before = snap(); }
      else { renderTimeline(); renderStage(); }
    };
    x.addEventListener("input", () => apply(false));
    x.addEventListener("change", () => apply(true));
  });
}

// 逐字稿：一句一行；删一句＝把那句（连同到下一句前的停顿）从片子里剪掉，后面的字卡跟着往前
function pieceRange(i) {
  const pcs = pieces(), pc = pcs[i], nx = pcs[i + 1];
  const a = +pc.s[0];
  let b = +pc.s[1] + 0.12;
  if (nx && +nx.s[0] - +pc.s[1] < 1.2) b = +nx.s[0];
  return [r3(a), r3(Math.max(+pc.s[1], b))];
}
function removedFor(pc) {
  const mid = (+pc.s[0] + +pc.s[1]) / 2;
  return ((S.sb.studio || {}).removed || []).find((r) => mid >= r[0] && mid <= r[1]);
}
async function recut(body, msg) {
  if (RO) return;
  const before = snap();
  try {
    const r = await api("api/recut", Object.assign({ storyboard: clone(S.sb) }, body));
    S.sb = r.storyboard; T = TL(); commit(before);
    toast(msg(r), false, [["复原", undo]]);
  } catch (e) { toast("没剪成：" + e.message, true); }
}
function cutPiece(i) {
  const pc = pieces()[i]; if (!pc || !capOut(pc)) return;
  recut({ remove: [pieceRange(i)] }, (r) => "剪掉「" + plain(pc.text).slice(0, 18) + "」，少了 " + r.saved.toFixed(1) + " 秒；后面的字卡已跟着往前。");
}
function restorePiece(i) {
  const pc = pieces()[i], rg = removedFor(pc) || [r3(+pc.s[0]), r3(+pc.s[1])];
  recut({ restore: [rg] }, (r) => "「" + plain(pc.text).slice(0, 18) + "」放回来了（多了 " + (-r.saved).toFixed(1) + " 秒）。");
}
function renderTranscript() {
  const el = $("pane-tr"); if (!S || el.hidden) return;
  const pcs = pieces();
  if (!pcs.length) { el.innerHTML = '<p class="empty">这个项目没有转录文字。</p>'; return; }
  el.innerHTML = toolsHTML() + '<p class="hint">点一句跳过去；<b>✕</b> 把那句从片子里剪掉（连同后面的停顿），被剪的句子划线，可以<b>还原</b>。' + (RO ? "" : "要改错字，点句子后在「属性」改。") + "</p>" +
    pcs.map((pc, i) => {
      const o = capOut(pc);
      return '<div class="tr-line' + (o ? "" : " gone") + '" data-i="' + i + '"><span class="tm" data-seek="' + i + '">' + (o ? fmt(o[0]).slice(0, 5) : "已剪") + '</span><span class="tx" data-seek="' + i + '">' + md(hl(pc)) + "</span>" +
        (RO ? "<span></span>" : o ? '<button class="btn sm x" data-cut="' + i + '" title="把这句剪掉" aria-label="剪掉这句">✕</button>' : '<button class="btn sm x" data-restore="' + i + '">还原</button>') + "</div>";
    }).join("");
  markTranscript();
}
$("pane-tr").addEventListener("click", (e) => {
  const tb = e.target.closest("[data-tool]"); if (tb) { runTool(tb.dataset.tool, tb.dataset.arg); return; }
  const c = e.target.closest("[data-cut]"); if (c) { cutPiece(+c.dataset.cut); return; }
  const r = e.target.closest("[data-restore]"); if (r) { restorePiece(+r.dataset.restore); return; }
  const s = e.target.closest("[data-seek]");
  if (s) { const i = +s.dataset.seek, o = capOut(pieces()[i]); if (o) seek(o[0] + 0.02); sel = { k: "cap", i }; renderTimeline(); renderStage(); renderInspector(); }
});
function toolsHTML() {
  if (RO) return "";
  let h = '<div class="tool"><div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm" data-tool="tidy">找口误／重讲</button><button class="btn sm" data-tool="hooks">推荐开头钩子</button></div>';
  if (TOOLS.busy) h += '<p class="hint">' + esc(TOOLS.busy) + "</p>";
  if (TOOLS.tidy) {
    h += TOOLS.tidy.length ? "<b>找到 " + TOOLS.tidy.length + " 处（勾选要剪的）</b>" + TOOLS.tidy.map((x) => '<label class="it"><input type="checkbox" class="tidyck" value="' + x.id + '" checked><span>' + (x.t != null ? '<span class="hint">' + fmt(x.t).slice(0, 5) + "</span> " : "") + "【" + esc(x.kind) + "】" + esc(x.text || "") + ' <span class="hint">' + x.len + " 秒</span></span></label>").join("") +
      '<div style="display:flex;gap:6px"><button class="btn primary sm" data-tool="tidyApply">剪掉勾选的</button><button class="btn sm" data-tool="close">收起</button></div>' : '<p class="hint">没有找到口误或重讲。</p>';
  }
  if (TOOLS.hooks) {
    h += S.sb.hook ? '<p class="hint">这支片已经有开头钩子（原片 ' + fmt(S.sb.hook.source[0]) + "–" + fmt(S.sb.hook.source[1]) + "）。要换先按复原或在对话里说。</p>" : "";
    h += TOOLS.hooks.length ? "<b>适合放开头的句子</b>" + TOOLS.hooks.map((x, k) => '<div class="it"><span class="hint">' + x.score + "</span><span>" + md(x.text) + '<br><button class="btn sm" data-tool="hookApply" data-arg="' + k + '"' + (S.sb.hook ? " disabled" : "") + '>放到开头当预告</button></span></div>').join("") +
      '<button class="btn sm" data-tool="close">收起</button>' : '<p class="hint">没有找到合适的句子。</p>';
  }
  return h + "</div>";
}
async function runTool(name, arg) {
  if (RO) return;
  if (name === "close") { TOOLS.tidy = TOOLS.hooks = null; renderTranscript(); return; }
  if (name === "tidy" || name === "hooks") {
    await flushSave(); if (CONFLICT) return;
    TOOLS.tidy = TOOLS.hooks = null;
    TOOLS.busy = name === "tidy" ? "在听整支片找口误与重讲…（第一次要半分钟到一分钟）" : "在挑适合放开头的句子…";
    renderTranscript();
    try {
      const r = await api(name === "tidy" ? "api/tidy" : "api/hook", { p: P.id });
      if (name === "tidy") TOOLS.tidy = r.items; else TOOLS.hooks = r.items;
    } catch (e) { toast("没做成：" + e.message, true); }
    TOOLS.busy = ""; renderTranscript(); return;
  }
  if (name === "tidyApply") {
    const ids = [...document.querySelectorAll(".tidyck:checked")].map((x) => +x.value);
    if (!ids.length) { toast("没有勾选。"); return; }
    await engineEdit(() => api("api/tidy", { p: P.id, apply: ids }), (r) => "剪掉 " + r.removed + " 处，省下 " + r.saved + " 秒。");
    TOOLS.tidy = null; renderTranscript(); return;
  }
  if (name === "hookApply") {
    const c = TOOLS.hooks[+arg];
    await engineEdit(() => api("api/hook", { p: P.id, a: c.s[0], b: c.s[1], mode: "teaser" }),
      (r) => "开头放了 " + r.len + " 秒的预告" + (r.tail_missing ? "（⚠️ 听起来句尾可能被切到，渲染这一段听听看）" : "") + "。");
    TOOLS.hooks = null; renderTranscript();
  }
}
// 引擎命令直接改剪辑表（口误清理、开头钩子）：先存档，做完载入新版本，旧的放进复原纪录
async function engineEdit(call, msg) {
  await flushSave(); if (CONFLICT) return;
  const before = snap();
  try {
    const r = await call();
    const fresh = await api("api/open?p=" + encodeURIComponent(P.id));
    load(fresh, false); undoStack.push(before); updUndo(); PNG.clear();
    toast(msg(r), false, [["复原", undo]], 10000);
  } catch (e) { toast("没做成：" + e.message, true); }
}

// ------------------------------------------------------------------ 素材面板
async function renderAssets() {
  const el = $("pane-ast"); if (el.hidden || !P) return;
  let list = [];
  try { list = (await api("api/assets?p=" + encodeURIComponent(P.id))).assets; } catch (_) {}
  const o = sel && sel.k === "ov" ? findSel() : null;
  const sc = o ? (SCHEMA.cards[o.type] || { fields: [] }) : null;
  const canFile = sc && sc.fields.some((f) => f.key === "file"), canIcon = sc && sc.fields.some((f) => f.key === "icon");
  el.innerHTML = (RO ? "" : '<div class="drop" id="drop">把图片、影片、声音拖到这里，或 <button class="btn sm" id="pickFile">选文件</button><input type="file" id="fileIn" multiple hidden accept="image/*,video/*,audio/*"><div class="hint">放进项目的 assets/ 文件夹；同名不会覆盖</div><div class="hint" id="upMsg"></div></div>') +
    (list.length ? list.map((a, k) => {
      const th = a.kind === "image" ? '<div class="th" style="background-image:url(&quot;' + esc(a.url) + '&quot;)"></div>' : a.kind === "video" ? '<div class="th"><video muted preload="metadata" src="' + esc(a.url) + '#t=0.5"></video></div>' : '<div class="th">♪</div>';
      let acts = "";
      if (!RO) {
        if (a.kind === "image" && !a.icon) acts += '<button class="btn sm" data-ast="image" data-k="' + k + '">放进画面</button>';
        if (a.kind === "video") acts += '<button class="btn sm" data-ast="broll" data-k="' + k + '">当 B-roll</button>';
        if (a.kind === "audio") acts += '<button class="btn sm" data-ast="music" data-k="' + k + '">当配乐</button>';
        if (canFile && a.kind !== "audio") acts += '<button class="btn sm" data-ast="file" data-k="' + k + '">填进选中的卡</button>';
        if (canIcon && a.icon) acts += '<button class="btn sm" data-ast="icon" data-k="' + k + '">当图标</button>';
      }
      return '<div class="asset">' + th + '<div><div class="nm">' + esc(a.path) + ' <span class="hint">' + (a.size / 1048576).toFixed(1) + " MB</span></div><div class=\"acts\">" + acts + "</div></div></div>";
    }).join("") : '<p class="empty">这个项目还没有素材。</p>');
  el._list = list;
  const fi = $("fileIn"); if (!fi) return;
  $("pickFile").onclick = () => fi.click();
  fi.onchange = () => uploadFiles([...fi.files]);
  const dz = $("drop");
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("on"); };
  dz.ondragleave = () => dz.classList.remove("on");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("on"); uploadFiles([...e.dataTransfer.files]); };
}
function uploadFiles(files) {
  const msg = $("upMsg");
  const next = () => {
    const f = files.shift(); if (!f) { renderAssets(); return; }
    const x = new XMLHttpRequest();
    x.open("POST", "api/upload?p=" + encodeURIComponent(P.id) + "&name=" + encodeURIComponent(f.name));
    x.upload.onprogress = (e) => { if (msg && e.lengthComputable) msg.textContent = "上传 " + f.name + "：" + Math.round(e.loaded / e.total * 100) + "%"; };
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (_) {} if (x.status !== 200) toast("「" + f.name + "」没传上：" + (j.error || x.status), true); else toast("已放进 " + j.path); next(); };
    x.onerror = () => { toast("上传失败：" + f.name, true); next(); };
    x.send(f);
  };
  next();
}
$("pane-ast").addEventListener("click", (e) => {
  const b = e.target.closest("[data-ast]"); if (!b || RO) return;
  const a = $("pane-ast")._list[+b.dataset.k], act = b.dataset.ast, before = snap();
  if (act === "image") { (S.sb.overlays = S.sb.overlays || []).push({ type: "image", t: startAt(3), file: a.path, width: 0.6, pos: "center" }); sel = { k: "ov", i: S.sb.overlays.length - 1 }; }
  else if (act === "broll") { (S.sb.overlays = S.sb.overlays || []).push({ type: "broll", t: startAt(3), file: a.path }); sel = { k: "ov", i: S.sb.overlays.length - 1 }; }
  else if (act === "music") { S.sb.music = Object.assign({ db: -18, duck: true }, S.sb.music || {}, { file: a.path }); }
  else if (act === "file") { findSel().file = a.path; }
  else if (act === "icon") { findSel().icon = a.name.replace(/\.[^.]+$/, ""); }
  commit(before);
  toast({ image: "图片放进画面了（右边可改大小与位置）。", broll: "B-roll 放好了：时间轴上拖它对准要盖的句子。", music: "配乐换成 " + a.name + "。", file: "已填进选中的卡。", icon: "图标换好了。" }[act], false, [["复原", undo]]);
  if (act === "image" || act === "broll") showPane("insp");
});

// ------------------------------------------------------------------ 设定：字幕样式、声音、出片
function getPath(o, path) { return path.split(".").reduce((x, k) => (x == null ? undefined : x[k]), o); }
function setPath(o, path, v) {
  const ks = path.split("."); let cur = o;
  for (const k of ks.slice(0, -1)) { if (cur[k] == null || typeof cur[k] !== "object") cur[k] = {}; cur = cur[k]; }
  if (v === undefined) delete cur[ks[ks.length - 1]]; else cur[ks[ks.length - 1]] = v;
}
function sfield(path, label, kind, opts, hint) {
  let v = getPath(S.sb, path);
  if (kind === "jsel") v = v === undefined ? "" : JSON.stringify(v);
  const id = "s_" + path.replace(/\./g, "_");
  return inp(id, label, kind === "jsel" ? "select" : kind, v, opts).replace("<select ", '<select data-path="' + path + '"' + (kind === "jsel" ? ' data-json="1"' : "") + " ").replace("<input ", '<input data-path="' + path + '" ').replace("<textarea ", '<textarea data-path="' + path + '" ') + (hint ? '<p class="hint" style="margin:-4px 0 0">' + hint + "</p>" : "");
}
function renderSettings() {
  const el = $("pane-set"); if (!S || el.hidden) return;
  if (document.activeElement && el.contains(document.activeElement)) return;   // 正在打字时不重画
  const capOpts = [["", "跟随风格（" + ((OPT && OPT.caption_style_now) || "默认") + "）"]].concat(((OPT && OPT.caption_styles) || []).map((x) => [x, x]));
  const bgm = [["", "不要配乐"]].concat(((OPT && OPT.bgm) || []).map(([n, d]) => ["bgm:" + n, n + (d ? "　" + d : "")]));
  const mf = getPath(S.sb, "music.file");
  if (mf && !bgm.some((x) => x[0] === mf)) bgm.push([mf, mf]);
  el.innerHTML = '<fieldset><legend>字幕</legend>' +
    sfield("captions.enabled", "显示字幕", "jsel", [["", "显示"], ["false", "不显示"]]) +
    sfield("captions.style", "字幕样式", "select", capOpts) +
    '<div class="row2">' + sfield("captions.margin_v", "离底部（0.1–0.5）", "num") + sfield("captions.size_scale", "字号倍率", "num") + "</div>" +
    '<p class="hint" style="margin:-4px 0 0">离底部默认 0.30（画面约 70% 处）；字号倍率默认 1。</p>' +
    sfield("captions.anim", "出字动效", "select", [["", "轻轻淡入（默认）"], ["none", "不要"]]) +
    sfield("captions.avoid_face", "字幕避开脸", "jsel", [["", "开（默认）"], ["false", "关"]]) + "</fieldset>" +
    '<fieldset><legend>字卡</legend>' + sfield("avoid_face", "字卡自动避开脸", "jsel", [["", "开（默认）"], ["false", "关"]], "手动拖过位置的字卡不会被自动挪。") + "</fieldset>" +
    '<fieldset><legend>声音</legend>' + sfield("music.file", "配乐", "select", bgm) +
    '<div class="row2">' + sfield("music.db", "配乐音量（dB）", "num") + sfield("music.duck", "人声出现时压低", "jsel", [["true", "压低"], ["false", "不压"], ["", "默认"]]) + "</div>" +
    sfield("denoise", "降噪", "jsel", [["", "标准（默认）"], ['"strong"', "加强"], ["false", "关（原声）"]]) +
    sfield("loudness", "成片响度（LUFS）", "num", null, "默认 −14（各平台通用）。") + "</fieldset>" +
    '<fieldset><legend>出片</legend>' + sfield("ending.fade", "结尾淡出（秒）", "num") +
    sfield("output.encoder", "编码", "select", [["", "软件编码（画质最好）"], ["hw", "硬件编码（快几倍、文件稍大）"]]) +
    '<p class="hint">尺寸：' + P.W + "×" + P.H + "，" + P.fps + " fps（多尺寸出片在之后的版本）。</p></fieldset>";
  if (RO) el.querySelectorAll("[data-path]").forEach((x) => { x.disabled = true; });
}
$("pane-set").addEventListener("change", (e) => {
  const x = e.target.closest("[data-path]"); if (!x || RO) return;
  let v = readVal(x);
  if (x.dataset.json) v = x.value === "" ? undefined : JSON.parse(x.value);
  if (v === null) { x.classList.add("err"); return; }
  x.classList.remove("err");
  const before = snap(), path = x.dataset.path;
  if (path === "music.file" && v === undefined) S.sb.music = null;
  else if (path.startsWith("music.") && !S.sb.music && path !== "music.file") { toast("先选一首配乐。"); renderSettings(); return; }
  else setPath(S.sb, path, v);
  commit(before);
  if (path.startsWith("captions.")) PNG.clear();
});

// ------------------------------------------------------------------ 新手导览（第一次打开时；? 里可以再看）
const TOUR = [
  ["欢迎使用 Studio", "左边是预览，右边是属性与工具，下面是多轨时间轴。改了什么都会<b>自动存进剪辑表</b>；你在对话里请 Claude 改的，这里也会同步。"],
  ["改字卡", "点画面或时间轴上的字卡就能在右边改字。停下来时字卡会换成<b>引擎排的真样子</b>：拖框＝移位置，拉右下角＝放大缩小。下面的「＋ 字卡」「＋ 特效」可以新增，Delete 删除。"],
  ["剪片", "「逐字稿」里删一句，就把那段从片子里剪掉，后面的字卡自动跟着往前；还有「找口误／重讲」和「推荐开头钩子」。"],
  ["检查与看真片", "「体检」把对时、字幕太长、字卡压脸标成红点；工具列的「安全区」「脸」「平台」帮你确认不被挡住。要看动态，按<b>渲染这一段</b>（几秒钟）。"],
  ["设定与素材", "「设定」改字幕样式、配乐、降噪、响度；「素材」把图片、影片拖进项目。满意了按右上角「出片」。按 <span class=\"kbd\">?</span> 随时看快捷键。"],
];
function tour(i) {
  const [t, body] = TOUR[i];
  modal('<div class="tour"><h2>' + t + '</h2><p class="hint" style="font-size:13px">' + body + '</p><div class="dots">' + TOUR.map((_, k) => "<i" + (k === i ? ' class="on"' : "") + "></i>").join("") +
    '</div><div class="acts"><button class="btn" data-a="skip">跳过</button>' + (i ? '<button class="btn" data-a="prev">上一步</button>' : "") +
    '<button class="btn primary" data-a="next">' + (i === TOUR.length - 1 ? "开始" : "下一步") + "</button></div></div>", (a) => {
    store.set("aaaai-studio-tour-1", true);
    if (a === "next" && i + 1 < TOUR.length) tour(i + 1);
    else if (a === "prev") tour(i - 1);
  });
}

// ------------------------------------------------------------------ 叠层开关
async function toggleFace() {
  SHOW.face = !SHOW.face; $("tgFace").setAttribute("aria-pressed", String(SHOW.face));
  if (SHOW.face && !FACES && !FACES_BUSY && P && P.source_ok) {
    FACES_BUSY = true; toast("在找脸的位置…（第一次要几秒到半分钟）");
    try { FACES = await api("api/faces?p=" + encodeURIComponent(P.id)); } catch (e) { toast("找不到脸的位置：" + e.message, true); SHOW.face = false; $("tgFace").setAttribute("aria-pressed", "false"); }
    FACES_BUSY = false;
  }
  renderGuides();
}
$("tgSafe").onclick = () => { SHOW.safe = !SHOW.safe; $("tgSafe").setAttribute("aria-pressed", String(SHOW.safe)); renderGuides(); };
$("tgFace").onclick = toggleFace;
$("platSel").onchange = (e) => { SHOW.plat = e.target.value; renderGuides(); };

let lastCur = -1;
function markTranscript() {
  const el = $("pane-tr"); if (el.hidden || !S) return;
  const src = T.toSrc(tOut).src, i = pieces().findIndex((pc) => src >= pc.s[0] && src < pc.s[1]);
  if (i === lastCur) return; lastCur = i;
  el.querySelectorAll(".tr-line.cur").forEach((x) => x.classList.remove("cur"));
  const cur = el.querySelector('.tr-line[data-i="' + i + '"]');
  if (cur) { cur.classList.add("cur"); if (playing) cur.scrollIntoView({ block: "nearest" }); }
}

// 体检
async function renderChecks(run) {
  const el = $("pane-chk");
  if (!run) {
    el.innerHTML = '<p class="hint">检查字幕对时（静音时还挂着字、讲话前就出字、话尾被切）、字幕太长、字卡压到脸、成片响度。问题会在时间轴上标红点，点一下跳过去。</p><button class="btn primary" id="runChk"' + (P && P.source_ok ? "" : " disabled") + ">开始体检</button>" + issuesHTML();
    $("runChk").onclick = () => renderChecks(true);
    return;
  }
  el.innerHTML = '<p class="hint">体检中…（第一次要分析声音，几秒到半分钟）</p>';
  try {
    await flushSave();
    const r = await api("api/check", { p: P.id });
    ISSUES = r.items; CHECKED = true;
    const n = ISSUES.filter((x) => x.level === "problem").length;
    $("chkN").hidden = !n; $("chkN").textContent = n;
    renderChecks(false); renderTimeline();
  } catch (e) { el.innerHTML = '<p class="hint">体检没跑成：' + esc(e.message) + "</p>"; }
}
function issuesHTML() {
  if (!CHECKED) return "";
  const n = ISSUES.filter((x) => x.level === "problem").length;
  return "<h3>" + (n ? n + " 个问题" : "没有发现问题 ✓") + "</h3>" + ISSUES.map((x) => '<div class="issue ' + x.level + '"' + (x.t != null ? ' data-t="' + x.t + '"' : "") + '><span class="dot"></span><div>' + (x.t != null ? '<span class="t">' + fmt(x.t) + "</span> " : "") + esc(x.msg) + "</div></div>").join("");
}
$("pane-chk").addEventListener("click", (e) => { const x = e.target.closest(".issue[data-t]"); if (x) { const t = +x.dataset.t; seek(t); const sc = $("tlScroll"); sc.scrollLeft = t * pps - sc.clientWidth / 3; } });

// ------------------------------------------------------------------ 加字卡、加特效、删除
function buildMenus() {
  if (!SCHEMA) return;
  $("cardMenu").innerHTML = SCHEMA.new.map(([g, items]) => '<div class="grp">' + esc(g) + "</div>" + items.map(([t, _d, hint], k) =>
    '<button data-t="' + esc(t) + '">' + esc((SCHEMA.cards[t] || {}).name || t) + "<small>" + esc(hint) + "</small></button>").join("")).join("");
  const snd = OPT ? OPT.sounds : ["pop", "ding", "whoosh", "coin"];
  const sname = (x) => ((SCHEMA.common.find((c) => c.key === "sfx") || { options: [] }).options.find((y) => y[0] === x) || [x, x])[1];
  $("fxMenu").innerHTML = '<div class="grp">画面</div><button data-fx="zoom">推近<small>这段画面慢慢放大</small></button><button data-fx="punch">瞬切推近<small>重点落下时冲一下</small></button><button data-fx="confetti">彩带<small>庆祝时刻</small></button>' +
    '<div class="grp">音效</div>' + snd.map((x) => '<button data-snd="' + esc(x) + '">' + esc(sname(x)) + "<small>" + esc(x) + "</small></button>").join("");
}
function menuToggle(btn, menu) {
  $(btn).onclick = (e) => { e.stopPropagation(); if (RO) return; buildMenus(); const m = $(menu), open = m.hidden; $("cardMenu").hidden = true; $("fxMenu").hidden = true; m.hidden = !open; if (open) { const f = m.querySelector("button"); if (f) f.focus(); } };
}
menuToggle("addCardBtn", "cardMenu"); menuToggle("addFxBtn", "fxMenu");
document.addEventListener("click", () => { $("cardMenu").hidden = true; $("fxMenu").hidden = true; });
function startAt(len) { const a = r2(Math.max(0, Math.min(tOut, T.dur - 0.5))); return [a, r2(Math.min(T.dur, a + len))]; }
$("cardMenu").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-t]"); if (!b) return;
  const type = b.dataset.t, data = SCHEMA.new.flatMap((g) => g[1]).find((x) => x[0] === type)[1];
  const before = snap();
  const o = Object.assign({ type, t: startAt((SCHEMA.new_len || {})[type] || 4) }, clone(data));
  (S.sb.overlays = S.sb.overlays || []).push(o);
  sel = { k: "ov", i: S.sb.overlays.length - 1 };
  commit(before); showPane("insp");
  toast("在 " + fmt(o.t[0]) + " 加了一张" + ((SCHEMA.cards[type] || {}).name || type) + "：右边改文字，画面上拖位置。", false, [["复原", undo]]);
});
$("fxMenu").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || (!b.dataset.fx && !b.dataset.snd)) return;
  const before = snap();
  if (b.dataset.snd) { (S.sb.sfx = S.sb.sfx || []).push({ t: r2(tOut), sound: b.dataset.snd }); sel = { k: "sx", i: S.sb.sfx.length - 1 }; }
  else if (b.dataset.fx === "confetti") { (S.sb.overlays = S.sb.overlays || []).push({ type: "confetti", t: startAt(2.6) }); sel = { k: "ov", i: S.sb.overlays.length - 1 }; }
  else { const punch = b.dataset.fx === "punch"; (S.sb.zooms = S.sb.zooms || []).push(Object.assign({ t: startAt(punch ? 0.6 : 2.5), to: punch ? 1.14 : 1.12 }, punch ? { style: "punch" } : {})); sel = { k: "zm", i: S.sb.zooms.length - 1 }; }
  commit(before); showPane("insp");
});
function deleteSel() {
  if (RO || !sel) return;
  if (sel.k === "cap") { cutPiece(sel.i); return; }
  const key = { ov: "overlays", rc: "recipes", zm: "zooms", sx: "sfx" }[sel.k];
  if (!key || !(S.sb[key] || [])[sel.i]) return;
  const before = snap(), what = { ov: "字卡", rc: "配方", zm: "推近", sx: "音效" }[sel.k];
  S.sb[key].splice(sel.i, 1); sel = null;
  commit(before);
  toast("删掉了这个" + what + "。", false, [["复原", undo]]);
}
$("delBtn").onclick = deleteSel;

// ------------------------------------------------------------------ 画面上拖拉：移位置、放大缩小（写进 xy、scale）
let cdragJustEnded = false;
function startCanvasDrag(e, mode) {
  const o = findSel(), pg = o && PNG.get(pngKey(o));
  if (RO || !o || !pg || !pg.box) return false;
  const r = stage.getBoundingClientRect();
  cdrag = { mode, o, box: pg.box, sx: e.clientX, sy: e.clientY, W: r.width, H: r.height, before: snap(), s0: +(o.scale || 1), k: 1, moved: false };
  $("selLayer").setPointerCapture(e.pointerId);
  e.preventDefault(); e.stopPropagation();
  return true;
}
$("selLayer").addEventListener("pointerdown", (e) => { if (e.target.closest(".selbox")) startCanvasDrag(e, e.target.classList.contains("hd") ? "scale" : "move"); });
layer.addEventListener("pointerdown", (e) => {
  const hit = e.target.closest(".hit"); if (!hit || RO) return;
  select({ k: "ov", i: +hit.dataset.i }); showPane("insp");
  startCanvasDrag(e, "move");
});
$("selLayer").addEventListener("pointermove", (e) => {
  if (!cdrag) return;
  const dx = e.clientX - cdrag.sx, dy = e.clientY - cdrag.sy;
  if (!cdrag.moved && Math.abs(dx) + Math.abs(dy) < 3) return;
  cdrag.moved = true;
  const img = $("truelook").querySelector('img[data-i="' + sel.i + '"]'), sb_ = $("selbox"), b = cdrag.box;
  if (cdrag.mode === "move") {
    const tr = "translate(" + dx + "px," + dy + "px)";
    if (img) img.style.transform = tr; if (sb_) sb_.style.transform = tr;
  } else {
    const diag = b[2] * cdrag.W + b[3] * cdrag.H;
    cdrag.k = Math.max(0.4 / cdrag.s0, Math.min(2.5 / cdrag.s0, 1 + (dx + dy) / Math.max(40, diag)));
    const org = b[0] * 100 + "% " + b[1] * 100 + "%";
    if (img) { img.style.transformOrigin = org; img.style.transform = "scale(" + cdrag.k + ")"; }
    if (sb_) { sb_.style.transformOrigin = "0 0"; sb_.style.transform = "scale(" + cdrag.k + ")"; }
  }
});
$("selLayer").addEventListener("pointerup", (e) => {
  if (!cdrag) return;
  const d = cdrag; cdrag = null;
  if (d.moved) {
    cdragJustEnded = true; setTimeout(() => { cdragJustEnded = false; }, 50);
    const b = d.box;
    if (d.mode === "move") {
      const cx = b[0] + b[2] / 2 + (e.clientX - d.sx) / d.W, top = b[1] + (e.clientY - d.sy) / d.H;
      d.o.xy = [r3(Math.max(0, Math.min(1, cx))), r3(Math.max(0, Math.min(0.97, top)))];
    } else d.o.scale = r2(d.s0 * d.k);
    commit(d.before);
  } else renderStage();
});
function nudge(dx, dy) {   // Alt＋方向键：微调位置（每次 0.5%，加 Shift＝2%）
  const o = findSel(), pg = o && PNG.get(pngKey(o));
  if (RO || !sel || sel.k !== "ov" || !o) return;
  const before = snap();
  const xy = o.xy ? [...o.xy] : pg && pg.box ? [pg.box[0] + pg.box[2] / 2, pg.box[1]] : null;
  if (!xy) { toast("停下来、等真样子出现后才能微调位置。"); return; }
  o.xy = [r3(Math.max(0, Math.min(1, xy[0] + dx))), r3(Math.max(0, Math.min(0.97, xy[1] + dy)))];
  commit(before);
}

// ------------------------------------------------------------------ 风格
$("styleSel").onchange = (e) => { const before = snap(); S.sb.style = e.target.value; commit(before); toast("整支片换成 " + e.target.value + " 风格；字卡真样子会在停下来后更新。"); };

// ------------------------------------------------------------------ 渲染这一段／出片
let curJob = null;
async function startJob(body) {
  if (RO) return;
  await flushSave();
  if (CONFLICT) { toast("先处理剪辑表的冲突再渲染。", true); return; }
  let r;
  try { r = await api("api/render", Object.assign({ p: P.id }, body)); } catch (e) { toast("没开始：" + e.message, true); return; }
  if (r.busy) { toast(r.msg, true); return; }
  curJob = r.job;
  const done = await waitJob(r.job, true);
  curJob = null;
  if (done.status === "done") {
    if (body.kind === "range") playResult(done.result, "这一段的成品画面（预览画质）", done.elapsed);
    else { P.final = done.result; toast("成片出好了（" + done.elapsed + " 秒）：out/final.mp4", false, [["播放", () => playResult(done.result, "成片", null)]], 12000); }
  } else if (done.status === "error") {
    toast("渲染失败：" + (done.log || []).slice(-2).join(" ") + "（⋯ → 诊断报告）", true);
  }
}
function waitJob(id, show) {
  return new Promise((resolve) => {
    if (show) { $("job").hidden = false; $("jobBar").style.width = "0"; }
    const t = setInterval(async () => {
      let j; try { j = await api("api/job?id=" + id); } catch (_) { return; }
      if (show) { $("jobLabel").textContent = j.label + " · " + j.stage; $("jobBar").style.width = Math.round(j.progress * 100) + "%"; $("jobPct").textContent = Math.round(j.progress * 100) + "%"; }
      if (j.status !== "running") { clearInterval(t); if (show) $("job").hidden = true; resolve(j); }
    }, 500);
  });
}
$("jobCancel").onclick = () => { if (curJob) api("api/cancel", { id: curJob }).then(() => toast("已取消。")); };
function renderRange() {
  const rg = rangeOf() || [Math.max(0, tOut - 2), Math.min(T.dur, tOut + 3)];
  const a = Math.max(0, rg[0] - 0.3), b = Math.min(T.dur, Math.max(rg[1] + 0.3, a + 1));
  startJob({ kind: "range", a: r3(a), b: r3(Math.min(b, a + 30)) });
}
$("renderRange").onclick = renderRange;
$("export").onclick = () => {
  modal('<h2>出片</h2><p class="hint">按目前的剪辑表出正式成片（' + fmt(T.dur) + "），覆盖 out/final.mp4。长片要几分钟，进度在上方；可以取消。</p><div class=\"acts\"><button class=\"btn\" data-a=\"no\">先不要</button><button class=\"btn primary\" data-a=\"go\">出片</button></div>", (a) => { if (a === "go") startJob({ kind: "final", duration: T.dur }); });
};
function playResult(url, title, sec) {
  modal("<h2>" + esc(title) + (sec ? '　<span class="hint">渲染 ' + sec + " 秒</span>" : "") + '</h2><video controls autoplay playsinline src="' + esc(url) + "?v=" + Date.now() + '"></video><div class="acts"><button class="btn" data-a="close">关闭</button></div>', null, true);
}

// ------------------------------------------------------------------ 提示、对话框、快捷键、诊断
let toastTimer = null;
function toast(msg, bad, acts, ms) {
  const t = $("toast");
  t.innerHTML = "<span>" + esc(msg) + "</span>" + (acts || []).map((a, k) => '<button class="btn sm" data-k="' + k + '">' + esc(a[0]) + "</button>").join("");
  t.className = "toast" + (bad ? " bad" : ""); t.hidden = false;
  t.onclick = (e) => { const b = e.target.closest("button"); if (b) { t.hidden = true; acts[+b.dataset.k][1](); } };
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, ms || (acts ? 8000 : 4200));
}
function modal(html, onAct, wide) {
  const m = $("modal"), box = $("modalBox");
  box.className = "box" + (wide ? " wide" : ""); box.innerHTML = html; m.hidden = false;
  const close = () => { m.hidden = true; box.innerHTML = ""; document.removeEventListener("keydown", esc_); };
  const esc_ = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", esc_);
  box.onclick = (e) => { const b = e.target.closest("[data-a]"); if (!b) return; const a = b.dataset.a; if (a !== "copy") close(); if (onAct) onAct(a); };
  m.onclick = (e) => { if (e.target === m) close(); };
  const f = box.querySelector(".primary, button"); if (f) f.focus();
}
function help() {
  const k = [["空格", "播放／暂停"], ["← →", "前后一格（加 Shift＝一秒）"], ["Alt＋方向键", "微调选中字卡的位置（加 Shift＝大步）"], ["G", "安全区开关"], ["⌘Z／Ctrl+Z", "复原"], ["⇧⌘Z／Ctrl+Y", "重做"], ["R", "渲染这一段（选中的或播放头前后）"], ["Delete", "删除选中的字卡／特效；选中字幕＝把那句剪掉"], ["Esc", "取消选取"], ["M", "声音开关"], ["+ −", "时间轴放大缩小"], ["?", "这张表"]];
  modal('<h2>快捷键</h2><div class="keys">' + k.map((x) => '<span class="kbd">' + esc(x[0]) + "</span><span>" + esc(x[1]) + "</span>").join("") + '</div><p class="hint">画面上的字卡是近似样子，停下来会换成引擎的真样子；动态、转场、组合卡以「渲染这一段」为准。</p>' +
    '<div class="acts"><button class="btn" data-a="tour">再看一次导览</button><button class="btn" data-a="diag">诊断报告</button><button class="btn primary" data-a="close">好</button></div>', (a) => { if (a === "diag") diag(); if (a === "tour") tour(0); });
}
async function diag() {
  try {
    const r = await api("api/diag", { p: P ? P.id : null });
    modal("<h2>诊断报告</h2><p class=\"hint\">不含影片、不含金钥。遇到问题把这段复制给 Claude。" + (r.path ? "<br>也存在：" + esc(r.path) : "") + "</p><pre id=\"diagText\">" + esc(r.text) + '</pre><div class="acts"><button class="btn" data-a="copy">复制</button><button class="btn primary" data-a="close">关闭</button></div>', (a) => {
      if (a === "copy") { navigator.clipboard.writeText(r.text).then(() => toast("已复制。"), () => toast("复制不了，请手动选取。", true)); }
    }, true);
  } catch (e) { toast("诊断报告没产生：" + e.message, true); }
}
$("more").onclick = help;
document.addEventListener("keydown", (e) => {
  if ($("app").hidden || !$("modal").hidden) return;
  if (e.target.closest("input, textarea, select")) return;
  const mod = e.metaKey || e.ctrlKey;
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  else if (mod && (e.key === "z" || e.key === "Z")) { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  else if (mod && (e.key === "y" || e.key === "Y")) { e.preventDefault(); redo(); }
  else if (mod) return;
  else if (e.altKey && e.key.startsWith("Arrow")) { e.preventDefault(); const st = e.shiftKey ? 0.02 : 0.005; nudge(e.key === "ArrowLeft" ? -st : e.key === "ArrowRight" ? st : 0, e.key === "ArrowUp" ? -st : e.key === "ArrowDown" ? st : 0); }
  else if (e.key === "ArrowRight") { e.preventDefault(); seek(tOut + (e.shiftKey ? 1 : 1 / P.fps)); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); seek(tOut - (e.shiftKey ? 1 : 1 / P.fps)); }
  else if (e.key === "Delete" || e.key === "Backspace") { if (sel) { e.preventDefault(); deleteSel(); } }
  else if (e.key === "g" || e.key === "G") $("tgSafe").click();
  else if (e.key === "Escape") select(null);
  else if (e.key === "r" || e.key === "R") renderRange();
  else if (e.key === "m" || e.key === "M") $("mute").click();
  else if (e.key === "?") help();
  else if (e.key === "+" || e.key === "=") { $("zoom").value = Math.min(120, pps * 1.25); $("zoom").oninput({ target: $("zoom") }); }
  else if (e.key === "-") { $("zoom").value = Math.max(6, pps / 1.25); $("zoom").oninput({ target: $("zoom") }); }
});

function renderAll() { renderTimeline(); renderStage(); renderInspector(); renderTranscript(); renderSettings(); if (!$("pane-chk").hidden) renderChecks(false); tick(); }

// ------------------------------------------------------------------ 路由
async function route() {
  const m = location.hash.match(/p=([0-9a-f]+)/);
  try { if (m) await openProject(m[1]); else await showHome(); }
  catch (e) { toast("出错了：" + e.message + "（⋯ → 诊断报告）", true); }
}
window.addEventListener("hashchange", () => { flushSave().finally(route); });
route();
