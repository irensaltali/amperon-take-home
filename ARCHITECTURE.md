# Architecture Documentation

## System Overview

The Tomorrow.io Weather Data Pipeline is a containerized ETL system that:
1. Fetches weather data from Tomorrow.io API for 10 geolocations
2. Stores data in PostgreSQL with proper indexing
3. Runs on a scheduled basis (hourly by default)
4. Provides observability via structured logging

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                           │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   postgres   │◄───│  tomorrow    │    │   jupyter    │      │
│  │   (data)     │    │   (etl)      │    │  (analysis)  │      │
│  └──────────────┘    └──────┬───────┘    └──────────────┘      │
│         ▲                   │                                    │
│         │            ┌──────┴───────┐                           │
│         │            │  tomorrow.io │                           │
│         │            │     API      │                           │
│         │            └──────────────┘                           │
└─────────┼───────────────────────────────────────────────────────┘
          │
    ┌─────┴──────────┐
    │  logs (stdout) │
    └────────────────┘
```

## Data Flow

```
1. Scheduler triggers pipeline
   │
   ▼
2. Load locations from DB
   │
   ▼
3. Fetch weather from API (10 locations)
   │
   ▼
4. Transform API response → WeatherReading
   │
   ▼
5. Batch insert with UPSERT
   │
   ▼
6. Log results (JSON to stdout)
```

## Module Responsibilities

### `tomorrow/config.py`
- Pydantic Settings for environment variables
- Validation and defaults
- Settings caching

### `tomorrow/models.py`
- Pydantic models for API validation
- TimelineValues, TimelineEntry, TimelinesResponse
- Internal models: Location, WeatherReading

### `tomorrow/db.py`
- Connection pooling (psycopg2)
- CRUD operations for locations
- Weather data batch insert with UPSERT
- Assignment queries

### `tomorrow/client.py`
- HTTP client for Tomorrow.io API
- Automatic retry with exponential backoff
- Error handling (auth, rate limit, server errors)

### `tomorrow/etl.py`
- ETL pipeline orchestration
- Data transformation
- Result tracking

### `tomorrow/scheduler.py`
- APScheduler integration
- Job scheduling (hourly/minutely)
- Signal handling for graceful shutdown

### `tomorrow/observability.py`
- structlog configuration
- Structured logging helpers
- Metric logging

### `tomorrow/migrations.py`
- yoyo-migrations runner
- Database setup

## Database Design

### ER Diagram

```
┌─────────────────┐       ┌─────────────────────┐
│   locations     │       │    weather_data     │
├─────────────────┤       ├─────────────────────┤
│ id (PK)         │◄──────┤ location_id (FK)    │
│ lat             │       │ timestamp (PK)      │
│ lon             │       │ data_granularity(PK)│
│ name            │       │ temperature         │
│ is_active       │       │ wind_speed          │
│ created_at      │       │ humidity            │
└─────────────────┘       │ pressure_*          │
                          │ ... (all API fields)│
                          │ fetched_at          │
                          └─────────────────────┘
```

### Key Design Decisions

1. **Composite Primary Key**: `(location_id, timestamp, data_granularity)`
   - Allows same timestamp for different granularities
   - Prevents duplicate inserts

2. **UPSERT (ON CONFLICT)**: Idempotent inserts
   - Safe to re-run pipeline
   - Updates existing records

3. **Indexes**:
   - `idx_weather_time_lookup`: Time range queries
   - `idx_weather_latest`: Latest value queries
   - `idx_weather_fetched_at`: Data freshness

## Error Handling Strategy

| Component | Error Type | Handling |
|-----------|-----------|----------|
| API Client | 401 Auth | Raise TomorrowAPIAuthError |
| API Client | 429 Rate Limit | Raise TomorrowAPIRateLimitError |
| API Client | 5xx Server | Retry with backoff |
| API Client | Timeout | Retry with backoff |
| ETL | API Error | Log, continue with other locations |
| ETL | DB Error | Log, fail pipeline |
| Scheduler | Job Error | Log, continue scheduling |

## Scalability Considerations

### Current Limits
- **API Rate Limit**: 25 calls/day (free tier)
- **10 locations** × **1 call/hour** = **240 calls/day** (exceeds free tier)
- **Solution**: Upgrade to paid plan or reduce frequency

### Horizontal Scaling
- Multiple scheduler instances need coordination
- Consider Redis job queue for distributed processing

### Database Scaling
- Partitioning by `timestamp` for large datasets
- Read replicas for analytics queries

## Security

### Secrets Management
- API keys via environment variables
- Database passwords via environment variables
- No secrets in code or Docker images

### Database Security
- Connection pooling with limited connections
- Prepared statements (SQL injection prevention)
- Check constraints on coordinates

## Monitoring

### Key Metrics
- `pipeline_completed`: Duration, locations processed
- `api_request`: Latency, success rate
- `db_operation`: Insert duration, rows affected

### Alerting
- Pipeline failures
- Database connectivity issues
- API rate limit approaching

## Future Improvements

1. **Data Retention**: Automatic cleanup of old data
2. **Backup Strategy**: PostgreSQL backups
3. **Multi-region**: Support for different regions
4. **Web UI**: Simple dashboard for monitoring
5. **API Caching**: Redis cache for API responses
