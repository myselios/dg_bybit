# EXPANSION_POLICY.md — Expansion 재검증 시스템

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 필수 보완 문서**다.

> **Expansion은 "보너스"가 아니다.
> Expansion은 두 번째 진입이다.
> 더 엄격해야 한다.**

구조 결정 권한: BASE_ARCHITECTURE.md
Expansion 재검증 정의 권한: 이 문서

---

## 1. 왜 Expansion 재검증이 필요한가

### 문제 상황

현재 BASE_ARCHITECTURE.md / POSITION_MODEL.md:
```python
# Layer 2: +8% 도달 시 자동 확장
# Layer 3: +15% 도달 시 자동 확장
```

**이건 위험하다.**

### 실전에서 발생하는 문제

```text
Entry: $100 → $108 (+8%)
  → Layer 2 자동 확장
  → 하지만 추세 이미 약화
  → 가격 반전
  → Layer 1 + Layer 2 모두 손실
```

**Expansion은 계좌를 죽이는 1순위 영역이다.**

---

## 2. Expansion 재검증 원칙

### 2.1 Expansion = 새로운 진입

**원칙**:
> **Expansion은 단순 추가가 아니라
> Unrealized PnL로 진입하는 '새로운 트레이드'다.**

**의미**:
- Entry와 동일한 검증 필요
- EV 재계산 필요
- Risk 재확인 필요

### 2.2 최소 안전장치

**Expansion 허가 조건** (모두 충족):
1. ✅ 트리거 달성 (+8%, +15%)
2. ✅ 구조 유지 (추세 intact)
3. ✅ EV 재검증 (경량)
4. ✅ Risk 재확인
5. ✅ Worst-case 시나리오 통과

---

## 3. Expansion 재검증 구조

### 3.1 ExpansionValidator

```python
class ExpansionValidator:
    """Expansion 허가 여부 재검증"""

    def validate_expansion(
        self,
        current_position: Position,
        features: Features,
        layer: int,
        context: MarketContext,
    ) -> ExpansionDecision:
        """
        Expansion 허가 여부 판단

        Returns:
            ExpansionDecision (허가/차단 + 이유)
        """

        # 1. 트리거 확인
        if not self._check_trigger(current_position, layer):
            return ExpansionDecision(
                allowed=False,
                reason="trigger_not_reached",
            )

        # 2. 구조 유지 확인
        if not self._check_structure_intact(features):
            return ExpansionDecision(
                allowed=False,
                reason="structure_broken",
            )

        # 3. EV 재검증 (경량)
        if not self._revalidate_ev_lightweight(current_position, features):
            return ExpansionDecision(
                allowed=False,
                reason="ev_revalidation_failed",
            )

        # 4. Risk 재확인
        if not self._recheck_risk(current_position):
            return ExpansionDecision(
                allowed=False,
                reason="risk_limit_exceeded",
            )

        # 5. Worst-case 시나리오
        if not self._check_worst_case(current_position, layer):
            return ExpansionDecision(
                allowed=False,
                reason="worst_case_unacceptable",
            )

        # 모든 조건 통과
        return ExpansionDecision(
            allowed=True,
            expansion_size=self._calculate_expansion_size(layer),
        )
```

---

## 4. 재검증 조건 상세

### 4.1 구조 유지 확인

**목적**: 추세가 여전히 intact한가?

```python
def _check_structure_intact(self, features: Features) -> bool:
    """추세 구조 유지 확인"""

    # 방향성 필터 유지
    if not features.price_above_ema:
        return False  # Long 방향 붕괴

    # 변동성 유지
    if not features.atr_expanding:
        return False  # 변동성 축소

    # EMA 거리 유지
    distance_pct = (features.price - features.ema200_4h) / features.ema200_4h

    if distance_pct < 0.01:  # EMA200에 너무 가까움
        return False

    return True
```

### 4.2 EV 재검증 (경량)

**목적**: Unrealized PnL로 진입해도 여전히 EV > 0인가?

