#!/usr/bin/env python3
"""Local web dashboard for Flip's trading desk.

Stdlib-only HTTP server: no new dependencies. Serves a single-page UI
plus a small JSON API that shells out to the same audited scripts the
Discord bot uses. Desk runs execute one at a time (same token-spam guard
as the bot). Binds 127.0.0.1 by default — set FLIP_DESK_UI_HOST=0.0.0.0
only on a trusted network; there is no auth layer.

    python webui/server.py            # http://127.0.0.1:8787
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
LEDGER = RUNS / "desk_ledger.sqlite3"
PYTHON = sys.executable

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except Exception:
    pass

HOST = os.getenv("FLIP_DESK_UI_HOST", "127.0.0.1")
PORT = int(os.getenv("FLIP_DESK_UI_PORT", "8787"))
CAP = int(os.getenv("FLIP_DESK_MONTHLY_LLM_CALL_CAP", "250"))
SCAN_TIMEOUT = int(os.getenv("FLIP_DESK_SCAN_TIMEOUT_SECONDS", "180"))
RUN_TIMEOUT = int(os.getenv("FLIP_DESK_ANALYSIS_TIMEOUT_SECONDS", "1800"))

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-_]{1,24}$")
FILE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,120}\.json$")

jobs: dict[str, dict] = {}
jobs_guard = threading.Lock()
desk_busy = threading.Lock()  # one expensive run at a time


def _clean_symbols(raw: str) -> str:
    parts = [p.strip().upper() for p in (raw or "").replace(" ", ",").split(",") if p.strip()]
    if not parts or len(parts) > 30 or any(not SYMBOL_RE.match(p) for p in parts):
        raise ValueError("bad symbols")
    return ",".join(parts)


def _job(kind: str, label: str) -> dict:
    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "label": label,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output_tail": "",
        "result_file": None,
        "error": None,
    }
    with jobs_guard:
        jobs[job["id"]] = job
    return job


def _run_subprocess(job: dict, cmd: list, out_path: Path, timeout: int, exclusive: bool) -> None:
    def work():
        lock_held = False
        try:
            if exclusive:
                if not desk_busy.acquire(blocking=False):
                    job.update(status="error", error="another desk run is already in progress")
                    return
                lock_held = True
            proc = subprocess.run(
                cmd, cwd=ROOT, text=True, timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            job["output_tail"] = (proc.stdout or "")[-4000:]
            if out_path.exists():
                job["result_file"] = out_path.name
                job["status"] = "done" if proc.returncode == 0 else "done_with_errors"
            elif proc.returncode == 0:
                job["status"] = "done"
            else:
                job.update(status="error", error=f"exit code {proc.returncode}")
        except subprocess.TimeoutExpired:
            job.update(status="error", error="timed out")
        except Exception as exc:
            job.update(status="error", error=repr(exc))
        finally:
            if lock_held:
                desk_busy.release()

    threading.Thread(target=work, daemon=True).start()


def start_scan(symbols: str) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RUNS / f"ui_scan_{stamp}.json"
    job = _job("scan", f"scan {symbols}")
    cmd = [PYTHON, "scripts/scan_watchlist.py", "--symbols", symbols,
           "--max-finalists", os.getenv("FLIP_DESK_MAX_FINALISTS", "5"), "--out", str(out)]
    _run_subprocess(job, cmd, out, SCAN_TIMEOUT, exclusive=False)
    return job


def start_run(ticker: str, mode: str, profile: str | None) -> dict:
    if not SYMBOL_RE.match(ticker):
        raise ValueError("bad ticker")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RUNS / f"ui_{ticker}_{stamp}.json"
    cmd = [PYTHON, "scripts/run_desk_analysis.py", ticker, "--json-out", str(out)]
    if mode == "preflight":
        cmd.append("--preflight-only")
    elif mode == "full":
        cmd.append("--full")
    elif mode != "desk":
        raise ValueError("bad mode")
    if profile:
        if profile not in ("cheap", "balanced", "local", "offline"):
            raise ValueError("bad profile")
        cmd += ["--model-profile", profile]
    label = f"{mode} {ticker}" + (f" [{profile}]" if profile else "")
    job = _job("run", label)
    exclusive = mode != "preflight"
    timeout = SCAN_TIMEOUT if mode == "preflight" else RUN_TIMEOUT
    _run_subprocess(job, cmd, out, timeout, exclusive=exclusive)
    return job


def state_payload() -> dict:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    budget = {"month": month, "cap": CAP, "used": 0, "runs": 0, "recent": []}
    if LEDGER.exists():
        with sqlite3.connect(LEDGER) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(COALESCE(actual_llm_calls, estimated_llm_calls)), 0), COUNT(*) "
                "FROM runs WHERE month = ? AND status != 'blocked'", (month,)).fetchone()
            budget["used"], budget["runs"] = int(row[0] or 0), int(row[1] or 0)
            budget["recent"] = [
                {"at": r[0][:16], "ticker": r[1], "status": r[2],
                 "calls": r[3] if r[3] is not None else r[4]}
                for r in conn.execute(
                    "SELECT created_at, ticker, status, actual_llm_calls, estimated_llm_calls "
                    "FROM runs ORDER BY id DESC LIMIT 8")
            ]
    files = sorted(RUNS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:12] if RUNS.exists() else []
    provider = os.getenv("FLIP_DESK_LLM_PROVIDER") or os.getenv("TRADINGAGENTS_LLM_PROVIDER") or "deepseek"
    return {
        "budget": budget,
        "files": [f.name for f in files],
        "provider": provider,
        "data_source": os.getenv("FLIP_DESK_DATA_SOURCE", "auto"),
        "alpaca_keys": bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")),
        "llm_key": bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
                        or os.getenv("OPENROUTER_API_KEY") or os.getenv("FLIP_DESK_LLM_API_KEY")),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "FlipDesk/1.0"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/api/state":
            self._json(200, state_payload())
        elif parsed.path.startswith("/api/jobs/"):
            job = jobs.get(parsed.path.rsplit("/", 1)[-1])
            self._json(200 if job else 404, job or {"error": "unknown job"})
        elif parsed.path == "/api/file":
            name = (parse_qs(parsed.query).get("name") or [""])[0]
            if not FILE_RE.match(name) or not (RUNS / name).exists():
                self._json(404, {"error": "unknown file"})
                return
            self._send(200, (RUNS / name).read_bytes(), "application/json")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return
        try:
            if self.path == "/api/scan":
                symbols = _clean_symbols(body.get("symbols") or os.getenv(
                    "FLIP_DESK_DEFAULT_SYMBOLS", "SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META"))
                self._json(200, start_scan(symbols))
            elif self.path == "/api/run":
                ticker = (body.get("ticker") or "").strip().upper()
                self._json(200, start_run(ticker, body.get("mode") or "desk", body.get("profile")))
            else:
                self._json(404, {"error": "not found"})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[webui] {self.address_string()} {fmt % args}", flush=True)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flip Trading Desk</title>
<style>
:root{--ground:#F6F7F4;--surface:#FFF;--line:#DDE3DE;--ink:#1B2528;--muted:#5C6B6D;--faint:#8A9896;
--accent:#0F6B68;--accent-soft:#E1EEEC;--bull:#22713F;--bull-soft:#E3EFE6;--bear:#A93A31;--bear-soft:#F5E7E4;
--hold:#9A6B14;--hold-soft:#F4EBD8;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme: dark){:root{--ground:#0F1517;--surface:#161E20;--line:#26332F;--ink:#E4EBE8;
--muted:#9AABA8;--faint:#6E7F7C;--accent:#4CBBB4;--accent-soft:#14312F;--bull:#5CB981;--bull-soft:#16301F;
--bear:#E2695F;--bear-soft:#3A1D19;--hold:#D9A64C;--hold-soft:#34290F}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);line-height:1.5}
.wrap{max-width:960px;margin:0 auto;padding:0 18px 60px}
header{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:18px 0;border-bottom:1px solid var(--line);
font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
header .spacer{flex:1}
.chip{font-family:var(--mono);font-size:11px;padding:3px 9px;border-radius:999px;white-space:nowrap}
.chip.ok{background:var(--bull-soft);color:var(--bull)}
.chip.warn{background:var(--bear-soft);color:var(--bear)}
.chip.info{background:var(--accent-soft);color:var(--accent)}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:22px}
@media(max-width:720px){.controls{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.panel h2{font-size:13px;font-family:var(--mono);letter-spacing:.1em;text-transform:uppercase;
color:var(--muted);margin:0 0 12px;font-weight:600}
.row{display:flex;gap:8px;flex-wrap:wrap}
input[type=text]{flex:1;min-width:120px;background:var(--ground);border:1px solid var(--line);border-radius:8px;
padding:9px 12px;color:var(--ink);font-family:var(--mono);font-size:14px;text-transform:uppercase}
input[type=text]:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}
button{border:0;border-radius:8px;padding:9px 16px;font-family:var(--mono);font-size:13px;font-weight:600;
cursor:pointer;background:var(--accent);color:#fff}
button.ghost{background:var(--accent-soft);color:var(--accent)}
button:disabled{opacity:.5;cursor:wait}
button:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.hint{font-size:12px;color:var(--faint);margin-top:9px}
.meter{height:10px;border-radius:5px;background:var(--line);overflow:hidden;margin-top:8px}
.meter div{height:100%;background:var(--accent);border-radius:5px;min-width:6px;transition:width .4s}
.meter-label{display:flex;justify-content:space-between;font-family:var(--mono);font-size:12px;color:var(--muted)}
.meter-label b{color:var(--ink);font-size:14px}
#status{margin-top:20px;font-family:var(--mono);font-size:13px;color:var(--accent);min-height:20px}
#status.err{color:var(--bear)}
.result{margin-top:14px}
.decision-word{font-family:var(--mono);font-size:30px;font-weight:700;letter-spacing:.12em}
.decision-word.BUY{color:var(--bull)}.decision-word.SELL{color:var(--bear)}
.decision-word.HOLD{color:var(--hold)}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:12px}
.kv .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}
.kv .v{font-size:14px;margin-top:2px}
details{margin-top:10px;border-top:1px dashed var(--line);padding-top:8px}
details summary{cursor:pointer;font-family:var(--mono);font-size:12.5px;color:var(--accent);font-weight:600}
details pre{white-space:pre-wrap;font-size:13px;font-family:var(--sans);color:var(--ink);margin:8px 0 0}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);
text-align:left;padding:4px 8px 6px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--line)}
td.sym{font-family:var(--mono);font-weight:700}
td.num{font-family:var(--mono)}
.pill{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:999px}
.pill.long{background:var(--bull-soft);color:var(--bull)}
.pill.neutral{background:var(--accent-soft);color:var(--accent)}
.pill.completed{background:var(--bull-soft);color:var(--bull)}
.pill.blocked,.pill.error{background:var(--bear-soft);color:var(--bear)}
.pill.preflight{background:var(--hold-soft);color:var(--hold)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
@media(max-width:720px){.grid2{grid-template-columns:1fr}}
.filelist{list-style:none;margin:0;padding:0;font-family:var(--mono);font-size:12.5px}
.filelist li{padding:5px 0;border-bottom:1px dashed var(--line)}
.filelist a{color:var(--accent);text-decoration:none;cursor:pointer}
.filelist a:hover{text-decoration:underline}
.overflow{overflow-x:auto}
</style>
</head>
<body>
<div class="wrap">
<header>
  <span>Flip Trading Desk</span><span class="spacer"></span>
  <span id="chip-llm" class="chip">llm…</span>
  <span id="chip-data" class="chip">data…</span>
</header>

<div class="controls">
  <div class="panel">
    <h2>Analyze a ticker</h2>
    <div class="row">
      <input type="text" id="ticker" placeholder="AAPL" maxlength="10" autocomplete="off">
      <button id="btn-desk" onclick="runDesk('desk')">Run desk · 8 calls</button>
      <button class="ghost" onclick="runDesk('preflight')">Preflight · free</button>
    </div>
    <div class="hint">Desk runs execute one at a time. Full 4-analyst stack: type ticker, hold Shift while clicking Run.</div>
  </div>
  <div class="panel">
    <h2>Watchlist scan · zero LLM</h2>
    <div class="row">
      <input type="text" id="symbols" placeholder="default watchlist" autocomplete="off">
      <button class="ghost" onclick="runScan()">Scan</button>
    </div>
    <div class="hint">Comma or space separated. Free — uses market data only.</div>
  </div>
</div>

<div id="status" role="status"></div>
<div id="result" class="result"></div>

<div class="grid2">
  <div class="panel">
    <h2>Monthly budget</h2>
    <div class="meter-label"><span id="budget-month"></span><b id="budget-used"></b></div>
    <div class="meter"><div id="budget-fill" style="width:0%"></div></div>
    <div class="overflow" style="margin-top:12px">
      <table><thead><tr><th>When (UTC)</th><th>Ticker</th><th>Status</th><th>Calls</th></tr></thead>
      <tbody id="ledger-rows"></tbody></table>
    </div>
  </div>
  <div class="panel">
    <h2>Saved artifacts</h2>
    <ul class="filelist" id="files"></ul>
  </div>
</div>
</div>

<script>
const $ = id => document.getElementById(id);
let busy = false;

async function refresh(){
  const s = await (await fetch('/api/state')).json();
  $('chip-llm').textContent = 'llm · ' + s.provider + (s.llm_key ? '' : ' · no key');
  $('chip-llm').className = 'chip ' + (s.llm_key ? 'ok' : 'warn');
  $('chip-data').textContent = 'data · ' + (s.alpaca_keys ? 'alpaca' : 'yahoo');
  $('chip-data').className = 'chip ' + (s.alpaca_keys ? 'ok' : 'info');
  const b = s.budget;
  $('budget-month').textContent = b.month + ' · ' + b.runs + ' runs';
  $('budget-used').textContent = b.used + ' / ' + b.cap;
  $('budget-fill').style.width = Math.min(100, 100 * b.used / b.cap) + '%';
  $('ledger-rows').innerHTML = b.recent.map(r =>
    `<tr><td class="num">${r.at.replace('T',' ')}</td><td class="sym">${r.ticker}</td>` +
    `<td><span class="pill ${r.status}">${r.status}</span></td><td class="num">${r.calls ?? '—'}</td></tr>`).join('')
    || '<tr><td colspan="4" style="color:var(--faint)">no runs yet</td></tr>';
  $('files').innerHTML = s.files.map(f =>
    `<li><a onclick="openFile('${f}')">${f}</a></li>`).join('') ||
    '<li style="color:var(--faint)">nothing saved yet</li>';
}

function setStatus(msg, err){ const el = $('status'); el.textContent = msg; el.className = err ? 'err' : ''; }

async function poll(job){
  while (true){
    await new Promise(r => setTimeout(r, 1500));
    const j = await (await fetch('/api/jobs/' + job.id)).json();
    if (j.status !== 'running') return j;
    setStatus('⏳ ' + j.label + ' — running…');
  }
}

async function launch(url, payload, doneMsg){
  if (busy) return;
  busy = true; document.querySelectorAll('button').forEach(b => b.disabled = true);
  try {
    const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const job = await res.json();
    if (!res.ok){ setStatus('✗ ' + (job.error || 'request failed'), true); return; }
    setStatus('⏳ ' + job.label + ' — started…');
    const done = await poll(job);
    if (done.status === 'error'){ setStatus('✗ ' + done.label + ' — ' + done.error, true); }
    else {
      setStatus('✓ ' + done.label + ' — ' + doneMsg);
      if (done.result_file) await openFile(done.result_file);
    }
  } finally {
    busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false);
    refresh();
  }
}

function runDesk(mode){
  const t = $('ticker').value.trim().toUpperCase();
  if (!t){ setStatus('enter a ticker first', true); return; }
  if (mode === 'desk' && window.event && window.event.shiftKey) mode = 'full';
  launch('/api/run', {ticker: t, mode: mode}, 'complete');
}
function runScan(){ launch('/api/scan', {symbols: $('symbols').value.trim()}, 'complete'); }

async function openFile(name){
  const p = await (await fetch('/api/file?name=' + encodeURIComponent(name))).json();
  const el = $('result');
  if (p.finalists || p.ranked){ el.innerHTML = renderScan(p, name); }
  else { el.innerHTML = renderRun(p, name); }
  el.scrollIntoView({behavior:'smooth', block:'nearest'});
}

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function renderScan(p, name){
  const rows = (p.ranked || []).map(r =>
    `<tr><td class="sym">${esc(r.symbol)}</td><td class="num">${esc(r.score)}</td>` +
    `<td><span class="pill ${esc(r.bias)}">${esc(r.bias)}</span></td>` +
    `<td class="num">${esc(r.close ?? '—')}</td><td class="num">${esc(r.rsi14 ?? '—')}</td>` +
    `<td>${esc((r.why||[]).slice(0,3).join(', ') || (r.risk_flags||[]).join(', '))}</td></tr>`).join('');
  return `<div class="panel"><h2>Scan · ${esc(name)}</h2><div class="overflow"><table>` +
    `<thead><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Close</th><th>RSI</th><th>Notes</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div></div>`;
}

function renderRun(p, name){
  const d = p.decision || {};
  const u = p.usage || {};
  const head = p.status === 'preflight'
    ? `<div class="decision-word HOLD">PREFLIGHT</div>`
    : `<div class="decision-word ${esc(d.action||'HOLD')}">${esc(d.action || p.status || '—')}</div>`;
  const reports = Object.entries(p.reports || {}).map(([k, v]) =>
    `<details><summary>${esc(k)}</summary><pre>${esc(v)}</pre></details>`).join('');
  return `<div class="panel"><h2>${esc(p.ticker || '')} · ${esc(name)}</h2>${head}` +
    `<div class="kv">` +
    `<div><div class="k">Rationale</div><div class="v">${esc(d.rationale || p.error || '—')}</div></div>` +
    `<div><div class="k">Risk</div><div class="v">${esc(d.risk_assessment || '—')}</div></div>` +
    `<div><div class="k">Plan</div><div class="v">${esc(d.entry ? `entry ${d.entry} · stop ${d.stop} · target ${d.target} · size ${d.position_size_pct}%` : 'no new position')}</div></div>` +
    `<div><div class="k">Spend</div><div class="v">${esc(u.llm_calls ?? p.estimate?.estimated_llm_calls ?? '—')} calls · ` +
    `${esc((u.prompt_tokens||0) + (u.completion_tokens||0))} tokens</div></div>` +
    `</div>${reports}</div>`;
}

refresh();
setInterval(refresh, 20000);
$('ticker').addEventListener('keydown', e => { if (e.key === 'Enter') runDesk('desk'); });
$('symbols').addEventListener('keydown', e => { if (e.key === 'Enter') runScan(); });
</script>
</body>
</html>
"""


def main() -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Flip desk dashboard → http://{HOST}:{PORT}", flush=True)
    if HOST != "127.0.0.1":
        print("WARNING: bound beyond localhost with no auth — trusted networks only.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
