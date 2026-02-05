"""Tests for command parsing functionality."""

from src.core.commands.parser import ParsedCommand, parse_command


class TestParser:
    """Test suite for command parser."""

    def test_parse_command_basic(self) -> None:
        """Test basic command parsing with input."""
        result = parse_command("!날씨 서울")
        assert result is not None
        assert result.name == "날씨"
        assert result.input == "서울"

    def test_parse_command_no_input(self) -> None:
        """Test command without input."""
        result = parse_command("!help")
        assert result is not None
        assert result.name == "help"
        assert result.input == ""

    def test_parse_command_not_command(self) -> None:
        """Test that regular text returns None."""
        result = parse_command("일반 메시지")
        assert result is None

    def test_parse_command_exclamation_only(self) -> None:
        """Test that lone exclamation mark returns None."""
        result = parse_command("!")
        assert result is None

    def test_parse_command_uppercase(self) -> None:
        """Test that command names are normalized to lowercase."""
        result = parse_command("!HELLO world")
        assert result is not None
        assert result.name == "hello"
        assert result.input == "world"

    def test_parse_command_multiple_spaces(self) -> None:
        """Test that multiple spaces in input are normalized."""
        result = parse_command("!test   extra   spaces")
        assert result is not None
        assert result.name == "test"
        assert result.input == "extra spaces"

    def test_parse_command_leading_trailing_spaces(self) -> None:
        """Test that leading/trailing spaces in input are stripped."""
        result = parse_command("!cmd   input text   ")
        assert result is not None
        assert result.name == "cmd"
        assert result.input == "input text"

    def test_parse_command_korean_name(self) -> None:
        """Test command with Korean name."""
        result = parse_command("!날씨")
        assert result is not None
        assert result.name == "날씨"
        assert result.input == ""

    def test_parse_command_korean_input(self) -> None:
        """Test command with Korean input."""
        result = parse_command("!번역 hello world")
        assert result is not None
        assert result.name == "번역"
        assert result.input == "hello world"

    def test_parse_command_mixed_case(self) -> None:
        """Test mixed case command name normalization."""
        result = parse_command("!HeLLo WoRLd")
        assert result is not None
        assert result.name == "hello"
        assert result.input == "WoRLd"

    def test_parse_command_single_space_separator(self) -> None:
        """Test command with single space separator."""
        result = parse_command("!cmd input")
        assert result is not None
        assert result.name == "cmd"
        assert result.input == "input"

    def test_parse_command_empty_string(self) -> None:
        """Test empty string returns None."""
        result = parse_command("")
        assert result is None

    def test_parse_command_whitespace_only(self) -> None:
        """Test whitespace-only string returns None."""
        result = parse_command("   ")
        assert result is None

    def test_parse_command_exclamation_in_middle(self) -> None:
        """Test that exclamation in middle doesn't trigger parsing."""
        result = parse_command("hello ! world")
        assert result is None

    def test_parse_command_special_characters_in_name(self) -> None:
        """Test command name with special characters."""
        result = parse_command("!cmd-name input")
        assert result is not None
        assert result.name == "cmd-name"
        assert result.input == "input"

    def test_parse_command_numbers_in_name(self) -> None:
        """Test command name with numbers."""
        result = parse_command("!cmd123 input")
        assert result is not None
        assert result.name == "cmd123"
        assert result.input == "input"

    def test_parse_command_underscore_in_name(self) -> None:
        """Test command name with underscore."""
        result = parse_command("!my_cmd input")
        assert result is not None
        assert result.name == "my_cmd"
        assert result.input == "input"

    def test_parse_command_long_input(self) -> None:
        """Test command with long input text."""
        long_input = "this is a very long input text with many words"
        result = parse_command(f"!cmd {long_input}")
        assert result is not None
        assert result.name == "cmd"
        assert result.input == long_input

    def test_parse_command_with_additional_instructions(self) -> None:
        """Test parsing command with comma-separated additional instructions."""
        result = parse_command("!브소개 아디다스, 영어로 답변줘")
        assert result is not None
        assert result.name == "브소개"
        assert result.input == "아디다스"
        assert result.additional_instructions == "영어로 답변줘"

    def test_parse_command_with_additional_instructions_and_period(self) -> None:
        """Test parsing command with additional instructions ending with period."""
        result = parse_command("!브소개 아디다스, 영어로 답변줘.")
        assert result is not None
        assert result.name == "브소개"
        assert result.input == "아디다스"
        assert result.additional_instructions == "영어로 답변줘."

    def test_parse_command_without_additional_instructions(self) -> None:
        """Test parsing command without comma returns empty additional_instructions."""
        result = parse_command("!날씨 서울")
        assert result is not None
        assert result.name == "날씨"
        assert result.input == "서울"
        assert result.additional_instructions == ""

    def test_parse_command_with_spaces_around_comma(self) -> None:
        """Test that spaces around comma are properly normalized."""
        result = parse_command("!cmd input text  ,   extra instructions  ")
        assert result is not None
        assert result.name == "cmd"
        assert result.input == "input text"
        assert result.additional_instructions == "extra instructions"

    def test_parse_command_comma_only_in_input(self) -> None:
        """Test command with comma but no text after it."""
        result = parse_command("!cmd input,")
        assert result is not None
        assert result.name == "cmd"
        assert result.input == "input"
        assert result.additional_instructions == ""

    def test_parse_command_multiple_commas(self) -> None:
        """Test that only first comma separates input from additional instructions."""
        result = parse_command("!cmd input, instruction one, instruction two")
        assert result is not None
        assert result.name == "cmd"
        assert result.input == "input"
        assert result.additional_instructions == "instruction one, instruction two"


