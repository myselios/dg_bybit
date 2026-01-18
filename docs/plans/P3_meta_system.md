# P3 Meta System — 자기 진단 및 전략 평가 (v3.0 목표)

## 목적

**시스템이 스스로를 판단하고, 필요시 전략을 교체합니다.**

v2.3에서 학습 능력이 추가된 후, **메타 레이어**를 구축합니다.

P0 + P1 + P2가 100% 완료된 후 시작합니다.

---

## ⚠️ 중요: 이 단계는 "계좌 점프" 이후 고려

Account Builder의 목표는 **계좌 점프**입니다.

- v2.2 (P0 + P1): 청산 방지 + 핵심 기능
- v2.3 (P2): 학습 능력
- **v3.0 (P3): 메타 능력 (선택)**

**P3는 필수가 아닙니다.**

> **철학**:
> 계좌가 10배 성장하지 못했다면,
> 전략 교체보다 **리스크 검토**가 먼저입니다.

---

## 🔮 Meta Issue 1: Strategy Validity Assessment

### 현재 상태
- Strategy 고정 (EMA200 + Volatility Expansion)
- 성과가 나쁘면 → 수동으로 판단

### 문제
"이 전략이 아직 유효한가?"를 판단하는 로직이 없습니다.

**예시**:
- 20 트레이드, 승률 5%, 평균 R -0.5 → **전략 실패**
- 하지만 시스템은 계속 진입 시도

### 해야 할 것
- [ ] `StrategyEvaluator` 클래스 구현
  ```python
  class StrategyEvaluator:
      def evaluate_strategy(
          self, trades: List[TradeResult], min_sample: int = 20
      ) -> StrategyEvaluation:
          """
          전략 유효성 평가

          기준:
          1. 최소 샘플 20개 이상
          2. 평균 R > 0 (최소한 손익분기)
          3. 상위 10% 평균 R > +3.0 (tail 존재)
          4. 최대 연속 손실 < 10회

          실패 시 → STRATEGY_INVALID
          """
          if len(trades) < min_sample:
              return StrategyEvaluation(
                  valid=True,
                  reason="insufficient_sample",
              )

          avg_r = np.mean([t.r_multiple for t in trades])
          top_10pct = sorted(trades, key=lambda t: t.r_multiple, reverse=True)[
              :int(len(trades) * 0.1)
          ]
          avg_tail_r = np.mean([t.r_multiple for t in top_10pct])
          max_consecutive_loss = self._calculate_max_consecutive_loss(trades)

          # 실패 조건
          if avg_r < 0:
              return StrategyEvaluation(
                  valid=False,
                  reason="negative_avg_r",
                  metric=avg_r,
              )

          if avg_tail_r < 3.0:
              return StrategyEvaluation(
                  valid=False,
                  reason="tail_insufficient",
                  metric=avg_tail_r,
              )

          if max_consecutive_loss > 10:
              return StrategyEvaluation(
                  valid=False,
                  reason="excessive_consecutive_loss",
                  metric=max_consecutive_loss,
              )

          return StrategyEvaluation(
              valid=True,
              reason="all_criteria_passed",
          )
  ```

- [ ] 주기적 평가 스케줄러
  ```python
  # 20 트레이드마다 평가
  def evaluate_strategy_periodically():
      trades = decision_log.get_all_trades()

      if len(trades) % 20 == 0:
          evaluation = strategy_evaluator.evaluate_strategy(trades)

          if not evaluation.valid:
              logger.critical(
                  f"Strategy invalid: {evaluation.reason} "
                  f"({evaluation.metric})"
              )

              # TERMINATED로 전환
              state_machine.force_terminate(
                  reason=f"strategy_invalid_{evaluation.reason}"
              )
  ```

- [ ] State Machine 연결
  ```python
  # EXECUTION_EVENTS.md 추가: STRATEGY_INVALID 이벤트

  ENTRY + STRATEGY_INVALID → TERMINATED
  MONITORING + STRATEGY_INVALID → TERMINATED

  조건:
  - 20 트레이드 평가 실패 → 강제 종료
  ```

### 완료 기준
- [ ] StrategyEvaluator 클래스 구현
- [ ] 주기적 평가 스케줄러 구현
- [ ] State Machine STRATEGY_INVALID 이벤트 연결
- [ ] 테스트: 평균 R < 0 (20 샘플) → TERMINATED
- [ ] 로그: StrategyEvaluationLog 기록

---

## 🔮 Meta Issue 2: Self-Adjusting Thresholds

### 현재 상태
- DecisionOutcome 기반 임계값 조정 (P1)
- ThresholdAdjuster 구현됨
- **하지만 조정 범위가 고정 (±5%, ±10%)**

### 문제
시장 환경에 따라 **최적 조정폭이 다릅니다.**

**예시**:
- 변동성 높은 시장: ±10% 조정 적절
- 변동성 낮은 시장: ±5% 조정만 안전

