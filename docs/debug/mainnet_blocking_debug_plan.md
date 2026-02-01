# Mainnet Dry-Run Blocking Issue - 체계적 디버깅 계획서
**작성일**: 2026-01-27
**상태**: IN PROGRESS
**우선순위**: CRITICAL (Phase 12b 진행 차단)

---

## 1. 문제 정의 (Problem Statement)

### 1.1 증상 (Symptoms)
```
2026-01-27 17:53:42,858 - ✅ Orchestrator initialized successfully
[이후 로그 없음 - 약 1분+ 동안 blocking]
```

**관찰된 현상**:
- Orchestrator 초기화: **성공** ✅
- Main loop 진입: **실패** ❌ (로그 없음)
- Process: **살아있음** (zombie 아님)
- CPU 사용률: 0% (I/O wait 또는 blocking call)

### 1.2 재현 조건
```bash
python scripts/run_mainnet_dry_run.py --target-trades 5 --force-entry --yes
```

**환경**:
- `BYBIT_TESTNET=false` (Mainnet mode)
- Bybit REST API: `https://api.bybit.com`
- Bybit WebSocket: `wss://stream.bybit.com/v5/private`
- Timeout 설정: 10초 (bybit_rest_client.py)

### 1.3 이전 시도 및 결과
1. **Position recovery 비활성화** → Orchestrator 초기화 성공 (하지만 main loop 진입 실패)
2. **Timeout 5→10초 증가** → 효과 없음
3. **Try-except 추가** → Orchestrator 초기화는 통과, 이후 문제

---

## 2. 가설 (Hypotheses)

### 가설 #1: run_mainnet_dry_run.py의 Main Loop 진입 전 Blocking
**가능성**: 90%
**근거**:
- Orchestrator 초기화 성공 로그 출력됨
- Main loop 첫 tick 로그가 없음
- Line 322-334 사이 어딘가에서 blocking

**검증 방법**:
```python
# Line 315 이후 각 라인마다 로그 추가
logger.info("✅ Orchestrator initialized successfully")
logger.info("🔍 DEBUG: About to enter main loop")  # <- 추가
previous_state = State.FLAT
logger.info("🔍 DEBUG: previous_state initialized")  # <- 추가
start_time = time.time()
logger.info("🔍 DEBUG: start_time initialized")  # <- 추가
```

### 가설 #2: Telegram notifier의 startup message (주석 처리했지만 다른 부분에서 호출)
**가능성**: 10%
**근거**:
- Telegram startup message는 주석 처리됨 (Line 300-303)
- 하지만 다른 곳에서 blocking call이 있을 수 있음

**검증 방법**:
```bash
# Telegram 완전 비활성화 테스트
TELEGRAM_ENABLED=false python scripts/run_mainnet_dry_run.py --target-trades 5 --force-entry --yes
```

### 가설 #3: BybitAdapter의 update_market_data() 내부 blocking
**가능성**: 5%
**근거**:
- Line 287 `bybit_adapter.update_market_data()` 성공 (로그 있음)
- 하지만 내부에서 background thread가 blocking될 수 있음

**검증 방법**:
- bybit_adapter.py의 update_market_data() 내부 로그 추가

---

## 3. 디버깅 전략 (Step-by-Step Plan)

### Phase 1: 로그 기반 범위 좁히기 (Log-Based Narrowing)
**목표**: Main loop 진입 전 정확한 blocking 지점 특정

#### Step 1.1: run_mainnet_dry_run.py에 세밀한 로그 추가
**파일**: `scripts/run_mainnet_dry_run.py`
**수정 범위**: Line 315-340

```python
# Line 315 이후
logger.info("✅ Orchestrator initialized successfully")

# Main loop
logger.info("🔍 DEBUG: Step A - About to initialize previous_state")
previous_state = State.FLAT
logger.info("🔍 DEBUG: Step B - previous_state = State.FLAT")

logger.info("🔍 DEBUG: Step C - About to call time.time()")
start_time = time.time()
logger.info(f"🔍 DEBUG: Step D - start_time = {start_time}")

logger.info("🔍 DEBUG: Step E - About to set tick_interval")
tick_interval = 1.0  # 1초마다 tick
logger.info(f"🔍 DEBUG: Step F - tick_interval = {tick_interval}")

try:
    logger.info("🔍 DEBUG: Step G - Entered try block")
    tick_count = 0
    logger.info(f"🔍 DEBUG: Step H - tick_count = {tick_count}")

    logger.info("🔍 DEBUG: Step I - About to enter while True loop")
    while True:
        logger.info(f"🔍 DEBUG: Step J - Inside while loop, tick_count = {tick_count}")
        tick_count += 1
        logger.info(f"🔍 DEBUG: Step K - Incremented tick_count to {tick_count}")
        # ...
```

**예상 결과**:
- 마지막으로 출력된 로그가 blocking 직전 지점

#### Step 1.2: 실행 및 결과 확인
```bash
timeout 30 python scripts/run_mainnet_dry_run.py --target-trades 5 --force-entry --yes 2>&1 | tee /tmp/debug_log_step1.txt
```

**판단 기준**:
- Step G까지 출력 → try 블록 진입 전 blocking
- Step I까지 출력 → while True 진입 전 blocking
- Step J 출력 없음 → while True 조건 평가 중 blocking

---

### Phase 2: 원인별 대응 (Root Cause Mitigation)

#### Case A: while True 진입 전 blocking
**원인 가능성**:
1. `previous_state = State.FLAT` → State enum import 문제?
2. `start_time = time.time()` → time module blocking?
3. `tick_interval = 1.0` → 변수 할당 blocking? (거의 불가능)

