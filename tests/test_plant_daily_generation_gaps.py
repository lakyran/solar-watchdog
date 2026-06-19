"""Unit tests for the plant-specific helpers in check_plant_daily_generation_gaps.

These cover the new (plant_id, vendor) grouping logic only — no database
access. The shared gap algorithm itself (analyze_plant / compute_gap_ranges)
is already exhaustively covered by tests/test_power_gen_history_gaps.py; here
we assert the plant module re-exports it and spot-check plant semantics, so we
don't duplicate that coverage.
"""
from datetime import date

from check_plant_daily_generation_gaps import (
    _group_present_by_plant,
    analyze_plant,
    compute_gap_ranges,
)

TODAY = date(2026, 6, 18)


# ---------------------------------------------------------------------------
# _group_present_by_plant — the only genuinely new pure logic
# ---------------------------------------------------------------------------
class TestGroupPresentByPlant:
    def test_single_plant_single_day(self):
        rows = [("plant_a", "growatt", date(2026, 6, 10))]
        assert _group_present_by_plant(rows) == {
            ("plant_a", "growatt"): {date(2026, 6, 10)}
        }

    def test_multiple_days_for_one_plant(self):
        rows = [
            ("plant_a", "growatt", date(2026, 6, 10)),
            ("plant_a", "growatt", date(2026, 6, 11)),
            ("plant_a", "growatt", date(2026, 6, 13)),
        ]
        assert _group_present_by_plant(rows) == {
            ("plant_a", "growatt"): {
                date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 13)
            }
        }

    def test_same_plant_id_different_vendors_are_separate(self):
        # A plant is (plant_id, vendor); same plant_id across vendors must
        # NOT be merged — this is the whole reason the key is a tuple.
        rows = [
            ("plant_a", "growatt", date(2026, 6, 10)),
            ("plant_a", "solis", date(2026, 6, 11)),
        ]
        assert _group_present_by_plant(rows) == {
            ("plant_a", "growatt"): {date(2026, 6, 10)},
            ("plant_a", "solis"): {date(2026, 6, 11)},
        }

    def test_duplicate_rows_are_deduped(self):
        rows = [
            ("plant_a", "growatt", date(2026, 6, 10)),
            ("plant_a", "growatt", date(2026, 6, 10)),
        ]
        assert _group_present_by_plant(rows) == {
            ("plant_a", "growatt"): {date(2026, 6, 10)}
        }

    def test_empty_rows_returns_empty_map(self):
        assert _group_present_by_plant([]) == {}


# ---------------------------------------------------------------------------
# analyze_plant / compute_gap_ranges — re-exported shared algorithm
# Spot-check that the plant module surfaces the algorithm with plant semantics.
# ---------------------------------------------------------------------------
class TestAnalyzePlantReexport:
    def test_complete_window_no_gaps(self):
        present = {date(2026, 6, d) for d in range(10, 19)}
        r = analyze_plant(present, TODAY)
        assert r["status"] == "complete"
        assert r["missing_days"] == 0
        assert r["missing_today"] is False

    def test_trailing_gap_including_today(self):
        # last data 06-16; 06-17 and 06-18 (today) missing
        present = {date(2026, 6, d) for d in range(10, 17)}
        r = analyze_plant(present, TODAY)
        assert r["status"] == "gaps"
        assert r["missing_days"] == 2
        assert r["gap_ranges"] == [
            {"start": date(2026, 6, 17), "end": TODAY, "days": 2}
        ]
        assert r["missing_today"] is True

    def test_compute_gap_ranges_is_the_shared_helper(self):
        assert compute_gap_ranges([date(2026, 6, 10), date(2026, 6, 13)]) == [
            {"start": date(2026, 6, 10), "end": date(2026, 6, 10), "days": 1},
            {"start": date(2026, 6, 13), "end": date(2026, 6, 13), "days": 1},
        ]
