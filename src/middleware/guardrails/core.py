# src/middleware/guardrails/core.py
"""Generic guardrail framework for MCP tools.

This module provides the generic security guardrail framework. Server-specific
rules (write tools, sensitive patterns, custom checks) are defined in each
MCP server file under src/tools/mcp/ and aggregated via the registry.

The framework provides:
1. GuardrailConfig - configuration for guardrail behavior
2. GuardrailViolation - exception for blocked operations
3. check_guardrails() - main check function that aggregates server rules
4. create_guardrail_hook() - creates process_tool_call hooks for MCPServerStdio

Example:
    >>> from pydantic_ai.mcp import MCPServerStdio
    >>> from src.middleware.guardrails import create_guardrail_hook, GuardrailConfig
    >>> hook = create_guardrail_hook(GuardrailConfig(read_only=True))
    >>> server = MCPServerStdio("npx", ["-y", "..."], process_tool_call=hook)
"""

import fnmatch
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc, ToolResult

logger = logging.getLogger(__name__)


# ============================================================================
# Guardrail Configuration
# ============================================================================


@dataclass
class GuardrailConfig:
    """Configuration for tool guardrails.

    Server-specific rules (write tools, sensitive patterns) are aggregated
    from registered MCP servers via ServerGuardrailRules.

    Attributes:
        read_only: If True, block all write/modify/delete operations.
        block_sensitive_files: If True, block access to sensitive files.
        sensitive_patterns: Additional patterns to block (merged with server defaults).
        safe_patterns: Patterns that override blocks (merged with server defaults).
        blocked_tools: Additional tool names to block.
        allowed_tools: If set, ONLY these tools are allowed (whitelist mode).
        log_blocked_attempts: If True, log all blocked attempts.
        current_user_id: Current user ID for memory isolation.
        safe_zone_paths: Paths where write operations are allowed.
    """

    read_only: bool = True
    block_sensitive_files: bool = True
    sensitive_patterns: set[str] = field(default_factory=set)
    safe_patterns: set[str] = field(default_factory=set)
    blocked_tools: set[str] = field(default_factory=set)
    allowed_tools: set[str] | None = None
    log_blocked_attempts: bool = True
    current_user_id: str | None = None
    safe_zone_paths: set[str] = field(default_factory=lambda: {"data/"})

    def get_all_sensitive_patterns(self) -> set[str]:
        """Get all sensitive file patterns including custom and server-registered ones."""
        from src.tools.mcp_registry import get_all_guardrail_rules

        patterns = set(self.sensitive_patterns)
        for rules in get_all_guardrail_rules():
            patterns |= rules.sensitive_file_patterns
        return patterns

    def get_all_sensitive_path_patterns(self) -> set[str]:
        """Get all sensitive path patterns from server-registered rules."""
        from src.tools.mcp_registry import get_all_guardrail_rules

        patterns: set[str] = set()
        for rules in get_all_guardrail_rules():
            patterns |= rules.sensitive_path_patterns
        return patterns

    def get_all_safe_patterns(self) -> set[str]:
        """Get all safe file patterns including custom and server-registered ones."""
        from src.tools.mcp_registry import get_all_guardrail_rules

        patterns = set(self.safe_patterns)
        for rules in get_all_guardrail_rules():
            patterns |= rules.safe_file_patterns
        return patterns

    def get_all_blocked_tools(self) -> set[str]:
        """Get all blocked tool names."""
        from src.tools.mcp_registry import get_all_guardrail_rules

        blocked = self.blocked_tools.copy()
        if self.read_only:
            for rules in get_all_guardrail_rules():
                blocked |= rules.write_tools
        return blocked

    def get_allowed_memory_entity(self) -> str | None:
        """Get the allowed memory entity name for current user."""
        if self.current_user_id:
            return f"user_{self.current_user_id}"
        return None


# ============================================================================
# Security Checks
# ============================================================================


class GuardrailViolation(Exception):
    """Raised when a guardrail is violated."""

    def __init__(self, message: str, tool_name: str, violation_type: str):
        super().__init__(message)
        self.tool_name = tool_name
        self.violation_type = violation_type


