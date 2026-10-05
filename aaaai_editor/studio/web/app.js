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
let multi = [];          // 多选：[{k, i}]（字卡、配方、推近、音效）
let stopAt = null;       // 试听剪点：播到这里自己停
let BROLL = null;        // B-roll 状态与搜寻结果
let NOTES = [];          // 时间点留言（work/notes.json；不进复原纪录）
let RULES = null;        // 频道规则
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
$("adoptBtn").onclick = () => {
  modal('<h2>接入影片</h2><p class="hint">把别处做好的影片（HyperFrames、动画片、别的剪辑软件出的）接进来，统一做字幕、响度、封面。会建一个新项目，影片复制进项目的 raw/（原档不动），自动转录。</p>' +
    '<div class="field"><label for="adName">项目名字</label><input id="adName" placeholder="例：产品发布" style="background:var(--panel-2);border:1px solid var(--line);border-radius:6px;padding:6px 8px"></div>' +
    '<div class="field"><label for="adFile">影片（mp4／mov）</label><input id="adFile" type="file" accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"></div><p class="hint" id="adMsg"></p>' +
    '<div class="acts"><button class="btn" data-a="close">取消</button><button class="btn primary" data-a="copy" id="adGo">接入</button></div>', async (a) => {
    if (a !== "copy") return;
    const f = $("adFile").files[0], msg = $("adMsg");
    if (!f) { msg.textContent = "先选一支影片。"; return; }
    $("adGo").disabled = true;
    try {
      const np = await api("api/newproject", { name: $("adName").value || f.name.replace(/\.[^.]+$/, "") });
      await new Promise((ok, bad) => {
        const x = new XMLHttpRequest();
        x.open("POST", "api/upload?p=" + np.id + "&dir=raw&name=" + encodeURIComponent(f.name));
        x.upload.onprogress = (e) => { if (e.lengthComputable) msg.textContent = "复制影片：" + Math.round(e.loaded / e.total * 100) + "%"; };
        x.onload = () => (x.status === 200 ? ok() : bad(new Error((JSON.parse(x.responseText || "{}").error) || x.status)));
        x.onerror = () => bad(new Error("上传失败")); x.send(f);
      });
      msg.textContent = "接入并转录中…（几十秒到几分钟）";
      const r = await api("api/render", { p: np.id, kind: "adopt" });
      if (r.busy) throw new Error(r.msg);
      const done = await waitJob(r.job, false);
      if (done.status !== "done") throw new Error((done.log || []).slice(-2).join(" ") || done.stage);
      $("modal").hidden = true; location.hash = "p=" + np.id;
    } catch (e) { msg.textContent = "没接成：" + e.message; $("adGo").disabled = false; }
  });
};
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
  P = { id: j.id, name: j.name, fps: j.fps, W: j.W, H: j.H, styles: j.styles, source_ok: j.source_ok, proxy: j.proxy, final: j.final, srcDur: j.source_duration || 1e9, dir: j.dir };
  S = { sb: j.storyboard, cap: j.captions };
  AUTO = j.captions_auto || [];
  V = { sb: j.sb_version, cap: j.cap_version, notes: j.notes_version || "" };
  NOTES = j.notes || [];
  SAVED = { sb: JSON.stringify(S.sb), cap: S.cap ? JSON.stringify(S.cap) : "" };
  RO = !j.source_ok;
  CONFLICT = false;
  T = TL();
  if (first) { FACES = null; TOOLS.tidy = null; TOOLS.hooks = null; OPT = null; multi = []; BROLL = null; RULES = null; }
  if (first) { undoStack = []; redoStack = []; sel = null; tOut = 0; ISSUES = []; CHECKED = false; $("chkN").hidden = true; PNG.clear(); }
  else { sel = keepSel && findSel(keepSel) ? keepSel : null; tOut = Math.min(keepT, Math.max(0, T.dur - 0.01)); }
  document.title = P.name + " · Studio";
  $("projName").textContent = "　" + P.name;
  $("styleSel").innerHTML = Object.keys(P.styles).map((k) => '<option value="' + esc(k) + '">' + esc(k) + "</option>").join("");
  $("styleSel").value = S.sb.style || "";
  $("app").classList.toggle("ro-mode", RO);
  $("roNote").hidden = !RO;
  $("roNote").innerHTML = RO ? '<span class="ro">原片不见了：只能看、不能改（把原片放回 storyboard.json 的 source 指向的位置后重新打开）</span>' : "";
  ["undo", "redo", "renderRange", "export", "styleSel", "addCardBtn", "addFxBtn", "delBtn", "splitBtn", "styleAll"].forEach((x) => { $(x).disabled = RO; });
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
  if ((v.notes_version || "") !== V.notes) {   // 留言变了（多半是 Claude 回覆了）：直接更新，不算冲突
    const had = NOTES.filter((n) => n.reply).length;
    const r = await api("api/notes", { p: P.id });
    setNotes(r);
    if (NOTES.filter((n) => n.reply).length > had) toast("Claude 回覆了留言（看「留言」页）。");
  }
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
const BLUR_BOX = [0.35, 0.40, 0.30, 0.15];
function boxOf(o) {
  if (o && o.type === "blur") return (o.box || BLUR_BOX).map(Number);
  const pg = o && PNG.get(pngKey(o));
  return pg && pg.box;
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
    if (v.k === "ov" && o.type === "blur") {   // 打码：画面上直接用模糊近似（马赛克要渲染才看得到格子）
      const bb = boxOf(o), px = Math.max(4, 16 * (+o.strength || 1));
      h += '<div class="hit blurbox' + (o.mode === "mosaic" ? " mosaic" : "") + '" data-k="ov" data-i="' + v.i + '" style="' + boxCss(bb) + ";--bl:" + px + 'px"></div>';
      continue;
    }
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
  const o = findSel(), bx = o && boxOf(o);
  if (!o || !bx || !(tOut >= o.t[0] && tOut < o.t[1])) { el.innerHTML = ""; return; }
  el.innerHTML = '<div class="selbox" id="selbox" style="' + boxCss(bx) + '"><span class="lbl">' + (RO ? "只读" : o.type === "blur" ? "拖动＝移范围 · 拉角＝大小" : "拖动＝移位置 · 拉角＝大小") + "</span>" + (RO ? "" : '<i class="hd" title="拉动改大小"></i>') + "</div>";
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
  multi = [];
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
  if (stopAt !== null && tOut >= stopAt) { stopAt = null; togglePlay(); return; }
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
  for (const n of NOTES) h += '<i class="mark nt' + (n.status === "done" ? " done" : "") + '" data-t="' + n.t + '" title="留言 #' + n.id + "：" + esc(n.text) + '" style="left:' + n.t * pps + 'px"></i>';
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
const inMulti = (k, i) => multi.some((m) => m.k === k && m.i === i);
function block(k, i, a, b, text, top, bad) {
  const isSel = sel && sel.k === k && sel.i === i;
  return '<div class="tl-block ' + k + (isSel ? " sel" : "") + (inMulti(k, i) && multi.length > 1 ? " multi" : "") + (k === "cut" && !RO ? " trim" : "") + (bad ? " bad" : "") + '" tabindex="0" data-k="' + k + '" data-i="' + i + '" style="left:' + a * pps + "px;width:" + Math.max(6, (b - a) * pps) + "px" + (top !== undefined ? ";top:" + top + "px" : "") + '" title="' + esc(plain(text)) + '">' + esc(plain(text)) + "</div>";
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
  const multiable = ["ov", "rc", "zm", "sx"].includes(k);
  if (multiable && (e.shiftKey || e.metaKey || e.ctrlKey)) {   // 加选／减选
    if (!multi.length && sel && ["ov", "rc", "zm", "sx"].includes(sel.k)) multi = [sel];
    multi = inMulti(k, i) ? multi.filter((m) => !(m.k === k && m.i === i)) : multi.concat([{ k, i }]);
    sel = multi.length ? multi[multi.length - 1] : null;
    renderTimeline(); renderInspector(); renderStage(); return;
  }
  if (!inMulti(k, i)) multi = [];
  select({ k, i });
  if (k === "cut" && !RO && mode !== "move") {   // 拖画面段的两端＝修剪剪辑点（原片入点／出点）
    tdrag = { k, i, mode, sx: e.clientX, before: snap(), sbBefore: clone(S.sb), orig: clone(S.sb.cuts), moved: false };
    $("tlInner").setPointerCapture(e.pointerId); e.preventDefault(); return;
  }
  if (RO || k === "cut") { seek((e.clientX - rect.left) / pps); return; }
  if (k === "cap" && !ensureCapTrack()) return;
  const o = findSel();
  const a0 = k === "cap" ? +o.s[0] : k === "sx" ? +o.t : +o.t[0], b0 = k === "cap" ? +o.s[1] : k === "sx" ? +o.t : +o.t[1];
  const others = multi.length > 1 ? multi.filter((m) => !(m.k === k && m.i === i)).map((m) => ({ o: findSel(m), k: m.k })).filter((x) => x.o)
    .map((x) => ({ o: x.o, k: x.k, t: clone(x.o.t) })) : [];
  tdrag = { k, o, mode, sx: e.clientX, before: tdragBefore || snap(), a0, b0, moved: false, others };
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
  if (tdrag.k === "cut") {
    const c = tdrag.orig[tdrag.i].slice();
    if (tdrag.mode === "l") c[0] = r2(Math.max(0, Math.min(c[1] - 0.2, c[0] + d)));
    else c[1] = r2(Math.min(P.srcDur, Math.max(c[0] + 0.2, c[1] + d)));
    S.sb.cuts = tdrag.orig.map((x, j) => (j === tdrag.i ? c : x)); T = TL();
    renderTimeline(); seek(tdrag.mode === "l" ? T.off[tdrag.i] : T.off[tdrag.i] + c[1] - c[0] - 0.05);
    toast("原片 " + fmt(c[0]) + " – " + fmt(c[1]) + "（放开后字卡会跟着换算）");
    return;
  }
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
  if (tdrag.others.length && tdrag.mode === "move") {   // 多选：整组一起移
    const dt = (tdrag.k === "sx" ? +o.t : +o.t[0]) - tdrag.a0;
    for (const x of tdrag.others) x.o.t = Array.isArray(x.t) ? [r2(Math.max(0, x.t[0] + dt)), r2(Math.max(0.3, x.t[1] + dt))] : r2(Math.max(0, x.t + dt));
  }
  renderTimeline(); renderStage(); renderInspector();
});
$("tlInner").addEventListener("pointerup", async () => {
  const d = tdrag; tdrag = null;
  if (d && d.k === "cut") {
    if (!d.moved) return;
    const newCuts = clone(S.sb.cuts);
    S.sb = d.sbBefore;   // 用拖之前的剪辑表换算字卡时间，再整组换上新剪辑点
    try {
      const r = await api("api/recut", { storyboard: clone(S.sb), set: newCuts });
      S.sb = r.storyboard; T = TL(); commit(d.before);
      toast("剪辑点改好了，片长 " + fmt(T.dur) + "；字卡已跟着换算。", false, [["复原", undo]]);
    } catch (e) { T = TL(); renderAll(); toast("没改成：" + e.message, true); }
    return;
  }
  if (d && d.before && d.moved) commit(d.before);
  scheduleTrueLook();
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
  for (const n of ["insp", "tr", "chk", "nt", "ast", "cov", "set"]) $("pane-" + n).hidden = n !== name;
  if (name === "nt") renderNotes();
  if (name === "cov") renderCover();
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
  if (multi.length > 1) { renderMulti(el); return; }
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
    if (!["blur", "confetti", "image", "clip", "broll", "cutout", "glow", "countdown"].includes(o.type)) {
      const C = [["accent", "强调色"], ["text", "文字色"], ["plate", "底板色"], ["value", "数值色"]], cc = o.colors || {};
      h += '<fieldset><legend>颜色（这张卡；不改＝跟随风格）</legend><div class="row2">' + C.map(([k, lb]) => '<div class="field"><label>' + lb + '</label><div style="display:flex;gap:6px;align-items:center"><input type="color" data-col="' + k + '" value="' + esc(/^#[0-9a-fA-F]{6}$/.test(cc[k] || "") ? cc[k] : (P.styles[S.sb.style] || {}).accent && k === "accent" ? P.styles[S.sb.style].accent : "#ffffff") + '"' + (RO ? " disabled" : "") + ">" +
        (cc[k] ? '<button class="btn sm" data-colreset="' + k + '" title="回到风格的颜色">×</button>' : '<span class="hint">风格</span>') + "</div></div>").join("") + "</div></fieldset>";
    }
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
    if (!RO) h += '<div class="row2">' + inp("c_a", "原片入点（秒）", "num", o[0]) + inp("c_b", "原片出点（秒）", "num", o[1]) + "</div>";
    h += '<div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm" id="audIn"' + (sel.i ? "" : " disabled") + '>▶ 试听入点（前后 2 秒）</button><button class="btn sm" id="audOut"' + (sel.i + 1 < T.cuts.length ? "" : " disabled") + ">▶ 试听出点</button>" +
      (RO ? "" : '<button class="btn danger sm" id="cutDel">删除这段</button>') + "</div>";
    h += '<p class="hint">时间轴上拖这一段的<b>两端</b>＝修剪入点／出点（字卡会自动跟着换算）；<span class="kbd">S</span> 在播放头切开；讲错的句子也可以到<b>逐字稿</b>里删。</p>';
  }
  if (!RO && ["ov", "rc", "zm", "sx"].includes(sel.k)) h += '<button class="btn danger sm" id="delSel">删除' + ({ ov: "这张字卡", rc: "这个配方", zm: "这个推近", sx: "这个音效" }[sel.k]) + "</button>";
  el.innerHTML = h;
  bindInspector(o);
  const ds = $("delSel"); if (ds) ds.onclick = deleteSel;
  if (sel.k === "cut") {
    const ai = $("audIn"), ao = $("audOut"), cd = $("cutDel"), i = sel.i;
    if (ai) ai.onclick = () => playRange(T.off[i] - 2, T.off[i] + 2);
    if (ao) ao.onclick = () => playRange(T.off[i + 1] - 2, T.off[i + 1] + 2);
    if (cd) cd.onclick = deleteSel;
    for (const id of ["c_a", "c_b"]) {
      const x = $(id); if (!x) continue;
      x.onchange = async () => {
        const v = parseFloat(x.value); if (isNaN(v)) return;
        const c = T.cuts[i].slice(); if (id === "c_a") c[0] = r3(Math.max(0, v)); else c[1] = r3(Math.min(P.srcDur, v));
        if (c[1] - c[0] < 0.2) { x.classList.add("err"); return; }
        const before = snap();
        try { const r = await api("api/recut", { storyboard: clone(S.sb), set: T.cuts.map((y, j) => (j === i ? c : y)) }); S.sb = r.storyboard; T = TL(); commit(before); }
        catch (e) { toast("没改成：" + e.message, true); }
      };
    }
    return;
  }
  const rx = $("resetXY"); if (rx) rx.onclick = () => { const before = snap(); delete o.xy; commit(before); };
  $("pane-insp").querySelectorAll("[data-col]").forEach((x) => {
    let before = null;
    x.addEventListener("focus", () => { before = snap(); });
    x.addEventListener("input", () => { if (!before) before = snap(); o.colors = Object.assign({}, o.colors || {}, { [x.dataset.col]: x.value }); });
    x.addEventListener("change", () => { o.colors = Object.assign({}, o.colors || {}, { [x.dataset.col]: x.value }); commit(before || snap()); before = null; });
  });
  $("pane-insp").querySelectorAll("[data-colreset]").forEach((x) => x.addEventListener("click", () => {
    const before = snap(); delete o.colors[x.dataset.colreset]; if (!Object.keys(o.colors).length) delete o.colors; commit(before);
  }));
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
  const bt = $("batch"); if (bt) bt.addEventListener("toggle", () => { TOOLS.batch = bt.open; });
}
$("pane-tr").addEventListener("input", (e) => { if (["bFind", "bRep", "bHl"].includes(e.target.id)) (TOOLS.bv = TOOLS.bv || {})[e.target.id] = e.target.value; });
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
  const bv = TOOLS.bv || {};
  h += '<details id="batch"' + (TOOLS.batch ? " open" : "") + '><summary class="hint" style="cursor:pointer">字幕批量：查找替换、全部高亮、整体前后移</summary><div style="display:grid;gap:6px;margin-top:6px">' +
    '<div class="row2"><input id="bFind" placeholder="找" class="field-in" value="' + esc(bv.bFind || "") + '"><input id="bRep" placeholder="换成" class="field-in" value="' + esc(bv.bRep || "") + '"></div><button class="btn sm" data-tool="replace">全部替换（中文和英文）</button>' +
    '<div class="row2"><input id="bHl" placeholder="要高亮的词" class="field-in" value="' + esc(bv.bHl || "") + '"><button class="btn sm" data-tool="hlAll">每句都高亮</button></div>' +
    '<div style="display:flex;gap:6px;align-items:center"><span class="hint">全部字幕</span><button class="btn sm" data-tool="shift" data-arg="-0.05">早 0.05 秒</button><button class="btn sm" data-tool="shift" data-arg="0.05">晚 0.05 秒</button></div></div></details>';
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
  if (name === "replace" || name === "hlAll" || name === "shift") {
    const before = snap();
    if (!ensureCapTrack()) return;
    tdragBefore = null;
    let n = 0;
    if (name === "replace") {
      const f = $("bFind").value, r = $("bRep").value;
      if (!f) { toast("先填要找的字。"); return; }
      for (const pc of S.cap.pieces) for (const key of ["text", "en"]) if (pc[key] && pc[key].includes(f)) { n += pc[key].split(f).length - 1; pc[key] = pc[key].split(f).join(r); }
      if (!n) { toast("没找到「" + f + "」。"); return; }
      commit(before); toast("换了 " + n + " 处。", false, [["复原", undo]]); return;
    }
    if (name === "hlAll") {
      const w = $("bHl").value.trim(); if (!w) { toast("先填要高亮的词。"); return; }
      for (const pc of S.cap.pieces) if ((pc.text || "").includes(w) && !(pc.hl || []).includes(w) && !(pc.text || "").includes("**" + w)) { pc.hl = (pc.hl || []).concat([w]); n++; }
      if (!n) { toast("没有句子含「" + w + "」，或已经高亮了。"); return; }
      commit(before); toast(n + " 句的「" + w + "」高亮了。", false, [["复原", undo]]); return;
    }
    const dt = +arg;
    for (const pc of S.cap.pieces) pc.s = [r3(Math.max(0, +pc.s[0] + dt)), r3(Math.max(0.1, +pc.s[1] + dt))];
    commit(before); toast("全部字幕" + (dt < 0 ? "提早" : "延后") + " " + Math.abs(dt) + " 秒。", false, [["复原", undo]]); return;
  }
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
  el.insertAdjacentHTML("beforeend", brollHTML());
  bindBroll();
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

// ------------------------------------------------------------------ B-roll：素材库、Pexels 免费素材（AI 生成要花钱，留在对话里先报价）
function brollHTML() {
  if (RO) return "";
  const st = BROLL && BROLL.status;
  let h = '<fieldset><legend>B-roll（盖在人像上的画面）</legend>';
  if (!st) { loadBroll(); return h + '<p class="hint">读取中…</p></fieldset>'; }
  h += st.pexels ? '<div class="row2"><input id="pxQ" placeholder="英文关键词，例：city night" value="' + esc(BROLL.q || "") + '"><button class="btn sm" id="pxGo">搜 Pexels 免费素材</button></div>'
    : '<p class="hint">绑定 Pexels 密钥（免费）就能在这里搜素材：在你自己的终端执行 <code>aaaai-editor keys set PEXELS_API_KEY</code>。</p>';
  if (BROLL.busy) h += '<p class="hint">' + esc(BROLL.busy) + "</p>";
  if (BROLL.res && BROLL.res.length) h += '<div class="pex">' + BROLL.res.map((x) => '<button data-px="' + x.id + '" title="Pexels / ' + esc(x.user) + '"><img alt="" src="' + esc(x.thumb) + '"><span>' + esc(x.user) + " · " + x.duration + "s</span></button>").join("") + "</div><p class=\"hint\">点一个＝下载进 assets/broll/ 并放在播放头（署名自动记在 out/broll_credits.txt）。</p>";
  if (BROLL.lib && BROLL.lib.length) h += "<b>素材库（以前生成或下载过的）</b>" + BROLL.lib.map((x) => '<div class="it" style="display:flex;justify-content:space-between;gap:8px"><span class="hint">' + esc(x.text || x.key) + "（" + esc(x.provider || "") + '）</span><button class="btn sm" data-lib="' + esc(x.key) + '">用这个</button></div>').join("");
  return h + '<p class="hint">要 AI 生成画面：在对话里说「这一段帮我生成 B-roll」，Claude 会先报价、你同意才花钱。</p></fieldset>';
}
async function loadBroll() {
  BROLL = BROLL || {};
  try { BROLL.status = await api("api/broll", { p: P.id, action: "status" }); BROLL.lib = (await api("api/broll", { p: P.id, action: "library" })).items; }
  catch (e) { BROLL.status = { pexels: false }; }
  renderAssets();
}
function bindBroll() {
  const go = $("pxGo");
  if (go) go.onclick = async () => {
    const q = $("pxQ").value.trim(); if (!q) return;
    BROLL.q = q; BROLL.busy = "搜寻中…"; renderAssets();
    try { BROLL.res = (await api("api/broll", { p: P.id, action: "search", q })).items; } catch (e) { toast("搜不到：" + e.message, true); }
    BROLL.busy = ""; renderAssets();
  };
  const pane = $("pane-ast");
  pane.querySelectorAll("[data-px], [data-lib]").forEach((b) => b.onclick = async () => {
    BROLL.busy = "下载并转成片子的画幅…（十几秒）"; renderAssets();
    try {
      const r = await api("api/broll", b.dataset.px ? { p: P.id, action: "get", id: b.dataset.px } : { p: P.id, action: "get", key: b.dataset.lib });
      const before = snap();
      (S.sb.overlays = S.sb.overlays || []).push(Object.assign({ type: "broll", t: startAt(3), file: r.path }, r.credit ? { credit: r.credit } : {}));
      sel = { k: "ov", i: S.sb.overlays.length - 1 }; multi = [];
      commit(before); toast("B-roll 放好了：时间轴上拖它对准要盖的句子。", false, [["复原", undo]]);
    } catch (e) { toast("没拿到：" + e.message, true); }
    BROLL.busy = ""; renderAssets();
  });
}

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
    '<div class="row2">' + sfield("music.fade_in", "配乐淡入（秒）", "num") + sfield("music.fade_out", "配乐淡出（秒）", "num") + "</div>" +
    '<div class="row2">' + sfield("music.start", "从配乐第几秒开始", "num") + sfield("music.end", "配乐在成片第几秒收掉", "num") + "</div>" +
    sfield("denoise", "降噪", "jsel", [["", "标准（默认）"], ['"strong"', "加强"], ["false", "关（原声）"]]) +
    sfield("loudness", "成片响度（LUFS）", "num", null, "默认 −14（各平台通用）。") +
    '<div class="row2"><div class="field"><label for="audMusic">试听别的配乐</label><select id="audMusic">' + bgm.filter((x) => x[0]).map((x) => '<option value="' + esc(x[0]) + '">' + esc(x[1]) + "</option>").join("") + '</select></div><div class="field"><label>&nbsp;</label><button class="btn sm" id="audMusicGo">▶ 试听 8 秒</button></div></div>' +
    '<div class="row2"><div class="field"><label for="audDn">试听降噪</label><select id="audDn"><option value="true">标准</option><option value="&quot;strong&quot;">加强</option><option value="false">关（原声）</option></select></div><div class="field"><label>&nbsp;</label><button class="btn sm" id="audDnGo">▶ 试听 8 秒</button></div></div>' +
    '<p class="hint" style="margin:-4px 0 0">从播放头开始渲染 8 秒（真正的混音与响度），不会改到剪辑表。</p></fieldset>' +
    '<fieldset><legend>取景（推近整支片）</legend><div class="row2">' + sfield("framing.zoom", "放大（1–1.4）", "num") + sfield("framing.cy", "垂直中心（0–1）", "num") + "</div>" +
    sfield("framing.cx", "水平中心（0–1）", "num", null, "机位太远时用，约 1.15–1.25 安全；改了会重做播放用的影片。") + "</fieldset>" +
    '<fieldset><legend>出片</legend>' + sfield("ending.fade", "结尾淡出（秒）", "num") +
    sfield("output.encoder", "编码", "select", [["", "软件编码（画质最好）"], ["hw", "硬件编码（快几倍、文件稍大）"]]) +
    '<p class="hint">尺寸：' + P.W + "×" + P.H + "，" + P.fps + " fps（多尺寸出片在之后的版本）。</p></fieldset>";
  if (RO) el.querySelectorAll("[data-path], button").forEach((x) => { x.disabled = true; });
  const aud = (ov) => startJob({ kind: "audition", a: r3(tOut), b: r3(Math.min(T.dur, tOut + 8)), override: ov });
  const am = $("audMusicGo"); if (am) am.onclick = () => aud({ music: Object.assign({ db: -18, duck: true }, S.sb.music || {}, { file: $("audMusic").value }) });
  const ad = $("audDnGo"); if (ad) ad.onclick = () => aud({ denoise: JSON.parse($("audDn").value) });
}
function pathChange(e) {
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
  if (path.startsWith("framing.") && P.source_ok) flushSave().then(() => { P.proxy = null; prepareProxy(); });
}
$("pane-set").addEventListener("change", pathChange);
$("pane-cov").addEventListener("change", pathChange);

