# src/core/scheduler/manager.py
"""APScheduler manager with SQLite persistence.

Provides singleton access to the scheduler for task management.
Uses AsyncIOScheduler for compatibility with async Slack bot.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from src.core.scheduler.notification import NotificationProtocol

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

KST = ZoneInfo("Asia/Seoul")

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Singleton manager for APScheduler with SQLite persistence.

    Manages scheduled tasks with:
    - SQLite job store for persistence across restarts
    - AsyncIO scheduler for async compatibility
    - Pluggable notification system via NotificationProtocol
    """

    _instance: SchedulerManager | None = None
    _initialized: bool = False

    def __new__(cls, db_path: str | None = None) -> SchedulerManager:  # noqa: ARG003, ARG004
        """Singleton pattern - return existing instance if available.

        Args:
            db_path: Path to SQLite database for job storage (used in __init__).

        Returns:
            SchedulerManager singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str | None = None):
        """Initialize the scheduler manager.

        Args:
            db_path: Path to SQLite database. Defaults to data/scheduler.db.
        """
        if SchedulerManager._initialized:
            return

        self._db_path = db_path or os.path.join("data", "scheduler.db")
        self._slack_client: Any = None
        self._notifier: NotificationProtocol | None = None
        self._scheduler: AsyncIOScheduler | None = None

        # Ensure data directory exists
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

        # Configure job stores
        jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{self._db_path}")}

        # Configure scheduler
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=KST,
            job_defaults={
                "coalesce": True,  # Combine missed runs into one
                "max_instances": 1,  # Only one instance of each job
                "misfire_grace_time": 60 * 5,  # 5 minute grace period
            },
        )

        # Add event listeners
        self._scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        SchedulerManager._initialized = True
        logger.info("SchedulerManager initialized with db: %s", self._db_path)

    @classmethod
    def get_instance(cls, db_path: str | None = None) -> SchedulerManager:
        """Get the singleton instance.

        Args:
            db_path: Path to SQLite database (only used on first call).

        Returns:
            SchedulerManager singleton instance.
        """
        return cls(db_path)

    def set_slack_client(self, client: Any) -> None:
        """Set the Slack client for notifications.

        Deprecated: Use set_notifier() with SlackNotifier instead.

        Args:
            client: Slack AsyncWebClient instance.
        """
        self._slack_client = client
        logger.info("Slack client set for scheduler notifications")

    def get_slack_client(self) -> Any:
        """Get the configured Slack client.

        Deprecated: Use get_notifier() instead.

        Returns:
            Slack client or None if not configured.
        """
        return self._slack_client

    def set_notifier(self, notifier: NotificationProtocol) -> None:
        """Set the notifier for sending notifications.

        Args:
            notifier: Implementation of NotificationProtocol.
        """
        self._notifier = notifier
        logger.info("Notifier set for scheduler notifications")

    def get_notifier(self) -> NotificationProtocol | None:
        """Get the configured notifier.

        Returns:
            NotificationProtocol implementation or None if not configured.
        """
        return self._notifier

    def start(self) -> None:
        """Start the scheduler."""
        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler.

        Args:
            wait: Whether to wait for running jobs to complete.
        """
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Scheduler shutdown")

    def add_task(
        self,
        task_id: str,
        run_date: datetime,
        task_prompt: str,
        user_id: str,
        channel_id: str,
        thread_ts: str | None = None,
    ) -> str:
        """Add a scheduled task.

        Args:
            task_id: Unique task identifier.
            run_date: When to execute the task.
            task_prompt: The prompt/task to execute.
            user_id: User who scheduled the task.
            channel_id: Slack channel for response.
            thread_ts: Slack thread timestamp.

        Returns:
            The task_id.

        Raises:
            RuntimeError: If scheduler is not initialized.
        """
        if not self._scheduler:
            raise RuntimeError("Scheduler not initialized")

        # Import executor function here to avoid circular imports
        from src.core.scheduler.executor import run_scheduled_task

        # Add job to scheduler
        self._scheduler.add_job(
            run_scheduled_task,
            "date",
            run_date=run_date,
            id=task_id,
            args=[task_id, task_prompt, user_id, channel_id, thread_ts],
            replace_existing=True,
        )

        logger.info(
            "Task scheduled: id=%s, run_at=%s, prompt=%s",
            task_id,
            run_date.isoformat(),
            task_prompt[:50],
        )
        return task_id

    def get_tasks(self, user_id: str | None = None) -> list[dict]:
        """Get scheduled tasks.

        Args:
            user_id: Optional user ID to filter by.

        Returns:
            List of task dictionaries with id, run_date, prompt, etc.
        """
        if not self._scheduler:
            return []

        jobs = self._scheduler.get_jobs()
        tasks = []

        for job in jobs:
            # Extract task info from job args
            if job.args and len(job.args) >= 5:
                job_task_id, job_prompt, job_user_id, job_channel, job_thread = (
                    job.args[:5]
                )

                # Filter by user if specified
                if user_id and job_user_id != user_id:
                    continue

                tasks.append(
                    {
                        "task_id": job_task_id,
                        "task_prompt": job_prompt,
                        "run_at": job.next_run_time,
                        "user_id": job_user_id,
                        "channel_id": job_channel,
                        "thread_ts": job_thread,
                    }
                )

        # Sort by run time
        tasks.sort(
            key=lambda t: t["run_at"]
            if t["run_at"]
            else datetime.max.replace(tzinfo=KST)
        )
        return tasks

    def cancel_task(self, task_id: str, user_id: str | None = None) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: Task ID to cancel.
            user_id: Optional user ID for authorization check.

        Returns:
            True if cancelled, False if not found or unauthorized.
        """
        if not self._scheduler:
            return False

        try:
            job = self._scheduler.get_job(task_id)
            if not job:
                return False

            # Check user authorization if user_id provided
            if user_id and job.args and len(job.args) >= 3:
                job_user_id = job.args[2]
                if job_user_id != user_id:
                    logger.warning(
                        "Unauthorized cancel attempt: task=%s, user=%s, owner=%s",
                        task_id,
                        user_id,
                        job_user_id,
                    )
                    return False

            self._scheduler.remove_job(task_id)
            logger.info("Task cancelled: %s", task_id)
            return True

        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return False

    def get_task(self, task_id: str) -> dict | None:
        """Get a specific task by ID.

        Args:
            task_id: Task ID to retrieve.

        Returns:
            Task dictionary or None if not found.
        """
        if not self._scheduler:
            return None

        job = self._scheduler.get_job(task_id)
        if not job or not job.args or len(job.args) < 5:
            return None

        job_task_id, job_prompt, job_user_id, job_channel, job_thread = job.args[:5]
        return {
            "task_id": job_task_id,
            "task_prompt": job_prompt,
            "run_at": job.next_run_time,
            "user_id": job_user_id,
            "channel_id": job_channel,
            "thread_ts": job_thread,
        }

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle job execution events for logging.

        Args:
            event: Job execution event from APScheduler.
        """
        if event.exception:
            logger.error(
                "Job %s failed: %s",
                event.job_id,
                str(event.exception),
            )
        else:
            logger.info("Job %s completed successfully", event.job_id)

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running.

        Returns:
            True if scheduler is running.
        """
        return self._scheduler is not None and self._scheduler.running


# Module-level helper for getting the singleton
def get_scheduler(db_path: str | None = None) -> SchedulerManager:
    """Get the scheduler manager singleton.

    Args:
        db_path: Path to SQLite database (only used on first call).

    Returns:
        SchedulerManager singleton instance.
    """
    return SchedulerManager.get_instance(db_path)
