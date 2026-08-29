# YC Launch Monitor — Project Context

## Project goal

Build a long-running monitoring bot that detects early Y Combinator founder and launch activity across multiple public and social sources, maintains durable state between runs, and notifies a team via Slack. The system should support adding new data sources and integrations over time without major rewrites.

## Required data sources

| Source        | Purpose (planned)                                      | Status              |
|---------------|--------------------------------------------------------|---------------------|
| YC Directory  | Track companies and founders listed on YC's directory  | **Implemented**     |
| YC Speedrun   | Monitor Speedrun cohort and related launch signals     | **Implemented**     |
| X (Twitter)   | Watch posts and activity from founders and startups    | **Implemented**     |
| LinkedIn      | Monitor profile and company updates from founders      | **Implemented**     |

### YC Directory monitor (implemented)

- Fetches company records backing https://www.ycombinator.com/companies via the public Algolia search index used by that page.
- Extracts company name, YC profile URL, description, batch, website, and industry/category when available.
- Normalizes data into a shared company model with stable IDs (`yc-dir:{slug}`) and source `yc_directory`.
- Persists companies in SQLite with `first_detected_at` and `last_seen_at`.
- Detects `NEW` vs `ALREADY_SEEN` companies and avoids duplicate rows on reruns.
- Modules are split across fetch (`fetcher.py`), parse (`parser.py`), orchestration (`monitor.py`), and storage (`storage/sqlite.py`).

### YC Speedrun monitor (implemented)

