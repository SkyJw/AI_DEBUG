"""Native tool extension slot.

Each module registers a tool via ``@TOOLS.register()`` at import time. Import
new tool modules here so their registration runs. Explicit and greppable.
"""

from aidbg.tools import (  # noqa: F401  (import side effect: registration)
    echo,
    findings_tools,
    log_tools,
    read_file,
)

__all__ = ["echo", "findings_tools", "log_tools", "read_file"]
