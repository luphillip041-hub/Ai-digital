#!/usr/bin/env python3
"""Flip desk runner — native multi-agent engine, no external agent framework.

Orchestrates the desk_agents sub-agent team (analysts → bull/bear debate →
research manager → trader → risk → portfolio manager) with an exact
planned-call budget guard, a SQLite ledger of planned AND actual usage,
and JSON artifacts for the Discord bot / dashboards.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desk_agents.llm import LLMConfig  # noqa: E402
from desk_agents.orchestrator import DeskOrchestrator, planned_calls  # noqa: E402

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional during static checks
    load_dotenv = None

VALID_ANALYSTS = ("market", "news", "fundamentals", "social")
MODEL_PROFILES = {
    "cheap": {
        "provider": "deepseek",
        "quick_model": "deepseek-v4-flash",
        "deep_model": "deepseek-v4-flash",
        "description": "lowest-burn default for broad screening",
    },
    "balanced": {
        "provider": "openrouter",
        "quick_model": "deepseek/deepseek-v4-flash",
        "deep_model": "deepseek/deepseek-v4-pro",
        "description": "cheap quick model plus stronger synthesis/final call",
    },
    "local": {
        "provider": "openai_compatible",
        "quick_model": "local-model",
        "deep_model": "local-model",
        "description": "local OpenAI-compatible endpoint; requires --backend-url or env",
    },
    "offline": {
        "provider": "offline",
        "quick_model": "offline",
        "deep_model": "offline",
        "description": "deterministic canned agents; zero network, zero keys (testing/demo)",
    },
}


@dataclass(frozen=True)
class RunEstimate:
    analyst_count: int
    estimated_llm_calls: int  # exact plan, name kept for bot/ledger compatibility
    estimated_tool_rounds: int  # deterministic data fetches, not LLM tool loops
    risk_level: str
    notes: list[str]


@dataclass(frozen=True)
class BudgetStatus:
    month: str
    monthly_cap: int
    used_before: int
    estimated_new: int
    remaining_after: int
    allowed: bool


def _env(*names: str, default: str | None = None) -> str | None:
    """First set env var among aliases (new FLIP_DESK_* names win over legacy)."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _load_env() -> None:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / ".env.local")


def _split_analysts(raw: str) -> tuple[str, ...]:
    items = tuple(x.strip().lower() for x in raw.split(",") if x.strip())
    bad = [x for x in items if x not in VALID_ANALYSTS]
    if bad:
        raise SystemExit(f"Invalid analysts {bad}; valid={VALID_ANALYSTS}")
    return items or ("market", "news")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _month_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def ledger_path() -> Path:
    return ROOT / "runs" / "desk_ledger.sqlite3"


def connect_ledger() -> sqlite3.Connection:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            month TEXT NOT NULL,
            ticker TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            analysts TEXT NOT NULL,
            provider TEXT,
            quick_model TEXT,
            deep_model TEXT,
            profile TEXT,
            estimated_llm_calls INTEGER NOT NULL,
            estimated_tool_rounds INTEGER NOT NULL,
            status TEXT NOT NULL,
            json_out TEXT,
            error TEXT
        )
        """
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    for column in ("actual_llm_calls", "prompt_tokens", "completion_tokens"):
        if column not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} INTEGER")
    conn.commit()
    return conn


def monthly_used(conn: sqlite3.Connection, month: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(actual_llm_calls, estimated_llm_calls)), 0) "
        "FROM runs WHERE month = ? AND status != 'blocked'",
        (month,),
    ).fetchone()
    return int(row[0] or 0)


def record_run(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    trade_date: str,
    analysts: tuple[str, ...],
    cfg: dict[str, Any],
    profile: str,
    estimate: RunEstimate,
    status: str,
    json_out: str | None = None,
    error: str | None = None,
    usage: dict[str, Any] | None = None,
) -> None:
    usage = usage or {}
    conn.execute(
        """
        INSERT INTO runs (
            created_at, month, ticker, trade_date, analysts, provider, quick_model,
            deep_model, profile, estimated_llm_calls, estimated_tool_rounds, status,
            json_out, error, actual_llm_calls, prompt_tokens, completion_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _utc_now(),
            _month_key(),
            ticker.upper(),
            trade_date,
            ",".join(analysts),
            cfg.get("llm_provider"),
            cfg.get("quick_think_llm"),
            cfg.get("deep_think_llm"),
            profile,
            estimate.estimated_llm_calls,
            estimate.estimated_tool_rounds,
            status,
            json_out,
            error,
            usage.get("llm_calls"),
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        ),
    )
    conn.commit()


def plan_run(analysts: tuple[str, ...], debate_rounds: int, risk_rounds: int) -> RunEstimate:
    """Exact call plan — the orchestrator makes precisely this many LLM calls."""
    calls = planned_calls(analysts, debate_rounds, risk_rounds)
    data_fetches = 1 + ("news" in analysts) + ("fundamentals" in analysts)

    notes: list[str] = []
    analyst_count = len(analysts)
    if analyst_count <= 2:
        risk_level = "low"
        notes.append("reduced analyst set")
    elif analyst_count == 3:
        risk_level = "medium"
        notes.append("expanded analyst set")
    else:
        risk_level = "high"
        notes.append("full analyst stack")
    if debate_rounds > 1 or risk_rounds > 1:
        risk_level = "high"
        notes.append("multi-round debate enabled")
    return RunEstimate(
        analyst_count=analyst_count,
        estimated_llm_calls=calls,
        estimated_tool_rounds=data_fetches,
        risk_level=risk_level,
        notes=notes,
    )


