"""Pick the executor a task needs from ``execution.runner`` (spec 10)."""

from __future__ import annotations

from eval_lab.runners.batch import Executor
from eval_lab.schemas.models import TaskSpec


def runner_for(task: TaskSpec) -> Executor:
    """Return the executor matching ``task.execution.runner``."""
    kind = task.execution.runner
    if kind == "direct":
        from eval_lab.runners.direct import DirectRunner

        return DirectRunner()
    if kind == "agent":
        from eval_lab.runners.agent_executor import AgentRunner

        return AgentRunner()
    if kind == "perplexity":
        from eval_lab.runners.perplexity import PerplexityRunner

        return PerplexityRunner()
    raise ValueError(f"unsupported runner: {kind}")


class DispatchingRunner:
    """An Executor that routes every task to the runner its spec asks for."""

    def execute_task(self, task: TaskSpec, context):  # type: ignore[no-untyped-def]
        return runner_for(task).execute_task(task, context)
