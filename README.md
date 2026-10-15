# TRACEWIRE

**Graph Hacks track:** Agents That Act on Connected Data  
**Stack:** FalkorDB + Python FastAPI + a single-page operations UI  
**Line:** Follow the money. Freeze the ring.

TRACEWIRE is an investigation agent whose entire brain is a FalkorDB graph. It does not retrieve documents and then “reason.” It selects graph tools (lookups, multi-hop `SENT` paths, PageRank, WCC, BFS), reads what the structure says, then **acts** by writing freezes, device flags, rings, and cases back into the same graph.

Unplug FalkorDB and the product returns `503`. That is the point. [Hackathon rules](https://www.wemakedevs.org/hackathons/falkordb/rules) require the graph to do real work. [Track 01](https://www.wemakedevs.org/hackathons/falkordb) asks for multi-hop reasoning, graph algorithms as tools, MCP-style tool selection, actions from what the graph shows, and explainable results. TRACEWIRE is built against that list.

It is not a chat UI with a graph drawing. Money is `SENT`. The crew is `USED_DEVICE`. PageRank / WCC / BFS are tools. A freeze is a `SET` in FalkorDB. That combination is the bet.

## Demo in 60 seconds

1. Open http://localhost:8080  
2. Click **Investigate TXN-ALERT-1 — $9,400 night wire**  
3. Watch the dossier stream live: `lookup_txn` → `neighborhood` → `pageRank` → `money_path` → `WCC` → `cash_out` → `simulate_freeze` → `BFS` → `SET frozen`  
4. Nodes turn lime when frozen. That freeze is a property on `(:Account)` in FalkorDB. Click a node to investigate it. Prior walks reload from `(:Investigation)` in the graph.  
5. Optional: open FalkorDB Browser at http://localhost:3000, graph name `tracewire`, and run:

```cypher
MATCH (a:Account {frozen: true}) RETURN a.id, a.name, a.kind
```

## Run (Docker)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up --build
```

- App: http://localhost:8080  
- FalkorDB Browser: http://localhost:3000  
- Redis protocol: `localhost:6379`

Optional LLM router (heuristic router always works without it):

```bash
# PowerShell
$env:OPENAI_API_KEY="sk-..."
docker compose up --build
```

## Run without Docker (FalkorDB Cloud + local Python)

The graph lives in [FalkorDB Cloud](https://app.falkordb.cloud). The TRACEWIRE UI still runs on your PC with Python. **ChatGPT’s free website does not plug in.** Leave `OPENAI_API_KEY` empty — the graph router is the real product.

1. Sign up at [app.falkordb.cloud](https://app.falkordb.cloud) and create a **Free** instance. Wait until status is **Running**.
2. Connectivity tab: copy **host** and **port** (port is often not 6379).
3. Instance Details: user is usually `falkordb`. Copy the password.
4. Free tier has **no TLS**. Paid TLS instances need `FALKOR_SSL=true`.
5. In this repo, copy `.env.example` to `.env` and fill:

```
FALKOR_HOST=paste-host
FALKOR_PORT=paste-port
FALKOR_USERNAME=falkordb
FALKOR_PASSWORD=paste-password
FALKOR_SSL=false
GRAPH_NAME=tracewire
OPENAI_API_KEY=
```

6. PowerShell:

```powershell
cd "C:\Users\sonan\OneDrive\Desktop\Graph Hacks\graph-hacks\backend"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

7. Open http://localhost:8080 — status must say **FalkorDB live**. Click **TXN-ALERT-1**.

[Cloud connect docs](https://docs.falkordb.com/cloud/console/connect). Never commit `.env`.

## Run (local Python + Docker FalkorDB)

```bash
docker run -d --name falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080 (UI is served from `../web`).

## Graph model

Full model, algorithms, and the seeded night-wire path: [`queries/GRAPH.md`](queries/GRAPH.md).

Canonical Cypher the agent executes: [`backend/app/queries.py`](backend/app/queries.py).

## Architecture

```
UI  →  FastAPI agent loop  →  tool catalog (MCP-shaped)
                              lookup / path / pageRank / WCC / BFS
                              freeze / flag / case / ring
                         →  FalkorDB graph `tracewire`
```

Tool selection:

- Default: graph-native router in `backend/app/planner.py` (ids, amounts, device overlap).  
- Optional: OpenAI JSON tool picker, still forced to the same catalog.  
- HTTP catalog: `GET /mcp/tools`  
- stdio MCP: `python backend/mcp_server.py`

Actions are Cypher `SET` / `MERGE`, not UI toggles. Investigation steps are stored as `(:Investigation)-[:HAS_STEP]->(:AgentStep)` so a judge can replay why a freeze happened.

## Seeded story (synthetic, no PII)

A fake-invoice victim (`V-03`) wires `$9,400` (`TXN-ALERT-1`) into `M-01`. That mule shares device `D-GHOST` with a crew. Money hops `M-01 → M-04 → C-ALPHA` (PageRank sink) then `C-BETA` and cashes out at `MRCH-NIGHT`. A quiet bakery/gym cluster exists so algorithms have contrast.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | FalkorDB ping |
| GET | `/api/overview` | alerts, counts, PageRank hubs |
| POST | `/api/investigate` | `{ "query", "take_actions" }` |
| POST | `/api/investigate/stream` | Same body, SSE: `start` / `step` / `done` |
| GET | `/api/investigations/{id}` | Replay a walk stored in FalkorDB |
| POST | `/api/reseed` | wipe and reload synthetic ledger |
| GET | `/mcp/tools` | MCP-shaped tool list |
| POST | `/api/tools/call` | run one graph tool |

## Submission checklist

- Track name: **Agents That Act on Connected Data**  
- Public repo: this folder  
- README + graph model: this file + `queries/GRAPH.md`  
- Cypher: `backend/app/queries.py`  
- AI disclosure: `DISCLOSURE.md`  
- Demo video: read [`VIDEO-SCRIPT.md`](VIDEO-SCRIPT.md), then film TXN-ALERT-1  
- Deploy: Docker local is complete; live host is optional

## Credentials you need

| What | Required? | Why |
|---|---|---|
| Docker Desktop | Yes | FalkorDB + app |
| WeMakeDevs account + [registration](https://www.wemakedevs.org/hackathons/falkordb) | Yes | You cannot submit without it |
| GitHub (public repo) | Yes | Rule 10 |
| `OPENAI_API_KEY` | No | Better tool-talk; product is complete without it |
| FalkorDB Cloud | No | Docker is enough. Use Cloud only if you want a public URL |
| Discord | Recommended | [FalkorDB Discord](https://www.wemakedevs.org/hackathons/falkordb) for team / query help |

No production bank data. No personal data. Seed is synthetic.

## What to say to judges

“Agents fail at fraud because the answer is a path, not a document. TRACEWIRE puts payments, devices, and collectors in FalkorDB, uses PageRank and WCC as tools, then freezes nodes in the same graph. The dossier is the query log. The lime nodes are writes.”
