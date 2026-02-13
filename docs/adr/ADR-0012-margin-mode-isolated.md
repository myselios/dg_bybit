# ADR-0012: Margin Mode Isolated Enforcement

**Status**: Accepted
**Date**: 2026-02-08
**Deciders**: Account Builder Architecture Review
**Related**: ADR-0002 (Linear USDT Migration), Phase 12b (Mainnet Dry-Run)

---

## Context and Problem Statement

현재 시스템은 **Bybit Linear USDT Futures** 기반으로 구현되어 있으나, **Margin Mode (격리/교차)가 문서와 코드 어디에도 명시되지 않음**:

- **문서 누락**:
  - `account_builder_policy.md`: Margin Mode 언급 없음
  - `FLOW.md`: Margin Mode 언급 없음
  - `agent_team.md`: Margin Mode 언급 없음
- **코드 누락**:
  - `bybit_rest_client.py`: `set_margin_mode()` 메서드 없음
  - API 호출 시 Margin Mode 파라미터 없음
- **현재 상태**: Bybit 계정의 **수동 설정에 의존** (Isolated로 설정됨, 2026-02-08 확인)

### 치명적 문제

1. **계정 설정 변경 시 감지 불가**:
   - Bybit 웹/앱에서 Cross Margin으로 변경 시 → 전체 계좌 청산 위험
   - 시스템이 Margin Mode를 확인/강제하지 않음

2. **신규 환경 구축 시 누락**:
   - Testnet/Mainnet 전환 시 Margin Mode 설정 잊을 수 있음
   - 기본값 의존 → 환경마다 다를 수 있음

3. **SSOT 위반**:
   - 핵심 리스크 설정(Margin Mode)이 문서에 없음
   - 운영자/개발자가 "어떤 Margin Mode를 사용하는가?" 알 수 없음

### Margin Mode 비교

| 항목 | Isolated (격리) | Cross (교차) |
|------|----------------|-------------|
| 증거금 할당 | 포지션마다 독립 | 전체 계좌 공유 |
| 청산 영향 | 해당 포지션만 청산 | 전체 계좌 청산 위험 |
| 리스크 격리 | ✅ 완전 격리 | ❌ 연결됨 |
| 포지션 크기 | 독립 증거금 필요 (작음) | 공유 증거금 (큼) |
| Account Builder 적합성 | ✅ 적합 (청산 방지 최우선) | ❌ 부적합 (전체 청산 위험) |

---

## Decision Drivers

1. **청산 방지 최우선**:
   - Account Builder 목표: "청산(Liquidation) = 실패" (CLAUDE.md Section 1)
   - Isolated Margin = 리스크 격리 → 한 포지션 청산 시 다른 포지션/잔고 보호

2. **명확한 정책 필요**:
   - Margin Mode는 "핵심 리스크 설정"이므로 SSOT 문서 명시 필수
   - 수동 설정 의존 금지 → 코드로 강제

3. **신규 환경 안전성**:
   - Testnet/Mainnet 전환 시 Margin Mode 설정 자동화
   - 프로세스 시작 시 Margin Mode 검증 (향후 구현)

4. **Stage 1 특성**:
   - Stage 1 (equity < $300)에서는 **1회 1포지션만 진입**
   - Isolated vs Cross 차이가 현재는 없음
   - 하지만 향후 Stage 2/3에서 복수 포지션 가능 → Isolated 필수

---

## Considered Options

### Option 1: Cross Margin (교차 마진)
**Pros**:
- 동일 증거금으로 더 큰 포지션 가능
- 증거금 효율성 높음

**Cons**:
- ❌ **전체 계좌 청산 위험** (한 포지션 청산 시 전체 잔고 손실)
- ❌ Account Builder 목표("청산 방지")와 상충
- ❌ 리스크 격리 불가능

**거부 이유**: 청산 방지가 최우선 목표 → Cross Margin 부적합

### Option 2: Isolated Margin (격리 마진) — **SELECTED**
**Pros**:
- ✅ **리스크 격리** (한 포지션 청산 시 다른 포지션/잔고 보호)
- ✅ Account Builder 목표와 일치 (청산 방지 최우선)
- ✅ 명확한 손실 상한 (포지션당 독립)

**Cons**:
- 포지션당 독립 증거금 필요 (동일 증거금으로 Cross 대비 포지션 작음)
- Stage 1에서는 1회 1포지션만이라 영향 없음

**선택 이유**: 청산 방지 최우선 목표 달성 + Stage 1 현재 환경에서 단점 없음

### Option 3: 문서만 명시 (코드 강제 없음)
**Pros**:
- 구현 불필요 (빠름)

**Cons**:
- ❌ 수동 설정 의존 → 실수 가능
- ❌ 신규 환경 구축 시 누락 위험

**거부 이유**: 핵심 리스크 설정은 코드로 강제해야 함

