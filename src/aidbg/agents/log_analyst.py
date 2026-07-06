"""Log-analyst sub-agent spec.

Locates faults in embedded-Linux board log bundles. Reads evidence through the
typed log tools (``log_tools.py``) — orient, pull the high-signal targeted view,
drill down, ground hypotheses in the problem catalogue — and returns a Markdown
triage report with stable ``bundle/source:line_no`` coordinates.

Wiring mirrors the other sub-agents: registered here, imported before the
orchestrator in ``agents/__init__.py``, listed in the orchestrator's
``delegates_to`` — after which a ``delegate_to_log_analyst`` tool appears.
"""

from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(
    AgentSpec(
        name="log-analyst",
        description=(
            "Delegate embedded-Linux board log triage. Give it an evidence directory "
            "(under the workspace) and a question, e.g. 'why does samples/fake_evidence "
            "show repeated reboots?'. Returns a Markdown report: conclusion, ranked "
            "root-cause hypotheses with cited log coordinates, and next verify steps. "
            "Pass the evidence dir + question as `task`."
        ),
        profile="analyst",
        instructions_path="prompts/log_analyst.md",
        tool_names=(
            "list_evidence",
            "targeted_view",
            "read_log",
            "describe_problem",
            "record_finding",
        ),
    )
)