def budget_status(conn: sqlite3.Connection, cap: int, estimate: RunEstimate) -> BudgetStatus:
    month = _month_key()
    used = monthly_used(conn, month)
    remaining_after = cap - used - estimate.estimated_llm_calls
    return BudgetStatus(
        month=month,
        monthly_cap=cap,
        used_before=used,
        estimated_new=estimate.estimated_llm_calls,
        remaining_after=remaining_after,
        allowed=remaining_after >= 0,
    )


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    profile_defaults = MODEL_PROFILES.get(args.model_profile, MODEL_PROFILES["cheap"])
    provider = args.provider or _env(
        "FLIP_DESK_LLM_PROVIDER", "TRADINGAGENTS_LLM_PROVIDER", default=profile_defaults["provider"]
    )
    quick = args.quick_model or _env(
        "FLIP_DESK_QUICK_MODEL", "TRADINGAGENTS_QUICK_THINK_LLM", default=profile_defaults["quick_model"]
    )
    deep = args.deep_model or _env(
        "FLIP_DESK_DEEP_MODEL", "TRADINGAGENTS_DEEP_THINK_LLM", default=profile_defaults["deep_model"]
    )
    backend = args.backend_url or _env("FLIP_DESK_LLM_BACKEND_URL", "TRADINGAGENTS_LLM_BACKEND_URL")
    if args.model_profile == "offline":
        provider = "offline"
    return {
        "llm_provider": provider,
        "quick_think_llm": quick,
        "deep_think_llm": deep,
        "backend_url": backend,
        "max_debate_rounds": args.debate_rounds,
        "max_risk_discuss_rounds": args.risk_rounds,
        "news_article_limit": args.news_limit,
        "lookback": args.lookback,
        "data_source": args.data_source,
        "temperature": args.temperature,
        "max_output_tokens": args.max_output_tokens,
        "results_dir": str((ROOT / "runs").resolve()),
    }


