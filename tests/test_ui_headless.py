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

        # Now finish the delegation. The sub-agent's report is shown in the
        # sub-agent window, NOT echoed into the main transcript.
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
        # No report collapsible on the main-chat card — the report stays in the
        # sub-agent window so the main transcript holds only orchestrator content.
        from textual.widgets import Collapsible

        reports = [w for w in card.query(Collapsible)]
        assert not reports, "sub-agent report must not be echoed into the main transcript"


async def test_welcome_card_lifecycle(tmp_path: Path):
    """The welcome/help card greets on an empty chat, dismisses on the first
    message, and toggles with F1."""
    from aidbg.ui.widgets.welcome import WelcomeCard

    session = ChatSession(
        settings=_settings(),
        workspace=tmp_path,
        mcp_config=McpConfig(),
        model_override=TestModel(call_tools=[]),
    )
    app = AidbgApp(session, agent_names=AGENTS.names())
    async with app.run_test() as pilot:
        cv = app._chat
        assert cv._welcome is not None and app.query(WelcomeCard), "welcome not shown on start"

        # F1 toggles it off, then back on.
        await pilot.press("f1")
        await pilot.pause()
        assert cv._welcome is None and not app.query(WelcomeCard), "F1 did not hide welcome"
        await pilot.press("f1")
        await pilot.pause()
        assert cv._welcome is not None, "F1 did not re-show welcome"

        # The first user message dismisses the card for good.
        await cv.add_user_message("分析 samples/fake_evidence 为什么反复重启")
        await pilot.pause()
        assert cv._welcome is None and not app.query(WelcomeCard), "welcome not dismissed on message"


async def test_subagent_events_route_to_panel_not_main(tmp_path: Path):
    """Sub-agent content lands in the sub-agent window; the main transcript
    only carries orchestrator content. Delegations reveal/hide the panel."""
    session = ChatSession(
        settings=_settings(),
        workspace=tmp_path,
        mcp_config=McpConfig(),
        model_override=TestModel(call_tools=[]),
    )
    app = AidbgApp(session, agent_names=AGENTS.names())
    async with app.run_test() as pilot:
        sp = app._subpanel
        assert sp.display is False, "sub-agent panel hidden until a delegation"

        # Orchestrator answer -> main chat, not the panel.
        app.post_message(UiEventArrived(ev.MessageStarted(agent="orchestrator", message_id="orchestrator-1")))
        app.post_message(UiEventArrived(ev.TokenDelta(agent="orchestrator", message_id="orchestrator-1", text="hi")))
        await pilot.pause()
        assert "orchestrator-1" in app._chat._by_id
        assert "orchestrator-1" not in sp._msg_pane

        # Delegation reveals the panel and opens a tab for the child.
        app.post_message(UiEventArrived(ev.DelegationStarted(parent="orchestrator", child="log-analyst", task="分析日志")))
        await pilot.pause()
        assert sp.display is True, "panel revealed on delegation"
        assert "log-analyst" in sp._panes

        # Sub-agent answer -> panel, NOT the main chat.
        app.post_message(UiEventArrived(ev.MessageStarted(agent="log-analyst", message_id="log-analyst-1")))
        app.post_message(UiEventArrived(ev.TokenDelta(agent="log-analyst", message_id="log-analyst-1", text="报告")))
        await pilot.pause()
        assert "log-analyst-1" in sp._msg_pane, "sub-agent message should route to the panel"
        assert "log-analyst-1" not in app._chat._by_id, "sub-agent content must not echo to main chat"

        # Sub-agent tool call bumps its pane counter.
        app.post_message(UiEventArrived(ev.ToolCallStarted(agent="log-analyst", tool_name="read_log", tool_call_id="t1")))
        await pilot.pause()
        assert sp._panes["log-analyst"]._tool_calls == 1

        # Finish flips the pane to done.
        app.post_message(UiEventArrived(ev.DelegationFinished(parent="orchestrator", child="log-analyst", output_preview="ok", full_output="full")))
        await pilot.pause()
        assert sp._panes["log-analyst"].has_class("done")

        # A new turn resets + hides the panel.
        await sp.reset()
        await pilot.pause()
        assert sp.display is False and not sp._panes
