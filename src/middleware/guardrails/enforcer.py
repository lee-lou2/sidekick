# src/middleware/guardrails/enforcer.py
"""Guardrail enforcer for all tool types.

This module provides a GuardrailEnforcer class that applies security guardrails
to all tool types (custom tools, command tools, scheduler tools), not just MCP tools.

Example:
    >>> from src.middleware.guardrails.enforcer import GuardrailEnforcer
    >>> from src.middleware.guardrails import GuardrailConfig
    >>>
    >>> config = GuardrailConfig(blocked_tools={'dangerous_tool'})
    >>> enforcer = GuardrailEnforcer(config)
    >>>
    >>> # Check a tool call
    >>> enforcer.check('safe_tool', (), {'path': 'file.txt'})  # OK
    >>> enforcer.check('dangerous_tool', (), {})  # Raises GuardrailViolation
    >>>
    >>> # Wrap a tool function
    >>> @enforcer.wrap_tool
    >>> def my_tool(path: str) -> str:
    ...     return f"Processing {path}"
"""

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from src.middleware.guardrails.core import (
    GuardrailConfig,
    check_guardrails,
)

F = TypeVar("F", bound=Callable[..., Any])


class GuardrailEnforcer:
    """Enforces guardrails for all tool types.

    Defense in Depth: Applies same security checks to custom tools,
    command tools, and scheduler tools - not just MCP tools.

    Attributes:
        config: GuardrailConfig instance with security settings.
    """

    def __init__(self, config: GuardrailConfig | None = None):
        """Initialize the enforcer.

        Args:
            config: GuardrailConfig instance. Defaults to default config
                   (read_only=True, block_sensitive_files=True).
        """
        self.config = config or GuardrailConfig()

    def check(self, tool_name: str, args: tuple, kwargs: dict) -> None:
        """Check if tool call is allowed.

        Args:
            tool_name: Name of the tool being called.
            args: Positional arguments to the tool.
            kwargs: Keyword arguments to the tool.

        Raises:
            GuardrailViolation: If tool call violates guardrails.
        """
        check_guardrails(tool_name, args, kwargs, self.config)

    def wrap_tool(self, func: F) -> F:
        """Wrap a tool function with guardrail checks.

        The wrapper inspects the function name and arguments before
        calling the actual function. If any guardrail is violated,
        a GuardrailViolation is raised.

        Args:
            func: The tool function to wrap.

        Returns:
            Wrapped function with guardrail checks.

        Example:
            >>> enforcer = GuardrailEnforcer()
            >>> @enforcer.wrap_tool
            >>> def read_data(path: str) -> str:
            ...     with open(path) as f:
            ...         return f.read()
        """
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                self.check(func.__name__, args, kwargs)
                return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                self.check(func.__name__, args, kwargs)
                return func(*args, **kwargs)

            return sync_wrapper  # type: ignore[return-value]

    def wrap_tool_with_name(self, tool_name: str) -> Callable[[F], F]:
        """Wrap a tool function with guardrail checks using a custom name.

        Use this when the function name doesn't match the tool name
        (e.g., prefixed or aliased tools).

        Args:
            tool_name: The tool name to use for guardrail checks.

        Returns:
            Decorator that wraps function with guardrail checks.

        Example:
            >>> enforcer = GuardrailEnforcer()
            >>> @enforcer.wrap_tool_with_name("write_file")
            >>> def custom_write(path: str, content: str) -> None:
            ...     with open(path, 'w') as f:
            ...         f.write(content)
        """

        def decorator(func: F) -> F:
            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    self.check(tool_name, args, kwargs)
                    return await func(*args, **kwargs)

                return async_wrapper  # type: ignore[return-value]
            else:

                @functools.wraps(func)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    self.check(tool_name, args, kwargs)
                    return func(*args, **kwargs)

                return sync_wrapper  # type: ignore[return-value]

        return decorator
