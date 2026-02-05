# src/api/task_repository.py
"""SQLite repository for API task persistence.

This module provides CRUD operations for API tasks using SQLite.
Tasks are stored with their execution results and metadata,
surviving server restarts.
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """Represents a stored task record."""

    task_id: str
    status: str  # "pending", "success", "error"
    result: str | None
    error_message: str | None
    execution_time: float | None
    tool_calls: list[str]
    model_used: str
    images: list[dict]  # Serialized ImageDataResponse
    created_at: datetime
    updated_at: datetime


class TaskRepository:
    """Repository for storing and retrieving API tasks from SQLite.

    Provides CRUD operations with automatic cleanup of old tasks.
    The repository auto-creates the database directory and table on initialization.

    Attributes:
        db_path: Path to the SQLite database file.
        retention_hours: How long to keep completed tasks (default: 24 hours).
    """

    def __init__(
        self,
        db_path: str = "data/tasks.db",
        retention_hours: int = 24,
    ) -> None:
        """Initialize the TaskRepository.

        Args:
            db_path: Path to the SQLite database file.
            retention_hours: Hours to retain completed tasks before cleanup.
        """
        self.db_path = db_path
        self.retention_hours = retention_hours

        # Create directory if needed
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result TEXT,
                    error_message TEXT,
                    execution_time REAL,
                    tool_calls TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    images TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Index for cleanup queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_updated_at
                ON tasks(updated_at)
            """)

            conn.commit()
        finally:
            conn.close()

    def _row_to_task(self, row: tuple) -> TaskRecord:
        """Convert a database row to a TaskRecord."""
        return TaskRecord(
            task_id=row[0],
            status=row[1],
            result=row[2],
            error_message=row[3],
            execution_time=row[4],
            tool_calls=json.loads(row[5]),
            model_used=row[6],
            images=json.loads(row[7]),
            created_at=datetime.fromisoformat(row[8]),
            updated_at=datetime.fromisoformat(row[9]),
        )

    def create(
        self, task_id: str, model_used: str = "gemini/gemini-3-flash-preview"
    ) -> TaskRecord:
        """Create a new pending task.

        Args:
            task_id: Unique task identifier.
            model_used: Model identifier for this task.

        Returns:
            Created TaskRecord with pending status.
        """
        now = datetime.now()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, status, result, error_message, execution_time,
                    tool_calls, model_used, images, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    "pending",
                    None,
                    None,
                    None,
                    json.dumps([]),
                    model_used,
                    json.dumps([]),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

            return TaskRecord(
                task_id=task_id,
                status="pending",
                result=None,
                error_message=None,
                execution_time=None,
                tool_calls=[],
                model_used=model_used,
                images=[],
                created_at=now,
                updated_at=now,
            )
        finally:
            conn.close()

    def get(self, task_id: str) -> TaskRecord | None:
        """Retrieve a task by ID.

        Args:
            task_id: Task identifier.

        Returns:
            TaskRecord if found, None otherwise.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_task(row)
        finally:
            conn.close()

    def update(
        self,
        task_id: str,
        status: str,
        result: str | None = None,
        error_message: str | None = None,
        execution_time: float | None = None,
        tool_calls: list[str] | None = None,
        images: list[dict] | None = None,
    ) -> TaskRecord | None:
        """Update a task's status and results.

        Args:
            task_id: Task identifier.
            status: New status ("success" or "error").
            result: Task result output.
            error_message: Error message if failed.
            execution_time: Execution duration in seconds.
            tool_calls: List of tool names called.
            images: List of image data dicts.

        Returns:
            Updated TaskRecord, or None if task not found.
        """
        now = datetime.now()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                UPDATE tasks SET
                    status = ?,
                    result = ?,
                    error_message = ?,
                    execution_time = ?,
                    tool_calls = ?,
                    images = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    status,
                    result,
                    error_message,
                    execution_time,
                    json.dumps(tool_calls or []),
                    json.dumps(images or []),
                    now.isoformat(),
                    task_id,
                ),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get(task_id)
        finally:
            conn.close()

    def cleanup_old_tasks(self) -> int:
        """Remove tasks older than retention period.

        Returns:
            Number of tasks deleted.
        """
        cutoff = datetime.now() - timedelta(hours=self.retention_hours)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                DELETE FROM tasks
                WHERE status != 'pending' AND updated_at < ?
                """,
                (cutoff.isoformat(),),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info("Cleaned up %d old tasks", deleted)
            return deleted
        finally:
            conn.close()

    def to_dict(self, task: TaskRecord) -> dict[str, Any]:
        """Convert TaskRecord to dict for API response."""
        return {
            "status": task.status,
            "result": task.result,
            "error_message": task.error_message,
            "execution_time": task.execution_time,
            "tool_calls": task.tool_calls,
            "model_used": task.model_used,
            "images": task.images,
        }


# Singleton instance
_repository: TaskRepository | None = None


def get_task_repository(db_path: str = "data/tasks.db") -> TaskRepository:
    """Get the singleton TaskRepository instance."""
    global _repository
    if _repository is None:
        _repository = TaskRepository(db_path=db_path)
    return _repository
