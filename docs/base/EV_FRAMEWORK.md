# EV_FRAMEWORK.md — EVPrefilter + EVFullValidator 명세

## 0. 이 문서의 지위

이 문서는 **BASE_ARCHITECTURE.md의 하위 문서**다.

> **BASE_ARCHITECTURE.md가 "EV는 2단계 검증"이라 했으므로,
> 이 문서는 그 2단계의 구체적 기준만 정의한다.**

구조 결정 권한: BASE_ARCHITECTURE.md
수학적 기준 정의 권한: 이 문서

---

## 1. Account Builder의 수학적 질문 (재확인)

> **"이 시스템은
> 파산 확률을 감수하더라도
> 계좌 점프가 발생할 '기대값'이 있는가?"**

이를 위해 필요한 것은 딱 4개다.

1. 승률 (Win Probability)
2. 평균 손실 (Avg Loss)
3. 평균 수익 (Avg Win)
4. 허용 시도 횟수 (Attempts)

---

## 2. 목표 수치 (역산, 변경 없음)

### 전제

- 시작 자본: 100 USD
- 목표: 300~1,000 USD 구간 진입
- 허용 실패: 여러 번
- 성공은 **1~2회면 충분**

### 실패 구조 가정

- 평균 손실: -25%
- 연속 실패 가능: 3~4회

→ 4회 실패 시 잔고: 100 → 75 → 56 → 42 → **31 USD**

👉 이 상태에서도 **"한 방"은 가능해야 한다.**

---

## 3. 성공 트레이드의 최소 조건 (절대 기준)

위 손실을 **한 번에 뒤집기 위해 필요한 수익률**:

- 31 → 100 복구: **+222%**
- 31 → 300 점프: **+868%**

즉,

> **성공 트레이드는
> 최소 +300% 이상을 만들어야
> Account Builder로서 의미가 있다.**

이게 싫으면, 이 프로젝트는 여기서 끝이다.

---

## 4. EV 최소 조건 수식

Account Builder의 기대값은 이렇게 정의한다.

```
EV = (P_win × R_win) − (P_loss × R_loss)
```

### 최소 통과 조건

- P_win ≥ 10~15%
- R_win ≥ +300%
- R_loss ≤ -25%

예시:
```
EV = (0.15 × 3.0) − (0.85 × 0.25)
   = 0.45 − 0.2125
   = +0.2375
```

👉 **양(+)의 기대값**

---

## 5. v2 구조: 2단계 검증으로 분리

**BASE_ARCHITECTURE.md 지시사항**:
- EV Pre-filter: Strategy 직후 (빠른 Gate)
- EV Full Validator: Risk 통과 후 (무거운 검증)

이 문서는 각 단계의 **판단 기준**을 정의한다.

---

## 6. EV Pre-filter 기준 (빠른 Gate)

### 6.1 목적

명백히 불가능한 트레이드를 조기 차단.
**무거운 EV 계산을 하지 않는다.**

### 6.2 체크 항목

#### 1. 잔고 충분성
```python
if account.balance < MIN_BALANCE_THRESHOLD:
    return FAIL("insufficient_balance")
```

**MIN_BALANCE_THRESHOLD**:
- 최소 진입 가능 금액: 10 USD
- 레버리지 3x 기준: 최소 포지션 30 USD 가치

#### 2. Confidence 임계값
```python
if intent.confidence < MIN_CONFIDENCE:
    return FAIL("low_confidence")
```

**MIN_CONFIDENCE**: 0.3 (30%)
- Strategy가 "확신 없음" 신호 → 즉시 차단
- 이건 EV 계산 전에 걸러야 함

#### 3. 진입 조건 충족
```python
if not intent.entry_valid:
    return FAIL("entry_condition_not_met")
```

- STRATEGY.md의 모든 조건 충족 여부
- 하나라도 미충족 → 차단

### 6.3 통과 조건

**Pre-filter는 "FAIL 이유를 찾는다"**:
- 명백한 불가 조건 하나라도 있으면 FAIL
- 모든 조건 통과 시에만 PASS

