# tests/test_message_processing.py
"""Unit tests for _process_user_message function.

Tests cover:
- Command parsing path (message starts with !)
- Thread context fetching (when in thread)
- Channel context fetching (when not in thread)
- Image attachment processing
- Error handling and cleanup (finally block)
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestProcessUserMessageCommandParsing:
    """Test command parsing path in _process_user_message."""

    @pytest.mark.asyncio
    async def test_command_detected_replaces_user_message(self, monkeypatch, tmp_path):
        """Test that when message starts with !, command is parsed and prompt replaced."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        # Track what message was passed to the runner
        captured_message = []

        async def mock_progress(runner, message, *args, **kwargs):
            captured_message.append(message)
            result = MagicMock()
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        # Create command repository with a test command
        db_path = tmp_path / "test_commands.db"
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        repo = CommandRepository(str(db_path))
        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="greet",
                prompt="Say hello to {input}",
                original_prompt="Say hello",
                recommended_tools=[],
                created_by="slack:U999",
                created_at=now,
                updated_at=now,
            )
        )

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_replies.return_value = {"messages": []}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        with patch("src.interfaces.slack.handlers.get_repository", return_value=repo):
            from src.interfaces.slack import handlers

            await handlers._process_user_message(
                user_message="!greet World",
                user_id="U456",
                channel="C123",
                thread_ts="1234567890.123456",
                event_ts="1234567890.123456",
                client=mock_client,
                say=mock_say,
                event_type="mention",
                event=None,
            )

        assert len(captured_message) == 1
        assert "Say hello to World" in captured_message[0]

    @pytest.mark.asyncio
    async def test_non_command_message_passes_through(self, monkeypatch):
        """Test that message without ! command passes through unchanged."""
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
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        from src.interfaces.slack import handlers

        await handlers._process_user_message(
            user_message="hello agent",
            user_id="U456",
            channel="C123",
            thread_ts="1234567890.123456",
            event_ts="1234567890.123456",
            client=mock_client,
            say=mock_say,
            event_type="mention",
            event=None,
        )

        assert len(captured_message) == 1
        # Message should contain original text (possibly with context prefix)
        assert "hello agent" in captured_message[0]


class TestProcessUserMessageContextFetching:
    """Test context fetching paths in _process_user_message."""

    @pytest.mark.asyncio
    async def test_thread_context_fetched_when_in_thread(self, monkeypatch):
        """Test that thread context is fetched when thread_ts != event_ts."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress(runner, message, *args, **kwargs):
            result = MagicMock()
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        # Thread context returns messages
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"user": "U111", "text": "Previous message", "ts": "1234567890.000001"}
            ]
        }
        mock_say = AsyncMock()

        # thread_ts != event_ts means we're in an existing thread
        from src.interfaces.slack import handlers

        await handlers._process_user_message(
            user_message="reply in thread",
            user_id="U456",
            channel="C123",
            thread_ts="1234567890.000001",  # Thread root
            event_ts="1234567890.123456",  # Current message
            client=mock_client,
            say=mock_say,
            event_type="mention",
            event=None,
        )

        # Verify conversations_replies was called (thread context fetch)
        mock_client.conversations_replies.assert_called_once()
        call_kwargs = mock_client.conversations_replies.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert call_kwargs["ts"] == "1234567890.000001"

    @pytest.mark.asyncio
    async def test_channel_context_fetched_when_not_in_thread(self, monkeypatch):
        """Test that channel context is fetched when thread_ts == event_ts (new thread)."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress(runner, message, *args, **kwargs):
            result = MagicMock()
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        # Channel history returns messages
        mock_client.conversations_history.return_value = {
            "messages": [
                {"user": "U111", "text": "Channel message", "ts": "1234567890.000001"}
            ]
        }
        mock_say = AsyncMock()

        # thread_ts == event_ts means new message (not in thread)
        from src.interfaces.slack import handlers

        await handlers._process_user_message(
            user_message="new message",
            user_id="U456",
            channel="C123",
            thread_ts="1234567890.123456",  # Same as event_ts
            event_ts="1234567890.123456",
            client=mock_client,
            say=mock_say,
            event_type="mention",
            event=None,
        )

        # Verify conversations_history was called (channel context fetch)
        mock_client.conversations_history.assert_called_once()
        call_kwargs = mock_client.conversations_history.call_args[1]
        assert call_kwargs["channel"] == "C123"


