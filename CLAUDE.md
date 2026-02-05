# CLAUDE.md

Quick reference for Claude Code. See [AGENTS.md](./AGENTS.md) for detailed tool creation guide.

## Project Overview

**Stack**: Python 3.10+, Pydantic AI, Google Gemini, FastAPI, Slack, MCP

**Purpose**: Personal AI agent with custom tools, Slack integration, REST API, and MCP-powered extended capabilities.

## Commands

```bash
# Make 명령어 (권장)
make              # 도움말
make run          # 실행 (설정 + 모드 선택)
make test         # 코어 테스트
make test-all     # 전체 테스트 (커스텀 도구 포함)
make lint         # 린트 + 자동 수정
make format       # 코드 포맷팅
make tool-install # 외부 도구 설치
make tool-upload  # 도구 공유용 업로드
make edit-env     # .env 편집

# 직접 실행 (Make 없이)
uv run pytest tests/ --ignore=tests/tools -v           # 코어 테스트
uv run pytest tests/ -v                              # 전체 테스트
uv run ruff check src/ tests/ --fix                  # 린트
uv run python src/interfaces/slack/bot.py            # Slack 봇
uv run uvicorn src.interfaces.api:app --port 8000    # API 서버
```

## Architecture

```
src/
├── config.py              # pydantic-settings 기반 Settings 클래스
├── core/
│   ├── agent/
│   │   ├── core.py       # Backward-compat re-exports
│   │   ├── utils.py      # AgentRunResult, retry logic, image normalization
│   │   ├── factory.py    # AgentFactory (creates isolated agents)
│   │   └── runner.py     # AgentRunner (run/run_async with image extraction)
│   ├── context/          # Request context management (ContextVar)
│   │   └── image.py      # Attached images context + bounded caches (LRU)
│   ├── lifecycle.py      # LifecycleManager - singleton startup/shutdown
│   ├── commands/         # Custom command management
│   │   ├── executor.py   # CommandExecutor
│   │   ├── models.py     # Command data model
│   │   ├── parser.py     # Command parsing
│   │   ├── prompts.py    # Prompt building
│   │   ├── repository.py # SQLite CRUD
│   │   └── tools.py      # Command CRUD tools
│   ├── memory/
│   │   └── prompts.py    # MEMORY_SYSTEM_PROMPT, build_memory_prompt()
│   └── scheduler/
│       ├── __init__.py   # SchedulerManager, parse_korean_time exports
│       ├── models.py     # ScheduledTask dataclass
│       ├── time_parser.py # Korean/English time expression parser
│       ├── manager.py    # APScheduler wrapper (SQLite persistence)
│       ├── executor.py   # Scheduled task execution + Slack notification
│       └── tools.py      # schedule_task, list_scheduled_tasks, cancel_scheduled_task
├── interfaces/
│   ├── slack/            # Modularized Slack bot (127-line orchestrator)
│   │   ├── bot.py        # Event router (thin orchestrator)
│   │   ├── handlers.py   # Event handlers (mention, DM, reaction)
│   │   ├── context.py    # Thread/channel context building
│   │   ├── images.py     # Image extraction and upload
│   │   ├── progress.py   # Progress indicator formatting
│   │   └── slack_api.py  # Slack API utilities (retry, rate limits)
│   └── api/
│       ├── main.py       # FastAPI app
│       ├── security.py   # API key auth + rate limiting (slowapi)
│       ├── schemas.py    # Pydantic models
│       ├── tasks.py      # Background tasks + webhooks
│       └── task_repository.py # SQLite-based task persistence
├── middleware/
│   ├── guardrails/
│   │   ├── __init__.py   # Exports: GuardrailConfig, GuardrailViolation, GuardrailEnforcer
│   │   ├── core.py       # Generic guardrail framework (aggregates server rules)
│   │   └── enforcer.py   # Defense-in-depth for ALL tool types
│   ├── preprocessing/    # Request preprocessing
│   │   └── __init__.py   # preprocess_command(), re-exports from core
│   └── postprocessing/   # Response postprocessing (minimal)
├── tools/
│   ├── __init__.py       # get_custom_toolset() - custom tools only
│   ├── catalog.py        # ToolCatalog - unified tool source management
│   ├── registry.py       # @register_tool decorator, auto-registration
│   ├── mcp_registry.py   # MCPServerConfig, ServerGuardrailRules, register_mcp_server()
│   ├── mcp_client.py     # MCPManager class (with guardrails)
│   ├── mcp/              # MCP server definitions (register_mcp_server, gitignored)
│   └── custom/           # User-implemented tools (@register_tool, gitignored)
└── utils/
    ├── logging.py        # Structured JSON logging with request_id
    ├── observability.py  # Logfire integration (setup_logfire)
    ├── image_handler.py  # ImageData, extract_images_from_result()
    ├── slack_files.py    # Slack file download/upload utilities
    └── slack_formatter.py # Markdown → Slack mrkdwn conversion
```

