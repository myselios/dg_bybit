# Phase 1 RED→GREEN Proof (ADR-0007 적용 후)

## Metadata
- **Phase**: 1 (Emergency & WS Health)
- **Date**: 2026-01-21 05:45 (KST)
- **Proof Type**: Retrospective + ADR-0007 Update
- **Latest Commit**: (ADR-0007 적용)
- **Status**: ✅ DONE with Evidence (COOLDOWN semantic 적용)

## Evidence Summary

### Gate 7 검증 통과 (ADR-0007 적용)
- **File**: [gate7_verification.txt](gate7_verification.txt)
- **Result**: ALL PASS (12개 커맨드 + Phase 1 특화 검증 3개 모두 통과)
  - (1a) Placeholder: 0개 ✅
  - (1b) Skip/Xfail: 0개 ✅
  - (1c) Assert: 166개 ✅ (163→166, is_cooldown assertions 추가)
  - (2a) 도메인 재정의: 0개 ✅
  - (2b) domain 모사 파일: 0개 ✅
  - (3) transition.py 존재 ✅
  - (4a) EventRouter 상태 분기: 0개 ✅
  - (4b) EventRouter State 참조: 0개 ✅
  - (5) sys.path hack: 0개 ✅
  - (6a) Deprecated wrapper: 0개 ✅
  - (6b) Migration 구 경로: 0개 ✅
  - (7) pytest: 83 passed ✅
  - (8) Phase 1 tests: 13 passed ✅ (COOLDOWN semantic 검증)
  - (9) emergency.py is_cooldown 필드 존재 ✅
  - (10) test_emergency.py is_cooldown assertions 존재 ✅

### pytest 실행 결과
- **File**: [pytest_output.txt](pytest_output.txt)
- **Result**: 83 passed in 0.07s
- **Phase 1 Tests**: 13 passed
  - test_emergency.py: 8 passed (COOLDOWN semantic 적용)
  - test_ws_health.py: 5 passed

### Policy 임계값 일치 검증
- **File**: [emergency_thresholds_verification.txt](emergency_thresholds_verification.txt)
- **Result**: 12 / 12 thresholds MATCH ✅
  - emergency.py: 8 thresholds (price drop → COOLDOWN, balance → HALT, latency → block, recovery)
  - ws_health.py: 4 thresholds (heartbeat, event drop, degraded timeout, recovery cooldown)

---

## RED→GREEN Reproduction (대표 케이스, ADR-0007 적용)

### Case 1: test_price_drop_1m_exceeds_threshold_enters_cooldown

**Test Location**: `tests/unit/test_emergency.py:28-48`

**Function Name Change** (ADR-0007):
- ❌ Before: `test_price_drop_1m_exceeds_threshold_enters_halt`
- ✅ After: `test_price_drop_1m_exceeds_threshold_enters_cooldown`

**Docstring Change** (ADR-0007):
- ❌ Before: `"""price_drop_1m <= -10%이면 HALT 진입 (FLOW Section 5 준수)."""`
- ✅ After: `"""price_drop_1m <= -10%이면 COOLDOWN 진입 (FLOW v1.8 준수)."""`

**Preconditions**:
```python
fake_data = FakeMarketData()
fake_data.inject_price_drop(pct_1m=-0.12, pct_5m=-0.05)  # -12%, -5%
```

**Expected Outcome (ADR-0007 변경)**:
```python
status = check_emergency(fake_data)

# ❌ Before (HALT semantic, ADR-0007 이전):
# assert status.is_halt is True
# assert status.is_blocked is False

# ✅ After (COOLDOWN semantic, ADR-0007 적용):
assert status.is_cooldown is True
assert status.is_halt is False
assert status.is_blocked is False
assert "price_drop_1m" in status.reason.lower()
```

**Implementation**: `src/application/emergency.py:103-109`
```python
# ❌ Before (ADR-0007 이전):
# if price_drop_1m <= -0.10:
#     return EmergencyStatus(
#         is_halt=True,  # Manual-only (잘못된 semantic)
#         is_blocked=False,
#         reason=f"price_drop_1m_{price_drop_1m*100:.1f}pct_exceeds_-10pct"
#     )

# ✅ After (ADR-0007 적용):
if price_drop_1m <= -0.10:
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=True,  # Auto-recovery (올바른 semantic)
        is_blocked=False,
        reason=f"price_drop_1m_{price_drop_1m*100:.1f}pct_exceeds_-10pct"
    )
```

