"""Researcher sub-agent spec."""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="researcher",
        description=(
            "Delegate a self-contained research question (gather/summarize "
            "information). Pass the question as `task`."
        ),
        profile="researcher",
        instructions_path="prompts/researcher.md",
        tool_names=(),
    )
)
