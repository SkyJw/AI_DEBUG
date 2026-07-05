"""History save/load round-trip through ModelMessagesTypeAdapter."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from aidbg.session.history import load_history, save_history


def test_roundtrip(tmp_path: Path):
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hello")]),
        ModelResponse(parts=[TextPart(content="hi there")]),
    ]
    path = tmp_path / "nested" / "history.json"
    save_history(path, messages)
    assert path.is_file()

    loaded = load_history(path)
    assert len(loaded) == 2
    assert loaded[0].parts[0].content == "hello"
    assert loaded[1].parts[0].content == "hi there"


def test_missing_file_yields_empty(tmp_path: Path):
    assert load_history(tmp_path / "nope.json") == []


def test_empty_file_yields_empty(tmp_path: Path):
    p = tmp_path / "empty.json"
    p.write_text("")
    assert load_history(p) == []
