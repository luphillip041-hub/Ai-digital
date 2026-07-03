#!/usr/bin/env python3
"""Discord interface for Flip's low-burn trading desk.

Commands are intentionally thin wrappers around the audited desk scripts:
- scan_watchlist.py: zero LLM calls
- run_desk_analysis.py --preflight-only: budget estimate, zero LLM calls
- run_desk_analysis.py: full low-burn TradingAgents analysis on one ticker

The bot never stages or executes broker orders. It only returns research JSON
summaries and paths to generated run artifacts.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import discord
from dotenv import load_dotenv

DESK_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = DESK_ROOT / "runs"
PYTHON = os.getenv("FLIP_DESK_PYTHON", "python")
PREFIX = os.getenv("FLIP_DESK_DISCORD_PREFIX", "!")
MAX_DISCORD_CHARS = 1850
ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("FLIP_DESK_ANALYSIS_TIMEOUT_SECONDS", "1800"))
SCAN_TIMEOUT_SECONDS = int(os.getenv("FLIP_DESK_SCAN_TIMEOUT_SECONDS", "180"))
DEFAULT_SYMBOLS = os.getenv(
    "FLIP_DESK_DEFAULT_SYMBOLS",
    "SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META",
)

load_dotenv(DESK_ROOT / ".env")
load_dotenv(DESK_ROOT / ".env.local")


def _parse_id_set(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


ALLOWED_CHANNEL_IDS = _parse_id_set(os.getenv("FLIP_DESK_ALLOWED_CHANNEL_IDS"))
ALLOWED_GUILD_IDS = _parse_id_set(os.getenv("FLIP_DESK_ALLOWED_GUILD_IDS"))

analysis_lock = asyncio.Lock()


@dataclass(frozen=True)
class CmdResult:
    exit_code: int
    stdout: str
    stderr: str


async def run_cmd(args: list[str], timeout: int) -> CmdResult:
    def _run() -> CmdResult:
        proc = subprocess.run(
            args,
            cwd=DESK_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return CmdResult(proc.returncode, proc.stdout, proc.stderr)

    return await asyncio.to_thread(_run)


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _safe_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not symbol or len(symbol) > 24:
        raise ValueError("bad ticker")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    if any(ch not in allowed for ch in symbol):
        raise ValueError("bad ticker")
    return symbol


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "n/a"


def _decision_text(decision: Any) -> str:
    if decision is None:
        return "No decision returned."
    if isinstance(decision, str):
        return decision.strip()[:1200]
    if isinstance(decision, dict):
        rating = decision.get("rating") or decision.get("action") or decision.get("decision")
        rationale = decision.get("rationale") or decision.get("summary") or decision.get("thesis")
        risk = decision.get("risk_assessment") or decision.get("risk")
        parts = []
        if rating:
            parts.append(f"Decision: **{rating}**")
        if rationale:
            parts.append(f"Why: {str(rationale)[:600]}")
        if risk:
            parts.append(f"Risk: {str(risk)[:400]}")
        if parts:
            return "\n".join(parts)
    return json.dumps(decision, indent=2, default=str)[:1200]


def format_scan(payload: dict[str, Any]) -> str:
    finalists = payload.get("finalists", [])
    ranked = payload.get("ranked", [])
    rows = finalists or ranked[:5]
    if not rows:
        return "📭 No scan results."
    lines = ["🔎 **Desk Scan** — zero LLM calls"]
    for item in rows[:8]:
        flags = item.get("risk_flags") or []
        why = ", ".join((item.get("why") or [])[:3]) or "no clear edge"
        flag_txt = f" | flags: {', '.join(flags[:2])}" if flags else ""
        elig = "✅" if item.get("eligible") else "⚪"
        lines.append(
            f"{elig} **{item.get('symbol')}** score `{item.get('score')}` "
            f"bias `{item.get('bias')}` close `{item.get('close')}` — {why}{flag_txt}"
        )
    lines.append(f"saved `{payload.get('output_path', 'runs/scanner_latest.json')}`")
    return "\n".join(lines)


def format_preflight(payload: dict[str, Any]) -> str:
    estimate = payload.get("estimate", {})
    budget = payload.get("budget", {})
    cfg = payload.get("config", {})
    ticker = payload.get("ticker")
    allowed = "✅ allowed" if budget.get("allowed") else "🛑 blocked"
    return (
        f"🧪 **{ticker} preflight** — {allowed}\n"
        f"Analysts: `{','.join(payload.get('analysts', []))}` | "
        f"Est calls: `{estimate.get('estimated_llm_calls')}` | "
        f"Month left after: `{budget.get('remaining_after')}`\n"
        f"Model: `{cfg.get('llm_provider')}/{cfg.get('quick_think_llm')}`"
    )


def format_decision(payload: dict[str, Any]) -> str:
    ticker = payload.get("ticker")
    status = payload.get("status")
    estimate = payload.get("estimate", {})
    budget = payload.get("budget", {})
    lines = [f"📊 **{ticker} desk result** — `{status}`"]
    lines.append(
        f"Analysts `{','.join(payload.get('analysts', []))}` | "
        f"est calls `{estimate.get('estimated_llm_calls')}` | "
        f"month left `{budget.get('remaining_after')}`"
    )
    if payload.get("error"):
        lines.append(f"Error: `{payload['error']}`")
    else:
        lines.append(_decision_text(payload.get("decision")))
    return "\n".join(lines)


def format_budget() -> str:
    db = RUNS_DIR / "desk_ledger.sqlite3"
    if not db.exists():
        return "💸 Budget ledger is empty — no runs recorded yet."
    import sqlite3

    month = datetime.now(UTC).strftime("%Y-%m")
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(estimated_llm_calls), 0), COUNT(*) FROM runs WHERE month = ? AND status != 'blocked'",
            (month,),
        ).fetchone()
        recent = conn.execute(
            "SELECT created_at, ticker, status, estimated_llm_calls FROM runs ORDER BY id DESC LIMIT 5"
        ).fetchall()
    cap = int(os.getenv("FLIP_DESK_MONTHLY_LLM_CALL_CAP", "250"))
    used = int(row[0] or 0)
    count = int(row[1] or 0)
    lines = [f"💸 **Desk budget {month}** `{used}/{cap}` est LLM calls across `{count}` runs"]
    for created_at, ticker, status, calls in recent:
        lines.append(f"`{created_at[:16]}` **{ticker}** {status} `{calls}` calls")
    return "\n".join(lines)


def format_runs() -> str:
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
    if not files:
        return "📭 No saved run JSON yet."
    lines = ["🗂️ **Recent desk JSON**"]
    for path in files:
        lines.append(f"`{path.name}`")
    return "\n".join(lines)


def chunk_message(text: str) -> list[str]:
    if len(text) <= MAX_DISCORD_CHARS:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        add = len(line) + 1
        if size + add > MAX_DISCORD_CHARS and current:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += add
    if current:
        chunks.append("\n".join(current))
    return chunks


async def reply_chunks(message: discord.Message, text: str) -> None:
    for chunk in chunk_message(text):
        await message.reply(chunk, mention_author=False)


def command_allowed(message: discord.Message) -> bool:
    if message.author.bot:
        return False
    if ALLOWED_GUILD_IDS and (message.guild is None or message.guild.id not in ALLOWED_GUILD_IDS):
        return False
    if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
        return False
    return True


HELP = f"""🤖 **Flip Desk Commands**
`{PREFIX}scan [symbols]` — zero-LLM scanner, e.g. `{PREFIX}scan SPY,QQQ,NVDA,TSLA`
`{PREFIX}preflight TICKER` — budget/model check, no LLM spend
`{PREFIX}desk TICKER` — low-burn analysis after preflight
`{PREFIX}deskfull TICKER` — expensive full analyst stack
`{PREFIX}budget` — monthly estimated LLM-call ledger
`{PREFIX}runs` — recent saved JSON files

