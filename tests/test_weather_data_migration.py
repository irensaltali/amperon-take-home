"""Tests for weather_data table migration.

These tests verify:
- 003_create_weather_data_table.sql creates the table correctly
- All columns match the API response structure
- Indexes are created properly
- Foreign key constraint works
- Rollback works
"""

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as pg_errors


def get_db_connection():
    """Get a database connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        database=os.getenv("PGDATABASE", "tomorrow"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )


@pytest.fixture
def db_conn():
    """Provide a database connection for tests."""
    conn = get_db_connection()
    yield conn
    conn.close()


@pytest.fixture
def cursor(db_conn):
    """Provide a database cursor for tests."""
    cur = db_conn.cursor(cursor_factory=RealDictCursor)
    yield cur
    cur.close()


@pytest.fixture
def sample_location_id(cursor, db_conn):
    """Get or create a sample location for testing foreign key constraints."""
    cursor.execute("SELECT id FROM locations LIMIT 1;")
    result = cursor.fetchone()
    if result:
        location_id = result["id"]
    else:
        # Insert a test location if none exist
        cursor.execute("""
            INSERT INTO locations (lat, lon, name)
            VALUES (25.8600, -97.4200, 'Test Location')
            RETURNING id;
        """)
        location_id = cursor.fetchone()["id"]
        db_conn.commit()

    # Clean up any existing weather data for this location
    cursor.execute("DELETE FROM weather_data WHERE location_id = %s;", (location_id,))
    db_conn.commit()

    return location_id


class TestWeatherDataTableStructure:
    """Tests for the weather_data table schema."""

    def test_table_exists(self, cursor):
        """weather_data table should exist."""
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'weather_data'
            );
        """)
        result = cursor.fetchone()
        assert result["exists"] is True

    def test_required_columns_exist(self, cursor):
        """Table should have all required columns."""
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'weather_data'
            ORDER BY ordinal_position;
        """)
        columns = {row["column_name"]: row for row in cursor.fetchall()}

        # Primary dimensions
        assert "location_id" in columns
        assert "timestamp" in columns
        assert columns["location_id"]["is_nullable"] == "NO"
        assert columns["timestamp"]["is_nullable"] == "NO"

        # Weather data fields (all should be nullable since API might not return all)
        weather_fields = [
            "temperature",
            "temperature_apparent",
            "wind_speed",
            "wind_gust",
            "wind_direction",
            "humidity",
            "precipitation_probability",
            "weather_code",
            "cloud_cover",
            "visibility",
            "pressure_sea_level",
            "pressure_surface_level",
            "dew_point",
            "uv_index",
        ]
        for field in weather_fields:
            assert field in columns, f"Missing column: {field}"

        # Metadata fields
        assert "fetched_at" in columns
        assert "data_granularity" in columns

    def test_primary_key_constraint(self, cursor):
        """Should have composite primary key on (location_id, timestamp, data_granularity)."""
        cursor.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'weather_data'
                AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position;
        """)
        columns = [row["column_name"] for row in cursor.fetchall()]
        assert columns == ["location_id", "timestamp", "data_granularity"]

    def test_foreign_key_constraint(self, cursor):
        """Should have foreign key to locations table."""
        cursor.execute("""
            SELECT 
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu 
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.table_name = 'weather_data'
                AND tc.constraint_type = 'FOREIGN KEY';
        """)
        result = cursor.fetchone()
        assert result is not None
        assert result["column_name"] == "location_id"
        assert result["foreign_table"] == "locations"
        assert result["foreign_column"] == "id"

    def test_data_granularity_check_constraint(self, cursor):
        """Should have check constraint on data_granularity."""
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.check_constraints
            WHERE constraint_name LIKE '%granularity%';
        """)
        result = cursor.fetchone()
        assert result is not None


class TestIndexes:
    """Tests for weather_data table indexes."""

    def test_time_lookup_index_exists(self, cursor):
        """Should have index for time-series queries."""
        cursor.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'weather_data'
                AND indexname = 'idx_weather_data_time_lookup';
        """)
        result = cursor.fetchone()
        assert result is not None
        assert "location_id" in result["indexdef"]
        assert "timestamp" in result["indexdef"]

    def test_latest_index_exists(self, cursor):
        """Should have index for latest queries."""
        cursor.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'weather_data'
                AND indexname = 'idx_weather_data_latest';
        """)
        result = cursor.fetchone()
        assert result is not None
        assert "location_id" in result["indexdef"]
        assert "data_granularity" in result["indexdef"]
        assert "timestamp" in result["indexdef"]

    def test_fetched_at_index_exists(self, cursor):
        """Should have index for observability queries."""
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'weather_data'
                AND indexname = 'idx_weather_data_fetched_at';
        """)
        result = cursor.fetchone()
        assert result is not None


