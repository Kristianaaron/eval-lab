Write a small arithmetic expression evaluator. Do **not** use `eval`, `exec`, `ast`, `compile` or any other facility that executes Python source; write a real tokenizer and parser. Only the standard library is allowed.

## Required API

```
class ExpressionError(ValueError): ...
def evaluate(expr: str, variables: dict | None = None) -> int | float: ...
```

## Language

- Numbers: integer literals (`42`) and floating point literals (`3.14`, `.5`, `2.`, `1e3`, `2.5E-2`). Integer literals produce `int`; anything with a `.` or an exponent produces `float`.
- Binary operators, lowest to highest precedence:
  1. `+`, `-` (left associative)
  2. `*`, `/`, `//`, `%` (left associative)
  3. unary `-` and unary `+` (prefix; may be repeated: `--3` is `3`)
  4. `**` (right associative: `2**3**2` is `512`)
  Unary minus binds *less* tightly than `**` on its left operand (`-2**2` is `-4`) but a unary operator may appear directly in the exponent (`2**-1` is `0.5`).
- Parentheses group sub-expressions.
- Identifiers match `[A-Za-z_][A-Za-z0-9_]*`. An identifier immediately followed by `(` is a function call; otherwise it is a variable looked up in `variables` (default: empty mapping).
- Functions (exactly these, all others are unknown names): `min(a, b, ...)` and `max(a, b, ...)` with one or more arguments, `abs(x)` with exactly one, `round(x)` and `round(x, ndigits)` with one or two. They behave exactly like the Python built-ins (so `round(2.5)` is `2` and `round(3.14159, 2)` is `3.14`).
- Whitespace (spaces, tabs, newlines) is allowed between tokens and ignored.
- Arithmetic follows Python semantics for `int`/`float` operands: `7 / 2` is `3.5`, `6 / 3` is `2.0` (a float), `7 // 2` is `3`, `-7 // 2` is `-4`, `-7 % 3` is `2`, `2 ** 10` is `1024` (an int), `2 ** -2` is `0.25`.

## Errors

Every failure must raise `ExpressionError` (or a subclass of it). Never let another exception type escape. Cases include:
- syntax errors: empty or whitespace-only input, unbalanced parentheses, missing operands (`2 +`, `* 3`), adjacent operands (`2 3`), unknown characters (`2 & 3`, `$`), trailing garbage, an empty call `min()`, a trailing comma;
- unknown names: a variable that is not in `variables`, or a call to an unknown function;
- wrong function arity (`abs(1, 2)`, `round()`, `round(1, 2, 3)`);
- calling a variable or using a function name as a value (`min + 1`, `x(1)` where `x` is a variable);
- division or modulo by zero with `/`, `//`, `%`, and `0 ** -1`;
- a variable whose value is not an `int` or `float` (`bool` counts as invalid);
- a result that would be complex (e.g. `(-8) ** 0.5`) or an overflow (`10.0 ** 400`).

Variable values that are `int` or `float` are used as-is. Do not mutate the `variables` mapping.

Performance: evaluating 2,000 expressions of roughly 30 tokens each must take well under one second, and an expression consisting of 3,000 terms added left to right (`1+1+...+1`) must evaluate without hitting the recursion limit.

Reply with exactly one fenced ```python block containing a complete module that defines these names. Do not include tests or example usage outside the block.
