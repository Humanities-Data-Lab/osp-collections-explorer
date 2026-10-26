/* OSP Collections Explorer: vanilla JavaScript.
   Searching and filtering are done by staticSearch (Project Endings), whose form and engine are embedded in this page.
   This script receives the matching documents through staticSearch's searchFinishedHook and draws the cards and charts. */
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("osp-data").textContent);
  var ITEMS = DATA.items;
  var VOLS = DATA.volumes;
  var BY = {};
  var PAGE = 25;
  var Sch = null;        // the staticSearch instance, or null when search is unavailable
  var hits = null;       // Map: item id -> {score, contexts}; null means "every item"
  var state = { sort: "relevance", shown: PAGE };
  var $ = function (id) { return document.getElementById(id); };

  function fold(s) { return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  ITEMS.forEach(function (it) { BY[it.id] = it; it._title = fold(it.title); });

  /* ---------- state read from the controls staticSearch maintains ---------- */
  function params() { return new URLSearchParams(decodeURI(location.search)); }
  function selected(key) { return Sch ? params().getAll(key) : []; }
  function yearRange() { var p = params(); return [p.get("Year_from") || "", p.get("Year_to") || ""]; }

  function current() {
    return hits ? ITEMS.filter(function (it) { return hits.has(it.id); }) : ITEMS.slice();
  }

  /* ---------- receiving results from staticSearch ---------- */
  function onSearchDone(num) {
    var sch = Sch, map = new Map();
    var noInput = sch.queryBox.value.trim() === "" && !sch.docsMatchingFilters.filtersActive;
    if (num === 5) { return; }                                  // staticSearch reported an error
    if (noInput) { hits = null; }
    else {
      sch.resultSet.mapDocs.forEach(function (d, uri) {
        map.set(uri.replace(/\.html$/, ""), { score: d.score, contexts: d.contexts || [] });
      });
      hits = map;
    }
    state.shown = PAGE;
    update();
  }

  function setControls(fn) {
    if (!Sch) { return; }
    fn();
    Sch.doSearch();
  }
  function descBox(title, value) {
    return Sch.descFilterCheckboxes.filter(function (c) { return c.getAttribute("title") === title && c.value === value; })[0];
  }
  function dateInput(suffix) {
    return Sch.dateFilterTextboxes.filter(function (t) { return t.getAttribute("title") === "Year" && t.id.slice(-suffix.length) === suffix; })[0];
  }
  function toggleDesc(title, value) { var c = descBox(title, value); if (c) { c.checked = !c.checked; } }

  /* ---------- rendering ---------- */
  function people(list, suffix) {
    if (!list.length) { return ""; }
    return esc(list.slice(0, 4).join(", ") + (list.length > 4 ? " et al." : "")) + suffix;
  }
  function contextHtml(h) {
    if (!h || !h.contexts.length) { return ""; }
    var parts = h.contexts.slice().sort(function (a, b) { return a.pos - b.pos; }).slice(0, 2).map(function (c) {
      return esc(c.context).replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
    });
    return parts.join(" … ");
  }
  function snippet(it, h) {
    var ctx = contextHtml(h);
    if (ctx) { return ctx; }
    var t = it.annotation;
    if (!t) { return ""; }
    return esc(t.length > 300 ? t.slice(0, t.lastIndexOf(" ", 300)) + "…" : t);
  }

  function card(it) {
    var h = hits ? hits.get(it.id) : null;
    var vols = it.volumes.map(function (v) { return '<li class="tag vol">' + esc(v) + "</li>"; }).join("");
    var topics = it.topics.map(function (t) { return '<li class="tag">' + esc(t) + "</li>"; }).join("");
    var href = it.doi ? "https://doi.org/" + it.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, "") : it.url;
    var links = href ? '<a href="' + esc(href) + '" rel="noopener">Open source ' + (it.doi ? "(DOI)" : "(link)") + "</a>" : "";
    var by = people(it.authors, "") || people(it.editors, it.editors.length > 1 ? " (eds.)" : " (ed.)") || "No named author";
    var sn = snippet(it, h);
    var full = it.annotation.length > 320 ? "<details><summary>Full annotation</summary><p>" + esc(it.annotation) + "</p></details>" : "";
    return '<li class="card"><h3><a href="items/' + it.id + '.html">' + esc(it.title || it.citation) + "</a></h3>" +
      '<p class="by"><strong>' + by + "</strong> · " + (it.year || "n.d.") + " · " + esc(it.kind) +
      (it.container ? " · " + esc(it.container.length > 90 ? it.container.slice(0, 88) + "…" : it.container) : "") + "</p>" +
      (sn ? '<p class="snippet">' + sn + "</p>" : '<p class="snippet by">No annotation in the source volume.</p>') + full +
      '<ul class="tags" aria-label="Volumes and topics">' + vols + topics + "</ul>" +
      '<div class="links">' + links + '<a href="items/' + it.id + '.html">Record page</a></div></li>';
  }

  function sorted(list) {
    var a = list.slice();
    var lead = function (x) { return fold(x.authors[0] || x.editors[0] || ""); };
    var byAuthor = function (x, y) { return lead(x).localeCompare(lead(y)) || (x.year || 0) - (y.year || 0); };
    var score = function (x) { return hits && hits.get(x.id) ? hits.get(x.id).score : 0; };
    if (state.sort === "relevance" && hits && Sch && Sch.queryBox.value.trim()) {
      a.sort(function (x, y) { return score(y) - score(x) || byAuthor(x, y); });
    } else if (state.sort === "year-desc") a.sort(function (x, y) { return (y.year || 0) - (x.year || 0) || byAuthor(x, y); });
    else if (state.sort === "year-asc") a.sort(function (x, y) { return (x.year || 9999) - (y.year || 9999) || byAuthor(x, y); });
    else if (state.sort === "title") a.sort(function (x, y) { return x._title.localeCompare(y._title); });
    else a.sort(byAuthor);
    return a;
  }

  function renderResults(list) {
    var a = sorted(list), n = Math.min(state.shown, a.length);
    $("results").innerHTML = a.length ? a.slice(0, n).map(card).join("") :
      '<li class="card">No items match. Remove a filter or change the words searched.</li>';
    var more = $("more");
    more.hidden = n >= a.length;
    more.textContent = "Show " + Math.min(PAGE, a.length - n) + " more (" + n + " of " + a.length + " shown)";
    var q = Sch ? Sch.queryBox.value.trim() : "";
    $("status").textContent = a.length + " of " + ITEMS.length + " items" + (q ? ' match "' + q + '"' : (list.length < ITEMS.length ? " match the filters" : ""));
    $("relevance-opt").disabled = !(Sch && q);
    $("sort").value = (!q && state.sort === "relevance") ? "author" : state.sort;
  }

  /* counts beside staticSearch's own checkboxes: how many of the current results have each value */
  function decorateCounts(list) {
    if (!Sch) { return; }
    var getters = { Volume: function (it) { return it.volumes; }, Topic: function (it) { return it.topics; }, Type: function (it) { return [it.kind]; } };
    var counts = {};
    Object.keys(getters).forEach(function (k) {
      counts[k] = {};
      list.forEach(function (it) { getters[k](it).forEach(function (v) { counts[k][v] = (counts[k][v] || 0) + 1; }); });
    });
    Sch.descFilterCheckboxes.forEach(function (cb) {
      var t = cb.getAttribute("title");
      if (!counts[t]) { return; }
      var li = cb.closest("li"), span = li.querySelector(".ssCount");
      if (!span) { span = document.createElement("span"); span.className = "ssCount"; li.appendChild(span); }
      var n = counts[t][cb.value] || 0;
      span.textContent = " (" + n + ")";
      span.setAttribute("aria-label", n + " in the current results");
    });
  }

  /* ---------- charts (semantic HTML) ---------- */
  function barList(entries, sel, key, label) {
    var max = entries.reduce(function (m, e) { return Math.max(m, e[1]); }, 1);
    var dis = Sch ? "" : " disabled";
    return '<ul class="bars" aria-label="' + esc(label) + '">' + entries.map(function (e) {
      return '<li><button type="button" class="bar" data-fk="' + key + "-" + esc(e[0]) + '" data-chart="' + key + '" data-v="' + esc(e[0]) +
        '" aria-pressed="' + (sel.indexOf(e[0]) !== -1) + '"' + dis + '><span class="lbl">' + esc(e[0]) + '</span><span class="track"><span class="fill" style="width:' +
        Math.max(1, Math.round(100 * e[1] / max)) + '%"></span></span><span class="num">' + e[1] + "</span></button></li>";
    }).join("") + "</ul>";
  }
  function tally(list, fn) {
    var c = {};
    list.forEach(function (it) { fn(it).forEach(function (v) { c[v] = (c[v] || 0) + 1; }); });
    return Object.keys(c).map(function (k) { return [k, c[k]]; });
  }

  function renderCharts(list) {
    var yr = yearRange(), dis = Sch ? "" : " disabled";
    var bins = {}, early = 0, undated = 0;
    list.forEach(function (it) {
      if (it.year === null) undated++; else if (it.year < 1990) early++; else bins[it.year] = (bins[it.year] || 0) + 1;
    });
    var cols = [["Before 1990", early, 1989]];
    for (var y = 1990; y <= 2025; y++) cols.push([String(y), bins[y] || 0, y]);
    var max = cols.reduce(function (m, c) { return Math.max(m, c[1]); }, 1);
    var hist = '<div class="hist" role="group" aria-label="Items per year">' + cols.map(function (c) {
      var on = c[2] === 1989 ? (yr[0] === "" && yr[1] === "1989") : (yr[0] === String(c[2]) && yr[1] === String(c[2]));
      return '<button type="button" data-fk="yr-' + c[2] + '" data-chart="year" data-y="' + c[2] + '" aria-pressed="' + on + '" aria-label="' + c[0] + ": " + c[1] + ' items"' + dis + '><span class="cnt">' + (c[1] || "") +
        '</span><span class="col" style="height:' + Math.round(100 * c[1] / max * 0.7) + '%"></span><span class="yr">' + (c[2] === 1989 ? "&lt;1990" : c[0]) + "</span></button>";
    }).join("") + "</div>";
    var htable = '<details><summary>View as table</summary><div class="scroll"><table class="data"><caption class="sr">Items per year</caption><thead><tr><th scope="col">Year</th><th scope="col">Items</th></tr></thead><tbody>' +
      cols.map(function (c) { return '<tr><th scope="row">' + c[0] + "</th><td>" + c[1] + "</td></tr>"; }).join("") + "</tbody></table></div></details>";
    $("chart-year").innerHTML = "<figcaption>Items by year of publication</figcaption><p class=\"sub\">" + (Sch ? "Select a column to filter by that year. " : "") +
      (undated ? undated + " items have no date." : "") + "</p>" + hist + htable;

    var vt = tally(list, function (it) { return it.volumes; }).sort(function (a, b) { return b[1] - a[1]; });
    $("chart-volume").innerHTML = '<figcaption>Items by volume</figcaption><p class="sub">An item counts once in each volume that includes it.</p>' + barList(vt, selected("Volume"), "volume", "Items by volume");

    var at = tally(list, function (it) { return it.authors; }).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); }).slice(0, 12);
    $("chart-author").innerHTML = '<figcaption>Most frequent authors</figcaption><p class="sub">Authors only; editors are counted separately. Names are split from citations by a heuristic, so organisations and unusual names may vary.</p>' +
      barList(at, selected("Author"), "author", "Most frequent authors");

    var topics = DATA.topics, vnames = VOLS.map(function (v) { return v.title; }), m = {}, mx = 1;
    var selT = selected("Topic"), selV = selected("Volume");
    list.forEach(function (it) { it.topics.forEach(function (t) { it.volumes.forEach(function (v) { var k = t + "\u0000" + v; m[k] = (m[k] || 0) + 1; mx = Math.max(mx, m[k]); }); }); });
    var head = "<tr><th scope=\"col\">Topic</th>" + vnames.map(function (v) { return '<th scope="col">' + esc(v.replace("Knowledge Mobilization in the Humanities", "Knowl. Mobilization").replace("Engaging ", "").replace(" in Open Scholarship", "")) + "</th>"; }).join("") + "</tr>";
    var body = topics.map(function (t) {
      return '<tr><th scope="row">' + esc(t) + "</th>" + vnames.map(function (v) {
        var n = m[t + "\u0000" + v] || 0;
        if (!n) return '<td class="zero">0</td>';
        var on = selT.length === 1 && selT[0] === t && selV.length === 1 && selV[0] === v;
        return '<td><button type="button" data-fk="h-' + esc(t + v) + '" data-chart="heat" data-t="' + esc(t) + '" data-v="' + esc(v) + '" style="--v:' + (n / mx).toFixed(2) +
          '" aria-pressed="' + on + '" aria-label="' + esc(t) + ", " + esc(v) + ": " + n + ' items.' + (Sch ? " Select to filter." : "") + '"' + dis + ">" + n + "</button></td>";
      }).join("") + "</tr>";
    }).join("");
    $("chart-heat").innerHTML = '<figcaption>Topics across volumes</figcaption><p class="sub">Counts of items per detected topic and volume; shading follows the count.' + (Sch ? " Select a number to filter by that topic and volume." : "") + '</p><div class="heat"><table><caption class="sr">Items by topic and volume</caption><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";

    var ov = {};
    list.forEach(function (it) { it.volumes.forEach(function (a) { it.volumes.forEach(function (b) { var k = a + "\u0000" + b; ov[k] = (ov[k] || 0) + 1; }); }); });
    var ohead = "<tr><th scope=\"col\"><span class=\"sr\">Volume</span></th>" + vnames.map(function (v) { return '<th scope="col">' + esc(v.split(" ")[0] === "Engaging" ? v.split(" ")[1] : v.split(" ")[0]) + "</th>"; }).join("") + "</tr>";
    var obody = vnames.map(function (a) {
      return '<tr><th scope="row">' + esc(a) + "</th>" + vnames.map(function (b) { return "<td>" + (ov[a + "\u0000" + b] || 0) + "</td>"; }).join("") + "</tr>";
    }).join("");
    $("chart-overlap").innerHTML = '<figcaption>Shared items between volumes</figcaption><p class="sub">Each cell counts items that appear in both volumes. The diagonal gives each volume’s total.</p><div class="heat"><table><caption class="sr">Items shared between volumes</caption><thead>' + ohead + "</thead><tbody>" + obody + "</tbody></table></div>";
  }

  function update() {
    var focusKey = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute("data-fk");
    var list = current();
    renderResults(list);
    renderCharts(list);
    decorateCounts(list);
    if (focusKey) { var el = document.querySelector('[data-fk="' + focusKey.replace(/"/g, '\\"') + '"]'); if (el && !el.disabled) { el.focus(); } }
  }

  /* ---------- events ---------- */
  $("sort").addEventListener("change", function (e) { state.sort = e.target.value; update(); });
  $("more").addEventListener("click", function () {
    var before = state.shown; state.shown += PAGE; update();
    var cards = $("results").querySelectorAll(".card h3 a"); if (cards[before]) { cards[before].focus(); }
  });
  $("viz").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-chart]");
    if (!b || !Sch) { return; }
    var c = b.dataset.chart;
    setControls(function () {
      if (c === "volume") { toggleDesc("Volume", b.dataset.v); }
      else if (c === "author") {
        var ta = Sch.mapFeatFilters.get("Author");
        if (ta) { ta.setCheckboxes(selected("Author").indexOf(b.dataset.v) !== -1 ? [] : [b.dataset.v]); }
      } else if (c === "year") {
        var y = b.dataset.y, early = y === "1989", yr = yearRange();
        var on = early ? (yr[0] === "" && yr[1] === "1989") : (yr[0] === y && yr[1] === y);
        dateInput("_from").value = on || early ? "" : y;
        dateInput("_to").value = on ? "" : y;
      } else if (c === "heat") {
        var tv = selected("Topic"), vv = selected("Volume");
        var same = tv.length === 1 && tv[0] === b.dataset.t && vv.length === 1 && vv[0] === b.dataset.v;
        Sch.descFilterCheckboxes.forEach(function (cb) {
          var t = cb.getAttribute("title");
          if (t === "Topic") { cb.checked = !same && cb.value === b.dataset.t; }
          if (t === "Volume") { cb.checked = !same && cb.value === b.dataset.v; }
        });
      }
    });
  });

  /* ---------- start ---------- */
  function unavailable(why) {
    var note = $("ss-unavailable"), box = $("staticSearch");
    if (note) { note.hidden = false; note.querySelector(".why").textContent = why; }
    if (box) { box.hidden = true; }
  }

  document.documentElement.classList.add("js");
  if (typeof StaticSearch === "undefined") {
    unavailable("The search index is not part of this copy of the site.");
  } else if (location.protocol === "file:") {
    unavailable("Search needs the page to be served over the web (browsers block reading the index from a saved file).");
  } else {
    try {
      Sch = new StaticSearch();
      Sch.searchFinishedHook = onSearchDone;
      Sch.scrollToResults = function () {};     // results are drawn by this page, not by staticSearch
      Sch.resultsPerPage = 0;                   // staticSearch's own (hidden) list needs no pagination
      if (Sch.queryBox) { Sch.queryBox.blur(); }
    } catch (err) {
      Sch = null;
      unavailable("The search engine could not start.");
    }
  }
  update();
})();
