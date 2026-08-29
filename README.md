# YC Launch Monitor

A long-running Python monitoring bot that watches Y Combinator-related sources for early founder and launch activity, persists state across runs, and will eventually send alerts via Slack and integrate with Pond.

**Status:** Step 1 — project initialization. No data sources or integrations are implemented yet.

## Project layout

```
src/yc_launch_monitor/   Application package (to be implemented)
data/                    Local persistent state (gitignored except .gitkeep)
logs/                    Runtime logs (gitignored except .gitkeep)
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

# Install dependencies (none required yet for Step 1)
pip install -r requirements.txt

# Copy environment template (fill in when integrations are added)
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```

## Running

The application entry point is not implemented yet. Future steps will add a CLI or service runner here.
