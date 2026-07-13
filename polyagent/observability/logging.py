"""Structured logging via structlog.

``configure_logging`` sets a sane default (ISO timestamp, level, console renderer).
``get_logger`` returns a bound logger. Structured fields attach with ``logger.bind(...)``.
"""

from __future__ import annotations

from typing import Any

import structlog


def configure_logging(level: int = 20) -> None:
    """Configure structlog globally. Idempotent; safe to call once at startup."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "polyagent") -> Any:
    return structlog.get_logger(name)
