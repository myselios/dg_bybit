# 🤖 CBGB Dev Team 일일 리포트 — 2026-03-23

## TL;DR
- 완료: Wave 5 전체 (signal_score fix + regime filter + Post-Only + DrawdownRecovery)
- Quality Gates: PASS ✅ (769/769 unit tests)
- 오늘 실거래: **2건 모두 수익** — Net +$2.625
- 결재 필요: 0건

---

## 봇 상태

| 항목 | 값 |
|------|-----|
| 상태 | healthy (Up 8시간) |
| 현재 score | 3/7 (RSI+BB 근접, Near-miss) |
| BTC 현재가 | $70,858 (강한 반등 — $68k→$70.8k) |
| ma_slope | +0.407% (상승 추세 진입) |
| last_fill | $70,570.8 |
| grid_spacing | $261.06 (ATR×0.3 적용) |
| 오늘 트레이드 | 1/10 (Wave 5 코드 기준) |

---

## 오늘 트레이드 (2건 — 구 코드 dfc5135)

| # | 방향 | 진입 | 청산 | PnL | Fee | Net | score | 레짐 |
|---|------|------|------|-----|-----|-----|-------|------|
| 1 | LONG | $67,415 | $67,918 | +$0.503 | -$0.037 | **+$0.466** | 4/7 | ranging |
| 2 | LONG | $69,812 | $70,571 | +$2.276 | -$0.116 | **+$2.159** | None* | high_vol |

\* trade 2: legacy MA slope 모드 (score=None = MA slope 단일 지표 진입, high_vol 레짐)

**오늘 합계:**
- 총 Net PnL: **+$2.625** ✅
- 승률: **2/2 (100%)**
- 평균 Net PnL/트레이드: +$1.31

> ⚠️ 두 트레이드 모두 Wave 5 배포(09:26 KST) 전 구 코드(dfc5135)에서 실행됨

---

## Score 분포 (오늘 24h 기준)

| score | 빈도 | 비고 |
|-------|------|------|
| 0 | 다수 | BTC $68k 하락 시간대 |
| 1 | 다수 | MACD hist 상승만 감지 |
| 3 | 현재 | RSI+BB 근접 — score≥4 임박 |

현재 BTC $70.8k 반등 + ma_slope +0.407% → score 4 달성 가능성 높음

---

## 오늘 완료 태스크

| 커밋 | 내용 |
|------|------|
| cf0703a | **Wave 5**: 3 streams 전체 (769 tests) |
| eb6c02d | TASKS.md + 작업일지 |
| ba41dcc | near-miss log /6→/7 + team.json wave5 completed |
| af6de95 | 오전 리포트 |

---

## Wave 5 배포 후 기대 효과 (실거래 대기 중)

| 항목 | 기대 |
|------|------|
| signal_score 보존 | 트레이드 로그 score 정확도 향상 |
| 레짐 필터 | trending_down → Buy 자동 차단 |
| Post-Only | Maker fee 0.01% (기존 Taker 0.06% → 6배 절약) |
| Trailing ATR*0.8 | 조기 청산 방지, TP 규모 확대 |
| Grid×0.3 | 수익 목표 +50% (ATR×0.2 → ATR×0.3) |

---

## 다음 세션 (19:00 KST 크론)

- BTC $70.8k → score≥4 달성 시 Wave 5 첫 트레이드 기대
- score=3 지속 시 Volume 확인 조건 검토
- 실거래 10건+ 후 `python scripts/analyze_trades.py` R:R 실측