### 해야 할 것
- [ ] `AdaptiveAdjuster` 클래스 구현
  ```python
  class AdaptiveAdjuster:
      def calculate_adjustment_magnitude(
          self,
          recent_outcomes: List[DecisionOutcome],
          volatility_regime: VolatilityRegime,
      ) -> float:
          """
          시장 regime에 따라 조정 폭 결정

          - EXPANSION: 크게 조정 (±15%)
          - CONTRACTION: 작게 조정 (±3%)
          - NORMAL: 표준 조정 (±5%)
          """
          base_magnitude = {
              VolatilityRegime.EXPANSION: 0.15,
              VolatilityRegime.CONTRACTION: 0.03,
              VolatilityRegime.NORMAL: 0.05,
          }[volatility_regime]

          # Outcome confidence 기반 조정
          confidence = self._calculate_confidence(recent_outcomes)
          adjusted_magnitude = base_magnitude * confidence

          return adjusted_magnitude

      def _calculate_confidence(
          self, outcomes: List[DecisionOutcome]
      ) -> float:
          """
          Outcome 일관성 → confidence

          - learning_tag 일치율 높음 → confidence 높음
          - 일치율 낮음 → confidence 낮음
          """
          if len(outcomes) < 5:
              return 0.5  # 낮은 신뢰

          tag_counts = Counter(o.learning_tag for o in outcomes)
          max_count = max(tag_counts.values())
          consistency = max_count / len(outcomes)

          return min(1.0, consistency)
  ```

- [ ] `ThresholdAdjuster` 업그레이드
  ```python
  class ThresholdAdjuster:
      def __init__(self):
          self.adaptive_adjuster = AdaptiveAdjuster()

      def adjust_based_on_outcomes(
          self,
          recent_outcomes: List[DecisionOutcome],
          volatility_regime: VolatilityRegime,
      ) -> ThresholdAdjustment:
          missed_count = sum(
              1 for o in recent_outcomes
              if o.learning_tag == "missed_opportunity"
          )

          # 동적 조정폭 계산
          magnitude = self.adaptive_adjuster.calculate_adjustment_magnitude(
              recent_outcomes, volatility_regime
          )

          if missed_count >= 3:
              multiplier = 1.0 - magnitude  # 완화
              reason = f"missed_opportunities_{magnitude:.1%}_relax"
          elif ...:
              multiplier = 1.0 + magnitude  # 강화
              reason = ...
          else:
              multiplier = 1.0
              reason = "stable"

          return ThresholdAdjustment(
              multiplier=multiplier,
              reason=reason,
              magnitude=magnitude,
          )
  ```

### 완료 기준
- [ ] AdaptiveAdjuster 클래스 구현
- [ ] ThresholdAdjuster regime-aware 업그레이드
- [ ] 테스트: EXPANSION → ±15% 조정
- [ ] 테스트: CONTRACTION → ±3% 조정
- [ ] 로그: ThresholdAdjustmentLog에 magnitude 기록

---

## 🔮 Meta Issue 3: Position Sizing Learning

### 현재 상태
- Position Size 고정 (POSITION_MODEL.md 규칙)
- Risk per trade 고정

### 문제
계좌 성장 시 **사이징 전략도 변해야 합니다.**

**예시**:
- 계좌 100 USD → 공격적 (5% risk)
- 계좌 1,000 USD → 보수적 (2% risk)

### 해야 할 것
- [ ] `DynamicSizer` 클래스 구현
  ```python
  class DynamicSizer:
      def calculate_risk_pct(
          self, account_equity: float, peak_equity: float
      ) -> float:
          """
          계좌 규모에 따라 risk per trade 조정

          규칙:
          - equity < 500 USD: 5% (공격)
          - equity 500~2000 USD: 3% (중립)
          - equity > 2000 USD: 2% (보수)
          """
          if account_equity < 500:
              return 0.05
          elif account_equity < 2000:
              return 0.03
          else:
              return 0.02
  ```

- [ ] `PositionSizer`에 통합
  ```python
  class PositionSizer:
      def __init__(self):
          self.dynamic_sizer = DynamicSizer()

      def calculate_size(
          self,
          account_equity: float,
          peak_equity: float,
          entry_price: float,
          stop_loss: float,
      ) -> PositionSize:
          # 동적 risk
          risk_pct = self.dynamic_sizer.calculate_risk_pct(
              account_equity, peak_equity
          )

          risk_usd = account_equity * risk_pct
          loss_per_contract = abs(entry_price - stop_loss)
          quantity = risk_usd / loss_per_contract

          return PositionSize(
              quantity=quantity,
              risk_pct=risk_pct,
              risk_usd=risk_usd,
          )
  ```

### 완료 기준
- [ ] DynamicSizer 클래스 구현
- [ ] PositionSizer 통합
- [ ] 테스트: equity 100 → 5% risk
- [ ] 테스트: equity 1000 → 3% risk
- [ ] 로그: PositionSizeLog에 risk_pct 기록

