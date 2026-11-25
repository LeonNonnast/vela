# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-11-25

### Fixed
- **TS:** `mcp_call` and `delegate` steps that declare `capture` no longer stall in `VelaWorkflows`. They were treated like interactive steps (elicitation gate, "awaiting_input"), so the handler never ran unless the agent sent some `output`. They now run server-side right away, with and without `autoAdvance`.

## [0.1.0] - 2026-11-25

First release of the TypeScript SDK (`vela-sdk` on npm). The Python SDK (`vela-sdk` on PyPI) shares the same version but is not published yet.

### Added
- YAML-defined workflows with step types `freeform`, `choice`, `confirm`, `execute`, `dialog`, `workflow` (sub-workflows), `mcp_call`, and `delegate` (TS only).
- Captures with output parsing and MCP elicitation, branching via `next` / choice options, `depends_on`, `on_error` (retry, fallback, abort).
- `fetch` step field and `mcp_call` execution via a source registry (`registerSource` / `register_source`).
- Delegate step type with handler registry (`registerDelegate`, TS only).
- Template resolution: `params`, `state`, `steps`, `resolved`, `fetch`, `project`.
- Workflow lifecycle: `allow_pause`, `auto_cancel_after`, `auto_archive_after`.
- Identity-based resume, auto-advance loop, agent personas as MCP prompts.
- Storage: in-memory, `LocalStorageStore` (TS), SQLAlchemy (Python); pluggable `WorkflowStore`.
- Adapters: official MCP SDK, FastMCP, LangChain, Azure AI Agents, headless (TS); FastMCP, LangChain, Azure AI Agents (Python).
- Locales: English and German.
- Bundled `vela` module with workflows, agent and method resources.

### Fixed
- **TS:** `depends_on` on a step that requires a field captured by the immediately preceding step no longer blocks the run forever. The dependency check now includes the captures of the step being completed.

### Docs
- **TS:** README rewritten to match the actual API — correct step types, `{{params.x}}` / `{{state.x}}` template syntax, sources/delegates, `fetch`, `lifecycle`, all adapters.