Paper/research only. No broker order staging or execution.
"""


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"Flip desk bot logged in as {client.user} prefix={PREFIX}", flush=True)


@client.event
async def on_message(message: discord.Message) -> None:
    if not command_allowed(message):
        return
    content = (message.content or "").strip()
    if not content.startswith(PREFIX):
        return

    parts = content[len(PREFIX) :].strip().split()
    if not parts:
        return
    cmd = parts[0].lower()
    args = parts[1:]

    try:
        if cmd in {"deskhelp", "help"}:
            await reply_chunks(message, HELP)
            return

        if cmd == "budget":
            await reply_chunks(message, format_budget())
            return

        if cmd == "runs":
            await reply_chunks(message, format_runs())
            return

        if cmd == "scan":
            symbols = args[0] if args else DEFAULT_SYMBOLS
            out = RUNS_DIR / f"discord_scan_{_now_stamp()}.json"
            thinking = await message.reply("🔎 scanning watchlist — zero LLM calls…", mention_author=False)
            result = await run_cmd(
                [
                    PYTHON,
                    "scripts/scan_watchlist.py",
                    "--symbols",
                    symbols,
                    "--max-finalists",
                    os.getenv("FLIP_DESK_MAX_FINALISTS", "5"),
                    "--out",
                    str(out),
                ],
                timeout=SCAN_TIMEOUT_SECONDS,
            )
            if result.exit_code != 0:
                await thinking.edit(content=f"❌ scan failed\n```{(result.stderr or result.stdout)[-1500:]}```")
                return
            payload = _read_json(out)
            payload["output_path"] = str(out.relative_to(DESK_ROOT))
            await thinking.edit(content=format_scan(payload)[:MAX_DISCORD_CHARS])
            return

        if cmd in {"preflight", "desk", "deskfull"}:
            if not args:
                await reply_chunks(message, f"Usage: `{PREFIX}{cmd} AAPL`")
                return
            ticker = _safe_symbol(args[0])
            full = cmd == "deskfull"
            preflight_only = cmd == "preflight"
            out = RUNS_DIR / f"discord_{ticker}_{date.today().isoformat()}_{_now_stamp()}.json"
            base_cmd = [PYTHON, "scripts/run_desk_analysis.py", ticker, "--json-out", str(out)]
            if full:
                base_cmd.append("--full")
            if preflight_only:
                base_cmd.append("--preflight-only")

            if preflight_only:
                thinking = await message.reply(f"🧪 preflighting **{ticker}** — no LLM spend…", mention_author=False)
                result = await run_cmd(base_cmd, timeout=SCAN_TIMEOUT_SECONDS)
                if result.exit_code != 0:
                    await thinking.edit(content=f"❌ preflight failed\n```{(result.stderr or result.stdout)[-1500:]}```")
                    return
                await thinking.edit(content=format_preflight(_read_json(out))[:MAX_DISCORD_CHARS])
                return

            async with analysis_lock:
                thinking = await message.reply(
                    f"📊 running {'FULL ' if full else ''}desk on **{ticker}**… queued one at a time to avoid token spam.",
                    mention_author=False,
                )
                result = await run_cmd(base_cmd, timeout=ANALYSIS_TIMEOUT_SECONDS)
                if result.exit_code != 0 and not out.exists():
                    await thinking.edit(content=f"❌ desk run failed\n```{(result.stderr or result.stdout)[-1500:]}```")
                    return
                payload = _read_json(out) if out.exists() else {"ticker": ticker, "status": "error", "error": result.stderr}
                await thinking.edit(content=format_decision(payload)[:MAX_DISCORD_CHARS])
                return

    except subprocess.TimeoutExpired:
        await reply_chunks(message, "⏱️ Desk command timed out. Check server logs before retrying.")
    except Exception as exc:
        await reply_chunks(message, f"❌ Desk bot error: `{exc!r}`")


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("FLIP_DESK_DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_BOT_TOKEN or FLIP_DESK_DISCORD_TOKEN in trading-desk/.env")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    client.run(token)


if __name__ == "__main__":
    main()
