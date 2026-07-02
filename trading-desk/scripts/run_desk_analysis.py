#!/usr/bin/env python3
"""Low-burn TradingAgents desk runner.

This wraps TauricResearch/TradingAgents with safer defaults for Discord-driven
paper analysis: fewer analysts, capped news, one debate/risk round, checkpoint
resume, and project-local cache/results/memory paths.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Iterable

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional during static checks
    load_dotenv = None

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

ROOT = Path(__file__).resolve().parents[1]
VALID_ANALYSTS = ("market", "news", "fundamentals", "social")


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


def build_config(args: argparse.Namespace) -> dict:
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

    # Let .env decide provider/model, but allow CLI override for testing.
    if args.provider:
        cfg["llm_provider"] = args.provider
    if args.quick_model:
        cfg["quick_think_llm"] = args.quick_model
    if args.deep_model:
        cfg["deep_think_llm"] = args.deep_model
    if args.backend_url:
        cfg["backend_url"] = args.backend_url

    return cfg


def decision_to_jsonable(decision):
    if isinstance(decision, (dict, list, str, int, float, bool)) or decision is None:
        return decision
    if hasattr(decision, "model_dump"):
        return decision.model_dump()
    if hasattr(decision, "dict"):
        return decision.dict()
    return str(decision)


def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser(description="Run low-burn TradingAgents analysis")
    parser.add_argument("ticker", help="Ticker symbol, e.g. AAPL, SPY, BTC-USD")
    parser.add_argument("--date", default=date.today().isoformat(), help="Analysis date YYYY-MM-DD")
    parser.add_argument(
        "--analysts",
        default="market,news",
        help="Comma list: market,news,fundamentals,social. Default keeps token burn low.",
    )
    parser.add_argument("--full", action="store_true", help="Use all analysts")
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
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--json-out", default=None, help="Optional path for final decision JSON")
    args = parser.parse_args()

    analysts = VALID_ANALYSTS if args.full else _split_analysts(args.analysts)
    cfg = build_config(args)

    for path_key in ("data_cache_dir", "results_dir"):
        Path(cfg[path_key]).mkdir(parents=True, exist_ok=True)
    Path(cfg["memory_log_path"]).parent.mkdir(parents=True, exist_ok=True)

    print("=== Flip Trading Desk Run ===")
    print(f"ticker={args.ticker} date={args.date} analysts={','.join(analysts)}")
    print(
        "provider={llm_provider} quick={quick_think_llm} deep={deep_think_llm}".format(**cfg)
    )
    print(
        f"limits: debate={cfg['max_debate_rounds']} risk={cfg['max_risk_discuss_rounds']} "
        f"news={cfg['news_article_limit']} global_news={cfg['global_news_article_limit']}"
    )

    graph = TradingAgentsGraph(selected_analysts=analysts, debug=args.debug, config=cfg)
    _, decision = graph.propagate(args.ticker.upper(), args.date)
    payload = {
        "ticker": args.ticker.upper(),
        "date": args.date,
        "analysts": analysts,
        "config": {
            "llm_provider": cfg.get("llm_provider"),
            "quick_think_llm": cfg.get("quick_think_llm"),
            "deep_think_llm": cfg.get("deep_think_llm"),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "news_article_limit": cfg.get("news_article_limit"),
            "global_news_article_limit": cfg.get("global_news_article_limit"),
        },
        "decision": decision_to_jsonable(decision),
    }

    print("\n=== Decision ===")
    print(json.dumps(payload["decision"], indent=2, default=str))

    out = Path(args.json_out) if args.json_out else ROOT / "runs" / f"{args.ticker.upper()}_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nsaved={out}")


if __name__ == "__main__":
    main()
