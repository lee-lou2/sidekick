# tests/test_guardrails.py
"""Tests for the guardrails module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.middleware.guardrails import (
    GuardrailConfig,
    GuardrailEnforcer,
    GuardrailViolation,
    check_guardrails,
    create_default_guardrails,
    create_guardrail_hook,
    extract_paths_from_args,
    is_sensitive_file,
)


class TestIsSensitiveFile:
    """Tests for is_sensitive_file function."""

    def test_env_file_is_sensitive(self):
        config = GuardrailConfig()
        assert is_sensitive_file(".env", config) is True
        assert is_sensitive_file(".env.local", config) is True
        assert is_sensitive_file(".env.production", config) is True

    def test_env_in_path_is_sensitive(self):
        config = GuardrailConfig()
        assert is_sensitive_file("/project/.env", config) is True
        assert is_sensitive_file("config/.env.local", config) is True

    def test_aws_credentials_is_sensitive(self):
        config = GuardrailConfig()
        assert is_sensitive_file(".aws/credentials", config) is True
        assert is_sensitive_file("/home/user/.aws/credentials", config) is True

    def test_ssh_keys_are_sensitive(self):
        config = GuardrailConfig()
        assert is_sensitive_file("id_rsa", config) is True
        assert is_sensitive_file(".ssh/id_ed25519", config) is True
        assert is_sensitive_file("server.pem", config) is True

    def test_secret_files_are_sensitive(self):
        config = GuardrailConfig()
        assert is_sensitive_file("my_secret.txt", config) is True
        assert is_sensitive_file("api_key.json", config) is True
        assert is_sensitive_file("password.txt", config) is True
        assert is_sensitive_file("credentials.json", config) is True

    def test_python_files_are_safe(self):
        config = GuardrailConfig()
        assert is_sensitive_file("main.py", config) is False
        assert is_sensitive_file("src/agent/core.py", config) is False

    def test_readme_is_safe(self):
        config = GuardrailConfig()
        assert is_sensitive_file("README.md", config) is False
        assert is_sensitive_file("docs/README.md", config) is False

    def test_package_json_is_safe(self):
        config = GuardrailConfig()
        assert is_sensitive_file("package.json", config) is False

    def test_custom_sensitive_patterns(self):
        config = GuardrailConfig(sensitive_patterns={".my_custom_secret"})
        assert is_sensitive_file(".my_custom_secret", config) is True


class TestExtractPaths:
    """Tests for extract_paths_from_args function."""

    def test_extract_from_kwargs(self):
        paths = extract_paths_from_args((), {"path": "/some/file.txt"}, "read_file")
        assert "/some/file.txt" in paths

    def test_extract_from_multiple_kwargs(self):
        paths = extract_paths_from_args(
            (),
            {"source": "/src/file.txt", "destination": "/dst/file.txt"},
            "move_file",
        )
        assert "/src/file.txt" in paths
        assert "/dst/file.txt" in paths

    def test_extract_from_args(self):
        paths = extract_paths_from_args(("/some/path.py",), {}, "read_file")
        assert "/some/path.py" in paths

    def test_extract_from_list_paths(self):
        paths = extract_paths_from_args(
            (),
            {"paths": ["/file1.txt", "/file2.txt"]},
            "read_multiple_files",
        )
        assert "/file1.txt" in paths
        assert "/file2.txt" in paths


class TestCheckGuardrails:
    """Tests for check_guardrails function."""

    def test_blocks_sensitive_file_access(self):
        config = GuardrailConfig(block_sensitive_files=True)
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("read_file", (), {"path": ".env"}, config)
        assert exc_info.value.violation_type == "sensitive_file"

    def test_blocks_write_operations_in_read_only_mode(self):
        config = GuardrailConfig(read_only=True)
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("write_file", (), {"path": "file.txt"}, config)
        assert exc_info.value.violation_type == "write_operation"

    def test_allows_read_operations(self):
        config = GuardrailConfig(read_only=True, block_sensitive_files=False)
        check_guardrails("read_file", (), {"path": "file.txt"}, config)

    def test_allows_safe_files(self):
        config = GuardrailConfig(block_sensitive_files=True)
        check_guardrails("read_file", (), {"path": "main.py"}, config)

    def test_whitelist_mode(self):
        config = GuardrailConfig(allowed_tools={"read_file", "list_directory"})

        check_guardrails("read_file", (), {}, config)

        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("write_file", (), {}, config)
        assert exc_info.value.violation_type == "not_allowed"

    def test_blocks_prefixed_write_operations(self):
        config = GuardrailConfig(read_only=True)
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("gh_update_issue", (), {}, config)
        assert exc_info.value.violation_type == "write_operation"

        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("sentry_update_issue", (), {}, config)
        assert exc_info.value.violation_type == "write_operation"

    def test_allows_prefixed_read_operations(self):
        config = GuardrailConfig(read_only=True, block_sensitive_files=False)
        check_guardrails("gh_get_issue", (), {}, config)
        check_guardrails("sentry_list_issues", (), {}, config)


class TestCreateGuardrailHook:
    """Tests for create_guardrail_hook function."""

    @pytest.mark.asyncio
    async def test_hook_allows_safe_operations(self):
        """Test that hook allows safe read operations."""
        config = GuardrailConfig(read_only=True, block_sensitive_files=True)
        hook = create_guardrail_hook(config)

        # Mock call_tool function
        mock_call_tool = AsyncMock(return_value="file contents")
        mock_ctx = MagicMock()

        # Should allow reading safe files
        result = await hook(mock_ctx, mock_call_tool, "read_file", {"path": "main.py"})

        assert result == "file contents"
        mock_call_tool.assert_called_once_with("read_file", {"path": "main.py"}, None)

    @pytest.mark.asyncio
    async def test_hook_blocks_sensitive_files(self):
        """Test that hook returns error for sensitive files."""
        config = GuardrailConfig(block_sensitive_files=True)
        hook = create_guardrail_hook(config)

        mock_call_tool = AsyncMock()
        mock_ctx = MagicMock()

        result = await hook(mock_ctx, mock_call_tool, "read_file", {"path": ".env"})

        assert isinstance(result, list)
        assert "[BLOCKED]" in result[0]["text"]
        assert "sensitive" in result[0]["text"].lower()
        mock_call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_hook_blocks_write_operations(self):
        """Test that hook returns error for write operations in read-only mode."""
        config = GuardrailConfig(read_only=True)
        hook = create_guardrail_hook(config)

        mock_call_tool = AsyncMock()
        mock_ctx = MagicMock()

        result = await hook(
            mock_ctx,
            mock_call_tool,
            "write_file",
            {"path": "test.txt", "content": "data"},
        )

        assert isinstance(result, list)
        assert "[BLOCKED]" in result[0]["text"]
        assert "write_file" in result[0]["text"]
        mock_call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_hook_uses_default_config(self):
        """Test that hook uses default config when none provided."""
        hook = create_guardrail_hook()

        mock_call_tool = AsyncMock()
        mock_ctx = MagicMock()

        result = await hook(
            mock_ctx,
            mock_call_tool,
            "write_file",
            {"path": "test.txt", "content": "data"},
        )
        assert isinstance(result, list)
        assert "[BLOCKED]" in result[0]["text"]

        result = await hook(mock_ctx, mock_call_tool, "read_file", {"path": ".env"})
        assert isinstance(result, list)
        assert "[BLOCKED]" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_hook_forwards_tool_result(self):
        """Test that hook forwards the tool result correctly."""
        config = GuardrailConfig(read_only=False, block_sensitive_files=False)
        hook = create_guardrail_hook(config)

        mock_result = {"status": "success", "data": "test data"}
        mock_call_tool = AsyncMock(return_value=mock_result)
        mock_ctx = MagicMock()

        result = await hook(mock_ctx, mock_call_tool, "some_tool", {"arg1": "value1"})

        assert result == mock_result
        mock_call_tool.assert_called_once_with("some_tool", {"arg1": "value1"}, None)


class TestGuardrailConfig:
    """Tests for GuardrailConfig class."""

    def test_default_config(self):
        config = GuardrailConfig()
        assert config.read_only is True
        assert config.block_sensitive_files is True
        assert config.log_blocked_attempts is True

    def test_custom_config(self):
        config = GuardrailConfig(
            read_only=False,
            block_sensitive_files=False,
            sensitive_patterns={".custom"},
        )
        assert config.read_only is False
        assert ".custom" in config.get_all_sensitive_patterns()

    def test_get_all_blocked_tools(self):
        config = GuardrailConfig(
            read_only=True,
            blocked_tools={"custom_blocked_tool"},
        )
        blocked = config.get_all_blocked_tools()
        assert "custom_blocked_tool" in blocked
        assert "write_file" in blocked


class TestCreateDefaultGuardrails:
    """Tests for create_default_guardrails function."""

    def test_creates_safe_defaults(self):
        config = create_default_guardrails()
        assert config.read_only is True
        assert config.block_sensitive_files is True
        assert config.log_blocked_attempts is True


class TestMemoryIsolation:
    """Tests for memory isolation between users."""

    def test_get_allowed_memory_entity_with_user_id(self):
        """Test that allowed memory entity is computed correctly."""
        config = GuardrailConfig(current_user_id="U123456")
        assert config.get_allowed_memory_entity() == "user_U123456"

    def test_get_allowed_memory_entity_without_user_id(self):
        """Test that no entity is returned when user_id is None."""
        config = GuardrailConfig()
        assert config.get_allowed_memory_entity() is None

    def test_memory_access_allowed_for_own_entity(self):
        """Test that users can access their own memory entity."""
        config = GuardrailConfig(current_user_id="U123")
        # add_observations uses nested structure
        check_guardrails(
            "add_observations",
            (),
            {"observations": [{"entityName": "user_U123", "contents": ["test"]}]},
            config,
        )

    def test_memory_access_blocked_for_other_entity(self):
        """Test that users cannot access other users' memory entities."""
        config = GuardrailConfig(current_user_id="U123")
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails(
                "add_observations",
                (),
                {"observations": [{"entityName": "user_U456", "contents": ["test"]}]},
                config,
            )
        assert exc_info.value.violation_type == "memory_isolation"

    def test_memory_write_blocked_when_no_user_id(self):
        """Test that memory writes are blocked without user_id for safety."""
        config = GuardrailConfig()  # No user_id
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails(
                "create_entities",
                (),
                {"entities": [{"name": "user_U456", "entityType": "person"}]},
                config,
            )
        assert exc_info.value.violation_type == "memory_no_context"

    def test_memory_read_allowed_when_no_user_id(self):
        """Test that search_nodes is allowed but read_graph is blocked without user_id."""
        config = GuardrailConfig()  # No user_id
        # search_nodes should work (no entity restriction needed)
        check_guardrails("search_nodes", (), {"query": "test"}, config)
        # read_graph is blocked without user context to prevent exposing all users' data
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("read_graph", (), {}, config)
        assert exc_info.value.violation_type == "memory_no_context"

    def test_read_graph_allowed_with_user_id(self):
        """Test that read_graph is allowed with user_id."""
        config = GuardrailConfig(current_user_id="U123")
        # read_graph should work with user context
        check_guardrails("read_graph", (), {}, config)

    def test_create_entities_with_own_entity(self):
        """Test create_entities is allowed for own entity."""
        config = GuardrailConfig(current_user_id="U123")
        check_guardrails(
            "create_entities",
            (),
            {
                "entities": [
                    {
                        "name": "user_U123",
                        "entityType": "person",
                        "observations": ["Test observation"],
                    }
                ]
            },
            config,
        )

    def test_create_entities_blocked_for_other_entity(self):
        """Test create_entities is blocked for other user's entity."""
        config = GuardrailConfig(current_user_id="U123")
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails(
                "create_entities",
                (),
                {"entities": [{"name": "user_U456", "entityType": "person"}]},
                config,
            )
        assert exc_info.value.violation_type == "memory_isolation"

    def test_create_relations_with_own_entities(self):
        """Test create_relations is allowed between own entities."""
        config = GuardrailConfig(current_user_id="U123")
        check_guardrails(
            "create_relations",
            (),
            {
                "relations": [
                    {
                        "from": "user_U123",
                        "to": "user_U123_project",
                        "relationType": "works_on",
                    }
                ]
            },
            config,
        )

    def test_create_relations_blocked_with_other_entity(self):
        """Test create_relations is blocked when involving other user's entity."""
        config = GuardrailConfig(current_user_id="U123")
        # 'from' is another user
        with pytest.raises(GuardrailViolation):
            check_guardrails(
                "create_relations",
                (),
                {
                    "relations": [
                        {
                            "from": "user_U456",
                            "to": "user_U123",
                            "relationType": "knows",
                        }
                    ]
                },
                config,
            )
        # 'to' is another user
        with pytest.raises(GuardrailViolation):
            check_guardrails(
                "create_relations",
                (),
                {
                    "relations": [
                        {
                            "from": "user_U123",
                            "to": "user_U456",
                            "relationType": "knows",
                        }
                    ]
                },
                config,
            )

    def test_delete_entities_blocked_for_other_user(self):
        """Test delete_entities is blocked for other user's entity."""
        config = GuardrailConfig(current_user_id="U123")
        with pytest.raises(GuardrailViolation):
            check_guardrails(
                "delete_entities", (), {"entityNames": ["user_U456"]}, config
            )

    def test_delete_entities_allowed_for_own_entity(self):
        """Test delete_entities is allowed for own entity."""
        config = GuardrailConfig(current_user_id="U123")
        check_guardrails("delete_entities", (), {"entityNames": ["user_U123"]}, config)

    def test_open_nodes_allowed_for_own_entity(self):
        """Test open_nodes is allowed for own entity."""
        config = GuardrailConfig(current_user_id="U123")
        check_guardrails("open_nodes", (), {"names": ["user_U123"]}, config)

    def test_open_nodes_blocked_for_other_entity(self):
        """Test open_nodes is blocked for other user's entity."""
        config = GuardrailConfig(current_user_id="U123")
        with pytest.raises(GuardrailViolation):
            check_guardrails("open_nodes", (), {"names": ["user_U456"]}, config)

    def test_search_nodes_always_allowed(self):
        """Test search_nodes is always allowed (no entity restriction)."""
        config = GuardrailConfig(current_user_id="U123")
        check_guardrails("search_nodes", (), {"query": "user_U456"}, config)

    def test_prefixed_memory_tools(self):
        """Test memory isolation works with prefixed tool names."""
        config = GuardrailConfig(current_user_id="U123")
        # Prefixed tool should still be blocked
        with pytest.raises(GuardrailViolation):
            check_guardrails(
                "mem_create_entities",
                (),
                {"entities": [{"name": "user_U456", "entityType": "person"}]},
                config,
            )


