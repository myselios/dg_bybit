# BASE_ARCHITECTURE.md — Account Builder Trading System (v2)

## 0. 이 문서의 지위 (가장 중요)

이 문서는 설계 문서가 아니다.
이 문서는 **코드가 반드시 따라야 하는 구조적 헌법**이다.

> 이 아키텍처를 벗어나는 코드는
> 기능이 맞아도 **버그로 간주**한다.

### v2 변경 이유

v1에서 발견된 **구조적 모순**을 해결한다:
1. State Machine 위치 (클린 아키텍처 위반 해결)
2. Backtest 불가능 구조 (Trading Engine 추상화)
3. EV 성능 문제 (2단계 검증 구조)
4. Indicator 계산 주체 불명확 (Feature Layer 추가)

---

## 1. 아키텍처의 핵심 원칙

### 원칙 1: 의존성은 안쪽으로만 향한다 (클린 아키텍처)
```text
┌─────────────────────────────────────┐
│   Execution / Market Data (외부)    │ ← Infrastructure
├─────────────────────────────────────┤
│   Risk / Position / EV (정책)       │ ← Application
├─────────────────────────────────────┤
│   State Machine / Strategy (핵심)   │ ← Domain
└─────────────────────────────────────┘

외부 → 정책 → 도메인 (의존성 방향)
도메인은 외부를 모른다
```

### 원칙 2: State Machine은 도메인 중심이다
- State Machine은 Execution 다음이 아니라 **모든 레이어가 참조하는 중심**
- "언제 무엇을 할 수 있는가"를 State가 결정

### 원칙 3: EV는 Gate이면서 Final Validator다
- **Pre-filter**: Strategy 직후 (빠른 조건 체크)
- **Full Validation**: Risk 통과 후 (무거운 시뮬레이션)
- 성능과 원칙을 모두 지킴

### 원칙 4: Backtest와 Live는 같은 구조를 쓴다
- Trading Engine 추상화
- Market Data 수신 방식만 다름
- 전략/리스크/실행 로직은 100% 동일

---

## 2. 전체 시스템 아키텍처 (수정됨)

```text
┌─────────────────────────────────────────────────────────┐
│          Trading Engine (Abstract)                      │
│          - Backtest Engine / Live Engine                │
│          - Market Data 공급 책임 분리                    │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│          STATE MACHINE (Domain Core)                    │ ← 도메인 중심
│  - IDLE / MONITORING / ENTRY / EXPANSION / EXIT         │
│  - 모든 레이어의 행동 허가 제어                          │
└─────────────────────────────────────────────────────────┘
           │                    │
           ▼                    ▼
    ┌─────────────┐      ┌─────────────┐
    │  Feature    │      │  Strategy   │
    │  Engine     │──────▶│  Layer      │
    └─────────────┘      └─────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  EV Pre-filter       │ ← 빠른 체크
                    │  (조건 충족 여부)     │
                    └──────────────────────┘
                               │ PASS
                               ▼
                    ┌──────────────────────┐
                    │  Risk Layer          │
                    └──────────────────────┘
                               │ ALLOW
                               ▼
                    ┌──────────────────────┐
                    │  EV Full Validator   │ ← 무거운 계산
                    │  (+300% 검증)        │
                    └──────────────────────┘
                               │ PASS
                               ▼
                    ┌──────────────────────┐
                    │  Position Sizer      │
                    └──────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Execution Layer     │
                    └──────────────────────┘
                               │
                               ▼
                    (State Machine에 결과 전달)
```

### 핵심 변경점

| 항목 | v1 | v2 |
|------|----|----|
| State Machine 위치 | Execution 다음 (최하위) | 도메인 중심 (최상위) |
| EV 검증 | 1단계 (Strategy 직후) | 2단계 (Pre-filter + Full) |
| Indicator 계산 | Strategy 내부? | Feature Engine (분리) |
| Backtest 지원 | 불가능 | Trading Engine 추상화로 가능 |
| Orchestrator 역할 | Market Data 직접 수신 | Engine에서 추상화 |

---

## 3. 핵심 컴포넌트 정의 (재정의)

### 3.1 Trading Engine (추가됨)

**역할**: Backtest와 Live 공통 인터페이스

```python
class ITradingEngine(Protocol):
    def run(self) -> None:
        """메인 루프 실행"""

    def get_market_data(self) -> MarketData:
        """Market Data 공급 (구현체마다 다름)"""
```

**구현체**:
- `BacktestEngine`: 역사적 데이터 replay
- `LiveEngine`: Bybit WebSocket 수신

**책임**:
- Market Data 공급 방식 추상화
- State Machine 호출
- 타이밍 제어

❌ **금지**:
- 전략 로직 포함
- 리스크 판단
- State 직접 변경

