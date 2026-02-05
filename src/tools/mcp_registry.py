# src/tools/mcp_registry.py
"""MCP server configuration and auto-registration.

Defines MCPServerConfig dataclass and the auto-registration system.
Each MCP server is defined in its own file under src/tools/mcp/
and registered via register_mcp_server() at module level.

Mirrors the @register_tool pattern from src/tools/registry.py:
- src/tools/registry.py    → custom tools in src/tools/custom/
- src/tools/mcp_registry.py → MCP servers in src/tools/mcp/

Usage:
    # In src/tools/mcp/github.py
    from src.tools.mcp_registry import register_mcp_server

    register_mcp_server(
        key="github",
        name="GitHub",
        description="GitHub API integration",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", "")},
        requires_env=["GITHUB_TOKEN"],
        tool_prefix="gh",
    )
"""

import importlib
import json
import logging
import os
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import StdioServerParameters

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def get_base_tool_name(tool_name: str) -> str:
    """Extract base tool name from potentially prefixed name.

    MCP servers may use a tool_prefix (e.g., 'gh_', 'mem_') to avoid naming
    conflicts. This function strips the prefix to get the base tool name.

    Args:
        tool_name: Tool name, possibly prefixed (e.g., 'gh_create_issue').

    Returns:
        Base tool name without prefix (e.g., 'create_issue').
    """
    if "_" not in tool_name:
        return tool_name
    parts = tool_name.split("_", 1)
    if len(parts) == 2 and len(parts[0]) <= 10:
        return parts[1]
    return tool_name


# ---------------------------------------------------------------------------
# Server guardrail rules
# ---------------------------------------------------------------------------


@dataclass
class ServerGuardrailRules:
    """Server-specific guardrail rules registered alongside server config.

    Each MCP server defines its own write/read tools and sensitive patterns.
    The generic guardrail framework aggregates these from all registered servers.

    Attributes:
        write_tools: Tool names that perform write/modify/delete operations.
        read_only_tools: Tool names that are always safe (read-only).
        sensitive_file_patterns: File patterns that should never be accessible.
        sensitive_path_patterns: Path patterns that should never be accessible.
        safe_file_patterns: Patterns that override sensitive blocks.
        custom_check: Optional custom guardrail check function.
            Signature: (tool_name, args, kwargs, config) -> None.
            Raises GuardrailViolation if blocked.
    """

    write_tools: set[str] = field(default_factory=set)
    read_only_tools: set[str] = field(default_factory=set)
    sensitive_file_patterns: set[str] = field(default_factory=set)
    sensitive_path_patterns: set[str] = field(default_factory=set)
    safe_file_patterns: set[str] = field(default_factory=set)
    custom_check: Callable[[str, tuple, dict[str, Any], Any], None] | None = None


@dataclass
class ServerCleanupHooks:
    """Optional cleanup hooks that MCP servers can register.

    These hooks are called by MCPManager after agent runs complete.
    Servers register hooks via register_mcp_server() and MCPManager
    discovers them from the registry—no hard imports needed.

    Attributes:
        create_process_hook: Factory function that creates a process_tool_call hook.
            The hook can wrap an existing hook (for chaining with guardrails).
            Signature: (existing_hook) -> new_hook
        needs_cleanup: Check whether cleanup is needed after agent run.
            Signature: () -> bool
        cleanup_async: Async cleanup function.
            Signature: (mcp_call) -> dict[str, Any]
        cleanup_sync: Sync cleanup (file-level only, for context managers).
            Signature: () -> int (number of files cleaned up)
        reset: Reset state for reuse in new session.
            Signature: () -> None
    """

    create_process_hook: Callable[..., Callable[..., Any]] | None = None
    needs_cleanup: Callable[[], bool] | None = None
    cleanup_async: Callable[..., Any] | None = None
    cleanup_sync: Callable[[], int] | None = None
    reset: Callable[[], None] | None = None


