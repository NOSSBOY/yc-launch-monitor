# YC Launch Monitor

A long-running Python monitoring bot that watches Y Combinator-related sources for early founder and launch activity, persists state across runs, and will eventually send alerts via Slack and integrate with Pond.

**Status:** Step 2 — YC Directory monitor implemented. Other sources and integrations are not built yet.

## Project layout

```
src/yc_launch_monitor/
  monitors/yc_directory/   YC Directory fetch, parse, and monitor logic
  models/                    Shared domain models
  storage/                   SQLite persistence
  cli.py                     Command-line entry point
data/                        Local persistent state (gitignored except .gitkeep)
logs/                        Runtime logs (gitignored except .gitkeep)
tests/                       Unit tests (fixture-based; no live YC dependency)
```

See [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for goals, planned integrations, and current status.

## Setup

Requires Python 3.11+.

```bash
# Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# Install the project and dependencies
pip install -e .
# or: pip install -r requirements.txt

# Copy environment template (fill in when other integrations are added)
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```

## Running the YC Directory monitor

The YC Directory monitor reads company data backing [ycombinator.com/companies](https://www.ycombinator.com/companies), normalizes each company, and stores it in SQLite at `STATE_DB_PATH` (default: `./data/state.db`).

```bash
# Using the module entry point
python -m yc_launch_monitor yc-directory run

# Or, after editable install
yc-launch-monitor yc-directory run
```

On each run it prints a summary:

```
YC Directory monitor summary: discovered=... new=... already_seen=... failed=...
```

### Optional YC Directory configuration

By default, the monitor loads the public Algolia search credentials embedded on the YC companies page. You can override them in `.env` if needed:

```
YC_ALGOLIA_APP_ID=
YC_ALGOLIA_API_KEY=
YC_ALGOLIA_INDEX=YCCompany_production
```

## Running tests

Tests use local JSON fixtures and do **not** call the live YC website.

```bash
pytest
```

## Not implemented yet

- YC Speedrun monitoring
- X (Twitter) monitoring
- LinkedIn monitoring
- Slack alerts
- Pond integration
- AI classification
- Continuous scheduler
