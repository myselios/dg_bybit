# docs/specs/account_builder_policy.md
# Account Builder Policy Specification (Stable Defaults + Tunables)
Last Updated: 2026-02-13 (KST)
Version: 2.4

## 목적 (Purpose)

이 문서는 Account Builder 시스템의 **정책 스펙**을 정의한다.

- **FLOW.md**: 실행 순서/상태 전환/모드(one-way, degraded 등) 같은 “구조적 헌법”
- **본 문서**: 수치/임계치/파라미터/게이트 기준 같은 “정책 값(Policy Values)”

> 구현 체크리스트: `docs/plans/task_plan.md`  
> 실행 헌법: `docs/constitution/FLOW.md`

---

## 0. 변경 규칙 (Change Governance)

### 0.1 ADR Required (구조/정의/단위 변경)
아래 변경은 반드시 ADR과 함께 진행한다.
- 계산 단위(contracts, BTC/USDT 환산) 변경
- Stage 결정 규칙(ENTRY-time snapshot) 변경
- Hard Stop / Manual-only HALT 조건 변경
- 측정 정의 변경(예: latency 정의, liquidation warning 정의)
- “Policy Data Model”의 필드 구조 변경(스키마 변경)

### 0.2 Config Change OK (튜닝 파라미터 변경)
아래 변경은 ADR 없이 config 값 변경으로 허용한다(단, 변경 이력 기록).
- EV gate 배수, ATR 임계치, 드랍 임계치, 연속 조건, cooldown 시간
- Maker/Taker fallback 계수, 타임아웃 횟수
- Winrate 기준, Streak multiplier 계수
- Liq distance 최소치(단, 정의 자체 변경은 ADR)

---

## 1. 용어/단위 정의 (Definitions)

### 1.1 계좌/가격 (Linear USDT)
- `equity_usdt` = `wallet_balance_usdt + unrealized_pnl_usdt`  (Bybit equity, USDT 기준)
- `btc_price_usd` = current mark price (USD, display용)
- **Note**: Linear Futures는 USDT-Margined이므로 equity는 USDT 단위

### 1.2 Linear 계약 단위 (USDT-Margined)
- Linear 특성: `1 contract = 1 coin` (e.g., BTCUSDT에서 1 contract = 0.001 BTC)
- `position_notional_usdt = qty * entry_price_usd`
- `estimated_fee_usdt = qty * entry_price_usd * fee_rate`
- **Bybit Linear BTCUSDT contract size**: 0.001 BTC per contract

### 1.3 시간/카운터 스냅샷
- Stage는 **신규 진입 시도 시점(ENTRY evaluation time)** 에만 계산한다.
- Position에는 아래를 저장한다:
  - `entry_stage` (1/2/3)
  - `policy_version` (예: "2.1")
- 오픈 포지션은 `policy_version` 및 `entry_stage` 기준으로 exit까지 유지한다.

---

## 2. Policy Data Model (Config Schema)

> 본 문서는 아래 스키마가 `config/*.yaml`에 1:1 매핑되는 것을 전제로 한다.

### 2.1 StageConfig
필드:
- `stage_id`: 1|2|3
- `equity_usd_min`: float
- `equity_usd_max`: float | null
- `default_leverage`: float
- `max_loss_usd_cap`: float
- `loss_pct_cap`: float
- `ev_fee_multiple_k`: float
- `atr_pct_24h_min`: float
- `max_trades_per_day`: int
- `maker_only_default`: bool
- `taker_allowed`: bool
- `taker_fee_multiple_k`: float  (taker 허용 시 추가 gate)
- `liq_distance_min_pct`: float

### 2.2 EmergencyConfig
필드:
- `drop_1m_halt_pct`: float  (negative)
- `drop_5m_halt_pct`: float  (negative)
- `latency_rest_degraded_s`: float
- `latency_rest_halt_s`: float
- `balance_halt_min_usd`: float
- `auto_recovery_drop_1m_clear_pct`: float
- `auto_recovery_drop_5m_clear_pct`: float
- `auto_recovery_consecutive_minutes`: int
- `post_recovery_cooldown_minutes`: int
- `stage_flap_max_changes_per_hour`: int
- `stage_flap_block_minutes`: int

### 2.3 FeesConfig
필드:
- `maker_fee_rate`: float
- `taker_fee_rate`: float
- `fee_spike_ratio`: float
- `fee_spike_tighten_hours`: int

