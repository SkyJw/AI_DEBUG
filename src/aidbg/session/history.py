"""Persist and restore conversation history.

pydantic-ai messages serialize via ``ModelMessagesTypeAdapter``. We store the
whole history as a single JSON document (not JSONL) for a simple, atomic
round-trip; the ``.jsonl`` extension in config is honored as a plain path.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter


def save_history(path: str | Path, messages: list[ModelMessage]) -> Path:
    """Write history to ``path`` (creating parent dirs). Returns the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(ModelMessagesTypeAdapter.dump_json(messages))
    return p


def load_history(path: str | Path) -> list[ModelMessage]:
    """Load history from ``path``. Missing/empty file yields an empty list."""
    p = Path(path)
    if not p.is_file():
        return []
    data = p.read_bytes()
    if not data.strip():
        return []
    return list(ModelMessagesTypeAdapter.validate_json(data))