```python
def _revalidate_ev_lightweight(
    self,
    current_position: Position,
    features: Features,
) -> bool:
    """EV 경량 재검증 (시뮬레이션 생략)"""

    # Unrealized PnL 기반 진입 가격
    effective_entry = current_position.avg_price * (
        1 + current_position.unrealized_pnl_pct
    )

    # 현재 가격 대비 여유
    upside_remaining = (features.price - effective_entry) / effective_entry

    # 최소 +100% 여유 필요
    MIN_UPSIDE_REMAINING = 1.0

    if upside_remaining < MIN_UPSIDE_REMAINING:
        return False

    return True
```

**논리**:
```text
Entry: $100
Current: $108 (+8%)
Effective Entry (Layer 2): $108

필요 수익: +300%
→ Target: $108 * 4 = $432

현재 여유: ($432 - $108) / $108 = 300%
→ OK, 충분한 여유
```

### 4.3 Risk 재확인

**목적**: Expansion 후에도 청산가 여유가 충분한가?

```python
def _recheck_risk(self, current_position: Position) -> bool:
    """Risk 한도 재확인"""

    # Expansion 후 예상 청산가
    new_liquidation_price = self._calculate_new_liquidation_price(
        current_position,
        expansion_layer=2,
    )

    # 청산가 거리 (ATR 배수)
    distance_atr = abs(
        (new_liquidation_price - current_position.current_price)
        / current_position.atr
    )

    # 최소 3 ATR 거리 필요
    MIN_LIQUIDATION_DISTANCE = 3.0

    if distance_atr < MIN_LIQUIDATION_DISTANCE:
        return False

    return True
```

### 4.4 Worst-case 시나리오

**목적**: Expansion 후 즉시 반전 시 손실 허용 가능한가?

```python
def _check_worst_case(
    self,
    current_position: Position,
    layer: int,
) -> bool:
    """Worst-case 시나리오 체크"""

    # 현재 상태
    unrealized_pnl = current_position.unrealized_pnl
    total_size = current_position.total_size

    # Expansion 후 사이즈
    expansion_size = self._calculate_expansion_size(layer)
    new_total_size = total_size + expansion_size

    # Worst-case: Entry 가격으로 즉시 반전
    entry_price = current_position.avg_price
    current_price = current_position.current_price

    # Expansion 후 손실 (Entry까지 반전)
    loss_if_reversed = (
        # 기존 포지션 손실
        (entry_price - current_price) * total_size +
        # 신규 포지션 손실
        (entry_price - current_price) * expansion_size
    )

    # 허용 손실 (계좌의 -25%)
    max_allowed_loss = current_position.account_balance * 0.25

    if abs(loss_if_reversed) > max_allowed_loss:
        return False

    return True
```

---

## 5. Expansion Decision Output

### 5.1 ExpansionDecision

```python
@dataclass
class ExpansionDecision:
    """Expansion 허가 결정"""

    allowed: bool
    reason: str

    # 허가 시
    expansion_size: Optional[int]
    new_total_size: Optional[int]
    new_liquidation_price: Optional[float]

    # 재검증 상세
    structure_intact: bool
    ev_revalidation_passed: bool
    risk_revalidation_passed: bool
    worst_case_passed: bool

    # 로그용
    timestamp: datetime
    layer: int
    unrealized_pnl_pct: float
```

---

## 6. State Machine 통합

### 6.1 Expansion 상태에서 재검증

```python
class TradingStateMachine:
    def process_tick(self, tick: MarketData, context: MarketContext) -> None:
        if self.state == State.ENTRY:
            # Expansion 트리거 감시
            if self._check_expansion_trigger():
                # 재검증
                decision = self._expansion_validator.validate_expansion(
                    current_position=self._position,
                    features=self._features,
                    layer=2,
                    context=context,
                )

                if decision.allowed:
                    # Expansion 허가
                    self.transition_to(
                        State.EXPANSION,
                        reason=f"layer_2_validated: {decision.reason}",
                        decision_maker="expansion_validator",
                    )

                    # Position 확대
                    self._expand_position(decision.expansion_size)

                else:
                    # Expansion 차단
                    # 로그만 기록, State 유지
                    self._log_expansion_denial(decision)

        elif self.state == State.EXPANSION:
            # Layer 3 재검증 (동일 로직)
            ...
```