**해결책**:
```python
# Import 검증
import sys
logger.info(f"State module: {State.__module__}")
logger.info(f"time module: {time.__name__}")
```

#### Case B: while True 조건 평가 중 blocking
**원인 가능성**:
- Python interpreter 자체 문제 (매우 드묾)
- GIL 문제로 background thread가 blocking

**해결책**:
```python
# while True 대신 명시적 조건 사용
max_iterations = 10000
for iteration in range(max_iterations):
    logger.info(f"Iteration {iteration}")
    # ... main loop body
```

#### Case C: Telegram notifier background thread blocking
**원인 가능성**:
- TelegramNotifier.__init__()에서 background thread 시작?
- HTTP connection pool 생성 중 blocking?

**해결책**:
```bash
# Telegram 완전 비활성화
TELEGRAM_ENABLED=false python scripts/run_mainnet_dry_run.py --target-trades 5 --force-entry --yes
```

---

### Phase 3: WebSocket Client 의심 (Parallel Investigation)

#### Step 3.1: WebSocket client의 start() 이후 동작 확인
**파일**: `src/infrastructure/exchange/bybit_ws_client.py`

**검증 포인트**:
```python
# ws_client.start() 호출 후:
# 1. Background thread가 살아있는가?
# 2. Heartbeat/ping이 동작하는가?
# 3. Connection이 실제로 열려있는가?
```

**테스트**:
```python
# run_mainnet_dry_run.py에서:
ws_client.start()
time.sleep(3)
logger.info(f"WebSocket thread alive: {ws_client._ws_thread.is_alive() if hasattr(ws_client, '_ws_thread') else 'N/A'}")
```

---

## 4. 실행 절차 (Execution Procedure)

### 4.1 준비 작업
```bash
# 1. 기존 프로세스 정리
pkill -9 -f "run_mainnet_dry_run.py"

# 2. 로그 백업
cp logs/mainnet_dry_run/mainnet_dry_run.log logs/mainnet_dry_run/mainnet_dry_run.log.bak_$(date +%s)

# 3. 작업 브랜치 확인
git status
```

### 4.2 Phase 1 실행
```bash
# Step 1.1: 세밀한 로그 추가 (수동 편집)
# Step 1.2: 실행 및 로그 수집
timeout 30 python scripts/run_mainnet_dry_run.py --target-trades 5 --force-entry --yes 2>&1 | tee /tmp/debug_phase1.log

# Step 1.3: 로그 분석
grep "🔍 DEBUG: Step" /tmp/debug_phase1.log | tail -10
```

### 4.3 Phase 2 실행 (Phase 1 결과에 따라)
```bash
# Case A: while True 진입 전
# → Import 검증 로그 추가 후 재실행

# Case B: while True 조건 평가 중
# → for loop로 변경 후 재실행

# Case C: Telegram blocking
# → TELEGRAM_ENABLED=false로 재실행
```

### 4.4 Phase 3 실행 (병렬)
```bash
# WebSocket thread 상태 확인
# → ws_client.start() 이후 thread.is_alive() 로그 추가
```

---

## 5. 성공 기준 (Success Criteria)

### 5.1 최소 성공 (Minimum Viable Success)
```
✅ Main loop 진입 성공
✅ 첫 번째 tick 실행 시작 (로그: "Tick #1")
```

### 5.2 완전 성공 (Full Success)
```
✅ 5회 Entry-Exit 사이클 완료
✅ 정상 종료 (timeout 없이)
✅ Trade log JSONL 파일 생성 확인
```

---

## 6. Rollback Plan (문제 악화 시)

### 6.1 Rollback 조건
- 30분 이상 blocking 원인 미파악
- 코드 수정 후 더 심각한 에러 발생

### 6.2 Rollback 절차
```bash
# 1. 작업 중단
pkill -9 -f "run_mainnet_dry_run.py"

# 2. 코드 원복
git restore src/application/orchestrator.py
git restore scripts/run_mainnet_dry_run.py
git restore src/infrastructure/exchange/bybit_rest_client.py

# 3. Testnet으로 전환하여 동일 문제 재현 확인
BYBIT_TESTNET=true python scripts/run_testnet_dry_run.py --target-trades 5 --force-entry --yes
```

---

## 7. Evidence Artifacts (작업 완료 시 생성)

### 7.1 필수 Artifacts
```
docs/debug/
├── mainnet_blocking_debug_plan.md  (이 파일)
├── phase1_log_analysis.txt         (Phase 1 로그 분석)
├── root_cause_identified.md        (근본 원인 문서)
└── fix_validation.txt              (수정 검증 결과)
```

### 7.2 로그 백업
```
logs/mainnet_dry_run/
├── debug_phase1_$(date +%s).log
├── debug_phase2_$(date +%s).log
└── final_success_$(date +%s).log
```

---

## 8. 다음 단계 (Next Steps)

### 즉시 실행
1. **Phase 1 Step 1.1**: run_mainnet_dry_run.py에 세밀한 로그 추가 ✅
2. **Phase 1 Step 1.2**: 실행 및 로그 수집 (30초 timeout)
3. **로그 분석**: 마지막 출력된 Step 확인

### 분석 후 실행
- Phase 1 결과에 따라 Phase 2 또는 Phase 3 실행
- 근본 원인 파악 후 수정
- 검증: 5회 거래 완료 확인

---

## 9. 참고 자료 (References)

- CLAUDE.md Section 5.7: Self-Verification Before DONE
- CLAUDE.md Section 8: 작업 절차
- task_plan.md Phase 12b: Mainnet Dry-Run 요구사항
- Previous debugging: Phase 12a-4c REST API fallback 버그 수정

---

**작성자**: Claude Code
**검토 필요**: 사용자 승인 (Phase 1 실행 전)