**계산 비용**: O(1) (상수 시간, 매우 빠름)

---

## 7. EV Full Validator 기준 (무거운 검증)

### 7.1 목적

**+300% 가능성을 시뮬레이션으로 검증**
이 단계만 EV_FRAMEWORK.md의 수학적 기준을 완전히 적용한다.

### 7.2 입력 조건

- EV Pre-filter: PASS
- Risk Manager: ALLOW

**왜 Risk 다음인가?**:
- Risk가 "노출 불가" 판단 → EV 계산 불필요
- 성능 절약

### 7.3 검증 알고리즘

#### Step 1: 시나리오 시뮬레이션

```python
def simulate_outcomes(
    intent: TradeIntent,
    risk_permission: RiskPermission,
    account: AccountMetrics,
) -> List[Outcome]:
    """
    Monte Carlo 시뮬레이션 (1000회)
    - 진입 → Expansion → 청산 시뮬레이션
    - ATR 기반 변동성
    - Tail Event 확률 고려
    """
    outcomes = []
    for _ in range(1000):
        outcome = simulate_single_trade(
            entry_price=current_price,
            direction=intent.direction,
            volatility=features.atr14,
            max_exposure=risk_permission.max_exposure,
        )
        outcomes.append(outcome)
    return outcomes
```

#### Step 2: 승률 및 R 계산

```python
wins = [o for o in outcomes if o.pnl > 0]
losses = [o for o in outcomes if o.pnl <= 0]

P_win = len(wins) / len(outcomes)
R_win = mean([w.pnl_pct for w in wins])
R_loss = abs(mean([l.pnl_pct for l in losses]))
```

#### Step 3: EV 기준 검증

```python
# 최소 조건 체크
if P_win < 0.10:
    return FAIL("win_probability_too_low")

if R_win < 3.0:  # +300%
    return FAIL("r_multiple_insufficient")

if R_loss > 0.25:  # -25%
    return FAIL("avg_loss_too_high")

# EV 계산
ev = (P_win * R_win) - ((1 - P_win) * R_loss)

if ev <= 0:
    return FAIL("negative_ev")

return PASS(
    expected_r=R_win,
    win_probability=P_win,
    ev_value=ev,
)
```

### 7.4 Tail Profit 검증 (추가 조건)

Account Builder는 "평균 승리"가 아니라 **"꼬리 수익"**을 노린다.

```python
# 상위 10% 승리 트레이드 분석
top_wins = sorted(wins, key=lambda x: x.pnl_pct, reverse=True)[:100]
tail_avg = mean([w.pnl_pct for w in top_wins])

if tail_avg < 5.0:  # +500%
    return FAIL("insufficient_tail_profit")
```

**이유**:
- 평균 +300%여도 꼬리가 약하면 → 계좌 점프 불가
- 상위 10%가 +500% 이상 → Tail Event 존재

---

## 8. 이 기준이 의미하는 것 (변경 없음)

### ❌ 허용 안 되는 것

- 1R : 1R 구조
- Grid 기반 잔수익
- 잦은 소액 익절
- "조금씩 쌓기" 전략

---

### ⭕ 반드시 필요한 것

- **Tail Profit 구조**
- 낮은 승률 허용
- 긴 대기
- 극단적 비대칭

> **Account Builder는
> '자주 이기는 시스템'이 아니라
> '가끔 미친 듯이 이기는 시스템'이다.**

---

## 9. 기존 설계에 미치는 영향 (강제 조건)

### STRATEGY에 대한 강제 조건

- 진입은 "확률"이 아니라 **"파괴력" 기준**
- 변동성 확장 + 구조적 돌파 필수
- 평범한 추세 ❌
- **레짐 전환(Regime Shift)**만 허용

### POSITION_MODEL 강제 조건

- Expansion은 **수익 구간에서만**
- 목표 R 미달 시:
  - 공격 금지
  - 의미 없는 트레이드로 분류

### RISK_MODEL 강제 조건

- -25% 손실은 허용
- 하지만 **+300% 가능성 없는 트레이드는 금지**
- 청산 회피보다 **EV 미달 차단**이 우선

