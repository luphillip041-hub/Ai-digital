#!/usr/bin/env python3
"""Streamlit UI for Flip's low-burn trading desk.

The UI stays intentionally thin: it reads/writes the same JSON artifacts used by
Discord/OpenAlice and calls the audited scanner/preflight scripts on demand.
No broker execution lives here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
SCRIPTS = ROOT / "scripts"
PYTHON = os.getenv("FLIP_DESK_PYTHON", sys.executable)
ET = ZoneInfo("America/New_York")
DEFAULT_SYMBOLS = os.getenv(
    "FLIP_DESK_DEFAULT_SYMBOLS",
    "SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META",
)

st.set_page_config(
    page_title="Flip Trading Desk",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
:root { --bg:#0e1117; --panel:rgba(17,24,39,.74); --panel2:rgba(15,23,42,.92); --line:rgba(148,163,184,.18); --text:#e5e7eb; --muted:#94a3b8; --green:#22c55e; --red:#ef4444; --cyan:#38bdf8; --amber:#f59e0b; --violet:#a78bfa; }
.stApp { background: radial-gradient(circle at 14% -10%, rgba(56,189,248,.18), transparent 30%), radial-gradient(circle at 85% 0%, rgba(167,139,250,.16), transparent 26%), #0e1117; color: var(--text); }
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1500px; }
[data-testid="stSidebar"] { background: rgba(2,6,23,.72); border-right:1px solid rgba(148,163,184,.14); }
.hero { border:1px solid var(--line); background:linear-gradient(135deg, rgba(15,23,42,.92), rgba(2,6,23,.65)); border-radius:24px; padding:24px; box-shadow:0 20px 80px rgba(0,0,0,.35); }
.hero h1 { margin:0; font-size:2.4rem; letter-spacing:-.05em; }
.subtle { color:var(--muted); font-size:.94rem; }
.pill { display:inline-flex; gap:6px; align-items:center; border:1px solid rgba(148,163,184,.25); background:rgba(15,23,42,.8); border-radius:999px; padding:6px 10px; color:#cbd5e1; font-size:.82rem; margin:3px 4px 3px 0; }
.card { border:1px solid var(--line); background:var(--panel); border-radius:20px; padding:18px; min-height:120px; box-shadow:0 10px 35px rgba(0,0,0,.22); }
.signal-card { border:1px solid rgba(56,189,248,.25); background:linear-gradient(180deg, rgba(14,165,233,.12), rgba(15,23,42,.76)); border-radius:22px; padding:20px; }
.badge-green { color:#86efac; }
.badge-red { color:#fca5a5; }
.metric-label { color:var(--muted); font-size:.8rem; text-transform:uppercase; letter-spacing:.08em; }
.metric-value { font-size:1.4rem; font-weight:750; margin-top:2px; }
.stButton>button { border-radius:12px; border:1px solid rgba(56,189,248,.32); background:rgba(14,165,233,.12); color:#e0f2fe; font-weight:650; }
.stButton>button:hover { border-color:#38bdf8; background:rgba(14,165,233,.2); }
[data-testid="stMetricValue"] { color:#e5e7eb; }
hr { border-color:rgba(148,163,184,.18); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def et_now() -> str:
    return datetime.now(ET).strftime("%a %b %-d, %Y · %-I:%M:%S %p ET")


def parse_iso(value: str | None) -> str:
    if not value:
        return "n/a"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ET).strftime("%b %-d · %-I:%M %p ET")
    except Exception:
        return value


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def run_script(args: list[str], timeout: int = 240) -> tuple[bool, str]:
    RUNS.mkdir(exist_ok=True)
    try:
        proc = subprocess.run(
            [PYTHON, *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, output[-4000:]


def dataframe_from(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.json_normalize(rows, sep="_")


def short_list(items: list[Any], limit: int = 4) -> str:
    return ", ".join(str(x) for x in (items or [])[:limit]) or "—"


def latest_runs(limit: int = 14) -> list[Path]:
    if not RUNS.exists():
        return []
    return sorted(RUNS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def ledger_stats() -> dict[str, Any]:
    db = RUNS / "desk_ledger.sqlite3"
    if not db.exists():
        return {"runs": 0, "llm_calls": 0, "db": str(db)}
    try:
        with sqlite3.connect(db) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = {r[0] for r in tables}
            out: dict[str, Any] = {"db": str(db), "tables": sorted(table_names)}
            for table in table_names:
                try:
                    out[f"{table}_rows"] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except Exception:
                    pass
            return out
    except Exception as exc:
        return {"error": str(exc), "db": str(db)}


def signal_key(sig: dict[str, Any]) -> str:
    c = sig.get("contract") or {}
    return f"{sig.get('symbol')}:{c.get('type')}:{c.get('expiration')}:{c.get('strike')}"


def render_top_metrics(stock_payload: dict[str, Any], options_payload: dict[str, Any]) -> None:
    finalists = stock_payload.get("finalists") or []
    signals = options_payload.get("signals") or []
    stats = ledger_stats()
    cols = st.columns(4)
    cols[0].metric("Stock finalists", len(finalists), help="Zero-LLM watchlist scanner finalists")
    cols[1].metric("Option signals", len(signals), help="Options signal scanner candidates")
    top = signals[0]["symbol"] if signals else (finalists[0]["symbol"] if finalists else "—")
    cols[2].metric("Top ticker", top)
    ledger_rows = sum(v for k, v in stats.items() if k.endswith("_rows") and isinstance(v, int))
    cols[3].metric("Ledger rows", ledger_rows)


def render_signal_card(sig: dict[str, Any], active: bool = False) -> None:
    setup = sig.get("setup") or {}
    contract = sig.get("contract") or {}
    mgmt = sig.get("management") or {}
    direction = setup.get("direction", "neutral")
    icon = "🟢" if direction == "long" else "🔴" if direction == "short" else "⚪"
    active_badge = " · ACTIVE" if active else ""
    st.markdown(
        f"""
