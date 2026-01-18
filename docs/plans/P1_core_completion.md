# P1 Core Completion — 핵심 기능 완성 (v2.2 목표)

## 목적

**이것들이 없으면 수익이 발생하지 않습니다.**

v2.1에서 구조는 설계되었으나, **실제 동작과 학습 능력이 누락된 항목들**을 완성합니다.

P0 (청산 방지)가 100% 완료된 후 시작합니다.

---

## 🔧 Core Issue 1: EV Framework Cold Start 문제

### 현재 상태
- EV_FRAMEWORK.md 14절에 동적 임계값 공식 있음
- `calculate_dynamic_threshold()` 함수 정의됨
- **하지만 "처음 10개 트레이드는 어떻게?"에 대한 답 없음**

### 문제
```python
# EV_FRAMEWORK.md 14.3
def calculate_dynamic_threshold(
    base_r_win: float,
    volatility_regime: VolatilityRegime,
    recent_trades: List[TradeResult],  # ← 처음엔 비어있음
    drawdown_pct: float,
) -> float:
    ...
```

처음 10개 트레이드는 `recent_trades`가 충분하지 않아 통계적으로 무의미합니다.

### 해야 할 것
- [ ] EV_FRAMEWORK.md 14.4 "Cold Start 정책" 섹션 추가
  ```markdown
  ## 14.4 Cold Start 정책 (초기 10 트레이드)

  ### 문제
  - 동적 임계값은 `recent_trades` 통계 필요
  - 처음 10개는 통계 불충분

  ### 해결
  초기 10 트레이드는 **완화된 고정 임계값** 사용:

  ```python
  def get_threshold(trade_count: int, ...) -> float:
      if trade_count < 10:
          # 초기 완화: +255% (0.85 multiplier)
          return 3.0 * 0.85  # = +255%
      else:
          # 동적 계산
          return calculate_dynamic_threshold(...)
  ```

  ### 근거
  1. 초기에는 **더 많은 기회 허용** (학습 우선)
  2. 10개 이후부터 통계적 유의성 확보
  3. 여전히 +255% 이상 요구 (과도한 완화 아님)
  ```

- [ ] `EVValidator.validate()` 구현 수정
  ```python
  class EVFullValidator:
      def validate(self, intent: TradeIntent) -> EVResult:
          trade_count = self.decision_log.count_total_trades()

          if trade_count < 10:
              threshold = 3.0 * 0.85  # +255%
              metadata = {"cold_start": True}
          else:
              threshold = self.threshold_calculator.calculate_dynamic(...)
              metadata = {"cold_start": False}

          ev_result = self.monte_carlo.calculate_ev(intent)

          if ev_result.r_win < threshold:
              return FAIL(
                  reason="ev_below_threshold",
                  required=threshold,
                  actual=ev_result.r_win,
                  metadata=metadata,
              )
  ```

- [ ] EVDecisionLog에 cold_start 플래그 추가
  ```python
  @dataclass
  class EVDecisionLog:
      ...
      cold_start: bool  # True면 고정 임계값 사용
      threshold_used: float  # 실제 사용된 임계값 기록
  ```

### 완료 기준
- [ ] EV_FRAMEWORK.md 14.4 섹션 추가
- [ ] EVValidator cold start 로직 구현
- [ ] 테스트: 첫 10개 트레이드는 +255% 임계값 사용 확인
- [ ] 테스트: 11번째부터 동적 임계값 사용 확인
- [ ] 로그: EVDecisionLog에 cold_start, threshold_used 기록

---

## 🔧 Core Issue 2: DecisionOutcome opportunity_cost 누락

### 현재 상태
- DECISION_LOG.md 9절에 `DecisionOutcome` 클래스 있음
- `regret_score`, `learning_tag` 정의됨
- **하지만 "거절한 신호가 실제로 +300% 갔는지" 추적 안 함**

### 문제
```python
# DECISION_LOG.md 9.1
@dataclass
class DecisionOutcome:
    decision_id: str
    decision_type: str

    short_term_r: float
    mid_term_r: float
    long_term_r: float

    regret_score: float
    learning_tag: str  # "good_denial", "missed_opportunity", ...
```

**"거절한 진입이 실제로 성공했는지"를 계산하는 로직이 없습니다.**

