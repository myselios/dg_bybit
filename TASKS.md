# TASKS.md — CBGB 현재 태스크 리스트
# 이 파일은 세션 간 작업 연속성을 위한 SSOT이다.
# Claude Code는 매 세션 시작 시 이 파일을 읽고 이어서 작업한다.

Last Updated: 2026-03-20 (KST) — Wave 4 Stream C
Bot Status: 운영 중 (Agentic v1 + 앙상블 신호 재배포 완료 2026-03-20)
Equity: ~$110.61 USDT
Target: $1,000 USDT

---

## 현재 설정 (Quick Reference) — Agentic v1 + 앙상블
- 레버리지: 5x (Stage 1 공격 설정, 2026-03-20 변경)
- SL: ATR * 0.7 기반, clamp(0.5%~2.0%)
- TP: Trailing Stop (trail_price 대비 ATR*0.5 이탈 시 청산)
- DCA: 비활성화
- Grid Entry: ATR * 0.2 spacing
- Order: GTC Limit (entry), Market (exit, reduce_only)
- Max Trades/Day: 15 (Stage 1 공격)
- Stage: 1 ($100-$300)
- 신호: RSI+MACD+BB+Volume+MASlope+Breakout 앙상블 (score 0-7, ≥4 진입)
- Kelly 사이징: cap 25%, fallback loss_budget

---

## P0: 즉시 처리 필요

- [x] qty 버그 수정 (contracts → BTC 단위) (2026-03-07)
  - Entry/Exit: `str(contracts * 0.001)`로 수정
  - DCA: 비활성화
- [x] 전략 개편 (2026-03-07)
  - 레버리지 5x→3x
  - SL ATR 기반 (고정 2.2% 제거)
  - TP 고정값 → Trailing Stop
  - DCA 제거
- [x] 정책 문서 동기화 (policy v2.5) (2026-03-07)
- [x] **재배포 완료** (2026-03-12) — 3개 버그 수정 후 재배포
  - Wave 1: _last_entry_fill_price (exit fill 오염 방지)
  - Wave 2: orphan ENTRY/EXIT_PENDING 안전망
  - Wave 3: Grid 역추세 진입 차단 (ma_slope 필터)

## P0: 완료 (2026-03-20)

- [x] Wave 1: 앙상블 신호엔진 + Kelly사이징 + Dashboard v2 (ef242a9)
- [x] Wave 2: orchestrator 앙상블 통합 + 백테스트 검증 (27cfe35)
  - 검증 결과: 승률 34.5% → 47.4% 예상 (+12.9%p)
  - ranging 레짐 SHORT이 주 손실 원인 (-$16.83), 앙상블로 차단 예상
- [x] Wave 3: Docker 재배포 완료 (2026-03-20 19:15 KST)
  - 봇 상태: healthy, Ensemble mode 활성

## P1: 단기

- [x] Volume 지표 활성화 (ac57f09, 2026-03-20) — Kline.volume 필드 추가, bybit_adapter → orchestrator 연결
- [x] Wave 2: ReflectionAgent 앙상블 피드백 + ShadowTrader threshold 검증 (d9430f2, 2026-03-20)
- [x] 핵심 모듈 테스트: emergency_checker (100%), entry_coordinator (100%) (d9430f2)
- [x] Dashboard 정합성: LONG→LONG/SHORT, 3%→ATR×0.7 (d9430f2)
- [x] Docker healthcheck: 로그 freshness 기반 120s (d9430f2)
- [x] ENTRY_THRESHOLD 3→4 (backtest 결과: T=4 승률 12.05%, PnL -$6.51 최적) (4df6ab5, 2026-03-20)
- [ ] **Docker 재배포** (Volume + T=4 + Breakout 반영) — 사용자 승인 필요
- [ ] 앙상블 모드 10건 트레이드 축적 후 검증
  - 명령어: `python scripts/analyze_trades.py`
- [x] Wave 4 Stream C: Breakout 신호 추가 (breakout.py, 최대점수 6→7) (2026-03-20)

## P2: 중기 (데이터 기반 튜닝)

- [ ] 파라미터 2차 튜닝 (TP/SL/Grid multiplier)
- [ ] 전략 에지 검증 (승률/Sharpe/DD)
- [ ] Dashboard PnL/승률 표시 검증
- [x] 핵심 모듈 테스트 추가 (d9430f2, 2026-03-20) — emergency_checker 100%, entry_coordinator 100%
- [x] Dashboard 하드코딩 값 정합성 (d9430f2, 2026-03-20) — ATR×0.7, LONG/SHORT, Fee 0.01%
- [x] Docker healthcheck 구현 (d9430f2, 2026-03-20) — 로그 freshness 120s
- [ ] Multi-position Grid 구현
- [ ] 2/12 구 스키마 6건 처리 (분석 파이프라인에서 제외 또는 partial 처리)

## P3: 장기 ($1,000 스케일업)

- [ ] Stage 2 전환 ($200 달성 시) — Leverage 3x, max_loss $20, loss_pct 8%
- [ ] Drawdown Recovery 로직
- [ ] Backtest 프레임워크 구축 (Bybit Historical Kline API 활용)

---

## 완료 이력

| 날짜 | 태스크 | 비고 |
|------|--------|------|
| 2026-02-14 | God Object 분리 + API 감사 CRITICAL 5건 | orchestrator 1222→747줄, +29 tests |
| 2026-02-14 | Stop 관리 전면 수정 (HALT 루프 해소) | set_trading_stop API |
| 2026-02-14 | P0 크리티컬 4건 + P1 3건 수정 | 420 passed |
| 2026-02-13 | Dashboard + 로그누락 + ADR-0014 | P1 완료 |
| 2026-02-13 | Docker + Watchdog + Policy v2.4 | P0 완료 |
| 2026-02-13 | R:R 2.14:1 최적화 | TP=ATR*1.5, SL=ATR*0.7 |
| 2026-02-12 | Inverse→Linear 마이그레이션 | Mainnet 첫 거래 |

---

## 세션 시작 체크리스트

1. Bot Status: `docker ps` + `docker logs cbgb-bot --tail 5`
2. 미완료 태스크 중 unblocked 확인
3. P0→P1→P2→P3 순서로 진행
4. 완료 시 이 파일 업데이트
