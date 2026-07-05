"""Native tool: echo — trivial round-trip to prove the tool wire works."""

from __future__ import annotations

from pydantic_ai import RunContext

from aidbg.core.deps import AppDeps
from aidbg.core.registry import TOOLS


@TOOLS.register()
async def echo(ctx: RunContext[AppDeps], text: str) -> str:
    """Echo the given text back verbatim (diagnostic tool)."""
    return text