---

### 3.2 State Machine (위치 변경: 도메인 중심)

**지위**: 모든 레이어가 참조하는 중심

**입력**:
- Market Tick (Trading Engine에서)
- Execution Result
- Risk Events

**출력**:
- Current State
- Allowed Actions (이 상태에서 가능한 행동)
- Next State Trigger

**책임**:
- IDLE → MONITORING → ENTRY → EXPANSION → EXIT 흐름 제어
- "지금 Strategy를 호출할 수 있는가?" 판단
- "지금 Expansion 가능한가?" 판단
- 실패 후 COOLDOWN 강제

**State별 허용 행동**:
```python
IDLE: [observe_market]
MONITORING: [check_entry_condition]
ENTRY: [open_position, set_stop]
EXPANSION: [increase_position, aggressive_sizing]
EXIT: [close_all, record_result]
COOLDOWN: [wait]
```

❌ **금지**:
- 가격 계산
- EV 판단
- 포지션 사이즈 결정

**v1과의 차이**:
- v1: Execution 다음 (결과를 받아 다음 상태 결정)
- v2: 모든 레이어 위 (각 레이어에게 "지금 할 수 있는가" 알려줌)

---

### 3.3 Feature Engine (신규 추가)

**역할**: 기술적 지표 계산 전담

**입력**:
- Raw Market Tick

**출력**:
```python
@dataclass
class Features:
    ema200_4h: float
    atr14: float
    atr_ema50: float
    price: float
    # ... STRATEGY.md 요구사항 반영
```

**책임**:
- EMA200(4H) 계산
- ATR(14) 계산
- ATR EMA(50) 계산
- 변동성 확장 감지용 지표

❌ **금지**:
- 진입 조건 판단
- Signal 생성
- EV 계산

**이유**: Strategy가 "지표 계산 + 조건 판단"을 모두 하면 SRP 위반

**⚠️ 구현 주의사항**:
- Feature Engine은 State를 **인식하지 않는다**
- State Machine은 "Feature update 시점만 제어"
- Feature Engine은 순수 계산 레이어 (상태 독립적)

---

### 3.4 Strategy Layer (수정 없음)

**입력**:
- Features (Feature Engine에서)
- Current State (State Machine에서)

**출력**:
```python
@dataclass
class TradeIntent:
    direction: Direction  # LONG / SHORT
    confidence: float
    context: str  # "volatility_expansion", "regime_shift"
    entry_valid: bool
```

**책임**:
- 진입 조건 충족 여부 판단
- 방향성 결정
- 시장 맥락 태깅

❌ **금지**:
- EV 판단
- 리스크 판단
- 사이즈 계산
- 지표 계산

---

### 3.5 EV Framework (2단계 구조로 재설계)

#### 3.5.1 EV Pre-filter (빠른 Gate)

**위치**: Strategy 직후

**입력**:
- Trade Intent
- Account State (현재 잔고)

**출력**:
```python
@dataclass
class EVPrefilterResult:
    passed: bool
    reason: str  # "insufficient_account", "low_confidence"
```

**책임**:
- 빠른 조건 체크 (계산 최소화)
- 명백히 불가능한 트레이드 조기 차단
  - 잔고 < 최소 요구량
  - Confidence < 임계값
  - 진입 조건 미충족

**허용 기준**:
```python
# 가벼운 체크만
if account.balance < MIN_BALANCE:
    return FAIL
if intent.confidence < 0.3:
    return FAIL
return PASS  # Full Validator로 전달
```

---

#### 3.5.2 EV Full Validator (무거운 검증)

**위치**: Risk Layer 통과 후

**입력**:
- Trade Intent
- Risk Permission (Max Exposure 포함)
- Account Metrics

**출력**:
```python
@dataclass
class EVFullResult:
    passed: bool
    expected_r: float  # +300% 이상 필수
    win_probability: float
    reason: str
```

**책임**:
- **EV_FRAMEWORK.md 기준 완전 검증**
- 시뮬레이션 기반 EV 계산
  - P_win ≥ 10~15%
  - R_win ≥ +300%
  - R_loss ≤ -25%
- Tail Profit 가능성 검증

**계산 비용**: 높음 (시뮬레이션, 역사적 데이터 분석)

**왜 Risk 다음인가?**:
- Risk가 먼저 "노출 가능 여부" 판단 (빠름)
- Risk 거부 시 EV 계산 불필요 (성능 절약)
- EV는 "Risk 허용된 트레이드" 중 최종 검증

❌ **금지**:
- 진입 타이밍 결정
- 포지션 사이즈 결정

---

### 3.6 Risk Layer (수정 없음)

**입력**:
- Trade Intent (EV Pre-filter 통과한 것)
- Account Metrics
- Current State

