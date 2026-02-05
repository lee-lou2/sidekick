# src/tools/__init__.py
"""Tools package for the personal AI agent.

Pydantic AI 도구는 이 디렉토리에서 관리됩니다.
FunctionToolset을 사용해 함수를 자동으로 도구로 등록합니다.
자세한 가이드는 AGENTS.md를 참고하세요.

Structure:
- tools/custom/: User-implemented tools (auto-registered via @register_tool)
- tools/mcp/: MCP server definitions (auto-registered via register_mcp_server)
- tools/registry.py: Auto-registration logic and @register_tool decorator
- tools/mcp_registry.py: MCP server registration and auto-discovery
- tools/mcp_client.py: MCPManager for connecting to MCP servers

Note:
- This package only provides CUSTOM tools from tools/custom/
- Command and scheduler tools are registered directly by the agent
  (src/core/agent/core.py) to avoid reverse dependencies
"""

from typing import Any

from pydantic_ai import FunctionToolset

from src.tools.registry import auto_register_tools

# Create the global toolset instance for custom tools
_custom_toolset: FunctionToolset | None = None


def _register_custom_tools(toolset: FunctionToolset) -> None:
    """Register all custom tool functions to the toolset.

    Only registers tools from src/tools/custom/ that are decorated
    with @register_tool.
    """
    auto_register_tools(toolset, "src.tools.custom")


def get_custom_toolset() -> FunctionToolset:
    """Get the toolset with custom tools only.

    Custom tools are functions in src/tools/custom/ decorated with @register_tool.
    Command and scheduler tools are NOT included here - they are registered
    directly by the agent (src/core/agent/core.py).

    Returns:
        FunctionToolset instance with custom tools registered.
    """
    global _custom_toolset
    if _custom_toolset is None:
        _custom_toolset = FunctionToolset()
        _register_custom_tools(_custom_toolset)
    return _custom_toolset


def get_custom_tools() -> list[Any]:
    """Return all custom tools.

    Note: This only returns custom tools, not command/scheduler tools.
    For ALL tools (custom + command + scheduler), use get_all_tools()
    from src.tools.catalog instead.

    Returns:
        List of all available custom tool objects.
    """
    ts = get_custom_toolset()
    return list(ts.tools.values())


# Backward compatibility alias
get_toolset = get_custom_toolset

__all__ = ["get_custom_tools", "get_custom_toolset", "get_toolset"]
