"""Log record types — the pure-modeling layer.

One physical log line becomes exactly one :class:`LogRecord`. This layer only
*structures* a line; it makes no judgement about what the line means (no boot
segmentation, no board-type / stage inference — those live above this layer).

Two invariants hold here:

- **Lossless w.r.t. input.** Every line handed to a log class becomes a record,
  even one whose format is unrecognised (then ``timestamp=None`` and
  ``message == raw``). Nothing is silently dropped. Selection is the filter
  layer's job (:mod:`aidbg.logs.target`), which runs *before* this layer.
- **Line order is the spine.** ``line_no`` is the original file line index and is
  the only reliable ordering key — timestamps jump (1970 → 1990 → real time as
  the board sets its clock), so they are never treated as a continuous clock.

Timestamps are normalised into one shape (:class:`LogTimestamp`) but each log
class extracts them its own way (see each ``parse_line``); ``raw`` always keeps
the original text so nothing is lost in translation.

No textual import; stdlib only. This module is import-safe from every layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogTimestamp:
    """A timestamp extracted from a line, in a shape common to all log types.

    Only the fields a given format can yield are populated:

    - ``raw`` — the original timestamp text, always kept verbatim.
    - ``value`` — a wall-clock ``datetime`` when the format carries one
      (panic / CBBLOG). May encode the boot-default 1970/1990 era; this layer
      does not interpret which era it is.
    - ``rel_ms`` — milliseconds since power-on for UBOOT's ``[100ms]`` form.

    A line with no recognisable timestamp carries ``timestamp=None`` on the
    record rather than an empty :class:`LogTimestamp`.
    """

    raw: str
    value: datetime | None = None
    rel_ms: int | None = None


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Base record: the fields every structured log line shares.

    Subclasses add source-specific fields (all defaulted, so they follow the
    base's required fields under dataclass ordering rules).
    """

    line_no: int  # original file line index (0-based); the ordering spine
    raw: str  # the original line, verbatim (newline stripped)
    timestamp: LogTimestamp | None  # None when no timestamp could be parsed
    message: str  # line text after the recognised prefix; == raw if unparsed


@dataclass(frozen=True, slots=True)
class UbootRecord(LogRecord):
    """A UBOOT (bootloader) line. Currently just timestamp + message."""


@dataclass(frozen=True, slots=True)
class PanicRecord(LogRecord):
    """A ``panic`` (kernel dmesg) line.

    Continuation lines of a multi-line block (call stacks, register dumps) are
    ordinary records with ``timestamp=None`` — grouping them into one logical
    event is interpretation and belongs above this layer.
    """

    level: str | None = None  # kernel level if one can be parsed, else None


@dataclass(frozen=True, slots=True)
class CbblogRecord(LogRecord):
    """A CBBLOG (BSP_DRV user-space) line.

    Only the fields we already understand are modelled. The private line format
    is not fully pinned down yet, so anything not yet modelled goes into
    ``fields`` — that dict is the extension point for the CBBLOG parser to grow
    without changing this structure.
    """

    process_id: int | None = None  # BSP custom process id (0/1/3/4/5/6 …)
    pid: int | None = None  # linux pid
    tid: int | None = None  # linux tid
    level: str | None = None  # error / warn / info …
    fields: dict[str, str] = field(default_factory=dict)  # not-yet-modelled fields
