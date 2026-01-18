# P0 Critical Fixes — 청산 방지 (v2.2 목표)

## 목적

**이것들이 없으면 계좌가 청산됩니다.**

v2.1에서 구조는 설계되었으나, **실제 연결과 검증이 누락된 항목들**을 완성합니다.

---

## 🔥 Critical Issue 1: Expansion 청산 DD 시뮬레이션

### 현재 상태
- EXPANSION_POLICY.md에 worst-case 체크 있음
- 하지만 "entry reversal" 체크만 있고 **liquidation path simulation 없음**

### 문제
```python
# 현재 (EXPANSION_POLICY.md 4.3절)
worst_case_loss = calculate_loss_if_entry_reverses()

# 누락: 청산까지 가는 경로 시뮬레이션
liquidation_dd = simulate_price_path_to_liquidation()
```

### 해야 할 것
- [ ] `LiquidationPathSimulator` 구현
  - Monte Carlo로 현재가 → 청산가 경로 1000회 시뮬레이션
  - 95th percentile DD 계산
  - DD > -50% 시 expansion 차단

- [ ] Expansion 재검증에 통합
  ```python
  def validate_expansion_safety(
      current_position: Position,
      expansion_layer: int,
  ) -> ValidationResult:
      # 기존: Marginal EV
      marginal_ev = calculate_marginal_ev(...)

      # 추가: 청산 DD
      liquidation_dd = simulate_liquidation_path(
          position_after_expansion=...,
          monte_carlo_runs=1000,
      )

      if liquidation_dd.percentile_95 > -0.5:
          return FAIL("liquidation_risk_too_high")
  ```

- [ ] 테스트 케이스
  - 레버리지 5x, ATR 거리 2.0 → expansion 시도
  - 시뮬레이션 결과 95% DD = -52% → 차단 확인

### 완료 기준
- [ ] LiquidationPathSimulator 클래스 구현 완료
- [ ] EXPANSION_POLICY.md 4.3절 업데이트 (청산 DD 추가)
- [ ] 테스트: expansion 시도 시 95% DD > -50% → 차단됨
- [ ] 로그: `ExpansionDecisionLog`에 `liquidation_dd_95` 필드 추가

### 예상 작업 시간
**협상 불가 — 이것 없으면 expansion = 청산**

---

## 🔥 Critical Issue 2: Liquidation Monitor 실제 연결

### 현재 상태
- TASK_BREAKDOWN.md P0에 "Liquidation Monitor" 있음
- BASE_ARCHITECTURE.md에 `RiskManager` Protocol 정의됨
- **하지만 실제 구현 코드 없음**

### 해야 할 것
- [ ] `LiquidationMonitor` 클래스 구현
  ```python
  class LiquidationMonitor:
      def check_liquidation_distance(
          self,
          position: Position,
          current_price: float,
          atr: float,
      ) -> LiquidationWarning | None:
          """
          청산가 거리를 ATR 단위로 계산

          Returns:
              LiquidationWarning if distance < 1.5 ATR
              None otherwise
          """
          liquidation_price = position.liquidation_price
          distance_atr = abs(current_price - liquidation_price) / atr

          if distance_atr < 1.5:
              return LiquidationWarning(
                  distance_atr=distance_atr,
                  recommended_action="EMERGENCY_EXIT",
              )
          return None
  ```

- [ ] `RiskManager`에 통합
  ```python
  class RiskManager:
      def __init__(self):
          self.liquidation_monitor = LiquidationMonitor()

      def validate_position_safety(
          self, position: Position, market_data: MarketData
      ) -> ValidationResult:
          warning = self.liquidation_monitor.check_liquidation_distance(...)
          if warning:
              self.event_emitter.emit(
                  ExecutionEvent.LIQUIDATION_WARNING
              )
              return FAIL("liquidation_imminent")
  ```

- [ ] State Machine 연결
  - EXECUTION_EVENTS.md 3.1 전환 테이블 확인
  - `ENTRY + LIQUIDATION_WARNING → EXIT_FAILURE`
  - `EXPANSION + LIQUIDATION_WARNING → EXIT_FAILURE`

### 완료 기준
- [ ] LiquidationMonitor 클래스 구현
- [ ] RiskManager 통합
- [ ] State Machine 이벤트 연결
- [ ] 테스트: 청산가 < 1.5 ATR → LIQUIDATION_WARNING 발생 → EXIT_FAILURE 전환

---

## 🔥 Critical Issue 3: Emergency Exit 로직

### 현재 상태
- TASK_BREAKDOWN.md P0에 "Emergency Exit" 있음
- EXECUTION_EVENTS.md에 LIQUIDATION_WARNING 정의됨
- **실제 market order 청산 로직 없음**

### 해야 할 것
- [ ] `EmergencyExit` 전략 구현
  ```python
  class EmergencyExit:
      def execute_emergency_exit(
          self,
          position: Position,
          reason: str,
      ) -> ExecutionResult:
          """
          무조건 Market Order로 즉시 청산

          - Slippage 무시
          - Retry 없음
          - 실패 시 로그만 남기고 계속 시도
          """
          order = MarketOrder(
              side=opposite(position.side),
              quantity=position.quantity,
              reduce_only=True,
          )

          result = self.trading_engine.submit_order(order)

          self.decision_log.log_emergency_exit(
              reason=reason,
              slippage=result.slippage,
              execution_time=result.execution_time,
          )

          return result
  ```

