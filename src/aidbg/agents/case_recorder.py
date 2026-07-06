"""Case-recorder sub-agent spec.

Distills a completed triage into a **case** for the 案例库 (case library): the
symptom, the evidence coordinates, the root-cause conclusion, and the resolution —
so a future case-rag search can find it. It reads the shared findings board
(``list_findings``) to see what this triage established, then — eventually —
persists the case through a case-store backend deployed later.

Scaffold stage: ``mcp_names`` is empty and no case store exists yet, so the agent
cannot persist anything; its playbook tells it to return a neutral status (the
case it *would* write, as a sketch) and to never claim a case was saved or invent
prior cases. Wiring the case-store later is spec-only — add its MCP name to
``mcp_names``, no code change.

Wiring mirrors the other sub-agents: registered here, imported before the
orchestrator in ``agents/__init__.py``, listed in the orchestrator's
``delegates_to`` — after which a ``delegate_to_case_recorder`` tool appears.
"""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="case-recorder",
        description=(
            "Delegate turning a completed triage into a case for the case library: "
            "symptom, cited evidence coordinates, root-cause conclusion, resolution. "
            "It reads the shared findings board to summarize what was established. NB: "
            "the case store is not wired yet, so it currently only shows the case it "
            "would record without persisting it. Delegate this last, after the "
            "diagnosis is synthesized. Pass any recording instructions as `task`."
        ),
        profile="case_recorder",
        instructions_path="prompts/case_recorder.md",
        tool_names=("list_findings",),
        # Future: a case-store backend (persist to the case library). Adding its name
        # here (once deployed) is the only change needed to give this agent real teeth.
        mcp_names=(),
    )
)
