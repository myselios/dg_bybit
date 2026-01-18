# ADR-0004: FLOW v1.5 실거래 함정 4가지 수정

**날짜**: 2026-01-18
**상태**: 수락됨
**영향 받는 문서**: FLOW.md v1.4 → v1.5
**작성자**: System Review

---

## 컨텍스트

FLOW v1.4는 구조적 구멍을 수정했으나, **실거래 집행(Execution) 함정 4가지**가 누락되었습니다.

이 함정들은 "문서상 옳지만 실제로는 불가능"하거나 "rate limit/거래소 제약으로 실패"하는 문제들입니다.

### 문제 1: Stop Loss 갱신 레이스 (치명적)

**현재 상황** (v1.4 Section 2.5):
```python
# 추가 체결 시 Stop 갱신
cancel_stop_loss(old_stop_order_id)
place_stop_loss(qty=position.qty, ...)
```

**리스크**:
1. **SL 공백(window)**: 취소 → 재설치 사이 급변동 → 무방어 노출
2. **Rate limit 소진**: 부분체결 이벤트마다 Cancel+Place → REST 예산 폭주
3. **레이스 조건**: 취소 실패 시 중복 Stop 발생 가능

**실제 사고 시나리오**:
```
10:00:00 - PARTIAL_FILL 100 contracts
10:00:01 - Stop Loss 설치 (100 contracts)
10:00:05 - PARTIAL_FILL 추가 50 contracts (총 150)
10:00:06 - Cancel Stop (100) → 요청 전송
10:00:07 - [SL 공백 1초] ← 급변동 발생
10:00:08 - Place Stop (150) → rate limit exceeded
→ Stop 없이 포지션 노출 + 진입 차단
```

---

### 문제 2: WS Reconcile 주기 vs DEGRADED Mode

**현재 상황** (v1.4 Section 2.6):
- IN_POSITION: 10초마다 reconcile
- WS 단절 시 대응 규칙 없음

**리스크**:
- **10초는 너무 길다**: 청산/SL 체결 같은 이벤트는 1~2초 밀리면 유령 포지션 오판
- **단순 주기 단축은 위험**: REST budget 초과 → 진짜 필요한 요청 막힘

**문제**:
- WS 단절은 "정상 운용"이 아닌데, FLOW가 "방어 모드" 전환 규칙 없음

---

### 문제 3: Client Order ID 길이/제약 무시

**현재 상황** (v1.4 Section 8):
```python
client_order_id = f"{signal_id}_{direction}"
# 예: "grid_1705593600_long_Buy"
```

**리스크**:
- Bybit `orderLinkId`: **최대 36자** + 허용 문자 제약 (영숫자, `-`, `_`)
- Signal ID가 길어지면 초과 → **주문 거절**
- 특수문자/공백 포함 → **주문 거절**

**실제 사고**:
```
signal_id = "grid_detailed_strategy_20260118_143022_long"
direction = "Buy"
client_order_id = "grid_detailed_strategy_20260118_143022_long_Buy"
→ len = 49 > 36
→ Bybit: "Invalid orderLinkId"
→ 모든 주문 거절
```

---

### 문제 4: Tick/Lot Size 미준수

**현재 상황** (v1.4 Section 3.4):
```python
contracts = (max_loss_btc × entry × (1 - stop_distance_pct)) / stop_distance_pct
# Constraints:
# - contracts >= 1
# - floor(contracts) to integer
```

**리스크**:
- **Lot size 미준수**: Bybit는 qtyStep(예: 1) 단위만 허용
- **Tick size 미준수**: Price도 tickSize(예: 0.5) 단위만 허용
- Floor 후 재검증 없음 → margin/liq gate 통과했는데 실제는 다른 수량

**실제 사고**:
```
계산: contracts = 127.3
Floor: contracts = 127 ✓
하지만 qtyStep = 10이면 → 127은 거절, 120만 허용
→ Margin 재계산 필요
→ 지금 FLOW는 재검증 없음
```

---

### 문제 5: Liquidation Gate 기준 비현실적

**현재 상황** (v1.4 Section 7.5):
```python
min_liq_distance_pct = {
    1: 0.30,  # Stage 1: 30%
    2: 0.30,  # Stage 2: 30%
    3: 0.15   # Stage 3: 15%
}
```

**리스크**:
- Leverage 3x Long: liq_distance ≈ 25%
- **Stage 1 기준 30% → 거의 모든 3x 진입 REJECT**
- Account Builder ($100 → $1000)는 "진입 빈도"가 핵심인데, 진입 자체가 막힘