def is_sensitive_file(path: str, config: GuardrailConfig) -> bool:
    """Check if a file path matches sensitive file patterns.

    Safe patterns are checked first - they override sensitive patterns.
    This allows specific files (e.g., data/commands.db) to be explicitly
    allowed even if they match a broad sensitive pattern (e.g., *.db).

    Aggregates patterns from all registered MCP servers and config.

    Args:
        path: File path to check.
        config: Guardrail configuration.

    Returns:
        True if the file is considered sensitive.
    """
    if not path:
        return False

    path_lower = path.lower().replace("\\", "/")
    filename = path_lower.split("/")[-1]

    # Check safe patterns first - they override sensitive patterns
    for pattern in config.get_all_safe_patterns():
        if fnmatch.fnmatch(filename, pattern.lower()):
            return False
        if fnmatch.fnmatch(path_lower, pattern.lower()):
            return False

    # Check sensitive file patterns
    for pattern in config.get_all_sensitive_patterns():
        pattern_lower = pattern.lower()
        if fnmatch.fnmatch(filename, pattern_lower):
            return True
        if fnmatch.fnmatch(path_lower, pattern_lower):
            return True
        if "*" not in pattern and pattern_lower in path_lower:
            return True

    # Check sensitive path patterns
    for pattern in config.get_all_sensitive_path_patterns():
        if fnmatch.fnmatch(path_lower, pattern.lower()):
            return True

    return False


def is_in_safe_zone(path: str, config: GuardrailConfig) -> bool:
    """Check if a file path is within a safe zone.

    Safe zones allow write operations even in read-only mode.
    This enables the agent to save files in designated folders like data/.

    Args:
        path: File path to check.
        config: Guardrail configuration.

    Returns:
        True if the path is in a safe zone.
    """
    if not path or not config.safe_zone_paths:
        return False

    path_lower = path.lower().replace("\\", "/")

    for zone in config.safe_zone_paths:
        zone_lower = zone.lower().replace("\\", "/").rstrip("/") + "/"
        # Direct match: data/file.txt starts with data/
        if path_lower.startswith(zone_lower) or path_lower == zone_lower.rstrip("/"):
            return True
        # Absolute path: /path/to/project/data/file.txt contains /data/
        if f"/{zone_lower}" in f"/{path_lower}/":
            return True

    return False


def extract_paths_from_args(args: tuple, kwargs: dict, tool_name: str) -> list[str]:
    """Extract file paths from tool arguments.

    Args:
        args: Positional arguments.
        kwargs: Keyword arguments.
        tool_name: Name of the tool being called.

    Returns:
        List of file paths found in arguments.
    """
    paths = []

    # Common parameter names for file paths
    path_params = {
        "path",
        "file",
        "filepath",
        "file_path",
        "filename",
        "source",
        "destination",
        "src",
        "dst",
        "paths",
    }

    # Check kwargs
    for key, value in kwargs.items():
        if key.lower() in path_params:
            if isinstance(value, str):
                paths.append(value)
            elif isinstance(value, list):
                paths.extend([v for v in value if isinstance(v, str)])

    # Check positional args (usually the first arg is a path for file tools)
    for arg in args:
        if isinstance(arg, str):
            # Heuristic: if it looks like a path, add it
            if "/" in arg or "\\" in arg or "." in arg:
                paths.append(arg)
        elif isinstance(arg, list):
            for item in arg:
                if isinstance(item, str) and (
                    "/" in item or "\\" in item or "." in item
                ):
                    paths.append(item)

    return paths