**출력**:
```python
@dataclass
class RiskPermission:
    allowed: bool
    max_exposure: float
    emergency_flag: bool
    cooldown_trigger: bool
```

**책임**:
- 최대 노출 한도 결정
- 구조적 위험 감지
  - 연속 실패 카운트
  - Drawdown 한도
  - 청산가 여유
- 거래 차단 여부 판단

❌ **금지**:
- EV 재판단
- 포지션 사이즈 계산

---

### 3.7 Position Layer (수정 없음)

**입력**:
- Trade Intent
- Risk Permission
- EV Full Result (Expected R 포함)

**출력**:
```python
@dataclass
class PositionPlan:
    entry_size: int  # contracts
    expansion_rules: List[ExpansionLayer]
    stop_threshold: float
    target_r: float
```

**책임**:
- 초기 진입 사이즈 계산
- Expansion 레이어 설계
  - +8%, +15%, +25% 등
- 비대칭 구조 설계

❌ **금지**:
- 방향 재해석
- 리스크 재판단
- 실행 방식 결정

---

### 3.8 Execution Layer (수정 없음)

**입력**:
- Position Plan

**출력**:
```python
@dataclass
class ExecutionResult:
    status: ExecutionStatus  # FILLED / PARTIAL / FAILED
    fill_price: float
    slippage: float
    error: Optional[str]
```

**책임**:
- 주문 타입 결정 (Limit / Market)
- 체결 관리
- 슬리피지 통제
- 미체결 주문 처리

❌ **금지**:
- 전략 수정
- 리스크 판단
- State 직접 변경

---

## 4. 데이터 흐름 (v2)

### 4.1 정상 진입 흐름

```text
Market Tick (from Engine)
    ↓
State Machine: "현재 MONITORING 상태, Strategy 호출 허용"
    ↓
Feature Engine: 지표 계산
    ↓
Strategy: Trade Intent 생성
    ↓
EV Pre-filter: 빠른 조건 체크
    ↓ PASS
Risk Layer: 노출 허용 판단
    ↓ ALLOW
EV Full Validator: +300% 검증 (무거운 계산)
    ↓ PASS
Position Sizer: 사이즈 계산
    ↓
Execution: 주문 실행
    ↓
State Machine: ENTRY 상태로 전환
```

### 4.2 조기 종료 흐름 (성능 최적화)

```text
Strategy → EV Pre-filter (FAIL: low confidence)
    └─▶ 종료 (이후 단계 호출 안 함)

Strategy → EV Pre-filter (PASS) → Risk (DENY: cooldown)
    └─▶ 종료 (EV Full 계산 안 함)

Risk (ALLOW) → EV Full (FAIL: R < +300%)
    └─▶ 종료 (Position 계산 안 함)
```

**성능 이득**:
- 모든 틱마다 EV Full 계산 ❌
- 조건 충족 시에만 EV Full 계산 ✅

---

## 5. 제어 흐름 (State Machine 중심)

### 5.1 State Machine의 제어권

```python
# State Machine이 각 레이어에게 허가 여부를 알림
class TradingStateMachine:
    def process_tick(self, tick: MarketTick) -> None:
        if self.state == State.IDLE:
            # Feature만 업데이트, Strategy 호출 안 함
            self.features = self.feature_engine.update(tick)

        elif self.state == State.MONITORING:
            # Strategy 호출 허용
            intent = self.strategy.check_entry(self.features)
            if intent.entry_valid:
                # EV/Risk 파이프라인 시작
                self._process_entry_pipeline(intent)

        elif self.state == State.EXPANSION:
            # Expansion 로직 허용
            self._check_expansion_conditions()
```

### 5.2 상태 전환 트리거

| From | To | Trigger |
|------|----|----|
| IDLE | MONITORING | Trading hours start |
| MONITORING | ENTRY | All filters PASS |
| ENTRY | EXPANSION | Price moves +8% |
| EXPANSION | EXIT_SUCCESS | Target reached |
| EXPANSION | EXIT_FAILURE | Structure broken |
| EXIT | IDLE | Position closed |
| EXIT_FAILURE (3연속) | COOLDOWN | Emergency |

---

## 6. 아키텍처 위반 사례 (v2)

다음은 **즉시 버그**로 간주한다:

### 클린 아키텍처 위반
- State Machine이 Execution을 직접 호출 ❌
- Strategy가 EV를 직접 호출 ❌
- Execution이 State를 직접 변경 ❌

### 책임 위반
- Strategy가 지표 계산 ❌
- Risk가 Position 사이즈 직접 조정 ❌
- Position이 방향 재해석 ❌

### EV 우회
- **EV Pre-filter 통과 없이 Risk 호출** ❌
- **EV Full Validator 통과 없이 Position 계산** ❌
- EV 판단이 Entry 이후에 수행됨 ❌

