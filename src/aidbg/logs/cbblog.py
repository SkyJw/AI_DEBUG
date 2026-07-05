"""CBBLOG (BSP_DRV user-space) log modelling.

CBBLOG is the log of the BSP_DRV repo's user-space ``.so``: every process on the
board calls ``vBSP_init(process_id)`` and all of that library's logging lands
here, in one shared file. A line carries a timestamp, the custom process id,
linux pid/tid, a level, and the message text.

Only the timestamp is pinned down here (``[YYYY-MM-DD:HH:MM:SS]`` linux system
time — 1970 before the clock is set). The rest of the private field layout still
needs close analysis, so **field extraction is intentionally deferred**: for now
everything after the timestamp goes into ``message`` and the structured fields
stay ``None``. Growing this parser means filling in the marked section below —
the ``CbblogRecord`` shape (and its ``fields`` escape-hatch dict) does not change.
"""

from __future__ import annotations

import re
from datetime import datetime

from aidbg.logs.base import LogFile, register_log
from aidbg.logs.records import CbblogRecord, LogRecord, LogTimestamp

# Leading "[YYYY-MM-DD:HH:MM:SS]" linux system-time stamp.
_TS = re.compile(r"^\[(?P<d>\d{4}-\d{2}-\d{2}:\d{2}:\d{2}:\d{2})\]\s?(?P<rest>.*)$")
_FMT = "%Y-%m-%d:%H:%M:%S"


@register_log
class CbblogLog(LogFile):
    source = "cbblog"
    record_type = CbblogRecord

    @classmethod
    def parse_line(cls, line_no: int, raw: str) -> LogRecord:
        m = _TS.match(raw)
        if m is None:
            return CbblogRecord(line_no=line_no, raw=raw, timestamp=None, message=raw)
        digits = m.group("d")
        try:
            value: datetime | None = datetime.strptime(digits, _FMT)
        except ValueError:
            value = None
        ts = LogTimestamp(raw=f"[{digits}]", value=value)
        rest = m.group("rest")

        # --- deferred: parse process_id / pid / tid / level out of `rest` here.
        # Until the private layout is nailed down, keep the remainder as message
        # and leave the structured fields unset. Fill this in without touching
        # CbblogRecord's shape (use `fields` for anything not yet promoted).
        return CbblogRecord(line_no=line_no, raw=raw, timestamp=ts, message=rest)
