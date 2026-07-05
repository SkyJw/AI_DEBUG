"""The pure-black aidbg theme.

A minimal, monochrome-leaning palette in the spirit of Claude Code / opencode:
a true-black canvas, near-black raised surfaces, soft off-white text, and a
single restrained accent. Registered and activated by :class:`AidbgApp`.
"""

from __future__ import annotations

from textual.theme import Theme

# One accent, used sparingly (badges, active agent, focus). Everything else is
# grayscale so content — not chrome — carries the color.
_ACCENT = "#7dd3fc"  # soft sky/cyan

AIDBG_BLACK = Theme(
    name="aidbg-black",
    dark=True,
    # Canvas + raised surfaces: true black grading up to near-black.
    background="#000000",
    surface="#0a0a0a",
    panel="#111214",
    # Text.
    foreground="#e6e6e6",
    # Semantic accents (kept muted so nothing screams).
    primary=_ACCENT,
    secondary="#9aa0a6",
    accent=_ACCENT,
    success="#7ee787",
    warning="#e3b341",
    error="#f47067",
    variables={
        # Muted secondary text used for thinking / dim chrome.
        "text-muted": "#6b7178",
        "text-disabled": "#4a4f55",
        # Borders barely lift off the background.
        "border": "#1c1f24",
        "border-blurred": "#141619",
        # Cursor/selection stay subtle on black.
        "block-cursor-background": _ACCENT,
        "block-cursor-foreground": "#000000",
        "input-selection-background": "#7dd3fc35",
        # Scrollbars disappear into the canvas until hovered.
        "scrollbar": "#141619",
        "scrollbar-hover": "#22262c",
        "scrollbar-active": _ACCENT,
        "footer-background": "#000000",
        "footer-key-foreground": _ACCENT,
    },
)
