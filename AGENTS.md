# AGENTS.md

This is a LiveKit Agents project. LiveKit Agents is a Python SDK for building voice AI agents, and this project is designed for LiveKit Cloud. See @README.md for more about the rest of the LiveKit ecosystem.

## Tooling

This Python project uses the `uv` package manager.

Be sure to maintain code formatting, using `uv run ruff format` and `uv run ruff check`.

## LiveKit documentation

Always refer to the latest documentation when working with this project. LiveKit offers both a CLI (`lk docs`) and an MCP server for browsing and searching its documentation.

### LiveKit CLI

The [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/) `lk docs` subcommand gives full access to LiveKit documentation from the terminal. It requires CLI version 2.15.0 or later. Check with `lk --version`.

Install or update the CLI:

- **macOS:** `brew install livekit-cli` (update: `brew update && brew upgrade livekit-cli`)
- **Linux:** `curl -sSL https://get.livekit.io/cli | bash`
- **Windows:** `winget install LiveKit.LiveKitCLI` (update: `winget upgrade LiveKit.LiveKitCLI`)

Run `lk docs --help` to see all available commands. Key commands: `lk docs overview`, `lk docs search`, `lk docs get-page`, `lk docs code-search`, `lk docs changelog`, and `lk docs submit-feedback`. Run `lk docs <command> --help` before using a command for the first time, because the help text explains how to use it and how to interpret results. Prefer browsing (`overview`, `get-page`) over search, and prefer `search` over `code-search`, because docs pages are more current and give better context than raw code. Search results are short excerpts, so fetch the full page with `lk docs get-page` before you act on one.

### LiveKit docs MCP server

For deeper IDE integration, LiveKit also offers an [MCP server](https://docs.livekit.io/reference/developer-tools/docs-mcp/) with the same documentation access. It uses Streamable HTTP transport at `https://docs.livekit.io/mcp`. See your IDE's documentation for how to add it.

### Submit docs feedback to LiveKit

If you use the LiveKit CLI or MCP server to search or browse documentation, also submit constructive feedback to LiveKit with `lk docs submit-feedback` or the MCP `submit_docs_feedback` tool. Add this to your to-do list when planning work, so you file feedback after completing your other tasks. Useful feedback includes incomplete documentation, broken examples, missing steps, or any other gap or issue in the docs.

## LiveKit Agents skill

This project includes the `livekit-agents` skill in `.claude/skills/` and `.agents/skills/`. It covers how to approach agent architecture, workflows, handoffs, tasks, and testing, and it defers to the live documentation for API details. If your tool doesn't load skills automatically, read `.agents/skills/livekit-agents/SKILL.md` before you design or restructure an agent.

## Handoffs and tasks ("workflows")

Voice AI agents are highly sensitive to latency. Design complex agents in a structured way that keeps irrelevant context and unneeded tools out of each LLM request. LiveKit Agents supports handoffs, where one agent hands control to another, and tasks, which are tightly scoped prompts that achieve a specific outcome, for building reliable workflows. Use them instead of long instruction prompts that cover several phases of a conversation. See the [workflows documentation](https://docs.livekit.io/agents/logic/workflows/) for more information.

## Testing

When possible, add tests for agent behavior. Add a scenario to `scenarios.yaml` and run it with `lk agent simulate --scenarios scenarios.yaml`. The scenarios run in CI on every merge to `main`. Read the [simulations documentation](https://docs.livekit.io/testing/simulations/) before editing them.

For turn-level checks that don't need a live session, use the in-process [unit testing framework](https://docs.livekit.io/testing/unit-tests/). `tests/test_agent.py` has a commented-out example. Run those tests with `uv run pytest`.

Important: when you modify core agent behavior such as instructions, tool descriptions, or tasks, workflows, and handoffs, never guess at what works. Use test-driven development (TDD) and start by writing tests for the desired behavior. For example, if you're adding a tool, write one or more tests for the tool's behavior, then iterate on the tool until the tests pass. This is how you produce a working, reliable agent.

After changing the agent, try it with the [agent debugger](https://docs.livekit.io/testing/debugger/) (CLI 2.18.8 or later) before calling the change done. Start the agent with `lk agent debugger start`, send user turns with `lk agent debugger say "..."`, and read the tool calls in each turn as well as the reply. Run `lk agent debugger restart` after every code edit, since a running session keeps the old code, and `lk agent debugger stop` when you're done.

## Debugging

To investigate unexpected agent behavior:

- Reproduce it with `lk agent debugger`: send the turns that trigger the problem and read the tool calls and errors in each one. Add `--logs` to `say` to see log lines, including tracebacks, next to the turn that produced them.
- Add a unit test or simulation scenario once it's fixed, so a later change can't bring it back unnoticed.
- Run `lk agent dev --log-level DEBUG` for verbose logs from a local agent connected to LiveKit Cloud.
- Run `lk agent logs` to stream logs from a deployed agent.
- Ask the developer to open the [Agent Console](https://docs.livekit.io/testing/agent-console/) for speech problems such as turn-taking, interruptions, or transcription, which the text-only debugger can't show. It shows events, tool calls, and model timing for a live session.
- Check [Agent Observability](https://docs.livekit.io/testing/observability/) for transcripts, traces, logs, and recordings of sessions with real users.

## Other CLI commands

Beyond documentation access, the LiveKit CLI (`lk`) handles tasks such as managing SIP trunks for telephony agents. Run `lk --help` to explore available commands.