---

## 🔮 Meta Issue 4: Multi-Strategy Portfolio

### 현재 상태
- 단일 전략 (EMA200 + Volatility)
- 전략 교체 = 시스템 재시작

### 문제 (장기 비전)
**여러 전략을 동시 운영하고, 성과에 따라 자원 배분**

**예시**:
- Strategy A: EMA200 + Volatility (70% 자본)
- Strategy B: Bollinger Breakout (30% 자본)
- A 실패 → B로 자본 이동

### 해야 할 것 (v4.0 고려 사항)
- [ ] `StrategyRegistry` 클래스
  ```python
  class StrategyRegistry:
      def __init__(self):
          self.strategies: Dict[str, Strategy] = {}
          self.allocations: Dict[str, float] = {}

      def register(self, name: str, strategy: Strategy, allocation: float):
          self.strategies[name] = strategy
          self.allocations[name] = allocation

      def rebalance(self, performance: Dict[str, float]):
          """성과 기반 자본 재배분"""
          ...
  ```

**현재는 설계만 (구현 보류)**

---

## 🔮 Meta Issue 5: Drawdown Recovery Mode

### 현재 상태
- Drawdown -50% → TERMINATED (P0)
- 중간 DD (-20% ~ -50%)는 대응 없음

### 문제
**DD -30% 구간에서 회복 전략 필요**

**예시**:
- DD -30% → 포지션 사이즈 50% 축소
- DD -40% → 진입 조건 강화 (EV +400% 요구)

### 해야 할 것
- [ ] `RecoveryMode` 클래스 구현
  ```python
  class RecoveryMode:
      def check_recovery_mode(self, drawdown_pct: float) -> RecoveryAction:
          """
          Drawdown 구간별 대응

          - DD < -20%: 정상
          - DD -20% ~ -30%: 사이즈 축소 (50%)
          - DD -30% ~ -40%: 사이즈 축소 (30%) + EV 강화 (+400%)
          - DD -40% ~ -50%: 진입 금지
          - DD > -50%: TERMINATED
          """
          if drawdown_pct > -0.20:
              return RecoveryAction(mode="NORMAL")
          elif drawdown_pct > -0.30:
              return RecoveryAction(
                  mode="MILD_RECOVERY",
                  size_reduction=0.5,
              )
          elif drawdown_pct > -0.40:
              return RecoveryAction(
                  mode="AGGRESSIVE_RECOVERY",
                  size_reduction=0.3,
                  ev_threshold_mult=1.33,  # +300% → +400%
              )
          elif drawdown_pct > -0.50:
              return RecoveryAction(mode="ENTRY_FREEZE")
          else:
              return RecoveryAction(mode="TERMINATED")
  ```

- [ ] State Machine 연결
  ```python
  # TradingOrchestrator 메인 루프
  def run(self):
      while True:
          dd = self.drawdown_monitor.get_current_dd()
          recovery = self.recovery_mode.check_recovery_mode(dd)

          if recovery.mode == "ENTRY_FREEZE":
              # MONITORING 상태만 유지
              continue

          if recovery.mode in ["MILD_RECOVERY", "AGGRESSIVE_RECOVERY"]:
              # PositionSizer, EVValidator 조정
              self.position_sizer.set_size_multiplier(recovery.size_reduction)
              if recovery.ev_threshold_mult:
                  self.ev_validator.set_threshold_multiplier(
                      recovery.ev_threshold_mult
                  )
  ```

### 완료 기준
- [ ] RecoveryMode 클래스 구현
- [ ] TradingOrchestrator 통합
- [ ] 테스트: DD -25% → 사이즈 50%
- [ ] 테스트: DD -35% → 사이즈 30% + EV +400%
- [ ] 로그: RecoveryModeLog 기록

---

## P3 전체 완료 조건

**이 5개 항목은 "선택"입니다. Account Builder 성공 후 고려.**

- [ ] Strategy Validity Assessment
- [ ] Self-Adjusting Thresholds (adaptive magnitude)
- [ ] Position Sizing Learning
- [ ] Multi-Strategy Portfolio (설계만)
- [ ] Drawdown Recovery Mode

### 검증 방법
1. **6개월 Paper Trading**: 전략 평가 1회 이상
2. **Adaptive Adjustment**: regime 전환 시 조정폭 변화 확인
3. **Recovery Mode**: DD -30% 도달 → 사이즈 축소 확인

### 예상 일정
**2~3개월 (계좌 점프 후)**

---

## 최종 선언

P3는 **Account Builder의 다음 단계**입니다.

> **순서**:
> 1. v2.2 (P0 + P1): 청산 방지 + 수익 발생
> 2. v2.3 (P2): 학습 능력
> 3. **계좌 점프 확인**
> 4. v3.0 (P3): 메타 시스템 (선택)

계좌가 10배 성장하지 못했다면,
P3 대신 **P0 재검토**가 답입니다.
