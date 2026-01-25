# Phase 12a Manual Dry-Run Guide

**목표**: Testnet에서 수동으로 30-50회 거래 실행 → DoD 검증

**예상 기간**: 1-2일 (1일 10-20회 거래)

---

## 📋 Manual Dry-Run 절차

### **1단계: Testnet 준비**

```bash
# 1. Testnet 계정 준비
# https://testnet.bybit.com/
# - 회원가입 / 로그인
# - Get Testnet Funds (BTC 0.01 이상 받기)

# 2. API Key 발급 (선택 사항, 로그 조회용)
# Account & Security → API → Create New Key
# - 권한: Contract Trading (Read-only로도 가능)
# - IP 제한: 없음 (Testnet이므로)

# 3. .env 파일 설정 (로그 조회용)
cat > .env << EOF
BYBIT_API_KEY=your_testnet_api_key_here
BYBIT_API_SECRET=your_testnet_api_secret_here
BYBIT_TESTNET=true
EOF
```

---

### **2단계: 수동 거래 (30-50회)**

#### **거래 전략**:
- **Grid Trading 시뮬레이션**
- **Entry**: Limit order (PostOnly, Maker)
- **Exit**: Market order (Stop loss hit 시뮬레이션)
- **Position Size**: 100-200 contracts (작은 금액)

#### **수동 거래 절차** (1회 사이클):

```markdown
1. **Entry 주문 발주** (Bybit Testnet UI)
   - 거래소 접속: https://testnet.bybit.com/trade/inverse/BTCUSD
   - Symbol: BTCUSD
   - Order Type: Limit
   - Side: Buy (or Sell)
   - Qty: 100 contracts
   - Price: 현재 가격 -50 USD (Buy) 또는 +50 USD (Sell)
   - Time in Force: PostOnly
   - **주문 발주 → Order ID 기록**

2. **Entry 체결 대기** (1-5분)
   - Order History에서 체결 확인
   - **Filled 상태 확인 → Entry price 기록**

3. **Stop Loss 계산**
   - LONG: stop_price = entry_price * 0.97 (3% 손절)
   - SHORT: stop_price = entry_price * 1.03 (3% 손절)

4. **Exit 주문 발주** (Stop loss hit 시뮬레이션)
   - Order Type: Market
   - Side: Sell (LONG 청산) 또는 Buy (SHORT 청산)
   - Qty: 100 contracts (전량 청산)
   - **주문 발주 → Order ID 기록**

5. **Exit 체결 확인** (즉시 체결)
   - Order History에서 체결 확인
   - **Exit price 기록**
   - **Realized PnL 기록**

6. **거래 기록 (CSV)**
   ```csv
   date,cycle,entry_order_id,entry_price,exit_order_id,exit_price,pnl_usd,side
   2026-01-25,1,abc123,50000.0,def456,48500.0,-150.0,LONG
   ```

7. **다음 사이클 시작** (5-10분 후)
```

---

### **3단계: Session Risk 시뮬레이션**

#### **Daily Loss Cap 발동 시뮬레이션**:
1. **연속 손실 거래 실행** (3-5회)
2. **총 손실이 Daily Cap 초과 확인** (-5% equity)
   - Equity: 0.0025 BTC = $125 (BTC = $50,000)
   - Daily Cap: -$6.25 (-5%)
   - **실제 손실: -$7.00 이상 → HALT 조건 충족**
3. **HALT 시뮬레이션**: 거래 중단, 로그 기록

#### **Loss Streak Kill 발동 시뮬레이션**:
1. **연속 손실 거래 3회 실행**
2. **Loss streak = 3 확인 → HALT 조건 충족**
3. **HALT 시뮬레이션**: 거래 중단

---

### **4단계: 로그 기록 (CSV)**

#### **수동 로그 파일: `logs/testnet_dry_run/trades_manual.csv`**

```csv
date,cycle,entry_order_id,entry_price,entry_time,exit_order_id,exit_price,exit_time,pnl_usd,side,notes
2026-01-25 10:00:00,1,abc123,50000.0,2026-01-25 10:01:30,def456,48500.0,2026-01-25 10:05:00,-150.0,LONG,Stop loss hit
2026-01-25 10:15:00,2,ghi789,50100.0,2026-01-25 10:16:45,jkl012,50300.0,2026-01-25 10:20:00,+40.0,LONG,Profit
2026-01-25 10:30:00,3,mno345,50200.0,2026-01-25 10:31:20,pqr678,49800.0,2026-01-25 10:35:00,-200.0,LONG,Stop loss hit
...
```

