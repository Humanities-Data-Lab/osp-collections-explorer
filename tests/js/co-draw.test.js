"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { makeCo, it, clickOn } = require("./co-harness");

const ITEMS = [
  it("i1", ["Amy", "Bob", "Cy"], 2001, ["Vol A"], [], "Article", "First"),
  it("i2", ["Amy", "Bob"], 2002, ["Vol A"], [], "Article", "Second"),
  it("i3", ["Amy", "Dee"], 2003, ["Vol B"], [], "Book", 'Say "hi" & <go>'),
  it("i4", ["Eve", "Fay"], 2010, ["Vol B"], [], "Book", "Fourth"),
  it("i5", ["Eve", "Fay"], 2011, ["Vol B"], [], "Book", "Fifth"),
  it("i6", ["Gus"], 2012, ["Vol B"], [], "Book", ""),
  it("i7", ["Hal", "Ivy"], 2020, ["Vol A"], [], "Article", "Seventh"),
];
const html = (h, id) => h.el(id).innerHTML;
const count = (s, re) => (s.match(re) || []).length;
const nodeNames = (h) => (html(h, "network").match(/<g class="node[^"]*"[^>]*data-n="([^"]*)"/g) || []).map((m) => /data-n="([^"]*)"/.exec(m)[1]);

/* ---------- drawNetwork ---------- */
test("drawNetwork: svg container, accessible nodes, edge widths and text labels", () => {
  const h = makeCo({ items: ITEMS });                       // default: groups of 3 or more, so only Amy's group
  const s = html(h, "network");
  assert.match(s, /^<svg viewBox="0 0 1000 \d+" role="group" aria-labelledby="net-cap" class="net" preserveAspectRatio="xMidYMin meet" focusable="false">/);
  assert.ok(s.endsWith("</svg>"));
  assert.deepEqual(nodeNames(h), ["Amy", "Bob", "Cy", "Dee"]);
  assert.equal(count(s, /<line /g), 4);
  assert.equal(count(s, /stroke-width="1\.9"/g), 1);        // Amy and Bob share two items: 0.8 + 1.1
  assert.equal(count(s, /stroke-width="0\.8"/g), 3);
  assert.ok(!s.includes("has-sel") && !s.includes("edge on") && !s.includes("node sel") && !s.includes("node near"));
  assert.match(s, /<g class="node" tabindex="0" role="button" data-n="Amy" aria-pressed="false" aria-label="Amy, 3 items, 3 co-authors"><circle cx="[\d.]+" cy="[\d.]+" r="[\d.]+"\/><title>Amy<\/title><\/g>/);
  assert.match(s, /aria-label="Cy, 1 item, 2 co-authors"/);           // singular item, plural co-authors
  assert.match(s, /aria-label="Dee, 1 item, 1 co-author"/);            // singular co-author
  assert.match(s, /<text class="lbl" x="[\d.]+" y="[\d.]+" text-anchor="start" aria-hidden="true">Amy<\/text>/);
  assert.equal(count(s, /<text /g), 1);                     // only Amy has 3 items; the others are too small to label
  assert.equal(h.view().height > 0, true);
  assert.match(s, new RegExp('viewBox="0 0 1000 ' + Math.ceil(h.view().height + 8) + '"'));
});

test("drawNetwork: a wider edge for a stronger tie, capped at four extra steps", () => {
  const six = [];
  for (let i = 0; i < 6; i++) { six.push(it("s" + i, ["Pat", "Quin"], 2000)); }
  const h = makeCo({ items: six.concat([it("t", ["Pat", "Rae"], 2000)]), search: "?Group=2" });
  assert.equal(count(html(h, "network"), /stroke-width="5\.2"/g), 1);   // 0.8 + 1.1 * min(6 - 1, 4)
  assert.equal(count(html(h, "network"), /stroke-width="0\.8"/g), 1);
});

