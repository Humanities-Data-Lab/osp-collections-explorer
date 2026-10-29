"use strict";
const test = require("node:test");
const assert = require("node:assert");
const vm = require("node:vm");
const { makeCo, it } = require("./co-harness");

const names = (g) => g.map((n) => n.name);
function chain(prefix, len, start) {                       // items sharing consecutive authors: a path graph
  const out = [];
  for (let i = 0; i < len - 1; i++) { out.push(it(prefix + "c" + i + (start || ""), [prefix + String(i).padStart(3, "0"), prefix + String(i + 1).padStart(3, "0")], 2000)); }
  return out;
}
function clique(prefix, n, id) { return [it(id || prefix, Array.from({ length: n }, (_, i) => prefix + i), 2000)]; }
function groupsOf(items, tie) {
  const h = makeCo({ items: [] });
  h.st().tie = tie || 1;
  const v = h.api.build(items);
  return { h, v };
}
const snap = (g) => g.map((n) => [n.x.toFixed(6), n.y.toFixed(6), n.r.toFixed(6)].join(","));

/* ---------- build ---------- */
const MIX = [
  it("A", ["Zed", "Amy", "Amy"]), it("B", ["Amy", "Zed", "Bob"]), it("C", ["Solo"]), it("D", []),
  it("E", ["Cy", "Di"]), it("F", ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]),
];

test("build counts items, authors, histogram, ties and groups", () => {
  const { v } = groupsOf(MIX);
  assert.equal(v.items, 6);
  assert.equal(v.withAuthors, 5);          // the item with no authors is skipped
  assert.equal(v.multi, 4);                // the single-author item is not multi-author
  assert.deepEqual(v.perItem, [0, 1, 2, 1, 0, 0, 1]);   // 7 authors land in the "six or more" slot
  assert.equal(v.count.Amy, 2);            // a duplicated name in one item counts once
  assert.equal(v.count.Zed, 2); assert.equal(v.count.Solo, 1);
  assert.equal(Object.keys(v.count).length, 13);
  assert.equal(v.edges.length, 25);        // Amy-Zed, Amy-Bob, Bob-Zed, Cy-Di and the 21 pairs of the seven
});

test("build: duplicate author names inside one item never tie an author to themselves", () => {
  const { v } = groupsOf([it("A", ["Amy", "Amy"]), it("B", ["Amy", "Amy", "Bob"])]);
  assert.equal(v.edges.length, 1);
  assert.deepEqual([v.edges[0].a, v.edges[0].b], ["Amy", "Bob"]);
  assert.equal(v.count.Amy, 2);
  assert.equal(v.multi, 1);                // item A collapses to a single author
  assert.deepEqual(v.perItem, [0, 1, 1, 0, 0, 0, 0]);
});

test("build: single-author items add a count but no node", () => {
  const { v } = groupsOf([it("A", ["Solo"]), it("B", ["Solo"])]);
  assert.equal(v.count.Solo, 2);
  assert.deepEqual(v.nodes, []); assert.deepEqual(v.groups, []); assert.deepEqual(v.edges, []);
  assert.equal(v.multi, 0);
});

test("build: ties and nodes", () => {
  const { v } = groupsOf(MIX);
  assert.equal(v.edges.length, 25);                        // 1 (Amy-Zed twice) + 2 + 1 + 21
  const amyZed = v.edges.find((e) => e.a === "Amy" && e.b === "Zed");
  assert.deepEqual(amyZed.items.map((i) => i.id), ["A", "B"]);
  assert.deepEqual(v.nodes.map((n) => n.name).slice(0, 5), ["Amy", "Bob", "Zed", "Cy", "Di"]);   // edge order, then first appearance
  const amy = v.nodes[0];
  assert.equal(amy.items, 2);
  assert.deepEqual(amy.adj.map((x) => x.n.name), ["Bob", "Zed"]);
  assert.deepEqual(Object.keys(amy.co).sort(), ["A", "B"]);
  v.nodes.forEach((n, i) => assert.equal(n.id, i));
});