### 해야 할 것
- [ ] DECISION_LOG.md 9.2 "Opportunity Cost 계산" 섹션 추가
  ```markdown
  ## 9.2 Opportunity Cost 계산

  ### 정의
  "만약 이 신호를 받아들였다면 얼마를 벌었을까?"

  ### 계산 로직
  ```python
  def calculate_opportunity_cost(
      rejected_intent: TradeIntent,
      time_horizon: timedelta,
  ) -> OpportunityCost:
      """
      거절한 신호의 counterfactual R 계산

      1. 거절 시점 가격 기록
      2. time_horizon 후 가격 확인
      3. 가상 트레이드 R 계산
      """
      entry_price = rejected_intent.entry_price
      exit_price = get_price_at(
          rejected_intent.timestamp + time_horizon
      )

      # 가상 손익 계산
      counterfactual_r = calculate_r_multiple(
          entry_price, exit_price, rejected_intent.side
      )

      return OpportunityCost(
          rejected_intent_id=rejected_intent.id,
          counterfactual_r=counterfactual_r,
          time_horizon=time_horizon,
      )
  ```

  ### DecisionOutcome 통합
  ```python
  @dataclass
  class DecisionOutcome:
      ...
      # 추가 필드
      opportunity_cost: OpportunityCost | None  # REJECT 결정만
      counterfactual_r: float | None  # 거절 신호의 가상 R
  ```
  ```

- [ ] `DecisionEvaluator` 클래스 구현
  ```python
  class DecisionEvaluator:
      def evaluate_rejection(
          self,
          decision: StateDecisionLog,
          time_horizon: timedelta = timedelta(days=7),
      ) -> DecisionOutcome:
          """
          거절 결정의 사후 평가

          1. 7일 후 가격 확인
          2. Counterfactual R 계산
          3. Regret score 계산
          4. Learning tag 부여
          """
          if decision.action != "REJECT":
              return None

          opp_cost = self.calculate_opportunity_cost(
              rejected_intent=decision.trade_intent,
              time_horizon=time_horizon,
          )

          # Regret score: 놓친 기회가 클수록 1.0
          regret = min(1.0, max(0.0, opp_cost.counterfactual_r / 5.0))

          # Learning tag
          if opp_cost.counterfactual_r > 3.0:
              tag = "missed_opportunity"  # 놓친 큰 기회
          elif opp_cost.counterfactual_r < 0:
              tag = "good_denial"  # 잘한 거절
          else:
              tag = "neutral"

          return DecisionOutcome(
              decision_id=decision.id,
              opportunity_cost=opp_cost,
              counterfactual_r=opp_cost.counterfactual_r,
              regret_score=regret,
              learning_tag=tag,
          )
  ```

- [ ] 자동 평가 스케줄러
  ```python
  # 매일 1회 실행
  def daily_decision_evaluation():
      recent_rejections = decision_log.get_rejections_7days_ago()

      for rejection in recent_rejections:
          outcome = evaluator.evaluate_rejection(rejection)
          decision_log.save_outcome(outcome)
  ```

### 완료 기준
- [ ] DECISION_LOG.md 9.2 섹션 추가
- [ ] OpportunityCost 계산 로직 구현
- [ ] DecisionEvaluator 클래스 구현
- [ ] 자동 평가 스케줄러 구현
- [ ] 테스트: 거절 7일 후 counterfactual R 계산 확인
- [ ] 로그: DecisionOutcome에 opportunity_cost 기록

---

## 🔧 Core Issue 3: 학습 루프 자동화

### 현재 상태
- DecisionOutcome 구조 있음
- 동적 EV 임계값 공식 있음
- **하지만 "DecisionOutcome → 임계값 조정" 자동 연결 없음**

### 문제
DecisionOutcome이 쌓여도, **스스로 임계값을 조정하지 않습니다.**

### 해야 할 것
- [ ] `ThresholdAdjuster` 클래스 구현
  ```python
  class ThresholdAdjuster:
      def adjust_based_on_outcomes(
          self,
          recent_outcomes: List[DecisionOutcome],
      ) -> ThresholdAdjustment:
          """
          DecisionOutcome 분석 → 임계값 조정

          규칙:
          1. missed_opportunity 3회 이상 → 임계값 -5% 완화
          2. good_denial 연속 5회 → 임계값 +10% 강화
          3. 중립 → 유지
          """
          missed_count = sum(
              1 for o in recent_outcomes
              if o.learning_tag == "missed_opportunity"
          )
          good_denial_streak = self._count_consecutive(
              recent_outcomes, "good_denial"
          )

          if missed_count >= 3:
              return ThresholdAdjustment(
                  multiplier=0.95,
                  reason="too_many_missed_opportunities",
              )
          elif good_denial_streak >= 5:
              return ThresholdAdjustment(
                  multiplier=1.10,
                  reason="consistent_good_rejections",
              )
          else:
              return ThresholdAdjustment(multiplier=1.0, reason="stable")
  ```

