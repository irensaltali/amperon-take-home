"""ETL Pipeline for Tomorrow.io Weather Data.

Orchestrates the end-to-end data flow:
1. EXTRACT: Load locations from DB, fetch weather from API
2. TRANSFORM: Convert API responses to WeatherReading models
3. LOAD: Batch insert readings into PostgreSQL with UPSERT

Features:
- Transactional batch processing
- Observability via structured logging
- Error handling with partial failure support
- Idempotent operations (safe to re-run)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import List, Optional

from tomorrow.client import TomorrowClient, TomorrowAPIError, TomorrowAPIRateLimitError
from tomorrow.db import get_active_locations, insert_readings
from tomorrow.models import Location, WeatherReading, TimelinesResponse


logger = logging.getLogger(__name__)


@dataclass
class ETLResult:
    """Result of an ETL pipeline run.

    Attributes:
        locations_processed: Number of locations successfully processed
        readings_inserted: Number of weather readings inserted/updated
        locations_failed: Number of locations that failed
        errors: List of error messages
        duration_seconds: Total pipeline execution time
        started_at: Pipeline start timestamp
        completed_at: Pipeline completion timestamp
    """

    locations_processed: int
    readings_inserted: int
    locations_failed: int
    errors: List[str]
    duration_seconds: float
    started_at: datetime
    completed_at: datetime

    @property
    def success(self) -> bool:
        """True if all locations were processed successfully."""
        return self.locations_failed == 0

    @property
    def total_locations(self) -> int:
        """Total number of locations attempted."""
        return self.locations_processed + self.locations_failed


def transform_timeline_to_readings(
    location: Location,
    response: TimelinesResponse,
    granularity: str = "hourly",
) -> List[WeatherReading]:
    """Transform API timeline response to WeatherReading models.

    Args:
        location: The location for this data
        response: API response with timelines
        granularity: Data granularity (minutely, hourly, daily) - maps to timestep

    Returns:
        List of WeatherReading models ready for database insertion
    """
    readings = []

    # Map granularity to timestep format used by API
    timestep_map = {
        "minutely": "1m",
        "hourly": "1h",
        "daily": "1d",
    }
    target_timestep = timestep_map.get(granularity, "1h")

    # Find the timeline matching our requested granularity
    for timeline in response.data.timelines:
        if timeline.timestep == target_timestep:
            for interval in timeline.intervals:
                values = interval.values

                reading = WeatherReading(
                    location_id=location.id,
                    timestamp=interval.start_time,
                    temperature=values.temperature,
                    temperature_apparent=values.temperature_apparent,
                    wind_speed=values.wind_speed,
                    wind_gust=values.wind_gust,
                    wind_direction=values.wind_direction,
                    humidity=values.humidity,
                    dew_point=values.dew_point,
                    cloud_cover=values.cloud_cover,
                    cloud_base=values.cloud_base,
                    cloud_ceiling=values.cloud_ceiling,
                    visibility=values.visibility,
                    precipitation_probability=values.precipitation_probability,
                    rain_intensity=values.rain_intensity,
                    rain_accumulation=values.rain_accumulation,
                    freezing_rain_intensity=values.freezing_rain_intensity,
                    sleet_intensity=values.sleet_intensity,
                    sleet_accumulation=values.sleet_accumulation,
                    sleet_accumulation_lwe=values.sleet_accumulation_lwe,
                    snow_intensity=values.snow_intensity,
                    snow_accumulation=values.snow_accumulation,
                    snow_accumulation_lwe=values.snow_accumulation_lwe,
                    snow_depth=values.snow_depth,
                    ice_accumulation=values.ice_accumulation,
                    ice_accumulation_lwe=values.ice_accumulation_lwe,
                    evapotranspiration=values.evapotranspiration,
                    pressure_sea_level=values.pressure_sea_level,
                    pressure_surface_level=values.pressure_surface_level,
                    altimeter_setting=values.altimeter_setting,
                    weather_code=values.weather_code,
                    uv_index=values.uv_index,
                    uv_health_concern=values.uv_health_concern,
                    data_granularity=granularity,
                )
                readings.append(reading)

    logger.debug(
        f"transformed_readings location_id={location.id} "
        f"granularity={granularity} count={len(readings)}"
    )

    return readings


def run_etl_pipeline(
    client: Optional[TomorrowClient] = None,
    granularity: str = "hourly",
    timesteps: str = "1h",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    locations: Optional[List[Location]] = None,
) -> ETLResult:
    """Run the complete ETL pipeline.

    This is the main entry point for weather data ingestion.

    Args:
        client: Tomorrow.io API client (created if not provided)
        granularity: Data granularity (minutely, hourly, daily)
        timesteps: Time interval (1m, 1h, 1d)
        start_time: Start of time range (defaults to now)
        end_time: End of time range (defaults to 5 days from now)
        locations: Specific locations to process (defaults to all active)

    Returns:
        ETLResult with statistics and error information

    Example:
        # Run with default settings (hourly data for all locations)
        result = run_etl_pipeline()

        # Run for specific time range
        result = run_etl_pipeline(
            start_time=datetime.now(timezone.utc) - timedelta(days=1),
            end_time=datetime.now(timezone.utc) + timedelta(days=5),
        )

        # Check results
        if result.success:
            print(f"Inserted {result.readings_inserted} readings")
        else:
            print(f"Failed: {result.errors}")
    """
    started_at = datetime.now(timezone.utc)

    # Initialize counters
    locations_processed = 0
    readings_inserted = 0
    locations_failed = 0
    errors = []

    # Create client if not provided
    client_created = False
    if client is None:
        client = TomorrowClient()
        client_created = True

    try:
        # ======================================================================
        # EXTRACT: Load locations and fetch weather data
        # ======================================================================

        # Load locations from database if not provided
        if locations is None:
            logger.info("loading_active_locations_from_db")
            locations = get_active_locations()
            logger.info(f"loaded_locations count={len(locations)}")

        if not locations:
            logger.warning("no_locations_to_process")
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            return ETLResult(
                locations_processed=0,
                readings_inserted=0,
                locations_failed=0,
                errors=["No active locations found"],
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )

        # Calculate default time range if not provided
        # Default: from -1 day to +5 days (6 days total)
        if start_time is None:
            start_time = started_at - timedelta(days=1)
        if end_time is None:
            end_time = started_at + timedelta(days=5)

        # Format times for API
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info(
            f"etl_pipeline_started locations={len(locations)} "
            f"granularity={granularity} timesteps={timesteps} "
            f"start={start_time_str} end={end_time_str}"
        )

        # Fetch weather data for all locations
        all_readings: List[WeatherReading] = []
        rate_limited = False

        for i, location in enumerate(locations):
            # Add delay between requests to avoid rate limiting (skip first request)
            if i > 0:
                logger.debug("rate_limit_delay seconds=3")
                time.sleep(3)

            try:
                logger.debug(
                    f"fetching_weather location_id={location.id} "
                    f"lat={location.lat} lon={location.lon}"
                )

                response = client.fetch_weather(
                    location=location,
                    timesteps=timesteps,
                    start_time=start_time_str,
                    end_time=end_time_str,
                )

                # ======================================================================
                # TRANSFORM: Convert API response to database models
                # ======================================================================
                readings = transform_timeline_to_readings(
                    location=location,
                    response=response,
                    granularity=granularity,
                )

                all_readings.extend(readings)
                locations_processed += 1

                logger.debug(
                    f"transformed_readings location_id={location.id} "
                    f"count={len(readings)}"
                )

            except TomorrowAPIRateLimitError:
                locations_failed += 1
                error_msg = f"Rate limit hit at location {location.id} - stopping to preserve quota"
                errors.append(error_msg)
                logger.warning(error_msg)
                rate_limited = True
                # Stop processing - save what we have so far
                break

            except TomorrowAPIError as e:
                locations_failed += 1
                error_msg = f"API error for location {location.id}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
                # Continue with other locations
                continue
            except Exception as e:
                locations_failed += 1
                error_msg = f"Unexpected error for location {location.id}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
                # Continue with other locations
                continue

        if rate_limited:
            logger.warning(
                f"etl_pipeline_rate_limited - processed {locations_processed} of {len(locations)} locations"
            )

        # ======================================================================
        # LOAD: Insert readings into database
        # ======================================================================

        if all_readings:
            try:
                logger.info(f"inserting_readings count={len(all_readings)}")
                insert_readings(all_readings)
                readings_inserted = len(all_readings)
                logger.info(f"inserted_readings count={readings_inserted}")
            except Exception as e:
                error_msg = f"Database insert failed: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        else:
            logger.warning("no_readings_to_insert")

    except Exception as e:
        error_msg = f"Pipeline failed: {e}"
        errors.append(error_msg)
        logger.error(error_msg)

    finally:
        # Clean up client if we created it
        if client_created:
            client.close()

    # Calculate duration
    completed_at = datetime.now(timezone.utc)
    duration_seconds = (completed_at - started_at).total_seconds()

    # Log completion
    log_level = logging.INFO if locations_failed == 0 else logging.WARNING
    logger.log(
        log_level,
        f"etl_pipeline_completed "
        f"locations_processed={locations_processed} "
        f"locations_failed={locations_failed} "
        f"readings_inserted={readings_inserted} "
        f"duration_seconds={duration_seconds:.2f}",
    )

    return ETLResult(
        locations_processed=locations_processed,
        readings_inserted=readings_inserted,
        locations_failed=locations_failed,
        errors=errors,
        duration_seconds=duration_seconds,
        started_at=started_at,
        completed_at=completed_at,
    )


def run_hourly_pipeline() -> ETLResult:
    """Run the standard hourly pipeline.

    Convenience function for scheduled execution.
    Fetches hourly data for the default time range (-1 day to +5 days).

    Returns:
        ETLResult with pipeline statistics
    """
    return run_etl_pipeline(
        granularity="hourly",
        timesteps="1h",
    )


def run_minutely_pipeline() -> ETLResult:
    """Run the minutely pipeline.

    Convenience function for high-frequency data collection.
    Fetches minutely data for the default time range.

    Returns:
        ETLResult with pipeline statistics
    """
    return run_etl_pipeline(
        granularity="minutely",
        timesteps="1m",
    )