---

## 10. 실패 관리에 대한 재정의

실패는 이렇게 분류한다.

| 실패 유형 | 평가 |
|---|---|
| -25% 손실 | 정상 |
| 연속 3회 실패 | 정상 |
| **EV Pre-filter 통과 실패** | 조기 차단 (정상) |
| **EV Full Validator 통과 실패** | 시스템 오류 |
| +300% 미달 수익 | 전략 실패 |

**v2 추가**:
- Pre-filter 차단 = 당연한 필터링
- Full Validator 차단 = **설계 결함**

---

## 11. 종료 조건 (이게 없으면 도박이다)

다음 중 하나면 **프로젝트 종료**:

1. 10회 시도 내 +300% 트레이드 0회
2. **EV Full Validator 통과하는 트레이드 자체가 희귀**
3. 실행 비용으로 기대값 붕괴

> **Account Builder는
> 영원히 시도하는 시스템이 아니다.**

---

## 12. v2 구조 요약

### 2단계 검증 흐름

```text
Trade Intent
    ↓
┌─────────────────────────────┐
│  EV Pre-filter              │
│  - 잔고 충분성              │
│  - Confidence 임계값        │
│  - 진입 조건 충족           │
│  [빠른 체크, 계산 최소]     │
└─────────────────────────────┘
    ↓ PASS
Risk Manager
    ↓ ALLOW
┌─────────────────────────────┐
│  EV Full Validator          │
│  - Monte Carlo 시뮬레이션   │
│  - P_win ≥ 10%              │
│  - R_win ≥ +300%            │
│  - Tail Profit 검증         │
│  [무거운 계산]              │
└─────────────────────────────┘
    ↓ PASS
Position Sizer
```

### 핵심 차이

| 항목 | Pre-filter | Full Validator |
|------|-----------|----------------|
| 위치 | Strategy 직후 | Risk 통과 후 |
| 계산 비용 | O(1) 상수 시간 | O(n) 시뮬레이션 |
| 목적 | 명백한 불가 차단 | +300% 가능성 검증 |
| 빈도 | 매 신호마다 | 조건 충족 시만 |

---

## 13. 구현 클래스 매핑

이 문서는 2개 클래스를 정의한다:

### 13.1 EVPrefilter 클래스
```python
class EVPrefilter:
    MIN_BALANCE = 10.0
    MIN_CONFIDENCE = 0.3

    def validate(
        self,
        intent: TradeIntent,
        account: AccountState,
    ) -> EVPrefilterResult:
        # 빠른 체크만
        ...
```

### 13.2 EVFullValidator 클래스
```python
class EVFullValidator:
    MIN_WIN_PROB = 0.10
    MIN_R_WIN = 3.0
    MAX_R_LOSS = 0.25
    MIN_TAIL_PROFIT = 5.0

    def validate(
        self,
        intent: TradeIntent,
        risk_permission: RiskPermission,
        account: AccountMetrics,
    ) -> EVFullResult:
        # 시뮬레이션 기반 검증
        ...
```

---

## 14. 동적 EV 임계값 (v2.1 추가)

### 14.1 문제: 정적 임계값의 한계

**현재 구조**:
```python
MIN_R_WIN = 3.0  # +300% (고정)
MIN_WIN_PROB = 0.10  # 10% (고정)
MIN_TAIL_PROFIT = 5.0  # +500% (고정)
```

**실전 문제**:
- 변동성 수축 국면: +300% 도달 불가능 → 진입 기회 0
- 변동성 확장 국면: +300%는 쉬움 → 기준 너무 낮음
- Drawdown 상태: -50% 손실 후 +300%로는 복구 불가

**결과**:
> **시장 환경 변화 시
> EV 조건이 현실과 괴리되어
> 기회 상실 또는 리스크 과다 발생**

### 14.2 동적 임계값 계산

#### 14.2.1 변동성 Regime 기반 조정

