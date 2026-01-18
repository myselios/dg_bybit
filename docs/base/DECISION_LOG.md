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

## 9. Decision Outcome (의미 압축)

### 9.1 문제: 로그만으로는 학습 불가

**현재 상태**:
- Tick 단위 기록
- Event 단위 기록

❌ **부족한 것**:
- "이 결정이 계좌 성장에 어떤 의미였는가?"
- Hindsight 기준 regret score

### 9.2 DecisionOutcome (사후 평가)

```python
@dataclass
class DecisionOutcome:
    """결정의 사후 평가"""

    # 연결
    decision_id: str  # StateDecisionLog.id
    decision_type: str  # "ev_full", "expansion", "exit"
    decision_timestamp: datetime

    # Horizon별 평가
    short_term_r: float  # 24시간 후 R
    mid_term_r: float    # 7일 후 R
    long_term_r: float   # 30일 후 R

    # Hindsight 평가
    regret_score: float  # 0.0 ~ 1.0 (높을수록 후회)
    optimal_action: str  # "should_have_expanded", "should_have_exited"

    # 맥락
    market_regime_at_decision: str
    market_regime_after: str

    # 학습 태그
    learning_tag: str  # "good_denial", "missed_opportunity", "lucky_pass"
```

### 9.3 Regret Score 계산

```python
def calculate_regret_score(
    decision: EVFullResult,
    actual_outcome: float,
    optimal_outcome: float,
) -> float:
    """사후적 후회 점수 계산"""

    if decision.passed and actual_outcome < 0:
        # EV 통과했지만 손실
        regret = abs(actual_outcome) / decision.expected_r
        return min(regret, 1.0)

    elif not decision.passed and optimal_outcome > decision.expected_r:
        # EV 차단했지만 실제로는 큰 기회
        regret = (optimal_outcome - decision.expected_r) / optimal_outcome
        return min(regret, 1.0)

    else:
        # 좋은 결정
        return 0.0
```

### 9.4 학습 태그 분류

| Tag | 의미 | 액션 |
|-----|------|------|
| good_denial | EV 차단 정확 | 기준 유지 |
| missed_opportunity | EV 차단했지만 기회 | 임계값 완화 검토 |
| lucky_pass | EV 통과했지만 손실 | 임계값 강화 검토 |
| good_pass | EV 통과하고 수익 | 기준 유지 |

### 9.5 Outcome 기반 EV 조정

```python
class EVThresholdAdjuster:
    """Outcome 기반 EV 임계값 동적 조정"""

    def adjust_threshold(
        self,
        recent_outcomes: List[DecisionOutcome],
        current_threshold: float,
    ) -> float:
        """
        최근 100개 결정의 Outcome 기반 조정

        missed_opportunity 많으면 → 임계값 완화
        lucky_pass 많으면 → 임계값 강화
        """

        missed = len([o for o in recent_outcomes if o.learning_tag == "missed_opportunity"])
        lucky = len([o for o in recent_outcomes if o.learning_tag == "lucky_pass"])

        if missed > 30:
            # 기회 놓침 과다 → 완화
            return current_threshold * 0.95

        elif lucky > 30:
            # 손실 과다 → 강화
            return current_threshold * 1.05

        return current_threshold
```

---

## 10. 구현 우선순위 (수정)

### Phase 0 (필수)
- StateDecisionLog
- EVDecisionLog
- DecisionLogStore

### Phase 1 (확장)
- RiskDecisionLog
- ExpansionDecisionLog
- **DecisionOutcome** (신규 추가)

### Phase 2 (학습)
- DecisionLogQuery
- **EVThresholdAdjuster** (신규 추가)
- 로그 기반 전략 개선

**이 문서는 BASE_ARCHITECTURE.md의
생존 능력을 30% → 학습 능력을 50% 향상시킨다.**
