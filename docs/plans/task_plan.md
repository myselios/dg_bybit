# docs/plans/task_plan.md
# PLAN: Account Builder Trading Flow → Implementation Tasks (v2, Bybit Inverse-ready)
Last Updated: 2026-01-18
Status: READY (implementation can start)

## 0. Goal
Implement an Account Builder system ($100 → $1,000) that is:
- executable in real trading (Bybit Inverse Futures constraints)
- survival-first but growth-enforcing (time + stage targets)
- deterministic gates (no vague "X%", no "short window")

Non-goal:
- over-architecting (keep components testable + replaceable only)
- fantasy liquidation math (use exchange-derived liq where possible)

---

## 1. Core Constants (code constants)

### 1.1 Time Targets
- Target: $100 → $1,000 within 6–12 months (max 18)
- Review Trigger: 12 months without $200
- Hard Failure: 18 months without $1,000

### 1.2 Hard Stops
- Balance < $80 => HALT (manual reset only)
- Liquidation warning / liquidation event => HALT (manual reset only)

### 1.3 Leverage Policy
- Default leverage: 3x
- Increase: forbidden
- Decrease: allowed (balance > $500 => consider 2x)

### 1.4 Loss Budget (BTC percentage with USD cap) — FINAL

Because Bybit Inverse is BTC-margined, a fixed $10 loss can become an unsafe % of balance when BTC price drops.
Therefore loss budget is defined in BTC with a USD cap.

Definitions:
- equity_btc = wallet_balance_btc + unrealized_pnl_btc  (Bybit equity)
- btc_price_usd = current_mark_price
- equity_usd = equity_btc * btc_price_usd

Stage USD caps:
- Stage 1 ($100–$300): max_loss_usd_cap = $10
- Stage 2 ($300–$700): max_loss_usd_cap = $20
- Stage 3 ($700–$1,000): max_loss_usd_cap = $30

BTC percentage caps (safety):
- Stage 1: pct_cap = 12%
- Stage 2: pct_cap = 8%
- Stage 3: pct_cap = 6%

Compute:
- max_loss_btc = min(equity_btc * pct_cap, max_loss_usd_cap / btc_price_usd)

This max_loss_btc is used by sizing (contracts).
USD values are for display/logging only.

### 1.5 Trade Frequency
- balance < $300  : max_trades_per_day = 5
- balance >= $300 : max_trades_per_day = 10

---

## 2. Stage & Mode (explicit parameter bundles)

### Stage 1 — Expansion ($100 → $300) : Aggressive
- max_loss: $10
- EV gate: expected_profit_usd >= estimated_fee_usd * 2
- volatility: ATR_pct_24h > 3%
- maker-only: enforced
- max_trades/day: 5

### Stage 2 — Acceleration ($300 → $700) : Balanced
- max_loss: $20
- EV gate: expected_profit_usd >= estimated_fee_usd * 2.5
- volatility: ATR_pct_24h > 4%
- maker-only: optional (default maker preferred)
- max_trades/day: 10

### Stage 3 — Preservation ($700 → $1,000) : Defensive
- max_loss: $30
- leverage: 2x default
- EV gate: expected_profit_usd >= estimated_fee_usd * 3
- volatility: ATR_pct_24h > 5%
- max_trades/day: 10

---

## 2.4 Stage Determination (USD Equity-based) — FINAL

Stage is determined ONLY at NEW ENTRY time.

Balance calculation (Bybit equity):
- equity_btc = wallet_balance_btc + unrealized_pnl_btc
- btc_price_usd = current_mark_price
- equity_usd = equity_btc * btc_price_usd

Stage by USD equity:
- Stage 1: equity_usd < $300
- Stage 2: $300 ≤ equity_usd < $700
- Stage 3: equity_usd ≥ $700

Entry-time snapshot rule:
- Determine stage at order placement time using current mark price.
- Store `entry_stage` inside Position.
- Open positions keep entry_stage rules until exit.

Anti-flap:
- If stage changes >2 times within 1 hour => block new entries for 1 hour.

---

## 3. Emergency (Priority 0, BEFORE signal)

### Thresholds (no “short window”)
- price_drop_1m <= -10% => HALT
- price_drop_5m <= -20% => HALT
- exchange_latency >= 5.0s => cancel pending orders + block new entries
- balance anomaly (<=0 or API invalid) => HALT

### HALT Recovery Rules (must exist)
Manual-only recovery:
- liquidation warning/event
- balance < $80

