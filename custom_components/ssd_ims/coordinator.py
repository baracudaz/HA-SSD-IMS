"""Data coordinator for SSD IMS integration."""

import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    StatisticMeanType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api_client import SsdImsApiClient
from .const import (
    API_DELAY_MAX,
    API_DELAY_MIN,
    CONF_HISTORY_DAYS,
    CONF_POINT_OF_DELIVERY,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PERIOD_YESTERDAY,
    SENSOR_TYPE_ACTUAL_CONSUMPTION,
    SENSOR_TYPE_ACTUAL_SUPPLY,
    _calculate_yesterday_range,
)
from .models import ChartData, PointOfDelivery

_LOGGER = logging.getLogger(__name__)

# Sensor types that are always enabled for statistics import
ENABLED_SENSOR_TYPES: tuple[str, ...] = (
    SENSOR_TYPE_ACTUAL_CONSUMPTION,
    SENSOR_TYPE_ACTUAL_SUPPLY,
)


def _sanitize_name(name: str) -> str:
    """Sanitize name for use in entity IDs."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")


class SsdImsDataCoordinator(DataUpdateCoordinator):
    """Data coordinator for SSD IMS integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SsdImsApiClient,
        config: Dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        self.api_client = api_client
        self.config = config
        self.entry = entry
        self.pods: Dict[str, PointOfDelivery] = {}

        scan_interval = timedelta(
            minutes=config.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=scan_interval)

    async def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update coordinator configuration."""
        self.config = new_config
        new_interval = timedelta(
            minutes=new_config.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        if self.update_interval != new_interval:
            self.update_interval = new_interval
            _LOGGER.info(
                f"Update interval changed to {new_interval.total_seconds() / 60} minutes"
            )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API and update statistics."""
        try:
            _LOGGER.info("Starting data update for SSD IMS integration")

            if not self.pods:
                await self._discover_pods()

            pod_ids = self.config.get(CONF_POINT_OF_DELIVERY) or list(self.pods.keys())
            if not pod_ids:
                _LOGGER.warning("No PODs configured or discovered. Skipping update.")
                return {}

            await self._update_statistics(pod_ids)

            all_pod_data = {pod_id: {} for pod_id in pod_ids}
            await self._fetch_cumulative_totals_from_statistics(all_pod_data)

            now = dt_util.now()
            for pod_id in pod_ids:
                pod = self.pods.get(pod_id)
                if not pod:
                    continue

                chart_data_by_period = {}
                try:
                    period_start, period_end = _calculate_yesterday_range(now)
                    chart_data_by_period[
                        PERIOD_YESTERDAY
                    ] = await self.api_client.get_chart_data(
                        pod_id, period_start, period_end
                    )
                except Exception as e:
                    _LOGGER.error(
                        f"Error fetching yesterday data for POD {pod_id}: {e}"
                    )
                    continue

                aggregated_data = self._aggregate_data(chart_data_by_period)
                pod_data = all_pod_data.setdefault(pod_id, {})
                pod_data.update(
                    {
                        "aggregated_data": aggregated_data,
                        "last_update": now.isoformat(),
                    }
                )
                for period_key, chart_data in chart_data_by_period.items():
                    pod_data[f"chart_data_{period_key}"] = chart_data

            _LOGGER.info("Data update for all sensors completed.")
            return all_pod_data

        except ConfigEntryAuthFailed:
            raise
        except Exception as e:
            _LOGGER.error(f"Error updating data: {e}")
            raise UpdateFailed(f"Error updating data: {e}") from e

    def _get_random_api_delay(self) -> float:
        """Get random API delay."""
        delay = random.uniform(API_DELAY_MIN, API_DELAY_MAX)
        return max(0.3, delay)

    async def _update_statistics(self, pod_ids: list[str]) -> None:
        """
        Unified function to import statistics.

        Checks the last imported statistic and fetches all missing daily data
        up to yesterday. Handles both initial import and daily updates.
        """
        enabled_sensor_types = ENABLED_SENSOR_TYPES

        for pod_id in pod_ids:
            pod_name_mapping = self.config.get("pod_name_mapping", {})
            pod_name = pod_name_mapping.get(pod_id, pod_id)

            for sensor_type in enabled_sensor_types:
                statistic_type_names = {
                    SENSOR_TYPE_ACTUAL_CONSUMPTION: "actual_consumption",
                    SENSOR_TYPE_ACTUAL_SUPPLY: "actual_supply",
                }
                statistic_type = statistic_type_names.get(sensor_type)
                sanitized_friendly_name = _sanitize_name(pod_name)
                statistic_name = f"{sanitized_friendly_name}_{statistic_type}".lower()
                statistic_id = f"{DOMAIN}:{statistic_name}"

                last_stats_result = await get_instance(
                    self.hass
                ).async_add_executor_job(
                    get_last_statistics,
                    self.hass,
                    1,
                    statistic_id,
                    True,
                    {"start", "sum"},
                )

                cumulative_sum = 0.0
                start_date = dt_util.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                last_stat_timestamp = None

                if last_stats_result and statistic_id in last_stats_result:
                    last_stat = last_stats_result[statistic_id][0]
                    cumulative_sum = last_stat.get("sum") or 0.0
                    start_val = last_stat.get("start")
                    if start_val:
                        if isinstance(start_val, (int, float)):
                            start_val = dt_util.utc_from_timestamp(start_val)
                        last_stat_timestamp = dt_util.as_local(start_val)
                        start_date = last_stat_timestamp.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ) + timedelta(days=1)
                else:
                    history_days = self.config.get(
                        CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS
                    )
                    start_date = start_date - timedelta(days=history_days)

                end_date = dt_util.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

                if start_date >= end_date:
                    continue

                stats_to_import = []
                current_date = start_date
                while current_date < end_date:
                    day_start = current_date
                    day_end = day_start + timedelta(days=1) - timedelta(seconds=1)

                    try:
                        await asyncio.sleep(self._get_random_api_delay())
                        chart_data = await self.api_client.get_chart_data(
                            pod_id, day_start, day_end
                        )

                        if not chart_data or not chart_data.metering_datetime:
                            current_date += timedelta(days=1)
                            continue

                        hourly_data = {}
                        for i, timestamp_str in enumerate(chart_data.metering_datetime):
                            value = (
                                chart_data.actual_consumption[i]
                                if sensor_type == SENSOR_TYPE_ACTUAL_CONSUMPTION
                                else chart_data.actual_supply[i]
                            )
                            if value is None:
                                continue

                            timestamp_end_utc = datetime.fromisoformat(
                                timestamp_str.replace("Z", "+00:00")
                            )
                            timestamp_start_utc = timestamp_end_utc - timedelta(
                                minutes=15
                            )
                            hour_timestamp = timestamp_start_utc.replace(
                                minute=0, second=0, microsecond=0
                            )

                            if hour_timestamp not in hourly_data:
                                hourly_data[hour_timestamp] = 0.0
                            hourly_data[hour_timestamp] += value * 0.25

                        for hour_timestamp, hourly_value in sorted(hourly_data.items()):
                            if (
                                last_stat_timestamp
                                and hour_timestamp <= last_stat_timestamp
                            ):
                                continue

                            cumulative_sum += hourly_value
                            stats_to_import.append(
                                {
                                    "start": hour_timestamp,
                                    "sum": cumulative_sum,
                                }
                            )
                    except Exception as e:
                        _LOGGER.error(
                            f"Failed to fetch or process data for {statistic_id} on {day_start.date()}: {e}"
                        )

                    current_date += timedelta(days=1)

                if stats_to_import:
                    metadata = {
                        "has_sum": True,
                        "mean_type": StatisticMeanType.NONE,
                        "name": f"{pod_name} {sensor_type.replace('_', ' ').title()}",
                        "source": DOMAIN,
                        "statistic_id": statistic_id,
                        "unit_of_measurement": "kWh",
                        "unit_class": "energy",
                    }
                    async_add_external_statistics(self.hass, metadata, stats_to_import)

    async def _fetch_cumulative_totals_from_statistics(
        self, pod_data_dict: Dict[str, Any]
    ) -> None:
        """Fetch cumulative totals from external statistics."""
        enabled_sensor_types = ENABLED_SENSOR_TYPES

        for pod_id, pod_data in pod_data_dict.items():
            pod_name_mapping = self.config.get("pod_name_mapping", {})
            pod_name = pod_name_mapping.get(pod_id, pod_id)

            if "cumulative_totals" not in pod_data:
                pod_data["cumulative_totals"] = {}

            for sensor_type in enabled_sensor_types:
                statistic_type_names = {
                    SENSOR_TYPE_ACTUAL_CONSUMPTION: "actual_consumption",
                    SENSOR_TYPE_ACTUAL_SUPPLY: "actual_supply",
                }
                statistic_type = statistic_type_names.get(sensor_type, sensor_type)
                sanitized_friendly_name = _sanitize_name(pod_name)
                statistic_name = f"{sanitized_friendly_name}_{statistic_type}".lower()
                statistic_id = f"{DOMAIN}:{statistic_name}"

                last_stats = await get_instance(self.hass).async_add_executor_job(
                    get_last_statistics, self.hass, 1, statistic_id, True, {"sum"}
                )

                if last_stats and statistic_id in last_stats:
                    last_stat = last_stats[statistic_id][0]
                    cumulative_total = last_stat.get("sum", 0.0)
                    pod_data["cumulative_totals"][sensor_type] = cumulative_total
                else:
                    pod_data["cumulative_totals"][sensor_type] = 0.0

    async def _discover_pods(self) -> None:
        """Discover points of delivery."""
        try:
            pods = await self.api_client.get_points_of_delivery()
            if not pods:
                raise Exception("No points of delivery found")

            self.pods = {pod.id: pod for pod in pods}
        except Exception as e:
            error_msg = str(e)
            if any(
                auth_error in error_msg.lower()
                for auth_error in [
                    "not authenticated",
                    "authentication failed",
                    "session expired",
                ]
            ):
                raise ConfigEntryAuthFailed(
                    "Authentication failed during POD discovery"
                ) from e
            raise

    def _aggregate_data(
        self, chart_data_by_period: Dict[str, ChartData]
    ) -> Dict[str, Dict[str, float]]:
        """Aggregate data for other (non-energy) sensors."""
        aggregated = {}
        enabled_sensor_types = ENABLED_SENSOR_TYPES

        for period_key, chart_data in chart_data_by_period.items():
            aggregated[period_key] = {}

            if chart_data and hasattr(chart_data, "sum_actual_consumption"):
                if SENSOR_TYPE_ACTUAL_CONSUMPTION in enabled_sensor_types:
                    aggregated[period_key][SENSOR_TYPE_ACTUAL_CONSUMPTION] = (
                        chart_data.sum_actual_consumption or 0.0
                    )
                if SENSOR_TYPE_ACTUAL_SUPPLY in enabled_sensor_types:
                    aggregated[period_key][SENSOR_TYPE_ACTUAL_SUPPLY] = (
                        chart_data.sum_actual_supply or 0.0
                    )
            else:
                for sensor_type in enabled_sensor_types:
                    aggregated[period_key][sensor_type] = 0.0
        return aggregated
