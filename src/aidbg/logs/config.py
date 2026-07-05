"""YAML-driven config for the log layer: filename routing + per-type targets.

One YAML file per log type declares three things:

- ``type`` — binds to a registered ``LogFile`` class (``LOG_TYPES[type]``).
- ``filenames`` — which file basenames route to that class (this is where the
  UBOOT / hiboot_bootinfo aliasing lives — *not* in the class).
- ``target`` — the optional catalogue of target log patterns (see
  :mod:`aidbg.logs.target`).

Example (``configs/logs/uboot.yaml``)::

    type: uboot
    filenames: [UBOOT, hiboot_bootinfo]
    target:
      enabled: false            # ship off → lossless by default
      entries:
        - id: uboot-kernel-handoff
          meaning: bootloader handed off to the kernel
          match: substring
          pattern: "Starting kernel"
          problem: null          # optional link to a problems.yaml entry

A :class:`LogConfigSet` loads a directory of these, resolves a filename to its
``(LogFile class, TargetSet)`` route, and honours a global master switch that
forces every set off to recover the fully raw stream.

No textual import; stdlib + PyYAML only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from aidbg.logs.base import LogFile, log_type
from aidbg.logs.target import Target, TargetSet


@dataclass(frozen=True, slots=True)
class LogRoute:
    """Resolved routing target for a filename: which class + which target set."""

    log_cls: type[LogFile]
    target_set: TargetSet


@dataclass(slots=True)
class LogTypeConfig:
    """One log type's parsed YAML config."""

    type: str
    filenames: tuple[str, ...]
    target_set: TargetSet

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, origin: str) -> "LogTypeConfig":
        type_name = data.get("type")
        if not type_name:
            raise ValueError(f"{origin}: missing required 'type'")
        filenames = tuple(data.get("filenames", ()) or ())
        target_set = _targets_from_dict(data.get("target") or {}, origin=origin)
        return cls(type=type_name, filenames=filenames, target_set=target_set)


def _targets_from_dict(data: dict[str, Any], *, origin: str) -> TargetSet:
    targets = []
    for i, raw in enumerate(data.get("entries", []) or []):
        if not isinstance(raw, dict):
            raise ValueError(f"{origin}: target.entries[{i}] must be a mapping")
        targets.append(
            Target(
                id=raw.get("id", f"{Path(origin).stem}-{i}"),
                meaning=raw.get("meaning", ""),
                pattern=raw["pattern"],
                match=raw.get("match", "regex"),
                problem=raw.get("problem"),
                enabled=raw.get("enabled", True),
            )
        )
    return TargetSet(targets=tuple(targets), enabled=bool(data.get("enabled", False)))


@dataclass(slots=True)
class LogConfigSet:
    """All log-type configs, with filename→route resolution.

    ``targets_enabled`` is the global master switch: when ``False`` every route's
    target set is neutralised (all lines pass, no annotation) regardless of
    per-type settings.
    """

    configs: dict[str, LogTypeConfig] = field(default_factory=dict)
    targets_enabled: bool = True

    def resolve(self, filename: str) -> LogRoute | None:
        """Route a filename to its ``(LogFile class, TargetSet)``.

        Matches a config whose ``filenames`` contains the file's basename stem
        (case-insensitive, extension-insensitive). Returns ``None`` if no config
        claims the file. Filename knowledge stays here, out of the classes.
        """
        stem = Path(filename).name
        stem_lower = stem.lower()
        stem_noext = Path(stem).stem.lower()
        for cfg in self.configs.values():
            for name in cfg.filenames:
                nl = name.lower()
                if nl == stem_lower or nl == stem_noext:
                    ts = cfg.target_set if self.targets_enabled else TargetSet()
                    return LogRoute(log_cls=log_type(cfg.type), target_set=ts)
        return None

    def all_targets(self) -> list[Target]:
        """Every target across all log types (for catalogue / cross-validation)."""
        return [t for cfg in self.configs.values() for t in cfg.target_set.targets]


def load_log_configs(directory: str | Path, *, targets_enabled: bool = True) -> LogConfigSet:
    """Load every ``*.yaml`` / ``*.yml`` under ``directory`` into a config set.

    A missing directory yields an empty set (nothing routes) rather than raising.
    """
    d = Path(directory)
    configs: dict[str, LogTypeConfig] = {}
    if d.is_dir():
        for path in sorted([*d.glob("*.yaml"), *d.glob("*.yml")]):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cfg = LogTypeConfig.from_dict(data, origin=str(path))
            if cfg.type in configs:
                raise ValueError(f"{path}: duplicate log type {cfg.type!r}")
            configs[cfg.type] = cfg
    return LogConfigSet(configs=configs, targets_enabled=targets_enabled)
