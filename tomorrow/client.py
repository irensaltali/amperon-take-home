"""Tomorrow.io API client."""

import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from tomorrow.config import get_settings
from tomorrow.models import Location, TimelinesResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.tomorrow.io/v4"
DEFAULT_TIMEOUT = 30
DEFAULT_FIELDS = [
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


class TomorrowAPIError(Exception):
    """Generic API error."""

    pass


class TomorrowAPIRateLimitError(TomorrowAPIError):
    """Rate limit exceeded (429)."""

    pass


class TomorrowClient:
    """Simple HTTP client for Tomorrow.io."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT):
        self.api_key = api_key or get_settings().tomorrow_api_key
        self.timeout = timeout
        self.session = requests.Session()

        # Configure retries for transient server errors
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def fetch_weather(
        self,
        location: Location,
        fields: Optional[list[str]] = None,
        timesteps: str = "1h",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> TimelinesResponse:
        """Fetch weather data for a location."""
        params = {
            "location": f"{location.lat},{location.lon}",
            "fields": ",".join(fields or DEFAULT_FIELDS),
            "timesteps": timesteps,
            "units": "metric",
            "apikey": self.api_key,
        }

        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        url = f"{DEFAULT_BASE_URL}/timelines"

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 429:
                raise TomorrowAPIRateLimitError("API rate limit exceeded")

            response.raise_for_status()

            data = response.json()
            return TimelinesResponse.model_validate(data)

        except requests.RequestException as e:
            logger.error(f"API Request failed: {e}")
            raise TomorrowAPIError(f"Request failed: {e}") from e
        except ValueError as e:
            logger.error(f"Failed to parse response: {e}")
            raise TomorrowAPIError(f"Invalid response data: {e}") from e

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
