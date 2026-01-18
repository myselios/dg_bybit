# FLOW.md — Execution Flow Constitution

**문서 성격**: 불변 헌법 (Constitution)
**변경 규칙**: 이 문서를 수정하려면 ADR(Architecture Decision Record) 필수
**우선순위**: STRATEGY.md / RISK.md / task_plan.md보다 상위

---

## 0. 헌법 선언

이 문서는 Account Builder 시스템의 **실행 규칙**을 정의한다.

- Plan(작업지시서)은 바뀌어도, **Flow(실행 순서)는 바뀌지 않는다**.
- 코드는 이 Flow를 **우회할 수 없다**.
- 이 Flow를 어기는 구현은 **버그로 간주**한다.

---

## 1. Execution State Machine (최소 상태 집합)

시스템은 **6가지 상태** 중 하나에만 존재한다.

```
FLAT           : 포지션 없음, 진입 가능
ENTRY_PENDING  : Entry 주문 대기 중 (체결 미완료)
IN_POSITION    : 포지션 오픈 (Stop Loss 주문 유지)
EXIT_PENDING   : Exit 주문 대기 중 (청산 미완료)
HALT           : 모든 진입 차단 (Manual reset only)
COOLDOWN       : 일시적 차단 (자동 해제 가능)
```

### 상태 전환 규칙

```
FLAT ─────────► ENTRY_PENDING  (주문 체결 대기)
                    │
                    ▼
ENTRY_PENDING ───► IN_POSITION  (체결 완료)
                    │
                    ├──────────► EXIT_PENDING  (청산 주문)
                    │                │
                    ▼                ▼
                IN_POSITION ──────► FLAT  (청산 완료)
                    │
                    ▼
                  HALT  (Emergency / Balance < $80 / Liquidation)

HALT ──────────► FLAT  (Manual reset only)
COOLDOWN ──────► FLAT  (Auto after timeout)
```

### 절대 금지

- **ENTRY_PENDING 상태를 건너뛰고 바로 IN_POSITION**: 부분체결/중복주문 사고
- **IN_POSITION인데 다시 Entry 시도**: 포지션 누적
- **EXIT_PENDING인데 다시 Exit**: 중복 청산

### IN_POSITION 서브상태 (stop_status)

**문제**: State Machine은 6개 상태만 추적하지만, Stop 주문 상태는 추적 안 함

**실거래 문제**:
- IN_POSITION인데 Stop이 거절/취소/만료될 수 있음
- Amend 실패/중복/지연이 생김
- "IN_POSITION인데 Stop 없는 상태"를 정상 흐름이 커버 못 함

**헌법 규칙**: Position 객체에 `stop_status` 필드 추가 (State 수는 6개 유지)

**stop_status 값**:
```
ACTIVE   : Stop 주문 활성 (정상)
PENDING  : Stop 설치/갱신 중 (일시적)
MISSING  : Stop 없음 (비정상, 즉시 복구 필요)
ERROR    : Stop 복구 실패 (HALT 고려)
```

**관리 규칙**:
```python
# IN_POSITION일 때 Stop 감시
if state == IN_POSITION:
    if stop_status == MISSING:
        # 즉시 복구 시도
        try:
            place_stop_loss(
                qty=position.qty,
                stop_price=calculate_stop_price(position.entry_price, position.direction),
                direction=position.direction,
                signal_id=position.signal_id
            )
            stop_status = ACTIVE
            stop_recovery_fail_count = 0
        except Exception as e:
            stop_recovery_fail_count += 1
            log_error("stop_recovery_failed", {
                "attempt": stop_recovery_fail_count,
                "error": str(e)
            })

            if stop_recovery_fail_count >= 3:
                stop_status = ERROR
                HALT(reason="stop_loss_unrecoverable")
```

**전이 규칙**:
```
ENTRY_PENDING → IN_POSITION 시: stop_status = PENDING → place_stop_loss() → ACTIVE
IN_POSITION + Stop 체결/취소: stop_status = MISSING → 복구 시도
IN_POSITION + Amend 성공: stop_status = ACTIVE 유지
IN_POSITION + Amend 실패: stop_status = PENDING → 재시도 → ACTIVE or ERROR
```

**금지**:
- IN_POSITION인데 stop_status를 확인 안 함
- MISSING 상태를 방치
- ERROR 상태인데 계속 운용

---

## 2. Tick Execution Flow (1 Cycle)

**Tick 주기**: 목표 1초 간격, 실제는 동적 조정 (blocking wait 절대 금지)

### Tick 실행 규칙

**목표 주기**: 1초
**실제 주기**: API latency + rate limit 고려하여 0.5~2초 사이 동적 조정

**Rate Limit 보호 (합산 제한)**:
- **REST Budget**: 1분 rolling window 기준 **90회 제한** (Bybit 120 req/min의 75%)
- Tick snapshot: ~3회/tick (price, account, orders)
- Reconcile: 상태별 5~30초마다 추가 REST 호출 (2회)
- **합산 예산 관리** 필수
- Rate limit 근접 시 (80% 도달): Tick 주기 자동 증가 (1초 → 2초)
- Execution events는 **WebSocket 우선**, REST는 fallback만

```python
# REST Budget 추적
REST_BUDGET_PER_MIN = 90
rolling_rest_calls = deque(maxlen=60)  # 1분 rolling window

def track_rest_call():
    rolling_rest_calls.append(now())

    # 1분 이내 호출 수
    calls_in_last_min = len([t for t in rolling_rest_calls if now() - t < 60])

    # 80% 도달 시 경고
    if calls_in_last_min > REST_BUDGET_PER_MIN * 0.8:
        tick_interval = min(tick_interval * 1.5, 2.0)
        log_warning("rest_budget_high", calls_in_last_min)

    # 100% 도달 시 HALT (rate limit 초과 직전)
    if calls_in_last_min >= REST_BUDGET_PER_MIN:
        HALT(reason="rest_budget_exceeded")
```

**Data Source 우선순위**:
1. **WebSocket** (실시간 execution/order/position stream)
2. **REST** (WebSocket 실패 시 fallback, snapshot 용도만)

```
[Every Tick - 1초 간격]
  │
  ▼
┌─────────────────────────────────────────┐
│ [1] Update Snapshot (항상)              │
│   - Market: price, ATR, drops, latency  │
│   - Account: equity_btc, margin, upnl   │
│   - Orders: status, fills, cancels      │
└─────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────┐
│ [1.5] Emergency Check (최우선, 항상)    │
│   - HALT 필요? → cancel orders + block  │
│   - Recovery 가능? → COOLDOWN 해제     │
└─────────────────────────────────────────┘
  │
  ├────── YES (HALT) ──────────────────┐
  │                                    │
  ▼                                    │
┌─────────────────────────────────────────┐
│ [2] Handle Execution Events (항상)      │
│   - Order fills / partial fills         │
│   - Order cancels / rejects             │
│   - State transition                    │
│   - Metrics update (winrate, streak)   │
│                                         │
│ Event Source Priority:                  │
│   1. WebSocket execution stream         │
│   2. REST fallback (WS 실패 시만)       │
└─────────────────────────────────────────┘
  │
  ├────── if IN_POSITION ───────────────┤
  │                                     │
  ▼                                     │
┌─────────────────────────────────────────┐
│ [3] Manage Position (IN_POSITION only)  │
│   - Stop Loss 주문 유지/재설정          │
│   - Grid Exit 조건 체크                 │
│   - Emergency Exit 트리거               │
└─────────────────────────────────────────┘
  │
  └────── if FLAT only ──────────────────┘
           │
           ▼
      ┌─────────────────────────────────────────┐
      │ [4] Signal Decision                     │
      │   - Signal 생성 (LONG/SHORT/NONE)       │
      │   - Grid spacing 계산                   │
      └─────────────────────────────────────────┘
           │
           ├────── Signal == NONE ───────────┐
           │                                 │
           ▼                                 │
      ┌─────────────────────────────────────────┐
      │ [5] Risk Gate (7 gates)                 │
      │   - Stage determination                 │
      │   - Max trades/day                      │
      │   - Volatility threshold                │
      │   - EV gate (fee × K)                   │
      │   - Maker-only enforcement              │
      │   - Winrate gate                        │
      │   - Cooldown check                      │
      └─────────────────────────────────────────┘
           │
           ├────── REJECT ───────────────────┤
           │                                 │
           ▼                                 │
      ┌─────────────────────────────────────────┐
      │ [6] Position Sizing                     │
      │   - Stop distance (Grid-based)          │
      │   - Contracts (loss budget + margin)    │
      │   - Liquidation buffer check            │
      └─────────────────────────────────────────┘
           │
           ├────── REJECT ───────────────────┤
           │                                 │
           ▼                                 │
      ┌─────────────────────────────────────────┐
      │ [7] Place Entry Order                   │
      │   - Maker 주문                          │
      │   - State = ENTRY_PENDING (비동기)      │
      │   - 다음 tick에서 체결 확인             │
      └─────────────────────────────────────────┘
           │
           └─────────────────────────────────┘
                       │
                       ▼
                 [End Tick]
```

