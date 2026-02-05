# src/interfaces/slack/handlers.py
"""Event handlers for Slack bot.

Provides handlers for:
- @mentions (app_mention event)
- Direct messages (message event, channel_type="im")
- :robot_face: emoji reactions (reaction_added event)
- App home opened event

Uses lazy listener pattern to ack within 3s and process in background.
Supports image uploads from MCP tools (e.g., Playwright screenshots).
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from src.config import settings
from src.core.agent.core import AgentRunner, AgentRunResult
from src.core.commands.executor import CommandExecutor
from src.core.commands.parser import parse_command
from src.core.commands.repository import get_repository
from src.core.context import (
    cache_images_for_thread,
    clear_attached_images,
    get_cached_images_for_thread,
    set_attached_images,
)
from src.core.scheduler.tools import clear_scheduler_context, set_scheduler_context
from src.interfaces.slack.context import (
    _fetch_channel_context,
    _fetch_thread_context,
    _format_context_for_agent,
)
from src.interfaces.slack.images import (
    _extract_images_from_thread_history,
    _format_images_for_agent,
    _upload_images_to_slack,
)
from src.interfaces.slack.progress import (
    _format_progress,
    _muted_block,
)
from src.interfaces.slack.slack_api import (
    _send_multipart_message,
    _slack_api_with_retry,
)
from src.middleware.guardrails import GuardrailConfig
from src.utils.slack_files import process_slack_audio_files, process_slack_images

logger = logging.getLogger(__name__)


# Emoji to command mapping
# When user reacts with these emojis, the mapped command is executed
# with the message content as input
EMOJI_COMMAND_MAP: dict[str, str] = {
    "bug": "!센트리",  # :bug: 🐛 emoji → !센트리 command
    # Add more mappings as needed:
    # "memo": "!요약",
}


async def _run_agent_with_progress(
    runner: AgentRunner,
    message: str,
    client: Any,
    channel: str,
    progress_ts: str,
    user_id: str,
) -> AgentRunResult:
    """Run agent with native async and real-time progress updates.

    Uses AgentRunner.run_async_with_user() which is native async.
    Updates Slack message when tools are being used.

    Shields the agent run from external cancellation to prevent MCP cleanup
    issues when running in Slack's lazy listener context.

    Args:
        runner: Shared AgentRunner instance.
        message: User message to process.
        client: Slack client for API calls.
        channel: Channel ID.
        progress_ts: Timestamp of progress message to update.
        user_id: User ID for memory context.

    Returns:
        AgentRunResult with .output (str) and .images (List[ImageData]).
    """
    try:
        await _slack_api_with_retry(
            client.chat_update,
            channel=channel,
            ts=progress_ts,
            text=":brain: 생각 중",
            blocks=_muted_block(":brain: 생각 중"),
        )
    except (TimeoutError, asyncio.CancelledError):
        pass

    async def on_tool_call(tool_name: str) -> None:
        """Update progress message when a tool is called."""
        text, blocks = _format_progress(tool_name)
        try:
            await _slack_api_with_retry(
                client.chat_update,
                channel=channel,
                ts=progress_ts,
                text=text,
                blocks=blocks,
            )
        except (TimeoutError, asyncio.CancelledError):
            pass

    # Run in isolated task to prevent MCP cancel scope issues
    # (Slack lazy listener runs in different task context than ack handler)
    async def _isolated_run() -> AgentRunResult:
        return await runner.run_async_with_user(
            message, user_id, platform="slack", on_tool_call=on_tool_call
        )

    task = asyncio.create_task(_isolated_run())
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        task.cancel()
        raise


def _create_agent_runner(user_id: str) -> AgentRunner:
    """Create an AgentRunner for a specific user.

    Args:
        user_id: Slack user ID.

    Returns:
        Configured AgentRunner instance.
    """
    guardrail_config = GuardrailConfig(current_user_id=user_id)
    runner = AgentRunner(
        api_key=settings.api_key,
        enable_mcp=True,
        guardrail_config=guardrail_config,
    )
    logger.info("AgentRunner initialized for user %s", user_id)
    return runner


def _extract_user_message(text: str) -> str:
    """Extract user message from mention text.

    Removes the @mention prefix from the message.

    Args:
        text: Raw message text including @mention.

    Returns:
        Cleaned user message without @mention.
    """
    import re

    # Remove @mention patterns like <@U123456>
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return cleaned if cleaned else text


async def _process_user_message(
    user_message: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    event_ts: str,
    client: Any,
    say: Callable,
    event_type: str,
    event: dict[str, Any] | None = None,
) -> None:
    """Process a user message through the agent with progress updates.

    This is the common handler logic shared by mentions, DMs, and reactions.

    Args:
        user_message: The message text to process.
        user_id: Slack user ID.
        channel: Channel ID.
        thread_ts: Thread timestamp for replies.
        event_ts: Original event timestamp (to detect thread vs new message).
        client: Slack client for API calls.
        say: Slack say function for posting messages.
        event_type: Type of event for logging ("mention", "DM", "reaction").
        event: Original Slack event dict (optional, for file handling).
    """
    progress_ts = None

    try:
        parsed_cmd = parse_command(user_message)
        if parsed_cmd:
            executor = CommandExecutor(get_repository())
            cmd_prompt = executor.execute(parsed_cmd, user_id=f"slack:{user_id}")
            if cmd_prompt:
                user_message = cmd_prompt

        is_in_thread = thread_ts != event_ts
        if is_in_thread:
            context_messages = await _fetch_thread_context(
                client, channel, thread_ts, event_ts
            )
        else:
            context_messages = await _fetch_channel_context(client, channel, event_ts)

        context_prefix = _format_context_for_agent(context_messages, is_in_thread)

        # Process attached files (images and audio)
        image_context = ""
        audio_context = ""
        processed_images: list[dict[str, Any]] = []

        if event and event.get("files") and settings.slack_bot_token:
            # Process images
            processed_images = await process_slack_images(
                event["files"], settings.slack_bot_token
            )
            if processed_images:
                # Store images in context for tools to access
                set_attached_images(processed_images)
                image_context = _format_images_for_agent(processed_images)
                logger.info(f"Processed {len(processed_images)} image(s) from event")

            # Process audio files (transcribe to text instead of passing binary)
            audio_transcriptions = await process_slack_audio_files(
                event["files"], settings.slack_bot_token
            )
            if audio_transcriptions:
                audio_lines = ["\n[첨부된 오디오 파일 전사 결과]"]
                for t in audio_transcriptions:
                    audio_lines.append(f"📎 {t['name']} ({t['language']}):")
                    audio_lines.append(t["text"])
                    audio_lines.append("")
                audio_context = "\n".join(audio_lines)
                logger.info(
                    f"Transcribed {len(audio_transcriptions)} audio file(s) from event"
                )

        # If no direct attachments, check thread cache for previously generated images
        if not processed_images and is_in_thread:
            thread_key = f"{channel}:{thread_ts}"
            cached_images = get_cached_images_for_thread(thread_key)
            if cached_images:
                set_attached_images(cached_images)
                image_context = _format_images_for_agent(cached_images)
                logger.info(
                    f"Retrieved {len(cached_images)} image(s) from thread cache for editing"
                )
            else:
                # Fallback: try to extract from thread history (for old data URI format)
                history_images = _extract_images_from_thread_history(context_messages)
                if history_images:
                    set_attached_images(history_images)
                    image_context = _format_images_for_agent(history_images)
                    logger.info(
                        f"Extracted {len(history_images)} image(s) from thread history for editing"
                    )

        message_with_context = (
            context_prefix + user_message + image_context + audio_context
        )

        logger.info(
            "Processing %s from %s: %s", event_type, user_id, user_message[:100]
        )

        progress_msg = await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=":hourglass: 처리 중",
            blocks=_muted_block(":hourglass: 처리 중"),
        )
        progress_ts = progress_msg.get("ts")

        set_scheduler_context(
            user_id=f"slack:{user_id}",
            channel_id=str(channel),
            thread_ts=thread_ts,
        )

        runner = _create_agent_runner(user_id)
        agent_result = await _run_agent_with_progress(
            runner,
            message_with_context,
            client,
            str(channel),
            str(progress_ts),
            user_id,
        )

        response_text = agent_result.output if agent_result.output else "결과 없음"
        await _send_multipart_message(
            client, str(channel), thread_ts, response_text, update_first_ts=progress_ts
        )

        if agent_result.images:
            await _upload_images_to_slack(
                agent_result.images, client, str(channel), thread_ts
            )
            # Cache images for potential cross-message editing
            thread_key = f"{channel}:{thread_ts}"
            cache_data = []
            for img in agent_result.images:
                data_uri = img.to_data_uri()
                b64_part = data_uri.split(",", 1)[1] if "," in data_uri else ""
                cache_data.append(
                    {
                        "bytes": img.data,
                        "base64": b64_part,
                        "mime_type": img.mime_type,
                        "name": img.filename
                        or f"generated_{len(cache_data)}.{img.extension}",
                    }
                )
            cache_images_for_thread(thread_key, cache_data)
            logger.info(f"Cached {len(cache_data)} image(s) for thread {thread_key}")

    except Exception as e:
        error_msg = str(e)
        # Handle MCP cancel scope errors gracefully (anyio/asyncio task boundary issue)
        if "cancel scope" in error_msg.lower():
            logger.warning(
                "MCP cancel scope error (task boundary issue) in %s - non-fatal",
                event_type,
            )
            return
        logger.exception("Error processing %s: %s", event_type, e)
        error_text = f":x: 오류: {error_msg[:200]}"
        try:
            if progress_ts:
                await _slack_api_with_retry(
                    client.chat_update,
                    channel=channel,
                    ts=progress_ts,
                    text=error_text,
                    blocks=_muted_block(error_text),
                )
            else:
                await say(error_text, thread_ts=thread_ts)
        except (TimeoutError, asyncio.CancelledError, RuntimeError):
            logger.warning("Failed to send error message to Slack")
    finally:
        clear_scheduler_context()
        clear_attached_images()


# ============================================================================
# App Mention Handler (Lazy Listener Pattern)
# ============================================================================


async def ack_mention(ack: Callable) -> None:
    """Acknowledge app_mention event immediately.

    Args:
        ack: Slack ack function to acknowledge receipt.
    """
    await ack()


async def process_mention(event: dict[str, Any], say: Callable, client: Any) -> None:
    """Process app_mention event with real-time progress updates."""
    event_ts = event["ts"]
    thread_ts = event.get("thread_ts") or event_ts
    channel = event.get("channel")
    user_id = event.get("user", "unknown")
    user_message = _extract_user_message(event.get("text", ""))

    await _process_user_message(
        user_message=user_message,
        user_id=user_id,
        channel=str(channel),
        thread_ts=thread_ts,
        event_ts=event_ts,
        client=client,
        say=say,
        event_type="mention",
        event=event,
    )


# ============================================================================
# DM Message Handler (Lazy Listener Pattern)
# ============================================================================


async def ack_dm(ack: Callable) -> None:
    """Acknowledge DM message event immediately.

    Args:
        ack: Slack ack function to acknowledge receipt.
    """
    await ack()


async def process_dm(event: dict[str, Any], say: Callable, client: Any) -> None:
    """Process DM message with real-time progress updates."""
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    event_ts = event["ts"]
    thread_ts = event.get("thread_ts") or event_ts
    channel = event.get("channel")
    user_id = event.get("user", "unknown")
    user_message = event.get("text", "")

    await _process_user_message(
        user_message=user_message,
        user_id=user_id,
        channel=str(channel),
        thread_ts=thread_ts,
        event_ts=event_ts,
        client=client,
        say=say,
        event_type="DM",
        event=event,
    )


async def handle_message(
    event: dict[str, Any], say: Callable, ack: Callable, client: Any
) -> None:
    """Handle message events, filtering for DMs."""
    if event.get("channel_type") == "im":
        await ack_dm(ack)
        await process_dm(event, say, client)


# ============================================================================
# Emoji Reaction Handler (Lazy Listener Pattern)
# ============================================================================


async def ack_reaction(ack: Callable) -> None:
    """Acknowledge reaction_added event immediately.

    Args:
        ack: Slack ack function to acknowledge receipt.
    """
    await ack()


async def process_reaction(event: dict[str, Any], say: Callable, client: Any) -> None:
    """Process emoji reactions to trigger agent or mapped commands.

    Supports:
    - :robot_face: → Process message as-is through agent
    - Mapped emojis (EMOJI_COMMAND_MAP) → Execute mapped command with message as input
    """
    reaction = event.get("reaction", "")

    # Check if this is a supported reaction
    is_robot_face = reaction == "robot_face"
    mapped_command = EMOJI_COMMAND_MAP.get(reaction)

    if not is_robot_face and not mapped_command:
        return

    channel = event.get("item", {}).get("channel")
    message_ts = event.get("item", {}).get("ts")
    user_id = event.get("user", "unknown")

    if not channel or not message_ts:
        logger.warning("Missing channel or ts in reaction event")
        return

    result = await client.conversations_history(
        channel=channel,
        latest=message_ts,
        inclusive=True,
        limit=1,
    )

    if not result.get("messages"):
        logger.warning("Could not fetch reacted message")
        return

    message = result["messages"][0]
    original_text = message.get("text", "")
    thread_ts = message.get("thread_ts") or message_ts

    if mapped_command:
        user_message = f"{mapped_command} {original_text}"
        log_event_type = f"reaction:{reaction}"
        logger.info(
            "Emoji :%s: triggered command %s for message: %s",
            reaction,
            mapped_command,
            original_text[:50],
        )
    else:
        user_message = original_text
        log_event_type = "reaction"

    await _process_user_message(
        user_message=user_message,
        user_id=user_id,
        channel=str(channel),
        thread_ts=thread_ts,
        event_ts=message_ts,
        client=client,
        say=say,
        event_type=log_event_type,
    )


# ============================================================================
# App Home Opened Handler
# ============================================================================


async def handle_app_home_opened(event: dict[str, Any], logger: Any) -> None:
    """Handle app_home_opened event (no-op, just silences warning)."""
    pass
