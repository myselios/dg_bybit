# STRATEGY.md — Strategy 클래스 명세

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 하위 문서**다.

> **BASE_ARCHITECTURE.md가 "Strategy는 진입 조건 판단만"이라 했으므로,
> 이 문서는 그 판단의 구체적 기준만 정의한다.**

구조 결정 권한: BASE_ARCHITECTURE.md
진입 조건 정의 권한: 이 문서

---

## 1. Strategy의 역할 (v2 재정의)

### v2 핵심 변경

| 항목 | v1 | v2 |
|------|----|----|
| 입력 | Market Data (직접) | **Features** (Feature Engine에서) |
| 책임 | 지표 계산 + 조건 판단 | **조건 판단만** |
| 출력 | 진입 신호 | TradeIntent |

**v2 원칙**:
- Strategy는 **지표를 계산하지 않는다**
- Feature Engine이 계산한 지표만 사용
- SRP 준수

---

## 2. 전략의 목적 (변경 없음)

이 전략의 목적은 잦은 수익이 아니다.

> **큰 변동이 발생하는 순간에만 개입하여
> 계좌의 기대값을 한 단계 올리는 것**

---

## 3. 전략 유형

❌ Grid 기반 평균 회귀
❌ 횡보장 대응

⭕ **방향성 돌파 + 확장 (Directional Expansion)**

---

## 4. 시장 참여 조건 (매우 엄격)

이 전략은 **아무 때나 거래하지 않는다.**

진입 조건은 다음이 동시에 만족되어야 한다:

1. 상위 타임프레임에서 명확한 방향성
2. 변동성 확장 시작
3. 가격이 정체 구간을 이탈

> 거래 기회는 적다.
> 대신 한 번의 기회가 크다.

---

## 5. 정량화된 진입 규칙 (v2: Feature 기반)

### 5.1 방향성 필터

**사용 지표** (Feature Engine에서 제공):
- `ema200_4h`: EMA200 (4H)
- `atr14`: ATR(14)
- `price`: 현재 가격

**진입 조건**:
```python
# Long
if features.price > features.ema200_4h + features.atr14 * 0.3:
    direction = Direction.LONG

# Short
if features.price < features.ema200_4h - features.atr14 * 0.3:
    direction = Direction.SHORT
```

**목적**: 트렌드 없는 구간에서 진입 차단

---

### 5.2 변동성 조건

**사용 지표** (Feature Engine에서 제공):
- `atr_expanding`: ATR > EMA(ATR, 50) * 1.2

**1차 조건**:
```python
if not features.atr_expanding:
    return TradeIntent(entry_valid=False, reason="atr_not_expanding")
```

**2차 조건** (추가 확인):
- 최근 3개 캔들 중 2개 이상이 `ATR(14) * 0.8` 이상 크기
  (이건 Feature Engine에서 `candle_sizes` 제공)

**목적**: 변동성 확장 구간만 선택

---

### 5.3 정체 구간 이탈

**사용 지표** (Feature Engine에서 제공):
- `consolidation_breakout`: True/False
- `candle_size_significant`: 캔들 크기 > ATR * 1.0
- `volume_surge`: Volume > EMA(Volume, 20) * 1.3

**이탈 확인**:
```python
if features.consolidation_breakout:
    if features.candle_size_significant and features.volume_surge:
        # 정체 이탈 확인됨
        pass
```

**목적**: 횡보 끝 → 트렌드 시작 포착

---

### 5.4 되돌림 진입

**사용 지표** (Feature Engine에서 제공):
- `pullback_level`: Fibonacci 레벨 (0.382, 0.5, 0.618)
- `ema20_distance`: EMA20 거리

**진입 수준**:
```python
if 0.382 <= features.pullback_level <= 0.5:
    # 적정 되돌림 구간
    entry_ok = True
elif features.pullback_level > 0.618:
    # 너무 깊은 되돌림
    entry_ok = False
```

**대기 제한**:
- 최대 8개 캔들 대기
- 0.618 초과 시 진입 거부

**목적**: 돌파 후 되돌림에서 저점 진입

---

### 5.5 최종 판단 (TradeIntent 생성)

