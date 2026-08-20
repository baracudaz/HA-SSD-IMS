"""Regression tests for async_setup_entry's authentication error handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientConnectionError

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.ssd_ims import async_setup_entry


def _make_entry():
    entry = MagicMock()
    entry.data = {CONF_USERNAME: "user", CONF_PASSWORD: "pass"}
    entry.options = {}
    return entry


class TestAsyncSetupEntryAuthHandling:
    """A network/server failure must not be reported the same way as an
    actual bad-credentials failure: the former should let Home Assistant
    retry (ConfigEntryNotReady), the latter should prompt reauth
    (ConfigEntryAuthFailed)."""

    async def test_network_error_raises_config_entry_not_ready(self):
        entry = _make_entry()
        hass = MagicMock()

        with (
            patch("custom_components.ssd_ims.async_get_clientsession"),
            patch("custom_components.ssd_ims.SsdImsApiClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(
                side_effect=ClientConnectionError("network down")
            )
            mock_client_cls.return_value = mock_client

            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    async def test_invalid_credentials_raises_config_entry_auth_failed(self):
        entry = _make_entry()
        hass = MagicMock()

        with (
            patch("custom_components.ssd_ims.async_get_clientsession"),
            patch("custom_components.ssd_ims.SsdImsApiClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ConfigEntryAuthFailed):
                await async_setup_entry(hass, entry)
