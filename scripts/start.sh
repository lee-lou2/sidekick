#!/usr/bin/env bash
# =============================================================================
# Sidekick 자동 설정 및 실행 스크립트
# Mac/Linux/Windows(Git Bash, WSL) 지원
# =============================================================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# =============================================================================
# OS 감지
# =============================================================================
detect_os() {
    case "$(uname -s)" in
        Darwin*)    OS="mac" ;;
        Linux*)     OS="linux" ;;
        CYGWIN*|MINGW*|MSYS*|MINGW32*|MINGW64*)
                    OS="windows" ;;
        *)          OS="unknown" ;;
    esac
    
    info "운영체제 감지: $OS ($(uname -s))"
    
    if [[ "$OS" == "unknown" ]]; then
        error "지원하지 않는 운영체제입니다: $(uname -s)"
    fi
}

# =============================================================================
# uv 설치 확인 및 설치
# =============================================================================
install_uv() {
    if command -v uv &> /dev/null; then
        UV_VERSION=$(uv --version 2>/dev/null | head -1)
        success "uv 이미 설치됨: $UV_VERSION"
        return 0
    fi
    
    info "uv 설치 중..."
    
    case "$OS" in
        mac|linux)
            curl -LsSf https://astral.sh/uv/install.sh | sh
            ;;
        windows)
            # Windows (Git Bash / MSYS2)
            if command -v powershell &> /dev/null; then
                powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
            else
                curl -LsSf https://astral.sh/uv/install.sh | sh
            fi
            ;;
    esac
    
    # PATH 새로고침
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    
    # Windows의 경우 추가 경로
    if [[ "$OS" == "windows" ]]; then
        export PATH="$LOCALAPPDATA/uv:$APPDATA/uv:$PATH"
    fi
    
    if command -v uv &> /dev/null; then
        success "uv 설치 완료: $(uv --version)"
    else
        error "uv 설치 실패. 수동으로 설치해주세요: https://docs.astral.sh/uv/getting-started/installation/"
    fi
}

# =============================================================================
# Python 버전 확인
# =============================================================================
check_python() {
    REQUIRED_VERSION="3.10"
    
    # uv가 Python을 찾거나 설치할 수 있는지 확인
    info "Python 버전 확인 중... (필요: >= $REQUIRED_VERSION)"
    
    # uv python list로 사용 가능한 Python 확인
    if uv python list 2>/dev/null | grep -q "3.1[0-9]"; then
        PYTHON_VERSION=$(uv python list 2>/dev/null | grep -E "3\.(1[0-9]|[2-9][0-9])" | head -1 | awk '{print $1}')
        success "사용 가능한 Python: $PYTHON_VERSION"
        return 0
    fi
    
    # 시스템 Python 확인
    if command -v python3 &> /dev/null; then
        SYSTEM_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$SYSTEM_VERSION" | sort -V | head -n1)" == "$REQUIRED_VERSION" ]]; then
            success "시스템 Python 사용: $SYSTEM_VERSION"
            return 0
        fi
    fi
    
    # Python 설치
    info "Python $REQUIRED_VERSION+ 설치 중..."
    uv python install 3.12
    success "Python 3.12 설치 완료"
}

# =============================================================================
# 가상환경 및 의존성 설치
# =============================================================================
setup_venv() {
    info "의존성 설치 중 (uv sync)..."
    
    # uv sync는 자동으로 가상환경 생성 + 의존성 설치
    if uv sync; then
        success "의존성 설치 완료"
    else
        error "의존성 설치 실패"
    fi
}

# =============================================================================
# 환경변수 파일 확인
# =============================================================================
check_env_file() {
    info "환경변수 파일 확인 중..."
    
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            warn ".env 파일이 없습니다."
            echo ""
            echo -e "${YELLOW}다음 명령어로 .env 파일을 생성하세요:${NC}"
            echo -e "  ${GREEN}cp .env.example .env${NC}"
            echo ""
            echo -e "${YELLOW}그 후 .env 파일을 편집하여 API 키를 설정하세요:${NC}"
            echo -e "  ${GREEN}nano .env${NC}  또는  ${GREEN}code .env${NC}"
            echo ""
            error ".env 파일 설정 후 다시 실행해주세요."
        else
            error ".env.example 파일이 없습니다. 저장소가 올바른지 확인하세요."
        fi
    fi
    
    success ".env 파일 존재 확인"
}

