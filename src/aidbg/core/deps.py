"""Dependencies injected into every agent run (pydantic-ai ``deps_type``).

pydantic-ai passes this object to tools and delegate adapters via
``RunContext[AppDeps]``. It carries the shared event bus, the workspace root
(for filesystem-scoped tools), the settings, and the run-scoped findings board
that sub-agents use to pass clues to each other. No textual import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aidbg.config.settings import Settings
from aidbg.core.events import EventBus
from aidbg.core.findings import FindingsBoard


@dataclass
class AppDeps:
    """Runtime dependencies shared across all agents in a run."""

    bus: EventBus
    workspace: Path
    settings: Settings
    # Shared clue blackboard — data flow between sub-agents (control flow stays
    # with the orchestrator). Default factory so existing construction sites need
    # no change; every agent in one run sees the same board.
    findings: FindingsBoard = field(default_factory=FindingsBoard)
