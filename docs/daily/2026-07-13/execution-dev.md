# Daily Log — execution-dev
Date: 2026-07-13

## 1. Planned (아침 기준)
- [x] 전체 코드베이스 분석 (아키텍처 / 리스크 로직 / 트레이드 성과 데이터)
- [x] 방향 재정립을 위한 문제 목록 확정

## 2. Done (팩트만, 파일/함수/커맨드 단위)
- 봇 상태: `docker ps` → 컨테이너 없음 (2026-03-27 이후 중지, 3.5개월 공백)
- 트레이드 로그 독립 집계: `logs/mainnet/trades_*.jsonl` 57건 (실거래 51건) → 실현 PnL **-$5.88**, fee $5.29, **Net -$11.17**. 재구성 equity **$88.83 (-11.2%)** — TASKS.md의 "$113.5(+13.5%)"는 2026-03-07 롤링 가산 오류가 이월된 과대계상(약 $24~25).
- 배포 검증: 실거래 49/57건(3/9~3/27 전체)의 `git_commit=dfc5135`(2026-02-01 커밋). Wave 7 수정(b243362) 이후 거래(3/27)도 동일 해시 + hold_seconds 음수 버그 재현 → **Wave 4~7 코드가 운영 컨테이너에 반영된 증거 없음** (배포 파이프라인 실패 가설).
- 리스크 검증 (FAIL):
  - `liquidation_gate.py` — src 전체에서 호출부 0건 (죽은 코드)
  - `kelly_sizer.py` — orchestrator.py:1002가 kelly_fraction 미전달 (죽은 코드). 실질 사이징은 sizing.py:72 `MAX_CONTRACTS_HARD_CAP=3`이 결정
  - orchestrator.py:1079-1089 — 진입 place_order에 stopLoss 미첨부 (체결~stop 설정 사이 보호 공백, 프로세스 다운 시 나체 포지션)
  - `set_leverage` 호출 0건 — 거래소 실제 레버리지 미설정/미검증
  - SL 이원화: 사이징(entry_coordinator.py:172, ATR*0.8/0.4~1.5%) vs 실제 스탑(stop_manager.py:169, ATR*0.7/0.5~2.0%)
- 아키텍처 검증:
  - orchestrator.py `self.state=` 직접 대입 18곳, transition() 정상 경로는 610 한 곳 — 상태머신 규칙 위반. rest_fallback.py는 transition() 미사용 병렬 상태머신
  - 파일 크기 위반 2건 (orchestrator 1250줄, dashboard/app.py 1015줄), 함수 >50줄 61건
  - 금융 계산 전면 float (Decimal import 0건)
  - 정책 SSOT 자기모순: account_builder_policy.md Sec5($15/$30/$45) vs Sec6($10/$20/$30), Sec5(5x) vs Sec5.4(3x). config/safety_limits.yaml은 코드에 미로딩(제3의 값)
- 분석 도구 버그 2건 확정: trade_analyzer.py:376-387 `holding_time_seconds` 필드명 불일치(실제 `hold_seconds`) → Avg Holding 0.00h. trade_analyzer.py:271-300 MDD가 시작자본 미포함 누적PnL 기준 → 1707.81% 발산 (실제 equity 기준 MDD ~22%)
- 3/9 SHORT -$17.41 (4.39% 역행, SL clamp 2%의 2배 초과): 구코드(dfc5135) 재배포 이전 발생. 이 1건 제외 시 기간 Net +$6.47

### 2차 작업 (사용자 방향 승인 후 — 수익 방향 재정렬)
- Phase 0 완료: trade_analyzer.py 버그 2건 수정(TDD) + scripts/reconcile_equity.py 신규 (Equity $88.83 재구성) + TASKS.md 팩트 교정
- Phase 1 완료: 배포 실패 근본 원인 확정 — redeploy.sh:7 macOS 절대경로로 Linux에서 매번 no-op + .env GIT_COMMIT 수동값이 로그에 기록됨. 수정: Dockerfile.bot ARG GIT_COMMIT → /app/BUILD_COMMIT 굽기, src/infrastructure/version.py resolve_git_commit() 신규, docker_rebuild.sh/redeploy.sh에 배포 후 검증(컨테이너 BUILD_COMMIT == HEAD, 불일치 exit 1). redeploy.sh 하드코딩 텔레그램 토큰 제거 (이력 노출 — 로테이션 필요)
- Phase 2 완료: 진입 place_order에 stopLoss+slTriggerBy 첨부 (bybit_rest_client.py, orchestrator.py:1085-1099), SL 계산 단일화 (stop_manager.calculate_stop_distance_pct — ATR*0.7 clamp 0.5~2.0%, entry_coordinator ATR*0.8 제거), set_leverage 기동 호출+실패 시 진입 차단, liquidation_gate 진입 흐름 연결. 신규 tests/unit/test_risk_safety_wiring.py 16개
- 추가 버그 수정 (직접, TDD): orchestrator.py:1115 `contracts = sizing_result.contracts`가 DrawdownRecovery 축소분(signal.qty)을 무시 → `contracts = signal.qty`로 수정. Wave 5 Stream C "통합 완료" 주장은 실제로 미통합이었음. fake_market_data.py inject_daily_realized_pnl() 추가
- 전략 v3 설계: docs/plans/strategy_v3.md — ranging 차단, Post-Only maker, max 5회/일, 3x, 1% 리스크, 검증 게이트 G1~G3
- 테스트: pytest -q (docker/integration_real 제외) **805 passed**, 회귀 0. 실패 6건은 환경 의존(docker 바이너리 부재 4, live testnet 필요 2) — 클린 트리에서도 동일 실패 확인됨

