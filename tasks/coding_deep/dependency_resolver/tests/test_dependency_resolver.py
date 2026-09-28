import time
import unittest

from solution import CycleError, MissingDependencyError, ResolverError, levels, resolve


def is_valid_order(graph, order, nodes=None):
    nodes = set(graph) if nodes is None else set(nodes)
    if sorted(order) != sorted(nodes):
        return False
    pos = {n: i for i, n in enumerate(order)}
    for n in nodes:
        for d in graph[n]:
            if pos[d] >= pos[n]:
                return False
    return True


class TestResolve(unittest.TestCase):
    def test_empty_graph(self):
        self.assertEqual(resolve({}), [])
        self.assertEqual(levels({}), [])

    def test_single_node(self):
        self.assertEqual(resolve({"a": []}), ["a"])
        self.assertEqual(levels({"a": ()}), [["a"]])

    def test_simple_chain(self):
        g = {"c": ["b"], "b": ["a"], "a": []}
        self.assertEqual(resolve(g), ["a", "b", "c"])

    def test_lexicographic_tie_break(self):
        g = {"z": [], "a": [], "m": []}
        self.assertEqual(resolve(g), ["a", "m", "z"])

    def test_lexicographically_smallest_not_just_sorted_ready_set(self):
        # 'a' depends on 'z': the smallest valid order starts with 'b', not 'z'.
        g = {"a": ["z"], "b": [], "z": []}
        self.assertEqual(resolve(g), ["b", "z", "a"])

    def test_diamond(self):
        g = {"d": ["b", "c"], "b": ["a"], "c": ["a"], "a": []}
        self.assertEqual(resolve(g), ["a", "b", "c", "d"])
        self.assertEqual(levels(g), [["a"], ["b", "c"], ["d"]])

    def test_duplicate_dependencies_and_any_iterable(self):
        g = {"b": ("a", "a", "a"), "a": set()}
        self.assertEqual(resolve(g), ["a", "b"])
        self.assertEqual(levels(g), [["a"], ["b"]])

    def test_input_not_mutated(self):
        g = {"b": ["a", "a"], "a": []}
        resolve(g)
        levels(g)
        self.assertEqual(g, {"b": ["a", "a"], "a": []})

    def test_larger_deterministic_example(self):
        g = {
            "app": ["lib", "utils", "config"],
            "lib": ["core"],
            "utils": ["core"],
            "config": [],
            "core": [],
            "tests": ["app", "fixtures"],
            "fixtures": ["config"],
        }
        order = resolve(g)
        self.assertTrue(is_valid_order(g, order))
        self.assertEqual(order, ["config", "core", "fixtures", "lib", "utils", "app", "tests"])
        self.assertEqual(
            levels(g),
            [["config", "core"], ["fixtures", "lib", "utils"], ["app"], ["tests"]],
        )


class TestLevels(unittest.TestCase):
    def test_levels_use_longest_chain(self):
        # 'd' depends on 'a' (level 0) and 'c' (level 2) -> 'd' is level 3.
        g = {"a": [], "b": ["a"], "c": ["b"], "d": ["a", "c"], "e": ["a"]}
        self.assertEqual(levels(g), [["a"], ["b", "e"], ["c"], ["d"]])

    def test_levels_sorted_within_level(self):
        g = {"z": [], "y": [], "x": ["z"], "w": ["y"]}
        self.assertEqual(levels(g), [["y", "z"], ["w", "x"]])

    def test_levels_no_empty_layers(self):
        g = {f"n{i}": [f"n{i-1}"] if i else [] for i in range(6)}
        self.assertEqual(levels(g), [[f"n{i}"] for i in range(6)])


class TestTargets(unittest.TestCase):
    G = {
        "a": [],
        "b": ["a"],
        "c": ["b"],
        "x": ["y"],
        "y": ["x"],  # cycle, only matters when reachable
        "m": ["ghost"],  # missing, only matters when reachable
    }

    def test_targets_restrict_to_closure(self):
        self.assertEqual(resolve(self.G, targets=["c"]), ["a", "b", "c"])
        self.assertEqual(resolve(self.G, targets=["b", "a"]), ["a", "b"])
        self.assertEqual(levels(self.G, targets=["c"]), [["a"], ["b"], ["c"]])

    def test_unreachable_problems_are_ignored(self):
        self.assertEqual(resolve(self.G, targets=["b"]), ["a", "b"])

    def test_reachable_problems_are_reported(self):
        with self.assertRaises(CycleError):
            resolve(self.G, targets=["x"])
        with self.assertRaises(MissingDependencyError):
            levels(self.G, targets=["m"])

    def test_unknown_target(self):
        with self.assertRaises(KeyError):
            resolve(self.G, targets=["nope"])

    def test_empty_targets(self):
        self.assertEqual(resolve(self.G, targets=[]), [])
        self.assertEqual(levels(self.G, targets=()), [])

    def test_whole_graph_reports_problems_and_hierarchy(self):
        self.assertTrue(issubclass(CycleError, ResolverError))
        self.assertTrue(issubclass(MissingDependencyError, ResolverError))
        self.assertTrue(issubclass(ResolverError, Exception))
        with self.assertRaises(ResolverError):
            resolve(self.G)


