"""Command module for custom command management and parsing.

This module provides:
- Command: Data model for storing custom commands
- CommandRepository: SQLite repository for command persistence
- ParsedCommand: Data model for parsed command input
- parse_command: Function to parse user input for commands
- build_command_prompt: Function to build prompts from commands
- CommandExecutor: Executor for processing parsed commands
- CRUD tools: create_command, list_commands, get_command, update_command, delete_command
"""

from src.core.commands.executor import CommandExecutor
from src.core.commands.models import Command
from src.core.commands.parser import ParsedCommand, parse_command
from src.core.commands.prompts import build_command_prompt
from src.core.commands.repository import CommandRepository, get_repository
from src.core.commands.tools import (
    create_command,
    delete_command,
    get_command,
    list_commands,
    update_command,
)

__all__ = [
    "Command",
    "CommandRepository",
    "get_repository",
    "ParsedCommand",
    "parse_command",
    "build_command_prompt",
    "CommandExecutor",
    "create_command",
    "list_commands",
    "get_command",
    "update_command",
    "delete_command",
]
