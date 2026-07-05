"""Evidence-package (Bundle) layer — the structural container above single files.

A *bundle* is one dumped package off the board:

- ``CBBLOG0.TGZ .. CBBLOG11.TGZ`` (extracted → ``CBBLOG0 .. CBBLOG11`` folders):
  **boot** packages, a 12-deep ring, index 0 newest. Dumped in the final
  process's ``vBSP_init`` and clears reserved memory.
- ``CBBLOGDUMP0.TGZ .. CBBLOGDUMP2.TGZ``: **runtime** packages, dumped hourly,
  do *not* clear reserved memory.

This layer only *loads and routes*: given a folder or ``.tgz``, it walks the
member files, routes each filename to a ``LogFile`` class + filter via the
:class:`~aidbg.logs.config.LogConfigSet`, and parses it. It makes **no** boot /
stage / board-type judgement — one package may span several boots (a boot that
never reached the final process is dumped by the *next* boot), and splitting a
bundle into boots is a later, interpretation layer that sits above this one.

No textual import; stdlib + the logs layer only.
"""

from __future__ import annotations

import re
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from aidbg.logs.base import LogFile
from aidbg.logs.config import LogConfigSet


class BundleKind(Enum):
    """Which package family a bundle belongs to (closed set, not an ext point)."""

    BOOT = "boot"  # CBBLOG0..11 — clears reserved mem on dump
    RUNTIME = "runtime"  # CBBLOGDUMP0..2 — hourly, does not clear
    UNKNOWN = "unknown"


# CBBLOGDUMP must be tested before CBBLOG (the latter is a prefix of the former).
_NAME = re.compile(r"^(?P<prefix>CBBLOGDUMP|CBBLOG)(?P<index>\d+)$", re.IGNORECASE)


def parse_bundle_name(name: str) -> tuple[BundleKind, int]:
    """Classify a package/folder name → ``(kind, index)``.

    Strips a trailing ``.tgz`` / ``.tar.gz``. Unrecognised names →
    ``(UNKNOWN, -1)`` rather than raising, so discovery stays tolerant.
    """
    stem = name
    for suffix in (".tar.gz", ".tgz", ".tar"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    m = _NAME.match(stem)
    if m is None:
        return BundleKind.UNKNOWN, -1
    kind = BundleKind.RUNTIME if m.group("prefix").upper() == "CBBLOGDUMP" else BundleKind.BOOT
    return kind, int(m.group("index"))


@dataclass(frozen=True, slots=True)
class Bundle:
    """One loaded evidence package: parsed logs keyed by source + leftovers.

    ``logs`` maps a log ``source`` ("uboot"/"panic"/"cbblog") to its parsed
    :class:`LogFile`. ``unrouted`` lists member filenames no config claimed, kept
    visible rather than silently ignored.
    """

    path: str
    kind: BundleKind
    index: int
    logs: dict[str, LogFile] = field(default_factory=dict)
    unrouted: list[str] = field(default_factory=list)

    def get(self, source: str) -> LogFile | None:
        """Parsed log for a source, or ``None`` if this package lacks it.

        (A package may lack a source — retention windows differ per log.)
        """
        return self.logs.get(source)

    @classmethod
    def load(cls, path: str | Path, configs: LogConfigSet) -> "Bundle":
        """Load a bundle from an extracted folder or a ``.tgz`` archive."""
        p = Path(path)
        kind, index = parse_bundle_name(p.name)
        logs: dict[str, LogFile] = {}
        unrouted: list[str] = []
        for filename, text in _iter_members(p):
            route = configs.resolve(filename)
            if route is None:
                unrouted.append(filename)
                continue
            logs[route.log_cls.source] = route.log_cls.parse(
                filename, text, targets=route.target_set
            )
        return cls(path=str(p), kind=kind, index=index, logs=logs, unrouted=sorted(unrouted))


@dataclass(frozen=True, slots=True)
class Evidence:
    """A set of bundles discovered under one directory, ordered newest-first."""

    root: str
    bundles: list[Bundle] = field(default_factory=list)

    def boots(self) -> list[Bundle]:
        return [b for b in self.bundles if b.kind is BundleKind.BOOT]

    def runtime(self) -> list[Bundle]:
        return [b for b in self.bundles if b.kind is BundleKind.RUNTIME]


def load_evidence(root: str | Path, configs: LogConfigSet) -> Evidence:
    """Discover and load every bundle (folder or ``.tgz``) directly under ``root``.

    Ordered by kind then index ascending (index 0 = newest boot). Names that
    aren't recognised bundle packages are skipped.
    """
    r = Path(root)
    found: list[Bundle] = []
    if r.is_dir():
        for child in r.iterdir():
            kind, _ = parse_bundle_name(child.name)
            if kind is BundleKind.UNKNOWN:
                continue
            if child.is_dir() or _is_tarball(child.name):
                found.append(Bundle.load(child, configs))
    found.sort(key=lambda b: (b.kind.value, b.index))
    return Evidence(root=str(r), bundles=found)


# --- member iteration (folder or tarball) ------------------------------------


def _is_tarball(name: str) -> bool:
    n = name.lower()
    return n.endswith(".tgz") or n.endswith(".tar.gz") or n.endswith(".tar")


def _decode(data: bytes) -> str:
    """Decode member bytes tolerantly; board logs aren't guaranteed clean UTF-8."""
    return data.decode("utf-8", errors="replace")


def _iter_members(path: Path) -> Iterator[tuple[str, str]]:
    """Yield ``(basename, text)`` for each regular file in a folder or tarball."""
    if path.is_dir():
        for f in sorted(path.rglob("*")):
            if f.is_file():
                yield f.name, _decode(f.read_bytes())
    elif _is_tarball(path.name):
        with tarfile.open(path, "r:*") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                fh = tar.extractfile(member)
                if fh is None:
                    continue
                yield Path(member.name).name, _decode(fh.read())
