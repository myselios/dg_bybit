# Linear USDT Migration - Completion Checklist
**Date**: 2026-01-25
**ADR**: ADR-0002
**Commit**: 5b31655

## Document-First Workflow (CLAUDE.md Section 5.0)
- [x] SSOT 3문서 읽기 (FLOW.md, account_builder_policy.md, task_plan.md)
- [x] TODO 항목 확인
- [x] task_plan.md Progress Table 업데이트 (TODO → IN PROGRESS)
- [x] 구현 시작
- [x] Evidence Artifacts 생성
- [x] task_plan.md Progress Table 업데이트 (IN PROGRESS → DONE)

## ADR-0002 Checklist
- [x] ADR-0002 작성 (Inverse to Linear USDT Migration)
- [x] Rationale 문서화 (실용성, 안정성, 직관성)
- [x] Implementation Plan (4 phases)
- [x] Technical Details (Formula comparison, API changes)

## SSOT 문서 업데이트
- [x] CLAUDE.md: "Bybit Linear (USDT-Margined) Futures"로 변경
- [x] account_builder_policy.md: 전면 재작성
  - [x] Section 1.1: equity_btc → equity_usdt
  - [x] Section 1.2: Inverse → Linear contract units
  - [x] Section 6: Loss Budget (BTC → USDT)
  - [x] Section 8: Fees Policy (Inverse → Linear)
  - [x] Section 10: Position Sizing (Inverse → Linear formula)

## Core Logic 구현
- [x] sizing.py: Linear formula 구현
  - [x] SizingParams: max_loss_btc → max_loss_usdt
  - [x] SizingParams: equity_btc → equity_usdt
  - [x] contract_size 파라미터 추가 (0.001 BTC)
  - [x] Direction-independent formula (qty = max_loss / (price × stop_pct))
  - [x] Margin feasibility check (USDT-denominated)
- [x] entry_coordinator.py: build_sizing_params() 수정
  - [x] get_equity_btc() → get_equity_usdt()
  - [x] max_loss_btc → max_loss_usdt
  - [x] contract_size 추가
- [x] bybit_adapter.py: Linear API 전환
  - [x] category="inverse" → category="linear"
  - [x] symbol="BTCUSD" → symbol="BTCUSDT"
  - [x] accountType="CONTRACT" → accountType="UNIFIED"
  - [x] execution.inverse → execution.linear (WebSocket)
  - [x] _equity_usdt 필드 추가
  - [x] update_market_data(): totalEquity 파싱

## Infrastructure Layer
- [x] market_data_interface.py: get_equity_usdt() 추가
  - [x] Docstring 작성 (Linear USDT-Margined)
  - [x] get_equity_btc() DEPRECATED 표시
- [x] fake_market_data.py: equity_usdt 지원
  - [x] __init__: equity_usdt 파라미터 추가 (Optional)
  - [x] get_equity_usdt(): _equity_usdt 또는 equity_btc × mark_price
  - [x] Backward compatible (equity_btc default 유지)

## Test 재작성 (RED → GREEN)
- [x] test_sizing.py: Linear formula 기준 재작성 (8개 테스트)
  - [x] test_contracts_from_loss_budget
  - [x] test_margin_cap
  - [x] test_qty_step_rounding
  - [x] test_tick_size_adjustment
  - [x] test_reject_qty_below_minimum
  - [x] test_reject_margin_insufficient
  - [x] test_extreme_leverage_cap
  - [x] test_reject_zero_equity
  - [x] **Result: 8/8 PASSED**
- [x] test_bybit_adapter.py: Linear API 기준 수정
  - [x] category="linear", symbol="BTCUSDT"
  - [x] test_get_equity_btc → test_get_equity_usdt
  - [x] UNIFIED account 구조 (totalEquity)
  - [x] accountType="UNIFIED"
  - [x] **Result: 14/14 PASSED**
- [x] test_orchestrator_entry_flow.py: equity_usdt 사용
  - [x] FakeMarketData(equity_usdt=1000.0)
  - [x] **Result: 7/7 PASSED**
