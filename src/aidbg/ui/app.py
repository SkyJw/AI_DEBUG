"""AidbgApp — the Textual application shell and event dispatcher.

Layout: a chat transcript (main) beside a sidebar (agent list + activity feed),
with a docked input bar. Core ``UiEvent``s arrive as ``UiEventArrived`` messages
and are dispatched here by event type to the relevant widget. This is the only
place, together with the widgets, that imports textual.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Label

from aidbg.core import events as ev
from aidbg.session.session import ChatSession
from aidbg.ui.messages import UiEventArrived
from aidbg.ui.theme import AIDBG_BLACK
from aidbg.ui.widgets.activity import ActivityLog
from aidbg.ui.widgets.agent_list import AgentList
from aidbg.ui.widgets.chat_view import ChatView
from aidbg.ui.widgets.input_bar import InputBar
from aidbg.ui.widgets.subagent_panel import SubAgentPanel
from aidbg.ui.workers import ChatController


class AidbgApp(App[None]):
    """The aidbg TUI."""

    CSS_PATH = "app.tcss"
    TITLE = "aidbg · 传送底软多智能体协同定位助手"
    BINDINGS = [
        ("ctrl+s", "save_history", "Save"),
        ("f1", "help", "帮助"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, session: ChatSession, *, agent_names: list[str]) -> None:
        super().__init__()
        self.session = session
        self.agent_names = agent_names
        # Sub-agents are every registered agent that isn't the orchestrator; their
        # events route to the sub-agent window instead of the main transcript.
        self._subagent_names = {n for n in agent_names if n != "orchestrator"}
        # message_id -> producing agent, so token/thinking/finish deltas (which
        # carry only a message_id) can be routed to the right window.
        self._msg_owner: dict[str, str] = {}
        self.controller = ChatController(self, session)
        self._chat: ChatView
        self._activity: ActivityLog
        self._agents: AgentList
        self._input: InputBar
        self._subpanel: SubAgentPanel

    # --- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        self._chat = ChatView()
        self._activity = ActivityLog()
        self._agents = AgentList(self.agent_names)
        self._input = InputBar()
        self._subpanel = SubAgentPanel()
        with Vertical(id="main"):
            yield self._chat
            yield self._input
        yield self._subpanel
        with Vertical(id="sidebar"):
            yield Label("Agents", classes="sidebar-title")
            yield self._agents
            yield Label("Activity", classes="sidebar-title")
            yield self._activity
        yield Footer()

    def on_mount(self) -> None:
        # Register the pure-black theme, then honor settings.theme (defaults to
        # "aidbg-black"). An unknown name falls back to black rather than erroring.
        self.register_theme(AIDBG_BLACK)
        try:
            self.theme = self.session.settings.theme or AIDBG_BLACK.name
        except Exception:
            self.theme = AIDBG_BLACK.name
        self._input.focus()
        self._update_usage("")

    # --- input -------------------------------------------------------------

    def on_input_submitted(self, message: InputBar.Submitted) -> None:
        prompt = message.value.strip()
        if not prompt:
            return
        self._input.value = ""
        self._input.disabled = True
        self.run_worker(self._begin_turn(prompt), exclusive=False)

    async def _begin_turn(self, prompt: str) -> None:
        # Fresh turn: clear the sub-agent window and message routing map.
        self._msg_owner.clear()
        await self._subpanel.reset()
        await self._chat.add_user_message(prompt)
        self.controller.run_turn(prompt)

    def on_turn_complete(self) -> None:
        """Called by the controller when a turn's worker finishes."""
        self._input.disabled = False
        self._input.focus()

    # --- core event dispatch ----------------------------------------------

    async def on_ui_event_arrived(self, message: UiEventArrived) -> None:
        e = message.event
        if isinstance(e, ev.MessageStarted):
            self._msg_owner[e.message_id] = e.agent
            if e.agent in self._subagent_names:
                await self._subpanel.start_message(e.agent, e.message_id, e.kind)
            else:
                await self._chat.start_message(e.agent, e.message_id, e.kind)
            self._agents.highlight_agent(e.agent)
        elif isinstance(e, ev.TokenDelta):
            if self._msg_owner.get(e.message_id) in self._subagent_names:
                await self._subpanel.append_token(e.message_id, e.text)
            else:
                await self._chat.append_token(e.message_id, e.text)
        elif isinstance(e, ev.ThinkingDelta):
            # Thinking has its own message id / block; stream it to its window.
            if self._msg_owner.get(e.message_id) in self._subagent_names:
                await self._subpanel.append_token(e.message_id, e.text)
            else:
                await self._chat.append_token(e.message_id, e.text)
        elif isinstance(e, ev.MessageFinished):
            if self._msg_owner.get(e.message_id) in self._subagent_names:
                await self._subpanel.finish_message(e.message_id)
            else:
                await self._chat.finish_message(e.message_id)
        elif isinstance(e, ev.ToolCallStarted):
            self._chat.note_tool_call(e.agent)
            if e.agent in self._subagent_names:
                await self._subpanel.note_tool(e.agent, e.tool_name, e.args_preview)
            self._activity.tool_started(e.agent, e.tool_name, e.args_preview)
        elif isinstance(e, ev.ToolCallFinished):
            self._activity.tool_finished(e.agent, e.tool_name, e.result_preview)
        elif isinstance(e, ev.DelegationStarted):
            # Slim breadcrumb in main; the sub-agent's work lives in its window.
            await self._chat.start_delegation(e.parent, e.child, e.task)
            await self._subpanel.open_agent(e.child, e.task)
            self._activity.delegation_started(e.parent, e.child, e.task)
            self._agents.highlight_agent(e.child)
        elif isinstance(e, ev.DelegationFinished):
            # Do not echo the sub-agent's report into the main window.
            await self._chat.finish_delegation(e.parent, e.child, "", "")
            self._subpanel.close_agent(e.child)
            self._activity.delegation_finished(e.parent, e.child, e.output_preview)
            self._agents.highlight_agent(e.parent)
        elif isinstance(e, ev.RunFinished):
            self._update_usage(e.usage_summary)
        elif isinstance(e, ev.RunError):
            if e.agent in self._subagent_names:
                await self._subpanel.error(e.agent, e.message)
            self._activity.run_error(e.agent, e.message)

    def _update_usage(self, summary: str) -> None:
        self.sub_title = f"usage: {summary}" if summary else ""

    # --- actions -----------------------------------------------------------

    def action_save_history(self) -> None:
        path = self.session.save()
        self._activity.write(f"[green]saved history →[/] {path}")

    def action_help(self) -> None:
        """Toggle the welcome/help card in the transcript."""
        self._chat.toggle_welcome()
