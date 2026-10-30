"""Tests for build/crossref.py: no network; urlopen and sleep are mocked, and every file is written to a temp folder."""
import contextlib
import email.message
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

import scratch   # noqa: F401  (puts build/ on sys.path)

import crossref as cr


def http_error(code, retry_after=None):
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError("http://x", code, "err", hdrs, None)


def reply(obj):
    return io.BytesIO(json.dumps(obj).encode())


MSG = {"DOI": "10.1/X", "title": ["A Title", "Alt"], "subtitle": ["A Subtitle"], "container-title": ["Journal"], "issued": {"date-parts": [[2020, 5]]}, "type": "journal-article",
       "publisher": "Pub", "author": [{"family": "Lee", "given": "Ann", "sequence": "first"}, {"name": "Group"}], "editor": [{"family": "Ed", "given": "E"}]}


class Pure(unittest.TestCase):
    def test_key_lowercases_and_strips(self):
        self.assertEqual(cr.key(" 10.1/AbC "), "10.1/abc")

    def test_first(self):
        self.assertEqual(cr.first(["a", "b"]), "a")
        self.assertEqual(cr.first([]), "")
        self.assertEqual(cr.first("s"), "s")
        self.assertEqual(cr.first(None), "")

    def test_year_of_uses_the_first_date_that_has_a_year(self):
        self.assertEqual(cr.year_of({"issued": {"date-parts": [[2019]]}}), 2019)
        self.assertEqual(cr.year_of({"issued": {"date-parts": [[None]]}, "published-print": {"date-parts": [[2018, 1]]}}), 2018)
        self.assertEqual(cr.year_of({"published-online": {"date-parts": [[2017]]}}), 2017)
        self.assertEqual(cr.year_of({"published": {"date-parts": [[2016]]}}), 2016)
        self.assertEqual(cr.year_of({"issued": {"date-parts": [[]]}}), None)
        self.assertIsNone(cr.year_of({}))
        self.assertIsNone(cr.year_of({"issued": {}}))

    def test_compact_keeps_what_the_check_reads(self):
        c = cr.compact(MSG)
        self.assertEqual(c["status"], 200)
        self.assertEqual((c["doi"], c["title"], c["subtitle"], c["container"], c["year"], c["type"], c["publisher"]), ("10.1/X", "A Title", "A Subtitle", "Journal", 2020, "journal-article", "Pub"))
        self.assertEqual(c["authors"], [{"family": "Lee", "given": "Ann", "name": ""}, {"family": "", "given": "", "name": "Group"}])
        self.assertEqual(c["editors"], [{"family": "Ed", "given": "E", "name": ""}])

    def test_compact_of_an_empty_message(self):
        c = cr.compact({})
        self.assertEqual((c["title"], c["subtitle"], c["container"], c["year"], c["authors"], c["editors"]), ("", "", "", None, [], []))


class Network(unittest.TestCase):
    def setUp(self):
        self.urlopen = mock.patch("urllib.request.urlopen").start()
        self.sleep = mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    @contextlib.contextmanager
    def quiet(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            yield out

    def test_registration_agency(self):
        self.urlopen.return_value.__enter__.return_value = reply([{"DOI": "10.5/z", "RA": "DataCite"}])
        self.assertEqual(cr.registration_agency("10.5/z"), "DataCite")
        sent = self.urlopen.call_args.args[0]
        self.assertEqual(sent.full_url, "https://doi.org/doiRA/10.5/z")
        self.assertEqual(sent.get_header("User-agent"), cr.UA)

    def test_agency_is_empty_when_the_doi_does_not_exist(self):
        self.urlopen.return_value.__enter__.return_value = reply([{"DOI": "10.5/z", "status": "DOI does not exist"}])
        self.assertEqual(cr.registration_agency("10.5/z"), "")
        self.urlopen.return_value.__enter__.return_value = reply([])
        self.assertEqual(cr.registration_agency("10.5/z"), "")

    def test_agency_is_empty_on_an_http_error(self):
        self.urlopen.side_effect = http_error(404)
        self.assertEqual(cr.registration_agency("10.5/z"), "")

    def test_get_returns_the_compact_record_and_quotes_the_doi(self):
        self.urlopen.return_value.__enter__.return_value = reply({"message": MSG})
        r = cr.get("10.1/a b(c)")
        self.assertEqual(r["title"], "A Title")
        self.assertEqual(self.urlopen.call_args.args[0].full_url, "https://api.crossref.org/works/10.1/a%20b(c)")
        self.assertEqual(self.urlopen.call_args.kwargs["timeout"], 60)

    def test_get_404_asks_for_the_agency(self):
        with mock.patch.object(cr, "registration_agency", return_value="DataCite") as ra:
            self.urlopen.side_effect = http_error(404)
            self.assertEqual(cr.get("10.5/z"), {"status": 404, "ra": "DataCite"})
        ra.assert_called_once_with("10.5/z")

    def test_get_retries_after_a_rate_limit_using_retry_after(self):
        self.urlopen.side_effect = [http_error(429, "7"), mock.MagicMock(__enter__=lambda s: reply({"message": MSG}), __exit__=lambda *a: False)]
        with self.quiet() as out:
            self.assertEqual(cr.get("10.1/x")["title"], "A Title")
        self.sleep.assert_called_once_with(7)
        self.assertIn("retry after HTTP 429", out.getvalue())

    def test_get_uses_its_own_wait_when_retry_after_is_a_date_or_empty(self):
        ok = mock.MagicMock(__enter__=lambda s: reply({"message": MSG}), __exit__=lambda *a: False)
        self.urlopen.side_effect = [http_error(503, "Wed, 21 Oct 2015 07:28:00 GMT"), http_error(503, "0"), ok]
        with self.quiet():
            cr.get("10.1/x")
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [10, 20])

    def test_get_retries_network_errors_then_raises_on_the_sixth(self):
        self.urlopen.side_effect = urllib.error.URLError("down")
        with self.quiet() as out, self.assertRaises(urllib.error.URLError):
            cr.get("10.1/x")
        self.assertEqual(self.urlopen.call_count, 6)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [10, 20, 30, 40, 50])
        self.assertEqual(out.getvalue().count("retry after URLError"), 5)

    def test_get_gives_up_on_a_persistent_http_error(self):
        self.urlopen.side_effect = http_error(500)
        with self.quiet(), self.assertRaises(urllib.error.HTTPError):
            cr.get("10.1/x")
        self.assertEqual(self.urlopen.call_count, 6)


