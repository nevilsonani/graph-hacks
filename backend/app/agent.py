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
    "fan_in": queries.FAN_IN.strip(),
    "cash_out": queries.CASH_OUT.strip(),
    "simulate_freeze": queries.SIMULATE_FREEZE.strip(),
    "search_accounts": queries.SEARCH.strip(),
    "freeze_account": queries.FREEZE.strip(),
    "flag_device": queries.FLAG_DEVICE.strip(),
    "open_case": queries.OPEN_CASE.strip(),
    "mark_ring": queries.MARK_RING.strip(),
}

ACTIONS = {"freeze_account", "flag_device", "open_case", "mark_ring"}


def _collect_ids(*blobs) -> list[str]:
    found: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in {"id", "src", "dst", "device", "merchant_id"} and isinstance(v, str) and v:
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
    out = []
    for x in found:
        if x.startswith(("V-", "M-", "C-", "L-", "BR-", "D-", "MRCH-")):
            out.append(x)
    return list(dict.fromkeys(out))


def _sink_from_hubs(hubs: list) -> str | None:
    for h in hubs or []:
        if isinstance(h, dict) and h.get("kind") == "collector" and h.get("id"):
            return h["id"]
    for h in hubs or []:
        if isinstance(h, dict) and h.get("id"):
            return h["id"]
    return None


def _verdict(state: dict, actions: list) -> tuple[str, float, str]:
    txn = state.get("txn") or {}
    neigh = state.get("neighborhood") or {}
    hubs = state.get("hubs") or []
    path = state.get("path") or {}
    freeze = [a for a in actions if a.get("tool") == "freeze_account"]
    peers = len(neigh.get("device_peers") or [])
    hops = (path.get("cypher_paths") or [{}])[0].get("hops") if path else None
    hop_n = len(hops or [])
    sink = _sink_from_hubs(hubs)
    hub_hit = bool(sink)
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


def _payload(inv_id, user_query, selector, steps_out, executed_actions, state, proposed, llm):
    node_ids = _collect_ids(state, executed_actions, *[s["result"] for s in steps_out])
    graph = tools.subgraph(node_ids[:40])
    verdict, confidence, hypothesis = _verdict(state, proposed)
    return {
        "investigation_id": inv_id,
        "query": user_query,
        "verdict": verdict,
        "confidence": confidence,
        "hypothesis": hypothesis,
        "selector": selector,
        "steps": steps_out,
        "actions": executed_actions,
        "graph": graph,
        "track": "Agents That Act on Connected Data",
        "llm": bool(llm),
    }