test("drawNetwork: a selected author is marked, with its ties and neighbours", () => {
  const h = makeCo({ items: ITEMS, search: "?Find=Amy" });
  const s = html(h, "network");
  assert.match(s, /class="net has-sel"/);
  assert.match(s, /class="node sel"[^>]*data-n="Amy" aria-pressed="true"/);
  ["Bob", "Cy", "Dee"].forEach((n) => assert.match(s, new RegExp('class="node near"[^>]*data-n="' + n + '" aria-pressed="false"')));
  assert.equal(count(s, /class="edge on"/g), 3);             // Amy's three ties
  assert.equal(count(s, /class="edge"/g), 1);                // Bob-Cy is not Amy's
  assert.equal(count(s, /<text /g), 4);                      // selected and near authors are always labelled
});

test("drawNetwork: names are escaped, including quotes and ampersands", () => {
  const nasty = 'O"Brien & <Co>', other = "Z'ed";
  const h = makeCo({ items: [it("n1", [nasty, other, "Plain"], 2000)] });
  const s = html(h, "network");
  assert.ok(s.includes('data-n="O&quot;Brien &amp; &lt;Co&gt;"'));
  assert.ok(s.includes('data-n="Z&#39;ed"'));
  assert.ok(s.includes("<title>O&quot;Brien &amp; &lt;Co&gt;</title>"));
  assert.ok(s.includes('aria-label="O&quot;Brien &amp; &lt;Co&gt;, 1 item, 2 co-authors"'));
  assert.ok(!s.includes('O"Brien') && !s.includes("<Co>"));
});

test("drawNetwork: nothing to draw gives the empty-state message and no svg", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=8" });
  assert.equal(html(h, "network"), '<p class="empty">No authors share an item under these filters. Widen the filters, or lower the minimum shared items or group size.</p>');
  const none = makeCo({ items: ITEMS, search: "?Year_from=2100" });
  assert.match(html(none, "network"), /^<p class="empty">No authors share/);
  assert.equal(none.view().height, 0);
});

test("drawNetwork: a selection outside the drawn groups marks nothing, and edges to undrawn authors are dropped", () => {
  const h = makeCo({ items: ITEMS, search: "?Find=Hal" });   // Hal's group has two authors; groups of 3 are drawn
  assert.ok(!html(h, "network").includes("has-sel"));
  assert.match(html(h, "panel"), /<h3>Hal<\/h3>/);          // but the panel still describes Hal
  const g = h.view().byName.Amy;
  h.api.drawNetwork([[g]], 50);                              // a partial group: neighbours are not in the drawing
  assert.equal(count(html(h, "network"), /<line /g), 0);
  assert.deepEqual(nodeNames(h), ["Amy"]);
});

/* ---------- labels ---------- */
function node(name, items, x, y, adj, r) { return { name, items, x, y, r: r === undefined ? 6 : r, adj: new Array(adj || 0).fill(0) }; }

test("labels: only prominent authors are labelled unless selected or near", () => {
  const h = makeCo({ items: [] });
  const nodes = [node("Small", 2, 100, 100, 6), node("Three", 3, 100, 200, 0), node("Hub", 1, 100, 300, 7), node("Near", 1, 100, 400, 1), node("Sel", 1, 100, 500, 1)];
  const out = h.api.labels(nodes, "Sel", { Sel: true, Near: true });
  assert.deepEqual(out.map((l) => l.n.name), ["Sel", "Near", "Three", "Hub"]);   // selected, near, then by items, then by degree
});

test("labels: later labels that would overlap an earlier one are dropped", () => {
  const h = makeCo({ items: [] });
  const a = node("Alpha", 9, 100, 100), b = node("Beta", 5, 110, 104), c = node("Gamma", 4, 100, 300);
  const out = h.api.labels([b, a, c], "", {});
  assert.deepEqual(out.map((l) => l.n.name), ["Alpha", "Gamma"]);
  const touching = h.api.labels([node("Aaa", 5, 100, 100), node("Bbb", 4, 100, 113)], "", {});   // exactly one line apart: no overlap
  assert.equal(touching.length, 2);
});

