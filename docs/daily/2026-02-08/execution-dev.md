# Daily Log — Execution Engine Developer
Date: 2026-02-08

## 1. Planned (아침 기준)
- [x] bybit_rest_client.py category/symbol 기본값 검증
- [x] bybit_adapter.py Inverse 잔존 검증
- [x] order_executor.py / event_handler.py symbol 검증

## 2. Done (팩트만)
- bybit_rest_client.py: 5개 메서드 기본값 `category="inverse"` → `"linear"`, `symbol="BTCUSD"` → `"BTCUSDT"` 수정
- get_wallet_balance: `accountType="CONTRACT", coin="BTC"` → `"UNIFIED", coin="USDT"` 수정
- orchestrator.py: Stop 관리 4곳 `BTCUSD` → `BTCUSDT` 수정
- event_handler.py: Stop 설치 2곳 `BTCUSD` → `BTCUSDT` 수정
- order_executor.py: docstring 2곳 `BTCUSD` → `BTCUSDT` 수정
- event_processor.py: Inverse 주석 제거
- bybit_ws_client.py: docstring `BTCUSD` → `BTCUSDT` 수정
- bybit_adapter.py: Inverse 주석 정리

## 3. Blocked / Issue
- 없음

## 4. Decision / Change
- ADR 필요 여부: NO (코드 기본값 변경은 ADR-0002 범위)

## 5. Next Action
- bybit_adapter.py `_equity_btc` 필드 완전 제거 (get_equity_usdt만 유지)
- WS subscription topic 확인 (execution.linear vs execution.inverse)
