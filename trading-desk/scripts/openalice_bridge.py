#!/usr/bin/env python3
"""Bridge Flip's low-burn desk into an OpenAlice workspace.

This does not vendor or modify OpenAlice. It produces a workspace prompt that
keeps OpenAlice as the cockpit/orchestrator while Flip's trading-desk remains
the deterministic scanner, budget ledger, and TradingAgents wrapper.

Optional: if an OpenAlice workspace id is provided, POST the prompt to
OpenAlice's headless workspace endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def build_prompt(args: argparse.Namespace) -> str:
    symbols = ",".join([s.strip().upper() for s in args.symbols.split(",") if s.strip()])
    finalists = max(1, args.max_finalists)
    return f"""You are running inside OpenAlice, but Flip's trading desk is the source of truth for scanner, budget, and risk discipline.

Desk root:
{ROOT}

Hard rules:
- Research/paper mode only. Do not place, stage, commit, push, or execute broker orders.
- Do not bypass Flip desk budget controls.
- First run the zero-LLM scanner; only analyze scanner finalists.
- Use concise outputs for Discord: ACTION/WATCH/REJECT, score, risk, entry/stop/target if present, and 3 bullets max.
- Treat OpenAlice as cockpit/workspace/UI/inbox; treat Flip trading-desk as the risk and decision engine.

Step 1 — zero-token scan:
```bash
cd {ROOT}
python scripts/scan_watchlist.py --symbols {symbols} --max-finalists {finalists} --out runs/openalice_scanner_latest.json
```

Step 2 — preflight each finalist before spending model calls:
```bash
python scripts/run_desk_analysis.py SYMBOL --date {args.trade_date} --preflight-only --json-out runs/SYMBOL_{args.trade_date}_preflight.json
```

Step 3 — only if preflight budget is allowed, run the low-burn analysis:
```bash
python scripts/run_desk_analysis.py SYMBOL --date {args.trade_date} --json-out runs/SYMBOL_{args.trade_date}_decision.json
```

Step 4 — summarize:
- Read `runs/openalice_scanner_latest.json`.
- Read any `runs/*_decision.json` produced.
- Send the user a compact final summary.
- If OpenAlice inbox tools are available, use `inbox_push` with the summary and generated JSON paths.

Default watchlist: {symbols}
Analysis date: {args.trade_date}
Max finalists: {finalists}
"""


def post_headless(base_url: str, workspace_id: str, prompt: str, agent: str, token: str | None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/workspaces/{workspace_id}/headless"
    payload = json.dumps({"prompt": prompt, "agent": agent}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
            return {"status": resp.status, "url": url, "body": json.loads(body) if body else None}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed: Any = json.loads(body)
        except Exception:
            parsed = body
        return {"status": exc.code, "url": url, "body": parsed}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or dispatch an OpenAlice run for Flip's desk")
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")
    parser.add_argument("--trade-date", default=date.today().isoformat())
    parser.add_argument("--max-finalists", type=int, default=3)
    parser.add_argument("--prompt-out", default=str(ROOT / "runs" / "openalice_prompt.md"))
    parser.add_argument("--openalice-url", default=os.getenv("OPENALICE_BASE_URL", "http://127.0.0.1:47331"))
    parser.add_argument("--workspace-id", default=os.getenv("OPENALICE_WORKSPACE_ID"), help="If set, dispatch headless run")
    parser.add_argument("--agent", default=os.getenv("OPENALICE_AGENT", "shell"))
    parser.add_argument("--admin-token", default=os.getenv("OPENALICE_ADMIN_TOKEN"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompt = build_prompt(args)
    out = Path(args.prompt_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    result: dict[str, Any] = {"prompt_path": str(out), "dispatched": False}
    if args.workspace_id:
        result["dispatch"] = post_headless(
            args.openalice_url,
            args.workspace_id,
            prompt,
            args.agent,
            args.admin_token,
        )
        result["dispatched"] = True
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
