"""Unit and integration tests for build/parse.py (stdlib unittest only, no network, temp dirs only)."""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

BUILD = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build"))
sys.path.insert(0, BUILD)

import parse  # noqa: E402


# ---------------------------------------------------------------------------
# Small string helpers
# ---------------------------------------------------------------------------

class TestFold(unittest.TestCase):
    def test_strips_accents_and_lowercases(self):
        self.assertEqual(parse.fold("Éco-LÉ Ñandú"), "eco-le nandu")

    def test_plain_ascii_is_only_lowercased(self):
        self.assertEqual(parse.fold("ABC def"), "abc def")

    def test_empty(self):
        self.assertEqual(parse.fold(""), "")

    def test_precomposed_and_decomposed_agree(self):
        self.assertEqual(parse.fold("é"), parse.fold("é"))


class TestCleanMarkup(unittest.TestCase):
    def test_removes_refs_including_multiline(self):
        self.assertEqual(parse.clean_markup("a<ref name=x>zz\nyy</ref>b"), "ab")

    def test_block_tags_become_spaces(self):
        self.assertEqual(parse.clean_markup("a<br/>b<div style='x'>c</div>d<span>e</span>"), "a b c d e")

    def test_wikilinks(self):
        self.assertEqual(parse.clean_markup("[[Target|shown]] and [[plain]]"), "shown and plain")

    def test_external_links_keep_label_and_url(self):
        self.assertEqual(parse.clean_markup("[http://x.org/y Link text]"), "Link text http://x.org/y")

    def test_bold_italic_templates_nbsp(self):
        self.assertEqual(parse.clean_markup("'''b''' ''i'' {{tmpl}}x&nbsp;y"), "b i x y")

    def test_collapses_whitespace_and_trims(self):
        self.assertEqual(parse.clean_markup("  a \n\t b  "), "a b")

    def test_idempotent_on_clean_text(self):
        self.assertEqual(parse.clean_markup("Plain text."), "Plain text.")


class TestLegend(unittest.TestCase):
    def test_parse_legend_rows(self):
        text = "intro\n| + || ''Open'' [[x|annotation]]\n|Φ|| duplicate\n| toolong || ignored\nfoo || bar"
        self.assertEqual(parse.parse_legend(text), {"+": "Open annotation", "Φ": "duplicate"})

    def test_parse_legend_empty(self):
        self.assertEqual(parse.parse_legend("no table here"), {})


class TestIsMarkerToken(unittest.TestCase):
    LEGEND = {"+": "x", "Φ": "y", "A": "letter key"}

    def test_symbols_only(self):
        self.assertTrue(parse.is_marker_token("*†", {}))
        self.assertTrue(parse.is_marker_token("+", {}))

    def test_greek_letters(self):
        self.assertTrue(parse.is_marker_token("α", {}))
        self.assertTrue(parse.is_marker_token("Φ+", self.LEGEND))

    def test_legend_key_that_is_alphanumeric(self):
        self.assertTrue(parse.is_marker_token("A", self.LEGEND))
        self.assertFalse(parse.is_marker_token("B", self.LEGEND))

    def test_words_are_not_markers(self):
        self.assertFalse(parse.is_marker_token("Abc", self.LEGEND))
        self.assertFalse(parse.is_marker_token("2020", self.LEGEND))

    def test_opening_quote_or_bracket_stops(self):
        for tok in ("(a", "“x", "‘x", '"x', "'x", "[x", "”", "’"):
            self.assertFalse(parse.is_marker_token(tok, self.LEGEND), tok)


class TestSplitCitation(unittest.TestCase):
    def test_leading_markers_are_split_off(self):
        self.assertEqual(parse.split_citation("Φ + Smith, J. 2020. T", {"+": "x"}),
                         (["Φ", "+"], "Smith, J. 2020. T"))

    def test_glued_marker_token_becomes_separate_chars(self):
        self.assertEqual(parse.split_citation("Φ+ Smith 2020", {}), (["Φ", "+"], "Smith 2020"))

    def test_no_marker(self):
        self.assertEqual(parse.split_citation("Smith J", {}), ([], "Smith J"))

    def test_lone_symbol_without_following_text_stays(self):
        self.assertEqual(parse.split_citation("+", {}), ([], "+"))

    def test_blank(self):
        self.assertEqual(parse.split_citation("   ", {}), ([], ""))

    def test_quote_after_marker_is_not_a_marker(self):
        self.assertEqual(parse.split_citation("+ “Title” 2020", {}), (["+"], "“Title” 2020"))


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

class TestParseNames(unittest.TestCase):
    def test_empty_and_whitespace(self):
        self.assertEqual(parse.parse_names(""), [])
        self.assertEqual(parse.parse_names("  ,  "), [])

    def test_single_token_is_returned_whole(self):
        self.assertEqual(parse.parse_names("Smith"), ["Smith"])

    def test_inverted_pair(self):
        self.assertEqual(parse.parse_names("Smith, John"), ["John Smith"])

    def test_first_inverted_then_natural_order(self):
        self.assertEqual(parse.parse_names("Smith, John, Jane Doe, and Lee Wu"),
                         ["John Smith", "Jane Doe", "Lee Wu"])

    def test_not_inverted_returns_tokens(self):
        self.assertEqual(parse.parse_names("John Smith and Jane Doe", inverted=False),
                         ["John Smith", "Jane Doe"])

    def test_et_al_removed(self):
        self.assertEqual(parse.parse_names("Smith, J. et al."), ["J. Smith"])
        self.assertEqual(parse.parse_names("Smith, John, et al"), ["John Smith"])

    def test_final_initial_keeps_its_full_stop(self):
        self.assertEqual(parse.parse_names("Brett D."), ["Brett D."])
        self.assertEqual(parse.parse_names("Smith, Brett D."), ["Brett D. Smith"])

    def test_trailing_full_stop_after_word_is_dropped(self):
        self.assertEqual(parse.parse_names("Smith, John."), ["John Smith"])

    def test_organisation_with_long_second_token(self):
        self.assertEqual(parse.parse_names("Council, of Canadian Academies Report Group"),
                         ["Council", "of Canadian Academies Report Group"])

    def test_organisation_with_function_word_in_first_token(self):
        self.assertEqual(parse.parse_names("Council of Canadian Academies, Ottawa"),
                         ["Council of Canadian Academies", "Ottawa"])

    def test_organisation_with_parenthesis_in_first_token(self):
        self.assertEqual(parse.parse_names("Library (UK), the"), ["Library (UK)", "the"])

    def test_and_the_tail_dropped_for_institutes(self):
        self.assertEqual(parse.parse_names("Foo Institute, and the Bar"), ["Foo Institute"])

    def test_and_the_tail_kept_without_institute_or_paren(self):
        self.assertEqual(parse.parse_names("A, and the B"), ["the B A"])

    def test_generational_suffix_joins_previous_name(self):
        self.assertEqual(parse.parse_names("Smith, John, Jr., Jane Doe"), ["John Smith Jr.", "Jane Doe"])
        self.assertEqual(parse.parse_names("Smith, John, III"), ["John Smith III"])

    def test_leading_and_removed_from_tokens(self):
        self.assertEqual(parse.parse_names("Smith, John and Jane Doe"), ["John Smith", "Jane Doe"])

    # Documented current behaviour (heuristic limitations), see the report.
    def test_current_behaviour_all_inverted_list_is_misread(self):
        self.assertEqual(parse.parse_names("Smith, John, and Doe, Jane"), ["John Smith", "Doe", "Jane"])

    def test_current_behaviour_final_period_of_jr_is_lost(self):
        self.assertEqual(parse.parse_names("Tennant, Jon, Jr."), ["Jon Tennant Jr"])


