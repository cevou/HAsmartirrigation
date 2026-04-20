# 5-Day Bucket Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Bucket Forecast" button per zone that expands a 5-day table showing estimated daily ET, precipitation, drainage, delta, and bucket-end-of-day using live weather service forecast data.

**Architecture:** New backend websocket endpoint `smart_irrigation/bucket_forecast` — two new coordinator methods (`_calculate_forecast_day`, `async_generate_bucket_forecast`) — mirrors the existing `/watering_calendar` pattern exactly. Frontend adds a lazily-fetched toggle section identical to the watering calendar section.

**Tech Stack:** Python 3.13, Home Assistant websocket API, Lit (TypeScript web components), `@mdi/js` icons, `moment.js` for date formatting, `pytest` + `unittest.mock` for tests.

---

## File Map

| File | Change |
|------|--------|
| `custom_components/smart_irrigation/__init__.py` | Add `_calculate_forecast_day()` and `async_generate_bucket_forecast()` methods to the coordinator class |
| `custom_components/smart_irrigation/websockets.py` | Add `websocket_get_bucket_forecast` handler and register it |
| `custom_components/smart_irrigation/frontend/src/types.ts` | Add `BucketForecastDay` interface |
| `custom_components/smart_irrigation/frontend/src/data/websockets.ts` | Add `fetchBucketForecast` function |
| `custom_components/smart_irrigation/frontend/localize/languages/en.json` | Add 5 new localization keys |
| `custom_components/smart_irrigation/frontend/localize/languages/it.json` | Add 5 new localization keys (Italian) |
| `custom_components/smart_irrigation/frontend/localize/languages/de.json` | Add 5 new localization keys (English fallback) |
| `custom_components/smart_irrigation/frontend/localize/languages/es.json` | Add 5 new localization keys (English fallback) |
| `custom_components/smart_irrigation/frontend/localize/languages/fr.json` | Add 5 new localization keys (English fallback) |
| `custom_components/smart_irrigation/frontend/localize/languages/nl.json` | Add 5 new localization keys (English fallback) |
| `custom_components/smart_irrigation/frontend/localize/languages/no.json` | Add 5 new localization keys (English fallback) |
| `custom_components/smart_irrigation/frontend/localize/languages/sk.json` | Add 5 new localization keys (English fallback) |
| `custom_components/smart_irrigation/frontend/src/views/zones/view-zones.ts` | Add state, icon import, button, handler, render method, and hidden section |
| `custom_components/smart_irrigation/tests/test_bucket_forecast.py` | New test file for backend calculation |

---

## Task 1: Frontend data layer — `BucketForecastDay` type and `fetchBucketForecast`

**Files:**
- Modify: `custom_components/smart_irrigation/frontend/src/types.ts` (append after line 191)
- Modify: `custom_components/smart_irrigation/frontend/src/data/websockets.ts` (append after line 175)

- [ ] **Step 1: Add `BucketForecastDay` interface to `types.ts`**

Open `custom_components/smart_irrigation/frontend/src/types.ts` and append at the end of the file (after the closing `}` of `WeatherRecord`):

```typescript
export interface BucketForecastDay {
  date: string;
  precipitation: number;
  et: number;
  drainage: number;
  delta: number;
  bucket_eod: number;
}
```

- [ ] **Step 2: Add `fetchBucketForecast` to `websockets.ts`**

Open `custom_components/smart_irrigation/frontend/src/data/websockets.ts`.

Add the import of `BucketForecastDay` at the top import block (line 7, after `WeatherRecord`):

```typescript
import {
  SmartIrrigationConfig,
  SmartIrrigationZone,
  SmartIrrigationModule,
  SmartIrrigationMapping,
  BucketForecastDay,
} from "../types";
```

Then append at the end of the file:

```typescript
// Backend API for 5-day bucket forecast for a zone
export const fetchBucketForecast = (
  hass: HomeAssistant,
  zone_id: string,
): Promise<BucketForecastDay[]> =>
  hass.callWS({
    type: DOMAIN + "/bucket_forecast",
    zone_id: zone_id,
  });
```

- [ ] **Step 3: Commit**

```bash
git add custom_components/smart_irrigation/frontend/src/types.ts \
        custom_components/smart_irrigation/frontend/src/data/websockets.ts
git commit -m "feat: add BucketForecastDay type and fetchBucketForecast websocket function"
```

---

## Task 2: Backend — `_calculate_forecast_day` method + unit tests

**Files:**
- Modify: `custom_components/smart_irrigation/__init__.py` — add method to coordinator class
- Create: `custom_components/smart_irrigation/tests/test_bucket_forecast.py`

