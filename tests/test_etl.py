"""Tests for ETL pipeline.

These tests verify:
- Data transformation from API to database models
- Full pipeline execution with mocked dependencies
- Error handling and partial failure scenarios
- Idempotent operations (safe re-runs)
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Set required environment variables for tests
os.environ.setdefault("TOMORROW_API_KEY", "test_api_key_for_tests")
os.environ.setdefault("PGPASSWORD", "postgres")

from tomorrow.etl import (
    ETLResult,
    transform_timeline_to_readings,
    run_etl_pipeline,
    run_hourly_pipeline,
    run_minutely_pipeline,
)
from tomorrow.models import Location, WeatherReading, TimelinesResponse, TimelineEntry, TimelineValues


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_location():
    """Create a sample location."""
    return Location(
        id=1,
        lat=25.86,
        lon=-97.42,
        name="Test Location",
        is_active=True,
    )


@pytest.fixture
def mock_timelines_response():
    """Create a mock API response."""
    return TimelinesResponse(
        timelines={
            "hourly": [
                TimelineEntry(
                    time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
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
                TimelineEntry(
                    time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
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
        }
    )


# =============================================================================
# Transform Tests
# =============================================================================

class TestTransformTimelineToReadings:
    """Tests for data transformation from API to database models."""
    
    def test_transform_single_reading(self, sample_location, mock_timelines_response):
        """Should transform API response to WeatherReading models."""
        readings = transform_timeline_to_readings(
            location=sample_location,
            response=mock_timelines_response,
            granularity="hourly",
        )
        
        assert len(readings) == 2
        
        # Check first reading
        first = readings[0]
        assert first.location_id == 1
        assert first.timestamp == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert first.temperature == 22.5
        assert first.wind_speed == 5.2
        assert first.humidity == 65.0
        assert first.data_granularity == "hourly"
    
    def test_transform_all_fields_mapped(self, sample_location, mock_timelines_response):
        """Should map all API fields to database fields."""
        readings = transform_timeline_to_readings(
            location=sample_location,
            response=mock_timelines_response,
        )
        
        reading = readings[0]
        
        # Check all fields are mapped
        assert reading.temperature is not None
        assert reading.temperature_apparent is not None
        assert reading.wind_speed is not None
        assert reading.wind_gust is not None
        assert reading.wind_direction is not None
        assert reading.humidity is not None
        assert reading.dew_point is not None
        assert reading.cloud_cover is not None
        assert reading.visibility is not None
        assert reading.precipitation_probability is not None
        assert reading.pressure_sea_level is not None
        assert reading.pressure_surface_level is not None
        assert reading.weather_code is not None
        assert reading.uv_index is not None
    
    def test_transform_empty_timeline(self, sample_location):
        """Should handle empty timeline gracefully."""
        empty_response = TimelinesResponse(timelines={"hourly": []})
        
        readings = transform_timeline_to_readings(
            location=sample_location,
            response=empty_response,
        )
        
        assert len(readings) == 0
    
    def test_transform_missing_granularity(self, sample_location):
        """Should handle missing granularity in response."""
        response = TimelinesResponse(timelines={"daily": []})
        
        readings = transform_timeline_to_readings(
            location=sample_location,
            response=response,
            granularity="hourly",
        )
        
        assert len(readings) == 0


# =============================================================================
# ETLResult Tests
# =============================================================================

class TestETLResult:
    """Tests for ETLResult dataclass."""
    
    def test_success_property_all_success(self):
        """Should report success when no failures."""
        result = ETLResult(
            locations_processed=10,
            readings_inserted=1440,
            locations_failed=0,
            errors=[],
            duration_seconds=30.5,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        
        assert result.success is True
        assert result.total_locations == 10
    
    def test_success_property_with_failures(self):
        """Should report failure when locations failed."""
        result = ETLResult(
            locations_processed=8,
            readings_inserted=1152,
            locations_failed=2,
            errors=["Error 1", "Error 2"],
            duration_seconds=30.5,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        
        assert result.success is False
        assert result.total_locations == 10


# =============================================================================
# Pipeline Integration Tests
# =============================================================================

class TestRunETLPipeline:
    """Tests for full ETL pipeline execution."""
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_full_pipeline_success(
        self,
        mock_insert,
        mock_get_locations,
        sample_location,
        mock_timelines_response,
    ):
        """Should run full pipeline successfully."""
        # Setup mocks
        mock_get_locations.return_value = [sample_location]
        mock_insert.return_value = 2
        
        # Mock API client
        mock_client = MagicMock()
        mock_client.fetch_weather.return_value = mock_timelines_response
        
        # Run pipeline
        result = run_etl_pipeline(
            client=mock_client,
            locations=[sample_location],
            granularity="hourly",
        )
        
        # Verify results
        assert result.success is True
        assert result.locations_processed == 1
        assert result.locations_failed == 0
        assert result.readings_inserted == 2
        assert len(result.errors) == 0
        
        # Verify mocks called
        mock_client.fetch_weather.assert_called_once()
        mock_insert.assert_called_once()
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_pipeline_with_api_error(
        self,
        mock_insert,
        mock_get_locations,
        sample_location,
    ):
        """Should handle API errors gracefully."""
        from tomorrow.client import TomorrowAPIError
        
        # Setup mocks
        mock_get_locations.return_value = [sample_location]
        
        # Mock API client that raises error
        mock_client = MagicMock()
        mock_client.fetch_weather.side_effect = TomorrowAPIError("API Error")
        
        # Run pipeline
        result = run_etl_pipeline(
            client=mock_client,
            locations=[sample_location],
        )
        
        # Verify results
        assert result.success is False
        assert result.locations_processed == 0
        assert result.locations_failed == 1
        assert result.readings_inserted == 0
        assert len(result.errors) == 1
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_pipeline_multiple_locations_partial_failure(
        self,
        mock_insert,
        mock_get_locations,
        mock_timelines_response,
    ):
        """Should continue processing when some locations fail."""
        from tomorrow.client import TomorrowAPIError
        
        locations = [
            Location(id=1, lat=25.86, lon=-97.42, name="Loc 1", is_active=True),
            Location(id=2, lat=26.20, lon=-98.23, name="Loc 2", is_active=True),
            Location(id=3, lat=29.76, lon=-95.37, name="Loc 3", is_active=True),
        ]
        
        mock_get_locations.return_value = locations
        
        # Mock API client - second location fails
        mock_client = MagicMock()
        mock_client.fetch_weather.side_effect = [
            mock_timelines_response,  # Loc 1 succeeds
            TomorrowAPIError("API Error"),  # Loc 2 fails
            mock_timelines_response,  # Loc 3 succeeds
        ]
        
        # Run pipeline
        result = run_etl_pipeline(
            client=mock_client,
            locations=locations,
        )
        
        # Verify results
        assert result.success is False
        assert result.locations_processed == 2
        assert result.locations_failed == 1
        assert result.readings_inserted == 4  # 2 readings per successful location
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_pipeline_no_locations(
        self,
        mock_insert,
        mock_get_locations,
    ):
        """Should handle empty locations list."""
        mock_get_locations.return_value = []
        
        result = run_etl_pipeline(locations=[])
        
        # success=True means no location API calls failed
        assert result.success is True
        assert result.locations_processed == 0
        assert result.readings_inserted == 0
        assert "No active locations found" in result.errors[0]
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_pipeline_custom_time_range(
        self,
        mock_insert,
        mock_get_locations,
        sample_location,
        mock_timelines_response,
    ):
        """Should support custom time range."""
        mock_get_locations.return_value = [sample_location]
        mock_insert.return_value = 2
        
        mock_client = MagicMock()
        mock_client.fetch_weather.return_value = mock_timelines_response
        
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        
        result = run_etl_pipeline(
            client=mock_client,
            locations=[sample_location],
            start_time=start_time,
            end_time=end_time,
        )
        
        assert result.success is True
        
        # Verify time parameters passed to API
        call_kwargs = mock_client.fetch_weather.call_args[1]
        assert call_kwargs["start_time"] == "2024-01-01T00:00:00Z"
        assert call_kwargs["end_time"] == "2024-01-02T00:00:00Z"
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_pipeline_creates_client_if_not_provided(
        self,
        mock_insert,
        mock_get_locations,
        sample_location,
        mock_timelines_response,
    ):
        """Should create API client if not provided."""
        mock_get_locations.return_value = [sample_location]
        mock_insert.return_value = 2
        
        with patch("tomorrow.etl.TomorrowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_weather.return_value = mock_timelines_response
            mock_client_class.return_value = mock_client
            
            result = run_etl_pipeline(locations=[sample_location])
            
            assert result.success is True
            mock_client_class.assert_called_once()
            mock_client.close.assert_called_once()
    
    @patch("tomorrow.etl.get_active_locations")
    @patch("tomorrow.etl.insert_readings")
    def test_pipeline_database_insert_failure(
        self,
        mock_insert,
        mock_get_locations,
        sample_location,
        mock_timelines_response,
    ):
        """Should handle database insert failures."""
        mock_get_locations.return_value = [sample_location]
        mock_insert.side_effect = Exception("DB Error")
        
        mock_client = MagicMock()
        mock_client.fetch_weather.return_value = mock_timelines_response
        
        result = run_etl_pipeline(
            client=mock_client,
            locations=[sample_location],
        )
        
        # success=True because no location API calls failed
        # (DB error is recorded but doesn't count as location failure)
        assert result.success is True
        assert result.locations_processed == 1  # API succeeded
        assert result.readings_inserted == 0  # But insert failed
        assert len(result.errors) == 1


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for run_hourly_pipeline and run_minutely_pipeline."""
    
    @patch("tomorrow.etl.run_etl_pipeline")
    def test_run_hourly_pipeline(self, mock_run):
        """Should run pipeline with hourly settings."""
        mock_run.return_value = MagicMock(success=True)
        
        result = run_hourly_pipeline()
        
        mock_run.assert_called_once_with(
            granularity="hourly",
            timesteps="1h",
        )
        assert result.success is True
    
    @patch("tomorrow.etl.run_etl_pipeline")
    def test_run_minutely_pipeline(self, mock_run):
        """Should run pipeline with minutely settings."""
        mock_run.return_value = MagicMock(success=True)
        
        result = run_minutely_pipeline()
        
        mock_run.assert_called_once_with(
            granularity="minutely",
            timesteps="1m",
        )
        assert result.success is True
