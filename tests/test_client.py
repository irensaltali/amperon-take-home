"""Tests for Tomorrow.io API client.

These tests verify:
- API client initialization
- Successful weather data fetching
- Error handling for various failure modes
- Batch fetching for multiple locations
- Response validation
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

# Set required environment variables for tests
os.environ.setdefault("TOMORROW_API_KEY", "test_api_key_for_tests")
os.environ.setdefault("PGPASSWORD", "postgres")

from tomorrow.client import (
    TomorrowClient,
    TomorrowAPIError,
    TomorrowAPIAuthError,
    TomorrowAPIRateLimitError,
    DEFAULT_FIELDS,
)
from tomorrow.models import Location, TimelinesResponse


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def api_key():
    """Test API key."""
    return "test_api_key_12345"


@pytest.fixture
def client(api_key):
    """Create a test client."""
    with TomorrowClient(api_key=api_key) as client:
        yield client


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
def mock_weather_response():
    """Create a mock API response."""
    return {
        "timelines": {
            "hourly": [
                {
                    "time": "2024-01-01T12:00:00Z",
                    "values": {
                        "temperature": 22.5,
                        "temperatureApparent": 21.0,
                        "windSpeed": 5.2,
                        "windGust": 8.1,
                        "windDirection": 180,
                        "humidity": 65,
                        "dewPoint": 15.5,
                        "cloudCover": 20,
                        "visibility": 10,
                        "precipitationProbability": 10,
                        "pressureSeaLevel": 1013,
                        "weatherCode": 1000,
                        "uvIndex": 5,
                    },
                },
                {
                    "time": "2024-01-01T13:00:00Z",
                    "values": {
                        "temperature": 23.0,
                        "temperatureApparent": 22.0,
                        "windSpeed": 5.5,
                        "windGust": 8.5,
                        "windDirection": 185,
                        "humidity": 63,
                        "dewPoint": 15.8,
                        "cloudCover": 25,
                        "visibility": 10,
                        "precipitationProbability": 15,
                        "pressureSeaLevel": 1012,
                        "weatherCode": 1000,
                        "uvIndex": 6,
                    },
                },
            ],
            "minutely": [
                {
                    "time": "2024-01-01T12:00:00Z",
                    "values": {
                        "temperature": 22.5,
                        "windSpeed": 5.2,
                    },
                },
            ],
        }
    }


def create_mock_response(status_code=200, json_data=None, text=""):
    """Helper to create a mock requests response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if json_data is not None:
        mock_response.json.return_value = json_data
    else:
        mock_response.json.side_effect = json.JSONDecodeError("test", text, 0)
    mock_response.text = text or json.dumps(json_data) if json_data else ""
    return mock_response


# =============================================================================
# Client Initialization Tests
# =============================================================================


class TestClientInitialization:
    """Tests for API client initialization."""

    def test_client_init_with_api_key(self, api_key):
        """Should initialize with explicit API key."""
        client = TomorrowClient(api_key=api_key)
        assert client.api_key == api_key
        assert client.base_url == "https://api.tomorrow.io/v4/"
        client.close()

    def test_client_init_from_settings(self):
        """Should initialize with API key from settings."""
        client = TomorrowClient()
        assert client.api_key == "test_api_key_for_tests"
        client.close()

    def test_client_init_custom_base_url(self, api_key):
        """Should initialize with custom base URL."""
        client = TomorrowClient(
            api_key=api_key,
            base_url="https://custom.api.tomorrow.io/v4/",
        )
        assert client.base_url == "https://custom.api.tomorrow.io/v4/"
        client.close()

    def test_client_context_manager(self, api_key):
        """Should work as context manager."""
        with TomorrowClient(api_key=api_key) as client:
            assert client.api_key == api_key
        # After exiting context, session should be closed

    def test_client_custom_timeout(self, api_key):
        """Should use custom timeout."""
        client = TomorrowClient(api_key=api_key, timeout=60)
        assert client.timeout == 60
        client.close()

    def test_client_custom_retries(self, api_key):
        """Should configure retry strategy."""
        # Just verify it doesn't raise
        client = TomorrowClient(api_key=api_key, max_retries=5)
        assert client.session is not None
        client.close()


# =============================================================================
# Successful API Call Tests
# =============================================================================


