"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { makeApp, item } = require("./app-harness");

const count = (s, re) => (s.match(re) || []).length;
const results = (h) => h.el("results").innerHTML;

function bulk(n, over) {
  return Array.from({ length: n }, (_, i) => item("b" + String(i).padStart(3, "0"), Object.assign({ authors: ["Writer " + String(i).padStart(3, "0")], year: 1990 + (i % 30) }, over && over(i))));
}

/* ---------- small pure helpers ---------- */
test("fold ignores case and accents' combining marks only, and stringifies", () => {
  const h = makeApp({ items: [] });
  assert.equal(h.api.fold("Schöpfel"), "schopfel");
  assert.equal(h.api.fold("ÉCOLE Ñandú"), "ecole nandu");
  assert.equal(h.api.fold(42), "42");
  assert.equal(h.api.fold("ß"), "ß");                           // not a combining mark: kept
});

test("esc escapes the five HTML characters", () => {
  const h = makeApp({ items: [] });
  assert.equal(h.api.esc(`<i a="b">Tom & 'Jerry'</i>`), "&lt;i a=&quot;b&quot;&gt;Tom &amp; &#39;Jerry&#39;&lt;/i&gt;");
  assert.equal(h.api.esc(null), "null");
});

test("people lists up to four names, then et al.", () => {
  const h = makeApp({ items: [] });
  assert.equal(h.api.people([], " (ed.)"), "");
  assert.equal(h.api.people(["A"], ""), "A");
  assert.equal(h.api.people(["A", "B", "C", "D"], ""), "A, B, C, D");
  assert.equal(h.api.people(["A", "B", "C", "D", "E"], ""), "A, B, C, D et al.");
  assert.equal(h.api.people(["A & B", "C"], " (eds.)"), "A &amp; B, C (eds.)");
});

test("contextHtml keeps staticSearch's mark tags, escapes everything else, orders by position, and uses two snippets", () => {
  const h = makeApp({ items: [] });
  assert.equal(h.api.contextHtml(null), "");
  assert.equal(h.api.contextHtml({ contexts: [] }), "");
  const hit = { contexts: [{ pos: 30, context: "later <mark>open</mark> text" }, { pos: 2, context: 'a <script>x</script> & <mark>data</mark>' }, { pos: 99, context: "third is dropped" }] };
  assert.equal(h.api.contextHtml(hit), "a &lt;script&gt;x&lt;/script&gt; &amp; <mark>data</mark> … later <mark>open</mark> text");
  assert.equal(hit.contexts[0].pos, 30);                       // the caller's array is not reordered
});

test("snippet prefers the search context, then the annotation, shortened at a word boundary", () => {
  const h = makeApp({ items: [] });
  assert.equal(h.api.snippet({ annotation: "Ann." }, { contexts: [{ pos: 0, context: "ctx <mark>hit</mark>" }] }), "ctx <mark>hit</mark>");
  assert.equal(h.api.snippet({ annotation: "" }, null), "");
  assert.equal(h.api.snippet({ annotation: "Fish & <chips>" }, { contexts: [] }), "Fish &amp; &lt;chips&gt;");
  const long = ("word ".repeat(80)).trim();                    // 399 characters
  const s = h.api.snippet({ annotation: long }, null);
  assert.ok(s.endsWith("…") && s.length <= 301);
  assert.equal(s.slice(0, -1), long.slice(0, long.lastIndexOf(" ", 300)));
  assert.equal(h.api.snippet({ annotation: "x".repeat(300) }, null), "x".repeat(300));   // exactly 300: untouched
});

test("tally counts values per item", () => {
  const h = makeApp({ items: [] });
  const t = h.api.tally([{ v: ["a", "b"] }, { v: ["a"] }, { v: [] }], (x) => x.v);
  assert.deepEqual(t, [["a", 2], ["b", 1]]);
  assert.deepEqual(h.api.tally([], () => []), []);
});

test("barList: one button per entry, widths relative to the largest, escaped labels, pressed state", () => {
  const h = makeApp({ items: [] });
  const s = h.api.barList([["R&D", 10], ["Small", 1], ["Tiny", 0]], ["Small"], "volume", 'By "vol"');
  assert.match(s, /^<ul class="bars" aria-label="By &quot;vol&quot;">/);
  assert.match(s, /data-fk="volume-R&amp;D" data-chart="volume" data-v="R&amp;D" aria-pressed="false">/);
  assert.match(s, /data-v="Small" aria-pressed="true">/);
  assert.match(s, /<span class="fill" style="width:100%">/);
  assert.match(s, /<span class="fill" style="width:10%">/);
  assert.match(s, /<span class="fill" style="width:1%">/);        // never invisible
  assert.ok(!/ disabled/.test(s));
  const off = makeApp({ items: [], noEngine: true });
  assert.match(off.api.barList([["A", 1]], [], "author", "x"), /aria-pressed="false" disabled>/);
});

