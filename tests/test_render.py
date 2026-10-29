"""Tests for build/render.py: helper functions, every page writer, the data files and the co-authorship page.
The site is built into a scratch folder from the committed wiki snapshot, then checked as a whole (links, well-formedness, reproducibility)."""
import copy
import csv
import hashlib
import json
import os
import re
import shutil
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

import scratch


def tree_digest(root):
    out = {}
    for base, _, files in os.walk(root):
        for name in sorted(files):
            p = os.path.join(base, name)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return out


class BuiltSite(unittest.TestCase):
    """One real build shared by the tests in this class."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.build = scratch.make_scratch()
        scratch.run_parse(cls.build)
        cls.render = scratch.load_render(cls.build)
        cls.render.main()
        cls.site = os.path.join(cls.root, "site")
        cls.first_digest = tree_digest(cls.site)

    @classmethod
    def tearDownClass(cls):
        scratch.unload_render()
        shutil.rmtree(cls.root, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.site, *parts)

    def text(self, *parts):
        with open(self.path(*parts), encoding="utf-8") as f:
            return f.read()

    # ----- what exists -----
    def test_every_page_is_written(self):
        for name in ("index.html", "about.html", "methodology.html", "coauthorship.html", ".nojekyll",
                     "items/search.html", "volumes/index.html", "data/items.json", "data/items.csv", "data/README.md",
                     "data/validation.json", "data/coauthorship-ties.csv", "data/coauthorship-authors.csv"):
            self.assertTrue(os.path.exists(self.path(name)), name)

    def test_one_page_per_item_and_volume(self):
        n = len(self.render.ITEMS)
        items = [f for f in os.listdir(self.path("items")) if f != "search.html"]
        self.assertEqual(len(items), n)
        for v in self.render.VOLS:
            self.assertTrue(os.path.exists(self.path("volumes", v["slug"] + ".html")))

    def test_main_replaces_an_old_site(self):
        stale = self.path("stale.txt")
        with open(stale, "w") as f:
            f.write("old")
        self.render.main()
        self.assertFalse(os.path.exists(stale))

    # ----- quality of the output -----
    def test_item_pages_are_well_formed_xml(self):
        for name in os.listdir(self.path("items")):
            ET.parse(self.path("items", name))      # raises on error

    def test_no_control_characters_in_any_page(self):
        bad = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
        for base, _, files in os.walk(self.site):
            for name in files:
                if name.endswith(".html"):
                    with open(os.path.join(base, name), encoding="utf-8") as f:
                        self.assertIsNone(bad.search(f.read()), name)

    def test_every_page_has_title_landmarks_and_one_h1(self):
        for base, _, files in os.walk(self.site):
            for name in files:
                if not name.endswith(".html"):
                    continue
                with open(os.path.join(base, name), encoding="utf-8") as f:
                    t = f.read()
                where = os.path.relpath(os.path.join(base, name), self.site)
                self.assertIn('<html lang="en"', t, where)
                self.assertRegex(t, r"<title>[^<]+</title>", where)
                self.assertIn('<main id="main"', t, where)
                self.assertIn('class="skip"', t, where)
                self.assertIn('aria-label="Primary"', t, where)
                self.assertEqual(t.count("<h1"), 1, where)

    def test_relative_links_and_fragments_resolve(self):
        link = re.compile(r'(?:href|src)="([^"]+)"')
        ids_cache = {}

        def ids(path):
            if path not in ids_cache:
                with open(path, encoding="utf-8") as f:
                    ids_cache[path] = set(re.findall(r'\bid="([^"]+)"', f.read()))
            return ids_cache[path]
        broken = []
        for base, _, files in os.walk(self.site):
            for name in files:
                if not name.endswith(".html"):
                    continue
                src = os.path.join(base, name)
                with open(src, encoding="utf-8") as f:
                    markup = re.sub(r"<script\b.*?</script>", "", f.read(), flags=re.S)   # strings inside scripts are not links
                    for target in link.findall(markup):
                        if re.match(r"^(https?:|mailto:|data:|javascript:)", target):
                            continue
                        ref, _, frag = target.partition("#")
                        ref = ref.split("?")[0]
                        dest = os.path.normpath(os.path.join(base, ref)) if ref else src
                        if "staticSearch" in dest:
                            continue                      # generated by the search step, which is tested separately
                        if os.path.isdir(dest):
                            dest = os.path.join(dest, "index.html")
                        if not os.path.exists(dest):
                            broken.append((os.path.relpath(src, self.site), target))
                        elif frag and dest.endswith(".html") and frag not in ids(dest):
                            broken.append((os.path.relpath(src, self.site), target))
        self.assertEqual(broken[:10], [])

    def test_navigation_marks_the_current_page(self):
        expect = {"index.html": "Explore", "coauthorship.html": "Co-authorship", "methodology.html": "Methodology",
                  "about.html": "About, data and citation", "items/search.html": "Search", "volumes/index.html": "Volumes"}
        for name, label in expect.items():
            t = self.text(*name.split("/"))
            current = re.findall(r'<a href="[^"]+" aria-current="page">([^<]+)</a>', t)
            self.assertEqual(current, [label], name)

    def test_navigation_lists_the_coauthorship_tab(self):
        self.assertIn('href="coauthorship.html"', self.text("index.html"))
        self.assertIn('href="../coauthorship.html"', self.text("volumes", "index.html"))

    def test_build_is_reproducible(self):
        self.render.main()
        self.assertEqual(tree_digest(self.site), self.first_digest)

    # ----- data files -----
    def test_items_json_matches_dataset(self):
        data = scratch.read_json(self.path("data", "items.json"))
        self.assertEqual(len(data["items"]), len(self.render.ITEMS))
        self.assertEqual(data["meta"]["version"], self.render.VERSION)
        self.assertEqual(data["meta"]["edition"], self.render.EDITION)
        self.assertEqual([v["slug"] for v in data["volumes"]], [v["slug"] for v in self.render.VOLS])

    def test_items_csv_has_one_row_per_item(self):
        with open(self.path("data", "items.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows) - 1, len(self.render.ITEMS))
        self.assertEqual(len(set(len(r) for r in rows)), 1)
        self.assertEqual(rows[0][0], "id")

    def test_data_readme_documents_every_file(self):
        t = self.text("data", "README.md")
        for name in ("items.json", "items.csv", "validation.json", "coauthorship-ties.csv", "coauthorship-authors.csv"):
            self.assertIn(name, t)

    # ----- co-authorship page and files -----
    def test_coauthorship_csv_matches_the_items(self):
        with open(self.path("data", "coauthorship-ties.csv"), encoding="utf-8", newline="") as f:
            ties = list(csv.DictReader(f))
        count, tie_map, groups, gid, co, nb = self.render.coauthor_stats()
        self.assertEqual(len(ties), len(tie_map))
        for row in ties[:50]:
            self.assertLess(row["author_a"], row["author_b"])
            self.assertEqual(int(row["shared_items"]), len(row["item_ids"].split("; ")))
        self.assertGreaterEqual(int(ties[0]["shared_items"]), int(ties[-1]["shared_items"]))
        with open(self.path("data", "coauthorship-authors.csv"), encoding="utf-8", newline="") as f:
            authors = list(csv.DictReader(f))
        self.assertEqual(len(authors), len(count))
        in_groups = [a for a in authors if a["group"]]
        self.assertEqual(len(in_groups), len(gid))

    def test_coauthorship_page_controls_and_data(self):
        t = self.text("coauthorship.html")
        for ident in ("co-filters", "yfrom", "yto", "tie", "group", "find", "only", "co-reset", "network", "panel", "co-status",
                      "t-people", "t-ties", "t-groups", "t-per", "co-data", "co-names", "find-note",
                      "m-items", "m-multi", "m-authors", "m-ties", "m-groups", "m-largest"):
            self.assertIn(f'id="{ident}"', t, ident)
        for v in self.render.VOLS:
            self.assertIn(f'name="Volume" value="{v["title"]}"', t)
        for topic in self.render.TOPICS:
            self.assertIn(f'name="Topic" value="{topic}"', t)
        blob = re.search(r'<script type="application/json" id="co-data">(.*?)</script>', t, re.S).group(1)
        self.assertNotIn("</", blob)
        data = json.loads(blob)
        authored = [it for it in self.render.ITEMS if it["authors"]]
        self.assertEqual(len(data["items"]), len(authored))
        self.assertEqual(set(data["items"][0]), {"id", "a", "y", "v", "t", "k", "n"})

    def test_coauthorship_page_has_a_no_script_fallback(self):
        t = self.text("coauthorship.html")
        self.assertIn('class="nojs"', t)
        self.assertIn("data/coauthorship-ties.csv", t)

    def test_coauthorship_page_embeds_the_script_once(self):
        t = self.text("coauthorship.html")
        self.assertEqual(t.count("OSP Collections Explorer, co-authorship page"), 1)

    def test_methodology_documents_coauthorship(self):
        t = self.text("methodology.html")
        self.assertIn('id="coauthorship"', t)
        self.assertIn('href="#coauthorship"', t)
        count, ties, groups, gid, co, nb = self.render.coauthor_stats()
        self.assertIn(f"{len(ties):,} ties among {len(gid):,} authors", t)
        self.assertIn(f"{len(groups)} connected groups", t)

    def test_methodology_table_of_contents_matches_headings(self):
        t = self.text("methodology.html")
        targets = set(re.findall(r'<a href="#([^"]+)">\d+\.', t))
        ids = set(re.findall(r'<h2 id="([^"]+)"', t))
        self.assertEqual(targets - ids, set())
        self.assertEqual(ids - targets, set())

    # ----- the other pages -----
    def test_index_embeds_all_items_and_a_static_list(self):
        t = self.text("index.html")
        blob = re.search(r'<script type="application/json" id="osp-data">(.*?)</script>', t, re.S).group(1)
        self.assertEqual(len(json.loads(blob)["items"]), len(self.render.ITEMS))
        self.assertIn("<!--@STATICSEARCH@-->", t)
        static_list = re.search(r'<section class="prerender".*?</section>', t, re.S).group(0)
        self.assertEqual(static_list.count('<a href="items/'), len(self.render.ITEMS))

    def test_search_page_has_the_staticsearch_slot(self):
        self.assertIn('<div id="staticSearch"></div>', self.text("items", "search.html"))

    def test_about_page_lists_downloads_and_anomalies(self):
        t = self.text("about.html")
        for name in ("items.json", "items.csv", "README.md"):
            self.assertIn(name, t)
        self.assertIn("Source irregularities found", t)
        self.assertIn('id="engine"', t)

    def test_volume_pages_list_their_items(self):
        for v in self.render.VOLS:
            t = self.text("volumes", v["slug"] + ".html")
            mine = [it for it in self.render.ITEMS if any(p["vslug"] == v["slug"] for p in it["placements"])]
            placed = sum(1 for it in mine for p in it["placements"] if p["vslug"] == v["slug"])     # an item listed under two sections appears twice
            self.assertEqual(t.count('<article class="entry"'), placed, v["slug"])
            self.assertIn(v["wiki_url"], t)

    def test_item_pages_carry_search_metadata(self):
        it = next(i for i in self.render.ITEMS if i["authors"] and i["year"] and i["topics"])
        t = self.text("items", it["id"] + ".html")
        self.assertIn('class="staticSearch_docTitle"', t)
        self.assertIn('name="Author" class="staticSearch_feat"', t)
        self.assertIn('name="Year" class="staticSearch_date"', t)
        self.assertIn('name="Topic" class="staticSearch_desc"', t)
        self.assertIn(f'id="rec-{it["id"]}"', t)


class Helpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.build = scratch.make_scratch()
        scratch.run_parse(cls.build)
        cls.render = scratch.load_render(cls.build)

    @classmethod
    def tearDownClass(cls):
        scratch.unload_render()
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_rel(self):
        self.assertEqual(self.render.rel(0), "")
        self.assertEqual(self.render.rel(2), "../../")

    def test_wiki_url_quotes_titles(self):
        self.assertEqual(self.render.wiki_url("A B/C:D (e)"), "https://en.wikibooks.org/wiki/A_B/C:D_(e)")
        self.assertIn("%C3%A9", self.render.wiki_url("Café"))

    def test_syntax_table_lists_every_example(self):
        t = self.render.syntax_table()
        for q, _ in self.render.SYNTAX:
            self.assertIn(self.render.e(q), t)

    def test_short_cit(self):
        base = {"authors": [], "editors": [], "year_label": "2020", "title": "T", "citation": "C"}
        sc = self.render.short_cit
        self.assertEqual(sc({**base, "authors": ["A B"]}), "A B (2020). T")
        self.assertEqual(sc({**base, "authors": ["A", "B", "C"]}), "A, B, C (2020). T")
        self.assertEqual(sc({**base, "authors": ["A", "B", "C", "D"]}), "A, B, C et al. (2020). T")
        self.assertEqual(sc({**base, "editors": ["E"]}), "E (ed.) (2020). T")
        self.assertEqual(sc({**base, "editors": ["E", "F"]}), "E, F (eds.) (2020). T")
        self.assertEqual(sc({**base, "title": ""}), "No named author (2020). C")

    def test_cite_block(self):
        t = self.render.cite_block(1, "Volume: X.", "abc")
        self.assertIn("Record abc.", t)
        self.assertIn(self.render.VERSION, t)
        self.assertNotIn("Record", self.render.cite_block(0, "Volume: X."))

    def test_page_wraps_a_body(self):
        t = self.render.page("T & U", "<p>body\x01</p>", depth=2, current="about", description="D", extra_head="<meta name='x'/>", scripts="<script>1</script>", html_id="rec-1")
        self.assertIn("<title>T &amp; U</title>", t)
        self.assertNotIn("\x01", t)
        self.assertIn('href="../../index.html"', t)
        self.assertIn('id="rec-1"', t)
        self.assertIn('content="D"', t)
        self.assertIn("<meta name='x'/>", t)
        self.assertTrue(t.rstrip().endswith("</html>"))
        self.assertIn("Search and visualize", self.render.page("T", "", description=""))

    def test_ss_meta_for_a_full_and_an_empty_item(self):
        full = {"title": "T", "authors": ["A"], "editors": ["E"], "container_editors": ["CE"], "year": 2001, "volumes": ["V"],
                "topics": ["Open data"], "kind": "Book chapter", "annotation": "x", "citation": "c"}
        t = self.render.ss_meta(full)
        for needle in ('content="V"', 'content="Open data"', 'content="Book chapter"', 'content="true"', 'content="2001"', 'name="Author"', 'name="Editor" class="staticSearch_feat" content="CE"'):
            self.assertIn(needle, t)
        empty = {"title": "", "authors": [], "editors": [], "container_editors": [], "year": None, "volumes": [], "topics": [], "kind": "Report or web resource", "annotation": "", "citation": "c" * 200}
        t = self.render.ss_meta(empty)
        self.assertIn('content="false"', t)
        self.assertNotIn("staticSearch_date", t)
        self.assertIn("9999", t)
        self.assertIn('content="' + "c" * 120 + '"', t)


def synthetic_items():
    def item(i, authors, year=2020, **kw):
        base = {"id": f"id{i:02d}", "authors": authors, "editors": [], "container_editors": [], "contributors": [], "authors_raw": "", "year": year,
                "year_label": str(year) if year else "n.d.", "title": f"Title {i}", "container": "", "kind": "Journal article", "url": "", "doi": "",
                "citation": f"Citation {i}", "variants": [], "annotation": "", "topics": [], "annotation_source": [], "volumes": ["Community"],
                "chapters": ["Ch"], "sections": [], "placements": [{"volume": "Community", "vslug": "community", "chapter": "Ch", "sections": [], "marker": []}]}
        base.update(kw)
        return base
    return [
        item(1, ["Ann", "Bob"]), item(2, ["Ann", "Bob", "Cy"]), item(3, ["Bob", "Cy"], year=None), item(4, ["Dee", "Eve"]),
        item(5, ["Solo"]), item(6, []), item(7, ["Ann", "Ann"]), item(8, ["Fay", "Gus", "Hal"]),
    ]


class CoauthorStats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.build = scratch.make_scratch()
        scratch.run_parse(cls.build)
        cls.render = scratch.load_render(cls.build)

    @classmethod
    def tearDownClass(cls):
        scratch.unload_render()
        shutil.rmtree(cls.root, ignore_errors=True)

    def stats(self):
        with mock.patch.object(self.render, "ITEMS", synthetic_items()):
            return self.render.coauthor_stats()

    def test_counts_distinct_authors_per_item(self):
        count, ties, groups, gid, co, nb = self.stats()
        self.assertEqual(count["Ann"], 3)            # the repeated name on item 7 counts once
        self.assertEqual(count["Solo"], 1)
        self.assertNotIn("", count)

    def test_ties_hold_the_items_that_made_them(self):
        count, ties, groups, gid, co, nb = self.stats()
        self.assertEqual(ties[("Ann", "Bob")], ["id01", "id02"])
        self.assertEqual(ties[("Bob", "Cy")], ["id02", "id03"])
        self.assertEqual(ties[("Ann", "Cy")], ["id02"])
        self.assertEqual(len(ties[("Fay", "Gus")]), 1)
        self.assertNotIn(("Ann", "Ann"), ties)
        self.assertEqual(len(ties), 3 + 1 + 3)         # {Ann,Bob,Cy}, {Dee,Eve}, {Fay,Gus,Hal}

    def test_groups_are_connected_components_largest_first(self):
        count, ties, groups, gid, co, nb = self.stats()
        self.assertEqual([len(g) for g in groups], [3, 3, 2])
        self.assertEqual(sorted(groups[0]), ["Ann", "Bob", "Cy"])
        self.assertEqual(sorted(groups[1]), ["Fay", "Gus", "Hal"])
        self.assertEqual((gid["Ann"], gid["Fay"], gid["Dee"]), (1, 2, 3))
        self.assertNotIn("Solo", gid)

    def test_coauthored_items_and_neighbours(self):
        count, ties, groups, gid, co, nb = self.stats()
        self.assertEqual(co["Bob"], {"id01", "id02", "id03"})
        self.assertEqual(nb["Bob"], {"Ann", "Cy"})
        self.assertNotIn("Solo", co)

    def test_empty_collection(self):
        with mock.patch.object(self.render, "ITEMS", []):
            count, ties, groups, gid, co, nb = self.render.coauthor_stats()
        self.assertEqual((len(count), len(ties), groups, len(gid)), (0, 0, [], 0))

    def test_files_written_for_synthetic_data(self):
        out = os.path.join(self.root, "synthetic-site")
        os.makedirs(os.path.join(out, "data"))
        with mock.patch.object(self.render, "ITEMS", synthetic_items()), mock.patch.object(self.render, "SITE", out):
            self.render.coauthor_files(*self.render.coauthor_stats())
        with open(os.path.join(out, "data", "coauthorship-authors.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        by = {r["author"]: r for r in rows}
        self.assertEqual(by["Bob"]["coauthored_items"], "3")
        self.assertEqual(by["Bob"]["coauthors"], "2")
        self.assertEqual(by["Bob"]["group"], "1")
        self.assertEqual(by["Bob"]["group_size"], "3")
        self.assertEqual(by["Solo"]["group"], "")
        self.assertEqual(by["Solo"]["group_size"], "1")
        self.assertEqual(rows[0]["author"], "Bob")      # most co-authored items first
        with open(os.path.join(out, "data", "coauthorship-ties.csv"), encoding="utf-8", newline="") as f:
            ties = list(csv.DictReader(f))
        self.assertEqual(ties[0]["author_a"] + ties[0]["author_b"], "AnnBob")
        self.assertEqual(ties[0]["item_ids"], "id01; id02")


class ItemPageBranches(unittest.TestCase):
    """The item page writer has a branch for every optional field."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.build = scratch.make_scratch()
        scratch.run_parse(cls.build)
        cls.render = scratch.load_render(cls.build)

    @classmethod
    def tearDownClass(cls):
        scratch.unload_render()
        shutil.rmtree(cls.root, ignore_errors=True)

    def write(self, **fields):
        vol = self.render.VOLS[0]
        it = copy.deepcopy(synthetic_items()[0])
        it["placements"] = [{"volume": vol["title"], "vslug": vol["slug"], "chapter": "Ch A", "sections": ["S1", "S2"], "marker": []}]
        it.update(fields)
        out = os.path.join(self.root, "branch-site")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        with mock.patch.object(self.render, "ITEMS", [it]), mock.patch.object(self.render, "SITE", out):
            self.render.item_pages()
        with open(os.path.join(out, "items", it["id"] + ".html"), encoding="utf-8") as f:
            return f.read()

    def test_fully_populated_record(self):
        t = self.write(editors=["Ed"], contributors=["Con"], container_editors=["Cont Ed"], container="Journal 5", doi="10.1/x",
                       topics=["Open data"], annotation_source=["Origin"], annotation="Words <b>here</b>", variants=["Other wording"],
                       author_recovery={"basis": "person-named", "evidence": "https://e.example/", "checked": "2026-10-26", "note": "Because."})
        for needle in ("Editors", "With", "Editors of the containing volume", "Published in", "https://doi.org/10.1/x", "Detected topics",
                       "Annotation origin", "Other listings", "Because.", "https://e.example/", "Words &lt;b&gt;here&lt;/b&gt;", "S1 › S2"):
            self.assertIn(needle, t)
        ET.fromstring(t.split("<!DOCTYPE html>")[1])      # still well-formed

    def test_sparse_record(self):
        t = self.write(authors=[], title="", doi="", url="", annotation="")
        self.assertIn("No named author in the source", t)
        self.assertIn("The source volume gives no annotation", t)
        self.assertNotIn("Source</dt>", t)
        self.assertNotIn("Other listings", t)
        self.assertIn("<h1>Citation 1</h1>", t)         # falls back to the citation when there is no title

    def test_url_is_used_when_there_is_no_doi(self):
        t = self.write(url="https://example.org/paper")
        self.assertIn('href="https://example.org/paper"', t)


