# src/api/tasks.py
"""Background task management and webhook callback logic.

Handles agent execution in background tasks and sends webhook callbacks
with retry logic using tenacity. Tasks are persisted to SQLite for
durability across server restarts.
"""

import base64
import logging
import time
from typing import Any

import httpx
import tenacity

from src.config import settings
from src.core.agent.core import AgentRunner
from src.core.commands.executor import CommandExecutor
from src.core.commands.parser import parse_command
from src.core.commands.repository import CommandRepository
from src.interfaces.api.schemas import ImageDataResponse, RunRequest, WebhookPayload
from src.interfaces.api.task_repository import TaskRepository, get_task_repository
from src.middleware.guardrails import GuardrailConfig
from src.utils.image_handler import ImageData

logger = logging.getLogger(__name__)

# Default model identifier
DEFAULT_MODEL = "gemini/gemini-3-flash-preview"


def get_tasks_store() -> TaskRepository:
    """Get the task repository (SQLite-backed).

    Returns:
        TaskRepository instance for persistent task storage.
    """
    return get_task_repository()


@tenacity.retry(
    stop=tenacity.stop_after_attempt(5),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=60),
    retry=tenacity.retry_if_exception_type(
        (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)
    ),
    retry_error_callback=lambda _: None,  # Don't raise on final failure
    reraise=False,
)
async def send_webhook(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> bool:
    """Send webhook callback with retry logic.

    Retries up to 5 times with exponential backoff (1-60 seconds)
    on timeout, connection errors, or HTTP errors.

    Args:
        url: Webhook URL to POST to.
        payload: JSON payload to send.
        headers: Optional headers to include (e.g., auth tokens).

    Returns:
        True if webhook sent successfully, False otherwise.
    """
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=payload, headers=request_headers)
        response.raise_for_status()
        logger.info("Webhook sent successfully to %s", url)
        return True


def _images_to_response(images: list[ImageData]) -> list[ImageDataResponse]:
    return [
        ImageDataResponse(
            data=base64.b64encode(img.data).decode("utf-8"),
            mime_type=img.mime_type,
            filename=img.filename,
        )
        for img in images
    ]


def _images_to_dict(images: list[ImageDataResponse]) -> list[dict]:
    """Convert ImageDataResponse list to dict list for storage."""
    return [
        {
            "data": img.data,
            "mime_type": img.mime_type,
            "filename": img.filename,
        }
        for img in images
    ]


async def execute_agent(
    task_id: str,
    request: RunRequest,
) -> None:
    """Execute agent task and store results.

    Args:
        task_id: Unique task identifier.
        request: Run request with prompt and options.
    """
    repo = get_tasks_store()
    start_time = time.time()
    tool_calls: list[str] = []
    images: list[ImageDataResponse] = []

    prompt = request.prompt
    user_id = request.user_id or "anonymous"
    full_user_id = f"api:{user_id}"

    # Check for command
    parsed_cmd = parse_command(prompt)
    if parsed_cmd:
        executor = CommandExecutor(CommandRepository("data/commands.db"))
        cmd_prompt = executor.execute(parsed_cmd, user_id=full_user_id)
        if cmd_prompt:
            prompt = cmd_prompt

    guardrail_config = GuardrailConfig(current_user_id=user_id) if user_id else None
    runner = AgentRunner(
        api_key=settings.api_key,
        enable_mcp=True,
        guardrail_config=guardrail_config,
    )
    logger.info("Created AgentRunner for user %s", user_id)

    try:
        if request.user_id:
            run_result = await runner.run_async_with_user(
                prompt, request.user_id, platform="api"
            )
        else:
            run_result = await runner.run_async(prompt)

        execution_time = time.time() - start_time
        images = _images_to_response(run_result.images)

        repo.update(
            task_id=task_id,
            status="success",
            result=run_result.output,
            error_message=None,
            execution_time=execution_time,
            tool_calls=tool_calls,
            images=_images_to_dict(images),
        )

        logger.info("Task %s completed successfully in %.2fs", task_id, execution_time)

    except Exception as e:
        execution_time = time.time() - start_time

        repo.update(
            task_id=task_id,
            status="error",
            result=None,
            error_message=str(e),
            execution_time=execution_time,
            tool_calls=tool_calls,
            images=[],
        )

        logger.error("Task %s failed: %s", task_id, str(e))

    finally:
        runner.close()

    # Send webhook if configured
    if request.webhook_url:
        task = repo.get(task_id)
        if task:
            try:
                payload = WebhookPayload(
                    task_id=task_id,
                    status=task.status,
                    result=task.result,
                    error_message=task.error_message,
                    execution_time=task.execution_time,
                    tool_calls=task.tool_calls,
                    model_used=task.model_used,
                    images=[ImageDataResponse(**img) for img in task.images],
                )
                await send_webhook(
                    request.webhook_url,
                    payload.model_dump(),
                    request.webhook_headers,
                )
            except Exception as e:
                logger.error("Failed to send webhook for task %s: %s", task_id, str(e))

    # Cleanup old tasks periodically (1% chance per request)
    import random

    if random.random() < 0.01:
        repo.cleanup_old_tasks()
