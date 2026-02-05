#!/usr/bin/env bash
# =============================================================================
# Tool Installer - 외부 도구 다운로드 스크립트
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/src/tools/custom"
TEMP_FILE=$(mktemp)

cleanup() {
    rm -f "$TEMP_FILE"
}
trap cleanup EXIT

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}    Tool Installer${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

read -p "도구 URL을 입력하세요: " URL

if [[ -z "$URL" ]]; then
    error "URL이 입력되지 않았습니다."
fi

read -p "저장할 파일명을 입력하세요 (예: my_tool.py): " FILENAME

if [[ -z "$FILENAME" ]]; then
    error "파일명이 입력되지 않았습니다."
fi

while [[ ! "$FILENAME" =~ \.py$ ]]; do
    warn "Python 파일(.py)만 설치할 수 있습니다: $FILENAME"
    read -p "저장할 파일명을 다시 입력하세요 (예: my_tool.py): " FILENAME
    if [[ -z "$FILENAME" ]]; then
        error "파일명이 입력되지 않았습니다."
    fi
done

info "다운로드 중: $URL"

if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -sL -w "%{http_code}" -o "$TEMP_FILE" "$URL")
    if [[ "$HTTP_CODE" != "200" ]]; then
        error "다운로드 실패 (HTTP $HTTP_CODE): $URL"
    fi
elif command -v wget &> /dev/null; then
    if ! wget -q -O "$TEMP_FILE" "$URL"; then
        error "다운로드 실패: $URL"
    fi
else
    error "curl 또는 wget이 필요합니다."
fi

success "다운로드 완료"

info "Python 문법 검사 중..."

if ! python3 -m py_compile "$TEMP_FILE" 2>/dev/null; then
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  문법 오류 발견!${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    python3 -m py_compile "$TEMP_FILE" 2>&1 || true
    echo ""
    error "Python 문법 오류가 있습니다. 설치를 중단합니다."
fi

success "문법 검사 통과"

DEST_FILE="$TOOLS_DIR/$FILENAME"

if [[ -f "$DEST_FILE" ]]; then
    echo ""
    warn "이미 존재하는 파일입니다: $FILENAME"
    read -p "덮어쓰시겠습니까? (y/N): " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[Yy]$ ]]; then
        info "설치를 취소합니다."
        exit 0
    fi
fi

mkdir -p "$TOOLS_DIR"
mv "$TEMP_FILE" "$DEST_FILE"
chmod 644 "$DEST_FILE"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  설치 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "파일: ${BLUE}$DEST_FILE${NC}"
echo ""
warn "도구를 사용하려면 서버를 재시작하세요:"
echo ""
echo -e "  ${GREEN}make run${NC}"
echo ""
