# Implementation Plan: Execution Roadmap

> **Branching Strategy**: GitHub Flow (feature branches → develop → main)
> **Branch Naming Convention**: `type/scope/description`
> **Merge Strategy**: Each step merges to `develop` via PR before next step begins

---

## Completed Steps

### ✅ Step 1.1: Migration Framework Setup
**Branch**: `feat/db/migrations-setup` (merged)

**Files**:
- `migrations/yoyo.ini`
- `migrations/README.md`
- `tomorrow/migrations.py`
- `tests/test_migrations.py`

**Features**:
- yoyo-migrations framework
- Migration runner module
- 12 comprehensive tests

---

### ✅ Step 1.2: Locations Table
**Branch**: `feat/db/locations-table` (merged)

**Files**:
- `migrations/001_create_locations_table.sql`
- `migrations/001_create_locations_table.rollback.sql`
- `migrations/002_insert_default_locations.sql`
- `migrations/002_insert_default_locations.rollback.sql`
- `tests/test_locations_migration.py`

**Features**:
- Locations table with constraints
- 10 default locations inserted via migration
- 18 comprehensive tests

---

### ✅ Step 1.3: Weather Data Table
**Branch**: `feat/db/weather-data-table` (merged)

**Files**:
- `migrations/003_create_weather_data_table.sql`
- `migrations/003_create_weather_data_table.rollback.sql`
- `tests/test_weather_data_migration.py`

**Features**:
- Weather data table with all API fields
- Composite PK, FK to locations
- 3 indexes for query patterns
- 19 comprehensive tests

---

## Remaining Steps

### Step 2.1: Pydantic Settings
**Branch**: `feat/config/pydantic-settings`
**Base**: `develop`

**Files**:
```
tomorrow/
├── config.py
.env.example
tests/
├── test_config.py
```

**Scope**:
- Pydantic Settings for environment variables
- `.env.example` documentation
- Config validation tests

**Acceptance Criteria**:
- [ ] Settings load from env vars
- [ ] Validation works
- [ ] Tests pass
- [ ] PR merged to `develop`

---

### Step 2.2: Pydantic API Models
**Branch**: `feat/models/api-pydantic-models`
**Base**: `develop` (after 2.1 merged)

**Files**:
```
tomorrow/
├── models.py
tests/
├── test_models.py
```

**Scope**:
- Models matching `wheather-api-response.json`:
  - `TimelineValues`
  - `TimelineEntry`
  - `TimelinesResponse`
  - `WeatherReading` (internal)
  - `Location` (internal)
- Field aliases for camelCase

**Acceptance Criteria**:
- [ ] Models parse API response JSON
- [ ] All fields mapped correctly
- [ ] Tests validate against real API structure
- [ ] PR merged to `develop`

---

### Step 3.1: Database Layer
**Branch**: `feat/db/database-layer`
**Base**: `develop` (after 2.2 merged)

**Files**:
```
tomorrow/
├── db.py
tests/
├── test_db.py
```

**Scope**:
- Connection pooling
- `get_active_locations()`
- `insert_readings()` with upsert
- `get_latest_by_location()`
- `get_time_series()`

**Acceptance Criteria**:
- [ ] All CRUD operations work
- [ ] Tests pass with test database
- [ ] PR merged to `develop`

---

### Step 3.2: API Client
**Branch**: `feat/client/tomorrow-api-client`
**Base**: `develop` (after 3.1 merged)

**Files**:
```
tomorrow/
├── client.py
tests/
├── test_client.py
```

**Scope**:
- HTTP client with requests
- Exponential backoff for retries
- `fetch_forecast(lat, lon)`
- `fetch_historical(lat, lon, start, end)`

**Acceptance Criteria**:
- [ ] Client fetches data from API
- [ ] Retries on 429 with backoff
- [ ] Mock tests with `respx`
- [ ] PR merged to `develop`

---

### Step 3.3: ETL Pipeline
**Branch**: `feat/etl/pipeline-orchestrator`
**Base**: `develop` (after 3.2 merged)

**Files**:
```
tomorrow/
├── etl.py
tests/
├── test_etl.py
```

**Scope**:
- `run_pipeline()` orchestrator
- Fetch locations from DB
- Transform and bulk insert
- Per-location error handling

**Acceptance Criteria**:
- [ ] Pipeline runs end-to-end
- [ ] Idempotent (safe to re-run)
- [ ] Tests pass
- [ ] PR merged to `develop`

