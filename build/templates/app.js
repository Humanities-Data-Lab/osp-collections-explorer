/* OSP Collections Explorer: vanilla JavaScript, no dependencies. */
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("osp-data").textContent);
  var ITEMS = DATA.items;
  var VOLS = DATA.volumes;
  var PAGE = 25;
  var $ = function (id) { return document.getElementById(id); };

  function fold(s) {
    return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  ITEMS.forEach(function (it) {
    it._authors = fold(it.authors.join(" ; "));
    it._title = fold(it.title);
    it._container = fold(it.container);
    it._note = fold(it.annotation);
    it._sections = fold(it.sections.join(" ; ") + " ; " + it.chapters.join(" ; "));
    it._topics = fold(it.topics.join(" ; "));
    it._vols = fold(it.volumes.join(" ; "));
    it._kind = fold(it.kind);
    it._all = [it._title, it._authors, it._container, it._note, it._sections, it._topics].join(" \n ");
  });

  var state = { q: "", volume: [], topic: [], kind: [], source: [], from: "", to: "", author: "", sort: "relevance", shown: PAGE };
  var FACETS = [
    { key: "volume", label: "Volume", get: function (it) { return it.volumes; } },
    { key: "topic", label: "Topic", get: function (it) { return it.topics; } },
    { key: "kind", label: "Type", get: function (it) { return [it.kind]; } },
    { key: "source", label: "Annotation source", get: function (it) { return it.annotation_source; } }
  ];

  /* ---------- query language ---------- */
  var FIELD = {
    author: "_authors", title: "_title", in: "_container", journal: "_container", container: "_container",
    note: "_note", annotation: "_note", section: "_sections", chapter: "_sections", topic: "_topics",
    vol: "_vols", volume: "_vols", type: "_kind", kind: "_kind"
  };
  function parseQuery(q) {
    var clauses = [], re = /(-?)(?:([a-zA-Z]+):)?(?:"([^"]*)"|(\S+))/g, m, joinNext = false;
    while ((m = re.exec(q))) {
      if (!m[1] && !m[2] && m[4] === "OR" && clauses.length) { joinNext = true; continue; }
      var field = m[2] ? m[2].toLowerCase() : "", text = m[3] !== undefined ? m[3] : m[4];
      var term = { neg: !!m[1], field: field, text: fold(text), raw: text };
      if (field === "year" || field === "doi") {
        if (field === "year") {
          var r = text.match(/^(\d{4})?\s*(\.\.|-)\s*(\d{4})?$/), g = text.match(/^([<>])=?(\d{4})$/);
          if (r) term.range = [r[1] ? +r[1] : -Infinity, r[3] ? +r[3] : Infinity];
          else if (g) term.range = g[1] === ">" ? [+g[2], Infinity] : [-Infinity, +g[2]];
          else if (/^\d{4}$/.test(text)) term.range = [+text, +text];
        }
      } else if (field && !FIELD[field]) {
        term.field = ""; term.text = fold(m[2] + ":" + text); // unknown field: treat as plain text
      }
      if (!term.text) continue;
      if (joinNext) { clauses[clauses.length - 1].push(term); joinNext = false; } else { clauses.push([term]); }
    }
    return clauses;
  }
  function termMatches(t, it) {
    var hit;
    if (t.field === "year") hit = t.range ? (it.year !== null && it.year >= t.range[0] && it.year <= t.range[1]) : false;
    else if (t.field === "doi") hit = fold(it.doi + " " + it.url).indexOf(t.text) !== -1;
    else hit = it[t.field ? FIELD[t.field] : "_all"].indexOf(t.text) !== -1;
    return t.neg ? !hit : hit;
  }
  function matchesQuery(clauses, it) {
    for (var i = 0; i < clauses.length; i++) {
      var ok = false;
      for (var j = 0; j < clauses[i].length; j++) { if (termMatches(clauses[i][j], it)) { ok = true; break; } }
      if (!ok) return false;
    }
    return true;
  }
  function count(hay, needle) {
    var n = 0, i = 0;
    while ((i = hay.indexOf(needle, i)) !== -1) { n++; i += needle.length; }
    return n;
  }
  function score(clauses, it) {
    var s = 0;
    clauses.forEach(function (c) {
      c.forEach(function (t) {
        if (t.neg || t.field === "year") return;
        if (!t.field || t.field === "title") s += 5 * count(it._title, t.text);
        if (!t.field || t.field === "author") s += 4 * count(it._authors, t.text);
        if (!t.field || t.field === "section") s += 2 * count(it._sections, t.text);
        if (!t.field || t.field === "note") s += Math.min(5, count(it._note, t.text));
      });
    });
    return s;
  }
  function highlightTerms(clauses) {
    var out = [];
    clauses.forEach(function (c) { c.forEach(function (t) {
      if (!t.neg && t.field !== "year" && t.field !== "doi" && t.text.length > 1) out.push(t.text);
    }); });
    return out;
  }
  function highlight(text, terms) {
    if (!terms.length) return esc(text);
    var f = fold(text);
    if (f.length !== text.length) return esc(text);
    var spans = [];
    terms.forEach(function (t) {
      var i = 0;
      while ((i = f.indexOf(t, i)) !== -1) { spans.push([i, i + t.length]); i += t.length; }
    });
    if (!spans.length) return esc(text);
    spans.sort(function (a, b) { return a[0] - b[0]; });
    var out = "", pos = 0;
    spans.forEach(function (s) {
      if (s[0] < pos) { if (s[1] > pos) { out += "<mark>" + esc(text.slice(pos, s[1])) + "</mark>"; pos = s[1]; } return; }
      out += esc(text.slice(pos, s[0])) + "<mark>" + esc(text.slice(s[0], s[1])) + "</mark>";
      pos = s[1];
    });
    return out + esc(text.slice(pos));
  }
  function snippet(it, terms) {
    var t = it.annotation;
    if (!t) return "";
    var f = fold(t), at = -1;
    if (f.length === t.length) {
      for (var i = 0; i < terms.length; i++) { var p = f.indexOf(terms[i]); if (p !== -1 && (at === -1 || p < at)) at = p; }
    }
    var start = at > 140 ? at - 120 : 0, end = Math.min(t.length, start + 300);
    var piece = t.slice(start, end);
    if (start > 0) piece = "…" + piece.slice(piece.indexOf(" ") + 1);
    if (end < t.length) piece = piece.slice(0, piece.lastIndexOf(" ")) + "…";
    return highlight(piece, terms);
  }

  /* ---------- filtering ---------- */
  function passes(it, clauses, skip) {
    if (!matchesQuery(clauses, it)) return false;
    for (var i = 0; i < FACETS.length; i++) {
      var f = FACETS[i], sel = state[f.key];
      if (f.key === skip || !sel.length) continue;
      var vals = f.get(it), ok = false;
      for (var j = 0; j < sel.length; j++) { if (vals.indexOf(sel[j]) !== -1) { ok = true; break; } }
      if (!ok) return false;
    }
    if (skip !== "year") {
      var lo = state.from === "" ? -Infinity : +state.from, hi = state.to === "" ? Infinity : +state.to;
      if (lo !== -Infinity || hi !== Infinity) { if (it.year === null || it.year < lo || it.year > hi) return false; }
    }
    if (skip !== "author" && state.author && it.authors.indexOf(state.author) === -1) return false;
    return true;
  }
  function run(skip) {
    var clauses = parseQuery(state.q);
    return ITEMS.filter(function (it) { return passes(it, clauses, skip); });
  }

  /* ---------- URL hash (no query strings, per Endings 4.4) ---------- */
  function writeHash() {
    var p = [];
    function add(k, v) { if (v) p.push(k + "=" + encodeURIComponent(v)); }
    add("q", state.q);
    FACETS.forEach(function (f) { add(f.key, state[f.key].join("|")); });
    add("from", state.from); add("to", state.to); add("author", state.author);
    if (state.sort !== "relevance") add("sort", state.sort);
    var h = p.length ? "#" + p.join("&") : "";
    try { history.replaceState(null, "", location.pathname + h); } catch (e) { /* file:// or sandbox */ }
  }
  function readHash() {
    var h = location.hash.replace(/^#/, ""), map = {};
    h.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) { try { map[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1)); } catch (e) { /* ignore */ } }
    });
    state.q = map.q || "";
    FACETS.forEach(function (f) { state[f.key] = map[f.key] ? map[f.key].split("|") : []; });
    state.from = /^\d{4}$/.test(map.from || "") ? map.from : "";
    state.to = /^\d{4}$/.test(map.to || "") ? map.to : "";
    state.author = map.author || "";
    state.sort = map.sort || "relevance";
    state.shown = PAGE;
  }

  /* ---------- rendering ---------- */
  var elResults = $("results"), elStatus = $("status"), elFacets = $("facets"), elChips = $("chips");

  function toggle(arr, v) { var i = arr.indexOf(v); if (i === -1) arr.push(v); else arr.splice(i, 1); }

  function renderFacets() {
    var html = "";
    FACETS.forEach(function (f) {
      var pool = run(f.key), counts = {};
      pool.forEach(function (it) { f.get(it).forEach(function (v) { counts[v] = (counts[v] || 0) + 1; }); });
      var all = {};
      ITEMS.forEach(function (it) { f.get(it).forEach(function (v) { all[v] = 1; }); });
      var names = Object.keys(all).sort(function (a, b) { return (counts[b] || 0) - (counts[a] || 0) || a.localeCompare(b); });
      html += '<fieldset><legend>' + f.label + '</legend><div class="' + (names.length > 8 ? "scroll" : "") + '">';
      var stable = Object.keys(all).sort();
      names.forEach(function (v) {
        var id = "f-" + f.key + "-" + stable.indexOf(v);
        var c = counts[v] || 0, on = state[f.key].indexOf(v) !== -1;
        html += '<label class="opt' + (c === 0 && !on ? " zero" : "") + '" for="' + id + '"><input type="checkbox" id="' + id +
          '" data-facet="' + f.key + '" value="' + esc(v) + '"' + (on ? " checked" : "") + '><span>' + esc(v) +
          '</span><span class="n" aria-label="' + c + ' items">' + c + "</span></label>";
      });
      html += "</div></fieldset>";
    });
    html += '<fieldset><legend>Year</legend><div class="yearrange"><label for="yfrom">From</label>' +
      '<input type="number" id="yfrom" inputmode="numeric" min="1500" max="2100" value="' + esc(state.from) + '">' +
      '<label for="yto">To</label><input type="number" id="yto" inputmode="numeric" min="1500" max="2100" value="' + esc(state.to) + '"></div></fieldset>';
    var fx = document.activeElement && document.activeElement.id;
    elFacets.innerHTML = html;
    if (fx && $(fx)) $(fx).focus();
  }

  function renderChips() {
    var chips = [];
    FACETS.forEach(function (f) { state[f.key].forEach(function (v) { chips.push([f.label + ": " + v, f.key, v]); }); });
    if (state.from || state.to) chips.push(["Year: " + (state.from || "…") + "–" + (state.to || "…"), "year", ""]);
    if (state.author) chips.push(["Author: " + state.author, "author", ""]);
    elChips.innerHTML = chips.map(function (c) {
      return '<li class="chip">' + esc(c[0]) + '<button type="button" data-chip="' + c[1] + '" data-v="' + esc(c[2]) +
        '" aria-label="Remove filter ' + esc(c[0]) + '">×</button></li>';
    }).join("");
    $("reset").hidden = !chips.length && !state.q;
  }

  function sorted(list, clauses) {
    var a = list.slice();
    var byAuthor = function (x, y) { return fold(x.authors[0] || "").localeCompare(fold(y.authors[0] || "")) || (x.year || 0) - (y.year || 0); };
    if (state.sort === "relevance" && clauses.length) {
      a.forEach(function (it) { it._s = score(clauses, it); });
      a.sort(function (x, y) { return y._s - x._s || byAuthor(x, y); });
    } else if (state.sort === "year-desc") a.sort(function (x, y) { return (y.year || 0) - (x.year || 0) || byAuthor(x, y); });
    else if (state.sort === "year-asc") a.sort(function (x, y) { return (x.year || 9999) - (y.year || 9999) || byAuthor(x, y); });
    else if (state.sort === "title") a.sort(function (x, y) { return x._title.localeCompare(y._title); });
    else a.sort(byAuthor);
    return a;
  }

  function card(it, terms) {
    var vols = it.volumes.map(function (v) { return '<li class="tag vol">' + esc(v) + "</li>"; }).join("");
    var topics = it.topics.map(function (t) { return '<li class="tag">' + esc(t) + "</li>"; }).join("");
    var links = "";
    var href = it.doi ? "https://doi.org/" + it.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, "") : it.url;
    if (href) links += '<a href="' + esc(href) + '" rel="noopener">Open source ' + (it.doi ? "(DOI)" : "(link)") + "</a>";
    var by = it.authors.length ? esc(it.authors.slice(0, 4).join(", ") + (it.authors.length > 4 ? " et al." : "")) : "No named author";
    var full = it.annotation.length > 320 ? '<details><summary>Full annotation</summary><p>' + highlight(it.annotation, terms) + "</p></details>" : "";
    return '<li class="card"><h3><a href="items/' + it.id + '.html">' + highlight(it.title || it.citation, terms) + "</a></h3>" +
      '<p class="by"><strong>' + by + "</strong> · " + (it.year || "n.d.") + " · " + esc(it.kind) +
      (it.container ? " · " + esc(it.container.length > 90 ? it.container.slice(0, 88) + "…" : it.container) : "") + "</p>" +
      (it.annotation ? '<p class="snippet">' + snippet(it, terms) + "</p>" : '<p class="snippet by">No annotation in the source volume.</p>') + full +
      '<ul class="tags" aria-label="Volumes and topics">' + vols + topics + "</ul>" +
      '<div class="links">' + links + '<a href="items/' + it.id + '.html">Record page</a></div></li>';
  }

  function renderResults(list, clauses) {
    var terms = highlightTerms(clauses), a = sorted(list, clauses), n = Math.min(state.shown, a.length);
    var html = a.slice(0, n).map(function (it) { return card(it, terms); }).join("");
    if (!a.length) html = '<li class="card">No items match. Remove a filter or simplify the query.</li>';
    elResults.innerHTML = html;
    var more = $("more");
    more.hidden = n >= a.length;
    more.textContent = "Show " + Math.min(PAGE, a.length - n) + " more (" + n + " of " + a.length + " shown)";
    elStatus.textContent = a.length + " of " + ITEMS.length + " items" + (state.q ? ' match "' + state.q + '"' : "");
  }

  /* ---------- charts (semantic HTML) ---------- */
  function barList(entries, selected, key, label) {
    var max = entries.reduce(function (m, e) { return Math.max(m, e[1]); }, 1);
    return '<ul class="bars" aria-label="' + esc(label) + '">' + entries.map(function (e) {
      return '<li><button type="button" class="bar" data-fk="' + key + "-" + esc(e[0]) + '" data-chart="' + key + '" data-v="' + esc(e[0]) +
        '" aria-pressed="' + (selected.indexOf(e[0]) !== -1) + '"><span class="lbl">' + esc(e[0]) + '</span><span class="track"><span class="fill" style="width:' +
        Math.max(1, Math.round(100 * e[1] / max)) + '%"></span></span><span class="num">' + e[1] + "</span></button></li>";
    }).join("") + "</ul>";
  }
  function tally(list, fn) {
    var c = {};
    list.forEach(function (it) { fn(it).forEach(function (v) { c[v] = (c[v] || 0) + 1; }); });
    return Object.keys(c).map(function (k) { return [k, c[k]]; });
  }

  function renderCharts(list) {
    // 1. Year histogram: one column per year from 1990, one column for earlier work.
    var bins = {}, early = 0, undated = 0;
    list.forEach(function (it) {
      if (it.year === null) undated++; else if (it.year < 1990) early++; else bins[it.year] = (bins[it.year] || 0) + 1;
    });
    var cols = [["Before 1990", early, "", 1989]];
    for (var y = 1990; y <= 2025; y++) cols.push([String(y), bins[y] || 0, y, y]);
    var max = cols.reduce(function (m, c) { return Math.max(m, c[1]); }, 1);
    var hist = '<div class="hist" role="group" aria-label="Items per year">' + cols.map(function (c) {
      var on = c[3] === 1989 ? (state.to === "1989" && state.from === "") : (state.from === String(c[3]) && state.to === String(c[3]));
      return '<button type="button" data-fk="yr-' + c[3] + '" data-chart="year" data-y="' + c[3] + '" aria-pressed="' + on + '" aria-label="' + c[0] + ": " + c[1] + ' items"><span class="cnt">' + (c[1] || "") +
        '</span><span class="col" style="height:' + Math.round(100 * c[1] / max * 0.7) + '%"></span><span class="yr">' + (c[3] === 1989 ? "&lt;1990" : c[0]) + "</span></button>";
    }).join("") + "</div>";
    var htable = '<details><summary>View as table</summary><div class="scroll"><table class="data"><caption class="sr">Items per year</caption><thead><tr><th scope="col">Year</th><th scope="col">Items</th></tr></thead><tbody>' +
      cols.map(function (c) { return '<tr><th scope="row">' + c[0] + "</th><td>" + c[1] + "</td></tr>"; }).join("") + "</tbody></table></div></details>";
    $("chart-year").innerHTML = '<figcaption>Items by year of publication</figcaption><p class="sub">Select a column to filter by that year. ' +
      (undated ? undated + " items have no date." : "") + "</p>" + hist + htable;

    // 2. Volumes
    var vt = tally(list, function (it) { return it.volumes; }).sort(function (a, b) { return b[1] - a[1]; });
    $("chart-volume").innerHTML = '<figcaption>Items by volume</figcaption><p class="sub">An item counts once in each volume that includes it.</p>' + barList(vt, state.volume, "volume", "Items by volume");

    // 3. Authors
    var at = tally(list, function (it) { return it.authors; }).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); }).slice(0, 12);
    $("chart-author").innerHTML = '<figcaption>Most frequent authors</figcaption><p class="sub">Select a name to filter. Names are split from citations by a heuristic, so organisations and unusual names may vary.</p>' +
      barList(at, state.author ? [state.author] : [], "author", "Most frequent authors");

    // 4. Topic by volume heat table
    var topics = DATA.topics, vnames = VOLS.map(function (v) { return v.title; }), m = {}, mx = 1;
    list.forEach(function (it) { it.topics.forEach(function (t) { it.volumes.forEach(function (v) { var k = t + "\u0000" + v; m[k] = (m[k] || 0) + 1; mx = Math.max(mx, m[k]); }); }); });
    var head = "<tr><th scope=\"col\">Topic</th>" + vnames.map(function (v) { return '<th scope="col">' + esc(v.replace("Knowledge Mobilization in the Humanities", "Knowl. Mobilization").replace("Engaging ", "").replace(" in Open Scholarship", "")) + "</th>"; }).join("") + "</tr>";
    var body = topics.map(function (t) {
      return '<tr><th scope="row">' + esc(t) + "</th>" + vnames.map(function (v) {
        var n = m[t + "\u0000" + v] || 0;
        if (!n) return '<td class="zero">0</td>';
        var on = state.topic.length === 1 && state.topic[0] === t && state.volume.length === 1 && state.volume[0] === v;
        return '<td><button type="button" data-fk="h-' + esc(t + v) + '" data-chart="heat" data-t="' + esc(t) + '" data-v="' + esc(v) + '" style="--v:' + (n / mx).toFixed(2) +
          '" aria-pressed="' + on + '" aria-label="' + esc(t) + ", " + esc(v) + ": " + n + ' items. Select to filter.">' + n + "</button></td>";
      }).join("") + "</tr>";
    }).join("");
    $("chart-heat").innerHTML = '<figcaption>Topics across volumes</figcaption><p class="sub">Counts of items per detected topic and volume; shading follows the count. Select a number to filter by that topic and volume.</p><div class="heat"><table><caption class="sr">Items by topic and volume</caption><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";

    // 5. Overlap
    var ov = {};
    list.forEach(function (it) { it.volumes.forEach(function (a) { it.volumes.forEach(function (b) { var k = a + "\u0000" + b; ov[k] = (ov[k] || 0) + 1; }); }); });
    var ohead = "<tr><th scope=\"col\"><span class=\"sr\">Volume</span></th>" + vnames.map(function (v) { return '<th scope="col">' + esc(v.split(" ")[0] === "Engaging" ? v.split(" ")[1] : v.split(" ")[0]) + "</th>"; }).join("") + "</tr>";
    var obody = vnames.map(function (a) {
      return '<tr><th scope="row">' + esc(a) + "</th>" + vnames.map(function (b) { return "<td>" + (ov[a + "\u0000" + b] || 0) + "</td>"; }).join("") + "</tr>";
    }).join("");
    $("chart-overlap").innerHTML = '<figcaption>Shared items between volumes</figcaption><p class="sub">Each cell counts items that appear in both volumes. The diagonal gives each volume’s total.</p><div class="heat"><table><caption class="sr">Items shared between volumes</caption><thead>' + ohead + "</thead><tbody>" + obody + "</tbody></table></div>";
  }

  /* ---------- update cycle ---------- */
  function update(opts) {
    var focusKey = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute("data-fk");
    var list = run(), clauses = parseQuery(state.q);
    if (!opts || !opts.keepFacets) renderFacets();
    renderChips();
    renderResults(list, clauses);
    renderCharts(list);
    $("sort").value = state.sort;
    $("q").value = state.q;
    $("relevance-opt").disabled = !clauses.length;
    if (focusKey) { var el = document.querySelector('[data-fk="' + focusKey.replace(/"/g, '\\"') + '"]'); if (el) el.focus(); }
    writeHash();
  }

  /* ---------- events ---------- */
  $("search-form").addEventListener("submit", function (e) { e.preventDefault(); state.q = $("q").value.trim(); state.shown = PAGE; update(); });
  var timer;
  $("q").addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { state.q = $("q").value.trim(); state.shown = PAGE; update({ keepFacets: false }); }, 250);
  });
  $("sort").addEventListener("change", function (e) { state.sort = e.target.value; update({ keepFacets: true }); });
  $("more").addEventListener("click", function () {
    var before = state.shown; state.shown += PAGE; update({ keepFacets: true });
    var cards = elResults.querySelectorAll(".card h3 a"); if (cards[before]) cards[before].focus();
  });
  $("reset").addEventListener("click", function () {
    state = { q: "", volume: [], topic: [], kind: [], source: [], from: "", to: "", author: "", sort: "relevance", shown: PAGE };
    update(); $("q").focus();
  });
  elFacets.addEventListener("change", function (e) {
    var t = e.target;
    if (t.dataset.facet) { toggle(state[t.dataset.facet], t.value); }
    else if (t.id === "yfrom") state.from = /^\d{4}$/.test(t.value) ? t.value : "";
    else if (t.id === "yto") state.to = /^\d{4}$/.test(t.value) ? t.value : "";
    state.shown = PAGE; update();
  });
  elChips.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-chip]"); if (!b) return;
    var k = b.dataset.chip;
    if (k === "year") { state.from = ""; state.to = ""; } else if (k === "author") state.author = ""; else toggle(state[k], b.dataset.v);
    state.shown = PAGE; update(); $("q").focus();
  });
  $("viz").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-chart]"); if (!b) return;
    var c = b.dataset.chart;
    if (c === "volume") toggle(state.volume, b.dataset.v);
    else if (c === "author") state.author = state.author === b.dataset.v ? "" : b.dataset.v;
    else if (c === "year") {
      var y = b.dataset.y, early = y === "1989";
      var on = early ? (state.to === "1989" && state.from === "") : (state.from === y && state.to === y);
      if (on) { state.from = ""; state.to = ""; } else if (early) { state.from = ""; state.to = "1989"; } else { state.from = y; state.to = y; }
    } else if (c === "heat") {
      var same = state.topic.length === 1 && state.topic[0] === b.dataset.t && state.volume.length === 1 && state.volume[0] === b.dataset.v;
      state.topic = same ? [] : [b.dataset.t]; state.volume = same ? [] : [b.dataset.v];
    }
    state.shown = PAGE; update();
  });
  window.addEventListener("hashchange", function () { readHash(); update(); });

  readHash();
  document.documentElement.classList.add("js");
  update();
})();
