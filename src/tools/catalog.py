# src/tools/catalog.py
"""Unified tool catalog for the personal AI agent.

Provides a single entry point for getting all tools combined:
- Custom tools from @register_tool decorator (src/tools/custom/)
- Command management tools (src/core/commands/tools.py)
- Scheduler tools (src/core/scheduler/tools.py)

Usage:
    from src.tools.catalog import get_all_tools
    toolset = get_all_tools()
"""

from pydantic_ai import FunctionToolset

from src.core.commands.tools import get_command_tools
from src.core.scheduler.tools import get_scheduler_tools
from src.tools import get_custom_toolset


def get_all_tools() -> FunctionToolset:
    """Get unified toolset combining all tool sources.

    Combines tools from:
    - Custom tools from @register_tool decorator (src/tools/custom/)
    - Command management tools (create, list, update, delete commands)
    - Scheduler tools (schedule, list, cancel tasks)

    Returns:
        A new FunctionToolset with all tools registered.
    """
    toolset = FunctionToolset()

    custom = get_custom_toolset()
    for tool in custom.tools.values():
        toolset.add_tool(tool)

    for func in get_command_tools():
        toolset.add_function(func)

    for func in get_scheduler_tools():
        toolset.add_function(func)

    return toolset
