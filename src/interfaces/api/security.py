# src/interfaces/api/security.py
"""API security: authentication and rate limiting."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

limiter = Limiter(key_func=get_remote_address)


def verify_api_key(api_key: Annotated[str | None, Depends(api_key_header)]) -> str:
    """Verify API key from X-API-Key header.

    Args:
        api_key: API key from header.

    Returns:
        Validated API key.

    Raises:
        HTTPException: 401 if key missing, 403 if key invalid.
    """
    if not settings.api_auth_key:
        # Auth disabled if no key configured
        return "auth_disabled"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include X-API-Key header.",
        )

    if not secrets.compare_digest(api_key, settings.api_auth_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key


def get_rate_limit_string() -> str:
    """Get rate limit string for slowapi.

    Returns:
        Rate limit string in format "N/minute".
    """
    return f"{settings.api_rate_limit}/minute"
