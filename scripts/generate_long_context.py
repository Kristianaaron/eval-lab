#!/usr/bin/env python3
"""Generate the long-context benchmark task packages (deterministic, stdlib only).

Produces, under ``tasks/longcontext_deep/``:

- ``handbook_8k`` / ``handbook_32k`` / ``handbook_64k``: a synthetic corporate
  policy compendium (numbered policies with owners, budget codes, effective
  dates, supersession chains, escalation contacts, and a staff directory) at
  three context sizes, each with four multi-hop questions whose answers are
  computed from the generated data (oracle: ``json_exact``).
- ``logs_32k``: a structured service log (~1 050 lines) with three aggregation
  questions over a time window.

Every question requires combining facts that are far apart in the document, so
a model cannot answer from the prompt's neighbourhood alone. Re-running the
script with the same seed reproduces byte-identical packages.

Usage:  python scripts/generate_long_context.py [--seed 20260928] [--out tasks/longcontext_deep]
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEPARTMENTS = [
    "Facilities",
    "Legal",
    "Finance",
    "Engineering",
    "People Operations",
    "Security",
    "Procurement",
    "Customer Support",
    "Data Governance",
    "Communications",
]
CADENCES = ["annual", "semi-annual", "quarterly", "biennial"]
TOPICS = [
    "remote work equipment",
    "visitor access",
    "expense reimbursement",
    "data retention",
    "incident escalation",
    "vendor onboarding",
    "travel booking",
    "password rotation",
    "meeting room booking",
    "open-source contributions",
    "device encryption",
    "parental leave",
    "records disposal",
    "press enquiries",
    "on-call compensation",
    "conference sponsorship",
    "software licensing",
    "physical key management",
    "customer data export",
    "internal mobility",
    "hazardous materials",
    "fleet vehicles",
    "training reimbursement",
    "acceptable use",
    "third-party audits",
    "gift acceptance",
    "backup verification",
    "badge replacement",
    "workstation ergonomics",
    "signage",
]
FIRST = [
    "Amara",
    "Bertil",
    "Chen",
    "Dalia",
    "Emeka",
    "Farid",
    "Greta",
    "Hiro",
    "Ines",
    "Jonas",
    "Keziah",
    "Lucas",
    "Maren",
    "Nikhil",
    "Olwen",
    "Priya",
    "Quentin",
    "Rosa",
    "Soren",
    "Tomasz",
    "Ulla",
    "Viktor",
    "Wanda",
    "Ximena",
    "Yusuf",
    "Zofia",
]
LAST = [
    "Okafor",
    "Lindqvist",
    "Ferrand",
    "Nakamura",
    "Adeyemi",
    "Castellanos",
    "Petrov",
    "Haddad",
    "Moreau",
    "Sørensen",
    "Banerjee",
    "Kowalski",
    "Oyelaran",
    "Fitzgerald",
    "Varga",
    "Tanaka",
    "Mbeki",
    "Almeida",
    "Novak",
    "Rahman",
]
BUILDINGS = ["Aster", "Birch", "Cedar", "Dunlin", "Elder", "Fennel"]

SENTENCES = [
    "This policy applies to all employees, contractors and visitors of Meridian Systems unless a written exemption has been granted by the owning department.",
    "Requests for exceptions must be submitted through the internal service desk and will be reviewed within ten working days.",
    "Managers are responsible for ensuring that the people reporting to them are aware of the obligations described here.",
    "Records created under this policy are retained according to the schedule maintained by Data Governance.",
    "Non-compliance may result in the withdrawal of access rights and, where appropriate, disciplinary action.",
    "Questions about interpretation should be directed to the escalation contact named below before any action is taken.",
    "Where this policy conflicts with a local legal requirement, the local requirement prevails and the conflict must be reported.",
    "Costs incurred under this policy are charged to the budget code listed in the summary table unless a project code has been agreed in advance.",
    "The owning department reviews this document at the stated cadence and publishes a change note with every revision.",
    "Training material supporting this policy is available on the learning portal and must be completed within thirty days of joining.",
    "Automated reminders are issued fourteen days before any deadline defined in this policy.",
    "Approvals may be delegated in writing for a period not exceeding ninety days.",
    "The procedure section below describes the steps in the order they must be performed.",
    "Audit evidence is sampled twice a year and findings are reported to the relevant department head.",
    "Temporary measures introduced during an incident expire automatically after seventy-two hours unless renewed.",
]
STEPS = [
    "Submit the request form with the required attachments.",
    "Obtain approval from the line manager and, where the amount exceeds the threshold, the department head.",
    "Record the approval reference in the tracking system.",
    "Notify the affected parties at least two working days in advance.",
    "Complete the checklist and file it with the records team.",
    "Verify completion and close the ticket with a short summary.",
    "Schedule the follow-up review at the interval defined by the cadence.",
]


def _date(rng: random.Random, start_year: int = 2019) -> datetime:
    base = datetime(start_year, 1, 1, tzinfo=UTC)
    return base + timedelta(days=rng.randrange(0, 365 * 6))


def gen_handbook(
    rng: random.Random, n_policies: int
) -> tuple[str, dict[str, object], dict[str, str]]:
    """Return (text, answers, questions)."""
    staff = []
    used = set()
    while len(staff) < max(24, n_policies // 3):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name in used:
            continue
        used.add(name)
        staff.append(
            {
                "name": name,
                "dept": rng.choice(DEPARTMENTS),
                "ext": rng.randrange(2000, 9999),
                "office": f"{rng.choice(BUILDINGS)} {rng.randrange(1, 5)}.{rng.randrange(1, 40):02d}",
            }
        )
    policies = []
    ids = rng.sample(range(100, 999), n_policies)
    for i, pid in enumerate(ids):
        p = {
            "id": f"POL-{pid}",
            "topic": rng.choice(TOPICS),
            "owner": rng.choice(DEPARTMENTS),
            "budget": f"BC-{rng.choice('ABCDEFGH')}{rng.randrange(100, 999)}",
            "effective": _date(rng),
            "cadence": rng.choice(CADENCES),
            "contact": rng.choice(staff)["name"],
            "supersedes": None,
            "threshold": rng.choice([250, 500, 1000, 2500, 5000, 10000]),
        }
        if i > 3 and rng.random() < 0.55:
            p["supersedes"] = policies[rng.randrange(0, i)]["id"]
        policies.append(p)
    rng.shuffle(policies)

    lines: list[str] = []
    lines.append("MERIDIAN SYSTEMS — CORPORATE POLICY COMPENDIUM")
    lines.append(
        f"Consolidated edition containing {len(policies)} policies. Sections are numbered in publication order; "
        "the summary table at the head of each section is authoritative."
    )
    lines.append("")
    for n, p in enumerate(policies, start=1):
        lines.append(f"SECTION {n}: {p['id']} — {p['topic'].title()}")
        lines.append("Summary table")
        lines.append(f"  Policy id:          {p['id']}")
        lines.append(f"  Owning department:  {p['owner']}")
        lines.append(f"  Effective date:     {p['effective']:%d %B %Y}")
        lines.append(f"  Review cadence:     {p['cadence']}")
        lines.append(f"  Budget code:        {p['budget']}")
        lines.append(f"  Approval threshold: {p['threshold']} EUR")
        lines.append(f"  Escalation contact: {p['contact']}")
        lines.append(f"  Supersedes:         {p['supersedes'] or 'none'}")
        lines.append("")
        lines.append("Purpose and scope")
        para = rng.sample(SENTENCES, rng.randrange(4, 8))
        lines.append(" ".join(para))
        lines.append("")
        lines.append("Procedure")
        for k, step in enumerate(rng.sample(STEPS, rng.randrange(4, 7)), start=1):
            lines.append(f"  {k}. {step}")
        lines.append("")
        lines.append("Notes")
        lines.append(" ".join(rng.sample(SENTENCES, rng.randrange(2, 5))))
        lines.append("")
    lines.append("APPENDIX A: STAFF DIRECTORY (escalation contacts)")
    for s in sorted(staff, key=lambda x: x["name"]):
        lines.append(f"  {s['name']:<24} {s['dept']:<20} ext. {s['ext']}   office {s['office']}")
    lines.append("")
    text = "\n".join(lines)

    by_id = {p["id"]: p for p in policies}
    staff_by = {s["name"]: s for s in staff}
    # Q1: owner of the policy that supersedes X (reverse lookup).
    superseded = [p for p in policies if p["supersedes"]]
    q1p = rng.choice(superseded)
    # Q2: budget code of the policy owned by D with the latest effective date.
    dept = rng.choice(DEPARTMENTS)
    owned = [p for p in policies if p["owner"] == dept]
    while len(owned) < 2:
        dept = rng.choice(DEPARTMENTS)
        owned = [p for p in policies if p["owner"] == dept]
    latest = max(owned, key=lambda p: p["effective"])
    # Q3: office extension of the escalation contact of policy Y.
    q3p = rng.choice(policies)
    # Q4: count of policies with cadence C owned by department D2.
    cad = rng.choice(CADENCES)
    d2 = rng.choice(DEPARTMENTS)
    count = sum(1 for p in policies if p["cadence"] == cad and p["owner"] == d2)
    questions = {
        "q1": f"Which department owns the policy that supersedes {q1p['supersedes']}?",
        "q2": f"Among the policies owned by {dept}, which budget code belongs to the one with the most recent effective date?",
        "q3": f"What is the telephone extension (digits only) of the escalation contact for {q3p['id']}?",
        "q4": f"How many policies are owned by {d2} and have a {cad} review cadence? Answer with an integer.",
    }
    answers: dict[str, object] = {
        "q1": q1p["owner"],
        "q2": latest["budget"],
        "q3": staff_by[q3p["contact"]]["ext"],
        "q4": count,
    }
    assert by_id[q1p["supersedes"]]
    return text, answers, questions


SERVICES = [
    "billing-api",
    "auth-gateway",
    "search-indexer",
    "notification-worker",
    "ledger-sync",
    "media-transcoder",
    "checkout-web",
    "inventory-api",
]
LEVELS = ["INFO"] * 12 + ["WARN"] * 3 + ["ERROR"] * 2 + ["DEBUG"] * 4
MSGS = {
    "INFO": [
        "request completed",
        "cache refreshed",
        "job scheduled",
        "connection pool resized",
        "health check ok",
        "config reloaded",
        "batch flushed",
    ],
    "WARN": [
        "retrying upstream call",
        "slow query detected",
        "queue depth above threshold",
        "certificate expires soon",
        "rate limit approaching",
    ],
    "ERROR": [
        "upstream timeout",
        "deserialization failed",
        "database connection refused",
        "unhandled exception in handler",
        "disk quota exceeded",
    ],
    "DEBUG": [
        "entering handler",
        "leaving handler",
        "cache probe",
        "span started",
        "span finished",
    ],
}


def gen_logs(rng: random.Random, n_lines: int) -> tuple[str, dict[str, object], dict[str, str]]:
    start = datetime(2026, 3, 14, 0, 0, 0, tzinfo=UTC)
    t = start
    rows = []
    for i in range(n_lines):
        t += timedelta(seconds=rng.randrange(1, 40))
        level = rng.choice(LEVELS)
        svc = rng.choice(SERVICES)
        row = {
            "ts": t,
            "level": level,
            "service": svc,
            "node": f"n{rng.randrange(1, 13):02d}",
            "code": f"E{rng.randrange(4000, 4099)}" if level == "ERROR" else "-",
            "latency": rng.randrange(3, 2500) if level != "DEBUG" else 0,
            "req": f"r{rng.randrange(10**6, 10**7 - 1):07d}",
            "msg": rng.choice(MSGS[level]),
        }
        rows.append(row)
    lines = [
        f"{r['ts']:%Y-%m-%dT%H:%M:%SZ} level={r['level']} service={r['service']} node={r['node']} "
        f'code={r["code"]} latency_ms={r["latency"]} req={r["req"]} msg="{r["msg"]}"'
        for r in rows
    ]
    text = "\n".join(lines) + "\n"
    # Window: pick two timestamps ~ a third of the way in and two thirds.
    w0 = rows[len(rows) // 3]["ts"].replace(second=0)
    w1 = rows[2 * len(rows) // 3]["ts"].replace(second=0)
    in_window = [r for r in rows if w0 <= r["ts"] < w1]
    errs: dict[str, int] = {}
    for r in in_window:
        if r["level"] == "ERROR":
            errs[r["service"]] = errs.get(r["service"], 0) + 1
    top_svc = max(errs, key=lambda s: (errs[s], s))
    # Q3: highest latency_ms among WARN lines from a given node over the whole log.
    node = rng.choice(sorted({r["node"] for r in rows}))
    warn_lat = [r["latency"] for r in rows if r["level"] == "WARN" and r["node"] == node]
    questions = {
        "q1": f"Between {w0:%Y-%m-%dT%H:%M:%SZ} (inclusive) and {w1:%Y-%m-%dT%H:%M:%SZ} (exclusive), which service has the most lines with level=ERROR? (If tied, the alphabetically last service name.)",
        "q2": "How many level=ERROR lines does that service have in the same window? Answer with an integer.",
        "q3": f"Over the entire log, what is the highest latency_ms value on a level=WARN line from node={node}? Answer with an integer.",
    }
    answers: dict[str, object] = {"q1": top_svc, "q2": errs[top_svc], "q3": max(warn_lat)}
    return text, answers, questions


PROMPT_HANDBOOK = """You are given the complete text of a corporate policy compendium as an attachment. Answer the four questions below using only the attached document. Each answer requires combining information from different sections (summary tables, supersession references and the staff directory in Appendix A).

