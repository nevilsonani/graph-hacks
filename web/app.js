const PROMPTS = [
  "Investigate TXN-ALERT-1 — $9,400 night wire",
  "Find mule hubs with PageRank",
  "Map the ring around device D-GHOST",
  "Money path from V-03 to C-ALPHA",
  "What breaks if we freeze C-ALPHA?",
];

const $ = (id) => document.getElementById(id);
const qEl = $("q");
const stepsEl = $("steps");
const alertsEl = $("alerts");
const promptsEl = $("prompts");
const verdictEl = $("verdict");
const canvas = $("graph");
const ctx = canvas.getContext("2d");
const inspectEl = $("inspect");
const stripEl = $("actions-strip");
const historyEl = $("history");

let graphData = { nodes: [], edges: [] };
let sim = [];
let hoverId = null;
let drawing = false;

PROMPTS.forEach((p) => {
  const b = document.createElement("button");
  b.className = "chip";
  b.type = "button";
  b.textContent = p;
  b.onclick = () => {
    qEl.value = p;
    run();
  };
  promptsEl.appendChild(b);
});

$("ask").addEventListener("submit", (e) => {
  e.preventDefault();
  run();
});

$("reseed").addEventListener("click", async () => {
  $("reseed").disabled = true;
  try {
    await fetch("/api/reseed", { method: "POST" });
    await boot();
    verdictEl.innerHTML = `<p class="v-title">Ledger reset.</p><p class="v-copy">Synthetic night-wire is back. Frozen flags cleared. Run TXN-ALERT-1 again.</p>`;
  } finally {
    $("reseed").disabled = false;
  }
});

async function boot() {
  try {
    const h = await fetch("/api/health").then((r) => r.json());
    $("dot").classList.toggle("on", !!h.ok);
    $("status-label").textContent = h.ok ? "FalkorDB live" : "graph offline";
    const o = await fetch("/api/overview").then((r) => r.json());
    $("counts").textContent = `${o.nodeCount || 0} nodes · ${o.relCount || 0} edges · ${o.frozen || 0} frozen`;
    alertsEl.innerHTML = "";
    (o.alerts || []).forEach((a) => {
      const b = document.createElement("button");
      b.className = "ticket";
      b.type = "button";
      b.innerHTML = `<b>${a.id}</b><span>$${a.amount} · ${a.src} → ${a.dst}<br>${a.note || a.channel}</span>`;
      b.onclick = () => {
        qEl.value = `Investigate ${a.id} from ${a.src} to ${a.dst}`;
        run();
      };
      alertsEl.appendChild(b);
    });
    historyEl.innerHTML = "";
    (o.investigations || []).forEach((inv) => {
      const b = document.createElement("button");
      b.className = "ticket";
      b.type = "button";
      b.innerHTML = `<b>${inv.id}</b><span>${inv.steps} steps · ${inv.actions} writes<br>${(inv.query || "").slice(0, 72)}</span>`;
      b.onclick = () => replay(inv.id);
      historyEl.appendChild(b);
    });
    if (o.scene && (o.scene.nodes || []).length) {
      graphData = o.scene;
      layout();
    }
  } catch {
    $("status-label").textContent = "graph offline — product cannot run";
  }
}

async function replay(id) {
  const data = await fetch(`/api/investigations/${id}`).then((r) => r.json());
  verdictEl.innerHTML = `
    <span class="badge WATCH">REPLAY</span>
    <p class="v-title">From the graph, not chat.</p>
    <p class="v-copy">${data.note} Query: ${data.query}</p>
  `;
  stepsEl.innerHTML = "";
  (data.steps || []).forEach(appendStep);
}

