"""UI-agnostic event types and a fan-out event bus.

The bus shields the UI from pydantic-ai's event shapes: ``core/streaming.py``
translates raw pydantic-ai events into this flat dataclass union and publishes
them. The UI subscribes to a queue and renders by event type. Nothing here
imports textual or pydantic-ai.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


# --- Event union -----------------------------------------------------------
# One dataclass per distinguishable UI concern. `agent` tags which agent the
# event belongs to so the UI can render nested sub-agent activity. `message_id`
# ties deltas to the message widget they belong to.


@dataclass(slots=True)
class MessageStarted:
    """A new assistant message began.

    ``kind`` distinguishes the model's reasoning stream (``"thinking"``) from its
    final answer (``"answer"``), so the UI can render them differently.
    """

    agent: str
    message_id: str
    kind: str = "answer"  # "answer" | "thinking"


@dataclass(slots=True)
class TokenDelta:
    """A chunk of assistant text."""

    agent: str
    message_id: str
    text: str


@dataclass(slots=True)
class ThinkingDelta:
    """A chunk of assistant reasoning/thinking text."""

    agent: str
    message_id: str
    text: str


@dataclass(slots=True)
class MessageFinished:
    """An assistant text message completed."""

    agent: str
    message_id: str


@dataclass(slots=True)
class ToolCallStarted:
    """A native/MCP tool call began."""

    agent: str
    tool_name: str
    tool_call_id: str
    args_preview: str = ""


@dataclass(slots=True)
class ToolCallFinished:
    """A tool call returned."""

    agent: str
    tool_name: str
    tool_call_id: str
    result_preview: str = ""


@dataclass(slots=True)
class DelegationStarted:
    """The orchestrator delegated a task to a sub-agent."""

    parent: str
    child: str
    task: str


@dataclass(slots=True)
class DelegationFinished:
    """A sub-agent delegation returned."""

    parent: str
    child: str
    output_preview: str
    full_output: str = ""  # complete sub-agent output (for the collapsible report)


@dataclass(slots=True)
class RunFinished:
    """The top-level agent run finished."""

    agent: str
    usage_summary: str = ""


@dataclass(slots=True)
class RunError:
    """The run raised before completing (e.g. backend unreachable, cancelled)."""

    agent: str
    message: str


UiEvent = (
    MessageStarted
    | TokenDelta
    | ThinkingDelta
    | MessageFinished
    | ToolCallStarted
    | ToolCallFinished
    | DelegationStarted
    | DelegationFinished
    | RunFinished
    | RunError
)


# --- Fan-out bus -----------------------------------------------------------


@dataclass
class EventBus:
    """Fan-out asyncio queue bus.

    Producers call :meth:`publish`; each subscriber gets its own queue and sees
    every event published after it subscribed. Used to decouple the core run
    loop from however many UI drains are listening.
    """

    _subscribers: list[asyncio.Queue[UiEvent]] = field(default_factory=list)

    def subscribe(self) -> asyncio.Queue[UiEvent]:
        q: asyncio.Queue[UiEvent] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[UiEvent]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, event: UiEvent) -> None:
        for q in list(self._subscribers):
            await q.put(event)
