"""The bottom input bar where the user types prompts."""

from __future__ import annotations

from textual.widgets import Input


class InputBar(Input):
    """Prompt input. Disabled while a turn is running."""

    def __init__(self) -> None:
        super().__init__(placeholder="Type a message… (Ctrl+S save, Ctrl+C quit)")
