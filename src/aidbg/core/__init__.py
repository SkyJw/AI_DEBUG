"""Core layer: pydantic-ai wiring, registries, event bus. No textual import."""

from aidbg.core.agent_factory import build_agent, build_all, build_orchestrator
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.registry import AGENTS, TOOLS, AgentRegistry, AgentSpec, ToolRegistry
from aidbg.core.streaming import pump_agent_run

__all__ = [
    "AGENTS",
    "TOOLS",
    "AgentRegistry",
    "AgentSpec",
    "AppDeps",
    "EventBus",
    "ToolRegistry",
    "build_agent",
    "build_all",
    "build_orchestrator",
    "pump_agent_run",
]
