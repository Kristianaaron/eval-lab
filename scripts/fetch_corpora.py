#!/usr/bin/env python3
"""Fetch standard public-domain corpora for perplexity and register them as tasks.

The bundled corpora under ``tasks/perplexity`` are small so the benchmark runs
in seconds offline. For publication-grade perplexity numbers run this script
once (needs network access) to download larger texts into
``tasks/perplexity_external/<name>/data/corpus.txt`` (gitignored) together with
a generated ``task.yaml``; then ``eval-lab perplexity configs/suites/perplexity-external.yaml``.

Sources are Project Gutenberg plain-text books (public domain). Gutenberg
license headers/footers are stripped. Add your own entries to SOURCES (e.g. a
local WikiText-2 test split) — anything reachable by URL or file path works.
"""

from __future__ import annotations

import argparse
import re
import urllib.request
from pathlib import Path

SOURCES = {
    "gutenberg_alice": ("https://www.gutenberg.org/cache/epub/11/pg11.txt", "Alice's Adventures in Wonderland (Carroll)"),
    "gutenberg_time_machine": ("https://www.gutenberg.org/cache/epub/35/pg35.txt", "The Time Machine (Wells)"),
    "gutenberg_pride": ("https://www.gutenberg.org/cache/epub/1342/pg1342.txt", "Pride and Prejudice (Austen)"),
    "gutenberg_origin": ("https://www.gutenberg.org/cache/epub/1228/pg1228.txt", "On the Origin of Species (Darwin)"),
}

_START = re.compile(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.IGNORECASE)
_END = re.compile(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG EBOOK", re.IGNORECASE)

TASK_TEMPLATE = """schema_version: "1.0"
id: perplexity.external.{slug}.001
name: 'Perplexity: {name}'
description: 'External public-domain corpus fetched by scripts/fetch_corpora.py ({chars} chars).'
version: 1
level: model
status: active
data_partition: held_out_evaluation
labels:
  domains: ['long_context']
  capabilities: ['long_horizon_coherence']
  modalities: ['text']
  difficulty: medium
  intervention: ['quantization', 'expert_pruning']
input:
  instruction_file: 'prompt.md'
  attachments: ['data/corpus.txt']
execution:
  runner: perplexity
  timeout_seconds: 3600
  parameters: {{"window_chars": 6000, "max_chars": {max_chars}}}
oracle:
  - type: perplexity
    weight: 1.0
    required: false
    config: {{"reference": 1000.0}}
"""


def strip_gutenberg(text: str) -> str:
    m = _START.search(text)
    if m:
        text = text[m.end():]
    m = _END.search(text)
    if m:
        text = text[: m.start()]
    return text.strip() + "\n"


def fetch(url: str) -> str:
    if Path(url).is_file():
        return Path(url).read_text(encoding="utf-8", errors="replace")
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed public URLs
        return resp.read().decode("utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tasks/perplexity_external")
    ap.add_argument("--max-chars", type=int, default=400_000)
    ap.add_argument("--only", nargs="*", help="subset of SOURCES keys")
    args = ap.parse_args()
    out = Path(args.out)
    suite_tasks: list[str] = []
    for slug, (url, name) in SOURCES.items():
        if args.only and slug not in args.only:
            continue
        pkg = out / slug
        (pkg / "data").mkdir(parents=True, exist_ok=True)
        try:
            text = strip_gutenberg(fetch(url))
        except Exception as exc:  # network / policy failures are reported, not hidden
            print(f"{slug}: FAILED to fetch {url}: {exc}")
            continue
        (pkg / "data" / "corpus.txt").write_text(text, encoding="utf-8")
        (pkg / "prompt.md").write_text(f"Perplexity corpus: {name}. Scored token-by-token; no generation.\n")
        (pkg / "task.yaml").write_text(
            TASK_TEMPLATE.format(slug=slug, name=name.replace("'", ""), chars=len(text), max_chars=args.max_chars)
        )
        suite_tasks.append(f"perplexity.external.{slug}.001")
        print(f"{slug}: {len(text)} chars -> {pkg}")
    if suite_tasks:
        suite = Path("configs/suites/perplexity-external.yaml")
        suite.write_text(
            "schema_version: '1.0'\nid: suite.benchmark.perplexity_external.001\n"
            "name: Perplexity — external corpora\ndescription: Public-domain corpora fetched by scripts/fetch_corpora.py.\n"
            "version: 1\nfamily: benchmark\ntasks:\n"
            + "".join(f"- task_id: {t}\n  weight: 1.0\n" for t in suite_tasks)
        )
        print(f"wrote {suite}")


if __name__ == "__main__":
    main()
