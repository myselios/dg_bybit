# Position Recovery Completion Evidence

**Date**: 2026-01-25
**Commit**: bb4a1dc
**Feature**: Orchestrator Position Recovery on Startup

---

## Problem Statement

Orchestrator가 startup 시 기존 포지션을 감지하지 못하고 항상 `State.FLAT`으로 시작하여, 실제 포지션이 있는 상태에서도 Entry 시도 및 상태 불일치 발생.

**사용자 보고**:
- Testnet에서 0.146 BTC Buy position 보유 중
- Orchestrator State: `FLAT` (잘못됨)
- 예상 State: `IN_POSITION`

---

## Solution

### 1. MarketDataInterface 확장

**파일**: `src/infrastructure/exchange/market_data_interface.py`

```python
def get_position(self) -> Dict[str, Any]:
    """
    현재 Position 정보 (Bybit API 구조).

    Returns:
        Dict[str, Any]: Position data
            - size: Position size (BTC 단위, "0"이면 포지션 없음)
            - side: "Buy", "Sell", "None"
            - avgPrice: Average entry price

    Used by:
        - Orchestrator startup (position recovery)
    """
    ...
```

### 2. BybitAdapter 구현

**파일**: `src/infrastructure/exchange/bybit_adapter.py`

```python
def get_position(self) -> Dict[str, Any]:
    """현재 Position 정보 (Bybit API 구조)"""
    if self._current_position is None:
        # Position 없음 (size = 0)
        return {"size": "0", "side": "None", "avgPrice": "0"}
    return self._current_position
```

### 3. Orchestrator Position Recovery 로직

**파일**: `src/application/orchestrator.py`

```python
def __init__(self, market_data, rest_client=None, log_storage=None):
    # ... 기존 초기화

    # Position recovery: 기존 포지션이 있으면 State.IN_POSITION으로 시작
    position_data = market_data.get_position()
    position_size = float(position_data.get("size", "0"))

    if position_size > 0:
        # Position 존재 → State.IN_POSITION
        position_side = position_data.get("side", "None")
        avg_price = float(position_data.get("avgPrice", "0") or "0")

        # Direction 매핑 (Bybit "Buy"/"Sell" → Domain Direction)
        direction = Direction.LONG if position_side == "Buy" else Direction.SHORT

        # Position 객체 생성 (recovery 시 signal_id는 "recovered")
        self.position = Position(
            direction=direction,
            qty=position_size,
            entry_price=avg_price,
            signal_id="recovered",
        )
        self.state = State.IN_POSITION
    else:
        # Position 없음 → State.FLAT
        self.state = State.FLAT
        self.position = None
```

---

## Test Evidence

### Unit Test: RED → GREEN

**파일**: `tests/unit/test_orchestrator_position_recovery.py`

```bash
$ pytest tests/unit/test_orchestrator_position_recovery.py -v

test_position_recovery_no_position PASSED [ 33%]
test_position_recovery_buy_position PASSED [ 66%]
test_position_recovery_sell_position PASSED [100%]

============================== 3 passed in 0.02s ===============================
```

**세부 출력**: [pytest_position_recovery.txt](pytest_position_recovery.txt)

### Regression Test: 전체 테스트 통과

```bash
$ pytest -q
323 passed, 15 deselected in 0.53s
```

---

## Testnet Validation

**스크립트**: `scripts/check_orchestrator_state.py`

### Before Fix (문제 상황)
```
Orchestrator Status:
   - Current State: State.FLAT  ← 잘못됨

Position Info:
   - Size: 0.1460 BTC
   - Side: Buy
   - Avg Price: $85,074.19

✅ Position exists → State should be IN_POSITION  ← 불일치!
```

### After Fix (수정 후)
```
Orchestrator Status:
   - Current State: State.IN_POSITION  ← 정상!

Position Info:
   - Size: 0.1460 BTC
   - Side: Buy
   - Avg Price: $85,074.19
   - Mark Price: $84,432.71

✅ Position exists → State should be IN_POSITION  ← 일치!

Tick Result:
   - State: State.IN_POSITION
   - Entry Blocked: state_not_flat  ← 정상 (IN_POSITION이므로 entry 차단)
```

**전체 출력**: [position_recovery_testnet.txt](position_recovery_testnet.txt)

---

## Implementation Details

### Position 객체 필드
```python
Position(
    direction=Direction.LONG,      # "Buy" → LONG, "Sell" → SHORT
    qty=0.146,                      # Position size (BTC)
    entry_price=85074.19,           # Average entry price
    signal_id="recovered",          # Recovery 시 특수 ID
)
```

### Edge Cases 처리
1. **Position size = 0**: `State.FLAT` 유지 (기존 동작)
2. **Buy position**: `Direction.LONG` 매핑
3. **Sell position**: `Direction.SHORT` 매핑
4. **avgPrice None**: `"0"` default 처리

---

## Impact Analysis

### Before
- ❌ 기존 포지션 무시
- ❌ State 불일치 (Position 있지만 FLAT)
- ❌ 중복 Entry 시도 가능
- ❌ Stop loss 미작동 (State != IN_POSITION)

### After
- ✅ 기존 포지션 감지
- ✅ State 일치 (Position → IN_POSITION)
- ✅ Entry 차단 (state_not_flat)
- ✅ Stop loss 활성화 (Position management 정상 작동)

---

## Files Changed

1. `src/infrastructure/exchange/market_data_interface.py` - Protocol 확장
2. `src/infrastructure/exchange/bybit_adapter.py` - get_position() 구현
3. `src/infrastructure/exchange/fake_market_data.py` - get_position() stub
4. `src/application/orchestrator.py` - Position recovery 로직
5. `tests/unit/test_orchestrator_position_recovery.py` - Unit test (NEW)
6. `tests/integration/test_orchestrator_session_risk.py` - get_position() stub 추가
7. `tests/unit/test_bybit_rest_client.py` - V5 API 테스트 수정

---

## Completion Checklist

- [x] Unit test 작성 (RED → GREEN)
- [x] Regression test 통과 (323 tests)
- [x] Testnet 검증 (실제 position 감지 확인)
- [x] State 일치 확인 (IN_POSITION)
- [x] Position 객체 생성 확인
- [x] Entry 차단 확인 (state_not_flat)
- [x] Evidence 생성 완료
- [x] Git commit 완료 (bb4a1dc)

---

## Next Steps

Phase 12a-4 (Testnet Automated Trading) 완료를 위한 다음 작업:
1. Exit flow 검증 (Stop loss trigger → EXIT_PENDING → FLAT)
2. Full cycle 검증 (Entry → IN_POSITION → Exit → FLAT)
3. Trade log 검증 (Exit 시 로그 생성)
4. 5-10 cycles 자동 실행 (Position recovery 포함)

---

**Status**: ✅ Position Recovery 완료
**Next**: Phase 12a-4 Full Cycle Validation