### 2.4 SizingConfig
필드:
- `stop_distance_min_pct`: float
- `stop_distance_max_pct`: float
- `stop_distance_multiplier`: float  (grid_spacing * multiplier)
- `stop_distance_fallback_pct`: float
- `liq_fallback_stop_distance_max_pct`: float
- `liq_fallback_size_haircut_ratio`: float
- `min_contracts`: int

### 2.5 PerformanceGatesConfig
필드:
- `backtest_winrate_min_pct`: float
- `live_winrate_soft_min_pct`: float
- `live_winrate_hard_min_pct`: float
- `live_winrate_soft_size_mult`: float
- `live_winrate_hard_action`: "HALT"

### 2.6 StreakConfig
필드:
- `min_multiplier`: float
- `max_multiplier`: float
- `loss_streak_count`: int
- `loss_reduce_ratio`: float
- `win_streak_count`: int
- `win_recover_ratio`: float

---

## 3. Core Constants (Stable Defaults)

### 3.1 Time Targets (Stable)
- Target: $100 → $1,000 within 6–12 months (max 18)
- Review Trigger: 12 months without $200
- Hard Failure: 18 months without $1,000

### 3.2 Hard Stops (ADR Required)
- `equity_usd < 80` → `HALT` (manual reset only)
- liquidation warning/event → `HALT` (manual reset only)

### 3.3 Trade Frequency (Stable defaults)
- `equity_usd < 300`  : max_trades_per_day = 5
- `equity_usd >= 300` : max_trades_per_day = 10

---

## 4. Stage Determination (ENTRY-time Snapshot) — ADR Required

Stage is determined ONLY at NEW ENTRY evaluation time.

Compute:
- `equity_btc = wallet_balance_btc + unrealized_pnl_btc`
- `btc_price_usd = current_mark_price`
- `equity_usd = equity_btc * btc_price_usd`

Stage by USD equity:
- Stage 1: equity_usd < $300
- Stage 2: $300 ≤ equity_usd < $700
- Stage 3: equity_usd ≥ $700

Snapshot rule:
- Determine stage using current mark price at order placement attempt.
- Store `entry_stage` inside Position.
- Open positions keep entry_stage rules until exit.

Anti-flap (ENTRY evaluation time only):
- Track `stage_candidate` calculated at each new entry attempt.
- If stage_candidate changes > 2 times within 1 hour:
  - block new entries for 60 minutes.

---

## 5. Stage Parameters (Tunables)

> NOTE: 아래 수치는 기본값이며, 튜닝은 config 변경으로 가능(변경 이력 기록).

### 5.1 Stage 1 — Expansion ($100 → $300) : Aggressive
- default_leverage: 3x
- max_loss_usd_cap: $10 (v2.4: $3→$10, 수익 스케일링 위해 상향)
- loss_pct_cap: 10% (v2.4: 3%→10%, 소액 계좌 3~5 contracts 진입 가능)
- EV gate: expected_profit_usd >= estimated_fee_usd * 2.0
- volatility: ATR_pct_24h > 2% (v2.4: 3%→2%, BTC 저변동 구간 진입 허용)
- maker_only_default: true
- max_trades/day: 10 (v2.4: 5→10, 소액 계좌 기회 포착 빈도 확보)
- liq_distance_min_pct: 30%

### 5.2 Stage 2 — Acceleration ($300 → $700) : Balanced
- default_leverage: 3x
- max_loss_usd_cap: $20
- loss_pct_cap: 8%
- EV gate: expected_profit_usd >= estimated_fee_usd * 2.5
- volatility: ATR_pct_24h > 4%
- maker_only_default: false (maker preferred)
- max_trades/day: 10
- liq_distance_min_pct: 30%

### 5.3 Stage 3 — Preservation ($700 → $1,000) : Defensive
- default_leverage: 2x
- max_loss_usd_cap: $30
- loss_pct_cap: 6%
- EV gate: expected_profit_usd >= estimated_fee_usd * 3.0
- volatility: ATR_pct_24h > 5%
- max_trades/day: 10
- liq_distance_min_pct: 20%

### 5.4 Leverage Policy (clarified)
- Each stage defines its `default_leverage`.
- Leverage increase above stage default is forbidden.
- Decrease is allowed (e.g., stage2/3 operate at lower leverage when risk gates tighten).

---

## 6. Loss Budget (USDT percent with USD cap) — ADR Required (definition)

**Linear USDT-Margined**: Loss budget is defined in USDT (직접 계산, 환산 불필요).

Definitions:
- equity_usdt = wallet_balance_usdt + unrealized_pnl_usdt (Bybit equity)

