"""The bottom input bar where the user types prompts."""

from __future__ import annotations

from textual.widgets import Input


class InputBar(Input):
    """Prompt input. Disabled while a turn is running."""

    def __init__(self) -> None:
        super().__init__(
            placeholder=(
                "输入问题回车发送 · 例:分析 samples/fake_evidence 为什么反复重启"
                " · F1 帮助 · Ctrl+S 保存 · Ctrl+C 退出"
            )
        )
