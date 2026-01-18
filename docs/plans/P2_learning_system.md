# P2 Learning System — 학습 및 최적화 (v2.3 목표)

## 목적

**이것들이 없어도 작동하지만, 느리고 비효율적입니다.**

v2.2에서 핵심 기능이 완성된 후, **스스로 개선하고 적응하는 능력**을 추가합니다.

P0 + P1이 100% 완료된 후 시작합니다.

---

## 🎯 Learning Issue 1: State Machine Meta-Capability

### 현재 상태
- StateMachine 기본 흐름 구현됨 (P1)
- 9×9 전환 테이블 작동
- **하지만 "비정상 패턴 감지" 능력 없음**

### 문제
State Machine이 **운영자** 수준이지, **감독자** 수준이 아닙니다.

**예시**:
- ENTRY_PENDING이 2시간째 유지 중 → 이상 신호
- 5번 연속 EXIT_FAILURE → 전략 문제
- 같은 구간에서 3번 청산 경고 → 구조적 위험

**현재는 이런 패턴을 감지하지 못합니다.**

### 해야 할 것
- [ ] `StateHealthMonitor` 클래스 구현
  ```python
  class StateHealthMonitor:
      def check_state_health(
          self, state_history: List[StateTransition]
      ) -> HealthStatus:
          """
          State 전환 이력을 분석해 비정상 패턴 감지

          1. Duration Anomaly: 특정 상태가 너무 오래 유지
          2. Failure Streak: 연속 실패 패턴
          3. Oscillation: 같은 상태 반복 진입
          """
          issues = []

          # 1. Duration Anomaly
          current_duration = state_history[-1].duration
          if current_duration > timedelta(hours=2):
              issues.append(
                  HealthIssue(
                      type="duration_anomaly",
                      severity="warning",
                      message=f"State {state_history[-1].state} "
                              f"held for {current_duration}",
                  )
              )

          # 2. Failure Streak
          recent_exits = [
              t for t in state_history[-10:]
              if t.state == State.EXIT_FAILURE
          ]
          if len(recent_exits) >= 5:
              issues.append(
                  HealthIssue(
                      type="failure_streak",
                      severity="critical",
                      message=f"5 consecutive failures detected",
                  )
              )

          # 3. Oscillation
          state_counts = Counter(t.state for t in state_history[-20:])
          max_count = max(state_counts.values())
          if max_count > 8:  # 20개 중 8번 이상 같은 상태
              issues.append(
                  HealthIssue(
                      type="state_oscillation",
                      severity="warning",
                      message=f"Excessive oscillation detected",
                  )
              )

          if issues:
              return HealthStatus(healthy=False, issues=issues)
          else:
              return HealthStatus(healthy=True, issues=[])
  ```

- [ ] `StateMachine`에 통합
  ```python
  class StateMachine:
      def __init__(self):
          ...
          self.health_monitor = StateHealthMonitor()

      def handle_event(self, event: ExecutionEvent) -> StateTransition:
          transition = ...  # 기존 로직

          # Health check
          health = self.health_monitor.check_state_health(
              self.state_history
          )

          if not health.healthy:
              for issue in health.issues:
                  logger.warning(f"State health issue: {issue}")

                  if issue.severity == "critical":
                      # 강제 종료
                      self.force_transition(State.COOLDOWN)

          return transition
  ```

- [ ] Anomaly 대응 정책
  ```python
  # EXECUTION_EVENTS.md 추가 섹션: "3.3 Health-based 전환"

  Duration Anomaly:
  - ENTRY_PENDING > 2h → MONITORING (재진입 포기)
  - EXPANSION_PENDING > 1h → ENTRY (확장 포기)

  Failure Streak:
  - EXIT_FAILURE 5연속 → COOLDOWN (24h 대기)

  Oscillation:
  - MONITORING ↔ ENTRY_PENDING 8회 → COOLDOWN (전략 재검토)
  ```

### 완료 기준
- [ ] StateHealthMonitor 클래스 구현
- [ ] StateMachine health check 통합
- [ ] Anomaly 대응 정책 정의 (EXECUTION_EVENTS.md 3.3)
- [ ] 테스트: ENTRY_PENDING 2시간 → MONITORING 전환
- [ ] 테스트: EXIT_FAILURE 5연속 → COOLDOWN 전환
- [ ] 로그: HealthIssueLog에 type, severity, action 기록

