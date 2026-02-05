# src/tools/registry.py
"""Auto-registration logic for tool functions.

This module provides utilities for automatically discovering and registering
tool functions from the tools/custom/ package using the @register_tool decorator.

Usage:
    from src.tools.registry import register_tool

    @register_tool
    def my_tool(param: str) -> str:
        '''My tool description.'''
        return f"Result: {param}"

Tool Function Requirements:
1. Must be decorated with @register_tool
2. Must be a callable (function)
3. Must have a docstring
4. Must have type annotations
"""

import importlib
import inspect
import logging
import pkgutil
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic_ai import FunctionToolset

logger = logging.getLogger(__name__)

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])

# Set of registered tool function names (populated by @register_tool decorator)
_registered_tools: set[str] = set()

# Modules to exclude from auto-registration (currently none)
EXCLUDED_MODULES: set[str] = set()


def register_tool(func: F) -> F:
    """Decorator to register a function as a tool.

    Simply add @register_tool above your function definition to auto-register it.
    No need to modify any whitelist or __init__.py file.

    Args:
        func: The function to register as a tool.

    Returns:
        The original function unchanged.

    Example:
        @register_tool
        def my_tool(query: str) -> str:
            '''Search for something.'''
            return f"Found: {query}"
    """
    _registered_tools.add(func.__name__)
    logger.debug("Registered tool via decorator: %s", func.__name__)
    return func


def get_registered_tools() -> set[str]:
    """Get the set of registered tool names.

    Returns:
        Set of tool function names registered via @register_tool.
    """
    return _registered_tools.copy()


def is_tool_function(obj: Any, name: str) -> bool:
    """Check if object is a valid tool function.

    Uses the decorator-based registration - only functions registered with
    @register_tool are considered valid tools.

    Args:
        obj: Object to check.
        name: Name of the object.

    Returns:
        True if object is a valid tool function.
    """
    # Must be registered via @register_tool decorator
    if name not in _registered_tools:
        return False

    # Must be callable
    if not callable(obj):
        return False

    # Must not be a class
    if inspect.isclass(obj):
        return False

    # Must have a docstring
    if not obj.__doc__:
        return False

    # Must have type annotations
    if not hasattr(obj, "__annotations__") or not obj.__annotations__:
        return False

    # Must be a function (not a method or builtin)
    if not inspect.isfunction(obj):
        return False

    return True


def auto_register_tools(toolset: FunctionToolset, package_path: str) -> int:
    """Auto-register all valid tool functions from a package.

    Args:
        toolset: FunctionToolset to register tools to.
        package_path: Python package path (e.g., "src.tools.custom").

    Returns:
        Number of tools successfully registered.
    """
    count = 0
    registered_names: list[str] = []

    try:
        package = importlib.import_module(package_path)
    except ImportError as e:
        logger.warning("Failed to import package %s: %s", package_path, e)
        return 0

    # Get package path for module iteration
    if not hasattr(package, "__path__"):
        logger.warning("Package %s has no __path__ attribute", package_path)
        return 0

    for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
        # Skip packages and excluded modules
        if is_pkg or name in EXCLUDED_MODULES:
            logger.debug(
                "Skipping module: %s (excluded=%s)", name, name in EXCLUDED_MODULES
            )
            continue

        try:
            module = importlib.import_module(f"{package_path}.{name}")
        except ImportError as e:
            logger.warning("Failed to import module %s.%s: %s", package_path, name, e)
            continue

        # Find and register tool functions in this module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            if is_tool_function(attr, attr_name):
                try:
                    toolset.add_function(attr)
                    count += 1
                    registered_names.append(attr_name)
                    logger.debug("Registered tool: %s from %s", attr_name, name)
                except Exception as e:
                    logger.warning(
                        "Failed to register tool %s from %s: %s",
                        attr_name,
                        name,
                        e,
                    )

    logger.info(
        "Auto-registered %d tools from %s: %s",
        count,
        package_path,
        registered_names,
    )
    return count
