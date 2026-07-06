# Textual TUI + pydantic-ai Multi-Agent Framework Plan

> **Historical doc.** This captures the original from-scratch framework build,
> when the bootstrap sub-agents were generic (coder / researcher / code-reviewer).
> The project has since pivoted to a **传送底软 (embedded-Linux BSP)
> fault-localization assistant**: the generic agents were retired and replaced by
> the domain team **log-analyst → case-rag → code-research → case-recorder** (see
> `README.md` and `CLAUDE.md` for the current architecture). The framework design,
> streaming pump, registries, and extension model below are all still accurate —
> only the specific agent lineup changed.

## Context

Empty repo at `\\wsl.localhost\Ubuntu-22.04\root\workspace\ai_debug` (only `.git`). Build a CLI TUI agent framework from scratch:

- Textual TUI: chat-style with sidebar activity feed
- Agent framework: pydantic-ai v2
- Multi-agent: Orchestrator pattern — one main Agent delegates via tool calls to sub-agents (coder / researcher)
- LLM backends: OpenAI-compatible (DeepSeek / Ollama / vLLM / OpenAI) via `.env`
- Capabilities required: Function calling, Streaming, MCP client

User's directive: "build the framework first, design it well so agent capabilities can be extended later". Goal is a minimal runnable skeleton with clear extension points; each wire (streaming / tool events / MCP / sub-agent delegation) must be demonstrably working.

Verified API facts (via context7, v2):
- `OpenAIChatModel` + `OpenAIProvider(base_url, api_key)` (v1 `OpenAIModel` renamed)
- `agent.iter()` / `agent.run_stream_events()` produce flat event stream: `PartDeltaEvent(TextPartDelta)` / `FunctionToolCallEvent` / `FunctionToolResultEvent`
- MCP v2 unified as `MCPToolset`, mounted via `Agent(toolsets=[...])`
- Sub-agent delegation MUST forward `ctx.usage` to aggregate token usage
- Textual streaming: one `MarkdownStream` per message inside a `VerticalScroll` (RichLog only for sidebar events)
- Async bridge: `@work(exclusive=True, group="llm")` + `app.post_message(...)` (thread-safe)

---

## Architecture: One-Directional Four-Layer Stack

```
   ui       ← only this layer imports textual
   ↓ subscribes EventBus / calls session.send()
   session  ← ChatSession: message history + usage + event bus + run loop
   ↓ uses core.agent_factory to build Agent
   core     ← pydantic-ai wiring, registries, event pump
   ↓ reads Settings
   config   ← pydantic-settings + mcp_servers.json
```

Invariant: `core / session / config` must NOT `import textual`. Enforce with one grep line in CI.

---

## Directory Layout (src/ + uv)

```
ai_debug/
├── .env.example
├── .gitignore
├── pyproject.toml                  # [project.scripts] aidbg = "aidbg.cli:main"
├── uv.lock
├── README.md
├── mcp_servers.json                # MCP server list
├── prompts/
│   ├── orchestrator.md
│   ├── coder.md
│   └── researcher.md
├── src/aidbg/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                      # argparse -> load Settings -> launch App
│   ├── config/
│   │   ├── settings.py             # pydantic-settings
│   │   └── mcp.py                  # parse mcp_servers.json
│   ├── core/                       # UI-agnostic pydantic-ai wiring
│   │   ├── deps.py                 # AppDeps
│   │   ├── events.py               # UiEvent + EventBus
│   │   ├── registry.py             # AgentRegistry / ToolRegistry
│   │   ├── models.py               # model_factory -> OpenAIChatModel
│   │   ├── mcp.py                  # build_toolsets -> list[MCPToolset]
│   │   ├── agent_factory.py        # build_agent / build_orchestrator
│   │   └── streaming.py            # pump_agent_run
│   ├── agents/                     # EXTENSION SLOT: one file = one sub-agent
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── coder.py
│   │   └── researcher.py
│   ├── tools/                      # EXTENSION SLOT: one file = one native tool
│   │   ├── __init__.py
│   │   ├── echo.py
│   │   └── read_file.py
│   ├── session/
│   │   ├── history.py              # save/load via ModelMessagesTypeAdapter
│   │   └── session.py              # ChatSession
│   └── ui/                         # only place importing textual
│       ├── app.py                  # AidbgApp(App)
│       ├── app.tcss
│       ├── messages.py             # UiEventArrived(Message)
│       ├── widgets/
│       │   ├── chat_view.py
│       │   ├── chat_message.py     # wraps MarkdownStream
│       │   ├── activity.py         # RichLog
│       │   ├── agent_list.py
│       │   └── input_bar.py
│       └── workers.py              # ChatController.run_turn
└── tests/
    ├── test_registry.py
    ├── test_event_bus.py
    ├── test_agent_factory.py
    └── test_history_roundtrip.py
```