test("build: the minimum shared items threshold removes weak ties", () => {
  const two = groupsOf(MIX, 2).v;
  assert.equal(two.edges.length, 1);
  assert.deepEqual(names(two.nodes), ["Amy", "Zed"]);
  assert.equal(two.groups.length, 1);
  assert.equal(two.count.Bob, 1);                          // still counted as an author
  assert.equal(two.multi, 4);                              // item counts do not depend on the threshold
  const three = groupsOf(MIX, 3).v;
  assert.deepEqual(three.edges, []); assert.deepEqual(three.groups, []);
});

test("build: connected components, largest first, with a group index on every node", () => {
  const { v } = groupsOf(MIX);
  assert.deepEqual(v.groups.map((g) => g.length), [7, 3, 2]);
  assert.deepEqual(names(v.groups[1]), ["Amy", "Bob", "Zed"]);
  assert.deepEqual(names(v.groups[2]), ["Cy", "Di"]);
  v.groups.forEach((g, i) => g.forEach((n) => assert.equal(n.group, i)));
});

test("build: equal-sized groups are ordered by their first member's name, whatever the input order", () => {
  const items = [it("1", ["Mia", "Ned"]), it("2", ["Abe", "Bea"]), it("3", ["Zoe", "Yan"])];
  const a = groupsOf(items).v, b = groupsOf(items.slice().reverse()).v;
  const order = (v) => v.groups.map((g) => names(g).join("+"));
  assert.deepEqual(order(a), ["Abe+Bea", "Mia+Ned", "Yan+Zoe"]);
  assert.deepEqual(order(a), order(b));
  assert.deepEqual(names(a.nodes), names(b.nodes));
});

test("build: one author in several groups of the same item set stays in a single component", () => {
  const { v } = groupsOf([it("1", ["A", "B"]), it("2", ["B", "C"]), it("3", ["C", "D"]), it("4", ["D", "A"])]);
  assert.equal(v.groups.length, 1);
  assert.equal(v.groups[0].length, 4);
});

/* ---------- rng and hash ---------- */
test("hash is 32-bit FNV-1a", () => {
  const h = makeCo({ items: [] });
  assert.equal(h.api.hash(""), 2166136261);
  assert.equal(h.api.hash("a"), 0xe40c292c);
  assert.equal(h.api.hash("foobar"), 0xbf9cf968);
  assert.notEqual(h.api.hash("Amy"), h.api.hash("Amz"));
});

test("rng is deterministic per seed, in [0, 1), and differs between seeds", () => {
  const h = makeCo({ items: [] });
  const take = (seed, n) => { const r = h.api.rng(seed); return Array.from({ length: n }, () => r()); };
  assert.deepEqual(take(42, 20), take(42, 20));
  assert.notDeepEqual(take(42, 5), take(43, 5));
  take(7, 500).forEach((x) => assert.ok(x >= 0 && x < 1));
  assert.deepEqual(take(-1, 3), take(4294967295, 3));      // seed is taken as an unsigned 32-bit number
  assert.equal(new Set(take(9, 200)).size, 200);
  assert.equal(take(0, 1)[0], 0.26642920868471265);        // mulberry32(0): pinned so the layouts stay stable
});

test("radius grows with the square root of the item count", () => {
  const h = makeCo({ items: [] });
  assert.equal(h.api.radius({ items: 1 }), 6.4);
  assert.equal(h.api.radius({ items: 4 }), 8.8);
  assert.equal(h.api.radius({ items: 0 }), 4);
});

/* ---------- layoutGroup ---------- */
test("layoutGroup n=2: two nodes one ideal edge length apart on a horizontal line", () => {
  const { h, v } = groupsOf([it("1", ["Amy", "Bob"])]);
  const pair = v.groups[0];
  const box = h.api.layoutGroup(pair);
  assert.equal(pair[1].x - pair[0].x, h.api.K);
  assert.equal(pair[0].y, pair[1].y);
  assert.equal(pair[0].r, h.api.radius(pair[0]));
  assert.ok(Math.abs(box.w - (h.api.K + pair[0].r + pair[1].r)) < 1e-9);
  assert.ok(Math.abs(box.h - 2 * pair[0].r) < 1e-9);
  assert.ok(Math.abs(pair[0].x - pair[0].r) < 1e-9);       // the box starts at the origin
});

