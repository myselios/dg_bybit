# DECISION_LOG.md — 결정 기록 시스템

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 필수 보완 문서**다.

> **State Machine은 단순 FSM이 아니라
> Account Growth Ledger다.**

구조 결정 권한: BASE_ARCHITECTURE.md
결정 기록 정의 권한: 이 문서

---

## 1. 왜 결정을 기록하는가

### 문제 상황

State Machine이 흐름만 제어하고 "왜"를 기록하지 않으면:

- 전략 개선 불가
- 백테스트 분석 불가
- AI/휴먼 디버깅 불가
- EV Full FAIL 이유 모름
- Risk가 cooldown 건 근거 모름

### Account Builder의 특수성

일반 시스템: 로그는 디버깅용
Account Builder: **로그는 학습 데이터**

> **한 번의 +300% 트레이드를 만들기 위해
> 수십 번의 실패가 필요하다.
> 그 실패의 '이유'가 없으면
> 다음은 더 나빠진다.**

---

## 2. 결정 로그의 구조

### 2.1 StateDecisionLog (상태 전환 로그)

```python
@dataclass
class StateDecisionLog:
    """모든 상태 전환 기록"""

    # 기본 정보
    timestamp: datetime
    state_from: TradingState
    state_to: TradingState
    transition_reason: str

    # Metrics Snapshot (상태 전환 시점)
    account_balance: float
    unrealized_pnl: float
    drawdown_pct: float
    consecutive_losses: int

    # 결정 근거
    decision_maker: str  # "state_machine", "risk", "ev_full"
    rejection_reason: Optional[str]  # FAIL 시

    # Context
    market_context: MarketContext
    active_position: Optional[PositionSnapshot]
```

### 2.2 EVDecisionLog (EV 검증 로그)

```python
@dataclass
class EVDecisionLog:
    """EV Pre-filter / Full Validator 결정 기록"""

    timestamp: datetime
    stage: str  # "pre_filter" / "full_validator"

    # 입력
    trade_intent: TradeIntent
    account_balance: float

    # Pre-filter
    prefilter_passed: bool
    prefilter_reason: Optional[str]

    # Full Validator (통과한 경우만)
    full_validation_passed: Optional[bool]
    expected_r: Optional[float]  # +300% 기준
    win_probability: Optional[float]
    ev_value: Optional[float]
    tail_profit_avg: Optional[float]

    # Simulation 상세
    simulation_outcomes: Optional[List[SimulationResult]]

    # 실패 이유 (상세)
    failure_code: Optional[str]  # "R_INSUFFICIENT", "TAIL_WEAK"
    failure_details: Optional[str]
```

### 2.3 RiskDecisionLog (Risk 판단 로그)

```python
@dataclass
class RiskDecisionLog:
    """Risk Manager 결정 기록"""

    timestamp: datetime

    # 입력
    trade_intent: TradeIntent
    current_state: TradingState

    # 계좌 상태
    balance: float
    drawdown_pct: float
    consecutive_losses: int
    trades_today: int

    # 결정
    allowed: bool
    max_exposure: float
    max_leverage: float
    emergency_flag: bool
    cooldown_trigger: bool

    # 근거
    denial_reason: Optional[str]
    risk_tier: int  # 1~4
    dynamic_risk_multiplier: float
```

### 2.4 ExpansionDecisionLog (Expansion 판단 로그)

```python
@dataclass
class ExpansionDecisionLog:
    """Expansion 허가/차단 기록"""

    timestamp: datetime

    # Position 상태
    entry_price: float
    current_price: float
    unrealized_pnl_pct: float
    current_size: int

    # Expansion 요청
    layer: int  # 2, 3
    trigger_pnl_pct: float  # +8%, +15%

    # 재검증
    ev_revalidation_passed: bool
    risk_revalidation_passed: bool
    structure_intact: bool

    # 결정
    expansion_allowed: bool
    expansion_size: Optional[int]

    # 실패 이유
    denial_reason: Optional[str]
```

---

## 3. 기록 시점 및 책임

### 3.1 State Machine

**기록 시점**:
- 모든 상태 전환 시

**기록 내용**:
```python
def transition_to(
    self,
    next_state: TradingState,
    reason: str,
    decision_maker: str,
) -> None:
    log = StateDecisionLog(
        timestamp=datetime.now(),
        state_from=self._state,
        state_to=next_state,
        transition_reason=reason,
        account_balance=self._account.balance,
        drawdown_pct=self._account.drawdown_pct,
        consecutive_losses=self._account.consecutive_losses,
        decision_maker=decision_maker,
        market_context=self._current_context,
        active_position=self._position_snapshot(),
    )

    self._decision_log_store.save(log)
    self._state = next_state
```

### 3.2 EV Pre-filter / Full Validator

**기록 시점**:
- Pre-filter 호출 시 (PASS/FAIL 모두)
- Full Validator 호출 시 (PASS/FAIL 모두)

