Implement a reconciliation routine that compares two sets of rows (as produced by `csv.DictReader`) by key. Only the standard library may be used.

## Required API

```
class ReconcileError(Exception): ...

class ReconcileResult:
    added: dict       # key -> right row (the original mapping object)
    removed: dict     # key -> left row (the original mapping object)
    changed: dict     # key -> {field: (left_value, right_value), ...}
    unchanged: list   # sorted list of keys
    def summary(self) -> str: ...

def values_equal(a, b) -> bool: ...
def reconcile(left_rows, right_rows, key, ignore_fields=()) -> ReconcileResult: ...
```

## Rows and keys

- `left_rows` and `right_rows` are iterables of mappings (`dict`-like) from field name (`str`) to a value. Values are usually `str` but may be `None` or numbers.
- A value is *normalised* as: `None` becomes `""`; anything else becomes `str(value)`.
- `key` is either a single field name (`str`) or a non-empty sequence of field names (composite key). Anything else raises `ValueError`.
- A row's *key value* is the normalised value of the key field for a single-field key, or a `tuple` of normalised values for a composite key. Key values are compared as exact strings (`"1"` and `"1.0"` are different keys; whitespace is significant).
- A row that is not a mapping, or that lacks a key field, raises `ReconcileError`.
- The same key value appearing twice on one side raises `ReconcileError`; its message must contain the word `left` or `right` (whichever side) and the key value.

## Comparison rule (`values_equal`)

`values_equal(a, b)` normalises both values, strips leading/trailing whitespace, and returns `True` when:
- the stripped strings are identical (case-sensitive: `"abc"` != `"ABC"`), or
- both strings are numeric literals matching `[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?` (after stripping) **and** they denote exactly the same number. The comparison must be exact, not `float`-based: `"1.0"` equals `"1"`, `"1e3"` equals `"1000"`, `"+5"` equals `"5"`, `"007"` equals `"7"`, but `"12345678901234567890"` does **not** equal `"12345678901234567891"` and `"0.1"` does **not** equal `"0.10000000000000001"`.

Otherwise it returns `False`. Note `""` equals `""`, `""` does not equal `"0"`, and `"abc"` equals `" abc "`.

## Reconciliation

- Keys present only on the right go to `added`; only on the left go to `removed`.
- For keys present on both sides, the compared fields are the union of both rows' field names minus the key field(s) minus `ignore_fields`. A field absent from one row is treated as `""` on that side. If every compared field is `values_equal`, the key goes to `unchanged`; otherwise it goes to `changed` with a dict of the differing fields, each mapped to `(left_normalised, right_normalised)` (normalised, **not** stripped), fields in sorted order.
- `added`, `removed` and `changed` are `dict`s whose keys are inserted in sorted order; `unchanged` is a sorted list. Each key appears in exactly one of the four.
- Inputs are never mutated. Reconciling 20,000 rows per side must take well under a second.

## `summary()`

Returns a string of lines joined with `"\n"` (no trailing newline):

1. `added=<A> removed=<R> changed=<C> unchanged=<U>` with the four counts.
2. One line `- <key>` per removed key, in sorted order.
3. One line `+ <key>` per added key, in sorted order.
4. One line `~ <key>: <field>=<left!r}-><right!r>` per changed key in sorted order, where the differing fields are listed in sorted order separated by `", "`, and values are shown with Python `repr` (e.g. `price='1.5'->'2.0'`).

`<key>` is the key value itself for a single-field key, or the components joined with `|` for a composite key. Example:

```
added=1 removed=1 changed=1 unchanged=2
- 41
+ 44
~ 42: price='1.5'->'2.0', qty='3'->'4'
```

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