<div class="signal-card">
  <div class="subtle">#{sig.get('rank', '—')} · Score {sig.get('total_score', '—')}{active_badge}</div>
  <h3>{icon} {setup.get('setup', 'Signal')} — {sig.get('symbol', '—')}</h3>
  <div class="pill">Entry ${setup.get('entry', 0):,.2f}</div>
  <div class="pill">Target ${setup.get('target', 0):,.2f}</div>
  <div class="pill">Stop ${setup.get('stop', 0):,.2f}</div>
  <div class="pill">R/R {setup.get('reward_risk', '—')}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contract", f"{contract.get('type', '—')} {contract.get('strike', '—')}")
    c2.metric("Expiry / DTE", f"{contract.get('expiration', '—')} / {contract.get('dte', '—')}")
    c3.metric("Bid / Ask", f"${contract.get('bid', 0):.2f} / ${contract.get('ask', 0):.2f}" if contract else "—")
    c4.metric("Vol / OI", f"{contract.get('volume', 0):,} / {contract.get('open_interest', 0):,}" if contract else "—")
    c5, c6, c7, c8 = st.columns(4)
    iv = contract.get("implied_volatility")
    c5.metric("IV", f"{iv * 100:.1f}%" if isinstance(iv, (int, float)) else "—")
    c6.metric("Delta", f"{contract.get('approx_delta', 0):+.2f}" if contract.get("approx_delta") is not None else "—")
    c7.metric("Breakeven", f"${contract.get('breakeven', 0):,.2f}" if contract else "—")
    c8.metric("Est. cost", f"${mgmt.get('estimated_contract_cost', 0):,.0f}" if mgmt else "—")
    st.caption("Why: " + short_list(setup.get("why") or [], 8))
    flags = (setup.get("risk_flags") or []) + (contract.get("risk_flags") or [])
    if flags:
        st.warning("Flags: " + short_list(flags, 8))


def payoff_dataframe(sig: dict[str, Any], shock: float = 0.0) -> pd.DataFrame:
    setup = sig.get("setup") or {}
    c = sig.get("contract") or {}
    spot = float(setup.get("entry") or setup.get("close") or 0)
    strike = float(c.get("strike") or spot or 1)
    premium = float(c.get("mid") or c.get("ask") or 0) + shock
    kind = c.get("type", "CALL")
    if spot <= 0:
        return pd.DataFrame()
    lo = max(0.01, spot * 0.82)
    hi = spot * 1.18
    xs = [lo + (hi - lo) * i / 80 for i in range(81)]
    ys = []
    for x in xs:
        intrinsic = max(x - strike, 0) if kind == "CALL" else max(strike - x, 0)
        ys.append(round((intrinsic - premium) * 100, 2))
    return pd.DataFrame({"underlying_price": xs, "expiry_pnl_per_contract": ys}).set_index("underlying_price")