class TestMissing(unittest.TestCase):
    def test_missing_dependency_details(self):
        g = {"a": ["zeta", "beta"], "b": ["zeta"], "c": []}
        with self.assertRaises(MissingDependencyError) as cm:
            resolve(g)
        self.assertEqual(cm.exception.missing, [("a", "beta"), ("a", "zeta"), ("b", "zeta")])
        msg = str(cm.exception)
        for name in ("a", "b", "zeta", "beta"):
            self.assertIn(name, msg)
        with self.assertRaises(MissingDependencyError):
            levels(g)

    def test_missing_checked_before_cycle(self):
        g = {"a": ["b"], "b": ["a", "ghost"]}
        with self.assertRaises(MissingDependencyError):
            resolve(g)


class TestCycles(unittest.TestCase):
    def assert_cycle_ok(self, graph, cycle):
        self.assertGreaterEqual(len(cycle), 2)
        self.assertEqual(cycle[0], cycle[-1])
        body = cycle[:-1]
        self.assertEqual(len(set(body)), len(body))
        self.assertEqual(cycle[0], min(body))
        for a, b in zip(cycle, cycle[1:]):
            self.assertIn(b, list(graph[a]), f"{a} does not depend on {b}")

    def test_self_dependency(self):
        with self.assertRaises(CycleError) as cm:
            resolve({"a": ["a"]})
        self.assertEqual(cm.exception.cycle, ["a", "a"])
        self.assertIn("a", str(cm.exception))

    def test_two_node_cycle(self):
        g = {"b": ["a"], "a": ["b"], "c": []}
        with self.assertRaises(CycleError) as cm:
            resolve(g)
        self.assertEqual(cm.exception.cycle, ["a", "b", "a"])
        with self.assertRaises(CycleError) as cm2:
            levels(g)
        self.assertEqual(cm2.exception.cycle, ["a", "b", "a"])

    def test_longer_cycle_rotated_to_smallest(self):
        g = {"p": ["q"], "q": ["r"], "r": ["m"], "m": ["p"], "z": ["p"]}
        with self.assertRaises(CycleError) as cm:
            resolve(g)
        self.assertEqual(cm.exception.cycle, ["m", "p", "q", "r", "m"])
        for name in ("m", "p", "q", "r"):
            self.assertIn(name, str(cm.exception))

    def test_cycle_hidden_behind_acyclic_prefix(self):
        g = {"a": [], "b": ["a"], "c": ["b", "e"], "d": ["c"], "e": ["d"]}
        with self.assertRaises(CycleError) as cm:
            resolve(g)
        self.assert_cycle_ok(g, cm.exception.cycle)

    def test_multiple_cycles_any_valid_one(self):
        g = {"a": ["b"], "b": ["a"], "x": ["y"], "y": ["z"], "z": ["x"]}
        with self.assertRaises(CycleError) as cm:
            resolve(g)
        self.assert_cycle_ok(g, cm.exception.cycle)


class TestTypeErrors(unittest.TestCase):
    def test_non_dict_graph(self):
        with self.assertRaises(TypeError):
            resolve([("a", [])])

    def test_non_string_names(self):
        with self.assertRaises(TypeError):
            resolve({1: []})
        with self.assertRaises(TypeError):
            resolve({"a": [1]})
        with self.assertRaises(TypeError):
            levels({"a": [None]})


class TestPerformance(unittest.TestCase):
    def test_long_chain_no_recursion_error(self):
        n = 20000
        g = {f"n{i:05d}": [f"n{i-1:05d}"] if i else [] for i in range(n)}
        start = time.perf_counter()
        order = resolve(g)
        lv = levels(g)
        elapsed = time.perf_counter() - start
        self.assertEqual(order, [f"n{i:05d}" for i in range(n)])
        self.assertEqual(len(lv), n)
        self.assertLess(elapsed, 2.0)

    def test_long_cycle_detected_without_recursion_error(self):
        n = 5000
        g = {f"n{i:05d}": [f"n{(i-1) % n:05d}"] for i in range(n)}
        with self.assertRaises(CycleError) as cm:
            resolve(g)
        cyc = cm.exception.cycle
        self.assertEqual(len(cyc), n + 1)
        self.assertEqual(cyc[0], cyc[-1])
        self.assertEqual(cyc[0], "n00000")

    def test_wide_graph_is_fast(self):
        n = 50000
        g = {f"n{i:05d}": [f"n{i // 2:05d}"] if i else [] for i in range(n)}
        start = time.perf_counter()
        order = resolve(g)
        lv = levels(g)
        elapsed = time.perf_counter() - start
        self.assertTrue(is_valid_order(g, order))
        self.assertEqual(sum(len(x) for x in lv), n)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
