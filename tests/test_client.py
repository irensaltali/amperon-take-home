"""Tests for Tomorrow.io API client."""

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
        "data": {
            "timelines": [
                {
                    "timestep": "1h",
                    "startTime": "2024-01-01T12:00:00Z",
                    "endTime": "2024-01-01T14:00:00Z",
                    "intervals": [
                        {
                            "startTime": "2024-01-01T12:00:00Z",
                            "values": {
                                "temperature": 22.5,
                                "temperatureApparent": 21.0,
                                "windSpeed": 5.2,
                                "windGust": 8.1,
                                "windDirection": 180,
                                "humidity": 65,
                                "precipitationProbability": 10,
                                "pressureSeaLevel": 1013,
                                "pressureSurfaceLevel": 1010,
                                "weatherCode": 1000,
                            },
                        },
                        {
                            "startTime": "2024-01-01T13:00:00Z",
                            "values": {
                                "temperature": 23.0,
                                "temperatureApparent": 22.0,
                                "windSpeed": 5.5,
                                "windGust": 8.5,
                                "windDirection": 185,
                                "humidity": 63,
                                "precipitationProbability": 15,
                                "pressureSeaLevel": 1012,
                                "pressureSurfaceLevel": 1009,
                                "weatherCode": 1000,
                            },
                        },
                    ]
                },
                {
                    "timestep": "1m",
                    "startTime": "2024-01-01T12:00:00Z",
                    "endTime": "2024-01-01T12:01:00Z",
                    "intervals": [
                        {
                            "startTime": "2024-01-01T12:00:00Z",
                            "values": {
                                "temperature": 22.5,
                                "windSpeed": 5.2,
                            },
                        },
                    ]
                }
            ]
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
    
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} Error", response=mock_response
        )
    
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
        client.close()

    def test_client_init_from_settings(self):
        """Should initialize with API key from settings."""
        client = TomorrowClient()
        assert client.api_key == "test_api_key_for_tests"
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
        assert len(response.data.timelines) > 0
        
        # Find hourly timeline
        hourly = next((t for t in response.data.timelines if t.timestep == "1h"), None)
        assert hourly is not None
        assert len(hourly.intervals) == 2

        # Verify first entry
        first_entry = hourly.intervals[0]
        assert first_entry.start_time == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert first_entry.values.temperature == 22.5
        assert first_entry.values.wind_speed == 5.2

    def test_fetch_weather_with_custom_fields(self, client, sample_location):
        """Should request only specified fields."""
        mock_response = create_mock_response(
            200,
            {
                "data": {
                    "timelines": [
                        {
                            "timestep": "1h",
                            "startTime": "2024-01-01T12:00:00Z",
                            "endTime": "2024-01-01T13:00:00Z",
                            "intervals": [
                                {
                                    "startTime": "2024-01-01T12:00:00Z",
                                    "values": {
                                        "temperature": 22.5,
                                        "humidity": 65,
                                    },
                                }
                            ]
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
        mock_response = create_mock_response(200, {"data": {"timelines": []}})

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
        mock_response = create_mock_response(200, {
            "data": {
                "timelines": [
                    {
                        "timestep": "1m",
                        "startTime": "2024-01-01T12:00:00Z",
                        "endTime": "2024-01-01T12:01:00Z",
                        "intervals": []
                    }
                ]
            }
        })

        with patch.object(client.session, "get", return_value=mock_response):
            response = client.fetch_weather(sample_location, timesteps="1m")
            minutely = next((t for t in response.data.timelines if t.timestep == "1m"), None)
            assert minutely is not None


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for API error handling."""

    def test_auth_error_401(self, client, sample_location):
        """Should raise generic TomorrowAPIError on 401."""
        mock_response = create_mock_response(401, text="Unauthorized")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)

        assert "401" in str(exc_info.value)

    def test_rate_limit_error_429(self, client, sample_location):
        """Should raise TomorrowAPIRateLimitError on 429."""
        mock_response = create_mock_response(429, text="Rate limit exceeded")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIRateLimitError) as exc_info:
                client.fetch_weather(sample_location)

        assert "rate limit exceeded" in str(exc_info.value).lower()

    def test_server_error_500(self, client, sample_location):
        """Should raise TomorrowAPIError on 500."""
        mock_response = create_mock_response(500, text="Internal Server Error")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)
        
        assert "500" in str(exc_info.value)

    def test_invalid_json_response(self, client, sample_location):
        """Should handle invalid JSON response."""
        mock_response = create_mock_response(200, text="invalid json")

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)

        assert (
            "invalid response" in str(exc_info.value).lower()
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

        assert "request failed" in str(exc_info.value).lower() and "time" in str(exc_info.value).lower()

    def test_connection_error(self, client, sample_location):
        """Should handle connection error."""
        with patch.object(
            client.session,
            "get",
            side_effect=requests.exceptions.ConnectionError("Connection failed"),
        ):
            with pytest.raises(TomorrowAPIError) as exc_info:
                client.fetch_weather(sample_location)

        assert "request failed" in str(exc_info.value).lower()


# =============================================================================
# Default Fields Tests
# =============================================================================


class TestDefaultFields:
    """Tests for default API fields."""

    def test_default_fields_list(self):
        """Should have essential default fields (simplified)."""
        expected_fields = [
            "temperature",
            "temperatureApparent",
            "windSpeed",
            "windGust",
            "windDirection",
            "humidity",
            "precipitationProbability",
            "weatherCode",
            "pressureSeaLevel",
            "pressureSurfaceLevel",
        ]

        assert DEFAULT_FIELDS == expected_fields
        assert len(DEFAULT_FIELDS) == 10