**Context:** `_calculate_forecast_day` is a pure synchronous helper — no zone state mutations, no async. It mirrors the bucket+drainage logic in `calculate_module` (lines 1860–1897 of `__init__.py`) but:
- Does not call `max(0, ...)` on the final bucket (allows negative)
- Takes `bucket_start` as a parameter instead of reading zone state
- Takes `modinst` and `module_name` as parameters (caller looks these up once)

The drainage formula (from line 1890–1895): `drainage = drainage_rate_mm_per_hour * 24 * (bucket_after_delta / maximum_bucket) ** 4` when `bucket_after_delta > 0` and `maximum_bucket > 0`. Exponent is `(2 + 3*2) / 2 = 4` (gamma=2).

- [ ] **Step 1: Write failing tests**

Create `custom_components/smart_irrigation/tests/test_bucket_forecast.py`:

```python
"""Tests for bucket forecast calculation."""
from unittest.mock import MagicMock
import pytest

from custom_components.smart_irrigation import const


def _make_zone(bucket=20.0, maximum_bucket=50.0, drainage_rate=0.5):
    """Return a minimal zone dict for testing."""
    return {
        const.ZONE_ID: 1,
        const.ZONE_NAME: "Test Zone",
        const.ZONE_BUCKET: bucket,
        const.ZONE_MAXIMUM_BUCKET: maximum_bucket,
        const.ZONE_DRAINAGE_RATE: drainage_rate,
        const.ZONE_MODULE: 1,
    }


def _make_weatherdata(precipitation=3.0, temp=25.0):
    """Return a minimal weatherdata dict for testing."""
    return {
        const.MAPPING_PRECIPITATION: precipitation,
        const.MAPPING_TEMPERATURE: temp,
        const.MAPPING_HUMIDITY: 60.0,
        const.MAPPING_PRESSURE: 1013.0,
        const.MAPPING_WINDSPEED: 2.0,
        const.MAPPING_DEWPOINT: 15.0,
        const.MAPPING_MAX_TEMP: 28.0,
        const.MAPPING_MIN_TEMP: 18.0,
        const.MAPPING_DATA_MULTIPLIER: 1.0,
    }


class TestCalculateForecastDay:
    """Test _calculate_forecast_day coordinator method."""

    def _make_coordinator(self):
        """Return a minimal coordinator mock with the real method bound."""
        from custom_components.smart_irrigation import SmartIrrigationCoordinator
        coord = object.__new__(SmartIrrigationCoordinator)
        # Provide hass with metric units
        hass = MagicMock()
        from homeassistant.util.unit_system import METRIC_SYSTEM
        hass.config.units = METRIC_SYSTEM
        coord.hass = hass
        return coord

    def test_positive_delta_increases_bucket(self):
        """Precipitation > ET → bucket grows."""
        coord = self._make_coordinator()
        zone = _make_zone(bucket=20.0, maximum_bucket=50.0, drainage_rate=0.0)
        weatherdata = _make_weatherdata(precipitation=5.0)

        modinst = MagicMock()
        modinst.calculate.return_value = -2.0  # ET = 2mm

        result = coord._calculate_forecast_day(
            zone, modinst, "PyETO", weatherdata, bucket_start=20.0
        )

        # delta = precip - et - drainage = 5 - 2 - 0 = +3
        assert result["delta"] == pytest.approx(3.0)
        assert result["bucket_eod"] == pytest.approx(23.0)
        assert result["et"] == pytest.approx(2.0)
        assert result["precipitation"] == pytest.approx(5.0)
        assert result["drainage"] == pytest.approx(0.0)

    def test_negative_delta_decreases_bucket_below_zero(self):
        """When ET > precipitation, bucket can go negative (no lower clamp)."""
        coord = self._make_coordinator()
        zone = _make_zone(bucket=1.0, maximum_bucket=50.0, drainage_rate=0.0)
        weatherdata = _make_weatherdata(precipitation=0.0)

        modinst = MagicMock()
        modinst.calculate.return_value = -5.0  # ET = 5mm

        result = coord._calculate_forecast_day(
            zone, modinst, "PyETO", weatherdata, bucket_start=1.0
        )

        assert result["bucket_eod"] == pytest.approx(-4.0)
        assert result["delta"] == pytest.approx(-5.0)

    def test_bucket_capped_at_maximum(self):
        """Bucket cannot exceed maximum_bucket."""
        coord = self._make_coordinator()
        zone = _make_zone(bucket=48.0, maximum_bucket=50.0, drainage_rate=0.0)
        weatherdata = _make_weatherdata(precipitation=10.0)

        modinst = MagicMock()
        modinst.calculate.return_value = 0.0  # zero ET

        result = coord._calculate_forecast_day(
            zone, modinst, "PyETO", weatherdata, bucket_start=48.0
        )

        assert result["bucket_eod"] == pytest.approx(50.0)

    def test_drainage_reduces_bucket(self):
        """Drainage is applied and reduces bucket_eod."""
        coord = self._make_coordinator()
        # drainage_rate = 1.0 mm/hour → 24 mm/day at full saturation
        zone = _make_zone(bucket=50.0, maximum_bucket=50.0, drainage_rate=1.0)
        weatherdata = _make_weatherdata(precipitation=0.0)

        modinst = MagicMock()
        modinst.calculate.return_value = 0.0  # zero ET

        result = coord._calculate_forecast_day(
            zone, modinst, "PyETO", weatherdata, bucket_start=50.0
        )

        # At full saturation (bucket/max = 1.0), drainage = 1.0 * 24 * 1.0^4 = 24
        assert result["drainage"] == pytest.approx(24.0)
        assert result["bucket_eod"] == pytest.approx(26.0)

    def test_no_drainage_when_bucket_at_zero_after_delta(self):
        """Drainage is 0 when bucket_after_delta <= 0."""
        coord = self._make_coordinator()
        zone = _make_zone(bucket=0.0, maximum_bucket=50.0, drainage_rate=1.0)
        weatherdata = _make_weatherdata(precipitation=0.0)

        modinst = MagicMock()
        modinst.calculate.return_value = 0.0

        result = coord._calculate_forecast_day(
            zone, modinst, "PyETO", weatherdata, bucket_start=0.0
        )

        assert result["drainage"] == pytest.approx(0.0)

    def test_static_module_no_precipitation(self):
        """Static module: precipitation is always 0, delta comes from module only."""
        coord = self._make_coordinator()
        zone = _make_zone(bucket=20.0, maximum_bucket=50.0, drainage_rate=0.0)
        weatherdata = _make_weatherdata(precipitation=5.0)  # precip ignored for Static

        modinst = MagicMock()
        modinst.calculate.return_value = -3.0  # constant ET

        result = coord._calculate_forecast_day(
            zone, modinst, "Static", weatherdata, bucket_start=20.0
        )

        # Static: precipitation = 0, et = 3.0
        assert result["precipitation"] == pytest.approx(0.0)
        assert result["et"] == pytest.approx(3.0)
        assert result["bucket_eod"] == pytest.approx(17.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest custom_components/smart_irrigation/tests/test_bucket_forecast.py -v --no-header 2>&1 | tail -20
```

