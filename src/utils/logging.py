# src/utils/logging.py
"""Structured logging with JSON format and correlation ID support.

Provides:
- JSON-formatted log output for structured logging
- Request correlation ID via ContextVar for async-safe tracking
- Centralized logger configuration
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

# Request correlation ID for tracking requests across async contexts
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(request_id: str) -> None:
    """Set the request correlation ID for the current context.

    Args:
        request_id: Unique identifier for the request.
    """
    request_id_var.set(request_id)


def get_request_id() -> str:
    """Get the request correlation ID for the current context.

    Returns:
        Current request ID, or empty string if not set.
    """
    return request_id_var.get()


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Outputs log records as JSON with timestamp, level, logger name,
    message, and optional request_id for correlation.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON.

        Args:
            record: Log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Logger instance.
    """
    logger = logging.getLogger(name)
    return logger


def configure_structured_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging for the application.

    Sets up a StreamHandler with StructuredFormatter and applies
    it to the root logger.

    Args:
        level: Logging level (default: logging.INFO).
    """
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logging.root.addHandler(handler)
    logging.root.setLevel(level)