---

## 🎯 Learning Issue 2: Regime-Aware EV Adjustment

### 현재 상태
- 동적 EV 임계값 구현됨 (P1)
- `calculate_dynamic_threshold()` 함수 작동
- **하지만 "시장 regime" 자동 감지 없음**

### 문제
EV_FRAMEWORK.md 14.2에 VolatilityRegime 있지만, **사람이 수동으로 지정해야 합니다.**

```python
# 현재
regime = VolatilityRegime.NORMAL  # ← 수동 지정

threshold = calculate_dynamic_threshold(
    base_r_win=3.0,
    volatility_regime=regime,  # ← 항상 NORMAL
    ...
)
```

### 해야 할 것
- [ ] `RegimeDetector` 클래스 구현
  ```python
  class RegimeDetector:
      def detect_regime(
          self, atr_history: List[float]
      ) -> VolatilityRegime:
          """
          최근 14일 ATR 변화율로 regime 판정

          1. ATR 증가 > 20% → EXPANSION
          2. ATR 감소 > 20% → CONTRACTION
          3. 그 외 → NORMAL
          """
          current_atr = atr_history[-1]
          avg_atr_14d = np.mean(atr_history[-14:])
          change_pct = (current_atr - avg_atr_14d) / avg_atr_14d

          if change_pct > 0.20:
              return VolatilityRegime.EXPANSION
          elif change_pct < -0.20:
              return VolatilityRegime.CONTRACTION
          else:
              return VolatilityRegime.NORMAL
  ```

- [ ] `ThresholdCalculator`에 통합
  ```python
  class ThresholdCalculator:
      def __init__(self):
          self.regime_detector = RegimeDetector()

      def calculate_dynamic_threshold(
          self,
          base_r_win: float,
          recent_trades: List[TradeResult],
          drawdown_pct: float,
          atr_history: List[float],  # ← 추가
      ) -> float:
          # 자동 regime 감지
          regime = self.regime_detector.detect_regime(atr_history)

          vol_mult = self._calculate_volatility_multiplier(regime)
          dist_mult = self._calculate_distribution_multiplier(recent_trades)
          dd_mult = self._calculate_drawdown_multiplier(drawdown_pct)

          final_mult = max(0.5, min(1.5, vol_mult * dist_mult * dd_mult))
          adjusted_r_win = base_r_win * final_mult

          logger.info(
              f"Threshold: {adjusted_r_win:.2f} "
              f"(regime={regime}, vol={vol_mult:.2f}, "
              f"dist={dist_mult:.2f}, dd={dd_mult:.2f})"
          )

          return adjusted_r_win
  ```

- [ ] EV_FRAMEWORK.md 14.2 업데이트
  ```markdown
  ## 14.2 Volatility Regime 자동 감지

  ### Regime 정의
  - **EXPANSION**: ATR 증가 > 20% (14일 기준)
  - **CONTRACTION**: ATR 감소 > 20%
  - **NORMAL**: 그 외

  ### 임계값 영향
  - EXPANSION: 기회 많음 → 기준 유지 (1.0x)
  - CONTRACTION: 기회 적음 → 기준 완화 (0.7x)
  - NORMAL: 표준 (1.0x)

  ### 자동 적용
  ```python
  regime = regime_detector.detect_regime(atr_history)
  vol_mult = {
      VolatilityRegime.EXPANSION: 1.0,
      VolatilityRegime.CONTRACTION: 0.7,
      VolatilityRegime.NORMAL: 1.0,
  }[regime]
  ```
  ```

### 완료 기준
- [ ] RegimeDetector 클래스 구현
- [ ] ThresholdCalculator regime 자동 감지 통합
- [ ] EV_FRAMEWORK.md 14.2 업데이트 (자동 감지 로직 추가)
- [ ] 테스트: ATR 증가 > 20% → EXPANSION 감지
- [ ] 테스트: CONTRACTION → 임계값 0.7x 완화
- [ ] 로그: EVDecisionLog에 detected_regime 기록

---

## 🎯 Learning Issue 3: Feature Engine 캐싱

### 현재 상태
- FeatureEngine 구현됨 (P1)
- EMA200, ATR 계산 작동
- **하지만 매번 250개 캔들 다시 계산**

