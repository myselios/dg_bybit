# INTERFACES.md — Account Builder Edition (v2)

## 0. 이 문서의 목적

이 문서는 구현 가이드가 아니다.

> **이 문서는
각 컴포넌트가
'무엇을 알고, 무엇을 모르며,
어디까지 결정할 수 있는지'를
강제하는 계약서다.**

Account Builder 시스템에서
인터페이스 붕괴 = 리스크 붕괴다.

### v2 변경사항

v1 대비 추가/변경:
1. **Trading Engine** 추가 (Backtest/Live 추상화)
2. **Feature Engine** 추가 (지표 계산 분리)
3. **EV Framework** 분리 (Pre-filter + Full Validator)
4. **State Machine** 역할 재정의 (도메인 중심)

---

## 1. 전체 시스템 구성요소 (v2)

이 시스템은 다음 **9개 핵심 컴포넌트**로 구성된다.

| # | 컴포넌트 | 계층 | 역할 |
|---|----------|------|------|
| 1 | Trading Engine | Infrastructure | Market Data 공급 추상화 |
| 2 | State Machine | Domain Core | 흐름 제어 중심 |
| 3 | Feature Engine | Domain | 지표 계산 |
| 4 | Strategy | Domain | 진입 조건 판단 |
| 5 | EV Pre-filter | Application | 빠른 Gate |
| 6 | EV Full Validator | Application | 최종 EV 검증 |
| 7 | Risk Manager | Application | 노출 허가 |
| 8 | Position Sizer | Application | 사이징 |
| 9 | Executor | Infrastructure | 주문 실행 |

> ⚠️ 중요
> **어느 컴포넌트도
> 다른 컴포넌트의 책임을 침범할 수 없다.**

---

## 2. Trading Engine Interface (신규)

### 2.1 Trading Engine의 역할

Trading Engine은 **Backtest와 Live의 공통 추상화**다.

- Market Data 공급 방식 캡슐화
- State Machine 호출
- 타이밍 제어

❌ 금지:
- 전략 로직 포함
- 리스크 판단
- State 직접 변경

---

### 2.2 Trading Engine Interface

```python
class ITradingEngine(Protocol):
    """Backtest/Live 공통 인터페이스"""

    def run(self) -> None:
        """메인 루프 실행"""

    def stop(self) -> None:
        """시스템 종료"""

    @property
    def state_machine(self) -> IStateMachine:
        """State Machine 참조"""
```

### 2.3 구현체

#### BacktestEngine
```python
class BacktestEngine(ITradingEngine):
    def __init__(
        self,
        historical_data: pd.DataFrame,
        state_machine: IStateMachine,
    ):
        self._data = historical_data
        self._state_machine = state_machine

    def run(self) -> None:
        for tick in self._data.itertuples():
            market_data = self._convert_to_market_data(tick)
            self._state_machine.process_tick(market_data)
```

#### LiveEngine
```python
class LiveEngine(ITradingEngine):
    def __init__(
        self,
        ws_client: BybitWebSocket,
        state_machine: IStateMachine,
    ):
        self._ws = ws_client
        self._state_machine = state_machine

    def run(self) -> None:
        while self._running:
            tick = self._ws.receive()
            market_data = self._convert_to_market_data(tick)
            self._state_machine.process_tick(market_data)
```

---

## 3. State Machine Interface (재정의)

### 3.1 State Machine의 지위 (v2)

State Machine은 **도메인 중심**이다.

> **State Machine이
> 각 레이어에게
> "지금 무엇을 할 수 있는가"를 알려준다.**

v1과의 차이:
- v1: Execution 다음 (결과를 받아 다음 상태 결정)
- v2: **모든 레이어 위** (각 레이어의 행동 허가 제어)

---

### 3.2 State Machine Interface

```python
class IStateMachine(Protocol):
    """상태 흐름 제어 중심"""

    def process_tick(self, tick: MarketData) -> None:
        """
        Market Tick 수신 시 호출
        현재 상태에 따라 적절한 레이어 호출
        """

    @property
    def current_state(self) -> TradingState:
        """현재 상태"""

    def can_execute_action(self, action: Action) -> bool:
        """이 상태에서 해당 액션 실행 가능한가?"""

    def transition_to(
        self,
        next_state: TradingState,
        reason: str,
    ) -> None:
        """상태 전환 (내부 로직만 호출 가능)"""
```

