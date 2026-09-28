def _check_width(width):
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("width must be an int >= 1")


def full_justify(words, width):
    _check_width(width)
    if isinstance(words, (str, bytes)):
        raise ValueError("words must be a sequence of strings")
    words = list(words)
    for w in words:
        if not isinstance(w, str) or not w or any(c.isspace() for c in w) or len(w) > width:
            raise ValueError(f"invalid word {w!r}")
    lines = []
    i = 0
    n = len(words)
    while i < n:
        j = i
        length = 0
        while j < n and length + len(words[j]) + (j - i) <= width:
            length += len(words[j])
            j += 1
        group = words[i:j]
        is_last = j == n
        if is_last or len(group) == 1:
            line = " ".join(group)
            line += " " * (width - len(line))
        else:
            slots = len(group) - 1
            spaces = width - length
            base, extra = divmod(spaces, slots)
            parts = []
            for k, w in enumerate(group[:-1]):
                parts.append(w)
                parts.append(" " * (base + (1 if k < extra else 0)))
            parts.append(group[-1])
            line = "".join(parts)
        lines.append(line)
        i = j
    return lines


def _wrap_words(words, width):
    lines = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            chunks = [word[k : k + width] for k in range(0, len(word), width)]
            lines.extend(chunks[:-1])
            current = chunks[-1]
            continue
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrap_paragraphs(text, width):
    _check_width(width)
    if not isinstance(text, str):
        raise ValueError("text must be a str")
    paragraphs = []
    current = []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    blocks = []
    for para in paragraphs:
        words = " ".join(para).split()
        if words:
            blocks.append("\n".join(_wrap_words(words, width)))
    return "\n\n".join(blocks)


def render_table(rows, aligns=None):
    if isinstance(rows, (str, bytes)):
        raise ValueError("rows must be a sequence of rows")
    rows = [list(r) if not isinstance(r, (str, bytes)) else None for r in rows]
    if any(r is None for r in rows):
        raise ValueError("each row must be a sequence of cells")
    if not rows:
        return ""
    ncols = len(rows[0])
    if ncols < 1 or any(len(r) != ncols for r in rows):
        raise ValueError("all rows must have the same, non-zero number of columns")
    if aligns is None:
        aligns = ["l"] * ncols
    else:
        aligns = list(aligns)
        if len(aligns) != ncols or any(a not in ("l", "r", "c") for a in aligns):
            raise ValueError("aligns must have one of 'l', 'r', 'c' per column")
    rendered = [["" if c is None else str(c) for c in r] for r in rows]
    widths = [max(1, max(len(r[i]) for r in rendered)) for i in range(ncols)]
    out = []
    for idx, r in enumerate(rendered):
        cells = []
        for i, cell in enumerate(r):
            extra = widths[i] - len(cell)
            a = aligns[i]
            if a == "l":
                cells.append(cell + " " * extra)
            elif a == "r":
                cells.append(" " * extra + cell)
            else:
                left = extra // 2
                cells.append(" " * left + cell + " " * (extra - left))
        out.append("| " + " | ".join(cells) + " |")
        if idx == 0:
            out.append("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    return "\n".join(out)
