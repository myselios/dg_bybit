# ADR-0001: Per-Trade Loss Cap Reduction (Stage 1)

**Status**: Accepted
**Date**: 2026-01-23
**Deciders**: Account Builder Policy Review
**Related**: Phase 9b (Session Risk Policy + 운영 안전장치)

---

## Context and Problem Statement

현재 Stage 1 (equity < $300) per-trade loss cap은 다음과 같이 설정되어 있다:
- `max_loss_usd_cap`: **$10** (equity $100 기준 **10%**)
- `loss_pct_cap`: **12%**

**치명적 문제**:
- Equity $100에서 $10 손실 1회 → **-10% equity**
- 복구 필요: +11.1% equity ($90 → $100)
- 연속 2회 손실 시 → **-19% equity** ($100 → $90 → $72.9)
- 연속 3회 손실 시 → **-27.1% equity** ($100 → $72.9)

**Session Risk Policy (Phase 9a)와의 관계**:
- Phase 9a에서 구현한 Session Risk (Daily -5%, Weekly -12.5%, Loss Streak Kill)는 **session 수준 보호**
- 하지만 **per-trade cap이 너무 크면** session cap이 발동하기 전에 이미 치명적 손실 발생
- 예: $100 equity에서 $10 손실 1회만으로도 -10% (Daily cap -5% 이미 초과)

**핵심 문제**:
- "$100 → $1,000" 목표는 "**안 죽는 베팅**"이 우선이다
- 10% 손실 1회는 **작은 계좌에 치명적**이며, 이는 "도박"에 가깝다
- Session Risk가 있어도 **per-trade cap이 너무 크면 무용지물**

---

## Decision Drivers

1. **생존성 우선**: 성장 속도보다 계좌 생존이 최우선
2. **Session Risk와 일관성**: Daily cap -5%와 조화되는 per-trade cap 필요
3. **복구 가능성**: 손실 후 복구가 현실적으로 가능한 수준
4. **리스크 비대칭**: 작은 계좌는 한 번의 큰 손실이 치명적
5. **목표 기간**: 6-12개월 목표 (최대 18개월)는 "느리지만 안전한 성장" 허용

---

## Considered Options

### Option 1: Keep Current ($10, 12%)
**Pros**:
- 빠른 성장 가능 (단일 거래 수익도 큼)
- 변경 없음

**Cons**:
- ❌ 1회 손실로 -10% equity (치명적)
- ❌ Session Risk와 불일치 (Daily -5% < per-trade -10%)
- ❌ "도박" 단계 (생존성 낮음)
- ❌ 복구 어려움 (-10% → +11.1% 필요)

### Option 2: Reduce to $5 (5%)
**Pros**:
- Daily cap -5%와 정확히 일치
- 중간 수준의 보호

**Cons**:
- ❌ 여전히 1회 손실로 Daily cap 전체 소진
- ❌ 2회 연속 손실 시 -9.75% (여전히 큼)

### Option 3: Reduce to $3 (3%) — **SELECTED**
**Pros**:
- ✅ Daily cap -5% 대비 충분한 여유 (3% + 3% = 6% 초과 시 Daily cap 발동)
- ✅ 1회 손실 -3% → 복구 +3.09% (현실적)
- ✅ 2회 연속 손실 -5.91% → Daily cap 발동 직전 (안전장치 작동)
- ✅ 3회 연속 손실 불가 (Daily cap이나 Loss Streak Kill 발동)
- ✅ "안 죽는 베팅" 원칙 준수

**Cons**:
- 성장 속도 느려짐 (6-12개월 목표는 여전히 달성 가능)
- 거래당 수익도 제한됨

### Option 4: Reduce to $2 (2%)
**Pros**:
- 최대 보호

**Cons**:
- ❌ 너무 보수적 (18개월 내 $1,000 목표 달성 어려움)
- ❌ 거래 기회 제한 (EV gate 통과 어려움)

---

## Decision Outcome

**Chosen option**: **Option 3 — $3 (3%)**

### Rationale

1. **Session Risk와 일관성**:
   - Daily cap -5% 대비 per-trade cap 3%는 적절한 비율
   - 2회 연속 손실 시 -5.91% → Daily cap 발동 (안전장치 작동)

2. **생존성 vs 성장 균형**:
   - Equity $100 → $1,000 (10배) 목표는 "안 죽는 베팅"이 우선
   - 3% 손실은 복구 가능 (-3% → +3.09% 필요)
   - 10% 손실은 복구 어려움 (-10% → +11.1% 필요)