- [x] test_full_cycle_testnet.py: equity_usdt 사용
  - [x] FakeMarketData(equity_usdt=1000.0)
  - [x] **Result: 5/5 PASSED**

## Import Path Migration (CLAUDE.md Section 8.1)
- [x] Phase 1: 현재 상태 확인 (grep으로 의존성 파악)
- [x] Phase 2: 새 구조 생성 (N/A, 이미 src/ 구조 존재)
- [x] Phase 3: Import Path 전환
  - [x] tests/: `from application` → `from src.application`
  - [x] tests/: `from domain` → `from src.domain`
  - [x] tests/: `from infrastructure` → `from src.infrastructure`
  - [x] tests/: `from adapter` → `from src.adapter` (test_flow_v1_9_scenarios.py)
  - [x] src/: 내부 import 경로 통일
- [x] Phase 4: 구 파일 처리 (N/A, 경로만 변경)
- [x] Phase 5: 검증 (pytest 실행)
- [x] Phase 6: 문서화 (Evidence 생성)
- [x] **Result: 320 tests PASSED**

## Self-Verification (CLAUDE.md Section 5.7)
- [x] Gate 1: Placeholder 테스트 0개
  ```bash
  $ grep -RInE "assert[[:space:]]+True|pytest\.skip\(" tests/ | wc -l
  0
  ```
- [x] Gate 2: 도메인 타입 재정의 금지
  ```bash
  $ grep -RInE "^class[[:space:]]+(Position|PendingOrder|ExecutionEvent|State)\b" tests/ | wc -l
  0
  ```
- [x] Gate 3: transition SSOT 파일 존재
  ```bash
  $ test -f src/application/transition.py && echo "OK"
  OK
  ```
- [x] Gate 4: EventRouter에 State 분기 금지
  ```bash
  $ grep -RInE "if[[:space:]]+.*state[[:space:]]*==|elif[[:space:]]+.*state[[:space:]]*==" src/application/event_router.py | wc -l
  0
  ```
- [x] Gate 5: sys.path hack 금지
  ```bash
  $ grep -RIn "sys\.path\.insert" src/ tests/ | wc -l
  0
  ```
- [x] Gate 6: Migration 완료 (구 경로 import 0개)
  ```bash
  $ grep -RInE "from application\.|from domain\.|from infrastructure\." tests/ src/ | wc -l
  0
  ```
- [x] Gate 7: pytest 증거 + 문서 업데이트
  ```bash
  $ venv/bin/pytest -v 2>&1 | tail -1
  ====================== 320 passed, 15 deselected in 0.49s ======================
  ```

## Git Commit
- [x] Commit message 작성 (feat(linear-usdt): ...)
- [x] Co-Authored-By 추가
- [x] Commit 완료 (5b31655)
- [x] **Result: 63 files changed, 897 insertions(+), 485 deletions(-)

## Evidence Artifacts
- [x] docs/evidence/linear_usdt_migration/ 생성
- [x] red_green_proof.md 작성
- [x] pytest_output.txt 저장
- [x] completion_checklist.md 작성 (이 파일)

## Final Verification
- [x] 전체 테스트 통과: **320 passed, 15 deselected**
- [x] Import 경로 오류: 0개
- [x] Linear formula 적용: sizing.py, test_sizing.py
- [x] Linear API 적용: bybit_adapter.py, test_bybit_adapter.py
- [x] equity_usdt 사용: entry_coordinator.py, fake_market_data.py, tests
- [x] SSOT 업데이트: CLAUDE.md, account_builder_policy.md, ADR-0002
- [x] Document-First Workflow 준수
- [x] "중간에 모든단위를 스킵하지말라고" 규칙 준수 ✅

## Conclusion
✅ **Linear USDT Migration 완료**
- Inverse → Linear 전환 100% 완료
- RED (Inverse, 실패) → GREEN (Linear, 320 passed)
- 모든 단위 스킵 없이 완료 (사용자 지시 준수)
- Evidence Artifacts 생성 완료
