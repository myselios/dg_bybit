# Phase 9b Completion Checklist (Per-Trade Cap Reduction)
Date: 2026-01-23
Status: ✅ COMPLETE

## DoD 검증 (Definition of DONE)

### Phase 9b DoD (task_plan.md 기준)

#### 1. account_builder_policy.md 수정 (ADR 필요)
✅ **PASS** - Stage 1 설정 변경 완료

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

**변경 위치**:
- [account_builder_policy.md](../specs/account_builder_policy.md) Section 5.1 (Line 177-178)
- [account_builder_policy.md](../specs/account_builder_policy.md) Section 6 (Line 221, 226)

#### 2. ADR 작성 (ADR-0001)
✅ **PASS** - ADR-0001 작성 완료

**파일**: [ADR-0001-per-trade-loss-cap-reduction.md](../adrs/ADR-0001-per-trade-loss-cap-reduction.md)

**핵심 내용**:
- **Context**: 현재 $10 cap (10% equity)은 작은 계좌에 치명적
- **Decision**: $10 → $3 (3% equity)로 감소
- **Rationale**:
  - Session Risk (Daily -5%)와 일관성
  - 생존성 우선 (복구 가능성)
  - 치명적 시나리오 방지 (2회 손실 후 Daily cap 발동)
- **Consequences**:
  - Positive: 계좌 생존성 향상, Session Risk와 조화
  - Negative: 성장 속도 느려짐, 거래 기회 제한

#### 3. 테스트 업데이트 (sizing.py 테스트)
✅ **PASS** - test_entry_allowed.py 수정 완료

**수정 파일**: [test_entry_allowed.py](../../tests/unit/test_entry_allowed.py)

**변경 내용**:
```python
# Before
STAGE_1 = StageParams(
    max_loss_usd_cap=10.0,
    loss_pct_cap=0.12,
)

# After
STAGE_1 = StageParams(
    max_loss_usd_cap=3.0,
    loss_pct_cap=0.03,
)
```

**미수정 파일**: [test_sizing.py](../../tests/unit/test_sizing.py)
- 이유: max_loss_btc를 직접 사용 (policy 값 무관)
- 영향: 없음 (sizing 로직 자체는 변경 없음)

---

## 전체 테스트 결과

### Pytest 실행 (Phase 9b 변경 후)
```bash
source venv/bin/activate && pytest -q
```

**결과**: ✅ **203 passed, 15 deselected in 0.21s**

**Regression 검증**:
- Before (Phase 9a): 203 passed
- After (Phase 9b): 203 passed
- 변경: 0 (regression 없음)

---

## SSOT 준수

### task_plan.md Phase 9b 요구사항
✅ **PASS** - 모든 요구사항 충족

**요구사항**:
- [x] account_builder_policy.md 수정 (ADR 필요)
  - Stage 1: max_loss_usd_cap $10 → $3
  - Stage 1: loss_pct_cap 12% → 3%
- [x] ADR 작성 (ADR-0001)
- [x] 테스트 업데이트 (test_entry_allowed.py)

---

## Phase 9b 완료 선언

✅ **Per-Trade Cap 조정 완료 (Stage 1)**

**변경 요약**:
- **max_loss_usd_cap**: $10 → $3 (10% → 3%)
- **loss_pct_cap**: 12% → 3%
- **영향 범위**: Stage 1 only (equity < $300)
- **ADR**: ADR-0001 작성 완료
- **테스트**: 203 passed (regression 없음)

**근거**:
- Session Risk (Daily -5%)와 일관성 확보
- 생존성 우선 ("안 죽는 베팅")
- 치명적 시나리오 방지:
  - Before: 3회 × $10 = -$30 (-27.1% equity) — 치명적
  - After: 2회 × $3 = -$6 (-5.91%) → Daily cap 발동 — 안전

**Phase 9a + Phase 9b 시너지**:
- Phase 9a (Session Risk): Daily -5%, Weekly -12.5%, Loss Streak Kill, Fee/Slippage Anomaly
- Phase 9b (Per-Trade Cap): $3 (3% equity)
- 결과: **완전한 계좌 보호** (session 수준 + trade 수준)

**다음 단계**: Phase 9c (Orchestrator 통합 + 기존 안전장치)