---

## 2.5. Execution Events (상태 확정 규칙)

**필수 규칙**: ENTRY_PENDING/EXIT_PENDING 상태에서 확정은 **이벤트로만** 가능

### Event Source

**우선순위**:
1. **WebSocket execution stream** (실시간)
   - `execution` topic: fill/partial fill/cancel/reject
   - `order` topic: order status change
   - `position` topic: position update (ADL/liquidation)

2. **REST fallback** (WebSocket 단절 시만)
   - `GET /v5/order/realtime`: 미체결 주문 조회
   - `GET /v5/position/list`: 포지션 상태 확인

### Event Types (필수 처리)

```
FILL             : 완전 체결 → ENTRY_PENDING → IN_POSITION
PARTIAL_FILL     : 부분 체결 → ENTRY_PENDING → IN_POSITION (부분)
CANCEL           : 주문 취소 → (filled_qty > 0 ? IN_POSITION : FLAT)
REJECT           : 주문 거부 → ENTRY_PENDING → FLAT
LIQUIDATION      : 강제 청산 → IN_POSITION → HALT
ADL              : 자동 감소 → IN_POSITION → (수량 감소 or FLAT)
```

### PARTIAL_FILL 처리 규칙 (치명적, 필수)

**문제**: 부분체결 시 Stop 미설치 → 노출 상태 → 급변동 시 파손

**헌법 규칙**:

```python
def on_partial_fill(event):
    filled_qty = event.filled_qty
    remaining_qty = event.order_qty - filled_qty

    # Rule 1: filled_qty > 0이면 즉시 IN_POSITION 전환
    if filled_qty > 0:
        state = IN_POSITION
        position.qty = filled_qty
        position.entry_working = True  # 서브상태: 잔량 주문 활성

        # Rule 2: Stop Loss 즉시 설치 (filled_qty 기준)
        stop_order = place_stop_loss(
            qty=filled_qty,
            stop_price=calculate_stop_price(entry_price)
        )

    # Rule 3: 잔량 처리
    # - 잔량이 자동 취소되거나 명시적 취소 시
    # - 상태는 FLAT 아님! IN_POSITION 유지 (filled_qty > 0)
    # - entry_working = False로 전환
```

**서브상태 (entry_working)**:

```python
# IN_POSITION 서브상태
position.entry_working = True   # 잔량 주문 활성 (추가 체결 가능)
position.entry_working = False  # 잔량 없음 (포지션만)

# Tick Flow에서
if state == IN_POSITION:
    # Stop은 항상 position.qty 기준으로 관리
    manage_stop_loss(position.qty)

    # entry_working=True: 잔량 체결 대기
    if position.entry_working:
        # 추가 체결 이벤트 처리
        if additional_fill_event:
            position.qty += additional_filled_qty

            # Stop 갱신 (조건부 + Amend 우선)
            update_stop_loss_if_needed(
                current_stop_qty=old_stop_qty,
                new_qty=position.qty,
                stop_order_id=stop_order_id
            )

        # 잔량 취소/만료 이벤트
        if remaining_cancelled or timeout:
            position.entry_working = False

    # entry_working=False: Signal Decision 가능 (exit 신호만)
```

**금지**:
```python
# ❌ 부분체결인데 Stop 안 깔기
if filled_qty < order_qty:
    state = ENTRY_PENDING  # 대기? 위험!
    # Stop 없음 → 급변동 시 노출

# ❌ 잔량 취소 시 FLAT으로 착각
if remaining_qty_cancelled:
    state = FLAT  # 잘못됨! filled_qty는 이미 포지션
```

**올바른 방식**:
```python
# ✅ 부분체결 = 즉시 포지션 + Stop
if filled_qty > 0:
    state = IN_POSITION
    position.qty = filled_qty

    # Stop은 filled_qty 기준으로 즉시
    place_stop_loss(qty=filled_qty, ...)

# ✅ 추가 체결 시 Stop 갱신
if additional_fill:
    position.qty += additional_filled_qty

    # Stop 갱신 (조건부 + Amend 우선)
    update_stop_loss_if_needed(
        current_stop_qty=old_stop_qty,
        new_qty=position.qty,
        stop_order_id=stop_order_id
    )
```

### State Confirmation Rule (정상 vs DEGRADED 모드 분리)

#### 정상 모드 (WS healthy)

**원칙**: 상태 전이는 이벤트가 트리거

**금지**:
```python
# ❌ REST 폴링으로 상태 확정
if get_order_status() == "Filled":
    state = IN_POSITION
```

**올바른 방식**:
```python
# ✅ Event-driven 상태 확정
def on_execution_event(event):
    if event.type == "FILL" and state == ENTRY_PENDING:
        state = IN_POSITION
    elif event.type == "CANCEL":
        state = FLAT
```

#### DEGRADED 모드 (WS unhealthy)

**진입 조건**:
- Heartbeat 10초 이상 없음
- 연속 이벤트 드랍 3회 이상

**동작**:
```python
if ws_heartbeat_timeout_exceeded or ws_event_drop_count >= 3:
    log_critical("entering_degraded_mode", {
        "reason": "ws_disconnection",
        "heartbeat_timeout": ws_heartbeat_timeout_exceeded,
        "event_drops": ws_event_drop_count
    })

    system.degraded_mode = True

    # 1. 신규 진입 차단 (FLAT일 때만)
    if state == FLAT:
        entry_allowed = False
        log_warning("entries_blocked", "degraded_mode")

    # 2. Reconcile 주기 단축
    if state == IN_POSITION:
        reconcile_interval = 1.0  # 1초 (포지션 보호)
    elif state in [ENTRY_PENDING, EXIT_PENDING]:
        reconcile_interval = 1.0  # 1초 (중요 상태)
    else:  # FLAT
        reconcile_interval = 30.0  # 기존 유지

    # 3. 목적: '확정'이 아니라 '정합성 회복'
    # REST로 불일치 감지 → 히스테리시스 적용 (Section 2.6)
```

**장기 미복구 시 HALT**:
```python
# DEGRADED 상태 60초 이상 지속 → HALT
if system.degraded_mode and now() - degraded_mode_entered_at > 60:
    log_critical("degraded_mode_timeout", {
        "duration": now() - degraded_mode_entered_at,
        "state": state
    })

    # IN_POSITION: Stop 유지하고 HALT
    # FLAT: 바로 HALT
    if state == IN_POSITION:
        # Stop 확인 후 HALT
        if stop_status != ACTIVE:
            # Stop 복구 시도
            place_stop_loss(...)

        HALT(reason="degraded_mode_timeout_with_position")
    else:
        HALT(reason="degraded_mode_timeout")
```

**복구**:
```python
if ws_heartbeat_ok and ws_event_drop_count == 0:
    if system.degraded_mode:
        log_info("ws_recovered", "exiting_degraded_mode")

        system.degraded_mode = False

        # 5분 COOLDOWN 후 진입 재개
        entry_cooldown_until = now() + 300

        log_warning("entry_cooldown", {
            "duration": 300,
            "reason": "ws_recovery_safety"
        })
```

**정리**:
- **정상**: Event-driven만, REST 확정 금지
- **DEGRADED**: Reconcile 강화, 진입 차단, 60초 후 HALT
- **목적**: DEGRADED에서도 '정합성 회복'이지 '상태 확정'이 아님

### Stop Loss 갱신 규칙 (Rate Limit 방지)

**문제**: 추가 체결마다 무조건 Cancel+Place → SL 공백 + Rate limit 소진

**헌법 규칙**:

```python
# Stop 갱신 상태 추적
last_stop_update_at = 0  # 마지막 갱신 시각
stop_order_id = None     # 현재 Stop 주문 ID
current_stop_qty = 0     # 현재 Stop 수량

def update_stop_loss_if_needed(current_stop_qty, new_qty, stop_order_id):
    """
    Stop Loss 조건부 갱신 (Amend 우선, Debounce 적용)

    목적:
    - SL 공백(gap) 제거: Amend API 사용 시 주문 유지
    - Rate limit 소진 방지: 20% threshold + 2초 debounce
    """

    # 1. 수량 변화 계산
    delta_qty = abs(new_qty - current_stop_qty)
    delta_ratio = delta_qty / current_stop_qty if current_stop_qty > 0 else 1.0

    # 2. Threshold 확인 (20% 미만 변화는 무시)
    if delta_ratio < 0.20:
        return  # 갱신 안 함

    # 3. Debounce 확인 (최소 2초 간격)
    if now() - last_stop_update_at < 2.0:
        return  # 갱신 안 함

    # 4. 갱신 방식 우선순위
    try:
        # 우선순위 1: Amend (qty만 수정, SL 공백 없음)
        amend_stop_loss(
            order_id=stop_order_id,
            qty=new_qty
        )
        last_stop_update_at = now()
        current_stop_qty = new_qty

        log_info("stop_amended", {
            "old_qty": current_stop_qty,
            "new_qty": new_qty,
            "delta_ratio": delta_ratio
        })

    except AmendNotSupported:
        # 우선순위 2: Cancel+Place (Amend 불가 시만)
        # 이 경우에도 debounce 강제 (위에서 확인됨)

        cancel_stop_loss(stop_order_id)

        stop_order_id = place_stop_loss(
            qty=new_qty,
            stop_price=calculate_stop_price(position.entry_price, position.direction),
            reduceOnly=True,
            positionIdx=0
        )

        last_stop_update_at = now()
        current_stop_qty = new_qty

        log_warning("stop_replaced", {
            "reason": "amend_not_supported",
            "old_qty": current_stop_qty,
            "new_qty": new_qty
        })
```

**보호 장치**:
1. **20% Threshold**: 미세 변화 무시 → Rate limit 절약
2. **2초 Debounce**: 연속 갱신 차단 → Rate limit 절약
3. **Amend 우선**: SL 공백 제거 → 급변동 보호
4. **Cancel+Place Fallback**: Amend 실패 시만 → 하위 호환성

**Trade-off**:
- **Stop 갱신 지연**: 20% 미만 수량 변화는 무시됨
- **수용 가능**: 손실 예산은 stop_distance로 제어되며, 수량 미세 조정은 청산거리에 미미한 영향

---

## 2.6. WebSocket Reconcile (상태 불일치 방지)

**문제**: WebSocket은 끊기고, 메시지는 드랍된다 (가능성 아님, 필연)

**헌법 규칙**: WebSocket Primary + REST Reconcile (저빈도 합치기)

### Reconcile 규칙

**금지**:
```python
# ❌ REST 매 tick 폴링
for tick in loop:
    orders = get_orders_rest()  # 매번 호출 → rate limit 낭비
```

**올바른 방식**:
```python
# ✅ WS Primary + 저빈도 Reconcile
websocket_healthy = True
last_reconcile = now()

for tick in loop:
    # Primary: WebSocket events
    if websocket_healthy:
        events = process_ws_events()

        # Reconcile: 10~30초마다 1회 (불일치 감지)
        if now() - last_reconcile > 30:
            rest_orders = get_orders_rest()
            rest_position = get_position_rest()

            # 불일치 감지
            if ws_state != rest_state:
                # WS 상태를 REST로 덮어쓰기 (REST = Source of Truth)
                state = reconcile(ws_state, rest_state)
                log_warning("WS/REST mismatch", diff)

            last_reconcile = now()

    # Fallback: WS 끊김
    else:
        # WS 복구 시도 + REST로 최소 동작
        rest_orders = get_orders_rest()
        rest_position = get_position_rest()
```

### Reconcile 주기

- **IN_POSITION**: 10초마다 (포지션 있으면 자주)
- **FLAT**: 30초마다
- **ENTRY_PENDING / EXIT_PENDING**: 5초마다 (중요 상태)

### 불일치 처리 (히스테리시스 필수)

**우선순위**: REST = Source of Truth (WS 메시지 드랍 가능성 때문)

**하지만**: 즉시 덮어쓰기는 플립플롭 위험 → **히스테리시스 적용**

```python
# 불일치 추적
mismatch_count = 0
last_reconcile_override = None
reconcile_cooldown_until = None

def on_reconcile():
    # COOLDOWN 중이면 건너뛰기
    if reconcile_cooldown_until and now() < reconcile_cooldown_until:
        return

    rest_state = get_state_from_rest()

    # 불일치 감지
    if ws_state != rest_state:
        mismatch_count += 1

        # 연속 3회 불일치 시 덮어쓰기
        if mismatch_count >= 3:
            log_critical("ws_rest_mismatch_confirmed", {
                "ws_state": ws_state,
                "rest_state": rest_state,
                "consecutive_count": mismatch_count
            })

            # REST로 덮어쓰기
            state = rest_state
            mismatch_count = 0

            # 5초 COOLDOWN (재확인 금지)
            last_reconcile_override = now()
            reconcile_cooldown_until = now() + 5

    else:
        # 일치하면 카운트 리셋
        mismatch_count = 0
```

**예시**:

```python
# Case 1: 일시적 불일치 (플립플롭 방지)
WS: IN_POSITION, REST: None (지연)  # count=1
WS: IN_POSITION, REST: IN_POSITION  # count=0 (리셋)
→ 상태 유지 (덮어쓰기 안 함)

# Case 2: 진짜 불일치 (감지)
WS: IN_POSITION, REST: None  # count=1
WS: IN_POSITION, REST: None  # count=2
WS: IN_POSITION, REST: None  # count=3
→ state = FLAT (덮어쓰기)
→ 5초 COOLDOWN
```

### WebSocket DEGRADED Mode (방어 모드)

**문제**: WS 단절은 "정상 운용"이 아닌데, 단순 주기 단축은 REST budget 폭주

**헌법 규칙**:

```python
# WS Health 추적
ws_heartbeat_timeout = 10          # heartbeat 10초 이상 없으면
ws_event_drop_count = 0            # 연속 이벤트 드랍 감지
system.degraded_mode = False       # DEGRADED mode 플래그

# DEGRADED Mode 진입 조건
if ws_heartbeat_timeout_exceeded or ws_event_drop_count >= 3:
    log_critical("entering_degraded_mode", {
        "reason": "ws_disconnection",
        "heartbeat_timeout": ws_heartbeat_timeout_exceeded,
        "event_drops": ws_event_drop_count
    })

    system.degraded_mode = True

    # 1. 신규 진입 차단 (FLAT일 때만)
    if state == FLAT:
        entry_allowed = False
        log_warning("entries_blocked", "degraded_mode")

    # 2. 포지션 있을 때만 aggressive reconcile
    if state == IN_POSITION:
        reconcile_interval = 1.0      # 1초 (포지션만)
        rest_calls_allowed = 2        # position/list + order/realtime만

        log_warning("aggressive_reconcile_enabled", {
            "interval": reconcile_interval,
            "reason": "position_protection"
        })
    else:
        # FLAT/PENDING: 기존 주기 유지
        reconcile_interval = 30.0

# WS 복구 시
if ws_heartbeat_ok and ws_event_drop_count == 0:
    if system.degraded_mode:
        log_info("ws_recovered", "exiting_degraded_mode")

        system.degraded_mode = False

        # 5분 COOLDOWN 후 진입 재개
        entry_cooldown_until = now() + 300

        log_warning("entry_cooldown", {
            "duration": 300,
            "reason": "ws_recovery_safety"
        })
```

**보호 장치**:
1. **진입 차단**: WS 불안정 시 FLAT에서 Entry 금지 → 사고 방지
2. **Selective Aggressive**: IN_POSITION일 때만 1초 reconcile → REST budget 절약
3. **복구 COOLDOWN**: WS 복구 후 5분 대기 → 재단절 방지

**Trade-off**:
- **진입 기회 손실**: WS 단절 중 FLAT이면 Entry 차단
- **수용 가능**: 포지션 보호 > 진입 기회

---

## 3. Bybit Inverse Futures 특성 (계산 기준)

### 3.1 BTC-Denominated + Position Mode Contract

Bybit Inverse Futures는 **BTC로 작동**한다.

- Balance: BTC
- Margin: BTC
- Fee: BTC
- PnL: BTC

**USD는 표시/목표 측정용으로만 사용.**

모든 계산은 **BTC 기준**으로 하고, USD는 마지막에 환산.

#### Position Mode (강제 계약)

**Bybit Position Mode**: **One-way only** (Hedge 금지)

**이유**:
- State Machine은 "포지션 1개"를 전제
- Hedge 모드면 롱/숏 동시 보유 가능 → State(FLAT/IN_POSITION) 붕괴

**헌법 규칙**: `positionIdx=0` 강제로 One-way 동작 보장

```python
# 모든 주문에 positionIdx=0 강제
positionIdx = 0  # One-way unified

# Entry 주문
place_order(..., positionIdx=0)

# Stop 주문
place_order(..., positionIdx=0)

# 포지션/주문 조회
get_position(..., positionIdx=0)
get_orders(..., positionIdx=0)
```

**문자열 검증은 보조 진단(로그)으로만**:
```python
# 시스템 시작 시 경고용 (HALT 안 함)
def check_position_mode():
    mode = bybit_adapter.get_position_mode(category="inverse", symbol="BTCUSD")

    if mode != "MergedSingle":
        log_warning("position_mode_unexpected", {
            "mode": mode,
            "expected": "MergedSingle"
        })
        # HALT은 안 함, positionIdx=0 강제로 운용
```

