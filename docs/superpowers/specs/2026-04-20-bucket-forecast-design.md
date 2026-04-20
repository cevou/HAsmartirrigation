# 5-Day Bucket Forecast per Zone

**Date:** 2026-04-20  
**Branch:** feat/forecast-prediction

## Overview

Add a "Bucket Forecast" button to each zone card on the zones page. When clicked, it expands an inline table showing the estimated bucket value at the end of each of the next 5 days, calculated using weather service forecast data and the zone's configured module. A warning note makes clear this is based on weather service data only, not the configured sensor group.

## Goals

- Let users see how the bucket will develop over the next 5 days without resetting/watering
- Surface negative bucket values so users can estimate when irrigation is needed
- Follow existing UI patterns (same toggle-section pattern as Watering Calendar and Weather Info)

## Architecture

**Approach:** New backend websocket endpoint `smart_irrigation/bucket_forecast`, mirroring `/watering_calendar`. Frontend fetches lazily on first open and caches per zone in memory.

## Backend

### New websocket handler: `websocket_get_bucket_forecast`

**File:** `custom_components/smart_irrigation/websockets.py`

Registered as `smart_irrigation/bucket_forecast`, schema: `{ type, zone_id }`.

**Logic (`__init__.py`):**

Two new methods:

**`_calculate_forecast_day(zone, weatherdata, bucket_start)`** — pure calculation, no zone state changes:
1. Call `modinst.calculate(weather_data=weatherdata, forecast_data=None)` to get the daily delta (ET deficiency)
2. Apply delta to bucket: `bucket_after_delta = min(bucket_start + delta, maximum_bucket)`
3. Calculate drainage (mirrors existing logic in `calculate_module`):
   - `drainage_rate` is in mm/hour; `drainage_per_day = drainage_rate * 24`
   - If `bucket_after_delta > 0` and `maximum_bucket > 0`: scale by `(bucket_after_delta / maximum_bucket)^4`
   - If `bucket_after_delta <= 0`: drainage = 0
4. `bucket_eod = bucket_after_delta - drainage` — **no `max(0, ...)` clamp, allow negative**
5. Return `{delta, drainage, bucket_eod}`

**`async_generate_bucket_forecast(zone_id)`**:
1. Load zone from store by `zone_id`
2. Get module instance via `getModuleInstanceByID(zone.module)`
3. Call `self._WeatherServiceClient.get_forecast_data()` to get up to 5 days of daily forecast
4. For each of the 5 forecast days:
   - Build `weatherdata` dict from forecast day fields (temperature, humidity, precipitation, pressure, wind_speed, dewpoint, max_temp, min_temp)
   - Call `_calculate_forecast_day(zone, weatherdata, bucket_start)`
   - Extract precipitation from forecast day
   - Set `bucket_start = result.bucket_eod` for next iteration
5. Return list of 5 daily objects (see Data Contract below)

**Error handling:**
- Weather service not configured → raise error (button is hidden on frontend when `use_weather_service=False`, but defend anyway)
- No forecast data from weather service → return empty list
- Zone not found → raise error

### Data Contract (backend → frontend, one object per day)

```json
{
  "date": "2026-04-21",
  "precipitation": 3.2,
  "et": 4.1,
  "drainage": 0.3,
  "delta": -1.2,
  "bucket_eod": 18.8
}
```

All values in mm. `bucket_eod` is clamped to `maximum_bucket` above, unbounded below (negative = irrigation needed). `drainage` is the actual calculated value for that day — it scales with `(bucket / maximum_bucket)^4` so it varies as the bucket changes, and is 0 when `bucket_after_delta <= 0`.

## Frontend

### `websockets.ts`

Add:

```typescript
export const fetchBucketForecast = (
  hass: HomeAssistant,
  zone_id: string,
): Promise<BucketForecastDay[]> =>
  hass.callWS({
    type: DOMAIN + "/bucket_forecast",
    zone_id: zone_id,
  });
```

Add interface to `types.ts`:

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

### `view-zones.ts`

**New state property:**
```typescript
private bucketForecasts = new Map<number, BucketForecastDay[]>();
```

**New button** (right side of action-buttons, alongside calendar/weather buttons):  
Condition: `this.config?.use_weather_service === true && zone.module !== undefined`  
Label: "Bucket Forecast" with chart icon (`mdiChartLine` or similar)

**New handler `handleViewBucketForecast(index)`:**
- On first open: call `fetchBucketForecast(this.hass, zone.id.toString())`, store in `bucketForecasts`
- Toggle `#forecast-section-${zone.id}` hidden attribute (same pattern as calendar/weather sections)

**New render method `renderBucketForecast(zone)`:**
- Warning banner: "Based on weather service forecast data only — not on the configured sensor group"
- Table columns: Date | Precipitation (mm) | ET (mm) | Drainage (mm) | Delta (mm) | Bucket EOD (mm)
- Delta column: color red when negative, green when positive
- Footer line: "Starting bucket: X mm | Maximum bucket: Y mm | Drainage: Z mm/day"
- Empty state: "No forecast data available" when list is empty

**New hidden section in `renderZone()`:**
```html
<div id="forecast-section-${zone.id}" hidden>
  ${this.renderBucketForecast(zone)}
</div>
```

## Visibility Rules

| Condition | Button shown |
|-----------|-------------|
| `use_weather_service === false` | No |
| `zone.module === undefined` | No |
| Both true | Yes |

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| No forecast data from weather service | Show "No forecast data available" |
| Bucket goes negative | Display as-is — signals irrigation is needed |
| Bucket exceeds maximum_bucket | Clamp to maximum_bucket |
| Zone has no module | Button hidden |
| Weather service not configured | Button hidden |

## Localization

New localization keys needed:
- `panels.zones.actions.view-bucket-forecast` — button label
- `panels.zones.bucket-forecast.title` — section heading
- `panels.zones.bucket-forecast.weather-service-note` — warning banner text
- `panels.zones.bucket-forecast.no-data` — empty state message
- `panels.zones.bucket-forecast.starting-bucket` — footer label
