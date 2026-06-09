from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Output logs as newline-delimited JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure the root logger.

    Parameters
    ----------
    log_level : str
        One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
    json_logs : bool
        If True, use JSON formatting (for production / container).
        If False, use plain text (for local development).
    """
    handler = logging.StreamHandler(sys.stdout)

    if json_logs:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level.upper())
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
