# src/tools/mcp/playwright.py
"""Playwright MCP server: configuration + cleanup utilities.

This file is self-contained - removing it cleanly removes
the Playwright MCP server and all related cleanup functionality.

Server config:
    Registers the Playwright MCP server via register_mcp_server().

Cleanup utilities:
    PlaywrightCleanupTracker tracks browser open/close state and
    manages temporary screenshot file cleanup.

Usage:
    from src.tools.mcp.playwright import PlaywrightCleanupTracker

    tracker = PlaywrightCleanupTracker()
    # ... use tracker.create_hook() as process_tool_call in MCPServerStdio
    # ... after agent run ...
    await tracker.cleanup()
"""

import glob
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.tools.mcp_registry import ServerCleanupHooks, register_mcp_server

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cleanup tracker
# ---------------------------------------------------------------------------

# Playwright MCP tool names that indicate browser is open
BROWSER_OPEN_TOOLS = {
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_take_screenshot",
    "browser_snapshot",
    "browser_hover",
    "browser_drag",
    "browser_select_option",
    "browser_press_key",
    "browser_evaluate",
    "browser_wait_for",
    "browser_handle_dialog",
    "browser_file_upload",
    "browser_tabs",
    "browser_navigate_back",
    "browser_network_requests",
    "browser_console_messages",
    "browser_run_code",
    "browser_resize",
}

# Tool that closes the browser
BROWSER_CLOSE_TOOL = "browser_close"

# Screenshot patterns to clean up
SCREENSHOT_PATTERNS = [
    "screenshot_*.png",
    "playwright_screenshot_*.png",
    "browser_screenshot_*.png",
]


@dataclass
class PlaywrightCleanupTracker:
    """Tracks Playwright MCP tool calls and provides cleanup utilities.

    Attributes:
        browser_opened: Whether any browser-opening tool was called.
        browser_closed: Whether browser_close was called.
        screenshot_files: List of screenshot file paths to clean up.
        temp_dir: Directory to scan for temporary screenshots.
    """

    browser_opened: bool = False
    browser_closed: bool = False
    screenshot_files: list[str] = field(default_factory=list)
    temp_dir: str = field(default_factory=lambda: tempfile.gettempdir())
    _session_start: datetime = field(default_factory=datetime.now)
    _cleanup_done: bool = False

    def track_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """Track a Playwright tool call.

        Args:
            tool_name: Name of the tool being called.
            args: Arguments passed to the tool.
        """
        # Strip any prefix (e.g., "playwright_browser_click" -> "browser_click")
        base_name = tool_name
        for prefix in ["playwright_", "pw_"]:
            if base_name.startswith(prefix):
                base_name = base_name[len(prefix) :]
                break

        if base_name in BROWSER_OPEN_TOOLS:
            self.browser_opened = True
            logger.debug("Playwright browser opened via %s", tool_name)

        if base_name == BROWSER_CLOSE_TOOL:
            self.browser_closed = True
            logger.debug("Playwright browser closed via %s", tool_name)

        # Track screenshot files if path is in args
        if base_name == "browser_take_screenshot":
            path = args.get("path")
            if path and isinstance(path, str):
                self.screenshot_files.append(path)
                logger.debug("Tracked screenshot file: %s", path)

    def create_hook(
        self,
        existing_hook: Callable[..., Awaitable[Any]] | None = None,
    ) -> Callable[..., Awaitable[Any]]:
        """Create a process_tool_call hook that tracks Playwright calls.

        This hook can be passed to MCPServerStdio's process_tool_call parameter.
        It tracks Playwright tool calls for cleanup purposes and optionally
        chains to an existing hook (e.g., guardrail hook).

        The hook signature must match pydantic-ai's process_tool_call interface:
        (ctx, call_tool, name, tool_args) -> ToolResult

        Args:
            existing_hook: Optional existing hook to chain to.

        Returns:
            Async hook function for process_tool_call.
        """

        async def hook(
            ctx: Any,
            call_tool: Callable[..., Awaitable[Any]],
            tool_name: str,
            tool_args: dict[str, Any],
        ) -> Any:
            """Hook that tracks Playwright calls and chains to existing hook.

            Args:
                ctx: Run context from pydantic-ai.
                call_tool: Function to call the actual tool.
                tool_name: Name of the tool being called.
                tool_args: Arguments for the tool.

            Returns:
                Tool result from call_tool or existing_hook.
            """
            # Track the call for cleanup
            self.track_tool_call(tool_name, tool_args)

            # Chain to existing hook if present
            if existing_hook:
                return await existing_hook(ctx, call_tool, tool_name, tool_args)

            # Call the actual tool
            return await call_tool(tool_name, tool_args, None)

        return hook

    @property
    def needs_browser_cleanup(self) -> bool:
        """Check if browser cleanup is needed.

        Returns:
            True if browser was opened but not closed.
        """
        return self.browser_opened and not self.browser_closed

    @property
    def needs_file_cleanup(self) -> bool:
        """Check if file cleanup is needed.

        Returns:
            True if there are tracked screenshot files.
        """
        return bool(self.screenshot_files)

    async def cleanup_browser(
        self,
        mcp_call: Callable[[str, dict], Awaitable[Any]] | None = None,
    ) -> bool:
        """Close the browser if it was opened but not closed.

        Args:
            mcp_call: Optional async function to call MCP tool.
                Signature: async def call(tool_name, args) -> result

        Returns:
            True if cleanup was performed, False otherwise.
        """
        if not self.needs_browser_cleanup:
            logger.debug("No browser cleanup needed")
            return False

        if mcp_call:
            try:
                await mcp_call(BROWSER_CLOSE_TOOL, {})
                self.browser_closed = True
                logger.info("Playwright browser closed via cleanup")
                return True
            except Exception as e:
                logger.warning("Failed to close browser via MCP: %s", e)
                return False
        else:
            logger.warning(
                "Browser cleanup needed but no mcp_call provided. "
                "Browser may still be running."
            )
            return False

    def cleanup_screenshot_files(self, max_age_minutes: int = 30) -> int:
        """Clean up tracked screenshot files and old temp screenshots.

        Args:
            max_age_minutes: Maximum age of temp files to keep (default: 30 min).

        Returns:
            Number of files deleted.
        """
        deleted_count = 0

        # Clean up tracked files
        for filepath in self.screenshot_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    deleted_count += 1
                    logger.debug("Deleted tracked screenshot: %s", filepath)
            except OSError as e:
                logger.warning("Failed to delete screenshot %s: %s", filepath, e)

        # Clean up old temp screenshots
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)

        for pattern in SCREENSHOT_PATTERNS:
            temp_pattern = os.path.join(self.temp_dir, pattern)
            for filepath in glob.glob(temp_pattern):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if mtime < cutoff_time:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.debug("Deleted old screenshot: %s", filepath)
                except OSError as e:
                    logger.warning(
                        "Failed to delete old screenshot %s: %s", filepath, e
                    )

        if deleted_count > 0:
            logger.info("Cleaned up %d screenshot file(s)", deleted_count)

        self.screenshot_files.clear()
        return deleted_count

    async def cleanup(
        self,
        mcp_call: Callable[[str, dict], Awaitable[Any]] | None = None,
        cleanup_files: bool = True,
    ) -> dict[str, Any]:
        """Perform full cleanup.

        Args:
            mcp_call: Optional async function to call MCP tool for browser close.
            cleanup_files: Whether to clean up screenshot files.

        Returns:
            Dict with cleanup results.
        """
        if self._cleanup_done:
            logger.debug("Cleanup already performed")
            return {"browser_closed": False, "files_deleted": 0, "skipped": True}

        results = {
            "browser_closed": False,
            "files_deleted": 0,
            "skipped": False,
        }

        # Close browser
        if await self.cleanup_browser(mcp_call):
            results["browser_closed"] = True

        # Clean up files
        if cleanup_files:
            results["files_deleted"] = self.cleanup_screenshot_files()

        self._cleanup_done = True
        return results

    def reset(self) -> None:
        """Reset tracker state for reuse."""
        self.browser_opened = False
        self.browser_closed = False
        self.screenshot_files.clear()
        self._session_start = datetime.now()
        self._cleanup_done = False


