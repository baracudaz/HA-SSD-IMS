"""Shared pytest fixtures — pulls in Home Assistant's own test harness.

Deliberately NOT making `enable_custom_integrations` autouse here: it
requires the `hass` fixture, and any test that also needs `recorder_mock`
(because this integration declares "recorder" as a manifest dependency)
must have recorder_mock's own internal setup run *before* `hass` is
otherwise touched. A blanket autouse fixture here would force `hass` to
spin up first for every test, breaking that ordering requirement. Test
modules that exercise the config/options flow request both fixtures
explicitly instead (see test_config_flow.py).
"""

pytest_plugins = "pytest_homeassistant_custom_component"
