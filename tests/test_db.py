"""Tests for database layer operations.

These tests verify:
- Connection pooling works correctly
- CRUD operations for locations and weather data
- Transaction handling (commit/rollback)
- Query patterns required by the assignment
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import psycopg2
from psycopg2 import sql


# =============================================================================
# Module-level setup to ensure correct environment
# =============================================================================

def _reset_test_environment():
    """Reset environment variables to known good values.
    
    This is needed because test_config.py uses @patch.dict(os.environ, ...)
    which changes environment variables and breaks subsequent database tests.
    """
    os.environ["TOMORROW_API_KEY"] = "test_api_key_for_tests"
    os.environ["PGPASSWORD"] = "postgres"
    os.environ["PGHOST"] = "localhost"
    os.environ["PGPORT"] = "5432"
    os.environ["PGDATABASE"] = "tomorrow"
    os.environ["PGUSER"] = "postgres"
    
    # Import and reload settings to pick up the new values
    from tomorrow.config import reload_settings
    reload_settings()

# Reset environment before importing db module
_reset_test_environment()

# Now import db modules (they will use the correct environment)
from tomorrow.db import (
    get_connection_pool,
    get_connection,
    get_cursor,
    close_all_connections,
    get_active_locations,
    get_location_by_id,
    get_location_by_coordinates,
    insert_readings,
    get_latest_by_location,
    get_time_series,
    get_data_availability,
    health_check,
)
from tomorrow.models import Location, WeatherReading, LocationSummary


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def reset_environment_session():
    """Reset environment before running any test_db tests.
    
    This is needed because test_config.py uses @patch.dict(os.environ, ...)
    which changes environment variables and breaks subsequent database tests.
    """
    _reset_test_environment()
    yield


@pytest.fixture(autouse=True)
def reset_connection_pool():
    """Reset connection pool before each test."""
    close_all_connections()
    yield
    close_all_connections()


@pytest.fixture
def sample_location():
    """Create a sample location for testing."""
    with get_cursor() as db_cursor:
        db_cursor.execute(
            """
            INSERT INTO locations (lat, lon, name, is_active)
            VALUES (1.1111, 1.1111, 'Test Location', TRUE)
            RETURNING id, lat, lon, name, is_active, created_at
            """
        )
        row = db_cursor.fetchone()
    loc = Location.model_validate(dict(row))
    yield loc
    # Cleanup - use fresh connection
    with get_cursor() as cleanup_cursor:
        cleanup_cursor.execute("DELETE FROM weather_data WHERE location_id = %s", (loc.id,))
        cleanup_cursor.execute("DELETE FROM locations WHERE id = %s", (loc.id,))


@pytest.fixture
def sample_weather_readings(sample_location):
    """Create sample weather readings for testing."""
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    readings = [
        WeatherReading(
            location_id=sample_location.id,
            timestamp=base_time + timedelta(hours=i),
            temperature=20.0 + i,
            wind_speed=5.0 + i,
            humidity=60.0 + i,
            data_granularity="hourly",
        )
        for i in range(5)
    ]
    
    insert_readings(readings)
    yield readings


# =============================================================================
# Connection Pool Tests
# =============================================================================

class TestConnectionPool:
    """Tests for connection pool management."""
    
    def test_get_connection_pool_singleton(self):
        """Should return same pool instance (singleton)."""
        pool1 = get_connection_pool()
        pool2 = get_connection_pool()
        assert pool1 is pool2
    
    def test_get_connection_context_manager(self):
        """Should provide working connection via context manager."""
        import psycopg2
        with get_connection() as conn:
            assert conn is not None
            # Use regular cursor (not RealDictCursor) for tuple access
            with conn.cursor(cursor_factory=psycopg2.extensions.cursor) as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                assert result[0] == 1
    
    def test_get_cursor_context_manager(self):
        """Should provide working cursor via context manager."""
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            assert result["?column?"] == 1
    
    def test_close_all_connections(self):
        """Should close all connections in pool."""
        pool = get_connection_pool()
        close_all_connections()
        
        # Should create new pool after closing
        new_pool = get_connection_pool()
        assert new_pool is not pool
    
    def test_connection_rollback_on_error(self):
        """Should rollback transaction on error."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO locations (lat, lon) VALUES (0, 0)")
                    raise Exception("Test error")
        except Exception:
            pass
        
        # Connection should be returned to pool (no hanging)
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM locations WHERE lat = 0 AND lon = 0")
            result = cur.fetchone()
            assert result["count"] == 0


