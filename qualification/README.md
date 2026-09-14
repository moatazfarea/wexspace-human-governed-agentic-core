# Isolated capability qualification

These probes exercise installed third-party runtimes against synthetic WEXSPACE work. They run in separate environments and do not add optional framework/server dependencies to the core package.

- `langgraph_resume.py`: real LangGraph tool callbacks, durable SQLite checkpoint, fresh-process continuation, and the WEXSPACE human review boundary. No model inference.
- `mcp_servers.py`: starts the official Git and Filesystem reference servers over stdio, enumerates tools, executes safe calls, verifies file readback, and checks a synthetic directory boundary.

Run the **Isolated fleet qualification** GitHub workflow for exact installed versions and execution receipts. A successful scoped probe does not authorize all exposed server operations or qualify a cloud model provider.

Official sources:
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://github.com/modelcontextprotocol/servers/tree/main/src/git
- https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem

LangGraph and the MCP reference servers are MIT licensed. Their licenses remain with installed packages; this directory contains original WEXSPACE probes, not vendored framework source.
