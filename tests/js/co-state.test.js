"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { makeCo, it } = require("./co-harness");

const ITEMS = [
  it("1", ["Amy", "Bob"], 1995, ["Vol A"], ["Open Access"], "Article"),
  it("2", ["Amy", "Cy"], 2005, ["Vol B"], ["Data"], "Book"),
  it("3", ["Dee", "Eve"], null, ["Vol A", "Vol B"], ["Open Access", "Data"], "Article"),
  it("4", ["Fay"], 2015, ["Vol B"], [], "Book"),
];
const lastQuery = (h) => h.hist[h.hist.length - 1];

test("the script exports nothing and sets the js class when no module object exists", () => {
  const { Doc, makeTimers } = require("./dom");
  const fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
  const doc = new Doc(); const t = makeTimers();
  doc.add("co-data").textContent = JSON.stringify({ items: [] });
  ["network", "t-people", "t-ties", "t-groups", "t-per", "panel", "co-status", "find-note", "m-items", "m-multi", "m-authors", "m-ties", "m-groups", "m-largest", "co-reset", "yfrom", "yto", "tie", "group", "find"].forEach((i) => doc.add(i));
  doc.add("only");
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "build", "templates", "coauthor.js"), "utf8");
  const ctx = vm.createContext({ document: doc, location: { search: "", pathname: "/x" }, history: { replaceState() {} }, URLSearchParams, setTimeout: t.setTimeout, clearTimeout: t.clearTimeout });
  vm.runInContext(src, ctx);                       // no `module` global: must not throw, as in a browser
  assert.ok(doc.documentElement.classList.contains("js"));
  assert.match(doc.getElementById("network").innerHTML, /No authors share an item/);
});

test("readAddress reads every parameter, including repeated Volume, Topic and Type", () => {
  const h = makeCo({ items: ITEMS, search: "?Volume=Vol+A&Volume=Vol+B&Topic=Data&Type=Book&Type=Article&Year_from=1990&Year_to=2010&Tie=2&Group=5&Find=Amy&Only=1" });
  h.api.readAddress();          // the load-time update already cleared sel, as Amy is not in these filters
  const s = h.st();
  assert.deepEqual(s.vol, ["Vol A", "Vol B"]);
  assert.deepEqual(s.topic, ["Data"]);
  assert.deepEqual(s.kind, ["Book", "Article"]);
  assert.equal(s.from, "1990"); assert.equal(s.to, "2010");
  assert.equal(s.tie, 2); assert.equal(s.group, 5);
  assert.equal(s.find, "Amy"); assert.equal(s.only, true); assert.equal(s.sel, "Amy");
});

test("readAddress applies defaults and clamps bad numbers", () => {
  const h = makeCo({ items: ITEMS });
  let s = h.st();
  assert.deepEqual([s.vol, s.topic, s.kind], [[], [], []]);
  assert.deepEqual([s.from, s.to, s.tie, s.group, s.find, s.only, s.sel], ["", "", 1, 3, "", false, ""]);
  h.loc.search = "?Tie=0&Group=1&Only=0";
  h.api.readAddress();
  assert.equal(h.st().tie, 1); assert.equal(h.st().group, 2); assert.equal(h.st().only, false);
  h.loc.search = "?Tie=abc&Group=abc&Tie=7&Group=12";
  h.api.readAddress();
  assert.equal(h.st().tie, 1); assert.equal(h.st().group, 3);   // first value wins; not a number falls back
  h.loc.search = "?Tie=-4&Group=-4";
  h.api.readAddress();
  assert.equal(h.st().tie, 1); assert.equal(h.st().group, 2);
});

test("writeAddress writes only non-default values, in a fixed order", () => {
  const h = makeCo({ items: ITEMS });
  assert.equal(lastQuery(h), "/coauthorship.html");                   // nothing set: bare path
  Object.assign(h.st(), { vol: ["Vol A", "Vol B"], topic: ["Data"], kind: ["Book"], from: "1990", to: "2010", tie: 2, group: 5, find: "Amy Lee", only: true });
  h.api.writeAddress();
  assert.equal(lastQuery(h), "/coauthorship.html?Volume=Vol+A&Volume=Vol+B&Topic=Data&Type=Book&Year_from=1990&Year_to=2010&Tie=2&Group=5&Find=Amy+Lee&Only=1");
  Object.assign(h.st(), { vol: [], topic: [], kind: [], from: "", to: "2000", tie: 1, group: 3, find: "", only: false });
  h.api.writeAddress();
  assert.equal(lastQuery(h), "/coauthorship.html?Year_to=2000");
  Object.assign(h.st(), { to: "", from: "1980" });
  h.api.writeAddress();
  assert.equal(lastQuery(h), "/coauthorship.html?Year_from=1980");
});

