"""Canonical Cypher the agent actually runs. See queries/GRAPH.md."""

INDEXES = [
    "CREATE INDEX FOR (a:Account) ON (a.id)",
    "CREATE INDEX FOR (t:Txn) ON (t.id)",
    "CREATE INDEX FOR (d:Device) ON (d.id)",
    "CREATE INDEX FOR (m:Merchant) ON (m.id)",
    "CREATE INDEX FOR (c:Card) ON (c.id)",
    "CREATE INDEX FOR (i:IP) ON (i.addr)",
]

LOOKUP_ACCOUNT = """
MATCH (a:Account {id: $id})
OPTIONAL MATCH (a)-[:USED_DEVICE]->(d:Device)
OPTIONAL MATCH (a)-[:USED_IP]->(ip:IP)
OPTIONAL MATCH (a)-[:USED_CARD]->(c:Card)
RETURN a.id, a.name, a.kind, a.country, a.kyc, a.risk, a.frozen, a.flagged,
       collect(DISTINCT d.id), collect(DISTINCT ip.addr), collect(DISTINCT c.id)
"""

LOOKUP_TXN = """
MATCH (src:Account)-[s:SENT {id: $id}]->(dst:Account)
OPTIONAL MATCH (dst)-[:PAID]->(m:Merchant)
RETURN s.id, s.amount, s.ts, s.channel, src.id, src.name, dst.id, dst.name,
       coalesce(m.id, ''), coalesce(m.name, '')
"""

NEIGHBORHOOD = """
MATCH (a:Account {id: $id})
OPTIONAL MATCH (a)-[out:SENT]->(payee:Account)
OPTIONAL MATCH (payer:Account)-[inc:SENT]->(a)
OPTIONAL MATCH (a)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(otherD:Account)
OPTIONAL MATCH (a)-[:USED_IP]->(ip:IP)<-[:USED_IP]-(otherIp:Account)
OPTIONAL MATCH (a)-[:USED_CARD]->(c:Card)<-[:USED_CARD]-(otherC:Account)
RETURN a.id,
       collect(DISTINCT {id: payee.id, amount: out.amount, txn: out.id, dir: 'out'})[0..12] AS outs,
       collect(DISTINCT {id: payer.id, amount: inc.amount, txn: inc.id, dir: 'in'})[0..12] AS ins,
       collect(DISTINCT otherD.id)[0..12] AS device_peers,
       collect(DISTINCT otherIp.id)[0..12] AS ip_peers,
       collect(DISTINCT otherC.id)[0..12] AS card_peers
"""

MONEY_PATH = """
MATCH (src:Account {id: $src}), (dst:Account {id: $dst})
MATCH p = (src)-[:SENT*1..6]->(dst)
WITH p,
     [n IN nodes(p) | n.id] AS hops,
     [r IN relationships(p) | r.amount] AS amounts,
     [r IN relationships(p) | r.id] AS txns,
     length(p) AS hops_n,
     reduce(total = 0.0, r IN relationships(p) | total + r.amount) AS volume
RETURN hops, amounts, txns, hops_n, volume
ORDER BY hops_n ASC, volume DESC
LIMIT 5
"""

SP_PATH = """
MATCH (src:Account {id: $src}), (dst:Account {id: $dst})
CALL algo.SPpaths({
  sourceNode: src,
  targetNode: dst,
  relTypes: ['SENT'],
  weightProp: 'weight',
  relDirection: 'outgoing',
  pathCount: 3,
  maxLen: 6
})
YIELD path, pathWeight
RETURN [n IN nodes(path) | n.id] AS hops, pathWeight
"""

PAGERANK_HUBS = """
CALL algo.pageRank('Account', 'SENT')
YIELD node, score
RETURN node.id AS id, node.name AS name, node.kind AS kind, score
ORDER BY score DESC
LIMIT $limit
"""

BETWEENNESS = """
CALL algo.betweenness({nodeLabels: ['Account'], relationshipTypes: ['SENT']})
YIELD node, score
RETURN node.id AS id, node.name AS name, score
ORDER BY score DESC
LIMIT $limit
"""

