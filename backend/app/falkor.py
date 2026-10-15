import time
from typing import Any

from falkordb import FalkorDB

from .config import settings

_client: FalkorDB | None = None


def connect(retries: int = 30, delay: float = 1.0) -> FalkorDB:
    global _client
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            client = FalkorDB(host=settings.falkor_host, port=settings.falkor_port)
            conn = getattr(client, "connection", None)
            if conn is not None and hasattr(conn, "ping"):
                conn.ping()
            else:
                client.select_graph(settings.graph_name).query("RETURN 1")
            _client = client
            return client
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(delay)
    raise RuntimeError(f"Cannot reach FalkorDB at {settings.falkor_host}:{settings.falkor_port}: {last_err}")


def client() -> FalkorDB:
    if _client is None:
        return connect()
    return _client


def graph():
    return client().select_graph(settings.graph_name)


def query(cypher: str, params: dict[str, Any] | None = None):
    return graph().query(cypher, params or {})


def rows(cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    return query(cypher, params).result_set


def ping() -> bool:
    try:
        query("RETURN 1")
        return True
    except Exception:  # noqa: BLE001
        return False


def serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    labels = getattr(value, "labels", None)
    props = getattr(value, "properties", None)
    if labels is not None and props is not None:
        return {"labels": list(labels), "properties": dict(props), "id": getattr(value, "id", None)}
    relation = getattr(value, "relation", None)
    if relation is not None and props is not None:
        return {
            "type": relation,
            "properties": dict(props),
            "src": getattr(value, "src_node", None),
            "dst": getattr(value, "dest_node", None),
        }
    nodes = getattr(value, "nodes", None)
    edges = getattr(value, "edges", None)
    if callable(nodes) or nodes is not None:
        try:
            nlist = nodes() if callable(nodes) else nodes
            elist = edges() if callable(edges) else (edges or [])
            return {"nodes": [serialize(n) for n in nlist], "edges": [serialize(e) for e in elist]}
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)
