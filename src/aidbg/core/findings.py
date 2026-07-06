"""The shared findings blackboard — how sub-agents pass clues without talking.

Delegation in this framework is a stateless text pipe (``delegate(task) -> str``);
sub-agents share nothing but :class:`~aidbg.core.deps.AppDeps`. That is fine for
one agent, but the log-triage team is a *relay*: log-analyst finds a suspicious
line, code-search must grep the source for the exact message, RAG must look up a
guide for the exact problem id. Passing those coordinates through the
orchestrator as prose loses precision.

So we separate the two channels:

- **control flow** (who runs when) stays with the orchestrator — the star
  topology, every dispatch visible as a delegation card;
- **data flow** (what they share) goes through this board — an append-only list
  of :class:`Finding`\\ s, each with a stable id (``F1``, ``F2`` …) that agents
  cite instead of re-quoting the raw evidence.

One agent writes a finding + returns its id; the next agent's task is just
"confirm F3", and it reads the real data (coordinate, raw text, problem id) from
the board. The board is created once per run and lives in ``AppDeps.findings``.

Pure data structure — no textual, no pydantic-ai. Access is from async tool
callables within a single event loop (asyncio is cooperative and ``add`` has no
await point, so id assignment is atomic without a lock).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True, slots=True)
class Finding:
    """One clue on the board, addressable by :attr:`id` across agents.

    ``coordinate`` is the stable pointer the whole system already speaks — a log
    coord ``bundle/source:line_no`` when an analyst files it, or a source coord
    ``path:line_no`` once code-search localizes the emit site. ``refs`` link a
    finding to the earlier finding(s) it builds on (e.g. a code-search result
    refs the analyst finding it confirmed), so the chain is reconstructable.
    """

    id: str
    agent: str  # machine name of the agent that filed it (e.g. "log-analyst")
    summary: str  # one-line human/LLM-readable statement of the clue
    coordinate: str = ""  # bundle/source:line_no  OR  path:line_no  (optional)
    problem: str = ""  # catalogued problem id, if this clue points at one
    detail: str = ""  # optional longer body (raw log line, code snippet …)
    refs: tuple[str, ...] = ()  # ids of findings this one builds on


@dataclass(slots=True)
class FindingsBoard:
    """Append-only, run-scoped store of :class:`Finding`\\ s shared by all agents."""

    _items: list[Finding] = field(default_factory=list)
    _seq: int = 0

    def add(
        self,
        *,
        agent: str,
        summary: str,
        coordinate: str = "",
        problem: str = "",
        detail: str = "",
        refs: tuple[str, ...] = (),
    ) -> Finding:
        """Append a finding, assign the next ``F<n>`` id, and return it.

        No await between reading ``_seq`` and appending, so the id is unique even
        under concurrent tool calls on one event loop.
        """
        self._seq += 1
        finding = Finding(
            id=f"F{self._seq}",
            agent=agent,
            summary=summary,
            coordinate=coordinate,
            problem=problem,
            detail=detail,
            refs=tuple(refs),
        )
        self._items.append(finding)
        return finding

    def get(self, finding_id: str) -> Finding | None:
        """Look up a finding by id (case-insensitive on the ``F`` prefix)."""
        want = finding_id.strip().upper()
        for item in self._items:
            if item.id == want:
                return item
        return None

    def all(self) -> list[Finding]:
        """All findings in insertion order (a shallow copy — the board is owned here)."""
        return list(self._items)

    def replace_detail(self, finding_id: str, detail: str) -> Finding | None:
        """Return a copy of a finding with new ``detail`` swapped in on the board.

        Findings are immutable; this rebinds the slot so late-arriving context can
        be attached without minting a new id. Returns ``None`` if id is unknown.
        """
        want = finding_id.strip().upper()
        for i, item in enumerate(self._items):
            if item.id == want:
                updated = replace(item, detail=detail)
                self._items[i] = updated
                return updated
        return None

    def __len__(self) -> int:
        return len(self._items)
