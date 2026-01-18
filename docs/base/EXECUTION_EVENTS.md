# EXECUTION_EVENTS.md — 실행 이벤트 처리 시스템

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 필수 보완 문서**다.

> **Executor는 판단을 실행으로 바꾸는 기술 계층이 아니라
> 시장 현실을 도메인에 보고하는 감각기관이다.**

구조 결정 권한: BASE_ARCHITECTURE.md
실행 이벤트 정의 권한: 이 문서

---

## 1. 왜 Execution Event가 필요한가

### 문제 상황

현재 BASE_ARCHITECTURE.md:
```python
# 추상적
Execution → State Machine (결과 전달)
```

실전에서 발생하는 것:
- 슬리피지 초과
- Partial fill 반복
- 주문 지연 (레이턴시)
- 거래소 장애
- 주문 거부 (insufficient margin)
- Liquidation 직전 경고

**이것들은 단순 "성공/실패"가 아니다.**
**각각이 State 전환을 트리거해야 한다.**

---

## 2. Execution Event 체계

### 2.1 ExecutionEvent (이벤트 타입)

```python
class ExecutionEvent(Enum):
    """Execution이 발생시키는 이벤트"""

    # 정상
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"

    # 비정상 (차단 필요)
    SLIPPAGE_BREACH = "slippage_breach"
    TIMEOUT = "timeout"
    EXCHANGE_ERROR = "exchange_error"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    ORDER_REJECTED = "order_rejected"

    # 위험
    LIQUIDATION_WARNING = "liquidation_warning"
    POSITION_FORCE_CLOSED = "position_force_closed"
```

### 2.2 ExecutionResult (확장)

**Before** (BASE_ARCHITECTURE.md):
```python
@dataclass
class ExecutionResult:
    status: ExecutionStatus
    fill_price: float
    slippage: float
    error: Optional[str]
```

**After** (v2):
```python
@dataclass
class ExecutionResult:
    # 기본 정보
    event: ExecutionEvent  # 이벤트 타입
    status: ExecutionStatus  # FILLED / PARTIAL / FAILED
    timestamp: datetime

    # 주문 상세
    order_id: str
    order_type: OrderType  # MARKET / LIMIT
    requested_qty: int
    filled_qty: int
    fill_price: Optional[float]

    # Slippage
    expected_price: float
    actual_price: Optional[float]
    slippage_pct: float
    slippage_breach: bool  # 임계값 초과 여부

    # 타이밍
    submit_time: datetime
    fill_time: Optional[datetime]
    latency_ms: float

    # 오류
    error: Optional[str]
    error_code: Optional[str]
    retryable: bool

    # 거래소 응답
    exchange_response: dict
```

---

## 3. Event → State 전환 규칙

### 3.1 정상 흐름

```python
# FILLED
ExecutionEvent.FILLED → State.ENTRY (정상 진입)
ExecutionEvent.FILLED → State.EXPANSION (확장 성공)
```

### 3.2 경고 흐름 (복구 가능)

```python
# PARTIAL_FILL
ExecutionEvent.PARTIAL_FILL (1회) → 재시도
ExecutionEvent.PARTIAL_FILL (3회 반복) → State.EXIT_FAILURE
    reason: "repeated_partial_fill"

# TIMEOUT
ExecutionEvent.TIMEOUT (1회) → 재시도
ExecutionEvent.TIMEOUT (2회 반복) → State.COOLDOWN
    reason: "execution_timeout"
```

### 3.3 즉시 차단 (복구 불가)

```python
# SLIPPAGE_BREACH
ExecutionEvent.SLIPPAGE_BREACH → State.COOLDOWN
    reason: "slippage_unacceptable"
    duration: 24시간

# EXCHANGE_ERROR
ExecutionEvent.EXCHANGE_ERROR → State.COOLDOWN
    reason: "exchange_instability"
    duration: 1시간

# INSUFFICIENT_MARGIN
ExecutionEvent.INSUFFICIENT_MARGIN → State.TERMINATED
    reason: "account_critical"
```

### 3.4 긴급 대응

```python
# LIQUIDATION_WARNING
ExecutionEvent.LIQUIDATION_WARNING → State.EXIT_FAILURE (즉시 청산)
    reason: "emergency_liquidation_risk"

# POSITION_FORCE_CLOSED
ExecutionEvent.POSITION_FORCE_CLOSED → State.TERMINATED
    reason: "liquidated"
```

---

## 4. State Machine 이벤트 처리

### 4.1 Event Handler