**Verification Command**:
```bash
pytest tests/unit/test_emergency.py::test_price_drop_1m_exceeds_threshold_enters_cooldown -v
```

**Result**: ✅ PASSED

---

### Case 2: test_price_drop_5m_exceeds_threshold_enters_cooldown

**Test Location**: `tests/unit/test_emergency.py:50-70`

**Function Name Change** (ADR-0007):
- ❌ Before: `test_price_drop_5m_exceeds_threshold_enters_halt`
- ✅ After: `test_price_drop_5m_exceeds_threshold_enters_cooldown`

**Docstring Change** (ADR-0007):
- ❌ Before: `"""price_drop_5m <= -20%이면 HALT 진입 (FLOW Section 5 준수)."""`
- ✅ After: `"""price_drop_5m <= -20%이면 COOLDOWN 진입 (FLOW v1.8 준수)."""`

**Preconditions**:
```python
fake_data = FakeMarketData()
fake_data.inject_price_drop(pct_1m=-0.05, pct_5m=-0.22)  # -5%, -22%
```

**Expected Outcome (ADR-0007 변경)**:
```python
status = check_emergency(fake_data)

# ✅ After (COOLDOWN semantic):
assert status.is_cooldown is True
assert status.is_halt is False
assert status.is_blocked is False
assert "price_drop_5m" in status.reason.lower()
```

**Implementation**: `src/application/emergency.py:111-117`
```python
if price_drop_5m <= -0.20:
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=True,  # ✅ COOLDOWN (ADR-0007)
        is_blocked=False,
        reason=f"price_drop_5m_{price_drop_5m*100:.1f}pct_exceeds_-20pct"
    )
```

**Verification Command**:
```bash
pytest tests/unit/test_emergency.py::test_price_drop_5m_exceeds_threshold_enters_cooldown -v
```

**Result**: ✅ PASSED

---

### Case 3: test_balance_anomaly_zero_equity_halts

**Test Location**: `tests/unit/test_emergency.py:92-111`

**Note**: This test is **unchanged** by ADR-0007 (balance anomaly는 여전히 HALT semantic)

**Preconditions**:
```python
fake_data = FakeMarketData()
fake_data.inject_balance_anomaly()  # equity = 0
```

**Expected Outcome** (변경 없음):
```python
status = check_emergency(fake_data)

assert status.is_halt is True  # ✅ HALT (Manual-only)
assert status.is_blocked is False
assert "equity" in status.reason.lower() or "balance" in status.reason.lower()
```

**Implementation**: `src/application/emergency.py:72-78`
```python
if equity_btc <= 0.0:
    return EmergencyStatus(
        is_halt=True,  # ✅ HALT (Manual-only, 변경 없음)
        is_cooldown=False,
        is_blocked=False,
        reason="balance_anomaly_equity_zero_or_negative"
    )
```

**Verification Command**:
```bash
pytest tests/unit/test_emergency.py::test_balance_anomaly_zero_equity_halts -v
```

**Result**: ✅ PASSED

---

### Case 4: test_auto_recovery_after_5_consecutive_minutes

**Test Location**: `tests/unit/test_emergency.py:154-174`

**Note**: Auto-recovery는 COOLDOWN에만 적용되므로, ADR-0007과 semantic 일치

**Preconditions**:
```python
fake_data = FakeMarketData()
fake_data.inject_price_drop(pct_1m=-0.03, pct_5m=-0.08)  # -3%, -8% (recovery threshold 이내)

cooldown_started_at = time.time() - 301.0  # 5분 1초 전
```

**Expected Outcome**:
```python
recovery = check_recovery(fake_data, cooldown_started_at)

assert recovery.can_recover is True
assert recovery.cooldown_minutes == 30
```

**Implementation**: `src/application/emergency.py:171-183`
```python
recovery_threshold_1m = -0.05  # -5%
recovery_threshold_5m = -0.10  # -10%

if price_drop_1m > recovery_threshold_1m and price_drop_5m > recovery_threshold_5m:
    elapsed_minutes = (market_data.get_timestamp() - cooldown_started_at) / 60.0

    if elapsed_minutes >= 5.0:
        return RecoveryStatus(
            can_recover=True,
            cooldown_minutes=30
        )
```

