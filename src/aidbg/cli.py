"""CLI entry point: parse args, load settings, register agents/tools, launch TUI."""

from __future__ import annotations

import argparse
from pathlib import Path

from aidbg import __version__


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="aidbg", description="Textual multi-agent TUI CLI.")
    parser.add_argument("--version", action="version", version=f"aidbg {__version__}")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root for filesystem-scoped tools (default: cwd).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load saved history (from AIDBG_HISTORY_PATH) at startup.",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="Print registered agents and exit (no TUI).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Import for registration side effects (populates AGENTS / TOOLS registries).
    import aidbg.agents  # noqa: F401
    import aidbg.tools  # noqa: F401
    from aidbg.config.settings import load_settings
    from aidbg.core.registry import AGENTS

    args = _parse_args(argv)

    if args.list_agents:
        for name, spec in sorted(AGENTS.all().items()):
            delegates = ", ".join(spec.delegates_to) or "-"
            print(f"{name:14} profile={spec.profile:12} delegates_to={delegates}")
        return 0

    settings = load_settings()

    # Deferred so --list-agents/--version don't require textual.
    from aidbg.session.session import ChatSession
    from aidbg.ui.app import AidbgApp

    session = ChatSession(settings=settings, workspace=args.workspace)
    if args.resume:
        session.load()

    app = AidbgApp(session, agent_names=AGENTS.names())
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
