"""Orchestrator delegation: events arrive tagged and in the right order."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai.models.test import TestModel

from aidbg.config.mcp import McpConfig
from aidbg.config.settings import load_settings
from aidbg.core import events as ev
from aidbg.core.agent_factory import build_orchestrator
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.streaming import pump_agent_run


async def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


async def test_delegation_event_order(tmp_path: Path):
    settings = load_settings()
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=settings)

    # Children use a plain TestModel; orchestrator is overridden to call the
    # coder delegate tool exactly once, then produce its final answer.
    agent = build_orchestrator(
        settings=settings,
        mcp_config=McpConfig(),
        workspace=tmp_path,
        model_override=TestModel(call_tools=[]),
    )
    with agent.override(model=TestModel(call_tools=["delegate_to_coder"])):
        result = await pump_agent_run(
            agent, "write fizzbuzz", deps=deps, bus=bus, agent_name="orchestrator"
        )

    events = await _drain(q)
    kinds = [type(e).__name__ for e in events]

    # Delegation brackets the coder's own run.
    i_start = kinds.index("DelegationStarted")
    i_fin = kinds.index("DelegationFinished")
    assert i_start < i_fin

    # The coder produced its own message events, tagged with its name, between
    # the delegation start and finish.
    coder_msgs = [
        e
        for e in events
        if isinstance(e, ev.MessageStarted) and e.agent == "coder"
    ]
    assert coder_msgs, "expected a coder MessageStarted event"

    deleg = next(e for e in events if isinstance(e, ev.DelegationStarted))
    assert deleg.parent == "orchestrator" and deleg.child == "coder"

    # Final run finished for the orchestrator.
    assert any(isinstance(e, ev.RunFinished) and e.agent == "orchestrator" for e in events)
    assert result.output is not None


async def test_delegation_to_code_reviewer(tmp_path: Path):
    """The dynamically-added code-reviewer is reachable as a delegate tool."""
    settings = load_settings()
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=settings)

    agent = build_orchestrator(
        settings=settings,
        mcp_config=McpConfig(),
        workspace=tmp_path,
        model_override=TestModel(call_tools=[]),
    )
    # The delegate tool name replaces '-' with '_': code-reviewer -> code_reviewer.
    with agent.override(model=TestModel(call_tools=["delegate_to_code_reviewer"])):
        result = await pump_agent_run(
            agent, "review this diff", deps=deps, bus=bus, agent_name="orchestrator"
        )

    events = await _drain(q)
    deleg = next(e for e in events if isinstance(e, ev.DelegationStarted))
    assert deleg.parent == "orchestrator" and deleg.child == "code-reviewer"
    assert any(
        isinstance(e, ev.MessageStarted) and e.agent == "code-reviewer" for e in events
    ), "expected a code-reviewer MessageStarted event"
    assert result.output is not None
