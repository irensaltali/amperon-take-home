"""Tests for __main__ entry point.

These tests verify:
- Command parsing
- Command execution
- Error handling
"""

import os
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

# Set required environment variables for tests
os.environ.setdefault("TOMORROW_API_KEY", "test_api_key_for_tests")
os.environ.setdefault("PGPASSWORD", "postgres")

from tomorrow.__main__ import (
    create_parser,
    cmd_run,
    cmd_scheduler,
    cmd_migrate,
    main,
)


# =============================================================================
# Parser Tests
# =============================================================================


class TestCreateParser:
    """Tests for argument parser."""

    def test_parser_creates_subparsers(self):
        """Should create subparsers for commands."""
        parser = create_parser()

        # Should have subparsers
        assert parser._subparsers is not None

    def test_run_command_parsing(self):
        """Should parse run command."""
        parser = create_parser()
        args = parser.parse_args(["run"])

        assert args.command == "run"
        assert args.func == cmd_run

    def test_scheduler_command_parsing_defaults(self):
        """Should parse scheduler command with defaults."""
        parser = create_parser()
        args = parser.parse_args(["scheduler"])

        assert args.command == "scheduler"
        assert args.func == cmd_scheduler
        assert args.minutely is False
        assert args.minutely_interval == 15

    def test_scheduler_command_parsing_with_options(self):
        """Should parse scheduler command with options."""
        parser = create_parser()
        args = parser.parse_args(["scheduler", "-m", "--minutely-interval", "30"])

        assert args.command == "scheduler"
        assert args.minutely is True
        assert args.minutely_interval == 30

    def test_migrate_command_parsing(self):
        """Should parse migrate command."""
        parser = create_parser()
        args = parser.parse_args(["migrate"])

        assert args.command == "migrate"
        assert args.func == cmd_migrate

    def test_no_command_parsing(self):
        """Should parse empty args without error."""
        parser = create_parser()

        # argparse doesn't exit for subparsers, just returns None
        args = parser.parse_args([])

        assert args.command is None


# =============================================================================
# Run Command Tests
# =============================================================================


class TestCmdRun:
    """Tests for run command."""

    @patch("tomorrow.__main__.health_check")
    @patch("tomorrow.__main__.run_hourly_pipeline")
    def test_run_success(self, mock_pipeline, mock_health):
        """Should return 0 on successful run."""
        mock_health.return_value = True

        # Create successful result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.locations_processed = 10
        mock_result.readings_inserted = 1440
        mock_result.duration_seconds = 45.0
        mock_result.errors = []
        mock_pipeline.return_value = mock_result

        args = Namespace()
        exit_code = cmd_run(args)

        assert exit_code == 0
        mock_health.assert_called_once()
        mock_pipeline.assert_called_once()

    @patch("tomorrow.__main__.health_check")
    def test_run_health_check_fails(self, mock_health):
        """Should return 1 when health check fails."""
        mock_health.return_value = False

        args = Namespace()
        exit_code = cmd_run(args)

        assert exit_code == 1
        mock_health.assert_called_once()

    @patch("tomorrow.__main__.health_check")
    @patch("tomorrow.__main__.run_hourly_pipeline")
    def test_run_pipeline_fails(self, mock_pipeline, mock_health):
        """Should return 1 when pipeline fails."""
        mock_health.return_value = True

        # Create failed result
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.locations_failed = 2
        mock_result.errors = ["Error 1", "Error 2"]
        mock_pipeline.return_value = mock_result

        args = Namespace()
        exit_code = cmd_run(args)

        assert exit_code == 1


# =============================================================================
# Scheduler Command Tests
# =============================================================================


