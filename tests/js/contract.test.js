"use strict";
/* Guards the contract between build/render.py and the two browser scripts: every id a script looks up must exist in
   the markup the corresponding render.py page function produces, and the data keys the scripts read must be written.
   render.py is read as text (never run, so site/ is untouched). */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const RENDER = fs.readFileSync(path.join(ROOT, "build", "render.py"), "utf8");
const APP = fs.readFileSync(path.join(ROOT, "build", "templates", "app.js"), "utf8");
const CO = fs.readFileSync(path.join(ROOT, "build", "templates", "coauthor.js"), "utf8");
const { makeApp } = require("./app-harness");
const { makeCo } = require("./co-harness");

function pyFunction(name) {                       // source of a top-level def, up to the next top-level statement
  const start = RENDER.indexOf("\ndef " + name + "(");
  assert.notEqual(start, -1, "render.py has no " + name + "()");
  const rest = RENDER.slice(start + 1);
  const next = rest.slice(1).search(/\n(def |class |# -{5,}|[A-Z_]+ = )/);
  return next === -1 ? rest : rest.slice(0, next + 1);
}
const ids = (src) => new Set([...src.matchAll(/\bid=["']([A-Za-z][\w-]*)["']/g)].map((m) => m[1]));
function scriptIds(src) {
  const out = new Set();
  for (const m of src.matchAll(/(?:\$|getElementById)\("([^"]+)"\)/g)) { out.add(m[1]); }
  for (const m of src.matchAll(/querySelector(?:All)?\("([^"]+)"\)/g)) { for (const i of m[1].matchAll(/#([A-Za-z][\w-]*)/g)) { out.add(i[1]); } }
  for (const m of src.matchAll(/aria-labelledby="([\w-]+)"/g)) { out.add(m[1]); }
  return out;
}
const missing = (want, have) => [...want].filter((i) => !have.has(i));

const INDEX = pyFunction("index_page"), COAUTHOR = pyFunction("coauthor_page");

test("render.py page functions can be located", () => {
  assert.ok(INDEX.includes("osp-data") && INDEX.includes("<!--@STATICSEARCH@-->"));
  assert.ok(COAUTHOR.includes("co-data") && COAUTHOR.includes("co-status"));
  assert.ok(!INDEX.includes("def coauthor_page") && !COAUTHOR.includes("def methodology_page"));
});

test("every id app.js looks up exists in the Explore page", () => {
  const want = scriptIds(APP);
  ["osp-data", "sort", "more", "viz", "results", "status", "relevance-opt", "chart-year", "chart-volume", "chart-author", "chart-heat", "chart-overlap", "ss-unavailable", "staticSearch"].forEach((i) => assert.ok(want.has(i), "extraction found " + i));
  const have = ids(INDEX);
  have.add("staticSearch");                       // the form is injected at <!--@STATICSEARCH@--> from the search page's markup
  assert.ok(RENDER.includes('<div id="staticSearch"'), "the search page markup that is injected carries id=staticSearch");
  assert.deepEqual(missing(want, have), []);
});

test("every id coauthor.js looks up exists in the Co-authorship page", () => {
  const want = scriptIds(CO);
  ["co-data", "network", "panel", "co-status", "yfrom", "yto", "tie", "group", "find", "only", "co-reset", "find-note", "t-people", "t-ties", "t-groups", "t-per",
    "m-items", "m-multi", "m-authors", "m-ties", "m-groups", "m-largest", "co-filters", "net-cap"].forEach((i) => assert.ok(want.has(i), "extraction found " + i));
  assert.deepEqual(missing(want, ids(COAUTHOR)), []);
});

test("the test fixtures only use ids that the real pages have", () => {
  const app = makeApp({ items: [] }), co = makeCo({ items: [] });
  assert.deepEqual(missing(Object.keys(app.doc.registry), ids(INDEX).add("staticSearch")), []);
  const coHave = ids(COAUTHOR);
  assert.deepEqual(missing(Object.keys(co.doc.registry).filter((i) => !["co-data"].includes(i)), coHave), []);
  assert.ok(coHave.has("co-data"));
});

test("the co-authorship filter controls are the ones the script reads", () => {
  assert.ok(COAUTHOR.includes('name="Volume"'));
  assert.ok(COAUTHOR.includes('boxes("Topic", TOPICS)') && COAUTHOR.includes('boxes("Type", kinds)'));
  assert.ok(COAUTHOR.includes('<form id="co-filters"'));
  for (const sel of ["tie", "group"]) { assert.match(COAUTHOR, new RegExp('<select id="' + sel + '">')); }
  assert.match(COAUTHOR, /<input type="number" id="yfrom"/); assert.match(COAUTHOR, /<input type="number" id="yto"/);
  assert.match(COAUTHOR, /<input type="text" id="find"/); assert.match(COAUTHOR, /<input type="checkbox" id="only"/);
  assert.match(COAUTHOR, /<figcaption id="net-cap">/);
  // the select values the script maps to numbers
  assert.match(COAUTHOR, /<option value="1">[^]*<option value="2">[^]*<option value="3">/);
  assert.match(COAUTHOR, /<select id="group"><option value="2">/);
});

test("the address parameter names the script reads are the ones staticSearch and the page write", () => {
  for (const p of ["Volume", "Topic", "Type", "Year_from", "Year_to", "Tie", "Group", "Find", "Only"]) { assert.ok(CO.includes('"' + p + '"'), p); }
  // app.js reads staticSearch's own parameters; the item pages must publish matching filter names
  for (const p of ["Volume", "Topic", "Author", "Year"]) { assert.ok(APP.includes('"' + p + '"'), p); }
  assert.ok(APP.includes("Type: function"));
  assert.ok(RENDER.includes('m("Volume", "desc"') && RENDER.includes('m("Topic", "desc"') && RENDER.includes('m("Type", "desc"'));
  assert.ok(RENDER.includes('m("Author", "feat"') && RENDER.includes('m("Year", "date"'));
});

test("the data fields app.js reads are written by index_page", () => {
  const slim = /for k in \(([^)]*)\)/.exec(INDEX);
  assert.ok(slim, "found the slim item field list");
  const stmt = INDEX.slice(INDEX.indexOf("slim.append("), INDEX.indexOf("data = {\"items\": slim"));
  const written = new Set([...slim[1].matchAll(/"(\w+)"/g)].map((m) => m[1]).concat([...stmt.matchAll(/,\s*"(\w+)":\s*(?:it\.get\(|\()/g)].map((m) => m[1])));
  assert.ok(written.has("crossref"), "index_page writes crossref");
  assert.ok(written.has("generated_note"), "index_page writes generated_note");
  const read = new Set([...APP.matchAll(/\b(?:it|x|y)\.(\w+)/g)].map((m) => m[1]));
  const own = new Set(["_title", "length", "id"]);   // set by the script itself, or not data
  ["id", "authors", "editors", "year", "title", "container", "kind", "url", "doi", "citation", "annotation", "topics", "volumes"].forEach((f) => assert.ok(written.has(f), "index_page writes " + f));
  const wanted = [...read].filter((f) => !own.has(f) && !["score", "pos", "context", "contexts", "name"].includes(f));
  assert.deepEqual(wanted.filter((f) => !written.has(f)), []);
  for (const k of ["items", "volumes", "topics"]) { assert.ok(INDEX.includes('"' + k + '"') || INDEX.includes(k + ":"), k); }
  assert.ok(/"title": v\["title"\]/.test(INDEX));    // volumes carry a title
});

test("the data fields coauthor.js reads are written by coauthor_page", () => {
  const from = COAUTHOR.indexOf("slim = [{"), to = COAUTHOR.indexOf("} for it in ITEMS", from);
  assert.ok(from !== -1 && to !== -1, "found the slim item dict");
  const written = new Set([...COAUTHOR.slice(from, to).matchAll(/"(\w+)":/g)].map((m) => m[1]));
  assert.deepEqual([...written].sort(), ["a", "id", "k", "n", "t", "v", "y"]);
  const read = new Set([...CO.matchAll(/\bit\.(\w+)/g)].map((m) => m[1]));
  assert.deepEqual([...read].filter((f) => !written.has(f)), []);
  assert.ok(COAUTHOR.includes('{"items": slim}'));
});

test("render.py inlines both scripts as plain script elements", () => {
  assert.ok(RENDER.includes('read("templates/app.js")') && RENDER.includes('read("templates/coauthor.js")'));
  assert.ok(INDEX.includes('"<script>" + JS + "</script>"'));
  assert.ok(COAUTHOR.includes('"<script>" + CO_JS + "</script>"'));
  // a plain script must not use module syntax or reference node-only globals unguarded
  for (const src of [APP, CO]) {
    assert.ok(!/^\s*(import|export)\s/m.test(src));
    assert.ok(!/\brequire\(/.test(src));
    assert.ok(!src.includes("</script"));
  }
  const guarded = (src) => /if \(typeof module !== "undefined" && module\.exports\) \{\s*module\.exports = /.test(src);
  assert.ok(guarded(APP) && guarded(CO));
});
