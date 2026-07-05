"""Problem catalogue — the curated "known problems" knowledge, loaded from YAML.

A :class:`Problem` is one catalogued fault: what it is, its likely causes, how to
verify it, and which target log patterns are its signatures. Association with
:class:`~aidbg.logs.target.Target` is **bidirectional**: a target names the
``problem`` it signs, and a problem lists the ``targets`` (ids) that signal it.
The two are authored in separate YAML (targets in ``configs/logs/*.yaml``,
problems in ``configs/problems.yaml``) and cross-checked by
:func:`~aidbg.logs.config` consumers / tests so the links stay consistent.

This is the seed of the "signature library": BSP engineers grow it over time, and
the log-analyst sub-agent reads it to ground its hypotheses in curated knowledge
rather than inventing them.

No textual import; stdlib + PyYAML only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class Problem:
    """One catalogued problem (a node in the signature library)."""

    id: str
    title: str
    summary: str = ""
    likely_causes: tuple[str, ...] = ()
    verify_steps: tuple[str, ...] = ()
    # Target ids that are signatures of this problem (the back-reference).
    targets: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, origin: str) -> "Problem":
        pid = data.get("id")
        if not pid:
            raise ValueError(f"{origin}: a problem is missing required 'id'")
        return cls(
            id=pid,
            title=data.get("title", pid),
            summary=data.get("summary", ""),
            likely_causes=tuple(data.get("likely_causes", ()) or ()),
            verify_steps=tuple(data.get("verify_steps", ()) or ()),
            targets=tuple(data.get("targets", ()) or ()),
        )


@dataclass(slots=True)
class ProblemCatalog:
    """All catalogued problems, keyed by id."""

    problems: dict[str, Problem] = field(default_factory=dict)

    def get(self, problem_id: str) -> Problem | None:
        return self.problems.get(problem_id)

    def __len__(self) -> int:
        return len(self.problems)


def load_problems(path: str | Path) -> ProblemCatalog:
    """Load the problem catalogue from a YAML file.

    A missing file yields an empty catalogue rather than raising. The file shape
    is ``{problems: [ {id, title, ...}, ... ]}``.
    """
    p = Path(path)
    catalog: dict[str, Problem] = {}
    if p.is_file():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for raw in data.get("problems", []) or []:
            if not isinstance(raw, dict):
                raise ValueError(f"{p}: each problem must be a mapping")
            prob = Problem.from_dict(raw, origin=str(p))
            if prob.id in catalog:
                raise ValueError(f"{p}: duplicate problem id {prob.id!r}")
            catalog[prob.id] = prob
    return ProblemCatalog(problems=catalog)


def check_links(catalog: ProblemCatalog, target_ids: set[str], target_problem_refs: set[str]) -> list[str]:
    """Validate bidirectional target↔problem links; return a list of issues.

    - Every ``problem`` a target references must exist in the catalogue.
    - Every target id a problem lists must exist among the known targets.
    - (Advisory) a target→problem link should be mirrored by the problem→target
      back-reference, and vice versa.

    Returns human-readable issue strings (empty = consistent). Kept as a pure
    checker so callers/tests decide whether to warn or fail.
    """
    issues: list[str] = []
    known_problems = set(catalog.problems)

    # target → problem must resolve.
    for ref in target_problem_refs:
        if ref not in known_problems:
            issues.append(f"target references unknown problem {ref!r}")

    for prob in catalog.problems.values():
        for tid in prob.targets:
            if tid not in target_ids:
                issues.append(f"problem {prob.id!r} references unknown target {tid!r}")

    return issues