// ------------------------------------------------------------------ 时间点留言（可以请 Claude 处理）
function setNotes(r) {
  NOTES = r.notes || []; V.notes = r.notes_version || "";
  const n = NOTES.filter((x) => x.status !== "done" && x.to === "claude").length;
  $("ntN").hidden = !n; $("ntN").textContent = n;
  renderTimeline(); renderNotes();
}
function selLabel() {
  const o = findSel(); if (!o || !sel) return null;
  if (sel.k === "ov") return { k: "ov", i: sel.i, label: ((SCHEMA.cards[o.type] || {}).name || o.type) + "「" + plain(o.kicker || o.text || o.name || o.title || "").slice(0, 16) + "」" };
  if (sel.k === "rc") return { k: "rc", i: sel.i, label: "配方 " + o.use };
  if (sel.k === "cap") return { k: "cap", i: sel.i, label: "字幕「" + plain(o.text).slice(0, 16) + "」" };
  return null;
}
function addNote() {
  if (RO || !P) return;
  const rg = rangeOf(), ref = selLabel();
  modal('<h2>在 ' + fmt(tOut) + " 留言</h2>" + (ref ? '<p class="hint">关于：' + esc(ref.label) + (rg ? "（成片 " + fmt(rg[0]) + "–" + fmt(rg[1]) + "）" : "") + "</p>" : "") +
    '<div class="field"><textarea id="ntText" rows="4" placeholder="例：这里字卡太多了，留一张就好／开头太慢，帮我剪紧一点"></textarea></div>' +
    '<label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="ntClaude" checked> 请 Claude 处理（在对话里说「看 Studio 留言」）</label>' +
    '<div class="acts"><button class="btn" data-a="close">取消</button><button class="btn primary" data-a="save">留言</button></div>', async (a) => {
    if (a !== "save") return;
    try {
      const r = await api("api/notes", Object.assign({ p: P.id, action: "add", text: $("ntText").value, t: r2(tOut), to: $("ntClaude").checked ? "claude" : "me", ref },
        rg && ref ? { a: r2(rg[0]), b: r2(rg[1]) } : {}));
      setNotes(r); toast("留言了。" + ($("ntClaude") && $("ntClaude").checked ? "" : ""), false, [["看留言", () => showPane("nt")]]);
    } catch (e) { toast("没留成：" + e.message, true); }
  });
  setTimeout(() => { const t = $("ntText"); if (t) t.focus(); }, 30);
}
$("noteBtn").onclick = addNote;
function renderNotes() {
  const el = $("pane-nt"); if (!P || el.hidden) return;
  const open = NOTES.filter((n) => n.status !== "done"), done = NOTES.filter((n) => n.status === "done");
  const ask = open.filter((n) => n.to === "claude");
  const one = (n) => '<div class="note' + (n.status === "done" ? " done" : "") + '"><div class="hd"><b>#' + n.id + "</b><span>" + (n.a != null ? fmt(n.a) + "–" + fmt(n.b) : fmt(n.t)) + "</span>" +
    (n.ref && n.ref.label ? "<span>" + esc(n.ref.label) + "</span>" : "") + (n.to === "claude" ? '<span class="chip">请 Claude</span>' : '<span class="chip">给自己</span>') + '<span class="spacer"></span><span>' + esc(n.created || "") + "</span></div>" +
    '<div class="tx">' + esc(n.text) + "</div>" + (n.reply ? '<div class="rp">' + esc(n.reply) + "</div>" : "") +
    '<div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm" data-nt="go" data-id="' + n.id + '">跳过去</button>' + (RO ? "" :
      '<button class="btn sm" data-nt="' + (n.status === "done" ? "reopen" : "done") + '" data-id="' + n.id + '">' + (n.status === "done" ? "重开" : "完成") + '</button><button class="btn sm" data-nt="del" data-id="' + n.id + '">删除</button>') + "</div></div>";
  el.innerHTML = '<div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm" id="ntAdd"' + (RO ? " disabled" : "") + '>＋ 在播放头留言</button><button class="btn sm" id="ntCopy"' + (ask.length ? "" : " disabled") + ">复制给 Claude（" + ask.length + "）</button></div>" +
    '<p class="hint">标「请 Claude」的留言，在对话里说「<b>看 Studio 留言</b>」，Claude 会逐条处理并回覆在这里。时间轴上方蓝色小方块就是留言。</p>' +
    (open.length ? open.map(one).join("") : '<p class="empty">还没有留言。</p>') + (done.length ? "<h3>已完成</h3>" + done.map(one).join("") : "");
  $("ntAdd").onclick = addNote;
  $("ntCopy").onclick = () => {
    const txt = "请处理 Studio 留言（aaaai-editor）：项目 " + (P.dir || P.name) + "\n" + ask.map((n) => "#" + n.id + " 成片 " + (n.a != null ? fmt(n.a) + "–" + fmt(n.b) : fmt(n.t)) + (n.ref && n.ref.label ? "（" + n.ref.label + "）" : "") + "：" + n.text).join("\n") +
      "\n（处理完用 aaaai-editor notes <项目> --reply 编号 \"做了什么\" --done-too 回覆）";
    navigator.clipboard.writeText(txt).then(() => toast("已复制，贴进对话就行。"), () => toast("复制不了，请手动选取。", true));
  };
}
$("pane-nt").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-nt]"); if (!b) return;
  const id = +b.dataset.id, n = NOTES.find((x) => x.id === id), act = b.dataset.nt;
  if (act === "go") { seek((n.a != null ? n.a : n.t) + 0.01); if (n.ref && n.ref.k && findSel(n.ref)) select({ k: n.ref.k, i: n.ref.i }); return; }
  try {
    const body = { p: P.id, action: "change", id };
    if (act === "done") body.status = "done"; if (act === "reopen") body.status = "open"; if (act === "del") body.delete = true;
    setNotes(await api("api/notes", body));
  } catch (err) { toast("没改成：" + err.message, true); }
});