Expected: `ERRORS` — `_calculate_forecast_day` does not exist yet.

- [ ] **Step 3: Implement `_calculate_forecast_day` in `__init__.py`**

Find the class definition for the coordinator (search for `async_generate_watering_calendar` at line ~3375). Add the following method **before** `async_generate_watering_calendar`:

```python
def _calculate_forecast_day(self, zone, modinst, module_name, weatherdata, bucket_start):
    """Calculate bucket forecast for a single day without modifying zone state.

    Args:
        zone: Zone dict with configuration.
        modinst: Already-instantiated module instance.
        module_name: String name of the module ("PyETO", "Static", "Passthrough").
        weatherdata: Dict of weather values for the day.
        bucket_start: Starting bucket value in mm for this day.

    Returns:
        dict with keys: date (caller sets), precipitation, et, drainage, delta, bucket_eod.
    """
    from homeassistant.util.unit_system import METRIC_SYSTEM

    maximum_bucket = zone.get(const.ZONE_MAXIMUM_BUCKET)
    ha_config_is_metric = self.hass.config.units is METRIC_SYSTEM

    # Convert maximum_bucket to mm if HA is imperial
    if not ha_config_is_metric and maximum_bucket is not None:
        maximum_bucket = convert_between(const.UNIT_INCH, const.UNIT_MM, maximum_bucket)

    # Get drainage_rate in mm/hour
    drainage_rate = zone.get(const.ZONE_DRAINAGE_RATE, 0.0) or 0.0
    if not ha_config_is_metric:
        drainage_rate = convert_between(const.UNIT_INCH, const.UNIT_MM, drainage_rate)

    # Compute ET and precipitation based on module type
    hour_multiplier = weatherdata.get(const.MAPPING_DATA_MULTIPLIER, 1.0)
    if module_name == "PyETO":
        module_delta = modinst.calculate(weather_data=weatherdata, forecast_data=None)
        precipitation = weatherdata.get(const.MAPPING_PRECIPITATION, 0.0) or 0.0
    elif module_name == "Static":
        module_delta = modinst.calculate()
        precipitation = 0.0
    elif module_name == "Passthrough":
        et_val = weatherdata.get(const.MAPPING_EVAPOTRANSPIRATION, 0.0) or 0.0
        module_delta = 0 - modinst.calculate(et_data=et_val)
        precipitation = 0.0
    else:
        module_delta = 0.0
        precipitation = 0.0

    # et is the positive evapotranspiration demand (module_delta is negative for drying)
    et = -(module_delta * hour_multiplier)

    # Apply delta to bucket, cap at maximum
    bucket_after_delta = bucket_start + (module_delta * hour_multiplier) + precipitation
    if maximum_bucket is not None and bucket_after_delta > maximum_bucket:
        bucket_after_delta = float(maximum_bucket)

    # Drainage: only when bucket is above 0, scales with (bucket/max)^4
    drainage_per_day = drainage_rate * 24
    drainage = 0.0
    if bucket_after_delta > 0 and drainage_rate > 0:
        if maximum_bucket and maximum_bucket > 0:
            gamma = 2
            drainage = drainage_per_day * (bucket_after_delta / maximum_bucket) ** ((2 + 3 * gamma) / gamma)
        else:
            drainage = drainage_per_day

    # No lower bound — allow negative (signals irrigation is needed)
    bucket_eod = bucket_after_delta - drainage
    delta = bucket_eod - bucket_start

    return {
        "precipitation": round(precipitation, 2),
        "et": round(et, 2),
        "drainage": round(drainage, 2),
        "delta": round(delta, 2),
        "bucket_eod": round(bucket_eod, 2),
    }
```

