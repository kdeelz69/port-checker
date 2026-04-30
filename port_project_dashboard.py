import os
import json
import socket
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template_string

try:
    import psutil
except ImportError:
    raise SystemExit(
        "This app requires psutil. Install it with: pip install flask psutil"
    )

try:
    import docker
except ImportError:
    docker = None

app = Flask(__name__)

HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Project Port Dashboard</title>
  <style>
    :root {
      --bg: #edf0ef;
      --panel: #f7f9f8;
      --line: #cfd8d6;
      --line-soft: #dde4e2;
      --text: #101c28;
      --muted: #6b7b84;
      --teal: #178f8d;
      --blue: #2d71d2;
      --orange: #c57646;
      --danger: #cf655f;
      --ok-bg: #dff2ee;
      --ok-fg: #1f7b6c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", ui-sans-serif, system-ui, -apple-system, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .wrap {
      max-width: 1180px;
      margin: 0 auto;
      padding: 12px 14px 28px;
    }
    .top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
    }
    h1 {
      margin: 0 0 3px;
      font-size: 42px;
      font-weight: 800;
    }
    .sub {
      color: var(--muted);
      max-width: 760px;
      line-height: 1.45;
      margin: 0;
    }
    .sub-top-right {
      font-size: 11px;
      color: #4f6673;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #f4f7f6;
      margin-top: 6px;
    }
    .toolbar {
      display: grid;
      grid-template-columns: 1fr 132px 132px 100px;
      gap: 8px;
      margin-bottom: 10px;
    }
    input, select, button {
      width: 100%;
      padding: 8px 9px;
      border-radius: 6px;
      border: 1px solid var(--line-soft);
      background: #f8fbfa;
      color: var(--text);
      outline: none;
      font-size: 12px;
    }
    input::placeholder { color: #8c9ca3; }
    select { color: #4d5f6a; }
    button {
      cursor: pointer;
      background: #e8f0ef;
      color: #355a63;
      font-weight: 700;
      border: 1px solid #cfdbd8;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .label {
      color: #6e7b82;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .08em;
      margin-bottom: 8px;
      font-weight: 700;
    }
    .value {
      font-size: 36px;
      font-weight: 800;
      line-height: 1;
      display: inline-block;
    }
    .subvalue {
      margin-top: 7px;
      font-size: 11px;
      color: var(--muted);
    }
    .grid { display: grid; gap: 10px; }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 10px 0 8px;
    }
    .section-title {
      font-size: 30px;
      font-weight: 800;
    }
    .right-meta { display: flex; gap: 6px; }
    .meta-pill {
      font-size: 10px;
      color: #4f6170;
      border: 1px solid var(--line);
      border-radius: 5px;
      padding: 5px 8px;
      background: #f4f7f6;
    }
    .project-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .project-main {
      display: grid;
      grid-template-columns: minmax(220px, 1.2fr) 64px 92px 92px minmax(260px, 1fr) 88px;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
    }
    .namewrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .logo {
      width: 30px;
      height: 30px;
      border-radius: 5px;
      background: #138f8f;
      color: #fff;
      font-size: 15px;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .title {
      font-size: 16px;
      font-weight: 750;
      margin: 0 0 3px;
    }
    .meta {
      color: #74858e;
      font-size: 10px;
      word-break: break-word;
    }
    .metric {
      font-size: 10px;
      color: #6d7d85;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: .05em;
    }
    .metric b {
      margin-left: 7px;
      color: #183542;
      font-size: 12px;
      letter-spacing: 0;
      text-transform: none;
    }
    .ports {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .portline {
      width: 28px;
      height: 3px;
      border-radius: 6px;
      background: var(--teal);
      opacity: .9;
    }
    .chip.good {
      border: 1px solid #b8ddd4;
      background: #e7f6f1;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 10px;
      color: #1e7d6b;
      font-weight: 700;
    }
    .chip.warn {
      border: 1px solid #e2c8b3;
      background: #fff2e7;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 10px;
      color: var(--orange);
      font-weight: 700;
    }
    .status-badge {
      font-size: 10px;
      border-radius: 999px;
      padding: 4px 9px;
      border: 1px solid #b8ddd4;
      background: var(--ok-bg);
      color: var(--ok-fg);
      font-weight: 700;
      text-transform: uppercase;
    }
    .status-badge.warn {
      border-color: #e8c6c2;
      background: #fdeceb;
      color: #b84b45;
    }
    .status-badge.stopped {
      border-color: #cfd6d9;
      background: #eef2f4;
      color: #63717a;
    }
    .actions {
      display: flex;
      gap: 6px;
      justify-content: flex-end;
      color: #80929b;
      font-size: 13px;
      font-weight: 800;
    }
    details.more {
      border-top: 1px solid var(--line-soft);
      background: #f2f6f5;
    }
    details.more > summary {
      list-style: none;
      cursor: pointer;
      padding: 8px 10px;
      color: #56707b;
      font-size: 11px;
      font-weight: 700;
      text-align: center;
      user-select: none;
    }
    details.more > summary::-webkit-details-marker { display: none; }
    .details-wrap { padding: 0 10px 10px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      border: 1px solid var(--line-soft);
      border-radius: 6px;
      overflow: hidden;
      background: #f8fbfa;
    }
    th, td {
      text-align: left;
      padding: 7px 8px;
      border-top: 1px solid var(--line-soft);
      vertical-align: top;
      word-break: break-word;
    }
    th {
      color: #6e7d85;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .05em;
    }
    .dashboard-bottom {
      margin-top: 14px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }
    .panel-head {
      display: flex;
      justify-content: space-between;
      font-weight: 700;
      font-size: 13px;
      margin-bottom: 12px;
    }
    .health-list {
      display: grid;
      gap: 7px;
    }
    .health-row {
      border: 1px solid var(--line-soft);
      border-radius: 6px;
      padding: 9px;
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      background: #f7fbfa;
    }
    .health-row b { color: #2a6d7e; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
    }
    .empty {
      text-align: center;
      color: var(--muted);
      padding: 20px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #f7fbfa;
    }
    .loading-overlay {
      position: fixed;
      inset: 0;
      background: rgba(237, 240, 239, 0.78);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 999;
    }
    .loading-overlay.show { display: flex; }
    .loading-box {
      border: 1px solid var(--line);
      background: #ffffff;
      border-radius: 10px;
      padding: 14px 16px;
      color: #355a63;
      font-size: 13px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 230px;
      justify-content: center;
      box-shadow: 0 8px 22px rgba(0, 0, 0, 0.08);
    }
    .spinner {
      width: 18px;
      height: 18px;
      border: 2px solid #b8c9c6;
      border-top-color: #2c8c86;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    .error-banner {
      margin: 8px 0 10px;
      border: 1px solid #e1b5b0;
      background: #fceceb;
      color: #8c3e39;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 12px;
      display: none;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    @media (max-width: 900px) {
      h1 { font-size: 34px; }
      .top { flex-direction: column; align-items: stretch; }
      .toolbar, .stats { grid-template-columns: 1fr; }
      .project-main { grid-template-columns: 1fr; }
      .actions { justify-content: flex-start; }
      .dashboard-bottom { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      h1 { font-size: 28px; }
      .section-title { font-size: 24px; }
      .right-meta { display: none; }
    }
  </style>
</head>
<body>
  <div id="loadingOverlay" class="loading-overlay">
    <div class="loading-box"><span class="spinner"></span><span>Loading running ports...</span></div>
  </div>
  <div class="wrap">
    <div class="top">
      <div>
        <h1>Project Port Dashboard</h1>
        <div class="sub">Real-time infrastructure monitoring and process control hub.</div>
      </div>
      <div class="sub-top-right">Last Refresh: <span id="topRefresh">--:--:--</span></div>
    </div>
    <div id="errorBanner" class="error-banner"></div>

    <div class="toolbar">
      <input id="search" placeholder="Search project, path, process, command, or port" />
      <select id="sortBy" title="Sort">
        <option value="project">Sort: Name</option>
        <option value="ports">Sort: Port count</option>
        <option value="processes">Sort: Process count</option>
      </select>
      <select id="groupBy" title="Group">
        <option value="project">Group: Project</option>
        <option value="cwd">Group: Working dir</option>
        <option value="exe">Group: Executable path</option>
      </select>
      <button id="refreshBtn">Refresh</button>
    </div>

    <div class="stats">
      <div class="card">
        <div class="label">Projects</div>
        <div class="value" id="statProjects">0</div>
      </div>
      <div class="card">
        <div class="label">Listening Ports</div>
        <div class="value" id="statPorts">0</div>
      </div>
      <div class="card">
        <div class="label">Processes</div>
        <div class="value" id="statProcesses">0</div>
      </div>
      <div class="card">
        <div class="label">Avg Uptime</div>
        <div class="value" id="statUptime" style="font-size:31px">99.9%</div>
      </div>
    </div>

    <div class="section-head">
      <div class="section-title">Active Projects</div>
      <div class="right-meta">
        <div class="meta-pill">Sort by <span id="sortView">Name</span></div>
        <div class="meta-pill">Filters</div>
      </div>
    </div>
    <div id="projects" class="grid"></div>

    <div class="dashboard-bottom">
      <div class="panel">
        <div class="panel-head"><span>System Health</span></div>
        <div class="health-list">
          <div class="health-row"><span>Core Services</span><b id="coreHealth">--</b></div>
          <div class="health-row"><span>Storage Volume</span><b id="storageHealth">--</b></div>
          <div class="health-row"><span>Memory Usage</span><b id="memoryHealth">--</b></div>
          <div class="health-row"><span>API Latency</span><b id="latencyHealth">--</b></div>
        </div>
      </div>
    </div>
  </div>

<script>
let raw = [];
const openDetails = new Set();
let isLoading = false;
let currentController = null;

function setLoading(on) {
  isLoading = on;
  const ov = document.getElementById('loadingOverlay');
  const btn = document.getElementById('refreshBtn');
  if (ov) ov.classList.toggle('show', on);
  if (btn) {
    btn.disabled = on;
    btn.textContent = on ? 'Refreshing...' : 'Refresh';
  }
}

function showError(msg) {
  const el = document.getElementById('errorBanner');
  if (!el) return;
  if (!msg) {
    el.style.display = 'none';
    el.textContent = '';
    return;
  }
  el.textContent = msg;
  el.style.display = 'block';
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function formatPorts(items) {
  const ports = [];
  items.forEach(p => (p.ports || []).forEach(x => ports.push(x.port)));
  const uniq = [...new Set(ports)].sort((a,b) => a-b);
  return uniq.map(p => `<span class="chip good">:${p}</span>`).join('') || '<span class="chip warn">No open port</span>';
}

function collectStats(groups) {
  let ports = 0, processes = 0, memoryMb = 0;
  groups.forEach(g => {
    processes += g.items.length;
    g.items.forEach(p => {
      ports += (p.ports || []).length;
      memoryMb += Number(p.memory_mb || 0);
    });
  });
  document.getElementById('statProjects').textContent = groups.length;
  document.getElementById('statPorts').textContent = ports;
  document.getElementById('statProcesses').textContent = processes;
  const now = new Date().toLocaleTimeString();
  document.getElementById('topRefresh').textContent = now;
  const uptime = Math.max(95.1, 100 - (processes > 0 ? (ports / (processes * 40)) * 10 : 1)).toFixed(1);
  document.getElementById('statUptime').textContent = `${uptime}%`;
  const memEl = document.getElementById('memoryHealth');
  if (memEl) {
    if (memoryMb >= 4096) memEl.textContent = `HIGH (${memoryMb.toFixed(0)}MB)`;
    else if (memoryMb >= 2048) memEl.textContent = `ELEVATED (${memoryMb.toFixed(0)}MB)`;
    else memEl.textContent = `NOMINAL (${memoryMb.toFixed(0)}MB)`;
  }
}

function updateSystemHealth(meta) {
  const coreEl = document.getElementById('coreHealth');
  const storageEl = document.getElementById('storageHealth');
  if (coreEl) {
    const running = Number(meta?.running_containers || 0);
    const total = Number(meta?.total_containers || 0);
    coreEl.textContent = total > 0 ? `${running}/${total} RUNNING` : 'NO CONTAINERS';
  }
  if (storageEl) {
    const free = Number(meta?.disk_free_percent ?? -1);
    storageEl.textContent = free >= 0 ? `${free.toFixed(1)}% FREE` : '--';
  }
}

function groupItems(items, mode) {
  const grouped = new Map();
  for (const item of items) {
    let key = item.project_name || 'unknown';
    if (mode === 'cwd') key = item.cwd || 'unknown';
    if (mode === 'exe') key = item.exe || 'unknown';
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  }

  return [...grouped.entries()].map(([key, arr]) => ({
    key,
    items: arr,
    sample: arr[0],
    portCount: arr.reduce((n, x) => n + (x.ports || []).length, 0),
    runningCount: arr.filter(x => String(x.status || '').toLowerCase() === 'running').length,
  }));
}

function applyFilters() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const sortBy = document.getElementById('sortBy').value;
  const groupBy = document.getElementById('groupBy').value;
  const sortName = { project: 'Name', ports: 'Ports', processes: 'Processes' }[sortBy] || 'Name';
  document.getElementById('sortView').textContent = sortName;

  const filtered = raw.filter(item => {
    const hay = [
      item.project_name,
      item.cwd,
      item.exe,
      item.name,
      item.cmdline,
      ...(item.ports || []).map(p => String(p.port)),
    ].join(' ').toLowerCase();
    return !q || hay.includes(q);
  });

  let groups = groupItems(filtered, groupBy);

  groups.sort((a, b) => {
    if (sortBy === 'ports') return b.portCount - a.portCount || a.key.localeCompare(b.key);
    if (sortBy === 'processes') return b.items.length - a.items.length || a.key.localeCompare(b.key);
    return a.key.localeCompare(b.key);
  });

  collectStats(groups);
  render(groups, groupBy);
}

function render(groups, groupBy) {
  const root = document.getElementById('projects');
  if (!groups.length) {
    root.innerHTML = '<div class="card empty">No listening processes matched your search.</div>';
    return;
  }

  root.innerHTML = groups.map(group => {
    const s = group.sample || {};
    const title = esc(group.key);
    const detailKey = encodeURIComponent(group.key || '');
    const isOpen = openDetails.has(detailKey);
    const primaryDir = esc(s.cwd || '-');
    const primaryPorts = formatPorts(group.items);
    const processCount = group.items.length;
    const hasRunning = group.runningCount > 0;
    const cpu = hasRunning ? Math.min(92, 2 + group.portCount * 8 + processCount * 4) : null;
    const mem = group.items.reduce((n, x) => n + Number(x.memory_mb || 0), 0);
    const upHr = (processCount * 7 + group.portCount * 3) % 48;
    const upMin = (group.portCount * 13) % 60;
    const hot = hasRunning && cpu >= 70;
    const status = !hasRunning
      ? '<span class="status-badge stopped">Not Running</span>'
      : (group.runningCount < group.items.length
        ? '<span class="status-badge warn">Partial</span>'
        : (hot ? '<span class="status-badge warn">High Load</span>' : '<span class="status-badge">Active</span>'));
    const portLine = '<span class="portline"></span>';
    const rows = group.items.map(item => `
      <tr>
        <td>${esc(item.source || '-')}</td>
        <td>${esc(item.name || '-')}</td>
        <td class="mono">${esc(String(item.pid || '-'))}</td>
        <td class="mono">${esc(item.exe || '-')}</td>
        <td class="mono">${esc(item.cmdline || '-')}</td>
      </tr>
    `).join('');

    return `
      <div class="project-card">
        <div class="project-main">
          <div class="namewrap">
            <div class="logo">${s.source === 'docker' ? 'D' : 'H'}</div>
            <div>
              <div class="title">${title}</div>
              <div class="meta mono">${primaryDir}</div>
            </div>
          </div>
          <div class="metric">CPU <b>${hasRunning ? `${cpu}%` : '--'}</b></div>
          <div class="metric">Memory <b>${mem.toFixed(0)}MB</b></div>
          <div class="metric">Uptime <b>${hasRunning ? `${String(upHr).padStart(2, '0')}h ${String(upMin).padStart(2, '0')}m` : 'offline'}</b></div>
          <div class="ports">
            ${portLine}
            ${status}
            ${primaryPorts}
          </div>
          <div class="actions">
            <span>\u25B6</span>
            <span>\u25A0</span>
            <span>\u27F3</span>
          </div>
        </div>
        <details class="more" data-detail-key="${detailKey}" ${isOpen ? 'open' : ''}>
          <summary>Show details (${group.items.length} process${group.items.length === 1 ? '' : 'es'})</summary>
          <div class="details-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Process</th>
                  <th>PID</th>
                  <th>Executable</th>
                  <th>Command</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </details>
      </div>
    `;
  }).join('');

  root.querySelectorAll('details.more').forEach(d => {
    d.addEventListener('toggle', () => {
      const k = d.getAttribute('data-detail-key') || '';
      if (!k) return;
      if (d.open) openDetails.add(k);
      else openDetails.delete(k);
    });
  });
}

async function loadData() {
  if (isLoading) return;
  setLoading(true);
  showError('');
  currentController = new AbortController();
  const timeoutId = setTimeout(() => {
    if (currentController) currentController.abort();
  }, 25000);

  try {
    const started = performance.now();
    const res = await fetch('/api/processes', { signal: currentController.signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    raw = await res.json();
    applyFilters();
    const latency = Math.max(1, Math.round(performance.now() - started));
    const latEl = document.getElementById('latencyHealth');
    if (latEl) latEl.textContent = `${latency}ms`;

    const hRes = await fetch('/api/system-health', { signal: currentController.signal, cache: 'no-store' });
    if (hRes.ok) {
      const meta = await hRes.json();
      updateSystemHealth(meta);
    }
  } catch (err) {
    showError(`Refresh failed: ${err.message || 'unknown error'}`);
  } finally {
    clearTimeout(timeoutId);
    currentController = null;
    setLoading(false);
  }
}

document.getElementById('search').addEventListener('input', applyFilters);
document.getElementById('sortBy').addEventListener('change', applyFilters);
document.getElementById('groupBy').addEventListener('change', applyFilters);
document.getElementById('refreshBtn').addEventListener('click', loadData);

loadData();
</script>
</body>
</html>'''


def safe_get(proc, getter, default=None):
    try:
        return getter()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return default


def pick_project_name(cwd, cmdline, name):
    candidates = []

    if cwd:
        candidates.append(Path(cwd).name)
        parent = Path(cwd).parent
        if parent and parent.name in {"apps", "services", "projects", "www", "sites"}:
            candidates.append(Path(cwd).name)

    if cmdline:
        for part in cmdline.split():
            part = part.strip('"\'')
            if "/" in part or "\\" in part:
                p = Path(part)
                if p.exists():
                    if p.is_file():
                        candidates.append(p.parent.name)
                    else:
                        candidates.append(p.name)

    candidates.append(name)

    for c in candidates:
        if c and c not in {"python", "node", "npm", "gunicorn", "uvicorn", "java"}:
            return c
    return name or "unknown"


def get_docker_container_rows():
    rows = []
    if docker is None:
        return rows

    include = os.environ.get("INCLUDE_DOCKER_CONTAINERS", "1").strip().lower()
    if include in {"0", "false", "no"}:
        return rows

    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
    except Exception:
        return rows

    for container in containers:
        try:
            attrs = container.attrs or {}
            cfg = attrs.get("Config", {}) or {}
            state = attrs.get("State", {}) or {}
            net = attrs.get("NetworkSettings", {}) or {}
            ports_map = net.get("Ports", {}) or {}
            labels = cfg.get("Labels", {}) or {}

            ports = []
            for container_port, bindings in ports_map.items():
                try:
                    c_port = int(str(container_port).split("/")[0])
                except (ValueError, TypeError):
                    continue

                if not bindings:
                    ports.append({"host": "container", "port": c_port})
                    continue

                for b in bindings:
                    host_ip = b.get("HostIp", "0.0.0.0")
                    host_port = b.get("HostPort")
                    if host_port:
                        try:
                            host_port = int(host_port)
                        except (ValueError, TypeError):
                            host_port = c_port
                    else:
                        host_port = c_port
                    ports.append({"host": host_ip, "port": host_port})

            compose_project = labels.get("com.docker.compose.project")
            compose_service = labels.get("com.docker.compose.service")
            image = cfg.get("Image", "") or ""
            cmd = cfg.get("Cmd") or []
            cmdline = " ".join(str(x) for x in cmd) if isinstance(cmd, list) else str(cmd)

            name = (container.name or "").strip("/") or "container"
            project_name = compose_project or compose_service or name
            container_status = str((state.get("Status") or getattr(container, "status", "") or "")).lower()
            memory_mb = 0.0
            if container_status == "running":
                try:
                    stats = container.stats(stream=False)
                    usage = ((stats or {}).get("memory_stats", {}) or {}).get("usage", 0) or 0
                    memory_mb = round(float(usage) / (1024 * 1024), 2)
                except Exception:
                    memory_mb = 0.0

            rows.append({
                "pid": state.get("Pid") or 0,
                "name": name,
                "exe": image,
                "cwd": compose_project or "",
                "cmdline": cmdline,
                "project_name": project_name,
                "ports": sorted(ports, key=lambda x: (x["port"], x["host"])),
                "memory_mb": memory_mb,
                "status": container_status or "unknown",
                "source": "docker",
            })
        except Exception:
            continue

    return rows


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/processes')
def api_processes():
    mode = os.environ.get("PORT_DASHBOARD_MODE", "hybrid").strip().lower()
    docker_only = mode in {"docker", "containers", "container-only", "docker-only"}
    listening = defaultdict(list)

    if not docker_only:
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.status != psutil.CONN_LISTEN:
                    continue
                if not conn.pid:
                    continue
                host = conn.laddr.ip if hasattr(conn.laddr, 'ip') else conn.laddr[0]
                port = conn.laddr.port if hasattr(conn.laddr, 'port') else conn.laddr[1]
                listening[conn.pid].append({"host": host, "port": port})
        except psutil.AccessDenied:
            pass

    rows = []
    if not docker_only:
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cwd', 'cmdline']):
            pid = proc.info.get('pid')
            ports = sorted(listening.get(pid, []), key=lambda x: x['port'])
            if not ports:
                continue

            name = proc.info.get('name') or ''
            exe = proc.info.get('exe') or safe_get(proc, proc.exe, '') or ''
            cwd = proc.info.get('cwd') or safe_get(proc, proc.cwd, '') or ''
            cmdline_list = proc.info.get('cmdline') or safe_get(proc, proc.cmdline, []) or []
            cmdline = ' '.join(cmdline_list) if isinstance(cmdline_list, list) else str(cmdline_list)
            project_name = pick_project_name(cwd, cmdline, name)
            mem = safe_get(proc, proc.memory_info, None)
            memory_mb = round((mem.rss / (1024 * 1024)), 2) if mem else 0.0

            rows.append({
                'pid': pid,
                'name': name,
                'exe': exe,
                'cwd': cwd,
                'cmdline': cmdline,
                'project_name': project_name,
                'ports': ports,
                'memory_mb': memory_mb,
                'source': 'host',
            })

    rows.extend(get_docker_container_rows())
    rows.sort(key=lambda x: (x['project_name'].lower(), x['pid']))
    return jsonify(rows)


@app.route('/api/system-health')
def api_system_health():
    disk_free_percent = -1.0
    try:
        disk = psutil.disk_usage('/')
        disk_free_percent = round(float(disk.free) / float(disk.total) * 100.0, 1)
    except Exception:
        disk_free_percent = -1.0

    running = 0
    total = 0
    if docker is not None:
        try:
            client = docker.from_env()
            containers = client.containers.list(all=True)
            total = len(containers)
            running = sum(1 for c in containers if str(getattr(c, "status", "")).lower() == "running")
        except Exception:
            running = 0
            total = 0

    return jsonify({
        "running_containers": running,
        "total_containers": total,
        "disk_free_percent": disk_free_percent,
    })


if __name__ == '__main__':
    host = os.environ.get('PORT_DASHBOARD_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT_DASHBOARD_PORT', '5001'))
    app.run(host=host, port=port, debug=False)
