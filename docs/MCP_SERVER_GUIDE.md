# MCP Server Guide

MCP 서버를 추가하는 상세 가이드입니다. `register_mcp_server()` 함수를 사용하면 파일 하나만 추가하여 MCP 서버를 등록할 수 있습니다.

> **Quick Reference**: [CLAUDE.md](../CLAUDE.md) | **MCP Integration**: [MCP_INTEGRATION_GUIDE.md](./MCP_INTEGRATION_GUIDE.md)

---

## Table of Contents

1. [핵심 규칙](#핵심-규칙)
2. [서버 추가 방법](#서버-추가-방법)
3. [register_mcp_server() API](#register_mcp_server-api)
4. [서버 유형별 예제](#서버-유형별-예제)
5. [테스트 작성](#테스트-작성)
6. [체크리스트](#체크리스트)

---

## 핵심 규칙

### 서버 파일 하나로 완결 (CRITICAL)

**`src/tools/mcp/` 디렉토리에 파일 하나만 추가하면 됩니다. 다른 파일 수정 금지!**

```
✅ MCP 서버 추가 시 수정하는 것:
   - src/tools/mcp/my_server.py (서버 설정 파일)
   - .env (환경변수 - 필요한 경우)

❌ 절대 수정하면 안 되는 것:
   - src/tools/mcp_registry.py
   - src/tools/mcp_client.py
   - 그 외 모든 파일
```

### 자동 등록 원리

```
src/tools/mcp/
├── __init__.py          # 패키지 마커 (수정 금지)
├── filesystem.py        # register_mcp_server(key="filesystem", ...)
├── github.py            # register_mcp_server(key="github", ...)
└── my_server.py         # register_mcp_server(key="my_server", ...)
```

서버 파일이 import되면 `register_mcp_server()`가 호출되어 전역 레지스트리에 등록됩니다.
`MCPManager`가 초기화될 때 `auto_discover_mcp_servers()`가 모든 서버 파일을 자동 import합니다.

---

## 서버 추가 방법

### Step 1: 서버 파일 생성

```python
# src/tools/mcp/my_server.py
import os

from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="my-server",
    name="My Server",
    description="Custom MCP server description",
    command="npx",
    args=["-y", "@my-org/mcp-server"],
    env={"MY_API_KEY": os.environ.get("MY_API_KEY", "")},
    requires_env=["MY_API_KEY"],
)
```

### Step 2: 환경 변수 설정 (필요한 경우)

```bash
# .env 파일에 추가
MY_API_KEY=your-api-key-here
```

### Step 3: 확인

```bash
# 에이전트 재시작
make run
# 로그에서 서버 등록 확인: "Auto-discovered N MCP servers: [... 'my-server']"
```

---

## register_mcp_server() API

```python
register_mcp_server(
    key: str,              # 서버 키 - connect("key")에서 사용
    name: str,             # 표시 이름
    description: str,      # 서버 설명
    command: str,          # 실행 명령어 ("npx", "uvx" 등)
    args: list[str],       # 명령어 인자
    env: dict[str, str] | None = None,       # 환경 변수
    enabled: bool = True,                     # 활성화 여부
    requires_env: list[str] | None = None,    # 필수 환경 변수
    tool_prefix: str | None = None,           # 도구 이름 접두사
    guardrail_rules: ServerGuardrailRules | None = None,  # 서버별 보안 규칙
) -> MCPServerConfig
```

### 파라미터 설명

| 파라미터 | 필수 | 설명 | 예시 |
|---------|:----:|------|------|
| `key` | ✅ | 서버 식별자 (고유) | `"github"`, `"my-server"` |
| `name` | ✅ | 표시 이름 | `"GitHub"`, `"My Server"` |
| `description` | ✅ | 서버 기능 설명 | `"GitHub API integration"` |
| `command` | ✅ | 실행 명령어 | `"npx"`, `"uvx"` |
| `args` | ✅ | 명령어 인자 리스트 | `["-y", "@pkg/server"]` |
| `env` | | 서버 프로세스 환경 변수 | `{"TOKEN": os.environ.get("TOKEN", "")}` |
| `enabled` | | 활성화 여부 (기본: True) | `True` |
| `requires_env` | | 필수 환경 변수 이름 목록 | `["GITHUB_TOKEN"]` |
| `tool_prefix` | | 도구 이름 접두사 | `"gh"`, `"sentry"` |
| `guardrail_rules` | | 서버별 보안 규칙 | `ServerGuardrailRules(...)` |

### tool_prefix 사용

서버 간 도구 이름 충돌을 방지합니다:

```python
# tool_prefix="gh" → list_issues → gh_list_issues
register_mcp_server(
    key="github",
    ...
    tool_prefix="gh",
)
```

### requires_env 동작

`requires_env`에 지정된 환경 변수가 설정되지 않으면 `connect_all()`에서 자동 skip됩니다:

```python
# GITHUB_TOKEN이 없으면 이 서버는 자동으로 건너뜀
register_mcp_server(
    key="github",
    ...
    requires_env=["GITHUB_TOKEN"],
)
```

### guardrail_rules 정의

서버별 보안 규칙을 정의하여 민감한 파일 패턴, 쓰기 도구, 커스텀 검사를 지정할 수 있습니다:

```python
from src.tools.mcp_registry import register_mcp_server, ServerGuardrailRules

register_mcp_server(
    key="filesystem",
    ...
    guardrail_rules=ServerGuardrailRules(
        write_tools={"write_file", "edit_file", "delete_file", "create_directory"},
        sensitive_file_patterns={".env", ".env.*", "*.env", ".aws/*", "*.key", "*.pem"},
        safe_file_patterns={"package.json", "data/commands.db"},  # 예외 허용
    ),
)
```

#### ServerGuardrailRules 필드

| 필드 | 타입 | 설명 |
|-----|------|------|
| `write_tools` | `set[str]` | 쓰기 작업으로 분류할 도구 이름 |
| `read_only_tools` | `set[str]` | 읽기 전용으로 분류할 도구 이름 |
| `sensitive_file_patterns` | `set[str]` | 차단할 파일 패턴 (glob) |
| `sensitive_path_patterns` | `set[str]` | 차단할 경로 패턴 (glob) |
| `safe_file_patterns` | `set[str]` | 민감 패턴 예외 (항상 허용) |
| `custom_check` | `Callable` | 커스텀 검증 함수 (선택) |

#### 커스텀 검증 함수

```python
from src.middleware.guardrails import GuardrailViolation

def check_memory_access(
    tool_name: str,
    args: tuple,
    kwargs: dict[str, Any],
    config: Any,
) -> None:
    """Memory access check - user isolation."""
    if tool_name == "read_graph" and not config.current_user_id:
        raise GuardrailViolation(
            "read_graph blocked: no user context",
            tool_name,
            "memory_no_context",
        )

register_mcp_server(
    key="memory",
    ...
    guardrail_rules=ServerGuardrailRules(
        read_only_tools={"search_nodes", "open_nodes", "read_graph"},
        custom_check=check_memory_access,
    ),
)
```

---

## 서버 유형별 예제

### npx 서버 (Node.js 패키지)

```python
# src/tools/mcp/filesystem.py
from src.tools.mcp_registry import ServerGuardrailRules, register_mcp_server

register_mcp_server(
    key="filesystem",
    name="Filesystem",
    description="Secure file operations with configurable access controls",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "."],
    guardrail_rules=ServerGuardrailRules(
        write_tools={"write_file", "edit_file", "delete_file", "create_directory"},
        sensitive_file_patterns={
            ".env", ".env.*", "*.env",
            ".aws/credentials", ".aws/config",
            ".ssh/*", "id_rsa*", "*.pem", "*.key",
            "*secret*", "*password*", "*credential*", "*token*",
        },
    ),
)
```

### uvx 서버 (Python 패키지)

```python
# src/tools/mcp/fetch.py
from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="fetch",
    name="Fetch",
    description="Web content fetching and conversion to various formats",
    command="uvx",
    args=["mcp-server-fetch"],
)
```

### 환경 변수 필요한 서버

```python
# src/tools/mcp/github.py
import os

from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="github",
    name="GitHub",
    description="GitHub API integration for repository management",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", "")},
    requires_env=["GITHUB_TOKEN"],
    tool_prefix="gh",
)
```

### 전체 기존 서버 예제

<details>
<summary>8개 기존 서버 설정 (펼치기)</summary>

#### filesystem.py
```python
from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="filesystem",
    name="Filesystem",
    description="Secure file operations with configurable access controls",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "."],
)
```

#### fetch.py
```python
from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="fetch",
    name="Fetch",
    description="Web content fetching and conversion to various formats",
    command="uvx",
    args=["mcp-server-fetch"],
)
```

#### git.py
```python
from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="git",
    name="Git",
    description="Git repository operations (status, diff, log, commit)",
    command="uvx",
    args=["mcp-server-git", "--repository", "."],
)
```

#### memory.py
```python
from src.middleware.guardrails.core import GuardrailViolation
from src.tools.mcp_registry import ServerGuardrailRules, get_base_tool_name, register_mcp_server

# NOTE: Memory write tools are NOT registered as write_tools because
# they need special user-isolation checks via custom_check.

def check_memory_access(tool_name, args, kwargs, config):
    """Memory access check - user isolation."""
    base_name = get_base_tool_name(tool_name.lower())
    if base_name == "read_graph" and not config.current_user_id:
        raise GuardrailViolation(
            "read_graph blocked: no user context",
            tool_name,
            "memory_no_context",
        )

register_mcp_server(
    key="memory",
    name="Memory",
    description="Knowledge graph-based persistent memory storage",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-memory"],
    env={"MEMORY_FILE_PATH": "data/memory.jsonl"},
    guardrail_rules=ServerGuardrailRules(
        read_only_tools={"search_nodes", "open_nodes", "read_graph"},
        custom_check=check_memory_access,
    ),
)
```

#### sequential_thinking.py
```python
from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="sequential-thinking",
    name="Sequential Thinking",
    description="Dynamic problem-solving through structured thought sequences",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
)
```

#### github.py
```python
import os

from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="github",
    name="GitHub",
    description="GitHub API integration for repository management",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", "")},
    requires_env=["GITHUB_TOKEN"],
    tool_prefix="gh",
)
```

#### sentry.py
```python
import os

from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="sentry",
    name="Sentry",
    description="Error monitoring, issue tracking, and AI-powered debugging",
    command="npx",
    args=["-y", "@sentry/mcp-server@latest"],
    env={"SENTRY_ACCESS_TOKEN": os.environ.get("SENTRY_ACCESS_TOKEN", "")},
    requires_env=["SENTRY_ACCESS_TOKEN"],
    tool_prefix="sentry",
)
```

#### playwright.py
```python
from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="playwright",
    name="Playwright",
    description="Browser automation for web testing, scraping, and interactions",
    command="npx",
    args=["-y", "@playwright/mcp@latest", "--headless", "--viewport-size=1920x1080"],
)
```

</details>

---

## 테스트 작성

MCP 서버 테스트는 `tests/tools/`에 작성합니다.

```python
# tests/tools/test_mcp_registry.py
from src.tools.mcp_registry import _registered_servers, register_mcp_server


class TestMyServer:
    def setup_method(self):
        _registered_servers.clear()

    def teardown_method(self):
        _registered_servers.clear()

    def test_server_registers(self):
        # Import triggers registration
        import src.tools.mcp.my_server  # noqa: F401

        assert "my-server" in _registered_servers
        config = _registered_servers["my-server"]
        assert config.name == "My Server"
        assert config.command == "npx"
```

---

## 체크리스트

```markdown
□ 1. src/tools/mcp/ 에 서버 파일 생성
□ 2. register_mcp_server() 호출 (모듈 레벨)
□ 3. key가 기존 서버와 중복되지 않는지 확인
□ 4. 필수 환경 변수 → requires_env에 추가
□ 5. 환경 변수 → .env에 추가
□ 6. 도구 이름 충돌 가능성 → tool_prefix 설정
□ 7. 보안 규칙 → guardrail_rules 정의 (쓰기 도구, 민감 패턴)
□ 8. tests/tools/에 테스트 추가 (선택)
□ 9. make run으로 서버 등록 확인
```

---

**Last Updated**: 2026-02-05
