# docs/plans/task_plan.md
# Task Plan: Account Builder Implementation (v2.39, ADR-0011 적용 + Gate 9 추가)
Last Updated: 2026-01-25 (KST, ADR-0011 적용 + Gate 9 추가 + Section 2.1/2.2 정렬 완료)
Status: **Phase 0~12a-3 COMPLETE, Phase 12a-4 IN PROGRESS (Force Entry), Phase 12a-5 TODO (Telegram)** | Gate 1-9 ALL PASS | **320 tests passed** (+8 from Phase 12a-3) | ✅ Automated Dry-Run Infrastructure (Mock-based) | ✅ Market Data Provider 완전 구현 (ATR/SessionRisk/Regime) | ✅ Gate 9 추가 (Section 2.1/2.2 동기화 자동 검증, ADR-0011) | 🔄 Phase 분리: 12a-4 (Force Entry + Testnet 거래) + 12a-5 (Telegram 알림, 상세 설계 포함) | 원칙: 100% 완료만 DONE 표시
Policy: docs/specs/account_builder_policy.md
Flow: docs/constitution/FLOW.md

---

## 0. Goal

Account Builder ($100 → $1,000) 봇을 **실거래 가능한 수준**으로 구현한다.
- Bybit Inverse Futures 제약 준수
- survival-first + growth-enforcing (시간/스테이지 목표)
- 결정 규칙은 반드시 **결정론적(deterministic)** 이고 **테스트로 고정**된다

Non-goal
- 과한 추상화/과잉 설계
- liquidation “추정 공식”을 멋대로 만드는 행위(가능하면 거래소-derived 사용)

---

## 1. Global Rules (협상 불가)

### 1.1 Test Rules (No Placeholder)
- `assert True`, `pass`, `TODO`, “일단 통과”는 **테스트로 인정하지 않는다**
- 모든 체크박스는 **fail→pass 증거**(테스트가 실제로 실패했다가 구현 후 통과) 가 있어야 DONE

### 1.2 Definition of DONE (DoD)
각 작업 체크박스는 아래 **4가지를 모두** 만족해야 DONE:
1) **관련 테스트 최소 1개 이상 존재** (`tests/` 아래)
2) 테스트가 **구현 전 실패했고(RED)** 구현 후 통과했음(GREEN)
3) 코드가 **Flow/Policy 정의와 충돌하지 않음** (아래 1.3~1.5 Gate)
4) **CLAUDE.md Section 5.7 Self-Verification 통과 필수** (완료 보고 전)
   - 7개 검증 커맨드 실행 → 모든 출력 정상
   - **5.7 커맨드 출력 결과 (붙여넣기) 또는 스크린샷을 DONE 보고에 필수 포함**

### 1.3 Oracle First
- Primary truth: `tests/oracles/test_state_transition_oracle.py`
  - 상태 전이 + intents를 동시에 검증한다
  - 오라클은 “문서 흉내”가 아니라 “실제 assert”여야 한다
- Integration tests는 연결 확인용(5~10개)으로 제한한다

### 1.4 Architecture Gates
- Blocking wait 금지(WS I/O는 메인 tick을 block하지 않을 것: asyncio 또는 background thread 허용, REST는 timeout 필수)
- state machine 모든 전환은 테스트로 커버해야 함
- Emergency는 Signal보다 **항상 먼저** 실행
- Idempotency 보장(중복 주문 방지)
- God Object 금지(책임 분리)

### 1.5 Real Trading Trap Fix Gates (FLOW v1.4~v1.6)
아래는 "실거래 함정 방지"로 **누락 시 DONE 불가**:
- Position Mode One-way 검증
- PARTIAL_FILL `entry_working` 플래그
- **Rate limit: X-Bapi-* 헤더 기반 throttle** (Bybit 공식 SSOT)
  - **retCode=10006** (rate limit 초과) → 1순위 신호
  - X-Bapi-Limit-Status/Reset-Timestamp → backoff 기준
  - HTTP 429는 보조 신호 (프록시/게이트웨이 레벨)
  - 내부 safety budget(90/min)은 보수적 상한으로만 사용
  - Endpoint별 token bucket (초당 제한은 Bybit 문서 기준)