## Critical Rules

- **RESPONSE LANGUAGE**: 답변은 항상 한국어로, 핵심만 요약해서 간결하게
- **GEMINI REQUIREMENT**: All tools MUST have at least 1 parameter
- **Type hints**: Required on ALL parameters and return values
- **Docstrings**: Use Google-style format
- **Tool location**: Place in `src/tools/custom/` with `@register_tool` decorator (auto-registered)

## Code Conventions

| Element | Style |
|---------|-------|
| Functions/variables | `snake_case` |
| Classes | `PascalCase` |
| Constants | `UPPER_SNAKE_CASE` |

**Git & Release**: [docs/GIT_CONVENTIONS.md](./docs/GIT_CONVENTIONS.md) 참조

## Tool Creation

Tools are plain Python functions with `@register_tool` decorator - **no manual registration needed**.

### Creating a New Tool

Create function in `src/tools/custom/my_tool.py` with `@register_tool`:

```python
# src/tools/custom/my_tool.py
from src.tools.registry import register_tool

@register_tool
def calculate_sum(a: float, b: float) -> str:
    """Calculate the sum of two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        Sum of a and b as a formatted string.
    """
    return f"Result: {a + b}"
```

**That's it!** No need to modify `__init__.py` or any other file.

### Tool with External API

```python
# src/tools/custom/weather.py
import os
from typing import Optional

from src.tools.registry import register_tool

_client: Optional[WeatherAPI] = None

def _get_client() -> WeatherAPI:
    """Lazy client initialization."""
    global _client
    if _client is None:
        api_key = os.getenv("WEATHER_API_KEY")
        if not api_key:
            raise ValueError("WEATHER_API_KEY required")
        _client = WeatherAPI(api_key=api_key)
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
    except Exception as e:
        return f"Error: {str(e)}"
```

## MCP Integration

MCP servers extend the agent with additional capabilities. Enable via `AgentRunner(enable_mcp=True)`.

**Auto-registration**: MCP 서버는 `src/tools/mcp/`에 파일을 추가하고 `register_mcp_server()`를 호출하면 자동 등록됩니다. 상세 가이드: [MCP_SERVER_GUIDE.md](./docs/MCP_SERVER_GUIDE.md)

**Security**: Guardrails are enabled by default to block sensitive file access and write operations.

### Available MCP Servers

| Server | Description | Requires |
|--------|-------------|----------|
| `filesystem` | File operations (read, write, list) | - |
| `fetch` | Web content fetching | - |
| `git` | Git operations (status, diff, log) | - |
| `memory` | Knowledge graph storage | - |
| `sequential-thinking` | Step-by-step reasoning (slow: 2-5 min/step) | - |
| `github` | GitHub API integration | `GITHUB_TOKEN` |
| `sentry` | Error monitoring and issue tracking | `SENTRY_ACCESS_TOKEN` |
| `playwright` | Browser automation (web testing, scraping) | - |

