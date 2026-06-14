"""Structured JSON logging to stdout.

One line of JSON per record so a container log collector can parse fields without
regex; stdout (not a file) is the 12-factor expectation for a containerized app.
"""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # Replace, don't append: every entry point calls this, so resetting handlers
    # keeps re-init (tests, uvicorn reload) from stacking duplicate log lines.
    root.handlers = [handler]
    root.setLevel(level.upper())