**기록 내용**:
```python
def validate(self, intent: TradeIntent, ...) -> EVFullResult:
    # ... 계산 ...

    log = EVDecisionLog(
        timestamp=datetime.now(),
        stage="full_validator",
        trade_intent=intent,
        full_validation_passed=passed,
        expected_r=R_win,
        ev_value=ev,
        failure_code="R_INSUFFICIENT" if not passed else None,
        simulation_outcomes=outcomes,
    )

    self._decision_log_store.save(log)
    return result
```

### 3.3 Risk Manager

**기록 시점**:
- 모든 리스크 판단 시 (ALLOW/DENY 모두)

### 3.4 Position Sizer (Expansion)

**기록 시점**:
- Expansion 요청 시 (허가/차단 모두)

---

## 4. 로그 저장 및 조회

### 4.1 저장 방식

```python
class DecisionLogStore:
    """결정 로그 영구 저장"""

    def save_state_log(self, log: StateDecisionLog) -> None:
        # SQLite / JSON / CSV
        ...

    def save_ev_log(self, log: EVDecisionLog) -> None:
        ...

    def save_risk_log(self, log: RiskDecisionLog) -> None:
        ...

    def save_expansion_log(self, log: ExpansionDecisionLog) -> None:
        ...
```

**저장 위치**:
- `logs/decisions/state_transitions.jsonl`
- `logs/decisions/ev_validations.jsonl`
- `logs/decisions/risk_decisions.jsonl`
- `logs/decisions/expansion_decisions.jsonl`

### 4.2 조회 인터페이스

```python
class DecisionLogQuery:
    """로그 분석용 쿼리"""

    def get_ev_failures_by_reason(
        self,
        start: datetime,
        end: datetime,
    ) -> Dict[str, int]:
        """EV 실패 이유별 카운트"""
        ...

    def get_risk_denial_patterns(self) -> List[RiskDecisionLog]:
        """Risk 거부 패턴 분석"""
        ...

    def get_expansion_success_rate(self) -> float:
        """Expansion 허가율"""
        ...

    def get_state_duration_stats(self) -> Dict[TradingState, timedelta]:
        """State별 평균 체류 시간"""
        ...
```

---

## 5. 로그 기반 분석 예시

### 5.1 EV Full Validator 실패 분석

```python
# 최근 100개 트레이드에서 EV Full 실패 이유
failures = log_query.get_ev_failures_by_reason(
    start=datetime.now() - timedelta(days=30),
    end=datetime.now(),
)

# 결과
{
    "R_INSUFFICIENT": 45,  # +300% 미달
    "WIN_PROB_LOW": 23,     # 승률 < 10%
    "TAIL_WEAK": 18,        # 꼬리 수익 부족
    "NEGATIVE_EV": 14,      # EV < 0
}

# 액션
if failures["R_INSUFFICIENT"] > 40:
    # 전략 파라미터 조정 필요
    # 또는 시장 환경 변화 인지
```

### 5.2 Cooldown 진입 원인 분석

```python
cooldowns = log_query.get_state_transitions(
    state_to=TradingState.COOLDOWN,
    last_n=10,
)

# 원인별 분류
for log in cooldowns:
    print(f"{log.transition_reason}: DD={log.drawdown_pct:.1f}%")

# 출력
# "consecutive_3_losses": DD=-28.5%
# "consecutive_3_losses": DD=-31.2%
# "single_loss_exceeds_20pct": DD=-22.1%
```

---

## 6. 백테스트 vs 실거래 로그 차이

### Backtest

- 로그는 메모리 저장 (빠른 분석)
- 결정 로그만 (실행 로그 제외)

### Live

- 로그는 영구 저장 (SQLite/JSON)
- 결정 + 실행 + 거래소 응답 모두 저장

---

## 7. BASE_ARCHITECTURE.md 반영 필요 사항

### State Machine 수정

**추가 필요**:
```python
class TradingStateMachine:
    def __init__(
        self,
        ...,
        decision_log_store: DecisionLogStore,  # 추가
    ):
        ...

    def transition_to(
        self,
        next_state: TradingState,
        reason: str,
        decision_maker: str,  # 추가
    ) -> None:
        # 로그 저장
        self._log_transition(...)
        self._state = next_state
```

---

## 8. 이 문서의 최종 선언

> **State Machine은 단순 FSM이 아니다.
> State Machine은 Account Growth Ledger다.**

> **모든 결정은 기록되어야 한다.
> 기록되지 않은 실패는
> 다음 성공의 기회를 죽인다.**

---

## 9. 구현 우선순위

### Phase 0 (필수)
- StateDecisionLog
- EVDecisionLog
- DecisionLogStore

### Phase 1 (확장)
- RiskDecisionLog
- ExpansionDecisionLog

### Phase 2 (분석)
- DecisionLogQuery
- 로그 기반 전략 개선

**이 문서는 BASE_ARCHITECTURE.md의
생존 능력을 30% 향상시킨다.**
