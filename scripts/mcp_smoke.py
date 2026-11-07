#!/usr/bin/env python3
"""Smoke-test the CyberGym MCP server over stdio (no API key needed).

    python scripts/mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from village.cybergym import _prepare_mock  # noqa: E402


def _text(result) -> str:
    parts = []
    for item in getattr(result, "content", []) or []:
        parts.append(getattr(item, "text", str(item)))
    return "\n".join(parts)


async def main() -> int:
    ws = ROOT / ".village" / "mcp" / "scout"
    ws.mkdir(parents=True, exist_ok=True)
    _prepare_mock("mock:1", ws)
    board = ROOT / ".village" / "mcp" / "board.jsonl"

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "village.mcp_server",
            "--workspace", str(ws),
            "--board", str(board),
            "--agent", "scout",
        ],
        cwd=str(ROOT),
        env={"PYTHONPATH": str(ROOT / "src")},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("tools:", names)
            assert {"bash", "grade_poc", "post_message", "read_board"} <= set(names)

            r = await session.call_tool("task_description", {})
            print("\ntask_description ->", _text(r)[:80].replace("\n", " "))

            r = await session.call_tool("bash", {"command": "ls -la"})
            print("\nbash ls ->", _text(r)[:160].replace("\n", " | "))

            # Build a valid PoC via bash, then grade it through the grounded tool.
            r = await session.call_tool(
                "bash", {"command": "printf AAAAAAAAAAAAAAAA > poc.bin"}
            )
            r = await session.call_tool("grade_poc", {"path": "poc.bin"})
            print("\ngrade_poc(valid) ->", _text(r))
            assert '"solved": true' in _text(r).replace('"solved":true', '"solved": true') or "true" in _text(r)

            # A too-short PoC must fail.
            await session.call_tool("bash", {"command": "printf AA > bad.bin"})
            r = await session.call_tool("grade_poc", {"path": "bad.bin"})
            print("\ngrade_poc(short) ->", _text(r))

            await session.call_tool("post_message", {"text": "MCP server online, PoC works."})
            r = await session.call_tool("read_board", {"limit": 5})
            print("\nread_board ->", _text(r).replace("\n", " | "))

    print("\nMCP server smoke test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
