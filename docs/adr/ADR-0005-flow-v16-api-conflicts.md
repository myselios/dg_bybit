# ADR-0005: FLOW v1.6 — 실거래 API 충돌 4가지 수정

**상태**: Accepted
**날짜**: 2026-01-18
**결정자**: System Architect
**관련 문서**: [FLOW v1.5](../constitution/FLOW.md), [task_plan.md](../plans/task_plan.md)

---

## 컨텍스트 (Context)

FLOW v1.5 리뷰 결과, **헌법이 PLAN보다 덜 현실적인 상황** 발견.

### 문제 1: Section 4.1 — REST 폴링 예시 모순

**증상**:
- Section 2.5에서 "상태 확정은 이벤트로만" 선언
- Section 4.1 "올바른 방식" 예시에서 `get_order_status()`로 REST 폴링

**헌법 위배**:
```python
# ❌ Section 4.1 "올바른 방식" 예시 (모순)
if state == ENTRY_PENDING:
    status = get_order_status(pending_order_id)  # REST 폴링
    if status.filled:
        state = IN_POSITION
```

이건 Section 2.5의 "Event-driven 상태 확정" 헌법을 정면으로 위반함.

**실거래 영향**:
- 구현자가 "올바른 방식"으로 착각
- WS 무시하고 REST 폴링 구현
- Rate limit 낭비 + 상태 지연

---

### 문제 2: Section 4.5 — Stop Loss API 호환성 실패

**증상**:
- 현재 예시: `place_order(..., stopLoss=stop_price, reduceOnly=True)`
- **Bybit Inverse Futures에서 이 조합은 거절됨**

**Bybit API 제약**:
```
reduceOnly + stopLoss 파라미터 동시 사용 불가
→ "Invalid parameter" 오류
```

**올바른 방식**:
- **방식 A**: Entry 주문에 `stopLoss` 파라미터 (reduceOnly=False 전제)
- **방식 B**: 별도 Conditional Stop Market 주문 (reduceOnly=True)

**Account Builder에 필요한 방식**:
- **방식 B만 가능**
- 이유:
  1. PARTIAL_FILL 시 Stop qty 증감(amend) 필요
  2. Stop/Entry 라이프사이클 분리 (상태도 분리)
  3. Rate limit/SL 공백 방지 설계 가능

**현재 헌법 문제**:
- 방식 A/B 혼용 허용
- 실거래에서 주문 거절 발생
- Stop 관리 규칙 미비 (SL 공백/Rate limit 대응 없음)

---

### 문제 3: Section 3.1 — Position Mode 검증 취약성

**증상**:
- 현재: `get_position_mode()` 문자열 검증 ("MergedSingle")
- **문자열은 API 버전/거래소에 따라 변경 가능**

**취약성**:
```python
# ❌ 취약한 검증
if mode != "MergedSingle":
    raise SystemError("Position mode must be One-way")
```

- Bybit가 문자열 변경하면 시스템 시작 실패
- 진짜 필요한 건 "One-way 동작 강제"이지 "문자열 검증"이 아님

**올바른 강제**:
```python
# ✅ 강제 계약
positionIdx = 0  # 모든 주문에 One-way 강제
```

---

### 문제 4: Section 2.5 — 상태 확정 규칙 예외 미명문화

**증상**:
- "상태 확정은 이벤트로만" 선언
- DEGRADED(WS 단절) 모드에서 예외 처리 애매

**헌법 공백**:
- 정상 모드: Event-driven ✅
- DEGRADED 모드: REST reconcile 허용하지만 "확정" vs "정합성 회복" 구분 없음
- 복구 시나리오: WS 복구 후 상태 전환 규칙 없음

**실거래 리스크**:
- DEGRADED 중 REST로 "상태 확정"을 착각하여 이벤트 무시
- WS 복구 후 불일치 상태 방치
- 장기 DEGRADED 시 HALT 조건 없음 → 계좌 노출

---

### 문제 5 (추가): Stop 주문 상태 추적 부재

**증상**:
- 현재 State Machine: FLAT/ENTRY_PENDING/IN_POSITION/EXIT_PENDING/HALT/COOLDOWN (6개)
- **Stop 주문 상태는 추적 안 함**

**실거래 문제**:
```python
# IN_POSITION인데 Stop이 없는 경우를 정상 흐름이 커버 못함
- Stop 주문 거절
- Stop 주문 취소/만료
- Amend 실패
- 중복/지연
```

**필요한 것**:
- Stop을 별도 상태로 늘리지 말고, **Position 서브상태**로 추가
- `stop_status = ACTIVE | PENDING | MISSING | ERROR`
- IN_POSITION + MISSING → 즉시 복구 시도 → 실패 누적 시 HALT

---

## 결정 (Decision)

### 수정 1: Section 4.1 — REST 폴링 예시 제거/교체

**변경**:
- "올바른 방식" 예시에서 `get_order_status()` 제거
- Event-driven 상태 전환 예시로 교체

**새 규칙**:
```
"REST는 reconcile용 스냅샷이며, state transition의 trigger가 아니다."

"단, WS DEGRADED 상태에서는 최소 동작을 위해 제한된 REST 확인이 허용되며,
이때도 '확정'이 아니라 '불일치 해소' 목적이다."
```

---

### 수정 2: Section 4.5 — Stop Loss 전면 개편 (방식 B 고정)

**변경**:
- **방식 B(Conditional Order)로 고정**
- Entry 주문: `reduceOnly=False` (일반 진입)
- Stop 주문: 별도 Conditional Order (`category="inverse", orderType="Market", stopLoss=price, reduceOnly=True`)