test("writeAddress then readAddress round-trips every field", () => {
  const h = makeCo({ items: ITEMS });
  const want = { vol: ["Vol A", "Vol B"], topic: ["Data", "Open Access"], kind: ["Book"], from: "1990", to: "2010", tie: 3, group: 8, find: "O'Brien & Co", only: true };
  Object.assign(h.st(), want);
  h.api.writeAddress();
  h.loc.search = "?" + lastQuery(h).split("?")[1];
  Object.assign(h.st(), { vol: [], topic: [], kind: [], from: "", to: "", tie: 1, group: 3, find: "", only: false, sel: "" });
  h.api.readAddress();
  const s = h.st();
  assert.deepEqual({ vol: s.vol, topic: s.topic, kind: s.kind, from: s.from, to: s.to, tie: s.tie, group: s.group, find: s.find, only: s.only }, want);
  assert.equal(s.sel, want.find);
});

test("writeAddress tolerates history.replaceState throwing (a saved file)", () => {
  const h = makeCo({ items: ITEMS, replaceThrows: true });
  h.st().tie = 2;
  assert.doesNotThrow(() => h.api.writeAddress());
});

test("the first update writes the normalised address", () => {
  const h = makeCo({ items: ITEMS, search: "?Tie=1&Group=3&Volume=Vol+A" });
  assert.equal(lastQuery(h), "/coauthorship.html?Volume=Vol+A");
});

test("applyToControls puts state into every control", () => {
  const h = makeCo({ items: ITEMS });
  Object.assign(h.st(), { vol: ["Vol B"], topic: ["Open Access", "Data"], kind: ["Book"], from: "1990", to: "2000", tie: 2, group: 5, find: "Amy", only: true });
  h.api.applyToControls();
  assert.deepEqual(h.boxes.Volume.map((c) => c.checked), [false, true]);
  assert.deepEqual(h.boxes.Topic.map((c) => c.checked), [true, true]);
  assert.deepEqual(h.boxes.Type.map((c) => c.checked), [false, true]);
  assert.equal(h.yfrom.value, "1990"); assert.equal(h.yto.value, "2000");
  assert.equal(h.tie.value, "2"); assert.equal(h.group.value, "5");
  assert.equal(h.find.value, "Amy"); assert.equal(h.only.checked, true);
});

test("the controls reflect the address on load", () => {
  const h = makeCo({ items: ITEMS, search: "?Volume=Vol+A&Year_from=1990&Find=Amy&Only=1&Tie=2&Group=2" });
  assert.equal(h.boxes.Volume[0].checked, true);
  assert.equal(h.yfrom.value, "1990"); assert.equal(h.find.value, "Amy"); assert.equal(h.only.checked, true);
  assert.equal(h.tie.value, "2"); assert.equal(h.group.value, "2");
});

test("readControls reads checked boxes, trims text, and falls back on unreadable numbers", () => {
  const h = makeCo({ items: ITEMS });
  h.boxes.Volume[1].checked = true; h.boxes.Topic[0].checked = true; h.boxes.Type[1].checked = true;
  h.yfrom.value = " 1990 "; h.yto.value = "2000 ";
  h.tie.value = "3"; h.group.value = "8"; h.find.value = "  Amy  "; h.only.checked = true;
  h.api.readControls();
  const s = h.st();
  assert.deepEqual([s.vol, s.topic, s.kind], [["Vol B"], ["Open Access"], ["Book"]]);
  assert.deepEqual([s.from, s.to, s.tie, s.group, s.find, s.only], ["1990", "2000", 3, 8, "Amy", true]);
  h.tie.value = ""; h.group.value = "x";
  h.api.readControls();
  assert.equal(h.st().tie, 1); assert.equal(h.st().group, 3);
});

test("chosen: no filters keeps every item, including those with no year", () => {
  const h = makeCo({ items: ITEMS });
  assert.deepEqual(h.api.chosen().map((i) => i.id), ["1", "2", "3", "4"]);
});