def check_guardrails(
    tool_name: str,
    args: tuple,
    kwargs: dict,
    config: GuardrailConfig,
) -> None:
    """Check if a tool call violates any guardrails.

    Aggregates rules from all registered MCP servers and runs custom checks.

    Args:
        tool_name: Name of the tool being called (may be prefixed).
        args: Positional arguments.
        kwargs: Keyword arguments.
        config: Guardrail configuration.

    Raises:
        GuardrailViolation: If any guardrail is violated.
    """
    from src.tools.mcp_registry import get_base_tool_name

    tool_name_lower = tool_name.lower()
    base_name_lower = get_base_tool_name(tool_name_lower)

    # Check allowed tools (whitelist mode) - exact match only, no prefix stripping
    if config.allowed_tools is not None:
        allowed_lower = {t.lower() for t in config.allowed_tools}
        if tool_name_lower not in allowed_lower:
            msg = f"Tool '{tool_name}' is not in the allowed tools list"
            if config.log_blocked_attempts:
                logger.warning("GUARDRAIL BLOCKED: %s", msg)
            raise GuardrailViolation(msg, tool_name, "not_allowed")

    blocked_tools = config.get_all_blocked_tools()
    blocked_lower = {t.lower() for t in blocked_tools}
    if tool_name_lower in blocked_lower or base_name_lower in blocked_lower:
        # Check if write operation is allowed in safe zone
        if config.read_only and config.safe_zone_paths:
            paths = extract_paths_from_args(args, kwargs, tool_name)
            if paths and all(is_in_safe_zone(p, config) for p in paths):
                pass  # Allow - continue to sensitive file check
            else:
                violation_type = "write_operation"
                msg = f"Tool '{tool_name}' is blocked (read-only mode)"
                if config.log_blocked_attempts:
                    logger.warning("GUARDRAIL BLOCKED: %s", msg)
                raise GuardrailViolation(msg, tool_name, violation_type)
        else:
            violation_type = "write_operation" if config.read_only else "blocked_tool"
            msg = (
                f"Tool '{tool_name}' is blocked (read-only mode)"
                if config.read_only
                else f"Tool '{tool_name}' is blocked"
            )
            if config.log_blocked_attempts:
                logger.warning("GUARDRAIL BLOCKED: %s", msg)
            raise GuardrailViolation(msg, tool_name, violation_type)

    # Check sensitive file access
    if config.block_sensitive_files:
        paths = extract_paths_from_args(args, kwargs, tool_name)
        for path in paths:
            if is_sensitive_file(path, config):
                msg = f"Access to sensitive file blocked: {path}"
                if config.log_blocked_attempts:
                    logger.warning("GUARDRAIL BLOCKED: %s (tool: %s)", msg, tool_name)
                raise GuardrailViolation(msg, tool_name, "sensitive_file")

    # Run custom guardrail checks from registered servers
    from src.tools.mcp_registry import get_all_guardrail_rules

    for rules in get_all_guardrail_rules():
        if rules.custom_check:
            rules.custom_check(tool_name, args, kwargs, config)


# ============================================================================
# Process Tool Call Hook
# ============================================================================


ProcessToolCallHook = Callable[
    [RunContext, CallToolFunc, str, dict[str, Any]],
    "Coroutine[Any, Any, ToolResult]",
]


def create_guardrail_hook(
    config: GuardrailConfig | None = None,
) -> ProcessToolCallHook:
    """Create a process_tool_call hook that applies guardrails.

    This function creates an async hook compatible with pydantic-ai's
    MCPServerStdio process_tool_call parameter. The hook intercepts tool
    calls and applies security guardrails before forwarding to the actual tool.

    Args:
        config: Guardrail configuration. Defaults to read-only + block sensitive.

    Returns:
        Async hook function with signature:
        (ctx, call_tool, name, tool_args) -> ToolResult

    Example:
        >>> from pydantic_ai.mcp import MCPServerStdio
        >>> hook = create_guardrail_hook(GuardrailConfig(read_only=True))
        >>> server = MCPServerStdio("npx", ["-y", "@modelcontextprotocol/server-filesystem"],
        ...                          process_tool_call=hook)
    """
    config = config or GuardrailConfig()

    async def guardrail_hook(
        ctx: RunContext,
        call_tool: CallToolFunc,
        name: str,
        tool_args: dict[str, Any],
    ) -> ToolResult:
        try:
            check_guardrails(name, (), tool_args, config)
        except GuardrailViolation as e:
            error_msg = f"[BLOCKED] {e}"
            if e.violation_type == "write_operation":
                error_msg += (
                    f"\n\nHINT: You can only write to safe zones: {config.safe_zone_paths}. "
                    "Use paths like 'data/filename.txt' instead."
                )
            elif e.violation_type == "sensitive_file":
                error_msg += "\n\nHINT: This file contains sensitive data and cannot be accessed."
            return [{"type": "text", "text": error_msg}]
        return await call_tool(name, tool_args, None)

    return guardrail_hook


def create_default_guardrails() -> GuardrailConfig:
    """Create default guardrail configuration.

    Returns:
        GuardrailConfig with recommended security settings.
    """
    return GuardrailConfig(
        read_only=True,
        block_sensitive_files=True,
        log_blocked_attempts=True,
    )
