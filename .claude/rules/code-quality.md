---
description: 코드 품질 게이트. src/와 tests/ 파일 수정 시 적용.
globs:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Code Quality Gates

## 테스트 규칙
- `assert True`, `pass # TODO`, `raise NotImplementedError` 금지
- tests/에서 domain 타입(Position, State, ExecutionEvent) 재정의 금지
- `sys.path.insert` 금지
- 각 test_ 함수에 최소 1개 도메인 값 비교 assert 필수

## 아키텍처 규칙
- transition()은 pure 함수 (I/O 금지)
- 상태 전이 로직은 transition()에만 존재
- I/O는 executor/adapter에서만 수행

## FLOW.md 수정 시
- ADR 필수 (예외 없음)
- ADR 없이 FLOW.md 수정 감지 시 즉시 작업 중단
- 사용자에게 "A안(ADR 추가) / B안(Rollback)" 선택지 제시

## 완료 기준
- `pytest -q` 통과
- `TASKS.md` 업데이트
- 작업일지 작성
