# AGENTS.md - Tool Creation & Style Guide

This guide explains how to create tools for the Pydantic AI-based personal AI agent and follow consistent code style.

> **For Claude Code users:** See [CLAUDE.md](./CLAUDE.md) for quick reference and MCP documentation.

## Response Guidelines

- **답변 언어**: 항상 한국어로 응답
- **답변 스타일**: 핵심만 요약해서 간결하게
- **Git 컨벤션**: [docs/GIT_CONVENTIONS.md](./docs/GIT_CONVENTIONS.md) 참조

---

## Tool Architecture

Tools are **plain Python functions** registered with Pydantic AI's `FunctionToolset`.

```
src/
├── config.py             # pydantic-settings 기반 Settings 클래스
├── interfaces/           # Entry points
│   ├── slack/           # Slack bot integration (모듈화됨)
│   │   ├── bot.py       # 이벤트 라우터 (127줄)
│   │   ├── handlers.py  # 이벤트 핸들러
│   │   ├── context.py   # 스레드/채널 컨텍스트
│   │   ├── images.py    # 이미지 처리
│   │   ├── progress.py  # 진행 상태 포맷팅
│   │   └── slack_api.py # Slack API 유틸리티
│   └── api/             # FastAPI REST API
│       ├── main.py      # FastAPI app
│       ├── security.py  # API 키 인증 + Rate Limiting
│       ├── schemas.py   # Pydantic 요청/응답 모델
│       ├── tasks.py     # 백그라운드 작업 + 웹훅
│       └── task_repository.py # SQLite 작업 영속성
├── middleware/          # Cross-cutting concerns
│   ├── guardrails/      # Security guardrails
│   │   ├── core.py      # Generic guardrail framework (서버 규칙 집계)
│   │   └── enforcer.py  # 모든 도구 유형 보호 (Defense in Depth)
│   ├── preprocessing/   # 요청 전처리
│   │   └── __init__.py  # preprocess_command(), core 모듈 re-export
│   └── postprocessing/  # 응답 후처리 (최소화)
├── core/                # Core business logic
│   ├── agent/           # AgentRunner, AgentFactory
│   │   ├── core.py      # Backward-compat re-exports
│   │   ├── utils.py     # AgentRunResult, retry, image normalization
│   │   ├── factory.py   # AgentFactory (isolated agent 생성)
│   │   └── runner.py    # AgentRunner (run/run_async + 이미지 추출)
│   ├── context/         # 요청 컨텍스트 관리 (ContextVar)
│   │   └── image.py     # 첨부 이미지 컨텍스트 + bounded LRU 캐시
│   ├── scheduler/       # Task scheduling system
│   ├── commands/        # Command system
│   ├── lifecycle.py     # 싱글톤 라이프사이클 관리
│   └── memory/          # Memory/graph system
├── tools/               # Tool definitions
│   ├── catalog.py       # 통합 ToolCatalog
│   ├── mcp_registry.py  # MCPServerConfig, ServerGuardrailRules, register_mcp_server()
│   ├── mcp_client.py    # MCPManager (다중 MCP 서버 연결)
│   ├── mcp/             # MCP server definitions (register_mcp_server, gitignored)
│   ├── custom/          # Custom tools (@register_tool, gitignored)
│   └── registry.py      # Tool registration
└── utils/               # Utilities
    ├── logging.py       # 구조화 로깅 (JSON + request_id)
    ├── observability.py # Logfire 통합
    ├── image_handler.py # ImageData, extract_images_from_result()
    ├── slack_files.py   # Slack 파일 다운로드/업로드 유틸리티
    └── slack_formatter.py # Markdown → Slack mrkdwn 변환
```

### Core Scheduler Components

```
src/core/scheduler/
├── __init__.py           # SchedulerManager, parse_korean_time
├── models.py             # ScheduledTask dataclass
├── time_parser.py        # Korean/English time parser
├── manager.py            # APScheduler + SQLite
├── executor.py           # Task execution + Slack notify
└── tools.py              # schedule_task, list_scheduled_tasks, cancel_scheduled_task
```

### How Tool Registration Works

Tools use the `@register_tool` decorator for automatic registration:

```python
# src/tools/custom/my_tool.py
from src.tools.registry import register_tool

@register_tool
def my_function(param: str) -> str:
    """My tool description.

    Args:
        param: Parameter description.

    Returns:
        Result string.
    """
    return f"Result: {param}"
```