### MCP Usage

```python
from src.core.agent import AgentRunner

# Enable all available MCP servers
with AgentRunner(enable_mcp=True) as agent:
    result = agent.run("List files in current directory")
    print(result.output)

# Enable specific MCP servers
with AgentRunner(enable_mcp=True, mcp_servers=["filesystem", "git"]) as agent:
    result = agent.run("Show git status and list files")
    print(result.output)
```

### Using AgentFactory (for concurrent requests)

```python
from src.core.agent import AgentFactory

# Create factory with shared resources
with AgentFactory(enable_mcp=True) as factory:
    # Each request gets isolated agent
    agent = factory.create_agent()
    result = await agent.run("Your task here")
```

### MCP Tools Reference

#### filesystem
- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to file
- `list_directory(path)` - List directory contents
- `create_directory(path)` - Create directory
- `search_files(pattern)` - Search for files

#### fetch
- `fetch(url)` - Fetch web page content
- Returns content in various formats (HTML, text, markdown)

#### git
- `git_status()` - Show working tree status
- `git_diff()` - Show file changes
- `git_log(n)` - Show last n commits
- `git_commit(message)` - Commit changes

#### memory
- `create_entities(entities)` - Store knowledge entities (user-isolated)
- `create_relations(relations)` - Store entity relationships (user-isolated)
- `search_nodes(query)` - Search knowledge graph
- `read_graph()` - Read knowledge graph (requires user context for security)

#### sequential-thinking
- `think(thought)` - Process step-by-step reasoning
- Supports branching and revision of thoughts

#### github (requires GITHUB_TOKEN)
- `create_issue(repo, title, body)` - Create issue
- `list_issues(repo)` - List repository issues
- `create_pull_request(repo, title, body, head, base)` - Create PR
- `search_code(query)` - Search code on GitHub

#### playwright
- `browser_navigate(url)` - Navigate to URL
- `browser_click(selector)` - Click element
- `browser_type(selector, text)` - Type text into element
- `browser_take_screenshot(path)` - Take screenshot
- `browser_close()` - Close browser

## Playwright Cleanup

Playwright MCP 사용 시 브라우저 미종료 및 임시 파일 누적 문제를 방지하기 위한 자동 정리 기능.

### 자동 정리 (기본 활성화)

```python
from src.core.agent.core import AgentRunner

# Async context manager 사용 시 자동 정리
async with AgentRunner(enable_mcp=True) as agent:
    result = await agent.run_async("Take a screenshot of google.com")
    # __aexit__에서 자동으로:
    # 1. browser_close 호출 (열려있는 경우)
    # 2. 임시 스크린샷 파일 삭제
```

### 수동 정리

```python
from src.tools.mcp_client import MCPManager

manager = MCPManager()
manager.connect("playwright")

# ... agent 실행 후 ...

# Cleanup 필요 여부 확인 (generic API - 모든 서버 대응)
if manager.needs_cleanup():
    # Async 정리 (browser close + 파일 삭제)
    await manager.cleanup_all()

    # 또는 Sync 정리 (파일만 삭제)
    manager.cleanup_files_sync()
```

### Cleanup Tracker 직접 사용

```python
from src.tools.mcp.playwright import PlaywrightCleanupTracker

tracker = PlaywrightCleanupTracker()

# Hook을 MCP 서버에 연결
hook = tracker.create_hook(existing_hook=guardrail_hook)

# ... 도구 호출 후 ...

# 정리 필요 여부 확인
if tracker.needs_browser_cleanup:
    await tracker.cleanup_browser(mcp_call=my_mcp_call_func)

if tracker.needs_file_cleanup:
    tracker.cleanup_screenshot_files()
```

### 주의사항

- **Sync context manager** (`with` 문): 파일만 정리, 브라우저는 경고 로그 출력
- **Async context manager** (`async with` 문): 브라우저 + 파일 모두 정리
- 30분 이상 된 임시 스크린샷 파일은 자동 삭제

