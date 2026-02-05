# src/middleware/guardrails/__init__.py
"""Generic guardrail framework for MCP tools.

Server-specific rules (write tools, sensitive patterns, custom checks) are
defined in each MCP server file under src/tools/mcp/ and aggregated here.

Example:
    Using create_guardrail_hook with MCPServerStdio:

    >>> from src.middleware.guardrails import create_guardrail_hook, GuardrailConfig
    >>> from pydantic_ai.mcp import MCPServerStdio
    >>>
    >>> hook = create_guardrail_hook(GuardrailConfig(read_only=True))
    >>> server = MCPServerStdio("npx", ["-y", "@mcp/server-fs"],
    ...                          process_tool_call=hook)

    Handling guardrail violations:

    >>> from src.middleware.guardrails import GuardrailViolation
    >>> try:
    ...     result = await call_tool(name, args, None)
    ... except GuardrailViolation as e:
    ...     print(f"Blocked: {e.violation_type} - {e}")
"""

from src.middleware.guardrails.core import (
    GuardrailConfig,
    GuardrailViolation,
    check_guardrails,
    create_default_guardrails,
    create_guardrail_hook,
    extract_paths_from_args,
    is_in_safe_zone,
    is_sensitive_file,
)
from src.middleware.guardrails.enforcer import GuardrailEnforcer

__all__ = [
    "GuardrailConfig",
    "GuardrailEnforcer",
    "GuardrailViolation",
    "check_guardrails",
    "create_default_guardrails",
    "create_guardrail_hook",
    "extract_paths_from_args",
    "is_in_safe_zone",
    "is_sensitive_file",
]
