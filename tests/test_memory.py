# tests/test_memory.py
"""Tests for memory module and user context functionality."""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMemoryPrompts:
    """Test memory prompt building functions."""

    def test_build_memory_prompt_includes_user_id(self):
        """Test that build_memory_prompt includes the user_id."""
        from src.core.memory import build_memory_prompt

        result = build_memory_prompt("U123456", "Hello agent", "slack")

        assert "U123456" in result
        assert "Hello agent" in result

    def test_build_memory_prompt_includes_platform(self):
        """Test that build_memory_prompt includes the platform."""
        from src.core.memory import build_memory_prompt

        result = build_memory_prompt("U123", "Test", "api")

        assert "api" in result

    def test_build_memory_prompt_default_platform(self):
        """Test that build_memory_prompt defaults to slack platform."""
        from src.core.memory import build_memory_prompt

        result = build_memory_prompt("U123", "Test")

        assert "slack" in result

    def test_build_memory_prompt_includes_memory_instructions(self):
        """Test that build_memory_prompt includes memory tool instructions."""
        from src.core.memory import build_memory_prompt

        result = build_memory_prompt("U123", "Test", "slack")

        assert "open_nodes" in result
        assert "user_U123" in result

    def test_memory_system_prompt_exists(self):
        """Test that MEMORY_SYSTEM_PROMPT is defined."""
        from src.core.memory import MEMORY_SYSTEM_PROMPT

        assert MEMORY_SYSTEM_PROMPT is not None
        assert len(MEMORY_SYSTEM_PROMPT) > 0
        assert "memory" in MEMORY_SYSTEM_PROMPT.lower()


class TestAgentRunnerUserContext:
    """Test AgentRunner with user context."""

    def test_run_with_user_calls_agent(self, monkeypatch):
        """Test that run_with_user calls the agent with context."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with patch("pydantic_ai.Agent") as mock_agent_class:
            mock_agent = MagicMock()
            mock_run_result = MagicMock()
            mock_run_result.output = "Response with memory"
            mock_run_result.all_messages.return_value = []
            mock_agent.run = AsyncMock(return_value=mock_run_result)
            mock_agent_class.return_value = mock_agent

            import src.core.agent.core as core_module

            importlib.reload(core_module)
            runner = core_module.AgentRunner()

            runner.run_with_user("Hello", "U123456", "slack")

            mock_agent.run.assert_called()
            call_args = mock_agent.run.call_args
            prompt = call_args[0][0]
            assert "U123456" in prompt
            assert "Hello" in prompt

    def test_run_with_user_returns_agent_run_result(self, monkeypatch):
        """Test that run_with_user returns AgentRunResult."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with patch("pydantic_ai.Agent") as mock_agent_class:
            mock_agent = MagicMock()
            mock_run_result = MagicMock()
            mock_run_result.output = "Test response"
            mock_run_result.all_messages.return_value = []
            mock_agent.run = AsyncMock(return_value=mock_run_result)
            mock_agent_class.return_value = mock_agent

            import src.core.agent.core as core_module

            importlib.reload(core_module)
            runner = core_module.AgentRunner()

            result = runner.run_with_user("Test", "U789", "api")

            assert hasattr(result, "output")
            assert hasattr(result, "images")
            assert result.output == "Test response"


class TestAPIUserContext:
    """Test API with user context."""

    @pytest.mark.asyncio
    async def test_execute_agent_with_user_id(self, monkeypatch):
        """Test that execute_agent uses run_async_with_user when user_id is provided."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from unittest.mock import patch

        from src.core.agent.core import AgentRunResult
        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.tasks import execute_agent

        mock_result = MagicMock(spec=AgentRunResult)
        mock_result.output = "Memory-aware response"
        mock_result.images = []

        mock_runner = MagicMock()
        mock_runner.run_async_with_user = AsyncMock(return_value=mock_result)
        mock_runner.run_async = AsyncMock(return_value=mock_result)
        mock_runner.close = MagicMock()

        with (
            patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner),
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
        ):
            mock_repo = MagicMock()
            mock_repo_func.return_value = mock_repo

            task_id = "test-user-context"
            request = RunRequest(
                prompt="Remember this",
                user_id="U123456",
                webhook_url=None,
            )

            await execute_agent(task_id, request)

            mock_runner.run_async_with_user.assert_called_once_with(
                "Remember this", "U123456", platform="api"
            )
            # Verify update was called with success
            mock_repo.update.assert_called()
            call_kwargs = mock_repo.update.call_args[1]
            assert call_kwargs["status"] == "success"
            assert call_kwargs["result"] == "Memory-aware response"

    @pytest.mark.asyncio
    async def test_execute_agent_without_user_id(self, monkeypatch):
        """Test that execute_agent uses run_async when user_id is not provided."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from unittest.mock import patch

        from src.core.agent.core import AgentRunResult
        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.tasks import execute_agent

        mock_result = MagicMock(spec=AgentRunResult)
        mock_result.output = "Standard response"
        mock_result.images = []

        mock_runner = MagicMock()
        mock_runner.run_async_with_user = AsyncMock(return_value=mock_result)
        mock_runner.run_async = AsyncMock(return_value=mock_result)
        mock_runner.close = MagicMock()

        with (
            patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner),
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
        ):
            mock_repo = MagicMock()
            mock_repo_func.return_value = mock_repo

            task_id = "test-no-user"
            request = RunRequest(
                prompt="Anonymous query",
                user_id=None,
                webhook_url=None,
            )

            await execute_agent(task_id, request)

            mock_runner.run_async.assert_called_once_with("Anonymous query")
            mock_runner.run_async_with_user.assert_not_called()
            # Verify update was called with success
            mock_repo.update.assert_called()
            call_kwargs = mock_repo.update.call_args[1]
            assert call_kwargs["status"] == "success"