class VolumePageBranches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.build = scratch.make_scratch()
        scratch.run_parse(cls.build)
        cls.render = scratch.load_render(cls.build)

    @classmethod
    def tearDownClass(cls):
        scratch.unload_render()
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_entries_without_links_annotations_or_legend(self):
        vols = copy.deepcopy(self.render.VOLS)
        vols[0]["legend"] = {}
        vslug = vols[0]["slug"]
        its = synthetic_items()[:3]
        for it in its:
            it["placements"] = [{"volume": vols[0]["title"], "vslug": vslug, "chapter": "Ch", "sections": [], "marker": []}]
        its[0].update(doi="10.5/y", annotation="A note")
        its[1].update(url="https://u.example/")
        out = os.path.join(self.root, "vol-site")
        os.makedirs(out)
        with mock.patch.object(self.render, "ITEMS", its), mock.patch.object(self.render, "VOLS", vols), mock.patch.object(self.render, "SITE", out):
            self.render.volume_pages()
        with open(os.path.join(out, "volumes", vslug + ".html"), encoding="utf-8") as f:
            t = f.read()
        self.assertNotIn("Annotation markers used in this volume", t)
        self.assertIn("https://doi.org/10.5/y", t)
        self.assertIn("https://u.example/", t)
        self.assertEqual(t.count('<p class="ann">'), 1)
        self.assertEqual(t.count("Open source"), 2)
        self.assertIn('<h2 id="ch">Ch</h2>', t)


if __name__ == "__main__":
    unittest.main()
