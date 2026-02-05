"""Preprocessing middleware for message handling."""

from src.core.commands import CommandExecutor, parse_command
from src.core.commands.repository import get_repository
from src.core.context import clear_attached_images, set_attached_images
from src.core.scheduler.tools import clear_scheduler_context, set_scheduler_context


def preprocess_command(message: str, user_id: str) -> str | None:
    """Preprocess message for commands.

    Returns the command prompt if command found, None otherwise.
    """
    parsed_cmd = parse_command(message)
    if parsed_cmd:
        executor = CommandExecutor(get_repository())
        return executor.execute(parsed_cmd, user_id=user_id)
    return None


__all__ = [
    "set_scheduler_context",
    "clear_scheduler_context",
    "set_attached_images",
    "clear_attached_images",
    "preprocess_command",
]
