# ACCOUNT_BUILDER_SYSTEM.md (v2)

## 0. System Identity

This system is an **Account Builder Execution System**.

- Start: $100
- Target: $1,000
- Time Limit: 6–12 months (max 18)
- Absolute Failure: **Liquidation**

Survival is a constraint.  
Growth is the objective.

---

## 1. Account Growth Model (목표 함수)

### Dual Objective
1. **Primary**: Avoid liquidation (always)
2. **Secondary**: Reach $1,000 within time limit

### Growth Stages

#### Stage 1 — Expansion ($100 → $300)
- Time target: 3–4 months
- Mode: Aggressive
- Purpose: Capital base creation

#### Stage 2 — Acceleration ($300 → $700)
- Time target: 2–4 months
- Mode: Balanced
- Purpose: Compounding with control

#### Stage 3 — Preservation ($700 → $1,000)
- Time target: 1–3 months
- Mode: Defensive
- Purpose: Capital protection + finish

---

## 2. Account Rules (불변 제약)

### R1. Liquidation = Failure
- Any liquidation event ends the system.

### R2. Loss Limits (Stage-based, absolute)

| Balance | Max Loss / Trade |
|------|------------------|
| $100–$300 | ≤ $10 |
| $300–$700 | ≤ $20 |
| $700–$1,000 | ≤ $30 |

- 3 consecutive losses → position size -50%
- Balance < $80 → **Immediate HALT**

### R3. Time Constraint
- 12 months without reaching $200 → strategy review
- 18 months without $1,000 → system failure

---

## 3. Leverage Policy

### R4. Leverage Control
- Default: **3x**
- Increase: ❌ forbidden
- Decrease: ✅ allowed

### Liquidation Distance
- Always ≥ 30%
- Balance > $500 → consider 2x

---

## 4. Fee Optimization (Small Account Critical)

### R5. Fee Rules
- Balance < $300 → **Maker-only**
- Expected Profit < (Fee + Slippage) × 3 → Entry forbidden
- Max trades per day: 5

> Fees are treated as **real risk**, not noise.

---

## 5. Trading Flow (Fixed)

[1] Market Data
↓
[1.5] Emergency Check (Priority 0)
↓
[2] Signal Decision
↓
[3] Risk Gate
↓
[4] Position Sizing
↓
[5] Order Execution

yaml
코드 복사

Any deviation = architecture violation.

---

## 6. Entry Conditions (Mandatory)

A trade is allowed only if ALL conditions hold:

- EV > Fee × 2
- Backtest Winrate ≥ 55%
- Recent volatility ≥ threshold
- Emergency state = FALSE

No discretionary overrides.

---

## 7. Emergency Rules (Top Priority)

Immediate HALT if:
- Price drop ≥ -20% (short window)
- Exchange latency > 5s
- Balance anomaly
- Liquidation warning

Emergency always overrides Signal/Risk.

---

## 8. Final Success Criteria

The system is considered successful ONLY if:

- Balance ≥ $1,000
- No liquidation
- Within time limit

Survival without growth is **failure**.
4️⃣ 이 문서가 갖는 의미 (중요)
이제 이 문서는:

❌ “망하지 말자” 문서 아님

❌ “보수적 트레이딩 철학” 아님

✅ Account Builder의 실행 헌법

✅ 코드가 따라야 할 목적 함수 + 제약식

그리고 이제서야:

“왜 Risk가 이만큼 빡센가”
“왜 진입을 거부하는가”
“왜 Maker 강제인가”

가 전부 계좌 관점에서 설명 가능해졌다.