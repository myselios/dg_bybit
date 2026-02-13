# Phase 1.1 Patch Notes
**Date**: 2026-02-01
**Reason**: Critical factual errors identified by user feedback

---

## 문제 진단 (User Feedback)

**판정**: HOLD - 문서 구조는 좋지만, 실거래에서 죽는 지점이 명확히 보임

### 치명적 문제 Top 5

1. **Contract 단위 애매함**: "1 contract = 0.001 BTC"는 Bybit Linear USDT Perp 스펙과 다를 가능성
2. **Rate limit 정책 불일치**: "120 req/min" 고정은 틀림, v5는 per-second rolling + 헤더 기반
3. **Risk Cap 정의 불명확**: Daily -5%, Weekly -12.5%의 기준(equity vs realized), 리셋 타이밍(UTC? KST?) 불명
4. **WS "max_active_time 10분" 위험**: 재연결 순간 이벤트 드랍/순서 꼬임 위험
5. **"방식 B" 내부 용어**: 운영자가 이해 불가, 실제 API 파라미터 없음

---

## 수정 내용 (Phase 1.1 Patch)

### 1. Section 1.4 Definitions 추가 ✅
**변경**:
- Product, Qty 단위, Equity/PnL, Time boundaries, Rate limit, Stop Loss 파라미터 명확히 정의
- **Contract 단위 HOLD**: "1 contract = 0.001 BTC" 보류, Bybit API 확인 필수 명시

**근거**:
- account_builder_policy.md Section 1 참조
- session_risk_tracker.py (UTC boundary)
- bybit_rest_client.py (Rate limit 헤더)
- order_executor.py (Stop Loss 파라미터)

### 2. Section 1.3 Constraints 수정 ✅
**변경**:
- ❌ 삭제: "Contract: BTCUSDT (1 contract = 0.001 BTC)"
- ❌ 삭제: "Rate Limit: 120 req/min (Bybit 공식), 내부 예산 90 req/min (75%)"
- ✅ 추가: "Symbol: BTCUSDT Linear Perpetual"
- ✅ 추가: "Rate Limit: X-Bapi-* 헤더 기반 throttle + retCode=10006 우선 감지"

### 3. Section 1.3 Risk Cap 명확화 ✅
**변경**:
- ✅ 추가: "Equity 정의: equity_usdt = wallet_balance_usdt + unrealized_pnl_usdt (미실현 손익 포함)"
- ✅ 추가: "Daily Loss Cap: -5% equity (UTC boundary 기준, 당일 realized PnL 누적)"
- ✅ 추가: "Weekly Loss Cap: -12.5% equity (UTC boundary 기준, 주간 realized PnL 누적)"
- ✅ 추가: "Loss Streak Kill: 3연패 시 HALT (거래 단위, 부분청산 포함)"

### 4. Section 1.2 Core Principles #6 수정 ✅
**변경**:
- ❌ 삭제: "WebSocket ping-pong + max_active_time 정책 (10분 무활동 시 연결 종료)"
- ❌ 삭제: "StopLoss 방식 B 고정 (혼용 금지)"
- ✅ 추가: "Rate limit 감지 (우선순위 순): retCode=10006 → X-Bapi-Limit-Status < 20% → 내부 예산(참고용)"
- ✅ 추가: "WebSocket 정합성: Heartbeat (ping-pong), Reconnection, Event drop 감지 → DEGRADED"
- ✅ 추가: "주의: 'max_active_time 10분'은 Bybit 서버측 제약이지, 클라이언트가 능동적으로 끊는 게 아님"
- ✅ 추가: "Stop 주문 파라미터: orderType=Market, triggerBy=LastPrice, reduceOnly=True, positionIdx=0"

---

## 검증 결과

### 파일 경로 검증
```bash
$ grep -oE 'src/[a-z_/]+\.py' docs/base/operation.md | sort -u | while read f; do
  if [ ! -f "$f" ]; then
    echo "MISSING: $f"
  fi
done

✅ All file paths exist
```

### 문서 크기
```bash
$ wc -l docs/base/operation.md
827 docs/base/operation.md (771 → 827, +56줄)
```

### SSOT 일치성
- ✅ account_builder_policy.md Section 1 (Equity, Contract 단위 경고)
- ✅ session_risk_tracker.py (UTC boundary, Daily/Weekly PnL)
- ✅ bybit_rest_client.py (X-Bapi-* 헤더, retCode=10006)
- ✅ order_executor.py (Stop Loss 파라미터)

---

## 남은 위험 요소

### 1. Contract 단위 미확정 ⚠️
**상태**: HOLD (보류)
**조치 필요**: 실거래 전 Bybit API `/v5/market/instruments-info?category=linear&symbol=BTCUSDT` 확인
**근거**: account_builder_policy.md에 "0.001 BTC per contract" 명시되어 있으나, Bybit 스펙 확인 필요

### 2. Loss Streak 정의 불완전 ⚠️
**상태**: "거래 단위, 부분청산 포함"으로 명시했으나, 실제 코드 확인 필요
**조치 필요**: session_risk_tracker.py의 loss_streak 로직 확인 (Phase 3에서 상세 문서화)

### 3. WS "max_active_time" 정책 불명확 ⚠️
**상태**: 코드에서 명확한 "10분" 정책 없음, ping-pong timeout만 존재
**조치 필요**: bybit_ws_client.py 코드 정밀 확인 + Bybit 공식 문서 대조 (Phase 4)

---

## 다음 단계

**Phase 2 시작 전 추가 확인**:
1. Bybit API Instruments Info 조회 (Contract 단위 확정)
2. session_risk_tracker.py loss_streak 로직 확인
3. bybit_ws_client.py ping-pong timeout 정책 확인

**Phase 2 작업 시 반영**:
- State Machine 문서화 시 위 Definitions 섹션 참조
- Event 우선순위에 "Rate limit backoff" 포함
- Stop Loss 파라미터 상세 설명 (API 예시 포함)

---

**Updated**: 2026-02-01
**Status**: ✅ Phase 1.1 Patch COMPLETE
**Next**: Phase 2 - State Machine & Event Flow