### 문제
```python
# 현재 (비효율)
def get_features(self, symbol: str) -> Features:
    history = self.market_data.get_ohlcv(symbol, "4h", limit=250)
    ema200 = talib.EMA(...)  # ← 매번 250개 계산
    atr = talib.ATR(...)
    return Features(ema200, atr, ...)
```

매 루프마다 동일한 계산 반복 → 불필요한 부하

### 해야 할 것
- [ ] `FeatureCache` 클래스 구현
  ```python
  class FeatureCache:
      def __init__(self, ttl: timedelta = timedelta(minutes=5)):
          self.cache: Dict[str, CachedFeatures] = {}
          self.ttl = ttl

      def get(self, key: str) -> Features | None:
          """캐시에서 feature 조회"""
          if key not in self.cache:
              return None

          cached = self.cache[key]
          if datetime.now() - cached.timestamp > self.ttl:
              # 만료
              del self.cache[key]
              return None

          return cached.features

      def set(self, key: str, features: Features):
          """캐시에 feature 저장"""
          self.cache[key] = CachedFeatures(
              features=features,
              timestamp=datetime.now(),
          )
  ```

- [ ] `FeatureEngine`에 통합
  ```python
  class FeatureEngine:
      def __init__(self):
          self.cache = FeatureCache(ttl=timedelta(minutes=5))

      def get_features(self, symbol: str, timeframe: str = "4h") -> Features:
          cache_key = f"{symbol}:{timeframe}"

          # 캐시 확인
          cached = self.cache.get(cache_key)
          if cached:
              logger.debug(f"Feature cache hit: {cache_key}")
              return cached

          # 계산
          history = self.market_data.get_ohlcv(symbol, timeframe, limit=250)
          features = Features(
              ema200=self.calculate_ema200_4h(history),
              atr=self.calculate_atr_4h(history),
              current_price=history[-1].close,
              timestamp=history[-1].timestamp,
          )

          # 캐시 저장
          self.cache.set(cache_key, features)
          return features
  ```

- [ ] 성능 목표
  ```
  - 캐시 히트율 > 80%
  - Feature 계산 시간 < 10ms (캐시 히트 시)
  - TTL: 5분 (4시간봉은 느리게 변함)
  ```

### 완료 기준
- [ ] FeatureCache 클래스 구현
- [ ] FeatureEngine 캐싱 통합
- [ ] 테스트: 5분 내 재요청 → 캐시 히트
- [ ] 테스트: 5분 경과 → 재계산
- [ ] 성능: 캐시 히트 시 < 10ms

---

## 🎯 Learning Issue 4: Slippage 임계값 동적 조정

### 현재 상태
- EXECUTION_MODEL.md에 slippage 0.15% 임계값 고정
- **시장 상황에 따라 조정 필요**

### 문제
변동성 높은 구간: slippage 0.2%도 정상
변동성 낮은 구간: slippage 0.1% 넘으면 비정상

**고정 임계값은 비효율적입니다.**

### 해야 할 것
- [ ] `SlippageEstimator` 클래스 구현
  ```python
  class SlippageEstimator:
      def estimate_acceptable_slippage(
          self, atr: float, avg_price: float
      ) -> float:
          """
          ATR 기준 slippage 임계값 동적 계산

          공식: acceptable_slippage = (ATR / price) * 0.5
          """
          atr_pct = atr / avg_price
          return atr_pct * 0.5  # ATR의 50%
  ```

- [ ] `ExecutionValidator`에 통합
  ```python
  class ExecutionValidator:
      def __init__(self):
          self.slippage_estimator = SlippageEstimator()

      def validate_fill(
          self,
          order: Order,
          fill: Fill,
          atr: float,
      ) -> ValidationResult:
          expected_price = order.price
          actual_price = fill.price
          slippage_pct = abs(actual_price - expected_price) / expected_price

          # 동적 임계값
          acceptable = self.slippage_estimator.estimate_acceptable_slippage(
              atr, expected_price
          )

          if slippage_pct > acceptable:
              return FAIL(
                  reason="excessive_slippage",
                  actual=slippage_pct,
                  acceptable=acceptable,
              )

          return PASS()
  ```