class TestSplitRoles(unittest.TestCase):
    def test_plain_authors(self):
        self.assertEqual(parse.split_roles("Smith, John"),
                         {"authors": ["John Smith"], "editors": [], "contributors": []})

    def test_trailing_punctuation_stripped(self):
        self.assertEqual(parse.split_roles("Smith, John.  ")["authors"], ["John Smith"])

    def test_final_initial_period_preserved(self):
        self.assertEqual(parse.split_roles("Brett D.")["authors"], ["Brett D."])

    def test_editor_forms(self):
        for s in ("Smith, John (ed.)", "Smith, John, eds.", "Smith, John, editor", "Smith, John (Eds)"):
            r = parse.split_roles(s)
            self.assertEqual(r["authors"], [], s)
            self.assertEqual(r["editors"], ["John Smith"], s)

    def test_with_contributors(self):
        r = parse.split_roles("Smith, John, with Jane Doe and Bob Roe")
        self.assertEqual(r, {"authors": ["John Smith"], "editors": [],
                             "contributors": ["Jane Doe", "Bob Roe"]})

    def test_with_the_prefix_stripped(self):
        r = parse.split_roles("Smith, John, with the Team")
        self.assertEqual(r["contributors"], ["Team"])

    def test_with_lowercase_word_is_not_contributor_marker(self):
        r = parse.split_roles("Working with data")
        self.assertEqual(r["contributors"], [])

    def test_collective_author_after_and_the(self):
        r = parse.split_roles("Smith, John, and the INKE and ETCL Research Groups")
        self.assertEqual(r["authors"], ["John Smith", "INKE and ETCL Research Groups"])

    def test_markup_is_cleaned(self):
        self.assertEqual(parse.split_roles("'''Smith, John'''")["authors"], ["John Smith"])

    def test_empty(self):
        self.assertEqual(parse.split_roles(""), {"authors": [], "editors": [], "contributors": []})


class TestContainerEditors(unittest.TestCase):
    def test_none(self):
        self.assertEqual(parse.container_editors("Journal 3 (2): 5"), [])

    def test_two_names_then_pages(self):
        self.assertEqual(parse.container_editors("In X, edited by A B and C D, pp. 5-9"), ["A B", "C D"])

    def test_cut_at_year_parenthesis(self):
        self.assertEqual(parse.container_editors("edited by A, B, and C (2020)"), ["A", "B", "C"])

    def test_cut_at_number(self):
        self.assertEqual(parse.container_editors("In Y, edited by Jane Doe, 12"), ["Jane Doe"])

    def test_cut_at_full_stop_after_word(self):
        self.assertEqual(parse.container_editors("edited by J. Smith. Pub"), ["J. Smith"])

    def test_case_insensitive(self):
        self.assertEqual(parse.container_editors("Edited By Ann Lee"), ["Ann Lee"])

    def test_volume_marker_cut(self):
        self.assertEqual(parse.container_editors("edited by Ann Lee, vol. 2"), ["Ann Lee"])


class TestNameCanonicalisation(unittest.TestCase):
    def test_fix_initials(self):
        self.assertEqual(parse.fix_initials("Brett D Hirsch"), "Brett D. Hirsch")
        self.assertEqual(parse.fix_initials("A"), "A.")
        self.assertEqual(parse.fix_initials("A B Smith"), "A. B. Smith")

    def test_fix_initials_leaves_other_names(self):
        self.assertEqual(parse.fix_initials("Brett D. Hirsch"), "Brett D. Hirsch")
        self.assertEqual(parse.fix_initials("ABC Smith"), "ABC Smith")

    def test_canonical_name_applies_alias_and_counts(self):
        used = {}
        alias = {"Ray Siemens": "Raymond G. Siemens"}
        self.assertEqual(parse.canonical_name("Ray Siemens", alias, used), "Raymond G. Siemens")
        self.assertEqual(parse.canonical_name("Ray Siemens", alias, used), "Raymond G. Siemens")
        self.assertEqual(used, {"Ray Siemens": 2})

    def test_canonical_name_without_alias(self):
        used = {}
        self.assertEqual(parse.canonical_name("Jane Doe", {}, used), "Jane Doe")
        self.assertEqual(used, {})

    def test_canonical_name_fixes_initials_before_lookup(self):
        used = {}
        alias = {"D. Butin": "Dan W. Butin"}
        self.assertEqual(parse.canonical_name("D Butin", alias, used), "Dan W. Butin")
        self.assertEqual(used, {"D. Butin": 1})


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

class TestSplitAuthorsRest(unittest.TestCase):
    def test_title_first_with_curly_quote(self):
        self.assertEqual(parse.split_authors_rest("“T” 2019. foo"), ("", "2019", "“T” 2019. foo"))

    def test_title_first_straight_quote_without_year(self):
        self.assertEqual(parse.split_authors_rest('"T" foo'), ("", "n.d.", '"T" foo'))

    def test_title_first_italic_uses_last_year(self):
        self.assertEqual(parse.split_authors_rest("''T'' 1999, reprinted 2004. x"),
                         ("", "2004", "''T'' 1999, reprinted 2004. x"))

    def test_apa_year_in_parentheses(self):
        self.assertEqual(parse.split_authors_rest("Smith, John. (2011). Title. Press."),
                         ("Smith, John", "2011", "Title. Press."))

    def test_apa_year_with_letter_and_no_full_stop(self):
        self.assertEqual(parse.split_authors_rest("Smith, John (2011a). Title."),
                         ("Smith, John", "2011a", "Title."))

    def test_apa_n_d(self):
        self.assertEqual(parse.split_authors_rest("Smith, John (n.d.). Title."),
                         ("Smith, John", "n.d.", "Title."))

    def test_apa_rejected_when_authors_contain_title_quote(self):
        a, y, rest = parse.split_authors_rest("The “thing” here (2020). Rest of it.")
        self.assertNotEqual(a, "The “thing” here")

    def test_chicago_year_after_full_stop(self):
        self.assertEqual(parse.split_authors_rest("Smith, John. 2019. Title here. Press."),
                         ("Smith, John", "2019", "Title here. Press."))

    def test_chicago_skips_year_not_preceded_by_full_stop(self):
        a, y, rest = parse.split_authors_rest("Smith, John 2018 and then. 2019. Title")
        self.assertEqual((a, y, rest), ("Smith, John 2018 and then", "2019", "Title"))

    def test_mla_like_first_sentence_boundary_before_quote(self):
        a, y, rest = parse.split_authors_rest("Doe, Jane. “Title.” Site.")
        self.assertEqual((a, y), ("Doe, Jane", "n.d."))
        self.assertEqual(rest, "“Title.” Site.")

    def test_mla_like_boundary_before_capital(self):
        a, y, rest = parse.split_authors_rest("Council. The Title of a Thing. Pub 2020, more.")
        self.assertEqual((a, y, rest), ("Council", "2020", "The Title of a Thing. Pub 2020, more."))

    def test_no_boundary_at_all(self):
        self.assertEqual(parse.split_authors_rest("x"), ("x", "n.d.", ""))

    def test_no_boundary_with_year(self):
        self.assertEqual(parse.split_authors_rest("something 2001 else"), ("something 2001 else", "2001", ""))