test("labels: a selected author wins a collision against a busier one", () => {
  const h = makeCo({ items: [] });
  const busy = node("Busy", 50, 100, 100), sel = node("Sel", 1, 105, 102);
  const out = h.api.labels([busy, sel], "Sel", { Sel: true });
  assert.deepEqual(out.map((l) => l.n.name), ["Sel"]);
});

test("labels: caps the number of labels at 90", () => {
  const h = makeCo({ items: [] });
  const nodes = Array.from({ length: 120 }, (_, i) => node("N" + String(i).padStart(3, "0"), 5, 100, 20 * i));
  const out = h.api.labels(nodes, "", {});
  assert.equal(out.length, 90);
  assert.equal(out[0].n.name, "N000");
});

test("labels: placed to the right of the circle, flipped to the left near the right edge", () => {
  const h = makeCo({ items: [] });
  const right = h.api.labels([node("Rightward", 5, 100, 50, 0, 8)], "", {})[0];
  assert.equal(right.anchor, "start");
  assert.equal(right.x, 100 + 8 + 3);
  assert.ok(Math.abs(right.y - (50 + 13 * 0.35)) < 1e-9);
  const w = "Leftward".length * 13 * 0.58 + 4;
  const left = h.api.labels([node("Leftward", 5, 960, 50, 0, 8)], "", {})[0];
  assert.equal(left.anchor, "end");
  assert.ok(Math.abs(left.x - (960 - 8 - 3)) < 1e-9);           // text ends just before the circle
  assert.ok(960 + 8 + 3 + w >= 998);
});

test("labels: ties are broken by degree and then by name, so the result is deterministic", () => {
  const h = makeCo({ items: [] });
  const spread = (names, adjs) => names.map((nm, i) => node(nm, 4, 100, 30 * i, adjs ? adjs[i] : 0));
  assert.deepEqual(h.api.labels(spread(["Bb", "Aa", "Cc"]), "", {}).map((l) => l.n.name), ["Aa", "Bb", "Cc"]);
  assert.deepEqual(h.api.labels(spread(["Bb", "Aa", "Cc"], [1, 1, 5]), "", {}).map((l) => l.n.name), ["Cc", "Aa", "Bb"]);
});

/* ---------- tables ---------- */
const col = (h, id, re) => (html(h, id).match(re) || []).map((m) => m.replace(/.*"(.*)".*/, "$1"));
const sel = /data-sel="[^"]*"/g;

test("drawTables: people ranked by co-authored items, then co-authors, then name", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2" });
  assert.deepEqual(col(h, "t-people", sel), ["Amy", "Bob", "Eve", "Fay", "Cy", "Dee", "Hal", "Ivy"]);
  assert.match(html(h, "t-people"), /^<div class="tablewrap" tabindex="0" role="region" aria-label="Scrollable table"><table class="data"><thead><tr><th scope="col">Author<\/th><th scope="col">Items<\/th><th scope="col">Co-authored items<\/th><th scope="col">Co-authors<\/th><\/tr><\/thead>/);
  assert.match(html(h, "t-people"), /<tr><th scope="row"><button type="button" class="linkish" data-sel="Amy">Amy<\/button><\/th><td>3<\/td><td>3<\/td><td>3<\/td><\/tr>/);
  assert.match(html(h, "t-people"), /<tr><th scope="row"><button[^>]*>Bob<\/button><\/th><td>2<\/td><td>2<\/td><td>2<\/td><\/tr>/);
});

test("drawTables: people are limited to the authors drawn, and to twelve rows", () => {
  const h = makeCo({ items: ITEMS });                        // groups of 3: only Amy's group is drawn
  assert.deepEqual(col(h, "t-people", sel), ["Amy", "Bob", "Cy", "Dee"]);
  const many = [];
  for (let i = 0; i < 15; i++) { many.push(it("m" + i, ["Hub", "Spoke" + String(i).padStart(2, "0")], 2000)); }
  const big = makeCo({ items: many });
  const names = col(big, "t-people", sel);
  assert.equal(names.length, 12);
  assert.equal(names[0], "Hub");
});