# =============================================================================
# 필수 환경변수 확인
# =============================================================================
check_required_env() {
    info "필수 환경변수 확인 중..."
    
    # .env 파일 로드
    set -a
    source .env 2>/dev/null || true
    set +a
    
    MISSING_VARS=()
    
    # 필수: GOOGLE_API_KEY 또는 GEMINI_API_KEY
    if [[ -z "${GOOGLE_API_KEY:-}" ]] && [[ -z "${GEMINI_API_KEY:-}" ]]; then
        MISSING_VARS+=("GOOGLE_API_KEY")
    fi
    
    if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
        echo ""
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}  필수 환경변수가 설정되지 않았습니다!${NC}"
        echo -e "${RED}========================================${NC}"
        echo ""
        echo -e "${YELLOW}누락된 환경변수:${NC}"
        for var in "${MISSING_VARS[@]}"; do
            echo -e "  - ${RED}$var${NC}"
        done
        echo ""
        echo -e "${YELLOW}.env 파일을 편집하여 설정하세요:${NC}"
        echo -e "  ${GREEN}nano .env${NC}  또는  ${GREEN}code .env${NC}"
        echo ""
        echo -e "${YELLOW}예시:${NC}"
        echo -e "  GOOGLE_API_KEY=your_gemini_api_key_here"
        echo ""
        error "필수 환경변수를 설정한 후 다시 실행해주세요."
    fi
    
    success "필수 환경변수 확인 완료"
    
    # 선택적 환경변수 상태 출력
    echo ""
    info "환경변수 설정 상태:"
    echo -e "  GOOGLE_API_KEY:    ${GREEN}설정됨${NC}"
    
    [[ -n "${SLACK_BOT_TOKEN:-}" ]] && echo -e "  SLACK_BOT_TOKEN:   ${GREEN}설정됨${NC}" || echo -e "  SLACK_BOT_TOKEN:   ${YELLOW}미설정 (Slack 봇 비활성화)${NC}"
    [[ -n "${SLACK_APP_TOKEN:-}" ]] && echo -e "  SLACK_APP_TOKEN:   ${GREEN}설정됨${NC}" || echo -e "  SLACK_APP_TOKEN:   ${YELLOW}미설정 (Slack 봇 비활성화)${NC}"
    [[ -n "${API_AUTH_KEY:-}" ]] && echo -e "  API_AUTH_KEY:      ${GREEN}설정됨${NC}" || echo -e "  API_AUTH_KEY:      ${YELLOW}미설정 (API 인증 비활성화)${NC}"
    [[ -n "${GITHUB_TOKEN:-}" ]] && echo -e "  GITHUB_TOKEN:      ${GREEN}설정됨${NC}" || echo -e "  GITHUB_TOKEN:      ${YELLOW}미설정 (GitHub MCP 비활성화)${NC}"
    [[ -n "${EXA_API_KEY:-}" ]] && echo -e "  EXA_API_KEY:       ${GREEN}설정됨${NC}" || echo -e "  EXA_API_KEY:       ${YELLOW}미설정 (웹 검색 비활성화)${NC}"
    echo ""
}

# =============================================================================
# 실행 모드 선택
# =============================================================================
select_run_mode() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}    실행 모드를 선택하세요${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "  1) Slack 봇 실행"
    echo "  2) REST API 서버 실행"
    echo "  3) 테스트 실행"
    echo "  4) 설정만 완료 (실행 안 함)"
    echo ""
    
    read -p "선택 (1-4, 기본값: 1): " choice
    choice=${choice:-1}
    
    case $choice in
        1)
            if [[ -z "${SLACK_BOT_TOKEN:-}" ]] || [[ -z "${SLACK_APP_TOKEN:-}" ]]; then
                error "Slack 봇 실행에는 SLACK_BOT_TOKEN과 SLACK_APP_TOKEN이 필요합니다."
            fi
            info "Slack 봇 시작 중..."
            uv run python src/interfaces/slack/bot.py
            ;;
        2)
            info "REST API 서버 시작 중..."
            echo -e "${GREEN}API 서버: http://localhost:8000${NC}"
            echo -e "${GREEN}문서: http://localhost:8000/docs${NC}"
            uv run uvicorn src.interfaces.api:app --host 0.0.0.0 --port 8000 --reload
            ;;
        3)
            info "테스트 실행 중..."
            uv run pytest tests/ -v
            ;;
        4)
            success "설정 완료! 다음 명령어로 실행할 수 있습니다:"
            echo ""
            echo -e "  Slack 봇:    ${GREEN}uv run python src/interfaces/slack/bot.py${NC}"
            echo -e "  REST API:    ${GREEN}uv run uvicorn src.interfaces.api:app --port 8000${NC}"
            echo -e "  테스트:      ${GREEN}uv run pytest tests/ -v${NC}"
            echo ""
            ;;
        *)
            warn "잘못된 선택입니다. 설정만 완료합니다."
            ;;
    esac
}

# =============================================================================
# 메인 실행
# =============================================================================
main() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}    Sidekick 자동 설정 스크립트${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # 프로젝트 루트로 이동
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
    cd "$PROJECT_ROOT"
    info "작업 디렉토리: $PROJECT_ROOT"
    
    # 각 단계 실행
    detect_os
    install_uv
    check_python
    setup_venv
    check_env_file
    check_required_env
    
    echo ""
    success "========================================="
    success "  모든 설정이 완료되었습니다!"
    success "========================================="
    
    select_run_mode
}

# 스크립트 실행
main "$@"
