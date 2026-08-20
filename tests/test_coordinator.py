"""Regression tests for SsdImsDataCoordinator statistics import logic."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util import dt as dt_util

from custom_components.ssd_ims.api_client import SsdImsAuthenticationError
from custom_components.ssd_ims.const import CONF_HISTORY_DAYS, CONF_POD_NAME_MAPPING
from custom_components.ssd_ims.coordinator import SsdImsDataCoordinator
from custom_components.ssd_ims.models import ChartData, PointOfDelivery


def _make_coordinator(api_client, config):
    """Build a coordinator instance without going through HA's config-entry setup."""
    coordinator = SsdImsDataCoordinator.__new__(SsdImsDataCoordinator)
    coordinator.hass = MagicMock()
    coordinator.api_client = api_client
    coordinator.config = config
    coordinator.entry = MagicMock()
    coordinator.pods = {}
    coordinator._last_successful_data_date = None
    coordinator._stats_lock = asyncio.Lock()
    coordinator.data = None
    return coordinator


def _chart_data(value: float = 1.0) -> ChartData:
    return ChartData(
        meteringDatetime=["2024-01-01T10:15:00.0000000Z"],
        actualConsumption=[value],
        actualSupply=[0.0],
        idleConsumption=[0.0],
        idleSupply=[0.0],
        sumActualConsumption=value,
        sumActualSupply=0.0,
        sumIdleConsumption=0.0,
        sumIdleSupply=0.0,
    )


async def _run_executor(fn, *args, **kwargs):
    """Stand-in for HA's recorder executor job: just call the function inline."""
    return fn(*args, **kwargs)


class TestStatisticsBackfillFailureHandling:
    """Regression tests for a mid-range day failure during the backfill walk."""

    async def test_mid_range_day_failure_stops_the_walk_and_reports_incomplete(self):
        """A day that fails partway through the range must not be skipped over.

        Before the fix, an exception on a middle day was logged and the walk
        continued to later days, letting a later day's flush land on top of a
        cumulative_sum that silently omitted the failed day's contribution. If
        the final day still succeeded, the whole POD/sensor was (incorrectly)
        reported complete, and — because resumption on the next poll is based
        on the last *persisted* statistic — the failed day's gap would never
        be retried, permanently understating the running total.
        """
        fail_day = dt_util.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=2)

        async def get_chart_data_side_effect(pod_id, day_start, day_end):
            if day_start.date() == fail_day.date():
                raise RuntimeError("simulated network error")
            return _chart_data()

        api_client = MagicMock()
        api_client.get_chart_data = AsyncMock(side_effect=get_chart_data_side_effect)

        coordinator = _make_coordinator(
            api_client, {CONF_HISTORY_DAYS: 3, CONF_POD_NAME_MAPPING: {}}
        )

        with (
            patch(
                "custom_components.ssd_ims.coordinator.get_instance"
            ) as mock_get_instance,
            patch(
                "custom_components.ssd_ims.coordinator.get_last_statistics",
                return_value={},
            ),
            patch(
                "custom_components.ssd_ims.coordinator.async_add_external_statistics"
            ) as mock_add_stats,
            patch("custom_components.ssd_ims.coordinator.asyncio.sleep", AsyncMock()),
        ):
            mock_instance = MagicMock()
            mock_instance.async_add_executor_job = AsyncMock(side_effect=_run_executor)
            mock_get_instance.return_value = mock_instance

            result = await coordinator._update_statistics_locked(["pod_1"])

        assert result is False
        # 2 sensor types x (day 1 succeeds, day 2 raises -> walk stops before day 3).
        assert api_client.get_chart_data.call_count == 4
        # Only day 1 ever produces a flush; day 3 must never be reached/flushed.
        assert mock_add_stats.call_count == 2


