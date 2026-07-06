"""The startup welcome / help card shown in an empty chat.

A UI-only intro panel: it states what aidbg is, which specialist sub-agents the
主智能体 can call, and gives concrete example questions so a first-time user knows
how to ask. It is mounted into the empty :class:`ChatView` on startup, removed on
the first question, and re-showable via F1. Purely presentational — no core
imports, matching the rest of ``ui/``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Markdown

WELCOME_MD = """\
# 传送底软 · 多智能体协同定位助手

我是「主智能体」，会把你的问题拆解，并**协同多个专家子智能体**一起定位。

## 我能帮你做什么

**🔍 日志定位（核心能力）** — 交给「日志分析智能体」
- 分析 `samples/fake_evidence`，板子为什么反复重启？
- 启动卡在哪个阶段？（如 vBSP_init 卡死排查）
- 是不是掉进了 reset storm / bios 恢复态？
- 有没有内核 oops / panic？发生在哪个驱动？
- 运行态里以太网链路有没有闪断？

**💻 写 / 改 / 解释代码** — 交给「编码智能体」
**🔎 查资料、调研** — 交给「调研智能体」
**✅ 代码评审** — 交给「代码评审智能体」

## 怎么用

- 在下方输入框输入问题，回车发送。
- 定位日志时请带上**证据目录**（工作区相对路径）+ 你的问题。
- 发起定位后，中间会**分出子智能体窗口**（按标签区分各子智能体），实时展示它们的执行过程；主窗口只保留主智能体的内容。
- 右侧「Agents」显示当前活跃的智能体，「Activity」实时显示工具调用与委派过程。
- `Ctrl+S` 保存对话 · `Ctrl+C` 退出 · `F1` 再次查看本帮助
"""


class WelcomeCard(Vertical):
    """A dismissible intro panel with branding + usage hints."""

    def compose(self) -> ComposeResult:
        yield Markdown(WELCOME_MD)
