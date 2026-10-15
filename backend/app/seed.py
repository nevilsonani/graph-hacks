"""Synthetic payment graph. Every alert in the UI is a real path in this data."""

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

    # Recreate graph handle after delete
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

    for aid, name, kind, country, kyc, risk in accounts:
        _q(
            """
            CREATE (:Account {
              id: $id, name: $name, kind: $kind, country: $country,
              kyc: $kyc, risk: $risk, frozen: false, flagged: false, ring: ''
            })
            """,
            {
                "id": aid,
                "name": name,
                "kind": kind,
                "country": country,
                "kyc": kyc,
                "risk": risk,
            },
        )

    devices = [
        ("D-GHOST", "iOS 19 / Graphene"),
        ("D-HOME", "Pixel legit"),
        ("D-CAFE", "shared cafe kiosk"),
        ("D-BRIDGE", "work laptop"),
    ]
    for did, label in devices:
        _q("CREATE (:Device {id: $id, label: $label, flagged: false})", {"id": did, "label": label})

    ips = [("185.22.9.4", "CY"), ("8.8.4.12", "US"), ("102.44.1.9", "AE"), ("73.11.2.8", "US")]
    for addr, country in ips:
        _q("CREATE (:IP {addr: $addr, country: $country})", {"addr": addr, "country": country})

    cards = [("CARD-4412", "visa"), ("CARD-9981", "mc"), ("CARD-1100", "visa")]
    for cid, brand in cards:
        _q("CREATE (:Card {id: $id, brand: $brand})", {"id": cid, "brand": brand})

    _q(
        """
        CREATE (:Merchant {id: 'MRCH-NIGHT', name: 'Night Kiosk Electronics', mcc: '5732', risk: 91})
        CREATE (:Merchant {id: 'MRCH-OAK', name: 'Oak Street Books', mcc: '5942', risk: 4})
        CREATE (:Merchant {id: 'MRCH-GYM', name: 'North Gym', mcc: '7997', risk: 3})
        """
    )

    def link_device(account, device):
        _q(
            "MATCH (a:Account {id:$a}), (d:Device {id:$d}) MERGE (a)-[:USED_DEVICE]->(d)",
            {"a": account, "d": device},
        )

    def link_ip(account, addr):
        _q(
            "MATCH (a:Account {id:$a}), (i:IP {addr:$ip}) MERGE (a)-[:USED_IP]->(i)",
            {"a": account, "ip": addr},
        )

    def link_card(account, card):
        _q(
            "MATCH (a:Account {id:$a}), (c:Card {id:$c}) MERGE (a)-[:USED_CARD]->(c)",
            {"a": account, "c": card},
        )

    for mule in ["M-01", "M-02", "M-03", "M-04", "M-05", "M-06"]:
        link_device(mule, "D-GHOST")
        link_ip(mule, "185.22.9.4")
        link_card(mule, "CARD-4412")

    for v in ["V-01", "V-02", "V-03", "V-04"]:
        link_device(v, "D-HOME")
        link_ip(v, "73.11.2.8")
        link_card(v, "CARD-1100")

    for lid in ["L-11", "L-12", "L-13", "L-14", "L-15"]:
        link_device(lid, "D-HOME")
        link_ip(lid, "73.11.2.8")

    link_device("C-ALPHA", "D-CAFE")
    link_ip("C-ALPHA", "102.44.1.9")
    link_device("BR-07", "D-BRIDGE")
    link_device("M-07", "D-GHOST")
    link_device("M-08", "D-CAFE")

    def sent(src, dst, amount, ts, channel, txn_id, alert=False, note=""):
        _q(
            """
            MATCH (s:Account {id:$src}), (d:Account {id:$dst})
            CREATE (s)-[:SENT {
              id: $id, amount: $amount, ts: $ts, channel: $channel,
              alert: $alert, note: $note, weight: $amount
            }]->(d)
            """,
            {
                "src": src,
                "dst": dst,
                "amount": amount,
                "ts": ts,
                "channel": channel,
                "id": txn_id,
                "alert": alert,
                "note": note,
            },
        )

    def paid(account, merchant, amount, ts, txn_id):
        _q(
            """
            MATCH (a:Account {id:$a}), (m:Merchant {id:$m})
            CREATE (a)-[:PAID {id:$id, amount:$amount, ts:$ts, weight:1.0}]->(m)
            """,
            {"a": account, "m": merchant, "id": txn_id, "amount": amount, "ts": ts},
        )

    # Night-wire mule path (the headline case)
    sent("V-03", "M-01", 9400, "2026-10-15T02:11:00Z", "ach", "TXN-ALERT-1", True, "victim wire after fake invoice")
    sent("V-01", "M-02", 8100, "2026-10-15T02:14:00Z", "ach", "TXN-ALERT-2", True, "same device cluster inbound")
    sent("V-04", "M-03", 7600, "2026-10-15T02:18:00Z", "wire", "TXN-9101")
    sent("M-01", "M-04", 9100, "2026-10-15T03:02:00Z", "p2p", "TXN-9102")
    sent("M-02", "M-04", 7900, "2026-10-15T03:05:00Z", "p2p", "TXN-9103")
    sent("M-03", "M-05", 7400, "2026-10-15T03:09:00Z", "p2p", "TXN-9104")
    sent("M-04", "C-ALPHA", 16800, "2026-10-15T04:40:00Z", "wire", "TXN-9105")
    sent("M-05", "C-ALPHA", 7200, "2026-10-15T04:44:00Z", "wire", "TXN-9106")
    sent("M-06", "C-ALPHA", 5300, "2026-10-15T04:51:00Z", "wire", "TXN-9107")
    sent("C-ALPHA", "C-BETA", 21000, "2026-10-15T06:10:00Z", "wire", "TXN-9108")
    paid("C-BETA", "MRCH-NIGHT", 19800, "2026-10-15T07:22:00Z", "TXN-CASH-1")

    # Fan-in from extra mules
    sent("M-07", "C-ALPHA", 4100, "2026-10-14T21:00:00Z", "p2p", "TXN-9110")
    sent("M-08", "C-BETA", 3900, "2026-10-14T21:30:00Z", "p2p", "TXN-9111")

    # Bridge account connecting legit and mule worlds
    sent("L-18", "BR-07", 1200, "2026-10-12T16:00:00Z", "ach", "TXN-B1")
    sent("BR-07", "M-06", 1100, "2026-10-13T11:00:00Z", "ach", "TXN-B2")
    sent("V-02", "BR-07", 2400, "2026-10-14T09:12:00Z", "ach", "TXN-ALERT-3", True, "bridge hop")

    # Quiet legitimate economy so algorithms have contrast
    legit_pairs = [
        ("L-11", "L-12", 42, "TXN-L1"),
        ("L-12", "L-13", 18, "TXN-L2"),
        ("L-13", "L-14", 90, "TXN-L3"),
        ("L-14", "L-15", 33, "TXN-L4"),
        ("L-15", "L-11", 27, "TXN-L5"),
        ("L-16", "L-17", 55, "TXN-L6"),
        ("L-17", "L-16", 40, "TXN-L7"),
        ("L-19", "L-20", 12, "TXN-L8"),
        ("L-20", "L-19", 15, "TXN-L9"),
        ("L-11", "L-16", 8, "TXN-L10"),
        ("V-02", "L-11", 24, "TXN-L11"),
        ("V-01", "L-17", 60, "TXN-L12"),
    ]
    for src, dst, amt, tid in legit_pairs:
        sent(src, dst, amt, "2026-10-10T12:00:00Z", "card", tid)
    paid("L-12", "MRCH-OAK", 18, "2026-10-10T12:05:00Z", "TXN-P1")
    paid("L-17", "MRCH-GYM", 60, "2026-10-10T12:08:00Z", "TXN-P2")

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
