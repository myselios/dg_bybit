# TASKS.md — CBGB 현재 태스크 리스트
# 이 파일은 세션 간 작업 연속성을 위한 SSOT이다.
# Claude Code는 매 세션 시작 시 이 파일을 읽고 이어서 작업한다.
#
# 규칙:
# - 태스크 완료 시 상태를 [x]로 변경하고 완료일 기록
# - 새 태스크 발견 시 적절한 우선순위에 추가
# - 차단된 태스크는 blocked_by 명시
# - 각 세션 종료 시 이 파일 업데이트 필수

Last Updated: 2026-02-13
Bot Status: Mainnet 실거래 중 (IN_POSITION)
Equity: ~$107 USDT
Target: $1,000 USDT

---

## 현재 설정 (Quick Reference)
- R:R Ratio: 2.14:1 (TP=ATR*1.5, SL=ATR*0.7)
- Grid Entry: ATR*0.3 spacing
- Order: GTC Limit (entry), Market (exit)
- Max Trades/Day: 10
- Stage: 1 ($100-$300)

---

## P0: 즉시 (운영 안정성) — 완료

- [x] Docker 리빌드 (R:R + watchdog 코드 반영) — 2026-02-13
- [x] Watchdog 상시 실행 + Telegram 알림 연동 — 2026-02-13
- [x] Policy vs Code 정합성 동기화 (v2.4) — 2026-02-13

## P1: 단기 (코드 품질 + 데이터 축적)

- [ ] 10건+ 트레이드 축적 후 analysis 파이프라인 실행
  - blocked_by: 트레이드 축적 대기 (현재 8건)
  - 명령어: `python scripts/analyze_trades.py`
  - 검증: 승률, PnL 분포, R:R 실측, 최대 드로다운

- [ ] max_loss ADR 문서화 (ADR-0014)
  - Stage 1 max_loss $3→$10 변경에 대한 ADR
  - Code Review에서 지적된 항목
  - 파일: docs/adr/ADR-0014-stage1-loss-budget-increase.md

- [ ] orchestrator.py God Object 분리
  - 현재: ~720줄, entry/exit/risk 로직 혼재
  - 목표: entry_flow.py, exit_flow.py, risk_manager.py 분리
  - Code Review에서 지적된 항목
  - 주의: 테스트 깨지지 않게 단계적 추출

## P2: 중기 (데이터 기반 튜닝)

- [ ] 파라미터 2차 튜닝 (TP/SL/Grid multiplier)
  - blocked_by: P1 "10건+ 트레이드 분석" 완료
  - 분석 결과 기반으로 ATR multiplier 조정

- [ ] 전략 에지 검증
  - blocked_by: P1 "10건+ 트레이드 분석" 완료
  - 승률 vs breakeven(32%), Sharpe ratio, 최대 드로다운

- [ ] Dashboard PnL/승률 표시 검증
  - blocked_by: 트레이드 10건+
  - http://localhost:8501 접속하여 실데이터 확인

- [ ] Multi-position Grid 구현
  - blocked_by: P2 "전략 에지 검증" 완료
  - 현재 1포지션 제한 → 복수 포지션 동시 운용

## P3: 장기 ($1,000 스케일업)

- [ ] Stage 2 전환 ($200 달성 시)
  - blocked_by: Equity $200+
  - Policy Section 5.2 파라미터 적용
  - Leverage 유지 3x, max_loss $20, loss_pct 8%

- [ ] Drawdown Recovery 로직
  - blocked_by: P2 "전략 에지 검증" 완료
  - 연속 손실 시 sizing 축소 → 회복 후 복원

- [ ] Backtest 프레임워크 구축
  - 과거 데이터 기반 전략 사전 검증
  - Bybit Historical Kline API 활용

---

## 완료 이력

| 날짜 | 태스크 | 비고 |
|------|--------|------|
| 2026-02-13 | Docker 리빌드 + Watchdog Telegram | P0 완료 |
| 2026-02-13 | Policy v2.4 동기화 | max_loss/atr_gate/stop_distance 정합 |
| 2026-02-13 | R:R 2.14:1 최적화 | TP=ATR*1.5, SL=ATR*0.7 |
| 2026-02-13 | Watchdog 스크립트 작성 | 5분 쿨다운 Telegram 알림 |
| 2026-02-12 | Inverse→Linear 마이그레이션 완료 | P0~P2 전체 |
| 2026-02-12 | Mainnet 첫 트레이딩 사이클 | SHORT→take-profit exit |
| 2026-02-12 | Dashboard P0-3 수정 | float 파싱, JSONL 필터, 로그 경로 |

---

## 세션 시작 체크리스트

새 세션에서 이 파일을 읽었다면:
1. Bot Status 확인: `docker ps` + `docker logs cbgb-bot --tail 5`
2. 미완료 태스크 중 blocked_by가 해소된 것 확인
3. 가장 높은 우선순위(P0→P1→P2→P3)의 unblocked 태스크부터 진행
4. 작업 완료 시 이 파일 업데이트
