#!/usr/bin/env bash
# =============================================================================
# Sidekick 원클릭 설치 스크립트
#
# 사용법 (아무 폴더에서 실행):
#   curl -fsSL https://raw.githubusercontent.com/lee-lou2/sidekick/main/install.sh | bash
# 또는:
#   wget -qO- https://raw.githubusercontent.com/lee-lou2/sidekick/main/install.sh | bash
#
# 옵션:
#   INSTALL_DIR=~/my-agent bash -c "$(curl -fsSL ...)"  # 설치 경로 지정
#   SKIP_ENV=1 bash -c "$(curl -fsSL ...)"              # .env 설정 건너뛰기
# =============================================================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# 로그 함수
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 설정
REPO_URL="https://github.com/lee-lou2/sidekick.git"
REPO_NAME="sidekick"
DEFAULT_INSTALL_DIR="$(pwd)/$REPO_NAME"
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

# =============================================================================
# 배너 출력
# =============================================================================
print_banner() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                               ║${NC}"
    echo -e "${GREEN}║   ${BOLD}🤖 Sidekick 설치 스크립트${NC}${GREEN}                  ║${NC}"
    echo -e "${GREEN}║                                                               ║${NC}"
    echo -e "${GREEN}║   대화를 기억하고, 작업을 예약하고,                                   ║${NC}"
    echo -e "${GREEN}║   나만의 명령어를 만들 수 있는 개인용 AI 에이전트                        ║${NC}"
    echo -e "${GREEN}║                                                               ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# =============================================================================
# 필수 도구 확인
# =============================================================================
check_requirements() {
    info "필수 도구 확인 중..."
    
    # git 확인
    if ! command -v git &> /dev/null; then
        echo ""
        error "git이 설치되어 있지 않습니다. 먼저 git을 설치해주세요.

  macOS:   brew install git
  Ubuntu:  sudo apt install git
  Windows: https://git-scm.com/download/win"
    fi
    success "git 확인됨: $(git --version)"
    
    # make 확인
    if ! command -v make &> /dev/null; then
        echo ""
        error "make가 설치되어 있지 않습니다. 먼저 make를 설치해주세요.

  macOS:   xcode-select --install
  Ubuntu:  sudo apt install build-essential
  Windows: WSL 사용 권장"
    fi
    success "make 확인됨: $(make --version | head -1)"
    
    # curl 또는 wget 확인 (다운로드용)
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        warn "curl/wget이 없지만 계속 진행합니다."
    fi
}

# =============================================================================
# 레포지토리 클론
# =============================================================================
clone_repository() {
    info "설치 경로: $INSTALL_DIR"
    
    if [ -d "$INSTALL_DIR" ]; then
        echo ""
        warn "이미 디렉토리가 존재합니다: $INSTALL_DIR"
        echo ""
        echo -e "  ${CYAN}1)${NC} 삭제하고 새로 설치"
        echo -e "  ${CYAN}2)${NC} 기존 디렉토리 사용 (git pull)"
        echo -e "  ${CYAN}3)${NC} 설치 취소"
        echo ""
        read -p "선택하세요 (1-3): " choice
        
        case $choice in
            1)
                info "기존 디렉토리 삭제 중..."
                rm -rf "$INSTALL_DIR"
                ;;
            2)
                info "기존 디렉토리에서 최신 코드 가져오는 중..."
                cd "$INSTALL_DIR"
                git pull origin main || git pull origin master || warn "git pull 실패. 기존 코드 사용."
                success "업데이트 완료"
                return 0
                ;;
            3|*)
                info "설치를 취소합니다."
                exit 0
                ;;
        esac
    fi
    
    info "저장소 클론 중: $REPO_URL"
    
    if git clone "$REPO_URL" "$INSTALL_DIR"; then
        success "클론 완료"
    else
        error "저장소 클론 실패. 네트워크 연결을 확인하세요."
    fi
    
    cd "$INSTALL_DIR"
}

# =============================================================================
# uv 설치
# =============================================================================
install_uv() {
    if command -v uv &> /dev/null; then
        success "uv 이미 설치됨: $(uv --version 2>/dev/null | head -1)"
        return 0
    fi
    
    info "uv 설치 중... (Python 패키지 매니저)"
    
    if command -v curl &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &> /dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        error "curl 또는 wget이 필요합니다."
    fi
    
    # PATH 새로고침
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    
    if command -v uv &> /dev/null; then
        success "uv 설치 완료: $(uv --version 2>/dev/null | head -1)"
    else
        warn "uv 설치됨. 터미널을 재시작하거나 다음을 실행하세요:"
        echo -e "  ${GREEN}source ~/.bashrc${NC}  또는  ${GREEN}source ~/.zshrc${NC}"
    fi
}

