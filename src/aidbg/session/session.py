"""ChatSession — owns message history, the event bus, and the run loop.

UI-agnostic: it builds the orchestrator via the core factory and drives turns
through the pump. The UI subscribes to ``session.bus`` and calls
``session.run(prompt)``. No textual import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from aidbg.config.mcp import McpConfig, load_mcp_config
from aidbg.config.settings import Settings
from aidbg.core.agent_factory import build_orchestrator
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.streaming import pump_agent_run
from aidbg.session.history import load_history, save_history


class ChatSession:
    """A single conversation: orchestrator agent + accumulating history."""

    def __init__(
        self,
        *,
        settings: Settings,
        workspace: Path | None = None,
        mcp_config: McpConfig | None = None,
        model_override: Any = None,
    ) -> None:
        self.settings = settings
        self.workspace = (workspace or Path.cwd()).resolve()
        self.bus = EventBus()
        self.history: list[ModelMessage] = []

        mcp = mcp_config if mcp_config is not None else load_mcp_config(settings.mcp_config)
        self.agent: Agent[AppDeps, str] = build_orchestrator(
            settings=settings,
            mcp_config=mcp,
            workspace=self.workspace,
            model_override=model_override,
        )
        self.deps = AppDeps(bus=self.bus, workspace=self.workspace, settings=settings)

    async def run(self, prompt: str) -> Any:
        """Run one user turn. Streams events to the bus; appends to history.

        MCP toolsets need an active connection, so the run is wrapped in the
        agent's async context (``agent`` acts as an async context manager that
        opens/closes toolset connections).
        """
        async with self.agent:
            result = await pump_agent_run(
                self.agent,
                prompt,
                deps=self.deps,
                bus=self.bus,
                agent_name=self.agent.name or "orchestrator",
                message_history=self.history or None,
            )
        # Persist the full turn (request + responses) for the next turn's context.
        self.history = list(result.all_messages())
        return result

    # --- persistence -------------------------------------------------------

    def save(self, path: str | Path | None = None) -> Path:
        return save_history(path or self.settings.history_path, self.history)

    def load(self, path: str | Path | None = None) -> None:
        self.history = load_history(path or self.settings.history_path)
