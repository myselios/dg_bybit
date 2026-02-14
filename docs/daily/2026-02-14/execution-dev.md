# Daily Log — Execution Dev
Date: 2026-02-14

## 1. Planned (아침 기준)
- [x] P0 크리티컬 버그 수정 4건 (전문감사 리뷰 결과)
- [x] P0 회귀 테스트 추가 + 전체 테스트 통과
- [x] Docker 리빌드 + 배포
- [x] P1-6: stop_distance_pct 미전달 수정
- [x] P1-7: LogStorage rotate_if_needed() NoneType 방어
- [x] P1-8: Dashboard BybitRestClient 공유 인스턴스

## 2. Done (팩트만, 파일/함수/커맨드 단위)

### P0 크리티컬 수정 (전 세션 코딩 완료 → 이번 세션 테스트/배포)

**P0-1: StopStatus.ERROR → HALT**
- `src/application/orchestrator.py:858-862` — `_manage_position()` 진입 시 stop_status==ERROR 체크
- Stop 복구 실패 시 Stop 없는 포지션 운영 방지 → 즉시 HALT

**P0-2: Exit order reduce_only=True**
- `src/infrastructure/exchange/bybit_rest_client.py` — `place_order()` 파라미터 `reduce_only: bool = False` 추가
- `src/application/orchestrator.py:915,1015,1034` — 모든 exit order에 `reduce_only=True`
- 반대 방향 포지션 오픈 방지

**P0-3: Cancelled 주문 시 포지션 API 확인**
- `src/application/orchestrator.py:672-689` — `rest_client.get_position()` 호출
- 포지션 존재 → IN_POSITION 복귀, 없음 → FLAT 전환

**P0-4: Recovery stop_price=None**
- `src/application/orchestrator.py:143,651,709,744` — 4개 recovery 사이트 전부 `stop_price=None`
- entry_price 대입 시 check_stop_hit()→True→즉시 청산 버그 수정

**P1-5: WS FILL pending_order_timestamp 초기화**
- `src/application/orchestrator.py:805,814` — FILL 처리 후 `self.pending_order_timestamp = None`

### Mock 수정
- `tests/integration_real/test_full_cycle_testnet.py` — MockRestClient에 `get_position()`, `reduce_only` 추가
- `tests/unit/test_orchestrator_event_processing.py` — 동일
- `tests/unit/test_orchestrator_entry_flow.py` — 동일

### P0 회귀 테스트 4건 추가
- `tests/unit/test_orchestrator_event_processing.py`:
  - `test_p0_1_stop_error_triggers_halt` — StopStatus.ERROR → HALT
  - `test_p0_2_exit_order_uses_reduce_only` — Exit 시 EXIT_PENDING 전환
  - `test_p0_3_get_position_returns_empty_means_flat` — get_position 빈 결과 → FLAT
  - `test_p0_4_recovery_stop_price_none` — stop_price=None → 즉시 stop hit 방지

### 테스트 결과
- `pytest -q`: 417 passed, 15 deselected, 0 failed (12.33s)

### Docker 리빌드 + 배포
- `docker build --no-cache -f docker/Dockerfile.base --target production -t cbgb:production .`
- `docker compose build --no-cache bot && docker compose build --no-cache dashboard`
- `docker compose up -d bot dashboard`
- 결과: bot (healthy), dashboard (healthy), analysis (healthy)
- Equity: $109.01 USDT, State: IN_POSITION, mark_price: $68,416.55

### P1-6: stop_distance_pct pending_order 전달
- `src/application/orchestrator.py:1215-1224` — entry flow에서 ATR*0.7 기반 stop_distance_pct 계산
- `pending_order["stop_distance_pct"]` 필드 추가
- `src/application/event_processor.py:170-172` — create_position_from_fill에서 이미 참조하고 있었음 (연결 완료)
- 테스트: `test_entry_pending_order_has_stop_distance_pct` 추가

### P1-7: LogStorage rotate_if_needed() NoneType 방어
- `src/infrastructure/storage/log_storage.py:173-179` — current_file_path=None 체크 + lazy open
- 테스트: `test_rotate_if_needed_handles_none_path` 추가

### P1-8: Dashboard BybitRestClient 공유 인스턴스
- `src/dashboard/app.py:102-118` — `_get_bybit_client()` 추가 (@st.cache_resource)
- `fetch_position_data()`, `fetch_equity_data()` 모두 공유 인스턴스 사용
- 기존: 함수마다 BybitRestClient 새로 생성 (2개) → 1개로 통합

### 긴급: Stop 관리 전면 수정 (HALT 루프 해소)

**문제**: 봇이 17초마다 HALT → restart 무한 루프 + Telegram 알림 폭탄
**근본 원인 3가지**:

1. `place_order(stop_loss=..., position_idx=...)` — 존재하지 않는 파라미터 → TypeError
2. `amend_order()` 메서드 rest_client에 미구현
3. Bybit V5 Stop Loss는 `set-trading-stop` API로 설정 (별도 엔드포인트)

**수정**:
- `src/infrastructure/exchange/bybit_rest_client.py` — `set_trading_stop()` 메서드 추가
  - 엔드포인트: `/v5/position/trading-stop` (set- 없음, 404 방지)
  - 파라미터: symbol, stopLoss, slTriggerBy, positionIdx
