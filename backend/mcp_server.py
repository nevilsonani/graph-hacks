"""
stdio MCP server so the same FalkorDB tools can be selected by an MCP host.
Run: python mcp_server.py
The hackathon UI uses the HTTP adapter at GET /mcp/tools + POST /api/tools/call.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import falkor, seed, tools  # noqa: E402


def handle(msg: dict) -> dict:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "tracewire", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "tools": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": {
                            "type": "object",
                            "properties": {k: {"type": "string"} for k in t["input_schema"]},
                        },
                    }
                    for t in tools.TOOLS
                ]
            },
        }
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        result = tools.call(name, args)
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {"content": [{"type": "text", "text": json.dumps(result, default=str)}]},
        }
    if method == "notifications/initialized":
        return {}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown method"}}


def main():
    falkor.connect()
    seed.seed(force=False)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        reply = handle(msg)
        if reply:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