# =============================================================================
# Location Operations Tests
# =============================================================================

class TestLocationOperations:
    """Tests for location CRUD operations."""
    
    def test_get_active_locations(self, sample_location):
        """Should return active locations only."""
        # Create inactive location
        with get_cursor() as db_cursor:
            db_cursor.execute(
                """
                INSERT INTO locations (lat, lon, name, is_active)
                VALUES (2.2222, 2.2222, 'Inactive Location', FALSE)
                RETURNING id
                """
            )
            inactive_id = db_cursor.fetchone()["id"]
        
        locations = get_active_locations()
        
        # Should include active location
        active_ids = [loc.id for loc in locations]
        assert sample_location.id in active_ids
        
        # Should not include inactive location
        assert inactive_id not in active_ids
        
        # Cleanup
        with get_cursor() as db_cursor:
            db_cursor.execute("DELETE FROM locations WHERE id = %s", (inactive_id,))
    
    def test_get_location_by_id_found(self, sample_location):
        """Should return location when found."""
        location = get_location_by_id(sample_location.id)
        
        assert location is not None
        assert location.id == sample_location.id
        assert location.lat == sample_location.lat
        assert location.lon == sample_location.lon
    
    def test_get_location_by_id_not_found(self):
        """Should return None when location not found."""
        location = get_location_by_id(99999)
        assert location is None
    
    def test_get_location_by_coordinates_found(self, sample_location):
        """Should return location when coordinates match."""
        location = get_location_by_coordinates(
            sample_location.lat,
            sample_location.lon
        )
        
        assert location is not None
        assert location.id == sample_location.id
    
    def test_get_location_by_coordinates_not_found(self):
        """Should return None when coordinates don't match."""
        location = get_location_by_coordinates(0.0, 0.0)
        assert location is None


# =============================================================================
# Weather Data Operations Tests
# =============================================================================

class TestWeatherDataOperations:
    """Tests for weather data CRUD operations."""
    
    def test_insert_readings_single(self, sample_location):
        """Should insert single reading."""
        reading = WeatherReading(
            location_id=sample_location.id,
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            temperature=25.5,
            wind_speed=5.2,
            humidity=65.0,
            data_granularity="hourly",
        )
        
        count = insert_readings([reading])
        
        assert count == 1
        
        # Verify insertion
        readings = get_time_series(
            sample_location.id,
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            "hourly"
        )
        assert len(readings) == 1
        assert readings[0].temperature == 25.5
    
    def test_insert_readings_multiple(self, sample_location):
        """Should insert multiple readings."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            WeatherReading(
                location_id=sample_location.id,
                timestamp=base_time + timedelta(hours=i),
                temperature=float(20 + i),
                data_granularity="hourly",
            )
            for i in range(10)
        ]
        
        count = insert_readings(readings)
        
        assert count == 10
    
    def test_insert_readings_empty_list(self):
        """Should handle empty list gracefully."""
        count = insert_readings([])
        assert count == 0
    
    def test_insert_readings_upsert(self, sample_location):
        """Should update existing readings on conflict."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # First insert
        reading1 = WeatherReading(
            location_id=sample_location.id,
            timestamp=timestamp,
            temperature=20.0,
            data_granularity="hourly",
        )
        insert_readings([reading1])
        
        # Second insert with same PK (should update)
        reading2 = WeatherReading(
            location_id=sample_location.id,
            timestamp=timestamp,
            temperature=25.0,  # Changed
            data_granularity="hourly",
        )
        insert_readings([reading2])
        
        # Verify update
        readings = get_time_series(
            sample_location.id,
            timestamp,
            timestamp,
            "hourly"
        )
        assert len(readings) == 1
        assert readings[0].temperature == 25.0
    
    def test_get_latest_by_location(self, sample_location, sample_weather_readings):
        """Should return latest reading for each location."""
        summaries = get_latest_by_location("hourly")
        
        # Find our sample location in results
        sample_summary = None
        for s in summaries:
            if s.location_id == sample_location.id:
                sample_summary = s
                break
        
        assert sample_summary is not None
        assert sample_summary.location_id == sample_location.id
        assert sample_summary.lat == sample_location.lat
        assert sample_summary.lon == sample_location.lon
        # Latest reading should have temperature 24.0 (20 + 4)
        assert sample_summary.temperature == 24.0
    
    def test_get_time_series(self, sample_location, sample_weather_readings):
        """Should return time series for location."""
        start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        
        readings = get_time_series(
            sample_location.id,
            start_time,
            end_time,
            "hourly"
        )
        
        assert len(readings) == 3  # 12:00, 13:00, 14:00
        
        # Check ordering (ascending by timestamp)
        assert readings[0].timestamp == start_time
        assert readings[1].timestamp == start_time + timedelta(hours=1)
        assert readings[2].timestamp == start_time + timedelta(hours=2)
    
    def test_get_time_series_empty(self, sample_location):
        """Should return empty list when no data."""
        start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        
        readings = get_time_series(
            sample_location.id,
            start_time,
            end_time,
            "hourly"
        )
        
        assert readings == []
    
    def test_get_data_availability(self, sample_location, sample_weather_readings):
        """Should return data time range."""
        earliest, latest = get_data_availability(sample_location.id, "hourly")
        
        assert earliest is not None
        assert latest is not None
        assert earliest < latest
    
    def test_get_data_availability_empty(self, sample_location):
        """Should return None when no data."""
        earliest, latest = get_data_availability(sample_location.id, "hourly")
        
        assert earliest is None
        assert latest is None


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthCheck:
    """Tests for database health check."""
    
    def test_health_check_success(self):
        """Should return True when DB is healthy."""
        assert health_check() is True
    
    def test_health_check_failure(self):
        """Should return False when DB is unreachable."""
        # Mock get_cursor to raise an exception
        from unittest.mock import patch
        import psycopg2
        
        with patch('tomorrow.db.get_cursor') as mock_get_cursor:
            mock_get_cursor.side_effect = psycopg2.Error("Connection failed")
            result = health_check()
            assert result is False