class TestProcessUserMessageImageProcessing:
    """Test image attachment processing in _process_user_message."""

    @pytest.mark.asyncio
    async def test_image_attachments_processed(self, monkeypatch):
        """Test that image files in event are processed."""
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
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        # Mock image processing
        processed_images = [
            {"bytes": b"fake_image", "mime_type": "image/png", "name": "test.png"}
        ]

        with (
            patch(
                "src.interfaces.slack.handlers.process_slack_images",
                new_callable=AsyncMock,
                return_value=processed_images,
            ) as mock_process_images,
            patch(
                "src.interfaces.slack.handlers.set_attached_images"
            ) as mock_set_images,
            patch("src.interfaces.slack.handlers.settings") as mock_settings,
        ):
            mock_settings.slack_bot_token = "xoxb-test-token"
            event = {
                "files": [
                    {
                        "id": "F123",
                        "mimetype": "image/png",
                        "url_private": "https://...",
                    }
                ]
            }

            from src.interfaces.slack import handlers

            await handlers._process_user_message(
                user_message="analyze this image",
                user_id="U456",
                channel="C123",
                thread_ts="1234567890.123456",
                event_ts="1234567890.123456",
                client=mock_client,
                say=mock_say,
                event_type="mention",
                event=event,
            )

            # Verify image processing was called
            mock_process_images.assert_called_once()
            mock_set_images.assert_called_once_with(processed_images)

    @pytest.mark.asyncio
    async def test_no_image_processing_without_files(self, monkeypatch):
        """Test that image processing is skipped when no files in event."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress(runner, message, *args, **kwargs):
            result = MagicMock()
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        with patch(
            "src.interfaces.slack.handlers.process_slack_images", new_callable=AsyncMock
        ) as mock_process_images:
            # Event without files
            event = {}

            from src.interfaces.slack import handlers

            await handlers._process_user_message(
                user_message="just text",
                user_id="U456",
                channel="C123",
                thread_ts="1234567890.123456",
                event_ts="1234567890.123456",
                client=mock_client,
                say=mock_say,
                event_type="mention",
                event=event,
            )

            # Verify image processing was NOT called
            mock_process_images.assert_not_called()


class TestProcessUserMessageErrorHandling:
    """Test error handling and cleanup in _process_user_message."""

    @pytest.mark.asyncio
    async def test_error_updates_progress_message(self, monkeypatch):
        """Test that error is shown by updating progress message."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress_error(*args, **kwargs):
            raise Exception("Agent failed!")

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress_error

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        from src.interfaces.slack import handlers

        await handlers._process_user_message(
            user_message="hello",
            user_id="U456",
            channel="C123",
            thread_ts="1234567890.123456",
            event_ts="1234567890.123456",
            client=mock_client,
            say=mock_say,
            event_type="mention",
            event=None,
        )

        # Verify error message was sent via chat_update
        mock_client.chat_update.assert_called()
        call_kwargs = mock_client.chat_update.call_args[1]
        assert ":x:" in call_kwargs.get("text", "") or "오류" in call_kwargs.get(
            "text", ""
        )

    @pytest.mark.asyncio
    async def test_error_uses_say_when_no_progress_ts(self, monkeypatch):
        """Test that error uses say() when progress_ts is not set."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        # Make chat_postMessage fail so progress_ts is never set
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = Exception("Failed to post")
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        from src.interfaces.slack import handlers

        await handlers._process_user_message(
            user_message="hello",
            user_id="U456",
            channel="C123",
            thread_ts="1234567890.123456",
            event_ts="1234567890.123456",
            client=mock_client,
            say=mock_say,
            event_type="mention",
            event=None,
        )

        # Verify error message was sent via say (since progress_ts is None)
        mock_say.assert_called()
        call_args = mock_say.call_args
        assert ":x:" in call_args[0][0] or "오류" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cleanup_always_runs(self, monkeypatch):
        """Test that scheduler context and image context are always cleared."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress_error(*args, **kwargs):
            raise Exception("Agent failed!")

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress_error

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        with (
            patch(
                "src.interfaces.slack.handlers.clear_scheduler_context"
            ) as mock_clear_scheduler,
            patch(
                "src.interfaces.slack.handlers.clear_attached_images"
            ) as mock_clear_images,
        ):
            from src.interfaces.slack import handlers

            await handlers._process_user_message(
                user_message="hello",
                user_id="U456",
                channel="C123",
                thread_ts="1234567890.123456",
                event_ts="1234567890.123456",
                client=mock_client,
                say=mock_say,
                event_type="mention",
                event=None,
            )

            # Verify cleanup functions were called even after error
            mock_clear_scheduler.assert_called_once()
            mock_clear_images.assert_called_once()


class TestProcessUserMessageSchedulerContext:
    """Test scheduler context management in _process_user_message."""

    @pytest.mark.asyncio
    async def test_scheduler_context_set_with_user_info(self, monkeypatch):
        """Test that scheduler context is set with correct user/channel info."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        import importlib

        import src.interfaces.slack.bot as bot_module

        importlib.reload(bot_module)

        async def mock_progress(runner, message, *args, **kwargs):
            result = MagicMock()
            result.output = "Response"
            result.images = []
            return result

        from src.interfaces.slack import handlers

        handlers._run_agent_with_progress = mock_progress

        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress_ts"}
        mock_client.conversations_history.return_value = {"messages": []}
        mock_say = AsyncMock()

        with patch(
            "src.interfaces.slack.handlers.set_scheduler_context"
        ) as mock_set_scheduler:
            from src.interfaces.slack import handlers

            await handlers._process_user_message(
                user_message="hello",
                user_id="U456",
                channel="C123",
                thread_ts="1234567890.123456",
                event_ts="1234567890.123456",
                client=mock_client,
                say=mock_say,
                event_type="mention",
                event=None,
            )

            # Verify scheduler context was set with correct params
            mock_set_scheduler.assert_called_once_with(
                user_id="slack:U456",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )
