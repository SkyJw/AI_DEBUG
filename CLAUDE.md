# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`aidbg` — a Textual TUI multi-agent CLI over **pydantic-ai** (installed: 2.5.x).
An orchestrator agent delegates to sub-agents (coder / researcher) via tool calls,
streaming tokens/tool-activity/delegations to a chat UI. Backends are
OpenAI-compatible (DeepSeek / Ollama / vLLM / OpenAI) via `.env`. The framework is
built and verified (23 tests, ruff + mypy clean, headless UI smoke test).

- **`PLAN.md`** — the original design doc (architecture, extension points,
  verification plan). Still the best "why" reference.
- **`README.md`** — user-facing quick start + extension recipes.

## Commands (uv-based)

```
uv sync                                          # install deps
uv run aidbg                                     # launch the TUI
uv run aidbg --list-agents                       # print agents, no TUI (no backend needed)
uv run pytest                                    # full suite (uses TestModel/FunctionModel — no backend)
uv run pytest tests/test_streaming_pump.py -q    # one file
uv run pytest tests/test_registry.py::test_tool_register_and_resolve   # one test
uv run ruff check src tests
uv run mypy src                                  # clean across all layers
```

## Load-bearing invariants (do not break these)

- **Layer direction is one-way: `ui → session → core → config`.** `core/`,
  `session/`, `config/`, and `logs/` must **never** `import textual`. CI check:
  `! grep -RIE 'import textual|from textual' src/aidbg/core src/aidbg/session src/aidbg/config src/aidbg/logs`
- **The streaming pump is the only pydantic-ai↔UI bridge.** `core/streaming.py`
  (`pump_agent_run`) iterates `agent.iter()`, gating `node.stream()` with
  `Agent.is_model_request_node` / `is_call_tools_node`, and translates each
  pydantic-ai event into a flat `UiEvent` (`core/events.py`) on a fan-out
  `EventBus`. The UI subscribes to the bus only — it never imports pydantic-ai
  message types. Both orchestrator and sub-agents run through this same pump,
  tagged by `agent_name`, so nested activity renders naturally.
- **Sub-agent delegation forwards `ctx.usage`** into the child run
  (`agent_factory._make_delegate_tool`) — required for aggregated token usage.
- **Extension is explicit + greppable.** Two decorator registries (`AGENTS`,
  `TOOLS` in `core/registry.py`) plus `from . import <module>` re-exports in
  `agents/__init__.py` / `tools/__init__.py`. No entry-point / plugin magic. Order
  matters in `agents/__init__.py`: sub-agents import before the orchestrator so
  `delegates_to` resolves.
- **Model injection seam:** `build_agent`/`build_orchestrator` take
  `model_override`. Tests pass a `TestModel`/`FunctionModel` so no real backend is
  contacted; this is also the seam for a future `--model` flag. Never hardcode a
  model in the factory.
