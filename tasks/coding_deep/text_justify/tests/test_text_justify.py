import random
import time
import unittest

from solution import full_justify, render_table, wrap_paragraphs


class TestFullJustify(unittest.TestCase):
    def test_leetcode_example_1(self):
        words = ["This", "is", "an", "example", "of", "text", "justification."]
        self.assertEqual(
            full_justify(words, 16),
            ["This    is    an", "example  of text", "justification.  "],
        )

    def test_leetcode_example_2_single_word_lines_left_justified(self):
        words = ["What", "must", "be", "acknowledgment", "shall", "be"]
        self.assertEqual(
            full_justify(words, 16),
            ["What   must   be", "acknowledgment  ", "shall be        "],
        )

    def test_leetcode_example_3(self):
        words = ["Science", "is", "what", "we", "understand", "well", "enough", "to",
                 "explain", "to", "a", "computer.", "Art", "is", "everything", "else",
                 "we", "do"]
        self.assertEqual(
            full_justify(words, 20),
            [
                "Science  is  what we",
                "understand      well",
                "enough to explain to",
                "a  computer.  Art is",
                "everything  else  we",
                "do                  ",
            ],
        )

    def test_empty_and_single_word(self):
        self.assertEqual(full_justify([], 5), [])
        self.assertEqual(full_justify(["abc"], 5), ["abc  "])
        self.assertEqual(full_justify(["abcde"], 5), ["abcde"])

    def test_extra_spaces_go_left(self):
        self.assertEqual(full_justify(["a", "b", "c", "d", "eeeeeeeee"], 10), ["a  b  c  d", "eeeeeeeee "])
        self.assertEqual(full_justify(["a", "b", "c", "d"], 10), ["a b c d   "])
        self.assertEqual(full_justify(["a", "b", "c", "xyzw"], 8), ["a   b  c", "xyzw    "])
        self.assertEqual(full_justify(["aa", "b", "c", "ddd", "e"], 9), ["aa   b  c", "ddd e    "])
        self.assertEqual(full_justify(["a", "b", "c", "d", "eeeeee"], 8), ["a  b c d", "eeeeee  "])

    def test_width_one(self):
        self.assertEqual(full_justify(["a", "b", "c"], 1), ["a", "b", "c"])

    def test_exact_fit_lines(self):
        self.assertEqual(full_justify(["ab", "cd", "ef", "gh"], 5), ["ab cd", "ef gh"])
        self.assertEqual(full_justify(["ab", "cd", "ef", "gh", "i"], 5), ["ab cd", "ef gh", "i    "])

    def test_all_lines_have_exact_width(self):
        rng = random.Random(1)
        letters = "abcdefghijklmnopqrstuvwxyz"
        for _ in range(50):
            width = rng.randint(1, 30)
            words = ["".join(rng.choice(letters) for _ in range(rng.randint(1, width)))
                     for _ in range(rng.randint(0, 60))]
            lines = full_justify(words, width)
            self.assertTrue(all(len(line) == width for line in lines))
            self.assertEqual(" ".join(words).split(), " ".join(lines).split())

    def test_validation(self):
        with self.assertRaises(ValueError):
            full_justify(["ab"], 0)
        with self.assertRaises(ValueError):
            full_justify(["ab"], True)
        with self.assertRaises(ValueError):
            full_justify(["ab"], 2.0)
        with self.assertRaises(ValueError):
            full_justify(["abc"], 2)
        with self.assertRaises(ValueError):
            full_justify(["a b"], 5)
        with self.assertRaises(ValueError):
            full_justify([""], 5)
        with self.assertRaises(ValueError):
            full_justify(["a", 5], 5)
        with self.assertRaises(ValueError):
            full_justify(["a\tb"], 5)


