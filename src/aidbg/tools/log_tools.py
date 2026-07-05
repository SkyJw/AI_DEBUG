"""Native tools for the log-analyst sub-agent — typed queries over ``logs/``.

These are **thin** tools: they do not judge (no boot segmentation / root-cause
logic — that lives in the analyst's playbook). What they do is run *typed*
queries over the modelled evidence (Evidence → Bundle → LogFile → LogRecord) and
project the result into a compact, LLM-friendly view. Every projected line
carries a **stable coordinate** ``bundle/source:line_no`` so the analyst's report
(and any downstream agent) can point back at the exact source line.

Four tools, matching the intended workflow:

- ``list_evidence`` — orient: which bundles exist, their kind, sources, counts.
- ``targeted_view`` — the high-signal entry point: lines matching the target
  catalogue, each tagged with its ``meaning`` + linked ``problem`` id.
- ``read_log`` — drill down: a typed slice of one source, optionally filtered by
  ``level`` / ``process_id``, to read context around a suspicious line.
- ``describe_problem`` — look up a catalogued problem (causes / verify steps).

Evidence is loaded **raw/lossless** (all lines kept) and cached per directory;
annotation is applied at query time so drill-down still sees every line. Config
lives under the workspace: ``configs/logs/*.yaml`` + ``configs/problems.yaml``.

No textual import.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import RunContext

from aidbg.core.deps import AppDeps
from aidbg.core.registry import TOOLS
from aidbg.logs import (
    Bundle,
    Evidence,
    LogConfigSet,
    ProblemCatalog,
    TargetSet,
    load_evidence,
    load_log_configs,
    load_problems,
)

_LOGS_CONFIG_DIR = "configs/logs"
_PROBLEMS_FILE = "configs/problems.yaml"


@dataclass(slots=True)
class _Loaded:
    """Cached, raw/lossless load for one evidence directory."""

    evidence: Evidence
    configs: LogConfigSet
    problems: ProblemCatalog


# Cache keyed by resolved evidence path — avoids re-parsing on every tool call.
_CACHE: dict[str, _Loaded] = {}


def _resolve_under_workspace(workspace: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``workspace``, refusing paths that escape it."""
    ws = workspace.resolve()
    target = (ws / rel).resolve()
    if target != ws and ws not in target.parents:
        raise ValueError(f"path {rel!r} escapes the workspace")
    return target


def _load(ctx: RunContext[AppDeps], evidence_dir: str) -> _Loaded:
    """Load (and cache) an evidence dir raw/lossless, plus configs + problems."""
    ws = ctx.deps.workspace
    root = _resolve_under_workspace(ws, evidence_dir)
    key = str(root)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    if not root.is_dir():
        raise FileNotFoundError(f"no such evidence directory: {evidence_dir!r}")
    # Raw/lossless: keep every line so drill-down (read_log) sees full context.
    configs = load_log_configs(ws / _LOGS_CONFIG_DIR, targets_enabled=False)
    problems = load_problems(ws / _PROBLEMS_FILE)
    evidence = load_evidence(root, configs)
    loaded = _Loaded(evidence=evidence, configs=configs, problems=problems)
    _CACHE[key] = loaded
    return loaded


def _bundle_id(b: Bundle) -> str:
    """Canonical handle for a bundle, e.g. ``boot0`` / ``runtime2``."""
    return f"{b.kind.value}{b.index}"


def _find_bundle(loaded: _Loaded, bundle_id: str) -> Bundle:
    for b in loaded.evidence.bundles:
        if _bundle_id(b) == bundle_id.lower():
            return b
    known = ", ".join(_bundle_id(b) for b in loaded.evidence.bundles) or "(none)"
    raise KeyError(f"unknown bundle {bundle_id!r}; known: {known}")


def _annotating_set(loaded: _Loaded, source: str) -> TargetSet:
    """An *enabled* TargetSet for ``source`` built from config, for annotation.

    The shipped per-type sets ship disabled (lossless default); annotation is a
    query-time concern, so we force-enable a copy of the configured targets here
    without touching how evidence was parsed.
    """
    cfg = loaded.configs.configs.get(source)
    if cfg is None:
        return TargetSet()
    return TargetSet(targets=cfg.target_set.targets, enabled=True)


def _fmt_ts(rec) -> str:  # type: ignore[no-untyped-def]
    """Compact timestamp cell: real datetime, uboot ms, or '-' if unparsed."""
    ts = rec.timestamp
    if ts is None:
        return "-"
    if ts.value is not None:
        return ts.value.strftime("%Y-%m-%d %H:%M:%S")
    if ts.rel_ms is not None:
        return f"+{ts.rel_ms}ms"
    return ts.raw or "-"


# --- tool 1: list_evidence ---------------------------------------------------


@TOOLS.register()
async def list_evidence(ctx: RunContext[AppDeps], evidence_dir: str) -> str:
    """List the bundles in an evidence directory: id, kind, sources, line counts.

    Use this first to orient. ``evidence_dir`` is a path under the workspace
    (e.g. ``samples/fake_evidence``). Boot bundles are index 0 = newest.
    """
    loaded = _load(ctx, evidence_dir)
    if not loaded.evidence.bundles:
        return f"No bundles found under {evidence_dir!r}."
    lines = [f"Evidence: {evidence_dir}  ({len(loaded.evidence.bundles)} bundles)"]
    for b in loaded.evidence.bundles:
        srcs = ", ".join(f"{s}={len(lf)}" for s, lf in sorted(b.logs.items())) or "(no known logs)"
        extra = f"  unrouted={b.unrouted}" if b.unrouted else ""
        lines.append(f"  {_bundle_id(b):<10} [{b.kind.value}] {srcs}{extra}")
    lines.append(
        "\nNext: targeted_view(<bundle>, <source>) for high-signal lines, "
        "then read_log(...) to drill in."
    )
    return "\n".join(lines)