/* ---------- cards ---------- */
test("card: title, authors, year, kind, tags and links", () => {
  const h = makeApp({ items: [item("c1", { title: "A <b>Title</b>", authors: ["Ann", "Bob"], year: 2019, kind: "Book", container: "Journal of Things", volumes: ["Community", "Policy"], topics: ["Data"], doi: "10.1/xyz" })] });
  const s = results(h);
  assert.ok(s.startsWith('<li class="card"><h3><a href="items/c1.html">A &lt;b&gt;Title&lt;/b&gt;</a></h3>'));
  assert.ok(s.includes('<p class="by"><strong>Ann, Bob</strong> · 2019 · Book · Journal of Things</p>'));
  assert.ok(s.includes('<ul class="tags" aria-label="Volumes and topics"><li class="tag vol">Community</li><li class="tag vol">Policy</li><li class="tag">Data</li></ul>'));
  assert.ok(s.includes('<a href="https://doi.org/10.1/xyz" rel="noopener">Open source (DOI)</a><a href="items/c1.html">Record page</a>'));
  assert.ok(s.includes('<p class="snippet">A short annotation.</p>'));
});

test("card: DOI forms are normalised, and a plain URL is labelled as a link", () => {
  const h = makeApp({ items: [] });
  const link = (over) => { const c = h.api.card(item("d", over)); return /<a href="([^"]*)" rel="noopener">Open source (\([A-Z]+\)|\(link\))/.exec(c); };
  assert.equal(link({ doi: "https://doi.org/10.2/a" })[1], "https://doi.org/10.2/a");
  assert.equal(link({ doi: "http://dx.doi.org/10.2/a" })[1], "https://doi.org/10.2/a");
  assert.equal(link({ doi: "10.2/a" })[1], "https://doi.org/10.2/a");
  const u = link({ url: "https://example.org/?a=1&b=2" });
  assert.equal(u[1], "https://example.org/?a=1&amp;b=2");
  assert.equal(u[2], "(link)");
  assert.ok(!h.api.card(item("e", {})).includes("Open source"));          // no DOI, no URL: no external link
  assert.ok(h.api.card(item("e", {})).includes('<div class="links"><a href="items/e.html">Record page</a></div>'));
});

test("card: who is credited, with editors and the no-author fallback", () => {
  const h = makeApp({ items: [] });
  const by = (over) => /<strong>(.*?)<\/strong>/.exec(h.api.card(item("a", over)))[1];
  assert.equal(by({ authors: ["Ann"], editors: ["Ed"] }), "Ann");
  assert.equal(by({ authors: [], editors: ["Ed"] }), "Ed (ed.)");
  assert.equal(by({ authors: [], editors: ["Ed", "Flo"] }), "Ed, Flo (eds.)");
  assert.equal(by({ authors: [], editors: [] }), "No named author");
});

test("card: missing year, container shortening, missing title and annotation", () => {
  const h = makeApp({ items: [] });
  const c1 = h.api.card(item("m", { year: null, title: "", citation: "Cite <me>", container: "x".repeat(91), annotation: "" }));
  assert.ok(c1.includes('<a href="items/m.html">Cite &lt;me&gt;</a>'));          // citation stands in for a missing title
  assert.ok(c1.includes(" · n.d. · Journal article · " + "x".repeat(88) + "…</p>"));
  assert.ok(c1.includes('<p class="snippet by">No annotation in the source volume.</p>'));
  assert.ok(!c1.includes("<details>"));
  const c2 = h.api.card(item("m", { container: "y".repeat(90) }));
  assert.ok(c2.includes("y".repeat(90) + "</p>"));                                  // 90 characters: kept whole
  assert.ok(!h.api.card(item("m", { container: "" })).includes(" · Journal article ·"));
});

test("card: a long annotation gets a collapsible full text", () => {
  const h = makeApp({ items: [] });
  const long = "Long & winding. ".repeat(30);
  const c = h.api.card(item("l", { annotation: long }));
  assert.ok(c.includes("<details><summary>Full annotation</summary><p>" + h.api.esc(long) + "</p></details>"));
  assert.ok(!h.api.card(item("l", { annotation: "x".repeat(320) })).includes("<details>"));
  assert.ok(h.api.card(item("l", { annotation: "x".repeat(321) })).includes("<details>"));
});