# ---------------------------------------------------------------------------
# Global tracker (convenience API)
# ---------------------------------------------------------------------------

_global_tracker: PlaywrightCleanupTracker | None = None


def get_global_tracker() -> PlaywrightCleanupTracker:
    """Get or create the global Playwright cleanup tracker.

    Returns:
        Global PlaywrightCleanupTracker instance.
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = PlaywrightCleanupTracker()
    return _global_tracker


def reset_global_tracker() -> None:
    """Reset the global tracker."""
    global _global_tracker
    if _global_tracker:
        _global_tracker.reset()


async def cleanup_playwright_session(
    mcp_call: Callable[[str, dict], Awaitable[Any]] | None = None,
) -> dict[str, Any]:
    """Convenience function to cleanup global Playwright session.

    Args:
        mcp_call: Optional async function to call MCP tool.

    Returns:
        Cleanup results dict.
    """
    tracker = get_global_tracker()
    results = await tracker.cleanup(mcp_call)
    reset_global_tracker()
    return results


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------

_cleanup_tracker = PlaywrightCleanupTracker()

register_mcp_server(
    key="playwright",
    name="Playwright",
    description="Browser automation for web testing, scraping, and interactions",
    command="npx",
    args=["-y", "@playwright/mcp@latest", "--headless", "--viewport-size=1920x1080"],
    cleanup_hooks=ServerCleanupHooks(
        create_process_hook=_cleanup_tracker.create_hook,
        needs_cleanup=lambda: (
            _cleanup_tracker.needs_browser_cleanup
            or _cleanup_tracker.needs_file_cleanup
        ),
        cleanup_async=_cleanup_tracker.cleanup,
        cleanup_sync=_cleanup_tracker.cleanup_screenshot_files,
        reset=_cleanup_tracker.reset,
    ),
)
