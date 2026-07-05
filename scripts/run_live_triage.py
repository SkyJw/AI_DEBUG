#!/usr/bin/env python3
"""One-shot LIVE triage against the real backend (no TUI).

Builds the real orchestrator, subscribes a printer to the event bus, and asks it
to triage samples/fake_evidence — exercising the full delegate → log-analyst →
log tools → report chain against a live LLM.

Run:  uv run python scripts/run_live_triage.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aidbg.agents  # noqa: F401  (import side effect: registers AGENTS)
import aidbg.tools  # noqa: F401  (import side effect: registers TOOLS)
from aidbg.config.mcp import load_mcp_config
from aidbg.config.settings import load_settings
from aidbg.core import events as ev
from aidbg.core.agent_factory import build_orchestrator
from aidbg.core.deps import AppDeps
from aidbg.core.events import EventBus
from aidbg.core.streaming import pump_agent_run

PROMPT = (
    "Triage the board logs in samples/fake_evidence. Which bundles show a failed "
    "or abnormal boot, and what is the most likely root cause? Delegate to the "
    "log-analyst."
)


async def _printer(q: asyncio.Queue) -> None:
    """Drain the event bus and print a readable trace of the run."""
    while True:
        e = await q.get()
        if isinstance(e, ev.DelegationStarted):
            print(f"\n[DELEGATE → {e.child}] {e.task[:80]}")
        elif isinstance(e, ev.DelegationFinished):
            print(f"[DELEGATE ✓ {e.child}]")
        elif isinstance(e, ev.ToolCallStarted):
            print(f"  · {e.agent} calls {e.tool_name}({e.args_preview[:80]})")
        elif isinstance(e, ev.ToolCallFinished):
            print(f"  · {e.tool_name} → {e.result_preview[:80]!r}")
        elif isinstance(e, ev.RunError):
            print(f"[ERROR] {e.agent}: {e.message}")
        elif isinstance(e, ev.RunFinished) and e.agent == "orchestrator":
            print(f"\n[RUN FINISHED] {e.usage_summary}")


async def main() -> None:
    settings = load_settings()
    workspace = Path.cwd()
    bus = EventBus()
    q = bus.subscribe()
    deps = AppDeps(bus=bus, workspace=workspace, settings=settings)

    agent = build_orchestrator(
        settings=settings,
        mcp_config=load_mcp_config(settings.mcp_config),
        workspace=workspace,
    )

    printer = asyncio.create_task(_printer(q))
    result = await pump_agent_run(agent, PROMPT, deps=deps, bus=bus, agent_name="orchestrator")
    await asyncio.sleep(0.1)  # let the printer flush trailing events
    printer.cancel()

    print("\n" + "=" * 70)
    print("ORCHESTRATOR FINAL REPORT")
    print("=" * 70)
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
