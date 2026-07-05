"""ChatController — bridges the async session run into the Textual UI.

Choreography (from the plan): an exclusive ``llm`` worker runs the session turn
while a second ``ui`` worker drains the event bus and re-posts each event as a
``UiEventArrived`` message onto the UI thread. A sentinel (``None``) put on the
queue in ``finally`` cleanly ends the drain even if the run errors or cancels.

Workers are launched via ``app.run_worker`` (not the ``@work`` decorator) because
this controller is a plain helper, not a ``DOMNode`` — the App owns the workers.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aidbg.ui.messages import UiEventArrived

if TYPE_CHECKING:
    from aidbg.session.session import ChatSession
    from aidbg.ui.app import AidbgApp


class ChatController:
    """Owns the run/drain worker choreography for one app + session."""

    def __init__(self, app: AidbgApp, session: ChatSession) -> None:
        self.app = app
        self.session = session

    def run_turn(self, prompt: str) -> None:
        """Launch the exclusive LLM worker for one user turn."""
        self.app.run_worker(
            self._run_turn(prompt),
            group="llm",
            exclusive=True,
        )

    async def _run_turn(self, prompt: str) -> None:
        q: asyncio.Queue = self.session.bus.subscribe()
        drain = self.app.run_worker(self._drain(q), group="ui", exclusive=False)
        try:
            await self.session.run(prompt)
        except asyncio.CancelledError:
            raise  # user cancelled mid-stream; partial message stays on screen
        except Exception:
            # pump_agent_run already published a RunError; swallow so the worker
            # ends gracefully and input re-enables via on_turn_complete.
            pass
        finally:
            await q.put(None)  # sentinel: stop the drain
            await drain.wait()
            self.session.bus.unsubscribe(q)
            self.app.on_turn_complete()

    async def _drain(self, q: asyncio.Queue) -> None:
        while (event := await q.get()) is not None:
            self.app.post_message(UiEventArrived(event))
