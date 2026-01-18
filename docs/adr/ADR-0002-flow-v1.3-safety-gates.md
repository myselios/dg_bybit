# ADR-0002: FLOW v1.3 안전 게이트 2가지 추가

**날짜**: 2026-01-18
**상태**: 수락됨
**영향 받는 문서**: FLOW.md v1.2 → v1.3
**작성자**: System Review

---

## 컨텍스트

FLOW.md v1.2는 실전 케이스 4가지를 추가하여 실거래 사고를 방지했으나, **2가지 추가 안전 게이트**가 누락되어 있습니다.

이 2가지는 v1.2 리뷰 중 식별된 실거래 필수 안전장치입니다.

### 문제 1: 청산거리 게이트 부재

**현재 상황**:
- Section 7 "Sizing Double-Check"에서 Margin feasibility만 확인
- Liquidation distance는 Section 3.6에서 "fallback conservative proxy"로만 언급
- **별도 강제 게이트 없음** → 레버리지 3x + Stop 2%인 상황에서 청산거리가 5%밖에 안 될 수 있음

**리스크**:
- Stop loss 발동 전에 청산 발생 가능
- 특히 소액 계좌($100) + 3x leverage + 좁은 Stop일 때 치명적

**사례**:
```
계좌: $100 (0.001 BTC @ $100k)
Leverage: 3x
Stop distance: 2%
Loss budget: 12% → contracts 계산 시 margin 80% 사용
→ 청산 거리: ~7% (leverage 3x 기준)
→ Stop 2% vs 청산 7% → 안전
```

그러나:
```
계좌: $100 (0.001 BTC @ $100k)
Leverage: 3x
Stop distance: 6% (volatility 높은 날)
Loss budget: 12% → contracts 줄어듦
하지만 Grid spacing이 크면 contracts가 여전히 클 수 있음
→ 청산 거리 계산 없이 진입 → 위험
```

**결론**: Stop loss로 손실 제한하려 했으나, 청산이 먼저 발생하면 **손실 예산 무력화**.

---

### 문제 2: 수수료 사후 검증 부재

**현재 상황**:
- Section 6에서 Fee rate API 조회 + fallback 정책 존재
- Section 4.5 (task_plan.md)에서 "Post-trade verification" 언급만
- **FLOW.md에는 사후 검증 규칙 없음** → 예상 수수료와 실제 수수료 차이 발생 시 대응 불가

**리스크**:
- Taker fee로 체결됨 (maker 주문이었는데)
- Fee rate가 API 조회 시점과 체결 시점 사이에 변경됨
- Slippage로 인한 가격 변동 → notional 변화 → 수수료 변화

**사례**:
```
예상:
- Maker fee: 0.01%
- Contracts: 1000
- estimated_fee_usd = $1

실제:
- Taker fee: 0.06% (maker timeout)
- Contracts: 1000
- actual_fee_usd = $6

→ EV gate를 통과했지만 실제로는 손해
→ 다음 거래도 같은 패턴 반복 → 누적 손실
```

**결론**: 사전 gate만으로는 불충분. **실제 체결 후 검증**이 없으면 수수료 스파이크 패턴을 감지하지 못함.

---

## 결정

2가지 안전 게이트를 추가하여 FLOW v1.3으로 업데이트합니다.

### 추가 1: Liquidation Distance Gate (강제)

**위치**: Section 7.5 (새로 추가)

**규칙**:
```python
# Sizing 완료 후 필수 검증
contracts = min(contracts_from_loss, contracts_from_margin)

# Gate: Liquidation distance 강제 확인
liq_distance_pct = calculate_liquidation_distance(
    entry_price=entry_price,
    contracts=contracts,
    leverage=leverage,
    direction=direction
)

# Stage별 최소 청산거리
min_liq_distance = {
    "Stage 1-2": 0.30,  # 30%
    "Stage 3": 0.20     # 20% (leverage 2x)
}

if liq_distance_pct < min_liq_distance[stage]:
    REJECT(reason=f"liquidation too close: {liq_distance_pct:.1%}")
```

**Fallback** (청산가 API 실패 시):
```python
# Conservative proxy
if leverage > 3 or stop_distance_pct > 0.05:
    contracts *= 0.8  # 20% haircut
```

