import re


class PathError(ValueError):
    pass


_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_INT_RE = re.compile(r"[+-]?\d+")


# Selector representations:
#   ("root",), ("child", name), ("wild",), ("index", n), ("slice", start, end, step),
#   ("union", [selectors]), ("recursive", selector)


class _Parser:
    def __init__(self, path):
        self.s = path
        self.i = 0

    def error(self, msg):
        raise PathError(f"{msg} at position {self.i} in {self.s!r}")

    def peek(self, n=1):
        return self.s[self.i : self.i + n]

    def at_end(self):
        return self.i >= len(self.s)

    def skip_ws(self):
        while not self.at_end() and self.s[self.i] in " \t":
            self.i += 1

    def parse(self):
        if not isinstance(self.s, str):
            raise PathError("path must be a string")
        if self.peek() != "$":
            self.error("path must start with '$'")
        self.i += 1
        segments = []
        while not self.at_end():
            segments.append(self.parse_segment())
        return segments

    def parse_segment(self):
        if self.peek(2) == "..":
            self.i += 2
            if self.at_end():
                self.error("'..' must be followed by a selector")
            if self.peek() == "[":
                inner = self.parse_bracket()
            else:
                inner = self.parse_dot_selector()
            return ("recursive", inner)
        if self.peek() == ".":
            self.i += 1
            return self.parse_dot_selector()
        if self.peek() == "[":
            return self.parse_bracket()
        self.error("unexpected character")

    def parse_dot_selector(self):
        if self.peek() == "*":
            self.i += 1
            return ("wild",)
        m = _NAME_RE.match(self.s, self.i)
        if not m:
            self.error("expected a name or '*'")
        self.i = m.end()
        return ("child", m.group())

    def parse_bracket(self):
        assert self.peek() == "["
        self.i += 1
        self.skip_ws()
        if self.peek() == "*":
            self.i += 1
            self.skip_ws()
            self.expect("]")
            return ("wild",)
        items = []
        first = True
        while True:
            self.skip_ws()
            item = self.parse_bracket_item(allow_slice=first)
            items.append(item)
            self.skip_ws()
            if self.peek() == ",":
                if item[0] == "slice":
                    self.error("slices are not allowed in unions")
                self.i += 1
                first = False
                continue
            break
        self.expect("]")
        if len(items) == 1:
            return items[0]
        return ("union", items)

    def expect(self, ch):
        if self.peek() != ch:
            self.error(f"expected {ch!r}")
        self.i += 1

    def parse_int(self):
        m = _INT_RE.match(self.s, self.i)
        if not m:
            return None
        self.i = m.end()
        return int(m.group())

    def parse_bracket_item(self, allow_slice):
        ch = self.peek()
        if ch in ("'", '"'):
            return ("child", self.parse_quoted())
        if ch == "" or ch == "]":
            self.error("empty bracket item")
        start = self.parse_int()
        self.skip_ws()
        if self.peek() == ":":
            if not allow_slice:
                self.error("slice not allowed here")
            self.i += 1
            self.skip_ws()
            end = self.parse_int()
            self.skip_ws()
            step = None
            if self.peek() == ":":
                self.i += 1
                self.skip_ws()
                step = self.parse_int()
                if step == 0:
                    self.error("slice step cannot be zero")
            return ("slice", start, end, step)
        if start is None:
            self.error("expected an index, a slice or a quoted name")
        if self.peek() not in ("", "]", ",") and not self.peek().isspace():
            self.error("bad index")
        return ("index", start)

    def parse_quoted(self):
        quote = self.s[self.i]
        self.i += 1
        out = []
        while True:
            if self.at_end():
                self.error("unterminated string")
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 1
                if self.at_end():
                    self.error("unterminated escape")
                esc = self.s[self.i]
                if esc in ("\\", "'", '"'):
                    out.append(esc)
                else:
                    self.error("invalid escape")
                self.i += 1
                continue
            if ch == quote:
                self.i += 1
                return "".join(out)
            out.append(ch)
            self.i += 1


def _children(node):
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return node
    return ()


def _preorder(node):
    """Iterative pre-order traversal yielding every node (node first, then descendants)."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        kids = _children(n)
        if kids:
            stack.extend(reversed(kids))


def _select(sel, node):
    kind = sel[0]
    if kind == "child":
        if isinstance(node, dict) and sel[1] in node:
            return [node[sel[1]]]
        return []
    if kind == "wild":
        return list(_children(node))
    if kind == "index":
        if isinstance(node, list):
            i = sel[1]
            if -len(node) <= i < len(node):
                return [node[i]]
        return []
    if kind == "slice":
        if isinstance(node, list):
            return node[sel[1] : sel[2] : sel[3]]
        return []
    if kind == "union":
        out = []
        for item in sel[1]:
            out.extend(_select(item, node))
        return out
    if kind == "recursive":
        inner = sel[1]
        out = []
        for n in _preorder(node):
            out.extend(_select(inner, n))
        return out
    raise PathError(f"unknown selector {kind}")


def query(data, path):
    segments = _Parser(path).parse()
    current = [data]
    for seg in segments:
        nxt = []
        for node in current:
            nxt.extend(_select(seg, node))
        current = nxt
    return current
