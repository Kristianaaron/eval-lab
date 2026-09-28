"""Resolve a task's on-disk inputs: instruction text, attachments, fixtures.

Task packages are directories (``tasks/<domain>/<slug>/``) holding ``task.yaml``
next to ``prompt.md``, optional ``data/`` attachments and an optional
``workspace/`` fixture. Every path in :class:`InputSpec` is relative to that
directory, so runners must never read ``instruction_file`` relative to the
process working directory (that is how a real model ends up being asked to
answer the literal string ``prompt.md``).
"""

from __future__ import annotations

from pathlib import Path

from eval_lab.schemas.models import TaskSpec

# Attachments larger than this are still sent in full; the marker just makes the
# framing explicit to the model so long documents are clearly delimited.
_ATTACHMENT_HEADER = "\n\n---\n## Attachment: {name}\n\n"
_ATTACHMENT_FOOTER = "\n\n--- end of {name} ---\n"


def task_dir(task: TaskSpec) -> Path | None:
    """Directory the task package was loaded from, if known."""
    return Path(task.source_dir) if task.source_dir else None


def resolve_input_path(task: TaskSpec, relative: str) -> Path:
    """Resolve a task-relative input path (falls back to cwd for ad-hoc specs)."""
    base = task_dir(task)
    candidate = (base / relative) if base is not None else Path(relative)
    if candidate.exists():
        return candidate
    # Ad-hoc TaskSpecs (tests, API) may pass an already-absolute or cwd path.
    return Path(relative)


def read_instruction(task: TaskSpec) -> str:
    """Return the instruction text; the raw field is the last-resort fallback."""
    path = resolve_input_path(task, task.input.instruction_file)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return task.input.instruction_file


def read_attachments(task: TaskSpec) -> list[tuple[str, str]]:
    """Return ``(name, text)`` for each attachment that exists on disk."""
    out: list[tuple[str, str]] = []
    for rel in task.input.attachments:
        path = resolve_input_path(task, rel)
        if path.is_file():
            out.append((rel, path.read_text(encoding="utf-8", errors="replace")))
    return out


def build_prompt(task: TaskSpec) -> str:
    """Instruction text followed by every attachment, clearly delimited.

    This is what a *direct* (no tools) run sends: long-context tasks depend on
    the attachment actually being in the context window.
    """
    prompt = read_instruction(task)
    for name, text in read_attachments(task):
        prompt += _ATTACHMENT_HEADER.format(name=name) + text + _ATTACHMENT_FOOTER.format(name=name)
    return prompt


def fixture_dir(task: TaskSpec) -> Path | None:
    """Absolute path of the workspace fixture to seed the sandbox with."""
    fixture = task.input.workspace_fixture
    if not fixture:
        return None
    path = resolve_input_path(task, fixture)
    return path if path.is_dir() else None


def prompt_char_count(task: TaskSpec) -> int:
    return len(build_prompt(task))
