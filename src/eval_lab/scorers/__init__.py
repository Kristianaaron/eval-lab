"""Scorer registry package.

Importing this package registers every scorer implementation via side-effect
``register_scorer`` calls at module import (spec 13.2/13.3).
"""

from __future__ import annotations

# Side-effect registration of deterministic and advanced scorers.
import eval_lab.scorers.aggregate  # noqa: F401
import eval_lab.scorers.artifact  # noqa: F401
import eval_lab.scorers.deterministic  # noqa: F401
import eval_lab.scorers.trajectory  # noqa: F401
import eval_lab.scorers.unit_test  # noqa: F401
import eval_lab.scorers.visual  # noqa: F401
from eval_lab.scorers.base import (
    Scorer,
    available_scorers,
    get_scorer,
    register_scorer,
)

__all__ = ["Scorer", "available_scorers", "get_scorer", "register_scorer"]
