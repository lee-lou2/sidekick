# src/scheduler/models.py
"""Data models for the scheduler module."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScheduledTask:
    """Represents a scheduled task.

    Attributes:
        task_id: Unique identifier for the task.
        task_prompt: The prompt/task description to execute.
        run_at: Scheduled execution time (KST).
        user_id: ID of the user who scheduled the task.
        channel_id: Slack channel ID for response.
        thread_ts: Slack thread timestamp for threading replies.
        created_at: When the task was created.
        status: Task status (pending, running, completed, failed, cancelled).
    """

    task_id: str
    task_prompt: str
    run_at: datetime
    user_id: str
    channel_id: str
    thread_ts: str | None = None
    created_at: datetime | None = None
    status: str = "pending"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the task.
        """
        return {
            "task_id": self.task_id,
            "task_prompt": self.task_prompt,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "thread_ts": self.thread_ts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        """Create from dictionary.

        Args:
            data: Dictionary with task data.

        Returns:
            ScheduledTask instance.
        """
        return cls(
            task_id=data["task_id"],
            task_prompt=data["task_prompt"],
            run_at=datetime.fromisoformat(data["run_at"])
            if data.get("run_at")
            else None,
            user_id=data["user_id"],
            channel_id=data["channel_id"],
            thread_ts=data.get("thread_ts"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            status=data.get("status", "pending"),
        )