def make_payload(
    *,
    args: argparse.Namespace,
    analysts: tuple[str, ...],
    cfg: dict[str, Any],
    estimate: RunEstimate,
    budget: BudgetStatus,
    result: dict[str, Any] | None = None,
    status: str = "preflight",
    error: str | None = None,
) -> dict[str, Any]:
    result = result or {}
    return {
        "ticker": args.ticker.upper(),
        "date": args.date,
        "status": status,
        "engine": "desk_agents-native",
        "analysts": analysts,
        "model_profile": args.model_profile,
        "config": {
            "llm_provider": cfg.get("llm_provider"),
            "quick_think_llm": cfg.get("quick_think_llm"),
            "deep_think_llm": cfg.get("deep_think_llm"),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "news_article_limit": cfg.get("news_article_limit"),
            "lookback": cfg.get("lookback"),
            "data_source": cfg.get("data_source"),
            "max_output_tokens": cfg.get("max_output_tokens"),
            "results_dir": cfg.get("results_dir"),
        },
        "estimate": asdict(estimate),
        "budget": asdict(budget),
        "decision": result.get("decision"),
        "reports": result.get("reports"),
        "data": result.get("data"),
        "usage": result.get("usage"),
        "error": error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the native multi-agent desk analysis")
    parser.add_argument("ticker", help="Ticker symbol, e.g. AAPL, SPY, BTC-USD")
    parser.add_argument("--date", default=date.today().isoformat(), help="Analysis date YYYY-MM-DD")
    parser.add_argument(
        "--analysts",
        default="market,news",
        help="Comma list: market,news,fundamentals,social. Default keeps token burn low.",
    )
    parser.add_argument("--full", action="store_true", help="Use all analysts")
    parser.add_argument(
        "--model-profile",
        choices=sorted(MODEL_PROFILES),
        default="cheap",
        help="Model routing preset. CLI/env provider/model flags still win.",
    )
    parser.add_argument("--provider", help="Override LLM provider (deepseek/openai/openrouter/openai_compatible/offline)")
    parser.add_argument("--quick-model", help="Model for analysts, debate, trader, risk")
    parser.add_argument("--deep-model", help="Model for research manager and portfolio manager")
    parser.add_argument("--backend-url", help="OpenAI-compatible base URL")
    parser.add_argument("--debate-rounds", type=int, default=1)
    parser.add_argument("--risk-rounds", type=int, default=1)
    parser.add_argument("--news-limit", type=int, default=5)
    parser.add_argument("--lookback", default="6mo", help="Price history window for the market brief")
    parser.add_argument(
        "--data-source",
        choices=("auto", "alpaca", "yahoo"),
        default=os.getenv("FLIP_DESK_DATA_SOURCE", "auto"),
        help="Market data source. auto = Alpaca when ALPACA_API_KEY/SECRET are set, else Yahoo.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=int(os.getenv("FLIP_DESK_MAX_OUTPUT_TOKENS", "700")))
    parser.add_argument(
        "--monthly-llm-call-cap",
        type=int,
        default=int(os.getenv("FLIP_DESK_MONTHLY_LLM_CALL_CAP", "250")),
        help="Local ledger cap on LLM calls/month. Use --force to override.",
    )
    parser.add_argument("--force", action="store_true", help="Bypass monthly call cap")
    parser.add_argument("--preflight-only", action="store_true", help="Print config/budget plan; no LLM calls")
    parser.add_argument("--json-out", default=None, help="Optional path for final decision JSON")
    return parser.parse_args()


def main() -> None:
    _load_env()
    args = parse_args()

    analysts = VALID_ANALYSTS if args.full else _split_analysts(args.analysts)
    cfg = build_config(args)
    estimate = plan_run(analysts, args.debate_rounds, args.risk_rounds)
    conn = connect_ledger()
    budget = budget_status(conn, args.monthly_llm_call_cap, estimate)

    print("=== Flip Trading Desk Run (native multi-agent) ===")
    print(f"ticker={args.ticker} date={args.date} analysts={','.join(analysts)}")
    print(
        f"profile={args.model_profile} provider={cfg['llm_provider']} "
        f"quick={cfg['quick_think_llm']} deep={cfg['deep_think_llm']}"
    )
    print(
        f"limits: debate={cfg['max_debate_rounds']} risk={cfg['max_risk_discuss_rounds']} "
        f"news={cfg['news_article_limit']} max_output_tokens={cfg['max_output_tokens']}"
    )
    print(
        f"plan: llm_calls={estimate.estimated_llm_calls} data_fetches={estimate.estimated_tool_rounds} "
        f"risk={estimate.risk_level} monthly_remaining_after={budget.remaining_after}"
    )

    out = Path(args.json_out) if args.json_out else ROOT / "runs" / f"{args.ticker.upper()}_{args.date}.json"

    def save(payload: dict[str, Any]) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str))

    if args.preflight_only:
        payload = make_payload(args=args, analysts=analysts, cfg=cfg, estimate=estimate, budget=budget)
        save(payload)
        print(json.dumps(payload, indent=2, default=str))
        print(f"\npreflight_saved={out}")
        return

    if not budget.allowed and not args.force:
        error = (
            f"Monthly LLM-call cap would be exceeded: used={budget.used_before}, "
            f"planned={budget.estimated_new}, cap={budget.monthly_cap}. Re-run with --force if intentional."
        )
        save(make_payload(args=args, analysts=analysts, cfg=cfg, estimate=estimate, budget=budget,
                          status="blocked", error=error))
        record_run(conn, ticker=args.ticker, trade_date=args.date, analysts=analysts, cfg=cfg,
                   profile=args.model_profile, estimate=estimate, status="blocked",
                   json_out=str(out), error=error)
        raise SystemExit(error)

    quick_cfg = LLMConfig(
        provider=cfg["llm_provider"],
        model=cfg["quick_think_llm"],
        base_url=cfg.get("backend_url"),
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )
    deep_cfg = LLMConfig(
        provider=cfg["llm_provider"],
        model=cfg["deep_think_llm"],
        base_url=cfg.get("backend_url"),
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )

    desk = None
    try:
        desk = DeskOrchestrator(
            quick=quick_cfg,
            deep=deep_cfg,
            debate_rounds=args.debate_rounds,
            risk_rounds=args.risk_rounds,
            news_limit=args.news_limit,
            lookback=args.lookback,
            data_source=args.data_source,
        )
        result = desk.run(args.ticker, args.date, analysts)
        payload = make_payload(args=args, analysts=analysts, cfg=cfg, estimate=estimate,
                               budget=budget, result=result, status="completed")
        save(payload)
        record_run(conn, ticker=args.ticker, trade_date=args.date, analysts=analysts, cfg=cfg,
                   profile=args.model_profile, estimate=estimate, status="completed",
                   json_out=str(out), usage=result.get("usage"))
    except Exception as exc:
        # Bill the ledger for what the failed run actually spent, not the plan.
        spent = desk.meter.as_dict() if desk else {"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        save(make_payload(args=args, analysts=analysts, cfg=cfg, estimate=estimate, budget=budget,
                          status="error", error=repr(exc)))
        record_run(conn, ticker=args.ticker, trade_date=args.date, analysts=analysts, cfg=cfg,
                   profile=args.model_profile, estimate=estimate, status="error",
                   json_out=str(out), error=repr(exc), usage=spent)
        raise

    usage = payload.get("usage") or {}
    print("\n=== Decision ===")
    print(json.dumps(payload["decision"], indent=2, default=str))
    print(
        f"\nactual usage: llm_calls={usage.get('llm_calls')} "
        f"prompt_tokens={usage.get('prompt_tokens')} completion_tokens={usage.get('completion_tokens')}"
    )
    print(f"saved={out}")


if __name__ == "__main__":
    main()
