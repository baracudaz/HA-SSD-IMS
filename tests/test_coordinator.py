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


class TestBackgroundBackfillGateOrdering:
    """Regression test for the first-refresh background backfill task.

    The background task used to set the smart-polling gate
    (_last_successful_data_date) *before* calling async_request_refresh().
    Since that refresh re-enters _async_update_data, which returns early
    (without recomputing cumulative totals) whenever the gate is already
    set for today, the premature set made the refresh short-circuit and
    return the stale, pre-backfill data — leaving the Total sensors stuck
    at 0 until the gate reset the next calendar day, even though the
    backfill had just successfully populated statistics.
    """

    async def test_gate_is_not_set_before_requesting_refresh(self):
        coordinator = _make_coordinator(MagicMock(), {})
        gate_at_refresh_time = "unset"

        async def fake_request_refresh():
            nonlocal gate_at_refresh_time
            gate_at_refresh_time = coordinator._last_successful_data_date

        coordinator._update_statistics = AsyncMock(return_value=True)
        coordinator.async_request_refresh = AsyncMock(side_effect=fake_request_refresh)

        await coordinator._async_backfill_statistics(["pod_1"])

        assert gate_at_refresh_time is None


class TestStatisticIdKeying:
    """statistic_id is derived from the user-editable friendly POD name
    (falling back to pod_id when no friendly name is set). This is a
    deliberate, currently-accepted limitation, not an oversight: an
    earlier pod_id-keyed design (with a rename-on-upgrade migration path)
    ran into a Home Assistant core limitation where the statistics-rename
    primitive silently no-ops for external, non-recorder-source statistics
    like ours, making that migration path unsafe. Since no published
    version of this integration has ever used a different scheme, there is
    nothing to migrate, so the simpler friendly-name-based scheme was kept.
    Renaming a POD's friendly name does start a fresh statistics series —
    documented, not silently handled."""

    def test_statistic_id_derives_from_friendly_name(self):
        assert (
            SsdImsDataCoordinator._build_statistic_id("Home", "actual_consumption")
            == "ssd_ims:home_actual_consumption"
        )

    def test_statistic_id_changes_when_friendly_name_changes(self):
        before = SsdImsDataCoordinator._build_statistic_id("Home", "actual_consumption")
        after = SsdImsDataCoordinator._build_statistic_id(
            "Cottage", "actual_consumption"
        )
        assert before != after

    def test_statistic_id_falls_back_to_pod_id_without_a_friendly_name(self):
        pod_id = "99XXX1234560000G"
        assert (
            SsdImsDataCoordinator._build_statistic_id(pod_id, "actual_consumption")
            == "ssd_ims:99xxx1234560000g_actual_consumption"
        )


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
