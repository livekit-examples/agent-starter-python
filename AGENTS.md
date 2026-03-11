# AGENTS.md

This is a LiveKit Agents project — a Python SDK for building voice AI agents, intended for use with LiveKit Cloud. See @README.md for more about the LiveKit ecosystem.

## This project already has a working voice agent

The file `src/agent.py` is a complete, working voice agent. **Do not rewrite it from scratch.** Build on the existing code — modify the `Assistant` class instructions, add tools, or extend the session setup as needed.

Run the existing agent to verify it works before making changes:
```
uv run python src/agent.py dev
```

## Documentation access — USE MCP FIRST

LiveKit Agents evolves rapidly. **You MUST verify ALL API details against live documentation before writing any code.** Do not rely on pre-trained knowledge — it is outdated.

**Use the `livekit-docs` MCP server for every documentation lookup:**

1. **Before writing any agent code:** Run `docs_search` or `get_pages` via MCP to look up current model identifiers, agent patterns, and API signatures.
2. **Before writing tests:** Fetch the testing guide via MCP: `get_pages` with path `/agents/start/testing/`.
3. **Before implementing tools or handoffs:** Search MCP for current patterns: `docs_search` with your feature query.
4. **Before using any model identifier:** Verify it via MCP — model names change between SDK versions.

If `livekit-docs` MCP tools are not available, install the LiveKit Docs MCP server:

- **Claude Code:** `claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp`
- **Codex:** `codex mcp add --url https://docs.livekit.io/mcp livekit-docs`
- **Cursor:** [![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en-US/install-mcp?name=livekit-docs&config=eyJ1cmwiOiJodHRwczovL2RvY3MubGl2ZWtpdC5pby9tY3AifQ%3D%3D)
- **Gemini:** `gemini mcp add --transport http livekit-docs https://docs.livekit.io/mcp`

If MCP cannot be installed, fetch documentation directly from https://docs.livekit.io.

<!-- VERIFY: architecture patterns current as of 2026-02 -->
## Key architecture (do not change unless asked)

The existing code follows the correct LiveKit Agents pattern:

- `Assistant(Agent)` — agent class with instructions and optional `@function_tool()` methods
- `AgentServer()` + `@server.rtc_session()` — server setup and room session handler
- `AgentSession(stt=..., llm=..., tts=..., ...)` — voice pipeline with LiveKit Inference models
- `await session.start(agent=..., room=ctx.room)` then `await ctx.connect()` — session lifecycle
- `cli.run_app(server)` in `__main__` — CLI entrypoint (supports `dev`, `download-files` commands)

**LiveKit Inference** is used for all AI models (no separate API keys needed):
- STT: `inference.STT(model="assemblyai/universal-streaming")`
- LLM: `inference.LLM(model="openai/gpt-4.1-mini")`
- TTS: `inference.TTS(model="cartesia/sonic-3", voice="...")`

> **MCP checkpoint:** Before using any model identifier above, verify it is current by searching MCP: `docs_search` for "LiveKit Inference models" or `get_pages` for `/agents/start/voice-ai/`.

## Skill document (read FIRST)

**Before writing any code**, check for the LiveKit Agents skill in `.claude/skills/`, `.cursor/skills/`, or `.agents/skills/`. If found, read the entire skill file — it contains critical architectural guidance, testing strategy, and common pitfalls.

If no skill file exists, install it:
```
npx skills add livekit/agent-skills
```
Then read the installed skill in its entirety before proceeding.

## Project structure

This Python project uses the `uv` package manager. Always use `uv` to install dependencies, run the agent, and run tests.

All app-level code is in the `src/` directory. Simple agents can be constructed with a single `agent.py` file. Additional files can be added, but you must retain `agent.py` as the entrypoint (see the associated Dockerfile for how this is deployed).

Maintain code formatting with ruff: `uv run ruff format` and `uv run ruff check`.

## Testing

Every implementation must include tests. **Read the existing tests in `tests/test_agent.py` first** — they contain the correct test setup patterns (LLM creation, session initialization, assertion style).

> **MCP checkpoint:** Before writing any test code, fetch the full testing guide via MCP: `get_pages` with path `/agents/start/testing/`. The test API has specific method names that you must use exactly.

**Do not rewrite existing tests.** Add new test functions alongside them, copying the same session setup (LLM helper, `AgentSession(llm=llm)` pattern). Consult the [testing documentation](https://docs.livekit.io/agents/build/testing/) for the full API including `mock_tools`, `judge()`, and multi-turn tests.

<!-- VERIFY: tool assertion pattern current as of 2026-02 -->
When adding `@function_tool()` methods, use the existing `_llm()` helper and `AgentSession(llm=llm)` setup from the test file — do not create custom MockLLM or FakeLLM classes. Test the tool call chain using this complete pattern:
```python
async def test_weather_tool():
    async with (
        _llm() as llm,
        AgentSession(llm=llm) as session,
    ):
        await session.start(Assistant())
        result = await session.run(user_input="What's the weather in Tokyo?")
        result.expect.next_event().is_function_call(name="tool_name")
        result.expect.next_event().is_function_call_output()
        await result.expect.next_event().is_message(role="assistant").judge(llm, intent="...")
```
**Important:** Do not pass `type=` to `next_event()` and then chain `.is_function_call()` — use one or the other, not both.

**Do not stop after the first test failure.** Run `uv run pytest`, read the error output, fix the issue, and re-run. Repeat until all tests pass with 0 failures. The task is not complete until tests pass.

## Handoffs and tasks ("workflows")

Voice AI agents are sensitive to latency. Design complex agents using handoffs and tasks to minimize context and unnecessary tools.

> **MCP checkpoint:** Before implementing handoffs or tasks, search MCP: `docs_search` for "handoffs workflows" and `get_pages` for `/agents/build/workflows/`. The API has specific patterns that must be followed exactly.

## Tools

> **MCP checkpoint:** Before implementing `@function_tool()` methods, fetch the tools guide via MCP: `get_pages` with path `/agents/logic/tools/`. Tool patterns have changed across SDK versions.

## LiveKit Docs MCP feedback

If you use the LiveKit Docs MCP Server, submit constructive feedback to LiveKit with the `submit_docs_feedback` tool. Add this to your to-do list when planning work. Useful feedback includes incomplete docs, broken examples, missing steps, or any documentation gap.

## LiveKit CLI

You can use the LiveKit CLI (`lk`) for various tasks. Installation instructions are at https://docs.livekit.io/home/cli if needed. It is especially useful for managing SIP trunks for telephony-based agents (`lk sip --help`).
