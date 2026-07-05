"""The event pump: translate a pydantic-ai agent run into ``UiEvent``s.

This is the single bridge between pydantic-ai's streaming event shapes and the
UI-agnostic bus. Both the orchestrator and every sub-agent run through
:func:`pump_agent_run`, tagged with ``agent_name``, so sub-agent activity is
rendered nested by the UI automatically.

Event mapping (verified against pydantic-ai 2.5):
  ModelRequestNode.stream:
    PartStartEvent(TextPart)      -> MessageStarted + TokenDelta(initial text)
    PartDeltaEvent(TextPartDelta) -> TokenDelta
    PartDeltaEvent(ThinkingDelta) -> ThinkingDelta
    PartStartEvent(ToolCallPart)  -> (buffered; emitted at call time)
    PartEndEvent(TextPart)        -> MessageFinished
  CallToolsNode.stream:
    FunctionToolCallEvent         -> ToolCallStarted
    FunctionToolResultEvent       -> ToolCallFinished
  end of run                      -> RunFinished(usage)
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)

from aidbg.core.events import (
    EventBus,
    MessageFinished,
    MessageStarted,
    RunError,
    RunFinished,
    ThinkingDelta,
    TokenDelta,
    ToolCallFinished,
    ToolCallStarted,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.usage import RunUsage

    from aidbg.core.deps import AppDeps

# Process-wide monotonic id source for message widgets. Deterministic ordering;
# uniqueness across a session is all the UI needs.
_id_counter = itertools.count(1)


def _next_message_id(agent_name: str) -> str:
    return f"{agent_name}-{next(_id_counter)}"


def _preview(value: Any, limit: int = 200) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


async def pump_agent_run(
    agent: Agent[Any, Any],
    prompt: str,
    *,
    deps: AppDeps,
    bus: EventBus,
    agent_name: str,
    usage: RunUsage | None = None,
    message_history: list[ModelMessage] | None = None,
) -> Any:
    """Run ``agent`` on ``prompt``, publishing ``UiEvent``s to ``bus``.

    Returns the pydantic-ai ``AgentRunResult``. ``usage`` is forwarded so a
    sub-agent's tokens aggregate into the parent run's usage (pydantic-ai
    requirement for multi-agent accounting).

    On error (backend unreachable, cancellation, tool failure) a
    :class:`RunError` is published and the exception re-raised so the caller can
    react (e.g. re-enable input).
    """
    state = _StreamState()

    try:
        async with agent.iter(
            prompt,
            deps=deps,
            usage=usage,
            message_history=message_history,
        ) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as request_stream:
                        async for model_event in request_stream:
                            await _handle_model_event(model_event, bus, agent_name, state)
                elif Agent.is_call_tools_node(node):
                    async with node.stream(run.ctx) as tools_stream:
                        async for tool_event in tools_stream:
                            await _handle_tool_event(tool_event, bus, agent_name)

        usage_summary = _format_usage(run.usage)
        await bus.publish(RunFinished(agent=agent_name, usage_summary=usage_summary))
        return run.result

    except Exception as exc:
        # asyncio.CancelledError is a BaseException (not Exception) since 3.8, so
        # user cancellation propagates cleanly without being reported as an error.
        await bus.publish(RunError(agent=agent_name, message=f"{type(exc).__name__}: {exc}"))
        raise


class _StreamState:
    """Per-run cursor: the currently-open answer and thinking message ids.

    Thinking and answer are surfaced as separate messages so the UI can render
    reasoning in its own (dimmed, collapsible) block above the final answer.
    """

    __slots__ = ("answer_id", "thinking_id")

    def __init__(self) -> None:
        self.answer_id: str | None = None
        self.thinking_id: str | None = None


async def _handle_model_event(
    event: Any,
    bus: EventBus,
    agent_name: str,
    state: _StreamState,
) -> None:
    """Handle one event from a model-request node, updating ``state``."""
    if isinstance(event, PartStartEvent):
        part = event.part
        if isinstance(part, TextPart):
            state.answer_id = _next_message_id(agent_name)
            await bus.publish(
                MessageStarted(agent=agent_name, message_id=state.answer_id, kind="answer")
            )
            if part.content:
                await bus.publish(
                    TokenDelta(agent=agent_name, message_id=state.answer_id, text=part.content)
                )
        elif isinstance(part, ThinkingPart):
            if state.thinking_id is None:
                state.thinking_id = _next_message_id(agent_name)
                await bus.publish(
                    MessageStarted(
                        agent=agent_name, message_id=state.thinking_id, kind="thinking"
                    )
                )
            if part.content:
                await bus.publish(
                    ThinkingDelta(
                        agent=agent_name, message_id=state.thinking_id, text=part.content
                    )
                )
        # ToolCallPart start is handled at call time via FunctionToolCallEvent.

    elif isinstance(event, PartDeltaEvent):
        delta = event.delta
        if isinstance(delta, TextPartDelta) and state.answer_id is not None:
            if delta.content_delta:
                await bus.publish(
                    TokenDelta(
                        agent=agent_name, message_id=state.answer_id, text=delta.content_delta
                    )
                )
        elif isinstance(delta, ThinkingPartDelta) and state.thinking_id is not None:
            if delta.content_delta:
                await bus.publish(
                    ThinkingDelta(
                        agent=agent_name,
                        message_id=state.thinking_id,
                        text=delta.content_delta,
                    )
                )

    elif isinstance(event, PartEndEvent):
        part = event.part
        if isinstance(part, TextPart) and state.answer_id is not None:
            await bus.publish(MessageFinished(agent=agent_name, message_id=state.answer_id))
            state.answer_id = None
        elif isinstance(part, ThinkingPart) and state.thinking_id is not None:
            await bus.publish(MessageFinished(agent=agent_name, message_id=state.thinking_id))
            state.thinking_id = None


async def _handle_tool_event(event: Any, bus: EventBus, agent_name: str) -> None:
    """Handle one event from a call-tools node."""
    if isinstance(event, FunctionToolCallEvent):
        call_part: ToolCallPart = event.part
        await bus.publish(
            ToolCallStarted(
                agent=agent_name,
                tool_name=call_part.tool_name,
                tool_call_id=call_part.tool_call_id,
                args_preview=_preview(call_part.args),
            )
        )
    elif isinstance(event, FunctionToolResultEvent):
        # event.part is a ToolReturnPart (tool_name, content, tool_call_id).
        result_part = event.part
        await bus.publish(
            ToolCallFinished(
                agent=agent_name,
                tool_name=getattr(result_part, "tool_name", ""),
                tool_call_id=getattr(result_part, "tool_call_id", ""),
                result_preview=_preview(getattr(result_part, "content", result_part)),
            )
        )


def _format_usage(usage: RunUsage | None) -> str:
    if usage is None:
        return ""
    parts = []
    for label, attr in (("in", "input_tokens"), ("out", "output_tokens"), ("req", "requests")):
        val = getattr(usage, attr, None)
        if val:
            parts.append(f"{label}={val}")
    return " ".join(parts)
