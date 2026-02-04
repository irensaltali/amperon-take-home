"""Scheduler for Tomorrow.io Weather Data Pipeline.

Uses APScheduler to run the ETL pipeline at regular intervals.
Configured for containerized deployment with background scheduling.

Example:
    # Start the scheduler (blocks indefinitely)
    from tomorrow.scheduler import start_scheduler
    start_scheduler()

View jobs:
    docker compose logs -f tomorrow
"""

import signal
import sys
import time
from typing import Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from tomorrow.config import get_settings
from tomorrow.etl import run_hourly_pipeline, run_minutely_pipeline
from tomorrow.observability import configure_logging, get_logger, log_metric

logger = get_logger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def create_scheduler() -> BackgroundScheduler:
    """Create and configure the background scheduler.

    Returns:
        Configured BackgroundScheduler instance
    """
    settings = get_settings()

    scheduler = BackgroundScheduler(
        {
            "apscheduler.jobstores.default": {
                "type": "memory",
            },
            "apscheduler.executors.default": {
                "class": "apscheduler.executors.pool:ThreadPoolExecutor",
                "max_workers": "2",
            },
            "apscheduler.job_defaults.coalesce": True,
            "apscheduler.job_defaults.max_instances": "1",
            "apscheduler.job_defaults.misfire_grace_time": "3600",  # 1 hour
        }
    )

    logger.info("scheduler_created", max_workers=2)
    return scheduler


def job_listener(event):
    """Listen for job events and log results."""
    if event.exception:
        logger.error(
            "job_failed",
            job_id=event.job_id,
            error=str(event.exception),
        )
    else:
        logger.info(
            "job_completed",
            job_id=event.job_id,
            retval=event.retval,
        )


def schedule_hourly_job(
    scheduler: BackgroundScheduler,
    minute: int = 0,
) -> None:
    """Schedule the hourly ETL pipeline job.

    Args:
        scheduler: APScheduler instance
        minute: Minute of the hour to run (0-59)
    """
    scheduler.add_job(
        run_hourly_pipeline,
        trigger=CronTrigger(minute=minute),
        id="hourly_weather_pipeline",
        name="Hourly Weather Data Pipeline",
        replace_existing=True,
    )

    logger.info(
        "hourly_job_scheduled",
        minute=minute,
        job_id="hourly_weather_pipeline",
    )


def schedule_minutely_job(
    scheduler: BackgroundScheduler,
    interval_minutes: int = 15,
) -> None:
    """Schedule the minutely ETL pipeline job.

    Args:
        scheduler: APScheduler instance
        interval_minutes: Minutes between runs
    """
    scheduler.add_job(
        run_minutely_pipeline,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="minutely_weather_pipeline",
        name="Minutely Weather Data Pipeline",
        replace_existing=True,
    )

    logger.info(
        "minutely_job_scheduled",
        interval_minutes=interval_minutes,
        job_id="minutely_weather_pipeline",
    )


def start_scheduler(
    run_hourly: bool = True,
    run_minutely: bool = False,
    hourly_minute: int = 0,
    minutely_interval: int = 15,
    block: bool = True,
) -> BackgroundScheduler:
    """Start the scheduler with configured jobs.

    This is the main entry point for running the scheduler.

    Args:
        run_hourly: Whether to schedule hourly pipeline
        run_minutely: Whether to schedule minutely pipeline
        hourly_minute: Minute of hour for hourly job
        minutely_interval: Interval in minutes for minutely job
        block: If True, block indefinitely; if False, return immediately

    Returns:
        Running BackgroundScheduler instance

    Example:
        # Run scheduler (blocks forever)
        start_scheduler()

        # Or run without blocking for testing
        scheduler = start_scheduler(block=False)
        # ... do other things ...
        scheduler.shutdown()
    """
    global _scheduler

    # Configure logging
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        json_format=True,
    )

    # Create scheduler
    scheduler = create_scheduler()
    _scheduler = scheduler

    # Add event listener
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Schedule jobs
    if run_hourly:
        schedule_hourly_job(scheduler, hourly_minute)

    if run_minutely:
        schedule_minutely_job(scheduler, minutely_interval)

    # Start scheduler
    scheduler.start()
    logger.info(
        "scheduler_started",
        run_hourly=run_hourly,
        run_minutely=run_minutely,
        jobs_count=len(scheduler.get_jobs()),
    )

    if block:
        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("scheduler_shutdown_signal_received")
            scheduler.shutdown()
            logger.info("scheduler_shutdown_complete")

    return scheduler


def shutdown_scheduler() -> None:
    """Shutdown the running scheduler.

    Safe to call even if scheduler is not running.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("scheduler_shutdown_complete")
    else:
        logger.warning("scheduler_not_running")


def get_scheduler_status() -> dict:
    """Get current scheduler status.

    Returns:
        Dictionary with scheduler status information
    """
    global _scheduler

    if not _scheduler:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
            }
        )

    return {
        "running": _scheduler.running,
        "jobs": jobs,
    }


def run_job_now(job_id: str) -> None:
    """Manually trigger a job to run immediately.

    Args:
        job_id: ID of the job to run

    Raises:
        ValueError: If job not found
    """
    global _scheduler

    if not _scheduler:
        raise RuntimeError("Scheduler not started")

    job = _scheduler.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    logger.info("manually_triggering_job", job_id=job_id)
    job.modify(next_run_time=None)  # Trigger immediately


# Signal handlers for graceful shutdown
def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("signal_received", signal=signum)
    shutdown_scheduler()
    sys.exit(0)


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    logger.info("signal_handlers_installed")
