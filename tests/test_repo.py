"""Guards on the repository itself: configuration files are valid, every program and template has tests,
and the deployment workflow cannot run without the tests passing first."""
import glob
import json
import os
import re
import unittest
import xml.etree.ElementTree as ET

import scratch

REPO = scratch.REPO
BUILD = scratch.BUILD
BASIS = {"person-named", "organisation-on-page", "organisation-other"}


def load(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return json.load(f)


def text(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


class Configuration(unittest.TestCase):
    def test_corrections_each_have_a_match_a_change_and_a_reason(self):
        for c in load("build", "corrections.json"):
            self.assertTrue(c["match"].strip())
            self.assertTrue(c["reason"].strip())
            self.assertIsInstance(c["set"], dict)
            self.assertTrue(c["set"])

    def test_name_variants_are_well_formed_and_do_not_overlap(self):
        seen = {}
        for g in load("build", "name_variants.json"):
            self.assertTrue(g["name"].strip())
            self.assertTrue(g["reason"].strip())
            self.assertTrue(g["variants"])
            self.assertNotIn(g["name"], g["variants"])
            for v in g["variants"]:
                self.assertNotIn(v, seen, f"{v!r} is a variant of two people")
                seen[v] = g["name"]
        self.assertFalse(set(seen) & {g["name"] for g in load("build", "name_variants.json")}, "a variant is also a canonical name")

    def test_recovered_authors_record_their_evidence(self):
        for r in load("build", "recovered_authors.json"):
            self.assertIn(r["basis"], BASIS)
            self.assertTrue(r["match"].strip())
            self.assertTrue(r["authors"])
            self.assertRegex(r["evidence"], r"^https?://")
            self.assertRegex(r["checked"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(r["note"].strip())
            self.assertIsInstance(r["contributors"], list)

    def test_known_anomalies_are_unique_signatures(self):
        known = load("build", "known_anomalies.json")
        self.assertEqual(len(known), len(set(known)))
        for s in known:
            self.assertEqual(s.count("|"), 2, s)

    def test_snapshot_has_every_volume_page(self):
        raw = load("build", "raw", "pages.json")
        self.assertTrue(raw["volumes"])
        for v in raw["volumes"]:
            self.assertIn(v["root"], raw["pages"])
            for t in v["titles"]:
                self.assertIn(t, raw["pages"], t)
                self.assertIn("text", raw["pages"][t])

    def test_staticsearch_config_is_xml_and_points_at_real_files(self):
        root = ET.parse(os.path.join(BUILD, "staticSearch_config.xml")).getroot()
        ns = "{http://hcmc.uvic.ca/ns/staticSearch}"
        page = root.find(f"{ns}params/{ns}searchPage").get("file")
        self.assertTrue(page.endswith("site/items/search.html"))
        self.assertEqual(root.get("version"), "2")

    def test_templates_exist(self):
        for name in ("app.js", "coauthor.js", "style.css"):
            self.assertTrue(os.path.getsize(os.path.join(BUILD, "templates", name)) > 0, name)

    def test_gitignore_keeps_generated_files_out(self):
        ignored = text(".gitignore")
        for pattern in ("site/", "build/dataset.json", "build/validation.json", "build/_staticsearch/"):
            self.assertIn(pattern, ignored)

    def test_version_is_one_number_in_one_place(self):
        versions = re.findall(r'^VERSION = "(\d+\.\d+\.\d+)"', text("build", "render.py"), re.M)
        self.assertEqual(len(versions), 1)


class EveryModuleIsTested(unittest.TestCase):
    def test_each_python_module_is_imported_by_a_test(self):
        tests = "".join(text("tests", os.path.basename(p)) for p in glob.glob(os.path.join(REPO, "tests", "test_*.py")))
        for path in glob.glob(os.path.join(BUILD, "*.py")):
            name = os.path.splitext(os.path.basename(path))[0]
            self.assertRegex(tests, rf"(^|\n)\s*(import|from) {name}\b|reload\(\"{name}\"\)|\"{name}\"", f"no test imports build/{name}.py")

    def test_each_template_script_has_a_test_file(self):
        js_tests = "".join(text("tests", "js", os.path.basename(p)) for p in glob.glob(os.path.join(REPO, "tests", "js", "*.test.js")))
        for path in glob.glob(os.path.join(BUILD, "templates", "*.js")):
            self.assertTrue(os.path.basename(path) in js_tests, f"no JavaScript test refers to {os.path.basename(path)}")


class DeploymentWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = text(".github", "workflows", "pages.yml")

    def job(self, name):
        m = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", self.wf, re.M | re.S)
        self.assertIsNotNone(m, f"job {name} missing")
        return m.group(1)

    def test_tests_run_in_their_own_job(self):
        t = self.job("test")
        self.assertIn("tests/run_all.py", t)

    def test_build_waits_for_the_tests_and_deploy_waits_for_the_build(self):
        self.assertRegex(self.job("build"), r"needs:\s*test\b")
        self.assertRegex(self.job("deploy"), r"needs:\s*build\b")

    def test_nothing_deploys_except_through_the_deploy_job(self):
        self.assertEqual(self.wf.count("deploy-pages"), 1)
        self.assertNotIn("deploy-pages", self.job("test") + self.job("build"))

    def test_test_job_installs_every_tool_the_tests_need(self):
        t = self.job("test")
        self.assertIn("setup-python", t)
        self.assertIn("setup-node", t)

    def test_tests_do_not_get_write_permissions_they_do_not_need(self):
        self.assertNotIn("pages: write", self.job("test"))


if __name__ == "__main__":
    unittest.main()