test("drawTables: pairs sharing two or more items, strongest first, ties by name", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2" });
  assert.deepEqual(col(h, "t-ties", sel), ["Amy", "Bob", "Eve", "Fay"]);
  assert.match(html(h, "t-ties"), /<th scope="col">Pair<\/th><th scope="col">Shared items<\/th>/);
  assert.match(html(h, "t-ties"), /data-sel="Amy">Amy<\/button> and <button[^>]*data-sel="Bob">Bob<\/button><\/th><td>2<\/td>/);
  const three = [it("a", ["Aa", "Bb"]), it("b", ["Aa", "Bb"]), it("c", ["Aa", "Bb"]), it("d", ["Cc", "Dd"]), it("e", ["Cc", "Dd"])];
  const t = makeCo({ items: three, search: "?Group=2" });
  assert.deepEqual(col(t, "t-ties", sel), ["Aa", "Bb", "Cc", "Dd"]);
  assert.match(html(t, "t-ties"), /Bb<\/button><\/th><td>3<\/td>/);
  const only = makeCo({ items: ITEMS });                     // Eve-Fay is not drawn at group size 3
  assert.deepEqual(col(only, "t-ties", sel), ["Amy", "Bob"]);
});

test("drawTables: at most fifteen pairs", () => {
  const many = [];
  for (let i = 0; i < 18; i++) { const a = "A" + String(i).padStart(2, "0"), b = "B" + String(i).padStart(2, "0"); many.push(it("x" + i, [a, b]), it("y" + i, [a, b])); }
  const h = makeCo({ items: many, search: "?Group=2" });
  assert.equal(col(h, "t-ties", sel).length, 30);
});

test("drawTables: groups listed with their three most active members", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2" });
  const s = html(h, "t-groups");
  assert.match(s, /<th scope="col">Group<\/th><th scope="col">Authors<\/th><th scope="col">Most active members<\/th>/);
  assert.match(s, /<tr><th scope="row">1<\/th><td>4<\/td><td><button[^>]*>Amy<\/button>, <button[^>]*>Bob<\/button>, <button[^>]*>Cy<\/button><\/td><\/tr>/);
  assert.match(s, /<tr><th scope="row">2<\/th><td>2<\/td><td><button[^>]*>Eve<\/button>, <button[^>]*>Fay<\/button><\/td><\/tr>/);
  assert.equal(count(s, /<tr><th scope="row">/g), 3);
  const bigger = makeCo({ items: ITEMS });                   // the table lists groups of any size, not only those drawn
  assert.equal(count(html(bigger, "t-groups"), /<tr><th scope="row">/g), 3);
  const members = makeCo({ items: [it("p", ["Ann", "Bea", "Cat", "Dan"]), it("q", ["Dan", "Cat"])], search: "?Group=2" });
  assert.match(html(members, "t-groups"), /Cat<\/button>, <button[^>]*>Dan<\/button>, <button[^>]*>Ann<\/button>/);   // items desc, then name
});

test("drawTables: authors-per-item bars with singular and plural labels", () => {
  const h = makeCo({ items: ITEMS });
  const s = html(h, "t-per");
  assert.match(s, /^<ul class="sbars">/);
  assert.match(s, /<li><span class="lbl">1 author<\/span><span class="track"><span class="fill" style="width:20\.0%"><\/span><\/span><span class="num">1<\/span><\/li>/);
  assert.match(s, /<li><span class="lbl">2 authors<\/span><span class="track"><span class="fill" style="width:100\.0%"><\/span><\/span><span class="num">5<\/span><\/li>/);
  assert.match(s, /<span class="lbl">3 authors<\/span>[^]*?width:20\.0%/);
  assert.match(s, /<span class="lbl">6 or more authors<\/span>/);
  assert.equal(count(s, /<li>/g), 6);
});

