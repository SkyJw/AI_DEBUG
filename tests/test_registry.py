"""Registry behavior: registration, duplicate rejection, resolution."""

from __future__ import annotations

import pytest

from aidbg.core.registry import AgentRegistry, AgentSpec, ToolRegistry


def test_tool_register_and_resolve():
    reg = ToolRegistry()

    @reg.register()
    async def my_tool():  # pragma: no cover - body irrelevant
        return "x"

    assert reg.names() == ["my_tool"]
    assert reg.get("my_tool") is my_tool
    assert reg.resolve(("my_tool",)) == [my_tool]


def test_tool_custom_name():
    reg = ToolRegistry()

    @reg.register("aliased")
    async def fn():  # pragma: no cover
        return None

    assert reg.get("aliased") is fn


def test_tool_duplicate_rejected():
    reg = ToolRegistry()

    @reg.register()
    async def dup():  # pragma: no cover
        return None

    with pytest.raises(ValueError, match="already registered"):

        @reg.register("dup")
        async def other():  # pragma: no cover
            return None


def test_tool_unknown_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError, match="unknown tool"):
        reg.get("nope")


def test_agent_register_and_get():
    reg = AgentRegistry()
    spec = AgentSpec(
        name="a", description="d", profile="a", instructions_path="p.md"
    )
    reg.register(spec)
    assert reg.get("a") is spec
    assert reg.names() == ["a"]


def test_agent_duplicate_rejected():
    reg = AgentRegistry()
    spec = AgentSpec(name="a", description="d", profile="a", instructions_path="p.md")
    reg.register(spec)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(spec)


def test_builtin_agents_registered():
    import aidbg.agents  # noqa: F401  (import side effect: registration)
    from aidbg.core.registry import AGENTS

    names = AGENTS.names()
    assert {
        "orchestrator",
        "coder",
        "researcher",
        "code-reviewer",
        "log-analyst",
        "code-research",
    } <= set(names)
    assert AGENTS.get("orchestrator").delegates_to == (
        "coder",
        "researcher",
        "code-reviewer",
        "log-analyst",
        "code-research",
    )


def test_code_research_scaffold_spec():
    """Code-research is wired as a scaffold: reads the board, no MCP backends yet."""
    import aidbg.agents  # noqa: F401
    from aidbg.core.registry import AGENTS

    spec = AGENTS.get("code-research")
    assert spec.profile == "code_research"
    assert spec.tool_names == ("list_findings",)  # reads the board, files nothing
    assert spec.mcp_names == ()  # MCP services not deployed yet
