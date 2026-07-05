"""Coder sub-agent spec."""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="coder",
        description=(
            "Delegate a self-contained coding task (write/edit/explain code). "
            "Pass a precise, complete task description as `task`."
        ),
        profile="coder",
        instructions_path="prompts/coder.md",
        tool_names=("read_file",),
    )
)