- **`logs/` is pure modelling — no interpretation, lossless w.r.t. input.** The
  pipeline is `raw text → TargetSet (optional, YAML) → LogFile.parse → list[LogRecord]`.
  `parse_line` never returns `None` (an unrecognised line becomes a record with
  `timestamp=None`, `message==raw`); `line_no` is the original file index and the
  only reliable ordering key (timestamps jump 1970→1990→real as the board sets its
  clock, so they're never a continuous clock). No boot segmentation / board-type /
  stage inference lives here — that's a future layer above `logs/`. Third registry
  `LOG_TYPES` (`logs/base.py`) mirrors `AGENTS`/`TOOLS`; add a log type = new
  `XxxRecord` + `XxxLog(LogFile)` + `@register_log` + a `configs/logs/*.yaml`.
  Filename→class routing (e.g. UBOOT / hiboot_bootinfo both → `UbootLog`) lives in
  YAML, **not** in the class.
- **`Bundle`/`Evidence` (`logs/bundle.py`) are structural, not interpretive.** A
  `Bundle` loads one package (folder or `.tgz`) — `CBBLOG0..11` (boot, ring, index
  0 newest, clears reserved mem) or `CBBLOGDUMP0..2` (runtime, hourly, no clear) —
  routes each member file via `LogConfigSet`, and exposes parsed logs by source +
  an `unrouted` list. `load_evidence(root, configs)` discovers + orders bundles.
  **One bundle may span several boots** (a boot that never reached the final
  process is dumped by the *next* boot), so splitting a bundle into boots is the
  next layer up — deliberately not done here.
- **`target`/`problems` are the diagnostic-knowledge seam (the signature library).**
  A `TargetSet` (`logs/target.py`, configured under `target:` in `configs/logs/*.yaml`)
  is a *switchable* catalogue of meaningful log patterns. One switch (`enabled`)
  gates two jobs: **select** (whitelist — keep only matched lines) and **annotate**
  (`annotate(line)` → matched `Target`s carrying `meaning` + a `problem` id). When
  `enabled=false` (shipped default) it's raw+lossless AND produces **no annotation**
  — annotation only exists in targeted mode, which is what makes the switch mean
  something. `Problem`s live in `configs/problems.yaml` (`logs/problems.py`) with
  `likely_causes`/`verify_steps` and a `targets` back-reference. Association is
  **bidirectional**: target names its `problem`, problem lists its `targets`;
  `check_links()` + `test_problems.py` enforce both directions resolve. This is the
  curated knowledge the log-analyst sub-agent reads to ground
  hypotheses. NB: was called `filter`/`FilterRule`/`description` before the rename.
- **`log-analyst` is the first consumer of `logs/` — thin tools + playbook, not
  deterministic judgement.** `agents/log_analyst.py` (profile `analyst`,
  delegated from the orchestrator) reads evidence via four typed tools in
  `tools/log_tools.py`: `list_evidence` (orient), `targeted_view` (high-signal —
  target-matched lines tagged with `meaning` + `⟶ problem:<id>`), `read_log`
  (typed slice, optional `level`/`process_id` filters), `describe_problem`
  (catalogue lookup). Tools run *typed queries over the model* (not raw-text
  grep) and project to a compact view where every line carries a stable
  `bundle/source:line_no` coordinate the Markdown report must cite. Evidence is
  loaded **raw/lossless** and cached per dir (`_CACHE`); annotation is applied at
  query time via an on-the-fly enabled `TargetSet` (shipped sets are disabled).
  Boot segmentation / stage inference stays in the *playbook* (`prompts/log_analyst.md`),
  deferred out of code until real samples calibrate it. The `process_id`/`level`
  filters are forward-looking: they work once CBBLOG field parsing is filled in
  (today `process_id` is always `None`, so that filter correctly matches nothing).

## Non-obvious gotchas (learned building this)

- **PyPI `pydantic-ai` is at 2.x** but the package pin is `>=1.0` (it went
  `0.x → 1.0 → 2.x`; the "v2" in PLAN.md means the API era, not a `2.0` release).
- **pydantic-settings does not auto-collapse** `AIDBG_<NAME>__<FIELD>` env vars
  into `dict[str, ModelProfile]`. `config/settings.py` has a custom
  `_ProfilesSource` that groups them; reserved top-level keys are excluded there.
- **MCP in 2.x:** unified `MCPToolset(<transport>)` where transport is
  `StdioTransport` / `StreamableHttpTransport` (not `MCPServerStdio`).
- **`MarkdownStream.write` / `.stop` are async**; `get_stream` is
  `Markdown.get_stream(md_widget)`. `ChatMessage.append`/`finalize` are async as a
  result, so the App's `on_ui_event_arrived` dispatch awaits token appends.
- **`@work` needs a `DOMNode` `self`.** `ChatController` is a plain helper, so it
  launches workers via `app.run_worker(...)` rather than the `@work` decorator.
- **`run.usage` is a property**, not a method (PLAN.md's `run.usage()` was wrong).

## Layout

`src/aidbg/{config,core,agents,tools,session,ui,logs}/` + `prompts/*.md` (agent
instructions, loaded by path from `AgentSpec.instructions_path`) +
`configs/logs/*.yaml` (one per log type: filename routing + filter) + `tests/`.
`agents/`, `tools/`, and `logs/` are the extension slots — one file per
agent/tool/log-type.