- [ ] EXECUTION_MODEL.md 5.2 업데이트
  ```markdown
  ## 5.2 Slippage 검증 (동적 임계값)

  ### 동적 임계값 계산
  ```python
  acceptable_slippage = (ATR / price) * 0.5
  ```

  ### 예시
  - BTC 40,000 USD, ATR 800 → acceptable = 1.0%
  - BTC 40,000 USD, ATR 200 → acceptable = 0.25%

  ### 장점
  - 변동성 높을 때: 넉넉한 허용
  - 변동성 낮을 때: 엄격한 검증
  ```

### 완료 기준
- [ ] SlippageEstimator 클래스 구현
- [ ] ExecutionValidator 동적 임계값 통합
- [ ] EXECUTION_MODEL.md 5.2 업데이트
- [ ] 테스트: ATR 800 → slippage 0.8% 허용
- [ ] 테스트: ATR 200 → slippage 0.3% 차단

---

## 🎯 Learning Issue 5: Tail Profit 분포 분석

### 현재 상태
- Account Builder 목표: 상위 10% 승리로 전체 보상
- **하지만 "어떤 트레이드가 tail인지" 학습 안 함**

### 문제
+500% 트레이드와 +100% 트레이드의 공통점을 학습하지 못합니다.

### 해야 할 것
- [ ] `TailAnalyzer` 클래스 구현
  ```python
  class TailAnalyzer:
      def analyze_tail_winners(
          self, trades: List[TradeResult]
      ) -> TailAnalysis:
          """
          상위 10% 승리 트레이드 패턴 분석

          1. 진입 조건 공통점
          2. Feature 분포
          3. 시장 regime
          """
          # 상위 10% 추출
          sorted_trades = sorted(trades, key=lambda t: t.r_multiple, reverse=True)
          top_10pct = sorted_trades[:int(len(sorted_trades) * 0.1)]

          # Feature 분석
          tail_features = [t.entry_features for t in top_10pct]

          return TailAnalysis(
              avg_r_multiple=np.mean([t.r_multiple for t in top_10pct]),
              common_regime=self._find_common_regime(tail_features),
              avg_atr=np.mean([f.atr for f in tail_features]),
              avg_ema_distance=np.mean([
                  (f.current_price - f.ema200) / f.ema200
                  for f in tail_features
              ]),
          )
  ```

- [ ] 주기적 분석 스케줄러
  ```python
  # 월 1회 실행
  def monthly_tail_analysis():
      all_trades = decision_log.get_all_trades()
      analysis = tail_analyzer.analyze_tail_winners(all_trades)

      logger.info(
          f"Tail winners analysis:\n"
          f"  Avg R: {analysis.avg_r_multiple:.2f}\n"
          f"  Common regime: {analysis.common_regime}\n"
          f"  Avg ATR: {analysis.avg_atr:.2f}\n"
          f"  Avg EMA distance: {analysis.avg_ema_distance:.2%}"
      )

      # 분석 결과 저장
      with open("reports/tail_analysis.json", "w") as f:
          json.dump(asdict(analysis), f)
  ```

- [ ] 학습 피드백 (선택)
  ```python
  # P3 (v3.0)에서 구현 예정
  # Tail 패턴 → Strategy 조건 강화
  ```

### 완료 기준
- [ ] TailAnalyzer 클래스 구현
- [ ] 월간 분석 스케줄러 구현
- [ ] 테스트: 100개 트레이드 → 상위 10개 분석
- [ ] 보고서: reports/tail_analysis.json 생성

---

## P2 전체 완료 조건

**이 5개 항목이 80% 이상 완료되면 시스템이 "학습"합니다.**

- [ ] State Machine meta-capability (StateHealthMonitor)
- [ ] Regime-aware EV adjustment (RegimeDetector)
- [ ] Feature Engine 캐싱
- [ ] Slippage 동적 임계값
- [ ] Tail Profit 분포 분석

### 검증 방법
1. **1개월 Paper Trading**: 자동 조정 로그 확인
2. **Health Issue 감지**: 최소 1회 anomaly 감지 및 대응
3. **Regime 전환**: NORMAL → CONTRACTION → 임계값 완화 확인
4. **성능**: Feature 계산 < 10ms (캐싱)

### 예상 일정
**4주차 이후**

---

## 이후 작업

P2 완료 후 → [P3_meta_system.md](P3_meta_system.md) (v3.0)

P3는 "전략 자체를 평가하고 교체하는" 메타 레이어입니다.
