# ADR-0002: Inverse to Linear USDT Migration

**Status**: Accepted
**Date**: 2026-01-25
**Deciders**: Account Builder Architecture Review
**Related**: Phase 12a-4 (Testnet Dry-Run Validation), Phase 0-11 (전체 아키텍처)

---

## Context and Problem Statement

현재 시스템은 **Bybit Inverse Futures (BTC Coin-Margined)** 기준으로 설계 및 구현되어 있다:
- **마진 통화**: BTC 필요
- **계약 단위**: 1 contract = 1 USD notional
- **Sizing 공식**: `loss_btc ≈ (contracts / entry_price_usd) * stop_distance_pct`
- **Fee 계산**: Inverse 특성 반영 (price cancels out in fee calculation)
- **PnL 계산**: BTC 기준 → USD 환산

**치명적 문제 (Phase 12a-4에서 발견)**:
- Bybit Testnet 계정에 **USDT $88,158**이 이미 존재하지만 **BTC는 0**
- Testnet에서 BTC를 받는 추가 절차가 필요함
- **Mainnet 실거래에서도 USDT가 더 일반적**:
  - USDT Linear Futures가 유동성이 더 높음
  - 대부분의 거래자가 USDT를 선호
  - 자금 관리가 더 직관적 (USD 기준 사고)

**핵심 문제**:
- 현재 설계(Inverse)는 **실용성이 낮음**
- Testnet 테스트를 위해서도 BTC를 별도로 받아야 함
- Mainnet 실거래에서도 USDT가 더 적합

---

## Decision Drivers

1. **실용성**: Testnet에 USDT가 이미 있음 → 즉시 테스트 가능
2. **Mainnet 준비**: USDT Linear Futures가 유동성/접근성 우수
3. **자금 관리 단순화**: USD 기준으로 사고 (BTC 가격 변동 영향 최소화)
4. **직관성**: Linear 공식이 더 직관적 (`loss_usd = qty * price * stop_distance_pct`)
5. **시장 표준**: 대부분의 거래자가 USDT Linear Futures 사용

---

## Considered Options

### Option 1: Keep Inverse (BTC Coin-Margined)
**Pros**:
- 코드 변경 불필요 (이미 구현됨)
- SSOT 문서와 일치
- 모든 테스트 통과

**Cons**:
- ❌ Testnet에서 BTC를 별도로 받아야 함 (시간 지연)
- ❌ Mainnet에서도 BTC 유동성/접근성 낮음
- ❌ 자금 관리 복잡 (BTC 가격 변동 영향)
- ❌ 실용성 낮음 (대부분의 거래자가 USDT 선호)

### Option 2: Migrate to Linear (USDT-Margined) — **SELECTED**
**Pros**:
- ✅ Testnet에 USDT $88,158 이미 존재 → 즉시 테스트 가능
- ✅ Mainnet 실거래에서 유동성/접근성 우수
- ✅ 자금 관리 단순화 (USD 기준 사고)
- ✅ Linear 공식이 더 직관적
- ✅ 시장 표준 준수

**Cons**:
- 코드 전면 수정 필요 (sizing, fee, PnL)
- SSOT 문서 전면 재작성 필요
- 모든 테스트 재작성 필요 (Oracle, Unit, Integration)
- 추정 작업 시간: 4-6시간

---

## Decision Outcome

**Chosen option**: **Option 2 — Linear USDT Migration**

### Rationale

1. **실용성 우선**:
   - Testnet 즉시 테스트 가능 (USDT 이미 있음)
   - Mainnet 실거래 준비 (유동성/접근성)

2. **장기 운영 안정성**:
   - 대부분의 거래자가 USDT 사용 → 시장 표준
   - 자금 관리 단순화 (BTC 가격 변동 영향 최소화)

3. **직관성**:
   - Linear 공식이 더 이해하기 쉬움
   - USD 기준 사고 (equity, loss, profit 모두 USD)

4. **변경 비용 수용 가능**:
   - Phase 12a 이전에 발견하여 다행 (실거래 전 수정)
   - 작업 시간 4-6시간은 충분히 투자할 가치

---

## Consequences

### Positive

1. **Testnet 즉시 테스트 가능** (USDT 이미 있음)
2. **Mainnet 실거래 준비** (유동성/접근성 우수)
3. **자금 관리 단순화** (USD 기준)
4. **시장 표준 준수** (대부분의 거래자가 USDT 사용)

### Negative

1. **전면적인 코드 수정 필요**:
   - sizing.py: Inverse → Linear 공식
   - fee 계산: Inverse 특성 제거
   - PnL 계산: BTC → USDT

2. **SSOT 문서 전면 재작성**:
   - account_builder_policy.md: Section 1.2, 6, 8, 10 전면 수정
   - CLAUDE.md: Inverse → Linear 변경

3. **모든 테스트 재작성**:
   - Oracle tests (transition, sizing, entry_allowed)
   - Unit tests (sizing, fee, PnL)
   - Integration tests (orchestrator)

