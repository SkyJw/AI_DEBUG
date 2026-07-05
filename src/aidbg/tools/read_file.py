"""Native tool: read_file — read a UTF-8 file under the workspace root.

Path traversal is blocked: the resolved path must stay within the workspace.
"""

from __future__ import annotations

from pydantic_ai import RunContext

from aidbg.core.deps import AppDeps
from aidbg.core.registry import TOOLS


@TOOLS.register()
async def read_file(ctx: RunContext[AppDeps], path: str, max_bytes: int = 65536) -> str:
    """Read a text file (UTF-8) located under the workspace directory."""
    workspace = ctx.deps.workspace.resolve()
    target = (workspace / path).resolve()
    if target != workspace and workspace not in target.parents:
        raise ValueError(f"path {path!r} escapes the workspace")
    if not target.is_file():
        raise FileNotFoundError(f"no such file: {path!r}")
    data = target.read_text(encoding="utf-8", errors="replace")
    return data[:max_bytes]