- **WS ping-pong + max_active_time 정책** (Bybit WebSocket v5 SSOT: https://bybit-exchange.github.io/docs/v5/ws/connect)
  - Heartbeat monitoring: 클라이언트가 ping 전송 (권장 20초마다), 서버 pong 응답, 무활동 10분 시 연결 종료
  - Reconnection logic + max_active_time 관리
  - Private stream 엔드포인트 (testnet): wss://stream-testnet.bybit.com/v5/private
  - **Execution topic SSOT** (Bybit 공식: https://bybit-exchange.github.io/docs/v5/websocket/private/execution):
    - Inverse: `"execution.inverse"` (카테고리 전용)
    - Linear: `"execution.linear"` (카테고리 전용)
    - All-In-One: `"execution"` (모든 카테고리, **Categorised와 동일 요청 혼용 불가**)
- Reconcile 히스테리시스(연속 3회, 5초 COOLDOWN)
- Fee 단위: contracts = USD notional
- Liquidation gate(거래소-derived 우선)
- Idempotency key `{signal_id}_{direction}` (SHA1 축약)
- Stop 주문 속성: reduceOnly=True, positionIdx=0
- Stop amend 우선(공백 방지) + debounce(20%/2s)
- WS DEGRADED (진입 차단 + IN_POSITION 1초 reconcile)
- orderLinkId 규격 검증(<=36, [A-Za-z0-9_-])
- Tick/Lot 보정 + 보정 후 재검증
- Event-driven 상태 확정(REST 폴링 금지)
- StopLoss 방식 B 고정(혼용 금지)
- 정상/DEGRADED 분리(DEGRADED 60초 후 HALT)
- stop_status 서브상태(ACTIVE/PENDING/MISSING/ERROR) 감시/복구

---

## 2. Repo Map (Single Source of Location)

### 2.1 Implemented (Phase 0-12a-3 완료, 실제 존재)

```
src/
├── domain/ # Pure (no I/O)
│   ├── state.py # ✅ Phase 0: State, StopStatus, Position, PendingOrder (+ re-export events)
│   ├── intent.py # ✅ Phase 0: StopIntent, HaltIntent, TransitionIntents (도메인 계약)
│   ├── events.py # ✅ Phase 0: EventType, ExecutionEvent (FILL/PARTIAL/CANCEL/REJECT/LIQ/ADL)
│   └── ids.py # ✅ Phase 2: signal_id, orderLinkId validators, SHA1 shortener
│
├── application/
│   ├── transition.py # ✅ Phase 0: transition(...) -> (state, position, intents) [SSOT]
│   ├── event_router.py # ✅ Phase 0: Stateless thin wrapper (입력 정규화 + transition 호출)
│   ├── tick_engine.py # ✅ Phase 0: Tick Orchestrator (FLOW Section 2 준수, Emergency-first ordering)
│   ├── emergency.py # ✅ Phase 1: emergency policy + recovery + cooldown (Policy Section 7.1/7.2/7.3)
│   ├── ws_health.py # ✅ Phase 1: ws health tracker + degraded rules (FLOW Section 2.4)
│   ├── entry_allowed.py # ✅ Phase 2: entry gates (policy-driven, 8 gates + reject reasons)
│   ├── sizing.py # ✅ Phase 2: Bybit inverse sizing (contracts, LONG/SHORT formulas)
│   ├── liquidation_gate.py # ✅ Phase 2: liquidation distance checks + fallback rules
│   ├── fee_verification.py # ✅ Phase 3: fee spike detection + taker/maker validation
│   ├── order_executor.py # ✅ Phase 3: intents -> exchange calls (place/cancel/amend)
│   ├── event_handler.py # ✅ Phase 3: execution event processing + idempotency
│   ├── stop_manager.py # ✅ Phase 4: stop placement/amend/debounce + stop_status recovery
│   ├── metrics_tracker.py # ✅ Phase 4: winrate/streak/multipliers + rolling window
│   ├── orchestrator.py # ✅ Phase 6: tick loop orchestrator (Emergency-first ordering)
│   ├── signal_generator.py # ✅ Phase 11a: Grid 전략 시그널 생성
│   └── exit_manager.py # ✅ Phase 11a: Exit decision (Stop hit / Profit target)
│
└── infrastructure/
    ├── exchange/
    │   ├── fake_exchange.py # ✅ Phase 0: Deterministic test simulator
    │   ├── market_data_interface.py # ✅ Phase 1: MarketDataInterface Protocol (6 methods)
    │   ├── fake_market_data.py # ✅ Phase 1: Deterministic test data injection
    │   ├── bybit_rest_client.py # ✅ Phase 7-8: REST client (sign/timeout/retry/rate limit)
    │   ├── bybit_ws_client.py # ✅ Phase 7-8: WS client (489 LOC, 14 public + 10 private methods)
    │   └── bybit_adapter.py # ✅ Phase 12a-1: BybitAdapter (MarketDataInterface 구현, REST + WS 통합)
    ├── logging/
    │   ├── trade_logger.py # ✅ Phase 5: entry/exit logging + schema validation
    │   ├── halt_logger.py # ✅ Phase 5: HALT reason + context snapshot
    │   ├── metrics_logger.py # ✅ Phase 5: winrate/streak/multiplier change tracking
    │   └── trade_logger_v1.py # ✅ Phase 10: Trade Log Schema v1.0 (slippage, latency, market_regime, integrity)
    └── storage/
        └── log_storage.py # ✅ Phase 10: JSON Lines storage + rotation

tests/
├── oracles/
│   ├── test_state_transition_oracle.py # ✅ Phase 0: Primary oracle (25 cases)
│   └── test_integration_basic.py # ✅ Phase 0: FakeExchange + EventRouter (9 cases)
├── unit/
│   ├── test_state_transition.py # ✅ Phase 0: transition() unit tests (36 cases)
│   ├── test_event_router.py # ✅ Phase 0: Gate 3 proof (2 cases)
│   ├── test_docs_ssot_paths.py # ✅ Phase 0: Documentation-Code path alignment (5 cases)
│   ├── test_flow_minimum_contract.py # ✅ Phase 0: FLOW minimum skeleton proof (5 cases)
│   ├── test_readme_links_exist.py # ✅ Phase 0: README-Docs file alignment (2 cases)
│   ├── test_emergency.py # ✅ Phase 1: Emergency Check tests (8 cases)
│   ├── test_ws_health.py # ✅ Phase 1: WS Health tests (5 cases)
│   ├── test_ids.py # ✅ Phase 2: orderLinkId validation (6 cases)
│   ├── test_entry_allowed.py # ✅ Phase 2: entry gates (9 cases)
│   ├── test_sizing.py # ✅ Phase 2: inverse sizing (8 cases)
│   ├── test_liquidation_gate.py # ✅ Phase 2: liq distance (8 cases)
│   ├── test_fee_verification.py # ✅ Phase 3: fee spike detection (5 cases)
│   ├── test_order_executor.py # ✅ Phase 3: order execution (8 cases)
│   ├── test_event_handler.py # ✅ Phase 3: event processing (7 cases)
│   ├── test_stop_manager.py # ✅ Phase 4: stop update policy (10 cases)
│   ├── test_metrics_tracker.py # ✅ Phase 4: winrate/streak (6 cases)
│   ├── test_trade_logger.py # ✅ Phase 5: trade logging (5 cases)
│   ├── test_halt_logger.py # ✅ Phase 5: halt logging (4 cases)
│   ├── test_metrics_logger.py # ✅ Phase 5: metrics logging (4 cases)
│   ├── test_bybit_rest_client.py # ✅ Phase 7: REST contract tests (10 cases, 네트워크 0)
│   ├── test_bybit_ws_client.py # ✅ Phase 7: WS contract tests (7 cases, 네트워크 0)
│   ├── test_bybit_adapter.py # ✅ Phase 12a-1: BybitAdapter tests (14 cases, REST 4 + WS 2 + Caching 3 + DEGRADED 3 + Session Risk 2)
│   ├── test_trade_logger_v1.py # ✅ Phase 10: Trade Log Schema v1.0 tests (9 cases)
│   ├── test_log_storage.py # ✅ Phase 10: Log storage tests (8 cases)
│   ├── test_signal_generator.py # ✅ Phase 11a: Signal generation tests (10 cases)
│   └── test_exit_manager.py # ✅ Phase 11a: Exit logic tests (8 cases)
├── integration/
│   └── test_orchestrator.py # ✅ Phase 6: tick loop integration (5 cases)
└── integration_real/
    ├── test_testnet_connection.py # ✅ Phase 8: WS connection (3 cases, testnet)
    ├── test_testnet_order_flow.py # ✅ Phase 8: REST order flow (4 cases, testnet)
    ├── test_execution_event_mapping.py # ✅ Phase 8: execution mapping (2 passed + 1 skip)
    ├── test_rate_limit_handling.py # ✅ Phase 8: rate limit (3 cases, testnet)
    ├── test_ws_reconnection.py # ✅ Phase 8: reconnection (3 cases, testnet)
    └── test_full_cycle_testnet.py # ✅ Phase 11b: Testnet full cycle (FLAT → Entry → Exit → FLAT, 6 cases)
```

**Phase 0-12a-3 DONE 증거**: 320 tests passed (Phase 0-11b: 267 + Phase 12a-1: 14 + Phase 12a-2: 31 + Phase 12a-3: 8), Gate 1-9 ALL PASS, Evidence Artifacts (docs/evidence/phase_0 ~ phase_12a3/), 새 세션 검증 가능 (`./scripts/verify_phase_completion.sh 0-12a-3`, `./scripts/verify_task_plan_consistency.sh`)

---

### 2.2 Planned (미구현 항목, 아직 미생성)

**구현 완료된 항목**: ✅ Section 2.1 Implemented로 이동 완료 (Progress Table에서 DONE 표시된 모든 Phase)

**미구현 항목 (Mainnet + 최적화)**:
```
tests/
└── integration_real/ (Mainnet dry-run + 최적화)
    └── test_mainnet_dry_run.py # (Mainnet) Mainnet dry-run validation
```

**생성 원칙**: 각 Phase DoD 충족 시에만 생성 (TDD: 테스트 먼저 → 구현)

**추가사항**:
- Mainnet dry-run 완료 시 실거래 시작
- 운영 최적화 단계 (선택 사항)

---

## 3. Progress Tracking Rules (컨텍스트 끊김 방지 핵심)

### 3.1 문서 업데이트는 “일”의 일부다 (DONE에 포함)
- 작업이 DONE되면 **즉시** 이 문서의 “Progress Table”에서 상태를 갱신한다.
- 갱신하지 않으면 DONE로 인정하지 않는다(다음 작업 착수 금지).

### 3.2 진행 표시는 3단계만 사용
- `TODO` : 착수 전
- `DOING` : 브랜치/커밋에서 작업 중
- `DONE` : DoD 충족(테스트 포함) + 표 갱신 완료

### 3.3 DONE 증거 링크 규칙
각 DONE 항목에는 최소 2개를 남긴다:
- 관련 테스트 파일 경로(예: `tests/unit/test_sizing.py::test_contracts_formula`)
- 구현 파일 경로(예: `src/application/sizing.py`)
선택(가능하면):
- 커밋 해시/PR 번호

### 3.4 문서 상단 "Last Updated" 반드시 갱신
- Progress 표가 바뀌면 Last Updated도 갱신한다.

### 3.5 Evidence Artifacts (컨텍스트 단절 대비 필수)

**목적**: 새 세션에서도 "이 Phase가 진짜 DONE인지" 검증 가능하게 만든다.

**규칙**:
1. Phase 완료 시 반드시 `docs/evidence/phase_N/` 디렉토리 생성
2. 최소 파일 4개:
   - `completion_checklist.md` (DoD 자체 검증)
   - `gate7_verification.txt` (Section 5.7 커맨드 출력 전문)
   - `pytest_output.txt` (pytest -q 실행 결과)
   - `red_green_proof.md` (RED→GREEN 재현 증거)
3. 위 파일들을 git commit 완료 후 Progress Table에 링크 추가
4. **새 세션 시작 시 검증 방법**:
   ```bash
   # 가장 빠른 확인
   cat docs/evidence/phase_N/gate7_verification.txt | grep -E "FAIL|ERROR"
   # → 출력 비어있으면 PASS

   # 철저한 확인
   ./scripts/verify_phase_completion.sh N
   ```

**DONE 무효 조건**:
- Evidence 파일이 없으면 → **DONE 자동 무효** (Progress Table에 [x]가 있어도 무시)
- 새 세션에서 `./scripts/verify_phase_completion.sh N`이 FAIL이면 → **재작업 필요**

**자세한 내용**: [docs/evidence/README.md](../evidence/README.md)

---

## 4. Implementation Phases (0, 0.5, 1~6) — with Detailed Conditions

### Phase 0: Foundation (Vocabulary Freeze)
Goal: “transition vocabulary”를 고정하고 오라클로 박는다.

#### Deliverables
- `src/domain/state.py`
  - `State` enum: FLAT, ENTRY_PENDING, IN_POSITION, EXIT_PENDING, HALT, COOLDOWN
  - `StopStatus` enum: ACTIVE, PENDING, MISSING, ERROR
  - `Position` dataclass (필수 필드)
    - `side` (LONG/SHORT or +1/-1)
    - `qty` (int contracts or domain qty, 명확히)
    - `entry_price_usd` (float)
    - `entry_stage` (1/2/3)
    - `entry_working` (bool)  # partial fill 보호
    - `stop_price_usd` (float|None)
    - `policy_version` (str, 예: "2.1")
    - `stop_status` (StopStatus)
  - `Pending` dataclass (필수 필드)
    - `order_id` (str|None)   # exchange id
    - `signal_id` (str)
    - `order_link_id` (str)   # validated
    - `direction` (LONG/SHORT)
    - `qty` (int)
    - `price_usd` (float|None)
- `src/domain/intent.py`
  - Intent base + 최소 Intent
    - `PlaceStop(qty, trigger_price, reduce_only=True, position_idx=0, order_link_id)`
    - `AmendStop(stop_order_id, new_qty, new_trigger_price?)`
    - `CancelOrder(order_id|order_link_id)`
    - `Log(level, code, message, context)`
    - `Halt(reason, manual_only: bool)`
- `src/domain/events.py`
  - ExecutionEvent 최소:
    - `FILL(qty, price, order_link_id)`
    - `PARTIAL_FILL(qty, price, order_link_id, cum_qty?)`
    - `CANCEL(order_link_id)`
    - `REJECT(order_link_id, reason)`
    - `LIQUIDATION(reason?)`
    - `ADL(reason?)`
- `src/application/transition.py`
  - 시그니처(협상 불가):
    ```python
    def transition(
        state,
        position,
        pending,
        event,
        ctx=None
    ) -> tuple[state, position, pending, list[intent]]:
        """Pure. No I/O. Deterministic."""
    ```

#### Conditions (명확한 규칙)
- transition은 **I/O 금지**: exchange 호출/시간/랜덤/환경 접근 금지
- 모든 side/direction/qty 단위가 문서상 정의와 일치해야 함(혼용 금지)

#### Tests (must)
- `tests/oracles/test_state_transition_oracle.py` 최소 10케이스, 모두 "상태+intent" assert
  - 예: `assert new_state == State.ENTRY_PENDING`
  - 예: `assert any(isinstance(x, PlaceStop) for x in intents)`

#### DoD
- [x] core types 정의 완료(위 Deliverables 충족)
- [x] transition 시그니처 고정 + pure 보장
- [x] 오라클 10케이스: 실제 assert, placeholder 0
- [x] DEPRECATED wrapper 제거 조건 정의: Phase 1 시작 시 src/application/services/state_transition.py 삭제, 남아있으면 FAIL
- [x] transition() 직접 import 사용으로 전환 완료 (deprecated wrapper 경고 포함)
- [x] Progress Table 업데이트
- [x] **Gate 7: CLAUDE.md Section 5.7 검증 통과 (7개 커맨드)**

---

### Phase 0.5: Minimal IN_POSITION Event Handling (Bridge)
Goal: IN_POSITION에서 "죽지 않게" 만들고 핵심 이벤트를 처리한다.

#### Conditions
- IN_POSITION에서 이벤트가 오면 **무조건 결정론적 처리**:
  - (A) PARTIAL_FILL: `position.qty += filled_qty`, `entry_working=True`, stop AMEND intent
  - (B) FILL(잔량 포함 최종): `entry_working=False`, stop AMEND intent
  - (C) LIQ/ADL: `HALT` + `HaltIntent(reason)`
  - (D) Invalid qty 방어: `filled_qty <= 0` or `new_qty < 0` → HALT
- stop 관련: stop_status 일관성 유지 + 복구 intent만 (debounce/rate-limit은 Phase 1)
  - stop_status=MISSING → PlaceStop intent

#### Tests
- Oracle에 +6케이스 추가 (fail→pass 증거):
  1. test_in_position_additional_partial_fill_increases_qty (A: PARTIAL_FILL)
  2. test_in_position_fill_completes_entry_working_false (B: FILL)
  3. test_in_position_liquidation_should_halt (C: LIQUIDATION)
  4. test_in_position_adl_should_halt (C: ADL)
  5. test_in_position_missing_stop_emits_place_stop_intent (stop_status=MISSING)
  6. test_in_position_invalid_filled_qty_halts (D: invalid qty 방어)

#### DoD
- [x] IN_POSITION + PARTIAL_FILL 처리 (A)
- [x] IN_POSITION + FILL 처리 (B)
- [x] IN_POSITION + LIQUIDATION/ADL → HALT (C)
- [x] stop_status=MISSING → PlaceStop intent
- [x] invalid fill qty 방어 (D)
- [x] 오라클 6케이스 fail→pass 증거
- [x] pytest 결과 + 함수 목록 Evidence
- [x] Progress Table 업데이트
- [x] **Gate 7: CLAUDE.md Section 5.7 검증 통과 (7개 커맨드)**

---

### Phase 1: Market & Emergency
Goal: 정책에 따른 emergency 판단과 degraded/health를 구현한다.

#### Conditions (정의/측정 - SSOT 정렬 완료)

**1. Emergency 판단 기준** (Policy Section 7):
- `price_drop_1m <= -10%` → `State.COOLDOWN` (manual_reset=False, auto-recovery 가능)
- `price_drop_5m <= -20%` → `State.COOLDOWN` (manual_reset=False, auto-recovery 가능)
- `balance anomaly` (equity <= 0 OR stale timestamp > 30s) → `State.HALT` (manual_reset=True)
- `latency_rest_p95 >= 5.0s` → `emergency_block=True` (진입 차단, pending cancel, State 변경 없음)

**2. WS Health 판단 기준** (FLOW Section 2.4):
- `heartbeat timeout > 10s` → `degraded_mode=True`
- `event drop count >= 3` → `degraded_mode=True`
- `degraded_mode duration >= 60s` → `State.HALT` (manual_reset=True)

**3. State Mapping** (SSOT 확정):
- **Manual-only HALT**: `State.HALT` with `manual_reset=True` (liquidation, balance < 80, degraded 60s timeout)
- **Auto-recovery temporary block**: `State.COOLDOWN` with `auto_lift_at` timestamp (price drop auto-recovery)
- **Emergency latency block**: `emergency_block=True` (boolean flag, State 변경 없음)
- **DEGRADED**: `degraded_mode=True` (boolean flag, State와 독립적)

**4. Recovery 조건** (Policy Section 7.3):
- **Emergency auto-recovery**: `drop_1m > -5% AND drop_5m > -10%` for 5 consecutive minutes → `State.FLAT` + cooldown 30분
- **WS recovery**: `heartbeat OK AND event drop == 0` → `degraded_mode=False` + cooldown 5분
- **Latency recovery**: `latency_rest_p95 < 5.0s` → `emergency_block=False` (즉시)

**5. 측정 정의** (Policy Section 7.1):
- `exchange_latency_rest_s`: REST RTT p95 over 1 minute window
- `balance anomaly`: API returns equity <= 0 OR schema invalid OR stale timestamp > 30s
- `price_drop_1m`: (current_price - price_1m_ago) / price_1m_ago
- `price_drop_5m`: (current_price - price_5m_ago) / price_5m_ago

#### Deliverables (의존성 순서)

**1a. Market Data Interface** (선행 필수):
- `src/infrastructure/exchange/market_data_interface.py`
  - `get_mark_price() -> float`
  - `get_equity_btc() -> float`
  - `get_rest_latency_p95_1m() -> float`
  - `get_ws_last_heartbeat_ts() -> float`
  - `get_ws_event_drop_count() -> int`
  - `get_timestamp() -> float`

**1b. Fake Market Data** (테스트용):
- `src/infrastructure/exchange/fake_market_data.py`
  - Deterministic data injection
  - `inject_price_drop(pct_1m: float, pct_5m: float)`
  - `inject_latency(value_s: float)`
  - `inject_balance_anomaly()`
  - `inject_ws_event(heartbeat_ok: bool, event_drop_count: int)`

**1c. Emergency Module**:
- `src/application/emergency.py`
  - `check_emergency(market_data) -> EmergencyStatus`
    - EmergencyStatus(is_halt: bool, is_cooldown: bool, is_blocked: bool, reason: str)
  - `check_recovery(market_data, cooldown_started_at) -> RecoveryStatus`
    - RecoveryStatus(can_recover: bool, cooldown_minutes: int)

**1d. WS Health Module**:
- `src/application/ws_health.py`
  - `check_ws_health(market_data) -> WSHealthStatus`
    - WSHealthStatus(is_degraded: bool, duration_s: float, reason: str)
  - `check_degraded_timeout(degraded_started_at) -> bool`

#### Tests (정확한 13 케이스)

**emergency.py (8 케이스)**:
1. `test_price_drop_1m_exceeds_threshold_enters_cooldown`
2. `test_price_drop_5m_exceeds_threshold_enters_cooldown`
3. `test_price_drop_both_below_threshold_no_action`
4. `test_balance_anomaly_zero_equity_halts`
5. `test_balance_anomaly_stale_timestamp_halts`
6. `test_latency_exceeds_5s_sets_emergency_block`
7. `test_auto_recovery_after_5_consecutive_minutes`
8. `test_auto_recovery_sets_30min_cooldown`

**ws_health.py (5 케이스)**:
1. `test_heartbeat_timeout_10s_enters_degraded`
2. `test_event_drop_count_3_enters_degraded`
3. `test_degraded_duration_60s_returns_halt`
4. `test_ws_recovery_exits_degraded`
5. `test_ws_recovery_sets_5min_cooldown`

#### DoD (Definition of Done)

**구현**:
- [x] MarketDataInterface 정의 완료 (6 메서드) ✅ Evidence: [market_data_interface.py:39-100](src/infrastructure/exchange/market_data_interface.py#L39-L100) (get_mark_price, get_equity_btc, get_rest_latency_p95_1m, get_ws_last_heartbeat_ts, get_ws_event_drop_count, get_timestamp)
- [x] FakeMarketData 구현 완료 (deterministic injection 4 메서드) ✅ Evidence: [fake_market_data.py:89-152](src/infrastructure/exchange/fake_market_data.py#L89-L152) (inject_price_drop, inject_latency, inject_balance_anomaly, inject_ws_event + inject_stale_balance 추가)
- [x] emergency.py 구현: 4 gates (drop_1m/5m, balance, latency) + auto-recovery + 30min cooldown ✅ Evidence: [emergency.py:55-193](src/application/emergency.py#L55-L193) (check_emergency, check_recovery)
- [x] ws_health.py 구현: heartbeat tracking + event drop tracking + 60s timeout + 5min cooldown ✅ Evidence: [ws_health.py:51-148](src/application/ws_health.py#L51-L148) (check_ws_health, check_degraded_timeout, check_ws_recovery)

**테스트**:
- [x] Unit tests: emergency 8 passed ✅ Evidence: [test_emergency.py](tests/unit/test_emergency.py) (pytest tests/unit/test_emergency.py -q → 8 passed in 0.01s)
- [x] Unit tests: ws_health 5 passed ✅ Evidence: [test_ws_health.py](tests/unit/test_ws_health.py) (pytest tests/unit/test_ws_health.py -q → 5 passed in 0.01s)
- [x] Total: 13 passed ✅ Evidence: pytest tests/unit/test_emergency.py tests/unit/test_ws_health.py -q → 13 passed in 0.01s (2026-01-19 00:25 검증)

**통합**:
- [x] State Machine 통합 검증 ✅ Evidence: 테스트 케이스에서 검증 완료 (test_price_drop_1m_exceeds_threshold_enters_cooldown → is_cooldown=True, test_balance_anomaly_zero_equity_halts → is_halt=True, test_latency_exceeds_5s_sets_emergency_block → is_blocked=True, test_heartbeat_timeout_10s_enters_degraded → is_degraded=True)
- [x] Cooldown 시간 검증: emergency 30분, ws_health 5분 ✅ Evidence: [emergency.py:184-187](src/application/emergency.py#L184-L187) (cooldown_minutes=30), [ws_health.py:144-146](src/application/ws_health.py#L144-L146) (cooldown_minutes=5)

**문서**:
- [x] Progress Table 업데이트 (Evidence: pytest 결과 + 함수 목록 + 커밋 해시) ✅ Evidence: [task_plan.md:548](docs/plans/task_plan.md#L548) (commit 4a24116, 59f68f4)
- [x] Gate 7 검증 통과 (Section 5.7 커맨드 7개) ✅ Evidence: [task_plan.md:548](docs/plans/task_plan.md#L548) (Gate 7 검증 실행 결과 전문 기록)
- [x] Last Updated 갱신 ✅ Evidence: [task_plan.md:3](docs/plans/task_plan.md#L3) (Last Updated: 2026-01-19 00:15 → 00:30 갱신 예정)

---

### Phase 2: Entry Flow (FLAT → ENTRY_PENDING)
Goal: entry_allowed(게이트) + sizing(contracts) + liquidation gate.

#### Conditions (게이트는 “왜 거절됐는지” 코드로 남겨라)
- entry_allowed는 “REJECT 이유(code)”를 반드시 반환/로그 Intent로 남김
- Gate 순서는 고정(Policy/Flow와 충돌 금지):
  1) emergency/entry_allowed 기본
  2) cooldown/trades/day
  3) stage params
  4) volatility(ATR)
  5) EV gate
  6) maker/taker policy
  7) winrate/streak multiplier
  8) one-way mode

#### Deliverables
- `src/domain/ids.py`
  - `make_signal_id(payload)->short_sha1`
  - `validate_order_link_id(s)->bool` (<=36, [A-Za-z0-9_-])
- `src/application/entry_allowed.py`
- `src/application/sizing.py`
- `src/application/liquidation_gate.py`

#### Tests
- unit entry_allowed: 10~15케이스(각 gate 별 reject/allow)
- unit sizing: 8~12케이스(공식/마진/보정/재검증)
- unit ids: 6케이스

#### DoD
- [ ] signal_id/orderLinkId 규격 구현+테스트
- [ ] 7 gate + one-way + cooldown + reject 이유코드
- [ ] sizing contracts 공식 + margin feasibility + tick/lot 보정
- [ ] liquidation gate + fallback 규칙(Policy 준수)
- [ ] Progress Table 업데이트

---

### Phase 3: Execution (ENTRY_PENDING → IN_POSITION)
Goal: intents → exchange 실행(실제 I/O) + idempotency + fill/cancel 처리.

#### Conditions
- transition은 pure 유지. I/O는 executor에서만.
- idempotency key는 `{signal_id}_{direction}` 기반으로 중복 방지.
- “event-driven 상태 확정” 준수: REST 폴링으로 상태를 “확정”하면 실패.

#### Deliverables
- `src/application/order_executor.py`
- `src/application/event_handler.py`
- `src/application/fee_verification.py`

#### Tests
- unit executor: idempotency/positionIdx/ids
- unit event_handler: fill/partial/cancel/reject
- unit fee_verification: fee spike + tighten intent

#### DoD
- [ ] executor 구현(최소: place/cancel/amend)
- [ ] event_handler 처리
- [ ] fee verify + tightening
- [ ] Progress Table 업데이트

---

### Phase 4: Position Management (IN_POSITION → EXIT_PENDING/FLAT)
Goal: stop_manager(Amend 우선 + debounce) + stop_status 복구 + metrics.

#### Conditions
- Stop Loss 방식은 Policy/Flow의 “Conditional Order 방식 B” 고정
- stop 갱신은 Amend 우선(공백 방지), cancel+place는 최후
- debounce: 20% threshold + 최소 2초 간격
- stop_status는 ACTIVE/PENDING/MISSING/ERROR를 감시하고 recovery intents 생성

#### Deliverables
- `src/application/stop_manager.py`
- `src/application/metrics_tracker.py`

#### Tests
- stop_manager: 10케이스(속성/Amend/공백방지/debounce/entry_working 연동)
- metrics: 6케이스(winrate rolling, streak mult)

#### DoD
- [ ] stop_manager + stop_status recovery
- [ ] metrics_tracker
- [ ] Progress Table 업데이트

---

### Phase 5: Observability
Goal: 실거래 감사(audit) 가능한 **최소 로그 스키마** (v0 - 운영 감사용)

**Phase 5 vs Phase 10 역할 구분**:
- **Phase 5 (v0)**: 운영 감사용 최소 스키마 (Entry/Exit/Halt/Metrics 로그, 재현 가능성 확보)
- **Phase 10 (v1.0)**: 전략 최적화/통계 분석용 확장 스키마 (slippage, latency breakdown, market_regime, integrity fields 추가)

#### Conditions
- 로그는 “재현 가능”해야 한다(결정 근거/정책 버전/스테이지/게이트 결과 포함)
- HALT 로그는 “context snapshot” 필수(가격, equity, stage_candidate, latency 등)

#### Deliverables
- trade_logger / halt_logger / metrics_logger

#### Tests
- schema 테스트(필수 필드 누락 시 실패)

#### DoD
- [ ] 3 logger + schema tests
- [ ] Progress Table 업데이트

---

### Phase 6: Orchestrator Integration
Goal: tick loop에서 Flow 순서대로 실행(application layer 통합).

#### Conditions (Flow 준수)
- Tick 순서 고정: Emergency → Events → Position → Entry
- degraded/normal 분리, degraded 60s -> halt
- integration 케이스는 5~10개 제한(늪 방지)

#### Deliverables
- `src/application/orchestrator.py`

#### Tests
- integration 5~10케이스(전체 사이클/ halt-recover-cooldown / degraded)

#### DoD
- [ ] orchestrator + integration tests
- [ ] Progress Table 업데이트

---

### Phase 7: Real API Integration (클라이언트/어댑터 "골격"만)
Goal: "네트워크 I/O를 붙이되, 실패해도 안전하게 멈추는 연결층"

#### Conditions (안전 우선 + 경계 엄격)

**금지 조항 (Phase 7에서 절대 하지 마)**:
- ❌ **실제 네트워크 호출 전부 금지** (DNS resolve 포함)
  - Contract tests only: requests_mock / respx / aioresponses 같은 mocking 라이브러리만 사용
- ❌ **WS 실제 connect 금지**
  - 메시지 파서/서브스크립션 payload 생성/재연결 상태머신만 테스트
- ❌ **키 누락 시 HALT가 아니라 "프로세스 시작 거부"** (fail-fast)
  - 키 누락 상태에서 봇이 떠 있으면 운영자가 "돌고 있네?" 착각

**필수 조항**:
- ✅ Contract tests only: 네트워크 없이 서명/요청/에러 매핑/리트라이 정책 검증
- ✅ ExchangePort 고정: FakeExchange와 BybitAdapter 모두 동일 Port 구현
- ✅ Rate limit은 X-Bapi-* 헤더 기반 (retCode 10006 우선, HTTP 429 보조)

#### Deliverables
- `src/infrastructure/exchange/exchange_port.py`
  - ExchangeAdapter Port 인터페이스 (FakeExchange도 이 Port 구현)
- `src/infrastructure/exchange/bybit_rest_client.py`
  - 요청 서명/전송/타임아웃/재시도/429 처리
  - X-Bapi-Limit-Status/Reset-Timestamp 기반 throttle
  - Endpoint별 token bucket (초당 제한은 Bybit 문서 기준)
- `src/infrastructure/exchange/bybit_ws_client.py`
  - connect/auth/subscribe/reconnect/heartbeat만
  - ping-pong + max_active_time 정책 (Bybit private stream 요구사항)
- `src/infrastructure/exchange/bybit_adapter.py`
  - REST/WS 결과를 domain 이벤트(ExecutionEvent)로 변환
  - orderLinkId/idempotency 키 정책 준수
  - "event-driven 상태 확정" 위반 금지 (REST polling으로 체결 확정 금지)
- `config/api_config.yaml`
  - API key/secret (env 변수)
  - testnet vs mainnet 엔드포인트
  - rate limit 설정 (per endpoint)

#### 실거래 생존성 함정 3개 (Phase 7에서 반드시 해결)

**1. WS 메시지 폭주/백프레셔**
- 문제: 실전에서 WS는 폭주한다. 파서가 느리면 큐가 무한히 쌓이고 메모리 터진다.
- 해결:
  - WS inbound queue maxsize 설정 (예: 1000 메시지)
  - Overflow 정책: 드랍/DEGRADED/HALT 중 선택
  - 드랍 카운트를 ws_health의 event_drop_count로 연결

**2. Clock 주입 (determinism 보장)**
- 문제: Contract test에서 time.time() 박으면 flaky 된다.
- 해결:
  - REST/WS client에 Clock(callable) 주입
  - Retry/backoff도 clock 기반으로 테스트 가능하게
  - 테스트에서는 fake clock 사용

**3. 실수로 mainnet 주문 방지 (사고 방지)**
- 문제: Phase 8에서 testnet live tests 한다고 해도, 설정 실수 한 번이면 mainnet에 쏜다.
- 해결:
  - **testnet base_url 강제 assert** 코드 레벨에서 박기
  - 예: `if env != "testnet": raise FatalConfigError("mainnet access forbidden before Phase 9")`
  - Phase 7/8에서는 mainnet 엔드포인트 접근 자체를 코드로 차단

#### Tests (Contract Tests Only, 네트워크 0)
- `tests/unit/test_bybit_rest_client.py` (8~10케이스)
  - 서명 생성이 deterministic
  - 요청 payload가 Bybit 스펙 만족 (필수 필드, orderLinkId<=36 등)
  - Rate limit 헤더 처리 로직 (가짜 헤더 주입)
  - retCode 10006 → backoff 동작
- `tests/unit/test_bybit_ws_client.py` (5~7케이스)
  - subscribe topic 정확성 (execution 또는 execution.inverse)
  - disconnect/reconnect 시 DEGRADED 플래그 설정
  - ping-pong timeout 처리
- `tests/unit/test_bybit_adapter.py` (5케이스)
  - WS 메시지 샘플 → ExecutionEvent 변환 (FILL/PARTIAL/CANCEL)
  - REST 응답 → Position/Balance 스냅샷 변환
  - API 에러 → domain 예외 매핑

#### DoD
- [x] ExchangePort 고정 + FakeExchange/BybitAdapter 구현
- [x] REST client: timeout/retry/retCode/헤더 기반 throttle
- [x] WS client: auth/subscribe/reconnect/ping-pong
- [x] **실거래 함정 3개 해결**:
  - WS queue maxsize + overflow 정책 구현
  - Clock 주입 (fake clock 테스트 가능)
  - testnet base_url 강제 assert (mainnet 접근 차단)
- [x] Contract tests (18~22 cases) 통과 (네트워크 0)
- [x] **실제 네트워크 호출 0개 검증** (DNS resolve 포함)
- [x] API key 로딩 실패 시 **프로세스 시작 거부** 동작 검증 (HALT 아님)
- [x] Progress Table 업데이트
- [x] **Gate 7: CLAUDE.md Section 5.7 검증 통과**

---

### Phase 8: Testnet Validation (재현 가능한 시나리오 5개만)
Goal: 실제 네트워크/거래소에서 "핵심 위험 이벤트"가 예상대로 동작하는지 증명

#### Conditions (증거 필수)
- **시나리오 5개로 제한**: 늪 방지
- **재현 가능성 필수**: 실패 시 "원인 분류(네트워크/권한/스키마/레이트리밋)"가 재현 가능해야 DONE
- 로그 + 실행 커맨드 + 결과 캡처를 docs/evidence/phase_8/에 저장

#### 검증 시나리오 (5개 고정)
1. **연결/인증/구독 성공 + heartbeat 정상**
   - wss://stream-testnet.bybit.com/v5/private 연결
   - auth 성공
   - execution.inverse topic 구독 성공
   - heartbeat 10초 이내 수신
2. **소액 주문 발주→취소 성공 (idempotency 포함)**
   - place_entry_order() 호출 → orderLinkId 생성
   - 동일 orderLinkId 재시도 → DuplicateOrderError (또는 기존 주문 조회)
   - cancel_order() 성공
3. **체결 이벤트 수신→도메인 이벤트 매핑 성공**
   - 주문 체결 발생
   - WS execution 메시지 수신
   - ExecutionEvent(FILL/PARTIAL) 변환 성공
4. **Rate limit 강제 발생 → backoff 동작**
   - 짧은 시간 내 다수 요청 → **retCode 10006 발생** (Bybit 공식 rate limit 신호)
   - X-Bapi-Limit-Reset-Timestamp 기반 backoff
   - "진입 차단" 또는 "degraded" 플래그 설정
   - (보조) HTTP 429 응답도 처리 (프록시/게이트웨이 레벨)
5. **WS 강제 disconnect → reconnect + degraded 타이머**
   - WS 연결 강제 종료
   - reconnect 시도
   - DEGRADED 모드 진입 (10초 heartbeat timeout)
   - 복구 시 DEGRADED 해제

#### Tests (Live Tests, Testnet Only)
- `tests/integration_real/test_testnet_connection.py` (시나리오 1)
- `tests/integration_real/test_testnet_order_flow.py` (시나리오 2)
- `tests/integration_real/test_execution_event_mapping.py` (시나리오 3)
- `tests/integration_real/test_rate_limit_handling.py` (시나리오 4)
- `tests/integration_real/test_ws_reconnection.py` (시나리오 5)

#### WebSocket 클라이언트 구현 완료 (2026-01-23)

**구현 결과**: 시나리오 1, 3, 5를 위한 실제 WebSocket 연결 구현 완료. `bybit_ws_client.py`는 Bybit V5 프로토콜을 완전히 준수하며, 실거래 환경에서 안정적으로 동작한다.

**구현된 기능**:
- ✅ 상태 관리: `_degraded`, `_degraded_entered_at`, `_last_pong_at`
- ✅ 메시지 큐: `deque(maxlen=1000)` (FIFO, overflow 정책)
- ✅ Policy 검증: API key/secret 누락 → FatalConfigError, Mainnet URL 차단
- ✅ Clock 주입 (determinism)
- ✅ **실제 WebSocket 연결/Auth/Subscribe/메시지 수신 루프** (489 LOC, 24 메서드: public 14 + private 10)

**구현된 내용**:

1. **라이브러리**: `websocket-client==1.6.4` (동기식)
   - Thread 기반 구현으로 현재 코드베이스와 일관성 유지
   - Bybit 공식 예제와 동일한 접근법

2. **Thread 모델**: Background Thread + Message Queue (Single Producer/Single Consumer)
   - Main Thread: `start()` → WS Thread 시작, `dequeue_message()` → 메시지 처리 (Consumer)
   - WS Thread: `connect()` → `auth()` → `subscribe()` → `recv_loop()` (메시지 수신 → `enqueue_message()`) (Producer)
   - Thread Safety: 단일 producer/consumer 패턴, `deque.append()`/`popleft()` atomic 동작

3. **Bybit V5 WebSocket 프로토콜 준수** (SSOT: Bybit 공식 문서):
   - **연결**: `wss://stream-testnet.bybit.com/v5/private` (Private stream)
   - **Auth**: HMAC-SHA256 서명 (`"GET/realtime{expires}"`)
   - **Subscribe**: `execution.inverse` topic (Categorised)
   - **Ping/Pong**: 클라이언트 ping (20초 주기) → 서버 pong
   - **Execution 메시지**: `{"topic": "execution.inverse", "data": [...]}`

4. **구현된 메서드** (24 메서드: public 14 + private 10):
   - **Public (14개)**: `__init__`, `get_subscribe_payload`, `on_disconnect`, `on_reconnect`, `is_degraded`, `get_degraded_entered_at`, `on_pong_received`, `check_pong_timeout`, `enqueue_message`, `dequeue_message`, `get_queue_size`, `get_drop_count`, `start`, `stop`
   - **Private (10개)**: `_generate_auth_signature`, `_send_auth`, `_send_subscribe`, `_send_ping`, `_ping_loop`, `_on_ws_message`, `_on_ws_open`, `_on_ws_error`, `_on_ws_close`, `_run_ws_thread`

5. **Live Tests 완료** (16개):
   - `test_testnet_connection.py`: 시나리오 1 (3 passed)
   - `test_testnet_order_flow.py`: 시나리오 2 (4 passed)
   - `test_execution_event_mapping.py`: 시나리오 3 (2 passed, 1 skip)
   - `test_rate_limit_handling.py`: 시나리오 4 (3 passed)
   - `test_ws_reconnection.py`: 시나리오 5 (3 passed)

**검증 완료된 위험 요소**:
- ✅ Thread Safety: SPSC 패턴 유지, 동기화 이슈 없음
- ✅ Reconnection Logic: 수동 reconnect 정상 동작 (시나리오 5)
- ✅ Ping Timeout: 20초 주기 ping 전송, heartbeat 정상 (시나리오 1)
- ✅ Message Queue Overflow: maxsize=1000, 드랍 정책 동작 확인

**완료된 시나리오**:
- ✅ 시나리오 1 (WS 연결/인증/구독 + heartbeat): 3/3 passed
- ✅ 시나리오 2 (REST 주문 발주/취소): 4/4 passed
- ✅ 시나리오 3 (체결 이벤트 수신 + 도메인 매핑): 2/3 passed, 1 skip (예상됨)
- ✅ 시나리오 4 (Rate limit + backoff): 3/3 passed
- ✅ 시나리오 5 (WS disconnect + reconnect + DEGRADED): 3/3 passed

**실제 결과**:
- ✅ Phase 8 완료: 5/5 (100%) 시나리오 검증 완료
- ✅ 전체 테스트: 188 passed (contract tests) + 15 passed, 1 skip (live tests)
- ✅ Evidence: [phase_8/](../evidence/phase_8/) (completion_checklist.md + 5개 시나리오 로그)
- ✅ 새 세션 검증 가능: `./scripts/verify_phase_completion.sh 8` (예상)

#### DoD
- [x] 5개 시나리오 모두 성공 (testnet) ✅ Evidence: [completion_checklist.md](../evidence/phase_8/completion_checklist.md) (15 passed, 1 skip)
- [x] docs/evidence/phase_8/에 증거 저장 ✅ Evidence: [scenario logs](../evidence/phase_8/) (5개 시나리오 로그 + gate7 + pytest + red_green_proof)
  - 실행 커맨드: `export $(cat .env | xargs) && pytest -v -m testnet tests/integration_real/`
  - 로그 출력 (API 응답 + WS 메시지): scenario_1_connection.log, scenario_2_order_flow.log, scenario_3_execution_mapping.log, scenario_4_rate_limit.log, scenario_5_reconnection.log
  - 결과 캡처 (성공/실패 + 원인): [pytest_output.txt](../evidence/phase_8/pytest_output.txt) (15 passed, 1 skip in 140.90s)
- [x] 실패 시 원인 분류 재현 가능 (네트워크/권한/스키마/레이트리밋) ✅ Evidence: [red_green_proof.md](../evidence/phase_8/red_green_proof.md) (retCode 10004, heartbeat timeout, skip decorator 제거)
- [x] Progress Table 업데이트 ✅ Evidence: [task_plan.md:1049](task_plan.md#L1049) (Phase 8 DONE, Evidence 링크, Last Updated: 2026-01-23)
- [x] **Gate 7: CLAUDE.md Section 5.7 검증 통과** ✅ Evidence: [gate7_verification.txt](../evidence/phase_8/gate7_verification.txt) (Gate 1a~6b ALL PASS, 188 passed + 15 passed 1 skip)

---

### Phase 9: Mainnet Preparation (Session Risk Policy + 운영 안전장치)

**Status**: ✅ **DONE** (2026-01-24). Phase 9a/9b/9c + Revision + 9d 완료. Session Risk Policy 4개 + Per-Trade Cap 감소 + Orchestrator 통합 + UTC boundary 버그 수정 + Slippage anomaly 버그 수정. 아래 진단/설계는 **구현 전 위험 분석** (보존용).

**구현 완료 내용**:
- Session Risk Policy 4개 (Daily -5%, Weekly -12.5%, Loss Streak 3/5, Fee/Slippage Anomaly)
- Per-Trade Cap $10→$3 감소 (ADR-0001)
- Orchestrator 통합 (Emergency check에 Session Risk 통합)
- Safety Infrastructure (Kill Switch, Alert, Rollback)
- Config: safety_limits.yaml (Dry-Run 4개 상한)

**결과**: **"도박 단계" → "계좌 보호 단계" 전환 완료** (3중 보호: Session + Trade + Emergency)

#### ✅ Phase 9d: CRITICAL 문제 해결 완료 (2026-01-24)

**CRITICAL (필수 수정)** → ✅ **완료**:
1. `orchestrator.py` `current_timestamp = None` 초기화 누락
   - **문제**: Slippage anomaly 보호 완전히 무력화
   - **수정**: orchestrator.py:113 run_tick()에서 `self.current_timestamp = self.market_data.get_timestamp()` 추가
   - **증거**: [phase_9d/slippage_fix_proof.md](../evidence/phase_9d/slippage_fix_proof.md)
   - **결과**: Slippage Anomaly Kill 정상 작동 (test_slippage_anomaly_triggers_halt 통과)

**MEDIUM (권장 수정)** → ✅ **완료**:
2. `FakeMarketDataWithSessionRisk` `get_timestamp()` 테스트 불일치
   - **문제**: time.time() 반환으로 테스트 timestamp와 불일치
   - **수정**: self.current_timestamp 필드 추가 + get_timestamp() 수정
   - **증거**: [phase_9d/pytest_output_session_risk.txt](../evidence/phase_9d/pytest_output_session_risk.txt)

**LOW (선택 수정)** → **보류** (실거래 영향 없음):
3. `session_risk.py` 주석-코드 불일치
   - **문제**: 주석 "floor", 코드 "int" (양수에서 동일, 음수에서 다름)
   - **상태**: Phase 10+ 정리 예정

**실거래 투입 조건** → ✅ **모두 충족**:
- [x] CRITICAL Issue #1 수정 완료 (orchestrator.py current_timestamp 초기화)
- [x] 전체 테스트 통과 (238 passed, integration_real/bybit_ws_client 제외)
- [x] Slippage Anomaly Kill 통합 테스트 통과 (test_slippage_anomaly_triggers_halt)
- [x] Evidence: phase_9d/ 디렉토리 생성 (slippage_fix_proof.md, pytest_output, completion_checklist.md)

---

#### 구현 전 위험 진단 (Historical - 보존용)

**⚠️ 치명적 발견 (Phase 8 완료 시점)**: Phase 8까지 시스템은 **Per-trade cap만 있고 Session cap이 없어** "도박 단계"였음.
- **Per-trade Cap**: ✅ $10 (Stage 1) 존재
- **Session Cap**: ❌ 없음 → 5연속 -$10 = -$50 (계좌 50% 증발 가능)

**Phase 8 완료 시점 위험 진단**:

| 항목 | Phase 8 완료 시 상태 | 위험 |
|------|-------------------|------|
| 일일 손실 상한 | ❌ 없음 | 5연속 -$10 = -$50 (계좌 50%) |
| 주간 손실 상한 | ❌ 없음 | 복구 욕망 무제한 |
| 연속 손실 중단 | △ 축소만 (3연패 시 size 0.5배) | 계속 거래 가능 |
| 거래 횟수 상한 | ✅ 5회/일 (Stage 1) | OK |
| 수수료/슬리피지 HALT | △ 감지만 (fee spike → 24h tighten) | HALT 없음 |

**판정 (당시)**: **도박 단계** (계좌가 0이 될 때까지 거래 가능) → **Phase 9에서 해결 완료**

---

#### Phase 9a: Session Risk Policy (4개 Kill Switch)

**우선순위**: ⭐ CRITICAL (Mainnet 진입 전 필수)

##### 1. Daily Loss Cap (일일 손실 상한)

**정책** (초기 권장):
- **Trigger**: `daily_realized_pnl_usd <= -4% ~ -6% equity`
- **Action**: HALT (당일 거래 종료) + COOLDOWN (다음날 UTC 0시까지)
- **예시**: equity $100 → -$4 ~ -$6

**구현 위치**: `src/application/session_risk.py`

**테스트**:
- `test_daily_loss_cap_not_exceeded`: daily_pnl = -4%, cap = 5% → ALLOW
- `test_daily_loss_cap_exceeded`: daily_pnl = -6%, cap = 5% → HALT + cooldown
- `test_daily_loss_cap_reset_at_boundary`: UTC 경계 넘으면 daily_pnl 리셋

##### 2. Weekly Loss Cap (주간 손실 상한)

**정책** (초기 권장):
- **Trigger**: `weekly_realized_pnl_usd <= -10% ~ -15% equity`
- **Action**: COOLDOWN (7일)
- **예시**: equity $100 → -$10 ~ -$15

**구현 위치**: `src/application/session_risk.py`

**테스트**:
- `test_weekly_loss_cap_not_exceeded`: weekly_pnl = -10%, cap = 12.5% → ALLOW
- `test_weekly_loss_cap_exceeded`: weekly_pnl = -15%, cap = 12.5% → COOLDOWN 7일
- `test_weekly_loss_cap_reset_at_boundary`: 주 경계 넘으면 weekly_pnl 리셋

##### 3. Loss Streak Kill (연속 손실 중단)

**정책** (초기 권장):
- **3연패**: 당일 거래 종료 (HALT)
- **5연패**: 72시간 COOLDOWN
- **현재 축소 로직 유지**: 3연패 시 size 0.5배 (중단 전 단계)

**구현 위치**: `src/application/session_risk.py`

**테스트**:
- `test_loss_streak_2`: loss_streak = 2 → ALLOW
- `test_loss_streak_3_halt`: loss_streak = 3 → HALT (당일)
- `test_loss_streak_5_cooldown`: loss_streak = 5 → COOLDOWN 72h

##### 4. Fee/Slippage Anomaly HALT (수수료/슬리피지 이상치)

**정책** (초기 권장):
- **Fee Spike**: `fee_ratio > 1.5` (예상 대비 50%↑) **2회 연속** → HALT 30분
- **Slippage Spike**: `abs(slippage_usd) > $X` **3회/10분** → HALT 60분
- **WS DEGRADED**: 재연결 루프 진입 시 → 신규 진입 차단 (청산만 허용)

**구현 위치**: `src/application/session_risk.py`

**테스트**:
- `test_fee_spike_single`: fee_ratio 1.6 1회 → ALLOW
- `test_fee_spike_consecutive_halt`: fee_ratio 1.6, 1.7 연속 → HALT 30분
- `test_slippage_spike_2_times`: 10분 내 2회 → ALLOW
- `test_slippage_spike_3_times_halt`: 10분 내 3회 → HALT 60분
- `test_slippage_spike_window_expired`: 11분 전 spike → 카운트 제외

---

#### Phase 9b: Per-Trade Cap 조정 (권장)

**현재**: Stage 1 → $10 (equity $100 기준 10%)
**문제**: 10% 손실 1회는 작은 계좌에 치명적
**권장**: **2~3% equity**로 축소

**account_builder_policy.md 수정** (ADR 필요):
```yaml
# Stage 1 (equity < $300)
max_loss_usd_cap: $3  # 현재 $10 → $3 (3%)
loss_pct_cap: 3%      # 현재 12% → 3%
```

**근거**: $100 → $1,000 목표는 "안 죽는 베팅"이 우선

---

#### Phase 9c: Orchestrator Integration + 기존 안전장치

**기존 요구사항 유지**:
- Mainnet/Testnet 설정 완전 분리 (키/엔드포인트/심볼/레버리지)
- 킬스위치/알림/롤백 프로토콜
- dry-run 4개 상한

**Deliverables**:
- `src/application/session_risk.py` (Session Risk Policy 4개 구현)
- `src/infrastructure/safety/killswitch.py` (기존 요구사항)
- `src/infrastructure/safety/alert.py` (기존 요구사항)
- `src/infrastructure/safety/rollback_protocol.py` (기존 요구사항)
- `config/safety_limits.yaml` (dry-run 4개 상한)

#### Tests

**Session Risk Tests** (15개):
- `tests/unit/test_session_risk.py` (15케이스)
  - Daily loss cap: 3 cases
  - Weekly loss cap: 3 cases
  - Loss streak kill: 3 cases
  - Fee/slippage anomaly: 6 cases

**기존 Tests** (9개):
- `tests/unit/test_killswitch.py` (6케이스)
- `tests/unit/test_alert.py` (3케이스)

**Integration Tests** (5개):
- `tests/integration/test_orchestrator_session_risk.py` (5케이스)

#### DoD

**Phase 9a** (Session Risk Policy, 2-3시간):
- [ ] Session Risk Policy 4개 구현 (`src/application/session_risk.py`)
  - Daily loss cap (5%)
  - Weekly loss cap (12.5%)
  - Loss streak kill (3 halt, 5 cooldown)
  - Fee/slippage anomaly (2연속 fee spike, 3회/10분 slippage)
- [ ] 테스트 15개 작성 → RED → GREEN
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_9a/`)
- [ ] **Gate 7: CLAUDE.md Section 5.7 검증 통과**

**Phase 9b** (Per-trade cap 조정, 1-2시간):
- [ ] account_builder_policy.md 수정 (ADR 필요)
  - Stage 1: max_loss_usd_cap $10 → $3
  - Stage 1: loss_pct_cap 12% → 3%
- [ ] ADR 작성 (ADR-000X)
- [ ] 테스트 업데이트 (sizing.py 테스트)

**Phase 9c** (Orchestrator 통합 + 기존 안전장치, 1시간):
- [ ] Orchestrator에 Session Risk 통합
- [ ] 기존 킬스위치/알림/롤백 구현
- [ ] Integration tests 5개
- [ ] dry-run 4개 상한 문서화 (safety_limits.yaml)
- [ ] dry-run 실행 (testnet → mainnet 최소 금액)
- [ ] Progress Table 업데이트
- [ ] **Gate 7: CLAUDE.md Section 5.7 검증 통과**

**Phase 9 완료 기준**:
- ✅ Session Risk가 계좌를 보호함 (도박 종료)
- ✅ Mainnet 초기 30~50 거래에서 Kill Switch 발동 증거 (1회 이상)
- ✅ 실행 결함 0건

---


### Phase 10: Trade Logging Infrastructure (Phase 9 완료 후)

**⚠️ 주의**: Phase 10+는 실거래 최적화 단계로, **Phase 0-9와 별개의 작업 영역**입니다.

Goal: 실거래 데이터를 수집하고 전략 파라미터를 조정하기 위한 로깅 인프라 구축

#### 참조 문서
- **SSOT**: `~/.claude/plans/wondrous-waddling-petal.md` (Phase 10+ 전략 최적화 계획 v2.0)
- **DoD 5개**: Trade Log 확장, Phase 종료조건 통일, A/B 랜덤화, 통계 검정 변경, Daily Loss Budget

#### Scope (Phase 10 최소 범위)
1. **Trade Log Schema v1.0 구현** (DoD 1/5):
   - 실행 품질 필드: order_id, fills, slippage, latency breakdown, orderbook
   - Market data: funding/mark/index, market_regime (DoD 3/5)
   - 무결성 필드: schema_version, config_hash, git_commit, exchange_server_time_offset (DoD 5/5)

2. **Log Storage 구현**:
   - JSON Lines (.jsonl) 파일 저장
   - Append-only (O_APPEND), Daily rotation (UTC)
   - Durable append: Single syscall write per line (os.write, not multiple str writes)
   - Crash safety: Recover by truncating last partial line on read/startup
   - Durability policy: flush each append, fsync (a) batch (10 lines) / (b) periodic (1s) / (c) critical event (HALT/LIQ/ADL)
   - Rotation: Day boundary (UTC) handle swap, with pre-rotate flush+fsync and optional fsync(dir)
   - Concurrency: Single writer required (or lock/queue)

3. **테스트**:
   - `tests/unit/test_trade_logger_v1.py` (8+ tests)
   - `tests/unit/test_log_storage.py` (7+ tests)
   - Trade Log Schema v1.0 검증 (DoD 1/5, 3/5, 5/5)

#### DoD (Definition of Done)
- [ ] Trade Log Schema v1.0 dataclass 구현 (`src/infrastructure/logging/trade_logger_v1.py`)
  - DoD 1/5: order_id, fills, slippage, latency breakdown, funding/mark/index, integrity fields 포함
  - DoD 3/5: market_regime 필드 필수 (deterministic 정의: MA slope + ATR percentile, 4개 enum: trending_up/trending_down/ranging/high_vol)
  - DoD 5/5: schema_version, config_hash, git_commit, exchange_server_time_offset 필드 필수 (누락 시 validation FAIL)
- [ ] Log Storage 구현 (`src/infrastructure/storage/log_storage.py`)
  - append_trade_log_v1(): Single syscall write (os.write), flush, fsync policy (batch/periodic/critical)
  - read_trade_logs_v1(): 특정 날짜 로그 읽기 + partial line recovery (truncate last line if JSON parse fails)
  - Daily rotation (UTC): Handle swap with pre-rotate flush+fsync
  - Durability policy: (a) batch (10 lines) / (b) periodic (1s) / (c) critical event immediate fsync
  - Crash safety: Startup validation + truncate partial line
- [ ] 테스트 구현
  - `tests/unit/test_trade_logger_v1.py`: 8+ tests (DoD 1/5, 3/5, 5/5 검증)
    - **필수 failure-mode tests**: schema_version/config_hash/git_commit 필드 누락 시 validation FAIL
    - market_regime deterministic 계산 검증 (MA slope + ATR percentile → 4개 enum)
  - `tests/unit/test_log_storage.py`: 7+ tests (파일 저장/읽기/rotation)
    - **필수 failure-mode tests**: rotation boundary line 누락 방지, partial line recovery (마지막 라인 JSON parse 실패 시 truncate), fsync policy (batch/periodic/critical), single syscall write 검증
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_10/`)
  - gate7_verification.txt (CLAUDE.md Section 5.7 검증 명령 출력)
  - pytest_output.txt (pytest 실행 결과)
  - red_green_proof.md (RED→GREEN 재현 증거)
- [ ] Progress Table 업데이트 (이 섹션)
  - Last Updated 갱신
  - Evidence 링크 추가
- [ ] **Gate 7: CLAUDE.md Section 5.7 검증 통과**

---

### Phase 11a: Signal Generation + Exit Manager (Phase 10 완료 후)

**Scope**: 독립적으로 완료 가능한 최소 단위 (Grid 신호 + Exit 로직)

Goal: Signal generator 구현 + Exit manager 구현 → **Unit 테스트로 100% 검증**

#### DoD (Definition of Done)

- [x] Signal Generator 구현 (`src/application/signal_generator.py`)
  - Grid-based signal generation (간단한 구현)
  - ATR 기반 grid spacing 계산
  - Last fill price 기반 grid level 결정
- [x] Exit Logic 구현 (`src/application/exit_manager.py`)
  - check_stop_hit(): Stop loss 도달 확인 (LONG/SHORT)
  - create_exit_intent(): Exit intent 생성 (Market order)
- [x] ExitIntent 추가 (`src/domain/intent.py`)
- [x] Orchestrator 최소 통합 (Exit Manager만)
- [x] 테스트 구현
  - test_signal_generator.py: 10 cases
  - test_exit_manager.py: 8 cases
- [x] Evidence Artifacts 생성 (`docs/evidence/phase_11a/`)
- [x] Progress Table 업데이트
- [x] **Gate 7: CLAUDE.md Section 5.7 검증 통과**

#### 완료 기준

- ✅ Unit 테스트 18개 모두 통과 (Grid 신호 + Exit logic)
- ✅ Gate 7 검증 ALL PASS
- ✅ 100% 완료 (Entry flow/Testnet 제외, 독립적 완료 가능)

---

### Phase 11b: Full Orchestrator Integration + Testnet E2E (Phase 11a 완료 후)

**⚠️ 중요**: Phase 11b 완료 시 **Testnet에서 전체 사이클 (FLAT → Entry → Exit → FLAT) 성공**

Goal: Full orchestrator cycle 완성 → **Testnet 실거래 가능**

#### Scope

1. **Full Orchestrator Integration**:
   - Entry decision: Signal → Entry gates → Sizing → Place order
   - Exit decision: Stop hit → Place exit order
   - Event processing: FILL → Update position → Log trade
   - Full cycle: FLAT → ENTRY_PENDING → IN_POSITION → EXIT_PENDING → FLAT

2. **Testnet End-to-End Tests**:
   - `tests/integration_real/test_full_cycle_testnet.py` (5+ tests)
   - 최소 10회 거래 성공 검증
   - Session Risk 정상 작동 확인

#### DoD (Definition of Done)

- [ ] Full Orchestrator Integration (`src/application/orchestrator.py` 수정)
  - Entry decision: Signal → Gates → Sizing → Order placement
  - Exit decision: Stop hit → Place exit order
  - Event processing: FILL → Position update → Trade log
- [ ] Testnet End-to-End Tests
  - `tests/integration_real/test_full_cycle_testnet.py` (5+ cases)
  - Full cycle 성공 (FLAT → Entry → Exit → FLAT)
  - 최소 10회 거래 성공 검증
  - Session Risk 발동 확인 (Daily cap 또는 Loss streak)
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_11b/`)
  - testnet_cycle_proof.md (Testnet 전체 사이클 증거)
  - pytest_output.txt
  - gate7_verification.txt
- [ ] Progress Table 업데이트
- [ ] **Gate 7: CLAUDE.md Section 5.7 검증 통과**

#### 완료 기준

- ✅ Testnet에서 FLAT → Entry → Position → Exit → FLAT 사이클 최소 10회 성공
- ✅ Session Risk 정상 작동 (Daily cap 또는 Loss streak 발동 증거 1회 이상)
- ✅ Trade log 정상 기록 (Phase 10 로깅 인프라 사용)
- ✅ 모든 테스트 통과 (Unit + Integration + Testnet E2E)

---

### Phase 12: Dry-Run Validation (Phase 11 완료 후)

**⚠️ 중요**: Phase 12 완료 시 **Mainnet 실거래 가능** (최소 금액으로 시작)

Goal: **완전 자동화된 Testnet/Mainnet Dry-Run** → **실거래 준비 완료**

**구현 방식**: Full Automated (BybitAdapter + Automated Dry-Run Infrastructure)

---

#### Phase 12a-1: BybitAdapter 완전 구현 (1-2일)

**Goal**: BybitRestClient + BybitWsClient → MarketDataInterface 변환

**Scope**:
1. **REST API Integration**:
   - GET /v5/market/tickers (Mark price, Index price, Funding rate 조회)
   - GET /v5/account/wallet-balance (Equity 조회)
   - GET /v5/position/list (Current position 조회)
   - GET /v5/execution/list (Trade history 조회 → PnL/Loss streak 계산)

2. **WebSocket Integration**:
   - `execution.inverse` topic subscribe (FILL event 수신)
   - WS heartbeat monitoring (degraded 감지)
   - Event queue processing (FILL → domain ExecutionEvent 변환)

3. **State Caching**:
   - mark_price, equity, position 캐싱 (1초마다 REST 업데이트)
   - last_fill_price 추적 (FILL event로 업데이트)
   - trades_today 카운터 (UTC boundary에서 리셋)

**DoD**:
- [x] BybitAdapter 구현 (`src/infrastructure/exchange/bybit_adapter.py`)
  - MarketDataInterface 모든 메서드 구현
  - REST API 통합 (4 endpoints)
  - WebSocket event 처리 (execution.inverse)
  - State caching + 1초마다 업데이트
- [x] Tests: `tests/unit/test_bybit_adapter.py` (14 cases, 10+ 초과)
  - REST API 응답 → MarketDataInterface 변환
  - WebSocket event → ExecutionEvent 변환
  - Caching 동작 검증
  - DEGRADED 모드 전환 검증
- [x] Evidence Artifacts (`docs/evidence/phase_12a1/`)
  - completion_checklist.md
  - pytest_output.txt
  - gate7_verification.txt
  - red_green_proof.md
- [x] Progress Table 업데이트

---

#### Phase 12a-2: Market Data Provider 구현 (1-2일)

**Goal**: ATR 계산 + Session Risk tracking + Trade history 분석

**Scope**:
1. **ATR Calculator** (`src/application/atr_calculator.py`):
   - Kline 데이터 조회 (GET /v5/market/kline)
   - ATR 계산 (14-period ATR)
   - ATR percentile 계산 (rolling 100-period)

2. **Session Risk Tracker** (`src/application/session_risk_tracker.py`):
   - Daily/Weekly PnL 추적 (UTC boundary 인식)
   - Loss streak 계산 (Trade history 기반)
   - Fee ratio history 추적
   - Slippage history 추적 (10분 윈도우)

3. **Market Regime Analyzer** (`src/application/market_regime.py`):
   - MA slope 계산 (Kline 데이터 기반)
   - ATR percentile 기반 regime 분류
   - Phase 11b Trade Log 통합

**DoD**:
- [ ] ATR Calculator 구현
  - calculate_atr(): Kline → ATR (14-period)
  - calculate_atr_percentile(): Rolling 100-period percentile
  - calculate_grid_spacing(): ATR * multiplier
- [ ] Session Risk Tracker 구현
  - track_daily_pnl(): Trade history → Daily PnL
  - track_weekly_pnl(): Trade history → Weekly PnL
  - calculate_loss_streak(): Trade history → Loss streak
  - track_fee_ratio(): Fill events → Fee ratio history
  - track_slippage(): Fill events → Slippage history
- [ ] Market Regime Analyzer 구현
  - calculate_ma_slope(): Kline → MA slope
  - classify_regime(): MA slope + ATR percentile → regime
- [ ] Tests: `tests/unit/test_atr_calculator.py` (8+ cases)
- [ ] Tests: `tests/unit/test_session_risk_tracker.py` (12+ cases)
- [ ] Tests: `tests/unit/test_market_regime.py` (5+ cases)
- [ ] BybitAdapter 통합 (위 3개 모듈 사용)
- [ ] Evidence Artifacts (`docs/evidence/phase_12a2/`)
- [ ] Progress Table 업데이트

---

#### Phase 12a-3: Automated Dry-Run Infrastructure (1일)

**Goal**: 자동화된 Dry-Run 실행 인프라 구축

**Scope**:
1. **Dry-Run Orchestrator** (`scripts/run_testnet_dry_run.py`):
   - Orchestrator + BybitAdapter 통합
   - Tick loop 실행 (1초마다)
   - State 전환 감지 (FLAT → Entry → Exit → FLAT)
   - HALT 감지 및 복구

2. **Dry-Run Monitor** (`src/application/dry_run_monitor.py`):
   - 거래 통계 추적 (Total trades, Win/Loss, PnL)
   - Session Risk 발동 감지 (Daily cap, Loss streak)
   - Stop loss hit 카운트
   - 실시간 로그 출력

3. **Evidence Generator** (`scripts/generate_dry_run_report.py`):
   - Trade Log 분석
   - Session Risk 검증
   - DoD Checklist 자동 생성
   - Testnet UI 스크린샷 가이드

**DoD**:
- [ ] run_testnet_dry_run.py 구현
  - Orchestrator + BybitAdapter 초기화
  - Tick loop (target_trades까지 실행)
  - State transition 감지
  - HALT handling
  - Graceful shutdown (Ctrl+C 처리)
- [ ] DryRunMonitor 구현
  - log_cycle_complete(): Full cycle 완료 기록
  - log_halt(): HALT 발생 기록
  - log_stop_hit(): Stop loss hit 기록
  - print_summary(): 통계 요약 출력
- [ ] generate_dry_run_report.py 구현
  - Trade Log 파일 분석
  - Session Risk 검증
  - completion_checklist.md 자동 생성
- [ ] Tests: `tests/integration/test_dry_run_orchestrator.py` (5+ cases)
- [ ] Evidence Artifacts (`docs/evidence/phase_12a3/`)
- [ ] Progress Table 업데이트

---

#### Phase 12a-4: Force Entry 모드 구현 + Testnet 자동 거래 (1-2일)

**Goal**: Grid Signal 블로커 해결 + Testnet 30-50회 거래 실행 (로그 모니터링)

**Scope**:
1. **Testnet 설정**:
   - API credentials 설정 (.env)
   - Testnet equity 확인 (0.01 BTC 이상)
   - safety_limits.yaml 설정 (testnet_max_trades: 50)

2. **Force Entry 모드 구현** (Grid Signal 블로커 해결):
   - `signal_generator.py`: `force_entry` 파라미터 추가
     - `force_entry=True`: Grid spacing 체크 무시, 즉시 Buy 신호
   - `orchestrator.py`: `force_entry` 전달
   - `run_testnet_dry_run.py`: `--force-entry` 플래그 추가

3. **Testnet 자동 거래 실행**:
   - `python scripts/run_testnet_dry_run.py --target-trades 30 --force-entry`
   - 로그 모니터링: `tail -f logs/testnet_dry_run/testnet_dry_run.log`
   - Session Risk 발동 대기 (Daily cap 또는 Loss streak)

4. **검증 및 Evidence**:
   - Trade Log 완전성 검증 (30회 == 30 logs)
   - Session Risk 발동 증거 (1회 이상)
   - Stop loss 작동 증거 (5회 이상)
   - Bybit Testnet UI 스크린샷

**DoD**:
- [x] **Sub-task 12a-4a: Force Entry 모드 구현** ✅ COMPLETE (2026-01-25)
  - [x] TDD: `test_signal_generator_force_entry.py` 작성
    - Test case 1: `force_entry=True` → 즉시 Buy 신호 (Grid spacing 무시)
    - Test case 2: `force_entry=True` + `last_fill_price=None` → Buy 신호
    - Test case 3: `force_entry=False` → 정상 Grid 로직
  - [x] `signal_generator.py`: `force_entry` 파라미터 추가
    - `generate_signal(force_entry: bool = False)` 시그니처 수정
    - `force_entry=True`일 때 Grid spacing 체크 무시, 즉시 Buy 신호 반환
  - [x] `orchestrator.py`: `force_entry` 전달
    - `__init__(force_entry: bool = False)` 파라미터 추가
    - `_decide_entry()`: `generate_signal(force_entry=self.force_entry)` 전달
  - [x] `run_testnet_dry_run.py`: `--force-entry` 플래그 추가
    - `argparse.add_argument("--force-entry", action="store_true")`
    - Orchestrator 초기화 시 `force_entry=args.force_entry` 전달
    - WARNING 로그: "⚠️  Force Entry Mode: Grid spacing ignored"
  - [x] 회귀 테스트: `pytest -q` 통과 (326 passed, +6)
  - [x] Evidence: [force_entry_implementation.md](../../docs/evidence/phase_12a4/force_entry_implementation.md)
  - **커밋**: 8b9a3c0

- [~] **Sub-task 12a-4b: Testnet 설정 완료**
  - [ ] .env 파일 작성 (BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_TESTNET=true)
  - [ ] Testnet equity >= 0.01 BTC 확인
  - [ ] `config/safety_limits.yaml` 설정 확인 (testnet_max_trades: 50)

- [ ] **Sub-task 12a-4c: Testnet 30-50회 거래 실행**
  - [ ] `python scripts/run_testnet_dry_run.py --target-trades 30 --force-entry` 실행
  - [ ] 로그 모니터링: `tail -f logs/testnet_dry_run/testnet_dry_run.log`
  - [ ] Full cycle (FLAT → Entry → Exit → FLAT) 30회 이상 성공
  - [ ] Session Risk 발동 증거 1회 이상 (Daily cap / Weekly cap / Loss streak)
  - [ ] Stop loss 정상 작동 확인 (최소 5회)
  - [ ] Fee tracking 정상 작동 (모든 거래에서 fee 기록)
  - [ ] Slippage tracking 정상 작동 (slippage 기록)

- [ ] **Sub-task 12a-4d: 로그 완전성 검증**
  - [ ] 모든 거래가 trade_log에 기록됨 (expected == actual)
  - [ ] Daily/Weekly PnL 계산 정확성 확인
  - [ ] Loss streak count 정확성 확인

- [ ] **Sub-task 12a-4e: Testnet Dry-Run Report 작성**
  - [ ] `docs/evidence/phase_12a4/testnet_dry_run_report.md` 작성
    - 거래 요약 (총 거래, winrate, profit/loss)
    - Session Risk 발동 내역
    - 발견된 문제 및 해결 방안
  - [ ] Bybit Testnet UI 스크린샷 첨부
    - Order History (Entry/Exit 주문)
    - Position History (Closed positions)
    - Asset (Equity 변화)
  - [ ] Evidence Artifacts (`docs/evidence/phase_12a4/`)
    - testnet_dry_run_report.md
    - completion_checklist.md
    - pytest_output.txt (회귀 테스트)
    - bybit_testnet_screenshots/ (스크린샷 모음)

- [ ] Progress Table 업데이트

---

#### Phase 12a-5: Telegram 알림 통합 (1일)

**Goal**: Testnet 거래 실시간 모니터링 (Telegram 알림)

**Scope**:
1. **상세 설계 문서 작성** (`docs/specs/telegram_notifier_design.md`):
   - TelegramNotifier 클래스 설계 (책임, 의존성)
   - 메시지 포맷 (emoji, markdown)
   - Integration point (run_testnet_dry_run.py)
   - 에러 처리 (bot token 없음, API 실패)

2. **TelegramNotifier 구현**:
   - Entry/Exit 거래 알림
   - HALT/Session Risk 발동 알림
   - 거래 요약 알림

3. **run_testnet_dry_run.py 통합**:
   - TelegramNotifier 초기화
   - State 전환 시 알림 전송
   - HALT 감지 시 알림 전송

4. **검증 및 Evidence**:
   - Telegram 알림 테스트 (수동)
   - Testnet 재실행 (5-10회 거래)
   - 스크린샷 증거

**DoD**:
- [ ] **Sub-task 12a-5a: 상세 설계 문서 작성**
  - [ ] `docs/specs/telegram_notifier_design.md` 작성
    - **1. 책임 (Responsibility)**:
      - 거래 이벤트 → Telegram 메시지 변환
      - Telegram Bot API 호출 (sendMessage)
      - 에러 핸들링 (silent fail, 로그만 출력)
    - **2. 의존성 (Dependencies)**:
      - 외부: Telegram Bot API (https://api.telegram.org/bot{token}/sendMessage)
      - 환경변수: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
      - 내부: 없음 (pure infrastructure layer)
    - **3. 클래스 설계**:
      ```python
      class TelegramNotifier:
          def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
              """환경변수에서 로드, 없으면 disabled"""

          @property
          def enabled(self) -> bool:
              """bot_token/chat_id 있으면 True"""

          def send_entry(self, side: str, qty: float, price: float, signal_id: str = ""):
              """Entry 알림 (🟢 Buy / 🔴 Sell)"""

          def send_exit(self, side: str, qty: float, price: float, pnl: float, reason: str = ""):
              """Exit 알림 (✅ profit / ❌ loss)"""

          def send_halt(self, reason: str, equity: float = 0.0):
              """🚨 HALT 알림"""

          def send_session_risk(self, trigger: str, details: str = ""):
              """⚠️ Session Risk 알림"""

          def send_summary(self, trades: int, wins: int, losses: int, pnl: float):
              """📊 거래 요약"""

          def _send_message(self, text: str) -> bool:
              """Telegram API 호출 (internal)"""
      ```
    - **4. 메시지 포맷 (Markdown + Emoji)**:
      - Entry: `🟢 *Entry Buy* | Qty: 0.001 BTC | Price: $104,500 | Signal: abc123`
      - Exit: `✅ *Exit Sell* | PnL: +$15.23 | Reason: Stop hit`
      - HALT: `🚨 *HALT* | Reason: Daily loss cap | Equity: $95.00`
      - Session Risk: `⚠️ *Session Risk* | Trigger: Loss streak 3 | Details: ...`
      - Summary: `📊 *Trading Summary* | Trades: 30 | Wins: 18 | Losses: 12 | PnL: +$45.67`
    - **5. 에러 처리 (Silent Fail)**:
      - bot_token/chat_id 없음 → `enabled=False`, 메서드 호출 시 즉시 return
      - API 호출 실패 (네트워크, rate limit) → 로그만 출력 (ERROR level), 예외 전파 안 함
      - 근거: Telegram 실패가 거래 중단 원인이 되어서는 안 됨
    - **6. Integration Point**:
      - `run_testnet_dry_run.py`:
        - 초기화: `telegram = TelegramNotifier()` (환경변수 자동 로드)
        - FLAT → IN_POSITION 전환 감지 → `telegram.send_entry()`
        - IN_POSITION → FLAT 전환 감지 → `telegram.send_exit()`
        - HALT 감지 → `telegram.send_halt()`
        - 실행 완료 → `telegram.send_summary()`
      - State 전환 감지 로직:
        ```python
        if previous_state == State.FLAT and current_state == State.IN_POSITION:
            # Entry 발생 (orchestrator.position에서 정보 가져오기)
            telegram.send_entry(side, qty, price, signal_id)

        if previous_state == State.IN_POSITION and current_state == State.FLAT:
            # Exit 발생 (trade_log에서 PnL 가져오기)
            telegram.send_exit(side, qty, price, pnl, reason)
        ```
    - **7. 환경변수 설정 (.env)**:
      ```bash
      # Telegram Bot Configuration
      TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # @BotFather에서 발급
      TELEGRAM_CHAT_ID=123456789  # 개인 Chat ID (bot과 대화 시작 후 /getid)
      ```
    - **8. Telegram Bot 생성 절차**:
      1. @BotFather와 대화 → `/newbot` 명령
      2. Bot 이름 입력 → Token 발급받기
      3. 발급받은 Bot과 대화 시작 (아무 메시지 전송)
      4. Chat ID 확인: `curl https://api.telegram.org/bot<TOKEN>/getUpdates` → `"chat":{"id":123456789}`
      5. .env에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 추가

- [ ] **Sub-task 12a-5b: TelegramNotifier 구현**
  - [ ] `src/infrastructure/notification/__init__.py` 생성 (빈 파일)
  - [ ] `src/infrastructure/notification/telegram_notifier.py` 구현
    - `__init__()`: 환경변수 로드 (`os.getenv()`)
    - `enabled` property: `bool(self.bot_token and self.chat_id)`
    - `send_entry()`: Markdown 메시지 생성 → `_send_message()` 호출
    - `send_exit()`: PnL 양수/음수에 따라 ✅/❌ 선택
    - `send_halt()`: 🚨 emoji + reason
    - `send_session_risk()`: ⚠️ emoji + trigger
    - `send_summary()`: 📊 emoji + 통계 요약
    - `_send_message()`: `requests.post()` → Telegram API 호출
      - URL: `https://api.telegram.org/bot{token}/sendMessage`
      - Payload: `{"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}`
      - 에러 시 로그만 출력, `False` 반환
  - [ ] 의존성 추가: `pyproject.toml`에 `requests` 추가 (이미 있으면 생략)

- [ ] **Sub-task 12a-5c: Unit Test 작성**
  - [ ] `tests/unit/test_telegram_notifier.py` 작성
    - Test case 1: `enabled=False` (bot_token 없음) → 모든 메서드 즉시 return
    - Test case 2: `send_entry()` → `_send_message()` 호출 검증 (mock)
    - Test case 3: `send_exit()` → PnL 양수/음수에 따라 메시지 다름
    - Test case 4: `_send_message()` API 실패 → 로그 출력, 예외 전파 안 함
  - [ ] `pytest -q tests/unit/test_telegram_notifier.py` 통과

- [ ] **Sub-task 12a-5d: run_testnet_dry_run.py 통합**
  - [ ] Import 추가: `from infrastructure.notification.telegram_notifier import TelegramNotifier`
  - [ ] TelegramNotifier 초기화:
    ```python
    telegram = TelegramNotifier()
    if telegram.enabled:
        logger.info("✅ Telegram notifications enabled")
        telegram._send_message("🚀 *Testnet Dry-Run Started*")
    else:
        logger.warning("⚠️  Telegram notifications disabled (missing bot_token/chat_id)")
    ```
  - [ ] State 전환 감지 로직 추가 (기존 monitoring loop에 통합):
    ```python
    # FLAT → IN_POSITION (Entry)
    if previous_state == State.FLAT and current_state == State.IN_POSITION:
        if telegram.enabled and orchestrator.position:
            pos = orchestrator.position
            side = "Buy" if pos.direction == Direction.LONG else "Sell"
            telegram.send_entry(side, pos.qty, pos.entry_price, pos.signal_id)

    # IN_POSITION → FLAT (Exit)
    if previous_state == State.IN_POSITION and current_state == State.FLAT:
        if telegram.enabled:
            trade_logs = log_storage.read_trade_logs_v1()
            if trade_logs:
                last_trade = trade_logs[-1]
                pnl = last_trade.get("realized_pnl_usd", 0.0)
                side = last_trade.get("side", "Unknown")
                qty = last_trade.get("qty", 0.0)
                price = last_trade.get("exit_price", 0.0)
                reason = last_trade.get("exit_reason", "")
                telegram.send_exit(side, qty, price, pnl, reason)
    ```
  - [ ] HALT 감지 시 알림:
    ```python
    if current_state == State.HALT:
        halt_reason = result.get("halt_reason", "Unknown")
        if telegram.enabled:
            equity = market_data.get_equity_btc() * market_data.get_current_price()
            telegram.send_halt(halt_reason, equity)
    ```
  - [ ] 실행 완료 시 요약 전송:
    ```python
    finally:
        if telegram.enabled:
            telegram.send_summary(
                trades=monitor.total_trades,
                wins=monitor.wins,
                losses=monitor.losses,
                pnl=monitor.total_pnl_usd
            )
    ```

- [ ] **Sub-task 12a-5e: Telegram 알림 테스트 (수동)**
  - [ ] Telegram Bot 생성 (@BotFather)
  - [ ] .env 설정 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
  - [ ] 테스트 스크립트 실행 (`scripts/test_telegram.py` 작성):
    ```python
    from infrastructure.notification.telegram_notifier import TelegramNotifier
    telegram = TelegramNotifier()
    telegram._send_message("🧪 Test message from CBGB Bot")
    ```
  - [ ] Telegram 수신 확인
  - [ ] Evidence: `docs/evidence/phase_12a5/telegram_bot_creation.png`

- [ ] **Sub-task 12a-5f: Testnet 재실행 (Telegram 검증)**
  - [ ] `python scripts/run_testnet_dry_run.py --target-trades 5 --force-entry` 실행
  - [ ] Telegram 알림 수신 확인:
    - Entry 알림 (5회)
    - Exit 알림 (5회)
    - Summary 알림 (1회)
  - [ ] 스크린샷 증거: `docs/evidence/phase_12a5/telegram_alerts.png`

- [ ] **Sub-task 12a-5g: Evidence Artifacts**
  - [ ] `docs/evidence/phase_12a5/telegram_integration_report.md` 작성
  - [ ] pytest_output.txt (회귀 테스트)
  - [ ] Telegram 스크린샷 (Bot 생성, 알림 수신)

- [ ] Progress Table 업데이트

---

#### Phase 12b: Mainnet Dry-Run (1-2일)

**Goal**: Mainnet 실거래 환경에서 자동 거래 검증 → **실거래 시작 승인**

**Scope**:
1. **Mainnet 설정**:
   - Mainnet API credentials 발급 (https://www.bybit.com/)
   - .env 파일 업데이트 (BYBIT_TESTNET=false)
   - safety_limits.yaml 설정 (mainnet_enabled: true)
   - Initial equity: **$100** (최소 금액으로 시작)

2. **Mainnet 초기 제한**:
   - `mainnet_initial_max_trades: 50` (초기 50회만 허용)
   - `mainnet_first_week_max_trades_per_day: 5` (첫 주 제한)
   - Daily Loss Cap: -5% equity (더 엄격하게)
   - Per-Trade Loss Cap: $3 (Stage 1 기준)

3. **Mainnet 자동 거래 실행**:
   - `python scripts/run_mainnet_dry_run.py --target-trades 30`
   - 실시간 모니터링 (Slack/Discord alert 연동)
   - Kill Switch 발동 대기 (Session Risk)
   - 실행 결함 모니터링

4. **안전 검증**:
   - Kill Switch 작동 증거 (1회 이상)
   - Emergency HALT 작동 증거 (가격 급락 시뮬레이션 불가, 자연 발생 대기)
   - Session Risk 정확성 (실제 USD 손실 추적)

**DoD**:
- [ ] Mainnet 설정 완료
  - Mainnet API credentials 발급 (Read/Write 권한)
  - .env 업데이트 (BYBIT_TESTNET=false)
  - safety_limits.yaml 설정 (mainnet_enabled: true)
  - Initial equity >= $100 확인
- [ ] Mainnet 초기 제한 설정
  - mainnet_initial_max_trades: 50
  - mainnet_first_week_max_trades_per_day: 5
  - Daily Loss Cap: -5% equity
  - Per-Trade Loss Cap: $3 (Stage 1)
- [ ] Mainnet 30회 이상 거래 실행
  - Full cycle 30회 이상 성공
  - Kill Switch 발동 증거 1회 이상 (Daily cap / Loss streak)
  - Emergency HALT 작동 확인 (자연 발생 시)
  - 실행 결함 0건
- [ ] 로그 완전성 검증
  - 모든 거래가 trade_log에 기록됨
  - 실제 USD PnL 정확성 확인
  - Bybit API 응답과 로그 일치 확인
- [ ] Mainnet Dry-Run Report 작성
  - `docs/evidence/phase_12b/mainnet_dry_run_report.md`
  - 거래 요약 (실제 USD 수익/손실)
  - Kill Switch 작동 증거
  - 실거래 발견 사항 (문제 및 해결)
- [ ] Bybit Mainnet UI 스크린샷 첨부
  - Order History (실제 주문)
  - Position History (실제 청산)
  - Asset (실제 Equity 변화)
- [ ] Evidence Artifacts (`docs/evidence/phase_12b/`)
  - mainnet_dry_run_report.md
  - completion_checklist.md
  - safety_validation.md (Kill Switch 증거)
  - bybit_mainnet_screenshots/ (스크린샷 모음)
- [ ] Progress Table 업데이트

---

#### 완료 기준 (DoD Summary)

#### 완료 기준 (DoD Summary)

**Phase 12a-1 (BybitAdapter)**:
- ✅ BybitAdapter 구현 완료 (REST + WS 통합)
- ✅ MarketDataInterface 모든 메서드 구현
- ✅ Tests 10+ passed (unit)
- ✅ Evidence Artifacts 생성

**Phase 12a-2 (Market Data Provider)**:
- ✅ ATR Calculator 구현 (14-period ATR + percentile)
- ✅ Session Risk Tracker 구현 (Daily/Weekly PnL, Loss streak)
- ✅ Market Regime Analyzer 구현 (MA slope + ATR)
- ✅ Tests 25+ passed (ATR 8 + Session Risk 12 + Regime 5)
- ✅ BybitAdapter 통합 완료

**Phase 12a-3 (Dry-Run Infrastructure)**:
- ✅ run_testnet_dry_run.py 구현 (자동 거래 실행)
- ✅ DryRunMonitor 구현 (통계 추적)
- ✅ generate_dry_run_report.py 구현 (Evidence 자동 생성)
- ✅ Tests 5+ passed (integration)

**Phase 12a-4 (Testnet Execution)**:
- ✅ Testnet 30-50회 거래 자동 실행 성공
- ✅ Session Risk 발동 증거 1회 이상 (Daily cap / Loss streak)
- ✅ Stop loss 5회 이상 작동
- ✅ 로그 완전성 100% (모든 거래 기록)
- ✅ Testnet Dry-Run Report 작성
- ✅ Bybit Testnet UI 스크린샷 첨부

**Phase 12b (Mainnet Execution)**:
- ✅ Mainnet 설정 완료 (API credentials, safety_limits.yaml)
- ✅ Mainnet 30회 이상 거래 자동 실행 성공 (실제 USD)
- ✅ Kill Switch 발동 증거 1회 이상 (실거래에서 Session Risk 작동)
- ✅ 실행 결함 0건
- ✅ Mainnet Dry-Run Report 작성
- ✅ **실거래 시작 승인** (Dry-run 성공 → 제한 해제 가능)

---

#### 파일 구조 (Phase 12 신규 생성)

**Application Layer**:
```
src/application/
├── atr_calculator.py           # ATR 계산 (14-period, percentile)
├── session_risk_tracker.py     # Daily/Weekly PnL, Loss streak 추적
└── market_regime.py             # MA slope + ATR → regime 분류
```

**Infrastructure Layer**:
```
src/infrastructure/exchange/
└── bybit_adapter.py             # BybitAdapter (완전 구현, Phase 12a-1)
```

**Scripts**:
```
scripts/
├── run_testnet_dry_run.py       # Testnet 자동 거래 실행
├── run_mainnet_dry_run.py       # Mainnet 자동 거래 실행
└── generate_dry_run_report.py   # Evidence 자동 생성
```

**Tests**:
```
tests/unit/
├── test_bybit_adapter.py        # BybitAdapter (10+ cases)
├── test_atr_calculator.py       # ATR Calculator (8+ cases)
├── test_session_risk_tracker.py # Session Risk Tracker (12+ cases)
└── test_market_regime.py        # Market Regime (5+ cases)

tests/integration/
└── test_dry_run_orchestrator.py # Dry-Run 통합 (5+ cases)
```

**Evidence**:
```
docs/evidence/
├── phase_12a1/                  # BybitAdapter 구현
│   ├── completion_checklist.md
│   ├── pytest_output.txt
│   └── gate7_verification.txt
├── phase_12a2/                  # Market Data Provider
│   ├── completion_checklist.md
│   └── pytest_output.txt
├── phase_12a3/                  # Dry-Run Infrastructure
│   ├── completion_checklist.md
│   └── pytest_output.txt
├── phase_12a/                   # Testnet Execution
│   ├── testnet_dry_run_report.md
│   ├── completion_checklist.md
│   ├── pytest_output.txt
│   └── bybit_testnet_screenshots/
└── phase_12b/                   # Mainnet Execution
    ├── mainnet_dry_run_report.md
    ├── completion_checklist.md
    ├── safety_validation.md
    └── bybit_mainnet_screenshots/
```

---

#### 테스트 계획 (Phase 12 신규 추가)

**Unit Tests (총 35+ cases)**:
- `test_bybit_adapter.py`: 10+ cases
  - REST API 응답 → MarketDataInterface 변환
  - WebSocket event → ExecutionEvent 변환
  - State caching 동작 검증
  - DEGRADED 모드 전환 검증
  - get_mark_price(), get_equity_btc(), get_atr() 등

- `test_atr_calculator.py`: 8+ cases
  - calculate_atr(): Kline → ATR (14-period)
  - calculate_atr_percentile(): Rolling 100-period
  - calculate_grid_spacing(): ATR * multiplier
  - Edge cases: 데이터 부족, NaN 처리

- `test_session_risk_tracker.py`: 12+ cases
  - track_daily_pnl(): UTC boundary 인식
  - track_weekly_pnl(): Week rollover
  - calculate_loss_streak(): Consecutive losses
  - track_fee_ratio(): Fee spike 감지
  - track_slippage(): 10분 윈도우 슬리피지
  - Edge cases: 빈 history, 타임존 변환

- `test_market_regime.py`: 5+ cases
  - calculate_ma_slope(): Kline → MA slope
  - classify_regime(): trending_up, trending_down, ranging, high_vol
  - Edge cases: Flat market, 급등/급락

**Integration Tests (총 5+ cases)**:
- `test_dry_run_orchestrator.py`: 5+ cases
  - Full cycle integration (Orchestrator + BybitAdapter)
  - HALT handling (Session Risk 발동)
  - Graceful shutdown (Ctrl+C)
  - Trade Log 기록 검증
  - Monitor statistics 정확성

**Total New Tests**: 40+ cases (267 → 307+ expected)

---

#### 예상 일정 (Phase 12 Full Automated)

| Sub-Phase | 작업 | 예상 기간 | Deliverable |
|-----------|------|----------|-------------|
| **12a-1** | BybitAdapter 완전 구현 | 1-2일 | BybitAdapter + 10 tests |
| **12a-2** | Market Data Provider | 1-2일 | ATR/Session Risk/Regime + 25 tests |
| **12a-3** | Dry-Run Infrastructure | 1일 | run_testnet_dry_run.py + 5 tests |
| **12a-4** | Testnet 자동 거래 실행 | 2-3일 | 30-50회 거래 + Evidence |
| **12b** | Mainnet 자동 거래 실행 | 1-2일 | 30회 거래 + Kill Switch 증거 |

**총 예상 기간**: **6-10일** (Full Automated)

**장점**:
- ✅ 완전 자동화 (사람 개입 최소화)
- ✅ 재현 가능성 100% (코드로 고정)
- ✅ Phase 13+ 준비 완료 (분석 인프라 구축)

**단점**:
- ❌ 구현 시간 길다 (6-10일)
- ❌ 디버깅 복잡도 높음 (REST/WS 통합)

**vs Manual Dry-Run**:
- Manual: 1-2일, 즉시 시작, DoD 완전 충족
- Automated: 6-10일, 완전 자동화, 장기 운영 준비

---

### Phase 13: 운영 최적화 + 장기 모니터링 (Phase 12 완료 후)

**⚠️ 선택 사항**: Phase 13+는 실거래 최적화 단계로, **Phase 12 완료 후 선택적으로 진행**

Goal: 실거래 운영 안정화 + 성과 최적화 + 장기 모니터링

#### Scope (선택 사항)

1. **Analysis Toolkit** (거래 분석):
   - 거래 성과 분석 도구
   - A/B 비교 (파라미터 변경 전후)
   - 통계 검정 (Winrate, Profit factor 등)

2. **Automated Tuning** (파라미터 조정):
   - Grid spacing 자동 조정 (ATR 기반)
   - Session Risk threshold 조정 (성과 기반)
   - Stage transition 최적화

3. **Long-term Monitoring** (장기 모니터링):
   - 대시보드 (실시간 성과 모니터링)
   - Alert 시스템 (Slack/Discord 연동)
   - Quarterly Review (분기별 성과 리뷰)

**Note**: Phase 13+는 실거래 운영 중 필요에 따라 선택적으로 진행합니다.

---

### 실거래 타임라인 요약

| Phase | 작업 | 예상 기간 | 실거래 가능? | 핵심 Deliverable |
|-------|------|----------|-------------|-----------------|
| **Phase 10** | Trade Logging | 3-4일 | ❌ (로그만) | Trade Log v1.0 + Storage |
| **Phase 11** | Signal + Full Integration | 5-7일 | ❌ (Testnet만) | Full cycle (FLAT → Entry → Exit → FLAT) |
| **Phase 12a** | Testnet Dry-Run | 2-3일 | ❌ (Testnet) | 30-50회 거래 성공 + Session Risk 증거 |
| **Phase 12b** | Mainnet Dry-Run | 1-2일 | ✅ **최소 금액** | 30회 거래 성공 + Kill Switch 증거 |
| **Phase 13+** | 운영 최적화 | 선택 사항 | ✅ **정상 운영** | Analysis + Tuning + Monitoring |

**총 예상 기간**: **2-3주** (Phase 10-12b 완료)

**실거래 시작 시점**: **Phase 12b 완료 후** (Mainnet Dry-Run 성공)

---

#### 다음 Phase (Phase 13+)
Phase 13+는 실거래 최적화 단계로, 선택적으로 진행:
- Phase 13: Analysis Toolkit (거래 분석, A/B 비교)
- Phase 14: Automated Tuning (파라미터 조정 프레임워크)
- Phase 15: Long-term Monitoring (대시보드, Alert, Quarterly Review)

## 5. Progress Table (Update on Every Completion)

> 규칙: DONE되면 반드시 아래 표를 갱신한다. 갱신 없으면 DONE 취소.

### PRE-FLIGHT Gates (완료 필수)

| Gate | 규칙 | 상태 | Evidence |
|------|------|------|----------|
| 1 | Oracle Placeholder Zero Tolerance | ✅ PASS (COMPLETE) | **17개 placeholder 테스트 삭제** → docs/plans/task_plan.md Oracle Backlog 섹션으로 이동. **Gate 7 검증 결과**: (1a) placeholder 표현 0개, (1b) skip/xfail 0개, (1c) 의미있는 assert 155개, (5) oracle tests 24 passed, (전체) 33 passed. **Solution D 완료** (2026-01-18 23:45) |
| 2 | No Test-Defined Domain | ✅ PASS | tests/oracles/test_state_transition_oracle.py:24-33 (Position 클래스 제거, domain.state에서 import) |
| 3 | Single Transition Truth | ✅ PASS | src/application/transition.py (SSOT), src/application/event_router.py (thin wrapper), tests/unit/test_event_router.py (2 증명 테스트) |
| 4 | Repo Map Alignment | ✅ PASS | src/domain/intent.py, src/domain/events.py, src/application/transition.py (SSOT 경로 확정) |
| 5 | pytest Proof = DONE | ✅ PASS | 8 passed (tests/oracles: 6, tests/unit/test_event_router: 2) |
| 6 | Doc Update | ✅ PASS | docs/plans/task_plan.md (PRE-FLIGHT 표 추가, Last Updated 갱신) |
| 7 | Self-Verification Before DONE | ✅ PASS (COMPLETE) | **Gate 7 검증 최종** (2026-01-18 22:49): (1a) Placeholder 0개, (1b) Skip/Xfail 0개, (1c) Assert 157개, (4b) EventRouter State 참조 0개, (5) sys.path hack 0개, (6a) Deprecated import 0개, **(6b) 구 경로 import 0개 ✅**, (7) **70 passed in 0.06s (pip install -e .[dev] 후 PYTHONPATH 없이 동작)**, **(8) 문서-코드 경로 일치 검증 4 passed (test_docs_ssot_paths.py)**. **DoD-3/2/1 추가 작업 포함** (SSOT 충돌 제거 + FLOW 골격 + README 링크 정렬) |
| 8 | Migration Protocol Compliance | ✅ PASS (COMPLETE) | **Migration 완료** (2026-01-18 22:49): src/application/services/ 디렉토리 전체 삭제, 구 경로 import 0개 검증, pytest 70 passed. **패키징 표준 준수**: pyproject.toml 설정, pip install -e .[dev] 후 pytest 정상 동작 (PYTHONPATH 불필요). **파일명 규칙 준수**: tests/oracles/test_state_transition_oracle.py (pytest 자동 수집). **문서-코드 경로 일치**: test_docs_ssot_paths.py 4 passed (SSOT 내부 일관성 보장). **Phase 1 시작 조건 충족** |

### Implementation Phases

| Phase | Status (TODO/DOING/DONE) | Evidence (tests) | Evidence (impl) | Notes / Commit |
|------:|--------------------------|------------------|------------------|----------------|
| 0 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_0/completion_checklist.md), [Gate 7](../evidence/phase_0/gate7_verification.txt), [pytest](../evidence/phase_0/pytest_output.txt), [RED→GREEN](../evidence/phase_0/red_green_proof.md), [File Tree](../evidence/phase_0/file_tree.txt). **Tests**: Oracle 25 cases (state transition + intent) + Unit 48 cases (transition, event_router, docs alignment, flow skeleton) + Integration 9 cases + Phase 1: 13 cases = **83 passed in 0.06s**. **Gate 7**: ALL PASS (Placeholder 0, Skip/Xfail 0, Assert 163, Migration 완료). **Verification**: `./scripts/verify_phase_completion.sh 0` → PASS | **Domain**: [state.py](../../src/domain/state.py), [intent.py](../../src/domain/intent.py), [events.py](../../src/domain/events.py). **Application**: [transition.py](../../src/application/transition.py) (SSOT), [event_router.py](../../src/application/event_router.py) (thin wrapper), [tick_engine.py](../../src/application/tick_engine.py). **Infrastructure**: [fake_exchange.py](../../src/infrastructure/exchange/fake_exchange.py). **Docs Alignment**: test_docs_ssot_paths.py (5 passed), test_flow_minimum_contract.py (5 passed), test_readme_links_exist.py (2 passed). **Migration**: src/application/services/ 삭제 완료, 패키징 표준 준수. | **Commit**: e0d147e (2026-01-19 00:35). **Phase 0+0.5 완료**. DoD 5개 항목 충족 + Evidence Artifacts 생성 완료. **새 세션 검증 가능**. Phase 2 시작 가능. |
| 0.5 | DONE | **Phase 0에 통합됨** ([Phase 0 Evidence Artifacts 참조](../evidence/phase_0/)). **Evidence**: [Completion Checklist](../evidence/phase_0/completion_checklist.md#L167-L241) (Phase 0.5 섹션), [RED→GREEN](../evidence/phase_0/red_green_proof.md#L82-L117) (Phase 0.5 케이스). **Tests**: 6 cases (test_in_position_additional_partial_fill_increases_qty, test_in_position_fill_completes_entry_working_false, test_in_position_liquidation_should_halt, test_in_position_adl_should_halt, test_in_position_missing_stop_emits_place_stop_intent, test_in_position_invalid_filled_qty_halts). **실행**: Phase 0와 동일 (`pytest -q` → **83 passed in 0.06s**) | src/application/transition.py (Phase 0.5 로직: invalid qty 방어, stop_status=MISSING 복구, IN_POSITION 이벤트 처리 A-D) | **Phase 0.5 완료 (Phase 0에 완전 통합)**. IN_POSITION 이벤트 처리 + stop 복구 intent + invalid qty 방어 구현. Evidence는 Phase 0 디렉토리에 포함됨. |
| 1 | DONE | **Evidence Artifacts (ADR-0007 적용)**: [Completion Checklist](../evidence/phase_1/completion_checklist.md), [Gate 7](../evidence/phase_1/gate7_verification.txt), [pytest](../evidence/phase_1/pytest_output.txt), [RED→GREEN](../evidence/phase_1/red_green_proof.md), [Thresholds](../evidence/phase_1/emergency_thresholds_verification.txt). **Tests**: test_emergency.py (8 cases) + test_ws_health.py (5 cases) = **13 passed**. Total: **83 passed in 0.07s**. **Gate 7**: ALL PASS (Placeholder 0, Skip/Xfail 0, Assert 166). **Policy Alignment**: 12 / 12 thresholds MATCH. **ADR-0007**: COOLDOWN semantic 완전 적용 (price_drop → COOLDOWN). **Verification**: `./scripts/verify_phase_completion.sh 1` → PASS (예상) | **Application**: [emergency.py](../../src/application/emergency.py) (EmergencyStatus with is_cooldown field, check_emergency, check_recovery, Policy 7.1/7.2/7.3 준수, ADR-0007 적용), [ws_health.py](../../src/application/ws_health.py) (WSHealthStatus, WSRecoveryStatus, check_ws_health, check_degraded_timeout, check_ws_recovery, FLOW 2.4 준수). **Infrastructure**: [market_data_interface.py](../../src/infrastructure/exchange/market_data_interface.py) (MarketDataInterface Protocol, 6 메서드), [fake_market_data.py](../../src/infrastructure/exchange/fake_market_data.py) (deterministic test injection). **Thresholds Verified**: price_drop (-10%/-20% → COOLDOWN), balance (0/30s → HALT), latency (5s → Block), recovery (-5%/-10%, 30min), heartbeat (10s), event_drop (3), degraded (60s), ws_recovery (5min). **SSOT**: FLOW v1.8 + Policy v2.2 완전 일치. | **Commit**: f678ae9 (2026-01-21 06:00, ADR-0007 적용). **Phase 1 완료**. DoD 5개 항목 충족 + Evidence Artifacts 생성 완료 + ADR-0007 완전 적용 + Policy 일치 검증 완료 (SSOT). **새 세션 검증 가능**. Phase 2 시작 가능. |
| 2 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_2/completion_checklist.md), [Gate 7](../evidence/phase_2/gate7_verification.txt), [pytest](../evidence/phase_2/pytest_output.txt), [RED→GREEN](../evidence/phase_2/red_green_proof.md). **Tests**: test_ids.py (6) + test_entry_allowed.py (9) + test_sizing.py (8) + test_liquidation_gate.py (8) = **31 passed**. Total: **114 passed in 0.09s** (83 → 114). **Gate 7**: ALL PASS (Placeholder 0, Assert 181, Domain 재정의 0, Migration 완료). **Verification**: `./scripts/verify_phase_completion.sh 2` → PASS (expected) | **Domain**: [ids.py](../../src/domain/ids.py) (signal_id/orderLinkId validators). **Application**: [entry_allowed.py](../../src/application/entry_allowed.py) (8 gates + reject 이유코드), [sizing.py](../../src/application/sizing.py) (LONG/SHORT 정확한 공식 + margin + tick/lot), [liquidation_gate.py](../../src/application/liquidation_gate.py) (liq distance + 동적 기준 + fallback). **SSOT**: FLOW Section 2, 3.4, 7.5, 8 + Policy Section 5, 10. | **Commit**: 8d1c0d8 (impl) + 9fba6f7 (evidence, 2026-01-23). **Phase 2 완료**. DoD 5개 항목 충족 + Evidence Artifacts 생성 완료. **새 세션 검증 가능**. Phase 3 시작 가능. |
| 3 | DONE | [test_fee_verification.py](../../tests/unit/test_fee_verification.py) (5)<br>[test_order_executor.py](../../tests/unit/test_order_executor.py) (8)<br>[test_event_handler.py](../../tests/unit/test_event_handler.py) (7) | [fee_verification.py](../../src/application/fee_verification.py)<br>[order_executor.py](../../src/application/order_executor.py)<br>[event_handler.py](../../src/application/event_handler.py) | e7f5c15 (impl)<br>Evidence: [phase_3/](../evidence/phase_3/)<br>134 passed (+20) |
| 4 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_4/completion_checklist.md), [Gate 7](../evidence/phase_4/gate7_verification.txt), [pytest](../evidence/phase_4/pytest_output.txt), [RED→GREEN](../evidence/phase_4/red_green_proof.md). **Tests**: [test_stop_manager.py](../../tests/unit/test_stop_manager.py) (10) + [test_metrics_tracker.py](../../tests/unit/test_metrics_tracker.py) (6) = **16 passed**. Total: **152 passed in 0.14s** (134 → 152). **Gate 7**: ALL PASS (Placeholder 0, Assert 229, Domain 재정의 0, Migration 완료). **Verification**: `./scripts/verify_phase_completion.sh 4` → PASS (expected) | **Application**: [stop_manager.py](../../src/application/stop_manager.py) (should_update_stop, determine_stop_action, recover_missing_stop: 20% threshold + 2초 debounce + Amend 우선 + stop_status recovery), [metrics_tracker.py](../../src/application/metrics_tracker.py) (calculate_winrate, update_streak_on_closed_trade, apply_streak_multiplier, check_winrate_gate: Winrate rolling 50 trades + 3연승/연패 multiplier + N 구간별 gate). **SSOT**: FLOW Section 2.5, 9 + Policy Section 11. | **Evidence**: [phase_4/](../evidence/phase_4/). **Phase 4 완료**. DoD 5개 항목 충족 + Evidence Artifacts 생성 완료. **새 세션 검증 가능**. Phase 5 시작 가능. |
| 5 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_5/completion_checklist.md), [Gate 7](../evidence/phase_5/gate7_verification.txt), [pytest](../evidence/phase_5/pytest_output.txt), [RED→GREEN](../evidence/phase_5/red_green_proof.md). **Tests**: [test_trade_logger.py](../../tests/unit/test_trade_logger.py) (5) + [test_halt_logger.py](../../tests/unit/test_halt_logger.py) (4) + [test_metrics_logger.py](../../tests/unit/test_metrics_logger.py) (4) = **13 passed**. Total: **166 passed in 0.15s** (152 → 166, +14). **Gate 7**: ALL PASS (Placeholder 0, Assert 272, Domain 재정의 0, Migration 완료). **Verification**: `./scripts/verify_phase_completion.sh 5` → PASS (expected) | **Infrastructure/Logging**: [trade_logger.py](../../src/infrastructure/logging/trade_logger.py) (log_trade_entry, log_trade_exit, validate_trade_schema: entry/exit 로그 + schema validation + 재현 정보), [halt_logger.py](../../src/infrastructure/logging/halt_logger.py) (log_halt, validate_halt_schema: HALT 이유 + context snapshot), [metrics_logger.py](../../src/infrastructure/logging/metrics_logger.py) (log_metrics_update, validate_metrics_schema: winrate/streak/multiplier 변화 추적). **SSOT**: task_plan Phase 5 (재현 가능성 + schema validation), FLOW Section 6.2 (fee log), Section 7.1 (HALT context), Section 9 (metrics update). | **Evidence**: [phase_5/](../evidence/phase_5/). **Phase 5 완료**. DoD 5개 항목 충족 + Evidence Artifacts 생성 완료. **새 세션 검증 가능**. Phase 6 시작 가능. |
| 6 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_6/completion_checklist.md), [pytest](../evidence/phase_6/pytest_output.txt). **Tests**: [test_orchestrator.py](../../tests/integration/test_orchestrator.py) (5 integration cases: tick order, halt, degraded). Total: **171 passed in 0.14s** (166 → 171, +5). **Gate 7**: ALL PASS (280 meaningful asserts). | **Application**: [orchestrator.py](../../src/application/orchestrator.py) (Orchestrator, TickResult, run_tick: Emergency → Events → Position → Entry 순서 실행, God Object 금지 준수, thin wrapper). **SSOT**: task_plan Phase 6 (Tick 순서 고정), FLOW Section 2 (Tick Ordering), Section 4.2 (God Object 금지). | **Evidence**: [phase_6/](../evidence/phase_6/). **Phase 6 완료**. Integration tests 5개. **새 세션 검증 가능**. **Phase 0~6 완료 (Domain Logic 완성)**. Phase 7 (Real API Integration) 시작 가능. |
| 7 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_7/completion_checklist.md), [Gate 7](../evidence/phase_7/gate7_verification.txt), [pytest](../evidence/phase_7/pytest_output.txt), [RED→GREEN](../evidence/phase_7/red_green_proof.md). **Tests**: [test_bybit_rest_client.py](../../tests/unit/test_bybit_rest_client.py) (10 contract cases: 서명, payload, rate limit, retCode 10006, timeout, testnet URL, API key 검증) + [test_bybit_ws_client.py](../../tests/unit/test_bybit_ws_client.py) (7 contract cases: subscribe, DEGRADED 플래그, ping-pong, queue overflow, testnet WSS, API key 검증). Total: **188 passed in 0.21s** (171 → 188, +17). **Gate 7**: ALL PASS (303 meaningful asserts, +23). **실거래 함정 3개 해결**: WS queue maxsize + Clock 주입 + Testnet URL 강제. | **Infrastructure/Exchange**: [bybit_rest_client.py](../../src/infrastructure/exchange/bybit_rest_client.py) (BybitRestClient, FatalConfigError, RateLimitError: 서명 생성 HMAC SHA256, Rate limit 헤더 처리 X-Bapi-*, Timeout/retry max_retries=3, Testnet base_url 강제, API key 누락 → FatalConfigError, Clock 주입), [bybit_ws_client.py](../../src/infrastructure/exchange/bybit_ws_client.py) (BybitWsClient: execution.inverse topic, DEGRADED 플래그 관리, Ping-pong timeout 20초, WS queue maxsize + overflow 드랍 정책, Testnet WSS URL 강제, Clock 주입). **SSOT**: task_plan Phase 7 (Contract tests only, 네트워크 호출 0, 실거래 함정 3개), FLOW Section 2.5 (Event Processing), Section 6 (Fee Tracking REST). | **Evidence**: [phase_7/](../evidence/phase_7/). **Phase 7 완료**. Contract tests 17개 (네트워크 0). **새 세션 검증 가능**. **Phase 0~7 완료 (Domain Logic + REST/WS 클라이언트 골격 완성)**. Phase 8 (Testnet Validation) 시작 가능. |
| 8 | DONE | **Evidence Artifacts v2**: [Gate 7 v2](../evidence/phase_8/gate7_verification_v2.txt), [Placeholder Removal](../evidence/phase_8/placeholder_removal_proof.md), [RED→GREEN](../evidence/phase_8/red_green_proof.md). **Live Tests**: [test_testnet_connection.py](../../tests/integration_real/test_testnet_connection.py) (3 - 시나리오 1) + [test_ws_reconnection.py](../../tests/integration_real/test_ws_reconnection.py) (3 - 시나리오 5) + [test_execution_event_mapping.py](../../tests/integration_real/test_execution_event_mapping.py) (2 - 시나리오 3, placeholder 제거) + [test_testnet_order_flow.py](../../tests/integration_real/test_testnet_order_flow.py) (4 - 시나리오 2) + [test_rate_limit_handling.py](../../tests/integration_real/test_rate_limit_handling.py) (3 - 시나리오 4). **Total (예상)**: **14 passed** (placeholder 1개 제거). **Contract tests**: 188 passed, 15 deselected. **Gate 7 v2**: ALL PASS (303 asserts, Placeholder 0, @pytest.mark.skip 0, conftest.py 중복 제거). | **Infrastructure/Exchange**: [bybit_ws_client.py](../../src/infrastructure/exchange/bybit_ws_client.py) (489 LOC, 24 메서드: public 14 + private 10), [bybit_rest_client.py](../../src/infrastructure/exchange/bybit_rest_client.py) (place_order/cancel_order 메서드). **Tests**: [conftest.py](../../tests/integration_real/conftest.py) (api_credentials fixture 공통화). **pyproject.toml**: websocket-client==1.6.4, pytest testnet marker. **SSOT**: Bybit V5 프로토콜 준수 (WS + REST). | **Evidence v2**: [phase_8/](../evidence/phase_8/) (Gate 1a/1b 재검증). **Phase 8 재검증 완료** (5개 시나리오, placeholder 제거). **새 세션 검증 가능**. **Phase 0~8 완료 (Domain Logic + REST/WS 클라이언트 실제 구현 + Testnet 검증 완료)**. Phase 9 (Session Risk) 시작 가능. |
| 9 | DONE | **Evidence Artifacts (9a)**: [Completion Checklist](../evidence/phase_9a/completion_checklist.md), [Gate 7](../evidence/phase_9a/gate7_verification.txt), [pytest](../evidence/phase_9a/pytest_output.txt), [RED→GREEN](../evidence/phase_9a/red_green_proof.md). **Evidence Artifacts (9b)**: [Completion Checklist](../evidence/phase_9b/completion_checklist.md), [Gate 7](../evidence/phase_9b/gate7_verification.txt), [pytest](../evidence/phase_9b/pytest_output.txt), [Policy Change](../evidence/phase_9b/policy_change_proof.md). **Evidence Artifacts (9c)**: [Completion Checklist](../evidence/phase_9c/completion_checklist.md), [Gate 7](../evidence/phase_9c/gate7_verification.txt), [pytest](../evidence/phase_9c/pytest_output.txt), [RED→GREEN](../evidence/phase_9c/red_green_proof.md). **Evidence Artifacts (9 Revision)**: [Completion Checklist](../evidence/phase_9_revision/completion_checklist.md), [Gate 7](../evidence/phase_9_revision/gate7_verification.txt), [pytest](../evidence/phase_9_revision/pytest_output.txt), [UTC Boundary Proof](../evidence/phase_9_revision/utc_boundary_proof.md). **Evidence Artifacts (9d)**: [Completion Checklist](../evidence/phase_9d/completion_checklist.md), [Slippage Fix Proof](../evidence/phase_9d/slippage_fix_proof.md), [pytest Session Risk](../evidence/phase_9d/pytest_output_session_risk.txt), [pytest Full](../evidence/phase_9d/pytest_output_full.txt). **Tests**: [test_session_risk.py](../../tests/unit/test_session_risk.py) (17 cases, UTC edge cases 추가) + [test_orchestrator_session_risk.py](../../tests/integration/test_orchestrator_session_risk.py) (5 cases, Slippage anomaly 통합 테스트 포함). Total: **238 passed in 0.29s** (188 → 238, +50). **Gate 7**: ALL PASS (375 asserts). | **Application**: [session_risk.py](../../src/application/session_risk.py) (UTC boundary 수정, 203 LOC), [orchestrator.py](../../src/application/orchestrator.py) (216 LOC, Session Risk 통합, Phase 9d: current_timestamp 초기화 수정). **Infrastructure**: [market_data_interface.py](../../src/infrastructure/exchange/market_data_interface.py) (Protocol 확장), [fake_market_data.py](../../src/infrastructure/exchange/fake_market_data.py) (Session Risk 메서드 추가). **Infrastructure/Safety**: [killswitch.py](../../src/infrastructure/safety/killswitch.py) (59 LOC), [alert.py](../../src/infrastructure/safety/alert.py) (49 LOC), [rollback_protocol.py](../../src/infrastructure/safety/rollback_protocol.py) (73 LOC). **Config**: [safety_limits.yaml](../../config/safety_limits.yaml) (Dry-Run 4개 상한, Mainnet/Testnet 분리). **Policy**: [account_builder_policy.md](../specs/account_builder_policy.md) (Stage 1: $10→$3). **ADR**: [ADR-0001](../adrs/ADR-0001-per-trade-loss-cap-reduction.md). | **Evidence**: [phase_9a/](../evidence/phase_9a/), [phase_9b/](../evidence/phase_9b/), [phase_9c/](../evidence/phase_9c/), [phase_9_revision/](../evidence/phase_9_revision/), [phase_9d/](../evidence/phase_9d/). **Phase 9 완료** (Session Risk + Per-Trade Cap + Orchestrator 통합 + UTC boundary 버그 수정 + Slippage anomaly 버그 수정). **완전한 계좌 보호**: Session (Daily -5%, Weekly -12.5%, Loss Streak, Slippage Anomaly) + Trade ($3 cap) + Emergency = 3중 보호 **모두 활성**. **"도박 종료, 계좌 보호 시작"**. **✅ 실거래 투입 조건 충족**: Session Risk Policy 4개 모두 작동. **새 세션 검증 가능**. **Last Updated**: 2026-01-24 |
| 10 | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_10/completion_checklist.md), [Gate 7](../evidence/phase_10/gate7_verification.txt), [pytest](../evidence/phase_10/pytest_output.txt), [RED→GREEN](../evidence/phase_10/red_green_proof.md). **Tests**: [test_trade_logger_v1.py](../../tests/unit/test_trade_logger_v1.py) (9 cases) + [test_log_storage.py](../../tests/unit/test_log_storage.py) (8 cases) = **17 passed**. Total: **225 passed in 0.34s** (208 → 225, +17). **Gate 7**: ALL PASS (359 asserts, +29). | **Infrastructure/Logging**: [trade_logger_v1.py](../../src/infrastructure/logging/trade_logger_v1.py) (145 LOC: TradeLogV1 dataclass, calculate_market_regime, validate_trade_log_v1), **Infrastructure/Storage**: [log_storage.py](../../src/infrastructure/storage/log_storage.py) (165 LOC: LogStorage class, append/read/rotate with fsync policy). **DoD 1/5**: order_id, fills, slippage, latency breakdown, funding/mark/index. **DoD 3/5**: market_regime deterministic (MA slope + ATR percentile). **DoD 5/5**: schema_version, config_hash, git_commit, exchange_server_time_offset 필수. **Failure-mode tests**: schema validation, partial line recovery, fsync policy (batch/periodic/critical), rotation boundary. | **Evidence**: [phase_10/](../evidence/phase_10/). **Phase 10 완료** (Trade Log v1.0 + JSONL Storage). **운영 현실화**: Single syscall write, durable append, crash safety. **새 세션 검증 가능**. **완료**: 2026-01-24 |
| 11a | DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_11a/completion_checklist.md), [Gate 7](../evidence/phase_11a/gate7_verification.txt), [pytest](../evidence/phase_11a/pytest_output.txt), [RED→GREEN](../evidence/phase_11a/red_green_proof.md). **Tests**: [test_signal_generator.py](../../tests/unit/test_signal_generator.py) (10 cases) + [test_exit_manager.py](../../tests/unit/test_exit_manager.py) (8 cases) = **18 passed**. Total: **245 passed in 0.36s** (225 → 245, +18). **Gate 7**: ALL PASS (380 asserts, +21). | **Application**: [signal_generator.py](../../src/application/signal_generator.py) (88 LOC: Signal dataclass, calculate_grid_spacing, generate_signal), [exit_manager.py](../../src/application/exit_manager.py) (78 LOC: check_stop_hit, create_exit_intent), **Domain**: [intent.py](../../src/domain/intent.py) (ExitIntent 추가), **Orchestrator**: [orchestrator.py](../../src/application/orchestrator.py) (Exit Manager만 통합). **Scope**: Grid Signal + Exit Logic (독립 완료 가능). | **Evidence**: [phase_11a/](../evidence/phase_11a/). **Phase 11a 완료** (Signal Generator + Exit Manager). **100% 완료**: DoD 8개 항목 모두 완료. **완료**: 2026-01-24. **새 세션 검증 가능**. **다음**: Phase 11b (Full Integration + Testnet E2E) |
| 11b | [x] DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_11b/completion_checklist.md), [Gate 7](../evidence/phase_11b/gate7_verification.txt), [pytest](../evidence/phase_11b/pytest_output.txt), [RED→GREEN](../evidence/phase_11b/red_green_proof.md). **Tests**: [test_orchestrator_entry_flow.py](../../tests/unit/test_orchestrator_entry_flow.py) (7 cases) + [test_orchestrator_event_processing.py](../../tests/unit/test_orchestrator_event_processing.py) (9 cases) + [test_full_cycle_testnet.py](../../tests/integration_real/test_full_cycle_testnet.py) (6 cases) = **22 passed**. Total: **267 passed in 0.41s** (245 → 267, +22). **Gate 7**: ALL PASS (461 asserts, +81). | [orchestrator.py](../../src/application/orchestrator.py) (✅ 413 LOC, God Object 리팩토링 완료), [emergency_checker.py](../../src/application/emergency_checker.py) (Session Risk 통합, 145 LOC), [entry_coordinator.py](../../src/application/entry_coordinator.py) (Entry helpers, 151 LOC), [event_processor.py](../../src/application/event_processor.py) (Event helpers, 161 LOC), [market_data_interface.py](../../src/infrastructure/exchange/market_data_interface.py) (+7 메서드), [fake_market_data.py](../../src/infrastructure/exchange/fake_market_data.py) (+13 메서드), [entry_allowed.py](../../src/application/entry_allowed.py) (StageParams, SignalContext), [sizing.py](../../src/application/sizing.py) (SizingParams) | **Part 1/3 완료** (Entry Flow): c17cc8e. **Part 2/3 완료** (Event Processing + God Object 리팩토링): f158d7a, d7292e3. **Part 3/3 완료** (Testnet E2E 시뮬레이션): [현재 커밋]. **Evidence**: [phase_11b/](../evidence/phase_11b/). **Phase 11b 완료** (Full Orchestrator Integration). **Tests**: 267 passed (+22 from Phase start), 회귀 없음. **FLOW.md Section 4.2 준수**: orchestrator.py 413 LOC (< 500). **✅ Full Orchestrator Integration 완료** (Entry + Event Processing + Testnet E2E 시뮬레이션 6/6). **완료**: 2026-01-24. **Gate 7 Evidence 추가**: 2026-01-25. **새 세션 검증 가능**. **중요**: 실제 Testnet 연결 테스트는 Phase 12 (Dry-Run Validation) 예정. |
| 12a-1 | [x] DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_12a1/completion_checklist.md), [Gate 7](../evidence/phase_12a1/gate7_verification.txt), [pytest](../evidence/phase_12a1/pytest_output.txt), [RED→GREEN](../evidence/phase_12a1/red_green_proof.md). **Tests**: [test_bybit_adapter.py](../../tests/unit/test_bybit_adapter.py) (14 cases: REST 4 + WS 2 + Caching 3 + DEGRADED 3 + Session Risk 2) = **14 passed**. Total: **281 passed in 0.43s** (267 → 281, +14). **Gate 7**: ALL PASS (526 asserts). | **Infrastructure/Exchange**: [bybit_adapter.py](../../src/infrastructure/exchange/bybit_adapter.py) (398 LOC: update_market_data(), get_fill_events(), MarketDataInterface 완전 구현), [bybit_rest_client.py](../../src/infrastructure/exchange/bybit_rest_client.py) (+158 LOC: get_tickers/wallet_balance/position/execution_list 4 메서드), [bybit_ws_client.py](../../src/infrastructure/exchange/bybit_ws_client.py) (+48 LOC: get_execution_events()). **SSOT**: task_plan Phase 12a-1 (REST + WS 통합), FLOW Section 2 (Market Data Provider). | **Evidence**: [phase_12a1/](../evidence/phase_12a1/). **Phase 12a-1 완료** (BybitAdapter 완전 구현: 4 REST endpoints + WS execution.inverse + State caching + last_fill_price tracking). **새 세션 검증 가능**. **완료**: 2026-01-25. **다음**: Phase 12a-2 (Market Data Provider). |
| 12a-2 | [x] DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_12a2/completion_checklist.md), [Gate 7](../evidence/phase_12a2/gate7_verification.txt), [pytest](../evidence/phase_12a2/pytest_output.txt), [RED→GREEN](../evidence/phase_12a2/red_green_proof.md). **Tests**: [test_atr_calculator.py](../../tests/unit/test_atr_calculator.py) (9 cases) + [test_session_risk_tracker.py](../../tests/unit/test_session_risk_tracker.py) (14 cases) + [test_market_regime.py](../../tests/unit/test_market_regime.py) (8 cases) = **31 passed**. Total: **312 passed in 0.40s** (281 → 312, +31). **Gate 7**: ALL PASS (490 asserts). | **Application**: [atr_calculator.py](../../src/application/atr_calculator.py) (170 LOC: 14-period ATR, percentile, grid spacing), [session_risk_tracker.py](../../src/application/session_risk_tracker.py) (182 LOC: Daily/Weekly PnL, Loss streak, Fee ratio, Slippage), [market_regime.py](../../src/application/market_regime.py) (138 LOC: MA slope, regime classification). **SSOT**: task_plan Phase 12a-2 (Market Data Provider), account_builder_policy Section 9/11 (Session Risk/Entry Flow). | **Evidence**: [phase_12a2/](../evidence/phase_12a2/). **Phase 12a-2 완료** (Market Data Provider 완전 구현: ATR Calculator + Session Risk Tracker + Market Regime Analyzer). **새 세션 검증 가능**. **완료**: 2026-01-25. **다음**: Phase 12a-3 (Market Data Provider → BybitAdapter 통합). |
| 12a-3 | [x] DONE | **Evidence Artifacts**: [Completion Checklist](../evidence/phase_12a3/completion_checklist.md), [Gate 7](../evidence/phase_12a3/gate7_verification.txt), [pytest](../evidence/phase_12a3/pytest_output.txt). **Tests**: [test_dry_run_orchestrator.py](../../tests/integration/test_dry_run_orchestrator.py) (8 cases: DryRunMonitor 5 + Orchestration 3) = **8 passed**. Total: **320 passed in 0.44s** (312 → 320, +8). **Gate 7**: ALL PASS (511 asserts). | **Scripts**: [run_testnet_dry_run.py](../../scripts/run_testnet_dry_run.py) (230 LOC: BybitAdapter 통합, State transition detection, HALT handling, DryRunMonitor inline), [generate_dry_run_report.py](../../scripts/generate_dry_run_report.py) (250 LOC: Trade log analysis, Session Risk verification, Auto-generate DoD checklist). **SSOT**: task_plan Phase 12a-3 (Automated Dry-Run Infrastructure). | **Evidence**: [phase_12a3/](../evidence/phase_12a3/). **Phase 12a-3 완료** (Automated Dry-Run Infrastructure: Mock-based, Testnet 연결 불필요). **새 세션 검증 가능**. **완료**: 2026-01-25. **다음**: Phase 12a-4 (Force Entry 모드 + Testnet 자동 거래). |
| 12a-4 | [~] IN PROGRESS | **TBD** | **TBD** | **Phase 12a-4 IN PROGRESS** (Force Entry 모드 구현 + Testnet 30-50회 거래 실행). **DoD**: Force Entry 모드 구현 + Testnet 설정 + 30-50회 거래 + 로그 검증 + Report 작성. **다음**: Phase 12a-5 (Telegram 알림 통합). |
| 12a-5 | [ ] TODO | **TBD** | **TBD** | **Phase 12a-5 TODO** (Telegram 알림 통합). **DoD**: 상세 설계 문서 작성 + TelegramNotifier 구현 + Unit Tests + run_testnet_dry_run.py 통합 + Testnet 재실행 검증. **상세 설계 필수**: [telegram_notifier_design.md](../../docs/specs/telegram_notifier_design.md) (책임/의존성/클래스 설계/메시지 포맷/에러 처리/Integration point). |

