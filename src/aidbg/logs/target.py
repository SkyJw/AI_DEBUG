"""Target log catalogue — the switchable "logs we care about" stage.

Data flow:  raw file text  ->  TargetSet (this)  ->  LogFile.parse -> records

A *target* is a known, diagnostically-meaningful log pattern. The set does two
things, both gated by one switch (``TargetSet.enabled``):

- **Select (whitelist).** In targeted mode a line is kept only if it matches an
  enabled target; everything else is dropped. There is no drop/deny rule — "keep
  only what I care about" is the whole contract.
- **Annotate.** A matched line is tagged with its target's ``meaning`` (a hint
  written for the LLM) and, if set, the ``problem`` it is a signature of. This is
  what feeds the log-analyst sub-agent.

The switch is what gives the layer meaning:

- ``enabled == False`` (or no targets) → every line passes through untouched and
  **no annotation is produced** (raw, lossless mode — the shipped default).
- ``enabled == True`` → targeted mode: whitelist + annotations.

A global master switch lives one layer up (:mod:`aidbg.logs.config`) and can
force every set off to recover the fully raw stream.

Selection preserves the **original file line number**: :meth:`select` yields
``(line_no, raw)`` pairs carrying the true index, so downstream records still
point back at the real position in the file even after lines are dropped.

No textual import; stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Target:
    """One target log pattern: what to keep, what it means, what problem it signs.

    ``id`` is a stable handle the problem catalogue links back to (bidirectional
    association). ``meaning`` is the human/LLM-facing significance. ``problem`` is
    the id of a :class:`~aidbg.logs.problems.Problem` this line is a signature of
    (optional; ``None`` = a noteworthy line not yet tied to a catalogued problem).
    The object is the extension point — new knobs become new fields here without
    disturbing existing YAML.
    """

    id: str
    meaning: str
    pattern: str
    match: str = "regex"  # "regex" | "substring"
    problem: str | None = None
    enabled: bool = True
    # Compiled form of a regex pattern, cached at construction. Not an init arg;
    # declared so the frozen+slots layout has a slot to hold it.
    _regex: re.Pattern[str] | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.match not in ("regex", "substring"):
            raise ValueError(
                f"target {self.id!r}: match must be 'regex' or 'substring', got {self.match!r}"
            )
        # Compile eagerly so a bad regex fails at load time, not mid-parse.
        if self.match == "regex":
            object.__setattr__(self, "_regex", re.compile(self.pattern))

    def matches(self, line: str) -> bool:
        if not self.enabled:
            return False
        if self.match == "substring":
            return self.pattern in line
        assert self._regex is not None  # guaranteed for match == "regex"
        return self._regex.search(line) is not None


@dataclass(frozen=True, slots=True)
class TargetSet:
    """A catalogue of target patterns plus a master ``enabled`` switch.

    When disabled (or empty), :meth:`keep` keeps every line and :meth:`annotate`
    produces nothing — the raw, lossless stream. When enabled, it whitelists and
    annotates.
    """

    targets: tuple[Target, ...] = ()
    enabled: bool = False

    def keep(self, line: str) -> bool:
        """Whitelist decision: keep a line only if some enabled target matches.

        Always ``True`` when disabled/empty (lossless passthrough).
        """
        if not self.enabled or not self.targets:
            return True
        return any(t.matches(line) for t in self.targets)

    def annotate(self, line: str) -> list[Target]:
        """Targets a line matches — its diagnostic annotations.

        Empty when the set is disabled: annotation only exists in targeted mode,
        so the switch stays meaningful (a disabled set adds no hints).
        """
        if not self.enabled:
            return []
        return [t for t in self.targets if t.matches(line)]

    def select(self, lines: Iterable[str]) -> Iterator[tuple[int, str]]:
        """Yield ``(original_line_no, line)`` for every kept line.

        ``original_line_no`` is the 0-based index in the *input* — preserved even
        as intervening lines are dropped — so records stay traceable to the file.
        """
        for line_no, line in enumerate(lines):
            if self.keep(line):
                yield line_no, line
