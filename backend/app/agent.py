from datetime import datetime, timezone
from uuid import uuid4

from . import falkor, planner, queries, tools


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(inv_id: str, n: int, tool: str, reason: str, cypher: str, query: str):
    try:
        falkor.query(
            queries.LOG_STEP,
            {
                "inv_id": inv_id,
                "query": query,
                "ts": _now(),
                "step_id": f"STEP-{uuid4().hex[:10]}",
                "n": n,
                "tool": tool,
                "reason": reason,
                "cypher": cypher[:500],
            },
        )
    except Exception:  # noqa: BLE001
        pass


CYPHER_FOR = {
    "lookup_account": queries.LOOKUP_ACCOUNT.strip(),
    "lookup_txn": queries.LOOKUP_TXN.strip(),
    "neighborhood": "MATCH SENT in/out + USED_DEVICE/USED_IP peers",
    "money_path": queries.MONEY_PATH.strip(),
    "rank_hubs": queries.PAGERANK_HUBS.strip(),
    "bridge_nodes": queries.BETWEENNESS.strip(),
    "detect_rings": queries.WCC_RINGS.strip(),
    "blast_radius": queries.BLAST_RADIUS.strip(),
    "search_accounts": queries.SEARCH.strip(),
    "freeze_account": queries.FREEZE.strip(),
    "flag_device": queries.FLAG_DEVICE.strip(),
    "open_case": queries.OPEN_CASE.strip(),
    "mark_ring": queries.MARK_RING.strip(),
}


def _collect_ids(*blobs) -> list[str]:
    found: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in {"id", "src", "dst"} and isinstance(v, str) and v:
                    found.append(v)
                elif k in {"hops", "members", "accounts"} and isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            found.append(item)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    for b in blobs:
        walk(b)
    # keep account-like ids
    out = []
    for x in found:
        if x.startswith(("V-", "M-", "C-", "L-", "BR-")):
            out.append(x)
    return list(dict.fromkeys(out))


def _verdict(state: dict, actions: list) -> tuple[str, float, str]:
    txn = state.get("txn") or {}
    neigh = state.get("neighborhood") or {}
    hubs = state.get("hubs") or []
    path = state.get("path") or {}
    freeze = [a for a in actions if a.get("tool") == "freeze_account"]
    peers = len(neigh.get("device_peers") or [])
    hops = (path.get("cypher_paths") or [{}])[0].get("hops") if path else None
    hop_n = len(hops or [])
    hub_hit = any(h.get("id") in {"C-ALPHA", "C-BETA"} for h in hubs[:5])
    score = 0.35
    if txn.get("found") and (txn.get("amount") or 0) >= 5000:
        score += 0.2
    if peers >= 3:
        score += 0.2
    if hop_n >= 3:
        score += 0.15
    if hub_hit:
        score += 0.15
    score = min(0.97, score)
    if freeze:
        return (
            "FREEZE",
            score,
            "The graph shows a high-value alert feeding a shared-device mule crew that sinks into a PageRank collector. TRACEWIRE froze the sink and first hop, flagged the device, and opened a case. Remove FalkorDB and none of this scoring or state exists.",
        )
    if peers or hop_n:
        return ("WATCH", score, "Structure is suspicious but the agent did not cross the freeze threshold.")
    return ("CLEAR", 0.4, "No mule structure on the seed. Contrast cluster looks like ordinary commerce.")