test("drawTables: empty selections give a message, and the histogram stays at zero without dividing by zero", () => {
  const h = makeCo({ items: ITEMS, search: "?Year_from=2100" });
  assert.equal(html(h, "t-people"), '<p class="empty">None under these filters.</p>');
  assert.equal(html(h, "t-ties"), '<p class="empty">No pair shares more than one item under these filters.</p>');
  assert.equal(html(h, "t-groups"), '<p class="empty">None under these filters.</p>');
  assert.equal(count(html(h, "t-per"), /width:0\.0%/g), 6);
});

/* ---------- panel ---------- */
test("drawPanel: nothing selected", () => {
  const h = makeCo({ items: ITEMS });
  assert.equal(html(h, "panel"), "<h3>Selected author</h3><p>Select a circle in the network, or a name in a table, to see the author's co-authors and shared items.</p>");
});

test("drawPanel: a selected author with several co-authors and items (plural wording)", () => {
  const h = makeCo({ items: ITEMS, search: "?Find=Amy" });
  const s = html(h, "panel");
  assert.ok(s.startsWith("<h3>Amy</h3><p>3 items in the current selection, 3 with a co-author. "));
  assert.ok(s.includes('<a href="index.html?Author=Amy">Show this author in Explore</a>. <button type="button" class="secondary" id="clear-sel">Clear selection</button></p>'));
  assert.ok(s.includes("<h4>Co-authors (3)</h4>"));
  assert.ok(s.includes('<li><button type="button" class="linkish" data-sel="Bob">Bob</button>, 2 shared items</li><li><button type="button" class="linkish" data-sel="Cy">Cy</button>, 1 shared item</li><li><button type="button" class="linkish" data-sel="Dee">Dee</button>, 1 shared item</li>'));
  assert.ok(s.includes("<h4>Co-authored items (3)</h4>"));
  assert.ok(s.includes('<li><a href="items/i1.html">First</a> (2001)</li><li><a href="items/i2.html">Second</a> (2002)</li><li><a href="items/i3.html">Say &quot;hi&quot; &amp; &lt;go&gt;</a> (2003)</li>'));
});

test("drawPanel: singular wording, untitled and undated items, and items ordered by year then title", () => {
  const items = [it("x1", ["Pam", "Quin"], null, ["Vol A"], [], "Article", ""), it("x2", ["Pam", "Quin"], 2000, ["Vol A"], [], "Article", "Beta"),
    it("x3", ["Pam", "Quin"], 2000, ["Vol A"], [], "Article", "Alpha"), it("y1", ["Pam", "Rob"], 1999, ["Vol A"], [], "Article", "Solo tie")];
  const h = makeCo({ items, search: "?Group=2&Find=Rob" });
  const rob = html(h, "panel");
  assert.ok(rob.startsWith("<h3>Rob</h3><p>1 item in the current selection, 1 with a co-author. "));
  assert.ok(rob.includes("<h4>Co-authors (1)</h4><ul><li><button type=\"button\" class=\"linkish\" data-sel=\"Pam\">Pam</button>, 1 shared item</li></ul>"));
  const pam = makeCo({ items, search: "?Group=2&Find=Pam" });
  const s = html(pam, "panel");
  assert.ok(s.includes("Quin</button>, 3 shared items</li>"));
  assert.ok(s.indexOf("Solo tie") < s.indexOf("Alpha") && s.indexOf("Alpha") < s.indexOf("Beta") && s.indexOf("Beta") < s.indexOf('items/x1.html">x1</a></li>'));
  assert.ok(s.includes('<li><a href="items/x1.html">x1</a></li>'));        // no title: the id; no year: no brackets
});

/* ---------- status ---------- */
test("status: sentence and metrics", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2" });
  assert.equal(h.el("co-status").textContent,
    "7 items match the filters; 7 have a named author and 6 (86 percent) have more than one. 9 authors; 8 in the 3 groups drawn. The largest group has 4 authors, counting groups of any size.");
  assert.deepEqual(["m-items", "m-multi", "m-authors", "m-ties", "m-groups", "m-largest"].map((id) => h.el(id).textContent), ["7", "6 (86%)", "9", "6", "3", "4"]);
});

