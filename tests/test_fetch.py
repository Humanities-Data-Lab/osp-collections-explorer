"""Unit tests for build/fetch.py. urllib and time.sleep are mocked: no network, no real waiting."""
import contextlib
import email.message
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

BUILD = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build"))
sys.path.insert(0, BUILD)

import fetch  # noqa: E402


def response(payload):
    """A urlopen() result: a context manager whose read() returns JSON bytes."""
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def http_error(code=429, retry_after=None):
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.org", code, "err", hdrs, None)


def page(title, revid=1, text="text"):
    return {"title": title, "revisions": [{"revid": revid, "timestamp": "2024-01-01T00:00:00Z",
                                           "slots": {"main": {"*": text}}}]}


def api_pages(*pages):
    return {"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}


class FetchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osp-fetch-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for target, value in (("HERE", self.tmp), ("OUT", os.path.join(self.tmp, "raw", "pages.json"))):
            p = mock.patch.object(fetch, target, value)
            p.start()
            self.addCleanup(p.stop)
        self.sleep = mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)
        self.urlopen = mock.patch("urllib.request.urlopen").start()

    def quiet(self):
        return contextlib.redirect_stdout(io.StringIO())


class TestCall(FetchCase):
    def test_success_returns_json_and_pauses_politely(self):
        self.urlopen.return_value = response({"ok": 1})
        self.assertEqual(fetch.call(action="query", titles="A|B"), {"ok": 1})
        self.urlopen.assert_called_once()
        self.sleep.assert_called_once_with(2)

    def test_request_url_headers_and_timeout(self):
        self.urlopen.return_value = response({})
        fetch.call(action="query", titles="A B|C", aplimit=500)
        req = self.urlopen.call_args[0][0]
        self.assertEqual(self.urlopen.call_args[1], {"timeout": 60})
        self.assertEqual(req.get_header("User-agent"), fetch.UA)
        parts = urllib.parse.urlsplit(req.full_url)
        self.assertEqual(parts.scheme + "://" + parts.netloc + parts.path, fetch.API)
        self.assertEqual(urllib.parse.parse_qs(parts.query),
                         {"action": ["query"], "titles": ["A B|C"], "aplimit": ["500"], "format": ["json"]})

    def test_format_json_cannot_be_overridden(self):
        self.urlopen.return_value = response({})
        fetch.call(format="xml")
        self.assertIn("format=json", self.urlopen.call_args[0][0].full_url)

    def test_retries_urlerror_with_growing_wait(self):
        self.urlopen.side_effect = [urllib.error.URLError("down"), urllib.error.URLError("down"), response({"ok": 2})]
        with self.quiet() as out:
            self.assertEqual(fetch.call(a=1), {"ok": 2})
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [30, 60, 2])
        self.assertEqual(self.urlopen.call_count, 3)
        self.assertIn("retry after URLError waiting 30 s", out.getvalue())
        self.assertIn("retry after URLError waiting 60 s", out.getvalue())

    def test_retries_timeout_and_oserror(self):
        self.urlopen.side_effect = [TimeoutError("slow"), OSError("reset"), response({"ok": 3})]
        with self.quiet():
            self.assertEqual(fetch.call(a=1), {"ok": 3})
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [30, 60, 2])

    def test_http_error_honours_retry_after(self):
        self.urlopen.side_effect = [http_error(429, "7"), response({"ok": 4})]
        with self.quiet() as out:
            fetch.call(a=1)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [7, 2])
        self.assertIn("HTTPError waiting 7 s", out.getvalue())

    def test_http_error_without_retry_after_uses_default_wait(self):
        self.urlopen.side_effect = [http_error(503), response({})]
        with self.quiet():
            fetch.call(a=1)
        self.assertEqual(self.sleep.call_args_list[0].args[0], 30)

    def test_http_error_with_zero_or_empty_retry_after_uses_default_wait(self):
        for value in ("0", ""):
            self.sleep.reset_mock()
            self.urlopen.side_effect = [http_error(503, value), response({})]
            with self.quiet():
                fetch.call(a=1)
            self.assertEqual(self.sleep.call_args_list[0].args[0], 30, value)

    def test_gives_up_after_six_attempts_and_reraises(self):
        self.urlopen.side_effect = urllib.error.URLError("down")
        with self.quiet():
            with self.assertRaises(urllib.error.URLError):
                fetch.call(a=1)
        self.assertEqual(self.urlopen.call_count, 6)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [30, 60, 90, 120, 150])

    def test_last_http_error_is_reraised_unchanged(self):
        err = http_error(500)
        self.urlopen.side_effect = err
        with self.quiet():
            with self.assertRaises(urllib.error.HTTPError) as cm:
                fetch.call(a=1)
        self.assertIs(cm.exception, err)

    def test_unexpected_exceptions_are_not_retried(self):
        self.urlopen.side_effect = RuntimeError("bug")
        with self.assertRaises(RuntimeError):
            fetch.call(a=1)
        self.assertEqual(self.urlopen.call_count, 1)
        self.sleep.assert_not_called()

    def test_invalid_json_is_not_retried(self):
        self.urlopen.return_value = io.BytesIO(b"<html>not json")
        with self.assertRaises(ValueError):
            fetch.call(a=1)
        self.assertEqual(self.urlopen.call_count, 1)

    def test_http_date_retry_after_falls_back_to_the_default_wait(self):
        # Retry-After may legally be an HTTP date rather than seconds; the call keeps its own 30 s step and retries.
        self.urlopen.side_effect = [http_error(429, "Wed, 21 Oct 2015 07:28:00 GMT"), response({"ok": 1})]
        with self.quiet():
            self.assertEqual(fetch.call(a=1), {"ok": 1})
        self.assertEqual(self.urlopen.call_count, 2)
        self.assertIn(mock.call(30), self.sleep.call_args_list)


