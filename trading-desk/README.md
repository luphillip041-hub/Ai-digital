# Flip Trading Desk

Isolated trading-research desk for Flip, powered by a **native multi-agent engine** (`desk_agents/`) built into this repo — no external agent framework dependency. This folder contains every trading-desk artifact: config, runs, cache, scripts, Discord bot, and deploy files.

## What this is

- An orchestrator + sub-agent research pipeline: analysts → bull/bear debate → research manager → trader → risk manager → portfolio manager.
- Each sub-agent runs with its own isolated conversation history; the orchestrator controls exactly what flows between them, so prompts stay small and call counts stay flat.
- All market data is fetched **deterministically before any agent runs** (zero LLM tool loops), so every run's LLM-call count is exact and known in advance.
- Produces structured JSON decisions for the Discord bot / dashboards.
- Research/paper-trading scaffold only — not financial advice and not auto-execution.

## Architecture

```text
scan_watchlist.py (0 LLM calls)          run_desk_analysis.py
  score watchlist deterministically  →     budget guard (exact call plan vs monthly cap)
  pick finalists                             │
                                             ▼
                                     DeskOrchestrator (desk_agents/)
                                       stage 0  fetch OHLCV/news/fundamentals   0 calls
                                       stage 1  analyst sub-agents              1 call each
                                                market · news · fundamentals · social
                                       stage 2  bull vs bear debate             2 calls/round
                                       stage 3  research manager (deep model)   1 call
                                                trader                          1 call
                                                risk manager                    1 call/round
                                                portfolio manager (deep model)  1 call → JSON
                                             │
                                             ▼
                                     runs/<TICKER>_<date>.json + SQLite ledger
                                     (planned AND actual calls + tokens recorded)
```

Default team (market+news, 1 debate round, 1 risk round): **exactly 8 LLM calls**. Full stack (`--full`): 10 calls.

## Folder boundary

```text
Ai-digital/
  app/                 # existing Next.js revenue app, left untouched
  trading-desk/        # Flip trading desk starts here
    .env.example
    requirements.txt
    desk_agents/       # native multi-agent engine
      llm.py           #   provider-agnostic chat client + usage meter
      subagent.py      #   sub-agent primitive (isolated history)
      marketdata.py    #   deterministic data layer (indicators/news/fundamentals)
      orchestrator.py  #   the desk team + pipeline
    scripts/
      setup.sh
      scan_watchlist.py
      run_desk_analysis.py
      openalice_bridge.py
    bot/
      discord_bot.py
    deploy/
      flip-trading-desk-bot.service
    Dockerfile
    docker-compose.yml
    runs/              # generated decisions + ledger, ignored by git
    .cache/            # generated data, ignored by git
```

## Cost-control design

| Layer | Typical multi-agent framework | Flip desk |
|---|---|---|
| Tool loops | LLM decides, count varies | none — data pre-fetched deterministically |
| Call count | estimated | **exact plan**, enforced pre-run |
| Usage tracking | none | actual calls + tokens recorded per run |
| Analysts | all | market, news (opt-in fundamentals/social) |
| Debate | multi-round | 1 round default |
| Output tokens | unbounded | capped per call (`FLIP_DESK_MAX_OUTPUT_TOKENS`) |
| Budget guard | none | SQLite monthly call cap, `--force` to override |
| Model routing | one model | quick model for most agents, deep model for synthesis/final call |
| Offline mode | none | `--model-profile offline` runs the whole pipeline with zero network/keys |

Use `--full` only when you specifically want the expensive four-analyst stack.

## Setup

```bash
cd trading-desk
bash scripts/setup.sh
```

Then edit `.env` from `.env.example` and add keys.

Minimum recommended key:

```text
DEEPSEEK_API_KEY=...
```

The engine speaks the OpenAI-compatible chat API, so `deepseek`, `openai`, `openrouter`, or any `openai_compatible` local endpoint works. Verify exact model IDs in your provider console and set `FLIP_DESK_QUICK_MODEL` / `FLIP_DESK_DEEP_MODEL` accordingly.

## Market data: Alpaca or Yahoo

The scanner and the desk pull daily bars and headlines through one shared data layer with two sources:

| Source | What it needs | Notes |
|---|---|---|
| `alpaca` | `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` (same vars as the repo's Alpaca bot) | Alpaca Market Data REST API, free `iex` feed by default; stocks/ETFs |
| `yahoo` | nothing | yfinance; also covers crypto-style symbols like `BTC-USD` |

Default `FLIP_DESK_DATA_SOURCE=auto` prefers Alpaca when keys are set and falls back to Yahoo per symbol (crypto pairs, Alpaca outage). Force one with `--data-source alpaca|yahoo` on either script. The LLM side is independent — DeepSeek (or any provider) analyzes whatever data source supplied.

## Discord bot — shared 24/7 access

Commands available to everyone in allowed Discord channels:

```text
!scan SPY,QQQ,NVDA,TSLA  # zero-LLM watchlist scanner
!preflight AAPL          # exact call plan + budget check, no LLM spend
!desk AAPL               # low-burn multi-agent analysis (8 calls)
!deskfull NVDA           # full four-analyst stack (10 calls)
!budget                  # monthly LLM-call ledger (actual usage)
!runs                    # recent saved JSON artifacts
!deskhelp                # command help
```

Create a Discord bot token:

1. Discord Developer Portal → New Application → Bot.
2. Enable **Message Content Intent**.
3. Invite with `View Channels`, `Send Messages`, `Read Message History`.
4. Put the token in `.env` as `DISCORD_BOT_TOKEN=...`.
5. Recommended: set `FLIP_DESK_ALLOWED_GUILD_IDS` / `FLIP_DESK_ALLOWED_CHANNEL_IDS` so only your channels can spend budget.

Run locally:

```bash
source .venv/bin/activate
bash scripts/run_discord_bot.sh
```

Run 24/7 with Docker:

```bash
docker compose up -d --build
docker compose logs -f flip-trading-desk-bot
```

Run 24/7 with systemd instead:

```bash
sudo cp deploy/flip-trading-desk-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flip-trading-desk-bot
sudo journalctl -u flip-trading-desk-bot -f
```

The bot queues `!desk`/`!deskfull` one at a time so Discord users cannot accidentally spawn five expensive model runs at once.

## Run examples

Zero-token watchlist scan first:

```bash
python scripts/scan_watchlist.py --symbols SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT --max-finalists 3
```

Cheap/default desk pass on a scanner finalist:

```bash
python scripts/run_desk_analysis.py AAPL --date 2026-07-01
```

Preflight only — exact call plan and monthly budget, no model calls:

```bash
python scripts/run_desk_analysis.py AAPL --preflight-only
```

Offline dry run — full pipeline, deterministic canned agents, zero network/keys:

```bash
python scripts/run_desk_analysis.py AAPL --model-profile offline
```

Monthly cap guard (default 250 calls/month):

```bash
python scripts/run_desk_analysis.py NVDA --monthly-llm-call-cap 1000
python scripts/run_desk_analysis.py NVDA --force   # bypass cap once
```

Model routing:

```bash
python scripts/run_desk_analysis.py AAPL --model-profile cheap
python scripts/run_desk_analysis.py AAPL --model-profile balanced
python scripts/run_desk_analysis.py AAPL --model-profile local --backend-url http://localhost:1234/v1
python scripts/run_desk_analysis.py AAPL --quick-model deepseek-v4-flash --deep-model deepseek-v4-pro
```

Analyst selection:

```bash
python scripts/run_desk_analysis.py SPY --analysts market
python scripts/run_desk_analysis.py NVDA --analysts market,news,fundamentals
python scripts/run_desk_analysis.py NVDA --full
```

Extra debate scrutiny (costs 2 more calls per round):

```bash
python scripts/run_desk_analysis.py NVDA --debate-rounds 2
```

OpenAlice cockpit prompt:

```bash
python scripts/openalice_bridge.py --symbols SPY,QQQ,NVDA,TSLA --max-finalists 3
```

See `trading-desk/openalice/README.md` for install/start/headless details.

## The sub-agent team

| Agent | Model tier | Job |
|---|---|---|
| market_analyst | quick | trend/momentum/volatility read from the indicator snapshot |
| news_analyst | quick | catalyst and binary-event risk from capped headlines |
| fundamentals_analyst | quick | valuation/growth/balance-sheet read (opt-in) |
| sentiment_analyst | quick | positioning/crowd read (opt-in, `social`) |
| bull_researcher | quick | strongest honest long case; rebuts the bear across rounds |
| bear_researcher | quick | strongest honest bear case; rebuts the bull across rounds |
| research_manager | deep | weighs the debate, issues thesis + conviction |
| trader | quick | entry/stop/target/time-limit/size paper plan (max 5% of book) |
| risk_manager | quick | aggressive/conservative/neutral stress + verdict |
| portfolio_manager | deep | final authority; emits strict JSON decision |

Each agent sees only what the orchestrator hands it — never another agent's raw history. The bull and bear keep their own private histories across debate rounds, so rebuttals are genuinely stateful.

## Ledger

SQLite at `runs/desk_ledger.sqlite3`. Every run records the planned call count, and completed runs also record **actual** calls plus prompt/completion tokens from provider usage data. The monthly budget check prefers actuals when available. Existing ledgers from the previous engine are migrated automatically (new columns added in place).

## Next fixes to build

1. Small dashboard for scan/runs/budget visibility.
2. Deterministic position-risk engine before any paper trade adapter.
3. Paper-trading execution only after the research layer proves useful.
