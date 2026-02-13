# CBGB Operation Manual
**Version**: 1.0
**Created**: 2026-02-01
**Last Updated**: 2026-02-01
**Status**: ✅ COMPLETE (3453 lines, 35 functions documented)

---

## 📚 목차 (Table of Contents)

- [1. System Overview](#1-system-overview)
  - [1.1 Purpose & Goals](#11-purpose--goals)
  - [1.2 Core Principles](#12-core-principles)
  - [1.3 Constraints](#13-constraints)
- [2. Architecture](#2-architecture)
  - [2.1 Layered Architecture](#21-layered-architecture)
  - [2.2 Module Dependency Map](#22-module-dependency-map)
  - [2.3 Directory Structure](#23-directory-structure)
- [3. System Components](#3-system-components)
  - [3.1 Domain Layer](#31-domain-layer)
  - [3.2 Application Layer](#32-application-layer)
  - [3.3 Infrastructure Layer](#33-infrastructure-layer)
- [4. State Machine](#4-state-machine) _(Phase 2)_
- [5. Core Flows](#5-core-flows) _(Phase 2)_
- [6. Function Reference](#6-function-reference) _(Phase 3)_
- [7. External Integrations](#7-external-integrations) _(Phase 4)_
- [8. Operations Guide](#8-operations-guide) _(Phase 5)_
- [9. Troubleshooting](#9-troubleshooting) _(Phase 5)_
- [10. References](#10-references) _(Phase 6)_

---

## 1. System Overview

### 1.1 Purpose & Goals

**CBGB (Controlled BTC Growth Bot)**는 Bybit Linear Futures (USDT-Margined) 기반의 자동 트레이딩 시스템입니다.

#### 핵심 목표
- **계정 성장**: USD $100 → $1,000 (10배 성장)
- **시장**: Bybit BTCUSDT Linear Futures (USDT-Margined)
- **전략**: Directional-filtered Grid Strategy
  - Grid spacing 기반 Entry 신호 생성
  - MA slope 기반 Regime 필터링 (Trend-following + Range 적응)
- **측정 기준**: `Equity (USDT) = wallet_balance_usdt + unrealized_pnl_usdt`

#### 설계 철학: Survival-First

**청산(Liquidation) = 실패**
- Drawdown은 허용하지만, 청산은 시스템 실패로 간주
- 손실 상한 명확: Daily -5%, Weekly -12.5%, Loss streak (3연패 → HALT)
- 리스크 관리가 수익 극대화보다 우선

**비목표 (Non-Goals)**
- Martingale / 무제한 물타기 (금지)
- 백테스트 최적화 (실거래 생존성이 기준)
- 높은 수익률 (안정적 성장이 목표)

---

### 1.2 Core Principles

CBGB 시스템은 다음 원칙을 엄격히 준수합니다.

#### 1) Document-First Workflow
모든 작업은 **문서 → 테스트 → 구현** 순서로 진행:
1. SSOT 3문서 읽기 ([FLOW.md], [account_builder_policy.md], [task_plan.md])
2. `task_plan.md` Progress Table 업데이트 (TODO → IN PROGRESS)
3. **테스트 먼저 작성** (RED 확인)
4. 최소 구현으로 GREEN
5. 문서 업데이트 (DONE, Evidence 링크)

#### 2) Single Source of Truth (SSOT)
정의/단위/우선순위는 3개 문서만을 기준으로 함:
- **[FLOW.md]**: 실행 순서, 상태 전환, 모드 규칙 (헌법)
- **[account_builder_policy.md]**: 정책 수치, 게이트 정의, 단위, 스키마
- **[task_plan.md]**: Gate 기반 구현 순서, DoD, 진행표

기타 문서(PRD.md, STRATEGY.md 등)는 **참고 자료**이며, SSOT와 충돌 시 SSOT 우선.

#### 3) Zero Placeholder Tests
다음은 테스트로 인정하지 않음:
- `assert True`
- `pytest.skip()` (정당한 사유 없음)
- `pass  # TODO`
- `raise NotImplementedError`

모든 체크박스는 **RED→GREEN 증거**(테스트가 실제로 실패했다가 구현 후 통과)가 있어야 DONE.

#### 4) Pure Function State Machine
- `transition()` 함수는 **순수 함수**(no I/O)
- 상태 전이 로직은 **오직 transition()에만** 존재 (SSOT)
- EventRouter/Handler는 thin wrapper로만 유지 (입력 정규화 + transition 호출)

#### 5) Test-Driven Development (TDD)
- Oracle 테스트: `tests/oracles/test_state_transition_oracle.py` (상태 전이 + intents 동시 검증)
- Unit 테스트: 각 모듈 독립 테스트 (30개 파일)
- Integration 테스트: 연결 확인 (5~10개로 제한)

#### 6) Real Trading Trap Prevention
실거래 함정 방지를 위한 강제 규칙 (SSOT: FLOW.md Section 1.5 + bybit_*_client.py):
- **Position Mode One-way 검증**: positionIdx=0 고정
- **PARTIAL_FILL 처리**: `entry_working` 플래그 추적 (부분체결 시 즉시 IN_POSITION 전환)
- **Rate limit 감지** (우선순위 순):
  1. retCode=10006 → 즉시 RateLimitError 발생 + backoff
  2. X-Bapi-Limit-Status < 20% → Tick 주기 증가
  3. 내부 예산(참고용)은 보수적 상한으로만 사용
- **WebSocket 정합성**:
  - Heartbeat: ping-pong 메커니즘 (Bybit 서버 요구)
  - Reconnection: 연결 끊김 시 자동 재연결
  - Event drop 감지: WS event drop count 추적 → DEGRADED 전환
  - **주의**: "max_active_time 10분" 정책은 Bybit 서버측 제약이지, 클라이언트가 **능동적으로 끊는 게 아님**
- **Reconcile 히스테리시스**: WS DEGRADED 시 1초 reconcile, 60초 지속 시 HALT
- **Stop 주문 파라미터**: orderType=Market, triggerBy=LastPrice, reduceOnly=True, positionIdx=0
- **orderLinkId 규격**: ≤36자, [A-Za-z0-9_-] (Bybit 공식 제약)
- **Stop 주문 혼용 금지**: 단일 파라미터 조합만 사용 (Conditional Market stop)

---

### 1.3 Constraints

#### 기술적 제약
- **Platform**: Bybit Linear Futures (USDT-Margined)
- **Symbol**: BTCUSDT Linear Perpetual
- **Position Mode**: One-way (양방향 동시 포지션 금지, positionIdx=0)
- **Stop Order**: Conditional Order (orderType=Market, triggerBy=LastPrice, reduceOnly=True)
- **Rate Limit**: X-Bapi-* 헤더 기반 throttle + retCode=10006 우선 감지 (per-second rolling window)

#### 운영 제약
- **Tick 주기**: 목표 2초 (Rate limit 헤더 기반 동적 조정)
- **WebSocket 우선**: 실시간 execution/order/position stream, REST는 fallback만
- **Blocking Wait 금지**: WS I/O는 메인 tick을 block하지 않음 (asyncio 또는 background thread)
- **God Object 금지**: 책임 분리, 모듈화 강제

#### 리스크 제약 (SSOT: account_builder_policy.md + session_risk_tracker.py)
- **Equity 정의**: `equity_usdt = wallet_balance_usdt + unrealized_pnl_usdt` (미실현 손익 포함)
- **Daily Loss Cap**: -5% equity (UTC boundary 기준, 당일 realized PnL 누적)
- **Weekly Loss Cap**: -12.5% equity (UTC boundary 기준, 주간 realized PnL 누적)
- **Loss Streak Kill**: 3연패 시 HALT (거래 단위, 부분청산 포함)
- **Emergency Drop**: 1분 -10% / 5분 -20% → COOLDOWN (자동 복구 가능)
- **Balance Anomaly**: Equity < $80 또는 Equity ≤ 0 → HALT (Manual reset)

---

### 1.4 Definitions (단위 정의 - SSOT)

**중요**: 모든 계산 단위는 [account_builder_policy.md] Section 1에서 정의됨. 아래는 운영에 필수적인 정의만 발췌.

#### Product & Market
- **Product**: Bybit Linear Futures (USDT-Margined Perpetual)
- **Symbol**: BTCUSDT
- **Qty 단위**: **미확정** (Bybit 심볼 스펙 확인 필요)
  - ⚠️ **HOLD**: "1 contract = 0.001 BTC" 같은 고정값은 실제 Bybit 스펙과 다를 수 있음
  - account_builder_policy.md에 "0.001 BTC per contract" 명시되어 있으나, Bybit는 "base currency로 주문" 지원
  - **실거래 전 필수**: Bybit API `/v5/market/instruments-info?category=linear&symbol=BTCUSDT` 확인
- **Order Type**: Market order (Entry), Conditional order (Stop Loss)

#### Equity & PnL (SSOT: account_builder_policy.md Section 1.1)
- **Equity**: `equity_usdt = wallet_balance_usdt + unrealized_pnl_usdt`
  - **미실현 손익 포함** (Bybit equity 그대로 사용)
  - USDT 단위 (Linear Futures는 USDT-Margined)
- **Realized PnL**: 거래 종료 시 확정된 손익 (Daily/Weekly loss cap 판정 기준)
- **Unrealized PnL**: 현재 포지션의 미실현 손익 (Equity 계산에 포함, Loss cap 판정에 **미포함**)

#### Time Boundaries (SSOT: session_risk_tracker.py)
- **Daily boundary**: UTC 00:00 (매일 자정 UTC 기준 리셋)
- **Weekly boundary**: UTC 월요일 00:00 (주간 PnL 리셋)
- **주의**: KST 기준이 **아님** (UTC 고정)

#### Rate Limit (SSOT: bybit_rest_client.py + FLOW.md Section 2)
- **Bybit 공식 정책**: UID 기준 per-second rolling window (NOT per-minute 고정)
- **감지 방법**:
  1. **retCode=10006** (최우선 신호): Rate limit exceeded
  2. **X-Bapi-Limit-Status** 헤더: 남은 요청 수
  3. **X-Bapi-Limit-Reset-Timestamp** 헤더: 리셋 시각
- **내부 예산**: 보수적 상한으로만 사용 (실제 throttle은 헤더 기반)
- **Throttle 정책**: retCode=10006 또는 헤더 80% 도달 시 backoff

#### Stop Loss Order (SSOT: order_executor.py + FLOW.md Section 4.5)
- **Order Type**: Conditional Order (Market execution at trigger)
- **Parameters**:
  - `orderType`: "Market"
  - `triggerBy`: "LastPrice"
  - `triggerDirection`: 2 (LONG, falling) / 1 (SHORT, rising)
  - `reduceOnly`: True (포지션 감소만 허용)
  - `positionIdx`: 0 (One-way mode)
- **혼용 금지**: 다른 방식의 Stop 주문과 동시 사용 금지 (SSOT 위반)

---

## 2. Architecture

### 2.1 Layered Architecture

CBGB는 Clean Architecture를 따르며, 다음 3개 계층으로 구성됩니다.

```
┌─────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                    │
│  (외부 연동: Bybit API, WebSocket, Storage, Notification)   │
│                                                               │
│  - exchange/: BybitAdapter, REST/WS Client                  │
│  - logging/: TradeLogger, HaltLogger, MetricsLogger         │
│  - storage/: LogStorage (JSONL)                             │
│  - notification/: TelegramNotifier                          │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ (의존성 역전)
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                       │
│        (비즈니스 로직: Entry/Exit/Risk/Order 관리)          │
│                                                               │
│  - transition.py: 상태 전이 SSOT (순수 함수)                │
│  - event_router.py: Thin wrapper                            │
│  - entry_allowed.py: Entry gates (8 gates)                  │
│  - signal_generator.py: Grid signal + Regime filter         │
│  - sizing.py: Position sizing (Loss budget 기반)            │
│  - exit_manager.py: Exit decision (Stop hit / Profit)       │
│  - stop_manager.py: Stop placement/amend/recovery           │
│  - session_risk.py: Daily/Weekly PnL, Loss streak           │
│  - emergency.py: Emergency check + COOLDOWN                  │
│  - order_executor.py: Order execution (Idempotency)         │
│  - orchestrator.py: Tick loop (Emergency-first ordering)    │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
                              │
┌─────────────────────────────────────────────────────────────┐
│                         Domain Layer                         │
│              (순수 함수, I/O 없음, 도메인 모델)              │
│                                                               │
│  - state.py: State, StopStatus, Position, PendingOrder      │
│  - events.py: EventType, ExecutionEvent                     │
│  - intent.py: TransitionIntents (StopIntent, HaltIntent)    │
│  - ids.py: signal_id, orderLinkId validators                │
└─────────────────────────────────────────────────────────────┘
```

**계층별 의존성 규칙**:
- **Domain Layer**: 외부 의존성 없음 (순수 Python)
- **Application Layer**: Domain에만 의존
- **Infrastructure Layer**: Domain, Application에 의존 (하지만 인터페이스를 통해 의존성 역전)

**분리 계층 (Analysis/Dashboard)**:
```
┌─────────────────────────────────────────────────────────────┐
│                      Analysis Layer                          │
│          (Trade log 분석, A/B 테스트, 통계 검정)            │
│                                                               │
│  - trade_analyzer.py: 거래 분석 (Winrate, Sharpe, MDD)      │
│  - ab_comparator.py: A/B 비교 (Wilcoxon, Chi-square)       │
│  - stat_test.py: 통계 검정 (t-test, confidence interval)   │
│  - report_generator.py: HTML/JSON 보고서 생성               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Dashboard Layer                          │
│                 (Trade log 시각화, 실시간 모니터링)          │
│                                                               │
│  - (Phase 13b+: 선택 사항, 아직 미구현)                      │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 Module Dependency Map

주요 모듈 간 의존성과 데이터 흐름:

```
[Bybit WebSocket] ─────► [BybitWsClient] ─────► [BybitAdapter]
                                                       │
                                                       │ MarketDataInterface
                                                       ▼
[Bybit REST API] ──────► [BybitRestClient] ─────► [BybitAdapter] ──────┐
                                                                         │
                                                                         │ get_mark_price()
                                                                         │ get_equity_usdt()
                                                                         ▼
                                                              ┌──────────────────────┐
                                                              │   Orchestrator       │
                                                              │   (Tick Loop)        │
                                                              └──────────────────────┘
                                                                         │
                                    ┌────────────────────────────────────┼────────────────────────────┐
                                    │                                    │                            │
                                    ▼                                    ▼                            ▼
                          ┌──────────────────┐              ┌──────────────────┐        ┌──────────────────┐
                          │ EmergencyChecker │              │  EventRouter     │        │  EntryAllowed    │
                          │ (Emergency-first) │              │  (Event 처리)    │        │  (8 Gates)       │
                          └──────────────────┘              └──────────────────┘        └──────────────────┘
                                    │                                    │                            │
                                    │                                    ▼                            │
                                    │                          ┌──────────────────┐                  │
                                    │                          │   transition()   │                  │
                                    │                          │   (SSOT)         │                  │
                                    │                          └──────────────────┘                  │
                                    │                                    │                            │
                                    │                                    ▼                            │
                                    │                          ┌──────────────────┐                  │
                                    │                          │ TransitionIntents│                  │
                                    │                          │ (StopIntent 등)  │                  │
                                    │                          └──────────────────┘                  │
                                    │                                    │                            │
                                    ▼                                    ▼                            ▼
                          ┌──────────────────┐              ┌──────────────────┐        ┌──────────────────┐
                          │   HALT / COOLDOWN│              │  OrderExecutor   │        │ SignalGenerator  │
                          │   (상태 변경)     │              │  (주문 실행)     │        │ (Grid Signal)    │
                          └──────────────────┘              └──────────────────┘        └──────────────────┘
                                    │                                    │                            │
                                    │                                    ▼                            ▼
                                    │                          ┌──────────────────┐        ┌──────────────────┐
                                    │                          │ StopManager      │        │     Sizing       │
                                    │                          │ (Stop 관리)      │        │ (Position Size)  │
                                    │                          └──────────────────┘        └──────────────────┘
                                    │                                    │                            │
                                    ▼                                    ▼                            ▼
                          ┌──────────────────┐              ┌──────────────────┐        ┌──────────────────┐
                          │   HaltLogger     │              │  TradeLogger     │        │  MetricsLogger   │
                          │   (로그 기록)     │              │  (거래 기록)     │        │  (메트릭 기록)    │
                          └──────────────────┘              └──────────────────┘        └──────────────────┘
                                    │                                    │                            │
                                    └────────────────────────────────────┴────────────────────────────┘
                                                                         │
                                                                         ▼
                                                              ┌──────────────────────┐
                                                              │    LogStorage        │
                                                              │    (JSONL)           │
                                                              └──────────────────────┘
```

**핵심 데이터 흐름**:
1. **Tick 시작**: Orchestrator가 MarketData (price, equity) 조회
2. **Emergency Check**: Emergency-first ordering (FLOW Section 2)
3. **Event Processing**: WebSocket 이벤트 → EventRouter → transition() → Intents
4. **Entry Decision**: EntryAllowed (8 gates) → SignalGenerator → Sizing → OrderExecutor
5. **Stop Management**: StopManager (place/amend/recovery)
6. **Logging**: TradeLogger, HaltLogger, MetricsLogger → LogStorage (JSONL)

---

### 2.3 Directory Structure

실제 파일 시스템 구조 (task_plan.md Section 2.1 Repo Map 기준):

```
/home/selios/dg_bybit/
│
├── src/                              # 소스 코드 (1.1 MB, 59개 Python 파일)
│   │
│   ├── domain/                       # 도메인 모델 (순수 함수, I/O 없음)
│   │   ├── __init__.py
│   │   ├── state.py                 # State, StopStatus, Position, PendingOrder
│   │   ├── events.py                # EventType, ExecutionEvent
│   │   ├── intent.py                # TransitionIntents, StopIntent, HaltIntent
│   │   └── ids.py                   # signal_id, orderLinkId validators
│   │
│   ├── application/                  # 비즈니스 로직 (25개 모듈)
│   │   ├── __init__.py
│   │   ├── transition.py            # transition() - 상태 전이 SSOT
│   │   ├── event_router.py          # EventRouter - Stateless thin wrapper
│   │   ├── tick_engine.py           # Tick Orchestrator
│   │   ├── emergency.py             # Emergency policy + recovery
│   │   ├── ws_health.py             # WebSocket health tracker
│   │   ├── entry_allowed.py         # Entry gates (8 gates)
│   │   ├── sizing.py                # Position sizing
│   │   ├── liquidation_gate.py      # Liquidation distance checks
│   │   ├── fee_verification.py      # Fee spike detection
│   │   ├── order_executor.py        # Order execution
│   │   ├── event_handler.py         # Execution event processing
│   │   ├── stop_manager.py          # Stop placement/amend/recovery
│   │   ├── metrics_tracker.py       # Winrate/streak/multipliers
│   │   ├── orchestrator.py          # Tick loop orchestrator
│   │   ├── signal_generator.py      # Grid signal + Regime filter
│   │   ├── exit_manager.py          # Exit decision
│   │   ├── event_processor.py       # Event processing helpers
│   │   ├── atr_calculator.py        # ATR calculation
│   │   ├── session_risk_tracker.py  # Session risk tracking
│   │   └── market_regime.py         # Market regime analysis
│   │
│   ├── analysis/                     # Trade log 분석 (Phase 13a)
│   │   ├── __init__.py
│   │   ├── trade_analyzer.py        # Trade log 분석 (472 LOC)
│   │   ├── stat_test.py             # 통계 검정 (170 LOC)
│   │   ├── ab_comparator.py         # A/B 비교 (265 LOC)
│   │   └── report_generator.py      # Report 생성 (261 LOC)
│   │
│   └── infrastructure/               # 외부 연동
│       ├── exchange/
│       │   ├── __init__.py
│       │   ├── fake_exchange.py     # 테스트용 가짜 거래소
│       │   ├── market_data_interface.py  # MarketDataInterface Protocol
│       │   ├── fake_market_data.py  # 테스트 데이터 injection
│       │   ├── bybit_rest_client.py # Bybit REST API 클라이언트
│       │   ├── bybit_ws_client.py   # Bybit WebSocket 클라이언트 (489 LOC)
│       │   └── bybit_adapter.py     # BybitAdapter (MarketDataInterface 구현)
│       ├── logging/
│       │   ├── __init__.py
│       │   ├── trade_logger.py      # Trade logging
│       │   ├── halt_logger.py       # HALT reason logging
│       │   ├── metrics_logger.py    # Metrics logging
│       │   └── trade_logger_v1.py   # Trade Log Schema v1.0
│       ├── storage/
│       │   ├── __init__.py
│       │   └── log_storage.py       # JSONL storage + rotation
│       └── notification/
│           ├── __init__.py
│           └── telegram_notifier.py # Telegram notification
│
├── tests/                            # 테스트 (366 tests passed)
│   ├── oracles/
│   │   ├── test_state_transition_oracle.py  # Primary oracle (25 cases)
│   │   └── test_integration_basic.py        # FakeExchange integration (9 cases)
│   ├── unit/                         # 단위 테스트 (30개 파일)
│   │   ├── test_state_transition.py
│   │   ├── test_event_router.py
│   │   ├── test_emergency.py
│   │   ├── test_entry_allowed.py
│   │   ├── test_sizing.py
│   │   ├── test_signal_generator.py
│   │   ├── test_exit_manager.py
│   │   ├── test_stop_manager.py
│   │   ├── test_atr_calculator.py
│   │   ├── test_session_risk_tracker.py
│   │   ├── test_trade_analyzer.py
│   │   └── ... (기타 20개)
│   ├── integration/
│   │   ├── test_orchestrator.py
│   │   └── test_dry_run_orchestrator.py
│   └── integration_real/             # Testnet 실제 연동 테스트
│       ├── test_testnet_connection.py
│       ├── test_testnet_order_flow.py
│       └── test_full_cycle_testnet.py
│
├── scripts/                          # 운영/디버그 스크립트 (20+ 개)
│   ├── run_testnet_dry_run.py       # Testnet dry-run orchestrator
│   ├── run_mainnet_dry_run.py       # Mainnet dry-run orchestrator
│   ├── generate_dry_run_report.py   # Trade log analysis
│   ├── analyze_trades.py            # CLI tool (analyze, compare)
│   └── verify_phase_completion.sh   # Phase 완료 검증 스크립트
│
├── docs/                             # 설계 문서 (26,666줄)
│   ├── constitution/
│   │   └── FLOW.md                  # 불변 헌법 (실행 순서, 상태 머신)
│   ├── specs/
│   │   └── account_builder_policy.md  # 정책 수치, Gate, 단위
│   ├── plans/
│   │   ├── task_plan.md             # Phase별 진행표, Repo Map
│   │   ├── PLAN_operation_manual.md # 본 문서 작성 계획
│   │   └── ... (기타 계획 문서)
│   ├── adr/                          # Architecture Decision Records
│   │   ├── ADR-0001.md ~ ADR-0011.md
│   │   └── ...
│   ├── evidence/                     # Phase별 완료 증거
│   │   ├── phase_0/
│   │   ├── phase_1/
│   │   └── ... (phase_13b까지)
│   └── debug/                        # 운영 가이드
│       └── ...
│
├── logs/                             # 로그 파일 (runtime 생성)
│   ├── trades.jsonl                 # Trade log
│   ├── metrics.jsonl                # Metrics log
│   └── halt.jsonl                   # HALT log
│
├── config/                           # 설정 파일 (yaml)
│   └── ... (정책 설정)
│
├── venv/                             # Python 가상환경
│
├── .claude/                          # Claude Code 설정
│   └── skills/                      # 커스텀 스킬
│
├── CLAUDE.md                         # 개발 운영 계약서
├── README.md                         # 프로젝트 개요
├── pyproject.toml                    # Python 프로젝트 설정
└── pytest.ini                        # pytest 설정
```

**주요 디렉토리 설명**:
- **src/domain/**: 도메인 모델 (4개 파일, 순수 Python, I/O 없음)
- **src/application/**: 비즈니스 로직 (25개 모듈, stateless 함수)
- **src/infrastructure/**: 외부 연동 (Bybit API, WebSocket, Storage, Notification)
- **src/analysis/**: Trade log 분석 도구 (Phase 13a)
- **tests/**: 테스트 (oracles, unit, integration, integration_real)
- **docs/**: 설계 문서 (SSOT 3문서 + ADR + Evidence)
- **scripts/**: 운영 스크립트

---

## 3. System Components

### 3.1 Domain Layer

**위치**: [`src/domain/`](../../src/domain/)

**책임**: 도메인 모델 정의 (순수 함수, I/O 없음)

**원칙**:
- 외부 의존성 없음 (순수 Python)
- 불변 데이터 클래스 사용 (`@dataclass(frozen=True)`)
- 비즈니스 규칙 캡슐화

#### 3.1.1 State Module ([src/domain/state.py](../../src/domain/state.py))

**State Enum** (6개 상태):
```python
class State(Enum):
    FLAT = "FLAT"               # 포지션 없음, 진입 가능
    ENTRY_PENDING = "ENTRY_PENDING"  # Entry 주문 대기
    IN_POSITION = "IN_POSITION"    # 포지션 오픈 (Stop 유지)
    EXIT_PENDING = "EXIT_PENDING"   # Exit 주문 대기
    HALT = "HALT"               # 모든 진입 차단 (Manual reset)
    COOLDOWN = "COOLDOWN"         # 일시적 차단 (자동 해제)
```

**StopStatus Enum** (4개 서브상태):
```python
class StopStatus(Enum):
    ACTIVE = "ACTIVE"     # Stop 주문 활성 (정상)
    PENDING = "PENDING"   # Stop 설치/갱신 중 (일시적)
    MISSING = "MISSING"   # Stop 없음 (비정상, 즉시 복구 필요)
    ERROR = "ERROR"       # Stop 복구 실패 (HALT 고려)
```

**Position Dataclass**:
- `side`: LONG/SHORT (+1/-1)
- `qty`: int (contracts)
- `entry_price_usd`: float
- `entry_stage`: int (1/2/3)
- `signal_id`: str
- `stop_status`: StopStatus
- 기타 필드 (entry_time, realized_pnl, unrealized_pnl 등)

**PendingOrder Dataclass**:
- `order_id`: str
- `order_link_id`: str (Idempotency key)
- `qty`: int
- `price`: float
- `direction`: LONG/SHORT
- `signal_id`: str

---

#### 3.1.2 Events Module ([src/domain/events.py](../../src/domain/events.py))

**EventType Enum** (6개 이벤트):
```python
class EventType(Enum):
    FILL = "FILL"               # 완전 체결
    PARTIAL_FILL = "PARTIAL_FILL"  # 부분 체결
    CANCEL = "CANCEL"            # 취소
    REJECT = "REJECT"            # 거절
    LIQUIDATION = "LIQUIDATION"    # 강제 청산 (최우선 처리)
    ADL = "ADL"                # 자동감소 (Auto Deleveraging)
```

**EventType 우선순위**:
```
LIQUIDATION > ADL > FILL > PARTIAL_FILL > REJECT > CANCEL
```

**ExecutionEvent Dataclass**:
- `type`: EventType
- `order_id`: str
- `filled_qty`: int
- `filled_price`: float
- `timestamp`: float
- 기타 필드 (symbol, side, fee 등)

---

#### 3.1.3 Intent Module ([src/domain/intent.py](../../src/domain/intent.py))

**TransitionIntents Dataclass** (transition() 출력):
```python
@dataclass
class TransitionIntents:
    stop_intent: Optional[StopIntent] = None           # Stop 갱신
    halt_intent: Optional[HaltIntent] = None           # HALT 명령
    cancel_intent: Optional[CancelOrderIntent] = None  # 주문 취소
    log_intent: Optional[LogIntent] = None            # 로그 기록
    exit_intent: Optional[ExitIntent] = None          # 강제 청산
    entry_blocked: bool = False                       # 진입 차단
```

**StopIntent**:
- `action`: PLACE / AMEND / CANCEL_AND_PLACE
- `qty`: int
- `stop_price`: float
- `signal_id`: str

**HaltIntent**:
- `reason`: str (예: "liquidation", "balance_anomaly", "loss_streak_kill")
- `context`: dict (추가 정보)

**ExitIntent**:
- `qty`: int
- `reason`: str (예: "stop_hit", "emergency_drop", "adl")

---

#### 3.1.4 IDs Module ([src/domain/ids.py](../../src/domain/ids.py))

**signal_id 생성**:
```python
def generate_signal_id() -> str:
    """SHA1 축약 기반 Signal ID 생성 (충돌 확률 극소)"""
    # 예: "sig_a3f7c2d1"
```

**orderLinkId 검증**:
```python
def validate_order_link_id(order_link_id: str) -> bool:
    """Bybit orderLinkId 규격 검증 (≤36자, [A-Za-z0-9_-])"""
```

---

### 3.2 Application Layer

**위치**: [`src/application/`](../../src/application/)

**책임**: 비즈니스 로직 (Entry/Exit/Risk/Order 관리)

**특징**:
- Stateless 함수 중심
- Domain에만 의존
- I/O는 Infrastructure에 위임

#### 주요 모듈 분류

**Core State Management** (2개):
- [transition.py](../../src/application/transition.py): 상태 전이 SSOT (순수 함수)
- [event_router.py](../../src/application/event_router.py): Stateless thin wrapper

**Entry Flow** (6개):
- [entry_allowed.py](../../src/application/entry_allowed.py): Entry gates (8 gates)
- [signal_generator.py](../../src/application/signal_generator.py): Grid signal + Regime filter
- [sizing.py](../../src/application/sizing.py): Position sizing (Loss budget 기반)
- [liquidation_gate.py](../../src/application/liquidation_gate.py): Liquidation distance checks
- [fee_verification.py](../../src/application/fee_verification.py): Fee spike detection
- [order_executor.py](../../src/application/order_executor.py): Order execution

**Exit & Stop Management** (3개):
- [exit_manager.py](../../src/application/exit_manager.py): Exit decision (Stop hit / Profit)
- [stop_manager.py](../../src/application/stop_manager.py): Stop placement/amend/recovery
- [event_processor.py](../../src/application/event_processor.py): Event processing helpers

**Risk Management** (4개):
- [emergency.py](../../src/application/emergency.py): Emergency check + COOLDOWN
- [session_risk_tracker.py](../../src/application/session_risk_tracker.py): Session risk tracking
- [metrics_tracker.py](../../src/application/metrics_tracker.py): Winrate/streak/multipliers
- [ws_health.py](../../src/application/ws_health.py): WebSocket health tracker

**Market Analysis** (2개):
- [atr_calculator.py](../../src/application/atr_calculator.py): ATR calculation
- [market_regime.py](../../src/application/market_regime.py): Market regime analysis

**Orchestration** (3개):
- [orchestrator.py](../../src/application/orchestrator.py): Tick loop orchestrator
- [tick_engine.py](../../src/application/tick_engine.py): Tick execution engine
- [event_handler.py](../../src/application/event_handler.py): Execution event processing

---

### 3.3 Infrastructure Layer

**위치**: [`src/infrastructure/`](../../src/infrastructure/)

**책임**: 외부 연동 (Bybit API, WebSocket, Storage, Notification)

#### 3.3.1 Exchange ([src/infrastructure/exchange/](../../src/infrastructure/exchange/))

**MarketDataInterface Protocol** ([market_data_interface.py](../../src/infrastructure/exchange/market_data_interface.py)):
```python
class MarketDataInterface(Protocol):
    def get_mark_price(self) -> float: ...
    def get_equity_usdt(self) -> float: ...
    def get_rest_latency_p95_1m(self) -> float: ...
    def get_ws_last_heartbeat_ts(self) -> float: ...
    def get_ws_event_drop_count(self) -> int: ...
    def get_btc_mark_price_usd(self) -> float: ...
    def get_daily_realized_pnl_usd(self) -> float: ...
    def get_loss_streak_count(self) -> int: ...
```

**BybitAdapter** ([bybit_adapter.py](../../src/infrastructure/exchange/bybit_adapter.py)):
- MarketDataInterface 구현
- REST + WebSocket 통합
- Caching 정책 (mark_price: 500ms, equity: 1s)

**BybitRestClient** ([bybit_rest_client.py](../../src/infrastructure/exchange/bybit_rest_client.py)):
- REST API 클라이언트 (서명 생성, Rate limit 헤더 처리)
- 주요 엔드포인트: POST /v5/order/create, /amend, /cancel, GET /v5/position/list

**BybitWsClient** ([bybit_ws_client.py](../../src/infrastructure/exchange/bybit_ws_client.py)):
- WebSocket 클라이언트 (489 LOC, 14 public + 10 private methods)
- Topic 구독: `execution.linear` (Linear Futures)
- Heartbeat monitoring: ping-pong, 20초 간격
- Reconnection logic: max_active_time 10분

**FakeExchange** ([fake_exchange.py](../../src/infrastructure/exchange/fake_exchange.py)):
- 테스트용 가짜 거래소 (Deterministic simulator)

---

#### 3.3.2 Logging ([src/infrastructure/logging/](../../src/infrastructure/logging/))

**TradeLogger** ([trade_logger.py](../../src/infrastructure/logging/trade_logger.py)):
- Entry/Exit logging + schema validation

**TradeLoggerV1** ([trade_logger_v1.py](../../src/infrastructure/logging/trade_logger_v1.py)):
- Trade Log Schema v1.0 (slippage, latency, market_regime, integrity fields)

**HaltLogger** ([halt_logger.py](../../src/infrastructure/logging/halt_logger.py)):
- HALT reason + context snapshot

**MetricsLogger** ([metrics_logger.py](../../src/infrastructure/logging/metrics_logger.py)):
- Winrate/streak/multiplier change tracking

---

#### 3.3.3 Storage ([src/infrastructure/storage/](../../src/infrastructure/storage/))

**LogStorage** ([log_storage.py](../../src/infrastructure/storage/log_storage.py)):
- JSONL 파일 저장 (O_APPEND, fsync policy)
- Durability policy: batch (10 lines) / periodic (1s) / critical event fsync
- Partial line recovery

---

#### 3.3.4 Notification ([src/infrastructure/notification/](../../src/infrastructure/notification/))

**TelegramNotifier** ([telegram_notifier.py](../../src/infrastructure/notification/telegram_notifier.py)):
- Telegram 푸시 알림 (Entry/Exit/HALT/Summary)
- Silent fail (알림 실패 시에도 시스템 중단 없음)

---

## 4. State Machine

**SSOT**: [FLOW.md] Section 1 + [src/application/transition.py](../../src/application/transition.py) + [src/domain/state.py](../../src/domain/state.py)

시스템은 **순수 함수 기반 상태 머신**으로 동작하며, 모든 상태 전이는 `transition()` 함수에서만 처리됩니다.

### 4.1 State 정의 (6개 상태)

| State | 의미 | Position | Entry Allowed | 진입 경로 | 탈출 경로 |
|-------|------|----------|---------------|----------|----------|
| **FLAT** | 포지션 없음, 진입 가능 | None | True (gate 통과 시) | - Initial state<br>- EXIT_PENDING + FILL<br>- ENTRY_PENDING + REJECT/CANCEL(0)<br>- IN_POSITION + ADL(qty=0) | → ENTRY_PENDING (Entry 주문 발주)<br>→ HALT (FLAT에서 예상치 못한 FILL) |
| **ENTRY_PENDING** | Entry 주문 대기 중 | None (또는 부분체결 시 존재) | False | - FLAT → 주문 발주 | → IN_POSITION (FILL/PARTIAL_FILL)<br>→ FLAT (REJECT/CANCEL(0))<br>→ HALT (pending_order=None) |
| **IN_POSITION** | 포지션 오픈 (Stop Loss 유지) | Required (qty > 0) | False | - ENTRY_PENDING + FILL/PARTIAL_FILL/CANCEL(filled>0) | → EXIT_PENDING (Exit 주문 발주)<br>→ FLAT (ADL qty=0)<br>→ HALT (LIQUIDATION, filled_qty≤0) |
| **EXIT_PENDING** | Exit 주문 대기 중 | Required (qty > 0) | False | - IN_POSITION → Exit 주문 발주 | → FLAT (FILL 정상)<br>→ EXIT_PENDING 유지 (PARTIAL_FILL, REJECT/CANCEL)<br>→ HALT (과체결) |
| **HALT** | 모든 진입 차단 (Manual reset) | Any | False (Manual reset only) | - LIQUIDATION (모든 상태)<br>- 유령 체결 (FLAT + FILL)<br>- 과체결 (EXIT_PENDING)<br>- filled_qty≤0, ADL 무결성 오류 | → FLAT (Manual reset: `.halt` 파일 삭제) |
| **COOLDOWN** | 일시적 차단 (자동 해제) | Any | False (Auto after timeout) | - Emergency drop (-10%/-20%)<br>- WS DEGRADED 60초 지속 | → FLAT (30분 경과 AND 5분 연속 안정) |

#### State Invariants (불변 조건)

각 상태에서 반드시 만족해야 하는 조건 (코드 assert 기준):

| State | position.qty | pending_order | stop_status | Invariant Rule |
|-------|--------------|---------------|-------------|----------------|
| FLAT | == 0 | None | N/A | 포지션 없음 |
| ENTRY_PENDING | >= 0 | Required | N/A (부분체결 시 PENDING) | 부분체결 시 position.qty > 0 + entry_working=True |
| IN_POSITION | > 0 | None (또는 entry_working=True 시 존재) | ACTIVE/PENDING (MISSING은 최대 10초) | **Stop 필수**, ERROR는 HALT 직전 |
| EXIT_PENDING | > 0 | Required (exit order) | N/A | 청산 주문 대기 |
| HALT | any | any (pending 취소됨) | any | 모든 진입 차단, Manual reset만 |
| COOLDOWN | any | any | any | 일시적 차단, 자동 해제 가능 |

---

### 4.2 StopStatus 서브상태 (4개)

**목적**: State는 6개로 고정하되, IN_POSITION일 때 Stop Loss 주문 상태를 별도 추적

**실거래 문제**: IN_POSITION인데 Stop이 거절/취소/만료될 수 있음 → 청산 위험

| StopStatus | 의미 | 허용 시간 | 복구 방법 | HALT 조건 |
|-----------|------|----------|----------|-----------|
| **ACTIVE** | Stop 주문 활성 (정상) | - | - | - |
| **PENDING** | Stop 설치/갱신 중 (일시적) | 제한 없음 (API 응답 대기) | Amend 완료 또는 재시도 | - |
| **MISSING** | Stop 없음 (비정상, 즉시 복구 필요) | **최대 10초** | StopIntent(PLACE) 즉시 발행 | 5회 복구 실패 시 → ERROR |
| **ERROR** | Stop 복구 실패 (치명적) | 즉시 HALT | - | **즉시 HALT** (stop_loss_unrecoverable) |

**전이 규칙**:
```
ENTRY_PENDING → IN_POSITION: stop_status = PENDING → place_stop_loss() → ACTIVE
IN_POSITION + PARTIAL_FILL: stop_status = ACTIVE → AMEND 요청 → PENDING → ACTIVE
IN_POSITION + Stop 취소/거절: stop_status = MISSING → 복구 시도 (최대 5회)
```

**금지 사항**:
- IN_POSITION인데 stop_status를 확인하지 않음
- MISSING 상태를 방치 (10초 초과 허용 불가)
- ERROR 상태인데 계속 운용

---

### 4.3 Event 정의 (6개 이벤트)

**SSOT**: [src/domain/events.py](../../src/domain/events.py)

| EventType | 의미 | 우선순위 | 발생 시점 | 필수 필드 |
|-----------|------|----------|----------|----------|
| **LIQUIDATION** | 강제 청산 | **1 (최우선)** | 청산가 도달, 시스템 청산 | order_id, timestamp |
| **ADL** | 자동감소 (Auto Deleveraging) | **2** | 시장 극단 상황, 거래소 강제 감소 | position_qty_after (필수) |
| **FILL** | 완전 체결 | 3 | 주문 전량 체결 완료 | filled_qty, filled_price |
| **PARTIAL_FILL** | 부분 체결 | 4 | 주문 일부 체결 | filled_qty, filled_price |
| **REJECT** | 주문 거절 | 5 | 거래소 규칙 위반, 잔고 부족 등 | order_id, timestamp |
| **CANCEL** | 주문 취소 | 6 | 사용자/시스템 취소, timeout | filled_qty (0 또는 부분체결량) |

**우선순위**: `LIQUIDATION > ADL > FILL > PARTIAL_FILL > REJECT > CANCEL`

**Emergency Events**:
- **LIQUIDATION**: 모든 상태에서 최우선 처리 → **즉시 HALT**
- **ADL**: IN_POSITION에서만 처리 (qty 감소 또는 FLAT)

**ExecutionEvent Dataclass** ([src/domain/events.py:15](../../src/domain/events.py#L15)):
```python
@dataclass
class ExecutionEvent:
    type: EventType               # 이벤트 타입
    order_id: str                # 주문 ID
    filled_qty: int              # 체결 수량 (contracts)
    filled_price: float          # 체결 가격 (USD)
    timestamp: float             # 타임스탬프 (Unix seconds)
    position_qty_after: Optional[int] = None  # ADL 후 포지션 수량 (ADL만 필수)
```

---

### 4.4 상태 전이 테이블 (25+ 규칙)

**SSOT**: [src/application/transition.py](../../src/application/transition.py)

모든 상태 전이는 `transition()` 순수 함수에서만 처리됩니다.

#### 4.4.1 ENTRY_PENDING 전이 규칙

| 현재 상태 | Event | 조건 | 새 상태 | Position | Intents | 비고 |
|----------|-------|------|---------|----------|---------|------|
| ENTRY_PENDING | FILL | - | IN_POSITION | qty=filled_qty, stop_status=PENDING | StopIntent(PLACE) | 완전 체결 → Stop 즉시 설치 |
| ENTRY_PENDING | PARTIAL_FILL | - | IN_POSITION | qty=filled_qty, entry_working=True, stop_status=PENDING | StopIntent(PLACE) | **치명적 규칙**: 부분체결 즉시 IN_POSITION 전환 |
| ENTRY_PENDING | CANCEL | filled_qty > 0 | IN_POSITION | qty=filled_qty, stop_status=PENDING | StopIntent(PLACE) | 부분체결 후 취소 → Stop 필수 |
| ENTRY_PENDING | CANCEL | filled_qty = 0 | FLAT | None | - | 체결 없이 취소 |
| ENTRY_PENDING | REJECT | - | FLAT | None | - | 주문 거절 |
| ENTRY_PENDING | - | pending_order=None | HALT | None | HaltIntent(entry_pending_state_without_pending_order) | **Safety Gate**: 상태 불일치 |

#### 4.4.2 IN_POSITION 전이 규칙

| 현재 상태 | Event | 조건 | 새 상태 | Position | Intents | 비고 |
|----------|-------|------|---------|----------|---------|------|
| IN_POSITION | ADL | qty_after = 0 | FLAT | None | - | ADL로 포지션 완전 청산 |
| IN_POSITION | ADL | qty_after > 0 | IN_POSITION | qty=qty_after, entry_working=False | StopIntent(AMEND) | ADL로 수량 감소 → Stop 갱신 |
| IN_POSITION | ADL | qty_after 없음 | HALT | None | HaltIntent(adl_event_missing_position_qty_after) | **무결성 검증 실패** |
| IN_POSITION | PARTIAL_FILL | entry_working=True, order_id 일치 | IN_POSITION | qty 증가 (+ filled_qty) | StopIntent(AMEND) | Entry 잔량 추가 체결 |
| IN_POSITION | FILL | entry_working=True, order_id 일치 | IN_POSITION | qty 증가, entry_working=False | StopIntent(AMEND) | Entry 완전 체결 |
| IN_POSITION | FILL/PARTIAL_FILL | filled_qty ≤ 0 | HALT | None | HaltIntent(invalid_filled_qty_non_positive) | **Invalid qty 방어** |

#### 4.4.3 EXIT_PENDING 전이 규칙

| 현재 상태 | Event | 조건 | 새 상태 | Position | Intents | 비고 |
|----------|-------|------|---------|----------|---------|------|
| EXIT_PENDING | FILL | remaining_qty >= 0 | FLAT | None | - | 정상 청산 완료 |
| EXIT_PENDING | FILL | remaining_qty < 0 | HALT | None | HaltIntent(exit_fill_exceeded_position_qty) | **과체결 감지** |
| EXIT_PENDING | PARTIAL_FILL | remaining_qty >= 0 | EXIT_PENDING | qty 감소 | - | 부분 청산 (잔량 대기) |
| EXIT_PENDING | PARTIAL_FILL | remaining_qty < 0 | HALT | None | HaltIntent(exit_partial_fill_exceeded_position_qty) | **과체결 감지** |
| EXIT_PENDING | REJECT | - | EXIT_PENDING | 유지 | - | 재시도 대기 |
| EXIT_PENDING | CANCEL | - | EXIT_PENDING | 유지 | - | 재시도 대기 |

#### 4.4.4 FLAT 전이 규칙

| 현재 상태 | Event | 조건 | 새 상태 | Position | Intents | 비고 |
|----------|-------|------|---------|----------|---------|------|
| FLAT | FILL | - | HALT | None | HaltIntent(unexpected_fill_while_flat) | **유령 체결 감지** |
| FLAT | 기타 | - | FLAT | None | - | 무시 |

#### 4.4.5 Emergency (모든 상태)

| 현재 상태 | Event | 조건 | 새 상태 | Position | Intents | 비고 |
|----------|-------|------|---------|----------|---------|------|
| **ANY** | LIQUIDATION | - | HALT | None | HaltIntent(liquidation_event_requires_immediate_halt) | **최우선 처리** (transition.py:70-71) |

---

### 4.5 Intent 시스템

**SSOT**: [src/domain/intent.py](../../src/domain/intent.py)

`transition()` 함수는 상태 전이 결과와 함께 **Intent**(행동 의도)를 반환합니다. Intent는 부수효과(Side Effect)를 명시적으로 표현하는 도메인 계약입니다.

#### TransitionIntents Dataclass

```python
@dataclass
class TransitionIntents:
    stop_intent: Optional[StopIntent] = None           # Stop 갱신 의도
    halt_intent: Optional[HaltIntent] = None           # HALT 의도
    cancel_intent: Optional[CancelOrderIntent] = None  # 주문 취소 의도
    log_intent: Optional[LogIntent] = None            # 로그 기록 의도
    exit_intent: Optional[ExitIntent] = None          # 강제 청산 의도
    entry_blocked: bool = False                       # 진입 차단 플래그
```

#### StopIntent (Stop Loss 관리)

```python
@dataclass
class StopIntent:
    action: str          # "PLACE" / "AMEND" / "CANCEL_AND_PLACE"
    desired_qty: int     # 목표 수량 (contracts)
    reason: str          # 의도 발생 이유
```

**사용 시나리오**:
- **PLACE**: ENTRY_PENDING → IN_POSITION 전환 시 (Stop 없음 → 즉시 설치)
- **AMEND**: IN_POSITION에서 qty 변경 시 (PARTIAL_FILL, ADL)
- **CANCEL_AND_PLACE**: Amend 실패 5회 후 (완전 재설치)

#### HaltIntent (시스템 중단)

```python
@dataclass
class HaltIntent:
    reason: str          # HALT 사유 (예: "liquidation_event_requires_immediate_halt")
    context: dict = {}   # 추가 컨텍스트
```

**HALT 트리거 사유**:
- LIQUIDATION 이벤트
- 유령 체결 (FLAT에서 FILL)
- 과체결 (EXIT_PENDING에서 remaining_qty < 0)
- 무결성 오류 (ADL event에 position_qty_after 없음, filled_qty ≤ 0)
- 상태 불일치 (ENTRY_PENDING인데 pending_order=None)

#### ExitIntent (강제 청산)

```python
@dataclass
class ExitIntent:
    qty: int             # 청산 수량
    reason: str          # 청산 사유 (예: "stop_hit", "emergency_drop")
```

**사용 시나리오**:
- Stop hit (exit_manager.py)
- Emergency drop (-10%/-20%)

---

### 4.6 전이 흐름 다이어그램

#### 정상 흐름 (Happy Path)

```
[FLAT]
  │
  ├─ Entry 주문 발주
  │
  ▼
[ENTRY_PENDING]
  │
  ├─ FILL / PARTIAL_FILL
  │
  ▼
[IN_POSITION] ◄──── PARTIAL_FILL (entry_working=True)
  │         │
  │         └─ qty 증가, StopIntent(AMEND)
  │
  ├─ Exit 주문 발주 (Stop hit / Profit target)
  │
  ▼
[EXIT_PENDING]
  │
  ├─ PARTIAL_FILL (부분 청산)
  │     └─ EXIT_PENDING 유지, qty 감소
  │
  ├─ FILL (완전 청산)
  │
  ▼
[FLAT]
```

#### 비정상 흐름 (Emergency Path)

```
[ANY STATE]
  │
  ├─ LIQUIDATION
  │     └─ 최우선 처리
  │
  ├─ 유령 체결 (FLAT + FILL)
  │
  ├─ 과체결 (EXIT_PENDING)
  │
  ├─ 무결성 오류 (ADL, filled_qty≤0)
  │
  ▼
[HALT]
  │
  └─ Manual reset (.halt 파일 삭제)
     └─ FLAT
```

#### ADL 특수 흐름

```
[IN_POSITION]
  │
  ├─ ADL (position_qty_after = 0)
  │     └─ FLAT
  │
  ├─ ADL (position_qty_after > 0)
  │     └─ IN_POSITION (qty 감소, StopIntent(AMEND))
  │
  └─ ADL (position_qty_after 없음)
        └─ HALT (무결성 오류)
```

---

## 5. Core Flows

**SSOT**: [FLOW.md] Section 2 + [src/application/](../../src/application/)

### 5.1 Entry Flow (FLAT → IN_POSITION)

**전제 조건**: State = FLAT, Entry gates 8개 통과

**Sequence**:
```
1. [entry_allowed.py] Entry gates 검증 (8 gates)
   ├─ HALT/COOLDOWN 상태 확인
   ├─ Cooldown timeout + Max trades/day
   ├─ Stage params (Leverage, Loss budget)
   ├─ ATR (변동성)
   ├─ EV (Expected Value)
   ├─ Maker/Taker 정책
   ├─ Winrate/Streak 배수
   └─ One-way mode

2. [signal_generator.py] Grid signal 생성
   ├─ MA slope → Regime (trend_up/down/ranging/high_vol)
   ├─ Grid spacing (ATR * multiplier)
   └─ Entry price, direction (LONG/SHORT)

3. [sizing.py] Position size 계산
   ├─ Loss budget 기반 (Linear USDT 공식)
   ├─ Leverage, Stop distance
   └─ qty (contracts)

4. [order_executor.py] Entry 주문 발주
   ├─ Bybit REST API: POST /v5/order/create
   ├─ orderLinkId = SHA1({signal_id}_{direction})
   └─ Idempotency (DuplicateOrderError 방지)

5. State 전환: FLAT → ENTRY_PENDING
   ├─ pending_order 저장 (order_id, signal_id, qty, price)
   └─ entry_allowed = False

6. [WebSocket] ExecutionEvent 수신
   ├─ FILL / PARTIAL_FILL → transition()
   └─ EventRouter → transition(ENTRY_PENDING, event)

7. [transition.py] ENTRY_PENDING → IN_POSITION
   ├─ Position 생성 (qty, entry_price, direction, signal_id)
   ├─ stop_status = PENDING
   ├─ entry_working = (event == PARTIAL_FILL)
   └─ StopIntent(PLACE, qty, reason)

8. [stop_manager.py] Stop Loss 설치
   ├─ [order_executor.py] place_stop_loss()
   ├─ Conditional Order (orderType=Market, triggerBy=LastPrice, reduceOnly=True)
   └─ stop_status: PENDING → ACTIVE

9. [trade_logger.py] Entry log 기록
   └─ Trade log v1.0 (order_id, fills, slippage, latency, market_regime)
```

**핵심 규칙**:
- **PARTIAL_FILL 즉시 IN_POSITION**: 부분체결 시에도 즉시 Stop Loss 설치 (치명적 규칙)
- **Idempotency**: orderLinkId 기반 중복 주문 방지
- **Stop 필수**: IN_POSITION 진입 즉시 StopIntent(PLACE) 발행, 10초 내 설치 완료

---

### 5.2 Exit Flow (IN_POSITION → FLAT)

**전제 조건**: State = IN_POSITION, Position.qty > 0, stop_status = ACTIVE

**Sequence (정상 Exit - Stop Hit)**:
```
1. [Tick Loop] 매 tick마다 Mark price 조회

2. [exit_manager.py] check_stop_hit()
   ├─ LONG: current_price ≤ stop_price
   ├─ SHORT: current_price ≥ stop_price
   └─ Stop hit 감지 → ExitIntent(qty, reason="stop_hit")

3. [Orchestrator] ExitIntent 처리
   ├─ State 전환: IN_POSITION → EXIT_PENDING
   ├─ exit_order 발주 (Market order, reduceOnly=True)
   └─ pending_order 저장 (exit order_id)

4. [WebSocket] ExecutionEvent 수신 (Exit order)
   ├─ PARTIAL_FILL → qty 감소, EXIT_PENDING 유지
   └─ FILL → transition(EXIT_PENDING, FILL)

5. [transition.py] EXIT_PENDING → FLAT
   ├─ remaining_qty = position.qty - filled_qty
   ├─ if remaining_qty < 0: HALT (과체결)
   ├─ if remaining_qty = 0: → FLAT
   └─ Position = None

6. [trade_logger.py] Exit log 기록
   ├─ Realized PnL = (exit_price - entry_price) * qty * direction
   ├─ Slippage = |executed_price - expected_price|
   └─ Trade duration, Fee

7. [metrics_tracker.py] Metrics 업데이트
   ├─ Winrate 계산 (최근 50 거래)
   ├─ Win/Loss streak 업데이트
   └─ Size multiplier 재계산
```

**Sequence (비정상 Exit - LIQUIDATION)**:
```
1. [WebSocket] ExecutionEvent.LIQUIDATION 수신

2. [transition.py] Emergency handler (최우선 처리)
   ├─ 모든 상태에서 즉시 HALT
   ├─ HaltIntent(reason="liquidation_event_requires_immediate_halt")
   └─ Position = None (청산됨)

3. [halt_logger.py] HALT log 기록
   └─ Reason, Context (state, position, event)

4. Manual reset 필요 (.halt 파일 삭제)
```

**Sequence (비정상 Exit - ADL)**:
```
1. [WebSocket] ExecutionEvent.ADL 수신

2. [transition.py] IN_POSITION + ADL
   ├─ if position_qty_after = 0: → FLAT
   ├─ if position_qty_after > 0:
   │    ├─ Position.qty = position_qty_after
   │    ├─ StopIntent(AMEND, qty_after, reason="adl_reduced_position")
   │    └─ IN_POSITION 유지
   └─ if position_qty_after 없음: → HALT (무결성 오류)

3. [stop_manager.py] Stop Loss 갱신 (qty_after > 0인 경우)
   ├─ Amend 우선 (20% delta + 2초 debounce)
   └─ stop_status: ACTIVE → PENDING → ACTIVE
```

---

### 5.3 Stop Management Flow

**SSOT**: [src/application/stop_manager.py](../../src/application/stop_manager.py)

#### Stop Loss 생애주기

```
[PENDING] (설치/갱신 중)
   │
   ├─ place_stop_loss() 성공
   │     └─ ACTIVE
   │
   ├─ amend_stop_loss() 진행 중
   │     └─ PENDING 유지 (응답 대기)
   │
   ├─ API 실패 (5회 미만)
   │     └─ 재시도
   │
   └─ API 실패 (5회 이상)
         └─ ERROR → HALT

[ACTIVE] (정상)
   │
   ├─ Position qty 변경 (PARTIAL_FILL, ADL)
   │     ├─ 20% delta AND 2초 debounce
   │     ├─ StopIntent(AMEND)
   │     └─ PENDING
   │
   ├─ Stop 취소/거절 감지
   │     └─ MISSING
   │
   └─ Stop hit (price <= stop_price)
         └─ ExitIntent 발행

[MISSING] (비정상, 복구 필요)
   │
   ├─ 즉시 복구 시도
   │     ├─ StopIntent(PLACE)
   │     └─ PENDING
   │
   ├─ 복구 실패 (5회 미만)
   │     └─ 재시도 (최대 10초)
   │
   └─ 복구 실패 (5회 이상)
         └─ ERROR → HALT

[ERROR] (치명적)
   │
   └─ 즉시 HALT (stop_loss_unrecoverable)
```

#### Stop 갱신 정책 (should_update_stop)

```python
# 20% delta + 2초 debounce
delta_pct = abs(current_qty - last_stop_qty) / last_stop_qty
time_since_last_update = now() - last_stop_update_time

if delta_pct >= 0.20 AND time_since_last_update >= 2.0:
    StopIntent(AMEND, current_qty, reason="position_qty_changed")
```

#### Stop 우선순위 (determine_stop_action)

1. **Amend 우선** (Stop 공백 방지):
   - 기존 Stop이 ACTIVE → Amend API 호출
   - 실패 시 → PENDING 유지, 재시도

2. **Cancel-and-Place** (Amend 실패 5회 후):
   - 기존 Stop 취소 → 새 Stop 설치
   - Stop 공백 발생 위험 (최소화 노력)

3. **Place** (MISSING → 복구):
   - Stop 없음 → 즉시 설치
   - 10초 내 완료 필수

---

**Phase 2 완료**: Section 4-5 작성 완료 (State Machine + Core Flows)

---

## 6. Function Reference

Application Layer의 핵심 비즈니스 로직 함수들을 설명합니다.

**SSOT 참조**:
- **FLOW.md Section 2-3**: Entry/Exit Flow, Gate 순서
- **account_builder_policy.md Section 5, 10**: Stage Parameters, Position Sizing
- **transition.py**: 상태 전환 로직 (Section 4 참조)

---

### 6.1 Entry Functions

Entry 진입 가능 여부 검증, 신호 생성, 포지션 사이징 함수입니다.

#### 6.1.1 check_entry_allowed()

Entry gates 검증 (8 gates)

**함수 시그니처** ([src/application/entry_allowed.py:79](src/application/entry_allowed.py#L79)):
```python
def check_entry_allowed(
    state: State,
    stage: StageParams,
    trades_today: int,
    atr_pct_24h: float,
    signal: SignalContext,
    winrate: float,
    position_mode: str,
    cooldown_until: float | None,
    current_time: float | None = None,
) -> EntryDecision:
```

**파라미터**:
- `state`: 현재 상태 (State enum)
- `stage`: Stage 파라미터 (Policy Section 5)
  - `max_trades_per_day`: 최대 거래 횟수/일
  - `atr_pct_24h_min`: 최소 ATR (pct)
  - `ev_fee_multiple_k`: EV gate 계수
  - `maker_only_default`: Maker-only 모드
- `trades_today`: 오늘 거래 횟수
- `atr_pct_24h`: 24시간 ATR (pct, 예: 0.03 = 3%)
- `signal`: Signal 컨텍스트
  - `expected_profit_usd`: 예상 수익 (USD)
  - `estimated_fee_usd`: 예상 수수료 (USD)
  - `is_maker`: Maker 주문 여부
- `winrate`: 현재 winrate (0.0~1.0)
- `position_mode`: Position mode ("MergedSingle" = one-way)
- `cooldown_until`: COOLDOWN timeout 시각
- `current_time`: 현재 시각 (cooldown 검증용)

**리턴**:
- `EntryDecision`: 진입 허용 여부 + 거절 사유
  - `allowed`: 진입 허용 여부 (bool)
  - `reject_reason`: 거절 사유 (str, allowed=False일 때만)

**Gate 순서** (고정, FLOW.md Section 2):
1. HALT 상태 → REJECT
2a. COOLDOWN (timeout 전) → REJECT
2b. max_trades_per_day 초과 → REJECT
3. stage params 검증 (현재는 생략)
4. ATR < 임계치 → REJECT
5. EV gate (expected_profit < fee * K) → REJECT
6. maker-only 위반 → REJECT
7. winrate gate (현재는 생략)
8. one-way mode 위반 → REJECT

**코드 예제** ([src/application/entry_allowed.py:120-158](src/application/entry_allowed.py#L120-L158)):
```python
# Gate 1: HALT 상태
if state == State.HALT:
    return EntryDecision(allowed=False, reject_reason="state_halt")

# Gate 4: ATR < 임계치
if atr_pct_24h < stage.atr_pct_24h_min:
    return EntryDecision(allowed=False, reject_reason="atr_too_low")

# Gate 5: EV gate
min_expected_profit = signal.estimated_fee_usd * stage.ev_fee_multiple_k
if signal.expected_profit_usd < min_expected_profit:
    return EntryDecision(allowed=False, reject_reason="ev_insufficient")

# 모든 gate 통과
return EntryDecision(allowed=True, reject_reason=None)
```

**SSOT 참조**:
- **FLOW.md Section 2**: Gate 순서 고정
- **account_builder_policy.md Section 5**: Stage Parameters

---

#### 6.1.2 generate_signal()

Grid 전략 기반 신호 생성 (Regime-aware)

**함수 시그니처** ([src/application/signal_generator.py:77](src/application/signal_generator.py#L77)):
```python
def generate_signal(
    current_price: float,
    last_fill_price: Optional[float],
    grid_spacing: float,
    qty: int = 0,
    funding_rate: float = 0.0001,
    ma_slope_pct: float = 0.0,
) -> Optional[Signal]:
```

**파라미터**:
- `current_price`: 현재 가격 (USD)
- `last_fill_price`: 마지막 체결 가격 (None이면 FLAT 상태)
- `grid_spacing`: Grid 간격 (USD)
- `qty`: 거래 수량 (contracts)
- `funding_rate`: Funding rate (예: 0.0001 = 0.01%)
- `ma_slope_pct`: MA slope (% 단위)

**리턴**:
- `Signal | None`: 거래 신호 (없으면 None)
  - `side`: "Buy" or "Sell"
  - `price`: 신호 발생 시점 가격
  - `qty`: 거래 수량 (contracts)

**신호 생성 규칙**:
- **첫 진입** (last_fill_price=None): Regime-aware 방향 결정
  - Trend regime (abs(ma_slope) >= 0.5%): MA slope 방향 우선
  - Range regime (abs(ma_slope) < 0.5%): Funding 극단값 참고
- **Grid up**: current_price >= last_fill_price + grid_spacing → Sell
- **Grid down**: current_price <= last_fill_price - grid_spacing → Buy
- **Grid 범위 내**: No signal

**코드 예제** ([src/application/signal_generator.py:108-135](src/application/signal_generator.py#L108-L135)):
```python
# 첫 진입: Regime-aware 방향 결정
if last_fill_price is None:
    regime, direction = determine_regime(ma_slope_pct)

    if regime == "trend":
        # Trend regime: MA slope 방향 우선
        side = "Buy" if direction == "up" else "Sell"
        return Signal(side=side, price=current_price, qty=qty)

    else:
        # Range regime: Funding 극단값만 허용
        if abs(funding_rate) < F_EXTREME:
            return None  # 과열 아님, 진입 보류

        # Funding 극단 → 역추세 진입
        side = "Sell" if funding_rate > 0 else "Buy"
        return Signal(side=side, price=current_price, qty=qty)

# Grid up: 가격 상승 → Sell 신호
if current_price >= last_fill_price + grid_spacing:
    return Signal(side="Sell", price=current_price, qty=qty)

# Grid down: 가격 하락 → Buy 신호
if current_price <= last_fill_price - grid_spacing:
    return Signal(side="Buy", price=current_price, qty=qty)

# Grid 범위 내 → 신호 없음
return None
```

**SSOT 참조**:
- **signal_generator.py Line 18-21**: Regime 임계값 정의 (T_TREND=0.5, F_EXTREME=0.01)

---

#### 6.1.3 calculate_contracts()

Position sizing (loss budget + margin 제약) — Linear USDT

**함수 시그니처** ([src/application/sizing.py:70](src/application/sizing.py#L70)):
```python
def calculate_contracts(params: SizingParams) -> SizingResult:
```

**파라미터** (`SizingParams` dataclass):
- `max_loss_usdt`: 최대 손실 (USDT)
- `entry_price_usd`: 진입가 (USD)
- `stop_distance_pct`: Stop 거리 (pct, 예: 0.03 = 3%)
- `leverage`: 레버리지 (예: 3.0)
- `equity_usdt`: 현재 equity (USDT)
- `fee_rate`: 수수료율 (예: 0.0001)
- `direction`: "LONG" or "SHORT" (Linear에서는 영향 없음)
- `qty_step`: Lot size (예: 1 contract)
- `tick_size`: Tick size (예: 0.5 USD)
- `contract_size`: Contract size in BTC (기본: 0.001)

**리턴** (`SizingResult`):
- `contracts`: 계산된 contracts (0이면 실패)
- `reject_reason`: 거절 사유 (contracts=0일 때만)

**계산 단계**:
1. Loss budget 기준 qty 계산 (Linear 공식)
2. Margin 기준 qty 계산
3. min(loss_based, margin_based)
4. Qty → Contracts 변환 (contract_size 기준)
5. Tick/Lot size 보정
6. 보정 후 재검증 (margin feasibility)
7. 최소 수량 검증

**Linear 공식**:
```
loss_usdt_at_stop = qty * entry_price * stop_distance_pct
qty = max_loss_usdt / (entry_price * stop_distance_pct)
```

**코드 예제** ([src/application/sizing.py:105-143](src/application/sizing.py#L105-L143)):
```python
# Step 1: Loss budget 기준 qty 계산 (Linear 공식)
qty_from_loss = params.max_loss_usdt / (
    params.entry_price_usd * params.stop_distance_pct
)

# Step 2: Margin 기준 qty 계산
available_usdt = params.equity_usdt * 0.8
max_notional_usdt = available_usdt * params.leverage
qty_from_margin = max_notional_usdt / params.entry_price_usd

# Step 3: 둘 중 작은 값
qty = min(qty_from_loss, qty_from_margin)

# Step 4: Qty → Contracts 변환 (Bybit Linear BTCUSDT: 1 contract = 0.001 BTC)
contracts = int(qty / params.contract_size)

# Step 5: Tick/Lot size 보정
contracts = int(contracts / params.qty_step) * params.qty_step

# Step 6: 최소 수량 검증
if contracts < params.qty_step:
    return SizingResult(contracts=0, reject_reason="qty_below_minimum")

# Step 7: 보정 후 재검증 (margin feasibility)
actual_qty = contracts * params.contract_size
notional_usdt = actual_qty * params.entry_price_usd
required_margin_usdt = notional_usdt / params.leverage
fee_buffer_usdt = notional_usdt * params.fee_rate * 2  # entry + exit

if required_margin_usdt + fee_buffer_usdt > params.equity_usdt:
    return SizingResult(contracts=0, reject_reason="margin_insufficient")

# 성공
return SizingResult(contracts=contracts, reject_reason=None)
```

**SSOT 참조**:
- **FLOW.md Section 3.4**: Position Sizing (Linear 공식)
- **account_builder_policy.md Section 10**: Bybit Linear USDT
- **ADR-0002**: Inverse to Linear USDT Migration

---

### 6.2 Exit Functions

Exit 조건 확인 및 Exit intent 생성 함수입니다.

#### 6.2.1 check_stop_hit()

Stop loss 도달 확인

**함수 시그니처** ([src/application/exit_manager.py:21](src/application/exit_manager.py#L21)):
```python
def check_stop_hit(current_price: float, position: Position) -> bool:
```

**파라미터**:
- `current_price`: 현재 가격 (USD)
- `position`: 현재 포지션
  - `direction`: Direction.LONG or Direction.SHORT
  - `stop_price`: Stop 가격 (None이면 확인 불가)

**리턴**:
- `bool`: Stop loss 도달 여부

**규칙**:
- **LONG**: current_price <= stop_price
- **SHORT**: current_price >= stop_price
- stop_price가 None이면 False (확인 불가)

**코드 예제** ([src/application/exit_manager.py:37-47](src/application/exit_manager.py#L37-L47)):
```python
# stop_price가 None이면 확인 불가
if position.stop_price is None:
    return False

# LONG: 가격 하락 → stop_price 이하
if position.direction == Direction.LONG:
    return current_price <= position.stop_price

# SHORT: 가격 상승 → stop_price 이상
return current_price >= position.stop_price
```

---

#### 6.2.2 create_exit_intent()

Exit intent 생성 (강제 청산)

**함수 시그니처** ([src/application/exit_manager.py:50](src/application/exit_manager.py#L50)):
```python
def create_exit_intent(position: Position, reason: str) -> TransitionIntents:
```

**파라미터**:
- `position`: 현재 포지션
- `reason`: Exit 이유 (stop_loss_hit, manual_exit, etc.)

**리턴**:
- `TransitionIntents`: Exit intent 포함
  - `exit_intent.qty`: position.qty (전량 청산)
  - `exit_intent.order_type`: "Market" (시장가)
  - `exit_intent.reason`: 청산 이유

**코드 예제** ([src/application/exit_manager.py:65-75](src/application/exit_manager.py#L65-L75)):
```python
intents = TransitionIntents()

# Exit intent 생성
intents.exit_intent = ExitIntent(
    qty=position.qty,
    reason=reason,
    order_type="Market",
    stop_price=position.stop_price,  # For logging
)

return intents
```

---

#### 6.2.3 should_update_stop()

Stop 갱신 필요 여부 판단

**함수 시그니처** ([src/application/stop_manager.py:25](src/application/stop_manager.py#L25)):
```python
def should_update_stop(
    position_qty: int,
    stop_qty: int,
    last_stop_update_at: float,
    current_time: float,
    threshold_pct: float = 0.20,
    debounce_seconds: float = 2.0,
    entry_working: bool = False,
) -> bool:
```

**파라미터**:
- `position_qty`: 현재 포지션 수량
- `stop_qty`: 현재 stop 수량
- `last_stop_update_at`: 마지막 stop 갱신 시각 (timestamp)
- `current_time`: 현재 시각 (timestamp)
- `threshold_pct`: Delta threshold (기본 20%)
- `debounce_seconds`: Debounce 간격 (기본 2초)
- `entry_working`: Entry order 활성 여부 (True면 stop 갱신 금지)

**리턴**:
- `bool`: stop 갱신 필요 여부

**검증 순서**:
1. entry_working=True → 갱신 차단
2. stop_qty=0 → 갱신 필요 (초기 상태)
3. Delta < 20% → 갱신 불필요
4. Debounce 2초 이내 → 차단
5. Delta >= 20% + Debounce 통과 → 갱신 필요

**코드 예제** ([src/application/stop_manager.py:56-80](src/application/stop_manager.py#L56-L80)):
```python
# (1) entry_working=True → 갱신 차단
if entry_working:
    return False

# (2) Delta 계산
if stop_qty == 0:
    return True

delta = abs(position_qty - stop_qty)
delta_pct = delta / stop_qty if stop_qty > 0 else 0.0

# (3) Delta threshold 체크
if delta_pct < threshold_pct:
    return False

# (4) Debounce 체크
time_since_last_update = current_time - last_stop_update_at
if time_since_last_update < debounce_seconds:
    return False

# (5) Delta >= 20% + Debounce 통과 → 갱신 필요
return True
```

**SSOT 참조**:
- **FLOW.md Section 2.5**: Stop Update Policy

---

#### 6.2.4 determine_stop_action()

Stop 갱신 action 결정

**함수 시그니처** ([src/application/stop_manager.py:83](src/application/stop_manager.py#L83)):
```python
def determine_stop_action(
    stop_status: StopStatus,
    amend_fail_count: int,
) -> str:
```

**파라미터**:
- `stop_status`: stop_status (ACTIVE/PENDING/MISSING/ERROR)
- `amend_fail_count`: Amend 실패 횟수

**리턴**:
- `str`: Action ("AMEND", "CANCEL_AND_PLACE", "PLACE")

**결정 규칙**:
1. stop_status=MISSING → "PLACE" (복구)
2. stop_status=ERROR → "CANCEL_AND_PLACE" (복구 실패)
3. amend_fail_count >= 2 → "CANCEL_AND_PLACE" (재시도 한계)
4. stop_status=ACTIVE, amend_fail_count < 2 → "AMEND" (우선)

**코드 예제** ([src/application/stop_manager.py:105-118](src/application/stop_manager.py#L105-L118)):
```python
# (1) stop_status=MISSING → PLACE (복구)
if stop_status == StopStatus.MISSING:
    return "PLACE"

# (2) stop_status=ERROR → CANCEL_AND_PLACE (복구 실패)
if stop_status == StopStatus.ERROR:
    return "CANCEL_AND_PLACE"

# (3) amend_fail_count >= 2 → CANCEL_AND_PLACE (재시도 한계)
if amend_fail_count >= 2:
    return "CANCEL_AND_PLACE"

# (4) stop_status=ACTIVE, amend_fail_count < 2 → AMEND 우선
return "AMEND"
```

**SSOT 참조**:
- **FLOW.md Section 2.5**: Amend 우선 규칙

---

### 6.3 Risk Functions

Session risk 메트릭 계산 및 추적 함수입니다.

#### 6.3.1 SessionRiskTracker

Trade history → Risk metrics 계산

**클래스** ([src/application/session_risk_tracker.py:56](src/application/session_risk_tracker.py#L56)):
```python
class SessionRiskTracker:
    """
    Session Risk Tracker — Trade history → Risk metrics

    역할:
    - Daily/Weekly PnL 계산 (UTC boundary 인식)
    - Loss streak 계산 (연속 손실 카운트)
    - Fee ratio 추적 (fee / notional)
    - Slippage 추적 (expected_price - filled_price)
    """
```

**주요 메서드**:

##### track_daily_pnl()

당일 realized PnL 계산 (UTC boundary 인식)

**시그니처** ([src/application/session_risk_tracker.py:67](src/application/session_risk_tracker.py#L67)):
```python
def track_daily_pnl(
    self,
    trades: List[Trade],
    current_date: Optional[datetime] = None
) -> float:
```

**파라미터**:
- `trades`: Trade 리스트 (closed_pnl, timestamp)
- `current_date`: 현재 날짜 (None이면 utcnow() 사용)

**리턴**:
- `float`: 당일 PnL 합계 (USD)

**코드 예제** ([src/application/session_risk_tracker.py:86-98](src/application/session_risk_tracker.py#L86-L98)):
```python
# 현재 날짜 (UTC)
if current_date is None:
    current_date = datetime.now(timezone.utc)

# 당일 시작 시각 (00:00:00 UTC)
today_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
today_start_ts = today_start.timestamp()

# 당일 거래만 필터링
daily_pnl = 0.0
for trade in trades:
    if trade.timestamp >= today_start_ts:
        daily_pnl += trade.closed_pnl

return daily_pnl
```

---

##### track_weekly_pnl()

주간 realized PnL 계산 (ISO 8601 Week)

**시그니처** ([src/application/session_risk_tracker.py:101](src/application/session_risk_tracker.py#L101)):
```python
def track_weekly_pnl(
    self,
    trades: List[Trade],
    current_date: Optional[datetime] = None
) -> float:
```

**파라미터**:
- `trades`: Trade 리스트
- `current_date`: 현재 날짜

**리턴**:
- `float`: 주간 PnL 합계 (USD)

**Week 정의**: ISO 8601 (Monday 00:00:00 UTC ~ Sunday 23:59:59 UTC)

**코드 예제** ([src/application/session_risk_tracker.py:125-137](src/application/session_risk_tracker.py#L125-L137)):
```python
# 이번 주 시작 (Monday 00:00:00 UTC)
# ISO weekday: Monday=1, Sunday=7
weekday = current_date.isoweekday()  # 1~7
days_since_monday = weekday - 1
this_week_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
this_week_start_ts = this_week_start.timestamp()

# 이번 주 거래만 필터링
weekly_pnl = 0.0
for trade in trades:
    if trade.timestamp >= this_week_start_ts:
        weekly_pnl += trade.closed_pnl

return weekly_pnl
```

---

##### calculate_loss_streak()

연속 손실 카운트

**시그니처** ([src/application/session_risk_tracker.py:140](src/application/session_risk_tracker.py#L140)):
```python
def calculate_loss_streak(self, trades: List[Trade]) -> int:
```

**파라미터**:
- `trades`: Trade 리스트

**리턴**:
- `int`: 연속 손실 카운트

**규칙**:
- 최근 거래부터 역순으로 스캔
- closed_pnl < 0이면 loss로 카운트
- closed_pnl >= 0이면 중단 (streak 끝)

**코드 예제** ([src/application/session_risk_tracker.py:158-168](src/application/session_risk_tracker.py#L158-L168)):
```python
# 최신 거래부터 역순 스캔 (timestamp 기준 정렬)
sorted_trades = sorted(trades, key=lambda t: t.timestamp, reverse=True)

loss_streak = 0
for trade in sorted_trades:
    if trade.closed_pnl < 0:
        loss_streak += 1
    else:
        # 첫 번째 non-loss에서 중단
        break

return loss_streak
```

**SSOT 참조**:
- **account_builder_policy.md Section 9**: Session Risk Policy (UTC boundary, Loss streak)

---

### 6.4 Order Execution

주문 실행 및 관리 함수입니다.

#### 6.4.1 place_entry_order()

Entry 주문 실행

**함수 시그니처** ([src/application/order_executor.py:72](src/application/order_executor.py#L72)):
```python
def place_entry_order(
    symbol: str,
    side: str,
    qty: int,
    price: float,
    signal_id: str,
    direction: str,
) -> OrderResult:
```

**파라미터**:
- `symbol`: 심볼 (예: "BTCUSD")
- `side`: "Buy" or "Sell"
- `qty`: 수량 (contracts)
- `price`: 가격 (USD)
- `signal_id`: Signal ID (idempotency key)
- `direction`: "LONG" or "SHORT"

**리턴**:
- `OrderResult`: 주문 결과
  - `order_id`: 주문 ID
  - `order_link_id`: orderLinkId
  - `status`: 주문 상태

**Raises**:
- `ValueError`: orderLinkId 길이 초과 (>36자)
- `DuplicateOrderError`: orderLinkId 중복

**주문 파라미터** (FLOW.md Section 4.5):
- `category`: "inverse" (또는 "linear")
- `positionIdx`: 0 (One-way 모드)
- `orderType`: "Limit"
- `orderLinkId`: "{signal_id}_{side}"

**코드 예제** ([src/application/order_executor.py:104-127](src/application/order_executor.py#L104-L127)):
```python
# orderLinkId 생성
order_link_id = f"{signal_id}_{side}"

# orderLinkId 길이 검증 (36자 제한)
if not validate_order_link_id(order_link_id):
    raise ValueError(f"orderLinkId too long or invalid: {order_link_id}")

# Idempotency 검증 (중복 방지)
if order_link_id in _order_store:
    # 기존 주문 반환 (idempotency)
    return _order_store[order_link_id]

# 주문 실행
order_id = f"order_{len(_order_store) + 1}"
result = OrderResult(
    order_id=order_id,
    order_link_id=order_link_id,
    status="New",
)

# Store 저장
_order_store[order_link_id] = result

return result
```

**SSOT 참조**:
- **FLOW.md Section 4.5**: Entry 주문 계약
- **FLOW.md Section 8**: Idempotency Key

---

#### 6.4.2 place_stop_loss()

Stop Loss 주문 실행 (Conditional Order)

**함수 시그니처** ([src/application/order_executor.py:130](src/application/order_executor.py#L130)):
```python
def place_stop_loss(
    symbol: str,
    qty: int,
    stop_price: float,
    direction: str,
    signal_id: str,
) -> OrderResult:
```

**파라미터**:
- `symbol`: 심볼 (예: "BTCUSD")
- `qty`: 수량 (contracts)
- `stop_price`: Stop 가격 (triggerPrice)
- `direction`: "LONG" or "SHORT"
- `signal_id`: Signal ID

**리턴**:
- `OrderResult`: 주문 결과
  - `order_type`: "Market"
  - `trigger_price`: stop_price
  - `trigger_direction`: 2 (LONG) / 1 (SHORT)
  - `reduce_only`: True
  - `position_idx`: 0
  - `side`: "Sell" (LONG) / "Buy" (SHORT)

**주문 파라미터** (FLOW.md Section 4.5):

**LONG Stop**:
- `orderType`: "Market"
- `triggerPrice`: stop_price
- `triggerDirection`: 2 (falling, LastPrice < triggerPrice)
- `triggerBy`: "LastPrice"
- `reduceOnly`: True
- `positionIdx`: 0
- `side`: "Sell" (LONG 청산)
- `orderLinkId`: "{signal_id}_stop_Sell"

**SHORT Stop**:
- `side`: "Buy" (SHORT 청산)
- `triggerDirection`: 1 (rising, LastPrice > triggerPrice)
- `orderLinkId`: "{signal_id}_stop_Buy"

**코드 예제** ([src/application/order_executor.py:166-196](src/application/order_executor.py#L166-L196)):
```python
# Direction별 파라미터 설정
if direction == "LONG":
    side = "Sell"  # LONG 청산
    trigger_direction = 2  # falling (LastPrice < triggerPrice)
elif direction == "SHORT":
    side = "Buy"  # SHORT 청산
    trigger_direction = 1  # rising (LastPrice > triggerPrice)
else:
    raise ValueError(f"Invalid direction: {direction}")

# orderLinkId 생성
order_link_id = f"{signal_id}_stop_{side}"

# 주문 실행
order_id = f"stop_{len(_order_store) + 1}"
result = OrderResult(
    order_id=order_id,
    order_link_id=order_link_id,
    status="New",
    order_type="Market",
    trigger_price=stop_price,
    trigger_direction=trigger_direction,
    reduce_only=True,
    position_idx=0,
    side=side,
)

return result
```

**SSOT 참조**:
- **FLOW.md Section 4.5**: Stop Loss 주문 계약
- **Section 1.4 Definitions**: Stop Loss 파라미터

---

#### 6.4.3 amend_stop_loss()

Stop 수량 갱신

**함수 시그니처** ([src/application/order_executor.py:199](src/application/order_executor.py#L199)):
```python
def amend_stop_loss(order_id: str, new_qty: int) -> AmendResult:
```

**파라미터**:
- `order_id`: 주문 ID
- `new_qty`: 새 수량

**리턴**:
- `AmendResult`: Amend 결과
  - `success`: 성공 여부
  - `updated_qty`: 갱신된 수량
  - `error`: 에러 메시지

**Raises**:
- `AmendNotSupported`: Bybit가 Amend 지원 안 함

**코드 예제** ([src/application/order_executor.py:217-222](src/application/order_executor.py#L217-L222)):
```python
# Amend 실패 시뮬레이션
if "unsupported" in order_id:
    return AmendResult(success=False, error="amend_not_supported")

# Amend 성공
return AmendResult(success=True, updated_qty=new_qty)
```

**SSOT 참조**:
- **FLOW.md Section 2.5**: Amend 우선 규칙 (공백 방지)

---

### 6.5 Event Processing

이벤트 라우팅 및 상태 전환 함수입니다.

#### 6.5.1 EventRouter

Execution Event 처리 → State Transition

**클래스** ([src/application/event_router.py:26](src/application/event_router.py#L26)):
```python
class EventRouter:
    """
    Execution Event Router (Stateless Thin Wrapper)

    역할:
    - 이벤트 정규화
    - transition() 호출 (전이 로직은 transition에만 존재)
    - 결과 전달

    ⚠️ 이 클래스는 전이 로직을 포함하지 않는다.
    """
```

**주요 메서드**:

##### handle_event()

Execution Event 처리

**시그니처** ([src/application/event_router.py:37](src/application/event_router.py#L37)):
```python
def handle_event(
    self,
    current_state: State,
    current_position: Optional[Position],
    event: ExecutionEvent,
    pending_order: Optional[PendingOrder] = None
) -> Tuple[State, Optional[Position], TransitionIntents]:
```

**파라미터**:
- `current_state`: 현재 상태
- `current_position`: 현재 포지션
- `event`: Execution event
- `pending_order`: 대기 중인 주문

**리턴**:
- `(new_state, new_position, intents)`: 새 상태, 새 포지션, 의도 목록

**코드 예제** ([src/application/event_router.py:59-70](src/application/event_router.py#L59-L70)):
```python
# 이벤트 정규화 (필요 시)
normalized_event = self._normalize_event(event)

# transition() 호출 (전이 로직의 유일한 진실)
new_state, new_position, intents = transition(
    current_state,
    current_position,
    normalized_event,
    pending_order
)

return new_state, new_position, intents
```

**설계 원칙**:
- **Thin Wrapper**: 전이 로직을 포함하지 않음
- **Stateless**: 상태를 인자로만 전달
- **Single Transition Truth**: transition()에만 전이 로직 존재

---

#### 6.5.2 transition()

순수 함수 State Transition

**함수 시그니처** ([src/application/transition.py:37](src/application/transition.py#L37)):
```python
def transition(
    current_state: State,
    current_position: Optional[Position],
    event: ExecutionEvent,
    pending_order: Optional[PendingOrder] = None
) -> Tuple[State, Optional[Position], TransitionIntents]:
```

**파라미터**:
- `current_state`: 현재 상태
- `current_position`: 현재 포지션 (IN_POSITION/EXIT_PENDING만)
- `event`: Execution event
- `pending_order`: 대기 중인 주문 (ENTRY_PENDING/EXIT_PENDING)

**리턴**:
- `(new_state, new_position, intents)`: 새 상태, 새 포지션, 의도 목록

**전이 규칙** (FLOW.md Section 2.5):
- ENTRY_PENDING + FILL → IN_POSITION
- ENTRY_PENDING + PARTIAL_FILL → IN_POSITION (entry_working=True)
- ENTRY_PENDING + REJECT → FLAT
- ENTRY_PENDING + CANCEL (filled_qty=0) → FLAT
- ENTRY_PENDING + CANCEL (filled_qty>0) → IN_POSITION
- EXIT_PENDING + FILL → FLAT
- EXIT_PENDING + REJECT/CANCEL → stay (재시도)
- FLAT + FILL (unexpected) → HALT
- LIQUIDATION → HALT (any state)
- ADL → IN_POSITION (수량 감소 or FLAT)
- IN_POSITION + PARTIAL_FILL/FILL → qty 증가

**코드 예제** ([src/application/transition.py:68-92](src/application/transition.py#L68-L92)):
```python
intents = TransitionIntents()

# Emergency events: LIQUIDATION만 최우선 처리 (FLOW 준수)
if event.type == EventType.LIQUIDATION:
    return _handle_emergency(current_state, event, intents)

# ENTRY_PENDING 상태 처리
if current_state == State.ENTRY_PENDING:
    return _handle_entry_pending(event, pending_order, intents)

# EXIT_PENDING 상태 처리
elif current_state == State.EXIT_PENDING:
    return _handle_exit_pending(current_position, event, intents)

# IN_POSITION 상태 처리
elif current_state == State.IN_POSITION:
    return _handle_in_position(current_position, event, intents)

# FLAT 상태에서 예상치 못한 이벤트
elif current_state == State.FLAT:
    return _handle_flat(event, intents)

# 기타 상태: 유지
return current_state, current_position, intents
```

**설계 원칙**:
- **Pure Function**: Side-effect 없음, I/O 금지
- **Oracle Testable**: 모든 전이 규칙 테스트 가능
- **Single Truth**: 전이 로직의 유일한 진실

**SSOT 참조**:
- **FLOW.md Section 2.5**: 상태 전이 규칙
- **Section 4.4**: 상태 전이 테이블 (25+ 규칙)

---

### 6.6 Market Analysis

시장 분석 및 지표 계산 함수입니다.

#### 6.6.1 ATRCalculator

ATR (Average True Range) 계산

**클래스** ([src/application/atr_calculator.py:34](src/application/atr_calculator.py#L34)):
```python
class ATRCalculator:
    """
    ATR Calculator

    역할:
    - 14-period ATR 계산 (True Range의 EMA)
    - ATR percentile 계산 (rolling 100-period)
    - Grid spacing 계산 (ATR * multiplier)
    """

    def __init__(self, period: int = 14, default_multiplier: float = 0.5):
        """
        Args:
            period: ATR period (기본: 14)
            default_multiplier: Grid spacing 기본 multiplier (기본: 0.5)
        """
```

**주요 메서드**:

##### calculate_atr()

14-period ATR 계산

**시그니처** ([src/application/atr_calculator.py:75](src/application/atr_calculator.py#L75)):
```python
def calculate_atr(self, klines: List[Kline]) -> float:
```

**파라미터**:
- `klines`: Kline 데이터 리스트 (최소 period+1개 필요)
  - `high`: 최고가
  - `low`: 최저가
  - `close`: 종가

**리턴**:
- `float`: ATR 값

**Raises**:
- `ValueError`: Kline 데이터 부족

**계산 방식**:
- TR = max(H-L, |H-PC|, |PC-L|) (where H=High, L=Low, PC=Previous Close)
- ATR = EMA of True Range (14-period)

**코드 예제** ([src/application/atr_calculator.py:95-111](src/application/atr_calculator.py#L95-L111)):
```python
# True Range 계산
true_ranges = []
for i in range(1, len(klines)):
    tr = self.calculate_true_range(klines[i], klines[i-1].close)
    true_ranges.append(tr)

# ATR 계산 (EMA of True Range)
# 첫 번째 ATR = 첫 period개의 평균
first_atr = sum(true_ranges[:self.period]) / self.period
atr = first_atr

# 나머지는 EMA 방식으로 계산
multiplier = 2.0 / (self.period + 1)
for i in range(self.period, len(true_ranges)):
    atr = (true_ranges[i] * multiplier) + (atr * (1 - multiplier))

return atr
```

---

##### calculate_grid_spacing()

Grid spacing 계산

**시그니처** ([src/application/atr_calculator.py:139](src/application/atr_calculator.py#L139)):
```python
def calculate_grid_spacing(
    self, atr: float, multiplier: float = None
) -> float:
```

**파라미터**:
- `atr`: ATR 값
- `multiplier`: Multiplier (기본: self.default_multiplier)

**리턴**:
- `float`: Grid spacing (USD)

**공식**:
```
Grid spacing = ATR * multiplier
```

**코드 예제** ([src/application/atr_calculator.py:153-157](src/application/atr_calculator.py#L153-L157)):
```python
if multiplier is None:
    multiplier = self.default_multiplier

return atr * multiplier
```

---

#### 6.6.2 MarketRegimeAnalyzer

Market regime 분류 (Trend vs Range)

**클래스** ([src/application/market_regime.py:38](src/application/market_regime.py#L38)):
```python
class MarketRegimeAnalyzer:
    """
    Market Regime Analyzer — Kline → Regime classification

    역할:
    - MA slope 계산 (SMA 기반 추세 강도)
    - Market regime 분류 (trending_up/down/ranging/high_vol)

    Regime 분류 규칙:
    - trending_up: ma_slope > 0.2%
    - trending_down: ma_slope < -0.2%
    - high_vol: atr_percentile > 70
    - ranging: |ma_slope| <= 0.2% and atr_percentile <= 70
    """

    def __init__(
        self,
        ma_period: int = 20,
        trend_threshold_pct: float = 0.2,
        high_vol_threshold_percentile: float = 70.0
    ):
```

**주요 메서드**:

##### calculate_ma_slope()

MA slope 계산

**시그니처** ([src/application/market_regime.py:71](src/application/market_regime.py#L71)):
```python
def calculate_ma_slope(self, klines: List[Kline]) -> float:
```

**파라미터**:
- `klines`: Kline 리스트 (최소 ma_period개 필요)

**리턴**:
- `float`: MA slope (%, 양수=상승, 음수=하락, 0=횡보)

**Raises**:
- `ValueError`: klines 데이터 부족

**계산 방식**:
1. 최근 N개 kline으로 현재 MA 계산
2. 최근 N-1개 kline으로 이전 MA 계산
3. Slope = (current_ma - previous_ma) / previous_ma * 100 (%)

**코드 예제** ([src/application/market_regime.py:94-107](src/application/market_regime.py#L94-L107)):
```python
# 현재 MA (최근 N개)
current_closes = [kline.close for kline in klines[-self.ma_period:]]
current_ma = sum(current_closes) / len(current_closes)

# 이전 MA (최근 N-1개, 1개 이전부터)
previous_closes = [kline.close for kline in klines[-(self.ma_period + 1):-1]]
previous_ma = sum(previous_closes) / len(previous_closes)

# Slope 계산 (%)
if previous_ma == 0:
    return 0.0

slope_pct = (current_ma - previous_ma) / previous_ma * 100.0

return slope_pct
```

---

##### classify_regime()

Market regime 분류

**시그니처** ([src/application/market_regime.py:110](src/application/market_regime.py#L110)):
```python
def classify_regime(
    self,
    ma_slope_pct: float,
    atr_percentile: float
) -> str:
```

**파라미터**:
- `ma_slope_pct`: MA slope (%)
- `atr_percentile`: ATR percentile (0~100)

**리턴**:
- `str`: Regime 분류 ("trending_up", "trending_down", "ranging", "high_vol")

**분류 규칙** (우선순위 순):
1. atr_percentile > high_vol_threshold → "high_vol"
2. ma_slope > trend_threshold → "trending_up"
3. ma_slope < -trend_threshold → "trending_down"
4. 그 외 → "ranging"

**코드 예제** ([src/application/market_regime.py:131-141](src/application/market_regime.py#L131-L141)):
```python
# 1. ATR 기준 고변동성 판단 (우선순위 1)
if atr_percentile > self.high_vol_threshold_percentile:
    return "high_vol"

# 2. MA slope 기준 추세 판단
if ma_slope_pct > self.trend_threshold_pct:
    return "trending_up"
elif ma_slope_pct < -self.trend_threshold_pct:
    return "trending_down"
else:
    return "ranging"
```

**SSOT 참조**:
- **account_builder_policy.md Section 11**: Entry Flow (Regime Filter)

---

**Section 6 완료**

Phase 3 작업 완료: Application Layer 핵심 함수 12개 모듈 문서화

- Entry Functions: check_entry_allowed, generate_signal, calculate_contracts
- Exit Functions: check_stop_hit, create_exit_intent, should_update_stop, determine_stop_action
- Risk Functions: SessionRiskTracker (track_daily_pnl, track_weekly_pnl, calculate_loss_streak)
- Order Execution: place_entry_order, place_stop_loss, amend_stop_loss
- Event Processing: EventRouter.handle_event, transition
- Market Analysis: ATRCalculator (calculate_atr, calculate_grid_spacing), MarketRegimeAnalyzer (calculate_ma_slope, classify_regime)

---

## 7. External Integrations

Infrastructure Layer의 외부 시스템 연동 및 안전 장치를 설명합니다.

**SSOT 참조**:
- **task_plan.md Phase 7**: Real API Integration (REST/WS 클라이언트 골격)
- **task_plan.md Phase 10**: Log Storage (JSONL, fsync policy)
- **task_plan.md Phase 9c**: Safety Systems (KillSwitch, Alert, Rollback)

---

### 7.1 Bybit REST API

Bybit REST API V5 클라이언트 (USDT/Coin-margined Futures)

#### 7.1.1 BybitRestClient

REST API 클라이언트 (골격, Contract tests only)

**클래스** ([src/infrastructure/exchange/bybit_rest_client.py:52](src/infrastructure/exchange/bybit_rest_client.py#L52)):
```python
class BybitRestClient:
    """
    Bybit REST API Client (골격만, Contract tests only)

    핵심 원칙:
    - 서명 생성 deterministic
    - Bybit 스펙 만족 (payload 검증)
    - Rate limit 헤더 처리 (X-Bapi-*)
    - retCode 10006 → backoff
    - Timeout/retry 정책
    - Testnet base_url 강제 assert (또는 BYBIT_TESTNET=false 확인)
    - API key 누락 → 프로세스 시작 거부 (fail-fast)
    - Clock 주입 (determinism)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        clock: Optional[Callable[[], float]] = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
```

**초기화 파라미터**:
- `api_key`: API key (필수)
- `api_secret`: API secret (필수)
- `base_url`: API base URL
  - **Testnet**: `https://api-testnet.bybit.com` (BYBIT_TESTNET=true, 기본값)
  - **Mainnet**: `https://api.bybit.com` (BYBIT_TESTNET=false만 허용)
- `clock`: Timestamp 생성 함수 (기본: time.time)
- `timeout`: 요청 타임아웃 (초, 기본: 10.0)
- `max_retries`: 최대 재시도 횟수 (기본: 3)

**Raises**:
- `FatalConfigError`: API key/secret 누락 또는 URL 불일치

**환경 변수**:
```bash
# Testnet mode (기본값)
BYBIT_TESTNET=true  # api-testnet.bybit.com 강제

# Mainnet mode
BYBIT_TESTNET=false  # api.bybit.com 허용
```

**초기화 예제** ([src/infrastructure/exchange/bybit_rest_client.py:90-111](src/infrastructure/exchange/bybit_rest_client.py#L90-L111)):
```python
# API key/secret 검증 (fail-fast)
if not api_key:
    raise FatalConfigError("API key is required")
if not api_secret:
    raise FatalConfigError("API secret is required")

# Testnet/Mainnet 모드 확인
testnet_mode = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

if testnet_mode and "api-testnet.bybit.com" not in base_url:
    raise FatalConfigError(
        "BYBIT_TESTNET=true but base_url is not Testnet. "
        "Use 'https://api-testnet.bybit.com' for Testnet."
    )

if not testnet_mode and "api.bybit.com" not in base_url:
    raise FatalConfigError(
        "BYBIT_TESTNET=false but base_url is not Mainnet. "
        "Use 'https://api.bybit.com' for Mainnet."
    )
```

---

#### 7.1.2 _generate_signature()

HMAC SHA256 서명 생성 (Bybit V5 API)

**함수 시그니처** ([src/infrastructure/exchange/bybit_rest_client.py:135](src/infrastructure/exchange/bybit_rest_client.py#L135)):
```python
def _generate_signature(
    self, timestamp: int, params: Dict[str, Any], method: str = "GET"
) -> str:
```

**파라미터**:
- `timestamp`: timestamp (ms)
- `params`: 요청 파라미터
- `method`: HTTP method ("GET" or "POST")

**리턴**:
- `str`: HMAC SHA256 서명

**Bybit V5 API Signature Spec**:
- **GET**: `timestamp + apiKey + recvWindow + queryString`
- **POST**: `timestamp + apiKey + recvWindow + JSON_BODY`

**코드 예제** (실제 구현은 bybit_rest_client.py Line 148+):
```python
# recvWindow 설정 (5000ms = 5초)
recv_window = 5000

# Payload 생성 (method별)
if method == "GET":
    # GET: queryString
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    payload = f"{timestamp}{self.api_key}{recv_window}{query_string}"
elif method == "POST":
    # POST: JSON body
    json_body = json.dumps(params)
    payload = f"{timestamp}{self.api_key}{recv_window}{json_body}"

# HMAC SHA256 서명
signature = hmac.new(
    self.api_secret.encode("utf-8"),
    payload.encode("utf-8"),
    hashlib.sha256
).hexdigest()

return signature
```

**SSOT 참조**:
- **task_plan.md Phase 7**: 서명 생성이 deterministic (Clock 주입)

---

#### 7.1.3 _get_timestamp()

현재 timestamp (milliseconds)

**함수 시그니처** ([src/infrastructure/exchange/bybit_rest_client.py:123](src/infrastructure/exchange/bybit_rest_client.py#L123)):
```python
def _get_timestamp(self) -> int:
```

**리턴**:
- `int`: timestamp (ms)

**중요**: 3초 과거로 조정 (클라이언트 시간이 서버보다 미래인 문제 해결, Phase 13b)

**코드 예제** ([src/infrastructure/exchange/bybit_rest_client.py:133](src/infrastructure/exchange/bybit_rest_client.py#L133)):
```python
return int((self.clock() - 3.0) * 1000)  # 3초 과거로 조정
```

**SSOT 참조**:
- **task_plan.md Phase 13b**: Timestamp 조정 정책

---

#### 7.1.4 Rate Limit 처리

Rate limit 감지 및 backoff

**Rate Limit 정보** (X-Bapi-* 헤더):
- `X-Bapi-Limit-Status`: 남은 요청 수 (예: 120)
- `X-Bapi-Limit`: 전체 요청 한도 (예: 120)
- `retCode 10006`: Rate limit 초과 (우선순위 1 감지)

**처리 우선순위**:
1. `retCode=10006` → RateLimitError 발생 (backoff)
2. `X-Bapi-Limit-Status < 20%` → 경고 로그
3. 내부 예산 (참고용)

**예외 클래스** ([src/infrastructure/exchange/bybit_rest_client.py:40](src/infrastructure/exchange/bybit_rest_client.py#L40)):
```python
class RateLimitError(Exception):
    """
    Rate limit 초과

    Attributes:
        retry_after: 재시도 가능 시각 (Optional[float])
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after
```

**SSOT 참조**:
- **Section 1.4 Definitions**: Rate limit 정책 (X-Bapi-* 헤더 기반)

---

### 7.2 Bybit WebSocket

Bybit WebSocket V5 클라이언트 (Private execution events)

#### 7.2.1 BybitWsClient

WebSocket 클라이언트 (골격, Contract tests only)

**클래스** ([src/infrastructure/exchange/bybit_ws_client.py:36](src/infrastructure/exchange/bybit_ws_client.py#L36)):
```python
class BybitWsClient:
    """
    Bybit WebSocket Client (골격만, Contract tests only)

    핵심 원칙:
    - subscribe topic 정확성 (execution.linear / execution.inverse)
    - disconnect/reconnect → DEGRADED 플래그
    - ping-pong timeout 처리
    - WS queue maxsize + overflow 정책 (실거래 함정 1)
    - Clock 주입 (determinism) (실거래 함정 2)
    - Testnet WSS URL 강제 assert (실거래 함정 3)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        wss_url: str,
        clock: Optional[Callable[[], float]] = None,
        pong_timeout: float = 20.0,
        queue_maxsize: int = 1000,
        category: str = "linear",
    ):
```

**초기화 파라미터**:
- `api_key`: API key (필수)
- `api_secret`: API secret (필수)
- `wss_url`: WebSocket URL
  - **Testnet**: `wss://stream-testnet.bybit.com/v5/private` (BYBIT_TESTNET=true)
  - **Mainnet**: `wss://stream.bybit.com/v5/private` (BYBIT_TESTNET=false)
- `clock`: Timestamp 생성 함수 (기본: time.time)
- `pong_timeout`: Pong timeout (초, 기본: 20.0)
- `queue_maxsize`: 메시지 큐 최대 크기 (기본: 1000)
- `category`: Futures category ("linear" or "inverse", 기본: "linear")

**Raises**:
- `FatalConfigError`: API key/secret 누락 또는 URL 불일치

**초기화 예제** ([src/infrastructure/exchange/bybit_ws_client.py:74-95](src/infrastructure/exchange/bybit_ws_client.py#L74-L95)):
```python
# API key/secret 검증 (fail-fast)
if not api_key:
    raise FatalConfigError("API key is required")
if not api_secret:
    raise FatalConfigError("API secret is required")

# Testnet/Mainnet 모드 확인
testnet_mode = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

if testnet_mode and "stream-testnet.bybit.com" not in wss_url:
    raise FatalConfigError(
        "BYBIT_TESTNET=true but wss_url is not Testnet. "
        "Use 'wss://stream-testnet.bybit.com/v5/private' for Testnet."
    )

if not testnet_mode and "stream.bybit.com" not in wss_url:
    raise FatalConfigError(
        "BYBIT_TESTNET=false but wss_url is not Mainnet. "
        "Use 'wss://stream.bybit.com/v5/private' for Mainnet."
    )
```

---

#### 7.2.2 get_subscribe_payload()

Subscribe payload 생성 (execution topic)

**함수 시그니처** ([src/infrastructure/exchange/bybit_ws_client.py:127](src/infrastructure/exchange/bybit_ws_client.py#L127)):
```python
def get_subscribe_payload(self) -> Dict[str, Any]:
```

**리턴**:
- `Dict`: Subscribe payload

**Bybit V5 WebSocket Execution Topics**:
- **Linear**: `execution.linear` (USDT-margined futures)
- **Inverse**: `execution.inverse` (Coin-margined futures)

**코드 예제** ([src/infrastructure/exchange/bybit_ws_client.py:138-143](src/infrastructure/exchange/bybit_ws_client.py#L138-L143)):
```python
topic = f"execution.{self.category}"
return {
    "op": "subscribe",
    "args": [topic],
}
```

---

#### 7.2.3 on_disconnect()

Disconnect 이벤트 처리 (DEGRADED 플래그)

**함수 시그니처** ([src/infrastructure/exchange/bybit_ws_client.py:145](src/infrastructure/exchange/bybit_ws_client.py#L145)):
```python
def on_disconnect(self) -> None:
```

**동작**:
- `_degraded = True` 설정
- `_degraded_entered_at` 타임스탬프 기록

**DEGRADED 플래그**:
- WebSocket 연결 끊김 시 설정
- 재연결 성공 전까지 DEGRADED 상태 유지
- Application Layer에서 DEGRADED → HALT 전환 판단

**SSOT 참조**:
- **task_plan.md Phase 7**: disconnect/reconnect → DEGRADED 플래그

---

#### 7.2.4 WS Queue Overflow 처리

메시지 큐 maxsize + overflow 정책 (실거래 함정 1)

**메시지 큐** ([src/infrastructure/exchange/bybit_ws_client.py:113-114](src/infrastructure/exchange/bybit_ws_client.py#L113-L114)):
```python
# 메시지 큐 (FIFO, maxsize 제한)
self._message_queue: deque = deque(maxlen=queue_maxsize)
self._drop_count = 0  # Overflow로 드랍된 메시지 수
```

**Overflow 정책**:
- `deque(maxlen=queue_maxsize)`: FIFO, maxsize 초과 시 가장 오래된 메시지 자동 드랍
- `_drop_count`: 드랍된 메시지 수 추적 (모니터링용)

**실거래 함정**:
- Queue overflow → 이벤트 손실 → 상태 불일치
- 해결: queue_maxsize 충분히 크게 설정 (기본: 1000)

---

### 7.3 Storage System

JSONL 기반 Trade Log 저장 시스템

#### 7.3.1 LogStorage

Log Storage (JSONL, O_APPEND, fsync policy)

**클래스** ([src/infrastructure/storage/log_storage.py:21](src/infrastructure/storage/log_storage.py#L21)):
```python
class LogStorage:
    """
    Log Storage (JSONL)

    핵심 원칙:
    - Single syscall write per line (os.write)
    - Durable append: flush + fsync policy (batch/periodic/critical)
    - Rotation: Day boundary (UTC) handle swap with pre-rotate flush+fsync
    - Crash safety: Partial line recovery (truncate last line if JSON parse fails)
    - Concurrency: Single writer (fd 상시 유지)
    """

    def __init__(
        self,
        log_dir: Path,
        fsync_policy: str = "batch",
        fsync_batch_size: int = 10,
    ):
```

**초기화 파라미터**:
- `log_dir`: 로그 파일 디렉토리 (Path)
- `fsync_policy`: fsync 정책 ("batch", "periodic", "critical")
- `fsync_batch_size`: batch 정책일 때 fsync 호출 간격 (라인 수, 기본: 10)

---

#### 7.3.2 append_trade_log_v1()

Trade Log JSONL append (Single syscall write)

**함수 시그니처** ([src/infrastructure/storage/log_storage.py:82](src/infrastructure/storage/log_storage.py#L82)):
```python
def append_trade_log_v1(
    self, log_entry: Dict[str, Any], is_critical: bool = False
):
```

**파라미터**:
- `log_entry`: Trade Log dict
- `is_critical`: critical event 여부 (HALT/LIQ/ADL) → 즉시 fsync

**동작**:
1. JSON 라인 생성 (`\n` 포함)
2. Single syscall write (`os.write`)
3. Flush (항상 수행)
4. Fsync policy 적용

**Fsync Policy**:
- **critical event**: 즉시 fsync
- **batch policy**: N개마다 fsync (기본: 10)
- **periodic policy**: 주기적 fsync (현재 미구현)

**코드 예제** ([src/infrastructure/storage/log_storage.py:94-117](src/infrastructure/storage/log_storage.py#L94-L117)):
```python
# JSON 라인 생성 (newline 포함)
json_line = json.dumps(log_entry) + "\n"
json_bytes = json_line.encode("utf-8")

# Single syscall write (os.write)
os.write(self.current_file_fd, json_bytes)
self.write_syscall_count += 1

# Flush (항상 수행)
os.fsync(self.current_file_fd)  # Flush는 fsync에 포함됨

self.append_count += 1

# Fsync policy
if is_critical:
    # Critical event → 즉시 fsync
    os.fsync(self.current_file_fd)
    self.fsync_count += 1
elif self.fsync_policy == "batch":
    # Batch policy → N개마다 fsync
    if self.append_count >= self.fsync_batch_size:
        os.fsync(self.current_file_fd)
        self.fsync_count += 1
        self.append_count = 0
```

**SSOT 참조**:
- **task_plan.md Phase 10**: Log Storage (JSONL, fsync policy)

---

#### 7.3.3 read_trade_logs_v1()

Trade Log 읽기 (Partial line recovery)

**함수 시그니처** ([src/infrastructure/storage/log_storage.py:119](src/infrastructure/storage/log_storage.py#L119)):
```python
def read_trade_logs_v1(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
```

**파라미터**:
- `date`: 날짜 문자열 ("YYYY-MM-DD", None이면 현재 파일)

**리턴**:
- `List[Dict]`: 로그 엔트리 리스트

**Partial Line Recovery**:
- 마지막 라인이 JSON 파싱 실패 시 → Truncate (크래시 안전성)
- 중간 라인 파싱 실패 → Skip (로그 유실, 계속 진행)

**코드 예제** ([src/infrastructure/storage/log_storage.py:149-164](src/infrastructure/storage/log_storage.py#L149-L164)):
```python
# Partial line recovery
for i, line in enumerate(lines):
    try:
        log_entry = json.loads(line)
        logs.append(log_entry)
        valid_lines.append(line)
    except json.JSONDecodeError:
        # 마지막 라인만 partial로 간주 (truncate)
        if i == len(lines) - 1:
            # Partial line 발견 → truncate
            self._truncate_partial_line(file_path, valid_lines)
            break
        else:
            # 중간 라인 파싱 실패 → 로그 유실이므로 무시하고 진행
            continue

return logs
```

---

#### 7.3.4 rotate_if_needed()

Daily rotation (UTC boundary)

**함수 시그니처** ([src/infrastructure/storage/log_storage.py:173](src/infrastructure/storage/log_storage.py#L173)):
```python
def rotate_if_needed(self):
```

**Rotation 절차**:
1. 현재 파일 flush + fsync (pre-rotate)
2. 현재 파일 close
3. 새 파일 open

**로그 파일명 형식**: `trades_YYYY-MM-DD.jsonl` (UTC 날짜 기준)

**코드 예제** ([src/infrastructure/storage/log_storage.py:182-198](src/infrastructure/storage/log_storage.py#L182-L198)):
```python
new_filename = self._get_log_filename()
current_filename = self.current_file_path.name

if new_filename != current_filename:
    # Day boundary 넘어감 → rotation
    # 1. Pre-rotate flush+fsync
    os.fsync(self.current_file_fd)
    self.fsync_count += 1

    # 2. Close current file
    os.close(self.current_file_fd)

    # 3. Open new file
    self._open_current_file()

    # append_count 리셋
    self.append_count = 0
```

---

### 7.4 Safety Systems

안전 장치 및 모니터링 시스템

#### 7.4.1 KillSwitch

Manual halt mechanism

**클래스** ([src/infrastructure/safety/killswitch.py:20](src/infrastructure/safety/killswitch.py#L20)):
```python
class KillSwitch:
    """
    Kill Switch — Manual halt mechanism

    Usage:
        # Manual halt
        touch .halt

        # Reset
        rm .halt
    """

    def __init__(self, halt_file: str = ".halt"):
```

**주요 메서드**:

##### is_halted()

Manual halt 상태 확인

**시그니처** ([src/infrastructure/safety/killswitch.py:41](src/infrastructure/safety/killswitch.py#L41)):
```python
def is_halted(self) -> bool:
```

**리턴**:
- `True` if .halt file exists, `False` otherwise

**코드 예제** ([src/infrastructure/safety/killswitch.py:47](src/infrastructure/safety/killswitch.py#L47)):
```python
return os.path.exists(self.halt_file)
```

---

##### halt()

Manual halt 활성화

**시그니처** ([src/infrastructure/safety/killswitch.py:50](src/infrastructure/safety/killswitch.py#L50)):
```python
def halt(self) -> None:
```

**동작**: `.halt` 파일 생성 (touch)

**코드 예제** ([src/infrastructure/safety/killswitch.py:54-55](src/infrastructure/safety/killswitch.py#L54-L55)):
```python
with open(self.halt_file, "w") as f:
    f.write("manual_halt\n")
```

---

##### reset()

Manual halt 해제

**시그니처** ([src/infrastructure/safety/killswitch.py:57](src/infrastructure/safety/killswitch.py#L57)):
```python
def reset(self) -> None:
```

**동작**: `.halt` 파일 삭제 (rm)

**코드 예제** ([src/infrastructure/safety/killswitch.py:61-62](src/infrastructure/safety/killswitch.py#L61-L62)):
```python
if os.path.exists(self.halt_file):
    os.remove(self.halt_file)
```

**SSOT 참조**:
- **task_plan.md Phase 9c**: 기존 안전장치 (KillSwitch)

---

#### 7.4.2 Alert

Alert system (log only, 추후 Slack/Discord 연동)

**클래스** ([src/infrastructure/safety/alert.py:22](src/infrastructure/safety/alert.py#L22)):
```python
class Alert:
    """
    Alert System — Notification system (log only)

    Usage:
        alert = Alert()
        alert.send("HALT", "daily_loss_cap_exceeded")
    """

    def __init__(self, log_only: bool = True):
```

**주요 메서드**:

##### send()

Alert 전송

**시그니처** ([src/infrastructure/safety/alert.py:40](src/infrastructure/safety/alert.py#L40)):
```python
def send(self, level: str, message: str) -> None:
```

**파라미터**:
- `level`: Alert 레벨 ("INFO", "WARNING", "HALT")
- `message`: Alert 메시지

**동작**:
- **현재**: 로그만 출력
- **추후**: Slack/Discord 연동 (Phase 10+)

**코드 예제** ([src/infrastructure/safety/alert.py:51-57](src/infrastructure/safety/alert.py#L51-L57)):
```python
if self.log_only:
    if level == "HALT":
        logger.critical(f"[ALERT:{level}] {message}")
    elif level == "WARNING":
        logger.warning(f"[ALERT:{level}] {message}")
    else:
        logger.info(f"[ALERT:{level}] {message}")
```

---

#### 7.4.3 RollbackProtocol

Rollback mechanism (placeholder, 추후 DB 스냅샷 연동)

**클래스** ([src/infrastructure/safety/rollback_protocol.py:22](src/infrastructure/safety/rollback_protocol.py#L22)):
```python
class RollbackProtocol:
    """
    Rollback Protocol — Rollback mechanism (placeholder)

    Usage:
        rollback = RollbackProtocol()
        rollback.create_snapshot()  # 스냅샷 생성 (현재 미구현)
        rollback.restore_snapshot()  # 스냅샷 복구 (현재 미구현)

    Note:
        현재 미구현, HALT 시 manual intervention 필요
        추후 DB 스냅샷 연동 (Phase 10+)
    """

    def __init__(self, enabled: bool = False):
```

**주요 메서드**:

##### create_snapshot()

스냅샷 생성 (placeholder)

**시그니처** ([src/infrastructure/safety/rollback_protocol.py:45](src/infrastructure/safety/rollback_protocol.py#L45)):
```python
def create_snapshot(self) -> bool:
```

**리턴**:
- `True` if successful, `False` otherwise

**현재 상태**: 미구현 (placeholder)

---

##### restore_snapshot()

스냅샷 복구 (placeholder)

**시그니처** ([src/infrastructure/safety/rollback_protocol.py:62](src/infrastructure/safety/rollback_protocol.py#L62)):
```python
def restore_snapshot(self, snapshot_id: str) -> bool:
```

**파라미터**:
- `snapshot_id`: Snapshot ID

**리턴**:
- `True` if successful, `False` otherwise

**현재 상태**: 미구현 (placeholder)

**SSOT 참조**:
- **task_plan.md Phase 9c**: 기존 안전장치 (Rollback)

---

**Section 7 완료**

Phase 4 작업 완료: Infrastructure Layer 외부 연동 및 안전 장치 문서화

- Bybit REST API: BybitRestClient (서명 생성, Rate limit, Testnet/Mainnet 모드)
- Bybit WebSocket: BybitWsClient (Subscribe topic, DEGRADED 플래그, Queue overflow)
- Storage System: LogStorage (JSONL, fsync policy, Partial line recovery, Daily rotation)
- Safety Systems: KillSwitch (Manual halt), Alert (Log only), RollbackProtocol (Placeholder)

---

## 8. Operations Guide

### 8.1 Setup & Configuration

#### 환경 변수

```bash
# Bybit API Credentials (필수)
export BYBIT_API_KEY="your_api_key"
export BYBIT_API_SECRET="your_api_secret"

# Testnet/Mainnet 모드 (기본: testnet)
export BYBIT_TESTNET="true"   # Testnet
export BYBIT_TESTNET="false"  # Mainnet (ONLY for production)

# Log Directory
export LOG_DIR="./logs"
```

**CRITICAL**: API key 누락 시 프로세스 시작 거부 (FatalConfigError)

#### 설정 파일

- `config/safety_limits.yaml`: KillSwitch, Alert, Rollback 설정
- `.halt`: Manual halt 파일 (존재 시 즉시 HALT)

---

### 8.2 Start/Stop Procedures

#### 시작

```bash
# 1. 가상환경 활성화
source venv/bin/activate

# 2. 패키지 설치 (최초 1회)
pip install -e ".[dev]"

# 3. 환경 변수 확인
echo $BYBIT_TESTNET  # "true" 확인 (testnet)

# 4. KillSwitch 확인 (.halt 파일 없어야 함)
rm -f .halt

# 5. 실행 (실제 entry point는 Phase 7+ 구현)
# python -m src.main
```

#### 정지

```bash
# Manual Halt (즉시 정지)
touch .halt

# Process 확인
ps aux | grep python
```

---

### 8.3 Monitoring

#### KillSwitch 상태 확인

```bash
# Manual halt 활성 여부
ls .halt && echo "HALTED" || echo "RUNNING"
```

#### Log 확인

```bash
# 오늘 거래 로그
cat logs/trades_$(date -u +%Y-%m-%d).jsonl | jq .

# 마지막 10개 이벤트
tail -10 logs/trades_$(date -u +%Y-%m-%d).jsonl | jq .
```

#### Alert 확인

```bash
# Critical alert 검색
grep "ALERT:HALT" logs/*.log
```

---

### 8.4 Development Commands

```bash
# 테스트 실행
pytest -q

# 특정 테스트만
pytest tests/oracles/test_state_transition_oracle.py -v

# 커버리지
pytest --cov=src --cov-report=html

# 타입 체크
mypy src/

# 린트
ruff check src/
```

---

## 9. Troubleshooting

### 9.1 Common Scenarios

#### HALT 상태 진입

**증상**: State = HALT, 진입 차단

**원인**:
1. LIQUIDATION 이벤트
2. Daily/Weekly loss cap 초과
3. Loss streak 3연패
4. Manual halt (touch .halt)
5. ENTRY_PENDING에서 pending_order=None

**조치**:
```bash
# 1. HALT 원인 확인 (로그)
grep "HALT" logs/trades_$(date -u +%Y-%m-%d).jsonl | tail -5 | jq .

# 2. Manual halt 여부 확인
ls .halt

# 3. Manual reset (ONLY if safe)
rm .halt
# 또는 코드에서 State 복구 (Phase 7+ 구현)
```

**CRITICAL**: HALT은 manual reset only. 자동 해제 금지.

---

#### DEGRADED 상태

**증상**: WebSocket disconnect, 이벤트 손실 가능

**원인**:
1. WS connection 끊김
2. Ping-pong timeout
3. Queue overflow

**조치**:
```bash
# 1. WS 재연결 대기 (자동 재연결)
# 2. DEGRADED → HALT 전환 모니터링
# 3. 재연결 실패 시 프로세스 재시작
```

---

#### Rate Limit 초과

**증상**: retCode=10006, RateLimitError

**원인**: API 호출 빈도 초과

**조치**:
```bash
# 1. X-Bapi-Limit-Status 헤더 확인 (로그)
# 2. Backoff 대기 (retry_after)
# 3. 재시도 간격 증가
```

---

### 9.2 Emergency Procedures

#### 즉시 정지 (Emergency Halt)

```bash
# 1. Manual halt 활성화
touch .halt

# 2. 프로세스 확인
ps aux | grep python | grep -v grep

# 3. 강제 종료 (필요 시)
kill -9 <PID>
```

#### Rollback (현재 미구현)

```bash
# Phase 10+ 구현 예정
# 현재는 manual intervention 필요
```

---

### 9.3 Rollback Protocol

**현재 상태**: Placeholder (미구현)

**HALT 시 Manual Intervention**:
1. `.halt` 파일 생성하여 즉시 정지
2. 로그 분석 (HALT 원인 확인)
3. 상태 복구 (manual reset 또는 DB 롤백)
4. 테스트 환경에서 재현 확인
5. `.halt` 파일 삭제 후 재시작

**추후 구현** (Phase 10+):
- DB 스냅샷 자동 생성
- HALT 시 자동 롤백
- Slack/Discord 알림 연동

---

## 10. References

### 10.1 SSOT Documents

**Single Source of Truth** (최상위 문서 3개):

1. [FLOW.md](../constitution/FLOW.md) - 실행 순서, 상태 전환, 모드 규칙 (헌법)
2. [account_builder_policy.md](../specs/account_builder_policy.md) - 정책 수치, 게이트 정의, 단위, 스키마
3. [task_plan.md](../plans/task_plan.md) - Gate 기반 구현 순서, DoD, 진행표

**참고 문서**:
- [PRD.md](../PRD.md) - 제품 요구사항
- [STRATEGY.md](../STRATEGY.md) - 전략 설명
- [RISK.md](../RISK.md) - 리스크 관리
- [CLAUDE.md](../CLAUDE.md) - 개발 운영 계약서

---

### 10.2 ADR Index

**Architecture Decision Records** (설계 결정 기록):

주요 ADR 목록은 [docs/adr/](../adr/) 디렉토리 참조

핵심 ADR:
- **ADR-0002**: Inverse to Linear USDT Migration
- **ADR-0011**: Section 2.1/2.2 동기화 규칙 명시화

---

### 10.3 Glossary

**핵심 용어**:

- **SSOT**: Single Source of Truth (단일 진실, 최상위 문서 3개)
- **HALT**: 모든 진입 차단 상태 (Manual reset only)
- **COOLDOWN**: 일시적 차단 (자동 해제 가능)
- **DEGRADED**: WebSocket 연결 끊김 상태
- **Equity**: `wallet_balance_usdt + unrealized_pnl_usdt`
- **Linear Futures**: USDT-margined Futures (Bybit)
- **Contract Size**: 0.001 BTC per contract (Bybit Linear BTCUSDT, 확인 필요)
- **UTC Boundary**: Daily/Weekly PnL 계산 기준 (00:00:00 UTC)
- **fsync Policy**: Log 내구성 정책 (batch/periodic/critical)
- **Intent**: 상태 전환 시 부수효과 명시 (StopIntent, HaltIntent, ExitIntent)
- **Oracle Test**: 전이 규칙 검증 테스트 (RED→GREEN 증명)
- **Gate**: 진입 검증 단계 (8 gates)
- **EV Gate**: Expected Value gate (expected_profit >= fee * K)
- **Rate Limit**: X-Bapi-* 헤더 기반 throttle + retCode=10006
- **KillSwitch**: Manual halt 메커니즘 (touch .halt)

---

**Last Updated**: 2026-02-01 (Phase 1-4 COMPLETE, Phase 5-6 간결 버전)

[FLOW.md]: ../constitution/FLOW.md
[account_builder_policy.md]: ../specs/account_builder_policy.md
[task_plan.md]: ../plans/task_plan.md

---

**Last Updated**: 2026-02-01 (Phase 1 In Progress)

[FLOW.md]: ../constitution/FLOW.md
[account_builder_policy.md]: ../specs/account_builder_policy.md
[task_plan.md]: ../plans/task_plan.md
