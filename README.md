# Tomorrow.io Weather Data Pipeline

[![CI](https://github.com/irensaltali/amperon-take-home/actions/workflows/ci.yml/badge.svg)](https://github.com/irensaltali/amperon-take-home/actions/workflows/ci.yml)
[![Docker](https://github.com/irensaltali/amperon-take-home/actions/workflows/docker.yml/badge.svg)](https://github.com/irensaltali/amperon-take-home/actions/workflows/docker.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-grade weather data ingestion system that fetches data from Tomorrow.io API for 10 geolocations, persists to PostgreSQL, and enables time-series analysis via Jupyter.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Tomorrow.io    │────▶│  Python ETL      │────▶│  PostgreSQL     │
│  API (Free)     │     │  (Containerized) │     │  (Time-series)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Jupyter Notebook│
                       │  (Analysis)      │
                       └──────────────────┘
```

## Features

- **No Hardcoded Locations**: 10 geolocations stored in database via migrations
- **API Validation**: Pydantic models validated against real API responses
- **Structured Logging**: JSON logs to stdout (Docker-captured), analyzed with `jq`
- **Migrations**: Every DB change uses yoyo-migrations
- **Observability**: Comprehensive logging via structlog
- **CI/CD**: GitHub Actions with automated testing

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Tomorrow.io API key ([get one free](https://www.tomorrow.io/))

### 1. Clone and Configure

```bash
git clone <repository-url>
cd amperon-take-home

# Copy environment template
cp .env.example .env

# Edit .env and add your API key
TOMORROW_API_KEY=your_api_key_here
```

### 2. Start Services

```bash
# Start all services (database, ETL pipeline, Jupyter notebook)
# On first start:
#   1. Database migrations run automatically
#   2. Initial data fetch from Tomorrow.io API
#   3. Scheduler starts for hourly updates
docker compose up -d
```

### 3. Verify Installation

```bash
# Check logs
docker compose logs -f tomorrow

# View structured logs with jq
docker compose logs tomorrow | jq 'select(.event == "pipeline_completed")'

# Open Jupyter Notebook for analysis
open http://localhost:8888
```

### Services Overview

After `docker compose up -d`, the following services are available:

| Service | URL | Description |
|---------|-----|-------------|
| PostgreSQL | `localhost:5432` | Database with weather data |
| ETL Pipeline | logs only | Background data ingestion |
| Jupyter | http://localhost:8888 | Data analysis notebook |

### Notebook Analysis

The `analysis.ipynb` notebook includes:
- **Query 1**: Latest temperature and wind speed by location
- **Query 2**: Hourly time series analysis (-1 day to +5 days)
- **Comparative Analysis**: Temperature variations across all 10 locations
- **Data Quality**: Record counts and availability metrics
- **Statistics**: Average, min, max values with heatmap visualization

## Usage

### CLI Commands

```bash
# Run pipeline once
python -m tomorrow run

# Start scheduler (runs hourly by default)
python -m tomorrow scheduler

# Start scheduler with minutely jobs
python -m tomorrow scheduler -m --minutely-interval 15

# Run database migrations
python -m tomorrow migrate
```

### Docker Commands

```bash
# Start all services
# - Migrations run automatically
# - Initial data fetch from API (fills database immediately)
# - Scheduler starts for hourly updates
docker compose up -d

# View ETL logs
docker compose logs -f tomorrow

# View Jupyter logs
docker compose logs -f jupyter

# Stop all services
docker compose down
```

## Project Structure

```
.
├── tomorrow/               # Main application code
│   ├── __main__.py        # CLI entry point
│   ├── config.py          # Pydantic settings
│   ├── models.py          # Pydantic models
│   ├── db.py              # Database operations
│   ├── client.py          # Tomorrow.io API client
│   ├── etl.py             # ETL pipeline
│   ├── scheduler.py       # APScheduler
│   ├── observability.py   # Structured logging
│   └── migrations.py      # Migration runner
├── tests/                  # Test suite (210 tests)
├── migrations/             # SQL migrations
├── scripts/                # Utility scripts
├── .github/workflows/      # CI/CD pipelines
├── docker-compose.yaml     # Docker orchestration
├── Dockerfile             # Container definition
├── analysis.ipynb         # Jupyter analysis notebook
└── README.md              # This file
```

## Assignment Queries

### Query 1: Latest Temperature and Wind Speed by Location

```sql
SELECT DISTINCT ON (l.id)
    l.name,
    l.lat,
    l.lon,
    w.timestamp,
    w.temperature,
    w.wind_speed
FROM locations l
LEFT JOIN weather_data w ON l.id = w.location_id
WHERE l.is_active = TRUE
ORDER BY l.id, w.timestamp DESC NULLS LAST;
```

### Query 2: Hourly Time Series (-1 Day to +5 Days)

```sql
SELECT 
    timestamp,
    temperature,
    wind_speed,
    humidity
FROM weather_data
WHERE location_id = 1
  AND data_granularity = 'hourly'
  AND timestamp BETWEEN NOW() - INTERVAL '1 day' AND NOW() + INTERVAL '5 days'
ORDER BY timestamp;
```

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run linting
ruff check tomorrow/ --ignore E501
ruff format tomorrow/

# Run audit
python scripts/audit.py
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TOMORROW_API_KEY` | Yes | - | Tomorrow.io API key |
| `PGHOST` | No | localhost | Database host |
| `PGPORT` | No | 5432 | Database port |
| `PGDATABASE` | No | tomorrow | Database name |
| `PGUSER` | No | postgres | Database user |
| `PGPASSWORD` | Yes | - | Database password |
| `LOG_LEVEL` | No | INFO | Logging level |

## Testing

The project includes comprehensive tests:

- **Unit Tests**: 210 tests covering all modules
- **E2E Tests**: Integration tests with database
- **Migration Tests**: Database schema validation

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_etl.py -v

# Run with coverage
pytest tests/ --cov=tomorrow --cov-report=html
```

## Observability

### Structured Logging

All logs are output as JSON to stdout for Docker capture:

```bash
# View all logs
docker compose logs tomorrow

# Filter specific events
docker compose logs tomorrow | jq 'select(.event == "pipeline_completed")'

# Calculate average pipeline duration
docker compose logs tomorrow | jq -s '[.[] | select(.event == "pipeline_completed") | .duration_seconds] | add / length'

# Find errors
docker compose logs tomorrow | jq 'select(.level == "error")'
```

### Log Format

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info",
  "event": "pipeline_completed",
  "locations_processed": 10,
  "readings_inserted": 1440,
  "duration_seconds": 45.2
}
```

## CI/CD

GitHub Actions workflows:

- **CI** (`.github/workflows/ci.yml`): Runs tests and linting on PR
- **Docker** (`.github/workflows/docker.yml`): Builds and pushes images

Required secrets:
- `GITHUB_TOKEN` (automatically provided)

## Database Schema

### Locations Table
- `id` (PK): Location identifier
- `lat`, `lon`: Coordinates (with constraints)
- `name`: Location name
- `is_active`: Boolean flag

### Weather Data Table
- Composite PK: `(location_id, timestamp, data_granularity)`
- All API fields: temperature, wind, humidity, pressure, etc.
- `fetched_at`: Ingestion timestamp
- Foreign key to locations

## License

MIT License - see LICENSE file for details

## Acknowledgments

- [Tomorrow.io](https://www.tomorrow.io/) for the weather API
- [Pydantic](https://docs.pydantic.dev/) for data validation
- [APScheduler](https://apscheduler.readthedocs.io/) for scheduling
- [structlog](https://www.structlog.org/) for structured logging
