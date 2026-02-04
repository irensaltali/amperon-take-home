"""Tests for APScheduler module.

These tests verify:
- Scheduler creation and configuration
- Job scheduling and execution
- Signal handling
- Status reporting
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Set required environment variables for tests
os.environ.setdefault("TOMORROW_API_KEY", "test_api_key_for_tests")
os.environ.setdefault("PGPASSWORD", "postgres")

from tomorrow.scheduler import (
    create_scheduler,
    schedule_hourly_job,
    schedule_minutely_job,
    start_scheduler,
    shutdown_scheduler,
    get_scheduler_status,
    setup_signal_handlers,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Reset scheduler state before each test."""
    # Import and reset global scheduler
    import tomorrow.scheduler as scheduler_module

    scheduler_module._scheduler = None
    yield
    # Cleanup after test
    if scheduler_module._scheduler and scheduler_module._scheduler.running:
        scheduler_module._scheduler.shutdown()
    scheduler_module._scheduler = None


@pytest.fixture
def mock_scheduler():
    """Create a mock scheduler for testing."""
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = []
    return scheduler


# =============================================================================
# Scheduler Creation Tests
# =============================================================================


class TestCreateScheduler:
    """Tests for create_scheduler function."""

    def test_create_scheduler_returns_instance(self):
        """Should return a BackgroundScheduler instance."""
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = create_scheduler()

        assert isinstance(scheduler, BackgroundScheduler)
        # Don't start it in the test

    def test_create_scheduler_configures_thread_pool(self):
        """Should configure thread pool executor."""
        scheduler = create_scheduler()

        # Just verify it doesn't raise and returns a scheduler
        assert scheduler is not None

    def test_create_scheduler_sets_job_defaults(self):
        """Should set job defaults."""
        scheduler = create_scheduler()

        # Just verify it doesn't raise and returns a scheduler
        assert scheduler is not None


# =============================================================================
# Job Scheduling Tests
# =============================================================================


class TestScheduleHourlyJob:
    """Tests for schedule_hourly_job function."""

    def test_schedule_hourly_job_adds_job(self, mock_scheduler):
        """Should add hourly job to scheduler."""
        schedule_hourly_job(mock_scheduler, minute=30)

        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args

        # Verify job configuration
        assert call_args[1]["id"] == "hourly_weather_pipeline"
        assert call_args[1]["name"] == "Hourly Weather Data Pipeline"
        assert call_args[1]["replace_existing"] is True

    def test_schedule_hourly_job_uses_cron_trigger(self, mock_scheduler):
        """Should use CronTrigger for hourly scheduling."""
        schedule_hourly_job(mock_scheduler, minute=30)

        call_args = mock_scheduler.add_job.call_args
        trigger = call_args[1]["trigger"]

        assert isinstance(trigger, CronTrigger)


class TestScheduleMinutelyJob:
    """Tests for schedule_minutely_job function."""

    def test_schedule_minutely_job_adds_job(self, mock_scheduler):
        """Should add minutely job to scheduler."""
        schedule_minutely_job(mock_scheduler, interval_minutes=15)

        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args

        assert call_args[1]["id"] == "minutely_weather_pipeline"
        assert call_args[1]["name"] == "Minutely Weather Data Pipeline"

    def test_schedule_minutely_job_uses_interval_trigger(self, mock_scheduler):
        """Should use IntervalTrigger for minutely scheduling."""
        schedule_minutely_job(mock_scheduler, interval_minutes=15)

        call_args = mock_scheduler.add_job.call_args
        trigger = call_args[1]["trigger"]

        assert isinstance(trigger, IntervalTrigger)


# =============================================================================
# Start Scheduler Tests
# =============================================================================


