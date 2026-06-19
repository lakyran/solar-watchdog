"""Unit tests for the pure helpers in fill_plant_daily_generation_gaps.

Covers report discovery, report flattening, URL resolution and response parsing
only — no network and no stdin. The login / ingest / prompt code is impure and
intentionally not covered here.
"""
import json

from fill_plant_daily_generation_gaps import (
    collect_gap_ranges,
    find_latest_report,
    load_report,
    next_delay,
    parse_ingest_response,
    resolve_base_url,
)

PREFIX = "plant-daily-generation-gap-report-"


def _report(users):
    """Minimal report skeleton wrapping a ``users`` list."""
    return {"users": users, "totals": {}, "generated_at_ist": "x", "expected_through_ist": "y"}


def _plant(plant_id, status, gap_ranges, vendor="unisolarpower", plant_name="p"):
    return {
        "plant_id": plant_id, "vendor": vendor, "plant_name": plant_name,
        "status": status, "gap_ranges": gap_ranges,
    }


# ---------------------------------------------------------------------------
# find_latest_report
# ---------------------------------------------------------------------------
class TestFindLatestReport:
    def test_picks_newest_stamp(self, tmp_path):
        (tmp_path / f"{PREFIX}2026-06-19_080000.json").write_text("{}")
        latest = tmp_path / f"{PREFIX}2026-06-19_115153.json"
        latest.write_text("{}")
        (tmp_path / f"{PREFIX}2025-01-01_000000.json").write_text("{}")
        assert find_latest_report(tmp_path, PREFIX) == latest

    def test_returns_none_when_dir_missing(self, tmp_path):
        assert find_latest_report(tmp_path / "nope", PREFIX) is None

    def test_returns_none_when_no_matches(self, tmp_path):
        (tmp_path / "unrelated-2026-06-19_000000.json").write_text("{}")
        (tmp_path / f"{PREFIX}bad-stamp.json").write_text("{}")
        assert find_latest_report(tmp_path, PREFIX) is None

    def test_ignores_non_json_and_bad_stamps(self, tmp_path):
        good = tmp_path / f"{PREFIX}2026-06-19_120000.json"
        good.write_text("{}")
        (tmp_path / f"{PREFIX}2026-06-19_120000.txt").write_text("{}")  # wrong ext
        (tmp_path / f"{PREFIX}not-a-stamp.json").write_text("{}")       # bad stamp
        assert find_latest_report(tmp_path, PREFIX) == good


# ---------------------------------------------------------------------------
# load_report
# ---------------------------------------------------------------------------
class TestLoadReport:
    def test_loads_json(self, tmp_path):
        path = tmp_path / "r.json"
        path.write_text(json.dumps({"users": []}))
        assert load_report(path) == {"users": []}


# ---------------------------------------------------------------------------
# collect_gap_ranges
# ---------------------------------------------------------------------------
class TestCollectGapRanges:
    def test_flattens_gap_ranges_across_users_and_plants(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "gaps", [
                    {"start": "2026-01-01", "end": "2026-01-03", "days": 3},
                    {"start": "2026-02-10", "end": "2026-02-10", "days": 1},
                ]),
            ]},
            {"user_name": "bob", "plants": [
                _plant("2", "gaps", [
                    {"start": "2026-03-01", "end": "2026-03-05", "days": 5},
                ]),
            ]},
        ])
        ranges = collect_gap_ranges(report)
        assert [(r["user"], r["plant_id"], r["start"], r["end"]) for r in ranges] == [
            ("alice", "1", "2026-01-01", "2026-01-03"),
            ("alice", "1", "2026-02-10", "2026-02-10"),
            ("bob", "2", "2026-03-01", "2026-03-05"),
        ]

    def test_carries_metadata(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}],
                       vendor="growatt", plant_name="Roof"),
            ]},
        ])
        r = collect_gap_ranges(report)[0]
        assert r["vendor"] == "growatt"
        assert r["plant_name"] == "Roof"
        assert r["days"] == 2

    def test_skips_complete_plants(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "complete", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}]),
                _plant("2", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}]),
            ]},
        ])
        assert [r["plant_id"] for r in collect_gap_ranges(report)] == ["2"]

    def test_includes_no_data_plants_with_window(self):
        # no_data plants already carry gap_ranges spanning the expected window.
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "no_data", [{"start": "2025-04-01", "end": "2025-04-10", "days": 10}]),
            ]},
        ])
        assert len(collect_gap_ranges(report)) == 1

    def test_skips_ranges_missing_start_or_end(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "gaps", [
                    {"start": None, "end": "2026-01-02", "days": 2},
                    {"start": "2026-01-03", "end": "2026-01-04", "days": 2},
                    {"start": "2026-01-05", "end": None, "days": 1},
                ]),
            ]},
        ])
        assert [(r["start"], r["end"]) for r in collect_gap_ranges(report)] == [
            ("2026-01-03", "2026-01-04"),
        ]

    def test_filter_by_plant_id(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}]),
                _plant("2", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}]),
            ]},
        ])
        assert [r["plant_id"] for r in collect_gap_ranges(report, plant_id="2")] == ["2"]

    def test_filter_by_user(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}]),
            ]},
            {"user_name": "bob", "plants": [
                _plant("2", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}]),
            ]},
        ])
        assert [r["user"] for r in collect_gap_ranges(report, user="bob")] == ["bob"]

    def test_same_plant_id_different_vendors_both_filled(self):
        report = _report([
            {"user_name": "alice", "plants": [
                _plant("1", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}], vendor="growatt"),
                _plant("1", "gaps", [{"start": "2026-01-01", "end": "2026-01-02", "days": 2}], vendor="solis"),
            ]},
        ])
        ranges = collect_gap_ranges(report)
        assert sorted(r["vendor"] for r in ranges) == ["growatt", "solis"]

    def test_empty_report(self):
        assert collect_gap_ranges(_report([])) == []
        assert collect_gap_ranges({}) == []


