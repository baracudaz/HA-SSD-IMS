# Changelog

## Version 2.1.6

- **Bug fix**: The initial statistics backfill (e.g. large `history_days` catch-up on first setup) no longer blocks Home Assistant's startup and can trip its bootstrap timeout; it now runs as a background task while setup completes immediately, with entities updating once the backfill finishes
- **Internal**: Added a lock around statistics updates so the background backfill task and a regular scheduled poll can't run concurrently against the same statistics
- **Internal**: Statistics are now flushed to Home Assistant day-by-day during backfill instead of all at once at the end, so progress survives an interrupted or cancelled update

## Version 2.1.5

- **Maintenance**: Updated release metadata for the 2.1.5 version

## Version 2.1.4

- **Metadata**: Updated integration display name to `Stredoslovenská distribučná (SSD IMS)`
- **Docs**: Synchronized installation and setup text with the current Home Assistant integration name

## Version 2.1.3

- **Metadata**: Renamed integration display name to `Stredoslovenská distribučná - Portál energetických dát (SSD IMS)` for clearer identification in Home Assistant
- **Docs**: Updated installation and setup wording to reference the new integration display name

## Version 2.1.1

- **Bug fix**: Reduced log noise — duplicate error messages (logged in both the API client and coordinator) are now emitted only once, at the coordinator level
- **Bug fix**: Session expiry on each scheduled poll (expected behavior) was logged as `WARNING`; downgraded to `DEBUG` since re-authentication is automatic and always handled
- **Internal**: Added `asyncio_mode = "auto"` to `pyproject.toml` so tests run correctly with a plain `pytest` invocation

## Version 2.1.0

- **New feature**: Re-authentication flow — when credentials expire, Home Assistant will prompt you to re-enter them without needing to remove and re-add the integration
- **New feature**: Reconfigure flow — update your Points of Delivery selection and friendly names via the integration's "Reconfigure" option, with current settings pre-filled
- **New feature**: Diagnostics support — integration data (PODs, last update, energy totals) is now included in Home Assistant's diagnostics download; credentials are automatically redacted
- **New feature**: Cumulative total sensors — two additional sensors per POD (`Actual Consumption Total`, `Actual Supply Total`) expose the running cumulative energy totals from the statistics database, useful in automations and templates
- **New feature**: Smart polling — once all statistics are confirmed complete for the current calendar day, subsequent scheduled polls skip the API entirely and return cached data; the integration retries automatically on the next poll if the portal hasn't published yet

## Version 2.0.6

- **Bug fix**: Scan interval set via the options flow now survives a restart; `async_setup_entry` reads `entry.options` first and falls back to `entry.data`
- **Bug fix**: `async_unload_entry` once again clears `entry.runtime_data` after successful platform unload, preventing stale coordinator references on reload
- **Bug fix**: Migration to version 2 no longer silently bumps the config version when POD discovery returns `None`; it now logs an error and returns `False` so the migration is retried on the next startup

## Version 2.0.5

- **Bug fix**: Authentication failures now correctly trigger Home Assistant's re-authentication flow instead of silently failing at startup
- **Bug fix**: Config entry migration no longer re-runs on every restart (version is now properly bumped to 2 after migration)
- **Bug fix**: Platform setup now correctly waits for the first data fetch before registering entities, preventing empty sensor states on initial load
- **Bug fix**: `calculate_yesterday_range` now returns both start and end as UTC-aware datetimes (was returning a naive local datetime for start)
- **Bug fix**: Session expiry detection now catches HTTP 200 responses with an HTML body (portal login-page redirect), not just non-200 responses
- **Internal**: Options flow now stores mutable settings (update interval) in `entry.options` instead of `entry.data`
- **Internal**: Sensor entities now use the standard `CoordinatorEntity` base class and typed `DeviceInfo` object
- **Internal**: Config flow uses the shared Home Assistant aiohttp session instead of creating its own `ClientSession`
- **Internal**: Replaced deprecated `FlowResult` with `ConfigFlowResult`; bumped config flow `VERSION` to 2
- **Internal**: Replaced `raise Exception(...)` with `raise RuntimeError(...)` for specificity
- **Internal**: Modernized all type hints to Python 3.10+ union syntax (`X | None`, `list[X]`, `dict[K, V]`)
- **Internal**: Replaced f-string logging with lazy `%s` format throughout
- **Internal**: Removed unused models (`PodNameMapping`, `QualityType`, `AggregatedData`), constants (`CONF_HISTORY_IMPORT_DONE`), and dead method `_get_pod_id_by_text`
- **Internal**: Added `SensorStateClass.TOTAL_INCREASING` to energy sensors for correct HA statistics integration

## Version 2.0.4

- Refactor release: moved shared utility logic to `helpers.py` and kept `const.py` constants-only
- Runtime/performance improvements: `ConfigEntry.runtime_data`, shared HA aiohttp session, POD cache (TTL)
- Internal cleanup: reduced duplicated logic in API client, coordinator, config flow, and sensors

## Version 2.0.3

- Stability and maintenance updates
- Small fixes and quality improvements

## Version 2.0.2

- Bug fixes for data handling and integration reliability
- Minor internal improvements

## Version 2.0.1

- Runtime cleanup: migrated to `ConfigEntry.runtime_data` and shared HA aiohttp session
- Performance: added POD cache (TTL) and fixed stable→session POD lookup
- Refactor: moved utility methods to `helpers.py` and kept `const.py` constants-only
- Docs: moved changelog out of `README.md` into `CHANGELOG.md`

## Version 2.0.0

- Major update: simplified to 3 sensors per POD and switched to long-term statistics import
- Added Energy dashboard-ready statistics and historical import in setup flow
- Removed legacy multi-period/idle-reactive sensors and improved translations

## Version 1.x

- Initial releases with multiple sensor types and time periods
- Forked from <https://github.com/samsk/HA-SSD-IMS>