---

## Key Design: pydantic-ai stream to Textual bridge

Three parts:

### 1. UI-agnostic event dataclasses (core/events.py)

Flat dataclass union, one class per distinguishable UI concern:
TokenDelta, ThinkingDelta, ToolCallStarted, ToolCallFinished, DelegationStarted, DelegationFinished, MessageStarted, MessageFinished, RunFinished.

EventBus is a fan-out asyncio.Queue: UI subscribes once, core just publishes.

### 2. Event pump (core/streaming.py)

`pump_agent_run(agent, prompt, *, deps, usage, bus, agent_name, message_history=None)`:

- Iterates via `agent.iter(...)` and `node.stream(run.ctx)` for fine-grained events
- Translates each pydantic-ai event into a UiEvent published to bus:
  - PartStartEvent(text) -> MessageStarted
  - PartDeltaEvent(TextPartDelta) -> TokenDelta
  - PartDeltaEvent(ThinkingPartDelta) -> ThinkingDelta
  - PartStartEvent(tool-call) -> ToolCallStarted
  - FunctionToolResultEvent -> ToolCallFinished
  - PartEndEvent(text) -> MessageFinished
  - End of run -> RunFinished(usage_summary=str(usage))
- Returns pydantic-ai AgentRunResult

### 3. Textual worker subscribes and forwards to UI

```python
class ChatController:
    @work(exclusive=True, group="llm")
    async def run_turn(self, prompt: str):
        q = self.session.bus.subscribe()
        drain = self.app.run_worker(self._drain(q), group="ui", exclusive=False)
        try:
            await self.session.run(prompt)
        finally:
            await q.put(None)
            await drain.wait()

    async def _drain(self, q):
        while (ev := await q.get()) is not None:
            self.app.post_message(UiEventArrived(ev))
```

AidbgApp.on_ui_event_arrived dispatches by ev.kind:
- msg_start -> chat_view.new_message(agent, id, role) creates ChatMessage(Markdown)
- token -> chat_view[id].append(text)
- msg_end -> chat_view[id].finalize()
- tool_start / tool_end -> activity.write(...)
- delegate_start / delegate_end -> activity + agent_list.highlight
- run_end -> re-enable input, update footer usage

---

## Orchestrator: sub-agents share the same pump

Sub-agent runs go through the SAME pump_agent_run with agent_name=child, so events are tagged by agent and UI renders naturally nested:

```python
def _make_delegate_tool(parent_name, child_agent, child_spec):
    async def delegate(ctx: RunContext[AppDeps], task: str) -> str:
        bus = ctx.deps.bus
        await bus.publish(DelegationStarted(parent=parent_name, child=child_spec.name, task=task[:200]))
        result = await pump_agent_run(child_agent, task,
                                      deps=ctx.deps,
                                      usage=ctx.usage,   # CRITICAL: forward usage
                                      bus=bus,
                                      agent_name=child_spec.name)
        await bus.publish(DelegationFinished(parent=parent_name, child=child_spec.name,
                                             output_preview=str(result.output)[:200]))
        return result.output
    delegate.__doc__ = child_spec.description   # becomes the tool description
    delegate.__name__ = f"delegate_to_{child_spec.name}"
    return delegate
```

---

## Extension Points (all ~10-line drop-ins)

### Add a sub-agent

```python
# src/aidbg/agents/code_reviewer.py
from aidbg.core.registry import AGENTS, AgentSpec

AGENTS.register(AgentSpec(
    name="code-reviewer",
    description="Review a code diff and give actionable feedback.",
    profile="default",
    instructions_path="prompts/code_reviewer.md",
    tool_names=("read_file",),
))
```
Then add `from . import code_reviewer` in agents/__init__.py. Orchestrator sees `delegate_to_code-reviewer(task)` on next startup.

### Add a native tool

```python
# src/aidbg/tools/read_file.py
from pydantic_ai import RunContext
from aidbg.core.registry import TOOLS
from aidbg.core.deps import AppDeps

@TOOLS.register()
async def read_file(ctx: RunContext[AppDeps], path: str, max_bytes: int = 65536) -> str:
    """Read a file under the workspace (UTF-8)."""
    p = (ctx.deps.workspace / path).resolve()
    if ctx.deps.workspace not in p.parents and p != ctx.deps.workspace:
        raise ValueError("path escapes workspace")
    return p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
```

### Add an MCP server

Add one line in mcp_servers.json:
```json
{ "name": "git", "kind": "stdio", "command": "uvx", "args": ["mcp-server-git"] }
```
Reference from any agent spec with `mcp_names=("fs", "git")`.

