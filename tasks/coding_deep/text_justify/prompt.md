Implement three text layout functions. Only the standard library may be used (do not use `textwrap`).

## Required API

```
def full_justify(words, width) -> list[str]: ...
def wrap_paragraphs(text, width) -> str: ...
def render_table(rows, aligns=None) -> str: ...
```

## `full_justify(words, width)`

- `width` must be an `int` (not `bool`) `>= 1`; `words` must be a sequence of `str`, each non-empty, containing no whitespace characters, and no longer than `width`. Otherwise raise `ValueError`.
- Pack words greedily: a line takes as many words as fit with at least one space between consecutive words and total length `<= width`.
- Every returned line has length exactly `width`.
- A line that is neither the last line nor a single-word line is *fully justified*: the extra spaces are distributed as evenly as possible between words, and when they cannot be divided evenly the slots on the **left** get one more space than those on the right.
- The last line, and any line containing a single word, is *left-justified*: words separated by exactly one space and padded with spaces on the right.
- `full_justify([], width)` returns `[]`.

Example: `full_justify(["This", "is", "an", "example", "of", "text", "justification."], 16)` returns `["This    is    an", "example  of text", "justification.  "]`.

## `wrap_paragraphs(text, width)`

- `width` must be an `int` (not `bool`) `>= 1` and `text` must be a `str`; otherwise raise `ValueError`.
- Paragraphs are separated by one or more *blank lines* (lines that are empty or contain only whitespace). Leading and trailing blank lines are ignored. Inside a paragraph, line breaks are just whitespace: the paragraph's words are `paragraph.split()`.
- Each paragraph is wrapped greedily and left-aligned: a word is appended to the current line (with a single space) when the resulting line is `<= width` characters; otherwise a new line starts. Lines never have trailing spaces.
- A word longer than `width` is *hard-broken*: if the current line is not empty it is finished first; then the word is cut into consecutive chunks of exactly `width` characters, each emitted as its own line, except that the final chunk (of length `1..width`) becomes the start of a new current line so that following words may be packed after it as usual.
- The result is the paragraphs' lines joined with `"\n"`, with paragraphs separated by exactly one blank line (`"\n\n"` between them). There is no trailing newline. If `text` contains no words, return `""`.

## `render_table(rows, aligns=None)`

- `rows` is a sequence of rows; each row is a sequence of cells. All rows must have the same number of columns, and that number must be `>= 1`; otherwise raise `ValueError`. If `rows` is empty, return `""`.
- A cell is rendered as `""` when it is `None` and `str(cell)` otherwise.
- `aligns` is either `None` (every column left-aligned) or a `str`/sequence with exactly one entry per column, each being `'l'`, `'r'` or `'c'`; anything else raises `ValueError`.
- Column width = length of the longest rendered cell in that column, but at least 1.
- Padding within a column: `'l'` pads on the right, `'r'` pads on the left, `'c'` puts `extra // 2` spaces on the left and the rest on the right.
- Each row renders as `"| " + " | ".join(padded_cells) + " |"`. Immediately after the **first** row (the header) comes a rule line: `"|" + "|".join("-" * (width + 2) for each column) + "|"`. Lines are joined with `"\n"`; no trailing newline.

Example: `render_table([["name", "qty"], ["apple", 3], ["kiwi", 12]], "lr")` returns:

```
| name  | qty |
|-------|-----|
| apple |   3 |
| kiwi  |  12 |
```

Performance: justifying 20,000 words, wrapping a 200 KB text and rendering a 5,000-row table must each finish well under a second.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
