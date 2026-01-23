# Phase 9b Policy Change Proof (Per-Trade Cap Reduction)
Date: 2026-01-23

## Before: Stage 1 설정 (Phase 9a 완료 시점)

### account_builder_policy.md

**Section 5.1 — Stage 1 (Line 177-178)**:
```yaml
max_loss_usd_cap: $10
loss_pct_cap: 12%
```

**Section 6 — Loss Budget (Line 221, 226)**:
```yaml
Stage USD caps:
- Stage 1: max_loss_usd_cap = $10

BTC percentage caps:
- Stage 1: pct_cap = 12%
```

### test_entry_allowed.py (Line 73-74)

```python
STAGE_1 = StageParams(
    max_loss_usd_cap=10.0,
    loss_pct_cap=0.12,
)
```

### 문제점

**치명적 시나리오**:
- Equity $100에서 $10 손실 1회 → **-10% equity**
- 복구 필요: +11.1% equity ($90 → $100)
- 연속 2회 손실 시 → **-19% equity** ($100 → $90 → $72.9)
- 연속 3회 손실 시 → **-27.1% equity** ($100 → $72.9)

**Session Risk와 불일치**:
- Daily cap: -5% equity
- Per-trade cap: -10% equity (Daily cap의 2배!)
- 1회 거래만으로 Daily cap 초과 가능 → Session Risk 무력화

**"도박" 단계**:
- 10% 손실 1회는 작은 계좌에 치명적
- 복구 어려움 (−10% → +11.1% 필요)

---

## After: Stage 1 설정 (Phase 9b 완료)

### account_builder_policy.md

**Section 5.1 — Stage 1 (Line 177-178)**:
```yaml
max_loss_usd_cap: $3
loss_pct_cap: 3%
```

**Section 6 — Loss Budget (Line 221, 226)**:
```yaml
Stage USD caps:
- Stage 1: max_loss_usd_cap = $3

BTC percentage caps:
- Stage 1: pct_cap = 3%
```

### test_entry_allowed.py (Line 73-74)

```python
STAGE_1 = StageParams(
    max_loss_usd_cap=3.0,
    loss_pct_cap=0.03,
)
```

### 개선 효과

**안전 시나리오**:
- Equity $100에서 $3 손실 1회 → **-3% equity**
- 복구 필요: +3.09% equity ($97 → $100)
- 연속 2회 손실 시 → **-5.91% equity** ($100 → $97 → $94.09) → **Daily cap 발동** (HALT)
- 연속 3회 손실 **불가** (Daily cap 발동으로 차단)

**Session Risk와 일관성**:
- Daily cap: -5% equity
- Per-trade cap: -3% equity (Daily cap의 60%)
- 2회 거래 후 Daily cap 발동 → Session Risk 정상 작동

**"계좌 보호" 단계**:
- 3% 손실은 복구 가능 (−3% → +3.09% 필요)
- 치명적 시나리오 차단 (2회 손실 후 HALT)

---

## 변경 내역

### Modified Files

1. **docs/specs/account_builder_policy.md**
   - Section 5.1 (Line 177-178): max_loss_usd_cap $10 → $3, loss_pct_cap 12% → 3%
   - Section 6 (Line 221, 226): Stage 1 caps 업데이트

2. **tests/unit/test_entry_allowed.py**
   - Line 73-74: STAGE_1 fixture 업데이트

3. **docs/adrs/ADR-0001-per-trade-loss-cap-reduction.md** (NEW)
   - 변경 근거 문서화

### Unchanged Files

**tests/unit/test_sizing.py**:
- 이유: max_loss_btc를 직접 사용 (policy 값 무관)
- 영향: 없음 (sizing 로직 자체는 변경 없음)

**Stage 2/3**:
- 변경 없음 (Stage 1만 조정)

---

## 시나리오 비교

### Equity $100, Stage 1

| Scenario | Before ($10 cap) | After ($3 cap) | Session Risk |
|----------|-----------------|----------------|--------------|
| 1회 손실 | -$10 (-10%) | -$3 (-3%) | Daily cap 미발동 |
| 복구 필요 | +11.1% | +3.09% | - |
| 2회 연속 | -$19 (-19%) | -$5.91 (-5.91%) | Daily cap 발동 (HALT) |
| 3회 연속 | -$27.1 (-27.1%) | **불가** (Daily cap 발동) | HALT |
| 최대 손실 | -27.1% (치명적) | -5.91% (안전) | - |

**결론**:
- **Before**: 3회 연속 손실 가능 → -27.1% equity (치명적, "도박")
- **After**: 2회 연속 손실 시 Daily cap 발동 → max -5.91% (보호됨, "안전")

---

## Validation

### Pytest 실행 결과

**Before (Phase 9a)**:
```bash
pytest -q
# 203 passed, 15 deselected in 0.20s
```

**After (Phase 9b)**:
```bash
pytest -q
# 203 passed, 15 deselected in 0.21s
```

**Regression**: 없음 (203 → 203)

### Gate 7 검증

✅ **모든 Gate 통과**
- Gate 1a (Placeholder): ✅ PASS (1개, 정당한 사유)
- Gate 1b (Skip decorator): ✅ PASS (0개)
- Gate 1c (Assert): ✅ PASS (315개)
- Gate 2a (도메인 재정의): ✅ PASS (0개)
- Gate 2b (domain 모사): ✅ PASS (0개)
- Gate 3 (transition SSOT): ✅ PASS
- Gate 4b (EventRouter): ✅ PASS (0개)
- Gate 5 (sys.path hack): ✅ PASS (0개)
- Gate 6b (Migration): ✅ PASS (0개)
- Gate 7 (pytest): ✅ PASS (203 passed)

---

## Before vs After 요약

### Before (Phase 9a 완료 시점)
- ❌ Per-trade cap: $10 (10% equity)
- ❌ Session Risk와 불일치 (Daily -5% < per-trade -10%)
- ❌ 치명적 시나리오: 3회 × $10 = -$30 (-27.1%)
- ❌ 복구 어려움 (−10% → +11.1%)
- ❌ "도박" 단계

### After (Phase 9b 완료)
- ✅ Per-trade cap: $3 (3% equity)
- ✅ Session Risk와 일관성 (Daily -5% > per-trade -3%)
- ✅ 안전 시나리오: 2회 × $3 = -$6 (-5.91%) → Daily cap 발동
- ✅ 복구 가능 (−3% → +3.09%)
- ✅ "계좌 보호" 단계

---

## 결론

✅ **Policy Change 완료**

**변경 요약**:
- max_loss_usd_cap: $10 → $3 (Stage 1)
- loss_pct_cap: 12% → 3% (Stage 1)

**근거**:
- ADR-0001: Per-Trade Loss Cap Reduction
- Session Risk (Phase 9a)와 일관성 확보
- 생존성 우선 ("안 죽는 베팅")

**결과**:
- 치명적 시나리오 차단 (2회 손실 후 Daily cap 발동)
- 복구 가능성 향상 (−3% vs −10%)
- Phase 9a + Phase 9b = **완전한 계좌 보호**

**새 세션 검증 가능**: Evidence Artifacts 생성 완료