---

## Config

### .env.example

```
AIDBG_DEFAULT__BASE_URL=https://api.deepseek.com/v1
AIDBG_DEFAULT__API_KEY=sk-...
AIDBG_DEFAULT__MODEL=deepseek-chat

AIDBG_OLLAMA__BASE_URL=http://localhost:11434/v1
AIDBG_OLLAMA__API_KEY=ollama
AIDBG_OLLAMA__MODEL=qwen2.5:14b

AIDBG_PROFILE_ORCHESTRATOR=default
AIDBG_PROFILE_CODER=default
AIDBG_PROFILE_RESEARCHER=ollama

AIDBG_THEME=nord
AIDBG_HISTORY_PATH=.aidbg/history.jsonl
AIDBG_MCP_CONFIG=mcp_servers.json
```

config/settings.py uses `env_nested_delimiter="__"`. Adding a profile = 3 env lines + 1 field.

---

## Dependencies (pyproject.toml)

```toml
[project]
name = "aidbg"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pydantic-ai-slim[openai,mcp]>=2.0",
  "textual>=0.86",
  "pydantic-settings>=2.5",
  "python-dotenv>=1.0",
  "rich>=13",
]

[project.optional-dependencies]
tracing = ["logfire>=2"]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "ruff>=0.6", "mypy>=1.11"]

[project.scripts]
aidbg = "aidbg.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/aidbg"]
```

No CLI framework (argparse suffices), no DI container (pydantic-ai deps_type is DI), no entry_points plugin loader (explicit imports are more greppable).

---

## Verification Plan

Cheapest to most integrated:

1. Static: ruff check, mypy src (strict on core/, session/)
2. Layering invariant: `! grep -RIE 'import textual|from textual' src/aidbg/core src/aidbg/session src/aidbg/config`
3. Unit tests: uv run pytest — registry, event bus, history round-trip
4. agent_factory + TestModel: build orchestrator with `pydantic_ai.models.test.TestModel`, feed a scripted `delegate_to_coder(task=...)` response, assert bus receives DelegationStarted -> coder Message*/Token* -> DelegationFinished in order
5. streaming pump + FunctionModel: scripted TextPart + ToolCallPart; assert MessageStarted -> TokenDelta* -> MessageFinished -> ToolCallStarted -> ToolCallFinished -> RunFinished
6. MCP smoke: launch fs MCP via `npx -y @modelcontextprotocol/server-filesystem .`; TestModel triggers list_directory; assert ToolCallFinished has non-empty preview
7. End-to-end interactive: `uv run aidbg` against a real backend (Ollama or DeepSeek):
   - "hello" -> single Markdown streams reply, footer shows usage
   - "ask the coder to write fizzbuzz" -> sidebar shows "delegating to coder", coder tokens appear in a second ChatMessage badged "coder", then "coder done"
   - "read pyproject.toml" -> read_file tool fires, sidebar shows call and return
   - Ctrl+C mid-stream -> worker group cancels, input re-enables, partial message preserved
   - Ctrl+S -> .aidbg/history.jsonl written; restart aidbg -> transcript restored

Passing all seven step-7 sub-cases = "framework is up, every wire connected."

---

## Load-Bearing Decisions

| Decision | Rationale |
|---|---|
| src/ layout + four-layer one-way stack | Forces core-UI decoupling; unit tests need no Textual |
| Two decorator registries + explicit __init__.py re-exports | Explicit, greppable, no entry_point magic |
| Single EventBus + flat dataclass UiEvent union | Shields UI from pydantic-ai event shape changes |
| Sub-agents run through same pump with agent_name tag | UI renders nested activity naturally |
| Delegate adapter forwards ctx.usage | pydantic-ai requirement for usage aggregation |
| One MarkdownStream per message in VerticalScroll | Official Textual streaming pattern |
| pydantic-settings nested profiles (AIDBG_DEFAULT__*) | Adding a backend = 3 env lines + 1 field |
| MCP list in separate JSON | Structured, versioned, decoupled from .env |
| No CLI framework / DI container / plugin loader | Pragmatic per user's "get framework up" directive |

---

## Implementation Order

1. pyproject.toml + .env.example + .gitignore + mcp_servers.json + prompts skeleton
2. config/{settings,mcp}.py + unit tests
3. core/{deps,events,registry,models,mcp}.py
4. core/{agent_factory,streaming}.py + TestModel/FunctionModel unit tests
5. tools/{echo,read_file}.py
6. agents/{orchestrator,coder,researcher}.py
7. session/{history,session}.py
8. ui/{app,app.tcss,messages,workers}.py + ui/widgets/*
9. cli.py + __main__.py
10. Run step-7 end-to-end scenarios; all green = done
