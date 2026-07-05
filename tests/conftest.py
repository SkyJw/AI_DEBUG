"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ layout is importable even without an editable install.
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _register_agents_and_tools():
    """Populate the registries (import side effects) for every test."""
    import aidbg.agents  # noqa: F401
    import aidbg.tools  # noqa: F401
