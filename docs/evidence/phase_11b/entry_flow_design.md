# Entry Flow Implementation Design — orchestrator._decide_entry()

**작성일**: 2026-01-24
**Phase**: 11b (Full Orchestrator Integration)
**Target**: [orchestrator.py:264-287](../../src/application/orchestrator.py#L264-L287) `_decide_entry()` 메서드

---

## 1. 현재 상태 (Current State)

### 1.1 기존 구현 ([orchestrator.py:264-287](../../src/application/orchestrator.py#L264-L287))

```python
def _decide_entry(self) -> dict:
    """
    Entry 결정 (signal → gate → sizing)

    Returns:
        {"blocked": bool, "reason": str}

    FLOW Section 2.4:
        - degraded_mode → entry 차단
    """
    # degraded mode 체크
    ws_degraded = self.market_data.is_ws_degraded()
    if ws_degraded and self.state == State.FLAT:
        return {"blocked": True, "reason": "degraded_mode"}

    # degraded timeout 체크 (60초)
    degraded_timeout = self.market_data.is_degraded_timeout()
    if degraded_timeout:
        self.state = State.HALT
        return {"blocked": True, "reason": "degraded_mode_timeout"}

    return {"blocked": False, "reason": None}
```

**문제**:
- Signal generation 없음
- Entry gates 검증 없음
- Sizing 계산 없음
- Order placement 없음
- FLAT → ENTRY_PENDING 전환 없음

---

## 2. 설계 목표 (Design Goals)

### 2.1 FLOW.md 준수

**FLOW Section 2.4: Entry Decision Flow**
```
1. FLAT 상태 확인
2. degraded_mode 체크
3. Signal generation (grid-based)
4. Entry gates (8 gates)
5. Position sizing (loss budget + margin)
6. Order placement (REST API)
7. FLAT → ENTRY_PENDING 전환
```

### 2.2 책임 분리 (Separation of Concerns)

**Thin wrapper 원칙** (FLOW Section 4.2):
- orchestrator.py는 **호출만** 수행
- 로직은 각 모듈에 위임:
  - Signal generation: `signal_generator.py`
  - Entry gates: `entry_allowed.py`
  - Sizing: `sizing.py`
  - Order placement: `bybit_rest_client.py`

**God Object 금지**:
- orchestrator.py는 500 LOC 초과 금지
- Entry flow 로직은 최소 50 LOC 이내 (호출 코드만)

---

## 3. 구현 설계 (Implementation Design)

### 3.1 Entry Flow 단계 (Step-by-Step)

#### Step 1: FLAT 상태 확인
```python
if self.state != State.FLAT:
    return {"blocked": True, "reason": "state_not_flat"}
```

**이유**: Entry는 FLAT 상태에서만 가능 (IN_POSITION에서 Entry 시도 = 포지션 누적)

---

#### Step 2: degraded_mode 체크 (기존 유지)
```python
ws_degraded = self.market_data.is_ws_degraded()
if ws_degraded:
    return {"blocked": True, "reason": "degraded_mode"}

degraded_timeout = self.market_data.is_degraded_timeout()
if degraded_timeout:
    self.state = State.HALT
    return {"blocked": True, "reason": "degraded_mode_timeout"}
```

**이유**: WS degraded 시 FILL event 수신 불가 → Entry 차단

---

#### Step 3: Signal generation
```python
from application.signal_generator import generate_signal, calculate_grid_spacing

# ATR 가져오기 (Grid spacing 계산용)
atr = self.market_data.get_atr()
if atr is None:
    return {"blocked": True, "reason": "atr_unavailable"}

# Grid spacing 계산 (ATR * 2.0)
grid_spacing = calculate_grid_spacing(atr=atr, multiplier=2.0)

# 현재 가격
current_price = self.market_data.get_current_price()

# 마지막 체결 가격 (Grid 기준점)
last_fill_price = self.market_data.get_last_fill_price()

# Signal 생성 (Grid up/down)
signal = generate_signal(
    current_price=current_price,
    last_fill_price=last_fill_price,
    grid_spacing=grid_spacing,
    qty=0,  # Sizing에서 계산
)

# Signal이 없으면 차단
if signal is None:
    return {"blocked": True, "reason": "no_signal"}
```

**의존성**:
- `market_data.get_atr()`: ATR 값 (Phase 2에서 구현 필요 확인)
- `market_data.get_last_fill_price()`: 마지막 체결 가격 (Phase 2에서 구현 필요 확인)

**리스크**:
- `get_atr()`, `get_last_fill_price()` 미구현 시 **Entry 불가**
- 해결: `FakeMarketData` (Phase 6)에 메서드 추가 필요

---

#### Step 4: Entry gates 검증
```python
from application.entry_allowed import check_entry_allowed, EntryDecision

# Stage params (Policy Section 5)
stage = self._get_stage_params()

# Trades today
trades_today = self.market_data.get_trades_today()

# ATR pct 24h
atr_pct_24h = self.market_data.get_atr_pct_24h()

# Signal context (EV gate용)
signal_context = self._build_signal_context(signal)

# Winrate
winrate = self.market_data.get_winrate()

# Position mode
position_mode = self.market_data.get_position_mode()

# Cooldown until
cooldown_until = None  # COOLDOWN 구현 시 추가

# Current time
current_time = self.market_data.get_current_timestamp()

# Entry gates 검증
entry_decision: EntryDecision = check_entry_allowed(
    state=self.state,
    stage=stage,
    trades_today=trades_today,
    atr_pct_24h=atr_pct_24h,
    signal=signal_context,
    winrate=winrate,
    position_mode=position_mode,
    cooldown_until=cooldown_until,
    current_time=current_time,
)

# Gate 거절 시 차단
if not entry_decision.allowed:
    return {"blocked": True, "reason": entry_decision.reject_reason}
```

**의존성**:
- `self._get_stage_params()`: Stage 파라미터 반환 (Policy Section 5)
- `self._build_signal_context()`: Signal context 생성 (EV gate용)
- `market_data.get_trades_today()`: 오늘 거래 횟수
- `market_data.get_atr_pct_24h()`: 24시간 ATR (pct)
- `market_data.get_winrate()`: 현재 winrate
- `market_data.get_position_mode()`: Position mode (MergedSingle = one-way)

**리스크**:
- `market_data` 메서드 미구현 시 **Entry 불가**
- 해결: `FakeMarketData`에 메서드 추가 + Integration test에서 실제 구현

---

#### Step 5: Position sizing
```python
from application.sizing import calculate_contracts, SizingResult

# Sizing params
sizing_params = self._build_sizing_params(signal)

# Contracts 계산
sizing_result: SizingResult = calculate_contracts(params=sizing_params)

# Sizing 실패 시 차단
if sizing_result.contracts == 0:
    return {"blocked": True, "reason": sizing_result.reject_reason}

# 계약 수 저장
contracts = sizing_result.contracts
```

**의존성**:
- `self._build_sizing_params()`: Sizing 파라미터 생성
- `sizing.calculate_contracts()`: Contracts 계산 (Phase 2 구현 완료)

---

#### Step 6: Order placement
```python
from infrastructure.exchange.bybit_rest_client import BybitRestClient

# Order placement
try:
    # Entry order 발주 (Limit order, Maker)
    order_result = self.rest_client.place_order(
        symbol="BTCUSD",
        side=signal.side,  # "Buy" or "Sell"
        order_type="Limit",
        qty=contracts,
        price=signal.price,
        time_in_force="PostOnly",  # Maker-only
        order_link_id=f"entry_{self._generate_signal_id()}",
    )

    # Order ID 저장
    order_id = order_result["orderId"]
    order_link_id = order_result["orderLinkId"]

except Exception as e:
    # Order placement 실패 → 차단
    return {"blocked": True, "reason": f"order_placement_failed: {str(e)}"}
```

**의존성**:
- `self.rest_client`: BybitRestClient 인스턴스 (orchestrator.__init__에 추가 필요)
- `self._generate_signal_id()`: Signal ID 생성 (타임스탬프 기반)

**리스크**:
- REST API timeout (5초)
- Order rejection (InsufficientBalance, InvalidQty)
- 해결: Retry 로직 (우선순위 2)

---

#### Step 7: FLAT → ENTRY_PENDING 전환
```python
# State 전환
self.state = State.ENTRY_PENDING

# Pending order 저장 (FILL event 매칭용)
self.pending_order = {
    "order_id": order_id,
    "order_link_id": order_link_id,
    "side": signal.side,
    "qty": contracts,
    "price": signal.price,
    "signal_id": self.current_signal_id,
}

return {"blocked": False, "reason": None}
```

**의존성**:
- `self.pending_order`: Pending order 정보 저장 (orchestrator에 필드 추가 필요)
- `self.current_signal_id`: 현재 Signal ID (orchestrator에 필드 추가 필요)

---

### 3.2 Helper 메서드 설계

#### 3.2.1 `_get_stage_params()` — Stage 파라미터 반환

```python
def _get_stage_params(self):
    """
    Stage 파라미터 반환 (Policy Section 5)

    Returns:
        StageParams: Stage 파라미터 객체
    """
    # 현재는 Stage 1 고정 (추후 동적 변경)
    return StageParams(
        max_trades_per_day=10,
        atr_pct_24h_min=0.02,  # 2%
        ev_fee_multiple_k=2.0,
        maker_only_default=True,
    )
```

**TODO**: `StageParams` 클래스 정의 필요 (application layer 또는 domain layer)

---

#### 3.2.2 `_build_signal_context()` — Signal context 생성 (EV gate용)

```python
def _build_signal_context(self, signal):
    """
    Signal context 생성 (EV gate용)

    Args:
        signal: Signal 객체 (signal_generator.Signal)

    Returns:
        SignalContext: Signal context 객체
    """
    # Expected profit (Grid spacing * contracts * price)
    # 간단한 근사: grid_spacing * contracts / entry_price
    # (실제 PnL 계산은 LONG/SHORT 방향 고려 필요)

    # Fee 추정 (Maker: 0.01%, Taker: 0.06%)
    fee_rate = 0.0001 if signal.is_maker else 0.0006
    estimated_fee_usd = signal.qty * fee_rate * signal.price

    # Expected profit (간단한 근사)
    expected_profit_usd = signal.qty * self.grid_spacing / signal.price

    return SignalContext(
        expected_profit_usd=expected_profit_usd,
        estimated_fee_usd=estimated_fee_usd,
        is_maker=True,  # Maker-only 전략
    )
```

**TODO**: `SignalContext` 클래스 정의 필요

---

#### 3.2.3 `_build_sizing_params()` — Sizing 파라미터 생성

```python
def _build_sizing_params(self, signal):
    """
    Sizing 파라미터 생성

    Args:
        signal: Signal 객체 (signal_generator.Signal)

    Returns:
        SizingParams: Sizing 파라미터 객체
    """
    # Equity BTC
    equity_btc = self.market_data.get_equity_btc()

    # Max loss BTC (loss budget = 1% equity per trade)
    max_loss_btc = equity_btc * 0.01

    # Direction (Buy → LONG, Sell → SHORT)
    direction = "LONG" if signal.side == "Buy" else "SHORT"

    # Stop distance pct (3%)
    stop_distance_pct = 0.03

    # Leverage (Stage 1 = 3x)
    leverage = 3.0

    # Fee rate (Maker: 0.01%)
    fee_rate = 0.0001

    # Tick/Lot size (Bybit BTCUSD)
    tick_size = 0.5
    qty_step = 1

    return SizingParams(
        max_loss_btc=max_loss_btc,
        entry_price_usd=signal.price,
        stop_distance_pct=stop_distance_pct,
        leverage=leverage,
        equity_btc=equity_btc,
        fee_rate=fee_rate,
        direction=direction,
        qty_step=qty_step,
        tick_size=tick_size,
    )
```

**TODO**: `SizingParams` 클래스 정의 확인 (sizing.py에 이미 있음)

---

#### 3.2.4 `_generate_signal_id()` — Signal ID 생성

```python
def _generate_signal_id(self) -> str:
    """
    Signal ID 생성 (타임스탬프 기반)

    Returns:
        str: Signal ID (예: "20260124_001")
    """
    import time
    timestamp = int(time.time())
    return f"{timestamp}"
```

---

### 3.3 orchestrator.__init__ 수정

```python
def __init__(self, market_data: MarketDataInterface, rest_client: BybitRestClient):
    """
    Orchestrator 초기화

    Args:
        market_data: Market data interface (FakeMarketData or BybitAdapter)
        rest_client: Bybit REST client (Order placement용)
    """
    self.market_data = market_data
    self.rest_client = rest_client  # Phase 11b 추가
    self.state = State.FLAT
    self.position: Optional[Position] = None

    # Phase 11b 추가: Pending order tracking
    self.pending_order: Optional[dict] = None
    self.current_signal_id: Optional[str] = None

    # Session Risk Policy 설정 (Phase 9c)
    # ... (기존 유지)
```

---

## 4. 의존성 분석 (Dependency Analysis)

### 4.1 MarketDataInterface 확장 필요

**현재 구현** (Phase 6):
- `get_equity_btc()`: ✅ 구현됨
- `get_btc_mark_price_usd()`: ✅ 구현됨
- `get_current_price()`: ✅ 구현됨
- `is_ws_degraded()`: ✅ 구현됨
- `is_degraded_timeout()`: ✅ 구현됨

**Phase 11b 추가 필요**:
- `get_atr()`: ATR 값 (Signal generation용) ❌ 미구현
- `get_last_fill_price()`: 마지막 체결 가격 (Grid 기준점용) ❌ 미구현
- `get_trades_today()`: 오늘 거래 횟수 (Entry gate용) ❌ 미구현
- `get_atr_pct_24h()`: 24시간 ATR (pct) (Entry gate용) ❌ 미구현
- `get_winrate()`: 현재 winrate (Entry gate용) ❌ 미구현
- `get_position_mode()`: Position mode (Entry gate용) ❌ 미구현
- `get_current_timestamp()`: 현재 시각 (Entry gate용) ❌ 미구현

**해결 전략**:
1. **Unit test (FakeMarketData)**: 모든 메서드를 Mock 구현 (고정값 반환)
2. **Integration test (Testnet)**: 실제 Bybit API에서 값 가져오기

---

### 4.2 새 클래스 정의 필요

#### 4.2.1 `StageParams` — Stage 파라미터
```python
@dataclass
class StageParams:
    """Stage 파라미터 (Policy Section 5)"""
    max_trades_per_day: int
    atr_pct_24h_min: float
    ev_fee_multiple_k: float
    maker_only_default: bool
```

**위치**: `src/domain/policy.py` (신규 파일) 또는 `src/application/entry_allowed.py` (기존 파일)

---

#### 4.2.2 `SignalContext` — Signal context (EV gate용)
```python
@dataclass
class SignalContext:
    """Signal context (EV gate용)"""
    expected_profit_usd: float
    estimated_fee_usd: float
    is_maker: bool
```

**위치**: `src/application/signal_generator.py` 또는 `src/domain/signal.py` (신규 파일)

---

### 4.3 orchestrator.py LOC 예상

**기존**: 288 LOC
**Entry flow 추가**: +80 LOC (Step 1~7)
**Helper 메서드**: +40 LOC (4개 메서드)
**__init__ 수정**: +5 LOC

**최종 예상**: 288 + 80 + 40 + 5 = **413 LOC** (✅ 500 LOC 이하, God Object 금지 준수)

---

## 5. 테스트 전략 (Testing Strategy)

### 5.1 Unit Test (tests/unit/test_orchestrator_entry_flow.py)

**테스트 케이스**:
1. `test_entry_flow_success` — 정상 Entry flow (FLAT → ENTRY_PENDING)
2. `test_entry_blocked_state_not_flat` — FLAT이 아닐 때 차단
3. `test_entry_blocked_degraded_mode` — degraded mode 시 차단
4. `test_entry_blocked_no_signal` — Signal 없을 때 차단
5. `test_entry_blocked_gate_reject` — Entry gate 거절 시 차단
6. `test_entry_blocked_sizing_fail` — Sizing 실패 시 차단
7. `test_entry_blocked_order_placement_fail` — Order placement 실패 시 차단

**Mock 대상**:
- `market_data.*`: 모든 get_* 메서드 Mock
- `rest_client.place_order()`: Order placement Mock
- `signal_generator.*`: Signal generation Mock

---

### 5.2 Integration Test (tests/integration_real/test_entry_flow_testnet.py)

**테스트 케이스**:
1. `test_entry_flow_testnet_success` — Testnet에서 Entry order 발주 성공
2. `test_entry_flow_testnet_fill` — Entry order FILL → IN_POSITION 전환

**실제 호출**:
- Bybit Testnet API (REST, WS)
- Real market data (ATR, last fill price, etc.)

---

## 6. 구현 순서 (Implementation Order)

### Phase 1: 의존성 추가 (Dependency Setup)
1. `MarketDataInterface` 메서드 추가 (7개 메서드)
2. `FakeMarketData` Mock 구현 (고정값 반환)
3. `StageParams`, `SignalContext` 클래스 정의

### Phase 2: Helper 메서드 구현
1. `_get_stage_params()` 구현
2. `_build_signal_context()` 구현
3. `_build_sizing_params()` 구현
4. `_generate_signal_id()` 구현

### Phase 3: Entry Flow 구현
1. orchestrator.__init__ 수정 (rest_client, pending_order 추가)
2. orchestrator._decide_entry() 수정 (Step 1~7)

### Phase 4: Unit Test 작성 (TDD: RED → GREEN)
1. `test_entry_flow_success` 작성 → FAIL
2. 최소 구현으로 PASS
3. 나머지 테스트 케이스 작성 → PASS

### Phase 5: Integration Test 작성 (Testnet)
1. `test_entry_flow_testnet_success` 작성
2. Testnet 실행 → PASS 확인

---

## 7. 리스크 완화 (Risk Mitigation)

### 7.1 Order Placement 실패 대응

**문제**: REST API timeout, Order rejection

**해결** (우선순위 2):
```python
# Retry 로직 (3회 재시도)
for attempt in range(3):
    try:
        order_result = self.rest_client.place_order(...)
        break
    except Exception as e:
        if attempt == 2:
            return {"blocked": True, "reason": f"order_placement_failed: {str(e)}"}
        time.sleep(0.5 * (2 ** attempt))  # Exponential backoff
```

---

### 7.2 ATR/last_fill_price 미구현 대응

**문제**: `get_atr()`, `get_last_fill_price()` 미구현 시 Entry 불가

**해결** (우선순위 1):
1. **FakeMarketData (Unit test)**: 고정값 반환 (atr=100, last_fill_price=50000)
2. **Integration test (Testnet)**: Bybit API에서 실제 값 가져오기 (REST API 호출)

---

### 7.3 State vs Pending Order 불일치 대응

**문제**: ENTRY_PENDING인데 pending_order가 None

**해결**:
```python
# Self-healing check (매 Tick 시작 시)
if self.state == State.ENTRY_PENDING and self.pending_order is None:
    # 불일치 감지 → HALT
    self.state = State.HALT
    return TickResult(..., halt_reason="pending_order_missing")
```

---

## 8. 완료 기준 (Definition of Done)

### 8.1 구현 완료
- [ ] MarketDataInterface 메서드 7개 추가
- [ ] FakeMarketData Mock 구현
- [ ] StageParams, SignalContext 클래스 정의
- [ ] Helper 메서드 4개 구현
- [ ] orchestrator.__init__ 수정
- [ ] orchestrator._decide_entry() Step 1~7 구현

### 8.2 Unit Test 완료
- [ ] test_entry_flow_success (RED → GREEN)
- [ ] test_entry_blocked_* (7개 케이스)
- [ ] pytest 실행 → 모든 테스트 PASS

### 8.3 Integration Test 완료
- [ ] test_entry_flow_testnet_success (Testnet 실행)
- [ ] Entry order 발주 성공 확인

### 8.4 Evidence Artifacts
- [ ] pytest_output.txt (Unit test 결과)
- [ ] entry_flow_implementation_proof.md (구현 증거)

---

## 9. 다음 단계 (Next Steps)

**현재 단계**: Entry Flow 설계 완료

**다음 작업**:
1. **MarketDataInterface 확장** (7개 메서드 추가)
2. **FakeMarketData Mock 구현** (Unit test용)
3. **Unit Test 작성** (TDD: RED → GREEN)
4. **Entry Flow 구현** (orchestrator._decide_entry())

**예상 시간**:
- Phase 1 (의존성): 30분
- Phase 2 (Helper 메서드): 30분
- Phase 3 (Entry Flow): 1시간
- Phase 4 (Unit Test): 1시간
- **총 3시간** (천천히 진행)

---

**다음 명령**: MarketDataInterface 확장 작업 시작
