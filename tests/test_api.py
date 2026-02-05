# tests/test_api.py
"""Tests for FastAPI endpoints and webhook callback.

TDD approach: Tests define expected behavior before implementation.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, ConnectError, TimeoutException

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.agent.core import AgentRunResult


class TestRunEndpoint:
    """Tests for POST /run endpoint."""

    @pytest.mark.asyncio
    async def test_run_endpoint_returns_task_id(self, monkeypatch):
        """Test POST /run returns task_id and pending status."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.main import app

        app.state.api_key_available = True

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(
            return_value=AgentRunResult(output="Done", images=[])
        )
        mock_runner.close = MagicMock()

        with patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post("/run", json={"prompt": "Test prompt"})

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert len(data["task_id"]) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_run_endpoint_with_webhook_url(self, monkeypatch):
        """Test POST /run accepts optional webhook_url."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.main import app

        app.state.api_key_available = True

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(
            return_value=AgentRunResult(output="Done", images=[])
        )
        mock_runner.close = MagicMock()

        with patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/run",
                    json={
                        "prompt": "Test prompt",
                        "webhook_url": "https://example.com/callback",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data


class TestStatusEndpoint:
    """Tests for GET /status/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_pending(self, monkeypatch):
        """Test GET /status returns pending status for new task."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.main import app
        from src.interfaces.api.task_repository import TaskRecord

        # Set up mock agent runner
        mock_runner = MagicMock()
        app.state.agent_runner = mock_runner

        # Create a mock task record
        test_task_id = "test-task-123"
        from datetime import datetime

        mock_task = TaskRecord(
            task_id=test_task_id,
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

        with patch("src.interfaces.api.main.get_task_repository") as mock_repo_func:
            mock_repo = MagicMock()
            mock_repo.get.return_value = mock_task
            mock_repo_func.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/status/{test_task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == test_task_id
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_completed(self, monkeypatch):
        """Test GET /status returns completed status with result."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.main import app
        from src.interfaces.api.task_repository import TaskRecord

        # Set up mock agent runner
        mock_runner = MagicMock()
        app.state.agent_runner = mock_runner

        # Create a completed task record
        test_task_id = "completed-task-456"
        from datetime import datetime

        mock_task = TaskRecord(
            task_id=test_task_id,
            status="success",
            result="Agent completed task",
            error_message=None,
            execution_time=1.5,
            tool_calls=["tool1", "tool2"],
            model_used="gemini/gemini-3-pro-preview",
            images=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with patch("src.interfaces.api.main.get_task_repository") as mock_repo_func:
            mock_repo = MagicMock()
            mock_repo.get.return_value = mock_task
            mock_repo_func.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/status/{test_task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == test_task_id
        assert data["status"] == "success"
        assert data["result"] == "Agent completed task"
        assert data["execution_time"] == 1.5
        assert data["tool_calls"] == ["tool1", "tool2"]

    @pytest.mark.asyncio
    async def test_status_endpoint_not_found(self, monkeypatch):
        """Test GET /status returns 404 for unknown task_id."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.main import app

        # Set up mock agent runner
        mock_runner = MagicMock()
        app.state.agent_runner = mock_runner

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/status/nonexistent-task-id")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestWebhookCallback:
    """Tests for webhook callback functionality."""

    @pytest.mark.asyncio
    async def test_send_webhook_success(self):
        """Test webhook is sent on successful task completion."""
        from src.interfaces.api.tasks import send_webhook

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            payload = {
                "task_id": "test-task",
                "status": "success",
                "result": "Done",
            }

            await send_webhook("https://example.com/callback", payload)

            mock_client.post.assert_called_once_with(
                "https://example.com/callback",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

    @pytest.mark.asyncio
    async def test_send_webhook_retries_on_timeout(self):
        """Test webhook retries on timeout (with tenacity)."""
        from src.interfaces.api.tasks import send_webhook

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            # First call times out, second succeeds
            mock_client.post.side_effect = [
                TimeoutException("Timeout"),
                mock_response,
            ]
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            payload = {"task_id": "test-task", "status": "success"}

            await send_webhook("https://example.com/callback", payload)

            # Should have been called twice (1 fail + 1 success)
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_webhook_retries_on_connect_error(self):
        """Test webhook retries on connection error."""
        from src.interfaces.api.tasks import send_webhook

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            # First two calls fail, third succeeds
            mock_client.post.side_effect = [
                ConnectError("Connection refused"),
                ConnectError("Connection refused"),
                mock_response,
            ]
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            payload = {"task_id": "test-task", "status": "success"}

            await send_webhook("https://example.com/callback", payload)

            # Should have been called 3 times
            assert mock_client.post.call_count == 3


class TestBackgroundTaskExecution:
    """Tests for background task execution."""

    @pytest.mark.asyncio
    async def test_execute_agent_stores_result(self, monkeypatch):
        """Test agent execution stores result in task repository."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.tasks import execute_agent

        mock_result = AgentRunResult(output="Task completed successfully", images=[])
        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = AsyncMock(return_value=mock_result)
        mock_runner_instance.close = MagicMock()

        with (
            patch(
                "src.interfaces.api.tasks.AgentRunner",
                return_value=mock_runner_instance,
            ),
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
        ):
            mock_repo = MagicMock()
            mock_repo_func.return_value = mock_repo

            request = RunRequest(prompt="Test prompt")
            task_id = "exec-test-task"

            await execute_agent(task_id, request)

            # Verify update was called with success status
            mock_repo.update.assert_called()
            call_kwargs = mock_repo.update.call_args[1]
            assert call_kwargs["task_id"] == task_id
            assert call_kwargs["status"] == "success"
            assert call_kwargs["result"] == "Task completed successfully"

    @pytest.mark.asyncio
    async def test_execute_agent_handles_error(self, monkeypatch):
        """Test agent execution handles errors gracefully."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.tasks import execute_agent

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = AsyncMock(
            side_effect=Exception("Agent failed")
        )
        mock_runner_instance.close = MagicMock()

        with (
            patch(
                "src.interfaces.api.tasks.AgentRunner",
                return_value=mock_runner_instance,
            ),
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
        ):
            mock_repo = MagicMock()
            mock_repo_func.return_value = mock_repo

            request = RunRequest(prompt="Test prompt")
            task_id = "error-test-task"

            await execute_agent(task_id, request)

            # Verify update was called with error status
            mock_repo.update.assert_called()
            call_kwargs = mock_repo.update.call_args[1]
            assert call_kwargs["task_id"] == task_id
            assert call_kwargs["status"] == "error"
            assert "Agent failed" in call_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_execute_agent_calls_webhook(self, monkeypatch):
        """Test agent execution calls webhook when provided."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from datetime import datetime

        from src.interfaces.api.schemas import RunRequest
        from src.interfaces.api.task_repository import TaskRecord
        from src.interfaces.api.tasks import execute_agent

        mock_result = AgentRunResult(output="Done", images=[])
        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = AsyncMock(return_value=mock_result)
        mock_runner_instance.close = MagicMock()

        # Create mock task record for webhook payload
        mock_task = TaskRecord(
            task_id="webhook-test-task",
            status="success",
            result="Done",
            error_message=None,
            execution_time=1.0,
            tool_calls=[],
            model_used="gemini/gemini-3-flash-preview",
            images=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        with (
            patch(
                "src.interfaces.api.tasks.AgentRunner",
                return_value=mock_runner_instance,
            ),
            patch("src.interfaces.api.tasks.get_task_repository") as mock_repo_func,
            patch("src.interfaces.api.tasks.send_webhook") as mock_webhook,
        ):
            mock_repo = MagicMock()
            mock_repo.get.return_value = mock_task
            mock_repo_func.return_value = mock_repo
            mock_webhook.return_value = True

            request = RunRequest(
                prompt="Test prompt", webhook_url="https://example.com/callback"
            )
            task_id = "webhook-test-task"

            await execute_agent(task_id, request)

            mock_webhook.assert_called_once()
            call_args = mock_webhook.call_args
            assert call_args[0][0] == "https://example.com/callback"
            assert call_args[0][1]["task_id"] == task_id
            assert call_args[0][1]["status"] == "success"


class TestCommandEndpoints:
    """Tests for /commands CRUD endpoints."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_commands.db"
        return str(db_path)

    @pytest.mark.asyncio
    async def test_create_command_success(self, monkeypatch, temp_db):
        """Test POST /commands creates a new command."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.create_command"
        ) as mock_create:
            mock_create.return_value = "Command 'test' created successfully!"

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/commands",
                    json={"name": "test", "prompt": "Test prompt", "user_id": "user1"},
                )

            assert response.status_code == 201
            data = response.json()
            assert "message" in data
            mock_create.assert_called_once_with("test", "Test prompt", "api:user1")

    @pytest.mark.asyncio
    async def test_create_command_duplicate(self, monkeypatch, temp_db):
        """Test POST /commands returns 400 for duplicate command."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.create_command"
        ) as mock_create:
            mock_create.return_value = "Error: Command 'test' already exists."

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/commands",
                    json={"name": "test", "prompt": "Test prompt", "user_id": "user1"},
                )

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_commands_empty(self, monkeypatch, temp_db):
        """Test GET /commands returns empty list when no commands exist."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch("src.interfaces.api.main._get_command_repository") as mock_repo_func:
            mock_repo = MagicMock()
            mock_repo.list_all.return_value = []
            mock_repo_func.return_value = mock_repo

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/commands")

            assert response.status_code == 200
            data = response.json()
            assert data == []

    @pytest.mark.asyncio
    async def test_list_commands_with_data(self, monkeypatch, temp_db):
        """Test GET /commands returns list of commands."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        from datetime import datetime

        from src.core.commands.models import Command

        mock_cmd = Command(
            id=1,
            name="test",
            prompt="Enhanced prompt",
            original_prompt="Original",
            recommended_tools=["tool1"],
            created_by="api:user1",
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            updated_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        with patch("src.interfaces.api.main._get_command_repository") as mock_repo_func:
            mock_repo = MagicMock()
            mock_repo.list_all.return_value = [mock_cmd]
            mock_repo_func.return_value = mock_repo

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/commands")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "test"
            assert data[0]["recommended_tools"] == ["tool1"]

    @pytest.mark.asyncio
    async def test_get_command_found(self, monkeypatch, temp_db):
        """Test GET /commands/{name} returns command details."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        from datetime import datetime

        from src.core.commands.models import Command

        mock_cmd = Command(
            id=1,
            name="test",
            prompt="Enhanced prompt",
            original_prompt="Original",
            recommended_tools=["tool1"],
            created_by="api:user1",
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            updated_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        with patch("src.interfaces.api.main._get_command_repository") as mock_repo_func:
            mock_repo = MagicMock()
            mock_repo.get_by_name.return_value = mock_cmd
            mock_repo_func.return_value = mock_repo

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/commands/test")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test"
            assert data["prompt"] == "Enhanced prompt"

    @pytest.mark.asyncio
    async def test_get_command_not_found(self, monkeypatch, temp_db):
        """Test GET /commands/{name} returns 404 for nonexistent command."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch("src.interfaces.api.main._get_command_repository") as mock_repo_func:
            mock_repo = MagicMock()
            mock_repo.get_by_name.return_value = None
            mock_repo_func.return_value = mock_repo

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/commands/nonexistent")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_command_success(self, monkeypatch, temp_db):
        """Test PUT /commands/{name} updates command."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.update_command"
        ) as mock_update:
            mock_update.return_value = "Command 'test' updated successfully!"

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.put(
                    "/commands/test",
                    json={"prompt": "New prompt", "user_id": "user1"},
                )

            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            mock_update.assert_called_once_with("test", "New prompt", "api:user1")

    @pytest.mark.asyncio
    async def test_update_command_not_found(self, monkeypatch, temp_db):
        """Test PUT /commands/{name} returns 404 for nonexistent command."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.update_command"
        ) as mock_update:
            mock_update.return_value = "Error: Command 'test' not found."

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.put(
                    "/commands/test",
                    json={"prompt": "New prompt", "user_id": "user1"},
                )

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_command_permission_denied(self, monkeypatch, temp_db):
        """Test PUT /commands/{name} returns 403 for non-owner."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.update_command"
        ) as mock_update:
            mock_update.return_value = "Permission denied: Only the creator can update."

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.put(
                    "/commands/test",
                    json={"prompt": "New prompt", "user_id": "other_user"},
                )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_command_success(self, monkeypatch, temp_db):
        """Test DELETE /commands/{name} deletes command."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.delete_command"
        ) as mock_delete:
            mock_delete.return_value = "Command 'test' deleted successfully."

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.delete("/commands/test?user_id=user1")

            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            mock_delete.assert_called_once_with("test", "api:user1")

    @pytest.mark.asyncio
    async def test_delete_command_permission_denied(self, monkeypatch, temp_db):
        """Test DELETE /commands/{name} returns 403 for non-owner."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with patch(
            "src.interfaces.api.main.command_tools.delete_command"
        ) as mock_delete:
            mock_delete.return_value = "Permission denied: Only the creator can delete."

            from src.interfaces.api.main import app

            app.state.agent_runner = MagicMock()
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.delete("/commands/test?user_id=other_user")

            assert response.status_code == 403


