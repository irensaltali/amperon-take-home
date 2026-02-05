"""Database migration runner using yoyo-migrations.

This module handles all database schema migrations. It runs migrations
on startup to ensure the database is always at the correct version.
"""

import os
import sys
from pathlib import Path

from yoyo import get_backend, read_migrations


MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def get_database_url() -> str:
    """Build database URL from environment variables.

    Returns:
        PostgreSQL connection URL.
    """
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    database = os.getenv("PGDATABASE", "tomorrow")
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "postgres")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def run_migrations() -> None:
    """Run all pending database migrations.

    This function:
    1. Connects to the database
    2. Loads migrations from the migrations directory
    3. Applies any pending migrations
    4. Rolls back on error

    Raises:
        SystemExit: If migrations fail to apply.
    """
    db_url = get_database_url()
    backend = get_backend(db_url)
    migrations = read_migrations(str(MIGRATIONS_DIR))

    print(
        f"Connecting to database: {db_url.replace(os.getenv('PGPASSWORD', 'postgres'), '***')}"
    )
    print(f"Found migrations directory: {MIGRATIONS_DIR}")

    with backend.lock():
        # Get pending migrations
        pending = backend.to_apply(migrations)

        if not pending:
            print("No pending migrations. Database is up to date.")
            return

        print(f"Applying {len(pending)} migration(s)...")

        try:
            backend.apply_migrations(pending)
            print(f"Successfully applied {len(pending)} migration(s).")

            # Print applied migration names
            for migration in pending:
                print(f"  ✓ {migration.id}")

        except Exception as e:
            print(f"ERROR: Migration failed: {e}", file=sys.stderr)
            backend.rollback_migrations(pending)
            raise SystemExit(1)


def rollback_migrations(steps: int = 1) -> None:
    """Rollback the last N migrations.

    Args:
        steps: Number of migrations to roll back.

    Raises:
        SystemExit: If rollback fails.
    """
    db_url = get_database_url()
    backend = get_backend(db_url)
    migrations = read_migrations(str(MIGRATIONS_DIR))

    print(f"Rolling back {steps} migration(s)...")

    with backend.lock():
        applied = backend.to_rollback(migrations)

        if not applied:
            print("No migrations to roll back.")
            return

        to_rollback = applied[:steps]

        try:
            backend.rollback_migrations(to_rollback)
            print(f"Successfully rolled back {len(to_rollback)} migration(s).")

            for migration in to_rollback:
                print(f"  ↺ {migration.id}")

        except Exception as e:
            print(f"ERROR: Rollback failed: {e}", file=sys.stderr)
            raise SystemExit(1)


def show_migration_status() -> None:
    """Display current migration status."""
    db_url = get_database_url()
    backend = get_backend(db_url)
    migrations = read_migrations(str(MIGRATIONS_DIR))

    print("\nMigration Status:")
    print("-" * 60)

    applied_ids = {m.id for m in backend.get_applied_migrations(migrations)}

    for migration in migrations:
        status = "✓ applied" if migration.id in applied_ids else "○ pending"
        print(f"  {status:12} {migration.id}")

    print("-" * 60)
    pending_count = len(backend.to_apply(migrations))
    print(f"Total: {len(migrations)} migration(s), {pending_count} pending\n")


def main() -> None:
    """Main entry point for running migrations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Database migration manager for Tomorrow.io pipeline"
    )
    parser.add_argument(
        "--rollback", type=int, metavar="STEPS", help="Rollback the last N migrations"
    )
    parser.add_argument("--status", action="store_true", help="Show migration status")

    args = parser.parse_args()

    if args.status:
        show_migration_status()
    elif args.rollback:
        rollback_migrations(args.rollback)
    else:
        run_migrations()


if __name__ == "__main__":
    main()
