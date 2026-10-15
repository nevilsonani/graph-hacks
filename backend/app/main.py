import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, falkor, seed, tools
from .config import settings

WEB = next(
    (
        p
        for p in (
            Path(__file__).resolve().parents[2] / "web",
            Path(__file__).resolve().parents[1] / "web",
            Path("/app/web"),
            Path("/web"),
        )
        if p.exists()
    ),
    Path("/app/web"),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    falkor.connect()
    seed.seed(force=False)
    yield


app = FastAPI(title="TRACEWIRE", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvestigateBody(BaseModel):
    query: str
    take_actions: bool = True


class ToolBody(BaseModel):
    name: str
    arguments: dict = {}


@app.get("/api/health")
def health():
    ok = falkor.ping()
    if not ok:
        raise HTTPException(503, "FalkorDB is down. TRACEWIRE cannot run without the graph.")
    return {"ok": True, "graph": settings.graph_name, "llm": bool(settings.openai_api_key)}


@app.get("/api/overview")
def overview():
    if not falkor.ping():
        raise HTTPException(503, "FalkorDB is down.")
    data = agent.overview()
    data["graph"] = settings.graph_name
    data["llm"] = bool(settings.openai_api_key)
    return data


@app.post("/api/reseed")
def reseed():
    return seed.seed(force=True)


@app.get("/api/tools")
def list_tools():
    return {"tools": tools.TOOLS}


@app.post("/api/tools/call")
def call_tool(body: ToolBody):
    if body.name not in tools.REGISTRY:
        raise HTTPException(400, "unknown tool")
    return {"name": body.name, "result": tools.call(body.name, body.arguments)}


@app.post("/api/investigate")
async def investigate(body: InvestigateBody):
    if not falkor.ping():
        raise HTTPException(503, "FalkorDB is down. The agent has no context layer.")
    if not body.query.strip():
        raise HTTPException(400, "query required")
    return await agent.investigate(body.query.strip(), take_actions=body.take_actions)


@app.post("/api/investigate/stream")
async def investigate_stream(body: InvestigateBody):
    if not falkor.ping():
        raise HTTPException(503, "FalkorDB is down. The agent has no context layer.")
    if not body.query.strip():
        raise HTTPException(400, "query required")

    async def events():
        async for event in agent.investigate_events(body.query.strip(), take_actions=body.take_actions):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/investigations/{inv_id}")
def replay(inv_id: str):
    if not falkor.ping():
        raise HTTPException(503, "FalkorDB is down.")
    data = agent.replay(inv_id)
    if not data:
        raise HTTPException(404, "investigation not in graph")
    return data


@app.get("/api/scene")
def scene():
    if not falkor.ping():
        raise HTTPException(503, "FalkorDB is down.")
    return tools.crime_scene()


@app.get("/mcp/tools")
def mcp_tools():
    """MCP-shaped catalog used by the agent selector and any MCP host."""
    return {
        "protocol": "mcp-http-adapter",
        "tools": [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": {
                    "type": "object",
                    "properties": {k: {"type": "string", "description": v} for k, v in t["input_schema"].items()},
                },
            }
            for t in tools.TOOLS
        ],
    }


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB), name="assets")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")
