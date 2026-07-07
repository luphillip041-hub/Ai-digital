# Flip Trading Desk

Isolated trading-research desk for <@832503719866007552>, built around TauricResearch/TradingAgents without mixing into Taylor/Slam projects. This folder is intended to contain every trading-desk artifact for Flip: config, runs, cache, memory, scripts, and future bot glue.

## What this is

- A low-token wrapper around `TauricResearch/TradingAgents`.
- Defaults to fewer analysts, fewer news articles, one bull/bear debate round, one risk round, local checkpointing, and local memory.
- Produces structured JSON decisions for Discord bot/web dashboard integration.
- Includes a Discord command bot for shared 24/7 server access.
- Research/paper-trading scaffold only — not financial advice and not auto-execution.

## Folder boundary

```text
Ai-digital/
  app/                 # existing Next.js revenue app, left untouched
  trading-desk/        # Flip trading desk starts here
    README.md
    .env.example
    requirements.txt
    Dockerfile
    docker-compose.yml
    scripts/
      setup.sh
      scan_watchlist.py
      options_signal_scanner.py
      run_desk_analysis.py
      openalice_bridge.py
    ui/
      dashboard.py
    docs/
      options_scanner_playbook.md
      sample_options_signal.md
    bot/
      discord_bot.py
    deploy/
      flip-trading-desk-bot.service
    runs/              # generated decisions, ignored by git later
    .cache/            # generated data/checkpoints, ignored by git later
    memory/            # generated TradingAgents memory, ignored by git later
```

## Cost-control design

The upstream project can burn API tokens because it runs many agents and debates. This wrapper keeps the TradingAgents architecture but narrows the default run:

| Layer | Upstream/full behavior | Flip default |
|---|---|---|
| Analysts | market, social, news, fundamentals | market, news |
| News articles | 20 ticker / 10 global | 5 ticker / 3 global |
| Debate | configurable multi-round | 1 round |
| Risk debate | configurable multi-round | 1 round |
| Checkpoints | opt-in | on |
| Memory/cache | global `~/.tradingagents` | local `trading-desk/` |
| Budget guard | none | local SQLite estimated-call cap |
| Model profile | manual | `cheap`, `balanced`, or `local` preset |
| Output | terminal + logs | terminal + JSON in `runs/` |

Use `--full` only when the user specifically wants the expensive analyst stack.

## Setup

Invoke through the `terminal` tool or a shell:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
bash scripts/setup.sh
```

Then edit `.env` from `.env.example` and add the keys.

Minimum recommended key:

```text
DEEPSEEK_API_KEY=...
```

Optional:

```text
MINIMAX_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
ALPHA_VANTAGE_API_KEY=...
FRED_API_KEY=...
```

## Discord bot — shared 24/7 access

Commands available to everyone in allowed Discord channels:

```text
!scan SPY,QQQ,NVDA,TSLA  # zero-LLM stock scanner
!optionscan SPY,QQQ,NVDA  # options signal scanner with contract/liquidity/risk card
!vibe TSLA              # Vibe-Trading style research bridge / analyst packet
!paperopts SPY,QQQ      # run standalone Alpaca PAPER options dry-run
!outcomes               # track saved signals vs current price/target/stop
!runcard                # daily operator brief: scanner/options/outcomes/Vibe/paper
!eod                    # standalone Alpaca PAPER options EOD report
!preflight AAPL          # budget/model check, no LLM spend
!desk AAPL               # low-burn desk analysis
!deskfull NVDA           # expensive full analyst stack
!budget                  # monthly estimated LLM-call ledger
!runs                    # recent saved JSON artifacts
!deskhelp                # command help
```

Create a Discord bot token:

1. Discord Developer Portal → New Application → Bot.
2. Enable **Message Content Intent**.
3. Invite with `View Channels`, `Send Messages`, `Read Message History`.
4. Put the token in `.env` as `DISCORD_BOT_TOKEN=...`.
5. Optional: set `FLIP_DESK_ALLOWED_GUILD_IDS` / `FLIP_DESK_ALLOWED_CHANNEL_IDS` to comma-separated IDs.

Run locally:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
source .venv/bin/activate
bash scripts/run_discord_bot.sh
```