- Monitors the official YC Speedrun directory/page (https://www.ycombinator.com/speedrun).
- Retrieves Speedrun company information supporting direct JSON endpoints, embedded `__NEXT_DATA__` JSON blocks, and embedded script payloads.
- Extracts company name, Speedrun profile URL, description, batch/cohort information, website, and industry/category.
- Normalizes records into the shared `ParsedCompany` model with source identifier `yc_speedrun` and stable IDs (`yc-sr:{slug}`).
- Persists companies into the SQLite `companies` table using the existing persistence architecture, preserving `first_detected_at` and updating `last_seen_at`.
- Detects `NEW` vs `ALREADY_SEEN` companies and prevents duplicate records across runs.
- Modules: `src/yc_launch_monitor/monitors/yc_speedrun/` (`fetcher.py`, `parser.py`, `monitor.py`).
- Limitations: HTML structure variations may require parser adjustments; automated continuous polling and notifications are not yet connected.

### X (Twitter) monitor (implemented)

- Monitors public X posts for founder and launch announcements mentioning YC or Speedrun acceptance (e.g. "got into YC", "accepted to YC S26", "backed by Y Combinator", "Speedrun cohort").
- Modular architecture:
  - Data collection: `fetcher.py` (queries X API v2 `/2/tweets/search/recent` via `X_BEARER_TOKEN`).
  - Signal detection: `detector.py` (pattern matching for acceptance verbs, batch extraction, company name heuristics, and exclusion filtering).
  - Post parsing: `parser.py` (normalizes tweets into `ParsedXSignal` with stable IDs `x:{post_id}` and source `x`).
  - Company confirmation matching: `matcher.py` (queries SQLite `companies` store to verify if company already exists).
  - Persistence & Orchestration: `monitor.py` & `storage/sqlite.py` (persists signals to SQLite `x_signals` table, prevents duplicate posts, preserves `detected_at`, and updates `last_seen_at`).
- **Early-detection logic**: Classifies signals as `EARLY_YC_SIGNAL` (`is_early_signal=True`, `is_confirmed_yc=False`) when the post represents a founder announcement and the company is not yet in the official YC Directory or Speedrun tables. If the company is already stored, it is classified as a confirmed social signal (`is_confirmed_yc=True`, `is_early_signal=False`).
- **API credentials & testing**: Live search requires `X_BEARER_TOKEN` in `.env`. Offline and automated testing runs via fixture data without live API access.

### LinkedIn monitor (implemented)

- Monitors founder and company posts on LinkedIn for YC and Speedrun acceptance and launch announcements.
- Modular architecture under `src/yc_launch_monitor/monitors/linkedin/`:
  - Data collection: `fetcher.py` (clean provider/API abstraction requiring OAuth 2.0 `LINKEDIN_ACCESS_TOKEN` for live API operations; avoids aggressive/unauthorized scraping).
  - Signal detection: `detector.py` (regex pattern matching for YC and Speedrun acceptance verbs, batch extraction e.g. S26/W27/Speedrun Winter 2024, company name heuristics, and exclusion filters for job postings/advice/rejections).
  - Post parsing: `parser.py` (normalizes posts and nested commentary payloads into `ParsedLinkedInSignal` with stable IDs `li:{post_id}` and source `linkedin`).
  - Company confirmation matching: `matcher.py` (cross-references detected company and author names against local SQLite `companies` table).
  - Persistence & Orchestration: `monitor.py` & `storage/sqlite.py` (persists signals to SQLite `linkedin_signals` table, prevents duplicate posts, preserves `detected_at`, and updates `last_seen_at`).
- **Signal classification**:
  - `EARLY_YC_SIGNAL`: Founder/company announces acceptance into YC, but the company is not yet present in the official YC Directory/Speedrun database (`is_early_signal=True`, `is_confirmed_yc=False`).
  - `CONFIRMED_YC`: Company is already confirmed in the local SQLite directory database (`is_confirmed_yc=True`, `is_early_signal=False`).
  - `SPEEDRUN_SIGNAL`: Post represents a verified Speedrun cohort announcement (`is_speedrun_signal=True`).
- **API credentials & testing**: Live search requires `LINKEDIN_ACCESS_TOKEN` in `.env`. Offline and automated testing runs via fixture data without live API access.

### Scheduler (implemented)

- Executes all four monitors (YC Directory, YC Speedrun, X, and LinkedIn) sequentially in a recurring loop.
- Configurable polling interval via `MONITOR_INTERVAL_SECONDS` (default: 300 seconds / 5 minutes).
- **Fault-tolerant / Failure-isolated**: If any monitor fails or encounters a network error, other monitors continue running and the scheduler proceeds with future cycles.
- **Graceful shutdown**: Cleanly handles SIGINT (Ctrl+C) and SIGTERM.
- Module: `src/yc_launch_monitor/scheduler.py` (`MonitorScheduler`, `CycleSummary`).

## Required Slack integration

- Send alerts to a configured Slack channel when new or notable founder/launch signals are detected.
- Credentials will be supplied via environment variables (see `.env.example`).

*Not implemented yet.*

## Required persistent state

- Store seen entities, last-checked timestamps, and deduplication keys so the bot can run continuously without re-alerting on the same events.
- Default local storage path: `./data/state.db` (configurable via `STATE_DB_PATH`).
- YC Directory and Speedrun companies are stored in `companies` table; social signals are stored in `x_signals` and `linkedin_signals` tables.

*Partially implemented — YC Directory, YC Speedrun, X signals, and LinkedIn signals.*

## Required early YC founder detection

- Identify signals that suggest a person or company is an early-stage YC founder or pre-launch YC-related entity before broad public awareness.
- X and LinkedIn monitors implement early-detection matching against local directory state. Additional heuristics and AI classification will be expanded in later steps.

*Partially implemented — X and LinkedIn early detection logic.*

## Required Pond integration

- Push or sync detected leads/signals into Pond for downstream workflow.
- API details and authentication will be configured via environment variables.

*Not implemented yet.*

## Requirement for future extensibility

- Modular package layout under `src/yc_launch_monitor/` so new monitors, notifiers, and storage backends can be added as separate modules.
- Configuration via environment variables and `.env` (see `.env.example`).
- Avoid hard-coding credentials or vendor-specific logic in a single monolithic script.

## Current project status

**Step 6 — Scheduler**

- YC Directory, YC Speedrun, X (Twitter), and LinkedIn fetch/parse/store pipelines are implemented with CLI support and fixture-based tests.
- Continuous multi-source scheduler with failure isolation is implemented.
- Slack, Pond, and AI classification are not implemented.
- The overall monitoring bot is **not complete**.