```python
@dataclass
class VolatilityRegime:
    """변동성 상태"""

    type: str  # "expanding", "contracting", "stable"
    atr_percentile: float  # 0.0 ~ 1.0 (최근 60일 대비)
    atr_trend: float  # ATR 변화율

def calculate_volatility_multiplier(regime: VolatilityRegime) -> float:
    """변동성 기반 임계값 배율 계산"""

    if regime.type == "expanding":
        # 변동성 확장 → 엄격한 기준
        return 1.0  # +300% 유지

    elif regime.type == "contracting":
        # 변동성 수축 → 완화된 기준
        # +300% → +210% 완화
        return 0.7

    elif regime.type == "stable":
        # 안정 구간 → 중간 기준
        return 0.85  # +255%

    return 1.0
```

**논리**:
- Contracting 구간: BTC 횡보 시 +300% 불가능 → +210%로 완화
- Expanding 구간: 큰 움직임 가능 → +300% 엄격 유지
- Stable 구간: 중간값 적용

#### 14.2.2 최근 트레이드 분포 기반 조정

```python
def calculate_distribution_multiplier(
    recent_trades: List[TradeResult],
    lookback_count: int = 20,
) -> float:
    """실제 트레이드 결과 기반 임계값 조정"""

    if len(recent_trades) < 10:
        # 데이터 부족 → 기본값
        return 1.0

    # 최근 20개 트레이드의 R 분포
    wins = [t.r_multiple for t in recent_trades if t.r_multiple > 0]

    if not wins:
        # 승리 없음 → 완화
        return 0.8

    # 상위 10% 실제 R
    top_10_pct = sorted(wins, reverse=True)[:max(1, len(wins) // 10)]
    actual_tail_avg = sum(top_10_pct) / len(top_10_pct)

    if actual_tail_avg < 2.0:
        # 실제로 +200%도 못 만듦 → 대폭 완화
        return 0.6
    elif actual_tail_avg < 3.0:
        # +300% 미달 → 소폭 완화
        return 0.8
    elif actual_tail_avg > 5.0:
        # +500% 이상 달성 → 엄격 강화
        return 1.2

    return 1.0
```

**논리**:
- 실제로 +300% 만들고 있으면 → 기준 유지/강화
- 실제로 +200%도 못 만들면 → 기준 완화 (진입 기회 확보)

#### 14.2.3 Drawdown 상태 기반 조정

```python
def calculate_drawdown_multiplier(
    current_balance: float,
    starting_balance: float,
    drawdown_pct: float,
) -> float:
    """Drawdown 상태에 따른 임계값 조정"""

    if drawdown_pct < 0.10:
        # 경미한 DD (-10% 미만) → 기본값
        return 1.0

    elif drawdown_pct < 0.30:
        # 중간 DD (-30% 미만) → 소폭 완화
        # 복구 위해 기회 필요
        return 0.9

    elif drawdown_pct < 0.50:
        # 심각한 DD (-50% 미만) → 대폭 완화
        # -50% → 복구 위해 +100% 필요
        # 하지만 +300% 기준 유지 시 진입 불가
        return 0.7

    else:
        # 치명적 DD (-50% 이상) → 최대 완화
        # 청산 직전 → 어떻게든 기회 필요
        return 0.5
```

**논리**:
- DD 클수록 복구 절박 → 임계값 완화
- 하지만 **최소 품질은 유지** (0.5 = +150% 최소)

#### 14.2.4 최종 임계값 계산

```python
def calculate_dynamic_threshold(
    base_r_win: float,
    volatility_regime: VolatilityRegime,
    recent_trades: List[TradeResult],
    drawdown_pct: float,
) -> float:
    """
    동적 EV 임계값 계산

    Returns:
        조정된 R_win 임계값
    """

    vol_mult = calculate_volatility_multiplier(volatility_regime)
    dist_mult = calculate_distribution_multiplier(recent_trades)
    dd_mult = calculate_drawdown_multiplier(current_balance, starting_balance, drawdown_pct)

    # 최종 배율 (최소 0.5, 최대 1.5)
    final_mult = max(0.5, min(1.5, vol_mult * dist_mult * dd_mult))

    # 조정된 임계값
    adjusted_r_win = base_r_win * final_mult

    return adjusted_r_win
```

