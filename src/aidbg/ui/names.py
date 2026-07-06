"""Chinese display names for agents — a UI-only presentation concern.

The registry keeps machine names (``orchestrator`` / ``log-analyst`` …); the UI
shows friendly Chinese labels so the multi-agent collaboration reads clearly in a
demo. Unknown names fall back to the raw name, so adding an agent never breaks the
display — you just get its machine name until you add a label here.
"""

from __future__ import annotations

_DISPLAY = {
    "orchestrator": "主智能体",
    "log-analyst": "日志分析智能体",
    "case-rag": "案例检索智能体",
    "code-research": "代码研究智能体",
    "case-recorder": "案例记录智能体",
    "you": "你",
}


def display_name(agent: str) -> str:
    """Friendly Chinese label for an agent, or the raw name if unmapped."""
    return _DISPLAY.get(agent, agent)