---

### 추가 2: Fee Post-Trade Verification

**위치**: Section 6 확장 (Subsection 6.2 추가)

**규칙**:
```python
# 체결 완료 후 즉시 검증
def on_fill(fill_event):
    actual_fee_btc = fill_event.fee_btc
    actual_fee_usd = actual_fee_btc * fill_event.price

    # 예상 수수료 (Entry 시 계산했던 값)
    estimated_fee_usd = session.estimated_fee_usd

    # Spike 감지
    fee_ratio = actual_fee_usd / estimated_fee_usd

    if fee_ratio > 1.5:  # 50% 초과
        log_warning("fee_spike", {
            "estimated": estimated_fee_usd,
            "actual": actual_fee_usd,
            "ratio": fee_ratio
        })

        # 대응: 24시간 Entry tightening
        session.fee_spike_detected = True
        session.fee_spike_until = now() + timedelta(hours=24)

    # Tightening 중일 때
    if session.fee_spike_detected:
        # EV gate 배수 증가
        ev_gate_multiplier = stage_config.ev_gate_k * 1.5
```

**저장**:
```python
# Trade log에 필수 기록
trade_log = {
    "estimated_fee_usd": estimated_fee_usd,
    "actual_fee_usd": actual_fee_usd,
    "fee_ratio": fee_ratio,
    "fee_spike": fee_ratio > 1.5
}
```

---

## 대안

### 대안 1: Liquidation distance를 "권장사항"으로만 남김
- **거부 이유**: Stop loss 전에 청산 발생 시 손실 예산 무력화. 헌법은 "권장"이 아닌 "강제"여야 함.

### 대안 2: Fee 사후 검증 없이 API fallback만 사용
- **거부 이유**: API는 "예정" fee rate이고, 실제 체결은 다를 수 있음. Maker timeout → Taker 전환 감지 불가.

### 대안 3: 두 게이트를 task_plan.md에만 추가
- **거부 이유**: task_plan.md는 "구현 체크리스트"이고 FLOW.md는 "헌법". 강제 게이트는 헌법에 있어야 함.

---

## 결과

### 긍정적 영향
- [x] 청산 사고 방지 (Stop 전 청산 차단)
- [x] 수수료 스파이크 패턴 감지 및 대응
- [x] Maker timeout → Taker 전환 추적 가능
- [x] Stage별 안전 기준 명확화 (30%/20% liquidation distance)

### 부정적 영향 / Trade-off
- [x] Entry 기회 감소 (청산거리 게이트 추가로 일부 REJECT)
- [x] 구현 복잡도 증가 (청산가 계산 로직 필요)
- [x] Fee spike 24시간 tightening으로 기회 손실 가능

### 변경이 필요한 코드/문서
- [x] FLOW.md v1.2 → v1.3
- [ ] task_plan.md: Phase 2에 "Liquidation distance calculator" 추가 필요
- [ ] src/sizing/: Liquidation distance gate 구현 필요
- [ ] src/execution/: Fee post-trade verification 구현 필요
- [ ] src/logging/: Trade log에 fee_ratio 필드 추가 필요

---

## 실거래 영향 분석

### 리스크 변화
- **청산 리스크**: 감소 (강제 게이트로 위험 진입 차단)
- **손실 한도**: 불변 (Stop loss budget 유지, 청산 방지만 추가)
- **Emergency 대응**: 불변 (Emergency flow는 그대로)

### 백워드 호환성
- [x] 기존 포지션 영향 없음 (아직 구현 전)
- [x] 기존 설정 마이그레이션 불필요
- [x] v1.2는 미구현이므로 완전 교체 가능

### 롤백 가능성
- [x] 쉽게 롤백 가능 (Git revert)
- [ ] 데이터 마이그레이션 불필요
- [ ] 롤백 불필요 (v1.2는 미구현)

---

## 참고 자료

- Bybit Liquidation Price: https://www.bybit.com/en/help-center/article/Inverse-Perpetual-Liquidation-Price-Calculation
- Bybit Fee Rate: https://www.bybit.com/en/help-center/article/Trading-Fee-Structure
- User Review: 2026-01-18 v1.2 리뷰 중 식별된 2가지 필수 항목
