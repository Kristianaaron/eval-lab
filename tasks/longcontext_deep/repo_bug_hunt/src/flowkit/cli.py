"""Command-line entry point: ``python -m flowkit.cli report <config> <input.csv>``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from flowkit.config import parse_config
from flowkit.errors import FlowkitError
from flowkit.formats import render_report
from flowkit.parsers.csvlite import parse_csv
from flowkit.pipeline import Pipeline, nightly_report
from flowkit.sink import JsonlSink
from flowkit.transforms import coerce
from flowkit.validate import in_range, required


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flowkit")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="render the nightly latency report")
    report.add_argument("config")
    report.add_argument("input")
    report.add_argument("--field", default="latency_ms")
    report.add_argument("--group", default="service")
    export = sub.add_parser("export", help="normalise a CSV into JSONL")
    export.add_argument("input")
    export.add_argument("output")
    export.add_argument("--dedupe", nargs="*", default=[])
    return parser


def cmd_report(args: argparse.Namespace) -> int:
    config = parse_config(Path(args.config).read_text(encoding="utf-8"), os.environ)
    with Path(args.input).open(encoding="utf-8") as fh:
        records = list(parse_csv(fh, timestamp_field="ts"))
    pipeline = Pipeline().map(coerce(**{args.field: "float"}))
    valid = [r for r in pipeline.run(records) if not required(args.group, args.field)(r)]
    valid = [r for r in valid if not in_range(args.field, 0, 10**7)(r)]
    report = nightly_report(valid, config, field=args.field, group_field=args.group)
    sys.stdout.write(render_report(report))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with Path(args.input).open(encoding="utf-8") as fh:
        records = list(parse_csv(fh, timestamp_field="ts"))
    pipeline = Pipeline()
    if args.dedupe:
        pipeline.dedupe(*args.dedupe)
    written = pipeline.run_to(records, JsonlSink(args.output, append=False))
    sys.stderr.write(f"wrote {written} record(s) to {args.output}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "report":
            return cmd_report(args)
        if args.command == "export":
            return cmd_export(args)
    except FlowkitError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