class TestSafeZone:
    """Tests for safe zone feature."""

    def test_default_safe_zone_is_data(self):
        """Test that default safe zone includes data/."""
        config = GuardrailConfig()
        assert config.safe_zone_paths == {"data/"}

    def test_write_allowed_in_safe_zone(self):
        """Test that write operations are allowed in safe zone."""
        config = GuardrailConfig(read_only=True, block_sensitive_files=False)
        check_guardrails("write_file", (), {"path": "data/test.txt"}, config)

    def test_write_allowed_in_safe_zone_subdir(self):
        """Test that write operations are allowed in safe zone subdirectories."""
        config = GuardrailConfig(read_only=True, block_sensitive_files=False)
        check_guardrails("write_file", (), {"path": "data/subdir/test.txt"}, config)

    def test_write_blocked_outside_safe_zone(self):
        """Test that write operations are blocked outside safe zone."""
        config = GuardrailConfig(read_only=True)
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("write_file", (), {"path": "src/test.txt"}, config)
        assert exc_info.value.violation_type == "write_operation"

    def test_sensitive_file_blocked_in_safe_zone(self):
        """Test that sensitive files are still blocked in safe zone."""
        config = GuardrailConfig(read_only=True, block_sensitive_files=True)
        with pytest.raises(GuardrailViolation) as exc_info:
            check_guardrails("write_file", (), {"path": "data/.env"}, config)
        assert exc_info.value.violation_type == "sensitive_file"

    def test_safe_zone_with_absolute_path(self):
        """Test safe zone works with absolute paths."""
        config = GuardrailConfig(read_only=True, block_sensitive_files=False)
        check_guardrails(
            "write_file",
            (),
            {"path": "/Users/jake/dev/python/sidekick/data/test.txt"},
            config,
        )

    def test_multiple_paths_all_in_safe_zone(self):
        """Test that all paths must be in safe zone for multi-path operations."""
        config = GuardrailConfig(read_only=True, block_sensitive_files=False)
        check_guardrails(
            "move_file",
            (),
            {"source": "data/file1.txt", "destination": "data/file2.txt"},
            config,
        )

    def test_multiple_paths_mixed_blocked(self):
        """Test that operation is blocked if any path is outside safe zone."""
        config = GuardrailConfig(read_only=True)
        with pytest.raises(GuardrailViolation):
            check_guardrails(
                "move_file",
                (),
                {"source": "data/file.txt", "destination": "src/file.txt"},
                config,
            )

    def test_custom_safe_zone(self):
        """Test custom safe zone paths."""
        config = GuardrailConfig(
            read_only=True,
            block_sensitive_files=False,
            safe_zone_paths={"tmp/", "cache/"},
        )
        check_guardrails("write_file", (), {"path": "tmp/test.txt"}, config)
        check_guardrails("write_file", (), {"path": "cache/test.txt"}, config)

    def test_empty_safe_zone_blocks_all_writes(self):
        """Test that empty safe zone blocks all writes."""
        config = GuardrailConfig(read_only=True, safe_zone_paths=set())
        with pytest.raises(GuardrailViolation):
            check_guardrails("write_file", (), {"path": "data/test.txt"}, config)