Run 24/7 with Docker:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
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

## Web UI — command-center dashboard

The Streamlit UI gives the desk a dark, glassy command-center front end:

- Home launchpad
- zero-LLM stock scanner
- options signal cards
- Vibe-Trading inspired Research Lab
- Paper Options control panel for the standalone Alpaca PAPER service
- Signal Outcomes tracker for target/stop accountability
- Daily Run Card that consolidates scanner, options, outcomes, Vibe packets, and paper-service status
- active strategy workspace
- payoff sketch for selected contract
- run artifacts / budget ledger
- diagnostics and key-presence checks

Run locally:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
source .venv/bin/activate
streamlit run ui/dashboard.py --server.port 8512 --server.address 0.0.0.0
```

Run with Docker Compose:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
docker compose up -d --build flip-trading-desk-ui
docker compose logs -f flip-trading-desk-ui
```

Open:

```text
http://localhost:8512
```

If the VPS exposes the port publicly, use the server IP with `:8512`.

## Run examples

Zero-token watchlist scan first:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
source .venv/bin/activate
python scripts/scan_watchlist.py --symbols SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT --max-finalists 3
```

Cheap/default desk pass on a scanner finalist:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
source .venv/bin/activate
python scripts/run_desk_analysis.py AAPL --date 2026-07-01
```

Preflight only — shows config, analyst set, estimated LLM calls, and monthly budget without calling any model:

```bash
python scripts/run_desk_analysis.py AAPL --date 2026-07-01 --preflight-only
```

Use the local monthly cap guard. Default is `250` estimated LLM calls/month; override intentionally:

```bash
python scripts/run_desk_analysis.py NVDA --monthly-llm-call-cap 1000
python scripts/run_desk_analysis.py NVDA --force   # bypass cap once
```

Model routing presets:

```bash
python scripts/run_desk_analysis.py AAPL --model-profile cheap
python scripts/run_desk_analysis.py AAPL --model-profile balanced
python scripts/run_desk_analysis.py AAPL --model-profile local --backend-url http://localhost:1234/v1
```

OpenAlice cockpit prompt:

```bash
python scripts/openalice_bridge.py --symbols SPY,QQQ,NVDA,TSLA --max-finalists 3
```

Vibe-Trading style research packet:

```bash
python scripts/vibe_research_bridge.py TSLA --refresh
# Optional, only if vibe-trading-ai is installed:
python scripts/vibe_research_bridge.py TSLA --refresh --run-vibe
```

This keeps Vibe as an analyst sidecar while the Flip desk remains source of truth for scanner/risk/run cards. See `docs/vibe_trading_integration.md`.

Standalone Alpaca PAPER options service from desk wrappers:

```bash
# Code/env remain in ../alpaca-paper-options; desk UI/Discord only launches/reviews it.
cd /root/flip/projects/trading-desk/Ai-digital/alpaca-paper-options
python scripts/paper_options_daily.py run-iteration --symbols SPY,QQQ,NVDA,TSLA
python scripts/paper_options_daily.py eod-report
```

Signal outcome tracker:

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
python scripts/signal_outcome_tracker.py --limit 50
```

Options signal scanner:

```bash
python scripts/options_signal_scanner.py \
  --symbols SPY,QQQ,NVDA,TSLA,AMD,AAPL,MSFT,COIN,MSTR \
  --max-signals 3