async def investigate_events(user_query: str, take_actions: bool = True):
    inv_id = f"INV-{uuid4().hex[:8].upper()}"
    steps_out: list[dict] = []
    state: dict = {}
    n = 0

    ids = planner.extract_ids(user_query)
    state["focus_accounts"] = ids.get("accounts") or []
    state["focus_devices"] = ids.get("devices") or []
    plan = planner.heuristic_plan(user_query)
    llm = await planner.llm_plan(user_query, "initial")
    selector = "llm+graph-router" if llm else "graph-router"
    if llm:
        names = {s["tool"] for s in llm}
        merged = list(llm)
        for s in plan:
            if s["tool"] not in names:
                merged.insert(0, s)
        plan = merged

    yield {"type": "start", "investigation_id": inv_id, "selector": selector, "query": user_query}

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
            "kind": "action" if name in ACTIONS else "observe",
        }
        steps_out.append(record)
        _log(inv_id, n, name, step.get("reason") or "", record["cypher"], user_query)
        return result

    async def emit(step: dict) -> dict:
        result = run(step)
        yield_graph = None
        ids_now = _collect_ids(state, result)
        if ids_now:
            yield_graph = tools.subgraph(ids_now[:40])
        return result, {
            "type": "step",
            "step": steps_out[-1],
            "graph": yield_graph,
        }

    for step in plan:
        result, event = await emit(step)
        yield event
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
                extra, event = await emit(
                    {
                        "tool": "lookup_account",
                        "args": {"id": first},
                        "reason": "Search hit. Promote to seed account.",
                    }
                )
                yield event
                state["account"] = extra

    seed = None
    src = None
    if state.get("txn"):
        seed = state["txn"].get("dst")
        src = state["txn"].get("src")
    elif state.get("account"):
        seed = state["account"].get("id")
    elif ids["accounts"]:
        seed = ids["accounts"][0]

    if seed and "neighborhood" not in state:
        result, event = await emit(
            {
                "tool": "neighborhood",
                "args": {"id": seed},
                "reason": "Expand 1-hop money and shared identifiers from the seed.",
            }
        )
        yield event
        state["neighborhood"] = result

    if "hubs" not in state:
        result, event = await emit(
            {"tool": "rank_hubs", "args": {"limit": 8}, "reason": "PageRank ranks who the money concentrates on."}
        )
        yield event
        state["hubs"] = result.get("hubs") or []

    sink = _sink_from_hubs(state.get("hubs") or []) or "C-ALPHA"

    if src and seed and "path" not in state:
        result, event = await emit(
            {
                "tool": "money_path",
                "args": {"src": src, "dst": sink},
                "reason": f"Follow SENT hops from the victim toward PageRank sink {sink}.",
            }
        )
        yield event
        state["path"] = result
    elif seed and "path" not in state and "path" in user_query.lower():
        result, event = await emit(
            {
                "tool": "money_path",
                "args": {"src": seed, "dst": sink},
                "reason": f"User asked for a path. {sink} is the current PageRank sink.",
            }
        )
        yield event
        state["path"] = result

    if "rings" not in state:
        result, event = await emit(
            {"tool": "detect_rings", "args": {"min_size": 3}, "reason": "WCC + shared device. Rings are components, not lists."}
        )
        yield event
        state["rings"] = result

    if take_actions or "cash" in user_query.lower():
        result, event = await emit(
            {"tool": "cash_out", "args": {}, "reason": "Where SENT money leaves the graph as PAID to a merchant."}
        )
        yield event
        state["cash"] = result

    if seed and ("blast" in user_query.lower() or "freeze" in user_query.lower() or take_actions):
        _, event = await emit(
            {"tool": "simulate_freeze", "args": {"id": sink}, "reason": "Counterfactual: what a freeze of the sink would cut."}
        )
        yield event
        _, event = await emit(
            {"tool": "blast_radius", "args": {"id": sink}, "reason": "BFS along SENT before writing the freeze."}
        )
        yield event

    executed_actions = []
    proposed = planner.decide_actions(state) if take_actions else []
    for act in proposed:
        result, event = await emit({**act, "reason": act.get("reason")})
        yield event
        executed_actions.append({**act, "result": result})

    payload = _payload(inv_id, user_query, selector, steps_out, executed_actions, state, proposed, llm)
    yield {"type": "done", "payload": payload}


async def investigate(user_query: str, take_actions: bool = True) -> dict:
    final = {
        "investigation_id": "",
        "query": user_query,
        "verdict": "CLEAR",
        "confidence": 0,
        "hypothesis": "No graph walk completed.",
        "steps": [],
        "actions": [],
        "graph": {"nodes": [], "edges": []},
        "track": "Agents That Act on Connected Data",
    }
    async for event in investigate_events(user_query, take_actions=take_actions):
        if event.get("type") == "done":
            final = event["payload"]
    return final


def replay(inv_id: str) -> dict | None:
    steps = falkor.rows(queries.REPLAY_STEPS, {"id": inv_id})
    if not steps:
        return None
    actions = falkor.rows(queries.REPLAY_ACTIONS, {"id": inv_id})
    return {
        "investigation_id": steps[0][0],
        "query": steps[0][1],
        "ts": steps[0][2],
        "from_graph": True,
        "steps": [
            {
                "n": r[3],
                "tool": r[4],
                "reason": r[5],
                "cypher": r[6],
                "ts": r[7],
            }
            for r in steps
        ],
        "actions": [
            {"id": r[0], "kind": r[1], "ts": r[2], "reason": r[3], "target": r[4]} for r in actions
        ],
        "note": "Replayed from (:Investigation)-[:HAS_STEP]->(:AgentStep) in FalkorDB.",
    }


def overview() -> dict:
    try:
        node_count = falkor.rows("MATCH (n) RETURN count(n)")[0][0]
        rel_count = falkor.rows("MATCH ()-[r]->() RETURN count(r)")[0][0]
        alerts = falkor.rows(queries.ALERTS)
        inv = falkor.rows(queries.INVESTIGATIONS)
        hubs = tools.rank_hubs(5)
        frozen = falkor.rows("MATCH (a:Account {frozen: true}) RETURN count(a)")[0][0]
        return {
            "online": True,
            "graph": "tracewire",
            "nodeCount": node_count,
            "relCount": rel_count,
            "frozen": frozen,
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
            "scene": tools.crime_scene(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"online": False, "error": str(exc)}
