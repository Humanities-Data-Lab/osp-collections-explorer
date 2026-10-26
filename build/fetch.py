"""Fetch wikitext for the Open Scholarship Press Collections from Wikibooks.

Stdlib only. Writes build/raw/pages.json with page text, revision id and
timestamp for every page of the bibliography volumes, plus licence info.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://en.wikibooks.org/w/api.php"
UA = "OSPCollectionsVisualizer/0.1 (static research visualization; non-commercial)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "pages.json")

# slug, display title, page-title prefix on Wikibooks
VOLUMES = [
    ("community", "Community", "Open Scholarship Press Collections: Community"),
    ("connection", "Connection", "Open Scholarship Press Collections: Connection"),
    ("policy", "Policy", "Open Scholarship Press Collections: Policy"),
    ("training", "Training", "Open Scholarship Press Collections: Training"),
    ("knowledge-mobilization", "Knowledge Mobilization in the Humanities", "Knowledge Mobilization in the Humanities"),
    ("knowledge-diversity", "Engaging Knowledge Diversity", "Engaging Knowledge Diversity"),
    ("platforms", "Engaging Platforms in Open Scholarship", "Engaging Platforms in Open Scholarship"),
]


def call(**params):
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            time.sleep(2)
            return data
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 5:
                raise
            wait = 30 * (attempt + 1)
            if isinstance(e, urllib.error.HTTPError):
                wait = int(e.headers.get("Retry-After") or 0) or wait
            print("retry after", type(e).__name__, "waiting", wait, "s")
            time.sleep(wait)


def list_titles(prefix):
    data = call(action="query", list="allpages", apprefix=prefix, aplimit=500)
    return [p["title"] for p in data["query"]["allpages"]]


def get_pages(titles):
    pages = {}
    cache = os.path.join(HERE, "raw", "chunks")
    os.makedirs(cache, exist_ok=True)
    for i in range(0, len(titles), 5):
        chunk = titles[i:i + 5]
        key = hashlib.sha1("|".join(chunk).encode()).hexdigest()
        path = os.path.join(cache, key + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = call(action="query", prop="revisions", rvprop="content|ids|timestamp",
                        rvslots="main", titles="|".join(chunk))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        for p in data["query"]["pages"].values():
            rev = p["revisions"][0]
            pages[p["title"]] = {
                "revid": rev["revid"],
                "timestamp": rev["timestamp"],
                "text": rev["slots"]["main"]["*"],
            }
    return pages


def main():
    out = {"fetched": time.strftime("%Y-%m-%d"), "volumes": [], "pages": {}}
    rights = call(action="query", meta="siteinfo", siprop="rightsinfo")["query"]["rightsinfo"]
    out["rights"] = rights
    for slug, name, prefix in VOLUMES:
        titles = list_titles(prefix)
        titles = [t for t in titles if t == prefix or t.startswith(prefix + "/")]
        out["volumes"].append({"slug": slug, "title": name, "root": prefix, "titles": titles})
        out["pages"].update(get_pages(titles))
        print(slug, len(titles), "pages")
    hub = get_pages(["Open Scholarship Press Collections"])
    out["pages"].update(hub)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("rights:", rights)


if __name__ == "__main__":
    main()
