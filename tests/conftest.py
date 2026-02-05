# tests/conftest.py
"""Shared pytest fixtures for all test modules.

Provides common fixtures for:
- Singleton reset (SchedulerManager, etc.)
- Temporary database paths
- Mock environment variables
"""

import os
import tempfile
from collections.abc import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(scope="session", autouse=True)
def init_mcp_servers_cache() -> None:
    """Initialize MCP servers cache at session start.

    This ensures the MCP server configs (including guardrail rules) are
    cached before any test can clear _registered_servers. Without this,
    test ordering issues can cause guardrail tests to see an empty registry.
    """
    from src.tools.mcp_registry import get_mcp_servers

    get_mcp_servers()


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create a temporary database file path.

    Yields:
        Path to temporary SQLite database file.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def reset_scheduler_singleton() -> Generator[None, None, None]:
    """Reset SchedulerManager singleton before and after test.

    This fixture ensures each test gets a fresh SchedulerManager instance
    and cleans up properly after the test.
    """
    from src.core.scheduler.manager import SchedulerManager

    # Reset before test
    SchedulerManager._instance = None
    SchedulerManager._initialized = False

    yield

    # Reset after test
    if SchedulerManager._instance is not None:
        try:
            SchedulerManager._instance.shutdown(wait=False)
        except Exception:
            pass
    SchedulerManager._instance = None
    SchedulerManager._initialized = False


@pytest.fixture
def reset_toolset_singleton() -> Generator[None, None, None]:
    """Reset custom toolset singleton before and after test.

    This fixture ensures each test gets a fresh FunctionToolset instance.
    """
    import src.tools

    # Store original and reset
    original = src.tools._custom_toolset
    src.tools._custom_toolset = None

    yield

    # Restore
    src.tools._custom_toolset = original


@pytest.fixture
def mock_env_vars() -> Generator[dict[str, str], None, None]:
    """Provide mock environment variables for testing.

    Yields:
        Dictionary of mock environment variables that were set.
    """
    mock_vars = {
        "GOOGLE_API_KEY": "test-api-key",
        "GEMINI_MODEL": "gemini-test",
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_APP_TOKEN": "xapp-test-token",
    }

    with patch.dict(os.environ, mock_vars):
        yield mock_vars


@pytest.fixture
def temp_data_dir() -> Generator[str, None, None]:
    """Create a temporary data directory.

    Yields:
        Path to temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