**금지**:
```python
# ❌ 문자열 의존 검증 (API 버전 변경 시 시스템 중단)
if mode != "MergedSingle":
    raise SystemError("Position mode must be One-way")

# ❌ positionIdx 누락/잘못된 값
place_order(..., positionIdx=1)  # Hedge Long
place_order(..., positionIdx=2)  # Hedge Short
place_order(...)  # positionIdx 누락
```

**이유**:
- Exchange가 문자열을 변경해도 시스템은 One-way로 동작
- `positionIdx=0` 강제로 State Machine 일관성 보장
- 문자열 검증 실패로 시스템 시작 못 하는 사고 방지

---

### 3.2 Inverse PnL Formula (Direction별 정확한 공식)

**Bybit Inverse Futures PnL**:
```
PnL (BTC) = Position Size (contracts) × (1/Entry Price - 1/Exit Price)

Long:
  PnL = contracts × (1/entry - 1/exit)

Short:
  PnL = contracts × (1/exit - 1/entry)
```

**Stop Price 정의 (Direction별)**:
```
Long:
  stop_price = entry_price × (1 - stop_distance_pct)
  (가격 하락 시 손절)

Short:
  stop_price = entry_price × (1 + stop_distance_pct)
  (가격 상승 시 손절)
```

**Stop Loss 발동 시 손실**:

**Long**:
```
stop_price = entry × (1 - d)

loss_btc = contracts × (1/entry - 1/stop_price)
         = contracts × (1/entry - 1/(entry×(1-d)))
         = contracts × (1/entry) × (1 - 1/(1-d))
         = contracts × (1/entry) × (-d / (1-d))

where d = stop_distance_pct
```

**Short**:
```
stop_price = entry × (1 + d)

loss_btc = contracts × (1/entry - 1/stop_price)
         = contracts × (1/entry - 1/(entry×(1+d)))
         = contracts × (1/entry) × (1 - 1/(1+d))
         = contracts × (1/entry) × (d / (1+d))

where d = stop_distance_pct
```

**근사 (d < 0.05 일 때만)**:
```
Long:  loss_btc ≈ (contracts / entry) × d
Short: loss_btc ≈ (contracts / entry) × d
```

**d ≥ 0.05 (5%) 이상**일 때는 정확한 공식 사용 필수.

---

### 3.3 Stop Distance 출처 계약 (Grid Strategy)

**문제**: stop_distance_pct를 어디서 받는지 불명확 → 구현자 마음대로

**헌법 규칙**: Grid Strategy는 stop_distance_pct를 **grid_spacing_pct 기반**으로 결정

### 출처

**Signal이 제공해야 하는 것**:
```python
@dataclass
class Signal:
    type: SignalType  # LONG / SHORT / NONE
    direction: Direction
    entry_price: float
    grid_spacing_pct: float  # 필수! (예: 0.02 = 2%)
    expected_profit_usd: float
```

**Grid spacing이 없으면 REJECT**:
```python
if signal.grid_spacing_pct is None or signal.grid_spacing_pct <= 0:
    REJECT(reason="grid_spacing_pct missing")
```

### Stop Distance 계산 규칙 (고정)

```python
# ✅ Grid spacing 기반 자동 계산
grid_spacing_pct = signal.grid_spacing_pct

# Stop은 Grid 간격의 1.5배 (구조 붕괴 감지)
stop_distance_pct_raw = grid_spacing_pct * 1.5

# Clamp (2% ~ 6%)
stop_distance_pct = clamp(stop_distance_pct_raw, min=0.02, max=0.06)

# Fallback (grid_spacing 불가능한 경우만)
if grid_spacing_pct is None:
    stop_distance_pct = 0.03  # 3% default
```

**금지**:
```python
# ❌ Signal이 stop_distance_pct를 직접 제공
signal.stop_distance_pct = 0.05  # 임의 값 불가

# ❌ 고정값 하드코딩
stop_distance_pct = 0.03  # Grid spacing 무시 불가
```

**이유**:
- Grid Strategy는 Grid 간격과 Stop이 연동되어야 함
- Stop이 Grid보다 좁으면 정상 변동에도 손절
- Stop이 Grid보다 너무 넓으면 손실 예산 초과

---

### 3.4 Position Sizing (Direction별 정확한 공식)

**목표**: `max_loss_btc`를 초과하지 않는 최대 contracts

**정확한 역산 (Direction별)**:

**Long**:
```
# max_loss_btc = contracts × (1/entry) × (-d/(1-d))
# where d = stop_distance_pct

contracts = max_loss_btc / ((1/entry) × (-d/(1-d)))
          = (max_loss_btc × entry × (1-d)) / (-d)

# 간소화 (음수 제거):
contracts = (max_loss_btc × entry × (1 - stop_distance_pct)) / stop_distance_pct
```

**Short**:
```
# max_loss_btc = contracts × (1/entry) × (d/(1+d))

contracts = max_loss_btc / ((1/entry) × (d/(1+d)))
          = (max_loss_btc × entry × (1+d)) / d

# 간소화:
contracts = (max_loss_btc × entry × (1 + stop_distance_pct)) / stop_distance_pct
```

**근사 공식** (d < 0.03일 때만 허용, Long/Short 동일):
```
contracts ≈ (max_loss_btc × entry) / stop_distance_pct
```

**구현 규칙**:
- stop_distance_pct < 0.03 (3%): 근사 공식 사용 가능
- stop_distance_pct ≥ 0.03: Direction별 정확한 공식 사용 필수

---

### 3.4 Margin Calculation

**Position Value (BTC)**:
```
position_value_btc = contracts / entry_price
```

**Required Margin (BTC)**:
```
required_margin_btc = position_value_btc / leverage
```

**Fee Buffer (BTC)** (Entry + Exit):
```
fee_buffer_btc = position_value_btc × fee_rate × 2
```

**Feasibility Check**:
```
if required_margin_btc + fee_buffer_btc > equity_btc:
    REJECT
```

**USD 환산** (로깅/표시용만):
```
required_margin_usd = required_margin_btc × entry_price
equity_usd = equity_btc × entry_price
```

### Tick/Lot Size 준수 (주문 거절 방지)

**문제**: 계산된 contracts/price가 거래소 제약 위반 → "Invalid qty/price" 거절

**헌법 규칙**:

```python
# 1. Instrument Info 조회 (캐싱)
instrument_info = exchange.get_instrument_info("BTCUSD")
qty_step = instrument_info.qty_step      # 예: 1 (최소 수량 단위)
tick_size = instrument_info.tick_size    # 예: 0.5 (최소 가격 단위)

# 2. Lot size 보정 (필수)
contracts = floor(contracts / qty_step) * qty_step

# 3. Price tick size 보정
entry_price = round_to_tick(entry_price, tick_size)

# round_to_tick 함수
def round_to_tick(price, tick_size):
    """가격을 tick_size 단위로 반올림"""
    return round(price / tick_size) * tick_size

# 4. 보정 후 재검증 (필수)

# 4-1. Margin feasibility 재확인
required_margin_btc = (contracts / entry_price) / leverage
fee_buffer_btc = (contracts / entry_price) × fee_rate × 2

if required_margin_btc + fee_buffer_btc > equity_btc:
    REJECT(reason="margin_insufficient_after_rounding")

# 4-2. Liquidation gate 재확인
liq_distance_pct = calculate_liquidation_distance(
    entry_price=entry_price,
    contracts=contracts,
    leverage=leverage,
    direction=direction
)

if liq_distance_pct < min_required_liq_distance[stage]:
    REJECT(reason="liquidation_too_close_after_rounding")

# 4-3. 최소 수량 검증
if contracts < qty_step:
    REJECT(reason="qty_below_minimum")

# 5. 검증 통과 후 주문
place_order(
    symbol="BTCUSD",
    qty=contracts,      # Lot size 보정됨
    price=entry_price,  # Tick size 보정됨
    ...
)
```

**보호 장치**:
1. **Lot size 보정**: qtyStep 단위로 floor → 주문 거절 방지
2. **Tick size 보정**: tickSize 단위로 round → 주문 거절 방지
3. **재검증 필수**: 보정 후 margin/liquidation 재확인 → 예상치 못한 REJECT 방지
4. **최소 수량 검증**: qty < qtyStep → REJECT (주문 자체 불가)

**Trade-off**:
- **보정으로 인한 수량 감소**: floor(contracts) → 실제 손실 < max_loss_btc
- **수용 가능**: 보수적 접근 (손실 예산 범위 내)

---

### 3.5 Leverage와 Loss Budget의 독립성 (중요)

**핵심 원칙**: Stop-loss 손실은 레버리지와 무관