class Main(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.out = os.path.join(self.dir, "raw", "crossref.json")
        self.patches = [mock.patch.object(cr, "HERE", self.dir), mock.patch.object(cr, "OUT", self.out), mock.patch("time.sleep"),
                        mock.patch.object(cr, "get", side_effect=lambda d: {"status": 200, "doi": d, "title": "T " + d})]
        self.get = None
        for p in self.patches:
            m = p.start()
            if p.attribute == "get":
                self.get = m
        self.addCleanup(mock.patch.stopall)
        self.dataset([{"doi": "10.1/B"}, {"doi": "10.1/a"}, {"doi": ""}, {"doi": "10.1/b"}])

    def dataset(self, items):
        with open(os.path.join(self.dir, "dataset.json"), "w", encoding="utf-8") as f:
            json.dump({"items": items}, f)

    def run_main(self, argv=()):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cr.main(list(argv))
        with open(self.out, encoding="utf-8") as f:
            return json.load(f), out.getvalue()

    def test_fetches_each_distinct_doi_once_in_order_and_writes_the_snapshot(self):
        snap, out = self.run_main()
        self.assertEqual([c.args[0] for c in self.get.call_args_list], ["10.1/a", "10.1/b"])
        self.assertEqual(list(snap["works"]), ["10.1/a", "10.1/b"])
        self.assertRegex(snap["fetched"], r"^\d{4}-\d\d-\d\d$")
        self.assertIn("2 fetched; 2 in the snapshot", out)

    def test_a_second_run_fetches_only_what_is_missing(self):
        self.run_main()
        self.get.reset_mock()
        self.dataset([{"doi": "10.1/a"}, {"doi": "10.1/b"}, {"doi": "10.1/c"}])
        snap, out = self.run_main()
        self.assertEqual([c.args[0] for c in self.get.call_args_list], ["10.1/c"])
        self.assertEqual(len(snap["works"]), 3)

    def test_a_run_with_nothing_to_fetch_keeps_the_old_date(self):
        self.run_main()
        with open(self.out, encoding="utf-8") as f:
            snap = json.load(f)
        snap["fetched"] = "2020-01-02"
        with open(self.out, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        self.get.reset_mock()
        snap, out = self.run_main()
        self.assertEqual(snap["fetched"], "2020-01-02")
        self.get.assert_not_called()
        self.assertIn("0 fetched", out)

    def test_refresh_fetches_everything_again(self):
        self.run_main()
        self.get.reset_mock()
        self.run_main(["--refresh"])
        self.assertEqual(self.get.call_count, 2)

    def test_dois_no_longer_in_the_data_are_dropped(self):
        self.run_main()
        self.dataset([{"doi": "10.1/b"}])
        snap, _ = self.run_main()
        self.assertEqual(list(snap["works"]), ["10.1/b"])

    def test_an_empty_dataset_writes_an_empty_snapshot_with_a_date(self):
        self.dataset([{"doi": ""}])
        snap, out = self.run_main()
        self.assertEqual(snap["works"], {})
        self.assertRegex(snap["fetched"], r"^\d{4}")

    def test_progress_is_printed_every_fifty(self):
        self.dataset([{"doi": f"10.1/{i:03d}"} for i in range(120)])
        _, out = self.run_main()
        self.assertIn("50 of 120", out)
        self.assertIn("100 of 120", out)

    def test_argv_defaults_to_sys_argv(self):
        with mock.patch("sys.argv", ["crossref.py", "--refresh"]), contextlib.redirect_stdout(io.StringIO()):
            self.run_main()
            self.get.reset_mock()
            cr.main()
        self.assertEqual(self.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