class TestCommand:
    """Test suite for Command dataclass."""

    def test_command_creation(self) -> None:
        """Test creating a Command instance with all fields."""
        from datetime import datetime

        from src.core.commands.models import Command

        now = datetime.now()
        cmd = Command(
            id=1,
            name="test-command",
            prompt="Test prompt text",
            original_prompt="Original prompt",
            recommended_tools=["tool1", "tool2"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        assert cmd.id == 1
        assert cmd.name == "test-command"
        assert cmd.prompt == "Test prompt text"
        assert cmd.original_prompt == "Original prompt"
        assert cmd.recommended_tools == ["tool1", "tool2"]
        assert cmd.created_by == "slack:U123456"
        assert cmd.created_at == now
        assert cmd.updated_at == now

    def test_command_with_empty_tools(self) -> None:
        """Test Command with empty recommended_tools list."""
        from datetime import datetime

        from src.core.commands.models import Command

        now = datetime.now()
        cmd = Command(
            id=1,
            name="simple-cmd",
            prompt="Simple prompt",
            original_prompt="Original",
            recommended_tools=[],
            created_by="api:user@example.com",
            created_at=now,
            updated_at=now,
        )

        assert cmd.recommended_tools == []


class TestRepository:
    """Test suite for CommandRepository class."""

    def test_table_auto_created(self, tmp_path) -> None:
        """Test that table is auto-created on initialization."""
        import sqlite3

        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        # Verify table exists
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='commands'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "commands"

    def test_create_command(self, tmp_path) -> None:
        """Test creating a command (INSERT)."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,  # Will be assigned by DB
            name="test-cmd",
            prompt="Test prompt",
            original_prompt="Original",
            recommended_tools=["tool1", "tool2"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        created = repo.create(cmd)

        assert created.id > 0  # ID should be assigned
        assert created.name == "test-cmd"
        assert created.prompt == "Test prompt"
        assert created.recommended_tools == ["tool1", "tool2"]

    def test_create_normalizes_name_to_lowercase(self, tmp_path) -> None:
        """Test that command name is normalized to lowercase."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="TEST-CMD",  # Uppercase
            prompt="Test prompt",
            original_prompt="Original",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        created = repo.create(cmd)

        assert created.name == "test-cmd"  # Should be lowercase

    def test_get_by_name(self, tmp_path) -> None:
        """Test getting a command by name (SELECT)."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="my-command",
            prompt="My prompt",
            original_prompt="Original",
            recommended_tools=["search"],
            created_by="api:user@test.com",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        retrieved = repo.get_by_name("my-command")

        assert retrieved is not None
        assert retrieved.name == "my-command"
        assert retrieved.prompt == "My prompt"
        assert retrieved.recommended_tools == ["search"]

    def test_get_by_name_case_insensitive(self, tmp_path) -> None:
        """Test that get_by_name is case-insensitive."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="my-command",
            prompt="My prompt",
            original_prompt="Original",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        # Should find with uppercase search
        retrieved = repo.get_by_name("MY-COMMAND")

        assert retrieved is not None
        assert retrieved.name == "my-command"

    def test_get_by_name_not_found(self, tmp_path) -> None:
        """Test get_by_name returns None when not found."""
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        retrieved = repo.get_by_name("nonexistent")

        assert retrieved is None

    def test_list_all(self, tmp_path) -> None:
        """Test listing all commands (SELECT ALL)."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        for name in ["cmd1", "cmd2", "cmd3"]:
            cmd = Command(
                id=0,
                name=name,
                prompt=f"Prompt for {name}",
                original_prompt="Original",
                recommended_tools=[],
                created_by="slack:U123456",
                created_at=now,
                updated_at=now,
            )
            repo.create(cmd)

        commands = repo.list_all()

        assert len(commands) == 3
        names = [c.name for c in commands]
        assert "cmd1" in names
        assert "cmd2" in names
        assert "cmd3" in names

    def test_list_all_empty(self, tmp_path) -> None:
        """Test list_all returns empty list when no commands."""
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        commands = repo.list_all()

        assert commands == []

    def test_update_command(self, tmp_path) -> None:
        """Test updating a command (UPDATE)."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="update-test",
            prompt="Original prompt",
            original_prompt="Original",
            recommended_tools=["tool1"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        created = repo.create(cmd)

        # Update the command
        created.prompt = "Updated prompt"
        created.recommended_tools = ["tool1", "tool2", "tool3"]
        updated = repo.update(created)

        assert updated.prompt == "Updated prompt"
        assert updated.recommended_tools == ["tool1", "tool2", "tool3"]

        # Verify persistence
        retrieved = repo.get_by_name("update-test")
        assert retrieved is not None
        assert retrieved.prompt == "Updated prompt"

    def test_delete_command(self, tmp_path) -> None:
        """Test deleting a command (DELETE)."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="delete-test",
            prompt="To be deleted",
            original_prompt="Original",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        result = repo.delete("delete-test")

        assert result is True
        assert repo.get_by_name("delete-test") is None

    def test_delete_case_insensitive(self, tmp_path) -> None:
        """Test that delete is case-insensitive."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="delete-me",
            prompt="To be deleted",
            original_prompt="Original",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        result = repo.delete("DELETE-ME")  # Uppercase

        assert result is True
        assert repo.get_by_name("delete-me") is None

    def test_delete_nonexistent(self, tmp_path) -> None:
        """Test delete returns False for nonexistent command."""
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        result = repo.delete("nonexistent")

        assert result is False

    def test_recommended_tools_json_serialization(self, tmp_path) -> None:
        """Test that recommended_tools is properly serialized/deserialized as JSON."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        tools = ["search", "calculator", "web_scraper"]
        cmd = Command(
            id=0,
            name="json-test",
            prompt="Test JSON",
            original_prompt="Original",
            recommended_tools=tools,
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        retrieved = repo.get_by_name("json-test")

        assert retrieved is not None
        assert retrieved.recommended_tools == tools
        assert isinstance(retrieved.recommended_tools, list)

    def test_data_directory_auto_created(self) -> None:
        """Test that data directory is auto-created if not exists."""
        import os
        import shutil

        from src.core.commands.repository import CommandRepository

        test_dir = "test_data_auto_create"
        db_path = f"{test_dir}/commands.db"

        try:
            # Ensure directory doesn't exist
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

            repo = CommandRepository(db_path=db_path)

            assert os.path.exists(test_dir)
            assert os.path.exists(db_path)
        finally:
            # Cleanup
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

    def test_wal_mode_enabled(self, tmp_path) -> None:
        """Test that WAL mode is enabled for SQLite."""
        import sqlite3

        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        conn.close()

        assert result[0].lower() == "wal"


class TestPromptBuilder:
    """Test suite for build_command_prompt function."""

    def test_build_command_prompt_basic(self) -> None:
        """Test basic prompt building with input substitution."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="weather",
            prompt="Get weather for {input}",
            original_prompt="weather for {input}",
            recommended_tools=["weather_api"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(cmd, "Seoul", "slack:U123456")

        assert "Get weather for Seoul" in result
        assert "slack:U123456" in result

    def test_build_command_prompt_with_tools(self) -> None:
        """Test that recommended tools are included in prompt."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="search",
            prompt="Search for {input}",
            original_prompt="search {input}",
            recommended_tools=["web_search", "calculator"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(cmd, "Python tutorials", "slack:U123456")

        assert "Search for Python tutorials" in result
        assert "web_search" in result
        assert "calculator" in result

    def test_build_command_prompt_no_input_placeholder(self) -> None:
        """Test prompt without {input} placeholder."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="help",
            prompt="Show help information",
            original_prompt="help",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(cmd, "", "slack:U123456")

        assert "Show help information" in result
        assert "slack:U123456" in result

    def test_build_command_prompt_empty_tools(self) -> None:
        """Test prompt with empty recommended_tools list."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="echo",
            prompt="Echo: {input}",
            original_prompt="echo {input}",
            recommended_tools=[],
            created_by="api:user@test.com",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(cmd, "hello world", "api:user@test.com")

        assert "Echo: hello world" in result
        assert "api:user@test.com" in result

    def test_build_command_prompt_multiple_placeholders(self) -> None:
        """Test prompt with multiple {input} placeholders."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="repeat",
            prompt="First: {input}, Second: {input}",
            original_prompt="repeat {input}",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(cmd, "test", "slack:U123456")

        assert "First: test, Second: test" in result

    def test_build_command_prompt_with_additional_instructions(self) -> None:
        """Test that additional instructions are included in prompt."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="브소개",
            prompt="브랜드 {input}에 대해 소개해줘",
            original_prompt="브랜드 소개",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(
            cmd, "아디다스", "slack:U123456", "영어로 답변해줘"
        )

        assert "브랜드 아디다스에 대해 소개해줘" in result
        assert "[Additional Instructions from User]" in result
        assert "영어로 답변해줘" in result

    def test_build_command_prompt_without_additional_instructions(self) -> None:
        """Test that additional instructions section is omitted when empty."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.prompts import build_command_prompt

        now = datetime.now()
        cmd = Command(
            id=1,
            name="test",
            prompt="Test {input}",
            original_prompt="test",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )

        result = build_command_prompt(cmd, "input", "slack:U123456", "")

        assert "Test input" in result
        assert "[Additional Instructions from User]" not in result


class TestExecutor:
    """Test suite for CommandExecutor class."""

    def test_executor_execute_existing_command(self, tmp_path) -> None:
        """Test executing an existing command."""
        from datetime import datetime

        from src.core.commands.executor import CommandExecutor
        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="weather",
            prompt="Get weather for {input}",
            original_prompt="weather {input}",
            recommended_tools=["weather_api"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        executor = CommandExecutor(repository=repo)
        parsed = ParsedCommand(name="weather", input="Seoul")

        result = executor.execute(parsed, "slack:U999999")

        assert result is not None
        assert "Get weather for Seoul" in result
        assert "slack:U999999" in result

    def test_executor_execute_nonexistent_command(self, tmp_path) -> None:
        """Test executing a nonexistent command returns None."""
        from src.core.commands.executor import CommandExecutor
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        executor = CommandExecutor(repository=repo)
        parsed = ParsedCommand(name="nonexistent", input="test")

        result = executor.execute(parsed, "slack:U123456")

        assert result is None

    def test_executor_execute_case_insensitive(self, tmp_path) -> None:
        """Test that executor lookup is case-insensitive."""
        from datetime import datetime

        from src.core.commands.executor import CommandExecutor
        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="hello",
            prompt="Hello {input}!",
            original_prompt="hello {input}",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        executor = CommandExecutor(repository=repo)
        parsed = ParsedCommand(name="HELLO", input="World")

        result = executor.execute(parsed, "slack:U123456")

        assert result is not None
        assert "Hello World!" in result

    def test_executor_execute_with_empty_input(self, tmp_path) -> None:
        """Test executing command with empty input."""
        from datetime import datetime

        from src.core.commands.executor import CommandExecutor
        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="help",
            prompt="Show help",
            original_prompt="help",
            recommended_tools=["help_tool"],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        executor = CommandExecutor(repository=repo)
        parsed = ParsedCommand(name="help", input="")

        result = executor.execute(parsed, "slack:U123456")

        assert result is not None
        assert "Show help" in result

    def test_executor_execute_with_additional_instructions(self, tmp_path) -> None:
        """Test executing command passes additional instructions to prompt builder."""
        from datetime import datetime

        from src.core.commands.executor import CommandExecutor
        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository

        db_path = tmp_path / "test.db"
        repo = CommandRepository(db_path=str(db_path))

        now = datetime.now()
        cmd = Command(
            id=0,
            name="브소개",
            prompt="브랜드 {input}에 대해 소개해줘",
            original_prompt="브랜드 소개",
            recommended_tools=[],
            created_by="slack:U123456",
            created_at=now,
            updated_at=now,
        )
        repo.create(cmd)

        executor = CommandExecutor(repository=repo)
        parsed = ParsedCommand(
            name="브소개", input="아디다스", additional_instructions="영어로 답변해줘"
        )

        result = executor.execute(parsed, "slack:U123456")

        assert result is not None
        assert "브랜드 아디다스에 대해 소개해줘" in result
        assert "[Additional Instructions from User]" in result
        assert "영어로 답변해줘" in result


class TestTools:
    """Test suite for command CRUD tools."""

    def test_create_command_basic(self, tmp_path, mocker) -> None:
        """Test creating a command with AI enhancement."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import create_command

        # Mock repository
        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch(
            "src.core.commands.tools.get_repository",
            return_value=repo,
        )

        # Mock AI calls
        mocker.patch(
            "src.core.commands.tools._enhance_prompt",
            return_value="Enhanced: Test prompt",
        )
        mocker.patch(
            "src.core.commands.tools._recommend_tools",
            return_value=["exa_search", "send_email"],
        )

        result = create_command("test-cmd", "Test prompt", "slack:U123456")

        assert "test-cmd" in result
        assert "created" in result.lower() or "success" in result.lower()

    def test_create_command_stores_original_prompt(self, tmp_path, mocker) -> None:
        """Test that create_command stores both original and enhanced prompt."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import create_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)
        mocker.patch(
            "src.core.commands.tools._enhance_prompt",
            return_value="Enhanced prompt text",
        )
        mocker.patch(
            "src.core.commands.tools._recommend_tools",
            return_value=["exa_search"],
        )

        create_command("orig-test", "Original text", "slack:U123456")

        cmd = repo.get_by_name("orig-test")
        assert cmd is not None
        assert cmd.original_prompt == "Original text"
        assert cmd.prompt == "Enhanced prompt text"

    def test_create_command_stores_recommended_tools(self, tmp_path, mocker) -> None:
        """Test that create_command stores recommended tools."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import create_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)
        mocker.patch(
            "src.core.commands.tools._enhance_prompt",
            return_value="Enhanced",
        )
        mocker.patch(
            "src.core.commands.tools._recommend_tools",
            return_value=["exa_search", "send_email"],
        )

        create_command("tools-test", "Search and email", "slack:U123456")

        cmd = repo.get_by_name("tools-test")
        assert cmd is not None
        assert cmd.recommended_tools == ["exa_search", "send_email"]

    def test_list_commands(self, tmp_path, mocker) -> None:
        """Test listing all commands."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import list_commands

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        # Create test commands
        now = datetime.now()
        for name in ["cmd1", "cmd2", "cmd3"]:
            repo.create(
                Command(
                    id=0,
                    name=name,
                    prompt=f"Prompt {name}",
                    original_prompt=f"Original {name}",
                    recommended_tools=[],
                    created_by="slack:U123456",
                    created_at=now,
                    updated_at=now,
                )
            )

        result = list_commands()

        assert "cmd1" in result
        assert "cmd2" in result
        assert "cmd3" in result

    def test_list_commands_empty(self, tmp_path, mocker) -> None:
        """Test listing commands when none exist."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import list_commands

        db_path = tmp_path / "empty_test.db"
        repo = CommandRepository(db_path=str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        result = list_commands()

        assert (
            "no commands" in result.lower()
            or "empty" in result.lower()
            or "0" in result
        )

    def test_get_command(self, tmp_path, mocker) -> None:
        """Test getting a specific command."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import get_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="my-cmd",
                prompt="My enhanced prompt",
                original_prompt="My original",
                recommended_tools=["exa_search"],
                created_by="slack:U123456",
                created_at=now,
                updated_at=now,
            )
        )

        result = get_command("my-cmd")

        assert "my-cmd" in result
        assert "My enhanced prompt" in result or "prompt" in result.lower()
        assert "exa_search" in result

    def test_get_command_not_found(self, tmp_path, mocker) -> None:
        """Test getting a nonexistent command."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import get_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        result = get_command("nonexistent")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_update_command_with_permission(self, tmp_path, mocker) -> None:
        """Test updating a command with correct permission."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import update_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)
        mocker.patch(
            "src.core.commands.tools._enhance_prompt",
            return_value="Updated enhanced prompt",
        )
        mocker.patch(
            "src.core.commands.tools._recommend_tools",
            return_value=["send_email"],
        )

        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="update-test",
                prompt="Original enhanced",
                original_prompt="Original",
                recommended_tools=["exa_search"],
                created_by="slack:U123456",
                created_at=now,
                updated_at=now,
            )
        )

        result = update_command("update-test", "New prompt", "slack:U123456")

        assert "updated" in result.lower() or "success" in result.lower()

        cmd = repo.get_by_name("update-test")
        assert cmd is not None
        assert cmd.prompt == "Updated enhanced prompt"

    def test_update_command_permission_denied(self, tmp_path, mocker) -> None:
        """Test updating a command without permission."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import update_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="protected-cmd",
                prompt="Protected prompt",
                original_prompt="Original",
                recommended_tools=[],
                created_by="slack:U123456",  # Created by user U123456
                created_at=now,
                updated_at=now,
            )
        )

        # Try to update with different user
        result = update_command("protected-cmd", "New prompt", "slack:U999999")

        assert (
            "permission" in result.lower()
            or "denied" in result.lower()
            or "not allowed" in result.lower()
        )

        # Verify command was not changed
        cmd = repo.get_by_name("protected-cmd")
        assert cmd is not None
        assert cmd.prompt == "Protected prompt"

    def test_update_command_not_found(self, tmp_path, mocker) -> None:
        """Test updating a nonexistent command."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import update_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        result = update_command("nonexistent", "New prompt", "slack:U123456")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_delete_command_with_permission(self, tmp_path, mocker) -> None:
        """Test deleting a command with correct permission."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import delete_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="delete-test",
                prompt="To be deleted",
                original_prompt="Original",
                recommended_tools=[],
                created_by="slack:U123456",
                created_at=now,
                updated_at=now,
            )
        )

        result = delete_command("delete-test", "slack:U123456")

        assert "deleted" in result.lower() or "success" in result.lower()
        assert repo.get_by_name("delete-test") is None

    def test_delete_command_permission_denied(self, tmp_path, mocker) -> None:
        """Test deleting a command without permission."""
        from datetime import datetime

        from src.core.commands.models import Command
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import delete_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        now = datetime.now()
        repo.create(
            Command(
                id=0,
                name="protected-delete",
                prompt="Protected",
                original_prompt="Original",
                recommended_tools=[],
                created_by="slack:U123456",
                created_at=now,
                updated_at=now,
            )
        )

        # Try to delete with different user
        result = delete_command("protected-delete", "slack:U999999")

        assert (
            "permission" in result.lower()
            or "denied" in result.lower()
            or "not allowed" in result.lower()
        )

        # Verify command still exists
        assert repo.get_by_name("protected-delete") is not None

    def test_delete_command_not_found(self, tmp_path, mocker) -> None:
        """Test deleting a nonexistent command."""
        from src.core.commands.repository import CommandRepository
        from src.core.commands.tools import delete_command

        db_path = tmp_path / "test.db"
        repo = CommandRepository(str(db_path))
        mocker.patch("src.core.commands.tools.get_repository", return_value=repo)

        result = delete_command("nonexistent", "slack:U123456")

        assert "not found" in result.lower() or "error" in result.lower()
