"""SSD IMS Home Assistant integration."""

import logging
import re

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api_client import SsdImsApiClient
from .const import (
    CONF_HISTORY_DAYS,
    CONF_POD_NAME_MAPPING,
    CONF_POINT_OF_DELIVERY,
    CONF_SCAN_INTERVAL,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_POINT_OF_DELIVERY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import SsdImsDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SSD IMS from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    session = ClientSession()
    api_client = SsdImsApiClient(session)

    # Authenticate
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    if not await api_client.authenticate(username, password):
        _LOGGER.error("Failed to authenticate with SSD IMS")
        await session.close()
        return False

    # Create coordinator
    config = {
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
        CONF_SCAN_INTERVAL: entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        CONF_POINT_OF_DELIVERY: entry.data.get(
            CONF_POINT_OF_DELIVERY, DEFAULT_POINT_OF_DELIVERY
        ),  # Now contains stable pod_ids
        CONF_POD_NAME_MAPPING: entry.data.get(CONF_POD_NAME_MAPPING, {}),
        CONF_HISTORY_DAYS: entry.data.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
    }

    coordinator = SsdImsDataCoordinator(hass, api_client, config, entry)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Load platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Schedule immediate first data request
    await coordinator.async_config_entry_first_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: SsdImsDataCoordinator = hass.data[DOMAIN][entry.entry_id]

        # Close API client session
        if hasattr(coordinator.api_client, "_session"):
            await coordinator.api_client._session.close()

        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry if needed."""
    if entry.version == 1:
        # Migrate from POD IDs/texts to stable POD IDs
        data = dict(entry.data)
        point_of_delivery = data.get(CONF_POINT_OF_DELIVERY, DEFAULT_POINT_OF_DELIVERY)

        # Check if we have old POD ID format (long strings that look like session
        # tokens)
        if point_of_delivery and any(len(pod) > 50 for pod in point_of_delivery):
            _LOGGER.info("Migrating from session POD IDs to stable POD IDs")

            # Create API client to discover PODs
            session = ClientSession()
            api_client = SsdImsApiClient(session)

            try:
                # Authenticate to get PODs
                username = data[CONF_USERNAME]
                password = data[CONF_PASSWORD]

                if await api_client.authenticate(username, password):
                    # Get current PODs
                    pods = await api_client.get_points_of_delivery()
                    pod_mapping = {}  # session_id -> stable_id

                    for pod in pods:
                        try:
                            stable_id = pod.id  # Extract stable 16-20 char ID
                            pod_mapping[pod.value] = stable_id
                        except ValueError as e:
                            _LOGGER.warning(
                                "Skipping POD with invalid ID format: %s - %s",
                                pod.text,
                                e,
                            )
                            continue

                    _LOGGER.debug(
                        f"Available PODs for migration: {list(pod_mapping.values())}"
                    )

                    # Migrate session POD IDs to stable POD IDs
                    new_point_of_delivery = []
                    for session_pod_id in point_of_delivery:
                        if session_pod_id in pod_mapping:
                            stable_pod_id = pod_mapping[session_pod_id]
                            new_point_of_delivery.append(stable_pod_id)
                            _LOGGER.info(
                                f"Migrated session POD ID {session_pod_id} to stable ID {stable_pod_id}"
                            )
                        else:
                            _LOGGER.warning(
                                f"Session POD ID {session_pod_id} not found in current PODs, removing"
                            )

                    # Update configuration
                    data[CONF_POINT_OF_DELIVERY] = new_point_of_delivery

                    # Update entry
                    hass.config_entries.async_update_entry(entry, data=data)
                    _LOGGER.info("Configuration migration completed")
                else:
                    _LOGGER.error("Failed to authenticate during migration")
                    return False

            except Exception as e:
                _LOGGER.error(f"Error during configuration migration: {e}")
                return False
            finally:
                await session.close()

        # Also check for POD texts that need to be converted to stable IDs
        elif point_of_delivery:
            _LOGGER.debug("Checking for POD text to stable ID conversion")

            # Create API client to discover PODs
            session = ClientSession()
            api_client = SsdImsApiClient(session)

            try:
                # Authenticate to get PODs
                username = data[CONF_USERNAME]
                password = data[CONF_PASSWORD]

                if await api_client.authenticate(username, password):
                    # Get current PODs
                    pods = await api_client.get_points_of_delivery()
                    pod_text_to_id = {}  # text -> stable_id

                    for pod in pods:
                        try:
                            stable_id = pod.id  # Extract stable 16-20 char ID
                            pod_text_to_id[pod.text] = stable_id
                        except ValueError as e:
                            _LOGGER.warning(
                                f"Skipping POD with invalid ID format: {pod.text} - {e}"
                            )
                            continue

                    _LOGGER.debug(
                        f"Available POD stable IDs: {list(pod_text_to_id.values())}"
                    )
                    _LOGGER.debug(f"Configured POD texts: {point_of_delivery}")

                    # Check if any configured PODs are not in current list
                    missing_pods = [
                        pod for pod in point_of_delivery if pod not in pod_text_to_id
                    ]
                    if missing_pods:
                        _LOGGER.warning(
                            f"Some configured POD texts not found in current API response: {missing_pods}"
                        )

                        # Try to find similar PODs by extracting the POD number
                        updated_point_of_delivery = []
                        for pod_text in point_of_delivery:
                            if pod_text in pod_text_to_id:
                                stable_id = pod_text_to_id[pod_text]
                                updated_point_of_delivery.append(stable_id)
                                _LOGGER.info(
                                    f"Converted POD text {pod_text} to stable ID {stable_id}"
                                )
                            else:
                                # Try to find a match by POD number
                                match = re.search(r"^([A-Z0-9]+)", pod_text)
                                if match:
                                    pod_number = match.group(1)
                                    # Look for PODs with the same number
                                    for (
                                        current_pod_text,
                                        stable_id,
                                    ) in pod_text_to_id.items():
                                        if current_pod_text.startswith(pod_number):
                                            updated_point_of_delivery.append(stable_id)
                                            _LOGGER.info(
                                                f"Updated POD from {pod_text} to stable ID {stable_id}"
                                            )
                                            break
                                    else:
                                        _LOGGER.warning(
                                            f"No matching POD found for {pod_text}"
                                        )
                                else:
                                    _LOGGER.warning(
                                        f"Could not extract POD number from {pod_text}"
                                    )
                        else:
                            # Convert all POD texts to stable IDs
                            updated_point_of_delivery = []
                            for pod_text in point_of_delivery:
                                if pod_text in pod_text_to_id:
                                    stable_id = pod_text_to_id[pod_text]
                                    updated_point_of_delivery.append(stable_id)
                                    _LOGGER.info(
                                        f"Converted POD text {pod_text} to stable ID {stable_id}"
                                    )
                                else:
                                    _LOGGER.warning(
                                        f"POD text {pod_text} not found, removing"
                                    )

                        # Update configuration if changes were made
                        if updated_point_of_delivery != point_of_delivery:
                            data[CONF_POINT_OF_DELIVERY] = updated_point_of_delivery
                            hass.config_entries.async_update_entry(entry, data=data)
                            _LOGGER.info("POD text to stable ID conversion completed")

            except Exception as e:
                _LOGGER.error(f"Error during POD text to stable ID conversion: {e}")
                # Don't fail the migration for this, just log the error
            finally:
                await session.close()

        return True

    return False
