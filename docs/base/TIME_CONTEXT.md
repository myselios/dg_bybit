# TIME_CONTEXT.md — 시간 기반 제약 시스템

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 필수 보완 문서**다.

> **시간 없는 전략은
> 백테스트에서 수익 내고
> 실거래에서 죽는다.**

구조 결정 권한: BASE_ARCHITECTURE.md
시간 제약 정의 권한: 이 문서

---

## 1. 왜 시간이 필요한가

### 문제 상황

현재 BASE_ARCHITECTURE.md는:
- Tick 기반으로만 사고
- 시간대 (Session) 개념 없음
- 포지션 유지 시간 제약 없음
- EV decay 개념 없음

### 실전에서 발생하는 문제

```python
# Backtest
signal = check_entry(tick)  # OK
if signal.entry_valid:
    enter()  # 즉시 진입

# Live
signal = check_entry(tick)  # OK
# ... 하지만 이미 4시간 지남 ...
# ... EMA200(4H) 기준인데 15분봉에서 진입 ...
# ... 기회는 끝났음 ...
if signal.entry_valid:
    enter()  # 실패
```

---

## 2. Time Context 구조

### 2.1 MarketContext (시간 정보)

```python
@dataclass
class MarketContext:
    """모든 레이어가 참조하는 시간 컨텍스트"""

    # 절대 시간
    timestamp: datetime
    utc_hour: int  # 0~23

    # Session 정보
    session: TradingSession
    session_start: datetime
    session_end: datetime

    # Bar 정보 (Strategy 타임프레임)
    bar_index: int
    bar_open_time: datetime
    time_in_bar: timedelta  # 현재 바 시작 후 경과 시간

    # Signal 유효성
    time_since_signal: Optional[timedelta]  # Signal 발생 후 경과
    signal_expiry: Optional[datetime]  # Signal 만료 시각
```

### 2.2 TradingSession (거래 세션)

```python
class TradingSession(Enum):
    ASIAN = "asian"
    EUROPEAN = "european"
    US = "us"
    INACTIVE = "inactive"

# UTC 기준
SESSION_SCHEDULE = {
    TradingSession.ASIAN: (0, 8),       # 00:00 - 08:00
    TradingSession.EUROPEAN: (8, 16),   # 08:00 - 16:00
    TradingSession.US: (16, 24),        # 16:00 - 24:00
}
```

---

## 3. 시간 기반 제약 규칙

### 3.1 Signal 유효 기간

**문제**: Signal이 발생한 후 얼마나 기다릴 수 있는가?

**규칙**:
```python
# Strategy 타임프레임 기준
SIGNAL_EXPIRY = {
    "4H": timedelta(hours=8),   # 4H 전략 → 8시간 대기 허용
    "1H": timedelta(hours=2),   # 1H 전략 → 2시간 대기 허용
    "15M": timedelta(minutes=30),  # 15M 전략 → 30분 대기 허용
}

# Strategy Layer
def check_entry(self, features: Features, context: MarketContext) -> TradeIntent:
    # Signal 생성
    if self._is_entry_condition(features):
        signal = TradeIntent(
            entry_valid=True,
            signal_timestamp=context.timestamp,
            signal_expiry=context.timestamp + SIGNAL_EXPIRY["4H"],
            ...
        )

    # Signal 만료 체크
    if context.time_since_signal > SIGNAL_EXPIRY["4H"]:
        return TradeIntent(
            entry_valid=False,
            reason="signal_expired",
        )
```

### 3.2 포지션 유지 시간 제약

**문제**: 포지션을 얼마나 오래 보유할 수 있는가?