- [ ] `EVValidator`에 통합
  ```python
  class EVFullValidator:
      def __init__(self):
          self.threshold_adjuster = ThresholdAdjuster()
          self.adjustment_multiplier = 1.0  # 초기값

      def validate(self, intent: TradeIntent) -> EVResult:
          base_threshold = self.threshold_calculator.calculate_dynamic(...)

          # 학습 기반 조정
          adjusted_threshold = base_threshold * self.adjustment_multiplier

          ...

      def update_from_outcomes(self):
          """주 1회 호출"""
          recent_outcomes = self.decision_log.get_outcomes_last_30_days()
          adjustment = self.threshold_adjuster.adjust_based_on_outcomes(
              recent_outcomes
          )

          self.adjustment_multiplier *= adjustment.multiplier

          logger.info(
              f"Threshold adjusted: {adjustment.multiplier:.2f} "
              f"({adjustment.reason})"
          )
  ```

- [ ] 주간 업데이트 스케줄러
  ```python
  # 매주 일요일 실행
  def weekly_threshold_update():
      ev_validator.update_from_outcomes()
  ```

### 완료 기준
- [ ] ThresholdAdjuster 클래스 구현
- [ ] EVValidator 학습 루프 통합
- [ ] 주간 업데이트 스케줄러 구현
- [ ] 테스트: missed_opportunity 3회 → 임계값 -5%
- [ ] 테스트: good_denial 5연속 → 임계값 +10%
- [ ] 로그: ThresholdAdjustmentLog에 multiplier, reason 기록

---

## 🔧 Core Issue 4: Strategy 방향성 필터 실제 구현

### 현재 상태
- STRATEGY.md에 "EMA200 4H 기준 Long만" 명시
- **실제 Feature Engine 구현 없음**

### 해야 할 것
- [ ] `FeatureEngine` 구현
  ```python
  class FeatureEngine:
      def calculate_ema200_4h(
          self, price_history: List[OHLCV]
      ) -> float:
          """4시간봉 EMA200 계산"""
          prices = [candle.close for candle in price_history[-200:]]
          return talib.EMA(prices, timeperiod=200)[-1]

      def calculate_atr_4h(
          self, price_history: List[OHLCV]
      ) -> float:
          """4시간봉 ATR 계산"""
          high = [c.high for c in price_history[-14:]]
          low = [c.low for c in price_history[-14:]]
          close = [c.close for c in price_history[-14:]]
          return talib.ATR(high, low, close, timeperiod=14)[-1]

      def get_features(
          self, symbol: str, timeframe: str = "4h"
      ) -> Features:
          """
          현재 시장 feature 계산

          Returns:
              Features(ema200, atr, price, ...)
          """
          history = self.market_data.get_ohlcv(symbol, timeframe, limit=250)

          return Features(
              ema200=self.calculate_ema200_4h(history),
              atr=self.calculate_atr_4h(history),
              current_price=history[-1].close,
              timestamp=history[-1].timestamp,
          )
  ```

- [ ] `DirectionalFilter` 구현
  ```python
  class DirectionalFilter:
      def check_direction(
          self, features: Features, intended_side: Side
      ) -> FilterResult:
          """
          STRATEGY.md 3.1 "방향성 필터" 구현

          Long 전용: price > EMA200
          """
          if intended_side == Side.SHORT:
              return FAIL("short_disabled")

          if features.current_price < features.ema200:
              return FAIL("price_below_ema200")

          return PASS()
  ```

- [ ] `Strategy`에 통합
  ```python
  class Strategy:
      def generate_signal(
          self, features: Features
      ) -> TradeIntent | None:
          # 1. 방향성 필터
          direction = self.directional_filter.check_direction(
              features, Side.LONG
          )
          if not direction.passed:
              return None

          # 2. 변동성 확장 감지
          expansion = self.volatility_filter.check_expansion(features)
          if not expansion.passed:
              return None

          # 3. TradeIntent 생성
          return TradeIntent(
              side=Side.LONG,
              entry_price=features.current_price,
              features=features,
          )
  ```

