# Database Migrations

This directory contains database migrations using [yoyo-migrations](https://ollycope.com/software/yoyo/latest/).

## Naming Convention

Migration files should be named with a sequential number prefix:

```
001_create_locations_table.sql
001_create_locations_table.rollback.sql
002_insert_default_locations.sql
002_insert_default_locations.rollback.sql
```

## Migration File Format

Each migration consists of two files:
1. `.sql` - Contains the forward migration (apply)
2. `.rollback.sql` - Contains the rollback migration (optional but recommended)

### Example Migration

**001_create_locations_table.sql**:
```sql
--
-- Migration: Create locations table
-- Description: What this migration does
--

CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);

CREATE INDEX idx_name ON locations(name);
```

**001_create_locations_table.rollback.sql**:
```sql
--
-- Rollback: Drop locations table
--

DROP TABLE IF EXISTS locations CASCADE;
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

## Migration Principles

1. **One change per migration** - Each migration should make a single logical change
2. **Always provide rollback** - Every migration should have a corresponding `.rollback.sql` file
3. **Immutable history** - Never modify existing migration files after they've been applied
4. **Idempotent operations** - Use `IF NOT EXISTS`, `IF EXISTS` where possible
5. **Test your rollbacks** - Always test that rollbacks work correctly