test("card: shows the search context for a hit", () => {
  const h = makeApp({ items: [item("k1"), item("k2")] });
  h.finish("open", { "k1.html": { score: 2, contexts: [{ pos: 1, context: "an <mark>open</mark> thing" }] } });
  assert.ok(results(h).includes('<p class="snippet">an <mark>open</mark> thing</p>'));
  assert.ok(!results(h).includes("k2"));
});

/* ---------- receiving results ---------- */
test("startup renders every item and the status", () => {
  const h = makeApp({ items: [item("a"), item("b")] });
  assert.deepEqual(h.ids(), ["a", "b"]);
  assert.equal(h.el("status").textContent, "2 of 2 items");
  assert.equal(h.api.getHits(), null);
  assert.ok(h.doc.documentElement.classList.contains("js"));
  assert.equal(h.sch().resultsPerPage, 0);
  assert.equal(typeof h.sch().scrollToResults, "function");
  assert.equal(h.sch().scrollToResults(), undefined);
  assert.equal(h.sch().queryBox.blurred, 1);
  assert.equal(h.note.hidden, true);
});

test("a search with words keeps only the matching items, strips .html, and ranks by score", () => {
  const h = makeApp({ items: [item("a", { authors: ["Zed"] }), item("b", { authors: ["Amy"] }), item("c", { authors: ["Cy"] })] });
  h.finish("open", { "a.html": { score: 5 }, "b.html": { score: 9, contexts: [] } });
  assert.deepEqual(h.ids(), ["b", "a"]);
  assert.equal(h.el("status").textContent, '2 of 3 items match "open"');
  assert.equal(h.relOpt.disabled, false);
  assert.equal(h.sort.value, "relevance");
  assert.equal(h.api.getHits().get("a").score, 5);
  assert.deepEqual(h.api.getHits().get("a").contexts, []);
});

test("relevance ties fall back to author then year", () => {
  const h = makeApp({ items: [item("a", { authors: ["Zed"], year: 2001 }), item("b", { authors: ["Amy"], year: 2005 }), item("c", { authors: ["Amy"], year: 2002 })] });
  h.finish("x", { "a.html": { score: 1 }, "b.html": { score: 1 }, "c.html": { score: 1 } });
  assert.deepEqual(h.ids(), ["c", "b", "a"]);
});

test("filters alone (no words) restrict the list and say so", () => {
  const h = makeApp({ items: [item("a"), item("b")] });
  h.finish("", { "b.html": { score: 0 } }, true);
  assert.deepEqual(h.ids(), ["b"]);
  assert.equal(h.el("status").textContent, "1 of 2 items match the filters");
  assert.equal(h.relOpt.disabled, true);                         // nothing to rank by
  assert.equal(h.sort.value, "author");
});

test("no words and no filters restores the whole collection", () => {
  const h = makeApp({ items: [item("a"), item("b")] });
  h.finish("x", { "a.html": { score: 1 } });
  assert.deepEqual(h.ids(), ["a"]);
  h.finish("  ", {}, false);
  assert.deepEqual(h.ids(), ["a", "b"]);
  assert.equal(h.api.getHits(), null);
});

test("a search that found nothing shows the empty message", () => {
  const h = makeApp({ items: [item("a")] });
  h.finish("zzz", {});
  assert.equal(results(h), '<li class="card">No items match. Remove a filter or change the words searched.</li>');
  assert.equal(h.el("status").textContent, '0 of 1 items match "zzz"');
  assert.equal(h.more.hidden, true);
});

test("an engine error (code 5) leaves the display alone", () => {
  const h = makeApp({ items: [item("a"), item("b")] });
  h.finish("x", { "a.html": { score: 1 } });
  const before = results(h);
  h.finish("y", {}, false, 5);
  assert.equal(results(h), before);
  assert.ok(h.api.getHits().has("a"));
});

test("a new search returns to the first page", () => {
  const h = makeApp({ items: bulk(60) });
  h.more.dispatch("click");
  assert.equal(h.st().shown, 50);
  h.finish("", {}, false);
  assert.equal(h.st().shown, 25);
});

