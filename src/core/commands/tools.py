# src/commands/tools.py
"""Command management tools for Pydantic AI.

This module provides command CRUD operations as simple functions.
Functions are registered as tools via the agent (src/core/agent/core.py).

Includes AI enhancement via Gemini API and permission checking.
"""

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from litellm import completion

from src.config import settings
from src.core.commands.models import Command
from src.core.commands.repository import get_repository

DEFAULT_COMMAND_MODEL = os.getenv(
    "COMMAND_ENHANCEMENT_MODEL", "gemini/gemini-2.0-flash"
)


def _get_available_tool_names() -> list[str]:
    """Get available tool names dynamically from the catalog.

    Returns:
        List of available tool names, or empty list if catalog unavailable.
    """
    try:
        from src.tools.catalog import get_all_tools

        toolset = get_all_tools()
        return list(toolset.tools.keys())
    except Exception:
        return []


def _enhance_prompt(original_prompt: str) -> str:
    """Enhance a prompt using Gemini API.

    Makes the prompt clearer, more specific, and better structured
    for the AI agent to understand and execute.

    Args:
        original_prompt: The original user-provided prompt.

    Returns:
        Enhanced prompt text.
    """
    if not settings.api_key:
        return original_prompt

    try:
        response = completion(
            model=DEFAULT_COMMAND_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a prompt engineer. Improve the following command prompt "
                        "to be clearer, more specific, and better structured. "
                        "Keep the same intent but make it more actionable. "
                        "If there's a {input} placeholder, preserve it. "
                        "Return ONLY the improved prompt, no explanations."
                    ),
                },
                {
                    "role": "user",
                    "content": original_prompt,
                },
            ],
            max_tokens=500,
        )
        enhanced = response.choices[0].message.content.strip()
        return enhanced if enhanced else original_prompt
    except Exception:
        # Return original on any error
        return original_prompt


def _recommend_tools(prompt: str) -> list[str]:
    """Analyze a prompt and recommend relevant tools.

    Uses Gemini API to analyze the prompt and suggest which tools
    from the available set would be useful for executing the command.

    Args:
        prompt: The command prompt to analyze.

    Returns:
        List of recommended tool names.
    """
    if not settings.api_key:
        return []

    tool_names = _get_available_tool_names()
    if not tool_names:
        return []

    tools_description = f"Available tools: {', '.join(tool_names)}"

    try:
        response = completion(
            model=DEFAULT_COMMAND_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a tool recommendation system. "
                        "Analyze the given command prompt and recommend which tools "
                        "would be most useful for executing it. "
                        f"{tools_description}\n"
                        "Return ONLY a comma-separated list of tool names (e.g., 'send_email,exa_search'). "
                        "If no tools seem relevant, return 'none'."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=100,
        )
        result = response.choices[0].message.content.strip().lower()

        if result == "none" or not result:
            return []

        # Parse comma-separated list and filter to valid tools
        recommended = [t.strip() for t in result.split(",") if t.strip() in tool_names]
        return recommended
    except Exception:
        return []


def create_command(name: str, prompt: str, user_id: str) -> str:
    """Create a new command with AI-enhanced prompt and tool recommendations.

    The prompt is automatically enhanced using AI for better clarity,
    and relevant tools are recommended based on the prompt content.

    Args:
        name: Command name (will be normalized to lowercase).
        prompt: The command prompt template. Use {input} as placeholder.
        user_id: User identifier in format 'platform:user_id' (e.g., 'slack:U123456').

    Returns:
        Success message with command details or error message.
    """
    repo = get_repository()

    # Check if command already exists
    existing = repo.get_by_name(name)
    if existing is not None:
        return f"Error: Command '{name.lower()}' already exists."

    # Enhance prompt and recommend tools
    enhanced_prompt = _enhance_prompt(prompt)
    recommended_tools = _recommend_tools(enhanced_prompt)

    now = datetime.now()
    cmd = Command(
        id=0,
        name=name,
        prompt=enhanced_prompt,
        original_prompt=prompt,
        recommended_tools=recommended_tools,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )

    created = repo.create(cmd)

    tools_str = ", ".join(recommended_tools) if recommended_tools else "none"
    return (
        f"Command '{created.name}' created successfully!\n"
        f"- Enhanced prompt: {enhanced_prompt[:100]}{'...' if len(enhanced_prompt) > 100 else ''}\n"
        f"- Recommended tools: {tools_str}\n"
        f"- Created by: {user_id}"
    )


