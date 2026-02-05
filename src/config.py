# src/config.py
"""Application configuration using pydantic-settings.

Provides a centralized Settings class for all environment variables.
Supports both GOOGLE_API_KEY and GEMINI_API_KEY for backward compatibility.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings are loaded from .env file and environment variables.
    Environment variables take precedence over .env file values.
    """

    # Google Gemini API (supports both GOOGLE_API_KEY and GEMINI_API_KEY)
    google_api_key: str = ""
    gemini_api_key: str = ""  # Backward compatibility alias

    # Gemini Model Configuration
    gemini_model: str = "gemini-3-flash-preview"

    # Slack Integration
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # Observability
    logfire_token: str = ""

    # API Security
    api_auth_key: str = ""  # Required for API access (X-API-Key header)
    api_rate_limit: int = 60  # Requests per minute

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
        case_sensitive=False,  # Allow case-insensitive env var names
    )

    @property
    def api_key(self) -> str:
        """Get API key with fallback support.

        Returns GOOGLE_API_KEY if set, otherwise falls back to GEMINI_API_KEY.
        This ensures backward compatibility with existing code.

        Returns:
            The API key string, or empty string if neither is set.
        """
        return self.google_api_key or self.gemini_api_key


# Singleton instance - import this in your code
settings = Settings()