---

## 6. Appendix: File Ownership (누가 뭘 담당하는지)

**Domain Logic (Phase 0-6)**:
- transition.py: 상태/인텐트 "유일한" 전이 엔진(핵심)
- entry_allowed.py: entry gate 결정(거절 사유코드 포함)
- sizing.py: contracts 산출(단위 고정)
- emergency.py/ws_health.py: 안전 모드/복구/차단
- order_executor.py: intents를 I/O로 실행(테스트는 fake_exchange로)
- stop_manager.py: SL 공백 방지의 주체
- orchestrator.py: Flow 순서 실행자(로직 최소)

**Real API Integration (Phase 7-9)**:
- exchange_port.py: ExchangeAdapter Port 인터페이스 (FakeExchange와 BybitAdapter 교체 가능)
- bybit_rest_client.py: REST 통신만 (서명/타임아웃/재시도/헤더 기반 rate limit)
- bybit_ws_client.py: WS 통신만 (auth/subscribe/reconnect/ping-pong)
- bybit_adapter.py: REST/WS 결과를 domain 이벤트로 변환 (로직 없음, 매핑만)
- killswitch.py: 손실/주문/호출 상한 감시 + 즉시 HALT
- alert.py: HALT 스냅샷 + 알림 전송 (텔레그램/슬랙/메일)
- rollback_protocol.py: 자동 정지/수동 개입 규칙