Also ensure `convert_between` is imported at the top of `__init__.py` (it already is — check line ~257).

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest custom_components/smart_irrigation/tests/test_bucket_forecast.py -v --no-header 2>&1 | tail -20
```

Expected: all 6 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/smart_irrigation/__init__.py \
        custom_components/smart_irrigation/tests/test_bucket_forecast.py
git commit -m "feat: add _calculate_forecast_day coordinator method with tests"
```

---

## Task 3: Backend — `async_generate_bucket_forecast` method + tests

**Files:**
- Modify: `custom_components/smart_irrigation/__init__.py` — add method after `_calculate_forecast_day`
- Modify: `custom_components/smart_irrigation/tests/test_bucket_forecast.py` — add new test class

- [ ] **Step 1: Write failing tests**

Append to `custom_components/smart_irrigation/tests/test_bucket_forecast.py`:

```python
class TestAsyncGenerateBucketForecast:
    """Test async_generate_bucket_forecast coordinator method."""

    def _make_coordinator(self, forecast_data=None, zone=None):
        """Return a coordinator mock with real method bound."""
        from custom_components.smart_irrigation import SmartIrrigationCoordinator
        coord = object.__new__(SmartIrrigationCoordinator)

        hass = MagicMock()
        from homeassistant.util.unit_system import METRIC_SYSTEM
        hass.config.units = METRIC_SYSTEM
        coord.hass = hass

        # Mock weather service client
        weather_client = MagicMock()
        weather_client.get_forecast_data.return_value = forecast_data
        coord._WeatherServiceClient = weather_client

        # Mock store
        store = MagicMock()
        store.get_zone.return_value = zone
        store.get_module.return_value = {"name": "PyETO"}
        coord.store = store

        return coord

    @pytest.mark.asyncio
    async def test_returns_five_days(self):
        """Returns exactly 5 daily forecast rows when forecast has 5+ entries."""
        zone = _make_zone(bucket=20.0, maximum_bucket=50.0, drainage_rate=0.0)
        forecast_data = [_make_weatherdata(precipitation=2.0)] * 7  # 7 available days

        coord = self._make_coordinator(forecast_data=forecast_data, zone=zone)

        modinst = MagicMock()
        modinst.calculate.return_value = -3.0  # ET = 3mm/day

        async def mock_get_module(mid):
            return modinst

        coord.getModuleInstanceByID = mock_get_module
        coord.hass.async_add_executor_job = AsyncMock(return_value=forecast_data)

        result = await coord.async_generate_bucket_forecast(zone_id=1)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_bucket_accumulates_across_days(self):
        """Bucket_eod of day N becomes bucket_start of day N+1."""
        zone = _make_zone(bucket=20.0, maximum_bucket=50.0, drainage_rate=0.0)
        # Each day: precip=0, ET=5 → delta=-5, bucket decreases by 5/day
        forecast_data = [_make_weatherdata(precipitation=0.0)] * 5

        coord = self._make_coordinator(forecast_data=forecast_data, zone=zone)

        modinst = MagicMock()
        modinst.calculate.return_value = -5.0

        async def mock_get_module(mid):
            return modinst

        coord.getModuleInstanceByID = mock_get_module
        coord.hass.async_add_executor_job = AsyncMock(return_value=forecast_data)

        result = await coord.async_generate_bucket_forecast(zone_id=1)

        assert result[0]["bucket_eod"] == pytest.approx(15.0)
        assert result[1]["bucket_eod"] == pytest.approx(10.0)
        assert result[4]["bucket_eod"] == pytest.approx(-5.0)  # went negative

    @pytest.mark.asyncio
    async def test_empty_list_when_no_forecast_data(self):
        """Returns empty list when weather service returns None."""
        zone = _make_zone()
        coord = self._make_coordinator(forecast_data=None, zone=zone)

        async def mock_get_module(mid):
            return MagicMock()

        coord.getModuleInstanceByID = mock_get_module
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)

        result = await coord.async_generate_bucket_forecast(zone_id=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_dates_are_sequential_from_tomorrow(self):
        """Each row date is today+1, today+2, ... today+5."""
        from datetime import datetime, timedelta
        zone = _make_zone()
        forecast_data = [_make_weatherdata()] * 5

        coord = self._make_coordinator(forecast_data=forecast_data, zone=zone)
        modinst = MagicMock()
        modinst.calculate.return_value = 0.0

        async def mock_get_module(mid):
            return modinst

        coord.getModuleInstanceByID = mock_get_module
        coord.hass.async_add_executor_job = AsyncMock(return_value=forecast_data)

        result = await coord.async_generate_bucket_forecast(zone_id=1)

        today = datetime.now().date()
        for i, row in enumerate(result):
            expected_date = (today + timedelta(days=i + 1)).strftime("%Y-%m-%d")
            assert row["date"] == expected_date
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest custom_components/smart_irrigation/tests/test_bucket_forecast.py::TestAsyncGenerateBucketForecast -v --no-header 2>&1 | tail -20
```

