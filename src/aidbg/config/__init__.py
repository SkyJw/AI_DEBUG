"""Configuration layer: settings + MCP server specs. No pydantic-ai / textual."""

from aidbg.config.mcp import McpConfig, McpServerSpec, load_mcp_config
from aidbg.config.settings import ModelProfile, Settings, load_settings

__all__ = [
    "McpConfig",
    "McpServerSpec",
    "ModelProfile",
    "Settings",
    "load_mcp_config",
    "load_settings",
]
