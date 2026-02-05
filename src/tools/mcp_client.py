# src/tools/mcp_client.py
"""MCP Client Manager for managing multiple MCP server connections.

Provides a unified interface for connecting to and managing multiple
MCP servers via Pydantic AI's MCPServerStdio.

LIFECYCLE NOTE: This class creates MCPServerStdio instances but does NOT
manage their async lifecycle. Pydantic AI's Agent manages __aenter__/__aexit__
automatically when servers are passed via `toolsets=`.

Guardrails are enabled by default to:
1. Block access to sensitive files (.env, credentials, secrets, AWS keys, etc.)
2. Block write/modify/delete operations - only allow read operations

Server-specific cleanup hooks (e.g., browser cleanup, temp file cleanup) are
automatically discovered from the MCP server registry - no hard imports needed.

Example:
    >>> from src.tools.mcp_client import MCPManager
    >>> from pydantic_ai import Agent
    >>>
    >>> manager = MCPManager(enable_guardrails=True)  # Default
    >>> manager.connect_all()  # Creates MCPServerStdio instances
    >>> toolsets = manager.get_toolsets()  # Get toolsets for Agent
    >>>
    >>> agent = Agent('google-gla:gemini-3-flash-preview', toolsets=toolsets)
    >>> result = await agent.run("List files in current directory")
    >>>
    >>> # After agent run, run registered cleanup hooks
    >>> if manager.needs_cleanup():
    >>>     await manager.cleanup_all()
"""

import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai.mcp import MCPServerStdio

from src.middleware.guardrails import GuardrailConfig, create_guardrail_hook
from src.tools.mcp_registry import (
    MCPServerConfig,
    ServerCleanupHooks,
    get_mcp_servers,
    load_from_json,
    merge_configs,
)

logger = logging.getLogger(__name__)