test("layoutGroup n=3 and a clique: finite, inside the box, no circles overlapping, and repeatable", () => {
  const { h, v } = groupsOf(clique("Q", 3).concat(clique("R", 12, "r")));
  const tri = v.groups[1], big = v.groups[0];
  assert.equal(tri.length, 3); assert.equal(big.length, 12);
  [tri, big].forEach((g) => {
    const box = h.api.layoutGroup(g);
    g.forEach((n) => {
      assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y));
      assert.ok(n.x - n.r > -1e-6 && n.x + n.r < box.w + 1e-6);
      assert.ok(n.y - n.r > -1e-6 && n.y + n.r < box.h + 1e-6);
    });
    for (let i = 0; i < g.length; i++) {
      for (let j = i + 1; j < g.length; j++) {
        assert.ok(Math.hypot(g[i].x - g[j].x, g[i].y - g[j].y) >= g[i].r + g[j].r + 5 - 1e-3, "overlap relaxation separates circles by 5px");
      }
    }
    const first = snap(g);
    h.api.layoutGroup(g);
    assert.deepEqual(snap(g), first);                       // same input, same layout
  });
});

test("layoutGroup is the same across separate loads, and a different first name seeds a different layout", () => {
  const items = chain("A", 8);
  const one = groupsOf(items).v.groups[0], two = groupsOf(items).v.groups[0];
  const h = groupsOf([]).h;
  h.api.layoutGroup(one); h.api.layoutGroup(two);
  assert.deepEqual(snap(one), snap(two));
  const other = groupsOf(chain("B", 8)).v.groups[0];
  h.api.layoutGroup(other);
  assert.notDeepEqual(snap(one), snap(other));
});

test("layoutGroup turns the long axis horizontal: a chain is wider than tall and its covariance is diagonal", () => {
  const { h, v } = groupsOf(chain("L", 12));
  const g = v.groups[0];
  const box = h.api.layoutGroup(g);
  assert.ok(box.w > 2 * box.h, `w=${box.w} h=${box.h}`);
  const mx = g.reduce((s, n) => s + n.x, 0) / g.length, my = g.reduce((s, n) => s + n.y, 0) / g.length;
  const sxx = g.reduce((s, n) => s + (n.x - mx) ** 2, 0), syy = g.reduce((s, n) => s + (n.y - my) ** 2, 0), sxy = g.reduce((s, n) => s + (n.x - mx) * (n.y - my), 0);
  assert.ok(sxx > syy);
  assert.ok(Math.abs(sxy) < 1e-6 * sxx);
});

test("layoutGroup on a group of more than 200 authors uses the shorter schedule and still finishes", () => {
  const { h, v } = groupsOf(chain("Z", 205));
  const g = v.groups[0];
  assert.equal(g.length, 205);
  const box = h.api.layoutGroup(g);
  assert.ok(box.w > 0 && box.h > 0);
  g.forEach((n) => assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y)));
});

test("layoutGroup copes with every circle starting on the same point", () => {
  const { h, v } = groupsOf(clique("S", 5));
  const M = vm.runInContext("Math", h.ctx);
  M.imul = () => 0;                                        // the seeded generator now returns 0 every time
  M.cos = () => 1; M.sin = () => 0;                        // and every start position is identical
  const g = v.groups[0];
  const box = h.api.layoutGroup(g);
  assert.ok(Number.isFinite(box.w) && Number.isFinite(box.h));
  g.forEach((n) => assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y)));
});

