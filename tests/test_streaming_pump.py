"""Streaming pump: scripted text + tool call produce the right UiEvent sequence."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, FunctionModel

from aidbg.core import events as ev
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.streaming import pump_agent_run


async def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


async def test_text_only_stream(tmp_path: Path):
    async def stream_fn(messages, info: AgentInfo):
        for chunk in ["Hel", "lo ", "wor", "ld"]:
            yield chunk

    agent = Agent(FunctionModel(stream_function=stream_fn), deps_type=AppDeps)
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=_dummy_settings())

    await pump_agent_run(agent, "hi", deps=deps, bus=bus, agent_name="t")
    events = await _drain(q)
    kinds = [type(e).__name__ for e in events]

    assert kinds == [
        "MessageStarted",
        "TokenDelta",
        "TokenDelta",
        "TokenDelta",
        "TokenDelta",
        "MessageFinished",
        "RunFinished",
    ]
    text = "".join(e.text for e in events if isinstance(e, ev.TokenDelta))
    assert text == "Hello world"


async def test_tool_call_then_text(tmp_path: Path):
    # TestModel supports streaming and calls the available tool once, then
    # produces its structured text output — exercising both tool + text events.
    from pydantic_ai.models.test import TestModel

    agent = Agent(TestModel(call_tools=["ping"]), deps_type=AppDeps)

    @agent.tool_plain
    def ping() -> str:
        return "pong"

    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=_dummy_settings())

    await pump_agent_run(agent, "hi", deps=deps, bus=bus, agent_name="t")
    events = await _drain(q)
    kinds = [type(e).__name__ for e in events]

    # Tool call brackets: started before finished, both present.
    assert "ToolCallStarted" in kinds and "ToolCallFinished" in kinds
    assert kinds.index("ToolCallStarted") < kinds.index("ToolCallFinished")

    started = next(e for e in events if isinstance(e, ev.ToolCallStarted))
    finished = next(e for e in events if isinstance(e, ev.ToolCallFinished))
    assert started.tool_name == "ping"
    assert finished.tool_name == "ping"
    assert "pong" in finished.result_preview

    # A final text message + run finished.
    assert kinds[-1] == "RunFinished"
    assert any(isinstance(e, ev.MessageFinished) for e in events)


async def test_run_error_published(tmp_path: Path):
    def boom(messages, info: AgentInfo):
        raise RuntimeError("backend exploded")

    agent = Agent(FunctionModel(boom), deps_type=AppDeps)
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=_dummy_settings())

    raised = False
    try:
        await pump_agent_run(agent, "hi", deps=deps, bus=bus, agent_name="t")
    except Exception:
        raised = True

    assert raised
    events = await _drain(q)
    assert any(isinstance(e, ev.RunError) for e in events)


async def test_thinking_then_answer_are_separate_messages(tmp_path: Path):
    """Reasoning surfaces as its own (thinking) message, then the answer."""

    async def stream_fn(messages, info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Let me ")}
        yield {0: DeltaThinkingPart(content="think.")}
        yield "The answer."

    agent = Agent(FunctionModel(stream_function=stream_fn), deps_type=AppDeps)
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=_dummy_settings())

    await pump_agent_run(agent, "hi", deps=deps, bus=bus, agent_name="t")
    events = await _drain(q)

    # Two MessageStarted: one thinking, one answer, thinking first.
    starts = [e for e in events if isinstance(e, ev.MessageStarted)]
    assert [s.kind for s in starts] == ["thinking", "answer"]
    thinking_id, answer_id = starts[0].message_id, starts[1].message_id
    assert thinking_id != answer_id

    # Thinking deltas carry the thinking id; token deltas carry the answer id.
    thinking_text = "".join(
        e.text for e in events if isinstance(e, ev.ThinkingDelta) and e.message_id == thinking_id
    )
    answer_text = "".join(
        e.text for e in events if isinstance(e, ev.TokenDelta) and e.message_id == answer_id
    )
    assert thinking_text == "Let me think."
    assert answer_text == "The answer."

    # Thinking message is finished before the answer message starts.
    kinds = [type(e).__name__ for e in events]
    finished_ids = [e.message_id for e in events if isinstance(e, ev.MessageFinished)]
    assert thinking_id in finished_ids and answer_id in finished_ids
    assert kinds.index("MessageFinished") < kinds.index("TokenDelta")


def _dummy_settings():
    from aidbg.config.settings import Settings

    return Settings(_env_file=None)
