.PHONY: help run test lint format tool-install tool-upload edit-env

.DEFAULT_GOAL := help

BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m

help:
	@echo ""
	@echo "$(GREEN)Sidekick$(NC) - 개인용 AI 에이전트"
	@echo ""
	@echo "$(YELLOW)사용법:$(NC) make [command]"
	@echo ""
	@echo "  run            실행 (설정 + 모드 선택)"
	@echo "  test           코어 테스트"
	@echo "  test-all       전체 테스트 (커스텀 도구 포함)"
	@echo "  lint           린트 + 자동 수정"
	@echo "  format         코드 포맷팅"
	@echo "  tool-install   도구 설치"
	@echo "  tool-upload    도구 업로드"
	@echo "  edit-env       .env 편집"
	@echo ""

run:
	@./scripts/start.sh

test:
	@uv run pytest tests/ --ignore=tests/tools -v

test-all:
	@uv run pytest tests/ -v

lint:
	@uv run ruff check src/ tests/ --fix

format:
	@uv run ruff format src/ tests/

tool-install:
	@./scripts/tool-installer.sh

tool-upload:
	@./scripts/tool-uploader.sh

edit-env:
	@$${EDITOR:-nano} .env
