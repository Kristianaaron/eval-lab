# Inventory service: fix the regressions

You are working in a small Python 3.12 project (no third-party dependencies) that
manages warehouse stock: the `inventory/` package holds the domain models, an
in-memory and a JSON-file repository, pricing/discount rules, a service layer, a
settings loader and a small CLI. The visible test suite lives in `tests/` and is
run with:

```
python -m unittest discover -s tests -t .
```

Three tests currently fail. On top of that, two problems were reported by users
that are *not* covered by the visible tests. All of them are real defects in the
package; none of them is a test bug.

## Failing tests

- `tests.test_pagination.PaginateTests.test_first_page_holds_page_size_items`
- `tests.test_pricing.DiscountTests.test_percent_discount_rounds_half_up`
- `tests.test_utils.ParseTimestampTests.test_explicit_offset_is_converted_to_utc`

## User-reported problems

1. **Warehouses bleed into each other.** A nightly job builds one
   `InventoryService()` per warehouse (without passing a repository), registers
   products and records receipts on the first one, and then calls
   `stock_level()` on the second. The second warehouse reports the first
   warehouse's quantities instead of raising `NotFoundError` for a SKU it never
   registered. The same thing happens with the CLI: running `inventory add ...`
   and then `inventory list` in the same process (without `--config`) shows the
   product although every invocation is supposed to start from an empty store.
2. **Broken settings files crash the CLI.** With a settings file that is not
   valid JSON, `inventory --config settings.json list` prints a Python traceback
   instead of the one-line `error: ...` message and exit code `2` that every
   other configuration problem produces. The docstring of `inventory/config.py`
   states the intended contract.

## What we need

- Find and fix the **root cause** of every defect above. There are five
  distinct bugs in five different places; each fix is small once you have found
  it. Do not paper over symptoms (for example by special-casing inputs in the
  CLI or catching exceptions at the call site).
- Keep the package's documented behaviour and public API intact: money is
  `Decimal` rounded half-up to two places, timestamps are timezone-aware UTC,
  pagination is 1-based, and every deliberate error derives from
  `inventory.errors.InventoryError`.
- **Do not modify, delete or add anything under `tests/`.** The visible suite
  must pass unchanged, and a larger hidden suite covering the same behaviours
  (plus regression checks on everything that already works) will be run
  against your workspace afterwards.
- Do not add dependencies.

When you are done, run the visible test suite and make sure every test passes.
