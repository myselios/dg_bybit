# TASKS.md — CBGB 현재 태스크 리스트
# 이 파일은 세션 간 작업 연속성을 위한 SSOT이다.
# Claude Code는 매 세션 시작 시 이 파일을 읽고 이어서 작업한다.

Last Updated: 2026-02-14 (12:05 KST)
Bot Status: Mainnet 실거래 중 (IN_POSITION)
Equity: ~$109 USDT
Target: $1,000 USDT

---

## 현재 설정 (Quick Reference)
- R:R Ratio: 2.14:1 (TP=ATR*1.5, SL=ATR*0.7)
- Grid Entry: ATR*0.3 spacing
- Order: GTC Limit (entry), Market (exit, reduce_only)
- Max Trades/Day: 10
- Stage: 1 ($100-$300)

---

## P0: 즉시 — 전부 완료 (2026-02-13~14)

없음. 상세 이력은 하단 "완료 이력" 참조.

## P1: 단기 (코드 품질 + 데이터 축적)

- [ ] 10건+ 트레이드 축적 후 analysis 파이프라인 실행
  - blocked_by: 트레이드 축적 대기 (현재 9건)
  - 명령어: `python scripts/analyze_trades.py`
  - 검증: 승률, PnL 분포, R:R 실측, 최대 드로다운

## P2: 중기 (데이터 기반 튜닝)

- [ ] 파라미터 2차 튜닝 (TP/SL/Grid multiplier)
  - blocked_by: P1 "10건+ 트레이드 분석" 완료
- [ ] 전략 에지 검증 (승률/Sharpe/DD)
  - blocked_by: P1 "10건+ 트레이드 분석" 완료
- [ ] Dashboard PnL/승률 표시 검증
  - blocked_by: 트레이드 10건+
- [ ] 핵심 모듈 테스트 추가
  - emergency_checker, entry_coordinator 등 테스트 없는 모듈
- [ ] Dashboard 하드코딩 값 정합성
  - Stop Distance "3%", "LONG only", Fee Rate 등 Policy 연동
- [ ] Docker healthcheck 구현
  - /health 엔드포인트 or 상태 파일 기반
- [ ] Multi-position Grid 구현
  - blocked_by: P2 "전략 에지 검증" 완료
- [ ] 2/12 구 스키마 6건 처리
  - 분석 파이프라인에서 제외 또는 partial 처리

## P3: 장기 ($1,000 스케일업)

- [ ] Stage 2 전환 ($200 달성 시)
  - blocked_by: Equity $200+
  - Leverage 3x, max_loss $20, loss_pct 8%
- [ ] Drawdown Recovery 로직
  - blocked_by: P2 "전략 에지 검증" 완료
- [ ] Backtest 프레임워크 구축
  - Bybit Historical Kline API 활용

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