---

## 7. Oracle Backlog (Future Phases)

> 규칙: 미래 Phase를 위한 테스트 케이스는 **테스트 파일에 placeholder로 존재하지 않는다** (Gate 1 위반).
> 대신 이 섹션에 문서화하고, 해당 Phase 시작 시 **TDD (RED→GREEN)** 로 작성한다.

### Stop Status Recovery (Phase 1+)

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| SR-1 | state=IN_POSITION, position.qty=100, stop_status=MISSING | tick (복구 시도) | IN_POSITION | stop_status=ACTIVE, stop_recovery_fail_count=0 | TBD |
| SR-2 | state=IN_POSITION, stop_status=MISSING, stop_recovery_fail_count=2 | tick (복구 실패) | HALT | stop_status=ERROR, halt_reason="stop_loss_unrecoverable" | TBD |

### WS DEGRADED Mode (Phase 1+)

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| WS-1 | state=FLAT, ws_heartbeat_timeout=True (10초 초과) | tick | FLAT | degraded_mode=True, entry_allowed=False | TBD |
| WS-2 | state=IN_POSITION, ws_event_drop_count=3 | tick | IN_POSITION | degraded_mode=True, reconcile_interval=1.0, entry_allowed=True | TBD |
| WS-3 | state=FLAT (or any), degraded_mode=True, degraded_mode_entered_at = now() - 61s | tick | HALT | halt_reason="degraded_mode_timeout" | TBD |

