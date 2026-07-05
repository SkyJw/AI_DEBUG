"""Log-analyst tools (typed queries over logs/) + delegation reachability.

Tools are exercised standalone against a workspace holding the shipped configs +
generated fake evidence — no real backend. Delegation is checked with a
TestModel that calls the delegate tool.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aidbg.config.mcp import McpConfig
from aidbg.config.settings import load_settings
from aidbg.core import events as ev
from aidbg.core.agent_factory import build_orchestrator
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.streaming import pump_agent_run
from aidbg.tools.log_tools import (
    _CACHE,
    describe_problem,
    list_evidence,
    read_log,
    targeted_view,
)

REPO = Path(__file__).parent.parent
GEN = REPO / "scripts" / "gen_fake_logs.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_fake_logs", GEN)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_fake_logs"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace with shipped configs + freshly generated fake evidence."""
    shutil.copytree(REPO / "configs", tmp_path / "configs")
    ev_dir = tmp_path / "samples" / "fake_evidence"
    ev_dir.mkdir(parents=True)
    _load_generator().generate(ev_dir)
    _CACHE.clear()  # isolate cache between tests
    return tmp_path


def _ctx(workspace: Path) -> RunContext[AppDeps]:
    deps = AppDeps(bus=EventBus(), workspace=workspace, settings=load_settings())
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


async def test_list_evidence_shows_bundles(workspace: Path):
    out = await list_evidence(_ctx(workspace), "samples/fake_evidence")
    assert "boot0" in out and "runtime0" in out
    assert "cbblog=" in out  # per-source line counts shown


async def test_targeted_view_annotates_with_meaning_and_problem(workspace: Path):
    # The multi-boot bundle's stall line should surface with its problem link.
    out = await targeted_view(_ctx(workspace), "samples/fake_evidence", "boot1", "cbblog")
    assert "boot1/cbblog:" in out  # stable coordinate present
    assert "no progress" in out or "stalled" in out
    assert "problem:sgc-stall" in out


async def test_targeted_view_bios_recovery(workspace: Path):
    out = await targeted_view(_ctx(workspace), "samples/fake_evidence", "boot2", "cbblog")
    assert "problem:reset-storm" in out


async def test_read_log_slice_and_coordinates(workspace: Path):
    out = await read_log(_ctx(workspace), "samples/fake_evidence", "boot0", "panic", start=0, count=3)
    assert "boot0/panic:0" in out
    # original line order preserved; only 3 shown
    assert out.count("boot0/panic:") == 3


async def test_read_log_process_id_filter_is_forward_looking(workspace: Path):
    # CBBLOG field extraction is deferred (process_id always None for now), so the
    # typed process_id filter correctly matches nothing yet. This guards that the
    # filter behaves honestly until the CBBLOG parser is filled in with real fields.
    out = await read_log(_ctx(workspace), "samples/fake_evidence", "boot2", "cbblog", process_id=5)
    assert "No matching lines" in out
    # ...but the nebios line IS present in the raw stream (found without the filter).
    unfiltered = await read_log(_ctx(workspace), "samples/fake_evidence", "boot2", "cbblog")
    assert "nebios" in unfiltered


async def test_describe_problem_returns_catalogue_entry(workspace: Path):
    out = await describe_problem(_ctx(workspace), "samples/fake_evidence", "sgc-stall")
    assert "SGC" in out
    assert "Likely causes" in out and "Verify steps" in out


async def test_unknown_bundle_is_helpful(workspace: Path):
    out = await targeted_view(_ctx(workspace), "samples/fake_evidence", "boot99", "cbblog")
    assert "unknown bundle" in out.lower() or "known:" in out.lower()


async def test_path_traversal_blocked(workspace: Path):
    with pytest.raises(ValueError):
        await list_evidence(_ctx(workspace), "../../etc")


async def test_delegation_to_log_analyst(tmp_path: Path):
    """The log-analyst is reachable as a delegate tool from the orchestrator."""
    settings = load_settings()
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=tmp_path, settings=settings)

    agent = build_orchestrator(
        settings=settings,
        mcp_config=McpConfig(),
        workspace=tmp_path,
        model_override=TestModel(call_tools=[]),
    )
    with agent.override(model=TestModel(call_tools=["delegate_to_log_analyst"])):
        result = await pump_agent_run(
            agent, "triage samples/fake_evidence", deps=deps, bus=bus, agent_name="orchestrator"
        )

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    deleg = next(e for e in events if isinstance(e, ev.DelegationStarted))
    assert deleg.parent == "orchestrator" and deleg.child == "log-analyst"
    assert any(
        isinstance(e, ev.MessageStarted) and e.agent == "log-analyst" for e in events
    ), "expected a log-analyst MessageStarted event"
    assert result.output is not None
