"""End-to-End tests for Tomorrow.io Weather Data Pipeline.

These tests verify the complete data flow:
1. Database setup with migrations
2. API client fetching data
3. ETL pipeline processing
4. Data verification in database

These are integration tests that require a running database.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Set required environment variables for tests
os.environ.setdefault("TOMORROW_API_KEY", "test_api_key_for_tests")
os.environ.setdefault("PGPASSWORD", "postgres")

from tomorrow.db import health_check

# Skip all E2E tests if database is not available
try:
    if not health_check():
        pytest.skip("Database not available", allow_module_level=True)
except Exception:
    pytest.skip("Database not available", allow_module_level=True)

from tomorrow.client import TomorrowClient
from tomorrow.db import (
    get_active_locations,
    get_cursor,
    insert_readings,
)
from tomorrow.etl import run_etl_pipeline
from tomorrow.models import Location, WeatherReading

pytestmark = pytest.mark.integration


@pytest.fixture
def clean_weather_data():
    """Clean up weather data before and after tests."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM weather_data")
    yield
    with get_cursor() as cur:
        cur.execute("DELETE FROM weather_data")


class TestDatabaseConnectivity:
    """E2E tests for database connectivity."""

    def test_health_check_success(self):
        """Should verify database is reachable."""
        result = health_check()
        assert result is True

    def test_get_active_locations_returns_data(self):
        """Should retrieve locations from database."""
        locations = get_active_locations()

        assert len(locations) == 10
        assert all(isinstance(loc, Location) for loc in locations)
        assert all(loc.is_active for loc in locations)


class TestETLPipelineIntegration:
    """E2E tests for ETL pipeline with mocked API."""

    @pytest.fixture
    def mock_api_response(self):
        """Create a mock API response for testing."""
        return {
            "data": {
                "timelines": [
                    {
                        "timestep": "1h",
                        "startTime": "2024-01-15T12:00:00Z",
                        "endTime": "2024-01-15T14:00:00Z",
                        "intervals": [
                            {
                                "startTime": "2024-01-15T12:00:00Z",
                                "values": {
                                    "temperature": 22.5,
                                    "temperatureApparent": 21.0,
                                    "windSpeed": 5.2,
                                    "windGust": 8.1,
                                    "windDirection": 180,
                                    "humidity": 65.0,
                                    "dewPoint": 15.5,
                                    "cloudCover": 20.0,
                                    "visibility": 10.0,
                                    "precipitationProbability": 10.0,
                                    "pressureSeaLevel": 1013.0,
                                    "pressureSurfaceLevel": 1012.0,
                                    "weatherCode": 1000,
                                    "uvIndex": 5,
                                },
                            },
                            {
                                "startTime": "2024-01-15T13:00:00Z",
                                "values": {
                                    "temperature": 23.0,
                                    "temperatureApparent": 22.0,
                                    "windSpeed": 5.5,
                                    "windGust": 8.5,
                                    "windDirection": 185,
                                    "humidity": 63.0,
                                    "dewPoint": 15.8,
                                    "cloudCover": 25.0,
                                    "visibility": 10.0,
                                    "precipitationProbability": 15.0,
                                    "pressureSeaLevel": 1012.0,
                                    "pressureSurfaceLevel": 1011.0,
                                    "weatherCode": 1000,
                                    "uvIndex": 6,
                                },
                            },
                        ]
                    }
                ]
            }
        }

    def test_full_etl_pipeline(
        self,
        clean_weather_data,
        mock_api_response,
    ):
        """Should run complete ETL pipeline and store data."""
        # Get first location
        locations = get_active_locations()
        test_location = locations[0]

        # Create mock client with proper response structure
        mock_client = MagicMock(spec=TomorrowClient)

        # Create proper mock response that matches TimelinesResponse structure
        from tomorrow.models import (
            TimelinesResponse, 
            TimelinesData, 
            Timeline, 
            TimelineInterval, 
            TimelineValues
        )

        mock_response = TimelinesResponse(
            data=TimelinesData(
                timelines=[
                    Timeline(
                        timestep="1h",
                        startTime=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                        endTime=datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
                        intervals=[
                            TimelineInterval(
                                startTime=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                                values=TimelineValues(
                                    temperature=22.5,
                                    temperature_apparent=21.0,
                                    wind_speed=5.2,
                                    wind_gust=8.1,
                                    wind_direction=180,
                                    humidity=65.0,
                                    dew_point=15.5,
                                    cloud_cover=20.0,
                                    visibility=10.0,
                                    precipitation_probability=10.0,
                                    pressure_sea_level=1013.0,
                                    pressure_surface_level=1012.0,
                                    weather_code=1000,
                                    uv_index=5,
                                ),
                            ),
                            TimelineInterval(
                                startTime=datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc),
                                values=TimelineValues(
                                    temperature=23.0,
                                    temperature_apparent=22.0,
                                    wind_speed=5.5,
                                    wind_gust=8.5,
                                    wind_direction=185,
                                    humidity=63.0,
                                    dew_point=15.8,
                                    cloud_cover=25.0,
                                    visibility=10.0,
                                    precipitation_probability=15.0,
                                    pressure_sea_level=1012.0,
                                    pressure_surface_level=1011.0,
                                    weather_code=1000,
                                    uv_index=6,
                                ),
                            ),
                        ]
                    )
                ]
            )
        )
        mock_client.fetch_weather.return_value = mock_response

        # Run pipeline with mocked client
        result = run_etl_pipeline(
            client=mock_client,
            locations=[test_location],
            granularity="hourly",
        )

        # Verify result
        assert result.success is True
        assert result.locations_processed == 1
        assert result.readings_inserted == 2

        # Verify data in database
        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as count FROM weather_data WHERE location_id = %s",
                (test_location.id,),
            )
            count = cur.fetchone()["count"]
            assert count == 2

            cur.execute(
                "SELECT temperature FROM weather_data WHERE location_id = %s ORDER BY timestamp",
                (test_location.id,),
            )
            rows = cur.fetchall()
            assert rows[0]["temperature"] == 22.5
            assert rows[1]["temperature"] == 23.0


