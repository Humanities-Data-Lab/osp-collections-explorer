"""How the Crossref check runs inside the parser and how every page, export and filter shows it."""
import contextlib
import copy
import csv
import io
import json
import os
import re
import shutil
import unittest
from unittest import mock

import scratch

REPO = scratch.REPO
DEWAELE = "10.1093/reseval/rvaa033"        # listed in the volume with the surname "Dewaele" only and no year


def real_snapshot():
    return scratch.read_json(os.path.join(REPO, "build", "raw", "crossref.json"))


class ParserStep(unittest.TestCase):
    def setUp(self):
        self.root, self.build = scratch.make_scratch()
        self.parse = scratch.reload("parse")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(scratch.reload, "parse")
        self.path = os.path.join(self.build, "raw", "crossref.json")

    def run_parse(self, snapshot="real"):
        if snapshot is None:
            os.remove(self.path)
        elif snapshot != "real":
            scratch.write_json(self.path, snapshot)
        old = self.parse.HERE
        self.parse.HERE = self.build
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.parse.main()
        finally:
            self.parse.HERE = old
        return scratch.read_json(os.path.join(self.build, "dataset.json")), scratch.read_json(os.path.join(self.build, "validation.json"))

    def by_doi(self, data, doi):
        return next(i for i in data["items"] if i["doi"].lower() == doi.lower())

    def test_every_doi_is_checked_and_counted(self):
        data, val = self.run_parse()
        with_doi = [i for i in data["items"] if i["doi"]]
        self.assertTrue(all("crossref" in i for i in with_doi))
        self.assertFalse(any("crossref" in i for i in data["items"] if not i["doi"]))
        meta = data["meta"]["crossref"]
        self.assertEqual(meta["items_with_doi"], len(with_doi))
        self.assertEqual(sum(meta["status"].values()), len(with_doi))
        self.assertEqual(meta["fetched"], real_snapshot()["fetched"])
        self.assertEqual([a for a in val["anomalies"] if a["type"].startswith("crossref")], [])

    def test_a_corrected_item_keeps_the_original_values_and_its_evidence(self):
        data, _ = self.run_parse()
        it = self.by_doi(data, DEWAELE)
        self.assertEqual(it["crossref"]["status"], "corrected")
        by_field = {c["field"]: c for c in it["crossref"]["changes"]}
        self.assertEqual(by_field["authors"]["from"], ["Dewaele"])
        self.assertEqual(it["authors"][0], "Alexis Dewaele")
        self.assertGreater(len(it["authors"]), 1)
        self.assertEqual((by_field["year"]["from"], it["year"], it["year_label"]), ("n.d.", 2021, "2021"))
        self.assertEqual(it["crossref"]["evidence"], "https://api.crossref.org/works/" + DEWAELE)
        self.assertEqual(it["crossref"]["checked"], real_snapshot()["fetched"])
        self.assertTrue(it["citation"].startswith("Dewaele"))          # the citation as listed is untouched

    def test_corrections_never_change_an_identifier(self):
        with_check, _ = self.run_parse()
        without, _ = self.run_parse(None)
        self.assertEqual({i["id"] for i in with_check["items"]}, {i["id"] for i in without["items"]})
        self.assertFalse(any("crossref" in i for i in without["items"]))
        self.assertEqual(without["meta"]["crossref"], {"fetched": "", "items_with_doi": 0, "status": {}})

    def test_without_a_snapshot_nothing_changes_and_nothing_is_reported(self):
        data, val = self.run_parse(None)
        self.assertEqual(self.by_doi(data, DEWAELE)["authors"], ["Dewaele"])
        self.assertEqual([a for a in val["anomalies"] if a["type"].startswith("crossref")], [])

    def test_a_doi_missing_from_the_snapshot_is_reported(self):
        snap = real_snapshot()
        del snap["works"][DEWAELE]
        data, val = self.run_parse(snap)
        self.assertIn({"type": "crossref-not-fetched", "text": DEWAELE}, val["anomalies"])
        self.assertNotIn("crossref", self.by_doi(data, DEWAELE))
        self.assertEqual(data["meta"]["crossref"]["items_with_doi"], sum(1 for i in data["items"] if i["doi"]) - 1)

    def test_the_name_variant_table_is_applied_to_crossref_names(self):
        snap = real_snapshot()
        w = snap["works"][DEWAELE]
        w["authors"] = [{"family": "Dewaele", "given": "Alexis", "name": ""}, {"family": "Siemens", "given": "Ray", "name": ""}]
        data, _ = self.run_parse(snap)
        self.assertEqual(self.by_doi(data, DEWAELE)["authors"], ["Alexis Dewaele", "Raymond G. Siemens"])

    def test_a_doi_that_points_elsewhere_changes_nothing(self):
        snap = real_snapshot()
        snap["works"][DEWAELE].update(title="Something Else Entirely Here", authors=[{"family": "Nobody", "given": "N", "name": ""}], year=1990)
        data, _ = self.run_parse(snap)
        it = self.by_doi(data, DEWAELE)
        self.assertEqual(it["crossref"]["status"], "different-work")
        self.assertEqual(it["authors"], ["Dewaele"])
        self.assertEqual(it["year"], None)

    def test_snapshot_keys_are_matched_case_insensitively(self):
        snap = real_snapshot()
        snap["works"] = {k.lower(): v for k, v in snap["works"].items()}
        data, val = self.run_parse(snap)
        self.assertEqual([a for a in val["anomalies"] if a["type"].startswith("crossref")], [])
        self.assertIn("crossref", self.by_doi(data, DEWAELE))


