# flowkit

A small, dependency-free toolkit for batch record pipelines: parse text
inputs into records, transform and window them, aggregate statistics and write
results to a sink. Used by the nightly reporting job.

## Statistics contract (aggregate.py)

`summarize(values)` returns a `Stats` object with:

- `count`, `total`, `minimum`, `maximum`
- `mean` — arithmetic mean rounded to 6 decimals
- `median` — for an odd count, the middle element of the sorted sample; for an
  even count, the arithmetic mean of the two middle elements
- `p95` — nearest-rank percentile: the element at position `ceil(0.95 * n)` of
  the sorted sample (1-based), so for n = 20 it is the 19th smallest value and
  for n = 40 the 38th. Never interpolated.

`percentile(values, p)` follows the same nearest-rank rule for any `p` in
(0, 1]; `p = 1.0` is the maximum. `p <= 0` or `p > 1` raises `ValueError`.

## Layout

- `config.py` — INI-style configuration with `${ENV}` interpolation
- `records.py` — the `Record` type and key extraction
- `parsers/` — `csvlite` (quoted CSV) and `kv` (key=value lines)
- `transforms.py` — pure per-record transformations
- `windowing.py` — tumbling and sliding time windows
- `aggregate.py` — group-by and descriptive statistics
- `dedupe.py` — keep-latest de-duplication
- `retry.py` — backoff schedule helpers
- `validate.py` — declarative record checks
- `formats.py` — text rendering of statistics tables
- `scheduler.py` — next-run computation for simple schedules
- `sink.py` — JSONL / in-memory sinks
- `pipeline.py` — stage composition and the nightly report entry point
- `cli.py` — `report` and `export` commands
