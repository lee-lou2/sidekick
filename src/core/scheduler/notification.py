# src/core/scheduler/notification.py
"""Notification protocol for scheduler.

Provides an abstraction layer for sending notifications from scheduled tasks,
allowing different notification backends (Slack, email, etc.).
"""

from typing import Any, Protocol


class NotificationProtocol(Protocol):
    """Protocol for sending notifications from scheduler.

    This protocol defines the interface that notification backends must implement.
    It decouples the scheduler from specific notification services like Slack.
    """

    async def send(
        self,
        channel_id: str,
        message: str,
        thread_ts: str | None = None,
    ) -> str | None:
        """Send a notification message.

        Args:
            channel_id: Target channel/conversation identifier.
            message: Message content to send.
            thread_ts: Optional thread timestamp for threading.

        Returns:
            Message identifier (e.g., timestamp) or None on failure.
        """
        ...

    async def update(
        self,
        channel_id: str,
        message_ts: str,
        message: str,
    ) -> bool:
        """Update an existing notification message.

        Args:
            channel_id: Target channel/conversation identifier.
            message_ts: Message identifier to update.
            message: New message content.

        Returns:
            True on success, False on failure.
        """
        ...


class SlackNotifier:
    """Slack implementation of NotificationProtocol.

    Wraps a Slack AsyncWebClient to implement the notification protocol.
    """

    def __init__(self, client: Any) -> None:
        """Initialize with a Slack client.

        Args:
            client: Slack AsyncWebClient instance.
        """
        self._client = client

    async def send(
        self,
        channel_id: str,
        message: str,
        thread_ts: str | None = None,
    ) -> str | None:
        """Send a Slack message.

        Args:
            channel_id: Slack channel ID.
            message: Message text.
            thread_ts: Thread timestamp for threading.

        Returns:
            Message timestamp or None on failure.
        """
        try:
            result = await self._client.chat_postMessage(
                channel=channel_id,
                text=message,
                thread_ts=thread_ts,
            )
            return result.get("ts")
        except Exception:
            return None

    async def update(
        self,
        channel_id: str,
        message_ts: str,
        message: str,
    ) -> bool:
        """Update a Slack message.

        Args:
            channel_id: Slack channel ID.
            message_ts: Message timestamp to update.
            message: New message text.

        Returns:
            True on success, False on failure.
        """
        try:
            await self._client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=message,
            )
            return True
        except Exception:
            return False