---

### Step 4.1: Structured Logging
**Branch**: `feat/observability/structured-logging`
**Base**: `develop` (after 3.3 merged)

**Files**:
```
tomorrow/
├── logging_config.py
├── observability.py
tests/
├── test_observability.py
```

**Scope**:
- `structlog` configuration for JSON output
- `PipelineMetrics` context manager
- `timed_api_call()` decorator
- Integration with ETL

**Acceptance Criteria**:
- [ ] JSON logs to stdout
- [ ] Contextual fields (run_id, location_id, etc.)
- [ ] Logs visible in Docker
- [ ] Tests pass
- [ ] PR merged to `develop`

---

### Step 5.1: APScheduler
**Branch**: `feat/scheduler/apscheduler`
**Base**: `develop` (after 4.1 merged)

**Files**:
```
tomorrow/
├── scheduler.py
```

**Scope**:
- BlockingScheduler setup
- Hourly job configuration
- Immediate first run
- Prevent overlap

**Acceptance Criteria**:
- [ ] Scheduler runs hourly
- [ ] Prevents overlapping runs
- [ ] PR merged to `develop`

---

### Step 5.2: Entry Point
**Branch**: `feat/app/main-entry-point`
**Base**: `develop` (after 5.1 merged)

**Files**:
```
tomorrow/
├── __main__.py
```

**Scope**:
- Run migrations on startup
- Start scheduler
- Signal handling

**Acceptance Criteria**:
- [ ] `python -m tomorrow` works
- [ ] Migrations run before scheduler
- [ ] PR merged to `develop`

---

### Step 5.3: Docker Compose
**Branch**: `feat/docker/compose-updates`
**Base**: `develop` (after 5.2 merged)

**Files**:
```
docker-compose.yaml
```

**Scope**:
- Add `migrations` service
- Healthcheck for `tomorrow`
- Restart policy

**Acceptance Criteria**:
- [ ] `docker compose up --build` works
- [ ] PR merged to `develop`

---

### Step 6.1: Tests
**Branch**: `feat/tests/unit-integration`
**Base**: `develop` (after 5.3 merged)

**Scope**:
- Complete test coverage
- Mock API tests
- Database tests
- E2E pipeline test

**Acceptance Criteria**:
- [ ] >80% test coverage
- [ ] All tests pass
- [ ] PR merged to `develop`

---

### Step 6.2: CI/CD
**Branch**: `feat/ci/github-actions`
**Base**: `develop` (after 6.1 merged)

**Files**:
```
.github/workflows/ci.yml
```

**Scope**:
- GitHub Actions workflow
- PostgreSQL service
- Test execution
- Linting

**Acceptance Criteria**:
- [ ] CI runs on PR
- [ ] All checks pass
- [ ] PR merged to `develop`

---

### Step 7.1: Jupyter Notebook
**Branch**: `feat/analysis/jupyter-notebook`
**Base**: `develop` (after 6.2 merged)

**Files**:
```
analysis.ipynb
```

**Scope**:
- Latest temperature/wind queries
- Time series visualization
- Log analysis cells

**Acceptance Criteria**:
- [ ] Notebook connects to DB
- [ ] Queries work
- [ ] Visualizations display
- [ ] PR merged to `develop`

---

### Step 7.2: Documentation
**Branch**: `feat/docs/readme-and-docs`
**Base**: `develop` (after 7.1 merged)

**Files**:
```
README.md
```

**Scope**:
- Architecture overview
- Setup instructions
- Technology choices

**Acceptance Criteria**:
- [ ] README is comprehensive
- [ ] PR merged to `develop`

---

## Development Workflow

```bash
# 1. Start new step
git checkout develop
git pull origin develop
git checkout -b feat/scope/description

# 2. Work on feature
# ... make changes ...
# ... write tests ...

# 3. Commit
git commit -m "feat(scope): description"

# 4. Push and create PR
git push -u origin feat/scope/description
# Create PR targeting develop

# 5. After merge
git checkout develop
git pull origin develop
# Start next step
```

---

## Merge Checklist (Per PR)

- [ ] Code changes complete
- [ ] Tests added/updated
- [ ] All tests pass locally
- [ ] Migrations tested (if applicable)
- [ ] No hardcoded values
- [ ] Logging added (if applicable)
- [ ] Docstrings added
- [ ] PR reviewed
- [ ] CI checks pass
- [ ] Squash merge to `develop`