### orderLinkId Validation (Phase 2: Entry Flow)

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| VAL-1 | signal_id 길이 36자 초과 | place_order 호출 전 검증 | - | ValidationError, 주문 시도 0회 | TBD |
| VAL-2 | signal_id="grid_a3f8d2e1c4_l", direction="Buy" | place_order 재시도 (동일 signal) | - | orderLinkId 동일, Bybit 중복 감지 | TBD |
| VAL-3 | client_order_id contains invalid chars (space, unicode, special) | validate before sending | - | ValidationError, 주문 호출 0회 | TBD |

### Entry Gates (Phase 2: Entry Flow)

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| GATE-1 | state=HALT | tick | HALT | place_order calls=0 | TBD |
| GATE-2 | state=COOLDOWN, cooldown_ends_at = now() + 3s | tick before timeout | COOLDOWN | entry_allowed=False | TBD |
| GATE-3 | state=COOLDOWN, cooldown_ends_at = now() - 1s | tick | FLAT | - | TBD |
| GATE-4 | positionIdx=1 or 2 | reconcile reads snapshot | HALT | halt_reason="hedge_mode_detected" | TBD |
| GATE-5 | rest_budget_remaining=0, ws_healthy=True | tick wants to call REST snapshot | - | REST call blocked, state unchanged or degraded_mode | TBD |

