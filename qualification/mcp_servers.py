"""Start official MCP servers and verify safe synthetic calls over stdio."""
import asyncio
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def output_text(result):
    return "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")


async def git_probe(root):
    repository = root / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "synthetic.txt").write_text("Synthetic MCP qualification.\n")
    params = StdioServerParameters(command=sys.executable, args=[
        "-m", "mcp_server_git", "--repository", str(repository)])
    started = perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = [tool.name for tool in (await session.list_tools()).tools]
            assert "git_status" in names
            result = await session.call_tool("git_status", {"repo_path": str(repository)})
            assert not result.isError
            body = output_text(result)
            assert "synthetic.txt" in body
            return {
                "server": "modelcontextprotocol/git",
                "version": version("mcp-server-git"),
                "mcp_sdk_version": version("mcp"),
                "state": "QUALIFIED",
                "scope": "Read-only git_status in disposable synthetic repository",
                "available_tools": names,
                "real_calls": 1,
                "result_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                "limitation": "Other exposed Git operations are not qualified or allowed by this probe.",
            }


async def filesystem_probe(root):
    allowed = root / "allowed"
    allowed.mkdir()
    outside = root / "outside-synthetic.txt"
    outside.write_text("Synthetic boundary-test marker.")
    package = Path(".fleet-node/node_modules/@modelcontextprotocol/server-filesystem").resolve()
    package_version = json.loads((package / "package.json").read_text())["version"]
    params = StdioServerParameters(command=shutil.which("node"), args=[
        str(package / "dist/index.js"), str(allowed)])
    started = perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = [tool.name for tool in (await session.list_tools()).tools]
            assert {"write_file", "read_text_file", "list_allowed_directories"} <= set(names)
            directories = await session.call_tool("list_allowed_directories", {})
            assert not directories.isError and str(allowed) in output_text(directories)
            target = allowed / "receipt.txt"
            payload = "WEXSPACE synthetic filesystem tool receipt."
            written = await session.call_tool("write_file", {"path": str(target), "content": payload})
            assert not written.isError
            readback = await session.call_tool("read_text_file", {"path": str(target)})
            assert not readback.isError and output_text(readback) == payload
            assert target.read_text() == payload
            denied = await session.call_tool("read_text_file", {"path": str(outside)})
            assert denied.isError, "The server must enforce its configured directory boundary"
            return {
                "server": "modelcontextprotocol/filesystem",
                "version": package_version,
                "state": "QUALIFIED",
                "scope": "Synthetic read/write inside a single disposable allowed directory",
                "available_tools": names,
                "real_calls": 4,
                "successful_calls": 3,
                "expected_boundary_denials": 1,
                "result_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                "limitation": "Reference server; broad write tools must not be granted to untrusted agents.",
            }


async def main():
    with tempfile.TemporaryDirectory(prefix="wexspace-mcp-") as directory:
        root = Path(directory)
        for probe in [git_probe, filesystem_probe]:
            print(json.dumps(await probe(root), sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
