"use strict";
/* Loads build/templates/app.js inside a vm context with a stub page whose ids mirror render.py's index_page(),
   and a stub of the staticSearch engine (only the members app.js touches). */
const { Doc, El, loadScript } = require("./dom");

const VOLUMES = ["Community", "Knowledge Mobilization in the Humanities", "Engaging Knowledge Diversity", "Engaging Platforms in Open Scholarship"];
const TOPICS = ["Open Access", "Data"];
const KINDS = ["Journal article", "Book"];

function item(id, over) {
  return Object.assign({
    id, title: "Title " + id, citation: "Citation " + id, authors: ["Author " + id], editors: [], year: 2000, kind: "Journal article", container: "",
    doi: "", url: "", annotation: "A short annotation.", volumes: ["Community"], topics: [],
  }, over || {});
}

function makeApp(opts) {
  opts = opts || {};
  const doc = new Doc();
  const items = opts.items || [];
  const data = { items, volumes: (opts.volumes || VOLUMES).map((t) => ({ title: t })), topics: opts.topics || TOPICS };
  doc.add("osp-data", "script").textContent = JSON.stringify(data);
  ["results", "status", "chart-year", "chart-volume", "chart-author", "chart-heat", "chart-overlap"].forEach((id) => doc.add(id, id === "results" ? "ol" : id === "status" ? "p" : "figure"));
  const sort = doc.add("sort", "select", { value: "relevance" });
  const relOpt = doc.add("relevance-opt", "option");
  const more = doc.add("more", "button", { hidden: true });
  const viz = doc.add("viz", "div");
  let note = null, box = null;
  if (!opts.noNote) { note = doc.add("ss-unavailable", "div", { hidden: true }); const why = doc.createElement("span"); why.className = "why"; note.appendChild(why); note.why = why; }
  if (!opts.noBox) { box = doc.add("staticSearch", "div"); }

  const env = { sch: null, constructed: 0 };
  class StaticSearch {
    constructor() {
      if (opts.ctorThrows) { throw new Error("engine failed"); }
      env.sch = this; env.constructed++;
      this.queryBox = opts.noQueryBox ? null : { value: "", blurred: 0, blur() { this.blurred++; } };
      this.docsMatchingFilters = { filtersActive: false };
      this.resultSet = { mapDocs: new Map() };
      this.searches = 0;
      this.descFilterCheckboxes = [];
      (opts.volumes || VOLUMES).forEach((v) => this.box("Volume", v));
      (opts.topics || TOPICS).forEach((v) => this.box("Topic", v));
      KINDS.forEach((v) => this.box("Type", v));
      this.box("Has annotation", "true");
      this.dateFilterTextboxes = [this.dateBox("ssDate_Year_from", "Year"), this.dateBox("ssDate_Year_to", "Year"), this.dateBox("ssDate_Other_from", "Other")];
      this.authorBoxes = [];
      this.mapFeatFilters = new Map();
      if (!opts.noAuthorFilter) { const me = this; this.mapFeatFilters.set("Author", { chosen: null, setCheckboxes(list) { this.chosen = list; me.authorBoxes = list; } }); }
    }
    box(title, value) {
      const li = doc.createElement("li"), cb = doc.createElement("input");
      cb.setAttribute("type", "checkbox"); cb.setAttribute("title", title); cb.value = value; li.appendChild(cb);
      this.descFilterCheckboxes.push(cb);
      return cb;
    }
    dateBox(id, title) { const t = doc.createElement("input"); t.setAttribute("id", id); t.setAttribute("title", title); t.value = ""; return t; }
    doSearch() { this.searches++; }
  }

  const loc = { search: opts.search || "", protocol: opts.protocol || "https:" };
  const globals = { document: doc, location: loc };
  if (!opts.noEngine) { globals.StaticSearch = StaticSearch; }
  const { ctx, api } = loadScript("app.js", globals);
  return {
    doc, ctx, api, loc, env, sort, relOpt, more, viz, note, box, items,
    el: (id) => doc.getElementById(id), sch: () => env.sch, st: () => api.getState(),
    ids: () => ((doc.getElementById("results").innerHTML.match(/<li class="card"><h3><a href="items\/([^"]*)\.html"/g)) || []).map((m) => /items\/([^"]*)\.html/.exec(m)[1]),
    /* finish a search as staticSearch would: the engine fills its result set, then calls the hook */
    finish(query, docs, filtersActive, code) {
      const s = env.sch;
      s.queryBox.value = query || "";
      s.docsMatchingFilters.filtersActive = !!filtersActive;
      s.resultSet.mapDocs = new Map(Object.keys(docs || {}).map((k) => [k, docs[k]]));
      s.searchFinishedHook(code === undefined ? 0 : code);
    },
    click(attrs) {
      const b = doc.createElement("button");
      Object.keys(attrs).forEach((k) => b.setAttribute(k, attrs[k]));
      b.parent = viz;
      return viz.dispatch("click", { target: b });
    },
  };
}

module.exports = { makeApp, item, VOLUMES, TOPICS, KINDS, El };
