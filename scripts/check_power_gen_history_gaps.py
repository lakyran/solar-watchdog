#!/usr/bin/env python3
"""Check per-device ingestion gaps in power_gen_history.

For every inverter, this script verifies that at least one generation
record was ingested for each calendar day from the device's *first*
recorded day through today (inclusive). Devices with missing days are
reported, with the gaps grouped into consecutive-day ranges.

Design notes:
- The gap-detection algorithm is pure (stdlib-only) and lives at module
  top level so it can be unit-tested without a database connection.
- All database / dotenv imports are deferred into ``main()``.
- Read-only: no writes to the database; the pooled connection is
  returned in a ``finally`` block.

Usage:
    python scripts/check_power_gen_history_gaps.py
    python scripts/check_power_gen_history_gaps.py --output reports/x.json
    python scripts/check_power_gen_history_gaps.py --end-date 2026-06-18
"""
import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Make the repo root importable (so `from src.azure_db import AzureDB`
# resolves when run from anywhere). Heavy imports stay lazy in main().
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Indian Standard Time (UTC+05:30) — the timezone used throughout the app.
IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure gap-detection logic (no DB, fully unit-tested)
# ---------------------------------------------------------------------------
def _date_range(start, end):
    """Inclusive list of ``date`` objects from ``start`` to ``end``.

    Returns an empty list when ``start`` is after ``end``.
    """
    out = []
    cur = start
    step = timedelta(days=1)
    while cur <= end:
        out.append(cur)
        cur += step
    return out


def compute_gap_ranges(missing_dates):
    """Group an iterable of dates into consecutive-day ranges.

    Returns a list of dicts sorted by start date, each shaped as
    ``{"start": date, "end": date, "days": int}`` where ``days`` is the
    inclusive count of days in the range.
    """
    dates = sorted(set(missing_dates))
    if not dates:
        return []

    ranges = []
    start = prev = dates[0]
    for current in dates[1:]:
        if (current - prev).days == 1:
            prev = current
            continue
        ranges.append({"start": start, "end": prev, "days": (prev - start).days + 1})
        start = prev = current
    ranges.append({"start": start, "end": prev, "days": (prev - start).days + 1})
    return ranges


def analyze_device(present, today, no_data_start=None):
    """Compute the ingestion-gap analysis for a single device.

    Args:
        present: iterable of ``date`` objects with at least one record.
        today: ``date`` — inclusive end of the expected window.
        no_data_start: ``date`` or ``None`` — window start used when the
            device has no records at all (e.g. the user's registration
            date).

    Returns a dict with: status ("complete" | "gaps" | "no_data"),
    first_record_date, last_record_date, expected_window {start, end},
    expected_days, present_days, missing_days, gap_ranges, missing_today.
    """
    present = set(present)
    empty_result_base = {
        "first_record_date": None,
        "last_record_date": None,
        "present_days": 0,
    }

    if not present:
        # Device has never been ingested.
        if no_data_start is None or no_data_start > today:
            return {
                **empty_result_base,
                "status": "no_data",
                "expected_window": {"start": None, "end": today},
                "expected_days": 0,
                "missing_days": 0,
                "gap_ranges": [],
                "missing_today": False,
            }
        expected = _date_range(no_data_start, today)
        return {
            **empty_result_base,
            "status": "no_data",
            "expected_window": {"start": no_data_start, "end": today},
            "expected_days": len(expected),
            "missing_days": len(expected),
            "gap_ranges": compute_gap_ranges(expected),
            "missing_today": True,
        }

    first = min(present)
    last = max(present)
    expected = set(_date_range(first, today))
    present_in_window = present & expected  # ignore any stray future dates
    missing = sorted(expected - present_in_window)

    return {
        "status": "complete" if not missing else "gaps",
        "first_record_date": first,
        "last_record_date": last,
        "expected_window": {"start": first, "end": today},
        "expected_days": len(expected),
        "present_days": len(present_in_window),
        "missing_days": len(missing),
        "gap_ranges": compute_gap_ranges(missing),
        "missing_today": today in missing,
    }


def report_file_stamp(generated_dt):
    """Filesystem-safe timestamp (``YYYY-MM-DD_HHMMSS``) for the report filename.

    Includes the time of day so multiple runs on the same date do not
    overwrite each other. Colons are avoided for cross-platform safety.
    """
    return generated_dt.strftime("%Y-%m-%d_%H%M%S")


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------
def _fetch_device_rows(cursor):
    """All inverters with their owning user and plant (distinct)."""
    cursor.execute(
        """
        SELECT DISTINCT device_sn, user_name, device_type, vendor, plant_id
        FROM inverters
        ORDER BY user_name, device_sn
        """
    )
    return cursor.fetchall()


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


def _fetch_present_days_by_device(cursor):
    """Map device_sn -> set of dates that have at least one record."""
    cursor.execute(
        """
        SELECT device_sn, DATE(datetime) AS d
        FROM power_gen_history
        GROUP BY device_sn, DATE(datetime)
        """
    )
    present = defaultdict(set)
    for device_sn, day in cursor.fetchall():
        present[device_sn].add(day)
    return present


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _jsonable(obj):
    """Recursively convert date/datetime to 'YYYY-MM-DD' strings for JSON."""
    if isinstance(obj, (date, datetime)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def _format_date(d):
    return d.strftime("%Y-%m-%d") if d else "unknown"


def _print_console(report, output_path):
    today = report["expected_through_ist"]
    totals = report["totals"]
    print()
    print(f"Ingestion gap report — generated {report['generated_at_ist']}")
    print(f"Expected window per device: first_record → {today} (today inclusive)")
    print(
        f"Checked {totals['users_checked']} users / {totals['devices_checked']} devices. "
        f"{totals['devices_with_gaps']} devices have gaps, "
        f"{totals['devices_no_data']} have no data. "
        f"{totals['total_missing_device_days']} total missing device-days."
    )

    flagged_users = [
        u for u in report["users"]
        if any(d["status"] != "complete" for d in u["devices"])
    ]
    if not flagged_users:
        print("\nNo gaps found. Every device has at least one record per day "
              "through today.\n")
        return

    print()
    for user in flagged_users:
        print(user["user_name"])
        for dev in user["devices"]:
            if dev["status"] == "complete":
                continue
            device_sn = dev["device_sn"]
            plant_id = dev.get("plant_id") or "?"
            if dev["status"] == "no_data":
                start = dev["expected_window"]["start"]
                print(
                    f"  {device_sn} (plant {plant_id}): NO DATA"
                    f"{f' since {start}' if start else ''}"
                    f" ({dev['missing_days']} days missing)"
                )
            else:
                print(
                    f"  {device_sn} (plant {plant_id}): "
                    f"{dev['first_record_date']} → {today} | "
                    f"{dev['missing_days']} missing"
                )
                for span in dev["gap_ranges"]:
                    line = (f"    {span['start']} → {span['end']} "
                            f"({span['days']} days)")
                    if dev["missing_today"]:
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
             "Default: reports/power-gen-history-gap-report-<today>.json",
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
        / f"power-gen-history-gap-report-{report_file_stamp(generated_dt)}.json"
    )

    load_dotenv()
    db = AzureDB()

    conn = None
    cursor = None
    try:
        conn = db.connection_pool.getconn()
        cursor = conn.cursor()

        logger.info("Fetching devices, users, and present days ...")
        device_rows = _fetch_device_rows(cursor)
        registered_on = _fetch_registered_on_by_user(cursor)
        present_by_device = _fetch_present_days_by_device(cursor)
    finally:
        if cursor:
            cursor.close()
        if conn:
            db.connection_pool.putconn(conn)

    # Build per-user, per-device analysis.
    users_devices = defaultdict(list)
    devices_with_gaps = 0
    devices_no_data = 0
    total_missing_device_days = 0

    for device_sn, user_name, device_type, vendor, plant_id in device_rows:
        present = present_by_device.get(device_sn, set())
        no_data_start = registered_on.get(user_name) if not present else None
        analysis = analyze_device(present, today, no_data_start=no_data_start)

        analysis["device_sn"] = device_sn
        analysis["user_name"] = user_name
        analysis["plant_id"] = plant_id
        analysis["vendor"] = vendor

        if analysis["status"] == "gaps":
            devices_with_gaps += 1
            total_missing_device_days += analysis["missing_days"]
        elif analysis["status"] == "no_data":
            devices_no_data += 1
            total_missing_device_days += analysis["missing_days"]

        users_devices[user_name].append(analysis)

    # Order keys for stable output: device_sn within user, users alphabetical.
    report_users = []
    for user_name in sorted(users_devices):
        devices = sorted(users_devices[user_name], key=lambda d: d["device_sn"])
        ordered = {
            "user_name": user_name,
            "devices": [
                {k: d[k] for k in (
                    "device_sn", "plant_id", "vendor", "status",
                    "first_record_date", "last_record_date", "expected_window",
                    "expected_days", "present_days", "missing_days",
                    "gap_ranges", "missing_today",
                )}
                for d in devices
            ],
        }
        report_users.append(ordered)

    report = {
        "generated_at_ist": generated_at,
        "expected_through_ist": today.strftime("%Y-%m-%d"),
        "include_today": True,
        "totals": {
            "users_checked": len(report_users),
            "devices_checked": sum(len(u["devices"]) for u in report_users),
            "devices_with_gaps": devices_with_gaps,
            "devices_no_data": devices_no_data,
            "total_missing_device_days": total_missing_device_days,
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