## Security Guardrails

MCP tools are protected by security guardrails that block sensitive file access and write operations. **Guardrail rules are now defined per-server** in each MCP server file (`src/tools/mcp/*.py`), allowing customized security policies.

### Default Behavior (Enabled)

```python
from src.tools.mcp_client import MCPManager

# Guardrails ON by default (read-only + block sensitive files)
manager = MCPManager()  # enable_guardrails=True
tools = manager.connect_all()
```

### Server-Specific Rules

Each MCP server defines its own guardrail rules via `ServerGuardrailRules`:

```python
# src/tools/mcp/filesystem.py
from src.tools.mcp_registry import ServerGuardrailRules, register_mcp_server

register_mcp_server(
    key="filesystem",
    ...
    guardrail_rules=ServerGuardrailRules(
        write_tools={"write_file", "edit_file", "delete_file", "create_directory"},
        sensitive_file_patterns={".env", ".env.*", "*.env", ".aws/*", "*.key", "*.pem"},
    ),
)
```

### Common Blocked Patterns

| Server | Sensitive Patterns | Write Tools |
|--------|-------------------|-------------|
| `filesystem` | `.env*`, `.aws/*`, `*.key`, `*.pem`, `*secret*`, `*password*` | `write_file`, `edit_file`, `delete_file`, `create_directory` |
| `git` | - | `git_commit`, `git_push`, `git_reset`, `git_rebase` |
| `github` | - | `create_issue`, `create_pull_request`, `merge_pull_request` |
| `memory` | - | *(custom_check로 사용자 격리 - write_tools 미사용)* |

### Custom Configuration

```python
from src.tools.mcp_client import MCPManager
from src.middleware.guardrails import GuardrailConfig

# Disable guardrails (DANGEROUS)
manager = MCPManager(enable_guardrails=False)

# Custom config
config = GuardrailConfig(
    read_only=True,               # Block write operations
    block_sensitive_files=True,   # Block sensitive files
    sensitive_patterns={".my_secret"},  # Additional blocked patterns
    safe_patterns={"config.json"},      # Override blocks
    blocked_tools={"dangerous_tool"},   # Additional blocked tools
    allowed_tools=None,           # Whitelist mode (None = allow all except blocked)
    log_blocked_attempts=True,    # Log violations
)
manager = MCPManager(guardrail_config=config)
```

### GuardrailViolation Exception

```python
from src.middleware.guardrails import GuardrailViolation

try:
    result = tool.forward(path=".env")
except GuardrailViolation as e:
    print(f"Blocked: {e.message}")
    print(f"Tool: {e.tool_name}")
    print(f"Type: {e.violation_type}")  # "sensitive_file" or "write_operation"
```

## Command System

Custom command management with SQLite persistence.

### Components

| Component | Description |
|-----------|-------------|
| `Command` | Data model for custom commands |
| `CommandRepository` | SQLite CRUD operations |
| `CommandExecutor` | Command lookup and execution |
| `parse_command` | Parse user input for commands |

### Available Command Tools

- `create_command(name, description, prompt_template)` - Create new command
- `list_commands()` - List all commands
- `get_command(name)` - Get command details
- `update_command(name, ...)` - Update command
- `delete_command(name)` - Delete command

## Task Scheduler

APScheduler 기반의 작업 예약 시스템. SQLite에 작업을 저장하여 봇 재시작 후에도 유지됩니다.

### Scheduler Tools

| Tool | Description |
|------|-------------|
| `schedule_task(time_expression, task_description)` | 작업 예약 |
| `list_scheduled_tasks(include_all)` | 예약 목록 조회 |
| `cancel_scheduled_task(task_id)` | 예약 취소 |

### Supported Time Expressions

