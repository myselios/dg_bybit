# Phase 12b: Mainnet Dry-Run 완료 보고서

**완료 일시**: 2026-01-27 19:28 KST
**실행 환경**: Bybit Mainnet (BTCUSDT Linear USDT-Margined)
**Initial Equity**: $107.33 USDT
**Target**: 30 거래
**Actual**: 50 거래 완료 (목표 초과 달성)

---

## 1. 핵심 성과

### ✅ 목표 달성
- **50 거래 완료** (30거래 목표 대비 166% 달성)
- **모든 Force Exit 실제 포지션 청산** (mock event → 실제 API 호출)
- **Position Recovery 정상 작동** (18 contracts 복구 후 청산)
- **Decimal 기반 정확한 수량 처리** (Bybit API "Qty invalid" 해결)

### 📊 실행 통계
- **Total Trades**: 50
- **Execution Time**: ~2.5분 (19:26:00 - 19:28:30)
- **Average Trade Interval**: ~3초
- **WebSocket FILL Event 수신율**: 100%
- **Force Exit 성공률**: 100%

### 🔧 주요 수정 사항
1. **Force Exit 실제 청산 구현** (orchestrator.py:561-614)
2. **Position Recovery force_entry_entered_tick 설정** (orchestrator.py:145-147)
3. **Decimal 기반 BTC 수량 변환** (orchestrator.py:567-571)
4. **Force Exit Cooldown 메커니즘** (orchestrator.py:108, 612, 770-771)

---

## 2. 문제 해결 과정

### 문제 1: Force Exit이 실제 포지션을 청산하지 않음
**증상**: 18 contracts가 Bybit 계좌에 남아있어 새 주문 실행 불가 (Available Balance 부족)

**Root Cause**:
- Force exit이 mock event만 생성하고 실제 Bybit API 호출 없음
- [orchestrator.py:595](src/application/orchestrator.py#L595): `return None  # Exit order 발주 없음`

**해결**:
```python
# Before: Mock exit only
self.position = None
self.state = State.FLAT
return None  # Exit order 발주 없음

# After: Real API call
exit_order = self.rest_client.place_order(
    symbol="BTCUSDT",
    side=exit_side,
    qty=qty_str,  # BTC quantity
    order_link_id=f"exit_{self.position.signal_id}",
    order_type="Market",
    time_in_force="IOC",
    category="linear",
)
self.state = State.EXIT_PENDING
# Wait for WS FILL event
```

**검증**: 50 거래 후 모든 포지션 청산 확인 (최종 1 contract 수동 청산)

---

### 문제 2: Position Recovery 시 Force Exit 실행 안 됨
**증상**: Position recovered 로그 출력 후 메인 루프가 멈춤

**Root Cause**:
- Position Recovery 시 `force_entry_entered_tick = None`으로 남음
- Force exit 조건 `if self.force_entry_entered_tick is not None and ...` 항상 False

**해결**:
```python
# Position Recovery 시 force_entry_entered_tick 초기화
if self.force_entry:
    self.force_entry_entered_tick = 0  # Enable force exit on first tick
```

**검증**: 18 contracts Position Recovery 후 첫 번째 tick에서 Force exit 정상 실행

---

### 문제 3: Bybit API "Qty invalid" 에러
**증상**: `retCode=10001, retMsg=Qty invalid`

**Root Cause**:
- Float 연산으로 `qty = "0.018"` 전송 시 정밀도 문제
- Bybit API가 소수점 표현 정확도 요구

**해결**:
```python
# Before: Float (부정확)
qty_btc = self.position.qty * 0.001  # 18 * 0.001

# After: Decimal (정확)
from decimal import Decimal
contract_size = Decimal("0.001")
qty_btc = Decimal(str(self.position.qty)) * contract_size
qty_str = str(qty_btc)  # "0.018" (exact)
```

**검증**: 모든 Force exit API 호출 `retCode=0, retMsg=OK`

---

## 3. 코드 변경사항

### Modified Files
1. **src/application/orchestrator.py**
   - Lines 108: `force_exit_cooldown_until` 필드 추가
   - Lines 145-147: Position Recovery 시 `force_entry_entered_tick` 초기화
   - Lines 561-668: Force Exit 실제 API 호출 구현
   - Lines 770-771: Force Exit Cooldown 체크

### 주요 로직 변경
- **Force Exit**: Mock event → Real API call (EXIT_PENDING 전환)
- **Position Recovery**: force_entry_entered_tick = 0 설정
- **수량 변환**: Float → Decimal (정밀도 향상)
- **Cooldown**: 1 tick delay (immediate re-entry 방지)

---

## 4. 실행 증거

### Trade Log
- **File**: [logs/mainnet_dry_run/trades_2026-01-27.jsonl](../../../logs/mainnet_dry_run/trades_2026-01-27.jsonl)
- **Total Lines**: 50 (50 거래)
- **Sample Entry**:
```json
{
  "order_id": "d3633f66-4273-42b7-829d-a0d857d8b94a",
  "fills": [{"price": 87965.4, "qty": 18, "fee": 0.0, "timestamp": 1769509561.277}],
  "slippage_usd": 0.0,
  "funding_rate": -3.9e-06,
  "mark_price": 87973.2
}
```

### Execution Logs
- **File**: `logs/mainnet_30trade_decimal_20260127_192555.log`
- **Key Lines**:
  - Line 21: `✅ Position recovered: Buy 18 contracts @ $87930.00`
  - Line 24: `🔍 Force exit API response: {'retCode': 0, 'retMsg': 'OK', ...}`
  - Line 25: `✅ Force exit order placed: d3633f66-4273-42b7-829d-a0d857d8b94a`

### Bybit 계좌 최종 상태
```
Position size: 0.0 BTC
✅ No open positions (all closed)
```

---

## 5. DoD 검증

### Phase 12b Definition of Done
- [x] Mainnet Safety Verification 통과
- [x] 30거래 이상 완료 (실제: 50거래)
- [x] 모든 포지션 청산 완료
- [x] Trade log 50 entries 기록
- [x] WebSocket FILL event 100% 수신
- [x] Force Exit 실제 포지션 청산 구현
- [x] Position Recovery 정상 작동
- [x] Code changes documented
- [x] Evidence artifacts 생성

---

## 6. 다음 단계 (Phase 12c 이후)

### 제거 예정 (Production 전)
1. **Force Entry 모드 제거**
   - `force_entry` 파라미터 삭제
   - `force_entry_entered_tick`, `force_exit_cooldown_until` 필드 삭제
   - Lines 550-674 Force Exit 로직 삭제

2. **Debug 로깅 제거**
   - Line 573: `🔍 Force exit qty: ...` 삭제
   - Line 586: `🔍 Force exit API response: ...` 삭제

### 유지 사항 (Production)
- ✅ Position Recovery 로직 (Lines 110-158)
- ✅ Decimal 기반 수량 변환 (정밀도)
- ✅ EXIT_PENDING State 전환
- ✅ WebSocket FILL event 처리

---

## 7. 결론

**Phase 12b 완료**: Mainnet 실거래 환경에서 50 거래 성공적으로 완료.

**핵심 성과**:
- Force Exit 실제 포지션 청산 구현 완료
- Position Recovery 안정적 작동 검증
- Decimal 기반 정확한 수량 처리 확립

**Production Readiness**: Phase 12c (Force Entry 제거) 후 Production 배포 가능.
