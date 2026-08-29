# YC Launch Monitor — Project Context

## Project goal

Build a long-running monitoring bot that detects early Y Combinator founder and launch activity across multiple public and social sources, maintains durable state between runs, and notifies a team via Slack. The system should support adding new data sources and integrations over time without major rewrites.

## Required data sources

| Source        | Purpose (planned)                                      | Status              |
|---------------|--------------------------------------------------------|---------------------|
| YC Directory  | Track companies and founders listed on YC's directory  | **Implemented**     |
| YC Speedrun   | Monitor Speedrun cohort and related launch signals     | Not implemented     |
| X (Twitter)   | Watch posts and activity from founders and startups    | Not implemented     |
| LinkedIn      | Monitor profile and company updates from founders      | Not implemented     |

### YC Directory monitor (implemented)

- Fetches company records backing https://www.ycombinator.com/companies via the public Algolia search index used by that page.
- Extracts company name, YC profile URL, description, batch, website, and industry/category when available.
- Normalizes data into a shared company model with stable IDs (`yc-dir:{slug}`).
- Persists companies in SQLite with `first_detected_at` and `last_seen_at`.
- Detects `NEW` vs `ALREADY_SEEN` companies and avoids duplicate rows on reruns.
- Modules are split across fetch (`fetcher.py`), parse (`parser.py`), orchestration (`monitor.py`), and storage (`storage/sqlite.py`).

## Required Slack integration

- Send alerts to a configured Slack channel when new or notable founder/launch signals are detected.
- Credentials will be supplied via environment variables (see `.env.example`).

*Not implemented yet.*

## Required persistent state

- Store seen entities, last-checked timestamps, and deduplication keys so the bot can run continuously without re-alerting on the same events.
- Default local storage path: `./data/state.db` (configurable via `STATE_DB_PATH`).
- YC Directory companies are stored in a `companies` SQLite table.

*Partially implemented — YC Directory company records only.*

## Required early YC founder detection

- Identify signals that suggest a person or company is an early-stage YC founder or pre-launch YC-related entity before broad public awareness.
- Detection logic (rules, heuristics, or AI-assisted classification) will be added in a later step.

*Not implemented yet.*

## Required Pond integration

- Push or sync detected leads/signals into Pond for downstream workflow.
- API details and authentication will be configured via environment variables.

*Not implemented yet.*

## Requirement for future extensibility

- Modular package layout under `src/yc_launch_monitor/` so new monitors, notifiers, and storage backends can be added as separate modules.
- Configuration via environment variables and `.env` (see `.env.example`).
- Avoid hard-coding credentials or vendor-specific logic in a single monolithic script.

## Current project status

**Step 2 — YC Directory monitor**

- YC Directory fetch/parse/store pipeline is implemented with CLI support and fixture-based tests.
- Slack, Pond, Speedrun, X, LinkedIn, AI classification, and scheduling are not implemented.
- The overall monitoring bot is **not complete**.
