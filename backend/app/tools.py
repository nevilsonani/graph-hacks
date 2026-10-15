from datetime import datetime, timezone
from uuid import uuid4

from . import falkor, queries

TOOLS = [
    {
        "name": "lookup_account",
        "description": "Load an account and the devices, IPs, and cards it uses.",
        "input_schema": {"id": "account id such as V-03 or C-ALPHA"},
    },
    {
        "name": "lookup_txn",
        "description": "Load a payment by transaction id such as TXN-ALERT-1.",
        "input_schema": {"id": "transaction id"},
    },
    {
        "name": "neighborhood",
        "description": "1-hop money and shared-device/IP/card peers for an account.",
        "input_schema": {"id": "account id"},
    },
    {
        "name": "money_path",
        "description": "Multi-hop SENT path between two accounts. Uses Cypher variable-length match plus algo.SPpaths.",
        "input_schema": {"src": "source account", "dst": "destination account"},
    },
    {
        "name": "rank_hubs",
        "description": "PageRank on Account-SENT to find collectors and mule sinks.",
        "input_schema": {"limit": "integer, default 8"},
    },
    {
        "name": "bridge_nodes",
        "description": "Betweenness centrality — accounts that sit on many money paths.",
        "input_schema": {"limit": "integer, default 8"},
    },
    {
        "name": "detect_rings",
        "description": "Weakly connected components on SENT plus shared-device rings.",
        "input_schema": {"min_size": "integer, default 4"},
    },
    {
        "name": "blast_radius",
        "description": "Who still gets paid if this account is frozen. BFS along SENT.",
        "input_schema": {"id": "account id"},
    },
    {
        "name": "fan_in",
        "description": "Accounts by inbound SENT volume. Complements PageRank with raw money flow.",
        "input_schema": {"limit": "integer, default 8"},
    },
    {
        "name": "cash_out",
        "description": "PAID edges into merchants — where the ring turns graph money into goods.",
        "input_schema": {},
    },
    {
        "name": "simulate_freeze",
        "description": "Counterfactual: who sits downstream of this account if we freeze it. Read-only.",
        "input_schema": {"id": "account id"},
    },
    {
        "name": "search_accounts",
        "description": "Find accounts by id fragment or name.",
        "input_schema": {"q": "search string"},
    },
    {
        "name": "freeze_account",
        "description": "ACTION: freeze an account in the graph. The product state changes.",
        "input_schema": {"id": "account id", "reason": "why"},
    },
    {
        "name": "flag_device",
        "description": "ACTION: flag a device and every account that used it.",
        "input_schema": {"id": "device id", "reason": "why"},
    },
    {
        "name": "open_case",
        "description": "ACTION: open a Case node linked to involved accounts.",
        "input_schema": {"title": "string", "severity": "high|medium", "account_ids": "list"},
    },
    {
        "name": "mark_ring",
        "description": "ACTION: stamp a mule ring onto accounts after WCC/device evidence.",
        "input_schema": {"account_ids": "list", "ring_id": "string", "method": "wcc|device"},
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table(result, keys: list[str]) -> list[dict]:
    out = []
    for row in result:
        item = {}
        for i, key in enumerate(keys):
            item[key] = falkor.serialize(row[i]) if i < len(row) else None
        out.append(item)
    return out


def lookup_account(id: str, **_) -> dict:
    rows = falkor.rows(queries.LOOKUP_ACCOUNT, {"id": id})
    if not rows:
        return {"found": False, "id": id}
    r = rows[0]
    return {
        "found": True,
        "id": r[0],
        "name": r[1],
        "kind": r[2],
        "country": r[3],
        "kyc": r[4],
        "risk": r[5],
        "frozen": r[6],
        "flagged": r[7],
        "devices": r[8],
        "ips": r[9],
        "cards": r[10],
    }


def lookup_txn(id: str, **_) -> dict:
    rows = falkor.rows(queries.LOOKUP_TXN, {"id": id})
    if not rows:
        return {"found": False, "id": id}
    r = rows[0]
    return {
        "found": True,
        "txn": r[0],
        "amount": r[1],
        "ts": r[2],
        "channel": r[3],
        "src": r[4],
        "src_name": r[5],
        "dst": r[6],
        "dst_name": r[7],
        "merchant_id": r[8],
        "merchant": r[9],
    }


def neighborhood(id: str, **_) -> dict:
    outs = falkor.rows(
        """
        MATCH (a:Account {id:$id})-[s:SENT]->(b:Account)
        RETURN b.id, b.name, s.amount, s.id, s.channel
        ORDER BY s.amount DESC LIMIT 16
        """,
        {"id": id},
    )
    ins = falkor.rows(
        """
        MATCH (b:Account)-[s:SENT]->(a:Account {id:$id})
        RETURN b.id, b.name, s.amount, s.id, s.channel
        ORDER BY s.amount DESC LIMIT 16
        """,
        {"id": id},
    )
    device_peers = falkor.rows(
        """
        MATCH (a:Account {id:$id})-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(b:Account)
        WHERE b.id <> $id
        RETURN DISTINCT d.id, b.id, b.name
        """,
        {"id": id},
    )
    ip_peers = falkor.rows(
        """
        MATCH (a:Account {id:$id})-[:USED_IP]->(ip:IP)<-[:USED_IP]-(b:Account)
        WHERE b.id <> $id
        RETURN DISTINCT ip.addr, b.id, b.name
        """,
        {"id": id},
    )
    return {
        "id": id,
        "out": [{"id": r[0], "name": r[1], "amount": r[2], "txn": r[3], "channel": r[4]} for r in outs],
        "in": [{"id": r[0], "name": r[1], "amount": r[2], "txn": r[3], "channel": r[4]} for r in ins],
        "device_peers": [{"device": r[0], "id": r[1], "name": r[2]} for r in device_peers],
        "ip_peers": [{"ip": r[0], "id": r[1], "name": r[2]} for r in ip_peers],
    }


def money_path(src: str, dst: str, **_) -> dict:
    try:
        hops = falkor.rows(queries.MONEY_PATH, {"src": src, "dst": dst})
    except Exception:  # noqa: BLE001
        hops = falkor.rows(
            """
            MATCH (src:Account {id: $src}), (dst:Account {id: $dst})
            MATCH p = (src)-[:SENT*1..6]->(dst)
            RETURN [n IN nodes(p) | n.id] AS hops,
                   [r IN relationships(p) | r.amount] AS amounts,
                   [r IN relationships(p) | r.id] AS txns,
                   length(p) AS hops_n
            ORDER BY hops_n ASC
            LIMIT 5
            """,
            {"src": src, "dst": dst},
        )
    paths = [
        {
            "hops": r[0],
            "amounts": r[1],
            "txns": r[2],
            "length": r[3],
            "volume": r[4] if len(r) > 4 else None,
        }
        for r in hops
    ]
    sp = []
    try:
        sp_rows = falkor.rows(queries.SP_PATH, {"src": src, "dst": dst})
        sp = [{"hops": r[0], "weight": r[1]} for r in sp_rows]
    except Exception as exc:  # noqa: BLE001
        sp = [{"error": str(exc)}]
    return {"src": src, "dst": dst, "cypher_paths": paths, "algo_sppaths": sp}


def rank_hubs(limit: int = 8, **_) -> dict:
    rows = falkor.rows(queries.PAGERANK_HUBS, {"limit": int(limit)})
    return {"algorithm": "algo.pageRank", "hubs": _table(rows, ["id", "name", "kind", "score"])}


def bridge_nodes(limit: int = 8, **_) -> dict:
    try:
        rows = falkor.rows(queries.BETWEENNESS, {"limit": int(limit)})
        return {"algorithm": "algo.betweenness", "bridges": _table(rows, ["id", "name", "score"])}
    except Exception as exc:  # noqa: BLE001
        return {"algorithm": "algo.betweenness", "error": str(exc), "bridges": []}


def detect_rings(min_size: int = 4, **_) -> dict:
    wcc = []
    try:
        rows = falkor.rows(queries.WCC_RINGS, {"min_size": int(min_size)})
        wcc = _table(rows, ["componentId", "size", "members"])
    except Exception as exc:  # noqa: BLE001
        wcc = [{"error": str(exc)}]
    devices = []
    try:
        drows = falkor.rows(queries.DEVICE_RINGS)
        devices = _table(drows, ["device", "size", "members"])
    except Exception as exc:  # noqa: BLE001
        devices = [{"error": str(exc)}]
    return {"algorithm": "algo.WCC + shared device", "wcc": wcc, "device_rings": devices}


def blast_radius(id: str, **_) -> dict:
    try:
        rows = falkor.rows(queries.BLAST_RADIUS, {"id": id})
        downstream = _table(rows, ["id", "name", "kind", "frozen"])
        return {"algorithm": "algo.BFS", "seed": id, "downstream": downstream}
    except Exception:
        rows = falkor.rows(queries.BLAST_RADIUS_FALLBACK, {"id": id})
        return {
            "algorithm": "SENT*1..3 fallback",
            "seed": id,
            "downstream": _table(rows, ["id", "name", "kind", "frozen"]),
        }


def search_accounts(q: str, **_) -> dict:
    rows = falkor.rows(queries.SEARCH, {"q": q})
    return {"matches": _table(rows, ["id", "name", "kind", "risk", "frozen"])}


def fan_in(limit: int = 8, **_) -> dict:
    rows = falkor.rows(queries.FAN_IN, {"limit": int(limit)})
    return {
        "algorithm": "inbound SENT volume",
        "sinks": _table(rows, ["id", "name", "kind", "inbound", "volume", "frozen"]),
    }


def cash_out(**_) -> dict:
    rows = falkor.rows(queries.CASH_OUT)
    return {
        "exits": [
            {
                "account": r[0],
                "name": r[1],
                "kind": r[2],
                "txn": r[3],
                "amount": r[4],
                "ts": r[5],
                "merchant_id": r[6],
                "merchant": r[7],
                "merchant_risk": r[8],
            }
            for r in rows
        ]
    }


def simulate_freeze(id: str, **_) -> dict:
    try:
        rows = falkor.rows(queries.SIMULATE_FREEZE, {"id": id})
    except Exception:  # noqa: BLE001
        rows = falkor.rows(
            """
            MATCH (seed:Account {id: $id})
            OPTIONAL MATCH (seed)-[:SENT*1..4]->(n:Account)
            RETURN seed.id, seed.name, seed.kind, seed.frozen, collect(DISTINCT n.id)
            """,
            {"id": id},
        )
    if not rows:
        return {"found": False, "id": id}
    r = rows[0]
    raw = r[4] or []
    if raw and isinstance(raw[0], dict):
        downstream = [x for x in raw if x and x.get("id")]
    else:
        downstream = [{"id": x} for x in raw if x]
    return {
        "found": True,
        "seed": {"id": r[0], "name": r[1], "kind": r[2], "already_frozen": r[3]},
        "would_cut": downstream,
        "cut_count": len(downstream),
        "note": "Read-only counterfactual. No SET. freeze_account is the write.",
    }


def freeze_account(id: str, reason: str = "", inv_id: str = "", **_) -> dict:
    rows = falkor.rows(
        queries.FREEZE,
        {
            "id": id,
            "reason": reason or "agent freeze",
            "ts": _now(),
            "action_id": f"ACT-{uuid4().hex[:8]}",
            "inv_id": inv_id or "INV-anon",
        },
    )
    if not rows:
        return {"ok": False, "id": id}
    return {"ok": True, "id": rows[0][0], "frozen": rows[0][1], "reason": reason}


def flag_device(id: str, reason: str = "", inv_id: str = "", **_) -> dict:
    rows = falkor.rows(
        queries.FLAG_DEVICE,
        {
            "id": id,
            "reason": reason or "shared mule device",
            "ts": _now(),
            "action_id": f"ACT-{uuid4().hex[:8]}",
            "inv_id": inv_id or "INV-anon",
        },
    )
    if not rows:
        return {"ok": False, "id": id}
    return {"ok": True, "device": rows[0][0], "accounts": rows[0][1], "reason": reason}


def open_case(title: str, severity: str = "high", account_ids: list | None = None, inv_id: str = "", **_) -> dict:
    ids = account_ids or []
    rows = falkor.rows(
        queries.OPEN_CASE,
        {
            "case_id": f"CASE-{uuid4().hex[:6].upper()}",
            "title": title,
            "severity": severity,
            "ts": _now(),
            "inv_id": inv_id or "INV-anon",
            "account_ids": ids,
        },
    )
    if not rows:
        return {"ok": False}
    return {"ok": True, "case": rows[0][0], "title": rows[0][1], "severity": rows[0][2]}


def mark_ring(account_ids: list | None = None, ring_id: str = "", method: str = "wcc", inv_id: str = "", **_) -> dict:
    ids = account_ids or []
    rid = ring_id or f"RING-{uuid4().hex[:5].upper()}"
    rows = falkor.rows(
        queries.MARK_RING,
        {"account_ids": ids, "ring_id": rid, "method": method, "inv_id": inv_id or "INV-anon"},
    )
    if not rows:
        return {"ok": False}
    return {"ok": True, "ring": rows[0][0], "size": rows[0][1]}


def subgraph(ids: list[str]) -> dict:
    if not ids:
        return {"nodes": [], "edges": []}
    nodes = []
    for r in falkor.rows(queries.SUBGRAPH_NODES, {"ids": ids}):
        nodes.append(
            {
                "id": r[0],
                "name": r[1],
                "kind": r[2],
                "risk": r[3],
                "frozen": r[4],
                "flagged": r[5],
                "type": "account",
            }
        )
    edges = []
    for r in falkor.rows(queries.SUBGRAPH_EDGES, {"ids": ids}):
        edges.append(
            {
                "source": r[0],
                "target": r[1],
                "amount": r[2],
                "id": r[3],
                "channel": r[4],
                "kind": "SENT",
            }
        )
    try:
        for r in falkor.rows(queries.SUBGRAPH_DEVICES, {"ids": ids}):
            nodes.append(
                {
                    "id": r[0],
                    "name": r[1],
                    "kind": "device",
                    "flagged": r[2],
                    "frozen": False,
                    "type": "device",
                }
            )
        for r in falkor.rows(queries.SUBGRAPH_DEVICE_EDGES, {"ids": ids}):
            edges.append({"source": r[0], "target": r[1], "kind": "USED_DEVICE"})
        for r in falkor.rows(queries.SUBGRAPH_PAY, {"ids": ids}):
            nodes.append(
                {
                    "id": r[1],
                    "name": r[2],
                    "kind": "merchant",
                    "risk": r[5],
                    "frozen": False,
                    "type": "merchant",
                }
            )
            edges.append(
                {
                    "source": r[0],
                    "target": r[1],
                    "amount": r[3],
                    "id": r[4],
                    "kind": "PAID",
                }
            )
    except Exception:  # noqa: BLE001
        pass
    # de-dupe nodes
    uniq = {}
    for n in nodes:
        uniq[n["id"]] = n
    return {"nodes": list(uniq.values()), "edges": edges}


def crime_scene() -> dict:
    nodes = []
    for r in falkor.rows(queries.CRIME_ACCOUNTS):
        nodes.append(
            {
                "id": r[0],
                "name": r[1],
                "kind": r[2],
                "risk": r[3],
                "frozen": r[4],
                "flagged": r[5],
                "type": "account",
            }
        )
    edges = []
    for r in falkor.rows(queries.CRIME_EDGES):
        edges.append(
            {
                "source": r[0],
                "target": r[1],
                "amount": r[2],
                "id": r[3],
                "channel": r[4],
                "alert": r[5],
                "kind": "SENT",
            }
        )
    try:
        for r in falkor.rows(queries.CRIME_DEVICES):
            nodes.append(
                {
                    "id": r[0],
                    "name": r[1],
                    "kind": "device",
                    "flagged": r[2],
                    "frozen": False,
                    "type": "device",
                    "accounts": r[3],
                }
            )
            for aid in r[3] or []:
                edges.append({"source": aid, "target": r[0], "kind": "USED_DEVICE"})
    except Exception:  # noqa: BLE001
        pass
    uniq = {}
    for n in nodes:
        uniq[n["id"]] = n
    return {"nodes": list(uniq.values()), "edges": edges}


REGISTRY = {
    "lookup_account": lookup_account,
    "lookup_txn": lookup_txn,
    "neighborhood": neighborhood,
    "money_path": money_path,
    "rank_hubs": rank_hubs,
    "bridge_nodes": bridge_nodes,
    "detect_rings": detect_rings,
    "blast_radius": blast_radius,
    "fan_in": fan_in,
    "cash_out": cash_out,
    "simulate_freeze": simulate_freeze,
    "search_accounts": search_accounts,
    "freeze_account": freeze_account,
    "flag_device": flag_device,
    "open_case": open_case,
    "mark_ring": mark_ring,
}


def call(name: str, arguments: dict, inv_id: str = "") -> dict:
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    args = dict(arguments or {})
    for key in ("limit", "min_size"):
        if key in args and args[key] not in (None, ""):
            try:
                args[key] = int(args[key])
            except (TypeError, ValueError):
                args.pop(key, None)
    if name in {"freeze_account", "flag_device", "open_case", "mark_ring"}:
        args["inv_id"] = inv_id
    try:
        return fn(**args)
    except TypeError as exc:
        return {"error": str(exc), "tool": name}
