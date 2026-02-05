# src/api/schemas.py
"""Pydantic models for FastAPI request/response validation.

Defines request and response schemas for the agent API endpoints.
"""

from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request body for POST /run endpoint.

    Attributes:
        prompt: The task description for the agent.
        user_id: Optional user identifier for memory context.
        webhook_url: Optional URL to receive completion callback.
    """

    prompt: str = Field(..., description="Task description for the agent")
    user_id: str | None = Field(
        None, description="User identifier for personalized memory context"
    )
    webhook_url: str | None = Field(
        None, description="URL to receive webhook callback on completion"
    )
    webhook_headers: dict[str, str] | None = Field(
        None, description="Headers to include in webhook request (e.g., auth tokens)"
    )


class RunResponse(BaseModel):
    """Response body for POST /run endpoint.

    Attributes:
        task_id: Unique identifier for the created task.
        status: Current status of the task (pending).
    """

    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task status (pending)")


class ImageDataResponse(BaseModel):
    """Image data in API response (base64 encoded)."""

    data: str = Field(..., description="Base64 encoded image data")
    mime_type: str = Field(..., description="MIME type (e.g., image/png)")
    filename: str | None = Field(None, description="Original filename")


class StatusResponse(BaseModel):
    """Response body for GET /status/{task_id} endpoint.

    Attributes:
        task_id: Unique identifier for the task.
        status: Current status (pending, success, error).
        result: Agent output (if completed successfully).
        error_message: Error description (if failed).
        execution_time: Time taken to execute (in seconds).
        tool_calls: List of tools called during execution.
        model_used: Model identifier used for the task.
        images: List of images from MCP tools (base64 encoded).
    """

    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task status (pending, success, error)")
    result: Any | None = Field(None, description="Agent output")
    error_message: str | None = Field(None, description="Error message if failed")
    execution_time: float | None = Field(None, description="Execution time in seconds")
    tool_calls: list[str] = Field(
        default_factory=list, description="List of tools called"
    )
    model_used: str | None = Field(None, description="Model identifier used")
    images: list[ImageDataResponse] = Field(
        default_factory=list, description="Images from MCP tools (base64)"
    )


class CommandCreate(BaseModel):
    """Request body for POST /commands endpoint.

    Attributes:
        name: Command name (will be normalized to lowercase).
        prompt: The command prompt template. Use {input} as placeholder.
        user_id: User identifier for tracking ownership.
    """

    name: str = Field(..., description="Command name")
    prompt: str = Field(
        ..., description="Command prompt template with optional {input}"
    )
    user_id: str = Field(..., description="User identifier for ownership")


class CommandUpdate(BaseModel):
    """Request body for PUT /commands/{name} endpoint.

    Attributes:
        prompt: New prompt template.
        user_id: User identifier making the request (for permission check).
    """

    prompt: str = Field(..., description="New command prompt template")
    user_id: str = Field(..., description="User identifier for permission check")


class CommandResponse(BaseModel):
    """Response body for command GET endpoints.

    Attributes:
        name: Command name (lowercase).
        prompt: Enhanced/processed prompt.
        original_prompt: Original user-provided prompt.
        recommended_tools: List of recommended tool names.
        created_by: User identifier who created the command.
        created_at: ISO format creation timestamp.
        updated_at: ISO format last update timestamp.
    """

    name: str = Field(..., description="Command name")
    prompt: str = Field(..., description="Enhanced prompt")
    original_prompt: str = Field(..., description="Original prompt")
    recommended_tools: list[str] = Field(
        default_factory=list, description="Recommended tools for this command"
    )
    created_by: str = Field(..., description="Creator user ID")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")


class WebhookPayload(BaseModel):
    """Payload sent to webhook URL on task completion.

    Attributes:
        task_id: Unique identifier for the task.
        status: Final status (success, error).
        result: Agent output (if successful).
        error_message: Error description (if failed).
        execution_time: Time taken to execute (in seconds).
        tool_calls: List of tools called during execution.
        model_used: Model identifier used for the task.
        images: List of images from MCP tools (base64 encoded).
    """

    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Final status (success, error)")
    result: Any | None = Field(None, description="Agent output")
    error_message: str | None = Field(None, description="Error message if failed")
    execution_time: float | None = Field(None, description="Execution time in seconds")
    tool_calls: list[str] = Field(
        default_factory=list, description="List of tools called"
    )
    model_used: str | None = Field(None, description="Model identifier used")
    images: list[ImageDataResponse] = Field(
        default_factory=list, description="Images from MCP tools (base64)"
    )