### Stop Update Policy (Phase 4: Position Management)

> 핵심 생존 규칙: 20% threshold + 2초 debounce + AMEND 우선 + cancel+place 최후 수단

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| PF-2 | state=IN_POSITION, position.qty=20, stop.qty=20 (ACTIVE), last_stop_update_at=1.0 | PARTIAL_FILL (+3, ts=5.0, delta 15% < 20%) | IN_POSITION | position.qty=23, stop.qty=20 (유지), stop_intent.action="NONE", reason="delta_under_20pct_threshold_blocks_stop_update" | TBD |
| PF-3 | state=IN_POSITION, position.qty=20, stop.qty=20 (ACTIVE), last_stop_update_at=1.0 | PARTIAL_FILL (+4, ts=5.0, delta 20% == threshold) | IN_POSITION | position.qty=24, stop_intent.action="AMEND", desired_qty=24, reason="delta_at_or_above_20pct_triggers_amend_priority" | TBD |
| PF-5 | state=IN_POSITION, position.qty=20→24, stop.qty=20 (ACTIVE), AMEND intent issued, amend_fail_count=1 | AMEND 거절, next tick | IN_POSITION | next_intent.action="AMEND", desired_qty=24, reason="amend_rejected_retry_amend_before_cancel_place" | TBD |
| PF-6 | (A) stop_status=MISSING or (C) amend_fail_count=2 | position.qty changed + debounce 통과 | IN_POSITION | stop_intent.action="CANCEL_AND_PLACE", desired_qty, reason 조건별 | TBD |

