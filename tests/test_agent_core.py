# tests/test_agent_core.py
"""Tests for AgentRunner class.

TDD approach: These tests define the expected behavior.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

_FACTORY_SETTINGS = "src.core.agent.factory.settings"
_FACTORY_AGENT = "src.core.agent.factory.Agent"


def _mock_settings():
    """Create mock settings with test API key."""
    mock = MagicMock()
    mock.api_key = "test-api-key"
    mock.gemini_model = "gemini-3-flash-preview"
    return mock


class TestAgentRunnerInitialization:
    """Test AgentRunner initialization."""

    def test_agent_runner_initialization(self, monkeypatch):
        """Test AgentRunner initializes with FunctionToolset and creates Agent."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            runner = AgentRunner()

            # Verify Agent was created
            mock_agent_class.assert_called_once()
            call_args = mock_agent_class.call_args

            # Check model name starts with google-gla:
            assert call_args[0][0].startswith("google-gla:")

            # Check toolsets were passed (FunctionToolset-based architecture)
            assert "toolsets" in call_args[1]
            assert len(call_args[1]["toolsets"]) >= 1  # At least FunctionToolset

    def test_missing_api_key_raises_error(self, monkeypatch):
        """Test AgentRunner raises ValueError when API key is missing (fail-fast)."""
        with (
            patch(_FACTORY_AGENT),
            patch(_FACTORY_SETTINGS) as mock_settings,
        ):
            mock_settings.api_key = ""
            from src.core.agent.core import AgentRunner

            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                AgentRunner()


class TestAgentRunnerRun:
    """Test AgentRunner run method."""

    def test_run_method_returns_agent_run_result(self, monkeypatch):
        """Test run() method returns AgentRunResult with output and images."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            # Mock the agent's run method
            mock_agent = MagicMock()
            mock_result = MagicMock()
            mock_result.output = "Agent response"
            mock_result.all_messages = MagicMock(return_value=[])

            # Create async mock for run
            async def mock_run(*args, **kwargs):
                return mock_result

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner, AgentRunResult

            runner = AgentRunner()
            result = runner.run("Test task")

            # Verify result is AgentRunResult
            assert isinstance(result, AgentRunResult)
            assert result.output == "Agent response"
            assert isinstance(result.images, list)

    @pytest.mark.asyncio
    async def test_run_async_method(self, monkeypatch):
        """Test run_async() method works correctly."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            mock_result = MagicMock()
            mock_result.output = "Async response"
            mock_result.all_messages = MagicMock(return_value=[])

            async def mock_run(*args, **kwargs):
                return mock_result

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner, AgentRunResult

            runner = AgentRunner()
            result = await runner.run_async("Test task")

            assert isinstance(result, AgentRunResult)
            assert result.output == "Async response"

    @pytest.mark.asyncio
    async def test_run_async_with_user_method(self, monkeypatch):
        """Test run_async_with_user() method includes user context."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            mock_result = MagicMock()
            mock_result.output = "User-aware response"
            mock_result.all_messages = MagicMock(return_value=[])

            async def mock_run(prompt, *args, **kwargs):
                # Verify prompt includes user context
                assert "user_123" in prompt or "User ID" in prompt
                return mock_result

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            runner = AgentRunner()
            result = await runner.run_async_with_user("Test task", user_id="user_123")

            assert result.output == "User-aware response"


class TestAgentRunnerRetry:
    """Test AgentRunner retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, monkeypatch):
        """Test run_async() retries on 429 rate limit (3 attempts)."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            call_count = 0

            async def mock_run(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    # First two calls raise 429
                    response = httpx.Response(
                        429, request=httpx.Request("POST", "http://test")
                    )
                    raise httpx.HTTPStatusError(
                        "Rate limited", request=response.request, response=response
                    )
                # Third call succeeds
                mock_result = MagicMock()
                mock_result.output = "Success after retry"
                mock_result.all_messages = MagicMock(return_value=[])
                return mock_result

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            runner = AgentRunner()
            result = await runner.run_async("Test task")

            # Should have called run 3 times
            assert call_count == 3
            assert result.output == "Success after retry"

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, monkeypatch):
        """Test run_async() does NOT retry on 400 client error (1 attempt only)."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            call_count = 0

            async def mock_run(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # Always raise 400 (client error)
                response = httpx.Response(
                    400, request=httpx.Request("POST", "http://test")
                )
                raise httpx.HTTPStatusError(
                    "Bad request", request=response.request, response=response
                )

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            runner = AgentRunner()

            with pytest.raises(httpx.HTTPStatusError, match="Bad request"):
                await runner.run_async("Test task")

            # Should have called run only once (no retry on 400)
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, monkeypatch):
        """Test run_async() retries on 500 server error."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            call_count = 0

            async def mock_run(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    # First call raises 500
                    response = httpx.Response(
                        500, request=httpx.Request("POST", "http://test")
                    )
                    raise httpx.HTTPStatusError(
                        "Server error", request=response.request, response=response
                    )
                # Second call succeeds
                mock_result = MagicMock()
                mock_result.output = "Success after server error"
                mock_result.all_messages = MagicMock(return_value=[])
                return mock_result

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            runner = AgentRunner()
            result = await runner.run_async("Test task")

            # Should have retried
            assert call_count == 2
            assert result.output == "Success after server error"


class TestAgentRunnerMessageHistory:
    """Test AgentRunner message history functionality."""

    @pytest.mark.asyncio
    async def test_preserve_history_accumulates_messages(self, monkeypatch):
        """Test preserve_history=True accumulates messages across calls."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch(_FACTORY_AGENT) as mock_agent_class,
            patch(_FACTORY_SETTINGS, _mock_settings()),
        ):
            mock_agent = MagicMock()
            call_count = 0

            async def mock_run(prompt, *args, message_history=None, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_result = MagicMock()
                mock_result.output = f"Response {call_count}"
                # Return accumulated messages
                prev_msgs = list(message_history) if message_history else []
                mock_result.all_messages = MagicMock(
                    return_value=prev_msgs + [f"msg_{call_count}"]
                )
                return mock_result

            mock_agent.run = AsyncMock(side_effect=mock_run)
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            runner = AgentRunner()

            # First call
            result1 = await runner.run_async("Hello", preserve_history=True)
            assert result1.output == "Response 1"

            # Second call - should include history from first
            result2 = await runner.run_async("How are you?", preserve_history=True)
            assert result2.output == "Response 2"

            # History should have accumulated
            history = runner.get_history()
            assert len(history) == 2
            assert "msg_1" in history
            assert "msg_2" in history
