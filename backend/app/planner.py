"""Tool selection. Heuristic router always runs; LLM can override when a key exists."""

import json
import re

import httpx

from .config import settings
from .tools import TOOLS

TXN_RE = re.compile(r"TXN-[A-Z0-9-]+", re.I)
ACCT_RE = re.compile(r"\b(V-\d{2}|M-\d{2}|L-\d{2}|C-ALPHA|C-BETA|BR-07)\b", re.I)
DEV_RE = re.compile(r"\b(D-GHOST|D-HOME|D-CAFE|D-BRIDGE)\b", re.I)


def extract_ids(text: str) -> dict:
    txns = [t.upper() for t in TXN_RE.findall(text or "")]
    accts = []
    for m in ACCT_RE.finditer(text or ""):
        u = m.group(0).upper()
        accts.append(u)
    devices = [m.group(0).upper() for m in DEV_RE.finditer(text or "")]
    return {"txns": txns, "accounts": list(dict.fromkeys(accts)), "devices": list(dict.fromkeys(devices))}


def heuristic_plan(query: str) -> list[dict]:
    q = (query or "").lower()
    ids = extract_ids(query)
    steps: list[dict] = []

    if ids["txns"]:
        txn = ids["txns"][0]
        steps.append({"tool": "lookup_txn", "args": {"id": txn}, "reason": "Alert ids are SENT edges. Start there."})
    elif ids.get("devices"):
        steps.append(
            {
                "tool": "detect_rings",
                "args": {"min_size": 3},
                "reason": "A device id is mule infrastructure. Find the shared-device component first.",
            }
        )
    elif ids["accounts"]:
        steps.append(
            {
                "tool": "lookup_account",
                "args": {"id": ids["accounts"][0]},
                "reason": "Named account is the seed node.",
            }
        )
    elif "hub" in q or "pagerank" in q or "collector" in q:
        steps.append({"tool": "rank_hubs", "args": {"limit": 8}, "reason": "PageRank on SENT finds money sinks."})
    elif "ring" in q or "mule" in q or "wcc" in q or "device" in q:
        steps.append({"tool": "detect_rings", "args": {"min_size": 4}, "reason": "WCC + shared device expose mule crews."})
    elif "bridge" in q or "between" in q:
        steps.append({"tool": "bridge_nodes", "args": {"limit": 8}, "reason": "Betweenness finds accounts on many paths."})
    else:
        steps.append({"tool": "search_accounts", "args": {"q": query[:40]}, "reason": "No id. Search the graph."})

    if "path" in q and len(ids["accounts"]) >= 2:
        steps.append(
            {
                "tool": "money_path",
                "args": {"src": ids["accounts"][0], "dst": ids["accounts"][1]},
                "reason": "User asked for a money path. Multi-hop SENT + algo.SPpaths.",
            }
        )
    elif "path" in q and ids["accounts"]:
        steps.append(
            {
                "tool": "money_path",
                "args": {"src": ids["accounts"][0], "dst": "C-ALPHA"},
                "reason": "Path toward Collector Alpha, the PageRank sink in this ledger.",
            }
        )

    if "blast" in q or "freeze" in q or "what breaks" in q:
        seed = ids["accounts"][0] if ids["accounts"] else "C-ALPHA"
        steps.append({"tool": "simulate_freeze", "args": {"id": seed}, "reason": "Counterfactual freeze before writing SET."})
        steps.append({"tool": "blast_radius", "args": {"id": seed}, "reason": "BFS downstream of the freeze candidate."})
    if "cash" in q or "merchant" in q or "kiosk" in q:
        steps.append({"tool": "cash_out", "args": {}, "reason": "PAID edges are the cash-out, not SENT."})
    if "volume" in q or "fan" in q or "inbound" in q:
        steps.append({"tool": "fan_in", "args": {"limit": 8}, "reason": "Inbound SENT volume vs PageRank."})

    if "pagerank" in q and not any(s["tool"] == "rank_hubs" for s in steps):
        steps.append({"tool": "rank_hubs", "args": {"limit": 8}, "reason": "Explicit PageRank request."})

    return steps[:6]


