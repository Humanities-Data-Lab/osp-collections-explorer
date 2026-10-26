"""Parse fetched wikitext into a deduplicated dataset of annotated entries.

Stdlib only. Reads build/raw/pages.json, writes build/dataset.json and
build/validation.json. Anomalies are reported, never silently repaired.
"""
import hashlib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_CHAPTERS = re.compile(r"/(Introduction|Abstract|Executive Summary)$")
LIST_PAGES = re.compile(r"/(Complete Alphabetical List of References|Alphabetical List of References|References)$")
YEAR = re.compile(r"\b((?:1[5-9]|20)\d\d[a-z]?|n\.d\.)(?=[.,)\s])")
BOLD = re.compile(r"^'''(.+?)'''[.\s]*$")
URL = re.compile(r"https?://[^\s<>\"]+")
DOI = re.compile(r"10\.\d{4,9}/[^\s<>\"]+")

# Controlled topic lexicon applied to annotation text. Matches are exposed as
# the "topics" facet; the terms are documented in the site data model.
LEXICON = {
    "Open access": [r"open access", r"\bOA\b", r"green oa", r"gold oa", r"diamond"],
    "Open data": [r"open data", r"research data management", r"\bRDM\b", r"FAIR principles"],
    "Open education": [r"open educational", r"\bOER", r"open education", r"open pedagogy"],
    "Digital humanities": [r"digital humanities", r"\bDH\b"],
    "Scholarly communication": [r"scholarly communication", r"scholarly publishing", r"academic publishing"],
    "Peer review": [r"peer review"],
    "Libraries and repositories": [r"librar", r"repositor"],
    "Policy and funders": [r"\bpolicy\b", r"\bpolicies\b", r"funder", r"funding agenc", r"mandate"],
    "Infrastructure": [r"infrastructure"],
    "Metrics and evaluation": [r"bibliometric", r"altmetric", r"impact factor", r"research evaluation", r"tenure"],
    "Copyright and licensing": [r"copyright", r"creative commons", r"licen[cs]"],
    "Community engagement": [r"community engagement", r"public engagement", r"community-based", r"citizen"],
    "Knowledge mobilization": [r"knowledge mobili[sz]ation", r"knowledge translation"],
    "Indigenous knowledges": [r"indigenous", r"first nations", r"decoloni"],
    "Equity and diversity": [r"equity", r"diversity", r"inclusion", r"epistemic", r"social justice", r"marginali[sz]"],
    "Multilingualism": [r"multilingual", r"bibliodiversity", r"lingua franca"],
    "Platforms and social media": [r"platform", r"social media", r"academia\.edu", r"researchgate"],
    "Training and pedagogy": [r"training", r"pedagog", r"curricul", r"graduate student", r"skills"],
    "Collaboration": [r"collaborat", r"partnership", r"co-creat", r"co-inquiry"],
    "Social knowledge creation": [r"social knowledge creation"],
    "Artificial intelligence": [r"artificial intelligence", r"machine learning", r"generative ai", r"\bAI\b"],
    "Open source and tools": [r"open source", r"open-source", r"software"],
    "Sustainability and labour": [r"sustainab", r"labou?r", r"care work"],
    "Governance and regulation": [r"governance", r"regulat", r"antitrust", r"monopol"],
}
LEXICON_RE = {k: re.compile("|".join(v), re.I) for k, v in LEXICON.items()}


