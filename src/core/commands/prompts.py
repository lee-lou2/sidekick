# src/commands/prompts.py
"""Prompt builder for command execution.

This module provides functions to build prompts from command templates
with user input substitution and context.
"""

from src.core.commands.models import Command


def build_command_prompt(
    command: Command, user_input: str, user_id: str, additional_instructions: str = ""
) -> str:
    """Build a prompt from a command template with user context.

    Substitutes {input} placeholders in the command prompt with the provided
    user_input and includes user context, recommended tools, and any additional
    instructions provided by the user.

    Args:
        command: Command object containing the prompt template.
        user_input: User input to substitute into the prompt.
        user_id: User identifier in format "platform:user_id".
        additional_instructions: Optional additional instructions from the user.

    Returns:
        Formatted prompt with user context and substituted input.

    Example:
        >>> from datetime import datetime
        >>> cmd = Command(
        ...     id=1, name="weather",
        ...     prompt="Get weather for {input}",
        ...     original_prompt="weather {input}",
        ...     recommended_tools=["weather_api"],
        ...     created_by="slack:U123",
        ...     created_at=datetime.now(),
        ...     updated_at=datetime.now()
        ... )
        >>> result = build_command_prompt(cmd, "Seoul", "slack:U999")
        >>> "Get weather for Seoul" in result
        True
        >>> "slack:U999" in result
        True
    """
    prompt_text = command.prompt.replace("{input}", user_input)

    tools_section = ""
    if command.recommended_tools:
        tools_list = ", ".join(command.recommended_tools)
        tools_section = f"""
[Recommended Tools]
The following tools may be useful for this command: {tools_list}
(These are suggestions - use your judgment to select appropriate tools)
"""

    additional_section = ""
    if additional_instructions:
        additional_section = f"""
[Additional Instructions from User]
{additional_instructions}
"""

    return f"""[User Context]
- User ID: {user_id}
- Command: {command.name}

[Instructions]
{prompt_text}
{tools_section}{additional_section}"""