class TestStatisticIdKeying:
    """Regression tests: statistic_id must be derived from the stable pod_id,
    never the user-editable friendly name (renaming a POD must not orphan
    its previously-imported statistics)."""

    def test_statistic_id_is_stable_across_friendly_name_changes(self):
        pod_id = "99XXX1234560000G"
        assert SsdImsDataCoordinator._build_statistic_id(
            pod_id, "actual_consumption"
        ) == SsdImsDataCoordinator._build_statistic_id(pod_id, "actual_consumption")
        assert (
            SsdImsDataCoordinator._build_statistic_id(pod_id, "actual_consumption")
            == "ssd_ims:99xxx1234560000g_actual_consumption"
        )

    async def test_migrate_statistic_ids_renames_legacy_metadata(self):
        pod_id = "pod_1"
        legacy_id = "ssd_ims:home_actual_consumption"
        new_id = "ssd_ims:pod_1_actual_consumption"

        coordinator = _make_coordinator(
            MagicMock(), {CONF_POD_NAME_MAPPING: {pod_id: "Home"}}
        )

        with (
            patch(
                "custom_components.ssd_ims.coordinator.get_instance"
            ) as mock_get_instance,
            patch(
                "custom_components.ssd_ims.coordinator.get_metadata"
            ) as mock_get_metadata,
            patch(
                "custom_components.ssd_ims.coordinator.async_update_statistics_metadata"
            ) as mock_rename,
        ):
            mock_instance = MagicMock()
            mock_instance.async_add_executor_job = AsyncMock(side_effect=_run_executor)
            mock_get_instance.return_value = mock_instance
            # Only the actual_consumption legacy id has been imported before;
            # actual_supply has never existed under the legacy name.
            mock_get_metadata.return_value = {legacy_id: (1, MagicMock())}

            await coordinator._migrate_statistic_ids([pod_id])

        mock_rename.assert_called_once_with(
            coordinator.hass, legacy_id, new_statistic_id=new_id
        )

    async def test_migrate_statistic_ids_skips_when_no_legacy_metadata_exists(self):
        """A fresh install (or one already migrated) has nothing to rename."""
        pod_id = "pod_1"
        coordinator = _make_coordinator(
            MagicMock(), {CONF_POD_NAME_MAPPING: {pod_id: "Home"}}
        )

        with (
            patch(
                "custom_components.ssd_ims.coordinator.get_instance"
            ) as mock_get_instance,
            patch(
                "custom_components.ssd_ims.coordinator.get_metadata",
                return_value={},
            ),
            patch(
                "custom_components.ssd_ims.coordinator.async_update_statistics_metadata"
            ) as mock_rename,
        ):
            mock_instance = MagicMock()
            mock_instance.async_add_executor_job = AsyncMock(side_effect=_run_executor)
            mock_get_instance.return_value = mock_instance

            await coordinator._migrate_statistic_ids([pod_id])

        mock_rename.assert_not_called()

    async def test_migrate_statistic_ids_noop_when_no_friendly_name_set(self):
        """When pod_name_mapping has no entry, legacy id already equals the new
        id, so no recorder lookup/rename should happen at all."""
        pod_id = "pod_1"
        coordinator = _make_coordinator(MagicMock(), {CONF_POD_NAME_MAPPING: {}})

        with patch(
            "custom_components.ssd_ims.coordinator.get_instance"
        ) as mock_get_instance:
            await coordinator._migrate_statistic_ids([pod_id])
            mock_get_instance.assert_not_called()


class TestPodDiscovery:
    """Regression tests for _discover_pods robustness.

    Filtering out PODs with unparseable text now happens one layer down, in
    SsdImsApiClient.get_points_of_delivery (see test_api_client.py) — every
    PointOfDelivery that exists at all is guaranteed to have a valid `.id`.
    These tests confirm the coordinator correctly trusts and uses whatever
    valid list the API client hands back.
    """

    async def test_discover_pods_builds_pods_dict_and_seeds_cache(self):
        pod_a = PointOfDelivery(text="99XXX1234560000G (Home)", value="v1")
        pod_b = PointOfDelivery(text="99YYY9876540000G (Garage)", value="v2")

        api_client = MagicMock()
        api_client.get_points_of_delivery = AsyncMock(return_value=[pod_a, pod_b])
        api_client.set_cached_pods = MagicMock()

        coordinator = _make_coordinator(api_client, {})

        await coordinator._discover_pods()

        assert coordinator.pods == {pod_a.id: pod_a, pod_b.id: pod_b}
        api_client.set_cached_pods.assert_called_once_with([pod_a, pod_b])

    async def test_authentication_error_becomes_config_entry_auth_failed(self):
        """A typed auth failure from the API client must be translated into
        ConfigEntryAuthFailed, not left to fragile string matching."""
        api_client = MagicMock()
        api_client.get_points_of_delivery = AsyncMock(
            side_effect=SsdImsAuthenticationError("Not authenticated")
        )

        coordinator = _make_coordinator(api_client, {})

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._discover_pods()
