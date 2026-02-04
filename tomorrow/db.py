"""Database layer for Tomorrow.io Weather Data Pipeline.

Provides connection pooling, transaction management, and CRUD operations
for locations and weather data.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional, Tuple

import psycopg2

from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import SimpleConnectionPool

from tomorrow.config import get_settings
from tomorrow.models import Location, LocationSummary, WeatherReading

logger = logging.getLogger(__name__)

# Global connection pool (initialized on first use)
_connection_pool: Optional[SimpleConnectionPool] = None


def get_connection_pool() -> SimpleConnectionPool:
    """Get or create the database connection pool.
    
    Uses a singleton pattern to ensure only one pool exists.
    The pool is thread-safe and handles concurrent requests.
    
    Returns:
        SimpleConnectionPool instance
    """
    global _connection_pool
    
    if _connection_pool is None:
        settings = get_settings()
        try:
            _connection_pool = SimpleConnectionPool(
                minconn=1,
                maxconn=settings.pg_pool_size,
                host=settings.pg_host,
                port=settings.pg_port,
                database=settings.pg_database,
                user=settings.pg_user,
                password=settings.pg_password,
                connect_timeout=settings.pg_pool_timeout_seconds,
                # Return dictionaries instead of tuples
                cursor_factory=RealDictCursor,
            )
            logger.info(
                f"database_pool_created host={settings.pg_host} port={settings.pg_port} "
                f"database={settings.pg_database} pool_size={settings.pg_pool_size}"
            )
        except psycopg2.Error as e:
            logger.error(
                f"database_pool_creation_failed host={settings.pg_host} port={settings.pg_port}: {e}"
            )
            raise
    
    return _connection_pool


@contextmanager
def get_connection():
    """Context manager for database connections.
    
    Automatically returns the connection to the pool when done.
    
    Yields:
        Database connection object
        
    Example:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM locations")
    """
    pool = get_connection_pool()
    conn = None
    try:
        conn = pool.getconn()
        yield conn
        conn.commit()
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"database_error: {e}")
        raise
    finally:
        if conn:
            pool.putconn(conn)


@contextmanager
def get_cursor():
    """Context manager for database cursors.
    
    Combines get_connection() with cursor creation for convenience.
    
    Yields:
        Database cursor object with RealDictCursor factory
        
    Example:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM locations")
            results = cur.fetchall()
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            yield cur


def close_all_connections() -> None:
    """Close all connections in the pool.
    
    Useful for cleanup during application shutdown or testing.
    """
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("database_pool_closed")


# =============================================================================
# Location Operations
# =============================================================================


def get_active_locations() -> List[Location]:
    """Fetch all active locations from the database.
    
    Returns locations that are marked as active for data collection.
    Locations are ordered by ID for consistent results.
    
    Returns:
        List of Location objects
        
    Raises:
        psycopg2.Error: If database query fails
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, lat, lon, name, is_active, created_at
            FROM locations
            WHERE is_active = TRUE
            ORDER BY id
            """
        )
        rows = cur.fetchall()
        
        locations = [Location.model_validate(dict(row)) for row in rows]
        
        logger.info(f"locations_fetched count={len(locations)}")
        
        return locations


def get_location_by_id(location_id: int) -> Optional[Location]:
    """Fetch a single location by ID.
    
    Args:
        location_id: The location ID to fetch
        
    Returns:
        Location object if found, None otherwise
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, lat, lon, name, is_active, created_at
            FROM locations
            WHERE id = %s
            """,
            (location_id,)
        )
        row = cur.fetchone()
        
        if row:
            return Location.model_validate(dict(row))
        return None


def get_location_by_coordinates(lat: float, lon: float) -> Optional[Location]:
    """Fetch a location by its coordinates.
    
    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        
    Returns:
        Location object if found, None otherwise
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, lat, lon, name, is_active, created_at
            FROM locations
            WHERE lat = %s AND lon = %s
            """,
            (lat, lon)
        )
        row = cur.fetchone()
        
        if row:
            return Location.model_validate(dict(row))
        return None


# =============================================================================
# Weather Data Operations
# =============================================================================


