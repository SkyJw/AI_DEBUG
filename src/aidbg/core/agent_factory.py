"""Build pydantic-ai agents from :class:`AgentSpec`s, incl. sub-agent delegation.

``build_agent`` wires one agent's model, instructions, native tools, and MCP
toolsets. ``build_orchestrator`` additionally attaches a ``delegate_to_<child>``
tool per sub-agent. Each delegate adapter runs the child through the SAME
:func:`~aidbg.core.streaming.pump_agent_run`, forwarding ``ctx.usage`` so token
accounting aggregates across agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext

from aidbg.config.mcp import McpConfig
from aidbg.config.settings import Settings
from aidbg.core.deps import AppDeps
from aidbg.core.events import DelegationFinished, DelegationStarted
from aidbg.core.mcp import build_toolsets
from aidbg.core.models import build_model
from aidbg.core.registry import AGENTS, TOOLS, AgentRegistry, AgentSpec, ToolRegistry
from aidbg.core.streaming import pump_agent_run


def _load_instructions(path: str, workspace: Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = workspace / p
    if p.is_file():
        return p.read_text(encoding="utf-8")
    # Missing prompt file is non-fatal; agent still works with a generic identity.
    return f"You are the {path} agent."


def build_agent(
    spec: AgentSpec,
    *,
    settings: Settings,
    mcp_config: McpConfig,
    workspace: Path,
    tools: ToolRegistry = TOOLS,
    model_override: Any = None,
) -> Agent[AppDeps, str]:
    """Build a single (non-delegating) agent from its spec.

    ``model_override`` (any pydantic-ai ``Model``, e.g. ``TestModel``) replaces
    the profile-derived model — the injection seam used by tests and a future
    ``--model`` flag so no real backend is contacted.
    """
    model = model_override if model_override is not None else build_model(
        settings.profile_for(spec.profile)
    )
    instructions = _load_instructions(spec.instructions_path, workspace)
    toolsets = build_toolsets(mcp_config, spec.mcp_names)

    agent: Agent[AppDeps, str] = Agent(
        model,
        deps_type=AppDeps,
        instructions=instructions,
        name=spec.name,
        toolsets=toolsets,
    )

    for fn in tools.resolve(spec.tool_names):
        agent.tool(fn)

    return agent


def _make_delegate_tool(parent_name: str, child_agent: Agent[AppDeps, str], child_spec: AgentSpec):
    """Create a ``delegate_to_<child>`` tool that runs the child sub-agent.

    The child streams through the shared pump tagged with its own name, so its
    tokens/tool-calls render nested in the UI. ``ctx.usage`` is forwarded so the
    child's token usage aggregates into the parent run.
    """

    async def delegate(ctx: RunContext[AppDeps], task: str) -> str:
        bus = ctx.deps.bus
        await bus.publish(
            DelegationStarted(parent=parent_name, child=child_spec.name, task=task[:200])
        )
        result = await pump_agent_run(
            child_agent,
            task,
            deps=ctx.deps,
            bus=bus,
            agent_name=child_spec.name,
            usage=ctx.usage,  # CRITICAL: aggregate child usage into parent
        )
        output = str(result.output)
        await bus.publish(
            DelegationFinished(
                parent=parent_name,
                child=child_spec.name,
                output_preview=output[:200],
                full_output=output,
            )
        )
        return output

    delegate.__doc__ = child_spec.description
    delegate.__name__ = f"delegate_to_{child_spec.name.replace('-', '_')}"
    return delegate


def build_orchestrator(
    *,
    settings: Settings,
    mcp_config: McpConfig,
    workspace: Path,
    registry: AgentRegistry = AGENTS,
    tools: ToolRegistry = TOOLS,
    orchestrator_name: str = "orchestrator",
    model_override: Any = None,
) -> Agent[AppDeps, str]:
    """Build the orchestrator with a delegate tool per declared sub-agent."""
    spec = registry.get(orchestrator_name)
    orchestrator = build_agent(
        spec,
        settings=settings,
        mcp_config=mcp_config,
        workspace=workspace,
        tools=tools,
        model_override=model_override,
    )

    for child_name in spec.delegates_to:
        child_spec = registry.get(child_name)
        child_agent = build_agent(
            child_spec,
            settings=settings,
            mcp_config=mcp_config,
            workspace=workspace,
            tools=tools,
            model_override=model_override,
        )
        delegate = _make_delegate_tool(spec.name, child_agent, child_spec)
        orchestrator.tool(delegate)

    return orchestrator


def build_all(
    *,
    settings: Settings,
    mcp_config: McpConfig,
    workspace: Path,
    registry: AgentRegistry = AGENTS,
    tools: ToolRegistry = TOOLS,
) -> dict[str, Agent[AppDeps, Any]]:
    """Build every registered agent (used for listing / smoke checks)."""
    return {
        name: build_agent(
            spec, settings=settings, mcp_config=mcp_config, workspace=workspace, tools=tools
        )
        for name, spec in registry.all().items()
    }