class TestDataIntegrity:
    """E2E tests for data integrity."""

    def test_upsert_prevents_duplicates(self, clean_weather_data):
        """Should prevent duplicate entries via upsert."""
        locations = get_active_locations()
        test_location = locations[0]

        # Insert same reading twice
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            WeatherReading(
                location_id=test_location.id,
                timestamp=base_time,
                temperature=22.5,
                data_granularity="hourly",
            ),
        ]

        # First insert
        count1 = insert_readings(readings)
        assert count1 == 1

        # Second insert (should update, not error)
        readings[0].temperature = 25.0
        count2 = insert_readings(readings)
        assert count2 == 1

        # Verify only one record with updated value
        with get_cursor() as cur:
            cur.execute(
                "SELECT temperature FROM weather_data WHERE location_id = %s",
                (test_location.id,),
            )
            rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0]["temperature"] == 25.0

    def test_foreign_key_constraint(self):
        """Should enforce foreign key constraints."""
        with pytest.raises(Exception):
            with get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO weather_data (location_id, timestamp, data_granularity)
                    VALUES (99999, NOW(), 'hourly')
                    """
                )


class TestAssignmentQueriesE2E:
    """E2E tests for assignment-required SQL queries."""

    def test_latest_readings_query(self, clean_weather_data):
        """Should retrieve latest readings per location."""
        locations = get_active_locations()[:3]  # Test with first 3 locations

        # Insert test data with different timestamps
        base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        for i, location in enumerate(locations):
            readings = [
                WeatherReading(
                    location_id=location.id,
                    timestamp=base_time - timedelta(hours=1),
                    temperature=20.0 + i,
                    wind_speed=5.0 + i,
                    data_granularity="hourly",
                ),
                WeatherReading(
                    location_id=location.id,
                    timestamp=base_time,
                    temperature=22.0 + i,
                    wind_speed=7.0 + i,
                    data_granularity="hourly",
                ),
            ]
            insert_readings(readings)

        # Query latest readings
        from tomorrow.db import get_latest_by_location

        latest = get_latest_by_location()

        # Should have entries for our test locations
        location_ids = {loc.id for loc in locations}
        latest_for_test = [r for r in latest if r.location_id in location_ids]

        assert len(latest_for_test) == 3

        # Verify latest values
        for i, location in enumerate(locations):
            loc_latest = next(
                r for r in latest_for_test if r.location_id == location.id
            )
            assert loc_latest.temperature == 22.0 + i
            assert loc_latest.wind_speed == 7.0 + i

    def test_time_series_query(self, clean_weather_data):
        """Should retrieve time series data."""
        locations = get_active_locations()
        test_location = locations[0]

        # Insert time series data
        base_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        readings = [
            WeatherReading(
                location_id=test_location.id,
                timestamp=base_time + timedelta(hours=i),
                temperature=float(i),
                data_granularity="hourly",
            )
            for i in range(24)
        ]
        insert_readings(readings)

        # Query time series
        from tomorrow.db import get_time_series

        start = base_time
        end = base_time + timedelta(hours=23)

        series = get_time_series(test_location.id, start, end)

        assert len(series) == 24

        # Verify ordering and values
        for i, reading in enumerate(series):
            assert reading.timestamp == base_time + timedelta(hours=i)
            assert reading.temperature == float(i)