### 완료 기준
- [ ] FeatureEngine 구현 (EMA200, ATR 계산)
- [ ] DirectionalFilter 구현
- [ ] Strategy 통합
- [ ] 테스트: price < EMA200 → TradeIntent 생성 안 됨
- [ ] 테스트: price > EMA200 + 변동성 확장 → TradeIntent 생성

---

## 🔧 Core Issue 5: State Machine 기본 흐름 구현

### 현재 상태
- STATE_MACHINE.md에 9개 상태 정의
- EXECUTION_EVENTS.md에 9×9 전환 테이블
- **실제 StateMachine 클래스 구현 없음**

### 해야 할 것
- [ ] `StateMachine` 클래스 구현
  ```python
  class StateMachine:
      def __init__(self):
          self.current_state = State.IDLE
          self.transition_table = self._load_transition_table()

      def handle_event(
          self, event: ExecutionEvent
      ) -> StateTransition:
          """
          EXECUTION_EVENTS.md 3.1 전환 테이블 적용

          Returns:
              StateTransition(next_state, action, retry_count, ...)
          """
          key = (self.current_state, event)
          rule = self.transition_table.get(key)

          if not rule:
              logger.warning(f"Undefined transition: {key}")
              return StateTransition(
                  next_state=self.current_state,
                  action="HOLD",
              )

          # 조건 확인
          if rule.condition and not rule.condition():
              return StateTransition(
                  next_state=self.current_state,
                  action="HOLD",
              )

          # 상태 전환
          old_state = self.current_state
          self.current_state = rule.next_state

          # 로그 기록
          self.decision_log.log_state_transition(
              from_state=old_state,
              to_state=rule.next_state,
              event=event,
              reason=rule.reason,
          )

          return StateTransition(
              next_state=rule.next_state,
              action=rule.action,
              retry_count=rule.retry_count,
          )

      def _load_transition_table(self) -> Dict:
          """
          EXECUTION_EVENTS.md 3.1 테이블을 코드로 변환

          Example:
          {
              (State.ENTRY_PENDING, ExecutionEvent.FILLED): TransitionRule(
                  next_state=State.ENTRY,
                  action="LOG_ENTRY",
                  condition=None,
              ),
              (State.ENTRY, ExecutionEvent.LIQUIDATION_WARNING): TransitionRule(
                  next_state=State.EXIT_FAILURE,
                  action="EMERGENCY_EXIT",
                  condition=None,
              ),
              ...
          }
          """
          ...
  ```

- [ ] `TradingOrchestrator`에 통합
  ```python
  class TradingOrchestrator:
      def run(self):
          while True:
              # 1. Features 계산
              features = self.feature_engine.get_features("BTCUSD")

              # 2. Strategy 신호
              intent = self.strategy.generate_signal(features)

              # 3. State Machine 이벤트 처리
              if intent and self.state_machine.can_enter():
                  transition = self.state_machine.handle_event(
                      ExecutionEvent.ENTRY_SIGNAL
                  )

              # 4. Execution
              if transition.action == "SUBMIT_ORDER":
                  result = self.trading_engine.submit_order(...)
                  self.state_machine.handle_event(result.event)

              time.sleep(60)  # 1분 대기
  ```

### 완료 기준
- [ ] StateMachine 클래스 구현
- [ ] 9×9 전환 테이블 코드 변환
- [ ] TradingOrchestrator 메인 루프 구현
- [ ] 테스트: IDLE → MONITORING → ENTRY_PENDING → ENTRY 흐름 확인
- [ ] 로그: StateDecisionLog에 모든 전환 기록

---

## P1 전체 완료 조건

**이 5개 항목이 90% 이상 완료되어야 실제 수익 가능.**

- [ ] EV cold start 정책 구현 및 테스트
- [ ] DecisionOutcome opportunity_cost 계산 구현
- [ ] 학습 루프 자동화 (ThresholdAdjuster)
- [ ] Strategy 방향성 필터 구현 (FeatureEngine + DirectionalFilter)
- [ ] State Machine 기본 흐름 구현 (9×9 전환 테이블)

### 검증 방법
1. **백테스트**: 2023-2024 BTC 데이터로 신호 생성 확인
2. **Paper Trading**: 2주간 실행, EV 통과/차단 로그 분석
3. **DecisionOutcome 분석**: 최소 20개 수집, missed_opportunity 비율 확인

### 예상 일정
**2~3주차 목표**

---

## 이후 작업

P1 완료 후 → [P2_learning_system.md](P2_learning_system.md)
