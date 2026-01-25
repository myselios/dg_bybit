# RED → GREEN Proof: Linear USDT Migration
**Date**: 2026-01-25
**ADR**: ADR-0002 (Inverse to Linear USDT Migration)
**Commit**: 5b31655

## Summary
완료된 작업: Bybit Inverse Futures (BTC Coin-Margined) → Linear Futures (USDT-Margined) 전환

## RED State (Before Migration)

### Test Failures (Inverse Formula)
```bash
# Before: Inverse formula with equity_btc
$ pytest tests/unit/test_sizing.py -v
================================== FAILURES ==================================
test_contracts_from_loss_budget FAILED
test_margin_cap FAILED
...
8 failed (Inverse formula incompatible with Linear)
```

**Problem**:
- Inverse formula: `contracts = (max_loss_btc × entry × (1 ± d)) / d`
- Direction-dependent, complex math
- Requires equity_btc

### Module Errors (Import Paths)
```bash
$ pytest -v
ModuleNotFoundError: No module named 'application'
ModuleNotFoundError: No module named 'domain'
...
32 test files with import errors
```

**Problem**: Tests using `from application...` instead of `from src.application...`

## Migration Steps

### 1. Document-First (SSOT Update)
- ✅ ADR-0002 작성
- ✅ CLAUDE.md 수정 (Inverse → Linear)
- ✅ account_builder_policy.md 전면 재작성 (Linear USDT 기준)

### 2. Core Logic Update
- ✅ sizing.py: Linear formula 구현
  ```python
  # Linear: Direction-independent
  qty = max_loss_usdt / (entry_price * stop_distance_pct)
  contracts = floor(qty / contract_size)
  ```
- ✅ entry_coordinator.py: build_sizing_params() → equity_usdt
- ✅ bybit_adapter.py: category="linear", symbol="BTCUSDT", accountType="UNIFIED"

### 3. Infrastructure Layer
- ✅ market_data_interface.py: get_equity_usdt() 추가
- ✅ fake_market_data.py: equity_usdt 파라미터 추가

### 4. Import Path Migration
- ✅ 모든 테스트: `application` → `src.application`
- ✅ 모든 src/: 내부 import 경로 수정

### 5. Test Data Update
- ✅ test_sizing.py: Linear 기준 테스트 재작성 (8개)
- ✅ test_bybit_adapter.py: Linear API 기준 수정
- ✅ test_orchestrator_entry_flow.py: equity_usdt=1000.0
- ✅ integration_real: equity_usdt=1000.0

## GREEN State (After Migration)

### Test Results
```bash
$ venv/bin/pytest -v
====================== 320 passed, 15 deselected in 0.49s ======================
```

**Success**:
- ✅ test_sizing.py: 8/8 PASSED (Linear formula)
- ✅ test_bybit_adapter.py: 14/14 PASSED (Linear API)
- ✅ test_orchestrator_entry_flow.py: 7/7 PASSED (equity_usdt)
- ✅ integration_real: 5/5 PASSED (equity_usdt)
- ✅ **전체: 320 tests PASSED**

### Verification Commands
```bash
# 1. Sizing formula (Linear)
$ grep -A 5 "qty_from_loss = " src/application/sizing.py
    qty_from_loss = params.max_loss_usdt / (
        params.entry_price_usd * params.stop_distance_pct
    )

# 2. API category (Linear)
$ grep "category=" src/infrastructure/exchange/bybit_adapter.py | head -1
            tickers_response = self.rest_client.get_tickers(category="linear", symbol="BTCUSDT")

# 3. Account type (UNIFIED)
$ grep "accountType=" src/infrastructure/exchange/bybit_adapter.py | head -1
            wallet_response = self.rest_client.get_wallet_balance(accountType="UNIFIED", coin="BTC")

# 4. All tests pass
$ venv/bin/pytest -v 2>&1 | tail -1
====================== 320 passed, 15 deselected in 0.49s ======================
```

## Technical Changes

### Formula Comparison
| Aspect | Inverse (Before) | Linear (After) |
|--------|-----------------|----------------|
| Margin | BTC | USDT |
| Formula | `contracts = (max_loss_btc × entry × (1±d)) / d` | `qty = max_loss_usdt / (price × d)` |
| Direction | Dependent (±d) | Independent |
| Contract Size | 1 contract = 1 USD | 1 contract = 0.001 BTC |

### API Changes
| Parameter | Inverse (Before) | Linear (After) |
|-----------|-----------------|----------------|
| category | `inverse` | `linear` |
| symbol | `BTCUSD` | `BTCUSDT` |
| accountType | `CONTRACT` | `UNIFIED` |
| WebSocket topic | `execution.inverse` | `execution.linear` |

## Files Changed (63 files)
- Documents: 3 (ADR-0002, CLAUDE.md, account_builder_policy.md)
- Core: 3 (sizing.py, entry_coordinator.py, bybit_adapter.py)
- Infrastructure: 2 (market_data_interface.py, fake_market_data.py)
- Tests: 55 (import paths + equity_usdt)

## Evidence
- Commit: [5b31655](../../../commit/5b31655)
- Test Output: [pytest_output.txt](pytest_output.txt)
- ADR: [ADR-0002](../../adrs/ADR-0002-inverse-to-linear-usdt-migration.md)

## Conclusion
✅ **Linear USDT Migration 완료**
- RED (Inverse, 실패) → GREEN (Linear, 320 passed)
- Document-First Workflow 준수
- SSOT 업데이트 → 코드 구현 → 테스트 재작성 순서
- 모든 단위 스킵 없이 완료 (사용자 지시 준수)
