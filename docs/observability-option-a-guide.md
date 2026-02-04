# Observability Option A: Structured Logging Guide

Complete guide for implementing, viewing, and visualizing structured logs using `structlog` with Docker.

---

## 1. Implementation

### 1.1 Install Dependencies

```bash
pip install structlog
```

### 1.2 Configure Structlog

Create `tomorrow/logging_config.py`:

```python
"""Structured logging configuration for the Tomorrow.io pipeline."""

import structlog


def configure_logging() -> None:
    """Configure structlog for JSON output to stdout."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "tomorrow"):
    """Get a configured logger instance."""
    return structlog.get_logger(name)
```

### 1.3 Pipeline Metrics

Create `tomorrow/observability.py`:

```python
"""Observability module for pipeline metrics."""

import time
from contextlib import contextmanager
from typing import Optional

from tomorrow.logging_config import get_logger

logger = get_logger("tomorrow.pipeline")


class PipelineMetrics:
    """Context manager for tracking pipeline execution."""
    
    def __init__(self, run_id: str, locations_count: int):
        self.run_id = run_id
        self.locations_count = locations_count
        self.start_time: Optional[float] = None
        self.locations_processed = 0
        self.locations_failed = 0
        self.records_inserted = 0
        
    def __enter__(self):
        self.start_time = time.time()
        logger.info(
            "pipeline_started",
            run_id=self.run_id,
            locations_count=self.locations_count,
            timestamp=time.time()
        )
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        status = "failure" if exc_type else "success"
        
        logger.info(
            "pipeline_completed",
            run_id=self.run_id,
            status=status,
            duration_seconds=round(duration, 3),
            locations_processed=self.locations_processed,
            locations_failed=self.locations_failed,
            records_inserted=self.records_inserted,
            error=str(exc_val) if exc_val else None
        )
```

---

## 2. Viewing Logs

```bash
# Pretty JSON
docker compose logs tomorrow | jq .

# Filter events
docker compose logs tomorrow | jq 'select(.event == "pipeline_completed")'

# Average duration
docker compose logs tomorrow | \
  jq -s '[.[] | select(.event == "pipeline_completed") | .duration_seconds] | add / length'
```

---

## 3. Visualization

See Jupyter notebook examples in `analysis.ipynb` for plotting pipeline metrics.

---

## Summary

| Task | Command |
|------|---------|
| View logs | `docker compose logs tomorrow` |
| Pretty JSON | `docker compose logs tomorrow \| jq .` |
| Filter | `docker compose logs tomorrow \| jq 'select(.event == "...")'` |
| Real-time | `docker compose logs -f tomorrow` |

Zero infrastructure observability!