Expected: `AttributeError` — `async_generate_bucket_forecast` does not exist yet.

- [ ] **Step 3: Implement `async_generate_bucket_forecast` in `__init__.py`**

Add the following method directly after `_calculate_forecast_day`:

```python
async def async_generate_bucket_forecast(self, zone_id: int):
    """Generate a 5-day bucket forecast for a zone using weather service forecast data.

    Args:
        zone_id: The ID of the zone to forecast.

    Returns:
        list: Up to 5 daily forecast dicts, each with keys:
              date, precipitation, et, drainage, delta, bucket_eod.
    """
    from datetime import datetime, timedelta
    from homeassistant.util.unit_system import METRIC_SYSTEM

    zone = self.store.get_zone(zone_id)
    if not zone:
        raise SmartIrrigationError(f"Zone {zone_id} not found")

    if not self._WeatherServiceClient:
        raise SmartIrrigationError(
            "No weather service configured — bucket forecast requires a weather service"
        )

    module_id = zone.get(const.ZONE_MODULE)
    modinst = await self.getModuleInstanceByID(module_id)
    if not modinst:
        raise SmartIrrigationError(
            f"Cannot load calculation module for zone {zone_id}"
        )

    m = self.store.get_module(module_id)
    module_name = m.get(const.MODULE_NAME) if m else "Unknown"

    forecast_data = await self.hass.async_add_executor_job(
        self._WeatherServiceClient.get_forecast_data
    )

    if not forecast_data:
        return []

    ha_config_is_metric = self.hass.config.units is METRIC_SYSTEM
    bucket_start = zone.get(const.ZONE_BUCKET, 0.0)
    if not ha_config_is_metric:
        bucket_start = convert_between(const.UNIT_INCH, const.UNIT_MM, bucket_start)

    today = datetime.now().date()
    results = []

    for i, day_data in enumerate(forecast_data[:5]):
        date_str = (today + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        # Ensure data_multiplier = 1.0 (full day)
        day_data_with_multiplier = {**day_data, const.MAPPING_DATA_MULTIPLIER: 1.0}

        day_result = self._calculate_forecast_day(
            zone, modinst, module_name, day_data_with_multiplier, bucket_start
        )
        day_result["date"] = date_str
        results.append(day_result)
        bucket_start = day_result["bucket_eod"]

    return results
```

Also ensure `const.MODULE_NAME` exists — check with:
```bash
grep -n "MODULE_NAME" custom_components/smart_irrigation/const.py
```

If not present, add to `const.py`: `MODULE_NAME = "name"`

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest custom_components/smart_irrigation/tests/test_bucket_forecast.py -v --no-header 2>&1 | tail -30
```

Expected: all 10 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/smart_irrigation/__init__.py \
        custom_components/smart_irrigation/tests/test_bucket_forecast.py
git commit -m "feat: add async_generate_bucket_forecast coordinator method with tests"
```

---

## Task 4: Backend — websocket handler and registration

**Files:**
- Modify: `custom_components/smart_irrigation/websockets.py`

- [ ] **Step 1: Add `websocket_get_bucket_forecast` handler**