- [ ] LIQUIDATION_WARNING 이벤트 핸들러에 연결
  ```python
  # State Machine에서
  if event == ExecutionEvent.LIQUIDATION_WARNING:
      emergency_exit.execute_emergency_exit(
          position=current_position,
          reason="liquidation_imminent",
      )
      self.transition_to(State.EXIT_FAILURE)
  ```

### 완료 기준
- [ ] EmergencyExit 클래스 구현
- [ ] LIQUIDATION_WARNING → EmergencyExit 연결
- [ ] 테스트: Mock으로 청산 임박 상황 생성 → Market 청산 확인
- [ ] 로그: EmergencyExitLog에 reason, slippage 기록

---

## 🔥 Critical Issue 4: Position Size 청산가 사전 계산

### 현재 상태
- TASK_BREAKDOWN.md P0에 "Position Size 청산가 계산" 있음
- POSITION_MODEL.md에 레버리지 제한 있음
- **진입 전 청산가 거리 검증 로직 없음**

### 해야 할 것
- [ ] `PositionSizer`에 청산가 검증 추가
  ```python
  def calculate_safe_size(
      self,
      entry_price: float,
      leverage: float,
      atr: float,
      side: Side,
  ) -> PositionSize | ValidationFailure:
      # 1. 청산가 계산
      liquidation_price = calculate_liquidation_price(
          entry_price, leverage, side
      )

      # 2. ATR 거리 확인
      distance_atr = abs(entry_price - liquidation_price) / atr

      # 3. 최소 거리 검증 (3 ATR)
      if distance_atr < 3.0:
          return FAIL(
              reason="liquidation_too_close",
              distance_atr=distance_atr,
          )

      # 4. Safe size 계산
      return PositionSize(...)
  ```

- [ ] EV Validator에 통합
  - EV_FRAMEWORK.md 7.1 Pre-filter에 추가
  - "청산가 < 3 ATR" → 즉시 차단

### 완료 기준
- [ ] PositionSizer.calculate_safe_size 구현
- [ ] EV Pre-filter에 청산가 검증 추가
- [ ] 테스트: 청산가 < 3 ATR 진입 시도 → Pre-filter 차단
- [ ] 로그: EVDecisionLog에 `liquidation_distance_atr` 기록

---

## 🔥 Critical Issue 5: Drawdown -50% 강제 종료

### 현재 상태
- TASK_BREAKDOWN.md P0에 "Drawdown 한도 (-50%)" 있음
- STATE_MACHINE.md에 TERMINATED 상태 있음
- **실제 DD 모니터링 및 전환 로직 없음**

### 해야 할 것
- [ ] `DrawdownMonitor` 구현
  ```python
  class DrawdownMonitor:
      def check_drawdown(
          self,
          account_equity: float,
          peak_equity: float,
      ) -> DrawdownStatus:
          dd_pct = (account_equity - peak_equity) / peak_equity

          if dd_pct <= -0.50:
              return DrawdownStatus(
                  current_dd=dd_pct,
                  action="TERMINATE",
              )

          return DrawdownStatus(current_dd=dd_pct, action="CONTINUE")
  ```

- [ ] State Machine 메인 루프에 통합
  ```python
  # TradingOrchestrator 메인 루프
  def run(self):
      while True:
          dd_status = self.drawdown_monitor.check_drawdown(...)

          if dd_status.action == "TERMINATE":
              self.state_machine.force_terminate(
                  reason="max_drawdown_exceeded"
              )
              break
  ```

- [ ] TERMINATED 상태 구현
  - 모든 포지션 청산
  - 새로운 진입 영구 차단
  - 최종 로그 기록

### 완료 기준
- [ ] DrawdownMonitor 클래스 구현
- [ ] State Machine TERMINATED 전환 로직
- [ ] 테스트: DD -50% 도달 → TERMINATED → 시스템 종료
- [ ] 로그: TerminationLog에 peak_equity, final_equity, reason 기록

---

## P0 전체 완료 조건

**이 5개 항목이 100% 완료되기 전까지 실거래 금지.**

- [ ] Expansion 청산 DD 시뮬레이션 구현 및 테스트
- [ ] Liquidation Monitor 구현 및 State Machine 연결
- [ ] Emergency Exit 구현 및 이벤트 핸들러 연결
- [ ] Position Size 청산가 사전 계산 구현
- [ ] Drawdown Monitor 구현 및 TERMINATED 전환

### 검증 방법
1. **단위 테스트**: 각 컴포넌트 독립 검증
2. **통합 테스트**: Mock 시장 데이터로 청산 시나리오 재현
3. **Paper Trading**: 최소 1주일 실행, 청산 경고 발생 확인

### 예상 일정
**1주차 목표**

---

## 이후 작업

P0 완료 후 → [P1_core_completion.md](P1_core_completion.md)