test("status: one group drawn is singular", () => {
  const h = makeCo({ items: ITEMS });
  assert.match(h.el("co-status").textContent, /4 in the 1 group drawn\./);
});

test("status: no items, no authors and no groups", () => {
  const h = makeCo({ items: ITEMS, search: "?Year_from=2100" });
  assert.equal(h.el("co-status").textContent,
    "0 items match the filters; 0 have a named author and 0 (0 percent) have more than one. 0 authors; 0 in the 0 groups drawn. The largest group has 0 authors, counting groups of any size.");
  assert.deepEqual(["m-items", "m-multi", "m-authors", "m-ties", "m-groups", "m-largest"].map((id) => h.el(id).textContent), ["0", "0 (0%)", "0", "0", "0", "0"]);
});

test("status: items without a listed author are matched but not counted as authored", () => {
  const h = makeCo({ items: [it("e1", []), it("e2", ["Solo"])] });
  assert.match(h.el("co-status").textContent, /^2 items match the filters; 1 have a named author and 0 \(0 percent\) have more than one\. 1 authors;/);
});

/* ---------- update with Find / Only ---------- */
test("update: Find selects the author, and Only keeps just that author's group", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2&Find=Eve" });
  assert.equal(h.st().sel, "Eve");
  assert.equal(h.el("find-note").textContent, "");
  assert.deepEqual(nodeNames(h), ["Amy", "Bob", "Cy", "Dee", "Eve", "Fay", "Hal", "Ivy"]);
  const only = makeCo({ items: ITEMS, search: "?Group=2&Find=Eve&Only=1" });
  assert.deepEqual(nodeNames(only), ["Eve", "Fay"]);
  assert.match(html(only, "panel"), /<h3>Eve<\/h3>/);
  assert.equal(count(html(only, "t-groups"), /<tr><th scope="row">/g), 3);   // the table still lists every group
});

test("update: Only without a matching author changes nothing", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2&Only=1" });
  assert.equal(nodeNames(h).length, 8);
  const none = makeCo({ items: ITEMS, search: "?Group=2&Only=1&Find=Nobody" });
  assert.equal(nodeNames(none).length, 8);
});

test("update: Find with an unknown name says so and selects nothing", () => {
  const h = makeCo({ items: ITEMS, search: '?Find=Nobody' });
  assert.equal(h.el("find-note").textContent, 'No co-authorship for "Nobody" under these filters.');
  assert.equal(h.st().sel, "");
  assert.match(html(h, "panel"), /<h3>Selected author<\/h3>/);
});

test("update: an unknown Find does not drop a different selection the reader made", () => {
  const h = makeCo({ items: ITEMS });
  clickOn(h, { "data-n": "Amy" }, { tag: "g" });
  assert.equal(h.st().sel, "Amy");
  h.find.value = "Nobody"; h.find.dispatch("input"); h.timers.flush();
  assert.equal(h.st().sel, "Amy");
  assert.equal(h.el("find-note").textContent, 'No co-authorship for "Nobody" under these filters.');
});

test("update: a selection that the filters remove is cleared", () => {
  const h = makeCo({ items: ITEMS, search: "?Group=2" });
  clickOn(h, { "data-n": "Hal" }, { tag: "g" });
  assert.equal(h.st().sel, "Hal");
  h.yto.value = "2005"; h.yto.dispatch("input"); h.timers.flush();
  assert.equal(h.st().sel, "");
  assert.match(html(h, "panel"), /<h3>Selected author<\/h3>/);
});

test("update: the address follows the controls", () => {
  const h = makeCo({ items: ITEMS });
  h.boxes.Volume[1].checked = true; h.boxes.Volume[1].dispatch("change"); h.timers.flush();
  assert.equal(h.hist[h.hist.length - 1], "/coauthorship.html?Volume=Vol+B");
  assert.equal(h.view().items, 4);
});