```python
def check_entry(
    self,
    features: Features,
    state: TradingState,
) -> TradeIntent:
    """진입 조건 종합 판단"""

    # State 확인 (MONITORING에서만 호출됨)
    if state != TradingState.MONITORING:
        return TradeIntent(entry_valid=False, reason="wrong_state")

    # 방향성 필터
    if features.price_above_ema:
        direction = Direction.LONG
    else:
        # Short 조건 체크
        direction = Direction.SHORT

    # 변동성 필터
    if not features.atr_expanding:
        return TradeIntent(
            entry_valid=False,
            direction=direction,
            confidence=0.0,
            reason="atr_not_expanding",
        )

    # 정체 이탈 확인
    if not features.consolidation_breakout:
        return TradeIntent(
            entry_valid=False,
            direction=direction,
            confidence=0.2,
            reason="no_breakout",
        )

    # 되돌림 적정성
    if features.pullback_level > 0.618:
        return TradeIntent(
            entry_valid=False,
            direction=direction,
            confidence=0.4,
            reason="pullback_too_deep",
        )

    # 모든 조건 충족
    confidence = calculate_confidence(features)

    return TradeIntent(
        direction=direction,
        entry_valid=True,
        confidence=confidence,
        context="volatility_expansion",
        metadata={
            "ema200": features.ema200_4h,
            "atr": features.atr14,
            "pullback_level": features.pullback_level,
        },
    )
```

---

## 6. Confidence 계산

```python
def calculate_confidence(features: Features) -> float:
    """0.0 ~ 1.0 신뢰도 계산"""

    score = 0.5  # 기본

    # 방향성 강도
    if features.price_distance_from_ema > features.atr14 * 0.5:
        score += 0.1

    # 변동성 확장 정도
    atr_ratio = features.atr14 / features.atr_ema50
    if atr_ratio > 1.3:
        score += 0.2
    elif atr_ratio > 1.2:
        score += 0.1

    # Volume 확인
    if features.volume_surge:
        score += 0.1

    # 되돌림 적정성
    if 0.382 <= features.pullback_level <= 0.5:
        score += 0.1

    return min(score, 1.0)
```

---

## 7. 확장 로직 (Strategy의 책임 아님)

**중요**: Strategy는 **확장 시점을 결정하지 않는다**.

확장은:
- State Machine이 EXPANSION 상태 진입 허가
- Position Sizer가 확장 크기 계산

Strategy는 진입 조건만 판단한다.

---

## 8. 청산 로직 (Strategy의 책임 아님)

**중요**: Strategy는 **청산 조건을 판단하지 않는다**.

청산은:
- State Machine이 EXIT 조건 감시
- Risk Manager가 손절 판단
- Position Sizer가 목표 수익 설정

Strategy는 "진입할 가치가 있는가"만 판단한다.

---

## 9. 전략의 의도 요약 (변경 없음)

이 전략은:

- 자주 맞추지 않는다
- 하지만 한 번 맞추면 크게 맞춘다

> **이 전략의 존재 이유는
> 계좌를 '점프'시키는 트레이드 한 번을
> 만들기 위함이다.**

---

## 10. 구현 클래스 매핑

이 문서는 **Strategy 클래스**를 정의한다:

```python
class Strategy(IStrategy):
    """진입 조건 판단 전담"""

    # 임계값
    MIN_ATR_EXPANSION = 1.2
    MAX_PULLBACK_LEVEL = 0.618
    MIN_CONFIDENCE = 0.3

    def check_entry(
        self,
        features: Features,
        state: TradingState,
    ) -> TradeIntent:
        """
        Feature Engine에서 계산된 지표로 진입 조건 판단
        지표 계산 ❌
        조건 판단만 ✅
        """
        ...

    def _calculate_confidence(self, features: Features) -> float:
        """신뢰도 계산 (0.0 ~ 1.0)"""
        ...
```

---

## 11. BASE_ARCHITECTURE.md와의 관계

이 문서는:
- **구조를 결정하지 않는다** (BASE가 결정)
- **진입 조건만 정의한다**
- Strategy 클래스의 명세서

BASE_ARCHITECTURE.md가 "Strategy는 Features 입력"이라 했으므로,
이 문서는 그 Features를 어떻게 해석하는지 정의한다.

**역할 분리 명확.**

---

## 12. Feature Engine 의존성 명시

Strategy가 사용하는 Features (Feature Engine 제공 필수):

```python
@dataclass
class Features:
    # 방향성 필터
    price: float
    ema200_4h: float
    price_above_ema: bool
    price_distance_from_ema: float

    # 변동성 확장
    atr14: float
    atr_ema50: float
    atr_expanding: bool  # ATR > EMA(ATR, 50) * 1.2

    # 정체 이탈
    consolidation_breakout: bool
    candle_size_significant: bool
    volume_surge: bool

    # 되돌림
    pullback_level: float  # Fibonacci 레벨
    ema20_distance: float

    # 추가
    timestamp: datetime
```

Feature Engine이 이 구조를 제공하지 못하면 Strategy는 작동 불가.

**이것이 SRP를 지키는 방법이다.**