**Verification Command**:
```bash
pytest tests/unit/test_emergency.py::test_auto_recovery_after_5_consecutive_minutes -v
```

**Result**: ✅ PASSED

---

## ADR-0007 Impact Analysis

### 변경 사항 요약

#### 1. EmergencyStatus Dataclass (emergency.py:23-37)
**Before**:
```python
@dataclass
class EmergencyStatus:
    is_halt: bool
    is_blocked: bool
    reason: str
```

**After**:
```python
@dataclass
class EmergencyStatus:
    """
    Emergency 평가 결과

    Attributes:
        is_halt: True이면 State.HALT (manual reset only - liquidation, balance < 80)
        is_cooldown: True이면 State.COOLDOWN (auto-recovery - price drop)
        is_blocked: True이면 emergency_block=True (진입 차단, State 변경 없음)
        reason: Emergency 사유 (로그/디버깅용)
    """
    is_halt: bool
    is_cooldown: bool  # ⭐ NEW FIELD
    is_blocked: bool
    reason: str
```

#### 2. price_drop 로직 (emergency.py:103-117)
**Before**:
```python
if price_drop_1m <= -0.10:
    return EmergencyStatus(is_halt=True, is_blocked=False, ...)  # ❌ 잘못된 semantic

if price_drop_5m <= -0.20:
    return EmergencyStatus(is_halt=True, is_blocked=False, ...)  # ❌ 잘못된 semantic
```

**After**:
```python
if price_drop_1m <= -0.10:
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=True,  # ✅ 올바른 semantic
        is_blocked=False,
        ...
    )

if price_drop_5m <= -0.20:
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=True,  # ✅ 올바른 semantic
        is_blocked=False,
        ...
    )
```

#### 3. Test Function Names (test_emergency.py)
**Before**:
- `test_price_drop_1m_exceeds_threshold_enters_halt`
- `test_price_drop_5m_exceeds_threshold_enters_halt`

**After**:
- `test_price_drop_1m_exceeds_threshold_enters_cooldown` ⭐
- `test_price_drop_5m_exceeds_threshold_enters_cooldown` ⭐

#### 4. Test Assertions (test_emergency.py)
**Before**:
```python
assert status.is_halt is True  # ❌ 잘못된 semantic 검증
assert status.is_blocked is False
```

**After**:
```python
assert status.is_cooldown is True  # ✅ 올바른 semantic 검증
assert status.is_halt is False
assert status.is_blocked is False
```

---

## TDD 방식 확인 (ADR-0007 적용)

### Phase 3: RED→GREEN→REFACTOR (2026-01-21)

#### RED 단계 (테스트 먼저 수정)
1. **test_emergency.py 수정** (함수명 + 어설션 변경)
   - `enters_halt` → `enters_cooldown`
   - `assert is_halt is True` → `assert is_cooldown is True`

2. **pytest 실행 → FAIL (RED)**
   ```
   AttributeError: 'EmergencyStatus' object has no attribute 'is_cooldown'
   ```

#### GREEN 단계 (최소 구현)
3. **emergency.py 수정** (is_cooldown 필드 추가 + 로직 변경)
   - EmergencyStatus에 `is_cooldown: bool` 추가
   - price_drop 로직: `is_halt=True` → `is_cooldown=True`
   - 모든 return 문에 `is_cooldown` 파라미터 추가

4. **pytest 실행 → PASS (GREEN)**
   ```
   tests/unit/test_emergency.py::test_price_drop_1m_exceeds_threshold_enters_cooldown PASSED
   tests/unit/test_emergency.py::test_price_drop_5m_exceeds_threshold_enters_cooldown PASSED
   ...
   8 passed in 0.01s
   ```

#### REFACTOR 단계
5. **Docstring 업데이트**
   - "HALT 진입" → "COOLDOWN 진입 (FLOW v1.8 준수)"
   - ADR-0007 참조 추가

6. **전체 테스트 실행 → ALL PASS**
   ```
   83 passed in 0.07s
   ```

---

## DoD (Definition of Done) 충족 확인 (ADR-0007 적용)

