"""Constants for SSD IMS integration."""

from datetime import timedelta
from typing import Final

# Domain
DOMAIN: Final = "ssd_ims"
NAME: Final = "SSD IMS"

# Configuration
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_POINT_OF_DELIVERY: Final = (
    "point_of_delivery"  # Now contains stable pod_ids instead of pod_texts
)
CONF_POD_NAME_MAPPING: Final = "pod_name_mapping"
CONF_ENABLE_HISTORY_IMPORT: Final = "enable_history_import"
CONF_HISTORY_DAYS: Final = "history_days"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 360  # 6 hours - sensible for daily data
DEFAULT_POINT_OF_DELIVERY: Final[tuple[str, ...]] = ()
DEFAULT_ENABLE_HISTORY_IMPORT: Final = True  # Enable by default
DEFAULT_HISTORY_DAYS: Final = 7  # Import last 7 days of past data by default

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

# POD cache TTL - the coordinator seeds this cache right after discovery
# (see SsdImsApiClient.set_cached_pods), so this mainly bounds how long a
# long-running statistics backfill can go before PODs are re-discovered.
PODS_CACHE_TTL: Final = timedelta(minutes=60)

# API endpoints
API_BASE_URL: Final = "https://ims.ssd.sk/api"
API_LOGIN: Final = f"{API_BASE_URL}/account/login"
API_PODS: Final = (
    f"{API_BASE_URL}/consumption-production/profile-data/get-points-of-delivery"
)
API_CHART: Final = f"{API_BASE_URL}/consumption-production/profile-data/chart-data"

# Sensor types
SENSOR_TYPE_ACTUAL_CONSUMPTION: Final = "actual_consumption"
SENSOR_TYPE_ACTUAL_SUPPLY: Final = "actual_supply"

SENSOR_TYPES: Final = [
    SENSOR_TYPE_ACTUAL_CONSUMPTION,
    SENSOR_TYPE_ACTUAL_SUPPLY,
]

SENSOR_TYPE_LABELS: Final = {
    SENSOR_TYPE_ACTUAL_CONSUMPTION: "Actual Consumption",
    SENSOR_TYPE_ACTUAL_SUPPLY: "Actual Supply",
}

# POD naming validation
POD_NAME_MAX_LENGTH: Final = 50
