"""Constants for SSD IMS integration."""

from datetime import datetime, timedelta
from typing import Final, Tuple

# Domain
DOMAIN: Final = "ssd_ims"
NAME: Final = "SSD IMS"

# Configuration
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_POINT_OF_DELIVERY: Final = (
    "point_of_delivery"  # Now contains stable pod_ids instead of pod_texts
)
CONF_POD_NAME_MAPPING: Final = "pod_name_mapping"
CONF_ENABLE_SUPPLY_SENSORS: Final = "enable_supply_sensors"
CONF_ENABLE_HISTORY_IMPORT: Final = "enable_history_import"
CONF_HISTORY_DAYS: Final = "history_days"
CONF_HISTORY_IMPORT_DONE: Final = "history_import_done"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 360  # 6 hours - sensible for daily data
DEFAULT_POINT_OF_DELIVERY: Final = []
DEFAULT_ENABLE_SUPPLY_SENSORS: Final = True
DEFAULT_ENABLE_HISTORY_IMPORT: Final = True  # Enable by default
DEFAULT_HISTORY_DAYS: Final = 30  # Import last 30 days of past data by default

# Options - Data is only available up to yesterday and released once per day
# So polling frequently doesn't make sense
SCAN_INTERVAL_OPTIONS: Final = {
    5: "5 minutes (debugging only)",
    360: "6 hours (recommended)",
    720: "12 hours",
    1440: "24 hours",
}

# API delay configuration - random between min and max
API_DELAY_MIN: Final = 1  # minimum random delay in seconds
API_DELAY_MAX: Final = 3  # maximum random delay in seconds

# API endpoints
API_BASE_URL: Final = "https://ims.ssd.sk/api"
API_LOGIN: Final = f"{API_BASE_URL}/account/login"
API_PODS: Final = (
    f"{API_BASE_URL}/consumption-production/profile-data/get-points-of-delivery"
)
API_DATA: Final = f"{API_BASE_URL}/consumption-production/profile-data"
API_CHART: Final = f"{API_BASE_URL}/consumption-production/profile-data/chart-data"

# Sensor types
SENSOR_TYPE_ACTUAL_CONSUMPTION: Final = "actual_consumption"
SENSOR_TYPE_ACTUAL_SUPPLY: Final = "actual_supply"

SENSOR_TYPES: Final = [
    SENSOR_TYPE_ACTUAL_CONSUMPTION,
    SENSOR_TYPE_ACTUAL_SUPPLY,
]


# Date range calculation callbacks
def _calculate_yesterday_range(now: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate date range for yesterday (previous day).

    The API expects:
    - validFromDate: midnight of the requested day in local timezone (e.g., 2025-11-28T00:00:00+01:00)
    - validToDate: 23:00 UTC of the same day (e.g., 2025-11-28T23:00:00Z), which equals midnight local time
    """
    # Get today at midnight in local timezone
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Yesterday at midnight in local timezone (start of the day we want)
    period_start = today_midnight - timedelta(days=1)

    # End time: today's midnight converted to UTC
    # In +01:00 timezone, 2025-11-29T00:00:00+01:00 = 2025-11-28T23:00:00Z
    from datetime import timezone

    period_end = today_midnight.astimezone(timezone.utc)

    return period_start, period_end


# Time periods configuration
PERIOD_YESTERDAY: Final = "yesterday"

# POD naming validation
POD_NAME_MAX_LENGTH: Final = 50
POD_NAME_PATTERN: Final = r"^[a-zA-Z0-9_]+$"  # alphanumeric + underscores only
