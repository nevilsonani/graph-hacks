"""Synthetic payment graph. Every alert in the UI is a real path in this data."""

import time

from . import falkor

GRAPH_STORY = {
    "name": "TRACEWIRE synthetic ledger",
    "note": "No real PII. Named after public-domain archetypes.",
}


def _q(cypher: str, params: dict | None = None):
    return falkor.query(cypher, params)


def seed(force: bool = False) -> dict:
    g = falkor.graph()
    try:
        existing = _q("MATCH (n) RETURN count(n)").result_set
    except Exception:  # noqa: BLE001
        existing = [[0]]
    if existing and existing[0][0] and not force:
        return {"seeded": False, "nodes": existing[0][0]}

    try:
        g.delete()
    except Exception:  # noqa: BLE001
        pass

    falkor.reset()
    time.sleep(1)
    g = falkor.graph()

    _q(
        """
        CREATE (:Meta {
          id: 'tracewire',
          title: 'TRACEWIRE synthetic ledger',
          generated: 'hackathon-synthetic',
          story: 'Night-wire mule ring cashing out through a front merchant'
        })
        """
    )

    accounts = [
        ("V-01", "Amina Cole", "victim", "US", "full", 22),
        ("V-02", "Ravi Shah", "victim", "US", "full", 18),
        ("V-03", "Elena Voss", "victim", "DE", "full", 31),
        ("V-04", "Jonah Park", "victim", "US", "full", 14),
        ("M-01", "Northline LLC", "mule", "US", "thin", 71),
        ("M-02", "QuickShift Co", "mule", "US", "thin", 68),
        ("M-03", "Harbor Pay", "mule", "CY", "thin", 74),
        ("M-04", "Nimbus Goods", "mule", "US", "thin", 77),
        ("M-05", "Velvet Route", "mule", "LT", "thin", 69),
        ("M-06", "Amber Relay", "mule", "US", "thin", 72),
        ("M-07", "Pebble Mint", "mule", "GB", "thin", 66),
        ("M-08", "Cinder Desk", "mule", "US", "thin", 70),
        ("C-ALPHA", "Collector Alpha", "collector", "AE", "shell", 88),
        ("C-BETA", "Night Desk Ltd", "collector", "HK", "shell", 81),
        ("BR-07", "Bridge Seven", "bridge", "SG", "full", 54),
        ("L-11", "Helio Bakery", "legit", "US", "full", 8),
        ("L-12", "Oak Street Books", "legit", "US", "full", 6),
        ("L-13", "Marlow Clinic", "legit", "US", "full", 9),
        ("L-14", "Kite Courier", "legit", "US", "full", 11),
        ("L-15", "Pine & Co", "legit", "US", "full", 7),
        ("L-16", "Sable Studio", "legit", "GB", "full", 10),
        ("L-17", "North Gym", "legit", "US", "full", 5),
        ("L-18", "River Teeth", "legit", "US", "full", 12),
        ("L-19", "Goldfinch Lab", "legit", "DE", "full", 9),
        ("L-20", "Copper Yarn", "legit", "US", "full", 4),
    ]

    _q(
        """
        UNWIND $rows AS r
        CREATE (:Account {
          id: r.id, name: r.name, kind: r.kind, country: r.country,
          kyc: r.kyc, risk: r.risk, frozen: false, flagged: false, ring: ''
        })
        """,
        {
            "rows": [
                {
                    "id": aid,
                    "name": name,
                    "kind": kind,
                    "country": country,
                    "kyc": kyc,
                    "risk": risk,
                }
                for aid, name, kind, country, kyc, risk in accounts
            ]
        },
    )

    devices = [
        ("D-GHOST", "iOS 19 / Graphene"),
        ("D-HOME", "Pixel legit"),
        ("D-CAFE", "shared cafe kiosk"),
        ("D-BRIDGE", "work laptop"),
    ]
    _q(
        "UNWIND $rows AS r CREATE (:Device {id: r.id, label: r.label, flagged: false})",
        {"rows": [{"id": did, "label": label} for did, label in devices]},
    )

    ips = [("185.22.9.4", "CY"), ("8.8.4.12", "US"), ("102.44.1.9", "AE"), ("73.11.2.8", "US")]
    _q(
        "UNWIND $rows AS r CREATE (:IP {addr: r.addr, country: r.country})",
        {"rows": [{"addr": addr, "country": country} for addr, country in ips]},
    )

    cards = [("CARD-4412", "visa"), ("CARD-9981", "mc"), ("CARD-1100", "visa")]
    _q(
        "UNWIND $rows AS r CREATE (:Card {id: r.id, brand: r.brand})",
        {"rows": [{"id": cid, "brand": brand} for cid, brand in cards]},
    )

    _q(
        """
        CREATE (:Merchant {id: 'MRCH-NIGHT', name: 'Night Kiosk Electronics', mcc: '5732', risk: 91})
        CREATE (:Merchant {id: 'MRCH-OAK', name: 'Oak Street Books', mcc: '5942', risk: 4})
        CREATE (:Merchant {id: 'MRCH-GYM', name: 'North Gym', mcc: '7997', risk: 3})
        """
    )

    _q(
        """
        UNWIND $rows AS r
        MATCH (a:Account {id: r.a}), (d:Device {id: r.d})
        MERGE (a)-[:USED_DEVICE]->(d)
        """,
        {
            "rows": (
                [{"a": m, "d": "D-GHOST"} for m in ["M-01", "M-02", "M-03", "M-04", "M-05", "M-06", "M-07"]]
                + [{"a": v, "d": "D-HOME"} for v in ["V-01", "V-02", "V-03", "V-04", "L-11", "L-12", "L-13", "L-14", "L-15"]]
                + [{"a": "C-ALPHA", "d": "D-CAFE"}, {"a": "BR-07", "d": "D-BRIDGE"}, {"a": "M-08", "d": "D-CAFE"}]
            )
        },
    )
    _q(
        """
        UNWIND $rows AS r
        MATCH (a:Account {id: r.a}), (i:IP {addr: r.ip})
        MERGE (a)-[:USED_IP]->(i)
        """,
        {
            "rows": (
                [{"a": m, "ip": "185.22.9.4"} for m in ["M-01", "M-02", "M-03", "M-04", "M-05", "M-06"]]
                + [{"a": v, "ip": "73.11.2.8"} for v in ["V-01", "V-02", "V-03", "V-04", "L-11", "L-12", "L-13", "L-14", "L-15"]]
                + [{"a": "C-ALPHA", "ip": "102.44.1.9"}]
            )
        },
    )
    _q(
        """
        UNWIND $rows AS r
        MATCH (a:Account {id: r.a}), (c:Card {id: r.c})
        MERGE (a)-[:USED_CARD]->(c)
        """,
        {
            "rows": (
                [{"a": m, "c": "CARD-4412"} for m in ["M-01", "M-02", "M-03", "M-04", "M-05", "M-06"]]
                + [{"a": v, "c": "CARD-1100"} for v in ["V-01", "V-02", "V-03", "V-04"]]
            )
        },
    )

    wires = [
        ("V-03", "M-01", 9400, "2026-10-15T02:11:00Z", "ach", "TXN-ALERT-1", True, "victim wire after fake invoice"),
        ("V-01", "M-02", 8100, "2026-10-15T02:14:00Z", "ach", "TXN-ALERT-2", True, "same device cluster inbound"),
        ("V-04", "M-03", 7600, "2026-10-15T02:18:00Z", "wire", "TXN-9101", False, ""),
        ("M-01", "M-04", 9100, "2026-10-15T03:02:00Z", "p2p", "TXN-9102", False, ""),
        ("M-02", "M-04", 7900, "2026-10-15T03:05:00Z", "p2p", "TXN-9103", False, ""),
        ("M-03", "M-05", 7400, "2026-10-15T03:09:00Z", "p2p", "TXN-9104", False, ""),
        ("M-04", "C-ALPHA", 16800, "2026-10-15T04:40:00Z", "wire", "TXN-9105", False, ""),
        ("M-05", "C-ALPHA", 7200, "2026-10-15T04:44:00Z", "wire", "TXN-9106", False, ""),
        ("M-06", "C-ALPHA", 5300, "2026-10-15T04:51:00Z", "wire", "TXN-9107", False, ""),
        ("C-ALPHA", "C-BETA", 21000, "2026-10-15T06:10:00Z", "wire", "TXN-9108", False, ""),
        ("M-07", "C-ALPHA", 4100, "2026-10-14T21:00:00Z", "p2p", "TXN-9110", False, ""),
        ("M-08", "C-BETA", 3900, "2026-10-14T21:30:00Z", "p2p", "TXN-9111", False, ""),
        ("L-18", "BR-07", 1200, "2026-10-12T16:00:00Z", "ach", "TXN-B1", False, ""),
        ("BR-07", "M-06", 1100, "2026-10-13T11:00:00Z", "ach", "TXN-B2", False, ""),
        ("V-02", "BR-07", 2400, "2026-10-14T09:12:00Z", "ach", "TXN-ALERT-3", True, "bridge hop"),
        ("L-11", "L-12", 42, "2026-10-10T12:00:00Z", "card", "TXN-L1", False, ""),
        ("L-12", "L-13", 18, "2026-10-10T12:00:00Z", "card", "TXN-L2", False, ""),
        ("L-13", "L-14", 90, "2026-10-10T12:00:00Z", "card", "TXN-L3", False, ""),
        ("L-14", "L-15", 33, "2026-10-10T12:00:00Z", "card", "TXN-L4", False, ""),
        ("L-15", "L-11", 27, "2026-10-10T12:00:00Z", "card", "TXN-L5", False, ""),
        ("L-16", "L-17", 55, "2026-10-10T12:00:00Z", "card", "TXN-L6", False, ""),
        ("L-17", "L-16", 40, "2026-10-10T12:00:00Z", "card", "TXN-L7", False, ""),
        ("L-19", "L-20", 12, "2026-10-10T12:00:00Z", "card", "TXN-L8", False, ""),
        ("L-20", "L-19", 15, "2026-10-10T12:00:00Z", "card", "TXN-L9", False, ""),
        ("L-11", "L-16", 8, "2026-10-10T12:00:00Z", "card", "TXN-L10", False, ""),
        ("V-02", "L-11", 24, "2026-10-10T12:00:00Z", "card", "TXN-L11", False, ""),
        ("V-01", "L-17", 60, "2026-10-10T12:00:00Z", "card", "TXN-L12", False, ""),
    ]
    _q(
        """
        UNWIND $rows AS r
        MATCH (s:Account {id: r.src}), (d:Account {id: r.dst})
        CREATE (s)-[:SENT {
          id: r.id, amount: r.amount, ts: r.ts, channel: r.channel,
          alert: r.alert, note: r.note, weight: r.amount
        }]->(d)
        """,
        {
            "rows": [
                {
                    "src": src,
                    "dst": dst,
                    "amount": amount,
                    "ts": ts,
                    "channel": channel,
                    "id": txn_id,
                    "alert": alert,
                    "note": note,
                }
                for src, dst, amount, ts, channel, txn_id, alert, note in wires
            ]
        },
    )
    _q(
        """
        UNWIND $rows AS r
        MATCH (a:Account {id: r.a}), (m:Merchant {id: r.m})
        CREATE (a)-[:PAID {id: r.id, amount: r.amount, ts: r.ts, weight: 1.0}]->(m)
        """,
        {
            "rows": [
                {"a": "C-BETA", "m": "MRCH-NIGHT", "id": "TXN-CASH-1", "amount": 19800, "ts": "2026-10-15T07:22:00Z"},
                {"a": "L-12", "m": "MRCH-OAK", "id": "TXN-P1", "amount": 18, "ts": "2026-10-10T12:05:00Z"},
                {"a": "L-17", "m": "MRCH-GYM", "id": "TXN-P2", "amount": 60, "ts": "2026-10-10T12:08:00Z"},
            ]
        },
    )

    for stmt in [
        "CREATE INDEX FOR (a:Account) ON (a.id)",
        "CREATE INDEX FOR (t:Device) ON (t.id)",
    ]:
        try:
            _q(stmt)
        except Exception:  # noqa: BLE001
            pass

    count = _q("MATCH (n) RETURN count(n)").result_set[0][0]
    rels = _q("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    return {"seeded": True, "nodes": count, "relationships": rels, "story": GRAPH_STORY}