**이유**:
- Stop Loss는 가격 변동에 의한 손실 (청산 아님)
- Leverage는 **margin 크기**와 **청산 거리**에만 영향
- Loss budget (max_loss_btc)은 Stop 발동 시 손실 = PnL 계산 기반
- **PnL 계산에는 leverage가 없음**

**올바른 사용**:
```
Loss Budget Sizing:
  - contracts = f(max_loss_btc, stop_distance_pct, entry_price)
  - Leverage 사용 안 함 ✓

Margin Check:
  - required_margin_btc = (contracts / entry) / leverage
  - Leverage 사용 ✓

Liquidation Check:
  - liq_distance = f(leverage, entry, contracts)
  - Leverage 사용 ✓
```

**금지**:
```python
# ❌ 잘못된 예시
contracts = (max_loss_btc × entry × leverage) / stop_distance_pct
# Leverage를 loss sizing에 넣으면 손실 예산 붕괴
```

---

### 3.6 Margin과 Loss Budget 충돌 해결

**문제**: Loss budget으로 계산한 contracts가 margin 부족으로 REJECT

**원인**: 소액 계좌($100)에서 loss budget 12% + 3x leverage는 계좌 대부분을 margin으로 사용

**해결**:
```python
# Step 1: Margin 기준 최대 contracts 계산
available_btc = equity_btc × 0.8  # 80%만 사용 (buffer)
max_position_value_btc = available_btc × leverage
max_contracts_from_margin = max_position_value_btc × entry_price

# Step 2: Loss budget 기준 최대 contracts 계산
max_contracts_from_loss = (max_loss_btc × entry × (1-d)) / d

# Step 3: 둘 중 작은 값
contracts = min(max_contracts_from_margin, max_contracts_from_loss)
```

**이유**: Margin 부족으로 주문 실패하는 것보다, 작은 포지션이라도 진입하는 게 낫다.

---

## 4. 절대 금지 사항 (Real Trading Killers)

### 4.1 Blocking Wait (wait_for_fill)

**금지**:
```python
# ❌ 절대 금지
order = place_order(...)
result = wait_for_fill(order_id, timeout=300)  # 5분 대기
```

**이유**:
- 5분간 Emergency Check 불가
- 급락/지연/오류 발생 시 대응 불가

**올바른 방식**:
```python
# ✅ 비동기 상태 전환 (이벤트 기반)
order = place_order(...)
state = ENTRY_PENDING
pending_order_id = order.order_id
order_placed_at = now()

# 상태 확정은 이벤트로만
def on_execution_event(event):
    if event.order_id == pending_order_id:
        if event.type == "FILL":
            state = IN_POSITION
        elif event.type == "CANCEL":
            state = FLAT
        elif event.type == "REJECT":
            state = FLAT

# Timeout 처리 (주문 취소만, 상태 확정 아님)
if state == ENTRY_PENDING and now() - order_placed_at > 300:
    cancel_order(pending_order_id)
    # state 전환은 CANCEL 이벤트 수신 후
```

**REST는 Reconcile용**:
```
"REST는 reconcile용 스냅샷이며, state transition의 trigger가 아니다."

"단, WS DEGRADED 상태에서는 최소 동작을 위해 제한된 REST 확인이 허용되며,
이때도 '확정'이 아니라 '불일치 해소' 목적이다."
```

---

### 4.2 God Object (Orchestrator가 모든 책임)

**금지**:
```python
# ❌ 500줄짜리 Orchestrator
class Orchestrator:
    def run_tick(self):
        # Snapshot 업데이트
        # Emergency 체크
        # Signal 생성
        # Stage 판정
        # Risk gates (7개)
        # Sizing
        # Order 실행
        # Metrics 업데이트
        # ...
```

**올바른 방식**:
```python
# ✅ 책임 분리
class Orchestrator:
    def __init__(self):
        self.state_machine = StateMachine()
        self.emergency = EmergencyChecker()
        self.signal_engine = SignalEngine()
        self.risk_gate = RiskGate()
        self.sizer = PositionSizer()
        self.executor = OrderExecutor()

    def run_tick(self):
        snapshot = self._update_snapshot()

        if self.emergency.should_halt(snapshot):
            self.state_machine.halt()
            return

        self._handle_execution_events()

        if self.state_machine.state == IN_POSITION:
            self._manage_position()
        elif self.state_machine.state == FLAT:
            self._try_entry(snapshot)
```

---

### 4.3 USD-based Calculation

**금지**:
```python
# ❌ USD로 계산
required_margin_usd = contracts / leverage
if required_margin_usd <= balance_usd:
    place_order(...)
```

**이유**: BTC 가격 변동 시 계산 오류

**올바른 방식**:
```python
# ✅ BTC로 계산
position_value_btc = contracts / entry_price
required_margin_btc = position_value_btc / leverage

if required_margin_btc <= equity_btc:
    place_order(...)

# USD는 로깅용
margin_usd = required_margin_btc × entry_price
```

---

### 4.4 State Bypass (상태 건너뛰기)

**금지**:
```python
# ❌ ENTRY_PENDING 건너뛰기
order = place_order(...)
state = IN_POSITION  # 체결 확인 없이 바로 전환
```

**이유**: 부분체결/미체결 시 포지션 상태 불일치

**올바른 방식**:
```python
# ✅ ENTRY_PENDING 거침
order = place_order(...)
state = ENTRY_PENDING

# 다음 tick에서 체결 확인 후 전환
if state == ENTRY_PENDING and order.filled:
    state = IN_POSITION
```

---

### 4.5 Stop Loss 주문 계약 (Conditional Order 고정)

**문제**: `reduceOnly + stopLoss` 파라미터 혼용 → Bybit Inverse에서 거절됨

**헌법 규칙**: Account Builder는 **방식 B(Conditional Order) 고정**

#### Entry와 Stop 주문 분리

**Entry 주문**:
```python
# Entry 주문 (reduceOnly=False, stopLoss 파라미터 없음)
entry_order = bybit_adapter.place_order(
    category="inverse",
    symbol="BTCUSD",
    side="Buy",  # or "Sell"
    orderType="Limit",
    qty=contracts,
    price=entry_price,

    # reduceOnly는 설정 안 함 (기본: False)
    positionIdx=0,
    orderLinkId=client_order_id
)
```

**Stop Loss 주문 (별도)**:
```python
# Stop Loss 주문 생성 (필수 파라미터 포함)
def place_stop_loss(position_qty, stop_price, direction, signal_id):
    """
    Stop Loss 주문 계약 (Conditional Order 방식 — Bybit v5)

    필수 파라미터:
    - triggerPrice: Stop trigger price (필수)
    - triggerDirection: 1 (rising), 2 (falling) (필수)
    - triggerBy: "LastPrice" or "MarkPrice" (기본: LastPrice)
    - reduceOnly: True (포지션 감소만)
    - positionIdx: 0 (One-way mode)
    - orderType: "Market" (트리거 시 즉시 체결)
    - orderLinkId: deterministic ID

    금지:
    - Entry 주문에 stopLoss/takeProfit 파라미터 혼용
    - triggerPrice 누락 (Conditional의 핵심)
    - reduceOnly=False
    - positionIdx 누락
    """
    # Direction별 side/triggerDirection 결정
    if direction == "LONG":
        stop_side = "Sell"
        trigger_direction = 2  # Falling (가격 하락 시 트리거)
    else:  # SHORT
        stop_side = "Buy"
        trigger_direction = 1  # Rising (가격 상승 시 트리거)

    # Stop client_order_id
    stop_client_order_id = f"{signal_id}_stop_{stop_side}"

    # Bybit v5 Conditional Stop Market 주문
    stop_order = bybit_adapter.place_order(
        category="inverse",
        symbol="BTCUSD",
        side=stop_side,
        orderType="Market",  # 트리거 시 시장가 청산
        qty=position_qty,

        # Conditional trigger (필수)
        triggerPrice=str(stop_price),  # Trigger price (string)
        triggerDirection=trigger_direction,  # 1: rising, 2: falling
        triggerBy="LastPrice",  # or "MarkPrice" (기본: LastPrice)

        # Position reduction (필수 속성)
        reduceOnly=True,      # 포지션 감소만 허용 (증가 금지)
        positionIdx=0,        # One-way mode

        # Idempotency
        orderLinkId=stop_client_order_id
    )

    return stop_order
```

#### Stop 관리 규칙 (헌법 승격)

**1. SL 공백 금지 (Amend 우선)**:
```python
# Amend API 우선 (주문 유지, 공백 없음)
try:
    amend_stop_loss(
        order_id=stop_order_id,
        qty=new_qty
    )
except AmendNotSupported:
    # Amend 불가 시에만 Cancel+Place
    cancel_stop_loss(stop_order_id)
    stop_order_id = place_stop_loss(...)
```

