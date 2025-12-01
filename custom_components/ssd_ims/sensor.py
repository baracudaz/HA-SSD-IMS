"""Sensor platform for SSD IMS integration."""

import logging
import re
from datetime import datetime
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_SUPPLY_SENSORS,
    CONF_POD_NAME_MAPPING,
    CONF_POINT_OF_DELIVERY,
    DEFAULT_ENABLE_SUPPLY_SENSORS,
    DEFAULT_POINT_OF_DELIVERY,
    DOMAIN,
    PERIOD_YESTERDAY,
    SENSOR_TYPE_ACTUAL_CONSUMPTION,
    SENSOR_TYPE_ACTUAL_SUPPLY,
)
from .coordinator import SsdImsDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SSD IMS sensors from config entry."""
    coordinator: SsdImsDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    pod_ids = config_entry.data.get(CONF_POINT_OF_DELIVERY, DEFAULT_POINT_OF_DELIVERY)
    pod_name_mapping = config_entry.data.get(CONF_POD_NAME_MAPPING, {})
    enable_supply_sensors = config_entry.data.get(
        CONF_ENABLE_SUPPLY_SENSORS, DEFAULT_ENABLE_SUPPLY_SENSORS
    )

    enabled_sensor_types = [SENSOR_TYPE_ACTUAL_CONSUMPTION]
    if enable_supply_sensors:
        enabled_sensor_types.append(SENSOR_TYPE_ACTUAL_SUPPLY)

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

    async_add_entities(sensors)


def _sanitize_name(name: str) -> str:
    """Sanitize name for use in sensor names."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")


class SsdImsSensor(SensorEntity):
    """Base sensor for SSD IMS data."""

    def __init__(
        self,
        coordinator: SsdImsDataCoordinator,
        pod_id: str,
        friendly_name: str,
    ) -> None:
        """Initialize sensor."""
        self.coordinator = coordinator
        self.pod_id = pod_id
        self.friendly_name = friendly_name

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.pod_id)},
            "name": self.friendly_name,
            "manufacturer": "IMS.SSD.sk",
            "model": "IMS Portal",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def should_poll(self) -> bool:
        """Return False as this entity is updated via coordinator."""
        return False

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    def _setup_entity_naming(self, sensor_name: str) -> None:
        """Set up entity naming."""
        self._attr_has_entity_name = True
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
        type_names = {
            SENSOR_TYPE_ACTUAL_CONSUMPTION: "Actual Consumption",
            SENSOR_TYPE_ACTUAL_SUPPLY: "Actual Supply",
        }
        type_name = type_names.get(self.sensor_type, "Energy")
        return f"{type_name} {suffix}"


class SsdImsYesterdaySensor(SsdImsEnergySensor):
    """Sensor for yesterday's values."""

    _attr_entity_registry_enabled_default = False

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

        sensor_name = self._generate_sensor_name("Yesterday")
        sanitized_sensor_name = _sanitize_name(sensor_name)
        self._attr_unique_id = f"{pod_id}_{sanitized_sensor_name}_{sensor_type}"
        self._setup_entity_naming(sensor_name)

    @property
    def native_value(self) -> Optional[StateType]:
        """Return sensor value (yesterday's total)."""
        if not self.coordinator.data or not (
            pod_data := self.coordinator.data.get(self.pod_id)
        ):
            return None

        aggregated_data = pod_data.get("aggregated_data", {})
        period_data = aggregated_data.get(self.period, {})
        value = period_data.get(self.sensor_type)
        return float(value) if value is not None else None


class SsdImsLastUpdateSensor(SsdImsSensor):
    """Sensor for last update timestamp."""

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
        sanitized_sensor_name = _sanitize_name(sensor_name)
        self._attr_unique_id = f"{pod_id}_{sanitized_sensor_name}"
        self._setup_entity_naming(sensor_name)

    @property
    def native_value(self) -> Optional[datetime]:
        """Return sensor value (last update timestamp)."""
        if not self.coordinator.data or not (
            pod_data := self.coordinator.data.get(self.pod_id)
        ):
            return None

        last_update_str = pod_data.get("last_update")
        return dt_util.parse_datetime(last_update_str) if last_update_str else None
