# Ledger: multi-currency, account statements and CSV export

The `ledger/` package is a small double-entry bookkeeping library (Python 3.12,
standard library only) with JSON persistence (`ledger/store.py`), a text report
(`ledger/reports.py`) and a CLI (`ledger/cli.py`). Everything works and the
visible suite passes:

```
python -m unittest discover -s tests -t .
```

Implement the three features below **exactly** as specified. Formats, names,
signatures, error types and messages are contractual: a hidden test suite
checks them character for character, alongside the visible suite, which must
keep passing unchanged. Do not modify anything under `tests/`, and do not add
dependencies.

---

## Feature 1: multi-currency postings

### `ledger/currency.py` (new module)

```python
class RateTable:
    def __init__(self, base: str = "USD") -> None: ...
    base: str                                   # normalised (upper-case) base code
    def set_rate(self, code, rate) -> None: ...
    def rate(self, code) -> Decimal: ...
    def convert(self, amount, from_code, to_code) -> Decimal: ...
    def rates(self) -> dict[str, Decimal]: ...  # every non-base currency -> rate
    def currencies(self) -> list[str]: ...      # sorted codes, base included
```

- A currency *code* is exactly three ASCII letters; codes are normalised to
  upper case everywhere (`"eur"` and `"EUR"` are the same currency). Anything
  else raises `CurrencyError` (see below) with message `invalid currency code:
  '<value as given>'` (Python `repr` of the original string).
- A *rate* is the value of one unit of the currency expressed in the base
  currency (`set_rate("EUR", "1.08")` means 1 EUR = 1.08 base units). The value
  may be a `Decimal`, `int` or `str`; it must be strictly positive, otherwise
  `CurrencyError("rate must be positive")`. Setting a rate for the base
  currency raises `CurrencyError("cannot set a rate for the base currency")`.
  Setting a rate again replaces the previous one.
- `rate(code)` returns `Decimal(1)` for the base currency and the stored rate
  otherwise. An unknown currency raises `CurrencyError("unknown currency: XXX")`
  (normalised code).
- `convert(amount, from_code, to_code)`: when both codes normalise to the same
  currency the amount is returned unchanged (no rounding, no rate lookup
  required). Otherwise the result is `amount * rate(from) / rate(to)` rounded to
  two decimal places with `ROUND_HALF_UP` (reuse `ledger.money.quantize`).
- `CurrencyError` is a new exception in `ledger/errors.py` deriving from
  `LedgerError`.

### Postings and the ledger

- `Posting` gets a third field `currency: str | None = None`, in that position
  (`Posting("1000", Decimal("5"), "EUR")` must work positionally). A given
  code is normalised to upper case in `__post_init__`; an invalid code raises
  `CurrencyError`. `None` means "the ledger's base currency".
- `Ledger.__init__(self, base_currency: str = "USD")`. The ledger exposes
  `base_currency` (normalised) and `rates`, a `RateTable` with that base.
- `Ledger.post(...)`: a posting with `currency=None` is stored with the base
  currency filled in, so every posting inside a stored `Transaction` has an
  explicit code. A transaction must balance **in the base currency**: convert
  each posting's amount to the base (each conversion rounded as above), and the
  sum must be zero, otherwise `UnbalancedTransactionError` whose `difference`
  is that base-currency sum. Unknown currencies raise `CurrencyError` before
  anything is stored. Rates are not versioned: the table as it is at the time
  of the call is what applies, both for posting and for reporting.
- `Ledger.balance(code, as_of=None, currency=None)`: sum of the account's
  postings (dated `<= as_of` when given), **each converted individually** to
  `currency` (default: the base currency) with `rates.convert`, i.e. round per
  posting, then add. Unknown currency raises `CurrencyError`.
- `Transaction` gets `amount_for(account, rates, currency) -> Decimal`: the sum
  of that transaction's postings for `account`, each converted to `currency`
  with the given `RateTable`.

### Persistence (`ledger/store.py`)

- The document gains `"base_currency": "USD"` and `"rates": {"EUR": "1.08", ...}`
  (rate strings are `str(Decimal)` of whatever was set, keys sorted), and each
  posting object gains `"currency": "EUR"`.
