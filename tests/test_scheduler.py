# tests/test_scheduler.py
"""Tests for scheduler module."""

import os
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.scheduler.models import ScheduledTask
from src.core.scheduler.tools import (
    cancel_scheduled_task,
    clear_scheduler_context,
    get_scheduler_context,
    list_scheduled_tasks,
    schedule_task,
    set_scheduler_context,
)

KST = ZoneInfo("Asia/Seoul")


class TestScheduledTask:
    """Tests for ScheduledTask model."""

    def test_to_dict(self):
        """Test converting task to dictionary."""
        task = ScheduledTask(
            task_id="abc12345",
            task_prompt="Test task",
            run_at=datetime(2024, 1, 15, 14, 0, 0, tzinfo=KST),
            user_id="slack:U123",
            channel_id="C456",
            thread_ts="1234567890.123456",
            status="pending",
        )

        result = task.to_dict()

        assert result["task_id"] == "abc12345"
        assert result["task_prompt"] == "Test task"
        assert result["user_id"] == "slack:U123"
        assert result["channel_id"] == "C456"
        assert result["thread_ts"] == "1234567890.123456"
        assert result["status"] == "pending"
        assert "2024-01-15" in result["run_at"]

    def test_from_dict(self):
        """Test creating task from dictionary."""
        data = {
            "task_id": "abc12345",
            "task_prompt": "Test task",
            "run_at": "2024-01-15T14:00:00+09:00",
            "user_id": "slack:U123",
            "channel_id": "C456",
            "thread_ts": "1234567890.123456",
            "status": "pending",
        }

        task = ScheduledTask.from_dict(data)

        assert task.task_id == "abc12345"
        assert task.task_prompt == "Test task"
        assert task.user_id == "slack:U123"
        assert task.channel_id == "C456"
        assert task.thread_ts == "1234567890.123456"
        assert task.status == "pending"


class TestSchedulerContext:
    """Tests for scheduler context management."""

    def test_set_and_get_context(self):
        """Test setting and getting scheduler context."""
        set_scheduler_context(
            user_id="slack:U123",
            channel_id="C456",
            thread_ts="1234567890.123456",
        )

        context = get_scheduler_context()

        assert context is not None
        assert context.user_id == "slack:U123"
        assert context.channel_id == "C456"
        assert context.thread_ts == "1234567890.123456"

    def test_clear_context(self):
        """Test clearing scheduler context."""
        set_scheduler_context(
            user_id="slack:U123",
            channel_id="C456",
        )

        clear_scheduler_context()
        context = get_scheduler_context()

        assert context is None

    def test_context_without_thread_ts(self):
        """Test context without thread_ts."""
        set_scheduler_context(
            user_id="slack:U123",
            channel_id="C456",
        )

        context = get_scheduler_context()

        assert context is not None
        assert context.thread_ts is None


class TestSchedulerManager:
    """Tests for SchedulerManager."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        yield db_path

        # Cleanup
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def scheduler(self, temp_db):
        """Create a scheduler with temporary database."""
        # Import here to avoid issues with singleton across tests
        from src.core.scheduler.manager import SchedulerManager

        # Reset singleton for testing
        SchedulerManager._instance = None
        SchedulerManager._initialized = False

        manager = SchedulerManager(db_path=temp_db)
        manager.start()

        yield manager

        manager.shutdown(wait=False)
        SchedulerManager._instance = None
        SchedulerManager._initialized = False

    def test_singleton_pattern(self, temp_db):
        """Test that SchedulerManager is a singleton."""
        from src.core.scheduler.manager import SchedulerManager

        SchedulerManager._instance = None
        SchedulerManager._initialized = False

        manager1 = SchedulerManager(db_path=temp_db)
        manager2 = SchedulerManager(db_path=temp_db)

        assert manager1 is manager2

        # Don't start since we don't have an event loop
        SchedulerManager._instance = None
        SchedulerManager._initialized = False

    @pytest.mark.asyncio
    async def test_add_and_get_task(self, scheduler):
        """Test adding and retrieving a task."""
        run_at = datetime.now(KST) + timedelta(hours=1)

        scheduler.add_task(
            task_id="test123",
            run_date=run_at,
            task_prompt="Test task prompt",
            user_id="slack:U123",
            channel_id="C456",
            thread_ts="1234567890.123456",
        )

        task = scheduler.get_task("test123")

        assert task is not None
        assert task["task_id"] == "test123"
        assert task["task_prompt"] == "Test task prompt"
        assert task["user_id"] == "slack:U123"

    @pytest.mark.asyncio
    async def test_get_tasks_by_user(self, scheduler):
        """Test getting tasks filtered by user."""
        run_at = datetime.now(KST) + timedelta(hours=1)

        scheduler.add_task(
            task_id="task1",
            run_date=run_at,
            task_prompt="Task 1",
            user_id="slack:U123",
            channel_id="C456",
        )
        scheduler.add_task(
            task_id="task2",
            run_date=run_at,
            task_prompt="Task 2",
            user_id="slack:U789",
            channel_id="C456",
        )

        tasks = scheduler.get_tasks(user_id="slack:U123")

        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "task1"

    @pytest.mark.asyncio
    async def test_cancel_task(self, scheduler):
        """Test cancelling a task."""
        run_at = datetime.now(KST) + timedelta(hours=1)

        scheduler.add_task(
            task_id="cancel_me",
            run_date=run_at,
            task_prompt="To be cancelled",
            user_id="slack:U123",
            channel_id="C456",
        )

        result = scheduler.cancel_task("cancel_me", user_id="slack:U123")
        task = scheduler.get_task("cancel_me")

        assert result is True
        assert task is None

    @pytest.mark.asyncio
    async def test_cancel_task_unauthorized(self, scheduler):
        """Test cancelling someone else's task fails."""
        run_at = datetime.now(KST) + timedelta(hours=1)

        scheduler.add_task(
            task_id="protected",
            run_date=run_at,
            task_prompt="Protected task",
            user_id="slack:U123",
            channel_id="C456",
        )

        result = scheduler.cancel_task("protected", user_id="slack:U789")

        assert result is False
        # Task should still exist
        task = scheduler.get_task("protected")
        assert task is not None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, scheduler):
        """Test cancelling a task that doesn't exist."""
        result = scheduler.cancel_task("nonexistent")
        assert result is False