**계산**:
```
Stage 1, 3x Long, stop 2%
→ liq_distance = 25%
→ 30% 미만 → REJECT

Stage 1, 3x Long, stop 4%
→ liq_distance = 25% (leverage는 동일)
→ 30% 미만 → REJECT
```

**문제**:
- 고정 기준(30%)은 leverage/stop과 무관 → **설계 모순**
- Stop distance가 넓어도 liquidation distance는 leverage만으로 결정됨

---

## 결정

4가지 실거래 함정을 모두 수정하여 FLOW v1.5로 업데이트합니다.

### 수정 1: Stop Loss 갱신 규칙 (Amend 우선 + Debounce)

**위치**: Section 2.5

```python
# Stop 갱신 조건 (즉시가 아닌 조건부)
delta_qty = abs(new_qty - current_stop_qty)
delta_ratio = delta_qty / current_stop_qty

# Threshold: 20% 이상 변화 시만
if delta_ratio < 0.20:
    return  # 갱신 안 함

# Debounce: 최소 2초 간격
if now() - last_stop_update_at < 2.0:
    return  # 갱신 안 함

# 갱신 방식 우선순위
try:
    # 1. Amend (qty만 수정, SL 공백 없음)
    amend_stop_loss(
        order_id=stop_order_id,
        qty=new_qty
    )
    last_stop_update_at = now()

except AmendNotSupported:
    # 2. Cancel+Place (Amend 불가 시만)
    # 이 경우에도 debounce 강제
    cancel_stop_loss(stop_order_id)
    place_stop_loss(qty=new_qty, ...)
    last_stop_update_at = now()
```

---

### 수정 2: WS DEGRADED Mode

**위치**: Section 2.6 확장

```python
# WS Health 추적
ws_heartbeat_timeout = 10  # heartbeat 10초 이상 없으면
ws_event_drop_count = 0    # 연속 이벤트 드랍 감지

# DEGRADED Mode 진입
if ws_heartbeat_timeout_exceeded or ws_event_drop_count >= 3:
    system.degraded_mode = True

    # 신규 진입 차단
    if state == FLAT:
        entry_allowed = False

    # 포지션 있을 때만 aggressive reconcile
    if state == IN_POSITION:
        reconcile_interval = 1.0  # 1초 (포지션만)
        rest_calls_allowed = 2    # position/list + order/realtime만
    else:
        reconcile_interval = 30.0  # FLAT은 유지

# WS 복구 시
if ws_heartbeat_ok and ws_event_drop_count == 0:
    system.degraded_mode = False
    # 5분 COOLDOWN 후 진입 재개
    entry_cooldown_until = now() + 300
```

---

### 수정 3: Client Order ID 길이/제약 강제

**위치**: Section 8

```python
# Signal ID 해시 축약 (길이 제한)
import hashlib

def generate_signal_id(strategy, bar_close_ts, side):
    # 원본 (너무 길 수 있음)
    raw = f"{strategy}_{bar_close_ts}_{side}"

    # 해시 축약 (sha1 앞 10자리)
    hash_suffix = hashlib.sha1(raw.encode()).hexdigest()[:10]

    # 축약 ID
    signal_id = f"{strategy[:4]}_{hash_suffix}_{side[:1]}"
    # 예: "grid_a3f8d2e1c4_l"

    return signal_id

# Client Order ID 생성
client_order_id = f"{signal_id}_{direction}"

# 검증 (강제)
assert len(client_order_id) <= 36, f"orderLinkId too long: {len(client_order_id)}"
assert re.match(r'^[a-zA-Z0-9_-]+$', client_order_id), "Invalid characters in orderLinkId"
```

---

### 수정 4: Tick/Lot Size 준수 + 재검증

**위치**: Section 3.4

```python
# Sizing 계산
contracts = (max_loss_btc × entry × (1 - d)) / d

# Lot size 보정 (필수)
qty_step = exchange.get_instrument_info("BTCUSD").qty_step  # 예: 1
contracts = floor(contracts / qty_step) * qty_step

# Price tick size 보정
tick_size = exchange.get_instrument_info("BTCUSD").tick_size  # 예: 0.5
entry_price = round_to_tick(entry_price, tick_size)

# 보정 후 재검증 (필수)
# 1. Margin feasibility
required_margin_btc = (contracts / entry_price) / leverage
fee_buffer_btc = (contracts / entry_price) × fee_rate × 2

if required_margin_btc + fee_buffer_btc > equity_btc:
    REJECT

# 2. Liquidation gate
liq_distance_pct = calculate_liquidation_distance(...)
if liq_distance_pct < min_required:
    REJECT

# 3. 최소 수량 (1 contract 미만 → REJECT)
if contracts < qty_step:
    REJECT
```

