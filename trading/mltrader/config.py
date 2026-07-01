"""Configuration loaded from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.environ.get("ALPACA_API_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get("ALPACA_SECRET_KEY", ""))
    paper: bool = field(default_factory=lambda: _env_bool("ALPACA_PAPER", True))
    symbols: list[str] = field(
        default_factory=lambda: [
            s.strip().upper()
            for s in os.environ.get("MLT_SYMBOLS", "SPY,QQQ,AAPL,MSFT,NVDA").split(",")
            if s.strip()
        ]
    )
    max_position_pct: float = field(default_factory=lambda: _env_float("MLT_MAX_POSITION_PCT", 0.20))
    max_gross_exposure: float = field(default_factory=lambda: _env_float("MLT_MAX_GROSS_EXPOSURE", 1.0))
    entry_threshold: float = field(default_factory=lambda: _env_float("MLT_ENTRY_THRESHOLD", 0.55))

    def require_keys(self) -> None:
        if not self.api_key or not self.secret_key:
            raise SystemExit(
                "ALPACA_API_KEY / ALPACA_SECRET_KEY are not set. "
                "Copy trading/.env.example, fill in your paper-trading keys, "
                "and export them into the environment."
            )
