"""Tests for bucket forecast calculation."""
from unittest.mock import AsyncMock, MagicMock
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