// ------------------------------------------------------------------ 风格总览：同一张字卡、同一个画面，所有风格并排
async function styleOverview() {
  if (!P || !P.source_ok) return;
  let v = visibleCards().find((x) => x.k === "ov" && SCHEMA.true_look.includes(x.o.type));
  if (!v) {   // 播放头没有字卡：跳到第一张能看真样子的字卡
    const i = (S.sb.overlays || []).findIndex((o) => SCHEMA.true_look.includes(o.type) && Array.isArray(o.t));
    if (i < 0) { toast("这支片还没有能预览的字卡（标题、数据、清单…）。"); return; }
    seek(+S.sb.overlays[i].t[0] + Math.min(1, (S.sb.overlays[i].t[1] - S.sb.overlays[i].t[0]) / 2));
    await new Promise((r) => setTimeout(r, 400));
    v = { k: "ov", i, o: S.sb.overlays[i] };
  }
  await flushSave();
  let bg = "";
  try { const c = document.createElement("canvas"); c.width = 360; c.height = Math.round(360 * P.H / P.W); c.getContext("2d").drawImage(video, 0, 0, c.width, c.height); bg = c.toDataURL("image/jpeg", 0.8); } catch (_) {}
  const names = Object.keys(P.styles), cur = S.sb.style || "";
  modal('<h2>风格总览</h2><p class="hint">同一张字卡（' + esc(((SCHEMA.cards[v.o.type] || {}).name || v.o.type)) + "）、同一个画面，每种风格的真样子。点一个就换成那个风格（整支片）。</p>" +
    '<div class="styles" style="--ar:' + P.W + " / " + P.H + '">' + names.map((n) => '<button data-a="st:' + esc(n) + '" class="' + (n === cur ? "cur" : "") + '"><div class="cv" style="background-image:url(' + bg + ')"><img alt="" id="sty_' + esc(n) + '"></div><div class="nm">' + esc(n) + (P.styles[n].desc ? ' <span class="hint">' + esc(P.styles[n].desc).slice(0, 18) + "</span>" : "") + "</div></button>").join("") + "</div>" +
    '<div class="acts"><button class="btn primary" data-a="close">关闭</button></div>', (a) => {
    if (!a.startsWith("st:")) return;
    const before = snap(); S.sb.style = a.slice(3); commit(before); $("styleSel").value = S.sb.style; PNG.clear();
    toast("整支片换成 " + S.sb.style + " 风格。", false, [["复原", undo]]);
  }, true);
  for (const n of names) {   // 一张张向引擎要（有缓存，第二次很快）
    if ($("modal").hidden) break;
    try {
      const r = await api("api/card", { p: P.id, overlay: Object.assign({}, v.o, { style: n }), height: 640 });
      const img = $("sty_" + n); if (img) img.src = r.url;
    } catch (_) {}
  }
}
$("styleAll").onclick = styleOverview;

