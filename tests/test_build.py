"""Tests for build/build.py: the anomaly gate, the XHTML check, the order of the steps, and a whole build in a scratch folder."""
import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import scratch

import build


class Sig(unittest.TestCase):
    def test_uses_volume_or_page_and_truncates_text(self):
        self.assertEqual(build.sig({"type": "t", "volume": "v", "text": "x" * 100}), "t|v|" + "x" * 60)
        self.assertEqual(build.sig({"type": "t", "page": "p"}), "t|p|")
        self.assertEqual(build.sig({"type": "t"}), "t||")


class CheckXhtml(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.items = os.path.join(self.root, "site", "items")
        os.makedirs(self.items)
        os.makedirs(os.path.join(self.root, "build"))
        self.patch = mock.patch.object(build, "HERE", os.path.join(self.root, "build"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.items, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_well_formed_pages_pass(self):
        self.write("a.html", "<html><body><p>ok</p></body></html>")
        build.check_xhtml()

    def test_empty_folder_passes(self):
        build.check_xhtml()

    def test_malformed_page_stops_the_build(self):
        self.write("a.html", "<html><body><p>ok</p></body></html>")
        self.write("bad.html", "<html><body><p>unclosed</body></html>")
        with self.assertRaises(SystemExit) as cm:
            build.check_xhtml()
        self.assertIn("bad.html", str(cm.exception))
        self.assertIn("not well-formed", str(cm.exception))


class CheckAnomalies(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.patch = mock.patch.object(build, "HERE", self.dir)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def found(self, anomalies):
        with open(os.path.join(self.dir, "validation.json"), "w", encoding="utf-8") as f:
            json.dump({"anomalies": anomalies}, f)

    def known(self, sigs):
        with open(os.path.join(self.dir, "known_anomalies.json"), "w", encoding="utf-8") as f:
            json.dump(sigs, f)

    def known_file(self):
        with open(os.path.join(self.dir, "known_anomalies.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_reviewed_anomalies_pass(self):
        a = {"type": "no-annotation", "volume": "V", "text": "x"}
        self.found([a])
        self.known([build.sig(a)])
        build.check_anomalies(False)

    def test_no_anomalies_and_no_known_file_pass(self):
        self.found([])
        build.check_anomalies(False)

    def test_new_anomaly_stops_the_build_and_is_listed(self):
        self.found([{"type": "odd-doi", "page": "P", "text": "10.x"}])
        self.known([])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            build.check_anomalies(False)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("odd-doi|P|10.x", out.getvalue())
        self.assertIn("--accept-anomalies", out.getvalue())

    def test_missing_known_file_counts_as_empty(self):
        self.found([{"type": "t", "text": "x"}])
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            build.check_anomalies(False)

    def test_accepting_records_the_current_anomalies_sorted(self):
        self.found([{"type": "b", "text": "2"}, {"type": "a", "text": "1"}])
        self.known(["stale"])
        build.check_anomalies(True)
        self.assertEqual(self.known_file(), ["a||1", "b||2"])


class Step(unittest.TestCase):
    def test_imports_then_reloads(self):
        name = "scratch_step_probe"
        d = tempfile.mkdtemp()
        with open(os.path.join(d, name + ".py"), "w") as f:
            f.write("import os\nVALUE = os.environ.get('PROBE', 'first')\n")
        sys.path.insert(0, d)
        try:
            with mock.patch.dict(os.environ, {"PROBE": "first"}):
                self.assertEqual(build.step(name).VALUE, "first")
            with mock.patch.dict(os.environ, {"PROBE": "second"}):
                self.assertEqual(build.step(name).VALUE, "second")      # the module is read again, not cached
        finally:
            sys.path.remove(d)
            sys.modules.pop(name, None)
            shutil.rmtree(d, ignore_errors=True)


class MainOrder(unittest.TestCase):
    def run_main(self, argv):
        calls = []

        def fake_step(name):
            m = mock.Mock()
            m.main.side_effect = lambda *a: calls.append((name,) + a)
            return m
        with mock.patch.object(build, "step", fake_step), \
                mock.patch.object(build, "check_anomalies", lambda accept: calls.append(("anomalies", accept))), \
                mock.patch.object(build, "check_xhtml", lambda: calls.append(("xhtml",))):
            build.main(argv)
        return calls

    def test_default_order(self):
        self.assertEqual(self.run_main([]), [("parse",), ("anomalies", False), ("render",), ("xhtml",), ("build_search", [])])

    def test_refresh_fetches_first(self):
        self.assertEqual(self.run_main(["--refresh"])[0], ("fetch",))

    def test_refresh_crossref_parses_fetches_then_parses_again(self):
        calls = self.run_main(["--refresh-crossref"])
        self.assertEqual(calls[:3], [("parse",), ("crossref", ["--refresh"]), ("parse",)])
        self.assertEqual(calls[3:], [("anomalies", False), ("render",), ("xhtml",), ("build_search", [])])

    def test_both_refreshes_fetch_the_wiki_first(self):
        calls = self.run_main(["--refresh", "--refresh-crossref"])
        self.assertEqual([c[0] for c in calls[:4]], ["fetch", "parse", "crossref", "parse"])

    def test_flags_are_passed_on(self):
        calls = self.run_main(["--accept-anomalies", "--require-search"])
        self.assertIn(("anomalies", True), calls)
        self.assertEqual(calls[-1], ("build_search", ["--require"]))

    def test_reads_sys_argv_by_default(self):
        with mock.patch.object(sys, "argv", ["build.py", "--refresh"]):
            calls = []
            with mock.patch.object(build, "step", lambda n: mock.Mock(main=lambda *a: calls.append(n))), \
                    mock.patch.object(build, "check_anomalies"), mock.patch.object(build, "check_xhtml"):
                build.main()
        self.assertEqual(calls[0], "fetch")

    def test_a_failing_step_stops_the_build(self):
        with mock.patch.object(build, "step", lambda n: mock.Mock(main=mock.Mock(side_effect=RuntimeError("boom")))):
            with self.assertRaises(RuntimeError):
                build.main([])


class WholeBuild(unittest.TestCase):
    """The real pipeline, in a scratch folder, with the search step skipped for want of Java."""

    def setUp(self):
        self.root, self.build_dir = scratch.make_scratch()
        os.environ["OSP_BUILD_DIR"] = self.build_dir
        real_step = build.step
        build_dir = self.build_dir

        def step(name):
            mod = real_step(name)
            if name == "parse":
                mod.HERE = build_dir
            if name == "build_search":
                mod.PAGE = os.path.join(build_dir, "..", "site", "items", "search.html")
                mod.INDEX = os.path.join(build_dir, "..", "site", "index.html")
                mod.OUT = os.path.join(build_dir, "..", "site", "items", "staticSearch")
                mod.DEST = os.path.join(build_dir, "_staticsearch")
            return mod
        self.patches = [mock.patch.object(build, "HERE", self.build_dir), mock.patch.object(build, "step", step),
                        mock.patch("shutil.which", return_value=None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        scratch.unload_render()
        sys.modules.pop("render", None)
        for name in ("parse", "build_search"):          # the steps were pointed at the scratch folder; point them back
            if name in sys.modules:
                importlib.reload(sys.modules[name])
        shutil.rmtree(self.root, ignore_errors=True)

    def test_unreviewed_anomalies_stop_before_any_page_is_written(self):
        os.remove(os.path.join(self.build_dir, "known_anomalies.json"))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            build.main([])
        self.assertFalse(os.path.exists(os.path.join(self.root, "site")))

    def test_full_build_without_java_writes_a_usable_site(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            build.main([])
        site = os.path.join(self.root, "site")
        self.assertTrue(os.path.exists(os.path.join(site, "coauthorship.html")))
        self.assertIn("Skipping search index", out.getvalue())
        with open(os.path.join(site, "items", "search.html"), encoding="utf-8") as f:
            self.assertIn("search index was not built", f.read())
        with open(os.path.join(site, "index.html"), encoding="utf-8") as f:
            self.assertNotIn("@STATICSEARCH@", f.read())

    def test_require_search_fails_without_java(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            build.main(["--require-search"])
        self.assertIn("Java and Apache Ant", str(cm.exception))

    def test_accept_anomalies_rewrites_the_known_list(self):
        path = os.path.join(self.build_dir, "known_anomalies.json")
        with open(path, "w") as f:
            f.write("[]")
        with contextlib.redirect_stdout(io.StringIO()):
            build.main(["--accept-anomalies"])
        with open(path, encoding="utf-8") as f:
            self.assertGreaterEqual(len(json.load(f)), 1)


class AsScript(unittest.TestCase):
    """CI runs `python3 -I build/build.py`; isolated mode drops the script folder from sys.path, so the script must add it itself."""

    def test_isolated_run_builds_the_site(self):
        root, build_dir = scratch.make_scratch()
        empty = tempfile.mkdtemp()                       # a PATH with no Java or Ant, so the search step is skipped
        try:
            env = {"PATH": empty, "HOME": empty}
            done = subprocess.run([sys.executable, "-I", os.path.join(build_dir, "build.py")], cwd=root, env=env,
                                  capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            self.assertIn("site built:", done.stdout)
            self.assertTrue(os.path.exists(os.path.join(root, "site", "coauthorship.html")))
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(empty, ignore_errors=True)

    def test_isolated_run_exits_non_zero_on_an_unreviewed_anomaly(self):
        root, build_dir = scratch.make_scratch()
        empty = tempfile.mkdtemp()
        try:
            with open(os.path.join(build_dir, "known_anomalies.json"), "w") as f:
                f.write("[]")
            done = subprocess.run([sys.executable, "-I", os.path.join(build_dir, "build.py")], cwd=root, env={"PATH": empty, "HOME": empty},
                                  capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 1)
            self.assertIn("new anomalies need review", done.stdout)
            self.assertFalse(os.path.exists(os.path.join(root, "site")))
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
