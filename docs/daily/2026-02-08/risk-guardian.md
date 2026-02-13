# Daily Log — Risk & Safety Guardian
Date: 2026-02-08

## 1. Planned (아침 기준)
- [x] emergency.py equity 단위 검증
- [x] session_risk.py PnL 단위 검증
- [x] Kill Switch USDT 단위 확인

## 2. Done (팩트만)
- emergency.py: `get_equity_btc()` → `get_equity_usdt()` 전환
- fake_market_data.py: 생성자 `equity_btc` → `equity_usdt` 전환, `inject_balance_anomaly()` 수정
- market_data_interface.py: Protocol docstring 갱신
- tick_engine.py: snapshot 키 `equity_btc` → `equity_usdt` 갱신
- halt_logger.py: context snapshot docstring 갱신
- safety_limits.yaml: `testnet_symbol: "BTCUSD"` → `"BTCUSDT"` 수정
- 테스트 6개 파일 equity_btc → equity_usdt 동기화

## 3. Blocked / Issue
- Protocol `get_equity_btc()` deprecated 유지 (삭제 시기 미정)

## 4. Decision / Change
- ADR 필요 여부: NO

## 5. Next Action
- `get_equity_btc()` deprecated 메서드 삭제 시기 확정
- Failure Budget 정의 (WS/REST 장애 → HALT 기준)