### 3.3 State Machine Output

```python
@dataclass
class StateMachineContext:
    current_state: TradingState
    allowed_actions: Set[Action]
    state_metadata: Dict[str, Any]

class TradingState(Enum):
    INIT = "INIT"
    IDLE = "IDLE"
    MONITORING = "MONITORING"
    ENTRY = "ENTRY"
    EXPANSION = "EXPANSION"
    EXIT_SUCCESS = "EXIT_SUCCESS"
    EXIT_FAILURE = "EXIT_FAILURE"
    COOLDOWN = "COOLDOWN"
    TERMINATED = "TERMINATED"

class Action(Enum):
    OBSERVE_MARKET = "observe_market"
    CHECK_ENTRY = "check_entry"
    OPEN_POSITION = "open_position"
    EXPAND_POSITION = "expand_position"
    CLOSE_POSITION = "close_position"
    WAIT = "wait"
```

### 3.4 State Machine의 책임

- **흐름 제어**: IDLE → MONITORING → ENTRY → EXPANSION → EXIT
- **행동 허가**: "지금 Strategy 호출 가능한가?"
- **상태 전환**: 조건 충족 시 다음 상태로 이동
- **실패 관리**: 연속 실패 시 COOLDOWN 강제

❌ 금지:
- 가격 계산
- EV 판단
- 포지션 사이즈 결정
- 주문 실행

---

## 4. Feature Engine Interface (신규)

### 4.1 Feature Engine의 역할

Feature Engine은 **기술적 지표 계산 전담**이다.

- EMA, ATR 등 계산
- Strategy는 계산된 지표만 사용
- SRP 준수 (계산 vs 판단 분리)

❌ 금지:
- 진입 조건 판단
- Signal 생성
- EV 계산

---

### 4.2 Feature Engine Interface

```python
class IFeatureEngine(Protocol):
    """기술적 지표 계산"""

    def update(self, tick: MarketData) -> Features:
        """
        새 Tick으로 지표 업데이트
        Returns: 계산된 Features
        """

    def get_current_features(self) -> Features:
        """현재 지표 값"""
```

### 4.3 Feature Engine Output

```python
@dataclass
class Features:
    """STRATEGY.md 요구사항 반영"""
    timestamp: datetime
    price: float

    # Directional Filter
    ema200_4h: float
    price_above_ema: bool

    # Volatility Expansion
    atr14: float
    atr_ema50: float
    atr_expanding: bool  # ATR > EMA(ATR, 50) * 1.2

    # Entry Threshold
    entry_threshold: float  # EMA200 + ATR * 0.3

    # 추가 지표 (필요 시)
    volume: Optional[float] = None
    funding_rate: Optional[float] = None
```

---

## 5. Strategy Interface (수정)

### 5.1 Strategy의 역할

Strategy는 **"언제 베팅할 가치가 있는가"**만 판단한다.

v2 변경:
- 입력에 **Features** 추가 (지표 계산 분리)
- 지표 계산 책임 제거

❌ 금지:
- **지표 계산** (Feature Engine이 담당)
- 포지션 크기 결정
- 손절/익절 가격 결정
- 실행 방식 결정

---

### 5.2 Strategy Interface

```python
class IStrategy(Protocol):
    """진입 조건 판단"""

    def check_entry(
        self,
        features: Features,
        state: TradingState,
    ) -> TradeIntent:
        """
        진입 조건 충족 여부 판단
        Args:
            features: Feature Engine에서 계산된 지표
            state: 현재 상태
        Returns:
            Trade Intent
        """
```

### 5.3 Strategy Output

```python
@dataclass
class TradeIntent:
    direction: Direction  # LONG / SHORT
    entry_valid: bool  # 진입 조건 충족 여부
    confidence: float  # 0.0 ~ 1.0
    context: str  # "volatility_expansion", "regime_shift"
    metadata: Dict[str, Any]  # 추가 정보

class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
```

> Strategy는
> **'이게 좋은 기회다'까지만 말한다.
> '얼마를 걸지'는 말하지 않는다.**

---

## 6. EV Framework Interface (2단계 분리)

### 6.1 EV Framework의 지위

EV Framework는 **2단계 검증 구조**다.

1. **Pre-filter**: Strategy 직후 (빠른 체크)
2. **Full Validator**: Risk 통과 후 (무거운 검증)