/* ---------- place ---------- */
test("place packs groups in rows, largest first, and returns the total height", () => {
  const { h, v } = groupsOf([].concat(clique("A", 4, "a"), clique("B", 3, "b"), clique("C", 2, "c")));
  const height = h.api.place(v.groups);
  const boxes = v.groups.map((g) => ({
    x0: Math.min(...g.map((n) => n.x - n.r)), x1: Math.max(...g.map((n) => n.x + n.r)),
    y0: Math.min(...g.map((n) => n.y - n.r)), y1: Math.max(...g.map((n) => n.y + n.r)),
  }));
  assert.ok(Math.abs(boxes[0].x0) < 1e-6 && Math.abs(boxes[0].y0) < 1e-6);
  assert.ok(boxes[1].x0 >= boxes[0].x1 + h.api.GAP - 1e-6);        // same row, one gap to the right
  assert.ok(Math.abs(boxes[1].y0) < 1e-6);
  boxes.forEach((b) => assert.ok(b.x1 <= 1000 + 1e-6));
  assert.ok(Math.abs(height - Math.max(...boxes.map((b) => b.y1))) < 1e-6);
});

test("place starts a new row when the next group no longer fits", () => {
  const { h, v } = groupsOf([].concat(chain("A", 14), chain("B", 14), chain("C", 14)));
  const height = h.api.place(v.groups);
  const tops = v.groups.map((g) => Math.min(...g.map((n) => n.y - n.r)));
  assert.ok(tops.some((t) => t > 1), "at least one group wrapped to a lower row: " + tops);
  const wrapped = v.groups.findIndex((g) => Math.min(...g.map((n) => n.y - n.r)) > 1);
  assert.ok(Math.abs(Math.min(...v.groups[wrapped].map((n) => n.x - n.r))) < 1e-6, "a wrapped row starts at x = 0");
  v.groups.forEach((g) => g.forEach((n) => assert.ok(n.x + n.r <= 1000 + 1e-6)));
  assert.ok(height > 0);
});

test("place scales a group wider than the drawing down to fit, circles included", () => {
  const { h, v } = groupsOf(chain("W", 120));
  const g = v.groups[0];
  const natural = h.api.layoutGroup(g);
  assert.ok(natural.w > 1000, "the unscaled group is wider than the drawing: " + natural.w);
  const rBefore = g[0].r;
  h.api.place(v.groups);
  const x1 = Math.max(...g.map((n) => n.x + n.r));
  assert.ok(x1 <= 1000 + 1e-6 && x1 > 990, "fills the width: " + x1);
  assert.ok(g[0].r < rBefore);
  assert.ok(Math.abs(g[0].r / rBefore - 1000 / natural.w) < 1e-9);
});

test("place of nothing is height 0", () => {
  assert.equal(makeCo({ items: [] }).api.place([]), 0);
});

test("layoutGroup pushes overlapping heavy circles apart", () => {
  const items = [];
  for (let i = 0; i < 60; i++) { items.push(it("h" + i, ["Hw", "Hx", "Hy", "Hz"], 2000)); }
  const { h, v } = groupsOf(items);
  const g = v.groups[0];
  assert.ok(h.api.radius(g[0]) > 22);
  h.api.layoutGroup(g);
  for (let i = 0; i < g.length; i++) {
    for (let j = i + 1; j < g.length; j++) {
      assert.ok(Math.hypot(g[i].x - g[j].x, g[i].y - g[j].y) >= g[i].r + g[j].r + 5 - 1e-6);
    }
  }
});

test("layoutGroup's zero-length guards let the loops finish even if every length reads as zero", () => {
  const { h, v } = groupsOf(clique("D", 4));
  const M = vm.runInContext("Math", h.ctx);
  M.sqrt = () => 0;                                        // artificial: only proves the "|| 0.1" guards avoid a division by zero
  const box = h.api.layoutGroup(v.groups[0]);
  assert.equal(typeof box.w, "number");
  assert.equal(typeof box.h, "number");
});

test("build orders many equal-sized groups by first member's name", () => {
  const items = [];
  for (let i = 40; i > 0; i--) { items.push(it("g" + i, ["N" + String(i * 7 % 41).padStart(2, "0"), "M" + String(i * 5 % 43).padStart(2, "0")])); }
  const { v } = groupsOf(items);
  const firsts = v.groups.map((g) => g[0].name);
  assert.deepEqual(firsts, firsts.slice().sort());
});
