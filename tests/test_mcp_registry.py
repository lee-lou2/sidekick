# tests/test_mcp_registry.py
"""Tests for MCP server auto-registration framework."""

import pytest

from src.tools.mcp_registry import (
    MCPServerConfig,
    _registered_servers,
    auto_discover_mcp_servers,
    get_registered_servers,
    register_mcp_server,
)


class TestRegisterMcpServer:
    """Tests for register_mcp_server() function."""

    def setup_method(self):
        _registered_servers.clear()

    def teardown_method(self):
        _registered_servers.clear()

    def test_basic_registration(self):
        config = register_mcp_server(
            key="test-server",
            name="Test Server",
            description="A test MCP server",
            command="npx",
            args=["-y", "@test/server"],
        )
        assert isinstance(config, MCPServerConfig)
        assert config.name == "Test Server"
        assert config.command == "npx"
        assert config.args == ["-y", "@test/server"]
        assert config.enabled is True
        assert config.env == {}
        assert config.requires_env == []
        assert config.tool_prefix is None
        assert "test-server" in _registered_servers

    def test_registration_with_env_and_prefix(self):
        config = register_mcp_server(
            key="github",
            name="GitHub",
            description="GitHub API",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "test-token"},
            requires_env=["GITHUB_TOKEN"],
            tool_prefix="gh",
        )
        assert config.env == {"GITHUB_TOKEN": "test-token"}
        assert config.requires_env == ["GITHUB_TOKEN"]
        assert config.tool_prefix == "gh"

    def test_empty_key_raises_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            register_mcp_server(
                key="",
                name="Bad",
                description="Bad server",
                command="npx",
                args=[],
            )

    def test_whitespace_key_raises_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            register_mcp_server(
                key="   ",
                name="Bad",
                description="Bad server",
                command="npx",
                args=[],
            )

    def test_duplicate_key_overwrites(self):
        register_mcp_server(
            key="dup",
            name="First",
            description="First server",
            command="npx",
            args=["first"],
        )
        register_mcp_server(
            key="dup",
            name="Second",
            description="Second server",
            command="uvx",
            args=["second"],
        )
        assert _registered_servers["dup"].name == "Second"
        assert _registered_servers["dup"].command == "uvx"

    def test_disabled_server(self):
        config = register_mcp_server(
            key="disabled",
            name="Disabled",
            description="Disabled server",
            command="npx",
            args=[],
            enabled=False,
        )
        assert config.enabled is False
        assert not config.is_available()


class TestGetRegisteredServers:
    """Tests for get_registered_servers() function."""

    def setup_method(self):
        _registered_servers.clear()

    def teardown_method(self):
        _registered_servers.clear()

    def test_returns_copy(self):
        register_mcp_server(
            key="test",
            name="Test",
            description="Test",
            command="npx",
            args=[],
        )
        result = get_registered_servers()
        assert result == _registered_servers
        # Modifying the copy should not affect the original
        result["injected"] = MCPServerConfig(
            name="Injected",
            description="Injected",
            command="npx",
            args=[],
        )
        assert "injected" not in _registered_servers

    def test_empty_registry(self):
        result = get_registered_servers()
        assert result == {}


class TestAutoDiscoverMcpServers:
    """Tests for auto_discover_mcp_servers() function."""

    def setup_method(self):
        _registered_servers.clear()

    def teardown_method(self):
        _registered_servers.clear()

    def test_nonexistent_package(self):
        result = auto_discover_mcp_servers("nonexistent.package.path")
        assert result == {}

    def test_package_without_path(self):
        # json module has no __path__ attribute (not a package)
        result = auto_discover_mcp_servers("json")
        assert isinstance(result, dict)

    def test_empty_package(self):
        # Discovers servers from src.tools.mcp
        result = auto_discover_mcp_servers("src.tools.mcp")
        assert isinstance(result, dict)
