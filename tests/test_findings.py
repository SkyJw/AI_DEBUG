"""FindingsBoard + findings tools — the data channel between sub-agents.

The board is exercised directly (unit) and through its tools with a RunContext
carrying a named Agent, so the agent-tagging path is real. No backend.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aidbg.config.settings import load_settings
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.findings import FindingsBoard
from aidbg.tools.findings_tools import list_findings, record_finding


def _ctx(workspace: Path, agent_name: str | None = None) -> RunContext[AppDeps]:
    deps = AppDeps(bus=EventBus(), workspace=workspace, settings=load_settings())
    agent = Agent(TestModel(), name=agent_name) if agent_name else None
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage(), agent=agent)


# --- board unit -------------------------------------------------------------


def test_board_assigns_sequential_ids():
    board = FindingsBoard()
    f1 = board.add(agent="log-analyst", summary="a")
    f2 = board.add(agent="log-analyst", summary="b")
    assert (f1.id, f2.id) == ("F1", "F2")
    assert len(board) == 2


def test_board_get_is_case_insensitive():
    board = FindingsBoard()
    board.add(agent="log-analyst", summary="a")
    assert board.get("f1") is not None
    assert board.get("F1").summary == "a"
    assert board.get("F9") is None


def test_board_preserves_coordinate_problem_refs():
    board = FindingsBoard()
    f = board.add(
        agent="log-analyst",
        summary="SGC stall",
        coordinate="boot1/cbblog:212",
        problem="sgc-stall",
        refs=("F0",),
    )
    assert f.coordinate == "boot1/cbblog:212"
    assert f.problem == "sgc-stall"
    assert f.refs == ("F0",)


def test_replace_detail_rebinds_without_new_id():
    board = FindingsBoard()
    board.add(agent="log-analyst", summary="a")
    updated = board.replace_detail("F1", "the raw log line")
    assert updated is not None and updated.id == "F1"
    assert board.get("F1").detail == "the raw log line"
    assert len(board) == 1  # no new finding minted
    assert board.replace_detail("F9", "x") is None


# --- tools ------------------------------------------------------------------


async def test_record_finding_returns_id_and_tags_agent(tmp_path: Path):
    ctx = _ctx(tmp_path, agent_name="log-analyst")
    out = await record_finding(
        ctx,
        summary="repeated boot attempts",
        coordinate="boot1/cbblog:212",
        problem="sgc-stall",
        detail="vBSP_init begin with no end",
        refs="F0, F1",
    )
    assert "F1" in out
    board = ctx.deps.findings
    f = board.get("F1")
    assert f.agent == "log-analyst"  # tagged from ctx.agent.name
    assert f.coordinate == "boot1/cbblog:212"
    assert f.problem == "sgc-stall"
    assert f.refs == ("F0", "F1")  # parsed + upper-cased from comma string


async def test_record_finding_defaults_agent_when_unnamed(tmp_path: Path):
    ctx = _ctx(tmp_path)  # no agent on the context
    await record_finding(ctx, summary="x")
    assert ctx.deps.findings.get("F1").agent == "agent"


async def test_list_findings_empty_and_populated(tmp_path: Path):
    ctx = _ctx(tmp_path, agent_name="log-analyst")
    assert "empty" in (await list_findings(ctx)).lower()
    await record_finding(ctx, summary="SGC stall", coordinate="boot1/cbblog:212", problem="sgc-stall")
    out = await list_findings(ctx)
    assert "F1" in out
    assert "boot1/cbblog:212" in out
    assert "sgc-stall" in out
    assert "log-analyst" in out


async def test_list_findings_shows_detail_and_refs(tmp_path: Path):
    ctx = _ctx(tmp_path, agent_name="log-analyst")
    await record_finding(ctx, summary="first")
    await record_finding(ctx, summary="second", detail="context here", refs="F1")
    out = await list_findings(ctx)
    assert "←F1" in out  # ref rendered
    assert "context here" in out  # detail appended
