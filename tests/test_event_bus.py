"""EventBus fan-out semantics."""

from __future__ import annotations

from aidbg.core.events import EventBus, RunFinished, TokenDelta


async def test_publish_reaches_all_subscribers():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    ev = TokenDelta(agent="a", message_id="m1", text="hi")
    await bus.publish(ev)

    assert q1.get_nowait() is ev
    assert q2.get_nowait() is ev


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)
    await bus.publish(RunFinished(agent="a"))
    assert q.empty()


async def test_late_subscriber_misses_earlier_events():
    bus = EventBus()
    await bus.publish(TokenDelta(agent="a", message_id="m", text="early"))
    q = bus.subscribe()
    assert q.empty()
    ev = TokenDelta(agent="a", message_id="m", text="late")
    await bus.publish(ev)
    assert q.get_nowait() is ev