// ------------------------------------------------------------------ 封面与图卡
async function renderCover() {
  const el = $("pane-cov"); if (!S || el.hidden) return;
  if (document.activeElement && el.contains(document.activeElement)) return;
  let pics = [], cards = [];
  try { pics = (await api("api/pictures?p=" + encodeURIComponent(P.id))).pictures; } catch (_) {}
  try { cards = (await api("api/cardlist?p=" + encodeURIComponent(P.id))).cards; } catch (_) {}
  const cv = S.sb.cover || {};
  el.innerHTML = '<fieldset><legend>封面</legend>' +
    '<div class="row2">' + sfield("cover.at", "画面（成片秒）", "num") + '<div class="field"><label>&nbsp;</label><button class="btn sm" id="covNow"' + (RO ? " disabled" : "") + ">用播放头的画面</button></div></div>" +
    sfield("cover.title", "大标题（用 | 自己断行）", "text") + sfield("cover.kicker", "小标签", "text") + sfield("cover.sub", "第三行说明", "text") +
    sfield("cover.layout", "版式", "select", [["", "招牌版（默认）"], ["center", "居中简洁版"]]) +
    '<button class="btn primary sm" id="covGo"' + (RO || !cv.title || cv.at == null ? " disabled" : "") + ">做封面</button>" +
    (cv.title && cv.at != null ? "" : '<p class="hint">先选画面（播放到满意的地方按「用播放头的画面」）并填大标题。背景取原片干净的那一帧，没有字幕和卡片。</p>') + "</fieldset>" +
    '<fieldset><legend>图卡（把字卡出成静态图，发图文用）</legend>' +
    (cards.length ? cards.map((c) => '<label class="it" style="display:flex;gap:8px"><input type="checkbox" class="cpk" value="' + c.n + '" checked><span>' + c.n + ". " + esc((SCHEMA.cards[c.type] || {}).name || c.type) + "　" + esc(c.text) + "</span></label>").join("") : '<p class="hint">这支片还没有能出图卡的字卡。</p>') +
    '<div class="row2"><div class="field"><label for="cpBg">背景</label><select id="cpBg"><option value="frame">原片干净帧</option><option value="blur">模糊帧</option><option value="solid">纯色</option></select></div>' +
    '<div class="field"><label for="cpSize">尺寸</label><select id="cpSize"><option value="1350">1080×1350（小红书／IG）</option><option value="1080">1080×1080</option><option value="1920">1080×1920</option></select></div></div>' +
    '<button class="btn primary sm" id="cpGo"' + (RO || !cards.length ? " disabled" : "") + ">出图卡</button></fieldset>" +
    (pics.length ? "<h3>项目里的封面与图卡</h3><div class=\"pics\">" + pics.map((x) => '<a href="' + esc(x.url) + '" target="_blank" rel="noopener" title="' + esc(x.name) + '"><img alt="' + esc(x.name) + '" src="' + esc(x.url) + '"></a>').join("") + "</div>" : "");
  const n = $("covNow"); if (n) n.onclick = () => { const before = snap(); setPath(S.sb, "cover.at", r2(tOut)); commit(before); renderCover(); };
  const g = $("covGo"); if (g) g.onclick = () => startJob({ kind: "cover" });
  const c = $("cpGo"); if (c) c.onclick = () => startJob({ kind: "cardpics", pick: [...el.querySelectorAll(".cpk:checked")].map((x) => +x.value), bg: $("cpBg").value, size: $("cpSize").value });
}