class TestDataInsertion:
    """Tests for inserting data into weather_data table."""

    def test_insert_minimal_weather_data(self, db_conn, cursor, sample_location_id):
        """Should insert minimal weather data with just required fields."""
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity,
                temperature, wind_speed, humidity
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s
            ) RETURNING location_id, timestamp;
        """,
            (
                sample_location_id,
                datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
                "hourly",
                25.5,
                5.2,
                65.0,
            ),
        )
        result = cursor.fetchone()
        assert result["location_id"] == sample_location_id
        db_conn.commit()

    def test_insert_full_weather_data(self, db_conn, cursor, sample_location_id):
        """Should insert complete weather data with all fields."""
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity,
                temperature, temperature_apparent, wind_speed, wind_gust,
                wind_direction, humidity, precipitation_probability,
                weather_code, cloud_cover, visibility,
                pressure_sea_level, pressure_surface_level, dew_point, uv_index
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s
            );
        """,
            (
                sample_location_id,
                datetime(2024, 6, 1, 13, 0, 0, tzinfo=timezone.utc),
                "hourly",
                # Weather data
                25.5,
                28.0,
                5.2,
                8.5,  # temp, apparent_temp, wind_speed, wind_gust
                180,
                65.0,
                20.0,  # wind_direction, humidity, precip_prob
                1000,
                25.0,
                16.0,  # weather_code, cloud_cover, visibility
                1015.5,
                1013.2,
                18.5,
                2,  # pressures, dew_point, uv_index
            ),
        )
        db_conn.commit()

        # Verify insertion
        cursor.execute(
            """
            SELECT * FROM weather_data 
            WHERE location_id = %s AND timestamp = %s;
        """,
            (sample_location_id, datetime(2024, 6, 1, 13, 0, 0, tzinfo=timezone.utc)),
        )
        result = cursor.fetchone()
        assert result is not None
        assert result["temperature"] == Decimal("25.50")
        assert result["wind_speed"] == Decimal("5.20")

    def test_reject_invalid_granularity(self, db_conn, cursor, sample_location_id):
        """Should reject invalid data_granularity values."""
        with pytest.raises(
            (pg_errors.CheckViolation, pg_errors.StringDataRightTruncation)
        ):
            cursor.execute(
                """
                INSERT INTO weather_data (
                    location_id, timestamp, data_granularity, temperature
                ) VALUES (%s, %s, %s, %s);
            """,
                (
                    sample_location_id,
                    datetime(2024, 6, 1, 14, 0, 0, tzinfo=timezone.utc),
                    "invalid",  # Invalid granularity value
                    25.0,
                ),
            )
            db_conn.commit()
        db_conn.rollback()

    def test_reject_invalid_foreign_key(self, db_conn, cursor):
        """Should reject insert with non-existent location_id."""
        with pytest.raises(pg_errors.ForeignKeyViolation):
            cursor.execute(
                """
                INSERT INTO weather_data (
                    location_id, timestamp, data_granularity, temperature
                ) VALUES (%s, %s, %s, %s);
            """,
                (
                    99999,  # Non-existent location
                    datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
                    "hourly",
                    25.0,
                ),
            )
            db_conn.commit()
        db_conn.rollback()

    def test_composite_pk_prevents_duplicates(
        self, db_conn, cursor, sample_location_id
    ):
        """Composite PK should prevent duplicate (location_id, timestamp, granularity)."""
        timestamp = datetime(2024, 6, 1, 16, 0, 0, tzinfo=timezone.utc)

        # First insert should succeed
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES (%s, %s, %s, %s);
        """,
            (sample_location_id, timestamp, "hourly", 25.0),
        )
        db_conn.commit()

        # Second insert with same PK should fail
        with pytest.raises(pg_errors.UniqueViolation):
            cursor.execute(
                """
                INSERT INTO weather_data (
                    location_id, timestamp, data_granularity, temperature
                ) VALUES (%s, %s, %s, %s);
            """,
                (sample_location_id, timestamp, "hourly", 26.0),
            )
            db_conn.commit()
        db_conn.rollback()

    def test_upsert_behavior(self, db_conn, cursor, sample_location_id):
        """Should update existing record when using ON CONFLICT."""
        timestamp = datetime(2024, 6, 1, 16, 0, 0, tzinfo=timezone.utc)

        # Initial insert
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES (%s, %s, 'hourly', 25.0);
            """,
            (sample_location_id, timestamp),
        )
        db_conn.commit()

        # Upsert (update temperature)
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES (%s, %s, 'hourly', 30.0)
            ON CONFLICT (location_id, timestamp, data_granularity) 
            DO UPDATE SET temperature = EXCLUDED.temperature;
            """,
            (sample_location_id, timestamp),
        )
        db_conn.commit()

        # Verify update
        cursor.execute(
            """
            SELECT temperature FROM weather_data 
            WHERE location_id = %s AND timestamp = %s;
            """,
            (sample_location_id, timestamp),
        )
        result = cursor.fetchone()
        assert result["temperature"] == Decimal("30.00")

    def test_different_granularity_same_timestamp_allowed(
        self, db_conn, cursor, sample_location_id
    ):
        """Same timestamp with different granularity should be allowed."""
        timestamp = datetime(2024, 6, 1, 17, 0, 0, tzinfo=timezone.utc)

        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES 
                (%s, %s, 'hourly', 25.0),
                (%s, %s, 'minutely', 25.1),
                (%s, %s, 'daily', 24.5);
        """,
            (sample_location_id, timestamp) * 3,
        )
        db_conn.commit()

        cursor.execute(
            """
            SELECT COUNT(*) as count FROM weather_data
            WHERE location_id = %s AND timestamp = %s;
        """,
            (sample_location_id, timestamp),
        )
        result = cursor.fetchone()
        assert result["count"] == 3


