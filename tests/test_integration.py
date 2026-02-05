# tests/test_integration.py
"""Integration tests for full workflow verification.

Tests cover:
1. FunctionToolset -> AgentRunner integration
2. API end-to-end flow (POST /run -> execution -> GET /status)
3. Command lifecycle

All external APIs are mocked (Gemini, Slack, webhooks).
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class MockAgentResult:
    """Mock agent result for testing."""

    text: str
    images: list = None

    def __post_init__(self):
        if self.images is None:
            self.images = []


class TestToolsetAgentIntegration:
    """Test FunctionToolset -> AgentRunner integration."""

    def test_toolset_discovers_tools(self) -> None:
        """Test that ToolCatalog discovers command and scheduler tools."""
        from src.tools.catalog import get_all_tools

        toolset = get_all_tools()
        tools = toolset.tools

        assert isinstance(tools, dict)
        # Should have at least the command and scheduler tools
        assert len(tools) > 0

    def test_agent_runner_uses_toolset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that AgentRunner can be initialized with FunctionToolset."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        with (
            patch("src.core.agent.factory.Agent") as mock_agent_class,
            patch(
                "src.core.agent.factory.settings",
                MagicMock(
                    api_key="test-api-key", gemini_model="gemini-3-flash-preview"
                ),
            ),
        ):
            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent

            from src.core.agent.core import AgentRunner

            AgentRunner()  # Instantiate to trigger Agent creation

            mock_agent_class.assert_called_once()
            call_kwargs = mock_agent_class.call_args[1]

            # Verify toolsets were passed (FunctionToolset-based)
            assert "toolsets" in call_kwargs
            assert len(call_kwargs["toolsets"]) >= 1


class TestAPIEndToEnd:
    """Test API end-to-end flow: POST /run -> execution -> GET /status."""

    @pytest.mark.asyncio
    async def test_api_run_to_status_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test full API workflow: POST /run -> background execution -> GET /status."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from datetime import datetime

        from src.interfaces.api.main import app
        from src.interfaces.api.task_repository import TaskRecord

        mock_result = MagicMock()
        mock_result.output = "Task completed successfully"
        mock_result.images = []

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(return_value=mock_result)
        mock_runner.close = MagicMock()

        # Create mock task record
        def create_mock_task(task_id):
            return TaskRecord(
                task_id=task_id,
                status="pending",
                result=None,
                error_message=None,
                execution_time=None,
                tool_calls=[],
                model_used="gemini/gemini-3-flash-preview",
                images=[],
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

        with (
            patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner),
            patch("src.interfaces.api.main.get_task_repository") as mock_main_repo,
            patch("src.interfaces.api.tasks.get_task_repository") as mock_tasks_repo,
        ):
            mock_repo = MagicMock()
            mock_repo.get.side_effect = lambda task_id: create_mock_task(task_id)
            mock_main_repo.return_value = mock_repo
            mock_tasks_repo.return_value = mock_repo

            app.state.agent_runner = mock_runner

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post("/run", json={"prompt": "Calculate 2 + 3"})
                assert response.status_code == 200
                data = response.json()
                assert "task_id" in data
                assert data["status"] == "pending"
                task_id = data["task_id"]

                await asyncio.sleep(0.1)

                response = await client.get(f"/status/{task_id}")
                assert response.status_code == 200
                status_data = response.json()
                assert status_data["task_id"] == task_id
                assert status_data["status"] in ["pending", "success"]

    @pytest.mark.asyncio
    async def test_api_full_flow_with_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test API flow returns correct result after execution."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.tasks import execute_agent

        mock_result = MagicMock()
        mock_result.output = "Result: 5"
        mock_result.images = []

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(return_value=mock_result)
        mock_runner.close = MagicMock()

        with (
            patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner),
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
        ):
            mock_repo = MagicMock()
            mock_repo_func.return_value = mock_repo

            task_id = "test-integration-task"
            request = RunRequest(prompt="Add 2 and 3", user_id=None, webhook_url=None)

            await execute_agent(task_id, request)

            # Verify update was called with success
            mock_repo.update.assert_called()
            call_kwargs = mock_repo.update.call_args[1]
            assert call_kwargs["status"] == "success"
            assert call_kwargs["result"] == "Result: 5"
            assert call_kwargs["execution_time"] is not None

    @pytest.mark.asyncio
    async def test_api_flow_with_webhook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test API flow sends webhook callback on completion."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from datetime import datetime

        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.task_repository import TaskRecord
        from src.interfaces.api.tasks import execute_agent

        mock_result = MagicMock()
        mock_result.output = "Webhook test result"
        mock_result.images = []

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(return_value=mock_result)
        mock_runner.close = MagicMock()

        # Create mock task record for webhook
        mock_task = TaskRecord(
            task_id="webhook-integration-test",
            status="success",
            result="Webhook test result",
            error_message=None,
            execution_time=1.0,
            tool_calls=[],
            model_used="gemini/gemini-3-flash-preview",
            images=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with (
            patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner),
            patch("src.interfaces.api.tasks.send_webhook") as mock_webhook,
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
        ):
            mock_repo = MagicMock()
            mock_repo.get.return_value = mock_task
            mock_repo_func.return_value = mock_repo
            mock_webhook.return_value = True

            task_id = "webhook-integration-test"
            request = RunRequest(
                prompt="Test with webhook",
                user_id=None,
                webhook_url="https://example.com/callback",
            )

            await execute_agent(task_id, request)

            mock_webhook.assert_called_once()
            call_args = mock_webhook.call_args[0]
            assert call_args[0] == "https://example.com/callback"
            assert call_args[1]["task_id"] == task_id
            assert call_args[1]["status"] == "success"
            assert call_args[1]["result"] == "Webhook test result"


class TestCommandE2E:
    """Test command feature end-to-end lifecycle."""

    @pytest.mark.asyncio
    async def test_full_command_lifecycle(self, tmp_path: Path) -> None:
        """Test complete command lifecycle: create -> execute -> update -> delete."""
        from datetime import datetime

        from src.core.commands.executor import CommandExecutor
        from src.core.commands.models import Command
        from src.core.commands.parser import parse_command
        from src.core.commands.repository import CommandRepository

        # Use temporary database
        db_path = tmp_path / "test_commands.db"
        repo = CommandRepository(str(db_path))
        executor = CommandExecutor(repo)

        # Step 1: Create command
        cmd = Command(
            id=0,
            name="greet",
            prompt="Say hello to {input}",
            original_prompt="Say hello to {input}",
            recommended_tools=[],
            created_by="test:user1",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        created = repo.create(cmd)
        assert created.id > 0
        assert created.name == "greet"

        # Step 2: Execute command via parser
        parsed = parse_command("!greet Alice")
        assert parsed is not None
        prompt = executor.execute(parsed, user_id="test:user1")
        assert prompt is not None
        assert "Alice" in prompt
        assert "greet" in prompt.lower()

        # Step 3: Update command
        created.prompt = "Greet {input} warmly"
        updated = repo.update(created)
        assert updated.prompt == "Greet {input} warmly"

        # Step 4: Execute updated command
        parsed2 = parse_command("!greet Bob")
        assert parsed2 is not None
        prompt2 = executor.execute(parsed2, user_id="test:user1")
        assert prompt2 is not None
        assert "Bob" in prompt2
        assert "warmly" in prompt2.lower()

        # Step 5: Delete command
        deleted = repo.delete("greet")
        assert deleted is True

        # Step 6: Verify command no longer exists
        parsed3 = parse_command("!greet Charlie")
        assert parsed3 is not None
        prompt3 = executor.execute(parsed3, user_id="test:user1")
        assert prompt3 is None

    @pytest.mark.asyncio
    async def test_command_with_ai_enhancement(self, tmp_path: Path) -> None:
        """Test that AI enhancement produces different prompt from original."""
        from src.core.commands import tools as command_tools

        # Mock Gemini API and settings.api_key (needed for _enhance_prompt to call completion)
        with (
            patch("src.core.commands.tools.completion") as mock_completion,
            patch("src.core.commands.tools.settings") as mock_settings,
        ):
            mock_settings.api_key = "test-api-key"
            mock_completion.return_value = MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content="Enhanced: Provide a detailed weather forecast for {input}"
                        )
                    )
                ]
            )

            # Use temporary database
            db_path = tmp_path / "test_commands.db"
            with patch("src.core.commands.tools.get_repository") as mock_get_repo:
                from src.core.commands.repository import CommandRepository

                repo = CommandRepository(str(db_path))
                mock_get_repo.return_value = repo

                result = command_tools.create_command(
                    name="weather",
                    prompt="Get weather for {input}",
                    user_id="test:user1",
                )

                assert "created successfully" in result
                assert "weather" in result

                # Verify command was created with enhanced prompt
                cmd = repo.get_by_name("weather")
                assert cmd is not None
                assert cmd.prompt != cmd.original_prompt
                assert "Enhanced" in cmd.prompt or "detailed" in cmd.prompt.lower()

    @pytest.mark.asyncio
    async def test_command_input_substitution(self, tmp_path: Path) -> None:
        """Test that {input} placeholder is correctly substituted."""
        from datetime import datetime

        from src.core.commands.executor import CommandExecutor
        from src.core.commands.models import Command
        from src.core.commands.parser import parse_command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test_commands.db"
        repo = CommandRepository(str(db_path))
        executor = CommandExecutor(repo)

        # Create command with multiple {input} placeholders
        cmd = Command(
            id=0,
            name="repeat",
            prompt="First {input}, then {input} again",
            original_prompt="First {input}, then {input} again",
            recommended_tools=[],
            created_by="test:user1",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        repo.create(cmd)

        # Execute and verify substitution
        parsed = parse_command("!repeat hello")
        assert parsed is not None
        prompt = executor.execute(parsed, user_id="test:user1")
        assert prompt is not None
        assert "First hello, then hello again" in prompt

    @pytest.mark.asyncio
    async def test_missing_command_returns_none(self, tmp_path: Path) -> None:
        """Test that executing non-existent command returns None."""
        from src.core.commands.executor import CommandExecutor
        from src.core.commands.parser import parse_command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test_commands.db"
        repo = CommandRepository(str(db_path))
        executor = CommandExecutor(repo)

        # Try to execute non-existent command
        parsed = parse_command("!nonexistent test")
        assert parsed is not None
        prompt = executor.execute(parsed, user_id="test:user1")
        assert prompt is None


class TestCommandPermissions:
    """Test command permission enforcement."""

    @pytest.mark.asyncio
    async def test_command_permission_check(self, tmp_path: Path) -> None:
        """Test command permission validation."""
        from src.core.commands import tools as command_tools
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test_commands.db"

        with patch("src.core.commands.tools.get_repository") as mock_get_repo:
            repo = CommandRepository(str(db_path))
            mock_get_repo.return_value = repo

            # User1 creates command
            result1 = command_tools.create_command(
                name="private", prompt="Private command", user_id="slack:U123"
            )
            assert "created successfully" in result1

            # User2 tries to delete (should fail)
            result2 = command_tools.delete_command(name="private", user_id="slack:U456")
            assert "Permission denied" in result2
            assert "slack:U123" in result2

            # User1 can delete
            result3 = command_tools.delete_command(name="private", user_id="slack:U123")
            assert "deleted successfully" in result3

    @pytest.mark.asyncio
    async def test_command_permissions_enforced_across_platforms(
        self, tmp_path: Path
    ) -> None:
        """Test permission checks work regardless of platform."""
        from src.core.commands import tools as command_tools
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test_commands.db"

        with patch("src.core.commands.tools.get_repository") as mock_get_repo:
            repo = CommandRepository(str(db_path))
            mock_get_repo.return_value = repo

            # Create as Slack user
            result1 = command_tools.create_command(
                name="mixed", prompt="Test", user_id="slack:U123"
            )
            assert "created successfully" in result1

            # Try to update as API user (should fail)
            result2 = command_tools.update_command(
                name="mixed", prompt="Updated", user_id="api:user1"
            )
            assert "Permission denied" in result2
            assert "slack:U123" in result2

            # Try to delete as API user (should fail)
            result3 = command_tools.delete_command(name="mixed", user_id="api:user1")
            assert "Permission denied" in result3

            # Original creator can delete
            result4 = command_tools.delete_command(name="mixed", user_id="slack:U123")
            assert "deleted successfully" in result4


class TestAPICommandIntegration:
    """Test API command integration."""

    @pytest.mark.asyncio
    async def test_api_command_crud_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test API command CRUD operations end-to-end."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")

        from src.interfaces.api.main import app

        # Use temporary database
        db_path = tmp_path / "test_commands.db"

        with patch("src.interfaces.api.main._get_command_repository") as mock_get_repo:
            from src.core.commands.repository import CommandRepository

            repo = CommandRepository(str(db_path))
            mock_get_repo.return_value = repo

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Step 1: Create command
                with patch(
                    "src.interfaces.api.main.command_tools.create_command"
                ) as mock_create:
                    mock_create.return_value = "Command 'test' created successfully!"

                    response = await client.post(
                        "/commands",
                        json={
                            "name": "test",
                            "prompt": "Test {input}",
                            "user_id": "user1",
                        },
                    )
                    assert response.status_code == 201
                    data = response.json()
                    assert "created successfully" in data["message"]

                    # Manually create in repo for subsequent tests
                    from datetime import datetime

                    from src.core.commands.models import Command

                    cmd = Command(
                        id=0,
                        name="test",
                        prompt="Test {input}",
                        original_prompt="Test {input}",
                        recommended_tools=[],
                        created_by="api:user1",
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                    )
                    repo.create(cmd)

                # Step 2: List commands
                response = await client.get("/commands")
                assert response.status_code == 200
                commands = response.json()
                assert len(commands) == 1
                assert commands[0]["name"] == "test"

                # Step 3: Get single command
                response = await client.get("/commands/test")
                assert response.status_code == 200
                cmd_data = response.json()
                assert cmd_data["name"] == "test"
                assert cmd_data["created_by"] == "api:user1"

                # Step 4: Update command
                with patch(
                    "src.interfaces.api.main.command_tools.update_command"
                ) as mock_update:
                    mock_update.return_value = "Command 'test' updated successfully!"

                    response = await client.put(
                        "/commands/test",
                        json={"prompt": "Updated {input}", "user_id": "user1"},
                    )
                    assert response.status_code == 200

                # Step 5: Delete command
                with patch(
                    "src.interfaces.api.main.command_tools.delete_command"
                ) as mock_delete:
                    mock_delete.return_value = "Command 'test' deleted successfully."

                    response = await client.delete("/commands/test?user_id=user1")
                    assert response.status_code == 200

                    repo.delete("test")

                # Step 6: Verify deleted
                response = await client.get("/commands/test")
                assert response.status_code == 404