> **Pre-filter가 FAIL → 즉시 종료
> Full Validator가 FAIL → Position 계산 안 함**

---

### 6.2 EV Pre-filter Interface

```python
class IEVPrefilter(Protocol):
    """빠른 조건 체크 (Gate)"""

    def validate(
        self,
        intent: TradeIntent,
        account: AccountState,
    ) -> EVPrefilterResult:
        """
        가벼운 체크만 수행
        - 잔고 충분한가?
        - Confidence 임계값 이상인가?
        - 진입 조건 충족했는가?

        무거운 EV 계산은 하지 않음
        """
```

### 6.3 EV Pre-filter Output

```python
@dataclass
class EVPrefilterResult:
    passed: bool
    reason: str  # FAIL 시 이유

    # 예시
    # "insufficient_balance"
    # "low_confidence"
    # "entry_invalid"
```

---

### 6.4 EV Full Validator Interface

```python
class IEVFullValidator(Protocol):
    """최종 EV 검증 (무거운 계산)"""

    def validate(
        self,
        intent: TradeIntent,
        risk_permission: RiskPermission,
        account: AccountMetrics,
    ) -> EVFullResult:
        """
        EV_FRAMEWORK.md 기준 완전 검증
        - P_win ≥ 10~15%
        - R_win ≥ +300%
        - R_loss ≤ -25%
        - 시뮬레이션 기반 EV 계산
        """
```

### 6.5 EV Full Validator Output

```python
@dataclass
class EVFullResult:
    passed: bool
    expected_r: float  # +300% 이상 필수
    win_probability: float  # 0.1 ~ 0.15 목표
    ev_value: float  # (P_win * R_win) - (P_loss * R_loss)
    reason: str  # FAIL 시 이유

    # Simulation 상세
    simulated_outcomes: Optional[List[SimulationResult]] = None
```

❌ 금지:
- 진입 타이밍 결정
- 포지션 사이즈 결정
- 리스크 한도 설정

---

## 7. Risk Manager Interface (수정 없음)

### 7.1 Risk Manager의 지위

Risk Manager는 **최상위 권한**을 가진다.

> **Risk는 언제든
> Strategy의 결정을 무효화할 수 있다.**

---

### 7.2 Risk Manager Interface

```python
class IRiskManager(Protocol):
    """리스크 허가 판단"""

    def check_permission(
        self,
        intent: TradeIntent,
        account: AccountMetrics,
        state: TradingState,
    ) -> RiskPermission:
        """
        노출 허용 여부 판단
        - 최대 노출 한도 확인
        - 연속 실패 카운트 확인
        - Drawdown 한도 확인
        - 청산가 여유 확인
        """
```

### 7.3 Risk Manager Output

```python
@dataclass
class RiskPermission:
    allowed: bool
    max_exposure: float  # USD 단위
    max_leverage: float
    emergency_flag: bool  # 구조적 위험 감지
    cooldown_trigger: bool  # 쿨다운 필요 여부
    reason: str  # DENY 시 이유

@dataclass
class AccountMetrics:
    balance: float
    unrealized_pnl: float
    drawdown_pct: float
    consecutive_losses: int
    trades_today: int
```

❌ 금지:
- 진입 타이밍 결정
- 포지션 확대 시점 결정
- EV 재판단

---

## 8. Position Sizer Interface (수정 없음)

### 8.1 Position Sizer의 정체성

Position Sizer는 **Account Builder의 심장**이다.

> 이 컴포넌트가 없다면
> 시스템은 도박과 다를 바 없다.

---

### 8.2 Position Sizer Interface

```python
class IPositionSizer(Protocol):
    """포지션 사이징"""

    def calculate(
        self,
        intent: TradeIntent,
        risk_permission: RiskPermission,
        ev_result: EVFullResult,
    ) -> PositionPlan:
        """
        초기 진입 + Expansion 계획
        - 초기 사이즈: 작게 시작
        - Expansion: 수익 구간에서만
        - 비대칭 구조: +300% 목표
        """
```

### 8.3 Position Sizer Output

```python
@dataclass
class PositionPlan:
    entry_size: int  # contracts
    expansion_layers: List[ExpansionLayer]
    stop_threshold: float
    target_r: float  # Expected R-multiple

@dataclass
class ExpansionLayer:
    trigger_pnl_pct: float  # +8%, +15%, +25%
    add_size: int  # contracts
    condition: str  # "price_above_ema", "atr_expanding"
```

