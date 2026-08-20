"""End-to-end setup tests that exercise real Home Assistant machinery
(the real recorder, the real sensor entity platform) rather than mocking
it away. Two real bugs (a recorder API incompatibility in
_migrate_statistic_ids, and an invalid sensor state_class for the ENERGY
device class) were only ever caught by running the integration in a real
Home Assistant instance — every existing unit test mocked the exact pieces
that would have caught them. These tests close that gap.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ssd_ims.const import (
    CONF_HISTORY_DAYS,
    CONF_POD_NAME_MAPPING,
    CONF_POINT_OF_DELIVERY,
    DOMAIN,
)
from custom_components.ssd_ims.models import ChartData, PointOfDelivery

pytestmark = pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations")

POD_ID = "99XXX1234560000G"


def _mock_api_client():
    client = MagicMock()
    client.authenticate = AsyncMock(return_value=True)
    client.get_points_of_delivery = AsyncMock(
        return_value=[PointOfDelivery(text=f"{POD_ID} (Home)", value="v1")]
    )
    client.get_chart_data = AsyncMock(
        return_value=ChartData(
            meteringDatetime=["2026-08-18T10:15:00Z"],
            actualConsumption=[1.5],
            actualSupply=[0.0],
            sumActualConsumption=1.5,
            sumActualSupply=0.0,
        )
    )
    client.set_cached_pods = MagicMock()
    return client


async def test_full_setup_against_real_recorder_and_sensor_platform(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    """A real config entry, set up through hass.config_entries against the
    real recorder and real sensor platform, with only the network-facing
    API client mocked. A friendly name that differs from the POD id forces
    _migrate_statistic_ids to actually call the real recorder's
    get_metadata — the exact call that broke against a newer HA release
    (statistic_ids combined with statistic_source became mutually
    exclusive). Real sensor entities being added also exercises HA's
    device_class/state_class compatibility validation, which the
    MEASUREMENT state class on the Yesterday sensor failed for the ENERGY
    device class.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="test_user",
        data={
            "username": "test_user",
            "password": "test_pass",
            CONF_POINT_OF_DELIVERY: [POD_ID],
            CONF_POD_NAME_MAPPING: {POD_ID: "Home"},
            CONF_HISTORY_DAYS: 1,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ssd_ims.SsdImsApiClient", return_value=_mock_api_client()
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Real entities were actually created, not just a "setup returned True".
    for entity_id in (
        "sensor.home_actual_consumption_yesterday",
        "sensor.home_actual_supply_yesterday",
        "sensor.home_actual_consumption_total",
        "sensor.home_actual_supply_total",
        "sensor.home_last_update",
    ):
        assert hass.states.get(entity_id) is not None, f"{entity_id} was not created"

    log_text = caplog.text
    assert "impossible" not in log_text, (
        "sensor state_class incompatible with its device_class"
    )
    assert "mutually exclusive" not in log_text, (
        "_migrate_statistic_ids called the recorder with an invalid "
        "statistic_ids/statistic_source combination"
    )
    assert "Traceback" not in log_text, f"unexpected error during setup:\n{log_text}"
