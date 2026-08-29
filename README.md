# YC Launch Monitor

A long-running Python monitoring bot that watches Y Combinator-related sources for early founder and launch activity, persists state across runs, and will eventually send alerts via Slack and integrate with Pond.

**Status:** Step 6 — YC Directory, YC Speedrun, X (Twitter), LinkedIn monitors, and continuous scheduler implemented. Other integrations are not built yet.

## Project layout

```
src/yc_launch_monitor/
  monitors/
    yc_directory/            YC Directory fetch, parse, and monitor logic
    yc_speedrun/             YC Speedrun fetch, parse, and monitor logic
    x/                       X (Twitter) search, signal detection, and early matching
    linkedin/                LinkedIn post search, signal detection, and early matching
  models/                    Shared domain models
  storage/                   SQLite persistence
  scheduler.py               Continuous multi-source runner with failure isolation
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

### Running the continuous scheduler

The scheduler runs all four monitors (YC Directory, YC Speedrun, X, and LinkedIn) sequentially in a recurring loop with failure isolation. A failure in one monitor (such as missing credentials or network issues) is logged and does not stop the other monitors or the scheduler.

```bash
# Start the recurring scheduler
python -m yc_launch_monitor scheduler
# or with uv:
uv run yc-launch-monitor scheduler

# Run a single cycle and exit
python -m yc_launch_monitor scheduler --once

# Override the polling interval in seconds (default: MONITOR_INTERVAL_SECONDS or 300)
python -m yc_launch_monitor scheduler --interval 60
```

### Running individual monitors

#### YC Directory monitor

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

#### YC Speedrun monitor

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

#### X (Twitter) monitor

The X monitor searches recent public posts for founder acceptance/launch language (e.g., "got into YC", "accepted to YC S26", "backed by Y Combinator", "Speedrun cohort"). It automatically checks whether the detected company is already officially confirmed in the local SQLite directory; unconfirmed entities are flagged as `EARLY_YC_SIGNAL`.

```bash
# Using the module entry point
python -m yc_launch_monitor x run

# Or, after editable install
yc-launch-monitor x run
```

On each run it prints a summary:

```
X monitor summary: discovered=... relevant_signals=... early_signals=... already_seen=... failed=...
```

#### LinkedIn monitor

The LinkedIn monitor searches founder and company posts for YC and Speedrun acceptance and launch announcements. It automatically checks whether the detected company is already officially confirmed in the local SQLite directory; unconfirmed entities are flagged as `EARLY_YC_SIGNAL`, confirmed entities as `CONFIRMED_YC`, and Speedrun announcements as `SPEEDRUN_SIGNAL`.

```bash
# Using the module entry point
python -m yc_launch_monitor linkedin run

# Or, after editable install
yc-launch-monitor linkedin run
```

On each run it prints a summary:

```
LinkedIn monitor summary: discovered=... relevant_signals=... early_signals=... speedrun_signals=... confirmed_yc=... already_seen=... failed=...
```

### Optional configuration

Optional overrides in `.env`:

```
# Application
STATE_DB_PATH=./data/state.db
LOG_LEVEL=INFO
MONITOR_INTERVAL_SECONDS=300

# YC Directory
YC_COMPANIES_URL=https://www.ycombinator.com/companies
YC_ALGOLIA_APP_ID=
YC_ALGOLIA_API_KEY=
YC_ALGOLIA_INDEX=YCCompany_production
YC_ALGOLIA_HITS_PER_PAGE=1000

# YC Speedrun
YC_SPEEDRUN_URL=https://www.ycombinator.com/speedrun

# X (Twitter) — Required for live API search
X_BEARER_TOKEN=
X_API_KEY=
X_API_SECRET=
X_SEARCH_QUERY=

# LinkedIn — Required for live API queries
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_SEARCH_QUERY=
```

## Running tests

Tests use local JSON fixtures and do **not** call live websites or external APIs.

```bash
pytest
# or with uv:
uv run --extra dev pytest
```

## Not implemented yet

- Slack alerts
- Pond integration
- AI classification
