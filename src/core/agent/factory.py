"""Agent factory for creating isolated Pydantic AI agents."""

import logging
import os

from pydantic_ai import Agent, FunctionToolset

from src.config import settings
from src.core.memory import GUARDRAILS_SYSTEM_PROMPT, MEMORY_SYSTEM_PROMPT
from src.middleware.guardrails import GuardrailConfig
from src.tools.catalog import get_all_tools
from src.tools.mcp_client import MCPManager
from src.utils.observability import setup_logfire

logger = logging.getLogger(__name__)

# Initialize Logfire at module load
setup_logfire()

# Support both env vars during transition
if settings.api_key:
    os.environ["GOOGLE_API_KEY"] = settings.api_key  # Pydantic AI reads this


class AgentFactory:
    """Factory for creating isolated agent instances with shared resources.

    This class solves the concurrency problem by:
    - Sharing expensive resources (tools, MCP connections, model config)
    - Creating a fresh Agent for each request
    - Ensuring each request has isolated conversation state

    Usage:
        factory = AgentFactory(enable_mcp=True)

        # For each request:
        agent = factory.create_agent()
        result = await agent.run(task)
    """

    @staticmethod
    def _create_combined_toolset() -> FunctionToolset:
        """Create a fresh toolset combining custom, command, and scheduler tools.

        Returns:
            A new FunctionToolset with all tools registered.
        """
        return get_all_tools()

    def __init__(
        self,
        api_key: str | None = None,
        enable_mcp: bool = False,
        mcp_servers: list[str] | None = None,
        guardrail_config: GuardrailConfig | None = None,
    ) -> None:
        """Initialize the agent factory with shared resources.

        Args:
            api_key: Google API key. Uses settings.api_key if not provided.
            enable_mcp: Enable MCP server connections.
            mcp_servers: List of MCP server names to connect. Connects all if None.
            guardrail_config: Security guardrail configuration for MCP tools.

        Raises:
            ValueError: If no API key is available.
        """
        _key = api_key or settings.api_key
        if not _key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required. "
                "Set it or pass api_key parameter."
            )
        os.environ["GOOGLE_API_KEY"] = _key

        # Create a fresh toolset by combining:
        # 1. Custom tools from tools/custom/ (via @register_tool decorator)
        # 2. Command tools from core/commands
        # 3. Scheduler tools from core/scheduler
        # This avoids modifying the singleton and prevents duplicate tool errors
        self._toolset = self._create_combined_toolset()

        self._mcp_manager: MCPManager | None = None
        self._mcp_toolsets: list = []

        if enable_mcp:
            self._mcp_manager = MCPManager(guardrail_config=guardrail_config)
            try:
                if mcp_servers is None:
                    self._mcp_manager.connect_all()
                else:
                    for server_name in mcp_servers:
                        self._mcp_manager.connect(server_name)
                self._mcp_toolsets = self._mcp_manager.get_toolsets()
                logger.info(
                    "AgentFactory: MCP enabled with %d servers",
                    self._mcp_manager.get_server_count(),
                )
            except Exception as e:
                logger.warning("AgentFactory: Failed to initialize MCP: %s", str(e))

        logger.info(
            "AgentFactory initialized with FunctionToolset, %d MCP toolsets",
            len(self._mcp_toolsets),
        )

    def create_agent(self) -> Agent:
        """Create a new isolated Agent instance.

        Each call creates a fresh agent with its own conversation memory,
        ensuring concurrent requests don't interfere with each other.

        Returns:
            A new Pydantic AI Agent instance.
        """
        model_name = settings.gemini_model
        all_toolsets = [self._toolset] + self._mcp_toolsets
        combined_prompt = MEMORY_SYSTEM_PROMPT + "\n\n" + GUARDRAILS_SYSTEM_PROMPT
        return Agent(
            f"google-gla:{model_name}",
            toolsets=all_toolsets,
            system_prompt=combined_prompt,
        )

    def get_tools(self) -> list:
        """Get the list of available tools."""
        return list(self._toolset.tools.values())

    def close(self) -> None:
        """Sync cleanup."""
        if self._mcp_manager:
            if self._mcp_manager.needs_cleanup():
                deleted = self._mcp_manager.cleanup_files_sync()
                if deleted > 0:
                    logger.info("AgentFactory: Cleaned up %d file(s)", deleted)
            self._mcp_manager.disconnect_all()
            logger.info("AgentFactory: MCP connections closed")

    async def close_async(self) -> None:
        """Async cleanup with full server cleanup support."""
        if self._mcp_manager:
            if self._mcp_manager.needs_cleanup():
                results = await self._mcp_manager.cleanup_all()
                for name, result in results.items():
                    logger.info("AgentFactory: Cleanup '%s': %s", name, result)
            self._mcp_manager.disconnect_all()
            logger.info("AgentFactory: MCP connections closed")

    def __enter__(self) -> "AgentFactory":
        """Enter context manager."""
        return self

    def __exit__(self, *args) -> None:
        """Exit context manager, closing MCP connections."""
        self.close()
