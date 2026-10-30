"""Tests for the language-model descriptive notes: how the parser applies build/generated_notes.json, how the pages show
them, and the file's own rules (basis, wording, timestamps)."""
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
NOTE = {"note": "A report on evidence and policy.", "basis": "page-read", "evidence": "https://x.example/p",
        "model": "claude-sonnet-5-5 (test)", "generated_at": "2026-10-29T21:38:33Z"}


def real_notes():
    return scratch.read_json(os.path.join(REPO, "build", "generated_notes.json"))


class FileRules(unittest.TestCase):
    def test_every_note_is_complete_short_and_dated(self):
        notes = real_notes()
        self.assertEqual(len({n["id"] for n in notes}), len(notes), "an item has two notes")
        for n in notes:
            self.assertEqual(set(n), {"id", "title", "note", "basis", "evidence", "model", "generated_at"})
            self.assertIn(n["basis"], ("page-read", "citation-only"))
            self.assertLessEqual(len(n["note"].split()), 60, n["id"])
            self.assertNotIn("\u2014", n["note"])
            self.assertRegex(n["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertEqual(n["model"], "claude-sonnet-5-5")
            self.assertRegex(n["evidence"], r"^(https?://\S+)?$")
            if n["basis"] == "page-read":
                self.assertTrue(n["evidence"], f"{n['id']} claims a page was read but gives no address")

    def test_citation_only_notes_do_not_state_findings(self):
        # a note that rests on the citation alone may describe the work only through its title; it must hedge.
        for n in real_notes():
            if n["basis"] == "citation-only" and "title indicates" not in n["note"] and "described in its title" not in n["note"] \
                    and "volume title indicates" not in n["note"] and "listed by its repository" not in n["note"]:
                self.assertNotRegex(n["note"], r"\b(argues|finds|shows|reports that|concludes)\b", n["id"])


class ParserApplies(unittest.TestCase):
    def setUp(self):
        self.root, self.build = scratch.make_scratch()
        self.parse = scratch.reload("parse")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(scratch.reload, "parse")

    def run_parse(self, notes):
        path = os.path.join(self.build, "generated_notes.json")
        if notes is None:
            os.remove(path)
        else:
            scratch.write_json(path, notes)
        old = self.parse.HERE
        self.parse.HERE = self.build
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.parse.main()
        finally:
            self.parse.HERE = old
        return scratch.read_json(os.path.join(self.build, "dataset.json")), scratch.read_json(os.path.join(self.build, "validation.json"))

    def test_a_valid_note_is_attached_and_logged_and_the_annotation_stays_empty(self):
        iid = real_notes()[0]["id"]
        data, val = self.run_parse([dict(NOTE, id=iid)])
        it = next(i for i in data["items"] if i["id"] == iid)
        self.assertEqual(it["annotation"], "")
        self.assertEqual(it["generated_note"], {"text": NOTE["note"], "basis": "page-read", "evidence": NOTE["evidence"], "model": NOTE["model"], "generated_at": NOTE["generated_at"]})
        self.assertEqual([g["id"] for g in data["meta"]["generated_notes"]], [iid])
        self.assertEqual(sum(1 for i in data["items"] if "generated_note" in i), 1)
        self.assertEqual(val["anomalies"] and [a["type"] for a in val["anomalies"] if "note" in a["type"]], [])

    def test_no_file_means_no_notes(self):
        data, val = self.run_parse(None)
        self.assertEqual(data["meta"]["generated_notes"], [])
        self.assertFalse(any("generated_note" in i for i in data["items"]))

    def test_unknown_id_is_a_stale_note(self):
        data, val = self.run_parse([dict(NOTE, id="ffffffffff")])
        self.assertIn({"type": "stale-generated-note", "text": "ffffffffff"}, val["anomalies"])
        self.assertEqual(data["meta"]["generated_notes"], [])

    def test_an_item_that_has_a_source_annotation_is_a_stale_note(self):
        data, _ = self.run_parse([])
        annotated = next(i["id"] for i in data["items"] if i["annotation"])
        data, val = self.run_parse([dict(NOTE, id=annotated)])
        self.assertIn({"type": "stale-generated-note", "text": annotated}, val["anomalies"])
        self.assertNotIn("generated_note", next(i for i in data["items"] if i["id"] == annotated))

    def test_two_notes_for_one_item_are_stale(self):
        iid = real_notes()[0]["id"]
        data, val = self.run_parse([dict(NOTE, id=iid), dict(NOTE, id=iid)])
        self.assertEqual([a["text"] for a in val["anomalies"] if a["type"] == "stale-generated-note"], [iid])
        self.assertEqual(len(data["meta"]["generated_notes"]), 1)

    def test_invalid_notes_are_reported_and_not_applied(self):
        iid = real_notes()[0]["id"]
        for bad in (dict(NOTE, id=iid, basis="guess"), dict(NOTE, id=iid, note="  "), dict(NOTE, id=iid, model=""), dict(NOTE, id=iid, generated_at="")):
            data, val = self.run_parse([bad])
            self.assertIn({"type": "invalid-generated-note", "text": iid}, val["anomalies"], bad)
            self.assertFalse(any("generated_note" in i for i in data["items"]))

    def test_a_missing_title_is_replaced_by_the_citation_in_the_log(self):
        iid = real_notes()[0]["id"]
        data, _ = self.run_parse([dict(NOTE, id=iid)])
        self.assertTrue(data["meta"]["generated_notes"][0]["title"])

    def test_build_stops_on_a_stale_note_through_the_anomaly_gate(self):
        import build
        _, val = self.run_parse([dict(NOTE, id="ffffffffff")])
        with mock.patch.object(build, "HERE", self.build), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            build.check_anomalies(False)


class RenderShowsNotes(unittest.TestCase):
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

    def noted(self):
        return [i for i in self.render.ITEMS if i.get("generated_note")]

    def test_every_noted_item_has_a_labelled_note_on_its_page(self):
        self.assertEqual(len(self.noted()), len(real_notes()))
        for it in self.noted():
            t = self.text("items", it["id"] + ".html")
            g = it["generated_note"]
            self.assertTrue(re.search(r'<div class="generated prose">\s*<h2>Descriptive note \(generated\)</h2>', t), it["id"])
            for needle in (self.render.e(g["text"]), g["model"], g["generated_at"][:10], g["generated_at"][11:16] + " UTC",
                           "The source volume gives no annotation for this entry.", "methodology.html#generated"):
                self.assertTrue(needle in t, f"{it['id']}: {needle[:40]}")

    def test_page_read_notes_link_their_evidence(self):
        it = next(i for i in self.noted() if i["generated_note"]["basis"] == "page-read")
        t = self.text("items", it["id"] + ".html")
        self.assertTrue(f'<a href="{self.render.e(it["generated_note"]["evidence"])}">Source read</a>' in t)
        self.assertTrue(self.render.e("the cited work's own page") in t)

    def test_citation_only_notes_never_claim_the_address_was_read(self):
        for it in self.noted():
            g = it["generated_note"]
            if g["basis"] != "citation-only":
                continue
            t = self.text("items", it["id"] + ".html")
            self.assertTrue("the citation alone" in t, it["id"])
            self.assertFalse("Source read" in t, it["id"])
            self.assertEqual("Address in the citation (not read)" in t, bool(g["evidence"]), it["id"])

    def test_items_without_a_note_show_no_generated_block(self):
        plain = next(i for i in self.render.ITEMS if i["annotation"])
        self.assertFalse("Descriptive note (generated)" in self.text("items", plain["id"] + ".html"))
        self.assertFalse("generated prose" in self.text("items", plain["id"] + ".html"))

    def test_search_config_leaves_generated_notes_out_of_the_index(self):
        cfg = scratch.REPO + "/build/staticSearch_config.xml"
        with open(cfg, encoding="utf-8") as f:
            self.assertIn("contains-token(@class,'generated')", f.read())

    def test_volume_page_labels_the_note_inline(self):
        t = self.text("volumes", "knowledge-mobilization.html")
        self.assertEqual(t.count('<p class="ann generated">'), len(self.noted()))
        self.assertIn('<span class="genlabel">Written by a language model', t)

    def test_items_csv_carries_the_note_columns(self):
        with open(os.path.join(self.site, "data", "items.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        noted = [r for r in rows if r["generated_note"]]
        self.assertEqual(len(noted), len(real_notes()))
        for r in noted:
            self.assertEqual(r["annotation"], "")
            self.assertIn(r["generated_note_basis"], ("page-read", "citation-only"))
            self.assertTrue(r["generated_note_model"].startswith("claude-"))
            self.assertRegex(r["generated_note_at"], r"^\d{4}-")
        self.assertEqual(sum(1 for r in rows if not r["generated_note"]), len(rows) - len(noted))
        self.assertIn("generated_note", self.text("data", "README.md"))

    def test_items_json_has_the_note_object(self):
        data = scratch.read_json(os.path.join(self.site, "data", "items.json"))
        self.assertEqual(sum(1 for i in data["items"] if "generated_note" in i), len(real_notes()))

    def test_explore_data_includes_the_note(self):
        t = self.text("index.html")
        blob = json.loads(re.search(r'<script type="application/json" id="osp-data">(.*?)</script>', t, re.S).group(1))
        self.assertEqual(sum(1 for i in blob["items"] if i["generated_note"]), len(real_notes()))
        self.assertTrue(all("generated_note" in i for i in blob["items"]))

    def test_methodology_section_records_model_time_basis_and_every_item(self):
        t = self.text("methodology.html")
        self.assertIn('id="generated"', t)
        self.assertIn("17. Generated descriptive notes", t)
        notes = real_notes()
        self.assertTrue("claude-sonnet-5-5" in t)
        self.assertIn(min(n["generated_at"] for n in notes).replace("T", " ").replace("Z", " UTC"), t)
        self.assertIn(max(n["generated_at"] for n in notes).replace("T", " ").replace("Z", " UTC"), t)
        section = t[t.index('id="generated"'):]
        self.assertEqual(section.count('<a href="items/'), len(notes))
        pr = sum(1 for n in notes if n["basis"] == "page-read")
        self.assertIn(f"{len(notes) - pr} are of that kind and {pr} are", section)
        self.assertIn(f"{len(notes)} of those items now carry", section)

    def test_about_page_points_to_the_methodology_section(self):
        self.assertIn("methodology.html#generated", self.text("about.html"))

    def test_note_label_wording(self):
        g = {"model": "m-1", "basis": "page-read", "generated_at": "2026-10-29T21:38:33Z"}
        self.assertEqual(self.render.note_label(g), "Written by a language model (m-1) on 2026-10-29 at 21:38 UTC, from the cited work's own page. "
                         "It is not part of the Open Scholarship Press annotation and can contain errors.")
        self.assertIn("from the citation alone (the page could not be read).", self.render.note_label(dict(g, basis="citation-only")))

    def test_methodology_without_notes_still_renders(self):
        meta = copy.deepcopy(self.render.DS["meta"])
        meta["generated_notes"] = []
        with mock.patch.dict(self.render.DS, {"meta": meta}):
            self.render.methodology_page()
        t = self.text("methodology.html")
        self.assertTrue("Model: none." in t[t.index('id="generated"'):])
        self.render.main()


if __name__ == "__main__":
    unittest.main()