class TestWrapParagraphs(unittest.TestCase):
    def test_simple_wrap(self):
        text = "the quick brown fox jumps over the lazy dog"
        self.assertEqual(
            wrap_paragraphs(text, 10),
            "the quick\nbrown fox\njumps over\nthe lazy\ndog",
        )

    def test_paragraphs_preserved_and_collapsed(self):
        text = "\n\n  first para\nstill first\n\n   \n\nsecond para\n\n\n"
        self.assertEqual(
            wrap_paragraphs(text, 12), "first para\nstill first\n\nsecond para"
        )

    def test_whitespace_normalisation(self):
        self.assertEqual(wrap_paragraphs("a   b\t\tc\n d ", 3), "a b\nc d")

    def test_long_word_hard_break(self):
        self.assertEqual(wrap_paragraphs("abcdefghij", 4), "abcd\nefgh\nij")
        self.assertEqual(wrap_paragraphs("abcdefgh", 4), "abcd\nefgh")
        self.assertEqual(wrap_paragraphs("x abcdefghij yz", 4), "x\nabcd\nefgh\nij\nyz")
        self.assertEqual(wrap_paragraphs("x abcdefghi yz", 4), "x\nabcd\nefgh\ni yz")

    def test_long_word_at_width_one(self):
        self.assertEqual(wrap_paragraphs("ab c", 1), "a\nb\nc")

    def test_empty_inputs(self):
        self.assertEqual(wrap_paragraphs("", 10), "")
        self.assertEqual(wrap_paragraphs("   \n\n \t\n", 10), "")

    def test_no_trailing_spaces_or_newline(self):
        out = wrap_paragraphs("alpha beta gamma delta\n\nepsilon", 11)
        self.assertEqual(out, "alpha beta\ngamma delta\n\nepsilon")
        self.assertFalse(out.endswith("\n"))
        self.assertTrue(all(line == line.rstrip() for line in out.split("\n")))

    def test_validation(self):
        with self.assertRaises(ValueError):
            wrap_paragraphs("abc", 0)
        with self.assertRaises(ValueError):
            wrap_paragraphs("abc", True)
        with self.assertRaises(ValueError):
            wrap_paragraphs(None, 5)
        with self.assertRaises(ValueError):
            wrap_paragraphs(["a"], 5)


class TestRenderTable(unittest.TestCase):
    def test_example(self):
        out = render_table([["name", "qty"], ["apple", 3], ["kiwi", 12]], "lr")
        self.assertEqual(
            out,
            "| name  | qty |\n|-------|-----|\n| apple |   3 |\n| kiwi  |  12 |",
        )

    def test_default_left_and_none_cells(self):
        out = render_table([["a", "b"], [None, "longer"]])
        self.assertEqual(out, "| a | b      |\n|---|--------|\n|   | longer |")

    def test_center_alignment_extra_on_right(self):
        out = render_table([["abcde"], ["x"], ["xy"]], ["c"])
        self.assertEqual(out, "| abcde |\n|-------|\n|   x   |\n|  xy   |")

    def test_aligns_as_list_and_mixed(self):
        out = render_table([["h1", "h2", "h3"], [1, 22, 333]], ["r", "c", "l"])
        self.assertEqual(out, "| h1 | h2 | h3  |\n|----|----|-----|\n|  1 | 22 | 333 |")

    def test_single_row_and_empty(self):
        self.assertEqual(render_table([], "l"), "")
        self.assertEqual(render_table([["only"]]), "| only |\n|------|")
        self.assertEqual(render_table([[""]]), "|   |\n|---|")

    def test_validation(self):
        with self.assertRaises(ValueError):
            render_table([["a", "b"], ["c"]])
        with self.assertRaises(ValueError):
            render_table([[]])
        with self.assertRaises(ValueError):
            render_table([["a"]], "lr")
        with self.assertRaises(ValueError):
            render_table([["a"]], "x")
        with self.assertRaises(ValueError):
            render_table([["a", "b"]], ["l"])


class TestPerformance(unittest.TestCase):
    def test_large_inputs(self):
        rng = random.Random(3)
        words = ["w" * rng.randint(1, 9) for _ in range(20000)]
        text = "\n\n".join(" ".join(words[i : i + 500]) for i in range(0, 20000, 500))
        rows = [["id", "name", "score"]] + [[i, f"n{i}", i * 1.5] for i in range(5000)]
        start = time.perf_counter()
        lines = full_justify(words, 40)
        wrapped = wrap_paragraphs(text * 2, 60)
        table = render_table(rows, "rlr")
        elapsed = time.perf_counter() - start
        self.assertTrue(all(len(line) == 40 for line in lines))
        self.assertLess(len(wrapped), 2 * len(text) + 5000)
        self.assertEqual(table.count("\n"), 5001)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
