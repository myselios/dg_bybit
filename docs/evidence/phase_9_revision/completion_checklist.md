# Phase 9 Revision — Completion Checklist

**Date**: 2026-01-24
**Task**: Phase 9 Session Risk Policy 수정 (UTC boundary 버그 수정)

---

## 1. 작업 범위

### 1.1 발견된 문제 (3개)

- [x] **Issue 1**: FLOW.md SSOT 누락 (Session Risk Policy 미문서화)
- [x] **Issue 2**: UTC boundary 계산 오류 (`math.ceil()` 버그)
- [x] **Issue 3**: hasattr() 타입 불안정 (Protocol 미확장)

### 1.2 수정 내용

- [x] FLOW.md에 Session Risk Policy 섹션 추가
- [x] session_risk.py UTC boundary 계산 수정 (`int() + 1` 패턴)
- [x] Edge case 테스트 2개 추가 (23:59:59, 00:00:01)
- [x] MarketDataInterface Protocol 확장
- [x] orchestrator.py hasattr() 제거
- [x] FakeMarketData Session Risk 메서드 추가
- [x] mypy 타입 체크 통과

---

## 2. DoD (Definition of Done)

### 2.1 SSOT 업데이트

- [x] FLOW.md에 Session Risk Policy 섹션 추가 (Section after COOLDOWN)
- [x] 4개 Kill Switch 문서화 (Daily/Weekly Loss Cap, Loss Streak, Anomaly)
- [x] 3-tier 보호 구조 명시 (Per-Trade Cap → Session Risk → Emergency)

### 2.2 구현 수정

- [x] session_risk.py `check_daily_loss_cap()` 수정
- [x] session_risk.py `check_loss_streak_kill()` 수정
- [x] 기존 테스트 기대값 수정 (2개)
- [x] Edge case 테스트 추가 (2개)

### 2.3 타입 안정화

- [x] MarketDataInterface Protocol 확장 (8개 메서드 추가)
- [x] orchestrator.py hasattr() 제거
- [x] Protocol 메서드 Optional 타입 체크
- [x] mypy 검증 통과

### 2.4 테스트 통과

- [x] Unit 테스트 통과 (test_session_risk.py: 17 passed)
- [x] Integration 테스트 통과 (test_orchestrator*.py: 8개 수정)
- [x] 전체 테스트 통과 (237 passed, 15 deselected)

### 2.5 Evidence Artifacts

- [x] `utc_boundary_proof.md` 작성
- [x] `gate7_verification.txt` 생성
- [x] `pytest_output.txt` 생성
- [x] `completion_checklist.md` 작성 (이 파일)

---

## 3. Section 5.7 Self-Verification 결과

### 3.1 Gate 1: Placeholder 테스트 0개

- [x] (1a) Placeholder 표현 감지: ✅ 1개 (conftest.py pytest.skip, 허용)
- [x] (1b) Skip/Xfail decorator: ✅ 0개
- [x] (1c) 의미있는 assert: ✅ 375개

### 3.2 Gate 2: 도메인 타입 재정의 금지

- [x] (2a) 도메인 타입 이름 재정의: ✅ 0개
- [x] (2b) tests/ 내 domain 파일: ✅ 0개

### 3.3 Gate 3: transition SSOT 존재

- [x] (3) transition.py 파일 존재: ✅ OK

### 3.4 Gate 4: EventRouter 상태 분기 금지

- [x] (4a) if/elif state == 금지: ✅ 0개
- [x] (4b) State. 참조 금지: ✅ 0개 (docstring만 존재)

### 3.5 Gate 5: 구조 위반 금지

- [x] (5) sys.path hack: ✅ 0개

### 3.6 Gate 6: Migration 완료

- [x] (6a) Deprecated import 추적: ✅ 0개
- [x] (6b) 구 경로 import: ✅ 0개

### 3.7 Gate 7: pytest 증거

- [x] (7) pytest 실행 결과: ✅ 237 passed, 15 deselected

---

## 4. 수정된 파일 목록

### 4.1 문서

1. `docs/constitution/FLOW.md` (Session Risk Policy 섹션 추가)

### 4.2 구현

2. `src/application/session_risk.py` (UTC boundary 계산 수정)
3. `src/application/orchestrator.py` (hasattr() 제거)
4. `src/infrastructure/exchange/market_data_interface.py` (Protocol 확장)
5. `src/infrastructure/exchange/fake_market_data.py` (Session Risk 메서드 추가)

### 4.3 테스트

6. `tests/unit/test_session_risk.py` (기대값 수정 + Edge case 추가)
7. `tests/integration/test_orchestrator_session_risk.py` (Protocol 메서드 추가)

### 4.4 Evidence

8. `docs/evidence/phase_9_revision/utc_boundary_proof.md`
9. `docs/evidence/phase_9_revision/gate7_verification.txt`
10. `docs/evidence/phase_9_revision/pytest_output.txt`
11. `docs/evidence/phase_9_revision/completion_checklist.md` (이 파일)

---

## 5. 실거래 생존성 검증

### 5.1 Critical Path 검증

- [x] **00:00:00 경계 케이스**: HALT 보호 장치 정상 작동 (24시간 차단)
- [x] **23:59:59 경계 케이스**: 1초 후 해제 (다음날 UTC 0:00)
- [x] **00:00:01 경계 케이스**: 거의 24시간 후 해제

### 5.2 타입 안정성

- [x] Protocol 메서드 사용 → 런타임 AttributeError 방지
- [x] Optional 타입 체크 → None 안전 처리
- [x] mypy 검증 통과 → 타입 불일치 0개

### 5.3 회귀 테스트

- [x] 기존 테스트 237개 통과 → 기존 기능 영향 없음
- [x] Session Risk 통합 테스트 5개 통과 → Orchestrator 정상 작동

---

## 6. 최종 판정

**Status**: ✅ **DONE**

**요약**:
- UTC boundary 버그 수정 완료
- SSOT 문서화 완료
- 타입 안정화 완료
- 전체 테스트 통과 (237 passed)
- Evidence Artifacts 생성 완료

**실거래 준비 상태**: ✅ **READY**
- 경계 케이스 버그 수정 → 보호 장치 정상 작동
- 타입 안정성 확보 → 런타임 오류 방지
- 문서-코드 일치 → 유지보수성 확보

**Next Steps**:
- task_plan.md Progress Table 업데이트
- Phase 9 Revision Evidence 링크 추가
- Commit 및 Push