**No manual registration needed!** The decorator handles everything.

Under the hood:
1. `@register_tool` registers the function name in `_registered_tools` set
2. `auto_register_tools()` scans `src/tools/custom/` and imports all modules
3. `is_tool_function()` checks if a function is registered via the decorator
4. `AgentFactory` creates a fresh toolset with all custom, command, and scheduler tools

---

## Tool Creation Guide

### Pattern: Plain Python Function

All tools are plain functions with type hints, docstrings, and `@register_tool`:

```python
# src/tools/custom/calculator.py
from src.tools.registry import register_tool

@register_tool
def calculate_sum(a: float, b: float) -> str:
    """Calculate the sum of two numbers.

    Args:
        a: First number to add.
        b: Second number to add.

    Returns:
        Result as a formatted string.
    """
    return f"Result: {a + b}"
```

**That's it!** No need to modify `__init__.py` - the decorator handles registration.

### Environment Variable Access

**도구(tools)와 코어(core)에서 환경변수 접근 방식이 다릅니다:**

| 위치 | 방식 | 이유 |
|------|------|------|
| `src/tools/custom/` | `os.getenv("MY_API_KEY")` | 도구 설치 시 `.env`만 수정하면 됨 |
| `src/core/`, `src/interfaces/` | `from src.config import settings` | 타입 안전성, 중앙 관리 |

**도구에서 환경변수 사용 예시:**
```python
import os

def _get_api_key() -> str:
    key = os.getenv("MY_API_KEY")
    if not key:
        raise ValueError("MY_API_KEY 환경변수를 설정하세요.")
    return key
```

**새 도구 추가 시:** `.env`에 환경변수만 추가하면 됩니다. `config.py` 수정 불필요.

### Pattern: Tool with External API

For tools needing API clients or configuration:

```python
# src/tools/custom/weather.py
import os
from typing import Optional

from src.tools.registry import register_tool

# Lazy client initialization
_client: Optional[WeatherClient] = None

def _get_client() -> WeatherClient:
    """Get or initialize the client."""
    global _client
    if _client is None:
        api_key = os.getenv("WEATHER_API_KEY")
        if not api_key:
            raise ValueError("WEATHER_API_KEY environment variable required")
        _client = WeatherClient(api_key=api_key)
    return _client

@register_tool
def get_weather(location: str, units: str = "celsius") -> str:
    """Get current weather for a location.

    Args:
        location: City name (e.g., 'Seoul, Korea').
        units: Temperature units: 'celsius' or 'fahrenheit'.

    Returns:
        Weather information string.
    """
    try:
        client = _get_client()
        data = client.fetch(location, units)
        return f"Weather in {location}: {data.temp}°, {data.condition}"
    except ValueError as e:
        return f"Configuration error: {str(e)}"
    except Exception as e:
        return f"Error fetching weather: {str(e)}"
```

---

## Style Guide

### Naming Conventions

**Functions and variables:** `snake_case`
```python
def calculate_total_price(items: list) -> float:
    total_amount = sum(item.price for item in items)
    return total_amount
```

**Classes:** `PascalCase`
```python
class CommandExecutor:
    pass
```

**Constants:** `UPPER_SNAKE_CASE`
```python
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
```

### Type Hints (Required)

**ALL** function parameters and return values MUST have type hints:

```python
# Good
def process_data(input_text: str, max_length: int = 100) -> dict[str, any]:
    return {"result": input_text[:max_length]}

# Bad (missing type hints)
def process_data(input_text, max_length=100):
    return {"result": input_text[:max_length]}
```

### Docstrings (Google Style)

All functions MUST have docstrings:

```python
def fetch_user_data(user_id: str, include_history: bool = False) -> dict:
    """Fetch user data from the database.

    This function retrieves user information and optionally includes
    their action history.

    Args:
        user_id: Unique identifier for the user.
        include_history: Whether to include user's action history.

    Returns:
        Dictionary containing user data with keys:
        - name: User's full name
        - email: User's email address
        - history: List of actions (if include_history=True)

    Raises:
        ValueError: If user_id is empty or invalid.
        DatabaseError: If database connection fails.
    """
    pass
```

### Import Organization

Organize imports in three groups:

```python
# 1. Standard library
import os
import sys
from datetime import datetime
from pathlib import Path

# 2. Third-party packages
import httpx
from pydantic_ai import Agent, FunctionToolset

# 3. Local imports
from src.core.agent import AgentRunner
from src.tools import get_toolset
```

