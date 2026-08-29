# YC Launch Monitor

A long-running Python monitoring bot that watches Y Combinator-related sources for early founder and launch activity, persists state across runs, and will eventually send alerts via Slack and integrate with Pond.

**Status:** Step 3 — YC Directory and YC Speedrun monitors implemented. Other sources and integrations are not built yet.

## Project layout

```
src/yc_launch_monitor/
  monitors/
    yc_directory/            YC Directory fetch, parse, and monitor logic
    yc_speedrun/             YC Speedrun fetch, parse, and monitor logic
  models/                    Shared domain models
  storage/                   SQLite persistence
  cli.py                     Command-line entry point
data/                        Local persistent state (gitignored except .gitkeep)
logs/                        Runtime logs (gitignored except .gitkeep)
tests/                       Unit tests (fixture-based; no live external dependency)
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
pip install -e ".[dev]"
# or: pip install -r requirements.txt

# Copy environment template (fill in when other integrations are added)
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```

## Running the monitors

Persistent SQLite database is stored at `STATE_DB_PATH` (default: `./data/state.db`).

### Running the YC Directory monitor

The YC Directory monitor reads company data backing [ycombinator.com/companies](https://www.ycombinator.com/companies), normalizes each company (`yc-dir:{slug}`, source: `yc_directory`), and stores it in SQLite.

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

### Running the YC Speedrun monitor

The YC Speedrun monitor monitors companies from the YC Speedrun program ([ycombinator.com/speedrun](https://www.ycombinator.com/speedrun)), normalizes each record (`yc-sr:{slug}`, source: `yc_speedrun`), and stores it in the shared SQLite database.

```bash
# Using the module entry point
python -m yc_launch_monitor yc-speedrun run

# Or, after editable install
yc-launch-monitor yc-speedrun run
```

On each run it prints a summary:

```
YC Speedrun monitor summary: discovered=... new=... already_seen=... failed=...
```

### Optional configuration

Optional overrides in `.env`:

```
# YC Directory
YC_COMPANIES_URL=https://www.ycombinator.com/companies
YC_ALGOLIA_APP_ID=
YC_ALGOLIA_API_KEY=
YC_ALGOLIA_INDEX=YCCompany_production

# YC Speedrun
YC_SPEEDRUN_URL=https://www.ycombinator.com/speedrun
```

## Running tests

Tests use local JSON fixtures and do **not** call live websites.

```bash
pytest
# or with uv:
uv run --extra dev pytest
```

## Not implemented yet

- X (Twitter) monitoring
- LinkedIn monitoring
- Slack alerts
- Pond integration
- AI classification
- Continuous scheduler