Open `websockets.py`. Add the following function after `websocket_get_watering_calendar` (after line ~562):

```python
@async_response
async def websocket_get_bucket_forecast(hass: HomeAssistant, connection, msg):
    """Get 5-day bucket forecast for a zone using weather service forecast data."""
    coordinator = hass.data[const.DOMAIN]["coordinator"]
    zone_id = msg.get("zone_id")

    _LOGGER.debug("websocket_get_bucket_forecast called for zone %s", zone_id)
    try:
        if zone_id is not None:
            zone_id = int(zone_id)

        forecast = await coordinator.async_generate_bucket_forecast(zone_id)
        connection.send_result(msg["id"], forecast)

    except Exception as e:
        _LOGGER.error(
            "Error generating bucket forecast for zone %s: %s", zone_id, e
        )
        connection.send_error(msg["id"], "bucket_forecast_failed", str(e))
```

- [ ] **Step 2: Register the websocket command**

In the `async_register_websockets` function at the bottom of `websockets.py`, add after the `watering_calendar` registration block (after line ~677):

```python
    async_register_command(
        hass,
        const.DOMAIN + "/bucket_forecast",
        websocket_get_bucket_forecast,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): const.DOMAIN + "/bucket_forecast",
                vol.Required("zone_id"): vol.Coerce(str),
            }
        ),
    )
```

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
.venv/bin/python -m pytest custom_components/smart_irrigation/tests/ -v --no-header 2>&1 | tail -30
```

Expected: all tests pass including existing ones.

- [ ] **Step 4: Commit**

```bash
git add custom_components/smart_irrigation/websockets.py
git commit -m "feat: add websocket_get_bucket_forecast handler and registration"
```

---

## Task 5: Localization keys

**Files:**
- Modify: all 8 files in `custom_components/smart_irrigation/frontend/localize/languages/`

The pattern in this project: `en.json` and `it.json` have full translations; the other 6 (de, es, fr, nl, no, sk) are behind and use English as fallback. Add the new keys to all 8 files — use proper translations for en/it, English text for the rest.

- [ ] **Step 1: Add keys to `en.json`**

Open `en.json`. In the `panels.zones.actions` block (around line 288), add after `"view-watering-calendar"`:

```json
"view-bucket-forecast": "View bucket forecast"
```

The `actions` block should now look like:

```json
"actions": {
  "add": "Add",
  "calculate": "Calculate",
  "information": "Information",
  "update": "Update",
  "reset-bucket": "Reset bucket",
  "view-weather-info": "View weather data",
  "view-weather-info-message": "Weather data available for",
  "view-watering-calendar": "View watering calendar",
  "view-bucket-forecast": "View bucket forecast"
},
```

Then add a new `bucket-forecast` block inside `panels.zones` (after the `actions` block closing `}`):

```json
"bucket-forecast": {
  "title": "5-Day Bucket Forecast",
  "weather-service-note": "Based on weather service forecast data only — not on the configured sensor group",
  "no-data": "No forecast data available",
  "starting-bucket": "Starting bucket"
}
```

- [ ] **Step 2: Add keys to `it.json`**

Open `it.json`. In `panels.zones.actions`, add after `"view-watering-calendar"`:

```json
"view-bucket-forecast": "Visualizza previsione secchio"
```

Add inside `panels.zones`:

```json
"bucket-forecast": {
  "title": "Previsione secchio 5 giorni",
  "weather-service-note": "Basato solo sui dati previsionali del servizio meteo — non sul gruppo di sensori configurato",
  "no-data": "Nessun dato di previsione disponibile",
  "starting-bucket": "Secchio iniziale"
}
```

- [ ] **Step 3: Add English fallback keys to de.json, es.json, fr.json, nl.json, no.json, sk.json**

Each of these files is missing `view-watering-calendar` and other recent keys. For each file, find the `panels.zones.actions` block (search for `"reset-bucket"`) and add after it:

```json
"view-bucket-forecast": "View bucket forecast"
```

Then add inside `panels.zones` (after the `actions` block):

```json
"bucket-forecast": {
  "title": "5-Day Bucket Forecast",
  "weather-service-note": "Based on weather service forecast data only — not on the configured sensor group",
  "no-data": "No forecast data available",
  "starting-bucket": "Starting bucket"
}
```

Apply this to: `de.json`, `es.json`, `fr.json`, `nl.json`, `no.json`, `sk.json` — all get identical English-text values.

- [ ] **Step 4: Commit**

```bash
git add custom_components/smart_irrigation/frontend/localize/languages/
git commit -m "feat: add bucket forecast localization keys to all 8 language files"
```

---

## Task 6: Frontend — zones view wiring

**Files:**
- Modify: `custom_components/smart_irrigation/frontend/src/views/zones/view-zones.ts`

This task has several sub-steps. Do them all before committing.

- [ ] **Step 1: Add `mdiChartLine` import**

On line 16 (after `mdiCalendar`), add `mdiChartLine` to the MDI import:

```typescript
import {
  mdiInformationOutline,
  mdiDelete,
  mdiCalculator,
  mdiUpdate,
  mdiPailRemove,
  mdiCloudOutline,
  mdiCalendar,
  mdiChartLine,
} from "@mdi/js";
```

- [ ] **Step 2: Add `fetchBucketForecast` to the websockets import**

On line 30–32, extend the websockets imports to include `fetchBucketForecast`:

```typescript
import {
  deleteZone,
  fetchConfig,
  fetchZones,
  saveZone,
  calculateZone,
  updateZone,
  fetchModules,
  fetchMappings,
  calculateAllZones,
  updateAllZones,
  resetAllBuckets,
  clearAllWeatherdata,
  fetchWateringCalendar,
  fetchMappingWeatherRecords,
  fetchBucketForecast,
} from "../../data/websockets";
```

- [ ] **Step 3: Add `BucketForecastDay` to the types import**

On line 35–42, extend the types imports:

```typescript
import {
  SmartIrrigationConfig,
  SmartIrrigationZone,
  SmartIrrigationZoneState,
  SmartIrrigationModule,
  SmartIrrigationMapping,
  WeatherRecord,
  BucketForecastDay,
} from "../../types";
```

- [ ] **Step 4: Add `bucketForecasts` state property**

After the `wateringCalendars` property declaration (line ~78), add:

```typescript
  @property({ type: Map })
  private bucketForecasts = new Map<number, BucketForecastDay[]>();