class MCPManager:
    """Manager for multiple MCP server connections with security guardrails.

    Handles creating MCPServerStdio instances for enabled MCP servers.
    Aggregates servers into toolsets that can be passed to Pydantic AI's Agent.
    Server-specific cleanup hooks are discovered from the registry automatically.

    LIFECYCLE: This class does NOT manage async lifecycle. The Agent automatically
    calls __aenter__/__aexit__ on toolsets when running queries.
    """

    def __init__(
        self,
        enable_guardrails: bool = True,
        guardrail_config: GuardrailConfig | None = None,
        config_path: str | None = None,
    ) -> None:
        """Initialize MCPManager.

        Args:
            enable_guardrails: Whether to enable security guardrails.
                Defaults to True for safety.
            guardrail_config: Custom guardrail configuration.
                If None, uses default (read-only + block sensitive files).
            config_path: Optional path to JSON config file.
                If provided, loads servers from JSON and merges with defaults.
        """
        self._servers: list[MCPServerStdio] = []
        self._enable_guardrails = enable_guardrails
        self._guardrail_config = guardrail_config or GuardrailConfig()
        self._config_path = config_path
        self._server_configs = self._load_configs()
        self._cleanup_hooks: dict[str, ServerCleanupHooks] = {}

    def _load_configs(self) -> dict[str, MCPServerConfig]:
        """Load server configs from auto-discovered servers, merged with JSON overrides."""
        base_configs = get_mcp_servers()
        if self._config_path:
            try:
                json_configs = load_from_json(self._config_path)
                return merge_configs(base_configs, json_configs)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning(
                    "Failed to load MCP config from %s: %s", self._config_path, e
                )
        return base_configs

    def _create_server(self, name: str, config: MCPServerConfig) -> MCPServerStdio:
        """Create MCPServerStdio from config.

        CRITICAL: MCPServerStdio does NOT inherit parent env by default.
        Must merge os.environ with config.env for npx/uvx to work.

        Args:
            name: Name of the MCP server (for logging).
            config: Server configuration.

        Returns:
            MCPServerStdio instance ready to be used as a toolset.
        """
        # Create guardrail hook if enabled
        hook: Callable[..., Awaitable[Any]] | None = None
        if self._enable_guardrails:
            hook = create_guardrail_hook(self._guardrail_config)
            logger.debug(
                "Created guardrail hook for server '%s' (read_only=%s)",
                name,
                self._guardrail_config.read_only,
            )

        # Apply cleanup hooks from registry (if server defines them)
        if config.cleanup_hooks and config.cleanup_hooks.create_process_hook:
            hook = config.cleanup_hooks.create_process_hook(existing_hook=hook)
            self._cleanup_hooks[name] = config.cleanup_hooks
            logger.debug("Applied cleanup hooks for server '%s'", name)

        # IMPORTANT: Merge parent environment with config env
        # MCPServerStdio doesn't inherit parent env - npx/uvx need PATH, HOME, etc.
        merged_env = {**os.environ, **(config.env or {})}

        return MCPServerStdio(
            command=config.command,
            args=config.args,
            env=merged_env,
            tool_prefix=config.tool_prefix,
            process_tool_call=hook,
        )

    def connect(self, server_name: str) -> MCPServerStdio:
        """Create MCPServerStdio for a single server.

        Args:
            server_name: Name of the MCP server to connect to.

        Returns:
            MCPServerStdio instance.

        Raises:
            ValueError: If server is not found or not available.
        """
        config = self._server_configs.get(server_name)
        if config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        if not config.is_available():
            missing = [env for env in config.requires_env if not os.environ.get(env)]
            raise ValueError(
                f"MCP server '{server_name}' requires environment variables: {missing}"
            )

        server = self._create_server(server_name, config)
        self._servers.append(server)

        logger.info(
            "Created MCPServerStdio for '%s' (command: %s)",
            server_name,
            config.command,
        )

        return server

    def connect_all(self) -> None:
        """Create MCPServerStdio instances for all enabled servers.

        Note: This does NOT start the servers. Pydantic AI's Agent will
        call __aenter__/__aexit__ on these when running via toolsets=.

        Gracefully handles failures - logs warnings and continues with
        available servers.
        """
        enabled_servers = {
            name: config
            for name, config in self._server_configs.items()
            if config.is_available()
        }

        for server_name, config in enabled_servers.items():
            try:
                self.connect(server_name)
                logger.info("Successfully created server '%s'", server_name)
            except Exception as e:
                logger.warning(
                    "Failed to create MCP server '%s': %s", server_name, str(e)
                )

        logger.info(
            "MCPManager ready with %d servers (guardrails=%s)",
            len(self._servers),
            self._enable_guardrails,
        )

    def get_toolsets(self) -> list[MCPServerStdio]:
        """Return MCP servers as toolsets for Agent.

        Pass these to Agent(toolsets=[...]). Agent manages lifecycle.

        Returns:
            List of MCPServerStdio instances.
        """
        return self._servers

    def disconnect_all(self) -> None:
        """Clear server list. Best-effort cleanup.

        In practice, Pydantic AI handles server lifecycle. This is for
        explicit cleanup in edge cases.
        """
        self._servers.clear()
        logger.debug("Cleared all MCP server instances")

    def get_server_count(self) -> int:
        """Get number of configured servers.

        Returns:
            Number of MCPServerStdio instances.
        """
        return len(self._servers)

    # --- Cleanup Methods (registry-based, server-agnostic) ---

    def needs_cleanup(self) -> bool:
        """Check if any server cleanup is needed."""
        for hooks in self._cleanup_hooks.values():
            if hooks.needs_cleanup and hooks.needs_cleanup():
                return True
        return False

    async def cleanup_all(
        self,
        mcp_call: Callable[[str, dict], Awaitable[Any]] | None = None,
    ) -> dict[str, Any]:
        """Run async cleanup for all servers that registered cleanup hooks."""
        results: dict[str, Any] = {}
        for name, hooks in self._cleanup_hooks.items():
            if hooks.cleanup_async and hooks.needs_cleanup and hooks.needs_cleanup():
                try:
                    result = await hooks.cleanup_async(mcp_call=mcp_call)
                    results[name] = result
                    logger.info("Cleanup completed for server '%s': %s", name, result)
                except Exception as e:
                    logger.warning("Cleanup failed for server '%s': %s", name, e)
                    results[name] = {"error": str(e)}
        return results

    def cleanup_files_sync(self) -> int:
        """Synchronous file cleanup for all servers."""
        total_deleted = 0
        for name, hooks in self._cleanup_hooks.items():
            if hooks.cleanup_sync and hooks.needs_cleanup and hooks.needs_cleanup():
                try:
                    deleted = hooks.cleanup_sync()
                    total_deleted += deleted
                except Exception as e:
                    logger.warning("Sync cleanup failed for '%s': %s", name, e)
        return total_deleted

    def reset_cleanup_trackers(self) -> None:
        """Reset all cleanup trackers for reuse."""
        for hooks in self._cleanup_hooks.values():
            if hooks.reset:
                hooks.reset()

    # --- Backward compatibility aliases ---

    def needs_playwright_cleanup(self) -> bool:
        """Backward compat: check if any cleanup is needed."""
        return self.needs_cleanup()

    async def cleanup_playwright(
        self,
        mcp_call: Callable[[str, dict], Awaitable[Any]] | None = None,
    ) -> dict[str, Any]:
        """Backward compat: run all async cleanup."""
        all_results = await self.cleanup_all(mcp_call)
        if "playwright" in all_results:
            return all_results["playwright"]
        return {"browser_closed": False, "files_deleted": 0, "skipped": True}

    def cleanup_playwright_files_sync(self) -> int:
        """Backward compat: sync file cleanup."""
        return self.cleanup_files_sync()

    def get_playwright_tracker(self) -> Any:
        """Backward compat: return None (use cleanup_hooks registry instead)."""
        return None
