# src/interfaces/slack/context.py
"""Context building utilities for Slack bot.

Provides functions to fetch and format conversation context from threads
and channels for the agent.
"""

import logging
from typing import Any

from src.interfaces.slack.slack_api import _slack_api_with_retry

logger = logging.getLogger(__name__)

THREAD_CONTEXT_LIMIT = 20
CHANNEL_CONTEXT_LIMIT = 10


async def _fetch_thread_context(
    client: Any,
    channel: str,
    thread_ts: str,
    current_ts: str,
) -> list[dict[str, str]]:
    """Fetch previous messages from a thread for context.

    Args:
        client: Slack client for API calls.
        channel: Channel ID.
        thread_ts: Thread timestamp (parent message ts).
        current_ts: Current message timestamp (to exclude from context).

    Returns:
        List of messages with 'user' and 'text' keys, oldest first.
    """
    try:
        result = await _slack_api_with_retry(
            client.conversations_replies,
            channel=channel,
            ts=thread_ts,
            limit=THREAD_CONTEXT_LIMIT,
        )
        messages = result.get("messages", [])
        context_messages = []
        for msg in messages:
            if msg.get("ts") == current_ts:
                continue
            is_bot = msg.get("bot_id") or msg.get("subtype") == "bot_message"
            context_messages.append(
                {
                    "user": "assistant" if is_bot else msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                }
            )
        return context_messages
    except Exception as e:
        logger.warning("Failed to fetch thread context: %s", e)
        return []


async def _fetch_channel_context(
    client: Any,
    channel: str,
    before_ts: str,
) -> list[dict[str, str]]:
    """Fetch recent messages from channel for context.

    Args:
        client: Slack client for API calls.
        channel: Channel ID.
        before_ts: Fetch messages before this timestamp.

    Returns:
        List of messages with 'user' and 'text' keys, oldest first.
    """
    try:
        result = await _slack_api_with_retry(
            client.conversations_history,
            channel=channel,
            latest=before_ts,
            limit=CHANNEL_CONTEXT_LIMIT,
            inclusive=False,
        )
        messages_chronological = list(reversed(result.get("messages", [])))
        context_messages = []
        for msg in messages_chronological:
            is_bot = msg.get("bot_id") or msg.get("subtype") == "bot_message"
            if is_bot:
                continue
            context_messages.append(
                {
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                }
            )
        return context_messages
    except Exception as e:
        logger.warning("Failed to fetch channel context: %s", e)
        return []


def _format_context_for_agent(
    context_messages: list[dict[str, str]],
    is_thread: bool,
) -> str:
    """Format context messages into a string for the agent.

    Args:
        context_messages: List of messages with 'user' and 'text' keys.
        is_thread: Whether context is from a thread or channel.

    Returns:
        Formatted context string to prepend to user message.
    """
    if not context_messages:
        return ""

    context_type = "스레드" if is_thread else "채널"
    lines = [f"[이전 {context_type} 대화 맥락]"]

    for msg in context_messages:
        user = msg["user"]
        text = msg["text"]
        if user == "assistant":
            lines.append(f"봇: {text}")
        else:
            lines.append(f"사용자: {text}")

    lines.append("[현재 요청]")
    return "\n".join(lines) + "\n"
