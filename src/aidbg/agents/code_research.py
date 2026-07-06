"""Code-research sub-agent spec.

Researches BSP source code to help localize a fault the log-analyst has already
narrowed down. It reads the shared findings board (``list_findings``) to see which
log clue to investigate, then — eventually — researches the real source tree
through MCP services (a code knowledge-graph service + a code-search service) that
will be deployed later.

Scaffold stage: ``mcp_names`` is empty, so the agent has no real code-inspection
capability yet; its playbook tells it to return a neutral status and to never
fabricate source locations (that would poison the orchestrator's localization).
Wiring the MCP services later is spec-only — add their names to ``mcp_names``, no
code change.

Wiring mirrors the other sub-agents: registered here, imported before the
orchestrator in ``agents/__init__.py``, listed in the orchestrator's
``delegates_to`` — after which a ``delegate_to_code_research`` tool appears.
"""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="code-research",
        description=(
            "Delegate source-code research for a fault the log-analyst has narrowed "
            "down. It reads the shared findings board to see which log clue to "
            "investigate and researches where in the BSP source that behavior "
            "originates. NB: code-research backends (MCP) are not deployed yet, so it "
            "currently returns a neutral status without source-level conclusions. "
            "Pass what to research as `task`."
        ),
        profile="code_research",
        instructions_path="prompts/code_research.md",
        tool_names=("list_findings",),
        # Future: code knowledge-graph + code-search MCP services. Adding them here
        # (once deployed) is the only change needed to give this agent real teeth.
        mcp_names=(),
    )
)