class TestCmdScheduler:
    """Tests for scheduler command."""

    @patch("tomorrow.__main__.health_check")
    @patch("tomorrow.__main__.setup_signal_handlers")
    @patch("tomorrow.__main__.start_scheduler")
    def test_scheduler_success(self, mock_start, mock_signals, mock_health):
        """Should start scheduler successfully."""
        mock_health.return_value = True
        mock_start.return_value = None  # Blocks, but we mock it

        args = Namespace(minutely=False, minutely_interval=15)
        exit_code = cmd_scheduler(args)

        assert exit_code == 0
        mock_health.assert_called_once()
        mock_signals.assert_called_once()
        mock_start.assert_called_once_with(
            run_hourly=True,
            run_minutely=False,
            minutely_interval=15,
        )

    @patch("tomorrow.__main__.health_check")
    @patch("tomorrow.__main__.setup_signal_handlers")
    @patch("tomorrow.__main__.start_scheduler")
    def test_scheduler_with_minutely(self, mock_start, mock_signals, mock_health):
        """Should start scheduler with minutely jobs."""
        mock_health.return_value = True
        mock_start.return_value = None

        args = Namespace(minutely=True, minutely_interval=30)
        exit_code = cmd_scheduler(args)

        mock_start.assert_called_once_with(
            run_hourly=True,
            run_minutely=True,
            minutely_interval=30,
        )

    @patch("tomorrow.__main__.health_check")
    def test_scheduler_health_check_fails(self, mock_health):
        """Should return 1 when health check fails."""
        mock_health.return_value = False

        args = Namespace(minutely=False, minutely_interval=15)
        exit_code = cmd_scheduler(args)

        assert exit_code == 1

    @patch("tomorrow.__main__.health_check")
    @patch("tomorrow.__main__.setup_signal_handlers")
    @patch("tomorrow.__main__.start_scheduler")
    def test_scheduler_exception(self, mock_start, mock_signals, mock_health):
        """Should return 1 on scheduler exception."""
        mock_health.return_value = True
        mock_start.side_effect = Exception("Scheduler error")

        args = Namespace(minutely=False, minutely_interval=15)
        exit_code = cmd_scheduler(args)

        assert exit_code == 1


# =============================================================================
# Migrate Command Tests
# =============================================================================


class TestCmdMigrate:
    """Tests for migrate command."""

    @patch("tomorrow.__main__.run_migrations")
    def test_migrate_success(self, mock_migrations):
        """Should return 0 on successful migration."""
        mock_migrations.return_value = None

        args = Namespace()
        exit_code = cmd_migrate(args)

        assert exit_code == 0
        mock_migrations.assert_called_once()

    @patch("tomorrow.__main__.run_migrations")
    def test_migrate_failure(self, mock_migrations):
        """Should return 1 on migration failure."""
        mock_migrations.side_effect = Exception("Migration error")

        args = Namespace()
        exit_code = cmd_migrate(args)

        assert exit_code == 1


# =============================================================================
# Main Entry Point Tests
# =============================================================================


class TestMain:
    """Tests for main entry point."""

    @patch("tomorrow.__main__.create_parser")
    @patch("tomorrow.__main__.configure_logging")
    @patch("tomorrow.__main__.get_settings")
    def test_main_no_command(self, mock_settings, mock_logging, mock_parser):
        """Should print help and return 1 when no command."""
        mock_args = MagicMock()
        mock_args.command = None
        mock_parser.return_value.parse_args.return_value = mock_args

        exit_code = main()

        assert exit_code == 1
        mock_parser.return_value.print_help.assert_called_once()

    @patch("tomorrow.__main__.create_parser")
    @patch("tomorrow.__main__.configure_logging")
    @patch("tomorrow.__main__.get_settings")
    def test_main_successful_command(self, mock_settings, mock_logging, mock_parser):
        """Should execute command and return 0."""
        mock_args = MagicMock()
        mock_args.command = "run"
        mock_args.func.return_value = 0
        mock_parser.return_value.parse_args.return_value = mock_args

        exit_code = main()

        assert exit_code == 0
        mock_args.func.assert_called_once_with(mock_args)

    @patch("tomorrow.__main__.create_parser")
    @patch("tomorrow.__main__.configure_logging")
    @patch("tomorrow.__main__.get_settings")
    def test_main_failed_command(self, mock_settings, mock_logging, mock_parser):
        """Should return non-zero on command failure."""
        mock_args = MagicMock()
        mock_args.command = "run"
        mock_args.func.return_value = 1
        mock_parser.return_value.parse_args.return_value = mock_args

        exit_code = main()

        assert exit_code == 1

    @patch("tomorrow.__main__.create_parser")
    @patch("tomorrow.__main__.configure_logging")
    @patch("tomorrow.__main__.get_settings")
    def test_main_exception(self, mock_settings, mock_logging, mock_parser):
        """Should return 1 on exception."""
        mock_args = MagicMock()
        mock_args.command = "run"
        mock_args.func.side_effect = Exception("Command error")
        mock_parser.return_value.parse_args.return_value = mock_args

        exit_code = main()

        assert exit_code == 1
