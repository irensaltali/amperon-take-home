# Amperon Weather Data Pipeline - Agent Guide

## Project Overview

This is a **data engineering take-home assignment** for Amperon. The goal is to build a weather data ingestion system that:

1. **Scrapes** the Tomorrow.io API for weather forecasts and historical data for 10 specific geographic locations
2. **Persists** the data to PostgreSQL with an optimized time-series schema
3. **Visualizes** the results via a Jupyter notebook with SQL queries

The system runs entirely in Docker containers locally (no cloud services required).

---

## Technology Stack

| Component | Technology | Version/Notes |
|-----------|------------|---------------|
| Language | Python | 3.11.7 (pinned in `.python-version` and `Dockerfile`) |
| Database | PostgreSQL | 16.2 (via Docker) |
| API Client | `requests` | For Tomorrow.io API calls |
| Scheduling | `APScheduler` | Python-native cron alternative |
| Data Validation | `pydantic` / `pydantic-settings` | Configuration and data models |
| Database Driver | `psycopg2-binary` | PostgreSQL adapter |
| Logging | `structlog` | Structured logging (planned) |
| Testing | `pytest` | Unit and integration tests |
| Notebook | `jupyter` | Data visualization |
| HTTP Mocking | `respx` | For testing API client |

---

## Project Structure

```
.
├── ASSIGNMENT.md          # Original assignment requirements
├── PLAN.md                # Detailed implementation plan (comprehensive)
├── docker-compose.yaml    # Container orchestration (3 services)
├── Dockerfile             # Python application image
├── requirements.txt       # Python dependencies (minimal baseline)
├── .python-version        # pyenv version file (3.11.7)
├── analysis.ipynb         # Jupyter notebook for visualization
│
├── tomorrow/              # Main Python package
│   ├── __init__.py        # (empty)
│   └── __main__.py        # Entry point (currently minimal logging setup)
│
├── tests/                 # Test suite
│   └── __init__.py        # (empty)
│
└── scripts/
    └── init-db.sql        # Database initialization script (placeholder)
```

---

## Docker Compose Architecture

Three services defined in `docker-compose.yaml`:

### 1. `postgres` (Database)
- **Image**: `postgres:16.2`
- **Port**: `5432:5432`
- **Credentials**: 
  - User: `postgres`
  - Password: `postgres`
  - Database: `tomorrow`
- **Volumes**:
  - `./scripts/init-db.sql` → `/docker-entrypoint-initdb.d/init.sql` (runs on startup)
  - `pgdata` (named volume for persistence)
- **Healthcheck**: Uses `pg_isready` to verify availability

### 2. `tomorrow` (ETL Application)
- **Build**: From local `Dockerfile`
- **Command**: `python -m tomorrow`
- **Depends on**: postgres (healthy)
- **Environment**: PostgreSQL connection settings
- **Volumes**: `./blobs:/tmp/blobs` (for data blobs if needed)

### 3. `jupyter` (Analysis Notebook)
- **Build**: Same `Dockerfile` as `tomorrow`
- **Command**: `jupyter notebook --ip 0.0.0.0 --NotebookApp.token='' --NotebookApp.password='' --allow-root`
- **Port**: `8888:8888`
- **Access**: http://localhost:8888 (no token/password required)
- **Depends on**: postgres (healthy)
- **Volumes**: `./analysis.ipynb:/app/analysis.ipynb`

---

## Development Commands

### Build and Start All Services
```bash
docker compose up --build
```

### Stop and Clean Up
```bash
docker compose down --volumes
```

### Access Jupyter Notebook
Navigate to http://localhost:8888 after services are running.

### Database Access (from host)
```bash
psql -h localhost -p 5432 -U postgres -d tomorrow
```
Password: `postgres`

---

## Key Configuration

### Environment Variables (for `tomorrow` and `jupyter` services)
| Variable | Default | Description |
|----------|---------|-------------|
| `PGHOST` | `postgres` | PostgreSQL hostname |
| `PGPORT` | `5432` | PostgreSQL port |
| `PGUSER` | `postgres` | PostgreSQL username |
| `PGPASSWORD` | `postgres` | PostgreSQL password |
| `PGDATABASE` | `tomorrow` | Database name |
| `TOMORROW_API_KEY` | (required) | Tomorrow.io API key (Free plan) |