# ---------------------------------------------------------------------------
# resolve_base_url
# ---------------------------------------------------------------------------
class TestResolveBaseUrl:
    def test_local_default(self):
        assert resolve_base_url() == "http://localhost:5001"

    def test_prod_flag(self):
        assert resolve_base_url(prod=True) == \
            "https://unisolartech-watchdog-databox-bgdqfzedhnd5ecbt.centralindia-01.azurewebsites.net"

    def test_base_url_overrides_prod(self):
        assert resolve_base_url(prod=True, base_url="http://example.com") == "http://example.com"

    def test_trailing_slash_stripped(self):
        assert resolve_base_url(base_url="http://example.com/") == "http://example.com"


# ---------------------------------------------------------------------------
# parse_ingest_response
# ---------------------------------------------------------------------------
class TestParseIngestResponse:
    def test_success_extracts_counts(self):
        payload = {
            "status": "success",
            "database_summary": {"total_inserted": 12, "total_updated": 3, "total_processed": 15},
            "message": "ok",
        }
        parsed = parse_ingest_response(payload)
        assert parsed == {"status": "success", "inserted": 12, "updated": 3, "message": "ok"}

    def test_warning_has_zero_counts(self):
        payload = {"status": "warning", "message": "No generation data found"}
        parsed = parse_ingest_response(payload)
        assert parsed["status"] == "warning"
        assert parsed["inserted"] == 0
        assert parsed["updated"] == 0

    def test_error_without_summary(self):
        parsed = parse_ingest_response({"status": "error", "message": "boom"})
        assert parsed["status"] == "error"
        assert parsed["inserted"] == 0

    def test_none_payload(self):
        parsed = parse_ingest_response(None)
        assert parsed["status"] == "unknown"
        assert parsed["inserted"] == 0
        assert parsed["message"] == ""

    def test_missing_database_summary_key(self):
        parsed = parse_ingest_response({"status": "success"})
        assert parsed["inserted"] == 0 and parsed["updated"] == 0


# ---------------------------------------------------------------------------
# next_delay — rate-limit spacing between ingest calls
# ---------------------------------------------------------------------------
class TestNextDelay:
    RD = 10  # range delay
    PD = 20  # plant delay

    def test_no_wait_before_first_call(self):
        assert next_delay(("u", "1", "v"), None, self.RD, self.PD) == 0

    def test_same_plant_uses_range_delay(self):
        assert next_delay(("u", "1", "v"), ("u", "1", "v"), self.RD, self.PD) == self.RD

    def test_different_plant_uses_plant_delay(self):
        assert next_delay(("u", "2", "v"), ("u", "1", "v"), self.RD, self.PD) == self.PD

    def test_same_plant_id_different_vendor_is_different_plant(self):
        # A plant is (plant_id, vendor); changing vendor counts as switching plants.
        assert next_delay(("u", "1", "solis"), ("u", "1", "growatt"), self.RD, self.PD) == self.PD

    def test_different_user_same_plant_id_is_different_plant(self):
        assert next_delay(("bob", "1", "v"), ("alice", "1", "v"), self.RD, self.PD) == self.PD