class SnapshotRules(unittest.TestCase):
    def test_the_committed_snapshot_is_well_formed_and_covers_every_doi(self):
        snap = real_snapshot()
        self.assertRegex(snap["fetched"], r"^\d{4}-\d\d-\d\d$")
        for doi, w in snap["works"].items():
            self.assertEqual(doi, doi.lower())
            self.assertIn(w["status"], (200, 404))
            if w["status"] == 200:
                self.assertEqual(set(w), {"status", "doi", "title", "subtitle", "container", "year", "type", "publisher", "authors", "editors"}, doi)
            else:
                self.assertIn("ra", w)
        root, build = scratch.make_scratch()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        scratch.run_parse(build)                                       # dataset.json is generated, never committed
        data = scratch.read_json(os.path.join(build, "dataset.json"))
        dois = {i["doi"].lower() for i in data["items"] if i["doi"]}
        self.assertEqual(set(snap["works"]), dois)


class Rendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.build = scratch.make_scratch()
        scratch.run_parse(cls.build)
        cls.render = scratch.load_render(cls.build)
        cls.render.main()
        cls.site = os.path.join(cls.root, "site")

    @classmethod
    def tearDownClass(cls):
        scratch.unload_render()
        shutil.rmtree(cls.root, ignore_errors=True)

    def text(self, *p):
        with open(os.path.join(self.site, *p), encoding="utf-8") as f:
            return f.read()

    def items(self, status):
        return [i for i in self.render.ITEMS if i.get("crossref", {}).get("status") == status]

    def test_all_four_outcomes_occur_in_the_real_data(self):
        for status in ("matched", "corrected", "not-registered", "different-work"):
            self.assertTrue(self.items(status), status)

    def test_corrected_pages_list_every_change_with_the_original(self):
        for it in self.items("corrected"):
            t = self.text("items", it["id"] + ".html")
            self.assertTrue("This record takes its values from Crossref" in t, it["id"])
            for c in it["crossref"]["changes"]:
                self.assertTrue(self.render.e(self.render.change_text(c["to"])) in t, (it["id"], c["field"]))
            self.assertTrue("The citation as listed, further down, is unchanged." in t)

    def test_matched_page(self):
        it = self.items("matched")[0]
        self.assertTrue("the record already agrees with it" in self.text("items", it["id"] + ".html"))

    def test_not_registered_pages_name_the_agency_or_say_the_doi_does_not_exist(self):
        seen = set()
        for it in self.items("not-registered"):
            t = self.text("items", it["id"] + ".html")
            ra = it["crossref"]["ra"]
            if ra:
                self.assertTrue(f"It is registered with {ra}." in t)
            else:
                self.assertTrue("the DOI does not exist" in t)
            seen.add(bool(ra))
        self.assertEqual(seen, {True, False})

    def test_different_work_pages_say_nothing_was_taken(self):
        for it in self.items("different-work"):
            t = self.text("items", it["id"] + ".html")
            self.assertTrue("to a different work" in t)
            self.assertTrue("Nothing in this record was taken from it." in t)
            self.assertTrue(self.render.e(it["crossref"]["crossref_title"]) in t)

    def test_a_different_year_takes_crossrefs_and_the_page_states_the_listed_one(self):
        it = next(i for i in self.items("corrected") if any(c["field"] == "year" and c["from"] not in ("n.d.", "") for c in i["crossref"]["changes"]))
        c = next(c for c in it["crossref"]["changes"] if c["field"] == "year")
        self.assertEqual(it["year"], c["to"])
        self.assertTrue(f"year: now {c['to']}; the volume listing gave {c['from']}" in self.text("items", it["id"] + ".html"))

    def test_kept_values_are_stated_on_the_page(self):
        seen = set()
        for it in self.render.ITEMS:
            for k in it.get("crossref", {}).get("kept", []):
                t = self.text("items", it["id"] + ".html")
                self.assertTrue("Kept as the volume lists them:" in t, it["id"])
                self.assertTrue(self.render.e(self.render.kept_text(k, it)) in t, it["id"])
                seen.add(k["reason"])
        self.assertEqual(seen, {"authors-fewer", "authors-reordered", "title-different"})

    def test_kept_text_wording(self):
        k = self.render.kept_text
        it = {"authors": ["A", "B", "C"]}
        self.assertEqual(k({"reason": "authors-fewer", "crossref": ["A"]}, it), "authors: Crossref lists 1 against the volume's 3, so the volume's longer list was kept")
        self.assertIn("same names in another order or form", k({"reason": "authors-reordered", "crossref": []}, it))
        self.assertEqual(k({"reason": "title-different", "crossref": "Intro"}, it), "title: Crossref words it differently (Intro), so the volume's title was kept")

    def test_crossref_fact_wording_for_each_status(self):
        f = self.render.crossref_fact
        base = {"checked": "2026-10-29", "evidence": "https://api.crossref.org/works/10.1/x", "changes": []}
        self.assertIsNone(f({}))
        self.assertIn("the record already agrees with it", f({"crossref": dict(base, status="matched")}))
        kept = f({"authors": ["A", "B"], "crossref": dict(base, status="matched", kept=[{"field": "authors", "reason": "authors-fewer", "crossref": ["A"]}])})
        self.assertIn("<br />Kept as the volume lists them: authors: Crossref lists 1 against the volume", kept.replace("&#x27;", "'"))
        self.assertIn("registered with DataCite", f({"crossref": dict(base, status="not-registered", ra="DataCite")}))
        self.assertIn("the DOI does not exist", f({"crossref": dict(base, status="not-registered", ra="")}))
        no_authors = f({"crossref": dict(base, status="different-work", crossref_title="T", crossref_authors=[])})
        self.assertTrue("different work: T." in no_authors and " by " not in no_authors)
        with_authors = f({"crossref": dict(base, status="different-work", crossref_title="T", crossref_authors=["A B", "C D"])})
        self.assertIn("different work: T by A B; C D.", with_authors)
        fixed = f({"crossref": dict(base, status="corrected", changes=[{"field": "kind", "from": "Book or report", "to": "Journal article"},
                                                                          {"field": "year", "from": "", "to": 2021}])})
        self.assertIn("type of work: now Journal article; the volume listing gave Book or report", fixed)
        self.assertIn("year: now 2021; the volume listing gave nothing", fixed)

    def test_change_text(self):
        self.assertEqual(self.render.change_text(["a", "b"]), "a; b")
        self.assertEqual(self.render.change_text(2021), "2021")
        self.assertEqual(self.render.CROSSREF_LABELS["matched"], "Agrees with Crossref")
        self.assertEqual(self.render.change_text([]), "")

    def test_search_filter_values_are_written_for_items_with_a_doi_only(self):
        corrected = self.items("corrected")[0]
        t = self.text("items", corrected["id"] + ".html")
        self.assertTrue('<meta name="Crossref check" class="staticSearch_desc" content="Corrected from Crossref" />' in t)
        no_doi = next(i for i in self.render.ITEMS if not i["doi"])
        self.assertFalse("Crossref check" in self.text("items", no_doi["id"] + ".html"))
        self.assertEqual(set(self.render.CROSSREF_LABELS), {"corrected", "matched", "not-registered", "different-work"})

    def test_csv_columns(self):
        with open(os.path.join(self.site, "data", "items.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        by_status = {}
        for r in rows:
            by_status.setdefault(r["crossref_status"], []).append(r)
        self.assertEqual(len(by_status[""]), sum(1 for i in self.render.ITEMS if not i["doi"]))
        self.assertEqual(len(by_status["corrected"]), len(self.items("corrected")))
        for r in by_status["corrected"]:
            self.assertTrue(r["crossref_changed_fields"])
            self.assertRegex(r["crossref_checked"], r"^\d{4}-")
        for r in by_status["matched"] + by_status["not-registered"]:
            self.assertEqual(r["crossref_changed_fields"], "")

    def test_json_export_and_data_readme(self):
        data = scratch.read_json(os.path.join(self.site, "data", "items.json"))
        self.assertEqual(sum(1 for i in data["items"] if "crossref" in i), sum(1 for i in self.render.ITEMS if i["doi"]))
        readme = self.text("data", "README.md")
        for needle in ("crossref:", "crossref_status", "not-registered", "section 18"):
            self.assertTrue(needle in readme, needle)

    def test_explore_data_carries_status_and_fields_only(self):
        blob = json.loads(re.search(r'<script type="application/json" id="osp-data">(.*?)</script>', self.text("index.html"), re.S).group(1))
        marked = [i for i in blob["items"] if i["crossref"]]
        self.assertEqual(len(marked), sum(1 for i in self.render.ITEMS if i["doi"]))
        self.assertTrue(all(set(i["crossref"]) == {"status", "fields"} for i in marked))
        self.assertEqual(sum(1 for i in marked if i["crossref"]["status"] == "corrected"), len(self.items("corrected")))
        self.assertTrue(all(i["crossref"] is None for i in blob["items"] if not i["id"] in {m["id"] for m in marked}))

    def test_methodology_section_records_the_decision_numbers_and_tables(self):
        t = self.text("methodology.html")
        self.assertIn('id="crossref"', t)
        self.assertIn('href="#crossref"', t)
        self.assertIn("18. Crossref as the source of truth for DOIs", t)
        section = t[t.index('id="crossref"'):]
        meta = self.render.DS["meta"]["crossref"]
        fixed = self.items("corrected")
        self.assertTrue("Decision (maintainer, 29 October 2026): for an item that has a DOI, Crossref is the source of truth" in section)
        self.assertIn(f"{meta['items_with_doi']} items carry a DOI", section)
        self.assertIn(f"{len(fixed)} records were changed on this basis", section)
        self.assertIn(f"read on {meta['fetched']}", section)
        self.assertIn(f"{meta['status']['matched']} items already agreed with Crossref", section)
        self.assertIn(f"{meta['status']['different-work']} DOIs resolve to a different work", section)
        self.assertIn(f"{meta['status']['not-registered']} are not held by Crossref", section)
        for guard in ("Fewer authors", "Names turned round", "Different title wording"):
            self.assertIn(guard, section)
        from collections import Counter
        kept = Counter(k["reason"] for i in self.render.ITEMS for k in i.get("crossref", {}).get("kept", []))
        self.assertIn(f"Fewer authors ({kept['authors-fewer']} items)", section)
        self.assertIn(f"Names turned round ({kept['authors-reordered']} items)", section)
        self.assertIn(f"Different title wording ({kept['title-different']} items)", section)
        changes = sum(len(i["crossref"]["changes"]) for i in fixed)
        changed_part = section[section.index("Items changed to Crossref's values"):section.index("DOIs that were not used")]
        self.assertEqual(changed_part.count("<tr>") - 1, changes)
        other_part = section[section.index("DOIs that were not used"):]
        self.assertEqual(other_part.count("<tr>") - 1, len(self.items("different-work")) + len(self.items("not-registered")))
        self.assertIn("Not held by Crossref; registered with DataCite", other_part)
        self.assertIn("the DOI does not exist", other_part)
        self.assertIn("Resolves to a different work", other_part)
        for needle in ("Crossref's title and subtitle", "Crossref's year", "Not touched: the citation as listed", "Titles that Crossref writes in sentence case"):
            self.assertTrue(needle in section, needle)

    def test_other_pages_point_to_section_18(self):
        self.assertTrue("Section 18 records the decision to treat Crossref as the source of truth for DOIs" in self.text("about.html"))
        self.assertTrue("(section 18)" in self.text("methodology.html"))

    def test_methodology_without_a_snapshot_still_renders(self):
        meta = copy.deepcopy(self.render.DS["meta"])
        meta.pop("crossref")
        items = [{k: v for k, v in i.items() if k != "crossref"} for i in self.render.ITEMS]
        with mock.patch.dict(self.render.DS, {"meta": meta}), mock.patch.object(self.render, "ITEMS", items):
            self.render.methodology_page()
        self.assertIn("0 items carry a DOI", self.text("methodology.html"))
        self.render.main()


if __name__ == "__main__":
    unittest.main()
