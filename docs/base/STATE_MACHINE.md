# STATE_MACHINE.md — TradingStateMachine 명세

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 하위 문서**다.

> **BASE_ARCHITECTURE.md가 "State Machine은 도메인 중심"이라 했으므로,
> 이 문서는 그 중심의 구체적 흐름만 정의한다.**

구조 결정 권한: BASE_ARCHITECTURE.md
상태 흐름 정의 권한: 이 문서

---

## 1. State Machine의 지위 (v2 재정의)

### v1과의 차이

| 항목 | v1 (잘못됨) | v2 (정답) |
|------|-------------|-----------|
| 위치 | Execution 다음 (최하위) | **도메인 중심** (최상위) |
| 역할 | 결과를 받아 다음 상태 결정 | **행동 허가 제어** |
| 제어 방향 | Execution → State Machine | State Machine → 모든 레이어 |

### v2 핵심 개념

> **State Machine이
> 각 레이어에게
> "지금 무엇을 할 수 있는가"를 알려준다.**

이 문서는 단순한 상태 다이어그램이 아니다.

> **이 문서는
> '언제 공격하고, 언제 물러나며,
> 언제 다시 시도할 수 있는지'를
> 강제하는 시스템의 행동 헌법이다.**

Account Builder 시스템에서
State Machine은 **수익보다 우선**한다.

---

## 2. 상태 머신의 핵심 철학 (변경 없음)

### 기존 시스템과의 차이

| 항목 | 일반 시스템 | Account Builder |
|---|---|---|
| 실패 | 예외 | **전제** |
| 중단 | 보호 | **기회 상실** |
| 재진입 | 제한 | **허용** |
| 목적 | 생존 | **점프** |

> 이 시스템은
> **실패 후 복귀가 '가능'해야 하는 것이 아니라
> '자연스러워야' 한다.**

---

## 3. 전체 상태 개요

```text
INIT
 └─▶ IDLE
      ├─▶ MONITORING
      │     ├─▶ ENTRY
      │     │     ├─▶ EXPANSION
      │     │     │     ├─▶ EXIT_SUCCESS
      │     │     │     └─▶ EXIT_FAILURE
      │     │     └─▶ EXIT_FAILURE
      │     └─▶ COOLDOWN
      └─▶ TERMINATED
```

---

## 4. 상태별 정의 및 의도

### 4.1 INIT — 시스템 초기화

**의도**: 시스템이 "정상 상태"임을 확인

**진입 조건**:
- 시스템 시작
- 재시작

**허용 행동** (v2 추가):
- 컴포넌트 연결 확인
- 계좌 상태 로딩
- 로그 초기화

**행동**:
- Risk / Strategy / Execution 연결 확인
- State Machine 자체 초기화

**이탈 조건**:
- 모든 컴포넌트 정상 → IDLE
- 오류 발생 → TERMINATED

---

### 4.2 IDLE — 대기 상태

**의도**: 아무것도 안 하는 것도 전략임을 명시

**허용 행동** (v2 명확화):
```python
IDLE: [observe_market]
```

**행동**:
- 시장 관찰
- **Feature Engine 업데이트만 허용**
- Strategy 호출 ❌
- 포지션 없음
- 리스크 노출 0

**이탈 조건**:
- 거래 시간 조건 충족 → MONITORING
- 시스템 종료 요청 → TERMINATED

**v2 강조**: IDLE 상태에서는 Feature만 업데이트되고, Strategy는 호출되지 않는다.

---

### 4.3 MONITORING — 기회 탐색

**의도**: 기회가 오기 전까지는 절대 진입하지 않는다

**허용 행동** (v2 명확화):
```python
MONITORING: [check_entry_condition]
```

**행동**:
- Feature Engine 업데이트
- **Strategy 호출 허용**
- 방향성 필터 확인
- 변동성 확장 감지
- 진입 조건 충족 여부 평가

**이탈 조건**:
- 모든 진입 조건 충족 **+ EV Pre-filter PASS + Risk ALLOW + EV Full PASS** → ENTRY
- 조건 소멸 → IDLE
- 연속 실패 후 쿨다운 필요 → COOLDOWN

**v2 추가**: MONITORING에서만 Strategy가 호출된다. 다른 상태에서는 호출 불가.

---

### 4.4 ENTRY — 초기 진입

**의도**: "확신 없음 상태"에서의 탐색 베팅

**허용 행동** (v2 명확화):
```python
ENTRY: [open_position, set_stop, monitor_expansion_trigger]
```

**행동**:
- 소형 포지션 진입 (Position Sizer 계산 결과)
- 손실 허용 범위 설정
- 청산가 여유 확인
- **Expansion 트리거 모니터링 시작**

**이탈 조건**:
- 가격이 예상 방향 (+8% 도달) → EXPANSION
- 즉시 반대 움직임 (손절 조건) → EXIT_FAILURE

**v2 강조**: ENTRY는 "작게 시작"의 상태. 여기서 Expansion 트리거를 감시한다.

---

### 4.5 EXPANSION — 공격 구간 (핵심 상태)