# ---------------------------------------------------------------------------
# MCPServerConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server.

    Attributes:
        name: Human-readable name of the server.
        description: Brief description of server capabilities.
        command: Command to run the MCP server.
        args: Arguments to pass to the command.
        env: Environment variables for the server.
        enabled: Whether this server is enabled.
        requires_env: List of required environment variables.
        tool_prefix: Optional prefix added to all tool names from this server.
            Use to avoid naming conflicts between servers (e.g., 'github_', 'sentry_').
        guardrail_rules: Optional server-specific guardrail rules.
    """

    name: str
    description: str
    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    requires_env: list[str] = field(default_factory=list)
    tool_prefix: str | None = None
    guardrail_rules: ServerGuardrailRules | None = None
    cleanup_hooks: ServerCleanupHooks | None = None

    def to_server_parameters(self) -> StdioServerParameters:
        """Convert to StdioServerParameters for MCPClient.

        Returns:
            StdioServerParameters instance ready for use with MCPClient.
        """
        merged_env = {**os.environ, **self.env}
        return StdioServerParameters(
            command=self.command,
            args=self.args,
            env=merged_env,
        )

    def is_available(self) -> bool:
        """Check if all required environment variables are set.

        Returns:
            True if all required env vars are available, False otherwise.
        """
        if not self.enabled:
            return False
        for env_var in self.requires_env:
            if not os.environ.get(env_var):
                return False
        return True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Global registry populated by register_mcp_server() calls
_registered_servers: dict[str, MCPServerConfig] = {}


def register_mcp_server(
    key: str,
    name: str,
    description: str,
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
    enabled: bool = True,
    requires_env: list[str] | None = None,
    tool_prefix: str | None = None,
    guardrail_rules: ServerGuardrailRules | None = None,
    cleanup_hooks: ServerCleanupHooks | None = None,
) -> MCPServerConfig:
    """Register an MCP server configuration.

    Call this at module level in a file under src/tools/mcp/.
    The server will be auto-discovered when the package is imported.

    Args:
        key: Server key used for connect("key"). Must be non-empty.
        name: Human-readable display name.
        description: Brief description of server capabilities.
        command: Command to run the server (e.g., "npx", "uvx").
        args: Arguments for the command.
        env: Environment variables for the server process.
        enabled: Whether this server is enabled. Defaults to True.
        requires_env: Required environment variable names.
        tool_prefix: Optional prefix for tool names from this server.
        guardrail_rules: Optional server-specific guardrail rules.

    Returns:
        The created MCPServerConfig instance.

    Raises:
        ValueError: If key is empty.
    """
    if not key or not key.strip():
        raise ValueError("MCP server key must not be empty")

    if key in _registered_servers:
        logger.debug("MCP server '%s' re-registered, updating config", key)

    config = MCPServerConfig(
        name=name,
        description=description,
        command=command,
        args=args,
        env=env or {},
        enabled=enabled,
        requires_env=requires_env or [],
        tool_prefix=tool_prefix,
        guardrail_rules=guardrail_rules,
        cleanup_hooks=cleanup_hooks,
    )
    _registered_servers[key] = config
    logger.debug("Registered MCP server: %s (%s)", key, name)
    return config


def get_registered_servers() -> dict[str, MCPServerConfig]:
    """Get a copy of all registered server configurations.

    Returns:
        Dictionary of server key to MCPServerConfig.
    """
    return _registered_servers.copy()


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------

# Singleton cache
_mcp_servers_cache: dict[str, MCPServerConfig] | None = None


def auto_discover_mcp_servers(
    package_path: str = "src.tools.mcp",
) -> dict[str, MCPServerConfig]:
    """Auto-discover and import MCP server modules, then return registered configs.

    Imports all Python modules in the given package. Each module is expected
    to call register_mcp_server() at module level during import.

    If a module was already imported (cached in sys.modules), it is reloaded
    to ensure register_mcp_server() is re-executed. This handles the case
    where _registered_servers was cleared (e.g., by tests).

    Args:
        package_path: Python package path to scan. Defaults to "src.tools.mcp".

    Returns:
        Dictionary of server key to MCPServerConfig.
    """
    try:
        package = importlib.import_module(package_path)
    except ImportError as e:
        logger.warning("Failed to import MCP servers package %s: %s", package_path, e)
        return _registered_servers.copy()

    if not hasattr(package, "__path__"):
        logger.warning("Package %s has no __path__ attribute", package_path)
        return _registered_servers.copy()

    for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            continue

        module_name = f"{package_path}.{name}"
        try:
            importlib.import_module(module_name)
            logger.debug("Loaded MCP server module: %s", name)
        except Exception as e:
            logger.warning(
                "Failed to import MCP server module %s: %s",
                module_name,
                e,
            )

    discovered = _registered_servers.copy()
    if discovered:
        logger.info(
            "Auto-discovered %d MCP servers: %s",
            len(discovered),
            list(discovered.keys()),
        )
    else:
        logger.debug("No MCP servers found in %s", package_path)

    return discovered


def get_mcp_servers() -> dict[str, MCPServerConfig]:
    """Get all registered MCP server configurations.

    Auto-discovers servers from src/tools/mcp/ on first call,
    then caches the result.

    Returns:
        Dictionary of server key to MCPServerConfig.
    """
    global _mcp_servers_cache
    if _mcp_servers_cache is None:
        _mcp_servers_cache = auto_discover_mcp_servers()
    return _mcp_servers_cache


def reset_mcp_servers_cache() -> None:
    """Reset the server cache. Useful for testing."""
    global _mcp_servers_cache
    _mcp_servers_cache = None


def get_all_guardrail_rules() -> list[ServerGuardrailRules]:
    """Get guardrail rules from all registered MCP servers.

    Ensures servers are discovered first by calling get_mcp_servers().
    Returns guardrail rules from all servers that define them.

    Returns:
        List of ServerGuardrailRules from registered servers.
    """
    servers = get_mcp_servers()
    return [c.guardrail_rules for c in servers.values() if c.guardrail_rules]


# ---------------------------------------------------------------------------
# JSON config loading (for external config files)
# ---------------------------------------------------------------------------


def _expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} and $VAR syntax.

    Args:
        value: String potentially containing env vars.

    Returns:
        String with env vars expanded.
    """
    return os.path.expandvars(value)


