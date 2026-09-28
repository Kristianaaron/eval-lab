import re
from collections.abc import Mapping
from fractions import Fraction


class ReconcileError(Exception):
    pass


_NUM_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\Z")


def _norm(value):
    return "" if value is None else str(value)


def values_equal(a, b):
    sa = _norm(a).strip()
    sb = _norm(b).strip()
    if sa == sb:
        return True
    if _NUM_RE.match(sa) and _NUM_RE.match(sb):
        return Fraction(sa) == Fraction(sb)
    return False


class ReconcileResult:
    def __init__(self, added, removed, changed, unchanged, key_fields):
        self.added = added
        self.removed = removed
        self.changed = changed
        self.unchanged = unchanged
        self._composite = key_fields is not None

    def _fmt_key(self, key):
        if isinstance(key, tuple):
            return "|".join(key)
        return key

    def summary(self):
        lines = [
            f"added={len(self.added)} removed={len(self.removed)} "
            f"changed={len(self.changed)} unchanged={len(self.unchanged)}"
        ]
        for k in self.removed:
            lines.append(f"- {self._fmt_key(k)}")
        for k in self.added:
            lines.append(f"+ {self._fmt_key(k)}")
        for k, diffs in self.changed.items():
            parts = ", ".join(f"{f}={l!r}->{r!r}" for f, (l, r) in diffs.items())
            lines.append(f"~ {self._fmt_key(k)}: {parts}")
        return "\n".join(lines)


def _key_fields(key):
    if isinstance(key, str):
        return [key], False
    if isinstance(key, (bytes, Mapping)) or not hasattr(key, "__iter__"):
        raise ValueError("key must be a field name or a sequence of field names")
    fields = list(key)
    if not fields or any(not isinstance(f, str) for f in fields):
        raise ValueError("key must be a non-empty sequence of field names")
    return fields, True


def _index(rows, fields, composite, side):
    index = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ReconcileError(f"{side} row is not a mapping: {row!r}")
        for f in fields:
            if f not in row:
                raise ReconcileError(f"{side} row is missing key field {f!r}")
        if composite:
            k = tuple(_norm(row[f]) for f in fields)
        else:
            k = _norm(row[fields[0]])
        if k in index:
            raise ReconcileError(f"duplicate key {k!r} in {side} rows")
        index[k] = row
    return index


def reconcile(left_rows, right_rows, key, ignore_fields=()):
    fields, composite = _key_fields(key)
    ignore = set(ignore_fields) | set(fields)
    left = _index(left_rows, fields, composite, "left")
    right = _index(right_rows, fields, composite, "right")

    added = {}
    removed = {}
    changed = {}
    unchanged = []
    for k in sorted(set(left) | set(right)):
        if k not in left:
            added[k] = right[k]
            continue
        if k not in right:
            removed[k] = left[k]
            continue
        lrow, rrow = left[k], right[k]
        diffs = {}
        for f in sorted((set(lrow) | set(rrow)) - ignore):
            lv, rv = lrow.get(f), rrow.get(f)
            if not values_equal(lv, rv):
                diffs[f] = (_norm(lv), _norm(rv))
        if diffs:
            changed[k] = diffs
        else:
            unchanged.append(k)
    return ReconcileResult(added, removed, changed, unchanged, fields if composite else None)
