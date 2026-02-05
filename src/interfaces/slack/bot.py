# src/slack/bot.py
"""Slack bot implementation with AsyncApp and AsyncSocketModeHandler.

Provides event handlers for:
- @mentions (app_mention event)
- Direct messages (message event, channel_type="im")
- :robot_face: emoji reactions (reaction_added event)

Uses lazy listener pattern to ack within 3s and process in background.
Supports image uploads from MCP tools (e.g., Playwright screenshots).
"""

import asyncio
import logging

from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp

# Load environment variables from .env file
load_dotenv()
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from src.config import settings
from src.core.lifecycle import get_lifecycle_manager
from src.core.scheduler.manager import SchedulerManager
from src.core.scheduler.notification import SlackNotifier
from src.interfaces.slack.handlers import (
    ack_mention,
    ack_reaction,
    handle_app_home_opened,
    handle_message,
    process_mention,
    process_reaction,
)

logger = logging.getLogger(__name__)

# Initialize AsyncApp
app = AsyncApp(token=settings.slack_bot_token)


# ============================================================================
# Event Registration
# ============================================================================

# Register with lazy listener pattern
app.event("app_mention")(ack=ack_mention, lazy=[process_mention])
app.event("message")(handle_message)
app.event("reaction_added")(ack=ack_reaction, lazy=[process_reaction])
app.event("app_home_opened")(handle_app_home_opened)


# ============================================================================
# Bot Factory and Startup Functions
# ============================================================================


def create_bot(
    bot_token: str | None = None, app_token: str | None = None
) -> tuple[AsyncApp, AsyncSocketModeHandler]:
    """Create and configure the Slack bot.

    Args:
        bot_token: Slack bot token (xoxb-*). Defaults to SLACK_BOT_TOKEN env var.
        app_token: Slack app token (xapp-*). Defaults to SLACK_APP_TOKEN env var.

    Returns:
        Tuple of (AsyncApp instance, AsyncSocketModeHandler instance).
    """
    global app

    resolved_bot_token = bot_token or settings.slack_bot_token
    resolved_app_token = app_token or settings.slack_app_token

    # Recreate app with provided token if different
    if resolved_bot_token and resolved_bot_token != app._token:
        app = AsyncApp(token=resolved_bot_token)
        # Re-register handlers
        app.event("app_mention")(ack=ack_mention, lazy=[process_mention])
        app.event("reaction_added")(ack=ack_reaction, lazy=[process_reaction])

    handler = AsyncSocketModeHandler(app, resolved_app_token)
    return app, handler


async def start_bot(bot_token: str | None = None, app_token: str | None = None) -> None:
    """Start the Slack bot with Socket Mode."""
    slack_app, handler = create_bot(bot_token, app_token)

    scheduler = SchedulerManager.get_instance()
    scheduler.set_slack_client(slack_app.client)
    scheduler.set_notifier(SlackNotifier(slack_app.client))

    lifecycle = get_lifecycle_manager()
    lifecycle.register("scheduler", scheduler)
    await lifecycle.startup()

    logger.info("Starting Slack bot with Socket Mode...")
    try:
        await handler.start_async()
    except asyncio.CancelledError:
        logger.info("Received shutdown signal")
    finally:
        await lifecycle.shutdown()
        await handler.close_async()
        logger.info("Slack bot stopped")


def main() -> None:
    """Entry point with graceful shutdown handling."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
