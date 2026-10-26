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
    ("author:siemens", "Search one field. Fields: author, title, in (journal or book), note, section, topic, volume, type, doi."),
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
    nav = [("index.html", "Explore", "explore"), ("volumes/index.html", "Volumes", "volumes"), ("about.html", "About, data and citation", "about")]
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
    a = ", ".join(it["authors"][:3]) + (" et al." if len(it["authors"]) > 3 else "")
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
        w.writerow(["id", "authors", "year", "title", "container", "type", "url", "doi", "volumes", "chapters", "sections", "topics", "annotation_source", "annotation", "citation_as_listed"])
        for it in ITEMS:
            w.writerow([it["id"], "; ".join(it["authors"]), it["year"] or "", it["title"], it["container"], it["kind"], it["url"], it["doi"],
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
- authors: list of display names (First Last), split from the citation by a heuristic. Organisations stay whole.
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

Author splitting, item type and topics are heuristic. The validation report lists source irregularities (for example a DOI written with a slash in place of a full stop). Source irregularities are reported, not repaired.
"""
    with open(os.path.join(SITE, "data", "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)


# ---------- index ----------
def index_page():
    slim = []
    for it in ITEMS:
        slim.append({k: it[k] for k in ("id", "authors", "year", "title", "container", "kind", "url", "doi", "citation", "annotation",
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
            for it in sorted(its, key=lambda x: ((x["authors"] or [""])[0].lower(), x["year"] or 0)):
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
        facts = [("Authors", e("; ".join(it["authors"])) or "No named author in the source"), ("Year", e(it["year_label"])), ("Type", e(it["kind"]))]
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
        ("1 Data", "Items are plain JSON and CSV (open formats) with a documented data model; the scraper and parser are in the build folder under version control."),
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
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    print("site built:", N, "items")


if __name__ == "__main__":
    main()