class TestGuardrailEnforcer:
    """Tests for GuardrailEnforcer class."""

    def test_custom_tool_blocking_via_blocked_tools(self):
        """Test that custom tools can be blocked via blocked_tools config."""
        config = GuardrailConfig(read_only=False, blocked_tools={"my_dangerous_tool"})
        enforcer = GuardrailEnforcer(config)

        with pytest.raises(GuardrailViolation) as exc_info:
            enforcer.check("my_dangerous_tool", (), {})
        assert exc_info.value.violation_type == "blocked_tool"

    def test_tool_with_sensitive_file_path_blocking(self):
        """Test that tools accessing sensitive files are blocked."""
        enforcer = GuardrailEnforcer()

        with pytest.raises(GuardrailViolation) as exc_info:
            enforcer.check("read_file", (), {"path": ".env"})
        assert exc_info.value.violation_type == "sensitive_file"

    def test_check_allows_safe_operations(self):
        """Test that check allows safe operations."""
        enforcer = GuardrailEnforcer()
        enforcer.check("read_file", (), {"path": "README.md"})

    def test_wrap_tool_blocks_violations(self):
        """Test that wrap_tool blocks violating calls."""
        config = GuardrailConfig(blocked_tools={"blocked_func"})
        enforcer = GuardrailEnforcer(config)

        @enforcer.wrap_tool
        def blocked_func() -> str:
            return "should not reach here"

        with pytest.raises(GuardrailViolation):
            blocked_func()

    def test_wrap_tool_allows_safe_calls(self):
        """Test that wrap_tool allows safe function calls."""
        enforcer = GuardrailEnforcer()

        @enforcer.wrap_tool
        def safe_func(path: str) -> str:
            return f"Read: {path}"

        result = safe_func(path="README.md")
        assert result == "Read: README.md"

    def test_wrap_tool_blocks_sensitive_file_access(self):
        """Test that wrap_tool blocks sensitive file access in args."""
        enforcer = GuardrailEnforcer()

        @enforcer.wrap_tool
        def read_file(path: str) -> str:
            return f"Content of {path}"

        with pytest.raises(GuardrailViolation):
            read_file(path=".env")

    def test_wrap_tool_with_name(self):
        """Test wrap_tool_with_name uses specified tool name."""
        config = GuardrailConfig(blocked_tools={"write_file"})
        enforcer = GuardrailEnforcer(config)

        @enforcer.wrap_tool_with_name("write_file")
        def custom_write(path: str, content: str) -> None:
            pass

        with pytest.raises(GuardrailViolation):
            custom_write(path="test.txt", content="data")

    @pytest.mark.asyncio
    async def test_wrap_tool_async_function(self):
        """Test that wrap_tool works with async functions."""
        config = GuardrailConfig(blocked_tools={"async_blocked"})
        enforcer = GuardrailEnforcer(config)

        @enforcer.wrap_tool
        async def async_blocked() -> str:
            return "should not reach"

        with pytest.raises(GuardrailViolation):
            await async_blocked()

    @pytest.mark.asyncio
    async def test_wrap_tool_async_allows_safe_calls(self):
        """Test that wrap_tool allows safe async function calls."""
        enforcer = GuardrailEnforcer()

        @enforcer.wrap_tool
        async def async_safe(path: str) -> str:
            return f"Async read: {path}"

        result = await async_safe(path="README.md")
        assert result == "Async read: README.md"

    def test_enforcer_uses_default_config(self):
        """Test that enforcer uses default config when none provided."""
        enforcer = GuardrailEnforcer()
        assert enforcer.config.read_only is True
        assert enforcer.config.block_sensitive_files is True
