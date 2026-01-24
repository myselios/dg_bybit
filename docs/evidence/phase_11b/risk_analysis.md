# Phase 11b Risk Analysis — Full Orchestrator Integration + Testnet E2E

**작성일**: 2026-01-24
**Phase**: 11b (Full Orchestrator Integration + Testnet E2E)
**SSOT**: FLOW.md Section 2, task_plan.md Phase 11b DoD

---

## 1. 개요 (Overview)

Phase 11b는 **Full Orchestrator Integration + Testnet E2E**를 목표로 한다.

**구현 범위**:
1. Entry Flow: Signal → Gates → Sizing → Order placement
2. Exit Flow: Stop hit → Exit order (Phase 11a에서 기본 구현 완료)
3. Event Processing: FILL → Position update → Trade log
4. Testnet E2E: Full cycle (FLAT → ENTRY_PENDING → IN_POSITION → EXIT_PENDING → FLAT) 성공 (10회 거래)

**리스크 분석 목적**: 실거래 생존성 확보, 치명적 실패 지점 사전 차단

---

## 2. 치명적 리스크 (Critical Risks)

### 2.1 Entry Flow Integration — 누락된 로직

**현재 상태** ([orchestrator.py:264-287](../../src/application/orchestrator.py#L264-L287)):
```python
def _decide_entry(self) -> dict:
    """Entry 결정 (signal → gate → sizing)"""
    # degraded mode 체크만 있음
    ws_degraded = self.market_data.is_ws_degraded()
    if ws_degraded and self.state == State.FLAT:
        return {"blocked": True, "reason": "degraded_mode"}

    degraded_timeout = self.market_data.is_degraded_timeout()
    if degraded_timeout:
        self.state = State.HALT
        return {"blocked": True, "reason": "degraded_mode_timeout"}

    return {"blocked": False, "reason": None}
```

**문제 지점**:
- Signal 생성 로직 없음 (signal_generator.py 미통합)
- Entry gates 검증 없음 (entry_allowed.py 미통합)
- Sizing 계산 없음 (sizing.py 미통합)
- Order placement 없음 (bybit_rest_client.place_order 미호출)

**실거래 시 결과**:
1. **무조건 진입 차단**: Entry가 항상 blocked=False만 반환 → 거래 0건
2. **Gate 우회 리스크**: EV gate, ATR gate, maker-only gate 전부 우회 → 손실 누적
3. **Sizing 실패**: 계약 수 계산 없음 → Order placement 불가
4. **상태 전환 실패**: FLAT → ENTRY_PENDING 전환 로직 없음 → State Machine 정체

**해결 방향**:
1. Signal generation: `signal_generator.generate_signal()` 통합
2. Entry gates: `entry_allowed.check_entry_allowed()` 통합
3. Sizing: `sizing.calculate_contracts()` 통합
4. Order placement: `bybit_rest_client.place_order()` 호출
5. State transition: FLAT → ENTRY_PENDING 전환

---

### 2.2 Event Processing — FILL → Position Update 누락

**현재 상태** ([orchestrator.py:226-236](../../src/application/orchestrator.py#L226-L236)):
```python
def _process_events(self) -> None:
    """Events 처리 (WS 이벤트)"""
    # 이벤트 처리는 이미 event_handler.py에 구현되어 있음
    # 여기서는 통합만 수행 (최소 구현)
    pass
```

**문제 지점**:
- `pass`로만 구현 → Event processing 0건
- FILL event 수신 시 Position update 로직 없음
- ENTRY_PENDING → IN_POSITION 전환 로직 없음
- EXIT_PENDING → FLAT 전환 로직 없음

**실거래 시 결과**:
1. **ENTRY_PENDING 영구 정체**: Entry 주문 체결되어도 IN_POSITION으로 전환 안 됨
2. **Position 객체 미생성**: self.position이 None으로 유지 → Stop hit check 불가
3. **Exit 불가**: IN_POSITION이 아니므로 Exit decision 실행 안 됨
4. **State Machine 붕괴**: FLAT 이외 상태 진입 불가

**해결 방향**:
1. WS execution event 수신 통합 (bybit_ws_client.py 이미 구현)
2. FILL event → Position 생성 (entry_price, qty, direction, stop_price)
3. ENTRY_PENDING → IN_POSITION 전환
4. EXIT_PENDING → FLAT 전환 (청산 완료)

---

### 2.3 Testnet 실거래 리스크 — 네트워크/API 장애

**Testnet 특성**:
- 네트워크 불안정 (간헐적 timeout, 502/503 에러)
- 유동성 부족 (Maker order 체결 지연)
- Rate limit (1초당 10건)
- Order rejection (InsufficientBalance, PositionNotExist, InvalidQty)

**리스크 시나리오**:
1. **Entry order rejection** → ENTRY_PENDING 영구 정체
2. **Stop order rejection** → IN_POSITION + stop_status=MISSING
3. **Exit order rejection** → EXIT_PENDING 영구 정체
4. **WS disconnection** → FILL event 수신 실패 → State 불일치
5. **Rate limit 초과** → Order placement 실패 → 재시도 필요

**치명도**:
- **청산 불가 (Exit order rejection)**: 손실 무제한 확대 → 청산 위험
- **Stop 없는 상태 (Stop order rejection)**: Stop loss 보호 없음 → 손실 상한 없음
- **State 불일치 (WS disconnection)**: 포지션 있는데 FLAT 상태 → 중복 진입 → 레버리지 초과

**해결 방향**:
1. **Retry 로직**: Order rejection 시 3회 재시도 (exponential backoff)
2. **Stop recovery**: IN_POSITION + stop_status=MISSING → 즉시 Stop 재설치 (3회 실패 시 HALT)
3. **WS health check**: WS degraded → Entry 차단 (이미 구현, [orchestrator.py:274-278](../../src/application/orchestrator.py#L274-L278))
4. **Manual intervention**: HALT 상태 도달 시 수동 개입 필요 (Testnet 실행 중 감시)

---

### 2.4 Session Risk 발동 조건 — 실거래 중단

**Session Risk Policy** (Phase 9c):
- Daily Loss Cap: -5% equity → HALT
- Weekly Loss Cap: -12.5% equity → HALT
- Loss Streak Kill: 3연패 / 5연패 → HALT
- Fee Anomaly: 2회 연속 spike → HALT
- Slippage Anomaly: 3회/10분 → HALT

**Testnet DoD 요구사항**:
- "Session Risk 발동 확인 (Daily cap 또는 Loss streak, **최소 1회**)"

**문제**:
- Testnet에서 Session Risk를 **의도적으로 발동**시켜야 검증 완료
- Daily Loss Cap 발동 시 HALT → 거래 중단 → 10회 거래 미달

**리스크 시나리오**:
1. **Loss streak 3연패 발동** → 10회 거래 중 3연패 도달 → HALT → 거래 중단
2. **Daily Loss Cap 발동** → 5% 손실 도달 → HALT → 나머지 거래 불가
3. **Fee Anomaly 발동** → Taker order 2회 연속 → HALT (Maker-only 위반)

**해결 방향**:
1. **Session Risk 발동 시나리오 분리 테스트**: E2E 테스트 중 1개는 Session Risk 발동 전용 (HALT 도달 확인)
2. **10회 거래는 정상 경로 테스트**: Session Risk 발동 없이 10회 성공 (stop hit exit 포함)
3. **DoD 충족 증거**: (정상 10회 거래) + (Session Risk 발동 1회) = 총 2개 E2E 시나리오

---

## 3. 구조적 리스크 (Architectural Risks)

### 3.1 God Object 안티패턴 경계 — orchestrator.py 비대화

**현재 상태**:
- orchestrator.py: 288 LOC (Phase 6 기준)
- Entry flow 통합 시 예상 증가: +100~150 LOC (Signal, Gates, Sizing, Order placement)
- Event processing 통합 시 예상 증가: +50~80 LOC (FILL handling, Position update)

**최종 예상 크기**: 450~500 LOC

**FLOW.md Section 4.2 위반 가능성**:
- "God Object 금지 — 책임 분리"
- orchestrator.py가 500 LOC 초과 시 **God Object로 간주**

**해결 방향**:
1. **Thin wrapper 유지**: orchestrator.py는 호출만 수행, 로직은 각 모듈에 위임
2. **Helper 함수 분리**: Entry flow, Event processing을 별도 함수로 분리 (orchestrator.py 외부)
3. **책임 명확화**:
   - Signal generation: signal_generator.py
   - Entry gates: entry_allowed.py
   - Sizing: sizing.py
   - Order placement: bybit_rest_client.py (Infrastructure layer)
   - Event processing: event_handler.py (최소 통합, Application layer)

---

### 3.2 Infrastructure Layer 의존성 — REST/WS Client 안정성

**현재 의존 컴포넌트** (Phase 7-8):
- `bybit_rest_client.py` (460 LOC): place_order, cancel_order, amend_order
- `bybit_ws_client.py` (489 LOC): execution event subscription

**리스크 지점**:
1. **REST API timeout**: place_order 호출 시 5초 timeout → Order placement 실패
2. **WS disconnection**: execution event 수신 실패 → FILL event 누락 → State 불일치
3. **API key 권한 부족**: Testnet API key가 주문 권한 없음 → Unauthorized 403
4. **Rate limit**: 1초당 10건 제한 → 초과 시 429 에러

**치명도**:
- **Order placement 실패**: Entry 불가 → 거래 0건
- **FILL event 누락**: ENTRY_PENDING 영구 정체
- **Rate limit 초과**: HALT 도달 (API 차단)

**해결 방향**:
1. **Testnet API key 검증**: 실행 전 `get_wallet_balance` 호출 → 권한 확인
2. **Retry 로직**: REST timeout 시 3회 재시도 (exponential backoff)
3. **WS health check**: degraded mode 감지 → Entry 차단 (이미 구현)
4. **Rate limit 준수**: 주문 간격 최소 0.2초 (5 QPS 유지)

---

## 4. 데이터 일관성 리스크 (Data Consistency Risks)

### 4.1 Position vs State 불일치

**시나리오**:
1. Entry order FILL → Position 생성 (self.position ≠ None)
2. WS event 수신 실패 → State는 ENTRY_PENDING 유지
3. 다음 Tick: State=ENTRY_PENDING이지만 Position이 이미 존재

**문제 지점**:
- `self.position is not None` vs `self.state == State.IN_POSITION` 불일치
- Stop hit check는 `self.state == State.IN_POSITION` 조건 → Stop hit check 실행 안 됨
- 실제로는 Position이 있지만 Exit decision 우회

**치명도**:
- **Stop loss 보호 없음**: Position이 있는데 Stop hit check 안 됨 → 손실 무제한 확대

**해결 방향**:
1. **State 전환 원자성**: FILL event 수신 → (Position 생성 + State 전환) atomic 수행
2. **Self-healing check**: 매 Tick 시작 시 `self.position is not None` vs `self.state` 일치 검증
3. **불일치 감지 시 HALT**: Position ≠ None이지만 State=FLAT → HALT (치명적 불일치)

---

### 4.2 Order ID vs order_link_id 혼동

**Bybit API 특성**:
- `orderId`: Bybit가 생성하는 서버 ID (FILL event에 포함)
- `orderLinkId`: 클라이언트가 설정하는 custom ID (주문 추적용)

**리스크 시나리오**:
1. Entry order 발주 시 `orderLinkId="signal_123"` 설정
2. FILL event 수신 시 `orderId="abc-def-ghi"` 포함
3. Stop order 발주 시 어느 ID를 사용할까?

**혼동 지점**:
- Cancel order: `orderId` 또는 `orderLinkId` 둘 다 사용 가능
- Amend order: `orderId` 필수
- FILL event tracking: `orderLinkId` 매칭

**해결 방향**:
1. **orderLinkId 기준 추적**: signal_id 기반 orderLinkId 생성 (예: `entry_20260124_001`)
2. **orderId 저장**: FILL event 수신 시 orderId 저장 (Amend 시 필요)
3. **명확한 분리**:
   - Entry order: `orderLinkId="entry_{signal_id}"`
   - Stop order: `orderLinkId="stop_{signal_id}"`
   - Exit order: `orderLinkId="exit_{signal_id}"`

---

## 5. 테스트 전략 리스크 (Testing Strategy Risks)

### 5.1 Testnet E2E Test — 10회 거래 성공 조건

**DoD 요구사항**:
- "최소 10회 거래 성공 검증"
- "Full cycle 성공 (FLAT → Entry → Exit → FLAT)"

**문제**:
- 10회 거래를 **단일 테스트**에서 수행할까? (순차 실행)
- 10회 거래를 **병렬 테스트**로 분리할까? (각 테스트 1회 거래)

**병렬 테스트 리스크**:
- Position 공유 불가 (각 테스트는 독립 실행)
- Session Risk 상태 공유 불가 (Daily Loss Cap, Loss Streak)
- 10회 거래 **누적 검증 불가**

**순차 테스트 리스크**:
- 단일 테스트 실행 시간 길어짐 (10회 × 2분/회 = 20분)
- 중간 실패 시 나머지 거래 검증 불가
- pytest timeout (기본 5분) 초과

**해결 방향**:
1. **순차 E2E 테스트 1개**: 10회 거래 순차 실행 (timeout 30분 설정)
2. **각 거래는 독립 Signal**: signal_id 다르게 생성 (충돌 방지)
3. **중간 실패 허용**: 10회 중 7회 성공 = PASS (Testnet 불안정성 고려)
4. **Session Risk 발동 테스트는 분리**: 별도 E2E 테스트 (HALT 도달 확인)

---

### 5.2 RED → GREEN Proof — Placeholder 테스트 금지

**CLAUDE.md Section 5.1**:
- "Placeholder 테스트 금지 (Zero Tolerance)"
- `assert True`, `pass`, `TODO` 포함 테스트는 **테스트가 아니다**

**리스크 지점**:
- Testnet E2E 테스트는 **외부 네트워크 의존** → 불안정
- 네트워크 실패 시 `pytest.skip()` 사용 유혹 → Placeholder화

**해결 방향**:
1. **pytest.skip() 금지**: 네트워크 실패 시 FAIL로 처리 (재실행 필요)
2. **Retry 로직**: 네트워크 일시 장애 시 3회 재시도 (테스트 내부)
3. **Evidence Artifacts**: 실패 시 로그 저장 → 재현 가능하도록

---

## 6. 복구 시나리오 (Recovery Scenarios)

### 6.1 ENTRY_PENDING 영구 정체

**원인**:
- Entry order rejection (InsufficientBalance, InvalidQty)
- Entry order timeout (5초 초과)
- FILL event 수신 실패 (WS disconnection)

**복구 전략**:
1. **Timeout 감지**: ENTRY_PENDING 상태 60초 경과 → Entry order 취소 → FLAT 복귀
2. **Order status 재확인**: REST API로 order status 조회 → Filled이면 IN_POSITION 전환
3. **HALT 조건**: 복구 3회 실패 → HALT (수동 개입 필요)

---

### 6.2 IN_POSITION + stop_status=MISSING

**원인**:
- Stop order rejection (InvalidStopPrice, PositionNotExist)
- Stop order 체결 후 재설치 실패

**복구 전략** (FLOW.md Section 1: stop_status):
```python
if state == IN_POSITION and stop_status == MISSING:
    try:
        place_stop_loss(...)
        stop_status = ACTIVE
        stop_recovery_fail_count = 0
    except Exception as e:
        stop_recovery_fail_count += 1
        if stop_recovery_fail_count >= 3:
            stop_status = ERROR
            HALT(reason="stop_loss_unrecoverable")
```

**HALT 조건**:
- Stop 복구 3회 실패 → HALT (손실 상한 없음 방지)

---

### 6.3 EXIT_PENDING 영구 정체

**원인**:
- Exit order rejection (PositionNotExist)
- Exit order timeout
- FILL event 수신 실패

**복구 전략**:
1. **Timeout 감지**: EXIT_PENDING 상태 60초 경과 → Exit order 취소 → Exit order 재발주
2. **Order status 재확인**: REST API로 order status 조회 → Filled이면 FLAT 전환
3. **HALT 조건**: 복구 3회 실패 → HALT (청산 불가 방지)

---

## 7. 구현 우선순위 (Implementation Priority)

### 우선순위 1 (Critical Path)
1. **Entry Flow Integration** ([orchestrator.py:264-287](../../src/application/orchestrator.py#L264-L287))
   - Signal generation 통합
   - Entry gates 통합
   - Sizing 통합
   - Order placement 호출
   - FLAT → ENTRY_PENDING 전환

2. **Event Processing Integration** ([orchestrator.py:226-236](../../src/application/orchestrator.py#L226-L236))
   - FILL event → Position 생성
   - ENTRY_PENDING → IN_POSITION 전환
   - EXIT_PENDING → FLAT 전환

### 우선순위 2 (Risk Mitigation)
3. **Retry Logic** (Order rejection 대응)
   - place_order 3회 재시도
   - exponential backoff (0.5s, 1s, 2s)

4. **Stop Recovery** (IN_POSITION + stop_status=MISSING 대응)
   - Stop 재설치 로직
   - 3회 실패 시 HALT

### 우선순위 3 (E2E Testing)
5. **Testnet E2E Tests** (`tests/integration_real/test_full_cycle_testnet.py`)
   - 정상 경로 10회 거래 (순차 실행)
   - Session Risk 발동 시나리오 (HALT 확인)
   - Stop hit exit 시나리오 (청산 확인)

---

## 8. DoD 검증 기준 (Definition of Done Verification)

### Phase 11b DoD 체크리스트

- [ ] **Full Orchestrator Integration** (src/application/orchestrator.py 수정)
  - [ ] Entry decision: Signal → Gates → Sizing → Order placement
  - [ ] Exit decision: Stop hit → Place exit order (Phase 11a 통합 완료)
  - [ ] Event processing: FILL → Position update → Trade log

- [ ] **Testnet End-to-End Tests** (tests/integration_real/test_full_cycle_testnet.py)
  - [ ] Full cycle 성공 (FLAT → Entry → Exit → FLAT) - 5+ test cases
  - [ ] 최소 10회 거래 성공 검증 (순차 실행)
  - [ ] Session Risk 발동 확인 (Daily cap 또는 Loss streak, 최소 1회)

- [ ] **Evidence Artifacts** (docs/evidence/phase_11b/)
  - [ ] testnet_cycle_proof.md (Testnet full cycle 증거)
  - [ ] pytest_output.txt (pytest 실행 결과)
  - [ ] gate7_verification.txt (Section 5.7 검증 커맨드 출력)

- [ ] **Progress Table Update** (docs/plans/task_plan.md)
  - [ ] Phase 11b: TODO → DONE
  - [ ] Evidence 링크 추가
  - [ ] Last Updated 갱신

---

## 9. 결론 (Conclusion)

**치명적 리스크 요약**:
1. Entry Flow 누락 (현재 거래 불가) → **우선순위 1**
2. Event Processing 누락 (State 전환 불가) → **우선순위 1**
3. Testnet 네트워크 불안정 (Order rejection, WS disconnection) → **Retry + Recovery 로직 필수**
4. Session Risk 발동 (HALT 도달) → **별도 시나리오 분리 테스트**

**구현 방향**:
- **Thin wrapper 유지**: orchestrator.py는 호출만, 로직은 각 모듈에 위임
- **Atomic state transition**: FILL event → (Position 생성 + State 전환) 동시 수행
- **Retry + Recovery**: Order rejection, Stop recovery, WS reconnection 대응
- **E2E 순차 테스트**: 10회 거래 순차 실행 (중간 실패 허용 7/10)

**실거래 생존성 확보 조건**:
- Stop loss 보호 (IN_POSITION + stop_status=ACTIVE 강제)
- Session Risk 준수 (Daily/Weekly Loss Cap, Loss Streak Kill)
- HALT 조건 명확 (Stop recovery 3회 실패, Exit timeout)
- Manual intervention 가능 (HALT 상태 감시)

---

**다음 단계**: 리스크 분석 완료 → Entry Flow 구현 시작 (orchestrator.py 수정)
