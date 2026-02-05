# Tool Creation Guide

AI 에이전트가 사용할 도구(Tool)를 생성하는 상세 가이드입니다. 이 문서는 AI가 코드를 작성할 때 참고하는 규칙과 패턴을 포함합니다.

> **Quick Reference**: [CLAUDE.md](../CLAUDE.md) | **Style Guide**: [AGENTS.md](../AGENTS.md)

---

## Table of Contents

1. [핵심 규칙](#핵심-규칙)
2. [도구 패턴](#도구-패턴)
3. [상세 구현 가이드](#상세-구현-가이드)
4. [에러 처리](#에러-처리)
5. [테스트 작성](#테스트-작성)
6. [도구 등록](#도구-등록)
7. [실전 예제](#실전-예제)

---

## 핵심 규칙

### 도구는 독립적이어야 함 (CRITICAL)

**도구 파일 하나만으로 모든 것을 완결해야 합니다. 다른 파일 수정 금지!**

```
✅ 도구 추가 시 수정하는 것:
   - src/tools/custom/my_tool.py (도구 파일)
   - .env (환경변수 - 필요한 경우)

❌ 절대 수정하면 안 되는 것:
   - src/config.py
   - src/tools/__init__.py
   - 그 외 모든 파일
```

### 반드시 지켜야 할 규칙 (MUST)

| 규칙 | 이유 | 예시 |
|------|------|------|
| **도구 파일 하나로 완결** | 독립성, 설치 용이성 | 다른 파일 수정 금지 |
| **환경변수는 `os.getenv()` 사용** | config.py 수정 불필요 | `os.getenv("MY_API_KEY")` |
| **최소 1개 파라미터** | Gemini API 호환성 | `def tool(query: str)` |
| **모든 파라미터에 타입 힌트** | 스키마 자동 생성 | `a: float, b: float` |
| **반환값 타입 힌트** | 출력 타입 검증 | `-> str`, `-> dict` |
| **Google 스타일 docstring** | 도구 설명 자동 추출 | Args, Returns 섹션 필수 |
| **`src/tools/custom/` 디렉토리에 배치** | 도구 구조화 | `src/tools/custom/my_tool.py` |
| **`@register_tool` 데코레이터 사용** | 도구 자동 등록 | 수동 등록 불필요 |

### 절대 하지 말아야 할 것 (MUST NOT)

```python
# ❌ BAD: config.py 수정 (절대 금지!)
from src.config import settings
api_key = settings.my_api_key  # config.py에 필드 추가해야 함

# ❌ BAD: 파라미터 없음 (Gemini 오류 발생)
def get_time() -> str:
    return datetime.now().isoformat()

# ❌ BAD: 타입 힌트 없음
def search(query):
    pass

# ❌ BAD: docstring 없음
def process(data: str) -> str:
    return data.upper()
```

### 올바른 예시 (GOOD)

```python
# ✅ GOOD: 모든 규칙 준수
from src.tools.registry import register_tool
from datetime import datetime

@register_tool
def get_time(format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get current time in specified format.

    Args:
        format_string: Time format string (default: ISO-like format).

    Returns:
        Formatted current time string.
    """
    return datetime.now().strftime(format_string)
```

---

## 도구 패턴

### Pattern: Plain Python Function

**사용 시점:**
- 모든 도구 (기본 패턴)
- Stateless 연산
- 단순 변환/계산
- API 호출

```python
# src/tools/custom/text_utils.py
from src.tools.registry import register_tool

@register_tool
def word_count(text: str, include_spaces: bool = False) -> str:
    """Count words in text.

    Args:
        text: Input text to count words from.
        include_spaces: If True, include whitespace characters in count.

    Returns:
        Word count as formatted string.
    """
    count = len(text.split())
    return f"Word count: {count}"
```

### Pattern: External API Tool

**사용 시점:**
- API 키/설정 필요
- 무거운 초기화 (ML 모델, DB 연결)
- 재사용 가능한 클라이언트

```python
# src/tools/custom/weather.py
import os
from typing import Optional

from src.tools.registry import register_tool

_client: Optional[WeatherAPI] = None

def _get_api_key() -> str:
    """Get API key from environment."""
    key = os.getenv("WEATHER_API_KEY")
    if not key:
        raise ValueError("WEATHER_API_KEY 환경변수를 설정하세요.")
    return key

def _get_client() -> WeatherAPI:
    """Get or initialize the client."""
    global _client
    if _client is None:
        _client = WeatherAPI(api_key=_get_api_key())
    return _client

@register_tool
def get_weather(location: str, units: str = "metric") -> str:
    """Get current weather information for a specified location.

    Args:
        location: City name (e.g., 'Seoul, Korea', 'New York, US').
        units: Temperature units: 'metric' (Celsius) or 'imperial' (Fahrenheit).

    Returns:
        Formatted weather information string.
    """
    try:
        client = _get_client()
        data = client.fetch(location, units)
        return f"Weather in {location}: {data.temp}°, {data.condition}"
    except ValueError as e:
        return f"설정 오류: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"
```

**환경변수 추가 (.env):**
```bash
WEATHER_API_KEY=your_api_key_here
```

**이것만 하면 끝!** `config.py` 수정 불필요.

---

## 상세 구현 가이드

### 파일 구조

```
src/tools/
├── __init__.py           # get_custom_toolset()
├── catalog.py            # ToolCatalog - 통합 도구 관리
├── registry.py           # @register_tool 데코레이터
├── mcp_registry.py       # MCPServerConfig, ServerGuardrailRules, register_mcp_server()
├── mcp_client.py         # MCPManager (다중 MCP 서버 연결)
├── mcp/                  # MCP 서버 정의 (register_mcp_server, gitignored)
│   └── *.py              # 각 MCP 서버 설정 파일
└── custom/               # 커스텀 도구 (@register_tool, gitignored)
    └── my_tool.py        # 사용자별 도구 파일들
```

### 네이밍 컨벤션

| 요소 | 스타일 | 예시 |
|------|--------|------|
| 파일명 | `snake_case` | `exa_search.py` |
| 함수명 | `snake_case` | `exa_search`, `get_weather` |
| 상수 | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |

### Import 구성

```python
# 1. 표준 라이브러리
import os
from typing import Optional

# 2. 서드파티 패키지
import httpx

# 3. 로컬 임포트 (registry만!)
from src.tools.registry import register_tool

# ❌ 금지: config.py import
# from src.config import settings  # 이거 쓰지 마세요!
```

---

## 에러 처리

### 기본 에러 처리 패턴

```python
def fetch_data(url: str) -> str:
    """Fetch data from URL.

    Args:
        url: URL to fetch data from.

    Returns:
        Response content or error message.
    """
    # 입력 검증
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

### 에러 메시지 가이드라인

```python
# ✅ GOOD: 명확하고 actionable한 에러 메시지
return "Error: API key not found. Set OPENWEATHER_API_KEY environment variable."
return "Error: Invalid date format. Use YYYY-MM-DD (e.g., 2024-01-15)."
return "Error: Query too long. Maximum 500 characters allowed."

# ❌ BAD: 모호하거나 기술적인 에러 메시지
return "Error occurred"
return f"Exception: {e}"
return "NoneType error"
```

---

## 테스트 작성

### 기본 테스트 구조

```python
# tests/tools/test_text_utils.py
import pytest
from src.tools.custom.text_utils import word_count

class TestWordCount:
    """Tests for word_count tool."""

    def test_basic_count(self):
        """Test basic word counting."""
        result = word_count("hello world")
        assert "2" in result

    def test_empty_string(self):
        """Test with empty string."""
        result = word_count("")
        assert "0" in result

    def test_multiple_spaces(self):
        """Test with multiple spaces between words."""
        result = word_count("hello    world")
        assert "2" in result
```

### External API 도구 테스트

```python
# tests/tools/test_weather.py
import pytest
from unittest.mock import patch, Mock
from src.tools.custom.weather import get_weather

class TestGetWeather:
    """Tests for get_weather tool."""

    def test_missing_api_key(self):
        """Test error when API key is missing."""
        with patch.dict('os.environ', {}, clear=True):
            # Reset client
            import src.tools.weather as weather_module
            weather_module._client = None

            result = get_weather("Seoul")
            assert "Configuration error" in result or "Error" in result

    @patch('src.tools.weather._get_client')
    def test_successful_fetch(self, mock_get_client):
        """Test successful weather fetch."""
        mock_client = Mock()
        mock_client.fetch.return_value = Mock(temp=22, condition="Sunny")
        mock_get_client.return_value = mock_client

        result = get_weather("Seoul")
        assert "Seoul" in result
        assert "22" in result
```

### 테스트 실행

```bash
# 특정 테스트 파일 실행
uv run pytest tests/tools/test_text_utils.py -v

# 특정 테스트 함수 실행
uv run pytest tests/tools/test_text_utils.py::TestWordCount::test_basic_count -v

# 커스텀 도구 테스트만 실행
uv run pytest tests/tools/ -v

# 전체 테스트 (코어 + 커스텀 도구)
uv run pytest tests/ -v

# 실패한 테스트만 재실행
uv run pytest tests/ --lf
```

---

## 도구 등록

### 자동 등록 시스템

`@register_tool` 데코레이터를 사용하면 도구가 자동으로 등록됩니다. **수동으로 `__init__.py`를 수정할 필요가 없습니다!**

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

### 등록 동작 원리

1. `@register_tool` 데코레이터가 함수 이름을 `_registered_tools` 집합에 저장
2. `auto_register_tools()`가 `src/tools/custom/` 디렉토리를 스캔하고 모든 모듈 import
3. `is_tool_function()`이 데코레이터로 등록된 함수인지 확인
4. `AgentFactory`가 모든 custom, command, scheduler 도구로 toolset 생성

### 등록 체크리스트

1. **파일 생성**: `src/tools/custom/my_tool.py`
2. **함수 작성**: `@register_tool` + 타입 힌트 + docstring
3. **환경변수 추가** (필요시): `.env`에 추가 (`.env.example` 수정 금지)
4. **테스트 작성**: `tests/tools/test_my_tool.py`
5. **테스트 실행**: `uv run pytest tests/tools/test_my_tool.py -v`
6. **재시작**: `make run`

**수정하는 것:** 도구 파일 + `.env` (필요시)
**수정 금지:** `config.py`, `__init__.py`, `.env.example`, 그 외 모든 파일

---

## 실전 예제

### 예제 1: 웹 검색 도구 (Exa AI)

```python
# src/tools/custom/exa_search.py
import os
from typing import Optional

from exa_py import Exa

from src.tools.registry import register_tool

_exa_client: Optional[Exa] = None

def _get_exa_client() -> Exa:
    global _exa_client
    if _exa_client is None:
        api_key = os.getenv("EXA_API_KEY")
        if not api_key:
            raise ValueError("EXA_API_KEY 환경변수를 설정하세요.")
        _exa_client = Exa(api_key=api_key)
    return _exa_client

@register_tool
def exa_search(
    query: str,
    num_results: int = 5,
    category: str | None = None,
) -> str:
    """Search the web using Exa AI's neural search.

    Args:
        query: Search query to find relevant web content.
        num_results: Number of results (default: 5, max: 100).
        category: Content type: 'research paper', 'news', 'github', etc.

    Returns:
        Formatted search results string.
    """
    params = {"query": query, "num_results": num_results, "text": True}
    if category:
        params["category"] = category

    try:
        client = _get_exa_client()
        response = client.search_and_contents(**params)
    except ValueError as e:
        return f"설정 오류: {str(e)}"
    except Exception as e:
        return f"검색 실패: {str(e)}"

    if not response.results:
        return f"결과 없음: {query}"

    results = []
    for i, r in enumerate(response.results, 1):
        text = f"[{i}] {r.title}\n    URL: {r.url}"
        if hasattr(r, "text") and r.text:
            snippet = r.text[:300] + "..." if len(r.text) > 300 else r.text
            text += f"\n    Content: {snippet}"
        results.append(text)

    return f"Found {len(response.results)} results:\n\n" + "\n\n".join(results)
```

**.env에 추가:**
```bash
EXA_API_KEY=your_exa_api_key_here
```

### 예제 2: 간단한 계산기

```python
# src/tools/custom/calculator.py
import math
from src.tools.registry import register_tool

@register_tool
def calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression.

    Supports basic arithmetic: +, -, *, /, **, (), sqrt, abs.

    Args:
        expression: Mathematical expression to evaluate (e.g., '2 + 3 * 4').

    Returns:
        Calculation result or error message.
    """
    # 허용된 이름들
    allowed_names = {
        "sqrt": math.sqrt,
        "abs": abs,
        "pow": pow,
        "round": round,
        "min": min,
        "max": max,
    }

    # 위험한 문자 검사
    dangerous = ["import", "exec", "eval", "__", "open", "file"]
    if any(d in expression.lower() for d in dangerous):
        return "Error: Expression contains forbidden terms"

    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return f"Result: {result}"
    except ZeroDivisionError:
        return "Error: Division by zero"
    except SyntaxError:
        return f"Error: Invalid expression syntax: {expression}"
    except Exception as e:
        return f"Error: Calculation failed - {str(e)}"
```

### 예제 3: HTTP GET 요청

```python
# src/tools/custom/http_client.py
import httpx
from src.tools.registry import register_tool

@register_tool
def http_get(url: str, timeout: int = 30) -> str:
    """Perform HTTP GET request.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds (default: 30).

    Returns:
        Response body or error message.
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()

        content = response.text
        if len(content) > 10000:
            content = content[:10000] + "\n... (truncated)"
        return content

    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout}s"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: Request failed - {str(e)}"
```

---

## 체크리스트

새 도구를 만들 때 다음 체크리스트를 확인하세요:

### 필수 요구사항

- [ ] **도구 파일 하나만 수정** (다른 파일 수정 금지!)
- [ ] **환경변수는 `os.getenv()` 사용** (config.py 사용 금지)
- [ ] 최소 1개의 파라미터가 있음 (Gemini 요구사항)
- [ ] 모든 파라미터에 타입 힌트 있음
- [ ] 반환 타입 힌트 있음
- [ ] Google 스타일 docstring 작성 (Args, Returns 섹션)
- [ ] `src/tools/custom/` 디렉토리에 파일 위치
- [ ] `@register_tool` 데코레이터 사용

### 권장 사항

- [ ] 에러 처리가 사용자 친화적
- [ ] 테스트 파일 생성 (`tests/tools/test_*.py`)

### 배포 전 확인

- [ ] `uv run pytest tests/tools/test_<tool_name>.py -v` 통과
- [ ] 로컬에서 수동 테스트 완료
- [ ] `.env`에 필요한 환경변수 추가됨

---

## 참고 자료

- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [pytest Documentation](https://docs.pytest.org/)

---

**Last Updated**: 2026-02-05