### Linting & Formatting (Ruff)

프로젝트는 [Ruff](https://docs.astral.sh/ruff/)를 사용하여 코드 스타일을 자동으로 검사하고 포맷팅합니다.

```bash
# Lint 검사 + 자동 수정
uv run ruff check src/ tests/ --fix

# 코드 포맷팅
uv run ruff format src/ tests/
```

**Ruff가 검사하는 항목:**
- PEP 8 스타일 (E, W)
- 논리적 오류 (F - Pyflakes)
- Import 정렬 (I - isort)
- 버그 패턴 (B - flake8-bugbear)
- 코드 단순화 (SIM - flake8-simplify)
- Python 최신 문법 (UP - pyupgrade)

### Pre-commit Hooks

Git 커밋 전에 자동으로 코드 품질을 검사합니다.

```bash
# Hook 설치 (최초 1회)
uv run pre-commit install

# 수동 실행 (모든 파일)
uv run pre-commit run --all-files
```

**커밋 시 자동 실행되는 검사:**
- `ruff` - Lint 검사 + 자동 수정
- `ruff-format` - 코드 포맷팅
- `trailing-whitespace` - 줄 끝 공백 제거
- `end-of-file-fixer` - 파일 끝 개행 추가
- `check-yaml/json/toml` - 설정 파일 문법 검사
- `debug-statements` - print/debugger 문 감지
- `detect-private-key` - 비밀키 노출 방지

**Hook 실패 시:**
```bash
# 1. ruff가 자동으로 수정한 파일 확인
git diff

# 2. 변경 사항 스테이징
git add -A

# 3. 다시 커밋
git commit -m "Your message"
```

---

## Testing Guide

### Basic Test with pytest

```python
# tests/test_calculator.py
import pytest
from src.tools.calculator import calculate_sum

def test_calculate_sum():
    """Test basic addition."""
    result = calculate_sum(2.0, 3.0)
    assert result == "Result: 5.0"

def test_calculate_sum_negative():
    """Test addition with negative numbers."""
    result = calculate_sum(-5.0, 3.0)
    assert result == "Result: -2.0"
```

### Async Test with pytest-asyncio

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient
from src.interfaces.api import app

@pytest.mark.asyncio
async def test_run_endpoint():
    """Test the /run endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/run",
            json={"prompt": "Hello, agent!"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
```

### Mocking with pytest-mock

```python
# tests/test_agent_core.py
import pytest
from src.core.agent import AgentRunner

def test_agent_runner_with_mock(mocker):
    """Test AgentRunner with mocked model."""
    # Mock the pydantic-ai Agent
    mock_agent = mocker.Mock()
    mock_agent.run.return_value = mocker.Mock(output="Mocked response")

    mocker.patch('src.core.agent.Agent', return_value=mock_agent)

    runner = AgentRunner()
    result = runner.run("Test prompt")

    assert "Mocked" in result.output
```

### Test File Organization

```
tests/
├── __init__.py
├── conftest.py                # Shared fixtures
├── test_agent_core.py         # AgentRunner tests
├── test_api.py                # FastAPI endpoint tests
├── test_commands.py           # Command system tests
├── test_guardrails.py         # Security guardrails tests
├── test_image_handler.py      # Image extraction utility tests
├── test_integration.py        # End-to-end tests
├── test_mcp_registry.py       # MCP server registration tests
├── test_memory.py             # Memory system tests
├── test_message_processing.py # Message processing tests
├── test_playwright_cleanup.py # Playwright cleanup tests
├── test_scheduler.py          # Scheduler manager and tools tests
├── test_slack_bot.py          # Slack integration tests
├── test_slack_formatter.py    # Slack formatting tests
├── test_time_parser.py        # Korean/English time parser tests
└── tools/                     # 커스텀 도구 테스트 (gitignored)
    ├── __init__.py
    └── test_*.py              # 각 커스텀 도구의 테스트 파일
```

> **Note**: `tests/tools/`는 `src/tools/custom/`과 마찬가지로 `.gitignore`에 의해 배포되지 않습니다.
> 커스텀 도구 테스트는 `make test-all`로 실행하고, `make test`는 코어 테스트만 실행합니다.

---

## Request Processing Workflow

AI 에이전트가 이 프로젝트에서 코드 작업을 수행할 때 따라야 하는 표준 워크플로우입니다.

### Phase 1: Discovery (문서 확인)

**ALWAYS** 작업 전 관련 문서를 먼저 확인하세요.

```bash
# 1. docs/ 디렉토리 확인
ls docs/

# 2. 작업 유형에 맞는 가이드 읽기
cat docs/TOOL_CREATION_GUIDE.md      # 새 도구 생성
cat docs/MCP_INTEGRATION_GUIDE.md    # MCP 서버 통합
cat docs/DEVELOPMENT_WORKFLOW.md     # 개발 프로세스

# 3. 기존 코드 패턴 파악
cat src/tools/custom/exa_search.py   # 외부 API 도구 예시
cat src/tools/custom/email_sender.py # 간단한 도구 예시
```

| 작업 유형 | 확인할 문서 | 참고 코드 |
|---------|-----------|----------|
| 새 도구 생성 | `docs/TOOL_CREATION_GUIDE.md` | `src/tools/custom/*.py` |
| MCP 통합 | `docs/MCP_INTEGRATION_GUIDE.md` | `src/tools/mcp/` |
| API 엔드포인트 | README.md | `src/interfaces/api/` |
| Slack 기능 | README.md | `src/interfaces/slack/` |
| 테스트 작성 | 이 문서 Testing Guide | `tests/test_*.py` |

### Phase 2: Analysis & Planning (분석 및 계획)

복잡한 작업은 구현 전에 분석하세요.

**분석 체크리스트:**
```markdown
## 요청 분석
- [ ] 무엇을 해야 하는가? (명확한 목표)
- [ ] 영향 받는 파일은? (수정 범위)
- [ ] 기존 패턴과 일치하는가? (코드 스타일)
- [ ] 의존성이 필요한가? (pyproject.toml)
- [ ] 환경 변수가 필요한가? (.env.example)
- [ ] 테스트가 필요한가? (거의 항상 Yes)
```

**작업 분해 예시:**
```markdown
## "이메일 발송 도구 추가" 분해

1. src/tools/custom/email_sender.py 생성
2. @register_tool 데코레이터로 함수 정의
3. tests/test_email_sender.py 테스트 작성
4. .env.example에 EMAIL_API_KEY 추가
5. AGENTS.md Tool Architecture 업데이트
6. README.md 환경 변수 테이블 업데이트
```

### Phase 3: Implementation (구현)

**TODO 생성 후 순차 실행:**

```markdown
- [ ] Step 1: 핵심 기능 구현
- [ ] Step 2: 에러 처리 추가
- [ ] Step 3: 테스트 작성
- [ ] Step 4: 린트 수정
- [ ] Step 5: 문서 업데이트
```

**구현 규칙:**
- 타입 힌트 **필수** (모든 파라미터, 반환값)
- Google 스타일 docstring **필수**
- 환경변수: `os.getenv("MY_API_KEY")` 사용 (.env에만 추가하면 됨)
- 에러 메시지는 사용자 친화적으로

### Phase 4: Verification (검증)

**ALWAYS** 변경 후 검증을 수행하세요.

```bash
# 1. 코어 테스트
uv run pytest tests/ --ignore=tests/tools -v

# 2. 전체 테스트 (커스텀 도구 포함)
uv run pytest tests/ -v

# 3. 특정 테스트 함수만
uv run pytest tests/test_<module>.py::test_function_name -v

# 4. 커스텀 도구 테스트만
uv run pytest tests/tools/ -v
```

**테스트 필수 케이스:**
- Happy path (정상 동작)
- Error handling (예외 상황)
- Edge cases (경계 조건)

### Phase 5: Lint Check (코드 스타일)

**ALWAYS** 커밋 전 린트 검사:

```bash
# Lint 검사 + 자동 수정
uv run ruff check src/ tests/ --fix

# 코드 포맷팅
uv run ruff format src/ tests/

# pre-commit (커밋 시 자동 실행)
uv run pre-commit run --all-files
```

**자주 발생하는 린트 에러:**
| 에러 코드 | 의미 | 해결 |
|---------|-----|-----|
| E501 | 줄 길이 초과 | 줄 분리 |
| F401 | 미사용 import | import 제거 |
| F841 | 미사용 변수 | 변수 제거 또는 `_` prefix |
| I001 | import 정렬 | `--fix`로 자동 수정 |

### Phase 6: Documentation Update (문서 업데이트)

코드 변경 시 **반드시** 관련 문서도 업데이트:

| 변경 유형 | 업데이트 대상 |
|---------|-------------|
| 새 도구 추가 | 도구 파일 + `.env`만 (다른 파일 수정 금지, 테스트는 `tests/tools/`) |
| 새 환경 변수 (코어) | `CLAUDE.md`, `README.md`, `.env.example` |
| 새 테스트 파일 | `AGENTS.md` (Test File Organization) |
| 아키텍처 변경 | `CLAUDE.md`, `README.md`, `AGENTS.md` 모두 |
| 새 docs/ 가이드 | `CLAUDE.md` (docs/ 섹션) |
| API 변경 | `README.md` (엔드포인트 섹션) |

**문서 업데이트 체크리스트:**
```markdown
□ AGENTS.md - Tool Architecture 트리 업데이트됨
□ AGENTS.md - Test File Organization 업데이트됨
□ CLAUDE.md - 환경 변수/Gotchas 업데이트됨
□ README.md - 기능/환경 변수 업데이트됨
□ .env.example - 새 환경 변수 추가됨
□ Last Updated 날짜 변경됨
```

### Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│ 1. DISCOVERY: docs/ 확인 → 기존 패턴 파악                     │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. ANALYSIS: 요청 분석 → 작업 분해 → TODO 생성               │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. IMPLEMENTATION: TODO 순차 실행 → 코드 작성                │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. VERIFICATION: pytest 실행 → 테스트 통과 확인              │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. LINT: ruff check/format → 스타일 검사                    │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. DOCUMENTATION: 관련 문서 모두 업데이트                     │
└─────────────────────────────────────────────────────────────┘
```

### Quick Checklist (빠른 체크리스트)

작업 완료 전 확인:

```markdown
□ 1. docs/ 문서를 확인했는가?
□ 2. 기존 코드 패턴을 따랐는가?
□ 3. 타입 힌트와 docstring을 작성했는가?
□ 4. 테스트를 작성하고 통과했는가?
□ 5. ruff check/format을 실행했는가?
□ 6. 관련 문서를 모두 업데이트했는가?
□ 7. .env.example에 새 환경 변수를 추가했는가? (해당 시)
```

---

## Quick Reference

### Tool Creation Checklist

- [ ] **도구 파일 하나만 수정** (다른 파일 수정 금지!)
- [ ] **환경변수는 `os.getenv()` 사용** (config.py 사용 금지)
- [ ] Function has descriptive name (`snake_case`)
- [ ] Function decorated with `@register_tool`
- [ ] ALL parameters have type hints
- [ ] Return type is specified
- [ ] Docstring with Args/Returns sections
- [ ] At least 1 parameter (Gemini requirement)
- [ ] File placed in `src/tools/custom/`
- [ ] Test file created in `tests/tools/`
- [ ] `.env`에 필요한 환경변수 추가

**수정 파일:** 도구 파일 + `.env` (필요시) | **수정 금지:** `config.py`, `__init__.py`

### Common Patterns

**Optional parameters:**
```python
def my_tool(required: str, optional: str = "default") -> str:
    pass
```

**Multiple return types:**
```python
from typing import Union

def my_tool(input: str) -> Union[str, dict]:
    pass
```

**List/Dict parameters:**
```python
def my_tool(items: list[str], config: dict[str, any]) -> str:
    pass
```

---

## Examples

### Example 1: Simple Calculator Tool

```python
# src/tools/custom/calculator.py
from src.tools.registry import register_tool

@register_tool
def add(a: float, b: float) -> str:
    """Add two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        Sum as formatted string.
    """
    return f"Result: {a + b}"

@register_tool
def multiply(a: float, b: float) -> str:
    """Multiply two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        Product as formatted string.
    """
    return f"Result: {a * b}"
```

### Example 2: Echo Tool

```python
# src/tools/custom/echo.py
from src.tools.registry import register_tool

@register_tool
def echo(text: str, prefix: str = "") -> str:
    """Echo the input text.

    Args:
        text: Text to echo.
        prefix: Optional prefix (default: empty).

    Returns:
        Echoed text with prefix.
    """
    if prefix:
        return f"{prefix}: {text}"
    return text
```

### Example 3: Test for Echo Tool

```python
# tests/test_echo.py
import pytest
from src.tools.custom.echo import echo

def test_echo_without_prefix():
    """Test echo without prefix."""
    result = echo("Hello")
    assert result == "Hello"

def test_echo_with_prefix():
    """Test echo with prefix."""
    result = echo("Hello", prefix="Echo")
    assert result == "Echo: Hello"
```

---

## Error Handling

### User-Friendly Error Messages

```python
def fetch_data(url: str) -> str:
    """Fetch data from URL.

    Args:
        url: URL to fetch data from.

    Returns:
        Response content or error message.
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    try:
        import httpx
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except httpx.TimeoutException:
        return f"Error: Request timed out for {url}"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} for {url}"
    except Exception as e:
        return f"Error: Failed to fetch {url}: {str(e)}"
