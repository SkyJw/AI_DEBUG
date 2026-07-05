"""Code-reviewer sub-agent spec.

Demonstrates the extension flow: one file registers one AgentSpec, it gets
imported in ``agents/__init__.py`` before the orchestrator, and the orchestrator
lists it in ``delegates_to`` — after which a ``delegate_to_code_reviewer`` tool
appears automatically.
"""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="code-reviewer",
        description=(
            "Delegate a self-contained code review (a diff, snippet, or file path). "
            "Returns an actionable review with a verdict and prioritized findings. "
            "Pass what to review as `task`."
        ),
        profile="reviewer",
        instructions_path="prompts/code_reviewer.md",
        tool_names=("read_file",),
    )
)