**의도**: 이 시스템이 존재하는 유일한 이유

**허용 행동** (v2 명확화):
```python
EXPANSION: [increase_position, aggressive_sizing, monitor_structure]
```

**행동**:
- **수익 구간에서 포지션 확대**
- 리스크 한시적 완화
- 계좌 점프 시도
- 구조 붕괴 감시

**허용**:
- 큰 변동성
- 높은 노출
- 공격적 사이징

**이탈 조건**:
- 목표 수익 도달 (+300% 이상) → EXIT_SUCCESS
- 추세 붕괴 (구조 깨짐) → EXIT_FAILURE
- 구조적 위험 감지 → EXIT_FAILURE

**v2 추가**: EXPANSION은 "미치는 구간". 하지만 구조 붕괴 시 즉시 EXIT.

---

### 4.6 EXIT_SUCCESS — 성공적 종료

**의도**: 계좌 점프 여부 판정

**허용 행동** (v2 명확화):
```python
EXIT_SUCCESS: [close_all, record_result, evaluate_jump]
```

**행동**:
- 전량 청산
- 수익 확정
- 로그 스냅샷 저장
- **계좌 점프 달성 여부 평가**

**이탈 조건**:
- 계좌 레벨 재평가
- 점프 성공 (예: 100→300 USD) → IDLE
- 부분 성공 (예: 100→150 USD) → COOLDOWN

**v2 추가**: EXIT_SUCCESS여도 목표 미달 시 COOLDOWN으로.

---

### 4.7 EXIT_FAILURE — 실패 종료

**의도**: 실패는 시스템의 일부

**허용 행동** (v2 명확화):
```python
EXIT_FAILURE: [close_all, record_failure, tag_reason]
```

**행동**:
- 포지션 정리
- 손실 기록
- 실패 원인 태깅

**이탈 조건**:
- 연속 실패 한도 미도달 → IDLE
- 연속 실패 초과 (3회 이상) → COOLDOWN
- 계좌 임계 손실 (-70% 이상) → TERMINATED

**v2 추가**: 실패 태깅으로 패턴 분석 가능.

---

### 4.8 COOLDOWN — 재정비 구간

**의도**: 시스템 과열 방지, 실패 후 즉각 재진입 방지

**허용 행동** (v2 명확화):
```python
COOLDOWN: [wait, observe_only]
```

**행동**:
- 일정 시간 거래 금지
- 시장 관찰만 수행
- Strategy 호출 ❌
- Entry 시도 ❌

**이탈 조건**:
- 쿨다운 시간 종료 (예: 24시간) → IDLE
- 시스템 종료 → TERMINATED

**v2 강조**: COOLDOWN은 "의도된 비활동". 이 상태를 우회하는 코드는 버그.

---

### 4.9 TERMINATED — 종료 상태

**의도**: 시스템 보호가 아니라 의미 없는 시도의 종료

**진입 조건**:
- 시스템 오류
- 계좌 임계 손실
- 사용자 종료 명령
- **EV Full Validator 통과 트레이드 희귀** (v2 추가)

**행동**:
- 모든 활동 중단
- 최종 로그 저장
- 포지션 강제 청산 (있다면)

---

## 5. v2 핵심 개념: 행동 허가 제어

### 5.1 State별 허용 행동 매핑

```python
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

# State → 허용 행동 매핑
ALLOWED_ACTIONS = {
    State.IDLE: {Action.OBSERVE_MARKET},
    State.MONITORING: {Action.CHECK_ENTRY},
    State.ENTRY: {Action.OPEN_POSITION, Action.SET_STOP},
    State.EXPANSION: {Action.INCREASE_POSITION, Action.MONITOR_STRUCTURE},
    State.EXIT_SUCCESS: {Action.CLOSE_POSITION, Action.RECORD_RESULT},
    State.EXIT_FAILURE: {Action.CLOSE_POSITION, Action.RECORD_FAILURE},
    State.COOLDOWN: {Action.WAIT},
    State.TERMINATED: set(),  # 아무것도 할 수 없음
}
```

### 5.2 State Machine의 제어 방식

```python
class TradingStateMachine:
    def process_tick(self, tick: MarketData) -> None:
        """Market Tick마다 호출"""

        # Feature는 항상 업데이트 (State 독립적)
        self.features = self.feature_engine.update(tick)

        # State별 분기
        if self.state == State.IDLE:
            # Strategy 호출 안 함
            pass

        elif self.state == State.MONITORING:
            # Strategy 호출 허용
            if self.can_execute_action(Action.CHECK_ENTRY):
                intent = self.strategy.check_entry(self.features)
                if intent.entry_valid:
                    self._process_entry_pipeline(intent)

        elif self.state == State.ENTRY:
            # Expansion 트리거 감시
            if self._check_expansion_trigger():
                self.transition_to(State.EXPANSION, "price_moved_8pct")

        elif self.state == State.EXPANSION:
            # Expansion 로직
            self._process_expansion()

        elif self.state == State.COOLDOWN:
            # 아무것도 안 함
            pass

    def can_execute_action(self, action: Action) -> bool:
        """이 상태에서 해당 액션 가능한가?"""
        return action in ALLOWED_ACTIONS[self.state]
```

