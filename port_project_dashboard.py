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
      --bg: #0b1020;
      --panel: #141a2f;
      --panel-2: #1a2140;
      --text: #eef2ff;
      --muted: #a9b3d1;
      --line: #2a345f;
      --accent: #7aa2ff;
      --good: #3ddc97;
      --warn: #ffcc66;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: linear-gradient(180deg, #0b1020 0%, #0f1630 100%);
      color: var(--text);
    }
    .wrap {
      max-width: 1300px;
      margin: 0 auto;
      padding: 24px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 30px;
    }
    .sub {
      color: var(--muted);
      margin-bottom: 20px;
    }
    .toolbar {
      display: grid;
      grid-template-columns: 1fr 180px 160px 120px;
      gap: 12px;
      margin-bottom: 18px;
    }
    input, select, button {
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      outline: none;
    }
    button {
      cursor: pointer;
      background: var(--accent);
      color: #081127;
      font-weight: 700;
      border: none;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .card {
      background: rgba(20, 26, 47, 0.9);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 12px 30px rgba(0,0,0,.18);
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 4px;
    }
    .value {
      font-size: 26px;
      font-weight: 800;
    }
    .grid {
      display: grid;
      gap: 14px;
    }
    .project-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 12px;
    }
    .project-title {
      font-size: 20px;
      font-weight: 800;
      margin-bottom: 6px;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      word-break: break-word;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .chip {
      background: var(--panel-2);
      border: 1px solid var(--line);
      color: var(--text);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
    }
    .chip.good { color: var(--good); }
    .chip.warn { color: var(--warn); }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      overflow: hidden;
      border-radius: 12px;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
      vertical-align: top;
      word-break: break-word;
    }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    .empty { text-align: center; color: var(--muted); padding: 30px; }
    @media (max-width: 900px) {
      .toolbar, .stats { grid-template-columns: 1fr; }
      .project-head { flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Project Port Dashboard</h1>
    <div class="sub">See which project is listening on which port, plus PID, executable path, working directory, and command.</div>

    <div class="toolbar">
      <input id="search" placeholder="Search project, path, process, command, or port" />
      <select id="sortBy">
        <option value="project">Sort: Project</option>
        <option value="ports">Sort: Port count</option>
        <option value="processes">Sort: Process count</option>
      </select>
      <select id="groupBy">
        <option value="project">Group: Project</option>
        <option value="cwd">Group: Working dir</option>
        <option value="exe">Group: Executable path</option>
      </select>
      <button id="refreshBtn">Refresh</button>
    </div>

    <div class="stats">
      <div class="card"><div class="label">Projects</div><div class="value" id="statProjects">0</div></div>
      <div class="card"><div class="label">Listening Ports</div><div class="value" id="statPorts">0</div></div>
      <div class="card"><div class="label">Processes</div><div class="value" id="statProcesses">0</div></div>
      <div class="card"><div class="label">Last Refresh</div><div class="value" id="statRefresh" style="font-size:18px">-</div></div>
    </div>

    <div id="projects" class="grid"></div>
  </div>

<script>
let raw = [];

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
  let ports = 0, processes = 0;
  groups.forEach(g => {
    processes += g.items.length;
    g.items.forEach(p => ports += (p.ports || []).length);
  });
  document.getElementById('statProjects').textContent = groups.length;
  document.getElementById('statPorts').textContent = ports;
  document.getElementById('statProcesses').textContent = processes;
  document.getElementById('statRefresh').textContent = new Date().toLocaleTimeString();
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
  }));
}

function applyFilters() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const sortBy = document.getElementById('sortBy').value;
  const groupBy = document.getElementById('groupBy').value;

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
    const subtitle = groupBy === 'project'
      ? `<div class="meta">Primary dir: ${esc(s.cwd || '-')}<br>Executable: ${esc(s.exe || '-')}</div>`
      : `<div class="meta">Project: ${esc(s.project_name || '-')}</div>`;

    const rows = group.items.map(item => `
      <tr>
        <td>${esc(item.source || '-')}</td>
        <td>${esc(item.name || '-')}</td>
        <td class="mono">${esc(String(item.pid || '-'))}</td>
        <td>${(item.ports || []).map(p => `<span class="chip good">${esc((p.host || '0.0.0.0') + ':' + p.port)}</span>`).join(' ') || '<span class="chip warn">-</span>'}</td>
        <td class="mono">${esc(item.cwd || '-')}</td>
        <td class="mono">${esc(item.exe || '-')}</td>
        <td class="mono">${esc(item.cmdline || '-')}</td>
      </tr>
    `).join('');

    return `
      <div class="card">
        <div class="project-head">
          <div>
            <div class="project-title">${title}</div>
            ${subtitle}
          </div>
          <div class="chips">
            <span class="chip">Processes: ${group.items.length}</span>
            <span class="chip">Ports: ${group.portCount}</span>
            ${formatPorts(group.items)}
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>Process</th>
              <th>PID</th>
              <th>Ports</th>
              <th>Working Dir</th>
              <th>Executable</th>
              <th>Command</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }).join('');
}

async function loadData() {
  const res = await fetch('/api/processes');
  raw = await res.json();
  applyFilters();
}

document.getElementById('search').addEventListener('input', applyFilters);
document.getElementById('sortBy').addEventListener('change', applyFilters);
document.getElementById('groupBy').addEventListener('change', applyFilters);
document.getElementById('refreshBtn').addEventListener('click', loadData);

loadData();
setInterval(loadData, 10000);
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
        containers = client.containers.list()
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

            if not ports:
                continue

            compose_project = labels.get("com.docker.compose.project")
            compose_service = labels.get("com.docker.compose.service")
            image = cfg.get("Image", "") or ""
            cmd = cfg.get("Cmd") or []
            cmdline = " ".join(str(x) for x in cmd) if isinstance(cmd, list) else str(cmd)

            name = (container.name or "").strip("/") or "container"
            project_name = compose_project or compose_service or name

            rows.append({
                "pid": state.get("Pid") or 0,
                "name": name,
                "exe": image,
                "cwd": compose_project or "",
                "cmdline": cmdline,
                "project_name": project_name,
                "ports": sorted(ports, key=lambda x: (x["port"], x["host"])),
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
    listening = defaultdict(list)

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

        rows.append({
            'pid': pid,
            'name': name,
            'exe': exe,
            'cwd': cwd,
            'cmdline': cmdline,
            'project_name': project_name,
            'ports': ports,
            'source': 'host',
        })

    rows.extend(get_docker_container_rows())
    rows.sort(key=lambda x: (x['project_name'].lower(), x['pid']))
    return jsonify(rows)


if __name__ == '__main__':
    host = os.environ.get('PORT_DASHBOARD_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT_DASHBOARD_PORT', '5001'))
    app.run(host=host, port=port, debug=False)
