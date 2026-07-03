"""Desk orchestrator: wires sub-agents into a research pipeline.

Pipeline (default low-burn team of market+news analysts):

    deterministic data fetch          0 LLM calls
    analyst sub-agents                1 call each
    bull vs bear debate               2 calls per round
    research manager (deep model)     1 call
    trader                            1 call
    risk manager                      1 call per risk round
    portfolio manager (deep model)    1 call

Call counts are exact — `planned_calls()` is what the budget guard
checks, and the UsageMeter records what actually happened.
"""

from __future__ import annotations

import json
from typing import Any

from desk_agents.llm import ChatClient, LLMConfig, UsageMeter
from desk_agents.marketdata import fetch_fundamentals, fetch_headlines, fetch_market_brief
from desk_agents.subagent import SubAgent

ANALYST_ORDER = ("market", "news", "fundamentals", "social")

GROUND_RULES = (
    "You are part of a paper-trading research desk. Research only: never place, stage, or "
    "recommend live broker orders. Be concise (under 180 words), concrete, and cite the "
    "supplied data instead of inventing numbers."
)

SYSTEM_PROMPTS = {
    "market_analyst": (
        f"{GROUND_RULES} You are the desk's technical market analyst. Read the indicator "
        "snapshot you are given and describe trend, momentum, volatility, and participation. "
        "End with one line: 'Technical bias: bullish|bearish|neutral'."
    ),
    "news_analyst": (
        f"{GROUND_RULES} You are the desk's news analyst. Assess the supplied headlines for "
        "catalysts and binary-event risk. If headlines are missing, say so and reason only "
        "about the absence of news. End with one line: 'News bias: positive|negative|neutral'."
    ),
    "fundamentals_analyst": (
        f"{GROUND_RULES} You are the desk's fundamentals analyst. Judge valuation, growth, "
        "and balance-sheet risk from the supplied metrics for a 2-4 week swing horizon. "
        "End with one line: 'Fundamental bias: supportive|stretched|neutral'."
    ),
    "sentiment_analyst": (
        f"{GROUND_RULES} You are the desk's sentiment analyst. Infer positioning and crowd "
        "behavior from the price/volume snapshot and headlines. End with one line: "
        "'Sentiment bias: greedy|fearful|balanced'."
    ),
    "bull_researcher": (
        f"{GROUND_RULES} You argue the strongest honest LONG case from the analyst reports. "
        "Attack the bear's weakest points in later rounds. Never concede just to be agreeable."
    ),
    "bear_researcher": (
        f"{GROUND_RULES} You argue the strongest honest BEAR/AVOID case from the analyst "
        "reports. Attack the bull's weakest points in later rounds. Never concede just to be agreeable."
    ),
    "research_manager": (
        f"{GROUND_RULES} You are the research manager. Weigh the debate, keep only arguments "
        "grounded in the data, and issue a thesis with conviction low|moderate|high."
    ),
    "trader": (
        f"{GROUND_RULES} You are the desk trader. Turn the thesis into a paper trade plan: "
        "entry, stop (invalidation), target, time limit, and position size as % of a paper book "
        "(max 5%). If the thesis is neutral, say 'no trade'."
    ),
    "risk_manager": (
        f"{GROUND_RULES} You are the risk manager. Stress the plan from three angles — "
        "aggressive (too timid?), conservative (too exposed?), neutral (balanced view) — then "
        "end with one line: 'Risk verdict: APPROVED|APPROVED_WITH_CONDITIONS|REJECTED' plus conditions."
    ),
    "portfolio_manager": (
        f"{GROUND_RULES} You are the portfolio manager with final authority. Respond with ONLY "
        "a JSON object, no prose, using exactly these keys: action (BUY|SELL|HOLD), conviction "
        "(low|moderate|high), rationale, risk_assessment, entry, stop, target, position_size_pct (number, 0 if HOLD)."
    ),
}


def planned_calls(analysts: tuple[str, ...], debate_rounds: int, risk_rounds: int) -> int:
    """Exact LLM-call count for a run — this is a plan, not an estimate."""
    return len(analysts) + 2 * max(1, debate_rounds) + 1 + 1 + max(1, risk_rounds) + 1


