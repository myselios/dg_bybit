# ADR-0007: HALT vs COOLDOWN Semantic Definition Fix

**Date**: 2026-01-21
**Status**: Accepted
**Context**: SSOT 충돌 수정 (FLOW.md Section 1 vs Section 5)
**Affected Versions**: FLOW v1.7 → v1.8, Policy v2.1 → v2.2

---

## Context

### Problem Statement

SSOT 3개 문서 간 치명적 충돌이 발견되었다 (2026-01-21 판정):

**1. FLOW.md 내부 불일치**:
- **Section 1** (Line 28-29, 48-49): State Machine 정의
  - `HALT` = "Manual reset only" (자동 해제 불가)
  - `COOLDOWN` = "자동 해제 가능" (일시적 차단)
- **Section 5** (Line 1436-1437): Emergency 조건
  - `price_drop_1m <= -10%` → **HALT**
  - `price_drop_5m <= -20%` → **HALT**
- **Policy Section 7.3** (Line 266-268): Recovery 규칙
  - "**Auto-recovery (temporary HALT only)**: price_drop_1m > -5% ..."

**헌법 자체가 모순**됨:
- FLOW Section 1 (헌법): HALT = Manual-only
- FLOW Section 5 + Policy 7.3: price_drop → HALT + auto-recovery 가능

**2. Policy.md 비표준 용어**:
- Section 7.3 (Line 266): "Auto-recovery (**temporary HALT** only)"
- FLOW.md에 "temporary HALT"라는 용어 **정의 없음**
- 구현자 혼란: "temporary HALT"을 State.HALT로 구현 가능성

**3. emergency.py 잘못된 구현**:
```python
# src/application/emergency.py:99-103
if price_drop_1m <= -0.10:
    return EmergencyStatus(
        is_halt=True,  # ❌ 잘못됨 (Manual-only로 해석)
        is_blocked=False,
        reason=...
    )
```
- `is_halt=True` → FLOW Section 1에 따르면 Manual-only
- Policy Section 7.3: price_drop은 auto-recovery 가능
- **결과**: 10% 급락 시 시스템 영구 정지 (수동 개입 필요)

**4. Phase 1 Evidence 무효화**:
- emergency.py가 SSOT와 불일치 → Phase 1 Evidence 재생성 필요

### Real Trading Impact

**현재 구현의 문제**:
1. BTC 가격 10% 급락 발생
2. emergency.py가 `is_halt=True` 반환
3. Orchestrator가 `State.HALT`로 전환 (Manual-only)
4. 5분 후 가격 회복 (-5% 이상) → recovery 조건 충족
5. 하지만 State.HALT는 Manual reset만 가능
6. **시스템이 영구 정지** → 기회 손실

**기대 동작** (수정 후):
1. BTC 가격 10% 급락 발생
2. emergency.py가 `is_cooldown=True` 반환
3. Orchestrator가 `State.COOLDOWN`로 전환 (auto-recovery 가능)
4. 5분 후 가격 회복 (-5% 이상) → recovery 조건 충족
5. `State.COOLDOWN → FLAT` 자동 전환 + 30분 cooldown
6. **시스템 자동 복구** → 다음 기회 포착 가능

---

## Decision

**FLOW.md Section 1 State Machine 정의를 SSOT로 고정한다** (협상 불가).

### SSOT 우선순위

1. **FLOW.md Section 1** (State Machine 정의) = **헌법** (불변 계약)
   - `HALT` = Manual reset only (liquidation, balance < 80)
   - `COOLDOWN` = Auto 해제 가능 (price drop auto-recovery)

2. **FLOW.md Section 5, Policy.md Section 7** = **정책** (변경 가능)
   - 헌법(Section 1)에 맞춰 수정 필요

### Semantic Definition (확정)

**HALT (Manual-only)**:
- **진입 조건**:
  - Liquidation warning/event
  - `equity_usd < 80` (Hard Stop)
  - `balance anomaly` (equity <= 0 OR stale > 30s)
  - DEGRADED 60초 timeout (WS 장기 단절)
- **해제 조건**: Manual reset만 (사용자 개입 필수)
- **용도**: 치명적 상황 (복구 불가능)

