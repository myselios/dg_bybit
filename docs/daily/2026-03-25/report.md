# 🤖 CBGB Dev Team 일일 리포트 — 2026-03-25

## TL;DR
- 완료: Wave 7 (hold_seconds 버그 수정 + .env GIT_COMMIT 업데이트 + TASKS.md 정리)
- Quality Gates: PASS ✅ (785/785 unit tests)
- 어제(2026-03-24) 실거래: 1건 Net **+$1.522** (Equity ~$113.5)
- 결재 필요: 0건

---

## 봇 상태 (22:00 KST 기준)

| 항목 | 값 |
|------|-----|
| 상태 | healthy (Up 13시간) |
| 현재 score | 2/7 (RSI=2) |
| BTC 현재가 | $71,625 (+1.4% 상승) |
| ma_slope | +0.138% (약 상승) |
| Tick | 40,388 |
| 오늘 트레이드 | 0/10 |

**오늘 트레이드 없음**: BTC $71.6k 상승 중, RSI 과매수권 접근 (RSI=2점), score=2/7로 미달.

---

## 어제(2026-03-24) 트레이드 — Wave 5 코드 첫 실거래!

| 항목 | 값 |
|------|-----|
| 방향 | LONG |
| 진입 | $68,947.6 |
| 청산 | $69,493.2 |
| 보유 | ~57분 |
| PnL | +$1.637 |
| Fee | -$0.115 (Taker 0.055%) |
| **Net** | **+$1.522** |
| signal_score | 4/7 (RSI=2, BB=1, Volume=1) |
| regime | ranging |

Equity: $112 → **~$113.5** USDT (+$1.522)

> ⚠️ 이 트레이드는 Wave 5 코드(Ensemble 신호)로 진입했지만 entry 주문이 Post-Only 적용 여부 불명확. fee $0.115 = Taker 0.055% (exit만). 다음 트레이드에서 Post-Only 효과 검증 필요.

---

## Wave 7 완료 태스크

| 커밋 | 스트림 | 내용 |
|------|--------|------|
| b243362 | A | `hold_seconds` 음수 버그 수정 — `execTime` ms→s 변환 (+4 tests) |
| 5d4b548 | B+C | TASKS.md 정리 + .env GIT_COMMIT 업데이트 + 트레이드 분석 |

테스트: **785 passed** (+4 신규, 3 pre-existing)

### Stream A 핵심 수정
```python
# bybit_adapter.py — execTime ms → seconds 정규화
exec_time_raw = float(raw_event.get("execTime", 0))
timestamp = exec_time_raw / 1000.0 if exec_time_raw > 1e12 else exec_time_raw
```
- 수정 전 hold_seconds: **-1,772,599,949,903초** (음수!)
- 수정 후 hold_seconds: **+3,415초** (~57분, 정상)

---

## 버그 이력

| 버그 | 파일 | 증상 | 수정 |
|------|------|------|------|
| hold_seconds 음수 | bybit_adapter.py | -1.77T초 | execTime /1000 ✅ |
| .env GIT_COMMIT 구버전 | .env | dfc5135 (3월초 커밋) | 최신 HEAD로 업데이트 ✅ |

---

## 오늘 트레이드 요약

트레이드 없음 — score=2/7 (RSI 과매수권 접근). BTC $71.6k 상승 중.

---

## 다음 세션 추천

1. BTC $71.6k 상승 → RSI+BB+MACD 조건 달성 시 Wave 7 코드 첫 트레이드 기대
2. Post-Only fee 실측 검증 — 다음 entry fee $0.02 목표 확인
3. 실거래 10건 축적 후 `analyze_trades.py` regime별 A/B 검증
4. `python scripts/analyze_trades.py --period 2026-03-25:2026-03-25`