class TestParseCitation(unittest.TestCase):
    def test_chicago_journal_article_with_doi_url(self):
        c = parse.parse_citation(
            "Arbuckle, Alyssa, and John Maxwell. 2019. “Modelling Open Social Scholarship.” "
            "''KULA: Knowledge'' 3 (February): 2. https://doi.org/10.5334/kula.15")
        self.assertEqual(c["authors"], ["Alyssa Arbuckle", "John Maxwell"])
        self.assertEqual(c["authors_raw"], "Arbuckle, Alyssa, and John Maxwell")
        self.assertEqual(c["year"], 2019)
        self.assertEqual(c["year_label"], "2019")
        self.assertEqual(c["title"], "Modelling Open Social Scholarship")
        self.assertEqual(c["container"], "KULA: Knowledge 3 (February): 2")
        self.assertEqual(c["doi"], "10.5334/kula.15")
        self.assertEqual(c["url"], "https://doi.org/10.5334/kula.15")
        self.assertEqual(c["kind"], "Journal article")
        self.assertEqual((c["editors"], c["contributors"], c["container_editors"]), ([], [], []))

    def test_apa_author_year_in_parentheses_book_or_report(self):
        c = parse.parse_citation("Smith, John. (2011). Productivity through innovation: Applying it. "
                                 "Ottawa: Press. https://x.org/a.")
        self.assertEqual(c["authors"], ["John Smith"])
        self.assertEqual(c["year"], 2011)
        self.assertEqual(c["title"], "Productivity through innovation: Applying it")
        self.assertEqual(c["container"], "Ottawa: Press")
        self.assertEqual(c["url"], "https://x.org/a")
        self.assertEqual(c["doi"], "")
        self.assertEqual(c["kind"], "Book or report")

    def test_apa_year_suffix_letter(self):
        c = parse.parse_citation("Smith, John (2011a). Productivity through innovation. Press.")
        self.assertEqual((c["year"], c["year_label"]), (2011, "2011a"))

    def test_italic_title_after_chicago_year(self):
        c = parse.parse_citation("Smith, John. 2018b. ''A Big Book.'' Toronto: UTP.")
        self.assertEqual(c["title"], "A Big Book")
        self.assertEqual(c["container"], "Toronto: UTP")
        self.assertEqual(c["kind"], "Book or report")

    def test_italic_title_first_without_author(self):
        c = parse.parse_citation("''Some Title''. 2019. Press.")
        self.assertEqual(c["authors"], [])
        self.assertEqual(c["authors_raw"], "")
        self.assertEqual(c["title"], "Some Title")
        self.assertEqual(c["year"], 2019)
        self.assertEqual(c["kind"], "Book or report")

    def test_quoted_title_first_without_author(self):
        c = parse.parse_citation("“Untitled Thing.” 2020. Online. https://www.Example.org/p/")
        self.assertEqual(c["authors"], [])
        self.assertEqual(c["title"], "Untitled Thing")
        self.assertEqual(c["url"], "https://www.Example.org/p/")
        # The year sits in the container, which counts as a digit: current classification.
        self.assertEqual(c["kind"], "Journal article")

    def test_undated_with_url_is_web_resource(self):
        c = parse.parse_citation("Doe, Jane. n.d. “Web page.” https://x.org/y.")
        self.assertIsNone(c["year"])
        self.assertEqual(c["year_label"], "n.d.")
        self.assertEqual(c["kind"], "Report or web resource")
        self.assertEqual(c["url"], "https://x.org/y")
        self.assertEqual(c["container"], "")

    def test_undated_mla_like_quoted_title(self):
        c = parse.parse_citation("Doe, Jane. “Web page.” Site. https://x.org/y")
        self.assertEqual((c["authors"], c["title"], c["container"], c["year_label"]),
                         (["Jane Doe"], "Web page", "Site", "n.d."))

    def test_editors_of_the_work_and_container_editors_and_dash_in_doi(self):
        c = parse.parse_citation("Doe, Jane, ed. 2020. “Chapter.” In ''Big Book'', edited by A B and C D, "
                                 "5-9. Pub. doi 10.1234/abc–def.")
        self.assertEqual(c["authors"], [])
        self.assertEqual(c["editors"], ["Jane Doe"])
        self.assertEqual(c["container_editors"], ["A B", "C D"])
        self.assertEqual(c["kind"], "Book chapter")
        self.assertEqual(c["doi"], "10.1234/abc-def")
        self.assertEqual(c["url"], "")

    def test_with_contributors_and_doi_url_dash_normalised(self):
        c = parse.parse_citation("Doe, Jane, with Bob Roe. 2020. “Chapter.” Report. "
                                 "https://doi.org/10.1234/abc–def.")
        self.assertEqual(c["authors"], ["Jane Doe"])
        self.assertEqual(c["contributors"], ["Bob Roe"])
        self.assertEqual(c["url"], "https://doi.org/10.1234/abc-def")
        self.assertEqual(c["doi"], "10.1234/abc-def")
        self.assertEqual(c["kind"], "Report or web resource")  # "Report" prefix wins over digits? no digits here

    def test_non_doi_url_dash_is_untouched(self):
        c = parse.parse_citation("Doe, Jane. 2020. “T.” Site. https://example.org/a–b")
        self.assertEqual(c["url"], "https://example.org/a–b")

    def test_organisation_author(self):
        c = parse.parse_citation("Canadian Association of Research Libraries. 2020. “Policy brief.” Working Paper 5. "
                                 "http://x.org/p")
        self.assertEqual(c["authors"], ["Canadian Association of Research Libraries"])
        self.assertEqual(c["kind"], "Report or web resource")

    def test_et_al(self):
        c = parse.parse_citation("Doe, Jane, et al. 2020. “Findings.” Journal 3 (2): 5.")
        self.assertEqual(c["authors"], ["Jane Doe"])
        self.assertEqual(c["kind"], "Journal article")

    def test_book_chapter_detected_by_in(self):
        c = parse.parse_citation("Doe, Jane. 2020. “Chapter.” In ''Book'', 12-20. Pub.")
        self.assertEqual(c["kind"], "Book chapter")

    def test_journal_vs_report_prefix_with_digits(self):
        c = parse.parse_citation("Doe, Jane. 2020. “T.” Policy Brief 5. Pub.")
        self.assertEqual(c["kind"], "Report or web resource")
        c = parse.parse_citation("Doe, Jane. 2020. “T.” Journal of X 5. Pub.")
        self.assertEqual(c["kind"], "Journal article")

    def test_quoted_title_without_digits_in_container_is_report(self):
        c = parse.parse_citation("Doe, Jane. 2020. “T.” Some Site.")
        self.assertEqual(c["kind"], "Report or web resource")

    def test_plain_title_uses_first_sentence(self):
        c = parse.parse_citation("Lee, Sam. 2019. Plain title here. Publisher Name.")
        self.assertEqual((c["title"], c["container"]), ("Plain title here", "Publisher Name"))

    def test_bare_text_has_no_title(self):
        c = parse.parse_citation("just some words without anything")
        self.assertEqual(c["authors"], ["just some words without anything"])
        self.assertEqual(c["title"], "")
        self.assertEqual(c["kind"], "Report or web resource")

    def test_inner_quotes_fold_back_into_title(self):
        # Current behaviour: the early-closing title absorbs the remainder; a stray quote stays in the title.
        c = parse.parse_citation("Doe, Jane, et al. 2020. “He said “hi” to me.” Journal 3 (2): 5.")
        self.assertEqual(c["title"], "He said “hi to me")
        self.assertEqual(c["container"], "Journal 3 (2): 5")

    def test_fold_back_skipped_for_in_container(self):
        c = parse.parse_citation("Doe, Jane. 2020. “Title.” In ''Book \"Q\"'', 5-6.")
        self.assertEqual(c["title"], "Title")
        self.assertTrue(c["container"].startswith("In Book"))

    def test_doi_trailing_punctuation_stripped(self):
        c = parse.parse_citation("Doe, Jane. 2020. “T.” Journal 1. doi:10.1234/xyz.")
        self.assertEqual(c["doi"], "10.1234/xyz")

    def test_year_label_only_year_int(self):
        c = parse.parse_citation("Doe, Jane. 2020a. “T.” Journal 1.")
        self.assertEqual((c["year"], c["year_label"]), (2020, "2020a"))

    def test_return_keys(self):
        c = parse.parse_citation("Doe, Jane. 2020. “T.” Journal 1.")
        self.assertEqual(sorted(c), sorted([
            "authors_raw", "authors", "editors", "contributors", "container_editors", "year", "year_label",
            "title", "container", "url", "doi", "kind"]))


# ---------------------------------------------------------------------------
# Page parsing
# ---------------------------------------------------------------------------

PAGE = """==Top==
===Sub===
{{anchor|x}}'''Smith, John. 2020. “A fairly long title for an article here.” ''Journal'' 3 (2): 5. https://doi.org/10.1234/abc'''
<div style="x">
:First para of annotation.
:Second ''para''.
</div>

'''+ Lee, Sam. 2019. ''Another long book title goes here for length''. Press.'''
Plain text annotation unindented.
'''Bold: not a citation line in annotation'''
'''Dup, Entry 2018'''  ([[Other page#x|see there]]) cross reference
'''Short 2020'''
'''A heading-ish line with a year 2020 but ends with a colon long enough:'''
==Next==
Stray text before any entry in this section is ignored.
'''Orphan, Au. 2001. Title with url http://x.org/very/long/path/here/yes.'''
"""


