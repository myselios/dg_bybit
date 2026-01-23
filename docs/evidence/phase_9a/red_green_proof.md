# Phase 9a RED→GREEN Proof (Session Risk Policy)
Date: 2026-01-23

## RED: 구현 전 상태

### Session Risk Policy 없음
- `src/application/session_risk.py`: 존재하지 않음
- Daily/Weekly Loss Cap: 없음
- Loss Streak Kill: 3연패 시 size 0.5배 축소만 (중단 없음)
- Fee/Slippage Anomaly HALT: 없음

### 테스트 없음
```bash
pytest tests/unit/test_session_risk.py
# ERROR: No module named 'application.session_risk'
```

### 치명적 문제
**현재 시스템은 "도박 단계"**:
- Per-trade cap만 있음 ($10)
- Session cap 없음 → 5연속 -$10 = -$50 (계좌 50%) 가능
- Daily/Weekly loss 제한 없음
- 연속 손실 중단 없음 (축소만)

---

## GREEN: 구현 후 상태 (Phase 9a 완료)

### Session Risk Policy 4개 구현
- [session_risk.py](../../src/application/session_risk.py) (203 LOC, 6 함수):
  1. **check_daily_loss_cap**: Daily loss ≤ -5% equity → HALT (다음날 UTC 0시까지)
  2. **check_weekly_loss_cap**: Weekly loss ≤ -12.5% equity → COOLDOWN (7일)
  3. **check_loss_streak_kill**: 3연패 HALT (당일), 5연패 COOLDOWN (72h)
  4. **check_fee_anomaly**: Fee spike 2회 연속 → HALT (30분)
  5. **check_slippage_anomaly**: Slippage spike 3회/10분 → HALT (60분)

### 테스트 15개 추가 및 통과
```bash
pytest tests/unit/test_session_risk.py -v
# 15 passed in 0.01s
```

#### 시나리오별 테스트

**Daily Loss Cap (3 cases)**:
- test_daily_loss_cap_not_exceeded: daily_pnl = -4%, cap = 5% → ALLOW
- test_daily_loss_cap_exceeded: daily_pnl = -6%, cap = 5% → HALT + cooldown
- test_daily_loss_cap_reset_at_boundary: UTC 경계 넘으면 리셋 → ALLOW

**Weekly Loss Cap (3 cases)**:
- test_weekly_loss_cap_not_exceeded: weekly_pnl = -10%, cap = 12.5% → ALLOW
- test_weekly_loss_cap_exceeded: weekly_pnl = -15%, cap = 12.5% → COOLDOWN (7일)
- test_weekly_loss_cap_reset_at_boundary: 주 경계 넘으면 리셋 → ALLOW

**Loss Streak Kill (3 cases)**:
- test_loss_streak_2: loss_streak = 2 → ALLOW
- test_loss_streak_3_halt: loss_streak = 3 → HALT (당일 종료)
- test_loss_streak_5_cooldown: loss_streak = 5 → COOLDOWN (72h)

**Fee/Slippage Anomaly (6 cases)**:
- test_fee_spike_single: fee_ratio 1.6 1회 → ALLOW
- test_fee_spike_consecutive_halt: fee_ratio [1.6, 1.7] 연속 → HALT (30분)
- test_fee_spike_non_consecutive: [1.6, 1.0, 1.7] 비연속 → ALLOW
- test_slippage_spike_2_times: 10분 내 2회 → ALLOW
- test_slippage_spike_3_times_halt: 10분 내 3회 → HALT (60분)
- test_slippage_spike_window_expired: 11분 전 spike → 카운트 제외

---

## 전체 테스트 결과

### 기본 실행
```bash
pytest -q
# 203 passed, 15 deselected in 0.20s
```
- 기존 188 tests + 신규 15 tests = 203 passed
- 기존 테스트 모두 통과 (regression 없음)

---

## RED→GREEN 전환 증명

### RED (구현 전)
- ❌ Session Risk Policy 없음
- ❌ Daily/Weekly Loss Cap 없음
- ❌ Loss Streak Kill 없음 (축소만)
- ❌ Fee/Slippage Anomaly HALT 없음
- ❌ 테스트 없음
- ❌ **도박 단계** (계좌 0까지 거래 가능)

### GREEN (Phase 9a 완료)
- ✅ Session Risk Policy 4개 구현 (203 LOC)
- ✅ Daily Loss Cap (5% → HALT)
- ✅ Weekly Loss Cap (12.5% → COOLDOWN 7일)
- ✅ Loss Streak Kill (3연패 HALT, 5연패 COOLDOWN 72h)
- ✅ Fee/Slippage Anomaly HALT (2회 연속, 3회/10분)
- ✅ 테스트 15개 통과
- ✅ **계좌 보호 단계** (Session cap이 계좌를 보호)

### 재현 가능성
모든 테스트는 재현 가능:
```bash
pytest tests/unit/test_session_risk.py -v
# 15 passed in 0.01s
```

---

## 결론

✅ **RED→GREEN 전환 완료**
- Phase 9a 시작 전: Session Risk 없음 (도박 단계)
- Phase 9a 완료: Session Risk 4개 구현 (계좌 보호)
- 15 tests passed (4개 정책 × 평균 3.75 cases)
- SSOT 준수 (task_plan.md Phase 9a)
- CLAUDE.md Section 5.7 모든 Gate 통과

**Phase 9a 완료 기준 충족**:
- Session Risk가 계좌를 보호함 (도박 종료) ✅
