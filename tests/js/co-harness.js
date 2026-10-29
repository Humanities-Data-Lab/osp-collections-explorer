"use strict";
/* Loads build/templates/coauthor.js inside a vm context with a stub page whose ids mirror render.py's coauthor_page(). */
const { Doc, makeTimers, loadScript } = require("./dom");

const VOLS = ["Vol A", "Vol B"], TOPICS = ["Open Access", "Data"], KINDS = ["Article", "Book"];

function it(id, a, y, v, t, k, n) { return { id, a, y, v: v || ["Vol A"], t: t || [], k: k || "Article", n: n === undefined ? "Title " + id : n }; }

function makeCo(opts) {
  opts = opts || {};
  const items = opts.items || [];
  const doc = new Doc();
  const timers = makeTimers();
  const hist = [];
  const loc = { search: opts.search || "", pathname: "/coauthorship.html", protocol: "https:" };
  const history = { replaceState(_s, _t, url) { if (opts.replaceThrows) { throw new Error("SecurityError"); } hist.push(url); } };

  const data = doc.add("co-data", "script");
  data.textContent = JSON.stringify({ items });
  ["network", "t-people", "t-ties", "t-groups", "t-per", "panel", "co-status", "find-note",
    "m-items", "m-multi", "m-authors", "m-ties", "m-groups", "m-largest"].forEach((id) => doc.add(id, id === "network" || id.startsWith("t-") || id === "panel" ? "div" : "p"));
  const reset = doc.add("co-reset", "button");

  const boxes = {};
  [["Volume", VOLS], ["Topic", TOPICS], ["Type", KINDS]].forEach(([name, vals]) => {
    boxes[name] = vals.map((v) => doc.control("input", { checked: false, value: v }, { type: "checkbox", name }));
  });
  function field(id, tag, type, value) {
    const e = doc.control(tag, { value: value || "" }, type ? { type, id } : { id });
    if (tag === "select") { e.type = "select-one"; }
    doc.registry[id] = e;
    return e;
  }
  const yfrom = field("yfrom", "input", "number"), yto = field("yto", "input", "number");
  const tie = field("tie", "select", null, "1"), group = field("group", "select", null, "3");
  const find = field("find", "input", "text");
  const only = field("only", "input", "checkbox"); only.checked = false;

  const { ctx, api } = loadScript("coauthor.js", {
    document: doc, location: loc, history,
    setTimeout: timers.setTimeout, clearTimeout: timers.clearTimeout,
  });
  return {
    doc, ctx, api, timers, hist, loc, reset, boxes, yfrom, yto, tie, group, find, only,
    el: (id) => doc.getElementById(id), st: () => api.getState(), view: () => api.getView(),
  };
}

/* make a click event on a stub element carrying attributes, as the page's buttons and circles do */
function clickOn(h, attrs, extra) {
  const e = h.doc.createElement(extra && extra.tag || "button");
  Object.keys(attrs).forEach((k) => e.setAttribute(k, attrs[k]));
  return h.doc.dispatch("click", { target: e });
}

module.exports = { makeCo, it, clickOn, VOLS, TOPICS, KINDS };
