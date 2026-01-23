# Phase 2 RED→GREEN Proof

## Overview
Phase 2는 TDD 방식으로 구현되었습니다:
1. 테스트 먼저 작성 (RED 확인)
2. 최소 구현 (GREEN 달성)
3. 리팩토링 (필요 시)

총 31개 테스트 추가: 83 passed → 114 passed (+31)

---

## Case 1: signal_id 생성 (test_ids.py)

### Test File
[tests/unit/test_ids.py:34-52](../../../tests/unit/test_ids.py#L34-L52)

### Preconditions
```python
strategy = "grid"
bar_close_ts = 1705593600
side = "long"
```

### Expected Outcome
- 동일한 입력 → 동일한 signal_id (idempotency)
- 형식: `{strategy}_{hash_10char}_{side}`
- 예: `"grid_a3f8d2e1c4_l"`
- 길이: ≤ 36자

### Implementation
[src/domain/ids.py:15-42](../../../src/domain/ids.py#L15-L42)

```python
def generate_signal_id(strategy: str, bar_close_ts: int, side: str) -> str:
    """
    Generate deterministic signal_id (SHA1 based)

    Format: {strategy_prefix}_{hash_10char}_{side_1char}
    """
    payload = f"{strategy}_{bar_close_ts}_{side}"
    hash_digest = hashlib.sha1(payload.encode()).hexdigest()
    hash_suffix = hash_digest[:10]

    side_char = "l" if side == "long" else "s"
    strategy_prefix = strategy[:16]

    signal_id = f"{strategy_prefix}_{hash_suffix}_{side_char}"
    return signal_id
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_ids.py::test_generate_signal_id_deterministic -v
# → ModuleNotFoundError: No module named 'src.domain.ids'

# GREEN (구현 후)
pytest tests/unit/test_ids.py::test_generate_signal_id_deterministic -v
# → PASSED
```

---

## Case 2: Entry Gate - HALT 차단 (test_entry_allowed.py)

### Test File
[tests/unit/test_entry_allowed.py:62-90](../../../tests/unit/test_entry_allowed.py#L62-L90)

### Preconditions
```python
state = State.HALT  # Emergency HALT 상태
stage = STAGE_1  # Stage 1 params
trades_today = 0
atr_pct_24h = 0.05  # 충분히 높음
signal = SignalContext(
    expected_profit_usd=5.0,
    estimated_fee_usd=1.0,  # EV = 5x (충분히 통과)
    is_maker=True,
)
winrate = 0.60  # 충분히 높음
position_mode = "MergedSingle"  # One-way
cooldown_until = None
```

### Expected Outcome
```python
decision.allowed = False
decision.reject_reason = "state_halt"
```

### Implementation
[src/application/entry_allowed.py:55-71](../../../src/application/entry_allowed.py#L55-L71)

```python
def check_entry_allowed(...) -> EntryDecision:
    # Gate 1: HALT/COOLDOWN 상태 검증
    if state == State.HALT:
        return EntryDecision(
            allowed=False,
            reject_reason="state_halt",
        )

    if state == State.COOLDOWN:
        if current_time < cooldown_until:
            return EntryDecision(
                allowed=False,
                reject_reason="cooldown_active",
            )
    # ... (나머지 gates)
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_entry_allowed.py::test_gate_halt_rejects -v
# → ModuleNotFoundError: No module named 'src.application.entry_allowed'

# GREEN (구현 후)
pytest tests/unit/test_entry_allowed.py::test_gate_halt_rejects -v
# → PASSED
```

---

## Case 3: Sizing LONG Contracts (test_sizing.py)

### Test File
[tests/unit/test_sizing.py:44-81](../../../tests/unit/test_sizing.py#L44-L81)

### Preconditions
```python
params = SizingParams(
    max_loss_btc=0.001,
    entry_price_usd=100000.0,
    stop_distance_pct=0.03,  # 3%
    leverage=3.0,
    equity_btc=0.02,  # 충분히 높음 (margin 통과용)
    fee_rate=0.0001,
    direction="LONG",
    qty_step=1,
    tick_size=0.5,
)
```

### Expected Outcome
```python
# FLOW Section 3.4 (LONG):
# contracts = (max_loss_btc × entry × (1 - stop_distance_pct)) / stop_distance_pct
contracts = (0.001 × 100000 × (1 - 0.03)) / 0.03
          = (100 × 0.97) / 0.03
          = 97 / 0.03
          = 3233.33
          → floor(3233) = 3233

result.contracts = 3233
result.reject_reason = None
```

### Implementation
[src/application/sizing.py:90-124](../../../src/application/sizing.py#L90-L124)

```python
def calculate_contracts(params) -> SizingResult:
    # Step 1: Contracts from loss budget (Direction별 정확한 공식)
    if params.direction == "LONG":
        numerator = (
            params.max_loss_btc
            * params.entry_price_usd
            * (1 - params.stop_distance_pct)
        )
        contracts_from_loss = numerator / params.stop_distance_pct
    elif params.direction == "SHORT":
        numerator = (
            params.max_loss_btc
            * params.entry_price_usd
            * (1 + params.stop_distance_pct)
        )
        contracts_from_loss = numerator / params.stop_distance_pct

    # Step 2: Contracts from margin (80% buffer)
    available_btc = params.equity_btc * 0.8
    max_position_value_btc = available_btc * params.leverage
    contracts_from_margin = max_position_value_btc * params.entry_price_usd

    # Step 3: min(loss, margin)
    contracts = min(contracts_from_loss, contracts_from_margin)
    contracts = int(contracts)  # floor

    # Step 4: Tick/Lot size 보정
    contracts = int(contracts / params.qty_step) * params.qty_step

    # Step 5: 최소 수량 검증
    if contracts < params.qty_step:
        return SizingResult(contracts=0, reject_reason="qty_below_minimum")

    # Step 6: 재검증 (margin feasibility)
    # ...

    return SizingResult(contracts=contracts)
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_sizing.py::test_contracts_from_loss_budget_long -v
# → ModuleNotFoundError: No module named 'src.application.sizing'

# GREEN (구현 후)
pytest tests/unit/test_sizing.py::test_contracts_from_loss_budget_long -v
# → PASSED
```

---

## Case 4: Liquidation Distance LONG (test_liquidation_gate.py)

### Test File
[tests/unit/test_liquidation_gate.py:36-61](../../../tests/unit/test_liquidation_gate.py#L36-L61)

### Preconditions
```python
entry_price = 100000.0
contracts = 1000
leverage = 3.0
direction = "LONG"
equity_btc = 0.01
```

### Expected Outcome
```python
# FLOW Section 7.5 (LONG):
# liq_price ≈ entry × leverage / (leverage + 1)
# liq_distance = (entry - liq_price) / entry

liq_price ≈ 100000 × 3 / (3 + 1) = 75000
liq_distance = (100000 - 75000) / 100000 = 0.25 (25%)

assert liq_distance ≈ 0.25
```

### Implementation
[src/application/liquidation_gate.py:49-81](../../../src/application/liquidation_gate.py#L49-L81)

```python
def calculate_liquidation_distance(
    entry_price: float,
    contracts: int,
    leverage: float,
    direction: str,
    equity_btc: float,
) -> float:
    """
    Liquidation distance 계산 (Bybit Inverse, 보수적 근사)
    """
    if direction == "LONG":
        # LONG: 청산가는 entry보다 낮음
        liq_price_approx = entry_price * leverage / (leverage + 1)
        liq_distance_pct = (entry_price - liq_price_approx) / entry_price
    elif direction == "SHORT":
        # SHORT: 청산가는 entry보다 높음
        liq_price_approx = entry_price * leverage / (leverage - 1)
        liq_distance_pct = (liq_price_approx - entry_price) / entry_price

    return liq_distance_pct
```

### RED → GREEN Verification
```bash
# RED (구현 전)
pytest tests/unit/test_liquidation_gate.py::test_calculate_liquidation_distance_long -v
# → ModuleNotFoundError: No module named 'src.application.liquidation_gate'

# GREEN (구현 후)
pytest tests/unit/test_liquidation_gate.py::test_calculate_liquidation_distance_long -v
# → PASSED
```

---

## TDD 확인 (전체)

### Phase 2 시작 전
```bash
ls tests/unit/test_ids.py 2>/dev/null
# → (파일 없음)

pytest -q
# → 83 passed in 0.06s
```

### Phase 2 구현 중
```bash
# Step 1: 테스트 먼저 작성
cat tests/unit/test_ids.py
# → test_generate_signal_id_deterministic, ...

# Step 2: RED 확인
pytest tests/unit/test_ids.py -v
# → ModuleNotFoundError

# Step 3: 최소 구현
cat src/domain/ids.py
# → generate_signal_id(), validate_order_link_id()

# Step 4: GREEN 달성
pytest tests/unit/test_ids.py -v
# → 6 passed
```

### Phase 2 완료 후
```bash
pytest -q
# → 114 passed in 0.09s (83 → 114, +31 tests)

# 파일 확인
ls -1 tests/unit/test_*.py | grep -E "(ids|entry_allowed|sizing|liquidation_gate)"
# → tests/unit/test_ids.py
# → tests/unit/test_entry_allowed.py
# → tests/unit/test_sizing.py
# → tests/unit/test_liquidation_gate.py
```

---

## Summary

Phase 2는 **TDD 방식으로 구현**되었으며, 모든 케이스에서 **RED → GREEN 전환**을 확인했습니다.

- **31개 테스트 추가** (6 + 9 + 8 + 8)
- **114 passed** (83 → 114)
- **4개 모듈 구현** (ids, entry_allowed, sizing, liquidation_gate)
- **SSOT 준수** (FLOW Section 2, 3.4, 7.5, 8 + Policy Section 5, 10)

**새 세션에서도 재현 가능**: 이 문서와 Evidence artifacts로 Phase 2 구현 과정을 검증할 수 있습니다.