Auto-recovery (temporary HALT only):
- price_drop_1m > -5% AND price_drop_5m > -10% for 5 consecutive minutes
- then: lift HALT but enforce cooldown: no entries for 30 minutes

---

## 4. Fees (Bybit Inverse Futures, entry-time estimable)

Key property (Inverse):
- contract_value = 1 USD per contract
- position_notional_usd = contracts
- therefore estimated_fee_usd = contracts * fee_rate  (price cancels out)

### Fee Estimation
- maker_fee_rate = 0.0001 (0.01%)
- taker_fee_rate = 0.0006 (0.06%)

estimated_fee_usd = contracts * fee_rate

### EV Gate
if expected_profit_usd < estimated_fee_usd * K(stage):
  REJECT

### Post-trade verification
- record actual fee from fill
- if actual_fee_usd > estimated_fee_usd * 1.5 => log "fee_spike" and tighten entries for 24h

---

## 4.5 Maker-only Timeout Fallback (small account realism)

Rule:
- balance < $300 => maker-only enforced by default

If 3 consecutive maker timeouts for same signal:
- allow ONE taker order
- condition: expected_profit_usd >= estimated_taker_fee_usd * 5
- max taker entries per day: 1
- if taker also fails (slippage/fee spike) => block entries 1 hour

Rationale:
Survival > rule purity, but taker is heavily gated.

---

## 5. Position Sizing (correct for Bybit Inverse)

IMPORTANT:
- Size must be computed in contracts (not USD notional as a final unit).
- Loss budget must be enforced by STOP distance, not liquidation math.
- Liquidation distance is a safety buffer check (use exchange-derived liq if possible).

### Step A: Stop Distance (Grid Strategy) — FINAL

Grid mechanics:
- Entry: at a grid level
- Primary exit: next grid level (profit-taking)
- Stop loss: emergency exit when structure breaks

stop_distance_pct is derived from grid spacing:

Inputs:
- grid_spacing_pct  (strategy parameter or derived from recent volatility/grid config)

Rule:
- stop_distance_pct = clamp(grid_spacing_pct * 1.5, min=2.0%, max=6.0%)

Fallback:
- if grid_spacing_pct is unavailable => stop_distance_pct = 3.0%

If stop_distance_pct <= 0 or missing => REJECT

### Step B: Compute contracts from loss budget — FINAL

Inverse property (loss in BTC):
- loss_btc_at_stop ≈ (contracts / entry_price_usd) * stop_distance_pct

Rearrange:
- contracts = (max_loss_btc * entry_price_usd) / stop_distance_pct

Where max_loss_btc from Section 1.4.

Constraints:
- contracts >= 1 (Bybit minimum)
- floor(contracts) to integer
- if contracts < 1 => REJECT

### Step C: Margin Feasibility (BTC-denominated, USD for display) — FINAL

Inverse Futures operates in BTC margin.

Definitions:
- entry_price_usd = current_mark_price
- contracts_to_btc = contracts / entry_price_usd
- required_margin_btc = contracts_to_btc / leverage

Fees (maker default):
- fee_buffer_btc = contracts_to_btc * maker_fee_rate * 2   (entry+exit)

Feasibility check (true):
- if required_margin_btc + fee_buffer_btc > equity_btc:
    REJECT

USD display for logging:
- required_margin_usd = required_margin_btc * entry_price_usd
- equity_usd = equity_btc * entry_price_usd

### Step D: Liquidation safety buffer (do NOT fake the formula)
- Obtain liquidation price/distance from exchange endpoint if available.
- Require: liq_distance_pct >= 30% (stage 1–2) or >= 20% (stage 3 with 2x)

If cannot obtain liq estimate:
- fallback conservative proxy: require leverage <= 3 and stop_distance_pct <= 5%
- and force smaller contracts by 20% (safety haircut)

---

## 6. Winrate Gating (adaptive for small accounts)

Definitions:
- N = number of CLOSED trades (rolling stats)
- live_winrate computed on last 50 closed trades (or fewer if <50)

Rules:
- N < 10: gate uses backtest_winrate >= 55% only
- 10 <= N < 30: soft gate
  - if live_winrate < 40% => WARNING + size_multiplier *= 0.5
- N >= 30: hard gate
  - if live_winrate < 45% => HALT (manual reset recommended)

---

## 7. Loss Streak Multiplier (with recovery)

- Min multiplier: 0.25, Max: 1.0