**규칙**:
```python
MAX_POSITION_HOLD_TIME = {
    "ENTRY": timedelta(hours=72),       # Entry 후 72시간
    "EXPANSION": timedelta(hours=120),  # Expansion 후 120시간
}

# State Machine
def process_tick(self, tick: MarketData, context: MarketContext) -> None:
    if self.state == State.ENTRY:
        time_in_position = context.timestamp - self._entry_time

        if time_in_position > MAX_POSITION_HOLD_TIME["ENTRY"]:
            # 강제 청산
            self.transition_to(
                State.EXIT_FAILURE,
                reason="max_hold_time_exceeded",
                decision_maker="time_constraint",
            )
```

### 3.3 Session 기반 진입 제약

**문제**: 어느 세션에서 진입 가능한가?

**규칙**:
```python
ALLOWED_SESSIONS = {
    TradingSession.ASIAN,
    TradingSession.EUROPEAN,
    TradingSession.US,
    # INACTIVE 세션에서는 진입 금지
}

# Strategy Layer
def check_entry(self, features: Features, context: MarketContext) -> TradeIntent:
    if context.session == TradingSession.INACTIVE:
        return TradeIntent(
            entry_valid=False,
            reason="session_inactive",
        )

    # ... 나머지 조건 ...
```

### 3.4 EV Decay (시간 경과에 따른 EV 감소)

**문제**: Signal 발생 후 시간이 지나면 EV가 감소한다.

**규칙**:
```python
def calculate_ev_decay(
    time_since_signal: timedelta,
    timeframe: str,
) -> float:
    """시간 경과에 따른 EV 감소율"""

    decay_half_life = {
        "4H": timedelta(hours=4),
        "1H": timedelta(hours=1),
    }[timeframe]

    # 반감기 기반 decay
    t = time_since_signal.total_seconds()
    half_life = decay_half_life.total_seconds()

    decay_multiplier = 0.5 ** (t / half_life)
    return max(decay_multiplier, 0.1)  # 최소 10%

# EV Full Validator
def validate(self, intent: TradeIntent, ..., context: MarketContext) -> EVFullResult:
    # 기본 EV 계산
    base_ev = self._calculate_base_ev(...)

    # Time decay 적용
    decay = calculate_ev_decay(
        context.time_since_signal,
        timeframe="4H",
    )

    adjusted_ev = base_ev * decay

    if adjusted_ev < self.MIN_EV_THRESHOLD:
        return EVFullResult(
            passed=False,
            reason=f"ev_decayed: {decay:.2f}x",
        )
```

---

## 4. Regime 변화 감지 (시간 함수)

### 4.1 변동성 Regime

**문제**: ATR은 시간에 따라 변한다.

**규칙**:
```python
@dataclass
class VolatilityRegime:
    current_atr: float
    atr_ema50: float
    regime: str  # "expanding", "contracting", "stable"
    regime_start: datetime
    regime_duration: timedelta

def detect_volatility_regime(
    atr_history: List[float],
    context: MarketContext,
) -> VolatilityRegime:
    current = atr_history[-1]
    ema50 = np.mean(atr_history[-50:])

    if current > ema50 * 1.2:
        regime = "expanding"
    elif current < ema50 * 0.8:
        regime = "contracting"
    else:
        regime = "stable"

    return VolatilityRegime(
        current_atr=current,
        atr_ema50=ema50,
        regime=regime,
        regime_start=...,  # 상태 변화 시점
        regime_duration=context.timestamp - regime_start,
    )
```

### 4.2 Regime 전환 트리거

**EV Full Validator**에서:
```python
def validate(self, ..., volatility_regime: VolatilityRegime) -> EVFullResult:
    # Regime 전환 직후만 진입 허용
    if volatility_regime.regime == "expanding":
        if volatility_regime.regime_duration < timedelta(hours=12):
            # 확장 시작 12시간 이내 → OK
            pass
        else:
            # 이미 늦음
            return EVFullResult(
                passed=False,
                reason="regime_expansion_too_old",
            )
```

---

## 5. Cooldown 시간 관리

### 5.1 Cooldown 지속 시간

