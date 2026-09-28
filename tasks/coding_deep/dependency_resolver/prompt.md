Implement a deterministic dependency resolver. Only the standard library may be used.

## Input

A *graph* is a `dict` mapping a node name (`str`) to an iterable of the names (`str`) of the nodes it **depends on** (they must come before it). Dependency lists may be in any order and may contain duplicates. A name that appears only as a dependency, never as a key, is a *missing dependency*.

## Required API

```
class ResolverError(Exception): ...
class CycleError(ResolverError):          # attribute: cycle -> list[str]
class MissingDependencyError(ResolverError):  # attribute: missing -> list[tuple[str, str]]

def resolve(graph, targets=None) -> list[str]: ...
def levels(graph, targets=None) -> list[list[str]]: ...
```

## Semantics

- `resolve(graph)` returns a list containing every node exactly once such that each node appears **after** all of its dependencies. Among all valid orderings it must return the **lexicographically smallest** one (compare orderings as Python lists of strings). Equivalently: repeatedly emit the smallest (by `str` ordering) node whose dependencies have all been emitted. An empty graph returns `[]`.
- `levels(graph)` groups nodes into execution layers: level 0 holds the nodes with no dependencies; a node is in level `k` when all its dependencies are in levels `< k` and at least one is in level `k - 1` (i.e. `k` is the length of the longest dependency chain below it). Each level is sorted, and the returned list has no empty levels. An empty graph returns `[]`.
- `targets`: when given (an iterable of node names), only the targets and their transitive dependencies are considered, and both functions behave as if the graph contained only those nodes. Nodes outside that closure are ignored entirely, including any cycles or missing dependencies among them. A target that is not a key of the graph raises `KeyError`. `targets=None` (the default) means the whole graph; an empty `targets` yields `[]`.
- Errors, checked in this order:
  1. `TypeError` if `graph` is not a `dict`, or if any key or dependency name is not a `str`.
  2. `MissingDependencyError` if any considered node depends on a name that is not a key of the graph. Its `missing` attribute is the sorted list of unique `(node, missing_dependency)` pairs.
  3. `CycleError` if the considered sub-graph contains a cycle. Its `cycle` attribute is a list `[n0, n1, ..., nk, n0]` where every consecutive pair `(ni, ni+1)` means "`ni` depends on `ni+1`", the first and last element are the same node, no other node repeats, and `n0` is the smallest (by `str` ordering) node in that cycle. A self-dependency `a -> a` is reported as `['a', 'a']`. If the graph contains several cycles, any one of them may be reported.
- The error message (`str(exc)`) of both custom errors must mention every node name involved.
- Never mutate the input graph.
- Both functions must handle graphs with 50,000 nodes, including a single dependency chain of length 20,000 (`n1 -> n0`, `n2 -> n1`, ...), in well under two seconds and without raising `RecursionError`.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
