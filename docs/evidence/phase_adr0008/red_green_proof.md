# RED → GREEN Proof: ADR-0008 FLOW v1.9 Implementation

**Date**: 2026-01-23
**ADR**: ADR-0008
**Status**: ✅ PASS (All Gates 8-12)

---

## Phase 1: Document Modifications (FLOW.md v1.8 → v1.9)

### Changes Applied
1. **SSOT 중복 제거**: Section 2.5 DEGRADED/Stop 규칙 중복 제거, cross-reference로 교체
2. **REST Budget 정렬**: Tick 목표 1초 → 2초 (90 calls/min 일치)
3. **State Invariants 표 추가**: 6개 상태별 불변 조건 명문화
4. **COOLDOWN 해제 조건 명확화**: 30분 + 5분 안정
5. **WS 이벤트 계약 추가**: Section 2.7 (dedup/ordering)
6. **Complete Failure 시나리오 3종 추가**
7. **Code Enforcement 요구사항 추가**: Section 10.1

### Verification
```bash
grep "현재 버전.*v1.9" docs/constitution/FLOW.md
# Output: **현재 버전**: FLOW v1.9 (2026-01-23)

grep -n "ADR-0008" docs/constitution/FLOW.md
# Output: 2297:- v1.9 (2026-01-23): ... (ADR-0008)
```

---

## Phase 2: Code Implementation

### 2.1 Gate 9: WS Event Processor

**File**: `src/adapter/ws_event_processor.py`

**RED State** (Before):
```bash
test -f src/adapter/ws_event_processor.py
# Output: (file does not exist)
```

**Implementation**:
- Created `WSEventProcessor` class
- Implemented `process_event()` with deduplication logic
- Implemented `_generate_dedup_key()` using order_id + type + timestamp

**GREEN State** (After):
```bash
test -f src/adapter/ws_event_processor.py && echo "✓ EXISTS"
# Output: ✓ EXISTS

grep -n "def process_event" src/adapter/ws_event_processor.py
# Output: 49:    def process_event(

grep -n "def _generate_dedup_key" src/adapter/ws_event_processor.py
# Output: 89:    def _generate_dedup_key(self, event: ExecutionEvent) -> str:
```

---

### 2.2 Gate 10: Position Manager (Stop Status Loop)

**File**: `src/application/position_manager.py`

**RED State** (Before):
```bash
test -f src/application/position_manager.py
# Output: (file does not exist)
```

**Implementation**:
- Created `manage_stop_status()` function
- Enforces IN_POSITION check (FLOW Section 1)
- Implements stop_recovery_fail_count >= 3 → HALT rule
- Implements _calculate_stop_price() helper

**GREEN State** (After):
```bash
test -f src/application/position_manager.py && echo "✓ EXISTS"
# Output: ✓ EXISTS

grep -n "if current_state != State.IN_POSITION" src/application/position_manager.py
# Output: 46:    if current_state != State.IN_POSITION:

grep -n "stop_recovery_fail_count >= 3" src/application/position_manager.py
# Output:
# 14:- stop_recovery_fail_count >= 3: ERROR → HALT
# 40:    - stop_recovery_fail_count >= 3 → HALT
# 60:        if current_position.stop_recovery_fail_count >= 3:
```

---

## Phase 3: Oracle Tests

### 3.1 Gate 11: Oracle Test Scenarios

**File**: `tests/oracles/test_flow_v1_9_scenarios.py`

**RED State** (Before):
```bash
test -f tests/oracles/test_flow_v1_9_scenarios.py
# Output: (file does not exist)

pytest tests/oracles/test_flow_v1_9_scenarios.py -v
# Output: ERROR: file not found
```

**Implementation**:
- Test 1: `test_event_dedup_ignores_duplicate` - WS dedup verification
- Test 2: `test_stop_recovery_3_failures_halt` - Stop recovery HALT verification

**GREEN State** (After):
```bash
pytest tests/oracles/test_flow_v1_9_scenarios.py -v
# Output:
# test_event_dedup_ignores_duplicate PASSED [ 50%]
# test_stop_recovery_3_failures_halt PASSED [100%]
# ============================== 2 passed in 0.01s ===============================
```

---

## Gate 8: transition SSOT (Pre-existing, Verified)

**Status**: ✅ ALREADY COMPLIANT

```bash
find src -name "*.py" -type f -exec grep -l "^def transition(" {} \;
# Output: src/application/transition.py (single file only)

grep -n "State\." src/application/event_router.py
# Output: (empty - no State enum references)
```

---

## Gate 12: SSOT Alignment

**Status**: ✅ PASS

```bash
grep "현재 버전.*v1.9" docs/constitution/FLOW.md
# Output: **현재 버전**: FLOW v1.9 (2026-01-23)

grep -n "ADR-0008" docs/constitution/FLOW.md
# Output:
# 2297:- v1.9 (2026-01-23): 헌법 강제력 확보 및 내부 정합성 개선 (ADR-0008)
# 2306:  - 참조: ADR-0008
```

---

## Debugging Steps (HaltIntent Schema Fix)

### Issue 1: ExecutionEvent field mismatch
**Error**: `ExecutionEvent.__init__() got an unexpected keyword argument 'execution_id'`

**Fix**: Modified test to use actual ExecutionEvent fields:
- Removed: `execution_id`, `exec_time`
- Added: `order_id`, `order_link_id`, `timestamp`, `filled_qty`, `order_qty`

### Issue 2: HaltIntent detail parameter
**Error**: `TypeError: HaltIntent.__init__() got an unexpected keyword argument 'detail'`

**Root Cause**: HaltIntent only has 'reason' field (no 'detail' field)

**Fix Applied**:
1. Removed `detail=` parameter from all HaltIntent instantiations in `position_manager.py`
2. Concatenated detail text into `reason` string
3. Updated test assertion from `.detail` to `.reason`

**Files Modified**:
- `src/application/position_manager.py` (Lines 51, 63, 79)
- `tests/oracles/test_flow_v1_9_scenarios.py` (Line 110)

**Verification**:
```bash
pytest tests/oracles/test_flow_v1_9_scenarios.py::TestFlowV19Scenarios::test_stop_recovery_3_failures_halt -v
# Before: FAILED (TypeError: detail parameter)
# After:  PASSED [100%]
```

---

## Final Verification: All Gates PASS

```bash
# Gate 8: transition SSOT ✓
# Gate 9: WS Event Processor ✓
# Gate 10: Stop Status Loop ✓
# Gate 11: Oracle Tests (2/2 PASSED) ✓
# Gate 12: SSOT Alignment ✓
```

**Result**: ✅ **ALL GATES PASSED** - ADR-0008 Implementation Complete

---

## Reproducibility

To reproduce RED → GREEN transition:

```bash
# 1. Verify initial RED state (files don't exist)
test -f src/adapter/ws_event_processor.py || echo "RED: ws_event_processor.py missing"
test -f src/application/position_manager.py || echo "RED: position_manager.py missing"
test -f tests/oracles/test_flow_v1_9_scenarios.py || echo "RED: test file missing"

# 2. Apply implementation (create files)
# (Files created as shown in Phase 2-3 above)

# 3. Verify GREEN state
pytest tests/oracles/test_flow_v1_9_scenarios.py -v
# Expected: 2 passed in 0.01s

# 4. Run full gate verification
./scripts/verify_phase_completion.sh adr0008  # (if script exists)
# OR manually run Gate 8-12 checks (see gate_verification.txt)
```