**2. Debounce/Threshold (Rate Limit 절약)**:
```python
# 20% threshold: 수량 변화 < 20% → 갱신 안 함
delta_ratio = abs(new_qty - current_stop_qty) / current_stop_qty
if delta_ratio < 0.20:
    return  # 갱신 안 함

# 2초 debounce: 최소 2초 간격
if now() - last_stop_update_at < 2.0:
    return  # 갱신 안 함
```

**3. Stop 필수 존재 감시**:
```python
# IN_POSITION이면 Stop 필수
if state == IN_POSITION:
    if stop_status == MISSING:
        # 즉시 복구 시도
        try:
            place_stop_loss(...)
            stop_status = ACTIVE
        except:
            stop_recovery_fail_count += 1
            if stop_recovery_fail_count >= 3:
                stop_status = ERROR
                HALT(reason="stop_loss_unrecoverable")
```

**금지**:
```python
# ❌ Entry 주문에 stopLoss 파라미터 + reduceOnly 혼용
place_order(..., stopLoss=price, reduceOnly=True)
# → Bybit: "Invalid parameter" 거절

# ❌ Stop 공백 방치
# Cancel+Place 시 "잠깐 비는 구간" 생기는 순간 계좌 터질 수 있음

# ❌ 모든 PARTIAL_FILL마다 Stop 갱신
# → Rate limit 지옥

# ❌ IN_POSITION인데 Stop 없는 상태 방치
# → 급변동 시 노출
```

**이유**:
- PARTIAL_FILL에서 Stop qty 증감(amend) 필요
- Stop/Entry 라이프사이클 분리 (상태도 분리)
- Rate limit/SL 공백 방지 설계 가능

---

## 5. Emergency Priority (최우선 규칙)

Emergency Check는 **Signal보다 먼저**.

**순서**:
```
1. Snapshot Update
2. Emergency Check ← 여기서 HALT 판단
3. Execution Events
4. Signal Decision ← Emergency 통과한 경우만
```

**Emergency 조건**:
- `price_drop_1m <= -10%` → HALT
- `price_drop_5m <= -20%` → HALT
- `exchange_latency >= 5.0s` → Cancel + Block
- `equity_usd < $80` → HALT (Manual reset)
- Liquidation warning → HALT (Manual reset)

**HALT 시 동작**:
1. 모든 pending orders 취소
2. 신규 진입 차단
3. 기존 포지션: Stop Loss 유지 (강제 청산 안 함)

---

## 6. Fee Rate (Dynamic, not Hardcoded)

**금지**:
```python
# ❌ 하드코딩
maker_fee_rate = 0.0001
taker_fee_rate = 0.0006
```

**이유**: Bybit는 VIP 등급/지역/프로모션에 따라 수수료 변동

**올바른 방식**:
```python
# ✅ Config + API + Fallback
# config/fee_config.yaml
bybit_inverse_fees:
  # Default (VIP 0 기준, 2026-01 기준)
  default_maker_rate: 0.0002
  default_taker_rate: 0.00055

  # API 조회 설정
  use_api_fee_rate: true
  api_cache_duration: 3600  # 1시간 캐시

  # Fallback 정책
  fallback_on_api_failure: true

# 초기화 시
def get_fee_rates():
    # Step 1: API 조회 시도
    if config.use_api_fee_rate:
        try:
            fee_info = bybit_adapter.get_fee_rate(
                category="inverse",  # 필수: inverse category 명시
                symbol="BTCUSD"
            )
            maker_rate = fee_info.maker_fee_rate
            taker_rate = fee_info.taker_fee_rate

            # 캐시 저장
            cache.set("fee_rates", {
                "maker": maker_rate,
                "taker": taker_rate,
                "cached_at": now()
            }, ttl=config.api_cache_duration)

            return maker_rate, taker_rate

        except APIError as e:
            # Step 2: 캐시 확인
            cached = cache.get("fee_rates")
            if cached and config.fallback_on_api_failure:
                return cached["maker"], cached["taker"]

            # Step 3: Config default
            return config.default_maker_rate, config.default_taker_rate

    # API 사용 안 함
    return config.default_maker_rate, config.default_taker_rate
```

**Bybit API Endpoint**:
```
GET /v5/account/fee-rate
Parameters:
  - category: "inverse" (필수)
  - symbol: "BTCUSD"
```

**Fallback 우선순위**:
1. API 조회 (실시간)
2. Cache (1시간 이내)
3. Config default (VIP 0 기준)

**금지**:
- API 실패 시 HALT ❌ (수수료는 치명적 아님)
- 캐시 없이 매번 API 호출 ❌ (rate limit 낭비)

---

### 6.2 Fee Post-Trade Verification (필수 안전장치)

**목적**: 예상 수수료와 실제 수수료 차이를 감지하여 수수료 스파이크 대응

**문제**:
- Maker 주문이었는데 Taker로 체결됨 (timeout)
- Fee rate가 체결 시점에 변경됨
- Slippage로 인한 notional 변화

**Bybit Inverse Fee 계산 (단위 명시)**:

**핵심 특성**:
- Bybit Inverse Futures: **1 contract = 1 USD notional**
- Fee는 BTC로 지불되지만, USD notional 기준으로 계산됨
- `fee_btc = (contracts × fee_rate) / price`

**규칙**:

```python
# Entry 시점: 예상 수수료 저장
def on_entry_order_placed(order, contracts, fee_rate, entry_price):
    # Inverse: contracts = USD notional
    estimated_fee_notional_usd = contracts * fee_rate  # USD 기준

    # BTC로 변환 (예상)
    estimated_fee_btc = estimated_fee_notional_usd / entry_price

    # 저장 (USD 기준으로 비교)
    session.estimated_fee_usd = estimated_fee_notional_usd
    session.estimated_fee_rate = fee_rate

# 체결 완료 시점: 실제 수수료 검증
def on_fill(fill_event):
    # Bybit fill event에서 실제 수수료 (BTC)
    actual_fee_btc = fill_event.fee_paid

    # USD로 변환 (비교용)
    actual_fee_usd = actual_fee_btc * fill_event.exec_price

    estimated_fee_usd = session.estimated_fee_usd

    # Fee spike 감지 (USD 기준)
    fee_ratio = actual_fee_usd / estimated_fee_usd

    if fee_ratio > 1.5:  # 50% 초과
        log_warning("fee_spike_detected", {
            "estimated_usd": estimated_fee_usd,
            "actual_usd": actual_fee_usd,
            "ratio": fee_ratio,
            "expected_rate": session.estimated_fee_rate,
            "fill_price": fill_event.exec_price
        })

        # 대응: 24시간 Entry tightening
        session.fee_spike_mode = True
        session.fee_spike_until = now() + timedelta(hours=24)

    # Trade log에 필수 기록
    trade_log["fee"] = {
        "estimated_usd": estimated_fee_usd,
        "actual_usd": actual_fee_usd,
        "fee_ratio": fee_ratio,
        "spike_detected": fee_ratio > 1.5
    }
```

**Fee Spike Mode 대응**:

```python
# EV Gate에 반영
if session.fee_spike_mode and now() < session.fee_spike_until:
    # EV gate 배수 증가 (더 보수적으로)
    ev_gate_multiplier = stage_config.ev_gate_k * 1.5

    # 예: Stage 1 기본 K=2 → K=3
    # expected_profit_usd >= estimated_fee_usd * 3
```

**Spike Mode 해제**:
```python
# 24시간 경과 시 자동 해제
if now() >= session.fee_spike_until:
    session.fee_spike_mode = False
```

**금지**:
- Fee spike 발생해도 무시 ❌
- Trade log에 actual fee 기록 안 함 ❌
- Maker timeout → Taker 전환 추적 안 함 ❌

---

## 7. Sizing Double-Check (Margin vs Loss)

**필수**: Sizing 후 Margin feasibility 재확인

```python
# Step 1: Loss budget 기준 contracts 계산
contracts_from_loss = (max_loss_btc × entry × (1-d)) / d

# Step 2: Margin 기준 최대 contracts
available_btc = equity_btc × 0.8
max_position_btc = available_btc × leverage
contracts_from_margin = max_position_btc × entry

# Step 3: 둘 중 작은 값
contracts = min(contracts_from_loss, contracts_from_margin)

# Step 4: Margin 재확인 (필수)
required_margin = (contracts / entry) / leverage
fee_buffer = (contracts / entry) × fee_rate × 2

if required_margin + fee_buffer > equity_btc:
    REJECT  # 이론적으로 발생하지 않아야 하지만, 안전장치
```

---

### 7.5 Liquidation Distance Gate (강제 안전장치)

**목적**: Stop loss 전에 청산 발생을 방지

