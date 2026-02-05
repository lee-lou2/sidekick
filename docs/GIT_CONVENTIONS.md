# Git & Release Conventions

## Commit Messages

[Conventional Commits](https://www.conventionalcommits.org/) 스타일 사용.

### 형식

```
<type>: <description>
```

### Type

| Type | 설명 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 변경 |
| `refactor` | 리팩토링 (기능 변경 없음) |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드, 설정 등 기타 |

### 예시

```
feat: add webhook_headers support for API callbacks
fix: resolve mermaid parse error in README
docs: add REST API usage examples
refactor: extract image processing to middleware
test: add scheduler time parser tests
chore: update ruff configuration
```

### 규칙

- 영어 소문자로 시작
- 마침표 없음
- 명령형 ("add" not "added")
- 50자 이내

---

## Release Notes

GitHub Releases에 작성. [Keep a Changelog](https://keepachangelog.com/) 기반.

### 형식

```markdown
## What's Changed

### Added
- 새로 추가된 기능

### Changed
- 변경된 기능

### Fixed
- 버그 수정

### Removed
- 제거된 기능
```

### 예시

```markdown
## What's Changed

### Added
- Webhook 요청 시 커스텀 헤더 지원 (`webhook_headers`)
- REST API 사용 예시 문서 추가

### Fixed
- README Mermaid 다이어그램 파싱 오류 수정

### Changed
- API 응답에 `execution_time` 필드 추가
```

### 규칙

- 사용자 관점에서 작성 (코드 변경이 아닌 기능 변경)
- 불필요한 섹션은 생략
- PR/이슈 링크는 자동 생성되므로 생략 가능
