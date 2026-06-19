#!/usr/bin/env python3
"""Check per-plant ingestion gaps in plant_daily_generation_history.

For every plant (identified by the ``(plant_id, vendor)`` pair that uniquely
keys the table), this script verifies that at least one daily generation
record was ingested for each calendar day from the plant's *first* recorded
day through today (inclusive). Plants with missing days are reported, with
the gaps grouped into consecutive-day ranges.

This is the plant-level analogue of ``check_power_gen_history_gaps.py``
(which does the same thing per inverter for ``power_gen_history``). The gap
algorithm is identical, so it is imported from that module rather than
duplicated; only the plant-specific database layer and ``(plant_id, vendor)``
grouping live here.

Design notes:
- The grouping helper (``_group_present_by_plant``) is pure (stdlib-only)
  and lives at module top level so it can be unit-tested without a database.
- All database / dotenv imports are deferred into ``main()``.
- Read-only: no writes to the database; the pooled connection is returned
  in a ``finally`` block.

Usage:
    python scripts/check_plant_daily_generation_gaps.py
    python scripts/check_plant_daily_generation_gaps.py --output reports/x.json
    python scripts/check_plant_daily_generation_gaps.py --end-date 2026-06-18
"""
import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the repo root importable (so `from src.azure_db import AzureDB`
# resolves when run from anywhere) AND put the scripts/ dir on sys.path so
# the shared algorithm can be imported from the sibling module. Heavy
# imports (dotenv, src.azure_db) stay lazy in main().
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

# Reuse the shared, already-tested gap algorithm from the sibling script.
# `analyze_device` is generic in behaviour (it only knows about a set of
# present dates vs. an expected window), so it is reused verbatim under a
# plant-appropriate name.
from check_power_gen_history_gaps import (  # noqa: E402
    analyze_device as analyze_plant,
    compute_gap_ranges,  # noqa: F401  (re-exported for tests / consumers)
    report_file_stamp,
    _jsonable,
)

# Indian Standard Time (UTC+05:30) — the timezone used throughout the app.
IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure grouping logic (no DB, unit-tested)
# ---------------------------------------------------------------------------
def _group_present_by_plant(rows):
    """Group ``(plant_id, vendor, date)`` rows into a map keyed by plant.

    Returns ``{(plant_id, vendor): {date, ...}}``. A plant is the
    ``(plant_id, vendor)`` pair (the table's unique key), so two rows that
    share a ``plant_id`` but differ in ``vendor`` are kept separate.
    Duplicate (key, date) rows collapse via the set.
    """
    present = defaultdict(set)
    for plant_id, vendor, day in rows:
        present[(plant_id, vendor)].add(day)
    return present


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------
def _fetch_plant_rows(cursor):
    """All plants with their owning user (distinct on plant_id, vendor)."""
    cursor.execute(
        """
        SELECT DISTINCT plant_id, vendor, plant_name, user_name
        FROM plants
        ORDER BY user_name, plant_id, vendor
        """
    )
    return cursor.fetchall()


def _fetch_present_days_by_plant(cursor):
    """Map ``(plant_id, vendor)`` -> set of dates that have at least one row."""
    # Cast date::date: the column is stored as TEXT (Growatt 'YYYY-MM-DD'
    # strings are inserted verbatim), and analyze_plant needs real date
    # objects. The cast is a no-op if the column is ever migrated to DATE.
    cursor.execute(
        """
        SELECT plant_id, vendor, date::date AS d
        FROM plant_daily_generation_history
        GROUP BY plant_id, vendor, date
        """
    )
    return _group_present_by_plant(cursor.fetchall())


def _fetch_created_date_by_plant(cursor):
    """Map ``(plant_id, vendor)`` -> earliest plant created_date (or absent).

    Used as the expected-window start for plants that have no history rows
    at all. Old plants may have a NULL ``created_date`` (the column was added
    later), in which case the entry is simply absent and callers fall back to
    the owning user's ``registered_on``.
    """
    cursor.execute(
        """
        SELECT plant_id, vendor, MIN(created_date)::date AS created_date
        FROM plants
        WHERE created_date IS NOT NULL
        GROUP BY plant_id, vendor
        """
    )
    return {(pid, v): d for pid, v, d in cursor.fetchall()}


def _fetch_registered_on_by_user(cursor):
    """Map user_name -> registration date (or None)."""
    cursor.execute(
        """
        SELECT user_name, MIN(registered_on)::date AS registered_on
        FROM users
        GROUP BY user_name
        """
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _format_date(d):
    return d.strftime("%Y-%m-%d") if d else "unknown"


def _print_console(report, output_path):
    today = report["expected_through_ist"]
    totals = report["totals"]
    print()
    print(f"Plant daily-generation gap report — generated {report['generated_at_ist']}")
    print(f"Expected window per plant: first_record → {today} (today inclusive)")
    print(
        f"Checked {totals['users_checked']} users / {totals['plants_checked']} plants. "
        f"{totals['plants_with_gaps']} plants have gaps, "
        f"{totals['plants_no_data']} have no data. "
        f"{totals['total_missing_plant_days']} total missing plant-days."
    )

    flagged_users = [
        u for u in report["users"]
        if any(p["status"] != "complete" for p in u["plants"])
    ]
    if not flagged_users:
        print("\nNo gaps found. Every plant has at least one record per day "
              "through today.\n")
        return

    print()
    for user in flagged_users:
        print(user["user_name"])
        for plant in user["plants"]:
            if plant["status"] == "complete":
                continue
            plant_id = plant["plant_id"]
            vendor = plant.get("vendor") or "?"
            label = f"{plant_id} ({vendor})"
            if plant["status"] == "no_data":
                start = plant["expected_window"]["start"]
                print(
                    f"  {label}: NO DATA"
                    f"{f' since {start}' if start else ''}"
                    f" ({plant['missing_days']} days missing)"
                )
            else:
                print(
                    f"  {label}: "
                    f"{plant['first_record_date']} → {today} | "
                    f"{plant['missing_days']} missing"
                )
                for span in plant["gap_ranges"]:
                    line = (f"    {span['start']} → {span['end']} "
                            f"({span['days']} days)")
                    if plant["missing_today"]:
                        line += "  | today MISSING"
                    print(line)
        print()
    print(f"Full report: {output_path}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write the JSON report. "
             "Default: reports/plant-daily-generation-gap-report-<today>.json",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End of the expected window as YYYY-MM-DD (default: today IST).",
    )
    args = parser.parse_args()

    # Deferred imports: keep module importable without DB deps (for tests).
    from dotenv import load_dotenv  # noqa: WPS433
    from src.azure_db import AzureDB  # noqa: WPS433

    generated_dt = datetime.now(IST)
    if args.end_date:
        today = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    else:
        today = generated_dt.date()

    generated_at = generated_dt.strftime("%Y-%m-%d %H:%M:%S")

    output_path = args.output or str(
        _REPO_ROOT / "reports"
        / f"plant-daily-generation-gap-report-{report_file_stamp(generated_dt)}.json"
    )

    load_dotenv()
    db = AzureDB()

    conn = None
    cursor = None
    try:
        conn = db.connection_pool.getconn()
        cursor = conn.cursor()

        logger.info("Fetching plants, users, and present days ...")
        plant_rows = _fetch_plant_rows(cursor)
        created_date_by_plant = _fetch_created_date_by_plant(cursor)
        registered_on = _fetch_registered_on_by_user(cursor)
        present_by_plant = _fetch_present_days_by_plant(cursor)
    finally:
        if cursor:
            cursor.close()
        if conn:
            db.connection_pool.putconn(conn)

    # Build per-user, per-plant analysis.
    users_plants = defaultdict(list)
    plants_with_gaps = 0
    plants_no_data = 0
    total_missing_plant_days = 0

    for plant_id, vendor, plant_name, user_name in plant_rows:
        present = present_by_plant.get((plant_id, vendor), set())
        if not present:
            # No history at all: anchor the window on the plant's created_date,
            # falling back to the owning user's registration date.
            no_data_start = (
                created_date_by_plant.get((plant_id, vendor))
                or registered_on.get(user_name)
            )
        else:
            no_data_start = None

        analysis = analyze_plant(present, today, no_data_start=no_data_start)

        analysis["plant_id"] = plant_id
        analysis["vendor"] = vendor
        analysis["plant_name"] = plant_name
        analysis["user_name"] = user_name

        if analysis["status"] == "gaps":
            plants_with_gaps += 1
            total_missing_plant_days += analysis["missing_days"]
        elif analysis["status"] == "no_data":
            plants_no_data += 1
            total_missing_plant_days += analysis["missing_days"]

        users_plants[user_name].append(analysis)

    # Order keys for stable output: plant_id within user, users alphabetical.
    report_users = []
    for user_name in sorted(users_plants):
        plants = sorted(
            users_plants[user_name],
            key=lambda p: (p["plant_id"], p["vendor"] or ""),
        )
        ordered = {
            "user_name": user_name,
            "plants": [
                {k: p[k] for k in (
                    "plant_id", "vendor", "plant_name", "status",
                    "first_record_date", "last_record_date", "expected_window",
                    "expected_days", "present_days", "missing_days",
                    "gap_ranges", "missing_today",
                )}
                for p in plants
            ],
        }
        report_users.append(ordered)

    report = {
        "generated_at_ist": generated_at,
        "expected_through_ist": today.strftime("%Y-%m-%d"),
        "include_today": True,
        "totals": {
            "users_checked": len(report_users),
            "plants_checked": sum(len(u["plants"]) for u in report_users),
            "plants_with_gaps": plants_with_gaps,
            "plants_no_data": plants_no_data,
            "total_missing_plant_days": total_missing_plant_days,
        },
        "users": report_users,
    }

    _print_console(report, output_path)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(_jsonable(report), fh, indent=2)
    logger.info("Report written to %s", output_path)


if __name__ == "__main__":
    main()