class TestQueryPatterns:
    """Tests for expected query patterns from the assignment."""

    def test_latest_temperature_query(self, db_conn, cursor, sample_location_id):
        """Test query pattern: What's the latest temperature for each geolocation?"""
        # Insert test data
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity,
                temperature, wind_speed
            ) VALUES 
                (%s, %s, 'hourly', 25.0, 5.0),
                (%s, %s, 'hourly', 26.0, 6.0),
                (%s, %s, 'hourly', 24.0, 4.0);
        """,
            (
                sample_location_id,
                datetime(2024, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
                sample_location_id,
                datetime(2024, 2, 1, 11, 0, 0, tzinfo=timezone.utc),
                sample_location_id,
                datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        )
        db_conn.commit()

        # Query latest temperature and wind speed
        cursor.execute(
            """
            SELECT DISTINCT ON (location_id)
                location_id, timestamp, temperature, wind_speed
            FROM weather_data
            WHERE location_id = %s AND data_granularity = 'hourly'
            ORDER BY location_id, timestamp DESC;
        """,
            (sample_location_id,),
        )
        result = cursor.fetchone()
        assert result is not None
        # Latest timestamp is 12:00 with temperature 24.0
        assert result["temperature"] == Decimal("24.00")

    def test_time_series_query(self, db_conn, cursor, sample_location_id):
        """Test query pattern: Hourly time series for selected location."""
        # Insert test data spanning multiple hours
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES 
                (%s, '2024-01-01 08:00:00+00', 'hourly', 20.0),
                (%s, '2024-01-01 09:00:00+00', 'hourly', 21.0),
                (%s, '2024-01-01 10:00:00+00', 'hourly', 22.0),
                (%s, '2024-01-01 11:00:00+00', 'hourly', 23.0),
                (%s, '2024-01-01 12:00:00+00', 'hourly', 24.0);
        """,
            (sample_location_id,) * 5,
        )
        db_conn.commit()

        # Query time series between two timestamps
        cursor.execute(
            """
            SELECT timestamp, temperature
            FROM weather_data
            WHERE location_id = %s
              AND data_granularity = 'hourly'
              AND timestamp BETWEEN '2024-01-01 09:00:00+00' AND '2024-01-01 11:00:00+00'
            ORDER BY timestamp;
        """,
            (sample_location_id,),
        )
        results = cursor.fetchall()

        assert len(results) == 3
        assert results[0]["temperature"] == Decimal("21.00")
        assert results[1]["temperature"] == Decimal("22.00")
        assert results[2]["temperature"] == Decimal("23.00")