def decide_actions(state: dict) -> list[dict]:
    """Graph-driven actions. Never freeze without structural evidence."""
    actions = []
    txn = state.get("txn") or {}
    neigh = state.get("neighborhood") or {}
    rings = state.get("rings") or {}
    hubs = state.get("hubs") or []
    path = state.get("path") or {}

    device_peers = list(neigh.get("device_peers") or [])
    hops = []
    if path.get("cypher_paths"):
        hops = path["cypher_paths"][0].get("hops") or []

    related = set(state.get("focus_accounts") or [])
    if txn.get("src"):
        related.add(txn["src"])
    if txn.get("dst"):
        related.add(txn["dst"])
    related.update({p.get("id") for p in device_peers if p.get("id")})
    related.update({p.get("id") for p in (neigh.get("out") or []) if p.get("id")})
    related.update({p.get("id") for p in (neigh.get("in") or []) if p.get("id")})
    related.update(hops)
    device_focus = set(state.get("focus_devices") or [])

    if txn.get("found") and txn.get("amount") and txn["amount"] >= 5000:
        dst = txn.get("dst")
        if dst:
            actions.append(
                {
                    "tool": "freeze_account",
                    "args": {"id": dst, "reason": f"Inbound alert {txn.get('txn')} ${txn.get('amount')} into {dst}"},
                    "reason": "High-value alert edge into a first-hop mule.",
                }
            )

    device_rings = rings.get("device_rings") or []
    ghost_members = []
    for dr in device_rings:
        if isinstance(dr, dict) and dr.get("device") == "D-GHOST":
            ghost_members = list(dr.get("members") or [])
    local_ghost = [p for p in device_peers if p.get("device") == "D-GHOST"]
    ghost_on_case = bool(local_ghost) or ("D-GHOST" in device_focus) or bool(related & set(ghost_members))
    if ghost_on_case and (local_ghost or ghost_members):
        actions.append(
            {
                "tool": "flag_device",
                "args": {"id": "D-GHOST", "reason": "Shared device across multiple accounts"},
                "reason": "Same device linking several accounts is mule infrastructure.",
            }
        )
        members = list(dict.fromkeys(ghost_members + [p.get("id") for p in device_peers if p.get("id")]))
        actions.append(
            {
                "tool": "mark_ring",
                "args": {"account_ids": [m for m in members if m][:12], "method": "device", "ring_id": "RING-GHOST"},
                "reason": "Stamp the device component as a ring in the graph.",
            }
        )

    wcc = rings.get("wcc") or []
    if related and wcc and isinstance(wcc[0], dict) and wcc[0].get("members"):
        top = wcc[0]
        members = top.get("members") or []
        if set(members) & related:
            actions.append(
                {
                    "tool": "mark_ring",
                    "args": {"account_ids": members[:16], "method": "wcc", "ring_id": f"RING-WCC-{top.get('componentId')}"},
                    "reason": "This investigation sits inside a weakly connected SENT component.",
                }
            )

    sink = next((h.get("id") for h in hubs[:5] if h.get("kind") == "collector" and h.get("id")), None)
    if not sink and hubs:
        sink = hubs[0].get("id")
    if sink and (sink in related or hops):
        actions.append(
            {
                "tool": "freeze_account",
                "args": {"id": sink, "reason": f"PageRank collector {sink} sits on this investigation's money path"},
                "reason": "Hub score plus path evidence. Freeze the sink, not only the first mule.",
            }
        )

    involved = list(dict.fromkeys([x for x in [txn.get("src"), txn.get("dst"), *hops, *list(related)] if x]))
    if actions and involved:
        actions.append(
            {
                "tool": "open_case",
                "args": {
                    "title": "Night-wire mule cash-out",
                    "severity": "high",
                    "account_ids": involved[:10],
                },
                "reason": "Persist the investigation as a Case node so the next session can resume.",
            }
        )
    return actions[:6]


async def llm_plan(query: str, observations: str) -> list[dict] | None:
    if not settings.openai_api_key:
        return None
    catalog = [{"name": t["name"], "description": t["description"], "input": t["input_schema"]} for t in TOOLS]
    payload = {
        "model": settings.openai_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are TRACEWIRE's tool router. Pick FalkorDB tools only. "
                    "Return JSON {steps:[{tool,args,reason}]}. Never invent graph facts. "
                    "Prefer lookup_txn, neighborhood, money_path, rank_hubs, detect_rings, blast_radius."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"query": query, "tools": catalog, "observations": observations[:4000]}),
            },
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            res = await http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            res.raise_for_status()
            content = res.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            steps = data.get("steps") or []
            allowed = {t["name"] for t in TOOLS}
            clean = []
            for s in steps:
                if s.get("tool") in allowed:
                    clean.append({"tool": s["tool"], "args" : s.get("args") or {}, "reason": s.get("reason") or "llm"})
            return clean[:8] or None
    except Exception:  # noqa: BLE001
        return None
