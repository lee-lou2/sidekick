# tests/test_playwright_cleanup.py
"""Tests for Playwright MCP cleanup utilities."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.tools.mcp.playwright import (
    BROWSER_CLOSE_TOOL,
    PlaywrightCleanupTracker,
    cleanup_playwright_session,
    get_global_tracker,
    reset_global_tracker,
)


class TestPlaywrightCleanupTracker:
    """Tests for PlaywrightCleanupTracker."""

    def test_init_defaults(self):
        """Test default initialization."""
        tracker = PlaywrightCleanupTracker()
        assert not tracker.browser_opened
        assert not tracker.browser_closed
        assert tracker.screenshot_files == []
        assert not tracker.needs_browser_cleanup
        assert not tracker.needs_file_cleanup

    def test_track_browser_open_tool(self):
        """Test tracking browser-opening tools."""
        tracker = PlaywrightCleanupTracker()

        # Test various browser-opening tools
        for tool in ["browser_navigate", "browser_click", "browser_take_screenshot"]:
            tracker.reset()
            tracker.track_tool_call(tool, {})
            assert tracker.browser_opened, f"{tool} should mark browser as opened"
            assert not tracker.browser_closed

    def test_track_browser_close_tool(self):
        """Test tracking browser_close tool."""
        tracker = PlaywrightCleanupTracker()
        tracker.track_tool_call("browser_close", {})

        assert tracker.browser_closed
        # browser_close is not in BROWSER_OPEN_TOOLS
        assert not tracker.browser_opened

    def test_track_prefixed_tools(self):
        """Test tracking tools with prefixes."""
        tracker = PlaywrightCleanupTracker()

        # Playwright prefix
        tracker.track_tool_call("playwright_browser_navigate", {})
        assert tracker.browser_opened

        tracker.reset()

        # pw prefix
        tracker.track_tool_call("pw_browser_click", {})
        assert tracker.browser_opened

    def test_track_screenshot_path(self):
        """Test tracking screenshot file paths."""
        tracker = PlaywrightCleanupTracker()
        tracker.track_tool_call(
            "browser_take_screenshot",
            {"path": "/tmp/screenshot.png"},
        )

        assert tracker.browser_opened
        assert "/tmp/screenshot.png" in tracker.screenshot_files
        assert tracker.needs_file_cleanup

    def test_needs_browser_cleanup(self):
        """Test needs_browser_cleanup property."""
        tracker = PlaywrightCleanupTracker()

        # No cleanup needed initially
        assert not tracker.needs_browser_cleanup

        # Browser opened but not closed = needs cleanup
        tracker.track_tool_call("browser_navigate", {})
        assert tracker.needs_browser_cleanup

        # Browser closed = no cleanup needed
        tracker.track_tool_call("browser_close", {})
        assert not tracker.needs_browser_cleanup

    def test_create_hook(self):
        """Test hook creation and chaining."""
        tracker = PlaywrightCleanupTracker()

        # Create hook without existing hook
        hook = tracker.create_hook()
        assert callable(hook)

    @pytest.mark.asyncio
    async def test_hook_tracks_calls(self):
        """Test that hook tracks tool calls."""
        tracker = PlaywrightCleanupTracker()
        hook = tracker.create_hook()

        call_tool = AsyncMock(return_value={"success": True})

        # Hook signature: (ctx, call_tool, name, args)
        result = await hook(
            MagicMock(), call_tool, "browser_navigate", {"url": "https://example.com"}
        )

        assert result == {"success": True}
        assert tracker.browser_opened
        call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_hook_chains_to_existing(self):
        """Test that hook chains to existing hook."""
        tracker = PlaywrightCleanupTracker()

        existing_hook = AsyncMock(return_value={"intercepted": True})
        call_tool = AsyncMock(return_value={"default": True})

        hook = tracker.create_hook(existing_hook=existing_hook)
        result = await hook(
            MagicMock(), call_tool, "browser_navigate", {"url": "https://example.com"}
        )

        assert result == {"intercepted": True}
        assert tracker.browser_opened
        existing_hook.assert_called_once()
        call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_browser(self):
        """Test browser cleanup."""
        tracker = PlaywrightCleanupTracker()
        tracker.track_tool_call("browser_navigate", {})

        # Without mcp_call
        result = await tracker.cleanup_browser()
        assert not result
        assert tracker.needs_browser_cleanup  # Still needs cleanup

        # With mcp_call
        mcp_call = AsyncMock()
        result = await tracker.cleanup_browser(mcp_call=mcp_call)

        assert result
        assert tracker.browser_closed
        mcp_call.assert_called_once_with(BROWSER_CLOSE_TOOL, {})

    def test_cleanup_screenshot_files(self):
        """Test screenshot file cleanup."""
        tracker = PlaywrightCleanupTracker()

        # Create temp files
        with tempfile.NamedTemporaryFile(
            prefix="screenshot_",
            suffix=".png",
            delete=False,
        ) as f:
            temp_path = f.name

        tracker.screenshot_files.append(temp_path)
        assert os.path.exists(temp_path)

        # Cleanup
        deleted = tracker.cleanup_screenshot_files()

        assert deleted >= 1
        assert not os.path.exists(temp_path)
        assert tracker.screenshot_files == []

    @pytest.mark.asyncio
    async def test_full_cleanup(self):
        """Test full cleanup process."""
        tracker = PlaywrightCleanupTracker()
        tracker.track_tool_call("browser_navigate", {})

        with tempfile.NamedTemporaryFile(
            prefix="screenshot_",
            suffix=".png",
            delete=False,
        ) as f:
            temp_path = f.name
        tracker.screenshot_files.append(temp_path)

        mcp_call = AsyncMock()
        results = await tracker.cleanup(mcp_call=mcp_call)

        assert results["browser_closed"]
        assert results["files_deleted"] >= 1
        assert not results.get("skipped")

    @pytest.mark.asyncio
    async def test_cleanup_skips_if_already_done(self):
        """Test that cleanup is skipped if already performed."""
        tracker = PlaywrightCleanupTracker()
        tracker.track_tool_call("browser_navigate", {})

        mcp_call = AsyncMock()
        await tracker.cleanup(mcp_call=mcp_call)

        # Second cleanup should be skipped
        results = await tracker.cleanup(mcp_call=mcp_call)
        assert results.get("skipped")

    def test_reset(self):
        """Test tracker reset."""
        tracker = PlaywrightCleanupTracker()
        tracker.track_tool_call("browser_navigate", {})
        tracker.screenshot_files.append("/tmp/test.png")

        tracker.reset()

        assert not tracker.browser_opened
        assert not tracker.browser_closed
        assert tracker.screenshot_files == []


class TestGlobalTracker:
    """Tests for global tracker functions."""

    def test_get_global_tracker(self):
        """Test getting global tracker."""
        reset_global_tracker()
        tracker = get_global_tracker()
        assert isinstance(tracker, PlaywrightCleanupTracker)

        # Same instance returned
        tracker2 = get_global_tracker()
        assert tracker is tracker2

    def test_reset_global_tracker(self):
        """Test resetting global tracker."""
        tracker = get_global_tracker()
        tracker.track_tool_call("browser_navigate", {})
        assert tracker.browser_opened

        reset_global_tracker()

        # Get fresh tracker
        tracker = get_global_tracker()
        assert not tracker.browser_opened

    @pytest.mark.asyncio
    async def test_cleanup_playwright_session(self):
        """Test convenience cleanup function."""
        reset_global_tracker()
        tracker = get_global_tracker()
        tracker.track_tool_call("browser_navigate", {})

        mcp_call = AsyncMock()
        results = await cleanup_playwright_session(mcp_call=mcp_call)

        assert results["browser_closed"]
