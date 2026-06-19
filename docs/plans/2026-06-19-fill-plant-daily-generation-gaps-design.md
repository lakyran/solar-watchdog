# Fill Plant Daily-Generation Gaps — Design

**Date:** 2026-06-19
**Status:** Approved
**New file:** `scripts/fill_plant_daily_generation_gaps.py`
**New tests:** `tests/test_fill_plant_daily_generation_gaps.py`

## Goal

Read the latest gap report produced by
`scripts/check_plant_daily_generation_gaps.py` and backfill every missing
daily-generation range by calling the existing ingest API, **one gap range at a
time** per plant. Default target is the **local** server; a flag switches to
**production**.

## Inputs

- **Report:** latest file in `reports/` matching
  `plant-daily-generation-gap-report-YYYY-MM-DD_HHMMSS.json` (selected by the
  embedded timestamp; overridable with `--report`). Shape: `users[] → plants[]`,
  each plant has `plant_id`, `vendor`, `status`, and `gap_ranges[]`
  (`{start, end, days}`). `gap_ranges` also covers `no_data` plants whose
  expected window is known, so both non-complete statuses are handled uniformly.
- **Fill endpoint:** `GET /api/plants/energy/daily/ingest?plant_id=&start_date=&end_date=`
  (`@jwt_required()`, admin token covers any plant). It **already chunks the
  range into 6-day windows internally** with 1s sleeps, so one call per gap range
  is safe even for a multi-month range. Success → `{status, database_summary:{total_inserted,total_updated}}`;
  Growatt-had-no-data → `{status:"warning"}` (non-fatal).
- **Auth:** `POST /api/auth/login {username,password}` → `{access_token}`.
  Defaults `admin`/`admin` (matches the job scripts), env-overridable.
- **URLs:** local `http://localhost:5001` (default); `--prod` →
  `https://unisolartech-watchdog-databox-bgdqfzedhnd5ecbt.centralindia-01.azurewebsites.net`;
  `--base-url` overrides both.

## Behavior

1. Resolve target URL; locate + load report; flatten every non-complete plant's
   `gap_ranges` into a flat list, applying optional `--plant-id` / `--user`
   filters.
2. Print a plan summary (plants, ranges, total missing days, target URL, mode).
3. **Dry-run (default) = zero network:** prints the complete plan including the
   exact request it would make per range. No login, no writes.
4. **`--apply` (live):** login once, reuse the bearer token (re-login once on a
   401), and **prompt `y/n/a/q` before each range** (the write gate).
   `--yes`/`-y` skips prompts for unattended runs. Calls the ingest endpoint per
   range, logs `success`/`warning`/`error`, tallies inserted/updated, and spaces
   calls to avoid hammering Growatt: **`--range-delay` (default 10s)** between
   consecutive ranges of the same plant, **`--plant-delay` (default 20s)** when
   moving to a different plant. No wait before the first call; skipped ranges
   don't advance the spacing clock.
5. Print a final tally; exit non-zero if any live call failed.

Rationale for prompts in live mode only: dry-run is already non-destructive, so
per-range prompts there add friction without safety value. The prompt is the
live-mode write gate.

## CLI

`--prod`, `--base-url URL`, `--apply`, `--yes/-y`, `--report PATH`,
`--plant-id ID`, `--user NAME`, `--username`, `--password`
(env `WATCHDOG_ADMIN_USER` / `WATCHDOG_ADMIN_PASS`), `--timeout SEC` (default
600), `--range-delay SEC` (default 10), `--plant-delay SEC` (default 20),
`--reports-dir DIR` (default `reports/`).

## Testable (pure) helpers

- `find_latest_report(dir, prefix)` — glob + regex-extract stamp, return max.
- `load_report(path)` — `json.load`.
- `collect_gap_ranges(report, plant_id, user)` — flatten to list of range dicts,
  skipping `complete` plants and applying filters.
- `resolve_base_url(prod, base_url)` — local/prod/override resolution.
- `parse_ingest_response(payload)` — extract status/inserted/updated/message.
- `next_delay(plant_key, prev_plant_key, range_delay, plant_delay)` — pick the
  rate-limit wait (0 before the first call; range vs plant delay otherwise).

`login` / `ingest_range` / the prompt + main loop are impure (network, stdin) and
stay thin; the pure helpers carry the logic and are unit-tested.

## Conventions

Lazy `requests` import (deps aren't in the local venv → run via
`uv run --with requests ...`); same `logging.basicConfig` style and IST note as
the sibling checker scripts; shebang + argparse docstring.

## Out of scope (YAGNI)

Regenerating the gap report afterward, parallelism, progress persistence/resume.
