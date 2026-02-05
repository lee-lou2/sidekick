#!/usr/bin/env bash
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

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}    Tool Uploader${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [[ -n "$1" ]]; then
    FILE_PATH="$1"
else
    echo "사용 가능한 도구 파일:"
    echo ""
    
    FILES=()
    while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        if [[ "$filename" != "__init__.py" ]]; then
            FILES+=("$file")
            echo "  $((${#FILES[@]}))) $filename"
        fi
    done < <(find "$TOOLS_DIR" -maxdepth 1 -name "*.py" -print0 2>/dev/null | sort -z)
    
    if [[ ${#FILES[@]} -eq 0 ]]; then
        error "src/tools/custom/에 업로드할 도구가 없습니다."
    fi
    
    echo ""
    read -p "업로드할 파일 번호를 선택하세요 (1-${#FILES[@]}): " CHOICE
    
    if [[ ! "$CHOICE" =~ ^[0-9]+$ ]] || [[ "$CHOICE" -lt 1 ]] || [[ "$CHOICE" -gt ${#FILES[@]} ]]; then
        error "잘못된 선택입니다."
    fi
    
    FILE_PATH="${FILES[$((CHOICE-1))]}"
fi

if [[ ! -f "$FILE_PATH" ]]; then
    error "파일을 찾을 수 없습니다: $FILE_PATH"
fi

FILENAME=$(basename "$FILE_PATH")

if [[ ! "$FILENAME" =~ \.py$ ]]; then
    error "Python 파일(.py)만 업로드할 수 있습니다."
fi

info "문법 검사 중: $FILENAME"
if ! python3 -m py_compile "$FILE_PATH" 2>/dev/null; then
    error "Python 문법 오류가 있습니다. 업로드를 중단합니다."
fi
success "문법 검사 통과"

echo ""
info "업로드 중: $FILENAME (1시간 후 자동 만료)"

LINK=$(curl -s -F "reqtype=fileupload" \
     -F "time=1h" \
     -F "fileToUpload=@$FILE_PATH" \
     "https://litterbox.catbox.moe/resources/internals/api.php")

if [[ -z "$LINK" ]] || [[ ! "$LINK" =~ ^https:// ]]; then
    echo ""
    echo -e "${RED}업로드 실패:${NC}"
    echo "$LINK"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  업로드 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "파일: ${BLUE}$FILENAME${NC}"
echo -e "다운로드 URL: ${GREEN}$LINK${NC}"
echo -e "만료: ${YELLOW}1시간 후 자동 삭제${NC}"
echo ""
echo -e "${YELLOW}이 URL을 공유하면 상대방이 tool-installer.sh로 설치할 수 있습니다:${NC}"
echo ""
echo -e "  ${GREEN}./tool-installer.sh${NC}"
echo -e "  도구 URL을 입력하세요: ${BLUE}$LINK${NC}"
echo ""
