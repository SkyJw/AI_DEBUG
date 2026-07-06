"""Two registries + the agent spec, the extension backbone of the framework.

``TOOLS`` — decorator registry of native tool functions.
``AGENTS`` — registry of :class:`AgentSpec` declarations.

Extension is explicit and greppable: a new tool/agent module registers itself at
import time, and ``tools/__init__.py`` / ``agents/__init__.py`` import the module
so the registration runs. No entry-point / plugin-loader magic.

No textual import; imports pydantic-ai only for the tool callable type.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# A native tool is any async callable pydantic-ai can register; kept as Any to
# avoid over-constraining signatures (they take RunContext[AppDeps] + kwargs).
ToolFunc = Callable[..., Any]


class ToolRegistry:
    """Name -> tool function. Populated via ``@TOOLS.register()``."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolFunc] = {}

    def register(self, name: str | None = None) -> Callable[[ToolFunc], ToolFunc]:
        def deco(fn: ToolFunc) -> ToolFunc:
            key = name or fn.__name__
            if key in self._tools:
                raise ValueError(f"tool {key!r} already registered")
            self._tools[key] = fn
            return fn

        return deco

    def get(self, name: str) -> ToolFunc:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"unknown tool {name!r}; registered: {sorted(self._tools)}") from None

    def resolve(self, names: tuple[str, ...]) -> list[ToolFunc]:
        return [self.get(n) for n in names]

    def names(self) -> list[str]:
        return sorted(self._tools)


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Declarative description of an agent.

    ``profile`` maps to a settings profile-name key (``profile_<key>``). One
    file in ``agents/`` should register exactly one of these.
    """

    name: str
    description: str
    profile: str  # e.g. "orchestrator" | "analyst" | "code_research"
    instructions_path: str
    tool_names: tuple[str, ...] = ()
    mcp_names: tuple[str, ...] = ()
    # Names of other registered agents this agent may delegate to.
    delegates_to: tuple[str, ...] = ()


class AgentRegistry:
    """Name -> AgentSpec. Populated via ``AGENTS.register(AgentSpec(...))``."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> AgentSpec:
        if spec.name in self._agents:
            raise ValueError(f"agent {spec.name!r} already registered")
        self._agents[spec.name] = spec
        return spec

    def get(self, name: str) -> AgentSpec:
        try:
            return self._agents[name]
        except KeyError:
            raise KeyError(
                f"unknown agent {name!r}; registered: {sorted(self._agents)}"
            ) from None

    def all(self) -> dict[str, AgentSpec]:
        return dict(self._agents)

    def names(self) -> list[str]:
        return sorted(self._agents)


# Module-level singletons — the registries the whole app shares.
TOOLS = ToolRegistry()
AGENTS = AgentRegistry()