# =============================================================================
# Query Pattern Tests (Assignment Requirements)
# =============================================================================

class TestAssignmentQueries:
    """Tests for the specific queries required by the assignment."""
    
    def test_latest_temperature_and_wind_speed_query(self, sample_location):
        """Test: What's the latest temperature for each geolocation? What's the latest wind speed?"""
        # Insert test data
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            WeatherReading(
                location_id=sample_location.id,
                timestamp=base_time + timedelta(hours=i),
                temperature=float(20 + i),
                wind_speed=float(5 + i),
                humidity=60.0,
                data_granularity="hourly",
            )
            for i in range(3)
        ]
        insert_readings(readings)
        
        # Query latest readings for the specific test location
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (l.id)
                    l.lat,
                    l.lon,
                    w.timestamp,
                    w.temperature,
                    w.wind_speed
                FROM locations l
                JOIN weather_data w ON w.location_id = l.id
                WHERE w.data_granularity = 'hourly'
                  AND l.id = %s
                ORDER BY l.id, w.timestamp DESC
                """,
                (sample_location.id,)
            )
            result = cur.fetchone()
        
        assert result is not None
        assert result["temperature"] == 22.0  # Latest (20 + 2)
        assert result["wind_speed"] == 7.0   # Latest (5 + 2)
    
    def test_time_series_query(self, sample_location):
        """Test: Show an hourly time series of temperature from a day ago to 5 days in the future"""
        # Insert test data spanning 6 days
        base_time = datetime(2024, 1, 3, 12, 0, 0, tzinfo=timezone.utc)  # "Now"
        readings = [
            WeatherReading(
                location_id=sample_location.id,
                timestamp=base_time + timedelta(hours=i),
                temperature=float(i),
                data_granularity="hourly",
            )
            for i in range(-24, 120)  # -1 day to +5 days (exclusive end)
        ]
        insert_readings(readings)
        
        # Query: 1 day ago to 5 days in future
        start_time = base_time - timedelta(days=1)
        end_time = base_time + timedelta(days=5)
        
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, temperature
                FROM weather_data
                WHERE location_id = %s
                  AND data_granularity = 'hourly'
                  AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp
                """,
                (sample_location.id, start_time, end_time)
            )
            results = cur.fetchall()
        
        # Should have 6 days * 24 hours = 144 readings
        assert len(results) == 144
        
        # Check first reading (1 day ago)
        assert results[0]["timestamp"] == start_time
        assert results[0]["temperature"] == -24.0
        
        # Check last reading (1 hour before 5 days future)
        assert results[-1]["timestamp"] == end_time - timedelta(hours=1)
        assert results[-1]["temperature"] == 119.0