```

- [ ] **Step 5: Add `handleViewBucketForecast` handler method**

Add the following method after `handleViewWateringCalendar` (after line ~455):

```typescript
  private async handleViewBucketForecast(index: number): Promise<void> {
    const zone = this.zones[index];
    if (!zone || zone.id == undefined) {
      return;
    }

    const selector = `#forecast-section-${zone.id}`;
    const forecastSection = this.shadowRoot?.querySelector(selector);

    if (forecastSection) {
      if (forecastSection.hasAttribute("hidden")) {
        // Fetch on first open only
        if (!this.bucketForecasts.has(zone.id)) {
          try {
            const forecast = await fetchBucketForecast(
              this.hass!,
              zone.id.toString(),
            );
            this.bucketForecasts.set(zone.id, forecast);
            this._scheduleUpdate();
          } catch (error) {
            console.error(
              `Failed to fetch bucket forecast for zone ${zone.id}:`,
              error,
            );
            this.bucketForecasts.set(zone.id, []);
            this._scheduleUpdate();
          }
        }
        forecastSection.removeAttribute("hidden");
      } else {
        forecastSection.setAttribute("hidden", "");
      }
    }
  }
```

- [ ] **Step 6: Add `renderBucketForecast` render method**

Add the following method after `renderWateringCalendar` (after line ~668):

```typescript
  private renderBucketForecast(zone: SmartIrrigationZone): TemplateResult {
    if (!this.hass || typeof zone.id !== "number") {
      return html``;
    }

    const forecastDays = this.bucketForecasts.get(zone.id) || [];

    return html`
      <div class="bucket-forecast">
        <h4>
          ${localize(
            "panels.zones.bucket-forecast.title",
            this.hass.language,
          )}
        </h4>
        <div class="forecast-note">
          ${localize(
            "panels.zones.bucket-forecast.weather-service-note",
            this.hass.language,
          )}
        </div>
        ${forecastDays.length === 0
          ? html`
              <div class="forecast-empty">
                ${localize(
                  "panels.zones.bucket-forecast.no-data",
                  this.hass.language,
                )}
              </div>
            `
          : html`
              <div class="forecast-table">
                <div class="forecast-header">
                  <span>Date</span>
                  <span>Precipitation (mm)</span>
                  <span>ET (mm)</span>
                  <span>Drainage (mm)</span>
                  <span>Delta (mm)</span>
                  <span>Bucket EOD (mm)</span>
                </div>
                ${forecastDays.map(
                  (day) => html`
                    <div class="forecast-row">
                      <span>${day.date}</span>
                      <span>${day.precipitation.toFixed(1)}</span>
                      <span>${day.et.toFixed(1)}</span>
                      <span>${day.drainage.toFixed(1)}</span>
                      <span
                        style="color: ${day.delta >= 0 ? "#2e7d32" : "#c62828"}"
                        >${day.delta >= 0 ? "+" : ""}${day.delta.toFixed(1)}</span
                      >
                      <span
                        style="color: ${day.bucket_eod < 0 ? "#c62828" : "inherit"}"
                        >${day.bucket_eod.toFixed(1)}</span
                      >
                    </div>
                  `,
                )}
              </div>
              <div class="forecast-info">
                ${localize(
                  "panels.zones.bucket-forecast.starting-bucket",
                  this.hass.language,
                )}:
                ${Number(zone.bucket).toFixed(1)} mm |
                Max: ${Number(zone.maximum_bucket).toFixed(1)} mm |
                Drainage rate: ${Number(zone.drainage_rate).toFixed(2)} mm/h
              </div>
            `}
      </div>
    `;
  }