Stage USD caps:
- Stage 1: max_loss_usd_cap = $10 (v2.4: $3→$10)
- Stage 2: max_loss_usd_cap = $20
- Stage 3: max_loss_usd_cap = $30

USDT percentage caps:
- Stage 1: pct_cap = 10% (v2.4: 3%→10%)
- Stage 2: pct_cap = 8%
- Stage 3: pct_cap = 6%

Compute:
- max_loss_usdt = min(equity_usdt * pct_cap, max_loss_usd_cap)

Rule:
- This `max_loss_usdt` is the only loss budget used by sizing.
- **Linear 장점**: 환산 불필요 (USDT = USD 1:1 근사)

---

## 7. Emergency Policy (Priority 0) — mixed (definitions ADR, thresholds tunable)

### 7.1 Measurement Definitions (ADR Required)
Latency metric used in policy:
- `exchange_latency_rest_s` is defined as:
  - REST request round-trip time (RTT), measured per endpoint,
  - using p95 over the last 1 minute window,
  - sampled on core endpoints used by trading loop.

Balance anomaly definition:
- API returns non-positive equity OR schema invalid OR stale timestamp beyond tolerance (implementation-defined tolerance, e.g., >30s).

Liquidation warning definition:
- Use Bybit-provided liquidation/maintenance margin signals if available in endpoints/streams.
- If not available, define a conservative internal warning in ADR (do not guess in code).

### 7.2 Thresholds (Tunables)
- price_drop_1m <= -10% => COOLDOWN (auto-recovery 가능)
- price_drop_5m <= -20% => COOLDOWN (auto-recovery 가능)
- exchange_latency_rest_s >= 5.0s => cancel pending orders + block new entries (emergency_block=True)
- balance anomaly => HALT (Manual reset only)

### 7.3 Recovery Rules (ADR Required for categories, tunable for time)
Manual-only recovery (HALT):
- liquidation warning/event
- equity_usd < 80
- balance anomaly (equity <= 0 OR stale > 30s)

Auto-recovery (COOLDOWN only):
- price_drop_1m > -5% AND price_drop_5m > -10% for 5 consecutive minutes
- then lift COOLDOWN and enforce cooldown: no entries for 30 minutes

---

## 8. Fees Policy (Linear USDT) — ADR Required (units), Tunable (rates/ratios)

### 8.1 Fee rates (Tunables)
- maker_fee_rate = 0.0001
- taker_fee_rate = 0.0006

### 8.2 Estimation (ADR Required - Linear)
- estimated_fee_usdt = qty * entry_price_usd * fee_rate
- **Linear 특성**: Fee는 notional value에 비례 (qty × price × fee_rate)

### 8.3 EV Gate (Tunables per stage)
- Reject if: expected_profit_usd < estimated_fee_usd * K(stage)

### 8.4 Post-trade verification (Tunables)
- record actual fee from fill
- if actual_fee_usd > estimated_fee_usd * 1.5:
  - log "fee_spike"
  - tighten entries for 24h (implementation: increase K, maker-only enforce, reduce size_multiplier)

---

## 9. Maker-only Timeout Fallback (Tunables with strict caps)

Defaults:
- equity_usd < 300 => maker-only enforced by default

Fallback rule:
If 3 consecutive maker timeouts for the same signal:
- allow ONE taker order
- require: expected_profit_usd >= estimated_taker_fee_usd * 5
- max taker entries per day: 1
- if taker also fails or fee spike occurs:
  - block entries for 60 minutes

---

## 10. Margin Mode & Position Sizing (Bybit Linear USDT)

### 10.0 Margin Mode (ADR-0012) — 협상 불가 (Immutable)

**고정값**: Isolated Margin (격리 마진)

**정책**:
- 모든 포지션은 **Isolated Margin**으로만 진입 (Cross Margin 사용 금지)
- 각 포지션마다 독립적인 증거금 할당
- 한 포지션 청산 시 다른 포지션/잔고에 영향 없음 (리스크 격리)

**Bybit Linear USDT API 파라미터**:
- `category="linear"`
- `symbol="BTCUSDT"`
- `tradeMode=0` (0=Isolated, 1=Cross/Portfolio Margin)
- `isLeverage=true` (Bybit Linear 기본값)

**Margin Mode vs Leverage 분리**:
- **Margin Mode**: Isolated 고정 (변경 금지)
- **Leverage**: Stage별 동적 변경 (Section 5: Stage 1/2=3x, Stage 3=2x)
- 두 개념은 독립적 (Isolated Margin에서도 Leverage 3x 사용 가능)

