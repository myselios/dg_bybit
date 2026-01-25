# Phase 12a Testnet Dry-Run Checklist

**Date**: YYYY-MM-DD
**Duration**: XX hours
**Operator**: [Your Name]

---

## ✅ DoD (Definition of Done) 체크리스트

### 1. Testnet 거래 실행 (30-50회)

- [ ] **Total trades**: ___ / 30 (최소 30회)
- [ ] **Successful cycles**: ___ (FLAT → Entry → Exit → FLAT 완료)
- [ ] **Failed cycles**: ___ (Entry 실패 또는 오류)
- [ ] **Bybit Testnet UI 스크린샷 첨부** (Order History, Position History)

---

### 2. Session Risk 발동 증거 (최소 1회)

- [ ] **Daily Loss Cap 발동**: ___ 회 (Expected: ≥ 1)
  - Log 증거: `grep "daily_loss_cap_exceeded" logs/testnet_dry_run.log`
  - Daily PnL: -$___ / -$___ (cap)

- [ ] **Weekly Loss Cap 발동**: ___ 회 (Optional)
  - Log 증거: `grep "weekly_loss_cap_exceeded" logs/testnet_dry_run.log`
  - Weekly PnL: -$___ / -$___ (cap)

- [ ] **Loss Streak Kill 발동**: ___ 회 (Optional)
  - Log 증거: `grep "loss_streak_kill" logs/testnet_dry_run.log`
  - Max loss streak: ___ (Expected: ≥ 3)

- [ ] **Slippage Anomaly 발동**: ___ 회 (Optional)
  - Log 증거: `grep "slippage_anomaly" logs/testnet_dry_run.log`

---

### 3. Stop Loss 정상 작동 (최소 5회)

- [ ] **Stop loss hits**: ___ / 5 (최소 5회)
- [ ] **Stop loss 로그 확인**: `grep "Stop loss hit" logs/testnet_dry_run.log`
- [ ] **Bybit Testnet UI 확인**: Exit 주문이 Market order로 체결됨

---

### 4. Fee Tracking 정상 작동

- [ ] **모든 거래에서 fee 기록됨**: Yes / No
- [ ] **Trade Log에 fee 필드 존재**: `cat logs/testnet_dry_run/trades_*.jsonl | jq '.fills[].fee'`
- [ ] **Fee spike 감지 (Optional)**: ___ 회

---

### 5. Slippage Tracking 정상 작동

- [ ] **모든 거래에서 slippage 기록됨**: Yes / No
- [ ] **Trade Log에 slippage_usd 필드 존재**: `cat logs/testnet_dry_run/trades_*.jsonl | jq '.slippage_usd'`

---

### 6. 로그 완전성 검증

- [ ] **모든 거래가 trade_log에 기록됨**: Yes / No
- [ ] **Trade Log 개수**: ___ (Expected: == Successful cycles)
- [ ] **검증 스크립트 실행**: `python scripts/analyze_session_risk.py logs/testnet_dry_run/`

---

### 7. Daily/Weekly PnL 계산 정확성

- [ ] **Daily PnL 계산 정확**: Yes / No
- [ ] **Weekly PnL 계산 정확**: Yes / No
- [ ] **Loss streak count 정확**: Yes / No

---

### 8. 발견된 문제 및 해결 방안

**문제 1**:
- 설명: _______
- 재현 방법: _______
- 해결 방안: _______

**문제 2**:
- 설명: _______
- 재현 방법: _______
- 해결 방안: _______

---

## 📊 통계 요약

| Metric | Value |
|--------|-------|
| Total trades | ___ |
| Successful cycles | ___ |
| Failed cycles | ___ |
| Stop loss hits | ___ |
| Session Risk halts | ___ |
| Emergency halts | ___ |
| Winrate | ___% |
| Total PnL | $____ |
| Max loss streak | ___ |
| Duration | ___ hours |

---

## 🎯 Phase 12a 완료 기준

- [x] Testnet 30-50회 거래 성공
- [x] Session Risk 발동 증거 1회 이상
- [x] 로그 완전성 100% (모든 거래 기록)
- [x] Testnet Dry-Run Report 작성 완료

**Status**: ✅ COMPLETE / ⏳ IN PROGRESS / ❌ FAILED

**Next Step**: Phase 12b - Mainnet Dry-Run

---

## 📎 첨부 파일

- [ ] `logs/testnet_dry_run.log` (전체 로그)
- [ ] `logs/testnet_dry_run/trades_*.jsonl` (Trade Log)
- [ ] Bybit Testnet UI 스크린샷 (Order History, Position History)
- [ ] Session Risk 발동 스크린샷
- [ ] `pytest -q` 실행 결과 (회귀 테스트)
