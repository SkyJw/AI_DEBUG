"""Chat message widgets: a streaming answer bubble, a thinking block, or a
delegation card.

Answer messages render a badge + streaming Markdown (the official Textual
``MarkdownStream`` incremental path). Thinking messages render a dimmed,
collapsible block that streams the model's reasoning and auto-collapses once the
thought completes — mirroring the way Claude Code / opencode surface reasoning.
Delegation cards make the orchestrator's dispatch visible inline: which sub-agent
got what task, with a live "running…" state that flips to "done" so the user can
see when a turn is waiting on a sub-agent.
``MarkdownStream.write``/``stop`` are async, so ``append``/``finalize`` are too.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Collapsible, Label, Markdown
from textual.widgets.markdown import MarkdownStream

from aidbg.ui.names import display_name


class ChatMessage(Vertical):
    """One answer bubble: an agent badge + a streaming Markdown body."""

    def __init__(self, *, agent: str, role: str = "assistant", initial: str = "") -> None:
        super().__init__()
        self._agent = agent
        self._role = role
        self._buffer = initial
        self._md: Markdown | None = None
        self._stream: MarkdownStream | None = None
        self.add_class(f"role-{role}")

    def compose(self) -> ComposeResult:
        badge = display_name(self._agent) if self._role == "assistant" else display_name("you")
        yield Label(badge, classes="msg-badge")
        self._md = Markdown(self._buffer)
        yield self._md

    def on_mount(self) -> None:
        # Open a stream for assistant messages so tokens render incrementally.
        if self._role == "assistant" and self._md is not None:
            self._stream = Markdown.get_stream(self._md)

    async def append(self, text: str) -> None:
        """Append a token chunk to the streaming body."""
        self._buffer += text
        if self._stream is not None:
            await self._stream.write(text)
        elif self._md is not None:
            await self._md.update(self._buffer)

    async def finalize(self) -> None:
        """Close the stream once the message is complete."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None


class ThinkingMessage(Vertical):
    """A dimmed, collapsible block that streams the model's reasoning.

    Expanded while the thought streams so the process is visible; collapses on
    :meth:`finalize` so the transcript stays focused on answers.
    """

    def __init__(self, *, agent: str) -> None:
        super().__init__()
        self._agent = agent
        self._buffer = ""
        self._md: Markdown | None = None
        self._stream: MarkdownStream | None = None
        self._collapsible: Collapsible | None = None
        self.add_class("role-thinking")

    def compose(self) -> ComposeResult:
        self._md = Markdown("")
        self._collapsible = Collapsible(
            self._md,
            title=f"✳ {display_name(self._agent)} 思考中…",
            collapsed=False,
            collapsed_symbol="▸",
            expanded_symbol="▾",
        )
        yield self._collapsible

    def on_mount(self) -> None:
        if self._md is not None:
            self._stream = Markdown.get_stream(self._md)

    async def append(self, text: str) -> None:
        self._buffer += text
        if self._stream is not None:
            await self._stream.write(text)
        elif self._md is not None:
            await self._md.update(self._buffer)

    async def finalize(self) -> None:
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None
        # Fold the reasoning away and relabel once it's done.
        if self._collapsible is not None:
            self._collapsible.title = f"✳ {display_name(self._agent)} 思考完成"
            self._collapsible.collapsed = True


class DelegationCard(Vertical):
    """An inline card marking the orchestrator dispatching a task to a sub-agent.

    Built to make multi-agent collaboration legible in a demo:

    - title + task show *who* was dispatched to do *what* (Chinese labels);
    - while running: an animated ``…`` plus a live ``工具 N 次 · 用时 Ns`` counter
      so the user sees the sub-agent actually working;
    - on finish: the status flips to done and the sub-agent's full report is
      mounted as a collapsible block (collapsed → the conclusion; expand → full).
    """

    _DOTS = ("", ".", "..", "...")

    def __init__(self, *, parent_agent: str, child: str, task: str) -> None:
        super().__init__()
        # NB: avoid the names `_parent` (DOMNode stores a weakref there) and
        # `_task` (Widget types it as an asyncio Task) — both are Textual internals.
        self._parent_agent = parent_agent
        self._child = child
        self._child_label = display_name(child)
        self._task_text = task
        self._status: Label | None = None
        self._tool_calls = 0
        self._start = time.monotonic()
        self._tick = 0
        self._timer: Timer | None = None
        self.add_class("running")

    def compose(self) -> ComposeResult:
        parent_label = display_name(self._parent_agent)
        yield Label(
            f"🔀 {parent_label} 调用子智能体 →「{self._child_label}」",
            classes="deleg-title",
        )
        if self._task_text:
            yield Label(f"下发任务：{self._task_text}", classes="deleg-task")
        self._status = Label("", classes="deleg-status")
        yield self._status

    def on_mount(self) -> None:
        self._render_running()
        # Animate the status line ~3x/sec so "running" visibly pulses.
        self._timer = self.set_interval(0.35, self._render_running)

    def _elapsed(self) -> int:
        return int(time.monotonic() - self._start)

    def _render_running(self) -> None:
        if self._status is None:
            return
        self._tick = (self._tick + 1) % len(self._DOTS)
        dots = self._DOTS[self._tick]
        meta = f"（已调用工具 {self._tool_calls} 次 · 用时 {self._elapsed()}s）"
        self._status.update(f"⏳ 子智能体「{self._child_label}」执行中{dots} {meta}")

    def note_tool_call(self) -> None:
        """Increment the live tool-call counter (called on the child's tool starts)."""
        self._tool_calls += 1
        if "running" in self.classes:
            self._render_running()

    async def finish(self, preview: str = "", full_output: str = "") -> None:
        """Flip to done: stop the animation, show a summary + collapsible report."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.remove_class("running")
        self.add_class("done")
        if self._status is not None:
            self._status.update(
                f"✅ 子智能体「{self._child_label}」已完成"
                f"（共调用工具 {self._tool_calls} 次 · 用时 {self._elapsed()}s）"
            )
        report = full_output or preview
        if report:
            md = Markdown(report)
            block = Collapsible(
                md,
                title=f"📄 展开「{self._child_label}」的完整报告",
                collapsed=True,
                collapsed_symbol="▸",
                expanded_symbol="▾",
            )
            block.add_class("deleg-report")
            await self.mount(block)
