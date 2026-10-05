// Studio 界面语言（中文／English）。
// 做法：界面照常用中文产生，选 English 时把画面上的文字逐段翻成英文（对照表在 i18n-data.js）。
// 不翻：使用者自己写的内容（字幕、字卡文字、留言、项目名、输入框）。换语言＝重新整理页面（修改都已自动存档）。
"use strict";
(function () {
  const KEY = "aaaai-studio-lang";
  let lang = "zh";
  try { lang = localStorage.getItem(KEY) || "zh"; } catch (_) {}
  if (lang !== "en") lang = "zh";
  window.STUDIO_LANG = lang;
  document.documentElement.lang = lang === "en" ? "en" : "zh-Hans";

  window.setStudioLang = function (l) {
    try { localStorage.setItem(KEY, l); } catch (_) {}
    const go = () => location.reload();
    if (typeof window.flushSave === "function") window.flushSave().finally(go); else go();
  };
  if (lang !== "en") return;

  const D = window.STUDIO_I18N || { dict: {}, full: {}, patterns: [], punct: {} };
  const PAT = D.patterns.map(([re, to]) => [new RegExp(re), to]);
  const CJK = /[㐀-䶿一-鿿]/;
  const RUN = /[㐀-䶿一-鿿]+|[　-〿＀-￯…·—]|[^㐀-䶿一-鿿　-〿＀-￯…·—]+/g;
  // 使用者内容：不翻
  const SKIP = "textarea, input, script, style, pre, .tx, .card, .cap, .pcard .nm, .note .tx, .note .rp, .asset .nm, #projName, .tl-block.cap, .hist .src + span, [data-noi18n]";
  const HEAD_ONLY = ".tl-block.ov, .tl-block.rc";   // 时间轴字卡：只翻前面的种类名，后面是使用者的字

  function joinSmart(parts) {
    let out = "";
    for (let p of parts) {
      if (!p) continue;
      if (out && /[A-Za-z0-9)%”×]$/.test(out) && /^[A-Za-z0-9(“#]/.test(p)) out += " ";
      out += p;
    }
    return out.replace(/ {2,}/g, " ").replace(/ ([,.;:!?)])/g, "$1").replace(/\( /g, "(");
  }
  function cap(s) {
    return s.replace(/^(\s*)([a-z])/, (m, a, b) => a + b.toUpperCase()).replace(/([.!?]\s+)([a-z])/g, (m, a, b) => a + b.toUpperCase());
  }
  function tr(s, first) {
    if (first === undefined) first = true;
    if (!s || !CJK.test(s)) return s;
    const lead = s.match(/^\s*/)[0], tail = s.match(/\s*$/)[0], core = s.trim();
    if (D.full[core] !== undefined) return lead + D.full[core] + tail;
    for (const [re, to] of PAT) {   // 句型：$1＝原样保留（使用者的字），{t1}＝那一段再翻译
      const m = core.match(re);
      if (m) return lead + to.replace(/\$(\d)/g, (_, k) => m[+k] || "").replace(/\{t(\d)\}/g, (_, k) => (m[+k] ? tr(m[+k]) : "")) + core.slice(m.index + m[0].length) + tail;
    }
    const parts = core.match(RUN) || [];
    const outp = parts.map((p) => {
      if (CJK.test(p)) return D.dict[p] !== undefined ? D.dict[p] : p;
      if (D.punct[p] !== undefined) return D.punct[p];
      return p;
    });
    let out = joinSmart(outp).trim();
    if (first) out = cap(out);
    else out = out.replace(/^([A-Z])([a-z]{2,})\b/, (m, a, b) => a.toLowerCase() + b);   // 句子中间：「Cards」→「cards」
    return lead + out + tail;
  }
  window.studioTr = tr;

  const done = new WeakMap();   // 已翻过的文字节点 → 翻好的值（避免重复翻、把使用者的字翻坏）
  const INLINE = /^(B|STRONG|EM|I|SPAN|A|SMALL|KBD|MARK|U)$/;
  function prevText(n) {   // 往前找相邻的文字（跳过空白；行内元素里没有前文时看外层）
    let p = n.previousSibling;
    while (p && p.nodeType === 3 && !p.nodeValue.trim()) p = p.previousSibling;
    if (!p && n.parentElement && INLINE.test(n.parentElement.tagName)) return prevText(n.parentElement);
    return p;
  }
  function isFirst(n) {   // 是不是句子开头：前面没有文字、前面是图标或换行、或前一段以句号之类结尾
    const p = prevText(n);
    if (!p) return true;
    if (p.nodeType === 1 && (p.tagName === "BR" || !(p.textContent || "").trim())) return true;
    return /[.!?:：。！？]\s*$/.test(p.textContent || "");
  }
  function needSpace(n, t) {   // 和前一段英文之间补空格
    const p = prevText(n);
    return !!(p && /[A-Za-z0-9)”%]$/.test(p.textContent || "") && /^[A-Za-z0-9(“#]/.test(t));
  }
  const BLOCK = "p, .hint, .empty, .tour p";
  function doBlock(el) {   // 整段（含粗体等）有现成翻译就整段换掉
    if (!D.blocks || el.dataset.i18n) return false;
    const k = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (D.blocks[k] === undefined) return false;
    el.innerHTML = D.blocks[k]; el.dataset.i18n = "1";
    return true;
  }
  function doText(n) {
    const el = n.parentElement;
    if (!el || el.closest(SKIP)) return;
    const v = n.nodeValue;
    if (!CJK.test(v) || done.get(n) === v) return;
    const h = el.closest(HEAD_ONLY);
    if (h) {   // 「标题卡　活动奖金」：只翻「标题卡」
      const i = v.indexOf("　");
      const head = i >= 0 ? v.slice(0, i) : v, rest = i >= 0 ? v.slice(i) : "";
      const t = tr(head);
      if (t !== head) { n.nodeValue = t + rest; done.set(n, n.nodeValue); }
      return;
    }
    let t = tr(v, isFirst(n));
    if (t !== v && needSpace(n, t.replace(/^\s+/, "")) && !/^\s/.test(t)) t = " " + t;
    if (t !== v) { n.nodeValue = t; done.set(n, t); }
  }
  const doneA = new WeakMap();
  function doAttrs(el) {
    if (el.closest && el.closest("[data-noi18n]")) return;
    const seen = doneA.get(el) || {};
    if (el.matches && el.matches(".tl-block.cap")) return;   // 字幕块的提示＝使用者的字
    const head = el.matches && el.matches(".tl-block.ov, .tl-block.rc");
    for (const a of ["title", "placeholder", "aria-label"]) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v && head && a === "title") {   // 字卡块：只翻种类名
        const i = v.search(/\s/); const h = i >= 0 ? v.slice(0, i) : v; const t = tr(h);
        if (t !== h) el.setAttribute(a, t + (i >= 0 ? v.slice(i) : ""));
        continue;
      }
      if (v && CJK.test(v) && seen[a] !== v) { const t = tr(v); if (t !== v) { el.setAttribute(a, t); seen[a] = t; doneA.set(el, seen); } }
    }
  }
  function walk(root) {
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1) return;
    if (root.matches && root.matches(SKIP) && root.tagName !== "SELECT") { doAttrs(root); return; }
    doAttrs(root);
    if (root.matches && root.matches(BLOCK) && doBlock(root)) return;
    if (root.querySelectorAll) root.querySelectorAll(BLOCK).forEach((b) => { if (!b.closest(SKIP)) doBlock(b); });
    const it = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = it.nextNode())) { if (n.nodeType === 3) doText(n); else doAttrs(n); }
  }
  let busy = false;
  const mo = new MutationObserver((list) => {
    if (busy) return;
    busy = true;
    try {
      for (const m of list) {
        if (m.type === "characterData") doText(m.target);
        else if (m.type === "attributes") doAttrs(m.target);
        else m.addedNodes.forEach(walk);
      }
    } finally { busy = false; }
  });
  function start() {
    walk(document.body);
    mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["title", "placeholder", "aria-label"] });
    document.title = tr(document.title);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
  // 对话框、提示、确认用到的文字
  const _confirm = window.confirm;
  window.confirm = (m) => _confirm(tr(m));
})();