```

Outputs a full JSON scan to `runs/options_signals_latest.json` and a Discord-ready signal card to `runs/options_signal_example.md`. See `docs/options_scanner_playbook.md` for the scanner methodology.

Standalone Alpaca PAPER options cycle now lives outside the trade desk at `../alpaca-paper-options/`.

See `trading-desk/openalice/README.md` for install/start/headless details.

Use only technical/market analyst:

```bash
python scripts/run_desk_analysis.py SPY --analysts market --date 2026-07-01
```

Use market + news + fundamentals, still capped:

```bash
python scripts/run_desk_analysis.py NVDA --analysts market,news,fundamentals --date 2026-07-01
```

Full expensive mode:

```bash
python scripts/run_desk_analysis.py NVDA --full --date 2026-07-01
```

Test provider/model override:

```bash
python scripts/run_desk_analysis.py AAPL \
  --provider deepseek \
  --quick-model deepseek-v4-flash \
  --deep-model deepseek-v4-pro
```

If a provider exposes OpenRouter-style IDs, swap via `.env` or flags:

```bash
TRADINGAGENTS_QUICK_THINK_LLM=deepseek-v4-flash
TRADINGAGENTS_DEEP_THINK_LLM=minimax-m3
```

Verify exact model IDs with the provider before relying on marketing names.

## TradingAgents source reference

Upstream repo: `https://github.com/TauricResearch/TradingAgents`

Key upstream facts used here:

- Installed command: `tradingagents`
- Python API: `TradingAgentsGraph().propagate(ticker, date)`
- Config source: `tradingagents/default_config.py`
- Env overrides:
  - `TRADINGAGENTS_LLM_PROVIDER`
  - `TRADINGAGENTS_DEEP_THINK_LLM`
  - `TRADINGAGENTS_QUICK_THINK_LLM`
  - `TRADINGAGENTS_LLM_BACKEND_URL`
  - `TRADINGAGENTS_MAX_DEBATE_ROUNDS`
  - `TRADINGAGENTS_MAX_RISK_ROUNDS`
  - `TRADINGAGENTS_CHECKPOINT_ENABLED`
  - `TRADINGAGENTS_TEMPERATURE`
  - `TRADINGAGENTS_CACHE_DIR`
  - `TRADINGAGENTS_RESULTS_DIR`
  - `TRADINGAGENTS_MEMORY_LOG_PATH`

## Built improvements

- Isolated project-local cache/results/memory.
- Reduced default analyst set and capped news pulls.
- Named model profiles: `cheap`, `balanced`, `local`.
- Zero-LLM watchlist scanner for broad symbol triage.
- Zero-LLM options signal scanner with chart setup, chain liquidity, IV/expected-move context, and management plan.
- OpenAlice cockpit bridge without vendoring AGPL code.
- Discord command bot for shared server access.
- Streamlit command-center UI for scanner/options/workspace/runs/diagnostics.
- Vibe-Trading inspired research bridge and Research Lab view, sidecar-only.
- Docker Compose and systemd deployment for 24/7 operation.
- Preflight mode to estimate LLM/tool usage before spending tokens.
- SQLite run ledger at `trading-desk/runs/desk_ledger.sqlite3`.
- Monthly estimated LLM-call cap before every non-preflight run.

## Next fixes to build

1. Add a small dashboard for scan/runs/budget visibility.
2. Add deterministic position-risk engine before any paper trade adapter.
3. Add paper-trading execution only after the research layer proves useful.

## GitHub push/update instructions for Flip

The server currently does not have `gh` installed, so the simplest write path is plain git with a GitHub fine-grained token.

Flip should create a token:

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens.
2. Resource owner: `luphillip041-hub`.
3. Repository access: select `Ai-digital` or all repos.
4. Permissions:
   - Contents: Read and write
   - Pull requests: Read and write
   - Metadata: Read-only
5. Expiration: short, e.g. 7 or 30 days.
6. Send the token privately, not in a public channel.

Then updates can be pushed with:

```bash
cd /root/flip/projects/trading-desk/Ai-digital
git checkout -b feat/flip-trading-desk
git add trading-desk README.md .gitignore
git commit -m "feat: add low-burn trading desk"
git push https://TOKEN@github.com/luphillip041-hub/Ai-digital.git feat/flip-trading-desk
```

After that, open a PR from `feat/flip-trading-desk` into the repo's default branch.
