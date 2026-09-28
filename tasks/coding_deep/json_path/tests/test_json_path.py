import time
import unittest

from solution import PathError, query


STORE = {
    "store": {
        "book": [
            {"category": "reference", "author": "Nigel Rees", "title": "Sayings", "price": 8.95},
            {"category": "fiction", "author": "Evelyn Waugh", "title": "Sword", "price": 12.99},
            {"category": "fiction", "author": "Herman Melville", "title": "Moby Dick",
             "isbn": "0-553-21311-3", "price": 8.99},
            {"category": "fiction", "author": "J. R. R. Tolkien", "title": "LotR",
             "isbn": "0-395-19395-8", "price": 22.99},
        ],
        "bicycle": {"color": "red", "price": 19.95},
    },
    "expensive": 10,
}


class TestBasics(unittest.TestCase):
    def test_root(self):
        self.assertEqual(query(STORE, "$"), [STORE])
        self.assertIs(query(STORE, "$")[0], STORE)
        self.assertEqual(query(5, "$"), [5])
        self.assertEqual(query(None, "$"), [None])

    def test_dot_child(self):
        self.assertEqual(query(STORE, "$.expensive"), [10])
        self.assertEqual(query(STORE, "$.store.bicycle.color"), ["red"])
        self.assertEqual(query(STORE, "$.missing"), [])
        self.assertEqual(query(STORE, "$.expensive.deeper"), [])

    def test_bracket_child_with_quotes_and_escapes(self):
        data = {"a b": 1, "it's": 2, 'say "hi"': 3, "back\\slash": 4, "dot.ted": 5, "": 6}
        self.assertEqual(query(data, "$['a b']"), [1])
        self.assertEqual(query(data, '$["a b"]'), [1])
        self.assertEqual(query(data, "$['it\\'s']"), [2])
        self.assertEqual(query(data, '$["it\'s"]'), [2])
        self.assertEqual(query(data, "$['say \"hi\"']"), [3])
        self.assertEqual(query(data, "$['back\\\\slash']"), [4])
        self.assertEqual(query(data, "$['dot.ted']"), [5])
        self.assertEqual(query(data, "$['']"), [6])
        self.assertEqual(query(data, "$.dot.ted"), [])

    def test_name_characters(self):
        data = {"snake_case": 1, "kebab-case": 2, "_x9": 3}
        self.assertEqual(query(data, "$.snake_case"), [1])
        self.assertEqual(query(data, "$.kebab-case"), [2])
        self.assertEqual(query(data, "$._x9"), [3])

    def test_returns_same_objects_not_copies(self):
        bike = STORE["store"]["bicycle"]
        self.assertIs(query(STORE, "$.store.bicycle")[0], bike)
        self.assertIs(query(STORE, "$..bicycle")[0], bike)


class TestWildcardAndIndex(unittest.TestCase):
    def test_wildcard_on_dict_and_list(self):
        self.assertEqual(query({"b": 1, "a": 2}, "$.*"), [1, 2])
        self.assertEqual(query([3, 4], "$[*]"), [3, 4])
        self.assertEqual(query([3, 4], "$.*"), [3, 4])
        self.assertEqual(query({"b": 1, "a": 2}, "$[*]"), [1, 2])
        self.assertEqual(query(5, "$.*"), [])
        self.assertEqual(query("str", "$[*]"), [])

    def test_wildcard_chain(self):
        self.assertEqual(
            query(STORE, "$.store.book[*].author"),
            ["Nigel Rees", "Evelyn Waugh", "Herman Melville", "J. R. R. Tolkien"],
        )
        self.assertEqual(query(STORE, "$.store.*.price"), [19.95])
        self.assertEqual(query(STORE, "$.store.book.*.isbn"), ["0-553-21311-3", "0-395-19395-8"])

    def test_index_positive_negative_out_of_range(self):
        data = [10, 20, 30]
        self.assertEqual(query(data, "$[0]"), [10])
        self.assertEqual(query(data, "$[2]"), [30])
        self.assertEqual(query(data, "$[-1]"), [30])
        self.assertEqual(query(data, "$[-3]"), [10])
        self.assertEqual(query(data, "$[3]"), [])
        self.assertEqual(query(data, "$[-4]"), [])
        self.assertEqual(query(data, "$[+1]"), [20])

    def test_index_on_dict_and_name_on_list_do_not_match(self):
        self.assertEqual(query({"0": "zero"}, "$[0]"), [])
        self.assertEqual(query(["a"], "$.a"), [])
        self.assertEqual(query(["a"], "$['0']"), [])

    def test_nested_indices(self):
        data = [[1, 2], [3, [4, 5]]]
        self.assertEqual(query(data, "$[1][1][0]"), [4])
        self.assertEqual(query(data, "$[-1][-1][-1]"), [5])
        self.assertEqual(query(data, "$[0][5]"), [])