**문제**:
- Stop distance 2%, Leverage 3x → 청산 거리 ~7% (안전)
- 하지만 Stop distance 6%, Leverage 3x + 큰 contracts → 청산 거리 5% 가능 (위험)
- **Stop loss 발동 전 청산 발생 → 손실 예산 무력화**

**헌법 규칙**: Sizing 완료 후 **청산 거리 필수 검증**

```python
# Sizing 완료 (Section 7)
contracts = min(contracts_from_loss, contracts_from_margin)

# Gate: Liquidation distance 계산 및 강제 확인
liq_distance_pct = calculate_liquidation_distance(
    entry_price=entry_price,
    contracts=contracts,
    leverage=leverage,
    direction=direction,
    equity_btc=equity_btc
)

# Stage별 동적 기준 (stop_distance 기반)
liq_distance_multiplier = {
    1: 4.0,  # Stage 1: stop × 4
    2: 3.5,  # Stage 2: stop × 3.5
    3: 3.0   # Stage 3: stop × 3
}

# 최소 절대값 (안전망)
min_absolute_liq_distance = {
    1: 0.15,  # Stage 1: 최소 15%
    2: 0.15,  # Stage 2: 최소 15%
    3: 0.12   # Stage 3: 최소 12%
}

# 동적 기준 계산
min_required_liq_distance = max(
    stop_distance_pct * liq_distance_multiplier[stage],
    min_absolute_liq_distance[stage]
)

# 강제 REJECT
if liq_distance_pct < min_required_liq_distance:
    REJECT(reason=f"liquidation_too_close: {liq_distance_pct:.1%} < {min_required_liq_distance:.1%} (stop={stop_distance_pct:.1%} × {liq_distance_multiplier[stage]})")
```

**Liquidation Distance 계산** (Bybit Inverse):

```python
def calculate_liquidation_distance(entry_price, contracts, leverage, direction, equity_btc):
    """
    Bybit Inverse Futures 청산가 계산

    Bankruptcy Price:
      Long:  entry × leverage / (leverage + 1)
      Short: entry × leverage / (leverage - 1)

    Liquidation Price ≈ Bankruptcy Price (maintenance margin 무시 시)

    Liquidation Distance:
      Long:  (entry - liq_price) / entry
      Short: (liq_price - entry) / entry

    실제 계산 (maintenance margin 포함)은 더 복잡하지만,
    보수적 근사로 최소 기준을 확보함.
    """
    # Simplified (보수적 근사)
    if direction == "LONG":
        # Long: 청산가는 entry보다 낮음
        liq_price_approx = entry_price * leverage / (leverage + 1)
        liq_distance_pct = (entry_price - liq_price_approx) / entry_price
    else:  # SHORT
        # Short: 청산가는 entry보다 높음
        liq_price_approx = entry_price * leverage / (leverage - 1)
        liq_distance_pct = (liq_price_approx - entry_price) / entry_price

    return liq_distance_pct
```

**Leverage별 실제 청산거리** (참고):

```python
# Long
leverage=3: liq_distance ≈ 25% (3/(3+1) = 0.75, 1-0.75 = 25%)
leverage=2: liq_distance ≈ 33% (2/(2+1) = 0.67, 1-0.67 = 33%)

# Short
leverage=3: liq_distance ≈ 50% ((3/(3-1))-1 = 1.5-1 = 50%)
leverage=2: liq_distance ≈ 100% ((2/(2-1))-1 = 2-1 = 100%)
```

**예시 (동적 기준)**:

```python
# Case 1: Stage 1, leverage 3x, LONG, stop 2%
entry = 100000, leverage = 3, direction = LONG, stop_distance = 2%
liq_distance ≈ 25%
min_required = max(2% × 4, 15%) = max(8%, 15%) = 15%
→ PASS (25% > 15%)

# Case 2: Stage 1, leverage 3x, LONG, stop 4%
entry = 100000, leverage = 3, direction = LONG, stop_distance = 4%
liq_distance ≈ 25%
min_required = max(4% × 4, 15%) = max(16%, 15%) = 16%
→ PASS (25% > 16%)

# Case 3: Stage 1, leverage 3x, LONG, stop 6%
entry = 100000, leverage = 3, direction = LONG, stop_distance = 6%
liq_distance ≈ 25%
min_required = max(6% × 4, 15%) = max(24%, 15%) = 24%
→ PASS (25% > 24%)

# Case 4: Stage 3, leverage 2x, LONG, stop 5%
entry = 100000, leverage = 2, direction = LONG, stop_distance = 5%
liq_distance ≈ 33%
min_required = max(5% × 3, 12%) = max(15%, 12%) = 15%
→ PASS (33% > 15%)

# Case 5: Stage 1, leverage 3x, SHORT, stop 3%
entry = 100000, leverage = 3, direction = SHORT, stop_distance = 3%
liq_distance ≈ 50%
min_required = max(3% × 4, 15%) = max(12%, 15%) = 15%
→ PASS (50% > 15%)
```

**Fallback** (청산가 API 실패 시):

```python
# Bybit API GET /v5/position/info 실패 시
# Conservative proxy 사용
if liq_distance_pct is None:
    # 보수적 haircut
    if leverage > 3:
        REJECT(reason="leverage_too_high_without_liq_check")

    if stop_distance_pct > 0.05:
        # 5% 이상 stop + API 실패 → 위험
        contracts *= 0.8  # 20% 감소
        log_warning("liq_distance_unavailable_haircut_applied")
```

**Bybit API 활용** (권장):

```python
# GET /v5/position/info로 예상 청산가 조회 가능
# 하지만 Entry 전이므로 계산으로 근사
#
# 더 정확한 방법:
# 1. Test order (dry-run)로 예상 margin/liq 확인
# 2. 또는 계산식 사용 (위 공식)
```

**금지**:
- 청산 거리 체크 없이 진입 ❌
- Stop distance > Liquidation distance 상황 허용 ❌
- API 실패 시 "대충 괜찮겠지" 진입 ❌

**이유**:
- Stop loss는 "손실 제한" 장치
- 청산은 "계좌 청산" 사고
- Stop 전에 청산 발생 = 손실 예산 무력화

---

## 8. Position Entry/Exit는 Idempotent (중복 방지)

**규칙**: 동일한 주문을 중복 실행해도 1회만 체결

**문제**: 재시도/중복 호출 시 포지션 누적 → 의도치 않은 레버리지 증가

**헌법 규칙**:

### Idempotency Key 생성 (길이/제약 강제)

**문제**: Bybit orderLinkId 제약 (최대 36자, 영숫자+`-_`만 허용) 위반 → 주문 거절

**Signal ID 생성 규칙** (해시 축약):

```python
import hashlib
import re

def generate_signal_id(strategy, bar_close_ts, side):
    """
    Signal ID 생성 (36자 제한 준수)

    구성: {strategy_prefix}_{hash_suffix}_{side_prefix}
    - strategy_prefix: 전략명 앞 4자
    - hash_suffix: SHA1 해시 앞 10자 (충돌 방지)
    - side_prefix: side 앞 1자 (l/s)
    """
    # 원본 (너무 길 수 있음)
    raw = f"{strategy}_{bar_close_ts}_{side}"

    # 해시 축약 (sha1 앞 10자리)
    hash_suffix = hashlib.sha1(raw.encode()).hexdigest()[:10]

    # 축약 ID (최대 약 16자)
    signal_id = f"{strategy[:4]}_{hash_suffix}_{side[:1]}"

    # 예시: "grid_a3f8d2e1c4_l"
    return signal_id

# 예시
strategy = "grid_detailed_strategy"
bar_close_ts = 1705593600
side = "long"

signal_id = generate_signal_id(strategy, bar_close_ts, side)
# → "grid_a3f8d2e1c4_l" (16자)
```

**Client Order ID 생성** (검증 강제):

```python
# 1. 결정적(Deterministic) ID 생성
client_order_id = f"{signal_id}_{direction}"

# 예시
# signal_id = "grid_a3f8d2e1c4_l"
# direction = "Buy"
# → client_order_id = "grid_a3f8d2e1c4_l_Buy" (20자)

# 2. 검증 (강제)
assert len(client_order_id) <= 36, f"orderLinkId too long: {len(client_order_id)}"
assert re.match(r'^[a-zA-Z0-9_-]+$', client_order_id), "Invalid characters in orderLinkId"
```

**entry_price를 제거한 이유**:
- Entry price는 호가/라운딩으로 미세 조정 가능
- 같은 시그널인데 다른 ID 생성 → 중복 주문 위험
- Signal ID에 bar_close_ts가 있어 이미 고유성 확보