WCC_RINGS = """
CALL algo.WCC({nodeLabels: ['Account'], relationshipTypes: ['SENT']})
YIELD node, componentId
WITH componentId, collect(node.id) AS members, count(node) AS size
WHERE size >= $min_size
RETURN componentId, size, members
ORDER BY size DESC
LIMIT 12
"""

DEVICE_RINGS = """
MATCH (a:Account)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(b:Account)
WHERE a.id < b.id
WITH d, collect(DISTINCT a.id) + collect(DISTINCT b.id) AS raw
WITH d, raw
MATCH (x:Account)-[:USED_DEVICE]->(d)
WITH d.id AS device, collect(DISTINCT x.id) AS members, count(DISTINCT x) AS size
WHERE size >= 3
RETURN device, size, members
ORDER BY size DESC
"""

BLAST_RADIUS = """
MATCH (seed:Account {id: $id})
CALL algo.BFS(seed, 3, 'SENT')
YIELD nodes
UNWIND nodes AS n
RETURN n.id AS id, n.name AS name, n.kind AS kind, n.frozen AS frozen
"""

BLAST_RADIUS_FALLBACK = """
MATCH (seed:Account {id: $id})-[:SENT*1..3]->(n:Account)
RETURN DISTINCT n.id AS id, n.name AS name, n.kind AS kind, n.frozen AS frozen
LIMIT 40
"""

FAN_IN = """
MATCH (a:Account)<-[s:SENT]-()
RETURN a.id, a.name, a.kind, count(s) AS inbound, sum(s.amount) AS volume, a.frozen
ORDER BY volume DESC
LIMIT $limit
"""

CASH_OUT = """
MATCH (a:Account)-[p:PAID]->(m:Merchant)
RETURN a.id, a.name, a.kind, p.id, p.amount, p.ts, m.id, m.name, m.risk
ORDER BY p.amount DESC
LIMIT 12
"""

SIMULATE_FREEZE = """
MATCH (seed:Account {id: $id})
OPTIONAL MATCH (seed)-[:SENT*1..4]->(n:Account)
RETURN seed.id, seed.name, seed.kind, seed.frozen,
       collect(DISTINCT {id: n.id, name: n.name, kind: n.kind, frozen: n.frozen})[0..30] AS downstream
"""

CRIME_ACCOUNTS = """
MATCH (a:Account)
WHERE a.kind IN ['victim', 'mule', 'collector', 'bridge']
RETURN a.id, a.name, a.kind, a.risk, a.frozen, a.flagged
"""

CRIME_EDGES = """
MATCH (a:Account)-[s:SENT]->(b:Account)
WHERE a.kind IN ['victim', 'mule', 'collector', 'bridge']
  AND b.kind IN ['victim', 'mule', 'collector', 'bridge']
RETURN a.id, b.id, s.amount, s.id, s.channel, s.alert
"""

CRIME_DEVICES = """
MATCH (a:Account)-[:USED_DEVICE]->(d:Device)
WHERE a.kind IN ['victim', 'mule', 'collector', 'bridge']
RETURN DISTINCT d.id, d.label, d.flagged, collect(a.id)
"""

REPLAY_STEPS = """
MATCH (inv:Investigation {id: $id})-[:HAS_STEP]->(s:AgentStep)
RETURN inv.id, inv.query, inv.ts, s.n, s.tool, s.reason, s.cypher, s.ts
ORDER BY s.n ASC
"""

REPLAY_ACTIONS = """
MATCH (inv:Investigation {id: $id})-[:TOOK]->(act:Action)-[:TARGET]->(t)
RETURN act.id, act.kind, act.ts, act.reason, coalesce(t.id, t.addr)
"""

SEARCH = """
MATCH (a:Account)
WHERE a.id CONTAINS $q OR toLower(a.name) CONTAINS toLower($q)
RETURN a.id, a.name, a.kind, a.risk, a.frozen
LIMIT 12
"""

FREEZE = """
MATCH (a:Account {id: $id})
SET a.frozen = true, a.risk = CASE WHEN a.risk < 90 THEN 90 ELSE a.risk END
WITH a
MERGE (act:Action {id: $action_id})
SET act.kind = 'freeze', act.ts = $ts, act.reason = $reason
MERGE (inv:Investigation {id: $inv_id})
MERGE (inv)-[:TOOK]->(act)
MERGE (act)-[:TARGET]->(a)
RETURN a.id, a.frozen
"""