class TestListTitles(FetchCase):
    def test_returns_titles_and_uses_prefix_query(self):
        with mock.patch.object(fetch, "call", return_value={"query": {"allpages": [{"title": "A"}, {"title": "A/B"}]}}) as c:
            self.assertEqual(fetch.list_titles("A"), ["A", "A/B"])
        c.assert_called_once_with(action="query", list="allpages", apprefix="A", aplimit=500)

    def test_empty(self):
        with mock.patch.object(fetch, "call", return_value={"query": {"allpages": []}}):
            self.assertEqual(fetch.list_titles("Z"), [])

    def test_through_urlopen(self):
        self.urlopen.return_value = response({"query": {"allpages": [{"title": "P/1"}]}})
        self.assertEqual(fetch.list_titles("P"), ["P/1"])
        self.assertIn("apprefix=P", self.urlopen.call_args[0][0].full_url)


class TestGetPages(FetchCase):
    def chunk_path(self, titles):
        return os.path.join(self.tmp, "raw", "chunks", hashlib.sha1("|".join(titles).encode()).hexdigest() + ".json")

    def test_empty_list_makes_no_calls_but_creates_cache_dir(self):
        with mock.patch.object(fetch, "call") as c:
            self.assertEqual(fetch.get_pages([]), {})
        c.assert_not_called()
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "raw", "chunks")))

    def test_pages_extracted_with_revid_timestamp_text(self):
        data = api_pages(page("A", 11, "alpha"), page("B", 22, "beta"))
        with mock.patch.object(fetch, "call", return_value=data):
            pages = fetch.get_pages(["A", "B"])
        self.assertEqual(pages, {
            "A": {"revid": 11, "timestamp": "2024-01-01T00:00:00Z", "text": "alpha"},
            "B": {"revid": 22, "timestamp": "2024-01-01T00:00:00Z", "text": "beta"},
        })

    def test_titles_are_requested_in_chunks_of_five(self):
        titles = ["T%d" % i for i in range(12)]
        seen = []

        def fake(**params):
            names = params["titles"].split("|")
            seen.append(names)
            return api_pages(*[page(n) for n in names])

        with mock.patch.object(fetch, "call", side_effect=fake) as c:
            pages = fetch.get_pages(titles)
        self.assertEqual([len(s) for s in seen], [5, 5, 2])
        self.assertEqual(sorted(pages), sorted(titles))
        self.assertEqual(c.call_args_list[0].kwargs,
                         {"action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp",
                          "rvslots": "main", "titles": "T0|T1|T2|T3|T4"})

    def test_chunk_is_cached_on_disk_and_reused(self):
        data = api_pages(page("A", 5, "cached text"))
        with mock.patch.object(fetch, "call", return_value=data) as c:
            first = fetch.get_pages(["A"])
        self.assertEqual(c.call_count, 1)
        with open(self.chunk_path(["A"]), encoding="utf-8") as f:
            self.assertEqual(json.load(f), data)
        with mock.patch.object(fetch, "call", side_effect=AssertionError("network used")) as c2:
            second = fetch.get_pages(["A"])
        c2.assert_not_called()
        self.assertEqual(first, second)

    def test_cache_key_depends_on_chunk_titles_and_order(self):
        self.assertNotEqual(self.chunk_path(["A", "B"]), self.chunk_path(["B", "A"]))

    def test_cache_is_read_even_without_network_and_mixed_with_fresh_chunks(self):
        titles = ["T%d" % i for i in range(6)]
        os.makedirs(os.path.join(self.tmp, "raw", "chunks"))
        with open(self.chunk_path(titles[:5]), "w", encoding="utf-8") as f:
            json.dump(api_pages(*[page(n, 1, "from cache") for n in titles[:5]]), f)
        with mock.patch.object(fetch, "call", return_value=api_pages(page("T5", 9, "fresh"))) as c:
            pages = fetch.get_pages(titles)
        self.assertEqual(c.call_count, 1)
        self.assertEqual(c.call_args.kwargs["titles"], "T5")
        self.assertEqual(pages["T0"]["text"], "from cache")
        self.assertEqual(pages["T5"], {"revid": 9, "timestamp": "2024-01-01T00:00:00Z", "text": "fresh"})

    def test_non_ascii_text_survives_cache_round_trip(self):
        data = api_pages(page("A", 1, "Φ é “quoted”"))
        with mock.patch.object(fetch, "call", return_value=data):
            fetch.get_pages(["A"])
        with mock.patch.object(fetch, "call", side_effect=AssertionError):
            self.assertEqual(fetch.get_pages(["A"])["A"]["text"], "Φ é “quoted”")

    def test_error_propagates_and_nothing_is_cached(self):
        with mock.patch.object(fetch, "call", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(urllib.error.URLError):
                fetch.get_pages(["A"])
        self.assertFalse(os.path.exists(self.chunk_path(["A"])))

    def test_retry_path_through_urlopen_then_cached(self):
        self.urlopen.side_effect = [urllib.error.URLError("blip"), response(api_pages(page("A", 3, "x")))]
        with self.quiet():
            self.assertEqual(fetch.get_pages(["A"])["A"]["revid"], 3)
        self.assertTrue(os.path.exists(self.chunk_path(["A"])))
        self.assertEqual(self.urlopen.call_count, 2)

    def test_current_behaviour_page_without_revisions_raises_keyerror(self):
        # A missing page comes back from the API without "revisions"; the fetch stops loudly.
        data = {"query": {"pages": {"-1": {"title": "Gone", "missing": ""}}}}
        with mock.patch.object(fetch, "call", return_value=data):
            with self.assertRaises(KeyError):
                fetch.get_pages(["Gone"])


class TestMain(FetchCase):
    def router(self, hub_title="Open Scholarship Press Collections"):
        """A fake wiki: every volume has a root page, two sub pages, and look-alike titles that must be excluded."""
        self.requests = []

        def fake_urlopen(req, timeout=None):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            self.requests.append(q)
            if q.get("meta") == ["siteinfo"]:
                return response({"query": {"rightsinfo": {"url": "https://license.example", "text": "CC BY-SA"}}})
            if q.get("list") == ["allpages"]:
                prefix = q["apprefix"][0]
                return response({"query": {"allpages": [
                    {"title": prefix}, {"title": prefix + "/One"}, {"title": prefix + "/Two"},
                    {"title": prefix + " 2"}, {"title": prefix + "x"}]}})
            names = q["titles"][0].split("|")
            return response(api_pages(*[page(n, len(n), "text of " + n) for n in names]))

        self.urlopen.side_effect = fake_urlopen

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fetch.main()
        with open(fetch.OUT, encoding="utf-8") as f:
            return json.load(f), out.getvalue()

    def test_end_to_end_with_mocked_wiki(self):
        self.router()
        data, stdout = self.run_main()
        self.assertEqual(sorted(data), ["fetched", "pages", "rights", "volumes"])
        self.assertRegex(data["fetched"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(data["rights"], {"url": "https://license.example", "text": "CC BY-SA"})
        self.assertEqual([v["slug"] for v in data["volumes"]], [v[0] for v in fetch.VOLUMES])
        for (slug, name, prefix), vol in zip(fetch.VOLUMES, data["volumes"]):
            self.assertEqual(vol, {"slug": slug, "title": name, "root": prefix,
                                   "titles": [prefix, prefix + "/One", prefix + "/Two"]})
            for t in vol["titles"]:
                self.assertEqual(data["pages"][t]["text"], "text of " + t)
        # look-alike titles ("<prefix> 2", "<prefix>x") are filtered out and never fetched
        self.assertFalse(any(k.endswith(" 2") or k.endswith("x") for k in data["pages"]))
        self.assertIn("Open Scholarship Press Collections", data["pages"])  # hub page
        self.assertEqual(len(data["pages"]), 7 * 3 + 1)
        self.assertIn("community 3 pages", stdout)
        self.assertIn("rights: {'url': 'https://license.example', 'text': 'CC BY-SA'}", stdout)

    def test_output_goes_to_patched_out_only(self):
        self.router()
        self.run_main()
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "raw", "pages.json")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "raw", "chunks")))

    def test_second_run_is_served_from_chunk_cache(self):
        self.router()
        self.run_main()
        first_requests = len(self.requests)
        self.run_main()
        second = self.requests[first_requests:]
        # only the rights lookup and the seven title listings hit the network the second time
        self.assertEqual(len(second), 1 + len(fetch.VOLUMES))
        self.assertFalse(any("revisions" == q.get("prop", [""])[0] for q in second))

    def test_main_with_mocked_functions(self):
        calls = []
        os.makedirs(os.path.join(self.tmp, "raw"))  # the real get_pages creates it; it is mocked here

        def fake_call(**params):
            calls.append(params)
            return {"query": {"rightsinfo": {"text": "licence"}}}

        titles = {"Open Scholarship Press Collections: Community":
                  ["Open Scholarship Press Collections: Community", "Open Scholarship Press Collections: Community/Intro",
                   "Unrelated"]}
        with mock.patch.object(fetch, "call", side_effect=fake_call), \
                mock.patch.object(fetch, "list_titles", side_effect=lambda p: titles.get(p, [])), \
                mock.patch.object(fetch, "get_pages", side_effect=lambda ts: {t: {"revid": 1} for t in ts}) as gp:
            data, _ = self.run_main()
        self.assertEqual(calls, [{"action": "query", "meta": "siteinfo", "siprop": "rightsinfo"}])
        self.assertEqual(data["volumes"][0]["titles"], [
            "Open Scholarship Press Collections: Community", "Open Scholarship Press Collections: Community/Intro"])
        self.assertEqual(data["volumes"][1]["titles"], [])
        self.assertEqual(gp.call_args_list[-1].args[0], ["Open Scholarship Press Collections"])
        self.assertIn("Open Scholarship Press Collections", data["pages"])

    def test_network_failure_aborts_without_writing_output(self):
        self.urlopen.side_effect = urllib.error.URLError("down")
        with self.quiet():
            with self.assertRaises(urllib.error.URLError):
                fetch.main()
        self.assertFalse(os.path.exists(fetch.OUT))

    def test_running_as_script_calls_main(self):
        self.router()
        os.makedirs(os.path.join(self.tmp, "script", "raw"))
        src_path = fetch.__file__.replace(".pyc", ".py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        with self.quiet():
            exec(compile(src, src_path, "exec"),
                 {"__name__": "__main__", "__file__": os.path.join(self.tmp, "script", "fetch.py")})
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "script", "raw", "pages.json")))


class TestConstants(unittest.TestCase):
    def test_volumes_are_well_formed(self):
        slugs = [v[0] for v in fetch.VOLUMES]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(len(v) == 3 and all(v) for v in fetch.VOLUMES))

    def test_api_is_https_and_user_agent_identifies_project(self):
        self.assertTrue(fetch.API.startswith("https://"))
        self.assertIn("OSPCollectionsVisualizer", fetch.UA)

    def test_default_paths_point_at_build_raw(self):
        self.assertEqual(os.path.basename(fetch.HERE), "build")
        self.assertEqual(fetch.OUT, os.path.join(fetch.HERE, "raw", "pages.json"))


if __name__ == "__main__":
    unittest.main()