test("chosen: each filter on its own, and combined", () => {
  const h = makeCo({ items: ITEMS });
  const ids = (patch) => {
    Object.assign(h.st(), { vol: [], topic: [], kind: [], from: "", to: "" }, patch);
    return h.api.chosen().map((i) => i.id);
  };
  assert.deepEqual(ids({ vol: ["Vol A"] }), ["1", "3"]);
  assert.deepEqual(ids({ vol: ["Vol A", "Vol B"] }), ["1", "2", "3", "4"]);          // any of
  assert.deepEqual(ids({ topic: ["Data"] }), ["2", "3"]);
  assert.deepEqual(ids({ kind: ["Book"] }), ["2", "4"]);
  assert.deepEqual(ids({ kind: ["Book", "Article"] }), ["1", "2", "3", "4"]);
  assert.deepEqual(ids({ from: "2000" }), ["2", "4"]);                                // undated item 3 excluded
  assert.deepEqual(ids({ to: "2000" }), ["1"]);                                       // undated item 3 excluded
  assert.deepEqual(ids({ from: "1995", to: "2005" }), ["1", "2"]);                    // bounds inclusive
  assert.deepEqual(ids({ from: "2006", to: "2000" }), []);
  assert.deepEqual(ids({ vol: ["Vol B"], topic: ["Data"], kind: ["Book"], from: "2000", to: "2010" }), ["2"]);
  assert.deepEqual(ids({ topic: ["Nope"] }), []);
});

test("chosen: a year bound that is not a number is ignored, so undated items stay", () => {
  const h = makeCo({ items: ITEMS });
  Object.assign(h.st(), { from: "abc", to: "xyz" });
  assert.deepEqual(h.api.chosen().map((i) => i.id), ["1", "2", "3", "4"]);
});

test("anyOf: empty wanted list matches anything; otherwise any overlap", () => {
  const h = makeCo({ items: [] });
  assert.equal(h.api.anyOf([], []), true);
  assert.equal(h.api.anyOf(["a"], []), false);
  assert.equal(h.api.anyOf(["a", "b"], ["c", "b"]), true);
});

test("esc escapes the five HTML characters and stringifies non-strings", () => {
  const h = makeCo({ items: [] });
  assert.equal(h.api.esc(`<a href="x">Tom & 'Jerry'</a>`), "&lt;a href=&quot;x&quot;&gt;Tom &amp; &#39;Jerry&#39;&lt;/a&gt;");
  assert.equal(h.api.esc(12), "12");
  assert.equal(h.api.exploreUrl("O'Brien & Co"), "index.html?Author=O'Brien%20%26%20Co");
});

test("checkbox and select changes recompute at once; text and number inputs are debounced 250 ms", () => {
  const h = makeCo({ items: ITEMS });
  const hist0 = h.hist.length;
  h.boxes.Volume[0].checked = true;
  h.boxes.Volume[0].dispatch("change");
  assert.deepEqual(h.timers.queue.map((q) => q.ms), [0]);
  h.timers.flush();
  assert.deepEqual(h.st().vol, ["Vol A"]);
  assert.ok(h.hist.length > hist0);

  h.group.value = "2"; h.group.dispatch("change");
  assert.deepEqual(h.timers.queue.map((q) => q.ms), [0]);
  h.timers.flush();
  assert.equal(h.st().group, 2);

  h.find.value = "A"; h.find.dispatch("input");
  h.find.value = "Am"; h.find.dispatch("input");
  h.yfrom.value = "1990"; h.yfrom.dispatch("input");
  assert.equal(h.timers.queue.length, 1);                  // earlier timers were cleared
  assert.equal(h.timers.queue[0].ms, 250);
  assert.equal(h.timers.cleared, 2);
  assert.equal(h.st().from, "");                           // nothing read until the timer fires
  h.timers.flush();
  assert.equal(h.st().find, "Am"); assert.equal(h.st().from, "1990");

  assert.equal(h.find.listeners.change, undefined);        // text inputs listen to input only
  assert.equal(h.boxes.Volume[0].listeners.input, undefined);
});

test("reset clears state, controls and address", () => {
  const h = makeCo({ items: ITEMS, search: "?Volume=Vol+A&Topic=Data&Type=Book&Year_from=1990&Year_to=2010&Tie=2&Group=2&Find=Amy&Only=1" });
  assert.equal(h.boxes.Volume[0].checked, true);
  h.reset.dispatch("click");
  const s = h.st();
  assert.deepEqual([s.vol, s.topic, s.kind, s.from, s.to, s.tie, s.group, s.find, s.only, s.sel], [[], [], [], "", "", 1, 3, "", false, ""]);
  assert.equal(h.boxes.Volume[0].checked, false);
  assert.equal(h.yfrom.value, ""); assert.equal(h.find.value, ""); assert.equal(h.only.checked, false);
  assert.equal(h.tie.value, "1"); assert.equal(h.group.value, "3");
  assert.equal(lastQuery(h), "/coauthorship.html");
});