/* ---------- select, click, keyboard ---------- */
test("clicking a circle selects it, and clicking it again deselects it", () => {
  const h = makeCo({ items: ITEMS });
  clickOn(h, { "data-n": "Bob" }, { tag: "g" });
  assert.equal(h.st().sel, "Bob");
  assert.match(html(h, "network"), /class="node sel"[^>]*data-n="Bob"/);
  assert.match(html(h, "panel"), /<h3>Bob<\/h3>/);
  assert.equal(h.el("network").scrolled, 0);                   // circles are already in view
  clickOn(h, { "data-n": "Bob" }, { tag: "g" });
  assert.equal(h.st().sel, "");
  assert.ok(!html(h, "network").includes("has-sel"));
});

test("clicking a name in a table selects it, scrolls the network into view, and toggles", () => {
  const h = makeCo({ items: ITEMS });
  clickOn(h, { "data-sel": "Cy" });
  assert.equal(h.st().sel, "Cy");
  assert.equal(h.el("network").scrolled, 1);
  clickOn(h, { "data-sel": "Cy" });
  assert.equal(h.st().sel, "");
  assert.equal(h.el("network").scrolled, 2);
});

test("clear selection empties the selection and the Find box", () => {
  const h = makeCo({ items: ITEMS, search: "?Find=Amy" });
  h.find.value = "Amy";
  assert.equal(h.st().sel, "Amy");
  clickOn(h, { id: "clear-sel" });
  assert.equal(h.st().sel, ""); assert.equal(h.st().find, ""); assert.equal(h.find.value, "");
  assert.equal(h.hist[h.hist.length - 1], "/coauthorship.html");
  assert.match(html(h, "panel"), /<h3>Selected author<\/h3>/);
});

test("clicks elsewhere are ignored, including targets with no closest()", () => {
  const h = makeCo({ items: ITEMS });
  const before = html(h, "network");
  h.doc.dispatch("click", { target: h.doc.createElement("p") });
  h.doc.dispatch("click", { target: {} });
  assert.equal(h.st().sel, "");
  assert.equal(html(h, "network"), before);
});

test("Enter and Space on a circle select it, keep focus on it, and prevent scrolling", () => {
  const h = makeCo({ items: ITEMS });
  ["Enter", " "].forEach((key, i) => {
    const g = h.doc.createElement("g"); g.setAttribute("data-n", "Amy");
    const ev = h.doc.dispatch("keydown", { key, target: g });
    assert.equal(ev.defaultPrevented, true);
    assert.equal(h.st().sel, i === 0 ? "Amy" : "");          // the second press toggles it off
  });
  const g = h.doc.createElement("g"); g.setAttribute("data-n", "Amy");
  h.doc.dispatch("keydown", { key: "Enter", target: g });
  assert.equal(h.st().sel, "Amy");
  assert.equal(h.doc.activeElement.getAttribute("data-n"), "Amy");   // focus is put back on the redrawn circle
  assert.ok(h.doc.activeElement.focused >= 1);
});

test("keyboard selection finds the redrawn circle for names with quotes", () => {
  const h = makeCo({ items: [it("n1", ['O"Brien & Co', "Plain", "Other"], 2000)] });
  const g = h.doc.createElement("g"); g.setAttribute("data-n", 'O"Brien & Co');
  h.doc.dispatch("keydown", { key: "Enter", target: g });
  assert.equal(h.st().sel, 'O"Brien & Co');
  assert.equal(h.doc.activeElement.getAttribute("data-n"), 'O"Brien & Co');
});

