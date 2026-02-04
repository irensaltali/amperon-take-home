--
-- Migration: Create locations table
-- Description: Stores the 10 geographic locations for weather data collection
--

CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    lat DECIMAL(8, 4) NOT NULL,
    lon DECIMAL(8, 4) NOT NULL,
    name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_lat CHECK (lat BETWEEN -90 AND 90),
    CONSTRAINT valid_lon CHECK (lon BETWEEN -180 AND 180),
    CONSTRAINT unique_coordinates UNIQUE (lat, lon)
);

CREATE INDEX IF NOT EXISTS idx_locations_active ON locations(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE locations IS 'Reference table for geographic locations being monitored';
COMMENT ON COLUMN locations.lat IS 'Latitude coordinate (-90 to 90)';
COMMENT ON COLUMN locations.lon IS 'Longitude coordinate (-180 to 180)';
COMMENT ON COLUMN locations.is_active IS 'Whether this location should be included in data collection';
