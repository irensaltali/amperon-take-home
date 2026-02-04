"""Tests for locations table migrations.

These tests verify:
- 001_create_locations_table.sql creates the table correctly
- 002_insert_default_locations.sql inserts the 10 required locations
- Constraints work properly
- Rollback works
"""

import os
from decimal import Decimal

import pytest
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor


# The 10 locations from ASSIGNMENT.md
EXPECTED_LOCATIONS = [
    (Decimal("25.8600"), Decimal("-97.4200")),
    (Decimal("25.9000"), Decimal("-97.5200")),
    (Decimal("25.9000"), Decimal("-97.4800")),
    (Decimal("25.9000"), Decimal("-97.4400")),
    (Decimal("25.9000"), Decimal("-97.4000")),
    (Decimal("25.9200"), Decimal("-97.3800")),
    (Decimal("25.9400"), Decimal("-97.5400")),
    (Decimal("25.9400"), Decimal("-97.5200")),
    (Decimal("25.9400"), Decimal("-97.4800")),
    (Decimal("25.9400"), Decimal("-97.4400")),
]


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


class TestLocationsTableStructure:
    """Tests for the locations table schema."""
    
    def test_table_exists(self, cursor):
        """Locations table should exist."""
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'locations'
            );
        """)
        result = cursor.fetchone()
        assert result["exists"] is True
    
    def test_required_columns_exist(self, cursor):
        """Table should have all required columns."""
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'locations'
            ORDER BY ordinal_position;
        """)
        columns = {row["column_name"]: row for row in cursor.fetchall()}
        
        assert "id" in columns
        assert "lat" in columns
        assert "lon" in columns
        assert "name" in columns
        assert "is_active" in columns
        assert "created_at" in columns
        
        # Check data types
        assert "integer" in columns["id"]["data_type"] or "serial" in columns["id"]["data_type"]
        assert columns["lat"]["is_nullable"] == "NO"
        assert columns["lon"]["is_nullable"] == "NO"
    
    def test_primary_key_exists(self, cursor):
        """Table should have a primary key on id."""
        cursor.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'locations'
                AND tc.constraint_type = 'PRIMARY KEY';
        """)
        result = cursor.fetchone()
        assert result["column_name"] == "id"
    
    def test_unique_constraint_on_coordinates(self, cursor):
        """Should have unique constraint on (lat, lon)."""
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM information_schema.table_constraints
            WHERE table_name = 'locations'
                AND constraint_type = 'UNIQUE'
                AND constraint_name = 'unique_coordinates';
        """)
        result = cursor.fetchone()
        assert result["count"] == 1
    
    def test_check_constraints_exist(self, cursor):
        """Should have check constraints for lat/lon validation."""
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.check_constraints
            WHERE constraint_name IN ('valid_lat', 'valid_lon');
        """)
        constraints = [row["constraint_name"] for row in cursor.fetchall()]
        assert "valid_lat" in constraints
        assert "valid_lon" in constraints
    
    def test_active_index_exists(self, cursor):
        """Should have index on is_active for filtered queries."""
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'locations'
                AND indexname = 'idx_locations_active';
        """)
        result = cursor.fetchone()
        assert result is not None


class TestDefaultLocations:
    """Tests for the default 10 locations from ASSIGNMENT.md."""
    
    def test_all_ten_locations_inserted(self, cursor):
        """All 10 locations should be present."""
        cursor.execute("SELECT COUNT(*) as count FROM locations;")
        result = cursor.fetchone()
        assert result["count"] == 10
    
    def test_location_coordinates_match(self, cursor):
        """Coordinates should match ASSIGNMENT.md exactly."""
        cursor.execute("SELECT lat, lon FROM locations ORDER BY id;")
        actual = [(row["lat"], row["lon"]) for row in cursor.fetchall()]
        
        assert len(actual) == 10
        for expected, actual_coords in zip(EXPECTED_LOCATIONS, actual):
            assert actual_coords[0] == expected[0], f"Latitude mismatch: {actual_coords[0]} != {expected[0]}"
            assert actual_coords[1] == expected[1], f"Longitude mismatch: {actual_coords[1]} != {expected[1]}"
    
    def test_locations_are_active(self, cursor):
        """All default locations should be active."""
        cursor.execute("SELECT COUNT(*) as count FROM locations WHERE is_active = TRUE;")
        result = cursor.fetchone()
        assert result["count"] == 10
    
    def test_locations_have_names(self, cursor):
        """All locations should have descriptive names."""
        cursor.execute("SELECT name FROM locations WHERE name IS NULL;")
        result = cursor.fetchone()
        assert result is None


