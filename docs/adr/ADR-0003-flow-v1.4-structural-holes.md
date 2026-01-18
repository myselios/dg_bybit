# ADR-0003: FLOW v1.4 구조적 구멍 8가지 수정

**날짜**: 2026-01-18
**상태**: 수락됨
**영향 받는 문서**: FLOW.md v1.3 → v1.4
**작성자**: System Review

---

## 컨텍스트

FLOW v1.3은 안전 게이트를 추가했으나, **구현 시 발생할 8가지 구조적 구멍**이 식별되었습니다.

이 구멍들은 "문서가 길다"가 아니라 **헌법이 현실과 충돌하는 문제**입니다.

### 문제 1: Position Mode 계약 부재

**현재 상황**:
- State Machine은 "포지션 1개"를 전제
- Bybit Position Mode (One-way vs Hedge) 명시 없음
- Hedge 모드면 롱/숏 동시 보유 가능 → State(FLAT/IN_POSITION) 붕괴

**리스크**:
```
거래소 설정: Hedge mode
State: FLAT (코드는 포지션 없다고 생각)
실제: Long 포지션 존재
→ Short 진입 → 롱/숏 동시 보유
→ State Machine 완전 붕괴
```

### 문제 2: PARTIAL_FILL 서브상태 애매

**현재 상황**:
- PARTIAL_FILL: IN_POSITION + Stop 설치 (정확함)
- 하지만 "IN_POSITION인데 Entry 주문(잔량) 살아있음" 상황 처리 불명확
- Tick Flow [3] Manage Position vs [4] Signal Decision 분기가 깨짐

**리스크**:
- "IN_POSITION인데 또 Entry 시도 금지" 규칙과 "잔량 추가 체결" 충돌
- 구현자마다 다르게 해석

### 문제 3: REST budget 충돌

**현재 상황**:
- "Tick당 REST 최대 3회" (Section 2)
- Reconcile: 5~30초마다 추가 REST 호출 (Section 2.6)
- **합산 예산 없음** → 실제로는 3회 제한 무력화

**리스크**:
```
Tick: 3회 (price, account, orders)
Reconcile (10초마다): 2회 (orders, position)
→ 실제: 5회/tick → rate limit 초과
```

### 문제 4: "REST = Source of Truth" 플립플롭

**현재 상황**:
- "WS state ≠ REST state → 즉시 REST로 덮어쓰기"
- REST도 지연/캐시/일시적 불일치 흔함
- **히스테리시스 없음** → 상태 왔다갔다

**리스크**:
```
WS: IN_POSITION
REST (1초 지연): None
→ State = FLAT

WS: IN_POSITION (정상)
REST (캐시 갱신): IN_POSITION
→ State = IN_POSITION

→ FLAT ↔ IN_POSITION 플립플롭
```

### 문제 5: Fee 계산 단위 불명확

**현재 상황**:
- `estimated_fee_usd = contracts * fee_rate`
- Inverse에서 contracts가 의미하는 notional 정의 없음
- **단위 불일치 가능성**

**리스크**:
- Fee spike 오탐 (계산 잘못해서 항상 1.5배 초과)
- Fee spike 누락 (계산 잘못해서 절대 안 울림)

### 문제 6: Liquidation gate 수치 모순

**현재 상황**:
- Leverage 3x @ Long → liq_distance = 25% (계산식 결과)
- Stage 1 최소 기준: 30%
- **3x는 영원히 통과 못함** → Stage 1 설계 붕괴

**리스크**:
```
Stage 1: leverage 3x (task_plan.md)
Liquidation gate: 30% 필요
3x 실제 청산거리: 25%
→ 모든 Entry REJECT
→ 시스템 정지
```

### 문제 7: Idempotency Key entry_price 위험

**현재 상황**:
- `client_order_id = f"{signal_id}_{entry_price_int}_{direction}"`
- entry_price는 호가/라운딩으로 미세 조정 가능
- **같은 시그널인데 다른 ID** → 중복 주문

