"""``panic`` (kernel dmesg) log modelling.

Despite the filename this is the kernel dmesg stream (kernel init + SoC ``.ko``
logs), not a kernel-panic record. Timestamps are a leading ``[YYYYMMDDHHMMSS]``
14-digit wall clock — the kernel boots at 1970, is bumped to 1990 mid-boot, then
set to real time once a user-space process configures the clock. This layer only
turns the digits into a ``datetime`` and keeps the raw text; it does not decide
which era a value belongs to.

Continuation lines of a multi-line block (call stacks, register dumps) have no
timestamp of their own → ``timestamp=None`` and ``message == raw``. Grouping
them into one logical event is interpretation and lives above this layer.
"""

from __future__ import annotations

import re
from datetime import datetime

from aidbg.logs.base import LogFile, register_log
from aidbg.logs.records import LogRecord, LogTimestamp, PanicRecord

# Leading "[<14 digits>]" wall-clock stamp, YYYYMMDDHHMMSS.
_TS = re.compile(r"^\[(?P<d>\d{14})\]\s?(?P<rest>.*)$")
_FMT = "%Y%m%d%H%M%S"


@register_log
class PanicLog(LogFile):
    source = "panic"
    record_type = PanicRecord

    @classmethod
    def parse_line(cls, line_no: int, raw: str) -> LogRecord:
        m = _TS.match(raw)
        if m is None:
            return PanicRecord(line_no=line_no, raw=raw, timestamp=None, message=raw)
        digits = m.group("d")
        try:
            value: datetime | None = datetime.strptime(digits, _FMT)
        except ValueError:
            # Well-formed 14 digits but not a valid date — keep raw, drop value.
            value = None
        ts = LogTimestamp(raw=f"[{digits}]", value=value)
        return PanicRecord(line_no=line_no, raw=raw, timestamp=ts, message=m.group("rest"))
