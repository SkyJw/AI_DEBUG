"""The sidebar activity feed: a RichLog of tool calls and delegations."""

from __future__ import annotations

from textual.widgets import RichLog


class ActivityLog(RichLog):
    """Append-only log of tool/delegation activity (sidebar)."""

    def __init__(self) -> None:
        super().__init__(markup=True, wrap=True, highlight=False)

    def tool_started(self, agent: str, tool: str, args_preview: str) -> None:
        self.write(f"[cyan]{agent}[/] 调用工具 [b]{tool}[/]（[dim]{args_preview}[/]）")

    def tool_finished(self, agent: str, tool: str, result_preview: str) -> None:
        self.write(f"[green]✓[/] {tool} 返回 [dim]{result_preview}[/]")

    def delegation_started(self, parent: str, child: str, task: str) -> None:
        self.write(f"[magenta]🔀 {parent} 调用子智能体 →「{child}」[/]：[dim]{task}[/]")

    def delegation_finished(self, parent: str, child: str, preview: str) -> None:
        self.write(f"[magenta]✅ 子智能体「{child}」已完成[/]：[dim]{preview}[/]")

    def run_error(self, agent: str, message: str) -> None:
        self.write(f"[red]✗ {agent} 出错[/]：{message}")
