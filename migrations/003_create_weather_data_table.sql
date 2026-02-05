--
-- Migration: Create weather_data table
-- Description: Stores time-series weather data from Tomorrow.io API
--

CREATE TABLE IF NOT EXISTS weather_data (
    -- Primary dimensions
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Data fields (raw from API to avoid data loss)
    -- Based on Tomorrow.io API response structure (wheather-api-response.json)
    temperature DECIMAL(6, 2),              -- Celsius (hourly/minutely)
    temperature_apparent DECIMAL(6, 2),     -- Feels like temp
    wind_speed DECIMAL(6, 2),               -- m/s
    wind_gust DECIMAL(6, 2),                -- m/s
    wind_direction INTEGER,                 -- Degrees (0-360)
    humidity DECIMAL(5, 2),                 -- % (0-100)
    precipitation_probability DECIMAL(5, 2), -- % (0-100)
    weather_code INTEGER,                   -- Tomorrow.io numeric code
    cloud_cover DECIMAL(5, 2),              -- % (0-100)
    visibility DECIMAL(8, 2),               -- km
    pressure_sea_level DECIMAL(8, 2),       -- hPa
    pressure_surface_level DECIMAL(8, 2),   -- hPa
    dew_point DECIMAL(6, 2),                -- Celsius
    uv_index INTEGER,                       -- 0-11+
    
    -- Metadata
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    data_granularity VARCHAR(10) CHECK (data_granularity IN ('minutely', 'hourly', 'daily')),
    
    -- Constraints
    PRIMARY KEY (location_id, timestamp, data_granularity)
);

-- Index for time-series queries (critical for the assignment)
-- Query pattern: SELECT ... WHERE location_id = X AND timestamp BETWEEN ...
CREATE INDEX IF NOT EXISTS idx_weather_data_time_lookup 
    ON weather_data(location_id, timestamp DESC);

-- Index for "latest" queries
-- Query pattern: SELECT ... WHERE location_id = X ORDER BY timestamp DESC LIMIT 1
CREATE INDEX IF NOT EXISTS idx_weather_data_latest 
    ON weather_data(location_id, data_granularity, timestamp DESC);

-- Index for observability queries
-- Query pattern: SELECT ... WHERE fetched_at > ...
CREATE INDEX IF NOT EXISTS idx_weather_data_fetched_at 
    ON weather_data(fetched_at DESC);

COMMENT ON TABLE weather_data IS 'Time-series weather data from Tomorrow.io API';
COMMENT ON COLUMN weather_data.location_id IS 'Foreign key to locations table';
COMMENT ON COLUMN weather_data.timestamp IS 'Timestamp of the weather reading (UTC)';
COMMENT ON COLUMN weather_data.temperature IS 'Temperature in Celsius';
COMMENT ON COLUMN weather_data.data_granularity IS 'Data granularity: minutely, hourly, or daily';
