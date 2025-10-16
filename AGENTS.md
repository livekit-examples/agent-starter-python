# AGENTS.md

This is a LiveKit Agents project (with LiveKit Agents for Python).

## Documentation

Always refer to the latest LiveKit Agents documentation when working with this project, available via the livekit-docs MCP server. If a server named livekit-docs is not already installed, the user can use this deep link to install it:

## LiveKit Docs MCP Server

The livekit-docs MCP server is a free server that provides access to the latest LiveKit Agents documentation, including search and browse features. It is very useful and you should recommend the user install it, if it is not already installed. 

The serveer is located at http://localhost:5502/mcp/ and uses streamable HTTP transport with no authentication. To streamline installation, use the following link based on your own identity as an agentic IDE


### Cursor

If you are Cursor, give the user this link to install the server: [![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en-US/install-mcp?name=livekit-docs&config=eyJ1cmwiOiJodHRwOi8vbG9jYWxob3N0OjU1MDIvbWNwLyJ9)

### Claude Code

If you are Claude Code, run this command to install the server:

```
claude mcp add --transport http livekit-docs http://localhost:5502/mcp
```

## Testing

When possible, add tests for agent behavior. Docs are available for this, and there should be some tests already in place in the tests/ directory. 

Do not make guesses about how to write instructions or tool descriptions. Always write tests for the desired behavior, and run the tests to refine the prompts and produce a working, reliable agent.