async function run() {
  const query = qEl.value.trim();
  if (!query) return;
  $("go").disabled = true;
  $("go").textContent = "Walking the graph…";
  stepsEl.innerHTML = "";
  stripEl.hidden = true;
  stripEl.innerHTML = "";
  verdictEl.innerHTML = `<span class="badge WALK">WALK</span><p class="v-title">Following edges.</p><p class="v-copy">Tool selection is running against FalkorDB. Each step below is a real query.</p>`;
  try {
    const res = await fetch("/api/investigate/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, take_actions: $("act").checked }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop();
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        handleEvent(event);
      }
    }
    await boot();
  } catch (err) {
    verdictEl.innerHTML = `<p class="v-title">Graph unreachable</p><p class="v-copy">${err.message}</p>`;
  } finally {
    $("go").disabled = false;
    $("go").textContent = "Run investigation";
  }
}

function handleEvent(event) {
  if (event.type === "step") {
    appendStep(event.step);
    if (event.graph && (event.graph.nodes || []).length) {
      graphData = event.graph;
      layout();
    }
  }
  if (event.type === "done") {
    renderDossier(event.payload);
    graphData = event.payload.graph || graphData;
    layout();
  }
}

function appendStep(s) {
  const li = document.createElement("li");
  if (s.kind === "action" || ["freeze_account", "flag_device", "open_case", "mark_ring"].includes(s.tool)) {
    li.className = "action";
  }
  const preview = JSON.stringify(s.result || { tool: s.tool }, null, 0).slice(0, 280);
  li.innerHTML = `
    <div class="n">STEP ${String(s.n).padStart(2, "0")} · ${s.tool}</div>
    <div class="tool">${s.reason || ""}</div>
    <div class="why">${preview}</div>
    <pre>${(s.cypher || "").slice(0, 360)}</pre>
  `;
  stepsEl.appendChild(li);
  li.scrollIntoView({ block: "nearest" });
}

function renderDossier(data) {
  const title =
    data.verdict === "FREEZE" ? "Freeze the ring." : data.verdict === "WATCH" ? "Keep the wire." : "No mule structure.";
  verdictEl.innerHTML = `
    <span class="badge ${data.verdict}">${data.verdict} · ${Math.round(data.confidence * 100)}%</span>
    <p class="v-title">${title}</p>
    <p class="v-copy">${data.hypothesis} <em>${data.investigation_id}</em> · selector ${data.selector}</p>
  `;
  const acts = data.actions || [];
  if (acts.length) {
    stripEl.hidden = false;
    stripEl.innerHTML = acts
      .map((a) => {
        const cls = a.tool === "flag_device" ? "flag" : a.tool === "open_case" ? "case" : "";
        const tgt = (a.args && (a.args.id || a.args.ring_id || a.args.title)) || "";
        return `<span class="pill ${cls}">${a.tool} ${tgt}</span>`;
      })
      .join("");
  }
}

function color(n) {
  if (n.frozen) return "#c8f04d";
  if (n.kind === "collector") return "#d64532";
  if (n.kind === "mule") return "#e36a3d";
  if (n.kind === "victim") return "#f0e7c3";
  if (n.kind === "bridge") return "#d4a24a";
  if (n.kind === "device") return "#7aa0c4";
  if (n.kind === "merchant") return "#c4a07a";
  return "#6f8f6a";
}

function layout() {
  const nodes = (graphData.nodes || []).filter((n) => n && n.id);
  const prev = Object.fromEntries(sim.map((n) => [n.id, n]));
  sim = nodes.map((n, i) => {
    const old = prev[n.id];
    if (old) return { ...n, x: old.x, y: old.y, vx: old.vx, vy: old.vy };
    return {
      ...n,
      x: Math.cos((i / Math.max(nodes.length, 1)) * Math.PI * 2) * 150,
      y: Math.sin((i / Math.max(nodes.length, 1)) * Math.PI * 2) * 120,
      vx: 0,
      vy: 0,
    };
  });
  if (!drawing) {
    drawing = true;
    draw();
  }
}