---

## 6. 상태 전환 트리거 (v2 명확화)

| From | To | Trigger | 조건 |
|------|----|----|------|
| INIT | IDLE | All systems ready | 컴포넌트 정상 |
| IDLE | MONITORING | Trading hours start | 거래 시간 |
| MONITORING | ENTRY | All filters PASS | EV Pre + Risk + EV Full 통과 |
| MONITORING | COOLDOWN | Consecutive failures | 연속 3회 실패 |
| ENTRY | EXPANSION | Price moves +8% | Expansion 트리거 |
| ENTRY | EXIT_FAILURE | Price moves against | 손절 조건 |
| EXPANSION | EXIT_SUCCESS | Target reached | +300% 이상 |
| EXPANSION | EXIT_FAILURE | Structure broken | 추세 붕괴 |
| EXIT_SUCCESS | IDLE | Jump achieved | 계좌 점프 성공 |
| EXIT_SUCCESS | COOLDOWN | Partial success | 목표 미달 |
| EXIT_FAILURE | IDLE | Attempts remaining | 연속 실패 < 3회 |
| EXIT_FAILURE | COOLDOWN | Consecutive failures | 연속 실패 ≥ 3회 |
| EXIT_FAILURE | TERMINATED | Critical loss | Drawdown > -70% |
| COOLDOWN | IDLE | Cooldown expired | 24시간 경과 |
| ANY | TERMINATED | System error / User stop | - |

---

## 7. Emergency Stop에 대한 재정의 (변경 없음)

❌ "위험하니까 멈춘다"
⭕ "더 이상 시도할 의미가 없어서 멈춘다"

Emergency Stop은:
- 일시적 변동성 ❌
- 연속 손실 ⭕

이 아니라,
- 구조 붕괴
- 계좌 소멸 위험
- 시스템 신뢰 붕괴

에서만 발동된다.

---

## 8. 이 State Machine의 핵심 요약

### v1 선언 (유지)

1. 이 시스템은 실패를 전제로 설계됨
2. 실패 후 복귀가 자연스러움
3. 공격 상태(EXPANSION)가 핵심
4. IDLE과 COOLDOWN은 의도된 비활동

### v2 추가

5. **State Machine은 도메인 중심**
   - Execution 다음 ❌
   - 모든 레이어 위에서 행동 허가 ✅

6. **각 상태는 허용 행동을 정의**
   - "지금 Strategy 호출 가능한가?"
   - "지금 Expansion 가능한가?"

7. **State 우회는 버그**
   - COOLDOWN에서 Entry 시도 → 버그
   - IDLE에서 Strategy 호출 → 버그

---

## 9. 구현 클래스 매핑

이 문서는 **TradingStateMachine 클래스**를 정의한다:

```python
class TradingStateMachine:
    """State Machine 구현"""

    def __init__(
        self,
        feature_engine: IFeatureEngine,
        strategy: IStrategy,
        ev_prefilter: IEVPrefilter,
        risk_manager: IRiskManager,
        ev_full_validator: IEVFullValidator,
        position_sizer: IPositionSizer,
        executor: IExecutor,
    ):
        self._state = TradingState.INIT
        # 의존성 주입으로 모든 레이어 참조

    def process_tick(self, tick: MarketData) -> None:
        """메인 루프에서 매 Tick마다 호출"""
        ...

    def can_execute_action(self, action: Action) -> bool:
        """행동 허가 여부"""
        return action in ALLOWED_ACTIONS[self._state]

    def transition_to(
        self,
        next_state: TradingState,
        reason: str,
    ) -> None:
        """상태 전환 (내부 로직만 호출)"""
        self._log_transition(self._state, next_state, reason)
        self._state = next_state

    @property
    def current_state(self) -> TradingState:
        return self._state
```

---

## 10. 이 문서를 읽는 개발자에게

### v1 경고 (유지)

이 상태 머신을 임의로 단순화하지 마라.

이 흐름은
돈을 지키기 위한 것이 아니라
돈을 키우기 위해
실패를 통제하는 구조다.

### v2 추가 경고

**State Machine을 우회하는 모든 코드는 버그다.**

다음은 금지:
- Executor가 State를 직접 변경
- Strategy가 State 확인 없이 호출됨
- COOLDOWN 상태에서 Entry 시도

---

## 11. BASE_ARCHITECTURE.md와의 관계

이 문서는:
- **구조를 결정하지 않는다** (BASE가 결정)
- **상태 흐름만 정의한다**
- TradingStateMachine 클래스의 명세서

BASE_ARCHITECTURE.md가 "State Machine은 도메인 중심"이라 했으므로,
이 문서는 그 중심의 구체적 동작을 정의한다.

**역할 분리 명확.**

상태가 많은 이유는
망설이기 위해서가 아니라
**'언제 미쳐야 하는지'를
명확히 하기 위함이다.**
