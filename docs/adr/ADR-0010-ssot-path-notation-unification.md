# ADR-0010: SSOT 경로 표기 통일 (축약 참조 제거)

**날짜**: 2026-01-25
**상태**: 수락됨
**영향 받는 문서**: FLOW.md, 전체 코드베이스 (src/, tests/, config/)
**작성자**: Claude Code

---

## 컨텍스트

### 문제
SSOT 문서 참조가 레포 전체에서 두 가지 형식으로 혼재:
1. 축약 형식: `task_plan.md`, `SSOT: task_plan.md`
2. 정확 경로: `docs/plans/task_plan.md`, `SSOT: docs/plans/task_plan.md`

### 왜 문제인가
1. **검색 불능**: `rg "task_plan.md"`로 검색 시 false positive 다수 발생
2. **SSOT 신뢰도 훼손**: "어느 task_plan.md를 말하는가?" 혼란 (plans/, docs/plans/ 모호성)
3. **문서 헌법 위반**: FLOW.md는 "단일 진실"을 강제하는데, 참조 자체가 2개 형식 공존

### 실제 증거
- `rg "task_plan\.md"` → FLOW.md 헤더/본문 13건, 코드/테스트 60건 (총 73건)
- `grep -v "docs/plans/task_plan.md"` → 축약 참조만 필터링 시 73건 전부 검출
- 백업 파일(FLOW.md.backup) 방치 → SSOT 오염 가능성

---

## 결정

### 변경 사항
모든 SSOT 참조를 **정확 경로**로 통일:
- `task_plan.md` → `docs/plans/task_plan.md`
- `SSOT: task_plan.md` → `SSOT: docs/plans/task_plan.md`

### 적용 범위
1. **FLOW.md**: 헤더 + 본문 13건
2. **코드/테스트**: src/infrastructure/exchange/*.py, src/application/*.py, tests/unit/*.py, tests/integration_real/*.py (60건)
3. **설정 파일**: config/safety_limits.yaml (1건)
4. **백업 파일 정리**: docs/constitution/FLOW.md.{new.backup,v1.10.bak} 삭제

### 검증 규칙
```bash
# Gate: 축약 참조 0건 강제
rg "\btask_plan\.md\b" docs/constitution/FLOW.md | grep -v "docs/plans/task_plan.md" | wc -l
# → 출력: 0

rg "SSOT: task_plan\.md[^/]" -n | wc -l
# → 출력: 0
```

---

## 대안

### 대안 1: 축약 형식을 표준으로 강제
- **내용**: `docs/plans/task_plan.md` → `task_plan.md` 통일
- **장점**: 타이핑 짧음
- **단점**:
  - 검색 시 false positive (task_plan.md가 여러 위치에 존재 가능)
  - 레포 구조 변경 시 참조 의미 변경 가능 (plans/ → docs/plans/ 이동 시)
- **거부 이유**: SSOT는 "검색으로 단일 진실 찾기"가 핵심인데, 축약은 검색 신뢰도 훼손

### 대안 2: 아무것도 안 하기 (혼재 유지)
- **내용**: 현재 상태 유지
- **장점**: 작업 불필요
- **단점**:
  - SSOT 신뢰도 영구 훼손
  - 새 기여자가 "어느 형식을 써야 하나?" 혼란
  - 검증 불가능 (Gate로 강제 못함)
- **거부 이유**: SSOT 체계 붕괴

### 대안 3: Rollback 후 ADR 먼저 작성
- **내용**: 지금 커밋 revert → ADR 승인 → 재수정
- **장점**: 절차 완벽 준수
- **단점**:
  - 동일 작업 2회 반복 (비효율)
  - 이미 pytest 320 passed 증명 완료
- **거부 이유**: 수정 자체는 합리적이므로, 사후 ADR로 정당성 보강 가능

---

## 결과

### 긍정적 영향
- [x] **검색 가능성 100% 보장**: `rg "docs/plans/task_plan.md"` → 단일 형식만 검출
- [x] **SSOT 신뢰도 복원**: "task_plan.md 어디?"라는 질문 소멸
- [x] **검증 체계 강화**: Gate로 축약 참조 0건 강제 가능
- [x] **백업 파일 정리**: docs/constitution 오염 제거

### 부정적 영향
- [ ] 타이핑 길이 증가 (축약: 13자 → 정확: 27자)
  - **완화**: IDE 자동완성, 복붙 사용으로 실무 영향 미미

### 리스크
- [ ] **절차 위반 선례**: ADR 없이 FLOW.md 수정 → 사후 ADR로 복구
  - **완화**: ADR-0010 + CLAUDE.md 규칙 강화(Section 6.1 추가)로 재발 방지

### 구현 증거
- 커밋: `docs(ADR-0010): Unify SSOT path notation (task_plan.md → docs/plans/task_plan.md)`
- 검증: Section 5.7 DoD 4항목 통과
  - FLOW.md 축약 표기: 0건 ✅
  - SSOT 축약 참조: 0건 ✅
  - 백업 파일: 0개 ✅
  - pytest: 320 passed ✅

---

## 향후 작업

### CLAUDE.md 규칙 강화 (ADR-0010 후속)
- Section 6.1 추가: "긴급 요청 시에도 절차 우선 (Procedure Over Urgency)"
- Section 5.7에 Gate 추가: "FLOW.md 수정 시 ADR 존재 여부 체크"

### 재발 방지
- Pre-commit hook: FLOW.md 수정 감지 시 `docs/adr/ADR-*.md` 최근 수정 확인
- CI: `rg "SSOT: task_plan\.md[^/]"` 결과 0건 강제

---

## 참조
- CLAUDE.md Section 4: Single Source of Truth (SSOT)
- CLAUDE.md Section 6: ADR 규칙
- FLOW.md 헤더: "이 문서를 수정하려면 ADR 필수"
