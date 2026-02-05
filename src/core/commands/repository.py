# src/commands/repository.py
"""SQLite repository for Command persistence.

This module provides CRUD operations for commands using direct sqlite3.
Commands are stored with their prompt templates and metadata.
"""

import json
import os
import sqlite3
from datetime import datetime

from src.core.commands.models import Command


class CommandRepository:
    """Repository for storing and retrieving commands from SQLite.

    Provides full CRUD operations for Command objects. The repository
    auto-creates the database directory and table on initialization.

    Attributes:
        db_path: Path to the SQLite database file.

    Example:
        >>> repo = CommandRepository(db_path="data/commands.db")
        >>> cmd = Command(
        ...     id=0, name="test", prompt="Test prompt",
        ...     original_prompt="test", recommended_tools=[],
        ...     created_by="slack:U123", created_at=datetime.now(),
        ...     updated_at=datetime.now()
        ... )
        >>> created = repo.create(cmd)
        >>> print(f"Created command with ID: {created.id}")
    """

    def __init__(self, db_path: str = "data/commands.db") -> None:
        """Initialize the CommandRepository.

        Creates the database directory and commands table if they don't exist.
        Enables WAL mode for better concurrent access.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path

        # Create directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        # Create table and enable WAL mode
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema.

        Creates the commands table if it doesn't exist and enables WAL mode.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # Enable WAL mode
            conn.execute("PRAGMA journal_mode=WAL")

            # Create commands table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    prompt TEXT NOT NULL,
                    original_prompt TEXT NOT NULL,
                    recommended_tools TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _row_to_command(self, row: tuple) -> Command:
        """Convert a database row to a Command object.

        Args:
            row: Tuple containing (id, name, prompt, original_prompt,
                 recommended_tools, created_by, created_at, updated_at).

        Returns:
            Command instance populated from the row data.
        """
        return Command(
            id=row[0],
            name=row[1],
            prompt=row[2],
            original_prompt=row[3],
            recommended_tools=json.loads(row[4]),
            created_by=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )

    def create(self, cmd: Command) -> Command:
        """Create a new command in the database.

        The command name is normalized to lowercase before storage.

        Args:
            cmd: Command object to create. The id field will be ignored
                 and assigned by the database.

        Returns:
            Command with the database-assigned ID.

        Raises:
            sqlite3.IntegrityError: If a command with the same name exists.
        """
        normalized_name = cmd.name.lower()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO commands (
                    name, prompt, original_prompt, recommended_tools,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_name,
                    cmd.prompt,
                    cmd.original_prompt,
                    json.dumps(cmd.recommended_tools),
                    cmd.created_by,
                    cmd.created_at.isoformat(),
                    cmd.updated_at.isoformat(),
                ),
            )
            conn.commit()

            return Command(
                id=cursor.lastrowid,
                name=normalized_name,
                prompt=cmd.prompt,
                original_prompt=cmd.original_prompt,
                recommended_tools=cmd.recommended_tools,
                created_by=cmd.created_by,
                created_at=cmd.created_at,
                updated_at=cmd.updated_at,
            )
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Command | None:
        """Retrieve a command by its name.

        The search is case-insensitive (name is normalized to lowercase).

        Args:
            name: Command name to search for.

        Returns:
            Command if found, None otherwise.
        """
        normalized_name = name.lower()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT * FROM commands WHERE name = ?",
                (normalized_name,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_command(row)
        finally:
            conn.close()

    def list_all(self) -> list[Command]:
        """List all commands in the database.

        Returns:
            List of all Command objects, empty list if none exist.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT * FROM commands ORDER BY name")
            rows = cursor.fetchall()
            return [self._row_to_command(row) for row in rows]
        finally:
            conn.close()

    def update(self, cmd: Command) -> Command:
        """Update an existing command.

        Updates all fields except id, name, created_by, and created_at.
        The updated_at field is automatically set to the current time.

        Args:
            cmd: Command with updated fields. Must have a valid id.

        Returns:
            Updated Command object with new updated_at timestamp.

        Raises:
            ValueError: If no command with the given id exists.
        """
        updated_at = datetime.now()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                UPDATE commands SET
                    prompt = ?,
                    original_prompt = ?,
                    recommended_tools = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    cmd.prompt,
                    cmd.original_prompt,
                    json.dumps(cmd.recommended_tools),
                    updated_at.isoformat(),
                    cmd.id,
                ),
            )
            conn.commit()

            if cursor.rowcount == 0:
                raise ValueError(f"No command found with id: {cmd.id}")

            return Command(
                id=cmd.id,
                name=cmd.name,
                prompt=cmd.prompt,
                original_prompt=cmd.original_prompt,
                recommended_tools=cmd.recommended_tools,
                created_by=cmd.created_by,
                created_at=cmd.created_at,
                updated_at=updated_at,
            )
        finally:
            conn.close()

    def delete(self, name: str) -> bool:
        """Delete a command by its name.

        The search is case-insensitive (name is normalized to lowercase).

        Args:
            name: Name of the command to delete.

        Returns:
            True if the command was deleted, False if it didn't exist.
        """
        normalized_name = name.lower()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM commands WHERE name = ?",
                (normalized_name,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


_repository: CommandRepository | None = None


def get_repository(db_path: str = "data/commands.db") -> CommandRepository:
    """Get the singleton CommandRepository instance.

    Args:
        db_path: Path to SQLite database (only used on first call).

    Returns:
        CommandRepository singleton instance.
    """
    global _repository
    if _repository is None:
        _repository = CommandRepository(db_path=db_path)
    return _repository
