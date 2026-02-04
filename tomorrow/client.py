"""Tomorrow.io API client for fetching weather data.

Provides a robust HTTP client for the Tomorrow.io Weather API with:
- Automatic retry with exponential backoff
- Pydantic model validation for responses
- Error handling for API failures
- Support for fetching multiple locations
"""

import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from tomorrow.config import get_settings
from tomorrow.models import Location, TimelinesResponse

logger = logging.getLogger(__name__)

# Default API configuration
DEFAULT_BASE_URL = "https://api.tomorrow.io/v4/"
DEFAULT_TIMEOUT = 30  # seconds

# Fields to request from the API (all available fields for completeness)
DEFAULT_FIELDS = [
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


class TomorrowAPIError(Exception):
    """Base exception for Tomorrow.io API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class TomorrowAPIRateLimitError(TomorrowAPIError):
    """Raised when API rate limit is exceeded."""

    pass


class TomorrowAPIAuthError(TomorrowAPIError):
    """Raised when API authentication fails."""

    pass


class TomorrowClient:
    """HTTP client for Tomorrow.io Weather API.

    Features:
    - Automatic retry with exponential backoff for transient failures
    - Pydantic model validation for all responses
    - Comprehensive error handling
    - Connection pooling for efficiency

    Example:
        client = TomorrowClient()

        # Fetch weather for a single location
        location = Location(id=1, lat=25.86, lon=-97.42, name="Brownsville")
        response = client.fetch_weather(location)

        # Access hourly data
        for entry in response.timelines.get("hourly", []):
            print(f"{entry.time}: {entry.values.temperature}°C")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ):
        """Initialize the API client.

        Args:
            api_key: Tomorrow.io API key (defaults to settings)
            base_url: API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        settings = get_settings()
        self.api_key = api_key or settings.tomorrow_api_key
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

        # Create session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,  # 1s, 2s, 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry these status codes
            allowed_methods=["GET"],  # Only retry GET requests
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

        logger.info(
            f"tomorrow_client_initialized base_url={self.base_url} "
            f"timeout={timeout} max_retries={max_retries}"
        )

    def fetch_weather(
        self,
        location: Location,
        fields: Optional[list[str]] = None,
        timesteps: str = "1h",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> TimelinesResponse:
        """Fetch weather data for a single location.

        Args:
            location: Location to fetch weather for
            fields: List of weather fields to request (defaults to all)
            timesteps: Time interval (1m, 1h, 1d)
            start_time: Start time in ISO 8601 format (defaults to now)
            end_time: End time in ISO 8601 format (defaults to 5 days from now)

        Returns:
            TimelinesResponse with validated weather data

        Raises:
            TomorrowAPIAuthError: If API key is invalid
            TomorrowAPIRateLimitError: If rate limit exceeded
            TomorrowAPIError: For other API errors
        """
        fields = fields or DEFAULT_FIELDS

        params = {
            "location": f"{location.lat},{location.lon}",
            "fields": ",".join(fields),
            "timesteps": timesteps,
            "units": "metric",
            "apikey": self.api_key,
        }

        # Add optional time parameters
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        logger.info(
            f"fetching_weather location_id={location.id} "
            f"lat={location.lat} lon={location.lon} "
            f"timesteps={timesteps}"
        )

        url = urljoin(self.base_url, "timelines")

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )

            # Handle specific error cases
            if response.status_code == 401:
                logger.error("api_auth_failed: Invalid API key")
                raise TomorrowAPIAuthError(
                    "Invalid API key",
                    status_code=response.status_code,
                    response_body=response.text,
                )

            if response.status_code == 429:
                logger.error("api_rate_limit_exceeded")
                raise TomorrowAPIRateLimitError(
                    "API rate limit exceeded",
                    status_code=response.status_code,
                    response_body=response.text,
                )

            response.raise_for_status()

        except requests.exceptions.Timeout:
            logger.error(f"api_request_timeout url={url} timeout={self.timeout}")
            raise TomorrowAPIError(f"Request timed out after {self.timeout}s")

        except requests.exceptions.ConnectionError as e:
            logger.error(f"api_connection_error: {e}")
            raise TomorrowAPIError(f"Connection error: {e}")

        except requests.exceptions.RequestException as e:
            logger.error(f"api_request_failed: {e}")
            raise TomorrowAPIError(f"Request failed: {e}")

        # Parse and validate response
        try:
            data = response.json()
            timelines_response = TimelinesResponse.model_validate(data)

            # Log success with data summary
            total_entries = sum(
                len(entries) for entries in timelines_response.timelines.values()
            )
            logger.info(
                f"weather_fetch_success location_id={location.id} "
                f"entries={total_entries} "
                f"granularities={list(timelines_response.timelines.keys())}"
            )

            return timelines_response

        except ValueError as e:
            logger.error(f"api_response_parse_error: {e}")
            raise TomorrowAPIError(f"Failed to parse API response: {e}")

    def fetch_weather_for_locations(
        self,
        locations: list[Location],
        fields: Optional[list[str]] = None,
        timesteps: str = "1h",
    ) -> dict[int, TimelinesResponse]:
        """Fetch weather data for multiple locations.

        Args:
            locations: List of locations to fetch weather for
            fields: List of weather fields to request
            timesteps: Time interval (1m, 1h, 1d)

        Returns:
            Dictionary mapping location_id to TimelinesResponse

        Note:
            Failures for individual locations are logged but not raised.
            The returned dict will only contain successful fetches.
        """
        results = {}

        logger.info(f"batch_fetch_weather location_count={len(locations)}")

        for location in locations:
            try:
                response = self.fetch_weather(
                    location, fields=fields, timesteps=timesteps
                )
                results[location.id] = response
            except TomorrowAPIError as e:
                logger.error(
                    f"fetch_weather_failed location_id={location.id} error={e}"
                )
                # Continue with other locations
                continue

        logger.info(
            f"batch_fetch_complete requested={len(locations)} "
            f"successful={len(results)} failed={len(locations) - len(results)}"
        )

        return results

    def close(self):
        """Close the HTTP session.

        Should be called when done using the client to free resources.
        """
        self.session.close()
        logger.info("tomorrow_client_closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
