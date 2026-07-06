"""The tmux-style sub-agent window.

When the 主智能体 (orchestrator) delegates to a sub-agent, that sub-agent's whole
execution — its streamed answer, reasoning, and tool calls — is shown here rather
than echoed into the main transcript. The main window stays focused on the
orchestrator alone.

Layout choice: **one window, one tab per sub-agent** (not N split panes). A tab
scales to any number of specialists without shrinking each to an unreadable
sliver, and Textual's ``TabbedContent`` supports adding panes at runtime. To keep
the live "focus follows the action" feel of a split, the newest sub-agent's tab
is auto-activated and each tab label carries a status badge (⏳ running + tool
count, ✅ done) so every sub-agent's state is visible at a glance in the strip.

UI-only, like the rest of ``ui/``: it consumes the same ``UiEvent`` stream the
main chat does, routed here by :class:`~aidbg.ui.app.AidbgApp` when the producing
agent is a sub-agent.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, TabbedContent, TabPane

from aidbg.ui.names import display_name
from aidbg.ui.widgets.chat_message import ChatMessage, ThinkingMessage


def _pane_id(agent: str) -> str:
    """Textual widget id for an agent's tab pane (ids allow ``-``)."""
    return f"pane-{agent}"


class AgentPane(VerticalScroll):
    """One sub-agent's live transcript: a status line, then its streamed
    messages and tool-call notes."""

    def __init__(self, agent: str) -> None:
        super().__init__()
        self._agent = agent
        self._by_id: dict[str, ChatMessage | ThinkingMessage] = {}
        self._status: Label | None = None
        self._tool_calls = 0

    def compose(self) -> ComposeResult:
        self._status = Label("", classes="pane-status")
        yield self._status

    # --- status ------------------------------------------------------------

    def set_running(self, task: str) -> None:
        if task:
            self._write_note(f"[dim]任务：{task}[/]")
        self._render_status()

    def set_done(self) -> None:
        self.add_class("done")
        self._render_status()

    def note_tool(self, tool: str, args_preview: str) -> None:
        self._tool_calls += 1
        self._write_note(f"[cyan]· 调用工具[/] [b]{tool}[/]（[dim]{args_preview}[/]）")
        self._render_status()

    def error(self, message: str) -> None:
        self.add_class("done")
        self._write_note(f"[red]✗ 出错[/]：{message}")

    def _render_status(self) -> None:
        if self._status is None:
            return
        glyph = "✅ 已完成" if self.has_class("done") else "⏳ 执行中"
        self._status.update(f"{glyph} · 已调用工具 {self._tool_calls} 次")

    def _write_note(self, markup: str) -> None:
        self.mount(Label(markup, classes="pane-note"))
        self.scroll_end(animate=False)

    # --- streamed content --------------------------------------------------

    async def start_message(self, message_id: str, kind: str = "answer") -> None:
        if message_id in self._by_id:
            return
        widget: ChatMessage | ThinkingMessage
        if kind == "thinking":
            widget = ThinkingMessage(agent=self._agent)
        else:
            widget = ChatMessage(agent=self._agent, role="assistant")
        self._by_id[message_id] = widget
        await self.mount(widget)
        self.scroll_end(animate=False)

    async def append_token(self, message_id: str, text: str) -> None:
        msg = self._by_id.get(message_id)
        if msg is not None:
            await msg.append(text)
            self.scroll_end(animate=False)

    async def finish_message(self, message_id: str) -> None:
        msg = self._by_id.get(message_id)
        if msg is not None:
            await msg.finalize()


class SubAgentPanel(Vertical):
    """Tabbed container of :class:`AgentPane`s — the sub-agent window.

    Hidden until the first delegation of a turn, then reveals with one tab per
    sub-agent that has run. ``reset`` clears it for a fresh turn.
    """

    def __init__(self) -> None:
        super().__init__()
        self._tabs: TabbedContent
        self._panes: dict[str, AgentPane] = {}
        self._msg_pane: dict[str, AgentPane] = {}

    def compose(self) -> ComposeResult:
        yield Label("子智能体执行", classes="sidebar-title")
        self._tabs = TabbedContent()
        yield self._tabs

    def on_mount(self) -> None:
        self.display = False  # revealed on first delegation

    # --- lifecycle ---------------------------------------------------------

    async def reset(self) -> None:
        """Clear all panes and hide the panel for a new turn."""
        self._panes.clear()
        self._msg_pane.clear()
        await self._tabs.clear_panes()
        self.display = False

    async def _ensure_pane(self, agent: str) -> AgentPane:
        self.display = True
        pane = self._panes.get(agent)
        if pane is None:
            pane = AgentPane(agent)
            self._panes[agent] = pane
            await self._tabs.add_pane(TabPane(display_name(agent), pane, id=_pane_id(agent)))
        return pane

    def _set_tab_badge(self, agent: str) -> None:
        pane = self._panes.get(agent)
        if pane is None:
            return
        glyph = "✅" if pane.has_class("done") else f"⏳{pane._tool_calls}"
        try:
            self._tabs.get_tab(_pane_id(agent)).label = f"{display_name(agent)} {glyph}"
        except Exception:
            pass  # tab may not be mounted yet; badge is best-effort

    async def open_agent(self, agent: str, task: str) -> None:
        """A delegation to ``agent`` started: reveal + focus its tab."""
        pane = await self._ensure_pane(agent)
        self._tabs.active = _pane_id(agent)  # auto-focus the newest
        pane.set_running(task)
        self._set_tab_badge(agent)

    def close_agent(self, agent: str) -> None:
        pane = self._panes.get(agent)
        if pane is not None:
            pane.set_done()
            self._set_tab_badge(agent)

    # --- content routing ---------------------------------------------------

    async def start_message(self, agent: str, message_id: str, kind: str = "answer") -> None:
        pane = await self._ensure_pane(agent)
        await pane.start_message(message_id, kind)
        self._msg_pane[message_id] = pane

    async def append_token(self, message_id: str, text: str) -> None:
        pane = self._msg_pane.get(message_id)
        if pane is not None:
            await pane.append_token(message_id, text)

    async def finish_message(self, message_id: str) -> None:
        pane = self._msg_pane.get(message_id)
        if pane is not None:
            await pane.finish_message(message_id)

    async def note_tool(self, agent: str, tool: str, args_preview: str) -> None:
        pane = await self._ensure_pane(agent)
        pane.note_tool(tool, args_preview)
        self._set_tab_badge(agent)

    async def error(self, agent: str, message: str) -> None:
        pane = await self._ensure_pane(agent)
        pane.error(message)
        self._set_tab_badge(agent)
