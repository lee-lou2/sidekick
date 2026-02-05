# tests/test_slack_bot.py
"""Tests for Slack bot implementation.

TDD approach: These tests define expected behavior for the async Slack bot
with lazy listeners for @mentions, DMs, and emoji reactions.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSlackBotEventHandlers:
    """Test Slack bot event handler registration."""

    def test_app_mention_handler_registered(self, monkeypatch):
        """Test app_mention event handler is registered."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        # Check that app_mention handler functions are defined
        assert callable(bot_module.ack_mention)
        assert callable(bot_module.process_mention)
        # Check that app is an AsyncApp instance
        assert bot_module.app is not None

    def test_reaction_added_handler_registered(self, monkeypatch):
        """Test reaction_added event handler is registered."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        # Verify reaction handler functions are defined
        assert callable(bot_module.ack_reaction)
        assert callable(bot_module.process_reaction)
        assert bot_module.app is not None

    def test_dm_message_handler_registered(self, monkeypatch):
        """Test DM message event handler is registered."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module
        import src.interfaces.slack.handlers as handlers_module

        importlib.reload(bot_module)

        # Verify DM handler function is defined
        # handle_message is the public interface in bot.py
        assert callable(bot_module.handle_message)
        # ack_dm and process_dm are internal to handlers module
        assert callable(handlers_module.ack_dm)
        assert callable(handlers_module.process_dm)


class TestSlackBotLazyListeners:
    """Test lazy listener pattern for long-running operations."""

    @pytest.mark.asyncio
    async def test_mention_ack_function(self, monkeypatch):
        """Test that mention ack function calls ack()."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        # Test ack_mention function directly
        mock_ack = AsyncMock()
        await bot_module.ack_mention(mock_ack)
        mock_ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_mention_calls_agent(self, monkeypatch):
        """Test that process_mention calls AgentRunner."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        # Create mock result matching AgentRunResult structure
        mock_result = MagicMock()
        mock_result.output = "Agent response"
        mock_result.images = []

        async def mock_progress(*args, **kwargs):
            return mock_result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        event = {
            "text": "<@U123> hello agent",
            "ts": "1234567890.123456",
            "channel": "C123",
            "user": "U456",
        }
        mock_say = AsyncMock()
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

        await bot_module.process_mention(event, mock_say, mock_client)

        mock_client.chat_postMessage.assert_called()
        mock_client.chat_update.assert_called()


class TestSlackBotThreadReply:
    """Test thread reply pattern."""

    @pytest.mark.asyncio
    async def test_thread_reply_uses_thread_ts(self, monkeypatch):
        """Test reply uses existing thread_ts if available."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        mock_result = MagicMock()
        mock_result.output = "Response"
        mock_result.images = []

        async def mock_progress(*args, **kwargs):
            return mock_result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        event = {
            "text": "<@U123> hello",
            "ts": "1234567890.123456",
            "thread_ts": "1234567890.000001",
            "channel": "C123",
            "user": "U456",
        }
        mock_say = AsyncMock()
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

        await bot_module.process_mention(event, mock_say, mock_client)

        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs.get("thread_ts") == "1234567890.000001"

    @pytest.mark.asyncio
    async def test_thread_reply_uses_ts_when_no_thread(self, monkeypatch):
        """Test reply uses event ts when no thread_ts exists (new thread)."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        mock_result = MagicMock()
        mock_result.output = "Response"
        mock_result.images = []

        async def mock_progress(*args, **kwargs):
            return mock_result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        event = {
            "text": "<@U123> hello",
            "ts": "1234567890.123456",
            "channel": "C123",
            "user": "U456",
        }
        mock_say = AsyncMock()
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

        await bot_module.process_mention(event, mock_say, mock_client)

        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs.get("thread_ts") == "1234567890.123456"


class TestSlackBotErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_error_message_sent_on_agent_failure(self, monkeypatch):
        """Test user-friendly error message is sent when agent fails."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress_error(*args, **kwargs):
            raise Exception("API Error")

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress_error

        event = {
            "text": "<@U123> hello",
            "ts": "1234567890.123456",
            "channel": "C123",
            "user": "U456",
        }
        mock_say = AsyncMock()
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

        await bot_module.process_mention(event, mock_say, mock_client)

        mock_client.chat_update.assert_called()
        update_kwargs = mock_client.chat_update.call_args[1]
        assert (
            "오류" in update_kwargs.get("text", "").lower()
            or "error" in update_kwargs.get("text", "").lower()
        )


class TestSlackBotCommandIntegration:
    """Test command detection and execution integration."""

    @pytest.mark.asyncio
    async def test_mention_with_command_replaces_message(self, monkeypatch, tmp_path):
        """Test that command in mention is detected and prompt is replaced."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        captured_message = []

        async def mock_progress(runner, message, *args, **kwargs):
            captured_message.append(message)
            result = MagicMock()
            result.output = "Agent response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        db_path = tmp_path / "test_commands.db"
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        repo = CommandRepository(str(db_path))
        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="weather",
                prompt="Get the weather for {input}",
                original_prompt="Get weather for {input}",
                recommended_tools=[],
                created_by="slack:U999",
                created_at=now,
                updated_at=now,
            )
        )

        with patch("src.interfaces.slack.handlers.get_repository", return_value=repo):
            event = {
                "text": "<@U123> !weather Seoul",
                "ts": "1234567890.123456",
                "channel": "C123",
                "user": "U456",
            }
            mock_say = AsyncMock()
            mock_client = AsyncMock()
            mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

            await bot_module.process_mention(event, mock_say, mock_client)

            assert len(captured_message) == 1
            assert "Get the weather for Seoul" in captured_message[0]

    @pytest.mark.asyncio
    async def test_dm_with_command_replaces_message(self, monkeypatch, tmp_path):
        """Test that command in DM is detected and prompt is replaced."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from src.interfaces.slack import handlers

        captured_message = []

        async def mock_progress(runner, message, *args, **kwargs):
            captured_message.append(message)
            result = MagicMock()
            result.output = "Agent response"
            result.images = []
            return result

        handlers._run_agent_with_progress = mock_progress

        db_path = tmp_path / "test_commands.db"
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        repo = CommandRepository(str(db_path))
        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="help",
                prompt="Show help information to the user",
                original_prompt="Show help",
                recommended_tools=[],
                created_by="slack:U999",
                created_at=now,
                updated_at=now,
            )
        )

        with patch("src.interfaces.slack.handlers.get_repository", return_value=repo):
            event = {
                "text": "!help",
                "ts": "1234567890.123456",
                "channel": "D123",
                "channel_type": "im",
                "user": "U456",
            }
            mock_say = AsyncMock()
            mock_client = AsyncMock()
            mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

            await handlers.process_dm(event, mock_say, mock_client)

            assert len(captured_message) == 1
            assert "Show help information" in captured_message[0]

    @pytest.mark.asyncio
    async def test_command_not_found_falls_through(self, monkeypatch, tmp_path):
        """Test that non-existent command falls through to normal handling."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        captured_message = []

        async def mock_progress(runner, message, *args, **kwargs):
            captured_message.append(message)
            result = MagicMock()
            result.output = "Agent response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        db_path = tmp_path / "test_commands_empty.db"
        from src.core.commands.repository import CommandRepository

        repo = CommandRepository(str(db_path))

        with patch("src.interfaces.slack.handlers.get_repository", return_value=repo):
            event = {
                "text": "<@U123> !nonexistent Seoul",
                "ts": "1234567890.123456",
                "channel": "C123",
                "user": "U456",
            }
            mock_say = AsyncMock()
            mock_client = AsyncMock()
            mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

            await bot_module.process_mention(event, mock_say, mock_client)

            assert len(captured_message) == 1
            assert captured_message[0] == "!nonexistent Seoul"

    @pytest.mark.asyncio
    async def test_normal_message_not_affected(self, monkeypatch):
        """Test that non-command message passes through unchanged."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        captured_message = []

        async def mock_progress(runner, message, *args, **kwargs):
            captured_message.append(message)
            result = MagicMock()
            result.output = "Agent response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        event = {
            "text": "<@U123> hello agent, what is the weather?",
            "ts": "1234567890.123456",
            "channel": "C123",
            "user": "U456",
        }
        mock_say = AsyncMock()
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}

        await bot_module.process_mention(event, mock_say, mock_client)

        assert len(captured_message) == 1
        assert captured_message[0] == "hello agent, what is the weather?"
