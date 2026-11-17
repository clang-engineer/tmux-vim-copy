"""Consumer-visible offsets and boundary behavior of pure text objects."""

import unittest

from vimcopy import select


class WordObjects(unittest.TestCase):
    def test_character_word_endpoints_and_punctuation(self):
        text = "alpha_12,..! beta"
        for cursor in (0, 4, 7):
            with self.subTest(cursor=cursor):
                self.assertEqual(select(text, cursor, "w", False), (0, 8))
        for cursor in (8, 9, 11):
            with self.subTest(cursor=cursor):
                self.assertEqual(select(text, cursor, "w", False), (8, 12))
        self.assertEqual(select(text, 12, "w", False), (12, 13))
        self.assertEqual(select(text, 13, "w", False), (13, 17))
        self.assertEqual(select(text, 7, "W", False), (0, 12))

    def test_around_prefers_following_whitespace_then_preceding(self):
        text = "  one \t two"
        self.assertEqual(select(text, 3, "w", True), (2, 8))
        self.assertEqual(select(text, 9, "w", True), (5, 11))
        self.assertEqual(select("one", 1, "w", True), (0, 3))
        self.assertEqual(select("one\n\ntwo", 0, "w", True), (0, 5))

    def test_around_whitespace_includes_following_or_final_word(self):
        text = "one  two  "
        self.assertEqual(select(text, 3, "w", False), (3, 5))
        self.assertEqual(select(text, 3, "w", True), (3, 10))
        self.assertEqual(select(text, 9, "w", True), (5, 10))
        self.assertIsNone(select(" \t\n", 0, "w", True))

    def test_counts_cross_word_and_punctuation_boundaries(self):
        text = "one, two! last"
        self.assertEqual(select(text, 0, "w", False, 2), (0, 4))
        self.assertEqual(select(text, 0, "w", False, 3), (0, 8))
        self.assertEqual(select(text, 0, "w", True, 2), (0, 5))
        self.assertEqual(select(text, 0, "W", False, 2), (0, 9))
        self.assertEqual(select(text, 4, "w", False, 2), (4, 8))
        self.assertIsNone(select(text, 0, "w", False, 6))
        self.assertIsNone(select(text, 0, "W", False, 4))

    def test_unicode_letters_numbers_and_combining_character_offsets(self):
        text = "漢字_１２ e\u0301lan 😀"
        self.assertEqual(select(text, 4, "w", False), (0, 5))
        # A decomposed accent belongs to its word, not a separate object.
        for cursor in (6, 7, 8, 10):
            self.assertEqual(select(text, cursor, "w", False), (6, 11))
        self.assertEqual(select(text, 7, "W", False), (6, 11))
        self.assertEqual(select(text, 12, "w", False), (12, 13))


class ParagraphObjects(unittest.TestCase):
    def test_inner_retains_line_terminators_not_blank_separator_lines(self):
        text = "first\nsecond\n\n \t\nthird\n\nlast"
        self.assertEqual(select(text, 0, "p", False), (0, 13))
        self.assertEqual(select(text, 11, "p", False), (0, 13))
        self.assertEqual(select(text, 17, "p", False), (17, 23))
        self.assertEqual(select(text, 25, "p", False), (24, 28))

    def test_around_prefers_following_separators_then_preceding(self):
        text = "first\nsecond\n\n \t\nthird\n\nlast"
        self.assertEqual(select(text, 1, "p", True), (0, 17))
        self.assertEqual(select(text, 17, "p", True), (17, 24))
        self.assertEqual(select(text, 27, "p", True), (23, 28))

    def test_cursor_on_separator_chooses_following_block_or_preceding_at_end(self):
        text = "one\n\n \nnext\n\n"
        self.assertEqual(select(text, 4, "p", False), (7, 12))
        self.assertEqual(select(text, 12, "p", False), (7, 12))
        self.assertEqual(select(text, 12, "p", True), (7, 13))
        self.assertIsNone(select("\n \t\n", 2, "p", False))

    def test_count_spans_paragraphs_and_intervening_separators(self):
        text = "one\n\ntwo\n\nthree"
        self.assertEqual(select(text, 0, "p", False, 2), (0, 9))
        self.assertEqual(select(text, 0, "p", True, 2), (0, 10))
        self.assertEqual(select(text, 0, "p", False, 3), (0, 15))
        self.assertIsNone(select(text, 0, "p", False, 4))

    def test_no_final_newline_and_leading_blank_lines(self):
        text = "\n\nlast"
        self.assertEqual(select(text, 0, "p", False), (2, 6))
        self.assertEqual(select(text, 5, "p", True), (0, 6))
        self.assertEqual(select("only", 3, "p", False), (0, 4))


