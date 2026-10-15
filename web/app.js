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

let graphData = { nodes: [], edges: [] };
let sim = [];

PROMPTS.forEach((p) => {
  const b = document.createElement("button");
  b.className = "chip";
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

async function boot() {
  try {
    const h = await fetch("/api/health").then((r) => r.json());
    $("dot").classList.toggle("on", !!h.ok);
    $("status-label").textContent = h.ok ? "FalkorDB live" : "graph offline";
    const o = await fetch("/api/overview").then((r) => r.json());
    $("counts").textContent = `${o.nodeCount || 0} nodes · ${o.relCount || 0} edges`;
    alertsEl.innerHTML = "";
    (o.alerts || []).forEach((a) => {
      const b = document.createElement("button");
      b.className = "ticket";
      b.innerHTML = `<b>${a.id}</b><span>$${a.amount} · ${a.src} → ${a.dst}<br>${a.note || a.channel}</span>`;
      b.onclick = () => {
        qEl.value = `Investigate ${a.id} from ${a.src} to ${a.dst}`;
        run();
      };
      alertsEl.appendChild(b);
    });
    if (o.hubs) {
      graphData = {
        nodes: o.hubs.map((h) => ({
          id: h.id,
          name: h.name,
          kind: h.kind,
          risk: Math.round((h.score || 0) * 400),
          frozen: false,
        })),
        edges: [],
      };
      layout();
    }
  } catch {
    $("status-label").textContent = "graph offline — product cannot run";
  }
}

async function run() {
  const query = qEl.value.trim();
  if (!query) return;
  $("go").disabled = true;
  $("go").textContent = "Walking the graph…";
  stepsEl.innerHTML = "";
  try {
    const res = await fetch("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, take_actions: $("act").checked }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t);
    }
    const data = await res.json();
    renderDossier(data);
    graphData = data.graph || { nodes: [], edges: [] };
    layout();
  } catch (err) {
    verdictEl.innerHTML = `<p class="v-title">Graph unreachable</p><p class="v-copy">${err.message}</p>`;
  } finally {
    $("go").disabled = false;
    $("go").textContent = "Run investigation";
  }
}

function renderDossier(data) {
  verdictEl.innerHTML = `
    <span class="badge ${data.verdict}">${data.verdict} · ${Math.round(data.confidence * 100)}%</span>
    <p class="v-title">${data.verdict === "FREEZE" ? "Freeze the ring." : data.verdict === "WATCH" ? "Keep the wire." : "No mule structure."}</p>
    <p class="v-copy">${data.hypothesis} <em>${data.investigation_id}</em> · selector ${data.selector}</p>
  `;
  stepsEl.innerHTML = "";
  (data.steps || []).forEach((s) => {
    const li = document.createElement("li");
    const preview = JSON.stringify(s.result, null, 0).slice(0, 280);
    li.innerHTML = `
      <div class="n">STEP ${String(s.n).padStart(2, "0")} · ${s.tool}</div>
      <div class="tool">${s.reason || ""}</div>
      <div class="why">${preview}</div>
      <pre>${(s.cypher || "").slice(0, 320)}</pre>
    `;
    stepsEl.appendChild(li);
  });
}

function color(n) {
  if (n.frozen) return "#c8f04d";
  if (n.kind === "collector") return "#d64532";
  if (n.kind === "mule") return "#e36a3d";
  if (n.kind === "victim") return "#f0e7c3";
  if (n.kind === "bridge") return "#d4a24a";
  return "#6f8f6a";
}

function layout() {
  const nodes = (graphData.nodes || []).filter((n) => n && n.id);
  sim = nodes.map((n, i) => ({
    ...n,
    x: Math.cos((i / Math.max(nodes.length, 1)) * Math.PI * 2) * 140,
    y: Math.sin((i / Math.max(nodes.length, 1)) * Math.PI * 2) * 110,
    vx: 0,
    vy: 0,
  }));
  draw();
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
      const force = 900 / (d * d);
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
    a.vx += dx * 0.01;
    a.vy += dy * 0.01;
    b.vx -= dx * 0.01;
    b.vy -= dy * 0.01;
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

function draw() {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  stepPhysics();
  ctx.lineWidth = 1;
  (graphData.edges || []).forEach((e) => {
    const a = sim.find((n) => n.id === e.source);
    const b = sim.find((n) => n.id === e.target);
    if (!a || !b) return;
    ctx.strokeStyle = "rgba(200,240,77,0.35)";
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
    ctx.fillStyle = color(n);
    ctx.beginPath();
    ctx.arc(cx + n.x, cy + n.y, n.frozen ? 9 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#efe6d2";
    ctx.font = "11px IBM Plex Mono";
    ctx.fillText(n.id, cx + n.x + 10, cy + n.y + 4);
  });
  requestAnimationFrame(draw);
}

window.addEventListener("resize", () => layout());
boot();