def fold(s):
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def clean_markup(s):
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"</?(div|span|big|small|br|p)[^>]*>", " ", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[(https?://[^\s\]]+)\s+([^\]]*)\]", r"\2 \1", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"&nbsp;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_legend(text):
    """Marker table in an Introduction page: '| + || meaning'."""
    legend = {}
    for m in re.finditer(r"^\|\s*(\S{1,3})\s*\|\|\s*(.+)$", text, flags=re.M):
        legend[m.group(1)] = clean_markup(m.group(2))
    return legend


MARK_STOP = set("“”‘’\"'([")


def is_marker_token(tok, legend):
    """A marker token is made only of symbols, Greek letters or legend keys (glued tokens such as 'Φ+' allowed)."""
    for ch in tok:
        if ch in MARK_STOP:
            return False
        if ch in legend or not ch.isalnum() or "\u0370" <= ch <= "\u03ff":
            continue
        return False
    return True


def split_citation(raw, legend):
    """Return (markers, citation_text). Markers are the leading symbol tokens."""
    raw = raw.strip()
    markers = []
    while True:
        m = re.match(r"^(\S+)\s+(?=\S)", raw)
        if not m or not is_marker_token(m.group(1), legend):
            break
        markers += list(m.group(1))
        raw = raw[m.end():]
    return markers, raw.strip()


def parse_names(author_str, inverted=True):
    """Heuristic author split. Returns a list of display names (First Last)."""
    s = re.sub(r"\s+", " ", author_str).strip()
    s = re.sub(r"(?<![A-Z])\.$", "", s)  # keep the full stop of a final initial ("Brett D.")
    s = re.sub(r",? and the .*$", "", s) if " Institute" in s or "(" in s else s
    s = re.sub(r"\bet al\b\.?", "", s).strip(", ")
    toks = [t.strip() for t in re.split(r",\s*(?:and\s+)?|\s+and\s+", s) if t.strip()]
    toks = [re.sub(r"^and\s+", "", t) for t in toks]
    if not toks:
        return []
    if len(toks) == 1 or not inverted:
        return toks
    if len(toks[1].split()) > 3 or re.search(r"[(]|\b(of|for|the)\b", toks[0]):
        return toks  # organisational authors
    first = f"{toks[1]} {toks[0]}"
    rest = [t for t in toks[2:]]
    out = [first]
    for t in rest:
        if t.lower() in ("jr.", "jr", "sr.", "iii") and out:
            out[-1] += " " + t
        else:
            out.append(t)
    return out


ROLE_ED = re.compile(r"[,\s]+\(?(?:eds?|editors?)\.?\)?\s*$", re.I)
WITH = re.compile(r",?\s+with\s+(?=[A-Z]|the\s)")
AND_THE = re.compile(r",?\s+and\s+the\s+", re.I)


def split_roles(authors_str):
    """Separate authors, editors (of the work itself) and contributors ('with ...')."""
    s = clean_markup(authors_str).strip()
    s = re.sub(r"(?<![A-Z])[.,\s]+$", "", s) if not ROLE_ED.search(s) else s
    editors_flag = bool(ROLE_ED.search(s))
    if editors_flag:
        s = ROLE_ED.sub("", s).rstrip(", ")
    contributors = []
    wm = WITH.search(s)
    if wm:
        contributors = parse_names(re.sub(r"^the\s+", "", s[wm.end():].strip(), flags=re.I), inverted=False)
        s = s[:wm.start()]
    groups = []
    am = AND_THE.search(s)
    if am:
        groups = [s[am.end():].strip()]  # collective author, kept whole ("INKE and ETCL Research Groups")
        s = s[:am.start()]
    names = parse_names(s) + groups
    return {
        "authors": [] if editors_flag else names,
        "editors": names if editors_flag else [],
        "contributors": contributors,
    }


def container_editors(container):
    m = re.search(r"\bedited by\s+(.+)$", container, re.I)
    if not m:
        return []
    rest = m.group(1)
    cut = re.search(r",\s*(?:(?:pp?|vol(?:ume)?)\.?\s*)?\d|\s\(|(?<![A-Z])\.\s", rest)
    if cut:
        rest = rest[:cut.start()]
    return [n for n in (t.strip() for t in re.split(r",\s*(?:and\s+)?|\s+and\s+", rest)) if n]


def split_authors_rest(cit):
    """Return (authors, year_label, rest) for author-date, APA, or title-first styles."""
    if cit.startswith(("“", '"', "''")):
        years = YEAR.findall(cit)  # no author given: the entry starts with the title
        return "", (years[-1] if years else "n.d."), cit
    m = re.match(r"^(.{3,400}?)\.?\s*\(((?:1[5-9]|20)\d\d[a-z]?|n\.d\.)\)\.?\s*(.*)$", cit)
    if m and "“" not in m.group(1) and "''" not in m.group(1):
        return m.group(1), m.group(2), m.group(3)
    for ym in YEAR.finditer(cit):
        before = cit[:ym.start()].rstrip()
        if before.endswith(".") and "“" not in before and "''" not in before:
            return before.rstrip("."), ym.group(1), cit[ym.end():].lstrip(". ").strip()
    # Title-first or MLA style: authors end at the first sentence boundary before the title.
    sm = re.search(r"\.\s+(?=[“\"‘]|'')", cit) or re.search(r"(?<![A-Z])\.\s+(?=[A-Z])", cit)
    years = YEAR.findall(cit)
    if sm:
        return cit[:sm.start()], (years[-1] if years else "n.d."), cit[sm.end():].strip()
    return cit, (years[-1] if years else "n.d."), ""


def parse_citation(cit):
    authors_str, year, rest = split_authors_rest(cit)
    url_m = URL.search(rest)
    url = url_m.group(0).rstrip(".,'") if url_m else ""
    doi_m = DOI.search(rest)
    doi = doi_m.group(0).rstrip(".,'") if doi_m else ""
    desc = rest[:url_m.start()].strip() if url_m else rest
    title = ""
    tm = re.match(r"[“\"](.+?)[”\"]", desc)
    if tm:
        title = tm.group(1).strip().rstrip(".,")
        container = desc[tm.end():].strip(" .")
    else:
        im = re.match(r"''(.+?)''", desc)
        if im:
            title = im.group(1).strip().rstrip(".,")
            container = desc[im.end():].strip(" .")
        else:
            title = desc.split(". ")[0].strip(" .")
            container = desc[len(title):].strip(" .")
    container = clean_markup(container)
    title = clean_markup(title).strip(" “”\"")
    # A title with inner quotation marks can close early; fold the rest back into the title.
    qm = re.match(r"^(.{0,250}?)[”\"]\s*", container)
    if qm and not container.startswith("In "):
        title = (title + " " + qm.group(1)).strip(" .,“”\"")
        container = container[qm.end():].strip(" .")
    roles = split_roles(authors_str)
    if tm and re.search(r"^In\b", container):
        kind = "Book chapter"
    elif tm and re.search(r"\d", container) and not re.search(r"^(In|Report|Working|Policy|White)\b", container):
        kind = "Journal article"
    elif tm or year == "n.d.":
        kind = "Report or web resource"
    else:
        kind = "Book or report"
    return {
        "authors_raw": clean_markup(authors_str),
        "authors": roles["authors"],
        "editors": roles["editors"],
        "contributors": roles["contributors"],
        "container_editors": container_editors(container),
        "year": None if year == "n.d." else int(year[:4]),
        "year_label": year,
        "title": title,
        "container": container,
        "url": url,
        "doi": doi,
        "kind": kind,
    }


xrefs = [0]


def parse_page(text, legend, volume_title, chapter, anomalies, page_title):
    entries = []
    heading = []  # stack of (level, text)
    lines = text.split("\n")
    cur = None

    def flush():
        nonlocal cur
        if cur:
            cur["annotation"] = clean_markup(" ".join(cur.pop("_ann")))
            entries.append(cur)
        cur = None

    for line in lines:
        hm = re.match(r"^(={2,5})\s*(.*?)\s*\1\s*$", line)
        if hm:
            flush()
            level = len(hm.group(1))
            heading = [h for h in heading if h[0] < level] + [(level, clean_markup(hm.group(2)))]
            continue
        stripped = re.sub(r"\{\{anchor\|[^}]*\}\}", "", line).strip()
        inner = re.sub(r"^<div[^>]*>\s*", "", stripped)
        inner = re.sub(r"\s*</div>\s*$", "", inner)
        if re.match(r"^'''.+'''\s*\([^)]*\[\[", inner):
            xrefs[0] += 1  # cross-reference to an entry filed in another section
            continue
        bm = BOLD.match(inner)
        if bm and (YEAR.search(bm.group(1)) or "“" in bm.group(1) or "http" in bm.group(1)) and len(bm.group(1)) > 40 and not bm.group(1).rstrip().endswith(":"):
            flush()
            marker, cit = split_citation(re.sub(r"'''", " ", bm.group(1)), legend)
            parsed = parse_citation(cit)
            if not parsed:
                anomalies.append({"type": "unparsed-citation", "page": page_title, "text": cit[:160]})
                continue
            cur = {
                "marker": marker,
                "citation_raw": clean_markup(cit),
                "volume": volume_title,
                "chapter": chapter,
                "sections": [h[1] for h in heading],
                "_ann": [],
                **parsed,
            }
            continue
        if cur is not None:
            if inner.startswith("</div") or inner == "":
                continue
            if re.match(r"^'''.+'''[:：]?", inner):
                anomalies.append({"type": "bold-line-in-annotation", "page": page_title, "text": inner[:140]})
            cur["_ann"].append(inner.lstrip(":").strip())
    flush()
    return entries


def item_id(e):
    key = (e["doi"].lower() if e["doi"] else "") or fold((e["authors"] or e["editors"] or [""])[0]) + "|" + str(e["year"]) + "|" + fold(e["title"])[:80]
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def norm_key(e):
    if e["doi"]:
        return "doi:" + e["doi"].lower().rstrip("/")
    if e["url"]:
        u = re.sub(r"^https?://(www\.)?", "", e["url"].lower()).rstrip("/")
        return "url:" + u
    return "t:" + re.sub(r"[^a-z0-9]", "", fold(e["title"]))[:70] + str(e["year"])


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", fold(s)).strip("-")


def main():
    with open(os.path.join(HERE, "raw", "pages.json"), encoding="utf-8") as f:
        raw = json.load(f)
    anomalies, per_volume, all_entries, volumes_meta = [], {}, [], []
    with open(os.path.join(HERE, "corrections.json"), encoding="utf-8") as f:
        corrections = json.load(f)
    applied = {}
    for vol in raw["volumes"]:
        titles = vol["titles"]
        intro = next((t for t in titles if SKIP_CHAPTERS.search(t) and t.endswith("/Introduction")), None)
        legend = parse_legend(raw["pages"][intro]["text"]) if intro else {}
        vol_entries, list_titles = [], [t for t in titles if LIST_PAGES.search(t)]
        for t in titles:
            if t == vol["root"] or SKIP_CHAPTERS.search(t) or LIST_PAGES.search(t):
                continue
            chapter = t.split("/", 1)[1]
            vol_entries += parse_page(raw["pages"][t]["text"], legend, vol["title"], chapter, anomalies, t)
        for e in vol_entries:
            for c in corrections:
                if c["match"] in e["citation_raw"]:
                    e.update(c["set"])
                    applied[c["match"]] = applied.get(c["match"], 0) + 1
        # Validate: every entry found in the alphabetical list should be parsed.
        listed = 0
        for t in list_titles:
            for ln in raw["pages"][t]["text"].split("\n"):
                ln = ln.strip()
                if ln.startswith("*") and len(ln) > 30 and YEAR.search(ln):
                    listed += 1
        per_volume[vol["slug"]] = {"parsed": len(vol_entries), "reference_lines_in_list_page": listed}
        no_ann = [e for e in vol_entries if not e["annotation"]]
        if no_ann:
            anomalies.append({"type": "entries-without-annotation", "volume": vol["title"], "count": len(no_ann),
                              "examples": [e["citation_raw"][:90] for e in no_ann[:5]]})
        for e in vol_entries:
            if e["doi"] and not re.match(r"^10\.\d{4,9}/", e["doi"]):
                anomalies.append({"type": "malformed-doi", "text": e["doi"]})
            if re.search(r"doi\.org/10/", e["url"] + e["doi"]):
                anomalies.append({"type": "malformed-doi", "volume": vol["title"], "text": (e["url"] or e["doi"])[:100]})
        revs = [raw["pages"][t] for t in titles]
        volumes_meta.append({
            "slug": vol["slug"], "title": vol["title"], "wiki_url": "https://en.wikibooks.org/wiki/" + vol["root"].replace(" ", "_"),
            "entries": len(vol_entries), "legend": legend,
            "latest_revision": max(r["timestamp"] for r in revs),
            "revision_ids": {t: raw["pages"][t]["revid"] for t in titles},
        })
        vol["_entries"] = vol_entries
        all_entries += vol_entries
    for c in corrections:
        if c["match"] not in applied:
            anomalies.append({"type": "stale-correction", "text": c["match"]})
    # Deduplicate across volumes, merging memberships.
    merged = {}
    for e in all_entries:
        k = norm_key(e)
        e["vslug"] = slugify(e["volume"])
        place = {"volume": e["volume"], "vslug": next(v["slug"] for v in raw["volumes"] if v["title"] == e["volume"]),
                 "chapter": e["chapter"], "sections": e["sections"], "marker": e["marker"]}
        if k not in merged:
            e["placements"] = [place]
            e["variants"] = [e["citation_raw"]]
            merged[k] = e
        else:
            m = merged[k]
            m["placements"].append(place)
            if e["citation_raw"] not in m["variants"]:
                m["variants"].append(e["citation_raw"])
            if len(e["annotation"]) > len(m["annotation"]):
                m["annotation"] = e["annotation"]
            if len(e["authors"]) + len(e["editors"]) > len(m["authors"]) + len(m["editors"]):
                for k in ("authors", "editors", "authors_raw"):
                    m[k] = e[k]
            for k in ("contributors", "container_editors"):
                if len(e[k]) > len(m[k]):
                    m[k] = e[k]
    items, seen = [], {}
    for e in merged.values():
        i = item_id(e)
        while i in seen:  # extremely unlikely collision: extend hash
            i = hashlib.sha1((i + e["citation_raw"]).encode()).hexdigest()[:12]
        seen[i] = True
        text = e["title"] + " " + e["annotation"]
        topics = [k for k, rx in LEXICON_RE.items() if rx.search(text)]
        legend_of = {v["slug"]: v["legend"] for v in volumes_meta}
        provenance = sorted({legend_of[p["vslug"]].get(sym, "") for p in e["placements"] for sym in p["marker"]} - {""})
        items.append({
            "id": i, "authors": e["authors"], "editors": e["editors"], "container_editors": e["container_editors"],
            "contributors": e["contributors"], "authors_raw": e["authors_raw"], "year": e["year"], "year_label": e["year_label"],
            "title": e["title"], "container": e["container"], "kind": e["kind"], "url": e["url"], "doi": e["doi"],
            "citation": e["citation_raw"], "variants": e["variants"][1:], "annotation": e["annotation"],
            "topics": topics, "annotation_source": provenance,
            "placements": e["placements"],
            "volumes": sorted({p["volume"] for p in e["placements"]}),
            "chapters": sorted({p["chapter"] for p in e["placements"]}),
            "sections": sorted({s for p in e["placements"] for s in p["sections"]}),
        })
    items.sort(key=lambda x: (fold((x["authors"] or x["editors"] or [""])[0]), x["year"] or 0, fold(x["title"])))
    for e in items:
        for role in ("authors", "editors", "container_editors", "contributors"):
            for nm in e[role]:
                if re.search(r"\b(eds?|editors?|trans|translators?)\b\.?$|^(eds?|editors?)\.?$", nm, re.I):
                    anomalies.append({"type": "role-word-in-name", "text": f"{role}: {nm}"})
                if re.search(r"\b(?:1[5-9]|20)\d\d\b|[“”\"]|https?:", nm):
                    anomalies.append({"type": "citation-fragment-in-name", "text": f"{role}: {nm}"})
                if re.search(r"[\u0370-\u03ff+†*▲¤]", nm):
                    anomalies.append({"type": "symbol-in-name", "text": f"{role}: {nm}"})
        if not e["title"]:
            anomalies.append({"type": "missing-title", "text": e["citation"][:120]})
        if not e["year"] and e["year_label"] != "n.d.":
            anomalies.append({"type": "missing-year", "text": e["citation"][:120]})
    dataset = {
        "meta": {
            "source": "https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections",
            "source_fetched": raw["fetched"], "licence": raw["rights"],
            "corrections": [{"match": c["match"], "reason": c["reason"], "applied": applied.get(c["match"], 0)} for c in corrections],
            "volume_count": len(volumes_meta), "raw_entries": len(all_entries), "unique_items": len(items),
        },
        "volumes": volumes_meta, "items": items, "lexicon": LEXICON,
    }
    with open(os.path.join(HERE, "dataset.json"), "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, "validation.json"), "w", encoding="utf-8") as f:
        json.dump({"per_volume": per_volume, "anomalies": anomalies,
                   "info": {"items_without_named_author": sum(1 for i in items if not i["authors"] and not i["editors"]),
                            "cross_reference_lines_skipped": xrefs[0]}}, f, ensure_ascii=False, indent=1)
    print(json.dumps(per_volume, indent=1))
    print("cross-reference lines skipped:", xrefs[0])
    print(len(all_entries), "raw entries;", len(items), "unique items;", len(anomalies), "anomalies")


if __name__ == "__main__":
    main()
