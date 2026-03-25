# 🤖 CBGB Dev Team 일일 리포트 — 2026-03-25

## TL;DR
- 완료: Wave 7 (hold_seconds 버그 수정 + .env GIT_COMMIT 업데이트 + TASKS.md 정리)
- Quality Gates: PASS ✅ (785/785 unit tests)
- 어제(2026-03-24) 실거래: 1건 Net **+$1.522** (Equity ~$113.5)
- 결재 필요: 0건

---

## 봇 상태

| 항목 | 값 |
|------|-----|
| 상태 | healthy (Up 24시간) |
| 현재 score | 1/7 (MACD hist만) |
| BTC 현재가 | $70,606 |
| ma_slope | +0.112% (중립) |
| Tick | 74,417 |
| 오늘 트레이드 | 1/10 (어제 count 이월) |

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

## 다음 세션 추천

1. Post-Only fee 실측 검증 — 다음 Wave 5 코드 트레이드에서 entry fee $0.02 확인
2. 실거래 10건 축적 후 `analyze_trades.py` regime별 A/B 검증
3. Dashboard PnL/승률 표시 정합성 확인
4. 신호 품질 개선 검토 (score=1/7 → score≥4 달성률 분석)
