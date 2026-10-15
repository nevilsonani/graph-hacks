# TRACEWIRE graph data model

**Track:** Agents That Act on Connected Data  
**Graph name:** `tracewire`  
**Engine:** FalkorDB (OpenCypher + `CALL algo.*`)

If you delete this graph, TRACEWIRE has nothing to investigate, nothing to rank, and nowhere to write a freeze. The UI is a window. The product is the graph.

## Model

```
(:Account {id, name, kind, country, kyc, risk, frozen, flagged, ring})
(:Device {id, label, flagged})
(:IP {addr, country})
(:Card {id, brand})
(:Merchant {id, name, mcc, risk})
(:Investigation {id, query, ts})
(:AgentStep {id, n, tool, reason, cypher, ts})
(:Action {id, kind, ts, reason})
(:Case {id, title, severity, ts, status})
(:Ring {id, size, method})

(Account)-[:SENT {id, amount, ts, channel, alert, note, weight}]->(Account)
(Account)-[:USED_DEVICE]->(Device)
(Account)-[:USED_IP]->(IP)
(Account)-[:USED_CARD]->(Card)
(Account)-[:PAID {id, amount, ts, weight}]->(Merchant)
(Account)-[:IN_RING]->(Ring)
(Investigation)-[:HAS_STEP]->(AgentStep)
(Investigation)-[:TOOK]->(Action)
(Action)-[:TARGET]->(Account|Device)
(Investigation)-[:OPENED]->(Case)
(Case)-[:INVOLVES]->(Account)
(Investigation)-[:MARKED]->(Ring)
```

`kind` on Account is one of: `victim | mule | collector | bridge | legit`.

## Why this shape

Fraud is not a row. A night-wire looks like:

`victim -SENT-> mule -SENT-> mule -SENT-> collector -PAID-> cash-out merchant`

plus a second overlay:

`mule -USED_DEVICE-> D-GHOST <-USED_DEVICE- other mules`

PageRank on `SENT` finds collectors. WCC on `SENT` finds the money pool. Shared `USED_DEVICE` finds the crew even when they split amounts.

## Algorithms the agent calls

| Tool | Procedure / pattern | Why |
|---|---|---|
| `rank_hubs` | `CALL algo.pageRank('Account', 'SENT')` | Who concentrates inbound money |
| `bridge_nodes` | `CALL algo.betweenness(...)` | Who sits on many paths (BR-07) |
| `detect_rings` | `CALL algo.WCC(...)` + shared device | Mule crews |
| `money_path` | `(src)-[:SENT*1..6]->(dst)` and `algo.SPpaths` | Multi-hop follow-the-money |
| `blast_radius` | `CALL algo.BFS(seed, 3, 'SENT')` | What a freeze actually stops |

Canonical Cypher lives in `backend/app/queries.py` and is copied onto every dossier step.

## Headline path (seeded)

`V-03 -TXN-ALERT-1 $9400-> M-01 -> M-04 -> C-ALPHA -> C-BETA -PAID-> MRCH-NIGHT`

Device `D-GHOST` is shared by `M-01` through `M-07`.
