# src/core/scheduler/executor.py
"""Executor for scheduled tasks.

Runs scheduled tasks using AgentRunner and sends results via notifications.
"""

import logging

logger = logging.getLogger(__name__)


async def run_scheduled_task(
    task_id: str,
    task_prompt: str,
    user_id: str,
    channel_id: str,
    thread_ts: str | None,
) -> None:
    """Execute a scheduled task.

    This function is called by APScheduler when a task's scheduled time arrives.
    It runs the agent and sends the result to the original Slack thread.

    Args:
        task_id: Unique task identifier.
        task_prompt: The prompt/task to execute.
        user_id: User who scheduled the task.
        channel_id: Slack channel for response.
        thread_ts: Slack thread timestamp (can be None for new thread).
    """
    # Import here to avoid circular imports
    from src.core.scheduler.manager import SchedulerManager

    scheduler = SchedulerManager.get_instance()
    notifier = scheduler.get_notifier()

    if not notifier:
        logger.error("No notifier configured for scheduled task %s", task_id)
        return

    logger.info(
        "Executing scheduled task: id=%s, prompt=%s, user=%s",
        task_id,
        task_prompt[:50],
        user_id,
    )

    progress_ts: str | None = None
    progress_ts = await notifier.send(
        channel_id,
        "⏰ 예약된 작업 실행 중",
        thread_ts=thread_ts,
    )

    try:
        from src.config import settings
        from src.core.agent.core import AgentRunner
        from src.middleware.guardrails import GuardrailConfig
        from src.utils.slack_formatter import markdown_to_mrkdwn

        slack_user_id = (
            user_id.replace("slack:", "") if user_id.startswith("slack:") else user_id
        )

        guardrail_config = GuardrailConfig(current_user_id=slack_user_id)
        runner = AgentRunner(
            api_key=settings.api_key,
            enable_mcp=True,
            guardrail_config=guardrail_config,
        )

        # Run the agent with the extracted Slack user ID (not the full "slack:..." format)
        result = await runner.run_async_with_user(
            task_prompt,
            slack_user_id,
            platform="slack",
        )

        response_text = result.output if result.output else "결과 없음"
        converted_text = markdown_to_mrkdwn(response_text)

        success_msg = f"✅ 예약 작업 완료\n\n{converted_text}"

        if progress_ts:
            success = await notifier.update(channel_id, progress_ts, success_msg)
            if not success:
                await notifier.send(channel_id, success_msg, thread_ts=thread_ts)
        else:
            await notifier.send(channel_id, success_msg, thread_ts=thread_ts)

        logger.info("Scheduled task %s completed successfully", task_id)

    except Exception as e:
        logger.exception("Scheduled task %s failed: %s", task_id, e)

        error_text = f"❌ 예약 작업 실패: {str(e)[:200]}"

        if progress_ts:
            await notifier.update(channel_id, progress_ts, error_text)
        else:
            await notifier.send(channel_id, error_text, thread_ts=thread_ts)
