"""Parse ``mcp_servers.json`` into structured specs.

Kept UI- and pydantic-ai-agnostic: this only reads and validates JSON into
:class:`McpServerSpec`. ``core/mcp.py`` turns specs into live ``MCPToolset``s.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class McpServerSpec(BaseModel):
    """One MCP server entry from ``mcp_servers.json``."""

    name: str
    kind: Literal["stdio", "http"] = "stdio"

    # stdio transport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    # http transport
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class McpConfig(BaseModel):
    """Top-level shape of ``mcp_servers.json``."""

    servers: list[McpServerSpec] = Field(default_factory=list)

    def by_name(self, name: str) -> McpServerSpec | None:
        return next((s for s in self.servers if s.name == name), None)


def load_mcp_config(path: str | Path) -> McpConfig:
    """Load MCP server specs. Missing file yields an empty config (MCP optional)."""
    p = Path(path)
    if not p.is_file():
        return McpConfig()
    data = json.loads(p.read_text(encoding="utf-8"))
    return McpConfig.model_validate(data)
