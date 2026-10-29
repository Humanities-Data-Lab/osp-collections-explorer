/* OSP Collections Explorer, co-authorship page: vanilla JavaScript, no libraries.
   The filters select items; authors of the same item are tied together; the network, tables and counts are
   recomputed from the selected items on every change. The layout is a seeded force-directed layout, so the same
   selection always draws the same picture. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  var D = JSON.parse(document.getElementById("co-data").textContent);
  var ITEMS = D.items;
  var $ = function (id) { return document.getElementById(id); };
  var NS = "http://www.w3.org/2000/svg";
  var W = 1000, GAP = 30, K = 44;               // drawing width, space between groups, ideal edge length
  var state = { vol: [], topic: [], kind: [], from: "", to: "", tie: 1, group: 3, find: "", only: false, sel: "" };
  var view = null;                              // the most recent computed network

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function exploreUrl(name) { return "index.html?Author=" + encodeURIComponent(name); }

  /* ---------- state and address ---------- */
  function readAddress() {
    var p = new URLSearchParams(location.search);
    state.vol = p.getAll("Volume"); state.topic = p.getAll("Topic"); state.kind = p.getAll("Type");
    state.from = p.get("Year_from") || ""; state.to = p.get("Year_to") || "";
    state.tie = Math.max(1, parseInt(p.get("Tie"), 10) || 1);
    state.group = Math.max(2, parseInt(p.get("Group"), 10) || 3);
    state.find = p.get("Find") || ""; state.only = p.get("Only") === "1"; state.sel = p.get("Find") || "";
  }
  function writeAddress() {
    var p = new URLSearchParams();
    state.vol.forEach(function (v) { p.append("Volume", v); });
    state.topic.forEach(function (v) { p.append("Topic", v); });
    state.kind.forEach(function (v) { p.append("Type", v); });
    if (state.from) { p.set("Year_from", state.from); }
    if (state.to) { p.set("Year_to", state.to); }
    if (state.tie > 1) { p.set("Tie", state.tie); }
    if (state.group !== 3) { p.set("Group", state.group); }
    if (state.find) { p.set("Find", state.find); }
    if (state.only) { p.set("Only", "1"); }
    var q = p.toString();
    try { history.replaceState(null, "", location.pathname + (q ? "?" + q : "")); } catch (err) { /* saved file: leave the address alone */ }
  }
  function applyToControls() {
    ["Volume", "Topic", "Type"].forEach(function (k) {
      var list = k === "Volume" ? state.vol : k === "Topic" ? state.topic : state.kind;
      document.querySelectorAll('input[name="' + k + '"]').forEach(function (c) { c.checked = list.indexOf(c.value) !== -1; });
    });
    $("yfrom").value = state.from; $("yto").value = state.to;
    $("tie").value = String(state.tie); $("group").value = String(state.group);
    $("find").value = state.find; $("only").checked = state.only;
  }
  function readControls() {
    function vals(k) { return Array.prototype.map.call(document.querySelectorAll('input[name="' + k + '"]:checked'), function (c) { return c.value; }); }
    state.vol = vals("Volume"); state.topic = vals("Topic"); state.kind = vals("Type");
    state.from = $("yfrom").value.trim(); state.to = $("yto").value.trim();
    state.tie = parseInt($("tie").value, 10) || 1; state.group = parseInt($("group").value, 10) || 3;
    state.find = $("find").value.trim(); state.only = $("only").checked;
  }

  /* ---------- selecting items ---------- */
  function anyOf(wanted, have) {
    if (!wanted.length) { return true; }
    for (var i = 0; i < have.length; i++) { if (wanted.indexOf(have[i]) !== -1) { return true; } }
    return false;
  }
  function chosen() {
    var f = state.from === "" ? null : parseInt(state.from, 10), t = state.to === "" ? null : parseInt(state.to, 10);
    return ITEMS.filter(function (it) {
      if (!anyOf(state.vol, it.v) || !anyOf(state.topic, it.t) || !anyOf(state.kind, [it.k])) { return false; }
      if (f !== null && !isNaN(f) && (it.y === null || it.y < f)) { return false; }
      if (t !== null && !isNaN(t) && (it.y === null || it.y > t)) { return false; }
      return true;
    });
  }

  /* ---------- the network ---------- */
  function build(items) {
    var count = {}, ties = {}, perItem = [0, 0, 0, 0, 0, 0, 0];   // index 1..5 exact, 6 = six or more
    var withAuthors = 0, multi = 0;
    items.forEach(function (it) {
      var a = it.a.filter(function (n, i) { return it.a.indexOf(n) === i; }).sort();
      if (!a.length) { return; }
      withAuthors++; perItem[Math.min(a.length, 6)]++;
      a.forEach(function (n) { count[n] = (count[n] || 0) + 1; });
      if (a.length < 2) { return; }
      multi++;
      for (var i = 0; i < a.length; i++) {
        for (var j = i + 1; j < a.length; j++) {
          var key = a[i] + "\u0001" + a[j];
          (ties[key] = ties[key] || { a: a[i], b: a[j], items: [] }).items.push(it);
        }
      }
    });
    var edges = Object.keys(ties).map(function (k) { return ties[k]; }).filter(function (t) { return t.items.length >= state.tie; });
    var nodes = {}, order = [];
    function node(n) {
      if (!nodes[n]) { nodes[n] = { name: n, items: count[n], adj: [], co: {}, id: order.length }; order.push(nodes[n]); }
      return nodes[n];
    }
    edges.sort(function (x, y) { return x.a < y.a ? -1 : x.a > y.a ? 1 : x.b < y.b ? -1 : x.b > y.b ? 1 : 0; });
    edges.forEach(function (t) {
      var A = node(t.a), B = node(t.b);
      A.adj.push({ n: B, t: t }); B.adj.push({ n: A, t: t });
      t.items.forEach(function (it) { A.co[it.id] = it; B.co[it.id] = it; });
    });
    // groups: connected components
    var seen = {}, groups = [];
    order.forEach(function (n) {
      if (seen[n.name]) { return; }
      var stack = [n], g = [];
      seen[n.name] = true;
      while (stack.length) {
        var c = stack.pop(); g.push(c);
        c.adj.forEach(function (x) { if (!seen[x.n.name]) { seen[x.n.name] = true; stack.push(x.n); } });
      }
      g.sort(function (x, y) { return x.id - y.id; });
      groups.push(g);
    });
    groups.sort(function (x, y) { return y.length - x.length || (x[0].name < y[0].name ? -1 : 1); });
    groups.forEach(function (g, i) { g.forEach(function (n) { n.group = i; }); });
    return { count: count, edges: edges, nodes: order, groups: groups, perItem: perItem, withAuthors: withAuthors, multi: multi, items: items.length };
  }

  /* ---------- layout ---------- */
  function rng(seed) {                         // mulberry32
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0; var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function radius(n) { return 4 + 2.4 * Math.sqrt(n.items); }

  function layoutGroup(g) {
    var n = g.length, i, j, it;
    var idx = {}; g.forEach(function (m, k) { idx[m.name] = k; });
    var es = [];
    g.forEach(function (m) { m.adj.forEach(function (x) { if (idx[m.name] < idx[x.n.name]) { es.push([idx[m.name], idx[x.n.name], x.t.items.length]); } }); });
    var x = new Array(n), y = new Array(n), dx = new Array(n), dy = new Array(n), r = g.map(radius);
    if (n === 2) { x = [-K / 2, K / 2]; y = [0, 0]; }
    else {
      var rand = rng(hash(g[0].name)), R = K * Math.sqrt(n) / 2;
      for (i = 0; i < n; i++) { var ang = 2 * Math.PI * i / n + rand() * 0.5; x[i] = R * Math.cos(ang) * (0.6 + rand() * 0.4); y[i] = R * Math.sin(ang) * (0.6 + rand() * 0.4); }
      var iters = n > 200 ? 120 : 260, temp = K * 1.5;
      for (it = 0; it < iters; it++) {
        for (i = 0; i < n; i++) { dx[i] = 0; dy[i] = 0; }
        for (i = 0; i < n; i++) {
          for (j = i + 1; j < n; j++) {
            var ex = x[i] - x[j], ey = y[i] - y[j], d2 = ex * ex + ey * ey;
            if (d2 < 0.01) { ex = 0.1; ey = 0.1; d2 = 0.02; }
            var f = K * K / d2;
            dx[i] += ex * f; dy[i] += ey * f; dx[j] -= ex * f; dy[j] -= ey * f;
          }
        }
        es.forEach(function (e) {
          var a = e[0], b = e[1], ex = x[a] - x[b], ey = y[a] - y[b], d = Math.sqrt(ex * ex + ey * ey) || 0.1;
          var f = d / K * (1 + 0.35 * Math.min(e[2] - 1, 4));
          dx[a] -= ex * f; dy[a] -= ey * f; dx[b] += ex * f; dy[b] += ey * f;
        });
        for (i = 0; i < n; i++) {
          dx[i] -= x[i] * 0.02; dy[i] -= y[i] * 0.02;
          var m = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 0.1, s = Math.min(m, temp) / m;
          x[i] += dx[i] * s; y[i] += dy[i] * s;
        }
        temp = K * 1.5 * (1 - (it + 1) / iters) + 0.5;
      }
      for (var pass = 0; pass < 40; pass++) {          // push overlapping circles apart
        var moved = false;
        for (i = 0; i < n; i++) {
          for (j = i + 1; j < n; j++) {
            var ox = x[j] - x[i], oy = y[j] - y[i], d = Math.sqrt(ox * ox + oy * oy) || 0.1, min = r[i] + r[j] + 5;
            if (d < min) { var p = (min - d) / 2 / d; x[i] -= ox * p; y[i] -= oy * p; x[j] += ox * p; y[j] += oy * p; moved = true; }
          }
        }
        if (!moved) { break; }
      }
    }
    if (n > 2) {                                       // turn the long axis of the group to the horizontal
      var mx = 0, my = 0, sxx = 0, syy = 0, sxy = 0;
      for (i = 0; i < n; i++) { mx += x[i] / n; my += y[i] / n; }
      for (i = 0; i < n; i++) { sxx += (x[i] - mx) * (x[i] - mx); syy += (y[i] - my) * (y[i] - my); sxy += (x[i] - mx) * (y[i] - my); }
      var th = -0.5 * Math.atan2(2 * sxy, sxx - syy), c = Math.cos(th), sn = Math.sin(th);
      for (i = 0; i < n; i++) { var rx = x[i] - mx, ry = y[i] - my; x[i] = rx * c - ry * sn; y[i] = rx * sn + ry * c; }
    }
    var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (i = 0; i < n; i++) { x0 = Math.min(x0, x[i] - r[i]); x1 = Math.max(x1, x[i] + r[i]); y0 = Math.min(y0, y[i] - r[i]); y1 = Math.max(y1, y[i] + r[i]); }
    g.forEach(function (m, k) { m.x = x[k] - x0; m.y = y[k] - y0; m.r = r[k]; });
    return { w: x1 - x0, h: y1 - y0 };
  }

  function place(groups) {                        // shelf packing, largest group first
    var cx = 0, cy = 0, rowH = 0, scale;
    groups.forEach(function (g) {
      var box = layoutGroup(g);
      scale = box.w > W ? W / box.w : 1;
      if (scale < 1) { g.forEach(function (m) { m.x *= scale; m.y *= scale; m.r *= scale; }); box.w *= scale; box.h *= scale; }
      if (cx > 0 && cx + box.w > W) { cx = 0; cy += rowH + GAP; rowH = 0; }
      g.forEach(function (m) { m.x += cx; m.y += cy; });
      cx += box.w + GAP; rowH = Math.max(rowH, box.h);
    });
    return cy + rowH;
  }

  /* ---------- drawing ---------- */
  function drawNetwork(groups, height) {
    var host = $("network"), nodes = [], edges = [];
    groups.forEach(function (g) { g.forEach(function (n) { nodes.push(n); }); });
    var keep = {}; nodes.forEach(function (n) { keep[n.name] = true; });
    nodes.forEach(function (n) { n.adj.forEach(function (x) { if (n.name < x.n.name && keep[x.n.name]) { edges.push([n, x.n, x.t.items.length]); } }); });
    if (!nodes.length) { host.innerHTML = '<p class="empty">No authors share an item under these filters. Widen the filters, or lower the minimum shared items or group size.</p>'; return; }
    var sel = state.sel && keep[state.sel] ? state.sel : "", near = {};
    if (sel) { near[sel] = true; view.byName[sel].adj.forEach(function (x) { near[x.n.name] = true; }); }
    var s = '<svg viewBox="0 0 ' + W + " " + Math.ceil(height + 8) + '" role="group" aria-labelledby="net-cap" class="net' + (sel ? " has-sel" : "") + '" preserveAspectRatio="xMidYMin meet" focusable="false">';
    edges.forEach(function (e) {
      var on = sel && (e[0].name === sel || e[1].name === sel);
      s += '<line class="edge' + (on ? " on" : "") + '" x1="' + e[0].x.toFixed(1) + '" y1="' + e[0].y.toFixed(1) + '" x2="' + e[1].x.toFixed(1) + '" y2="' + e[1].y.toFixed(1) +
        '" stroke-width="' + (0.8 + 1.1 * Math.min(e[2] - 1, 4)).toFixed(1) + '"/>';
    });
    var labelled = labels(nodes, sel, near);
    nodes.forEach(function (n) {
      var cls = "node" + (n.name === sel ? " sel" : near[n.name] ? " near" : "");
      s += '<g class="' + cls + '" tabindex="0" role="button" data-n="' + esc(n.name) + '" aria-pressed="' + (n.name === sel) + '" aria-label="' + esc(n.name + ", " + n.items + (n.items === 1 ? " item, " : " items, ") + n.adj.length + (n.adj.length === 1 ? " co-author" : " co-authors")) + '">' +
        '<circle cx="' + n.x.toFixed(1) + '" cy="' + n.y.toFixed(1) + '" r="' + n.r.toFixed(1) + '"/><title>' + esc(n.name) + "</title></g>";
    });
    labelled.forEach(function (l) {
      s += '<text class="lbl" x="' + l.x.toFixed(1) + '" y="' + l.y.toFixed(1) + '" text-anchor="' + l.anchor + '" aria-hidden="true">' + esc(l.n.name) + "</text>";
    });
    host.innerHTML = s + "</svg>";
  }

  function labels(nodes, sel, near) {             // greedy, highest priority first, no overlaps
    var fs = 13, out = [], boxes = [];
    var rank = nodes.slice().sort(function (a, b) {
      var pa = (a.name === sel ? 3 : near[a.name] ? 2 : 0), pb = (b.name === sel ? 3 : near[b.name] ? 2 : 0);
      return pb - pa || b.items - a.items || b.adj.length - a.adj.length || (a.name < b.name ? -1 : 1);
    });
    rank.forEach(function (n) {
      if (out.length >= 90) { return; }
      var important = n.name === sel || near[n.name];
      if (!important && n.items < 3 && n.adj.length < 7) { return; }
      var w = n.name.length * fs * 0.58 + 4, h = fs, right = n.x + n.r + 3 + w < W - 2;
      var bx = right ? n.x + n.r + 3 : n.x - n.r - 3 - w, by = n.y - h / 2;
      for (var i = 0; i < boxes.length; i++) {
        var b = boxes[i];
        if (bx < b[0] + b[2] && bx + w > b[0] && by < b[1] + b[3] && by + h > b[1]) { return; }
      }
      boxes.push([bx, by, w, h]);
      out.push({ n: n, x: right ? bx : bx + w, y: n.y + fs * 0.35, anchor: right ? "start" : "end" });
    });
    return out;
  }

  /* ---------- tables, counts, panel ---------- */
  function nameButton(n) { return '<button type="button" class="linkish" data-sel="' + esc(n) + '">' + esc(n) + "</button>"; }
  function table(head, rows) {
    return '<div class="tablewrap" tabindex="0" role="region" aria-label="Scrollable table"><table class="data"><thead><tr>' +
      head.map(function (h) { return '<th scope="col">' + h + "</th>"; }).join("") + "</tr></thead><tbody>" + rows + "</tbody></table></div>";
  }
  function coCount(n) { return Object.keys(n.co).length; }

  function drawTables(v, shown) {
    var inView = {}; shown.forEach(function (g) { g.forEach(function (n) { inView[n.name] = true; }); });
    var people = v.nodes.filter(function (n) { return inView[n.name]; }).sort(function (a, b) {
      return coCount(b) - coCount(a) || b.adj.length - a.adj.length || (a.name < b.name ? -1 : 1);
    }).slice(0, 12);
    $("t-people").innerHTML = people.length ? table(["Author", "Items", "Co-authored items", "Co-authors"],
      people.map(function (n) { return "<tr><th scope=\"row\">" + nameButton(n.name) + "</th><td>" + n.items + "</td><td>" + coCount(n) + "</td><td>" + n.adj.length + "</td></tr>"; }).join("")) : '<p class="empty">None under these filters.</p>';

    var ties = v.edges.filter(function (t) { return inView[t.a] && inView[t.b] && t.items.length >= 2; }).sort(function (a, b) {
      return b.items.length - a.items.length || (a.a + a.b < b.a + b.b ? -1 : 1);
    }).slice(0, 15);
    $("t-ties").innerHTML = ties.length ? table(["Pair", "Shared items"],
      ties.map(function (t) { return "<tr><th scope=\"row\">" + nameButton(t.a) + " and " + nameButton(t.b) + "</th><td>" + t.items.length + "</td></tr>"; }).join("")) :
      '<p class="empty">No pair shares more than one item under these filters.</p>';

    var gs = v.groups.filter(function (g) { return g.length >= 2; }).slice(0, 12);
    $("t-groups").innerHTML = gs.length ? table(["Group", "Authors", "Most active members"],
      gs.map(function (g, i) {
        var top = g.slice().sort(function (a, b) { return b.items - a.items || (a.name < b.name ? -1 : 1); }).slice(0, 3);
        return "<tr><th scope=\"row\">" + (i + 1) + "</th><td>" + g.length + "</td><td>" + top.map(function (n) { return nameButton(n.name); }).join(", ") + "</td></tr>";
      }).join("")) : '<p class="empty">None under these filters.</p>';

    var names = ["1", "2", "3", "4", "5", "6 or more"], max = Math.max.apply(null, v.perItem.slice(1).concat([1]));
    $("t-per").innerHTML = '<ul class="sbars">' + names.map(function (nm, i) {
      var c = v.perItem[i + 1];
      return "<li><span class=\"lbl\">" + nm + (i === 0 ? " author" : " authors") + '</span><span class="track"><span class="fill" style="width:' + (100 * c / max).toFixed(1) + '%"></span></span><span class="num">' + c + "</span></li>";
    }).join("") + "</ul>";
  }

  function drawPanel() {
    var box = $("panel"), n = state.sel && view.byName[state.sel];
    if (!n) {
      box.innerHTML = "<h3>Selected author</h3><p>Select a circle in the network, or a name in a table, to see the author's co-authors and shared items.</p>";
      return;
    }
    var co = n.adj.slice().sort(function (a, b) { return b.t.items.length - a.t.items.length || (a.n.name < b.n.name ? -1 : 1); });
    var its = Object.keys(n.co).map(function (k) { return n.co[k]; }).sort(function (a, b) { return (a.y || 9999) - (b.y || 9999) || (a.n < b.n ? -1 : 1); });
    box.innerHTML = "<h3>" + esc(n.name) + "</h3><p>" + n.items + (n.items === 1 ? " item" : " items") + " in the current selection, " + its.length + " with a co-author. " +
      '<a href="' + exploreUrl(n.name) + '">Show this author in Explore</a>. <button type="button" class="secondary" id="clear-sel">Clear selection</button></p>' +
      "<h4>Co-authors (" + co.length + ")</h4><ul>" + co.map(function (x) { return "<li>" + nameButton(x.n.name) + ", " + x.t.items.length + (x.t.items.length === 1 ? " shared item" : " shared items") + "</li>"; }).join("") + "</ul>" +
      "<h4>Co-authored items (" + its.length + ")</h4><ul>" + its.map(function (it) { return '<li><a href="items/' + it.id + '.html">' + esc(it.n || it.id) + "</a>" + (it.y ? " (" + it.y + ")" : "") + "</li>"; }).join("") + "</ul>";
  }

  function status(v, shown, drawn) {
    var people = Object.keys(v.count).length, inNet = 0;
    shown.forEach(function (g) { inNet += g.length; });
    var share = v.withAuthors ? Math.round(100 * v.multi / v.withAuthors) : 0;
    var biggest = v.groups.length ? v.groups[0].length : 0;
    $("co-status").textContent = v.items.toLocaleString() + " items match the filters; " + v.withAuthors.toLocaleString() + " have a named author and " + v.multi.toLocaleString() + " (" + share + " percent) have more than one. " +
      people.toLocaleString() + " authors; " + inNet.toLocaleString() + " in the " + drawn + (drawn === 1 ? " group" : " groups") + " drawn. The largest group has " + biggest + " authors, counting groups of any size.";
    $("m-items").textContent = v.items.toLocaleString();
    $("m-multi").textContent = v.multi.toLocaleString() + " (" + share + "%)";
    $("m-authors").textContent = people.toLocaleString();
    $("m-ties").textContent = v.edges.length.toLocaleString();
    $("m-groups").textContent = v.groups.length.toLocaleString();
    $("m-largest").textContent = String(biggest);
  }

  /* ---------- whole update ---------- */
  function update() {
    writeAddress();
    var v = build(chosen());
    v.byName = {}; v.nodes.forEach(function (n) { v.byName[n.name] = n; });
    view = v;
    var found = state.find && v.byName[state.find] ? state.find : "";
    if (state.find && !found) { state.sel = state.sel === state.find ? "" : state.sel; }
    if (found) { state.sel = found; }
    if (state.sel && !v.byName[state.sel]) { state.sel = ""; }
    var shown = v.groups.filter(function (g) { return g.length >= state.group; });
    if (state.only && found) { shown = shown.filter(function (g) { return g[0].group === v.byName[found].group; }); }
    $("find-note").textContent = state.find && !found ? "No co-authorship for \"" + state.find + "\" under these filters." : "";
    var height = shown.length ? place(shown) : 0;
    view.shown = shown; view.height = height;
    drawNetwork(shown, height);
    drawTables(v, shown);
    drawPanel();
    status(v, shown, shown.length);
  }

  function select(name) {
    state.sel = name || "";
    if (!name) { state.find = ""; $("find").value = ""; }
    drawNetwork(view.shown, view.height); drawPanel(); writeAddress();
  }

  /* ---------- events ---------- */
  var timer = null;
  function changed(delay) {
    clearTimeout(timer);
    timer = setTimeout(function () { readControls(); update(); }, delay || 0);
  }
  document.querySelectorAll("#co-filters input, #co-filters select").forEach(function (c) {
    c.addEventListener(c.type === "checkbox" || c.tagName === "SELECT" ? "change" : "input", function () { changed(c.type === "checkbox" || c.tagName === "SELECT" ? 0 : 250); });
  });
  $("co-reset").addEventListener("click", function () {
    state = { vol: [], topic: [], kind: [], from: "", to: "", tie: 1, group: 3, find: "", only: false, sel: "" };
    applyToControls(); update();
  });
  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-n],[data-sel],#clear-sel") : null;
    if (!t) { return; }
    if (t.id === "clear-sel") { select(""); return; }
    var name = t.getAttribute("data-n") || t.getAttribute("data-sel");
    select(name === state.sel ? "" : name);
    if (t.hasAttribute("data-sel")) { $("network").scrollIntoView({ block: "nearest" }); }
  });
  document.addEventListener("keydown", function (ev) {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target.getAttribute && ev.target.getAttribute("data-n") && ev.target.tagName.toLowerCase() === "g") {
      ev.preventDefault(); var name = ev.target.getAttribute("data-n"); select(name === state.sel ? "" : name);
      var again = document.querySelector('[data-n="' + name.replace(/"/g, '\\"') + '"]'); if (again) { again.focus(); }
    }
  });

  readAddress(); applyToControls(); update();

  /* Test hook only: browsers inline this script as a plain <script>, where `module` is undefined and this does nothing. */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      esc: esc, exploreUrl: exploreUrl, readAddress: readAddress, writeAddress: writeAddress, applyToControls: applyToControls,
      readControls: readControls, anyOf: anyOf, chosen: chosen, build: build, rng: rng, hash: hash, radius: radius,
      layoutGroup: layoutGroup, place: place, drawNetwork: drawNetwork, labels: labels, nameButton: nameButton, table: table,
      coCount: coCount, drawTables: drawTables, drawPanel: drawPanel, status: status, update: update, select: select,
      changed: changed, W: W, GAP: GAP, K: K,
      getState: function () { return state; }, getView: function () { return view; }
    };
  }
})();
