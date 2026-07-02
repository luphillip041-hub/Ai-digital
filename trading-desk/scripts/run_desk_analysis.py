#!/usr/bin/env python3
"""Low-burn TradingAgents desk runner.

This wraps TauricResearch/TradingAgents with safer defaults for Discord-driven
paper analysis: fewer analysts, capped news, one debate/risk round, checkpoint
resume, project-local cache/results/memory paths, a local run ledger, and a
monthly LLM-call budget guard before expensive agent runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional during static checks
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
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
        "description": "cheap quick model plus stronger final synthesis",
    },
    "local": {
        "provider": "openai_compatible",
        "quick_model": "local-model",
        "deep_model": "local-model",
        "description": "local OpenAI-compatible endpoint; requires --backend-url or env",
    },
}


@dataclass(frozen=True)
class RunEstimate:
    analyst_count: int
    estimated_llm_calls: int
    estimated_tool_rounds: int
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


def _month_key(ts: datetime | None = None) -> str:
    ts = ts or datetime.now(UTC)
    return ts.strftime("%Y-%m")


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
    conn.commit()
    return conn


def monthly_used(conn: sqlite3.Connection, month: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(estimated_llm_calls), 0) FROM runs WHERE month = ? AND status != 'blocked'",
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
) -> None:
    conn.execute(
        """
        INSERT INTO runs (
            created_at, month, ticker, trade_date, analysts, provider, quick_model,
            deep_model, profile, estimated_llm_calls, estimated_tool_rounds, status,
            json_out, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    conn.commit()


def estimate_run(analysts: tuple[str, ...], debate_rounds: int, risk_rounds: int) -> RunEstimate:
    """Conservative call estimate; blocks expensive surprises before they happen."""
    analyst_count = len(analysts)
    # Each analyst usually needs one or more LLM turns plus tool-node loops. Keep
    # estimate conservative rather than exact, because actual tool loops vary.
    analyst_calls = analyst_count * 2
    debate_calls = max(0, debate_rounds) * 2 + 1  # bull/bear + research manager
    trader_calls = 1
    risk_calls = max(0, risk_rounds) * 3 + 1  # aggressive/conservative/neutral + PM
    estimated_llm_calls = analyst_calls + debate_calls + trader_calls + risk_calls
    estimated_tool_rounds = analyst_count * 2

    notes: list[str] = []
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
        estimated_llm_calls=estimated_llm_calls,
        estimated_tool_rounds=estimated_tool_rounds,
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


def decision_to_jsonable(decision):
    if isinstance(decision, (dict, list, str, int, float, bool)) or decision is None:
        return decision
    if hasattr(decision, "model_dump"):
        return decision.model_dump()
    if hasattr(decision, "dict"):
        return decision.dict()
    return str(decision)


def _apply_model_profile(args: argparse.Namespace) -> tuple[str, str | None, str | None, str | None]:
    """Return provider/quick/deep defaults from a named profile, then CLI overrides."""
    profile = args.model_profile
    profile_defaults = MODEL_PROFILES.get(profile, MODEL_PROFILES["cheap"])
    provider = args.provider or os.getenv("TRADINGAGENTS_LLM_PROVIDER") or profile_defaults["provider"]
    quick = args.quick_model or os.getenv("TRADINGAGENTS_QUICK_THINK_LLM") or profile_defaults["quick_model"]
    deep = args.deep_model or os.getenv("TRADINGAGENTS_DEEP_THINK_LLM") or profile_defaults["deep_model"]
    backend = args.backend_url or os.getenv("TRADINGAGENTS_LLM_BACKEND_URL")
    return provider, quick, deep, backend


def build_config(args: argparse.Namespace) -> dict:
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = DEFAULT_CONFIG.copy()

    # Project-local state: nothing leaks into Slam/Taylor/global projects.
    cfg["data_cache_dir"] = str((ROOT / ".cache").resolve())
    cfg["results_dir"] = str((ROOT / "runs").resolve())
    cfg["memory_log_path"] = str((ROOT / "memory" / "trading_memory.md").resolve())

    # Cost controls. Override by CLI only when explicitly requested.
    cfg["checkpoint_enabled"] = True
    cfg["max_debate_rounds"] = args.debate_rounds
    cfg["max_risk_discuss_rounds"] = args.risk_rounds
    cfg["max_recur_limit"] = args.max_recur
    cfg["news_article_limit"] = args.news_limit
    cfg["global_news_article_limit"] = args.global_news_limit
    cfg["global_news_lookback_days"] = args.global_news_lookback
    cfg["temperature"] = args.temperature

    provider, quick, deep, backend = _apply_model_profile(args)
    cfg["llm_provider"] = provider
    cfg["quick_think_llm"] = quick
    cfg["deep_think_llm"] = deep
    if backend:
        cfg["backend_url"] = backend

    return cfg


def make_payload(
    *,
    args: argparse.Namespace,
    analysts: tuple[str, ...],
    cfg: dict[str, Any],
    estimate: RunEstimate,
    budget: BudgetStatus,
    decision: Any = None,
    status: str = "preflight",
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "ticker": args.ticker.upper(),
        "date": args.date,
        "status": status,
        "analysts": analysts,
        "model_profile": args.model_profile,
        "config": {
            "llm_provider": cfg.get("llm_provider"),
            "quick_think_llm": cfg.get("quick_think_llm"),
            "deep_think_llm": cfg.get("deep_think_llm"),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "news_article_limit": cfg.get("news_article_limit"),
            "global_news_article_limit": cfg.get("global_news_article_limit"),
            "global_news_lookback_days": cfg.get("global_news_lookback_days"),
            "cache_dir": cfg.get("data_cache_dir"),
            "results_dir": cfg.get("results_dir"),
        },
        "estimate": asdict(estimate),
        "budget": asdict(budget),
        "decision": decision_to_jsonable(decision),
        "error": error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run low-burn TradingAgents analysis")
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
    parser.add_argument("--provider", help="Override TRADINGAGENTS_LLM_PROVIDER")
    parser.add_argument("--quick-model", help="Override quick model")
    parser.add_argument("--deep-model", help="Override deep model")
    parser.add_argument("--backend-url", help="OpenAI-compatible base URL")
    parser.add_argument("--debate-rounds", type=int, default=1)
    parser.add_argument("--risk-rounds", type=int, default=1)
    parser.add_argument("--news-limit", type=int, default=5)
    parser.add_argument("--global-news-limit", type=int, default=3)
    parser.add_argument("--global-news-lookback", type=int, default=3)
    parser.add_argument("--max-recur", type=int, default=45)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--monthly-llm-call-cap",
        type=int,
        default=int(os.getenv("FLIP_DESK_MONTHLY_LLM_CALL_CAP", "250")),
        help="Local ledger cap based on estimated LLM calls/month. Use --force to override.",
    )
    parser.add_argument("--force", action="store_true", help="Bypass monthly estimated-call cap")
    parser.add_argument("--preflight-only", action="store_true", help="Print config/budget estimate; no LLM calls")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--json-out", default=None, help="Optional path for final decision JSON")
    return parser.parse_args()


def main() -> None:
    _load_env()
    args = parse_args()

    analysts = VALID_ANALYSTS if args.full else _split_analysts(args.analysts)
    cfg = build_config(args)
    estimate = estimate_run(analysts, args.debate_rounds, args.risk_rounds)
    conn = connect_ledger()
    budget = budget_status(conn, args.monthly_llm_call_cap, estimate)

    for path_key in ("data_cache_dir", "results_dir"):
        Path(cfg[path_key]).mkdir(parents=True, exist_ok=True)
    Path(cfg["memory_log_path"]).parent.mkdir(parents=True, exist_ok=True)

    print("=== Flip Trading Desk Run ===")
    print(f"ticker={args.ticker} date={args.date} analysts={','.join(analysts)}")
    print(
        "profile={profile} provider={llm_provider} quick={quick_think_llm} deep={deep_think_llm}".format(
            profile=args.model_profile,
            **cfg,
        )
    )
    print(
        f"limits: debate={cfg['max_debate_rounds']} risk={cfg['max_risk_discuss_rounds']} "
        f"news={cfg['news_article_limit']} global_news={cfg['global_news_article_limit']}"
    )
    print(
        f"estimate: llm_calls={estimate.estimated_llm_calls} tool_rounds={estimate.estimated_tool_rounds} "
        f"risk={estimate.risk_level} monthly_remaining_after={budget.remaining_after}"
    )

    out = Path(args.json_out) if args.json_out else ROOT / "runs" / f"{args.ticker.upper()}_{args.date}.json"
    if args.preflight_only:
        payload = make_payload(
            args=args,
            analysts=analysts,
            cfg=cfg,
            estimate=estimate,
            budget=budget,
            status="preflight",
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str))
        print(json.dumps(payload, indent=2, default=str))
        print(f"\npreflight_saved={out}")
        return

    if not budget.allowed and not args.force:
        error = (
            f"Monthly estimated LLM-call cap would be exceeded: used={budget.used_before}, "
            f"new={budget.estimated_new}, cap={budget.monthly_cap}. Re-run with --force if intentional."
        )
        payload = make_payload(
            args=args,
            analysts=analysts,
            cfg=cfg,
            estimate=estimate,
            budget=budget,
            status="blocked",
            error=error,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str))
        record_run(
            conn,
            ticker=args.ticker,
            trade_date=args.date,
            analysts=analysts,
            cfg=cfg,
            profile=args.model_profile,
            estimate=estimate,
            status="blocked",
            json_out=str(out),
            error=error,
        )
        raise SystemExit(error)

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(selected_analysts=analysts, debug=args.debug, config=cfg)
        _, decision = graph.propagate(args.ticker.upper(), args.date)
        payload = make_payload(
            args=args,
            analysts=analysts,
            cfg=cfg,
            estimate=estimate,
            budget=budget,
            decision=decision,
            status="completed",
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str))
        record_run(
            conn,
            ticker=args.ticker,
            trade_date=args.date,
            analysts=analysts,
            cfg=cfg,
            profile=args.model_profile,
            estimate=estimate,
            status="completed",
            json_out=str(out),
        )
    except Exception as exc:
        payload = make_payload(
            args=args,
            analysts=analysts,
            cfg=cfg,
            estimate=estimate,
            budget=budget,
            status="error",
            error=repr(exc),
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str))
        record_run(
            conn,
            ticker=args.ticker,
            trade_date=args.date,
            analysts=analysts,
            cfg=cfg,
            profile=args.model_profile,
            estimate=estimate,
            status="error",
            json_out=str(out),
            error=repr(exc),
        )
        raise

    print("\n=== Decision ===")
    print(json.dumps(payload["decision"], indent=2, default=str))
    print(f"\nsaved={out}")


if __name__ == "__main__":
    main()
