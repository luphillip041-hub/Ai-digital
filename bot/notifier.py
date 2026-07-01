"""Push notifications for trades and daily summaries.

Channels are optional and configured via .env — every one that has
credentials set receives every message:

  Discord:  DISCORD_WEBHOOK_URL
  Telegram: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  Email:    SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD + NOTIFY_EMAIL

Delivery failures are logged and swallowed — notifications must never
break the trading loop.

Test your configuration with:  python -m bot.notifier
"""

import logging
import smtplib
from email.message import EmailMessage

import requests

import config

logger = logging.getLogger(__name__)


def _money(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):,.2f}"


class Notifier:
    def __init__(self):
        self.channels = []
        if config.DISCORD_WEBHOOK_URL:
            self.channels.append(("discord", self._send_discord))
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            self.channels.append(("telegram", self._send_telegram))
        if config.SMTP_HOST and config.SMTP_USER and config.NOTIFY_EMAIL:
            self.channels.append(("email", self._send_email))
        if self.channels:
            logger.info("Notifications enabled: %s",
                        ", ".join(name for name, _ in self.channels))
        else:
            logger.info("No notification channels configured "
                        "(set DISCORD_WEBHOOK_URL, TELEGRAM_*, or SMTP_* in .env)")

    def send(self, subject: str, body: str) -> None:
        for name, sender in self.channels:
            try:
                sender(subject, body)
            except Exception as exc:
                logger.error("Notification via %s failed: %s", name, exc)

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------
    def trade_opened(self, symbol: str, direction: str, qty: float,
                     entry: float, hard_stop: float, reason: str) -> None:
        self.send(
            f"OPENED {direction.upper()} {symbol}",
            f"qty {qty} @ ${entry:,.2f}\n"
            f"hard stop: ${hard_stop:,.2f} (1% equity)\n"
            f"reason: {reason}",
        )

    def trade_closed(self, symbol: str, direction: str, qty: float,
                     exit_price: float, pnl: float, reason: str) -> None:
        emoji = "🟢" if pnl >= 0 else "🔴"
        self.send(
            f"{emoji} CLOSED {direction.upper()} {symbol}: {_money(pnl)}",
            f"qty {qty} @ ${exit_price:,.2f}\nreason: {reason}",
        )

    def daily_summary(self, day: str, realized: float, equity,
                      trades_today: int, open_positions: dict) -> None:
        pos_lines = "\n".join(
            f"  {s}: {p.direction} {p.qty} @ ${p.entry_price:,.2f}"
            for s, p in open_positions.items()
        ) or "  none"
        equity_str = f"${equity:,.2f}" if equity is not None else "unavailable"
        self.send(
            f"📊 Daily summary {day}: {_money(realized)}",
            f"realized P&L: {_money(realized)}\n"
            f"account equity: {equity_str}\n"
            f"trades closed today: {trades_today}\n"
            f"open positions:\n{pos_lines}",
        )

    # ------------------------------------------------------------------
    # Transports
    # ------------------------------------------------------------------
    @staticmethod
    def _send_discord(subject: str, body: str) -> None:
        resp = requests.post(
            config.DISCORD_WEBHOOK_URL,
            json={"content": f"**{subject}**\n{body}"},
            timeout=10,
        )
        resp.raise_for_status()

    @staticmethod
    def _send_telegram(subject: str, body: str) -> None:
        resp = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID,
                  "text": f"{subject}\n{body}"},
            timeout=10,
        )
        resp.raise_for_status()

    @staticmethod
    def _send_email(subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"[trading-bot] {subject}"
        msg["From"] = config.SMTP_USER
        msg["To"] = config.NOTIFY_EMAIL
        msg.set_content(body)
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                              timeout=15) as smtp:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    n = Notifier()
    if not n.channels:
        raise SystemExit("No channels configured — nothing to test.")
    n.send("Test notification", "If you can read this, notifications work.")
    print(f"Sent test message to: {', '.join(name for name, _ in n.channels)}")