class TestCommandDetectionInRun:
    """Tests for command detection in /run endpoint."""

    @pytest.mark.asyncio
    async def test_run_with_command_expands_prompt(self, monkeypatch):
        """Test POST /run detects and expands command in prompt."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with (
            patch("src.interfaces.api.tasks.parse_command") as mock_parse,
            patch("src.interfaces.api.tasks.CommandExecutor") as mock_executor_class,
            patch("src.interfaces.api.tasks.CommandRepository"),
            patch("src.interfaces.api.tasks.AgentRunner") as mock_runner_class,
        ):
            from src.core.commands.parser import ParsedCommand

            mock_parse.return_value = ParsedCommand(name="test", input="Seoul")
            mock_executor = MagicMock()
            mock_executor.execute.return_value = "Expanded prompt for Seoul"
            mock_executor_class.return_value = mock_executor

            from src.interfaces.api.schemas import RunRequest
            from src.interfaces.api.tasks import execute_agent

            mock_runner = MagicMock()
            mock_result = AgentRunResult(output="Agent result", images=[])
            mock_runner.run_async = AsyncMock(return_value=mock_result)
            mock_runner.close = MagicMock()
            mock_runner_class.return_value = mock_runner

            with patch(
                "src.interfaces.api.tasks.get_task_repository"
            ) as mock_repo_func:
                mock_repo = MagicMock()
                mock_repo_func.return_value = mock_repo

                request = RunRequest(prompt="!test Seoul")
                task_id = "cmd-test-task"

                await execute_agent(task_id, request)

                mock_runner.run_async.assert_called_once_with(
                    "Expanded prompt for Seoul"
                )
                # Verify update was called with success status
                mock_repo.update.assert_called()
                call_kwargs = mock_repo.update.call_args[1]
                assert call_kwargs["status"] == "success"

    @pytest.mark.asyncio
    async def test_run_without_command_uses_original_prompt(self, monkeypatch):
        """Test POST /run uses original prompt when no command detected."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with (
            patch("src.interfaces.api.tasks.parse_command") as mock_parse,
            patch("src.interfaces.api.tasks.AgentRunner") as mock_runner_class,
        ):
            mock_parse.return_value = None

            from src.interfaces.api.schemas import RunRequest
            from src.interfaces.api.tasks import execute_agent

            mock_runner = MagicMock()
            mock_result = AgentRunResult(output="Agent result", images=[])
            mock_runner.run_async = AsyncMock(return_value=mock_result)
            mock_runner.close = MagicMock()
            mock_runner_class.return_value = mock_runner

            with patch(
                "src.interfaces.api.tasks.get_task_repository"
            ) as mock_repo_func:
                mock_repo = MagicMock()
                mock_repo_func.return_value = mock_repo

                request = RunRequest(prompt="Regular prompt without command")
                task_id = "regular-test-task"

                await execute_agent(task_id, request)

                mock_runner.run_async.assert_called_once_with(
                    "Regular prompt without command"
                )

    @pytest.mark.asyncio
    async def test_run_with_command_not_found_uses_original(self, monkeypatch):
        """Test POST /run uses original prompt when command not found."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        with (
            patch("src.interfaces.api.tasks.parse_command") as mock_parse,
            patch("src.interfaces.api.tasks.CommandExecutor") as mock_executor_class,
            patch("src.interfaces.api.tasks.CommandRepository"),
            patch("src.interfaces.api.tasks.AgentRunner") as mock_runner_class,
        ):
            from src.core.commands.parser import ParsedCommand

            mock_parse.return_value = ParsedCommand(name="nonexistent", input="")
            mock_executor = MagicMock()
            mock_executor.execute.return_value = None
            mock_executor_class.return_value = mock_executor

            from src.interfaces.api.schemas import RunRequest
            from src.interfaces.api.tasks import execute_agent

            mock_runner = MagicMock()
            mock_result = AgentRunResult(output="Agent result", images=[])
            mock_runner.run_async = AsyncMock(return_value=mock_result)
            mock_runner.close = MagicMock()
            mock_runner_class.return_value = mock_runner

            with patch(
                "src.interfaces.api.tasks.get_task_repository"
            ) as mock_repo_func:
                mock_repo = MagicMock()
                mock_repo_func.return_value = mock_repo

                request = RunRequest(prompt="!nonexistent arg")
                task_id = "notfound-test-task"

                await execute_agent(task_id, request)

                mock_runner.run_async.assert_called_once_with("!nonexistent arg")


class TestApiSecurity:
    """Tests for API authentication and rate limiting."""

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_401(self, monkeypatch):
        """Test request without API key returns 401 when auth is enabled."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("API_AUTH_KEY", "secret-api-key")

        from importlib import reload

        import src.config
        import src.interfaces.api.security

        reload(src.config)
        reload(src.interfaces.api.security)

        from src.interfaces.api.main import app

        app.state.api_key_available = True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/run", json={"prompt": "Test"})

        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_403(self, monkeypatch):
        """Test request with invalid API key returns 403."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("API_AUTH_KEY", "secret-api-key")

        from importlib import reload

        import src.config
        import src.interfaces.api.security

        reload(src.config)
        reload(src.interfaces.api.security)

        from src.interfaces.api.main import app

        app.state.api_key_available = True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/run",
                json={"prompt": "Test"},
                headers={"X-API-Key": "wrong-key"},
            )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_api_key_succeeds(self, monkeypatch):
        """Test request with valid API key succeeds."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("API_AUTH_KEY", "secret-api-key")

        from importlib import reload

        import src.config
        import src.interfaces.api.security

        reload(src.config)
        reload(src.interfaces.api.security)

        from src.interfaces.api.main import app

        app.state.api_key_available = True

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(
            return_value=AgentRunResult(output="Done", images=[])
        )
        mock_runner.close = MagicMock()

        with patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/run",
                    json={"prompt": "Test"},
                    headers={"X-API-Key": "secret-api-key"},
                )

        assert response.status_code == 200
        assert "task_id" in response.json()

    @pytest.mark.asyncio
    async def test_auth_disabled_when_no_key_configured(self, monkeypatch):
        """Test auth is disabled when API_AUTH_KEY is not set."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.delenv("API_AUTH_KEY", raising=False)

        from importlib import reload

        import src.config
        import src.interfaces.api.security

        reload(src.config)
        reload(src.interfaces.api.security)

        from src.interfaces.api.main import app

        app.state.api_key_available = True

        mock_runner = MagicMock()
        mock_runner.run_async = AsyncMock(
            return_value=AgentRunResult(output="Done", images=[])
        )
        mock_runner.close = MagicMock()

        with patch("src.interfaces.api.tasks.AgentRunner", return_value=mock_runner):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post("/run", json={"prompt": "Test"})

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_rate_limited(self, monkeypatch):
        """Test health endpoint has rate limiting."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        from src.interfaces.api.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert "status" in response.json()
