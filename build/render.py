"""Render the static site from build/dataset.json. Stdlib only."""
import csv
import html
import json
import os
import re
import shutil
import urllib.parse

HERE = os.environ.get("OSP_BUILD_DIR") or os.path.dirname(os.path.abspath(__file__))   # the variable lets the tests build in a scratch copy
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "site")
VERSION = "0.3.0"
TITLE = "Open Scholarship Press Collections Explorer"

e = html.escape


def read(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return f.read()


CSS = read("templates/style.css")
JS = read("templates/app.js")
CO_JS = read("templates/coauthor.js")

with open(os.path.join(HERE, "dataset.json"), encoding="utf-8") as f:
    DS = json.load(f)
with open(os.path.join(HERE, "validation.json"), encoding="utf-8") as f:
    VAL = json.load(f)

EDITION = DS["meta"]["source_fetched"]
ITEMS = DS["items"]
VOLS = DS["volumes"]
LIC = DS["meta"]["licence"]
N = len(ITEMS)
TOPICS = list(DS["lexicon"].keys())
SYNTAX = [
    ("open access", "Items containing any of the words; items with more of them rank higher. Word endings match: repositories finds repository."),
    ("+open +data", "A plus sign makes a word required."),
    ("-facebook", "A minus sign excludes items containing the word."),
    ('"digital commons"', "Exact phrase."),
    ("reposit*  wom?n", "Wildcards: * stands for any letters, ? for one letter, and [ae] for either letter."),
    ("Schöpfel", "Capitals are ignored but accents are not. Search with the accent as it is written in the record, and try both spellings for names such as Schöpfel and Schopfel."),
    ("Filters", "The boxes below the search field narrow the results by volume, topic, type, year, author and editor."),
]


def rel(depth):
    return "../" * depth


def wiki_url(title):
    return "https://en.wikibooks.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="/:_(),'")


def syntax_table():
    rows = "".join(f"<tr><td><code>{e(q)}</code></td><td>{e(d)}</td></tr>" for q, d in SYNTAX)
    return f'<table><thead><tr><th scope="col">Type</th><th scope="col">It finds</th></tr></thead><tbody>{rows}</tbody></table>'


RECOVERY_LABELS = {
    "person-named": "Named author or authors found in or on the source",
    "organisation-on-page": "The organisation that publishes the page, as named on the page",
    "organisation-other": "The organisation behind the page, identified from the citation or from other published descriptions because the page could not be read",
}
XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def page(title, body, depth=0, current="", description="", extra_head="", scripts="", html_id=""):
    """Every page is written as well-formed XHTML5 so that staticSearch can index it."""
    r = rel(depth)
    nav = [("index.html", "Explore", "explore"), ("items/search.html", "Search", "search"), ("coauthorship.html", "Co-authorship", "coauthorship"), ("volumes/index.html", "Volumes", "volumes"),
           ("methodology.html", "Methodology", "methodology"), ("about.html", "About, data and citation", "about")]
    cur = ' aria-current="page"'
    links = "".join(
        f'<li><a href="{r}{h}"{cur if c == current else ""}>{e(t)}</a></li>' for h, t, c in nav)
    out = f'''<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml"{(" id=" + chr(34) + html_id + chr(34)) if html_id else ""}>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<title>{e(title)}</title>
<meta name="description" content="{e(description or 'Search and visualize the annotated bibliographies of the Open Scholarship Press Collections.')}" />
<meta name="generator" content="osp-explorer {VERSION}" />
<style>/*<![CDATA[*/{CSS}/*]]>*/</style>{extra_head}
</head>
<body>
<a class="skip" href="#main">Skip to main content</a>
<header class="site"><div class="wrap">
<p style="margin:0;font-family:var(--serif);font-size:1.15rem;font-weight:600">{TITLE}</p>
<p class="meta">Version {VERSION} · Edition {EDITION} · {N:,} annotated items from {len(VOLS)} volumes</p>
<nav class="primary" aria-label="Primary"><ul>{links}</ul></nav>
</div></header>
<main id="main" tabindex="-1"><div class="wrap">
{body}
</div></main>
<footer class="site"><div class="wrap">
<p>{TITLE}, version {VERSION}, edition {EDITION}. Item records and annotations come from the
<a href="https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections">Open Scholarship Press Collections</a> on Wikibooks
(Implementing New Knowledge Environments, Electronic Textual Cultures Lab, University of Victoria and partners),
used under <a href="{e(LIC['url'])}">{e(LIC['text'])}</a>. The cited articles themselves are linked, not copied.</p>
<p>This site is static HTML, CSS and JavaScript with no external libraries or services, built to the
<a href="https://endings.uvic.ca/principles.html">Endings Principles for Digital Longevity</a>.
The <a href="{r}data/items.json">data</a> are included with the site. See <a href="{r}about.html">About, data and citation</a> for citation instructions.</p>
</div></footer>
{scripts}
</body>
</html>
'''
    return XML_BAD.sub("", out)


HERE_JS = '<script>//<![CDATA[\ndocument.querySelectorAll(".here").forEach(function(n){n.textContent=location.href.split("#")[0];});\n//]]></script>'


def cite_block(depth, label, ident=""):
    return (f'<div class="cite"><h2 style="font-size:1.05rem">How to cite this page</h2>'
            f'<p>{TITLE}, version {VERSION}, edition {EDITION}. {e(label)}{(" Record " + ident + ".") if ident else ""} '
            f'Address: <span class="here">{"[address of this page]"}</span></p></div>')


def note_label(g):
    """The label that always accompanies a generated note: who wrote it, when, and what it rests on."""
    when = g["generated_at"].replace("T", " ").replace("Z", " UTC")[:20].rstrip()
    base = ("the cited work's own page" if g["basis"] == "page-read" else "the citation alone (the page could not be read)")
    return (f'Written by a language model ({g["model"]}) on {when[:10]} at {when[11:16]} UTC, from {base}. '
            "It is not part of the Open Scholarship Press annotation and can contain errors.")


def short_cit(it):
    names = it["authors"] or it["editors"]
    a = ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")
    if not it["authors"] and it["editors"]:
        a += " (ed.)" if len(it["editors"]) == 1 else " (eds.)"
    return f'{a or "No named author"} ({it["year_label"]}). {it["title"] or it["citation"]}'


# ---------- data downloads ----------
def write_data():
    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    out = {"meta": {**DS["meta"], "version": VERSION, "edition": EDITION}, "volumes": [
        {k: v[k] for k in ("slug", "title", "wiki_url", "entries", "legend", "latest_revision", "revision_ids")} for v in VOLS],
        "lexicon": DS["lexicon"], "items": ITEMS}
    with open(os.path.join(SITE, "data", "items.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(SITE, "data", "items.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "authors", "editors", "volume_editors", "contributors", "year", "title", "container", "type", "url", "doi", "volumes", "chapters", "sections", "topics", "annotation_source", "annotation", "citation_as_listed", "author_recovery_basis", "generated_note", "generated_note_basis", "generated_note_model", "generated_note_at", "generated_note_evidence"])
        for it in ITEMS:
            w.writerow([it["id"], "; ".join(it["authors"]), "; ".join(it["editors"]), "; ".join(it["container_editors"]), "; ".join(it["contributors"]), it["year"] or "", it["title"], it["container"], it["kind"], it["url"], it["doi"],
                        "; ".join(it["volumes"]), "; ".join(it["chapters"]), "; ".join(it["sections"]), "; ".join(it["topics"]),
                        "; ".join(it["annotation_source"]), it["annotation"], it["citation"], (it.get("author_recovery") or {}).get("basis", ""),
                        *[(it.get("generated_note") or {}).get(k, "") for k in ("text", "basis", "model", "generated_at", "evidence")]])
    with open(os.path.join(SITE, "data", "validation.json"), "w", encoding="utf-8") as f:
        json.dump(VAL, f, ensure_ascii=False, indent=1)
    readme = f"""# Data model, {TITLE}

Version {VERSION}, edition {EDITION}. Licence of the item records and annotations: {LIC['text']} ({LIC['url']}).
Source: https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections

Files: items.json (full records, volumes, lexicon), items.csv (flat table), validation.json (parser report), coauthorship-ties.csv (one row per pair of authors who share items: author_a, author_b, shared_items, item_ids) and coauthorship-authors.csv (one row per author: items, coauthored_items, coauthors, group, group_size; authors with no co-author have an empty group). Only authors are tied; editors and contributors are not. See section 16 of the Methodology page.

## items.json, item fields

- id: stable identifier (first 10 hex digits of a SHA-1 of the DOI, or of first author, year and title). Item pages live at items/<id>.html.
- authors: list of display names (First Last), split from the citation by a heuristic. Organisations stay whole. Never contains editors.
- editors: names credited as editors of the work itself (the author position ended in ed., eds. or editor). Empty for ordinary works.
- container_editors: for a chapter, the editors of the containing book (from "edited by" in the venue text).
- contributors: collaborators introduced by "with" after the author list.
- year: integer or null. year_label keeps suffixes such as 2015a and n.d.
- title, container (journal, book or publisher text), kind (Journal article, Book chapter, Book or report, Report or web resource; guessed from citation form), url, doi.
- citation: the citation exactly as listed in the first volume where it appears; variants: alternate listings from other volumes.
- annotation: the annotation text (longest version when an item appears in several volumes). Empty when the source has none.
- generated_note: present only on items whose source annotation is empty and for which a descriptive note was generated by a language model. An object with text, basis ("page-read" or "citation-only"), evidence (the address read), model and generated_at (UTC). It is never merged into annotation. In items.csv the same values are in the generated_note_* columns.
- topics: terms from the lexicon below that occur in title or annotation (case-insensitive pattern match, so a hit signals presence of the term, not a judgement of subject).
- annotation_source: the meaning of the marker symbols that precede the entry in its volume (for example annotations drawn from earlier bibliographies).
- placements: one record per volume listing: volume, chapter, sections (heading path), marker symbols.
- volumes, chapters, sections: unions across placements, for filtering.

## Deduplication

Entries are merged across volumes when they share a DOI, a normalized URL, or a normalized title plus year. Entries without DOI or URL and with differing titles remain separate.

## Lexicon

{chr(10).join('- ' + k + ': ' + ', '.join(v) for k, v in DS['lexicon'].items())}

## Known limitations

Author splitting, item type and topics are heuristic. The validation report lists source irregularities. A small set of named corrections (build/corrections.json, listed on the Methodology page) repairs source typing errors; everything else is reported, not repaired.
"""
    with open(os.path.join(SITE, "data", "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)


# ---------- index ----------
def index_page():
    slim = []
    for it in ITEMS:
        slim.append({**{k: it[k] for k in ("id", "authors", "editors", "container_editors", "contributors", "year", "title", "container", "kind", "url", "doi", "citation", "annotation",
                                            "topics", "annotation_source", "volumes", "chapters", "sections")}, "generated_note": it.get("generated_note")})
    data = {"items": slim, "volumes": [{"slug": v["slug"], "title": v["title"], "entries": v["entries"]} for v in VOLS], "topics": TOPICS}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pre = "".join(f'<li><a href="items/{it["id"]}.html">{e(short_cit(it))}</a></li>' for it in ITEMS)
    vol_links = "".join(f'<li><a href="volumes/{v["slug"]}.html">{e(v["title"])}</a> ({v["entries"]} entries)</li>' for v in VOLS)
    body = f'''<h1>Explore the Open Scholarship Press Collections</h1>
<p class="lede">Search, filter and chart {N:,} annotated sources on open social scholarship, drawn from {len(VOLS)} volumes of annotated bibliographies. The articles themselves stay at their original addresses.</p>
<div class="nojs" role="note"><p><strong>JavaScript is off or unavailable.</strong> Search and filters need JavaScript. Every volume and every item has its own page below, and the complete list works as plain links.</p><ul>{vol_links}</ul></div>
<div class="layout jsonly">
<aside class="filters" aria-label="Search and filters"><details id="filterbox"><summary>Search and filters</summary>
<details class="syntax"><summary id="qhelp">Query syntax</summary>{syntax_table()}</details>
<div id="ss-unavailable" class="nojs-note" hidden="hidden"><p><strong>Search and filters are unavailable.</strong> <span class="why"></span> Browse the <a href="volumes/index.html">volume pages</a>; the charts and list below still show the whole collection.</p></div>
<!--@STATICSEARCH@--></details></aside>
<section aria-label="Results">
<details open class="vizbox"><summary style="font-family:var(--serif);font-size:1.2rem;font-weight:600">Visual overview of the current results</summary>
<div class="viz" id="viz" style="margin-top:0.75rem">
<figure class="chart wide" id="chart-year"></figure>
<figure class="chart" id="chart-volume"></figure>
<figure class="chart" id="chart-author"></figure>
<figure class="chart wide" id="chart-heat"></figure>
<figure class="chart wide" id="chart-overlap"></figure>
</div></details>
<div class="statusrow"><p id="status" role="status" aria-live="polite"></p>
<div><label for="sort">Sort by </label><select id="sort"><option value="relevance" id="relevance-opt">Relevance</option><option value="author">Author</option><option value="year-desc">Year, newest first</option><option value="year-asc">Year, oldest first</option><option value="title">Title</option></select></div></div>
<ol class="results" id="results" aria-label="Results"></ol>
<p><button type="button" id="more" class="secondary" hidden></button></p>
</section></div>
<section class="prerender" aria-label="All items"><h2>All {N:,} items</h2><ol>{pre}</ol></section>
<script type="application/json" id="osp-data">{blob}</script>'''
    boot = ('<script>(function(){var d=document.getElementById("filterbox");if(d&&window.matchMedia&&matchMedia("(min-width:60.01rem)").matches)d.open=true;})();</script>')
    scripts = boot + "<script>" + JS + "</script>"
    return page(f"{TITLE}", body, 0, "explore", scripts=scripts)


# ---------- volumes ----------
def volume_pages():
    os.makedirs(os.path.join(SITE, "volumes"), exist_ok=True)
    cards = ""
    for v in VOLS:
        mine = [it for it in ITEMS if any(p["vslug"] == v["slug"] for p in it["placements"])]
        cards += f'<li><h2 style="font-size:1.2rem"><a href="{v["slug"]}.html">{e(v["title"])}</a></h2><p>{len(mine)} items. <a href="{e(v["wiki_url"])}">Read the volume on Wikibooks</a>.</p></li>'
        groups = {}
        for it in mine:
            for p in it["placements"]:
                if p["vslug"] == v["slug"]:
                    groups.setdefault((p["chapter"], " › ".join(p["sections"])), []).append(it)
        body = f'<h1>{e(v["title"])}</h1><p class="lede">{len(mine)} items in this volume (unique across the collection). Latest wiki revision used: {e(v["latest_revision"][:10])}. Source: <a href="{e(v["wiki_url"])}">{e(v["wiki_url"])}</a>.</p>'
        if v["legend"]:
            body += '<details><summary>Annotation markers used in this volume</summary><dl class="facts">' + "".join(
                f'<dt>{e(k)}</dt><dd>{e(d)}</dd>' for k, d in v["legend"].items()) + "</dl></details>"
        for (chapter, sec), its in groups.items():
            hid = re.sub(r"[^a-z0-9]+", "-", (chapter + sec).lower())
            suffix = (" › " + e(sec)) if sec else ""
            body += f'<h2 id="{hid}">{e(chapter)}{suffix}</h2>'
            for it in sorted(its, key=lambda x: ((x["authors"] or x["editors"] or [""])[0].lower(), x["year"] or 0)):
                href = ("https://doi.org/" + it["doi"]) if it["doi"] else it["url"]
                ann = ('<p class="ann">' + e(it["annotation"]) + "</p>") if it["annotation"] else ""
                if not it["annotation"] and it.get("generated_note"):
                    g = it["generated_note"]
                    ann = f'<p class="ann generated">{e(g["text"])} <span class="genlabel">{e(note_label(g))}</span></p>'
                src = ('<p><a href="' + e(href) + '">Open source</a></p>') if href else ""
                body += (f'<article class="entry" id="{it["id"]}"><h3><a href="../items/{it["id"]}.html">{e(short_cit(it))}</a></h3>'
                         f'<p style="margin:0;color:var(--muted)">{e(it["citation"])}</p>{ann}{src}</article>')
        body += cite_block(1, f"Volume: {v['title']}.")
        with open(os.path.join(SITE, "volumes", v["slug"] + ".html"), "w", encoding="utf-8") as f:
            f.write(page(f"{v['title']} · {TITLE}", body, 1, "volumes", scripts=HERE_JS))
    body = f'<h1>Volumes</h1><p class="lede">Each volume page lists every entry with its annotation and works without JavaScript.</p><ul class="prose" style="list-style:none;padding:0">{cards}</ul>'
    with open(os.path.join(SITE, "volumes", "index.html"), "w", encoding="utf-8") as f:
        f.write(page(f"Volumes · {TITLE}", body, 1, "volumes", scripts=HERE_JS))


# ---------- items ----------
def ss_meta(it):
    """Filter and title metadata read by staticSearch (class names fixed by that tool)."""
    def m(name, cls, value):
        return f'<meta name="{e(name)}" class="staticSearch_{cls}" content="{e(value)}" />'

    out = [m("docTitle", "docTitle", it["title"] or it["citation"][:120]),
           m("docSortKey", "docSortKey", ((it["authors"] or it["editors"] or [""])[0] + " " + str(it["year"] or 9999) + " " + it["title"]).lower())]
    out += [m("Volume", "desc", v) for v in it["volumes"]]
    out += [m("Topic", "desc", t) for t in it["topics"]]
    out.append(m("Type", "desc", it["kind"]))
    out.append(m("Has annotation", "bool", "true" if it["annotation"] else "false"))
    if it["year"]:
        out.append(m("Year", "date", str(it["year"])))
    out += [m("Author", "feat", a) for a in it["authors"]]
    out += [m("Editor", "feat", a) for a in it["editors"] + it["container_editors"]]
    return "\n" + "\n".join(out)


def item_pages():
    os.makedirs(os.path.join(SITE, "items"), exist_ok=True)
    roots = {v["slug"]: v for v in VOLS}
    for it in ITEMS:
        href = ("https://doi.org/" + it["doi"]) if it["doi"] else it["url"]
        places = ""
        for p in it["placements"]:
            v = roots[p["vslug"]]
            wiki = v["wiki_url"] + "/" + urllib.parse.quote(p["chapter"].replace(" ", "_"))
            secs = (" › " + e(" › ".join(p["sections"]))) if p["sections"] else ""
            places += (f'<li><a href="../volumes/{p["vslug"]}.html#{it["id"]}">{e(p["volume"])}</a> › {e(p["chapter"])}'
                       f'{secs} (<a href="{e(wiki)}">chapter on Wikibooks</a>)</li>')
        facts = []
        if it["authors"]:
            facts.append(("Authors", e("; ".join(it["authors"]))))
        if it["editors"]:
            facts.append(("Editors", e("; ".join(it["editors"]))))
        if not it["authors"] and not it["editors"]:
            facts.append(("Authors", "No named author in the source"))
        if it["contributors"]:
            facts.append(("With", e("; ".join(it["contributors"]))))
        if it["container_editors"]:
            facts.append(("Editors of the containing volume", e("; ".join(it["container_editors"]))))
        rec = it.get("author_recovery")
        if rec:
            facts.append(("Author recovered", e(RECOVERY_LABELS[rec["basis"]]) + ". " + e(rec["note"]) +
                          ' <a href="' + e(rec["evidence"]) + '">Evidence</a>'))
        facts += [("Year", e(it["year_label"])), ("Type", e(it["kind"]))]
        if it["container"]:
            facts.append(("Published in", e(it["container"])))
        if href:
            facts.append(("Source", f'<a href="{e(href)}">{e(href)}</a>'))
        if it["topics"]:
            facts.append(("Detected topics", e("; ".join(it["topics"]))))
        if it["annotation_source"]:
            facts.append(("Annotation origin", e("; ".join(it["annotation_source"]))))
        dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)
        variants = ("<h2>Other listings</h2><ul>" + "".join(f"<li>{e(v)}</li>" for v in it["variants"]) + "</ul>") if it["variants"] else ""
        ann = ("<p>" + e(it["annotation"]) + "</p>") if it["annotation"] else "<p>The source volume gives no annotation for this entry.</p>"
        gen = it.get("generated_note")
        gen_html = ""
        if gen:
            ev = ""
            if gen["evidence"]:
                ev = (' <a href="' + e(gen["evidence"]) + '">' + ("Source read" if gen["basis"] == "page-read" else "Address in the citation (not read)") + "</a>.")
            gen_html = (f'<div class="generated prose"><h2>Descriptive note (generated)</h2><p>{e(gen["text"])}</p>'
                        f'<p class="genlabel">{e(note_label(gen))}{ev} See <a href="../methodology.html#generated">section 17 of the Methodology</a>.</p></div>')
        body = (f'<p><a href="../index.html">← Explore all items</a></p><h1>{e(it["title"] or it["citation"])}</h1>'
                f'<p class="lede">{e(short_cit(it))}</p><dl class="facts">{dl}</dl>'
                f'<h2>Annotation</h2><div id="annotation" class="prose">{ann}</div>{gen_html}'
                f'<h2>Where it appears</h2><ul class="prose">{places}</ul>{variants}'
                f'<h2>Citation as listed</h2><p class="prose">{e(it["citation"])}</p>'
                f'{cite_block(1, "Record: " + (it["title"] or "untitled") + ".", it["id"])}')
        body = body.replace("><", ">\n<")  # whitespace between fields, so the search index does not join their words
        with open(os.path.join(SITE, "items", it["id"] + ".html"), "w", encoding="utf-8") as f:
            f.write(page(f'{it["title"] or "Record"} · {TITLE}', body, 1, "", extra_head=ss_meta(it), scripts=HERE_JS, html_id="rec-" + it["id"]))


# ---------- search (staticSearch) ----------
def search_page():
    body = f"""<h1>Search the annotations</h1>
<p class="lede">Full-text search across the {N:,} item records, with filters. To chart the results, use <a href="../index.html">Explore</a>.</p>
<details class="syntax"><summary>Query syntax</summary>{syntax_table()}</details>
<div id="staticSearch"></div>"""
    with open(os.path.join(SITE, "items", "search.html"), "w", encoding="utf-8") as f:
        f.write(page(f"Search · {TITLE}", body, 1, "search"))


# ---------- about ----------
def about_page():
    anomalies = VAL["anomalies"]
    arows = "".join(f'<tr><td>{e(a["type"])}</td><td>{e(a.get("volume", a.get("page", "")))}</td><td>{e(str(a.get("text", a.get("count", ""))))[:140]}</td></tr>' for a in anomalies)
    vrows = "".join(f'<tr><th scope="row">{e(v["title"])}</th><td>{v["entries"]}</td><td>{VAL["per_volume"][v["slug"]]["reference_lines_in_list_page"] or "none"}</td><td>{e(v["latest_revision"][:10])}</td></tr>' for v in VOLS)
    endings = [
        ("1 Data", "Items are plain JSON and CSV (open formats) with a documented data model; the programs that read and parse the source text are in the build folder under version control."),
        ("2 Documentation", "The data model, lexicon and limitations are in data/README.md. Licence and attribution appear on every page."),
        ("3 Processing", "The build validates the parse against each volume's reference list and stops on any anomaly not previously reviewed."),
        ("4.1 to 4.3", "Static HTML, CSS and JavaScript only. No server software, frameworks, fonts, analytics or services. Search uses staticSearch, an Endings project tool that runs at build time and ships its own scripts and index files with the site (the 4.8 and 4.9 concessions)."),
        ("4.4", "Every volume and item has its own plain address. The exception is search state: Explore and the Search page record it after a question mark, as staticSearch does."),
        ("4.5, 4.6", "The full data ship with the site, and the main page embeds them. Search needs the index files to be served over the web; from a saved file, Explore still shows the list and charts."),
        ("4.7", "Without JavaScript, the main page, volume pages and item pages remain readable and linked."),
        ("5.1 to 5.5", "Editions are built on a schedule chosen by the maintainers, carry a version and edition date on every page, include citation instructions, and keep item addresses stable (identifiers derive from the item's content, not its position)."),
    ]
    erows = "".join(f'<tr><th scope="row">{e(a)}</th><td>{e(b)}</td></tr>' for a, b in endings)
    body = f'''<h1>About, data and citation</h1>
<div class="prose">
<p>This explorer indexes the annotated entries of seven volumes of the Open Scholarship Press Collections. It reads the public wiki text, keeps authors, years, venues, section headings and annotations, and links to each source rather than copying it. Observatory volumes, French editions and the Curated Volumes are outside this first edition.</p>
<h2>Using the search</h2>{syntax_table()}
<p>Filters combine: choices inside one group widen the result (any selected volume), and choices across groups narrow it. The address in your browser records the current search so you can share it.</p>
<h2 id="engine">The search engine</h2>
<p>Searching and filtering on Explore and on the Search page use <a href="https://endings.uvic.ca/staticSearch/">staticSearch</a>, a search tool from the Endings project (release 2.0.3, taken from a fixed commit that the build verifies). It needs no server or database. When the site is built, staticSearch reads every item page and writes an index of word stems (English Porter2 stemming, with a stop-word list) as many small data files, which are published with the site. In your browser, its script fetches only the index files for the words you type and does the matching there; nothing you type is sent anywhere.</p>
<p>Word endings match ("repositories" finds "repository"). Plain words match items containing any of them, and items containing more of them rank higher. Common words are ignored and reported. The syntax above covers required words, exclusions, phrases and wildcards. The Search page shows the engine's own result list with excerpts; Explore uses the same engine and draws the results as cards and charts. The choices made for this collection are set out in section 11 of the <a href="methodology.html">Methodology</a>.</p>
<h2>Downloads</h2>
<ul><li><a href="data/items.json">items.json</a>, full records</li><li><a href="data/items.csv">items.csv</a>, flat table</li><li><a href="data/README.md">README.md</a>, data model and lexicon</li><li><a href="data/validation.json">validation.json</a>, parser report</li></ul>
<h2>How to cite</h2>
<div class="cite"><p>{TITLE}, version {VERSION}, edition {EDITION}. Address: <span class="here">[address of this page]</span>. Underlying text: Open Scholarship Press Collections, Wikibooks, {e(LIC['text'])}.</p></div>
<p>To cite an item, use the citation block at the foot of its record page and cite the original work as listed there.</p>
<h2>Licence</h2>
<p>Item records and annotations: <a href="{e(LIC['url'])}">{e(LIC['text'])}</a>, inherited from Wikibooks. Reuse requires attribution to the Open Scholarship Press Collections authors and the same licence. The software licence is to be set by the maintainers.</p>
<h2>Source volumes and checks</h2>
</div>
<table class="data"><thead><tr><th scope="col">Volume</th><th scope="col">Entries parsed</th><th scope="col">Lines in its reference list</th><th scope="col">Wiki revision</th></tr></thead><tbody>{vrows}</tbody></table>
<div class="prose"><p>Parsed counts exceed reference-list counts where entries repeat across sections of a volume or the list is partial. Items shared by several volumes are merged: {DS["meta"]["raw_entries"]:,} listed entries become {N:,} unique items.</p>
<h2>Source irregularities found</h2><p>These are reported, not repaired. For the items without an annotation, the Methodology page (<a href="methodology.html#generated">section 17</a>) records the short labelled notes that a language model added; the source annotation itself stays empty.</p></div>
<table class="data"><thead><tr><th scope="col">Kind</th><th scope="col">Where</th><th scope="col">Detail</th></tr></thead><tbody>{arows}</tbody></table>
<div class="prose"><h2>Endings principles in practice</h2></div>
<table class="data"><thead><tr><th scope="col">Principle</th><th scope="col">How this site meets it</th></tr></thead><tbody>{erows}</tbody></table>
<div class="prose"><h2>Accessibility</h2><p>The pages use landmarks, labelled controls, keyboard-operable charts built from buttons and tables, visible focus, light and dark themes that follow your system, reduced-motion support and text that scales. Charts present their numbers as text and in tables, and no meaning rests on colour alone. Please report barriers to the maintainers.</p></div>'''
    body = body.replace("<table", '<div class="tablewrap" tabindex="0" role="region" aria-label="Scrollable table"><table').replace("</table>", "</table></div>")
    with open(os.path.join(SITE, "about.html"), "w", encoding="utf-8") as f:
        f.write(page(f"About, data and citation · {TITLE}", body, 0, "about", scripts=HERE_JS))


# ---------- co-authorship ----------
def coauthor_stats():
    """Ties between authors of the same item, over the whole collection (unfiltered). Authors only; editors and contributors are not authors."""
    from collections import defaultdict
    from itertools import combinations
    count = defaultdict(int)
    ties = defaultdict(list)
    for it in ITEMS:
        names = sorted(set(it["authors"]))
        for n in names:
            count[n] += 1
        for a, b in combinations(names, 2):
            ties[(a, b)].append(it["id"])
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in ties:
        parent[find(a)] = find(b)
    members = defaultdict(list)
    for n in {x for t in ties for x in t}:
        members[find(n)].append(n)
    groups = sorted(members.values(), key=lambda g: (-len(g), min(g)))
    gid = {n: i + 1 for i, g in enumerate(groups) for n in g}
    co = defaultdict(set)
    nb = defaultdict(set)
    for (a, b), ids in ties.items():
        co[a].update(ids)
        co[b].update(ids)
        nb[a].add(b)
        nb[b].add(a)
    return count, ties, groups, gid, co, nb


def coauthor_files(count, ties, groups, gid, co, nb):
    with open(os.path.join(SITE, "data", "coauthorship-authors.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["author", "items", "coauthored_items", "coauthors", "group", "group_size"])
        for n in sorted(count, key=lambda x: (-len(co[x]), x)):
            g = gid.get(n)
            w.writerow([n, count[n], len(co[n]), len(nb[n]), g or "", len(groups[g - 1]) if g else 1])
    with open(os.path.join(SITE, "data", "coauthorship-ties.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["author_a", "author_b", "shared_items", "item_ids"])
        for (a, b), ids in sorted(ties.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            w.writerow([a, b, len(ids), "; ".join(ids)])


def coauthor_page():
    count, ties, groups, gid, co, nb = coauthor_stats()
    coauthor_files(count, ties, groups, gid, co, nb)
    slim = [{"id": it["id"], "a": it["authors"], "y": it["year"], "v": it["volumes"], "t": it["topics"], "k": it["kind"],
             "n": it["title"] if len(set(it["authors"])) > 1 else ""} for it in ITEMS if it["authors"]]
    years = [it["year"] for it in ITEMS if it["year"]]
    kinds = sorted({it["kind"] for it in ITEMS})
    data = {"items": slim}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    def boxes(name, values):
        return "".join(f'<label class="opt"><input type="checkbox" name="{name}" value="{e(v)}" /> <span>{e(v)}</span></label>' for v in values)
    vols = "".join(f'<label class="opt"><input type="checkbox" name="Volume" value="{e(v["title"])}" /> <span>{e(v["title"])}</span></label>' for v in VOLS)
    datalist = "".join(f'<option value="{e(n)}"></option>' for n in sorted(gid))
    top = sorted(co, key=lambda n: (-len(co[n]), -len(nb[n]), n))[:12]
    people_rows = "".join(f'<tr><th scope="row">{e(n)}</th><td>{count[n]}</td><td>{len(co[n])}</td><td>{len(nb[n])}</td></tr>' for n in top)
    pairs = sorted((kv for kv in ties.items() if len(kv[1]) >= 2), key=lambda kv: (-len(kv[1]), kv[0]))[:15]
    pair_rows = "".join(f'<tr><th scope="row">{e(a)} and {e(b)}</th><td>{len(ids)}</td></tr>' for (a, b), ids in pairs)

    def table(head, rows):
        return ('<div class="tablewrap" tabindex="0" role="region" aria-label="Scrollable table"><table class="data"><thead><tr>' +
                "".join(f'<th scope="col">{h}</th>' for h in head) + "</tr></thead><tbody>" + rows + "</tbody></table></div>")
    body = f"""<h1>Co-authorship</h1>
<p class="lede">Authors who share an item are tied together. The network shows every connected group of authors, and the filters choose which items count. Circle size follows the number of items an author has in the current selection; line thickness follows the number of items two authors share.</p>
<div class="nojs" role="note"><p><strong>JavaScript is off or unavailable.</strong> The interactive network needs JavaScript. The tables below describe the whole collection, and the ties are available as <a href="data/coauthorship-ties.csv">CSV</a>.</p>
{table(["Author", "Items", "Co-authored items", "Co-authors"], people_rows)}
{table(["Pair sharing two or more items", "Shared items"], pair_rows)}</div>
<div class="layout jsonly">
<aside class="filters" aria-label="Co-authorship filters"><details id="filterbox" open="open"><summary>Filters</summary>
<form id="co-filters" onsubmit="return false">
<fieldset><legend>Volume</legend><div class="scroll">{vols}</div></fieldset>
<fieldset><legend>Topic</legend><div class="scroll">{boxes("Topic", TOPICS)}</div></fieldset>
<fieldset><legend>Type</legend>{boxes("Type", kinds)}</fieldset>
<fieldset><legend>Year</legend><div class="yearrange"><label for="yfrom" class="sr">From year</label><input type="number" id="yfrom" min="{min(years)}" max="{max(years)}" placeholder="{min(years)}" />
<span aria-hidden="true">to</span><label for="yto" class="sr">To year</label><input type="number" id="yto" min="{min(years)}" max="{max(years)}" placeholder="{max(years)}" /></div></fieldset>
<fieldset><legend>Network</legend>
<p><label for="tie">Draw a tie when two authors share at least</label> <select id="tie"><option value="1">1 item</option><option value="2">2 items</option><option value="3">3 items</option></select></p>
<p><label for="group">Draw groups of at least</label> <select id="group"><option value="2">2 authors</option><option value="3">3 authors</option><option value="4">4 authors</option><option value="5">5 authors</option><option value="8">8 authors</option></select></p></fieldset>
<fieldset><legend>Find an author</legend>
<label for="find" class="sr">Author name</label><input type="text" id="find" list="co-names" autocomplete="off" placeholder="Start typing a name" />
<datalist id="co-names">{datalist}</datalist>
<p id="find-note" role="status" class="sub"></p>
<label class="opt"><input type="checkbox" id="only" /> <span>Show only that author's group</span></label></fieldset>
<p><button type="button" class="secondary" id="co-reset">Reset all filters</button></p>
</form></details></aside>
<section aria-label="Co-authorship results">
<p id="co-status" role="status" aria-live="polite"></p>
<dl class="metrics"><div><dt>Items with a named author</dt><dd id="m-items"></dd></div><div><dt>Items with more than one author</dt><dd id="m-multi"></dd></div><div><dt>Authors</dt><dd id="m-authors"></dd></div>
<div><dt>Ties between authors</dt><dd id="m-ties"></dd></div><div><dt>Groups</dt><dd id="m-groups"></dd></div><div><dt>Authors in largest group</dt><dd id="m-largest"></dd></div></dl>
<figure class="chart wide"><figcaption id="net-cap">Network of co-authors</figcaption>
<p class="sub">Each circle is an author; a line joins two authors who share an item. Groups are laid out separately, largest first. Colour carries no information. Select a circle to see that author's ties.</p>
<div id="network"></div></figure>
<div id="panel" class="panel" aria-live="polite"></div>
<div class="viz">
<figure class="chart"><figcaption>Most active co-authors</figcaption><p class="sub">Ranked by items written with at least one other author.</p><div id="t-people"></div></figure>
<figure class="chart"><figcaption>Pairs who share most</figcaption><p class="sub">Pairs sharing two or more items.</p><div id="t-ties"></div></figure>
<figure class="chart"><figcaption>Authors per item</figcaption><p class="sub">Items with at least one named author.</p><div id="t-per"></div></figure>
<figure class="chart"><figcaption>Largest groups</figcaption><p class="sub">Connected groups of any size, largest first.</p><div id="t-groups"></div></figure>
</div>
<p>The ties and authors can be downloaded for the whole collection as <a href="data/coauthorship-ties.csv">CSV of ties</a> and <a href="data/coauthorship-authors.csv">CSV of authors</a>. How ties are counted is set out in section 16 of the <a href="methodology.html#coauthorship">Methodology</a>.</p>
</section></div>
<script type="application/json" id="co-data">{blob}</script>"""
    with open(os.path.join(SITE, "coauthorship.html"), "w", encoding="utf-8") as f:
        f.write(page(f"Co-authorship · {TITLE}", body, 0, "coauthorship", description="Explore which authors in the Open Scholarship Press Collections write together, with filters.",
                     scripts="<script>" + CO_JS + "</script>"))


# ---------- methodology ----------
def methodology_page():
    from collections import Counter
    kinds = Counter(it["kind"] for it in ITEMS)
    n_ann = sum(1 for it in ITEMS if it["annotation"])
    n_noauth = sum(1 for it in ITEMS if not it["authors"] and not it["editors"])
    n_topic = sum(1 for it in ITEMS if it["topics"])
    n_multi = sum(1 for it in ITEMS if len(it["placements"]) > 1)
    n_doi = sum(1 for it in ITEMS if it["doi"])
    n_url = sum(1 for it in ITEMS if it["url"] or it["doi"])
    n_nodate = sum(1 for it in ITEMS if it["year"] is None)
    n_src = sum(1 for it in ITEMS if it["annotation_source"])
    raw = DS["meta"]["raw_entries"]
    co_count, co_ties, co_groups, co_gid, co_co, co_nb = coauthor_stats()
    co_multi = sum(1 for it in ITEMS if len(set(it["authors"])) > 1)
    co_withauth = sum(1 for it in ITEMS if it["authors"])
    co_pairs = sum(1 for g in co_groups if len(g) == 2)
    rec_log = DS["meta"]["author_recovery"]
    rec_n = {b: sum(1 for r in rec_log if r["basis"] == b) for b in RECOVERY_LABELS}
    rec_rows = "".join(f'<tr><td>{e(r["title"][:70])}</td><td>{e("; ".join(r["authors"]))}</td><td>{e(RECOVERY_LABELS[r["basis"]].split(" as ")[0].split(" because")[0])}</td><td><a href="{e(r["evidence"])}">Evidence</a></td></tr>' for r in rec_log)
    gn = DS["meta"].get("generated_notes", [])
    gn_basis = {b: sum(1 for g in gn if g["basis"] == b) for b in ("page-read", "citation-only")}
    gn_models = sorted({g["model"] for g in gn})
    gn_first = min((g["generated_at"] for g in gn), default="")
    gn_last = max((g["generated_at"] for g in gn), default="")
    gn_rows = "".join(f'<tr><td><a href="items/{g["id"]}.html">{e(g["title"][:90])}</a></td><td>{e(g["basis"])}</td><td>{e(g["generated_at"].replace("T", " ").replace("Z", " UTC"))}</td></tr>' for g in gn)
    n_noann = sum(1 for it in ITEMS if not it["annotation"])
    n_ed = sum(1 for it in ITEMS if it["editors"])
    n_ce = sum(1 for it in ITEMS if it["container_editors"])
    n_contrib = sum(1 for it in ITEMS if it["contributors"])
    nv_rows = "".join(f'<tr><td>{e(g["name"])}</td><td>{e("; ".join(g["variants"]))}</td><td>{e(g["reason"])}</td><td>{g["applied"]}</td></tr>' for g in DS["meta"]["name_variants"])
    corr_rows = "".join(f'<tr><td>{e(c["match"])}</td><td>{e(c["reason"])}</td><td>{c["applied"]}</td></tr>' for c in DS["meta"]["corrections"])
    kind_rows = "".join(f'<tr><th scope="row">{e(k)}</th><td>{v}</td></tr>' for k, v in kinds.most_common())
    lex_rows = "".join(
        f'<tr><th scope="row">{e(k)}</th><td>{e(", ".join(v))}</td></tr>' for k, v in DS["lexicon"].items())
    vol_rows = "".join(
        f'<tr><th scope="row">{e(v["title"])}</th><td>{v["entries"]}</td><td>{e(", ".join(v["legend"].keys()) or "none")}</td></tr>' for v in VOLS)
    def table(head, rows):
        return ('<div class="tablewrap" tabindex="0" role="region" aria-label="Scrollable table"><table class="data"><thead><tr>' +
                "".join(f'<th scope="col">{h}</th>' for h in head) + "</tr></thead><tbody>" + rows + "</tbody></table></div>")
    body = f"""<h1>Methodology</h1>
<p class="lede">How this edition decides what is an item, who wrote it, what it is about, and which items count as the same. Every rule below is applied by program code, never by hand, so a rebuild reproduces the same result. Where a rule is a guess, the page says so.</p>
<nav aria-label="On this page" class="prose"><ul>
<li><a href="#scope">1. Scope and sources</a></li><li><a href="#capture">2. Source text</a></li><li><a href="#entries">3. Deciding what counts as an entry</a></li>
<li><a href="#citations">4. Reading a citation</a></li><li><a href="#authors">5. Deciding who the authors and editors are</a></li><li><a href="#types">6. Deciding the type of work</a></li>
<li><a href="#dupes">7. Deciding that two entries are the same item</a></li><li><a href="#ids">8. Identifiers and addresses</a></li><li><a href="#topics">9. Deciding topics</a></li>
<li><a href="#origin">10. Annotation origin</a></li><li><a href="#search">11. How search and filters decide</a></li><li><a href="#charts">12. What the charts count</a></li>
<li><a href="#checks">13. Checks and what they cannot show</a></li><li><a href="#limits">14. Limits and cautions</a></li><li><a href="#repro">15. Reproducing and changing the method</a></li><li><a href="#coauthorship">16. Co-authorship</a></li><li><a href="#generated">17. Generated descriptive notes</a></li></ul></nav>
<div class="prose">
<h2 id="scope">1. Scope and sources</h2>
<p>The unit of analysis is the annotated bibliography entry: one cited work with an annotation written by the Open Scholarship Press authors. The explorer reads seven volumes from the <a href="https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections">Open Scholarship Press Collections</a> hub on English Wikibooks: Community, Connection, Policy, Training, Knowledge Mobilization in the Humanities, Engaging Knowledge Diversity, and Engaging Platforms in Open Scholarship.</p>
<p>Four Observatory volumes (Foundational Observations and Extensions, in English and French) are left out because they appear to be essays about policy events rather than lists of cited works with annotations (this was judged from their page titles and structure, not from a full reading). The French editions and the separate Curated Volumes are also outside this edition. The cited works are not downloaded: the explorer keeps their bibliographic details and the annotations, and links to the original.</p>
<h2 id="capture">2. Source text</h2>
<p>The source is the public wikitext of every Wikibooks page whose title begins with the name of one of the seven volumes. For each page the build keeps the revision identifier and timestamp. This edition uses the source text as it stood on {EDITION}. The licence is taken from the source site, which reports {e(LIC['text'])}, and each volume page on this site states the latest revision used.</p>
<h2 id="entries">3. Deciding what counts as an entry</h2>
<p>Each chapter page is read line by line. Headings (<code>==</code> to <code>=====</code>) build the section path shown as chapter and sections. A line starts a new entry when all of these hold:</p>
<ul><li>it is bold wiki text on a line of its own (the wiki's way of setting a citation);</li><li>it is longer than 40 characters and does not end in a colon (this excludes glossary terms such as a bold definition heading);</li><li>it contains a year (1500 to 2099, with an optional letter such as 2015a, or n.d.), a quoted title, or a web address.</li></ul>
<p>Everything after that line, up to the next entry or heading, is the annotation, with wiki markup removed. Introductions, abstracts and executive summaries are never read as entry sources. The alphabetical reference lists are not parsed into items; they are used only as a cross-check (section 13).</p>
<p>Some entries are filed in one section and pointed to from another by a line that repeats the entry followed by a bracketed see-reference. The build skips those pointer lines ({VAL['info']['cross_reference_lines_skipped']} in this edition) and never parses them as entries.</p>
<p>Result: {raw:,} entries listed across the seven volumes, before merging duplicates (section 7).</p>
<h2 id="citations">4. Reading a citation</h2>
<p>The wiki uses several citation styles. The parser tries them in this order and takes the first that fits:</p>
<ol><li>The entry begins with a quotation mark or italics: no author was given, and the whole line is the title.</li><li>Author-year in parentheses, as in APA: <code>Authors. (2011). Title.</code></li><li>Author-year after a full stop, as in Chicago: <code>Authors. 2011. Title.</code></li><li>Title-first or MLA-like: the authors end at the first sentence boundary before a quoted or italic title, and the year is the last year found in the line.</li></ol>
<p>The title is the quoted text, or the italic text when there are no quotes, or else the first sentence. Everything after the title is kept as the venue ("published in"). A DOI is any <code>10.nnnn/</code> string; the web address is the first <code>http</code> address. Leading symbols (such as +, a dagger, a triangle, or Greek letters such as Φ and Δ) are markers, not part of the citation (section 10); the program removes them before reading any name. Source typing errors are reported, not corrected: for example, a DOI written <code>10/1177/…</code> stays as written.</p>
<p>The citation text as the volume lists it is kept in full on every item, so any parsing mistake can be checked against it.</p>
<h2 id="authors">5. Deciding who the authors and editors are</h2>
<p>Four groups of people are kept apart, because a person who edited a book did not write the chapters in it:</p>
<ul>
<li><strong>Authors</strong>: the names in the author position of the citation.</li>
<li><strong>Editors</strong>: when the author position ends in "ed.", "eds.", "editor", "editors" or "(Ed.)", the work is an edited book or issue. Those names are recorded as editors and the author list stays empty. The words "ed" and "eds" are removed and never kept as part of a name. {n_ed} items are edited works of this kind.</li>
<li><strong>Volume editors</strong>: for a chapter, the names after "edited by" in the venue text are the editors of the containing book, recorded separately and never counted as authors. {n_ce} items carry them.</li>
<li><strong>Contributors</strong>: names introduced by "with", such as "with the INKE Research Group", are collaborators credited after the authors. {n_contrib} items have them. A group introduced by "and the" at the end of the author list (for example "and the INKE and ETCL Research Groups") stays an author as one collective name.</li></ul>
<p>The remaining author text is split at commas and "and". If the first name is written "Last, First", it is turned into "First Last"; later names are taken as written. A name list is treated as an organisation, and left whole, when the second piece is long (more than three words) or the first piece contains a bracket or words such as "of", "for" or "the". "et al." is dropped. This is a heuristic: it handles most personal names correctly, but organisations with commas, double-barrelled names and unusual titles can be split wrongly. The author chart counts authors only, each name once per item; two spellings of one person count as two people. The Author and Editor filters look in the two groups separately; a plain word search looks at every name on the page.</p>
<p>Names are then made consistent in two steps. First, a single capital letter standing alone is an initial and always takes a full stop, so "Brett D Hirsch" and "Brett D. Hirsch" are one name. Second, a reviewed table (<code>build/name_variants.json</code>) maps variants of the same person to the most complete form found in the sources, for example "Ray Siemens" and "Raymond Siemens" to "Raymond G. Siemens". {len(DS["meta"]["name_variants"])} people are in the table. Variants that only share a surname and initial but may be different people (such as Hannah McGregor and Heidi McGregor) are left separate. The table covers the variants found by comparing surnames and first initials; a variant with a different surname spelling, or a different order of names, would not be found.</p>
{table(["Form used", "Written in the sources as", "Reason", "Uses"], nv_rows)}
<p>After parsing, the build tests every name. It stops if a name still contains a role word (ed, eds, editor, translator), a marker symbol, a Greek letter, a year, a quotation mark or a web address, so that such defects cannot pass unnoticed.</p>
<h3 id="recovery">Data recovery: items listed without an author</h3>
<p>In the volumes, {len(rec_log) + n_noauth} items were listed with no author, almost all of them websites, blogs, reports and reference pages cited under their title. For this edition each one was checked against its own source on 26 October 2026: the cited address was opened, and its page title, site name, copyright line, structured publisher data, bylines and about text were read. Where the page could not be read (blocked automated access, an error, a page that shows no text without scripts, or an address that has moved), the name was taken from the citation itself or from the publisher's own published descriptions, found by search. The result is {len(rec_log)} recovered records and {n_noauth} still without a named author.</p>
<p>Each recovered record carries its basis, a note and an evidence link, shown on the record page and kept in the data. The three bases are:</p>
<ul><li><strong>Named authors found ({rec_n["person-named"]})</strong>: people named in or on the source as its authors, such as the members listed in a working group's report. When a page credits a host and a guest, the host is recorded as the author and the guest as a contributor.</li><li><strong>Organisation named on the page ({rec_n["organisation-on-page"]})</strong>: the page names no person, so the organisation or project that publishes it is recorded as a collective author, as is usual when citing an organisation's own website. The name is the one the page gives itself.</li><li><strong>Organisation identified from other sources ({rec_n["organisation-other"]})</strong>: the page itself could not be read, so the organisation is recorded from the citation or from other descriptions, and the note says which. These carry less certainty than the others.</li></ul>
<p>Limits: a named author is recorded only when a source states it, and an interview's poster is not assumed to be its interviewer. One page in {len(rec_log) + n_noauth} still has no named author because its site shows no text without scripts and gave no name. Recovered names are written in <code>build/recovered_authors.json</code>; they are applied after item identifiers are made, so no address changed, and a recovery that stops matching its item stops the build.</p>
{table(["Item", "Author recorded", "Basis", "Source checked"], rec_rows)}
<p>{n_noauth} item still has neither a named author nor an editor. It is labelled "No named author" rather than guessed.</p>
<h2 id="types">6. Deciding the type of work</h2>
<p>Type is inferred from the citation's form, because the wiki does not record it:</p>
<ul><li><strong>Book chapter</strong>: a quoted title followed by "In" and a book title.</li><li><strong>Journal article</strong>: a quoted title followed by a venue that contains a number (volume or issue), unless it starts with Report, Working, Policy or White.</li><li><strong>Report or web resource</strong>: a quoted title that fits neither, or an undated item.</li><li><strong>Book or report</strong>: an italic title with no quoted title.</li></ul>
<p>This is a rough guide. A chapter in an edited volume without "In" will be called an article, and a book may be called a report. Treat the type filter as a convenience, not a catalogue record.</p>
{table(["Type", "Items"], kind_rows)}
<h2 id="dupes">7. Deciding that two entries are the same item</h2>
<p>The same work appears in several volumes, often with different wording and with different links (a DOI in one volume, the publisher or an archive page in another). Two entries are the same item when they share any one of: the same DOI (after dashes typed in place of hyphens are corrected); the same web address (ignoring http, www and a trailing slash); or the same title plus year, where the title has at least 25 letters and digits after accents, capitals and punctuation are ignored. Entries that match on none of these stay separate, even if a person would call them the same work.</p>
<p>The title-plus-year rule is the loosest and could, in principle, merge two different works that share a long title and a year. In this edition it joined entries that differed only in how the link was written (for example a DOI against a publisher page); it is the reason the {raw:,} listed entries become {N:,} items and not more.</p>
<p>When entries merge, the item keeps every volume placement, the longest annotation, the longer author list, and the other wordings as "other listings". The first volume's citation is kept as the citation as listed. {n_multi:,} of the {N:,} items appear in more than one volume. This also means the volume counts on this site (which count placements) add up to more than the number of items.</p>
<h2 id="ids">8. Identifiers and addresses</h2>
<p>Each item's identifier is the first ten characters of a SHA-1 hash of its DOI, or, without a DOI, of its first author, year and the first 80 characters of its title (accents and capitals removed). It depends on content, not on position, so adding entries elsewhere does not renumber existing items. Changing a parsing or naming rule can change the identifiers of the affected items, which is why such a change raises the version number. If an item's DOI, first author, year or title changes in the wiki, its identifier will change. Item pages live at <code>items/identifier.html</code>.</p>
<h2 id="topics">9. Deciding topics</h2>
<p>The wiki gives chapter and section headings but no keywords, so topics come from a fixed list of {len(DS['lexicon'])} topics, each defined by word patterns written into the program (listed below). An item has a topic when any of the topic's patterns appears in its title or annotation, ignoring capitals. {n_topic:,} items ({round(100 * n_topic / N)} percent) have at least one topic; an item can have several.</p>
<p>A topic tag means "this vocabulary appears in the text". It is not a judgement of what the work is mainly about, and it can overreach: "skills" or "training" tag a Training topic for any annotation that uses the word, and short patterns such as AI and DH are matched as whole words only. Items with no annotation cannot receive topics except from the title. The chapter and section path (searchable as ordinary words) is the editors' own classification and is more reliable for subject than these tags.</p>
{table(["Topic", "Patterns (any one matches)"], lex_rows)}
<p>The patterns are in <code>build/parse.py</code> and the same list ships in <code>data/items.json</code>. Changing them and rebuilding changes every topic count.</p>
<h2 id="origin">10. Annotation origin</h2>
<p>Each volume's introduction has a table explaining the marker symbols that prefix entries (for example, annotations carried over from an earlier bibliography, or written by a named team member). The build reads that table for each volume rather than assuming one meaning, attaches each entry's markers to its placement, and exposes the table's wording as the "Annotation source" filter. {n_src:,} items carry at least one marker. A symbol means different things in different volumes, so the filter shows the full wording, not the symbol. Symbols are recognised when they are punctuation, Greek letters, or keys of the volume's own legend table. Volumes without a legend table give no origin information.</p>
{table(["Volume", "Entries parsed", "Marker symbols in legend"], vol_rows)}
<h2 id="search">11. How search and filters decide</h2>
<p>Explore and the Search page use the same engine, described on the <a href="about.html#engine">About page</a>. The choices made for this collection are:</p>
<ul>
<li>The text indexed is each item page's title, authors, venue, annotation, topics, and chapter and section names. The page header, navigation, footer and citation box are left out, and a word in the item title counts three times as much as elsewhere.</li>
<li>Filters come from labels written into each item page: Volume, Topic and Type (choose any), Has annotation (yes or no), Year (a range), and Author and Editor (type a name). Within one filter, an item needs to match any choice; across filters it needs to match all. The author and editor filters keep the separation described in section 5.</li>
<li>Items are ranked by the engine's relevance score. Items with equal scores sort by author, then year. With no search words, Explore lists items by author A to Z.</li>
</ul>
<h3 id="exploredraws">What Explore adds</h3>
<ul>
<li>Explore receives the list of matching items from the engine and draws the cards and charts itself.</li>
<li>The counts in brackets beside each Volume, Topic and Type option are the number of items in the current results that have that value; they are not predictions of what a further filter would give.</li>
<li>Selecting a bar, column or table cell in a chart sets the matching filter (a year column sets the Year range, an author bar sets the Author filter) and runs the search again. The filters on the left always show what is applied.</li>
<li>Snippets on the cards are the engine's excerpts with the matched words marked; with filters only, they are the start of the annotation.</li>
<li>If the search index is missing, or the page is opened as a saved file (browsers refuse to read the index that way), Explore says so and still shows every item and the charts, without filtering.</li>
<li>Both pages keep your search in the address after a question mark (for example <code>index.html?q=repositories&amp;Volume=Policy</code>), which is how the engine records and restores a search. This is the only place on the site where query strings are used; every record and volume address is plain.</li>
</ul>
<h2 id="charts">12. What the charts count</h2>
<ul><li><strong>Items by year</strong>: one column per year from 1990 and one for everything earlier. Items with no year ({n_nodate} in the whole collection) are left out of the columns, and the chart says how many were left out.</li><li><strong>Items by volume</strong>: placements; an item in two volumes counts in both.</li><li><strong>Most frequent authors</strong>: the twelve names that appear on most items in the current results.</li><li><strong>Topics across volumes</strong>: items per topic and volume (section 9), shaded in proportion to the largest cell.</li><li><strong>Shared items</strong>: items present in both of two volumes; the diagonal is each volume's total.</li></ul>
<p>All charts describe the current search and filters, not the whole collection. The bibliography reflects what the editors chose to annotate, so counts describe this corpus, not the research literature at large. A rise in recent years reflects when the volumes were compiled as well as publishing trends.</p>
<h2 id="checks">13. Checks and what they cannot show</h2>
<p>The build compares each volume's parsed entries with the lines in its alphabetical reference list (where the volume has one) and reports the counts on the <a href="about.html">About page</a>. It lists entries without annotations, DOIs of unusual form, entries with no title, and lines it could not parse. The build stops if a new kind of irregularity appears that has not been reviewed.</p>
<h3>Corrections</h3><p>Where the source itself contains a typing error that no rule can repair, the build applies a named correction, recorded in <code>build/corrections.json</code> with its reason and applied before duplicates are merged. A correction that stops matching anything stops the build. {len(DS["meta"]["corrections"])} corrections are in force:</p>{table(["Entry (fragment of the citation)", "Reason", "Applied"], corr_rows)}<p>These checks catch gross failures. They cannot show that every author name was split correctly, that each type or topic is right, or that two entries with different wording are really different works. The parsed count and the reference-list count differ in several volumes because lists can be partial or repeat entries listed in several sections. {n_ann:,} of {N:,} items have an annotation; the rest are unannotated in the source and are labelled so.</p>
<h2 id="limits">14. Limits and cautions</h2>
<ul><li>The data are a snapshot of a wiki that editors continue to improve. Check the volume page for the revision used.</li><li>{n_url:,} items carry a link ({n_doi:,} with a DOI). Links were not tested and may have moved.</li><li>Type, topics and author splitting are program guesses (sections 5, 6 and 9) and are described here so that you can discount them.</li><li>The corpus is English-language Wikibooks content; French editions are not included, which narrows the coverage of the multilingual theme.</li><li>No record is edited by hand except through the listed corrections (section 13) and the recovered authors (section 5). If a record is wrong, correct the wiki, the rules or the corrections file, then rebuild.</li></ul>
<h2 id="repro">15. Reproducing and changing the method</h2>
<p>The snapshot, the program and the rules above are in the project repository. <code>python3 build/build.py</code> rebuilds this site from the snapshot with no network access; adding <code>--refresh</code> fetches the wiki again. The files <code>build/fetch.py</code> (source retrieval), <code>build/parse.py</code> (sections 3 to 10) and <code>build/render.py</code> (this site) hold the rules. When a rule changes, the maintainers raise the version number in <code>build/render.py</code>, and every page then shows it.</p>
<h2 id="coauthorship">16. Co-authorship</h2>
<p>The <a href="coauthorship.html">Co-authorship</a> page draws the authors of the same item as a network that responds to filters. It follows the Endings Principles in these ways.</p>
<ul>
<li>Data: the ties and the authors are published as plain CSV (<a href="data/coauthorship-ties.csv">ties</a>, <a href="data/coauthorship-authors.csv">authors</a>) beside the full records, so the network can be rebuilt in any other tool without this site.</li>
<li>Documentation: this section states every rule that turns records into the picture, and the limits of each.</li>
<li>Processes: the network is computed by a short, readable script (<code>build/templates/coauthor.js</code>) with no libraries, no network calls and no stored state. The layout starts from a pseudo-random arrangement seeded by the first author's name, so the same filters always give the same picture.</li>
<li>Products: the page is plain HTML with an embedded data block. Without JavaScript it falls back to tables describing the whole collection. The network is SVG with text names; every circle can be reached and activated from the keyboard, and the tables repeat what the picture shows. Colour carries no information.</li>
<li>Distribution: the page needs no server and works from a saved copy. The filter state is kept in the page address after a question mark, so a view can be bookmarked or shared.</li>
</ul>
<h3>What counts as a tie</h3>
<p>Only authors are tied. Editors, volume editors and contributors (section 5) are left out, because editing a book or being credited as a collaborator is a different relation from writing together. Every pair of authors named on the same item receives a tie, so an item with <em>n</em> authors yields n(n-1)/2 ties. Each tie records the items that produced it. In the whole collection, {co_multi:,} of the {co_withauth:,} items with a named author have more than one author, and they yield {len(co_ties):,} ties among {len(co_gid):,} authors. The authors form {len(co_groups)} connected groups (a group is a set of authors linked by chains of ties); {co_pairs} of them are single pairs, and the largest has {len(co_groups[0])} authors.</p>
<h3>What the filters do</h3>
<p>The filters select items first, and the network is then recomputed from the authors of the selected items alone. Within one filter an item needs to match any choice; across filters it needs to match all, as on Explore. An item with no year is dropped when a year limit is set. Two further settings shape the drawing without changing which items are selected: the minimum number of shared items for a tie to be drawn (so that one-off collaborations can be set aside to show repeated ones), and the smallest group to draw. Raising the tie threshold can split a group into smaller groups, and authors left with no tie disappear from the picture while remaining in the counts of authors. Choosing an author with "Find an author" selects the circle and, if asked, shows only that author's group.</p>
<h3>What the picture shows</h3>
<ul>
<li>Circle area grows with the number of selected items an author has; line thickness grows with the number of items two authors share (up to five).</li>
<li>Each connected group is laid out by itself with a force-directed method (every circle repels every other, every tie pulls its two ends together) and the groups are then packed in rows, largest first. Distance across the picture has no meaning. Position inside a group shows structure only: authors with many ties sit in the middle, authors with few at the edge.</li>
<li>Names are drawn beside a circle only for authors with three or more items or seven or more co-authors, and for the selected author and that author's co-authors; a name is left out where it would overlap another. Every circle carries its name in the tooltip and the accessible label.</li>
<li>The tables rank authors by items written with at least one other author, then by number of distinct co-authors; pairs by shared items; and groups by size.</li>
</ul>
<h3>Limits</h3>
<ul>
<li>A long author list produces a dense cluster of ties between people who may never have worked together in pairs. The largest groups in this collection are driven by a few items with many authors. Raising the minimum shared items to two or three removes most such clusters.</li>
<li>The ties describe the annotated bibliography, which lists what the volume editors chose to annotate. They describe collaboration in this corpus, not in the research literature at large.</li>
<li>Names are matched as written after the reviewed variants of section 5 are applied. Two people with the same name become one author, and one person written in two ways not yet in the table becomes two, which splits or joins groups wrongly. The name-variant table is the place to correct this.</li>
<li>Organisations that the parser could not tell from people (section 5) appear as authors; an organisation listed beside people is tied to them like any other author.</li>
<li>{co_withauth:,} items is the base for all shares on the page; the {N - co_withauth} items with no named author are not counted.</li>
</ul>
<h2 id="generated">17. Generated descriptive notes</h2>
<p>{n_noann} items have no annotation in the source volumes. The parser reports this as the irregularity "entries-without-annotation" on the <a href="about.html">About page</a>, and the report stays, because the source text is unchanged. {len(gn)} of those items now carry a short descriptive note that a language model wrote for this edition. The other {n_noann - len(gn)} have none.</p>
<h3>Why the gap exists</h3>
<p>In the Knowledge Mobilization in the Humanities volume the editors often list several citations in a row and then write one annotation, which is about the last citation of the run. The entries before it have no annotation text anywhere in the wiki, and no other volume supplies one. The parser reads this layout correctly; the text does not exist to be recovered.</p>
<h3>What was done</h3>
<ul>
<li>Model: {e(", ".join(gn_models) or "none")}. Notes were written between {e(gn_first.replace("T", " ").replace("Z", " UTC"))} and {e(gn_last.replace("T", " ").replace("Z", " UTC"))}; the time recorded for each is in the table below and in the data (it was taken when its batch was written, so it can trail the reading by minutes).</li>
<li>Procedure: the notes were written by Claude Code subagents, each given 15 items. For each item the model was asked to open the cited work's own page and write one or two sentences (at most 60 words) of neutral prose that paraphrase what that page says the work is and addresses. Where the page could not be read, or the entry has no address, the note may state only what the citation shows (the title, the kind of work and the publisher or venue) and uses hedged wording such as "the title indicates". Those notes are marked "citation-only"; {gn_basis["citation-only"]} are of that kind and {gn_basis["page-read"]} are "page-read".</li>
<li>Instructions found on any page read were treated as data and ignored.</li>
<li>Each note is stored with its basis, the address read, the model and the time in <code>build/generated_notes.json</code>, and the parser applies it after item identifiers are made. A note whose item no longer exists, or whose item has since gained a source annotation, stops the build.</li>
</ul>
<h3>How the notes are shown</h3>
<p>A generated note never replaces or merges into the source annotation, which stays empty; the "Has annotation" filter still means "annotated in the source". On the item page, the volume pages and Explore, the note appears under its own heading or label with the model, date, time and basis. The search index leaves the notes out, so a search matches only text that the volume authors wrote. In the data the note is the <code>generated_note</code> field of the item and the <code>generated_note_*</code> columns of items.csv.</p>
<h3>Limits</h3>
<ul>
<li>A language model can misdescribe a work. A "page-read" note rests on the abstract or description on the work's page, which may itself be partial; a "citation-only" note says no more than the citation does. Neither is a reading of the work.</li>
<li>The notes are not the work of the Open Scholarship Press authors and should not be cited as their annotations. Cite the work itself.</li>
<li>The notes were written once for this edition. A rebuild reuses them as stored and does not write them again.</li>
</ul>
{table(["Item", "Basis", "Generated"], gn_rows)}
</div>"""
    with open(os.path.join(SITE, "methodology.html"), "w", encoding="utf-8") as f:
        f.write(page(f"Methodology · {TITLE}", body, 0, "methodology", scripts=HERE_JS))


def main():
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    write_data()
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_page())
    volume_pages()
    item_pages()
    search_page()
    coauthor_page()
    about_page()
    methodology_page()
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    print("site built:", N, "items")


if __name__ == "__main__":
    main()
