# src/interfaces/slack/slack_api.py
"""Slack API utilities for message handling and retry logic."""

import asyncio
from collections.abc import Callable
from typing import Any

from src.utils.slack_formatter import markdown_to_mrkdwn

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]
SLACK_MESSAGE_LIMIT = 2500


async def _slack_api_with_retry(coro_func: Callable, *args, **kwargs) -> Any:
    """Execute Slack API call with retry on timeout."""
    last_error: BaseException = TimeoutError("Max retries exceeded")
    for attempt in range(MAX_RETRIES):
        try:
            return await coro_func(*args, **kwargs)
        except (TimeoutError, asyncio.TimeoutError, asyncio.CancelledError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
    raise last_error


def _split_message_at_boundaries(
    text: str, limit: int = SLACK_MESSAGE_LIMIT
) -> list[str]:
    """Split message text at natural boundaries to fit Slack's message limit.

    Attempts to split at paragraph breaks, newlines, or spaces to maintain
    readability. Falls back to hard limit if no suitable break point found.

    Args:
        text: Message text to split.
        limit: Maximum characters per chunk (default: SLACK_MESSAGE_LIMIT).

    Returns:
        List of text chunks, each within the character limit.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        chunk = remaining[:limit]
        split_at = chunk.rfind("\n\n")
        if split_at < limit * 0.5:
            split_at = chunk.rfind("\n")
        if split_at < limit * 0.3:
            split_at = chunk.rfind(" ")
        if split_at < limit * 0.3:
            split_at = limit

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks


async def _send_multipart_message(
    client: Any,
    channel: str,
    thread_ts: str,
    text: str,
    update_first_ts: str | None = None,
) -> None:
    """Send a message to Slack, splitting into multiple parts if needed.

    Converts Markdown to Slack mrkdwn format and handles messages that
    exceed Slack's character limit by splitting at natural boundaries.

    Args:
        client: Slack AsyncWebClient instance.
        channel: Target channel ID.
        thread_ts: Thread timestamp for replies.
        text: Message text (Markdown format).
        update_first_ts: If provided, update existing message instead of posting new.
    """
    from slack_sdk.errors import SlackApiError

    # Convert standard Markdown to Slack mrkdwn format
    converted_text = markdown_to_mrkdwn(text)
    chunks = _split_message_at_boundaries(converted_text)

    for i, chunk in enumerate(chunks):
        try:
            if i == 0 and update_first_ts:
                await client.chat_update(
                    channel=channel, ts=update_first_ts, text=chunk
                )
            else:
                part_indicator = f"({i + 1}/{len(chunks)})" if len(chunks) > 1 else ""
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"{chunk}\n{part_indicator}".strip()
                    if part_indicator
                    else chunk,
                )
        except SlackApiError as e:
            if e.response.get("error") == "msg_too_long":
                shorter = _split_message_at_boundaries(chunk, limit=1000)
                for j, sub in enumerate(shorter):
                    if i == 0 and j == 0 and update_first_ts:
                        await client.chat_update(
                            channel=channel, ts=update_first_ts, text=sub
                        )
                    else:
                        await client.chat_postMessage(
                            channel=channel, thread_ts=thread_ts, text=sub
                        )
            else:
                raise
