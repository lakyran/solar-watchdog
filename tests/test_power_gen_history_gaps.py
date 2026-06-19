"""Unit tests for the pure gap-detection logic in check_power_gen_history_gaps.

These cover the algorithm only — no database access. The DB/IO layer
(`main`) is exercised by running the script against a live database.
"""
from datetime import date, datetime

import pytest

from check_power_gen_history_gaps import analyze_device, compute_gap_ranges, report_file_stamp

TODAY = date(2026, 6, 18)


# ---------------------------------------------------------------------------
# compute_gap_ranges
# ---------------------------------------------------------------------------
class TestComputeGapRanges:
    def test_empty_input_returns_empty(self):
        assert compute_gap_ranges([]) == []

    def test_single_date_is_one_day_range(self):
        result = compute_gap_ranges([date(2026, 6, 12)])
        assert result == [{"start": date(2026, 6, 12), "end": date(2026, 6, 12), "days": 1}]

    def test_consecutive_run_is_single_range(self):
        result = compute_gap_ranges([date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)])
        assert result == [{"start": date(2026, 6, 10), "end": date(2026, 6, 12), "days": 3}]

    def test_two_separate_runs_become_two_ranges(self):
        result = compute_gap_ranges([date(2026, 6, 10), date(2026, 6, 11),
                                     date(2026, 6, 13), date(2026, 6, 14)])
        assert result == [
            {"start": date(2026, 6, 10), "end": date(2026, 6, 11), "days": 2},
            {"start": date(2026, 6, 13), "end": date(2026, 6, 14), "days": 2},
        ]

    def test_unsorted_input_is_sorted(self):
        result = compute_gap_ranges([date(2026, 6, 14), date(2026, 6, 10), date(2026, 6, 11)])
        assert result == [{"start": date(2026, 6, 10), "end": date(2026, 6, 11), "days": 2},
                          {"start": date(2026, 6, 14), "end": date(2026, 6, 14), "days": 1}]

    def test_run_then_isolated_day(self):
        # 10,11,12 consecutive, then a gap, then isolated 15
        result = compute_gap_ranges([date(2026, 6, 10), date(2026, 6, 11),
                                     date(2026, 6, 12), date(2026, 6, 15)])
        assert result == [
            {"start": date(2026, 6, 10), "end": date(2026, 6, 12), "days": 3},
            {"start": date(2026, 6, 15), "end": date(2026, 6, 15), "days": 1},
        ]


# ---------------------------------------------------------------------------
# analyze_device
# ---------------------------------------------------------------------------
class TestAnalyzeDevice:
    def test_complete_window_no_gaps(self):
        # data present every day from 06-10 through today (06-18)
        present = {date(2026, 6, d) for d in range(10, 19)}
        r = analyze_device(present, TODAY)
        assert r["status"] == "complete"
        assert r["first_record_date"] == date(2026, 6, 10)
        assert r["last_record_date"] == date(2026, 6, 18)
        assert r["expected_window"] == {"start": date(2026, 6, 10), "end": date(2026, 6, 18)}
        assert r["expected_days"] == 9
        assert r["present_days"] == 9
        assert r["missing_days"] == 0
        assert r["gap_ranges"] == []
        assert r["missing_today"] is False

    def test_internal_single_day_gap(self):
        # present 06-10, 06-11, skip 06-12, then 06-13..06-18
        present = {date(2026, 6, 10), date(2026, 6, 11)} | {date(2026, 6, d) for d in range(13, 19)}
        r = analyze_device(present, TODAY)
        assert r["status"] == "gaps"
        assert r["missing_days"] == 1
        assert r["gap_ranges"] == [{"start": date(2026, 6, 12), "end": date(2026, 6, 12), "days": 1}]
        assert r["missing_today"] is False  # today (06-18) is present

    def test_trailing_gap_to_today(self):
        # last data 06-16; 06-17 and 06-18 (today) missing
        present = {date(2026, 6, d) for d in range(10, 17)}
        r = analyze_device(present, TODAY)
        assert r["status"] == "gaps"
        assert r["missing_days"] == 2
        assert r["gap_ranges"] == [{"start": date(2026, 6, 17), "end": date(2026, 6, 18), "days": 2}]
        assert r["missing_today"] is True

    def test_two_gap_ranges(self):
        # present only on 06-10, 06-13, 06-18
        present = {date(2026, 6, 10), date(2026, 6, 13), date(2026, 6, 18)}
        r = analyze_device(present, TODAY)
        assert r["status"] == "gaps"
        assert r["first_record_date"] == date(2026, 6, 10)
        assert r["expected_days"] == 9
        assert r["present_days"] == 3
        assert r["missing_days"] == 6
        assert r["gap_ranges"] == [
            {"start": date(2026, 6, 11), "end": date(2026, 6, 12), "days": 2},
            {"start": date(2026, 6, 14), "end": date(2026, 6, 17), "days": 4},
        ]

    def test_single_day_present_equals_today(self):
        r = analyze_device({TODAY}, TODAY)
        assert r["status"] == "complete"
        assert r["first_record_date"] == TODAY
        assert r["last_record_date"] == TODAY
        assert r["expected_days"] == 1
        assert r["missing_days"] == 0

    def test_no_data_with_start_flags_entire_window(self):
        r = analyze_device(set(), TODAY, no_data_start=date(2026, 6, 10))
        assert r["status"] == "no_data"
        assert r["first_record_date"] is None
        assert r["last_record_date"] is None
        assert r["expected_window"] == {"start": date(2026, 6, 10), "end": TODAY}
        assert r["expected_days"] == 9
        assert r["present_days"] == 0
        assert r["missing_days"] == 9
        assert r["gap_ranges"] == [{"start": date(2026, 6, 10), "end": TODAY, "days": 9}]
        assert r["missing_today"] is True

    def test_no_data_without_start_is_unknown_window(self):
        r = analyze_device(set(), TODAY)
        assert r["status"] == "no_data"
        assert r["expected_window"]["start"] is None
        assert r["expected_days"] == 0
        assert r["missing_days"] == 0
        assert r["gap_ranges"] == []
        assert r["missing_today"] is False


class TestReportFileStamp:
    def test_format_is_full_timestamp_without_colons(self):
        # Filesystem-safe: no colons; date + time so each run is unique.
        dt = datetime(2026, 6, 18, 16, 14, 30)
        assert report_file_stamp(dt) == "2026-06-18_161430"

    def test_different_seconds_yield_different_stamps(self):
        a = report_file_stamp(datetime(2026, 6, 18, 16, 14, 30))
        b = report_file_stamp(datetime(2026, 6, 18, 16, 14, 31))
        assert a != b
