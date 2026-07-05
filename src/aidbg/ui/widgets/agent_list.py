"""Sidebar list of known agents, with the active one highlighted."""

from __future__ import annotations

from textual.widgets import Label, ListItem, ListView

from aidbg.ui.names import display_name


class AgentList(ListView):
    """List of agent names; highlights the currently-active agent.

    Shows Chinese display labels but keys items by the machine name so
    :meth:`highlight_agent` still resolves against the registry names.
    """

    def __init__(self, agents: list[str]) -> None:
        self._agents = agents
        items = [ListItem(Label(display_name(name)), id=f"agent-{name}") for name in agents]
        super().__init__(*items)

    def highlight_agent(self, name: str) -> None:
        for agent in self._agents:
            item = self.query_one(f"#agent-{agent}", ListItem)
            item.set_class(agent == name, "active-agent")
