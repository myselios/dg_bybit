# Phase 3 RED→GREEN Proof

## Overview
Phase 3는 TDD 방식으로 구현되었습니다:
1. 테스트 먼저 작성 (RED 확인)
2. 최소 구현 (GREEN 달성)
3. 리팩토링 (import 경로 정렬)

총 20개 테스트 추가: 114 passed → 134 passed (+20)

---

## Case 1: Fee Spike Detection (test_fee_verification.py)

### Test File
[tests/unit/test_fee_verification.py:69-112](../../../tests/unit/test_fee_verification.py#L69-L112)

### Preconditions
```python
estimated_fee_usd = 0.01
actual_fee_btc = 0.0000004  # 2x of estimated
exec_price = 50000.0
```

### Expected Outcome
- actual_fee_usd = 0.0000004 × 50000 = 0.02 USD
- fee_ratio = 0.02 / 0.01 = 2.0 (> 1.5)
- spike_detected = True
- tightening_required = True
- tighten_until_ts = now() + 86400

### Implementation
[src/application/fee_verification.py:56-108](../../../src/application/fee_verification.py#L56-L108)

```python
def verify_fee_post_trade(
    estimated_fee_usd: float,
    actual_fee_btc: float,
    exec_price: float,
    estimated_fee_rate: float,
) -> FeeVerificationResult:
    # Actual fee 계산 (BTC → USD)
    actual_fee_usd = actual_fee_btc * exec_price

    # Fee ratio 계산
    if estimated_fee_usd > 0:
        fee_ratio = actual_fee_usd / estimated_fee_usd
    else:
        fee_ratio = 0.0

    # Spike 감지 (1.5x 초과)
    spike_detected = fee_ratio > 1.5

    # Tightening 설정 (24시간)
    if spike_detected:
        tightening_required = True
        tighten_until_ts = time() + 86400
    else:
        tightening_required = False
        tighten_until_ts = None

    return FeeVerificationResult(
        spike_detected=spike_detected,
        fee_ratio=fee_ratio,
        tightening_required=tightening_required,
        tighten_until_ts=tighten_until_ts,
    )
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_fee_verification.py::test_verify_fee_post_trade_spike_detected -v
# → ModuleNotFoundError: No module named 'application.fee_verification'

# GREEN (구현 후)
pytest tests/unit/test_fee_verification.py::test_verify_fee_post_trade_spike_detected -v
# → PASSED
```

---

## Case 2: Entry Order Placement (test_order_executor.py)

### Test File
[tests/unit/test_order_executor.py:51-76](../../../tests/unit/test_order_executor.py#L51-L76)

### Preconditions
```python
symbol = "BTCUSD"
side = "Buy"
qty = 100
price = 50000.0
signal_id = "test_1"
direction = "LONG"
```

### Expected Outcome
- orderLinkId = "test_1_Buy"
- positionIdx = 0 (One-way 모드)
- status = "New"
- validate_order_link_id(orderLinkId) = True

### Implementation
[src/application/order_executor.py:87-142](../../../src/application/order_executor.py#L87-L142)

```python
def place_entry_order(
    symbol: str,
    side: str,
    qty: int,
    price: float,
    signal_id: str,
    direction: str,
) -> OrderResult:
    # orderLinkId 생성
    order_link_id = f"{signal_id}_{side}"

    # orderLinkId 길이 검증 (36자 제한)
    if not validate_order_link_id(order_link_id):
        raise ValueError(f"orderLinkId too long or invalid: {order_link_id}")

    # Idempotency 검증 (중복 방지)
    if order_link_id in _order_store:
        return _order_store[order_link_id]

    # 주문 실행 (Fake implementation)
    order_id = f"order_{len(_order_store) + 1}"
    result = OrderResult(
        order_id=order_id,
        order_link_id=order_link_id,
        status="New",
    )

    # Store 저장
    _order_store[order_link_id] = result

    return result
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_order_executor.py::test_place_entry_order_success -v
# → ModuleNotFoundError: No module named 'application.order_executor'

# GREEN (구현 후)
pytest tests/unit/test_order_executor.py::test_place_entry_order_success -v
# → PASSED
```

---

## Case 3: Stop Loss Conditional Order (test_order_executor.py)

### Test File
[tests/unit/test_order_executor.py:179-232](../../../tests/unit/test_order_executor.py#L179-L232)

### Preconditions
```python
qty = 100
stop_price = 49000.0
direction = "LONG"
signal_id = "test_1"
```

### Expected Outcome (LONG Stop)
- orderType = "Market"
- triggerPrice = 49000.0
- triggerDirection = 2 (falling, LastPrice < triggerPrice)
- reduceOnly = True
- positionIdx = 0
- side = "Sell" (LONG 청산)
- orderLinkId = "test_1_stop_Sell"

### Implementation
[src/application/order_executor.py:144-205](../../../src/application/order_executor.py#L144-L205)

```python
def place_stop_loss(
    symbol: str,
    qty: int,
    stop_price: float,
    direction: str,
    signal_id: str,
) -> OrderResult:
    # Direction별 파라미터 설정
    if direction == "LONG":
        side = "Sell"  # LONG 청산
        trigger_direction = 2  # falling (LastPrice < triggerPrice)
    elif direction == "SHORT":
        side = "Buy"  # SHORT 청산
        trigger_direction = 1  # rising (LastPrice > triggerPrice)
    else:
        raise ValueError(f"Invalid direction: {direction}")

    # orderLinkId 생성
    order_link_id = f"{signal_id}_stop_{side}"

    # 주문 실행 (Fake implementation)
    order_id = f"stop_{len(_order_store) + 1}"
    result = OrderResult(
        order_id=order_id,
        order_link_id=order_link_id,
        status="New",
        order_type="Market",
        trigger_price=stop_price,
        trigger_direction=trigger_direction,
        reduce_only=True,
        position_idx=0,
        side=side,
    )

    return result
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_order_executor.py::test_place_stop_loss_conditional_order_params -v
# → ModuleNotFoundError

# GREEN (구현 후)
pytest tests/unit/test_order_executor.py::test_place_stop_loss_conditional_order_params -v
# → PASSED
```

---

## Case 4: FILL Event → IN_POSITION (test_event_handler.py)

### Test File
[tests/unit/test_event_handler.py:35-93](../../../tests/unit/test_event_handler.py#L35-L93)

### Preconditions
```python
state = ENTRY_PENDING
event = ExecutionEvent(
    type=EventType.FILL,
    filled_qty=100,
    order_qty=100,
)
pending_order = PendingOrder(
    side="Buy",
    qty=100,
    price=50000.0,
)
```

### Expected Outcome
- new_state = IN_POSITION
- position.qty = 100
- position.stop_status = PENDING
- StopIntent.action = "PLACE"
- StopIntent.desired_qty = 100

### Implementation
[src/application/event_handler.py:52-91](../../../src/application/event_handler.py#L52-L91)

```python
def handle_execution_event(
    event: ExecutionEvent,
    current_state: State,
    current_position: Optional[Position],
    pending_order: Optional[PendingOrder],
) -> HandleResult:
    # Step 1: transition() 호출 (pure function)
    new_state, new_position, intents = transition(
        current_state=current_state,
        current_position=current_position,
        event=event,
        pending_order=pending_order,
    )

    # Step 2: intents 실행 (I/O 레이어)
    # (실제 구현에서는 execute_intents()를 호출하여 I/O 수행)
    # 여기서는 HandleResult만 반환 (executor는 별도 호출)

    # Step 3: 결과 반환
    return HandleResult(
        new_state=new_state,
        new_position=new_position,
        intents=intents,
    )
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_event_handler.py::test_handle_fill_event_entry_pending_to_in_position -v
# → ModuleNotFoundError: No module named 'application.event_handler'

# GREEN (구현 후)
pytest tests/unit/test_event_handler.py::test_handle_fill_event_entry_pending_to_in_position -v
# → PASSED
```

---

## TDD 확인 (전체)

### Phase 3 시작 전
```bash
ls src/application/fee_verification.py 2>/dev/null
# → (파일 없음)

pytest -q
# → 114 passed in 0.09s
```

### Phase 3 구현 중
```bash
# Step 1: 테스트 먼저 작성
cat tests/unit/test_fee_verification.py
# → test_estimate_fee_usd_inverse_formula, ...

# Step 2: RED 확인
pytest tests/unit/test_fee_verification.py -v
# → ModuleNotFoundError

# Step 3: 최소 구현
cat src/application/fee_verification.py
# → estimate_fee_usd(), verify_fee_post_trade(), apply_fee_spike_tightening()

# Step 4: GREEN 달성
pytest tests/unit/test_fee_verification.py -v
# → 5 passed
```

### Phase 3 완료 후
```bash
pytest -q
# → 134 passed in 0.11s (114 → 134, +20 tests)

# 파일 확인
ls -1 src/application/*.py | grep -E "(fee_verification|order_executor|event_handler)"
# → src/application/event_handler.py
# → src/application/fee_verification.py
# → src/application/order_executor.py
```

---

## Summary

Phase 3는 **TDD 방식으로 구현**되었으며, 모든 케이스에서 **RED → GREEN 전환**을 확인했습니다.

- **20개 테스트 추가** (5 + 8 + 7)
- **134 passed** (114 → 134)
- **3개 모듈 구현** (fee_verification, order_executor, event_handler)
- **SSOT 준수** (FLOW Section 2.5, 4.5, 6.2, 8)
- **Import 경로 정렬** (src 없이, editable mode 표준 준수)

**새 세션에서도 재현 가능**: 이 문서와 Evidence artifacts로 Phase 3 구현 과정을 검증할 수 있습니다.