Reduction:
- 3 consecutive losses => size_multiplier = max(size_multiplier * 0.5, 0.25)

Recovery:
- 3 consecutive wins => size_multiplier = min(size_multiplier * 1.5, 1.0)

---

## 8. Final Criteria (code-enforceable)

SUCCESS:
- balance >= 1000
- no liquidation
- within 18 months

FAILURE (HALT):
- liquidation warning/event
- balance < 80
- time_elapsed > 18 months without reaching 1000

REVIEW TRIGGER:
- time_elapsed > 12 months without 200 => flag strategy_review_required

---

## 9. Minimal Architecture (prevent God Object, keep testable)

app/
  orchestrator.py        # flow only: stage order + stop-on-reject
  session_state.py       # HALT, stage, cooldown, trade/day counts
  metrics_tracker.py     # winrate, streak, rolling stats

exchange/
  adapter.py             # interface
  bybit_adapter.py       # real impl
  mock_adapter.py        # tests

logging/
  trade_logger.py        # entry/exit audit
  halt_logger.py         # HALT reasons + context snapshot
  metrics_logger.py      # daily summaries

config/
  constants.py           # invariants (hard stops, leverage limits)
  stage_config.yaml      # stage params (K, ATR threshold, max trades/day)
  emergency_config.yaml  # emergency thresholds

---

## 10. Implementation Reference

**실행 Flow 규칙**: `docs/constitution/FLOW.md` 참조 (헌법)

본 문서는 **구현 작업 체크리스트**만 포함.
Flow(실행 순서/상태 전환)를 수정하려면 FLOW.md를 ADR과 함께 변경.

### Build Order (Implementation Tasks)

**Phase 0: Foundation**
- [ ] Config system (YAML + constants)
- [ ] Core types (Enums, Dataclasses)
- [ ] State Machine (FLAT/ENTRY_PENDING/IN_POSITION/EXIT_PENDING/HALT/COOLDOWN)
- [ ] Position Mode Verification (FLOW v1.4 Section 3.1: One-way 강제)
- [ ] REST Budget Tracker (90회/분 rolling window)
- [ ] Tests: config validation, state transitions, position mode check

**Phase 1: Market & Emergency**
- [ ] Bybit Adapter (Interface + Mock)
- [ ] Market Data (candles, ATR, drops, latency)
- [ ] Emergency Checker (HALT conditions + recovery)
- [ ] WS Health Tracker (heartbeat timeout, event drop count) (FLOW v1.5 Section 2.6)
- [ ] WS DEGRADED Mode (진입 차단 + IN_POSITION 1초 reconcile) (FLOW v1.5 Section 2.6)
- [ ] Tests: Emergency paths, auto-recovery, DEGRADED mode transitions

**Phase 2: Entry Flow (FLAT → ENTRY_PENDING)**
- [ ] Signal Engine (Grid spacing, EV estimation)
  - [ ] Signal ID 생성: SHA1 해시 축약 (36자 제한) (FLOW v1.5 Section 8)
  - [ ] orderLinkId 검증: 길이 <= 36, 영숫자+`-_` 만 (FLOW v1.5 Section 8)
- [ ] Risk Gate (7 gates: stage/trades/volatility/EV/maker/winrate/cooldown)
  - [ ] One-way mode 검증: 포지션 있으면 반대방향 진입 REJECT (Section 3.1)
- [ ] Position Sizer (Bybit Inverse PnL formula, margin double-check)
  - [ ] Tick/Lot Size 보정: qtyStep, tickSize (FLOW v1.5 Section 3.4)
  - [ ] 보정 후 재검증: margin, liquidation (FLOW v1.5 Section 3.4)
- [ ] Liquidation Distance Calculator (FLOW v1.4 Section 7.5)
- [ ] Liquidation Distance Gate (동적 기준: stop × 배수 + 최소 절대값) (FLOW v1.5 Section 7.5)
- [ ] Tests: Sizing accuracy, margin feasibility, liquidation distance, reject reasons, tick/lot size

**Phase 3: Execution (ENTRY_PENDING → IN_POSITION)**
- [ ] Order Executor (Maker 주문, Idempotency)
  - [ ] Client Order ID: {signal_id}_{direction} (entry_price 제거, Section 8)
  - [ ] positionIdx=0 강제 (Section 3.1)
- [ ] Execution Event Handler (fills, cancels, timeouts)
  - [ ] PARTIAL_FILL: entry_working=True 플래그 설정 (Section 2.5)
