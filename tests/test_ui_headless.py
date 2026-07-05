"""Headless UI tests: input -> worker -> bus drain -> widgets update.

Exercises the full Textual wiring (App dispatch, ChatController workers, the
streaming message/thinking widgets, the black theme) against scripted models so
no backend is contacted. Settings are built explicitly so results don't depend
on a developer's local ``.env``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, FunctionModel
from pydantic_ai.models.test import TestModel

from aidbg.config.mcp import McpConfig
from aidbg.config.settings import Settings
from aidbg.core import events as ev
from aidbg.core.registry import AGENTS
from aidbg.session.session import ChatSession
from aidbg.ui.app import AidbgApp
from aidbg.ui.messages import UiEventArrived
from aidbg.ui.theme import AIDBG_BLACK
from aidbg.ui.widgets.chat_message import ChatMessage, DelegationCard, ThinkingMessage


def _settings() -> Settings:
    return Settings(_env_file=None)  # ignore local .env for determinism


async def _run_until_idle(app: AidbgApp, pilot) -> None:
    await pilot.pause()
    for _ in range(60):
        if not app._input.disabled:
            return
        await asyncio.sleep(0.05)
        await pilot.pause()


async def test_headless_turn_and_black_theme(tmp_path: Path):
    session = ChatSession(
        settings=_settings(),
        workspace=tmp_path,
        mcp_config=McpConfig(),
        model_override=TestModel(call_tools=[]),
    )
    app = AidbgApp(session, agent_names=AGENTS.names())

    async with app.run_test() as pilot:
        # The pure-black theme is registered and active.
        assert app.theme == AIDBG_BLACK.name
        assert app.current_theme.background == "#000000"

        app._input.value = "hello"
        await pilot.press("enter")
        await _run_until_idle(app, pilot)

        assert not app._input.disabled, "input should re-enable after the turn"
        assert len(app._chat._by_id) >= 1, "expected at least one assistant message"
        assert len(session.history) == 2, "expected request + response in history"


async def test_headless_thinking_block(tmp_path: Path):
    async def stream_fn(messages, info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Reasoning ")}
        yield {0: DeltaThinkingPart(content="here.")}
        yield "Final **answer**."

    session = ChatSession(
        settings=_settings(),
        workspace=tmp_path,
        mcp_config=McpConfig(),
        model_override=FunctionModel(stream_function=stream_fn),
    )
    app = AidbgApp(session, agent_names=AGENTS.names())

    async with app.run_test() as pilot:
        app._input.value = "hi"
        await pilot.press("enter")
        await _run_until_idle(app, pilot)

        widgets = list(app._chat._by_id.values())
        thinking = [w for w in widgets if isinstance(w, ThinkingMessage)]
        answers = [w for w in widgets if isinstance(w, ChatMessage)]

        assert len(thinking) == 1, "expected exactly one thinking block"
        assert thinking[0]._buffer == "Reasoning here."
        # Thinking auto-collapses once complete.
        assert thinking[0]._collapsible is not None
        assert thinking[0]._collapsible.collapsed is True

        assert answers, "expected an answer message"
        assert answers[0]._buffer == "Final **answer**."


async def test_headless_delegation_card_inline(tmp_path: Path):
    """A delegation renders as an inline card in the transcript that flips to done."""
    session = ChatSession(
        settings=_settings(),
        workspace=tmp_path,
        mcp_config=McpConfig(),
        model_override=TestModel(call_tools=[]),
    )
    app = AidbgApp(session, agent_names=AGENTS.names())

    async with app.run_test() as pilot:
        # Drive the app's dispatch directly with delegation events.
        app.post_message(
            UiEventArrived(
                ev.DelegationStarted(
                    parent="orchestrator", child="log-analyst", task="triage samples/fake_evidence"
                )
            )
        )
        await pilot.pause()

        cards = [w for w in app._chat.children if isinstance(w, DelegationCard)]
        assert len(cards) == 1, "expected an inline delegation card"
        card = cards[0]
        assert card.has_class("running"), "card should start in running state"
        assert card._child == "log-analyst"
        assert card._task_text == "triage samples/fake_evidence"

        # A tool call by the sub-agent bumps the live counter on its card.
        app.post_message(
            UiEventArrived(
                ev.ToolCallStarted(
                    agent="log-analyst", tool_name="list_evidence", tool_call_id="t1"
                )
            )
        )
        await pilot.pause()
        assert card._tool_calls == 1, "sub-agent tool call should bump the card counter"

        # A tool call by the orchestrator itself must NOT bump the child card.
        app.post_message(
            UiEventArrived(
                ev.ToolCallStarted(
                    agent="orchestrator", tool_name="delegate_to_log_analyst", tool_call_id="t2"
                )
            )
        )
        await pilot.pause()
        assert card._tool_calls == 1, "orchestrator's own tool call must not count on child"

        # Now finish the delegation, carrying a full report for the collapsible.
        app.post_message(
            UiEventArrived(
                ev.DelegationFinished(
                    parent="orchestrator",
                    child="log-analyst",
                    output_preview="## 结论 ...",
                    full_output="## 结论\n主控板反复重启，卡在 SGC。\n\n## 根因假设\n1. ...",
                )
            )
        )
        await pilot.pause()

        assert card.has_class("done"), "card should flip to done"
        assert not card.has_class("running")
        # The full report is mounted as a collapsible block on the card.
        from textual.widgets import Collapsible

        reports = [w for w in card.query(Collapsible)]
        assert reports, "expected a collapsible report block on the finished card"
