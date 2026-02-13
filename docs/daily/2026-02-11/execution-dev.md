# Daily Log — Execution Dev
Date: 2026-02-11

## 1. Planned (아침 기준)
- [x] Phase A Pre-launch (A-1 ~ A-6) 완료 후 Mainnet 봇 가동
- [x] Mainnet 실거래 데이터 수집 시작

## 2. Done (팩트만, 파일/함수/커맨드 단위)

### Fix 1: Market data refresh 누락
- `scripts/run_mainnet_dry_run.py`: `update_market_data()` 30초 간격 호출 추가
- 변수: `market_data_refresh_interval = 30.0`, `last_market_refresh = 0.0`

### Fix 2: Signal threshold 조정 (T_RANGE_ENTRY)
- `src/application/signal_generator.py`: `T_RANGE_ENTRY = 0.02` 추가 (Range regime 3단계 로직)
  - Extreme funding -> 역추세 진입
  - 약한 방향성 (>= 0.02%) -> MA 방향 진입
  - Dead flat (< 0.02%) -> 보류
- `tests/unit/test_signal_generator.py`: Case 4 수정 + Case 5 (dead flat) 추가

### Fix 3: PostOnly -> GTC
- `src/application/orchestrator.py` `_decide_entry()`: `time_in_force="PostOnly"` -> `"GTC"`
- 원인: PostOnly Limit 주문이 현재가에 놓이면 Bybit가 Taker로 판정하여 취소
- `tests/unit/test_orchestrator_entry_flow.py`: assertion 수정

### Fix 4: Cancelled order state recovery
- `src/application/orchestrator.py` `_process_events()`: REST fallback에서 execution 0건 시 FLAT 복귀 로직 추가
- 이전: 주문 취소 감지 불가 -> ENTRY_PENDING 영구 잠김

### Fix 5: Grid take-profit exit
- `src/application/orchestrator.py` `_manage_position()`: ATR * 0.5 기반 take-profit 체크 추가
- SHORT: `current_price <= entry_price - (ATR * 0.5)` -> exit
- LONG: `current_price >= entry_price + (ATR * 0.5)` -> exit

### Mainnet 첫 트레이딩 사이클 완료
- Entry: SHORT 1 contract @ $68,179.50 (GTC Limit)
- Take Profit: $67,672.30 <= $67,816.53 (entry - ATR*0.5)
- Exit: Market order -> WS FILL 1초 내 수신
- State: FLAT (Cycle 1 complete)
- 410 tests passed, 15 deselected

## 3. Blocked / Issue
- Grid entry spacing ATR * 2.0 = $1,452 -> 재진입 불가 (너무 넓음)
- PnL 계산 $0.00 으로 기록됨 (trade_logger closed_pnl 확인 필요)

## 4. Decision / Change
- ADR 필요 여부: NO (기존 구현 버그 수정, 정책 변경 아님)
- PostOnly -> GTC: Bybit Linear Futures 특성상 불가피한 변경

## 5. Next Action
- Grid entry multiplier 2.0 -> 0.3 변경 (재진입 빈도 증가)
- Docker 재빌드 후 멀티 사이클 검증
- PnL 기록 검증