{questions}

Reply with a single JSON object and nothing else, e.g. {{"q1": "...", "q2": "...", "q3": 1234, "q4": 5}}. Use the exact spelling that appears in the document for names and codes.
"""

PROMPT_LOGS = """You are given a structured service log as an attachment (one event per line: timestamp, level, service, node, code, latency_ms, request id, message). Answer the questions below using only the attached log.

{questions}

Reply with a single JSON object and nothing else, e.g. {{"q1": "service-name", "q2": 12, "q3": 345}}.
"""


def write_task(
    out: Path,
    slug: str,
    name: str,
    description: str,
    text: str,
    questions: dict[str, str],
    answers: dict[str, object],
    prompt_template: str,
    attachment_name: str,
    difficulty: str,
) -> None:
    pkg = out / slug
    (pkg / "data").mkdir(parents=True, exist_ok=True)
    (pkg / "data" / attachment_name).write_text(text, encoding="utf-8")
    qtext = "\n".join(f"{k}: {v}" for k, v in questions.items())
    (pkg / "prompt.md").write_text(prompt_template.format(questions=qtext), encoding="utf-8")
    approx_tokens = len(text) // 4
    task = {
        "schema_version": "1.0",
        "id": f"longcontext.{slug}.001",
        "name": name,
        "description": f"{description} (~{approx_tokens // 1000}k tokens of context).",
        "version": 1,
        "level": "model",
        "status": "active",
        "data_partition": "held_out_evaluation",
        "labels": {
            "domains": ["long_context", "retrieval"],
            "capabilities": ["long_context_retrieval", "state_tracking", "instruction_following"],
            "modalities": ["text", "structured"],
            "difficulty": difficulty,
            "trajectory_stages": ["inspect", "execute"],
            "failure_modes_targeted": ["context_forgetting", "plausible_but_unverified"],
            "intervention": ["quantization", "expert_pruning"],
            "atlas_labels": [],
        },
        "input": {
            "instruction_file": "prompt.md",
            "attachments": [f"data/{attachment_name}"],
            "workspace_fixture": None,
            "initial_state_hash": None,
        },
        "execution": {
            "runner": "direct",
            "sandbox": None,
            "network": "disabled",
            "timeout_seconds": 900,
            "seeds": [0],
        },
        "oracle": [
            {"type": "json_exact", "weight": 1.0, "required": True, "config": {"expected": answers}}
        ],
        "repetitions": {"default": 1, "seeds": []},
    }
    import yaml  # PyYAML is an eval-lab dependency

    (pkg / "task.yaml").write_text(
        yaml.safe_dump(task, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (pkg / "GENERATED.md").write_text(
        "Generated by scripts/generate_long_context.py — do not edit by hand; re-run the script.\n"
        f"approx tokens: {approx_tokens}\n"
        + json.dumps({"questions": questions, "answers": answers}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"{slug:<14} chars={len(text):>8}  ~tokens={approx_tokens:>6}  answers={answers}")


def build_repo_listing(task_dir: Path) -> None:
    """Concatenate ``src/`` of the repo bug-hunt task into its single attachment."""
    src = task_dir / "src"
    files = sorted(p for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    parts = [
        "REPOSITORY LISTING: flowkit (complete; every file is shown once)",
        f"{len(files)} files. Paths are relative to the repository root.",
        "",
    ]
    for f in files:
        rel = f.relative_to(src).as_posix()
        parts.append(f"===== FILE: {rel} =====")
        parts.append(f.read_text(encoding="utf-8").rstrip("\n"))
        parts.append("")
    text = "\n".join(parts) + "\n"
    (task_dir / "data").mkdir(exist_ok=True)
    (task_dir / "data" / "repository.txt").write_text(text, encoding="utf-8")
    print(f"{'repo_bug_hunt':<14} chars={len(text):>8}  ~tokens={len(text) // 4:>6}  files={len(files)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--out", default="tasks/longcontext_deep")
    args = ap.parse_args()
    out = Path(args.out)
    tiers = [
        ("handbook_8k", 18, "hard"),
        ("handbook_32k", 70, "expert"),
        ("handbook_64k", 145, "expert"),
    ]
    for slug, n, diff in tiers:
        rng = random.Random(f"{args.seed}:{slug}")
        text, answers, questions = gen_handbook(rng, n)
        write_task(
            out,
            slug,
            f"Policy compendium multi-hop ({slug.split('_')[1]})",
            "Four multi-hop questions over a numbered policy compendium with supersession chains and a staff directory",
            text,
            questions,
            answers,
            PROMPT_HANDBOOK,
            "handbook.txt",
            diff,
        )
    build_repo_listing(out / "repo_bug_hunt")
    rng = random.Random(f"{args.seed}:logs")
    text, answers, questions = gen_logs(rng, 1050)
    write_task(
        out,
        "logs_32k",
        "Service log aggregation (32k)",
        "Windowed error aggregation and per-node maxima over a 1 050-line structured service log",
        text,
        questions,
        answers,
        PROMPT_LOGS,
        "service.log",
        "expert",
    )


if __name__ == "__main__":
    main()
