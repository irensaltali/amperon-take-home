# Implementation Plan: Amperon Weather Data Pipeline

## Executive Summary

Build a production-grade weather data ingestion system that scrapes Tomorrow.io API for 10 geolocations hourly, persists to PostgreSQL, and enables time-series analysis via Jupyter. Target: zero technical debt, maximal observability, minimal complexity.

---

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Tomorrow.io    │────▶│  Python ETL     │────▶│  PostgreSQL     │
│  API (Free)     │     │  (Container)    │     │  (Time-series)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                          │
                               │    ┌─────────────────────┘
                               │    ▼
                               │ ┌─────────────────┐
                               │ │  Jupyter Lab    │
                               │ │  (Analysis)     │
                               │ └─────────────────┘
                               ▼
                        ┌─────────────────┐
                        │  Docker Logs    │
                        │  (Structured)   │
                        └─────────────────┘
```

---

## Phase 1: Foundation & Schema Design

### 1.1 Database Schema

**Decision**: Separate tables for locations (reference data) and weather data (time-series). Migrations-managed schema evolution.

#### Locations Table (Reference Data)

```sql
CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    lat DECIMAL(8, 4) NOT NULL,
    lon DECIMAL(8, 4) NOT NULL,
    name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_lat CHECK (lat BETWEEN -90 AND 90),
    CONSTRAINT valid_lon CHECK (lon BETWEEN -180 AND 180),
    CONSTRAINT unique_coordinates UNIQUE (lat, lon)
);
```

#### Weather Data Table (Time-Series)

```sql
CREATE TABLE weather_data (
    -- Primary dimensions
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Data fields (raw from API to avoid data loss)
    temperature DECIMAL(6, 2),
    temperature_apparent DECIMAL(6, 2),
    wind_speed DECIMAL(6, 2),
    wind_gust DECIMAL(6, 2),
    wind_direction INTEGER,
    humidity DECIMAL(5, 2),
    precipitation_probability DECIMAL(5, 2),
    weather_code INTEGER,
    cloud_cover DECIMAL(5, 2),
    visibility DECIMAL(8, 2),
    pressure_sea_level DECIMAL(8, 2),
    pressure_surface_level DECIMAL(8, 2),
    dew_point DECIMAL(6, 2),
    uv_index INTEGER,
    
    -- Metadata
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    data_granularity VARCHAR(10) CHECK (data_granularity IN ('minutely', 'hourly', 'daily')),
    
    -- Constraints
    PRIMARY KEY (location_id, timestamp, data_granularity)
);

-- Indexes
CREATE INDEX idx_weather_data_time_lookup ON weather_data(location_id, timestamp DESC);
CREATE INDEX idx_weather_data_latest ON weather_data(location_id, data_granularity, timestamp DESC);
CREATE INDEX idx_weather_data_fetched_at ON weather_data(fetched_at DESC);
```

### 1.2 Database Migration Strategy

**Tool**: `yoyo-migrations` (Python-native, SQL-based)

**Migration Files**:
- `001_create_locations_table.sql`
- `002_insert_default_locations.sql`
- `003_create_weather_data_table.sql`

### 1.3 Configuration

Create `tomorrow/config.py` with Pydantic Settings:
- Environment variable-based config
- No hardcoded credentials
- Locations loaded from DB

---

## Phase 2: Core Implementation

### 2.1 API Client (`tomorrow/client.py`)

**Pydantic Models** matching `wheather-api-response.json`:
```python
class TimelineValues(BaseModel):
    temperature: float | None = Field(None, alias="temperature")
    wind_speed: float | None = Field(None, alias="windSpeed")
    # ... all API fields

class TimelinesResponse(BaseModel):
    timelines: dict[Literal["minutely", "hourly", "daily"], list[TimelineEntry]]
```

### 2.2 Database Layer (`tomorrow/db.py`)

- Connection pooling
- `get_active_locations()` - query from DB
- `insert_readings()` - batch insert with upsert
- `get_latest_by_location()`
- `get_time_series()`

### 2.3 ETL Pipeline (`tomorrow/etl.py`)

**Flow**:
1. Fetch active locations from DB
2. For each location: fetch forecast + historical
3. Transform and bulk insert with upsert
4. Log metrics via structured logging

---

## Phase 3: Observability (Option A - Structured Logging)

### 3.1 Implementation

**Tool**: `structlog` for JSON-formatted logs to stdout

**Configuration** (`tomorrow/logging_config.py`):
```python
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ]
)
```

**Metrics Tracking** (`tomorrow/observability.py`):
```python
class PipelineMetrics:
    def __enter__(self):
        logger.info("pipeline_started", run_id=..., locations_count=...)
        
    def __exit__(self, ...):
        logger.info("pipeline_completed", run_id=..., duration_seconds=..., ...)
```

### 3.2 Viewing Logs

```bash
# Pretty JSON
docker compose logs tomorrow | jq .

# Filter events
docker compose logs tomorrow | jq 'select(.event == "pipeline_completed")'

# Statistics
docker compose logs tomorrow | jq -s '[.[] | select(.event == "pipeline_completed") | .duration_seconds] | add / length'
```

### 3.3 Visualization

- **Jupyter Notebook**: Parse logs with Python, plot with matplotlib
- **Python Script**: `scripts/analyze_logs.py` generates charts
- **jq**: Command-line analysis

See `docs/observability-option-a-guide.md` for complete guide.

---

## Phase 4: Scheduling & Deployment

### 4.1 Scheduler (`tomorrow/scheduler.py`)

```python
scheduler = BlockingScheduler()
scheduler.add_job(
    etl.run_pipeline,
    'interval',
    hours=1,
    next_run_time=datetime.now(),
    max_instances=1
)
```

### 4.2 Docker Compose

- Healthcheck for `tomorrow` service
- Migration service (runs before app)
- Restart policy: `unless-stopped`

---

## Phase 5: Testing & CI/CD

### 5.1 Testing
- Unit tests for API client
- Integration tests for DB
- E2E pipeline tests

### 5.2 GitHub Actions
- Test workflow with PostgreSQL service
- Branch protection rules

---

## Phase 6: Analysis & Documentation

### 6.1 Jupyter Notebook
- Latest temperature/wind queries
- Time series visualization
- Log analysis charts

### 6.2 Documentation
- README with setup instructions
- Architecture decisions
- API data structure

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| PostgreSQL | Assignment simplicity; handles this scale |
| yoyo-migrations | SQL-first, simple, version-controlled |
| APScheduler | Container-native, Python error handling |
| Pydantic | Runtime validation, type safety |
| **Structured Logging** | Zero infrastructure, Docker-native |
| Locations in DB | No hardcoding, configurable |

---

## Checklist

- [ ] Phase 1: Schema + Config
- [ ] Phase 2: Core Modules
- [ ] Phase 3: Observability (structured logging)
- [ ] Phase 4: Scheduling
- [ ] Phase 5: Testing
- [ ] Phase 6: CI/CD
- [ ] Phase 7: Documentation
