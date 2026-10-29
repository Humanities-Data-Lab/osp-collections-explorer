"""Tests for build/build_search.py: Java and Ant are replaced by mocks, so no clone, no network and no JVM are needed."""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import scratch

import build_search as bs

FORM = ('<div id="staticSearch" data-ssfolder="staticSearch"><form><div class="a"><div class="b"></div><br/></div>'
        '<input type="text"/></form></div>')


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.page = os.path.join(self.dir, "search.html")
        self.index = os.path.join(self.dir, "index.html")
        self.out = os.path.join(self.dir, "staticSearch")
        self.dest = os.path.join(self.dir, "_staticsearch")
        self.config = os.path.join(self.dir, "config.xml")
        self.patches = [mock.patch.object(bs, n, v) for n, v in
                        (("PAGE", self.page), ("INDEX", self.index), ("OUT", self.out), ("DEST", self.dest), ("CONFIG", self.config))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def get(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()


class GeneratedForm(Base):
    def test_extracts_the_balanced_form_block(self):
        self.put(self.page, "<html><body><p>x</p>" + FORM + "<p>after</p></body></html>")
        self.assertEqual(bs.generated_form(), FORM)

    def test_ignores_self_closing_divs(self):
        block = '<div id="staticSearch"><div/><div>t</div></div>'
        self.put(self.page, "<body>" + block + "<div>other</div></body>")
        self.assertEqual(bs.generated_form(), block)

    def test_unbalanced_block_is_an_error(self):
        self.put(self.page, '<div id="staticSearch"><div>')
        with self.assertRaises(ValueError):
            bs.generated_form()

    def test_missing_block_is_an_error(self):
        self.put(self.page, "<body></body>")
        with self.assertRaises(ValueError):
            bs.generated_form()


class FillSlot(Base):
    def test_replaces_the_slot(self):
        self.put(self.index, "<main><!--@STATICSEARCH@--></main>")
        bs.fill_explore_slot("<form/>")
        self.assertEqual(self.get(self.index), "<main><form/></main>")

    def test_missing_slot_stops_the_build(self):
        self.put(self.index, "<main></main>")
        with self.assertRaises(SystemExit) as cm:
            bs.fill_explore_slot("<form/>")
        self.assertIn("no staticSearch slot", str(cm.exception))


class HaveJava(unittest.TestCase):
    def test_no_java_on_the_path(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(bs.have_java())

    def test_java_that_runs(self):
        with mock.patch("shutil.which", return_value="/usr/bin/java"), \
                mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)):
            self.assertTrue(bs.have_java())

    def test_a_java_stub_that_fails(self):
        with mock.patch("shutil.which", return_value="/usr/bin/java"), \
                mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            self.assertFalse(bs.have_java())


class Main(Base):
    def setUp(self):
        super().setUp()
        self.put(self.page, '<body><div id="staticSearch"></div></body>')
        self.put(self.index, "<main><!--@STATICSEARCH@--></main>")

    def fake_run(self, head=bs.COMMIT, files=25):
        """Stand-in for subprocess.run: records calls, plays git and ant."""
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "git" and "clone" in cmd:
                os.makedirs(self.dest)
            if cmd[0] == "git" and "rev-parse" in cmd:
                return mock.Mock(stdout=head + "\n")
            if cmd[0] == "ant":
                os.makedirs(self.out, exist_ok=True)
                for i in range(files):
                    self.put(os.path.join(self.out, f"f{i}.json"), "{}")
                self.put(self.page, "<body>" + FORM + "</body>")
            return mock.Mock(returncode=0)
        run.calls = calls
        return run

    def run_with_tools(self, run, argv=()):
        with mock.patch.object(bs, "have_java", return_value=True), mock.patch("shutil.which", return_value="/usr/bin/ant"), \
                mock.patch("subprocess.run", run):
            bs.main(list(argv))

    def test_without_java_the_page_says_so_and_the_slot_is_emptied(self):
        with mock.patch.object(bs, "have_java", return_value=False):
            bs.main([])
        self.assertIn("search index was not built", self.get(self.page))
        self.assertNotIn('id="staticSearch"', self.get(self.page))
        self.assertEqual(self.get(self.index), "<main></main>")

    def test_without_ant_the_same(self):
        with mock.patch.object(bs, "have_java", return_value=True), mock.patch("shutil.which", return_value=None):
            bs.main([])
        self.assertEqual(self.get(self.index), "<main></main>")

    def test_require_stops_without_java(self):
        with mock.patch.object(bs, "have_java", return_value=False), self.assertRaises(SystemExit) as cm:
            bs.main(["--require"])
        self.assertIn("Java and Apache Ant", str(cm.exception))

    def test_argv_defaults_to_sys_argv(self):
        with mock.patch.object(bs, "have_java", return_value=False), mock.patch("sys.argv", ["x", "--require"]):
            with self.assertRaises(SystemExit):
                bs.main()

    def test_full_run_clones_checks_the_commit_runs_ant_and_fills_the_slot(self):
        run = self.fake_run()
        self.run_with_tools(run)
        self.assertEqual(run.calls[0][:2], ["git", "clone"])
        self.assertIn(bs.TAG, run.calls[0])
        self.assertIn(bs.REPO, run.calls[0])
        self.assertEqual(run.calls[-1][0], "ant")
        self.assertIn("-DssConfigFile=" + self.config, run.calls[-1])
        index = self.get(self.index)
        self.assertIn('data-ssfolder="items/staticSearch"', index)
        self.assertIn('href="items/staticSearch/ssSearch.css"', index)
        self.assertIn('src="items/staticSearch/ssSearch.js"', index)
        self.assertNotIn("@STATICSEARCH@", index)

    def test_existing_checkout_is_not_cloned_again_and_old_output_is_cleared(self):
        os.makedirs(self.dest)
        os.makedirs(self.out)
        self.put(os.path.join(self.out, "stale.json"), "{}")
        run = self.fake_run()
        self.run_with_tools(run)
        self.assertFalse(any("clone" in c for c in run.calls))
        self.assertFalse(os.path.exists(os.path.join(self.out, "stale.json")))

    def test_wrong_checkout_commit_stops_the_build(self):
        run = self.fake_run(head="0" * 40)
        with self.assertRaises(SystemExit) as cm:
            self.run_with_tools(run)
        self.assertIn("expected " + bs.COMMIT, str(cm.exception))
        self.assertFalse(any(c[0] == "ant" for c in run.calls))

    def test_too_few_index_files_stops_the_build(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_with_tools(self.fake_run(files=3))
        self.assertIn("only 3 files", str(cm.exception))

    def test_ant_that_writes_nothing_stops_the_build(self):
        def run(cmd, **kw):
            if "clone" in cmd:
                os.makedirs(self.dest)
            if "rev-parse" in cmd:
                return mock.Mock(stdout=bs.COMMIT)
            return mock.Mock(returncode=0)
        with self.assertRaises(SystemExit) as cm:
            self.run_with_tools(run)
        self.assertIn("only 0 files", str(cm.exception))

    def test_a_failing_ant_run_propagates(self):
        def run(cmd, **kw):
            if cmd[0] == "ant":
                raise subprocess.CalledProcessError(1, cmd)
            if "rev-parse" in cmd:
                return mock.Mock(stdout=bs.COMMIT)
            return mock.Mock(returncode=0)
        os.makedirs(self.dest)
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_with_tools(run)


class Pins(unittest.TestCase):
    def test_release_is_pinned_by_tag_and_full_commit(self):
        self.assertRegex(bs.TAG, r"^v\d+\.\d+\.\d+$")
        self.assertRegex(bs.COMMIT, r"^[0-9a-f]{40}$")

    def test_default_paths_are_inside_the_repository(self):
        for p in (bs.PAGE, bs.OUT, bs.INDEX, bs.CONFIG):
            self.assertTrue(os.path.abspath(p).startswith(scratch.REPO), p)


if __name__ == "__main__":
    unittest.main()
