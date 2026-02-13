# Daily Log — Execution Dev
Date: 2026-02-12

## 1. Planned (아침 기준)
- [x] Grid entry multiplier 2.0 -> 0.3 변경
- [x] Docker base + bot 이미지 재빌드 (no-cache)
- [x] Mainnet 봇 재가동 + no_signal 원인 진단

## 2. Done (팩트만, 파일/함수/커맨드 단위)

### Grid entry spacing 축소
- `src/application/orchestrator.py:768`: `calculate_grid_spacing(atr=atr, multiplier=2.0)` -> `multiplier=0.3`
- 효과: ATR=556 기준 grid_spacing $1,112 -> $167 (재진입 빈도 7배 증가)
- `tests/unit/test_orchestrator_entry_flow.py`: `test_entry_blocked_no_signal` 테스트 가격 조정

### Docker 빌드 캐시 이슈 발견 + 해결
- `Dockerfile.bot`은 `cbgb:production` 의존 -> base 먼저 빌드 필수
- `docker build --no-cache -f docker/Dockerfile.base --target production -t cbgb:production .` 후 bot 빌드

### no_signal 디버그 로깅 추가
- `src/application/signal_generator.py`: `logger.debug(f"generate_signal: ...")` 추가
- `scripts/run_mainnet_dry_run.py`: no_signal 시 `last_fill`, `grid_spacing` 값 로깅, signal_generator만 DEBUG

### Fix 6: REST fallback race condition 수정
- 원인: 체결 직후 execution list API에 데이터 미전파 (1초 지연)
- `src/application/orchestrator.py` `_process_events()`:
  - execution 없을 때 `/v5/order/history` API로 실제 상태(Filled/Cancelled) 확인
  - Filled + execution 없음 -> 2초 후 재시도
  - Cancelled 확인 시에만 FLAT 복귀
- `src/infrastructure/exchange/bybit_rest_client.py`: `get_order_history()` 메서드 추가

### Fix 7: WS timeout 5s -> 10s
- `src/application/orchestrator.py`: `WEBSOCKET_TIMEOUT = 5.0` -> `10.0`
- WS FILL 이벤트 도착 시간 확보, race condition 방지

### Fix 8: Exit order retCode 검증 + 실패 시 재시도
- `src/application/orchestrator.py` `_manage_position()`:
  - retCode != 0 또는 orderId 없으면 IN_POSITION 유지 (다음 tick 재시도)
  - Exception 발생 시 HALT 대신 IN_POSITION 유지
  - Entry order에도 동일 retCode 검증 추가

### Fix 9: Duplicate orderLinkId 해결
- 원인: exit order의 order_link_id = `exit_{signal_id}` -> recovered 포지션 재시작 시 중복
- `src/application/orchestrator.py`: `order_link_id=f"exit_{signal_id}_{timestamp}"` (타임스탬프 추가)

### Fix 10: pending_order order_id=None 시 position 확인
- `src/application/orchestrator.py` REST fallback:
  - order_id=None 시 position API로 실제 상태 확인
  - EXIT_PENDING + 포지션 없음 -> FLAT 복귀
  - ENTRY_PENDING + 포지션 있음 -> IN_POSITION

### Mock retCode 추가
- `tests/unit/test_orchestrator_entry_flow.py`: MockRestClient에 `retCode: 0` 추가
- `tests/unit/test_orchestrator_event_processing.py`: 동일
- `tests/integration_real/test_full_cycle_testnet.py`: 동일

### import time 정리
- `src/application/orchestrator.py`: 파일 최상단으로 이동, 로컬 import 4개 제거

### Mainnet 봇 상태 (22:33 KST)
- Container: d2a16c5927395
- LONG 1 contract @ $67,701.90 (recovered position)
- Current: $67,843, TP: $67,978 ($135 남음)
- 정상 동작 중, take-profit 대기

### 테스트 결과
- `pytest -q`: 410 passed, 15 deselected, 1 warning

## 3. Blocked / Issue
- (없음, 봇 정상 동작 중)

## 4. Decision / Change
- ADR 필요 여부: NO (기존 구현 버그 수정, 정책 변경 아님)
- Docker 빌드 순서: base -> bot (MEMORY.md에 기록 완료)

## 5. Next Action
- 봇 가동 상태 모니터링 (take-profit 대기)
- 첫 사이클 완료 후 재진입 검증
- 5 trades 완료 목표