**리스크**:
```
Signal 1: entry=50000.5 → 50001 (round up)
Signal 1 retry: entry=50000.5 → 50000 (round down)
→ 다른 client_order_id
→ 중복 주문
```

### 문제 8: Stop 주문 속성 계약 부재

**현재 상황**:
- "Stop Loss 설치"만 명시
- reduceOnly, closeOnTrigger, positionIdx 등 필수 플래그 없음
- **Stop이 포지션을 늘리는 사고 가능**

**리스크**:
```
Stop Loss 체결
reduceOnly=false (미설정)
→ 포지션 반대 방향 신규 진입
→ 손절이 아니라 포지션 반전
```

---

## 결정

8가지 구조적 구멍을 모두 수정하여 FLOW v1.4로 업데이트합니다.

### 수정 1: Position Mode Contract 추가

**위치**: Section 3.1 확장

```python
# Bybit Position Mode 강제 계약
position_mode = "OneWay"  # Hedge 금지
positionIdx = 0           # One-way unified

# 설정 검증 (시스템 시작 시)
assert bybit_adapter.get_position_mode() == "MergedSingle"  # One-way

# 롱/숏 동시 보유 = 버그
if has_long_position and signal.direction == SHORT:
    REJECT(reason="hedge_mode_violation")
```

### 수정 2: PARTIAL_FILL 서브상태 명시

**위치**: Section 2.5 확장

```python
# IN_POSITION 서브상태
state = IN_POSITION
position.qty = filled_qty
position.entry_working = True  # 잔량 주문 활성

# Tick Flow에서
if state == IN_POSITION:
    # Stop은 항상 position.qty 기준으로 관리
    manage_stop_loss(position.qty)

    # entry_working=True면 추가 체결 대기
    if position.entry_working:
        # 잔량 체결 이벤트 처리
        on_additional_fill()
```

### 수정 3: REST Budget 합산 제한

**위치**: Section 2 Tick 규칙

```python
# REST Budget (1분 rolling window)
REST_BUDGET_PER_MIN = 90

# Tick: ~3회 (snapshot)
# Reconcile: 상태별 (5~30초)
# 합산이 90/min 초과 시 tick 주기 증가

if rolling_rest_calls_1min > REST_BUDGET_PER_MIN * 0.8:
    tick_interval = min(tick_interval * 1.5, 2.0)
```

### 수정 4: Reconcile 히스테리시스 추가

**위치**: Section 2.6

```python
# 불일치 연속 확인
mismatch_count = 0

if ws_state != rest_state:
    mismatch_count += 1

    # 연속 3회 불일치 시 덮어쓰기
    if mismatch_count >= 3:
        state = rest_state
        mismatch_count = 0

        # 5초 COOLDOWN (재확인 금지)
        last_reconcile_override = now()
        reconcile_cooldown_until = now() + 5
else:
    mismatch_count = 0
```

### 수정 5: Fee 계산 단위 명시

**위치**: Section 6.2

```python
# Bybit Inverse Futures 특성
# contracts = USD notional (1 contract = 1 USD)

# Entry 시점
estimated_fee_usd = contracts * fee_rate  # contracts가 곧 USD notional

# 체결 시점
actual_fee_btc = fill_event.fee_paid
actual_fee_usd = actual_fee_btc * fill_event.exec_price

# 검증
fee_ratio = actual_fee_usd / estimated_fee_usd
```

### 수정 6: Liquidation Gate 수치 재설계

**위치**: Section 7.5

```python
# Stage별 최소 청산거리 (현실적 수치)
min_liq_distance_pct = {
    1: 0.20,  # Stage 1: 20% (leverage 3x 허용)
    2: 0.20,  # Stage 2: 20%
    3: 0.15   # Stage 3: 15% (leverage 2x)
}

# Leverage별 실제 청산거리
# 3x Long: ~25%
# 3x Short: ~50%
# 2x Long: ~33%
# 2x Short: ~100%
```

