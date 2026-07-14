# TASKS.md — CBGB 현재 태스크 리스트
# 이 파일은 세션 간 작업 연속성을 위한 SSOT이다.
# Claude Code는 매 세션 시작 시 이 파일을 읽고 이어서 작업한다.

Last Updated: 2026-07-13 (KST) — 전체 감사 + 신뢰성 복구 (Phase 0~2) 완료
Bot Status: 중지 (2026-03-27 이후, 실행 컨테이너 없음). 재가동은 strategy_v3 게이트 통과 후
Equity: **$108.72** (2026-07-13 거래소 API 실측) — 거래소 원장 대사 완결 (오차 $0.17):
  입금 $128.74 (1/18) | BTCUSDT 봇 -$30.94/205건 (1월 테스트 -$25.33, 2~3월 운영 -$5.61) | ETHUSDT 수동 +$10.91 | funding -$0.16
  → 실투입 자본 대비 총 성과 **-15.6%**. 이전 표기 $113.5(롤링 오류)·$88.83(로그 누락, 커버리지 ~30%) 모두 부정확
Target: $1,000 USDT

---

## 현재 설정 (Quick Reference) — Agentic v1 + 앙상블
- 레버리지: 5x (Stage 1 공격 설정, 2026-03-20 변경)
- SL: ATR * 0.7 기반, clamp(0.5%~2.0%)
- TP: Trailing Stop (trail_price 대비 ATR*0.5 이탈 시 청산)
- DCA: 비활성화
- Grid Entry: ATR * 0.3 spacing (Wave 5 개선)
- Order: GTC Limit (entry), Market (exit, reduce_only)
- Max Trades/Day: 15 (Stage 1 공격)
- Stage: 1 ($100-$300)
- 신호: RSI+MACD+BB+Volume+MASlope+Breakout 앙상블 (score 0-7, ≥4 진입)
- Kelly 사이징: cap 25%, fallback loss_budget

---

## P0: 재가동 전 필수 (2026-07-13 전체 감사 결과)

- [x] Phase 0: 회계 재정립 (2026-07-13)
  - trade_analyzer.py 버그 2건 수정 (hold_seconds 필드명, MDD equity 기준)
  - scripts/reconcile_equity.py 신규 — 재구성 Equity $88.83
  - TASKS.md Equity 팩트 교정
- [x] Phase 1: 배포 신뢰성 (2026-07-13)
  - 원인 확정: redeploy.sh macOS 경로로 no-op + .env GIT_COMMIT 수동값
  - 빌드 시점 커밋 이미지에 굽기(BUILD_COMMIT) + 배포 후 검증(불일치 시 exit 1)
- [x] Phase 2: 안전장치 배선 (2026-07-13)
  - 진입 주문 stopLoss 첨부, SL 계산 단일화(ATR*0.7/0.5~2.0%)
  - set_leverage 기동 호출 + 실패 시 진입 차단, liquidation_gate 연결
  - DrawdownRecovery size_multiplier 주문 미반영 버그 수정 (orchestrator.py)
- [x] 거래소 원장 대사 완결 (2026-07-13) — 헤더 Equity 참조. API 키 재발급 완료
- [x] bybit_rest_client GET 서명 버그 수정 (2026-07-13) — 서명(sorted) vs 전송(삽입 순서) 불일치 → retCode 10004. 회귀 테스트 추가
- [ ] **사용자 액션 대기**: (a) 텔레그램 토큰 로테이션 (redeploy.sh 이력 노출), (b) 레버리지 3x 복귀 승인
- [ ] 트레이드 로깅 커버리지 수리: 거래소 169건 vs 로컬 51건 (2~3월). 로깅 누락 경로 조사 + 일일 대사를 거래소 closed-pnl 기반으로 전환 (reconcile_equity.py 확장)
- [ ] Phase 3: 정책 수치 단일화 ADR (Sec5 vs Sec6 vs config vs 코드) + config 실로딩
- [x] Phase 4-G1: strategy_v3 백테스트 → **FAIL** (앙상블 엣지 없음 확정: 6개월 gross +$23 vs fee $514). 신호버그 확인: breakout 영구0점, MACD 크로스 오판정 (2026-07-13)
- [x] Strategy v4 설계 + G1 통과 (2026-07-13): 일봉 TSM, 2년 백테스트 +0.125R/건, 9개 파라미터 전부 양, P(엣지>0)=80% — docs/plans/strategy_v4.md
- [x] **v4 채택 확정** (사용자, 2026-07-13): 리스크 티어 **5%** → ADR-0015
- [x] v4 구현 완료 (2026-07-13): src/application/tsm_signal.py (백테스트 비트단위 패리티 검증) + tsm_trader.py (Decimal 사이징, funding 필터, 거래소 SL 첨부) + scripts/run_tsm_daily.py (shadow 기본). 847 passed. shadow 1회 실행 검증 완료 (no_signal — 시장 교차검증 일치)
- [x] **실거래 전환** (사용자 결정 2026-07-14, G2 shadow 생략): 첫 실거래 SHORT 0.001 BTC @ $62,467.8, 스탑 $67,351 거래소 상주 검증. 크론 live 전환 (00:10 UTC). ADR-0015 개정
- [x] 레버리지 3x 강제 (2026-07-14): 계좌 5x→3x 설정 + tsm_trader._ensure_leverage()로 진입 시 강제. 마진모드는 계좌가 이미 ISOLATED_MARGIN(UTA 2.0)으로 확인 — 정책 정합
- [ ] 가드레일 equity<$90 자동강제: **사용자 지시로 보류(안 함)**
- [ ] 별건 버그 수정: bybit_rest_client.set_margin_mode()가 set-leverage로 POST(tradeMode 무시) → 마진모드 전환 불가. ADR-0012 미작동. `/v5/account/set-margin-mode`로 수정 (TSM 미사용이라 P2)
- [ ] G3 평가: 첫 15건 누적 후 기대값 R>0 확인 → 유지/중단. 실거래 로그(logs/tsm_shadow/ shadow:false) 기반
- [ ] $1,000 목표 처리 결정 잔존: 입금 증액 / 목표 수정 / 멀티심볼 확장
- [ ] liq gate 정식화: get_position liqPrice 연동 (현 근사식은 보수적 임시)

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
- [x] **Docker 재배포** (Wave 5 전체 반영: regime filter + Post-Only + DrawdownRecovery) (2026-03-23, cf0703a)
- [ ] 앙상블 모드 10건 트레이드 축적 후 검증
  - 명령어: `python scripts/analyze_trades.py`