**예시**:
```python
# 시나리오 1: 정상 상태
vol_mult = 1.0  # Expanding
dist_mult = 1.0  # 최근 +300% 달성
dd_mult = 1.0   # DD < 10%
→ R_win = 3.0 * 1.0 = +300% (기본값 유지)

# 시나리오 2: 변동성 수축 + 깊은 DD
vol_mult = 0.7  # Contracting
dist_mult = 0.8  # 최근 +250% 수준
dd_mult = 0.7   # DD -40%
→ R_win = 3.0 * 0.39 = +117% (대폭 완화)

# 시나리오 3: 변동성 확장 + 높은 실제 성과
vol_mult = 1.0  # Expanding
dist_mult = 1.2  # 최근 +500% 달성
dd_mult = 1.0   # DD < 10%
→ R_win = 3.0 * 1.2 = +360% (엄격 강화)
```

### 14.3 EVFullValidator에 적용

```python
class EVFullValidator:
    BASE_R_WIN = 3.0  # 기본 +300%
    BASE_WIN_PROB = 0.10
    BASE_TAIL_PROFIT = 5.0

    def validate(
        self,
        intent: TradeIntent,
        risk_permission: RiskPermission,
        account: AccountMetrics,
        market_regime: MarketRegime,  # 추가
        recent_trades: List[TradeResult],  # 추가
    ) -> EVFullResult:
        # 동적 임계값 계산
        dynamic_r_win = calculate_dynamic_threshold(
            base_r_win=self.BASE_R_WIN,
            volatility_regime=market_regime.volatility,
            recent_trades=recent_trades,
            drawdown_pct=account.drawdown_pct,
        )

        # 시뮬레이션
        outcomes = self._simulate_outcomes(intent, risk_permission, account)

        # 동적 기준 적용
        wins = [o for o in outcomes if o.pnl > 0]
        R_win = mean([w.pnl_pct for w in wins])

        if R_win < dynamic_r_win:
            return FAIL(
                reason=f"r_insufficient: {R_win:.1f} < {dynamic_r_win:.1f}",
                threshold_used=dynamic_r_win,
            )

        # ... 나머지 검증
```

### 14.4 Threshold 로깅 및 추적

```python
@dataclass
class EVDecisionLog:
    # 기존 필드 + 동적 임계값 추가
    threshold_r_win: float  # 사용된 R_win 임계값
    threshold_multiplier: float  # 적용된 배율
    volatility_regime: str
    recent_trade_count: int
    drawdown_pct: float
```

**이유**:
- 임계값이 동적으로 변하므로 **어떤 기준이 사용되었는지 기록 필수**
- 사후 분석 시 "왜 이 트레이드가 PASS/FAIL 됐는가" 판단 가능

### 14.5 동적 임계값의 철학

**정적 임계값**:
> "+300%는 절대 기준이다."

**동적 임계값**:
> "+300%는 '정상 시장'의 기준이다.
> 시장이 비정상이면 기준도 변한다.
> 하지만 최소 품질은 유지한다."

**핵심 원칙**:
1. **환경 적응**: 시장 변화에 기준 조정
2. **최소 품질 보장**: 아무리 완화해도 +150% 이상
3. **사후 검증 가능**: 모든 임계값 로깅

---

## 15. 이 문서의 최종 선언

### v1 선언 (유지)
> **이 시스템은
> '가능성'을 믿지 않는다.
> '수치'를 믿는다.**

> **+300%를 만들 수 없는 전략은
> 아무리 안전해도
> Account Builder가 아니다.**

### v2 추가
> **그리고 그 검증을
> 2단계로 나눠서
> 성능 저하 없이 강제한다.**

---

## 15. BASE_ARCHITECTURE.md와의 관계

이 문서는:
- **구조를 결정하지 않는다** (BASE가 결정)
- **수학적 기준만 정의한다**
- EVPrefilter, EVFullValidator 클래스의 명세서

BASE_ARCHITECTURE.md가 "어디서 호출"을 정의하면,
이 문서는 "무엇을 계산"을 정의한다.

**역할 분리 명확.**
