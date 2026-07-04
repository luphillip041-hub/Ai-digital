"""Discord webhook notifications — fire-and-forget, never breaks a pass.

Set FLIP_DESK_DISCORD_WEBHOOK_URL in .env (Discord: channel settings →
Integrations → Webhooks → New Webhook → Copy URL). No bot token needed;
a webhook can only post to its one channel.
"""

from __future__ import annotations

import json
import os
import urllib.request

WEBHOOK_ENV = "FLIP_DESK_DISCORD_WEBHOOK_URL"
MAX_LEN = 1900


def webhook_configured() -> bool:
    return bool(os.getenv(WEBHOOK_ENV, "").startswith("https://"))


def post_discord(message: str, *, username: str = "Flip Desk") -> bool:
    """Post to the configured webhook. Returns False (never raises) on failure."""
    url = os.getenv(WEBHOOK_ENV, "")
    if not url.startswith("https://"):
        return False
    body = json.dumps({"content": message[:MAX_LEN], "username": username}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except Exception:
        return False


def autopilot_summary(report: dict) -> str:
    """Render an autopilot pass report as a Discord message."""
    mode = "🚀 EXECUTED" if report.get("mode") == "execute" else "📝 dry-run"
    lines = [f"**Autopilot pass** — {mode}"]

    scan_step = next((s for s in report.get("steps", []) if s.get("step") == "scan"), {})
    finalists = scan_step.get("finalists") or []
    lines.append(f"scan finalists: `{', '.join(finalists) if finalists else 'none'}`")

    for step in report.get("steps", []):
        if step.get("step") == "research":
            action = step.get("action") or step.get("status")
            lines.append(f"🧠 **{step.get('symbol')}** → `{action}`")

    for trade in report.get("trades", []):
        plan = trade.get("plan") or {}
        if plan.get("action") == "buy":
            verb = "✅ placed" if trade.get("executed") else "📝 would place"
            lines.append(
                f"{verb}: buy `{plan.get('qty')}` **{trade.get('symbol')}** ~`${plan.get('entry_ref')}` "
                f"stop `{plan.get('stop_price')}` target `{plan.get('target_price')}` "
                f"risk `${plan.get('risk_dollars')}`"
            )
        elif plan.get("action") == "close":
            verb = "✅ closed" if trade.get("executed") else "📝 would close"
            lines.append(f"{verb} position: **{trade.get('symbol')}**")
        else:
            lines.append(f"⚪ {trade.get('symbol')}: {plan.get('reason', 'no trade')}")

    account = report.get("account") or {}
    if account:
        lines.append(f"💼 paper account: `${account.get('equity')}` equity · `${account.get('cash')}` cash")
    positions = report.get("positions") or []
    if positions:
        for pos in positions[:6]:
            lines.append(
                f"   {pos['symbol']} ×{pos['qty']} → `${pos['market_value']}` "
                f"(P&L `{pos['unrealized_pl']}`)"
            )
    return "\n".join(lines)
