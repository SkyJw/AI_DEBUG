"""Settings: profile grouping from env, agent->profile routing, MCP config parse."""

from __future__ import annotations

import json
from pathlib import Path

from aidbg.config.mcp import load_mcp_config
from aidbg.config.settings import Settings, load_settings


def test_profile_grouping(monkeypatch):
    monkeypatch.setenv("AIDBG_DEFAULT__MODEL", "deepseek-chat")
    monkeypatch.setenv("AIDBG_DEFAULT__BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("AIDBG_OLLAMA__MODEL", "qwen2.5")
    monkeypatch.setenv("AIDBG_OLLAMA__BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("AIDBG_PROFILE_RESEARCHER", "ollama")

    s = load_settings()
    assert set(s.profiles) == {"default", "ollama"}
    assert s.profiles["default"].model == "deepseek-chat"
    assert s.profile_for("researcher").model == "qwen2.5"
    assert s.profile_for("coder").model == "deepseek-chat"


def test_missing_profile_falls_back_to_default():
    s = Settings(_env_file=None)
    # No profiles defined -> profile_for never crashes.
    assert s.profile_for("nonexistent").model  # some default string


def test_load_settings_guarantees_default(monkeypatch):
    monkeypatch.delenv("AIDBG_DEFAULT__MODEL", raising=False)
    s = load_settings()
    assert "default" in s.profiles


def test_mcp_config_parse(tmp_path: Path):
    cfg = {
        "servers": [
            {"name": "fs", "kind": "stdio", "command": "npx", "args": ["-y", "x"]},
            {"name": "api", "kind": "http", "url": "https://mcp.example/mcp"},
        ]
    }
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps(cfg))
    parsed = load_mcp_config(p)
    assert len(parsed.servers) == 2
    assert parsed.by_name("fs").command == "npx"
    assert parsed.by_name("api").kind == "http"
    assert parsed.by_name("missing") is None


def test_mcp_config_missing_file(tmp_path: Path):
    assert load_mcp_config(tmp_path / "nope.json").servers == []
