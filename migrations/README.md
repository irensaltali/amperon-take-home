# Database Migrations

This directory contains database migrations using [yoyo-migrations](https://ollycope.com/software/yoyo/latest/).

## Naming Convention

Migration files should be named with a sequential number prefix:

```
001_create_locations_table.sql
002_insert_default_locations.sql
003_create_weather_data_table.sql
```

## Migration File Format

Each migration file must have two sections:

```sql
-- step:
CREATE TABLE example (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);

-- step_back:
DROP TABLE IF EXISTS example;
```

## Running Migrations

### Apply all pending migrations:
```bash
python -m tomorrow.migrations
```

### Check migration status:
```bash
python -m tomorrow.migrations --status
```

### Rollback migrations:
```bash
# Rollback last 1 migration
python -m tomorrow.migrations --rollback 1

# Rollback last 3 migrations
python -m tomorrow.migrations --rollback 3
```

### Using yoyo CLI directly:
```bash
cd migrations
yoyo apply
yoyo rollback
yoyo status
```

## Environment Variables

Migrations use the following environment variables:

- `PGHOST` - Database host (default: localhost)
- `PGPORT` - Database port (default: 5432)
- `PGDATABASE` - Database name (default: tomorrow)
- `PGUSER` - Database user (default: postgres)
- `PGPASSWORD` - Database password (default: postgres)
