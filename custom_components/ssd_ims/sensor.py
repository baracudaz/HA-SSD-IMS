"""Sensor platform for SSD IMS integration."""

import logging
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_POD_NAME_MAPPING,
    CONF_POINT_OF_DELIVERY,
    DEFAULT_POINT_OF_DELIVERY,
    DOMAIN,
    PERIOD_YESTERDAY,
    SENSOR_TYPE_ACTUAL_CONSUMPTION,
    SENSOR_TYPE_ACTUAL_SUPPLY,
    SENSOR_TYPE_LABELS,
)
from .helpers import sanitize_name
from .coordinator import SsdImsDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SSD IMS sensors from config entry."""
    coordinator: SsdImsDataCoordinator = config_entry.runtime_data

    pod_ids = config_entry.data.get(CONF_POINT_OF_DELIVERY, DEFAULT_POINT_OF_DELIVERY)
    pod_name_mapping = config_entry.data.get(CONF_POD_NAME_MAPPING, {})

    enabled_sensor_types = [SENSOR_TYPE_ACTUAL_CONSUMPTION, SENSOR_TYPE_ACTUAL_SUPPLY]

    sensors = []
    for pod_id in pod_ids:
        friendly_name = pod_name_mapping.get(pod_id, pod_id)
        sensors.append(SsdImsLastUpdateSensor(coordinator, pod_id, friendly_name))
        for sensor_type in enabled_sensor_types:
            sensors.append(
                SsdImsYesterdaySensor(
                    coordinator,
                    sensor_type,
                    PERIOD_YESTERDAY,
                    pod_id,
                    friendly_name,
                )
            )
            sensors.append(
                SsdImsCumulativeSensor(
                    coordinator,
                    sensor_type,
                    pod_id,
                    friendly_name,
                )
            )

    async_add_entities(sensors)


class SsdImsSensor(CoordinatorEntity[SsdImsDataCoordinator], SensorEntity):
    """Base sensor for SSD IMS data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SsdImsDataCoordinator,
        pod_id: str,
        friendly_name: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.pod_id = pod_id
        self.friendly_name = friendly_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.pod_id)},
            name=self.friendly_name,
            manufacturer="IMS.SSD.sk",
            model="IMS Portal",
        )

    def _setup_entity_naming(self, sensor_name: str) -> None:
        """Set up entity naming."""
        self._attr_name = sensor_name


class SsdImsEnergySensor(SsdImsSensor):
    """Base class for energy sensors."""

    def __init__(
        self,
        coordinator: SsdImsDataCoordinator,
        sensor_type: str,
        period: str,
        pod_id: str,
        friendly_name: str,
    ) -> None:
        """Initialize energy sensor."""
        super().__init__(coordinator, pod_id, friendly_name)
        self.sensor_type = sensor_type
        self.period = period
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY

    def _generate_sensor_name(self, suffix: str) -> str:
        """Generate sensor name based on type and suffix."""
        type_name = SENSOR_TYPE_LABELS.get(self.sensor_type, "Energy")
        return f"{type_name} {suffix}"


class SsdImsYesterdaySensor(SsdImsEnergySensor):
    """Sensor for yesterday's values."""

    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: SsdImsDataCoordinator,
        sensor_type: str,
        period: str,
        pod_id: str,
        friendly_name: str,
    ) -> None:
        """Initialize yesterday sensor."""
        super().__init__(coordinator, sensor_type, period, pod_id, friendly_name)
        # This is a self-contained daily snapshot, replaced once a day, and
        # can legitimately be lower than the previous day's value — not a
        # running total. TOTAL_INCREASING would make HA generate its own
        # long-term "sum" statistics for this entity, duplicating (and
        # potentially conflicting with) the external statistics the
        # coordinator writes directly for the Energy dashboard.
        self._attr_state_class = SensorStateClass.MEASUREMENT

        sensor_name = self._generate_sensor_name("Yesterday")
        sanitized_sensor_name = sanitize_name(sensor_name)
        self._attr_unique_id = f"{pod_id}_{sanitized_sensor_name}_{sensor_type}"
        self._setup_entity_naming(sensor_name)

    @property
    def native_value(self) -> StateType | None:
        """Return sensor value (yesterday's total)."""
        if not self.coordinator.data or not (
            pod_data := self.coordinator.data.get(self.pod_id)
        ):
            return None

        aggregated_data = pod_data.get("aggregated_data", {})
        period_data = aggregated_data.get(self.period, {})
        value = period_data.get(self.sensor_type)
        return float(value) if value is not None else None


class SsdImsCumulativeSensor(SsdImsEnergySensor):
    """Sensor for cumulative total energy imported from statistics."""

    def __init__(
        self,
        coordinator: SsdImsDataCoordinator,
        sensor_type: str,
        pod_id: str,
        friendly_name: str,
    ) -> None:
        """Initialize cumulative sensor."""
        super().__init__(coordinator, sensor_type, "", pod_id, friendly_name)
        # This one genuinely mirrors an ever-increasing running total read
        # back from the coordinator's own statistics.
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        sensor_name = self._generate_sensor_name("Total")
        sanitized_sensor_name = sanitize_name(sensor_name)
        self._attr_unique_id = f"{pod_id}_{sanitized_sensor_name}_{sensor_type}_total"
        self._setup_entity_naming(sensor_name)

    @property
    def native_value(self) -> StateType | None:
        """Return cumulative total from statistics."""
        if not self.coordinator.data or not (
            pod_data := self.coordinator.data.get(self.pod_id)
        ):
            return None

        cumulative_totals = pod_data.get("cumulative_totals", {})
        value = cumulative_totals.get(self.sensor_type)
        return float(value) if value is not None else None


class SsdImsLastUpdateSensor(SsdImsSensor):
    def __init__(
        self,
        coordinator: SsdImsDataCoordinator,
        pod_id: str,
        friendly_name: str,
    ) -> None:
        """Initialize last update sensor."""
        super().__init__(coordinator, pod_id, friendly_name)
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

        sensor_name = "Last Update"
        sanitized_sensor_name = sanitize_name(sensor_name)
        self._attr_unique_id = f"{pod_id}_{sanitized_sensor_name}"
        self._setup_entity_naming(sensor_name)

    @property
    def native_value(self) -> datetime | None:
        """Return sensor value (last update timestamp)."""
        if not self.coordinator.data or not (
            pod_data := self.coordinator.data.get(self.pod_id)
        ):
            return None

        last_update_str = pod_data.get("last_update")
        return dt_util.parse_datetime(last_update_str) if last_update_str else None