def insert_readings(readings: List[WeatherReading]) -> int:
    """Insert weather readings into the database.
    
    Uses UPSERT (ON CONFLICT DO UPDATE) to handle duplicate entries.
    This makes the operation idempotent - safe to re-run.
    
    Args:
        readings: List of WeatherReading objects to insert
        
    Returns:
        Number of rows inserted/updated
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    if not readings:
        logger.info("insert_readings_empty_list")
        return 0
    
    # Prepare data for bulk insert
    # Column order must match the INSERT statement
    data = [
        (
            r.location_id,
            r.timestamp,
            r.temperature,
            r.temperature_apparent,
            r.wind_speed,
            r.wind_gust,
            r.wind_direction,
            r.humidity,
            r.precipitation_probability,
            r.weather_code,
            r.cloud_cover,
            r.visibility,
            r.pressure_sea_level,
            r.pressure_surface_level,
            r.dew_point,
            r.uv_index,
            r.data_granularity,
        )
        for r in readings
    ]
    
    with get_cursor() as cur:
        # Use execute_values for efficient bulk insert
        execute_values(
            cur,
            """
            INSERT INTO weather_data (
                location_id, timestamp, temperature, temperature_apparent,
                wind_speed, wind_gust, wind_direction, humidity,
                precipitation_probability, weather_code, cloud_cover,
                visibility, pressure_sea_level, pressure_surface_level,
                dew_point, uv_index, data_granularity
            ) VALUES %s
            ON CONFLICT (location_id, timestamp, data_granularity) DO UPDATE SET
                temperature = EXCLUDED.temperature,
                temperature_apparent = EXCLUDED.temperature_apparent,
                wind_speed = EXCLUDED.wind_speed,
                wind_gust = EXCLUDED.wind_gust,
                wind_direction = EXCLUDED.wind_direction,
                humidity = EXCLUDED.humidity,
                precipitation_probability = EXCLUDED.precipitation_probability,
                weather_code = EXCLUDED.weather_code,
                cloud_cover = EXCLUDED.cloud_cover,
                visibility = EXCLUDED.visibility,
                pressure_sea_level = EXCLUDED.pressure_sea_level,
                pressure_surface_level = EXCLUDED.pressure_surface_level,
                dew_point = EXCLUDED.dew_point,
                uv_index = EXCLUDED.uv_index,
                fetched_at = NOW()
            """,
            data,
            page_size=1000,  # Process in batches for large inserts
        )
        
        rowcount = cur.rowcount
        
        logger.info(
            f"readings_inserted count={rowcount} location_id={readings[0].location_id if readings else None}"
        )
        
        return rowcount


def get_latest_by_location(
    granularity: str = "hourly"
) -> List[LocationSummary]:
    """Get the latest weather reading for each location.
    
    This answers the assignment question:
    "What's the latest temperature for each geolocation? What's the latest wind speed?"
    
    Args:
        granularity: Data granularity (minutely, hourly, daily)
        
    Returns:
        List of LocationSummary objects with latest readings
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (l.id)
                l.id as location_id,
                l.lat,
                l.lon,
                l.name,
                w.timestamp,
                w.temperature,
                w.wind_speed,
                w.humidity
            FROM locations l
            JOIN weather_data w ON w.location_id = l.id
            WHERE w.data_granularity = %s
              AND l.is_active = TRUE
            ORDER BY l.id, w.timestamp DESC
            """,
            (granularity,)
        )
        rows = cur.fetchall()
        
        summaries = [LocationSummary.model_validate(dict(row)) for row in rows]
        
        logger.info(f"latest_readings_fetched count={len(summaries)} granularity={granularity}")
        
        return summaries


def get_time_series(
    location_id: int,
    start_time: datetime,
    end_time: datetime,
    granularity: str = "hourly"
) -> List[WeatherReading]:
    """Get time series weather data for a location.
    
    This answers the assignment question:
    "Show an hourly time series of temperature from a day ago to 5 days in the future"
    
    Args:
        location_id: The location ID to query
        start_time: Start of time range (inclusive)
        end_time: End of time range (inclusive)
        granularity: Data granularity (minutely, hourly, daily)
        
    Returns:
        List of WeatherReading objects ordered by timestamp
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                location_id,
                timestamp,
                temperature,
                temperature_apparent,
                wind_speed,
                wind_gust,
                wind_direction,
                humidity,
                precipitation_probability,
                weather_code,
                cloud_cover,
                visibility,
                pressure_sea_level,
                pressure_surface_level,
                dew_point,
                uv_index,
                data_granularity
            FROM weather_data
            WHERE location_id = %s
              AND data_granularity = %s
              AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp ASC
            """,
            (location_id, granularity, start_time, end_time)
        )
        rows = cur.fetchall()
        
        readings = [WeatherReading.model_validate(dict(row)) for row in rows]
        
        logger.info(
            f"time_series_fetched location_id={location_id} granularity={granularity} "
            f"start={start_time.isoformat()} end={end_time.isoformat()} count={len(readings)}"
        )
        
        return readings


def get_data_availability(
    location_id: int,
    granularity: str = "hourly"
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Get the time range of available data for a location.
    
    Args:
        location_id: The location ID to query
        granularity: Data granularity
        
    Returns:
        Tuple of (earliest_timestamp, latest_timestamp) or (None, None) if no data
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                MIN(timestamp) as earliest,
                MAX(timestamp) as latest
            FROM weather_data
            WHERE location_id = %s
              AND data_granularity = %s
            """,
            (location_id, granularity)
        )
        row = cur.fetchone()
        
        if row and row["earliest"]:
            return (row["earliest"], row["latest"])
        return (None, None)


# =============================================================================
# Health Check
# =============================================================================


def health_check() -> bool:
    """Check database connectivity.
    
    Returns:
        True if database is reachable, False otherwise
    """
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            return True
    except psycopg2.Error as e:
        logger.error(f"health_check_failed: {e}")
        return False