| Type | Examples |
|------|----------|
| 상대 시간 (Korean) | `1분 후`, `30초 뒤`, `2시간 후`, `3일 후` |
| 상대 시간 (English) | `in 5 minutes`, `after 1 hour` |
| 절대 시간 (Korean) | `오후 3시`, `오전 10시 30분` |
| 절대 시간 (24h) | `15:00`, `14:30` |
| 조합 | `내일 오전 10시`, `tomorrow 15:00` |

### Usage Example (Slack)

```
User: @agent 1분 후에 오늘 뉴스 요약해줘

Agent: :calendar: 작업이 예약되었습니다!
- ID: `a1b2c3d4`
- 실행 시간: 2024-01-15 오후 3:31 KST
- 작업: 오늘 뉴스 요약해줘

(1분 후)

Agent: :alarm_clock: 예약된 작업 실행 중...
Agent: :white_check_mark: 예약 작업 완료
오늘의 주요 뉴스: ...
```

### Architecture

```python
# Slack bot initializes scheduler on startup (src/slack/bot.py)
scheduler = SchedulerManager.get_instance()
scheduler.set_slack_client(app.client)
scheduler.start()

# Context is set before agent runs
set_scheduler_context(user_id, channel_id, thread_ts)

# Agent calls schedule_task tool
# → APScheduler stores job in SQLite
# → At scheduled time, executor runs agent and sends result to thread
```

## Code Quality

### Ruff (Linter & Formatter)

