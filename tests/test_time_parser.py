# tests/test_time_parser.py
"""Tests for Korean time expression parser."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.scheduler.time_parser import format_time_kst, parse_korean_time

KST = ZoneInfo("Asia/Seoul")


class TestParseKoreanTime:
    """Tests for parse_korean_time function."""

    def test_relative_minutes_korean(self):
        """Test Korean relative time: N분 후."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("1분 후", base)

        assert result is not None
        assert result == base + timedelta(minutes=1)

    def test_relative_seconds_korean(self):
        """Test Korean relative time: N초 후."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("30초 후", base)

        assert result is not None
        assert result == base + timedelta(seconds=30)

    def test_relative_hours_korean(self):
        """Test Korean relative time: N시간 후."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("2시간 후", base)

        assert result is not None
        assert result == base + timedelta(hours=2)

    def test_relative_days_korean(self):
        """Test Korean relative time: N일 후."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("3일 후", base)

        assert result is not None
        assert result == base + timedelta(days=3)

    def test_relative_korean_dwi(self):
        """Test Korean relative time with 뒤 variant."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("5분 뒤", base)

        assert result is not None
        assert result == base + timedelta(minutes=5)

    def test_relative_english_in_minutes(self):
        """Test English relative time: in N minutes."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("in 5 minutes", base)

        assert result is not None
        assert result == base + timedelta(minutes=5)

    def test_relative_english_after_seconds(self):
        """Test English relative time: after N seconds."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("after 10 seconds", base)

        assert result is not None
        assert result == base + timedelta(seconds=10)

    def test_relative_english_hours(self):
        """Test English relative time with hours."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("in 2 hours", base)

        assert result is not None
        assert result == base + timedelta(hours=2)

    def test_absolute_korean_pm(self):
        """Test Korean absolute time: 오후 N시."""
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        result = parse_korean_time("오후 3시", base)

        assert result is not None
        assert result.hour == 15
        assert result.minute == 0

    def test_absolute_korean_am(self):
        """Test Korean absolute time: 오전 N시."""
        # Base time in afternoon - should schedule for tomorrow morning
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("오전 10시", base)

        assert result is not None
        assert result.hour == 10
        assert result.day == 16  # Tomorrow

    def test_absolute_korean_with_minutes(self):
        """Test Korean absolute time: 오후 N시 M분."""
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        result = parse_korean_time("오후 3시 30분", base)

        assert result is not None
        assert result.hour == 15
        assert result.minute == 30

    def test_absolute_24hour_format(self):
        """Test 24-hour format: HH:MM."""
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        result = parse_korean_time("15:00", base)

        assert result is not None
        assert result.hour == 15
        assert result.minute == 0

    def test_absolute_24hour_with_seconds(self):
        """Test 24-hour format with seconds: HH:MM:SS."""
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        result = parse_korean_time("15:30:45", base)

        assert result is not None
        assert result.hour == 15
        assert result.minute == 30
        assert result.second == 45

    def test_absolute_korean_24hour(self):
        """Test Korean 24-hour format: N시 M분."""
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        result = parse_korean_time("15시 30분", base)

        assert result is not None
        assert result.hour == 15
        assert result.minute == 30

    def test_tomorrow_korean(self):
        """Test Korean tomorrow: 내일 + time."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("내일 오전 10시", base)

        assert result is not None
        assert result.day == 16
        assert result.hour == 10

    def test_tomorrow_english(self):
        """Test English tomorrow + time."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("tomorrow 15:00", base)

        assert result is not None
        assert result.day == 16
        assert result.hour == 15

    def test_today_korean(self):
        """Test Korean today: 오늘 + time."""
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        result = parse_korean_time("오늘 15시", base)

        assert result is not None
        assert result.day == 15
        assert result.hour == 15

    def test_past_time_schedules_tomorrow(self):
        """Test that past times schedule for tomorrow."""
        base = datetime(2024, 1, 15, 16, 0, 0, tzinfo=KST)  # 4 PM
        result = parse_korean_time("오후 3시", base)  # 3 PM (past)

        assert result is not None
        assert result.day == 16  # Tomorrow
        assert result.hour == 15

    def test_invalid_time_expression(self):
        """Test invalid time expressions return None."""
        result = parse_korean_time("invalid time")
        assert result is None

    def test_empty_string(self):
        """Test empty string returns None."""
        result = parse_korean_time("")
        assert result is None

    def test_none_base_time_uses_now(self):
        """Test that None base_time defaults to now."""
        result = parse_korean_time("1분 후")

        assert result is not None
        # Should be approximately 1 minute from now
        now = datetime.now(KST)
        diff = (result - now).total_seconds()
        assert 55 <= diff <= 65  # Allow some tolerance

    def test_simple_number_unit(self):
        """Test simple number + unit format (e.g., '5분')."""
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST)
        result = parse_korean_time("5분", base)

        assert result is not None
        assert result == base + timedelta(minutes=5)


class TestFormatTimeKst:
    """Tests for format_time_kst function."""

    def test_format_morning(self):
        """Test formatting morning time."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=KST)
        result = format_time_kst(dt)

        assert "2024-01-15" in result
        assert "오전" in result
        assert "10:30" in result
        assert "KST" in result

    def test_format_afternoon(self):
        """Test formatting afternoon time."""
        dt = datetime(2024, 1, 15, 15, 45, 0, tzinfo=KST)
        result = format_time_kst(dt)

        assert "2024-01-15" in result
        assert "오후" in result
        assert "3:45" in result
        assert "KST" in result

    def test_format_noon(self):
        """Test formatting noon."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=KST)
        result = format_time_kst(dt)

        assert "오후" in result
        assert "12:00" in result

    def test_format_midnight(self):
        """Test formatting midnight."""
        dt = datetime(2024, 1, 15, 0, 0, 0, tzinfo=KST)
        result = format_time_kst(dt)

        assert "오전" in result
        assert "12:00" in result

    def test_format_naive_datetime(self):
        """Test formatting naive datetime (assumes KST)."""
        dt = datetime(2024, 1, 15, 14, 30, 0)  # No timezone
        result = format_time_kst(dt)

        assert "2024-01-15" in result
        assert "오후" in result
        assert "2:30" in result
