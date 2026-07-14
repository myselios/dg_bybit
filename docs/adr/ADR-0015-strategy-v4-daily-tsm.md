# ADR-0015: Strategy v4 — Daily TSM 채택 및 리스크 기반 사이징 전환

Date: 2026-07-13 (2026-07-14 개정: G2 waiver + live 전환)
Status: Accepted (리스크 5%). **2026-07-14 사용자 결정으로 G2 shadow 생략, 실거래 전환.**

## 개정 (2026-07-14) — G2 Waiver + Live 전환

사용자 판단: shadow 모드는 주문/청산 경로를 실행하지 않아(계좌 flat 유지) 검증 가치가 낮음.
→ G2 60일 shadow 생략, 오늘부터 실거래로 트레이드 API를 실제 검증.

- 첫 실거래 (2026-07-14 01:43 UTC): SHORT 0.001 BTC @ $62,467.8, stopLoss $67,351 거래소 첨부 확인.
  체결·스탑상주·청산가($74,588, 스탑보다 위) 전부 거래소 검증됨. 트레이드 API(place_order+stop) 정상.
- 크론 shadow→live 전환 (09:10/10:10 KST = 00:10/01:10 UTC).
- **가드레일**: equity < $90 (약 -17%, 백테스트 maxDD 수준) 도달 시 live 중단·재검토 — **운영 규칙(수동), 자동강제는 사용자 지시로 미구현**.
- **레버리지/마진 정정 (2026-07-14)**: 프리플라이트에서 position tradeMode=0을 "cross"로 오판했으나, `/v5/account/info` 조회 결과 계좌 marginMode=**ISOLATED_MARGIN** (UTA 2.0). liqPrice가 isolated 증거금 소진 지점과 일치함으로 확증. 즉 **고립은 이미 충족**.
  - 레버리지만 5x→3x로 설정 (`set_leverage("3","3")`, 현재 포지션 반영: liqPrice $74,588→$82,876으로 원거리화).
  - tsm_trader._ensure_leverage()로 매 진입 시 3x 강제 (110043=성공, I/O 실패는 진입 비차단). 마진모드는 계좌 단위라 코드에서 미변경.
  - 별건 버그: bybit_rest_client.set_margin_mode()가 `/v5/position/set-leverage`로 POST해 tradeMode 무시 (마진모드 전환 불가). ADR-0012 "isolated 강제"는 실작동 안 했음. TSM 경로 미사용이라 무해하나 수정 대상 → 후속 태스크.
- G3(첫 15건 기대값 R>0 확인 → 유지/중단)는 유효. 실거래 자체가 G2+G3 통합 검증 역할.

## Context

- 2026-07-13 전체 감사: 기존 tick 앙상블 신호는 엣지 없음 확정 (6개월 195일 백테스트 N=22,853, gross +$22.94 vs fee $514 → net -$491). 레짐 필터·임계값 조정으로 구제 불가. 근거: docs/plans/strategy_v3.md 부록, scratchpad/bt6m.py
- 신호 로직 버그 확인: breakout.py 영구 0점, macd.py:83 크로스 오판정, ATR 비표준 평활 — 단, 버그 수정으로도 엣지가 생기지 않음이 백테스트로 확인됨
- 대체 후보 3개 중 일봉 TSM만 생존: 2년 백테스트 +0.125R/건, 파라미터 9조합 전부 양(+), 반기 분할 부호 유지, P(엣지>0)=80.2%. 근거: docs/plans/strategy_v4.md, scratchpad/bt_v4_robust.py

## Decision

1. **신호**: 일봉 확정 후 1일 1회 판정. LONG = close > close[30일 전] AND close > EMA50. SHORT = 대칭. 플립 시 청산.
2. **청산**: 하드 SL = entry ∓ 2.5×ATR(14, Wilder, 일봉) — 진입 주문에 거래소 첨부 (Phase 2 배선). 플립 청산은 market reduce_only.
3. **사이징**: 거래당 리스크 = equity × 5% (사용자 선택, half-Kelly 4.3% 초과·full Kelly 8.6% 미만). qty = risk_usd / stop_distance, 3x 레버리지 cap, 0.001 BTC step. **Stage별 loss budget (policy Sec 5) 은 TSM 모드에 적용하지 않음** — 리스크 정의가 % 기반으로 대체됨.
4. **funding 필터**: 진입 방향 부담 funding > 0.05%/8h → 스킵.
5. **검증 게이트**: G2 shadow (60일 or 신호 5건) 통과 전 live 금지. G3 live 15건에서 기대값 R ≤ 0이면 중단 (파라미터 조정 연명 금지).
6. 기존 tick 앙상블 경로는 동결 (삭제하지 않음, TSM 모드와 병행 실행 금지).

## Consequences

- (+) 판정 1일 1회 — tick 루프·30초 캐시·인트라캔들 휩쏘 문제 자체가 소멸
- (+) 거래소 SL 상주 — 프로세스 다운 시에도 보호 유지 (기존 나체 포지션 리스크 해소)
- (+) 월 2~3건 × 왕복비용 0.14% — 수수료 잠식 구조 해소
- (-) 승률 24% — 5~10연패가 정상 범위. 5% 리스크에서 maxDD 17.5% (백테스트), 실전 2배 각오
- (-) P(엣지>0)=80% — 20% 확률로 엣지 없음. G3 중단 조건이 이를 담보
- 정책 문서(account_builder_policy.md) Sec 5 사이징은 TSM 모드 범위 밖 — 차기 정책 개정 시 반영 필요