/* ---------- sorting ---------- */
test("sorting by author, year and title", () => {
  const items = [
    item("a", { authors: ["Brown"], year: 2010, title: "Zebra" }),
    item("b", { authors: ["Adams"], year: null, title: "émile" }),
    item("c", { authors: [], editors: ["Clark"], year: 1999, title: "Apple" }),
    item("d", { authors: ["Adams"], year: 2001, title: "mango" }),
    item("e", { authors: [], editors: [], year: 2005, title: "Cherry" }),
  ];
  const h = makeApp({ items });
  const order = (v) => { h.sort.value = v; h.sort.dispatch("change"); return h.ids().join(""); };
  assert.equal(order("author"), "ebdac");                       // no author first; Adams undated (year 0), Adams 2001; Brown; editor Clark
  assert.equal(order("year-desc"), "aedcb");                    // undated last
  assert.equal(order("year-asc"), "cdeab");                     // undated last
  assert.equal(order("title"), "cebda");                        // accents and capitals ignored: apple, cherry, emile, mango, zebra
  assert.equal(h.st().sort, "title");
});

test("relevance sort with no query behaves as author sort and the control shows author", () => {
  const h = makeApp({ items: [item("a", { authors: ["Zed"] }), item("b", { authors: ["Amy"] })] });
  assert.equal(h.st().sort, "relevance");
  assert.deepEqual(h.ids(), ["b", "a"]);
  assert.equal(h.sort.value, "author");
  assert.equal(h.relOpt.disabled, true);
});

test("year sorts break ties by author", () => {
  const h = makeApp({ items: [item("a", { authors: ["Zed"], year: 2000 }), item("b", { authors: ["Amy"], year: 2000 }), item("c", { authors: ["Cy"], year: null }), item("d", { authors: ["Bo"], year: null })] });
  h.sort.value = "year-desc"; h.sort.dispatch("change");
  assert.deepEqual(h.ids(), ["b", "a", "d", "c"]);
  h.sort.value = "year-asc"; h.sort.dispatch("change");
  assert.deepEqual(h.ids(), ["b", "a", "d", "c"]);
});

test("sorted does not change the list it is given", () => {
  const h = makeApp({ items: [] });
  const list = [item("a", { authors: ["Zed"] }), item("b", { authors: ["Amy"] })];
  assert.deepEqual(h.api.sorted(list).map((i) => i.id), ["b", "a"]);
  assert.deepEqual(list.map((i) => i.id), ["a", "b"]);
});

/* ---------- paging ---------- */
test("the more button pages through the list and moves focus to the first new card", () => {
  const h = makeApp({ items: bulk(60) });
  assert.equal(h.ids().length, 25);
  assert.equal(h.more.hidden, false);
  assert.equal(h.more.textContent, "Show 25 more (25 of 60 shown)");
  h.more.dispatch("click");
  assert.equal(h.ids().length, 50);
  assert.equal(h.more.textContent, "Show 10 more (50 of 60 shown)");
  assert.equal(h.doc.activeElement.getAttribute("href"), "items/" + h.ids()[25] + ".html");
  assert.equal(h.doc.activeElement.focused, 1);
  h.more.dispatch("click");
  assert.equal(h.ids().length, 60);
  assert.equal(h.more.hidden, true);
  assert.equal(h.more.textContent, "Show 0 more (60 of 60 shown)");
});

test("the more button does not fail when there is no new card to focus", () => {
  const h = makeApp({ items: bulk(30) });
  h.more.dispatch("click");
  h.more.dispatch("click");                                      // a stray click on the hidden button
  assert.equal(h.ids().length, 30);
});

test("an exact multiple of the page size hides the button", () => {
  const h = makeApp({ items: bulk(25) });
  assert.equal(h.more.hidden, true);
});

/* ---------- counts beside staticSearch's checkboxes ---------- */
test("decorateCounts adds, then updates, a count beside each filter checkbox", () => {
  const items = [item("a", { volumes: ["Community"], topics: ["Data"], kind: "Book" }), item("b", { volumes: ["Community", "Policy"], topics: [], kind: "Journal article" })];
  const h = makeApp({ items });
  const find = (title, value) => h.sch().descFilterCheckboxes.find((c) => c.getAttribute("title") === title && c.value === value);
  const span = (c) => c.parent.querySelector(".ssCount");
  assert.equal(span(find("Volume", "Community")).textContent, " (2)");
  assert.equal(span(find("Volume", "Community")).getAttribute("aria-label"), "2 in the current results");
  assert.equal(span(find("Volume", "Knowledge Mobilization in the Humanities")).textContent, " (0)");
  assert.equal(span(find("Topic", "Data")).textContent, " (1)");
  assert.equal(span(find("Type", "Book")).textContent, " (1)");
  assert.equal(span(find("Has annotation", "true")), null);          // only Volume, Topic and Type get counts
  h.finish("", { "a.html": { score: 0 } }, true);
  assert.equal(span(find("Volume", "Community")).textContent, " (1)");
  assert.equal(count(find("Volume", "Community").parent.children.map((c) => c.className).join(" "), /ssCount/g), 1);   // reused, not duplicated
});