- [x] Wave 4 Stream C: Breakout 신호 추가 (breakout.py, 최대점수 6→7) (2026-03-20)

## P1: Wave 5 (2026-03-23)

- [x] Wave 5 Stream C: Drawdown Recovery 구현 (2026-03-23)
  - `src/application/drawdown_recovery.py` 신규 (pure function, frozen dataclass)
  - `tests/unit/test_drawdown_recovery.py` 14 테스트 통과
  - orchestrator.py 통합: sizing 후 size_multiplier 적용 (REDUCE×0.7, HALT×0.0)
  - 날짜 기반 자동 복구 (UTC 0시)
- [x] Backtest 분석 — T=3 vs T=4 (2026-03-23)
  - T=4 유지 결정: 승률 12.56%, 손실 -$6.60 (T=3: 11.18%, -$19.73)
  - `scripts/run_backtest.py` _score() 버그 수정 (sharpe×win_rate→net_pnl 기반)
- [x] Wave 5 Stream A: signal_score 보존 버그 수정 + 레짐 방향 필터 (2026-03-23, cf0703a)
- [x] Wave 5 Stream B: Post-Only + Trailing ATR*0.8 임계값 + Grid×0.3 (2026-03-23, cf0703a)
- [x] Wave 5: Docker 재배포 완료 (2026-03-23 09:26 KST)
- [ ] 실거래 10건 이상 후 앙상블 score 기반 트레이드 검증

## P2: 중기 (데이터 기반 튜닝)

- [ ] 파라미터 2차 튜닝 (TP/SL/Grid multiplier)
- [ ] 전략 에지 검증 (승률/Sharpe/DD)
- [ ] Dashboard PnL/승률 표시 검증
- [x] 핵심 모듈 테스트 추가 (d9430f2, 2026-03-20) — emergency_checker 100%, entry_coordinator 100%
- [x] Dashboard 하드코딩 값 정합성 (d9430f2, 2026-03-20) — ATR×0.7, LONG/SHORT, Fee 0.01%
- [x] Docker healthcheck 구현 (d9430f2, 2026-03-20) — 로그 freshness 120s
- [ ] Multi-position Grid 구현
- [ ] 2/12 구 스키마 6건 처리 (분석 파이프라인에서 제외 또는 partial 처리)

## P2: Wave 6 (2026-03-24 완료)

- [x] Wave 6 Stream A: ranging threshold 상향 (score≥4→5) (b6b0c98, 2026-03-24)
  - ranging 레짐에서 false positive 줄이기 위해 임계값 5로 상향
- [x] Wave 6 Stream B: analyze_trades.py default 필드 수정 (121a4ee, 2026-03-24)
  - signal_score=null 트레이드 (2건 확인) partial 처리
  - signal_components=null 처리 로직 추가
- [ ] Wave 6 Stream C: Post-Only fee 검증 ($0.02 이하 확인)
  - blocked_by: Wave 5 트레이드 첫 건 발생 후
  - 명령어: `cat logs/mainnet/trades_*.jsonl | python3 -c "..."` fee_usd 집계

## P1: Wave 7 (2026-03-25)

- [ ] Wave 7 Stream A: hold_seconds 음수 버그 수정 (bybit_adapter.py ms→s)
- [ ] Wave 7 Stream B: .env GIT_COMMIT 업데이트 + 트레이드 분석
- [x] Wave 7 Stream C: TASKS.md 정리 + 작업일지 생성 (2026-03-25)
- [ ] 어제 Wave 5 코드 첫 실거래 Post-Only fee 검증 (fee=$0.115 분석)

## P3: 장기 ($1,000 스케일업)

- [ ] Stage 2 전환 ($200 달성 시) — Leverage 3x, max_loss $20, loss_pct 8%
- [x] Drawdown Recovery 로직 (2026-03-23, Wave 5 Stream C)
- [x] Backtest 프레임워크 구축 (Bybit Historical Kline API 활용) (2026-03-20)

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
