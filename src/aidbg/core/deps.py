"""Dependencies injected into every agent run (pydantic-ai ``deps_type``).

pydantic-ai passes this object to tools and delegate adapters via
``RunContext[AppDeps]``. It carries the shared event bus, the workspace root
(for filesystem-scoped tools), and the settings. No textual import.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aidbg.config.settings import Settings
from aidbg.core.events import EventBus


@dataclass
class AppDeps:
    """Runtime dependencies shared across all agents in a run."""

    bus: EventBus
    workspace: Path
    settings: Settings
