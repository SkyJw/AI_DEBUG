"""UBOOT (bootloader) log modelling.

Covers the bootloader phase (UEFI → OS load/jump). Timestamps are relative
milliseconds since power-on, printed as a leading ``[100ms]``. A line without
that prefix (or with an unrecognised shape) still becomes a record — its
``timestamp`` is ``None`` and ``message`` is the full raw line.

The same class parses both the ``UBOOT`` and ``hiboot_bootinfo`` file variants;
that filename routing is declared in config, not here.
"""

from __future__ import annotations

import re

from aidbg.logs.base import LogFile, register_log
from aidbg.logs.records import LogRecord, LogTimestamp, UbootRecord

# Leading "[<digits>ms]" — relative milliseconds since power-on.
_TS = re.compile(r"^\[(?P<ms>\d+)ms\]\s?(?P<rest>.*)$")


@register_log
class UbootLog(LogFile):
    source = "uboot"
    record_type = UbootRecord

    @classmethod
    def parse_line(cls, line_no: int, raw: str) -> LogRecord:
        m = _TS.match(raw)
        if m is None:
            return UbootRecord(line_no=line_no, raw=raw, timestamp=None, message=raw)
        ms = int(m.group("ms"))
        ts = LogTimestamp(raw=f"[{ms}ms]", rel_ms=ms)
        return UbootRecord(line_no=line_no, raw=raw, timestamp=ts, message=m.group("rest"))