### 수정 7: Idempotency Key 정규화

**위치**: Section 8

```python
# Signal ID 생성 규칙 (명시)
signal_id = f"{strategy}_{bar_close_ts}_{side}"
# 예: "grid_1705593600_long"

# Client Order ID (entry_price 제거)
client_order_id = f"{signal_id}_{direction}"
# 예: "grid_1705593600_long_Buy"

# 재시도: 동일 ID
# 새 시그널: 새 ID (새 bar_close_ts)
```

### 수정 8: Stop 주문 속성 계약

**위치**: Section 3 or Section 4 (새 섹션)

```python
# Stop Loss 필수 속성
stop_order = place_stop_loss(
    symbol="BTCUSD",
    side="Sell",  # Long 포지션 → Sell stop
    qty=position.qty,
    stop_price=stop_price,

    # 필수 속성 (강제 계약)
    reduceOnly=True,       # 포지션 증가 금지
    positionIdx=0,         # One-way
    stopOrderType="StopLoss",

    # Bybit Inverse는 closeOnTrigger 없음 (명시)
    client_order_id=stop_client_order_id
)
```

---

## 대안

### 대안 1: 구멍을 그대로 두고 구현 중 해결
- **거부 이유**: 헌법이 현실과 충돌하면 구현자마다 다르게 만듦 → 사고

### 대안 2: 일부만 수정 (우선순위 상위 4개만)
- **거부 이유**: #7 (Idempotency)도 중복주문 사고로 직결됨, 8개 모두 치명적

### 대안 3: v2.0으로 major version up
- **거부 이유**: Breaking change 아님, 계약 명확화/수정이므로 v1.4 적합

---

## 결과

### 긍정적 영향
- [x] Position mode 계약으로 Hedge 사고 방지
- [x] PARTIAL_FILL 서브상태 명확화로 구현 일관성 확보
- [x] REST budget 합산으로 rate limit 초과 방지
- [x] Reconcile 히스테리시스로 플립플롭 방지
- [x] Fee 단위 명시로 spike 오탐/누락 방지
- [x] Liquidation gate 수치 정합성 확보 (3x 허용)
- [x] Idempotency key 정규화로 중복주문 방지
- [x] Stop 속성 계약으로 포지션 증가 사고 방지

### 부정적 영향 / Trade-off
- [x] Liquidation gate 완화 (30% → 20%) → 청산 리스크 약간 증가
- [x] Reconcile 히스테리시스로 불일치 감지 지연 (즉시 → 연속 3회)
- [x] 문서 길이 증가 (1,256줄 → ~1,400줄 예상)

### 변경이 필요한 코드/문서
- [x] FLOW.md v1.3 → v1.4
- [ ] task_plan.md: Phase 0에 "Position Mode 검증" 추가
- [ ] src/exchange/: Position mode 강제 설정/검증 필요
- [ ] src/state/: IN_POSITION + entry_working 플래그 구현 필요
- [ ] src/execution/: Stop 주문 reduceOnly 강제 필요

---

## 실거래 영향 분석

### 리스크 변화
- **청산 리스크**: 약간 증가 (gate 30% → 20%, 하지만 현실적 수치)
- **손실 한도**: 불변 (Stop loss budget 유지)
- **Emergency 대응**: 불변

### 백워드 호환성
- [x] 기존 포지션 영향 없음 (아직 구현 전)
- [x] 기존 설정 마이그레이션 불필요
- [x] v1.3은 미구현이므로 완전 교체 가능

### 롤백 가능성
- [x] 쉽게 롤백 가능 (Git revert)
- [ ] 데이터 마이그레이션 불필요
- [ ] 롤백 불필요 (v1.3은 미구현)

---

## 참고 자료

- Bybit Position Mode: https://bybit-exchange.github.io/docs/v5/position/position-mode
- Bybit Stop Order: https://bybit-exchange.github.io/docs/v5/order/create-order#stop-order
- User Review: 2026-01-18 v1.3 구조적 구멍 8가지 식별