**Trade-off**:
- **단점**: 포지션당 독립 증거금 필요 (Cross 대비 포지션 크기 작음)
- **현재 영향 없음**: Stage 1 (equity < $300)에서는 1회 1포지션만 진입
- **장점**: 청산 리스크 격리 (Account Builder 목표 "청산 방지" 달성)

**검증** (향후 구현, Phase 13+):
- 프로세스 시작 시 Margin Mode 확인 (`get_position()` → `tradeMode=0` 검증)
- Cross Margin 감지 시 프로세스 시작 거부 (`FatalConfigError`)

**참조**: ADR-0012 (Margin Mode Isolated Enforcement)

---

## 10.1 Position Sizing (Bybit Linear USDT) — ADR Required (math), Tunables (bounds)

### 10.1.1 Step A: Stop Distance (ATR-based Dynamic, v2.4)
Inputs:
- ATR (14-period, from market data)
- entry_price

Rule (v2.4: Grid→ATR 전환, R:R 2.14:1 최적화):
- stop_distance_pct = clamp(ATR * 0.7 / entry_price, min=0.5%, max=2.0%)

Fallback:
- if ATR unavailable or <= 0 => stop_distance_pct = 1.0%

Reject:
- if stop_distance_pct <= 0 or missing => REJECT

### 10.1.2 Step B: Compute qty from loss budget (Linear)
**Linear property**:
- loss_usdt_at_stop = qty * entry_price_usd * stop_distance_pct

Rearrange:
- qty = max_loss_usdt / (entry_price_usd * stop_distance_pct)

**Bybit Linear BTCUSDT contract size**: 0.001 BTC per contract
- contracts = floor(qty / 0.001)
- qty = contracts * 0.001  (실제 거래량)

Constraints:
- contracts >= 1 (최소 1 contract = 0.001 BTC)
- contracts = floor(contracts)

### 10.1.3 Step C: Margin feasibility (USDT-denominated)
Definitions:
- notional_usdt = qty * entry_price_usd
- required_margin_usdt = notional_usdt / leverage
- fee_buffer_usdt = notional_usdt * maker_fee_rate * 2  (entry+exit)

Feasibility:
- if required_margin_usdt + fee_buffer_usdt > equity_usdt => REJECT

### 10.1.4 Step D: Liquidation safety buffer (no fake formula)
Preferred:
- obtain liquidation distance from exchange endpoint if available
- require: liq_distance_pct >= stage.liq_distance_min_pct

Fallback (if liq estimate unavailable):
- require leverage <= 3
- require stop_distance_pct <= 5%
- apply size haircut:
  - contracts = floor(contracts * 0.8)
- additionally:
  - if stop_distance_pct > 4% => REJECT (conservative)

---

## 11. Performance Gates (Winrate + Streak)

### 11.1 Winrate gating (Tunables)
Definitions:
- N = number of CLOSED trades
- live_winrate computed on last 50 closed trades (or fewer if <50)

Rules:
- N < 10:
  - gate uses backtest_winrate >= 55% only
- 10 <= N < 30:
  - if live_winrate < 40% => WARNING + size_multiplier *= 0.5
- N >= 30:
  - if live_winrate < 45% => HALT (manual reset recommended)

### 11.2 Loss streak multiplier (Tunables)
- Min multiplier: 0.25, Max: 1.0

Reduction:
- 3 consecutive losses => size_multiplier = max(size_multiplier * 0.5, 0.25)

Recovery:
- 3 consecutive wins => size_multiplier = min(size_multiplier * 1.5, 1.0)

---

## 12. Final Criteria (code-enforceable)

SUCCESS:
- equity_usd >= 1000
- no liquidation
- within 18 months

FAILURE (HALT):
- liquidation warning/event
- equity_usd < 80
- time_elapsed > 18 months without reaching 1000

REVIEW TRIGGER:
- time_elapsed > 12 months without 200 => flag strategy_review_required

---

## 13. Change History

| Date | Version | Change | ADR |
|------|---------|--------|-----|
| 2026-02-08 | 2.3 | Margin Mode Isolated 정책 추가 (Section 10.0) | ADR-0012 |
| 2026-01-21 | 2.2 | HALT vs COOLDOWN 정의 정렬 (SSOT 충돌 수정) | ADR-0007 |
| 2026-01-18 | 2.1 | 정책 스펙을 "불변/튜닝 분리 + 데이터모델 스키마"로 정리 | - |