```

- [ ] **Step 7: Add the bucket forecast button in `renderZone`**

In `renderZone`, after the `calendar_button_to_show` block (around line 822), add:

```typescript
      let forecast_button_to_show;
      if (
        this.config?.use_weather_service === true &&
        zone.module !== undefined
      ) {
        forecast_button_to_show = html` <div
          class="action-button-right"
          @click="${() => this.handleViewBucketForecast(index)}"
        >
          <span class="action-button-label">
            ${localize(
              "panels.zones.actions.view-bucket-forecast",
              this.hass.language,
            )}
          </span>
          <svg style="width:24px;height:24px" viewBox="0 0 24 24">
            <path fill="#404040" d="${mdiChartLine}" />
          </svg>
        </div>`;
      }
```

- [ ] **Step 8: Add the button to the action-buttons-right div**

In `renderZone`, inside the `action-buttons-right` div (around line 1194–1199), add `${forecast_button_to_show}` before `${delete_button_to_show}`:

```typescript
              <div class="action-buttons-right">
                ${reset_bucket_button_to_show}
                ${weather_info_button_to_show}
                ${calendar_button_to_show}
                ${forecast_button_to_show}
                ${delete_button_to_show}
              </div>
```

- [ ] **Step 9: Add the hidden forecast section in `renderZone`**

After the `calendar-section` div (line ~1208–1210), add:

```typescript
            <div id="forecast-section-${zone.id}" hidden>
              ${this.renderBucketForecast(zone)}
            </div>
```

- [ ] **Step 10: Add CSS for forecast table**

Open `view-zones.ts`, find `static get styles()` at line 1399. Inside the `css\`` template (after `${globalStyle}`), add styles for the new forecast elements:

```css
.bucket-forecast {
  margin-top: 8px;
}
.forecast-note {
  font-size: 12px;
  color: #e65100;
  background: #fff3e0;
  padding: 6px 8px;
  border-radius: 4px;
  border-left: 3px solid #ff9800;
  margin-bottom: 8px;
}
.forecast-table {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  font-size: 13px;
  border: 1px solid var(--divider-color, #e0e0e0);
  border-radius: 4px;
  overflow: hidden;
}
.forecast-header {
  display: contents;
}
.forecast-header span {
  background: var(--primary-color-light, #e3f2fd);
  padding: 6px 8px;
  font-weight: bold;
  border-bottom: 1px solid var(--divider-color, #e0e0e0);
}
.forecast-row {
  display: contents;
}
.forecast-row span {
  padding: 6px 8px;
  border-bottom: 1px solid var(--secondary-background-color, #f0f0f0);
}
.forecast-info {
  font-size: 11px;
  color: var(--secondary-text-color, #757575);
  margin-top: 6px;
}
.forecast-empty {
  font-size: 13px;
  color: var(--secondary-text-color, #757575);
  padding: 8px 0;
}
```

- [ ] **Step 11: Build the frontend**

```bash
cd custom_components/smart_irrigation/frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 12: Commit**

```bash
git add custom_components/smart_irrigation/frontend/src/views/zones/view-zones.ts
git commit -m "feat: add bucket forecast button, handler, and render section to zones view"
```

---

## Task 7: End-to-end verification

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest custom_components/smart_irrigation/tests/ -v --no-header 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 2: Manual verification checklist**

In a running Home Assistant instance with the integration loaded:

1. Open the Smart Irrigation zones page
2. **Zone with weather service enabled + module configured:** "View bucket forecast" button is visible
3. **Zone with no module:** "View bucket forecast" button is NOT visible
4. **When weather service is disabled in general config:** button is NOT visible on any zone
5. Click "View bucket forecast" → table expands below the action buttons
6. Table shows 5 rows with dates starting from tomorrow
7. Delta column: negative values are red, positive are green
8. Negative bucket_eod values are shown in red
9. Click button again → table collapses
10. Warning note is visible above the table
11. Footer shows starting bucket, max bucket, drainage rate

- [ ] **Step 3: Final commit if any fixups were needed**

```bash
git add -p
git commit -m "fix: bucket forecast UI fixups from manual verification"
```