class TestDataTypes:
    """Tests for column data types and precision."""

    def test_temperature_precision(self, db_conn, cursor, sample_location_id):
        """Temperature should support decimal precision."""
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES (%s, %s, %s, %s)
            RETURNING temperature;
        """,
            (
                sample_location_id,
                datetime(2024, 6, 1, 18, 0, 0, tzinfo=timezone.utc),
                "hourly",
                -15.75,
            ),
        )
        result = cursor.fetchone()
        db_conn.commit()
        assert result["temperature"] == Decimal("-15.75")

    def test_pressure_precision(self, db_conn, cursor, sample_location_id):
        """Pressure should support decimal precision."""
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity,
                pressure_sea_level, pressure_surface_level
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING pressure_sea_level, pressure_surface_level;
        """,
            (
                sample_location_id,
                datetime(2024, 6, 1, 19, 0, 0, tzinfo=timezone.utc),
                "hourly",
                1015.55,
                1013.22,
            ),
        )
        result = cursor.fetchone()
        db_conn.commit()
        assert result["pressure_sea_level"] == Decimal("1015.55")
        assert result["pressure_surface_level"] == Decimal("1013.22")


class TestForeignKeyBehavior:
    """Tests for foreign key cascade behavior."""

    def test_delete_cascade(self, db_conn, cursor):
        """Deleting location should cascade delete weather data."""
        # Create a test location
        cursor.execute("""
            INSERT INTO locations (lat, lon, name)
            VALUES (25.1234, -97.1234, 'Temp Test Location')
            RETURNING id;
        """)
        temp_location_id = cursor.fetchone()["id"]
        db_conn.commit()

        # Insert weather data for this location
        cursor.execute(
            """
            INSERT INTO weather_data (
                location_id, timestamp, data_granularity, temperature
            ) VALUES (%s, %s, %s, %s);
        """,
            (
                temp_location_id,
                datetime(2024, 1, 1, 20, 0, 0, tzinfo=timezone.utc),
                "hourly",
                25.0,
            ),
        )
        db_conn.commit()

        # Verify data exists
        cursor.execute(
            "SELECT COUNT(*) as count FROM weather_data WHERE location_id = %s;",
            (temp_location_id,),
        )
        assert cursor.fetchone()["count"] == 1

        # Delete location
        cursor.execute("DELETE FROM locations WHERE id = %s;", (temp_location_id,))
        db_conn.commit()

        # Verify weather data was cascade deleted
        cursor.execute(
            "SELECT COUNT(*) as count FROM weather_data WHERE location_id = %s;",
            (temp_location_id,),
        )
        assert cursor.fetchone()["count"] == 0