class TestSuccessfulAPICalls:
    """Tests for successful API interactions."""

    def test_fetch_weather_success(
        self, client, sample_location, mock_weather_response
    ):
        """Should successfully fetch and parse weather data."""
        mock_response = create_mock_response(200, mock_weather_response)

        with patch.object(client.session, "get", return_value=mock_response):
            response = client.fetch_weather(sample_location)

        # Verify response is parsed correctly
        assert isinstance(response, TimelinesResponse)
        assert "hourly" in response.timelines
        assert len(response.timelines["hourly"]) == 2

        # Verify first entry
        first_entry = response.timelines["hourly"][0]
        assert first_entry.time == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert first_entry.values.temperature == 22.5
        assert first_entry.values.wind_speed == 5.2

    def test_fetch_weather_with_custom_fields(self, client, sample_location):
        """Should request only specified fields."""
        mock_response = create_mock_response(
            200,
            {
                "timelines": {
                    "hourly": [
                        {
                            "time": "2024-01-01T12:00:00Z",
                            "values": {
                                "temperature": 22.5,
                                "humidity": 65,
                            },
                        }
                    ]
                }
            },
        )

        custom_fields = ["temperature", "humidity"]

        with patch.object(
            client.session, "get", return_value=mock_response
        ) as mock_get:
            response = client.fetch_weather(sample_location, fields=custom_fields)

            # Verify request was made
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args[1]
            assert "params" in call_kwargs
            assert "temperature" in call_kwargs["params"]["fields"]

    def test_fetch_weather_with_time_range(self, client, sample_location):
        """Should support custom time range."""
        mock_response = create_mock_response(200, {"timelines": {"hourly": []}})

        with patch.object(
            client.session, "get", return_value=mock_response
        ) as mock_get:
            client.fetch_weather(
                sample_location,
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-02T00:00:00Z",
            )

            # Verify time parameters in call
            call_kwargs = mock_get.call_args[1]
            assert "params" in call_kwargs
            assert call_kwargs["params"]["startTime"] == "2024-01-01T00:00:00Z"
            assert call_kwargs["params"]["endTime"] == "2024-01-02T00:00:00Z"

    def test_fetch_weather_minutely_timesteps(self, client, sample_location):
        """Should support minutely timesteps."""
        mock_response = create_mock_response(200, {"timelines": {"minutely": []}})

        with patch.object(client.session, "get", return_value=mock_response):
            response = client.fetch_weather(sample_location, timesteps="1m")
            assert "minutely" in response.timelines


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for API error handling."""

    def test_auth_error_401(self, client, sample_location):
        """Should raise TomorrowAPIAuthError on 401."""
        mock_response = create_mock_response(401, text="Unauthorized")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIAuthError) as exc_info:
                client.fetch_weather(sample_location)

        assert exc_info.value.status_code == 401

    def test_rate_limit_error_429(self, client, sample_location):
        """Should raise TomorrowAPIRateLimitError on 429."""
        mock_response = create_mock_response(429, text="Rate limit exceeded")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIRateLimitError) as exc_info:
                client.fetch_weather(sample_location)

        assert exc_info.value.status_code == 429

    def test_server_error_500(self, client, sample_location):
        """Should raise TomorrowAPIError on 500."""
        mock_response = create_mock_response(500, text="Internal Server Error")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIError):
                client.fetch_weather(sample_location)

    def test_invalid_json_response(self, client, sample_location):
        """Should handle invalid JSON response."""
        mock_response = create_mock_response(200, text="invalid json")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)

        assert (
            "parse" in str(exc_info.value).lower()
            or "json" in str(exc_info.value).lower()
        )

    def test_timeout_error(self, client, sample_location):
        """Should handle request timeout."""
        with patch.object(
            client.session,
            "get",
            side_effect=requests.exceptions.Timeout("Request timed out"),
        ):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)

        assert "timed out" in str(exc_info.value).lower()

    def test_connection_error(self, client, sample_location):
        """Should handle connection error."""
        with patch.object(
            client.session,
            "get",
            side_effect=requests.exceptions.ConnectionError("Connection failed"),
        ):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)

        assert "connection" in str(exc_info.value).lower()


# =============================================================================
# Batch Fetching Tests
# =============================================================================


class TestBatchFetching:
    """Tests for fetching weather for multiple locations."""

    def test_fetch_multiple_locations_success(self, client, mock_weather_response):
        """Should fetch weather for multiple locations."""
        locations = [
            Location(id=1, lat=25.86, lon=-97.42, name="Loc 1", is_active=True),
            Location(id=2, lat=26.20, lon=-98.23, name="Loc 2", is_active=True),
            Location(id=3, lat=29.76, lon=-95.37, name="Loc 3", is_active=True),
        ]

        mock_response = create_mock_response(200, mock_weather_response)

        with patch.object(client.session, "get", return_value=mock_response):
            results = client.fetch_weather_for_locations(locations)

        assert len(results) == 3
        assert all(loc.id in results for loc in locations)
        assert all(isinstance(r, TimelinesResponse) for r in results.values())

    def test_fetch_multiple_locations_partial_failure(
        self, client, mock_weather_response
    ):
        """Should continue fetching when some locations fail."""
        locations = [
            Location(id=1, lat=25.86, lon=-97.42, name="Loc 1", is_active=True),
            Location(id=2, lat=26.20, lon=-98.23, name="Loc 2", is_active=True),
        ]

        # First call succeeds, second fails
        success_response = create_mock_response(200, mock_weather_response)
        error_response = create_mock_response(500, text="Server Error")

        with patch.object(
            client.session, "get", side_effect=[success_response, error_response]
        ):
            results = client.fetch_weather_for_locations(locations)

        # Should have result for first location only
        assert len(results) == 1
        assert 1 in results
        assert 2 not in results

    def test_fetch_empty_locations_list(self, client):
        """Should handle empty locations list."""
        results = client.fetch_weather_for_locations([])
        assert len(results) == 0


# =============================================================================
# Default Fields Tests
# =============================================================================


class TestDefaultFields:
    """Tests for default API fields."""

    def test_default_fields_list(self):
        """Should have comprehensive default fields."""
        expected_fields = [
            "temperature",
            "temperatureApparent",
            "windSpeed",
            "windGust",
            "windDirection",
            "humidity",
            "dewPoint",
            "cloudCover",
            "cloudBase",
            "cloudCeiling",
            "visibility",
            "precipitationProbability",
            "rainIntensity",
            "rainAccumulation",
            "freezingRainIntensity",
            "sleetIntensity",
            "sleetAccumulation",
            "sleetAccumulationLwe",
            "snowIntensity",
            "snowAccumulation",
            "snowAccumulationLwe",
            "snowDepth",
            "iceAccumulation",
            "iceAccumulationLwe",
            "evapotranspiration",
            "pressureSeaLevel",
            "pressureSurfaceLevel",
            "altimeterSetting",
            "weatherCode",
            "uvIndex",
            "uvHealthConcern",
        ]

        assert DEFAULT_FIELDS == expected_fields
        assert len(DEFAULT_FIELDS) >= 30  # Should have many fields