**Stop 관리 규칙 추가** (헌법 승격):
1. **SL 공백 금지**:
   - Amend API 우선 (주문 유지)
   - Amend 불가 시에만 Cancel+Place (원자적 대체 흉내)

2. **Debounce/Threshold**:
   - 20% threshold: 수량 변화 < 20% → 갱신 안 함
   - 2초 debounce: 최소 2초 간격

3. **Stop 필수 존재 감시**:
   - IN_POSITION이면 Stop 필수
   - Stop 없으면 즉시 복구 시도
   - 복구 실패 누적 시 HALT

**API 명세**:
```python
# Entry 주문
place_order(
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

# Stop Loss 주문 (별도)
place_order(
    category="inverse",
    symbol="BTCUSD",
    side="Sell",  # Long 포지션 → Sell stop
    orderType="Market",
    qty=position_qty,
    stopLoss=stop_price,  # Trigger price

    # 필수 속성
    reduceOnly=True,
    positionIdx=0,
    orderLinkId=stop_client_order_id
)
```

---

### 수정 3: Section 3.1 — Position Mode 검증 간소화

**변경**:
- 문자열 검증 ("MergedSingle") 제거
- **핵심만 남김**: `positionIdx=0` 강제

**새 규칙**:
```
모든 주문은 positionIdx=0 (One-way)로 강제한다.
포지션/주문 조회 시도 positionIdx=0만 대상이다.
Exchange가 모드를 뭐라 부르든 상관없이, 시스템이 One-way로 동작하도록 강제한다.
```

**문자열 검증은 보조 진단(로그)으로만**:
```python
# 시스템 시작 시 경고용
mode = bybit_adapter.get_position_mode(category="inverse", symbol="BTCUSD")
if mode != "MergedSingle":
    log_warning("position_mode_unexpected", {"mode": mode, "expected": "MergedSingle"})
    # 하지만 HALT은 안 함, positionIdx=0 강제로 운용
```

---

### 수정 4: Section 2.5 — 상태 확정 규칙 명확화

**변경**:
- **정상(WS healthy) vs DEGRADED(WS unhealthy) 규칙 분리 명문화**

**새 규칙**:

#### 정상 모드 (WS healthy)
- 상태 전이는 `execution`/`order`/`position` 이벤트가 트리거
- REST로 `Filled` 확인해서 state 바꾸는 로직 **금지**

#### DEGRADED 모드 (WS unhealthy)
**진입 조건**:
- Heartbeat 10초 이상 없음
- 연속 이벤트 드랍 3회 이상

**동작**:
1. **신규 진입 차단** (FLAT이어도)
2. **Reconcile 주기 단축**:
   - IN_POSITION: 1초 (포지션 보호)
   - ENTRY_PENDING/EXIT_PENDING: 1초 (중요 상태)
   - FLAT: 30초 (기존 유지)
3. **목적**: '확정'이 아니라 '정합성 회복'
4. **장기 미복구 시 HALT**:
   - DEGRADED 상태 60초 이상 지속 → HALT
   - (단, IN_POSITION은 Stop 유지)

**복구**:
- WS 복구 후 5분 COOLDOWN → 진입 재개

---

### 수정 5: Position 서브상태 추가 (stop_status)

**변경**:
- State Machine 상태 수는 6개 유지
- **Position 객체에 `stop_status` 필드 추가**

**stop_status 값**:
```python
ACTIVE   : Stop 주문 활성 (정상)
PENDING  : Stop 설치/갱신 중 (일시적)
MISSING  : Stop 없음 (비정상, 즉시 복구 필요)
ERROR    : Stop 복구 실패 (HALT 고려)
```

**관리 규칙**:
```python
if state == IN_POSITION:
    # Stop 상태 감시
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

---

## 결과 (Consequences)

### 긍정적 영향

1. **헌법 일관성 확보**:
   - FLOW가 PLAN보다 현실적으로 전환
   - 내부 모순 제거

2. **실거래 안정성**:
   - Stop Loss API 호환성 보장
   - SL 공백 제거 (Amend 우선)
   - Rate limit 절약 (Debounce/Threshold)

3. **상태 전환 명확성**:
   - 정상/DEGRADED 모드 구분
   - 예외 규칙 명문화

4. **Stop 추적 강화**:
   - Stop 없는 상태 감지
   - 자동 복구 + HALT 안전망

### Trade-offs

1. **복잡도 증가**:
   - Position 서브상태 추가 (`stop_status`)
   - DEGRADED 모드 전이 규칙 추가

2. **Stop 갱신 지연**:
   - 20% threshold → 미세 변화 무시
   - 수용 가능: 손실 예산은 `stop_distance`로 제어

3. **WS 단절 시 진입 차단**:
   - DEGRADED 중 진입 기회 손실
   - 수용 가능: 포지션 보호 > 진입 기회

---

## 참조 (References)

- [FLOW v1.5](../constitution/FLOW.md)
- [task_plan.md](../plans/task_plan.md) — P1 Phase 2.3
- Bybit V5 API Documentation:
  - [Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order)
  - [Stop Order Types](https://bybit-exchange.github.io/docs/v5/order/order-type)

---

## 버전

**FLOW 버전**: v1.5 → v1.6
**변경 범위**: Breaking (Stop Loss API 계약 변경)
**ADR 상태**: Accepted
**적용 날짜**: 2026-01-18
