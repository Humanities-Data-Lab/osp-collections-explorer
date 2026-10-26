"""Render the static site from build/dataset.json. Stdlib only."""
import csv
import html
import json
import os
import re
import shutil
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "site")
VERSION = "0.1.0"
TITLE = "Open Scholarship Press Collections Explorer"

e = html.escape


def read(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return f.read()


CSS = read("templates/style.css")
JS = read("templates/app.js")

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
    ("open access", "All words must appear somewhere in the title, authors, source, sections or annotation."),
    ('"digital commons"', "Exact phrase."),
    ("repository OR repositories", "Either term. OR joins the terms next to it."),
    ("-facebook", "Exclude items that contain the word."),
    ("author:siemens", "Search one field. Fields: author, editor, title, in (journal or book), note, section, topic, volume, type, doi. Author and editor are separate fields."),
    ("year:2015..2020", "Year range. Also year:2018, year:>2010 and year:<2000."),
    ("author:colin-arce", "Accents and capitals are ignored: Colín-Arce matches colin-arce."),
]


def rel(depth):
    return "../" * depth


def wiki_url(title):
    return "https://en.wikibooks.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="/:_(),'")


def syntax_table():
    rows = "".join(f"<tr><td><code>{e(q)}</code></td><td>{e(d)}</td></tr>" for q, d in SYNTAX)
    return f'<table><thead><tr><th scope="col">Type</th><th scope="col">It finds</th></tr></thead><tbody>{rows}</tbody></table>'


def page(title, body, depth=0, current="", description="", extra_head="", scripts=""):
    r = rel(depth)
    nav = [("index.html", "Explore", "explore"), ("volumes/index.html", "Volumes", "volumes"),
           ("methodology.html", "Methodology", "methodology"), ("about.html", "About, data and citation", "about")]
    cur = ' aria-current="page"'
    links = "".join(
        f'<li><a href="{r}{h}"{cur if c == current else ""}>{e(t)}</a></li>' for h, t, c in nav)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(title)}</title>
<meta name="description" content="{e(description or 'Search and visualize the annotated bibliographies of the Open Scholarship Press Collections.')}">
<meta name="generator" content="osp-explorer {VERSION}">
<style>{CSS}</style>{extra_head}
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


HERE_JS = '<script>document.querySelectorAll(".here").forEach(function(n){n.textContent=location.href.split("#")[0];});</script>'