---

## Decision Outcome

**Chosen option**: **Option 2 — Isolated Margin Enforcement**

### Rationale

1. **청산 방지 최우선**:
   - Isolated Margin = 리스크 격리 → Account Builder 목표 달성
   - Cross Margin = 전체 청산 위험 → 목표 상충

2. **Stage 1 환경 적합**:
   - 현재 Stage 1 (equity < $300)에서는 1회 1포지션만 진입
   - Isolated 단점(포지션 크기 작음) 없음

3. **향후 확장성**:
   - Stage 2/3에서 복수 포지션 진입 시 Isolated 필수
   - 지금부터 Isolated로 고정 → 일관성 유지

4. **코드 강제 필요**:
   - 핵심 리스크 설정은 수동 설정 의존 금지
   - `set_margin_mode("ISOLATED")` 자동 호출로 안전성 확보

---

## Consequences

### Positive

- ✅ **청산 리스크 격리**: 한 포지션 청산 시 다른 포지션/잔고 보호
- ✅ **SSOT 완성**: 핵심 리스크 설정(Margin Mode) 문서 명시
- ✅ **신규 환경 안전성**: Testnet/Mainnet 전환 시 Margin Mode 자동 설정
- ✅ **명확한 손실 상한**: 포지션당 독립 증거금 → 예측 가능한 리스크

### Negative / Trade-offs

- 포지션당 독립 증거금 필요 (Cross 대비 포지션 크기 작음)
  - **현재 영향 없음**: Stage 1에서는 1회 1포지션만
  - **향후**: Stage 2/3에서도 리스크 격리가 우선
- 구현 작업 필요 (ADR + 문서 + 코드)
  - **수용 가능**: 약 2시간 작업, 청산 방지 대비 충분한 투자

### Implementation Checklist

- [x] ADR-0012 작성 (본 문서)
- [ ] `account_builder_policy.md` Section 10.0 추가 (Margin Mode 정책)
- [ ] `FLOW.md` Section 4.5 업데이트 (`isLeverage=true` 명시)
- [ ] `bybit_rest_client.py`에 `set_margin_mode()` 추가
- [ ] `safety_limits.yaml` 주석 명확화 (leverage 참고값 명시)
- [ ] `CLAUDE.md` Section 5.7에 Gate 10 추가 (Margin Mode 검증)

---

## Implementation Details

### 1. API 호출 (Bybit V5 API)

```python
# /v5/position/set-leverage
# Request:
{
    "category": "linear",
    "symbol": "BTCUSDT",
    "buyLeverage": "3",    # Stage별 leverage
    "sellLeverage": "3",
    "tradeMode": 0         # 0=Isolated, 1=Cross (Portfolio Margin)
}
```

### 2. Leverage vs Margin Mode 분리

- **Leverage**: Stage별 동적 변경 (Stage 1/2: 3x, Stage 3: 2x)
- **Margin Mode**: Isolated 고정 (변경 금지)

두 개념은 **독립적**:
- Isolated Margin에서도 Leverage 3x 사용 가능
- Cross Margin에서도 Leverage 1x 사용 가능

### 3. 프로세스 시작 시 검증 (향후 구현)

```python
# 프로세스 시작 시 Margin Mode 확인 (Phase 13+)
def verify_margin_mode(client: BybitRestClient, symbol: str = "BTCUSDT"):
    """
    Margin Mode가 Isolated인지 확인

    Raises:
        FatalConfigError: Margin Mode가 Cross인 경우
    """
    position = client.get_position(category="linear", symbol=symbol)
    trade_mode = position["result"]["list"][0]["tradeMode"]

    if trade_mode != 0:  # 0=Isolated, 1=Cross
        raise FatalConfigError(
            f"Margin Mode must be ISOLATED (tradeMode=0), got tradeMode={trade_mode}. "
            f"Please set Margin Mode to Isolated in Bybit settings."
        )
```

---

## Backward Compatibility

- **기존 포지션**: 없음 (현재 FLAT 상태)
- **기존 설정**: Isolated로 이미 설정됨 (2026-02-08 확인)
- **마이그레이션**: 불필요

---

## Rollback Plan

Rollback 불필요 (Isolated → Cross 전환은 Account Builder 목표와 상충).

만약 긴급 사유로 Cross Margin이 필요하면:
1. Bybit 웹/앱에서 수동 전환 (API 호출 불필요)
2. 시스템 재시작 (검증 로직 우회, 단 Phase 13+ 구현 후에는 불가)

---

## References

- Bybit Margin Mode 문서: https://bybit-exchange.github.io/docs/v5/position/leverage
- ADR-0002: Inverse to Linear USDT Migration
- CLAUDE.md Section 1: 절대 금지 (청산 = 실패)
- account_builder_policy.md Section 3.2: Hard Stops
