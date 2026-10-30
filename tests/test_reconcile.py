"""Tests for build/reconcile.py: every rule that decides whether an item's record is corrected from Crossref."""
import copy
import unittest

import scratch   # noqa: F401  (puts build/ on sys.path)

import reconcile as rc


def item(**kw):
    base = {"id": "i1", "doi": "10.1/x", "title": "A Study of Open Scholarship", "authors": ["Ann Lee"], "editors": [], "contributors": [],
            "year": 2020, "year_label": "2020", "kind": "Journal article"}
    base.update(kw)
    return base


def work(**kw):
    base = {"status": 200, "doi": "10.1/x", "title": "A Study of Open Scholarship", "container": "J", "year": 2020, "type": "journal-article",
            "publisher": "P", "authors": [{"family": "Lee", "given": "Ann", "name": ""}], "editors": []}
    base.update(kw)
    return base


def person(given, family):
    return {"given": given, "family": family, "name": ""}


class Text(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(rc.fold("Éloïse  O'Brien-Smith!"), "eloise o brien smith")
        self.assertEqual(rc.fold(""), "")

    def test_clean_title_removes_markup_entities_and_spaces(self):
        self.assertEqual(rc.clean_title("Podcasting <i>the</i> Past &amp;  Present\n"), "Podcasting the Past & Present")
        self.assertEqual(rc.clean_title(None), "")

    def test_clean_title_removes_a_chapter_number_and_fixes_the_colon(self):
        self.assertEqual(rc.clean_title("14. Research Ethics in Context"), "Research Ethics in Context")
        self.assertEqual(rc.clean_title("Introduction :Digital Humanities"), "Introduction: Digital Humanities")
        self.assertEqual(rc.clean_title("linking:Reality Hunger"), "linking: Reality Hunger")
        self.assertEqual(rc.clean_title("Ratio 10:30 matters"), "Ratio 10:30 matters")
        self.assertEqual(rc.clean_title("2020. A year"), "2020. A year")       # four digits are a year, not a chapter number
        self.assertEqual(rc.clean_title("1984 and after"), "1984 and after")

    def test_full_title_joins_the_subtitle_once(self):
        self.assertEqual(rc.full_title({"title": "Two Bits", "subtitle": "The Cultural Significance of Free Software"}), "Two Bits: The Cultural Significance of Free Software")
        self.assertEqual(rc.full_title({"title": "Is it open?", "subtitle": "A study"}), "Is it open? A study")
        self.assertEqual(rc.full_title({"title": "Two Bits: The Cultural Significance", "subtitle": "The Cultural Significance"}), "Two Bits: The Cultural Significance")
        self.assertEqual(rc.full_title({"title": "Only", "subtitle": ""}), "Only")
        self.assertEqual(rc.full_title({"title": "Only"}), "Only")
        self.assertEqual(rc.full_title({}), "")

    def test_family_key_is_the_last_folded_word(self):
        self.assertEqual(rc.family_key("José van Dijck"), "dijck")
        self.assertEqual(rc.family_key("Dewaele"), "dewaele")
        self.assertEqual(rc.family_key(""), "")
        self.assertEqual(rc.family_key("!!"), "")


class DisplayName(unittest.TestCase):
    def test_given_and_family(self):
        self.assertEqual(rc.display_name(person("Ann", "Lee")), "Ann Lee")

    def test_family_only(self):
        self.assertEqual(rc.display_name({"family": "Lee"}), "Lee")

    def test_initial_takes_a_full_stop(self):
        self.assertEqual(rc.display_name(person("Peter M", "Groffman")), "Peter M. Groffman")
        self.assertEqual(rc.display_name(person("J. K.", "Rowling")), "J. K. Rowling")

    def test_a_person_written_in_capitals_is_put_in_ordinary_case(self):
        self.assertEqual(rc.display_name(person("BEN", "LEVIN")), "Ben Levin")

    def test_short_capitals_in_a_full_name_are_also_changed(self):
        self.assertEqual(rc.display_name(person("LI", "WANG")), "Li Wang")

    def test_group_names_are_left_alone(self):
        self.assertEqual(rc.display_name(person("ETCL", "Research Group")), "ETCL Research Group")
        self.assertEqual(rc.display_name({"name": " INKE Research Group "}), "INKE Research Group")

    def test_empty(self):
        self.assertEqual(rc.display_name({}), "")


class TitleRelation(unittest.TestCase):
    def test_all_relations(self):
        r = rc.title_relation
        self.assertEqual(r("Open Access: A Guide", "open access a guide"), "equal")
        self.assertEqual(r("Open access publishing", "Open access publishing in the humanities"), "ours-shorter")
        self.assertEqual(r("Open access publishing in the humanities", "Open access publishing"), "theirs-shorter")
        self.assertEqual(r("The science of open data sharing", "Open data sharing: the science of it"), "similar")
        self.assertEqual(r("Open access", "Closed doors"), "different")

    def test_a_plural_or_partial_word_is_not_a_truncation(self):
        self.assertEqual(r := rc.title_relation("The future of scholarly communication", "The future of scholarly communications"), "similar")

    def test_a_very_short_title_is_not_called_a_truncation(self):
        self.assertEqual(rc.title_relation("Intro", "Intro to everything else here"), "different")
        self.assertEqual(rc.title_relation("Intro to everything else here", "Intro"), "different")

    def test_empty_titles_differ(self):
        self.assertEqual(rc.title_relation("", "Anything"), "different")
        self.assertEqual(rc.title_relation("Anything", ""), "different")
        self.assertEqual(rc.title_relation("", ""), "different")


class SameWork(unittest.TestCase):
    def test_similar_titles(self):
        self.assertTrue(rc.same_work(item(), work(), ["Ann Lee"]))

    def test_the_subtitle_counts_towards_the_title(self):
        w = work(title="A Study", subtitle="of Open Scholarship")
        self.assertTrue(rc.same_work(item(), w, ["Zed Roe"]))

    def test_different_titles_but_shared_surname_and_close_year(self):
        w = work(title="Entirely Other Words Here", year=2021)
        self.assertTrue(rc.same_work(item(), w, ["Anne Lee"]))

    def test_editors_count_as_names(self):
        self.assertTrue(rc.same_work(item(authors=[], editors=["Ed Lee"]), work(title="Completely Different"), ["Ann Lee"]))

    def test_shared_surname_but_distant_year(self):
        self.assertFalse(rc.same_work(item(), work(title="Entirely Other Words Here", year=2010), ["Ann Lee"]))

    def test_shared_surname_with_a_year_missing_on_either_side(self):
        w = work(title="Entirely Other Words Here")
        self.assertTrue(rc.same_work(item(year=None), w, ["Ann Lee"]))
        self.assertTrue(rc.same_work(item(), dict(w, year=None), ["Ann Lee"]))

    def test_nothing_shared(self):
        self.assertFalse(rc.same_work(item(), work(title="Entirely Other Words Here"), ["Bo Chan"]))
        self.assertFalse(rc.same_work(item(authors=[]), work(title="Entirely Other Words Here"), []))


class SameWords(unittest.TestCase):
    def test_order_and_accents_do_not_matter(self):
        self.assertTrue(rc.same_words(["Ben Levin"], ["Levin Ben"]))
        self.assertTrue(rc.same_words(["Zoë Roe", "Ann Lee"], ["Ann Lee", "Zoe Roe"]))

    def test_different_words_differ(self):
        self.assertFalse(rc.same_words(["Ann Lee"], ["Anne Lee"]))
        self.assertFalse(rc.same_words(["Ann Lee"], ["Ann Lee", "Bo Chan"]))
        self.assertTrue(rc.same_words([], []))


class Reconcile(unittest.TestCase):
    def test_no_doi_or_no_snapshot_entry(self):
        self.assertIsNone(rc.reconcile(item(doi=""), work()))
        self.assertIsNone(rc.reconcile(item(), None))

    def test_not_registered_with_and_without_an_agency(self):
        self.assertEqual(rc.reconcile(item(), {"status": 404, "ra": "DataCite"}), {"status": "not-registered", "ra": "DataCite", "changes": []})
        self.assertEqual(rc.reconcile(item(), {"status": 404})["ra"], "")

    def test_different_work_carries_what_the_doi_points_to(self):
        w = work(title="The <i>Routledge</i> Handbook", subtitle="Of Things", type="book", authors=[person("Bo", "Chan")], year=2010)
        r = rc.reconcile(item(), w)
        self.assertEqual(r["status"], "different-work")
        self.assertEqual((r["crossref_title"], r["crossref_authors"], r["crossref_type"], r["changes"]), ("The Routledge Handbook: Of Things", ["Bo Chan"], "book", []))
        self.assertNotIn("kept", r)

    def test_matched_when_nothing_differs(self):
        self.assertEqual(rc.reconcile(item(), work()), {"status": "matched", "changes": []})

    # ----- authors -----
    def test_authors_filled_in_when_the_volume_names_none(self):
        r = rc.reconcile(item(authors=[]), work(authors=[person("Ann", "Lee"), person("Bo", "Chan")]))
        self.assertEqual((r["status"], r["changes"]), ("corrected", [{"field": "authors", "from": [], "to": ["Ann Lee", "Bo Chan"]}]))

    def test_authors_not_filled_in_for_an_edited_work(self):
        r = rc.reconcile(item(authors=[], editors=["Ed Lee"]), work(authors=[person("Bo", "Chan")]))
        self.assertEqual(r["changes"], [])

    def test_crossref_authors_replace_the_volumes_when_they_differ(self):
        w = work(authors=[person("Ann", "Lee"), person("Bo", "Chan"), person("Cy", "Doe")])
        for ours in (["Ann Lee", "Bo Chan"], ["Lee"], ["Ann Lee", "Cy Doe"], ["Ann Leigh", "Bo Chan"], ["Ann W. Lee", "Bo Chan", "Cy Doe"]):
            r = rc.reconcile(item(authors=ours), w)
            self.assertEqual(r["changes"], [{"field": "authors", "from": ours, "to": ["Ann Lee", "Bo Chan", "Cy Doe"]}], ours)

    def test_identical_authors_are_not_a_change(self):
        self.assertEqual(rc.reconcile(item(authors=["Ann Lee"]), work())["changes"], [])

    def test_a_shorter_crossref_list_never_drops_authors(self):
        r = rc.reconcile(item(authors=["Ann Lee", "Bo Chan", "Cy Doe"]), work(authors=[person("Bo", "Chan")]))
        self.assertEqual(r["changes"], [])
        self.assertEqual(r["kept"], [{"field": "authors", "reason": "authors-fewer", "crossref": ["Bo Chan"]}])
        self.assertEqual(r["status"], "matched")

    def test_the_same_words_in_another_order_keep_the_volumes_spelling(self):
        r = rc.reconcile(item(authors=["Amanda Cooper", "Ben Levin"]), work(authors=[person("Amanda", "Cooper"), person("Levin", "Ben")]))
        self.assertEqual(r["changes"], [])
        self.assertEqual(r["kept"][0]["reason"], "authors-reordered")

    def test_authors_left_alone_when_crossref_lists_none(self):
        self.assertEqual(rc.reconcile(item(authors=[]), work(authors=[]))["changes"], [])
        r = rc.reconcile(item(authors=["Ann Lee"]), work(authors=[]))
        self.assertEqual((r["changes"], r.get("kept")), ([], None))

    def test_the_name_variant_table_is_applied_and_duplicates_dropped(self):
        w = work(authors=[person("Ray", "Siemens"), person("Ray", "Siemens"), person("Bo", "Chan")])
        canon = lambda n: {"Ray Siemens": "Raymond G. Siemens"}.get(n, n)
        r = rc.reconcile(item(authors=["Raymond G. Siemens"]), w, canon)
        self.assertEqual(r["changes"][0]["to"], ["Raymond G. Siemens", "Bo Chan"])

    # ----- title -----
    def test_crossref_title_replaces_the_volumes_in_every_close_relation(self):
        for ours, theirs, why in (("A Study of Open Scholarship", "A study of open scholarship", "case"),
                                  ("Open access publishing", "Open access publishing in the <b>humanities</b>", "ours cut short"),
                                  ("Open access publishing: a guide for authors", "Open access publishing", "theirs cut short"),
                                  ("The science of open data sharing", "Open data sharing: the science of it", "similar")):
            r = rc.reconcile(item(title=ours), work(title=theirs))
            self.assertEqual([c["field"] for c in r["changes"]], ["title"], why)
            self.assertEqual(r["changes"][0]["from"], ours)
            self.assertEqual(r["changes"][0]["to"], rc.full_title({"title": theirs}))

    def test_the_subtitle_is_part_of_the_crossref_title(self):
        r = rc.reconcile(item(title="Two Bits: The Cultural Significance of Free Software"), work(title="Two Bits", subtitle="The Cultural Significance of Free Software"))
        self.assertEqual(r["changes"], [])

    def test_an_identical_title_is_not_a_change(self):
        self.assertEqual(rc.reconcile(item(), work())["changes"], [])

    def test_a_title_worded_too_differently_is_kept(self):
        r = rc.reconcile(item(title="Whose Infrastructure? Towards Inclusive Knowledge"), work(title="Introduction", authors=[person("Ann", "Lee")]))
        self.assertEqual(r["changes"], [])
        self.assertEqual(r["kept"], [{"field": "title", "reason": "title-different", "crossref": "Introduction"}])

    def test_an_empty_crossref_title_changes_nothing(self):
        r = rc.reconcile(item(), work(title="", authors=[person("Ann", "Lee")]))
        self.assertEqual(r["changes"], [])
        self.assertNotIn("kept", r)

    # ----- year and type -----
    def test_a_missing_year_is_filled_in(self):
        r = rc.reconcile(item(year=None, year_label="n.d."), work(year=2021))
        self.assertEqual(r["changes"], [{"field": "year", "from": "n.d.", "to": 2021}])

    def test_a_different_year_takes_crossrefs(self):
        r = rc.reconcile(item(year=2020, year_label="2020a"), work(year=2019))
        self.assertEqual((r["status"], r["changes"]), ("corrected", [{"field": "year", "from": "2020a", "to": 2019}]))

    def test_the_same_year_and_no_crossref_year_change_nothing(self):
        self.assertEqual(rc.reconcile(item(year=2020), work(year=2020))["changes"], [])
        self.assertEqual(rc.reconcile(item(year=None, year_label="n.d."), work(year=None))["changes"], [])
        self.assertEqual(rc.reconcile(item(year=2020), work(year=None))["changes"], [])

    def test_type_of_work_follows_crossref_when_known(self):
        for ctype, kind in (("journal-article", "Journal article"), ("book-chapter", "Book chapter"), ("book", "Book or report"),
                            ("monograph", "Book or report"), ("edited-book", "Book or report"), ("reference-book", "Book or report"),
                            ("report", "Report or web resource"), ("posted-content", "Report or web resource")):
            wrong = "Book chapter" if kind != "Book chapter" else "Journal article"
            r = rc.reconcile(item(kind=wrong), work(type=ctype))
            self.assertEqual(r["changes"], [{"field": "kind", "from": wrong, "to": kind}], ctype)
            self.assertEqual(rc.reconcile(item(kind=kind), work(type=ctype))["changes"], [], ctype)

    def test_an_unmapped_crossref_type_leaves_the_guess_alone(self):
        self.assertEqual(rc.reconcile(item(kind="Book chapter"), work(type="dataset"))["changes"], [])

    def test_several_changes_together_make_the_item_corrected_in_a_fixed_order(self):
        r = rc.reconcile(item(authors=["Lee"], title="Open access publishing", year=None, year_label="n.d.", kind="Book or report"),
                         work(title="Open access publishing in the humanities", year=2021, authors=[person("Ann", "Lee"), person("Bo", "Chan")]))
        self.assertEqual(r["status"], "corrected")
        self.assertEqual([c["field"] for c in r["changes"]], ["authors", "title", "year", "kind"])

    def test_kept_reasons_are_the_documented_ones(self):
        self.assertEqual(rc.KEPT_REASONS, ("authors-fewer", "authors-reordered", "title-different"))

    def test_the_inputs_are_not_modified(self):
        it, w = item(authors=["Lee"]), work(authors=[person("Ann", "Lee"), person("Bo", "Chan")])
        before = copy.deepcopy((it, w))
        rc.reconcile(it, w)
        self.assertEqual((it, w), before)


class Apply(unittest.TestCase):
    def test_every_field_is_written(self):
        it = item(authors=["Lee"], contributors=["Bo Chan", "Zed Roe"], title="Short title here", year=None, year_label="n.d.", kind="Book or report")
        res = {"changes": [{"field": "authors", "from": ["Lee"], "to": ["Ann Lee", "Bo Chan"]}, {"field": "title", "from": "Short title here", "to": "Short title here and more"},
                           {"field": "year", "from": "n.d.", "to": 2021}, {"field": "kind", "from": "Book or report", "to": "Journal article"}]}
        rc.apply(it, res)
        self.assertEqual(it["authors"], ["Ann Lee", "Bo Chan"])
        self.assertEqual(it["contributors"], ["Zed Roe"])          # a contributor who is now an author is not listed twice
        self.assertEqual((it["title"], it["year"], it["year_label"], it["kind"]), ("Short title here and more", 2021, "2021", "Journal article"))

    def test_no_changes_no_writes(self):
        it = item()
        before = copy.deepcopy(it)
        rc.apply(it, {"status": "matched", "changes": []})
        self.assertEqual(it, before)

    def test_authors_list_is_copied(self):
        it, to = item(), ["Ann Lee"]
        rc.apply(it, {"changes": [{"field": "authors", "from": [], "to": to}]})
        to.append("x")
        self.assertEqual(it["authors"], ["Ann Lee"])


if __name__ == "__main__":
    unittest.main()