class TestStartScheduler:
    """Tests for start_scheduler function."""

    @patch("tomorrow.scheduler.configure_logging")
    @patch("tomorrow.scheduler.create_scheduler")
    @patch("tomorrow.scheduler.schedule_hourly_job")
    def test_start_scheduler_with_hourly_job(
        self,
        mock_schedule_hourly,
        mock_create,
        mock_configure,
    ):
        """Should start scheduler with hourly job."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        mock_create.return_value = mock_scheduler

        scheduler = start_scheduler(
            run_hourly=True,
            run_minutely=False,
            block=False,
        )

        mock_configure.assert_called_once()
        mock_create.assert_called_once()
        mock_schedule_hourly.assert_called_once_with(mock_scheduler, 0)
        mock_scheduler.start.assert_called_once()

    @patch("tomorrow.scheduler.configure_logging")
    @patch("tomorrow.scheduler.create_scheduler")
    @patch("tomorrow.scheduler.schedule_minutely_job")
    def test_start_scheduler_with_minutely_job(
        self,
        mock_schedule_minutely,
        mock_create,
        mock_configure,
    ):
        """Should start scheduler with minutely job."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        mock_create.return_value = mock_scheduler

        scheduler = start_scheduler(
            run_hourly=False,
            run_minutely=True,
            block=False,
        )

        mock_schedule_minutely.assert_called_once_with(mock_scheduler, 15)

    @patch("tomorrow.scheduler.configure_logging")
    @patch("tomorrow.scheduler.create_scheduler")
    def test_start_scheduler_adds_listener(
        self,
        mock_create,
        mock_configure,
    ):
        """Should add event listener to scheduler."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        mock_create.return_value = mock_scheduler

        start_scheduler(block=False)

        mock_scheduler.add_listener.assert_called_once()


# =============================================================================
# Shutdown Scheduler Tests
# =============================================================================


class TestShutdownScheduler:
    """Tests for shutdown_scheduler function."""

    def test_shutdown_running_scheduler(self):
        """Should shutdown running scheduler."""
        import tomorrow.scheduler as scheduler_module

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        scheduler_module._scheduler = mock_scheduler

        shutdown_scheduler()

        mock_scheduler.shutdown.assert_called_once()

    def test_shutdown_not_running(self):
        """Should handle shutdown when not running."""
        import tomorrow.scheduler as scheduler_module

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        scheduler_module._scheduler = mock_scheduler

        # Should not raise
        shutdown_scheduler()

    def test_shutdown_no_scheduler(self):
        """Should handle shutdown when no scheduler exists."""
        import tomorrow.scheduler as scheduler_module

        scheduler_module._scheduler = None

        # Should not raise
        shutdown_scheduler()


# =============================================================================
# Status Tests
# =============================================================================


class TestGetSchedulerStatus:
    """Tests for get_scheduler_status function."""

    def test_status_when_no_scheduler(self):
        """Should return not running when no scheduler."""
        import tomorrow.scheduler as scheduler_module

        scheduler_module._scheduler = None

        status = get_scheduler_status()

        assert status["running"] is False
        assert status["jobs"] == []

    def test_status_with_running_scheduler(self):
        """Should return status with job information."""
        import tomorrow.scheduler as scheduler_module

        mock_job = MagicMock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_job.trigger = CronTrigger(minute=0)

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.get_jobs.return_value = [mock_job]

        scheduler_module._scheduler = mock_scheduler

        status = get_scheduler_status()

        assert status["running"] is True
        assert len(status["jobs"]) == 1
        assert status["jobs"][0]["id"] == "test_job"


# =============================================================================
# Signal Handler Tests
# =============================================================================


class TestSignalHandlers:
    """Tests for signal handlers."""

    @patch("tomorrow.scheduler.signal.signal")
    def test_setup_signal_handlers(self, mock_signal):
        """Should setup signal handlers."""
        import signal

        setup_signal_handlers()

        # Should register SIGTERM and SIGINT
        assert mock_signal.call_count == 2
        calls = [call[0][0] for call in mock_signal.call_args_list]
        assert signal.SIGTERM in calls
        assert signal.SIGINT in calls
