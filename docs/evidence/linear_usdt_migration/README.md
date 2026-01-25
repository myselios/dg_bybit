# Evidence: Linear USDT Migration
**Date**: 2026-01-25
**ADR**: [ADR-0002](../../adrs/ADR-0002-inverse-to-linear-usdt-migration.md)
**Commit**: 5b31655

## Overview
Bybit Inverse Futures (BTC Coin-Margined) → Linear Futures (USDT-Margined) 전환 완료.

## Files
- [red_green_proof.md](red_green_proof.md) - RED→GREEN 전환 증거
- [completion_checklist.md](completion_checklist.md) - DoD 자체 검증 체크리스트
- [pytest_output.txt](pytest_output.txt) - 전체 테스트 결과 (320 passed)

## Summary
- **Status**: ✅ COMPLETED
- **Test Results**: 320 passed, 15 deselected
- **Files Changed**: 63 files (897 insertions, 485 deletions)
- **Key Changes**:
  - Documents: ADR-0002, CLAUDE.md, account_builder_policy.md
  - Core: sizing.py (Linear formula), entry_coordinator.py, bybit_adapter.py
  - Infrastructure: market_data_interface.py (get_equity_usdt), fake_market_data.py
  - Tests: All tests updated (import paths, equity_usdt)

## Verification
```bash
# Quick verification (run from repo root)
$ venv/bin/pytest -v 2>&1 | tail -1
====================== 320 passed, 15 deselected in 0.49s ======================

# Linear formula check
$ grep -A 3 "qty_from_loss = " src/application/sizing.py
    qty_from_loss = params.max_loss_usdt / (
        params.entry_price_usd * params.stop_distance_pct
    )

# API category check
$ grep "category=" src/infrastructure/exchange/bybit_adapter.py | head -1
            tickers_response = self.rest_client.get_tickers(category="linear", symbol="BTCUSDT")
```

## References
- ADR: [ADR-0002](../../adrs/ADR-0002-inverse-to-linear-usdt-migration.md)
- SSOT: [account_builder_policy.md](../../specs/account_builder_policy.md)
- Project Guide: [CLAUDE.md](../../../CLAUDE.md)
