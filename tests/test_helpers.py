"""Tests for pure helper functions: date-range math and name sanitization."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from custom_components.ssd_ims.helpers import calculate_yesterday_range, sanitize_name


class TestCalculateYesterdayRange:
    """calculate_yesterday_range must always return UTC-aware boundaries —
    a past bug (CHANGELOG v2.0.5) returned a naive local datetime for the
    start of the range."""

    def test_utc_input_returns_utc_aware_bounds_one_day_apart(self):
        now = datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)

        start, end = calculate_yesterday_range(now)

        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc
        assert start == datetime(2026, 6, 14, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc)
        assert end - start == timedelta(days=1)

    def test_start_is_tz_aware_not_naive(self):
        now = datetime(2026, 6, 15, 14, 30, tzinfo=ZoneInfo("Europe/Bratislava"))

        start, end = calculate_yesterday_range(now)

        assert start.tzinfo is not None
        assert end.tzinfo is not None

    def test_local_midnight_boundaries_convert_correctly_in_winter(self):
        """Local midnight in winter (CET, UTC+1) must convert to 23:00 UTC
        the prior day, not be off by an hour."""
        now = datetime(2026, 1, 15, 10, 0, tzinfo=ZoneInfo("Europe/Bratislava"))

        start, end = calculate_yesterday_range(now)

        assert start == datetime(2026, 1, 13, 23, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)

    def test_local_midnight_boundaries_convert_correctly_in_summer_dst(self):
        """Local midnight in summer (CEST, UTC+2) must convert to 22:00 UTC
        the prior day."""
        now = datetime(2026, 7, 15, 10, 0, tzinfo=ZoneInfo("Europe/Bratislava"))

        start, end = calculate_yesterday_range(now)

        assert start == datetime(2026, 7, 13, 22, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)


class TestSanitizeName:
    def test_replaces_special_characters_with_underscore(self):
        assert sanitize_name("Home (Rodinný dom)") == "home_rodinn_dom"

    def test_collapses_consecutive_replacements_and_strips_edges(self):
        assert sanitize_name("  multiple   spaces  ") == "multiple_spaces"

    def test_lower_false_preserves_case(self):
        assert sanitize_name("Home Address", lower=False) == "Home_Address"

    def test_already_valid_identifier_is_unchanged(self):
        assert sanitize_name("pod_1") == "pod_1"

    def test_only_invalid_characters_sanitizes_to_empty_string(self):
        assert sanitize_name("!!!") == ""