### 1) 관련 테스트 존재 및 업데이트
- ✅ tests/unit/test_emergency.py (8 cases)
  - ⭐ test_price_drop_1m_exceeds_threshold_enters_cooldown (UPDATED)
  - ⭐ test_price_drop_5m_exceeds_threshold_enters_cooldown (UPDATED)
  - test_price_drop_both_below_threshold_no_action
  - test_balance_anomaly_zero_equity_halts
  - test_balance_anomaly_stale_timestamp_halts
  - test_latency_exceeds_5s_sets_emergency_block
  - test_auto_recovery_after_5_consecutive_minutes
  - test_auto_recovery_sets_30min_cooldown

- ✅ tests/unit/test_ws_health.py (5 cases, 변경 없음)

### 2) RED→GREEN 증거 (ADR-0007)
- ✅ RED: test 수정 → AttributeError 발생
- ✅ GREEN: emergency.py 수정 → 8 passed
- ✅ REFACTOR: docstring 업데이트 → 83 passed

### 3) Gate 통과
- ✅ Gate 1 (Placeholder Zero Tolerance): PASS (166 asserts)
- ✅ Gate 2 (No Test-Defined Domain): PASS
- ✅ Gate 3 (Single Transition Truth): PASS
- ✅ Gate 7 (Self-Verification): PASS (12 커맨드)
- ✅ Gate 8 (Migration Protocol): PASS

### 4) Policy 일치 검증 (ADR-0007 적용)
- ✅ emergency_thresholds_verification.txt (12 / 12 thresholds MATCH)
- ✅ COOLDOWN semantic 검증 완료
- ✅ SSOT 준수 (FLOW v1.8 + Policy v2.2)

### 5) Evidence Artifacts 재생성 (ADR-0007)
- ✅ gate7_verification.txt (ADR-0007 적용 후 재생성)
- ✅ pytest_output.txt (ADR-0007 적용 후 재생성)
- ✅ emergency_thresholds_verification.txt (COOLDOWN semantic 반영)
- ✅ red_green_proof.md (본 문서, ADR-0007 적용 과정 기록)

---

## Deliverables 검증 (ADR-0007 적용)

### Application Layer
- ✅ **src/application/emergency.py** (updated)
  - `EmergencyStatus` dataclass에 `is_cooldown: bool` 필드 추가
  - `check_emergency()`: price_drop → COOLDOWN semantic 적용
  - `check_recovery()`: COOLDOWN에서만 auto-recovery 가능
  - Policy Section 7 (v2.2) 준수

- ✅ **src/application/ws_health.py** (변경 없음)
  - FLOW Section 2.4 준수

### Infrastructure Layer (변경 없음)
- ✅ **src/infrastructure/exchange/market_data_interface.py**
- ✅ **src/infrastructure/exchange/fake_market_data.py**

---

## 종합 판정

**Phase 1: ✅ DONE (DoD 충족 + Evidence 확보 + ADR-0007 완전 적용)**

- 모든 테스트 통과 (83 passed, Phase 1: 13 passed)
- Gate 1~8 모두 PASS
- Policy 임계값 일치 (12 / 12 thresholds MATCH)
- ADR-0007 (HALT vs COOLDOWN Semantic Fix) 완전 적용
  - EmergencyStatus.is_cooldown 필드 추가
  - price_drop → COOLDOWN semantic 적용
  - test 함수명 + assertion 업데이트
  - FLOW v1.8 + Policy v2.2 준수
- Evidence Artifacts 재생성 완료

**새 세션에서 검증 방법**:
```bash
# 빠른 확인
cat docs/evidence/phase_1/gate7_verification.txt | grep -E "FAIL|ERROR"
# → 출력 비어있으면 PASS

# COOLDOWN semantic 검증
grep "is_cooldown is True" tests/unit/test_emergency.py
# → 2개 assertion 확인 (test_price_drop_1m, test_price_drop_5m)

grep "is_cooldown=True" src/application/emergency.py
# → 2개 return statement 확인 (price_drop_1m, price_drop_5m)

# Policy 일치 재확인
cat docs/evidence/phase_1/emergency_thresholds_verification.txt | grep "COOLDOWN"
# → Price Drop 1m/5m에 COOLDOWN semantic 확인

# 전체 테스트 실행
pytest -q
# → 83 passed
```

**Phase 1 완료 + ADR-0007 적용 확인. SSOT 정렬 완료.**
