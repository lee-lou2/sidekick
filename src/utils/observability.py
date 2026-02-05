"""Observability configuration with Pydantic Logfire."""

import logging

from src.config import settings

logger = logging.getLogger(__name__)


def setup_logfire() -> None:
    """Configure Logfire for observability.

    Only activates if LOGFIRE_TOKEN environment variable is set.
    Call this at application startup before any agent operations.
    """
    if not settings.logfire_token:
        return

    try:
        import logfire

        logfire.configure(send_to_logfire="if-token-present")
        logfire.instrument_pydantic_ai()
        logfire.instrument_httpx(capture_all=True)
    except Exception as e:
        # Log but don't fail - observability is optional
        logger.warning("Failed to configure Logfire: %s", str(e))