---

### **5단계: 검증 스크립트 실행**

```bash
# 1. CSV 로그 분석
python scripts/analyze_manual_trades.py logs/testnet_dry_run/trades_manual.csv

# 예상 출력:
# ========== Manual Trades Analysis ==========
# Total trades: 30
# Win/Loss: 15/15
# Winrate: 50.0%
# Total PnL: -$45.00
# Max loss streak: 3
# Daily Loss Cap exceeded: Yes (Daily PnL: -$7.00 < -$6.25)
# ============================================

# 2. Bybit Testnet API로 실제 거래 내역 조회 (검증)
python scripts/fetch_testnet_trades.py --start-date 2026-01-25

# 3. CSV vs API 일치 확인
python scripts/verify_trades.py logs/testnet_dry_run/trades_manual.csv logs/testnet_dry_run/trades_2026-01-25.json
```

---

### **6단계: Evidence 작성**

#### **Checklist 작성: `docs/evidence/phase_12a/dry_run_checklist.md`**

```markdown
## ✅ Phase 12a Manual Dry-Run 완료

### 1. Testnet 거래 실행
- [x] Total trades: 30 / 30
- [x] Successful cycles: 30
- [x] CSV 로그 기록 완료: logs/testnet_dry_run/trades_manual.csv

### 2. Session Risk 발동 증거
- [x] Daily Loss Cap 발동: 1회 (Day 2, -$7.00 < -$6.25)
- [x] Loss Streak Kill 발동: 1회 (Day 1, 3연패)

### 3. Stop Loss 작동
- [x] Stop loss hits: 12 / 5 (최소 5회 이상)

### 4. 로그 완전성
- [x] 모든 거래 기록됨: 30 / 30

### 5. Bybit Testnet UI 스크린샷
- [x] Order History 스크린샷 첨부
- [x] Position History 스크린샷 첨부
- [x] Realized PnL 스크린샷 첨부

## 📊 통계 요약
- Total trades: 30
- Winrate: 50.0%
- Total PnL: -$45.00
- Session Risk halts: 2 (Daily cap + Loss streak)

## 🎯 Phase 12a 완료
Status: ✅ COMPLETE
Next: Phase 12b (Mainnet Dry-Run)
```

---

## 📌 Manual Dry-Run 장점

1. **즉시 시작 가능**: 복잡한 구현 없이 오늘부터 시작
2. **실제 거래소 동작 검증**: Bybit Testnet의 실제 주문 흐름 확인
3. **Session Risk 정확한 시뮬레이션**: 실제 손실로 Daily/Weekly Cap 테스트
4. **DoD 완전 충족**: 30회 거래, Session Risk 발동, 로그 완전성 모두 검증 가능

---

## 🚀 시작 방법

```bash
# 1. Testnet 계정 준비 (위 1단계)
https://testnet.bybit.com/

# 2. CSV 로그 파일 생성
touch logs/testnet_dry_run/trades_manual.csv
echo "date,cycle,entry_order_id,entry_price,entry_time,exit_order_id,exit_price,exit_time,pnl_usd,side,notes" > logs/testnet_dry_run/trades_manual.csv

# 3. 첫 번째 거래 시작 (위 2단계)
# → Bybit Testnet UI에서 수동 주문 발주

# 4. 거래 후 CSV에 기록
echo "2026-01-25 10:00:00,1,abc123,50000.0,2026-01-25 10:01:30,def456,48500.0,2026-01-25 10:05:00,-150.0,LONG,Stop loss hit" >> logs/testnet_dry_run/trades_manual.csv

# 5. 30회 반복
```

---

**예상 일정**:
- Day 1: 10-15회 거래 (Loss streak 발동 시뮬레이션)
- Day 2: 15-20회 거래 (Daily cap 발동 시뮬레이션)
- Day 3: 검증 및 Evidence 작성

**완료 시**: ✅ Phase 12b (Mainnet Dry-Run) 진행 가능