class QuoteObjects(unittest.TestCase):
    def test_each_quote_and_cursor_on_both_delimiters(self):
        for quote in ('"', "'", "`"):
            text = "x " + quote + "漢😀e\u0301" + quote + " y"
            for cursor in (2, 3, 4, 5, 6, 7):
                with self.subTest(quote=quote, cursor=cursor):
                    self.assertEqual(select(text, cursor, quote, False), (3, 7))
                    self.assertEqual(select(text, cursor, quote, True), (2, 8))

    def test_odd_and_even_backslash_escaping(self):
        text = r'"a\"b"'
        self.assertEqual(select(text, 3, '"', False), (1, 5))
        text = r'"a\\" tail'
        self.assertEqual(select(text, 2, '"', False), (1, 4))
        for quote in ("'", "`"):
            text = quote + "a\\" + quote + "b" + quote
            self.assertEqual(select(text, 3, quote, False), (1, 5))

    def test_next_pair_is_available_only_on_current_line(self):
        text = 'before "first" between "second" after\n"next"'
        self.assertEqual(select(text, 0, '"', False), (8, 13))
        self.assertEqual(select(text, 17, '"', False), (24, 30))
        self.assertIsNone(select(text, 33, '"', False))
        self.assertIsNone(select('before\n"next"', 0, '"', False))

    def test_count_spans_successive_complete_pairs(self):
        text = '"one" and "two"'
        self.assertEqual(select(text, 1, '"', False, 2), (1, 14))
        self.assertEqual(select(text, 1, '"', True, 2), (0, 15))
        self.assertIsNone(select(text, 1, '"', False, 3))

    def test_unmatched_and_empty_quotes(self):
        self.assertIsNone(select('"unclosed', 2, '"', False))
        self.assertIsNone(select('"one\ntwo"', 1, '"', False))
        self.assertIsNone(select('""', 0, '"', False))
        self.assertEqual(select('""', 1, '"', True), (0, 2))
        self.assertIsNone(select(r'\"not delimiters\"', 5, '"', False))


class BracketObjects(unittest.TestCase):
    def test_pairs_and_aliases_on_opening_closing_and_content(self):
        for opening, closing, aliases in (
            ("(", ")", ("(", ")", "b")),
            ("[", "]", ("[", "]")),
            ("{", "}", ("{", "}", "B")),
            ("<", ">", ("<", ">")),
        ):
            text = "x " + opening + "漢😀e\u0301" + closing + " y"
            for key in aliases:
                for cursor in (2, 3, 4, 5, 6, 7):
                    with self.subTest(key=key, cursor=cursor):
                        self.assertEqual(select(text, cursor, key, False), (3, 7))
                        self.assertEqual(select(text, cursor, key, True), (2, 8))

    def test_nested_multiline_and_same_type_enclosing_counts(self):
        text = "(outer\n [other (inner) kind]\n end)"
        cursor = text.index("inner")
        inner_start = text.index("(inner)")
        inner_end = inner_start + len("(inner)")
        self.assertEqual(select(text, cursor, "(", False), (inner_start + 1, inner_end - 1))
        self.assertEqual(select(text, cursor, "(", True, 2), (0, len(text)))
        self.assertEqual(select(text, cursor, "(", False, 2), (1, len(text) - 1))
        self.assertIsNone(select(text, cursor, "(", False, 3))
        self.assertEqual(
            select(text, cursor, "[", True),
            (text.index("["), text.index("]") + 1),
        )
        # At the inner closing delimiter, select inner; just beyond it, outer.
        self.assertEqual(select(text, inner_end - 1, "(", True), (inner_start, inner_end))
        self.assertEqual(select(text, inner_end, "(", True), (0, len(text)))

    def test_escaped_delimiters_and_backslash_parity(self):
        text = r'(one \(ignored\) two)'
        self.assertEqual(select(text, 9, "(", True), (0, len(text)))
        text = r'\\(real)'
        self.assertEqual(select(text, 4, "(", True), (2, len(text)))
        self.assertIsNone(select(r'\(not a pair\)', 5, "(", False))

    def test_delimiters_inside_each_quoted_string_are_ignored(self):
        for quote in ('"', "'", "`"):
            text = "(before " + quote + "fake ) [ { <" + quote + "\n after)"
            with self.subTest(quote=quote):
                self.assertEqual(select(text, 12, "(", True), (0, len(text)))
                self.assertIsNone(select(text, 12, "[", True))
        text = '("escaped \\" still ) quoted"\nend)'
        self.assertEqual(select(text, 12, "(", True), (0, len(text)))

    def test_empty_unmatched_crossing_and_unrelated_pairs(self):
        for text, key in (("()", "("), ("[]", "["), ("{}", "{"), ("<>", "<")):
            with self.subTest(text=text):
                self.assertIsNone(select(text, 0, key, False))
                self.assertEqual(select(text, 1, key, True), (0, 2))
        for text in ("(unclosed", "closed)", "([crossed)]", "(bad ] end)"):
            with self.subTest(text=text):
                self.assertIsNone(select(text, 1, "(", True))
        self.assertIsNone(select("(one) (two)", 5, "(", False))
        self.assertIsNone(select("(one) (two)", 2, "(", False, 2))

    def test_quote_context_ends_at_logical_line_boundary(self):
        text = '("unfinished quote\nnext)'
        self.assertEqual(select(text, 2, "(", True), (0, len(text)))
        text = '("unfinished quote' + "\\" + "\nnext)"
        self.assertEqual(select(text, 2, "(", True), (0, len(text)))


class InvalidRequests(unittest.TestCase):
    def test_invalid_cursor_key_and_count_return_none(self):
        for text, cursor, key, count in (
            ("", 0, "w", 1),
            ("word", -1, "w", 1),
            ("word", 4, "w", 1),
            ("word", 0, "unknown", 1),
            ("word", 0, "", 1),
            ("word", 0, "w", 0),
            ("word", 0, "w", -1),
        ):
            with self.subTest(text=text, cursor=cursor, key=key, count=count):
                self.assertIsNone(select(text, cursor, key, False, count))


if __name__ == "__main__":
    unittest.main()