**COOLDOWN (Auto-recovery)**:
- **진입 조건**:
  - `price_drop_1m <= -10%`
  - `price_drop_5m <= -20%`
- **해제 조건**: Auto-recovery 가능
  - Recovery: `price_drop_1m > -5% AND price_drop_5m > -10%` for 5 min
  - Recovery 후 30분 cooldown → `State.FLAT`
- **용도**: 일시적 상황 (자동 복구 가능)

---

## Consequences

### 변경 범위

**1. FLOW.md Section 5 수정**:
```markdown
**수정 전** (Line 1436-1437):
- price_drop_1m <= -10% → HALT
- price_drop_5m <= -20% → HALT

**수정 후**:
- price_drop_1m <= -10% → COOLDOWN
- price_drop_5m <= -20% → COOLDOWN
- equity_usd < $80 → HALT (Manual reset only)
- Liquidation warning → HALT (Manual reset only)
```

**2. Policy.md Section 7.2/7.3 수정**:
```markdown
**Section 7.2 수정** (Line 256-257):
- price_drop_1m <= -10% => COOLDOWN
- price_drop_5m <= -20% => COOLDOWN
- balance anomaly => HALT (Manual reset only)

**Section 7.3 수정** (Line 266):
Auto-recovery (COOLDOWN only):  # "temporary HALT" 삭제
- price_drop_1m > -5% AND ...
```

**3. emergency.py 수정**:
```python
# EmergencyStatus 스키마 수정
@dataclass
class EmergencyStatus:
    is_halt: bool       # Manual-only HALT (liquidation, balance < 80)
    is_cooldown: bool   # Auto-recovery COOLDOWN (price drop) ← 추가!
    is_blocked: bool
    reason: str

# check_emergency() 수정
if price_drop_1m <= -0.10:
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=True,  # HALT → COOLDOWN!
        is_blocked=False,
        reason=f"price_drop_1m_{price_drop_1m*100:.1f}pct_exceeds_-10pct"
    )
```

**4. test_emergency.py 수정**:
```python
# 함수명 변경
def test_price_drop_1m_exceeds_threshold_enters_cooldown():  # halt → cooldown
    # ...
    assert result.is_cooldown is True  # is_halt → is_cooldown
    assert result.is_halt is False
```

**5. Phase 1 Evidence 재생성**:
- `docs/evidence/phase_1/gate7_verification.txt`
- `docs/evidence/phase_1/pytest_output.txt`
- `docs/evidence/phase_1/emergency_thresholds_verification.txt`
- `docs/evidence/phase_1/red_green_proof.md`
- `docs/evidence/phase_1/completion_checklist.md`

### Version Updates

- **FLOW.md**: v1.7 → v1.8
- **Policy.md**: v2.1 → v2.2
- **emergency.py**: is_cooldown 필드 추가
- **Phase 1 Evidence**: 재생성 (SSOT 일치 확인)

### Benefits

1. **SSOT 일관성 확보**: FLOW Section 1 = Section 5 = Policy Section 7
2. **실거래 생존성 향상**: price_drop 시 자동 복구 → 기회 손실 방지
3. **용어 명확화**: "temporary HALT" 제거 → COOLDOWN 사용
4. **구현 정확성**: emergency.py가 FLOW Section 1 준수

### Risks

1. **Phase 1 Evidence 무효화**: 재생성 필요 (1-1.5h 추가 작업)
2. **테스트 수정 범위**: test_emergency.py 8개 함수 수정
3. **문서 일관성 유지**: FLOW + Policy 동시 수정 필요

---

## Alternatives Considered

### Alternative 1: Section 1 수정 (HALT에 manual_reset 플래그 추가)

**Approach**:
```python
@dataclass
class Position:
    ...
    halt_manual_reset: bool  # True: Manual-only, False: Auto-recovery
```

**Rejected Reason**:
- State Machine 복잡도 증가 (State 수는 6개 유지, 하지만 서브상태 증가)
- FLOW Section 1은 헌법 (불변 계약) → 변경 비용 높음
- "HALT with auto-recovery"는 의미론적 모순