```

### Error Message Guidelines

```python
# Good: Clear and actionable
return "Error: API key not found. Set OPENWEATHER_API_KEY environment variable."
return "Error: Invalid date format. Use YYYY-MM-DD (e.g., 2024-01-15)."
return "Error: Query too long. Maximum 500 characters allowed."

# Bad: Vague or technical
return "Error occurred"
return f"Exception: {e}"
return "NoneType error"
```

---

## Task Scheduler

The scheduler allows users to schedule tasks via Slack (e.g., "1분 후에 뉴스 요약해줘").

### Scheduler Components

| Component | File | Description |
|-----------|------|-------------|
| `SchedulerManager` | `manager.py` | APScheduler singleton with SQLite persistence |
| `ScheduledTask` | `models.py` | Task data model |
| `parse_korean_time` | `time_parser.py` | Korean/English time expression parser |
| `run_scheduled_task` | `executor.py` | Executes task and sends result to Slack |
| `schedule_task` | `tools.py` | Agent tool to schedule tasks |

### Creating Time-Aware Tools

If you need to create tools that work with time expressions:

```python
# src/tools/reminder.py
from src.core.scheduler.time_parser import parse_korean_time, format_time_kst
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

def parse_time_info(time_expression: str) -> str:
    """Parse a time expression and return formatted info.

    Args:
        time_expression: Time like "1분 후", "오후 3시", "tomorrow 15:00".

    Returns:
        Formatted time information.
    """
    parsed = parse_korean_time(time_expression)
    if not parsed:
        return f"Cannot parse: {time_expression}"

    return f"Parsed: {format_time_kst(parsed)}"