// ------------------------------------------------------------------ 历史版本
async function openHistory(which) {
  which = which || "sb";
  let items = [];
  try { items = (await api("api/history?p=" + encodeURIComponent(P.id) + "&which=" + which)).items; } catch (e) { toast("读不到历史：" + e.message, true); return; }
  const SRC = { studio: "界面", claude: "对话", "原样": "最早的样子", cover: "封面", tidy: "清口误", hook: "开头钩子", edit: "命令", engine: "引擎", test: "测试", captions: "字幕", align: "对时" };
  modal("<h2>历史版本</h2><div style=\"display:flex;gap:6px\"><button class=\"btn sm" + (which === "sb" ? " primary" : "") + "\" data-a=\"sb\">剪辑表</button><button class=\"btn sm" + (which === "cap" ? " primary" : "") + "\" data-a=\"cap\">字幕轨</button></div>" +
    '<p class="hint">每次存档都会留一份（最近 100 份）。回到某一版＝把那一版存成最新版本，之后还能复原。</p>' +
    (items.length ? '<div class="hist">' + items.map((x, k) => "<span>" + esc(x.time) + '</span><span class="src">' + esc(SRC[x.source] || x.source) + '</span><span class="hint">' + esc(x.version) + '</span><button class="btn sm" data-a="r' + k + '"' + (RO ? " disabled" : "") + ">回到这版</button>").join("") + "</div>" : '<p class="empty">还没有历史版本（这个功能装好之后的修改才会留）。</p>') +
    '<div class="acts"><button class="btn primary" data-a="close">关闭</button></div>', async (a) => {
    if (a === "sb" || a === "cap") { openHistory(a); return; }
    if (!a.startsWith("r")) return;
    const x = items[+a.slice(1)];
    try {
      const r = await api("api/history?p=" + encodeURIComponent(P.id) + "&which=" + which + "&name=" + encodeURIComponent(x.name));
      const before = snap();
      if (which === "cap") S.cap = r.content; else S.sb = r.content;
      commit(before); PNG.clear();
      toast("回到 " + x.time + " 的版本了。", false, [["复原", undo]], 8000);
    } catch (e) { toast("没回去：" + e.message, true); }
  }, true);
}

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
    el.innerHTML = '<p class="hint">检查字幕对时（静音时还挂着字、讲话前就出字、话尾被切）、字幕太长、字卡压到脸、成片响度，以及频道档案里能自动检查的规则。问题会在时间轴上标红点，点一下跳过去。</p><button class="btn primary" id="runChk"' + (P && P.source_ok ? "" : " disabled") + ">开始体检</button>" + issuesHTML() + rulesHTML();
    $("runChk").onclick = () => renderChecks(true);
    if (!RULES) api("api/rules?p=" + encodeURIComponent(P.id)).then((r) => { RULES = r; if (!$("pane-chk").hidden && !el.contains(document.activeElement)) renderChecks(false); }).catch(() => { RULES = { files: [] }; });
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
function rulesHTML() {
  if (!RULES) return "";
  if (!RULES.files.length) return '<p class="hint">没有设定频道档案（aaaai-editor config --set profile=名字）；有的话这里会列出你的剪辑规则。</p>';
  const ck = Object.keys(RULES.checks || {});
  return '<details class="rules"><summary class="hint" style="cursor:pointer">频道规则（' + esc(RULES.profile) + "）" + (ck.length ? "：会自动检查 " + ck.length + " 项" : "") + "</summary>" +
    RULES.files.map((f) => '<p class="hint" style="margin:6px 0 4px">' + esc(f.name) + "</p><pre>" + esc(f.text) + "</pre>").join("") + "</details>";
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
  $("cardMenu").innerHTML += '<div class="grp">配方（一组卡＋推近；真样子要渲染）</div>' + (SCHEMA.new_recipes || []).map(([n, _d, hint]) =>
    '<button data-r="' + esc(n) + '">' + esc(n) + "<small>" + esc(hint) + "</small></button>").join("");
  const snd = OPT ? OPT.sounds : ["pop", "ding", "whoosh", "coin"];
  const sname = (x) => ((SCHEMA.common.find((c) => c.key === "sfx") || { options: [] }).options.find((y) => y[0] === x) || [x, x])[1];
  $("fxMenu").innerHTML = '<div class="grp">画面</div><button data-fx="zoom">推近<small>这段画面慢慢放大</small></button><button data-fx="punch">瞬切推近<small>重点落下时冲一下</small></button><button data-fx="confetti">彩带<small>庆祝时刻</small></button><button data-fx="blur">打码（模糊）<small>遮车牌、个资</small></button><button data-fx="mosaic">马赛克<small>遮车牌、个资</small></button>' +
    '<div class="grp">音效</div>' + snd.map((x) => '<button data-snd="' + esc(x) + '">' + esc(sname(x)) + "<small>" + esc(x) + "</small></button>").join("");
}
function menuToggle(btn, menu) {
  $(btn).onclick = (e) => { e.stopPropagation(); if (RO) return; buildMenus(); const m = $(menu), open = m.hidden; $("cardMenu").hidden = true; $("fxMenu").hidden = true; m.hidden = !open; if (open) { const f = m.querySelector("button"); if (f) f.focus(); } };
}
menuToggle("addCardBtn", "cardMenu"); menuToggle("addFxBtn", "fxMenu");
document.addEventListener("click", () => { $("cardMenu").hidden = true; $("fxMenu").hidden = true; });
function startAt(len) { const a = r2(Math.max(0, Math.min(tOut, T.dur - 0.5))); return [a, r2(Math.min(T.dur, a + len))]; }
$("cardMenu").addEventListener("click", (e) => {
  const rb = e.target.closest("button[data-r]");
  if (rb) {
    const n = rb.dataset.r, data = SCHEMA.new_recipes.find((x) => x[0] === n)[1], before = snap();
    (S.sb.recipes = S.sb.recipes || []).push(Object.assign({ use: n, t: startAt((SCHEMA.new_len || {})[n] || 4) }, clone(data)));
    sel = { k: "rc", i: S.sb.recipes.length - 1 }; multi = [];
    commit(before); showPane("insp");
    toast("加了配方 " + n + "：右边改内容，按「渲染这一段」看真样子。", false, [["复原", undo]]);
    return;
  }
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
  else if (b.dataset.fx === "blur" || b.dataset.fx === "mosaic") { (S.sb.overlays = S.sb.overlays || []).push(Object.assign({ type: "blur", t: startAt(3), box: BLUR_BOX.slice() }, b.dataset.fx === "mosaic" ? { mode: "mosaic" } : {})); sel = { k: "ov", i: S.sb.overlays.length - 1 }; toast("画面上拖框盖住要遮的地方，拉右下角改大小。"); }
  else if (b.dataset.fx === "confetti") { (S.sb.overlays = S.sb.overlays || []).push({ type: "confetti", t: startAt(2.6) }); sel = { k: "ov", i: S.sb.overlays.length - 1 }; }
  else { const punch = b.dataset.fx === "punch"; (S.sb.zooms = S.sb.zooms || []).push(Object.assign({ t: startAt(punch ? 0.6 : 2.5), to: punch ? 1.14 : 1.12 }, punch ? { style: "punch" } : {})); sel = { k: "zm", i: S.sb.zooms.length - 1 }; }
  commit(before); showPane("insp");
});
function splitAtPlayhead() {
  if (RO) return;
  const m = T.toSrc(tOut), c = T.cuts[m.i];
  if (!c || m.src - c[0] < 0.2 || c[1] - m.src < 0.2) { toast("播放头太靠近这一段的头尾，换个位置再切。"); return; }
  const before = snap();
  S.sb.cuts = T.cuts.flatMap((x, j) => (j === m.i ? [[x[0], r3(m.src)], [r3(m.src), x[1]]] : [x]));
  sel = { k: "cut", i: m.i + 1 }; commit(before);
  toast("在原片 " + fmt(m.src) + " 切开了。选中多余的一段按 Delete 就能剪掉。");
}
$("splitBtn").onclick = splitAtPlayhead;
function playRange(a, b) {   // 剪点试听：从 a 播到 b 自己停（会开声音）
  if (!video.src) { toast("播放用的影片还在准备中。"); return; }
  if (playing) togglePlay();
  video.muted = false; $("mute").textContent = "🔊";
  seek(Math.max(0, a)); stopAt = Math.min(T.dur, b); togglePlay();
}
function deleteSel() {
  if (RO || !sel) return;
  if (multi.length > 1) { deleteMulti(); return; }
  if (sel.k === "cap") { cutPiece(sel.i); return; }
  if (sel.k === "cut") {
    if (T.cuts.length < 2) { toast("至少要留一段画面。"); return; }
    const c = T.cuts[sel.i]; sel = null;
    recut({ remove: [c] }, (r) => "剪掉这一段画面（" + r.saved.toFixed(1) + " 秒），后面的字卡已跟着往前。");
    return;
  }
  const key = { ov: "overlays", rc: "recipes", zm: "zooms", sx: "sfx" }[sel.k];
  if (!key || !(S.sb[key] || [])[sel.i]) return;
  const before = snap(), what = { ov: "字卡", rc: "配方", zm: "推近", sx: "音效" }[sel.k];
  S.sb[key].splice(sel.i, 1); sel = null;
  commit(before);
  toast("删掉了这个" + what + "。", false, [["复原", undo]]);
}
$("delBtn").onclick = deleteSel;
function deleteMulti() {
  const before = snap(), key = { ov: "overlays", rc: "recipes", zm: "zooms", sx: "sfx" };
  const n = multi.length;
  for (const m of [...multi].sort((x, y) => y.i - x.i)) { const L = S.sb[key[m.k]]; if (L && L[m.i]) L.splice(m.i, 1); }
  multi = []; sel = null; commit(before);
  toast("删掉了 " + n + " 个。", false, [["复原", undo]]);
}
function renderMulti(el) {
  const items = multi.map((m) => ({ m, o: findSel(m) })).filter((x) => x.o);
  const ovs = items.filter((x) => x.m.k === "ov");
  let h = "<h3>已选 " + items.length + " 个</h3><p class=\"hint\">Shift／⌘ 点时间轴上的块加选或减选；拖其中一个，整组一起移。下面改的会套用到选中的每一张字卡（留空＝不改）。</p>";
  if (ovs.length && !RO) {
    h += "<fieldset><legend>套用到 " + ovs.length + " 张字卡</legend>";
    for (const f of SCHEMA.common) {
      const opts = f.kind === "bool" ? [["", "不改"], ["true", "是"], ["false", "否"], ["__del", "还原默认"]] : f.kind === "select" ? [["", "不改"]].concat(f.options.filter((x) => x[0] !== "")).concat([["__del", "还原默认"]]) : null;
      h += opts ? '<div class="field"><label>' + esc(f.label) + '</label><select data-mk="' + f.key + '" data-bool="' + (f.kind === "bool" ? 1 : "") + '">' + opts.map((x) => '<option value="' + esc(x[0]) + '">' + esc(x[1]) + "</option>").join("") + "</select></div>"
        : '<div class="field"><label>' + esc(f.label) + '（留空不改）</label><input type="number" step="any" data-mk="' + f.key + '"></div>';
    }
    h += "</fieldset>";
  }
  if (!RO) h += '<div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm" data-shift="-0.1">整组往前 0.1 秒</button><button class="btn sm" data-shift="0.1">往后 0.1 秒</button><button class="btn danger sm" id="mDel">全部删除</button></div>';
  el.innerHTML = h;
  el.querySelectorAll("[data-mk]").forEach((x) => x.addEventListener("change", () => {
    if (x.value === "") return;
    const before = snap(), key = x.dataset.mk;
    for (const { o } of ovs) {
      if (x.value === "__del") delete o[key];
      else o[key] = x.dataset.bool ? x.value === "true" : x.type === "number" ? parseFloat(x.value) : x.value;
    }
    commit(before); toast("已套用到 " + ovs.length + " 张字卡。", false, [["复原", undo]]);
  }));
  el.querySelectorAll("[data-shift]").forEach((x) => x.addEventListener("click", () => {
    const before = snap(), dt = +x.dataset.shift;
    for (const { o } of items) o.t = Array.isArray(o.t) ? [r2(Math.max(0, +o.t[0] + dt)), r2(Math.max(0.3, +o.t[1] + dt))] : r2(Math.max(0, +o.t + dt));
    commit(before);
  }));
  const md_ = $("mDel"); if (md_) md_.onclick = deleteMulti;
}

