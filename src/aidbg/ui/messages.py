"""Textual Message wrappers bridging the core EventBus into the widget system.

The core layer publishes ``UiEvent``s to an asyncio queue; a UI worker drains
that queue and re-posts each event as a Textual ``Message`` (thread/async-safe
via ``post_message``) so it's handled on the UI thread.
"""

from __future__ import annotations

from textual.message import Message

from aidbg.core.events import UiEvent


class UiEventArrived(Message):
    """One core ``UiEvent`` delivered onto the Textual message pump."""

    def __init__(self, event: UiEvent) -> None:
        super().__init__()
        self.event = event