- `src/application/orchestrator.py:968-1010` — stop 관리 코드 전면 교체
  - PLACE/AMEND/CANCEL_AND_PLACE 모두 → `set_trading_stop()` 단일 호출
  - **SL 이미 관통 체크**: mark_price vs new_stop_price 비교
    - SHORT: mark >= SL → stop_price 설정 후 다음 tick에서 exit
    - LONG: mark <= SL → 동일
  - Bybit API 거부 방지 (SL < mark for SHORT → error 10001)
- `src/application/orchestrator.py:709,744` — 나머지 2개 recovery 사이트 stop_price=None 수정

**검증**:
- Tick 1: Position recovered (SHORT 3 @ $67,781.90) → SL=$68,131 < mark=$68,874 → "Stop already breached"
- Tick 2: EXIT_PENDING (Market Buy order)
- Tick 3: FILL → FLAT (exit @ $68,869.22)
- Tick 4+: 정상 FLAT, trades: 1/10

### 테스트 결과
- `pytest -q`: 420 passed, 15 deselected, 0 failed
- 새 테스트: `test_stop_recovery_uses_set_trading_stop`

### Hotfix: retCode 34040 HALT 방지
- `src/application/orchestrator.py:576` — `ret_code not in (0, 34040)`
- 원인: set_trading_stop "not modified" → 실패로 처리 → 3회 → ERROR → HALT
- Docker 리빌드 + 배포 → 봇 정상 동작 확인

### API 감사 CRITICAL 수정 5건
- `scripts/force_close_position.py` — `import time` 추가, `order_link_id=f"force_close_{int(time.time())}"` 추가
- `scripts/place_manual_order.py:84` — `qty=qty` → `qty=str(qty * 0.001)` (contracts→BTC)
- `src/infrastructure/exchange/bybit_rest_client.py:292` — `qty: int` → `qty: str`, docstring 수정
- `scripts/close_position.py:92` — `qty=size` → `qty=str(size)`
- `src/application/orchestrator.py:122` — `pos_response["retCode"]` → `.get("retCode", -1)`
- 주석 "10000ms" → "20000ms" 정합성 수정

### orchestrator.py God Object 분리 (1,222→747줄)

**Step 2-1: Trade Logging 추출 (171줄 감소)**
- `src/application/trade_logging.py` 신규 생성
  - `log_estimated_trade()`: mark_price 기반 추정 트레이드 로그
  - `log_completed_trade()`: 실제 FILL 이벤트 기반 트레이드 로그
- orchestrator `_log_estimated_trade()`, `_log_completed_trade()` → thin delegate (각 10줄)
- `tests/unit/test_trade_logging.py`: 4건 추가

**Step 2-2: REST Fallback 추출 (300줄 감소)**
- `src/application/rest_fallback.py` 신규 생성 (250줄)
  - `check_pending_order_fallback()`: WS timeout 시 REST API 주문 상태 확인
  - `FallbackResult` dataclass: 상태 변경을 반환값으로 표현
  - Helper: `_check_has_position`, `_recover_position_from_api`, `_handle_fill_event` 등
- orchestrator `_process_events()` 380줄 → 55줄
- `_apply_fallback_result()` 메서드 추가 (FallbackResult → self.* 적용)
- `tests/unit/test_rest_fallback.py`: 11건 추가

**Step 2-3: Stop Update 추출 (80줄 감소)**
- `src/application/stop_manager.py` 확장
  - `calculate_stop_price()`: ATR 기반 stop price 계산 (clamped)
  - `is_stop_breached()`: SL 관통 체크
  - `execute_stop_update()`: API 호출 + breached 판단 통합
- orchestrator `_manage_position()` stop 로직 30줄 → 15줄 위임
- `tests/unit/test_stop_manager_execute.py`: 14건 추가

**Step 2-4: 레거시 모듈 삭제**
- 삭제 소스: tick_engine.py, event_router.py, event_handler.py, order_executor.py, position_manager.py (5개)
- 삭제 테스트: test_order_executor.py, test_event_handler.py, test_event_router.py, test_flow_minimum_contract.py, test_integration_basic.py, test_flow_v1_9_scenarios.py (6개, 34 tests)

### 최종 테스트 결과
- `pytest -q`: 415 passed, 15 deselected, 0 failed
- 기존 420 - 레거시 34 + 신규 29 = 415

### Docker 리빌드 + 배포
- `docker build --no-cache -f docker/Dockerfile.base --target production -t cbgb:production .`
- `docker compose build --no-cache bot && docker compose up -d bot`
- 결과: 봇 정상 동작, `application.stop_manager - Stop Loss set: $69,366.81`

## 3. Blocked / Issue
- 없음

## 4. Decision / Change
- ADR 필요 여부: NO (기존 FLOW.md 의도와 일치, 내부 구조 리팩토링)
- God Object 분리: orchestrator.py 1,222줄 → 747줄 (trade_logging + rest_fallback + stop_manager 확장)
- retCode 34040 "not modified" → success 처리 (Bybit API 정상 응답)

## 5. Next Action
- 봇 모니터링 (IN_POSITION → exit 대기)
- 트레이드 10건+ 달성 시 analysis 파이프라인 실행
- P2: 핵심 모듈 테스트 추가 (emergency_checker, entry_coordinator 등)