class TestParsePage(unittest.TestCase):
    def setUp(self):
        parse.xrefs[0] = 0
        self.anomalies = []

    def parse(self, text, legend=None):
        return parse.parse_page(text, legend or {"+": "marker"}, "Vol", "Chap", self.anomalies, "Page Title")

    def test_entries_found_with_annotations_and_sections(self):
        es = self.parse(PAGE)
        self.assertEqual(len(es), 3)
        a, b, c = es
        self.assertEqual(a["authors"], ["John Smith"])
        self.assertEqual(a["annotation"], "First para of annotation. Second para.")
        self.assertEqual(a["sections"], ["Top", "Sub"])
        self.assertEqual((a["volume"], a["chapter"]), ("Vol", "Chap"))
        self.assertEqual(a["marker"], [])
        self.assertNotIn("_ann", a)
        self.assertEqual(b["marker"], ["+"])
        self.assertEqual(b["sections"], ["Top", "Sub"])
        self.assertEqual(c["sections"], ["Next"])  # level-2 heading replaces the whole stack
        self.assertEqual(c["annotation"], "")
        self.assertEqual(c["url"], "http://x.org/very/long/path/here/yes")

    def test_bold_lines_inside_annotation_are_reported_not_started_as_entries(self):
        es = self.parse(PAGE)
        self.assertEqual([x["type"] for x in self.anomalies], ["bold-line-in-annotation"] * 2 + ["bold-line-in-annotation"])
        texts = [x["text"] for x in self.anomalies]
        self.assertIn("'''Bold: not a citation line in annotation'''", texts)
        self.assertIn("'''Short 2020'''", texts)
        self.assertTrue(all(x["page"] == "Page Title" for x in self.anomalies))
        self.assertIn("Bold: not a citation line in annotation", es[1]["annotation"])
        self.assertIn("Short 2020", es[1]["annotation"])

    def test_cross_reference_lines_skipped_and_counted(self):
        es = self.parse(PAGE)
        self.assertEqual(parse.xrefs[0], 1)
        self.assertFalse(any("Dup, Entry" in e["citation_raw"] for e in es))

    def test_entry_detection_rules(self):
        long_title = "x" * 41
        cases = {
            "year": f"'''Name, A. {long_title} 2020, thing'''",
            "curly quote": f"'''Name, A. {long_title} “quoted”'''",
            "http": f"'''Name, A. {long_title} http://x.org'''",
        }
        for label, line in cases.items():
            self.assertEqual(len(self.parse(line)), 1, label)
        rejected = {
            "too short": "'''Short 2020 text'''",
            "no year quote or http": f"'''Name, A. {long_title} nothing'''",
            "ends with colon": f"'''Name, A. {long_title} 2020:'''",
            "not wrapped in bold": f"Name, A. {long_title} 2020",
            "heading year only after text": f"'''{long_title}'''",
        }
        for label, line in rejected.items():
            self.assertEqual(self.parse(line), [], label)

    def test_div_wrapper_and_anchor_are_removed(self):
        line = "<div>{{anchor|a}}'''Name, A. " + "x" * 41 + " 2020, thing'''</div>"
        self.assertEqual(len(self.parse(line)), 1)

    def test_annotation_ignores_blank_and_closing_div_lines(self):
        es = self.parse("'''Name, A. " + "x" * 41 + " 2020, thing'''\n\n</div>\n:text\n</div>")
        self.assertEqual(es[0]["annotation"], "text")

    def test_headings_stack_and_pop(self):
        es = self.parse("==A==\n===B===\n==C==\n====D====\n'''Name, A. " + "x" * 41 + " 2020, thing'''")
        self.assertEqual(es[0]["sections"], ["C", "D"])

    def test_heading_flushes_current_entry(self):
        es = self.parse("'''Name, A. " + "x" * 41 + " 2020, thing'''\n:note\n==H==\n:later text")
        self.assertEqual(es[0]["annotation"], "note")

    def test_lone_equals_line_is_not_a_heading(self):
        self.assertEqual(self.parse("= H ="), [])

    def test_unparsed_citation_is_reported_and_skipped(self):
        # parse_citation never returns a falsy value today; this guards the defensive branch.
        with mock.patch.object(parse, "parse_citation", return_value=None):
            es = self.parse("'''Name, A. " + "x" * 41 + " 2020, thing'''\n:ignored")
        self.assertEqual(es, [])
        self.assertEqual(self.anomalies[0]["type"], "unparsed-citation")
        self.assertEqual(self.anomalies[0]["page"], "Page Title")

    def test_marker_not_in_legend_but_symbol_still_split(self):
        es = self.parse("'''Φ Name, A. " + "x" * 41 + " 2020, thing'''", legend={})
        self.assertEqual(es[0]["marker"], ["Φ"])


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------

def entry(**kw):
    base = {"doi": "", "url": "", "authors": [], "editors": [], "year": 2020, "title": "A Title"}
    base.update(kw)
    return base


class TestIdentifiers(unittest.TestCase):
    def test_item_id_is_ten_hex(self):
        self.assertRegex(parse.item_id(entry()), r"^[0-9a-f]{10}$")

    def test_item_id_known_values_are_stable(self):
        self.assertEqual(parse.item_id(entry(doi="10.1/ABC", title="t", year=1)), "3b342fbc3b")
        self.assertEqual(parse.item_id(entry(editors=["É Z"], title="Ti", year=2000)), "c36ff6c72f")
        self.assertEqual(parse.item_id(entry(year=None, title="")), "baed70fad3")

    def test_doi_identity_ignores_case_and_other_fields(self):
        a = parse.item_id(entry(doi="10.1234/ABC", title="One"))
        b = parse.item_id(entry(doi="10.1234/abc", title="Two", authors=["X"]))
        self.assertEqual(a, b)

    def test_author_accents_and_case_are_folded(self):
        a = parse.item_id(entry(authors=["Émile Zola"]))
        b = parse.item_id(entry(authors=["emile zola"]))
        self.assertEqual(a, b)

    def test_editors_used_when_no_authors(self):
        a = parse.item_id(entry(editors=["Ed Itor"]))
        b = parse.item_id(entry(authors=["Ed Itor"]))
        self.assertEqual(a, b)

    def test_year_and_title_matter(self):
        self.assertNotEqual(parse.item_id(entry(year=2020)), parse.item_id(entry(year=2021)))
        self.assertNotEqual(parse.item_id(entry(title="A")), parse.item_id(entry(title="B")))

    def test_title_truncated_to_80_characters(self):
        t = "a" * 80
        self.assertEqual(parse.item_id(entry(title=t + "X")), parse.item_id(entry(title=t + "Y")))


class TestNormKey(unittest.TestCase):
    def test_doi_wins_and_is_lowercased_and_stripped_of_trailing_slash(self):
        self.assertEqual(parse.norm_key(entry(doi="10.1/A/", url="http://x")), "doi:10.1/a")

    def test_url_normalised(self):
        self.assertEqual(parse.norm_key(entry(url="HTTPS://www.X.org/a/")), "url:x.org/a")
        self.assertEqual(parse.norm_key(entry(url="http://x.org/a")), "url:x.org/a")

    def test_title_year_fallback(self):
        self.assertEqual(parse.norm_key(entry(title="Héllo, World!", year=2020)), "t:helloworld2020")

    def test_title_part_truncated_to_70(self):
        k = parse.norm_key(entry(title="a" * 100, year=None))
        self.assertEqual(k, "t:" + "a" * 70 + "None")


