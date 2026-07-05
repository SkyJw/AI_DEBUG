"""Build live ``MCPToolset`` objects from MCP server specs.

pydantic-ai 2.x unifies MCP behind ``MCPToolset(<transport>)``, where the
transport is ``StdioTransport`` (spawn a subprocess) or
``StreamableHttpTransport`` (remote HTTP server). Toolsets are mounted on an
agent via ``Agent(toolsets=[...])`` and their tools appear as normal tool calls.
"""

from __future__ import annotations

from pydantic_ai.mcp import MCPToolset, StdioTransport, StreamableHttpTransport

from aidbg.config.mcp import McpConfig, McpServerSpec


def _build_one(spec: McpServerSpec) -> MCPToolset:
    transport: StdioTransport | StreamableHttpTransport
    if spec.kind == "http":
        if not spec.url:
            raise ValueError(f"MCP server {spec.name!r} kind=http requires 'url'")
        transport = StreamableHttpTransport(url=spec.url, headers=spec.headers or None)
    else:  # stdio
        if not spec.command:
            raise ValueError(f"MCP server {spec.name!r} kind=stdio requires 'command'")
        transport = StdioTransport(
            command=spec.command,
            args=spec.args,
            env=spec.env or None,
        )
    return MCPToolset(transport, id=spec.name)


def build_toolsets(config: McpConfig, names: tuple[str, ...]) -> list[MCPToolset]:
    """Build the toolsets an agent requested by name.

    Unknown names raise, so a typo in an :class:`~aidbg.core.registry.AgentSpec`
    surfaces immediately rather than silently dropping a capability.
    """
    toolsets: list[MCPToolset] = []
    for name in names:
        spec = config.by_name(name)
        if spec is None:
            available = [s.name for s in config.servers]
            raise KeyError(f"unknown MCP server {name!r}; configured: {available}")
        toolsets.append(_build_one(spec))
    return toolsets