# =============================================================================
# 의존성 설치
# =============================================================================
install_dependencies() {
    info "의존성 설치 중 (uv sync)..."
    
    # PATH 확인 (uv가 방금 설치된 경우)
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    
    if uv sync; then
        success "의존성 설치 완료"
    else
        warn "의존성 설치 실패. 나중에 'uv sync'를 직접 실행하세요."
    fi
}

# =============================================================================
# 환경변수 설정
# =============================================================================
setup_env() {
    if [ "${SKIP_ENV:-}" = "1" ]; then
        info ".env 설정을 건너뜁니다. (SKIP_ENV=1)"
        return 0
    fi
    
    info "환경변수 파일 설정 중..."
    
    if [ -f ".env" ]; then
        warn ".env 파일이 이미 존재합니다."
        read -p "덮어쓰시겠습니까? (y/N): " overwrite
        if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
            info ".env 파일을 유지합니다."
            return 0
        fi
    fi
    
    # .env.example 복사
    if [ -f ".env.example" ]; then
        cp .env.example .env
        success ".env 파일 생성됨"
    else
        error ".env.example 파일이 없습니다."
    fi
    
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  필수 환경변수 설정${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${YELLOW}GOOGLE_API_KEY${NC}가 필요합니다. (Gemini API)"
    echo ""
    echo -e "  API 키 발급: ${BLUE}https://aistudio.google.com/apikey${NC}"
    echo ""
    
    read -p "GOOGLE_API_KEY를 입력하세요 (Enter로 건너뛰기): " api_key
    
    if [ -n "$api_key" ]; then
        # .env 파일에서 GOOGLE_API_KEY 업데이트
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s|^GOOGLE_API_KEY=.*|GOOGLE_API_KEY=$api_key|" .env
        else
            # Linux
            sed -i "s|^GOOGLE_API_KEY=.*|GOOGLE_API_KEY=$api_key|" .env
        fi
        success "GOOGLE_API_KEY 설정됨"
    else
        warn "나중에 .env 파일을 직접 편집하세요."
    fi
    
    # 선택적 환경변수 안내
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  선택적 환경변수 (나중에 설정 가능)${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${YELLOW}Slack 봇 연동:${NC}"
    echo -e "    SLACK_BOT_TOKEN=xoxb-..."
    echo -e "    SLACK_APP_TOKEN=xapp-..."
    echo ""
    echo -e "  ${YELLOW}외부 서비스:${NC}"
    echo -e "    GITHUB_TOKEN     - MCP GitHub 연동"
    echo -e "    EXA_API_KEY      - 웹 검색 (Exa AI)"
    echo ""
    echo -e "  전체 목록: ${BLUE}.env.example${NC} 참조"
    echo ""
}

# =============================================================================
# 완료 메시지 출력
# =============================================================================
print_success() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                               ║${NC}"
    echo -e "${GREEN}║   ${BOLD}✅ 설치가 완료되었습니다!${NC}${GREEN}                                  ║${NC}"
    echo -e "${GREEN}║                                                               ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  시작하기${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${GREEN}cd $INSTALL_DIR${NC}"
    echo -e "  ${GREEN}make run${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  Make 명령어${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${GREEN}make${NC}              도움말"
    echo -e "  ${GREEN}make run${NC}          실행 (설정 + 모드 선택)"
    echo -e "  ${GREEN}make test${NC}         테스트"
    echo -e "  ${GREEN}make lint${NC}         린트"
    echo -e "  ${GREEN}make tool-install${NC} 도구 설치"
    echo -e "  ${GREEN}make tool-upload${NC}  도구 업로드"
    echo -e "  ${GREEN}make edit-env${NC}     .env 편집"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  문서${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BLUE}https://github.com/lee-lou2/sidekick${NC}"
    echo ""
}

# =============================================================================
# 메인 실행
# =============================================================================
main() {
    print_banner
    check_requirements
    clone_repository
    install_uv
    install_dependencies
    setup_env
    print_success
}

main "$@"