---

### 수정 5: Liquidation Gate 동적 기준

**위치**: Section 7.5

```python
# 고정 기준 제거, 동적 기준 적용
# liq_distance >= stop_distance × 배수

# Stage별 배수
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

# 동적 기준
min_required = max(
    stop_distance_pct * liq_distance_multiplier[stage],
    min_absolute_liq_distance[stage]
)

# Gate
if liq_distance_pct < min_required:
    REJECT(reason=f"liquidation_too_close: {liq_distance_pct:.1%} < {min_required:.1%}")
```

**예시**:
```python
# Stage 1, 3x Long, stop 2%
liq_distance = 25%
min_required = max(2% × 4, 15%) = max(8%, 15%) = 15%
→ PASS (25% > 15%)

# Stage 1, 3x Long, stop 4%
liq_distance = 25%
min_required = max(4% × 4, 15%) = max(16%, 15%) = 16%
→ PASS (25% > 16%)

# Stage 1, 3x Long, stop 6%
liq_distance = 25%
min_required = max(6% × 4, 15%) = max(24%, 15%) = 24%
→ PASS (25% > 24%)
```

---

## 대안

### 대안 1: Stop 갱신을 항상 Cancel+Place
- **거부 이유**: SL 공백 + rate limit 소진

### 대안 2: WS 단절 시 단순 주기 단축
- **거부 이유**: REST budget 초과 → 진짜 요청 막힘

### 대안 3: orderLinkId 길이 제한 무시
- **거부 이유**: Bybit 주문 거절 → 시스템 정지

### 대안 4: Tick/Lot size 보정 없이 진행
- **거부 이유**: 주문 거절 → "Invalid qty/price"

### 대안 5: Liquidation gate 고정 기준 유지
- **거부 이유**: 3x leverage 거의 REJECT → 진입 불가 → 성장 불가

---

## 결과

### 긍정적 영향
- [x] Stop 갱신 레이스 제거 (Amend + debounce)
- [x] SL 공백 제거 (Amend 우선)
- [x] Rate limit 소진 방지 (20% threshold + 2s debounce)
- [x] WS 단절 시 방어 모드 전환 (DEGRADED mode)
- [x] orderLinkId 길이 초과 방지 (36자 강제)
- [x] Tick/Lot size 준수 (주문 거절 방지)
- [x] Liquidation gate 현실화 (진입 빈도 확보)

### 부정적 영향 / Trade-off
- [x] Stop 갱신 지연 (20% threshold) → 미세 수량 변화 무시
- [x] DEGRADED mode에서 진입 차단 → 기회 손실
- [x] Signal ID 해시 축약 → 가독성 저하
- [x] Tick/Lot size 보정 후 재검증 → 계산 복잡도 증가

### 변경이 필요한 코드/문서
- [x] FLOW.md v1.4 → v1.5
- [ ] task_plan.md: Phase 3에 "Amend Stop Loss" 추가
- [ ] task_plan.md: Phase 1에 "WS DEGRADED mode" 추가
- [ ] task_plan.md: Phase 2에 "Tick/Lot size 보정" 추가
- [ ] src/execution/: Amend Stop Loss 구현 필요
- [ ] src/exchange/: WS heartbeat tracking 구현 필요
- [ ] src/exchange/: Instrument info (qtyStep, tickSize) 조회 필요

---

## 실거래 영향 분석

### 리스크 변화
- **Stop 공백 리스크**: 제거 (Amend 우선)
- **Rate limit 초과**: 감소 (debounce)
- **주문 거절**: 제거 (orderLinkId, tick/lot size 준수)
- **진입 빈도**: 증가 (liquidation gate 현실화)

### 백워드 호환성
- [x] 기존 포지션 영향 없음 (아직 구현 전)
- [x] 기존 설정 마이그레이션 불필요
- [x] v1.4는 미구현이므로 완전 교체 가능

### 롤백 가능성
- [x] 쉽게 롤백 가능 (Git revert)
- [ ] 데이터 마이그레이션 불필요
- [ ] 롤백 불필요 (v1.4는 미구현)

---

## 참고 자료

- Bybit Amend Order: https://bybit-exchange.github.io/docs/v5/order/amend-order
- Bybit orderLinkId: https://bybit-exchange.github.io/docs/v5/order/create-order#parameters
- Bybit Instrument Info: https://bybit-exchange.github.io/docs/v5/market/instrument
- User Review: 2026-01-18 실거래 함정 4가지 식별