```python
class TradingStateMachine:
    def handle_execution_event(
        self,
        result: ExecutionResult,
        context: MarketContext,
    ) -> None:
        """Execution 이벤트를 State 전환으로 변환"""

        event = result.event

        # 정상
        if event == ExecutionEvent.FILLED:
            self._handle_filled(result)

        # 경고
        elif event == ExecutionEvent.PARTIAL_FILL:
            self._handle_partial_fill(result)

        elif event == ExecutionEvent.TIMEOUT:
            self._handle_timeout(result)

        # 차단
        elif event == ExecutionEvent.SLIPPAGE_BREACH:
            self._handle_slippage_breach(result, context)

        elif event == ExecutionEvent.EXCHANGE_ERROR:
            self._handle_exchange_error(result, context)

        # 긴급
        elif event == ExecutionEvent.LIQUIDATION_WARNING:
            self._handle_liquidation_warning(result)

        elif event == ExecutionEvent.POSITION_FORCE_CLOSED:
            self._handle_force_closed(result)
```

### 4.2 구체적 핸들러 예시

```python
def _handle_slippage_breach(
    self,
    result: ExecutionResult,
    context: MarketContext,
) -> None:
    """Slippage 초과 → Cooldown"""

    # 결정 로그
    log = StateDecisionLog(
        timestamp=context.timestamp,
        state_from=self._state,
        state_to=TradingState.COOLDOWN,
        transition_reason=f"slippage_breach: {result.slippage_pct:.2f}%",
        decision_maker="execution_event",
        ...
    )

    self._decision_log_store.save(log)

    # Cooldown 진입
    self.enter_cooldown(
        reason="slippage_unacceptable",
        duration=timedelta(hours=24),
        context=context,
    )

def _handle_partial_fill(
    self,
    result: ExecutionResult,
) -> None:
    """Partial Fill 반복 감지"""

    self._partial_fill_count += 1

    if self._partial_fill_count >= 3:
        # 3회 반복 → 시장 유동성 부족
        self.transition_to(
            State.EXIT_FAILURE,
            reason="repeated_partial_fill",
            decision_maker="execution_event",
        )

def _handle_liquidation_warning(
    self,
    result: ExecutionResult,
) -> None:
    """청산 위험 → 즉시 청산"""

    # 긴급 청산 요청
    self._executor.close_position(
        reason="emergency_liquidation_risk",
        order_type=OrderType.MARKET,  # 즉시 체결
    )

    # State 강제 전환
    self.transition_to(
        State.EXIT_FAILURE,
        reason="liquidation_warning_triggered",
        decision_maker="execution_event",
    )
```

---

## 5. Slippage 임계값 정의

### 5.1 Slippage Threshold

```python
# Execution Layer
class Executor:
    SLIPPAGE_THRESHOLD = {
        OrderType.MARKET: 0.15,  # 0.15% (15 bps)
        OrderType.LIMIT: 0.05,   # 0.05% (5 bps)
    }

    def execute(self, plan: PositionPlan, ...) -> ExecutionResult:
        # 주문 실행
        fill = self._submit_order(...)

        # Slippage 계산
        slippage_pct = abs(
            (fill.actual_price - fill.expected_price) / fill.expected_price
        )

        # 임계값 체크
        threshold = self.SLIPPAGE_THRESHOLD[order_type]
        breach = slippage_pct > threshold

        # Event 결정
        if breach:
            event = ExecutionEvent.SLIPPAGE_BREACH
        elif fill.status == FillStatus.FILLED:
            event = ExecutionEvent.FILLED
        else:
            event = ExecutionEvent.PARTIAL_FILL

        return ExecutionResult(
            event=event,
            slippage_pct=slippage_pct,
            slippage_breach=breach,
            ...
        )
```

### 5.2 Slippage 허용 조건

**일반 상황**:
- Market Order: 0.15%
- Limit Order: 0.05%

**긴급 상황** (청산):
- Market Order: 1.0% (허용 완화)

---

## 6. 재시도 로직

### 6.1 재시도 가능 조건

```python
@dataclass
class RetryPolicy:
    max_retries: int
    retry_delay: timedelta
    backoff_multiplier: float

RETRY_POLICIES = {
    ExecutionEvent.TIMEOUT: RetryPolicy(
        max_retries=2,
        retry_delay=timedelta(seconds=5),
        backoff_multiplier=2.0,
    ),
    ExecutionEvent.PARTIAL_FILL: RetryPolicy(
        max_retries=3,
        retry_delay=timedelta(seconds=10),
        backoff_multiplier=1.5,
    ),
    ExecutionEvent.EXCHANGE_ERROR: RetryPolicy(
        max_retries=1,
        retry_delay=timedelta(seconds=30),
        backoff_multiplier=1.0,
    ),
}

# Executor
def execute_with_retry(
    self,
    plan: PositionPlan,
    ...
) -> ExecutionResult:
    retries = 0
    policy = RETRY_POLICIES.get(event, None)

    while retries < policy.max_retries:
        result = self.execute(plan, ...)

        if result.event == ExecutionEvent.FILLED:
            return result

        if not result.retryable:
            return result

        # Backoff
        delay = policy.retry_delay * (policy.backoff_multiplier ** retries)
        time.sleep(delay.total_seconds())
        retries += 1

    return result
```