class TestSlugify(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(parse.slugify("Engaging Knowledge Diversity!"), "engaging-knowledge-diversity")
        self.assertEqual(parse.slugify("  École -- Test  "), "ecole-test")
        self.assertEqual(parse.slugify("!!!"), "")


class TestLexicon(unittest.TestCase):
    SAMPLES = {
        "Open access": "Green OA routes",
        "Open data": "the FAIR principles",
        "Open education": "OER adoption",
        "Digital humanities": "DH projects",
        "Scholarly communication": "scholarly publishing",
        "Peer review": "open peer review",
        "Libraries and repositories": "an institutional repository",
        "Policy and funders": "funder mandates",
        "Infrastructure": "research infrastructure",
        "Metrics and evaluation": "altmetrics and tenure",
        "Copyright and licensing": "Creative Commons licence",
        "Community engagement": "citizen science",
        "Knowledge mobilization": "knowledge mobilisation",
        "Indigenous knowledges": "First Nations",
        "Equity and diversity": "marginalised voices",
        "Multilingualism": "bibliodiversity",
        "Platforms and social media": "ResearchGate",
        "Training and pedagogy": "curriculum design",
        "Collaboration": "co-creation",
        "Social knowledge creation": "social knowledge creation",
        "Artificial intelligence": "AI tools",
        "Open source and tools": "open-source software",
        "Sustainability and labour": "unpaid labor",
        "Governance and regulation": "antitrust law",
    }

    def test_every_topic_has_a_sample_and_matches(self):
        self.assertEqual(set(self.SAMPLES), set(parse.LEXICON))
        self.assertEqual(set(parse.LEXICON_RE), set(parse.LEXICON))
        for topic, text in self.SAMPLES.items():
            self.assertRegex(text, parse.LEXICON_RE[topic], topic)

    def test_samples_do_not_match_unrelated_topics_wholesale(self):
        self.assertIsNone(parse.LEXICON_RE["Artificial intelligence"].search("said air"))
        self.assertIsNone(parse.LEXICON_RE["Open access"].search("boat"))

    def test_regexes_are_case_insensitive(self):
        self.assertTrue(parse.LEXICON_RE["Peer review"].search("PEER REVIEW"))


# ---------------------------------------------------------------------------
# main(): synthetic wiki snapshot
# ---------------------------------------------------------------------------

def bold(cit):
    return "'''" + cit + "'''\n"


def ann(text):
    return "<div style=\"x\">\n:" + text + "\n</div>\n\n"


ALPHA_INTRO = "Intro text\n{|\n| + || Annotation by the Alpha team\n|-\n| Φ || Duplicate entry\n|}\n"

ALPHA_LIST = (
    "* Smith, John, and Jane Doe. 2020. Open Access and Policy in Libraries. Journal of Open.\n"
    "* Too short 2020\n"
    "* A line that is long enough to count but carries no year at all in it\n"
    "Not a bullet line even though it is long and mentions 2020 and so on and so on\n"
)

ALPHA_ONE = (
    "==Section One==\n"
    + bold("+ Smith, John, and Jane Doe. 2020. “Open Access and Policy in Libraries.” ''Journal of Open'' 3 (2): 5. "
           "https://doi.org/10.1234/abc.def")
    + ann("Discusses open access mandates and funder policy for institutional repositories.")
    + bold("Siemens, Ray, and Raymond Siemens. 2019. “Social Knowledge Creation and Training.” ''Digital Journal'' 4 (1): 1. "
           "https://example.org/a")
    + ann("Short.")
    + bold("Lee, Sam. 2018. “A Sufficiently Long Title Here For Matching.” Report. http://a.org/x")
    + ann("Short note.")
    + bold("Kim, Pat. 2015. “Url Dup One.” Site. https://www.Example.org/page/")
    + ann("First annotation.")
    + bold("Dawkins, “The Necessity of Public Humanities” (research poster) 2019. http://poster.example.org/dawkins")
    + ann("A poster.")
    + bold("“An Untitled Orphan Report That Needs An Author.” 2021. Org Name. http://orphan.example.org/report")
    + ann("Recoverable.")
    + bold("Shared, Tit. 2014. “Same Id Title.” Pub 1. http://same.example.org/one")
    + ann("One.")
    + bold("Shared, Tit. 2014. “Same Id Title.” Pub 1. http://same.example.org/two")
    + ann("Two.")
    + bold("Sister, Name. 2013. “Entry With No Annotation At All Here.” Pub 2. http://noann.example.org/q")
)

ALPHA_TWO = (
    "==Section Two==\n"
    # identical citation text to the first Alpha entry, filed again in another chapter
    + bold("Smith, John, and Jane Doe. 2020. “Open Access and Policy in Libraries.” ''Journal of Open'' 3 (2): 5. "
           "https://doi.org/10.1234/abc.def")
    + ann("A")
    + bold("Bad, Role. 2010. “Bad role entry for anomaly checks.” Pub 1. http://bad.example.org/1")
    + ann("Bad.")
    + bold("Notitle, Ann. 2011. “Entry whose title is blanked by a correction.” Pub 1. http://nt.example.org/1")
    + ann("Blank.")
    + bold("Noyear, Bob. 2012. “Entry whose year is blanked by a correction.” Pub 1. http://ny.example.org/1")
    + ann("Blank.")
    + bold("Baddoi, Cy. 2016. “Entry with a malformed DOI set by a correction.” Pub 1. http://bd.example.org/1")
    + ann("Doi.")
)

BETA_THREE = (
    "==Beta Section==\n"
    + bold("Φ Lee, Sam, and Pat Kim. 2018. “A Sufficiently Long Title Here For Matching.” Report. http://b.org/y")
    + ann("A much longer annotation than the earlier one, mentioning peer review and the Indigenous perspective.")
    + bold("Smith, John, with Bob Roe. 2020. “Open Access and Policy in Libraries.” ''Journal of Open'' 3 (2): 5. "
           "https://doi.org/10.1234/ABC.DEF")
    + ann("Short.")
    + bold("Kim, Pat. 2015. “Another Title Entirely.” Site. http://example.org/page")
    + ann("Second.")
    + bold("Smith, John, with Bob Roe and Cy Poe. 2020. “Open Access and Policy in Libraries.” "
           "''Journal of Open'' 3 (2): 5. https://doi.org/10.1234/abc.def")
    + ann("More contributors.")
    + bold("Parent, Ann, editor. 2017. “Chapter In Book.” In ''The Book'', edited by Zed Zed, 5-9. Pub. http://ed.example.org/c")
    + ann("Edited.")
)

CORRECTIONS = [
    {"match": "Dawkins, “The Necessity of Public Humanities”",
     "set": {"authors": ["Dawkins"], "title": "The Necessity of Public Humanities", "container": "Research poster"},
     "reason": "Synthetic correction."},
    {"match": "Bad role entry",
     "set": {"authors": ["Ann Lee, ed."], "editors": ["Editors"], "contributors": ["Jo 2020"],
             "container_editors": ["Q Φ"]},
     "reason": "Force name contamination."},
    {"match": "title is blanked", "set": {"title": ""}, "reason": "Force missing title."},
    {"match": "year is blanked", "set": {"year": None, "year_label": "2012x"}, "reason": "Force missing year."},
    {"match": "malformed DOI",
     "set": {"doi": "11.bad/x", "url": "https://doi.org/10/zz"}, "reason": "Force malformed DOIs."},
    {"match": "THIS MATCHES NOTHING", "set": {"title": "x"}, "reason": "Stale on purpose."},
]

VARIANTS = [
    {"name": "Raymond G. Siemens", "variants": ["Ray Siemens", "Raymond Siemens"], "reason": "Same person."},
    {"name": "Nobody Real", "variants": ["Nobody Here"], "reason": "Stale on purpose."},
]

RECOVERIES = [
    {"match": "An Untitled Orphan Report", "authors": ["Orphan Org"], "contributors": ["Helper One", "Helper One"],
     "basis": "organisation", "evidence": "http://orphan.example.org/about", "checked": "2026-01-01", "note": "Seen."},
    {"match": "Open Access and Policy in Libraries", "authors": ["Should Not Apply"], "contributors": [],
     "basis": "x", "evidence": "x", "checked": "x", "note": "x"},  # item already has authors
    {"match": "NO SUCH CITATION", "authors": ["Nobody"], "contributors": [],
     "basis": "x", "evidence": "x", "checked": "x", "note": "x"},
]


def make_pages(volumes):
    """volumes: list of (slug, title, root, {suffix: text}); returns a pages.json structure."""
    pages, vols = {}, []
    stamp = 0
    for slug, title, root, chapters in volumes:
        titles = [root]
        pages[root] = {"revid": 1, "timestamp": "2020-01-01T00:00:00Z", "text": "root"}
        for suffix, text in chapters.items():
            t = root + "/" + suffix
            titles.append(t)
            stamp += 1
            pages[t] = {"revid": 100 + stamp, "timestamp": "2021-0%d-01T00:00:00Z" % stamp, "text": text}
        vols.append({"slug": slug, "title": title, "root": root, "titles": titles})
    return {"fetched": "2026-01-02", "rights": {"url": "u", "text": "t"}, "volumes": vols, "pages": pages}


def synthetic_raw():
    return make_pages([
        ("alpha", "Alpha Volume", "Alpha Vol", {
            "Introduction": ALPHA_INTRO,
            "Abstract": "abstract text",
            "Complete Alphabetical List of References": ALPHA_LIST,
            "Chapter One": ALPHA_ONE,
            "Chapter Two": ALPHA_TWO,
        }),
        ("beta", "Beta Volume", "Beta Vol", {"Chapter Three": BETA_THREE}),
    ])


class MainCase(unittest.TestCase):
    """Base class: write a snapshot into a temp dir, patch parse.HERE and run main()."""

    raw = None
    corrections = None
    variants = None
    recoveries = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osp-parse-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patcher = mock.patch.object(parse, "HERE", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        parse.xrefs[0] = 0

    def write(self, raw, corrections, variants, recoveries):
        os.makedirs(os.path.join(self.tmp, "raw"), exist_ok=True)
        for rel, data in (("raw/pages.json", raw), ("corrections.json", corrections),
                          ("name_variants.json", variants), ("recovered_authors.json", recoveries)):
            with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            parse.main()
        with open(os.path.join(self.tmp, "dataset.json"), encoding="utf-8") as f:
            self.dataset = json.load(f)
        with open(os.path.join(self.tmp, "validation.json"), encoding="utf-8") as f:
            self.validation = json.load(f)
        self.stdout = out.getvalue()
        return self.dataset, self.validation

    def item(self, needle):
        hits = [i for i in self.dataset["items"] if needle in i["citation"]]
        self.assertEqual(len(hits), 1, "expected exactly one item for %r, got %d" % (needle, len(hits)))
        return hits[0]

    def anomalies(self, typ):
        return [a for a in self.validation["anomalies"] if a["type"] == typ]


class TestMainSynthetic(MainCase):
    def setUp(self):
        super().setUp()
        self.write(synthetic_raw(), copy.deepcopy(CORRECTIONS), copy.deepcopy(VARIANTS), copy.deepcopy(RECOVERIES))
        self.run_main()

    def test_outputs_only_in_temp_dir(self):
        self.assertEqual(sorted(os.listdir(self.tmp)),
                         ["corrections.json", "dataset.json", "name_variants.json", "raw",
                          "recovered_authors.json", "validation.json"])

    def test_stdout_summary(self):
        self.assertIn("cross-reference lines skipped: 0", self.stdout)
        self.assertRegex(self.stdout, r"\d+ raw entries; \d+ unique items; \d+ anomalies")

    def test_meta_counts_and_provenance(self):
        meta = self.dataset["meta"]
        self.assertEqual(meta["volume_count"], 2)
        self.assertEqual(meta["raw_entries"], 19)
        self.assertEqual(meta["unique_items"], len(self.dataset["items"]))
        self.assertEqual(meta["source_fetched"], "2026-01-02")
        self.assertEqual(meta["licence"], {"url": "u", "text": "t"})
        self.assertEqual(self.dataset["lexicon"], parse.LEXICON)

    def test_volumes_meta(self):
        a, b = self.dataset["volumes"]
        self.assertEqual((a["slug"], a["title"], a["entries"]), ("alpha", "Alpha Volume", 14))
        self.assertEqual((b["slug"], b["entries"]), ("beta", 5))
        self.assertEqual(a["wiki_url"], "https://en.wikibooks.org/wiki/Alpha_Vol")
        self.assertEqual(a["legend"], {"+": "Annotation by the Alpha team", "Φ": "Duplicate entry"})
        self.assertEqual(b["legend"], {})
        self.assertEqual(a["latest_revision"], "2021-05-01T00:00:00Z")
        self.assertEqual(b["latest_revision"], "2021-06-01T00:00:00Z")
        self.assertEqual(a["revision_ids"]["Alpha Vol"], 1)
        self.assertEqual(len(a["revision_ids"]), 6)

    def test_validation_per_volume_and_info(self):
        self.assertEqual(self.validation["per_volume"]["alpha"], {"parsed": 14, "reference_lines_in_list_page": 1})
        self.assertEqual(self.validation["per_volume"]["beta"], {"parsed": 5, "reference_lines_in_list_page": 0})
        self.assertEqual(self.validation["info"]["cross_reference_lines_skipped"], 0)
        # only the orphan item had no author, and the recovery gave it one
        self.assertEqual(self.validation["info"]["items_without_named_author"], 0)

    def test_special_chapters_not_parsed_as_entries(self):
        for it in self.dataset["items"]:
            self.assertNotIn("Introduction", it["chapters"])
            self.assertNotIn("Abstract", it["chapters"])
        self.assertEqual({c for it in self.dataset["items"] for c in it["chapters"]},
                         {"Chapter One", "Chapter Two", "Chapter Three"})

    # -- corrections -------------------------------------------------------

    def test_correction_applied(self):
        it = self.item("Dawkins, “The Necessity of Public Humanities”")
        self.assertEqual(it["authors"], ["Dawkins"])
        self.assertEqual(it["title"], "The Necessity of Public Humanities")
        self.assertEqual(it["container"], "Research poster")

    def test_corrections_recorded_in_meta_with_counts(self):
        counts = {c["match"]: c["applied"] for c in self.dataset["meta"]["corrections"]}
        self.assertEqual(counts["Bad role entry"], 1)
        self.assertEqual(counts["THIS MATCHES NOTHING"], 0)
        self.assertEqual(len(self.dataset["meta"]["corrections"]), len(CORRECTIONS))
        self.assertEqual(self.dataset["meta"]["corrections"][0]["reason"], "Synthetic correction.")

    def test_stale_correction_reported_so_build_stops(self):
        self.assertEqual(self.anomalies("stale-correction"), [{"type": "stale-correction", "text": "THIS MATCHES NOTHING"}])

    # -- name variants -----------------------------------------------------

    def test_name_variants_applied_and_deduplicated(self):
        it = self.item("Social Knowledge Creation and Training")
        self.assertEqual(it["authors"], ["Raymond G. Siemens"])

    def test_name_variant_counts(self):
        nv = {g["name"]: g for g in self.dataset["meta"]["name_variants"]}
        self.assertEqual(nv["Raymond G. Siemens"]["applied"], 2)
        self.assertEqual(nv["Nobody Real"]["applied"], 0)
        self.assertEqual(nv["Raymond G. Siemens"]["variants"], ["Ray Siemens", "Raymond Siemens"])

    def test_stale_name_variant_reported(self):
        self.assertEqual(self.anomalies("stale-name-variant"), [{"type": "stale-name-variant", "text": "Nobody Here"}])

    # -- duplicate merging -------------------------------------------------

    def test_merge_by_doi_case_insensitive_and_across_volumes(self):
        it = self.item("Open Access and Policy in Libraries")
        self.assertEqual(it["doi"], "10.1234/abc.def")
        self.assertEqual(len(it["placements"]), 4)
        self.assertEqual(it["volumes"], ["Alpha Volume", "Beta Volume"])
        self.assertEqual(it["chapters"], ["Chapter One", "Chapter Three", "Chapter Two"])
        self.assertEqual(it["sections"], ["Beta Section", "Section One", "Section Two"])

    def test_merge_keeps_longest_annotation(self):
        it = self.item("Open Access and Policy in Libraries")
        self.assertEqual(it["annotation"],
                         "Discusses open access mandates and funder policy for institutional repositories.")

    def test_merge_keeps_longer_author_list_and_collects_variants(self):
        it = self.item("Open Access and Policy in Libraries")
        self.assertEqual(it["authors"], ["John Smith", "Jane Doe"])
        # identical citation text filed twice is recorded once; differing text is a variant
        self.assertEqual(len(it["variants"]), len(set(it["variants"])))
        self.assertNotIn(it["citation"], it["variants"])
        self.assertTrue(any("Bob Roe" in v for v in it["variants"]))

    def test_merge_takes_longer_contributors(self):
        it = self.item("Open Access and Policy in Libraries")
        # the later entry lists two contributors, the earlier one only one; the longer list wins
        self.assertEqual(it["contributors"], ["Bob Roe", "Cy Poe"])

    def test_merge_by_normalised_url(self):
        it = self.item("Url Dup One")
        self.assertEqual(len(it["placements"]), 2)
        self.assertEqual(it["annotation"], "First annotation.")
        self.assertEqual(it["title"], "Url Dup One")
        self.assertEqual([i["title"] for i in self.dataset["items"]].count("Another Title Entirely"), 0)

    def test_merge_by_title_and_year_replaces_with_longer_author_list(self):
        it = self.item("A Sufficiently Long Title Here For Matching")
        self.assertEqual(len(it["placements"]), 2)
        self.assertEqual(it["authors"], ["Sam Lee", "Pat Kim"])
        self.assertEqual(it["authors_raw"], "Lee, Sam, and Pat Kim")
        self.assertIn("peer review", it["annotation"])
        self.assertEqual(len(it["variants"]), 1)
        self.assertIn("Peer review", it["topics"])
        self.assertIn("Indigenous knowledges", it["topics"])

    def test_distinct_entries_stay_distinct(self):
        titles = [i["title"] for i in self.dataset["items"]]
        self.assertIn("Chapter In Book", titles)
        self.assertEqual(titles.count("Same Id Title"), 2)

    def test_placement_shape(self):
        it = self.item("A Sufficiently Long Title Here For Matching")
        p0, p1 = it["placements"]
        self.assertEqual(p0, {"volume": "Alpha Volume", "vslug": "alpha", "chapter": "Chapter One",
                              "sections": ["Section One"], "marker": []})
        self.assertEqual(p1["vslug"], "beta")
        self.assertEqual(p1["marker"], ["Φ"])

    def test_container_editors_and_editor_roles(self):
        it = self.item("Chapter In Book")
        self.assertEqual(it["editors"], ["Ann Parent"])
        self.assertEqual(it["authors"], [])
        self.assertEqual(it["container_editors"], ["Zed Zed"])
        self.assertEqual(it["kind"], "Book chapter")

    def test_container_editors_longer_list_wins(self):
        # direct unit check of the merge rule through a second snapshot
        beta = BETA_THREE + bold("Parent, Ann, editor. 2017. “Chapter In Book.” In ''The Book'', edited by Zed Zed and Yan Yan, 5-9. Pub. http://ed.example.org/c") + ann("Again.")
        raw = make_pages([("alpha", "Alpha Volume", "Alpha Vol", {"Chapter One": ALPHA_ONE}),
                          ("beta", "Beta Volume", "Beta Vol", {"Chapter Three": beta})])
        self.write(raw, [], [], [])
        self.run_main()
        self.assertEqual(self.item("Chapter In Book")["container_editors"], ["Zed Zed", "Yan Yan"])

    # -- ids ---------------------------------------------------------------

    def test_ids_unique_and_collision_extended(self):
        ids = [i["id"] for i in self.dataset["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        same = [i for i in self.dataset["items"] if i["title"] == "Same Id Title"]
        self.assertEqual(sorted(len(i["id"]) for i in same), [10, 12])

    def test_every_item_has_id_and_sorted_by_first_author(self):
        firsts = [parse.fold((i["authors"] or i["editors"] or [""])[0]) for i in self.dataset["items"]]
        self.assertEqual(firsts, sorted(firsts))
        for i in self.dataset["items"]:
            self.assertRegex(i["id"], r"^[0-9a-f]{10,12}$")

    # -- provenance and topics --------------------------------------------

    def test_annotation_source_from_legend(self):
        self.assertEqual(self.item("Open Access and Policy in Libraries")["annotation_source"],
                         ["Annotation by the Alpha team"])
        # marker Φ is in the legend of Alpha only; the Beta placement has no legend at all
        self.assertEqual(self.item("A Sufficiently Long Title Here For Matching")["annotation_source"], [])

    def test_topics_from_title_and_annotation(self):
        it = self.item("Open Access and Policy in Libraries")
        self.assertEqual(it["topics"], ["Open access", "Libraries and repositories", "Policy and funders"])
        self.assertEqual(self.item("Social Knowledge Creation and Training")["topics"],
                         ["Training and pedagogy", "Social knowledge creation"])

    # -- annotation validation --------------------------------------------

    def test_entries_without_annotation_reported(self):
        a = self.anomalies("entries-without-annotation")
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["volume"], "Alpha Volume")
        self.assertEqual(a[0]["count"], 1)
        self.assertTrue(a[0]["examples"][0].startswith("Sister, Name. 2013."))

    # -- recovered authors -------------------------------------------------

    def test_recovery_applied_to_authorless_item(self):
        it = self.item("An Untitled Orphan Report")
        self.assertEqual(it["authors"], ["Orphan Org"])
        self.assertEqual(it["contributors"], ["Helper One"])
        self.assertEqual(it["author_recovery"], {"basis": "organisation", "evidence": "http://orphan.example.org/about",
                                                  "checked": "2026-01-01", "note": "Seen."})

    def test_recovery_does_not_change_item_id(self):
        it = self.item("An Untitled Orphan Report")
        e = {"doi": "", "authors": [], "editors": [], "year": 2021, "title": it["title"]}
        self.assertEqual(it["id"], parse.item_id(e))

    def test_recovery_log_in_meta(self):
        log = self.dataset["meta"]["author_recovery"]
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["authors"], ["Orphan Org"])
        self.assertEqual(log[0]["basis"], "organisation")
        self.assertEqual(log[0]["id"], self.item("An Untitled Orphan Report")["id"])

    def test_recovery_ignores_items_that_already_have_authors(self):
        self.assertNotIn("author_recovery", self.item("Open Access and Policy in Libraries"))
        self.assertNotIn(["Should Not Apply"], [i["authors"] for i in self.dataset["items"]])

    def test_stale_recovery_reported_including_when_item_has_authors(self):
        stale = [a["text"] for a in self.anomalies("stale-recovery")]
        self.assertEqual(sorted(stale), ["NO SUCH CITATION", "Open Access and Policy in Libraries"])

    # -- name contamination checks ----------------------------------------

    def test_role_word_in_name_reported(self):
        texts = [a["text"] for a in self.anomalies("role-word-in-name")]
        self.assertIn("authors: Ann Lee, ed.", texts)
        self.assertIn("editors: Editors", texts)

    def test_citation_fragment_in_name_reported(self):
        texts = [a["text"] for a in self.anomalies("citation-fragment-in-name")]
        self.assertEqual(texts, ["contributors: Jo 2020"])

    def test_symbol_in_name_reported(self):
        texts = [a["text"] for a in self.anomalies("symbol-in-name")]
        self.assertEqual(texts, ["container_editors: Q Φ"])

    def test_missing_title_and_year_reported(self):
        self.assertEqual([a["text"][:14] for a in self.anomalies("missing-title")], ["Notitle, Ann. "])
        self.assertEqual([a["text"][:12] for a in self.anomalies("missing-year")], ["Noyear, Bob."])

    def test_malformed_doi_reported_twice_for_two_checks(self):
        a = self.anomalies("malformed-doi")
        self.assertEqual(len(a), 2)
        self.assertEqual(a[0], {"type": "malformed-doi", "text": "11.bad/x"})
        self.assertEqual(a[1]["volume"], "Alpha Volume")
        self.assertEqual(a[1]["text"], "https://doi.org/10/zz")

    def test_no_unexpected_anomaly_types(self):
        self.assertEqual({a["type"] for a in self.validation["anomalies"]}, {
            "stale-correction", "stale-name-variant", "stale-recovery", "entries-without-annotation",
            "role-word-in-name", "citation-fragment-in-name", "symbol-in-name", "missing-title", "missing-year",
            "malformed-doi", "bold-line-in-annotation"} - {"bold-line-in-annotation"})


class TestMainClean(MainCase):
    """A snapshot with no corrections, variants or recoveries is anomaly free."""

    def test_clean_snapshot_has_no_anomalies(self):
        raw = make_pages([("alpha", "Alpha Volume", "Alpha Vol", {
            "Chapter One": "==S==\n" + bold("Smith, John. 2020. “A Clean Entry With A Title.” Journal 3 (2): 5. https://example.org/z")
            + ann("Annotation text about nothing in particular.")})])
        self.write(raw, [], [], [])
        ds, val = self.run_main()
        self.assertEqual(val["anomalies"], [])
        self.assertEqual(ds["meta"]["raw_entries"], 1)
        self.assertEqual(ds["items"][0]["topics"], [])
        self.assertEqual(ds["meta"]["corrections"], [])
        self.assertEqual(ds["meta"]["author_recovery"], [])

    def test_xrefs_counted_in_info(self):
        raw = make_pages([("alpha", "Alpha Volume", "Alpha Vol", {
            "Chapter One": bold("Smith, John. 2020. “A Clean Entry With A Title.” Journal 3 (2): 5. https://example.org/z")
            + ann("Text.") + "'''Other 2019'''  ([[Elsewhere#x|see]])\n"})])
        self.write(raw, [], [], [])
        _, val = self.run_main()
        self.assertEqual(val["info"]["cross_reference_lines_skipped"], 1)

    def test_item_without_author_counted_in_info(self):
        raw = make_pages([("alpha", "Alpha Volume", "Alpha Vol", {
            "Chapter One": bold("“A Title With No Author Anywhere.” 2020. Org. https://example.org/z") + ann("Text.")})])
        self.write(raw, [], [], [])
        ds, val = self.run_main()
        self.assertEqual(val["info"]["items_without_named_author"], 1)
        self.assertEqual(ds["items"][0]["authors"], [])

    def test_item_with_only_editors_counts_as_named(self):
        raw = make_pages([("alpha", "Alpha Volume", "Alpha Vol", {
            "Chapter One": bold("Smith, John, ed. 2020. “A Title With An Editor Only.” Org. https://example.org/z") + ann("Text.")})])
        self.write(raw, [], [], [])
        ds, val = self.run_main()
        self.assertEqual(val["info"]["items_without_named_author"], 0)
        self.assertEqual(ds["items"][0]["editors"], ["John Smith"])

    def test_volume_without_introduction_has_empty_legend(self):
        raw = make_pages([("alpha", "Alpha Volume", "Alpha Vol", {"Chapter One": ""})])
        self.write(raw, [], [], [])
        ds, val = self.run_main()
        self.assertEqual(ds["volumes"][0]["legend"], {})
        self.assertEqual(ds["items"], [])
        self.assertEqual(val["per_volume"]["alpha"]["parsed"], 0)

    def test_main_is_deterministic(self):
        raw = synthetic_raw()
        self.write(raw, copy.deepcopy(CORRECTIONS), copy.deepcopy(VARIANTS), copy.deepcopy(RECOVERIES))
        self.run_main()
        first = (json.dumps(self.dataset, sort_keys=True), json.dumps(self.validation, sort_keys=True))
        parse.xrefs[0] = 0
        self.run_main()
        self.assertEqual(first, (json.dumps(self.dataset, sort_keys=True), json.dumps(self.validation, sort_keys=True)))

    def test_missing_input_raises(self):
        with self.assertRaises(FileNotFoundError):
            with contextlib.redirect_stdout(io.StringIO()):
                parse.main()


# ---------------------------------------------------------------------------
# Golden / integration test on the committed snapshot
# ---------------------------------------------------------------------------

class TestGoldenSnapshot(unittest.TestCase):
    ROLE = re.compile(r"\b(eds?|editors?|trans|translators?)\b\.?$|^(eds?|editors?)\.?$", re.I)
    FRAGMENT = re.compile(r"\b(?:1[5-9]|20)\d\d\b|[“”\"]|https?:")
    SYMBOL = re.compile(r"[\u0370-\u03ff+†*▲¤]")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(os.path.join(BUILD, "raw", "pages.json")):
            raise unittest.SkipTest("committed snapshot not present")
        cls.tmp = tempfile.mkdtemp(prefix="osp-parse-golden-")
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        os.makedirs(os.path.join(cls.tmp, "raw"))
        for rel in ("raw/pages.json", "corrections.json", "name_variants.json", "recovered_authors.json"):
            shutil.copyfile(os.path.join(BUILD, rel), os.path.join(cls.tmp, rel))
        parse.xrefs[0] = 0
        with mock.patch.object(parse, "HERE", cls.tmp), contextlib.redirect_stdout(io.StringIO()):
            parse.main()
        with open(os.path.join(cls.tmp, "dataset.json"), encoding="utf-8") as f:
            cls.dataset = json.load(f)
        with open(os.path.join(cls.tmp, "validation.json"), encoding="utf-8") as f:
            cls.validation = json.load(f)
        cls.items = cls.dataset["items"]

    def anomalies(self, typ):
        return [a for a in self.validation["anomalies"] if a["type"] == typ]

    def test_counts(self):
        meta = self.dataset["meta"]
        self.assertEqual(meta["raw_entries"], 1328)
        self.assertEqual(meta["unique_items"], 968)
        self.assertEqual(len(self.items), 968)
        self.assertEqual(meta["volume_count"], 7)
        self.assertEqual(sum(v["entries"] for v in self.dataset["volumes"]), 1328)
        self.assertEqual(sum(v["parsed"] for v in self.validation["per_volume"].values()), 1328)
        self.assertEqual(sum(len(i["placements"]) for i in self.items), 1328)

    def test_cross_references_skipped(self):
        self.assertEqual(self.validation["info"]["cross_reference_lines_skipped"], 103)

    def test_ids_present_and_unique(self):
        ids = [i["id"] for i in self.items]
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{10,12}", i) for i in ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_item_has_title_kind_and_placement(self):
        kinds = {"Book chapter", "Journal article", "Report or web resource", "Book or report"}
        for i in self.items:
            self.assertTrue(i["title"], i["citation"])
            self.assertIn(i["kind"], kinds)
            self.assertTrue(i["placements"])
            self.assertEqual(i["volumes"], sorted({p["volume"] for p in i["placements"]}))
            self.assertEqual(i["citation"], i["citation"].strip())

    def test_no_contaminated_names(self):
        for i in self.items:
            for role in ("authors", "editors", "container_editors", "contributors"):
                for n in i[role]:
                    self.assertFalse(self.ROLE.search(n), (role, n))
                    self.assertFalse(self.FRAGMENT.search(n), (role, n))
                    self.assertFalse(self.SYMBOL.search(n), (role, n))
                    self.assertEqual(n, n.strip())
                    self.assertTrue(n)

    def test_no_name_anomalies_and_only_known_anomaly_types(self):
        types = {a["type"] for a in self.validation["anomalies"]}
        self.assertLessEqual(types, {"entries-without-annotation"})
        self.assertEqual(self.anomalies("stale-correction"), [])
        self.assertEqual(self.anomalies("stale-name-variant"), [])
        self.assertEqual(self.anomalies("stale-recovery"), [])

    def test_author_recovery(self):
        self.assertEqual(len(self.dataset["meta"]["author_recovery"]), 37)
        self.assertEqual(sum(1 for i in self.items if "author_recovery" in i), 37)
        self.assertEqual(self.validation["info"]["items_without_named_author"], 1)

    def test_all_corrections_and_variants_applied(self):
        for c in self.dataset["meta"]["corrections"]:
            self.assertGreaterEqual(c["applied"], 1, c["match"])
        for g in self.dataset["meta"]["name_variants"]:
            self.assertGreaterEqual(g["applied"], 1, g["name"])

    def test_topics_are_lexicon_keys(self):
        for i in self.items:
            self.assertLessEqual(set(i["topics"]), set(parse.LEXICON))
        self.assertTrue(any(i["topics"] for i in self.items))

    def test_dois_well_formed_and_unique_per_item(self):
        dois = [i["doi"].lower().rstrip("/") for i in self.items if i["doi"]]
        for d in dois:
            self.assertRegex(d, r"^10\.\d{4,9}/")
        self.assertEqual(len(dois), len(set(dois)))

    def test_items_sorted(self):
        keys = [(parse.fold((i["authors"] or i["editors"] or [""])[0]), i["year"] or 0, parse.fold(i["title"]))
                for i in self.items]
        self.assertEqual(keys, sorted(keys))

    def test_repository_files_untouched(self):
        # main() wrote into the temp dir, not into the build directory
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "dataset.json")))
        self.assertNotEqual(os.path.abspath(self.tmp), os.path.abspath(BUILD))


class TestModuleEntryPoint(unittest.TestCase):
    def test_here_is_build_directory(self):
        self.assertEqual(os.path.basename(parse.HERE), "build")

    def test_running_as_script_calls_main(self):
        # Execute the real source as __main__ but with __file__ pointing into a temp dir, so that HERE
        # (derived from __file__) makes the script read and write only there.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "raw"))
            for name, data in (("raw/pages.json", make_pages([("a", "A", "A Root", {"Ch": ""})])),
                               ("corrections.json", []), ("name_variants.json", []),
                               ("recovered_authors.json", [])):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                    json.dump(data, f)
            with open(parse.__file__.replace(".pyc", ".py"), encoding="utf-8") as f:
                src = f.read()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exec(compile(src, parse.__file__.replace(".pyc", ".py"), "exec"),
                     {"__name__": "__main__", "__file__": os.path.join(tmp, "parse.py")})
            self.assertTrue(os.path.exists(os.path.join(tmp, "dataset.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "validation.json")))
            self.assertIn("0 raw entries; 0 unique items; 0 anomalies", out.getvalue())


if __name__ == "__main__":
    unittest.main()
