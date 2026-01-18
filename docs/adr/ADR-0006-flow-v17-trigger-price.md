# ADR-0006: FLOW v1.7 — Stop Loss API 파라미터 정정 (triggerPrice 기반)

**상태**: Accepted
**날짜**: 2026-01-18
**결정자**: System Architect
**관련 문서**: [FLOW v1.6](../constitution/FLOW.md), ADR-0005

---

## 컨텍스트 (Context)

FLOW v1.6에서 Stop Loss를 Conditional Order 방식 B로 고정했으나, **파라미터 불일치** 발견.

### 문제: Section 4.5 — stopLoss 파라미터 사용 (API 계약 위반)

**증상**:
- 현재 예시: `stopLoss=stop_price` 파라미터 사용
- **Bybit v5 Conditional Order는 `triggerPrice` 중심**

**Bybit v5 API 계약**:

1. **방식 A (TP/SL Attached)**:
   - Entry 주문에 `takeProfit` / `stopLoss` 파라미터 첨부
   - 체결 후 자동으로 TP/SL 주문 생성
   - **제약**: `reduceOnly=True`와 혼용 불가

2. **방식 B (Conditional Order)**:
   - 별도 Conditional Order로 Stop 생성
   - **필수 파라미터**: `triggerPrice`, `triggerDirection`, `triggerBy`
   - `stopLoss` 파라미터 **사용 안 함**

**현재 FLOW.md (v1.6) 문제**:
```python
# ❌ FLOW v1.6 예시 (파라미터 불일치)
stop_order = bybit_adapter.place_order(
    category="inverse",
    symbol="BTCUSD",
    side="Sell",
    orderType="Market",
    qty=position_qty,
    stopLoss=stop_price,  # ← 방식 A 파라미터 (Conditional에서 미지원)
    reduceOnly=True,
    positionIdx=0
)
```

**실거래 영향**:
- Bybit API가 `stopLoss` 파라미터를 방식 A로 해석
- `reduceOnly=True` 와 충돌 → "Invalid parameter" 거절
- 또는 Conditional이 아닌 일반 주문으로 오인 → 트리거 작동 안 함

**Bybit v5 문서 명시**:
```
Conditional Order:
  - triggerPrice: Trigger price (필수)
  - triggerDirection: 1 (rising), 2 (falling) (필수)
  - triggerBy: "LastPrice", "IndexPrice", "MarkPrice" (기본: "LastPrice")
  - stopLoss/takeProfit: 사용 안 함 (일반 주문 전용)
```

---

## 결정 (Decision)

### 수정: Section 4.5 — triggerPrice 기반 Conditional Order 계약

**변경**:
- `stopLoss` 파라미터 제거
- `triggerPrice` + `triggerDirection` + `triggerBy` 로 교체

**새 API 계약**:

```python
# ✅ Conditional Stop Market (방식 B)
def place_stop_loss(position_qty, stop_price, direction, signal_id):
    """
    Stop Loss Conditional Order 계약 (Bybit v5 기준)

    필수 파라미터:
    - triggerPrice: Stop trigger price
    - triggerDirection: 1 (rising, Short용), 2 (falling, Long용)
    - triggerBy: "LastPrice" (기본) or "MarkPrice"
    - reduceOnly: True (포지션 감소만)
    - positionIdx: 0 (One-way)
    - orderType: "Market" (트리거 시 즉시 체결)

    금지:
    - stopLoss 파라미터 사용 (일반 주문 전용)
    - triggerPrice 누락 (Conditional의 핵심)
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

    # Bybit v5 Conditional Stop Market
    stop_order = bybit_adapter.place_order(
        category="inverse",
        symbol="BTCUSD",
        side=stop_side,
        orderType="Market",
        qty=position_qty,

        # Conditional trigger (필수)
        triggerPrice=str(stop_price),  # Trigger price (string)
        triggerDirection=trigger_direction,  # 1: rising, 2: falling
        triggerBy="LastPrice",  # or "MarkPrice" (기본: LastPrice)

        # Position reduction
        reduceOnly=True,
        positionIdx=0,

        # Idempotency
        orderLinkId=stop_client_order_id
    )

    return stop_order
```

**triggerDirection 규칙** (혼동 방지):

```python
# Long 포지션: 가격 하락(falling) 시 Stop 발동
# → triggerDirection=2 (falling)
# → stop_price < entry_price

# Short 포지션: 가격 상승(rising) 시 Stop 발동
# → triggerDirection=1 (rising)
# → stop_price > entry_price
```

**triggerBy 선택** (기본: LastPrice):

```python
# LastPrice: 최종 체결가 기준 (일반적)
# MarkPrice: Mark Price 기준 (급변동 시 안정적, 하지만 지연 가능)
# IndexPrice: Index Price 기준 (거의 사용 안 함)

# 기본값: LastPrice (빠른 반응)
# 선택 사항: MarkPrice는 급변동 시 오발동 방지에 유리하지만,
#            대신 트리거 지연 가능 → 손실 증가 가능
#            → Account Builder는 LastPrice 고정
```

---

## 결과 (Consequences)

### 긍정적 영향

1. **API 호환성 확보**:
   - Bybit v5 Conditional Order 계약 준수
   - "Invalid parameter" 거절 리스크 제거

2. **실거래 안정성**:
   - Conditional Order 트리거 정상 작동
   - Stop Loss 발동 보장

3. **구현 명확성**:
   - `triggerPrice` 중심으로 코드 작성 → 오해 제거
   - Direction별 `triggerDirection` 규칙 명확화

### Trade-offs

1. **파라미터 복잡도 증가**:
   - `stopLoss` 1개 → `triggerPrice` + `triggerDirection` + `triggerBy` 3개
   - 수용 가능: API 계약 준수가 우선

2. **Direction별 분기 필요**:
   - Long/Short에 따라 `triggerDirection` 다름
   - 수용 가능: 로직 복잡도는 낮음 (if/else 1줄)

---

## 참조 (References)

- [FLOW v1.6](../constitution/FLOW.md) — Section 4.5
- ADR-0005 — FLOW v1.6 실거래 API 충돌 수정
- Bybit V5 API Documentation:
  - [Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order)
  - [Conditional Order Parameters](https://bybit-exchange.github.io/docs/v5/order/order-type)

---

## 버전

**FLOW 버전**: v1.6 → v1.7
**변경 범위**: Breaking (Stop Loss API 파라미터 변경)
**ADR 상태**: Accepted
**적용 날짜**: 2026-01-18