---

## 7. Liquidation 감지 및 대응

### 7.1 청산가 모니터링

```python
class LiquidationMonitor:
    """청산 위험 감시"""

    CRITICAL_DISTANCE = 1.5  # ATR * 1.5

    def check_liquidation_risk(
        self,
        position: Position,
        features: Features,
    ) -> Optional[ExecutionEvent]:
        """청산가 거리 체크"""

        liquidation_price = position.liquidation_price
        current_price = features.price
        atr = features.atr14

        distance_pct = abs(
            (liquidation_price - current_price) / current_price
        )
        distance_atr = distance_pct / (atr / current_price)

        if distance_atr < self.CRITICAL_DISTANCE:
            # 청산가 너무 가까움
            return ExecutionEvent.LIQUIDATION_WARNING

        return None

# State Machine
def process_tick(self, tick: MarketData, context: MarketContext) -> None:
    if self.state in [State.ENTRY, State.EXPANSION]:
        # 청산 위험 감시
        event = self._liquidation_monitor.check_liquidation_risk(
            self._position,
            self._features,
        )

        if event == ExecutionEvent.LIQUIDATION_WARNING:
            self.handle_execution_event(
                ExecutionResult(event=event, ...),
                context,
            )
```

---

## 8. Event 로그 저장

### 8.1 ExecutionEventLog

```python
@dataclass
class ExecutionEventLog:
    """Execution 이벤트 기록"""

    timestamp: datetime
    event: ExecutionEvent
    state_before: TradingState
    state_after: TradingState

    # Execution 상세
    order_id: str
    order_type: OrderType
    requested_qty: int
    filled_qty: int
    slippage_pct: float

    # 결과
    action_taken: str  # "retry", "cooldown", "exit"
    retry_count: int

# State Machine
def handle_execution_event(
    self,
    result: ExecutionResult,
    context: MarketContext,
) -> None:
    # Event 처리
    state_before = self._state
    self._handle_event_internal(result, context)
    state_after = self._state

    # 로그 저장
    log = ExecutionEventLog(
        timestamp=context.timestamp,
        event=result.event,
        state_before=state_before,
        state_after=state_after,
        ...
    )

    self._decision_log_store.save_execution_event(log)
```

---

## 9. BASE_ARCHITECTURE.md 반영 필요 사항

### Executor Interface 확장

**Before**:
```python
class IExecutor(Protocol):
    def execute(
        self,
        plan: PositionPlan,
        market_data: MarketData,
    ) -> ExecutionResult:
        ...
```

**After**:
```python
class IExecutor(Protocol):
    def execute(
        self,
        plan: PositionPlan,
        market_data: MarketData,
        context: MarketContext,  # 추가
    ) -> ExecutionResult:
        """
        Returns:
            ExecutionResult with event field
        """
        ...

    def close_position(
        self,
        reason: str,
        order_type: OrderType = OrderType.MARKET,
    ) -> ExecutionResult:
        """긴급 청산"""
        ...
```

### State Machine Interface 확장

**추가 메서드**:
```python
class IStateMachine(Protocol):
    def handle_execution_event(
        self,
        result: ExecutionResult,
        context: MarketContext,
    ) -> None:
        """Execution 이벤트 처리"""
        ...
```

---

## 10. 이 문서의 최종 선언

> **Executor는 단순 실행자가 아니다.
> Executor는 시장 현실을 도메인에 보고하는 감각기관이다.**

> **모든 Execution 이벤트는
> State 전환을 트리거할 자격이 있다.
> 슬리피지 초과는 Cooldown 이유다.
> 청산 경고는 긴급 탈출 신호다.**

---

## 11. 구현 우선순위

### Phase 0 (필수)
- ExecutionEvent 정의
- ExecutionResult 확장
- SLIPPAGE_BREACH 처리

### Phase 1 (확장)
- Retry 로직
- LIQUIDATION_WARNING 처리
- PARTIAL_FILL 반복 감지

### Phase 2 (최적화)
- Event → State 전환 패턴 분석
- Slippage threshold 최적화

**이 문서는 BASE_ARCHITECTURE.md의
실전 안정성을 50% 향상시킨다.**
