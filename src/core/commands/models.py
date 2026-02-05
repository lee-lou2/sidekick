# src/commands/models.py
"""Command data model for storing custom commands.

This module defines the Command dataclass which represents a user-defined
command with its prompt template and metadata.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Command:
    """Represents a custom command with its prompt template.

    A command stores a reusable prompt template that users can invoke
    by name. Commands track who created them and when.

    Attributes:
        id: Unique identifier assigned by the database.
        name: Command name (lowercase normalized).
        prompt: The optimized/processed prompt template.
        original_prompt: The original prompt text before optimization.
        recommended_tools: List of tool names suggested for this command.
        created_by: User identifier in format "platform:user_id".
        created_at: Timestamp when the command was created.
        updated_at: Timestamp when the command was last updated.

    Example:
        >>> from datetime import datetime
        >>> cmd = Command(
        ...     id=1,
        ...     name="weather",
        ...     prompt="Get weather for {location}",
        ...     original_prompt="weather for {location}",
        ...     recommended_tools=["weather_api"],
        ...     created_by="slack:U123456",
        ...     created_at=datetime.now(),
        ...     updated_at=datetime.now(),
        ... )
    """

    id: int
    name: str
    prompt: str
    original_prompt: str
    recommended_tools: list[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
