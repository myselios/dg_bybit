# Phase 11a RED→GREEN Proof

**Phase 재정의**: Phase 11 → 11a (Signal+Exit, 100% 완료) + 11b (Full Integration+Testnet, TODO)

## Phase 11a: Signal Generation + Exit Manager + Orchestrator Integration (최소)

**Goal**: Grid 신호 생성, Exit logic 구현, Orchestrator 최소 통합 (Exit Manager만)

---

## Part 1: Signal Generator (RED→GREEN)

### RED 단계 (구현 전)

#### 실행 명령
```bash
pytest tests/unit/test_signal_generator.py -v
```

#### 결과
```
FAILED tests/unit/test_signal_generator.py::test_grid_up_generates_sell_signal
FAILED tests/unit/test_signal_generator.py::test_grid_down_generates_buy_signal
FAILED tests/unit/test_signal_generator.py::test_no_signal_within_grid_range
FAILED tests/unit/test_signal_generator.py::test_calculate_grid_spacing_from_atr
FAILED tests/unit/test_signal_generator.py::test_calculate_grid_spacing_with_custom_multiplier
FAILED tests/unit/test_signal_generator.py::test_grid_boundary_exact_buy
FAILED tests/unit/test_signal_generator.py::test_grid_boundary_exact_sell
FAILED tests/unit/test_signal_generator.py::test_signal_contains_qty
FAILED tests/unit/test_signal_generator.py::test_initial_entry_signal_when_no_last_fill
FAILED tests/unit/test_signal_generator.py::test_multiple_grid_levels_away

============================== 10 failed in 0.05s ==============================
```

#### 실패 이유
```
ModuleNotFoundError: No module named 'src.application.signal_generator'
```

**확인**: 구현 파일이 존재하지 않음 (TDD RED 단계 정상)

---

### GREEN 단계 (구현 후)

#### 구현 파일
1. `src/application/signal_generator.py` (88 LOC)
   - Signal dataclass (side, price, qty)
   - calculate_grid_spacing(atr, multiplier)
   - generate_signal(current_price, last_fill_price, grid_spacing, qty)

#### 실행 명령
```bash
pytest tests/unit/test_signal_generator.py -v
```

#### 결과
```
tests/unit/test_signal_generator.py::test_grid_up_generates_sell_signal PASSED [ 10%]
tests/unit/test_signal_generator.py::test_grid_down_generates_buy_signal PASSED [ 20%]
tests/unit/test_signal_generator.py::test_no_signal_within_grid_range PASSED [ 30%]
tests/unit/test_signal_generator.py::test_calculate_grid_spacing_from_atr PASSED [ 40%]
tests/unit/test_signal_generator.py::test_calculate_grid_spacing_with_custom_multiplier PASSED [ 50%]
tests/unit/test_signal_generator.py::test_grid_boundary_exact_buy PASSED [ 60%]
tests/unit/test_signal_generator.py::test_grid_boundary_exact_sell PASSED [ 70%]
tests/unit/test_signal_generator.py::test_signal_contains_qty PASSED [ 80%]
tests/unit/test_signal_generator.py::test_initial_entry_signal_when_no_last_fill PASSED [ 90%]
tests/unit/test_signal_generator.py::test_multiple_grid_levels_away PASSED [100%]

============================== 10 passed in 0.01s ==============================
```

**확인**: Signal Generator 10 tests PASSED

---

## Part 2: Exit Manager (RED→GREEN)

### RED 단계 (구현 전)

#### 실행 명령
```bash
pytest tests/unit/test_exit_manager.py -v
```

#### 결과
```
ERROR collecting tests/unit/test_exit_manager.py
ModuleNotFoundError: No module named 'application.exit_manager'
```

**확인**: 구현 파일이 존재하지 않음 (TDD RED 단계 정상)

---

### GREEN 단계 (구현 후)

#### 구현 파일
1. `src/domain/intent.py` 수정
   - ExitIntent dataclass 추가 (qty, reason, order_type, stop_price)
   - TransitionIntents.exit_intent 필드 추가

2. `src/application/exit_manager.py` (78 LOC)
   - check_stop_hit(current_price, position) → bool
   - create_exit_intent(position, reason) → TransitionIntents

#### 실행 명령
```bash
pytest tests/unit/test_exit_manager.py -v
```

#### 결과
```
tests/unit/test_exit_manager.py::test_stop_hit_long PASSED               [ 12%]
tests/unit/test_exit_manager.py::test_stop_hit_short PASSED              [ 25%]
tests/unit/test_exit_manager.py::test_stop_not_hit_long PASSED           [ 37%]
tests/unit/test_exit_manager.py::test_stop_not_hit_short PASSED          [ 50%]
tests/unit/test_exit_manager.py::test_create_exit_intent PASSED          [ 62%]
tests/unit/test_exit_manager.py::test_stop_hit_long_boundary PASSED      [ 75%]
tests/unit/test_exit_manager.py::test_stop_hit_short_boundary PASSED     [ 87%]
tests/unit/test_exit_manager.py::test_stop_hit_no_stop_price PASSED      [100%]

============================== 8 passed in 0.01s ==============================
```

**확인**: Exit Manager 8 tests PASSED

---

## Part 3: Orchestrator Integration

### 구현 내용
1. `src/application/orchestrator.py` 수정
   - Exit Manager import 추가
   - TickResult.exit_intent 필드 추가
   - _manage_position() → check_stop_hit() 통합
   - run_tick() → exit_intent를 TickResult에 포함

### 전체 테스트 스위트
```bash
pytest -q
```

### 결과
```
245 passed, 15 deselected in 0.32s
```

**확인**: Phase 11 완료 후 총 245 tests (+18 from Phase 10: 227)
- Signal Generator: +10 tests
- Exit Manager: +8 tests
- 회귀 없음 (기존 227 tests 유지)

---

## 결론

✅ **RED→GREEN 완료**
- Part 1 (Signal Generator): 10 failed → 10 passed
- Part 2 (Exit Manager): ModuleNotFoundError → 8 passed
- Part 3 (Orchestrator Integration): 245 passed (회귀 없음)

✅ **TDD 절차 준수**
- 테스트 먼저 작성 (RED 확인)
- 최소 구현 (GREEN)
- 통합 (Orchestrator에 Exit Manager 연동)
- 전체 테스트 재실행 (회귀 방지)

✅ **Phase 11 DoD 달성**
- Signal Generator 구현 (Grid-based, ATR spacing)
- Exit Manager 구현 (Stop hit check, Exit intent)
- Orchestrator Integration (최소 통합)