@st.cache_data(ttl=60, show_spinner=False)
def history(symbol: str) -> pd.DataFrame:
    try:
        import yfinance as yf  # type: ignore

        data = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=True)
        if data is None or data.empty:
            return pd.DataFrame()
        return data[["Close"]].rename(columns={"Close": symbol})
    except Exception:
        return pd.DataFrame()


def render_launchpad(stock_payload: dict[str, Any], options_payload: dict[str, Any]) -> None:
    st.markdown(
        f"""
<div class="hero">
  <div class="subtle">{et_now()} · research/paper desk · no live execution</div>
  <h1>Flip Trading Desk</h1>
  <p class="subtle">Command center for scanners, options signals, Vibe-style research, budget guardrails, OpenAlice bridge, and Discord run artifacts.</p>
  <span class="pill">Zero-LLM scanner first</span>
  <span class="pill">Options signals</span>
  <span class="pill">Budget guard</span>
  <span class="pill">Vibe research bridge</span>
  <span class="pill">OpenAlice cockpit-ready</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")
    render_top_metrics(stock_payload, options_payload)
    st.write("")
    cards = st.columns(5)
    copy = [
        ("📡 Live Scanner", "Run broad symbol triage before spending model calls."),
        ("🎯 Options Signals", "Contract-quality cards with target/stop/management."),
        ("🧬 Research Lab", "Vibe-Trading style analyst packets without replacing desk rules."),
        ("🧠 Strategy Workspace", "Inspect active signal, payoff curve, levels, and risk."),
        ("🛠 Diagnostics", "Artifacts, ledgers, environment status, and docs."),
    ]
    for col, (title, body) in zip(cards, copy, strict=False):
        col.markdown(f"<div class='card'><h3>{title}</h3><p class='subtle'>{body}</p></div>", unsafe_allow_html=True)


def render_scanner(symbols: str) -> None:
    st.subheader("📡 Zero-LLM Watchlist Scanner")
    st.caption("Fast deterministic triage. Use this before any model-heavy desk run.")
    c1, c2, c3 = st.columns([2, 1, 1])
    min_score = c2.slider("Min score", 0, 100, 60, 5)
    max_finalists = c3.slider("Finalists", 1, 10, 5)
    out = RUNS / "ui_watchlist_scan.json"
    if c1.button("Run stock scanner", use_container_width=True):
        ok, output = run_script(
            [
                str(SCRIPTS / "scan_watchlist.py"),
                "--symbols",
                symbols,
                "--min-score",
                str(min_score),
                "--max-finalists",
                str(max_finalists),
                "--out",
                str(out),
            ]
        )
        if ok:
            st.success("Scanner complete")
        else:
            st.error(output)
    payload = read_json(out) or read_json(RUNS / "latest_watchlist_scan.json")
    rows = payload.get("ranked") or payload.get("finalists") or []
    st.caption(f"Generated: {parse_iso(payload.get('generated_at'))}")
    df = dataframe_from(rows)
    if not df.empty:
        cols = [c for c in ["symbol", "score", "bias", "eligible", "close", "rsi14", "volume_ratio", "atr_pct", "five_day_return_pct", "twenty_day_return_pct"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.info("Run the scanner to populate candidates.")


def render_options(symbols: str) -> dict[str, Any]:
    st.subheader("🎯 Options Signal Scanner")
    st.caption("Screenshot-style options cards backed by chart setup + chain/liquidity/risk filters.")
    c1, c2, c3 = st.columns([2, 1, 1])
    max_signals = c2.slider("Signals", 1, 8, int(os.getenv("FLIP_DESK_MAX_OPTION_SIGNALS", "3")))
    max_exp = c3.slider("Expiries checked", 1, 6, 4)
    out = RUNS / "ui_options_signals.json"
    md = RUNS / "ui_options_signal.md"
    if c1.button("Run options scanner", use_container_width=True):
        ok, output = run_script(
            [
                str(SCRIPTS / "options_signal_scanner.py"),
                "--symbols",
                symbols,
                "--max-signals",
                str(max_signals),
                "--max-expirations",
                str(max_exp),
                "--out",
                str(out),
                "--markdown-out",
                str(md),
            ],
            timeout=420,
        )
        if ok:
            st.success("Options scan complete")
        else:
            st.error(output)
    payload = read_json(out) or read_json(RUNS / "options_signals_latest.json")
    signals = payload.get("signals") or []
    st.caption(f"Generated: {parse_iso(payload.get('generated_at'))} · {payload.get('data_source', 'data source n/a')}")
    if not signals:
        st.info("Run the options scanner to populate signal cards.")
        return payload
    options = {f"#{s.get('rank')} {s.get('symbol')} · {(s.get('setup') or {}).get('setup')}": i for i, s in enumerate(signals)}
    selected_label = st.selectbox("Active signal", list(options.keys()), key="active_signal_label")
    idx = options[selected_label]
    st.session_state.active_signal = signals[idx]
    for s in signals:
        with st.container():
            active = signal_key(s) == signal_key(st.session_state.active_signal)
            render_signal_card(s, active=active)
            if st.button(f"Load {s.get('symbol')} into workspace", key=f"load_{signal_key(s)}"):
                st.session_state.active_signal = s
                st.session_state.active_ticker = s.get("symbol")
                st.rerun()
            st.divider()
    return payload



def render_research_lab(symbols: str) -> None:
    st.subheader("🧬 Research Lab — Vibe bridge")
    st.caption("Uses Vibe-Trading ideas as an analyst sidecar: scanner context + optional external vibe-trading CLI. No execution.")
    default_symbol = (st.session_state.get("active_ticker") or symbols.split(",")[0] or "SPY").strip().upper()
    c1, c2, c3 = st.columns([1.2, 1, 1])
    symbol = c1.text_input("Ticker", value=default_symbol, key="vibe_symbol").strip().upper()
    run_external = c2.toggle("Call external Vibe CLI if installed", value=False)
    refresh = c3.toggle("Refresh scanner context", value=True)
    out = RUNS / f"ui_vibe_{symbol}.json"
    md = RUNS / f"ui_vibe_{symbol}.md"
    if st.button("Build research packet", use_container_width=True):
        args = [
            str(SCRIPTS / "vibe_research_bridge.py"),
            symbol,
            "--json-out",
            str(out),
            "--markdown-out",
            str(md),
        ]
        if refresh:
            args.append("--refresh")
        if run_external:
            args.append("--run-vibe")
        ok, output = run_script(args, timeout=960 if run_external else 300)
        if ok:
            st.success("Research packet built")
        else:
            st.error(output)
    payload = read_json(out)
    if not payload:
        recent = sorted(RUNS.glob("ui_vibe_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if recent:
            payload = read_json(recent[0])
            st.caption(f"Showing latest packet: {recent[0].name}")
    if not payload:
        st.info("Build a packet to populate the research lab.")
        st.markdown("""
**Why this exists:** Vibe-Trading is best as an analyst lab, not the desk's source of truth. This bridge normalizes its ideas into our desk format so scanner/risk/run-card discipline stays intact.
""")
        return
    verdict = payload.get("verdict") or {}
    desk = payload.get("desk_context") or {}
    opt = payload.get("option_signal") or {}
    sidecar = payload.get("vibe_sidecar") or {}
    st.markdown(
        f"""
<div class="signal-card">
  <div class="subtle">{payload.get('generated_at')} · research/paper only</div>
  <h3>🧬 {payload.get('symbol')} — {verdict.get('stance', 'research packet')}</h3>
  <div class="pill">Bias {verdict.get('bias', 'n/a')}</div>
  <div class="pill">Confidence {verdict.get('confidence', 'n/a')}/10</div>
  <div class="pill">Sidecar {sidecar.get('status', 'skipped')}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write(verdict.get("summary", ""))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Desk score", desk.get("score", "—"))
    c2.metric("Close", desk.get("close", "—"))
    c3.metric("RSI14", desk.get("rsi14", "—"))
    c4.metric("ATR%", desk.get("atr_pct", "—"))
    st.caption("Scanner why: " + short_list(desk.get("why") or [], 8))
    if opt:
        st.markdown("### Matched option signal")
        st.json(opt)
    with st.expander("Full research JSON", expanded=False):
        st.json(payload)
    if md.exists():
        with st.expander("Markdown report", expanded=False):
            st.code(md.read_text(encoding="utf-8")[:6000], language="markdown")

def render_workspace(options_payload: dict[str, Any]) -> None:
    st.subheader("🧠 Strategy Workspace")
    signals = options_payload.get("signals") or []
    active = st.session_state.get("active_signal") or (signals[0] if signals else None)
    if not active:
        st.info("Run or load an options signal first.")
        return
    st.session_state.active_ticker = active.get("symbol")
    left, right = st.columns([1.15, 1])
    with left:
        render_signal_card(active, active=True)
        shock = st.slider("Premium shock for payoff model", -2.0, 2.0, 0.0, 0.05)
        payoff = payoff_dataframe(active, shock)
        if not payoff.empty:
            st.caption("Single-leg expiry payoff model. Spreads/butterflies come next.")
            st.line_chart(payoff, height=300)
    with right:
        symbol = active.get("symbol") or "SPY"
        st.markdown(f"### {symbol} price context")
        hist = history(symbol)
        if not hist.empty:
            st.line_chart(hist, height=350)
        setup = active.get("setup") or {}
        levels = pd.DataFrame(
            [
                {"level": "Entry", "price": setup.get("entry")},
                {"level": "Target", "price": setup.get("target")},
                {"level": "Stop", "price": setup.get("stop")},
                {"level": "Support", "price": setup.get("support")},
                {"level": "Resistance", "price": setup.get("resistance")},
            ]
        )
        st.dataframe(levels, use_container_width=True, hide_index=True)
    st.markdown("### Management plan")
    st.json(active.get("management") or {})


def render_runs() -> None:
    st.subheader("📁 Runs, Budget & Artifacts")
    stats = ledger_stats()
    st.json(stats)
    files = latest_runs()
    if files:
        rows = [
            {
                "file": p.name,
                "modified_et": datetime.fromtimestamp(p.stat().st_mtime, ET).strftime("%b %-d %-I:%M %p"),
                "kb": round(p.stat().st_size / 1024, 1),
            }
            for p in files
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        chosen = st.selectbox("Open artifact", [p.name for p in files])
        payload = read_json(RUNS / chosen)
        st.json(payload)
    else:
        st.info("No JSON run artifacts yet.")


def render_diagnostics(symbols: str) -> None:
    st.subheader("🛠 Diagnostics")
    env_names = [
        "DISCORD_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "TRADIER_ACCESS_TOKEN",
        "VIBE_TRADING_BIN",
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
    ]
    env_rows = [{"name": name, "present": bool(os.getenv(name))} for name in env_names]
    st.dataframe(pd.DataFrame(env_rows), hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    c1.code(f"Root: {ROOT}\nRuns: {RUNS}\nPython: {PYTHON}\nSymbols: {symbols}")
    with c2:
        st.markdown("**Safety posture**")
        st.write("✅ No broker execution in UI")
        st.write("✅ Scanner/preflight on demand")
        st.write("✅ Runtime artifacts stay in `runs/`")
        st.write("⚠️ yfinance data is delayed/proxy until Tradier is wired")
    st.markdown("### Commands")
    st.code(
        "python ui/dashboard.py  # not recommended\n"
        "streamlit run ui/dashboard.py --server.port 8512 --server.address 0.0.0.0\n"
        "docker compose up -d --build",
        language="bash",
    )


def main() -> None:
    RUNS.mkdir(exist_ok=True)
    with st.sidebar:
        st.markdown("## Flip Desk")
        st.caption("Dark command center · ET market time")
        symbols = st.text_area("Universe", value=DEFAULT_SYMBOLS, height=95)
        st.session_state.symbols = symbols
        view = st.radio(
            "View",
            ["Home", "Live Scanner", "Options Signals", "Research Lab", "Strategy Workspace", "Runs/Budget", "Diagnostics"],
            index=0,
        )
        st.divider()
        st.caption("Discord commands")
        st.code("!scan\n!optionscan\n!vibe TSLA\n!preflight AAPL\n!desk AAPL", language="text")
    stock_payload = read_json(RUNS / "ui_watchlist_scan.json")
    options_payload = read_json(RUNS / "ui_options_signals.json") or read_json(RUNS / "options_signals_latest.json")
    if view == "Home":
        render_launchpad(stock_payload, options_payload)
    elif view == "Live Scanner":
        render_scanner(symbols)
    elif view == "Options Signals":
        render_options(symbols)
    elif view == "Research Lab":
        render_research_lab(symbols)
    elif view == "Strategy Workspace":
        render_workspace(options_payload)
    elif view == "Runs/Budget":
        render_runs()
    elif view == "Diagnostics":
        render_diagnostics(symbols)


if __name__ == "__main__":
    main()
