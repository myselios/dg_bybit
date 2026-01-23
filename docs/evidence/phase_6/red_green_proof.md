# Phase 6: RED→GREEN Proof (Orchestrator Integration)

## 목적
Phase 6 (Orchestrator Integration) 구현의 TDD 증거를 기록한다.

## SSOT
- task_plan.md Phase 6: Orchestrator Integration
- FLOW.md Section 2: Tick Ordering (Emergency-first)
- FLOW.md Section 4.2: God Object 금지

## 구현 순서

### Step 1: RED (테스트 먼저 작성)
```bash
# tests/integration/test_orchestrator.py 작성 (5 cases)
# 1. test_orchestrator_tick_order_emergency_first
# 2. test_orchestrator_full_cycle_flat_to_in_position_to_flat
# 3. test_orchestrator_halt_on_emergency
# 4. test_orchestrator_degraded_mode_blocks_entry
# 5. test_orchestrator_degraded_timeout_triggers_halt

# 실행 결과: FAILED (orchestrator.py 미구현)
$ pytest tests/integration/test_orchestrator.py -q
FAILED (ModuleNotFoundError: No module named 'application.orchestrator')
```

### Step 2: GREEN (최소 구현)
```bash
# src/application/orchestrator.py 구현
# - Orchestrator 클래스
# - TickResult dataclass
# - run_tick() 메서드 (Emergency → Events → Position → Entry)

# src/infrastructure/exchange/fake_market_data.py 확장
# - is_ws_degraded() 메서드 추가
# - is_degraded_timeout() 메서드 추가
# - set_ws_degraded() 메서드 추가

# 실행 결과: PASSED
$ pytest tests/integration/test_orchestrator.py -q
5 passed in 0.02s

# 전체 테스트: PASSED
$ pytest -q
171 passed in 0.12s
```

### Step 3: Refactor (불필요)
- God Object 금지 원칙 준수 (thin wrapper로 구현)
- 리팩토링 필요 없음 (최소 구현이 이미 클린)

## 최종 검증
```bash
$ pytest -q
171 passed in 0.12s
```

## 구현 파일
- src/application/orchestrator.py (186 lines)
- tests/integration/test_orchestrator.py (5 cases)
- src/infrastructure/exchange/fake_market_data.py (확장)

## DoD 충족 확인
- [x] orchestrator + integration tests (5케이스)
- [x] Tick 순서 고정: Emergency → Events → Position → Entry
- [x] pytest 통과 (171 passed)
- [x] Progress Table 업데이트
- [x] Evidence 생성
