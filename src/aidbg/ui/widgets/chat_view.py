"""The scrolling chat transcript: a column of message / thinking / delegation
widgets."""

from __future__ import annotations

from aidbg.ui.widgets.chat_message import ChatMessage, DelegationCard, ThinkingMessage

from textual.containers import VerticalScroll


class ChatView(VerticalScroll):
    """Vertical scroll of chat messages keyed by message id.

    Values are either :class:`ChatMessage` (answers) or :class:`ThinkingMessage`
    (reasoning) — both expose the same async ``append``/``finalize`` interface.
    Delegation cards are tracked separately, keyed by ``(parent, child)`` on a
    small stack so a finish matches the most recent matching start.
    """

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, ChatMessage | ThinkingMessage] = {}
        self._deleg_stacks: dict[tuple[str, str], list[DelegationCard]] = {}

    async def add_user_message(self, text: str) -> None:
        msg = ChatMessage(agent="you", role="user", initial=text)
        await self.mount(msg)
        self.scroll_end(animate=False)

    async def start_message(self, agent: str, message_id: str, kind: str = "answer") -> None:
        if message_id in self._by_id:
            return
        widget: ChatMessage | ThinkingMessage
        if kind == "thinking":
            widget = ThinkingMessage(agent=agent)
        else:
            widget = ChatMessage(agent=agent, role="assistant")
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

    async def start_delegation(self, parent: str, child: str, task: str) -> None:
        """Mount a delegation card marking a dispatch to a sub-agent."""
        card = DelegationCard(parent_agent=parent, child=child, task=task)
        self._deleg_stacks.setdefault((parent, child), []).append(card)
        await self.mount(card)
        self.scroll_end(animate=False)

    async def finish_delegation(
        self, parent: str, child: str, preview: str = "", full_output: str = ""
    ) -> None:
        """Flip the most recent matching delegation card to done."""
        stack = self._deleg_stacks.get((parent, child))
        if stack:
            await stack.pop().finish(preview, full_output)

    def note_tool_call(self, agent: str) -> None:
        """Bump the live tool-count on any running card whose child is ``agent``.

        Tool calls are tagged by the agent making them, so a sub-agent's own tool
        calls land on its card while the orchestrator's delegate calls do not.
        """
        for (_parent, child), stack in self._deleg_stacks.items():
            if child != agent:
                continue
            for card in stack:
                if "running" in card.classes:
                    card.note_tool_call()
