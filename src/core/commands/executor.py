# src/commands/executor.py
"""Command executor for processing parsed commands.

This module provides the CommandExecutor class which handles command
lookup and prompt building for execution.
"""

from src.core.commands.parser import ParsedCommand
from src.core.commands.prompts import build_command_prompt
from src.core.commands.repository import CommandRepository


class CommandExecutor:
    """Executor for processing parsed commands.

    The CommandExecutor looks up commands from the repository and builds
    prompts for agent execution. It does not perform permission checks
    (execution is allowed for all users).

    Attributes:
        repository: CommandRepository for command lookup.

    Example:
        >>> from src.core.commands.repository import CommandRepository
        >>> from src.core.commands.parser import ParsedCommand
        >>> repo = CommandRepository(db_path="data/commands.db")
        >>> executor = CommandExecutor(repository=repo)
        >>> parsed = ParsedCommand(name="weather", input="Seoul")
        >>> prompt = executor.execute(parsed, "slack:U123456")
        >>> if prompt:
        ...     print("Prompt ready for agent execution")
    """

    def __init__(self, repository: CommandRepository) -> None:
        """Initialize the CommandExecutor.

        Args:
            repository: CommandRepository for command lookup.
        """
        self.repository = repository

    def execute(self, parsed_cmd: ParsedCommand, user_id: str) -> str | None:
        """Execute a parsed command by building its prompt.

        Looks up the command by name and builds a prompt with user context.
        Returns None if the command does not exist.

        Args:
            parsed_cmd: ParsedCommand with name, input, and additional_instructions.
            user_id: User identifier in format "platform:user_id".

        Returns:
            Built prompt string ready for agent execution, or None if
            command not found.

        Example:
            >>> parsed = ParsedCommand(name="weather", input="Seoul")
            >>> prompt = executor.execute(parsed, "slack:U123456")
            >>> if prompt is None:
            ...     print("Command not found")
            ... else:
            ...     print("Ready to execute:", prompt)
        """
        command = self.repository.get_by_name(parsed_cmd.name)

        if command is None:
            return None

        return build_command_prompt(
            command, parsed_cmd.input, user_id, parsed_cmd.additional_instructions
        )