4. **작업 시간**: 4-6시간 추정

### Neutral

- 핵심 아키텍처는 유지 (transition, intent, state machine)
- API 호출은 category="inverse" → category="linear"로만 변경

---

## Implementation Plan

### Phase 1: SSOT 문서 수정 (Document-First)

1. **ADR-0002 작성** (이 문서) ✅
2. **account_builder_policy.md 전면 재작성**:
   - Section 1.2: Linear 계약 단위 정의
   - Section 6: Loss Budget (USDT percent with USD cap)
   - Section 8: Fees Policy (Linear)
   - Section 10: Position Sizing (Linear)
3. **CLAUDE.md 수정**:
   - "Bybit Inverse" → "Bybit Linear (USDT-Margined)"
   - 모든 Inverse 언급 제거

### Phase 2: 코드 수정 (Implementation)

1. **sizing.py Linear 공식으로 변경**:
   ```python
   # Before (Inverse):
   # loss_btc_at_stop ≈ (contracts / entry_price_usd) * stop_distance_pct

   # After (Linear):
   # loss_usdt_at_stop = qty * entry_price_usd * stop_distance_pct
   # qty = loss_budget_usdt / (entry_price_usd * stop_distance_pct)
   ```

2. **fee 계산 수정**:
   ```python
   # Before (Inverse):
   # fee_usd ≈ contracts * fee_rate (price cancels out)

   # After (Linear):
   # fee_usdt = qty * entry_price_usd * fee_rate
   ```

3. **PnL 계산 수정**:
   ```python
   # Before (Inverse):
   # pnl_btc → pnl_usd (환산 필요)

   # After (Linear):
   # pnl_usdt (환산 불필요, 직접 계산)
   ```

4. **API 호출 수정**:
   - `category="inverse"` → `category="linear"`
   - `symbol="BTCUSD"` → `symbol="BTCUSDT"`

### Phase 3: 테스트 재작성 (RED→GREEN)

1. **Oracle tests 재작성**:
   - test_state_transition_oracle.py (변경 없음)
   - test_sizing_oracle.py (Linear 공식)
   - test_entry_allowed_oracle.py (변경 없음)

2. **Unit tests 재작성**:
   - test_sizing.py (Linear 공식 + 예제)
   - test_bybit_adapter.py (category="linear")
   - test_session_risk_tracker.py (변경 없음)

3. **Integration tests 업데이트**:
   - test_orchestrator_*.py (변경 최소)
   - test_dry_run_orchestrator.py (변경 없음)

### Phase 4: Evidence 생성

1. **RED→GREEN 증거**:
   - pytest 실행 결과 (FAIL → PASS)
   - 변경된 파일 목록
   - Git commit

2. **Evidence Artifacts**:
   - docs/evidence/adr_0002/
   - red_green_proof.md
   - pytest_output.txt
   - gate7_verification.txt

---

## Validation

### DoD (Definition of DONE)

1. ✅ ADR-0002 작성 완료
2. ✅ account_builder_policy.md Linear 기준 재작성
3. ✅ CLAUDE.md 수정 (Inverse → Linear)
4. ✅ sizing.py Linear 공식 구현
5. ✅ Oracle tests 통과 (Linear 기준)
6. ✅ Unit tests 통과 (Linear 기준)
7. ✅ Integration tests 통과 (회귀 없음)
8. ✅ Gate 7 Self-Verification ALL PASS
9. ✅ Evidence Artifacts 생성
10. ✅ task_plan.md Progress Table 업데이트

### Rollback Plan

**만약 Linear 전환이 실패하면**:
- Git revert로 Inverse 버전 복원
- 하지만 **실패 가능성 낮음** (공식은 단순하고 명확함)

---

## References

### Bybit Linear vs Inverse 차이

| 항목 | Inverse (BTC Coin-Margined) | Linear (USDT-Margined) |
|------|----------------------------|------------------------|
| **마진 통화** | BTC | USDT |
| **계약 단위** | 1 contract = 1 USD notional | 1 contract = 1 coin (e.g., BTC) |
| **Sizing 공식** | `loss_btc ≈ (contracts / entry_price) * stop_pct` | `loss_usdt = qty * price * stop_pct` |
| **Fee 계산** | `fee_usd ≈ contracts * fee_rate` | `fee_usdt = qty * price * fee_rate` |
| **PnL 계산** | BTC 기준 → USD 환산 | USDT 직접 계산 |
| **유동성** | 낮음 | 높음 |
| **접근성** | BTC 필요 (진입 장벽) | USDT 사용 (일반적) |

### External Links

- [Bybit Linear Futures 문서](https://www.bybit.com/en-US/help-center/bybitHC_Article?id=000001067&language=en_US)
- [Bybit Inverse Futures 문서](https://www.bybit.com/en-US/help-center/bybitHC_Article?id=000001135&language=en_US)

---

**Last Updated**: 2026-01-25
**Migration Estimated Completion**: 2026-01-25 (4-6 hours)
