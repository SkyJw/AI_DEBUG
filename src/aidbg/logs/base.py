"""``LogFile`` — the per-log-type modelling class, plus its registry.

One subclass per kind of log (UBOOT / panic / CBBLOG). A subclass owns exactly
one piece of knowledge: **how to structure a single line** of that log into a
:class:`~aidbg.logs.records.LogRecord` (its ``parse_line``). It does *not* know
which filenames it applies to — that routing lives in config (see
:mod:`aidbg.logs.config`), keeping the class simple and reusable.

Adding a new log type = write a ``XxxRecord`` + ``XxxLog(LogFile)`` +
``@register_log`` + a YAML config. Nothing else changes — same greppable
extension style as the ``AGENTS`` / ``TOOLS`` registries.

Parsing is **lossless w.r.t. input**: every line the class receives yields a
record (``parse_line`` never returns ``None``). The optional
:class:`~aidbg.logs.target.TargetSet` runs first and may drop lines, but it
preserves original line numbers so records stay traceable.

No textual import; stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from aidbg.logs.records import LogRecord
from aidbg.logs.target import TargetSet


class LogFile(ABC):
    """Base class for a parsed log file: a flat, line-ordered list of records.

    Subclasses set ``source`` / ``record_type`` and implement :meth:`parse_line`.
    The list is never boot-segmented here — that is a higher layer's concern.
    """

    source: ClassVar[str]  # "uboot" | "panic" | "cbblog"
    record_type: ClassVar[type[LogRecord]]

    def __init__(self, path: str, records: list[LogRecord]) -> None:
        self.path = path
        self.records = records  # flat, in original line order

    @classmethod
    @abstractmethod
    def parse_line(cls, line_no: int, raw: str) -> LogRecord:
        """Structure one line into a record.

        Must never return ``None``: an unrecognised line becomes a record with
        ``timestamp=None`` and ``message == raw`` so nothing is dropped.
        ``line_no`` is the original file line index (survives filtering).
        """

    @classmethod
    def parse(cls, path: str, text: str, targets: TargetSet | None = None) -> "LogFile":
        """Parse file text into a ``LogFile``.

        ``targets`` (if given) selects which lines reach :meth:`parse_line`;
        the original line numbers are preserved either way.
        """
        lines = text.splitlines()
        if targets is not None:
            pairs = targets.select(lines)
        else:
            pairs = enumerate(lines)
        records = [cls.parse_line(line_no, raw) for line_no, raw in pairs]
        return cls(path, records)

    def __len__(self) -> int:
        return len(self.records)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} source={self.source!r} records={len(self.records)}>"


# --- registry (mirrors AGENTS / TOOLS) ---------------------------------------

LOG_TYPES: dict[str, type[LogFile]] = {}


def register_log(cls: type[LogFile]) -> type[LogFile]:
    """Class decorator: register a ``LogFile`` subclass under its ``source``."""
    if cls.source in LOG_TYPES:
        raise ValueError(f"log type {cls.source!r} already registered")
    LOG_TYPES[cls.source] = cls
    return cls


def log_type(source: str) -> type[LogFile]:
    """Resolve a registered ``LogFile`` class by ``source`` name."""
    try:
        return LOG_TYPES[source]
    except KeyError:
        raise KeyError(
            f"unknown log type {source!r}; registered: {sorted(LOG_TYPES)}"
        ) from None