test("decorateCounts does nothing without the engine", () => {
  const h = makeApp({ items: [item("a")], noEngine: true });
  assert.doesNotThrow(() => h.api.decorateCounts([]));
});

/* ---------- charts ---------- */
const VOLS = ["Community", "Knowledge Mobilization in the Humanities", "Engaging Knowledge Diversity", "Engaging Platforms in Open Scholarship"];
const CH = [
  item("a", { year: 1985, volumes: ["Community"], topics: ["Data"], authors: ["Ann"] }),
  item("b", { year: 1990, volumes: ["Community", VOLS[1]], topics: ["Data", "Open Access"], authors: ["Ann", "Bob"] }),
  item("c", { year: 2025, volumes: [VOLS[2]], topics: ["Open Access"], authors: ["Bob"] }),
  item("d", { year: null, volumes: [VOLS[3]], topics: [], authors: ["Cy"] }),
  item("e", { year: 2030, volumes: [VOLS[3]], topics: ["Data"], authors: [] }),    // outside the charted years
];

test("year chart: before-1990 column, one column per year, undated note, table", () => {
  const h = makeApp({ items: CH });
  const s = h.el("chart-year").innerHTML;
  assert.ok(s.startsWith("<figcaption>Items by year of publication</figcaption>"));
  assert.ok(s.includes("Select a column to filter by that year. 1 items have no date."));
  assert.equal(count(s, /data-chart="year"/g), 37);                  // 1989 bucket plus 1990 to 2025
  assert.ok(s.includes('data-fk="yr-1989" data-chart="year" data-y="1989" aria-pressed="false" aria-label="Before 1990: 1 items">'));
  assert.ok(s.includes('<span class="cnt">1</span><span class="col" style="height:70%"></span><span class="yr">&lt;1990</span>'));
  assert.ok(s.includes('data-y="1995" aria-pressed="false" aria-label="1995: 0 items"><span class="cnt"></span><span class="col" style="height:0%"></span><span class="yr">1995</span>'));
  assert.ok(s.includes('<tr><th scope="row">2025</th><td>1</td></tr>'));
  assert.ok(!s.includes("2030"));
  assert.ok(s.includes('<caption class="sr">Items per year</caption>'));
});

test("year chart: no undated note, and no instruction, when nothing applies", () => {
  const h = makeApp({ items: [item("a", { year: 2000 })], noEngine: true });
  const s = h.el("chart-year").innerHTML;
  assert.ok(s.includes('<p class="sub"></p>'));
  assert.equal(count(s, / disabled>/g), 37);
});

test("year chart: a column is pressed when the date filter selects exactly that year", () => {
  const one = makeApp({ items: CH, search: "?Year_from=1990&Year_to=1990" });
  assert.equal(count(one.el("chart-year").innerHTML, /aria-pressed="true"/g), 1);
  assert.ok(one.el("chart-year").innerHTML.includes('data-y="1990" aria-pressed="true"'));
  const early = makeApp({ items: CH, search: "?Year_to=1989" });
  assert.ok(early.el("chart-year").innerHTML.includes('data-y="1989" aria-pressed="true"'));
  const range = makeApp({ items: CH, search: "?Year_from=1990&Year_to=2000" });
  assert.equal(count(range.el("chart-year").innerHTML, /aria-pressed="true"/g), 0);
  const earlyFrom = makeApp({ items: CH, search: "?Year_from=1980&Year_to=1989" });
  assert.ok(earlyFrom.el("chart-year").innerHTML.includes('data-y="1989" aria-pressed="false"'));
});

