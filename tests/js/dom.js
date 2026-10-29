"use strict";
/* A tiny hand-written DOM stub and script loader for the browser-script tests.
   Not a general DOM: it supports only what build/templates/app.js and coauthor.js use. */
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const TEMPLATES = path.resolve(__dirname, "..", "..", "build", "templates");

/* ---- selector matching: comma lists of simple selectors (#id, .class, tag, [attr], [attr="v"], tag[attr]) ---- */
function matchesSimple(el, sel) {
  sel = sel.trim();
  const re = /^([a-zA-Z0-9]*)(#[\w-]+)?((?:\.[\w-]+)*)((?:\[[^\]]+\])*)$/;
  const m = re.exec(sel);
  if (!m) { return false; }
  if (m[1] && el.tagName.toLowerCase() !== m[1].toLowerCase()) { return false; }
  if (m[2] && el.id !== m[2].slice(1)) { return false; }
  if (m[3]) {
    for (const c of m[3].split(".").filter(Boolean)) { if (!el.classList.contains(c)) { return false; } }
  }
  if (m[4]) {
    const attrs = m[4].match(/\[[^\]]+\]/g);
    for (const a of attrs) {
      const am = /^\[([\w-]+)(?:="(.*)")?\]$/.exec(a);
      if (!am || !el.hasAttribute(am[1])) { return false; }
      if (am[2] !== undefined && el.getAttribute(am[1]) !== am[2]) { return false; }
    }
  }
  return true;
}
function matches(el, selector) { return selector.split(",").some((s) => matchesSimple(el, s)); }

class ClassList {
  constructor(el) { this.el = el; this.set = new Set(); }
  add(...c) { c.forEach((x) => this.set.add(x)); }
  remove(...c) { c.forEach((x) => this.set.delete(x)); }
  contains(c) { return this.set.has(c); }
  toggle(c, force) { const on = force === undefined ? !this.set.has(c) : force; if (on) { this.set.add(c); } else { this.set.delete(c); } return on; }
}

class El {
  constructor(tag, doc) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = doc;
    this.attrs = {};
    this.children = [];
    this.parent = null;
    this.listeners = {};
    this.classList = new ClassList(this);
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this.textContent = "";
    this._html = "";
    this.focused = 0;
    this.scrolled = 0;
    this.blurred = 0;
  }
  get id() { return this.attrs.id || ""; }
  set id(v) { this.attrs.id = v; }
  get type() { return this.attrs.type || "text"; }
  set type(v) { this.attrs.type = v; }
  get className() { return Array.from(this.classList.set).join(" "); }
  set className(v) { this.classList.set = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get dataset() {
    const out = {};
    Object.keys(this.attrs).forEach((k) => {
      if (k.startsWith("data-")) { out[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = this.attrs[k]; }
    });
    return out;
  }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = String(v); this.children = []; this._cache = null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k); }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  descendants() { const out = []; this.children.forEach((c) => { out.push(c); out.push(...c.descendants()); }); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    if (sel === ".card h3 a") {                 // result links, parsed from the captured innerHTML
      if (!this._cache) {
        this._cache = (this._html.match(/<li class="card"><h3><a [^>]*>/g) || []).map((t) => {
          const a = new El("a", this.ownerDocument); a.setAttribute("href", /href="([^"]*)"/.exec(t)[1]); return a;
        });
      }
      return this._cache;
    }
    return this.descendants().filter((d) => matches(d, sel));
  }
  closest(sel) {
    for (let e = this; e; e = e.parent) { if (matches(e, sel)) { return e; } }
    return null;
  }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type, ev) {
    ev = Object.assign({ type, target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } }, ev || {});
    (this.listeners[type] || []).forEach((fn) => fn(ev));
    return ev;
  }
  focus() { this.focused++; this.ownerDocument.activeElement = this; }
  blur() { this.blurred++; }
  scrollIntoView() { this.scrolled++; }
}

class Doc {
  constructor() {
    this.registry = {};
    this.controls = [];
    this.documentElement = new El("html", this);
    this.activeElement = null;
    this.listeners = {};
    this.keyCache = {};
  }
  createElement(tag) { return new El(tag, this); }
  /* Register an element with an id (what the page markup would provide). */
  add(id, tag, props) {
    const e = new El(tag || "div", this);
    e.id = id;
    Object.assign(e, props || {});
    this.registry[id] = e;
    return e;
  }
  getElementById(id) { return this.registry[id] || null; }
  /* Register a form control for the #co-filters queries. */
  control(tag, props, attrs) {
    const e = new El(tag, this);
    Object.assign(e, props || {});
    Object.keys(attrs || {}).forEach((k) => e.setAttribute(k, attrs[k]));
    this.controls.push(e);
    return e;
  }
  querySelectorAll(sel) {
    if (sel === "#co-filters input, #co-filters select") { return this.controls.slice(); }
    const m = /^input\[name="([^"]+)"\](:checked)?$/.exec(sel);
    if (m) { return this.controls.filter((c) => c.tagName === "INPUT" && c.getAttribute("name") === m[1] && (!m[2] || c.checked)); }
    throw new Error("stub document.querySelectorAll: unsupported selector " + sel);
  }
  querySelector(sel) {
    const m = /^\[(data-[a-z]+)="(.*)"\]$/.exec(sel);
    if (!m) { throw new Error("stub document.querySelector: unsupported selector " + sel); }
    const attr = m[1], key = m[2].replace(/\\"/g, '"');
    const cacheKey = attr + "=" + key;
    const html = (x) => x.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const needle = attr + '="' + html(key) + '"';
    const pool = Object.keys(this.registry).map((k) => this.registry[k]);
    for (const host of pool) {
      const at = host._html.indexOf(needle);
      if (at === -1) { continue; }
      const tagStart = host._html.lastIndexOf("<", at), tagEnd = host._html.indexOf(">", at);
      const tag = host._html.slice(tagStart, tagEnd + 1);
      if (!this.keyCache[cacheKey]) {
        const e = new El(/^<(\w+)/.exec(tag)[1], this); e.setAttribute(attr, key);
        this.keyCache[cacheKey] = e;
      }
      this.keyCache[cacheKey].disabled = /\sdisabled(\s|>)/.test(tag);
      return this.keyCache[cacheKey];
    }
    return null;
  }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type, ev) {
    ev = Object.assign({ type, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } }, ev || {});
    (this.listeners[type] || []).forEach((fn) => fn(ev));
    return ev;
  }
}

/* Fake timers: setTimeout queues, tick() runs everything due. */
function makeTimers() {
  let next = 1;
  const t = { queue: [], cleared: 0 };
  t.setTimeout = (fn, ms) => { const id = next++; t.queue.push({ id, fn, ms: ms || 0 }); return id; };
  t.clearTimeout = (id) => { const i = t.queue.findIndex((q) => q.id === id); if (i !== -1) { t.queue.splice(i, 1); t.cleared++; } };
  t.flush = () => { while (t.queue.length) { const q = t.queue.shift(); q.fn(); } };
  return t;
}

/* Run a template inside a fresh vm context whose globals are the given stubs. The filename is the real file URL so
   that node's coverage report attributes the executed lines to the template. */
function loadScript(file, globals) {
  const full = path.join(TEMPLATES, file);
  const src = fs.readFileSync(full, "utf8");
  const mod = { exports: {} };
  const ctx = vm.createContext(Object.assign({ module: mod, URLSearchParams, console }, globals));
  new vm.Script(src, { filename: pathToFileURL(full).href }).runInContext(ctx);
  return { ctx, api: mod.exports };
}

module.exports = { El, Doc, makeTimers, loadScript, matches, TEMPLATES };
