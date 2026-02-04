"""Tests for Pydantic models.

Tests validate models against the actual API response structure in
wheather-api-response.json to ensure compatibility.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from tomorrow.models import (
    TimelineValues,
    TimelineEntry,
    TimelinesResponse,
    Location,
    WeatherReading,
    LocationSummary,
)


# Load the actual API response for testing
@pytest.fixture(scope="module")
def api_response_json():
    """Load the actual API response JSON file."""
    api_response_path = Path(__file__).parent.parent / "wheather-api-response.json"
    with open(api_response_path) as f:
        return json.load(f)


class TestTimelineValues:
    """Tests for TimelineValues model."""

    def test_create_with_all_fields(self):
        """Should create TimelineValues with all fields."""
        values = TimelineValues(
            temperature=25.5,
            temperature_apparent=28.0,
            wind_speed=5.2,
            wind_gust=8.5,
            wind_direction=180,
            humidity=65.0,
            dew_point=18.5,
            cloud_cover=25.0,
            cloud_base=7.1,
            cloud_ceiling=7.1,
            visibility=16.0,
            precipitation_probability=20.0,
            rain_intensity=0.5,
            pressure_sea_level=1015.5,
            pressure_surface_level=1013.2,
            weather_code=1000,
            uv_index=5,
        )

        assert values.temperature == 25.5
        assert values.wind_speed == 5.2
        assert values.humidity == 65.0

    def test_create_with_minimal_fields(self):
        """Should create TimelineValues with only required fields (all optional)."""
        values = TimelineValues()

        assert values.temperature is None
        assert values.wind_speed is None
        assert values.humidity is None

    def test_alias_mapping(self):
        """Should correctly map camelCase aliases to snake_case attributes."""
        data = {
            "temperature": 25.5,
            "temperatureApparent": 28.0,
            "windSpeed": 5.2,
            "windGust": 8.5,
            "windDirection": 180,
            "humidity": 65.0,
            "dewPoint": 18.5,
            "cloudCover": 25.0,
            "cloudBase": 7.1,
            "cloudCeiling": 7.1,
            "visibility": 16.0,
            "precipitationProbability": 20.0,
            "pressureSeaLevel": 1015.5,
            "pressureSurfaceLevel": 1013.2,
            "weatherCode": 1000,
            "uvIndex": 5,
        }

        values = TimelineValues.model_validate(data)

        assert values.temperature == 25.5
        assert values.temperature_apparent == 28.0
        assert values.wind_speed == 5.2
        assert values.wind_gust == 8.5
        assert values.precipitation_probability == 20.0
        assert values.weather_code == 1000
        assert values.uv_index == 5

    def test_none_values_accepted(self):
        """Should accept None values for optional fields."""
        data = {
            "temperature": None,
            "cloudBase": None,
            "cloudCeiling": None,
        }

        values = TimelineValues.model_validate(data)
        assert values.temperature is None
        assert values.cloud_base is None
        assert values.cloud_ceiling is None

    def test_parse_from_api_response(self, api_response_json):
        """Should parse actual API response values."""
        # Get first minutely entry's values
        minutely_data = api_response_json["timelines"]["minutely"][0]["values"]

        values = TimelineValues.model_validate(minutely_data)

        assert values.temperature is not None
        assert values.wind_speed is not None
        assert values.humidity is not None
        assert isinstance(values.weather_code, int)


class TestTimelineEntry:
    """Tests for TimelineEntry model."""

    def test_create_timeline_entry(self):
        """Should create TimelineEntry with time and values."""
        entry = TimelineEntry(
            time="2024-01-01T12:00:00Z", values={"temperature": 25.5, "humidity": 65.0}
        )

        assert isinstance(entry.time, datetime)
        assert entry.time.hour == 12
        assert entry.values.temperature == 25.5
        assert entry.values.humidity == 65.0

    def test_parse_from_api_response(self, api_response_json):
        """Should parse actual API response entry."""
        minutely_entry = api_response_json["timelines"]["minutely"][0]

        entry = TimelineEntry.model_validate(minutely_entry)

        assert isinstance(entry.time, datetime)
        assert isinstance(entry.values, TimelineValues)
        assert entry.values.temperature is not None


class TestTimelinesResponse:
    """Tests for TimelinesResponse model."""

    def test_create_timelines_response(self):
        """Should create TimelinesResponse with timelines."""
        response = TimelinesResponse(
            timelines={
                "hourly": [
                    {"time": "2024-01-01T12:00:00Z", "values": {"temperature": 25.5}}
                ]
            }
        )

        assert "hourly" in response.timelines
        assert len(response.timelines["hourly"]) == 1
        assert response.timelines["hourly"][0].values.temperature == 25.5

    def test_parse_from_api_response(self, api_response_json):
        """Should parse actual full API response."""
        response = TimelinesResponse.model_validate(api_response_json)

        assert "minutely" in response.timelines
        assert "hourly" in response.timelines
        assert isinstance(response.timelines["minutely"], list)
        assert isinstance(response.timelines["hourly"], list)

        # Check first entry
        if response.timelines["minutely"]:
            entry = response.timelines["minutely"][0]
            assert isinstance(entry.time, datetime)
            assert isinstance(entry.values, TimelineValues)


class TestLocation:
    """Tests for Location model."""

    def test_create_location(self):
        """Should create Location with all fields."""
        location = Location(
            id=1,
            lat=25.8600,
            lon=-97.4200,
            name="Test Location",
            is_active=True,
        )

        assert location.id == 1
        assert location.lat == 25.8600
        assert location.lon == -97.4200
        assert location.name == "Test Location"
        assert location.is_active is True

    def test_location_equality(self):
        """Should correctly compare locations by coordinates."""
        loc1 = Location(id=1, lat=25.8600, lon=-97.4200)
        loc2 = Location(id=2, lat=25.8600, lon=-97.4200)
        loc3 = Location(id=3, lat=25.9000, lon=-97.5200)

        assert loc1 == loc2
        assert loc1 != loc3
        assert hash(loc1) == hash(loc2)

    def test_location_in_set(self):
        """Should work correctly in sets."""
        loc1 = Location(id=1, lat=25.8600, lon=-97.4200)
        loc2 = Location(id=2, lat=25.8600, lon=-97.4200)  # Same coords
        loc3 = Location(id=3, lat=25.9000, lon=-97.5200)  # Different coords

        location_set = {loc1, loc2, loc3}

        # loc1 and loc2 are equal, so set should have 2 items
        assert len(location_set) == 2


class TestWeatherReading:
    """Tests for WeatherReading model."""

    def test_create_weather_reading(self):
        """Should create WeatherReading with all fields."""
        reading = WeatherReading(
            location_id=1,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            temperature=25.5,
            wind_speed=5.2,
            humidity=65.0,
            data_granularity="hourly",
        )

        assert reading.location_id == 1
        assert reading.temperature == 25.5
        assert reading.data_granularity == "hourly"

    def test_weather_reading_optional_fields(self):
        """Should accept None for optional weather fields."""
        reading = WeatherReading(
            location_id=1,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            data_granularity="hourly",
        )

        assert reading.temperature is None
        assert reading.wind_speed is None
        assert reading.humidity is None

    def test_invalid_granularity(self):
        """Should reject invalid granularity values."""
        with pytest.raises(ValidationError):
            WeatherReading(
                location_id=1,
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                data_granularity="invalid",  # Invalid value
            )

    def test_from_timeline_entry(self):
        """Should create WeatherReading from TimelineEntry."""
        timeline_entry = TimelineEntry(
            time="2024-01-01T12:00:00Z",
            values={
                "temperature": 25.5,
                "windSpeed": 5.2,
                "humidity": 65.0,
            },
        )

        reading = WeatherReading.from_timeline_entry(
            entry=timeline_entry, location_id=1, granularity="hourly"
        )

        assert reading.location_id == 1
        assert reading.temperature == 25.5
        assert reading.wind_speed == 5.2
        assert reading.humidity == 65.0
        assert reading.data_granularity == "hourly"
        assert reading.timestamp == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_from_timeline_entry_with_none_values(self):
        """Should handle None values when converting from TimelineEntry."""
        timeline_entry = TimelineEntry(
            time="2024-01-01T12:00:00Z",
            values={},  # All None
        )

        reading = WeatherReading.from_timeline_entry(
            entry=timeline_entry, location_id=1, granularity="hourly"
        )

        assert reading.location_id == 1
        assert reading.temperature is None
        assert reading.wind_speed is None
        assert reading.data_granularity == "hourly"


class TestLocationSummary:
    """Tests for LocationSummary model."""

    def test_create_location_summary(self):
        """Should create LocationSummary."""
        summary = LocationSummary(
            location_id=1,
            lat=25.8600,
            lon=-97.4200,
            name="Test Location",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            temperature=25.5,
            wind_speed=5.2,
            humidity=65.0,
        )

        assert summary.location_id == 1
        assert summary.lat == 25.8600
        assert summary.lon == -97.4200
        assert summary.temperature == 25.5


class TestModelIntegration:
    """Integration tests for model interactions."""

    def test_full_api_to_db_workflow(self, api_response_json):
        """Test complete workflow from API response to DB model."""
        # Parse API response
        response = TimelinesResponse.model_validate(api_response_json)

        # Get hourly data
        hourly_entries = response.timelines.get("hourly", [])

        if hourly_entries:
            # Convert first entry to WeatherReading
            entry = hourly_entries[0]
            reading = WeatherReading.from_timeline_entry(
                entry=entry, location_id=1, granularity="hourly"
            )

            # Verify conversion
            assert reading.location_id == 1
            assert reading.data_granularity == "hourly"
            assert isinstance(reading.timestamp, datetime)

            # At least some fields should have values
            has_some_data = (
                reading.temperature is not None
                or reading.wind_speed is not None
                or reading.humidity is not None
            )
            assert has_some_data, "WeatherReading should have some data from API"


class TestModelValidation:
    """Tests for model validation edge cases."""

    def test_timeline_values_extra_fields_ignored(self):
        """Should ignore extra fields in TimelineValues."""
        data = {
            "temperature": 25.5,
            "unknownField": "should be ignored",
            "anotherUnknown": 123,
        }

        # Should not raise an error
        values = TimelineValues.model_validate(data)
        assert values.temperature == 25.5
        assert not hasattr(values, "unknownField")

    def test_datetime_parsing(self):
        """Should parse various datetime formats."""
        # ISO 8601 with Z
        entry1 = TimelineEntry(time="2024-01-01T12:00:00Z", values={})
        assert entry1.time.year == 2024

        # ISO 8601 with timezone
        entry2 = TimelineEntry(time="2024-01-01T12:00:00+00:00", values={})
        assert entry2.time.year == 2024

        # ISO 8601 without timezone
        entry3 = TimelineEntry(time="2024-01-01T12:00:00", values={})
        assert entry3.time.year == 2024

    def test_numeric_types(self):
        """Should accept various numeric types."""
        values = TimelineValues(
            temperature=25,  # int instead of float
            humidity=65,  # int instead of float
            wind_direction=180,  # int
        )

        assert values.temperature == 25.0
        assert values.humidity == 65.0
        assert values.wind_direction == 180