def load_from_json(config_path: str) -> dict[str, MCPServerConfig]:
    """Load MCP server configurations from a JSON file.

    Follows the standard Claude/Cline MCP config format:
    {
      "mcpServers": {
        "server-name": {
          "command": "npx",
          "args": ["-y", "@pkg/server"],
          "env": {"KEY": "${HOME}/value"}
        }
      }
    }

    Environment variables in args and env values are expanded.

    Args:
        config_path: Path to the JSON config file.

    Returns:
        Dictionary of server name to MCPServerConfig.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        json.JSONDecodeError: If config file is invalid JSON.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"MCP config file not found: {config_path}")

    with open(path) as f:
        data = json.load(f)

    servers_data = data.get("mcpServers", data)

    configs: dict[str, MCPServerConfig] = {}

    for name, server_data in servers_data.items():
        if not isinstance(server_data, dict):
            continue

        args = server_data.get("args", [])
        expanded_args = [_expand_env_vars(arg) for arg in args]

        env = server_data.get("env", {})
        expanded_env = {k: _expand_env_vars(v) for k, v in env.items()}

        requires_env = list(env.keys()) if env else []

        config = MCPServerConfig(
            name=name.replace("-", " ").title(),
            description=server_data.get("description", f"MCP server: {name}"),
            command=server_data.get("command", "npx"),
            args=expanded_args,
            env=expanded_env,
            enabled=server_data.get("enabled", True),
            requires_env=requires_env,
        )
        configs[name] = config

    return configs


def merge_configs(
    base: dict[str, MCPServerConfig], override: dict[str, MCPServerConfig]
) -> dict[str, MCPServerConfig]:
    """Merge two config dictionaries, with override taking precedence.

    Args:
        base: Base configurations.
        override: Override configurations (takes precedence).

    Returns:
        Merged configuration dictionary.
    """
    return {**base, **override}