def list_commands(dummy: str = "list") -> str:
    """List all available commands.

    Returns a formatted list of all commands with their names and descriptions.

    Args:
        dummy: Unused parameter (required for Gemini compatibility).

    Returns:
        Formatted list of commands or message if none exist.
    """
    repo = get_repository()
    commands = repo.list_all()

    if not commands:
        return "No commands found. Use create_command to add one."

    lines = [f"Found {len(commands)} command(s):", "=" * 40]
    for cmd in commands:
        tools_str = (
            ", ".join(cmd.recommended_tools) if cmd.recommended_tools else "none"
        )
        lines.append(f"\n!{cmd.name}")
        lines.append(
            f"  Prompt: {cmd.prompt[:50]}{'...' if len(cmd.prompt) > 50 else ''}"
        )
        lines.append(f"  Tools: {tools_str}")
        lines.append(f"  Created by: {cmd.created_by}")

    return "\n".join(lines)


def get_command(name: str) -> str:
    """Get detailed information about a specific command.

    Args:
        name: Command name to look up (case-insensitive).

    Returns:
        Command details or error message if not found.
    """
    repo = get_repository()
    cmd = repo.get_by_name(name)

    if cmd is None:
        return f"Error: Command '{name}' not found."

    tools_str = ", ".join(cmd.recommended_tools) if cmd.recommended_tools else "none"
    return (
        f"Command: !{cmd.name}\n"
        f"{'=' * 40}\n"
        f"Prompt: {cmd.prompt}\n"
        f"Original prompt: {cmd.original_prompt}\n"
        f"Recommended tools: {tools_str}\n"
        f"Created by: {cmd.created_by}\n"
        f"Created at: {cmd.created_at.isoformat()}\n"
        f"Updated at: {cmd.updated_at.isoformat()}"
    )


def update_command(name: str, prompt: str, user_id: str) -> str:
    """Update an existing command's prompt.

    Only the original creator can update the command. The new prompt
    is automatically enhanced using AI.

    Args:
        name: Command name to update (case-insensitive).
        prompt: New prompt template.
        user_id: User identifier making the request.

    Returns:
        Success message or error message (permission denied or not found).
    """
    repo = get_repository()
    cmd = repo.get_by_name(name)

    if cmd is None:
        return f"Error: Command '{name}' not found."

    # Permission check
    if cmd.created_by != user_id:
        return (
            f"Permission denied: Only the creator ({cmd.created_by}) "
            f"can update this command."
        )

    # Enhance prompt and recommend tools
    enhanced_prompt = _enhance_prompt(prompt)
    recommended_tools = _recommend_tools(enhanced_prompt)

    # Update command
    cmd.prompt = enhanced_prompt
    cmd.original_prompt = prompt
    cmd.recommended_tools = recommended_tools

    updated = repo.update(cmd)

    tools_str = ", ".join(recommended_tools) if recommended_tools else "none"
    return (
        f"Command '{updated.name}' updated successfully!\n"
        f"- Enhanced prompt: {enhanced_prompt[:100]}{'...' if len(enhanced_prompt) > 100 else ''}\n"
        f"- Recommended tools: {tools_str}"
    )


def delete_command(name: str, user_id: str) -> str:
    """Delete an existing command.

    Only the original creator can delete the command.

    Args:
        name: Command name to delete (case-insensitive).
        user_id: User identifier making the request.

    Returns:
        Success message or error message (permission denied or not found).
    """
    repo = get_repository()
    cmd = repo.get_by_name(name)

    if cmd is None:
        return f"Error: Command '{name}' not found."

    # Permission check
    if cmd.created_by != user_id:
        return (
            f"Permission denied: Only the creator ({cmd.created_by}) "
            f"can delete this command."
        )

    repo.delete(name)
    return f"Command '{name.lower()}' deleted successfully."


def get_command_tools() -> list[Callable[..., Any]]:
    """Get all command management tools as a list.

    Returns:
        List of tool functions for command CRUD operations.
    """
    return [
        create_command,
        list_commands,
        get_command,
        update_command,
        delete_command,
    ]