class TestSchedulerTools:
    """Tests for scheduler tool functions."""

    @pytest.fixture(autouse=True)
    def setup_context(self):
        """Set up and clean up scheduler context for each test."""
        set_scheduler_context(
            user_id="slack:U123",
            channel_id="C456",
            thread_ts="1234567890.123456",
        )
        yield
        clear_scheduler_context()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        yield db_path

        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def mock_scheduler(self, temp_db):
        """Create a mock scheduler for tool tests."""
        from src.core.scheduler.manager import SchedulerManager

        SchedulerManager._instance = None
        SchedulerManager._initialized = False

        manager = SchedulerManager(db_path=temp_db)
        manager.start()

        yield manager

        manager.shutdown(wait=False)
        SchedulerManager._instance = None
        SchedulerManager._initialized = False

    @pytest.mark.asyncio
    async def test_schedule_task_success(self, mock_scheduler):
        """Test scheduling a task successfully."""
        result = schedule_task("1분 후", "테스트 작업")

        assert ":calendar:" in result
        assert "테스트 작업" in result
        assert "예약되었습니다" in result

    @pytest.mark.asyncio
    async def test_schedule_task_invalid_time(self, mock_scheduler):
        """Test scheduling with invalid time expression."""
        result = schedule_task("invalid time", "테스트 작업")

        assert "이해하지 못했습니다" in result

    def test_schedule_task_no_context(self):
        """Test scheduling without context."""
        # Import fresh to reset singleton
        from src.core.scheduler.manager import SchedulerManager

        SchedulerManager._instance = None
        SchedulerManager._initialized = False

        clear_scheduler_context()

        result = schedule_task("1분 후", "테스트 작업")

        assert "컨텍스트가 설정되지 않았습니다" in result

    @pytest.mark.asyncio
    async def test_list_scheduled_tasks_empty(self, mock_scheduler):
        """Test listing tasks when none exist."""
        result = list_scheduled_tasks()

        assert "예약된 작업이 없습니다" in result

    @pytest.mark.asyncio
    async def test_list_scheduled_tasks_with_tasks(self, mock_scheduler):
        """Test listing tasks when tasks exist."""
        # Add a task first
        schedule_task("1시간 후", "테스트 작업")

        result = list_scheduled_tasks()

        assert ":clipboard:" in result
        assert "테스트 작업" in result

    @pytest.mark.asyncio
    async def test_cancel_scheduled_task_success(self, mock_scheduler):
        """Test cancelling a task successfully."""
        # Schedule a task first
        schedule_result = schedule_task("1시간 후", "취소할 작업")

        # Extract task ID from result
        import re

        match = re.search(r"`([a-f0-9]{8})`", schedule_result)
        assert match is not None
        task_id = match.group(1)

        # Cancel it
        result = cancel_scheduled_task(task_id)

        assert ":wastebasket:" in result
        assert "취소되었습니다" in result

    @pytest.mark.asyncio
    async def test_cancel_scheduled_task_not_found(self, mock_scheduler):
        """Test cancelling a task that doesn't exist."""
        result = cancel_scheduled_task("nonexist")

        assert "찾을 수 없습니다" in result

    @pytest.mark.asyncio
    async def test_cancel_scheduled_task_invalid_id(self, mock_scheduler):
        """Test cancelling with invalid task ID."""
        result = cancel_scheduled_task("")

        assert "유효한 작업 ID" in result