class TestSlicesAndUnions(unittest.TestCase):
    DATA = list(range(10))

    def test_slices(self):
        self.assertEqual(query(self.DATA, "$[1:4]"), [1, 2, 3])
        self.assertEqual(query(self.DATA, "$[:3]"), [0, 1, 2])
        self.assertEqual(query(self.DATA, "$[7:]"), [7, 8, 9])
        self.assertEqual(query(self.DATA, "$[::3]"), [0, 3, 6, 9])
        self.assertEqual(query(self.DATA, "$[::-1]"), list(reversed(self.DATA)))
        self.assertEqual(query(self.DATA, "$[-3:]"), [7, 8, 9])
        self.assertEqual(query(self.DATA, "$[:-8]"), [0, 1])
        self.assertEqual(query(self.DATA, "$[8:2:-2]"), [8, 6, 4])
        self.assertEqual(query(self.DATA, "$[:]"), self.DATA)
        self.assertEqual(query(self.DATA, "$[100:200]"), [])
        self.assertEqual(query({"a": 1}, "$[0:1]"), [])

    def test_slice_whitespace(self):
        self.assertEqual(query(self.DATA, "$[ 1 : 3 ]"), [1, 2])
        self.assertEqual(query(self.DATA, "$[ : : 4 ]"), [0, 4, 8])

    def test_union_of_indices_order_and_duplicates(self):
        self.assertEqual(query(self.DATA, "$[3,1,3]"), [3, 1, 3])
        self.assertEqual(query(self.DATA, "$[ 0 , -1 ]"), [0, 9])
        self.assertEqual(query(self.DATA, "$[0,50]"), [0])

    def test_union_of_names_and_mixed(self):
        data = {"a": 1, "b": 2, "c": 3}
        self.assertEqual(query(data, "$['c','a']"), [3, 1])
        self.assertEqual(query(data, "$['c', \"b\", 'zzz']"), [3, 2])
        self.assertEqual(query(data, "$[0,'b']"), [2])
        self.assertEqual(query([7, 8], "$[1,'b']"), [8])

    def test_union_then_child(self):
        self.assertEqual(query(STORE, "$.store.book[0,2].title"), ["Sayings", "Moby Dick"])
        self.assertEqual(query(STORE, "$.store.book[1:3].price"), [12.99, 8.99])


class TestRecursiveDescent(unittest.TestCase):
    def test_recursive_name(self):
        self.assertEqual(query(STORE, "$..price"), [8.95, 12.99, 8.99, 22.99, 19.95])
        self.assertEqual(query(STORE, "$..isbn"), ["0-553-21311-3", "0-395-19395-8"])
        self.assertEqual(query(STORE, "$..nothing"), [])

    def test_recursive_preorder_includes_current_node(self):
        data = {"a": {"a": {"a": 1}, "b": 2}, "c": [{"a": 3}]}
        matches = query(data, "$..a")
        self.assertEqual(matches, [{"a": {"a": 1}, "b": 2}, {"a": 1}, 1, 3])
        self.assertEqual(query(data, "$.a..a"), [{"a": 1}, 1])

    def test_recursive_wildcard_order(self):
        data = {"x": [1, {"y": 2}], "z": 3}
        # Pre-order: the root's own matches first, then those of each descendant.
        self.assertEqual(query(data, "$..*"), [[1, {"y": 2}], 3, 1, {"y": 2}, 2])
        self.assertEqual(query(data, "$.x..*"), [1, {"y": 2}, 2])

    def test_recursive_bracket_forms(self):
        self.assertEqual(query(STORE, "$..['price']"), [8.95, 12.99, 8.99, 22.99, 19.95])
        self.assertEqual(query(STORE, "$..book[0].title"), ["Sayings"])
        self.assertEqual(query(STORE, "$..[0]"), [STORE["store"]["book"][0]])
        self.assertEqual(query(STORE, "$..[-1].title"), ["LotR"])
        self.assertEqual(query(STORE, "$..book[1:2].author"), ["Evelyn Waugh"])
        self.assertEqual(query(STORE, "$..[*]")[:1], [STORE["store"]])
        self.assertEqual(len(query(STORE, "$..[*]")), len(query(STORE, "$..*")))

    def test_recursive_on_scalar_and_after_index(self):
        self.assertEqual(query(5, "$..a"), [])
        data = [[{"k": 1}], [{"k": 2}, [{"k": 3}]]]
        self.assertEqual(query(data, "$[1]..k"), [2, 3])


class TestErrors(unittest.TestCase):
    BAD = [
        "", " ", "$$", "foo", ".a", "$.", "$[", "$]", "$foo", "$..", "$...a", "$.a.", "$[]",
        "$[1.5]", "$[a]", "$['a", "$['a]", "$[1:2:0]", "$[*,1]", "$[1:2,3]", "$['a']b",
        "$ .a", "$. a", "$.a ", "$[1]]", "$[1,]", "$[,1]", "$['a\\qb']", "$.*x", "$[**]",
        "$.a..", "$..[", "$.-a", "$[1 2]", "$['a'.b]", "$[--1]",
    ]

    def test_syntax_errors(self):
        for path in self.BAD:
            with self.assertRaises(PathError):
                query(STORE, path)

    def test_errors_raised_even_for_empty_data(self):
        for path in ("$.", "$[", "$[a]"):
            with self.assertRaises(PathError):
                query({}, path)

    def test_path_error_is_value_error(self):
        self.assertTrue(issubclass(PathError, ValueError))

    def test_non_string_path(self):
        with self.assertRaises(PathError):
            query({}, None)


class TestPerformance(unittest.TestCase):
    def test_recursive_wildcard_on_large_document(self):
        doc = {f"k{i}": {"id": i, "tags": ["a", "b", {"deep": i}]} for i in range(4000)}
        start = time.perf_counter()
        res = query(doc, "$..*")
        deep = query(doc, "$..deep")
        elapsed = time.perf_counter() - start
        self.assertEqual(len(deep), 4000)
        self.assertEqual(len(res), 4000 * 7)
        self.assertLess(elapsed, 2.0)

    def test_deep_nesting_without_recursion_error(self):
        node = 1
        for _ in range(5000):
            node = [node]
        res = query(node, "$..*")
        self.assertEqual(len(res), 5000)
        self.assertIs(res[-1], 1)
        self.assertEqual(query(node, "$" + "[0]" * 5000), [1])
        self.assertEqual(len(query(node, "$..[0]")), 5000)
        self.assertEqual(query(node, "$..[0]")[-1], 1)


if __name__ == "__main__":
    unittest.main()
