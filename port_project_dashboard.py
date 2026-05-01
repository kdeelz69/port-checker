import os
import json
import socket
import base64
import hmac
import ipaddress
import time
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, Response, session, redirect, url_for

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
secret_key = os.environ.get("PORT_DASHBOARD_SECRET_KEY", "").strip()
if len(secret_key) < 32 or secret_key.lower() in {"change-this-secret-key", "changeme", "default", "secret"}:
    raise SystemExit("PORT_DASHBOARD_SECRET_KEY must be set to a strong value (min 32 chars).")
app.secret_key = secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("PORT_DASHBOARD_COOKIE_SECURE", "1").strip().lower() in {"1", "true", "yes"},
)
LOGIN_LIMIT_BUCKETS = {}


def _client_key():
    ip = _client_ip() or "unknown"
    ua = (request.headers.get("User-Agent") or "").strip()[:120]
    return f"{ip}|{ua}"


def _login_rate_limited():
    max_attempts = int(os.environ.get("PORT_DASHBOARD_LOGIN_MAX_ATTEMPTS", "8"))
    window_sec = int(os.environ.get("PORT_DASHBOARD_LOGIN_WINDOW_SEC", "300"))
    now = int(time.time())
    key = _client_key()
    times = LOGIN_LIMIT_BUCKETS.get(key, [])
    times = [t for t in times if now - t <= window_sec]
    LOGIN_LIMIT_BUCKETS[key] = times
    return len(times) >= max_attempts


def _record_login_failure():
    now = int(time.time())
    key = _client_key()
    times = LOGIN_LIMIT_BUCKETS.get(key, [])
    times.append(now)
    LOGIN_LIMIT_BUCKETS[key] = times