- [ ] Fee Post-Trade Verification (FLOW v1.4 Section 6.2)
  - [ ] Inverse fee 단위: contracts = USD notional
- [ ] Fee Spike Detection & 24h Tightening (fee_ratio > 1.5)
- [ ] Maker Fallback (3 timeout → 1 taker)
- [ ] Tests: Partial fills, duplicate orders, taker gating, fee spike handling

**Phase 4: Position Management (IN_POSITION → EXIT_PENDING/FLAT)**
- [ ] Stop Loss placement (Grid exit vs Emergency exit)
  - [ ] Stop 주문 속성: reduceOnly=True, positionIdx=0, orderType="Market" (Section 4.5)
  - [ ] Stop 갱신: Amend 우선 (SL 공백 방지) (FLOW v1.5 Section 2.5)
  - [ ] Debounce: 20% threshold + 2초 간격 (Rate limit 절약) (FLOW v1.5 Section 2.5)
  - [ ] entry_working=True 상태에서 잔량 체결 시 조건부 Stop 갱신 (Section 2.5)
- [ ] Position Monitor (PnL tracking, exit conditions)
- [ ] Metrics Tracker (Winrate, Streak, Size multiplier)
- [ ] Tests: Stop order integrity, Amend vs Cancel+Place, debounce, metrics accuracy, entry_working 처리

**Phase 5: Observability**
- [ ] Trade Logger (Entry/Exit audit trail)
- [ ] HALT Logger (Emergency context snapshot)
- [ ] Metrics Logger (Daily rollup)
- [ ] Tests: Log schema, required fields

**Phase 6: Orchestrator Integration**
- [ ] Tick Loop (1초 간격, non-blocking)
- [ ] Snapshot Update (Market + Account + Orders)
- [ ] Flow execution (Emergency → Events → Position/Entry)
- [ ] Tests: End-to-end state transitions

### Definition of DONE

- [ ] Flow 규칙 (FLOW.md v1.6) 위반 없음
- [ ] Blocking wait 사용 없음
- [ ] BTC-denominated 계산 검증
- [ ] State machine 모든 전환 테스트
- [ ] Emergency가 Signal보다 우선 실행
- [ ] Idempotency 보장 (중복 주문 방지)
- [ ] God Object 없음 (책임 분리 검증)
- [ ] **v1.4 구조적 구멍 8개 수정 검증**:
  - [ ] Position Mode = One-way 검증 (Section 3.1)
  - [ ] PARTIAL_FILL entry_working 플래그 구현 (Section 2.5)
  - [ ] REST Budget 90회/분 합산 제한 (Section 2)
  - [ ] Reconcile 히스테리시스 (연속 3회, 5초 COOLDOWN) (Section 2.6)
  - [ ] Fee 계산 단위: contracts = USD notional (Section 6.2)
  - [ ] Liquidation Gate 동적 기준 (Section 7.5)
  - [ ] Idempotency Key: {signal_id}_{direction} SHA1 해시 축약 (Section 8)
  - [ ] Stop 주문 속성: reduceOnly=True, positionIdx=0 (Section 4.5)
- [ ] **v1.5 실거래 함정 5개 수정 검증**:
  - [ ] Stop Loss Amend API 우선 (SL 공백 제거) (Section 2.5)
  - [ ] Stop 갱신 Debounce (20% threshold + 2초) (Section 2.5)
  - [ ] WS DEGRADED Mode (진입 차단 + IN_POSITION 1초 reconcile) (Section 2.6)
  - [ ] orderLinkId 길이 <= 36, 영숫자+`-_` 검증 (Section 8)
  - [ ] Tick/Lot Size 보정 + 재검증 (Section 3.4)
- [ ] **v1.6 실거래 API 충돌 5개 수정 검증** (참조: ADR-0005):
  - [ ] Event-driven 상태 확정 (REST 폴링 금지) (Section 4.1)
  - [ ] Stop Loss = Conditional Order 방식 B 고정 (reduceOnly + stopLoss 혼용 금지) (Section 4.5)
  - [ ] positionIdx=0 강제 (문자열 검증은 로그만) (Section 3.1)
  - [ ] 정상/DEGRADED 모드 분리 (DEGRADED 60초 후 HALT) (Section 2.5)
  - [ ] stop_status 서브상태 (ACTIVE/PENDING/MISSING/ERROR) 감시 및 복구 (Section 1)
