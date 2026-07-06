"""Orchestrator agent spec — the primary agent that delegates to sub-agents.

``delegates_to`` drives which ``delegate_to_<child>`` tools are attached by
``build_orchestrator``; those children must be registered first (import order in
``agents/__init__.py`` guarantees it).
"""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="orchestrator",
        description="Primary coordinating agent.",
        profile="orchestrator",
        instructions_path="prompts/orchestrator.md",
        tool_names=("read_file",),
        delegates_to=("coder", "researcher", "code-reviewer", "log-analyst", "code-research"),
    )
)