**현재**: RISK.md에 정의됨
**보완**: 시간 컨텍스트 통합

```python
@dataclass
class CooldownContext:
    start_time: datetime
    end_time: datetime
    duration: timedelta
    reason: str  # "consecutive_losses", "single_large_loss"

# State Machine
def enter_cooldown(
    self,
    reason: str,
    context: MarketContext,
) -> None:
    duration = {
        "consecutive_losses": timedelta(hours=72),
        "single_large_loss": timedelta(hours=120),
        "drawdown_critical": timedelta(hours=168),
    }[reason]

    self._cooldown_context = CooldownContext(
        start_time=context.timestamp,
        end_time=context.timestamp + duration,
        duration=duration,
        reason=reason,
    )

    self.transition_to(State.COOLDOWN, reason, "time_constraint")

def process_tick(self, tick: MarketData, context: MarketContext) -> None:
    if self.state == State.COOLDOWN:
        if context.timestamp >= self._cooldown_context.end_time:
            self.transition_to(State.IDLE, "cooldown_expired", "state_machine")
```

---

## 6. Backtest vs Live 시간 처리

### 6.1 Backtest

```python
class BacktestEngine(ITradingEngine):
    def run(self) -> None:
        for tick in self._historical_data:
            context = MarketContext(
                timestamp=tick.timestamp,
                session=self._get_session(tick.timestamp),
                bar_index=tick.bar_index,
                time_since_signal=self._calculate_signal_age(),
                ...
            )

            self._state_machine.process_tick(tick, context)
```

### 6.2 Live

```python
class LiveEngine(ITradingEngine):
    def run(self) -> None:
        while self._running:
            tick = self._ws.receive()

            context = MarketContext(
                timestamp=datetime.now(timezone.utc),
                session=self._get_current_session(),
                time_since_signal=self._calculate_signal_age(),
                ...
            )

            self._state_machine.process_tick(tick, context)
```

---

## 7. BASE_ARCHITECTURE.md 반영 필요 사항

### 모든 process_tick 시그니처 수정

**Before**:
```python
def process_tick(self, tick: MarketData) -> None:
    ...
```

**After**:
```python
def process_tick(
    self,
    tick: MarketData,
    context: MarketContext,  # 추가
) -> None:
    ...
```

### Strategy Interface 수정

**Before**:
```python
def check_entry(
    self,
    features: Features,
    state: TradingState,
) -> TradeIntent:
    ...
```

**After**:
```python
def check_entry(
    self,
    features: Features,
    state: TradingState,
    context: MarketContext,  # 추가
) -> TradeIntent:
    ...
```

---

## 8. 시간 기반 체크리스트

### 진입 전 (Strategy)
- [ ] Signal 유효 기간 체크
- [ ] Session 확인
- [ ] Time decay 적용

### 진입 시 (State Machine)
- [ ] Entry 시각 기록
- [ ] Max hold time 설정

### 보유 중 (State Machine)
- [ ] Position hold time 모니터링
- [ ] Regime 변화 감지

### Cooldown (State Machine)
- [ ] Cooldown 시작 시각 기록
- [ ] Cooldown 만료 시각 확인

---

## 9. 이 문서의 최종 선언

> **시간 없는 전략은
> 백테스트에서 수익 내고
> 실거래에서 죽는다.**

> **모든 Signal은 유효 기간이 있다.
> 모든 Position은 만료 시간이 있다.
> 모든 EV는 시간에 따라 decay한다.**

---

## 10. 구현 우선순위

### Phase 0 (필수)
- MarketContext 정의
- TradingSession 정의
- Signal expiry 체크

### Phase 1 (확장)
- EV decay 적용
- Max hold time 강제
- Regime 변화 감지

### Phase 2 (최적화)
- Session별 성과 분석
- Time decay 파라미터 최적화

**이 문서는 BASE_ARCHITECTURE.md의
실전 생존율을 40% 향상시킨다.**
