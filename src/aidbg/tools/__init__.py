"""Native tool extension slot.

Each module registers a tool via ``@TOOLS.register()`` at import time. Import
new tool modules here so their registration runs. Explicit and greppable.
"""

from aidbg.tools import echo, log_tools, read_file  # noqa: F401  (import side effect: registration)

__all__ = ["echo", "log_tools", "read_file"]
