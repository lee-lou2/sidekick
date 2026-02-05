# src/api/main.py
"""FastAPI application with agent execution endpoints.

Provides REST API for running agent tasks asynchronously with
optional webhook callbacks for completion notifications.
"""

import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Load environment variables from .env file
load_dotenv()

from src.config import settings  # noqa: E402
from src.core.commands import tools as command_tools  # noqa: E402
from src.core.commands.repository import get_repository  # noqa: E402
from src.core.lifecycle import get_lifecycle_manager  # noqa: E402
from src.core.scheduler.manager import SchedulerManager  # noqa: E402
from src.interfaces.api.schemas import (  # noqa: E402
    CommandCreate,
    CommandResponse,
    CommandUpdate,
    RunRequest,
    RunResponse,
    StatusResponse,
)
from src.interfaces.api.security import (  # noqa: E402
    get_rate_limit_string,
    limiter,
    verify_api_key,
)
from src.interfaces.api.task_repository import get_task_repository  # noqa: E402
from src.interfaces.api.tasks import execute_agent  # noqa: E402

logger = logging.getLogger(__name__)

ApiKey = Annotated[str, Depends(verify_api_key)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    if settings.api_key:
        app.state.api_key_available = True
        logger.info("API key validated - agent ready")
    else:
        app.state.api_key_available = False
        logger.warning("GOOGLE_API_KEY not set - agent will not work")

    lifecycle = get_lifecycle_manager()
    lifecycle.register("scheduler", SchedulerManager.get_instance())
    await lifecycle.startup()

    yield

    await lifecycle.shutdown()
    logger.info("Shutting down...")


app = FastAPI(
    title="Personal AI Agent API",
    description="REST API for running AI agent tasks asynchronously",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.post("/run", response_model=RunResponse)
@limiter.limit(get_rate_limit_string)
async def run_agent(
    request: Request,
    run_request: RunRequest,
    background_tasks: BackgroundTasks,
    _api_key: ApiKey,
) -> RunResponse:
    """Submit a task for the agent to execute.

    Creates a new task with a unique ID and schedules it for
    background execution. Optionally sends a webhook callback
    when the task completes.

    Args:
        request: RunRequest with prompt and optional webhook_url.
        background_tasks: FastAPI background task manager.

    Returns:
        RunResponse with task_id and initial status.

    Raises:
        HTTPException: If agent runner is not initialized.
    """
    if not getattr(app.state, "api_key_available", False):
        raise HTTPException(
            status_code=503,
            detail="Agent not available. Check GOOGLE_API_KEY.",
        )

    # Generate unique task ID and create in repository
    task_id = str(uuid.uuid4())
    repo = get_task_repository()
    repo.create(task_id)

    # Schedule background execution
    background_tasks.add_task(
        execute_agent,
        task_id,
        run_request,
    )

    logger.info("Task %s created and queued", task_id)

    return RunResponse(task_id=task_id, status="pending")


@app.get("/status/{task_id}", response_model=StatusResponse)
@limiter.limit(get_rate_limit_string)
async def get_status(
    request: Request, task_id: str, _api_key: ApiKey
) -> StatusResponse:
    """Get the status of a task.

    Returns the current status and results (if completed) for
    a previously submitted task.

    Args:
        task_id: Unique identifier for the task.

    Returns:
        StatusResponse with current status and results.

    Raises:
        HTTPException: If task_id is not found.
    """
    repo = get_task_repository()
    task = repo.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return StatusResponse(
        task_id=task_id,
        status=task.status,
        result=task.result,
        error_message=task.error_message,
        execution_time=task.execution_time,
        tool_calls=task.tool_calls,
        model_used=task.model_used,
        images=task.images,
    )


@app.get("/health")
@limiter.limit(get_rate_limit_string)
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint.

    Returns:
        Dictionary with health status and agent availability.
    """
    return {
        "status": "healthy",
        "agent_ready": getattr(app.state, "api_key_available", False),
    }


def _get_command_repository():
    """Get CommandRepository singleton instance."""
    return get_repository()


@app.post("/commands", status_code=201)
@limiter.limit(get_rate_limit_string)
async def create_command(
    request: Request, cmd_request: CommandCreate, _api_key: ApiKey
) -> dict[str, str]:
    """Create a new command with AI enhancement."""
    user_id = f"api:{cmd_request.user_id}"
    result = command_tools.create_command(cmd_request.name, cmd_request.prompt, user_id)

    if result.startswith("Error:"):
        raise HTTPException(status_code=400, detail=result)

    return {"message": result}


@app.get("/commands", response_model=list[CommandResponse])
@limiter.limit(get_rate_limit_string)
async def list_commands(request: Request, _api_key: ApiKey) -> list[CommandResponse]:
    """List all available commands."""
    repo = _get_command_repository()
    commands = repo.list_all()

    return [
        CommandResponse(
            name=cmd.name,
            prompt=cmd.prompt,
            original_prompt=cmd.original_prompt,
            recommended_tools=cmd.recommended_tools,
            created_by=cmd.created_by,
            created_at=cmd.created_at.isoformat(),
            updated_at=cmd.updated_at.isoformat(),
        )
        for cmd in commands
    ]


@app.get("/commands/{name}", response_model=CommandResponse)
@limiter.limit(get_rate_limit_string)
async def get_command(request: Request, name: str, _api_key: ApiKey) -> CommandResponse:
    """Get a specific command by name."""
    repo = _get_command_repository()
    cmd = repo.get_by_name(name)

    if cmd is None:
        raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

    return CommandResponse(
        name=cmd.name,
        prompt=cmd.prompt,
        original_prompt=cmd.original_prompt,
        recommended_tools=cmd.recommended_tools,
        created_by=cmd.created_by,
        created_at=cmd.created_at.isoformat(),
        updated_at=cmd.updated_at.isoformat(),
    )


@app.put("/commands/{name}")
@limiter.limit(get_rate_limit_string)
async def update_command(
    request: Request, name: str, cmd_request: CommandUpdate, _api_key: ApiKey
) -> dict[str, str]:
    """Update an existing command (creator only)."""
    user_id = f"api:{cmd_request.user_id}"
    result = command_tools.update_command(name, cmd_request.prompt, user_id)

    if "not found" in result.lower():
        raise HTTPException(status_code=404, detail=result)
    if "permission denied" in result.lower():
        raise HTTPException(status_code=403, detail=result)

    return {"message": result}


@app.delete("/commands/{name}")
@limiter.limit(get_rate_limit_string)
async def delete_command(
    request: Request, name: str, user_id: str, _api_key: ApiKey
) -> dict[str, str]:
    """Delete a command (creator only)."""
    api_user_id = f"api:{user_id}"
    result = command_tools.delete_command(name, api_user_id)

    if "not found" in result.lower():
        raise HTTPException(status_code=404, detail=result)
    if "permission denied" in result.lower():
        raise HTTPException(status_code=403, detail=result)

    return {"message": result}