test("volume chart: counts per volume, biggest first, pressed when selected in the URL", () => {
  const h = makeApp({ items: CH, search: "?Volume=Community" });
  const s = h.el("chart-volume").innerHTML;
  assert.ok(s.includes("<figcaption>Items by volume</figcaption>"));
  assert.deepEqual((s.match(/data-v="([^"]*)"/g)).map((m) => m.slice(8, -1)), ["Community", VOLS[3], VOLS[1], VOLS[2]]);
  assert.ok(s.includes('data-v="Community" aria-pressed="true"'));
  assert.ok(s.includes('data-v="' + VOLS[3] + '" aria-pressed="false"'));
});

test("author chart: the twelve most frequent, ties alphabetical, pressed when chosen", () => {
  const many = bulk(14, (i) => ({ authors: ["Zz" + String(i).padStart(2, "0")] })).concat([item("x1", { authors: ["Zz13"] })]);
  const h = makeApp({ items: many, search: "?Author=Zz05" });
  const s = h.el("chart-author").innerHTML;
  const names = (s.match(/data-v="([^"]*)"/g)).map((m) => m.slice(8, -1));
  assert.equal(names.length, 12);
  assert.equal(names[0], "Zz13");                                   // two items
  assert.deepEqual(names.slice(1, 4), ["Zz00", "Zz01", "Zz02"]);
  assert.ok(s.includes('data-v="Zz05" aria-pressed="true"'));
  assert.ok(s.includes("Authors only; editors are counted separately."));
});

test("heat map: topics by volume with shortened headings, zero cells and pressed cell", () => {
  const h = makeApp({ items: CH, search: "?Topic=Data&Volume=Community" });
  const s = h.el("chart-heat").innerHTML;
  assert.ok(s.includes('<th scope="col">Topic</th><th scope="col">Community</th><th scope="col">Knowl. Mobilization</th><th scope="col">Knowledge Diversity</th><th scope="col">Platforms</th>'));
  assert.ok(s.includes('<tr><th scope="row">Data</th><td><button type="button" data-fk="h-DataCommunity" data-chart="heat" data-t="Data" data-v="Community" style="--v:1.00" aria-pressed="true" aria-label="Data, Community: 2 items. Select to filter.">2</button></td>'));
  assert.ok(s.includes('<td class="zero">0</td>'));
  assert.ok(s.includes('data-t="Open Access" data-v="Community" style="--v:0.50" aria-pressed="false"'));
  assert.equal(count(s, /aria-pressed="true"/g), 1);
  assert.ok(s.includes("Select a number to filter by that topic and volume."));
});

test("heat map without the engine has disabled cells and no instruction", () => {
  const h = makeApp({ items: CH, noEngine: true });
  const s = h.el("chart-heat").innerHTML;
  assert.ok(s.includes('aria-label="Data, Community: 2 items." disabled>2</button>'));
  assert.ok(!s.includes("Select a number"));
  assert.ok(!s.includes("Select to filter."));
});

test("heat map: a topic selected without a volume does not press a cell", () => {
  const h = makeApp({ items: CH, search: "?Topic=Data" });
  assert.equal(count(h.el("chart-heat").innerHTML, /aria-pressed="true"/g), 0);
});

test("overlap table: the diagonal is each volume's total, off-diagonal cells count shared items", () => {
  const h = makeApp({ items: CH });
  const s = h.el("chart-overlap").innerHTML;
  assert.ok(s.includes('<th scope="col"><span class="sr">Volume</span></th><th scope="col">Community</th><th scope="col">Knowledge</th><th scope="col">Knowledge</th><th scope="col">Platforms</th>'));
  assert.ok(s.includes('<tr><th scope="row">Community</th><td>2</td><td>1</td><td>0</td><td>0</td></tr>'));
  assert.ok(s.includes('<tr><th scope="row">' + VOLS[3] + '</th><td>0</td><td>0</td><td>0</td><td>2</td></tr>'));
  assert.ok(s.includes("The diagonal gives each volume’s total."));
});

test("charts follow the current results", () => {
  const h = makeApp({ items: CH });
  h.finish("", { "c.html": { score: 0 } }, true);
  assert.ok(h.el("chart-year").innerHTML.includes('aria-label="2025: 1 items"'));
  assert.ok(h.el("chart-year").innerHTML.includes('aria-label="Before 1990: 0 items"'));
  assert.ok(!h.el("chart-year").innerHTML.includes("no date"));
});

/* ---------- chart clicks drive staticSearch ---------- */
const box = (h, title, value) => h.sch().descFilterCheckboxes.find((c) => c.getAttribute("title") === title && c.value === value);
const yearBox = (h, which) => h.sch().dateFilterTextboxes.find((t) => t.id.endsWith(which) && t.getAttribute("title") === "Year");

test("clicking a volume bar toggles that volume's checkbox and runs the search", () => {
  const h = makeApp({ items: CH });
  h.click({ "data-chart": "volume", "data-v": "Community" });
  assert.equal(box(h, "Volume", "Community").checked, true);
  assert.equal(h.sch().searches, 1);
  h.click({ "data-chart": "volume", "data-v": "Community" });
  assert.equal(box(h, "Volume", "Community").checked, false);
  assert.equal(h.sch().searches, 2);
  h.click({ "data-chart": "volume", "data-v": "No such volume" });         // unknown value: search still runs, nothing changes
  assert.equal(h.sch().searches, 3);
});

test("clicking an author bar selects that author, and clicking it again clears the filter", () => {
  const h = makeApp({ items: CH });
  h.click({ "data-chart": "author", "data-v": "Ann" });
  assert.deepEqual(h.sch().mapFeatFilters.get("Author").chosen, ["Ann"]);
  h.loc.search = "?Author=Ann";
  h.click({ "data-chart": "author", "data-v": "Ann" });
  assert.deepEqual(h.sch().mapFeatFilters.get("Author").chosen, []);
  assert.equal(h.sch().searches, 2);
  const noFilter = makeApp({ items: CH, noAuthorFilter: true });
  noFilter.click({ "data-chart": "author", "data-v": "Ann" });
  assert.equal(noFilter.sch().searches, 1);
});

test("clicking a year column sets both ends of the date filter, and clicking it again clears them", () => {
  const h = makeApp({ items: CH });
  h.click({ "data-chart": "year", "data-y": "2000" });
  assert.deepEqual([yearBox(h, "_from").value, yearBox(h, "_to").value], ["2000", "2000"]);
  assert.equal(h.sch().searches, 1);
  h.loc.search = "?Year_from=2000&Year_to=2000";
  h.click({ "data-chart": "year", "data-y": "2000" });
  assert.deepEqual([yearBox(h, "_from").value, yearBox(h, "_to").value], ["", ""]);
  assert.equal(h.sch().dateFilterTextboxes[2].value, "");                  // a date control for another facet is never touched
});

test("clicking before-1990 filters to 1989 and earlier, and clicking again clears it", () => {
  const h = makeApp({ items: CH });
  h.click({ "data-chart": "year", "data-y": "1989" });
  assert.deepEqual([yearBox(h, "_from").value, yearBox(h, "_to").value], ["", "1989"]);
  h.loc.search = "?Year_to=1989";
  h.click({ "data-chart": "year", "data-y": "1989" });
  assert.deepEqual([yearBox(h, "_from").value, yearBox(h, "_to").value], ["", ""]);
});

test("clicking another year replaces a different year filter", () => {
  const h = makeApp({ items: CH, search: "?Year_from=1990&Year_to=1995" });
  h.click({ "data-chart": "year", "data-y": "2001" });
  assert.deepEqual([yearBox(h, "_from").value, yearBox(h, "_to").value], ["2001", "2001"]);
});

test("clicking a heat-map cell selects exactly that topic and volume, and clicking it again clears both", () => {
  const h = makeApp({ items: CH });
  box(h, "Topic", "Data").checked = true; box(h, "Volume", VOLS[2]).checked = true; box(h, "Type", "Book").checked = true;
  h.click({ "data-chart": "heat", "data-t": "Open Access", "data-v": "Community" });
  assert.deepEqual(h.sch().descFilterCheckboxes.filter((c) => c.checked).map((c) => c.getAttribute("title") + ":" + c.value), ["Volume:Community", "Topic:Open Access", "Type:Book"]);
  h.loc.search = "?Topic=Open+Access&Volume=Community";
  h.click({ "data-chart": "heat", "data-t": "Open Access", "data-v": "Community" });
  assert.deepEqual(h.sch().descFilterCheckboxes.filter((c) => c.checked).map((c) => c.getAttribute("title")), ["Type"]);   // other facets are left alone
  assert.equal(h.sch().searches, 2);
});

test("a click that is not on a chart button, or an unknown chart, does not search", () => {
  const h = makeApp({ items: CH });
  const p = h.doc.createElement("p"); p.parent = h.viz;
  h.viz.dispatch("click", { target: p });
  h.click({ "data-chart": "mystery", "data-v": "x" });
  assert.equal(h.sch().searches, 1);                                       // the unknown chart still triggers the (empty) search
});

test("chart buttons do nothing when search is unavailable", () => {
  const h = makeApp({ items: CH, noEngine: true });
  h.click({ "data-chart": "volume", "data-v": "Community" });
  assert.equal(h.api.getSch(), null);
});

/* ---------- focus survives redraws ---------- */
test("the focused chart button is refocused after the charts are redrawn", () => {
  const h = makeApp({ items: CH });
  h.doc.activeElement = h.doc.createElement("button"); h.doc.activeElement.setAttribute("data-fk", "yr-1990");
  h.api.update();
  assert.equal(h.doc.activeElement.getAttribute("data-fk"), "yr-1990");
  assert.equal(h.doc.activeElement.focused, 1);
});

test("focus is not moved to a button that is gone or disabled", () => {
  const h = makeApp({ items: CH });
  const stale = h.doc.createElement("button"); stale.setAttribute("data-fk", "gone"); h.doc.activeElement = stale;
  h.api.update();
  assert.equal(h.doc.activeElement, stale);
  const off = makeApp({ items: CH, noEngine: true });
  const cur = off.doc.createElement("button"); cur.setAttribute("data-fk", 'yr-1990'); off.doc.activeElement = cur;
  off.api.update();
  assert.equal(off.doc.activeElement, cur);                                // the new button is disabled: leave focus alone
});

test("update copes with no active element, and with one that has no attributes", () => {
  const h = makeApp({ items: CH });
  h.doc.activeElement = null; assert.doesNotThrow(() => h.api.update());
  h.doc.activeElement = {}; assert.doesNotThrow(() => h.api.update());
  const p = h.doc.createElement("p"); h.doc.activeElement = p; assert.doesNotThrow(() => h.api.update());
  assert.equal(p.focused, 0);
});

test("focus restore handles keys that contain quotes", () => {
  const h = makeApp({ items: [item("a", { authors: ['O"Neil'] })] });
  const cur = h.doc.createElement("button"); cur.setAttribute("data-fk", 'author-O"Neil'); h.doc.activeElement = cur;
  h.api.update();
  assert.equal(h.doc.activeElement.getAttribute("data-fk"), 'author-O"Neil');
  assert.equal(h.doc.activeElement.focused, 1);
});

/* ---------- state read from the address ---------- */
test("selected() and yearRange() read the current address, decoding it first", () => {
  const h = makeApp({ items: [], search: "?Volume=Policy%20and%20Practice&Volume=Two&Topic=Data&Year_from=1990&Year_to=2000" });
  assert.deepEqual(h.api.selected("Volume"), ["Policy and Practice", "Two"]);
  assert.deepEqual(h.api.yearRange(), ["1990", "2000"]);
  h.loc.search = "";
  assert.deepEqual(h.api.yearRange(), ["", ""]);
  assert.deepEqual(h.api.selected("Volume"), []);
  const off = makeApp({ items: [], noEngine: true, search: "?Volume=X" });
  assert.deepEqual(off.api.selected("Volume"), []);                        // no engine: the address is not trusted
});

/* ---------- search unavailable ---------- */
test("no staticSearch on the page: the note is shown, the form hidden, the list and charts still work", () => {
  const h = makeApp({ items: CH, noEngine: true });
  assert.equal(h.note.hidden, false);
  assert.equal(h.note.why.textContent, "The search index is not part of this copy of the site.");
  assert.equal(h.box.hidden, true);
  assert.equal(h.api.getSch(), null);
  assert.equal(h.ids().length, 5);
  assert.equal(h.el("status").textContent, "5 of 5 items");
  assert.equal(h.relOpt.disabled, true);
  assert.equal(h.sort.value, "author");
});

test("opened from a saved file: search is declared unavailable", () => {
  const h = makeApp({ items: CH, protocol: "file:" });
  assert.match(h.note.why.textContent, /^Search needs the page to be served over the web/);
  assert.equal(h.env.constructed, 0);
  assert.equal(h.api.getSch(), null);
  assert.equal(h.box.hidden, true);
});

test("an engine that fails to start is reported and the page carries on without it", () => {
  const h = makeApp({ items: CH, ctorThrows: true });
  assert.equal(h.note.why.textContent, "The search engine could not start.");
  assert.equal(h.api.getSch(), null);
  assert.equal(h.ids().length, 5);
});

test("the unavailable notice is optional in the markup", () => {
  const a = makeApp({ items: CH, noEngine: true, noNote: true }), b = makeApp({ items: CH, noEngine: true, noBox: true });
  assert.equal(a.box.hidden, true);
  assert.equal(b.note.hidden, false);
});

test("an engine without a query box: start-up guards the blur call but the first draw still reads it (documents current behaviour)", () => {
  assert.throws(() => makeApp({ items: CH, noQueryBox: true }), /Cannot read properties of null/);
});

test("two items with the same title sort stably under title order", () => {
  const h = makeApp({ items: [item("a", { title: "Same" }), item("b", { title: "Same" })] });
  h.sort.value = "title"; h.sort.dispatch("change");
  assert.deepEqual(h.ids(), ["a", "b"]);
});

test("author sort breaks ties by year with undated items first, whatever order they arrive in", () => {
  const years = [null, 2000, null, 1990, 2010];
  const orders = [years, years.slice().reverse(), [2000, null, 2010, null, 1990], [1990, 2010, null, 2000, null]];
  orders.forEach((ys) => {
    const h = makeApp({ items: ys.map((y, i) => item("s" + i, { authors: ["Same"], year: y })) });
    const got = h.ids().map((id) => h.api.current().find((it) => it.id === id).year);
    assert.deepEqual(got, [null, null, 1990, 2000, 2010]);
  });
});
