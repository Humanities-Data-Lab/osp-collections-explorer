"""Reconcile an item's record with the Crossref record of its DOI (the snapshot in build/raw/crossref.json).

Decision of the maintainer, 2026-10-29: Crossref is the source of truth for the bibliographic facts of an item that has a DOI
and whose Crossref record is for the same work. Where it differs, the record takes Crossref's authors, title, year and type of
work, and keeps the volume's original value in the item's `crossref.changes`. Three narrow guards keep the volume's value where
following Crossref literally would destroy information; each is recorded in `crossref.kept` (Methodology section 18).

Pure functions, no network.
"""
import html
import re
import unicodedata

# Crossref `type` -> this site's type of work. Types not listed leave the guessed type alone.
KINDS = {
    "journal-article": "Journal article",
    "book-chapter": "Book chapter",
    "book": "Book or report",
    "monograph": "Book or report",
    "edited-book": "Book or report",
    "reference-book": "Book or report",
    "report": "Report or web resource",
    "posted-content": "Report or web resource",
}
MIN_PREFIX = 8          # a title shorter than this is too short to call a truncation of another title
SAME_TITLE = 0.5        # shared-word share at which two titles are taken to name one work
KEPT_REASONS = ("authors-fewer", "authors-reordered", "title-different")


def fold(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def clean_title(t):
    """Crossref titles can carry markup, character references, a chapter number and odd spacing around the colon."""
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t or ""))).strip()
    t = re.sub(r"^\d{1,3}\.\s+(?=\S)", "", t)                        # "14. Research Ethics" -> "Research Ethics"
    t = re.sub(r"\s+:", ":", t)
    return re.sub(r"(?<=[A-Za-z]):(?=[A-Za-z])", ": ", t)


def full_title(work):
    """The title with its subtitle, which Crossref keeps in a field of its own."""
    title, sub = clean_title(work.get("title", "")), clean_title(work.get("subtitle", ""))
    if sub and fold(sub) not in fold(title):
        title += (" " if title[-1:] in "?!.:" else ": ") + sub
    return title


def display_name(a):
    """'Given Family' from a Crossref author, or the group name as given. A person's name written in capitals is put in
    ordinary case, and a lone initial takes its full stop, as everywhere else on this site."""
    if a.get("family"):
        given, family = a.get("given", ""), a["family"]
        if given.isupper() and family.isupper():                  # a person written entirely in capitals; "ETCL Research Group" is left alone
            given, family = given.title(), family.title()
        name = (given + " " + family).strip()
        return re.sub(r"\b([A-Z])(?=\s|$)", r"\1.", name)
    return a.get("name", "").strip()


def family_key(name):
    """The surname used to compare two spellings of a name: the last word, folded."""
    parts = fold(name).split()
    return parts[-1] if parts else ""


def title_relation(ours, theirs):
    """'equal', 'ours-shorter' (ours is a leading part of Crossref's), 'theirs-shorter', 'similar' or 'different'."""
    a, b = fold(ours), fold(theirs)
    if not a or not b:
        return "different"
    if a == b:
        return "equal"
    if len(a) >= MIN_PREFIX and b.startswith(a + " "):
        return "ours-shorter"
    if len(b) >= MIN_PREFIX and a.startswith(b + " "):
        return "theirs-shorter"
    ta, tb = set(a.split()), set(b.split())
    return "similar" if len(ta & tb) / len(ta | tb) >= SAME_TITLE else "different"


def same_work(item, work, crossref_names):
    """Crossref's record is for this work when the titles agree, or an author surname is shared and the years are within two."""
    if title_relation(item["title"], full_title(work)) != "different":
        return True
    ours = {family_key(n) for n in item["authors"] + item["editors"]} - {""}
    theirs = {family_key(n) for n in crossref_names} - {""}
    year_ok = item["year"] is None or work["year"] is None or abs(item["year"] - work["year"]) <= 2
    return bool(ours & theirs) and year_ok


def same_words(a, b):
    """Two name lists made of the same words, whatever their order (a given and a family name written the wrong way round)."""
    return sorted(fold(" ".join(a)).split()) == sorted(fold(" ".join(b)).split())


def reconcile(item, work, canon=lambda n: n):
    """Compare one item with its Crossref record. `canon` maps a name to its canonical form (the reviewed name-variant table).
    Returns None when the item has no DOI or the snapshot has no entry; otherwise a dict:
      status: matched | corrected | not-registered | different-work
      changes: [{field, from, to}] the corrections to apply (authors, title, year, kind)
      kept: [{field, reason, crossref}] where a guard kept the volume's value; reasons in KEPT_REASONS
      crossref_title, crossref_authors, crossref_type: for different-work, what the DOI points to
      ra: for not-registered, the agency that holds the DOI ("" when the DOI does not exist)."""
    if not item["doi"] or work is None:
        return None
    if work["status"] != 200:
        return {"status": "not-registered", "ra": work.get("ra", ""), "changes": []}
    names = [canon(display_name(a)) for a in work["authors"]]
    names = list(dict.fromkeys(n for n in names if n))
    title = full_title(work)
    if not same_work(item, work, names):
        return {"status": "different-work", "changes": [], "crossref_title": title, "crossref_authors": names, "crossref_type": work["type"]}
    changes, kept = [], []

    # authors: Crossref's list, unless it would drop authors the volume names or only turns names round
    ours = item["authors"]
    if names and names != ours:
        if not ours:
            if not item["editors"]:                                   # an edited work keeps its editors and gets no authors
                changes.append({"field": "authors", "from": [], "to": names})
        elif len(names) < len(ours):
            kept.append({"field": "authors", "reason": "authors-fewer", "crossref": names})
        elif same_words(ours, names):
            kept.append({"field": "authors", "reason": "authors-reordered", "crossref": names})
        else:
            changes.append({"field": "authors", "from": list(ours), "to": names})

    # title: Crossref's, unless its wording differs so much that the match rests on the authors alone
    if title and title != item["title"]:
        if title_relation(item["title"], title) == "different":
            kept.append({"field": "title", "reason": "title-different", "crossref": title})
        else:
            changes.append({"field": "title", "from": item["title"], "to": title})

    # year and type of work: Crossref's
    if work["year"] and work["year"] != item["year"]:
        changes.append({"field": "year", "from": item["year_label"], "to": work["year"]})
    kind = KINDS.get(work["type"])
    if kind and kind != item["kind"]:
        changes.append({"field": "kind", "from": item["kind"], "to": kind})
    out = {"status": "corrected" if changes else "matched", "changes": changes}
    if kept:
        out["kept"] = kept
    return out


def apply(item, result):
    """Write the changes of a result into the item. The original values stay in item['crossref']['changes']."""
    for c in result["changes"]:
        f, to = c["field"], c["to"]
        if f == "authors":
            item["authors"] = list(to)
            item["contributors"] = [n for n in item["contributors"] if n not in to]
        elif f == "year":
            item["year"], item["year_label"] = to, str(to)
        else:
            item[f] = to