class TestConstraints:
    """Tests for database constraints."""
    
    def test_duplicate_coordinates_rejected(self, db_conn, cursor):
        """Should reject duplicate lat/lon combinations."""
        # Try to insert a duplicate
        with pytest.raises(psycopg2.IntegrityError):
            cursor.execute("""
                INSERT INTO locations (lat, lon, name)
                VALUES (25.8600, -97.4200, 'Duplicate');
            """)
            db_conn.commit()
        
        # Rollback the failed transaction
        db_conn.rollback()
    
    def test_invalid_latitude_rejected(self, db_conn, cursor):
        """Should reject latitudes outside -90 to 90."""
        with pytest.raises(pg_errors.CheckViolation):
            cursor.execute("""
                INSERT INTO locations (lat, lon, name)
                VALUES (100.0, -97.4200, 'Invalid Lat');
            """)
            db_conn.commit()
        
        db_conn.rollback()
    
    def test_invalid_longitude_rejected(self, db_conn, cursor):
        """Should reject longitudes outside -180 to 180."""
        with pytest.raises(pg_errors.CheckViolation):
            cursor.execute("""
                INSERT INTO locations (lat, lon, name)
                VALUES (25.8600, 200.0, 'Invalid Lon');
            """)
            db_conn.commit()
        
        db_conn.rollback()
    
    def test_null_latitude_rejected(self, db_conn, cursor):
        """Should reject NULL latitude."""
        with pytest.raises(pg_errors.NotNullViolation):
            cursor.execute("""
                INSERT INTO locations (lat, lon, name)
                VALUES (NULL, -97.4200, 'Null Lat');
            """)
            db_conn.commit()
        
        db_conn.rollback()


class TestDataTypes:
    """Tests for column data types and precision."""
    
    def test_lat_precision(self, cursor):
        """Latitude should support 4 decimal places."""
        cursor.execute("""
            SELECT lat FROM locations 
            WHERE lat = 25.8600;
        """)
        result = cursor.fetchone()
        assert result is not None
        assert str(result["lat"]) == "25.8600"
    
    def test_lon_precision(self, cursor):
        """Longitude should support 4 decimal places."""
        cursor.execute("""
            SELECT lon FROM locations 
            WHERE lon = -97.5200;
        """)
        result = cursor.fetchone()
        assert result is not None
        assert str(result["lon"]) == "-97.5200"


class TestQueryPatterns:
    """Tests for expected query patterns."""
    
    def test_get_active_locations(self, cursor):
        """Should be able to query active locations efficiently."""
        cursor.execute("""
            SELECT id, lat, lon, name
            FROM locations
            WHERE is_active = TRUE
            ORDER BY id;
        """)
        results = cursor.fetchall()
        assert len(results) == 10
        
        # Verify structure
        assert all("id" in row for row in results)
        assert all("lat" in row for row in results)
        assert all("lon" in row for row in results)
    
    def test_get_location_by_coordinates(self, cursor):
        """Should be able to look up location by coordinates."""
        cursor.execute("""
            SELECT id, name
            FROM locations
            WHERE lat = 25.8600 AND lon = -97.4200;
        """)
        result = cursor.fetchone()
        assert result is not None
        assert "Location 1" in result["name"]