## 3. Blocked / Issue
- ~~Bybit API 키 만료~~ → 사용자 재발급 완료, 대사 수행됨 (아래)
- **거래소 원장 대사 완결 (오차 $0.17)** — scratchpad/reconcile_exchange2.py:
  - 입금: **$128.74** (2026-01-18, on-chain USDT) — "시작 $100" 전제가 애초에 틀림
  - BTCUSDT closed PnL: **-$30.94 / 205건** (1월 테스트 -$25.33/36건, 2월 -$1.61/53건, 3월 -$4.00/116건)
  - ETHUSDT closed PnL: **+$10.91 / 2건** (봇 심볼 아님 — 수동 거래 추정)
  - Funding(SETTLEMENT): -$0.16 / 94건
  - 검산: 128.74 - 30.94 + 10.91 - 0.16 = **108.55 ≈ 실잔고 108.72**
  - **진짜 성과: 총 -$20.02 (-15.6%)**. 봇 운영기(2~3월) 순손실 -$5.61 (거래소 net)
- **트레이드 로깅 커버리지 심각**: 거래소 2~3월 169건 vs 로컬 로그 51건 (부분청산 분리 감안해도 2월 53 vs 6은 큰 공백) → 로컬 로그 기반 분석 신뢰 불가, 대사는 거래소 원장 기반으로 전환 필요
- 배포 실패 근본 원인: redeploy.sh no-op + .env 수동 GIT_COMMIT으로 확정 (Section 2 참조)
- bybit_rest_client.py GET 서명 버그 발견·수정 (TDD): 서명은 sorted, 전송은 삽입 순서 → 비알파벳 파라미터에서 retCode 10004. _make_request에서 전송 전 정렬로 수정 + 회귀 테스트

### 3차 작업 (냉정 분석 — "이게 돈을 벌 수 있는가")
- 신호 로직 감사 (audit-signal): breakout.py:69-80 **영구 0점 버그** (현재 캔들 고가 포함 → close>own-high 불가능, 유효 최대점수 7→6), macd.py:83 크로스오버 stale 인덱스 (macd_line[-(len(signal)+1)] → 허위/누락 크로스), atr_calculator.py:107 비표준 EMA 평활 (Wilder 1/14 아닌 2/15), bybit_adapter.py:380 미완성 캔들로 지표 계산. RSI/BB/MA slope는 표준 정확. R:R 구조 결함: 트레일 온리 청산, 최소 승리 0.43R vs 손실 1R
- 백테스트 감사 (audit-backtest): backtest_ensemble.py는 **합성 가격** 사용 (백테스트 아님), run_backtest.py는 스코어러가 프로덕션과 불일치(5지표 vs 6지표) + 룩어헤드 + 슬리피지 0 + 기간 7일. "T=4 최적" 근거 전부 무효 (원본 리포트는 T=2 권장 — 자기모순)
- **6개월(195일) 1분봉 재백테스트** (scratchpad/bt6m.py, 프로덕션 스코어러): N=22,853, gross +$22.94 vs fee $514 → net **-$491**. ranging 제외 net -$37, score≥5 net -$10.2. 수수료 후 +EV 설정은 N=10/N=4뿐 (노이즈). **판정: 현 앙상블 신호에 엣지 없음**
- strategy_v3.md Status를 G1 FAIL로 갱신 (전제 반증 부록 추가)

### 4차 작업 (v4 구현 — 사용자 승인: 리스크 5%)
- ADR-0015 작성 (strategy v4 채택, % 리스크 사이징으로 전환, 검증 게이트)
- src/application/tsm_signal.py (120줄, 순수) + tests 17개 — **백테스트 패리티: 2년 데이터 전체 트레이드 방향/진입/스탑/청산 rel_tol=1e-12 일치**
- src/application/tsm_trader.py (326줄) + tests 24개 — compute_order_qty Decimal, entry/flip/hold/funding스킵/error 전 경로, shadow 주문 미발주 검증, live stop_loss 첨부 검증
- scripts/run_tsm_daily.py — --mode shadow|live, --once|--loop
- 실행 증거: pytest **847 passed** (환경의존 6건 제외 기준), shadow 1회 실전 실행 → action=no_signal, 시장 데이터 교차검증 일치 (close>30일전 BUT close<EMA50)
- 결정: stateful shadow 시뮬레이터 불필요 판정 — 사후 리플레이(eval_tsm_shadow.py)로 G2 평가 (태스크 등록)

## 4. Decision / Change
- ADR 필요 여부: YES (재가동 전 — 정책 수치 단일화 ADR, 상태머신 단일화 ADR)
- 방향 결정 대기: 파라미터 튜닝(Wave 방식) 중단, 신뢰성 복구 우선 (사용자 승인 필요)

## 5. Next Action (내일)
- 사용자: (a) Bybit 실잔고 확인 → $88.83 대사, (b) 텔레그램 봇 토큰 로테이션, (c) strategy_v3.md 결정 3건 (레버리지 3x 복귀 / max_loss 단일값 / 승인)
- Phase 3: 정책 수치 단일화 ADR + config/safety_limits.yaml 실로딩
- Phase 4 G1: run_backtest.py에 v3 규칙(ranging 차단, maker fee, 5회/일) 반영 후 walk-forward 백테스트
- 커밋 정리: 워킹트리 변경분을 논리 단위로 분할 커밋 (사용자 요청 시)
