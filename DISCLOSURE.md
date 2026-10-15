# AI disclosure (Graph Hacks rule 11)

Cursor Grok 4.6 was used as a coding assistant to scaffold TRACEWIRE, write FalkorDB Cypher, the FastAPI agent loop, and the UI.

What still had to be decided by a person:

- Track choice: **Agents That Act on Connected Data** (iPhone prize)
- Product bet: freeze/flag/case are graph writes, not chat text
- Schema: SENT + USED_DEVICE overlay, not a chat memory graph pretending to be fraud
- Seed story: night-wire mule ring on D-GHOST into Collector Alpha
- Rule that the agent must not invent nodes; every verdict cites a tool result

Do not submit this as “AI built it, I cannot explain it.” You need to be able to walk a judge through:

1. Why `SENT` is directed and `USED_DEVICE` is the ring overlay  
2. Why PageRank is the collector detector  
3. Why a freeze is a `SET a.frozen = true` plus an `Action` node  
4. What happens if FalkorDB is down (HTTP 503, product dead)