### Required API Key
The application requires a Tomorrow.io API key. Create a `.env` file (not in git) with:
```bash
TOMORROW_API_KEY=your_api_key_here
```

---

## Planned Architecture (From PLAN.md)

The implementation plan (`PLAN.md`) outlines a comprehensive architecture:

### Database Schema
```sql
CREATE TABLE weather_data (
    lat DECIMAL(8, 4) NOT NULL,
    lon DECIMAL(8, 4) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature DECIMAL(5, 2),
    wind_speed DECIMAL(5, 2),
    humidity DECIMAL(5, 2),
    precipitation_probability DECIMAL(5, 2),
    weather_code VARCHAR(50),
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    data_type VARCHAR(10) CHECK (data_type IN ('forecast', 'historical')),
    PRIMARY KEY (lat, lon, timestamp, data_type)
);
```

### Module Structure (To Be Implemented)
- `tomorrow/config.py` - Pydantic settings with environment variables
- `tomorrow/models.py` - Pydantic data classes for API responses
- `tomorrow/client.py` - Tomorrow.io API client with retry logic
- `tomorrow/db.py` - Database operations with connection pooling
- `tomorrow/etl.py` - Pipeline orchestration
- `tomorrow/scheduler.py` - APScheduler setup for hourly runs

### Geolocations (10 locations in Texas)
| lat | lon |
|:---:|:---:|
| 25.8600 | -97.4200 |
| 25.9000 | -97.5200 |
| 25.9000 | -97.4800 |
| 25.9000 | -97.4400 |
| 25.9000 | -97.4000 |
| 25.9200 | -97.3800 |
| 25.9400 | -97.5400 |
| 25.9400 | -97.5200 |
| 25.9400 | -97.4800 |
| 25.9400 | -97.4400 |

---

## Testing Strategy

The `PLAN.md` specifies a three-tier testing approach:

1. **Unit Tests** (`tests/test_client.py`)
   - Mock API responses with `respx`
   - Test retry logic and rate limit handling
   - Test data transformation edge cases

2. **Integration Tests** (`tests/test_db.py`)
   - Test container PostgreSQL or transaction rollback
   - Test CRUD operations and constraint violations

3. **E2E Tests** (`tests/test_pipeline.py`)
   - Mock API + real database
   - Full pipeline execution verification

---

## Code Style Guidelines

Based on the project structure and `PLAN.md`:

- **No global state**: Everything should be injectable/testable
- **Type hints**: Use Python type annotations
- **Pydantic models**: Use for configuration and data validation
- **Structured logging**: Use `structlog` for observability
- **Docstrings**: All public functions should have docstrings
- **Idempotency**: Pipeline should be safe to re-run
- **Fail fast**: Validate configs at startup

---

## API Rate Limits

Tomorrow.io Free Plan: **500 calls/day**

Usage calculation:
- 10 locations × 1 call/hour = 240 calls/day
- Well within limits

---

## Current State

⚠️ **This is a baseline/template project**. The current implementation is minimal:

- `tomorrow/__main__.py` only sets up basic logging
- `scripts/init-db.sql` contains only a placeholder query
- `analysis.ipynb` has empty cells
- `requirements.txt` only has `pytest` and `jupyter`

The `PLAN.md` contains the comprehensive implementation plan to follow.

---

## Security Considerations

1. **API Key Management**: Use `.env` file (already in `.gitignore`)
2. **Database Credentials**: Hardcoded in docker-compose for local dev only
3. **Jupyter Security**: Token and password disabled for local dev (`--NotebookApp.token=''`)
4. **No Secrets in Git**: Never commit API keys or credentials

---

## Useful References

- **Tomorrow.io API Docs**: https://docs.tomorrow.io/reference/welcome
- **Assignment Requirements**: `ASSIGNMENT.md`
- **Implementation Plan**: `PLAN.md`
- **PostgreSQL Image**: https://hub.docker.com/_/postgres