function stepPhysics() {
  const edges = graphData.edges || [];
  for (let i = 0; i < sim.length; i++) {
    for (let j = i + 1; j < sim.length; j++) {
      const a = sim[i];
      const b = sim[j];
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      let d = Math.hypot(dx, dy) || 0.1;
      const force = 1100 / (d * d);
      dx /= d;
      dy /= d;
      a.vx += dx * force;
      a.vy += dy * force;
      b.vx -= dx * force;
      b.vy -= dy * force;
    }
  }
  edges.forEach((e) => {
    const a = sim.find((n) => n.id === e.source);
    const b = sim.find((n) => n.id === e.target);
    if (!a || !b) return;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const pull = e.kind === "USED_DEVICE" ? 0.018 : 0.012;
    a.vx += dx * pull;
    a.vy += dy * pull;
    b.vx -= dx * pull;
    b.vy -= dy * pull;
  });
  sim.forEach((n) => {
    n.vx += -n.x * 0.002;
    n.vy += -n.y * 0.002;
    n.vx *= 0.82;
    n.vy *= 0.82;
    n.x += n.vx;
    n.y += n.vy;
  });
}

function metrics() {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  return { dpr, rect, cx: rect.width / 2, cy: rect.height / 2 };
}

function draw() {
  const dpr = window.devicePixelRatio || 1;
  const wrap = canvas.parentElement.getBoundingClientRect();
  canvas.width = wrap.width * dpr;
  canvas.height = wrap.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, wrap.width, wrap.height);
  const cx = wrap.width / 2;
  const cy = wrap.height / 2;
  stepPhysics();
  (graphData.edges || []).forEach((e) => {
    const a = sim.find((n) => n.id === e.source);
    const b = sim.find((n) => n.id === e.target);
    if (!a || !b) return;
    ctx.strokeStyle = e.kind === "USED_DEVICE" ? "rgba(122,160,196,0.45)" : e.alert ? "rgba(214,69,50,0.65)" : "rgba(200,240,77,0.32)";
    ctx.lineWidth = e.kind === "PAID" ? 1.6 : 1;
    ctx.beginPath();
    ctx.moveTo(cx + a.x, cy + a.y);
    ctx.lineTo(cx + b.x, cy + b.y);
    ctx.stroke();
    if (e.amount) {
      ctx.fillStyle = "#8a8270";
      ctx.font = "10px IBM Plex Mono";
      ctx.fillText(`$${e.amount}`, cx + (a.x + b.x) / 2, cy + (a.y + b.y) / 2);
    }
  });
  sim.forEach((n) => {
    const r = n.frozen ? 10 : n.kind === "device" ? 5 : n.kind === "collector" ? 8 : 6;
    ctx.fillStyle = color(n);
    ctx.beginPath();
    if (n.kind === "device") {
      ctx.fillRect(cx + n.x - r, cy + n.y - r, r * 2, r * 2);
    } else {
      ctx.arc(cx + n.x, cy + n.y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    if (n.id === hoverId) {
      ctx.strokeStyle = "#efe6d2";
      ctx.stroke();
    }
    ctx.fillStyle = "#efe6d2";
    ctx.font = "11px IBM Plex Mono";
    ctx.fillText(n.id, cx + n.x + 10, cy + n.y + 4);
  });
  requestAnimationFrame(draw);
}

canvas.addEventListener("mousemove", (ev) => {
  const { rect, cx, cy } = metrics();
  const x = ev.clientX - rect.left - cx;
  const y = ev.clientY - rect.top - cy;
  let hit = null;
  sim.forEach((n) => {
    if (Math.hypot(n.x - x, n.y - y) < 14) hit = n;
  });
  hoverId = hit ? hit.id : null;
  if (hit) {
    inspectEl.hidden = false;
    inspectEl.innerHTML = `<b>${hit.id}</b>${hit.name || ""}<br>${hit.kind || ""}${hit.frozen ? " · FROZEN" : ""}${hit.flagged ? " · flagged" : ""}`;
  } else {
    inspectEl.hidden = true;
  }
});

canvas.addEventListener("click", () => {
  if (!hoverId) return;
  qEl.value = `Investigate ${hoverId}`;
  run();
});

window.addEventListener("resize", () => layout());
boot();