def _split_csv_env(name):
    raw = os.environ.get(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _client_ip():
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (request.remote_addr or "").strip()


def _ip_allowed(ip_text, allowed_entries):
    if not allowed_entries:
        return True
    if not ip_text:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    for entry in allowed_entries:
        try:
            if "/" in entry:
                if ip_obj in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if ip_obj == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


def _unauthorized_response():
    return Response("Unauthorized", 401)


def _is_authenticated(for_api=False):
    if session.get("authenticated") is True:
        return True

    # Optional IP allowlist gate.
    allowed_ips = _split_csv_env("PORT_DASHBOARD_ALLOWED_IPS")
    if allowed_ips and not _ip_allowed(_client_ip(), allowed_ips):
        return False

    # If neither auth method is configured, only allow when explicitly enabled.
    api_token = os.environ.get("PORT_DASHBOARD_API_TOKEN", "")
    user = os.environ.get("PORT_DASHBOARD_BASIC_AUTH_USER", "")
    pwd = os.environ.get("PORT_DASHBOARD_BASIC_AUTH_PASS", "")
    allow_anonymous = os.environ.get("PORT_DASHBOARD_ALLOW_ANONYMOUS", "0").strip().lower() in {"1", "true", "yes"}
    if not api_token and not (user and pwd):
        return allow_anonymous

    # Browser route auth is session-only so logout always works.
    if not for_api:
        return False

    # Token auth: X-API-Token or Authorization: Bearer <token>
    hdr_token = (request.headers.get("X-API-Token") or "").strip()
    authz = (request.headers.get("Authorization") or "").strip()
    bearer = ""
    if authz.lower().startswith("bearer "):
        bearer = authz[7:].strip()
    if api_token and (hmac.compare_digest(hdr_token, api_token) or hmac.compare_digest(bearer, api_token)):
        return True

    # Basic auth
    if user and pwd and authz.lower().startswith("basic "):
        enc = authz[6:].strip()
        try:
            decoded = base64.b64decode(enc).decode("utf-8")
            given_user, given_pwd = decoded.split(":", 1)
        except Exception:
            return False
        return hmac.compare_digest(given_user, user) and hmac.compare_digest(given_pwd, pwd)

    return False


@app.before_request
def enforce_security():
    if request.path in {"/login", "/logout"}:
        return None
    if request.path.startswith("/api/") or request.path == "/":
        if request.path.startswith("/api/"):
            if _is_authenticated(for_api=True):
                return None
            return _unauthorized_response()
        if _is_authenticated(for_api=False):
            return None
        return redirect(url_for("login"))
    return None


@app.after_request
def set_secure_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


LOGIN_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sign in - Port Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root { --bg:#f5f7fb; --card:#ffffff; --text:#1f2937; --muted:#6b7280; --line:#dbe2ec; --blue:#1a73e8; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; font-family:"Ubuntu",Arial,sans-serif; background:var(--bg); display:grid; place-items:center; color:var(--text); }
    .card { width:min(420px,92vw); background:var(--card); border:1px solid var(--line); border-radius:16px; padding:28px 24px; box-shadow:0 10px 30px rgba(15,23,42,.06); }
    .logo { width:44px; height:44px; border-radius:12px; background:#e8f0fe; color:var(--blue); font-weight:700; display:grid; place-items:center; margin-bottom:12px; }
    h1 { margin:0 0 6px; font-size:28px; }
    p { margin:0 0 18px; color:var(--muted); font-size:14px; }
    label { display:block; margin:0 0 6px; font-size:13px; color:#4b5563; }
    input { width:100%; border:1px solid var(--line); border-radius:12px; padding:12px; font-size:14px; margin-bottom:12px; }
    button { width:100%; border:1px solid #1557b0; background:var(--blue); color:#fff; border-radius:12px; padding:12px; font-size:14px; font-weight:500; cursor:pointer; }
    .err { margin:0 0 10px; color:#b42318; font-size:13px; }
  </style>
</head>
<body>
  <form method="post" class="card">
    <div class="logo">P</div>
    <h1>Sign in</h1>
    <p>Port Dashboard access</p>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
    {% if mode == 'basic' %}
      <label>Username</label>
      <input name="username" autocomplete="username" required />
      <label>Password</label>
      <input type="password" name="password" autocomplete="current-password" required />
    {% else %}
      <label>Access Token</label>
      <input type="password" name="token" autocomplete="off" required />
    {% endif %}
    <button type="submit">Next</button>
  </form>
</body>
</html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    api_token = os.environ.get("PORT_DASHBOARD_API_TOKEN", "")
    basic_user = os.environ.get("PORT_DASHBOARD_BASIC_AUTH_USER", "")
    basic_pass = os.environ.get("PORT_DASHBOARD_BASIC_AUTH_PASS", "")
    mode = "basic" if (basic_user and basic_pass) else "token"
    error = ""

    if request.method == "POST":
        if _login_rate_limited():
            return render_template_string(LOGIN_HTML, mode=mode, error="Too many attempts. Try again later."), 429
        if mode == "basic":
            u = str(request.form.get("username") or "")
            p = str(request.form.get("password") or "")
            if hmac.compare_digest(u, basic_user) and hmac.compare_digest(p, basic_pass):
                session["authenticated"] = True
                return redirect(url_for("index"))
        else:
            t = str(request.form.get("token") or "")
            if api_token and hmac.compare_digest(t, api_token):
                session["authenticated"] = True
                return redirect(url_for("index"))
        _record_login_failure()
        error = "Invalid credentials"

    if not api_token and not (basic_user and basic_pass):
        return Response("No auth method configured", 500)
    return render_template_string(LOGIN_HTML, mode=mode, error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    resp = redirect(url_for("login"))
    resp.delete_cookie(app.config.get("SESSION_COOKIE_NAME", "session"))
    return resp

HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Project Port Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f3f6fb;
      --panel: #ffffff;
      --line: #d6deea;
      --line-soft: #e8edf4;
      --text: #0d1730;
      --muted: #5f708a;
      --teal: #1fa687;
      --blue: #3566c9;
      --orange: #d08742;
      --danger: #cf5656;
      --ok-bg: #e5f7f1;
      --ok-fg: #18825f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Ubuntu", "Segoe UI", ui-sans-serif, system-ui, -apple-system, Arial, sans-serif;
      font-weight: 400;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      position: relative;
    }
    .wrap {
      width: 100%;
      max-width: 1320px;
      margin: 0 auto;
      padding: 28px 44px 44px;
      position: relative;
      z-index: 2;
    }
    .top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
    }
    .top-right {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 6px;
    }
    h1 {
      margin: 0;
      font-size: 58px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .sub {
      color: var(--muted);
      max-width: 760px;
      line-height: 1.35;
      font-size: 16px;
      font-weight: 500;
      margin: 0;
    }
    .sub-top-right {
      font-size: 12px;
      color: #4f6673;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 10px 16px;
      background: #f5f8fc;
      font-weight: 400;
    }
    .logout-btn {
      width: auto;
      border-radius: 999px;
      padding: 10px 14px;
      background: #ffffff;
      border: 1px solid var(--line);
      color: #1f2d44;
      font-size: 12px;
      font-weight: 500;
    }
    .toolbar {
      display: grid;
      grid-template-columns: 1fr auto 150px auto 150px 140px;
      gap: 12px;
      margin-bottom: 22px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 20px;
      padding: 24px;
      box-shadow: none;
    }
    input, select, button {
      width: 100%;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid var(--line-soft);
      background: #f8fbfa;
      color: var(--text);
      outline: none;
      font-size: 14px;
    }
    input::placeholder { color: #7789a2; }
    select { color: #4d5f6a; }
    .toolbar-label {
      display: flex;
      align-items: center;
      color: #7f93b1;
      font-size: 19px;
      font-weight: 500;
      letter-spacing: .08em;
      text-transform: uppercase;
      padding-left: 6px;
    }
    button {
      cursor: pointer;
      background: #0b1838;
      color: #eef3fb;
      font-weight: 500;
      border: 1px solid #091228;
    }
    input:focus, select:focus, button:focus {
      border-color: #80b9b0;
      box-shadow: 0 0 0 3px rgba(80, 158, 145, 0.16);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 30px;
      margin-bottom: 34px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 26px 30px;
      box-shadow: none;
      position: relative;
    }
    .stats .card::after {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 5px;
      border-radius: 0 0 20px 20px;
      background: #2f79ed;
    }
    .stats .card:nth-child(2)::after { background: #14b57a; }
    .stats .card:nth-child(3)::after { background: #8559f2; }
    .stats .card:nth-child(4)::after { background: #ef9413; }
    .stats .card .value {
      color: #0b1731;
    }
    #statUptime {
      font-size: 52px !important;
    }
    .label {
      color: #6e7b82;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .11em;
      margin-bottom: 10px;
      font-weight: 500;
    }
    .value {
      font-size: 52px;
      font-weight: 800;
      line-height: 1;
      display: inline-block;
    }
    .subvalue {
      margin-top: 7px;
      font-size: 11px;
      color: var(--muted);
    }
    .grid {
      display: grid;
      gap: 16px;
      padding: 0 6px;
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 10px 0 12px;
    }
    .section-title {
      font-size: 54px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .right-meta { display: flex; gap: 14px; }
    .meta-pill {
      font-size: 14px;
      color: #344965;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px 18px;
      background: #f8fbff;
      font-weight: 500;
    }
    .project-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 13px;
      overflow: hidden;
    }
    .project-main {
      display: grid;
      grid-template-columns: minmax(260px, 1.25fr) minmax(420px, 1fr) minmax(360px, auto);
      gap: 20px;
      align-items: center;
      padding: 16px 16px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(110px, 1fr));
      gap: 16px;
      align-items: center;
    }
    .namewrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .namecol {
      display: grid;
      gap: 9px;
    }
    .logo {
      width: 40px;
      height: 40px;
      border-radius: 9px;
      background: #138f8f;
      color: #fff;
      font-size: 18px;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .title {
      font-size: 38px;
      font-weight: 750;
      margin: 0 0 3px;
    }
    .meta {
      color: #74858e;
      font-size: 13px;
      word-break: break-word;
    }
    .metric {
      font-size: 11px;
      color: #6d7d85;
      text-transform: uppercase;
      font-weight: 500;
      letter-spacing: .05em;
      white-space: nowrap;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;
      line-height: 1.05;
    }
    .metric b {
      margin-left: 0;
      color: #183542;
      font-size: 33px;
      letter-spacing: 0;
      text-transform: none;
      line-height: 1;
    }
    .ports {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      min-height: 38px;
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
      font-size: 12px;
      color: #1e7d6b;
      font-weight: 500;
    }
    .chip.warn {
      border: 1px solid #e2c8b3;
      background: #fff2e7;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      color: var(--orange);
      font-weight: 500;
    }
    .status-badge {
      font-size: 13px;
      border-radius: 999px;
      padding: 6px 11px;
      border: 1px solid #b8ddd4;
      background: var(--ok-bg);
      color: var(--ok-fg);
      font-weight: 500;
      text-transform: uppercase;
      white-space: nowrap;
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
      gap: 8px;
      justify-content: flex-start;
      flex-wrap: wrap;
      color: #80929b;
      font-size: 13px;
      font-weight: 500;
    }
    .action-btn {
      border: 1px solid #bdd1cd;
      background: #eef5f3;
      color: #355e64;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      width: auto;
      min-width: 74px;
      transition: background .15s ease, border-color .15s ease, transform .06s ease;
      white-space: nowrap;
    }
    .action-btn:hover { background: #e3efec; border-color: #aac7c1; }
    .action-btn:active { transform: translateY(1px); }
    .action-btn:disabled {
      opacity: .55;
      cursor: not-allowed;
    }
    details.more {
      border-top: 1px solid var(--line-soft);
      background: #f2f6f5;
    }
    details.more > summary {
      list-style: none;
      cursor: pointer;
      padding: 10px 20px;
      color: #56707b;
      font-size: 13px;
      font-weight: 500;
      text-align: center;
      user-select: none;
      border-top: 1px solid var(--line-soft);
    }
    details.more > summary::-webkit-details-marker { display: none; }
    .details-wrap { padding: 0 20px 12px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      overflow: hidden;
      background: #f8fbfa;
    }
    th, td {
      text-align: left;
      padding: 8px 10px;
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
      border-radius: 12px;
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
    @media (max-width: 1200px) {
      .project-main {
        grid-template-columns: minmax(220px, 1.2fr) 1fr;
      }
      .metrics { grid-template-columns: repeat(3, minmax(90px, 1fr)); }
      .ports { grid-column: 1 / -1; justify-content: flex-start; }
    }
    @media (max-width: 900px) {
      h1 { font-size: 34px; }
      .top { flex-direction: column; align-items: stretch; }
      .toolbar, .stats { grid-template-columns: 1fr; }
      .project-main { grid-template-columns: 1fr; }
      .actions { justify-content: flex-start; }
      .dashboard-bottom { grid-template-columns: 1fr; }
      .ports { margin-top: 4px; }
    }
    @media (max-width: 560px) {
      h1 { font-size: 28px; }
      .section-title { font-size: 30px; }
      .right-meta { display: none; }
      .wrap { padding: 18px 16px 28px; }
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
      <div class="top-right">
        <div class="sub-top-right">Last Refresh: <span id="topRefresh">--:--:--</span></div>
        <form method="post" action="/logout" style="margin:0">
          <button type="submit" class="logout-btn">Logout</button>
        </form>
      </div>
    </div>
    <div id="errorBanner" class="error-banner"></div>

    <div class="toolbar">
      <input id="search" placeholder="Search project, path, process, command, or port" />
      <div class="toolbar-label">Sort</div>
      <select id="sortBy" title="Sort">
        <option value="project">Name</option>
        <option value="ports">Port count</option>
        <option value="processes">Process count</option>
      </select>
      <div class="toolbar-label">Group</div>
      <select id="groupBy" title="Group">
        <option value="project">Project</option>
        <option value="cwd">Working dir</option>
        <option value="exe">Executable path</option>
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
      <div class="section-title"></div>
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
let protectedNames = [];

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
  document.getElementById('statUptime').textContent = '--';
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
  const pn = meta?.protected_names;
  protectedNames = Array.isArray(pn) ? pn.map(x => String(x || '').trim()).filter(Boolean) : [];
}

async function runContainerAction(action, names) {
  if (!Array.isArray(names) || !names.length) return;
  if ((action === 'stop' || action === 'restart') && protectedNames.length) {
    const targetSet = new Set(names.map(x => String(x || '').trim().toLowerCase()));
    const risky = protectedNames.filter(x => targetSet.has(String(x).toLowerCase()));
    if (risky.length) {
      const msg = action === 'stop'
        ? `Warning: You are trying to STOP the dashboard container (${risky.join(', ')}). This can make the UI unavailable. Continue?`
        : `Warning: You are trying to RESTART the dashboard container (${risky.join(', ')}). UI may disconnect briefly. Continue?`;
      if (!window.confirm(msg)) return;
    }
  }
  setLoading(true);
  showError('');
  try {
    const res = await fetch('/api/container-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, names }),
      cache: 'no-store',
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const out = await res.json();
    if (out && out.ok === false) throw new Error(out.error || 'action failed');
    setLoading(false);
    await loadData();
  } catch (err) {
    showError(`Action failed: ${err.message || 'unknown error'}`);
  } finally {
    setLoading(false);
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
    const cpu = null;
    const mem = group.items.reduce((n, x) => n + Number(x.memory_mb || 0), 0);
    const hot = false;
    const status = !hasRunning
      ? '<span class="status-badge stopped">Not Running</span>'
      : (group.runningCount < group.items.length
        ? '<span class="status-badge warn">Partial</span>'
        : (hot ? '<span class="status-badge warn">High Load</span>' : '<span class="status-badge">Active</span>'));
    const portLine = '<span class="portline"></span>';
    const containerNames = [...new Set(group.items.filter(x => x.source === 'docker').map(x => x.name).filter(Boolean))];
    const canControl = containerNames.length > 0;
    const canStart = canControl && group.runningCount < group.items.length;
    const canStop = canControl && group.runningCount > 0;
    const namesPayload = containerNames.map(n => encodeURIComponent(String(n))).join(',');
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
          <div class="namecol">
            <div class="namewrap">
              <div class="logo">${s.source === 'docker' ? 'D' : 'H'}</div>
              <div>
                <div class="title">${title}</div>
                <div class="meta mono">${primaryDir}</div>
              </div>
            </div>
            <div class="actions">
              <button type="button" class="action-btn js-action" data-action="start" data-names="${namesPayload}" ${canStart ? '' : 'disabled'}>Start</button>
              <button type="button" class="action-btn js-action" data-action="stop" data-names="${namesPayload}" ${canStop ? '' : 'disabled'}>Stop</button>
              <button type="button" class="action-btn js-action" data-action="restart" data-names="${namesPayload}" ${canControl ? '' : 'disabled'}>Restart</button>
            </div>
          </div>
          <div class="metrics">
            <div class="metric">CPU <b>n/a</b></div>
            <div class="metric">Memory <b>${mem.toFixed(0)}MB</b></div>
            <div class="metric">Uptime <b>n/a</b></div>
          </div>
          <div class="ports">
            ${portLine}
            ${status}
            ${primaryPorts}
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

  root.querySelectorAll('.js-action').forEach(btn => {
    btn.addEventListener('click', async () => {
      const action = btn.getAttribute('data-action');
      const namesRaw = btn.getAttribute('data-names') || '';
      const names = namesRaw
        .split(',')
        .map(x => x.trim())
        .filter(Boolean)
        .map(x => decodeURIComponent(x));
      if (!action || !names.length) return;
      await runContainerAction(action, names);
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
                    host_ip = b.get("HostIp") or "unknown"
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
        except Exception as exc:
            app.logger.debug("Skipping container row due to parsing error: %s", exc)

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


@app.route('/api/container-action', methods=['POST'])
def api_container_action():
    actions_enabled = os.environ.get("PORT_DASHBOARD_ENABLE_ACTIONS", "0").strip().lower()
    if actions_enabled not in {"1", "true", "yes"}:
        return jsonify({"ok": False, "error": "Container actions are disabled"}), 403

    if docker is None:
        return jsonify({"ok": False, "error": "Docker SDK is not available"}), 500

    payload = request.get_json(silent=True) or {}
    action = str(payload.get('action') or '').strip().lower()
    names = payload.get('names') or []
    if action not in {'start', 'stop', 'restart'}:
        return jsonify({"ok": False, "error": "Invalid action"}), 400
    if not isinstance(names, list) or not names:
        return jsonify({"ok": False, "error": "No container names provided"}), 400

    try:
        client = docker.from_env()
    except Exception:
        return jsonify({"ok": False, "error": "Cannot connect to Docker Engine"}), 500

    results = []
    for raw_name in names:
        name = str(raw_name or '').strip().strip('/')
        if not name:
            continue
        try:
            c = client.containers.get(name)
            if action == 'start':
                c.start()
            elif action == 'stop':
                c.stop(timeout=10)
            else:
                c.restart(timeout=10)
            results.append({"name": name, "ok": True})
        except Exception as exc:
            results.append({"name": name, "ok": False, "error": str(exc)})

    ok = all(r.get("ok") for r in results) if results else False
    return jsonify({"ok": ok, "results": results}), (200 if ok else 207)


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

    protected_raw = os.environ.get("PORT_DASHBOARD_PROTECTED_NAMES", "port-dashboard")
    protected_names = [x.strip() for x in protected_raw.split(",") if x.strip()]

    return jsonify({
        "running_containers": running,
        "total_containers": total,
        "disk_free_percent": disk_free_percent,
        "protected_names": protected_names,
    })


if __name__ == '__main__':
    host = os.environ.get('PORT_DASHBOARD_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT_DASHBOARD_PORT', '5001'))
    app.run(host=host, port=port, debug=False)
