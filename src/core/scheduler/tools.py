# src/core/scheduler/tools.py
"""Agent tools for task scheduling.

Provides tools for scheduling, listing, and cancelling tasks.
Uses contextvars for async-safe context propagation.
"""

import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.core.scheduler.manager import SchedulerManager
from src.core.scheduler.time_parser import format_time_kst, parse_korean_time

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


@dataclass
class SchedulerContext:
    """Context for scheduler operations.

    Stores the current user, channel, and thread information
    needed for scheduling tasks from within agent tool execution.
    """

    user_id: str
    channel_id: str
    thread_ts: str | None = None


# ContextVar for async-safe context propagation
# Works across async tasks and thread pools
_scheduler_context: ContextVar[SchedulerContext | None] = ContextVar(
    "scheduler_context", default=None
)


def set_scheduler_context(
    user_id: str,
    channel_id: str,
    thread_ts: str | None = None,
) -> None:
    """Set the scheduler context for the current async context.

    This should be called before running the agent to provide
    context for scheduling operations. Works with both sync and async code.

    Args:
        user_id: User ID (e.g., "slack:U12345").
        channel_id: Slack channel ID.
        thread_ts: Slack thread timestamp.
    """
    context = SchedulerContext(
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )
    _scheduler_context.set(context)
    logger.debug(
        "Scheduler context set: user=%s, channel=%s, thread=%s",
        user_id,
        channel_id,
        thread_ts,
    )


def get_scheduler_context() -> SchedulerContext | None:
    """Get the current scheduler context.

    Returns:
        SchedulerContext or None if not set.
    """
    return _scheduler_context.get()


def clear_scheduler_context() -> None:
    """Clear the scheduler context."""
    _scheduler_context.set(None)
    logger.debug("Scheduler context cleared")


def _generate_task_id() -> str:
    """Generate a short, unique task ID.

    Returns:
        8-character hex string.
    """
    return uuid.uuid4().hex[:8]


def schedule_task(
    time_expression: str,
    task_description: str,
) -> str:
    """Schedule a task to be executed at a future time.

    The task will be executed by the agent at the scheduled time,
    and the result will be sent to the current Slack thread.

    Supports Korean and English time expressions:
    - Relative: "1분 후", "30초 뒤", "2시간 후", "in 5 minutes"
    - Absolute: "오후 3시", "15:00", "내일 오전 10시"

    Args:
        time_expression: When to execute the task (e.g., "1분 후", "오후 3시").
        task_description: What task the agent should perform.

    Returns:
        Confirmation message with task ID and scheduled time.

    Examples:
        schedule_task("1분 후", "오늘 뉴스 요약해줘")
        schedule_task("오후 5시", "회의 준비 알림")
        schedule_task("in 30 minutes", "check email")
    """
    # Get context
    context = get_scheduler_context()
    if not context:
        logger.error("schedule_task called without context")
        return (
            "오류: 스케줄러 컨텍스트가 설정되지 않았습니다.\n"
            "이 기능은 Slack에서만 사용 가능합니다."
        )

    # Check if scheduler is running
    try:
        scheduler = SchedulerManager.get_instance()
        if not scheduler.is_running:
            logger.error("Scheduler is not running")
            return "오류: 스케줄러가 실행 중이 아닙니다. 봇을 재시작해 주세요."
    except Exception as e:
        logger.exception("Failed to get scheduler instance: %s", e)
        return f"오류: 스케줄러 초기화 실패 - {str(e)}"

    # Parse time expression
    run_at = parse_korean_time(time_expression)
    if not run_at:
        return (
            f"시간 표현을 이해하지 못했습니다: '{time_expression}'\n\n"
            "지원하는 형식:\n"
            "- 상대 시간: '1분 후', '30초 뒤', '2시간 후', 'in 5 minutes'\n"
            "- 절대 시간: '오후 3시', '15:00', '14시 30분'\n"
            "- 조합: '내일 오전 10시', 'tomorrow 15:00'"
        )

    # Validate time is in the future
    now = datetime.now(KST)
    if run_at <= now:
        return f"오류: 예약 시간이 과거입니다. 현재 시간: {format_time_kst(now)}"

    # Generate task ID
    task_id = _generate_task_id()

    try:
        # Add task to scheduler (already retrieved above)
        scheduler.add_task(
            task_id=task_id,
            run_date=run_at,
            task_prompt=task_description,
            user_id=context.user_id,
            channel_id=context.channel_id,
            thread_ts=context.thread_ts,
        )

        formatted_time = format_time_kst(run_at)
        return (
            f":calendar: 작업이 예약되었습니다!\n"
            f"- ID: `{task_id}`\n"
            f"- 실행 시간: {formatted_time}\n"
            f"- 작업: {task_description}"
        )

    except Exception as e:
        logger.exception("Failed to schedule task: %s", e)
        return f"작업 예약 실패: {str(e)}"