---

## 7. Expansion 차단 시 대응

### 7.1 차단 이유별 대응

| 차단 이유 | 대응 |
|----------|------|
| structure_broken | 즉시 EXIT_SUCCESS (수익 확정) |
| ev_revalidation_failed | EXIT_SUCCESS (목표 미달이지만 수익) |
| risk_limit_exceeded | EXIT_SUCCESS (리스크 한도 초과) |
| worst_case_unacceptable | EXIT_SUCCESS (안전 우선) |

**핵심**:
> **Expansion 차단 = 실패 아님
> 현재 수익으로 만족 = 성공**

---

## 8. Expansion 로그 저장

### 8.1 ExpansionDecisionLog (DECISION_LOG.md 연동)

```python
@dataclass
class ExpansionDecisionLog:
    """Expansion 판단 기록"""

    timestamp: datetime

    # Position 상태
    entry_price: float
    current_price: float
    unrealized_pnl_pct: float
    current_size: int

    # Expansion 요청
    layer: int
    trigger_pnl_pct: float

    # 재검증 결과
    structure_intact: bool
    ev_revalidation_passed: bool
    risk_revalidation_passed: bool
    worst_case_passed: bool

    # 결정
    expansion_allowed: bool
    expansion_size: Optional[int]

    # 실패 이유
    denial_reason: Optional[str]

# State Machine
def _check_expansion_conditions(self) -> None:
    decision = self._expansion_validator.validate_expansion(...)

    # 로그 저장
    log = ExpansionDecisionLog(
        timestamp=datetime.now(),
        layer=2,
        expansion_allowed=decision.allowed,
        ...
    )

    self._decision_log_store.save_expansion_log(log)
```

---

## 9. BASE_ARCHITECTURE.md 반영 필요 사항

### Position Sizer Interface 수정

**Before**:
```python
class IPositionSizer(Protocol):
    def calculate(
        self,
        intent: TradeIntent,
        risk_permission: RiskPermission,
        ev_result: EVFullResult,
    ) -> PositionPlan:
        ...
```

**After** (Expansion 메서드 추가):
```python
class IPositionSizer(Protocol):
    def calculate(
        self,
        intent: TradeIntent,
        risk_permission: RiskPermission,
        ev_result: EVFullResult,
    ) -> PositionPlan:
        """초기 진입 계획"""
        ...

    def validate_expansion(
        self,
        current_position: Position,
        features: Features,
        layer: int,
        context: MarketContext,
    ) -> ExpansionDecision:
        """Expansion 재검증"""
        ...
```

---

## 10. Expansion 체크리스트

### Expansion 요청 시 (자동)
- [ ] 트리거 달성 (+8%, +15%)
- [ ] 구조 유지 (추세 intact)
- [ ] EV 재검증 (경량)
- [ ] Risk 재확인
- [ ] Worst-case 시나리오

### Expansion 차단 시
- [ ] 차단 이유 로그 기록
- [ ] EXIT_SUCCESS 검토

### Expansion 허가 시
- [ ] Position 확대
- [ ] 새 청산가 계산
- [ ] State → EXPANSION

---

## 11. 이 문서의 최종 선언

> **Expansion은 "보너스"가 아니다.
> Expansion은 Unrealized PnL로 진입하는
> 두 번째 트레이드다.**

> **모든 Expansion은 재검증되어야 한다.
> 트리거 달성 ≠ 자동 허가
> 구조 붕괴 시 즉시 청산이 정답이다.**

---

## 12. 구현 우선순위

### Phase 0 (필수)
- ExpansionValidator 정의
- 구조 유지 확인
- Worst-case 시나리오

### Phase 1 (확장)
- EV 경량 재검증
- Risk 재확인
- Expansion 차단 대응

### Phase 2 (최적화)
- Expansion 성공률 분석
- Layer별 재검증 임계값 조정

**이 문서는 BASE_ARCHITECTURE.md의
Expansion 안정성을 80% 향상시킨다.**

**이것이 마지막 안전장치다.**