프로젝트는 [Ruff](https://docs.astral.sh/ruff/)를 사용하여 코드 스타일을 검증하고 포맷팅합니다.

```bash
# Lint 검사 (자동 수정 포함)
uv run ruff check src/ tests/ --fix

# 코드 포맷팅
uv run ruff format src/ tests/

# Lint만 검사 (수정 없이)
uv run ruff check src/ tests/
```

**활성화된 규칙:**
- `E`, `W` - pycodestyle (PEP 8 스타일)
- `F` - Pyflakes (논리적 오류)
- `I` - isort (import 정렬)
- `B` - flake8-bugbear (버그 패턴)
- `UP` - pyupgrade (Python 최신 문법)
- `SIM` - flake8-simplify (코드 단순화)

### Pre-commit Hooks

Git 커밋 전에 자동으로 코드 품질을 검사합니다.

```bash
# Hook 설치 (최초 1회)
uv run pre-commit install

# 수동 실행 (모든 파일)
uv run pre-commit run --all-files

# 특정 hook만 실행
uv run pre-commit run ruff --all-files
```

**포함된 Hook:**
| Hook | 설명 |
|------|------|
| `ruff` | Lint 검사 + 자동 수정 |
| `ruff-format` | 코드 포맷팅 |
| `trailing-whitespace` | 줄 끝 공백 제거 |
| `end-of-file-fixer` | 파일 끝 개행 추가 |
| `check-yaml/json/toml` | 설정 파일 문법 검사 |
| `debug-statements` | print/debugger 문 감지 |
| `detect-private-key` | 비밀키 노출 방지 |

**커밋 시 자동 실행:**
```bash
git commit -m "Your message"
# → pre-commit hooks 자동 실행
# → 실패 시 커밋 중단, 수정 후 재시도
```

## Observability

Pydantic Logfire integration for monitoring and debugging.

### Setup

```python
from src.utils.observability import setup_logfire

# Called automatically in AgentRunner
setup_logfire()  # Only activates if LOGFIRE_TOKEN is set
```

### Features
- Automatic pydantic-ai instrumentation
- HTTP request tracing via httpx
- Structured logging for debugging

## Environment Variables

```bash
# Required
GOOGLE_API_KEY=<required>           # Google Gemini API key (or GEMINI_API_KEY)

# Optional - Core
GEMINI_MODEL=gemini-3-flash-preview # Model to use (default: gemini-3-flash-preview)
LOGFIRE_TOKEN=logfire_...           # Pydantic Logfire token

# Optional - Slack
SLACK_BOT_TOKEN=xoxb-...            # Slack bot token
SLACK_APP_TOKEN=xapp-...            # Slack app token

# Optional - API Security
API_AUTH_KEY=your-secret-key        # API authentication key (X-API-Key header)
API_RATE_LIMIT=60                   # Requests per minute (default: 60)

# 커스텀 도구/MCP 서버 환경변수는 .env에만 추가 (예: GITHUB_TOKEN, EXA_API_KEY 등)
```

## Workflows

### Creating a New Tool
1. Create `src/tools/custom/my_tool.py` with `@register_tool` decorator
2. Use `os.getenv()` for API keys (NOT `settings`)
3. Add environment variables to `.env` (`.env.example` 수정 금지)
4. Ensure at least 1 parameter (Gemini requirement)
5. Add type hints and docstring
6. Create test in `tests/tools/test_my_tool.py`
7. Run tests: `make test-all`
8. Restart: `make run`

**도구 파일 하나만 수정!** `config.py`, `__init__.py` 등 다른 파일 수정 금지.

### Adding a New MCP Server
1. Create `src/tools/mcp/my_server.py` with `register_mcp_server()` call
2. Add environment variables to `.env` (필요한 경우)
3. Restart: `make run`

**서버 파일 하나만 추가!** `config.py`, `client.py` 등 다른 파일 수정 금지. 상세 가이드: [MCP_SERVER_GUIDE.md](./docs/MCP_SERVER_GUIDE.md)

### Using MCP
1. Set required environment variables (e.g., `GITHUB_TOKEN`)
2. Initialize AgentRunner with `enable_mcp=True`
3. Use context manager for automatic cleanup
4. Specify `mcp_servers=["server1", "server2"]` to limit servers

## New Architecture Components

### Settings (`src/config.py`)

pydantic-settings 기반 환경 변수 관리. 타입 안전하고 검증된 설정.

```python
from src.config import settings

# 사용 예시
api_key = settings.google_api_key
model = settings.gemini_model  # default: "gemini-3-flash-preview"
```

### ToolCatalog (`src/tools/catalog.py`)

모든 도구 소스를 통합 관리. AgentFactory가 사용.

```python
from src.tools.catalog import ToolCatalog

catalog = ToolCatalog()
tools = catalog.get_all_tools()  # custom + commands + scheduler tools
```

### Request Context (`src/core/context/`)

요청 스코프 데이터 관리 (ContextVar 기반). 이미지 편집 도구에서 첨부 이미지 접근에 사용.

```python
from src.core.context import set_attached_images, get_attached_images

# Slack handler에서 첨부 이미지 설정
set_attached_images([{"bytes": img_bytes, "mime_type": "image/png", "name": "photo.png"}])

# edit_image 도구에서 첨부 이미지 접근
images = get_attached_images()
```

### Preprocessing Middleware (`src/middleware/preprocessing/`)

요청 전처리 레이어. 커맨드 파싱, 스케줄러 컨텍스트, 첨부 이미지 설정.

```python
from src.middleware.preprocessing import preprocess_command, set_scheduler_context

# 커맨드 전처리
result = preprocess_command(message)

# 스케줄러 컨텍스트 설정
set_scheduler_context(user_id, channel_id, thread_ts)
```

### GuardrailEnforcer (`src/middleware/guardrails/enforcer.py`)

모든 도구 유형에 대한 Defense-in-Depth 보안 레이어.

```python
from src.middleware.guardrails import GuardrailEnforcer

enforcer = GuardrailEnforcer(config)
enforcer.validate_tool_call("write_file", {"path": ".env"})  # Raises!
```

### API Security (`src/interfaces/api/security.py`)

API 키 인증 및 Rate Limiting (slowapi 기반).

```python
from src.interfaces.api.security import verify_api_key, limiter

# FastAPI 의존성으로 사용
@app.post("/run")
@limiter.limit(get_rate_limit_string())  # 분당 60요청 (설정 가능)
async def run(api_key: str = Depends(verify_api_key)):
    pass
```

### REST API Endpoints

#### POST /run - 에이전트 작업 실행

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "prompt": "오늘 뉴스 요약해줘",
    "user_id": "user123",
    "webhook_url": "https://your-server.com/webhook",
    "webhook_headers": {
      "Authorization": "Bearer your_webhook_token",
      "X-Custom-Header": "custom_value"
    }
  }'
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `prompt` | string | ✅ | 에이전트에게 보낼 작업 |
| `user_id` | string | | 사용자 ID (메모리 컨텍스트용) |
| `webhook_url` | string | | 완료 시 콜백 받을 URL |
| `webhook_headers` | object | | 웹훅 요청에 포함할 헤더 (인증 등) |