**금지**:
```python
# ❌ 랜덤/타임스탬프 ID
client_order_id = f"{uuid4()}"  # 재시도 시 다른 ID → 중복 주문
client_order_id = f"{now()}"    # 매번 바뀜 → 중복 주문

# ❌ Entry price 포함
client_order_id = f"{signal_id}_{entry_price_int}_{direction}"
# entry_price가 50000.5 → 50001 (round up)
# retry 시 50000.5 → 50000 (round down)
# → 다른 ID → 중복 주문

# ❌ 길이 제한 무시
signal_id = f"grid_detailed_strategy_20260118_143022_long"
client_order_id = f"{signal_id}_Buy"
# → len = 49 > 36
# → Bybit: "Invalid orderLinkId"
# → 모든 주문 거절
```

**재시도 규칙**:
```python
# 동일 Signal → 동일 client_order_id (재시도 포함)
# 새 Signal → 새 bar_close_ts → 새 client_order_id
```

### 재시도 규칙

```python
# 주문 실패 시 재시도
try:
    order = place_order(
        symbol="BTCUSD",
        side="Buy",
        qty=contracts,
        price=entry_price,
        client_order_id=client_order_id  # 동일 ID 유지
    )
except DuplicateOrderError:
    # Bybit가 중복 감지 → 정상 (이미 주문됨)
    existing_order = get_order_by_client_id(client_order_id)
    # 기존 주문 상태 확인
    if existing_order.status == "Filled":
        state = IN_POSITION
    elif existing_order.status == "New":
        state = ENTRY_PENDING
```

### Client Order ID 저장

```python
# Session State에 저장
session.pending_order = {
    "order_id": order.order_id,
    "client_order_id": client_order_id,  # 필수 저장
    "signal_id": signal_id,
    "placed_at": now()
}

# 재시작 시 복구 가능
if restart:
    # 미체결 주문 조회 (client_order_id로)
    pending = get_orders_by_client_id(session.pending_order.client_order_id)
    if pending:
        state = ENTRY_PENDING
```

### Stop Loss도 Idempotent

```python
# Stop Loss도 동일 원칙
stop_client_order_id = f"{signal_id}_stop_{direction}"

# 재시도/중복 호출해도 1회만 설치
place_stop_loss(
    qty=position.qty,
    stop_price=stop_price,
    client_order_id=stop_client_order_id
)

---

## 9. Metrics Update는 Closed Trades만

**규칙**: Winrate/Streak는 **청산 완료** 거래만 집계

```python
# ❌ 잘못된 방식
if position_pnl > 0:
    win_streak += 1  # 아직 청산 안 됨

# ✅ 올바른 방식
def on_position_closed(position, pnl_btc):
    closed_trades.append({
        "pnl_btc": pnl_btc,
        "is_win": pnl_btc > 0
    })

    if pnl_btc > 0:
        win_streak += 1
        loss_streak = 0
    else:
        loss_streak += 1
        win_streak = 0
```

---

## 10. 변경 규칙 (ADR 필수)

이 문서를 수정하려면:

1. **ADR(Architecture Decision Record) 작성**
   - 왜 바꾸는가?
   - 무엇이 문제였는가?
   - 대안은 무엇인가?

2. **실거래 영향 분석**
   - 기존 로직과 충돌하는가?
   - 청산 리스크가 증가하는가?

3. **테스트 필수**
   - Flow 변경은 Integration Test 필수
   - 상태 전환은 State Machine Test 필수

4. **버전 명시**
   - FLOW v1 → FLOW v2로 명시
   - Breaking change는 Major version up

---

## 최종 선언

이 Flow는 **Account Builder의 실행 계약**이다.

- 코드는 이 Flow를 따른다.
- Plan은 이 Flow를 위반할 수 없다.
- 성능/편의를 이유로 우회 불가.

**Flow를 어기면 = 실거래 실패.**

---

## 문서 버전 및 변경 이력

**현재 버전**: FLOW v1.7 (2026-01-18)

**변경 이력**:
- v1.7 (2026-01-18): Stop Loss API 파라미터 정정 (triggerPrice 기반)
  - **Section 4.5 triggerPrice 기반 계약**: `stopLoss` 파라미터 제거, `triggerPrice` + `triggerDirection` + `triggerBy` 로 교체
  - Bybit v5 Conditional Order API 계약 준수 (API 거절 리스크 제거)
  - 참조: ADR-0006

- v1.6 (2026-01-18): 실거래 API 충돌 4가지 수정 + Stop 상태 추적 추가 (헌법 일관성 확보)
  - **Section 4.1 REST 폴링 예시 제거**: Event-driven 상태 확정 원칙 준수, REST는 reconcile 용도로만 명확화
  - **Section 4.5 Stop Loss 전면 개편**: Conditional Order 방식 B 고정 (reduceOnly + stopLoss 파라미터 혼용 금지)
  - **Section 3.1 Position Mode 간소화**: positionIdx=0 강제만, 문자열 검증은 보조 진단으로 전환
  - **Section 2.5 상태 확정 규칙 명확화**: 정상/DEGRADED 모드 분리, DEGRADED 60초 후 HALT 규칙 추가
  - **Section 1 Position 서브상태 추가**: stop_status (ACTIVE/PENDING/MISSING/ERROR) 감시 및 복구 규칙
  - 참조: ADR-0005

- v1.5 (2026-01-18): 실거래 함정 5가지 수정 (Execution 레벨 사고 방지)
  - **Section 2.5 Stop Loss 갱신 규칙**: Amend API 우선 (SL 공백 제거), 20% threshold + 2초 debounce (Rate limit 절약)
  - **Section 2.6 WS DEGRADED Mode**: WS 단절 시 진입 차단 + IN_POSITION만 1초 reconcile (포지션 보호 우선)
  - **Section 3.4 Tick/Lot Size 준수**: qtyStep, tickSize 보정 + 재검증 필수 (주문 거절 방지)
  - **Section 7.5 Liquidation Gate 동적 기준**: stop × 배수 (4.0/3.5/3.0) + 최소 절대값 (15%/15%/12%)
  - **Section 8 orderLinkId 길이/제약 강제**: SHA1 해시 축약 (36자 제한), 영숫자+`-_` 검증
  - 참조: ADR-0004

- v1.4 (2026-01-18): 구조적 구멍 8가지 수정 (현실과 헌법 정합성 확보)
  - **Section 3.1 Position Mode Contract**: One-way 강제 (Hedge 금지), positionIdx=0
  - **Section 2.5 PARTIAL_FILL 서브상태**: entry_working 플래그 추가 (잔량 주문 추적)
  - **Section 2 REST Budget 합산**: 90회/분 rolling window 제한, tick+reconcile 합산
  - **Section 2.6 Reconcile 히스테리시스**: 연속 3회 불일치 시 덮어쓰기, 5초 COOLDOWN
  - **Section 6.2 Fee 단위 명시**: Inverse 1 contract = 1 USD notional, fee_btc = (contracts × rate) / price
  - **Section 7.5 Liquidation Gate 수치 재설계**: 20%/20%/15% (3x leverage 허용)
  - **Section 8 Idempotency Key 정규화**: entry_price 제거, signal_id = {strategy}_{bar_close_ts}_{side}
  - **Section 4.5 Stop 주문 속성 계약**: reduceOnly=True, positionIdx=0, orderType="Market" 강제
  - 참조: ADR-0003

- v1.3 (2026-01-18): 안전 게이트 2가지 추가 (청산/수수료 사고 방지)
  - **Section 6.2 Fee Post-Trade Verification**: 실제 수수료와 예상 수수료 비교, 50% 초과 시 24시간 tightening
  - **Section 7.5 Liquidation Distance Gate**: Sizing 후 청산거리 강제 검증 (Stage 1-2: 30%, Stage 3: 20%)
  - 참조: ADR-0002

- v1.2 (2026-01-18): 실전 케이스 4가지 추가 (실거래 사고 방지)
  - **PARTIAL_FILL 처리 규칙**: filled_qty > 0이면 즉시 IN_POSITION + Stop 설치
  - **WS Reconcile 규칙**: WS Primary + REST 저빈도 합치기 (10~30초)
  - **Idempotency Key 규칙**: 결정적 ID 생성 + 재시도 시 동일 ID 유지
  - **Stop Distance 출처 계약**: Grid spacing 기반 자동 계산 (grid × 1.5, clamp 2~6%)

- v1.1 (2026-01-18): 6가지 치명적 구멍 수정
  - 상태 수 정정 (5 → 6)
  - Tick 주기 동적 조정 + Rate limit 보호
  - Execution Events 소스 우선순위 (WS > REST)
  - Direction별 stop_price/sizing 공식 분기
  - Leverage와 Loss Budget 독립성 명시
  - Fee rate fallback 정책 추가

- v1.0 (2026-01-18): 초안

**다음 변경 시 필수 사항**:
1. ADR 문서 작성 (`docs/adr/ADR-XXXX-{title}.md`)
2. 버전 번호 증가 (v1.3 → v1.4 or v2.0)
3. task_plan.md의 "Definition of DONE"에 새 규칙 반영
