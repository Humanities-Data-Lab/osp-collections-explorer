"""Fetch the Crossref record of every item that has a DOI and keep a compact snapshot in build/raw/crossref.json.

Network access happens only here (like fetch.py); the build reads the snapshot, so a release can be rebuilt offline and identically.
Usage: python3 build/crossref.py [--refresh]    (--refresh fetches every DOI again; by default only DOIs missing from the snapshot are fetched)
Reads build/dataset.json, so run parse.py first. The record kept per DOI is the part of Crossref's reply that the reconciliation reads.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.crossref.org/works/"
UA = "OSPCollectionsVisualizer/0.3 (static research visualization; non-commercial; https://github.com/Humanities-Data-Lab/osp-collections-explorer)"
OUT = os.path.join(HERE, "raw", "crossref.json")
PAUSE = 0.25          # seconds between requests


def key(doi):
    """DOIs are case-insensitive; the snapshot is keyed by the lower-case form."""
    return doi.strip().lower()


def first(v):
    return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else "")


def year_of(msg):
    for field in ("issued", "published-print", "published-online", "published"):
        parts = (msg.get(field) or {}).get("date-parts") or [[None]]
        if parts[0] and parts[0][0]:
            return parts[0][0]
    return None


def compact(msg):
    """The fields the reconciliation compares, from a Crossref `message`."""
    return {
        "status": 200,
        "doi": msg.get("DOI", ""),
        "title": first(msg.get("title")),
        "subtitle": first(msg.get("subtitle")),
        "container": first(msg.get("container-title")),
        "year": year_of(msg),
        "type": msg.get("type", ""),
        "publisher": msg.get("publisher", ""),
        "authors": [{"family": a.get("family", ""), "given": a.get("given", ""), "name": a.get("name", "")} for a in msg.get("author", [])],
        "editors": [{"family": a.get("family", ""), "given": a.get("given", ""), "name": a.get("name", "")} for a in msg.get("editor", [])],
    }


def registration_agency(doi):
    """For a DOI that Crossref does not hold: which agency registered it (DataCite, mEDRA, ...), or "" when the DOI does not exist."""
    req = urllib.request.Request("https://doi.org/doiRA/" + urllib.parse.quote(doi, safe="/()"), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            reply = json.load(r)
    except urllib.error.HTTPError:
        return ""
    return (reply[0].get("RA") or "") if reply else ""


def get(doi):
    """One Crossref record: {status: 200, ...} or {status: 404, ra: <agency or "">}. Retries politely; raises on other failures."""
    url = API + urllib.parse.quote(doi, safe="/()")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return compact(json.load(r)["message"])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"status": 404, "ra": registration_agency(doi)}
            if attempt == 5:
                raise
            wait = 10 * (attempt + 1)
            try:
                wait = int(e.headers.get("Retry-After") or 0) or wait
            except ValueError:
                pass
            print("retry after HTTP", e.code, "waiting", wait, "s")
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 5:
                raise
            print("retry after", type(e).__name__)
            time.sleep(10 * (attempt + 1))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    with open(os.path.join(HERE, "dataset.json"), encoding="utf-8") as f:
        dois = sorted({key(it["doi"]) for it in json.load(f)["items"] if it["doi"]})
    snapshot = {"fetched": "", "works": {}}
    if os.path.exists(OUT) and "--refresh" not in argv:
        with open(OUT, encoding="utf-8") as f:
            snapshot = json.load(f)
    todo = [d for d in dois if d not in snapshot["works"]]
    for n, doi in enumerate(todo, 1):
        snapshot["works"][doi] = get(doi)
        time.sleep(PAUSE)
        if n % 50 == 0:
            print(n, "of", len(todo))
    snapshot["works"] = {d: snapshot["works"][d] for d in sorted(snapshot["works"]) if d in dois}
    snapshot["fetched"] = datetime.date.today().isoformat() if todo or not snapshot["fetched"] else snapshot["fetched"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)
    print(len(todo), "fetched;", len(snapshot["works"]), "in the snapshot")


if __name__ == "__main__":
    main()