```

### Context Propagation

The scheduler uses `contextvars.ContextVar` for async-safe context:

```python
from src.core.scheduler.tools import set_scheduler_context, clear_scheduler_context

# Set before agent runs (done automatically in Slack bot)
set_scheduler_context(
    user_id="U12345",
    channel_id="C67890",
    thread_ts="1234567890.123456",
)

# Agent can now call schedule_task tool

# Clear after (done automatically in finally block)
clear_scheduler_context()
```

## Security Guardrails

MCP tools are protected by guardrails. **Rules are defined per-server** in `src/tools/mcp/*.py` via `ServerGuardrailRules`, and aggregated by the generic framework in `src/middleware/guardrails/core.py`. See [CLAUDE.md](./CLAUDE.md) for details.

### Per-Server Rules

Each MCP server defines its own guardrail rules (sensitive patterns, write tools, custom checks):

```python
# src/tools/mcp/filesystem.py
register_mcp_server(
    key="filesystem",
    ...
    guardrail_rules=ServerGuardrailRules(
        write_tools={"write_file", "edit_file", "delete_file"},
        sensitive_file_patterns={".env", "*.key", "*secret*"},
        safe_file_patterns={"data/commands.db"},
    ),
)
```

### Memory Tools Isolation

Memory tools use `custom_check` for user isolation instead of generic `write_tools`:

```python
# Without user context - blocked for security
config = GuardrailConfig()  # No current_user_id
check_guardrails("read_graph", (), {}, config)  # GuardrailViolation!

# With user context - allowed
config = GuardrailConfig(current_user_id="U123")
check_guardrails("read_graph", (), {}, config)  # OK
```

---

## Additional Resources

- **Pydantic AI Documentation:** https://ai.pydantic.dev/
- **Python Type Hints:** https://docs.python.org/3/library/typing.html
- **pytest Documentation:** https://docs.pytest.org/
- **Google Python Style Guide:** https://google.github.io/styleguide/pyguide.html

---

**Last Updated:** 2026-02-05
