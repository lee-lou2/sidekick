# src/scheduler/time_parser.py
"""Korean time expression parser.

Parses Korean and English time expressions into datetime objects.
All times are in KST (Asia/Seoul) timezone.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# Time unit mappings (Korean -> seconds multiplier)
TIME_UNITS = {
    # Korean
    "초": 1,
    "분": 60,
    "시간": 3600,
    "일": 86400,
    "주": 604800,
    # English
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "s": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "m": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
    "h": 3600,
    "day": 86400,
    "days": 86400,
    "d": 86400,
    "week": 604800,
    "weeks": 604800,
    "w": 604800,
}

# Relative time patterns
RELATIVE_PATTERNS = [
    # Korean: "1분 후", "30초 뒤", "2시간 후에"
    r"(\d+)\s*(초|분|시간|일|주)\s*(후|뒤|후에|뒤에)",
    # English: "in 5 minutes", "after 1 hour"
    r"in\s+(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)",
    r"after\s+(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)",
    # Simple: "5분", "10초" (assume "후")
    r"^(\d+)\s*(초|분|시간|일|주)$",
]

# Absolute time patterns
ABSOLUTE_PATTERNS = [
    # Korean: "오후 3시", "오전 10시 30분"
    r"(오전|오후)\s*(\d{1,2})시(?:\s*(\d{1,2})분)?",
    # 24-hour: "15:00", "14:30"
    r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
    # Korean 24-hour: "15시", "14시 30분"
    r"(\d{1,2})시(?:\s*(\d{1,2})분)?",
]

# Day offset patterns
DAY_PATTERNS = {
    "오늘": 0,
    "today": 0,
    "내일": 1,
    "tomorrow": 1,
    "모레": 2,
    "내일모레": 2,
    "day after tomorrow": 2,
}


def _normalize_unit(unit: str) -> str:
    """Normalize time unit to lowercase for lookup.

    Args:
        unit: Time unit string.

    Returns:
        Normalized unit string.
    """
    return unit.lower().strip()


def _parse_relative_time(text: str, base_time: datetime) -> datetime | None:
    """Parse relative time expressions.

    Args:
        text: Text containing relative time expression.
        base_time: Base time to calculate from.

    Returns:
        Calculated datetime or None if not matched.
    """
    text_lower = text.lower().strip()

    for pattern in RELATIVE_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            groups = match.groups()
            amount = int(groups[0])
            unit = _normalize_unit(groups[1])

            # Find multiplier
            multiplier = TIME_UNITS.get(unit)
            if multiplier is None:
                continue

            seconds = amount * multiplier
            return base_time + timedelta(seconds=seconds)

    return None


def _parse_absolute_time(text: str, base_time: datetime) -> datetime | None:
    """Parse absolute time expressions.

    Args:
        text: Text containing absolute time expression.
        base_time: Base time for date reference.

    Returns:
        Calculated datetime or None if not matched.
    """
    text_lower = text.strip()

    # Check for day offset first
    day_offset = 0
    for day_word, offset in DAY_PATTERNS.items():
        if day_word in text_lower:
            day_offset = offset
            break

    # Try Korean AM/PM format: "오후 3시 30분"
    match = re.search(r"(오전|오후)\s*(\d{1,2})시(?:\s*(\d{1,2})분)?", text_lower)
    if match:
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3)) if match.group(3) else 0

        # Convert to 24-hour format
        if period == "오후" and hour < 12:
            hour += 12
        elif period == "오전" and hour == 12:
            hour = 0

        target = base_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        target += timedelta(days=day_offset)

        # If time has passed today and no day offset, schedule for tomorrow
        if day_offset == 0 and target <= base_time:
            target += timedelta(days=1)

        return target

    # Try 24-hour format: "15:00" or "14:30:00"
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text_lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3)) if match.group(3) else 0

        if 0 <= hour < 24 and 0 <= minute < 60:
            target = base_time.replace(
                hour=hour, minute=minute, second=second, microsecond=0
            )
            target += timedelta(days=day_offset)

            if day_offset == 0 and target <= base_time:
                target += timedelta(days=1)

            return target

    # Try Korean 24-hour format: "15시 30분"
    match = re.search(r"(\d{1,2})시(?:\s*(\d{1,2})분)?", text_lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0

        if 0 <= hour < 24 and 0 <= minute < 60:
            target = base_time.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            target += timedelta(days=day_offset)

            if day_offset == 0 and target <= base_time:
                target += timedelta(days=1)

            return target

    return None


def parse_korean_time(text: str, base_time: datetime | None = None) -> datetime | None:
    """Parse Korean/English time expression to datetime.

    Supports:
    - Relative: "1분 후", "30초 뒤", "2시간 후", "in 5 minutes", "after 1 hour"
    - Absolute: "오후 3시", "15:00", "14시 30분"
    - With day: "내일 오전 10시", "tomorrow 15:00"

    Args:
        text: Time expression text.
        base_time: Base time for calculations. Defaults to now (KST).

    Returns:
        Parsed datetime (KST) or None if parsing failed.

    Examples:
        >>> parse_korean_time("1분 후")  # 1 minute later
        >>> parse_korean_time("오후 3시")  # 3 PM today (or tomorrow if passed)
        >>> parse_korean_time("내일 오전 10시")  # Tomorrow 10 AM
        >>> parse_korean_time("in 30 seconds")  # 30 seconds later
    """
    if not text or not text.strip():
        return None

    if base_time is None:
        base_time = datetime.now(KST)
    elif base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=KST)

    # Try relative time first (more common for scheduling)
    result = _parse_relative_time(text, base_time)
    if result:
        return result

    # Try absolute time
    result = _parse_absolute_time(text, base_time)
    if result:
        return result

    return None


def format_time_kst(dt: datetime) -> str:
    """Format datetime as KST string.

    Args:
        dt: Datetime to format.

    Returns:
        Formatted string like "2024-01-15 오후 3:30 KST".
    """
    dt = dt.replace(tzinfo=KST) if dt.tzinfo is None else dt.astimezone(KST)

    hour = dt.hour
    period = "오전" if hour < 12 else "오후"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12

    return f"{dt.strftime('%Y-%m-%d')} {period} {display_hour}:{dt.strftime('%M')} KST"
