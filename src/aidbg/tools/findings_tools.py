"""Tools over the shared findings board — the data channel between sub-agents.

Two thin tools, deliberately not tied to any one agent:

- ``record_finding`` — file a clue and get back its ``F<n>`` id. An analyst files
  a suspicious log line (coordinate ``bundle/source:line_no``); code-search files
  the emit site it localized (coordinate ``path:line_no``, ``refs`` the analyst's
  finding). The returned id is what downstream tasks cite instead of re-quoting.
- ``list_findings`` — read the board. The orchestrator reads it to decide the
  next dispatch; code-search reads it to pull the coordinate/text it must grep
  for. Data flows here; control flow stays with the orchestrator.

No judgement lives here — the board just stores what agents put on it. No textual
import.
"""

from __future__ import annotations

from pydantic_ai import RunContext

from aidbg.core.deps import AppDeps
from aidbg.core.registry import TOOLS


def _fmt(f) -> str:  # type: ignore[no-untyped-def]
    """One-line board row: ``F3 [code-search] summary  @path:line  ⟶problem  ←F1``."""
    bits = [f"{f.id} [{f.agent}] {f.summary}"]
    if f.coordinate:
        bits.append(f"  @{f.coordinate}")
    if f.problem:
        bits.append(f"  ⟶problem:{f.problem}")
    if f.refs:
        bits.append("  ←" + ",".join(f.refs))
    return "".join(bits)


@TOOLS.register()
async def record_finding(
    ctx: RunContext[AppDeps],
    summary: str,
    coordinate: str = "",
    problem: str = "",
    detail: str = "",
    refs: str = "",
) -> str:
    """Record a clue on the shared board so other agents can build on it.

    ``summary`` is a one-line statement of the clue. ``coordinate`` is the stable
    pointer — ``bundle/source:line_no`` for a log line, ``path:line_no`` for a
    source location. ``problem`` is a catalogued problem id if it points at one.
    ``detail`` is optional longer context (the raw log line / code snippet).
    ``refs`` is a comma-separated list of earlier finding ids this one builds on
    (e.g. ``F1,F2``). Returns the assigned id (``F<n>``) — cite it downstream.
    """
    ref_ids = tuple(r.strip().upper() for r in refs.split(",") if r.strip())
    finding = ctx.deps.findings.add(
        agent=_agent_name(ctx),
        summary=summary.strip(),
        coordinate=coordinate.strip(),
        problem=problem.strip(),
        detail=detail.strip(),
        refs=ref_ids,
    )
    return f"Recorded {finding.id}. Cite it when handing off. Board now has {len(ctx.deps.findings)} finding(s)."


@TOOLS.register()
async def list_findings(ctx: RunContext[AppDeps]) -> str:
    """List all clues currently on the shared board, oldest first.

    Read this to see what other agents have found before you act — e.g.
    code-search reads the coordinate/text an analyst filed; the orchestrator
    reads it to decide the next dispatch. Use ``detail`` fields via the ids shown.
    """
    board = ctx.deps.findings
    items = board.all()
    if not items:
        return "The findings board is empty."
    rows = [_fmt(f) for f in items]
    detailed = [f"\n{f.id} detail: {f.detail}" for f in items if f.detail]
    return (
        f"Findings board ({len(items)}):\n"
        + "\n".join(rows)
        + ("".join(detailed) if detailed else "")
    )


def _agent_name(ctx: RunContext[AppDeps]) -> str:
    """Machine name of the agent calling the tool.

    ``ctx.agent`` is the running :class:`~pydantic_ai.Agent`; its ``.name`` is the
    machine name we tag findings with (``log-analyst`` / ``code-search`` …). Fall
    back to a neutral label if it is unset.
    """
    agent = getattr(ctx, "agent", None)
    name = getattr(agent, "name", None)
    if isinstance(name, str) and name:
        return name
    return "agent"