- Files written by the old format (no `base_currency`, no `rates`, postings
  without `currency`) must still load: base `USD`, empty rate table, postings in
  the base currency.

### CLI

- New global option `--base-currency CODE` (default `USD`), used only when the
  ledger file does not exist yet and a new ledger is created.
- New subcommand `rate CODE RATE`: sets the rate, saves, prints
  `rate CODE = RATE` where RATE is the `str()` of the stored `Decimal`
  (`rate EUR = 1.08`).
- `post` postings accept `ACCOUNT:AMOUNT` or `ACCOUNT:AMOUNT:CURRENCY`. Any
  other shape is `ValidationError` with message
  `invalid posting '<text>' (expected ACCOUNT:AMOUNT or ACCOUNT:AMOUNT:CURRENCY)`.
- `balance` gains `--currency CODE`.

---

## Feature 2: account statement

Add `statement(ledger, code, start, end, currency=None) -> str` to
`ledger/reports.py` (`start`/`end` are `datetime.date`, both inclusive;
`currency` defaults to the ledger base) and a CLI subcommand
`statement CODE START END [--currency CODE]` that prints it followed by a
newline. Amounts are formatted with `ledger.money.format_amount`. The exact
layout (every line from the opening balance on is exactly 62 characters wide):

```
Statement for 1000 Cash
Period 2024-01-01 to 2024-01-31 (USD)
Opening balance                                       1,000.00
2024-01-05  Office supplies                 -45.50      954.50
2024-01-20  Client payment                2,000.00    2,954.50
Closing balance                                       2,954.50
```

1. `"Statement for " + code + " " + account name`
2. `"Period " + start ISO + " to " + end ISO + " (" + currency + ")"`
3. `"Opening balance"` left-justified to 50, then the opening balance
   right-justified to 12 (line width 62). The opening balance is
   `ledger.balance(code, as_of=start - 1 day, currency=currency)`.
4. One line per transaction in the period that touches the account, ordered by
   `(date, id)`: date ISO (10) + two spaces + memo truncated to 26 characters
   and left-justified to 26 + the transaction's amount for the account
   (`amount_for`, in the statement currency) right-justified to 12 + the running
   balance right-justified to 12 (width 62). The running balance starts at the
   opening balance and accumulates each line's amount.
5. `"Closing balance"` left-justified to 50 + the final running balance
   right-justified to 12. With no transactions in the period it equals the
   opening balance.

Lines are joined with `"\n"` and there is **no** trailing newline. Unknown
accounts raise `UnknownAccountError`; `end < start` raises `ValidationError`.

---

## Feature 3: CSV export

Add `ledger/export.py` with:

```python
CSV_HEADER = ["transaction_id", "date", "memo", "account", "amount", "currency"]
def export_csv(ledger, start=None, end=None) -> str: ...
def write_csv(ledger, path, start=None, end=None) -> None: ...   # writes export_csv() to path (UTF-8)
```

- One row per posting; transactions ordered by `(date, id)` (filtered by the
  inclusive `start`/`end` dates when given), postings in stored order.
- Columns: transaction id as an integer, date ISO, memo, account code, amount
  as a plain two-decimal number without thousands separators and with a leading
  `-` for negatives (`2000.00`, `-45.50`), currency code.
- Escaping (RFC 4180, minimal quoting): a field containing a comma, a double
  quote, `\n` or `\r` is wrapped in double quotes with every embedded double
  quote doubled; all other fields are written bare. Every row, including the
  header and the last data row, ends with `\n` (LF only). An empty ledger
  produces just the header line.
- CLI subcommand `export [--start DATE] [--end DATE] [--out PATH]`: writes the
  CSV to `PATH` when given (printing nothing), otherwise writes it to stdout
  verbatim.

---

Work through the package (`models`, `book`, `store`, `reports`, `cli`, the new
`currency` and `export` modules) and keep the existing public behaviour intact.
Run the visible suite when you are done; write your own quick checks for the
new behaviour, since the hidden suite is strict about the formats above.