def list_scheduled_tasks(include_all: bool = False) -> str:
    """List scheduled tasks.

    Shows pending tasks with their IDs, scheduled times, and descriptions.

    Args:
        include_all: If True, show all users' tasks. If False, only show
            tasks for the current user.

    Returns:
        Formatted list of scheduled tasks or message if none found.
    """
    context = get_scheduler_context()
    user_id = context.user_id if context and not include_all else None

    try:
        scheduler = SchedulerManager.get_instance()
        tasks = scheduler.get_tasks(user_id=user_id)

        if not tasks:
            if include_all:
                return "예약된 작업이 없습니다."
            return "예약된 작업이 없습니다. (본인의 작업만 표시됩니다)"

        lines = [":clipboard: 예약된 작업 목록:\n"]

        for task in tasks:
            formatted_time = (
                format_time_kst(task["run_at"]) if task["run_at"] else "알 수 없음"
            )
            prompt_preview = task["task_prompt"][:50]
            if len(task["task_prompt"]) > 50:
                prompt_preview += "..."

            lines.append(
                f"- `{task['task_id']}` | {formatted_time}\n  작업: {prompt_preview}"
            )

        return "\n".join(lines)

    except Exception as e:
        logger.exception("Failed to list tasks: %s", e)
        return f"작업 목록 조회 실패: {str(e)}"


def cancel_scheduled_task(task_id: str) -> str:
    """Cancel a scheduled task.

    Only the user who created the task can cancel it.

    Args:
        task_id: The task ID to cancel (8-character hex string).

    Returns:
        Confirmation message or error if not found/unauthorized.
    """
    if not task_id or len(task_id) < 4:
        return "오류: 유효한 작업 ID를 입력해주세요."

    context = get_scheduler_context()
    user_id = context.user_id if context else None

    try:
        scheduler = SchedulerManager.get_instance()

        # Get task info first for confirmation message
        task = scheduler.get_task(task_id)
        if not task:
            return f"작업을 찾을 수 없습니다: `{task_id}`"

        # Check authorization
        if user_id and task["user_id"] != user_id:
            return "권한 없음: 본인이 예약한 작업만 취소할 수 있습니다."

        # Cancel the task
        success = scheduler.cancel_task(task_id, user_id=user_id)

        if success:
            return (
                f":wastebasket: 작업이 취소되었습니다.\n"
                f"- ID: `{task_id}`\n"
                f"- 작업: {task['task_prompt'][:50]}"
            )
        else:
            return f"작업 취소 실패: `{task_id}`"

    except Exception as e:
        logger.exception("Failed to cancel task %s: %s", task_id, e)
        return f"작업 취소 실패: {str(e)}"


def get_scheduler_tools() -> list[Callable[..., Any]]:
    """Get all scheduler tools as a list.

    Returns:
        List of tool functions for task scheduling operations.
    """
    return [
        schedule_task,
        list_scheduled_tasks,
        cancel_scheduled_task,
    ]