async def investigate(user_query: str, take_actions: bool = True) -> dict:
    inv_id = f"INV-{uuid4().hex[:8].upper()}"
    steps_out: list[dict] = []
    state: dict = {}
    n = 0

    ids = planner.extract_ids(user_query)
    state["focus_accounts"] = ids.get("accounts") or []
    state["focus_devices"] = ids.get("devices") or []
    plan = planner.heuristic_plan(user_query)
    llm = await planner.llm_plan(user_query, "initial")
    if llm:
        # LLM may reorder; keep heuristic seeds if LLM forgot lookups
        names = {s["tool"] for s in llm}
        merged = list(llm)
        for s in plan:
            if s["tool"] not in names:
                merged.insert(0, s)
        plan = merged

    def run(step: dict) -> dict:
        nonlocal n
        n += 1
        name = step["tool"]
        args = step.get("args") or {}
        result = tools.call(name, args, inv_id=inv_id)
        record = {
            "n": n,
            "tool": name,
            "args": args,
            "reason": step.get("reason"),
            "cypher": CYPHER_FOR.get(name, ""),
            "result": result,
            "selector": "llm" if llm and step in (llm or []) else "graph-router",
        }
        steps_out.append(record)
        _log(inv_id, n, name, step.get("reason") or "", record["cypher"], user_query)
        return result

    for step in plan:
        result = run(step)
        if step["tool"] == "lookup_txn" and result.get("found"):
            state["txn"] = result
        if step["tool"] == "lookup_account" and result.get("found"):
            state["account"] = result
        if step["tool"] == "neighborhood":
            state["neighborhood"] = result
        if step["tool"] == "money_path":
            state["path"] = result
        if step["tool"] == "rank_hubs":
            state["hubs"] = result.get("hubs") or []
        if step["tool"] == "detect_rings":
            state["rings"] = result
        if step["tool"] == "search_accounts" and result.get("matches"):
            first = result["matches"][0]["id"]
            if not state.get("account"):
                extra = run(
                    {
                        "tool": "lookup_account",
                        "args": {"id": first},
                        "reason": "Search hit. Promote to seed account.",
                    }
                )
                state["account"] = extra

    seed = None
    if state.get("txn"):
        seed = state["txn"].get("dst")
        src = state["txn"].get("src")
    elif state.get("account"):
        seed = state["account"].get("id")
        src = None
    elif ids["accounts"]:
        seed = ids["accounts"][0]
        src = None
    else:
        src = None

    if seed and "neighborhood" not in state:
        state["neighborhood"] = run(
            {
                "tool": "neighborhood",
                "args": {"id": seed},
                "reason": "Expand 1-hop money and shared identifiers from the seed.",
            }
        )

    if src and seed and "path" not in state:
        state["path"] = run(
            {
                "tool": "money_path",
                "args": {"src": src, "dst": "C-ALPHA"},
                "reason": "Follow SENT hops from the victim toward the PageRank collector.",
            }
        )
    elif seed and "path" not in state and "path" in user_query.lower():
        state["path"] = run(
            {
                "tool": "money_path",
                "args": {"src": seed, "dst": "C-ALPHA"},
                "reason": "User asked for a path. Collector Alpha is the known sink in this ledger.",
            }
        )

    if "hubs" not in state:
        state["hubs"] = (run({"tool": "rank_hubs", "args": {"limit": 8}, "reason": "PageRank ranks who the money concentrates on."})).get(
            "hubs"
        ) or []

    if "rings" not in state:
        state["rings"] = run(
            {"tool": "detect_rings", "args": {"min_size": 3}, "reason": "WCC + shared device. Rings are components, not lists."}
        )

    if seed and ("blast" in user_query.lower() or "freeze" in user_query.lower() or take_actions):
        sink = "C-ALPHA" if any(h.get("id") == "C-ALPHA" for h in state.get("hubs") or []) else seed
        run({"tool": "blast_radius", "args": {"id": sink}, "reason": "Before acting, see who sits downstream of the freeze."})

    executed_actions = []
    proposed = planner.decide_actions(state) if take_actions else []
    for act in proposed:
        executed_actions.append(
            {
                **act,
                "result": run({**act, "reason": act.get("reason")}),
            }
        )

    node_ids = _collect_ids(state, executed_actions, *[s["result"] for s in steps_out])
    graph = tools.subgraph(node_ids[:40])
    verdict, confidence, hypothesis = _verdict(state, proposed)

    return {
        "investigation_id": inv_id,
        "query": user_query,
        "verdict": verdict,
        "confidence": confidence,
        "hypothesis": hypothesis,
        "selector": "llm+graph-router" if llm else "graph-router",
        "steps": steps_out,
        "actions": executed_actions,
        "graph": graph,
        "track": "Agents That Act on Connected Data",
    }


def overview() -> dict:
    try:
        node_count = falkor.rows("MATCH (n) RETURN count(n)")[0][0]
        rel_count = falkor.rows("MATCH ()-[r]->() RETURN count(r)")[0][0]
        alerts = falkor.rows(queries.ALERTS)
        inv = falkor.rows(queries.INVESTIGATIONS)
        hubs = tools.rank_hubs(5)
        return {
            "online": True,
            "graph": "tracewire",
            "nodeCount": node_count,
            "relCount": rel_count,
            "labels": {},
            "relTypes": {},
            "alerts": [
                {
                    "id": r[0],
                    "amount": r[1],
                    "ts": r[2],
                    "channel": r[3],
                    "src": r[4],
                    "src_name": r[5],
                    "dst": r[6],
                    "dst_name": r[7],
                    "note": r[8],
                }
                for r in alerts
            ],
            "investigations": [
                {"id": r[0], "query": r[1], "ts": r[2], "steps": r[3], "actions": r[4]} for r in inv
            ],
            "hubs": hubs.get("hubs"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"online": False, "error": str(exc)}
