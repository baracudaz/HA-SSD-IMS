# Changelog

## Version 2.1.9

- **Docs**: Fixed the README's Energy dashboard / long-term statistics examples, which still showed statistic IDs keyed by friendly POD name (`ssd_ims:<pod_name>_...`); they're keyed by the stable POD ID (`ssd_ims:<pod_id>_...`) as of 2.1.8
- **Docs**: The README's development section didn't mention `make install`, the actual first step needed before `make test`/`make lint` work locally; added
- **Internal**: `make test-coverage`, referenced by the README but not implemented, now actually runs (`pytest-cov` added as a dependency)
- **Internal**: Added a `Dependency Review` CI workflow that flags newly introduced vulnerable dependencies on pull requests
- **Internal**: Added a `CodeQL` CI workflow for static security analysis of the Python code, on push/PR and weekly on a schedule
- **Internal**: Removed a redundant explicit `pytest-asyncio` install in `make install` and CI — `requirements.txt` already pins it
- **Internal**: Added test coverage for `helpers.py` (previously untested, including the DST-sensitive UTC conversion in `calculate_yesterday_range`) and the `models.py` validators' error paths

## Version 2.1.8

- **Bug fix**: Network errors, timeouts, and unexpected responses during login were reported the same way as wrong credentials, forcing a spurious reauthentication prompt instead of a transparent retry. Authentication failures are now raised distinctly from actual credential rejection, so setup correctly raises `ConfigEntryNotReady` (retried automatically) instead of `ConfigEntryAuthFailed` for transient connectivity issues
- **Bug fix**: The statistics backfill's day boundaries were computed in local time and sent to the portal unconverted, while the "yesterday" sensors' boundaries were converted to UTC first — an inconsistency that could shift which readings landed in which day around DST transitions. Both now convert to UTC consistently
- **Bug fix**: A single POD whose text couldn't be parsed into a stable ID (e.g. after a portal-side format change) aborted discovery for every configured POD. It's now skipped individually, with the rest discovered normally
- **Bug fix**: Server errors (5xx) were not retried despite the error message claiming they would be; they're now treated as transient and retried with the same backoff as network errors
- **Bug fix**: The `too_long` POD name validation message said "maximum 32 characters" while the actual configured limit is 50; the message now matches
- **Bug fix**: The "Yesterday" sensors used the `total_increasing` state class, which is only correct for a genuinely monotonic running total. Since this sensor is a daily snapshot that can legitimately be lower than the previous day, that state class made Home Assistant auto-generate its own long-term statistics for the entity — a second, redundant series alongside the one this integration writes directly. It's now `measurement`; the cumulative total sensors keep `total_increasing`, which is correct for them
- **Bug fix**: Authentication-failure detection during POD discovery matched substrings of exception messages, which would silently break if those messages were ever reworded. It's now based on a dedicated exception type
- **Bug fix**: Diagnostics downloads included the raw POD ID (a utility meter number) and any friendly name set for a POD, which the setup flow's own guidance suggests filling in with a home address. Both are now redacted/anonymized in the diagnostics payload
- **New feature**: Adding the same SSD IMS account as a second config entry is no longer allowed
- **Internal**: Removed unused code: `get_metering_data` and its supporting models, and the `session_token`/`is_authenticated`/`logout()` API client members, none of which were called anywhere in the integration
- **Internal**: The API client's internal POD cache is now seeded from the coordinator's own discovery result and its TTL raised from 5 to 60 minutes, avoiding redundant POD re-fetches during a long-running statistics backfill

## Version 2.1.7

- **Bug fix**: A single day that failed to fetch or process partway through the statistics backfill range was previously skipped over silently, and if the final day still succeeded the whole range was marked complete — permanently understating the cumulative energy total from that point on, since the next poll resumes from the last successfully persisted day. A failed day now stops the backfill walk for that POD/sensor and is retried on the next poll instead of being silently dropped
- **Bug fix**: `None` entries in the portal's `actualConsumption`/`actualSupply` chart data were dropped instead of zero-filled, which could shift every value after the gap out of alignment with its timestamp. They're now preserved as `0.0` so list positions stay aligned
- **Bug fix**: External statistic IDs are now derived from the stable POD ID instead of the user-editable friendly name. Previously, renaming a POD (via initial setup or the reconfigure flow) changed its statistic ID and silently orphaned all previously-imported history, resetting the Energy dashboard total for that POD to zero. Existing installs are migrated automatically: statistics found under the old, name-derived ID are renamed in place to the new pod_id-derived ID, preserving history
- **Internal**: `pyproject.toml` is now tracked in the repository instead of being gitignored, so a fresh clone gets the same `ruff`/`pytest` configuration as the working tree CI already relies on
- **Internal**: CI now runs the `pytest` test suite on every push/PR, alongside the existing `ruff` lint/format checks

## Version 2.1.6

- **Bug fix**: The initial statistics backfill (e.g. large `history_days` catch-up on first setup) no longer blocks Home Assistant's startup and can trip its bootstrap timeout; it now runs as a background task while setup completes immediately, with entities updating once the backfill finishes
- **Internal**: Added a lock around statistics updates so the background backfill task and a regular scheduled poll can't run concurrently against the same statistics
- **Internal**: Statistics are now flushed to Home Assistant day-by-day during backfill instead of all at once at the end, so progress survives an interrupted or cancelled update
- **Bug fix**: Smart-polling completeness was judged on whether *any* day in the backfill range had published data; a pod/sensor with older data but no data for yesterday yet was incorrectly marked complete, skipping retries for the rest of the day. It's now judged on the most recent pending day specifically
- **Bug fix**: Restored an explicit `pydantic` entry in `manifest.json` requirements — it's imported directly (`models.py`) and, unlike `aiohttp`, isn't a dependency of Home Assistant core itself, so it isn't guaranteed to be present otherwise

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
