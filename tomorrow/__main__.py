"""Main entry point for Tomorrow.io Weather Data Pipeline.

Run with:
    python -m tomorrow

Or with Docker:
    docker compose up tomorrow

Commands:
    run         Run ETL pipeline once
    scheduler   Start scheduler for periodic runs
    migrate     Run database migrations

Environment variables:
    TOMORROW_API_KEY    Required: API key for Tomorrow.io
    PGHOST              Database host (default: localhost)
    PGPORT              Database port (default: 5432)
    PGDATABASE          Database name (default: tomorrow)
    PGUSER              Database user (default: postgres)
    PGPASSWORD          Required: Database password
    LOG_LEVEL           Logging level (default: INFO)
"""

import argparse
import sys

from tomorrow.config import get_settings
from tomorrow.db import health_check
from tomorrow.etl import run_hourly_pipeline, check_and_run_initial_fetch
from tomorrow.migrations import run_migrations
from tomorrow.observability import configure_logging, get_logger
from tomorrow.scheduler import setup_signal_handlers, start_scheduler

logger = get_logger(__name__)


def cmd_run(args: argparse.Namespace) -> int:
    """Run ETL pipeline once.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logger.info("run_command_started")

    # Check database health
    if not health_check():
        logger.error("database_health_check_failed")
        return 1

    # Run pipeline
    result = run_hourly_pipeline()

    if result.success:
        logger.info(
            "run_command_completed",
            locations_processed=result.locations_processed,
            readings_inserted=result.readings_inserted,
            duration_seconds=result.duration_seconds,
        )
        return 0
    else:
        logger.error(
            "run_command_failed",
            locations_failed=result.locations_failed,
            errors=result.errors,
        )
        return 1


def cmd_scheduler(args: argparse.Namespace) -> int:
    """Start scheduler for periodic pipeline runs.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for graceful shutdown, 1 for error)
    """
    logger.info("scheduler_command_started")

    # Check database health
    if not health_check():
        logger.error("database_health_check_failed")
        return 1

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()

    # Check for initial data and run pipeline if needed
    try:
        check_and_run_initial_fetch()
    except Exception as e:
        # Don't crash scheduler if initial check fails, just log it
        logger.error("initial_data_check_failed", error=str(e))

    # Start scheduler (blocks indefinitely)
    try:
        start_scheduler(
            run_hourly=True,
            run_minutely=args.minutely,
            minutely_interval=args.minutely_interval,
        )
        return 0
    except Exception as e:
        logger.error("scheduler_command_failed", error=str(e))
        return 1


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run database migrations.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logger.info("migrate_command_started")

    try:
        run_migrations()
        logger.info("migrate_command_completed")
        return 0
    except Exception as e:
        logger.error("migrate_command_failed", error=str(e))
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="tomorrow",
        description="Tomorrow.io Weather Data Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tomorrow run              # Run pipeline once
  python -m tomorrow scheduler        # Start hourly scheduler
  python -m tomorrow scheduler -m     # Start with minutely jobs
  python -m tomorrow migrate          # Run database migrations
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run ETL pipeline once",
    )
    run_parser.set_defaults(func=cmd_run)

    # Scheduler command
    scheduler_parser = subparsers.add_parser(
        "scheduler",
        help="Start scheduler for periodic runs",
    )
    scheduler_parser.add_argument(
        "-m",
        "--minutely",
        action="store_true",
        help="Also schedule minutely pipeline",
    )
    scheduler_parser.add_argument(
        "--minutely-interval",
        type=int,
        default=15,
        help="Minutely interval in minutes (default: 15)",
    )
    scheduler_parser.set_defaults(func=cmd_scheduler)

    # Migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Run database migrations",
    )
    migrate_parser.set_defaults(func=cmd_migrate)

    return parser


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Parse arguments first to get potential log level override
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Configure logging
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        json_format=True,
    )

    logger.info(
        "application_started",
        command=args.command,
        log_level=settings.log_level,
    )

    try:
        # Execute command
        exit_code = args.func(args)

        if exit_code == 0:
            logger.info("application_completed", command=args.command)
        else:
            logger.error(
                "application_failed", command=args.command, exit_code=exit_code
            )

        return exit_code

    except Exception as e:
        logger.exception("application_error", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
