"""Tests for observability module.

These tests verify:
- Logging configuration
- Structured log output
- Helper functions for metrics and events
"""

import json
import logging
import os
from io import StringIO
from unittest.mock import patch

import pytest
import structlog

# Set required environment variables for tests
os.environ.setdefault("TOMORROW_API_KEY", "test_api_key_for_tests")
os.environ.setdefault("PGPASSWORD", "postgres")

from tomorrow.observability import (
    configure_logging,
    get_logger,
    log_metric,
    log_pipeline_start,
    log_pipeline_complete,
    log_api_request,
    log_db_operation,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_structlog():
    """Reset structlog configuration before each test."""
    # Reset to default configuration
    structlog.reset_defaults()
    yield
    # Reset again after test
    structlog.reset_defaults()


@pytest.fixture
def capture_logs():
    """Capture log output for verification."""
    log_capture = StringIO()

    # Configure structlog to write to our capture (no extra logging_configured output)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=log_capture),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    yield log_capture


# =============================================================================
# Configuration Tests
# =============================================================================


class TestConfigureLogging:
    """Tests for logging configuration."""

    def test_configure_logging_json_format(self, capsys):
        """Should configure JSON logging."""
        # Configure only, don't use capture_logs fixture
        structlog.reset_defaults()
        configure_logging(log_level="INFO", json_format=True)

        logger = get_logger("test")
        logger.info("test_event", key="value")

        captured = capsys.readouterr()
        # Should be JSON format with our event
        assert "test_event" in captured.out
        assert "key" in captured.out

    def test_configure_logging_console_format(self, capsys):
        """Should configure console logging in dev mode."""
        structlog.reset_defaults()
        configure_logging(log_level="INFO", json_format=False)

        logger = get_logger("test")
        logger.info("test_event")

        captured = capsys.readouterr()
        # Should not be JSON in console mode
        assert "test_event" in captured.out

    def test_configure_logging_log_level(self, capsys):
        """Should respect log level setting."""
        structlog.reset_defaults()
        configure_logging(log_level="ERROR")

        logger = get_logger("test")

        # INFO should not be logged
        logger.info("info_message")
        captured = capsys.readouterr()
        assert "info_message" not in captured.out

        # ERROR should be logged
        logger.error("error_message")
        captured = capsys.readouterr()
        assert "error_message" in captured.out


# =============================================================================
# Logger Tests
# =============================================================================


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_name(self, capture_logs):
        """Should return logger with name bound."""
        logger = get_logger("my_module")
        logger.info("test_event")

        log_output = capture_logs.getvalue()
        # Get last line (the actual test event, not the configure_logging output)
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "test_event"
        assert log_data["logger_name"] == "my_module"

    def test_get_logger_without_name(self, capture_logs):
        """Should return logger without name binding."""
        logger = get_logger()
        logger.info("test_event")

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "test_event"


# =============================================================================
# Metric Logging Tests
# =============================================================================


class TestLogMetric:
    """Tests for log_metric function."""

    def test_log_metric_basic(self, capture_logs):
        """Should log metric with basic fields."""
        log_metric("pipeline_duration", 45.2, "seconds")

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "metric"
        assert log_data["metric_name"] == "pipeline_duration"
        assert log_data["value"] == 45.2
        assert log_data["unit"] == "seconds"

    def test_log_metric_with_tags(self, capture_logs):
        """Should log metric with additional tags."""
        log_metric(
            "api_requests",
            10,
            "count",
            status="success",
            endpoint="timelines",
        )

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["metric_name"] == "api_requests"
        assert log_data["status"] == "success"
        assert log_data["endpoint"] == "timelines"


# =============================================================================
# Pipeline Event Tests
# =============================================================================


class TestPipelineEvents:
    """Tests for pipeline event logging."""

    def test_log_pipeline_start(self, capture_logs):
        """Should log pipeline start event."""
        log_pipeline_start(
            location_count=10,
            granularity="hourly",
        )

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "pipeline_started"
        assert log_data["location_count"] == 10
        assert log_data["granularity"] == "hourly"

    def test_log_pipeline_complete_success(self, capture_logs):
        """Should log successful pipeline completion."""
        log_pipeline_complete(
            locations_processed=10,
            locations_failed=0,
            readings_inserted=1440,
            duration_seconds=45.234,
        )

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "pipeline_completed"
        assert log_data["locations_processed"] == 10
        assert log_data["locations_failed"] == 0
        assert log_data["readings_inserted"] == 1440
        assert log_data["duration_seconds"] == 45.234
        assert log_data["success"] is True

    def test_log_pipeline_complete_failure(self, capture_logs):
        """Should log failed pipeline completion."""
        log_pipeline_complete(
            locations_processed=8,
            locations_failed=2,
            readings_inserted=1152,
            duration_seconds=45.0,
        )

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["success"] is False


# =============================================================================
# API Request Logging Tests
# =============================================================================


class TestAPIRequestLogging:
    """Tests for API request logging."""

    def test_log_api_request(self, capture_logs):
        """Should log API request event."""
        log_api_request(
            location_id=1,
            lat=25.86,
            lon=-97.42,
            status="success",
            duration_ms=123.456,
        )

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "api_request"
        assert log_data["location_id"] == 1
        assert log_data["lat"] == 25.86
        assert log_data["lon"] == -97.42
        assert log_data["status"] == "success"
        assert log_data["duration_ms"] == 123.46  # Rounded


# =============================================================================
# Database Operation Logging Tests
# =============================================================================


class TestDBOperationLogging:
    """Tests for database operation logging."""

    def test_log_db_operation(self, capture_logs):
        """Should log database operation event."""
        log_db_operation(
            operation="insert",
            table="weather_data",
            rows_affected=1440,
            duration_ms=50.123,
        )

        log_output = capture_logs.getvalue()
        last_line = log_output.strip().split("\n")[-1]
        log_data = json.loads(last_line)

        assert log_data["event"] == "db_operation"
        assert log_data["operation"] == "insert"
        assert log_data["table"] == "weather_data"
        assert log_data["rows_affected"] == 1440
        assert log_data["duration_ms"] == 50.12  # Rounded
