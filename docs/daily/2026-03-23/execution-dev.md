# Daily Log — CBGB Dev Team (Autonomous)
Date: 2026-03-23

## 1. Planned (아침 기준)
- [x] Wave 5 Stream A: signal_score 보존 버그 수정 + 레짐 방향 필터
- [x] Wave 5 Stream B: Post-Only 주문 + Trailing 임계값 + Grid spacing 개선
- [x] Wave 5 Stream C: DrawdownRecovery 구현 + 백테스트 재검증
- [x] pytest -q 769 통과 확인 + 커밋 + push
- [x] Docker 재배포 (Wave 5 반영)

## 2. Done (팩트만, 파일/함수/커맨드 단위)

### Wave 5 Stream A (17 tests)
- `src/application/orchestrator.py`
  - `_entry_signal_score`, `_entry_signal_components` 인스턴스 변수 추가
  - EXIT pending_order 처리 시 signal_score 덮어쓰기 버그 수정
  - `_classify_regime()` static method: trending_up/trending_down/ranging/high_vol
  - `_decide_entry()`: trending_down→Buy 차단, trending_up→Sell 차단
- `tests/unit/test_wave5a_regime_filter.py`: 17 tests

### Wave 5 Stream B (13 tests)
- `src/infrastructure/exchange/bybit_rest_client.py`
  - `place_order(is_post_only=True)` — Maker fee 0.01% 보장
- `src/application/orchestrator.py`
  - `_compute_adaptive_trail_distance()`: ATR*0.8 활성화 임계값 추가
  - Grid spacing multiplier: 0.2→0.3
- `tests/unit/test_wave5_streamb.py`: 13 tests

### Wave 5 Stream C (14 tests)
- `src/application/drawdown_recovery.py` 신규 생성
  - NORMAL: 일손실 < 50% → size×1.0
  - REDUCE: 50~80% → size×0.7
  - HALT: ≥80% → size×0.0 (당일 거래 중단)
  - UTC 0:00 자동 리셋
- `src/application/orchestrator.py`: drawdown_multiplier 통합
- `scripts/run_backtest.py`: _score() 함수 sharpe*win_rate→net_pnl-max_dd*0.5 수정
- `tests/unit/test_drawdown_recovery.py`: 14 tests
- 백테스트 재확인: ENTRY_THRESHOLD=4 최적 (223 trades, 12.56% win, -$6.60 PnL)

### 커밋/배포
- `pytest -q`: 769 passed, 3 pre-existing failures (docker + testnet)
- `git commit cf0703a`: [feat] Wave 5 전체
- `git push origin feature/cbgb-v3-profit-fix`
- `docker compose build --no-cache bot` → `docker compose up -d bot`
- 봇 상태: healthy, score=1 (BTC $68,124 횡보/하락)

## 3. Blocked / Issue
- score=1 지속: BTC $68k 하락 추세, ma_slope=-0.0814% → 레짐 필터가 Buy 차단 (정상 동작)
- 실거래 데이터 0건 (Wave 5 배포 후 첫 트레이드 대기 중)

## 4. Decision / Change
- ADR 필요 여부: NO (파라미터 조정, 버그 수정 범위)
- DrawdownRecovery: Stage 1 max_loss=$15 기준 50%($7.5)/80%($12) 임계값

## 5. Next Action (내일)
- Wave 5 코드 기반 트레이드 축적 대기 (목표: 10건 이상)
- `python scripts/analyze_trades.py` 실행 후 R:R 실측 검증
- BTC 반등 시 score≥4 달성 여부 모니터링
- TASKS.md P2: Multi-position Grid 구현 검토

---
<!-- 강제 규칙:
  ❌ 감정 표현 금지
  ❌ "검토함", "고민함", "열심히 했다" 금지
  ✅ 파일명 / 함수명 / 커맨드 결과 필수
  ✅ Blocked는 24시간 이상 방치 금지 (다음날 잔존 시 Architect Review 대상)
-->