FLAG_DEVICE = """
MATCH (d:Device {id: $id})
SET d.flagged = true
WITH d
MATCH (a:Account)-[:USED_DEVICE]->(d)
SET a.flagged = true
MERGE (act:Action {id: $action_id})
SET act.kind = 'flag_device', act.ts = $ts, act.reason = $reason
MERGE (inv:Investigation {id: $inv_id})
MERGE (inv)-[:TOOK]->(act)
MERGE (act)-[:TARGET]->(d)
RETURN d.id, collect(a.id)
"""

OPEN_CASE = """
MERGE (c:Case {id: $case_id})
SET c.title = $title, c.severity = $severity, c.ts = $ts, c.status = 'open'
MERGE (inv:Investigation {id: $inv_id})
MERGE (inv)-[:OPENED]->(c)
WITH c, inv
UNWIND $account_ids AS aid
MATCH (a:Account {id: aid})
MERGE (c)-[:INVOLVES]->(a)
RETURN c.id, c.title, c.severity
"""

MARK_RING = """
UNWIND $account_ids AS aid
MATCH (a:Account {id: aid})
SET a.ring = $ring_id, a.flagged = true
WITH collect(a) AS accounts
MERGE (r:Ring {id: $ring_id})
SET r.size = size(accounts), r.method = $method
MERGE (inv:Investigation {id: $inv_id})
MERGE (inv)-[:MARKED]->(r)
WITH r, accounts
UNWIND accounts AS a
MERGE (a)-[:IN_RING]->(r)
RETURN r.id, r.size
"""

LOG_STEP = """
MERGE (inv:Investigation {id: $inv_id})
SET inv.query = coalesce(inv.query, $query), inv.ts = coalesce(inv.ts, $ts), inv.updated = $ts
CREATE (s:AgentStep {
  id: $step_id,
  n: $n,
  tool: $tool,
  reason: $reason,
  cypher: $cypher,
  ts: $ts
})
MERGE (inv)-[:HAS_STEP]->(s)
"""

SUBGRAPH_NODES = """
UNWIND $ids AS aid
MATCH (a:Account {id: aid})
RETURN a.id, a.name, a.kind, a.risk, a.frozen, a.flagged
"""

SUBGRAPH_EDGES = """
UNWIND $ids AS aid
UNWIND $ids AS bid
MATCH (a:Account {id: aid})-[s:SENT]->(b:Account {id: bid})
RETURN a.id, b.id, s.amount, s.id, s.channel
"""

SUBGRAPH_DEVICES = """
UNWIND $ids AS aid
MATCH (a:Account {id: aid})-[:USED_DEVICE]->(d:Device)
RETURN DISTINCT d.id, d.label, d.flagged
"""

SUBGRAPH_DEVICE_EDGES = """
UNWIND $ids AS aid
MATCH (a:Account {id: aid})-[:USED_DEVICE]->(d:Device)
RETURN a.id, d.id
"""

SUBGRAPH_PAY = """
UNWIND $ids AS aid
MATCH (a:Account {id: aid})-[p:PAID]->(m:Merchant)
RETURN a.id, m.id, m.name, p.amount, p.id, m.risk
"""

STATS = """
CALL db.meta.stats()
YIELD nodeCount, relCount, labels, relTypes
RETURN nodeCount, relCount, labels, relTypes
"""

ALERTS = """
MATCH (src:Account)-[s:SENT]->(dst:Account)
WHERE s.alert = true
RETURN s.id, s.amount, s.ts, s.channel, src.id, src.name, dst.id, dst.name, s.note
ORDER BY s.ts DESC
"""

INVESTIGATIONS = """
MATCH (inv:Investigation)
OPTIONAL MATCH (inv)-[:HAS_STEP]->(s:AgentStep)
OPTIONAL MATCH (inv)-[:TOOK]->(act:Action)
RETURN inv.id, inv.query, inv.ts, count(DISTINCT s), count(DISTINCT act)
ORDER BY inv.ts DESC
LIMIT 12
"""
