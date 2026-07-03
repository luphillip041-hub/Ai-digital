"""Minimal OpenAI-compatible chat client with call/token accounting.

Stdlib-only (urllib) so the desk has no heavyweight SDK dependency. Works
with any OpenAI-compatible endpoint: DeepSeek, OpenAI, OpenRouter, or a
local server. The special provider ``offline`` returns deterministic
canned responses so the whole pipeline can run with zero network and
zero keys (used by tests and demos).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

PROVIDERS: dict[str, tuple[str | None, str]] = {
    # provider -> (default base_url, api key env var)
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "openai_compatible": (None, "FLIP_DESK_LLM_API_KEY"),
    "offline": (None, ""),
}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    max_output_tokens: int = 700
    timeout_seconds: int = 120
    max_retries: int = 3


@dataclass
class UsageMeter:
    """Shared across sub-agents; records what actually got spent."""

    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_agent: dict[str, int] = field(default_factory=dict)

    def record(self, agent: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.llm_calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.by_agent[agent] = self.by_agent.get(agent, 0) + 1

    def as_dict(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "calls_by_agent": dict(self.by_agent),
        }


class ChatClient:
    def __init__(self, config: LLMConfig):
        if config.provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {config.provider!r}; valid={sorted(PROVIDERS)}")
        self.config = config
        default_base, key_env = PROVIDERS[config.provider]
        self.base_url = (config.base_url or default_base or "").rstrip("/")
        self.api_key = config.api_key or os.getenv(key_env, "")
        if config.provider != "offline":
            if not self.base_url:
                raise ValueError(f"Provider {config.provider} needs a base URL (set FLIP_DESK_LLM_BACKEND_URL)")
            if not self.api_key:
                raise ValueError(f"Provider {config.provider} needs an API key (set {key_env})")

    def chat(self, messages: list[dict[str, str]], *, agent: str, meter: UsageMeter) -> str:
        if self.config.provider == "offline":
            text = _offline_response(agent, messages)
            meter.record(agent, prompt_tokens=0, completion_tokens=0)
            return text

        body = json.dumps(
            {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_output_tokens,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                usage = payload.get("usage") or {}
                meter.record(
                    agent,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                )
                return payload["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in RETRYABLE_STATUS:
                    detail = exc.read().decode("utf-8", "replace")[:400]
                    raise RuntimeError(f"LLM call failed ({exc.code}) for {agent}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            time.sleep(2**attempt)
        raise RuntimeError(f"LLM call failed for {agent} after {self.config.max_retries} attempts: {last_error!r}")


def _offline_response(agent: str, messages: list[dict[str, str]]) -> str:
    """Deterministic role-appropriate stand-ins for keyless/offline runs."""
    prompt = messages[-1]["content"] if messages else ""
    ticker = "the ticker"
    for token in prompt.replace("\n", " ").split():
        token = token.strip(".,:;()!?")
        if token.isupper() and 1 < len(token) <= 6 and token.isalpha() and token != "JSON":
            ticker = token
            break
    canned = {
        "market_analyst": (
            f"[offline] {ticker} technical read: price above 20/50-day averages, RSI in the "
            "constructive zone, volume slightly above its 20-day mean. Trend is up with "
            "orderly pullbacks; ATR supports a defined-risk swing."
        ),
        "news_analyst": (
            f"[offline] {ticker} news read: headline flow is thin and mildly positive; "
            "no imminent binary events detected in the provided items."
        ),
        "fundamentals_analyst": (
            f"[offline] {ticker} fundamentals read: valuation rich versus market but growth "
            "and margins support it; balance sheet not a concern for a short swing horizon."
        ),
        "sentiment_analyst": (
            f"[offline] {ticker} sentiment read: recent tape shows accumulation behavior; "
            "no crowding extremes evident from price/volume."
        ),
        "bull_researcher": (
            f"[offline] Bull case for {ticker}: trend, participation, and catalysts align; "
            "risk/reward favors long exposure with a stop under the 20-day average."
        ),
        "bear_researcher": (
            f"[offline] Bear case for {ticker}: extended distance from long-term averages and "
            "elevated expectations; a broad-market wobble likely hits this name harder than average."
        ),
        "research_manager": (
            f"[offline] Thesis: constructive long on {ticker} with moderate conviction. The bull "
            "case rests on verifiable trend/volume facts; the bear case is real but conditional."
        ),
        "trader": (
            f"[offline] Plan for {ticker}: enter at next session open, stop on a daily close below "
            "the 20-day average, target +2R or exit after 20 sessions. Paper size 3% of book."
        ),
        "risk_manager": (
            "[offline] Risk verdict: APPROVED with conditions. Aggressive view wants more size, "
            "conservative view wants confirmation; neutral compromise is the 3% starter with a "
            "hard stop. No leverage, no options."
        ),
        "portfolio_manager": json.dumps(
            {
                "action": "BUY",
                "conviction": "moderate",
                "rationale": f"[offline] Trend, volume and debate outcome favor a starter long in {ticker}.",
                "risk_assessment": "Defined-risk swing; invalidated on a daily close below the 20-day average.",
                "entry": "next session open",
                "stop": "daily close below 20-day average",
                "target": "+2R or 20 sessions",
                "position_size_pct": 3,
            }
        ),
    }
    return canned.get(agent, f"[offline] {agent} acknowledges: {prompt[:120]}")