3. **치명적 시나리오 방지**:
   - Before: $10 × 3회 = -$30 (-27.1% equity) — **치명적**
   - After: $3 × 2회 = -$6 (-5.91%) → Daily cap 발동 — **안전**
   - Loss Streak Kill (3연패 HALT, 5연패 COOLDOWN)과 함께 작동

4. **목표 기간 내 달성 가능**:
   - 6-12개월 목표 (최대 18개월)는 "느린 성장" 허용
   - 3% cap으로도 충분히 달성 가능 (복리 효과)

5. **EV gate와 조화**:
   - Stage 1 EV gate: `expected_profit >= fee * 2.0`
   - $3 cap으로도 EV gate 통과 가능한 거래 존재

---

## Implementation

### Changes to `docs/specs/account_builder_policy.md`

**Before**:
```yaml
# Stage 1 (equity < $300)
max_loss_usd_cap: $10
loss_pct_cap: 12%
```

**After**:
```yaml
# Stage 1 (equity < $300)
max_loss_usd_cap: $3
loss_pct_cap: 3%
```

**Affected Sections**:
- Section 5.1 Stage 1 — Expansion ($100 → $300)
- Section 6 Loss Budget (BTC percent with USD cap)

### Changes to Tests

**Affected Files**:
- `tests/unit/test_sizing.py` (if exists)
- `tests/oracles/test_sizing_oracle.py` (if exists)

**Required Updates**:
- Update test fixtures using `max_loss_usd_cap = 10.0` → `3.0`
- Update test fixtures using `loss_pct_cap = 12.0` → `3.0`
- Verify all sizing calculations with new caps

### Migration Strategy

1. **Document Update**: Update `account_builder_policy.md` first (SSOT)
2. **Test Update**: Update test fixtures and expected values
3. **Verification**: Run `pytest -q` to ensure no regressions
4. **Evidence**: Generate Phase 9b evidence artifacts
5. **No Code Changes**: `src/domain/sizing.py` already reads policy values from config (no hardcoded values)

---

## Consequences

### Positive

- ✅ **계좌 생존성 향상**: 1회 손실 -3% (복구 가능) vs -10% (치명적)
- ✅ **Session Risk와 일관성**: Daily cap -5% 내에서 2회 거래 가능
- ✅ **Loss Streak Kill과 조화**: 3연패 전에 Daily cap 발동 가능
- ✅ **복구 현실성**: -3% → +3.09% (vs -10% → +11.1%)
- ✅ **"도박" → "계좌 보호"**: Phase 9a (Session Risk) + Phase 9b (Per-trade cap) = 완전한 보호

### Negative

- ⚠️ **성장 속도 느려짐**: 단일 거래 수익/손실 모두 제한
- ⚠️ **거래 기회 제한**: 일부 거래는 EV gate 통과 어려움 (예: 수수료가 큰 경우)

### Neutral

- 📊 **목표 기간 유지**: 6-12개월 목표는 여전히 달성 가능 (복리 효과)
- 📊 **Stage 2/3는 유지**: Stage 2 ($20, 8%), Stage 3 ($30, 6%) 변경 없음

---

## Validation

### Scenario Analysis

**Equity $100, Stage 1**:

| Scenario | Before ($10 cap) | After ($3 cap) | Session Risk |
|----------|-----------------|----------------|--------------|
| 1회 손실 | -$10 (-10%) | -$3 (-3%) | Daily cap 미발동 |
| 2회 연속 | -$19 (-19%) | -$5.91 (-5.91%) | Daily cap 발동 (HALT) |
| 3회 연속 | -$27.1 (-27.1%) | **불가** (Daily cap 발동) | HALT |
| 복구 필요 | +11.1% | +3.09% | - |

**결론**:
- Before: 3회 연속 손실 가능 → **-27.1% equity** (치명적, "도박")
- After: 2회 연속 손실 시 Daily cap 발동 → **max -5.91%** (보호됨, "안전")

---

## References

- [CLAUDE.md Section 6](../../CLAUDE.md): ADR 규칙 (정책 변경)
- [account_builder_policy.md Section 0.1](../specs/account_builder_policy.md): ADR Required (구조/정의/단위 변경)
- [task_plan.md Phase 9b](../plans/task_plan.md): Per-trade cap 조정 요구사항
- [Phase 9a Evidence](../evidence/phase_9a/): Session Risk Policy 구현 증거

---

## Notes

- ADR 번호: **0001** (첫 ADR)
- 변경 범위: **Stage 1 only** (Stage 2/3는 변경 없음)
- 후속 작업: Phase 9c (Orchestrator 통합 + 기존 안전장치)