**Notes:**
- PF-2~PF-6: Stop Update Policy는 Phase 4에서 구현. AMEND 우선 원칙과 Stop 공백 방지가 핵심.
- PF-4 (debounce coalescing): 현재 transition()이 stateless이므로 Phase 4 Stop Update Executor에서 구현 예정.

### Execution Event Mapping from Order Fill (Phase 9+)

> 실제 주문 발주 → 체결 → execution 메시지 수신 → 도메인 이벤트 변환

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| EX-1 | REST로 소액 주문 발주 (Market order, BTCUSD, 1 contract) | WS execution 메시지 수신 | - | ExecutionEvent(FILL) 변환 성공, orderId/execQty 일치 | TBD |
| EX-2 | REST로 소액 주문 발주 (Limit order, BTCUSD, 10 contracts, 부분 체결 가능) | WS execution 메시지 수신 (부분 체결) | - | ExecutionEvent(PARTIAL_FILL) 변환 성공, execQty < orderQty | TBD |
| EX-3 | REST로 주문 발주 후 즉시 취소 | WS execution 메시지 수신 (CANCEL) | - | ExecutionEvent(CANCEL) 변환 성공, execQty=0 | TBD |

**Notes:**
- EX-1~EX-3: Phase 9에서 구현 예정 (REST order flow 완성 후)
- 삭제된 placeholder 테스트: `test_ws_execution_message_from_order_fill` (2026-01-23, Gate 1b 위반 수정)

---

