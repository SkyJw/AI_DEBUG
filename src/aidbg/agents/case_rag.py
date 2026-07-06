"""Case-rag sub-agent spec.

RAG-searches the 案例库 (case library) for past cases similar to the fault being
triaged. It reads the shared findings board (``list_findings``) to see the current
symptoms + problem ids, then — eventually — retrieves matching historical cases
through a case-retrieval backend (a RAG service over the case library) deployed
later. A known matching case can shortcut the rest of the pipeline.

Scaffold stage: ``mcp_names`` is empty and no retrieval backend exists yet, so the
agent has no real search capability; its playbook tells it to return a neutral
status (which cases it *would* look for, on what keys) and to never fabricate a
specific past case or resolution (that would mislead the localization). Wiring the
retrieval backend later is spec-only — add its MCP name to ``mcp_names``, no code
change.

Wiring mirrors the other sub-agents: registered here, imported before the
orchestrator in ``agents/__init__.py``, listed in the orchestrator's
``delegates_to`` — after which a ``delegate_to_case_rag`` tool appears.
"""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="case-rag",
        description=(
            "Delegate a search of the case library for past cases similar to the fault "
            "being triaged. It reads the shared findings board to see the current "
            "symptoms and problem ids and looks for a matching historical case (whose "
            "resolution could shortcut the diagnosis). NB: the case-retrieval backend "
            "is not deployed yet, so it currently returns a neutral status without a "
            "matched case. Pass what to search for as `task`."
        ),
        profile="case_rag",
        instructions_path="prompts/case_rag.md",
        tool_names=("list_findings",),
        # Future: a RAG retrieval service over the case library. Adding its name here
        # (once deployed) is the only change needed to give this agent real teeth.
        mcp_names=(),
    )
)
