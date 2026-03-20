# Task Plan: CBGB 전략 개선 + 문서 동기화

## Goal
qty 버그 수정 + 전략 개선(DCA 제거, Trailing Stop, ATR SL, 3x 레버리지) + 정책 문서 전체 동기화

## Phases
- [x] Phase 1: 파일 읽기 완료 및 수정 범위 확정
- [x] Phase 2: P0 — qty 버그 수정 (Entry BTC 단위, DCA 제거, Exit BTC 단위)
- [x] Phase 3: 전략 수정 — DCA 비활성화, Trailing Stop, ATR SL, 레버리지 3x
- [x] Phase 4: 문서 동기화 — policy.md v2.5, safety_limits.yaml, TASKS.md
- [x] Phase 5: 테스트 — 16 failed (전부 pre-existing, 내 변경으로 인한 신규 실패 없음)

## 수정 대상 파일
- `src/application/orchestrator.py` — qty 버그(3곳), DCA 비활성화, TP→Trailing Stop
- `src/application/entry_coordinator.py` — ATR SL, 레버리지 3x
- `docs/specs/account_builder_policy.md` — 전략 수치 동기화 (v2.5 진행 중)
- `config/safety_limits.yaml` — 전략 수치 동기화
- `TASKS.md` — 태스크 업데이트

## 전략 변경 내역
| 파라미터 | 현재 | 변경 후 |
|---------|------|--------|
| qty API 단위 | contracts (버그) | BTC (contracts * 0.001) |
| DCA | -2/-4/-6% 물타기 | 비활성화 |
| TP | +1.5%/+3.0% 고정 | Trailing Stop (최고점 -ATR*0.5) |
| SL | 2.2% 고정 | ATR * 0.7 (clamp 0.5%~2.0%) |
| 레버리지 (전 Stage) | 5x | 3x |
| 목표 R:R | 1.36:1 | 3:1 이상 |

## Trailing Stop 설계
- `position.trail_price` 필드 추가 (최고/최저 유리가격 추적)
- 매 tick: trail_price 갱신
- 청산 조건: LONG → current_price < trail_price - ATR*0.5
             SHORT → current_price > trail_price + ATR*0.5
- ATR 없으면 fallback: trail_price - entry_price * 0.015 (1.5%)

## Decisions Made
- DCA 제거: 5x 레버리지에서 DCA-4%가 청산 경계선, "손실 최소" 철학과 반대
- Trailing Stop: 추세 끝까지 타고 가는 "그리디 수익" 전략
- ATR SL: 변동성 반영, 노이즈 회피
- 3x 레버리지: SL이 타이트해지면 포지션 크기 줄어드니 레버리지 낮춰도 수익 유사

## Errors Encountered
-

## Status
**Phase 1 완료** - orchestrator.py 읽기 중 (offset 400까지 읽음, 나머지 필요)