❌ 금지:
- 시장 방향 재해석
- 실행 방식 선택
- 리스크 재판단

---

## 9. Executor Interface (수정 없음)

### 9.1 Executor의 역할

Executor는 **판단을 실행으로 바꾸는 기술 계층**이다.

> Executor는
> 판단을 바꾸지 않는다.
> **판단을 망치지 않을 책임만 진다.**

---

### 9.2 Executor Interface

```python
class IExecutor(Protocol):
    """주문 실행"""

    def execute(
        self,
        plan: PositionPlan,
        market_data: MarketData,
    ) -> ExecutionResult:
        """
        주문 타입 결정 (Limit/Market)
        체결 관리
        슬리피지 통제
        """

    def close_position(
        self,
        reason: str,
    ) -> ExecutionResult:
        """포지션 청산"""
```

### 9.3 Executor Output

```python
@dataclass
class ExecutionResult:
    status: ExecutionStatus
    fill_price: float
    filled_qty: int
    slippage: float  # 예상가 대비 슬리피지
    error: Optional[str]

class ExecutionStatus(Enum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    PENDING = "PENDING"
```

❌ 금지:
- 전략 수정
- 리스크 완화/강화 판단
- State 직접 변경

---

## 10. 컴포넌트 간 의사결정 흐름 (v2)

```text
Trading Engine
   ↓ (Market Data 공급)
State Machine (도메인 중심)
   ↓ (현재 상태에 따라 레이어 호출 허가)
Feature Engine (지표 계산)
   ↓
Strategy (진입 조건 판단)
   ↓
EV Pre-filter (빠른 Gate)
   ↓ (PASS만 진행)
Risk Manager (노출 허가)
   ↓ (ALLOW만 진행)
EV Full Validator (최종 검증: +300% 확인)
   ↓ (PASS만 진행)
Position Sizer (사이징)
   ↓
Executor (주문 실행)
   ↓ (결과 전달)
State Machine (상태 전환)
```

> **이 순서는 절대 바뀌지 않는다.**
> **EV Pre-filter 또는 Full Validator가 FAIL이면
> 다음 단계는 실행되지 않는다.**

---

## 11. 인터페이스 위반은 실패다 (v2)

다음은 시스템 실패로 간주한다:

### 계층 위반
- Strategy가 지표 계산 ❌ (Feature Engine이 담당)
- Strategy가 사이즈 결정 ❌
- Position Sizer가 방향 바꿈 ❌
- Executor가 리스크 판단 ❌

### EV 우회
- **EV Pre-filter 통과 없이 Risk 호출** ❌
- **EV Full Validator 통과 없이 Position 계산** ❌
- EV 판단이 Entry 이후 수행 ❌

### State Machine 우회
- State 확인 없이 Strategy 호출 ❌
- COOLDOWN 상태에서 진입 시도 ❌
- Executor가 State 직접 변경 ❌

### Backtest/Live 불일치
- Live에만 있는 로직 ❌
- Backtest에만 있는 로직 ❌
- Trading Engine 우회 Market Data 수신 ❌

돈을 벌어도
이 위반이 발생하면
그 트레이드는 실패다.

---

## 12. v1 대비 변경 요약

| 컴포넌트 | v1 | v2 | 이유 |
|----------|----|----|------|
| Trading Engine | 없음 | 추가 | Backtest/Live 분리 |
| State Machine | 최하위 | 도메인 중심 | 클린 아키텍처 준수 |
| Feature Engine | 없음 | 추가 | SRP 준수 (계산 vs 판단) |
| EV Framework | 1단계 | 2단계 (Pre + Full) | 성능 최적화 |
| Strategy | 지표 계산 포함? | Features 입력 | 책임 분리 |

---

## 13. 이 문서의 최종 선언

이 시스템은
똑똑한 알고리즘으로 돈을 벌려 하지 않는다.

역할이 명확한 구조로
큰 실수를 하지 않으려 한다.

Account Builder에서
구조는 곧 생존이고,
생존은 다음 기회를 만든다.

**v2 추가:**
그리고 그 구조를
백테스트와 실거래에서 동일하게 유지하며,
성능 저하 없이 운영한다.