test("keyboard: other keys, other elements and bare targets are ignored", () => {
  const h = makeCo({ items: ITEMS });
  const g = h.doc.createElement("g"); g.setAttribute("data-n", "Amy");
  const btn = h.doc.createElement("button"); btn.setAttribute("data-n", "Amy");
  const plain = h.doc.createElement("g");
  [{ key: "a", target: g }, { key: "Tab", target: g }, { key: "Enter", target: btn }, { key: "Enter", target: plain }, { key: "Enter", target: {} }].forEach((ev) => {
    const out = h.doc.dispatch("keydown", ev);
    assert.equal(out.defaultPrevented, false);
  });
  assert.equal(h.st().sel, "");
});

test("keyboard selection tolerates a circle that cannot be found afterwards", () => {
  const h = makeCo({ items: ITEMS });
  const g = h.doc.createElement("g"); g.setAttribute("data-n", "Nobody Here");
  assert.doesNotThrow(() => h.doc.dispatch("keydown", { key: "Enter", target: g }));
  assert.equal(h.st().sel, "Nobody Here");
});

test("the same filters give byte-identical output on every load", () => {
  const a = makeCo({ items: ITEMS, search: "?Group=2" }), b = makeCo({ items: ITEMS, search: "?Group=2" });
  assert.equal(html(a, "network"), html(b, "network"));
});

/* ---------- ordering is total and independent of input order ---------- */
function shuffled(list, seed) {                       // deterministic Fisher-Yates with a small LCG
  const a = list.slice(); let s = seed;
  for (let i = a.length - 1; i > 0; i--) { s = (s * 1664525 + 1013904223) >>> 0; const j = s % (i + 1); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

test("the panel's co-author and item lists are ordered the same whatever order the data arrives in", () => {
  const base = [];
  const years = [null, 2000, 2000, 1999, null, 2005, 1999, 2001];
  years.forEach((y, i) => base.push(it("w" + i, ["Pam", "Co" + (i % 4)], y, ["Vol A"], [], "Article", i % 3 === 0 ? "" : "T" + (7 - i))));
  base.push(it("w9", ["Pam", "Co1", "Co2"], 1998, ["Vol A"], [], "Article", "Triple"));
  const outs = [1, 2, 3, 4, 5, 6, 7, 8].map((seed) => html(makeCo({ items: shuffled(base, seed), search: "?Group=2&Find=Pam" }), "panel"));
  outs.forEach((o) => assert.equal(o, outs[0]));
  const order = (outs[0].match(/<li><a href="items\/(w\d)\.html"/g) || []).map((m) => /(w\d)/.exec(m)[1]);
  assert.equal(order.length, 9);
  assert.equal(order[0], "w9");                            // 1998 first; undated last
  assert.deepEqual(order.slice(-2).sort(), ["w0", "w4"]);
  const cos = (outs[0].match(/data-sel="Co\d"/g) || []).map((m) => m.slice(10, -1));
  assert.deepEqual(cos, ["Co1", "Co2", "Co0", "Co3"]);     // most shared items first, then by name
});

test("the tables are ordered the same whatever order the data arrives in", () => {
  const base = [];
  for (let i = 0; i < 24; i++) {
    const shared = 2 + (i * 7) % 3;
    for (let k = 0; k < shared; k++) { base.push(it("p" + i + "_" + k, ["A" + String(i).padStart(2, "0"), "B" + String(i).padStart(2, "0"), "C" + String(i % 5)], 2000)); }
  }
  const outs = [11, 12, 13].map((seed) => {
    const h = makeCo({ items: shuffled(base, seed), search: "?Group=2" });
    return [html(h, "t-people"), html(h, "t-ties"), html(h, "t-groups")];
  });
  outs.forEach((o) => assert.deepEqual(o, outs[0]));
  const pairs = (outs[0][1].match(/data-sel="[^"]*"/g) || []).map((m) => m.slice(10, -1));
  assert.equal(pairs.length, 30);                          // fifteen pairs, two names each
  const nums = (outs[0][1].match(/<td>(\d+)<\/td>/g) || []).map((m) => +/\d+/.exec(m)[0]);
  assert.deepEqual(nums, nums.slice().sort((a, b) => b - a));
});