### State Machine 우회
- State 확인 없이 Strategy 호출 ❌
- COOLDOWN 상태에서 진입 시도 ❌

---

## 7. 이 아키텍처의 존재 이유 (재선언)

### v1 선언
> 계좌를 키우기 위해
> '하지 말아야 할 트레이드'를
> 물리적으로 불가능하게 만든다.

### v2 추가
> 그리고 그 구조를
> **백테스트와 실거래에서 동일하게** 강제하며
> **성능 저하 없이** 유지한다.

---

## 8. 구현 순서 (자동으로 결정됨)

이 문서가 생긴 순간, 다음이 자동으로 정해진다:

### Phase 0: 인터페이스 정의
```python
# src/core/interfaces.py
class ITradingEngine(Protocol): ...
class IStateMachine(Protocol): ...
class IFeatureEngine(Protocol): ...
class IStrategy(Protocol): ...
class IEVPrefilter(Protocol): ...
class IEVFullValidator(Protocol): ...
class IRiskManager(Protocol): ...
class IPositionSizer(Protocol): ...
class IExecutor(Protocol): ...
```

### Phase 1: 도메인 코어
1. State Machine 구현
2. Feature Engine 구현
3. Strategy Layer 구현

### Phase 2: 정책 레이어
4. EV Pre-filter 구현
5. Risk Layer 구현
6. EV Full Validator 구현
7. Position Sizer 구현

### Phase 3: 인프라 레이어
8. Execution Layer 구현
9. Backtest Engine 구현
10. Live Engine 구현

### Phase 4: 통합
11. Dependency Injection 컨테이너
12. End-to-end 백테스트
13. Paper Trading 검증

---

## 9. 최종 선언

### 설계는 끝났다

이제 구조가 생겼다.

### v1과의 차이

| 측면 | v1 | v2 |
|------|----|----|
| 클린 아키텍처 준수 | 부분적 | 완전 |
| 백테스트 가능성 | 불가능 | 가능 |
| 성능 | EV 병목 | 2단계 필터링 |
| 확장성 | 모호 | 인터페이스 명확 |
| State Machine 위치 | 최하위 (모순) | 도메인 중심 (일관) |

### 이 문서를 읽는 개발자에게

> **이 아키텍처는 "완벽"하지 않다.
> 하지만 "Account Builder"를 위해서는
> 이것이 필요충분조건이다.**

---

## 10. 필수 보완 문서 (v2 추가)

이 아키텍처를 실전에서 작동시키려면 **4개 필수 보완 문서**가 필요하다:

### 10.1 관측 가능성 (Observability)
- **`DECISION_LOG.md`**: 모든 결정 이유 기록
  - State Machine = Account Growth Ledger
  - EV/Risk 차단 이유 추적
  - 전략 개선 데이터

### 10.2 시간 제약 (Temporal Constraints)
- **`TIME_CONTEXT.md`**: 시간 기반 제약 시스템
  - Signal 유효 기간
  - Session 기반 진입 제약
  - EV decay
  - 포지션 만료 시간

### 10.3 실행 안정성 (Execution Safety)
- **`EXECUTION_EVENTS.md`**: 실행 이벤트 처리
  - Executor = 감각기관
  - Slippage/청산 경고 → State 전환
  - 재시도 로직

### 10.4 확장 안정성 (Expansion Safety)
- **`EXPANSION_POLICY.md`**: Expansion 재검증
  - Expansion = 두 번째 진입
  - 5단계 재검증 (구조/EV/Risk/Worst-case)
  - 차단 시 EXIT_SUCCESS

**⚠️ 중요**:
> **이 4개 문서 없이 BASE_ARCHITECTURE를 구현하면
> 백테스트는 수익 내고 실거래는 죽는 시스템이 된다.**

---

## 11. 다음 문서와의 관계

이 문서를 읽은 후:

### 핵심 (필수)
- `INTERFACES.md`: 각 컴포넌트의 계약 확인
- `STATE_MACHINE.md`: 상태 흐름 상세 확인
- `EV_FRAMEWORK.md`: EV 기준 이해

### 보완 (필수 - v2)
- `DECISION_LOG.md`: 결정 기록 시스템
- `TIME_CONTEXT.md`: 시간 제약
- `EXECUTION_EVENTS.md`: 실행 이벤트
- `EXPANSION_POLICY.md`: Expansion 재검증

### 구현 (상세)
- `STRATEGY.md`: 진입 조건 구체화
- `RISK.md`: 리스크 한도 설정
- `POSITION_MODEL.md`: 사이징 로직
- `EXECUTION_MODEL.md`: 체결 처리

**이 문서는 헌법이고,
나머지는 법률이다.**