def cite_block(depth, label, ident=""):
    return (f'<div class="cite"><h2 style="font-size:1.05rem">How to cite this page</h2>'
            f'<p>{TITLE}, version {VERSION}, edition {EDITION}. {e(label)}{(" Record " + ident + ".") if ident else ""} '
            f'Address: <span class="here">{"[address of this page]"}</span></p></div>')


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
        w.writerow(["id", "authors", "editors", "volume_editors", "contributors", "year", "title", "container", "type", "url", "doi", "volumes", "chapters", "sections", "topics", "annotation_source", "annotation", "citation_as_listed"])
        for it in ITEMS:
            w.writerow([it["id"], "; ".join(it["authors"]), "; ".join(it["editors"]), "; ".join(it["container_editors"]), "; ".join(it["contributors"]), it["year"] or "", it["title"], it["container"], it["kind"], it["url"], it["doi"],
                        "; ".join(it["volumes"]), "; ".join(it["chapters"]), "; ".join(it["sections"]), "; ".join(it["topics"]),
                        "; ".join(it["annotation_source"]), it["annotation"], it["citation"]])
    with open(os.path.join(SITE, "data", "validation.json"), "w", encoding="utf-8") as f:
        json.dump(VAL, f, ensure_ascii=False, indent=1)
    readme = f"""# Data model, {TITLE}

Version {VERSION}, edition {EDITION}. Licence of the item records and annotations: {LIC['text']} ({LIC['url']}).
Source: https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections

Files: items.json (full records, volumes, lexicon), items.csv (flat table), validation.json (parser report).

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
        slim.append({k: it[k] for k in ("id", "authors", "editors", "container_editors", "contributors", "year", "title", "container", "kind", "url", "doi", "citation", "annotation",
                                         "topics", "annotation_source", "volumes", "chapters", "sections")})
    data = {"items": slim, "volumes": [{"slug": v["slug"], "title": v["title"], "entries": v["entries"]} for v in VOLS], "topics": TOPICS}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pre = "".join(f'<li><a href="items/{it["id"]}.html">{e(short_cit(it))}</a></li>' for it in ITEMS)
    vol_links = "".join(f'<li><a href="volumes/{v["slug"]}.html">{e(v["title"])}</a> ({v["entries"]} entries)</li>' for v in VOLS)
    body = f'''<h1>Explore the Open Scholarship Press Collections</h1>
<p class="lede">Search, filter and chart {N:,} annotated sources on open social scholarship, drawn from {len(VOLS)} volumes of annotated bibliographies. Annotations are searchable; the articles themselves stay at their original addresses.</p>
<div class="nojs" role="note"><p><strong>JavaScript is off or unavailable.</strong> Search and filters need JavaScript. Every volume and every item has its own page below, and the complete list works as plain links.</p><ul>{vol_links}</ul></div>
<form id="search-form" class="searchbar jsonly" role="search" aria-label="Search items">
<label for="q">Search authors, titles, annotations and sections</label>
<input type="search" id="q" name="q" autocomplete="off" spellcheck="false" aria-describedby="qhelp">
<button type="submit">Search</button>
</form>
<details class="syntax jsonly"><summary id="qhelp">Query syntax</summary>{syntax_table()}</details>
<div class="layout jsonly">
<aside class="filters" aria-label="Filters"><details id="filterbox"><summary>Filters</summary><div id="facets"></div></details></aside>
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
<div><label for="sort">Sort by </label><select id="sort"><option value="relevance" id="relevance-opt">Relevance</option><option value="author">Author</option><option value="year-desc">Year, newest first</option><option value="year-asc">Year, oldest first</option><option value="title">Title</option></select>
<button type="button" class="secondary" id="reset" hidden>Reset all</button></div></div>
<ul class="chips" id="chips" aria-label="Active filters"></ul>
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
        body = (f'<p><a href="../index.html">← Explore all items</a></p><h1>{e(it["title"] or it["citation"])}</h1>'
                f'<p class="lede">{e(short_cit(it))}</p><dl class="facts">{dl}</dl>'
                f'<h2>Annotation</h2><div class="prose">{ann}</div>'
                f'<h2>Where it appears</h2><ul class="prose">{places}</ul>{variants}'
                f'<h2>Citation as listed</h2><p class="prose">{e(it["citation"])}</p>'
                f'{cite_block(1, "Record: " + (it["title"] or "untitled") + ".", it["id"])}')
        with open(os.path.join(SITE, "items", it["id"] + ".html"), "w", encoding="utf-8") as f:
            f.write(page(f'{it["title"] or "Record"} · {TITLE}', body, 1, "", scripts=HERE_JS))


# ---------- about ----------
def about_page():
    anomalies = VAL["anomalies"]
    arows = "".join(f'<tr><td>{e(a["type"])}</td><td>{e(a.get("volume", a.get("page", "")))}</td><td>{e(str(a.get("text", a.get("count", ""))))[:140]}</td></tr>' for a in anomalies)
    vrows = "".join(f'<tr><th scope="row">{e(v["title"])}</th><td>{v["entries"]}</td><td>{VAL["per_volume"][v["slug"]]["reference_lines_in_list_page"] or "none"}</td><td>{e(v["latest_revision"][:10])}</td></tr>' for v in VOLS)
    endings = [
        ("1 Data", "Items are plain JSON and CSV (open formats) with a documented data model; the programs that read and parse the source text are in the build folder under version control."),
        ("2 Documentation", "The data model, lexicon and limitations are in data/README.md. Licence and attribution appear on every page."),
        ("3 Processing", "The build validates the parse against each volume's reference list and stops on any anomaly not previously reviewed."),
        ("4.1 to 4.3", "Static HTML, CSS and JavaScript only. No server software, frameworks, fonts, analytics or services."),
        ("4.4", "Every volume and item has its own address. Search and filter state lives in the URL fragment (after #), never in a query string."),
        ("4.5, 4.6", "The full data ship with the site, and the main page embeds them, so it works from a saved file."),
        ("4.7", "Without JavaScript, the main page, volume pages and item pages remain readable and linked."),
        ("5.1 to 5.5", "Editions are built on a schedule chosen by the maintainers, carry a version and edition date on every page, include citation instructions, and keep item addresses stable (identifiers derive from the item's content, not its position)."),
    ]
    erows = "".join(f'<tr><th scope="row">{e(a)}</th><td>{e(b)}</td></tr>' for a, b in endings)
    body = f'''<h1>About, data and citation</h1>
<div class="prose">
<p>This explorer indexes the annotated entries of seven volumes of the Open Scholarship Press Collections. It reads the public wiki text, keeps authors, years, venues, section headings and annotations, and links to each source rather than copying it. Observatory volumes, French editions and the Curated Volumes are outside this first edition.</p>
<h2>Using the search</h2>{syntax_table()}
<p>Filters combine: choices inside one group widen the result (any selected volume), and choices across groups narrow it. The address in your browser records the current search so you can share it.</p>
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
<h2>Source irregularities found</h2><p>These are reported, not repaired.</p></div>
<table class="data"><thead><tr><th scope="col">Kind</th><th scope="col">Where</th><th scope="col">Detail</th></tr></thead><tbody>{arows}</tbody></table>
<div class="prose"><h2>Endings principles in practice</h2></div>
<table class="data"><thead><tr><th scope="col">Principle</th><th scope="col">How this site meets it</th></tr></thead><tbody>{erows}</tbody></table>
<div class="prose"><h2>Accessibility</h2><p>The pages use landmarks, labelled controls, keyboard-operable charts built from buttons and tables, visible focus, light and dark themes that follow your system, reduced-motion support and text that scales. Charts present their numbers as text and in tables, and no meaning rests on colour alone. Please report barriers to the maintainers.</p></div>'''
    body = body.replace("<table", '<div class="tablewrap" tabindex="0" role="region" aria-label="Scrollable table"><table').replace("</table>", "</table></div>")
    with open(os.path.join(SITE, "about.html"), "w", encoding="utf-8") as f:
        f.write(page(f"About, data and citation · {TITLE}", body, 0, "about", scripts=HERE_JS))


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
    n_ed = sum(1 for it in ITEMS if it["editors"])
    n_ce = sum(1 for it in ITEMS if it["container_editors"])
    n_contrib = sum(1 for it in ITEMS if it["contributors"])
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
<li><a href="#checks">13. Checks and what they cannot show</a></li><li><a href="#limits">14. Limits and cautions</a></li><li><a href="#repro">15. Reproducing and changing the method</a></li></ul></nav>
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
<p>The remaining author text is split at commas and "and". If the first name is written "Last, First", it is turned into "First Last"; later names are taken as written. A name list is treated as an organisation, and left whole, when the second piece is long (more than three words) or the first piece contains a bracket or words such as "of", "for" or "the". "et al." is dropped. This is a heuristic: it handles most personal names correctly, but organisations with commas, double-barrelled names and unusual titles can be split wrongly. The author chart counts authors only, each name once per item; two spellings of one person count as two people. The search fields <code>author:</code> and <code>editor:</code> look in the two groups separately, and a search with no field looks in all four.</p>
<p>After parsing, the build tests every name. It stops if a name still contains a role word (ed, eds, editor, translator), a marker symbol, a Greek letter, a year, a quotation mark or a web address, so that such defects cannot pass unnoticed.</p>
<p>{n_noauth} items have neither a named author nor editor because the source lists a website or document under its title alone. They are labelled "No named author" rather than guessed.</p>
<h2 id="types">6. Deciding the type of work</h2>
<p>Type is inferred from the citation's form, because the wiki does not record it:</p>
<ul><li><strong>Book chapter</strong>: a quoted title followed by "In" and a book title.</li><li><strong>Journal article</strong>: a quoted title followed by a venue that contains a number (volume or issue), unless it starts with Report, Working, Policy or White.</li><li><strong>Report or web resource</strong>: a quoted title that fits neither, or an undated item.</li><li><strong>Book or report</strong>: an italic title with no quoted title.</li></ul>
<p>This is a rough guide. A chapter in an edited volume without "In" will be called an article, and a book may be called a report. Treat the type filter as a convenience, not a catalogue record.</p>
{table(["Type", "Items"], kind_rows)}
<h2 id="dupes">7. Deciding that two entries are the same item</h2>
<p>The same work appears in several volumes, often with different wording. Two entries are the same item when they share, in this order of preference: the same DOI; otherwise the same web address (ignoring http, www and a trailing slash); otherwise the same title (letters and digits only) plus year. Entries that do not match on any of these stay separate, even if a person would call them the same work.</p>
<p>When entries merge, the item keeps every volume placement, the longest annotation, the longer author list, and the other wordings as "other listings". The first volume's citation is kept as the citation as listed. {n_multi:,} of the {N:,} items appear in more than one volume. This also means the volume counts on this site (which count placements) add up to more than the number of items.</p>
<h2 id="ids">8. Identifiers and addresses</h2>
<p>Each item's identifier is the first ten characters of a SHA-1 hash of its DOI, or, without a DOI, of its first author, year and the first 80 characters of its title (accents and capitals removed). It depends on content, not on position, so adding entries elsewhere does not renumber existing items. If an item's DOI, first author, year or title changes in the wiki, its identifier will change. Item pages live at <code>items/identifier.html</code>.</p>
<h2 id="topics">9. Deciding topics</h2>
<p>The wiki gives chapter and section headings but no keywords, so topics come from a fixed list of {len(DS['lexicon'])} topics, each defined by word patterns written into the program (listed below). An item has a topic when any of the topic's patterns appears in its title or annotation, ignoring capitals. {n_topic:,} items ({round(100 * n_topic / N)} percent) have at least one topic; an item can have several.</p>
<p>A topic tag means "this vocabulary appears in the text". It is not a judgement of what the work is mainly about, and it can overreach: "skills" or "training" tag a Training topic for any annotation that uses the word, and short patterns such as AI and DH are matched as whole words only. Items with no annotation cannot receive topics except from the title. The chapter and section path (searchable with <code>section:</code>) is the editors' own classification and is more reliable for subject than these tags.</p>
{table(["Topic", "Patterns (any one matches)"], lex_rows)}
<p>The patterns are in <code>build/parse.py</code> and the same list ships in <code>data/items.json</code>. Changing them and rebuilding changes every topic count.</p>
<h2 id="origin">10. Annotation origin</h2>
<p>Each volume's introduction has a table explaining the marker symbols that prefix entries (for example, annotations carried over from an earlier bibliography, or written by a named team member). The build reads that table for each volume rather than assuming one meaning, attaches each entry's markers to its placement, and exposes the table's wording as the "Annotation source" filter. {n_src:,} items carry at least one marker. A symbol means different things in different volumes, so the filter shows the full wording, not the symbol. Symbols are recognised when they are punctuation, Greek letters, or keys of the volume's own legend table. Volumes without a legend table give no origin information.</p>
{table(["Volume", "Entries parsed", "Marker symbols in legend"], vol_rows)}
<h2 id="search">11. How search and filters decide</h2>
<ul><li>All matching is done on text with accents removed and capitals ignored, and checks whether the text contains the typed letters, so <code>commons</code> also finds "commonsense".</li><li>Words typed together must all match; <code>OR</code> lets either neighbouring term match; a leading minus excludes.</li><li>A search with no field looks in title, authors, venue, annotation, topics, and chapter and section names. A field prefix looks only in that field.</li><li>Relevance score: each occurrence in the title counts 5, in the authors 4, in the section path 2, and in the annotation 1 (up to 5). Items with equal scores sort by author, then year. Without a search, the default order is author A to Z.</li><li>Within one filter group (for example two volumes) an item needs to match any selection; across groups it needs to match every group. The counts beside each option show what the result would be if that option alone were added to the other current filters.</li><li>Searching and filtering happen in your browser; nothing is sent anywhere.</li></ul>
<h2 id="charts">12. What the charts count</h2>
<ul><li><strong>Items by year</strong>: one column per year from 1990 and one for everything earlier. Items with no year ({n_nodate} in the whole collection) are left out of the columns, and the chart says how many were left out.</li><li><strong>Items by volume</strong>: placements; an item in two volumes counts in both.</li><li><strong>Most frequent authors</strong>: the twelve names that appear on most items in the current results.</li><li><strong>Topics across volumes</strong>: items per topic and volume (section 9), shaded in proportion to the largest cell.</li><li><strong>Shared items</strong>: items present in both of two volumes; the diagonal is each volume's total.</li></ul>
<p>All charts describe the current search and filters, not the whole collection. The bibliography reflects what the editors chose to annotate, so counts describe this corpus, not the research literature at large. A rise in recent years reflects when the volumes were compiled as well as publishing trends.</p>
<h2 id="checks">13. Checks and what they cannot show</h2>
<p>The build compares each volume's parsed entries with the lines in its alphabetical reference list (where the volume has one) and reports the counts on the <a href="about.html">About page</a>. It lists entries without annotations, DOIs of unusual form, entries with no title, and lines it could not parse. The build stops if a new kind of irregularity appears that has not been reviewed.</p>
<h3>Corrections</h3><p>Where the source itself contains a typing error that no rule can repair, the build applies a named correction, recorded in <code>build/corrections.json</code> with its reason and applied before duplicates are merged. A correction that stops matching anything stops the build. {len(DS["meta"]["corrections"])} corrections are in force:</p>{table(["Entry (fragment of the citation)", "Reason", "Applied"], corr_rows)}<p>These checks catch gross failures. They cannot show that every author name was split correctly, that each type or topic is right, or that two entries with different wording are really different works. The parsed count and the reference-list count differ in several volumes because lists can be partial or repeat entries listed in several sections. {n_ann:,} of {N:,} items have an annotation; the rest are unannotated in the source and are labelled so.</p>
<h2 id="limits">14. Limits and cautions</h2>
<ul><li>The data are a snapshot of a wiki that editors continue to improve. Check the volume page for the revision used.</li><li>{n_url:,} items carry a link ({n_doi:,} with a DOI). Links were not tested and may have moved.</li><li>Type, topics and author splitting are program guesses (sections 5, 6 and 9) and are described here so that you can discount them.</li><li>The corpus is English-language Wikibooks content; French editions are not included, which narrows the coverage of the multilingual theme.</li><li>No record is edited by hand except through the listed corrections (section 13). If a record is wrong, correct the wiki, the rules or the corrections file, then rebuild.</li></ul>
<h2 id="repro">15. Reproducing and changing the method</h2>
<p>The snapshot, the program and the rules above are in the project repository. <code>python3 build/build.py</code> rebuilds this site from the snapshot with no network access; adding <code>--refresh</code> fetches the wiki again. The files <code>build/fetch.py</code> (source retrieval), <code>build/parse.py</code> (sections 3 to 10) and <code>build/render.py</code> (this site) hold the rules. When a rule changes, the maintainers raise the version number in <code>build/render.py</code>, and every page then shows it.</p>
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
    about_page()
    methodology_page()
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    print("site built:", N, "items")


if __name__ == "__main__":
    main()