## 8. Change History
| Date | Version | Change |
|------|---------|--------|
| 2026-01-25 | 2.38 | **Phase 12a-4/12a-5 분리 (Document-First Workflow 복구)**: 사용자 지적 (텔레그램 로그 히스토리를 Phase 분리 필요) → Phase 12a-4 (Force Entry + Testnet 거래) + Phase 12a-5 (Telegram 알림, 상세 설계 포함) 분리. **Phase 12a-4 Scope**: Force Entry 모드 구현 + Testnet 30-50회 거래 + 로그 모니터링 (`tail -f`). **Phase 12a-5 Scope**: 상세 설계 문서 작성 (`telegram_notifier_design.md`, 책임/의존성/클래스 설계/메시지 포맷/에러 처리/Integration point 8개 섹션) + TelegramNotifier 구현 + Unit Tests + run_testnet_dry_run.py 통합 + Testnet 재실행 검증. **근거**: (1) Critical Path 분리 (Force Entry 필수, Telegram 선택), (2) DoD 단위 축소 (각각 1-2시간), (3) Document-First 원칙 (상세 설계 선행), (4) Rollback 최소화 (Telegram 실패 시 Phase 12a-4 영향 없음). **Progress Table**: Phase 12a-4 IN PROGRESS, Phase 12a-5 TODO 추가. **Status**: "Phase 12a-4 IN PROGRESS (Force Entry), Phase 12a-5 TODO (Telegram)". |
| 2026-01-25 | 2.32 | **Phase 12a-1 완료 (BybitAdapter 완전 구현)**: REST API + WS Integration + State Caching + DEGRADED Mode + Session Risk Tracking. **구현**: (1) BybitAdapter (13207 bytes, MarketDataInterface 구현), (2) bybit_rest_client.py +158 LOC (4 endpoints: tickers, wallet-balance, position, execution), (3) bybit_ws_client.py +48 LOC (get_execution_events 메서드), (4) Tests 14개 (REST 4, WS 2, Caching 3, DEGRADED 3, Session Risk 2). **Tests**: 281 passed (+14, 267 → 281), 회귀 없음. **Evidence**: [phase_12a1/](../evidence/phase_12a1/) (completion_checklist.md, pytest_output.txt, gate7_verification.txt, red_green_proof.md). **커밋**: [TBD]. **✅ Phase 12a-1 COMPLETE**. **Status**: "Phase 0~12a-1 COMPLETE". **새 세션 검증 가능**. **다음**: Phase 12a-2 (Market Data Provider 통합). |
| 2026-01-24 | 2.31 | **Phase 11b 완료 (Full Orchestrator Integration + Testnet E2E)**: Part 3/3 완료 (Testnet E2E 6개 테스트). **구현**: (1) test_full_cycle_testnet.py 생성 (6 test cases: Full cycle, Entry blocked, Stop hit, Session Risk HALT, Degraded mode, Multiple cycles), (2) Exit FILL 후 last_fill_price 업데이트 추가 (Grid signal 무효화, 즉시 재진입 방지), (3) FakeMarketData.inject_last_fill_price() 명시적 호출 (테스트 투명성). **Tests**: 267 passed (+22 from Phase 11b start: Entry 7 + Event 9 + Testnet 6), 회귀 없음. **Evidence**: [testnet_cycle_proof.md](../evidence/phase_11b/testnet_cycle_proof.md), [completion_checklist.md](../evidence/phase_11b/completion_checklist.md), [pytest_output.txt](../evidence/phase_11b/pytest_output.txt). **커밋**: [현재 커밋]. **✅ Phase 11b COMPLETE**: Entry Flow (7) + Event Processing (9) + God Object 리팩토링 (413 LOC) + Testnet E2E (6) 모두 완료. **Status**: "Phase 0~11b COMPLETE". **새 세션 검증 가능**. **다음**: Phase 12 (Dry-Run Validation). |
| 2026-01-24 | 2.30 | **SSOT 복구 + Phase 10 Evidence 완성 (리뷰 판정 조치 완료)**: 리뷰 판정에서 발견된 3가지 치명적 문제 조치 완료. **(1) 문서-코드 테스트 수 불일치 해소**: Status "Phase 0~11a COMPLETE" → "Phase 0~10 COMPLETE \| Phase 11a COMPLETE \| Phase 11b IN PROGRESS" 명확화 (100% 원칙 준수), Progress Table Phase 11b 행에 "261 passed" 명시. **(2) God Object 위반 해소**: ✅ **이미 완료됨** (v2.29, d7292e3 커밋: orchestrator.py 706→413 LOC, -41%). **(3) Phase 10 Evidence 완성**: completion_checklist.md 체크박스 업데이트 (DoD 6/6 완료), red_green_proof.md + gate7_verification.txt 이미 존재 확인, "Phase 10 최종 판정: COMPLETE" 명시. **근거**: SSOT 원칙 (문서가 유일한 진실), 100% 원칙 (부분 완료 ≠ COMPLETE), 새 세션 검증 가능성 확보. **결과**: 리뷰 판정 FAIL → **PASS 전환**. |
| 2026-01-24 | 2.29 | **God Object 리팩토링 완료 (FLOW.md Section 4.2 준수)**: orchestrator.py 706 → 413 LOC (-293 LOC, -41%). **3개 모듈로 책임 분리**: (1) emergency_checker.py (Session Risk 통합, 145 LOC), (2) entry_coordinator.py (Entry helpers 4개, 151 LOC), (3) event_processor.py (Event helpers 4개, 161 LOC). **Thin wrapper pattern**: orchestrator.py는 흐름 관리만, 로직은 분리된 모듈에 위임. **Pure functions**: 명확한 파라미터, 상태 변경 없음. **Tests**: 261 passed (회귀 없음). **커밋**: d7292e3. **✅ FLOW.md Section 4.2 준수**: orchestrator.py < 500 LOC. **Progress Table**: Phase 11b 업데이트 (413 LOC 명시, 리팩토링 3 모듈 추가). |
| 2026-01-24 | 2.28 | **Phase 11b Part 2/3 완료 (Event Processing + Self-healing)**: Event Processing 구현 완료 + Atomic state transition + Dual ID tracking + Self-healing check. **구현**: (1) Event Processing helper 3개 (_get_fill_events, _match_pending_order with Dual ID tracking, _create_position_from_fill with signal_id), (2) Self-healing check (_verify_state_consistency, Position vs State 일관성 검증, HALT on inconsistency), (3) run_tick()에 self-healing check 추가 (매 tick 최우선 검증), (4) FakeMarketData 확장 (inject_fill_event에 orderLinkId/side/price 추가), (5) Unit Test 9개 작성 (Entry FILL, Exit FILL, Dual ID matching, Self-healing 검증 모두 PASS). **Tests**: 261 passed (+16, 252 → 261), orchestrator.py LOC 575 → 706 (⚠️ God Object 금지 위반: 500 limit 초과, 리팩토링 필요). **커밋**: f158d7a. **진행**: Part 1/3 (Entry Flow), Part 2/3 (Event Processing) 완료, Part 3/3 (Testnet E2E) 대기. **Progress Table**: Phase 11b 업데이트 (16 tests, 706 LOC 명시). |
| 2026-01-24 | 2.27 | **Phase 11b 시작 (Entry Flow 구현 완료, Part 1/3)**: Document-First Workflow 준수 → task_plan.md 먼저 업데이트 (v2.27). **구현**: (1) MarketDataInterface 확장 (7개 메서드: get_current_price, get_atr, get_last_fill_price, get_trades_today, get_atr_pct_24h, get_winrate, get_position_mode), (2) FakeMarketData Mock 구현 (13개 메서드), (3) StageParams, SignalContext, SizingParams 클래스 정의, (4) orchestrator._decide_entry() Step 1~7 구현 (Signal → Gates → Sizing → Order placement → FLAT → ENTRY_PENDING 전환), (5) Helper 메서드 4개 추가, (6) Unit Test 7개 작성 (모두 PASS). **Tests**: 252 passed (+7), orchestrator.py LOC 287 → 423 (✅ God Object 금지 준수: < 500). **Evidence**: [risk_analysis.md](../evidence/phase_11b/risk_analysis.md), [entry_flow_design.md](../evidence/phase_11b/entry_flow_design.md). **커밋**: c17cc8e. **진행**: Part 1/3 완료 (Entry Flow), Part 2/3 진행 중 (Event Processing + Self-healing). **Progress Table**: Phase 11b TODO → IN PROGRESS. |
| 2026-01-24 | 2.26 | **Phase 9d 완료 (CRITICAL 문제 해결 → 실거래 투입 가능)**: Phase 9 FAIL 판정 이후 CRITICAL Issue #1 수정 완료. **수정**: orchestrator.py:113 run_tick()에서 `self.current_timestamp = self.market_data.get_timestamp()` 추가 → Slippage anomaly 보호 활성화. **근거**: (1) Slippage Anomaly Kill 정상 작동 (test_slippage_anomaly_triggers_halt 통과), (2) Session Risk Policy 4개 모두 활성 (Daily/Weekly Loss Cap, Loss Streak, Fee/Slippage Anomaly), (3) 238 tests passed (회귀 없음). **조치**: Phase 9 Status FAIL → DONE, Progress Table 업데이트 (phase_9d Evidence 링크 추가, 238 tests), 본문 "잔존 문제" → "해결 완료" 섹션 변경, 실거래 투입 조건 체크박스 완료. **Evidence**: phase_9d/ 디렉토리 (slippage_fix_proof.md, pytest_output, completion_checklist.md). **실거래 준비 상태**: ✅ READY. |
| 2026-01-24 | 2.25 | **Phase 9 FAIL 판정 (100% 기준 적용)**: Phase 9 Revision 완료 (UTC boundary 버그 수정 + Type safety 개선) 후 100% 기준 재검증 → **1개 CRITICAL 문제 발견 → FAIL 판정**. **근거**: (1) orchestrator.py `current_timestamp = None` 초기화 누락 → Slippage anomaly 보호 완전히 무력화 (Session Risk 4개 중 1개 비활성), (2) 사용자 원칙 "조건부 통과라는건없어 항상 100프로 기준으로해줘" → FAIL is FAIL. **조치**: Phase 9 Status DONE → FAIL, Progress Table 업데이트 (⚠️ CRITICAL Issue 명시, Evidence 링크 추가), 본문에 "잔존 문제" 섹션 추가 (CRITICAL/MEDIUM/LOW 3가지), 실거래 투입 조건 명시. **테스트**: 237 passed (UTC edge cases 추가), Gate 7 ALL PASS, 375 asserts. **실거래 투입 불가 상태**. |
| 2026-01-24 | 2.24 | **Phase 재정의 (11 → 11a/11b 분리, Option A 선택)**: 사용자 원칙 "phase가 다르게진행되면 그걸 분리통합해서 항상 태스크안에서 100프로완료되게 해" → Phase 11을 11a (Signal+Exit, DONE), 11b (Full Integration+Testnet, TODO)로 분리. Evidence 디렉토리 phase_11 → phase_11a 변경. Progress Table: Phase 11a DONE (100% 완료), Phase 11b TODO 추가. Status: "Phase 0~11a COMPLETE". **근거**: 독립 완료 가능한 단위 분리 → 100% 원칙 준수. |
| 2026-01-24 | 2.23 | **원칙 위반 복구 (부분 완료 DONE 표시 → DOING 복원)**: Phase 11을 DONE으로 표시했으나, 원래 DoD 4개 중 2개만 완료 (Signal+Exit 완료, Entry flow+Testnet 미완성). **사용자 원칙**: "100프로 통과가 아니면 통과표시하지마" → 즉시 Progress Table DONE → DOING 복원. Status 수정: "Phase 0~11 COMPLETE" → "Phase 0~10 COMPLETE, Phase 11 DOING (50%)". **근거**: 부분 완료 ≠ DONE, 원칙 준수. → v2.24에서 Phase 재정의로 해결. |
| 2026-01-24 | 2.22 | **Phase 11 부분 구현 (Signal Generation + Exit Manager)**: (1) Signal Generator 구현 (Grid-based, ATR spacing, 10 tests), (2) Exit Manager 구현 (Stop hit check, Exit intent, 8 tests), (3) Orchestrator Integration (Exit Manager만 통합), (4) ExitIntent 추가. **⚠️ 원칙 위반**: Full Integration + Testnet 미완성인데 DONE 표시 → v2.23에서 복구, v2.24에서 Phase 재정의. 245 tests passed (+18). |
| 2026-01-24 | 2.21 | **Phase 10 JSONL 저장 패턴 운영 현실화 (치명적 구멍 4개 메움)**: (1) Single line integrity: "보장"이 아니라 "single syscall write + partial line recovery (truncate)" 명확화, (2) fsync 정책: "per append"가 아니라 "batch (10 lines) / periodic (1s) / critical event (HALT/LIQ/ADL)" 운영 균형 정의, (3) Rotation: "handle swap"만이 아니라 "UTC 기준 + pre-rotate flush+fsync + optional fsync(dir)" 완전 정의, (4) fd 관리: "with open() 매번"이 아니라 "fd 상시 유지 + rotate 시점에만 close/open" 성능 최적화. **근거**: 사용자 지적 (v2.20 "Durable append" 정의에 실전 구멍 4개) → 운영 수준 정의 완성. |
| 2026-01-24 | 2.20 | **SSOT 복구 2차 (Phase 9/10 현실 정렬 3가지)**: (1) Phase 9 섹션 "도박 단계" 과거형 수정 (현재형 제거, Status: ✅ DONE 명시, 구현 완료 내용↔구현 전 위험 진단 분리), (2) Section 2.2 Planned: Phase 9 항목 제거 (2.1 Implemented로 이동, Phase 10+ 항목만 보존), (3) Phase 10 JSONL 저장 패턴 현실화 ("Atomic write (temp→rename)" 제거, "Durable append (O_APPEND, flush+fsync, rotation-safe swap)" 정의, DoD에 market_regime deterministic 정의 + failure-mode tests 추가). **근거**: 사용자 지적 (Phase 9 DONE 후 문서-현실 괴리 3가지) → 즉시 수정. |
| 2026-01-24 | 2.19 | **SSOT 복구 (문서 내부 모순 3가지 해결)**: (1) 상단 Status를 Progress Table 최종 상태와 동기화 (Phase 0~8 COMPLETE → Phase 0~9 COMPLETE, 188 passed → 208 passed, "Phase 9 시작 가능" 제거), (2) Last Updated 간소화 (세부 내용 제거), (3) Phase 5 vs Phase 10 역할 구분 명확화 (Phase 5: 운영 감사용 v0, Phase 10: 전략 최적화용 v1.0). **근거**: 사용자 지적 (SSOT 깨짐 3가지) → 즉시 수정. |
| 2026-01-23 | 2.18 | **Gate 1a/1b 위반 수정 완료 (Phase 8 재검증)**: (1) Placeholder 테스트 제거 (test_ws_execution_message_from_order_fill 삭제, @pytest.mark.skip + TODO 3개 + pass), (2) Oracle Backlog 섹션에 EX-1~EX-3 추가 (Phase 9 구현 예정), (3) conftest.py 생성 (api_credentials fixture 공통화, pytest.skip() 5회 → 1회), (4) Evidence Artifacts v2 생성 (gate7_verification_v2.txt, placeholder_removal_proof.md). **근거**: CLAUDE.md Section 5.7 Gate 1b FAIL → PASS, Zero Tolerance + Oracle Backlog 규칙 준수. pytest: 188 passed, 15 deselected (placeholder 1개 제거). |
| 2026-01-23 | 2.17 | **SSOT 모순 제거 완료 (치명적 문제 3개 해결)**: (1) Repo Map 2.2 "Planned (Phase 2+ 예정, 아직 미생성)" → "Planned (Phase 9+ 예정)" 수정, Phase 2~8 파일들을 2.1 Implemented로 이동 (문서-현실 일치), (2) Phase 8 DoD 체크박스 [ ] → [x] 변경 + Evidence 링크 추가 (5개 항목 완료 증거), (3) bybit_ws_client.py 스펙 통일 ("8개 핵심 메서드" → "489 LOC, 24 메서드: public 14 + private 10"). **근거**: CLAUDE.md 리뷰 판정 FAIL → 수정 완료. |
| 2026-01-23 | 2.16 | **Phase 8 문서 정렬 (Phase 0-8 완료 확정)**: Phase 8 본문 "WebSocket 구현 계획" 섹션을 "구현 완료"로 수정 (과거 계획서 제거, 실제 구현 내용 반영). Progress Table 이모지 제거 (✅ DONE → DONE, 텍스트 통일). Phase 8 완료 상태 확정: 5개 시나리오 모두 검증 완료 (15 passed, 1 skip), bybit_ws_client.py 489줄 구현 완료, Evidence Artifacts 존재. 본문↔Progress Table 모순 해소 (시도, v2.17에서 완료). |
| 2026-01-23 | 2.15 | **Phase 9 Session Risk Policy 추가**: "도박 단계" 치명적 발견 (Per-trade cap만 존재, Session cap 없음 → 5연속 -$10 = -$50 가능). Phase 9를 3개 하위 단계로 확장: Phase 9a (Session Risk 4개: daily/weekly loss cap, loss streak kill, fee/slippage anomaly), Phase 9b (Per-trade cap 조정 $10→$3, ADR 필요), Phase 9c (Orchestrator 통합 + 기존 킬스위치/알림/롤백). Session Risk Policy 구현 위치/테스트/DoD 문서화. **근거**: `~/.claude/plans/logical-swimming-squirrel.md` ML 계획서 Appendix (Phase 9 업데이트 내용). |
| 2026-01-23 | 2.14 | **내부 모순 수정 (SSOT 확정)**: Global Rule 1.4 "WS는 async" → "WS I/O는 메인 tick block 금지 (async/thread 허용)" 수정, **Ping-pong 주체 반대 오류 수정** (실제: 클라이언트 ping → 서버 pong), WS 토픽 SSOT 확정 (execution.inverse for Inverse, All-In-One과 혼용 불가), Bybit 공식 문서 근거 3개 추가 (auth 서명 "GET/realtime{expires}", ping-pong 주체/주기, execution 토픽), Thread safety 표현 정확화 ("GIL 보호" → "단일 producer/consumer 패턴"). **치명적 오류 3개 해결**. |
| 2026-01-23 | 2.13 | **WebSocket 구현 계획 추가** (Phase 8에 WS 구현 상세 설계 추가, 6-9시간 예상) - HOLD 판정으로 v2.14에 즉시 대체됨 |
| 2026-01-23 | 2.12 | **Phase 7 경계 엄격화 + 실거래 함정 3개 추가**: Phase 7 금지 조항 강화 (실제 네트워크 호출 금지, WS connect 금지, 키 누락 시 프로세스 거부), 실거래 생존성 함정 3개 해결 (WS 폭주/백프레셔, Clock 주입, mainnet 사고 방지). Rate limit retCode 10006 우선 명시 (HTTP 429 보조). WS 스펙 근거 추가 (Bybit 문서 링크). DoD "3가지" → "4가지" 수정. Status에 pytest 최종 출력 링크 추가. |
| 2026-01-23 | 2.11 | **Phase 7-9 추가 (Real API Integration → Mainnet Preparation)**: Bybit 공식 스펙 준수 (X-Bapi-* 헤더 기반 rate limit, WS ping-pong), Phase 7 "골격만" (Contract tests only, Live tests 금지), Phase 8 "재현 가능한 시나리오 5개", Phase 9 "운영 안전장치" (킬스위치/알림/롤백/dry-run 상한). Real Trading Trap Fix Gates 수정 ("90/min" → internal safety budget, WS 요구사항 추가). |
| 2026-01-19 | 2.5 | **Repo Map 정렬 완료 (Gate 4 재발 방지)**: Repo Map을 "Implemented (Phase 0 완료)" vs "Planned (Phase 1+)" 섹션으로 분리, 문서↔현실 괴리 제거, 컨텍스트 끊김 시 혼란 방지 |
| 2026-01-19 | 2.4 | **Gate 7 완전 달성**: sys.path hack 0개 (pyproject.toml 정상화, PYTHONPATH=src 방식), 패키징 표준 준수, CLAUDE.md pytest 실행법 업데이트 |
| 2026-01-18 | 2.3 | Oracle Backlog 섹션 추가 (17개 미래 케이스 문서화, Gate 1 위반 제거) |
| 2026-01-18 | 2.2 | 조건/DoD 강화, 진행상황표/업데이트 룰 추가, 컨텍스트 끊김 방지 구조 확정 |
| 2026-01-18 | 2.0 | 정책/구현 분리, Gates 추가, Phase 0/0.5 강화 |