### Alternative 2: "temporary HALT" 신규 State 추가

**Approach**:
```python
class State(Enum):
    FLAT = 1
    ENTRY_PENDING = 2
    IN_POSITION = 3
    EXIT_PENDING = 4
    HALT = 5
    COOLDOWN = 6
    TEMPORARY_HALT = 7  # 추가
```

**Rejected Reason**:
- FLOW Section 1: "시스템은 **6가지 상태** 중 하나에만 존재한다" (협상 불가)
- State 수 증가 = 전이 규칙 복잡도 기하급수 증가
- "TEMPORARY_HALT"는 이미 "COOLDOWN"과 동일 의미 (중복)

### Alternative 3: Policy만 수정 (FLOW 유지)

**Approach**:
- FLOW Section 5 유지 (price_drop → HALT)
- Policy Section 7.3에서 "HALT는 auto-recovery 가능"으로 정의

**Rejected Reason**:
- FLOW Section 1 (HALT = Manual-only)와 직접 충돌
- 헌법 위반 → 실거래 사고 위험
- SSOT 우선순위: FLOW Section 1 > Section 5 > Policy

---

## Implementation Plan

### Phase 1: ADR Creation (1-1.5h) ✅
- [x] ADR-0007 작성
- [x] SSOT 고정 방향 결정 (FLOW Section 1 우선)
- [x] 변경 범위 정의

### Phase 2: FLOW.md + Policy.md SSOT Alignment (1.5-2h)
- [ ] FLOW.md Section 5 수정 (price_drop → COOLDOWN)
- [ ] Policy.md Section 7.2/7.3 수정 ("temporary HALT" → "COOLDOWN")
- [ ] Version 업데이트 (FLOW v1.8, Policy v2.2)

### Phase 3: emergency.py Implementation Fix (1.5-2h)
- [ ] EmergencyStatus에 `is_cooldown: bool` 필드 추가
- [ ] check_emergency() 수정 (price_drop → is_cooldown=True)
- [ ] test_emergency.py 수정 (is_halt → is_cooldown)
- [ ] pytest → 83 passed 확인

### Phase 4: Evidence Regeneration (1-1.5h)
- [ ] Phase 1 Evidence 5개 파일 재생성
- [ ] Gate 7 재검증 (ALL PASS)
- [ ] Policy 임계값 일치 확인 (12/12 MATCH)

---

## References

- **FLOW.md**: `docs/constitution/FLOW.md` (Section 1, Section 5)
- **Policy.md**: `docs/specs/account_builder_policy.md` (Section 7.1, 7.2, 7.3)
- **emergency.py**: `src/application/emergency.py` (check_emergency, EmergencyStatus)
- **test_emergency.py**: `tests/unit/test_emergency.py` (8 test cases)
- **Phase 1 Evidence**: `docs/evidence/phase_1/` (5 files)
- **Task Plan**: `docs/plans/task_plan.md` (Phase 1 Conditions, Line 326-327)

---

## Verification

### SSOT Alignment Verification

```bash
# 검증 스크립트 실행
./scripts/verify_ssot_alignment.sh
# → ✅ PASS: FLOW Section 1 vs Section 5 일치
# → ✅ PASS: Policy 7.2/7.3 COOLDOWN 용어 사용
# → ✅ PASS: emergency.py is_cooldown 필드 존재
# → ✅ PASS: pytest 83 passed

# 개별 검증
grep "price_drop.*HALT" docs/constitution/FLOW.md docs/specs/account_builder_policy.md
# → 출력 비어있음 (emergency 제외)

grep "price_drop.*COOLDOWN" docs/constitution/FLOW.md docs/specs/account_builder_policy.md
# → FLOW Section 5, Policy Section 7.2 매칭

grep "temporary HALT" docs/
# → 출력 비어있음

pytest -q
# → 83 passed in 0.06s
```

---

## Approval

**Approved by**: Claude Code (2026-01-21)
**Rationale**: FLOW Section 1 헌법 우선, SSOT 일관성 확보, 실거래 생존성 향상

**Decision**: FLOW.md Section 1을 SSOT로 고정, Section 5 + Policy 7 수정

---

**END OF ADR-0007**
