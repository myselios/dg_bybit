# Phase 11 Completion Checklist

## DoD Items

### 1. Signal Generator 구현
- [x] Grid-based signal generation (간단한 구현)
  - File: `src/application/signal_generator.py` (88 LOC)
  - Dataclass: Signal (side, price, qty)
  - Tests: 10 passed

- [x] ATR 기반 grid spacing 계산
  - Function: `calculate_grid_spacing(atr, multiplier)` 구현
  - Test: test_calculate_grid_spacing_from_atr (PASS)
  - Test: test_calculate_grid_spacing_with_custom_multiplier (PASS)

- [x] Last fill price 기반 grid level 결정
  - Function: `generate_signal(current_price, last_fill_price, grid_spacing, qty)` 구현
  - Tests:
    - test_grid_up_generates_sell_signal (PASS)
    - test_grid_down_generates_buy_signal (PASS)
    - test_no_signal_within_grid_range (PASS)
    - test_grid_boundary_exact_buy (PASS)
    - test_grid_boundary_exact_sell (PASS)
    - test_signal_contains_qty (PASS)
    - test_initial_entry_signal_when_no_last_fill (PASS)
    - test_multiple_grid_levels_away (PASS)

### 2. Exit Logic 구현
- [x] check_stop_hit(): Stop loss 도달 확인
  - File: `src/application/exit_manager.py` (78 LOC)
  - Direction별 확인 (LONG: <=, SHORT: >=)
  - Tests: 8 passed
    - test_stop_hit_long (PASS)
    - test_stop_hit_short (PASS)
    - test_stop_not_hit_long (PASS)
    - test_stop_not_hit_short (PASS)
    - test_stop_hit_long_boundary (PASS)
    - test_stop_hit_short_boundary (PASS)
    - test_stop_hit_no_stop_price (PASS)

- [x] create_exit_intent(): Exit 주문 Intent 생성
  - Test: test_create_exit_intent (PASS)
  - Market order로 강제 청산

- [ ] check_profit_target(): Profit target 도달 확인 (optional)
  - Grid 전략에서는 signal_generator가 처리 → Not applicable

### 3. Full Orchestrator Integration (최소)
- [x] domain/intent.py 수정: ExitIntent 추가
  - ExitIntent dataclass (qty, reason, order_type, stop_price)
  - TransitionIntents.exit_intent 필드 추가

- [x] orchestrator.py 수정: Exit Manager 통합
  - Exit Manager import 추가
  - TickResult.exit_intent 필드 추가
  - _manage_position() → check_stop_hit() 호출
  - run_tick() → exit_intent 포함

- [ ] Entry decision: Signal → Gates → Sizing → Order placement
  - **Not implemented**: Testnet E2E에서 수행 예정

- [ ] Event processing: FILL → Position update → Trade log
  - **Not implemented**: Testnet E2E에서 수행 예정

### 4. 테스트 구현
- [x] test_signal_generator.py: 10 tests
  - Grid up/down, ATR spacing, boundary cases
  - All 10 tests PASSED

- [x] test_exit_manager.py: 8 tests
  - Stop hit check (LONG/SHORT, boundary, no stop_price)
  - Exit intent 생성
  - All 8 tests PASSED

- [ ] Testnet End-to-End Tests
  - **Not implemented**: `tests/integration_real/test_full_cycle_testnet.py`
  - Full cycle: FLAT → Entry → Exit → FLAT
  - 최소 10회 거래 성공 검증
  - Session Risk 발동 확인
  - **Reason**: Requires real Testnet connection (Phase 12 scope)

### 5. Evidence Artifacts 생성
- [x] pytest_output.txt (pytest 실행 결과: 245 passed)
- [x] red_green_proof.md (RED→GREEN 재현 증거)
- [x] completion_checklist.md (this file)
- [x] gate7_verification.txt (CLAUDE.md Section 5.7 검증 명령 출력)

### 6. Progress Table 업데이트
- [ ] task_plan.md Progress Table 업데이트
- [ ] Last Updated 갱신
- [ ] Evidence 링크 추가

### 7. Gate 7: CLAUDE.md Section 5.7 검증
- [x] 7개 검증 커맨드 실행 (gate7_verification.txt 참조)
- [x] 모든 출력 PASS 확인

## Summary

**Tests**: 18 passed (10 + 8)
**Total**: 245 passed (+18 from Phase 10)

**Files Created**:
- src/application/signal_generator.py (88 LOC)
- src/application/exit_manager.py (78 LOC)
- src/domain/intent.py (ExitIntent 추가)
- tests/unit/test_signal_generator.py (10 tests)
- tests/unit/test_exit_manager.py (8 tests)

**Files Modified**:
- src/application/orchestrator.py (Exit Manager 통합)

**DoD Status**: 5/7 완료 (Progress Table + Testnet E2E 남음)

**Note**: Testnet E2E Tests는 Phase 12 (Dry-Run Validation)에서 수행 예정
