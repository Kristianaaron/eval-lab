Implement a query engine for a subset of JSONPath over plain Python data (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`). Only the standard library may be used.

## Required API

```
class PathError(ValueError): ...
def query(data, path: str) -> list: ...
```

`query` returns a `list` of the matched values (the actual objects from `data`, not copies; duplicates are possible). Path syntax errors raise `PathError` **before** any data is inspected (an invalid path fails even on empty data). Any other data shape simply produces no matches; querying never raises for data reasons.

## Path grammar

A path is `$` followed by zero or more segments. No whitespace is allowed anywhere **except** inside square brackets around items and separators (`[ 0 , 1 ]` is fine; `$ .a` and `$. a` are errors).

Segments:
- `.name` — child of a dict by key. `name` matches `[A-Za-z_][A-Za-z0-9_-]*`. Applies to dicts only; anything else yields no match.
- `['name']` / `["name"]` — child by key, allowing any characters. Escapes inside the quotes: `\\`, `\'`, `\"`; any other backslash sequence is a syntax error.
- `.*` or `[*]` — wildcard: all values of a dict (insertion order) or all elements of a list.
- `[n]` — list element by integer index; negative indices count from the end; out-of-range yields no match. Lists only.
- `[start:end:step]` — Python slice semantics (any part may be omitted, e.g. `[1:]`, `[:-1]`, `[::2]`, `[::-1]`); a step of `0` is a syntax error. Lists only.
- `[a, b, ...]` — union of two or more items, each an integer index or a quoted name (mixing is allowed; slices are not allowed inside a union). Matches are produced item by item in the written order; each item behaves like the single selector of the same kind.
- `..name`, `..*`, `..[...]` — recursive descent: the selector after `..` is applied to the current node and to every descendant. Nodes are visited in **pre-order** (a node before its descendants; dict values in insertion order; list elements in index order), and matches are emitted in visit order.
- `$` alone returns `[data]`.

Syntax errors (non-exhaustive): empty path, a path not starting with `$`, `$.`, `$[`, `$foo`, `$..`, `$...a`, `$.a.`, `[]`, `[1.5]`, `[a]` (unquoted name in brackets), `['a` (unterminated), `[1:2:0]`, `[*,1]`, `[1:2,3]`, trailing characters after a segment, and stray characters anywhere.

## Semantics details

- Segments are applied left to right: each segment maps the current list of nodes to the concatenation of its results for each node, preserving order.
- Multiple matches of the same object (for example `$[0,0]`) are returned as many times as they are matched.
- `bool` keys/values are ordinary values. Dict keys are always strings.

## Performance and robustness

- `$..*` on a document with 20,000 nodes must finish well under a second.
- The engine must handle documents nested 5,000 levels deep (e.g. a list inside a list 5,000 times) without raising `RecursionError`; traversal has to be iterative.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
