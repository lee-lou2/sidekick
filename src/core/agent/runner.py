"""Agent runner with retry logic and image extraction."""

import asyncio
import concurrent.futures
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    BinaryContent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
)

from src.core.agent.factory import AgentFactory
from src.core.agent.utils import (
    AgentRunResult,
    _normalize_tool_result,
    _retry_decorator,
    _store_images_in_context,
)
from src.core.context import get_generated_images
from src.core.memory import build_memory_prompt
from src.middleware.guardrails import GuardrailConfig
from src.utils.image_handler import ImageData, extract_images_from_result

logger = logging.getLogger(__name__)


class AgentRunner:
    """Runner that wraps Pydantic AI Agent with image extraction and message history.

    Provides both sync and async interfaces for backward compatibility.
    Supports conversation memory via message_history parameter.
    """

    def __init__(
        self,
        tools: list | None = None,
        api_key: str | None = None,
        enable_mcp: bool = False,
        mcp_servers: list[str] | None = None,
        guardrail_config: GuardrailConfig | None = None,
    ) -> None:
        """Initialize the agent runner.

        Args:
            tools: Deprecated. Tools are now managed via FunctionToolset.
            api_key: Google API key. Uses settings.api_key if not provided.
            enable_mcp: Enable MCP server connections.
            mcp_servers: List of MCP server names to connect. Connects all if None.
            guardrail_config: Security guardrail configuration for MCP tools.
        """
        if tools is not None:
            logger.warning(
                "AgentRunner: 'tools' parameter is deprecated. "
                "Tools are now managed via FunctionToolset in src/tools/__init__.py"
            )

        self._factory = AgentFactory(
            api_key=api_key,
            enable_mcp=enable_mcp,
            mcp_servers=mcp_servers,
            guardrail_config=guardrail_config,
        )
        self._agent = self._factory.create_agent()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._enable_mcp = enable_mcp

        # Message history for conversation memory
        self._message_history: list[ModelMessage] = []

        logger.info("AgentRunner initialized (mcp=%s)", enable_mcp)

    @_retry_decorator
    async def _run_async_internal(
        self,
        prompt: str,
        message_history: list[ModelMessage] | None = None,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        """Internal async run with retry logic.

        Args:
            prompt: The prompt to send to the agent.
            message_history: Optional previous messages for context.
            on_tool_call: Optional async callback called when a tool is invoked.
                Receives the tool name as argument. Useful for progress updates.

        Returns:
            AgentRunResult with output, images, and messages.
        """
        all_images: list[ImageData] = []

        async def _event_handler(ctx, event_stream):
            """Handle tool call and result events."""
            async for event in event_stream:
                if isinstance(event, FunctionToolCallEvent):
                    # Notify callback when tool is being called
                    # Tool name is in event.part.tool_name
                    if on_tool_call:
                        try:
                            tool_name = event.part.tool_name
                            await on_tool_call(tool_name)
                        except Exception as e:
                            logger.warning("on_tool_call callback failed: %s", e)
                elif isinstance(event, FunctionToolResultEvent):
                    result_content = event.result.content
                    result_str = str(result_content) if result_content else ""

                    # Check if this is an image generation/edit result with request ID
                    import re

                    match = re.search(
                        r"\[IMAGE_(?:GENERATED|EDITED):([^\]]+)\]", result_str
                    )
                    if match:
                        # Extract images using request ID (thread-safe)
                        request_id = match.group(1)
                        stored_images = get_generated_images(request_id)
                        for img in stored_images:
                            img_bytes = img.get("bytes")
                            if img_bytes:
                                all_images.append(
                                    ImageData(
                                        data=img_bytes,
                                        mime_type=img.get("mime_type", "image/png"),
                                        filename=img.get("name"),
                                    )
                                )
                        logger.debug(
                            "Retrieved %d image(s) for request_id=%s",
                            len(stored_images),
                            request_id,
                        )
                    else:
                        # For other tools (e.g., MCP), extract images from result
                        normalized = _normalize_tool_result(result_content)
                        images = extract_images_from_result(normalized)
                        all_images.extend(images)
                        if images:
                            _store_images_in_context(images)

                    # Check event.content for BinaryContent (Playwright MCP screenshots)
                    # Playwright MCP returns images as separate UserContent, not in result
                    event_content = event.content
                    if event_content:
                        if isinstance(event_content, BinaryContent):
                            media_type = str(event_content.media_type)
                            if media_type.startswith("image/"):
                                logger.info(
                                    "Found BinaryContent in event.content: %s (%d bytes)",
                                    media_type,
                                    len(event_content.data),
                                )
                                all_images.append(
                                    ImageData(
                                        data=event_content.data,
                                        mime_type=media_type,
                                        filename=f"screenshot.{media_type.split('/')[-1]}",
                                    )
                                )
                        elif hasattr(event_content, "__iter__") and not isinstance(
                            event_content, str | bytes
                        ):
                            for item in event_content:
                                if isinstance(item, BinaryContent):
                                    media_type = str(item.media_type)
                                    if media_type.startswith("image/"):
                                        logger.info(
                                            "Found BinaryContent in event.content list: %s (%d bytes)",
                                            media_type,
                                            len(item.data),
                                        )
                                        all_images.append(
                                            ImageData(
                                                data=item.data,
                                                mime_type=media_type,
                                                filename=f"screenshot.{media_type.split('/')[-1]}",
                                            )
                                        )

        # Run agent with event handler to capture tool results
        result = await self._agent.run(
            prompt,
            message_history=message_history,
            event_stream_handler=_event_handler,
        )

        return AgentRunResult(
            output=str(result.output),
            images=all_images,
            messages=result.all_messages(),
        )

    async def run_async(
        self,
        prompt: str,
        preserve_history: bool = False,
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        """Native async run - use in async contexts (FastAPI, Slack).

        Includes retry logic: 3 attempts with exponential backoff.
        Retries on transient HTTP errors (429, 5xx).
        Does NOT retry on validation/user errors.

        Args:
            prompt: The prompt to send to the agent.
            preserve_history: If True, maintains conversation history across calls.
            on_tool_call: Optional async callback called when a tool is invoked.
                Receives the tool name as argument. Useful for progress updates.

        Returns:
            AgentRunResult with output, images, and messages.
        """
        try:
            history = self._message_history if preserve_history else None
            result = await self._run_async_internal(
                prompt, message_history=history, on_tool_call=on_tool_call
            )

            # Update message history if preserving
            if preserve_history:
                self._message_history = result.messages

            return result
        except UserError:
            logger.error("UserError - not retrying: %s", prompt[:100])
            raise

    def run(self, prompt: str, preserve_history: bool = False) -> AgentRunResult:
        """Sync run - SAFE to call from async context (runs in thread).

        Uses ThreadPoolExecutor to avoid blocking the event loop.

        Args:
            prompt: The prompt to send to the agent.
            preserve_history: If True, maintains conversation history across calls.

        Returns:
            AgentRunResult with output, images, and messages.
        """

        def _run_in_new_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.run_async(prompt, preserve_history=preserve_history)
                )
            finally:
                loop.close()

        future = self._executor.submit(_run_in_new_loop)
        return future.result(timeout=300)  # 5 minute timeout

    def run_with_user(
        self, task: str, user_id: str, platform: str = "slack"
    ) -> AgentRunResult:
        """Sync run with user context (wraps run_async_with_user in thread)."""

        def _run_in_new_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.run_async_with_user(task, user_id, platform)
                )
            finally:
                loop.close()

        future = self._executor.submit(_run_in_new_loop)
        return future.result(timeout=300)  # 5 minute timeout

    async def run_async_with_user(
        self,
        task: str,
        user_id: str,
        platform: str = "slack",
        on_tool_call: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentRunResult:
        """Async run with user context for memory-aware interactions.

        The agent uses MCP memory tools to retrieve and store user information.
        This method builds a prompt with user context that instructs the agent
        to use the memory tools appropriately.

        Args:
            task: The task/prompt to send to the agent.
            user_id: User identifier for memory context.
            platform: Platform name (e.g., "slack", "api").
            on_tool_call: Optional async callback called when a tool is invoked.

        Returns:
            AgentRunResult with output, images, and messages.
        """
        prompt = build_memory_prompt(user_id, task, platform)
        return await self.run_async(prompt, on_tool_call=on_tool_call)

    def run_streaming(self, task: str) -> Any:
        """Run agent and return result. For backward compat.

        Note: Streaming events are handled internally for image extraction.
        This method returns the final result directly.
        """
        return self.run(task)

    def clear_history(self) -> None:
        """Clear the conversation message history."""
        self._message_history = []
        logger.info("AgentRunner: Message history cleared")

    def get_history(self) -> list[ModelMessage]:
        """Get the current message history.

        Returns:
            List of ModelMessage objects from previous conversations.
        """
        return self._message_history.copy()

    def close(self) -> None:
        """Close MCP connections and executor (sync).

        Note: For full Playwright cleanup (including browser close),
        use close_async() instead.
        """
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._factory.close()

    async def close_async(self) -> None:
        """Async close with full Playwright cleanup.

        Performs:
        1. Playwright browser close (if open)
        2. Playwright file cleanup
        3. MCP connections cleanup
        4. Executor shutdown
        """
        self._executor.shutdown(wait=True, cancel_futures=True)
        await self._factory.close_async()

    def __enter__(self) -> "AgentRunner":
        """Enter context manager."""
        return self

    def __exit__(self, *args) -> None:
        """Exit context manager, closing MCP connections."""
        self.close()

    async def __aenter__(self) -> "AgentRunner":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context manager with full Playwright cleanup."""
        await self.close_async()
