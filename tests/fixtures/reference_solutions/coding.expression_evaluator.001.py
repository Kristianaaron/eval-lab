import math
import re


class ExpressionError(ValueError):
    pass


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\*\*|//|[-+*/%(),])
    """,
    re.VERBOSE,
)

_FUNCS = {
    "min": (1, None),
    "max": (1, None),
    "abs": (1, 1),
    "round": (1, 2),
}


def _tokenize(expr):
    if not isinstance(expr, str):
        raise ExpressionError("expression must be a string")
    tokens = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if m is None:
            raise ExpressionError(f"unexpected character {expr[pos]!r} at {pos}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        text = m.group(kind)
        if kind == "num":
            if "." in text or "e" in text or "E" in text:
                value = float(text)
            else:
                value = int(text)
            tokens.append(("num", value))
        elif kind == "name":
            tokens.append(("name", text))
        else:
            tokens.append(("op", text))
    tokens.append(("end", None))
    if len(tokens) == 1:
        raise ExpressionError("empty expression")
    return tokens


class _Parser:
    def __init__(self, tokens, variables):
        self.tokens = tokens
        self.i = 0
        self.variables = variables

    def peek(self):
        return self.tokens[self.i]

    def take(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def is_op(self, *ops):
        kind, text = self.peek()
        return kind == "op" and text in ops

    def expect_op(self, op):
        if not self.is_op(op):
            kind, text = self.peek()
            raise ExpressionError(f"expected {op!r}, found {text!r}")
        self.take()

    # expression := term (('+'|'-') term)*
    def parse_expression(self):
        value = self.parse_term()
        while self.is_op("+", "-"):
            op = self.take()[1]
            rhs = self.parse_term()
            value = _apply(op, value, rhs)
        return value

    # term := unary (('*'|'/'|'//'|'%') unary)*
    def parse_term(self):
        value = self.parse_unary()
        while self.is_op("*", "/", "//", "%"):
            op = self.take()[1]
            rhs = self.parse_unary()
            value = _apply(op, value, rhs)
        return value

    # unary := ('+'|'-') unary | power
    def parse_unary(self):
        if self.is_op("-"):
            self.take()
            return _neg(self.parse_unary())
        if self.is_op("+"):
            self.take()
            return _pos(self.parse_unary())
        return self.parse_power()

    # power := atom ('**' unary)?
    def parse_power(self):
        base = self.parse_atom()
        if self.is_op("**"):
            self.take()
            exponent = self.parse_unary()
            return _apply("**", base, exponent)
        return base

    def parse_atom(self):
        kind, text = self.peek()
        if kind == "num":
            self.take()
            return text
        if kind == "name":
            self.take()
            if self.is_op("("):
                return self.parse_call(text)
            if text in _FUNCS and text not in self.variables:
                raise ExpressionError(f"function {text!r} used as a value")
            if text not in self.variables:
                raise ExpressionError(f"unknown name {text!r}")
            value = self.variables[text]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ExpressionError(f"variable {text!r} is not numeric")
            return value
        if self.is_op("("):
            self.take()
            value = self.parse_expression()
            self.expect_op(")")
            return value
        raise ExpressionError(f"unexpected token {text!r}")

    def parse_call(self, name):
        self.expect_op("(")
        if name not in _FUNCS:
            raise ExpressionError(f"unknown function {name!r}")
        args = []
        if self.is_op(")"):
            raise ExpressionError(f"{name}() needs at least one argument")
        while True:
            args.append(self.parse_expression())
            if self.is_op(","):
                self.take()
                continue
            break
        self.expect_op(")")
        lo, hi = _FUNCS[name]
        if len(args) < lo or (hi is not None and len(args) > hi):
            raise ExpressionError(f"wrong number of arguments for {name}")
        try:
            if name == "min":
                return min(args)
            if name == "max":
                return max(args)
            if name == "abs":
                return abs(args[0])
            if name == "round":
                if len(args) == 2:
                    if isinstance(args[1], float):
                        raise ExpressionError("ndigits must be an integer")
                    return round(args[0], args[1])
                return round(args[0])
        except ExpressionError:
            raise
        except (ValueError, OverflowError, TypeError) as exc:
            raise ExpressionError(str(exc))
        raise ExpressionError(f"unknown function {name!r}")


def _check(value):
    if isinstance(value, complex):
        raise ExpressionError("complex result")
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        raise ExpressionError("overflow")
    return value


def _neg(v):
    return _check(-v)


def _pos(v):
    return _check(+v)


def _apply(op, a, b):
    try:
        if op == "+":
            r = a + b
        elif op == "-":
            r = a - b
        elif op == "*":
            r = a * b
        elif op == "/":
            r = a / b
        elif op == "//":
            r = a // b
        elif op == "%":
            r = a % b
        elif op == "**":
            if isinstance(a, int) and isinstance(b, int) and b >= 0 and a.bit_length() * b > 100000:
                raise ExpressionError("result too large")
            r = a**b
        else:
            raise ExpressionError(f"unknown operator {op}")
    except ZeroDivisionError:
        raise ExpressionError("division by zero")
    except OverflowError:
        raise ExpressionError("overflow")
    return _check(r)


def evaluate(expr, variables=None):
    if variables is None:
        variables = {}
    tokens = _tokenize(expr)
    parser = _Parser(tokens, variables)
    value = parser.parse_expression()
    if parser.peek()[0] != "end":
        raise ExpressionError(f"unexpected token {parser.peek()[1]!r}")
    return value
