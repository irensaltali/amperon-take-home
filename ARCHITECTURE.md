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
- Simple HTTP client for Tomorrow.io API
- Automatic retry for 5xx errors
- Rate limit handling (429)

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
└─────────────────┘       │ ... (all API fields)│
                          └─────────────────────┘
```

### Key Design Decisions

1. **Composite Primary Key**: `(location_id, timestamp, data_granularity)`
   - Prevents duplicate inserts for the same time/granularity

2. **UPSERT (ON CONFLICT)**: Idempotent inserts
   - Safe to re-run pipeline; updates existing records

3. **Indexes**:
   - Optimized for time-series and latest-value queries

## Error Handling Strategy

| Component | Error Type | Handling |
|-----------|-----------|----------|
| API Client | 429 Rate Limit | Raises TomorrowAPIRateLimitError |
| API Client | 5xx Server | Automatic Retry |
| API Client | Network/Timeout | Raises TomorrowAPIError |
| API Client | Other API Error | Raises TomorrowAPIError |
| ETL | API Error | Logs & Skips Location |
| ETL | DB Error | Logs & Fails Pipeline |

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