# --- tool 2: targeted_view ---------------------------------------------------


@TOOLS.register()
async def targeted_view(
    ctx: RunContext[AppDeps], evidence_dir: str, bundle: str, source: str
) -> str:
    """High-signal view: lines of ``source`` in ``bundle`` matching the target
    catalogue, each tagged with its meaning and linked problem id.

    ``source`` is ``uboot`` / ``panic`` / ``cbblog``. This is where the curated
    knowledge surfaces — start here, then read_log around anything notable.
    Lines are shown as ``bundle/source:line_no`` (a stable coordinate).
    """
    loaded = _load(ctx, evidence_dir)
    try:
        b = _find_bundle(loaded, bundle)
    except KeyError as e:
        return str(e)
    lf = b.get(source)
    if lf is None:
        have = ", ".join(sorted(b.logs)) or "(none)"
        return f"{_bundle_id(b)} has no {source!r} log. Available: {have}."
    tset = _annotating_set(loaded, source)
    bid = _bundle_id(b)
    out: list[str] = []
    for rec in lf.records:
        hits = tset.annotate(rec.raw)
        for h in hits:
            prob = f"  ⟶ problem:{h.problem}" if h.problem else ""
            out.append(f"{bid}/{source}:{rec.line_no} | {_fmt_ts(rec)} | {h.meaning}{prob}")
    if not out:
        return (
            f"No target patterns matched in {bid}/{source} "
            f"({len(lf)} lines). Use read_log to inspect raw lines."
        )
    header = f"Targeted view — {bid}/{source} ({len(out)} hits of {len(lf)} lines):"
    return header + "\n" + "\n".join(out)


# --- tool 3: read_log --------------------------------------------------------


@TOOLS.register()
async def read_log(
    ctx: RunContext[AppDeps],
    evidence_dir: str,
    bundle: str,
    source: str,
    start: int = 0,
    count: int = 60,
    level: str | None = None,
    process_id: int | None = None,
) -> str:
    """Read a slice of one source's records, for context around a finding.

    Records are in original file order (the reliable ordering key). ``start`` is a
    line number, ``count`` caps output. Optional ``level`` (e.g. ``ERROR``) and
    ``process_id`` (0/1/3/4/5/6) filter by parsed fields. Shows
    ``bundle/source:line_no | ts | message``.
    """
    loaded = _load(ctx, evidence_dir)
    try:
        b = _find_bundle(loaded, bundle)
    except KeyError as e:
        return str(e)
    lf = b.get(source)
    if lf is None:
        have = ", ".join(sorted(b.logs)) or "(none)"
        return f"{_bundle_id(b)} has no {source!r} log. Available: {have}."
    bid = _bundle_id(b)
    rows: list[str] = []
    shown = 0
    for rec in lf.records:
        if rec.line_no < start:
            continue
        if level is not None and (getattr(rec, "level", None) or "").upper() != level.upper():
            continue
        if process_id is not None and getattr(rec, "process_id", None) != process_id:
            continue
        rows.append(f"{bid}/{source}:{rec.line_no} | {_fmt_ts(rec)} | {rec.message}")
        shown += 1
        if shown >= count:
            break
    if not rows:
        return f"No matching lines in {bid}/{source} (start={start}, level={level}, pid={process_id})."
    filt = []
    if level is not None:
        filt.append(f"level={level}")
    if process_id is not None:
        filt.append(f"process_id={process_id}")
    suffix = f"  [{', '.join(filt)}]" if filt else ""
    return f"{bid}/{source} lines from {start} ({shown} shown){suffix}:\n" + "\n".join(rows)


# --- tool 4: describe_problem ------------------------------------------------


@TOOLS.register()
async def describe_problem(ctx: RunContext[AppDeps], evidence_dir: str, problem_id: str) -> str:
    """Look up a catalogued problem: summary, likely causes, verify steps, signatures.

    Use after ``targeted_view`` surfaces a ``problem:<id>`` link, to ground a
    hypothesis in the curated signature library rather than inventing one.
    """
    loaded = _load(ctx, evidence_dir)
    p = loaded.problems.get(problem_id)
    if p is None:
        known = ", ".join(sorted(loaded.problems.problems)) or "(none)"
        return f"Unknown problem {problem_id!r}. Catalogued: {known}."
    parts = [f"# {p.id}: {p.title}"]
    if p.summary:
        parts.append(p.summary.strip())
    if p.likely_causes:
        parts.append("Likely causes:\n" + "\n".join(f"  - {c}" for c in p.likely_causes))
    if p.verify_steps:
        parts.append("Verify steps:\n" + "\n".join(f"  - {s}" for s in p.verify_steps))
    if p.targets:
        parts.append("Signature targets: " + ", ".join(p.targets))
    return "\n\n".join(parts)