#### GET /status/{task_id} - 작업 상태 조회

```bash
curl http://localhost:8000/status/{task_id} \
  -H "X-API-Key: your-api-key"
```

#### GET /health - 헬스 체크 (인증 불필요)

```bash
curl http://localhost:8000/health
```

#### Webhook Payload

작업 완료 시 `webhook_url`로 전송되는 데이터:

```json
{
  "task_id": "uuid",
  "status": "success|error",
  "result": "에이전트 응답",
  "error_message": null,
  "execution_time": 14.5,
  "tool_calls": [],
  "model_used": "gemini-3-flash-preview",
  "images": []
}
```

### LifecycleManager (`src/core/lifecycle.py`)

싱글톤 라이프사이클 관리 (시작/종료).

```python
from src.core.lifecycle import LifecycleManager

manager = LifecycleManager()
await manager.startup()   # Initialize all singletons
await manager.shutdown()  # Clean shutdown
```

### Structured Logging (`src/utils/logging.py`)

구조화된 JSON 로깅 with request_id 추적.

```python
from src.utils.logging import get_logger, set_request_id

set_request_id("req-123")
logger = get_logger(__name__)
logger.info("Processing", extra={"user_id": "U123"})
# Output: {"timestamp": "...", "request_id": "req-123", "user_id": "U123", ...}
```

## Request Processing Workflow

AI 에이전트가 코드 요청을 처리할 때 따라야 하는 워크플로우입니다.

### 1. Check Documentation First

**ALWAYS** 작업 전 관련 문서 확인:

```bash
# 문서 디렉토리 구조 파악
ls docs/

# 관련 가이드 확인
cat docs/TOOL_CREATION_GUIDE.md      # 도구 생성 시
cat docs/MCP_INTEGRATION_GUIDE.md    # MCP 작업 시
cat docs/DEVELOPMENT_WORKFLOW.md     # 개발 프로세스
```

| 작업 유형 | 확인할 문서 |
|---------|-----------|
| 도구 생성 | `docs/TOOL_CREATION_GUIDE.md`, `AGENTS.md` |
| MCP 서버 추가 | `docs/MCP_SERVER_GUIDE.md` |
| MCP 통합 | `docs/MCP_INTEGRATION_GUIDE.md` |
| API 수정 | `src/interfaces/api/` 코드 + README |
| Slack 봇 | `src/interfaces/slack/` 코드 |
| 테스트 | `tests/` 기존 패턴 참고 |

### 2. Analyze & Plan

복잡한 작업은 먼저 분석:

```markdown
## 요청 분석
- 무엇을 해야 하는가?
- 영향 받는 파일은?
- 기존 패턴과 일치하는가?
- 테스트가 필요한가?
```

### 3. Create TODOs & Execute

다단계 작업은 TODO 생성 후 순차 실행:

```markdown
- [ ] Step 1: 파일 생성/수정
- [ ] Step 2: 테스트 작성
- [ ] Step 3: 린트 검사
- [ ] Step 4: 문서 업데이트
```

### 4. Test & Verify

**ALWAYS** 변경 후 검증:

```bash
# 특정 테스트 실행
uv run pytest tests/test_<module>.py -v

# 전체 테스트
uv run pytest tests/ -v

# 타입 검사 (선택)
uv run mypy src/
```

### 5. Lint Check

**ALWAYS** 코드 스타일 검사:

```bash
# Lint 검사 + 자동 수정
uv run ruff check src/ tests/ --fix

# 포맷팅
uv run ruff format src/ tests/
```

### 6. Update Documentation

코드 변경 시 문서도 함께 업데이트:

| 변경 유형 | 업데이트 대상 |
|---------|-------------|
| 새 도구 추가 | 도구 파일 + `.env`만 (다른 파일 수정 금지, 테스트는 `tests/tools/` - gitignored) |
| 새 MCP 서버 추가 | `src/tools/mcp/` 서버 파일 + `.env`만 (다른 파일 수정 금지) |
| 새 환경변수 (코어) | `CLAUDE.md`, `README.md`, `.env.example` |
| 새 테스트 파일 | `AGENTS.md` (Test File Organization) |
| 아키텍처 변경 | `CLAUDE.md`, `README.md`, `AGENTS.md` |
| 새 docs/ 가이드 | `CLAUDE.md` (docs/ 섹션) |

### Quick Checklist

```markdown
□ 1. docs/ 확인했는가?
□ 2. 기존 패턴을 따랐는가?
□ 3. 테스트를 실행했는가?
□ 4. ruff check/format을 실행했는가?
□ 5. 관련 문서를 업데이트했는가?
```

## Gotchas

- Tool parameters: Must have at least 1 parameter (Gemini)
- Tool discovery: Requires restart after adding new tools
- Tool registration: Use `@register_tool` decorator (no manual registration needed)
- MCP servers: Use `npx` to run, requires Node.js installed
- **MCP registration**: Use `register_mcp_server()` in `src/tools/mcp/*.py` (auto-discovered, gitignored)
- GitHub MCP: Requires `GITHUB_TOKEN` environment variable
- Async tests: Use `@pytest.mark.asyncio` decorator
- **Settings (Core)**: Use `from src.config import settings` for core/interfaces
- **Settings (Tools)**: Use `os.getenv()` for tools - `.env`만 수정하면 됨
- **Guardrails**: Enabled by default - rules defined per-server in `src/tools/mcp/*.py` via `ServerGuardrailRules`
- **GuardrailEnforcer**: Protects ALL tools (custom, MCP, scheduler) by aggregating server-specific rules
- **Memory Guardrails**: `read_graph()` requires user context to prevent data leakage (enforced via custom_check)
- **Slack retry**: API calls after agent execution have automatic retry (3 attempts, exponential backoff)
- **AgentRunResult**: Agent.run() returns `AgentRunResult(output, images, messages)`, not a string
- **AgentRunner timeout**: Sync `run()` method has 5-minute timeout to prevent infinite hangs
- **Scheduler**: Uses `contextvars` for async context propagation (not `threading.local`)
- **Scheduler DB**: SQLite at `data/scheduler.db` - persists across restarts
- **Task DB**: API tasks persisted to SQLite at `data/tasks.db` - survives server restarts
- **ToolCatalog**: Unified tool source - replaces scattered tool assembly in AgentFactory
- **Playwright cleanup**: Use `async with AgentRunner()` for full cleanup (browser + files). Sync `with` only cleans files.
- **Playwright tracker**: Automatically tracks `browser_*` tool calls and cleans up if `browser_close` wasn't called
- **Image Generation**: Uses request_id pattern `[IMAGE_GENERATED:uuid]` for image extraction from tool results
- **Image Context**: `core/context` stores attached images for `edit_image` tool to access Slack attachments
- **API Security**: Set `API_AUTH_KEY` env var to enable X-API-Key authentication (disabled if unset)
- **Audio Transcription**: Requires `mlx-audio` package and Apple Silicon Mac for optimal performance

**For detailed patterns and examples, see [AGENTS.md](./AGENTS.md).**
