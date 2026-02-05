# MCP Integration Guide

MCP (Model Context Protocol) 서버를 연결하고 구성하는 상세 가이드입니다. AI 에이전트가 외부 도구와 서비스를 활용할 수 있도록 확장합니다.

> **Quick Reference**: [CLAUDE.md](../CLAUDE.md) | **Tool Creation**: [TOOL_CREATION_GUIDE.md](./TOOL_CREATION_GUIDE.md)

---

## Table of Contents

1. [MCP 개요](#mcp-개요)
2. [사용 가능한 MCP 서버](#사용-가능한-mcp-서버)
3. [기본 사용법](#기본-사용법)
4. [서버 설정](#서버-설정)
5. [보안 Guardrails](#보안-guardrails)
6. [새 MCP 서버 추가](#새-mcp-서버-추가)
7. [트러블슈팅](#트러블슈팅)
8. [고급 패턴](#고급-패턴)

---

## MCP 개요

### MCP란?

MCP (Model Context Protocol)는 AI 에이전트가 외부 도구와 데이터 소스에 접근할 수 있게 하는 프로토콜입니다.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent     │────▶│ MCP Client  │────▶│ MCP Server  │
│(Pydantic AI)│     │ (MCPManager)│     │ (filesystem)│
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ Guardrails  │
                    │ (Security)  │
                    └─────────────┘
```

### 주요 컴포넌트

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| `MCPManager` | `src/tools/mcp_client.py` | 다중 MCP 서버 연결 관리 |
| `MCPServerConfig` | `src/tools/mcp_registry.py` | 개별 서버 설정 정의 |
| `GuardrailConfig` | `src/middleware/guardrails/core.py` | 보안 정책 설정 |
| `ServerGuardrailRules` | `src/tools/mcp_registry.py` | 서버별 보안 규칙 정의 |
| `PlaywrightCleanupTracker` | `src/tools/mcp/playwright.py` | Playwright 브라우저/파일 정리 |

---

## 사용 가능한 MCP 서버

### 기본 제공 서버

| 서버 | 설명 | 환경 변수 | 상태 |
|------|------|-----------|------|
| `filesystem` | 파일 읽기/쓰기/목록 | 없음 | 항상 사용 가능 |
| `fetch` | 웹 콘텐츠 가져오기 | 없음 | 항상 사용 가능 |
| `git` | Git 저장소 작업 | 없음 | 항상 사용 가능 |
| `memory` | 지식 그래프 저장소 | 없음 | 항상 사용 가능 |
| `sequential-thinking` | 단계별 추론 (느림) | 없음 | 항상 사용 가능 |
| `playwright` | 브라우저 자동화 | 없음 | 항상 사용 가능 |
| `github` | GitHub API | `GITHUB_TOKEN` | 토큰 필요 |
| `sentry` | 에러 모니터링 | `SENTRY_ACCESS_TOKEN` | 토큰 필요 |

### 서버별 도구 목록

#### filesystem
```
read_file(path)           # 파일 내용 읽기
read_multiple_files(paths) # 여러 파일 읽기
write_file(path, content)  # 파일 쓰기 (guardrails로 차단됨)
list_directory(path)       # 디렉토리 목록
create_directory(path)     # 디렉토리 생성 (guardrails로 차단됨)
search_files(pattern)      # 파일 검색
get_file_info(path)        # 파일 정보
directory_tree(path)       # 디렉토리 트리
```

#### git
```
git_status()              # 워킹 트리 상태
git_diff()                # 변경 사항 표시
git_log(n)                # 최근 n개 커밋
git_show(commit)          # 커밋 상세 정보
git_blame(file)           # 파일 blame
git_commit(message)       # 커밋 (guardrails로 차단됨)
git_push()                # 푸시 (guardrails로 차단됨)
```

#### github (GITHUB_TOKEN 필요)
```
list_issues(repo)                    # 이슈 목록
get_issue(repo, number)              # 이슈 상세
create_issue(repo, title, body)      # 이슈 생성 (guardrails로 차단됨)
list_pull_requests(repo)             # PR 목록
get_pull_request(repo, number)       # PR 상세
create_pull_request(...)             # PR 생성 (guardrails로 차단됨)
search_code(query)                   # 코드 검색
```

#### memory
```
create_entities(entities)    # 엔티티 생성 (guardrails로 차단됨)
create_relations(relations)  # 관계 생성 (guardrails로 차단됨)
search_nodes(query)          # 노드 검색
read_graph()                 # 전체 그래프 읽기
```

#### fetch
```
fetch(url)                  # 웹 페이지 가져오기
```

#### playwright
```
browser_navigate(url)       # URL로 이동
browser_click(selector)     # 요소 클릭
browser_fill(selector, value) # 입력 필드 채우기
browser_screenshot()        # 스크린샷 촬영
browser_get_text(selector)  # 텍스트 추출
```

---

## 기본 사용법

### AgentRunner와 함께 사용

```python
from src.core.agent import AgentRunner

# MCP 포함하여 에이전트 실행 (async context manager 권장)
async with AgentRunner(enable_mcp=True) as agent:
    result = await agent.run_async("Show the current git status")
    print(result.output)

# Sync context manager (Playwright 브라우저 정리는 async에서만 완전 지원)
with AgentRunner(enable_mcp=True) as agent:
    result = agent.run("Show the current git status")
    print(result.output)
```

### 특정 MCP 서버만 사용

```python
# filesystem과 git 서버만 사용
async with AgentRunner(enable_mcp=True, mcp_servers=["filesystem", "git"]) as agent:
    result = await agent.run_async("List files and show git status")
    print(result.output)
```

### MCPManager 직접 사용

```python
from src.tools.mcp_client import MCPManager

# 모든 사용 가능한 서버 연결
manager = MCPManager()
manager.connect_all()

print(f"Server count: {manager.get_server_count()}")
print(f"Server count: {manager.get_server_count()}")

# 정리
manager.disconnect_all()
```

### AgentFactory 패턴

```python
from src.core.agent import AgentFactory

# 동시 요청 처리를 위한 팩토리
async with AgentFactory(enable_mcp=True) as factory:
    # 각 요청마다 새 에이전트 생성
    agent = factory.create_agent()
    result = await agent.run("Show git status")
```

---

## 서버 설정

### MCPServerConfig 구조

```python
# src/tools/mcp_registry.py
from dataclasses import dataclass, field

@dataclass
class MCPServerConfig:
    name: str                              # 서버 이름
    description: str                       # 설명
    command: str                           # 실행 명령어 (npx, uvx 등)
    args: list[str]                        # 명령어 인자
    env: dict[str, str] = field(default_factory=dict)  # 환경 변수
    enabled: bool = True                   # 활성화 여부
    requires_env: list[str] = field(default_factory=list)  # 필수 환경 변수
    tool_prefix: str | None = None         # 도구 이름 접두사
    guardrail_rules: ServerGuardrailRules | None = None  # 서버별 보안 규칙
```

### 기존 서버 설정 확인

```python
# 현재 등록된 서버 확인
from src.tools.mcp_registry import get_mcp_servers

# 모든 서버 설정
for name, config in get_mcp_servers().items():
    print(f"{name}: {config.description}")
    print(f"  Command: {config.command} {' '.join(config.args)}")
    print(f"  Available: {config.is_available()}")
    print()

# 사용 가능한 서버만
available = {k: v for k, v in get_mcp_servers().items() if v.is_available()}
print(f"Available servers: {list(available.keys())}")
```

### 환경 변수 설정

```bash
# .env 파일
GOOGLE_API_KEY=your-gemini-api-key

# GitHub MCP 서버용
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Sentry MCP 서버용
SENTRY_ACCESS_TOKEN=sntrys_xxxxxxxxxxxx
```

---

## 보안 Guardrails

### 기본 동작

Guardrails는 **기본으로 활성화**되어 있습니다:
- 민감한 파일 접근 차단 (`.env`, 자격 증명 등)
- 쓰기 작업 차단 (읽기 전용 모드)

```python
from src.tools.mcp_client import MCPManager

# 기본: guardrails 활성화
manager = MCPManager()  # enable_guardrails=True (기본값)

# guardrails 비활성화 (위험!)
manager = MCPManager(enable_guardrails=False)
```

### 서버별 규칙 정의

**Guardrail 규칙은 이제 각 MCP 서버 파일에서 정의됩니다.** 이를 통해 서버마다 맞춤형 보안 정책을 적용할 수 있습니다.

```python
# src/tools/mcp/filesystem.py
from src.tools.mcp_registry import ServerGuardrailRules, register_mcp_server

register_mcp_server(
    key="filesystem",
    ...
    guardrail_rules=ServerGuardrailRules(
        write_tools={"write_file", "edit_file", "delete_file", "create_directory"},
        sensitive_file_patterns={
            ".env", ".env.*", "*.env",
            ".aws/credentials", ".aws/config",
            ".ssh/*", "id_rsa*", "*.pem", "*.key",
            "*secret*", "*credential*", "*password*", "*token*",
        },
    ),
)
```

### 규칙 집계

`GuardrailEnforcer`는 모든 서버의 규칙을 자동으로 집계합니다:

```python
# src/middleware/guardrails/enforcer.py
class GuardrailEnforcer:
    def __init__(self, config: GuardrailConfig):
        # 모든 등록된 서버의 guardrail_rules를 집계
        for server_config in get_mcp_servers().values():
            if server_config.guardrail_rules:
                # write_tools, sensitive_patterns 통합
                self._write_tools.update(server_config.guardrail_rules.write_tools)
                self._sensitive_patterns.update(server_config.guardrail_rules.sensitive_patterns)
```

### 주요 서버별 규칙 예시

| 서버 | 민감 파일 패턴 | 쓰기 도구 |
|------|---------------|----------|
| `filesystem` | `.env*`, `.aws/*`, `*.key`, `*.pem`, `*secret*`, `*password*` | `write_file`, `edit_file`, `delete_file`, `create_directory` |
| `git` | - | `git_commit`, `git_push`, `git_reset`, `git_rebase` |
| `github` | - | `create_issue`, `create_pull_request`, `merge_pull_request` |
| `memory` | - | *(custom_check로 사용자 격리 - write_tools 미사용)* |

### 커스텀 Guardrail 설정

서버별 규칙 외에 추가 규칙을 `GuardrailConfig`로 지정할 수 있습니다:

```python
from src.tools.mcp_client import MCPManager
from src.middleware.guardrails import GuardrailConfig

# 커스텀 설정 (서버별 규칙에 추가됨)
config = GuardrailConfig(
    read_only=True,                    # 쓰기 작업 차단
    block_sensitive_files=True,        # 민감 파일 차단
    sensitive_patterns={".my_secret"}, # 추가 차단 패턴 (서버 규칙에 추가)
    safe_patterns={"config.json"},     # 예외 허용 패턴
    blocked_tools={"dangerous_tool"},  # 추가 차단 도구 (서버 규칙에 추가)
    log_blocked_attempts=True,         # 차단 로그 기록
)

manager = MCPManager(guardrail_config=config)
manager.connect_all()
```

**참고**: `GuardrailConfig`의 설정은 서버별 `ServerGuardrailRules`와 **병합**됩니다. 즉, 양쪽의 규칙이 모두 적용됩니다.

### Guardrail 예외 처리

```python
from src.middleware.guardrails import GuardrailViolation

try:
    # 민감한 파일 접근 시도
    result = guarded_tool.forward(path=".env")
except GuardrailViolation as e:
    print(f"Blocked: {e.message}")
    print(f"Tool: {e.tool_name}")
    print(f"Type: {e.violation_type}")  # "sensitive_file" 또는 "write_operation"
```

### Whitelist 모드

```python
# 특정 도구만 허용
config = GuardrailConfig(
    allowed_tools={"read_file", "list_directory", "git_status"},
    # allowed_tools가 설정되면 이 목록에 있는 도구만 사용 가능
)

manager = MCPManager(guardrail_config=config)
```

---

## 새 MCP 서버 추가

> 상세 가이드: [MCP_SERVER_GUIDE.md](./MCP_SERVER_GUIDE.md)

`register_mcp_server()` 패턴을 사용하여 **파일 하나만 추가**하면 MCP 서버가 자동 등록됩니다.

### Step 1: 서버 파일 생성

```python
# src/tools/mcp/my_server.py
import os

from src.tools.mcp_registry import register_mcp_server

register_mcp_server(
    key="my-server",
    name="My Server",
    description="Custom MCP server for specific functionality",
    command="npx",
    args=["-y", "@my-org/mcp-server-name"],
    env={"MY_API_KEY": os.environ.get("MY_API_KEY", "")},
    requires_env=["MY_API_KEY"],
)
```

### Step 2: 환경 변수 설정

```bash
# .env 파일에 추가
MY_API_KEY=your-api-key-here
```

### Step 3: 사용 확인

```python
from src.tools.mcp_client import MCPManager

manager = MCPManager()
manager.connect("my-server")

print(f"Server count: {manager.get_server_count()}")
```

### MCP 서버 유형

| 패키지 관리자 | 명령어 | 예시 |
|---------------|--------|------|
| npm (Node.js) | `npx` | `npx -y @modelcontextprotocol/server-filesystem` |
| uv (Python) | `uvx` | `uvx mcp-server-fetch` |
| pip (Python) | `python -m` | `python -m mcp_server` |

---

## 트러블슈팅

### 일반적인 문제

#### 서버 연결 실패

```python
# 문제: "MCP server 'github' requires environment variables: ['GITHUB_TOKEN']"

# 해결:
# 1. .env 파일에 환경 변수 추가
# 2. 또는 export GITHUB_TOKEN=ghp_xxx
```

#### Node.js 관련 오류

```bash
# 문제: npx command not found

# 해결: Node.js 설치
brew install node  # macOS
# 또는
nvm install --lts
```

#### 도구 스키마 오류 (Gemini)

```python
# 문제: "anyOf" 스키마 오류

# 해결: MCPManager가 Gemini 호환성을 위해 자동 처리
# src/tools/mcp_client.py 참조
```

### 디버깅

```python
import logging

# MCP 로깅 활성화
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("src.tools.mcp").setLevel(logging.DEBUG)
logging.getLogger("src.middleware.guardrails").setLevel(logging.DEBUG)

# 연결 테스트
from src.tools.mcp_client import MCPManager

manager = MCPManager()
try:
    manager.connect("filesystem")
    print(f"Success: {manager.get_server_count()} servers")
except Exception as e:
    print(f"Error: {e}")
```

### Guardrail 차단 디버깅

```python
import logging

# Guardrail 로깅 활성화
logging.getLogger("src.middleware.guardrails").setLevel(logging.DEBUG)

# 차단된 시도 확인
from src.middleware.guardrails import GuardrailConfig

config = GuardrailConfig(
    log_blocked_attempts=True,  # 차단 로그 기록
)
```

---

## 고급 패턴

### AgentFactory로 동시성 처리

```python
from src.core.agent import AgentFactory

# 공유 리소스로 팩토리 생성
async with AgentFactory(enable_mcp=True) as factory:
    # 각 요청마다 새 에이전트 생성 (격리됨)
    agent1 = factory.create_agent()
    agent2 = factory.create_agent()

    # 병렬 실행 가능 (각 에이전트는 독립적)
    result1 = await agent1.run("Task 1")
    result2 = await agent2.run("Task 2")
```

### 사용자 컨텍스트와 메모리

```python
from src.core.agent import AgentRunner

async with AgentRunner(enable_mcp=True) as agent:
    # 사용자별 컨텍스트 포함
    result = await agent.run_with_user(
        task="What files did I work on recently?",
        user_id="user123",
        platform="slack"
    )
    print(result.output)
```

### 커스텀 도구 보호

```python
from src.middleware.guardrails import GuardrailEnforcer, GuardrailConfig

# GuardrailEnforcer로 모든 도구 유형 보호
config = GuardrailConfig(
    read_only=False,  # 쓰기 허용
    sensitive_patterns={".custom_secret"},
)

enforcer = GuardrailEnforcer(config)
enforcer.validate_tool_call("my_tool", {"path": ".env"})  # Raises!
```

---

## Playwright Cleanup

Playwright MCP 사용 시 브라우저 미종료 및 임시 파일 누적 문제를 방지하기 위한 자동 정리 기능.

### 자동 정리 (기본 활성화)

```python
from src.core.agent import AgentRunner

# Async context manager 사용 시 자동 정리 (권장)
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

### 주의사항

| 컨텍스트 | 정리 범위 |
|---------|----------|
| `async with AgentRunner()` | 브라우저 + 임시 파일 (완전 정리) |
| `with AgentRunner()` | 임시 파일만 (브라우저는 경고 로그) |

- 30분 이상 된 임시 스크린샷 파일은 자동 삭제됩니다.

---

## 참고 자료

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Servers GitHub](https://github.com/modelcontextprotocol/servers)
- [Pydantic AI MCP Integration](https://ai.pydantic.dev/mcp/)

---

**Last Updated**: 2026-02-05
