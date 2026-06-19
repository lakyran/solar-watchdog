#!/usr/bin/env python3
"""Backfill plant daily-generation gaps by calling the ingest API.

Reads the latest gap report produced by
``scripts/check_plant_daily_generation_gaps.py`` and fills each missing
daily-generation range, **one gap range at a time** per plant, by hitting the
existing ``GET /api/plants/energy/daily/ingest`` endpoint (which itself chunks
the range into 6-day windows internally, so a single call per range is safe even
for multi-month spans).

By default the script targets the **local** server and runs in **dry-run** mode
(zero network calls — it only prints what it would do). Pass ``--apply`` to
actually ingest, and ``--prod`` to target production.

Design notes:
- Report discovery, report flattening, URL resolution and response parsing are
  pure (stdlib-only) helpers at module top level so they can be unit-tested
  without a server. The network + prompt code stays thin.
- ``requests`` is imported lazily in ``main()`` so the module is importable for
  tests without the dependency installed (the local venv does not carry it; run
  the script via ``uv run --with requests ...``).

Usage:
    # Preview every range it would fill against the local server (no writes):
    uv run --with requests scripts/fill_plant_daily_generation_gaps.py

    # Actually fill, on local, prompting y/n before each range:
    uv run --with requests scripts/fill_plant_daily_generation_gaps.py --apply

    # Fill on production, no prompts (unattended):
    uv run --with requests scripts/fill_plant_daily_generation_gaps.py --prod --apply --yes

    # Limit to one plant / one report:
    uv run --with requests scripts/fill_plant_daily_generation_gaps.py --plant-id 9354885
    uv run --with requests scripts/fill_plant_daily_generation_gaps.py --report reports/x.json
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Make the repo root importable for consistency with sibling scripts.
_REPO_ROOT = Path(__file__).resolve().parents[1]

# Indian Standard Time note: this script speaks to a server that runs in IST,
# but the report already carries IST date strings; no local tz math is needed.

REPORTS_DIR = _REPO_ROOT / "reports"
REPORT_PREFIX = "plant-daily-generation-gap-report-"
# Filename tail looks like "...-YYYY-MM-DD_HHMMSS.json". The stamp sorts
# lexicographically == chronologically, so the max stamp is the latest report.
REPORT_STAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{6})\.json$")

PROD_BASE_URL = "https://unisolartech-watchdog-databox-bgdqfzedhnd5ecbt.centralindia-01.azurewebsites.net"
DEFAULT_LOCAL_BASE_URL = "http://localhost:5001"
INGEST_PATH = "/api/plants/energy/daily/ingest"
LOGIN_PATH = "/api/auth/login"

DEFAULT_TIMEOUT = 600        # seconds, matches the job scripts
DEFAULT_RANGE_DELAY = 10     # seconds between consecutive ranges of the same plant
DEFAULT_PLANT_DELAY = 20     # seconds when moving to a different plant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers (no network, no stdin — unit-tested)
# ---------------------------------------------------------------------------
def find_latest_report(reports_dir, prefix=REPORT_PREFIX):
    """Return the ``Path`` of the newest report under ``reports_dir``.

    Selects by the ``YYYY-MM-DD_HHMMSS`` stamp embedded in the filename (robust
    to filesystem mtime being touched). Returns ``None`` if none match.
    """
    reports_dir = Path(reports_dir)
    if not reports_dir.is_dir():
        return None

    candidates = []
    for path in reports_dir.glob(f"{prefix}*.json"):
        match = REPORT_STAMP_RE.search(path.name)
        if match:
            candidates.append((match.group(1), path))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def load_report(path):
    """Load and return the report JSON from ``path``."""
    with open(path, "r") as fh:
        return json.load(fh)


def collect_gap_ranges(report, plant_id=None, user=None):
    """Flatten a gap report into a list of fillable range dicts.

    Walks ``report["users"] -> plants``. A plant contributes a range for every
    entry in its ``gap_ranges`` unless its status is ``"complete"``. ``no_data``
    plants are included when their ``gap_ranges`` already spans the expected
    window (the checker populates it when a window start is known). Optional
    ``plant_id`` / ``user`` filters restrict the result.

    Each returned dict: ``{user, plant_id, vendor, plant_name, start, end,
    days}``.
    """
    out = []
    for user_entry in report.get("users", []):
        user_name = user_entry.get("user_name")
        if user and user_name != user:
            continue

        for plant in user_entry.get("plants", []):
            if plant.get("status") == "complete":
                continue

            pid = plant.get("plant_id")
            if plant_id and pid != plant_id:
                continue

            for span in plant.get("gap_ranges", []):
                start = span.get("start")
                end = span.get("end")
                if not start or not end:
                    continue
                out.append({
                    "user": user_name,
                    "plant_id": pid,
                    "vendor": plant.get("vendor"),
                    "plant_name": plant.get("plant_name"),
                    "start": start,
                    "end": end,
                    "days": span.get("days"),
                })
    return out


def resolve_base_url(prod=False, base_url=None):
    """Pick the target base URL. ``--base-url`` wins; else prod vs local."""
    if base_url:
        return base_url.rstrip("/")
    return (PROD_BASE_URL if prod else DEFAULT_LOCAL_BASE_URL).rstrip("/")


def parse_ingest_response(payload):
    """Extract status / inserted / updated / message from an ingest response.

    The endpoint returns ``database_summary`` on success, nothing of the kind on
    warning/error. Missing fields default to ``0`` / ``""`` so callers can tally
    without re-checking.
    """
    payload = payload or {}
    summary = payload.get("database_summary") or {}
    return {
        "status": payload.get("status", "unknown"),
        "inserted": summary.get("total_inserted", 0),
        "updated": summary.get("total_updated", 0),
        "message": payload.get("message", ""),
    }


def next_delay(plant_key, prev_plant_key, range_delay, plant_delay):
    """Seconds to wait before the next ingest call (rate-limit spacing).

    Returns ``0`` before the very first call (``prev_plant_key is None``),
    ``range_delay`` when the next call is for the same plant as the previous
    one, and ``plant_delay`` when the plant has changed. Skipped ranges do not
    update ``prev_plant_key``, so spacing tracks actual API calls.
    """
    if prev_plant_key is None:
        return 0
    return range_delay if plant_key == prev_plant_key else plant_delay


# ---------------------------------------------------------------------------
# Network helpers (impure — thin wrappers over requests)
# ---------------------------------------------------------------------------
def login(base_url, username, password, timeout, session):
    """Authenticate and return an access token. Raises on failure."""
    resp = session.post(
        base_url + LOGIN_PATH,
        json={"username": username, "password": password},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"Login succeeded but no access_token in response: {payload}")
    return token


def ingest_range(base_url, token, plant_id, start_date, end_date, timeout, session):
    """Call the daily-energy ingest endpoint for one range.

    Returns ``(status_code, payload_dict)``. Does not raise on HTTP errors — the
    caller inspects ``status_code`` (e.g. 401 → re-login) and the JSON body.
    """
    resp = session.get(
        base_url + INGEST_PATH,
        params={
            "plant_id": plant_id,
            "start_date": start_date,
            "end_date": end_date,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"status": "error", "message": (resp.text or "")[:300]}
    return resp.status_code, payload


# ---------------------------------------------------------------------------
# Interactive prompt (impure — stdin)
# ---------------------------------------------------------------------------
def prompt_confirm():
    """Ask the user whether to proceed with one range.

    Returns one of ``"y"`` (yes), ``"n"`` (skip this range), ``"a"`` (yes to all
    remaining), ``"q"`` (quit immediately).
    """
    while True:
        answer = input("  proceed? [y/n/a/q] ").strip().lower()
        if answer in ("y", "yes"):
            return "y"
        if answer in ("n", "no"):
            return "n"
        if answer in ("a", "all"):
            return "a"
        if answer in ("q", "quit", "exit"):
            return "q"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    target = parser.add_argument_group("target")
    target.add_argument(
        "--prod", action="store_true",
        help=f"Target production ({PROD_BASE_URL}) instead of local "
             f"({DEFAULT_LOCAL_BASE_URL}).",
    )
    target.add_argument(
        "--base-url", default=None,
        help="Explicit base URL. Overrides --prod and the local default.",
    )

    run = parser.add_argument_group("execution")
    run.add_argument(
        "--apply", action="store_true",
        help="Actually ingest (default: dry-run, no network).",
    )
    run.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the per-range prompt (auto-proceed). For unattended runs.",
    )
    run.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default {DEFAULT_TIMEOUT}).",
    )
    run.add_argument(
        "--range-delay", type=float, default=DEFAULT_RANGE_DELAY,
        help=f"Seconds between consecutive ranges of the same plant "
             f"(default {DEFAULT_RANGE_DELAY}).",
    )
    run.add_argument(
        "--plant-delay", type=float, default=DEFAULT_PLANT_DELAY,
        help=f"Seconds to wait when moving to a different plant "
             f"(default {DEFAULT_PLANT_DELAY}).",
    )
    run.add_argument(
        "--username", default=os.getenv("WATCHDOG_ADMIN_USER", "admin"),
        help="Admin username (env WATCHDOG_ADMIN_USER; default 'admin').",
    )
    run.add_argument(
        "--password", default=os.getenv("WATCHDOG_ADMIN_PASS", "admin"),
        help="Admin password (env WATCHDOG_ADMIN_PASS; default 'admin').",
    )

    scope = parser.add_argument_group("scope")
    scope.add_argument(
        "--report", default=None,
        help="Path to a specific report JSON (default: latest in --reports-dir).",
    )
    scope.add_argument(
        "--reports-dir", default=str(REPORTS_DIR),
        help=f"Directory to search for the latest report (default {REPORTS_DIR}).",
    )
    scope.add_argument("--plant-id", default=None, help="Only fill this plant_id.")
    scope.add_argument("--user", default=None, help="Only fill plants owned by this user.")

    return parser.parse_args(argv)


def _print_plan(report, ranges, base_url, apply, range_delay, plant_delay):
    totals = report.get("totals", {})
    mode = "LIVE (--apply)" if apply else "DRY RUN"
    print()
    print(f"Fill plant daily-generation gaps — {mode}")
    print(f"Target: {base_url}")
    print(
        f"Report generated {report.get('generated_at_ist', '?')}, "
        f"expected through {report.get('expected_through_ist', '?')}. "
        f"{totals.get('plants_with_gaps', 0)} plant(s) with gaps, "
        f"{totals.get('total_missing_plant_days', 0)} total missing plant-days."
    )
    print(
        f"Will process {len(ranges)} range(s) across "
        f"{len({(r['user'], r['plant_id'], r['vendor']) for r in ranges})} plant(s)."
    )
    if apply:
        print(f"Spacing: {range_delay}s between ranges, {plant_delay}s between plants.")


def main(argv=None):
    args = parse_args(argv)

    # Locate and load the report.
    report_path = Path(args.report) if args.report else find_latest_report(args.reports_dir)
    if report_path is None or not Path(report_path).is_file():
        logger.error("No report found (looked in %s). Run check_plant_daily_generation_gaps.py first "
                     "or pass --report.", args.reports_dir)
        return 2
    logger.info("Using report: %s", report_path)

    report = load_report(report_path)
    ranges = collect_gap_ranges(
        report, plant_id=args.plant_id, user=args.user,
    )

    base_url = resolve_base_url(prod=args.prod, base_url=args.base_url)
    _print_plan(report, ranges, base_url, args.apply, args.range_delay, args.plant_delay)

    if not ranges:
        print("\nNo gap ranges to fill. Nothing to do.\n")
        return 0

    # Dry-run: print the full plan and exit without any network calls.
    if not args.apply:
        print("\nRanges that would be filled:")
        for r in ranges:
            print(
                f"  - {r['user']} / plant {r['plant_id']} ({r['vendor']}): "
                f"{r['start']} -> {r['end']} ({r['days']} day(s))"
            )
            print(
                f"      GET {base_url}{INGEST_PATH}"
                f"?plant_id={r['plant_id']}&start_date={r['start']}&end_date={r['end']}"
            )
        print("\nDry run complete. Re-run with --apply to fill for real.\n")
        return 0

    # Live mode. Lazy-import requests (not in the local venv).
    import requests  # noqa: WPS433

    session = requests.Session()
    try:
        token = login(base_url, args.username, args.password, args.timeout, session)
        logger.info("Authenticated as %s.", args.username)
    except Exception as exc:
        logger.error("Login failed: %s", exc)
        return 1

    stats = {
        "attempted": 0, "succeeded": 0, "warned": 0,
        "failed": 0, "skipped": 0,
        "inserted": 0, "updated": 0,
    }
    auto_proceed = args.yes
    prev_plant_key = None  # plant key of the last *attempted* range, for spacing

    for r in ranges:
        plant_key = (r["user"], r["plant_id"], r["vendor"])
        label = (f"{r['user']} / plant {r['plant_id']} ({r['vendor']}): "
                 f"{r['start']} -> {r['end']} ({r['days']} day(s))")
        print(f"\n* {label}")

        if not auto_proceed:
            choice = prompt_confirm()
            if choice == "n":
                logger.info("Skipped.")
                stats["skipped"] += 1
                continue
            if choice == "q":
                logger.info("Quit requested; stopping.")
                break
            if choice == "a":
                auto_proceed = True

        # Space out ingest calls to avoid hammering the Growatt API: short gap
        # between ranges of the same plant, longer gap when switching plants.
        # No wait before the very first call.
        delay = next_delay(plant_key, prev_plant_key, args.range_delay, args.plant_delay)
        if delay > 0:
            logger.info("Waiting %ss before next ingest...", delay)
            time.sleep(delay)

        stats["attempted"] += 1
        result = _ingest_with_relogin(
            base_url, token, r, args, session,
            relogin_fn=lambda: login(base_url, args.username, args.password, args.timeout, session),
        )
        # _ingest_with_relogin may return a fresh token via the mutable holder.
        token = result["token"]

        parsed = parse_ingest_response(result["payload"])
        http_ok = 200 <= result["status_code"] < 300

        if http_ok and parsed["status"] == "success":
            stats["succeeded"] += 1
            stats["inserted"] += parsed["inserted"] or 0
            stats["updated"] += parsed["updated"] or 0
            logger.info(
                "OK — inserted=%s updated=%s",
                parsed["inserted"], parsed["updated"],
            )
        elif http_ok and parsed["status"] == "warning":
            stats["warned"] += 1
            logger.warning("No data for this range: %s", parsed["message"])
        else:
            stats["failed"] += 1
            logger.error(
                "Failed (HTTP %s, status=%s): %s",
                result["status_code"], parsed["status"], parsed["message"],
            )

        prev_plant_key = plant_key

    _print_tally(stats)
    return 1 if stats["failed"] else 0


def _ingest_with_relogin(base_url, token, range_entry, args, session, relogin_fn):
    """Call ingest_range once, re-logging in and retrying once on a 401.

    Returns ``{"status_code", "payload", "token"}`` where ``token`` is the token
    used (possibly refreshed) so the caller can reuse it for the next range.
    """
    status_code, payload = ingest_range(
        base_url, token, range_entry["plant_id"],
        range_entry["start"], range_entry["end"], args.timeout, session,
    )

    if status_code == 401:
        logger.warning("Token expired (401); re-authenticating and retrying once.")
        token = relogin_fn()
        status_code, payload = ingest_range(
            base_url, token, range_entry["plant_id"],
            range_entry["start"], range_entry["end"], args.timeout, session,
        )

    return {"status_code": status_code, "payload": payload, "token": token}


def _print_tally(stats):
    print("\nDone.")
    print(
        f"  attempted={stats['attempted']}  succeeded={stats['succeeded']}  "
        f"warned={stats['warned']}  failed={stats['failed']}  skipped={stats['skipped']}"
    )
    print(
        f"  rows inserted={stats['inserted']}  updated={stats['updated']}"
    )
    if stats["failed"]:
        print("  One or more ranges failed; see logs above.")
    print()


if __name__ == "__main__":
    sys.exit(main())