class DeskOrchestrator:
    def __init__(
        self,
        *,
        quick: LLMConfig,
        deep: LLMConfig | None = None,
        debate_rounds: int = 1,
        risk_rounds: int = 1,
        news_limit: int = 5,
        lookback: str = "6mo",
        data_source: str | None = None,
        log=print,
    ):
        self.quick_client = ChatClient(quick)
        self.deep_client = ChatClient(deep) if deep else self.quick_client
        self.debate_rounds = max(1, debate_rounds)
        self.risk_rounds = max(1, risk_rounds)
        self.news_limit = news_limit
        self.lookback = lookback
        self.data_source = data_source
        self.log = log
        self.meter = UsageMeter()

    def _agent(self, name: str, *, deep: bool = False) -> SubAgent:
        client = self.deep_client if deep else self.quick_client
        return SubAgent(name=name, system_prompt=SYSTEM_PROMPTS[name], client=client, meter=self.meter)

    def run(self, ticker: str, trade_date: str, analysts: tuple[str, ...]) -> dict[str, Any]:
        ticker = ticker.upper()
        reports: dict[str, str] = {}

        # Stage 0 — deterministic data, zero LLM calls.
        self.log(f"[desk] gathering data for {ticker} (0 LLM calls)")
        brief = fetch_market_brief(ticker, lookback=self.lookback, source=self.data_source)
        self.log(f"[desk] market data source: {brief.source}")
        headlines = (
            fetch_headlines(ticker, limit=self.news_limit, source=self.data_source)
            if "news" in analysts
            else []
        )
        fundamentals = fetch_fundamentals(ticker) if "fundamentals" in analysts else {}

        # Stage 1 — analyst sub-agents, one call each.
        analyst_inputs = {
            "market": ("market_analyst", f"Analysis date {trade_date}.\n{brief.to_prompt()}"),
            "news": (
                "news_analyst",
                f"Analysis date {trade_date}. Ticker {ticker}. Recent headlines "
                f"(max {self.news_limit}):\n" + ("\n".join(headlines) if headlines else "(no headlines available)"),
            ),
            "fundamentals": (
                "fundamentals_analyst",
                f"Ticker {ticker}. Metrics: {json.dumps(fundamentals) if fundamentals else '(no fundamental data available)'}",
            ),
            "social": (
                "sentiment_analyst",
                f"Ticker {ticker}.\n{brief.to_prompt()}\nHeadlines:\n"
                + ("\n".join(headlines) if headlines else "(none)"),
            ),
        }
        for key in analysts:
            agent_name, prompt = analyst_inputs[key]
            self.log(f"[desk] {agent_name} analyzing…")
            reports[agent_name] = self._agent(agent_name).ask(prompt)

        analyst_digest = "\n\n".join(f"## {name}\n{text}" for name, text in reports.items())

        # Stage 2 — bull/bear debate; each researcher keeps private history across rounds.
        bull = self._agent("bull_researcher")
        bear = self._agent("bear_researcher")
        self.log(f"[desk] bull vs bear debate ({self.debate_rounds} round(s))…")
        bull_says = bull.ask(f"Ticker {ticker}. Analyst reports:\n{analyst_digest}\n\nMake the bull case.")
        bear_says = bear.ask(
            f"Ticker {ticker}. Analyst reports:\n{analyst_digest}\n\nBull argued:\n{bull_says}\n\nMake the bear case and rebut."
        )
        for round_number in range(2, self.debate_rounds + 1):
            self.log(f"[desk] debate round {round_number}…")
            bull_says = bull.ask(f"The bear responded:\n{bear_says}\n\nRebut and strengthen the bull case.")
            bear_says = bear.ask(f"The bull responded:\n{bull_says}\n\nRebut and strengthen the bear case.")
        reports["bull_researcher"] = bull.last_reply
        reports["bear_researcher"] = bear.last_reply

        # Stage 3 — synthesis, plan, risk, final call.
        self.log("[desk] research manager synthesizing…")
        thesis = self._agent("research_manager", deep=True).ask(
            f"Ticker {ticker}.\nBull:\n{reports['bull_researcher']}\n\nBear:\n{reports['bear_researcher']}\n\nIssue the thesis."
        )
        reports["research_manager"] = thesis

        self.log("[desk] trader drafting plan…")
        plan = self._agent("trader").ask(
            f"Ticker {ticker}. Thesis:\n{thesis}\n\nMarket snapshot:\n{brief.to_prompt()}\n\nWrite the paper trade plan."
        )
        reports["trader"] = plan

        risk = self._agent("risk_manager")
        self.log(f"[desk] risk review ({self.risk_rounds} round(s))…")
        verdict = risk.ask(f"Ticker {ticker}. Proposed plan:\n{plan}\n\nThesis:\n{thesis}\n\nRun the risk review.")
        for _ in range(1, self.risk_rounds):
            verdict = risk.ask("Challenge your own verdict once more; tighten conditions if needed.")
        reports["risk_manager"] = verdict

        self.log("[desk] portfolio manager finalizing…")
        final_raw = self._agent("portfolio_manager", deep=True).ask(
            f"Ticker {ticker}, date {trade_date}.\nThesis:\n{thesis}\n\nPlan:\n{plan}\n\nRisk review:\n{verdict}\n\nFinal JSON decision:"
        )
        decision = _parse_decision(final_raw)

        return {
            "decision": decision,
            "reports": reports,
            "data": {
                "market_brief": brief.to_prompt(),
                "headlines": headlines,
                "fundamentals": fundamentals,
            },
            "usage": self.meter.as_dict(),
        }


def _parse_decision(raw: str) -> dict[str, Any]:
    """PM must return JSON; salvage the object if it wrapped it in prose/fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict) and parsed.get("action"):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"action": "HOLD", "conviction": "low", "rationale": raw.strip()[:1200],
            "risk_assessment": "Portfolio manager output was not valid JSON; defaulting to HOLD.",
            "entry": "n/a", "stop": "n/a", "target": "n/a", "position_size_pct": 0}
