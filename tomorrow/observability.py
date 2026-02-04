"""Observability configuration for structured logging.

Uses structlog to produce JSON structured logs to stdout,
which are captured by Docker and can be analyzed with jq.

Example log output:
    {
        "timestamp": "2024-01-15T10:30:00Z",
        "level": "info",
        "event": "pipeline_completed",
        "locations_processed": 10,
        "readings_inserted": 1440,
        "duration_seconds": 45.2
    }

View logs:
    docker compose logs tomorrow | jq .
    docker compose logs tomorrow | jq 'select(.event == "pipeline_completed")'
    docker compose logs tomorrow | jq -s '[.[] | select(.event == "pipeline_completed") | .duration_seconds] | add / length'
"""

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    log_level: str = "INFO",
    json_format: bool = True,
) -> None:
    """Configure structured logging with structlog.

    Sets up both structlog and standard library logging to output
    JSON formatted logs to stdout for Docker capture.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, output JSON; if False, output plain text
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Define shared processors
    processors = [
        # Add timestamp in ISO format
        structlog.processors.TimeStamper(fmt="iso"),
        # Add log level
        structlog.processors.add_log_level,
        # Format exceptions nicely
        structlog.processors.format_exc_info,
    ]

    if json_format:
        # JSON output for production (Docker)
        processors.extend([
            # Render as JSON
            structlog.processors.JSONRenderer(),
        ])
    else:
        # Pretty console output for development
        processors.extend([
            structlog.dev.ConsoleRenderer(),
        ])

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Redirect standard library logging through structlog
    handler = logging.StreamHandler(sys.stdout)
    
    # Use a simple formatter that works with both JSON and console output
    if json_format:
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    # Update root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]

    # Get logger and log configuration
    logger = structlog.get_logger()
    logger.info(
        "logging_configured",
        log_level=log_level,
        json_format=json_format,
    )


def get_logger(name: str | None = None) -> Any:
    """Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        structlog logger bound with optional name

    Example:
        from tomorrow.observability import get_logger

        logger = get_logger(__name__)
        logger.info("pipeline_started", locations_count=10)
        logger.error("api_error", location_id=5, error="Timeout")
    """
    if name:
        return structlog.get_logger(name).bind(logger_name=name)
    return structlog.get_logger()


# Metrics tracking helpers
def log_metric(
    metric_name: str,
    value: float,
    unit: str = "count",
    **tags: Any,
) -> None:
    """Log a metric for observability.

    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement (count, seconds, bytes, etc.)
        **tags: Additional tags for the metric

    Example:
        log_metric("pipeline_duration", 45.2, "seconds", locations=10)
        log_metric("api_requests", 10, "count", status="success")
    """
    logger = get_logger("metrics")
    logger.info(
        "metric",
        metric_name=metric_name,
        value=value,
        unit=unit,
        **tags,
    )


def log_pipeline_start(
    location_count: int,
    granularity: str,
    **extra: Any,
) -> None:
    """Log pipeline start event.

    Args:
        location_count: Number of locations to process
        granularity: Data granularity (minutely, hourly, daily)
        **extra: Additional context
    """
    logger = get_logger("etl")
    logger.info(
        "pipeline_started",
        location_count=location_count,
        granularity=granularity,
        **extra,
    )


def log_pipeline_complete(
    locations_processed: int,
    locations_failed: int,
    readings_inserted: int,
    duration_seconds: float,
    **extra: Any,
) -> None:
    """Log pipeline completion event.

    Args:
        locations_processed: Number of successful locations
        locations_failed: Number of failed locations
        readings_inserted: Total readings inserted
        duration_seconds: Total execution time
        **extra: Additional context
    """
    logger = get_logger("etl")
    logger.info(
        "pipeline_completed",
        locations_processed=locations_processed,
        locations_failed=locations_failed,
        readings_inserted=readings_inserted,
        duration_seconds=round(duration_seconds, 3),
        success=locations_failed == 0,
        **extra,
    )


def log_api_request(
    location_id: int,
    lat: float,
    lon: float,
    status: str,
    duration_ms: float,
    **extra: Any,
) -> None:
    """Log API request event.

    Args:
        location_id: Location identifier
        lat: Latitude
        lon: Longitude
        status: Request status (success, error, timeout)
        duration_ms: Request duration in milliseconds
        **extra: Additional context
    """
    logger = get_logger("api")
    logger.info(
        "api_request",
        location_id=location_id,
        lat=lat,
        lon=lon,
        status=status,
        duration_ms=round(duration_ms, 2),
        **extra,
    )


def log_db_operation(
    operation: str,
    table: str,
    rows_affected: int,
    duration_ms: float,
    **extra: Any,
) -> None:
    """Log database operation event.

    Args:
        operation: Operation type (insert, update, select)
        table: Table name
        rows_affected: Number of rows affected
        duration_ms: Operation duration in milliseconds
        **extra: Additional context
    """
    logger = get_logger("db")
    logger.info(
        "db_operation",
        operation=operation,
        table=table,
        rows_affected=rows_affected,
        duration_ms=round(duration_ms, 2),
        **extra,
    )