// ------------------------------------------------------------------ 画面上拖拉：移位置、放大缩小（写进 xy、scale）
let cdragJustEnded = false;
function startCanvasDrag(e, mode) {
  const o = findSel(), bx = o && boxOf(o);
  if (RO || !o || !bx) return false;
  const r = stage.getBoundingClientRect();
  cdrag = { mode, o, box: bx, blur: o.type === "blur", sx: e.clientX, sy: e.clientY, W: r.width, H: r.height, before: snap(), s0: +(o.scale || 1), k: 1, moved: false };
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
  const img = $("truelook").querySelector('img[data-i="' + sel.i + '"]') || (cdrag.blur ? layer.querySelector('.blurbox[data-i="' + sel.i + '"]') : null), sb_ = $("selbox"), b = cdrag.box;
  if (cdrag.blur && cdrag.mode !== "move") {   // 打码：宽、高分开拉
    cdrag.nw = Math.max(0.03, Math.min(1 - b[0], b[2] + dx / cdrag.W)); cdrag.nh = Math.max(0.02, Math.min(1 - b[1], b[3] + dy / cdrag.H));
    for (const el_ of [img, sb_]) if (el_) { el_.style.width = cdrag.nw * 100 + "%"; el_.style.height = cdrag.nh * 100 + "%"; }
    return;
  }
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
    if (d.blur) {
      const nx = d.mode === "move" ? b[0] + (e.clientX - d.sx) / d.W : b[0], ny = d.mode === "move" ? b[1] + (e.clientY - d.sy) / d.H : b[1];
      const nw = d.mode === "move" ? b[2] : d.nw, nh = d.mode === "move" ? b[3] : d.nh;
      d.o.box = [r3(Math.max(0, Math.min(1 - nw, nx))), r3(Math.max(0, Math.min(1 - nh, ny))), r3(nw), r3(nh)];
    } else if (d.mode === "move") {
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
    if (body.kind === "cover" || body.kind === "cardpics") {
      const pics = done.result || [];
      modal("<h2>" + (body.kind === "cover" ? "封面" : "图卡") + '做好了　<span class="hint">' + done.elapsed + " 秒</span></h2><div class=\"pics\">" + pics.map((u) => '<a href="' + esc(u) + '" target="_blank" rel="noopener"><img alt="" src="' + esc(u) + '"></a>').join("") +
        '</div><p class="hint">在项目的 out/ 文件夹，也复制了一份到「成品」。' + (body.kind === "cover" ? "竖版会出 Reels 全画面与主页 4:5 两种。" : "") + '</p><div class="acts"><button class="btn primary" data-a="close">好</button></div>', null, true);
      renderCover(); return;
    }
    if (body.kind === "audition") { playResult(done.result, "试听（真正的混音与响度）", done.elapsed); return; }
    if (body.kind === "range") playResult(done.result, "这一段的成品画面（预览画质）", done.elapsed);
    else if (body.kind === "variant") toast(body.w + "×" + body.h + " 版出好了（" + done.elapsed + " 秒）", false, [["播放", () => playResult(done.result, body.w + "×" + body.h + " 版", null)]], 12000);
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
const SIZES = [[1080, 1920, "9:16 竖版（Reels／抖音／Shorts）"], [1080, 1350, "4:5（IG／小红书 动态）"], [1080, 1080, "1:1 方形"], [1920, 1080, "16:9 横版（YouTube）"]];
$("export").onclick = () => {
  const portrait = P.H > P.W;
  const opts = SIZES.filter(([w, h]) => !(w === P.W && h === P.H)).map(([w, h, lb]) => {
    const bad = portrait && w > h;   // 竖版原片出横版：会裁掉大半个画面
    return '<label style="display:flex;gap:8px;align-items:center"><input type="checkbox" class="vsz" value="' + w + "x" + h + '"' + (bad ? " disabled" : "") + "> " + esc(lb) + (bad ? ' <span class="hint">（竖版片不适合，会裁掉大半）</span>' : "") + "</label>";
  }).join("");
  modal('<h2>出片</h2><p class="hint">按目前的剪辑表出正式成片（' + fmt(T.dur) + "，" + P.W + "×" + P.H + "），覆盖 out/final.mp4。长片要几分钟，进度在上方；可以取消。</p>" +
    "<b>另外再出（选填）</b>" + opts + '<p class="hint">其他尺寸会裁切画面（字卡、字幕按比例重新排），另存成 out/final_宽x高.mp4，成品文件夹的名字加尺寸后缀，不会盖掉主版本。一个接一个出。</p>' +
    '<div class="acts"><button class="btn" data-a="no">先不要</button><button class="btn primary" data-a="go">出片</button></div>', async (a) => {
    if (a !== "go") return;
    const extra = [...document.querySelectorAll(".vsz:checked")].map((x) => x.value.split("x").map(Number));
    await startJob({ kind: "final", duration: T.dur });
    for (const [w, h] of extra) { if (!P) break; await startJob({ kind: "variant", w, h, duration: T.dur }); }
  });
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
let modalGen = 0;
function modal(html, onAct, wide) {
  const m = $("modal"), box = $("modalBox"), gen = ++modalGen;
  box.className = "box" + (wide ? " wide" : ""); box.innerHTML = html; m.hidden = false;
  const close = () => { m.hidden = true; box.innerHTML = ""; document.removeEventListener("keydown", esc_); };
  const esc_ = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", esc_);
  // 先做动作（这时表单还在、读得到），再关；动作自己开了新的对话框（下一步、重新整理）就不关
  box.onclick = (e) => { const b = e.target.closest("[data-a]"); if (!b) return; const a = b.dataset.a; if (onAct) onAct(a); if (a !== "copy" && gen === modalGen) close(); };
  m.onclick = (e) => { if (e.target === m) close(); };
  const f = box.querySelector(".primary, button"); if (f) f.focus();
}
function help() {
  const k = [["空格", "播放／暂停"], ["← →", "前后一格（加 Shift＝一秒）"], ["Alt＋方向键", "微调选中字卡的位置（加 Shift＝大步）"], ["G", "安全区开关"], ["S", "在播放头切开画面"], ["N", "在播放头留言（可以请 Claude 处理）"], ["Shift／⌘＋点", "多选字卡与特效（整组拖、一起改）"], ["⌘Z／Ctrl+Z", "复原"], ["⇧⌘Z／Ctrl+Y", "重做"], ["R", "渲染这一段（选中的或播放头前后）"], ["Delete", "删除选中的字卡／特效；选中字幕＝把那句剪掉"], ["Esc", "取消选取"], ["M", "声音开关"], ["+ −", "时间轴放大缩小"], ["?", "这张表"]];
  modal('<h2>快捷键</h2><div class="keys">' + k.map((x) => '<span class="kbd">' + esc(x[0]) + "</span><span>" + esc(x[1]) + "</span>").join("") + '</div><p class="hint">画面上的字卡是近似样子，停下来会换成引擎的真样子；动态、转场、组合卡以「渲染这一段」为准。</p>' +
    '<div class="acts"><button class="btn" data-a="hist">历史版本</button><button class="btn" data-a="tour">再看一次导览</button><button class="btn" data-a="diag">诊断报告</button><button class="btn primary" data-a="close">好</button></div>', (a) => { if (a === "diag") diag(); if (a === "tour") tour(0); if (a === "hist") openHistory("sb"); });
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
  else if (e.key === "s" || e.key === "S") splitAtPlayhead();
  else if (e.key === "n" || e.key === "N") { e.preventDefault(); addNote(); }
  else if (e.key === "Escape") { multi = []; select(null); }
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
